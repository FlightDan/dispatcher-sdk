"""Completed child delivery observes parent authority without a writer grant."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace
from tests._acceptance_evidence import retained_directory
import unittest
from unittest.mock import patch

from dispatcher_sdk._inspection import InspectionBudgetExceeded
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope
from dispatcher_sdk.execution_kernel import child_factual_read as factual
from dispatcher_sdk.execution_kernel.children import ChildExecutionError, HandlerChildren, _RetryWindow, _retry
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

    def completed_child(self, *, failure=None):
        envelope = self.budget.derive(source='tool', origin_id='original-child-call', timeout_seconds=.5)
        command = replace(self.command, execution_id='child', idempotency_key='child', causation_id='parent')
        self.kernel.submit_child(command, self.lease, envelope)
        # Retry only transient admission within this original child-call window,
        # preserving ownership of a captured clock fact until its ACK commits.
        window = _RetryWindow(envelope, self.kernel)
        original_deadline = window.deadline
        lease = _retry(window, lambda: self.kernel.claim_and_start(
            'child-owner', execution_id='child', child_pool=True,
            timeout_seconds=window.timeout()), kernel=None)
        self.assertIsNotNone(lease)
        self.assertEqual(lease.attempt, 1)
        self.assertLessEqual(window.deadline, original_deadline)
        snapshot = self.kernel.get('child')
        # Guard ACKs promote elapsed floors into the durable logical clock;
        # a frozen raw wall sample can precede this actual claimed snapshot.
        completed_at = self.kernel.current_time()
        record = {'scenario': 'original_child_setup', 'frozen_wall': self.wall[0],
            'claimed_snapshot': snapshot.to_dict(), 'logical_completed_at': completed_at,
            'completion_clock_source': 'SQLiteKernel.current_time',
            'original_budget': envelope.to_dict(),
            'original_native_deadline': original_deadline,
            'retained_native_deadline': window.deadline}
        self.evidence['records'].append(record)
        result = ExecutionResultV2('original-child-result', 'child', 'succeeded' if failure is None else 'failed',
            lease.attempt, lease.fence, [], snapshot.started_at, completed_at,
            'root', 'parent', {'original': 42} if failure is None else None, failure)
        record['original_result'] = result.to_dict()
        self.kernel.complete(lease, result)
        row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
            'parent_attempt': self.lease.attempt, 'parent_fence': self.lease.fence,
            'child_execution_id': 'child', 'action': 'run'}
        return row, window, result

    def watermark(self):
        return self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0]

    def test_real_writer_held_beyond_original_cutoff_allows_readonly_delivery_without_clock_write(self):
        row, window, result = self.completed_child()
        original = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
        before = self.watermark()
        writer = sqlite3.connect(self.kernel.db_path, timeout=.1)
        writer.execute('BEGIN IMMEDIATE')
        statements, reader_statements, calls = [], [], []
        self.kernel._connection.set_trace_callback(statements.append)
        connect, read_floor = factual._connect_readonly, factual._read_floor
        def observe_connection(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connection.set_trace_callback(reader_statements.append)
            return connection
        def observe_floor(connection, lease, budget, **kwargs):
            calls.append(budget.deadline)
            return read_floor(connection, lease, budget, **kwargs)
        try:
            # Actual contention remains held throughout the expired original
            # child-call window and both fresh parent observations.
            original_deadline = window.deadline
            time.sleep(max(0., original_deadline - time.monotonic()) + .01)
            before_delivery = time.monotonic()
            self.evidence['records'].append({'scenario': 'held_writer_original_cutoff_aging',
                'original_native_deadline': original_deadline,
                'before_completed_result': before_delivery,
                'cutoff_has_passed': before_delivery >= original_deadline})
            with patch.object(factual, '_connect_readonly', side_effect=observe_connection), \
                    patch.object(factual, '_read_floor', side_effect=observe_floor), \
                    patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as child_read, \
                    patch.object(self.kernel, 'verify', side_effect=AssertionError('business verify invoked')):
                started = time.monotonic()
                delivered = self.children._completed_result(row, window)
                elapsed = time.monotonic() - started
            after = self.watermark()
            self.assertEqual(delivered, result.to_dict())
            self.assertEqual(before, after)
            child_read.assert_called_once()
            self.assertGreaterEqual(len(calls), 4)
            self.assertEqual(len(set(calls)), 1)
            self.assertLess(elapsed, .1)
            self.assertFalse(self.kernel._connection.in_transaction)
            self.assertFalse(any(sql.lstrip().upper().startswith(('BEGIN', 'UPDATE', 'INSERT', 'DELETE'))
                                 for sql in statements), statements)
            self.assertFalse(any(sql.lstrip().upper().startswith(('UPDATE', 'INSERT', 'DELETE'))
                                 for sql in reader_statements), reader_statements)
            self.evidence['records'].append({'scenario': 'writer_held_after_original_cutoff',
                'elapsed': elapsed, 'watermark_before': before, 'watermark_after': after,
                'parent_read_deadlines': calls, 'statements': statements,
                'readonly_statements': reader_statements,
                'original_budget': original.to_dict(), 'delivered': delivered})
        finally:
            self.kernel._connection.set_trace_callback(None)
            writer.rollback()
            writer.close()

    def test_fresh_final_parent_read_observes_actual_cancel_committed_during_child_read(self):
        row, window, _ = self.completed_child()
        original_read = factual._read_child_snapshot
        def cancel_between_reads(*args):
            result = original_read(*args)
            with SQLiteKernel(self.kernel.db_path) as other:
                other.cancel('parent', lease=self.lease, reason='concurrent parent cancellation')
            return result
        with patch.object(factual, '_read_child_snapshot', side_effect=cancel_between_reads) as child_read:
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._completed_result(row, window)
            child_read.assert_called_once()
        self.assertEqual(caught.exception.code, 'parent_authority_revoked')

    def test_shared_kernel_lock_cannot_block_independent_factual_result(self):
        row, window, result = self.completed_child()
        acquired, release = threading.Event(), threading.Event()
        def hold_control():
            with self.kernel._lock:
                acquired.set()
                release.wait(1)
        holder = threading.Thread(target=hold_control)
        holder.start()
        try:
            self.assertTrue(acquired.wait(.5))
            window._delivery_deadline = time.monotonic() + .1
            with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
                delivered = self.children._completed_result(row, window)
                read.assert_called_once()
            self.assertEqual(delivered, result.to_dict())
            self.assertLess(time.monotonic(), window._delivery_deadline)
        finally:
            release.set()
            holder.join(1)
            self.assertFalse(holder.is_alive())

    def final_sql_failure(self, *, exhaust_progress):
        row, window, _ = self.completed_child()
        time.sleep(max(0., window.deadline-time.monotonic())+.01)
        original = ChildExecutionError('child_wait_timeout',
            'child wait exhausted its inherited work window', execution_id='child')
        actual_read, actual_floor = factual._read_child_snapshot, factual._read_floor
        returned = False
        raw_errors = []
        record = {'scenario': 'actual_final_progress_timeout' if exhaust_progress else 'actual_final_permanent_sql',
            'original_proof_seconds': .1, 'original_budget': json.loads(row['budget_json'])}
        def read_once(*args):
            nonlocal returned
            snapshot = actual_read(*args)
            returned = True
            return snapshot
        def final_sql(connection, lease, budget, **kwargs):
            if not returned:
                return actual_floor(connection, lease, budget, **kwargs)
            # The actual reader's final BEGIN starts only after its sole child
            # result read. Its installed progress handler owns this deadline.
            self.assertTrue(connection.in_transaction)
            record['proof_deadline'] = budget.deadline
            try:
                if exhaust_progress:
                    connection.execute('WITH RECURSIVE work(value) AS '
                        '(VALUES(0) UNION ALL SELECT value+1 FROM work) '
                        'SELECT sum(value) FROM work').fetchone()
                else:
                    connection.execute('SELECT value FROM missing_required_authority').fetchone()
            except sqlite3.OperationalError as error:
                raw_errors.append(error)
                record['raw_type'] = type(error).__name__
                record['raw_message'] = str(error)
                record['sqlite_errorcode'] = getattr(error, 'sqlite_errorcode', None)
                record['stopped_reason'] = budget.stopped_reason
                raise
            self.fail('actual proof SQL unexpectedly completed')
        try:
            with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                    patch.object(self.children.store, 'attach'), \
                    patch.object(self.children, '_await_window', side_effect=original), \
                    patch.object(factual, '_read_child_snapshot', side_effect=read_once) as read, \
                    patch.object(factual, '_read_floor', side_effect=final_sql):
                started = time.monotonic()
                expected = ChildExecutionError if exhaust_progress else sqlite3.OperationalError
                with self.assertRaises(expected) as caught:
                    self.children._await(row)
                record['elapsed'] = time.monotonic()-started
                record['read_calls'] = read.call_count
                read.assert_called_once()
            self.assertEqual(len(raw_errors), 1)
            if exhaust_progress:
                self.assertIs(caught.exception, original)
                self.assertIsInstance(caught.exception.__cause__, InspectionBudgetExceeded)
                self.assertIs(caught.exception.__cause__.__cause__, raw_errors[0])
                self.assertEqual(record['stopped_reason'], 'timeout')
                self.assertGreaterEqual(time.monotonic(), record['proof_deadline'])
                code = getattr(raw_errors[0], 'sqlite_errorcode', None)
                if code is not None:
                    self.assertEqual(code & 255, sqlite3.SQLITE_INTERRUPT)
                else:
                    self.assertEqual(str(raw_errors[0]), 'interrupted')
            else:
                self.assertIs(caught.exception, raw_errors[0])
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(record['stopped_reason'])
                self.assertIn('no such table', str(caught.exception))
            self.assertLess(record['elapsed'], .2)
            self.assertIsNone(window._delivery_deadline)
        finally:
            self.evidence['records'].append(record)

    def test_real_final_progress_timeout_keeps_original_wait_and_interrupt_after_one_child_read(self):
        self.final_sql_failure(exhaust_progress=True)

    def test_real_final_permanent_sql_error_remains_raw_after_one_child_read(self):
        self.final_sql_failure(exhaust_progress=False)

    def test_cancelled_and_revoked_parent_are_excluded_before_child_read(self):
        row, window, _ = self.completed_child()
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                self.children.parent_lease = (self.lease if cancelled else
                    replace(self.lease, lease_id='revoked-lease'))
                if cancelled:
                    self.kernel.cancel('parent', lease=self.lease, reason='parent cancelled')
                with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as child_read:
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
        with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as child_read:
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
