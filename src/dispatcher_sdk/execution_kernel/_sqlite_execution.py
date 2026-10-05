"""SQLite execution submission, leasing, and lease-expiry recovery."""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Optional
import os
from pathlib import Path
import sqlite3
import time
import uuid

from ._sqlite_base import MAX_SQLITE_INTEGER, SQLiteBase, encode_json
from ._sqlite_completion import ExecutionCompletionMixin
from ._sqlite_effects import EffectStoreMixin
from ._sqlite_outbox import ResultOutboxMixin
from ._sqlite_recovery import EffectRecoveryMixin
from .supervision import SupervisionMixin
from .budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from .contracts import ExecutionCommandV2, ExecutionLease, ExecutionSnapshot
from .claiming import claim_predicate
from .errors import (
    CASConflictError,
    ExecutionNotFoundError,
    IdempotencyConflictError,
    StorageIsolationError,
    StaleFenceError,
)
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


MANAGED_EXECUTION_PREFIX = "sdk-managed:"


def _next_claim_row(connection, timestamp: float, revisions: Optional[tuple[str, ...]],
                    execution_id: str | None = None):
    predicate, parameters = claim_predicate(timestamp, revisions, alias="k")
    if execution_id is not None:
        predicate += " AND k.execution_id = ?"
        parameters = (*parameters, execution_id)
    else:
        predicate += " AND NOT EXISTS (SELECT 1 FROM kernel_execution_limits l " \
                     "WHERE l.execution_id=k.execution_id AND l.parent_execution_id IS NOT NULL)"
        # An unresolved root keeps its own admission fence, while unrelated
        # eligible work remains claimable. Explicit targets retain the normal
        # authority check and surface their unknown clock instead of skipping.
        predicate += " AND NOT EXISTS (SELECT 1 FROM kernel_budget_samples s " \
                     "WHERE s.execution_id=k.execution_id)"
    return connection.execute(
        """SELECT k.* FROM kernel_executions AS k WHERE """ + predicate + """
           AND (
               k.execution_id NOT GLOB 'sdk-managed:*'
               OR EXISTS (
                   SELECT 1 FROM kernel_managed_executions AS m
                   JOIN kernel_run_controls AS c ON c.run_id = m.run_id
                   WHERE m.execution_id = k.execution_id
                     AND (
                         (
                             c.claims_used < c.max_claims
                             AND c.deadline_at > ?
                             AND (
                                 (c.state = 'active' AND m.generation = c.generation)
                                 OR (c.state = 'pausing' AND m.drain_allowed = 1)
                             )
                         )
                     )
               )
           )
           ORDER BY k.created_at, k.execution_id LIMIT 1""",
        (*parameters, timestamp),
    ).fetchone()


class SQLiteKernel(
    SupervisionMixin,
    ExecutionCompletionMixin,
    EffectRecoveryMixin,
    EffectStoreMixin,
    ResultOutboxMixin,
    SQLiteBase,
):
    """Durable v3 kernel constrained to exact ``kernel_*`` schema objects."""

    def _assert_child_claim(self, connection, execution_id: str, timestamp: float) -> None:
        limits = connection.execute(
            "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (execution_id,)
        ).fetchone()
        if limits is None or limits["parent_execution_id"] is None:
            return
        self._assert_budget_clock(connection, execution_id)
        parent = self._get_row(connection, limits["parent_execution_id"])
        if (parent["state"] != "running"
                or (parent["attempt"], parent["fence"]) != (limits["parent_attempt"], limits["parent_fence"])
                or parent["lease_expires_at"] is None or parent["lease_expires_at"] <= timestamp):
            raise StaleFenceError("child claim belongs to a revoked parent lease")
        self._authorize_managed_operation(
            connection, parent["execution_id"], timestamp=timestamp, operation="child claim"
        )
        parent_limits = connection.execute(
            "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (parent["execution_id"],)
        ).fetchone()
        if (parent_limits is None or parent_limits["entry_state"] != "confirmed"
                or (parent_limits["entry_attempt"], parent_limits["entry_fence"]) != (
                    parent["attempt"], parent["fence"])):
            raise CASConflictError("child claim requires confirmed parent handler entry")
        parent_envelope = BudgetEnvelope.from_dict(json.loads(parent_limits["envelope_json"]))
        # Admission consumes committed clock evidence. The invocation wrapper
        # owns the next guarded wall sample before actual business entry.
        sample = sample_clock(wall_time=parent_envelope.checkpoint.wall_at)
        for stored in (parent_limits, limits):
            envelope = BudgetEnvelope.from_dict(json.loads(stored["envelope_json"]))
            if not any(item.origin_id == "execution:" + parent["execution_id"]
                       and item.source == "execution" for item in envelope.constraints):
                raise CASConflictError("child claim has no confirmed parent execution cutoff")
            view = envelope.view(sample=sample)
            if view.clock_status != "trusted":
                raise BudgetClockUnknownError(view.unknown_reason)
            if not view.remaining_work_seconds:
                raise CASConflictError("child claim inherited work deadline has elapsed")

    @staticmethod
    def _managed_run_id(value: str) -> str:
        if type(value) is not str or not value.strip():
            raise ValueError("run_id must be a non-empty string")
        return value

    @staticmethod
    def _managed_generation(value: int, name: str = "generation") -> int:
        if type(value) is not int or value < 0 or value > MAX_SQLITE_INTEGER:
            raise ValueError(
                f"{name} must be a non-negative SQLite integer"
            )
        return value

    @staticmethod
    def _normalize_drain_ids(values) -> tuple[str, ...]:
        if isinstance(values, (str, bytes, bytearray)) or not isinstance(
            values, (Sequence, set, frozenset)
        ):
            raise ValueError("drain_execution_ids must be a sequence or set of identifiers")
        identifiers = tuple(values)
        if any(type(value) is not str or not value.strip() for value in identifiers):
            raise ValueError("drain_execution_ids must contain non-empty strings")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("drain_execution_ids must not contain duplicates")
        if any(not value.startswith(MANAGED_EXECUTION_PREFIX) for value in identifiers):
            raise ValueError("drain_execution_ids must use the reserved managed execution prefix")
        return tuple(sorted(identifiers))

    @staticmethod
    def _run_control_value(row, drain_ids=()) -> dict:
        return {
            "run_id": row[0],
            "control_epoch": row[1],
            "generation": row[2],
            "state": row[3],
            "max_claims": row[4],
            "claims_used": row[5],
            "deadline_at": row[6],
            "drain_execution_ids": tuple(drain_ids),
        }

    def _require_shared_transaction(self, connection) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be a sqlite3.Connection")
        if not connection.in_transaction:
            raise RuntimeError("caller must hold an open SQLite transaction")
        if self.db_path == ":memory:":
            raise ValueError("managed Run controls require a durable Kernel database")
        if connection is self._connection:
            same_store = True
        else:
            main = next(
                (row[2] for row in connection.execute("PRAGMA database_list") if row[1] == "main"),
                None,
            )
            try:
                same_store = main is not None and os.path.samefile(main, self.db_path)
            except OSError:
                same_store = False
        if not same_store:
            raise StorageIsolationError(
                "control transaction must use the Kernel's main SQLite database"
            )
        marker = connection.execute(
            "SELECT component,schema_version FROM kernel_schema_meta"
        ).fetchone()
        from ._sqlite_schema import KERNEL_STORAGE_SCHEMA_VERSION

        if tuple(marker or ()) != ("execution_kernel", KERNEL_STORAGE_SCHEMA_VERSION):
            raise StorageIsolationError("control transaction requires the current Kernel schema")

    def _run_control_snapshot(self, connection, run_id: str):
        row = connection.execute(
            "SELECT run_id,control_epoch,generation,state,max_claims,claims_used,deadline_at "
            "FROM kernel_run_controls WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        drain_ids = tuple(
            row[0]
            for row in connection.execute(
                "SELECT execution_id FROM kernel_managed_executions "
                "WHERE run_id=? AND drain_allowed=1 ORDER BY execution_id",
                (run_id,),
            )
        )
        return self._run_control_value(row, drain_ids)

    def _authorize_managed_operation(
        self,
        connection,
        execution_id: str,
        *,
        timestamp: float,
        operation: str,
        settlement: bool = False,
    ) -> None:
        """Recheck Run control before managed work or effect settlement."""

        if not execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            return
        row = connection.execute(
            """SELECT m.generation,m.drain_allowed,c.generation,c.state,c.deadline_at
               FROM kernel_managed_executions AS m
               LEFT JOIN kernel_run_controls AS c ON c.run_id=m.run_id
               WHERE m.execution_id=?""",
            (execution_id,),
        ).fetchone()
        if row is None or row[2] is None:
            raise StorageIsolationError(
                f"managed execution lacks its Run control during {operation}"
            )
        # An external effect may finish after pause/deadline changed. Recording
        # that already-authorized outcome grants no new external authority.
        if settlement:
            return
        if row[4] <= timestamp:
            error = CASConflictError("managed Run deadline has elapsed")
            error._budget_deadline = {
                "source": "run", "deadline_at": row[4], "observed_at": timestamp}
            raise error
        if row[3] == "active" and row[0] == row[2]:
            return
        if (
            row[3] == "pausing"
            and row[1] == 1
            and operation not in {"effect preparation", "external effect claim"}
        ):
            return
        raise CASConflictError(
            f"managed Run control does not allow {operation} for this execution"
        )

    def _charge_managed_claim(self, connection, execution_id: str, *, timestamp: float) -> None:
        if not execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            return
        cursor = connection.execute(
            """UPDATE kernel_run_controls SET claims_used=claims_used+1
               WHERE run_id=(SELECT run_id FROM kernel_managed_executions
                             WHERE execution_id=?)
                 AND claims_used < max_claims AND deadline_at > ?
                 AND EXISTS (
                     SELECT 1 FROM kernel_managed_executions AS m
                     WHERE m.execution_id=? AND m.run_id=kernel_run_controls.run_id
                       AND (
                           (kernel_run_controls.state='active'
                                AND m.generation=kernel_run_controls.generation)
                           OR (kernel_run_controls.state='pausing' AND m.drain_allowed=1)
                       )
                 )""",
            (execution_id, timestamp, execution_id),
        )
        self._cas(cursor, "managed Run claim budget")

    def get_run_control(self, run_id: str) -> dict | None:
        """Read one durable control snapshot without advancing the Kernel clock."""

        run_id = self._managed_run_id(run_id)
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                return self._run_control_snapshot(self._connection, run_id)
            finally:
                self._connection.rollback()

    def register_run_control(
        self, run_id: str, *, max_claims: int, deadline_at: float
    ) -> dict:
        """Idempotently register a managed Run, initially closed to claims."""

        with self._transaction() as (connection, _timestamp):
            return self.register_run_control_in_transaction(
                connection,
                run_id,
                max_claims=max_claims,
                deadline_at=deadline_at,
            )

    def register_run_control_in_transaction(
        self, connection, run_id: str, *, max_claims: int, deadline_at: float
    ) -> dict:
        """Register in a caller-owned transaction for a shared Orchestrator store."""

        run_id = self._managed_run_id(run_id)
        if type(max_claims) is not int or not 0 <= max_claims <= MAX_SQLITE_INTEGER:
            raise ValueError("max_claims must be a non-negative SQLite integer")
        deadline_at = self._number(deadline_at, "deadline_at", minimum=0.0)
        self._require_shared_transaction(connection)
        current = self._run_control_snapshot(connection, run_id)
        if current is not None:
            if current["max_claims"] != max_claims or current["deadline_at"] != deadline_at:
                raise IdempotencyConflictError(
                    "managed Run was registered with different budget limits"
                )
            return current
        connection.execute(
            "INSERT INTO kernel_run_controls "
            "(run_id,control_epoch,generation,state,max_claims,claims_used,deadline_at) "
            "VALUES(?,0,0,'paused',?,0,?)",
            (run_id, max_claims, deadline_at),
        )
        return self._run_control_snapshot(connection, run_id)

    def set_run_control(
        self,
        run_id: str,
        *,
        expected_epoch: int,
        state: str,
        generation: int,
        drain_execution_ids=(),
    ) -> dict:
        """CAS a durable control epoch and replace its scoped drain set."""

        run_id = self._managed_run_id(run_id)
        with self._transaction() as (connection, _timestamp):
            return self.set_run_control_in_transaction(
                connection,
                run_id,
                expected_epoch=expected_epoch,
                state=state,
                generation=generation,
                drain_execution_ids=drain_execution_ids,
            )

    def set_run_control_in_transaction(
        self,
        connection,
        run_id: str,
        *,
        expected_epoch: int,
        state: str,
        generation: int,
        drain_execution_ids=(),
    ) -> dict:
        """Apply the control CAS inside a caller-owned shared-file transaction.

        The caller must have acquired ``BEGIN IMMEDIATE`` and owns commit or
        rollback. Separate database files cannot share this transaction.
        """

        run_id = self._managed_run_id(run_id)
        if type(expected_epoch) is not int or expected_epoch < 0:
            raise ValueError("expected_epoch must be a non-negative integer")
        if expected_epoch >= MAX_SQLITE_INTEGER:
            raise ValueError("expected_epoch cannot be advanced")
        if type(state) is not str or state not in {"active", "pausing", "paused"}:
            raise ValueError("state must be active, pausing, or paused")
        generation = self._managed_generation(generation)
        drain_ids = self._normalize_drain_ids(drain_execution_ids)
        if state != "pausing" and drain_ids:
            raise ValueError("drain_execution_ids are only valid while pausing")
        self._require_shared_transaction(connection)

        current = self._run_control_snapshot(connection, run_id)
        if current is None:
            raise ExecutionNotFoundError(f"managed Run control {run_id!r} is not registered")
        target_epoch = expected_epoch + 1
        if current["control_epoch"] == target_epoch:
            if (
                current["state"] == state
                and current["generation"] == generation
                and current["drain_execution_ids"] == drain_ids
            ):
                return current
            raise CASConflictError("managed Run control epoch already has different content")
        if current["control_epoch"] != expected_epoch:
            raise CASConflictError("managed Run control epoch changed")
        if generation < current["generation"]:
            raise ValueError("managed Run generation cannot move backwards")

        if drain_ids:
            placeholders = ",".join("?" for _ in drain_ids)
            rows = connection.execute(
                "SELECT execution_id FROM kernel_managed_executions "
                f"WHERE run_id=? AND generation=? AND execution_id IN ({placeholders})",
                (run_id, generation, *drain_ids),
            ).fetchall()
            if {row[0] for row in rows} != set(drain_ids):
                raise ValueError(
                    "each drain execution must already be registered to this Run and generation"
                )

        cursor = connection.execute(
            "UPDATE kernel_run_controls SET control_epoch=?,generation=?,state=? "
            "WHERE run_id=? AND control_epoch=?",
            (target_epoch, generation, state, run_id, expected_epoch),
        )
        self._cas(cursor, "managed Run control")
        connection.execute(
            "UPDATE kernel_managed_executions SET drain_allowed=0 WHERE run_id=?",
            (run_id,),
        )
        for execution_id in drain_ids:
            cursor = connection.execute(
                "UPDATE kernel_managed_executions SET drain_allowed=1 "
                "WHERE run_id=? AND generation=? AND execution_id=?",
                (run_id, generation, execution_id),
            )
            self._cas(cursor, "managed Run drain registration")
        return self._run_control_snapshot(connection, run_id)

    def submit(self, command: ExecutionCommandV2) -> ExecutionSnapshot:
        if type(command) is not ExecutionCommandV2:
            raise TypeError("submit requires ExecutionCommandV2")
        if command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            raise StorageIsolationError(
                "reserved managed execution IDs require submit_managed"
            )
        encoded = encode_json(command.to_dict())
        with self._transaction() as (connection, timestamp):
            row, _ = self._submit_in_transaction(command, encoded, connection, timestamp)
            return self._snapshot(row)

    def submit_managed(
        self, command: ExecutionCommandV2, *, run_id: str, generation: int
    ) -> ExecutionSnapshot:
        """Atomically register and queue one opted-in managed execution."""
        return self._submit_managed(command, run_id=run_id, generation=generation)

    def _submit_supervisor(self, command: ExecutionCommandV2, *, run_id: str, generation: int,
                           parent_lease: ExecutionLease, budget_envelope: BudgetEnvelope,
                           timeout_seconds: float = .1) -> ExecutionSnapshot:
        """Bind reserved supervision to its original live source in one commit.

        The supervisor has its own claim allowance and reserved process pool;
        parent limits and attempt/fence remain authoritative at claim and entry.
        This private SDK composition does not relax submit_child's Run rules.
        """
        if type(parent_lease) is not ExecutionLease or type(budget_envelope) is not BudgetEnvelope:
            raise TypeError("supervisor admission requires an original parent lease and budget")
        return self._submit_managed(command, run_id=run_id, generation=generation,
            parent_lease=parent_lease, budget_envelope=budget_envelope, timeout_seconds=timeout_seconds)

    def _submit_managed(self, command: ExecutionCommandV2, *, run_id: str, generation: int,
                        parent_lease: ExecutionLease | None = None,
                        budget_envelope: BudgetEnvelope | None = None,
                        timeout_seconds: float | None = None) -> ExecutionSnapshot:

        if type(command) is not ExecutionCommandV2:
            raise TypeError("submit_managed requires ExecutionCommandV2")
        if not command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            raise ValueError(
                f"managed execution_id must start with {MANAGED_EXECUTION_PREFIX!r}"
            )
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        if command.correlation_id != run_id:
            raise ValueError("managed execution correlation_id must match run_id")
        encoded = encode_json(command.to_dict())
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            control = connection.execute(
                "SELECT generation,state FROM kernel_run_controls WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if control is None:
                raise StorageIsolationError("managed Run control is missing")
            mapping = connection.execute(
                "SELECT run_id,generation FROM kernel_managed_executions "
                "WHERE execution_id=?",
                (command.execution_id,),
            ).fetchone()
            existing = connection.execute(
                "SELECT * FROM kernel_executions WHERE execution_id=? OR idempotency_key=? "
                "ORDER BY CASE WHEN execution_id=? THEN 0 ELSE 1 END LIMIT 1",
                (command.execution_id, command.idempotency_key, command.execution_id),
            ).fetchone()
            if existing is not None:
                if existing["command_json"] != encoded:
                    raise IdempotencyConflictError(
                        "execution_id/idempotency_key already identifies another command"
                    )
                if (
                    mapping is None
                    or mapping["run_id"] != run_id
                    or mapping["generation"] != generation
                ):
                    raise IdempotencyConflictError(
                        "existing execution has no matching managed Run registration"
                    )
                if parent_lease is not None:
                    binding = connection.execute("SELECT parent_execution_id,parent_attempt,parent_fence "
                        "FROM kernel_execution_limits WHERE execution_id=?", (command.execution_id,)).fetchone()
                    if binding is None or tuple(binding) != (
                            parent_lease.execution_id, parent_lease.attempt, parent_lease.fence):
                        raise IdempotencyConflictError("existing supervisor has no matching source binding")
                return self._snapshot(existing)
            if mapping is not None:
                raise StorageIsolationError(
                    "managed execution registration exists without its Kernel execution"
                )
            if control["generation"] != generation:
                raise CASConflictError("managed execution generation is stale")
            if control["state"] != "active":
                raise CASConflictError(
                    "new managed executions may only be accepted by an active Run"
                )
            connection.execute(
                "INSERT INTO kernel_managed_executions "
                "(execution_id,run_id,generation,drain_allowed) VALUES(?,?,?,0)",
                (command.execution_id, run_id, generation),
            )
            row, created = self._submit_in_transaction(
                command, encoded, connection, timestamp
            )
            if not created:
                raise IdempotencyConflictError(
                    "execution was accepted without its managed registration"
                )
            if parent_lease is not None:
                parent = self._assert_lease(connection, parent_lease, timestamp=timestamp, states={"running"})
                self._authorize_managed_operation(connection, parent_lease.execution_id,
                    timestamp=timestamp, operation="supervisor admission")
                self._bind_child_limits(connection, command.execution_id, parent, budget_envelope,
                                        self._child_depth(connection, parent_lease.execution_id) + 1)
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
        if command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            raise StorageIsolationError(
                "reserved managed execution IDs require cancel_managed_before_accept"
            )
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

    def cancel_managed_before_accept(
        self,
        command: ExecutionCommandV2,
        *,
        run_id: str,
        generation: int,
        reason: str = "execution cancelled",
    ) -> ExecutionSnapshot:
        """Atomically bind then cancel a not-yet-accepted managed execution."""

        if type(command) is not ExecutionCommandV2:
            raise TypeError("cancel_managed_before_accept requires ExecutionCommandV2")
        if not command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            raise ValueError(
                f"managed execution_id must start with {MANAGED_EXECUTION_PREFIX!r}"
            )
        if type(reason) is not str or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        if command.correlation_id != run_id:
            raise ValueError("managed execution correlation_id must match run_id")
        encoded = encode_json(command.to_dict())
        with self._transaction() as (connection, timestamp):
            control = connection.execute(
                "SELECT generation FROM kernel_run_controls WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if control is None:
                raise StorageIsolationError("managed Run control is missing")
            mapping = connection.execute(
                "SELECT run_id,generation FROM kernel_managed_executions "
                "WHERE execution_id=?",
                (command.execution_id,),
            ).fetchone()
            existing = connection.execute(
                "SELECT * FROM kernel_executions WHERE execution_id=? OR idempotency_key=? "
                "ORDER BY CASE WHEN execution_id=? THEN 0 ELSE 1 END LIMIT 1",
                (command.execution_id, command.idempotency_key, command.execution_id),
            ).fetchone()
            if existing is not None:
                if existing["command_json"] != encoded:
                    raise IdempotencyConflictError(
                        "execution_id/idempotency_key already identifies another command"
                    )
                if (
                    mapping is None
                    or mapping["run_id"] != run_id
                    or mapping["generation"] != generation
                ):
                    raise IdempotencyConflictError(
                        "existing execution has no matching managed Run registration"
                    )
                return self._snapshot(existing)
            if mapping is not None:
                raise StorageIsolationError(
                    "managed execution registration exists without its Kernel execution"
                )
            if control["generation"] != generation:
                raise CASConflictError("managed execution generation is stale")
            connection.execute(
                "INSERT INTO kernel_managed_executions "
                "(execution_id,run_id,generation,drain_allowed) VALUES(?,?,?,0)",
                (command.execution_id, run_id, generation),
            )
            row, created = self._submit_in_transaction(
                command, encoded, connection, timestamp
            )
            if not created:
                raise IdempotencyConflictError(
                    "execution was accepted without its managed registration"
                )
            result = self._cancelled_result(
                row, command, timestamp=timestamp, reason=reason, effect_ids=[]
            )
            return self._terminal(
                connection, row, result, event_type="cancelled", timestamp=timestamp
            )

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
            self._assert_budget_clock(connection, row["execution_id"])
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
            self._charge_managed_claim(
                connection, row["execution_id"], timestamp=timestamp
            )
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
        execution_id: str | None = None,
        timeout_seconds: float | None = None,
        child_pool: bool | None = None,
    ) -> Optional[ExecutionLease]:
        """Atomically lease and start one queued execution.

        Both canonical transitions and both revisioned events are retained,
        but a runtime crash cannot land between two local commits.  The final
        running row remains fenced and is recovered by normal lease expiry.
        """

        if type(owner) is not str or not owner.strip():
            raise ValueError("owner must be a non-empty string")
        if execution_id is not None and (type(execution_id) is not str or not execution_id.strip()):
            raise ValueError("execution_id must be non-empty")
        revisions = _claim_revisions(registry_revision, registry_revisions)
        floor = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        safety = self._nonnegative_duration(
            start_safety_seconds, "start_safety_seconds"
        )
        if execution_id is not None:
            with self._control_lock(timeout_seconds):
                deadline = self._control_deadline
                limits = self._connection.execute(
                    "SELECT parent_execution_id,envelope_json FROM kernel_execution_limits WHERE execution_id=?",
                    (execution_id,)).fetchone()
            if limits is not None and limits[0] is not None:
                # Sampling waits must release the wrapper lock so an existing
                # live owner can publish its floor. Admission still rechecks
                # the parent relationship and lease in its own transaction.
                from .budget_capture import _KernelBudgetCapture

                envelope = BudgetEnvelope.from_dict(json.loads(limits[1]))
                projected = envelope.recheckpoint(
                    sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
                work = projected.view(sample=projected.checkpoint).remaining_work_seconds
                if work is None or work > 0:
                    if work is not None:
                        work_deadline = time.monotonic() + work
                        deadline = work_deadline if deadline is None else min(deadline, work_deadline)
                    remaining = .1 if deadline is None else deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Kernel control admission budget elapsed")
                    capture = _KernelBudgetCapture(self, limits[0])
                    try:
                        capture(projected, timeout_seconds=min(.1, remaining))
                    except BaseException as exc:
                        if getattr(exc, "budget_sample_token", None) is not None:
                            # Transfer this exact live obligation to the caller's
                            # original retry window; a new sampler cannot own it.
                            exc.budget_sample_owner = capture
                        raise
            if deadline is not None:
                timeout_seconds = deadline - time.monotonic()
                if timeout_seconds <= 0:
                    raise TimeoutError("Kernel control admission budget elapsed")
        return self._claim_and_start(owner, revisions=revisions, floor=floor, safety=safety,
            execution_id=execution_id, timeout_seconds=timeout_seconds, child_pool=child_pool)

    def _claim_and_start(self, owner, *, revisions, floor, safety, execution_id,
                         timeout_seconds, child_pool):
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            self._reap_in_transaction(connection, timestamp)
            row = _next_claim_row(connection, timestamp, revisions, execution_id)
            if row is None:
                return None
            self._assert_budget_clock(connection, row["execution_id"])
            if child_pool is not None:
                relationship = connection.execute(
                    "SELECT parent_execution_id FROM kernel_execution_limits WHERE execution_id=?",
                    (row["execution_id"],)).fetchone()
                if bool(relationship is not None and relationship[0] is not None) != child_pool:
                    # Adoption may have changed the required pool since the
                    # runtime reserved its slot. Leave the work queued.
                    return None
            if execution_id is not None:
                self._assert_child_claim(connection, row["execution_id"], timestamp)
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
            self._charge_managed_claim(
                connection, row["execution_id"], timestamp=timestamp
            )
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

    def _verify_active_lease_readonly(self, lease: ExecutionLease) -> ExecutionSnapshot:
        """Inspect delivery authority without advancing the durable clock.

        Each call reads fresh autocommit state and inherits any enclosing
        control deadline. Business authorization continues to use ``verify``.
        """
        with self._control_lock(None):
            if self._connection.in_transaction:
                raise StorageIsolationError("readonly lease inspection requires autocommit")
            clock = self._connection.execute(
                "SELECT watermark FROM kernel_clock WHERE singleton = 1"
            ).fetchone()
            if clock is None:
                raise RuntimeError("kernel logical clock row is missing")
            timestamp = max(self._wall_time(), self._number(
                clock["watermark"], "clock watermark", minimum=0.0))
            row = self._assert_lease(self._connection, lease, timestamp=timestamp,
                                     states={"leased", "running"})
            return self._snapshot(row)

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
            self._authorize_managed_operation(
                connection,
                lease.execution_id,
                timestamp=timestamp,
                operation="start",
            )
            self._assert_budget_clock(connection, lease.execution_id)
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
            self._authorize_managed_operation(
                connection,
                lease.execution_id,
                timestamp=timestamp,
                operation="lease renewal",
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
