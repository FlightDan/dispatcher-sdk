"""Lifecycle host for the local Kernel/Execution Bridge.

The host is intentionally an integration boundary, not another workflow
layer.  One coordinator owns every Bridge call; a fixed pool owns only
``runtime.run_once`` calls.  This keeps the Bridge event cursor and its
delivery leases single-writer while allowing Kernel executions to overlap.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
import threading
import time
from typing import Any, Callable, Protocol

from .runtime import InProcessRuntime


class RuntimeHostBridge(Protocol):
    """The small transport surface required by :class:`RuntimeHost`."""

    def pump(self, *, limit: int = 100) -> object: ...

    def sweep(self, *, limit: int = 100) -> object: ...


@dataclass(frozen=True)
class RuntimeHostError:
    at: float
    source: str
    error_type: str
    message: str
    consecutive: int


@dataclass(frozen=True)
class RuntimeHostHealth:
    state: str
    coordinator_alive: bool
    worker_count: int
    active_workers: int
    completed_workers: int
    wake_count: int
    last_pump_at: float | None
    last_sweep_at: float | None
    error_count: int
    retry_count: int
    last_error: RuntimeHostError | None
    recent_errors: tuple[RuntimeHostError, ...]


@dataclass(frozen=True)
class StopPhase:
    """One observable phase of a host shutdown."""

    name: str
    status: str
    started_at: float | None
    finished_at: float | None
    elapsed_seconds: float | None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StopReport:
    """A point-in-time, JSON-serializable snapshot of host shutdown.

    ``pending_delivery_count`` and ``pending_delivery_persisted`` are scoped to
    application notification delivery.  ``None`` means the host did not
    observe the value; shutdown reporting never performs a potentially
    blocking durable-store scan to fill either field.

    ``can_continue_waiting`` describes whether an unfinished host thread was
    still observable when the snapshot was made.  It does not promise that
    waiting will finish or cancel the operation that is holding shutdown up.
    """

    scope: str
    status: str
    started_at: float
    finished_at: float | None
    elapsed_seconds: float
    timeout_seconds: float | None
    phases: tuple[StopPhase, ...]
    unfinished_phases: tuple[str, ...]
    active_worker_count: int
    notification_thread_alive: bool | None
    pending_delivery_count: int | None
    pending_delivery_persisted: bool | None
    can_continue_waiting: bool
    errors: tuple[RuntimeHostError, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeHost:
    """Run the Kernel and Bridge continuously inside one process.

    ``RuntimeHost`` owns the supplied runtime for its lifetime.  ``stop``
    drains active ``run_once`` calls, performs one final Bridge flush, closes
    the runtime, and joins the coordinator.  If a finite stop timeout expires,
    the runtime is closed immediately so process supervisors are revoked and
    the workers can return.
    """

    def __init__(
        self,
        runtime: InProcessRuntime,
        bridge: RuntimeHostBridge,
        *,
        worker_count: int = 4,
        sweep_interval: float = 1.0,
        pump_interval: float = 0.05,
        batch_size: int = 100,
        retry_initial: float = 0.1,
        retry_max: float = 5.0,
        progress_hook: Callable[[], bool] | None = None,
    ) -> None:
        if not callable(getattr(runtime, "run_once", None)):
            raise TypeError("runtime must provide run_once")
        if not callable(getattr(runtime, "reap", None)):
            raise TypeError("runtime must provide reap")
        if not callable(getattr(runtime, "close", None)):
            raise TypeError("runtime must provide close")
        if not callable(getattr(bridge, "pump", None)) or not callable(
            getattr(bridge, "sweep", None)
        ):
            raise TypeError("bridge must provide pump and sweep")
        self.runtime = runtime
        self.bridge = bridge
        self.worker_count = self._positive_int(worker_count, "worker_count")
        self.sweep_interval = self._positive_number(sweep_interval, "sweep_interval")
        self.pump_interval = self._positive_number(pump_interval, "pump_interval")
        self.batch_size = self._positive_int(batch_size, "batch_size")
        self.retry_initial = self._positive_number(retry_initial, "retry_initial")
        self.retry_max = self._positive_number(retry_max, "retry_max")
        if self.retry_max < self.retry_initial:
            raise ValueError("retry_max must be at least retry_initial")
        if progress_hook is not None and not callable(progress_hook):
            raise TypeError("progress_hook must be callable or None")
        self.progress_hook = progress_hook

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._state = "new"
        self._coordinator: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._futures: set[Future[Any]] = set()
        self._wake_pending = False
        self._wake_count = 0
        self._completed_workers = 0
        self._last_pump_at: float | None = None
        self._last_sweep_at: float | None = None
        self._error_count = 0
        self._retry_count = 0
        self._last_error: RuntimeHostError | None = None
        self._recent_errors: list[RuntimeHostError] = []
        self._consecutive_errors: dict[str, int] = {}
        self._retry_at: dict[str, float] = {}
        self._runtime_stop_requested = False
        self._shutdown_lock = threading.Lock()
        self._shutdown_attempted = False
        self._shutdown_error: BaseException | None = None
        self._stop_started_at: float | None = None
        self._stop_finished_at: float | None = None
        self._stop_timeout: float | None = None
        self._stop_status = "not_started"
        self._stop_phases: dict[str, dict[str, Any]] = {
            name: {
                "status": "not_started",
                "started_at": None,
                "finished_at": None,
                "error_type": None,
                "error_message": None,
            }
            for name in (
                "worker_drain",
                "executor_shutdown",
                "final_pump",
                "runtime_close",
            )
        }

        # A composition created before this host may have handed the Bridge
        # an adapter which still points only at SQLiteKernel.  Binding here is
        # deliberately duck-typed so RuntimeHost does not own Orchestrator
        # models or import the business transport.
        bind_runtime = getattr(getattr(bridge, "kernel", None), "bind_runtime", None)
        if callable(bind_runtime):
            bind_runtime(runtime)

    @staticmethod
    def _positive_int(value: object, label: str) -> int:
        if type(value) is not int or value < 1:
            raise ValueError(f"{label} must be a positive integer")
        return value

    @staticmethod
    def _positive_number(value: object, label: str) -> float:
        if type(value) not in {int, float} or value <= 0:
            raise ValueError(f"{label} must be a positive number")
        result = float(value)
        if result != result or result in {float("inf"), float("-inf")}:
            raise ValueError(f"{label} must be finite")
        return result

    def start(self) -> "RuntimeHost":
        with self._lock:
            if self._state in {"starting", "running"}:
                return self
            if self._state in {"stopping", "stopped", "failed"}:
                raise RuntimeError(f"cannot start host in state {self._state}")
            self._state = "starting"
            self._stop_event.clear()
            try:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.worker_count,
                    thread_name_prefix="runtime-host-worker",
                )
                self._coordinator = threading.Thread(
                    target=self._run,
                    name="runtime-host-coordinator",
                    daemon=False,
                )
                self._coordinator.start()
            except BaseException:
                # Construction and start failures have no coordinator to own
                # shutdown. Preserve the original failure and retain any
                # cleanup failure for subsequent stop callers.
                self._coordinator = None
                self._state = "failed"
                self._stop_event.set()
                self._wake_event.set()
                self._shutdown_resources()
                raise
        self.wake()
        return self

    def wake(self, run_id: str | None = None) -> bool:
        """Wake scheduling after a durable submission or external signal."""

        del run_id  # The Kernel queue is global; scheduling is not per Run.
        with self._lock:
            if self._state in {"stopped", "failed"}:
                return False
            self._wake_count += 1
            self._wake_pending = True
            self._wake_event.set()
            return True

    def health(self) -> RuntimeHostHealth:
        with self._lock:
            coordinator_alive = bool(
                self._coordinator is not None and self._coordinator.is_alive()
            )
            return RuntimeHostHealth(
                state=self._state,
                coordinator_alive=coordinator_alive,
                worker_count=self.worker_count,
                active_workers=len(self._futures),
                completed_workers=self._completed_workers,
                wake_count=self._wake_count,
                last_pump_at=self._last_pump_at,
                last_sweep_at=self._last_sweep_at,
                error_count=self._error_count,
                retry_count=self._retry_count,
                last_error=self._last_error,
                recent_errors=tuple(self._recent_errors),
            )

    def join(self, timeout: float | None = None) -> bool:
        if timeout is not None and (
            type(timeout) not in {int, float} or timeout < 0
        ):
            raise ValueError("timeout must be a non-negative number or None")
        with self._lock:
            coordinator = self._coordinator
        if coordinator is None:
            return True
        coordinator.join(timeout)
        return not coordinator.is_alive()

    @property
    def stop_report(self) -> StopReport | None:
        """Return the latest shutdown snapshot, or ``None`` before shutdown."""

        with self._lock:
            return self._stop_report_locked()

    def _stop_report_locked(self) -> StopReport | None:
        started_at = self._stop_started_at
        if started_at is None:
            return None
        now = time.monotonic()
        phases = tuple(
            self._phase_snapshot_locked(name, values, now)
            for name, values in self._stop_phases.items()
        )
        coordinator_alive = bool(
            self._coordinator is not None and self._coordinator.is_alive()
        )
        finished_at = self._stop_finished_at
        return StopReport(
            scope="runtime_host",
            status=self._stop_status,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=max(
                0.0, (finished_at if finished_at is not None else now) - started_at
            ),
            timeout_seconds=self._stop_timeout,
            phases=phases,
            unfinished_phases=tuple(
                phase.name
                for phase in phases
                if phase.status not in {"completed", "skipped"}
            ),
            active_worker_count=len(self._futures),
            notification_thread_alive=None,
            pending_delivery_count=None,
            pending_delivery_persisted=None,
            can_continue_waiting=coordinator_alive,
            errors=tuple(self._recent_errors),
        )

    @staticmethod
    def _phase_snapshot_locked(
        name: str, values: dict[str, Any], now: float
    ) -> StopPhase:
        started_at = values["started_at"]
        finished_at = values["finished_at"]
        elapsed = None
        if started_at is not None:
            elapsed = max(
                0.0, (finished_at if finished_at is not None else now) - started_at
            )
        return StopPhase(
            name=name,
            status=values["status"],
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=elapsed,
            error_type=values["error_type"],
            error_message=values["error_message"],
        )

    def _begin_stop(self, timeout: float | None) -> None:
        with self._lock:
            first_stop = self._stop_started_at is None
            if first_stop:
                self._stop_started_at = time.monotonic()
            if self._stop_status in {"completed", "failed"}:
                return
            # The coordinator also enters this method from ``finally``.  Do
            # not let that unbounded internal cleanup erase the caller's
            # finite deadline from the report.
            if first_stop or timeout is not None:
                self._stop_timeout = timeout
            self._stop_status = "in_progress"
            self._stop_finished_at = None

    def _start_stop_phase(self, name: str) -> None:
        with self._lock:
            values = self._stop_phases[name]
            if values["status"] == "not_started":
                values["status"] = "in_progress"
                values["started_at"] = time.monotonic()

    def _finish_stop_phase(
        self, name: str, *, error: BaseException | None = None, skipped: bool = False
    ) -> None:
        with self._lock:
            values = self._stop_phases[name]
            now = time.monotonic()
            if values["started_at"] is None and not skipped:
                values["started_at"] = now
            values["finished_at"] = now
            if error is not None:
                values["status"] = "failed"
                values["error_type"] = type(error).__name__
                values["error_message"] = str(error)
            else:
                values["status"] = "skipped" if skipped else "completed"

    def _finish_stop(self, status: str) -> None:
        with self._lock:
            if self._stop_status == "failed" and status != "failed":
                return
            if status == "timed_out" and self._stop_status in {"completed", "failed"}:
                return
            self._stop_status = status
            self._stop_finished_at = (
                time.monotonic() if status in {"completed", "failed"} else None
            )

    def stop(self, timeout: float | None = None) -> bool:
        """Stop scheduling, drain workers, and close the supplied runtime."""

        if timeout is not None and (
            type(timeout) not in {int, float} or timeout < 0 or not float(timeout) < float("inf")
        ):
            raise ValueError("timeout must be a finite non-negative number or None")
        stop_called_at = time.monotonic()
        deadline = None if timeout is None else stop_called_at + timeout
        self._begin_stop(None if timeout is None else float(timeout))
        with self._lock:
            if self._state == "new":
                self._state = "stopping"
                coordinator = None
            elif self._state == "stopped":
                self._finish_stop("completed")
                return True
            elif self._state == "failed" and self._coordinator is None:
                coordinator = None
            else:
                if self._state != "failed":
                    self._state = "stopping"
                coordinator = self._coordinator
            self._stop_event.set()
            self._wake_event.set()

        if coordinator is None:
            self._finish_stop_phase("worker_drain", skipped=True)
            self._shutdown_resources()
            try:
                self._raise_shutdown_error()
            except BaseException:
                self._finish_stop("failed")
                raise
            self._finish_stop("completed")
            return True

        if timeout is None:
            coordinator.join()
        else:
            graceful_deadline = stop_called_at + timeout / 2.0
            coordinator.join(max(0.0, graceful_deadline - time.monotonic()))
            if coordinator.is_alive():
                # Revoke active handler authority without closing the Kernel.
                # The coordinator remains the sole owner of final Bridge
                # flushing and runtime.close, so callers can safely preserve
                # the Orchestrator store when the bounded join returns false.
                self._request_runtime_stop_once()
                coordinator.join(max(0.0, deadline - time.monotonic()))
        if coordinator.is_alive():
            self._finish_stop("timed_out")
            return False
        self._shutdown_resources(flush=True)
        try:
            self._raise_shutdown_error()
        except BaseException:
            self._finish_stop("failed")
            raise
        self._finish_stop("completed")
        return True

    def _raise_shutdown_error(self) -> None:
        with self._lock:
            error = self._shutdown_error
        if error is not None:
            raise RuntimeError(f"RuntimeHost cleanup failed: {error}") from error

    def _shutdown_resources(self, *, flush: bool = False) -> None:
        # One owner closes each resource. A failed close is not a successful
        # stop, and calling stop again cannot erase that failure.
        with self._shutdown_lock:
            if self._shutdown_attempted:
                return
            executor = self._executor
            if executor is not None:
                with self._lock:
                    drain_complete = self._stop_phases["worker_drain"]["status"] == "completed"
                if not drain_complete:
                    self._start_stop_phase("worker_drain")
                self._start_stop_phase("executor_shutdown")
                try:
                    executor.shutdown(wait=True, cancel_futures=True)
                except BaseException as exc:
                    self._finish_stop_phase("executor_shutdown", error=exc)
                    self._record_error("executor_shutdown", exc)
                    with self._lock:
                        self._shutdown_error = exc
                        self._state = "failed"
                    # Before coordinator startup there can be no submitted
                    # worker. Otherwise preserve the runtime until a later
                    # stop can complete executor shutdown.
                    if self._coordinator is not None:
                        return
                else:
                    self._collect_workers()
                    if not drain_complete:
                        self._finish_stop_phase("worker_drain")
                    self._finish_stop_phase("executor_shutdown")
            else:
                with self._lock:
                    drain_status = self._stop_phases["worker_drain"]["status"]
                if drain_status == "not_started":
                    self._finish_stop_phase("worker_drain", skipped=True)
                self._finish_stop_phase("executor_shutdown", skipped=True)
            self._shutdown_attempted = True
            if flush:
                self._start_stop_phase("final_pump")
                errors_before = self.health().error_count
                try:
                    self._pump()
                    self._run_progress_hook()
                except BaseException as exc:
                    self._record_error("final_pump", exc)
                if self.health().error_count != errors_before:
                    error = RuntimeError("final Bridge flush failed")
                    self._finish_stop_phase("final_pump", error=error)
                    with self._lock:
                        self._shutdown_error = error
                        self._state = "failed"
                else:
                    self._finish_stop_phase("final_pump")
            else:
                self._finish_stop_phase("final_pump", skipped=True)
            self._start_stop_phase("runtime_close")
            try:
                self.runtime.close()
            except BaseException as exc:
                self._finish_stop_phase("runtime_close", error=exc)
                self._record_error("runtime_close", exc)
                with self._lock:
                    self._shutdown_error = exc
                    self._state = "failed"
            else:
                self._finish_stop_phase("runtime_close")
                with self._lock:
                    self._executor = None
                    if self._state != "failed":
                        self._state = "stopped"

    def _record_error(self, source: str, error: BaseException) -> None:
        with self._lock:
            consecutive = self._consecutive_errors.get(source, 0) + 1
            record = RuntimeHostError(
                at=time.monotonic(),
                source=source,
                error_type=type(error).__name__,
                message=str(error),
                consecutive=consecutive,
            )
            self._consecutive_errors[source] = consecutive
            self._retry_at[source] = record.at + min(
                self.retry_max,
                self.retry_initial * (2 ** min(consecutive - 1, 10)),
            )
            self._error_count += 1
            self._retry_count += 1
            self._last_error = record
            self._recent_errors.append(record)
            del self._recent_errors[:-32]

    def _request_runtime_stop_once(self) -> None:
        with self._lock:
            if self._runtime_stop_requested:
                return
            self._runtime_stop_requested = True
        request_stop = getattr(self.runtime, "request_stop", None)
        if callable(request_stop):
            try:
                request_stop()
            except BaseException as exc:
                self._record_error("runtime_stop", exc)

    def _clear_error(self, source: str) -> None:
        with self._lock:
            self._consecutive_errors[source] = 0
            self._retry_at[source] = 0.0

    def _retry_ready(self, source: str, now: float) -> bool:
        with self._lock:
            return now >= self._retry_at.get(source, 0.0)

    def _scheduled_retry_at(self, source: str, scheduled_at: float) -> float:
        with self._lock:
            return max(scheduled_at, self._retry_at.get(source, 0.0))

    def _startup(self) -> bool:
        try:
            self.runtime.reap()
            report = self.bridge.sweep(limit=self.batch_size)
        except BaseException as exc:
            self._record_error("startup", exc)
            return False
        with self._lock:
            self._last_sweep_at = time.monotonic()
            self._last_pump_at = self._last_sweep_at
            self._wake_pending = True
            self._state = "running"
        self._clear_error("startup")
        self._request_workers_from_report(report)
        return True

    def _sweep(self) -> object | None:
        try:
            self.runtime.reap()
            report = self.bridge.sweep(limit=self.batch_size)
        except BaseException as exc:
            self._record_error("sweep", exc)
            return None
        now = time.monotonic()
        with self._lock:
            self._last_sweep_at = now
            self._last_pump_at = now
        self._clear_error("sweep")
        self._request_workers_from_report(report)
        return report

    def _pump(self) -> object | None:
        try:
            report = self.bridge.pump(limit=self.batch_size)
        except BaseException as exc:
            self._record_error("pump", exc)
            return None
        with self._lock:
            self._last_pump_at = time.monotonic()
        self._clear_error("pump")
        self._request_workers_from_report(report)
        return report

    def _run_progress_hook(self) -> bool:
        hook = self.progress_hook
        if hook is None:
            return False
        try:
            progressed = hook()
            if type(progressed) is not bool:
                raise TypeError("progress_hook must return a boolean")
        except BaseException as exc:
            self._record_error("progress_hook", exc)
            return False
        self._clear_error("progress_hook")
        if progressed:
            with self._lock:
                self._wake_pending = True
                self._wake_event.set()
        return progressed

    def _request_workers_from_report(self, report: object) -> None:
        if any(
            getattr(report, name, 0) > 0
            for name in ("dispatch_deliveries",)
        ):
            with self._lock:
                self._wake_pending = True
                self._wake_event.set()

    def _collect_workers(self) -> bool:
        progress = False
        with self._lock:
            done = tuple(future for future in self._futures if future.done())
            for future in done:
                self._futures.remove(future)
        for future in done:
            try:
                result = future.result()
            except BaseException as exc:
                self._record_error("worker", exc)
            else:
                with self._lock:
                    self._completed_workers += 1
                self._clear_error("worker")
                if result is not None:
                    progress = True
        return progress

    def _fill_workers(self, *, force: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            wake_pending = self._wake_pending
            if wake_pending:
                self._wake_pending = False
            active = len(self._futures)
            next_poll = getattr(self, "_next_worker_poll", 0.0)
        if not force and not wake_pending and now < next_poll:
            return
        if not self._retry_ready("worker", now) or not self._retry_ready("worker_submit", now):
            return
        executor = self._executor
        if executor is None:
            return
        for _ in range(self.worker_count - active):
            try:
                future = executor.submit(self.runtime.run_once)
            except BaseException as exc:
                self._record_error("worker_submit", exc)
                break
            self._clear_error("worker_submit")
            with self._lock:
                self._futures.add(future)
        self._next_worker_poll = now + self.pump_interval

    def _wait(
        self, deadline: float | None = None, *, allow_stopping: bool = False
    ) -> None:
        if self._stop_event.is_set() and not allow_stopping:
            return
        timeout = self.pump_interval
        if deadline is not None:
            timeout = min(timeout, max(0.0, deadline - time.monotonic()))
        self._wake_event.wait(timeout)
        self._wake_event.clear()

    def _drain_workers(self) -> None:
        self._start_stop_phase("worker_drain")
        while True:
            self._collect_workers()
            with self._lock:
                active = len(self._futures)
            if active == 0:
                self._finish_stop_phase("worker_drain")
                return
            self._wait(allow_stopping=True)

    def _run(self) -> None:
        try:
            startup_ready = False
            next_sweep = time.monotonic()
            next_pump = time.monotonic()
            next_progress = time.monotonic()
            while True:
                if startup_ready:
                    progress = self._collect_workers()
                    if self._stop_event.is_set():
                        self._drain_workers()
                        break
                    now = time.monotonic()
                    if (
                        now >= next_sweep
                        and self._retry_ready("sweep", now)
                    ):
                        self._sweep()
                        next_sweep = now + self.sweep_interval
                    if now >= next_pump and self._retry_ready("pump", now):
                        self._pump()
                        next_pump = now + self.pump_interval
                    if now >= next_progress and self._retry_ready("progress_hook", now):
                        self._run_progress_hook()
                        next_progress = now + self.pump_interval
                    self._fill_workers(force=progress)
                    # A failed operation may be due for its regular poll but
                    # still in backoff. Sleeping to that expired poll deadline
                    # would spin the coordinator until its retry becomes due.
                    # Each channel keeps its own deadline so a failed pump or
                    # policy callback does not hold up the other channels.
                    self._wait(min(
                        self._scheduled_retry_at("sweep", next_sweep),
                        self._scheduled_retry_at("pump", next_pump),
                        self._scheduled_retry_at("progress_hook", next_progress),
                    ))
                    continue

                now = time.monotonic()
                if self._stop_event.is_set():
                    break
                if self._retry_ready("startup", now):
                    startup_ready = self._startup()
                if not startup_ready:
                    self._wait(self._retry_at.get("startup", now))
            # Let already-produced terminal results/outbox acks leave the
            # process before closing the Kernel connection.
            if startup_ready and not self._stop_event.is_set():
                self._pump()
        except BaseException as exc:
            self._record_error("coordinator", exc)
            with self._lock:
                self._state = "failed"
        finally:
            # A coordinator failure must revoke active authority and wait for
            # every worker before closing the Kernel/SQLite connection.  In
            # particular, ``shutdown(wait=False)`` here creates a use-after-
            # close race for a still-running ``run_once``.
            self._stop_event.set()
            self._begin_stop(None)
            self._request_runtime_stop_once()
            self._shutdown_resources(flush=startup_ready)
            with self._lock:
                failed = self._shutdown_error is not None or self._state == "failed"
            self._finish_stop("failed" if failed else "completed")


__all__ = [
    "RuntimeHost", "RuntimeHostBridge", "RuntimeHostError", "RuntimeHostHealth",
    "StopPhase", "StopReport",
]
