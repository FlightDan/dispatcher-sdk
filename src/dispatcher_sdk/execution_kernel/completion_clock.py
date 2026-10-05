"""Bounded factual return-time capture, independent of live Kernel writers.

The read snapshot is a completion fact, not renewed execution authority. It
neither samples a new budget nor clears an outstanding budget observation.
"""
from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from .._inspection import InspectionBudget, InspectionBudgetExceeded
from .._sqlite_errors import is_sqlite_contention
from ..storage_connection import _connect_readonly
from .budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from .budget_capture import _KernelBudgetCapture
from .contracts import ExecutionLease
from .errors import StorageIsolationError


_IDENTITY_BYTES = 4096
_MAX_ANCESTRY = 64


def _identifier(value: Any, name: str) -> str:
    if (type(value) is not str or len(value) > _IDENTITY_BYTES
            or not value.strip()
            or len(value.encode("utf-8")) > _IDENTITY_BYTES):
        raise StorageIsolationError(f"completion clock {name} is unavailable or oversized")
    return value


def _finite(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise StorageIsolationError(f"completion clock {name} is not finite")
    try:
        number = float(value)
    except OverflowError as error:
        raise StorageIsolationError(f"completion clock {name} is not finite") from error
    if not math.isfinite(number) or number < 0:
        raise StorageIsolationError(f"completion clock {name} is not finite")
    return number


def _owned_capture(context: Any, kernel: Any, execution_id: str) -> tuple[str, BudgetEnvelope] | None:
    """Freeze positive local ownership without waiting on a live sampler.

    Pending tuples and envelopes are immutable. Registry publication precedes
    the arm COMMIT; a concurrent retirement can conservatively remove proof,
    but cannot change the already captured fact into new business authority.
    """
    owner = getattr(context, "_budget_capture", None)
    captured = _owned_capture_owner(owner, kernel, execution_id)
    if captured is not None:
        return captured
    from .children import HandlerChildren

    children = getattr(context, "children", None)
    if (type(children) is not HandlerChildren or children._budget_context is not context
            or children.kernel is not kernel
            or children.command is not getattr(context, "command", None)
            or children.parent_lease is not getattr(context, "lease", None)):
        return None
    proof = children._completion_capture
    if proof is None:
        return None
    owner, pending = proof
    # Child delivery and handler return share this exact captured fact, but
    # neither reader owns its ACK. Retirement or replacement removes proof.
    return _owned_capture_owner(owner, kernel, execution_id, pending=pending)


def _owned_capture_owner(owner: Any, kernel: Any,
                         execution_id: str, *, pending=None) -> tuple[str, BudgetEnvelope] | None:
    """Borrow an exact registered caller's immutable captured fact."""
    if (type(owner) is not _KernelBudgetCapture or owner.kernel is not kernel
            or owner.execution_id != execution_id):
        return None
    pending = owner._pending if pending is None else pending
    if (type(pending) is not tuple or len(pending) != 2
            or type(pending[1]) is not BudgetEnvelope):
        return None
    token = _identifier(pending[0], "owned sampling token")
    if kernel._budget_sample_owners.get(token) is not owner or owner._pending is not pending:
        return None
    return token, pending[1]


def _read_floor(connection: sqlite3.Connection, lease: ExecutionLease,
                budget: InspectionBudget, *, owned_token: str | None = None,
                additional_owned_tokens: tuple[str, ...] = (),
                identity: tuple[str, int, int] | None = None,
                strict_identity: bool = False) -> float:
    """Read bounded schema, watermark and ancestry authority.

    Completion provenance keeps its existing attempt-bound ancestry behavior.
    Delivery additionally requires every inspected identity to remain exact.
    An owned token always belongs only to the supplied original lease, even
    when delivery starts ancestry inspection at that lease's terminal child.
    """
    from ._sqlite_schema import KERNEL_STORAGE_SCHEMA_VERSION

    budget.check()
    markers = [tuple(row) for row in connection.execute(
        "SELECT CASE WHEN typeof(component)='text' AND length(CAST(component AS BLOB))<=64 "
        "THEN component END,CASE WHEN typeof(schema_version)='integer' THEN schema_version END,"
        "typeof(schema_version) FROM kernel_schema_meta LIMIT 2").fetchall()]
    if markers != [("execution_kernel", KERNEL_STORAGE_SCHEMA_VERSION, "integer")]:
        raise StorageIsolationError("completion clock requires the current Kernel schema")
    budget.check()
    clocks = connection.execute(
        "SELECT CASE WHEN typeof(singleton)='integer' THEN singleton END,"
        "CASE WHEN typeof(watermark) IN ('integer','real') THEN watermark END,"
        "typeof(singleton),typeof(watermark) "
        "FROM kernel_clock LIMIT 2").fetchall()
    if (len(clocks) != 1 or clocks[0][0] != 1 or clocks[0][2] != "integer"
            or clocks[0][3] not in {"integer", "real"}):
        raise StorageIsolationError("completion clock watermark row is unavailable or malformed")
    floor = _finite(clocks[0][1], "watermark")

    execution_id: str | None = lease.execution_id if identity is None else identity[0]
    expected_pair = (lease.attempt, lease.fence) if identity is None else identity[1:]
    _identifier(execution_id, "execution identity")
    if strict_identity and (len(expected_pair) != 2
            or any(type(value) is not int or value < 1 for value in expected_pair)):
        raise StorageIsolationError("child result ancestry identity is malformed")
    seen: set[str] = set()
    while execution_id is not None:
        budget.check()
        if execution_id in seen or len(seen) >= _MAX_ANCESTRY:
            raise BudgetClockUnknownError("completion clock ancestry cannot be established")
        seen.add(execution_id)
        current_identity = connection.execute(
            "SELECT CASE WHEN typeof(attempt)='integer' THEN attempt END,"
            "CASE WHEN typeof(fence)='integer' THEN fence END "
            "FROM kernel_executions WHERE execution_id=?",
            (execution_id,)).fetchone()
        # A newer attempt is not this return fact's ancestry. Its constraints
        # or pending samples cannot replace the immutable original floor.
        # Revocation/lease expiry remains the later settlement CAS's concern.
        if current_identity is not None and (type(current_identity[0]) is not int
                or type(current_identity[1]) is not int):
            raise StorageIsolationError("completion clock execution identity is malformed")
        if current_identity is None or tuple(current_identity) != expected_pair:
            if strict_identity:
                raise BudgetClockUnknownError("child result ancestry identity cannot be established")
            break
        # Bound scalar reads before materialization; business payloads and
        # serialized budget constraints never enter this diagnostic path.
        guards = connection.execute(
            "SELECT CASE WHEN typeof(token)='text' AND length(CAST(token AS BLOB))<=4096 "
            "THEN token END,CASE WHEN typeof(reason)='text' AND length(CAST(reason AS BLOB))<=128 "
            "THEN reason END "
            "FROM kernel_budget_samples WHERE execution_id=? LIMIT 2",
            (execution_id,)).fetchall()
        for token, reason in guards:
            _identifier(token, "sampling token")
            if reason not in {"sampling", "legacy_unprotected"}:
                raise StorageIsolationError("completion clock sampling guard is malformed")
        if guards and not (len(guards) == 1 and execution_id == lease.execution_id
                and guards[0][1] == "sampling"
                and guards[0][0] in (owned_token, *additional_owned_tokens)):
            # Only this Context's fully captured fact proves a factual return
            # floor. Extra, foreign, parent, and uncaptured guards still fence
            # it. No marker is acknowledged or cleared by this reader.
            reason = "legacy_unprotected" if any(row[1] == "legacy_unprotected" for row in guards) else "sampling"
            raise BudgetClockUnknownError("budget_clock_sample_unresolved:" + reason)
        parent = connection.execute(
            "SELECT CASE WHEN typeof(parent_execution_id)='text' "
            "AND length(CAST(parent_execution_id AS BLOB))<=4096 THEN parent_execution_id END,"
            "typeof(parent_execution_id),"
            "CASE WHEN typeof(parent_attempt)='integer' THEN parent_attempt END,"
            "CASE WHEN typeof(parent_fence)='integer' THEN parent_fence END "
            "FROM kernel_execution_limits WHERE execution_id=?",
            (execution_id,)).fetchone()
        if parent is None:
            raise BudgetClockUnknownError("completion clock execution limits are missing")
        if parent[1] == "null":
            execution_id = None
        else:
            execution_id = _identifier(parent[0], "parent identity")
            if (type(parent[2]) is not int or parent[2] < 1
                    or type(parent[3]) is not int or parent[3] < 1):
                raise StorageIsolationError("completion clock parent identity is malformed")
            expected_pair = (parent[2], parent[3])
    budget.check()
    return floor


class _CompletionReaderLifetime:
    """One Context reservation; retries own the same physically live reader.

    The capture stays on its original invocation thread. Cross-thread cleanup
    is allowed only after the full capture body has left; it never overlaps a
    statement, takes another wall sample, or opens another connection.
    """

    def __init__(self, context: Any) -> None:
        self.context = context
        self._body_done = threading.Event()
        self._close_lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None
        self._close_error: BaseException | None = None

    def attached(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def close_connection(self, connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except BaseException as error:
            if self._close_error is None:
                self._close_error = error
            raise
        else:
            self._connection = None

    def body_finished(self, deadline: float) -> None:
        # Publication follows every original read/rollback/close statement.
        # An unsuccessful close keeps this Context reservation charged.
        self._body_done.set()
        if self._connection is None:
            self.context._release_completion_reader(self, deadline)

    def drain(self, deadline: float) -> None:
        if not self._body_done.wait(max(0., deadline - time.monotonic())):
            return
        if not self._close_lock.acquire(timeout=max(0., deadline - time.monotonic())):
            return
        try:
            if time.monotonic() >= deadline:
                return
            connection = self._connection
            if connection is not None:
                try:
                    self.close_connection(connection)
                except BaseException:
                    # The original error remains on this exact owner. A failed
                    # retry cannot discharge physical/maintenance ownership.
                    return
            self.context._release_completion_reader(self, deadline)
        finally:
            self._close_lock.release()


def capture_completion_time(context: Any, *, timeout_seconds: float = .1) -> float:
    """Capture an original return fact within one unrenewed control window.

    File-backed standard Kernels use an independent committed read snapshot.
    The actual return sample is taken once, before SQLite admission; retries
    reuse it. Custom and in-memory Kernels retain their bounded clock method.
    Any unavailable fact is raised to the caller, which owns the original
    outcome and its unknown-clock receipt.
    """
    if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= .1):
        raise ValueError("completion capture timeout must be finite, positive, and at most .1")
    budget = InspectionBudget(timeout_seconds, None)
    kernel = context._kernel
    from .sqlite import SQLiteKernel
    from .context import HandlerContext

    # Standalone helper contexts retain existing inline/affinity semantics.
    # Only a real HandlerContext participates in Runtime's lifetime tracking.
    if type(kernel) is SQLiteKernel and kernel.db_path != ":memory:":
        configured_timeout = kernel._default_control_timeout
        if configured_timeout is not None:
            assert budget.deadline is not None
            budget.deadline = min(budget.deadline, budget.started + configured_timeout)
    owner = _CompletionReaderLifetime(context) if isinstance(context, HandlerContext) else None
    if owner is not None:
        # No raw wall observation or storage open precedes this atomic gate.
        context._reserve_completion_reader(owner, budget)
    try:
        return _capture_completion_time(context, budget, owner)
    finally:
        if owner is not None:
            assert budget.deadline is not None
            owner.body_finished(budget.deadline)


def _capture_completion_time(context: Any, budget: InspectionBudget,
                             owner: _CompletionReaderLifetime | None) -> float:
    deadline = budget.deadline
    assert deadline is not None
    kernel = context._kernel
    from .sqlite import SQLiteKernel

    if type(kernel) is not SQLiteKernel or kernel.db_path == ":memory:":
        budget.check()
        with kernel._control_lock(max(0., deadline - time.monotonic())):
            completed_at = _finite(kernel.current_time(), "custom clock")
        budget.check()
        return completed_at

    # Read one immutable retained reference without waiting on the monitor's
    # budget lock. Stronger committed observations are covered by the snapshot
    # watermark; a pending observation remains explicitly unknown below.
    envelope = context._budget_envelope
    if type(envelope) is not BudgetEnvelope:
        raise BudgetClockUnknownError("completion clock retained budget is missing")
    lease = context.lease
    if type(lease) is not ExecutionLease:
        raise StorageIsolationError("completion clock requires an exact execution lease")
    _identifier(lease.execution_id, "execution identity")
    _identifier(lease.lease_id, "lease identity")
    owned = _owned_capture(context, kernel, lease.execution_id)
    if owned is not None:
        # Borrow only its checkpoint. Original Context constraints/entry stay
        # unchanged even if a captured observer used a different envelope.
        envelope = envelope.with_clock_floor(owned[1].checkpoint)
    sample = sample_clock(wall_time=kernel._wall_time())
    retained_floor = envelope.recheckpoint(sample=sample).checkpoint.wall_at
    budget.check()
    path = Path(kernel.db_path).expanduser().resolve()
    connection = None
    reader_ready = False
    failure: BaseException | None = None
    result = None
    admission_error: Exception | None = None
    # The independent connection owns its maintenance participation until
    # actual close, including an unsuccessful close retained by its factory.
    try:
        budget.check()
        while True:
            if budget.expired():
                if admission_error is not None:
                    raise admission_error
                budget.check()
            try:
                if connection is None:
                    if owner is None:
                        connection = _connect_readonly(path, timeout=0)
                    else:
                        connection = _connect_readonly(path, timeout=0, check_same_thread=False)
                        owner.attached(connection)
                if not reader_ready:
                    connection.execute("PRAGMA query_only=ON")
                    connection.execute("PRAGMA trusted_schema=OFF")
                    budget.install(connection)
                    reader_ready = True
                connection.execute("BEGIN")
                floor = _read_floor(connection, lease, budget,
                    owned_token=None if owned is None else owned[0])
                result = max(sample.wall_at, retained_floor, floor)
                break
            except (sqlite3.OperationalError, BudgetClockUnknownError) as error:
                transient = (is_sqlite_contention(error) or
                    type(error) is BudgetClockUnknownError and
                    str(error) == "budget_clock_sample_unresolved:sampling")
                if not transient:
                    raise
                admission_error = error
                if connection is not None and connection.in_transaction:
                    try:
                        connection.rollback()
                    except BaseException as rollback_error:
                        raise error from rollback_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(.005, remaining))
    except BaseException as error:
        # Exhaustion after a prior refusal retains that original cause
        # rather than replacing it with a timer. A SQLite interruption must
        # be attributed to this reader's progress deadline, not just happen
        # to coincide with an expired window.
        code = getattr(error, "sqlite_errorcode", None)
        timed_interrupt = (isinstance(error, sqlite3.OperationalError)
            and budget.stopped_reason == "timeout"
            and (type(code) is int and code & 255 == sqlite3.SQLITE_INTERRUPT
                or code is None and str(error).lower() == "interrupted"))
        failure = (admission_error if (isinstance(error, InspectionBudgetExceeded) or timed_interrupt)
            and admission_error is not None else error)
    finally:
        if connection is not None:
            try:
                if owner is None:
                    connection.close()
                else:
                    owner.close_connection(connection)
            except BaseException as error:
                if failure is not None:
                    raise failure from error
                raise
    if failure is not None:
        raise failure
    budget.check()
    assert result is not None
    return result
