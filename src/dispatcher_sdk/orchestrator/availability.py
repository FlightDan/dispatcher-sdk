"""Bounded, read-only scheduling facts for an existing SQLite Run."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import sqlite3
from typing import TYPE_CHECKING, Any, Sequence

from ..execution_kernel._sqlite_execution import _claim_revisions
from ..execution_kernel.claiming import claim_predicate
from .contracts import OrchestrationError, TERMINAL, canonical, identifier

if TYPE_CHECKING:
    from .engine import Orchestrator


@dataclass(frozen=True)
class WorkExecutionSummary:
    execution_id: str
    task_id: str
    application_attempt: int
    state: str
    revision: int
    fence: int
    next_attempt_at: float
    lease_expires_at: float | None


@dataclass(frozen=True)
class WorkAvailabilityReport:
    run_id: str
    run_revision: int
    run_state: str
    orchestrator_source: str
    kernel_source: str
    observed_at: float
    kernel_event_sequence: int
    binding_status: str
    registry_revisions: tuple[str, ...] | None
    claimable_now: int | None
    queued_ready: int
    active_leases: int
    expired_leases: int
    future_retries: int
    earliest_retry_at: float | None
    pending_commands: int
    pending_result_sync: int | None
    pending_result_delivery: int
    open_waits: int
    recovery_required: int
    unknown_effects: int | None
    task_count: int
    missing_executions: int
    reason_codes: tuple[str, ...]
    next_change_hint: float | None
    snapshot_consistency: str
    complete: bool
    summaries: tuple[WorkExecutionSummary, ...]
    summaries_truncated: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def _open_reader(path: str) -> sqlite3.Connection:
    if str(path) == ":memory:":
        raise OrchestrationError("work availability requires an existing SQLite file")
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def _run_registration_source(connection: sqlite3.Connection) -> str:
    """Force Run-first access using the existing unique registration index."""
    for index in connection.execute("PRAGMA index_list(sdk_executions)"):
        name = index[1]
        quoted = '"' + name.replace('"', '""') + '"'
        columns = tuple(row[2] for row in connection.execute(f"PRAGMA index_info({quoted})"))
        if columns == ('run_id', 'task_id', 'attempt'):
            return f" FROM sdk_executions s INDEXED BY {quoted}"
    raise OrchestrationError("Run registration index is missing")


def inspect_work_availability(
    orchestrator: Orchestrator, run_id: str, *,
    registry_revision: str | None = None,
    registry_revisions: Sequence[str] | None = None,
    sample_limit: int = 20,
    effect_scan_limit: int = 1000,
) -> WorkAvailabilityReport:
    """Inspect without flush, sync, reap, cursor changes, or clock writes.

    Binding filters have exactly Kernel.claim's meaning; absent explicit filters,
    the attached Runtime's registry and handler revisions are used. Without a
    Runtime, ``claimable_now`` is not checked and ``queued_ready`` is unfiltered.
    Claimable counts only queued executions already due, BEFORE claim's reap.

    Command identities are (run_id, command_id, ordinal), SDK -> Kernel. Result
    sync counts distinct execution IDs with terminal Kernel authority missing
    from the Run projection, Kernel -> SDK. Delivery counts SDK result IDs not
    yet delivered to the application (including dead deliveries).

    Each database has a read transaction. These are NOT one atomic cross-store
    snapshot. Detected concurrent writes mark the report incomplete and the
    cross-store result-sync count unknown; undetected races remain possible.
    Counts are facts at observation, never guarantees that a later claim works.
    Queries read Run registrations and current active executions, not events or
    historical Run snapshots. Execution examples alone are sample-limited.
    Effects have no execution index in schema v2: at most effect_scan_limit + 1
    rows are read globally, without sorting. Zero disables that check. Exceeding
    the limit returns unknown_effects=None and an incomplete report; no partial
    count is presented as an exact count.
    """
    identifier(run_id, "run_id")
    if type(sample_limit) is not int or not 0 <= sample_limit <= 1000:
        raise ValueError("sample_limit must be between 0 and 1000")
    if type(effect_scan_limit) is not int or not 0 <= effect_scan_limit <= 100000:
        raise ValueError("effect_scan_limit must be between 0 and 100000")
    revisions = _claim_revisions(registry_revision, registry_revisions)
    if revisions is None and orchestrator.runtime is not None:
        runtime = orchestrator.runtime
        runtime._assert_registry_current()
        revisions = tuple(dict.fromkeys((runtime.registry_revision, *runtime.handler_revisions.values())))
    source = str(Path(orchestrator.db_path).resolve())
    kernel_source = str(Path(orchestrator.kernel.db_path).resolve())
    connection = _open_reader(orchestrator.db_path)
    try:
        # ATTACH opens only the already-existing file; URI mode=ro also applies
        # to the attached database. No writer object or initializer is created.
        connection.execute("ATTACH DATABASE ? AS authority", (
            Path(orchestrator.kernel.db_path).resolve().as_uri() + "?mode=ro",))
        versions = tuple(connection.execute(f"PRAGMA {db}.data_version").fetchone()[0]
                         for db in ("main", "authority"))
        connection.execute("BEGIN")
        if tuple(connection.execute("SELECT component,version FROM sdk_schema_meta").fetchone() or ()) != ("orchestrator", 2):
            raise OrchestrationError("unsupported orchestration schema")
        if tuple(connection.execute("SELECT component,schema_version FROM authority.kernel_schema_meta").fetchone() or ()) != ("execution_kernel", 2):
            raise OrchestrationError("unsupported Kernel schema")
        run = connection.execute("SELECT revision,state FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise OrchestrationError("unknown run")
        clock = connection.execute("SELECT watermark,event_sequence FROM authority.kernel_clock WHERE singleton=1").fetchone()
        # current_time is the Kernel's documented non-mutating logical clock.
        now = max(orchestrator.kernel.current_time(), clock["watermark"])
        registration = _run_registration_source(connection)
        join = (registration + " CROSS JOIN authority.kernel_executions k "
                "ON k.execution_id=s.execution_id WHERE s.run_id=? AND s.active=1")
        def count(condition: str, args: tuple = ()) -> int:
            return connection.execute("SELECT COUNT(*)" + join + " AND " + condition, (run_id, *args)).fetchone()[0]
        mismatch = count("json(k.command_json) != json(s.command)")
        # JSON textual ordering is not identity; compare decoded canonical data
        # only for mismatches to avoid trusting a reused execution ID.
        if mismatch:
            for row in connection.execute("SELECT k.command_json,s.command" + join, (run_id,)):
                if canonical(json.loads(row[0])) != canonical(json.loads(row[1])):
                    raise OrchestrationError("Kernel execution command does not match the accepted command")
        queued = count(*claim_predicate(now, None, alias="k"))
        claimable = None if revisions is None else count(*claim_predicate(now, revisions, alias="k"))
        live = count("k.state IN ('leased','running') AND k.lease_expires_at>?", (now,))
        expired = count("k.state IN ('leased','running') AND k.lease_expires_at<=?", (now,))
        future = count("k.state='queued' AND k.next_attempt_at>?", (now,))
        retry = connection.execute("SELECT MIN(k.next_attempt_at)" + join + " AND k.state='queued' AND k.next_attempt_at>?", (run_id, now)).fetchone()[0]
        lease = connection.execute("SELECT MIN(k.lease_expires_at)" + join + " AND k.state IN ('leased','running') AND k.lease_expires_at>?", (run_id, now)).fetchone()[0]
        recovery = count("k.state='recovery_required'")
        active_ids = {row[0] for row in connection.execute(
            "SELECT s.execution_id" + registration + " WHERE s.run_id=? AND s.active=1", (run_id,))}
        effect_rows = [] if effect_scan_limit == 0 else connection.execute(
            "SELECT execution_id,state FROM authority.kernel_effects LIMIT ?",
            (effect_scan_limit + 1,)).fetchall()
        effects_complete = effect_scan_limit > 0 and len(effect_rows) <= effect_scan_limit
        unknown = sum(row[0] in active_ids and row[1] in ('performing', 'indeterminate')
                      for row in effect_rows) if effects_complete else None
        pending_sync = count("k.state IN ('succeeded','failed','timed_out','cancelled','dead')")
        missing = connection.execute("SELECT COUNT(*)" + registration + " LEFT JOIN authority.kernel_executions k ON k.execution_id=s.execution_id WHERE s.run_id=? AND s.active=1 AND k.execution_id IS NULL", (run_id,)).fetchone()[0]
        commands = connection.execute("SELECT COUNT(*) FROM sdk_outbox WHERE run_id=? AND delivered=0", (run_id,)).fetchone()[0]
        delivery = connection.execute("SELECT COUNT(*)" + registration + " CROSS JOIN sdk_results r ON s.execution_id=r.execution_id WHERE s.run_id=? AND r.state!='delivered'", (run_id,)).fetchone()[0]
        tasks = connection.execute("SELECT COUNT(*) FROM sdk_run_items WHERE run_id=? AND section='task'", (run_id,)).fetchone()[0]
        waits = connection.execute("SELECT COUNT(*) FROM sdk_run_items WHERE run_id=? AND section='waits' AND json_extract(value,'$.state')='open'", (run_id,)).fetchone()[0]
        total = count("1=1")
        rows = connection.execute("SELECT k.execution_id,s.task_id,s.attempt,k.state,k.revision,k.fence,k.next_attempt_at,k.lease_expires_at" + join + " ORDER BY k.execution_id LIMIT ?", (run_id, sample_limit)).fetchall()
        summaries = tuple(WorkExecutionSummary(*tuple(row)) for row in rows)
        connection.rollback()
        after = tuple(connection.execute(f"PRAGMA {db}.data_version").fetchone()[0]
                      for db in ("main", "authority"))
        changed = versions != after
        reasons = []
        for flag, reason in ((run["state"] in TERMINAL, "terminal_run"), (tasks == 0, "no_tasks"),
            (revisions is None, "binding_not_checked"), (bool(claimable), "claimable_now"),
            (revisions is not None and queued > (claimable or 0), "binding_mismatch"),
            (live, "active_leases"), (expired, "expired_leases_pending_reap"),
            (future, "retry_backoff"), (commands, "pending_commands"),
            (pending_sync, "pending_result_sync"), (delivery, "pending_result_delivery"),
            (waits, "application_wait"), (recovery, "recovery_required"),
            (unknown, "unknown_effects"), (missing, "execution_not_observed"),
            (changed, "concurrent_change"),
            (effect_scan_limit == 0, "effects_not_checked"),
            (effect_scan_limit > 0 and not effects_complete, "effect_scan_limit_exceeded")):
            if flag:
                reasons.append(reason)
        hints = [value for value in (retry, lease) if value is not None]
        return WorkAvailabilityReport(run_id, run["revision"], run["state"], source, kernel_source,
            now, clock["event_sequence"], "not_checked" if revisions is None else "checked",
            revisions, claimable, queued, live, expired, future, retry, commands,
            None if changed or missing else pending_sync, delivery, waits, recovery, unknown, tasks,
            missing, tuple(reasons), min(hints) if hints else None,
            "concurrent_change" if changed else "non_atomic", not changed and not missing and effects_complete,
            summaries, total > len(summaries))
    finally:
        connection.close()


__all__ = ["WorkAvailabilityReport", "WorkExecutionSummary", "inspect_work_availability"]
