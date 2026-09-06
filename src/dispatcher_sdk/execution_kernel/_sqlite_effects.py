"""Durable, lease-fenced external-effect execution and recovery."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional
import uuid

from ._sqlite_base import encode_json
from .contracts import EffectRecord, ExecutionError, ExecutionLease, ExecutionSnapshot
from .errors import (
    EffectClaimConflictError,
    EffectConflictError,
    EffectIndeterminateError,
    EffectRecoveryRequiredError,
    StaleFenceError,
)
from .transitions import reduce_state


UNFINISHED_EFFECT_STATES = frozenset({"prepared", "performing", "indeterminate"})


class EffectStoreMixin:
    @staticmethod
    def _effect(row: sqlite3.Row) -> EffectRecord:
        return EffectRecord(
            effect_id=row["effect_id"],
            execution_id=row["execution_id"],
            name=row["name"],
            request=json.loads(row["request_json"]),
            state=row["state"],
            lease_id=row["lease_id"],
            claim_id=row["claim_id"],
            attempt=row["attempt"],
            fence=row["fence"],
            prepared_at=row["prepared_at"],
            response=None if row["response_json"] is None else json.loads(row["response_json"]),
            committed_at=row["committed_at"],
            indeterminate_at=row["indeterminate_at"],
            recovery_id=row["recovery_id"],
            recovery_decision=row["recovery_decision"],
            resolved_at=row["resolved_at"],
            revision=row["revision"],
        )

    def _effect_event(
        self,
        connection: sqlite3.Connection,
        *,
        record: EffectRecord,
        event_type: str,
        from_state: Optional[str],
        data: Any,
        timestamp: float,
    ) -> None:
        cursor = connection.execute(
            """INSERT INTO kernel_effect_events
               (event_id, effect_id, execution_id, revision, event_type,
                from_state, to_state, data_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"{record.effect_id}:{record.revision}",
                record.effect_id,
                record.execution_id,
                record.revision,
                event_type,
                from_state,
                record.state,
                encode_json(data),
                timestamp,
            ),
        )
        self._cas(cursor, "effect event append")

    def get_effect(self, effect_id: str) -> EffectRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
        if row is None:
            raise KeyError(effect_id)
        return self._effect(row)

    def effect_events(self, effect_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM kernel_effect_events WHERE effect_id = ? ORDER BY revision",
                (effect_id,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "effect_id": row["effect_id"],
                "execution_id": row["execution_id"],
                "revision": row["revision"],
                "event_type": row["event_type"],
                "from_state": row["from_state"],
                "to_state": row["to_state"],
                "data": json.loads(row["data_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def effect_ids_for_attempt(
        self,
        execution_id: str,
        attempt: int,
        fence: int,
        *,
        states: set[str] | frozenset[str] = frozenset({"committed", "indeterminate"}),
    ) -> list[str]:
        if type(execution_id) is not str or not execution_id.strip():
            raise ValueError("execution_id must be a non-empty string")
        if type(attempt) is not int or attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if type(fence) is not int or fence < 1:
            raise ValueError("fence must be a positive integer")
        allowed = {"prepared", "performing", "committed", "indeterminate", "not_applied"}
        if type(states) not in {set, frozenset} or not states or not states <= allowed:
            raise ValueError("states must be a non-empty set of effect states")
        with self._lock:
            rows = self._connection.execute(
                """SELECT effect_id, state FROM kernel_effects
                   WHERE execution_id = ? AND attempt = ? AND fence = ?
                   ORDER BY effect_id""",
                (execution_id, attempt, fence),
            ).fetchall()
        return [row["effect_id"] for row in rows if row["state"] in states]

    def _unfinished_effect_rows(
        self, connection: sqlite3.Connection, execution_id: str
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """SELECT * FROM kernel_effects
               WHERE execution_id = ?
                 AND state IN ('prepared', 'performing', 'indeterminate')
               ORDER BY effect_id""",
            (execution_id,),
        ).fetchall()

    def _park_unfinished_effects(
        self,
        connection: sqlite3.Connection,
        execution: sqlite3.Row,
        timestamp: float,
        *,
        trigger: str,
        cancel_reason: Optional[str] = None,
    ) -> Optional[ExecutionSnapshot]:
        """Convert uncertain effects and atomically park instead of terminating.

        A cancellation is a durable recovery disposition, not a transient
        caller preference.  Once set, resolving the final uncertain effect
        must terminalize the execution as cancelled without exposing a queued
        claim window.  Other recovery causes resume through the normal queue.
        """

        if trigger == "cancel":
            if type(cancel_reason) is not str or not cancel_reason.strip():
                raise ValueError("cancel recovery requires a non-empty reason")
            requested_target = "cancelled"
        else:
            if cancel_reason is not None:
                raise ValueError("cancel_reason is only valid for cancel recovery")
            requested_target = "queued"

        rows = self._unfinished_effect_rows(connection, execution["execution_id"])
        if not rows:
            return None
        recovery_ids: list[str] = []
        for row in rows:
            record = self._effect(row)
            if record.state in {"prepared", "performing"}:
                detail = ExecutionError(
                    code="effect_outcome_uncertain",
                    message="execution authority ended before the effect outcome was settled",
                    retryable=False,
                    details={
                        "trigger": trigger,
                        "prior_state": record.state,
                        "attempt": record.attempt,
                        "fence": record.fence,
                    },
                )
                cursor = connection.execute(
                    """UPDATE kernel_effects
                       SET state = 'indeterminate', response_json = ?,
                           indeterminate_at = ?, recovery_id = NULL,
                           recovery_decision = NULL, resolved_at = NULL, revision = ?
                       WHERE effect_id = ? AND state = ? AND revision = ?""",
                    (
                        encode_json(detail.to_dict()),
                        timestamp,
                        record.revision + 1,
                        record.effect_id,
                        record.state,
                        record.revision,
                    ),
                )
                self._cas(cursor, "unfinished effect indeterminate conversion")
                converted = self._effect(
                    connection.execute(
                        "SELECT * FROM kernel_effects WHERE effect_id = ?",
                        (record.effect_id,),
                    ).fetchone()
                )
                self._effect_event(
                    connection,
                    record=converted,
                    event_type=(
                        "lease_expired_indeterminate"
                        if trigger == "lease_expired"
                        else "recovery_required_indeterminate"
                    ),
                    from_state=record.state,
                    data={"trigger": trigger},
                    timestamp=timestamp,
                )
            recovery_ids.append(record.effect_id)
        pointer = execution["recovery_effect_id"]
        if pointer not in recovery_ids:
            pointer = recovery_ids[0]
        pointer_row = connection.execute(
            "SELECT revision FROM kernel_effects WHERE effect_id = ?",
            (pointer,),
        ).fetchone()
        if pointer_row is None:
            raise KeyError(pointer)
        pointer_revision = int(pointer_row["revision"])
        if execution["state"] == "recovery_required":
            current_target = execution["recovery_target_state"]
            current_reason = execution["recovery_reason"]
            target = (
                "cancelled"
                if current_target == "cancelled" or requested_target == "cancelled"
                else "queued"
            )
            reason = (
                current_reason
                if current_target == "cancelled"
                else cancel_reason if target == "cancelled" else None
            )
            if (
                execution["recovery_effect_id"] == pointer
                and current_target == target
                and current_reason == reason
            ):
                return self._snapshot(execution)
            revision = execution["revision"] + 1
            cursor = connection.execute(
                """UPDATE kernel_executions SET recovery_effect_id = ?,
                       recovery_target_state = ?, recovery_reason = ?,
                       revision = ?, updated_at = ?
                   WHERE execution_id = ? AND state = 'recovery_required'
                     AND revision = ?""",
                (
                    pointer,
                    target,
                    reason,
                    revision,
                    timestamp,
                    execution["execution_id"],
                    execution["revision"],
                ),
            )
            upgraded_to_cancel = (
                current_target != "cancelled" and target == "cancelled"
            )
            self._cas(
                cursor,
                "recovery cancellation upgrade"
                if upgraded_to_cancel
                else "recovery pointer correction",
            )
            self._event(
                connection,
                execution_id=execution["execution_id"],
                revision=revision,
                event_type=(
                    "effect_recovery_cancellation_requested"
                    if upgraded_to_cancel
                    else "effect_recovery_pointer_corrected"
                ),
                from_state="recovery_required",
                to_state="recovery_required",
                data={
                    "effect_id": pointer,
                    "effect_revision": pointer_revision,
                    "effect_ids": recovery_ids,
                    "trigger": trigger,
                    "recovery_target_state": target,
                    "recovery_reason": reason,
                },
                timestamp=timestamp,
            )
            return self._snapshot(self._get_row(connection, execution["execution_id"]))
        reduce_state(
            execution["state"],
            "require_recovery",
            execution_id=execution["execution_id"],
            revision=execution["revision"],
            lease_id=execution["lease_id"],
            fence=execution["fence"],
        )
        revision = execution["revision"] + 1
        recovery_reason = cancel_reason if requested_target == "cancelled" else None
        cursor = connection.execute(
            """UPDATE kernel_executions
               SET state = 'recovery_required', lease_id = NULL, lease_owner = NULL,
                   lease_expires_at = NULL, started_at = COALESCE(started_at, ?),
                   recovery_effect_id = ?, recovery_target_state = ?,
                   recovery_reason = ?, revision = ?, updated_at = ?
               WHERE execution_id = ? AND state = ? AND revision = ?""",
            (
                timestamp,
                pointer,
                requested_target,
                recovery_reason,
                revision,
                timestamp,
                execution["execution_id"],
                execution["state"],
                execution["revision"],
            ),
        )
        self._cas(cursor, "execution effect-recovery park")
        self._event(
            connection,
            execution_id=execution["execution_id"],
            revision=revision,
            event_type=(
                "lease_expired_effect_recovery_required"
                if trigger == "lease_expired"
                else "effect_recovery_required"
            ),
            from_state=execution["state"],
            to_state="recovery_required",
            data={
                "effect_id": pointer,
                "effect_revision": pointer_revision,
                "effect_ids": recovery_ids,
                "trigger": trigger,
                "recovery_target_state": requested_target,
                "recovery_reason": recovery_reason,
            },
            timestamp=timestamp,
        )
        return self._snapshot(self._get_row(connection, execution["execution_id"]))

    def prepare_effect(
        self,
        lease: ExecutionLease,
        *,
        effect_id: str,
        name: str,
        request: Any,
    ) -> EffectRecord:
        recovery_required = False
        result: Optional[EffectRecord] = None
        with self._transaction() as (connection, timestamp):
            execution = self._assert_lease(
                connection, lease, timestamp=timestamp, states={"running"}
            )
            candidate = EffectRecord(
                effect_id=effect_id,
                execution_id=lease.execution_id,
                name=name,
                request=request,
                state="prepared",
                lease_id=lease.lease_id,
                claim_id=None,
                attempt=lease.attempt,
                fence=lease.fence,
                prepared_at=timestamp,
                response=None,
                committed_at=None,
                indeterminate_at=None,
                recovery_id=None,
                recovery_decision=None,
                resolved_at=None,
                revision=1,
            )
            row = connection.execute(
                "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    """INSERT INTO kernel_effects
                       (effect_id, execution_id, name, request_json, state, response_json,
                        lease_id, claim_id, attempt, fence, prepared_at, committed_at,
                        indeterminate_at, recovery_id, recovery_decision, resolved_at,
                        revision)
                       VALUES (?, ?, ?, ?, 'prepared', NULL, ?, NULL, ?, ?, ?, NULL,
                               NULL, NULL, NULL, NULL, 1)""",
                    (
                        candidate.effect_id,
                        candidate.execution_id,
                        candidate.name,
                        encode_json(candidate.request),
                        candidate.lease_id,
                        candidate.attempt,
                        candidate.fence,
                        candidate.prepared_at,
                    ),
                )
                self._cas(cursor, "effect preparation")
                self._effect_event(
                    connection,
                    record=candidate,
                    event_type="prepared",
                    from_state=None,
                    data={"attempt": lease.attempt, "fence": lease.fence},
                    timestamp=timestamp,
                )
                result = candidate
            else:
                existing = self._effect(row)
                if (
                    existing.execution_id != lease.execution_id
                    or existing.name != candidate.name
                    # Compare the canonical representation persisted at
                    # preparation time.  Python equality is deliberately not
                    # used because it conflates bool/int/float values.
                    or row["request_json"] != encode_json(candidate.request)
                ):
                    raise EffectConflictError("effect_id already identifies another effect")
                if existing.state == "committed":
                    result = existing
                elif existing.state == "not_applied":
                    cursor = connection.execute(
                        """UPDATE kernel_effects
                           SET state = 'prepared', response_json = NULL, lease_id = ?,
                               claim_id = NULL, attempt = ?, fence = ?, prepared_at = ?,
                               committed_at = NULL, revision = ?
                           WHERE effect_id = ? AND state = 'not_applied' AND revision = ?""",
                        (
                            lease.lease_id,
                            lease.attempt,
                            lease.fence,
                            timestamp,
                            existing.revision + 1,
                            effect_id,
                            existing.revision,
                        ),
                    )
                    self._cas(cursor, "recovered effect re-preparation")
                    result = self._effect(
                        connection.execute(
                            "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
                        ).fetchone()
                    )
                    self._effect_event(
                        connection,
                        record=result,
                        event_type="reprepared_after_not_applied",
                        from_state="not_applied",
                        data={"attempt": lease.attempt, "fence": lease.fence},
                        timestamp=timestamp,
                    )
                elif (
                    existing.lease_id == lease.lease_id
                    and existing.attempt == lease.attempt
                    and existing.fence == lease.fence
                    and existing.state in {"prepared", "performing"}
                ):
                    result = existing
                elif existing.state in UNFINISHED_EFFECT_STATES and lease.fence > existing.fence:
                    self._park_unfinished_effects(
                        connection, execution, timestamp, trigger="newer_fence_observed"
                    )
                    recovery_required = True
                elif existing.state == "indeterminate":
                    self._park_unfinished_effects(
                        connection, execution, timestamp, trigger="indeterminate_reuse"
                    )
                    recovery_required = True
                else:
                    raise StaleFenceError("effect belongs to an incompatible lease/fence")
        if recovery_required:
            raise EffectRecoveryRequiredError(effect_id)
        assert result is not None
        return result

    @staticmethod
    def _effect_matches_lease(record: EffectRecord, lease: ExecutionLease) -> None:
        if (
            record.execution_id != lease.execution_id
            or record.lease_id != lease.lease_id
            or record.attempt != lease.attempt
            or record.fence != lease.fence
        ):
            raise StaleFenceError(
                "effect was prepared by another lease/fence",
                context={
                    "effect_id": record.effect_id,
                    "effect_attempt": record.attempt,
                    "attempt": lease.attempt,
                    "effect_fence": record.fence,
                    "fence": lease.fence,
                },
            )

    def claim_effect(self, lease: ExecutionLease, effect_id: str) -> EffectRecord:
        """Acquire the sole durable authority to invoke an external effect."""

        if type(effect_id) is not str or not effect_id.strip():
            raise ValueError("effect_id must be a non-empty string")
        with self._transaction() as (connection, timestamp):
            self._assert_lease(connection, lease, timestamp=timestamp, states={"running"})
            row = connection.execute(
                "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
            if row is None:
                raise KeyError(effect_id)
            record = self._effect(row)
            self._effect_matches_lease(record, lease)
            if record.state == "performing":
                raise EffectClaimConflictError("effect perform authority is already claimed")
            if record.state == "indeterminate":
                raise EffectIndeterminateError("indeterminate effect requires recovery")
            if record.state != "prepared":
                raise EffectConflictError("only a prepared effect can be claimed")
            claim_id = uuid.uuid4().hex
            cursor = connection.execute(
                """UPDATE kernel_effects SET state = 'performing', claim_id = ?, revision = ?
                   WHERE effect_id = ? AND state = 'prepared' AND claim_id IS NULL
                     AND revision = ?""",
                (claim_id, record.revision + 1, effect_id, record.revision),
            )
            self._cas(cursor, "effect perform claim")
            claimed = self._effect(
                connection.execute(
                    "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
                ).fetchone()
            )
            self._effect_event(
                connection,
                record=claimed,
                event_type="perform_claimed",
                from_state="prepared",
                data={"claim_id": claim_id, "attempt": lease.attempt, "fence": lease.fence},
                timestamp=timestamp,
            )
            return claimed

    @staticmethod
    def _claim_matches(record: EffectRecord, claim_id: str) -> None:
        if type(claim_id) is not str or not claim_id.strip():
            raise ValueError("claim_id must be a non-empty string")
        if record.claim_id != claim_id:
            raise EffectClaimConflictError("effect claim token is stale")

    def commit_effect(
        self, effect_id: str, response: Any, lease: ExecutionLease, claim_id: str
    ) -> EffectRecord:
        with self._transaction() as (connection, timestamp):
            self._assert_lease(connection, lease, timestamp=timestamp, states={"running"})
            row = connection.execute(
                "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
            if row is None:
                raise KeyError(effect_id)
            record = self._effect(row)
            self._effect_matches_lease(record, lease)
            self._claim_matches(record, claim_id)
            if record.state == "committed":
                if row["response_json"] != encode_json(response):
                    raise EffectConflictError("committed effect response is immutable")
                return record
            if record.state == "indeterminate":
                raise EffectIndeterminateError("ordinary commit cannot resolve uncertainty")
            if record.state != "performing":
                raise EffectConflictError("effect is not under performing authority")
            validated = EffectRecord(
                record.effect_id, record.execution_id, record.name, record.request,
                "committed", record.lease_id, claim_id, record.attempt, record.fence,
                record.prepared_at, response, timestamp, record.indeterminate_at,
                record.recovery_id, record.recovery_decision, record.resolved_at,
                record.revision + 1,
            )
            cursor = connection.execute(
                """UPDATE kernel_effects
                   SET state = 'committed', response_json = ?, committed_at = ?, revision = ?
                   WHERE effect_id = ? AND state = 'performing' AND claim_id = ?
                     AND revision = ?""",
                (
                    encode_json(validated.response), timestamp, validated.revision,
                    effect_id, claim_id, record.revision,
                ),
            )
            self._cas(cursor, "effect commit")
            committed = self._effect(
                connection.execute(
                    "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
                ).fetchone()
            )
            self._effect_event(
                connection,
                record=committed,
                event_type="committed",
                from_state="performing",
                data={"claim_id": claim_id},
                timestamp=timestamp,
            )
            return committed

    def mark_effect_indeterminate(
        self,
        effect_id: str,
        details: Any,
        lease: ExecutionLease,
        claim_id: str,
    ) -> EffectRecord:
        with self._transaction() as (connection, timestamp):
            self._assert_lease(connection, lease, timestamp=timestamp, states={"running"})
            row = connection.execute(
                "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
            if row is None:
                raise KeyError(effect_id)
            record = self._effect(row)
            self._effect_matches_lease(record, lease)
            self._claim_matches(record, claim_id)
            if record.state == "indeterminate":
                if row["response_json"] != encode_json(details):
                    raise EffectConflictError("indeterminate effect detail is immutable")
                return record
            if record.state == "committed":
                raise EffectConflictError("committed effect cannot become indeterminate")
            if record.state != "performing":
                raise EffectConflictError("effect is not under performing authority")
            validated = EffectRecord(
                record.effect_id, record.execution_id, record.name, record.request,
                "indeterminate", record.lease_id, claim_id, record.attempt, record.fence,
                record.prepared_at, details, None, timestamp, None, None, None,
                record.revision + 1,
            )
            cursor = connection.execute(
                """UPDATE kernel_effects
                   SET state = 'indeterminate', response_json = ?, indeterminate_at = ?,
                       recovery_id = NULL, recovery_decision = NULL, resolved_at = NULL,
                       revision = ?
                   WHERE effect_id = ? AND state = 'performing' AND claim_id = ?
                     AND revision = ?""",
                (
                    encode_json(validated.response), timestamp, validated.revision,
                    effect_id, claim_id, record.revision,
                ),
            )
            self._cas(cursor, "effect indeterminate mark")
            uncertain = self._effect(
                connection.execute(
                    "SELECT * FROM kernel_effects WHERE effect_id = ?", (effect_id,)
                ).fetchone()
            )
            self._effect_event(
                connection,
                record=uncertain,
                event_type="marked_indeterminate",
                from_state="performing",
                data={"claim_id": claim_id, "details": details},
                timestamp=timestamp,
            )
            return uncertain
