"""Reserved SDK handler execution for the existing durable stall inbox.

The inbox owns delivery, Kernel owns commands/results and Run deadlines, and
Runtime owns process containment. This scheduler creates no business ledger.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
import inspect
import json
import math
import sqlite3
import threading
import time
from typing import Any
from types import SimpleNamespace
import uuid

from .contracts import ManagedStallOptions
from ..durability import configure_sqlite_connection
from ..orchestrator.inbox import NotificationInbox, _number
from .._sqlite_admission import retry_sqlite_admission
from ..storage_connection import connect as storage_connect


_SOURCE = "dispatcher.stalls.v1"
_HANDLER = "__sdk_stall_supervisor__"


class _AdmissionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _error(error: BaseException) -> dict[str, Any]:
    try:
        raw = str(error).encode("utf-8", errors="replace")
    except BaseException:
        raw = b"error message could not be rendered"
    attributes = {}
    unavailable, truncated_attributes = [], []
    frames = []
    current = error.__traceback__
    for _ in range(16):
        if current is None:
            break
        code = current.tb_frame.f_code
        frames.append({"file": code.co_filename.encode("utf-8", errors="replace")[:512].decode("utf-8", errors="ignore"),
                       "line": current.tb_lineno, "function": code.co_name[:128]})
        current = current.tb_next
    for name in ("code", "sqlite_errorcode", "sqlite_errorname"):
        try:
            value = getattr(error, name, None)
            attributes[name] = value if type(value) in (str, int) else None
            if type(value) is str:
                encoded = value.encode("utf-8", errors="replace")
                attributes[name] = encoded[:2048].decode("utf-8", errors="ignore")
                if len(encoded) > 2048:
                    truncated_attributes.append(name)
        except BaseException:
            attributes[name] = None
            unavailable.append(name)
    return {"type": type(error).__name__, **attributes,
            "message": raw[:2048].decode("utf-8", errors="ignore"),
            "truncated": len(raw) > 2048 or bool(truncated_attributes),
            "unavailable_attributes": unavailable, "truncated_attributes": truncated_attributes,
            "frames": frames, "frames_truncated": current is not None}


class _SupervisorInbox(NotificationInbox):
    """Same inbox protocol, with bounded connections owned by the scheduler."""
    def __init__(self, path, *, durability, timeout):
        self._timeout = timeout
        super().__init__(path, durability=durability)

    def _connect(self):
        connection = storage_connect(self.db_path, timeout=self._timeout, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            configure_sqlite_connection(connection, self.db_path, durability=self.durability,
                                        timeout_seconds=self._timeout)
            connection.execute("PRAGMA foreign_keys=ON")
            # BEGIN admission retries share the original operation cutoff;
            # native busy sleep must not extend that window independently.
            connection.execute("PRAGMA busy_timeout=0")
            return connection
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def _transaction(self):
        """Admit BEGIN within the existing operation window, not one poll."""
        deadline = time.monotonic()+self._timeout
        connection = self._connect()
        try:
            retry_sqlite_admission(lambda: connection.execute("BEGIN IMMEDIATE"),
                deadline=deadline, expired=TimeoutError("managed inbox transaction admission elapsed"))
            watermark = float(connection.execute(
                "SELECT value FROM main.notification_inbox_clock WHERE id=1").fetchone()[0])

            def now():
                nonlocal watermark
                watermark = max(watermark, _number(self.clock(), "clock"))
                connection.execute("UPDATE main.notification_inbox_clock SET value=? WHERE id=1", (watermark,))
                return watermark

            # Keep the existing inbox clock/savepoint protocol exactly: failed
            # bodies publish the observed watermark without replaying the body.
            now()
            connection.execute("SAVEPOINT inbox_operation")
            try:
                yield connection, now
            except BaseException as body_error:
                try:
                    connection.execute("ROLLBACK TO inbox_operation")
                    connection.execute("RELEASE inbox_operation")
                    connection.execute("UPDATE main.notification_inbox_clock SET value=? WHERE id=1", (watermark,))
                    connection.commit()
                except BaseException as persistence_error:
                    # Preserve the raised operation; a failed watermark write
                    # is evidence of unconfirmed persistence, not its result.
                    raise body_error from persistence_error
                raise
            connection.execute("RELEASE inbox_operation")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def inspect_record(self, source_id, notification_id, *, budget, max_bytes):
        """Read the original receipt without starting a writer/configuration."""
        from pathlib import Path
        connection = sqlite3.connect(Path(self.db_path).as_uri()+"?mode=ro", uri=True,
                                     timeout=budget.sqlite_timeout_seconds)
        connection.row_factory = sqlite3.Row
        try:
            budget.install(connection)
            connection.execute("BEGIN")
            marker = connection.execute("SELECT source_id,notification_id,state,attempts,fence,revision,"
                "created_at,length(CAST(payload AS BLOB))+COALESCE(length(CAST(last_error AS BLOB)),0) AS bytes "
                "FROM notification_inbox_messages WHERE source_id=? AND notification_id=?",
                (source_id, notification_id)).fetchone()
            if marker is None:
                raise KeyError((source_id, notification_id))
            budget.check()
            if marker["bytes"] > max_bytes:
                return {**{key: marker[key] for key in marker.keys() if key != "bytes"},
                        "payload": None, "last_error": None, "truncated": True,
                        "unknown_reason": "managed_status_byte_limit"}
            row = self._row(connection, source_id, notification_id)
            budget.check()
            record = self._record(row)
            budget.check()
            return record
        finally:
            connection.close()

    def has_unsettled(self, source_id):
        """An empty source needs no durable clock or lease mutation.

        This is only an advisory readiness read. The original atomic claim
        still checks eligibility/expiry and owns all delivery authority.
        """
        from pathlib import Path
        from .._inspection import InspectionBudget
        budget = InspectionBudget(self._timeout, None)
        connection = sqlite3.connect(Path(self.db_path).as_uri()+"?mode=ro", uri=True,
                                     timeout=budget.sqlite_timeout_seconds)
        try:
            budget.install(connection)
            ready = connection.execute("SELECT 1 FROM notification_inbox_messages "
                "WHERE source_id=? AND state IN ('pending','processing') LIMIT 1", (source_id,)).fetchone()
            budget.check()
            return ready is not None
        finally:
            connection.close()


class ManagedStallSupervisor:
    def __init__(self, dispatcher, handler, options: ManagedStallOptions):
        if not callable(handler) or inspect.iscoroutinefunction(handler):
            raise TypeError("managed stall handler must be synchronous")
        if type(options) is not ManagedStallOptions:
            raise TypeError("options must be ManagedStallOptions")
        from ..execution_kernel.runtime import InProcessRuntime

        self.options = options
        self._dispatcher = dispatcher
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._owner = "managed-stalls:" + uuid.uuid4().hex
        self._active: dict[str, Future[Any]] = {}
        self._ownership: dict[str, dict[str, Any]] = {}
        self._admissions: dict[str, dict[str, Any]] = {}
        self._finished: set[str] = set()
        self._cleanup_proofs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cleanup_proof_evictions = 0
        self._thread: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._executor_unavailable = False
        self._executor_error: dict[str, Any] | None = None
        self._executor_shutdown_error: dict[str, Any] | None = None
        self._close_thread: threading.Thread | None = None
        self._close_done = threading.Event()
        self._close_error: BaseException | None = None
        self._last_error: dict[str, Any] | None = None
        self._admission_state = "not_started"
        self._completed = 0
        self._peak_active = 0
        self._empty_polls = 0
        self._claim_calls = 0
        self._storage_timeout = dispatcher.runtime.observation_options.write_timeout
        self.runtime = InProcessRuntime(str(dispatcher.path), {_HANDLER: handler},
            isolation_mode="process", durability=dispatcher.runtime.durability,
            observation_options=dispatcher.runtime.observation_options,
            process_memory_limit_bytes=options.memory_limit_bytes, allow_children=False,
            child_capacity=options.capacity, worker_id=self._owner)
        self.runtime._process_cleanup_observer = self._cleanup_receipt
        try:
            self.inbox = _SupervisorInbox(dispatcher.path, durability=self.runtime.durability,
                                          timeout=self._storage_timeout)
        except BaseException:
            self.runtime.close()
            raise

    @staticmethod
    def identities(notification_id: str) -> tuple[str, str]:
        if type(notification_id) is not str:
            raise ValueError("notification_id must be a nonempty string")
        if len(notification_id) > 900:
            raise ValueError("notification_id is too long for managed execution identity")
        if not notification_id.strip():
            raise ValueError("notification_id must be a nonempty string")
        if len(notification_id.encode("utf-8")) > 900:
            raise ValueError("notification_id is too long for managed execution identity")
        return ("stall-supervisor:" + notification_id,
                "sdk-managed:stall-supervisor:" + notification_id)

    def start(self):
        with self._lock:
            if self._stop.is_set():
                raise RuntimeError("managed stall supervisor is stopping")
            if self._thread is not None:
                return
            self._executor = ThreadPoolExecutor(max_workers=self.options.capacity,
                                               thread_name_prefix="dispatcher-stall-handler")
            self._thread = threading.Thread(target=self._coordinate,
                name="dispatcher-managed-stalls", daemon=True)
            try:
                self._thread.start()
            except BaseException:
                self._thread = None
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None
                raise

    def _collect(self):
        with self._lock:
            done = [(key, future) for key, future in self._active.items() if future.done()]
        for key, future in done:
            with self._lock:
                if key not in self._finished:
                    if not future.cancelled():
                        try:
                            future.result()
                        except BaseException as error:
                            self._last_error = _error(error)
                    self._finished.add(key)
                    self._completed += 1
                owned = dict(self._ownership[key])
            checkpoint_pending = self._finish_admission_checkpoint(key)
            if owned["state"] == "unknown":
                try:
                    self._recover_cleanup(key, owned)
                except Exception as error:
                    with self._lock:
                        self._last_error = {**_error(error), "phase": "cleanup_proof_recovery"}
                with self._lock:
                    owned = dict(self._ownership[key])
            if not checkpoint_pending and owned["state"] in {"confirmed", "not_invoked"} and (
                    owned["attempt"] is None or not self.runtime._execution_observation_pending(
                        owned["execution_id"], owned["attempt"], owned["fence"])):
                with self._lock:
                    del self._active[key]
                    del self._ownership[key]
                    self._admissions.pop(key, None)
                    self._finished.discard(key)

    def _finish_admission_checkpoint(self, notification_id):
        """Finish only retained facts, including after original work expires."""
        with self._lock:
            admission = self._admissions.get(notification_id)
        if admission is None:
            return False
        deadline = time.monotonic()+self._storage_timeout
        pending = False
        owners = []
        for owner in (admission["capture"], admission["pending_owner"]):
            if owner is not None and all(owner is not prior for prior in owners):
                owners.append(owner)
        for owner in owners:
            if getattr(owner, "_pending", None) is None:
                continue
            try:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("original checkpoint cleanup admission elapsed")
                admission["envelope"] = owner.finish_pending(admission["envelope"],
                    timeout_seconds=remaining)
            except Exception as error:
                with self._lock:
                    self._last_error = {**_error(error), "phase": "admission_checkpoint_cleanup"}
            pending = pending or getattr(owner, "_pending", None) is not None
        return pending

    def _cleanup_receipt(self, receipt):
        with self._lock:
            for notification_id, owned in self._ownership.items():
                if owned["execution_id"] == receipt["execution_id"]:
                    if (owned["attempt"] is not None and
                            (owned["attempt"], owned["fence"]) != (receipt["attempt"], receipt["fence"])):
                        # A delayed callback for another lease cannot release
                        # this slot or its native memory reservation.
                        continue
                    owned.update(receipt)
                    owned["source"] = ("actual_runtime_containment" if receipt["state"] == "confirmed"
                                       else "native_preparation_denied")
                    self._cleanup_proofs[notification_id] = dict(owned)
                    self._cleanup_proofs.move_to_end(notification_id)
                    while len(self._cleanup_proofs) > self.options.capacity:
                        self._cleanup_proofs.popitem(last=False)
                        self._cleanup_proof_evictions += 1

    def _recover_cleanup(self, notification_id, owned):
        """Revisit original physical facts; never invoke, flush or renew work."""
        from pathlib import Path
        from .._inspection import InspectionBudget
        budget = InspectionBudget(self._storage_timeout, None)
        connection = sqlite3.connect(Path(self.inbox.db_path).as_uri()+"?mode=ro", uri=True,
                                     timeout=budget.sqlite_timeout_seconds)
        connection.row_factory = sqlite3.Row
        try:
            budget.install(connection)
            row = connection.execute("SELECT execution_id,attempt,fence FROM kernel_executions "
                "WHERE execution_id=?", (owned["execution_id"],)).fetchone()
            budget.check()
        finally:
            connection.close()
        if row is None:
            return
        if owned["attempt"] is not None and (owned["attempt"], owned["fence"]) != (row["attempt"], row["fence"]):
            return  # A different canonical lease cannot discharge this owner.
        if row["attempt"] == 0:
            # SDK native dispatch follows claim. An authoritative unclaimed
            # command proves this failed admission never created a process.
            with self._lock:
                self._ownership[notification_id].update(attempt=0, fence=row["fence"],
                    state="not_invoked", source="canonical_unclaimed")
            return
        self._restore_cleanup(notification_id, SimpleNamespace(**dict(row)),
            timeout_seconds=max(.000001, self._storage_timeout-budget.elapsed_seconds))
        budget.check()

    def _restore_cleanup(self, notification_id, snapshot, *, timeout_seconds=None):
        """Canonical result is business evidence, never process-release proof."""
        with self._lock:
            owned = self._ownership[notification_id]
            if (owned["attempt"] is not None and
                    (owned["attempt"], owned["fence"]) != (snapshot.attempt, snapshot.fence)):
                owned.update(state="unknown", source="cleanup_identity_changed")
            owned.update(attempt=snapshot.attempt, fence=snapshot.fence)
            if (snapshot.attempt > 0 and owned["state"] == "not_invoked"
                    and owned["source"] == "scheduler"):
                owned["state"] = "unknown"
            if owned["state"] in {"confirmed", "not_invoked"} and owned["source"] != "scheduler":
                return
        journal = self.runtime._settlement_journal
        if journal is None:
            return
        report = journal.inspect_notes(snapshot.execution_id,
            timeout_seconds=self._storage_timeout if timeout_seconds is None else timeout_seconds)
        for note in report["notes"]:
            identity = note.get("identity", {})
            evidence = note.get("evidence", {})
            if (note.get("phase") == "process_cleanup" and identity.get("attempt") == snapshot.attempt
                    and identity.get("fence") == snapshot.fence and
                    ((evidence.get("state") == "confirmed" and evidence.get("source") == "runtime_supervisor_reaped") or
                     (evidence.get("state") == "not_invoked" and evidence.get("source") == "runtime_admission_denied"))):
                with self._lock:
                    self._ownership[notification_id].update(state=evidence["state"],
                        source="durable_runtime_containment" if evidence["state"] == "confirmed"
                        else "durable_runtime_admission_denied")
                return

    def _coordinate(self):
        while not self._stop.is_set():
            try:
                self._collect()
                capability = self.runtime.process_resource_capability
                with self._lock:
                    active = len(self._active)
                    budget = self.options.memory_budget_bytes
                    if budget is None:
                        budget = self.options.capacity * self.options.memory_limit_bytes
                    if self._executor_unavailable:
                        self._admission_state = "executor_unavailable"
                    elif not capability.get("supported"):
                        self._admission_state = "resource_enforcement_unsupported"
                    elif active >= self.options.capacity:
                        self._admission_state = ("cleanup_pending" if self._finished
                                                 else "capacity_shortage")
                    elif budget - active*self.options.memory_limit_bytes < self.options.memory_limit_bytes:
                        self._admission_state = "memory_shortage"
                    else:
                        self._admission_state = "ready"
                if self._admission_state == "ready":
                    if not self.inbox.has_unsettled(_SOURCE):
                        with self._lock:
                            self._empty_polls += 1
                        self._stop.wait(self.options.poll_interval)
                        continue
                    # Shortage does not claim a notice or spend its retry budget.
                    with self._lock:
                        self._claim_calls += 1
                    claim_started = time.monotonic()
                    lease = self.inbox.claim(self._owner, source_id=_SOURCE,
                        lease_seconds=self.options.budget_seconds + self._dispatcher.callback_lease_seconds)
                    if lease is not None:
                        with self._lock:
                            if lease.notification_id in self._active:
                                # An expired receipt does not authorize another
                                # execution of an already active command.
                                raise _AdmissionError("supervisor_receipt_inflight",
                                                      "original handler still owns execution capacity")
                            assert self._executor is not None
                            self._ownership[lease.notification_id] = {
                                "execution_id": self.identities(lease.notification_id)[1],
                                "attempt": None, "fence": None, "state": "not_invoked", "source": "scheduler",
                                "delivery_deadline": claim_started+self.options.budget_seconds+
                                    self._dispatcher.callback_lease_seconds}
                            if lease.notification_id in self._cleanup_proofs:
                                self._ownership[lease.notification_id].update(self._cleanup_proofs[lease.notification_id])
                            self._ownership[lease.notification_id]["delivery_deadline"] = (
                                claim_started+self.options.budget_seconds+
                                self._dispatcher.callback_lease_seconds)
                            accepted = {"value": False}

                            def dispatch_owned(current_lease=lease, marker=accepted):
                                with self._lock:
                                    if not marker["value"]:
                                        return
                                self._handle(current_lease)

                            try:
                                # CPython may enqueue before thread creation
                                # raises. Such a WorkItem owns no SDK admission.
                                future = self._executor.submit(dispatch_owned)
                                self._active[lease.notification_id] = future
                                accepted["value"] = True
                            except BaseException as error:
                                self._ownership.pop(lease.notification_id, None)
                                self._executor_unavailable = True
                                self._executor_error = _error(error)
                                self._admission_state = "executor_unavailable"
                                try:
                                    self._executor.shutdown(wait=False, cancel_futures=True)
                                except BaseException as shutdown_error:
                                    self._executor_shutdown_error = _error(shutdown_error)
                                raise
                            self._peak_active = max(self._peak_active, len(self._active))
            except Exception as error:
                with self._lock:
                    self._last_error = _error(error)
                    self._admission_state = ("executor_unavailable" if self._executor_unavailable
                                             else "admission_error")
            self._stop.wait(self.options.poll_interval)

    def _admission_context(self, lease):
        """Freeze original durable notice/source bounds before authority retry."""
        from pathlib import Path
        from .._inspection import InspectionBudget
        from ..execution_kernel.budget import BudgetEnvelope, sample_clock
        budget = InspectionBudget(self._storage_timeout, None)
        connection = sqlite3.connect(Path(self.inbox.db_path).as_uri()+"?mode=ro", uri=True,
                                     timeout=budget.sqlite_timeout_seconds)
        connection.row_factory = sqlite3.Row
        try:
            budget.install(connection)
            connection.execute("BEGIN")
            record = connection.execute("SELECT created_at FROM notification_inbox_messages "
                "WHERE source_id=? AND notification_id=? AND lease_id=? AND fence=? AND state='processing'",
                (_SOURCE, lease.notification_id, lease.lease_id, lease.fence)).fetchone()
            if record is None:
                raise _AdmissionError("supervisor_receipt_stale", "original delivery no longer owns its receipt")
            existing = connection.execute("SELECT state FROM kernel_executions WHERE execution_id=?",
                (self.identities(lease.notification_id)[1],)).fetchone()
            if existing is not None and existing["state"] not in {"queued", "leased", "running"}:
                clock = connection.execute("SELECT value FROM notification_inbox_clock WHERE id=1").fetchone()[0]
                remaining = max(0., lease.expires_at-clock)
                return {"native_deadline": time.monotonic()+remaining, "result_only": True,
                        "record": {"created_at": record["created_at"], "payload": lease.payload},
                        "capture": None, "pending_owner": None, "envelope": None}
            target = lease.payload.get("execution_id") if type(lease.payload) is dict else None
            row = connection.execute("SELECT CASE WHEN length(CAST(envelope_json AS BLOB))<=? "
                "THEN envelope_json END AS envelope FROM kernel_execution_limits WHERE execution_id=?",
                (self.runtime.observation_options.query_bytes, target)).fetchone()
            budget.check()
            if row is None or row["envelope"] is None:
                raise _AdmissionError("supervisor_budget_unknown", "original source envelope cannot be inspected")
            envelope = BudgetEnvelope.from_dict(json.loads(row["envelope"]))
            view = envelope.view(sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
            budget.check()
            if view.remaining_work_seconds is None or view.observed_at is None:
                raise _AdmissionError("supervisor_budget_unknown", "original source clock continuity is unknown")
            remaining = min(view.remaining_work_seconds,
                record["created_at"]+self.options.budget_seconds-view.observed_at)
            control = connection.execute("SELECT deadline_at FROM kernel_run_controls WHERE run_id=?",
                (self.identities(lease.notification_id)[0],)).fetchone()
            if control is not None:
                remaining = min(remaining, control["deadline_at"]-view.observed_at)
            if remaining <= 0:
                raise _AdmissionError("supervisor_budget_exhausted", "original notice/source work deadline elapsed")
            return {"native_deadline": time.monotonic()+remaining, "result_only": False,
                    "record": {"created_at": record["created_at"], "payload": lease.payload},
                    "capture": None, "pending_owner": None, "envelope": envelope}
        finally:
            connection.close()

    @staticmethod
    def _retryable_admission(error):
        from ..execution_kernel.budget import BudgetClockUnknownError
        return (ManagedStallSupervisor._contention(error) or
                isinstance(error, BudgetClockUnknownError) and str(error) == "budget_clock_sample_unresolved:sampling" or
                isinstance(error, TimeoutError) and str(error) in {
                    "Kernel control admission budget elapsed", "Kernel control lock admission timed out",
                    "child lifecycle admission timed out", "budget capture exhausted its original native window",
                    "budget capture owner admission timed out"})

    def _admit(self, operation, admission):
        while not self._stop.is_set():
            remaining = admission["native_deadline"]-time.monotonic()
            if remaining <= 0:
                raise _AdmissionError("supervisor_budget_exhausted", "original admission deadline elapsed")
            try:
                pending = admission["pending_owner"]
                if pending is not None:
                    envelope = pending.finish_pending(admission["envelope"],
                        timeout_seconds=min(self._storage_timeout, remaining))
                    admission["envelope"] = admission["envelope"].with_clock_floor(envelope.checkpoint)
                    admission["pending_owner"] = None
                return operation()
            except Exception as error:
                owner = getattr(error, "budget_sample_owner", None)
                if owner is not None:
                    admission["pending_owner"] = owner
                captured = getattr(error, "budget_sample_envelope", None)
                if captured is not None and admission["envelope"] is not None:
                    admission["envelope"] = admission["envelope"].with_clock_floor(captured.checkpoint)
                with self._lock:
                    self._last_error = _error(error)
                remaining = admission["native_deadline"]-time.monotonic()
                if not self._retryable_admission(error) or remaining <= 0:
                    raise  # Retain the actual last cause, never relabel it as success.
                self._stop.wait(min(self.options.poll_interval, remaining))
        raise _AdmissionError("supervisor_stopping", "reserved handler admission stopped")

    def _initial_deadline(self, record, admission=None):
        from ..execution_kernel.budget import BudgetEnvelope, sample_clock
        from ..execution_kernel.budget_capture import _KernelBudgetCapture
        payload = record["payload"]
        if type(payload) is not dict or payload.get("kind") != "stalled":
            raise _AdmissionError("invalid_stall_notice", "expected a durable stall notification")
        target_id = payload.get("execution_id")
        if type(target_id) is not str:
            raise _AdmissionError("supervisor_budget_unknown", "notification has no execution budget identity")
        with self.runtime.kernel._control_lock(self._storage_timeout):
            snapshot = self.runtime.kernel.get(target_id)
        if (snapshot.attempt, snapshot.fence) != (payload.get("attempt"), payload.get("fence")):
            raise _AdmissionError("stale_stall_notice", "notification belongs to another execution attempt")
        if snapshot.state != "running":
            raise _AdmissionError("stale_stall_notice", "monitored execution no longer permits new handler work")
        limits = self.runtime.kernel.get_execution_limits(target_id, timeout_seconds=self._storage_timeout)
        if (limits is None or limits.get("entry_state") != "confirmed"
                or (limits.get("entry_attempt"), limits.get("entry_fence")) != (snapshot.attempt, snapshot.fence)):
            raise _AdmissionError("supervisor_budget_unknown", "monitored handler has no confirmed budget")
        kernel_envelope = BudgetEnvelope.from_dict(limits["envelope"])
        # Current elapsed projection preserves queue residence without observing
        # a new forward wall sample before the durable sampling guard is armed.
        prior_view = kernel_envelope.view(sample=sample_clock(wall_time=kernel_envelope.checkpoint.wall_at))
        if prior_view.remaining_work_seconds is None or prior_view.observed_at is None:
            raise _AdmissionError("supervisor_budget_unknown", "original execution work budget cannot be admitted")
        if prior_view.remaining_work_seconds <= 0:
            raise _AdmissionError("supervisor_budget_exhausted", "original execution permits no new handler work")
        remaining = min(self.options.budget_seconds, prior_view.remaining_work_seconds,
                        record["created_at"] + self.options.budget_seconds - prior_view.observed_at)
        if admission is not None:
            admission["native_deadline"] = min(admission["native_deadline"], time.monotonic()+remaining)
            remaining = min(remaining, admission["native_deadline"]-time.monotonic())
        if remaining <= 0:
            raise _AdmissionError("supervisor_budget_exhausted", "original notice deadline elapsed")
        if admission is None:
            capture = _KernelBudgetCapture(self.runtime.kernel, target_id)
        else:
            if admission["capture"] is None:
                admission["capture"] = _KernelBudgetCapture(self.runtime.kernel, target_id)
            capture = admission["capture"]
        envelope = capture(kernel_envelope, timeout_seconds=min(self._storage_timeout, remaining))
        view = envelope.view(sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
        if (view.clock_status != "trusted" or view.remaining_work_seconds is None
                or view.observed_at is None or view.effective_work_deadline_at is None):
            raise _AdmissionError("supervisor_budget_unknown", "original clock continuity cannot be established")
        if view.remaining_work_seconds <= 0:
            raise _AdmissionError("supervisor_budget_exhausted", "original execution permits no new handler work")
        now = view.observed_at
        # Mapping the retained remaining bound onto Kernel logical time keeps a
        # stronger parent checkpoint even if raw wall time has rolled back.
        deadline = min(record["created_at"] + self.options.budget_seconds,
                       view.effective_work_deadline_at,
                       now + view.remaining_work_seconds)
        if not math.isfinite(deadline) or deadline <= now:
            raise _AdmissionError("supervisor_budget_exhausted", "original notice work deadline elapsed")
        remaining = min(deadline-now, view.remaining_work_seconds)
        if admission is not None:
            admission["envelope"] = envelope
            admission["native_deadline"] = min(admission["native_deadline"], time.monotonic()+remaining)
            remaining = min(remaining, admission["native_deadline"]-time.monotonic())
        return deadline, snapshot.lease, envelope, remaining

    @staticmethod
    def _projected_time(envelope):
        from ..execution_kernel.budget import sample_clock
        view = envelope.view(sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
        if view.observed_at is None:
            raise _AdmissionError("supervisor_budget_unknown", "original elapsed continuity is unavailable")
        return view.observed_at

    def _enroll(self, lease, *, admission=None):
        from ..execution_kernel import ExecutionNotFoundError, RetryPolicy
        kernel = self.runtime.kernel
        run_id, execution_id = self.identities(lease.notification_id)
        with kernel._control_lock(self._storage_timeout):
            control = kernel.get_run_control(run_id)
            try:
                snapshot = kernel.get(execution_id)
            except ExecutionNotFoundError:
                snapshot = None
            if snapshot is not None:
                return snapshot, control
        record = self.inbox.get(_SOURCE, lease.notification_id) if admission is None else admission["record"]
        deadline, parent_lease, parent_budget, remaining = self._initial_deadline(record, admission)
        attempt_timeout = min(self._storage_timeout, remaining)
        with kernel._control_lock(attempt_timeout):
            # Another reserved scheduler may have committed the same identity.
            control = kernel.get_run_control(run_id)
            try:
                snapshot = kernel.get(execution_id)
            except ExecutionNotFoundError:
                snapshot = None
            if snapshot is not None:
                return snapshot, control
            if control is None:
                control = kernel.register_run_control(run_id, max_claims=1, deadline_at=deadline)
            if control["deadline_at"] <= self._projected_time(parent_budget):
                raise _AdmissionError("supervisor_budget_exhausted", "original controller deadline elapsed")
            if control["state"] == "paused" and control["control_epoch"] == 0:
                control = kernel.set_run_control(run_id, expected_epoch=0, state="active", generation=0)
            if control["state"] != "active":
                raise _AdmissionError("supervisor_control_closed", "controller Run is not active")
            command = self.runtime.command(_HANDLER, execution_id=execution_id,
                idempotency_key=execution_id, correlation_id=run_id,
                causation_id=lease.payload.get("execution_id"), payload=lease.payload,
                timeout_seconds=min(self.options.timeout_seconds,
                                    control["deadline_at"] - self._projected_time(parent_budget)),
                retry_policy=RetryPolicy(max_attempts=1))
            return kernel._submit_supervisor(command, run_id=run_id, generation=control["generation"],
                parent_lease=parent_lease, budget_envelope=parent_budget,
                timeout_seconds=attempt_timeout), control

    def _handle(self, lease):
        try:
            if self._stop.is_set():
                return
            admission = self._admission_context(lease)
            with self._lock:
                self._admissions[lease.notification_id] = admission
                delivery_deadline = self._ownership[lease.notification_id]["delivery_deadline"]
            snapshot, control = self._admit(lambda: self._enroll(lease, admission=admission), admission)
            if admission["result_only"] and snapshot.state in {"queued", "leased", "running"}:
                raise _AdmissionError("supervisor_result_changed", "factual replay cannot admit new handler work")
            while snapshot.state in {"queued", "leased", "running"} and not self._stop.is_set():
                if snapshot.state == "queued":
                    from ..execution_kernel.budget import BudgetEnvelope
                    limits = self._admit(lambda: self.runtime.kernel.get_execution_limits(
                        snapshot.execution_id, timeout_seconds=self._storage_timeout), admission)
                    if limits is None:
                        raise _AdmissionError("supervisor_budget_unknown", "reserved execution has no inherited budget")
                    now = self._projected_time(BudgetEnvelope.from_dict(limits["envelope"]))
                    if control is None or control["deadline_at"] <= now:
                        raise _AdmissionError("supervisor_budget_exhausted", "original controller deadline elapsed")
                    with self._lock:
                        self._ownership[lease.notification_id].update(state="unknown")
                    returned = self._admit(lambda: self.runtime.run_once(execution_id=snapshot.execution_id), admission)
                    if returned is None:
                        current = self._admit(lambda: self._read_execution(snapshot.execution_id), admission)
                        snapshot = current
                        if current.attempt == 0:
                            with self._lock:
                                self._ownership[lease.notification_id].update(state="not_invoked")
                        self._stop.wait(self.options.poll_interval)
                    else:
                        # This is the actual Runtime result, including retained
                        # settlement. Never dispatch again to obtain a receipt.
                        snapshot = returned
                else:
                    self._stop.wait(self.options.poll_interval)
                    snapshot = self._read_factual(lambda: self._read_execution(snapshot.execution_id),
                        delivery_deadline)
            if self._stop.is_set():
                return
            self._restore_cleanup(lease.notification_id, snapshot)
            if snapshot.state == "succeeded" and snapshot.result is not None:
                self._settle(lease, succeeded=True)
            else:
                error = _AdmissionError("supervisor_handler_failed", "canonical controller result is not successful")
                facts = _error(error)
                facts.update(execution_id=snapshot.execution_id, state=snapshot.state,
                             result_id=None if snapshot.result is None else snapshot.result.result_id,
                             error_code=None if snapshot.result is None or snapshot.result.error is None
                                 else snapshot.result.error.code)
                self._settle(lease, succeeded=False, facts=facts)
        except Exception as error:
            if "snapshot" in locals():
                try:
                    with self.runtime.kernel._control_lock(self._storage_timeout):
                        current = self.runtime.kernel.get(snapshot.execution_id)
                    if current.attempt == 0:
                        with self._lock:
                            self._ownership[lease.notification_id].update(state="not_invoked")
                except Exception:
                    pass  # Missing authority facts cannot prove process release.
            with self._lock:
                self._last_error = _error(error)
            try:
                self._settle(lease, succeeded=False, facts=_error(error))
            except Exception as settlement_error:
                with self._lock:
                    self._last_error = {**_error(error), "receipt_settlement_error": _error(settlement_error)}

    def _read_execution(self, execution_id):
        with self.runtime.kernel._control_lock(self._storage_timeout):
            return self.runtime.kernel.get(execution_id)

    def _read_factual(self, operation, deadline):
        """Retry an existing result read within the original delivery lease."""
        while not self._stop.is_set():
            try:
                return operation()
            except Exception as error:
                remaining = deadline-time.monotonic()
                if not self._retryable_admission(error) or remaining <= 0:
                    raise
                with self._lock:
                    self._last_error = _error(error)
                self._stop.wait(min(self.options.poll_interval, remaining))
        raise _AdmissionError("supervisor_stopping", "factual result inspection stopped")

    @staticmethod
    def _contention(error):
        if not isinstance(error, sqlite3.OperationalError):
            return False
        code = getattr(error, "sqlite_errorcode", None)
        if code is not None:
            return code & 255 in (5, 6)
        # Python 3.10 omits SQLite's structured error attributes.
        return str(error).lower() in {"database is locked", "database table is locked",
                                     "database schema is locked"}

    def _settle(self, lease, *, succeeded, facts=None):
        """Retry only receipt persistence within the original delivery lease.

        The canonical handler result is already fixed. This performs no handler
        invocation and cannot grant a new execution or receipt deadline.
        """
        while not self._stop.is_set():
            try:
                # A prior COMMIT may have completed before an error was raised.
                # Read its original durable receipt instead of replaying work.
                record = self.inbox.get(_SOURCE, lease.notification_id)
                if record["state"] == "consumed":
                    with self._lock:
                        self._cleanup_proofs.pop(lease.notification_id, None)
                    return
                if record["fence"] != lease.fence or record["lease_id"] != lease.lease_id:
                    return  # The durable receipt no longer belongs to this owner.
                if succeeded:
                    settled = self.inbox.consume(lease)
                else:
                    settled = self.inbox.fail(lease, error=facts,
                                             retry_delay=self._dispatcher.callback_retry_delay)
                if settled["state"] in {"consumed", "dead"}:
                    with self._lock:
                        self._cleanup_proofs.pop(lease.notification_id, None)
                return
            except Exception as error:
                with self._lock:
                    self._last_error = _error(error)
                if not self._contention(error) and not (isinstance(error, TimeoutError)
                        and str(error) == "managed inbox transaction admission elapsed"):
                    raise
                with self._lock:
                    remaining = self._ownership[lease.notification_id]["delivery_deadline"]-time.monotonic()
                if remaining <= 0:
                    raise
                self._stop.wait(min(self.options.poll_interval, remaining))

    @staticmethod
    def _report_size(report, budget, maximum):
        size = 0
        for chunk in json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).iterencode(report):
            budget.check()
            size += len(chunk.encode("utf-8"))
            if size > maximum:
                return size
        budget.check()
        return size

    def status(self, notification_id=None, *, budget=None):
        from .._inspection import InspectionBudget
        if budget is None:
            budget = InspectionBudget(self.runtime.observation_options.query_timeout, None)
        maximum = self.runtime.observation_options.query_bytes
        budget.check()
        if not self._lock.acquire(timeout=budget.sqlite_timeout_seconds):
            raise TimeoutError("managed status lock admission timed out")
        try:
            budget.check()
            active = len(self._active)
            known_pending, checkpoint_unknown = 0, False
            for key, owned in self._ownership.items():
                admission = self._admissions.get(key)
                local_pending = admission is not None and any(getattr(owner, "_pending", None) is not None
                    for owner in (admission["capture"], admission["pending_owner"]))
                registry_pending = self.runtime.kernel._budget_sample_status(owned["execution_id"])
                if local_pending or registry_pending is True:
                    known_pending += 1
                elif registry_pending is None:
                    checkpoint_unknown = True
                budget.check()
            report = {"mode": "managed_handler", "admission_state": self._admission_state,
                "capacity": self.options.capacity, "active": active, "peak_active": self._peak_active,
                "reserved_memory_bytes": active*self.options.memory_limit_bytes,
                "memory_limit_bytes": self.options.memory_limit_bytes,
                "memory_budget_bytes": self.options.memory_budget_bytes if self.options.memory_budget_bytes is not None
                    else self.options.capacity*self.options.memory_limit_bytes,
                "resource_capability": dict(self.runtime.process_resource_capability),
                "completed": self._completed, "last_error": deepcopy(self._last_error),
                "empty_polls": self._empty_polls, "claim_calls": self._claim_calls,
                "executor_unavailable": self._executor_unavailable,
                "executor_error": deepcopy(self._executor_error),
                "executor_shutdown_error": deepcopy(self._executor_shutdown_error),
                "cleanup_ownership": [dict(item) for _, item in zip(range(maximum//8192), self._ownership.values())],
                "cleanup_ownership_count": len(self._ownership),
                "cleanup_proof_evictions": self._cleanup_proof_evictions,
                "budget_checkpoint_pending": None if checkpoint_unknown else known_pending,
                "budget_checkpoint_known_pending": known_pending,
                "budget_checkpoint_state": "unknown" if checkpoint_unknown else "pending" if known_pending else "clear",
                "coordinator_alive": self._thread is not None and self._thread.is_alive(),
                "closing": self._stop.is_set(), "closed": self._close_done.is_set() and self._close_error is None,
                "cleanup_pending": bool(self._finished) or
                    (self._close_thread is not None and not self._close_done.is_set())}
        finally:
            self._lock.release()
        report["complete"] = (len(report["cleanup_ownership"]) == report["cleanup_ownership_count"]
                              and not checkpoint_unknown)
        if checkpoint_unknown:
            report["unknown_reason"] = "budget_checkpoint_registry_unavailable"
        if notification_id is not None:
            from pathlib import Path
            run_id, execution_id = self.identities(notification_id)
            # Original durable facts remain inspectable when independent
            # Host cleanup has already closed its business Kernel connection.
            kernel = self.runtime.kernel
            # Inspect sizes before loading any command, result or notice JSON.
            # Escaping may expand raw text sixfold; reserve space for metadata.
            record_bytes = max(0, (maximum-self._report_size(report, budget, maximum)-2048)//12)
            connection = sqlite3.connect(Path(self.inbox.db_path).as_uri()+"?mode=ro", uri=True,
                                         timeout=budget.sqlite_timeout_seconds)
            connection.row_factory = sqlite3.Row
            try:
                budget.install(connection)
                connection.execute("BEGIN")
                row = connection.execute("SELECT run_id,control_epoch,generation,state,max_claims,claims_used,deadline_at "
                    "FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone()
                if row is None:
                    control = None
                else:
                    control = kernel._run_control_value(row)
                    marker = connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(execution_id AS BLOB))),0) "
                        "FROM kernel_managed_executions WHERE run_id=? AND drain_allowed=1", (run_id,)).fetchone()
                    budget.check()
                    if marker[1]+marker[0]*3 > record_bytes:
                        control.update(drain_execution_ids=None, truncated=True,
                            unknown_reason="managed_status_byte_limit")
                    else:
                        control["drain_execution_ids"] = tuple(item[0] for item in connection.execute(
                            "SELECT execution_id FROM kernel_managed_executions "
                            "WHERE run_id=? AND drain_allowed=1 ORDER BY execution_id", (run_id,)))
                        budget.check()
                marker = connection.execute("SELECT execution_id,state,attempt,fence,revision,"
                    "length(CAST(command_json AS BLOB))+COALESCE(length(CAST(result_json AS BLOB)),0)"
                    "+COALESCE(length(CAST(recovery_reason AS BLOB)),0) AS bytes "
                    "FROM kernel_executions WHERE execution_id=?", (execution_id,)).fetchone()
                budget.check()
                if marker is None:
                    snapshot = None
                elif marker["bytes"] > record_bytes:
                    snapshot = {**{key: marker[key] for key in marker.keys() if key != "bytes"},
                                "command": None, "result": None, "truncated": True,
                                "unknown_reason": "managed_status_byte_limit"}
                else:
                    snapshot = kernel._snapshot(kernel._get_row(connection, execution_id)).to_dict()
                    budget.check()
            finally:
                connection.close()
            receipt = self.inbox.inspect_record(_SOURCE, notification_id, budget=budget, max_bytes=record_bytes)
            report.update(notification_id=notification_id, execution_id=execution_id,
                          run_control=control, execution=snapshot,
                          receipt=receipt)
            budget.check()
        if len(report["cleanup_ownership"]) != report["cleanup_ownership_count"] or any(
                isinstance(report.get(key), dict) and report[key].get("truncated")
                                         for key in ("execution", "receipt", "run_control")):
            report.update(complete=False, truncated=True, unknown_reason="managed_status_byte_limit")
        for key in ("cleanup_ownership", "last_error", "executor_error", "executor_shutdown_error",
                    "execution", "receipt", "run_control",
                    "notification_id", "execution_id", "resource_capability"):
            if self._report_size(report, budget, maximum) <= maximum:
                break
            if key in report:
                report[key] = ([] if key == "cleanup_ownership" else None if key in {
                    "last_error", "executor_error", "executor_shutdown_error", "notification_id", "execution_id"}
                    else {"truncated": True, "unknown_reason": "managed_status_byte_limit"})
                report.update(complete=False, truncated=True, unknown_reason="managed_status_byte_limit")
        budget.check()
        return report

    def _finish_close(self):
        try:
            self.runtime.request_stop()
            if self._thread is not None:
                self._thread.join()
            if self._executor is not None:
                self._executor.shutdown(wait=True)
            self._collect()
            with self._lock:
                checkpoint_pending = any(any(getattr(owner, "_pending", None) is not None
                    for owner in (item["capture"], item["pending_owner"]))
                    for item in self._admissions.values())
            if checkpoint_pending:
                raise _AdmissionError("supervisor_checkpoint_pending",
                                      "original reserved admission checkpoint remains pending")
            self.runtime.close()
            self._collect()
            with self._lock:
                if self._ownership:
                    raise _AdmissionError("supervisor_cleanup_unknown",
                                          "reserved execution cleanup remains unconfirmed")
            self.inbox.close()
        except BaseException as error:
            with self._lock:
                self._close_error = error
        finally:
            self._close_done.set()

    def close(self, *, timeout: float):
        deadline = time.monotonic() + timeout
        with self._lock:
            self._stop.set()
            if self._close_thread is None or (self._close_done.is_set() and self._close_error is not None):
                self._close_done.clear()
                self._close_error = None
                self._close_thread = threading.Thread(target=self._finish_close,
                    name="dispatcher-managed-stalls-close", daemon=True)
                self._close_thread.start()
        if not self._close_done.wait(max(0., deadline-time.monotonic())):
            raise TimeoutError("managed stall handler cleanup remains pending; retry close")
        if self._close_error is not None:
            raise self._close_error
