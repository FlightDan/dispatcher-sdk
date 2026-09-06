"""Explicit resolution of indeterminate effects and recovery disposition."""

from __future__ import annotations

from typing import Any

from ._sqlite_base import encode_json
from .contracts import EffectRecord
from .errors import EffectConflictError, StaleFenceError
from .transitions import reduce_state


class EffectRecoveryMixin:
    def resolve_effect(
        self,
        effect_id: str,
        *,
        decision: str,
        response: Any,
        expected_revision: int,
        recovery_id: str,
    ) -> EffectRecord:
        """Record one explicit decision and honor the durable recovery target."""

        if decision not in {"applied", "not_applied"}:
            raise ValueError("decision must be applied or not_applied")
        if decision == "not_applied" and response is not None:
            raise ValueError("not_applied recovery response must be null")
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        if type(recovery_id) is not str or not recovery_id.strip():
            raise ValueError("recovery_id must be a non-empty string")
        with self._transaction() as (connection, timestamp):
            row = connection.execute(
                "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
            if row is None:
                raise KeyError(effect_id)
            record = self._effect(row)
            if record.recovery_id == recovery_id:
                same_response = (
                    decision == "not_applied"
                    or row["response_json"] == encode_json(response)
                )
                if record.recovery_decision == decision and same_response:
                    return record
                raise EffectConflictError("effect recovery identity is immutable")
            if record.recovery_id is not None:
                raise EffectConflictError(
                    "effect already has a different recovery decision"
                )
            if record.revision != expected_revision:
                raise StaleFenceError(
                    "effect recovery revision is stale",
                    context={
                        "effect_id": effect_id,
                        "expected_revision": expected_revision,
                        "actual_revision": record.revision,
                    },
                )
            if record.state != "indeterminate":
                raise EffectConflictError(
                    "only an indeterminate effect can be resolved"
                )
            execution = self._get_row(connection, record.execution_id)
            if (
                execution["state"] != "recovery_required"
                or execution["recovery_effect_id"] != effect_id
            ):
                raise EffectConflictError("execution is not parked for this effect")
            state = "committed" if decision == "applied" else "not_applied"
            committed_at = timestamp if decision == "applied" else None
            claim_id = record.claim_id if decision == "applied" else None
            validated = EffectRecord(
                record.effect_id,
                record.execution_id,
                record.name,
                record.request,
                state,
                record.lease_id,
                claim_id,
                record.attempt,
                record.fence,
                record.prepared_at,
                response,
                committed_at,
                record.indeterminate_at,
                recovery_id,
                decision,
                timestamp,
                record.revision + 1,
            )
            cursor = connection.execute(
                """UPDATE kernel_effects
                   SET state = ?, response_json = ?, claim_id = ?, committed_at = ?,
                       recovery_id = ?, recovery_decision = ?, resolved_at = ?, revision = ?
                   WHERE effect_id = ? AND revision = ? AND state = 'indeterminate'""",
                (
                    validated.state,
                    encode_json(validated.response),
                    validated.claim_id,
                    validated.committed_at,
                    recovery_id,
                    decision,
                    timestamp,
                    validated.revision,
                    effect_id,
                    record.revision,
                ),
            )
            self._cas(cursor, "effect recovery resolution")
            resolved = self._effect(
                connection.execute(
                    "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
                ).fetchone()
            )
            self._effect_event(
                connection,
                record=resolved,
                event_type=f"recovery_{decision}",
                from_state="indeterminate",
                data={"recovery_id": recovery_id, "response": response},
                timestamp=timestamp,
            )
            remaining = connection.execute(
                """SELECT effect_id, revision FROM kernel_effects
                   WHERE execution_id = ? AND state = 'indeterminate'
                   ORDER BY effect_id LIMIT 1""",
                (record.execution_id,),
            ).fetchone()
            execution_revision = execution["revision"] + 1
            if remaining is not None:
                cursor = connection.execute(
                    """UPDATE kernel_executions SET recovery_effect_id = ?, revision = ?,
                           updated_at = ?
                       WHERE execution_id = ? AND state = 'recovery_required'
                         AND recovery_effect_id = ? AND revision = ?""",
                    (
                        remaining["effect_id"],
                        execution_revision,
                        timestamp,
                        record.execution_id,
                        effect_id,
                        execution["revision"],
                    ),
                )
                self._cas(cursor, "next effect recovery pointer")
                self._event(
                    connection,
                    execution_id=record.execution_id,
                    revision=execution_revision,
                    event_type="effect_recovery_next_required",
                    from_state="recovery_required",
                    to_state="recovery_required",
                    data={
                        "resolved_effect_id": effect_id,
                        "next_effect_id": remaining["effect_id"],
                        "effect_revision": int(remaining["revision"]),
                        "recovery_target_state": execution[
                            "recovery_target_state"
                        ],
                        "recovery_reason": execution["recovery_reason"],
                    },
                    timestamp=timestamp,
                )
                return resolved
            if execution["recovery_target_state"] == "cancelled":
                reason = execution["recovery_reason"]
                if type(reason) is not str or not reason.strip():
                    raise EffectConflictError(
                        "cancel recovery is missing its durable cancellation reason"
                    )
                command = self._command(execution["command_json"])
                result = self._cancelled_result(
                    execution,
                    command,
                    timestamp=timestamp,
                    reason=reason,
                    effect_ids=self._execution_effect_ids(
                        connection, record.execution_id
                    ),
                )
                terminal = self._terminal(
                    connection,
                    execution,
                    result,
                    event_type="cancelled_after_effect_recovery",
                    timestamp=timestamp,
                )
                if terminal.state != "cancelled":
                    raise EffectConflictError(
                        "cancel recovery did not terminalize the execution"
                    )
                return resolved
            reduce_state(
                "recovery_required",
                "recovery_resolved",
                execution_id=record.execution_id,
                revision=execution["revision"],
                fence=execution["fence"],
            )
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET state = 'queued', next_attempt_at = ?, lease_id = NULL,
                       lease_owner = NULL, lease_expires_at = NULL, started_at = NULL,
                       recovery_effect_id = NULL, recovery_target_state = NULL,
                       recovery_reason = NULL, revision = ?, updated_at = ?
                   WHERE execution_id = ? AND state = 'recovery_required'
                     AND recovery_effect_id = ? AND revision = ?""",
                (
                    timestamp,
                    execution_revision,
                    timestamp,
                    record.execution_id,
                    effect_id,
                    execution["revision"],
                ),
            )
            self._cas(cursor, "effect recovery execution resume")
            self._event(
                connection,
                execution_id=record.execution_id,
                revision=execution_revision,
                event_type="effect_recovery_resolved",
                from_state="recovery_required",
                to_state="queued",
                data={
                    "effect_id": effect_id,
                    "decision": decision,
                    "recovery_id": recovery_id,
                },
                timestamp=timestamp,
            )
            return resolved


__all__ = ("EffectRecoveryMixin",)
