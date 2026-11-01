"""Synthetic host authorization tests; these do not establish host isolation."""
import sqlite3
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, SQLiteKernel, runtime as runtime_module
from dispatcher_sdk.execution_kernel.settlement import SettlementBindingError, SettlementJournal, _SCHEMA
from dispatcher_sdk.execution_kernel.settlement_migration import copy_rebind_settlement
from dispatcher_sdk.maintenance import maintenance_lease
from dispatcher_sdk.storage_migration import upgrade_storage
import test_runtime_captured_checkpoint_recovery as recovery_fixture
from test_execution_kernel_v2_sqlite import make_command


class SettlementCopyRebindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.old_kernel, self.new_kernel = root / 'old-kernel', root / 'new-kernel'
        self.old_kernel.touch()
        self.new_kernel.touch()
        self.source, self.dest = root / 'source', root / 'dest'
        self.claims = []

    def create_source(self, version):
        with sqlite3.connect(self.source) as db:
            for statement in (_SCHEMA[:-1] if version == 2 else
                              [s.replace('CHECK(version=2)', 'CHECK(version=3)') for s in _SCHEMA]):
                db.execute(statement)
            db.execute('INSERT INTO settlement_meta VALUES(1,?,?,?)',
                       (version, 'origin', str(self.old_kernel)))
            if version == 3:
                db.execute('INSERT INTO settlement_recovery_cursor VALUES(1,42)')
            db.execute('INSERT INTO settlement_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       ('exec', 2, 9, '{"lease":"original"}', 'deferred', '{"outcome":"unknown"}',
                        'pending', '{"clock":"unknown"}', 4, 1.0, 2.0))
            db.execute('INSERT INTO settlement_notes VALUES(?,?,?,?,?,?,?,?)',
                       (8, 'note', 'exec', 2, 9, 'capture', '{"sample":7}', 3.0))

    def copy(self, verifier=None, **overrides):
        def accepted(credential, claim):
            self.claims.append((credential, claim))
            return True
        args = dict(source_kernel_path=self.old_kernel, destination_kernel_path=self.new_kernel,
                    source_id='origin', operation_id='migration-1', credential='host-proof',
                    verify_host=verifier or accepted, timeout_seconds=2)
        args.update(overrides)
        return copy_rebind_settlement(self.source, self.dest, **args)

    def test_v2_and_v3_preserve_facts_and_change_only_binding(self):
        for version in (2, 3):
            with self.subTest(version=version):
                self.create_source(version)
                receipt = self.copy()
                self.assertEqual(receipt['source_version'], version)
                self.assertFalse(receipt['automatic_activation'])
                with sqlite3.connect(self.source) as original, sqlite3.connect(self.dest) as copied:
                    for table in ('settlement_records', 'settlement_notes'):
                        self.assertEqual(original.execute(f'SELECT * FROM {table}').fetchall(),
                                         copied.execute(f'SELECT * FROM {table}').fetchall())
                    self.assertEqual(original.execute('SELECT version,kernel_path FROM settlement_meta').fetchone(),
                                     (version, str(self.old_kernel)))
                    self.assertEqual(copied.execute('SELECT version,kernel_path FROM settlement_meta').fetchone(),
                                     (3, str(self.new_kernel)))
                    if version == 3:
                        self.assertEqual(copied.execute('SELECT last_rowid FROM settlement_recovery_cursor').fetchone(), (42,))
                SettlementJournal.open_existing(self.dest, source_id='origin', kernel_path=self.new_kernel)
                with self.assertRaises(SettlementBindingError):
                    SettlementJournal.open_existing(self.dest, source_id='origin', kernel_path=self.old_kernel)
                self.assertEqual(self.claims[-2][1], self.claims[-1][1])
                with self.assertRaises(FileExistsError):
                    self.copy()
                self.source.unlink()
                self.dest.unlink()

    def test_denied_or_revoked_authority_and_bad_binding_leave_no_destination(self):
        self.create_source(3)
        for verifier in (lambda *_: False, iter((True, False)).__next__):
            if getattr(verifier, '__name__', '') == '__next__':
                next_value = verifier
                verifier = lambda *_: next_value()
            with self.assertRaises(SettlementBindingError):
                self.copy(verifier)
            self.assertFalse(self.dest.exists())
        with self.assertRaises(SettlementBindingError):
            self.copy(source_id='wrong')
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.dest.parent.glob('.settlement-copy-*')), [])

    def test_v4_copy_preserves_lifecycle_receipt_namespace(self):
        kernel = SQLiteKernel(self.old_kernel)
        kernel.submit(make_command('exec'))
        kernel.lifecycle_reserve('exec', 0, 0, 'p', slots=1)
        sequence = kernel.lifecycle_append('p', 'event', 'phase', {'fact': 1})
        store_id = kernel.kernel_store_identity()
        kernel.close()
        with sqlite3.connect(self.old_kernel) as source_kernel, sqlite3.connect(self.new_kernel) as destination_kernel:
            source_kernel.backup(destination_kernel)
        journal = SettlementJournal(self.source, source_id='origin', kernel_path=self.old_kernel)
        identity = {'execution_id': 'exec', 'attempt': 0, 'fence': 0}
        original = journal.lifecycle_note(identity, 'phase', {'fact': 1}, store_id=store_id, outbox_sequence=sequence)
        result = self.copy()
        self.assertEqual((result['source_version'], result['target_version']), (4, 4))
        copied = SettlementJournal.open_existing(self.dest, source_id='origin', kernel_path=self.new_kernel)
        self.assertEqual(copied.lifecycle_note(identity, 'phase', {'fact': 1}, store_id=store_id, outbox_sequence=sequence), original)
        self.assertEqual(len(copied.inspect_notes('exec')['notes']), 1)

    def test_existing_target_and_kernel_alias_are_rejected(self):
        self.create_source(3)
        self.dest.write_text('preserve')
        with self.assertRaises(FileExistsError):
            self.copy()
        self.assertEqual(self.dest.read_text(), 'preserve')
        self.dest.unlink()
        with self.assertRaises(SettlementBindingError):
            self.copy(destination_kernel_path=self.old_kernel)
        self.assertFalse(self.dest.exists())

    def test_existing_and_dangling_destination_symlinks_are_rejected(self):
        self.create_source(3)
        for existing in (True, False):
            target = self.dest.parent / ('target-' + str(existing))
            if existing:
                target.write_text('unchanged')
            self.dest.symlink_to(target)
            with self.assertRaises(FileExistsError):
                self.copy()
            self.assertTrue(self.dest.is_symlink())
            if existing:
                self.assertEqual(target.read_text(), 'unchanged')
            else:
                self.assertFalse(target.exists())
            self.dest.unlink()

    @unittest.skipUnless(os.name == 'posix', 'requires POSIX process containment')
    def test_copied_kernel_runtime_recovers_original_pending_result(self):
        # Synthetic verifier models an isolated host; it does not fence writers.
        for version in (2, 3):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory, \
                 patch.object(runtime_module, 'registry_revision', return_value='fixture-registry'), \
                 patch.object(runtime_module, 'handler_revision', return_value='fixture-handler'):
                root = Path(directory)
                old_kernel, new_kernel = root / 'old.sqlite', root / 'new.sqlite'
                tokens, original, _ = recovery_fixture.CapturedCheckpointRecoveryTests.crash_receipt(self, old_kernel)
                source = Path(str(old_kernel) + '.settlements.sqlite3')
                destination = root / 'selected.sqlite'
                if version == 2:
                    # Construct the historical schema with exactly the captured facts.
                    with sqlite3.connect(source) as db:
                        db.execute('DROP TABLE settlement_lifecycle_receipts')
                        db.execute('DROP TABLE settlement_recovery_cursor')
                        db.execute('ALTER TABLE settlement_meta RENAME TO old_meta')
                        db.execute(_SCHEMA[0])
                        db.execute('INSERT INTO settlement_meta SELECT singleton,2,source_id,kernel_path FROM old_meta')
                        db.execute('DROP TABLE old_meta')
                with sqlite3.connect(source) as db:
                    metadata = db.execute('SELECT source_id,kernel_path,version FROM settlement_meta').fetchone()
                    source_records = db.execute('SELECT * FROM settlement_records').fetchall()
                    source_notes = db.execute('SELECT * FROM settlement_notes').fetchall()
                with maintenance_lease(old_kernel, 'test-host', 'copy', lease_seconds=30) as lease:
                    upgrade_storage(old_kernel, new_kernel, lease=lease)
                args = dict(source_kernel_path=old_kernel, destination_kernel_path=new_kernel,
                            source_id=metadata[0], operation_id='copy-test', credential='synthetic',
                            verify_host=lambda _credential, _claim: True, timeout_seconds=5)
                copy_rebind_settlement(source, destination, **args)
                with self.assertRaises(FileExistsError):
                    copy_rebind_settlement(source, destination, **args)
                denied = root / 'denied.sqlite'
                approvals = iter((True, False))
                with self.assertRaises(SettlementBindingError):
                    copy_rebind_settlement(source, denied, **{**args, 'verify_host': lambda *_: next(approvals)})
                self.assertFalse(denied.exists())
                runtime = Kernel.open_sqlite(new_kernel, {'handler': recovery_fixture._handler}, isolation_mode='process',
                                             settlement_journal_path=str(destination))
                try:
                    self.assertEqual(runtime._settlement_journal.pending()[0]['result'], original['result'])
                    reports = runtime.recover_completions(timeout_seconds=3)
                    self.assertTrue(any(item['state'] == 'recorded' for item in reports), reports)
                    self.assertEqual(runtime.kernel.get('execution').result.to_dict(), original['result'])
                    self.assertEqual(runtime.kernel.inspect_supervisor_obligations('execution')['obligations'][0]['state'], 'resolved')
                    self.assertEqual(runtime._settlement_journal.inspect('execution')[0]['identity'], original['identity'])
                finally:
                    runtime.close()
                with sqlite3.connect(source) as db:
                    self.assertEqual(db.execute('SELECT source_id,kernel_path,version FROM settlement_meta').fetchone(), metadata)
                    self.assertEqual(db.execute('SELECT * FROM settlement_records').fetchall(), source_records)
                    self.assertEqual(db.execute('SELECT * FROM settlement_notes').fetchall(), source_notes)
