"""Durable recovery scan progress, independent of Runtime launch and hashing."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from dispatcher_sdk.execution_kernel.contracts import ExecutionLease, ExecutionResultV2
from dispatcher_sdk.execution_kernel.runtime import Runtime
from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.settlement import (SettlementBindingError, SettlementBusyError,
    SettlementConflictError, SettlementJournal, _SCHEMA)


class SettlementRecoveryCursorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settlement.sqlite'
        self.kernel_path = Path(self.temp.name) / 'kernel.sqlite'

    def open(self):
        return SettlementJournal(self.path, source_id='source', kernel_path=self.kernel_path, timeout_seconds=1)

    def seed(self, journal, count=4):
        for index in range(count):
            lease = ExecutionLease(f'execution-{index}', f'lease-{index}', 'worker', 1, 1, 9999999999, 1)
            journal.record(lease, {'kind': 'unknown', 'outcome': {}},
                evidence={'budget_checkpoint': {'state': 'unknown'}}, timeout_seconds=1)

    def test_restart_per_page_reaches_every_unknown_without_settlement(self):
        self.seed(self.open())
        observed = []
        for _ in range(4):
            # Fresh Runtime shell and journal per page; no handler or Runtime launch.
            runtime = object.__new__(Runtime)
            runtime.kernel = SimpleNamespace(_positive_duration=lambda value, _name: value)
            runtime._settlement_journal = self.open()
            runtime._settlement_lock = threading.Lock()
            runtime._settlement_inflight_lock = threading.Lock()
            runtime._settlement_inflight = set()
            runtime._closed = False
            runtime._persist_pending_settlements = lambda *_args, **_kwargs: []
            runtime._drain_recovery_completion_readers = lambda *_: None
            runtime._recover_script_output = lambda *_: None
            runtime._finish_received_budget_checkpoints = lambda *_: None
            runtime._reconcile_recorded_handoffs = lambda *_args, **_kwargs: []
            reports = runtime.recover_completions(limit=1, timeout_seconds=1)
            self.assertEqual(reports[0]['state'], 'pending')
            observed.append(reports[0]['execution_id'])
        self.assertEqual(set(observed), {f'execution-{i}' for i in range(4)})
        self.assertEqual(len(self.open().pending()), 4)
        self.assertEqual(self.open().next_pending_round_robin(timeout_seconds=1)['identity']['execution_id'], observed[0])

    def test_v2_readonly_then_transactional_upgrade_retains_records_and_binding(self):
        with sqlite3.connect(self.path) as db:
            for statement in _SCHEMA[:-1]: db.execute(statement)
            db.execute('INSERT INTO settlement_meta VALUES(1,2,?,?)', ('source', str(self.kernel_path)))
            original = ExecutionLease('legacy', 'legacy-lease', 'worker', 1, 1, 9999999999, 1)
            db.execute('INSERT INTO settlement_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       ('legacy', 1, 1, json.dumps(original.to_dict()), 'deferred',
                        json.dumps({'kind': 'unknown', 'outcome': {}}), 'pending', '{}', 1, 1.0, 1.0))
        old = SettlementJournal.open_readonly(self.path, source_id='source', kernel_path=self.kernel_path, timeout_seconds=1)
        self.assertEqual(old.pending(timeout_seconds=1)[0]['identity']['execution_id'], 'legacy')
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT version FROM settlement_meta').fetchone()[0], 2)
        with self.assertRaises(SettlementBindingError):
            SettlementJournal(self.path, source_id='wrong', kernel_path=self.kernel_path, timeout_seconds=1)
        with self.assertRaises(SettlementBindingError):
            self.open()
        upgraded = Path(self.temp.name) / 'upgraded.sqlite'
        journal = SettlementJournal.upgrade_v2_copy(self.path, upgraded, source_id='source', kernel_path=self.kernel_path, timeout_seconds=1)
        self.assertEqual(journal.next_pending_round_robin(timeout_seconds=1)['identity']['execution_id'], 'legacy')
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT version FROM settlement_meta').fetchone()[0], 2)
        with sqlite3.connect(upgraded) as db:
            self.assertEqual(db.execute('SELECT version FROM settlement_meta').fetchone()[0], 3)

    def test_oversized_obligation_is_visible_and_does_not_block_next(self):
        journal = self.open()
        lease = ExecutionLease('big', 'lease', 'worker', 1, 1, 9999999999, 1)
        journal.record(lease, {'kind': 'unknown', 'outcome': {'data': 'x' * 300000}}, timeout_seconds=1)
        self.seed(journal, 1)
        first = journal.next_pending_round_robin(timeout_seconds=1)
        self.assertTrue(first['oversized'])
        self.assertEqual(first['identity'], {'execution_id': 'big', 'attempt': 1, 'fence': 1})
        self.assertGreater(first['required_bytes'], 256 * 1024)
        self.assertEqual(journal.next_pending_round_robin(timeout_seconds=1)['identity']['execution_id'], 'execution-0')
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT state FROM settlement_records WHERE execution_id='big'").fetchone()[0], 'pending')

    def test_large_identifier_is_not_materialized_in_bounded_diagnostic(self):
        journal = self.open()
        identifier = 'x' * 300000
        journal.record(ExecutionLease(identifier, 'lease', 'worker', 1, 1, 9999999999, 1),
                       {'kind': 'unknown', 'outcome': {}}, timeout_seconds=1)
        report = journal.next_pending_round_robin(timeout_seconds=1)
        self.assertTrue(report['oversized'])
        self.assertIsNone(report['identity'])
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT typeof(last_rowid) FROM settlement_recovery_cursor').fetchone()[0], 'integer')

    def test_vacuum_renumbering_still_wraps_to_all_remaining_rows(self):
        journal = self.open()
        self.seed(journal)
        journal.next_pending_round_robin(timeout_seconds=1)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM settlement_records WHERE execution_id='execution-0'")
            db.commit()
            db.execute('VACUUM')
        observed = {journal.next_pending_round_robin(timeout_seconds=1)['identity']['execution_id'] for _ in range(3)}
        self.assertEqual(observed, {'execution-1', 'execution-2', 'execution-3'})

    def test_runtime_can_recover_large_receipt_with_explicit_read_budget(self):
        path = Path(self.temp.name) / 'large-kernel.sqlite'
        def handler(_payload, _context): raise AssertionError('not invoked')
        with patch('dispatcher_sdk.execution_kernel.runtime.registry_revision', return_value='host-supplied'), \
             patch('dispatcher_sdk.execution_kernel.runtime.handler_revision', return_value='host-supplied'):
            runtime = Kernel.open_sqlite(path, {'work': handler}, isolation_mode='thread')
            try:
                cmd = runtime.command('work', execution_id='large', idempotency_key='large',
                                      correlation_id='large', timeout_seconds=120, payload={})
                runtime.submit(cmd)
                lease = runtime.kernel.claim_and_start('worker', execution_id='large', lease_seconds=120)
                runtime.kernel.register_supervisor_obligation(lease)
                started = runtime.kernel.get('large').started_at
                result = ExecutionResultV2('large-result', 'large', 'succeeded', lease.attempt, lease.fence, [],
                    started, max(started, runtime.kernel.current_time()), 'large', None, {'data': 'x' * 300000}, None)
                runtime._settlement_journal.record(lease, result, evidence={'supervisor_completion': {
                    'cleanup': 'confirmed', 'source': 'runtime_supervisor_reaped', 'result': 'accepted'}}, timeout_seconds=1)
                report = runtime.recover_completions(limit=1, timeout_seconds=2)
                self.assertEqual(report[0]['state'], 'pending')
                self.assertGreater(report[0]['required_bytes'], 256 * 1024)
                report = runtime.recover_completions(limit=1, timeout_seconds=2, max_record_bytes=1024 * 1024)
                self.assertEqual(report[0]['state'], 'recorded')
                self.assertEqual(runtime.kernel.get('large').result.value, result.value)
            finally:
                runtime.close()

    def test_background_after_restart_recovers_large_receipt_with_host_budget(self):
        path = Path(self.temp.name) / 'background-kernel.sqlite'
        def handler(_payload, _context): raise AssertionError('not invoked')
        with patch('dispatcher_sdk.execution_kernel.runtime.registry_revision', return_value='host-supplied'), \
             patch('dispatcher_sdk.execution_kernel.runtime.handler_revision', return_value='host-supplied'):
            runtime = Kernel.open_sqlite(path, {'work': handler}, isolation_mode='thread')
            cmd = runtime.command('work', execution_id='large', idempotency_key='large',
                                  correlation_id='large', timeout_seconds=120, payload={})
            runtime.submit(cmd)
            lease = runtime.kernel.claim_and_start('worker', execution_id='large', lease_seconds=120)
            runtime.kernel.register_supervisor_obligation(lease)
            started = runtime.kernel.get('large').started_at
            result = ExecutionResultV2('large-result', 'large', 'succeeded', lease.attempt, lease.fence, [],
                started, max(started, runtime.kernel.current_time()), 'large', None, {'data': 'x' * 300000}, None)
            journal = runtime._settlement_journal
            runtime.close()
            journal.record(lease, result, evidence={'supervisor_completion': {
                'cleanup': 'confirmed', 'source': 'runtime_supervisor_reaped', 'result': 'accepted'}}, timeout_seconds=1)
            # The first reopened background loop reports the default size refusal.
            runtime = Kernel.open_sqlite(path, {'work': handler}, isolation_mode='thread')
            runtime.run_once(execution_id='no-such-execution')
            deadline = time.monotonic() + 5
            while runtime.settlement_recovery_diagnostic is None and time.monotonic() < deadline:
                time.sleep(.02)
            diagnostic = runtime.settlement_recovery_diagnostic
            self.assertEqual(diagnostic['execution_id'], 'large')
            self.assertGreater(diagnostic['required_bytes'], 256 * 1024)
            self.assertEqual(runtime.kernel.get('large').state, 'running')
            runtime.close()
            # A host-configured larger bounded budget survives another restart.
            runtime = Kernel.open_sqlite(path, {'work': handler}, isolation_mode='thread',
                settlement_recovery_max_record_bytes=1024 * 1024, settlement_recovery_timeout_seconds=2)
            try:
                runtime.run_once(execution_id='no-such-execution')
                deadline = time.monotonic() + 5
                while (runtime.kernel.get('large').state != 'succeeded' or
                       runtime._settlement_journal.inspect('large', timeout_seconds=1)[0]['state'] != 'recorded') and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertEqual(runtime.kernel.get('large').result.value, result.value)
                self.assertEqual(runtime._settlement_journal.inspect('large', timeout_seconds=1)[0]['state'], 'recorded')
            finally:
                runtime.close()

    def test_writer_contention_does_not_advance_cursor(self):
        journal = self.open()
        self.seed(journal, 2)
        with sqlite3.connect(self.path) as connection:
            connection.execute('BEGIN IMMEDIATE')
            with self.assertRaises(SettlementBusyError):
                journal.next_pending_round_robin(timeout_seconds=.02)
            connection.rollback()
        self.assertEqual(journal.next_pending_round_robin(timeout_seconds=1)['identity']['execution_id'], 'execution-0')

    def test_concurrent_settlement_cannot_be_overwritten_by_stale_scan(self):
        journal = self.open()
        self.seed(journal, 1)
        selected = journal.next_pending_round_robin(timeout_seconds=1)
        self.open().settle(selected, 'recorded', {'receipt': 'other maintainer'}, timeout_seconds=1)
        with self.assertRaises(SettlementConflictError):
            journal.settle(selected, 'error', {'error': 'stale'}, timeout_seconds=1)
        self.assertEqual(journal.inspect('execution-0', timeout_seconds=1)[0]['state'], 'recorded')

    def test_failed_copy_upgrade_leaves_original_and_no_destination(self):
        with sqlite3.connect(self.path) as db:
            for statement in _SCHEMA[:-1]: db.execute(statement)
            db.execute('INSERT INTO settlement_meta VALUES(1,2,?,?)', ('source', str(self.kernel_path)))
        destination = Path(self.temp.name) / 'failed-copy.sqlite'
        validate = SettlementJournal._validate
        def fail_v3(journal, connection):
            version = validate(journal, connection)
            if version == 3:
                raise SettlementBindingError('injected post-upgrade failure')
            return version
        with patch.object(SettlementJournal, '_validate', fail_v3):
            with self.assertRaisesRegex(SettlementBindingError, 'injected'):
                SettlementJournal.upgrade_v2_copy(self.path, destination, source_id='source', kernel_path=self.kernel_path, timeout_seconds=1)
        self.assertFalse(destination.exists())
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT version FROM settlement_meta').fetchone()[0], 2)

    def test_concurrent_scanners_advance_one_shared_cursor(self):
        self.seed(self.open())
        with ThreadPoolExecutor(max_workers=4) as pool:
            records = list(pool.map(lambda _: self.open().next_pending_round_robin(timeout_seconds=1), range(4)))
        self.assertEqual(len({record['identity']['execution_id'] for record in records}), 4)
        self.assertEqual(len(self.open().pending(timeout_seconds=1)), 4)

    def test_recovery_rejects_byte_limit_outside_sqlite_integer_range(self):
        journal = self.open()
        with self.assertRaises(ValueError):
            journal.next_pending_round_robin(max_record_bytes=1 << 63)
        with self.assertRaises(ValueError):
            object.__new__(Runtime).recover_completions(max_record_bytes=1 << 63)

    def test_runtime_refuses_unupgraded_v2_journal(self):
        kernel_path = Path(self.temp.name) / 'actual-kernel.sqlite'
        with patch('dispatcher_sdk.execution_kernel.runtime.registry_revision', return_value='host-supplied'), \
             patch('dispatcher_sdk.execution_kernel.runtime.handler_revision', return_value='host-supplied'):
            first = Kernel.open_sqlite(kernel_path, {}, isolation_mode='thread')
            source_id = first._observation_source_id
            journal_path = Path(first._settlement_journal.path)
            first.close()
            journal_path.unlink()
            with sqlite3.connect(journal_path) as db:
                for statement in _SCHEMA[:-1]: db.execute(statement)
                db.execute('INSERT INTO settlement_meta VALUES(1,2,?,?)', (source_id, str(kernel_path)))
            with self.assertRaises(SettlementBindingError):
                Kernel.open_sqlite(kernel_path, {}, isolation_mode='thread')
            with sqlite3.connect(journal_path) as db:
                self.assertEqual(db.execute('SELECT version FROM settlement_meta').fetchone()[0], 2)
            destination = Path(self.temp.name) / 'copy.sqlite'
            SettlementJournal.upgrade_v2_copy(journal_path, destination, source_id=source_id, kernel_path=kernel_path, timeout_seconds=1)
            selected = Kernel.open_sqlite(kernel_path, {}, isolation_mode='thread', settlement_journal_path=str(destination))
            try:
                self.assertEqual(selected.settlement_storage, {'path': str(destination), 'kernel_path': str(kernel_path),
                                 'source_id': source_id, 'available': True})
            finally:
                selected.close()
            with self.assertRaises((ValueError, sqlite3.OperationalError)):
                Kernel.open_sqlite(kernel_path, {}, isolation_mode='thread', settlement_journal_path='')
            with self.assertRaises(sqlite3.OperationalError):
                Kernel.open_sqlite(kernel_path, {}, isolation_mode='thread', settlement_journal_path=str(Path(self.temp.name) / 'missing'))
