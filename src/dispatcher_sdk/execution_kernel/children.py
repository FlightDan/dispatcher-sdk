"""Durable parent waits backed by a separate, fixed child execution pool.

The journal records admission before touching Kernel storage. Kernel submission
and adoption validate the parent fence again, making partial registration
recoverable without claiming a transaction across the two databases. Capacity
counts unresolved execution requests, including requests left by a crashed
service. Nothing in this module releases a live parent's memory reservation.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import contextmanager, nullcontext
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterator, Mapping, Protocol
import uuid

from .._inspection import InspectionBudgetExceeded
from .._sqlite_errors import is_sqlite_contention
from .budget import BudgetEnvelope, BudgetClockUnknownError, sample_clock
from .contracts import ExecutionCommandV2, ExecutionLease, RetryPolicy
from .errors import ExecutionNotFoundError, StaleFenceError, InvalidStateTransitionError


CHILD_SCHEMA = """
CREATE TABLE sdk_child_requests (
 source_id TEXT NOT NULL, parent_execution_id TEXT NOT NULL,
 request_id TEXT NOT NULL, parent_attempt INTEGER NOT NULL, parent_fence INTEGER NOT NULL,
 parent_lease_json TEXT NOT NULL, child_execution_id TEXT NOT NULL,
 depth INTEGER NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL,
 command_json TEXT, budget_json TEXT NOT NULL, wait_id TEXT NOT NULL,
 created_at REAL NOT NULL, updated_at REAL NOT NULL,
 response_json TEXT, error_json TEXT, service_owner TEXT, owner_expires_at REAL,
 PRIMARY KEY(source_id,parent_execution_id,request_id));
CREATE INDEX sdk_child_requests_work ON sdk_child_requests(source_id,state,owner_expires_at);
CREATE INDEX sdk_child_requests_target ON sdk_child_requests(source_id,child_execution_id,state);
CREATE TABLE sdk_child_waits (
 source_id TEXT NOT NULL, wait_id TEXT NOT NULL,
 parent_execution_id TEXT NOT NULL, parent_attempt INTEGER NOT NULL, parent_fence INTEGER NOT NULL,
 target_execution_id TEXT NOT NULL, reason TEXT NOT NULL, started_at REAL NOT NULL,
 deadline_at REAL NOT NULL, state TEXT NOT NULL, updated_at REAL NOT NULL,
 error_json TEXT, PRIMARY KEY(source_id,wait_id));
CREATE INDEX sdk_child_waits_graph ON sdk_child_waits(source_id,parent_execution_id,state);
"""

_OPEN = ("pending", "running")
_TERMINAL = {"succeeded", "failed", "timed_out", "cancelled", "dead"}
_MAX_GRAPH_NODES = 256
_MAX_RECORD_BYTES = 256 * 1024


def _transient_control_error(error: Exception) -> bool:
    if (isinstance(error, BudgetClockUnknownError)
            and str(error) == "budget_clock_sample_unresolved:sampling"):
        # Wait for a live owner's publication within the original child window.
        # This does not clear its marker or permit business while it is pending.
        return True
    if isinstance(error, InspectionBudgetExceeded):
        # This expires one read attempt, not the original child wait window.
        return True
    if is_sqlite_contention(error):
        return True
    from ..observability.journal import _ObservationWriteBudgetExceeded
    if isinstance(error, _ObservationWriteBudgetExceeded):
        return error.rollback_confirmed
    return isinstance(error, TimeoutError) and str(error) in (
        "Kernel control lock admission timed out", "Kernel control admission budget elapsed",
        "child lifecycle admission timed out", "observation schema admission budget elapsed",
        "budget capture owner admission timed out", "budget capture exhausted its original native window")


def _merge_checkpoint(envelope, checkpoint):
    return envelope.with_clock_floor(checkpoint)


class _RetryWindow:
    """One conservative work window, retained across every storage replay."""

    def __init__(self, envelope: BudgetEnvelope, kernel: Any, stop=None, *, execution_id=None):
        self.envelope, self.kernel, self.stop = envelope, kernel, stop
        self.execution_id = execution_id or next((item.origin_id[len("execution:"):]
            for item in reversed(envelope.constraints) if item.source == "execution"
            and item.origin_id.startswith("execution:")), None)
        self.on_advance = None
        self._projecting = False
        self.deadline = math.inf
        self._pending_sample = None
        self._pending_sample_owner = None
        self._pending_sample_error = None
        self._capture = None
        self._delivery_deadline = None
        if hasattr(kernel, "_sample_budget") and self.execution_id is not None:
            from .budget_capture import _KernelBudgetCapture
            self._capture = _KernelBudgetCapture(kernel, self.execution_id)
        remaining = self.remaining()
        check_clock = getattr(kernel, "_assert_budget_clock", None)
        if remaining <= 0 and self._capture is not None and check_clock is not None:
            # Expiry denies work, but cannot turn a foreign unresolved sample
            # into known clock authority. Only initial reconstruction needs
            # this bounded read; later projections stay free of I/O.
            with kernel._control_lock(.1):
                check_clock(kernel._connection, self.execution_id)

    def _project_elapsed(self):
        # Establish the native work cutoff before attempting any new sample.
        # This uses the retained floor, never a new authoritative wall reading.
        sample = sample_clock(wall_time=self.envelope.checkpoint.wall_at)
        self.envelope = self.envelope.recheckpoint(sample=sample)
        view = self.envelope.view(sample=self.envelope.checkpoint)
        if view.clock_status != "trusted" or view.remaining_work_seconds is None:
            raise BudgetClockUnknownError(view.unknown_reason or "child clock continuity cannot be established")
        self.deadline = min(self.deadline, time.monotonic() + view.remaining_work_seconds)
        return max(0., min(view.remaining_work_seconds, self.deadline - time.monotonic()))

    def _adopt_sample_owner(self, error):
        owner = getattr(error, "budget_sample_owner", None)
        if (owner is None or owner.kernel is not self.kernel
                or owner.execution_id != self.execution_id or owner._pending is None):
            return
        # Transfer the live helper, not a duplicate token retry authority.
        # Claim retries and this window now share the exact original obligation.
        self._pending_sample_owner = owner
        self._pending_sample = owner._pending
        self._pending_sample_error = error
        captured = self._pending_sample[1]
        if captured is not None:
            self.envelope = self.envelope.with_clock_floor(captured.checkpoint)

    def _resume_sample(self):
        # Publication retries belong to this exact live window and captured
        # token. They do not arm another sample or renew its work deadline.
        while self._pending_sample is not None:
            if self.stop is not None and self.stop.is_set():
                raise ChildExecutionError("child_service_closed", "child service stopped before response settlement")
            remaining = self._project_elapsed()
            if remaining <= 0:
                raise self._pending_sample_error
            token, captured = self._pending_sample
            if captured is None:
                raise self._pending_sample_error
            try:
                if self._pending_sample_owner is not None:
                    published = self._pending_sample_owner.finish_pending(
                        self.envelope, timeout_seconds=min(.1, remaining))
                else:
                    published = self.kernel._finish_budget_sample(
                        token, self.execution_id, captured, timeout_seconds=min(.1, remaining))
            except Exception as exc:
                exc.budget_sample_token = token
                exc.budget_sample_envelope = captured
                self._pending_sample_error = exc
                if not _transient_control_error(exc):
                    raise
                remaining = self._project_elapsed()
                if remaining <= 0:
                    raise
                if self.stop is None:
                    time.sleep(min(.005, remaining))
                else:
                    self.stop.wait(min(.005, remaining))
            else:
                self.envelope = self.envelope.with_clock_floor(published.checkpoint)
                self._pending_sample = self._pending_sample_error = self._pending_sample_owner = None

    def _raise_expired_capture(self, error):
        # This read only classifies uncertainty; it cannot grant fresh time.
        check_clock = getattr(self.kernel, "_assert_budget_clock", None)
        control_lock = getattr(self.kernel, "_control_lock", None)
        if check_clock is not None and control_lock is not None:
            try:
                with control_lock(.1):
                    check_clock(self.kernel._connection, self.execution_id)
            except Exception as proof_error:
                if (not isinstance(proof_error, BudgetClockUnknownError)
                        and _transient_control_error(proof_error)):
                    raise error from proof_error
                raise
        raise error

    def remaining(self) -> float:
        if self.stop is not None and self.stop.is_set():
            raise ChildExecutionError("child_service_closed", "child service stopped before response settlement")
        previous = self.envelope.checkpoint
        sampler = getattr(self.kernel, "_sample_budget", None)
        if sampler is not None and self.execution_id is not None and not self._projecting:
            remaining = self._project_elapsed()
            if self._pending_sample is not None:
                self._resume_sample()
            elif remaining > 0:
                while True:
                    try:
                        self.envelope = self._capture(
                            self.envelope, timeout_seconds=min(.1, remaining))
                    except Exception as exc:
                        token = getattr(exc, "budget_sample_token", None)
                        captured = getattr(exc, "budget_sample_envelope", None)
                        waiting_owner = (isinstance(exc, BudgetClockUnknownError)
                            and str(exc) == "budget_clock_sample_unresolved:sampling")
                        if token is not None:
                            self._pending_sample_owner = getattr(exc, "budget_sample_owner", self._capture)
                            self._pending_sample = (token, captured)
                            self._pending_sample_error = exc
                            if captured is None or not _transient_control_error(exc):
                                raise
                            self.envelope = self.envelope.with_clock_floor(captured.checkpoint)
                            self._resume_sample()
                        elif waiting_owner:
                            # No business is admitted while another sampler's
                            # floor remains unpublished. Waiting spends this
                            # original call window and cannot clear its token.
                            remaining = self._project_elapsed()
                            if remaining <= 0 or (self.stop is not None and self.stop.is_set()):
                                raise
                            if self.stop is None:
                                time.sleep(min(.005, remaining))
                            else:
                                self.stop.wait(min(.005, remaining))
                            continue
                        elif not _transient_control_error(exc):
                            raise
                        else:
                            # Admission may expire before ancestry is checked.
                            # Cached time cannot prove absence of a foreign
                            # captured floor; retry within this original window.
                            remaining = self._project_elapsed()
                            if remaining <= 0:
                                self._raise_expired_capture(exc)
                            read_floor = getattr(self.kernel, "_read_budget_floor", None)
                            if read_floor is not None:
                                try:
                                    checkpoint = read_floor(self.execution_id,
                                        timeout_seconds=min(.1, remaining))
                                except Exception as proof_error:
                                    if not _transient_control_error(proof_error):
                                        raise
                                    if isinstance(proof_error, BudgetClockUnknownError):
                                        # Preserve the precise foreign-guard
                                        # refusal if the original window expires.
                                        exc = proof_error
                                else:
                                    self.envelope = self.envelope.with_clock_floor(checkpoint)
                                    break
                            if self.stop is not None and self.stop.is_set():
                                raise ChildExecutionError("child_service_closed",
                                    "child service stopped before response settlement") from exc
                            if self.stop is None:
                                time.sleep(min(.005, remaining))
                            else:
                                self.stop.wait(min(.005, remaining))
                            remaining = self._project_elapsed()
                            if remaining <= 0:
                                self._raise_expired_capture(exc)
                            if self.stop is not None and self.stop.is_set():
                                raise ChildExecutionError("child_service_closed",
                                    "child service stopped before response settlement") from exc
                            continue
                    break
            self._project_elapsed()
            sample = self.envelope.checkpoint
        else:
            wall = (self.envelope.checkpoint.wall_at if self._projecting else
                    self.kernel._wall_time() if hasattr(self.kernel, "_wall_time") else None)
            sample = sample_clock(wall_time=wall)
            self.envelope = self.envelope.recheckpoint(sample=sample)
        view = self.envelope.view(sample=sample)
        if view.clock_status != "trusted" or view.remaining_work_seconds is None:
            raise BudgetClockUnknownError(view.unknown_reason or "child clock continuity cannot be established")
        self.deadline = min(self.deadline, time.monotonic() + view.remaining_work_seconds)
        projected = previous.wall_at + sample.elapsed_at - previous.elapsed_at
        if self.on_advance is not None and self.envelope.checkpoint.wall_at > projected + .001:
            self.on_advance(self.envelope)
        return max(0., min(view.remaining_work_seconds, self.deadline - time.monotonic()))

    @contextmanager
    def project(self):
        """Use the just-guarded floor while an authority operation owns its lock."""
        previous, self._projecting = self._projecting, True
        try:
            yield
        finally:
            self._projecting = previous

    def timeout(self) -> float:
        remaining = self.remaining()
        if remaining <= 0:
            raise ChildExecutionError("child_wait_timeout", "child wait exhausted its inherited work window")
        return min(.1, remaining)


def _retry(window: _RetryWindow, operation, *, kernel=None, store=None):
    last_error = None
    while True:
        # The enclosing call already captured one durable clock floor. A read
        # or timeout calculation is not another independent wall observation.
        with window.project():
            remaining = window.remaining()
        if remaining <= 0:
            if last_error is not None:
                raise last_error
            raise ChildExecutionError("child_wait_timeout", "child wait exhausted its inherited work window")
        try:
            lock = getattr(kernel, "_control_lock", None)
            with lock(min(.1, remaining)) if lock is not None else nullcontext():
                with window.project():
                    with store.bound(window) if store is not None else nullcontext():
                        return operation()
        except Exception as exc:
            window._adopt_sample_owner(exc)
            if not _transient_control_error(exc):
                raise
            last_error = exc
            remaining = window.remaining()
            if remaining <= 0:
                raise
            if window.stop is None:
                time.sleep(min(.01, remaining))
            else:
                window.stop.wait(min(.01, remaining))


class ChildCalls(Protocol):
    """Public bounded child calls, including explicit service unavailability."""

    def run(self, handler_id: str, payload: Any, *, request_id: str,
            timeout_seconds: float = 300.0, handler_contract_version: int = 1) -> dict[str, Any]: ...

    def wait_for(self, execution_id: str, *, request_id: str,
                 timeout_seconds: float | None = None, reason: str = "child_result") -> dict[str, Any]: ...


class ChildExecutionError(RuntimeError):
    """A child admission/wait error, retaining its original execution result."""

    def __init__(self, code: str, message: str, *, execution_id: str | None = None,
                 result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.execution_id = execution_id
        self.result = result


def _identifier(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 1024:
        raise ValueError(f"{name} must be a nonempty string of at most 1024 characters")
    return value


def _positive(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be positive and finite")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _encode(value: Any) -> str:
    encoded = json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_RECORD_BYTES:
        raise ChildExecutionError("child_record_too_large", "child record exceeds its bounded journal capacity")
    return encoded


def _verify_parent(kernel: Any, lease: ExecutionLease) -> None:
    # Parent authority checks must not wait on SQLite's default 30-second
    # writer timeout while the caller's original work deadline keeps running.
    control_lock = getattr(kernel, "_control_lock", None)
    with control_lock(.1) if control_lock is not None else nullcontext():
        kernel.verify(lease)


def _inspect_parent_revocation(kernel: Any, lease: ExecutionLease) -> None:
    """Give known lease revocation precedence over reconstruction of its clock.

    This read grants no authority and creates no clock sample. An unavailable
    observation leaves the existing budget/entry checks fully responsible for
    admission; a genuinely live parent still encounters any unresolved guard.
    """
    inspect = getattr(kernel, "_verify_active_lease_readonly", None)
    if inspect is None:
        # Older custom Kernel implementations retain their existing checks.
        # Never substitute the writing business verify primitive here.
        return
    try:
        lock = getattr(kernel, "_control_lock", None)
        with lock(.1) if lock is not None else nullcontext():
            inspect(lease)
    except (StaleFenceError, InvalidStateTransitionError, ExecutionNotFoundError) as exc:
        raise ChildExecutionError("parent_authority_revoked", str(exc),
                                  execution_id=lease.execution_id) from exc
    except Exception as exc:
        if not _transient_control_error(exc):
            raise


def _wait_parent_entry(kernel: Any, lease: ExecutionLease, envelope: BudgetEnvelope,
                       stop: threading.Event | None = None, *, window=None) -> None:
    """Wait for the durable ACK within the worker's already captured work window."""
    window = window or _RetryWindow(envelope, kernel, stop, execution_id=lease.execution_id)
    while True:
        if stop is not None and stop.is_set():
            raise ChildExecutionError("child_service_closed", "child service stopped before parent entry confirmation")
        try:
            # A bounded authority read remains meaningful after work expiry;
            # it may prove cancellation before any new business admission.
            with window.project():
                expired = window.remaining() <= 0
            if expired:
                try:
                    _verify_parent(kernel, lease)
                except Exception as exc:
                    if not _transient_control_error(exc):
                        raise
            _retry(window, lambda: kernel.verify(lease), kernel=kernel)
        except ChildExecutionError as exc:
            if exc.code == "child_wait_timeout":
                raise ChildExecutionError("parent_entry_confirmation_timeout",
                    "parent entry confirmation exhausted its work deadline") from exc
            raise
        except (StaleFenceError, InvalidStateTransitionError, ExecutionNotFoundError) as exc:
            raise ChildExecutionError("parent_authority_revoked", str(exc), execution_id=lease.execution_id) from exc
        with window.project():
            window.remaining()
        view = window.envelope.view(sample=window.envelope.checkpoint)
        if view.clock_status != "trusted":
            raise BudgetClockUnknownError(view.unknown_reason)
        if view.remaining_work_seconds is None:
            raise ChildExecutionError("parent_budget_missing", "parent entry confirmation requires a finite work deadline")
        if view.remaining_work_seconds <= 0:
            raise ChildExecutionError("parent_entry_confirmation_timeout", "parent entry confirmation exhausted its work deadline")
        try:
            limits = _retry(window, lambda: kernel.get_execution_limits(lease.execution_id), kernel=kernel)
        except ChildExecutionError as exc:
            if exc.code == "child_wait_timeout":
                raise ChildExecutionError("parent_entry_confirmation_timeout",
                    "parent entry confirmation exhausted its work deadline") from exc
            raise
        if (limits is not None and limits.get("entry_state") == "confirmed"
                and (limits.get("entry_attempt"), limits.get("entry_fence")) == (lease.attempt, lease.fence)):
            return
        window.remaining()
        duration = min(.05, view.remaining_work_seconds)
        if stop is None:
            time.sleep(duration)
        else:
            stop.wait(duration)


class _Store:
    def __init__(self, journal: Any) -> None:
        self.journal = journal
        self.source_id = _identifier(journal.source_id, "source_id")
        self._local = threading.local()
        self._floors = {}
        self._floor_lock = threading.Lock()

    def _facts(self, *, writer=False, timeout_seconds=.1):
        kernel_path = getattr(self.journal, "kernel_path", None)
        if kernel_path is None:
            return None
        from .settlement import SettlementJournal
        path = str(kernel_path) + ".settlements.sqlite3"
        if not Path(path).exists():
            if writer:
                raise BudgetClockUnknownError("independent child budget checkpoint storage is unavailable")
            # Direct public capabilities may predate the optional receipt
            # store. Their original durable request remains usable; a known
            # failed forward-checkpoint write still fails explicitly above.
            return None
        factory = SettlementJournal if writer else SettlementJournal.open_readonly
        return factory(path, source_id=self.source_id, kernel_path=kernel_path,
                       timeout_seconds=timeout_seconds)

    def attach(self, row, window):
        """Carry stronger observed clocks through publication and reclamation."""
        from .settlement import SettlementBusyError

        def inspect_parent(timeout):
            lease_json = row.get("parent_lease_json")
            if lease_json is None:
                return
            lease = ExecutionLease.from_dict(json.loads(lease_json))
            try:
                lock = getattr(window.kernel, "_control_lock", None)
                with lock(timeout) if lock is not None else nullcontext():
                    window.kernel._verify_active_lease_readonly(lease)
            except (StaleFenceError, InvalidStateTransitionError, ExecutionNotFoundError) as exc:
                raise ChildExecutionError("parent_authority_revoked", str(exc),
                                          execution_id=lease.execution_id) from exc

        receipt_error: SettlementBusyError | None = None

        def read_receipt(operation):
            nonlocal receipt_error
            try:
                return operation()
            except SettlementBusyError as exc:
                receipt_error = exc
                raise
        try:
            while True:
                try:
                    with window.project():
                        remaining = window.remaining()
                    if remaining <= 0:
                        raise SettlementBusyError("child checkpoint inspection exhausted its original window")
                    deadline = time.monotonic() + min(.1, remaining)
                    facts = read_receipt(lambda: self._facts(timeout_seconds=min(.1, remaining)))
                    if facts is None:
                        report = None
                        break
                    with window.project():
                        duration = min(window.remaining(), deadline - time.monotonic())
                    if duration <= 0:
                        raise SettlementBusyError("child checkpoint inspection admission budget elapsed")
                    report = read_receipt(lambda: facts.inspect_notes(row["child_execution_id"], limit=50,
                                                 max_bytes=256*1024, timeout_seconds=duration))
                    truncated = report.get("truncated") or any(note.get("truncated") for note in report["notes"])
                    if (report.get("timed_out") and not truncated and
                            report.get("unknown_reason") == "settlement_notes_inspection_timeout"):
                        receipt_error = SettlementBusyError(report.get("error") or "child checkpoint inspection timed out")
                        raise receipt_error
                    if not report["complete"] or report.get("has_more") or truncated:
                        raise BudgetClockUnknownError("child budget checkpoint inspection is incomplete")
                    break
                except Exception as error:
                    if not (isinstance(error, SettlementBusyError) or _transient_control_error(error)):
                        raise
                    # Failed inspection admits no business. Project its
                    # retained floor so a terminal receipt error cannot be
                    # replaced by another sample/ACK past the original cutoff.
                    with window.project():
                        remaining = window.remaining()
                    # A spent business window still permits one bounded
                    # observation of known revocation. This never admits a
                    # receipt read, result rescue, or new child work.
                    try:
                        inspect_parent(min(.1, remaining) if remaining > 0 else .1)
                    except Exception as exc:
                        if not _transient_control_error(exc):
                            raise
                        if remaining <= 0:
                            if receipt_error is not None and receipt_error.__cause__ is not None:
                                receipt_error.original_receipt_cause = receipt_error.__cause__
                            if receipt_error is not None and error is not receipt_error:
                                error.parent_inspection_error = exc
                                raise receipt_error from error
                            raise error from exc
                    with window.project():
                        remaining = window.remaining()
                    if remaining <= 0:
                        if receipt_error is not None and error is not receipt_error:
                            if receipt_error.__cause__ is not None:
                                receipt_error.original_receipt_cause = receipt_error.__cause__
                            raise receipt_error from error
                        raise
                    if window.stop is None:
                        time.sleep(min(.01, remaining))
                    else:
                        window.stop.wait(min(.01, remaining))
            if report is not None:
                for note in report["notes"]:
                    if note["phase"] == "child_budget_checkpoint":
                        evidence = note["evidence"]
                        if not isinstance(evidence, dict) or not isinstance(evidence.get("wait_id"), str) or not evidence["wait_id"]:
                            raise BudgetClockUnknownError("child budget checkpoint required facts are missing")
                        if evidence["wait_id"] == row["wait_id"]:
                            checkpoint = BudgetEnvelope.from_dict(evidence["budget_envelope"]).checkpoint
                            window.envelope = _merge_checkpoint(window.envelope, checkpoint)
            with self._floor_lock:
                floor = self._floors.get(row["wait_id"])
            if floor is not None:
                window.envelope = _merge_checkpoint(window.envelope, floor.checkpoint)
        except (BudgetClockUnknownError, SettlementBusyError, ChildExecutionError):
            raise
        except Exception as exc:
            raise BudgetClockUnknownError(f"child budget checkpoint unavailable: {type(exc).__name__}: {exc}") from exc
        window.on_advance = lambda envelope: self.remember(row, envelope)
        self.remember(row, window.envelope)

    def remember(self, row, envelope):
        original = BudgetEnvelope.from_dict(json.loads(row["budget_json"]))
        checkpoint = envelope.checkpoint
        narrowed = _merge_checkpoint(original, checkpoint)
        with self._floor_lock:
            previous = self._floors.get(row["wait_id"])
            if previous is not None:
                narrowed = _merge_checkpoint(narrowed, previous.checkpoint)
            self._floors[row["wait_id"]] = narrowed
        projected = original.checkpoint.wall_at + checkpoint.elapsed_at - original.checkpoint.elapsed_at
        if narrowed.checkpoint.wall_at <= projected + .001:
            return
        # The request's immutable deadlines remain unchanged. Only the clock
        # floor advances. Independent notes preserve it when telemetry is busy.
        encoded = _encode(narrowed.to_dict())
        try:
            with self.journal._transaction(timeout_seconds=.1) as (connection, now):
                existing = connection.execute(
                    "SELECT budget_json FROM sdk_child_requests WHERE source_id=? AND wait_id=?",
                    (self.source_id, row["wait_id"])).fetchone()
                if existing is not None:
                    narrowed = _merge_checkpoint(BudgetEnvelope.from_dict(json.loads(existing[0])), narrowed.checkpoint)
                    encoded = _encode(narrowed.to_dict())
                connection.execute(
                    "UPDATE sdk_child_requests SET budget_json=?,updated_at=? WHERE source_id=? AND wait_id=? "
                    "AND state IN ('pending','running')", (encoded, now, self.source_id, row["wait_id"]))
        except Exception as exc:
            if not _transient_control_error(exc):
                raise
            facts = self._facts(writer=True)
            if facts is None:
                raise
            facts.note({"execution_id": row["child_execution_id"], "attempt": 0, "fence": 0},
                "child_budget_checkpoint", {"wait_id": row["wait_id"], "budget_envelope": narrowed.to_dict()},
                timeout_seconds=.1)
        row["budget_json"] = encoded

    @contextmanager
    def bound(self, window):
        previous = getattr(self._local, "window", None)
        self._local.window = window
        try:
            yield
        finally:
            self._local.window = previous

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        window = getattr(self._local, "window", None)
        duration = self.journal.options.query_timeout if window is None else min(
            self.journal.options.query_timeout, window.timeout())
        with self.journal._read_connection(duration) as (connection, _):
            yield connection

    def transaction(self):
        window = getattr(self._local, "window", None)
        return self.journal._transaction() if window is None else self.journal._transaction(
            timeout_seconds=window.timeout())

    def request(self, parent_id: str, request_id: str) -> dict[str, Any] | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM sdk_child_requests WHERE source_id=? AND parent_execution_id=? AND request_id=?",
                (self.source_id, parent_id, request_id)).fetchone()
            return None if row is None else dict(row)

    def finish(self, row: Mapping[str, Any], state: str, *, result=None, error=None) -> None:
        response = None
        if result is not None:
            try:
                response = _encode(result)
            except ChildExecutionError:
                # The original full result remains authoritative in Kernel.
                response = _encode({"result_ref": row["child_execution_id"]})
        encoded_error = None if error is None else _encode(error)
        with self.transaction() as (connection, now):
            changed = connection.execute(
                "UPDATE sdk_child_requests SET state=?,response_json=?,error_json=?,updated_at=?,"
                "service_owner=NULL,owner_expires_at=NULL WHERE source_id=? AND parent_execution_id=? "
                "AND request_id=? AND state IN ('pending','running')",
                (state, response, encoded_error, now, self.source_id,
                 row["parent_execution_id"], row["request_id"])).rowcount
            if changed:
                connection.execute(
                    "UPDATE sdk_child_waits SET state=?,error_json=?,updated_at=? WHERE source_id=? AND wait_id=?",
                    (state, encoded_error, now, self.source_id, row["wait_id"]))
        with self._floor_lock:
            self._floors.pop(row["wait_id"], None)


class HandlerChildren:
    """Automatically bound child capability supplied by HandlerContext.

    ``run`` returns the complete ExecutionResultV2 dictionary. A failed child
    raises ChildExecutionError with that same dictionary in ``result``. Waiting
    consumes the parent's original work window; no parent memory is released.
    Request IDs are scoped to one parent execution and replay durable responses.
    """

    def __init__(self, kernel: Any, command: ExecutionCommandV2,
                 parent_lease: ExecutionLease, budget_envelope: BudgetEnvelope,
                 service_spec: Mapping[str, Any], *, journal: Any = None,
                 _budget_context: Any = None) -> None:
        self.kernel, self.command, self.parent_lease = kernel, command, parent_lease
        self._budget_context = _budget_context
        self._completion_capture = None
        self.budget_envelope = budget_envelope
        self.service_spec = dict(service_spec)
        self.capacity = self.service_spec.get("capacity", 1)
        self.max_depth = self.service_spec.get("max_depth", 1)
        for name, value in (("capacity", self.capacity), ("max_depth", self.max_depth)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if command.execution_id != parent_lease.execution_id:
            raise ValueError("parent command and lease identities disagree")
        if journal is None:
            from ..observability.contracts import ObservationOptions
            from ..observability.journal import ObservationJournal
            options = self.service_spec.get("options")
            if isinstance(options, Mapping):
                options = ObservationOptions(**options)
            journal = ObservationJournal(self.service_spec["journal_path"],
                kernel_path=self.service_spec["kernel_path"],
                source_id=self.service_spec["source_id"], options=options)
        self.store = _Store(journal)

    def _active(self, window=None) -> None:
        try:
            if window is None:
                _verify_parent(self.kernel, self.parent_lease)
            else:
                _retry(window, lambda: self.kernel.verify(self.parent_lease), kernel=self.kernel)
        except (StaleFenceError, InvalidStateTransitionError, ExecutionNotFoundError) as exc:
            raise ChildExecutionError("parent_authority_revoked", str(exc),
                                      execution_id=self.command.execution_id) from exc

    def _budget(self, request_id: str, timeout_seconds: float | None) -> BudgetEnvelope:
        # Establish the original local cutoff from persisted clock authority.
        # The retry window arms before it first samples the current wall clock.
        sample = sample_clock(wall_time=self.budget_envelope.checkpoint.wall_at)
        self.budget_envelope = self.budget_envelope.recheckpoint(sample=sample)
        view = self.budget_envelope.view(sample=sample)
        if view.clock_status != "trusted":
            raise BudgetClockUnknownError(view.unknown_reason)
        if view.remaining_work_seconds is None:
            raise ChildExecutionError("parent_budget_missing", "child waits require a finite parent work deadline")
        if view.remaining_work_seconds <= 0:
            raise ChildExecutionError("parent_budget_exhausted", "parent work budget is exhausted")
        assert view.effective_work_deadline_at is not None
        envelope = self.budget_envelope.derive(source="parent",
            origin_id=f"parent:{self.command.execution_id}:{self.parent_lease.attempt}:{self.parent_lease.fence}",
            deadline_at=view.effective_work_deadline_at, sample=sample)
        if timeout_seconds is not None:
            envelope = envelope.derive(source="tool", origin_id=(
                f"child-call:{self.command.execution_id}:{self.parent_lease.attempt}:"
                f"{self.parent_lease.fence}:{request_id}"),
                                       timeout_seconds=_positive(timeout_seconds, "timeout_seconds"), sample=sample)
        return envelope

    def _depth(self, window=None) -> int:
        limits = (self.kernel.get_execution_limits(self.command.execution_id) if window is None else
            _retry(window, lambda: self.kernel.get_execution_limits(self.command.execution_id), kernel=self.kernel))
        depth = 0 if limits is None else limits.get("depth", 0)
        if type(depth) is not int or depth < 0:
            raise ChildExecutionError("child_depth_unknown", "parent depth is unavailable")
        if depth + 1 > self.max_depth:
            raise ChildExecutionError("child_depth_exceeded", "configured child depth would be exceeded")
        return depth + 1

    def _cycle(self, connection: sqlite3.Connection, target_id: str) -> None:
        pending, seen = [target_id], set()
        while pending:
            node = pending.pop()
            if node == self.command.execution_id:
                raise ChildExecutionError("child_wait_cycle", "child wait would create a dependency cycle")
            if node in seen:
                continue
            seen.add(node)
            if len(seen) > _MAX_GRAPH_NODES:
                raise ChildExecutionError("child_graph_limit", "wait graph exceeds the supported bounded scan")
            rows = connection.execute(
                "SELECT target_execution_id FROM sdk_child_waits WHERE source_id=? AND parent_execution_id=? "
                "AND state='open' LIMIT ?", (self.store.source_id, node, _MAX_GRAPH_NODES + 1)).fetchall()
            if len(rows) > _MAX_GRAPH_NODES:
                raise ChildExecutionError("child_graph_limit", "wait graph exceeds the supported bounded scan")
            pending.extend(row[0] for row in rows)

    def _enqueue(self, *, request_id: str, child_id: str, action: str,
                 child_command: ExecutionCommandV2 | None, envelope: BudgetEnvelope,
                 reason: str = "child_result", window=None) -> dict[str, Any]:
        _identifier(request_id, "request_id")
        _identifier(child_id, "execution_id")
        _identifier(reason, "reason")
        window = window or _RetryWindow(envelope, self.kernel)
        self._active(window)
        _wait_parent_entry(self.kernel, self.parent_lease, envelope, window=window)
        depth = self._depth(window)
        command_json = None if child_command is None else _encode(child_command.to_dict())
        budget_json, lease_json = _encode(window.envelope.to_dict()), _encode(self.parent_lease.to_dict())
        view = window.envelope.view(sample=window.envelope.checkpoint)
        if view.clock_status != "trusted" or not view.remaining_work_seconds:
            raise ChildExecutionError("child_budget_exhausted", "child has no trusted remaining work time")
        wait_id = str(uuid.uuid4())
        with self.store.transaction() as (connection, now):
            existing = connection.execute(
                "SELECT * FROM sdk_child_requests WHERE source_id=? AND parent_execution_id=? AND request_id=?",
                (self.store.source_id, self.command.execution_id, request_id)).fetchone()
            if existing is not None:
                row = dict(existing)
                if row["state"] in _OPEN and (row["parent_attempt"], row["parent_fence"]) != (
                        self.parent_lease.attempt, self.parent_lease.fence):
                    raise ChildExecutionError("child_request_previous_attempt", "unsettled request belongs to an older parent attempt")
                if row["action"] != action or (action != "run" and row["child_execution_id"] != child_id):
                    raise ChildExecutionError("child_request_conflict", "request ID identifies a different child call")
                if action == "run":
                    previous = ExecutionCommandV2.from_dict(json.loads(row["command_json"]))
                    assert child_command is not None
                    if (previous.handler_id, previous.handler_contract_version, previous.payload,
                            previous.timeout_seconds) != (child_command.handler_id, child_command.handler_contract_version,
                                                          child_command.payload, child_command.timeout_seconds):
                        raise ChildExecutionError("child_request_conflict", "request ID identifies a different child call")
                return row
            self._cycle(connection, child_id)
            open_waits = connection.execute(
                "SELECT COUNT(*) FROM sdk_child_waits WHERE source_id=? AND state='open'",
                (self.store.source_id,)).fetchone()[0]
            if open_waits >= _MAX_GRAPH_NODES:
                raise ChildExecutionError("child_graph_limit", "active wait graph reached its configured bound")
            if action != "observe":
                used = connection.execute(
                    "SELECT COUNT(*) FROM sdk_child_requests WHERE source_id=? AND action IN ('run','adopt') "
                    "AND state IN ('pending','running')", (self.store.source_id,)).fetchone()[0]
                if used >= self.capacity:
                    raise ChildExecutionError("child_capacity_exhausted", "configured child capacity is fully reserved")
                other = connection.execute(
                    "SELECT parent_execution_id FROM sdk_child_requests WHERE source_id=? AND child_execution_id=? "
                    "AND action IN ('run','adopt') LIMIT 1",
                    (self.store.source_id, child_id)).fetchone()
                if other is not None:
                    raise ChildExecutionError("child_relationship_conflict", "target already has an execution owner")
            connection.execute(
                "INSERT INTO sdk_child_requests(source_id,parent_execution_id,request_id,parent_attempt,parent_fence,"
                "parent_lease_json,child_execution_id,depth,action,state,command_json,budget_json,wait_id,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,'pending',?,?,?,?,?)",
                (self.store.source_id, self.command.execution_id, request_id, self.parent_lease.attempt,
                 self.parent_lease.fence, lease_json, child_id, depth, action, command_json,
                 budget_json, wait_id, now, now))
            connection.execute(
                "INSERT INTO sdk_child_waits VALUES(?,?,?,?,?,?,?,?,?,'open',?,NULL)",
                (self.store.source_id, wait_id, self.command.execution_id, self.parent_lease.attempt,
                 self.parent_lease.fence, child_id, reason, now, view.effective_work_deadline_at, now))
        row = self.store.request(self.command.execution_id, request_id)
        assert row is not None
        self.store.attach(row, window)
        try:
            self._active(window)
        except ChildExecutionError as exc:
            self.store.finish(row, "cancelled", error={"code": exc.code, "message": str(exc)})
            raise
        return row

    def run(self, handler_id: str, payload: Any, *, request_id: str,
            timeout_seconds: float = 300.0, handler_contract_version: int = 1) -> dict[str, Any]:
        """Submit and await one actual child through the configured bounded pool."""
        _identifier(handler_id, "handler_id")
        _identifier(request_id, "request_id")
        timeout = _positive(timeout_seconds, "timeout_seconds")
        envelope = self._budget(request_id, timeout)
        prefix = "sdk-managed:child:" if self.command.execution_id.startswith("sdk-managed:") else "sdk-child:"
        child_id = f"{prefix}{uuid.uuid4()}"
        bindings = self.service_spec.get("bindings", {})
        revision = bindings.get((handler_id, handler_contract_version), self.service_spec.get("registry_revision"))
        child = ExecutionCommandV2(execution_id=child_id, idempotency_key=child_id,
            registry_revision=revision, correlation_id=self.command.correlation_id,
            causation_id=self.command.execution_id, handler_id=handler_id,
            handler_contract_version=handler_contract_version, retry_policy=RetryPolicy(),
            timeout_seconds=timeout, payload=payload)
        window = _RetryWindow(envelope, self.kernel)
        self._active(window)
        row = _retry(window, lambda: self._enqueue(request_id=request_id, child_id=child_id, action="run",
                            child_command=child, envelope=envelope, window=window), store=self.store)
        return self._await(row)

    def wait_for(self, execution_id: str, *, request_id: str,
                 timeout_seconds: float | None = None, reason: str = "child_result") -> dict[str, Any]:
        """Await an existing execution, adopting queued work when capacity permits."""
        _identifier(execution_id, "execution_id")
        envelope = self._budget(request_id, timeout_seconds)
        window = _RetryWindow(envelope, self.kernel)
        self._active(window)
        try:
            target = _retry(window, lambda: self.kernel.get(execution_id), kernel=self.kernel)
        except ExecutionNotFoundError as exc:
            raise ChildExecutionError("child_missing", str(exc), execution_id=execution_id) from exc
        if target.state in _TERMINAL:
            return self._result(target.result.to_dict())
        self._depth(window)
        action = "observe"
        if target.state == "queued":
            limits = _retry(window, lambda: self.kernel.get_execution_limits(execution_id), kernel=self.kernel)
            parent = None if limits is None else limits.get("parent_execution_id")
            if parent is None or parent == self.command.execution_id:
                action = "adopt"
            else:
                reason = "child_owned_by_another_parent"
        row = _retry(window, lambda: self._enqueue(request_id=request_id, child_id=execution_id, action=action,
                            child_command=None, envelope=envelope, reason=reason, window=window), store=self.store)
        return self._await(row)

    def _result(self, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("status") != "succeeded":
            error = value.get("error") or {}
            raise ChildExecutionError(error.get("code") or "child_failed", error.get("message") or "child failed",
                                      execution_id=value.get("execution_id"), result=value)
        return value

    def _await(self, row: Mapping[str, Any]) -> dict[str, Any]:
        _inspect_parent_revocation(self.kernel, self.parent_lease)
        window = _RetryWindow(BudgetEnvelope.from_dict(json.loads(row["budget_json"])), self.kernel,
                              execution_id=row["parent_execution_id"])
        attached = False
        try:
            self.store.attach(row, window)
            attached = True
            return self._await_window(row, window)
        except Exception as exc:
            if not attached:
                # An unread floor may be stronger than the original request.
                # Result delivery cannot bypass unresolved checkpoint facts.
                raise
            wait_expired = isinstance(exc, ChildExecutionError) and exc.code == "child_wait_timeout"
            if not wait_expired and _transient_control_error(exc):
                # A busy read can be the last error retained by _retry when
                # the same trusted original window expires. Do not treat
                # contention during a live window as completed delivery.
                with window.project():
                    wait_expired = window.remaining() <= 0
            if not wait_expired:
                raise
            previous_deadline = window._delivery_deadline
            window._delivery_deadline = time.monotonic() + .1
            try:
                from .child_factual_read import uses_independent_reader
                if uses_independent_reader(self.kernel):
                    # Factual delivery borrows exact captured floors. It must
                    # not spend its proof allowance on writer admission/ACK.
                    completed = self._completed_result(row, window)
                else:
                    completed = self._complete_result_after_publication(row, window)
            except Exception as proof_error:
                if (_transient_control_error(proof_error)
                        or isinstance(proof_error, (BudgetClockUnknownError, InspectionBudgetExceeded))
                        or (isinstance(proof_error, TimeoutError)
                            and str(proof_error) == "child result proof admission budget elapsed")):
                    # Keep the original wait outcome and its identity while
                    # retaining why the bounded delivery proof was unknown.
                    raise exc from proof_error
                raise
            finally:
                window._delivery_deadline = previous_deadline
            if completed is None:
                raise
            # The durable request remains the service's publication obligation.
            # Reading a proved result neither acknowledges that write nor
            # releases an unresolved child reservation.
            return self._result(completed)

    def _complete_result_after_publication(self, row, window):
        """Retain the existing custom/in-memory Kernel settlement fallback."""
        # Finishing a retained observation is factual cleanup, not
        # another sample or business admission. It shares the existing
        # result proof's deadline and cannot clear a foreign guard.
        owner = window._pending_sample_owner or window._capture
        if owner is not None and owner._pending is not None:
            if (owner.kernel is not self.kernel
                    or owner.execution_id != self.command.execution_id
                    or (row["parent_execution_id"], row["parent_attempt"], row["parent_fence"]) != (
                        self.command.execution_id, self.parent_lease.attempt, self.parent_lease.fence)):
                raise BudgetClockUnknownError("child result checkpoint owner cannot be established")
            published = owner.finish_pending(window.envelope,
                timeout_seconds=max(0., window._delivery_deadline-time.monotonic()))
            window.envelope = window.envelope.with_clock_floor(published.checkpoint)
            window._pending_sample = window._pending_sample_owner = window._pending_sample_error = None
        drain = getattr(self.kernel, "_drain_budget_samples", None)
        sample_status = getattr(self.kernel, "_budget_sample_status", None)
        execution_ids = (self.command.execution_id, row["child_execution_id"])
        if (drain is not None and sample_status is not None
                and any(sample_status(execution_id) is True for execution_id in execution_ids)
                and (row.get("parent_execution_id"), row.get("parent_attempt"),
                row.get("parent_fence")) == (
                    self.command.execution_id, self.parent_lease.attempt, self.parent_lease.fence)):
            # A Context monitor owns a different helper from this wait.
            # Visit only exact locally retained parent/child facts; an
            # unrelated capture must not spend this proof's allowance.
            drain(window._delivery_deadline, execution_ids=execution_ids)
        return self._completed_result(row, window)

    @contextmanager
    def _completed_result_authority(self, row: Mapping[str, Any], deadline: float):
        """Observe a live sampler's ACK within the existing factual window."""
        waiting = None
        lock = getattr(self.kernel, "_control_lock", None)
        while True:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                if waiting is not None:
                    raise waiting
                raise TimeoutError("child result proof admission budget elapsed")
            with lock(remaining) if lock is not None else nullcontext():
                self.kernel._verify_active_lease_readonly(self.parent_lease)
                try:
                    self.kernel._assert_budget_clock(self.kernel._connection, self.command.execution_id)
                    self.kernel._assert_budget_clock(self.kernel._connection, row["child_execution_id"])
                except BudgetClockUnknownError as error:
                    if str(error) != "budget_clock_sample_unresolved:sampling":
                        raise
                    waiting = error
                else:
                    # The reader and its final guards are outside the wait's
                    # catch: a late guard cannot cause a second result read.
                    yield
                    return
            remaining = deadline-time.monotonic()
            if remaining > 0:
                time.sleep(min(.005, remaining))

    def _completed_result(self, row: Mapping[str, Any], window: _RetryWindow) -> dict[str, Any] | None:
        """Read an already committed result once after diagnostic delivery lag."""
        from .child_factual_read import read_completed_result, uses_independent_reader
        if uses_independent_reader(self.kernel):
            return read_completed_result(self, row, window)
        deadline = window._delivery_deadline
        if deadline is None:
            deadline = time.monotonic() + .1
        sample = sample_clock(wall_time=self.kernel._wall_time())
        views = [envelope.view(sample=sample) for envelope in (
            BudgetEnvelope.from_dict(json.loads(row["budget_json"])), window.envelope)]
        if any(view.clock_status != "trusted" for view in views):
            raise BudgetClockUnknownError("child result delivery clock continuity cannot be established")
        cutoffs = [deadline for view in views for deadline in (
            view.effective_work_deadline_at, view.effective_hard_deadline_at) if deadline is not None]
        if not cutoffs or (row["parent_execution_id"], row["parent_attempt"], row["parent_fence"]) != (
                self.command.execution_id, self.parent_lease.attempt, self.parent_lease.fence):
            return None
        checking_parent = True
        try:
            with self._completed_result_authority(row, deadline):
                checking_parent = False
                snapshot = self.kernel.get(row["child_execution_id"])
                if snapshot.state not in _TERMINAL or snapshot.result is None:
                    return None
                result = snapshot.result
                if (result.execution_id, result.attempt, result.fence) != (
                        row["child_execution_id"], snapshot.attempt, snapshot.fence):
                    return None
                if not math.isfinite(result.completed_at) or result.completed_at > min(cutoffs):
                    return None
                if row["action"] in {"run", "adopt"}:
                    limits = self.kernel.get_execution_limits(row["child_execution_id"])
                    if limits is None or (limits.get("parent_execution_id"), limits.get("parent_attempt"),
                                          limits.get("parent_fence")) != (
                            self.command.execution_id, self.parent_lease.attempt, self.parent_lease.fence):
                        return None
                # A cancellation concurrent with the child read must win.
                # This shares the same admission deadline, not another wait.
                checking_parent = True
                self.kernel._verify_active_lease_readonly(self.parent_lease)
                self.kernel._assert_budget_clock(self.kernel._connection, self.command.execution_id)
                self.kernel._assert_budget_clock(self.kernel._connection, row["child_execution_id"])
                return result.to_dict()
        except (StaleFenceError, InvalidStateTransitionError) as exc:
            raise ChildExecutionError("parent_authority_revoked", str(exc),
                                      execution_id=self.command.execution_id) from exc
        except ExecutionNotFoundError as exc:
            if checking_parent:
                raise ChildExecutionError("parent_authority_revoked", str(exc),
                                          execution_id=self.command.execution_id) from exc
            return None

    def _await_window(self, row: Mapping[str, Any], window: _RetryWindow) -> dict[str, Any]:
        while True:
            self._active(window)
            current = _retry(window, lambda: self.store.request(self.command.execution_id, row["request_id"]), store=self.store)
            if current is None:
                raise ChildExecutionError("child_registration_missing", "durable child registration disappeared")
            if current["response_json"] is not None:
                value = json.loads(current["response_json"])
                if "result_ref" in value:
                    snapshot = _retry(window, lambda: self.kernel.get(value["result_ref"]), kernel=self.kernel)
                    if snapshot.result is None:
                        raise ChildExecutionError("child_result_missing", "recorded result reference is unavailable")
                    value = snapshot.result.to_dict()
                with self.store._floor_lock:
                    self.store._floors.pop(row["wait_id"], None)
                return self._result(value)
            if current["state"] not in _OPEN:
                error = json.loads(current["error_json"] or "{}")
                raise ChildExecutionError(error.get("code", "child_wait_failed"), error.get("message", current["state"]),
                                          execution_id=current["child_execution_id"])
            remaining = window.remaining()
            if remaining is None:
                raise BudgetClockUnknownError("child clock continuity cannot be established")
            if remaining <= 0:
                raise ChildExecutionError("child_wait_timeout", "child wait exhausted its inherited work window",
                                          execution_id=current["child_execution_id"])
            time.sleep(min(.05, remaining))


class ChildService:
    """Recoverable coordinator with at most ``capacity`` targeted child workers."""

    def __init__(self, runtime: Any, journal: Any, *, capacity: int = 1,
                 max_depth: int = 1, poll_interval: float = .05) -> None:
        for name, value in (("capacity", capacity), ("max_depth", max_depth)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        self.runtime, self.store = runtime, _Store(journal)
        self.capacity, self.max_depth = capacity, max_depth
        self.poll_interval = _positive(poll_interval, "poll_interval")
        self.owner = f"child-service:{uuid.uuid4()}"
        self._stop, self._wake = threading.Event(), threading.Event()
        self._lock = threading.Lock()
        self._pool: ThreadPoolExecutor | None = None
        self._thread: threading.Thread | None = None
        self._futures: dict[str, tuple[Future[Any], dict[str, Any]]] = {}
        self._last_error: str | None = None
        self._last_renewal = 0.0

    def start(self) -> ChildService:
        with self._lock:
            if self._thread is not None:
                return self
            if self._stop.is_set():
                raise RuntimeError("child service has been closed")
            self._pool = ThreadPoolExecutor(max_workers=self.capacity, thread_name_prefix="sdk-child")
            self._thread = threading.Thread(target=self._coordinate, name="sdk-child-coordinator", daemon=True)
            self._thread.start()
        return self

    def wake(self) -> None:
        self._wake.set()

    def _coordinate(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
            self._wake.wait(self.poll_interval)
            self._wake.clear()

    def tick(self) -> None:
        self._observe_waits()
        with self._lock:
            if self._pool is None or self._stop.is_set():
                return
            for key, (future, _) in tuple(self._futures.items()):
                if future.done():
                    try:
                        future.result()
                    except Exception as exc:
                        self._last_error = f"{type(exc).__name__}: {exc}"
                    del self._futures[key]
            free = self.capacity - len(self._futures)
            renewal_due = (bool(self._futures) and time.monotonic() - self._last_renewal >= .5)
            if free <= 0 and not renewal_due:
                return
            # This is only a scheduling hint for the observation journal's
            # ownership lease. Actual claim still atomically rechecks below;
            # budget capture happens in _execute before business admission.
            with self.store.read() as connection:
                candidate = connection.execute(
                    "SELECT 1 FROM sdk_child_requests WHERE source_id=? "
                    "AND state IN ('pending','running') AND action IN ('run','adopt') "
                    "AND (service_owner IS NULL OR owner_expires_at<=?) LIMIT 1",
                    (self.store.source_id, self.store.journal.clock())).fetchone()
            if candidate is None and not renewal_due:
                return
            with self.store.transaction() as (connection, now):
                if time.monotonic() - self._last_renewal >= .5:
                    for future, active_row in self._futures.values():
                        if not future.done():
                            connection.execute(
                                "UPDATE sdk_child_requests SET owner_expires_at=? WHERE source_id=? AND service_owner=? "
                                "AND parent_execution_id=? AND request_id=? AND state IN ('pending','running')",
                                (now + 2, self.store.source_id, self.owner,
                                 active_row["parent_execution_id"], active_row["request_id"]))
                    self._last_renewal = time.monotonic()
                rows = connection.execute(
                    "SELECT * FROM sdk_child_requests WHERE source_id=? AND state IN ('pending','running') "
                    "AND action IN ('run','adopt') "
                    "AND (service_owner IS NULL OR owner_expires_at<=?) ORDER BY created_at,request_id LIMIT ?",
                    (self.store.source_id, now, free)).fetchall()
                for row in rows:
                    connection.execute(
                        "UPDATE sdk_child_requests SET service_owner=?,owner_expires_at=?,updated_at=? "
                        "WHERE source_id=? AND parent_execution_id=? AND request_id=?",
                        (self.owner, now + 2, now, self.store.source_id, row["parent_execution_id"], row["request_id"]))
            if self._stop.is_set():
                return
            for row in rows:
                record = dict(row)
                future = self._pool.submit(self._execute, record)
                self._futures[record["wait_id"]] = (future, record)

    def _observe_waits(self) -> None:
        # Observation-only waits never consume a child execution worker. This
        # avoids filling the one child slot with a caller observing another
        # parent's queued target, which would prevent that target progressing.
        with self.store.read() as connection:
            rows = connection.execute(
                "SELECT * FROM sdk_child_requests WHERE source_id=? AND action='observe' "
                "AND state IN ('pending','running') ORDER BY created_at LIMIT ?",
                (self.store.source_id, _MAX_GRAPH_NODES)).fetchall()
        for record in rows:
            row = dict(record)
            try:
                lease = ExecutionLease.from_dict(json.loads(row["parent_lease_json"]))
                _inspect_parent_revocation(self.runtime.kernel, lease)
                window = _RetryWindow(BudgetEnvelope.from_dict(json.loads(row["budget_json"])),
                    self.runtime.kernel, self._stop, execution_id=row["parent_execution_id"])
                self.store.attach(row, window)
                _verify_parent(self.runtime.kernel, lease)
                with self.runtime.kernel._control_lock(.1) if hasattr(self.runtime.kernel, "_control_lock") else nullcontext():
                    snapshot = self.runtime.kernel.get(row["child_execution_id"])
                if snapshot.state in _TERMINAL:
                    result = snapshot.result.to_dict()
                    self.store.finish(row, "completed" if result["status"] == "succeeded" else "failed", result=result)
                elif snapshot.state == "recovery_required":
                    self.store.finish(row, "unknown", error={"code": "child_recovery_required",
                        "message": snapshot.recovery_reason or "observed target requires recovery"})
                else:
                    window.remaining()
                    view = window.envelope.view(sample=window.envelope.checkpoint)
                    if view.clock_status != "trusted":
                        raise BudgetClockUnknownError(view.unknown_reason)
                    if not view.remaining_work_seconds:
                        raise ChildExecutionError("child_wait_timeout", "observed wait exhausted its work deadline")
            except Exception as exc:
                if _transient_control_error(exc):
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    continue
                try:
                    self.store.finish(row, "failed", error={"code": getattr(exc, "code", None) or "child_observation_error",
                                                           "message": str(exc)})
                except Exception as publish_error:
                    if not _transient_control_error(publish_error):
                        raise
                    self._last_error = f"{type(publish_error).__name__}: {publish_error}"

    def _cancel(self, child_id: str, reason: str) -> dict[str, Any] | None:
        try:
            lock = getattr(self.runtime.kernel, "_control_lock", None)
            with lock(.1) if lock is not None else nullcontext():
                snapshot = self.runtime.kernel.get(child_id)
        except ExecutionNotFoundError:
            return None
        if snapshot.state not in _TERMINAL and snapshot.state != "recovery_required":
            self.runtime.cancel(child_id, expected_revision=snapshot.revision, reason=reason)
            with lock(.1) if lock is not None else nullcontext():
                snapshot = self.runtime.kernel.get(child_id)
        return None if snapshot.result is None else snapshot.result.to_dict()

    def _execute(self, row: dict[str, Any]) -> None:
        submitted = row["action"] == "observe"
        lease = None
        try:
            lease = ExecutionLease.from_dict(json.loads(row["parent_lease_json"]))
            _inspect_parent_revocation(self.runtime.kernel, lease)
            envelope = BudgetEnvelope.from_dict(json.loads(row["budget_json"]))
            window = _RetryWindow(envelope, self.runtime.kernel, self._stop,
                                  execution_id=row["parent_execution_id"])
            self.store.attach(row, window)
            def control(operation):
                return _retry(window, operation, kernel=self.runtime.kernel)
            def publish(operation):
                return _retry(window, operation, store=self.store)
            if row["action"] == "adopt":
                limits = control(lambda: self.runtime.kernel.get_execution_limits(row["child_execution_id"]))
                if limits is not None and limits.get("parent_execution_id") is not None:
                    if (limits["parent_execution_id"], limits["parent_attempt"], limits["parent_fence"]) != (
                            lease.execution_id, lease.attempt, lease.fence):
                        raise ChildExecutionError("child_relationship_conflict", "adopted child belongs to another parent attempt")
                    # A prior service may have adopted and started the target
                    # before its journal update. Retain ownership for cleanup
                    # even if this parent has since lost its authority.
                    submitted = True
            if row["depth"] > self.max_depth:
                raise ChildExecutionError("child_depth_exceeded", "configured child depth would be exceeded")
            _wait_parent_entry(self.runtime.kernel, lease, envelope, self._stop, window=window)
            budget = window.envelope.view(sample=window.envelope.checkpoint)
            if budget.clock_status != "trusted":
                raise BudgetClockUnknownError(budget.unknown_reason)
            if not budget.remaining_work_seconds:
                raise ChildExecutionError("child_wait_timeout", "child inherited work deadline is exhausted")
            if row["action"] == "run":
                child_command = ExecutionCommandV2.from_dict(json.loads(row["command_json"]))
                _retry(window, lambda: self.runtime.submit_child(child_command,
                    parent_lease=lease, budget_envelope=window.envelope, timeout_seconds=window.timeout()))
                submitted = True
            elif row["action"] == "adopt":
                snapshot = control(lambda: self.runtime.kernel.get(row["child_execution_id"]))
                if not submitted or snapshot.state == "queued":
                    _retry(window, lambda: self.runtime.adopt_child(row["child_execution_id"],
                        parent_lease=lease, budget_envelope=window.envelope, timeout_seconds=window.timeout()))
                submitted = True
            def mark_running():
                with self.store.transaction() as (connection, now):
                    connection.execute(
                        "UPDATE sdk_child_requests SET state='running',updated_at=? WHERE source_id=? "
                        "AND parent_execution_id=? AND request_id=? AND state='pending'",
                        (now, self.store.source_id, row["parent_execution_id"], row["request_id"]))
            publish(mark_running)
            while not self._stop.is_set():
                control(lambda: self.runtime.kernel.verify(lease))
                window.remaining()
                view = window.envelope.view(sample=window.envelope.checkpoint)
                if view.clock_status != "trusted":
                    raise BudgetClockUnknownError(view.unknown_reason)
                if not view.remaining_work_seconds:
                    raise ChildExecutionError("child_wait_timeout", "child inherited work deadline is exhausted")
                snapshot = control(lambda: self.runtime.kernel.get(row["child_execution_id"]))
                if snapshot.state in _TERMINAL:
                    result = snapshot.result.to_dict()
                    publish(lambda: self.store.finish(row, "completed" if result["status"] == "succeeded" else "failed", result=result))
                    return
                if snapshot.state == "recovery_required":
                    publish(lambda: self.store.finish(row, "unknown", error={"code": "child_recovery_required",
                        "message": snapshot.recovery_reason or "child requires explicit effect recovery"}))
                    return
                if row["action"] != "observe" and snapshot.state == "queued":
                    _retry(window, lambda: self.runtime.run_once(execution_id=row["child_execution_id"]))
                else:
                    self._stop.wait(min(self.poll_interval, view.remaining_work_seconds))
            raise ChildExecutionError("child_service_closed", "child service stopped before response settlement")
        except Exception as exc:
            code = getattr(exc, "code", None) or "child_execution_control_error"
            original_result = None
            if row["action"] == "adopt" and not submitted and lease is not None:
                try:
                    lock = getattr(self.runtime.kernel, "_control_lock", None)
                    with lock(.1) if lock is not None else nullcontext():
                        limits = self.runtime.kernel.get_execution_limits(row["child_execution_id"])
                    submitted = limits is not None and (
                        limits.get("parent_execution_id"), limits.get("parent_attempt"), limits.get("parent_fence")) == (
                            lease.execution_id, lease.attempt, lease.fence)
                except Exception as lookup_error:
                    self._retain_registration(row, exc, lookup_error)
                    return
            if row["action"] == "run" or (submitted and row["action"] == "adopt"):
                try:
                    original_result = self._cancel(row["child_execution_id"], str(exc))
                except Exception as cancel_error:
                    # A failed cross-store call may have committed submission.
                    # Preserve its capacity and recoverable registration until
                    # Kernel can establish the child's outcome or stop it.
                    self._retain_registration(row, exc, cancel_error)
                    return
            state = "completed" if original_result is not None and original_result.get("status") == "succeeded" else "failed"
            self.store.finish(row, state, result=original_result,
                              error={"code": code, "message": str(exc)[:2048]})

    def _retain_registration(self, row, error: Exception, cleanup_error: Exception) -> None:
        with self.store.transaction() as (connection, now):
            connection.execute(
                "UPDATE sdk_child_requests SET error_json=?,updated_at=?,service_owner=NULL,"
                "owner_expires_at=NULL WHERE source_id=? AND parent_execution_id=? AND request_id=? "
                "AND state IN ('pending','running')",
                (_encode({"code": "registration_or_cleanup_pending", "message": str(error)[:2048],
                    "cleanup_error": f"{type(cleanup_error).__name__}: {cleanup_error}"[:2048]}),
                 now, self.store.source_id, row["parent_execution_id"], row["request_id"]))

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {"state": "stopped" if self._stop.is_set() else "running" if self._thread else "not_started",
                "capacity": self.capacity, "max_depth": self.max_depth,
                "active_workers": sum(not future.done() for future, _ in self._futures.values()),
                "last_error": self._last_error,
                "actions": [row["action"] for future, row in self._futures.values() if not future.done()]}

    def _close_pending(self) -> bool:
        """Inspect live storage ownership without waiting behind its owner."""
        if self._thread is not None and self._thread.is_alive():
            return True
        if not self._lock.acquire(blocking=False):
            return True
        try:
            return any(not future.done() for future, _ in self._futures.values())
        finally:
            self._lock.release()

    def close(self, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + _positive(timeout_seconds, "timeout_seconds")
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(max(0, deadline - time.monotonic()))
        inspected = self._lock.acquire(timeout=max(0, deadline - time.monotonic()))
        futures = ()
        workers = ()
        pool = None
        if inspected:
            try:
                workers = tuple(self._futures.values())
                futures = tuple(future for future, _ in workers)
                pool = self._pool
            finally:
                self._lock.release()
        if futures:
            wait(futures, timeout=max(0, deadline - time.monotonic()))
        # A coordinator may still hold the scheduling lock inside SQLite.
        # Its stop flag prevents new submissions after that operation returns;
        # a later close can finish pool shutdown after ownership is inspectable.
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
        unfinished = sum(not future.done() for future in futures) if inspected else None
        actions = [row["action"] for future, row in workers if not future.done()] if inspected else None
        return {"state": "stopped", "capacity": self.capacity, "max_depth": self.max_depth,
            "active_workers": unfinished, "last_error": self._last_error, "actions": actions,
            "unfinished_workers": unfinished, "dispatcher_alive": thread is not None and thread.is_alive(),
            "inspection_pending": not inspected}

    def __enter__(self) -> ChildService:
        return self.start()

    def __exit__(self, *args: Any) -> None:
        self.close()
