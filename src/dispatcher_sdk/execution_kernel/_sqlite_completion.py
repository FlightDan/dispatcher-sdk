"""Execution completion, retry, cancellation, and terminal invariants."""

from __future__ import annotations

import sqlite3
import json
import time
from typing import Any, Optional
import uuid

from ._sqlite_base import encode_json
from .budget import BudgetEnvelope, sample_clock
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
    StorageIsolationError,
)
from .transitions import TERMINAL_STATES, reduce_state


class ExecutionCompletionMixin:
    def _is_committed_supervisor_result(self, lease: ExecutionLease, result: ExecutionResultV2,
                                       *, timeout_seconds: float, max_record_bytes: int = 256 * 1024) -> bool:
        """Inspect an exact already-committed result; never perform completion."""
        deadline = time.monotonic() + timeout_seconds
        with self._control_lock(timeout_seconds):
            if time.monotonic() >= deadline:
                raise TimeoutError('supervisor result proof budget elapsed')
            self._connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
            try:
                self._connection.execute('BEGIN')
                return self._committed_supervisor_retry_in_snapshot(lease, result, max_record_bytes, deadline)
            except sqlite3.OperationalError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError('supervisor result proof budget elapsed') from exc
                raise
            finally:
                self._connection.set_progress_handler(None, 0)
                self._connection.rollback()

    def _committed_supervisor_retry_in_snapshot(self, lease: ExecutionLease, result: ExecutionResultV2,
                                                max_record_bytes: int, deadline: float) -> bool:
        def check_time():
            if time.monotonic() >= deadline:
                raise TimeoutError('supervisor result proof budget elapsed')

        row = self._connection.execute(
            'SELECT attempt,fence,state,length(CAST(result_json AS BLOB)) AS result_bytes '
            'FROM kernel_executions WHERE execution_id=?', (lease.execution_id,)).fetchone()
        if row is None:
            return False
        # Later claims or cancellation cannot erase this historical receipt.
        # A different fence at the same attempt is not this generation.
        if (row['attempt'] < lease.attempt or
                (row['attempt'] == lease.attempt and row['fence'] != lease.fence) or
                (row['attempt'] > lease.attempt and row['fence'] <= lease.fence)):
            return False
        obligation = self._connection.execute(
            'SELECT length(CAST(resolution_json AS BLOB)) FROM kernel_supervisor_obligations '
            'WHERE execution_id=? AND attempt=? AND fence=?',
            (lease.execution_id, lease.attempt, lease.fence)).fetchone()
        if obligation is None or obligation[0] is None:
            return False
        if obligation[0] > max_record_bytes:
            raise TimeoutError('supervisor resolution exceeds proof byte budget')
        obligation = self._connection.execute(
            'SELECT resolution_json FROM kernel_supervisor_obligations WHERE execution_id=? AND attempt=? AND fence=?',
            (lease.execution_id, lease.attempt, lease.fence)).fetchone()
        expected = {'source': 'sdk_confirmed_supervisor_cleanup', 'result_id': result.result_id,
                    'status': result.status}
        resolution = json.loads(obligation[0])
        if resolution != expected and resolution != {**expected, 'source': 'sdk_supervisor_not_invoked'}:
            return False
        check_time()
        if ((row['attempt'], row['fence']) == (lease.attempt, lease.fence)
                and row['state'] in TERMINAL_STATES and row['result_bytes'] is not None):
            if row['result_bytes'] > max_record_bytes:
                raise TimeoutError('terminal result exceeds proof byte budget')
            saved = json.loads(self._connection.execute('SELECT result_json FROM kernel_executions WHERE execution_id=?',
                                                        (lease.execution_id,)).fetchone()[0])
            check_time()
            matched = encode_json(saved) == encode_json(result.to_dict())
            check_time()
            if matched:
                return True
            if (isinstance(saved, dict) and saved.get('status') == 'dead'
                    and isinstance(saved.get('error'), dict)
                    and saved['error'].get('code') == 'retry_exhausted'
                    and isinstance(saved['error'].get('details'), dict)
                    and encode_json(saved['error']['details'].get('last_result')) == encode_json(result.to_dict())):
                check_time()
                return True
        event = self._connection.execute(
            "SELECT length(CAST(data_json AS BLOB)) FROM kernel_events WHERE execution_id=? AND revision=? "
            "AND event_type='retry_scheduled' LIMIT 1",
            (lease.execution_id, lease.revision + 1)).fetchone()
        if event is None:
            return False
        if event[0] > max_record_bytes:
            raise TimeoutError('retry event exceeds proof byte budget')
        event = self._connection.execute(
            "SELECT data_json FROM kernel_events WHERE execution_id=? AND revision=? "
            "AND event_type='retry_scheduled' LIMIT 1", (lease.execution_id, lease.revision + 1)).fetchone()
        data = json.loads(event[0])
        check_time()
        matched = isinstance(data, dict) and 'result' in data and encode_json(data['result']) == encode_json(result.to_dict())
        check_time()
        return matched

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
        *,
        budget_envelope: BudgetEnvelope | None = None,
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
        accepted_at = timestamp
        if budget_envelope is not None:
            # Exact ownership and causal identity above precede SDK receipt
            # evidence. Its verified clock continuity can prove elapsed time
            # after rollback, without changing the lease or global wall clock.
            retained = self._tighten_completion_budget(connection, row, lease, budget_envelope)
            effective = retained.checkpoint.effective_time(sample_clock(wall_time=timestamp))
            if effective is not None:
                accepted_at = max(accepted_at, effective)
        if result.completed_at > accepted_at or result.completed_at > lease.expires_at:
            raise StaleFenceError(
                "result completion time is after acceptance or lease expiry",
                context={
                    "completed_at": result.completed_at,
                    "accepted_at": accepted_at,
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

    def complete(self, lease: ExecutionLease, result: ExecutionResultV2, *,
                 timeout_seconds: float | None = None) -> ExecutionSnapshot:
        return self._complete_result(lease, result, timeout_seconds=timeout_seconds)

    def _restore_completion(self, lease: ExecutionLease, result: ExecutionResultV2, *,
                            timeout_seconds: float = .1) -> ExecutionSnapshot:
        """Settle a retained result without granting expired business authority.

        The exact lease, attempt, fence and revision must still own the row;
        completion must have happened before its original lease expiry. A
        cancel, reap or subsequent claim therefore wins over this receipt.
        """
        return self._complete_result(lease, result, timeout_seconds=timeout_seconds,
                                     settlement=True)

    def _complete_sdk_result(self, lease: ExecutionLease, result: ExecutionResultV2, *,
                             budget_envelope: BudgetEnvelope | None,
                             timeout_seconds: float = .1,
                             settlement: bool = False,
                             supervisor_cleanup_confirmed: bool = False,
                             supervisor_not_invoked: bool = False,
                             supervisor_registration_uncertain: bool = False) -> ExecutionSnapshot:
        """Settle original SDK result and its observed budget in one transaction."""
        return self._complete_result(lease, result, timeout_seconds=timeout_seconds,
                                     settlement=settlement, budget_envelope=budget_envelope,
                                     supervisor_cleanup_confirmed=supervisor_cleanup_confirmed,
                                     supervisor_not_invoked=supervisor_not_invoked,
                                     supervisor_registration_uncertain=supervisor_registration_uncertain)

    def reconcile_supervisor_result(self, credential: Any, *, lease: ExecutionLease,
                                    result: ExecutionResultV2, budget_envelope: BudgetEnvelope,
                                    kernel_store_id: str, cleanup_evidence: str) -> ExecutionSnapshot:
        """Apply an independently host-verified original result and cleanup decision.

        A settlement journal observation alone is not authority. The configured
        verifier must authenticate the complete decision and its permission.
        """
        if type(lease) is not ExecutionLease or type(result) is not ExecutionResultV2:
            raise TypeError("reconciliation requires an exact lease and result")
        if type(budget_envelope) is not BudgetEnvelope:
            raise TypeError("reconciliation requires the original budget envelope")
        if type(cleanup_evidence) is not str or not cleanup_evidence.strip():
            raise ValueError("cleanup evidence must be non-empty")
        if type(kernel_store_id) is not str or not kernel_store_id.strip():
            raise ValueError("kernel store identity must be non-empty")
        decision = {"kernel_store_id": kernel_store_id, "lease": lease.to_dict(), "result": result.to_dict(),
                    "budget_envelope": budget_envelope.to_dict(), "cleanup": "confirmed",
                    "cleanup_evidence": cleanup_evidence}
        if len(encode_json(decision).encode("utf-8")) > 65536:
            raise ValueError("reconciliation decision exceeds its bound")
        return self._complete_result(lease, result, settlement=True, budget_envelope=budget_envelope,
                                     host_reconciliation=(credential, decision))

    def _complete_result(self, lease: ExecutionLease, result: ExecutionResultV2, *,
                         timeout_seconds: float | None = None,
                         settlement: bool = False,
                         budget_envelope: BudgetEnvelope | None = None,
                         supervisor_cleanup_confirmed: bool = False,
                         supervisor_not_invoked: bool = False,
                         supervisor_registration_uncertain: bool = False,
                         host_reconciliation: tuple[Any, dict] | None = None) -> ExecutionSnapshot:
        if type(lease) is not ExecutionLease:
            raise TypeError("complete requires ExecutionLease")
        if type(result) is not ExecutionResultV2:
            raise TypeError("complete requires ExecutionResultV2")
        if budget_envelope is not None and type(budget_envelope) is not BudgetEnvelope:
            raise TypeError("budget must be a BudgetEnvelope or None")
        if type(supervisor_cleanup_confirmed) is not bool:
            raise TypeError("supervisor_cleanup_confirmed must be a bool")
        if type(supervisor_not_invoked) is not bool or (supervisor_not_invoked and supervisor_cleanup_confirmed):
            raise TypeError("supervisor_not_invoked must be an exclusive bool")
        if type(supervisor_registration_uncertain) is not bool or (supervisor_registration_uncertain and not supervisor_not_invoked):
            raise TypeError("uncertain registration requires not-invoked proof")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            host_record = None
            if host_reconciliation is not None:
                credential, decision = host_reconciliation
                def verify_host():
                    try:
                        proof = self._authority_verifier(credential)
                        principal = proof["principal"]
                        store = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
                        if (type(principal) is not str or not principal.strip() or
                            store is None or store[0] != decision["kernel_store_id"] or
                            self._number(proof["expires_at"], "authority expiry", minimum=0.0) <= self._advance_clock(connection) or
                            encode_json(proof["supervisor_result_reconciliation"]) != encode_json(decision) or
                            not any(tuple(p) == (lease.execution_id, "kernel:reconcile_supervisor_result") for p in proof["permissions"])):
                            raise ValueError("reconciliation authority differs")
                        return principal
                    except Exception:
                        raise StorageIsolationError("host did not authenticate supervisor result reconciliation") from None
                principal = verify_host()
                def recheck_host():
                    if verify_host() != principal:
                        raise StorageIsolationError("supervisor result authority changed")
                self._precommit_authority_checks.append(recheck_host)
                host_record = encode_json({"source": "host_verified_supervisor_result", "principal": principal,
                                           "decision": decision})
                self._assert_budget_clock(connection, lease.execution_id)
                if budget_envelope.checkpoint.effective_time(sample_clock(wall_time=timestamp)) is None:
                    raise StorageIsolationError("reconciliation clock continuity is unknown")
            def resolve_supervisor():
                # An unacknowledged sample on this execution or an ancestor
                # fences cleanup resolution as well as future admission. The
                # check and resolution must share this transaction.
                self._assert_budget_clock(connection, lease.execution_id)
                key = (lease.execution_id, lease.attempt, lease.fence)
                obligation = connection.execute("SELECT resolution_json FROM kernel_supervisor_obligations "
                    "WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone()
                if obligation is None:
                    if supervisor_registration_uncertain:
                        return
                    raise CASConflictError("exact supervisor obligation is unavailable")
                resolution = host_record or encode_json({"source": "sdk_supervisor_not_invoked" if supervisor_not_invoked else "sdk_confirmed_supervisor_cleanup", "result_id": result.result_id,
                                                         "status": result.status})
                if obligation[0] is not None and obligation[0] != resolution:
                    raise CASConflictError("supervisor obligation has a different resolution")
                connection.execute("UPDATE kernel_supervisor_obligations SET resolution_json=? WHERE execution_id=? "
                                   "AND attempt=? AND fence=? AND resolution_json IS NULL", (resolution, *key))
            row = self._get_row(connection, lease.execution_id)
            if host_record is not None:
                if (row["attempt"], row["fence"]) != (lease.attempt, lease.fence):
                    raise StaleFenceError("supervisor execution generation changed")
                obligation = connection.execute("SELECT resolution_json FROM kernel_supervisor_obligations "
                    "WHERE execution_id=? AND attempt=? AND fence=?",
                    (lease.execution_id, lease.attempt, lease.fence)).fetchone()
                if obligation is None:
                    raise CASConflictError("exact supervisor obligation is unavailable")
                if obligation[0] is not None:
                    if obligation[0] != host_record:
                        raise CASConflictError("supervisor obligation has a different resolution")
                    if row["state"] == "queued":
                        event = connection.execute("SELECT data_json FROM kernel_events WHERE execution_id=? "
                            "AND revision=? AND event_type='retry_scheduled' LIMIT 1",
                            (lease.execution_id, lease.revision + 1)).fetchone()
                        if event is None or encode_json(json.loads(event[0])["result"]) != encode_json(result.to_dict()):
                            raise CASConflictError("original retry receipt is unavailable")
                    elif row["state"] in TERMINAL_STATES:
                        saved = self._result(row["result_json"])
                        if saved is None or (saved.to_json() != result.to_json() and not (
                            saved.status == "dead" and saved.error is not None and
                            saved.error.code == "retry_exhausted" and
                            encode_json(saved.error.details.get("last_result")) == encode_json(result.to_dict())
                        )):
                            raise CASConflictError("reconciled terminal result is no longer current")
                    else:
                        raise CASConflictError("reconciled result is no longer current")
                    return self._snapshot(row)
            if row["state"] in TERMINAL_STATES:
                current = self._result(row["result_json"])
                # Dataclass/Python equality is not a wire identity: it folds
                # values such as 1, 1.0, and True together.  Duplicate
                # results must match the exact canonical contract payload.
                if current is not None and current.to_json() == result.to_json():
                    if budget_envelope is not None:
                        self._assert_budget_clock(connection, lease.execution_id)
                        # An earlier exact result receipt does not prove its
                        # independently retained floor reached Kernel storage.
                        self._validate_result(connection, row, lease, result, timestamp,
                                              budget_envelope=budget_envelope)
                    if supervisor_cleanup_confirmed or supervisor_not_invoked or host_record is not None:
                        if (row["attempt"], row["fence"]) != (lease.attempt, lease.fence):
                            raise CASConflictError("supervisor execution generation changed")
                        resolve_supervisor()
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
                connection, lease, timestamp=timestamp, states={"running"},
                settlement=settlement,
            )
            self._authorize_managed_operation(
                connection,
                lease.execution_id,
                timestamp=timestamp,
                operation="execution completion",
                settlement=True,
            )
            if budget_envelope is not None:
                # A retained completion floor cannot establish the current
                # clock while another sample on this lineage is unresolved.
                # Check in the same transaction as result publication even
                # when there is no proof permitting supervisor resolution.
                self._assert_budget_clock(connection, lease.execution_id)
            command = self._validate_result(connection, row, lease, result, timestamp,
                                            budget_envelope=budget_envelope)
            parked = self._park_unfinished_effects(
                connection, row, timestamp, trigger=f"complete:{result.status}"
            )
            if parked is not None:
                return parked
            if supervisor_cleanup_confirmed or supervisor_not_invoked or host_record is not None:
                resolve_supervisor()
            managed_deadline_elapsed = False
            deadline = connection.execute(
                "SELECT c.deadline_at FROM kernel_managed_executions m "
                "JOIN kernel_run_controls c ON c.run_id=m.run_id "
                "WHERE m.execution_id=?", (lease.execution_id,),
            ).fetchone()
            if deadline is not None:
                managed_deadline_elapsed = deadline is not None and deadline[0] <= timestamp
            if self._retryable(result, command) and not managed_deadline_elapsed:
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
        self, lease: ExecutionLease, effect_id: str, *, timeout_seconds: float | None = None
    ) -> ExecutionSnapshot:
        return self._require_effect_recovery(lease, effect_id, timeout_seconds=timeout_seconds)

    def _require_effect_recovery(self, lease: ExecutionLease, effect_id: str, *,
                                 timeout_seconds: float | None = None,
                                 settlement: bool = False) -> ExecutionSnapshot:
        if type(effect_id) is not str or not effect_id.strip():
            raise ValueError("effect_id must be a non-empty string")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = self._assert_lease(
                connection, lease, timestamp=timestamp, states={"running"},
                settlement=settlement,
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
            self._authorize_managed_operation(
                connection,
                lease.execution_id,
                timestamp=timestamp,
                operation="dead-letter transition",
                settlement=True,
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
        expected_supervision: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
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
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = self._get_row(connection, execution_id)
            if expected_supervision is not None:
                self._assert_stall_disposition(connection, row, expected_supervision)
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
            control = connection.execute(
                "SELECT c.state FROM kernel_managed_executions m "
                "LEFT JOIN kernel_run_controls c ON c.run_id=m.run_id "
                "WHERE m.execution_id=?", (execution_id,),
            ).fetchone()
            if control is not None or execution_id.startswith("sdk-managed:"):
                if control is None or control[0] is None:
                    raise StorageIsolationError("managed cancellation lacks Run control")
                if control[0] not in {"pausing", "paused"}:
                    raise CASConflictError(
                        "managed cancellation requires a persisted pause barrier"
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
