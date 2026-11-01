"""Real supervisor retry; registry identity functions are fixed test stubs."""
import contextlib
import os
import multiprocessing
import sqlite3
from dataclasses import replace
import tempfile
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionLease, ExecutionResultV2, HandlerExecutionError, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime
from dispatcher_sdk.execution_kernel.budget import sample_clock
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel


def large_retry(payload, context):
    if payload.get('large') and context.lease.attempt == 1:
        raise HandlerExecutionError('temporary', 'retry', retryable=True,
                                    details={'data': 'x' * 150000})
    if payload.get('terminal_large'):
        return {'data': 'x' * 1100000}
    return {'execution_id': context.lease.execution_id, 'attempt': context.lease.attempt,
            'fence': context.lease.fence, 'pid': os.getpid()}


def claim_in_other_process(path, pipe):
    try:
        with SQLiteKernel(path) as kernel:
            lease = kernel.claim('independent-worker', execution_id='large')
            pipe.send(lease.to_dict())
    finally:
        pipe.close()


def crash_with_captured_result(path, pipe):
    finish = process_runtime._finish_budget_capture
    injected = []
    def capture(owner, envelope, *, timeout_seconds=.1):
        if not injected:
            token = owner.kernel._begin_budget_sample(owner.execution_id, timeout_seconds=1, _owner=owner)
            owner._captured(token, envelope.recheckpoint(sample=sample_clock()))
            owner.finish_pending = lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError('blocked'))
            injected.append(token)
        return finish(owner, envelope, timeout_seconds=timeout_seconds)
    try:
        with patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'), \
             patch.object(runtime_module.Runtime, '_settlement_loop', return_value=None):
            runtime = Kernel.open_sqlite(path, {'work': large_retry}, isolation_mode='process')
            policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                 backoff_multiplier=1, max_backoff_seconds=0)
            runtime.submit(runtime.command('work', execution_id='large', idempotency_key='large',
                correlation_id='large', timeout_seconds=30, payload={'large': True}, retry_policy=policy))
            with patch.object(process_runtime, '_finish_budget_capture', side_effect=capture), \
                 patch.object(runtime, '_finish_received_budget_checkpoints', side_effect=TimeoutError('blocked')):
                runtime.run_once(execution_id='large')
            pipe.send(runtime._settlement_journal.pending()[0])
    except BaseException as exc:
        pipe.send(('error', repr(exc)))
    finally:
        pipe.close()
        os._exit(0)


@unittest.skipUnless(os.name == 'posix', 'requires POSIX supervisor')
class LargeHandoffRetryTests(unittest.TestCase):
    def test_recorded_reconciliation_rotates_after_deadline_exhaustion(self):
        runtime = object.__new__(runtime_module.Runtime)
        runtime._diagnostic_pending_lock = threading.Lock()
        runtime._diagnostic_unknown_handoffs = {('a', 1, 1), ('b', 1, 1)}
        runtime._diagnostic_handoff_cursor = None
        visited = []
        class Connection:
            def execute(self, _sql, key):
                visited.append(key)
                if key[0] == 'a':
                    time.sleep(.03)
                    raise TimeoutError('blocked')
                return SimpleNamespace(fetchone=lambda: None)
        @contextmanager
        def connection(_timeout):
            yield Connection()
        runtime._settlement_journal = SimpleNamespace(_connection=connection)
        runtime._reconcile_recorded_handoffs(time.monotonic() + .01, limit=2, max_record_bytes=4096)
        runtime._reconcile_recorded_handoffs(time.monotonic() + .1, limit=2, max_record_bytes=4096)
        self.assertEqual([key[0] for key in visited[:2]], ['a', 'b'])

    def test_handoff_capacity_recovers_without_clearing_generic_overflow(self):
        runtime = object.__new__(runtime_module.Runtime)
        runtime._diagnostic_pending_lock = threading.Lock()
        runtime._diagnostic_pending_capacity = 1
        runtime._diagnostic_pending_overflow = False
        runtime._diagnostic_pending = {}
        runtime._diagnostic_failed_executions = set()
        runtime._diagnostic_unknown_handoffs = {('large', 1, 1)}
        runtime._settlement_journal = object()
        self.assertTrue(runtime._diagnostic_claim_exclusions('other')[0])
        runtime._resolve_diagnostic_handoff(type('Lease', (), {'execution_id': 'large', 'attempt': 1, 'fence': 1})())
        self.assertFalse(runtime._diagnostic_claim_exclusions('other')[0])
        runtime._diagnostic_pending_overflow = True
        runtime._resolve_diagnostic_handoff(type('Lease', (), {'execution_id': 'large', 'attempt': 1, 'fence': 1})())
        self.assertTrue(runtime._diagnostic_claim_exclusions('other')[0])

    def test_postcommit_terminal_large_result_respects_explicit_read_budget(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'), \
             patch.object(runtime_module.Runtime, '_settlement_loop', return_value=None):
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.sqlite', {'work': large_retry}, isolation_mode='process')
            try:
                runtime.submit(runtime.command('work', execution_id='large', idempotency_key='large',
                    correlation_id='large', timeout_seconds=30, payload={'terminal_large': True}))
                settle = runtime._settlement_journal.settle
                def commit_then_lose_ack(*args, **kwargs):
                    settle(*args, **kwargs)
                    raise TimeoutError('committed; acknowledgement lost')
                with patch.object(runtime._settlement_journal, 'settle', side_effect=commit_then_lose_ack):
                    self.assertEqual(runtime.run_once(execution_id='large').state, 'succeeded')
                self.assertTrue(runtime._diagnostics_block_admission('large'))
                runtime.recover_completions(timeout_seconds=3, max_record_bytes=256 * 1024)
                self.assertTrue(runtime._diagnostics_block_admission('large'))
                reports = runtime.recover_completions(timeout_seconds=3, max_record_bytes=2 * 1024 * 1024)
                self.assertTrue(any(item['state'] == 'recorded' for item in reports), reports)
                self.assertFalse(runtime._diagnostics_block_admission('large'))
                self.assertEqual(len(runtime.kernel.get('large').result.value['data']), 1100000)
            finally:
                runtime.close()

    def test_postcommit_journal_ack_loss_reconciles_recorded_receipt(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'), \
             patch.object(runtime_module.Runtime, '_settlement_loop', return_value=None):
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.sqlite', {'work': large_retry}, isolation_mode='process')
            try:
                policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     backoff_multiplier=1, max_backoff_seconds=0)
                runtime.submit(runtime.command('work', execution_id='large', idempotency_key='large',
                    correlation_id='large', timeout_seconds=30, payload={'large': True}, retry_policy=policy))
                settle = runtime._settlement_journal.settle
                def commit_then_lose_ack(*args, **kwargs):
                    settle(*args, **kwargs)
                    raise TimeoutError('committed; acknowledgement lost')
                with patch.object(runtime._settlement_journal, 'settle', side_effect=commit_then_lose_ack):
                    self.assertEqual(runtime.run_once(execution_id='large').state, 'queued')
                self.assertEqual(runtime._settlement_journal.inspect('large')[0]['state'], 'recorded')
                self.assertTrue(runtime._diagnostics_block_admission('large'))
                reports = runtime.recover_completions(timeout_seconds=3)
                self.assertTrue(any(item['state'] == 'recorded' for item in reports), reports)
                self.assertFalse(runtime._diagnostics_block_admission('large'))
                self.assertEqual(runtime.recover_completions(timeout_seconds=3), ())
                self.assertEqual(runtime.run_once(execution_id='large').result.value['attempt'], 2)
            finally:
                runtime.close()

    def test_background_reconciles_postcommit_ack_before_manual_scan(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'):
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.sqlite', {'work': large_retry}, isolation_mode='process')
            reconciled = threading.Event()
            seen = []
            reconcile = runtime._reconcile_recorded_handoffs
            def observe(*args, **kwargs):
                reports = reconcile(*args, **kwargs)
                if reports:
                    seen.extend(reports)
                    reconciled.set()
                return reports
            try:
                policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     backoff_multiplier=1, max_backoff_seconds=0)
                runtime.submit(runtime.command('work', execution_id='large', idempotency_key='large',
                    correlation_id='large', timeout_seconds=30, payload={'large': True}, retry_policy=policy))
                settle = runtime._settlement_journal.settle
                def commit_then_lose_ack(*args, **kwargs):
                    settle(*args, **kwargs)
                    raise TimeoutError('committed; acknowledgement lost')
                with patch.object(runtime, '_reconcile_recorded_handoffs', side_effect=observe), \
                     patch.object(runtime._settlement_journal, 'settle', side_effect=commit_then_lose_ack):
                    self.assertEqual(runtime.run_once(execution_id='large').state, 'queued')
                    self.assertTrue(reconciled.wait(10), 'background recovery did not reconcile the receipt')
                record = runtime._settlement_journal.inspect('large')[0]
                self.assertEqual(record['state'], 'recorded')
                self.assertEqual(seen, [{**record['identity'], 'state': 'recorded',
                                         'result_id': record['result']['result_id']}])
                self.assertFalse(runtime._diagnostics_block_admission('large'))
                self.assertEqual(runtime.recover_completions(timeout_seconds=3), ())
                self.assertEqual(runtime.run_once(execution_id='large').result.value['attempt'], 2)
            finally:
                runtime.close()

    def test_captured_checkpoint_retry_lost_ack_reconciles(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'), \
             patch.object(runtime_module.Runtime, '_settlement_loop', return_value=None):
            path = Path(root) / 'kernel.sqlite'
            ctx = multiprocessing.get_context('spawn')
            reader, writer = ctx.Pipe(duplex=False)
            process = ctx.Process(target=crash_with_captured_result, args=(path, writer))
            process.start()
            writer.close()
            self.assertTrue(reader.poll(20))
            record = reader.recv()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertIsInstance(record, dict, record)
            runtime = Kernel.open_sqlite(path, {'work': large_retry}, isolation_mode='process')
            try:
                self.assertIn('supervisor_completion_pending_checkpoint', record['evidence'])
                # Model an equivalent still-live diagnostic marker on this Runtime.
                identity = record['identity']
                runtime._diagnostic_unknown_handoffs.add((identity['execution_id'], identity['attempt'], identity['fence']))
                with patch.object(runtime._settlement_journal, 'settle', side_effect=TimeoutError('lost ACK')):
                    reports = runtime.recover_completions(timeout_seconds=3, max_record_bytes=1024 * 1024)
                    self.assertTrue(any(item['state'] == 'pending' for item in reports), reports)
                self.assertEqual(runtime.kernel.get('large').state, 'queued', reports)
                self.assertTrue(runtime._diagnostics_block_admission('large'))
                reports = runtime.recover_completions(timeout_seconds=3, max_record_bytes=1024 * 1024)
                self.assertTrue(any(item['state'] == 'recorded' for item in reports), reports)
                self.assertFalse(runtime._diagnostics_block_admission('large'))
                self.assertEqual(runtime.run_once(execution_id='large').state, 'succeeded')
            finally:
                runtime.close()

    def test_lost_ack_after_independent_process_claim_is_factual_only(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'), \
             patch.object(runtime_module.Runtime, '_settlement_loop', return_value=None):
            path = Path(root) / 'kernel.sqlite'
            runtime = Kernel.open_sqlite(path, {'work': large_retry}, isolation_mode='process')
            try:
                policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     backoff_multiplier=1, max_backoff_seconds=0)
                runtime.submit(runtime.command('work', execution_id='large', idempotency_key='large',
                    correlation_id='large', timeout_seconds=30, payload={'large': True}, retry_policy=policy))
                with patch.object(runtime._settlement_journal, 'settle', side_effect=TimeoutError('lost ACK')):
                    self.assertEqual(runtime.run_once(execution_id='large').state, 'queued')
                ctx = multiprocessing.get_context('spawn')
                reader, writer = ctx.Pipe(duplex=False)
                process = ctx.Process(target=claim_in_other_process, args=(path, writer))
                process.start()
                writer.close()
                self.assertTrue(reader.poll(10))
                successor = reader.recv()
                process.join(10)
                self.assertEqual(process.exitcode, 0)
                self.assertEqual(successor['attempt'], 2)
                reports = runtime.recover_completions(timeout_seconds=3)
                self.assertTrue(any(item['state'] == 'recorded' for item in reports), reports)
                current = runtime.kernel.get('large')
                self.assertEqual((current.state, current.attempt, current.fence),
                                 ('leased', successor['attempt'], successor['fence']))
                self.assertEqual(runtime._settlement_journal.inspect('large')[0]['state'], 'recorded')
            finally:
                runtime.close()

    def test_lost_journal_ack_reconciles_exact_committed_retry(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'), \
             patch.object(runtime_module.Runtime, '_settlement_loop', return_value=None):
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.sqlite', {'work': large_retry}, isolation_mode='process')
            try:
                policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     backoff_multiplier=1, max_backoff_seconds=0)
                runtime.submit(runtime.command('work', execution_id='large', idempotency_key='large',
                    correlation_id='large', timeout_seconds=30, payload={'large': True}, retry_policy=policy))
                with patch.object(runtime._settlement_journal, 'settle', side_effect=TimeoutError('lost ACK')):
                    first = runtime.run_once(execution_id='large')
                self.assertEqual(first.state, 'queued')
                record = runtime._settlement_journal.pending()[0]
                lease = ExecutionLease.from_dict(record['lease'])
                result = ExecutionResultV2.from_dict(record['result'])
                check = runtime.kernel._is_committed_supervisor_result
                self.assertTrue(check(lease, result, timeout_seconds=1))
                with contextlib.closing(sqlite3.connect(Path(root) / 'kernel.sqlite')) as db, db:
                    command = db.execute('SELECT command_json FROM kernel_executions WHERE execution_id=?', ('large',)).fetchone()[0]
                    event = db.execute("SELECT data_json FROM kernel_events WHERE execution_id=? AND revision=? AND event_type='retry_scheduled'", ('large', lease.revision + 1)).fetchone()[0]
                    db.execute('UPDATE kernel_executions SET command_json=? WHERE execution_id=?', (command + ' ' * 2000000, 'large'))
                self.assertTrue(check(lease, result, timeout_seconds=1))
                with contextlib.closing(sqlite3.connect(Path(root) / 'kernel.sqlite')) as db, db:
                    db.execute("UPDATE kernel_events SET data_json=? WHERE execution_id=? AND revision=? AND event_type='retry_scheduled'", (event + ' ' * 300000, 'large', lease.revision + 1))
                with self.assertRaises(TimeoutError):
                    check(lease, result, timeout_seconds=1, max_record_bytes=256 * 1024)
                with contextlib.closing(sqlite3.connect(Path(root) / 'kernel.sqlite')) as db, db:
                    db.execute('UPDATE kernel_executions SET command_json=? WHERE execution_id=?', (command, 'large'))
                    db.execute("UPDATE kernel_events SET data_json=? WHERE execution_id=? AND revision=? AND event_type='retry_scheduled'", (event, 'large', lease.revision + 1))
                self.assertFalse(check(lease, replace(result, result_id='different'), timeout_seconds=1))
                self.assertFalse(check(lease, replace(result, error=replace(result.error, message='changed')), timeout_seconds=1))
                self.assertFalse(check(replace(lease, fence=lease.fence + 1), result, timeout_seconds=1))
                self.assertTrue(runtime._diagnostics_block_admission('large'))
                reports = runtime.recover_completions(timeout_seconds=3)
                self.assertTrue(any(item['state'] == 'recorded' for item in reports), reports)
                self.assertEqual(runtime._settlement_journal.inspect('large')[0]['state'], 'recorded')
                self.assertFalse(runtime._diagnostics_block_admission('large'))
                self.assertEqual(runtime.run_once(execution_id='large').state, 'succeeded')
            finally:
                runtime.close()

    def test_accepted_large_retry_runs_next_generation(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'):
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.sqlite', {'work': large_retry}, isolation_mode='process')
            try:
                policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     backoff_multiplier=1, max_backoff_seconds=0)
                runtime.submit(runtime.command('work', execution_id='large', idempotency_key='large',
                    correlation_id='large', timeout_seconds=30, payload={'large': True}, retry_policy=policy))
                first = runtime.run_once(execution_id='large')
                self.assertEqual(first.state, 'queued')
                notes = runtime._settlement_journal.inspect_notes('large')['notes']
                self.assertTrue(any(note['phase'] == 'supervisor_outcome_observed' and
                    note['evidence'].get('reason') == 'outcome_exceeds_limit' for note in notes))
                self.assertFalse(runtime._diagnostics_block_admission('large'))
                second = runtime.run_once(execution_id='large')
                self.assertEqual(second.state, 'succeeded')
                self.assertEqual(second.result.value['attempt'], 2)
            finally:
                runtime.close()

    def test_durable_settlement_releases_only_exact_handoff(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed'), \
             patch.object(runtime_module.Runtime, '_settlement_loop', return_value=None):
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.sqlite', {'work': large_retry}, isolation_mode='process')
            try:
                policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     backoff_multiplier=1, max_backoff_seconds=0)
                for key, large in (('large', True), ('other', False)):
                    runtime.submit(runtime.command('work', execution_id=key, idempotency_key=key,
                        correlation_id=key, timeout_seconds=30, payload={'large': large}, retry_policy=policy))
                journal = runtime._settlement_journal
                with patch.object(runtime.kernel, '_complete_sdk_result', side_effect=TimeoutError('test deferred Kernel settlement')):
                    first = runtime.run_once(execution_id='large')
                self.assertEqual(first.state, 'running')
                identity = journal.pending()[0]['identity']
                self.assertIn((identity['execution_id'], identity['attempt'], identity['fence']),
                              runtime._diagnostic_unknown_handoffs)
                self.assertTrue(runtime._diagnostics_block_admission('large'))
                with patch.object(runtime, 'recover_completions', return_value=()):
                    self.assertEqual(runtime.run_once(execution_id='other').state, 'succeeded')
                # A different generation and unrelated generic failure cannot be cleared.
                with runtime._diagnostic_pending_lock:
                    runtime._diagnostic_unknown_handoffs.add(('large', 99, 99))
                    runtime._diagnostic_failed_executions.add('independent-failure')
                runtime._resolve_diagnostic_handoff(type('Lease', (), {'execution_id': 'large', 'attempt': 98, 'fence': 98})())
                self.assertTrue(runtime._diagnostics_block_admission('large'))
                reports = runtime.recover_completions(timeout_seconds=3)
                self.assertTrue(any(item['state'] == 'recorded' for item in reports), reports)
                self.assertNotIn((identity['execution_id'], identity['attempt'], identity['fence']),
                                 runtime._diagnostic_unknown_handoffs)
                self.assertTrue(runtime._diagnostics_block_admission('large'))
                self.assertTrue(runtime._diagnostics_block_admission('independent-failure'))
                with runtime._diagnostic_pending_lock:
                    runtime._diagnostic_unknown_handoffs.remove(('large', 99, 99))
                    runtime._diagnostic_failed_executions.remove('independent-failure')
                second = runtime.run_once(execution_id='large')
                self.assertEqual(second.state, 'succeeded')
                self.assertEqual(second.result.value['attempt'], 2)
                self.assertNotEqual(second.result.value['pid'], os.getpid())
                obligations = runtime.kernel.inspect_supervisor_obligations('large')['obligations']
                self.assertEqual([item['state'] for item in obligations], ['resolved', 'resolved'])
                self.assertNotEqual(obligations[0]['fence'], obligations[1]['fence'])
            finally:
                runtime.close()
