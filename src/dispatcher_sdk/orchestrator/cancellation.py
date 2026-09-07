"""Read-only cancellation evidence scoped to Run, Task and execution identities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Literal, TYPE_CHECKING

from ..execution_kernel.cancellation import inspect_cancellation_journal
from ..execution_kernel._sandbox_registry import validate_registry
from ..execution_kernel.sandbox import validate_sandbox_schema
from ..storage import _read_only
from .contracts import OrchestrationError, TERMINAL, canonical, identifier

if TYPE_CHECKING:
    from .engine import Orchestrator


EvidenceStatus = Literal["confirmed", "pending", "unknown", "not_applicable", "failed"]


@dataclass(frozen=True)
class CancellationFact:
    status: EvidenceStatus
    code: str
    source: str
    details: dict[str, Any]


@dataclass(frozen=True)
class ExecutionCancellationReport:
    task_id: str
    application_attempt: int
    execution_id: str
    execution_revision: int | None
    kernel_attempt: int | None
    fence: int | None
    execution_state: str | None
    task_state: str
    task_terminal_state: str | None
    request_committed: CancellationFact
    command_delivered: CancellationFact
    execution_authority_revoked: CancellationFact
    local_process_tree_reaped: CancellationFact
    external_outcome: CancellationFact
    cleanup: CancellationFact
    execution_result_known: bool
    effects: tuple[dict[str, Any], ...]
    effects_truncated: bool
    receipt_ids: tuple[str, ...]
    receipts_truncated: bool
    issues: tuple[str, ...]


@dataclass(frozen=True)
class CancellationRecoveryReport:
    source_id: str | None
    run_id: str
    run_revision: int
    run_state: str
    run_terminal_state: str | None
    observed_at: float
    orchestrator_source: str
    kernel_source: str
    snapshot_consistency: str
    executions: tuple[ExecutionCancellationReport, ...]
    truncated: bool
    next_task_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fact(status: EvidenceStatus, code: str, source: str, **details: Any) -> CancellationFact:
    return CancellationFact(status, code, source, details)


def _sandbox_facts(kernel_connection, snapshot):
    """Read lifecycle records without constructing a journal writer or provider."""
    records, issues = [], []
    if kernel_connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='runtime_sandbox_meta'").fetchone() is None:
        return records, issues
    store_id = validate_registry(kernel_connection)
    paths = [row[0] for row in kernel_connection.execute("SELECT path FROM runtime_sandbox_journals ORDER BY path")]
    for path in paths:
        try:
            with _read_only(path) as journal:
                journal.execute("BEGIN")
                validate_sandbox_schema(journal)
                if journal.execute("SELECT store_id FROM sandbox_meta").fetchone()[0] != store_id:
                    raise ValueError("sandbox journal store binding differs")
                row = journal.execute("SELECT * FROM sandbox_operations WHERE execution_id=?",
                                      (snapshot.execution_id,)).fetchone()
                if row is None:
                    continue
                if (row["handler_id"], row["handler_contract_version"]) != (
                        snapshot.command.handler_id, snapshot.command.handler_contract_version):
                    raise ValueError("sandbox handler binding differs")
                if row["attempt"] != snapshot.attempt or row["fence"] != snapshot.fence:
                    issues.append("sandbox_evidence_other_generation")
                    continue
                records.append({"journal_path": path, "operation_key": row["operation_key"],
                                "effect_id": row["effect_id"], "attempt": row["attempt"],
                                "fence": row["fence"], "phase": row["phase"],
                                "result_known": row["result"] is not None,
                                "cleanup_confirmed": bool(row["cleanup_confirmed"])})
        except (OSError, sqlite3.Error, ValueError) as exc:
            issues.append("sandbox_evidence_unavailable:" + type(exc).__name__)
    return records, issues


def inspect_cancellation(
    orchestrator: Orchestrator, run_id: str, *, task_id: str | None = None,
    execution_id: str | None = None, source_id: str | None = None,
    cancellation_journal_path: str | Path | None = None,
    limit: int = 100, after_task_id: str | None = None,
) -> CancellationRecoveryReport:
    """Inspect current task attempts, or one explicitly selected historical execution.

    Every store uses a read snapshot; separate stores are not one atomic view.
    No cancellation, synchronization, provider calls or lease reaping occurs.
    Missing receipts never mean that an external action was not applied.
    ``after_task_id`` is an exclusive paging cursor for current attempts.
    """
    identifier(run_id, "run_id")
    for value, name in ((task_id, "task_id"), (execution_id, "execution_id"),
                        (source_id, "source_id"), (after_task_id, "after_task_id")):
        if value is not None:
            identifier(value, name)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if after_task_id is not None and (task_id is not None or execution_id is not None):
        raise ValueError("paging is only supported for the Run's current attempts")
    journal = getattr(orchestrator.runtime, "cancellation_journal", None)
    if cancellation_journal_path is None and journal is not None:
        cancellation_journal_path = journal.path
        if source_id is not None and source_id != journal.source_id:
            raise ValueError("cancellation journal source identity differs")
        source_id = journal.source_id
    if cancellation_journal_path is not None and source_id is None:
        raise ValueError("a cancellation journal requires its source_id")
    kernel_path = orchestrator.kernel.db_path
    if str(kernel_path) == ":memory:":
        raise OrchestrationError("cancellation report requires an existing SQLite Kernel file")
    with _read_only(orchestrator.db_path) as application:
        application.execute("BEGIN")
        state = orchestrator._load(application, run_id)
        deliveries = []
        for row in application.execute("SELECT * FROM sdk_outbox WHERE run_id=? ORDER BY sequence", (run_id,)):
            intent = json.loads(row["payload"])
            if intent["kind"] == "cancel":
                deliveries.append((row, intent))
    selected = []
    for name, task in sorted(state["tasks"].items()):
        if task_id is not None and name != task_id:
            continue
        if after_task_id is not None and name <= after_task_id:
            continue
        indices = range(len(task["attempts"])) if execution_id is not None else [len(task["attempts"]) - 1]
        for index in indices:
            attempt = task["attempts"][index]
            if execution_id is None or attempt["command"]["execution_id"] == execution_id:
                selected.append((name, index, attempt))
    if not selected and (task_id is not None or execution_id is not None):
        raise OrchestrationError("requested task/execution does not belong to this Run")
    reports = []
    with _read_only(kernel_path) as kernel:
        kernel.execute("BEGIN")
        for name, index, attempt in selected[:limit]:
            identity = attempt["command"]["execution_id"]
            requests = [(row, intent) for row, intent in deliveries if intent["execution_id"] == identity]
            request = _fact("confirmed" if requests or "cancel_reason" in attempt else "unknown",
                            "application_cancel_intent" if requests or "cancel_reason" in attempt else "no_cancel_intent_observed",
                            "orchestrator", command_ids=[row["command_id"] for row, _ in requests])
            delivered = _fact("confirmed" if requests and all(row["delivered"] for row, _ in requests)
                              else "pending" if requests else "not_applicable" if "cancel_reason" in attempt and not attempt["dispatched"] else "unknown",
                              "cancel_delivery", "orchestrator.outbox",
                              messages=[{"id": row["sequence"], "delivered": bool(row["delivered"]),
                                         "last_error": json.loads(row["last_error"]) if row["last_error"] else None}
                                        for row, _ in requests])
            authority = _fact("unknown", "execution_not_observed", "kernel")
            local = _fact("unknown", "no_process_receipt", "cancellation_journal")
            external = _fact("unknown", "execution_not_observed", "kernel.effects")
            cleanup = _fact("unknown", "no_cleanup_receipt", "cancellation_journal")
            issues, receipt_ids, effects = [], (), ()
            receipt_truncated = effect_truncated = False
            snapshot = None
            row = kernel.execute("SELECT * FROM kernel_executions WHERE execution_id=?", (identity,)).fetchone()
            if row is not None:
                snapshot = orchestrator.kernel._snapshot(row)
                if canonical(snapshot.command.to_dict()) != canonical(attempt["command"]):
                    raise OrchestrationError("Kernel execution command does not match the accepted command")
                revoked = snapshot.state in TERMINAL or snapshot.state == "recovery_required"
                authority = _fact("confirmed" if revoked else "pending", "kernel_execution_authority",
                                  "kernel", revision=snapshot.revision, state=snapshot.state,
                                  fence=snapshot.fence, recovery_target_state=snapshot.recovery_target_state)
                if snapshot.state == "cancelled" or snapshot.recovery_target_state == "cancelled":
                    request = _fact("confirmed", "kernel_cancel_committed", "kernel", revision=snapshot.revision)
                effect_rows = kernel.execute(
                    "SELECT effect_id,revision,attempt,fence,state,recovery_id,recovery_decision "
                    "FROM kernel_effects WHERE execution_id=? ORDER BY effect_id LIMIT 101", (identity,)).fetchall()
                effects = tuple(dict(item) for item in effect_rows[:100])
                effect_truncated = len(effect_rows) > 100
                unknown = effect_truncated or any(item["state"] in {"prepared", "performing", "indeterminate"} for item in effects)
                external = _fact("unknown" if unknown else "confirmed" if effects else "not_applicable",
                                 "tracked_effect_outcomes", "kernel.effects", coverage="recorded_effects_only")
                if cancellation_journal_path is not None:
                    try:
                        page = inspect_cancellation_journal(cancellation_journal_path, source_id=source_id,
                            kernel_path=kernel_path, snapshot=snapshot)
                    except (OSError, sqlite3.Error, ValueError) as exc:
                        issues.append("cancellation_evidence_unavailable:" + type(exc).__name__)
                    else:
                        receipt_ids = tuple(receipt.receipt_id for receipt in page.receipts)
                        receipt_truncated = page.truncated
                        if page.receipts and request.status != "confirmed":
                            request = _fact("confirmed", "runtime_request_persisted", "cancellation_journal")
                        phases = [receipt.phases for receipt in page.receipts]
                        issues.extend("cancellation_phase_failed:" + phase["failure"]["phase"]
                                      for phase in phases if "failure" in phase)
                        local_phases = [phase["process_cleanup"] for phase in phases if "process_cleanup" in phase]
                        proof = next((phase for phase in local_phases if phase["state"] == "confirmed"),
                                     local_phases[0] if local_phases else None)
                        if proof is not None:
                            local = _fact(proof["state"], proof["code"], "cancellation_journal")
                        if any(phase.get("failure", {}).get("phase") == "process_cleanup" for phase in phases) and proof is None:
                            local = _fact("failed", "process_cleanup_failed", "cancellation_journal")
                records, sandbox_issues = _sandbox_facts(kernel, snapshot)
                issues.extend(sandbox_issues)
                if records or sandbox_issues:
                    remote = "unknown" if sandbox_issues else "confirmed" if all(item["cleanup_confirmed"] for item in records) else "pending"
                    external = _fact(external.status, external.code, external.source,
                                     coverage="recorded_effects_only", sandbox_records=records)
                    cleanup = _fact("pending" if remote == "pending" else "unknown" if remote == "unknown" or local.status in {"unknown", "failed"}
                                    else "confirmed", "local_and_sandbox_cleanup", "runtime_evidence",
                                    local=local.status, remote=remote, sandbox_records=records)
                else:
                    cleanup = _fact(local.status, "local_cleanup_only", "cancellation_journal",
                                    coverage="local_process_and_registered_sandboxes_only")
            elif "cancel_reason" in attempt and not attempt["dispatched"]:
                local = _fact("not_applicable", "execution_not_dispatched", "orchestrator")
                cleanup = local
            reports.append(ExecutionCancellationReport(
                name, index, identity, snapshot.revision if snapshot else None,
                snapshot.attempt if snapshot else None, snapshot.fence if snapshot else None,
                snapshot.state if snapshot else None, attempt["state"],
                attempt["state"] if attempt["state"] in TERMINAL else None,
                request, delivered, authority, local, external, cleanup,
                bool(snapshot and snapshot.result is not None), effects, effect_truncated,
                receipt_ids, receipt_truncated, tuple(issues)))
    truncated = len(selected) > limit
    return CancellationRecoveryReport(source_id, run_id, state["revision"], state["state"],
        state["state"] if state["state"] in TERMINAL else None, time.time(),
        str(Path(orchestrator.db_path).resolve()), str(Path(kernel_path).resolve()), "non_atomic",
        tuple(reports), truncated, reports[-1].task_id if truncated else None)


__all__ = ["EvidenceStatus", "CancellationFact", "ExecutionCancellationReport",
           "CancellationRecoveryReport", "inspect_cancellation"]
