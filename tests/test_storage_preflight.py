from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

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
            self.assertEqual((good["kernel_schema"], good["orchestrator_schema"]), (2, 3))
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
        light = inspect_storage(self.path, check="schema")
        self.assertFalse(light["compatible"])
        self.assertEqual(light["checks"]["integrity"], "not_checked")

    def test_schema_tier_rejects_invalid_kernel_clock_without_history_scan(self):
        with Runtime(self.path, {}, isolation_mode="thread"):
            pass
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE kernel_clock SET watermark=-1")
        report = inspect_storage(self.path, check="schema")
        self.assertFalse(report["compatible"])
        self.assertEqual(report["kernel_schema"], "unsupported")
        self.assertEqual(report["checks"]["integrity"], "not_checked")

    def test_all_tiers_reject_invalid_orchestrator_singletons(self):
        with Runtime(self.path, {}, isolation_mode="thread") as runtime:
            Orchestrator(self.path, runtime.kernel)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE sdk_storage_identity SET store_id='' WHERE singleton=1")
            connection.execute("UPDATE sdk_storage_clock SET mutation=-1 WHERE singleton=1")
        for check in ("schema", "bindings", "full"):
            with self.subTest(check=check):
                report = inspect_storage(self.path, handlers={}, check=check)
                self.assertFalse(report["compatible"])
                self.assertEqual(report["orchestrator_schema"], "unsupported")

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

    def test_schema_tier_avoids_integrity_counts_and_binding_scans(self):
        with Runtime(self.path, {"echo": echo}, isolation_mode="thread") as runtime:
            command = runtime.command("echo", execution_id="x", idempotency_key="x",
                                      correlation_id="r", timeout_seconds=1, payload={"large": "x" * 1000})
            runtime.kernel.submit(command)
        # A large history makes an accidental MAX/COUNT/history walk observable
        # as a real cost; the schema tier must stay catalog-only regardless.
        with closing(sqlite3.connect(self.path)) as connection, connection:
            start = connection.execute("SELECT event_sequence FROM kernel_clock").fetchone()[0]
            rows = [(start + number, f"bulk-{number}", f"bulk-execution-{number}", 1,
                     "fixture", None, "queued", "{}", 1.0)
                    for number in range(1, 5_001)]
            connection.executemany("INSERT INTO kernel_events VALUES(?,?,?,?,?,?,?,?,?)", rows)
            connection.execute("UPDATE kernel_clock SET event_sequence=?", (start + len(rows),))
        statements = []
        from dispatcher_sdk import storage
        original = storage._read_only

        @contextmanager
        def traced(*args, **kwargs):
            with original(*args, **kwargs) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with mock.patch("dispatcher_sdk.storage._read_only", side_effect=traced):
            with mock.patch("dispatcher_sdk.storage.normalize_handlers",
                            side_effect=AssertionError("schema tier normalized handlers")):
                report = inspect_storage(self.path, handlers={"echo": other}, check="schema")

        sql = [" ".join(statement.upper().split()) for statement in statements]
        self.assertEqual(report["checks"]["schema"], "checked")
        self.assertEqual(report["checks"]["integrity"], "not_checked")
        self.assertEqual(report["checks"]["bindings"], "not_checked")
        self.assertIsNone(report["compatible"])
        self.assertFalse(any("QUICK_CHECK" in statement for statement in sql))
        self.assertFalse(any("COUNT(" in statement or "MAX(SEQUENCE)" in statement
                             or "COMMAND_JSON FROM KERNEL_EXECUTIONS" in statement
                             for statement in sql))

    def test_bindings_tier_detects_mismatch_without_integrity_scan(self):
        with Runtime(self.path, {"echo": echo}, isolation_mode="thread") as runtime:
            runtime.kernel.submit(runtime.command(
                "echo", execution_id="x", idempotency_key="x", correlation_id="r",
                timeout_seconds=1, payload=None))
        report = inspect_storage(self.path, handlers={"echo": other}, check="bindings")
        self.assertEqual(report["checks"]["integrity"], "not_checked")
        self.assertEqual(report["checks"]["bindings"], "checked")
        self.assertEqual(report["binding_mismatch_count"], 1)
        self.assertFalse(report["compatible"])

    def test_final_command_decode_cannot_report_complete_after_its_budget(self):
        from dispatcher_sdk.execution_kernel import ExecutionCommandV2

        with Runtime(self.path, {"echo": echo}, isolation_mode="thread") as runtime:
            runtime.kernel.submit(runtime.command(
                "echo", execution_id="last", idempotency_key="last", correlation_id="r",
                timeout_seconds=1, payload=None))
        clock = [0.0]
        original = ExecutionCommandV2.from_json

        def slow_decode(value):
            result = original(value)
            clock[0] = 2.0
            return result

        with mock.patch("dispatcher_sdk._inspection.time.monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(ExecutionCommandV2, "from_json", side_effect=slow_decode):
            report = inspect_storage(self.path, handlers={"echo": echo}, check="bindings", timeout_seconds=1)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "timeout")
        self.assertEqual(report["checks"]["bindings"], "unknown")
        self.assertIsNone(report["compatible"])

    def test_timeout_is_incomplete_unknown_not_damage(self):
        with Runtime(self.path, {}, isolation_mode="thread"):
            pass
        events = []
        report = inspect_storage(self.path, timeout_seconds=0, progress=events.append)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "timeout")
        self.assertIsNone(report["compatible"])
        self.assertFalse(report["issues"])
        self.assertEqual(report["checks"]["integrity"], "unknown")
        self.assertTrue(events)
        self.assertTrue(all("percent" not in event for event in events))

    def test_expired_budget_does_not_fingerprint_handlers(self):
        with Runtime(self.path, {}, isolation_mode="thread"):
            pass
        with mock.patch("dispatcher_sdk.storage.normalize_handlers",
                        side_effect=AssertionError("fingerprinted after timeout")):
            report = inspect_storage(self.path, handlers={"echo": echo}, timeout_seconds=0)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "timeout")

    def test_sqlite_progress_handler_interrupts_large_integrity_scan(self):
        with Runtime(self.path, {}, isolation_mode="thread"):
            pass
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE app_large(value BLOB)")
            connection.executemany("INSERT INTO app_large VALUES(zeroblob(512))",
                                   [() for _ in range(20_000)])

        class Clock:
            now = 0.0

            def __call__(self):
                return self.now

        clock = Clock()

        def advance(event):
            if event["phase"] == "integrity" and event["status"] == "started":
                clock.now = 2.0

        with mock.patch("dispatcher_sdk._inspection.time.monotonic", clock):
            report = inspect_storage(self.path, timeout_seconds=1, progress=advance)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "timeout")
        self.assertEqual(report["checks"]["integrity"], "unknown")
        self.assertFalse(report["issues"])
        self.assertIsNone(report["compatible"])

    def test_invalid_cost_options_are_rejected_before_open(self):
        with self.assertRaises(ValueError):
            inspect_storage(self.path, check="deep")
        with self.assertRaises(ValueError):
            inspect_storage(self.path, timeout_seconds=-1)
        self.assertFalse(self.path.exists())

    def test_progress_callback_failure_propagates(self):
        with Runtime(self.path, {}, isolation_mode="thread"):
            pass

        def fail(_event):
            raise LookupError("observer failed")

        with self.assertRaisesRegex(RuntimeError, "progress callback failed") as raised:
            inspect_storage(self.path, progress=fail)
        self.assertIsInstance(raised.exception.__cause__, LookupError)
