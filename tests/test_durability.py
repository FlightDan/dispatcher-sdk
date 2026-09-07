"""Real SQLite coverage for shared durability configuration."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.durability import configure_sqlite_connection, validate_durability
from dispatcher_sdk.execution_kernel import SQLiteKernel
from dispatcher_sdk.execution_kernel import _sqlite_base


class DurabilityTests(unittest.TestCase):
    def test_profiles_apply_to_every_connection_and_preserve_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.db"
            with closing(sqlite3.connect(path)) as first:
                configure_sqlite_connection(first, path)
                first.execute("CREATE TABLE application_data(value TEXT)")
                first.execute("INSERT INTO application_data VALUES ('preserved')")
                first.commit()
                for filename in (path, Path(directory) / "independent.db"):
                    with closing(sqlite3.connect(filename)) as second:
                        configure_sqlite_connection(second, filename, durability="normal")
                        self.assertEqual(second.execute("PRAGMA synchronous").fetchone()[0], 1)
                        self.assertEqual(second.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                        self.assertEqual(second.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
                        configure_sqlite_connection(second, filename)
                        self.assertEqual(second.execute("PRAGMA synchronous").fetchone()[0], 2)
                self.assertEqual(first.execute("PRAGMA synchronous").fetchone()[0], 2)
            with closing(sqlite3.connect(path)) as reopened:
                configure_sqlite_connection(reopened, path)
                self.assertEqual(reopened.execute("SELECT value FROM application_data").fetchone()[0], "preserved")

    def test_memory_retains_its_nonpersistent_journal(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            configure_sqlite_connection(connection, ":memory:")
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "memory")
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)

    def test_invalid_profiles_fail_before_opening_kernel_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent.db"
            for value in (None, True, 1, "FULL", "off", "", [], {}):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    validate_durability(value)
                with self.subTest(kernel=value), self.assertRaises(ValueError):
                    SQLiteKernel(path, durability=value)
            self.assertFalse(path.exists())

    def test_file_profile_rejects_refused_wal(self):
        # An actual in-memory connection cannot enable WAL. A file-backed
        # request must reject it instead of accepting the returned mode.
        with closing(sqlite3.connect(":memory:")) as connection:
            with self.assertRaisesRegex(RuntimeError, "refused wal"):
                configure_sqlite_connection(connection, "expected-file.db")

    def test_refused_synchronous_is_detected_by_readback(self):
        class RefusingConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "PRAGMA synchronous = 2":
                    return super().execute("PRAGMA synchronous = 1")
                return super().execute(sql, parameters)

        with closing(sqlite3.connect(":memory:", factory=RefusingConnection)) as connection:
            with self.assertRaisesRegex(RuntimeError, "refused synchronous"):
                configure_sqlite_connection(connection, ":memory:")

    def test_transaction_rejected_without_committing_application_changes(self):
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE TABLE app(value INTEGER)")
            connection.execute("INSERT INTO app VALUES (1)")
            with self.assertRaisesRegex(ValueError, "outside a transaction"):
                configure_sqlite_connection(connection, ":memory:")
            self.assertTrue(connection.in_transaction)
            connection.rollback()
            self.assertEqual(connection.execute("SELECT count(*) FROM app").fetchone()[0], 0)

    def test_kernel_configures_each_profile_before_installing_authorizer(self):
        observed = []

        def configure(connection, path, *, durability="full"):
            configure_sqlite_connection(connection, path, durability=durability)
            observed.append(connection.execute("PRAGMA synchronous").fetchone()[0])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.db"
            for profile in ("full", "normal", "full"):
                with patch.object(_sqlite_base, "configure_sqlite_connection", side_effect=configure):
                    with SQLiteKernel(path, durability=profile) as kernel:
                        self.assertEqual(kernel.durability, profile)
                        with self.assertRaises(sqlite3.DatabaseError):
                            kernel._connection.execute("PRAGMA synchronous = OFF")
            self.assertEqual(observed, [2, 1, 2])


if __name__ == "__main__":
    unittest.main()
