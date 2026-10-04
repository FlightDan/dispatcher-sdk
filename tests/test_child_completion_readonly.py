"""Completed child delivery observes parent authority without a writer grant."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace
from tests._acceptance_evidence import retained_directory
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope
from dispatcher_sdk.execution_kernel.children import ChildExecutionError, HandlerChildren, _RetryWindow
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, ExecutionResultV2, RetryPolicy
from dispatcher_sdk.execution_kernel.errors import StaleFenceError, StorageIsolationError
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ObservationJournal


class ChildCompletionReadonlyTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-child-completion-readonly-')
        self.wall = [time.time()]
        self.kernel = SQLiteKernel(self.root/'kernel.sqlite3', now=lambda: self.wall[0])
        self.addCleanup(self.kernel.close)
        self.command = ExecutionCommandV2('parent', 'parent', 'readonly-proof', 'root', None,
            'parent', 1, RetryPolicy(), 5, {})
        self.kernel.submit(self.command)
        self.lease = self.kernel.claim_and_start('owner', execution_id='parent')
        budget = self.kernel.prepare_execution_budget(self.lease).enter_handler(
            5, origin_id='execution:parent')
        self.budget = self.kernel.confirm_handler_entry(self.lease, budget)
        journal = ObservationJournal(self.root/'observations.sqlite3',
            kernel_path=self.kernel.db_path, source_id='readonly-host')
        self.children = HandlerChildren(self.kernel, self.command, self.lease, self.budget,
            {'capacity': 1, 'max_depth': 1}, journal=journal)
        self.evidence = {'test': self.id(), 'python': sys.executable,
            'kernel_path': self.kernel.db_path, 'records': []}

    def tearDown(self):
        path = self.root/'evidence.json'
        path.write_text(json.dumps(self.evidence, indent=2), encoding='utf-8')
        print('child_completion_readonly_evidence=' + str(path), flush=True)

    def completed_child(self):
        envelope = self.budget.derive(source='tool', origin_id='original-child-call', timeout_seconds=.5)
        command = replace(self.command, execution_id='child', idempotency_key='child', causation_id='parent')
        self.kernel.submit_child(command, self.lease, envelope)
        lease = self.kernel.claim_and_start('child-owner', execution_id='child', child_pool=True)
        snapshot = self.kernel.get('child')
        result = ExecutionResultV2('original-child-result', 'child', 'succeeded',
            lease.attempt, lease.fence, [], snapshot.started_at, self.wall[0],
            'root', 'parent', {'original': 42}, None)
        self.kernel.complete(lease, result)
        row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
            'parent_attempt': self.lease.attempt, 'parent_fence': self.lease.fence,
            'child_execution_id': 'child', 'action': 'run'}
        return row, _RetryWindow(envelope, self.kernel), result

    def watermark(self):
        return self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0]

    def test_real_writer_held_beyond_original_cutoff_allows_readonly_delivery_without_clock_write(self):
        row, window, result = self.completed_child()
        original = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
        before = self.watermark()
        writer = sqlite3.connect(self.kernel.db_path, timeout=.1)
        writer.execute('BEGIN IMMEDIATE')
        statements, calls = [], []
        self.kernel._connection.set_trace_callback(statements.append)
        readonly = self.kernel._verify_active_lease_readonly
        def observe(lease):
            calls.append(self.kernel._control_deadline)
            return readonly(lease)
        try:
            # Actual contention remains held throughout the expired original
            # child-call window and both fresh parent observations.
            time.sleep(window.remaining() + .01)
            with patch.object(self.kernel, '_verify_active_lease_readonly', side_effect=observe), \
                    patch.object(self.kernel, 'verify', side_effect=AssertionError('business verify invoked')):
                started = time.monotonic()
                delivered = self.children._completed_result(row, window)
                elapsed = time.monotonic() - started
            after = self.watermark()
            self.assertEqual(delivered, result.to_dict())
            self.assertEqual(before, after)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0], calls[1])
            self.assertLess(elapsed, .1)
            self.assertFalse(self.kernel._connection.in_transaction)
            self.assertFalse(any(sql.lstrip().upper().startswith(('BEGIN', 'UPDATE', 'INSERT', 'DELETE'))
                                 for sql in statements), statements)
            self.evidence['records'].append({'scenario': 'writer_held_after_original_cutoff',
                'elapsed': elapsed, 'watermark_before': before, 'watermark_after': after,
                'parent_read_deadlines': calls, 'statements': statements,
                'original_budget': original.to_dict(), 'delivered': delivered})
        finally:
            self.kernel._connection.set_trace_callback(None)
            writer.rollback()
            writer.close()

    def test_fresh_final_parent_read_observes_actual_cancel_committed_during_child_read(self):
        row, window, _ = self.completed_child()
        original_get = self.kernel.get
        def cancel_between_reads(execution_id):
            result = original_get(execution_id)
            with SQLiteKernel(self.kernel.db_path) as other:
                other.cancel('parent', lease=self.lease, reason='concurrent parent cancellation')
            return result
        with patch.object(self.kernel, 'get', side_effect=cancel_between_reads):
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._completed_result(row, window)
        self.assertEqual(caught.exception.code, 'parent_authority_revoked')

    def test_cancelled_and_revoked_parent_are_excluded_before_child_read(self):
        row, window, _ = self.completed_child()
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                self.children.parent_lease = (self.lease if cancelled else
                    replace(self.lease, lease_id='revoked-lease'))
                if cancelled:
                    self.kernel.cancel('parent', lease=self.lease, reason='parent cancelled')
                with patch.object(self.kernel, 'get', wraps=self.kernel.get) as child_read:
                    with self.assertRaises(ChildExecutionError) as caught:
                        self.children._completed_result(row, window)
                    self.assertEqual(caught.exception.code, 'parent_authority_revoked')
                    child_read.assert_not_called()

    def test_expired_parent_uses_durable_watermark_even_after_wall_rollback(self):
        row, window, _ = self.completed_child()
        self.wall[0] = self.lease.expires_at + 1
        with self.assertRaises(StaleFenceError):
            self.kernel.verify(self.lease)
        advanced = self.watermark()
        self.wall[0] = self.budget.checkpoint.wall_at
        with patch.object(self.kernel, 'get', wraps=self.kernel.get) as child_read:
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._completed_result(row, window)
            self.assertEqual(caught.exception.code, 'parent_authority_revoked')
            child_read.assert_not_called()
        self.assertEqual(self.watermark(), advanced)

    def test_readonly_helper_rejects_retained_transaction_and_inherits_control_expiry(self):
        self.kernel._connection.execute('BEGIN')
        try:
            with self.assertRaises(StorageIsolationError):
                self.kernel._verify_active_lease_readonly(self.lease)
        finally:
            self.kernel._connection.rollback()
        before = self.watermark()
        clock = [time.monotonic()]
        control_clock = SimpleNamespace(**{**vars(time), 'monotonic': lambda: clock[0]})
        with patch('dispatcher_sdk.execution_kernel._sqlite_base.time', control_clock):
            with self.kernel._control_lock(.005):
                # A short real sleep need not cross a coarse monotonic tick.
                # Advance the original caller's clock beyond its same cutoff.
                clock[0] += .01
                with self.assertRaises(TimeoutError):
                    self.kernel._verify_active_lease_readonly(self.lease)
        self.assertEqual(self.watermark(), before)


if __name__ == '__main__':
    unittest.main()
