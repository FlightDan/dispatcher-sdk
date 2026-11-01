"""Bounded legacy split-store mapping is read-only and preserves uncertainty."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel._sqlite_schema import KERNEL_SCHEMA_V5
from dispatcher_sdk.orchestrator.adoption_inspection import inspect_legacy_execution_page
from dispatcher_sdk.orchestrator.notifications import NotificationsMixin
from dispatcher_sdk.orchestrator.results import ResultsMixin
from dispatcher_sdk.orchestrator.store import SCHEMA_V4, execute_schema, initialize_storage_tracking


class LegacyExecutionInspectionTests(unittest.TestCase):
    def test_without_connection_setlimit(self):
        class LegacyConnection(sqlite3.Connection):
            def __getattribute__(self, name):
                if name == 'setlimit':
                    raise AttributeError(name)
                return super().__getattribute__(name)

        connect = sqlite3.connect
        def legacy_connect(*args, **kwargs):
            return connect(*args, factory=LegacyConnection, **kwargs)

        with patch('dispatcher_sdk.orchestrator.adoption_inspection.sqlite3.connect', side_effect=legacy_connect):
            self.test_split_store_paging_and_missing_kernel_fact()
            self.test_rejects_missing_cursor_index_and_oversized_row()
            self.test_unsupported_schema_marker_is_rejected()

    def test_split_store_paging_and_missing_kernel_fact(self):
        with tempfile.TemporaryDirectory() as directory:
            orchestration = Path(directory) / "orchestration.db"
            kernel = Path(directory) / "kernel.db"
            with closing(sqlite3.connect(orchestration)) as db:
                execute_schema(db, SCHEMA_V4)
                results = ResultsMixin()
                results.max_result_deliveries = 5
                results._init_results(db)
                NotificationsMixin._init_notifications(db)
                db.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',4)")
                db.execute("INSERT INTO sdk_storage_identity VALUES(1,'store','incarnation',1)")
                db.execute("INSERT INTO sdk_storage_clock VALUES(1,0)")
                initialize_storage_tracking(db)
                db.execute("INSERT INTO sdk_runs VALUES('legacy-run',3,'running')")
                db.executemany("INSERT INTO sdk_executions VALUES(?,?,?,?,?,?,?,?)", [
                    ("old-1", "legacy-run", "task-a", 0, 0, "{}", "key-1", 1),
                    ("old-2", "legacy-run", "task-b", 0, 0, "{}", "key-2", 1),
                ])
                db.commit()
            with closing(sqlite3.connect(kernel)) as db:
                db.executescript(KERNEL_SCHEMA_V5)
                db.execute("INSERT INTO kernel_executions(execution_id,idempotency_key,registry_revision,"
                           "command_json,state,attempt,redelivery_count,next_attempt_at,fence,revision,"
                           "created_at,updated_at) VALUES('old-1','key-1','registry','{}','queued',0,0,1,0,1,1,1)")
                db.commit()
            first = inspect_legacy_execution_page(orchestration, kernel, "legacy-run", limit=1)
            self.assertEqual(first["run"]["run_id"], "legacy-run")
            self.assertEqual(first["executions"][0]["kernel_observation"]["state"], "queued")
            self.assertEqual(first["adoption_eligibility"], "unknown")
            self.assertFalse(first["cross_store_snapshot"])
            self.assertEqual(first["kernel_association"], "execution_id_match_only")
            second = inspect_legacy_execution_page(orchestration, kernel, "legacy-run", limit=1,
                                                   **first["next_cursor"])
            self.assertEqual(second["executions"][0]["execution_id"], "old-2")
            self.assertEqual(second["executions"][0]["kernel_observation"]["status"], "not_observed")
            self.assertIsNone(second["next_cursor"])
            with closing(sqlite3.connect(orchestration)) as db:
                self.assertEqual(db.execute("SELECT revision FROM sdk_runs").fetchone(), (3,))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM sdk_executions").fetchone(), (2,))

    def test_rejects_missing_cursor_index_and_oversized_row(self):
        with tempfile.TemporaryDirectory() as directory:
            orchestration = Path(directory) / "orchestration.db"
            kernel = Path(directory) / "kernel.db"
            with closing(sqlite3.connect(orchestration)) as db:
                db.executescript("""
                    CREATE TABLE sdk_schema_meta(component TEXT, version INTEGER);
                    INSERT INTO sdk_schema_meta VALUES('orchestrator',4);
                    CREATE TABLE sdk_runs(run_id TEXT, revision INTEGER, state TEXT);
                    INSERT INTO sdk_runs VALUES('run',1,'running');
                    CREATE TABLE sdk_executions(execution_id TEXT, run_id TEXT,
                        task_id TEXT, attempt INTEGER, generation INTEGER, active INTEGER);
                    INSERT INTO sdk_executions VALUES('one','run','task',0,0,1);
                """)
                db.commit()
            with closing(sqlite3.connect(kernel)) as db:
                db.executescript("""
                    CREATE TABLE kernel_schema_meta(component TEXT, schema_version INTEGER);
                    INSERT INTO kernel_schema_meta VALUES('execution_kernel',5);
                    CREATE TABLE kernel_executions(execution_id TEXT, state TEXT, attempt INTEGER, fence INTEGER);
                """)
                db.commit()
            with self.assertRaisesRegex(ValueError, "cursor index"):
                inspect_legacy_execution_page(orchestration, kernel, "run")
            with closing(sqlite3.connect(orchestration)) as db:
                db.execute("CREATE UNIQUE INDEX cursor_key ON sdk_executions(run_id,task_id,attempt)")
                db.execute("UPDATE sdk_executions SET execution_id=?", ("x" * 70000,))
                db.commit()
            with self.assertRaises(sqlite3.DataError):
                inspect_legacy_execution_page(orchestration, kernel, "run")

    def test_unsupported_schema_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            orchestration = Path(directory) / "orchestration.db"
            kernel = Path(directory) / "kernel.db"
            with closing(sqlite3.connect(orchestration)) as db:
                db.executescript("CREATE TABLE sdk_schema_meta(component TEXT, version INTEGER);"
                                 "INSERT INTO sdk_schema_meta VALUES('orchestrator',99);")
            with closing(sqlite3.connect(kernel)) as db:
                db.executescript("CREATE TABLE kernel_schema_meta(component TEXT, schema_version INTEGER);"
                                 "INSERT INTO kernel_schema_meta VALUES('execution_kernel',5);")
            with self.assertRaisesRegex(ValueError, "unsupported Orchestrator"):
                inspect_legacy_execution_page(orchestration, kernel, "run")

    def test_missing_paths_are_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.db"
            with self.assertRaises(sqlite3.OperationalError):
                inspect_legacy_execution_page(missing, missing, "run")
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
