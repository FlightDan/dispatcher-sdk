"""A parent's inherited start is not proof that a child entered business."""
from dataclasses import replace
import json
from pathlib import Path
from tests._acceptance_evidence import retained_directory
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.contracts import (
    ExecutionCommandV2, ExecutionError, ExecutionResultV2, RetryPolicy,
)
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel


class ChildPreentrySettlementTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-child-preentry-settlement-')
        self.wall = [100.0]
        self.kernel = SQLiteKernel(self.root/'kernel.sqlite3', now=lambda: self.wall[0])
        self.addCleanup(lambda: self.kernel.close())
        self.parent = ExecutionCommandV2('parent', 'parent', 'original-binding', 'root', None,
            'parent', 1, RetryPolicy(), 10, {})
        self.kernel.submit(self.parent)
        self.parent_lease = self.kernel.claim_and_start('owner', execution_id='parent', lease_seconds=90)
        prepared = self.kernel._prepare_handler_entry(self.parent_lease)
        entered = prepared.enter_handler(10, origin_id='execution:parent', sample=sample_clock(wall_time=100))
        parent_budget = self.kernel.confirm_handler_entry(self.parent_lease, entered)
        inherited = parent_budget.derive(source='tool', origin_id='child-call:original', deadline_at=101,
                                         sample=sample_clock(wall_time=100))
        child = replace(self.parent, execution_id='child', idempotency_key='child', causation_id='parent',
                        handler_id='child', timeout_seconds=2)
        self.kernel.submit_child(child, self.parent_lease, inherited)
        self.lease = self.kernel.claim_and_start('owner', execution_id='child', lease_seconds=90)
        # This is the original claim timestamp, not inherited parent entry or
        # proof that a native child handler entered its business body.
        claimed_snapshot = self.kernel.get('child')
        self.original_started_at = claimed_snapshot.started_at
        self.inherited = BudgetEnvelope.from_dict(self.kernel.get_execution_limits('child')['envelope'])
        self.assertIsNotNone(self.inherited.started_at)
        self.assertFalse(any(item.origin_id == 'execution:child' for item in self.inherited.constraints))
        self.evidence = {'root': str(self.root), 'inherited': self.inherited.to_dict(),
            'frozen_wall': self.wall[0], 'original_claimed_snapshot': claimed_snapshot.to_dict(),
            'result_start_source': 'original SQLiteKernel.claim_and_start snapshot',
            'original_completed_at': 102}

    def tearDown(self):
        self.evidence['limits'] = self.kernel.get_execution_limits('child')
        self.evidence['snapshot'] = self.kernel.get('child').to_dict()
        path = self.root/'evidence.json'
        path.write_text(json.dumps(self.evidence, indent=2))
        print('child_preentry_settlement_evidence='+str(path), flush=True)

    def original_result(self):
        return ExecutionResultV2('original-result', 'child', 'failed', self.lease.attempt,
            self.lease.fence, [], self.original_started_at, 102, 'root', 'parent', None,
            ExecutionError('handler_process_start_failure', 'handler supervisor did not reach invocation',
                           retryable=False, details={'exitcode': 0, 'raw': [True, 1, 1.0]}))

    def settle(self, prepared):
        self.wall[0] = 102
        original = self.original_result()
        checkpoint = prepared.recheckpoint(sample=sample_clock(wall_time=102))
        self.evidence.update(original=original.to_dict(), prepared=prepared.to_dict(), checkpoint=checkpoint.to_dict())
        try:
            result = self.kernel._complete_sdk_result(self.lease, original, budget_envelope=checkpoint)
        except Exception as error:
            self.evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        self.evidence['returned'] = result.to_dict()
        self.assertEqual(result.result.to_json(), original.to_json())
        self.assertEqual(result.state, 'failed')
        limits = self.kernel.get_execution_limits('child')
        retained = BudgetEnvelope.from_dict(limits['envelope'])
        self.assertEqual(retained.constraints, prepared.constraints)
        self.assertEqual(retained.started_at, self.inherited.started_at)
        self.assertFalse(any(item.origin_id == 'execution:child' for item in retained.constraints))
        self.assertEqual(retained.view(sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)
        return limits

    def test_actual_bound_child_denied_before_preparation_retains_unentered_original(self):
        limits = self.settle(self.inherited)
        self.assertEqual(limits['entry_state'], 'unentered')
        self.assertIsNone(limits['entry_attempt'])
        self.assertIsNone(limits['entry_fence'])

    def test_actual_bound_child_prepared_but_unentered_retains_pending_original(self):
        prepared = self.kernel._prepare_handler_entry(self.lease)
        limits = self.settle(prepared)
        self.assertEqual(limits['entry_state'], 'pending')
        self.assertEqual((limits['entry_attempt'], limits['entry_fence']), (1, 1))

    def test_exact_original_receipt_restores_preentry_failure_after_reopen(self):
        prepared = self.kernel._prepare_handler_entry(self.lease)
        self.wall[0] = 102
        original = self.original_result()
        retained = prepared.recheckpoint(sample=sample_clock(wall_time=102))
        self.evidence.update(original=original.to_dict(), prepared=prepared.to_dict(), checkpoint=retained.to_dict())
        journal = SettlementJournal(self.root/'settlements.sqlite3', source_id='host', kernel_path=self.kernel.db_path)
        journal.record(self.lease, original, evidence={'budget_envelope': retained.to_dict()})
        self.kernel.close()
        self.kernel = SQLiteKernel(self.root/'kernel.sqlite3', now=lambda: self.wall[0])
        receipt = journal.pending()[0]
        self.evidence['receipt'] = receipt
        try:
            restored = self.kernel._complete_sdk_result(self.lease,
                ExecutionResultV2.from_dict(receipt['result']),
                budget_envelope=BudgetEnvelope.from_dict(receipt['evidence']['budget_envelope']), settlement=True)
        except Exception as error:
            self.evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        self.evidence['restored'] = restored.to_dict()
        self.assertEqual(restored.result.to_json(), original.to_json())
        self.assertEqual(self.kernel.get_execution_limits('child')['entry_state'], 'pending')

    def test_inherited_timestamp_cannot_authorize_entry_or_changed_completion_start(self):
        prepared = self.kernel._prepare_handler_entry(self.lease)
        before = self.kernel.get_execution_limits('child')
        with self.assertRaises(ValueError):
            self.kernel.confirm_handler_entry(self.lease, prepared)
        self.wall[0] = 102
        with self.assertRaises(ValueError):
            self.kernel._complete_sdk_result(self.lease, self.original_result(),
                budget_envelope=replace(prepared, started_at=101).recheckpoint(sample=sample_clock(wall_time=102)))
        self.assertEqual(self.kernel.get_execution_limits('child'), before)
        self.assertEqual(self.kernel.get('child').state, 'running')


if __name__ == '__main__':
    unittest.main()
