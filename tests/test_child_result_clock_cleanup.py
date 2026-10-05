"""Factual child delivery borrows exact captured facts without publishing them."""
import json
from dataclasses import replace
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import child_factual_read as factual
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture
from dispatcher_sdk.execution_kernel.children import HandlerChildren
from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests import test_child_completion_readonly as readonly_fixture


class ChildResultClockCleanupTests(unittest.TestCase):
    setUp = readonly_fixture.ChildCompletionReadonlyTests.setUp
    tearDown = readonly_fixture.ChildCompletionReadonlyTests.tearDown
    completed_child = readonly_fixture.ChildCompletionReadonlyTests.completed_child

    def captured_wait(self, *, different_owner=False, foreign_kernel=None, context_owner=False, failure=None):
        row, window, result = self.completed_child(failure=failure)
        context = None
        if context_owner:
            context = HandlerContext(self.command, self.lease,
                HandlerEffects(self.kernel, self.lease, lambda: True),
                budget_envelope=self.budget, service_spec={'guard_budget': True})
            context._enter_handler()
            self.children = HandlerChildren(self.kernel, self.command, self.lease,
                self.budget, {'capacity': 1, 'max_depth': 1},
                journal=self.children.store.journal, _budget_context=context)
        writer = sqlite3.connect(self.kernel.db_path, timeout=.1)
        self.addCleanup(writer.close)
        self.addCleanup(writer.rollback)
        owner = (context._budget_capture if context is not None else
            _KernelBudgetCapture(foreign_kernel or self.kernel, 'parent')
            if different_owner else window._capture)
        captured = owner._captured

        def hold_after_capture(token, envelope):
            captured(token, envelope)
            writer.execute('BEGIN IMMEDIATE')

        with patch.object(owner, '_captured', side_effect=hold_after_capture):
            with self.assertRaises((sqlite3.OperationalError, TimeoutError)) as caught:
                owner(window.envelope, timeout_seconds=.02)
        original = caught.exception
        if not different_owner and not context_owner:
            window._adopt_sample_owner(original)
        token, fact = owner._pending
        self.assertIsNotNone(fact)
        time.sleep(max(0., window.deadline-time.monotonic())+.01)
        self.evidence['records'].append({'scenario': 'expired_captured_owner',
            'different_registered_owner': different_owner, 'explicit_context_owner': context_owner,
            'token': token, 'captured': fact.to_dict(),
            'original_error': str(original), 'original_budget': json.loads(row['budget_json']),
            'original_native_deadline': window.deadline})
        return row, window, result, writer, original, token

    def await_expired(self, row, window, original):
        with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                patch.object(self.children.store, 'attach'), \
                patch.object(self.children, '_await_window', side_effect=original):
            return self.children._await(row)

    def assert_borrowed_delivery(self, row, window, result, original, token):
        owner = self.kernel._budget_sample_owners[token]
        pending = owner._pending
        watermark = self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0]
        actual_rescue = self.children._completed_result
        def rescue_without_wall_sample(*args, **kwargs):
            # Entry's fresh parent-authority check remains real. Only factual
            # result proof must avoid observing another wall-clock sample.
            with patch.object(self.kernel, '_wall_time', side_effect=AssertionError('new wall observation')):
                return actual_rescue(*args, **kwargs)
        with patch.object(self.kernel, '_sample_budget', side_effect=AssertionError('new sample')), \
                patch.object(self.kernel, '_finish_budget_sample', side_effect=AssertionError('guard ACK')), \
                patch.object(self.kernel, '_drain_budget_samples', side_effect=AssertionError('guard drain')), \
                patch.object(self.kernel, 'claim_and_start', side_effect=AssertionError('business replay')), \
                patch.object(self.children, '_completed_result', side_effect=rescue_without_wall_sample) as rescue, \
                patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
            started = time.monotonic()
            delivered = self.await_expired(row, window, original)
            elapsed = time.monotonic()-started
        read.assert_called_once()
        rescue.assert_called_once()
        self.assertEqual(delivered, result.to_dict())
        self.assertLess(elapsed, .1)
        self.assertIs(owner._pending, pending)
        self.assertIs(self.kernel._budget_sample_owners[token], owner)
        self.assertEqual(self.kernel._connection.execute(
            'SELECT token FROM kernel_budget_samples WHERE token=?', (token,)).fetchone()[0], token)
        self.assertEqual(self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0], watermark)
        self.assertEqual(window.envelope.constraints,
            BudgetEnvelope.from_dict(json.loads(row['budget_json'])).constraints)
        self.evidence['records'].append({'scenario': 'borrowed_exact_fact_with_writer_held',
            'elapsed': elapsed, 'delivered': delivered, 'token': token,
            'guard_retained': True, 'owner_tuple_retained': True, 'watermark': watermark})

    def test_exact_wait_capture_delivers_under_held_writer_without_ack_or_resampling(self):
        row, window, result, _, original, token = self.captured_wait()
        self.assert_borrowed_delivery(row, window, result, original, token)

    def test_actual_imported_owner_tuple_delivers_without_registry_discovery(self):
        row, window, result, _, original, token = self.captured_wait(different_owner=True)
        owner = self.kernel._budget_sample_owners[token]
        window._adopt_sample_owner(original)
        self.assertIs(window._pending_sample_owner, owner)
        self.assertIs(window._pending_sample, owner._pending)
        self.assertIsNone(window._capture._pending)
        self.assert_borrowed_delivery(row, window, result, original, token)

    def test_explicit_real_context_capture_delivers_without_ack(self):
        row, window, result, _, original, token = self.captured_wait(context_owner=True)
        self.assertIsInstance(self.children._budget_context, HandlerContext)
        self.assertIsNone(window._capture._pending)
        self.assert_borrowed_delivery(row, window, result, original, token)

    def test_registry_only_owner_and_copied_imported_tuple_remain_foreign(self):
        row, window, _, _, original, token = self.captured_wait(different_owner=True)
        owner = self.kernel._budget_sample_owners[token]
        other_context = HandlerContext(self.command, self.lease,
            HandlerEffects(self.kernel, self.lease, lambda: True), budget_envelope=self.budget)
        other_context._budget_capture = owner
        self.assertIsNone(self.children._budget_context)
        self.assertIs(other_context._budget_capture, owner)
        for imported_copy in (False, True):
            with self.subTest(imported_copy=imported_copy):
                if imported_copy:
                    window._pending_sample_owner = owner
                    window._pending_sample = (owner._pending[0], owner._pending[1])
                    self.assertIsNot(window._pending_sample, owner._pending)
                with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
                    with self.assertRaises(type(original)) as caught:
                        self.await_expired(row, window, original)
                self.assertIs(caught.exception, original)
                self.assertIsInstance(caught.exception.__cause__, BudgetClockUnknownError)
                read.assert_not_called()
                self.assertEqual(self.kernel._connection.execute(
                    'SELECT token FROM kernel_budget_samples WHERE token=?', (token,)).fetchone()[0], token)

    def test_result_read_spends_same_proof_window_without_ack_or_second_read(self):
        row, window, _, _, original, token = self.captured_wait()
        actual_read = factual._read_child_snapshot
        def read_then_spend_remaining(*args):
            snapshot = actual_read(*args)
            deadline = window._delivery_deadline
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(remaining)
            return snapshot
        with patch.object(factual, '_read_child_snapshot', side_effect=read_then_spend_remaining) as read:
            started = time.monotonic()
            with self.assertRaises(type(original)) as caught:
                self.await_expired(row, window, original)
            elapsed = time.monotonic()-started
        self.assertIs(caught.exception, original)
        from dispatcher_sdk._inspection import InspectionBudgetExceeded
        self.assertIsInstance(caught.exception.__cause__, InspectionBudgetExceeded)
        read.assert_called_once()
        self.assertLess(elapsed, .2)
        self.assertIsNotNone(self.kernel._connection.execute(
            'SELECT token FROM kernel_budget_samples WHERE token=?', (token,)).fetchone())
        self.assertIsNone(window._delivery_deadline)

    def test_finish_only_publication_remains_a_separate_exact_owner_obligation(self):
        row, window, result, writer, original, token = self.captured_wait()
        self.assert_borrowed_delivery(row, window, result, original, token)
        owner = self.kernel._budget_sample_owners[token]
        writer.rollback()
        with patch.object(self.kernel, '_sample_budget', side_effect=AssertionError('new sample')):
            owner.finish_pending(window.envelope, timeout_seconds=.1)
        self.assertIsNone(owner._pending)
        self.assertNotIn(token, self.kernel._budget_sample_owners)
        self.assertIsNone(self.kernel._connection.execute(
            'SELECT token FROM kernel_budget_samples WHERE token=?', (token,)).fetchone())

    def test_result_delivery_does_not_visit_unrelated_registered_owner(self):
        unrelated = replace(self.command, execution_id='unrelated', idempotency_key='unrelated')
        self.kernel.submit(unrelated)
        lease = self.kernel.claim_and_start('unrelated-owner', execution_id='unrelated')
        budget = self.kernel.prepare_execution_budget(lease)
        row, window, result, writer, original, _ = self.captured_wait(context_owner=True)
        writer.rollback()
        owner = _KernelBudgetCapture(self.kernel, 'unrelated')
        token = self.kernel._begin_budget_sample('unrelated', _owner=owner)
        captured = budget.recheckpoint(sample=sample_clock(wall_time=self.wall[0]))
        owner._captured(token, captured)
        try:
            with patch.object(owner, 'finish_pending', side_effect=AssertionError('unrelated owner visited')) as finish:
                delivered = self.await_expired(row, window, original)
                finish.assert_not_called()
            self.assertEqual(delivered, result.to_dict())
            self.assertTrue(self.kernel._budget_sample_status('unrelated'))
            self.assertEqual(owner._pending, (token, captured))
        finally:
            owner.finish_pending(captured, timeout_seconds=.1)

    def test_two_positively_owned_parent_guards_still_refuse_before_result_read(self):
        row, window, _, writer, original, token = self.captured_wait(context_owner=True)
        writer.rollback()
        second = window._capture
        second_token = 'second-exact-wait-guard'
        with sqlite3.connect(self.kernel.db_path, timeout=.1) as native:
            native.execute("INSERT INTO kernel_budget_samples(token,execution_id,reason) VALUES(?,'parent','sampling')",
                           (second_token,))
        second._armed(second_token)
        second._captured(second_token, window.envelope.recheckpoint(
            sample=sample_clock(wall_time=self.wall[0])))
        self.kernel._budget_sample_owners[second_token] = second
        with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
            with self.assertRaises(type(original)) as caught:
                self.await_expired(row, window, original)
        self.assertIs(caught.exception, original)
        self.assertIsInstance(caught.exception.__cause__, BudgetClockUnknownError)
        read.assert_not_called()
        self.assertEqual({item[0] for item in self.kernel._connection.execute(
            'SELECT token FROM kernel_budget_samples WHERE execution_id=?', ('parent',))}, {token, second_token})
        # This case proves refusal with two owners. Publish each retained fact
        # explicitly afterward; final close has one shared maintenance window.
        for retained_token in (token, second_token):
            owner = self.kernel._budget_sample_owners[retained_token]
            owner.finish_pending(owner._pending[1], timeout_seconds=.1)
        self.assertFalse(self.kernel._budget_samples_pending())

    def foreign_ack(self, *, after_proof=False):
        # This case tests live commit visibility within a short proof window.
        # Full synchronization can finish after that window; power-loss
        # durability is exercised separately. The consumer remains FULL.
        foreign = SQLiteKernel(self.kernel.db_path,
            durability='full' if after_proof else 'normal')
        self.addCleanup(foreign.close)
        row, window, result, writer, original, token = self.captured_wait(
            different_owner=True, foreign_kernel=foreign)
        owner = foreign._budget_sample_owners[token]
        captured = owner._pending[1]
        writer.rollback()
        refused, proof_finished = threading.Event(), threading.Event()
        errors, record = [], {'scenario': 'foreign_ack_after_proof' if after_proof else 'foreign_ack_in_proof',
            'token': token, 'original_proof_seconds': .1, 'refusals': [], 'proof_deadlines': [],
            'publisher_durability': foreign.durability, 'consumer_durability': self.kernel.durability}
        actual_floor = factual._read_floor
        def observe_refusal(connection, lease, budget, **kwargs):
            try:
                return actual_floor(connection, lease, budget, **kwargs)
            except BudgetClockUnknownError as error:
                if str(error) == 'budget_clock_sample_unresolved:sampling':
                    record['proof_deadline'] = budget.deadline
                    record['proof_deadlines'].append(budget.deadline)
                    record['refusals'].append(time.monotonic())
                    refused.set()
                raise
        def publish():
            try:
                if not refused.wait(.2):
                    raise AssertionError('reader never observed actual foreign guard')
                if after_proof and not proof_finished.wait(.2):
                    raise AssertionError('original proof never finished')
                record['ack_started'] = time.monotonic()
                remaining = (.1 if after_proof else
                    record['proof_deadline']-record['ack_started'])
                if remaining <= 0:
                    raise AssertionError('ACK did not enter original factual proof window')
                owner.finish_pending(captured, timeout_seconds=min(.1, remaining))
                record['ack_returned'] = time.monotonic()
            except BaseException as error:
                errors.append(repr(error))
        publisher = threading.Thread(target=publish)
        publisher.start()
        try:
            with patch.object(factual, '_read_floor', side_effect=observe_refusal), \
                    patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read, \
                    patch.object(self.kernel, '_sample_budget', side_effect=AssertionError('new sample')):
                started = time.monotonic()
                if after_proof:
                    with self.assertRaises(type(original)) as caught:
                        self.await_expired(row, window, original)
                    self.assertIs(caught.exception, original)
                    self.assertIsInstance(caught.exception.__cause__, BudgetClockUnknownError)
                    read.assert_not_called()
                else:
                    delivered = self.await_expired(row, window, original)
                    self.assertEqual(delivered, result.to_dict())
                    read.assert_called_once()
                    self.assertLess(time.monotonic(), record['proof_deadline'])
                    record['delivered'] = delivered
                record['elapsed'] = time.monotonic()-started
                record['child_reads'] = read.call_count
        finally:
            record['proof_finished'] = time.monotonic()
            proof_finished.set()
            publisher.join(.2)
            record['errors'] = errors
            record['publisher_alive'] = publisher.is_alive()
            self.evidence['records'].append(record)
            self.assertFalse(publisher.is_alive())
            self.assertEqual(errors, [])
        self.assertTrue(record['refusals'])
        self.assertEqual(len(set(record['proof_deadlines'])), 1)
        self.assertGreaterEqual(record['ack_started'], record['refusals'][0])
        if after_proof:
            self.assertGreaterEqual(record['ack_started'], record['proof_deadline'])
        else:
            self.assertLess(record['ack_returned'], record['proof_deadline'])

    def test_foreign_owner_ack_after_actual_refusal_is_observed_inside_original_proof(self):
        self.foreign_ack()

    def test_foreign_owner_ack_after_original_proof_cannot_deliver_result(self):
        self.foreign_ack(after_proof=True)

    def test_foreign_parent_guard_is_never_cleared_by_result_delivery(self):
        row, window, _ = self.completed_child()
        with SQLiteKernel(self.kernel.db_path) as foreign:
            token = foreign._begin_budget_sample('parent')
        original_row = dict(row)
        parent = self.kernel.get('parent').to_dict()
        child = self.kernel.get('child').to_dict()
        with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
            began = time.monotonic()
            with self.assertRaises(BudgetClockUnknownError) as caught:
                self.children._completed_result(row, window)
            elapsed = time.monotonic()-began
        read.assert_not_called()
        self.assertEqual(self.kernel._connection.execute(
            'SELECT token FROM kernel_budget_samples WHERE token=?', (token,)).fetchone()[0], token)
        self.assertEqual(row, original_row)
        self.assertEqual(self.kernel.get('parent').to_dict(), parent)
        self.assertEqual(self.kernel.get('child').to_dict(), child)
        self.assertLess(elapsed, .2)
        self.evidence['records'].append({'scenario': 'foreign_guard_refusal',
            'error_type': type(caught.exception).__name__, 'error': str(caught.exception),
            'elapsed': elapsed, 'original_proof_seconds': .1, 'guard_token': token,
            'child_reads': read.call_count})

    def test_child_guard_committed_during_result_read_prevents_delivery(self):
        row, window, _ = self.completed_child()
        actual_read = factual._read_child_snapshot
        tokens = []
        def arm_child(*args):
            snapshot = actual_read(*args)
            with SQLiteKernel(self.kernel.db_path) as foreign:
                tokens.append(foreign._begin_budget_sample('child'))
            return snapshot
        with patch.object(factual, '_read_child_snapshot', side_effect=arm_child) as read:
            with self.assertRaises(BudgetClockUnknownError):
                self.children._completed_result(row, window)
            read.assert_called_once()
        self.assertEqual(len(tokens), 1)
        self.assertIsNotNone(self.kernel._connection.execute(
            'SELECT token FROM kernel_budget_samples WHERE token=?', (tokens[0],)).fetchone())

    def test_uncaptured_owned_guard_preserves_original_error_without_reading_child(self):
        row, window, _ = self.completed_child()
        owner = window._capture
        token = self.kernel._begin_budget_sample('parent', _owner=owner)
        def close_interrupted_fixture():
            try:
                with self.assertRaises(BudgetClockUnknownError):
                    self.kernel.close()
            finally:
                self.kernel._connection.close()
                self.kernel._connection_closed = True
        self.addCleanup(close_interrupted_fixture)
        self.assertEqual(owner._pending, (token, None))
        original = TimeoutError('Kernel control admission budget elapsed')
        time.sleep(max(0., window.deadline-time.monotonic())+.01)
        with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
            with self.assertRaises(TimeoutError) as caught:
                self.await_expired(row, window, original)
        self.assertIs(caught.exception, original)
        self.assertIsInstance(caught.exception.__cause__, BudgetClockUnknownError)
        read.assert_not_called()
        self.assertEqual(owner._pending, (token, None))


if __name__ == '__main__':
    unittest.main()
