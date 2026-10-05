"""A failed bounded proof retains its raw cause behind the original wait error."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel import child_factual_read as factual
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope
from dispatcher_sdk.execution_kernel.children import ChildExecutionError, HandlerChildren
from dispatcher_sdk.execution_kernel.children import _RetryWindow
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, ExecutionResultV2, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ObservationJournal


class ChildDeliveryDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-child-delivery-diagnostics-')
        self.kernel = SQLiteKernel(self.root/'kernel.sqlite3')
        self.addCleanup(self.kernel.close)
        self.command = ExecutionCommandV2('parent', 'parent', 'diagnostic-proof', 'root', None,
            'parent', 1, RetryPolicy(), 5, {})
        self.kernel.submit(self.command)
        self.lease = self.kernel.claim_and_start('owner', execution_id='parent')
        budget = self.kernel.prepare_execution_budget(self.lease).enter_handler(
            5, origin_id='execution:parent')
        self.budget = self.kernel.confirm_handler_entry(self.lease, budget)
        journal = ObservationJournal(self.root/'observations.sqlite3',
            kernel_path=self.kernel.db_path, source_id='diagnostic-host')
        self.children = HandlerChildren(self.kernel, self.command, self.lease, self.budget,
            {'capacity': 1, 'max_depth': 1}, journal=journal)
        # These propagation tests start after checkpoint attachment and an
        # already spent original window; they grant no new business time.
        envelope = self.budget.derive(source='tool', origin_id='original-call',
            deadline_at=time.time()-.01)
        self.row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
            'parent_attempt': self.lease.attempt, 'parent_fence': self.lease.fence,
            'child_execution_id': 'missing-child', 'action': 'observe'}
        self.original = ChildExecutionError('child_wait_timeout',
            'child wait exhausted its inherited work window', execution_id='missing-child')
        self.evidence = {'test': self.id(), 'interpreter': sys.executable,
            'kernel_path': self.kernel.db_path, 'original_budget': json.loads(self.row['budget_json']),
            'records': []}

    def tearDown(self):
        path = self.root/'evidence.json'
        path.write_text(json.dumps(self.evidence, indent=2), encoding='utf-8')
        print('child_delivery_diagnostics_evidence=' + str(path), flush=True)

    def await_after_attachment(self):
        return self.children._await(self.row)

    def admit_actual_child(self):
        child_id = self.row['child_execution_id']
        command = replace(self.command, execution_id=child_id, idempotency_key=child_id,
                          causation_id='parent')
        budget = self.budget.derive(source='tool', origin_id='actual-diagnostic-child', timeout_seconds=1)
        self.kernel.submit_child(command, self.lease, budget)
        lease = self.kernel.claim_and_start('child-owner', execution_id=child_id, child_pool=True)
        snapshot = self.kernel.get(child_id)
        result = ExecutionResultV2('diagnostic-child-result', child_id, 'succeeded', lease.attempt,
            lease.fence, [], snapshot.started_at, self.kernel.current_time(), 'root', 'parent', 42, None)
        self.kernel.complete(lease, result)

    def test_real_kernel_lock_timeout_is_cause_of_the_identical_original_wait_error(self):
        # A custom Kernel deliberately retains the shared-connection fallback.
        # Standard file-backed factual reads have independent-lock coverage.
        class CustomSQLiteKernel(SQLiteKernel):
            pass
        self.kernel = CustomSQLiteKernel(self.kernel.db_path)
        self.addCleanup(self.kernel.close)
        self.children.kernel = self.kernel
        # This case starts after initial clock reconstruction and attachment.
        # Hold the lock only during the original wait's factual delivery proof.
        window = _RetryWindow(BudgetEnvelope.from_dict(json.loads(self.row['budget_json'])),
                              self.kernel, execution_id=self.row['parent_execution_id'])
        acquired, release = threading.Event(), threading.Event()
        def hold_control():
            with self.kernel._lock:
                acquired.set()
                release.wait(1)
        holder = threading.Thread(target=hold_control)
        holder.start()
        self.assertTrue(acquired.wait(.5))
        original_budget = self.row['budget_json']
        actual_proof = self.children._completed_result
        try:
            with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                    patch.object(self.children.store, 'attach'), \
                    patch.object(self.children, '_await_window', side_effect=self.original), \
                    patch.object(self.children, '_completed_result', wraps=actual_proof) as proof:
                before = time.monotonic()
                with self.assertRaises(ChildExecutionError) as caught:
                    self.await_after_attachment()
                elapsed = time.monotonic()-before
                cause = caught.exception.__cause__
                self.evidence['records'].append({'scenario': 'actual_kernel_control_lock_timeout',
                    'elapsed': elapsed, 'proof_calls': proof.call_count,
                    'outer_type': type(caught.exception).__name__, 'outer_code': caught.exception.code,
                    'outer_message': str(caught.exception), 'cause_type': type(cause).__name__,
                    'cause_message': str(cause)})
                self.assertIs(caught.exception, self.original)
                self.assertEqual(caught.exception.code, 'child_wait_timeout')
                self.assertEqual(str(caught.exception), 'child wait exhausted its inherited work window')
                cause = caught.exception.__cause__
                self.assertIsInstance(cause, TimeoutError)
                self.assertEqual(str(cause), 'Kernel control lock admission timed out')
                self.assertEqual(proof.call_count, 1)
                self.assertGreaterEqual(elapsed, .09)
                self.assertLess(elapsed, .3)
                self.assertEqual(self.row['budget_json'], original_budget)

        finally:
            release.set()
            holder.join(1)
            self.assertFalse(holder.is_alive())

    def actual_sqlite_busy(self):
        path = self.root/'contended-read.sqlite3'
        writer = sqlite3.connect(path, timeout=.01)
        writer.execute('CREATE TABLE control(value INTEGER)')
        writer.commit()
        reader = sqlite3.connect(path, timeout=.01)
        writer.execute('BEGIN EXCLUSIVE')
        try:
            try:
                reader.execute('SELECT * FROM control').fetchall()
            except sqlite3.OperationalError as error:
                self.assertEqual(str(error), 'database is locked')
                if hasattr(error, 'sqlite_errorcode'):
                    self.assertEqual(error.sqlite_errorcode, sqlite3.SQLITE_BUSY)
                return error
            self.fail('real exclusive writer did not block its reader')
        finally:
            writer.rollback()
            reader.close()
            writer.close()

    def test_real_sqlite_busy_code_and_object_are_retained_without_proof_retry(self):
        self.admit_actual_child()
        raw = self.actual_sqlite_busy()
        actual_proof = self.children._completed_result
        with patch.object(self.children.store, 'attach'), \
                patch.object(self.children, '_await_window', side_effect=self.original), \
                patch.object(factual, '_read_child_snapshot', side_effect=raw) as read, \
                patch.object(self.children, '_completed_result', wraps=actual_proof) as proof:
            with self.assertRaises(ChildExecutionError) as caught:
                self.await_after_attachment()
            self.evidence['records'].append({'scenario': 'actual_sqlite_busy_cause',
                'proof_calls': proof.call_count, 'read_calls': read.call_count,
                'outer_code': caught.exception.code, 'outer_message': str(caught.exception),
                'cause_type': type(raw).__name__, 'cause_message': str(raw),
                'sqlite_errorcode': getattr(raw, 'sqlite_errorcode', None),
                'sqlite_errorname': getattr(raw, 'sqlite_errorname', None)})
            self.assertIs(caught.exception, self.original)
            self.assertIs(caught.exception.__cause__, raw)
            if hasattr(raw, 'sqlite_errorcode'):
                self.assertEqual(raw.sqlite_errorcode, sqlite3.SQLITE_BUSY)
                self.assertEqual(raw.sqlite_errorname, 'SQLITE_BUSY')
            self.assertEqual(proof.call_count, 1)
            self.assertEqual(read.call_count, 1)


    def test_no_proved_child_preserves_original_error_without_secondary_cause(self):
        with patch.object(self.children.store, 'attach'), \
                patch.object(self.children, '_await_window', side_effect=self.original):
            with self.assertRaises(ChildExecutionError) as caught:
                self.await_after_attachment()
        self.assertIs(caught.exception, self.original)
        self.assertIsNone(caught.exception.__cause__)

    def test_permanent_proof_error_propagates_instead_of_becoming_wait_error(self):
        self.admit_actual_child()
        permanent = sqlite3.OperationalError('no such table: required_authority')
        with patch.object(self.children.store, 'attach'), \
                patch.object(self.children, '_await_window', side_effect=self.original), \
                patch.object(factual, '_read_child_snapshot', side_effect=permanent):
            with self.assertRaises(sqlite3.OperationalError) as caught:
                self.await_after_attachment()
        self.assertIs(caught.exception, permanent)
        self.assertIsNone(permanent.__cause__)

    def test_actual_parent_cancellation_keeps_revocation_behavior(self):
        self.kernel.cancel('parent', lease=self.lease, reason='actual parent revoked')
        with patch.object(self.children.store, 'attach'), \
                patch.object(self.children, '_await_window', side_effect=self.original), \
                patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
            with self.assertRaises(ChildExecutionError) as caught:
                self.await_after_attachment()
        self.assertEqual(caught.exception.code, 'parent_authority_revoked')
        self.assertIsNot(caught.exception, self.original)
        read.assert_not_called()

    def test_public_kernel_result_preserves_original_wait_error_and_bounded_sqlite_cause(self):
        raw = self.actual_sqlite_busy()
        calls = []

        def handler(payload, context):
            calls.append(context.command.execution_id)
            raise self.original from raw

        handler.__execution_kernel_revision__ = 'child-delivery-diagnostic-v1'
        with Kernel.open_sqlite(self.root/'public-runtime.sqlite3', {'parent': handler},
                               isolation_mode='thread') as runtime:
            runtime.submit(runtime.command('parent', execution_id='public-parent',
                idempotency_key='public-parent', correlation_id='diagnostic-proof',
                timeout_seconds=5, payload={}))
            outcome = runtime.run_once(execution_id='public-parent')
            self.evidence['records'].append({'scenario': 'public_runtime_normalization',
                'calls': calls, 'authoritative_parent_result': outcome.result.to_dict()})
            self.assertEqual(outcome.state, 'failed')
            self.assertEqual(calls, ['public-parent'])
            self.assertEqual(outcome.result.error.code, self.original.code)
            self.assertEqual(outcome.result.error.message, str(self.original))
            details = outcome.result.error.details
            self.assertEqual(details['child_execution_id'], 'missing-child')
            self.assertIsNone(details['child_result'])
            self.assertEqual(details['cause']['cause'], 'OperationalError')
            self.assertEqual(details['cause']['error'], str(raw))
            if hasattr(raw, 'sqlite_errorcode'):
                self.assertEqual(details['cause']['sqlite_errorcode'], raw.sqlite_errorcode)
            else:
                self.assertNotIn('sqlite_errorcode', details['cause'])
            self.assertFalse(details['cause']['error_truncated'])
            self.assertLessEqual(len(details['cause']['error'].encode('utf-8')), 4096)
            self.assertEqual(runtime.kernel.get('public-parent').result.to_dict(), outcome.result.to_dict())



if __name__ == '__main__':
    unittest.main()
