"""Failure facts for real observation SQLite transactions."""
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dispatcher_sdk.observability import ActivityRecorder, ObservationIdentity, ObservationJournal, ObservationOptions, StallPolicy
from dispatcher_sdk.execution_kernel.runtime import InProcessRuntime
from dispatcher_sdk.execution_kernel.children import _transient_control_error
from dispatcher_sdk.observability.supervision import StallSupervisor
from dispatcher_sdk.observability import journal as journal_module
from dispatcher_sdk.observability.journal import _ObservationWriteBudgetExceeded


class TransactionResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.journal = ObservationJournal(root / "obs.db", kernel_path=root / "kernel.db",
                                          source_id="test", options=ObservationOptions(write_timeout=.03))

    def test_locked_admission_keeps_sqlite_error_and_reports_no_write(self):
        with closing(sqlite3.connect(self.journal.path)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError) as caught:
                with self.journal._transaction():
                    self.fail("writer must not enter")
        error = caught.exception
        result = error.observation_transaction
        self.assertEqual((error.sqlite_errorcode, error.sqlite_errorname),
                         (result.sqlite_errorcode, result.sqlite_errorname))
        self.assertEqual(("admission", False, True, "not_applied", None),
                         (result.phase, result.transaction_entered, result.rollback_confirmed,
                          result.outcome, result.replay_safe))

    def test_public_watch_stall_propagates_transaction_failure(self):
        kernel = SimpleNamespace(get=lambda execution_id: SimpleNamespace(attempt=1, fence=1),
            supervision_status=lambda execution_id: {"execution_state": "running", "attempt": 1, "fence": 1})
        runtime = InProcessRuntime.__new__(InProcessRuntime)
        runtime.kernel = kernel
        runtime._stall_supervisor = StallSupervisor(self.journal, kernel)
        with closing(sqlite3.connect(self.journal.path)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError) as caught:
                runtime.watch_stall("execution", StallPolicy("policy"))
        result = caught.exception.observation_transaction
        self.assertEqual("stall.watch", result.operation)
        self.assertEqual(("admission", "not_applied", None),
                         (result.phase, result.outcome, result.replay_safe))
        with closing(sqlite3.connect(self.journal.path)) as reader:
            self.assertEqual(0, reader.execute("SELECT COUNT(*) FROM obs_policies").fetchone()[0])

    def test_batch_connection_failure_identifies_operation_without_a_write(self):
        failure = sqlite3.OperationalError("connection unavailable")
        with patch.object(journal_module.sqlite3, "connect", side_effect=failure):
            with self.assertRaises(sqlite3.OperationalError) as caught:
                with self.journal._batch_connection(time.monotonic() + 1):
                    self.fail("connection should not open")
        self.assertIs(caught.exception, failure)
        result = failure.observation_transaction
        self.assertEqual((result.operation, result.phase, result.outcome),
                         ("write_batch", "connection", "not_applied"))

    def test_sql_error_after_write_is_rolled_back_and_preserved(self):
        with self.assertRaises(sqlite3.OperationalError) as caught:
            with self.journal._transaction() as (connection, now):
                connection.execute("INSERT INTO obs_current VALUES(?,?,?,?,?)", ("x", 1, 1, "{}", now))
                connection.execute("SELECT * FROM missing_observation_table")
        result = caught.exception.observation_transaction
        self.assertEqual(("body", True, True, "not_applied"),
                         (result.phase, result.transaction_entered, result.rollback_confirmed, result.outcome))
        self.assertEqual(caught.exception.sqlite_errorname, result.sqlite_errorname)
        with closing(sqlite3.connect(self.journal.path)) as reader:
            self.assertEqual(0, reader.execute("SELECT COUNT(*) FROM obs_current").fetchone()[0])

    def test_failed_rollback_does_not_replace_original_error(self):
        class BrokenRollback(sqlite3.Connection):
            def rollback(self):
                raise RuntimeError("rollback failed")

        with closing(sqlite3.connect(self.journal.path, factory=BrokenRollback)) as connection:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                with self.journal._transaction(_connection=connection) as (writer, now):
                    writer.execute("INSERT INTO obs_current VALUES(?,?,?,?,?)", ("x", 1, 1, "{}", now))
                    writer.execute("SELECT * FROM missing_observation_table")
            result = caught.exception.observation_transaction
            self.assertIsInstance(result.rollback_error, RuntimeError)
            self.assertFalse(result.rollback_confirmed)
            self.assertEqual("unknown", result.outcome)
            self.assertTrue(connection.in_transaction)

    def test_sqlite_automatic_rollback_without_receipt_is_unknown(self):
        with self.assertRaises(sqlite3.IntegrityError) as caught:
            with self.journal._transaction() as (connection, now):
                connection.execute("INSERT INTO obs_current VALUES(?,?,?,?,?)", ("x", 1, 1, "{}", now))
                connection.execute("INSERT OR ROLLBACK INTO obs_current VALUES(?,?,?,?,?)", ("x", 1, 1, "{}", now))
        result = caught.exception.observation_transaction
        self.assertEqual((True, False, "unknown"),
                         (result.transaction_entered, result.rollback_confirmed, result.outcome))
        with closing(sqlite3.connect(self.journal.path)) as reader:
            self.assertEqual(0, reader.execute("SELECT COUNT(*) FROM obs_current").fetchone()[0])

    def test_sqlite_interrupt_preserves_code_and_transaction_facts(self):
        with self.assertRaises(sqlite3.OperationalError) as caught:
            with self.journal._transaction() as (connection, now):
                connection.execute("INSERT INTO obs_current VALUES(?,?,?,?,?)", ("x", 1, 1, "{}", now))
                connection.set_progress_handler(lambda: 1, 1)
                connection.execute("SELECT count(*) FROM obs_current").fetchone()
        result = caught.exception.observation_transaction
        self.assertEqual(sqlite3.SQLITE_INTERRUPT, result.sqlite_errorcode)
        self.assertEqual("SQLITE_INTERRUPT", result.sqlite_errorname)
        self.assertEqual(("body", True), (result.phase, result.transaction_entered))
        self.assertIn(result.outcome, ("not_applied", "unknown"))
        self.assertEqual(result.outcome == "not_applied", result.rollback_confirmed)
        self.assertIsNone(result.replay_safe)
        with closing(sqlite3.connect(self.journal.path)) as reader:
            self.assertEqual(0, reader.execute("SELECT COUNT(*) FROM obs_current").fetchone()[0])

    def test_commit_that_succeeds_then_raises_has_unknown_outcome(self):
        class LostCommitReceipt(sqlite3.Connection):
            def commit(self):
                super().commit()
                raise sqlite3.OperationalError("commit response lost")

        with closing(sqlite3.connect(self.journal.path, factory=LostCommitReceipt)) as connection:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                with self.journal._transaction(_connection=connection) as (writer, now):
                    writer.execute("INSERT INTO obs_current VALUES(?,?,?,?,?)", ("x", 1, 1, "{}", now))
            result = caught.exception.observation_transaction
            self.assertEqual(("commit", False, "unknown", None),
                             (result.phase, result.rollback_confirmed, result.outcome, result.replay_safe))
        with closing(sqlite3.connect(self.journal.path)) as reader:
            self.assertEqual(1, reader.execute("SELECT COUNT(*) FROM obs_current").fetchone()[0])

    def test_unknown_contention_is_not_retried_by_recorder_or_child_control(self):
        class LostCommitReceipt(sqlite3.Connection):
            def commit(self):
                super().commit()
                raise sqlite3.OperationalError("database is locked")

        with closing(sqlite3.connect(self.journal.path, factory=LostCommitReceipt)) as connection:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                with self.journal._transaction(_connection=connection):
                    pass
        error = caught.exception
        self.assertFalse(ActivityRecorder._transient_storage_error(error))
        self.assertFalse(_transient_control_error(error))
        recorder = ActivityRecorder(self.journal, ObservationIdentity("x", 1, 1))
        with patch.object(self.journal, "write_batch", side_effect=error) as write:
            self.assertFalse(recorder.flush()["retryable"])
            self.assertEqual("write_outcome_unknown", recorder.flush()["reason"])
            self.assertEqual(1, write.call_count)

    def test_batch_close_failure_after_commit_is_applied_and_not_retried(self):
        class BrokenClose(sqlite3.Connection):
            def close(self):
                super().close()
                raise sqlite3.OperationalError("database is locked")

        original_connect = sqlite3.connect
        proxy = SimpleNamespace(**{**vars(sqlite3), "connect":
            lambda *args, **kwargs: original_connect(*args, factory=BrokenClose, **kwargs)})
        recorder = ActivityRecorder(self.journal, ObservationIdentity("x", 1, 1))
        original_write = self.journal.write_batch
        errors = []
        def capture(*args, **kwargs):
            try:
                return original_write(*args, **kwargs)
            except sqlite3.OperationalError as error:
                errors.append(error)
                raise
        with patch.object(journal_module, "sqlite3", proxy), patch.object(self.journal, "write_batch", side_effect=capture):
            first = recorder.flush()
            second = recorder.flush()
        self.assertEqual("applied", errors[0].observation_transaction.outcome)
        self.assertEqual(1, len(errors))
        self.assertFalse(first["retryable"])
        self.assertEqual("write_outcome_unknown", second["reason"])
        with closing(sqlite3.connect(self.journal.path)) as reader:
            self.assertEqual(1, reader.execute("SELECT COUNT(*) FROM obs_sources").fetchone()[0])

    def test_batch_rollback_failure_preserves_budget_error_and_cleanup_details(self):
        class BrokenRollback(sqlite3.Connection):
            def rollback(self):
                raise RuntimeError("rollback failed")
            def close(self):
                super().close()
                raise RuntimeError("close failed")

        original_connect = sqlite3.connect
        proxy = SimpleNamespace(**{**vars(sqlite3), "connect":
            lambda *args, **kwargs: original_connect(*args, factory=BrokenRollback, **kwargs)})
        expired = _ObservationWriteBudgetExceeded("original budget error")
        with patch.object(journal_module, "sqlite3", proxy), patch.object(
                self.journal, "_validate_binding", side_effect=expired):
            with self.assertRaises(_ObservationWriteBudgetExceeded) as caught:
                self.journal.write_batch(ObservationIdentity("x", 1, 1), source_id="s", sequence=1,
                                         metrics={}, captured_at=time.time())
        self.assertIs(caught.exception, expired)
        self.assertFalse(expired.rollback_confirmed)
        self.assertEqual(["rollback failed", "close failed"],
                         [str(error) for error in expired.observation_cleanup_errors])
        self.assertEqual("unknown", expired.observation_transaction.outcome)

    def test_batch_cleanup_preserves_original_if_total_changes_unavailable(self):
        class BrokenCleanup(sqlite3.Connection):
            @property
            def total_changes(self):
                raise RuntimeError("accounting failed")
            def close(self):
                super().close()
                raise RuntimeError("close failed")

        original_connect = sqlite3.connect
        proxy = SimpleNamespace(**{**vars(sqlite3), "connect":
            lambda *args, **kwargs: original_connect(*args, factory=BrokenCleanup, **kwargs)})
        with patch.object(journal_module, "sqlite3", proxy):
            with self.assertRaisesRegex(RuntimeError, "accounting failed") as caught:
                with self.journal._batch_connection(time.monotonic() + 1):
                    pass
        self.assertEqual("close failed", str(caught.exception.observation_cleanup_errors[0]))
        self.assertEqual("unknown", caught.exception.observation_transaction.outcome)


if __name__ == "__main__":
    unittest.main()
