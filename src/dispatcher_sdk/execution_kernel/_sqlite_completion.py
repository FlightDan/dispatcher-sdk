"""Execution completion, retry, cancellation, and terminal invariants."""

from __future__ import annotations

import sqlite3
from typing import Any, Optional
import uuid

from ._sqlite_base import encode_json
from .contracts import (
    ExecutionCommandV2,
    ExecutionError,
    ExecutionLease,
    ExecutionResultV2,
    ExecutionSnapshot,
)
from .errors import (
    CASConflictError,
    EffectRecoveryRequiredError,
    InvalidStateTransitionError,
    ResultConflictError,
    StaleFenceError,
)
from .transitions import TERMINAL_STATES, reduce_state


class ExecutionCompletionMixin:
    def _terminal(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        result: ExecutionResultV2,
        *,
        event_type: str,
        timestamp: float,
    ) -> ExecutionSnapshot:
        parked = self._park_unfinished_effects(
            connection, row, timestamp, trigger=f"before_terminal:{event_type}"
        )
        if parked is not None:
            return parked
        target = reduce_state(
            row["state"],
            result.status,
            execution_id=row["execution_id"],
            revision=row["revision"],
            lease_id=row["lease_id"],
            fence=row["fence"],
        )
        revision = row["revision"] + 1
        cursor = connection.execute(
            """UPDATE kernel_executions
               SET state = ?, result_json = ?, lease_id = NULL, lease_owner = NULL,
                   lease_expires_at = NULL, started_at = ?, recovery_effect_id = NULL,
                   recovery_target_state = NULL, recovery_reason = NULL,
                   revision = ?, updated_at = ?
               WHERE execution_id = ? AND state = ? AND revision = ?""",
            (
                target,
                encode_json(result.to_dict()),
                result.started_at,
                revision,
                timestamp,
                row["execution_id"],
                row["state"],
                row["revision"],
            ),
        )
        self._cas(cursor, "terminal result")
        self._event(
            connection,
            execution_id=row["execution_id"],
            revision=revision,
            event_type=event_type,
            from_state=row["state"],
            to_state=target,
            data={"result": result.to_dict()},
            timestamp=timestamp,
        )
        self._insert_result_outbox(connection, result, timestamp)
        return self._snapshot(self._get_row(connection, row["execution_id"]))

    @staticmethod
    def _dead_result(
        row: sqlite3.Row,
        command: ExecutionCommandV2,
        *,
        timestamp: float,
        code: str,
        message: str,
        details: dict[str, Any],
        result_id: Optional[str] = None,
        effect_ids: Optional[list[str]] = None,
    ) -> ExecutionResultV2:
        started_at = row["started_at"] if row["started_at"] is not None else timestamp
        return ExecutionResultV2(
            result_id=result_id or uuid.uuid4().hex,
            execution_id=row["execution_id"],
            status="dead",
            attempt=row["attempt"],
            fence=row["fence"],
            effect_ids=list(effect_ids or []),
            started_at=started_at,
            completed_at=timestamp,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            value=None,
            error=ExecutionError(
                code=code,
                message=message,
                retryable=False,
                details=details,
            ),
        )

    @staticmethod
    def _cancelled_result(
        row: sqlite3.Row,
        command: ExecutionCommandV2,
        *,
        timestamp: float,
        reason: str,
        effect_ids: list[str],
    ) -> ExecutionResultV2:
        """Build the one terminal result used by direct and recovered cancel."""

        started_at = row["started_at"] if row["started_at"] is not None else timestamp
        return ExecutionResultV2(
            result_id=uuid.uuid4().hex,
            execution_id=row["execution_id"],
            status="cancelled",
            attempt=row["attempt"],
            fence=row["fence"],
            effect_ids=effect_ids,
            started_at=started_at,
            completed_at=timestamp,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            value=None,
            error=ExecutionError(
                code="cancelled", message=reason, retryable=False, details={}
            ),
        )

    @staticmethod
    def _execution_effect_ids(
        connection: sqlite3.Connection,
        execution_id: str,
        *,
        states: frozenset[str] = frozenset({"committed"}),
    ) -> list[str]:
        rows = connection.execute(
            """SELECT effect_id, state FROM kernel_effects
               WHERE execution_id = ? ORDER BY effect_id""",
            (execution_id,),
        ).fetchall()
        return [row["effect_id"] for row in rows if row["state"] in states]

    def _validate_result(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        lease: ExecutionLease,
        result: ExecutionResultV2,
        timestamp: float,
    ) -> ExecutionCommandV2:
        if type(result) is not ExecutionResultV2:
            raise TypeError("complete requires ExecutionResultV2")
        command = self._command(row["command_json"])
        if (
            result.execution_id != lease.execution_id
            or result.attempt != row["attempt"]
            or result.attempt != lease.attempt
            or result.fence != row["fence"]
            or result.fence != lease.fence
            or result.correlation_id != command.correlation_id
            or result.causation_id != command.causation_id
            or row["started_at"] != result.started_at
        ):
            raise StaleFenceError(
                "result identity, attempt, fence, or causal binding is stale",
                context={
                    "execution_id": lease.execution_id,
                    "result_attempt": result.attempt,
                    "lease_attempt": lease.attempt,
                    "current_attempt": row["attempt"],
                    "result_fence": result.fence,
                    "lease_fence": lease.fence,
                    "current_fence": row["fence"],
                },
            )
        if result.completed_at > timestamp or result.completed_at > lease.expires_at:
            raise StaleFenceError(
                "result completion time is after acceptance or lease expiry",
                context={
                    "completed_at": result.completed_at,
                    "accepted_at": timestamp,
                    "lease_expires_at": lease.expires_at,
                },
            )
        if result.effect_ids:
            rows = connection.execute(
                """SELECT effect_id, execution_id, state FROM kernel_effects
                   WHERE execution_id = ?""",
                (lease.execution_id,),
            ).fetchall()
            facts = {item["effect_id"]: item for item in rows}
            allowed = {"committed", "prepared", "performing", "indeterminate"}
            if any(
                effect_id not in facts or facts[effect_id]["state"] not in allowed
                for effect_id in result.effect_ids
            ):
                raise StaleFenceError(
                    "result references an absent, foreign, or resolved-not-applied effect"
                )
        return command

    @staticmethod
    def _retryable(result: ExecutionResultV2, command: ExecutionCommandV2) -> bool:
        if result.status == "failed":
            return bool(result.error and result.error.retryable)
        if result.status == "timed_out":
            return bool(
                result.error
                and result.error.retryable
                and command.retry_policy.retry_timeouts
            )
        return False

    def complete(self, lease: ExecutionLease, result: ExecutionResultV2) -> ExecutionSnapshot:
        if type(lease) is not ExecutionLease:
            raise TypeError("complete requires ExecutionLease")
        if type(result) is not ExecutionResultV2:
            raise TypeError("complete requires ExecutionResultV2")
        with self._transaction() as (connection, timestamp):
            row = self._get_row(connection, lease.execution_id)
            if row["state"] in TERMINAL_STATES:
                current = self._result(row["result_json"])
                # Dataclass/Python equality is not a wire identity: it folds
                # values such as 1, 1.0, and True together.  Duplicate
                # results must match the exact canonical contract payload.
                if current is not None and current.to_json() == result.to_json():
                    return self._snapshot(row)
                if current is not None and current.result_id == result.result_id:
                    raise ResultConflictError("duplicate result_id has different content")
                raise InvalidStateTransitionError(
                    lease.execution_id,
                    row["state"],
                    result.status,
                    revision=row["revision"],
                    lease_id=lease.lease_id,
                    fence=lease.fence,
                    reason="terminal state is immutable",
                )
            row = self._assert_lease(
                connection, lease, timestamp=timestamp, states={"running"}
            )
            command = self._validate_result(connection, row, lease, result, timestamp)
            parked = self._park_unfinished_effects(
                connection, row, timestamp, trigger=f"complete:{result.status}"
            )
            if parked is not None:
                return parked
            if self._retryable(result, command):
                if row["attempt"] >= command.retry_policy.max_attempts:
                    dead = self._dead_result(
                        row,
                        command,
                        timestamp=timestamp,
                        code="retry_exhausted",
                        message="retryable result exhausted the attempt budget",
                        details={
                            "max_attempts": command.retry_policy.max_attempts,
                            "last_result": result.to_dict(),
                        },
                        result_id=result.result_id,
                        effect_ids=self._execution_effect_ids(
                            connection, row["execution_id"]
                        ),
                    )
                    return self._terminal(
                        connection,
                        row,
                        dead,
                        event_type="retry_exhausted_dead",
                        timestamp=timestamp,
                    )
                reduce_state(
                    row["state"],
                    "retry",
                    execution_id=lease.execution_id,
                    revision=row["revision"],
                    lease_id=lease.lease_id,
                    fence=lease.fence,
                )
                revision = row["revision"] + 1
                redeliveries = row["redelivery_count"] + 1
                delay = command.retry_policy.delay_for_attempt(row["attempt"])
                next_at = self._checked_add(timestamp, delay, "retry delay")
                cursor = connection.execute(
                    """UPDATE kernel_executions
                       SET state = 'queued', redelivery_count = ?, next_attempt_at = ?,
                           lease_id = NULL, lease_owner = NULL, lease_expires_at = NULL,
                           started_at = NULL, recovery_effect_id = NULL,
                           revision = ?, updated_at = ?
                       WHERE execution_id = ? AND state = 'running' AND revision = ?""",
                    (
                        redeliveries,
                        next_at,
                        revision,
                        timestamp,
                        lease.execution_id,
                        row["revision"],
                    ),
                )
                self._cas(cursor, "execution retry")
                self._event(
                    connection,
                    execution_id=lease.execution_id,
                    revision=revision,
                    event_type="retry_scheduled",
                    from_state="running",
                    to_state="queued",
                    data={"result": result.to_dict(), "next_attempt_at": next_at},
                    timestamp=timestamp,
                )
                return self._snapshot(self._get_row(connection, lease.execution_id))
            return self._terminal(
                connection,
                row,
                result,
                event_type=result.status,
                timestamp=timestamp,
            )

    def require_effect_recovery(
        self, lease: ExecutionLease, effect_id: str
    ) -> ExecutionSnapshot:
        if type(effect_id) is not str or not effect_id.strip():
            raise ValueError("effect_id must be a non-empty string")
        with self._transaction() as (connection, timestamp):
            row = self._assert_lease(
                connection, lease, timestamp=timestamp, states={"running"}
            )
            effect = connection.execute(
                """SELECT execution_id, state FROM kernel_effects
                   WHERE effect_id = ?""",
                (effect_id,),
            ).fetchone()
            if (
                effect is None
                or effect["execution_id"] != lease.execution_id
                or effect["state"] not in {"prepared", "performing", "indeterminate"}
            ):
                raise StaleFenceError(
                    "recovery requires an unfinished effect owned by the execution",
                    context={"execution_id": lease.execution_id, "effect_id": effect_id},
                )
            parked = self._park_unfinished_effects(
                connection, row, timestamp, trigger="handler_recovery_signal"
            )
            assert parked is not None
            return parked

    def dead_letter(self, lease: ExecutionLease, error: ExecutionError) -> ExecutionSnapshot:
        if type(error) is not ExecutionError or error.retryable:
            raise ValueError("dead_letter requires a non-retryable ExecutionError")
        with self._transaction() as (connection, timestamp):
            row = self._assert_lease(
                connection, lease, timestamp=timestamp, states={"leased", "running"}
            )
            parked = self._park_unfinished_effects(
                connection, row, timestamp, trigger="dead_letter"
            )
            if parked is not None:
                return parked
            command = self._command(row["command_json"])
            result = self._dead_result(
                row,
                command,
                timestamp=timestamp,
                code=error.code,
                message=error.message,
                details=error.details,
                effect_ids=self._execution_effect_ids(connection, row["execution_id"]),
            )
            return self._terminal(
                connection, row, result, event_type="permanent_dead", timestamp=timestamp
            )

    def cancel(
        self,
        execution_id: str | ExecutionLease,
        lease: Optional[ExecutionLease] = None,
        *,
        reason: str = "execution cancelled",
        expected_revision: Optional[int] = None,
    ) -> ExecutionSnapshot:
        """Cancel an execution through either worker or external authority.

        A worker may present its live lease.  A bridge/control caller cannot
        know that private lease, so it must instead present the exact current
        execution revision.  The transaction then revokes the active state;
        any later completion under the old fence is rejected by the terminal
        state/CAS checks.  Unfinished effects still fail closed through the
        existing recovery-required path.
        """

        if isinstance(execution_id, ExecutionLease):
            if lease is not None:
                raise ValueError("lease supplied twice")
            lease = execution_id
            execution_id = lease.execution_id
        if type(execution_id) is not str or not execution_id.strip():
            raise ValueError("execution_id must be a non-empty string")
        if type(reason) is not str or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        if expected_revision is not None and (
            type(expected_revision) is not int or expected_revision < 0
        ):
            raise ValueError("expected_revision must be an integer >= 0 or None")
        if lease is not None and expected_revision is not None:
            raise ValueError("lease and expected_revision are mutually exclusive")
        recovery_effect_id: Optional[str] = None
        answer: Optional[ExecutionSnapshot] = None
        with self._transaction() as (connection, timestamp):
            row = self._get_row(connection, execution_id)
            if row["state"] in TERMINAL_STATES:
                if row["state"] == "cancelled":
                    return self._snapshot(row)
                raise InvalidStateTransitionError(
                    execution_id,
                    row["state"],
                    "cancelled",
                    revision=row["revision"],
                    lease_id=row["lease_id"],
                    fence=row["fence"],
                    reason="a non-cancelled terminal execution is immutable",
                )
            if row["state"] == "recovery_required":
                recovery_effect_id = row["recovery_effect_id"]
                if lease is None:
                    if expected_revision is not None and row["revision"] != expected_revision:
                        raise CASConflictError(
                            "execution cancellation revision conflict: "
                            f"expected {expected_revision}, found {row['revision']}"
                        )
                    if expected_revision is not None:
                        parked = self._park_unfinished_effects(
                            connection,
                            row,
                            timestamp,
                            trigger="cancel",
                            cancel_reason=reason,
                        )
                        assert parked is not None
                        recovery_effect_id = parked.recovery_effect_id
            elif row["state"] in {"leased", "running"}:
                if lease is None:
                    if expected_revision is None:
                        raise StaleFenceError(
                            "active execution cancellation requires a live lease "
                            "or exact expected_revision"
                        )
                    if row["revision"] != expected_revision:
                        raise CASConflictError(
                            "execution cancellation revision conflict: "
                            f"expected {expected_revision}, found {row['revision']}"
                        )
                else:
                    row = self._assert_lease(
                        connection,
                        lease,
                        timestamp=timestamp,
                        states={"leased", "running"},
                    )
            elif expected_revision is not None and row["revision"] != expected_revision:
                raise CASConflictError(
                    "execution cancellation revision conflict: "
                    f"expected {expected_revision}, found {row['revision']}"
                )
            if row["state"] != "recovery_required":
                parked = self._park_unfinished_effects(
                    connection,
                    row,
                    timestamp,
                    trigger="cancel",
                    cancel_reason=reason,
                )
            else:
                parked = None
            if row["state"] != "recovery_required" and parked is not None:
                recovery_effect_id = parked.recovery_effect_id
            elif row["state"] != "recovery_required":
                command = self._command(row["command_json"])
                result = self._cancelled_result(
                    row,
                    command,
                    timestamp=timestamp,
                    reason=reason,
                    effect_ids=self._execution_effect_ids(connection, execution_id),
                )
                answer = self._terminal(
                    connection, row, result, event_type="cancelled", timestamp=timestamp
                )
        if recovery_effect_id is not None:
            raise EffectRecoveryRequiredError(recovery_effect_id)
        assert answer is not None
        return answer
