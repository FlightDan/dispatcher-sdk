"""Read-only deployment preflight and consistent, non-overwriting SQLite backups."""

from __future__ import annotations

from contextlib import contextmanager
import os
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Mapping

from .execution_kernel._registry import Handler, handler_revision, normalize_handlers, registry_revision
from .execution_kernel._sqlite_schema import existing_table_names, validate_schema
from .execution_kernel.contracts import ExecutionCommandV2
from .execution_kernel.transitions import TERMINAL_STATES


@contextmanager
def _read_only(path):
    source = Path(path).resolve(strict=True)
    connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        yield connection
    finally:
        connection.close()


def inspect_storage(path: str | Path, *, handlers: Mapping[Any, Handler] | None = None) -> dict[str, Any]:
    """Inspect a consistent read snapshot without opening or upgrading an SDK writer.

    Checks persisted schema, integrity and unfinished command bindings. It cannot
    observe another connection's synchronous profile or prove fsync hardware
    guarantees. A missing path is reported without creating it.
    """
    report: dict[str, Any] = {"path": str(Path(path).resolve()), "exists": Path(path).exists(),
        "compatible": True, "kernel_schema": "absent", "orchestrator_schema": "absent",
        "inbox_schema": "absent", "sandbox_schema": "absent", "sandbox_registry_schema": "absent",
        "journal_mode": None, "issues": [], "execution_counts": {},
        "binding_mismatch_count": 0, "binding_mismatches": []}
    if not report["exists"]:
        return report
    normalized = None if handlers is None else normalize_handlers(handlers)
    full_revision = None if normalized is None else registry_revision(normalized)
    bindings = {} if normalized is None else {key: handler_revision(normalized, *key) for key in normalized}
    with _read_only(path) as connection:
        connection.execute("BEGIN")
        report["journal_mode"] = connection.execute("PRAGMA journal_mode").fetchone()[0]
        integrity = [row[0] for row in connection.execute("PRAGMA quick_check")]
        if integrity != ["ok"]:
            report["issues"].append({"component": "sqlite", "message": "; ".join(integrity)})
        tables = existing_table_names(connection)
        if any(name.startswith("cancellation_") for name in tables):
            from .execution_kernel.cancellation import validate_cancellation_schema
            report["cancellation_schema"] = "unsupported"
            try:
                report["cancellation_identity"] = validate_cancellation_schema(connection)
                report["cancellation_schema"] = 1
            except (ValueError, sqlite3.Error) as error:
                report["issues"].append({"component": "cancellation", "message": str(error)})
        kernel_tables = {name for name in tables if name.startswith("kernel_")}
        kernel_valid = False
        if kernel_tables:
            report["kernel_schema"] = "unsupported"
            try:
                validate_schema(connection, kernel_tables)
            except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                report["issues"].append({"component": "kernel", "message": str(error)})
            else:
                kernel_valid = True
                report["kernel_schema"] = 2
                report["execution_counts"] = {row[0]: row[1] for row in connection.execute(
                    "SELECT state,COUNT(*) FROM kernel_executions GROUP BY state")}
        sdk_valid = False
        sdk_tables = {name for name in tables if name.startswith("sdk_")}
        if sdk_tables:
            report["orchestrator_schema"] = "unsupported"
            try:
                from .orchestrator.engine import Orchestrator
                from .orchestrator.store import SCHEMA, execute_schema

                marker = connection.execute("SELECT component,version FROM sdk_schema_meta").fetchall()
                if len(marker) != 1 or tuple(marker[0]) != ("orchestrator", 2):
                    raise ValueError("unsupported orchestration schema version")
                reference = sqlite3.connect(":memory:")
                try:
                    execute_schema(reference, SCHEMA)
                    Orchestrator._init_results(Orchestrator.__new__(Orchestrator), reference)
                    Orchestrator._init_notifications(reference)
                    expected = Orchestrator._schema_objects(reference)
                    actual = Orchestrator._schema_objects(connection)
                    if actual != expected:
                        raise ValueError("orchestration schema differs from its declared version")
                finally:
                    reference.close()
            except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                report["issues"].append({"component": "orchestrator", "message": str(error)})
            else:
                sdk_valid = True
                report["orchestrator_schema"] = 2
        if any(name.startswith("notification_inbox_") for name in tables):
            from .orchestrator.inbox import validate_inbox_schema
            report["inbox_schema"] = "unsupported"
            try:
                validate_inbox_schema(connection)
            except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                report["issues"].append({"component": "inbox", "message": str(error)})
            else:
                report["inbox_schema"] = 1
        if any(name.startswith("sandbox_") for name in tables):
            from .execution_kernel.sandbox import validate_sandbox_schema
            report["sandbox_schema"] = "unsupported"
            try:
                validate_sandbox_schema(connection)
            except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                report["issues"].append({"component": "sandbox", "message": str(error)})
            else:
                report["sandbox_schema"] = 1
        if any(name.startswith("runtime_sandbox_") for name in tables):
            from .execution_kernel._sandbox_registry import validate_registry
            from .execution_kernel.sandbox import SandboxHandler, validate_sandbox_schema
            report["sandbox_registry_schema"] = "unsupported"
            try:
                store_id = validate_registry(connection)
                report["sandbox_registry_schema"] = 1
                for journal_row in connection.execute("SELECT path FROM runtime_sandbox_journals ORDER BY path"):
                    try:
                        with _read_only(journal_row[0]) as journal:
                            journal.execute("BEGIN")
                            validate_sandbox_schema(journal)
                            if journal.execute("SELECT store_id FROM sandbox_meta").fetchone()[0] != store_id:
                                raise ValueError("sandbox journal belongs to another store")
                            for operation in journal.execute(
                                    "SELECT handler_id,handler_contract_version,backend_name,backend_revision "
                                    "FROM sandbox_operations WHERE cleanup_confirmed=0"):
                                if normalized is None:
                                    continue
                                handler = normalized.get((operation[0], operation[1]))
                                if (not isinstance(handler, SandboxHandler) or handler.journal_path != journal_row[0]
                                        or (handler.backend.name, handler.backend.revision) != (operation[2], operation[3])):
                                    raise ValueError("pending sandbox disposal requires its original handler and journal configuration")
                    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                        report["issues"].append({"component": "sandbox", "journal_path": journal_row[0], "message": str(error)})
            except (ValueError, RuntimeError, sqlite3.DatabaseError) as error:
                report["issues"].append({"component": "sandbox_registry", "message": str(error)})

        def inspect_command(text):
            command = ExecutionCommandV2.from_json(text)
            if command.registry_revision == full_revision or command.registry_revision == bindings.get(
                    (command.handler_id, command.handler_contract_version)):
                return
            report["binding_mismatch_count"] += 1
            if len(report["binding_mismatches"]) < 100:
                report["binding_mismatches"].append({"execution_id": command.execution_id,
                    "handler_id": command.handler_id, "handler_contract_version": command.handler_contract_version,
                    "required_revision": command.registry_revision})

        if normalized is not None and kernel_valid:
            placeholders = ",".join("?" for _ in TERMINAL_STATES)
            for row in connection.execute(
                    f"SELECT command_json FROM kernel_executions WHERE state NOT IN ({placeholders})",
                    tuple(TERMINAL_STATES)):
                inspect_command(row[0])
        if normalized is not None and sdk_valid:
            query = "SELECT command,run_id,task_id,attempt FROM sdk_executions"
            if kernel_valid:
                query += " WHERE execution_id NOT IN (SELECT execution_id FROM kernel_executions)"
            for row in connection.execute(query):
                from .orchestrator.contracts import canonical, TERMINAL
                attempt = connection.execute(
                    "SELECT value FROM sdk_run_items WHERE run_id=? AND section='attempt' AND item_key=?",
                    (row[1], canonical([row[2], row[3]]))).fetchone()
                if attempt is not None and json.loads(attempt[0])["state"] in TERMINAL:
                    continue
                inspect_command(row[0])
        if report["binding_mismatch_count"]:
            report["issues"].append({"component": "deployment", "message":
                "unfinished commands require unavailable handler bindings; retain the old deployment to drain or recover them"})
    report["compatible"] = not report["issues"]
    return report


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


__all__ = ["inspect_storage", "backup_database", "export_database"]
