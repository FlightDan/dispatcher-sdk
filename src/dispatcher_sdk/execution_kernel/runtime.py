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
import multiprocessing
import os
import threading
import time
from typing import Any, Mapping, Optional
from types import MappingProxyType
import uuid

from ..durability import Durability, validate_durability

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
    HandlerUnavailableError,
    RegistryRevisionMismatchError,
    ExecutionNotFoundError,
)
from ._registry import Handler, handler_revision, normalize_handlers, registry_revision
from ._process_runtime import (
    ProcessSupervisorHandle,
    invoke_handler,
    invoke_process_handler,
)
from .sqlite import SQLiteKernel
from .sandbox import SandboxHandler, SandboxJournal
from .sandbox_contracts import SandboxOutcomeUnknown
from ._sandbox_registry import register_journals, journal_paths


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
    ) -> None:
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
        self.isolation_mode = isolation_mode
        self._lifecycle_lock = threading.RLock()
        self._lifecycle_condition = threading.Condition(self._lifecycle_lock)
        self._close_complete = threading.Event()
        self._close_error: BaseException | None = None
        self._stop_event = threading.Event()
        self._active_runs = 0
        self._process_supervisors: dict[str, Any] = {}
        # Exists from the moment a claimed execution enters process
        # invocation until its supervisor has been reaped.  Cancellation
        # waits on this marker so a start/register race cannot report success
        # while a process tree is still becoming visible to the runtime.
        self._process_registration_events: dict[str, threading.Event] = {}
        self._revoked_executions: dict[str, str] = {}
        self._thread_lock = threading.RLock()
        self._closed = False
        self._thread_executor: Optional[ThreadPoolExecutor] = None
        self._thread_slots: Optional[threading.BoundedSemaphore] = None
        self._thread_authorities: set[threading.Event] = set()
        self._thread_authority_by_execution: dict[str, threading.Event] = {}
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
            sandbox_bindings = [handler for handler in self.handlers.values() if isinstance(handler, SandboxHandler)]
            self._sandbox_store_id = register_journals(self.kernel.db_path, [],
                durability=self.durability, initialize_only=bool(sandbox_bindings))
            registered_paths = journal_paths(self.kernel.db_path)
            for handler in sandbox_bindings:
                if handler.journal_path in registered_paths:
                    # Verify existing registration before a journal constructor
                    # could initialize a replaced or empty file.
                    register_journals(self.kernel.db_path, [handler.journal_path], durability=self.durability)
                handler.journal()._bind_store(self._sandbox_store_id)
            if sandbox_bindings:
                register_journals(self.kernel.db_path, [h.journal_path for h in sandbox_bindings], durability=self.durability)
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
            if self._close_error is not None:
                raise self._close_error
            return
        try:
            self.request_stop()
            with self._lifecycle_condition:
                while self._active_runs:
                    self._lifecycle_condition.wait()
            try:
                unresolved = self.recover_sandboxes(all_pages=True)
                if any(not item["cleanup_confirmed"] for item in unresolved):
                    raise SandboxOutcomeUnknown("remote cleanup remains pending in the sandbox journal")
            finally:
                self.kernel.close()
        except BaseException as exc:
            self._close_error = exc
            raise
        finally:
            self._close_complete.set()

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
        for supervisor in supervisors:
            supervisor.revoke("runtime_closed")
        if executor is not None:
            # Running Python threads cannot be killed. Their Kernel authority
            # is revoked and the run_once wrapper is woken promptly.
            executor.shutdown(wait=False, cancel_futures=True)

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
    ):
        """Externally cancel one execution with revision-CAS authority."""

        registration: Optional[threading.Event] = None
        recovery_error: EffectRecoveryRequiredError | None = None
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("runtime is closed")
            before = self.kernel.get(execution_id)
            try:
                cancelled = self.kernel.cancel(
                    execution_id,
                    expected_revision=expected_revision,
                    reason=reason,
                )
            except EffectRecoveryRequiredError as exc:
                # The durable state is now recovery_required, but cancellation
                # authority still requires the running process tree to stop
                # before the Bridge may acknowledge the intent.
                cancelled = None
                recovery_error = exc
            if self.isolation_mode == "process" and before.state in {"leased", "running"}:
                self._revoked_executions[execution_id] = "execution_cancelled"
            supervisor = self._process_supervisors.get(execution_id)
            registration = self._process_registration_events.get(execution_id)
            with self._thread_lock:
                thread_authority = self._thread_authority_by_execution.get(execution_id)
        if supervisor is not None:
            if not supervisor.revoke("execution_cancelled"):
                raise RuntimeError(
                    f"process supervisor for {execution_id} did not terminate"
                )
        if registration is not None and not registration.wait(
            self._handler_start_timeout()
        ):
            raise RuntimeError(
                f"process registration for {execution_id} did not settle after cancellation"
            )
        if thread_authority is not None:
            thread_authority.clear()
        handler = self.handlers.get((before.command.handler_id, before.command.handler_contract_version))
        unresolved = self.recover_sandboxes(all_pages=True, execution_id=execution_id,
                                            max_fence=before.fence)
        if any(not item["cleanup_confirmed"] for item in unresolved):
            raise SandboxOutcomeUnknown("cancellation has not confirmed remote sandbox disposal")
        if recovery_error is not None:
            raise recovery_error
        assert cancelled is not None
        return cancelled

    def events_since(self, after_sequence: int, limit: int = 100):
        return self.kernel.events_since(after_sequence, limit)

    def pending_recoveries(self, *, limit: int = 100):
        return self.kernel.pending_recoveries(limit=limit)

    def reap(self):
        """Reap expired execution leases through the durable Kernel API."""

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

    def _begin_process_execution(self, execution_id: str) -> None:
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("runtime is closed")
            self._process_registration_events[execution_id] = threading.Event()

    def _finish_process_execution(self, execution_id: str) -> None:
        with self._lifecycle_lock:
            registration = self._process_registration_events.pop(execution_id, None)
            if registration is not None:
                registration.set()

    def _acquire_thread_slot(self) -> bool:
        if self.isolation_mode != "thread":
            return True
        with self._thread_lock:
            if self._closed or self._thread_slots is None:
                return False
            return self._thread_slots.acquire(blocking=False)

    def _release_thread_slot(self) -> None:
        if self.isolation_mode != "thread":
            return
        with self._thread_lock:
            if self._thread_slots is not None:
                self._thread_slots.release()

    def _thread_finished(
        self, authority: threading.Event, execution_id: str
    ) -> None:
        with self._thread_lock:
            if authority not in self._thread_authorities:
                return
            self._thread_authorities.remove(authority)
            if self._thread_authority_by_execution.get(execution_id) is authority:
                del self._thread_authority_by_execution[execution_id]
            if self._thread_slots is not None:
                self._thread_slots.release()

    def _handler_start_timeout(self) -> float:
        return max(5.0, min(self.lease_seconds, 30.0))

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
        def register(supervisor: Any) -> bool:
            with self._lifecycle_lock:
                reason = self._revoked_executions.pop(command.execution_id, None)
                if reason is None and (
                    self._closed or self._stop_event.is_set()
                ):
                    reason = "runtime_closed"
                if reason is None:
                    self._process_supervisors[command.execution_id] = supervisor
                    return True
            # The caller that requested cancellation waits for the outer
            # invocation to finish.  Do the kill synchronously here so a
            # process which wins the start/register race cannot run with
            # revoked authority.
            supervisor.revoke(reason)
            return False

        def unregister(supervisor: Any) -> None:
            with self._lifecycle_lock:
                if self._process_supervisors.get(command.execution_id) is supervisor:
                    del self._process_supervisors[command.execution_id]
                self._revoked_executions.pop(command.execution_id, None)

        invoke = invoke_process_handler
        if os.name == "nt":
            from ._windows_runtime import invoke_windows_handler
            invoke = invoke_windows_handler
        outcome = invoke(
            db_path=self.kernel.db_path,
            durability=self.durability,
            handler=handler,
            command=command,
            lease=lease,
            now=self._now,
            start_timeout=self._handler_start_timeout(),
            on_started=register,
            on_finished=unregister,
        )
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
    ) -> dict[str, Any]:
        active = threading.Event()
        active.set()
        effects = HandlerEffects(self.kernel, lease, active.is_set)
        context = HandlerContext(command, lease, effects)
        executor = self._thread_executor
        if executor is None:
            raise RuntimeError("thread isolation executor is not available")
        started = threading.Event()

        def invoke_started() -> dict[str, Any]:
            started.set()
            return invoke_handler(handler, command, context)

        with self._thread_lock:
            if self._closed:
                active.clear()
                raise RuntimeError("runtime is closed")
            self._thread_authorities.add(active)
            self._thread_authority_by_execution[command.execution_id] = active
        try:
            future = executor.submit(invoke_started)
        except BaseException:
            with self._thread_lock:
                self._thread_authorities.discard(active)
                if self._thread_authority_by_execution.get(command.execution_id) is active:
                    del self._thread_authority_by_execution[command.execution_id]
            active.clear()
            raise
        future.add_done_callback(
            lambda _future: self._thread_finished(active, command.execution_id)
        )
        try:
            if not started.wait(self._handler_start_timeout()):
                active.clear()
                future.cancel()
                return {
                    "kind": "error",
                    "code": "handler_thread_start_failure",
                    "message": "handler thread did not reach invocation",
                    "retryable": False,
                    "details": {},
                    "effect_ids": effects.effect_ids,
                }
            deadline = time.monotonic() + command.timeout_seconds
            while True:
                if self._stop_event.is_set():
                    active.clear()
                    future.cancel()
                    return {
                        "kind": "authority_revoked",
                        "reason": "runtime_closed",
                        "effect_ids": effects.effect_ids,
                    }
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    active.clear()
                    future.cancel()
                    return {"kind": "timeout", "effect_ids": effects.effect_ids}
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
            completed_at = max(started_at, self.kernel.current_time())
            kind = outcome.get("kind")
            effect_ids = outcome.get("effect_ids", [])
            if kind == "timeout":
                error = ExecutionError(
                    code="handler_timeout",
                    message=f"handler exceeded {command.timeout_seconds} seconds",
                    retryable=command.retry_policy.retry_timeouts,
                    details={"timeout_seconds": command.timeout_seconds},
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
            completed_at = max(started_at, self.kernel.current_time())
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
                error=ExecutionError(
                    code="invalid_handler_result",
                    message=str(exc),
                    retryable=False,
                    details={},
                ),
            )

    def run_once(self):
        with self._lifecycle_condition:
            if self._closed:
                return None
            self._active_runs += 1
        try:
            return self._run_once_active()
        finally:
            with self._lifecycle_condition:
                self._active_runs -= 1
                self._lifecycle_condition.notify_all()

    def _run_once_active(self):
        self._assert_registry_current()
        last_rejected = None
        while True:
            thread_slot_owned = False
            process_execution_started = False
            if self.isolation_mode == "thread":
                if not self._acquire_thread_slot():
                    # Every running/timed-out call owns one slot until its
                    # underlying thread really exits.  Do not claim and queue
                    # more work behind a stuck call.
                    return last_rejected
                thread_slot_owned = True
            try:
                with self._lifecycle_lock:
                    if self._closed:
                        return last_rejected
                    running_lease = self.kernel.claim_and_start(
                        self.worker_id,
                        lease_seconds=self.lease_seconds,
                        start_safety_seconds=self._handler_start_timeout() + 5.0,
                        registry_revisions=(self.registry_revision, *self.handler_revisions.values()),
                    )
                    if (
                        running_lease is not None
                        and self.isolation_mode == "process"
                    ):
                        # Keep registration inside the same lifecycle lock as
                        # claim-and-start.  Cancellation cannot observe a
                        # running row without also seeing its registration
                        # marker.
                        self._begin_process_execution(running_lease.execution_id)
                        process_execution_started = True
                if running_lease is None:
                    return last_rejected
                snapshot = self.kernel.get(running_lease.execution_id)
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
                    outcome = self._invoke_thread(handler, command, running_lease)
                    # The done callback owns the slot from this point.  This
                    # remains true for a timeout: the Python thread may still
                    # be running and must continue to consume its slot.
                    thread_slot_owned = False
                with self._lifecycle_lock:
                    current = self.kernel.get(running_lease.execution_id)
                    runtime_closed = self._closed
                    if (
                        outcome.get("kind") == "authority_revoked"
                        or runtime_closed
                        or current.state != "running"
                        or current.lease is None
                        or current.lease.lease_id != running_lease.lease_id
                        or current.lease.fence != running_lease.fence
                    ):
                        return current
                    if outcome.get("kind") == "recovery_required":
                        if current.state == "recovery_required":
                            return current
                        return self.kernel.require_effect_recovery(
                            running_lease, outcome.get("effect_id")
                        )
                    outcome = dict(outcome)
                    persisted_effect_ids = self.kernel.effect_ids_for_attempt(
                        command.execution_id,
                        running_lease.attempt,
                        running_lease.fence,
                        states={
                            "prepared",
                            "performing",
                            "committed",
                            "indeterminate",
                        },
                    )
                    reported_effect_ids = outcome.get("effect_ids")
                    if type(reported_effect_ids) is list and all(
                        type(item) is str for item in reported_effect_ids
                    ):
                        outcome["effect_ids"] = list(
                            dict.fromkeys(reported_effect_ids + persisted_effect_ids)
                        )
                    outcome["persisted_effect_ids"] = persisted_effect_ids
                    result = self._outcome_result(
                        command, running_lease, started_at, outcome
                    )
                    # The lifecycle lock is also held by cancel().  State
                    # validation and the terminal CAS therefore have one
                    # winner instead of allowing cancel to land between them.
                    return self.kernel.complete(running_lease, result)
            finally:
                if process_execution_started:
                    self._finish_process_execution(running_lease.execution_id)
                if thread_slot_owned:
                    self._release_thread_slot()


Runtime = InProcessRuntime
