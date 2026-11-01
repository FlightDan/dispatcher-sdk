from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dispatcher_sdk.execution_kernel._sqlite_schema import KERNEL_SCHEMA_V5
from dispatcher_sdk.maintenance import maintenance_lease
from dispatcher_sdk.storage_migration import StorageMigrationError, upgrade_storage


class MigrationForeignKeyTests(unittest.TestCase):
    def test_existing_destination_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite3"
            destination = Path(directory) / "copy.sqlite3"
            with closing(sqlite3.connect(source)) as db:
                db.executescript(KERNEL_SCHEMA_V5)
            destination.write_text("existing file", encoding="utf-8")
            with maintenance_lease(source, "test", "copy-upgrade") as lease:
                with self.assertRaises(FileExistsError):
                    upgrade_storage(source, destination, lease=lease)
            self.assertEqual(destination.read_text(encoding="utf-8"), "existing file")

    def test_orphan_membership_rejects_copy_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite3"
            destination = Path(directory) / "copy.sqlite3"
            with closing(sqlite3.connect(source)) as db:
                db.executescript(KERNEL_SCHEMA_V5)
                db.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                           ("sdk-managed:orphan", "missing-run", 3, 0))
                db.commit()
                original = db.execute("SELECT * FROM kernel_managed_executions").fetchall()
            with maintenance_lease(source, "test", "copy-upgrade") as lease:
                with self.assertRaisesRegex(StorageMigrationError, "foreign key violation"):
                    upgrade_storage(source, destination, lease=lease)
            self.assertFalse(destination.exists())
            with closing(sqlite3.connect(source)) as db:
                self.assertEqual(db.execute("SELECT schema_version FROM kernel_schema_meta").fetchone(), (5,))
                self.assertEqual(db.execute("SELECT * FROM kernel_managed_executions").fetchall(), original)

    def test_valid_membership_is_preserved_in_published_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite3"
            destination = Path(directory) / "copy.sqlite3"
            with closing(sqlite3.connect(source)) as db:
                db.executescript(KERNEL_SCHEMA_V5)
                db.execute("INSERT INTO kernel_run_controls VALUES(?,?,?,?,?,?,?)",
                           ("run", 1, 3, "paused", 4, 1, 500))
                db.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                           ("sdk-managed:valid", "run", 3, 1))
                db.commit()
            with maintenance_lease(source, "test", "copy-upgrade") as lease:
                upgrade_storage(source, destination, lease=lease)
            with closing(sqlite3.connect(destination)) as db:
                self.assertEqual(db.execute("SELECT * FROM kernel_managed_executions").fetchall(),
                                 [("sdk-managed:valid", "run", 3, 1)])
                self.assertEqual(db.execute("SELECT schema_version FROM kernel_schema_meta").fetchone(), (12,))


if __name__ == "__main__":
    unittest.main()
