"""Read-only deployment preflight and consistent, non-overwriting SQLite backups."""

from __future__ import annotations

from contextlib import contextmanager
import os
import json
import math
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Callable, Literal, Mapping

from ._inspection import InspectionBudget, InspectionBudgetExceeded, ProgressCallbackError
from .execution_kernel._registry import Handler, handler_revision, normalize_handlers, registry_revision
from .execution_kernel._sqlite_schema import existing_table_names, validate_schema
from .execution_kernel.contracts import ExecutionCommandV2
from .execution_kernel.transitions import TERMINAL_STATES
from .storage_usage import inspect_storage_usage
from .maintenance import maintenance_lease, inspect_maintenance, storage_participant


@contextmanager
def _read_only(path, *, timeout: float = 30):
    source = Path(path).resolve(strict=True)
    connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=timeout)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        yield connection
    finally:
        connection.close()


StorageInspectionCheck = Literal["schema", "bindings", "full"]


def _validate_kernel_schema_light(connection: sqlite3.Connection, kernel_tables: set[str]) -> None:
    """Validate Kernel structure without the event-history consistency scan.

    The writer's validator intentionally also compares ``MAX(sequence)`` with
    the clock.  That is a data integrity check and can scan a large history, so
    the schema and binding tiers use the same exact structural checks while
    leaving that invariant to the full tier.
    """
    from .execution_kernel import _sqlite_schema as schema

    if kernel_tables != set(schema.KERNEL_TABLES):
        missing = sorted(schema.KERNEL_TABLES - kernel_tables)
        extra = sorted(kernel_tables - schema.KERNEL_TABLES)
        raise ValueError(f"incompatible execution-kernel table set; missing={missing!r}, unexpected={extra!r}")
    objects = connection.execute(
        "SELECT name,type,sql FROM sqlite_master WHERE name LIKE 'kernel_%' ORDER BY name"
    ).fetchall()
    if {row["name"] for row in objects} != schema.KERNEL_TABLES | schema.KERNEL_INDEXES:
        raise ValueError("incompatible execution-kernel schema object set")
    for table, expected in schema.EXPECTED_COLUMNS.items():
        if schema._table_columns(connection, table) != expected:
            raise ValueError(f"incompatible v2 column schema: {table}")
    sql_by_name = {row["name"]: schema._normalize_sql(row["sql"] or "") for row in objects}
    for name, expected in schema._expected_object_sql().items():
        if sql_by_name.get(name) != expected:
            raise ValueError(f"incompatible exact schema definition: {name}")
    for table, fragments in schema.SQL_REQUIREMENTS.items():
        if any(schema._normalize_sql(fragment) not in sql_by_name[table] for fragment in fragments):
            raise ValueError(f"weakened or incompatible CHECK schema: {table}")
    for name, expected in schema.EXPECTED_INDEX_SQL.items():
        if sql_by_name.get(name) != expected:
            raise ValueError(f"incompatible index definition: {name}")
    meta = connection.execute(
        "SELECT component,schema_version,typeof(schema_version) FROM kernel_schema_meta"
    ).fetchall()
    if (len(meta) != 1 or meta[0][0] != "execution_kernel" or type(meta[0][1]) is not int
            or meta[0][1] != 2 or meta[0][2] != "integer"):
        raise ValueError("kernel_schema_meta must contain exactly execution_kernel schema v2")
    clock = connection.execute(
        "SELECT singleton,watermark,event_sequence,typeof(watermark),typeof(event_sequence) FROM kernel_clock"
    ).fetchall()
    if (len(clock) != 1 or clock[0][0] != 1 or type(clock[0][2]) is not int
            or clock[0][2] < 0 or clock[0][3] not in {"integer", "real"}
            or clock[0][4] != "integer" or not math.isfinite(float(clock[0][1]))
            or clock[0][1] < 0):
        raise ValueError("kernel_clock must contain one valid watermark row")


def _new_storage_report(path: str | Path, check: StorageInspectionCheck) -> dict[str, Any]:
    return {
        "path": str(Path(path).resolve()), "exists": Path(path).exists(),
        "compatible": None, "kernel_schema": "absent", "orchestrator_schema": "absent",
        "inbox_schema": "absent", "sandbox_schema": "absent", "sandbox_registry_schema": "absent",
        "journal_mode": None, "issues": [], "execution_counts": {},
        "binding_mismatch_count": 0, "binding_mismatches": [],
        "requested_check": check, "actual_scope": ["existence"],
        "checks": {"schema": "not_checked", "integrity": "not_checked",
                   "bindings": "not_checked", "execution_counts": "not_checked"},
        "complete": True, "stopped_reason": None, "elapsed_seconds": 0.0,
    }


def _inspect_storage(path: str | Path, *, handlers: Mapping[Any, Handler] | None,
                     check: StorageInspectionCheck, budget: InspectionBudget,
                     snapshot_name: str = "main") -> dict[str, Any]:
    report = _new_storage_report(path, check)
    if not report["exists"]:
        report["checks"]["schema"] = "not_applicable"
        report["checks"]["integrity"] = "not_applicable" if check == "full" else "not_checked"
        report["checks"]["bindings"] = "not_applicable" if handlers is not None else "not_checked"
        report["elapsed_seconds"] = budget.elapsed_seconds
        return report
    normalized = None
    full_revision = None
    bindings: dict[tuple[str, int], str] = {}
    budget.emit("storage", "started", snapshot=snapshot_name, path=report["path"], check=check)
    try:
        budget.check()
        if handlers is not None and check != "schema":
            normalized = normalize_handlers(handlers)
            budget.check()
            full_revision = registry_revision(normalized)
            budget.check()
            for key in normalized:
                budget.check()
                bindings[key] = handler_revision(normalized, *key)
                budget.check()
        with _read_only(path, timeout=budget.sqlite_timeout_seconds) as connection:
            budget.install(connection)
            connection.execute("BEGIN")
            report["journal_mode"] = connection.execute("PRAGMA journal_mode").fetchone()[0]
            if check == "full":
                budget.emit("integrity", "started", snapshot=snapshot_name)
                integrity = [row[0] for row in connection.execute("PRAGMA quick_check")]
                report["actual_scope"].append("integrity")
                report["checks"]["integrity"] = "ok" if integrity == ["ok"] else "failed"
                if integrity != ["ok"]:
                    report["issues"].append({"component": "sqlite", "message": "; ".join(integrity)})
                budget.emit("integrity", "completed", snapshot=snapshot_name,
                            result=report["checks"]["integrity"])
            budget.emit("schema", "started", snapshot=snapshot_name)
            tables = existing_table_names(connection)
            if any(name.startswith("cancellation_") for name in tables):
                from .execution_kernel.cancellation import validate_cancellation_schema
                report["cancellation_schema"] = "unsupported"
                try:
                    report["cancellation_identity"] = validate_cancellation_schema(connection)
                    report["cancellation_schema"] = 1
                except (ValueError, sqlite3.Error) as error:
                    if isinstance(error, (InspectionBudgetExceeded, ProgressCallbackError)):
                        raise
                    if isinstance(error, sqlite3.DatabaseError) and budget.interrupted(error):
                        raise
                    report["issues"].append({"component": "cancellation", "message": str(error)})
            kernel_tables = {name for name in tables if name.startswith("kernel_")}
            kernel_valid = False
            if kernel_tables:
                report["kernel_schema"] = "unsupported"
                try:
                    if check == "full":
                        validate_schema(connection, kernel_tables)
                    else:
                        _validate_kernel_schema_light(connection, kernel_tables)
                except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                    if isinstance(error, (InspectionBudgetExceeded, ProgressCallbackError)):
                        raise
                    if isinstance(error, sqlite3.DatabaseError) and budget.interrupted(error):
                        raise
                    report["issues"].append({"component": "kernel", "message": str(error)})
                else:
                    kernel_valid = True
                    report["kernel_schema"] = 2
                    if check == "full":
                        report["execution_counts"] = {row[0]: row[1] for row in connection.execute(
                            "SELECT state,COUNT(*) FROM kernel_executions GROUP BY state")}
                        report["actual_scope"].append("execution_counts")
                        report["checks"]["execution_counts"] = "checked"
            sdk_valid = False
            sdk_tables = {name for name in tables if name.startswith("sdk_")}
            if sdk_tables:
                report["orchestrator_schema"] = "unsupported"
                try:
                    from .orchestrator.engine import Orchestrator
                    from .orchestrator.store import (SCHEMA, ORCHESTRATOR_SCHEMA_VERSION,
                                                     execute_schema, initialize_storage_tracking)
                    marker = connection.execute("SELECT component,version FROM sdk_schema_meta").fetchall()
                    if len(marker) != 1 or tuple(marker[0]) != ("orchestrator", ORCHESTRATOR_SCHEMA_VERSION):
                        raise ValueError("unsupported orchestration schema version")
                    reference = sqlite3.connect(":memory:")
                    try:
                        execute_schema(reference, SCHEMA)
                        Orchestrator._init_results(Orchestrator.__new__(Orchestrator), reference)
                        Orchestrator._init_notifications(reference)
                        initialize_storage_tracking(reference)
                        expected = Orchestrator._schema_objects(reference)
                        actual = Orchestrator._schema_objects(connection)
                        if actual != expected:
                            raise ValueError("orchestration schema differs from its declared version")
                    finally:
                        reference.close()
                    identity = connection.execute(
                        "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
                    ).fetchone()
                    clock = connection.execute(
                        "SELECT mutation FROM sdk_storage_clock WHERE singleton=1"
                    ).fetchone()
                    if (identity is None or any(type(value) is not str or not value for value in identity)
                            or clock is None or type(clock[0]) is not int or clock[0] < 0):
                        raise ValueError("orchestration storage identity or mutation clock is missing or damaged")
                except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                    if isinstance(error, (InspectionBudgetExceeded, ProgressCallbackError)):
                        raise
                    if isinstance(error, sqlite3.DatabaseError) and budget.interrupted(error):
                        raise
                    report["issues"].append({"component": "orchestrator", "message": str(error)})
                else:
                    sdk_valid = True
                    report["orchestrator_schema"] = ORCHESTRATOR_SCHEMA_VERSION
            if any(name.startswith("notification_inbox_") for name in tables):
                from .orchestrator.inbox import validate_inbox_schema
                report["inbox_schema"] = "unsupported"
                try:
                    validate_inbox_schema(connection)
                except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                    if isinstance(error, (InspectionBudgetExceeded, ProgressCallbackError)):
                        raise
                    if isinstance(error, sqlite3.DatabaseError) and budget.interrupted(error):
                        raise
                    report["issues"].append({"component": "inbox", "message": str(error)})
                else:
                    report["inbox_schema"] = 1
            if any(name.startswith("sandbox_") for name in tables):
                from .execution_kernel.sandbox import validate_sandbox_schema
                report["sandbox_schema"] = "unsupported"
                try:
                    validate_sandbox_schema(connection)
                except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                    if isinstance(error, (InspectionBudgetExceeded, ProgressCallbackError)):
                        raise
                    if isinstance(error, sqlite3.DatabaseError) and budget.interrupted(error):
                        raise
                    report["issues"].append({"component": "sandbox", "message": str(error)})
                else:
                    report["sandbox_schema"] = 1
            registry_bindings_checked = False
            if any(name.startswith("runtime_sandbox_") for name in tables):
                from .execution_kernel._sandbox_registry import validate_registry
                report["sandbox_registry_schema"] = "unsupported"
                try:
                    store_id = validate_registry(connection)
                    report["sandbox_registry_schema"] = 1
                    if check == "full" or check == "bindings" and normalized is not None:
                        from .execution_kernel.sandbox import SandboxHandler, validate_sandbox_schema
                        for journal_row in connection.execute(
                                "SELECT path FROM runtime_sandbox_journals ORDER BY path"):
                            budget.check()
                            try:
                                with _read_only(journal_row[0], timeout=budget.sqlite_timeout_seconds) as journal:
                                    budget.install(journal)
                                    journal.execute("BEGIN")
                                    validate_sandbox_schema(journal)
                                    if journal.execute("SELECT store_id FROM sandbox_meta").fetchone()[0] != store_id:
                                        raise ValueError("sandbox journal belongs to another store")
                                    for operation in journal.execute(
                                            "SELECT handler_id,handler_contract_version,backend_name,backend_revision "
                                            "FROM sandbox_operations WHERE cleanup_confirmed=0"):
                                        budget.check()
                                        if normalized is None:
                                            continue
                                        handler = normalized.get((operation[0], operation[1]))
                                        if (not isinstance(handler, SandboxHandler)
                                                or handler.journal_path != journal_row[0]
                                                or (handler.backend.name, handler.backend.revision)
                                                != (operation[2], operation[3])):
                                            raise ValueError("pending sandbox disposal requires its original handler and journal configuration")
                                    budget.check()
                                if normalized is not None:
                                    registry_bindings_checked = True
                            except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                                if isinstance(error, (InspectionBudgetExceeded, ProgressCallbackError)):
                                    raise
                                if isinstance(error, sqlite3.DatabaseError) and budget.interrupted(error):
                                    raise
                                report["issues"].append({"component": "sandbox",
                                    "journal_path": journal_row[0], "message": str(error)})
                except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                    if isinstance(error, (InspectionBudgetExceeded, ProgressCallbackError)):
                        raise
                    if isinstance(error, sqlite3.DatabaseError) and budget.interrupted(error):
                        raise
                    report["issues"].append({"component": "sandbox_registry", "message": str(error)})
            budget.check()
            report["actual_scope"].append("schema")
            schema_issues = [item for item in report["issues"] if item["component"] not in {"sqlite", "deployment"}]
            report["checks"]["schema"] = "failed" if schema_issues else "checked"
            budget.emit("schema", "completed", snapshot=snapshot_name,
                        result=report["checks"]["schema"])

            def inspect_command(text):
                budget.check()
                command = ExecutionCommandV2.from_json(text)
                budget.check()
                if command.registry_revision == full_revision or command.registry_revision == bindings.get(
                        (command.handler_id, command.handler_contract_version)):
                    return
                report["binding_mismatch_count"] += 1
                if len(report["binding_mismatches"]) < 100:
                    report["binding_mismatches"].append({"execution_id": command.execution_id,
                        "handler_id": command.handler_id,
                        "handler_contract_version": command.handler_contract_version,
                        "required_revision": command.registry_revision})

            if normalized is not None and check in ("bindings", "full"):
                budget.emit("bindings", "started", snapshot=snapshot_name)
                binding_blocked = ((bool(kernel_tables) and not kernel_valid)
                                   or (bool(sdk_tables) and not sdk_valid))
                if kernel_valid and not binding_blocked:
                    placeholders = ",".join("?" for _ in TERMINAL_STATES)
                    for row in connection.execute(
                            f"SELECT command_json FROM kernel_executions WHERE state NOT IN ({placeholders})",
                            tuple(TERMINAL_STATES)):
                        inspect_command(row[0])
                if sdk_valid and not binding_blocked:
                    query = "SELECT command,run_id,task_id,attempt FROM sdk_executions"
                    if kernel_valid:
                        query += " WHERE execution_id NOT IN (SELECT execution_id FROM kernel_executions)"
                    for row in connection.execute(query):
                        budget.check()
                        from .orchestrator.contracts import canonical, TERMINAL
                        attempt = connection.execute(
                            "SELECT value FROM sdk_run_items WHERE run_id=? AND section='attempt' AND item_key=?",
                            (row[1], canonical([row[2], row[3]]))).fetchone()
                        terminal = attempt is not None and json.loads(attempt[0])["state"] in TERMINAL
                        budget.check()
                        if terminal:
                            continue
                        inspect_command(row[0])
                budget.check()
                if binding_blocked:
                    report["checks"]["bindings"] = "unknown"
                elif kernel_valid or sdk_valid or registry_bindings_checked:
                    report["actual_scope"].append("bindings")
                    report["checks"]["bindings"] = "checked"
                else:
                    report["checks"]["bindings"] = "not_applicable"
                budget.emit("bindings", "completed", snapshot=snapshot_name,
                            result=report["checks"]["bindings"],
                            mismatches=report["binding_mismatch_count"])
            if report["binding_mismatch_count"]:
                report["issues"].append({"component": "deployment", "message":
                    "unfinished commands require unavailable handler bindings; retain the old deployment to drain or recover them"})
            budget.check()
            budget.clear(connection)
    except InspectionBudgetExceeded:
        report["complete"] = False
        report["stopped_reason"] = budget.stopped_reason or "timeout"
    except sqlite3.DatabaseError as error:
        if not budget.interrupted(error):
            raise
        report["complete"] = False
        report["stopped_reason"] = budget.stopped_reason or "timeout"
    if not report["complete"]:
        for name, status in tuple(report["checks"].items()):
            if status not in {"ok", "failed", "checked", "not_applicable"}:
                report["checks"][name] = "unknown" if (
                    name == "integrity" and check == "full"
                    or name == "schema"
                    or name == "bindings" and handlers is not None and check in ("bindings", "full")
                ) else status
        budget.emit("storage", "stopped", snapshot=snapshot_name, reason=report["stopped_reason"])
    else:
        budget.emit("storage", "completed", snapshot=snapshot_name)
    report["compatible"] = (False if report["issues"] else
                            True if check == "full" and report["complete"] else None)
    report["elapsed_seconds"] = budget.elapsed_seconds
    return report


def inspect_storage(path: str | Path, *, handlers: Mapping[Any, Handler] | None = None,
                    check: StorageInspectionCheck = "full", timeout_seconds: float | None = None,
                    progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Inspect a consistent read snapshot without opening or upgrading an SDK writer.

    ``schema`` checks catalog structure without table/history scans. ``bindings``
    adds unfinished-command binding scans. ``full`` preserves the historical
    schema, integrity, count and optional binding checks. It cannot
    observe another connection's synchronous profile or prove fsync hardware
    guarantees. A missing path is reported without creating it.
    """
    if check not in ("schema", "bindings", "full"):
        raise ValueError("check must be 'schema', 'bindings', or 'full'")
    budget = InspectionBudget(timeout_seconds, progress)
    return _inspect_storage(path, handlers=handlers, check=check, budget=budget)


def _sync_directory(path: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


@contextmanager
def _new_artifact(destination):
    target = Path(destination).absolute()
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".dispatcher-backup-", dir=target.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        yield temporary
        # Windows flush requires a writable handle; this is our completed
        # temporary artifact, never the caller's source database.
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        # Same-directory hard link publishes atomically and refuses an existing
        # destination. No rename-overwrite race can replace the user's backup.
        os.link(temporary, target)
        _sync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)


def backup_database(source: str | Path, destination: str | Path) -> Path:
    """Take one online SQLite snapshot including committed WAL data.

    Other databases (for example a separate sandbox journal/inbox) need their own
    backups. Stop writers if the application requires a coordinated multi-DB cut.
    Existing destinations are never overwritten. Source schema need not be current.
    """
    with _read_only(source) as connection, _new_artifact(destination) as temporary:
        target = sqlite3.connect(temporary)
        try:
            connection.backup(target)
            if target.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("backup integrity check failed")
            # Produce a standalone file, not a main file dependent on a sidecar.
            target.execute("PRAGMA journal_mode=DELETE")
            target.commit()
        finally:
            target.close()
    return Path(destination).absolute()


def export_database(source: str | Path, destination: str | Path) -> Path:
    """Export a read-consistent SQL dump, including unsupported legacy schemas."""
    with _read_only(source) as connection, _new_artifact(destination) as temporary:
        connection.execute("BEGIN")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for line in connection.iterdump():
                stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return Path(destination).absolute()


__all__ = ["inspect_storage", "inspect_storage_usage", "backup_database", "export_database",
           "maintenance_lease", "inspect_maintenance", "storage_participant"]
