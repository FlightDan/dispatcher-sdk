"""Read-only, bounded SQLite storage usage inspection.

This module deliberately does not import an SDK store implementation.  Opening
an inspector must never initialize a writer, migrate a schema, checkpoint WAL,
create a backup, or run an integrity check.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from typing import Any, Callable, Literal, TypedDict

from ._inspection import InspectionBudget, InspectionBudgetExceeded


StorageUsageDetail = Literal["files", "physical", "logical"]


class StorageUsageReport(TypedDict, total=False):
    """JSON-compatible result returned by :func:`inspect_storage_usage`."""

    path: str
    exists: bool
    detail: StorageUsageDetail
    files: dict[str, dict[str, Any]]
    physical_total_bytes: int
    sqlite: dict[str, Any]
    owned_objects: dict[str, Any]
    logical: dict[str, Any]
    snapshot: dict[str, Any]
    caveats: list[str]
    actual_scope: list[str]
    complete: bool
    stopped_reason: str | None
    elapsed_seconds: float
    checks: dict[str, str]


_CAVEATS = [
    "SQLite values are read from one transaction snapshot; physical sidecar file sizes may change concurrently.",
    "A report for one path is not an atomic snapshot with any other SDK database.",
    "Estimated compacted size is page arithmetic, not an exact promise of bytes reclaimed on disk.",
]

_OWNED_PREFIXES = (
    "sdk_", "kernel_", "notification_inbox_", "cancellation_", "sandbox_",
    "runtime_sandbox_",
)

# Payload columns known to current SDK stores.  Values are measured as stored
# SQLite bytes.  JSON is never decoded by this inspector.
_PAYLOAD_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "sdk_commands": (("response", "command_receipts"),),
    "sdk_events": (("payload", "event_payloads"),),
    "sdk_executions": (("command", "execution_commands"),),
    "sdk_outbox": (("payload", "outbox_payloads"), ("last_error", "outbox_errors")),
    "sdk_recoveries": (
        ("decision", "recovery_decisions"),
        ("application_state", "recovery_application_state"),
        ("manifest", "recovery_manifests"),
        ("error", "recovery_errors"),
    ),
    "sdk_results": (("result_json", "result_payloads"), ("last_error_json", "result_errors")),
    "sdk_watches": (("target", "watch_targets"),),
    "sdk_notifications": (
        ("payload", "notification_payloads"), ("last_error", "notification_errors"),
    ),
    "kernel_executions": (
        ("command_json", "kernel_commands"),
        ("result_json", "kernel_results"),
        ("recovery_reason", "kernel_recovery_reasons"),
    ),
    "kernel_events": (("data_json", "kernel_event_payloads"),),
    "kernel_result_outbox": (
        ("result_json", "kernel_result_outbox_payloads"),
        ("last_error_json", "kernel_result_outbox_errors"),
    ),
    "kernel_effects": (
        ("request_json", "effect_requests"), ("response_json", "effect_responses"),
    ),
    "kernel_effect_events": (("data_json", "effect_event_payloads"),),
    "notification_inbox_messages": (
        ("payload", "inbox_payloads"), ("last_error", "inbox_errors"),
        ("settlement", "inbox_settlements"),
    ),
    "cancellation_stages": (("evidence", "cancellation_evidence"),),
    "sandbox_operations": (
        ("spec", "sandbox_specs"), ("result", "sandbox_results"),
        ("cleanup_evidence", "sandbox_cleanup_evidence"),
    ),
    "sandbox_history": (("record", "sandbox_history_payloads"),),
    "sdk_maintenance_receipts": (("result", "maintenance_receipts"),),
}


def _file_size(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False, "bytes": 0}
    return {"path": str(path), "exists": True, "bytes": stat.st_size}


def _files(path: Path) -> dict[str, dict[str, Any]]:
    # These are the only SQLite files owned by this database name.  Do not scan
    # the containing directory: unrelated application files are not SDK data.
    return {
        "main": _file_size(path),
        "wal": _file_size(Path(str(path) + "-wal")),
        "shm": _file_size(Path(str(path) + "-shm")),
        "journal": _file_size(Path(str(path) + "-journal")),
    }


def _read_only(path: Path, *, timeout: float = 30) -> sqlite3.Connection:
    uri = path.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=timeout)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
    except BaseException:
        connection.close()
        raise
    return connection


def _owned_objects(connection: sqlite3.Connection, budget: InspectionBudget) -> dict[str, Any]:
    schema = connection.execute(
        "SELECT type,name,tbl_name FROM sqlite_schema "
        "WHERE type IN ('table','index') ORDER BY type,name"
    ).fetchall()
    owned_tables = {row[1] for row in schema
                    if row[0] == "table" and row[1].startswith(_OWNED_PREFIXES)}
    owned_names = {row[1] for row in schema
                   if row[1].startswith(_OWNED_PREFIXES) or row[2] in owned_tables}
    try:
        rows = connection.execute(
            "SELECT name,COALESCE(SUM(pgsize),0),COUNT(*) FROM dbstat GROUP BY name"
        ).fetchall()
    except sqlite3.DatabaseError as error:
        if budget.interrupted(error):
            raise
        return {
            "available": False,
            "reason": f"SQLite dbstat is unavailable: {error}",
            "objects": [],
            "total_bytes": None,
        }
    sizes = {str(row[0]): (int(row[1]), int(row[2])) for row in rows}
    objects = []
    for row in schema:
        object_type, name, table_name = map(str, row)
        if name not in owned_names:
            continue
        byte_count, pages = sizes.get(name, (0, 0))
        objects.append({
            "name": name, "type": object_type, "table": table_name,
            "bytes": byte_count, "pages": pages,
        })
    return {
        "available": True,
        "reason": None,
        "objects": objects,
        "total_bytes": sum(item["bytes"] for item in objects),
    }


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    # table is always sourced from sqlite_schema, never caller input.
    escaped = table.replace('"', '""')
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{escaped}")')}


def _add_category(categories: dict[str, dict[str, int]], name: str, byte_count: Any) -> None:
    if byte_count is None:
        return
    category = categories.setdefault(name, {"values": 0, "bytes": 0})
    category["values"] += 1
    category["bytes"] += int(byte_count)


def _logical_usage(
    connection: sqlite3.Connection,
    tables: list[str],
    scan_limit: int,
    budget: InspectionBudget,
) -> dict[str, Any]:
    categories: dict[str, dict[str, int]] = {}
    table_reports: dict[str, dict[str, Any]] = {}
    rows_scanned = 0
    complete = True
    stopped_at: dict[str, Any] | None = None

    for table in sorted(tables):
        budget.check()
        budget.emit("logical_table", "started", table=table, rows_scanned=rows_scanned)
        columns = _table_columns(connection, table)
        payloads: list[tuple[str, str]] = []
        selectors: list[str] = []
        if table in {"sdk_run_items", "sdk_run_history"} and {"section", "item_key", "value"} <= columns:
            payloads = [("value", "run_item_values")]
            selectors = ["section", "item_key"]
        elif table == "sdk_content_objects":
            # Pick exactly one stored representation.  Metadata length fields
            # describe the same bytes and must not be added again.
            for candidate in ("encoded", "content", "data", "payload", "value"):
                if candidate in columns:
                    payloads = [(candidate, "content_objects")]
                    break
        else:
            payloads = [(column, category) for column, category in _PAYLOAD_COLUMNS.get(table, ())
                        if column in columns]
        if not payloads:
            continue

        escaped_table = table.replace('"', '""')
        selected = [f'"{name.replace(chr(34), chr(34) * 2)}"' for name in selectors]
        selected.extend(
            f'length(CAST("{column.replace(chr(34), chr(34) * 2)}" AS BLOB))'
            for column, _ in payloads
        )
        remaining = scan_limit - rows_scanned
        # One extra row establishes incompleteness without COUNT(*) or an
        # unbounded aggregate scan.
        query = f'SELECT {",".join(selected)} FROM "{escaped_table}" LIMIT ?'
        fetched = connection.execute(query, (remaining + 1,)).fetchall()
        sampled = fetched[:remaining]
        table_reports[table] = {
            "rows_scanned": len(sampled),
            "payload_columns": [column for column, _ in payloads],
            "complete": len(fetched) <= remaining,
        }
        for row in sampled:
            offset = len(selectors)
            for index, (_, category) in enumerate(payloads):
                effective = category
                if table in {"sdk_run_items", "sdk_run_history"}:
                    prefix = "current" if table == "sdk_run_items" else "historical"
                    effective = (f"{prefix}_application_state" if row[0] == "root"
                                 and row[1] == "application_state" else f"{prefix}_run_items")
                _add_category(categories, effective, row[offset + index])
        rows_scanned += len(sampled)
        budget.emit("logical_table", "completed", table=table, rows_scanned=rows_scanned,
                    table_complete=len(fetched) <= remaining)
        if len(fetched) > remaining:
            complete = False
            stopped_at = {"table": table, "rows_scanned_in_table": len(sampled)}
            break

    content = categories.get("content_objects", {"values": 0, "bytes": 0})
    return {
        "scan_limit_rows": scan_limit,
        "rows_scanned": rows_scanned,
        "complete": complete,
        "stopped_at": stopped_at,
        "categories": categories,
        "tables": table_reports,
        "payload_values": sum(item["values"] for item in categories.values()),
        "payload_bytes": sum(item["bytes"] for item in categories.values()),
        "content_objects": {
            "objects_scanned": content["values"],
            "stored_bytes": content["bytes"],
            "counted_once": True,
        },
        "method": "stored byte lengths only; JSON payloads were not decoded",
    }


def inspect_storage_usage(
    path: str | os.PathLike[str],
    *,
    detail: StorageUsageDetail = "physical",
    scan_limit: int = 100_000,
    timeout_seconds: float | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> StorageUsageReport:
    """Inspect one SQLite store without changing it.

    ``detail='files'`` stats only the named database and sidecar files and does
    not open SQLite. ``detail='physical'`` reads page allocation and,
    when SQLite provides it, dbstat allocation for SDK-owned tables/indexes.
    ``detail='logical'`` additionally scans stored payload lengths, stopping
    after ``scan_limit`` rows across all known SDK payload tables.
    """
    if detail not in ("files", "physical", "logical"):
        raise ValueError("detail must be 'files', 'physical', or 'logical'")
    if type(scan_limit) is not int or scan_limit < 0:
        raise ValueError("scan_limit must be a nonnegative integer")

    budget = InspectionBudget(timeout_seconds, progress)
    database = Path(path).expanduser().resolve()
    report: StorageUsageReport = {
        "path": str(database),
        "exists": database.is_file(),
        "detail": detail,
        "files": _files(database),
        "physical_total_bytes": 0,
        "sqlite": {},
        "owned_objects": {
            "available": False, "reason": "database is missing", "objects": [], "total_bytes": None,
        },
        "snapshot": {"available": False},
        "caveats": list(_CAVEATS),
        "actual_scope": ["files"],
        "complete": True,
        "stopped_reason": None,
        "elapsed_seconds": 0.0,
        "checks": {"files": "checked", "sqlite_metadata": "not_checked",
                   "object_attribution": "not_checked", "logical_payloads": "not_checked"},
    }
    report["owned_objects"]["reason"] = (
        "database is missing" if not report["exists"] else "object attribution not checked")
    report["physical_total_bytes"] = sum(item["bytes"] for item in report["files"].values())
    budget.emit("files", "completed", path=str(database))
    if detail == "files":
        report["elapsed_seconds"] = budget.elapsed_seconds
        return report
    if not report["exists"]:
        if detail == "logical":
            report["logical"] = {
                "scan_limit_rows": scan_limit, "rows_scanned": 0, "complete": True,
                "stopped_at": None, "categories": {}, "tables": {}, "payload_values": 0,
                "payload_bytes": 0,
                "content_objects": {"objects_scanned": 0, "stored_bytes": 0, "counted_once": True},
                "method": "stored byte lengths only; JSON payloads were not decoded",
            }
        report["elapsed_seconds"] = budget.elapsed_seconds
        return report

    connection = None
    try:
        budget.check()
        connection = _read_only(database, timeout=budget.sqlite_timeout_seconds)
        budget.install(connection)
        connection.execute("BEGIN")
        budget.emit("sqlite_metadata", "started")
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        freelist_pages = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        allocated = page_size * page_count
        free = page_size * freelist_pages
        report["sqlite"] = {
            "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
            "page_size_bytes": page_size,
            "page_count": page_count,
            "allocated_page_bytes": allocated,
            "freelist_pages": freelist_pages,
            "free_page_bytes": free,
            "used_page_bytes": allocated - free,
            "estimated_reclaimable_bytes": free,
            "estimated_reclaimable_is_exact": False,
            "estimated_compacted_main_bytes_lower_bound": allocated - free,
            "exact_reclaimable_bytes": None,
            "estimate_method": "freelist-only estimate (freelist pages multiplied by page size); partially filled pages and compaction overhead are unknown",
        }
        schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
        data_version = int(connection.execute("PRAGMA data_version").fetchone()[0])
        report["snapshot"] = {
            "available": True,
            "transaction": "sqlite read transaction",
            "schema_version": schema_version,
            "data_version": data_version,
            "page_count": page_count,
            "freelist_pages": freelist_pages,
            "cross_database_atomic": False,
            "physical_files_atomic_with_transaction": False,
        }
        report["actual_scope"].append("sqlite_metadata")
        report["checks"]["sqlite_metadata"] = "checked"
        budget.emit("sqlite_metadata", "completed")
        budget.emit("object_attribution", "started")
        report["owned_objects"] = _owned_objects(connection, budget)
        report["actual_scope"].append("object_attribution")
        report["checks"]["object_attribution"] = (
            "checked" if report["owned_objects"]["available"] else "unknown")
        budget.emit("object_attribution", "completed",
                    available=report["owned_objects"]["available"])
        if detail == "logical":
            tables = [str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ) if str(row[0]).startswith(_OWNED_PREFIXES)]
            budget.emit("logical_payloads", "started", scan_limit_rows=scan_limit)
            report["logical"] = _logical_usage(connection, tables, scan_limit, budget)
            report["actual_scope"].append("logical_payloads")
            report["checks"]["logical_payloads"] = (
                "checked" if report["logical"]["complete"] else "partial")
            if not report["logical"]["complete"]:
                report["complete"] = False
                report["stopped_reason"] = "scan_limit"
            budget.emit("logical_payloads", "completed",
                        complete=report["logical"]["complete"],
                        rows_scanned=report["logical"]["rows_scanned"])
        connection.rollback()
        budget.clear(connection)
    except InspectionBudgetExceeded:
        report["complete"] = False
        report["stopped_reason"] = budget.stopped_reason or "timeout"
        requested = ["sqlite_metadata", "object_attribution"]
        if detail == "logical":
            requested.append("logical_payloads")
        for name in requested:
            if report["checks"][name] == "not_checked":
                report["checks"][name] = "unknown"
        budget.emit("storage_usage", "stopped", reason=report["stopped_reason"])
    except sqlite3.DatabaseError as error:
        if not budget.interrupted(error):
            if connection is not None:
                connection.rollback()
            raise
        report["complete"] = False
        report["stopped_reason"] = budget.stopped_reason or "timeout"
        requested = ["sqlite_metadata", "object_attribution"]
        if detail == "logical":
            requested.append("logical_payloads")
        for name in requested:
            if report["checks"][name] == "not_checked":
                report["checks"][name] = "unknown"
        budget.emit("storage_usage", "stopped", reason=report["stopped_reason"])
    except BaseException:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()

    # Stat after the snapshot work.  This remains observational only and is
    # explicitly reported as non-atomic with the SQLite transaction.
    report["files"] = _files(database)
    report["physical_total_bytes"] = sum(item["bytes"] for item in report["files"].values())
    report["elapsed_seconds"] = budget.elapsed_seconds
    return report


__all__ = ["StorageUsageDetail", "StorageUsageReport", "inspect_storage_usage"]
