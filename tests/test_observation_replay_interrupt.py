"""Real SQLite replay interruption and late read-only close diagnostics."""
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dispatcher_sdk.observability import ObservationIdentity, ObservationJournal, ObservationOptions
from dispatcher_sdk.observability import journal as journal_module
from dispatcher_sdk.observability.journal import _ObservationWriteBudgetExceeded


class ObservationReplayInterruptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.journal = ObservationJournal(root / 'observation.sqlite', kernel_path=root / 'kernel.sqlite',
            source_id='source', options=ObservationOptions(write_timeout=.05))
        self.identity = ObservationIdentity('execution', 1, 1)

    def write(self):
        return self.journal.write_batch(self.identity, source_id='collector', sequence=1,
                                        metrics={}, captured_at=1.0)

    def test_real_replay_sqlite_interrupt_keeps_cause_and_rollback(self):
        rolled_back = []
        class TrackedConnection(sqlite3.Connection):
            def rollback(self):
                entered = self.in_transaction
                super().rollback()
                rolled_back.append((entered, self.in_transaction))
        original_connect = sqlite3.connect
        proxy = SimpleNamespace(**{**vars(sqlite3), 'connect': lambda *args, **kwargs:
                                    original_connect(*args, factory=TrackedConnection, **kwargs)})
        def interrupted_read(connection):
            def interrupt():
                time.sleep(.06)
                return 1
            connection.set_progress_handler(interrupt, 1)
            connection.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000) '
                               'SELECT sum(x) FROM n').fetchone()
        with patch.object(journal_module, 'sqlite3', proxy), patch.object(self.journal, '_validate_binding', interrupted_read):
            with self.assertRaises(_ObservationWriteBudgetExceeded) as caught:
                self.write()
        error = caught.exception
        self.assertIsInstance(error.__cause__, sqlite3.OperationalError)
        self.assertEqual((error.__cause__.sqlite_errorcode, error.__cause__.sqlite_errorname),
                         (sqlite3.SQLITE_INTERRUPT, 'SQLITE_INTERRUPT'))
        result = error.observation_transaction
        self.assertEqual((result.operation, result.phase, result.sqlite_errorcode, result.sqlite_errorname),
                         ('write_batch', 'replay_read', sqlite3.SQLITE_INTERRUPT, 'SQLITE_INTERRUPT'))
        self.assertEqual((result.transaction_entered, result.rollback_confirmed, result.outcome),
                         (False, True, 'not_applied'))
        self.assertIn((True, False), rolled_back)
        with sqlite3.connect(self.journal.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM obs_sources').fetchone()[0], 0)

    def test_replayed_read_close_after_deadline_reports_not_applied(self):
        self.assertTrue(self.write())
        class SlowClose(sqlite3.Connection):
            def close(self):
                time.sleep(.06)
                return super().close()
        original_connect = sqlite3.connect
        proxy = SimpleNamespace(**{**vars(sqlite3), 'connect': lambda *args, **kwargs:
                                    original_connect(*args, factory=SlowClose, **kwargs)})
        with patch.object(journal_module, 'sqlite3', proxy):
            with self.assertRaises(_ObservationWriteBudgetExceeded) as caught:
                self.write()
        result = caught.exception.observation_transaction
        self.assertEqual((result.operation, result.phase, result.sqlite_errorcode, result.sqlite_errorname),
                         ('write_batch', 'close', None, None))
        self.assertEqual((result.transaction_entered, result.rollback_confirmed, result.outcome),
                         (False, True, 'not_applied'))
        with sqlite3.connect(self.journal.path) as db:
            self.assertEqual(db.execute('SELECT sequence FROM obs_sources').fetchone()[0], 1)
