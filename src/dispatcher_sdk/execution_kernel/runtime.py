"""Local runtime with fenced effects and process timeout isolation.

On POSIX, trusted handlers run behind an independently timed supervisor which
terminates and reaps their process tree on timeout, cancellation, or close.
Windows uses suspended process creation into a kill-on-close Job Object and a
host watchdog thread. Platforms without either backend use a revocable thread.
In thread mode, calls that
begin after timeout and all later durable effect commits are rejected. Python
cannot kill an arbitrary call already executing in a thread, so an external
operation already inside ``perform`` may finish after timeout. Its durable
``performing`` claim is converted to indeterminate and the execution is parked
before any result can become terminal. The timed-out thread can never publish a
Kernel result or commit an effect after authority is revoked.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
import multiprocessing
import os
import threading
import time
from typing import Any, Mapping, Optional
from types import MappingProxyType
import uuid
from dataclasses import asdict, replace
import tempfile
import sqlite3
import json
from pathlib import Path

from ..observability import ActivityRecorder, ObservationIdentity, ObservationJournal, ObservationOptions
from ..observability import StallPolicy
from ..observability.supervision import StallSupervisor
from .budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from .children import ChildService

from ..durability import Durability, validate_durability
from .._sqlite_errors import is_sqlite_contention

from .context import HandlerContext, HandlerEffects
from .contracts import (
    ContractValidationError,
    ExecutionCommandV2,
    ExecutionError,
    ExecutionLease,
    ExecutionResultV2,
)
from .errors import (
    EffectRecoveryRequiredError,
    HandlerContractMismatchError,
    HandlerExecutionError,
    HandlerUnavailableError,
    RegistryRevisionMismatchError,
    ExecutionNotFoundError,
    StaleFenceError,
    InvalidStateTransitionError,
    ResultConflictError,
)
from ._registry import Handler, handler_revision, normalize_handlers, registry_revision
from ._process_runtime import (
    ProcessSupervisorHandle,
    invoke_handler,
    invoke_process_handler,
    _capture_completion_time,
    _confirm_handler_entry,
    _control_error_details,
)
from .sqlite import SQLiteKernel
from .sandbox import SandboxHandler, SandboxJournal
from .sandbox_contracts import SandboxOutcomeUnknown
from ._sandbox_registry import register_journals, journal_paths
from .cancellation import CancellationJournal
from .settlement import SettlementJournal, merge_diagnostic_notes
from .pending_settlements import PendingSettlements, SettlementAdmission


class _ProcessRegistration(threading.Event):
    """Completion alone is not a cleanup proof when invocation raises."""

    cleanup_confirmed = False


class _UnpersistedSettlementsError(RuntimeError):
    """Local cleanup finished, but original result retention is unresolved."""


class _ObservationCleanupPendingError(RuntimeError):
    """Stopped SDK storage workers have not yet released runtime storage."""


class InProcessRuntime:
    """A local coordinator whose handlers are bound to exact historical keys."""

    def __init__(
        self,
        db_path: str,
        handlers: Mapping[Any, Handler],
        *,
        worker_id: str = "local-runtime",
        lease_seconds: float = 30.0,
        now: Any = None,
        isolation_mode: str = "auto",
        outbox_max_attempts: int = 8,
        max_thread_workers: int = 4,
        durability: Durability = "full",
        cancellation_journal_path: str | None = None,
        source_id: str | None = None,
        observation_path: str | None = None,
        observation_options: ObservationOptions | None = None,
        child_capacity: int = 1,
        max_child_depth: int = 1,
    ) -> None:
        if (cancellation_journal_path is None) != (source_id is None):
            raise ValueError("cancellation_journal_path and source_id must be provided together")
        self.durability = validate_durability(durability)
        self.handlers = normalize_handlers(handlers)
        self.registry_revision = registry_revision(self.handlers)
        self.handler_revisions = MappingProxyType({
            key: handler_revision(self.handlers, *key) for key in self.handlers
        })
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self._now = now
        fork_available = os.name == "posix" and "fork" in multiprocessing.get_all_start_methods()
        process_available = fork_available or os.name == "nt"
        if isolation_mode == "auto":
            isolation_mode = "process" if process_available else "thread"
        if isolation_mode == "process" and not process_available:
            raise ValueError("process isolation requires POSIX fork or native Windows support")
        if isolation_mode not in {"process", "thread"}:
            raise ValueError("isolation_mode must be auto, process, or thread")
        if isolation_mode != "process" and any(
            getattr(handler, "requires_process_isolation", False)
            for handler in self.handlers.values()
        ):
            raise ValueError("registered handler requires process isolation")
        for handler in self.handlers.values():
            if isinstance(handler, SandboxHandler) and handler.durability != self.durability:
                raise ValueError("sandbox handler and Runtime must use the same durability profile")
        if isolation_mode == "process" and str(db_path) == ":memory:":
            raise ValueError("process isolation requires a file-backed SQLite path; :memory: is not supported")
        if type(max_thread_workers) is not int or max_thread_workers < 1:
            raise ValueError("max_thread_workers must be a positive integer")
        for name, value in (("child_capacity", child_capacity), ("max_child_depth", max_child_depth)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        self.isolation_mode = isolation_mode
        self._lifecycle_lock = threading.RLock()
        # Completion bookkeeping must not wait behind cancellation or result
        # admission. Close still waits for this independently guarded count.
        self._lifecycle_condition = threading.Condition()
        self._close_complete = threading.Event()
        self._close_retry_lock = threading.Lock()
        self._close_error: BaseException | None = None
        self._stop_event = threading.Event()
        self._active_runs = 0
        self._process_supervisors: dict[tuple[str, int, int], Any] = {}
        self._execution_recorders: dict[tuple[str, int, int], ActivityRecorder] = {}
        self._retired_recorders: list[ActivityRecorder] = []
        self._retired_observation_contexts: list[HandlerContext] = []
        self._observation_cleanup_report: list[dict[str, Any]] = []
        self._observation_cleanup_pending = False
        # Exists from the moment a claimed execution enters process
        # invocation until its supervisor has been reaped.  Cancellation
        # waits on this marker so a start/register race cannot report success
        # while a process tree is still becoming visible to the runtime.
        self._process_registration_events: dict[tuple[str, int, int], _ProcessRegistration] = {}
        self._revoked_executions: dict[tuple[str, int, int], str] = {}
        self._thread_lock = threading.RLock()
        self._closed = False
        self._thread_executor: Optional[ThreadPoolExecutor] = None
        self._thread_slots: Optional[threading.BoundedSemaphore] = None
        self._thread_authorities: set[threading.Event] = set()
        self._thread_authority_by_execution: dict[tuple[str, int, int], threading.Event] = {}
        self._thread_slot_by_authority: dict[threading.Event, threading.BoundedSemaphore] = {}
        self._thread_contexts: dict[tuple[str, int, int], HandlerContext] = {}
        self._child_thread_executor: ThreadPoolExecutor | None = None
        self._child_thread_slots = threading.BoundedSemaphore(child_capacity)
        self._child_capacity, self._max_child_depth = child_capacity, max_child_depth
        self._services_started = False
        self._temporary_observation: Any = None
        self.observation_options = observation_options or ObservationOptions()
        self.observation_journal: ObservationJournal | None = None
        self._child_service: ChildService | None = None
        self._stall_supervisor: StallSupervisor | None = None
        self._notification_bridge: Any = None
        self._observation_error: str | None = None
        self._settlement_journal: SettlementJournal | None = None
        self._settlement_error: str | None = None
        self._diagnostic_errors: dict[str, str] = {}
        self._settlement_thread: threading.Thread | None = None
        self._settlement_lock = threading.Lock()
        self._settlement_inflight_lock = threading.Lock()
        self._settlement_inflight: set[tuple[str, int, int]] = set()
        self._pending_settlements = PendingSettlements()
        if isolation_mode == "thread":
            self._thread_executor = ThreadPoolExecutor(
                max_workers=max_thread_workers,
                thread_name_prefix="execution-kernel",
            )
            self._thread_slots = threading.BoundedSemaphore(max_thread_workers)
        self.kernel = SQLiteKernel(
            db_path,
            durability=self.durability,
            now=now,
            default_lease_seconds=lease_seconds,
            outbox_max_attempts=outbox_max_attempts,
        )
        try:
            self.cancellation_journal: CancellationJournal | None = None
            if cancellation_journal_path is not None:
                assert source_id is not None
                self.cancellation_journal = CancellationJournal(
                    cancellation_journal_path, source_id=source_id, kernel_path=self.kernel.db_path,
                    durability=self.durability)
            sandbox_bindings = [handler for handler in self.handlers.values() if isinstance(handler, SandboxHandler)]
            self._sandbox_store_id = register_journals(self.kernel.db_path, [],
                durability=self.durability, initialize_only=True)
            registered_paths = journal_paths(self.kernel.db_path)
            for handler in sandbox_bindings:
                if handler.journal_path in registered_paths:
                    # Verify existing registration before a journal constructor
                    # could initialize a replaced or empty file.
                    register_journals(self.kernel.db_path, [handler.journal_path], durability=self.durability)
                handler.journal()._bind_store(self._sandbox_store_id)
            if sandbox_bindings:
                register_journals(self.kernel.db_path, [h.journal_path for h in sandbox_bindings], durability=self.durability)
            if self.kernel.db_path == ":memory:" and observation_path is None:
                self._temporary_observation = tempfile.TemporaryDirectory(prefix="sdk-observation-")
                observation_path = os.path.join(self._temporary_observation.name, "observations.sqlite3")
            self._observation_source_id = self._sandbox_store_id or uuid.uuid4().hex
            self._observation_path = observation_path or self.kernel.db_path + ".observations.sqlite3"
            try:
                settlement_path = (os.path.join(self._temporary_observation.name, "settlements.sqlite3")
                    if self.kernel.db_path == ":memory:" and self._temporary_observation is not None
                    else self.kernel.db_path + ".settlements.sqlite3")
                self._settlement_journal = SettlementJournal(settlement_path,
                    source_id=self._observation_source_id, kernel_path=self.kernel.db_path)
            except Exception as exc:
                self._settlement_error = f"{type(exc).__name__}: {exc}"
            try:
                self.observation_journal = ObservationJournal(self._observation_path,
                    kernel_path=self.kernel.db_path, source_id=self._observation_source_id,
                    options=self.observation_options, clock=self.kernel._wall_time)
                self._child_service = ChildService(self, self.observation_journal,
                    capacity=child_capacity, max_depth=max_child_depth)
                self._stall_supervisor = StallSupervisor(self.observation_journal, self.kernel)
            except Exception as exc:
                self._observation_error = f"{type(exc).__name__}: {exc}"
        except BaseException:
            self.kernel.close()
            raise

    def close(self) -> None:
        with self._lifecycle_lock:
            if self._closed:
                close_complete = self._close_complete
                first_closer = False
            else:
                self._closed = True
                self._stop_event.set()
                close_complete = self._close_complete
                first_closer = True
        if not first_closer:
            close_complete.wait()
            with self._close_retry_lock:
                self._retry_close_cleanup()
            return
        try:
            self.request_stop()
            if self._stall_supervisor is not None:
                self._stall_supervisor.close(timeout=1.0)
            if self._child_service is not None:
                self._child_service.close(timeout_seconds=5.0)
            if self._settlement_thread is not None:
                self._settlement_thread.join(timeout=1.0)
            with self._lifecycle_condition:
                while self._active_runs:
                    self._lifecycle_condition.wait()
            observation_pending = self._drain_observation_workers(time.monotonic() + 1.0)
            try:
                self._persist_pending_settlements(time.monotonic() + 1, limit=64)
                unresolved = self.recover_sandboxes(all_pages=True)
                if any(not item["cleanup_confirmed"] for item in unresolved):
                    raise SandboxOutcomeUnknown("remote cleanup remains pending in the sandbox journal")
                if self._pending_settlements.identities():
                    raise _UnpersistedSettlementsError("runtime closed with original outcomes not yet durably persisted")
                if observation_pending:
                    raise _ObservationCleanupPendingError("runtime storage cleanup remains pending")
            finally:
                self.kernel.close()
                if self._temporary_observation is not None and not observation_pending:
                    self._temporary_observation.cleanup()
        except BaseException as exc:
            self._close_error = exc
            raise
        finally:
            self._close_complete.set()

    def _retry_close_cleanup(self) -> None:
        observation_pending = False
        if (self._retired_recorders or self._retired_observation_contexts or self._observation_cleanup_pending
                or isinstance(self._close_error, _ObservationCleanupPendingError)):
            observation_pending = self._drain_observation_workers(time.monotonic() + 1.0)
            if not observation_pending:
                if isinstance(self._close_error, _ObservationCleanupPendingError):
                    self._close_error = None
                if self._temporary_observation is not None:
                    self._temporary_observation.cleanup()
        if isinstance(self._close_error, _UnpersistedSettlementsError):
            self._persist_pending_settlements(time.monotonic() + 1, limit=64)
            if not self._pending_settlements.identities():
                self._close_error = None
        # Resolving the original settlement obligation does not release a
        # still-running collector's storage ownership.
        if observation_pending and self._close_error is None:
            self._close_error = _ObservationCleanupPendingError("runtime storage cleanup remains pending")
        if self._close_error is not None:
            raise self._close_error

    def _retain_observation_workers(self, recorder: ActivityRecorder) -> None:
        with self._lifecycle_condition:
            self._retired_recorders = [item for item in self._retired_recorders if item._owned_workers_alive()]
            if recorder._owned_workers_alive() and recorder not in self._retired_recorders:
                self._retired_recorders.append(recorder)

    @staticmethod
    def _context_observation_pending(context: HandlerContext) -> bool:
        return (not context._observation_start_done.is_set()
                or (isinstance(context.activity, ActivityRecorder) and context.activity._owned_workers_alive()))

    def _retain_observation_context(self, context: HandlerContext) -> None:
        with self._lifecycle_condition:
            self._retired_observation_contexts = [item for item in self._retired_observation_contexts
                if self._context_observation_pending(item)]
            if self._context_observation_pending(context) and context not in self._retired_observation_contexts:
                self._retired_observation_contexts.append(context)

    def _drain_observation_workers(self, deadline: float) -> bool:
        with self._lifecycle_condition:
            recorders = tuple(self._retired_recorders)
            contexts = tuple(self._retired_observation_contexts)
        reports = [recorder._join_owned_workers(deadline) for recorder in recorders]
        for context in contexts:
            context._observation_start_done.wait(max(0.0, deadline - time.monotonic()))
            report = {"kind": "handler_observation_start", "execution_id": context.lease.execution_id,
                      "initialization_pending": not context._observation_start_done.is_set()}
            if isinstance(context.activity, ActivityRecorder):
                report["recorder"] = context.activity._join_owned_workers(deadline)
            report["state"] = "pending" if self._context_observation_pending(context) else "closed"
            reports.append(report)
        # These SDK threads can own journal connections. User delivery
        # callbacks are not storage ownership and are never joined here.
        sampler = None if self._stall_supervisor is None else self._stall_supervisor._sampler
        service_workers = (("stall_sampler", sampler), ("settlement", self._settlement_thread))
        for name, worker in service_workers:
            if worker is not None and worker is not threading.current_thread():
                worker.join(max(0.0, deadline - time.monotonic()))
            reports.append({"kind": "sdk_storage_service", "service": name,
                "state": "pending" if worker is not None and worker.is_alive() else "closed"})
        with self._lifecycle_condition:
            self._retired_recorders = [recorder for recorder in self._retired_recorders if recorder._owned_workers_alive()]
            self._retired_observation_contexts = [context for context in self._retired_observation_contexts
                if self._context_observation_pending(context)]
            self._observation_cleanup_report = reports
            self._observation_cleanup_pending = (bool(self._retired_recorders or self._retired_observation_contexts)
                or any(worker is not None and worker.is_alive() for _, worker in service_workers))
            return self._observation_cleanup_pending

    def request_stop(self) -> None:
        """Revoke active handler authority without closing durable storage."""

        with self._lifecycle_lock:
            self._stop_event.set()
            supervisors = tuple(self._process_supervisors.values())
            for execution_id in self._process_registration_events:
                self._revoked_executions.setdefault(
                    execution_id, "runtime_closed"
                )
            with self._thread_lock:
                for authority in self._thread_authorities:
                    authority.clear()
                executor = self._thread_executor
                child_executor = self._child_thread_executor
                contexts = tuple(self._thread_contexts.values())
        for supervisor in supervisors:
            supervisor.revoke("runtime_closed")
        if executor is not None:
            # Running Python threads cannot be killed. Their Kernel authority
            # is revoked and the run_once wrapper is woken promptly.
            executor.shutdown(wait=False, cancel_futures=True)
        if child_executor is not None:
            child_executor.shutdown(wait=False, cancel_futures=True)
        for context in contexts:
            try:
                context.close()
            finally:
                self._retain_observation_context(context)
                if isinstance(context.activity, ActivityRecorder):
                    self._retain_observation_workers(context.activity)

    def _start_services(self) -> None:
        with self._lifecycle_lock:
            if self._services_started or self._closed:
                return
            if self.isolation_mode == "thread":
                self._child_thread_executor = ThreadPoolExecutor(max_workers=self._child_capacity,
                    thread_name_prefix="execution-kernel-child")
            if self._child_service is not None:
                self._child_service.start()
            if self._stall_supervisor is not None:
                self._stall_supervisor.start()
            if self._settlement_journal is not None:
                self._settlement_thread = threading.Thread(target=self._settlement_loop,
                    name="execution-kernel-settlement", daemon=True)
                self._settlement_thread.start()
            self._services_started = True

    def _settlement_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.recover_completions(timeout_seconds=.25)
            except Exception as exc:
                self._settlement_error = f"{type(exc).__name__}: {exc}"
            self._stop_event.wait(.25)

    def _persist_pending_settlements(self, deadline: float, *, limit: int = 50) -> list[dict[str, Any]]:
        """Transfer original local facts to the journal, without running work."""
        reports: list[dict[str, Any]] = []
        if self._settlement_journal is None:
            return reports
        for entry in self._pending_settlements.entries(limit):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                payload = entry.payload
                original = payload if set(payload) == {"kind", "outcome"} else ExecutionResultV2.from_dict(payload)
                self._settlement_journal.record(entry.lease, original, evidence=entry.evidence,
                    timeout_seconds=min(.1, remaining))
                self._pending_settlements.persisted(entry.key, expected=entry)
                reports.append({**entry.identity, "state": "persisted"})
            except Exception as exc:
                self._settlement_error = f"{type(exc).__name__}: {exc}"
                reports.append({**entry.identity, "state": "unpersisted", "error": self._settlement_error})
                break
        return reports

    def recover_completions(self, *, limit: int = 50,
                            timeout_seconds: float = .5) -> tuple[dict[str, Any], ...]:
        """Retry retained result CAS operations, without invoking any handler."""
        duration = self.kernel._positive_duration(timeout_seconds, "timeout_seconds")
        if self._settlement_journal is None:
            return ({"state": "unknown", "error": self._settlement_error},)
        deadline = time.monotonic() + duration
        if not self._settlement_lock.acquire(timeout=min(.1, duration)):
            return ({"state": "pending", "error": "completion recovery busy"},)
        reports = []
        try:
            reports.extend(self._persist_pending_settlements(deadline, limit=limit))
            if time.monotonic() >= deadline:
                return tuple(reports)
            records = self._settlement_journal.pending(limit=limit,
                timeout_seconds=min(.1, max(.001, deadline-time.monotonic())))
            for record in records:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._closed:
                    break
                identity = record["identity"]
                key = (identity["execution_id"], identity["attempt"], identity["fence"])
                with self._settlement_inflight_lock:
                    if key in self._settlement_inflight:
                        continue
                try:
                    lease = ExecutionLease.from_dict(record["lease"])
                    with self._bounded_lifecycle(min(.1, remaining)):
                        operation_timeout = min(.1, max(.001, deadline-time.monotonic()))
                        if record["deferred"] is not None:
                            original = record["deferred"]
                            with self.kernel._control_lock(operation_timeout):
                                completed = self.kernel.get(lease.execution_id)
                            if (completed.attempt, completed.fence) != (lease.attempt, lease.fence):
                                raise StaleFenceError("deferred recovery belongs to an old attempt")
                            if original["kind"] == "completion_time_unknown":
                                # A later clock read cannot establish the
                                # original return time. Retain the outcome,
                                # without granting pre-expiry settlement.
                                if completed.state != "running":
                                    self._settlement_journal.settle(record, "superseded",
                                        {**record["evidence"], "execution_state": completed.state,
                                         "error": "original completion time remains unknown"}, timeout_seconds=.1)
                                    reports.append({**identity, "state": "superseded"})
                                else:
                                    self._settlement_journal.settle(record, "error",
                                        {**record["evidence"], "error": "original completion time remains unknown"}, timeout_seconds=.1)
                                    reports.append({**identity, "state": "unknown"})
                                continue
                            if original["kind"] != "recovery_required":
                                raise ValueError("unknown deferred completion kind")
                            if completed.state != "recovery_required":
                                completed = self.kernel._require_effect_recovery(lease,
                                    original["outcome"]["effect_id"], timeout_seconds=operation_timeout,
                                    settlement=True)
                            result = None
                        else:
                            result = ExecutionResultV2.from_dict(record["result"])
                            retained_budget = record["evidence"].get("budget_envelope")
                            completed = self.kernel._complete_sdk_result(lease, result,
                                budget_envelope=(None if retained_budget is None else
                                    BudgetEnvelope.from_dict(retained_budget)),
                                timeout_seconds=operation_timeout, settlement=True)
                    state = "recovery_required" if completed.state == "recovery_required" else "recorded"
                    evidence = {**record["evidence"], "execution_state": completed.state,
                        "execution_revision": completed.revision}
                    if result is not None:
                        evidence["result_id"] = result.result_id
                    self._settlement_journal.settle(record, state, evidence, timeout_seconds=.1)
                    reports.append({**identity, "state": state, **evidence})
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    if self._storage_contention(exc) or isinstance(exc, TimeoutError):
                        reports.append({**identity, "state": "pending", "error": error})
                        break
                    state = "superseded" if isinstance(exc, (StaleFenceError,
                        InvalidStateTransitionError, ResultConflictError)) else "error"
                    self._settlement_journal.settle(record, state,
                        {**record["evidence"], "error": error}, timeout_seconds=.1)
                    reports.append({**identity, "state": state, "error": error})
            return tuple(reports)
        finally:
            self._settlement_lock.release()

    def _diagnostic_note(self, identity, phase: str, evidence: dict[str, Any]) -> None:
        """Retain diagnostics even when the activity writer is unavailable."""
        execution_id = (identity.execution_id if hasattr(identity, "execution_id")
                        else identity["execution_id"])
        try:
            if self._settlement_journal is None:
                raise RuntimeError(self._settlement_error or "diagnostic journal unavailable")
            key = {"execution_id": execution_id, "attempt": identity.attempt,
                   "fence": identity.fence} if hasattr(identity, "attempt") else identity
            self._settlement_journal.note(key, phase, evidence, timeout_seconds=.1)
        except Exception as exc:
            self._diagnostic_errors[execution_id] = f"{type(exc).__name__}: {exc}"

    def _service_spec(self, lease: ExecutionLease) -> dict[str, Any]:
        if self.observation_journal is None:
            return {"entry_protocol": True}
        spec = {"journal_path": self._observation_path, "kernel_path": self.kernel.db_path,
            "entry_protocol": True,
            "source_id": self._observation_source_id,
            "options": asdict(self.observation_options), "capacity": self._child_capacity,
            "max_depth": self._max_child_depth, "registry_revision": self.registry_revision,
            "bindings": dict(self.handler_revisions)}
        with self.kernel._lock:
            row = self.kernel._connection.execute(
                "SELECT run_id,generation FROM kernel_managed_executions WHERE execution_id=?",
                (lease.execution_id,)).fetchone()
        if row is not None:
            spec.update(run_id=row[0], generation=row[1])
        try:
            connection = sqlite3.connect(Path(self.kernel.db_path).resolve().as_uri()+"?mode=ro",
                uri=True, timeout=self.observation_options.write_timeout)
            try:
                task = connection.execute("SELECT run_id,task_id,generation,attempt FROM sdk_executions "
                    "WHERE execution_id=?", (lease.execution_id,)).fetchone()
                if task is not None:
                    spec.update(run_id=task[0], task_id=task[1], generation=task[2], task_attempt=task[3])
            finally:
                connection.close()
        except sqlite3.Error:
            pass
        return spec

    def _observation_identity(self, lease: ExecutionLease) -> ObservationIdentity:
        spec = self._service_spec(lease)
        return ObservationIdentity(lease.execution_id, lease.attempt, lease.fence,
            run_id=spec.get("run_id"), task_id=spec.get("task_id"), generation=spec.get("generation", 0),
            task_attempt=spec.get("task_attempt"))

    def _begin_activity(self, lease: ExecutionLease) -> None:
        if self.observation_journal is None:
            return
        try:
            identity = self._observation_identity(lease)
            recorder = ActivityRecorder(self.observation_journal, identity, options=self.observation_options,
                source_scope="driver", metric_coverage=("phase_events", "heartbeat"),
                clock=self.kernel._wall_time, start=True, bind_current=True)
            self._execution_recorders[(lease.execution_id, lease.attempt, lease.fence)] = recorder
            recorder.phase("worker_dispatch")
            recorder.heartbeat()
            recorder.observe_process(multiprocessing.current_process(), role="driver", process_id="driver")
        except Exception as exc:
            self._observation_error = f"{type(exc).__name__}: {exc}"

    def _activity_phase(self, lease: ExecutionLease, phase: str, **details: Any) -> None:
        recorder = self._execution_recorders.get((lease.execution_id, lease.attempt, lease.fence))
        if recorder is not None:
            recorder.phase(phase, details=details)

    def set_stall_notification_bridge(self, bridge) -> None:
        if bridge is not None and not callable(bridge):
            raise TypeError("bridge must be callable")
        self._notification_bridge = bridge
        if self._stall_supervisor is not None:
            self._stall_supervisor.notification_bridge = bridge
            if self._services_started:
                self._stall_supervisor.start()

    @property
    def observation_storage(self) -> dict[str, Any]:
        """Public binding for a separate read-only inspection process."""
        return {"path": self._observation_path, "kernel_path": self.kernel.db_path,
            "source_id": self._observation_source_id, "available": self.observation_journal is not None,
            "unknown_reason": self._observation_error}

    def watch_stall(self, execution_id: str, policy: StallPolicy, *, target: dict[str, Any] | None = None):
        if self._stall_supervisor is None:
            raise RuntimeError("durable observation storage is unavailable")
        snapshot = self.kernel.get(execution_id)
        metadata = target or {}
        identity = ObservationIdentity(execution_id, snapshot.attempt, snapshot.fence,
            run_id=metadata.get("run_id"), task_id=metadata.get("task_id"),
            generation=metadata.get("generation", 0), task_attempt=metadata.get("task_attempt"))
        result = self._stall_supervisor.watch(identity, policy, target=metadata)
        self._start_services()
        return result

    def cancel_if_stalled(self, notification: dict[str, Any], *, reason: str = "stall disposition"):
        if notification.get("kind") != "stalled" or type(notification.get("disposition")) is not dict:
            raise ValueError("expected an SDK stall notification with disposition authority")
        token = notification["disposition"]
        current = self.kernel.supervision_status(token["execution_id"])
        return self.cancel(token["execution_id"], expected_revision=current["execution_revision"],
            reason=reason, expected_supervision=token)

    def stall_notifications(self, *, limit: int = 50):
        """Read durable notifications before their orchestration handoff."""
        if self._stall_supervisor is None:
            return ()
        return self._stall_supervisor.outbox(limit=limit)

    def retry_stall_notification(self, notification_id: str, *, expected_revision: int):
        if self._stall_supervisor is None:
            raise RuntimeError("durable observation storage is unavailable")
        receipt = self._stall_supervisor.retry_dead(notification_id, expected_revision=expected_revision)
        self._start_services()
        return receipt

    def stall_windows(self, execution_id: str, *, after: str | None = None, limit: int = 50):
        if self._stall_supervisor is None:
            return {"windows": [], "complete": False, "unknown_reason": "observation_unavailable"}
        return self._stall_supervisor.windows(execution_id, after=after, limit=limit)

    def submit_child(self, command: ExecutionCommandV2, *, parent_lease: ExecutionLease,
                     budget_envelope: BudgetEnvelope, timeout_seconds: float | None = None):
        if timeout_seconds is not None:
            timeout_seconds = self.kernel._positive_duration(timeout_seconds, "timeout_seconds")
        self._assert_registry_current()
        if not self._binding_matches(command):
            raise RegistryRevisionMismatchError("child handler binding differs from runtime")
        started = time.monotonic()
        admission = (self._lifecycle_lock if timeout_seconds is None else
            self._bounded_lifecycle(timeout_seconds, message="child lifecycle admission timed out"))
        with admission:
            if self._closed:
                raise RuntimeError("runtime is closed")
            remaining = None if timeout_seconds is None else timeout_seconds - (time.monotonic() - started)
            if remaining is not None and remaining <= 0:
                raise TimeoutError("child lifecycle admission timed out")
            return self.kernel.submit_child(command, parent_lease, budget_envelope,
                                            timeout_seconds=remaining)

    def adopt_child(self, execution_id: str, *, parent_lease: ExecutionLease,
                    budget_envelope: BudgetEnvelope, timeout_seconds: float | None = None):
        if timeout_seconds is not None:
            timeout_seconds = self.kernel._positive_duration(timeout_seconds, "timeout_seconds")
        self._assert_registry_current()
        started = time.monotonic()
        admission = (self._lifecycle_lock if timeout_seconds is None else
            self._bounded_lifecycle(timeout_seconds, message="child lifecycle admission timed out"))
        with admission:
            if self._closed:
                raise RuntimeError("runtime is closed")
            remaining = None if timeout_seconds is None else timeout_seconds - (time.monotonic() - started)
            if remaining is not None and remaining <= 0:
                raise TimeoutError("child lifecycle admission timed out")
            with self.kernel._control_lock(remaining):
                target = self.kernel.get(execution_id)
                if not self._binding_matches(target.command):
                    raise RegistryRevisionMismatchError("adopted child handler binding differs from runtime")
                return self.kernel.adopt_child(execution_id, parent_lease, budget_envelope,
                                              timeout_seconds=remaining)

    def observe(self, execution_id: str, *, timeout: float | None = None,
                attempt: int | None = None, fence: int | None = None) -> dict[str, Any]:
        """Query a bounded persisted view without driving or reaping execution."""
        if self.observation_journal is None:
            return {"execution_id": execution_id, "view": "persisted", "complete": False,
                "unknown_reason": "observation_unavailable", "error": self._observation_error}
        duration = self.observation_options.query_timeout if timeout is None else timeout
        from .._inspection import InspectionBudget
        budget = InspectionBudget(duration, None)
        report = {"execution_id": execution_id, "view": "persisted", "complete": False,
            "current": False, "unknown_reason": "observation_query_unavailable"}
        connection = None
        reader = None
        try:
            budget.check()
            reader = ObservationJournal.open_readonly(self._observation_path,
                kernel_path=self.kernel.db_path, source_id=self._observation_source_id,
                options=replace(self.observation_options, query_timeout=max(.001, duration-budget.elapsed_seconds)),
                clock=self.kernel._wall_time)
            budget.check()
            report = reader.inspect(execution_id, timeout=max(.001, duration-budget.elapsed_seconds), attempt=attempt, fence=fence)
            budget.check()
            connection = sqlite3.connect(Path(self.kernel.db_path).resolve().as_uri()+"?mode=ro", uri=True,
                timeout=budget.sqlite_timeout_seconds)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            budget.install(connection)
            connection.execute("BEGIN")
            row = connection.execute("SELECT state,attempt,fence,revision,started_at,"
                "CASE WHEN length(CAST(result_json AS BLOB))<=? THEN result_json END AS result_json,"
                "length(CAST(result_json AS BLOB)) AS result_bytes FROM kernel_executions "
                "WHERE execution_id=?", (self.observation_options.query_bytes // 2, execution_id)).fetchone()
            if row is None:
                raise ExecutionNotFoundError(execution_id)
            report["execution"] = {name: row[name] for name in ("state", "attempt", "fence", "revision")}
            report["execution"]["kernel_started_at"] = row["started_at"]
            report["settlement"] = {"result_recorded": row["result_bytes"] is not None,
                "consumer_ack": "unknown"}
            if row["result_json"] is not None:
                result = json.loads(row["result_json"])
                report["result"] = {name: result[name] for name in
                    ("result_id", "status", "attempt", "fence", "started_at", "completed_at", "error")}
            elif row["result_bytes"] is not None:
                report.update(complete=False, unknown_reason="result_query_byte_limit")
            delivery = connection.execute("SELECT result_id,state,attempts,max_attempts,revision,updated_at "
                "FROM kernel_result_outbox WHERE execution_id=?", (execution_id,)).fetchone()
            report["settlement"]["kernel_result_delivery"] = None if delivery is None else dict(delivery)
            limits = connection.execute("SELECT envelope_json,entry_state FROM kernel_execution_limits WHERE execution_id=?",
                (execution_id,)).fetchone()
            if limits is not None:
                if len(limits[0].encode("utf-8")) > self.observation_options.query_bytes // 2:
                    report.update(complete=False, unknown_reason="budget_query_byte_limit")
                else:
                    report["budget"] = BudgetEnvelope.from_dict(json.loads(limits[0])).view(
                        sample=sample_clock(wall_time=self.kernel._wall_time())).to_dict()
                    report["budget"]["entry_state"] = limits[1]
                    if limits[1] == "pending":
                        report["budget"].update(clock_status="unknown", unknown_reason="entry_confirmation_pending",
                            remaining_work_seconds=None, remaining_hard_seconds=None)
            supervision = connection.execute("SELECT * FROM kernel_supervision WHERE execution_id=?",
                (execution_id,)).fetchone()
            report["supervision"] = None if supervision is None else dict(supervision)
            identity = report.get("identity")
            if identity is not None and (identity["attempt"], identity["fence"]) != (row["attempt"], row["fence"]):
                report["current"] = False
            budget.check()
        except Exception as exc:
            report.update(complete=False, unknown_reason="control_observation_unavailable",
                error=f"{type(exc).__name__}: {exc}")
        finally:
            if connection is not None:
                connection.close()
        if self._settlement_journal is not None:
            try:
                budget.check()
                report["settlement_obligations"] = self._settlement_journal.inspect(execution_id,
                    timeout_seconds=min(.1, max(.001, duration-budget.elapsed_seconds)),
                    max_bytes=min(256 * 1024, max(1024, self.observation_options.query_bytes // 2)))
                if any(item.get("truncated") or item.get("more") or item.get("unknown_reason")
                       for item in report["settlement_obligations"]):
                    report.update(complete=False, unknown_reason="settlement_query_incomplete")
                budget.check()
                notes = self._settlement_journal.inspect_notes(execution_id,
                    timeout_seconds=min(.1, max(.001, duration-budget.elapsed_seconds)),
                    max_bytes=min(256 * 1024, max(1024, self.observation_options.query_bytes // 2)))
                merge_diagnostic_notes(report, notes, process_freshness=self.observation_options.process_freshness)
                budget.check()
            except Exception as exc:
                report.update(complete=False,
                    settlement_obligations_error=f"{type(exc).__name__}: {exc}")
        elif self._settlement_error is not None:
            report.update(complete=False, settlement_obligations_error=self._settlement_error)
        if execution_id in self._diagnostic_errors:
            report.update(complete=False, diagnostic_receipt_error=self._diagnostic_errors[execution_id])
        local_obligations = tuple(identity for identity in self._pending_settlements.identities()
                                  if identity["execution_id"] == execution_id)
        if local_obligations:
            report.update(complete=False, local_settlement_obligations=local_obligations,
                unknown_reason="original_result_not_durably_persisted")
        if report.get("collection_gaps", 0) > 0:
            report.update(complete=False, unknown_reason="telemetry_collection_incomplete")
        return report if reader is None else reader._bound_report(report, budget=budget)

    def observation_events(self, execution_id: str, *, after: int = 0,
                           limit: int | None = None, timeout: float | None = None):
        if self.observation_journal is None:
            return {"events": [], "complete": False, "unknown_reason": "observation_unavailable"}
        from .._inspection import InspectionBudget
        duration = self.observation_options.query_timeout if timeout is None else timeout
        budget = InspectionBudget(duration, None)
        try:
            budget.check()
            reader = ObservationJournal.open_readonly(self._observation_path,
                kernel_path=self.kernel.db_path, source_id=self._observation_source_id,
                options=replace(self.observation_options, query_timeout=max(.001, duration-budget.elapsed_seconds)),
                clock=self.kernel._wall_time)
            budget.check()
            return reader.events(execution_id, after=after, limit=limit,
                timeout=max(.001, duration-budget.elapsed_seconds))
        except Exception as exc:
            return {"events": [], "cursor": after, "complete": False,
                "unknown_reason": "observation_query_unavailable", "error": f"{type(exc).__name__}: {exc}"}

    def __enter__(self) -> "InProcessRuntime":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def submit(self, command: ExecutionCommandV2):
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("runtime is closed")
        self._assert_registry_current()
        if not self._binding_matches(command):
            raise RegistryRevisionMismatchError(
                f"command requires registry revision {command.registry_revision}; "
                f"runtime provides {self.registry_revision}"
            )
        return self.kernel.submit(command)

    def submit_managed(
        self, command: ExecutionCommandV2, *, run_id: str, generation: int
    ):
        """Submit a Run-associated execution after validating its handler binding."""

        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("runtime is closed")
        self._assert_registry_current()
        if not self._binding_matches(command):
            raise RegistryRevisionMismatchError(
                f"command requires registry revision {command.registry_revision}; "
                f"runtime provides {self.registry_revision}"
            )
        return self.kernel.submit_managed(
            command, run_id=run_id, generation=generation
        )

    def command(self, handler_id: str, *, execution_id: str,
                idempotency_key: str, correlation_id: str, timeout_seconds: float,
                payload: Any, handler_contract_version: int = 1,
                causation_id: str | None = None, retry_policy: Any = None) -> ExecutionCommandV2:
        """Freeze a command against just its handler's current implementation."""
        from .contracts import RetryPolicy

        self._assert_registry_current()
        binding = handler_revision(self.handlers, handler_id, handler_contract_version)
        return ExecutionCommandV2(
            execution_id=execution_id, idempotency_key=idempotency_key,
            correlation_id=correlation_id, causation_id=causation_id,
            handler_id=handler_id, handler_contract_version=handler_contract_version,
            registry_revision=binding, timeout_seconds=timeout_seconds,
            payload=payload, retry_policy=RetryPolicy(max_attempts=1) if retry_policy is None else retry_policy,
        )

    def _binding_matches(self, command: ExecutionCommandV2) -> bool:
        return command.registry_revision == self.registry_revision or (
            command.registry_revision == self.handler_revisions.get(
                (command.handler_id, command.handler_contract_version)))

    def cancel(
        self,
        execution_id: str,
        *,
        expected_revision: int,
        reason: str = "execution cancelled",
        expected_supervision: dict[str, Any] | None = None,
        timeout_seconds: float = 1,
    ):
        """Externally cancel one execution with revision-CAS authority.

        An explicitly configured cancellation journal preserves stage evidence
        across restart. Evidence failures after the Kernel commit do not skip
        process cleanup and are surfaced after cleanup is attempted.
        """

        registration: Optional[threading.Event] = None
        recovery_error: EffectRecoveryRequiredError | None = None
        receipt_id = None
        evidence_errors: list[Exception] = []
        duration = self.kernel._positive_duration(timeout_seconds, "timeout_seconds")
        control_deadline = time.monotonic() + duration
        if type(expected_supervision) is dict:
            expected_supervision = dict(expected_supervision)
        cancellation_identity: ObservationIdentity | None = None
        observation_available = True
        requested_at = self.kernel._wall_time()
        pending_evidence: list[tuple[str, dict[str, Any], float]] = []

        def remaining_control():
            remaining = control_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Kernel control admission budget elapsed")
            return remaining

        def control_admission_error(error):
            if isinstance(error, sqlite3.OperationalError):
                code = getattr(error, "sqlite_errorcode", None)
                if type(code) is int:
                    return code & 255 in (getattr(sqlite3, "SQLITE_BUSY", 5),
                                          getattr(sqlite3, "SQLITE_LOCKED", 6))
                return code is None and str(error) in (
                    "database is locked", "database table is locked", "database schema is locked")
            return isinstance(error, TimeoutError) and str(error) in (
                "Kernel control lock admission timed out", "Kernel control admission budget elapsed")

        def bounded_control(operation):
            last_admission_error = None
            while True:
                try:
                    attempt_timeout = min(.1, remaining_control())
                except TimeoutError:
                    if last_admission_error is not None:
                        raise last_admission_error
                    raise
                entered = returned = retry_uncommitted = False
                operation_error = None
                try:
                    with self.kernel._control_lock(attempt_timeout):
                        entered = True
                        connection = self.kernel._connection
                        was_in_transaction = connection.in_transaction
                        changes_before = connection.total_changes
                        try:
                            answer = operation(min(.1, remaining_control()))
                        except Exception as error:
                            operation_error = error
                            # Both snapshots are taken under this same lock.
                            # Any write, even a rolled-back clock advance,
                            # makes replay too uncertain to authorize here.
                            retry_uncommitted = (not was_in_transaction and not connection.in_transaction
                                and connection.total_changes == changes_before)
                            raise
                        returned = True
                    return answer
                except Exception as error:
                    if not control_admission_error(error) or returned:
                        raise
                    if entered:
                        if error is not operation_error or not retry_uncommitted:
                            raise
                    elif not (isinstance(error, TimeoutError) and str(error) in (
                            "Kernel control lock admission timed out", "Kernel control admission budget elapsed")):
                        raise
                    last_admission_error = error
                    remaining = control_deadline - time.monotonic()
                    if remaining <= 0:
                        raise
                    time.sleep(min(.01, remaining))

        def record(stage, evidence, captured_at=None):
            nonlocal observation_available
            if cancellation_identity is not None:
                self._diagnostic_note(cancellation_identity, "cancellation_"+stage,
                    evidence if captured_at is None else {**evidence, "captured_at": captured_at})
            if observation_available and self.observation_journal is not None and cancellation_identity is not None:
                try:
                    self.observation_journal.phase(cancellation_identity, "cancellation_"+stage,
                        captured_at=captured_at, details=evidence)
                except Exception as exc:
                    observation_available = False
                    self._observation_error = f"{type(exc).__name__}: {exc}"
            if receipt_id is not None and stage != "requested":
                try:
                    legacy_evidence = ({name: evidence[name] for name in ("phase", "type")}
                        if stage == "failure" else evidence)
                    self.cancellation_journal._record(receipt_id, stage, legacy_evidence, timeout_seconds=min(duration, .1))
                except Exception as exc:
                    evidence_errors.append(exc)

        with self._bounded_lifecycle(remaining_control()):
            if self._closed:
                raise RuntimeError("runtime is closed")
            before = bounded_control(lambda timeout: self.kernel.get(execution_id))
            cancellation_identity = ObservationIdentity(execution_id, before.attempt, before.fence)
            pending_evidence.append(("requested", {"state": "requested",
                "expected_revision": expected_revision, "reason": reason}, requested_at))
            if self.cancellation_journal is not None:
                try:
                    receipt_id = self.cancellation_journal._begin(
                        before, expected_revision=expected_revision, reason=reason,
                        isolation_mode=self.isolation_mode, timeout_seconds=min(.1, remaining_control()))
                except Exception as exc:
                    evidence_errors.append(exc)
            try:
                cancelled = bounded_control(lambda timeout: self.kernel.cancel(
                    execution_id,
                    expected_revision=expected_revision,
                    reason=reason,
                    expected_supervision=expected_supervision,
                    timeout_seconds=timeout,
                ))
            except EffectRecoveryRequiredError as exc:
                # The durable state is now recovery_required, but cancellation
                # authority still requires the running process tree to stop
                # before the Bridge may acknowledge the intent.
                cancelled = None
                recovery_error = exc
            except BaseException as exc:
                for stage, evidence, captured_at in pending_evidence:
                    record(stage, evidence, captured_at)
                pending_evidence.clear()
                record("failure", {"phase": "kernel_cancel", "type": type(exc).__name__, "message": str(exc)})
                raise
            authority = cancelled if cancelled is not None else self.kernel.get(execution_id)
            pending_evidence.append(("authority_revoked", {"state": "confirmed",
                "execution_revision": authority.revision, "execution_state": authority.state,
                "attempt": before.attempt, "fence": before.fence}, self.kernel._wall_time()))
            generation = (execution_id, before.attempt, before.fence)
            registration = self._process_registration_events.get(generation)
            if registration is not None:
                self._revoked_executions[generation] = "execution_cancelled"
            supervisor = self._process_supervisors.get(generation)
            with self._thread_lock:
                thread_authority = self._thread_authority_by_execution.get(generation)
        phase = "process_cleanup"
        try:
            try:
                if supervisor is not None and not supervisor.revoke("execution_cancelled"):
                    raise RuntimeError(
                        f"process supervisor for {execution_id} did not terminate"
                    )
                if registration is not None and not registration.wait(self._handler_start_timeout()):
                    raise RuntimeError(
                        f"process registration for {execution_id} did not settle after cancellation"
                    )
                if thread_authority is not None:
                    thread_authority.clear()
            finally:
                # Neither independent telemetry nor its writer admission may
                # postpone local revocation. Preserve the original phase times.
                for stage, evidence, captured_at in pending_evidence:
                    record(stage, evidence, captured_at)
                pending_evidence.clear()
            if thread_authority is not None:
                local_state, local_code = "not_applicable", "thread_authority_is_not_thread_termination"
            elif getattr(registration, "cleanup_confirmed", False):
                local_state, local_code = "confirmed", "runtime_supervisor_reaped"
            elif before.attempt == 0:
                local_state, local_code = "not_applicable", "execution_never_claimed"
            else:
                local_state, local_code = "unknown", "no_local_supervisor_evidence"
            record(phase, {"state": local_state, "code": local_code})
            phase = "remote_cleanup"
            unresolved = self.recover_sandboxes(all_pages=True, execution_id=execution_id,
                                               max_fence=before.fence)
            failed = any(not item["cleanup_confirmed"] for item in unresolved)
            record(phase, {"state": "pending" if failed else "confirmed" if unresolved else "unknown",
                           "code": "sandbox_cleanup_checked", "reports": list(unresolved)})
            if failed:
                raise SandboxOutcomeUnknown("cancellation has not confirmed remote sandbox disposal")
        except BaseException as exc:
            record("failure", {"phase": phase, "type": type(exc).__name__, "message": str(exc)})
            raise
        if evidence_errors:
            record("failure", {"phase": "evidence_write", "type": type(evidence_errors[0]).__name__,
                "message": str(evidence_errors[0])})
            raise RuntimeError("cancellation changed authority but its durable evidence could not be saved") from evidence_errors[0]
        if recovery_error is not None:
            raise recovery_error
        assert cancelled is not None
        return cancelled

    @contextmanager
    def _bounded_lifecycle(self, timeout_seconds: float, *, message: str = "execution control is busy; cancellation was not submitted"):
        if not self._lifecycle_lock.acquire(timeout=timeout_seconds):
            raise TimeoutError(message)
        try:
            yield
        finally:
            self._lifecycle_lock.release()

    def events_since(self, after_sequence: int, limit: int = 100):
        return self.kernel.events_since(after_sequence, limit)

    def pending_recoveries(self, *, limit: int = 100):
        return self.kernel.pending_recoveries(limit=limit)

    def reap(self):
        """Reap expired execution leases through the durable Kernel API."""

        self.recover_completions()
        with self._lifecycle_lock:
            if self._closed:
                return []
            result = self.kernel.reap()
        self.recover_sandboxes()
        return result

    def recover_sandboxes(self, *, limit: int = 100, after_execution_id: str = "",
                          all_pages: bool = False, execution_id: str | None = None,
                          max_fence: int | None = None) -> tuple[dict[str, Any], ...]:
        """Retry disposal for inactive executions; never replay an uncertain launch.

        Effects still need an explicit application recovery decision. The journal
        retains collected results even when the Kernel effect commit was lost.
        """
        reports = []
        for path in journal_paths(self.kernel.db_path):
            from pathlib import Path
            if not Path(path).is_file():
                reports.append({"execution_id": execution_id, "journal_path": path,
                                "cleanup_confirmed": False, "error": "sandbox_journal_missing"})
                continue
            try:
                # Never initialize an empty or replaced registered journal.
                import sqlite3
                check = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
                try:
                    bound = check.execute("SELECT store_id FROM sandbox_meta").fetchone()[0]
                    if bound != self._sandbox_store_id:
                        raise ValueError("sandbox journal store binding differs")
                finally:
                    check.close()
                journal = SandboxJournal(path, durability=self.durability)
            except Exception as exc:
                reports.append({"execution_id": execution_id, "journal_path": path,
                                "cleanup_confirmed": False, "error": type(exc).__name__})
                continue
            cursor = after_execution_id
            while True:
                if execution_id is None:
                    records = journal.pending(after_execution_id=cursor, limit=limit)
                else:
                    record = journal.get(execution_id)
                    records = (record,) if record is not None and not record["cleanup_confirmed"] else ()
                for record in records:
                    confirmed, error = False, None
                    try:
                        snapshot = self.kernel.get(record["execution_id"])
                        if snapshot.state in {"leased", "running"}:
                            continue
                        handler = self.handlers.get((record["handler_id"], record["handler_contract_version"]))
                        if not isinstance(handler, SandboxHandler) or handler.journal_path != path:
                            error = "sandbox_handler_unavailable"
                        elif (snapshot.command.handler_id, snapshot.command.handler_contract_version) != (
                                record["handler_id"], record["handler_contract_version"]):
                            error = "sandbox_execution_binding_mismatch"
                        elif (handler.backend.name, handler.backend.revision) != (
                                record["backend_name"], record["backend_revision"]):
                            error = "sandbox_backend_revision_unavailable"
                        else:
                            confirmed = handler.cleanup(record["execution_id"],
                                operation_key=record["operation_key"], max_fence=max_fence)
                    except Exception as exc:
                        error = type(exc).__name__
                    reports.append({"execution_id": record["execution_id"],
                                    "cleanup_confirmed": confirmed, "error": error})
                if execution_id is not None or not all_pages or len(records) < limit:
                    break
                cursor = records[-1]["execution_id"]
        return tuple(reports)

    def _assert_registry_current(self) -> None:
        current = registry_revision(self.handlers)
        if current != self.registry_revision:
            raise RegistryRevisionMismatchError(
                "handler implementation state changed after registry binding"
            )

    def _begin_process_execution(self, lease: ExecutionLease) -> None:
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("runtime is closed")
            self._process_registration_events[(lease.execution_id, lease.attempt, lease.fence)] = _ProcessRegistration()

    def _finish_process_execution(self, lease: ExecutionLease) -> None:
        with self._lifecycle_lock:
            generation = (lease.execution_id, lease.attempt, lease.fence)
            registration = self._process_registration_events.pop(generation, None)
            self._revoked_executions.pop(generation, None)
            if registration is not None:
                registration.set()

    def _acquire_thread_slot(self, *, child: bool = False) -> bool:
        if self.isolation_mode != "thread":
            return True
        with self._thread_lock:
            if self._closed or self._thread_slots is None:
                return False
            slots = self._child_thread_slots if child else self._thread_slots
            return slots.acquire(blocking=False)

    def _release_thread_slot(self, *, child: bool = False) -> None:
        if self.isolation_mode != "thread":
            return
        with self._thread_lock:
            if self._thread_slots is not None:
                slots = self._child_thread_slots if child else self._thread_slots
                slots.release()

    def _thread_finished(
        self, authority: threading.Event, generation: tuple[str, int, int]
    ) -> None:
        with self._thread_lock:
            if authority not in self._thread_authorities:
                return
            self._thread_authorities.remove(authority)
            if self._thread_authority_by_execution.get(generation) is authority:
                del self._thread_authority_by_execution[generation]
            slots = self._thread_slot_by_authority.pop(authority, None)
            if slots is not None:
                slots.release()

    def _handler_start_timeout(self) -> float:
        return max(5.0, min(self.lease_seconds, 30.0))

    @staticmethod
    def _storage_contention(error: Exception) -> bool:
        return is_sqlite_contention(error)

    def _prepare_handler_admission(self, lease: ExecutionLease):
        """Retry short control collisions within one original startup window."""
        deadline = time.monotonic() + self._handler_start_timeout()
        inherited = None
        last_error = None
        while not self._stop_event.is_set():
            try:
                if inherited is None:
                    inherited = self.kernel.admission_budget(lease,
                        timeout_seconds=min(.1, max(.001, deadline - time.monotonic())))
                sample = sample_clock(wall_time=self.kernel._wall_time())
                view = inherited.view(sample=sample)
                if view.clock_status != "trusted":
                    raise BudgetClockUnknownError(view.unknown_reason)
                inherited = inherited.recheckpoint(sample=sample)
                bound = inherited.deadline_monotonic(hard=True, sample=sample)
                if bound is not None:
                    deadline = min(deadline, bound)
                if view.remaining_work_seconds is not None and view.remaining_work_seconds <= 0:
                    return None, {"kind": "timeout", "phase": "entry_authority",
                        "limiting_source": view.limiting_source, "effect_ids": [],
                        "budget_envelope": inherited.to_dict(), "details": view.to_dict()}, deadline
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                prepared = self.kernel._prepare_handler_entry(lease,
                    timeout_seconds=min(.1, remaining))
                checkpoint = inherited.recheckpoint(sample=prepared.checkpoint).checkpoint
                prepared = prepared.recheckpoint(sample=checkpoint)
                return prepared, None, deadline
            except Exception as exc:
                last_error = exc
                if not self._storage_contention(exc) and not isinstance(exc, TimeoutError):
                    return None, {"kind": "error", "code": "budget_clock_unknown" if isinstance(
                        exc, BudgetClockUnknownError) else "entry_admission_failed",
                        "message": str(exc), "retryable": False, "control_error": True,
                        "details": {"cause": type(exc).__name__, "phase": "entry_admission"},
                        "effect_ids": []}, deadline
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._stop_event.wait(min(.01, remaining))
        if self._stop_event.is_set():
            return None, {"kind": "authority_revoked", "reason": "runtime_closed", "effect_ids": []}, deadline
        return None, {"kind": "error", "code": "entry_admission_timeout",
            "message": "handler admission exceeded its startup window", "retryable": False,
            "control_error": True, "details": {"phase": "entry_admission",
                "cause": None if last_error is None else type(last_error).__name__,
                "error": None if last_error is None else str(last_error)}, "effect_ids": []}, deadline

    def _handler_or_error(
        self, command: ExecutionCommandV2
    ) -> tuple[Optional[Handler], Optional[ExecutionError]]:
        key = (command.handler_id, command.handler_contract_version)
        if not self._binding_matches(command):
            return None, ExecutionError(
                code="registry_revision_mismatch",
                message="command binding does not match its specific handler",
                retryable=False, details={"handler_id": command.handler_id},
            )
        handler = self.handlers.get(key)
        if handler is not None:
            return handler, None
        same_id = any(handler_id == command.handler_id for handler_id, _ in self.handlers)
        if same_id:
            error = HandlerContractMismatchError(
                f"no exact contract version {command.handler_contract_version} for {command.handler_id}"
            )
            code = "handler_contract_mismatch"
        else:
            error = HandlerUnavailableError(f"no handler registered for {command.handler_id}")
            code = "handler_unavailable"
        return None, ExecutionError(
            code=code,
            message=str(error),
            retryable=False,
            details={
                "handler_id": command.handler_id,
                "handler_contract_version": command.handler_contract_version,
            },
        )

    def _invoke_process(
        self,
        handler: Handler,
        command: ExecutionCommandV2,
        lease: ExecutionLease,
    ) -> dict[str, Any]:
        generation = (lease.execution_id, lease.attempt, lease.fence)
        prepared_budget, preparation_error, startup_deadline = self._prepare_handler_admission(lease)
        if preparation_error is not None:
            return preparation_error
        entry_errors: list[Exception] = []
        entry_ack: dict[str, Any] = {}

        def acknowledge_entry(packet: dict[str, Any]) -> None:
            entry_ack.update(packet)
            self._diagnostic_note(lease, "handler_entered", packet)
            if self.observation_journal is not None:
                try:
                    identity = self._observation_identity(lease)
                    self.observation_journal.register_process(identity, "worker", role="worker",
                        pid=packet.get("worker_pid"), birth_identity=packet.get("birth_identity"),
                        namespace=packet.get("namespace"), source="worker_self_report")
                    self.observation_journal.observe_process(identity, "worker", "alive",
                        evidence=packet.get("process_evidence", {}))
                except Exception as exc:
                    self._observation_error = f"{type(exc).__name__}: {exc}"
            if packet.get("entry_confirmed") is not True:
                try:
                    self.kernel.confirm_handler_entry(lease, BudgetEnvelope.from_dict(packet["budget_envelope"]))
                except Exception as exc:
                    entry_errors.append(exc)

        def register(supervisor: Any) -> bool:
            with self._lifecycle_lock:
                reason = self._revoked_executions.pop(generation, None)
                if reason is None and (
                    self._closed or self._stop_event.is_set()
                ):
                    reason = "runtime_closed"
                if reason is None:
                    self._process_supervisors[generation] = supervisor
                    recorder = self._execution_recorders.get(generation)
                    if recorder is not None:
                        recorder.observe_process(supervisor, role="supervisor", process_id="supervisor")
                        recorder.phase("worker_created")
                    return True
            # The caller that requested cancellation waits for the outer
            # invocation to finish.  Do the kill synchronously here so a
            # process which wins the start/register race cannot run with
            # revoked authority.
            supervisor.revoke(reason)
            return False

        def unregister(supervisor: Any) -> None:
            with self._lifecycle_lock:
                if self._process_supervisors.get(generation) is supervisor:
                    del self._process_supervisors[generation]
                self._revoked_executions.pop(generation, None)

        def cleanup_confirmed() -> None:
            with self._lifecycle_lock:
                registration = self._process_registration_events.get(generation)
                if registration is not None:
                    registration.cleanup_confirmed = True
            self._activity_phase(lease, "process_cleanup", state="confirmed", source="runtime_supervisor_reaped")
            self._diagnostic_note(lease, "process_cleanup", {"state": "confirmed", "source": "runtime_supervisor_reaped"})
            if self.observation_journal is not None and entry_ack:
                try:
                    self.observation_journal.observe_process(self._observation_identity(lease), "worker", "exited",
                        evidence={"source": "runtime_supervisor_reaped", "cleanup": "confirmed"})
                except Exception as exc:
                    self._observation_error = f"{type(exc).__name__}: {exc}"

        invoke = invoke_process_handler
        if os.name == "nt":
            from ._windows_runtime import invoke_windows_handler
            invoke = invoke_windows_handler
        def worker_phase(phase: str, details: dict[str, Any]) -> None:
            self._activity_phase(lease, phase, **details)
            self._diagnostic_note(lease, phase, details)
        outcome = invoke(
            db_path=self.kernel.db_path,
            durability=self.durability,
            handler=handler,
            command=command,
            lease=lease,
            now=self._now,
            start_timeout=max(.001, startup_deadline - time.monotonic()),
            on_started=register,
            on_finished=unregister,
            on_cleanup_confirmed=cleanup_confirmed,
            budget_envelope=prepared_budget,
            service_spec=self._service_spec(lease),
            on_entered=acknowledge_entry,
            on_phase=worker_phase,
        )
        if entry_errors and entry_ack:
            try:
                self.kernel.confirm_handler_entry(lease, BudgetEnvelope.from_dict(entry_ack["budget_envelope"]))
                entry_errors.clear()
            except Exception as exc:
                entry_errors[:] = [exc]
        if entry_errors and outcome.get("kind") == "ok":
            outcome = {**outcome, "kind": "error", "code": "entry_confirmation_unknown",
                "message": "handler entry could not be durably confirmed", "retryable": False,
                "control_error": True, "details": {**_control_error_details(entry_errors[0]),
                    "business_outcome": outcome}}
        if isinstance(handler, SandboxHandler):
            try:
                confirmed = handler.cleanup(command.execution_id, max_fence=lease.fence)
            except Exception:
                confirmed = False
            if not confirmed:
                if outcome.get("kind") in {"recovery_required", "authority_revoked"}:
                    return outcome
                # Disposal can fail after execution was already committed, or
                # after the worker died in the gap before preparing disposal.
                # Park a *disposal* effect, never request recovery of a committed
                # execution effect.
                current = self.kernel.get(command.execution_id)
                if current.state != "running" or current.lease is None or current.lease.fence != lease.fence:
                    return outcome
                record = handler.journal().get(command.execution_id)
                if record is None:
                    raise SandboxOutcomeUnknown("sandbox cleanup failed without a lifecycle record")
                unfinished = self.kernel.effect_ids_for_attempt(
                    command.execution_id, lease.attempt, lease.fence,
                    states={"prepared", "performing", "indeterminate"})
                if unfinished:
                    effect_id = unfinished[0]
                else:
                    effect_id = handler.effect_id(command.execution_id) + ":dispose:" + record["operation_key"]
                    effect = self.kernel.prepare_effect(lease, effect_id=effect_id, name="sandbox.dispose",
                        request={"operation_key": record["operation_key"], "backend_name": handler.backend.name,
                                 "backend_revision": handler.backend.revision})
                    if effect.state == "committed":
                        raise SandboxOutcomeUnknown("committed disposal contradicts the sandbox journal")
                return {"kind": "recovery_required", "effect_id": effect_id, "effect_ids": []}
        return outcome

    def _invoke_thread(
        self,
        handler: Handler,
        command: ExecutionCommandV2,
        lease: ExecutionLease,
        *,
        child: bool = False,
    ) -> dict[str, Any]:
        generation = (lease.execution_id, lease.attempt, lease.fence)
        active = threading.Event()
        active.set()
        effects = HandlerEffects(self.kernel, lease, active.is_set)
        prepared_budget, preparation_error, startup_deadline = self._prepare_handler_admission(lease)
        if preparation_error is not None:
            active.clear()
            self._release_thread_slot(child=child)
            return preparation_error
        context = HandlerContext(command, lease, effects,
            budget_envelope=prepared_budget, service_spec=self._service_spec(lease))
        admission = context.budget
        if admission.remaining_work_seconds is not None and admission.remaining_work_seconds <= 0:
            active.clear()
            # No future will own the slot's usual completion callback.
            self._release_thread_slot(child=child)
            return {"kind": "timeout", "phase": "entry_authority",
                "limiting_source": admission.limiting_source, "effect_ids": [],
                "budget_envelope": context.budget_envelope.to_dict(), "details": admission.to_dict()}
        executor = self._child_thread_executor if child else self._thread_executor
        if executor is None:
            raise RuntimeError("thread isolation executor is not available")
        started = threading.Event()
        entry_confirmed = threading.Event()
        entered: dict[str, Any] = {}

        def on_entered(ctx: HandlerContext) -> None:
            entered["deadline"] = ctx.budget_envelope.deadline_monotonic(sample=ctx._sample())
            entered["started_at"] = ctx.budget_envelope.started_at
            entered["envelope"] = ctx.budget_envelope
            started.set()
            # User code must wait for durable first-entry authority. A revoked
            # worker leaves this wait even if the coordinator cannot ACK it.
            while not entry_confirmed.wait(0.01):
                if not active.is_set() or self._stop_event.is_set():
                    raise RuntimeError("handler entry authority was revoked before confirmation")
                view = ctx.budget
                if view.clock_status == "unknown":
                    raise HandlerExecutionError("budget_clock_unknown",
                        "execution clock continuity cannot be established", details=view.to_dict())
                if (time.monotonic() >= entered["deadline"]
                        or (view.remaining_work_seconds is not None and view.remaining_work_seconds <= 0)):
                    raise HandlerExecutionError("execution_deadline_exhausted",
                        "execution work deadline elapsed before entry confirmation", details=view.to_dict())
            if not active.is_set() or self._stop_event.is_set():
                raise RuntimeError("handler entry authority was revoked before invocation")
            # Entry was accepted at the committed checkpoint. Charge native
            # elapsed time while releasing the gate, without introducing a new
            # unconfirmed wall-clock floor between final ACK and invocation.
            with ctx._budget_lock:
                accepted = ctx.budget_envelope
                sample = sample_clock()
                sample = replace(sample, wall_at=accepted.checkpoint.wall_at)
                view = accepted.view(sample=sample)
            if view.remaining_work_seconds is None or view.remaining_work_seconds <= 0:
                raise HandlerExecutionError("execution_deadline_exhausted",
                    "execution has no trusted remaining work time", details=view.to_dict())

        def invoke_started() -> dict[str, Any]:
            try:
                result = invoke_handler(handler, command, context, on_entered=on_entered)
                _capture_completion_time(result, context)
                completion = {key: result[key] for key in
                    ("completed_at", "completion_time_known", "completion_time_error") if key in result}
                self._thread_finished(active, generation)
                if "started_at" in entered:
                    view = context.budget
                    if view.clock_status == "unknown":
                        result = {"kind": "error", "code": "budget_clock_unknown", "control_error": True,
                            "message": "execution clock continuity cannot be established", "effect_ids": effects.effect_ids,
                            "details": {"business_outcome": result}}
                    elif view.remaining_work_seconds is not None and view.remaining_work_seconds <= 0:
                        result = {"kind": "timeout", "limiting_source": view.limiting_source,
                            "effect_ids": effects.effect_ids, "details": {"business_outcome": result}}
                    result.update(started_at=entered["started_at"], budget_envelope=context.budget_envelope.to_dict())
                result.update(completion)
                return result
            finally:
                started.set()
                self._thread_finished(active, generation)
                try:
                    context.close()
                finally:
                    self._retain_observation_context(context)
                    if isinstance(context.activity, ActivityRecorder):
                        self._retain_observation_workers(context.activity)
                    with self._thread_lock:
                        self._thread_contexts.pop(generation, None)

        with self._thread_lock:
            if self._closed:
                active.clear()
                raise RuntimeError("runtime is closed")
            self._thread_authorities.add(active)
            self._thread_authority_by_execution[generation] = active
            self._thread_slot_by_authority[active] = self._child_thread_slots if child else self._thread_slots
            self._thread_contexts[generation] = context
        try:
            future = executor.submit(invoke_started)
        except BaseException:
            with self._thread_lock:
                self._thread_authorities.discard(active)
                self._thread_slot_by_authority.pop(active, None)
                self._thread_contexts.pop(generation, None)
                if self._thread_authority_by_execution.get(generation) is active:
                    del self._thread_authority_by_execution[generation]
            active.clear()
            raise
        future.add_done_callback(
            lambda _future: self._thread_finished(active, generation)
        )
        try:
            startup = max(0, startup_deadline - time.monotonic())
            inherited = context.budget_envelope.deadline_monotonic(hard=True, sample=context._sample())
            if inherited is not None:
                startup = min(startup, max(0, inherited - time.monotonic()))
            if not started.wait(startup):
                active.clear()
                future.cancel()
                view = context.budget
                if view.remaining_work_seconds is not None and view.remaining_work_seconds <= 0:
                    return {"kind": "timeout", "phase": "entry_authority",
                        "limiting_source": view.limiting_source, "effect_ids": effects.effect_ids,
                        "budget_envelope": context.budget_envelope.to_dict(), "details": view.to_dict()}
                return {
                    "kind": "error",
                    "code": "handler_thread_start_failure",
                    "message": "handler thread did not reach invocation",
                    "retryable": False,
                    "details": {},
                    "effect_ids": effects.effect_ids,
                }
            deadline = entered.get("deadline", time.monotonic())
            if "started_at" in entered:
                try:
                    _confirm_handler_entry(context)
                except Exception as exc:
                    active.clear()
                    future.cancel()
                    typed = isinstance(exc, HandlerExecutionError)
                    code = exc.code if typed else "entry_confirmation_unknown"
                    details = exc.details if typed else _control_error_details(exc)
                    expired = code == "execution_deadline_exhausted"
                    if expired and details.get("limiting_source") == "execution":
                        code = "handler_timeout"
                    return {"kind": "timeout" if expired else "error",
                        "code": code, "message": str(exc) if typed else details["error"],
                        "retryable": False, "control_error": True,
                        "phase": "entry_authority", "effect_ids": effects.effect_ids,
                        "started_at": entered["started_at"],
                        "budget_envelope": context.budget_envelope.to_dict(),
                        "limiting_source": details.get("limiting_source"), "details": details}
                entry_confirmed.set()
            while True:
                if future.done():
                    return future.result()
                if self._stop_event.is_set():
                    active.clear()
                    future.cancel()
                    return {
                        "kind": "authority_revoked",
                        "reason": "runtime_closed",
                        "effect_ids": effects.effect_ids,
                    }
                view = context.budget
                if view.clock_status == "unknown":
                    active.clear()
                    return {"kind": "error", "code": "budget_clock_unknown", "control_error": True,
                        "message": "execution clock continuity cannot be established", "effect_ids": effects.effect_ids}
                current_deadline = context.budget_envelope.deadline_monotonic(sample=context._sample())
                if current_deadline is not None:
                    deadline = min(deadline, current_deadline)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    active.clear()
                    future.cancel()
                    view = context.budget
                    return {"kind": "timeout", "effect_ids": effects.effect_ids,
                        "started_at": entered.get("started_at"), "limiting_source": view.limiting_source,
                        "budget_envelope": context.budget_envelope.to_dict()}
                try:
                    return future.result(timeout=min(remaining, 0.05))
                except FutureTimeoutError:
                    continue
        except FutureTimeoutError:  # defensive: the loop handles normal expiry
            active.clear()
            future.cancel()
            return {"kind": "timeout", "effect_ids": effects.effect_ids}

    def _outcome_result(
        self,
        command: ExecutionCommandV2,
        lease: ExecutionLease,
        started_at: float,
        outcome: dict[str, Any],
    ) -> ExecutionResultV2:
        try:
            completed_at = max(started_at, outcome["completed_at"] if "completed_at" in outcome
                else self._completion_time(started_at))
            kind = outcome.get("kind")
            effect_ids = outcome.get("effect_ids", [])
            if kind == "timeout":
                source = outcome.get("limiting_source", "execution")
                error = ExecutionError(
                    code=outcome.get("code") or ("handler_timeout" if source == "execution" else "execution_deadline_exhausted"),
                    message=outcome.get("message") or f"handler exceeded {command.timeout_seconds} seconds",
                    retryable=command.retry_policy.retry_timeouts,
                    details={**(outcome.get("details") or {}),
                             "timeout_seconds": command.timeout_seconds, "limiting_source": source,
                             "budget_envelope": outcome.get("budget_envelope"), "phase": outcome.get("phase")},
                )
                status = "timed_out"
                value = None
            elif kind == "error":
                error = ExecutionError(
                    code=outcome.get("code"),
                    message=outcome.get("message"),
                    retryable=outcome.get("retryable"),
                    details=outcome.get("details"),
                )
                status = "failed"
                value = None
            else:
                error = None
                status = "succeeded"
                value = outcome.get("value")
            return ExecutionResultV2(
                result_id=uuid.uuid4().hex,
                execution_id=command.execution_id,
                status=status,
                attempt=lease.attempt,
                fence=lease.fence,
                effect_ids=effect_ids,
                started_at=started_at,
                completed_at=completed_at,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
                value=value,
                error=error,
            )
        except ContractValidationError as exc:
            completed_at = max(started_at, outcome["completed_at"] if "completed_at" in outcome
                else self._completion_time(started_at))
            safe_effect_ids = (
                effect_ids
                if type(effect_ids) is list
                and all(type(item) is str and item.strip() for item in effect_ids)
                and len(effect_ids) == len(set(effect_ids))
                else outcome.get("persisted_effect_ids", [])
            )
            return ExecutionResultV2(
                result_id=uuid.uuid4().hex,
                execution_id=command.execution_id,
                status="failed",
                attempt=lease.attempt,
                fence=lease.fence,
                effect_ids=safe_effect_ids,
                started_at=started_at,
                completed_at=completed_at,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
                value=None,
                error=ExecutionError(code="invalid_handler_result", message=str(exc),
                    retryable=False, details={}),
            )

    def _completion_time(self, started_at: float) -> float:
        try:
            with self.kernel._control_lock(.1):
                return max(started_at, self.kernel.current_time())
        except (TimeoutError, sqlite3.OperationalError):
            # The actual outcome is already known locally. Collection must
            # not wait on the writer which its receipt is meant to survive.
            return max(started_at, self.kernel._wall_time())

    def _settle_outcome(self, snapshot, lease: ExecutionLease,
                        outcome: dict[str, Any], admission: SettlementAdmission):
        key = (lease.execution_id, lease.attempt, lease.fence)
        with self._settlement_inflight_lock:
            self._settlement_inflight.add(key)
        try:
            return self._settle_outcome_active(snapshot, lease, outcome, admission)
        finally:
            with self._settlement_inflight_lock:
                self._settlement_inflight.discard(key)

    def _settle_outcome_active(self, snapshot, lease: ExecutionLease,
                               outcome: dict[str, Any], admission: SettlementAdmission):
        """Retain the original result before a bounded Kernel completion CAS."""
        command = snapshot.command
        if outcome.get("kind") == "authority_revoked":
            try:
                with self.kernel._control_lock(.1):
                    return self.kernel.get(lease.execution_id)
            except (TimeoutError, sqlite3.OperationalError):
                return snapshot
        try:
            with self.kernel._control_lock(.1):
                persisted = self.kernel.effect_ids_for_attempt(command.execution_id,
                    lease.attempt, lease.fence,
                    states={"prepared", "performing", "committed", "indeterminate"})
        except (TimeoutError, sqlite3.OperationalError):
            persisted = []
        outcome = dict(outcome)
        reported = outcome.get("effect_ids", [])
        if type(reported) is list and all(type(item) is str for item in reported):
            outcome["effect_ids"] = list(dict.fromkeys(reported + persisted))
        outcome["persisted_effect_ids"] = persisted
        deferred_kind = ("recovery_required" if outcome.get("kind") == "recovery_required" else
            "completion_time_unknown" if outcome.get("completion_time_known") is False else None)
        deferred = deferred_kind is not None
        result = None if deferred else self._outcome_result(command, lease, snapshot.started_at, outcome)
        if deferred:
            payload = {"kind": deferred_kind, "outcome": outcome}
            journal_payload: dict[str, Any] | ExecutionResultV2 = payload
        else:
            assert result is not None
            payload = result.to_dict()
            journal_payload = result
        # The original observed clock floor is part of the result obligation.
        # Retrying publication must never sample a new return-time budget or
        # release a retry before this floor and the result commit together.
        retained_budget = outcome.get("budget_envelope")
        budget = None if retained_budget is None else BudgetEnvelope.from_dict(retained_budget)
        evidence = {"telemetry_flush": outcome.get("telemetry_flush"), "outcome_kind": outcome.get("kind"),
                    "budget_envelope": retained_budget}
        retained_key = self._pending_settlements.retain(admission, lease, payload, evidence)
        record = None
        if self._settlement_journal is not None:
            try:
                record = self._settlement_journal.record(lease,
                    journal_payload,
                    evidence=evidence,
                    timeout_seconds=.1)
                self._pending_settlements.persisted(retained_key)
            except Exception as exc:
                self._settlement_error = f"{type(exc).__name__}: {exc}"
        if not self._lifecycle_lock.acquire(timeout=.1):
            self._activity_phase(lease, "result_pending", durable_receipt=record is not None,
                error="runtime lifecycle busy", receipt_error=self._settlement_error)
            return snapshot
        try:
            if self._closed:
                return snapshot
            if deferred_kind == "completion_time_unknown":
                self._activity_phase(lease, "result_pending", durable_receipt=record is not None,
                    unknown_reason="completion_time_unknown",
                    error=outcome.get("completion_time_error"))
                return snapshot
            if deferred:
                # The effect already has durable recovery ownership; no
                # invented successful result may replace it.
                try:
                    completed = self.kernel.require_effect_recovery(lease, outcome.get("effect_id"),
                        timeout_seconds=.1)
                    if record is not None:
                        self._settlement_journal.settle(record, "recovery_required",
                            {**record["evidence"], "execution_state": completed.state, "execution_revision": completed.revision},
                            timeout_seconds=.1)
                    return completed
                except Exception as exc:
                    if self._storage_contention(exc) or isinstance(exc, TimeoutError):
                        return snapshot
                    raise
            assert result is not None
            try:
                completed = self.kernel._complete_sdk_result(lease, result,
                    budget_envelope=budget, timeout_seconds=.1)
            except Exception as exc:
                if isinstance(exc, (StaleFenceError, InvalidStateTransitionError, ResultConflictError)):
                    # Cancellation/reap may have won while the independent
                    # receipt was being saved. Preserve that receipt and the
                    # immutable winner instead of surfacing a worker failure.
                    with self.kernel._control_lock(.1):
                        return self.kernel.get(lease.execution_id)
                if not self._storage_contention(exc) and not isinstance(exc, TimeoutError):
                    raise
                self._activity_phase(lease, "result_pending", result_id=result.result_id,
                    durable_receipt=record is not None,
                    error=f"{type(exc).__name__}: {exc}", receipt_error=self._settlement_error)
                return snapshot
            if record is not None:
                try:
                    state = "recovery_required" if completed.state == "recovery_required" else "recorded"
                    self._settlement_journal.settle(record, state,
                        {**record["evidence"], "execution_state": completed.state, "execution_revision": completed.revision,
                         "result_id": result.result_id}, timeout_seconds=.1)
                except Exception as exc:
                    self._settlement_error = f"{type(exc).__name__}: {exc}"
            elif completed.result is not None and completed.result.result_id == result.result_id:
                # The authoritative Kernel itself durably owns the exact result.
                self._pending_settlements.persisted(retained_key)
            self._activity_phase(lease, "result_recorded", state=completed.state,
                result_id=result.result_id, source="kernel_complete")
            return completed
        finally:
            self._lifecycle_lock.release()

    def run_once(self, *, execution_id: str | None = None):
        self._start_services()
        self.recover_completions(timeout_seconds=.25)
        admission = self._pending_settlements.acquire()
        if admission is None:
            # Bound both active calls and outcomes waiting for persistence;
            # leave additional work queued until a reservation is released.
            return None
        with self._lifecycle_condition:
            if self._closed:
                self._pending_settlements.finish(admission)
                return None
            self._active_runs += 1
        try:
            return self._run_once_active(execution_id=execution_id, admission=admission)
        finally:
            self._pending_settlements.finish(admission)
            with self._lifecycle_condition:
                self._active_runs -= 1
                self._lifecycle_condition.notify_all()

    def _run_once_active(self, *, execution_id: str | None = None, admission: SettlementAdmission):
        self._assert_registry_current()
        limits = None if execution_id is None else self.kernel.get_execution_limits(execution_id)
        targeted_child = limits is not None and limits.get("parent_execution_id") is not None
        last_rejected = None
        while True:
            thread_slot_owned = False
            process_execution_started = False
            if self.isolation_mode == "thread":
                if not self._acquire_thread_slot(child=targeted_child):
                    # Every running/timed-out call owns one slot until its
                    # underlying thread really exits.  Do not claim and queue
                    # more work behind a stuck call.
                    return last_rejected
                thread_slot_owned = True
            try:
                with self._lifecycle_lock if execution_id is None else self._bounded_lifecycle(
                        .1, message="child lifecycle admission timed out"):
                    if self._closed:
                        return last_rejected
                    running_lease = self.kernel.claim_and_start(
                        self.worker_id,
                        lease_seconds=self.lease_seconds,
                        start_safety_seconds=self._handler_start_timeout() + 5.0,
                        registry_revisions=(self.registry_revision, *self.handler_revisions.values()),
                        execution_id=execution_id,
                        timeout_seconds=None if execution_id is None else .1,
                        child_pool=targeted_child,
                    )
                    if (
                        running_lease is not None
                        and self.isolation_mode == "process"
                    ):
                        # Keep registration inside the same lifecycle lock as
                        # claim-and-start.  Cancellation cannot observe a
                        # running row without also seeing its registration
                        # marker.
                        self._begin_process_execution(running_lease)
                        process_execution_started = True
                if running_lease is None:
                    return last_rejected
                snapshot = self.kernel.get(running_lease.execution_id)
                self._begin_activity(running_lease)
                command = snapshot.command
                handler, permanent_error = self._handler_or_error(command)
                if permanent_error is not None:
                    last_rejected = self.kernel.dead_letter(
                        running_lease, permanent_error
                    )
                    continue
                assert handler is not None
                started_at = snapshot.started_at
                assert started_at is not None
                if self.isolation_mode == "process":
                    outcome = self._invoke_process(handler, command, running_lease)
                else:
                    outcome = self._invoke_thread(handler, command, running_lease, child=targeted_child)
                    # The done callback owns the slot from this point.  This
                    # remains true for a timeout: the Python thread may still
                    # be running and must continue to consume its slot.
                    thread_slot_owned = False
                self._activity_phase(running_lease, "handler_outcome", kind=outcome.get("kind"),
                    code=outcome.get("code"), limiting_source=outcome.get("limiting_source"),
                    details=outcome.get("details"), telemetry_flush=outcome.get("telemetry_flush"),
                    isolation_mode=self.isolation_mode,
                    process_stop="not_applicable" if self.isolation_mode == "thread" else "unknown")
                flush = outcome.get("telemetry_flush")
                self._diagnostic_note(running_lease, "handler_outcome", {
                    "kind": outcome.get("kind"), "code": outcome.get("code"),
                    "details": outcome.get("details"), "telemetry_flush": flush,
                    "telemetry_incomplete": isinstance(flush, dict) and flush.get("state") != "confirmed"})
                return self._settle_outcome(snapshot, running_lease, outcome, admission)
            finally:
                if process_execution_started:
                    # Native invocation has already completed containment.
                    # Final telemetry collection must not keep cancellation
                    # waiting for a process tree that has been reaped.
                    self._finish_process_execution(running_lease)
                if 'running_lease' in locals() and running_lease is not None:
                    recorder = self._execution_recorders.pop((running_lease.execution_id, running_lease.attempt, running_lease.fence), None)
                    if recorder is not None:
                        try:
                            receipt = recorder.close()
                        finally:
                            self._retain_observation_workers(recorder)
                        local = recorder.snapshot()
                        self._diagnostic_note(running_lease, "driver_close", {
                            "receipt": receipt, "dropped_events": local["dropped_events"],
                            "collection_gaps": local["collection_gaps"], "error": local["error"],
                            "telemetry_incomplete": not receipt.get("final_flush_persisted", False)
                                or not receipt.get("source_closed", False)
                                or local["dropped_events"] > 0 or local["collection_gaps"] > 0})
                if thread_slot_owned:
                    self._release_thread_slot(child=targeted_child)


Runtime = InProcessRuntime
