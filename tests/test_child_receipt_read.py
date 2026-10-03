"""Real receipt read admission retries keep original authority and clock floors."""
import json
from pathlib import Path
import sqlite3
import threading
import time
from unittest.mock import patch
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope
from dispatcher_sdk.execution_kernel.children import _RetryWindow
from dispatcher_sdk.execution_kernel.settlement import SettlementBusyError
from tests import test_child_clock_checkpoint as checkpoint_fixture
from tests import test_observability_runtime_integration as runtime_fixture


class ChildReceiptReadTests(checkpoint_fixture.ChildClockCheckpointTests):
    def short_row(self, seconds):
        envelope = self.parent_budget.derive(source='tool', origin_id='receipt-read', timeout_seconds=seconds)
        window = _RetryWindow(envelope, self.kernel)
        row = self.children._enqueue(request_id='receipt-read', child_id='receipt-child', action='run',
            child_command=self.command('receipt-child'), envelope=envelope, window=window)
        return row, window

    def exclusive_writer(self):
        connection = sqlite3.connect(self.facts.path, timeout=.1, check_same_thread=False)
        connection.execute('BEGIN EXCLUSIVE')
        return connection

    def test_actual_receipt_contention_retries_inside_same_window_and_enforces_stronger_floor(self):
        from dataclasses import replace
        row, window = self.short_row(1)
        original = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
        narrowed = replace(original, checkpoint=replace(original.checkpoint,
            wall_at=original.checkpoint.wall_at + .3))
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'wait_id': row['wait_id'], 'budget_envelope': narrowed.to_dict()})
        writer = self.exclusive_writer()
        def unlock():
            time.sleep(.25)
            writer.rollback()
            writer.close()
        release = threading.Thread(target=unlock)
        release.start()
        before = time.monotonic()
        original_facts = self.children.store._facts
        try:
            with patch.object(self.children.store, '_facts', wraps=original_facts) as reads:
                self.children.store.attach(row, window)
                attempts = reads.call_count
        finally:
            release.join(1)
        elapsed = time.monotonic() - before
        remaining = window.remaining()
        original_remaining = original.view(sample=self.kernel_clock()).remaining_work_seconds
        self.assertGreaterEqual(attempts, 2)
        self.assertGreaterEqual(elapsed, .20)
        self.assertLess(elapsed, 1)
        self.assertGreater(remaining, 0)
        self.assertLess(remaining, original_remaining - .25)
        self.assertEqual(window.envelope.constraints, original.constraints)
        self.evidence['records'].append({'scenario': 'receipt_writer_released_before_original_cutoff',
            'read_attempts': attempts, 'elapsed': elapsed, 'original_remaining': original_remaining,
            'enforced_remaining': remaining, 'original_constraints': original.to_dict()['constraints'],
            'retained_floor': window.envelope.to_dict()})

    def kernel_clock(self):
        from dispatcher_sdk.execution_kernel.budget import sample_clock
        return sample_clock(wall_time=self.kernel._wall_time())

    def test_persistent_receipt_contention_expires_without_completed_result_rescue(self):
        import traceback

        row, window = self.short_row(.3)
        original = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
        writer = self.exclusive_writer()
        before = time.monotonic()
        try:
            with patch.object(self.children, '_completed_result') as rescue:
                remaining_at_call = window.remaining()
                window_at_call = window.envelope.to_dict()
                deadline_at_call = window.deadline
                caught, returned, raw_traceback = None, None, None
                try:
                    returned = self.children._await(row)
                except Exception as error:
                    caught, raw_traceback = error, traceback.format_exc()
                elapsed = time.monotonic() - before
                remaining_at_end = window.remaining()
                row_budget_at_end = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
                self.evidence['records'].append({'scenario': 'persistent_receipt_contention',
                    'elapsed': elapsed, 'began': before,
                    'remaining_at_call': remaining_at_call, 'remaining_at_end': remaining_at_end,
                    'original_deadline_at_call': deadline_at_call,
                    'error_type': None if caught is None else type(caught).__name__,
                    'error': None if caught is None else str(caught), 'traceback': raw_traceback,
                    'sqlite_errorcode': getattr(caught, 'sqlite_errorcode', None), 'returned': returned,
                    'completed_result_rescue_calls': rescue.call_count,
                    'writer_in_transaction': writer.in_transaction,
                    'original_budget': original.to_dict(), 'window_at_call': window_at_call,
                    'window_at_end': window.envelope.to_dict(), 'row_budget_at_end': row_budget_at_end.to_dict()})
                # Setup already spent part of the original .3-second window.
                # Exhaustion, rather than a new minimum wait, is the contract.
                self.assertIsInstance(caught, SettlementBusyError)
                rescue.assert_not_called()
                self.assertEqual(remaining_at_end, 0)
                self.assertEqual(window.envelope.constraints, original.constraints)
                self.assertEqual(row_budget_at_end.constraints, original.constraints)
                self.assertTrue(writer.in_transaction)
                self.assertLess(elapsed, .6)
        finally:
            writer.rollback()
            writer.close()

    def test_missing_checkpoint_facts_are_unknown_without_rescue(self):
        row, window = self.short_row(1)
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'budget_envelope': window.envelope.to_dict()})
        with patch.object(self.children, '_completed_result') as rescue:
            with self.assertRaises(BudgetClockUnknownError):
                self.children._await(row)
            rescue.assert_not_called()

    def test_expired_wait_with_actual_reaped_parent_keeps_revocation_without_receipt_read(self):
        from dispatcher_sdk.execution_kernel.children import ChildExecutionError
        row, window = self.short_row(.2)
        original = json.loads(row['budget_json'])
        # Reaping is an actual persisted parent transition after the original
        # window has been spent, as in controller crash recovery.
        self.wall[0] = self.lease.expires_at + 1
        self.kernel.reap()
        watermark = self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0]
        with patch.object(self.children, '_completed_result') as rescue, \
                patch.object(self.children.store, '_facts') as facts:
            before = time.monotonic()
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._await(row)
            elapsed = time.monotonic() - before
            self.assertEqual(caught.exception.code, 'parent_authority_revoked')
            self.assertLess(elapsed, .1)
            rescue.assert_not_called()
            facts.assert_not_called()
        self.assertEqual(self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0], watermark)
        self.assertEqual(json.loads(row['budget_json']), original)
        self.evidence['records'].append({'scenario': 'expired_wait_actual_reaped_parent',
            'elapsed': elapsed, 'error': str(caught.exception), 'code': caught.exception.code,
            'original_budget': original, 'watermark': watermark,
            'receipt_read_calls': facts.call_count, 'completed_result_rescue_calls': rescue.call_count})

    def test_other_wait_checkpoint_does_not_require_the_current_wait_envelope(self):
        row, window = self.short_row(1)
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'wait_id': 'different-historical-wait'})
        self.children.store.attach(row, window)
        self.assertGreater(window.remaining(), .5)
        self.evidence['records'].append({'scenario': 'unrelated_wait_history',
            'remaining': window.remaining(), 'original_wait_id': row['wait_id']})

    def test_current_wait_missing_envelope_facts_remain_unknown(self):
        row, window = self.short_row(1)
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'wait_id': row['wait_id']})
        with patch.object(self.children, '_completed_result') as rescue:
            with self.assertRaises(BudgetClockUnknownError):
                self.children._await(row)
            rescue.assert_not_called()

    def test_current_wait_byte_truncation_remains_unknown(self):
        row, window = self.short_row(1)
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'wait_id': row['wait_id'],
                'budget_envelope': window.envelope.to_dict(), 'padding': 'x'*300000})
        with patch.object(self.children, '_completed_result') as rescue:
            with self.assertRaises(BudgetClockUnknownError):
                self.children._await(row)
            rescue.assert_not_called()

    def test_actual_parent_cancellation_interrupts_receipt_retry_before_original_cutoff(self):
        from dispatcher_sdk.execution_kernel.children import ChildExecutionError
        row, window = self.short_row(1)
        writer = self.exclusive_writer()
        errors = []
        def await_child():
            try:
                self.children._await(row)
            except BaseException as error:
                errors.append(error)
        reader = threading.Thread(target=await_child)
        before = time.monotonic()
        with patch.object(self.children, '_completed_result') as rescue:
            try:
                reader.start()
                time.sleep(.15)
                self.kernel.cancel(self.parent.execution_id, lease=self.lease, reason='real parent cancellation')
                reader.join(.5)
                elapsed = time.monotonic() - before
                self.assertFalse(reader.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], ChildExecutionError)
                self.assertEqual(errors[0].code, 'parent_authority_revoked')
                self.assertLess(elapsed, .7)
                rescue.assert_not_called()
                self.evidence['records'].append({'scenario': 'cancel_during_receipt_exclusive_lock',
                    'elapsed': elapsed, 'error_type': type(errors[0]).__name__,
                    'code': errors[0].code, 'error': str(errors[0]), 'original_budget': json.loads(row['budget_json'])})
            finally:
                writer.rollback()
                writer.close()
                reader.join(1)

    def test_original_public_parent_process_child_fixture(self):
        runtime_fixture.RuntimeObservationIntegrationTests().execute('process')


if __name__ == '__main__':
    unittest.main()
