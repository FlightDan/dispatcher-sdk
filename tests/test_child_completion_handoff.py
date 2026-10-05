"""A child's exact captured clock remains available at handler return."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError
from dispatcher_sdk.execution_kernel.children import ChildExecutionError
from dispatcher_sdk.execution_kernel.completion_clock import capture_completion_time
from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects
from dispatcher_sdk.execution_kernel.contracts import ExecutionError
from tests import test_child_result_clock_cleanup as fixture


class ChildCompletionHandoffTests(unittest.TestCase):
    setUp = fixture.ChildResultClockCleanupTests.setUp
    tearDown = fixture.ChildResultClockCleanupTests.tearDown
    completed_child = fixture.ChildResultClockCleanupTests.completed_child
    captured_wait = fixture.ChildResultClockCleanupTests.captured_wait
    await_expired = fixture.ChildResultClockCleanupTests.await_expired

    def delivered_capture(self, *, failure=None):
        row, window, result, writer, original, token = self.captured_wait(failure=failure)
        context = HandlerContext(self.command, self.lease,
            HandlerEffects(self.kernel, self.lease, lambda: True), budget_envelope=self.budget)
        context.children = self.children
        self.children._budget_context = context
        if failure is None:
            self.assertEqual(self.await_expired(row, window, original), result.to_dict())
        else:
            with self.assertRaises(ChildExecutionError) as caught:
                self.await_expired(row, window, original)
            self.assertEqual(caught.exception.result, result.to_dict())
            self.assertEqual(caught.exception.code, failure.code)
        return context, window, writer, token

    def assert_completion_handoff(self, *, failure=None):
        context, window, writer, token = self.delivered_capture(failure=failure)
        owner = window._capture
        pending = owner._pending
        watermark = self.kernel._connection.execute('SELECT watermark FROM kernel_clock').fetchone()[0]
        with patch.object(self.kernel, '_sample_budget', side_effect=AssertionError('new budget sample')), \
                patch.object(self.kernel, '_finish_budget_sample', side_effect=AssertionError('early ACK')), \
                patch.object(self.kernel, '_wall_time', wraps=self.kernel._wall_time) as wall:
            completed_at = capture_completion_time(context)
        wall.assert_called_once()
        self.assertGreaterEqual(completed_at, pending[1].checkpoint.wall_at)
        self.assertIs(owner._pending, pending)
        self.assertIs(self.kernel._budget_sample_owners[token], owner)
        self.assertEqual(self.kernel._connection.execute(
            'SELECT token FROM kernel_budget_samples').fetchone()[0], token)
        self.assertEqual(self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock').fetchone()[0], watermark)
        self.assertEqual(context._budget_envelope.constraints, self.budget.constraints)
        self.evidence['records'].append({'scenario': 'child_to_handler_completion',
            'child_error': None if failure is None else failure.to_dict(), 'token': token,
            'completed_at': completed_at, 'guard_retained': True, 'wall_samples': 1})
        writer.rollback()
        owner.finish_pending(window.envelope, timeout_seconds=.1)
        self.assertIsNone(owner._pending)

    def test_successful_child_retains_exact_fact_for_parent_completion(self):
        self.assert_completion_handoff()

    def test_raw_failed_child_retains_exact_fact_for_parent_completion(self):
        self.assert_completion_handoff(failure=ExecutionError(
            'original_provider_failure', 'raw child failure', False, {'provider': 'local-fixture'}))

    def test_foreign_context_command_and_lease_cannot_borrow_retained_child_fact(self):
        context, _, _, _ = self.delivered_capture()
        for name, value in (('_budget_context', object()),
                            ('command', replace(self.command)),
                            ('parent_lease', replace(self.lease)), ('kernel', object())):
            with self.subTest(binding=name), patch.object(self.children, name, value):
                with self.assertRaisesRegex(BudgetClockUnknownError, 'sample_unresolved:sampling'):
                    capture_completion_time(context)

    def test_replaced_pending_tuple_and_registration_cannot_borrow_old_proof(self):
        context, window, _, token = self.delivered_capture()
        owner = window._capture
        pending = owner._pending
        with patch.object(owner, '_pending', (pending[0], pending[1])):
            with self.assertRaisesRegex(BudgetClockUnknownError, 'sample_unresolved:sampling'):
                capture_completion_time(context)
        with patch.dict(self.kernel._budget_sample_owners, {token: object()}):
            with self.assertRaisesRegex(BudgetClockUnknownError, 'sample_unresolved:sampling'):
                capture_completion_time(context)
        with patch.object(owner, '_pending', (pending[0], None)):
            with self.assertRaisesRegex(BudgetClockUnknownError, 'sample_unresolved:sampling'):
                capture_completion_time(context)


if __name__ == '__main__':
    unittest.main()
