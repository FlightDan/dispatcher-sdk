from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dispatcher_sdk.execution_kernel import Runtime
from dispatcher_sdk.orchestrator import Orchestrator, Operations, NotificationInbox
from dispatcher_sdk.storage import inspect_storage, backup_database, export_database


def echo(payload, context):
    return payload


def other(payload, context):
    return {"other": payload}


class StoragePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "source.db"

    def test_missing_and_legacy_store_are_inspected_without_initialization(self):
        report = inspect_storage(self.path)
        self.assertFalse(report["exists"])
        self.assertFalse(self.path.exists())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_runs(run_id TEXT, snapshot TEXT)")
            connection.execute("INSERT INTO sdk_runs VALUES('old','preserve')")
        before = self.path.read_bytes()
        report = inspect_storage(self.path)
        self.assertFalse(report["compatible"])
        self.assertEqual(report["orchestrator_schema"], "unsupported")
        self.assertEqual(before, self.path.read_bytes())
        backup = backup_database(self.path, self.root / "legacy-backup.db")
        with closing(sqlite3.connect(backup)) as connection, connection:
            self.assertEqual(connection.execute("SELECT snapshot FROM sdk_runs").fetchone()[0], "preserve")

    def test_binding_check_includes_unflushed_orchestration_work(self):
        with Runtime(self.path, {"echo": echo}, isolation_mode="thread") as runtime:
            sdk = Orchestrator(self.path, runtime.kernel)
            sdk.create_run("run", command_id="create")
            command = runtime.command("echo", execution_id="x", idempotency_key="x",
                                      correlation_id="r", timeout_seconds=1, payload="hello")
            sdk.apply_operations("run", command_id="add", expected_revision=0,
                                 operations=[Operations.add_task("task", command)])
            good = inspect_storage(self.path, handlers={"echo": echo, "unrelated": other})
            self.assertTrue(good["compatible"], good)
            self.assertEqual((good["kernel_schema"], good["orchestrator_schema"]), (2, 2))
            mismatch = inspect_storage(self.path, handlers={"echo": other})
            self.assertFalse(mismatch["compatible"])
            self.assertEqual(mismatch["binding_mismatch_count"], 1)
            self.assertEqual(mismatch["binding_mismatches"][0]["execution_id"], "x")

    def test_backup_includes_wal_and_never_overwrites_existing_destination(self):
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute("CREATE TABLE application(value TEXT)")
            connection.execute("INSERT INTO application VALUES('committed WAL content')")
            connection.commit()
            self.assertTrue(Path(str(self.path) + "-wal").exists())
            destination = self.root / "snapshot.db"
            backup_database(self.path, destination)
            with closing(sqlite3.connect(destination)) as backup, backup:
                self.assertEqual(backup.execute("SELECT value FROM application").fetchone()[0], "committed WAL content")
                self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            before = destination.read_bytes()
            with self.assertRaises(FileExistsError):
                backup_database(self.path, destination)
            self.assertEqual(before, destination.read_bytes())
            self.assertFalse(Path(str(destination) + "-wal").exists())
        finally:
            connection.close()

    def test_sql_export_restores_legacy_rows_and_refuses_overwrite(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE app(value TEXT)")
            connection.execute("INSERT INTO app VALUES(?)", ("quotes ' and\nnewlines",))
        destination = self.root / "export.sql"
        export_database(self.path, destination)
        with closing(sqlite3.connect(":memory:")) as restored, restored:
            restored.executescript(destination.read_text())
            self.assertEqual(restored.execute("SELECT value FROM app").fetchone()[0], "quotes ' and\nnewlines")
        with self.assertRaises(FileExistsError):
            export_database(self.path, destination)

    def test_kernel_schema_literal_damage_is_reported(self):
        with Runtime(self.path, {}, isolation_mode="thread"):
            pass
        with closing(sqlite3.connect(self.path)) as connection, connection:
            sql = connection.execute("SELECT sql FROM sqlite_master WHERE name='kernel_executions'").fetchone()[0]
            connection.execute("PRAGMA writable_schema=ON")
            connection.execute("UPDATE sqlite_master SET sql=? WHERE name='kernel_executions'",
                               (sql.replace("'queued'", "'QUEUED'"),))
            connection.execute("PRAGMA schema_version=99")
        self.assertFalse(inspect_storage(self.path)["compatible"])

    def test_planned_cancelled_task_does_not_require_retaining_its_old_handler(self):
        with Runtime(self.path, {"echo": echo}, isolation_mode="thread") as runtime:
            sdk = Orchestrator(self.path, runtime.kernel)
            sdk.create_run("run", command_id="create")
            command = runtime.command("echo", execution_id="x", idempotency_key="x",
                                      correlation_id="r", timeout_seconds=1, payload=None)
            sdk.apply_operations("run", command_id="cancel-before-dispatch", expected_revision=0,
                operations=[Operations.add_task("task", command), Operations.cancel("task", reason="unneeded")])
            report = inspect_storage(self.path, handlers={"echo": other})
            self.assertTrue(report["compatible"], report)
            self.assertEqual(report["binding_mismatch_count"], 0)

    def test_inbox_schema_is_checked_read_only(self):
        NotificationInbox(self.path)
        report = inspect_storage(self.path)
        self.assertTrue(report["compatible"], report)
        self.assertEqual(report["inbox_schema"], 1)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("ALTER TABLE notification_inbox_messages RENAME COLUMN settlement TO old_settlement")
        before = self.path.read_bytes()
        report = inspect_storage(self.path)
        self.assertFalse(report["compatible"])
        self.assertEqual(report["inbox_schema"], "unsupported")
        self.assertEqual(self.path.read_bytes(), before)
