"""Explicit copy upgrade preserves v4 Run history and fails closed."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dispatcher_sdk.maintenance import maintenance_lease
from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator.run_diagnostics import inspect_run_diagnostics
from dispatcher_sdk.orchestrator.notifications import NotificationsMixin
from dispatcher_sdk.orchestrator.results import ResultsMixin
from dispatcher_sdk.orchestrator.store import SCHEMA_V4, execute_schema, initialize_storage_tracking
from dispatcher_sdk.storage_migration import upgrade_storage


class OrchestratorV5UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source.sqlite"
        self.target = Path(self.temp.name) / "target.sqlite"
        with closing(sqlite3.connect(self.source)) as connection:
            execute_schema(connection, SCHEMA_V4)
            results = ResultsMixin()
            results.max_result_deliveries = 5
            results._init_results(connection)
            NotificationsMixin._init_notifications(connection)
            connection.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',4)")
            connection.execute("INSERT INTO sdk_storage_identity VALUES(1,'store','incarnation',1)")
            connection.execute("INSERT INTO sdk_storage_clock VALUES(1,0)")
            initialize_storage_tracking(connection)
            connection.execute("INSERT INTO sdk_runs VALUES('original-run',7,'running')")
            connection.execute("INSERT INTO sdk_events(run_id,revision,kind,payload) VALUES('original-run',7,'test','{}')")
            connection.commit()

    def test_v4_copy_preserves_original_run_and_storage_identity(self):
        with maintenance_lease(self.source, "test", "upgrade") as lease:
            result = upgrade_storage(self.source, self.target, lease=lease)
        self.assertEqual((result["source_version"], result["target_version"]), (4, 6))
        with closing(sqlite3.connect(self.source)) as source, closing(sqlite3.connect(self.target)) as target:
            self.assertEqual(source.execute("SELECT version FROM sdk_schema_meta").fetchone()[0], 4)
            self.assertEqual(target.execute("SELECT version FROM sdk_schema_meta").fetchone()[0], 6)
            for table in ("sdk_runs", "sdk_events", "sdk_storage_identity"):
                self.assertEqual(source.execute(f"SELECT * FROM {table}").fetchall(),
                                 target.execute(f"SELECT * FROM {table}").fetchall())
            self.assertEqual(target.execute("SELECT COUNT(*) FROM sdk_dispatch_permits").fetchone()[0], 0)
            self.assertTrue(Orchestrator.__new__(Orchestrator)._validate_existing_store(target))
        report = inspect_run_diagnostics(self.target, "original-run")
        self.assertEqual(report.run_summary["run_id"], "original-run")
        self.assertIn("schema", report.phase_elapsed_seconds)
        self.assertIn("task_count", report.phase_elapsed_seconds)
        self.assertIsNone(report.stopped_phase)

    def test_failed_copy_leaves_original_and_no_target(self):
        def fail(stage):
            if stage == "after_schema":
                raise RuntimeError("injected")
        with maintenance_lease(self.source, "test", "upgrade") as lease:
            with self.assertRaisesRegex(RuntimeError, "injected"):
                upgrade_storage(self.source, self.target, lease=lease, failpoint=fail)
        self.assertFalse(self.target.exists())
        with closing(sqlite3.connect(self.source)) as connection:
            self.assertEqual(connection.execute("SELECT version FROM sdk_schema_meta").fetchone()[0], 4)
            self.assertEqual(connection.execute("SELECT run_id FROM sdk_runs").fetchone()[0], "original-run")

    def test_large_history_reports_bounded_count_and_continuation(self):
        with maintenance_lease(self.source, "test", "upgrade") as lease:
            upgrade_storage(self.source, self.target, lease=lease)
        with closing(sqlite3.connect(self.target)) as connection:
            connection.executemany(
                "INSERT INTO sdk_run_items VALUES(?,?,?,?)",
                (("original-run", "task", f"task-{number:05d}", "{}")
                 for number in range(12_000)),
            )
            connection.commit()
        first = inspect_run_diagnostics(
            self.target, "original-run", task_limit=4,
            task_count_scan_limit=100, timeout_seconds=10,
        )
        self.assertFalse(first.timed_out)
        self.assertFalse(first.task_count_complete)
        self.assertIsNone(first.task_count)
        self.assertEqual(first.task_count_lower_bound, 100)
        self.assertEqual(first.next_task_id, "task-00003")
        second = inspect_run_diagnostics(
            self.target, "original-run", after_task_id=first.next_task_id,
            task_limit=4, task_count_scan_limit=100, timeout_seconds=10,
        )
        self.assertEqual(second.tasks[0]["task_id"], "task-00004")
        self.assertEqual(second.next_task_id, "task-00007")


if __name__ == "__main__":
    unittest.main()
