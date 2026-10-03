"""Managed local execution with durable, replay-safe task submission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import ExitStack
import inspect
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable, Mapping
import uuid

from .durability import Durability
from .execution_kernel import RetryPolicy
from .observability import ObservationOptions, StallPolicy
from .orchestrator import NotificationInbox, Orchestrator, OrchestratorHost
from .orchestrator.contracts import CommandConflict, canonical, digest, identifier
from .storage import inspect_storage
from ._inspection import InspectionBudget, InspectionBudgetExceeded
from .observability.journal import _json_size


_SOURCE = "dispatcher.application.v1"
_TASK = "task"
_STALL_SOURCE = "dispatcher.stalls.v1"
_STALL_PHASES = ("observation", "orchestration", "inbox")


class _StallNotificationReader:
    """Read both stores under one budget without taking a writer's lock."""

    def __init__(self, dispatcher, budget, stack):
        self.budget = budget
        self.maximum_bytes = dispatcher.runtime.observation_options.query_bytes
        connection = sqlite3.connect(dispatcher.path.as_uri()+"?mode=ro", uri=True,
            timeout=budget.sqlite_timeout_seconds)
        stack.callback(connection.close)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        budget.install(connection)
        connection.execute("BEGIN")
        journal = dispatcher.runtime.observation_journal
        self.kind_bytes = max(self.maximum_bytes, 256 * 1024)
        observation = None if journal is None else stack.enter_context(
            journal._read_connection(budget.sqlite_timeout_seconds, budget))[0]
        self.sources = {
            "observation": (observation, "obs_outbox"),
            "orchestration": (connection, "sdk_notifications"),
            "inbox": (connection, "notification_inbox_messages"),
        }
        self.projections = {}
        for phase, (database, table) in self.sources.items():
            if database is None:
                continue
            budget.check()
            fields = database.execute(f'PRAGMA table_info("{table}")').fetchall()
            columns = [row["name"] for row in fields if row["name"] != "settlement"]
            projection = ",".join(
                f'CASE WHEN length(CAST("{name}" AS BLOB))<={self.maximum_bytes} THEN "{name}" ELSE NULL END AS "{name}"'
                if row["type"] == "TEXT" else f'"{name}"'
                for row in fields if (name := row["name"]) in columns)
            oversized = " OR ".join(f'COALESCE(length(CAST("{row["name"]}" AS BLOB))>{self.maximum_bytes},0)'
                for row in fields if row["type"] == "TEXT" and row["name"] in columns)
            self.projections[phase] = projection + f",({oversized}) AS read_truncated"

    def candidates(self, phase, after, limit):
        database, table = self.sources[phase]
        if database is None:
            return []
        self.budget.check()
        source = ",source_id" if phase == "inbox" else ""
        return database.execute(f"SELECT rowid AS cursor,notification_id{source} FROM {table} "
            "WHERE rowid>? ORDER BY rowid LIMIT ?", (after, limit+1)).fetchall()

    def row(self, phase, notification_id):
        database, table = self.sources[phase]
        if database is None:
            return None
        self.budget.check()
        condition = " AND source_id=?" if phase == "inbox" else ""
        parameters = (notification_id, _STALL_SOURCE) if phase == "inbox" else (notification_id,)
        value = database.execute(f"SELECT {self.projections[phase]},"
            f"CASE WHEN length(CAST(payload AS BLOB))<={self.kind_bytes} THEN "
            "CASE WHEN json_valid(payload) THEN json_extract(payload,'$.kind') END END AS notification_kind "
            f"FROM {table} WHERE notification_id=?{condition}", parameters).fetchone()
        if value is None:
            return None
        kind = value["notification_kind"]
        kind_unknown = kind is None and value["read_truncated"] and value["payload"] is None
        if kind != "stalled" and not kind_unknown:
            return None
        record = dict(value)
        record.pop("notification_kind")
        if record.pop("read_truncated"):
            record["truncated"] = True
        if kind_unknown:
            record.update(kind_known=False, unknown_reason="notification_kind_unknown")
        payload = record.get("payload")
        record["payload"] = json.loads(payload) if payload is not None else {
            "kind": "unknown" if kind_unknown else "stalled", "notification_id": notification_id, "truncated": True}
        if phase != "observation":
            record["payload"].setdefault("generation", 0)
        error = record.get("last_error")
        if error is not None:
            record["last_error"] = json.loads(error)
        self.budget.check()
        return record

    def resolve(self, notification_id):
        record, owner, stages = None, None, {}
        for phase in _STALL_PHASES:
            row = self.row(phase, notification_id)
            if row is None:
                continue
            owner = owner or phase
            stages[phase] = {"state": row["state"], "revision": row["revision"]}
            record = {**row, "phase": phase, "stages": dict(stages),
                "received": phase == "inbox", "consumed": phase == "inbox" and row["state"] == "consumed"}
        return owner, record


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

    def observe(self, *, timeout: float = 3) -> dict[str, Any]:
        """Read bounded persisted execution activity without driving the task."""
        started = time.monotonic()
        execution_id = self.dispatcher._observed_execution(self.request_id, timeout)
        return self.dispatcher.runtime.observe(execution_id, timeout=max(0, timeout-(time.monotonic()-started)))

    def events(self, *, after: int = 0, limit: int = 50, timeout: float = 3):
        started = time.monotonic()
        execution_id = self.dispatcher._observed_execution(self.request_id, timeout)
        return self.dispatcher.runtime.observation_events(execution_id,
            after=after, limit=limit, timeout=max(0, timeout-(time.monotonic()-started)))

    def watch_stall(self, policy: StallPolicy):
        snapshot = self.snapshot
        self.dispatcher.orchestrator.flush()
        return self.dispatcher.runtime.watch_stall(snapshot["command"]["execution_id"], policy,
            target={"run_id": _run_id(self.request_id), "task_id": _TASK,
                "generation": snapshot.get("generation", 0), "request_id": self.request_id,
                "task_attempt": snapshot.get("attempt", 0)})

    def stall_windows(self, *, after: str | None = None, limit: int = 50):
        return self.dispatcher.runtime.stall_windows(self.snapshot["command"]["execution_id"],
            after=after, limit=limit)

    def cancel(self, *, reason: str = "task cancelled"):
        execution_id = self.snapshot["command"]["execution_id"]
        current = self.dispatcher.runtime.kernel.get(execution_id)
        return self.dispatcher.runtime.cancel(execution_id, expected_revision=current.revision, reason=reason)

    def cancel_if_stalled(self, notification: dict[str, Any], *, reason: str = "stall disposition"):
        if notification.get("execution_id") != self.snapshot["command"]["execution_id"]:
            raise ValueError("notification belongs to another task execution")
        return self.dispatcher.runtime.cancel_if_stalled(notification, reason=reason)

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
        observation_options: ObservationOptions | None = None,
        child_capacity: int = 1, max_child_depth: int = 1,
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
        self._stall_consumer: threading.Thread | None = None
        self._stall_callback: Callable[[dict[str, Any]], Any] | None = None
        self._state = "open"
        self._owner = "dispatcher-consumer-" + uuid.uuid4().hex
        self._callback = on_result
        self._callback_errors = 0
        self._last_callback_error: str | None = None
        self.orchestrator = Orchestrator.open_sqlite(
            self.path, handlers, isolation_mode=isolation_mode, durability=durability,
            observation_options=observation_options, child_capacity=child_capacity, max_child_depth=max_child_depth)
        self.runtime = self.orchestrator.runtime
        try:
            self.inbox = NotificationInbox(self.path, durability=durability)
            self.host = OrchestratorHost(
                self.orchestrator, self._accept, worker_count=worker_count)
            self.runtime.set_stall_notification_bridge(self.orchestrator.enqueue_stall_notification)
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
            self._start_stall_consumer()
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

    def _observed_execution(self, request_id: str, timeout: float) -> str:
        from ._inspection import InspectionBudget
        budget = InspectionBudget(timeout, None)
        budget.check()
        connection = sqlite3.connect(self.path.as_uri()+"?mode=ro", uri=True,
            timeout=budget.sqlite_timeout_seconds)
        try:
            budget.install(connection)
            row = connection.execute("SELECT execution_id FROM sdk_executions WHERE run_id=? AND task_id=? "
                "ORDER BY generation DESC,attempt DESC LIMIT 1", (_run_id(request_id), _TASK)).fetchone()
            budget.check()
            if row is None:
                raise KeyError(request_id)
            return row[0]
        finally:
            connection.close()

    def _snapshot(self, request_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            run = self.orchestrator.get_run(_run_id(request_id))
            if not isinstance(run["definition"], dict) or run["definition"].get("api") != _SOURCE:
                raise ValueError("Run does not belong to Dispatcher")
            return dict(run["tasks"][_TASK]["attempts"][-1])

    def _accept(self, notification: dict[str, Any]) -> None:
        source = _STALL_SOURCE if notification.get("kind") == "stalled" else _SOURCE
        self.inbox.accept(source, notification, max_attempts=notification.get("max_deliveries", 5))

    def subscribe_stalls(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        """Start one bounded at-least-once consumer for stall episodes only."""
        if not callable(callback) or inspect.iscoroutinefunction(callback):
            raise TypeError("stall callback must be synchronous")
        with self._lock:
            self._ensure_open()
            if self._stall_callback is not None and self._stall_callback is not callback:
                raise RuntimeError("a stall consumer is already registered")
            self._stall_callback = callback
            if self._state == "running":
                self._start_stall_consumer()

    def _start_stall_consumer(self) -> None:
        if self._stall_callback is None or self._stall_consumer is not None:
            return
        self._stall_consumer = threading.Thread(target=self._deliver_stalls,
            name="dispatcher-stall-consumer", daemon=True)
        self._stall_consumer.start()

    def _deliver_stalls(self) -> None:
        while not self._stop.is_set():
            lease = None
            try:
                lease = self.inbox.claim(self._owner+":stalls", source_id=_STALL_SOURCE,
                    lease_seconds=self.callback_lease_seconds)
                if lease is not None:
                    assert self._stall_callback is not None
                    returned = self._stall_callback(lease.payload)
                    if inspect.isawaitable(returned):
                        if inspect.iscoroutine(returned):
                            returned.close()
                        raise TypeError("stall callback must be synchronous")
                    self.inbox.consume(lease)
                    continue
            except Exception as error:
                with self._lock:
                    self._callback_errors += 1
                    self._last_callback_error = f"{type(error).__name__}: {error}"
                if lease is not None:
                    try:
                        self.inbox.fail(lease, error={"type": type(error).__name__, "message": str(error)},
                            retry_delay=self.callback_retry_delay)
                    except Exception:
                        pass
            self._stop.wait(.05)

    def stall_notifications(self, *, state=None, limit: int = 100):
        """Read one bounded page; use stall_notification_page to continue."""
        return self.stall_notification_page(state=state, limit=limit)["notifications"]

    def stall_notification_page(self, *, state=None, after: str | None = None,
                                limit: int = 50, timeout: float = 3):
        """Read latest durable stages using an opaque, read-only continuation.

        Each call inspects at most one configured page from each store. A
        filtered page may be empty while has_more remains true; pass cursor
        as after to continue. Receipt and consumption are distinct facts.
        """
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        if state not in (None, "pending", "awaiting_authority", "delivering", "bridged",
                         "delivered", "processing", "consumed", "dead", "superseded"):
            raise ValueError("invalid stall notification state")
        maximum = min(limit, self.runtime.observation_options.page_events)
        positions = [0, 0, 0]
        if after is not None:
            if type(after) is not str or len(after) > 256:
                raise ValueError("invalid notification cursor")
            try:
                positions = json.loads(after)
            except (ValueError, TypeError) as error:
                raise ValueError("invalid notification cursor") from error
            if (type(positions) is not list or len(positions) != 3
                    or any(type(value) is not int or not 0 <= value <= 2**63-1 for value in positions)):
                raise ValueError("invalid notification cursor")
        budget = InspectionBudget(_seconds(timeout, "timeout"), None)
        report = {"notifications": [], "cursor": after, "has_more": False, "complete": True}
        stopped = False
        used = 384
        try:
            with ExitStack() as stack:
                reader = _StallNotificationReader(self, budget, stack)
                for index, phase in enumerate(_STALL_PHASES):
                    rows = reader.candidates(phase, positions[index], maximum)
                    if len(rows) > maximum:
                        report["has_more"] = True
                    for candidate in rows[:maximum]:
                        budget.check()
                        if len(report["notifications"]) >= maximum:
                            report["has_more"], stopped = True, True
                            break
                        if phase == "inbox" and candidate["source_id"] != _STALL_SOURCE:
                            positions[index] = candidate["cursor"]
                            continue
                        owner, record = reader.resolve(candidate["notification_id"])
                        if record is None or owner != phase or (state is not None and record["state"] != state):
                            positions[index] = candidate["cursor"]
                            continue
                        if record.get("truncated"):
                            report.update(complete=False, truncated=True)
                        if record.get("kind_known") is False:
                            report["unknown_reason"] = record["unknown_reason"]
                        size = _json_size(record, budget, reader.maximum_bytes)
                        if used + size > reader.maximum_bytes:
                            if report["notifications"]:
                                report.update(has_more=True, complete=False, truncated=True)
                                stopped = True
                                break
                            record = {name: record[name] for name in (
                                "notification_id", "state", "revision", "phase", "stages", "received", "consumed")}
                            unknown = report.get("unknown_reason") == "notification_kind_unknown"
                            record["payload"] = {"kind": "unknown" if unknown else "stalled", "truncated": True}
                            if unknown:
                                record.update(kind_known=False, unknown_reason="notification_kind_unknown")
                            size = _json_size(record, budget, reader.maximum_bytes)
                            report.update(complete=False, truncated=True)
                        report["notifications"].append(record)
                        used += size + 1
                        positions[index] = candidate["cursor"]
                    if stopped:
                        break
        except (InspectionBudgetExceeded, sqlite3.Error) as error:
            if isinstance(error, sqlite3.Error) and not budget.interrupted(error):
                raise
            report.update(has_more=True, complete=False, timed_out=True, unknown_reason="query_timeout")
        report["cursor"] = json.dumps(positions, separators=(",", ":"))
        report["notifications"] = tuple(report["notifications"])
        report["elapsed_seconds"] = budget.elapsed_seconds
        return report

    def retry_stall_notification(self, notification_id: str, *, expected_revision: int,
                                 phase: str | None = None):
        """Retry the failed phase, preserving the original notification ID."""
        if phase not in (None, "observation", "orchestration", "inbox"):
            raise ValueError("invalid notification phase")
        identifier(notification_id, "notification_id")
        budget = InspectionBudget(self.runtime.observation_options.query_timeout, None)
        with ExitStack() as stack:
            _, record = _StallNotificationReader(self, budget, stack).resolve(notification_id)
        if record is None:
            raise KeyError(notification_id)
        current_phase = record["phase"]
        if phase is not None and phase != current_phase:
            raise ValueError("notification has advanced to another delivery phase")
        phase = current_phase
        if phase == "inbox":
            return self.inbox.retry_dead(_STALL_SOURCE, notification_id, expected_revision=expected_revision)
        if phase == "orchestration":
            return self.orchestrator.retry_notification(notification_id, expected_revision=expected_revision)
        return self.runtime.retry_stall_notification(notification_id, expected_revision=expected_revision)

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
                "stall_consumer_alive": self._stall_consumer is not None and self._stall_consumer.is_alive(),
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
        if threading.current_thread() in (self._consumer, self._stall_consumer):
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
            if self._stall_consumer is not None:
                self._stall_consumer.join(max(0, deadline-time.monotonic()))
                if self._stall_consumer.is_alive():
                    raise TimeoutError("stall callback is still running; retry close after it returns")
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
