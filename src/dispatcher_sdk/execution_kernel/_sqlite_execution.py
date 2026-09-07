"""SQLite execution submission, leasing, and lease-expiry recovery."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional
import uuid

from ._sqlite_base import SQLiteBase, encode_json
from ._sqlite_completion import ExecutionCompletionMixin
from ._sqlite_effects import EffectStoreMixin
from ._sqlite_outbox import ResultOutboxMixin
from ._sqlite_recovery import EffectRecoveryMixin
from .contracts import ExecutionCommandV2, ExecutionLease, ExecutionSnapshot
from .claiming import claim_predicate
from .errors import IdempotencyConflictError
from .transitions import reduce_state


def _claim_revisions(
    registry_revision: Optional[str], registry_revisions: Optional[Sequence[str]]
) -> Optional[tuple[str, ...]]:
    """Validate before entering the transaction, including its logical clock."""

    if registry_revision is not None:
        if registry_revisions is not None:
            raise ValueError("registry_revision and registry_revisions are mutually exclusive")
        if type(registry_revision) is not str or not registry_revision.strip():
            raise ValueError("registry_revision must be a non-empty string")
        return (registry_revision,)
    if registry_revisions is None:
        return None
    if isinstance(registry_revisions, (str, bytes, bytearray)) or not isinstance(registry_revisions, Sequence):
        raise ValueError("registry_revisions must be a non-empty sequence of non-empty strings")
    values = tuple(registry_revisions)
    if not values or any(type(value) is not str or not value.strip() for value in values):
        raise ValueError("registry_revisions must be a non-empty sequence of non-empty strings")
    return tuple(dict.fromkeys(values))


def _next_claim_row(connection, timestamp: float, revisions: Optional[tuple[str, ...]]):
    predicate, parameters = claim_predicate(timestamp, revisions)
    return connection.execute(
        "SELECT * FROM kernel_executions WHERE " + predicate + " ORDER BY created_at, execution_id LIMIT 1",
        parameters,
    ).fetchone()


class SQLiteKernel(
    ExecutionCompletionMixin,
    EffectRecoveryMixin,
    EffectStoreMixin,
    ResultOutboxMixin,
    SQLiteBase,
):
    """Durable v2 kernel constrained to exact ``kernel_*`` schema objects."""

    def submit(self, command: ExecutionCommandV2) -> ExecutionSnapshot:
        if type(command) is not ExecutionCommandV2:
            raise TypeError("submit requires ExecutionCommandV2")
        encoded = encode_json(command.to_dict())
        with self._transaction() as (connection, timestamp):
            row, _ = self._submit_in_transaction(command, encoded, connection, timestamp)
            return self._snapshot(row)

    def cancel_before_accept(
        self, command: ExecutionCommandV2, *, reason: str = "execution cancelled"
    ) -> ExecutionSnapshot:
        """Atomically record a previously unseen command as cancelled.

        The submission and normal terminal result/events/outbox share one
        SQLite transaction, so independent workers can never claim the new
        execution. If an exact command was already accepted, return its current
        snapshot unchanged: callers must still cancel it through its runtime
        to enforce revision authority and process-tree cleanup. Conflicting
        execution or idempotency identities fail without changing either row.
        """
        if type(command) is not ExecutionCommandV2:
            raise TypeError("cancel_before_accept requires ExecutionCommandV2")
        if type(reason) is not str or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        encoded = encode_json(command.to_dict())
        with self._transaction() as (connection, timestamp):
            row, created = self._submit_in_transaction(command, encoded, connection, timestamp)
            if not created:
                return self._snapshot(row)
            result = self._cancelled_result(
                row, command, timestamp=timestamp, reason=reason, effect_ids=[])
            return self._terminal(
                connection, row, result, event_type="cancelled", timestamp=timestamp)

    def _submit_in_transaction(self, command, encoded, connection, timestamp):
        existing = connection.execute(
            """SELECT * FROM kernel_executions
               WHERE execution_id = ? OR idempotency_key = ?
               ORDER BY CASE WHEN execution_id = ? THEN 0 ELSE 1 END LIMIT 1""",
            (command.execution_id, command.idempotency_key, command.execution_id),
        ).fetchone()
        if existing is not None:
            if existing["command_json"] != encoded:
                raise IdempotencyConflictError(
                    "execution_id/idempotency_key already identifies another command"
                )
            return existing, False
        cursor = connection.execute(
            """INSERT INTO kernel_executions
               (execution_id, idempotency_key, registry_revision, command_json, state,
                attempt, redelivery_count, next_attempt_at, lease_id, lease_owner,
                fence, lease_expires_at, started_at, result_json,
                recovery_effect_id, revision, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'queued', 0, 0, ?, NULL, NULL, 0, NULL, NULL,
                       NULL, NULL, 1, ?, ?)""",
            (
                command.execution_id,
                command.idempotency_key,
                command.registry_revision,
                encoded,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        self._cas(cursor, "execution submission")
        self._event(
            connection,
            execution_id=command.execution_id,
            revision=1,
            event_type="submitted",
            from_state=None,
            to_state="queued",
            data={"command": command.to_dict()},
            timestamp=timestamp,
        )
        return self._get_row(connection, command.execution_id), True

    def _reap_in_transaction(self, connection, timestamp: float) -> list[str]:
        rows = connection.execute(
            """SELECT * FROM kernel_executions
               WHERE state IN ('leased', 'running')
                 AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?
               ORDER BY created_at, execution_id""",
            (timestamp,),
        ).fetchall()
        changed: list[str] = []
        for row in rows:
            command = self._command(row["command_json"])
            parked = self._park_unfinished_effects(
                connection, row, timestamp, trigger="lease_expired"
            )
            if parked is not None:
                changed.append(row["execution_id"])
                continue
            if row["attempt"] >= command.retry_policy.max_attempts:
                result = self._dead_result(
                    row,
                    command,
                    timestamp=timestamp,
                    code="lease_retry_exhausted",
                    message="lease expired after the retry budget was exhausted",
                    details={"max_attempts": command.retry_policy.max_attempts},
                    effect_ids=self._execution_effect_ids(
                        connection, row["execution_id"]
                    ),
                )
                self._terminal(
                    connection,
                    row,
                    result,
                    event_type="lease_expired_dead",
                    timestamp=timestamp,
                )
            else:
                reduce_state(
                    row["state"],
                    "lease_expired",
                    execution_id=row["execution_id"],
                    revision=row["revision"],
                    lease_id=row["lease_id"],
                    fence=row["fence"],
                )
                revision = row["revision"] + 1
                redeliveries = row["redelivery_count"] + 1
                delay = command.retry_policy.delay_for_attempt(row["attempt"])
                next_at = self._checked_add(timestamp, delay, "lease retry delay")
                cursor = connection.execute(
                    """UPDATE kernel_executions
                       SET state = 'queued', redelivery_count = ?, next_attempt_at = ?,
                           lease_id = NULL, lease_owner = NULL, lease_expires_at = NULL,
                           started_at = NULL, recovery_effect_id = NULL,
                           revision = ?, updated_at = ?
                       WHERE execution_id = ? AND state = ? AND revision = ?""",
                    (
                        redeliveries,
                        next_at,
                        revision,
                        timestamp,
                        row["execution_id"],
                        row["state"],
                        row["revision"],
                    ),
                )
                self._cas(cursor, "lease expiry redelivery")
                self._event(
                    connection,
                    execution_id=row["execution_id"],
                    revision=revision,
                    event_type="lease_expired_redelivery",
                    from_state=row["state"],
                    to_state="queued",
                    data={"attempt": row["attempt"], "redelivery_count": redeliveries},
                    timestamp=timestamp,
                )
            changed.append(row["execution_id"])
        return changed

    def reap(self) -> list[ExecutionSnapshot]:
        with self._transaction() as (connection, timestamp):
            ids = self._reap_in_transaction(connection, timestamp)
            return [self._snapshot(self._get_row(connection, item)) for item in ids]

    def next_queued(self, *, registry_revision: str) -> Optional[ExecutionSnapshot]:
        if type(registry_revision) is not str or not registry_revision.strip():
            raise ValueError("registry_revision must be a non-empty string")
        with self._transaction() as (connection, timestamp):
            self._reap_in_transaction(connection, timestamp)
            row = _next_claim_row(connection, timestamp, (registry_revision,))
            return None if row is None else self._snapshot(row)

    def claim(
        self,
        owner: str,
        *,
        lease_seconds: Optional[float] = None,
        registry_revision: Optional[str] = None,
        registry_revisions: Optional[Sequence[str]] = None,
    ) -> Optional[ExecutionLease]:
        if type(owner) is not str or not owner.strip():
            raise ValueError("owner must be a non-empty string")
        revisions = _claim_revisions(registry_revision, registry_revisions)
        duration = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        with self._transaction() as (connection, timestamp):
            self._reap_in_transaction(connection, timestamp)
            row = _next_claim_row(connection, timestamp, revisions)
            if row is None:
                return None
            reduce_state(
                row["state"],
                "lease",
                execution_id=row["execution_id"],
                revision=row["revision"],
            )
            lease_id = uuid.uuid4().hex
            attempt = row["attempt"] + 1
            fence = row["fence"] + 1
            revision = row["revision"] + 1
            expires_at = self._checked_add(timestamp, duration, "lease_seconds")
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET state = 'leased', attempt = ?, lease_id = ?, lease_owner = ?,
                       fence = ?, lease_expires_at = ?, revision = ?, updated_at = ?
                   WHERE execution_id = ? AND state = 'queued' AND revision = ?""",
                (
                    attempt,
                    lease_id,
                    owner,
                    fence,
                    expires_at,
                    revision,
                    timestamp,
                    row["execution_id"],
                    row["revision"],
                ),
            )
            self._cas(cursor, "execution claim")
            self._event(
                connection,
                execution_id=row["execution_id"],
                revision=revision,
                event_type="leased",
                from_state="queued",
                to_state="leased",
                data={"owner": owner, "attempt": attempt, "fence": fence},
                timestamp=timestamp,
            )
            return ExecutionLease(
                execution_id=row["execution_id"],
                lease_id=lease_id,
                owner=owner,
                fence=fence,
                attempt=attempt,
                expires_at=expires_at,
                revision=revision,
            )

    def claim_and_start(
        self,
        owner: str,
        *,
        lease_seconds: Optional[float] = None,
        start_safety_seconds: float = 5.0,
        registry_revision: Optional[str] = None,
        registry_revisions: Optional[Sequence[str]] = None,
    ) -> Optional[ExecutionLease]:
        """Atomically lease and start one queued execution.

        Both canonical transitions and both revisioned events are retained,
        but a runtime crash cannot land between two local commits.  The final
        running row remains fenced and is recovered by normal lease expiry.
        """

        if type(owner) is not str or not owner.strip():
            raise ValueError("owner must be a non-empty string")
        revisions = _claim_revisions(registry_revision, registry_revisions)
        floor = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        safety = self._nonnegative_duration(
            start_safety_seconds, "start_safety_seconds"
        )
        with self._transaction() as (connection, timestamp):
            self._reap_in_transaction(connection, timestamp)
            row = _next_claim_row(connection, timestamp, revisions)
            if row is None:
                return None
            command = self._command(row["command_json"])
            duration = max(
                floor,
                self._checked_add(
                    command.timeout_seconds,
                    safety,
                    "handler timeout safety",
                ),
            )
            reduce_state(
                row["state"],
                "lease",
                execution_id=row["execution_id"],
                revision=row["revision"],
            )
            reduce_state(
                "leased",
                "start",
                execution_id=row["execution_id"],
                revision=row["revision"] + 1,
            )
            lease_id = uuid.uuid4().hex
            attempt = row["attempt"] + 1
            fence = row["fence"] + 1
            leased_revision = row["revision"] + 1
            running_revision = leased_revision + 1
            expires_at = self._checked_add(timestamp, duration, "lease_seconds")
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET state = 'running', attempt = ?, lease_id = ?, lease_owner = ?,
                       fence = ?, lease_expires_at = ?, started_at = ?,
                       revision = ?, updated_at = ?
                   WHERE execution_id = ? AND state = 'queued' AND revision = ?""",
                (
                    attempt,
                    lease_id,
                    owner,
                    fence,
                    expires_at,
                    timestamp,
                    running_revision,
                    timestamp,
                    row["execution_id"],
                    row["revision"],
                ),
            )
            self._cas(cursor, "atomic execution claim/start")
            self._event(
                connection,
                execution_id=row["execution_id"],
                revision=leased_revision,
                event_type="leased",
                from_state="queued",
                to_state="leased",
                data={"owner": owner, "attempt": attempt, "fence": fence},
                timestamp=timestamp,
            )
            self._event(
                connection,
                execution_id=row["execution_id"],
                revision=running_revision,
                event_type="started",
                from_state="leased",
                to_state="running",
                data={"attempt": attempt, "fence": fence},
                timestamp=timestamp,
            )
            return ExecutionLease(
                execution_id=row["execution_id"],
                lease_id=lease_id,
                owner=owner,
                fence=fence,
                attempt=attempt,
                expires_at=expires_at,
                revision=running_revision,
            )

    def verify(self, lease: ExecutionLease) -> ExecutionSnapshot:
        with self._transaction() as (connection, timestamp):
            row = self._assert_lease(
                connection,
                lease,
                timestamp=timestamp,
                states={"leased", "running"},
            )
            return self._snapshot(row)

    def start(self, lease: ExecutionLease) -> ExecutionLease:
        with self._transaction() as (connection, timestamp):
            row = self._assert_lease(
                connection, lease, timestamp=timestamp, states={"leased"}
            )
            reduce_state(
                row["state"],
                "start",
                execution_id=lease.execution_id,
                revision=row["revision"],
                lease_id=lease.lease_id,
                fence=lease.fence,
            )
            revision = row["revision"] + 1
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET state = 'running', started_at = ?, revision = ?, updated_at = ?
                   WHERE execution_id = ? AND state = 'leased' AND revision = ?""",
                (timestamp, revision, timestamp, lease.execution_id, row["revision"]),
            )
            self._cas(cursor, "execution start")
            self._event(
                connection,
                execution_id=lease.execution_id,
                revision=revision,
                event_type="started",
                from_state="leased",
                to_state="running",
                data={"attempt": lease.attempt, "fence": lease.fence},
                timestamp=timestamp,
            )
            return ExecutionLease(
                execution_id=lease.execution_id,
                lease_id=lease.lease_id,
                owner=lease.owner,
                fence=lease.fence,
                attempt=lease.attempt,
                expires_at=lease.expires_at,
                revision=revision,
            )

    def renew(
        self, lease: ExecutionLease, *, lease_seconds: Optional[float] = None
    ) -> ExecutionLease:
        duration = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        with self._transaction() as (connection, timestamp):
            row = self._assert_lease(
                connection,
                lease,
                timestamp=timestamp,
                states={"leased", "running"},
            )
            expires_at = self._checked_add(timestamp, duration, "lease_seconds")
            revision = row["revision"] + 1
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET lease_expires_at = ?, revision = ?, updated_at = ?
                   WHERE execution_id = ? AND revision = ?""",
                (expires_at, revision, timestamp, lease.execution_id, row["revision"]),
            )
            self._cas(cursor, "lease renewal")
            self._event(
                connection,
                execution_id=lease.execution_id,
                revision=revision,
                event_type="lease_renewed",
                from_state=row["state"],
                to_state=row["state"],
                data={"fence": lease.fence, "expires_at": expires_at},
                timestamp=timestamp,
            )
            return ExecutionLease(
                execution_id=lease.execution_id,
                lease_id=lease.lease_id,
                owner=lease.owner,
                fence=lease.fence,
                attempt=lease.attempt,
                expires_at=expires_at,
                revision=revision,
            )


ExecutionKernel = SQLiteKernel
