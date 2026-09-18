"""Managed local execution with durable, replay-safe task submission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable, Mapping
import uuid

from .durability import Durability
from .execution_kernel import RetryPolicy
from .orchestrator import NotificationInbox, Orchestrator, OrchestratorHost
from .orchestrator.contracts import CommandConflict, canonical, digest, identifier
from .storage import inspect_storage


_SOURCE = "dispatcher.application.v1"
_TASK = "task"


class SubmissionConflictError(ValueError):
    """A stable request ID was reused with different submission content."""


class DeploymentMismatchError(RuntimeError):
    """Startup preflight failed; ``report`` contains structured storage issues."""

    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__(f"storage/deployment preflight failed: {report['issues']}; "
                         f"stopped_reason={report.get('stopped_reason')}")


class RecoveryRequiredError(RuntimeError):
    """Execution is parked pending external evidence, rather than finished."""

    def __init__(self, request_id: str, snapshot: dict[str, Any]):
        self.request_id = request_id
        self.snapshot = snapshot
        super().__init__(f"task {request_id!r} requires external-effect recovery")


def _seconds(value: float, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


def _run_id(request_id: str) -> str:
    identifier(request_id, "request_id")
    return "dispatcher-task-v1:" + digest(request_id)


@dataclass(frozen=True)
class Task:
    """A durable task reference; reconstruct it with Dispatcher.task(request_id)."""

    dispatcher: Dispatcher
    request_id: str

    @property
    def snapshot(self) -> dict[str, Any]:
        return self.dispatcher._snapshot(self.request_id)

    @property
    def state(self) -> str:
        return self.snapshot["state"]

    def wait(self, *, timeout: float = 30) -> dict[str, Any]:
        """Wait for the result without consuming notifications or retrying work.

        The returned Kernel result includes ``status``, ``value`` and ``error``.
        A timeout only ends this wait; it does not cancel execution.
        """
        deadline = time.monotonic() + _seconds(timeout, "timeout")
        while True:
            snapshot = self.snapshot
            if snapshot["state"] == "recovery_required":
                raise RecoveryRequiredError(self.request_id, snapshot)
            if snapshot["result"] is not None:
                return snapshot["result"]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"task {self.request_id!r} has not completed")
            time.sleep(min(0.02, remaining))


class Dispatcher:
    """Own execution, orchestration and a durable notification inbox in one file.

    Construction opens storage but does not start workers. ``with`` or ``start``
    starts them. ``on_result`` is a synchronous at-least-once callback and must
    deduplicate external effects with the stable notification ID. For atomic
    application SQL and receipt settlement, use ``consume_results`` instead.
    Advanced workflows can use ``orchestrator`` and ``runtime`` explicitly.
    """

    def __init__(
        self, path: str | Path, handlers: Mapping[Any, Any], *,
        on_result: Callable[[dict[str, Any]], Any] | None = None,
        isolation_mode: str = "process", worker_count: int = 1,
        durability: Durability = "full", shutdown_timeout: float = 5,
        callback_retry_delay: float = 1, callback_lease_seconds: float = 30,
        preflight_timeout: float = 30,
    ) -> None:
        if str(path) == ":memory:":
            raise ValueError("Dispatcher requires a durable SQLite file")
        if on_result is not None and not callable(on_result):
            raise TypeError("on_result must be callable or None")
        if on_result is not None and inspect.iscoroutinefunction(on_result):
            raise TypeError("on_result must be synchronous")
        if type(worker_count) is not int or worker_count < 1:
            raise ValueError("worker_count must be a positive integer")
        self.shutdown_timeout = _seconds(shutdown_timeout, "shutdown_timeout")
        self.callback_retry_delay = _seconds(callback_retry_delay, "callback_retry_delay")
        self.callback_lease_seconds = _seconds(callback_lease_seconds, "callback_lease_seconds")
        self.path = Path(path).resolve()
        self.preflight = inspect_storage(
            self.path, handlers=handlers, check="bindings",
            timeout_seconds=_seconds(preflight_timeout, "preflight_timeout"))
        if (self.preflight["issues"] or not self.preflight["complete"]
                or self.preflight["checks"]["bindings"] not in {"checked", "not_applicable"}):
            raise DeploymentMismatchError(self.preflight)
        self._lock = threading.RLock()
        self._consumption_condition = threading.Condition(self._lock)
        self._active_consumers = 0
        self._close_lock = threading.Lock()
        self._stop = threading.Event()
        self._consumer: threading.Thread | None = None
        self._state = "open"
        self._owner = "dispatcher-consumer-" + uuid.uuid4().hex
        self._callback = on_result
        self._callback_errors = 0
        self._last_callback_error: str | None = None
        self.orchestrator = Orchestrator.open_sqlite(
            self.path, handlers, isolation_mode=isolation_mode, durability=durability)
        self.runtime = self.orchestrator.runtime
        try:
            self.inbox = NotificationInbox(self.path, durability=durability)
            self.host = OrchestratorHost(
                self.orchestrator, self._accept, worker_count=worker_count)
        except BaseException:
            self.orchestrator.close()
            raise

    def _ensure_open(self) -> None:
        if self._state not in {"open", "running"}:
            raise RuntimeError(f"Dispatcher is {self._state}")

    def start(self) -> Dispatcher:
        with self._lock:
            self._ensure_open()
            if self._state == "running":
                return self
            self.host.start()
            self._state = "running"
            if self._callback is not None:
                self._consumer = threading.Thread(
                    target=self._deliver, name="dispatcher-result-consumer", daemon=True)
                try:
                    self._consumer.start()
                except BaseException:
                    self._consumer = None
                    self._state = "stopping"
                    self._stop.set()
                    self.host.stop(timeout=self.shutdown_timeout)
                    raise
            return self

    def submit(
        self, handler_id: str, payload: Any, *, request_id: str,
        timeout_seconds: float = 30, handler_contract_version: int = 1,
        retry_policy: RetryPolicy | None = None, target: Any = None,
    ) -> Task:
        """Durably submit one standalone task, or replay an identical request.

        The request ID must come from the application's durable input. Generating
        a new ID after response loss submits new work. Retry policy defaults to
        one execution attempt. No business acceptance is inferred from success.
        """
        run_id = _run_id(request_id)
        policy = RetryPolicy() if retry_policy is None else retry_policy
        if type(policy) is not RetryPolicy:
            raise TypeError("retry_policy must be RetryPolicy")
        timeout = _seconds(timeout_seconds, "timeout_seconds")
        definition = {
            "api": _SOURCE, "request_id": request_id, "handler_id": handler_id,
            "handler_contract_version": handler_contract_version,
            "payload": payload, "timeout_seconds": timeout,
            "retry_policy": policy.to_dict(), "target": target,
        }
        # Validate JSON before storing any part of this request.
        canonical(definition)
        with self._lock:
            self._ensure_open()
            if self.orchestrator.get_command_receipt(run_id, "create") is None:
                self.runtime.command(
                    handler_id, execution_id="validate", idempotency_key="validate",
                    correlation_id=run_id,
                    payload=payload, timeout_seconds=timeout,
                    handler_contract_version=handler_contract_version, retry_policy=policy)
            try:
                self.orchestrator.create_run(run_id, command_id="create", definition=definition)
                self.orchestrator.submit_task(
                    run_id, _TASK, request_id=request_id, expected_revision=0,
                    handler_id=handler_id, handler_contract_version=handler_contract_version,
                    payload=payload, timeout_seconds=timeout, retry_policy=policy,
                    watch_target={"request_id": request_id} if target is None else target)
            except CommandConflict as error:
                raise SubmissionConflictError(str(error)) from error
            self.host.wake(run_id)
        return Task(self, request_id)

    def task(self, request_id: str) -> Task:
        """Recover a submitted task handle without submitting or executing it."""
        self._snapshot(request_id)
        return Task(self, request_id)

    def _snapshot(self, request_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            run = self.orchestrator.get_run(_run_id(request_id))
            if not isinstance(run["definition"], dict) or run["definition"].get("api") != _SOURCE:
                raise ValueError("Run does not belong to Dispatcher")
            return dict(run["tasks"][_TASK]["attempts"][-1])

    def _accept(self, notification: dict[str, Any]) -> None:
        self.inbox.accept(_SOURCE, notification)

    def consume_results(
        self, mutation: Callable[[sqlite3.Connection, Any], Any], *, limit: int = 100,
    ) -> int:
        """Apply synchronous local SQL and settle each inbox message atomically.

        The mutation receives (connection, notification). It must not perform
        external effects or control transactions. Exceptions roll back SQL and
        ACK, schedule a bounded retry, then propagate to the caller.
        """
        if not callable(mutation):
            raise TypeError("mutation must be callable")
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._lock:
            self._ensure_open()
            if self._callback is not None:
                raise RuntimeError("choose on_result or transactional consumption")
            self._active_consumers += 1
        try:
            return self._consume_results(mutation, limit)
        finally:
            with self._consumption_condition:
                self._active_consumers -= 1
                self._consumption_condition.notify_all()

    def _consume_results(self, mutation, limit: int) -> int:
        count = 0
        for _ in range(limit):
            if self._stop.is_set():
                break
            lease = self.inbox.claim(
                self._owner, source_id=_SOURCE, lease_seconds=self.callback_lease_seconds)
            if lease is None:
                break
            try:
                self.inbox.consume(lease, mutation)
            except Exception as error:
                try:
                    self.inbox.fail(lease, error={"type": type(error).__name__, "message": str(error)},
                                    retry_delay=self.callback_retry_delay)
                except Exception as settlement_error:
                    # Expired leases are reclaimed by the next claim. Preserve
                    # the mutation error even when this lease cannot settle.
                    if hasattr(error, "add_note"):
                        error.add_note(f"Inbox settlement also failed: {settlement_error}")
                raise
            count += 1
        return count

    def _deliver(self) -> None:
        while not self._stop.is_set():
            lease = None
            try:
                lease = self.inbox.claim(
                    self._owner, source_id=_SOURCE, lease_seconds=self.callback_lease_seconds)
                if lease is not None:
                    assert self._callback is not None
                    returned = self._callback(lease.payload)
                    if inspect.isawaitable(returned):
                        if inspect.iscoroutine(returned):
                            returned.close()
                        raise TypeError("on_result must be synchronous")
                    self.inbox.consume(lease)
                    continue
            except Exception as error:
                with self._lock:
                    self._callback_errors += 1
                    self._last_callback_error = f"{type(error).__name__}: {error}"
                if lease is not None:
                    try:
                        self.inbox.fail(
                            lease, error={"type": type(error).__name__, "message": str(error)},
                            retry_delay=self.callback_retry_delay)
                    except Exception as settlement_error:
                        with self._lock:
                            self._last_callback_error += f"; settlement: {settlement_error}"
            self._stop.wait(0.05)

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state, "host": asdict(self.host.health()),
                "consumer_alive": self._consumer is not None and self._consumer.is_alive(),
                "callback_errors": self._callback_errors,
                "active_consumers": self._active_consumers,
                "last_callback_error": self._last_callback_error,
            }

    def diagnostics(self, *, timeout_seconds: float = 5) -> dict[str, Any]:
        from .diagnostics import inspect_diagnostics

        return inspect_diagnostics(self.path, timeout_seconds=timeout_seconds)

    def close(self, *, timeout: float | None = None) -> None:
        """Stop owned execution and callbacks; retry after a timeout to finish."""
        duration = self.shutdown_timeout if timeout is None else _seconds(timeout, "timeout")
        if threading.current_thread() is self._consumer:
            raise RuntimeError("close Dispatcher from its owner, not its result callback")
        deadline = time.monotonic() + duration
        if not self._close_lock.acquire(timeout=duration):
            raise TimeoutError("another Dispatcher close is still running")
        try:
            with self._lock:
                if self._state == "closed":
                    return
                self._state = "stopping"
                self._stop.set()
            if self._consumer is not None:
                self._consumer.join(max(0, deadline - time.monotonic()))
                if self._consumer.is_alive():
                    raise TimeoutError("result callback is still running; retry close after it returns")
            with self._consumption_condition:
                while self._active_consumers:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("transactional result consumer is still running; retry close")
                    self._consumption_condition.wait(remaining)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Dispatcher shutdown deadline expired; retry close")
            self.host.stop(timeout=remaining)
            self.orchestrator.close()
            self.inbox.close()
            with self._lock:
                self._state = "closed"
        finally:
            self._close_lock.release()

    def __enter__(self) -> Dispatcher:
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.close()
