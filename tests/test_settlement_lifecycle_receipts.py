"""Lifecycle receipts use a durable namespace independent of arbitrary note IDs."""
import contextlib
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import SQLiteKernel
from dispatcher_sdk.execution_kernel._sqlite_schema import KERNEL_SCHEMA_V11, _schema_statement_for, upgrade_kernel_schema_v11_to_v12
from test_execution_kernel_v2_sqlite import make_command
from dispatcher_sdk.execution_kernel.settlement import (
    SettlementBindingError, SettlementBusyError, SettlementConflictError, SettlementJournal, _SCHEMA,
)


class LifecycleReceiptTests(unittest.TestCase):
    def test_multibyte_phase_matches_kernel_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel'
            kernel = SQLiteKernel(path)
            kernel.submit(make_command('job'))
            store = kernel.kernel_store_identity()
            journal = SettlementJournal(Path(directory) / 'journal', source_id='source', kernel_path=path)
            identity = {'execution_id': 'job', 'attempt': 0, 'fence': 0}
            kernel.lifecycle_reserve('job', 0, 0, 'producer', slots=1)
            phase = '界' * 256
            sequence = kernel.lifecycle_append('producer', 'event', phase, {'ok': True})
            receipt = journal.lifecycle_note(identity, phase, {'ok': True}, store_id=store,
                                             outbox_sequence=sequence)
            self.assertEqual(receipt['phase'], phase)
            self.assertTrue(journal.lifecycle_receipt_committed(identity, phase, {'ok': True},
                store_id=store, outbox_sequence=sequence))
            with self.assertRaises(ValueError):
                journal.lifecycle_note(identity, phase + '界', {'ok': True}, store_id=store,
                                       outbox_sequence=sequence)
            kernel.close()

    def test_unavailable_kernel_proof_fails_closed_and_releases_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel'
            kernel = SQLiteKernel(path)
            store = kernel.kernel_store_identity()
            kernel.close()
            journal = SettlementJournal(Path(directory) / 'journal', source_id='source', kernel_path=path)
            with contextlib.closing(sqlite3.connect(path, isolation_level=None, timeout=0)) as locked, locked:
                locked.execute('PRAGMA journal_mode=DELETE')
                locked.execute('BEGIN EXCLUSIVE')
                with self.assertRaises(SettlementBusyError):
                    journal.lifecycle_note({'execution_id': 'job', 'attempt': 0, 'fence': 0},
                        'phase', {}, store_id=store, outbox_sequence=1, timeout_seconds=1)
                with journal._connection(1, write=True):
                    pass
                locked.rollback()

    def test_existing_identical_note_id_cannot_fake_lifecycle_receipt(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteKernel(Path(directory) / 'kernel') as kernel:
            store = kernel.kernel_store_identity()
            journal = SettlementJournal(Path(directory) / 'journal', source_id='source', kernel_path=Path(directory) / 'kernel')
            identity = {'execution_id': 'job', 'attempt': 0, 'fence': 0}
            kernel.submit(make_command('job'))
            kernel.lifecycle_reserve('job', 0, 0, 'p', slots=1)
            kernel.lifecycle_append('p', 'event', 'phase', {'x': 1})
            journal.note(identity, 'phase', {'x': 1}, note_id='collision')
            with patch('dispatcher_sdk.execution_kernel.settlement.uuid4', side_effect=['collision', 'new-id']):
                first = journal.lifecycle_note(identity, 'phase', {'x': 1}, store_id=store, outbox_sequence=1)
            self.assertEqual(first['note_id'], 'new-id')
            self.assertTrue(journal.lifecycle_receipt_committed(identity, 'phase', {'x': 1},
                store_id=store, outbox_sequence=1))
            self.assertFalse(journal.lifecycle_receipt_committed(identity, 'phase', {'x': 1},
                store_id=store, outbox_sequence=2))
            self.assertFalse(journal.lifecycle_receipt_committed(identity, 'phase', {'x': 2},
                store_id=store, outbox_sequence=1))
            self.assertEqual(journal.lifecycle_note(identity, 'phase', {'x': 1}, store_id=store, outbox_sequence=1), first)
            with self.assertRaises(SettlementConflictError):
                journal.lifecycle_note(identity, 'phase', {'x': 2}, store_id=store, outbox_sequence=1)
            self.assertEqual(len(journal.inspect_notes('job')['notes']), 2)

    def test_retired_pruning_and_late_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel'
            kernel = SQLiteKernel(path)
            kernel.submit(make_command('job'))
            store = kernel.kernel_store_identity()
            journal = SettlementJournal(Path(directory) / 'journal', source_id='source', kernel_path=path)
            identity = {'execution_id': 'job', 'attempt': 0, 'fence': 0}
            kernel.lifecycle_reserve('job', 0, 0, 'p', slots=2)
            kernel.lifecycle_append('p', 'e1', 'phase', {'x': 1})
            kernel.lifecycle_append('p', 'e2', 'phase', {'x': 2})
            journal.note(identity, 'legacy', {'keep': True}, note_id='legacy')
            journal.lifecycle_note(identity, 'phase', {'x': 1}, store_id=store, outbox_sequence=1)
            journal.lifecycle_note(identity, 'phase', {'x': 2}, store_id=store, outbox_sequence=2)
            with self.assertRaises(SettlementConflictError):
                journal.lifecycle_note({'execution_id': 'forged', 'attempt': 0, 'fence': 0}, 'phase', {'x': 1}, store_id=store, outbox_sequence=1)
            with self.assertRaises(SettlementConflictError):
                journal.prune_lifecycle_notes('job', 0, 0, store_id=store)
            kernel.lifecycle_ack(1, 'e1')
            kernel.lifecycle_ack(2, 'e2')
            kernel.lifecycle_finish('p')
            kernel.lifecycle_retire_generation('job', 0, 0)
            self.assertEqual(journal.prune_lifecycle_notes('job', 0, 0, store_id=store, limit=1), {'pruned': 1, 'more': True})
            with self.assertRaises(SettlementConflictError):
                journal.lifecycle_note(identity, 'phase', {'x': 1}, store_id=store, outbox_sequence=1)
            self.assertEqual(journal.prune_lifecycle_notes('job', 0, 0, store_id=store), {'pruned': 1, 'more': False})
            with self.assertRaises(SettlementConflictError):
                journal.lifecycle_note({'execution_id': 'forged', 'attempt': 1, 'fence': 1}, 'phase', {'x': 1}, store_id=store, outbox_sequence=1)
            self.assertEqual([n['note_id'] for n in journal.inspect_notes('job')['notes']], ['legacy'])
            kernel.close()

    def test_legacy_committed_note_with_lost_ack_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel'
            kernel = SQLiteKernel(path)
            kernel.submit(make_command('job'))
            store = kernel.kernel_store_identity()
            kernel.lifecycle_reserve('job', 0, 0, 'p', slots=2)
            sequence = kernel.lifecycle_append('p', 'legacy-id', 'phase', {'v': 1})
            second = kernel.lifecycle_append('p', 'fresh-legacy-id', 'phase', {'v': 2})
            kernel.close()
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute('DROP TABLE kernel_lifecycle_retired')
                db.execute('DROP TABLE kernel_lifecycle_metadata')
                db.execute('DROP TABLE kernel_schema_meta')
                db.execute(_schema_statement_for('kernel_schema_meta', KERNEL_SCHEMA_V11))
                db.execute("INSERT INTO kernel_schema_meta VALUES('execution_kernel',11)")
            journal = SettlementJournal(Path(directory) / 'journal', source_id='source', kernel_path=path)
            identity = {'execution_id': 'job', 'attempt': 0, 'fence': 0}
            legacy = journal.note(identity, 'phase', {'v': 1}, note_id='legacy-id')
            with contextlib.closing(sqlite3.connect(path, isolation_level=None)) as db, db:
                upgrade_kernel_schema_v11_to_v12(db)
            with self.assertRaises(SettlementConflictError):
                journal.lifecycle_note(identity, 'phase', {'v': 1}, store_id=store,
                                       outbox_sequence=sequence, legacy_note_id='legacy-id')
            with self.assertRaises(SettlementConflictError):
                journal.lifecycle_note(identity, 'phase', {'v': 1}, store_id=store, outbox_sequence=sequence)
            claim_values = []
            def attest(credential, claim):
                claim_values.append(claim)
                return credential == 'authorized' and claim['settlement_note_sequence'] == legacy['sequence']
            with self.assertRaises(SettlementBindingError):
                journal.reconcile_legacy_lifecycle_receipt(identity, 'phase', {'v': 1},
                    store_id=store, outbox_sequence=sequence, legacy_note_id='legacy-id',
                    note_sequence=legacy['sequence'], credential='denied', verify_host=attest)
            self.assertFalse(journal.lifecycle_receipt_committed(identity, 'phase', {'v': 1},
                store_id=store, outbox_sequence=sequence))
            with self.assertRaises(SettlementConflictError):
                journal.reconcile_legacy_lifecycle_receipt(identity, 'phase', {'v': 2},
                    store_id=store, outbox_sequence=sequence, legacy_note_id='legacy-id',
                    note_sequence=legacy['sequence'], credential='authorized', verify_host=attest)
            self.assertEqual(journal.reconcile_legacy_lifecycle_receipt(identity, 'phase', {'v': 1},
                store_id=store, outbox_sequence=sequence, legacy_note_id='legacy-id',
                note_sequence=legacy['sequence'], credential='authorized', verify_host=attest), legacy)
            self.assertTrue(journal.lifecycle_receipt_committed(identity, 'phase', {'v': 1},
                store_id=store, outbox_sequence=sequence))
            self.assertEqual(journal.lifecycle_note(identity, 'phase', {'v': 1}, store_id=store,
                outbox_sequence=sequence, legacy_note_id='legacy-id'), legacy)
            self.assertEqual(claim_values[-1]['event_id'], 'legacy-id')
            self.assertEqual(claim_values[-1]['kernel_path'], str(path.resolve()))
            self.assertEqual(claim_values[-1]['settlement_path'], str((Path(directory) / 'journal').resolve()))
            fresh = journal.lifecycle_note(identity, 'phase', {'v': 2}, store_id=store,
                                           outbox_sequence=second, legacy_note_id='fresh-legacy-id')
            self.assertEqual(journal.lifecycle_note(identity, 'phase', {'v': 2}, store_id=store,
                                                    outbox_sequence=second, legacy_note_id='fresh-legacy-id'), fresh)
            kernel = SQLiteKernel(path)
            self.assertEqual(kernel.lifecycle_peek()['event_id'], 'legacy-id')
            self.assertEqual([n['note_id'] for n in journal.inspect_notes('job')['notes']], ['legacy-id', 'fresh-legacy-id'])
            kernel.close()

    def test_inflight_receiver_cannot_recreate_pruned_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel'
            kernel = SQLiteKernel(path)
            kernel.submit(make_command('job'))
            store = kernel.kernel_store_identity()
            journal = SettlementJournal(Path(directory) / 'journal', source_id='source', kernel_path=path)
            identity = {'execution_id': 'job', 'attempt': 0, 'fence': 0}
            kernel.lifecycle_reserve('job', 0, 0, 'p', slots=1)
            kernel.lifecycle_append('p', 'event', 'phase', {})
            journal.lifecycle_note(identity, 'phase', {}, store_id=store, outbox_sequence=1)
            kernel.lifecycle_ack(1, 'event')
            kernel.lifecycle_finish('p')
            checked, release, outcomes = threading.Event(), threading.Event(), []
            original = journal._kernel_retired_watermark
            def gated(*args, **kwargs):
                result = original(*args, **kwargs)
                checked.set()
                self.assertTrue(release.wait(3))
                return result
            def receive():
                try:
                    outcomes.append(journal.lifecycle_note(identity, 'phase', {}, store_id=store, outbox_sequence=1, timeout_seconds=3))
                except Exception as error:
                    outcomes.append(error)
            with patch.object(journal, '_kernel_retired_watermark', side_effect=gated):
                worker = threading.Thread(target=receive)
                worker.start()
                self.assertTrue(checked.wait(3))
                retirement = []
                retire_entered = threading.Event()
                def retire():
                    try:
                        retire_entered.set()
                        retirement.append(kernel.lifecycle_retire_generation('job', 0, 0))
                    except Exception as error:
                        retirement.append(error)
                retire_worker = threading.Thread(target=retire)
                retire_worker.start()
                try:
                    self.assertTrue(retire_entered.wait(1))
                    time.sleep(.05)
                    self.assertTrue(retire_worker.is_alive(), 'retirement overtook in-flight receipt')
                finally:
                    release.set()
                worker.join(3)
                retire_worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(retire_worker.is_alive())
            self.assertIsInstance(outcomes[0], dict)
            self.assertIsInstance(retirement[0], dict)
            self.assertEqual(journal.prune_lifecycle_notes('job', 0, 0, store_id=store), {'pruned': 1, 'more': False})
            with self.assertRaises(SettlementConflictError):
                journal.lifecycle_note(identity, 'phase', {}, store_id=store, outbox_sequence=1)
            kernel.close()

    def test_ack_verifier_and_prune_use_bounded_locks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel'
            kernel = SQLiteKernel(path)
            for execution in ('job', 'other'):
                kernel.submit(make_command(execution))
            store = kernel.kernel_store_identity()
            journal = SettlementJournal(Path(directory) / 'journal', source_id='source', kernel_path=path)
            kernel.lifecycle_reserve('job', 0, 0, 'job-token', slots=1)
            kernel.lifecycle_append('job-token', 'job-event', 'phase', {})
            journal.lifecycle_note({'execution_id': 'job', 'attempt': 0, 'fence': 0}, 'phase', {}, store_id=store, outbox_sequence=1)
            kernel.lifecycle_ack(1, 'job-event')
            kernel.lifecycle_finish('job-token')
            kernel.lifecycle_retire_generation('job', 0, 0)
            kernel.lifecycle_reserve('other', 0, 0, 'token', slots=1)
            sequence = kernel.lifecycle_append('token', 'other-event', 'phase', {}, identity=('other', 0, 0))
            verifier_entered, release = threading.Event(), threading.Event()
            outcomes = []
            original = kernel._authorize_lifecycle
            def verifier(connection, execution_id, attempt, fence, operation, timestamp, *args, **kwargs):
                if operation == 'ack':
                    verifier_entered.set()
                    if not release.wait(2):
                        raise TimeoutError('test verifier wait elapsed')
                    with journal._connection(1, write=True):
                        pass
                return original(connection, execution_id, attempt, fence, operation, timestamp, *args, **kwargs)
            def ack():
                try:
                    outcomes.append(kernel.lifecycle_ack(sequence, 'other-event', timeout_seconds=3))
                except Exception as error:
                    outcomes.append(error)
            pruning = []
            prune_entered = threading.Event()
            def prune():
                try:
                    prune_entered.set()
                    pruning.append(journal.prune_lifecycle_notes('job', 0, 0,
                        store_id=store, timeout_seconds=3))
                except Exception as error:
                    pruning.append(error)
            with patch.object(kernel, '_authorize_lifecycle', side_effect=verifier):
                worker = threading.Thread(target=ack)
                worker.start()
                self.assertTrue(verifier_entered.wait(2))
                prune_worker = threading.Thread(target=prune)
                prune_worker.start()
                try:
                    self.assertTrue(prune_entered.wait(1))
                    time.sleep(.05)
                    self.assertTrue(prune_worker.is_alive(), 'prune overtook in-flight ACK')
                finally:
                    release.set()
                worker.join(3)
                prune_worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(prune_worker.is_alive())
            self.assertEqual(pruning, [{'pruned': 1, 'more': False}])
            self.assertEqual(outcomes, [True])
            kernel.close()

    def test_v3_copy_upgrade_preserves_notes_and_source(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteKernel(Path(directory) / 'kernel') as kernel_db:
            source = Path(directory) / 'v3'
            destination = Path(directory) / 'v4'
            kernel = Path(directory) / 'kernel'
            store = kernel_db.kernel_store_identity()
            kernel_db.submit(make_command('job'))
            kernel_db.lifecycle_reserve('job', 0, 0, 'p', slots=1)
            kernel_db.lifecycle_append('p', 'event', 'phase', {})
            with contextlib.closing(sqlite3.connect(source)) as db, db:
                for statement in _SCHEMA:
                    db.execute(statement.replace('CHECK(version=2)', 'CHECK(version=3)'))
                db.execute('INSERT INTO settlement_meta VALUES(1,3,?,?)', ('source', str(kernel.resolve())))
                db.execute('INSERT INTO settlement_recovery_cursor VALUES(1,NULL)')
            old = SettlementJournal.open_existing(source, source_id='source', kernel_path=kernel)
            identity = {'execution_id': 'job', 'attempt': 0, 'fence': 0}
            old.note(identity, 'old', {}, note_id='old-id')
            with self.assertRaises(SettlementBindingError):
                old.lifecycle_note(identity, 'phase', {}, store_id=store, outbox_sequence=1)
            new = SettlementJournal.upgrade_v3_copy(source, destination, source_id='source', kernel_path=kernel)
            new.lifecycle_note(identity, 'phase', {}, store_id=store, outbox_sequence=1)
            self.assertEqual(len(new.inspect_notes('job')['notes']), 2)
            self.assertEqual(len(old.inspect_notes('job')['notes']), 1)


if __name__ == '__main__':
    unittest.main()
