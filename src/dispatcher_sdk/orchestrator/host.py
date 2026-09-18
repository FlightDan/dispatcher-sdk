"""Autonomous Kernel execution and durable application notification delivery."""

from __future__ import annotations

from dataclasses import dataclass, fields
import threading
import time
from typing import Callable
from uuid import uuid4

from ..execution_kernel.host import (
    RuntimeHost,
    RuntimeHostHealth,
    StopPhase,
    StopReport,
)


@dataclass(frozen=True)
class OrchestratorHostHealth(RuntimeHostHealth):
    notification_alive: bool
    notification_deliveries: int
    notification_error_count: int
    last_notification_error: str | None


class OrchestratorHostTimeoutError(TimeoutError):
    """A bounded host stop expired; ``report`` describes observed progress."""

    def __init__(self, message: str, report: StopReport) -> None:
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class _Report:
    dispatch_deliveries: int


class _Transport:
    def __init__(self, orchestrator, wake_notifications):
        self.orchestrator = orchestrator
        self.wake_notifications = wake_notifications

    def pump(self, *, limit=100):
        resume = getattr(self.orchestrator, "resume_recoveries", None)
        if callable(resume):
            resume(limit=min(limit, 20))
        delivered = self.orchestrator.flush(limit=limit)
        self.orchestrator.sync()
        if self.orchestrator.collect_notifications(limit=limit):
            self.wake_notifications.set()
        return _Report(dispatch_deliveries=delivered)

    def sweep(self, *, limit=100):
        return self.pump(limit=limit)


class OrchestratorHost:
    """Own the Orchestrator's runtime and drive it until explicitly stopped.

    When supplied, the synchronous callback receives durable notification
    dictionaries on a separate daemon thread. It never runs on the coordinator
    or worker pool. With no callback, the host still runs execution, flush,
    synchronization, and notification collection, while leaving queued
    notifications durable for an application-managed consumer. Callback
    failures follow the Orchestrator's durable delivery retry policy; they do
    not make application decisions or retry executions.

    ``stop`` stops new delivery claims and drains the runtime, leaving unclaimed
    notifications durable for a subsequent host. Its default deadline is five
    seconds. Python cannot interrupt an arbitrary callback: a deadline expiry
    raises ``TimeoutError`` and the daemon thread may remain alive until the
    callback returns. Keep callback dependencies available until a later stop
    succeeds. The Orchestrator itself remains caller-owned.
    """

    def __init__(self, orchestrator, callback: Callable[[dict], object] | None = None, *,
                 notification_interval: float = 0.05,
                 notification_lease_seconds: float = 30.0,
                 notification_retry_delay: float = 1.0,
                 notification_owner: str | None = None,
                 **runtime_options):
        runtime = getattr(orchestrator, "runtime", None)
        if runtime is None:
            raise ValueError("OrchestratorHost requires an Orchestrator runtime")
        if getattr(runtime, "kernel", None) is not getattr(orchestrator, "kernel", None):
            raise ValueError("runtime and orchestrator must share the Kernel")
        if callback is not None and not callable(callback):
            raise TypeError("callback must be callable or None")
        for name in ("flush", "sync", "collect_notifications", "deliver_notifications"):
            if not callable(getattr(orchestrator, name, None)):
                raise TypeError(f"orchestrator must provide {name}")
        self.notification_interval = RuntimeHost._positive_number(
            notification_interval, "notification_interval")
        self.notification_lease_seconds = RuntimeHost._positive_number(
            notification_lease_seconds, "notification_lease_seconds")
        self.notification_retry_delay = RuntimeHost._positive_number(
            notification_retry_delay, "notification_retry_delay")
        if notification_owner is not None and (
                not isinstance(notification_owner, str) or not notification_owner.strip()):
            raise ValueError("notification_owner must be a nonempty string")
        self.notification_owner = notification_owner or f"orchestrator-host-{uuid4().hex}"
        self.orchestrator = orchestrator
        self.callback = callback
        self.runtime = runtime
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread = None
        self._started = False
        self._deliveries = 0
        self._error_count = 0
        self._last_error = None
        self._stop_started_at = None
        self._stop_finished_at = None
        self._stop_timeout = None
        self._stop_status = "not_started"
        self._notification_phase = {
            "status": "not_started",
            "started_at": None,
            "finished_at": None,
            "error_type": None,
            "error_message": None,
        }
        self.runtime_host = RuntimeHost(
            runtime, _Transport(orchestrator, self._wake_event), **runtime_options)

    def start(self):
        with self._lock:
            if self._stop_event.is_set():
                raise RuntimeError("cannot restart a stopped OrchestratorHost")
            if self._started:
                return self
            self.runtime_host.start()
            try:
                if self.callback is not None:
                    thread = threading.Thread(target=self._deliver, daemon=True,
                                              name="orchestrator-host-notifications")
                    thread.start()
                    self._thread = thread
                self._started = True
            except BaseException as error:
                self._stop_event.set()
                try:
                    self.runtime_host.stop(timeout=5.0)
                except BaseException as cleanup_error:
                    if hasattr(error, "add_note"):
                        error.add_note(f"Runtime cleanup failed: {cleanup_error}")
                raise
        return self

    def wake(self, run_id: str | None = None) -> bool:
        self._wake_event.set()
        return self.runtime_host.wake(run_id)

    def _deliver(self):
        callback = self.callback
        if callback is None:
            return
        while not self._stop_event.is_set():
            try:
                count = self.orchestrator.deliver_notifications(
                    callback, owner=self.notification_owner,
                    lease_seconds=self.notification_lease_seconds,
                    retry_delay=self.notification_retry_delay, limit=1)
                with self._lock:
                    self._deliveries += count
            except Exception as error:
                with self._lock:
                    self._error_count += 1
                    self._last_error = f"{type(error).__name__}: {error}"
                count = 0
            if not count:
                self._wake_event.wait(self.notification_interval)
                self._wake_event.clear()

    def health(self) -> OrchestratorHostHealth:
        runtime = self.runtime_host.health()
        values = {field.name: getattr(runtime, field.name) for field in fields(runtime)}
        with self._lock:
            alive = self._thread is not None and self._thread.is_alive()
            if alive and values["state"] == "stopped":
                values["state"] = "stopping"
            return OrchestratorHostHealth(
                **values, notification_alive=alive,
                notification_deliveries=self._deliveries,
                notification_error_count=self._error_count,
                last_notification_error=self._last_error)

    @property
    def stop_report(self) -> StopReport | None:
        """Return the latest combined runtime and notification stop snapshot."""

        runtime_report = self.runtime_host.stop_report
        now = time.monotonic()
        with self._lock:
            started_at = self._stop_started_at
            if started_at is None:
                return None
            thread_alive = self._thread is not None and self._thread.is_alive()
            if (
                self._notification_phase["status"] == "in_progress"
                and not thread_alive
            ):
                self._notification_phase["status"] = "completed"
                self._notification_phase["finished_at"] = now
            notification = self._notification_phase_snapshot_locked(now)
            status = self._stop_status
            timeout = self._stop_timeout
            finished_at = self._stop_finished_at
        if runtime_report is None:
            runtime_phases = tuple(
                StopPhase(name, "not_started", None, None, None)
                for name in (
                    "worker_drain", "executor_shutdown", "final_pump", "runtime_close"
                )
            )
            active_workers = self.runtime_host.health().active_workers
            runtime_waitable = False
        else:
            runtime_phases = runtime_report.phases
            active_workers = runtime_report.active_worker_count
            runtime_waitable = runtime_report.can_continue_waiting
        # A timeout describes the last stop call, even if a thread finished
        # between the deadline check and this snapshot. Only a successful retry
        # settles that call-level status. Runtime failures remain visible.
        if status == "completed" and runtime_report is not None and runtime_report.status == "failed":
            status = "failed"
        phases = runtime_phases + (notification,)
        return StopReport(
            scope="orchestrator_host",
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=max(
                0.0, (finished_at if finished_at is not None else now) - started_at
            ),
            timeout_seconds=timeout,
            phases=phases,
            unfinished_phases=tuple(
                phase.name
                for phase in phases
                if phase.status not in {"completed", "skipped"}
            ),
            active_worker_count=active_workers,
            notification_thread_alive=thread_alive,
            pending_delivery_count=None,
            pending_delivery_persisted=None,
            can_continue_waiting=runtime_waitable or thread_alive,
            errors=() if runtime_report is None else runtime_report.errors,
        )

    def _notification_phase_snapshot_locked(self, now: float) -> StopPhase:
        values = self._notification_phase
        started_at = values["started_at"]
        finished_at = values["finished_at"]
        elapsed = None
        if started_at is not None:
            elapsed = max(
                0.0, (finished_at if finished_at is not None else now) - started_at
            )
        return StopPhase(
            name="notification_join",
            status=values["status"],
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=elapsed,
            error_type=values["error_type"],
            error_message=values["error_message"],
        )

    def _begin_stop(self, timeout: float) -> None:
        with self._lock:
            if self._stop_started_at is None:
                self._stop_started_at = time.monotonic()
            self._stop_timeout = timeout
            if self._stop_status not in {"completed", "failed"}:
                self._stop_status = "in_progress"
                self._stop_finished_at = None

    def _start_notification_join(self, thread) -> None:
        with self._lock:
            phase = self._notification_phase
            if thread is None:
                if phase["status"] == "not_started":
                    phase["status"] = "skipped"
                    phase["finished_at"] = time.monotonic()
            elif phase["status"] == "not_started":
                phase["status"] = "in_progress"
                phase["started_at"] = time.monotonic()

    def _finish_notification_join(self) -> None:
        with self._lock:
            phase = self._notification_phase
            if phase["status"] == "in_progress":
                phase["status"] = "completed"
                phase["finished_at"] = time.monotonic()

    def _finish_stop(self, status: str) -> None:
        with self._lock:
            self._stop_status = status
            self._stop_finished_at = (
                time.monotonic() if status in {"completed", "failed"} else None
            )

    def stop(self, timeout: float = 5.0) -> bool:
        if type(timeout) not in {int, float} or timeout < 0 or not float(timeout) < float("inf"):
            raise ValueError("timeout must be a finite non-negative number")
        with self._lock:
            if self._thread is threading.current_thread():
                raise RuntimeError("notification callback cannot join its own host")
        deadline = time.monotonic() + timeout
        self._begin_stop(float(timeout))
        self._stop_event.set()
        self._wake_event.set()
        error = None
        try:
            stopped = self.runtime_host.stop(timeout=max(0.0, deadline - time.monotonic()))
        except BaseException as exc:
            error = exc
            stopped = False
        with self._lock:
            thread = self._thread
        self._start_notification_join(thread)
        if thread is not None:
            thread.join(max(0.0, deadline - time.monotonic()))
            if not thread.is_alive():
                self._finish_notification_join()
        if error is not None:
            self._finish_stop("failed")
            raise error
        if not stopped or (thread is not None and thread.is_alive()):
            self._finish_stop("timed_out")
            report = self.stop_report
            assert report is not None
            raise OrchestratorHostTimeoutError(
                "OrchestratorHost did not stop before the timeout", report
            )
        self._finish_stop("completed")
        return True

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, traceback):
        self.stop()


__all__ = [
    "OrchestratorHost", "OrchestratorHostHealth", "OrchestratorHostTimeoutError",
    "StopPhase", "StopReport",
]
