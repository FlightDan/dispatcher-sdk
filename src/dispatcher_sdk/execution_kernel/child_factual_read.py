"""Independent, bounded proof of a child's already committed result.

Delivery is a factual read of the original request. It grants no business
authority and never acknowledges, drains, clears or arms a budget sample.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
from typing import Any, Mapping

from .._inspection import InspectionBudget, InspectionBudgetExceeded
from .._sqlite_errors import is_sqlite_contention
from ..storage_connection import _connect_readonly
from .budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from .completion_clock import _identifier, _owned_capture_owner, _read_floor
from .contracts import ExecutionLease
from .errors import ExecutionNotFoundError, InvalidStateTransitionError, StaleFenceError


_TERMINAL = {"succeeded", "failed", "timed_out", "cancelled", "dead"}


def uses_independent_reader(kernel: Any) -> bool:
    from .sqlite import SQLiteKernel
    return type(kernel) is SQLiteKernel and kernel.db_path != ":memory:"


def _read_child_snapshot(connection, kernel, execution_id, budget):
    """The sole factual result read; final refusal never replays this hook."""
    budget.check()
    result = kernel._snapshot(kernel._get_row(connection, execution_id))
    budget.check()
    return result


def _borrow_owned(capability, window):
    """Freeze only exact original callers; registry-by-execution is insufficient."""
    kernel, lease = capability.kernel, capability.parent_lease
    owners = []
    if window.kernel is kernel and window.execution_id == lease.execution_id:
        owners.append((window._capture, None))
        imported = window._pending_sample_owner
        if (imported is not None and window._pending_sample is not None
                and window._pending_sample is getattr(imported, "_pending", None)):
            # This is the exact helper/tuple transferred by the real failed
            # capture, not another observer found by execution ID.
            owners.append((imported, window._pending_sample))
    context = capability._budget_context
    if (context is not None and getattr(context, "_kernel", None) is kernel
            and getattr(context, "lease", None) is lease
            and getattr(context, "command", None) is capability.command):
        owners.append((getattr(context, "_budget_capture", None), None))
    retained = []
    for owner, expected in owners:
        pending = getattr(owner, "_pending", None) if expected is None else expected
        if pending is None:
            continue
        captured = _owned_capture_owner(owner, kernel, lease.execution_id, pending=pending)
        if captured is not None and not any(item[1][0] == captured[0] for item in retained):
            retained.append((owner, pending))
    return retained


def read_completed_result(capability, row: Mapping[str, Any], window) -> dict[str, Any] | None:
    """Read one result between fresh original parent/ancestry proofs.

    Authority checks may retry within the caller's existing proof deadline.
    After the child is read, a failed final proof never replays that read.
    """
    from .children import ChildExecutionError

    kernel, lease = capability.kernel, capability.parent_lease
    if type(lease) is not ExecutionLease:
        raise TypeError("child result proof requires ExecutionLease")
    _identifier(lease.execution_id, "execution identity")
    _identifier(lease.lease_id, "lease identity")
    _identifier(row["parent_execution_id"], "parent identity")
    _identifier(row["child_execution_id"], "child identity")
    if (row["parent_execution_id"], row["parent_attempt"], row["parent_fence"]) != (
            capability.command.execution_id, lease.attempt, lease.fence):
        return None
    original = BudgetEnvelope.from_dict(json.loads(row["budget_json"]))
    retained = window.envelope
    deadline = window._delivery_deadline
    if deadline is None:
        deadline = time.monotonic() + .1
    budget = InspectionBudget(max(0., deadline-time.monotonic()), None)
    configured_timeout = kernel._default_control_timeout
    if configured_timeout is not None:
        deadline = min(deadline, budget.started + configured_timeout)
    budget.deadline = deadline

    borrowed = []

    def borrow():
        nonlocal retained, borrowed
        borrowed = _borrow_owned(capability, window)
        for _, (_, envelope) in borrowed:
            retained = retained.with_clock_floor(envelope.checkpoint)
        return tuple(pending[0] for _, pending in borrowed)

    def timestamp(floor):
        # Native elapsed projection strengthens retained time without another
        # wall observation or modifying any original constraint/cutoff.
        projected = retained.recheckpoint(
            sample=sample_clock(wall_time=retained.checkpoint.wall_at))
        return max(floor, projected.checkpoint.wall_at)

    def parent_proof(connection, tokens):
        budget.check()
        # Classify an already revoked parent before ancestry identity checks;
        # otherwise a newer parent fence could look merely clock-unknown.
        assert_parent_lease(connection, timestamp(0.))
        floor = _read_floor(connection, lease, budget,
            additional_owned_tokens=tokens, strict_identity=True)
        assert_parent_lease(connection, timestamp(floor))
        budget.check()

    def assert_parent_lease(connection, timestamp):
        # Parent business payloads are unrelated to this scalar authority
        # proof. Reuse the Kernel's exact lease checks without materializing
        # its potentially large command/result JSON four times.
        current = connection.execute(
            "SELECT state,revision,attempt,fence,lease_id,lease_owner,lease_expires_at "
            "FROM kernel_executions WHERE execution_id=?", (lease.execution_id,)).fetchone()
        if current is None:
            raise ExecutionNotFoundError(lease.execution_id)
        kernel._assert_lease_row(current, lease, timestamp=timestamp,
                                 states={"leased", "running"})

    def child_proof(connection, tokens, identity):
        budget.check()
        _read_floor(connection, lease, budget, additional_owned_tokens=tokens,
                    identity=identity, strict_identity=True)
        if row["action"] in {"run", "adopt"}:
            association = connection.execute(
                "SELECT parent_execution_id,parent_attempt,parent_fence "
                "FROM kernel_execution_limits WHERE execution_id=?",
                (row["child_execution_id"],)).fetchone()
            if association is None or tuple(association) != (
                    lease.execution_id, lease.attempt, lease.fence):
                return False
        budget.check()
        return True

    # Unknown original clock continuity denies proof before any child read.
    # These are the exact stored/window constraints, never a child's larger
    # independently admitted execution allowance.
    sample = sample_clock(wall_time=retained.checkpoint.wall_at)
    views = [envelope.view(sample=sample) for envelope in (original, retained)]
    if any(view.clock_status != "trusted" for view in views):
        raise BudgetClockUnknownError("child result delivery clock continuity cannot be established")
    cutoffs = [cutoff for view in views for cutoff in (
        view.effective_work_deadline_at, view.effective_hard_deadline_at) if cutoff is not None]
    if not cutoffs:
        return None

    connection = None
    reader_ready = False
    waiting = None
    checking_parent = True
    failure = None
    delivered = None
    try:
        # No BEGIN spans the child read. Final checks start a separate fresh
        # snapshot so a cancellation or new guard during that read wins.
        while True:
            if budget.expired() and waiting is not None:
                raise waiting
            budget.check()
            try:
                if connection is None:
                    connection = _connect_readonly(kernel.db_path, timeout=0)
                    connection.row_factory = sqlite3.Row
                if not reader_ready:
                    connection.execute("PRAGMA query_only=ON")
                    connection.execute("PRAGMA trusted_schema=OFF")
                    budget.install(connection)
                    reader_ready = True
                tokens = borrow()
                parent_proof(connection, tokens)
                # Guard both identities before reading any child result. The
                # current child pair supplies strict ancestry, not a lease.
                checking_parent = False
                identity = connection.execute(
                    "SELECT execution_id,attempt,fence FROM kernel_executions WHERE execution_id=?",
                    (row["child_execution_id"],)).fetchone()
                if identity is None or not child_proof(connection, tokens, tuple(identity)):
                    return None
                break
            except (sqlite3.OperationalError, BudgetClockUnknownError) as error:
                if not (is_sqlite_contention(error) or type(error) is BudgetClockUnknownError
                        and str(error) == "budget_clock_sample_unresolved:sampling"):
                    raise
                waiting = error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                checking_parent = True
                time.sleep(min(.005, remaining))

        budget.check()
        snapshot = _read_child_snapshot(connection, kernel, row["child_execution_id"], budget)
        budget.check()
        result = snapshot.result
        if snapshot.state not in _TERMINAL or result is None:
            return None
        result_identity = (result.execution_id, result.attempt, result.fence)
        if result_identity != (row["child_execution_id"], snapshot.attempt, snapshot.fence):
            return None
        if not math.isfinite(result.completed_at) or result.completed_at > min(cutoffs):
            return None

        value = result.to_dict()
        budget.check()
        # Exact pending facts may retire or change during the child read.
        # Start this fresh snapshot only AFTER the sole result read/encoding.
        # Its lease, identity, association and ancestry checks are consistent
        # without hiding cancellation committed while the result was read.
        while True:
            if budget.expired() and waiting is not None:
                raise waiting
            budget.check()
            try:
                tokens = borrow()
                connection.execute("BEGIN")
                checking_parent = True
                parent_proof(connection, tokens)
                checking_parent = False
                identity = connection.execute(
                    "SELECT execution_id,attempt,fence FROM kernel_executions WHERE execution_id=?",
                    (row["child_execution_id"],)).fetchone()
                if identity is None or tuple(identity) != result_identity:
                    return None
                if not child_proof(connection, tokens, result_identity):
                    return None
                budget.check()
            except (sqlite3.OperationalError, BudgetClockUnknownError) as error:
                if not (is_sqlite_contention(error) or type(error) is BudgetClockUnknownError
                        and str(error) == "budget_clock_sample_unresolved:sampling"):
                    raise
                waiting = error
                if connection.in_transaction:
                    try:
                        connection.rollback()
                    except BaseException as rollback_error:
                        raise error from rollback_error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                # Retain the sole child read. Only fresh authority snapshots
                # may observe a sampler's ACK within this original window.
                checking_parent = True
                time.sleep(min(.005, remaining))
            else:
                connection.rollback()
                delivered = value
                break
    except (StaleFenceError, InvalidStateTransitionError) as error:
        failure = ChildExecutionError("parent_authority_revoked", str(error),
                                      execution_id=lease.execution_id)
        failure.__cause__ = error
    except ExecutionNotFoundError as error:
        if checking_parent:
            failure = ChildExecutionError("parent_authority_revoked", str(error),
                                          execution_id=lease.execution_id)
            failure.__cause__ = error
    except BaseException as error:
        code = getattr(error, "sqlite_errorcode", None)
        timed_interrupt = (isinstance(error, sqlite3.OperationalError)
            and budget.stopped_reason == "timeout"
            and (type(code) is int and code & 255 == sqlite3.SQLITE_INTERRUPT
                or code is None and str(error).lower() == "interrupted"))
        if waiting is not None and (isinstance(error, InspectionBudgetExceeded) or timed_interrupt):
            failure = waiting
        elif timed_interrupt:
            failure = InspectionBudgetExceeded("child result proof admission budget elapsed")
            failure.__cause__ = error
        else:
            failure = error
    finally:
        if connection is not None:
            try:
                connection.close()
            except BaseException as error:
                if failure is not None:
                    raise failure from error
                raise
    if failure is not None:
        raise failure
    budget.check()
    if delivered is not None:
        for owner, pending in borrowed:
            if _owned_capture_owner(owner, kernel, lease.execution_id, pending=pending) is not None:
                # One successful final proof admits at most one sampling guard.
                # Keep its exact live tuple for the bound Context's return-time
                # read, including when _result next raises the child's error.
                capability._completion_capture = (owner, pending)
                break
    return delivered
