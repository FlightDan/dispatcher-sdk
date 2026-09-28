"""Bounded, read-only diagnostics for one existing orchestration Run.

This module reads only the supplied Orchestrator SQLite file. It does not
open a Kernel, Runtime, or application handler, so Kernel deployment and live
handler binding remain explicitly unknown.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from typing import Any

from .._inspection import InspectionBudget, InspectionBudgetExceeded
from ..content import ContentReadBudget, decode_value
from .contracts import OrchestrationError, identifier
from .notifications import NotificationsMixin
from .results import ResultsMixin
from .store import ORCHESTRATOR_SCHEMA_VERSION, StoreMixin


_MAX_PAGE = 100
_MAX_TASK_COUNT_SCAN = 100_000
_MAX_ITEM_ENCODED_BYTES = 64 * 1024
_MAX_PAGE_CONTENT_BYTES = 1024 * 1024
_SAFE_BUDGET_KIND = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")


class _SchemaValidationView(StoreMixin, ResultsMixin, NotificationsMixin):
    """Supply the owned DDL helpers required by StoreMixin's exact check."""


@dataclass(frozen=True)
class RunDiagnosticReport:
    """Bounded facts from one read-only SQLite snapshot."""

    run_id: str
    observed_at: float
    schema_status: str
    schema_version: int | None
    kernel_schema_status: str
    deployment_status: str
    run_summary: dict[str, Any] | None
    task_count: int | None
    task_count_lower_bound: int
    task_count_complete: bool
    tasks: tuple[dict[str, Any], ...]
    tasks_has_more: bool | None
    tasks_complete: bool
    waits: tuple[dict[str, Any], ...]
    waits_has_more: bool | None
    waits_complete: bool
    blockers: dict[str, Any]
    blockers_complete: bool
    complete: bool
    timed_out: bool
    error_code: str | None
    elapsed_seconds: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class _ReportBuilder:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.observed_at = time.time()
        self.schema_status = "unknown"
        self.schema_version = None
        self.kernel_schema_status = "unknown"
        self.deployment_status = "unknown"
        self.run_summary = None
        self.task_count = None
        self.task_count_lower_bound = 0
        self.task_count_complete = False
        self.tasks: tuple[dict[str, Any], ...] = ()
        self.tasks_has_more = None
        self.tasks_complete = False
        self.waits: tuple[dict[str, Any], ...] = ()
        self.waits_has_more = None
        self.waits_complete = False
        self.blockers: dict[str, Any] = {}
        self.blockers_complete = False
        self.complete = False
        self.timed_out = False
        self.error_code = None

    def freeze(self, budget: InspectionBudget) -> RunDiagnosticReport:
        return RunDiagnosticReport(
            run_id=self.run_id,
            observed_at=self.observed_at,
            schema_status=self.schema_status,
            schema_version=self.schema_version,
            kernel_schema_status=self.kernel_schema_status,
            deployment_status=self.deployment_status,
            run_summary=self.run_summary,
            task_count=self.task_count,
            task_count_lower_bound=self.task_count_lower_bound,
            task_count_complete=self.task_count_complete,
            tasks=self.tasks,
            tasks_has_more=self.tasks_has_more,
            tasks_complete=self.tasks_complete,
            waits=self.waits,
            waits_has_more=self.waits_has_more,
            waits_complete=self.waits_complete,
            blockers=self.blockers,
            blockers_complete=self.blockers_complete,
            complete=self.complete,
            timed_out=self.timed_out,
            error_code=self.error_code,
            elapsed_seconds=budget.elapsed_seconds,
        )


def _open_reader(path: str | Path, budget: InspectionBudget) -> sqlite3.Connection:
    if str(path) == ":memory:":
        raise ValueError("run diagnostics require an existing SQLite file")
    database = Path(path).resolve()
    connection = sqlite3.connect(
        f"{database.as_uri()}?mode=ro",
        uri=True,
        timeout=budget.sqlite_timeout_seconds,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN")
        budget.install(connection)
        return connection
    except BaseException:
        connection.close()
        raise


def _rows(
    connection: sqlite3.Connection,
    budget: InspectionBudget,
    sql: str,
    parameters: tuple[Any, ...] = (),
) -> list[sqlite3.Row]:
    budget.check()
    try:
        rows = connection.execute(sql, parameters).fetchall()
    except sqlite3.Error as error:
        if budget.interrupted(error):
            raise InspectionBudgetExceeded("run diagnostics timeout exceeded") from error
        raise
    budget.check()
    return rows


def _index_for_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
) -> str:
    for index in connection.execute(f"PRAGMA index_list(\"{table}\")"):
        name = str(index[1])
        quoted = '"' + name.replace('"', '""') + '"'
        indexed_columns = tuple(
            row[2] for row in connection.execute(f"PRAGMA index_info({quoted})")
        )
        if indexed_columns == columns:
            return quoted
    raise OrchestrationError(f"required {table} index is missing")


def _decode_limited(
    connection: sqlite3.Connection,
    value: str | None,
    read_budget: ContentReadBudget,
) -> tuple[Any | None, str]:
    if value is None:
        return None, "item_too_large"
    try:
        return decode_value(
            connection,
            value,
            max_logical_bytes=_MAX_ITEM_ENCODED_BYTES,
            max_encoded_bytes=_MAX_ITEM_ENCODED_BYTES,
            max_depth=40,
            read_budget=read_budget,
        ), "ok"
    except (ValueError, TypeError, RecursionError):
        return None, "content_unavailable"


def _sample_page(
    connection: sqlite3.Connection,
    budget: InspectionBudget,
    sql: str,
    parameters: tuple[Any, ...],
    limit: int,
) -> tuple[list[sqlite3.Row], bool]:
    rows = _rows(connection, budget, sql, (*parameters, limit + 1))
    return rows[:limit], len(rows) > limit


def _task_page(
    connection: sqlite3.Connection,
    budget: InspectionBudget,
    run_id: str,
    after_task_id: str,
    limit: int,
) -> tuple[tuple[dict[str, Any], ...], bool, bool]:
    item_index = _index_for_columns(connection, "sdk_run_items", ("run_id", "section", "item_key"))
    execution_index = _index_for_columns(
        connection, "sdk_executions", ("run_id", "task_id", "attempt"))
    rows, has_more = _sample_page(
        connection,
        budget,
        "SELECT item_key "
        f"FROM sdk_run_items INDEXED BY {item_index} "
        "WHERE run_id=? AND section='task' AND item_key>? ORDER BY item_key LIMIT ?",
        (run_id, after_task_id),
        limit,
    )
    values: list[dict[str, Any]] = []
    complete = True
    for row in rows:
        budget.check()
        latest = _rows(
            connection,
            budget,
            f"SELECT attempt FROM sdk_executions INDEXED BY {execution_index} "
            "WHERE run_id=? AND task_id=? ORDER BY attempt DESC LIMIT 1",
            (run_id, row["item_key"]),
        )
        latest_attempt: dict[str, Any] | None = None
        attempt_status = "unknown"
        if latest:
            attempt_key = json.dumps(
                [row["item_key"], latest[0]["attempt"]],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            safe_fields = (
                ("state", "state"),
                ("dispatched", "dispatched"),
                ("generation", "generation"),
                ("kernel_revision", "kernel_revision"),
                ("command.execution_id", "execution_id"),
                ("command.handler_id", "handler_id"),
                ("command.handler_contract_version", "handler_contract_version"),
                ("command.registry_revision", "registry_revision"),
            )
            projection = ", ".join(
                f"CASE WHEN length(value)<=? AND json_valid(value) "
                f"THEN json_extract(value,'$.{path}') END AS {alias}"
                for path, alias in safe_fields
            )
            encoded = _rows(
                connection,
                budget,
                f"SELECT {projection} "
                f"FROM sdk_run_items INDEXED BY {item_index} "
                "WHERE run_id=? AND section='attempt' AND item_key=?",
                (_MAX_ITEM_ENCODED_BYTES,) * len(safe_fields) + (run_id, attempt_key),
            )
            attempt_fields = encoded[0] if encoded else None
            attempt_status = (
                "ok" if attempt_fields is not None and attempt_fields["state"] is not None
                else "content_unavailable"
            )
            if attempt_fields is not None and attempt_status == "ok":
                latest_attempt = {
                    "attempt": latest[0]["attempt"],
                    "state": attempt_fields["state"],
                    "dispatched": (
                        None if attempt_fields["dispatched"] is None
                        else bool(attempt_fields["dispatched"])
                    ),
                    "generation": attempt_fields["generation"],
                    "kernel_revision": attempt_fields["kernel_revision"],
                    "execution_id": attempt_fields["execution_id"],
                    "handler_id": attempt_fields["handler_id"],
                    "handler_contract_version": attempt_fields["handler_contract_version"],
                    "registry_revision": attempt_fields["registry_revision"],
                }
        if attempt_status != "ok":
            complete = False
        values.append({
            "task_id": row["item_key"],
            "attempt_count": None if not latest else latest[0]["attempt"] + 1,
            "latest_attempt": latest_attempt,
            "latest_attempt_status": attempt_status,
        })
    return tuple(values), has_more, complete


def _wait_page(
    connection: sqlite3.Connection,
    budget: InspectionBudget,
    run_id: str,
    after_wait_id: str,
    limit: int,
) -> tuple[tuple[dict[str, Any], ...], bool, bool]:
    item_index = _index_for_columns(connection, "sdk_run_items", ("run_id", "section", "item_key"))
    rows, has_more = _sample_page(
        connection,
        budget,
        "SELECT item_key,CASE WHEN length(value)<=? AND json_valid(value) "
        "THEN json_extract(value,'$.state') END AS state "
        f"FROM sdk_run_items INDEXED BY {item_index} "
        "WHERE run_id=? AND section='waits' AND item_key>? ORDER BY item_key LIMIT ?",
        (_MAX_ITEM_ENCODED_BYTES, run_id, after_wait_id),
        limit,
    )
    values: list[dict[str, Any]] = []
    complete = True
    for row in rows:
        budget.check()
        state = row["state"]
        status = "ok" if isinstance(state, str) else "content_unavailable"
        if status != "ok":
            complete = False
        values.append({
            "wait_id": row["item_key"],
            "state": state if isinstance(state, str) else None,
            "status": status,
        })
    return tuple(values), has_more, complete


def _task_count(
    connection: sqlite3.Connection,
    budget: InspectionBudget,
    run_id: str,
    scan_limit: int,
) -> tuple[int | None, int, bool]:
    item_index = _index_for_columns(connection, "sdk_run_items", ("run_id", "section", "item_key"))
    rows = _rows(
        connection,
        budget,
        f"SELECT 1 FROM sdk_run_items INDEXED BY {item_index} "
        "WHERE run_id=? AND section='task' LIMIT ?",
        (run_id, scan_limit + 1),
    )
    if len(rows) > scan_limit:
        return None, scan_limit, False
    return len(rows), len(rows), True


def _blocker_report(
    connection: sqlite3.Connection,
    budget: InspectionBudget,
    run_id: str,
    blocker_limit: int,
) -> tuple[dict[str, Any], bool]:
    outbox_index = _index_for_columns(
        connection, "sdk_outbox", ("run_id", "command_id", "ordinal"))
    execution_index = _index_for_columns(
        connection, "sdk_executions", ("run_id", "task_id", "attempt"))
    result_index = _index_for_columns(
        connection, "sdk_results", ("execution_id",))
    recovery_index = _index_for_columns(
        connection, "sdk_recoveries", ("run_id", "status"))
    item_index = _index_for_columns(connection, "sdk_run_items", ("run_id", "section", "item_key"))

    outbox_rows, outbox_more = _sample_page(
        connection,
        budget,
        f"SELECT command_id,ordinal FROM sdk_outbox INDEXED BY {outbox_index} "
        "WHERE run_id=? AND delivered=0 LIMIT ?",
        (run_id,),
        blocker_limit,
    )
    result_rows, results_more = _sample_page(
        connection,
        budget,
        f"SELECT e.execution_id,e.task_id,e.attempt,r.state "
        f"FROM sdk_executions AS e INDEXED BY {execution_index} "
        f"CROSS JOIN sdk_results AS r INDEXED BY {result_index} "
        "ON r.execution_id=e.execution_id "
        "WHERE e.run_id=? AND r.state!='delivered' LIMIT ?",
        (run_id,),
        blocker_limit,
    )
    recovery_rows, recoveries_more = _sample_page(
        connection,
        budget,
        "SELECT recovery_id,status,target_generation "
        f"FROM sdk_recoveries INDEXED BY {recovery_index} "
        "WHERE run_id=? AND status IN ('preparing','prepared','committed') LIMIT ?",
        (run_id,),
        blocker_limit,
    )
    wait_rows, waits_scanned_more = _sample_page(
        connection,
        budget,
        "SELECT item_key,CASE WHEN length(value)<=? AND json_valid(value) "
        "THEN json_extract(value,'$.state') END AS state "
        f"FROM sdk_run_items INDEXED BY {item_index} "
        "WHERE run_id=? AND section='waits' ORDER BY item_key LIMIT ?",
        (_MAX_ITEM_ENCODED_BYTES, run_id),
        blocker_limit,
    )
    open_waits: list[str] = []
    wait_values_complete = True
    for row in wait_rows:
        budget.check()
        state = row["state"]
        if not isinstance(state, str):
            wait_values_complete = False
        elif state == "open":
            open_waits.append(row["item_key"])

    categories = {
        "pending_execution_delivery": {
            "items": tuple({"command_id": row["command_id"], "ordinal": row["ordinal"]}
                            for row in outbox_rows),
            "has_more": outbox_more,
            "complete": not outbox_more,
        },
        "pending_result_delivery": {
            "items": tuple({"execution_id": row["execution_id"], "task_id": row["task_id"],
                             "attempt": row["attempt"], "state": row["state"]}
                            for row in result_rows),
            "has_more": results_more,
            "complete": not results_more,
        },
        "open_waits": {
            "wait_ids": tuple(open_waits),
            "has_more": waits_scanned_more,
            "complete": not waits_scanned_more and wait_values_complete,
        },
        "recovery_required": {
            "items": tuple({"recovery_id": row["recovery_id"], "status": row["status"],
                             "target_generation": row["target_generation"]}
                            for row in recovery_rows),
            "has_more": recoveries_more,
            "complete": not recoveries_more,
        },
        "kernel_execution_recovery": {
            "status": "unknown",
            "reason": "Kernel database path and live deployment were not supplied",
            "complete": False,
        },
    }
    complete = all(category["complete"] for category in categories.values())
    return categories, complete


def _managed_summary(
    connection: sqlite3.Connection,
    budget: InspectionBudget,
    run_id: str,
    scan_limit: int,
) -> tuple[dict[str, Any], bool]:
    managed_index = _index_for_columns(connection, "sdk_managed_runs", ("run_id",))
    row = _rows(
        connection,
        budget,
        "SELECT control_state,control_epoch,generation,max_claims,deadline_at "
        f"FROM sdk_managed_runs INDEXED BY {managed_index} WHERE run_id=? LIMIT 1",
        (run_id,),
    )
    if not row:
        return {"status": "not_managed"}, True

    budget_index = _index_for_columns(
        connection, "sdk_managed_budget_entries", ("run_id", "entry_id"))
    entries = _rows(
        connection,
        budget,
        "SELECT CASE WHEN length(kind)<=64 AND kind NOT GLOB '*[^A-Za-z0-9_.:-]*' "
        "THEN kind ELSE 'other' END AS kind,amount FROM sdk_managed_budget_entries "
        f"INDEXED BY {budget_index} WHERE run_id=? LIMIT ?",
        (run_id, scan_limit + 1),
    )
    has_more = len(entries) > scan_limit
    entries = entries[:scan_limit]
    entry_counts: dict[str, int] = {}
    amount_counts: dict[str, int] = {}
    values_complete = True
    for entry in entries:
        budget.check()
        raw_kind = entry["kind"]
        kind = (
            raw_kind
            if isinstance(raw_kind, str) and _SAFE_BUDGET_KIND.fullmatch(raw_kind)
            else "other"
        )
        amount = entry["amount"]
        if type(amount) is not int or amount < 0:
            values_complete = False
            continue
        entry_counts[kind] = entry_counts.get(kind, 0) + 1
        amount_counts[kind] = amount_counts.get(kind, 0) + amount
    complete = not has_more and values_complete
    cleanup_index = _index_for_columns(
        connection, "sdk_managed_cleanup_obligations",
        ("run_id", "state", "control_epoch", "execution_id"))
    cleanup = _rows(
        connection,
        budget,
        "SELECT execution_id FROM sdk_managed_cleanup_obligations "
        f"INDEXED BY {cleanup_index} WHERE run_id=? AND state='pending' "
        "ORDER BY control_epoch,execution_id LIMIT ?",
        (run_id, scan_limit + 1),
    )
    cleanup_has_more = len(cleanup) > scan_limit
    cleanup = cleanup[:scan_limit]
    return {
        "status": "observed",
        "control_state": row[0]["control_state"],
        "control_epoch": row[0]["control_epoch"],
        "generation": row[0]["generation"],
        "max_claims": row[0]["max_claims"],
        "claims_used": None,
        "remaining_claims": None,
        "claims_source": "kernel_unavailable",
        "deadline_at": row[0]["deadline_at"],
        "budget_entry_count": None if has_more else len(entries),
        "budget_entry_count_lower_bound": len(entries),
        "budget_counts_by_kind": entry_counts,
        "budget_amounts_by_kind": amount_counts,
        "budget_entries_has_more": has_more,
        "budget_counts_complete": complete,
        "cleanup_pending_execution_ids": tuple(row["execution_id"] for row in cleanup),
        "cleanup_pending_has_more": cleanup_has_more,
    }, complete and not cleanup_has_more


def inspect_run_diagnostics(
    path: str | Path,
    run_id: str,
    *,
    after_task_id: str = "",
    task_limit: int = 20,
    after_wait_id: str = "",
    wait_limit: int = 20,
    blocker_limit: int = 20,
    task_count_scan_limit: int = 10_000,
    timeout_seconds: float = 3.0,
) -> RunDiagnosticReport:
    """Read a bounded Run summary, task/wait pages and delivery/recovery flags.

    The Orchestrator schema is compared with the SDK's exact declared schema.
    Reads use SQLite ``mode=ro``, ``query_only`` and a shared time budget.
    Task pages project only identity, state and handler-binding fields; wait
    pages return only IDs and states. Stored payloads, results, effect data and
    budget evidence are omitted. Counts and blocker categories expose when
    bounded scans cannot prove an exact zero or total. The supplied
    Orchestrator path may differ from the Kernel database;
    this function therefore reports Kernel schema and active deployment as
    unknown and never imports a business handler.
    """
    identifier(run_id, "run_id")
    for label, value in (("after_task_id", after_task_id), ("after_wait_id", after_wait_id)):
        if type(value) is not str:
            raise ValueError(f"{label} must be a string")
    for label, value in (("task_limit", task_limit), ("wait_limit", wait_limit),
                         ("blocker_limit", blocker_limit)):
        if type(value) is not int or not 1 <= value <= _MAX_PAGE:
            raise ValueError(f"{label} must be between 1 and {_MAX_PAGE}")
    if (type(task_count_scan_limit) is not int
            or not 1 <= task_count_scan_limit <= _MAX_TASK_COUNT_SCAN):
        raise ValueError(f"task_count_scan_limit must be between 1 and {_MAX_TASK_COUNT_SCAN}")
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds) or timeout_seconds < 0):
        raise ValueError("timeout_seconds must be finite and nonnegative")

    budget = InspectionBudget(timeout_seconds, None)
    report = _ReportBuilder(run_id)
    connection: sqlite3.Connection | None = None
    try:
        budget.check()
        connection = _open_reader(path, budget)
        try:
            # This validator compares the complete stored SDK DDL with its
            # declared schema using a private in-memory reference database.
            if not _SchemaValidationView._validate_existing_store(
                    _SchemaValidationView(), connection):
                report.schema_status = "unsupported"
                report.error_code = "orchestrator_schema_unavailable"
                return report.freeze(budget)
        except OrchestrationError:
            report.schema_status = "unsupported"
            report.error_code = "orchestrator_schema_unsupported"
            return report.freeze(budget)

        report.schema_status = "verified"
        report.schema_version = ORCHESTRATOR_SCHEMA_VERSION
        marker = _rows(
            connection,
            budget,
            "SELECT version FROM sdk_schema_meta WHERE component='orchestrator'",
        )
        if marker:
            report.schema_version = int(marker[0]["version"])

        if _rows(connection, budget,
                 "SELECT 1 FROM sdk_disposed_runs WHERE run_id=? LIMIT 1", (run_id,)):
            report.error_code = "run_disposed"
            return report.freeze(budget)
        runs = _rows(
            connection,
            budget,
            "SELECT run_id,revision,state FROM sdk_runs WHERE run_id=? LIMIT 1",
            (run_id,),
        )
        if not runs:
            report.error_code = "unknown_run"
            return report.freeze(budget)
        run = dict(runs[0])
        item_index = _index_for_columns(
            connection, "sdk_run_items", ("run_id", "section", "item_key"))
        content_budget = ContentReadBudget(_MAX_PAGE_CONTENT_BYTES)
        root = _rows(
            connection,
            budget,
            "SELECT CASE WHEN length(value)<=? THEN value END AS value "
            f"FROM sdk_run_items INDEXED BY {item_index} "
            "WHERE run_id=? AND section='root' AND item_key='generation' LIMIT 1",
            (_MAX_ITEM_ENCODED_BYTES, run_id),
        )
        generation, generation_status = _decode_limited(
            connection, root[0]["value"] if root else "0", content_budget)
        previous = _rows(
            connection, budget,
            "SELECT previous_run_id FROM sdk_run_links WHERE next_run_id=? LIMIT 1", (run_id,))
        following = _rows(
            connection, budget,
            "SELECT next_run_id FROM sdk_run_links WHERE previous_run_id=? LIMIT 1", (run_id,))
        managed_summary, managed_complete = _managed_summary(
            connection, budget, run_id, blocker_limit)
        report.run_summary = {
            **run,
            "generation": generation if generation_status == "ok" else None,
            "generation_status": generation_status,
            "previous_run_id": previous[0]["previous_run_id"] if previous else None,
            "next_run_id": following[0]["next_run_id"] if following else None,
            "deployment_status": "unknown",
            "managed_control": managed_summary,
        }

        (report.task_count, report.task_count_lower_bound,
         report.task_count_complete) = _task_count(
            connection, budget, run_id, task_count_scan_limit)
        report.tasks, report.tasks_has_more, report.tasks_complete = _task_page(
            connection, budget, run_id, after_task_id, task_limit)
        report.waits, report.waits_has_more, report.waits_complete = _wait_page(
            connection, budget, run_id, after_wait_id, wait_limit)
        report.blockers, report.blockers_complete = _blocker_report(
            connection, budget, run_id, blocker_limit)
        budget.check()
        report.complete = (
            report.task_count_complete
            and report.tasks_complete
            and report.waits_complete
            and report.blockers_complete
            and generation_status == "ok"
            and managed_complete
        )
    except InspectionBudgetExceeded:
        report.timed_out = True
        report.error_code = "inspection_timeout"
    except sqlite3.Error as error:
        if budget.interrupted(error):
            report.timed_out = True
            report.error_code = "inspection_timeout"
        else:
            report.error_code = "sqlite_read_error"
    except OrchestrationError:
        report.error_code = "schema_or_run_data_unavailable"
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()
    return report.freeze(budget)


__all__ = ["RunDiagnosticReport", "inspect_run_diagnostics"]
