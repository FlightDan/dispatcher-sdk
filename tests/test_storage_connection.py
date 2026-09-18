"""Connection lifetime and permanent identity safety regressions."""
from contextlib import closing
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from dispatcher_sdk.maintenance import MaintenanceBusyError, maintenance_lease
from dispatcher_sdk.storage_connection import connect
from dispatcher_sdk.orchestrator import Operations, Orchestrator, RunDisposed


class StorageConnectionTests(unittest.TestCase):
    def test_unsupported_factory_is_rejected_before_opening_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "store.db"
            with self.assertRaises(TypeError):
                connect(path, factory=sqlite3.Connection)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_failed_cross_thread_close_keeps_participation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "store.db"
            connection = connect(path)
            failures = []

            def close_elsewhere():
                try:
                    connection.close()
                except sqlite3.ProgrammingError as error:
                    failures.append(error)

            worker = threading.Thread(target=close_elsewhere)
            worker.start()
            worker.join(timeout=5)
            self.assertEqual(len(failures), 1)
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
            with self.assertRaises(MaintenanceBusyError):
                with maintenance_lease(path, "test", "blocked"):
                    self.fail("live connection lost its lock")
            connection.close()
            with maintenance_lease(path, "test", "closed") as lease:
                lease.check(path)

    def test_dangling_snapshot_marker_blocks_sdk_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".sdk-snapshot-readonly").symlink_to(root / "absent")
            with self.assertRaises(PermissionError):
                connect(root / "store.db")
            self.assertFalse((root / "store.db").exists())

    def test_continuation_rejects_permanently_disposed_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "store.db"
            with Orchestrator.open_sqlite(path, {}) as sdk:
                sdk.create_run("previous", command_id="create")
                sdk.apply_operations("previous", command_id="finish", expected_revision=0,
                                     operations=[Operations.finish("succeeded")])
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute("INSERT INTO sdk_disposed_runs VALUES(?,?,?)",
                                       ("disposed", "{}", "test"))
                with self.assertRaises(RunDisposed):
                    sdk.continue_run("previous", "disposed", command_id="continue",
                                     expected_revision=1)
                self.assertIsNone(sdk.get_run_summary("previous")["next_run_id"])
