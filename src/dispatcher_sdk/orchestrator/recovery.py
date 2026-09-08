"""Application-scoped recovery inspection and same-Run reopening.

The Run state remains one of the normal four states.  Reopen coordination is
stored separately so a crashed caller can resume the same decision without
inventing another Run identity.  Kernel and application facts are checked
again at commit time; the read-only preflight is diagnostic only.
"""

from dataclasses import dataclass
import json
import math
import sqlite3
from typing import Any, Protocol, TypedDict

from ..execution_kernel import EffectRecord, ExecutionKernel, ExecutionNotFoundError, ExecutionSnapshot
from ..execution_kernel._sandbox_registry import journal_paths
from ..execution_kernel.sandbox import validate_sandbox_schema
from ..storage import _read_only
from .contracts import (CommandConflict, OrchestrationError, RevisionConflict,
                        TERMINAL, canonical, clone, digest,
                        identifier, integer, validate_operation)
from .types import RunSnapshot


_UNSET = object()
_RECOVERY_ACTIVE = frozenset(("preparing", "prepared", "committed"))


class RecoveryRecord(TypedDict, total=False):
    recovery_id: str
    run_id: str
    command_id: str
    request_digest: str
    source_generation: int
    target_generation: int
    status: str
    actor: str
    authorization_source: str
    reason: str
    target_deployment: dict[str, Any]
    source_deployment: dict[str, Any]
    decision: dict[str, Any]
    application_state: Any
    owner_id: str
    owner_fence: int
    lease_until: float
    waiters: int
    manifest: dict[str, Any]
    settlement_proof: dict[str, Any]
    error: dict[str, Any] | None


def _now(orchestrator) -> float:
    value = orchestrator.clock()
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise OrchestrationError("clock must return a finite nonnegative timestamp")
    return float(value)


def _json(value, name):
    try:
        return canonical(value)
    except OrchestrationError as error:
        raise OrchestrationError(f"{name} must be strict JSON") from error


def _record(row, *, waiters=None):
    value = dict(row)
    for field in ("target_deployment", "decision", "manifest", "application_state", "error"):
        if value.get(field) is not None:
            value[field] = json.loads(value[field])
    if waiters is not None:
        value["waiters"] = waiters
    manifest = value.get("manifest")
    if isinstance(manifest, dict) and "source_deployment" in manifest:
        value["source_deployment"] = manifest["source_deployment"]
    if isinstance(manifest, dict) and "settlement_proof" in manifest:
        value["settlement_proof"] = manifest["settlement_proof"]
    return value


@dataclass(frozen=True)
class RecoveryDetails:
    """One current effect requiring a decision, with its application identity.

    ``attempt`` is the zero-based application attempt index, not the Kernel's
    execution attempt counter. ``run_revision`` identifies the initial Run
    read; it is not an atomic cross-store snapshot revision. Re-query after
    each resolution: an execution can have more than one uncertain effect.
    """

    run_id: str
    run_revision: int
    task_id: str
    attempt: int
    execution: ExecutionSnapshot
    effect: EffectRecord


class _RecoveryReader(Protocol):
    kernel: ExecutionKernel

    def get_run(self, run_id: str) -> RunSnapshot: ...

    def inspect_execution(self, execution_id: str) -> ExecutionSnapshot: ...


class RecoveryMixin:
    @staticmethod
    def _recovery_row(connection, recovery_id):
        row = connection.execute("SELECT * FROM sdk_recoveries WHERE recovery_id=?",
                                 (recovery_id,)).fetchone()
        if row is None:
            raise OrchestrationError("unknown recovery")
        return row

    @staticmethod
    def _active_recovery(connection, run_id):
        return connection.execute(
            "SELECT * FROM sdk_recoveries WHERE run_id=? AND status IN ('preparing','prepared','committed') "
            "ORDER BY created_at LIMIT 1", (run_id,)).fetchone()

    def _recovery_waiters(self, connection, recovery_id, now):
        connection.execute("DELETE FROM sdk_recovery_waiters WHERE recovery_id=? AND lease_until<=?",
                           (recovery_id, now))
        return connection.execute("SELECT COUNT(*) FROM sdk_recovery_waiters WHERE recovery_id=?",
                                  (recovery_id,)).fetchone()[0]

    def _register_recovery_waiter(self, connection, recovery_id, waiter_id, lease_until):
        connection.execute(
            "INSERT INTO sdk_recovery_waiters(recovery_id,waiter_id,lease_until) VALUES(?,?,?) "
            "ON CONFLICT(recovery_id,waiter_id) DO UPDATE SET lease_until=excluded.lease_until",
            (recovery_id, waiter_id, lease_until))

    def get_recovery(self, recovery_id: str) -> dict:
        identifier(recovery_id, "recovery_id")
        connection = self._connect()
        try:
            row = self._recovery_row(connection, recovery_id)
            return _record(row, waiters=self._recovery_waiters(connection, recovery_id, _now(self)))
        finally:
            connection.close()

    def _reopen_facts(self, connection, state, *, include_external=True):
        """Return conservative blockers from the authoritative local views."""
        blockers = []
        if state["state"] not in {"failed", "cancelled"}:
            blockers.append({"code": "run_not_reopenable", "detail": "only failed or cancelled Runs may reopen"})
        if state["state"] == "cancelled":
            blockers.append({"code": "cancellation_authorization_required", "detail": "cancelled recovery requires a separate authorization record"})
        if any(attempt["state"] not in TERMINAL
               for task in state.get("tasks", {}).values()
               for attempt in task.get("attempts", ())):
            blockers.append({"code": "execution_not_settled", "detail": "every historical attempt must be terminal"})
        if any(wait.get("state") == "open" for wait in state.get("waits", {}).values()):
            blockers.append({"code": "open_wait", "detail": "all application waits must be released"})
        pending = connection.execute(
            "SELECT COUNT(*) FROM sdk_outbox WHERE run_id=? AND delivered=0", (state["run_id"],)
        ).fetchone()[0]
        if pending:
            blockers.append({"code": "pending_execution_delivery", "detail": f"{pending} execution intent(s) remain undelivered"})
        result_pending = connection.execute(
            "SELECT COUNT(*) FROM sdk_results r JOIN sdk_executions e ON e.execution_id=r.execution_id "
            "WHERE e.run_id=? AND r.state!='delivered'", (state["run_id"],)
        ).fetchone()[0]
        if result_pending:
            blockers.append({"code": "pending_result_delivery", "detail": f"{result_pending} result(s) remain undelivered"})
        notification_delivery = connection.execute(
            "SELECT COUNT(*) FROM sdk_notifications WHERE state='delivering' "
            "AND json_extract(payload,'$.run_id')=?", (state["run_id"],)
        ).fetchone()[0]
        if notification_delivery:
            blockers.append({"code": "notification_in_flight", "detail": f"{notification_delivery} notification lease(s) are active"})
        inbox_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='notification_inbox_messages'"
        ).fetchone()
        if inbox_table is not None:
            inbox_processing = connection.execute(
                "SELECT COUNT(*) FROM notification_inbox_messages "
                "WHERE state='processing' AND json_extract(payload,'$.run_id')=?",
                (state["run_id"],),
            ).fetchone()[0]
            if inbox_processing:
                blockers.append({"code": "inbox_in_flight", "detail": f"{inbox_processing} inbox lease(s) are active"})
        for task in state.get("tasks", {}).values():
            for attempt in task.get("attempts", ()):
                if not attempt.get("dispatched"):
                    continue
                execution_id = attempt["command"]["execution_id"]
                try:
                    snapshot = self.inspect_execution(execution_id)
                except ExecutionNotFoundError:
                    blockers.append({"code": "execution_missing", "detail": execution_id})
                    continue
                if snapshot.state not in TERMINAL:
                    blockers.append({"code": "kernel_execution_not_settled", "detail": f"{execution_id}: {snapshot.state}"})
                if snapshot.state == "recovery_required":
                    blockers.append({"code": "effect_recovery_required", "detail": execution_id})
                runtime = getattr(self, "runtime", None)
                if runtime is not None:
                    active_keys = set()
                    for attribute in ("_process_supervisors", "_process_registration_events",
                                      "_thread_authority_by_execution"):
                        mapping = getattr(runtime, attribute, None)
                        if isinstance(mapping, dict):
                            active_keys.update(mapping)
                    if any(isinstance(key, tuple) and key and key[0] == execution_id
                           for key in active_keys):
                        blockers.append({"code": "process_cleanup_in_flight", "detail": execution_id})
                journal = getattr(runtime, "cancellation_journal", None) if runtime is not None else None
                if snapshot.state == "cancelled" and journal is not None:
                    try:
                        report = self.inspect_cancellation(
                            state["run_id"], execution_id=execution_id,
                            source_id=journal.source_id,
                            cancellation_journal_path=journal.path,
                        )
                        facts = [item.cleanup for item in report.executions
                                 if item.execution_id == execution_id]
                    except (OSError, sqlite3.Error, ValueError, TypeError, OrchestrationError) as error:
                        facts = []
                        blockers.append({"code": "cleanup_evidence_unavailable",
                                         "detail": f"{execution_id}: {type(error).__name__}"})
                    if not facts or facts[0].status not in {"confirmed", "not_applicable"}:
                        blockers.append({"code": "cleanup_not_confirmed", "detail": execution_id})
                try:
                    outbox = self.kernel.result_outbox_status((execution_id,))
                except (AttributeError, ValueError):
                    outbox = None
                if outbox is not None and (outbox.pending or outbox.delivering or outbox.dead):
                    blockers.append({"code": "kernel_result_not_settled", "detail": execution_id})
                # Sandbox disposal is recorded outside the Kernel database.
                # Read the registered journals without constructing a journal
                # writer or invoking a provider; missing or malformed evidence
                # is conservatively a commit blocker.
                try:
                    kernel_path = getattr(self.kernel, "db_path", None)
                    paths = () if kernel_path is None else journal_paths(kernel_path)
                    for path in paths:
                        with _read_only(path) as journal:
                            journal.execute("BEGIN")
                            validate_sandbox_schema(journal)
                            row = journal.execute(
                                "SELECT cleanup_confirmed FROM sandbox_operations "
                                "WHERE execution_id=?", (execution_id,)).fetchone()
                            if row is not None and not bool(row[0]):
                                blockers.append({"code": "sandbox_cleanup_unconfirmed",
                                                 "detail": execution_id})
                except (OSError, sqlite3.Error, ValueError, TypeError) as error:
                    blockers.append({"code": "sandbox_cleanup_evidence_unavailable",
                                     "detail": f"{execution_id}: {type(error).__name__}"})
        return blockers

    def inspect_reopen(self, run_id: str, *, expected_revision: int | None = None,
                       expected_generation: int | None = None,
                       cancellation_authorization=None) -> dict:
        """Return a bounded, diagnostic-only reopen preflight."""
        identifier(run_id, "run_id")
        if expected_revision is not None:
            integer(expected_revision, "expected_revision")
        if expected_generation is not None:
            integer(expected_generation, "expected_generation")
        if cancellation_authorization is not None:
            if not isinstance(cancellation_authorization, dict):
                raise OrchestrationError("cancellation authorization must be an object")
            cancellation_authorization = clone(cancellation_authorization)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            state = self._load(connection, run_id)
            generation = int(state.get("generation", 0))
            blockers = self._reopen_facts(connection, state)
            if expected_revision is not None and state["revision"] != expected_revision:
                blockers.append({"code": "revision_changed", "detail": "Run revision differs from observation"})
            if expected_generation is not None and generation != expected_generation:
                blockers.append({"code": "generation_changed", "detail": "Run generation differs from observation"})
            if state["state"] == "cancelled" and cancellation_authorization is not None:
                blockers = [item for item in blockers if item["code"] != "cancellation_authorization_required"]
            active = self._active_recovery(connection, run_id)
            if active is not None:
                blockers.append({"code": "recovery_in_progress", "detail": active["recovery_id"]})
            following, chain_end = self._continuation_chain(connection, run_id)
            if following:
                blockers.append({"code": "continuation_exists",
                                 "detail": f"successor={following}; chain_end={chain_end}"})
            return {"run_id": run_id, "revision": state["revision"], "generation": generation,
                    "state": state["state"], "complete": not blockers,
                    "blockers": blockers, "suggestions": self._reopen_suggestions(blockers),
                    "observed_at": _now(self),
                    "continuation_run_id": following,
                    "continuation_chain_end_id": chain_end}
        finally:
            connection.rollback()
            connection.close()

    def _validate_decision(self, decision):
        if not isinstance(decision, dict):
            raise OrchestrationError("decision must be an object")
        value = clone(decision)
        stage = value.get("start_stage")
        if type(stage) is not str or not stage.strip():
            raise OrchestrationError("decision.start_stage is required")
        value.setdefault("reused_artifacts", [])
        value.setdefault("invalidated_artifacts", [])
        value.setdefault("budget_change", None)
        if not isinstance(value["reused_artifacts"], list) or not isinstance(value["invalidated_artifacts"], list):
            raise OrchestrationError("decision artifact lists must be arrays")
        for change, reason in (("budget_change", "budget_reason"),
                               ("deadline_change", "deadline_reason")):
            if value.get(change) is not None:
                identifier(value.get(reason), reason)
        return value

    def _validate_deployment(self, target_deployment):
        if isinstance(target_deployment, str):
            target_deployment = {"registry_revision": target_deployment}
        if not isinstance(target_deployment, dict):
            raise OrchestrationError("target_deployment must identify a concrete runtime binding")
        value = clone(target_deployment)
        revision = value.get("registry_revision")
        identifier(revision, "target_deployment.registry_revision")
        declared_handlers = value.get("handler_revisions")
        if declared_handlers is not None:
            if type(declared_handlers) is not dict or any(
                    type(key) is not str or not key.strip()
                    or type(handler_revision) is not str or not handler_revision.strip()
                    for key, handler_revision in declared_handlers.items()):
                raise OrchestrationError(
                    "target_deployment.handler_revisions must map names to revisions")
        runtime = getattr(self, "runtime", None)
        if runtime is not None:
            allowed = {runtime.registry_revision, *runtime.handler_revisions.values()}
            if revision not in allowed:
                raise OrchestrationError("target deployment registry revision is not installed")
            if declared_handlers is not None:
                unknown = sorted(set(declared_handlers.values()) - allowed)
                if unknown:
                    raise OrchestrationError(
                        "target deployment declares an uninstalled handler revision")
        return value

    @staticmethod
    def _command_binding_matches(command, target_deployment):
        """Check a new command against the declared target handler binding."""
        binding = command.get("registry_revision") if isinstance(command, dict) else None
        if binding == target_deployment.get("registry_revision"):
            return True
        declared = target_deployment.get("handler_revisions")
        if not isinstance(declared, dict):
            return False
        handler_id = command.get("handler_id")
        version = command.get("handler_contract_version")
        keys = (handler_id, f"{handler_id}:{version}", f"{handler_id}@{version}")
        expected = next((declared[key] for key in keys if key in declared), None)
        if expected is not None:
            return binding == expected
        return binding in declared.values()

    @staticmethod
    def _continuation_chain(connection, run_id):
        """Return the direct successor and terminal successor for a Run."""
        row = connection.execute(
            "SELECT next_run_id FROM sdk_run_links WHERE previous_run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            return None, None
        direct = row[0]
        current = direct
        seen = {run_id}
        while True:
            if current in seen:
                raise CommandConflict("Run continuation links contain a cycle")
            seen.add(current)
            row = connection.execute(
                "SELECT next_run_id FROM sdk_run_links WHERE previous_run_id=?", (current,)
            ).fetchone()
            if row is None:
                return direct, current
            current = row[0]

    def _check_reopen_identity(self, connection, run_id, command_id, request_digest):
        row = connection.execute(
            "SELECT * FROM sdk_recoveries WHERE run_id=? AND command_id=?", (run_id, command_id)
        ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise CommandConflict("recovery command identity already has different content")
        return row

    @staticmethod
    def _source_deployment(state):
        revisions = set()
        handlers = []
        for task_id, task in state.get("tasks", {}).items():
            for index, attempt in enumerate(task.get("attempts", ())):
                command = attempt.get("command")
                if not isinstance(command, dict):
                    continue
                revision = command.get("registry_revision")
                if not isinstance(revision, str):
                    continue
                revisions.add(revision)
                handlers.append({
                    "task_id": task_id,
                    "attempt": index,
                    "handler_id": command.get("handler_id"),
                    "handler_contract_version": command.get("handler_contract_version"),
                    "registry_revision": revision,
                })
        return {"registry_revisions": sorted(revisions), "handlers": handlers}

    @staticmethod
    def _settlement_proof(state, checked_at):
        attempts = []
        for task_id, task in state.get("tasks", {}).items():
            for index, attempt in enumerate(task.get("attempts", ())):
                attempts.append({
                    "task_id": task_id,
                    "attempt": index,
                    "execution_id": attempt["command"]["execution_id"],
                    "generation": int(attempt.get("generation", 0)),
                    "state": attempt["state"],
                    "kernel_revision": attempt.get("kernel_revision", 0),
                    "dispatched": bool(attempt.get("dispatched")),
                })
        return {"complete": True, "checked_at": checked_at,
                "run_revision": state["revision"], "run_generation": int(state.get("generation", 0)),
                "attempts": attempts}

    @staticmethod
    def _reopen_suggestions(blockers):
        advice = {
            "execution_not_settled": "settle every historical attempt before reopening",
            "kernel_execution_not_settled": "wait for the Kernel execution to become terminal",
            "effect_recovery_required": "resolve each indeterminate effect explicitly",
            "pending_execution_delivery": "drain or reconcile the SDK execution outbox",
            "pending_result_delivery": "drain the SDK result outbox",
            "kernel_result_not_settled": "drain or reconcile Kernel result delivery",
            "notification_in_flight": "let the notification lease settle before committing",
            "inbox_in_flight": "finish the inbox lease before committing",
            "sandbox_cleanup_unconfirmed": "obtain durable sandbox cleanup evidence",
            "sandbox_cleanup_evidence_unavailable": "restore or inspect the registered sandbox journal",
            "process_cleanup_in_flight": "wait for the old process authority to be reaped",
            "cleanup_not_confirmed": "obtain cancellation cleanup evidence",
            "open_wait": "release all application waits",
            "continuation_exists": "continue the existing successor chain instead",
            "cancellation_authorization_required": "provide a separate cancellation authorization",
            "recovery_in_progress": "query or advance the existing recovery record",
        }
        seen = set()
        result = []
        for blocker in blockers:
            code = blocker["code"]
            if code not in seen:
                seen.add(code)
                result.append(advice.get(code, f"resolve blocker: {code}"))
        return result

    def _lease_owner(self, owner_id):
        identifier(owner_id, "owner_id")
        return owner_id

    def reopen_run(self, run_id: str, *, command_id: str, expected_revision: int,
                   expected_generation: int | None = None, actor: str | None = None,
                   operator: str | None = None, authorization_source: str,
                   reason: str, target_deployment, decision: dict,
                   application_state=_UNSET, operations=None,
                   cancellation_authorization=None, authorization=None,
                   owner_id: str = "reopen-client", lease_seconds: float = 30.0) -> dict:
        """Reopen a terminal Run and execute the application's recovery plan.

        The method is idempotent by ``(run_id, command_id)``.  Preparation is
        persisted separately from the commit and activation records, so a
        caller may safely resume through :meth:`advance_recovery` after a
        process crash.
        """
        identifier(run_id, "run_id")
        identifier(command_id, "command_id")
        integer(expected_revision, "expected_revision")
        if expected_generation is not None:
            integer(expected_generation, "expected_generation")
        actor = actor if actor is not None else operator
        identifier(actor, "actor")
        identifier(authorization_source, "authorization_source")
        identifier(reason, "reason")
        identifier(owner_id, "owner_id")
        if type(lease_seconds) not in (int, float) or not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise OrchestrationError("lease_seconds must be positive and finite")
        if operations is None:
            operations = []
        if type(operations) is not list:
            raise OrchestrationError("operations must be a list")
        values = [validate_operation(value) for value in operations]
        if any(value["kind"] == "finish" for value in values):
            raise OrchestrationError("reopen operations cannot finish the Run")
        decision = self._validate_decision(decision)
        # Normalize only for the idempotency digest.  A replay of an already
        # committed recovery must remain readable even if the process no
        # longer has that deployment installed; fresh work is validated below.
        if isinstance(target_deployment, str):
            target_deployment = {"registry_revision": target_deployment}
        else:
            target_deployment = clone(target_deployment)
        deployment_json = _json(target_deployment, "target_deployment")
        authorization = cancellation_authorization if cancellation_authorization is not None else authorization
        if authorization is not None:
            if not isinstance(authorization, dict):
                raise OrchestrationError("cancellation authorization must be an object")
            authorization = clone(authorization)
        request = {"kind": "reopen_run", "run_id": run_id, "command_id": command_id,
                   "expected_revision": expected_revision, "expected_generation": expected_generation,
                   "actor": actor, "authorization_source": authorization_source, "reason": reason,
                   "target_deployment": json.loads(deployment_json), "decision": decision,
                   "application_state": None if application_state is _UNSET else clone(application_state),
                   "has_application_state": application_state is not _UNSET,
                   "operations": values, "cancellation_authorization": authorization,
                   }
        request_digest = digest(request)
        now = _now(self)
        waiter_conflict = None
        replay_record = None
        with self._transaction() as connection:
            replay = self._check_reopen_identity(connection, run_id, command_id, request_digest)
            if replay is not None:
                record = _record(replay, waiters=self._recovery_waiters(connection, replay["recovery_id"], now))
                if record["status"] in _RECOVERY_ACTIVE and owner_id != record["owner_id"]:
                    self._register_recovery_waiter(connection, record["recovery_id"], owner_id,
                                                    now + float(lease_seconds))
                    record["waiters"] = self._recovery_waiters(connection, record["recovery_id"], now)
                replay_record = record
            else:
                command_row = connection.execute(
                    "SELECT digest FROM sdk_commands WHERE run_id=? AND command_id=?",
                    (run_id, command_id)).fetchone()
                if command_row is not None:
                    raise CommandConflict("command identity is already used by another operation")
                target_deployment = self._validate_deployment(target_deployment)
                deployment_json = _json(target_deployment, "target_deployment")
                state = self._load(connection, run_id)
                generation = int(state.get("generation", 0))
                if expected_generation is not None and expected_generation != generation:
                    raise RevisionConflict("run generation changed")
                if generation and expected_generation is None:
                    raise RevisionConflict("expected_generation is required after Run recovery")
                if state["revision"] != expected_revision:
                    raise RevisionConflict("run revision changed")
                if state["state"] == "succeeded":
                    raise OrchestrationError("successful Run cannot be reopened")
                if state["state"] == "cancelled" and authorization is None:
                    raise OrchestrationError("cancelled Run requires a separate cancellation authorization")
                following, chain_end = self._continuation_chain(connection, run_id)
                if following:
                    raise CommandConflict(
                        f"Run already has a continuation: successor={following}; chain_end={chain_end}")
                active = self._active_recovery(connection, run_id)
                if active is not None and active["command_id"] != command_id:
                    self._register_recovery_waiter(connection, active["recovery_id"], owner_id,
                                                    now + float(lease_seconds))
                    waiter_conflict = active["recovery_id"]
                else:
                    blockers = self._reopen_facts(connection, state)
                    blockers = [item for item in blockers if not (
                        item["code"] == "cancellation_authorization_required" and authorization is not None)]
                    if blockers:
                        raise OrchestrationError("reopen blocked: " + "; ".join(
                            f"{item['code']}: {item['detail']}" for item in blockers))
                    recovery_id = digest(["dispatcher-sdk.reopen.v1", run_id, command_id, request_digest])[:32]
                    prior = connection.execute("SELECT MAX(owner_fence) FROM sdk_recoveries WHERE run_id=?", (run_id,)).fetchone()[0] or 0
                    settlement_proof = self._settlement_proof(state, now)
                    manifest = {"source_revision": expected_revision, "source_generation": generation,
                                "source_deployment": self._source_deployment(state),
                                "target_generation": generation + 1, "operations": values,
                                "decision": decision, "authorization": authorization,
                                "has_application_state": application_state is not _UNSET,
                                "settlement_proof": settlement_proof}
                    connection.execute(
                        "INSERT INTO sdk_recoveries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (recovery_id, run_id, command_id, request_digest, generation, generation + 1,
                         "preparing", actor, authorization_source, reason, deployment_json,
                         _json(decision, "decision"),
                         None if application_state is _UNSET else _json(application_state, "application_state"),
                         owner_id, prior + 1, now + float(lease_seconds), 0, _json(manifest, "manifest"),
                         None, now, now, None, None))
                    connection.execute("UPDATE sdk_recoveries SET status='prepared',updated_at=? WHERE recovery_id=?",
                                       (now, recovery_id))
        if waiter_conflict is not None:
            raise CommandConflict(f"Run already has recovery {waiter_conflict}")
        if replay_record is not None:
            if replay_record["status"] == "committed":
                return self.advance_recovery(replay_record["recovery_id"], owner_id=owner_id)
            return replay_record
        # The preparation record survives a caller crash.  It contains the
        # complete immutable decision, so a later host can safely commit it.
        self._failpoint("after_recovery_prepare")
        return self.advance_recovery(recovery_id, owner_id=owner_id)

    def _advance_recovery_locked(self, connection, recovery_id, owner_id, now, *,
                                 state=None, values=None, application_state=_UNSET):
        row = self._recovery_row(connection, recovery_id)
        if row["owner_id"] != owner_id or row["lease_until"] <= now:
            raise OrchestrationError("recovery owner lease is stale")
        if row["status"] == "activated":
            return _record(row, waiters=self._recovery_waiters(connection, recovery_id, now))
        if row["status"] == "aborted":
            return _record(row)
        if state is None:
            state = self._load(connection, row["run_id"])
        if values is None:
            values = json.loads(row["manifest"])["operations"]
        if row["status"] == "preparing":
            connection.execute("UPDATE sdk_recoveries SET status='prepared',updated_at=? WHERE recovery_id=?",
                               (now, recovery_id))
            row = self._recovery_row(connection, recovery_id)
        # The commit is deliberately explicit and immutable.  Run state changes
        # are kept in this transaction with history, events, receipts and intents.
        if row["status"] == "prepared":
            self._validate_deployment(json.loads(row["target_deployment"]))
            if state["state"] not in {"failed", "cancelled"}:
                raise OrchestrationError("Run changed while recovery was preparing")
            if state["revision"] != json.loads(row["manifest"])["source_revision"]:
                raise RevisionConflict("Run revision changed while recovery was preparing")
            manifest = json.loads(row["manifest"])
            blockers = self._reopen_facts(connection, state)
            if manifest.get("authorization") is not None:
                blockers = [item for item in blockers
                            if item["code"] != "cancellation_authorization_required"]
            if blockers:
                raise OrchestrationError("reopen blocked at commit: " + "; ".join(
                    f"{item['code']}: {item['detail']}" for item in blockers))
            target_generation = row["target_generation"]
            state["state"] = "running"
            state["generation"] = target_generation
            manifest = json.loads(row["manifest"])
            if application_state is not _UNSET:
                state["application_state"] = clone(application_state)
            elif manifest.get("has_application_state"):
                state["application_state"] = (None if row["application_state"] is None
                                                else json.loads(row["application_state"]))
            target_deployment = json.loads(row["target_deployment"])
            target_revision = target_deployment["registry_revision"]
            allowed_bindings = {target_revision}
            declared_handlers = target_deployment.get("handler_revisions")
            if isinstance(declared_handlers, dict):
                allowed_bindings.update(declared_handlers.values())
            runtime = getattr(self, "runtime", None)
            if (runtime is not None and target_revision == runtime.registry_revision
                    and declared_handlers is None):
                allowed_bindings.update(runtime.handler_revisions.values())
            intents = []
            registrations = []
            changes = set()
            for op in values:
                if op["kind"] == "watch_task":
                    self._register_watch(connection, state, op)
                    continue
                if op["kind"] in {"add_task", "new_attempt"}:
                    binding = op["command"].get("registry_revision")
                    if (binding not in allowed_bindings
                            and binding not in (declared_handlers or {}).values()):
                        raise OrchestrationError("recovery command is bound to a different deployment")
                    if (declared_handlers is not None
                            and not self._command_binding_matches(op["command"], target_deployment)):
                        raise OrchestrationError("recovery command handler binding differs from target deployment")
                if op["kind"] == "dispatch":
                    task = state["tasks"].get(op["task_id"])
                    if task is None or int(task["attempts"][-1].get("generation", 0)) != target_generation:
                        raise OrchestrationError(
                            "recovery dispatch must target a new-generation attempt")
                intents.extend(self._reduce_reopen_operation(state, op))
                if "task_id" in op:
                    task_id = op["task_id"]
                    task = state["tasks"][task_id]
                    index = len(task["attempts"]) - 1
                    changes.add(("attempt", canonical([task_id, index])))
                    if op["kind"] in {"add_task", "set_dependencies"}:
                        changes.add(("task", task_id))
                    if op["kind"] in {"add_task", "new_attempt"}:
                        task["attempts"][index]["generation"] = target_generation
                        registrations.append((task_id, index, task["attempts"][index]))
                elif "wait_id" in op:
                    changes.add(("waits", op["wait_id"]))
                elif "signal_id" in op:
                    changes.add(("signals", op["signal_id"]))
            self._register_executions(connection, state, registrations)
            for ordinal, intent in enumerate(intents):
                intent["generation"] = target_generation
                connection.execute("INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) VALUES(?,?,?,?)",
                                   (row["run_id"], row["command_id"], ordinal, canonical(intent)))
            state["revision"] += 1
            self._save(connection, state, changes=changes)
            self._event(connection, state, "run.reopened", {
                "recovery_id": recovery_id, "source_generation": row["source_generation"],
                "target_generation": target_generation, "decision": json.loads(row["decision"]),
                "source_deployment": manifest.get("source_deployment", {"registry_revisions": []}),
                "target_deployment": json.loads(row["target_deployment"]),
            })
            connection.execute(
                "UPDATE sdk_recoveries SET status='committed',committed_at=?,updated_at=? WHERE recovery_id=?",
                (now, now, recovery_id))
            self._write_receipt(connection, row["run_id"], row["command_id"], row["request_digest"], state)
            row = self._recovery_row(connection, recovery_id)
        return _record(row, waiters=self._recovery_waiters(connection, recovery_id, now))

    @staticmethod
    def _reduce_reopen_operation(state, op):
        # The normal reducer's terminal guard is correct for ordinary calls;
        # reopening changes the Run to running only after all old history is
        # checked, so this small adapter uses the same mechanical reducer.
        from .reducer import reduce_operation
        return reduce_operation(state, op)

    def _activate_recovery(self, recovery_id: str) -> dict:
        """Durably finish the post-commit activation step.

        The commit transaction intentionally ends with ``committed``.  This
        gives a crash, a Kernel outage, or a failpoint a durable point from
        which a later host can continue without repeating the Run mutation.
        The current SDK Kernel has no cross-database activation transaction, so
        the local activation marker is idempotent and is advanced separately.
        """
        identifier(recovery_id, "recovery_id")
        with self._transaction() as connection:
            row = self._recovery_row(connection, recovery_id)
            if row["status"] == "committed":
                now = _now(self)
                connection.execute(
                    "UPDATE sdk_recoveries SET status='activated',activated_at=?,updated_at=? "
                    "WHERE recovery_id=? AND status='committed'",
                    (now, now, recovery_id))
                connection.execute("DELETE FROM sdk_recovery_waiters WHERE recovery_id=?", (recovery_id,))
                row = self._recovery_row(connection, recovery_id)
            return _record(row, waiters=self._recovery_waiters(connection, recovery_id, _now(self)))

    def advance_recovery(self, recovery_id: str, *, owner_id: str | None = None) -> dict:
        identifier(recovery_id, "recovery_id")
        committed = False
        with self._transaction() as connection:
            row = self._recovery_row(connection, recovery_id)
            owner_id = owner_id or row["owner_id"]
            identifier(owner_id, "owner_id")
            now = _now(self)
            if row["status"] in _RECOVERY_ACTIVE and row["lease_until"] <= now:
                # Takeover is itself fenced in the SDK transaction.  The old
                # holder may reclaim under the same logical owner identity,
                # but only with a higher fence. It cannot make a new decision
                # with the expired owner fence.
                new_fence = row["owner_fence"] + 1
                connection.execute(
                    "UPDATE sdk_recoveries SET owner_id=?,owner_fence=?,lease_until=?,updated_at=? "
                    "WHERE recovery_id=? AND owner_fence=? AND lease_until<=?",
                    (owner_id, new_fence, now + 30.0, now, recovery_id,
                     row["owner_fence"], row["lease_until"]))
                row = self._recovery_row(connection, recovery_id)
            if row["status"] in {"preparing", "prepared"}:
                self._advance_recovery_locked(connection, recovery_id, owner_id, now)
                row = self._recovery_row(connection, recovery_id)
            committed = row["status"] == "committed"
            result = _record(row, waiters=self._recovery_waiters(connection, recovery_id, now))
        if committed:
            # The decision and Run mutation are already durable.  If this
            # fails, the persisted committed record is safe for host resume.
            self._failpoint("after_recovery_commit")
            return self._activate_recovery(recovery_id)
        return result

    def abort_recovery(self, recovery_id: str, *, owner_id: str | None = None,
                       reason: str = "recovery aborted") -> dict:
        identifier(recovery_id, "recovery_id")
        identifier(reason, "reason")
        with self._transaction() as connection:
            row = self._recovery_row(connection, recovery_id)
            owner_id = owner_id or row["owner_id"]
            if row["owner_id"] != owner_id or row["lease_until"] <= _now(self):
                raise OrchestrationError("recovery owner lease is stale")
            if row["status"] in {"committed", "activated"}:
                raise OrchestrationError("committed recovery can only roll forward")
            now = _now(self)
            connection.execute("UPDATE sdk_recoveries SET status='aborted',error=?,updated_at=? WHERE recovery_id=?",
                               (canonical({"code": "aborted", "message": reason}), now, recovery_id))
            connection.execute("DELETE FROM sdk_recovery_waiters WHERE recovery_id=?", (recovery_id,))
            return _record(self._recovery_row(connection, recovery_id), waiters=0)

    def renew_recovery(self, recovery_id: str, *, owner_id: str,
                       lease_seconds: float = 30.0) -> dict:
        """Extend an active recovery lease without changing its decision."""
        identifier(recovery_id, "recovery_id")
        identifier(owner_id, "owner_id")
        if type(lease_seconds) not in (int, float) or not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise OrchestrationError("lease_seconds must be positive and finite")
        with self._transaction() as connection:
            now = _now(self)
            row = self._recovery_row(connection, recovery_id)
            if row["owner_id"] != owner_id or row["lease_until"] <= now:
                raise OrchestrationError("recovery owner lease is stale")
            if row["status"] not in _RECOVERY_ACTIVE:
                return _record(row)
            connection.execute("UPDATE sdk_recoveries SET lease_until=?,updated_at=? WHERE recovery_id=?",
                               (now + float(lease_seconds), now, recovery_id))
            return _record(self._recovery_row(connection, recovery_id),
                           waiters=self._recovery_waiters(connection, recovery_id, now))

    def resume_recoveries(self, *, limit: int = 20, owner_id: str = "recovery-host") -> int:
        """Advance persisted recoveries after a coordinator restart."""
        if type(limit) is not int or limit < 1:
            raise OrchestrationError("limit must be positive")
        identifier(owner_id, "owner_id")
        connection = self._connect()
        try:
            ids = [row[0] for row in connection.execute(
                "SELECT recovery_id FROM sdk_recoveries WHERE status IN ('preparing','prepared','committed') "
                "ORDER BY created_at LIMIT ?", (limit,)).fetchall()]
        finally:
            connection.close()
        advanced = 0
        for recovery_id in ids:
            try:
                record = self.advance_recovery(recovery_id, owner_id=owner_id)
            except OrchestrationError:
                # A live owner retains the lease; its own process remains
                # responsible for completing the immutable decision.
                continue
            if record["status"] in {"committed", "activated"}:
                advanced += 1
        return advanced

    def _has_active_recovery(self, connection, run_id):
        return self._active_recovery(connection, run_id) is not None

    def inspect_recoveries(self: _RecoveryReader, run_id: str) -> list[RecoveryDetails]:
        """Read current recovery pointers for this Run without syncing or reaping.

        Kernel authority is inspected even when the persisted Run view is stale.
        Only dispatched current application attempts are considered. Pending
        command deliveries without a Kernel execution are skipped. Each effect
        is paired with an unchanged execution revision using bounded re-reads;
        continuous changes raise ``RevisionConflict`` for the caller to retry.
        Different entries are not one atomic snapshot. Resolution must still
        use the effect's revision and an explicit, stable recovery identity.
        """
        state = self.get_run(run_id)
        result = []
        for task_id, task in state["tasks"].items():
            index = len(task["attempts"]) - 1
            attempt = task["attempts"][index]
            if not attempt["dispatched"]:
                continue
            execution_id = attempt["command"]["execution_id"]
            for _ in range(3):
                try:
                    execution = self.inspect_execution(execution_id)
                except ExecutionNotFoundError:
                    if attempt["kernel_revision"]:
                        raise
                    break
                if execution.state != "recovery_required":
                    break
                if execution.recovery_effect_id is None:
                    raise OrchestrationError("Kernel recovery execution has no effect")
                effect = self.kernel.get_effect(execution.recovery_effect_id)
                after = self.inspect_execution(execution_id)
                if after.revision != execution.revision:
                    continue
                if (type(effect) is not EffectRecord
                        or effect.effect_id != execution.recovery_effect_id
                        or effect.execution_id != execution_id
                        or effect.state != "indeterminate"):
                    raise OrchestrationError("Kernel recovery effect does not match the execution")
                result.append(RecoveryDetails(
                    run_id, state["revision"], task_id, index, execution, effect))
                break
            else:
                raise RevisionConflict("recovery changed during inspection; retry the query")
        return result


__all__ = ["RecoveryDetails", "RecoveryRecord"]
