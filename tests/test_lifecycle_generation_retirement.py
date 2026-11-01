"""Lifecycle retirement rejects stale producers and collects bounded batches."""
import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dispatcher_sdk.execution_kernel import SQLiteKernel, LifecycleReceiptExpiredError
from test_execution_kernel_v2_sqlite import make_command
from dispatcher_sdk.execution_kernel._sqlite_schema import (KERNEL_SCHEMA_V11, _schema_statement_for, upgrade_kernel_schema_v11_to_v12)


class RetirementTests(unittest.TestCase):
    def test_v11_pending_uses_original_receiver_id_after_upgrade(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'kernel.sqlite'
            k = SQLiteKernel(path)
            k.submit(make_command('job'))
            k.lifecycle_reserve('job', 0, 0, 'old-token', slots=1)
            seq = k.lifecycle_append('old-token', 'legacy-id', 'phase', {})
            k.close()
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute('DROP TABLE kernel_lifecycle_retired')
                db.execute('DROP TABLE kernel_lifecycle_metadata')
                db.execute('DROP TABLE kernel_schema_meta')
                db.execute(_schema_statement_for('kernel_schema_meta', KERNEL_SCHEMA_V11))
                db.execute("INSERT INTO kernel_schema_meta VALUES('execution_kernel',11)")
            with contextlib.closing(sqlite3.connect(path, isolation_level=None)) as db, db:
                upgrade_kernel_schema_v11_to_v12(db)
            k = SQLiteKernel(path)
            event = k.lifecycle_peek()
            self.assertEqual((event['sequence'], event['receiver_note_id'], event['receiver_store_id']),
                             (seq, 'legacy-id', None))
            k.close()

    def test_quiescence_bounded_cleanup_and_stale_replay(self):
        with tempfile.TemporaryDirectory() as d:
            k = SQLiteKernel(Path(d) / 'kernel.sqlite')
            k.submit(make_command('job'))
            identity = ('job', 0, 0)
            k.lifecycle_reserve(*identity, 'token', slots=2)
            seq = k.lifecycle_append('token', 'event', 'phase', {'v': 1})
            with self.assertRaises(ValueError):
                k.lifecycle_retire_generation(*identity)
            k.lifecycle_ack(seq, 'event')
            with self.assertRaises(ValueError):
                k.lifecycle_retire_generation(*identity)
            k.lifecycle_finish('token')
            first = k.lifecycle_retire_generation(*identity, limit=1)
            self.assertEqual(first, {'events_deleted': 1, 'producers_deleted': 0, 'more': True})
            with self.assertRaises(LifecycleReceiptExpiredError):
                k.lifecycle_reserve(*identity, 'new-token', slots=1)
            self.assertEqual(k.lifecycle_retire_generation(*identity, limit=1),
                             {'events_deleted': 0, 'producers_deleted': 1, 'more': False})
            lease = k.claim_and_start('owner', registry_revision='registry-1', execution_id='job')
            new_identity = ('job', lease.attempt, lease.fence)
            k.lifecycle_reserve(*new_identity, 'token', slots=1)
            with self.assertRaises(ValueError):
                k.lifecycle_append('token', 'event', 'phase', {'v': 1})
            with self.assertRaises(ValueError):
                k.lifecycle_append('token', 'event', 'phase', {'v': 1}, identity=identity)
            with self.assertRaises(ValueError):
                k.lifecycle_finish('token', identity=identity)
            second = k.lifecycle_append('token', 'event', 'phase', {'v': 2}, identity=new_identity)
            self.assertGreater(second, seq)
            self.assertIsNotNone(k.lifecycle_peek()['receiver_store_id'])
            k.close()


if __name__ == '__main__':
    unittest.main()
