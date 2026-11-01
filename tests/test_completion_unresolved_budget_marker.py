"""Exact or ancestor unacknowledged clock facts fence result and cleanup commit."""
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

from dispatcher_sdk.execution_kernel import CASConflictError, SQLiteKernel
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, sample_clock
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture
from tests.test_execution_kernel_v2_sqlite import make_command, make_result


class CompletionUnresolvedBudgetMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.kernel = SQLiteKernel(Path(self.temp.name) / "kernel.sqlite")
        self.addCleanup(self.kernel.close)
        parent = replace(make_command("parent"), timeout_seconds=60)
        self.kernel.submit(parent)
        self.parent_lease = self.kernel.claim_and_start("parent-owner", execution_id="parent", lease_seconds=120)
        prepared = self.kernel._prepare_handler_entry(self.parent_lease)
        parent_envelope = prepared.enter_handler(60, origin_id="execution:parent")
        self.parent_budget = self.kernel.confirm_handler_entry(self.parent_lease, parent_envelope)
        child = replace(make_command("child"), timeout_seconds=45, causation_id="parent")
        self.kernel.submit_child(child, self.parent_lease, self.parent_budget)
        self.lease = self.kernel.claim_and_start("child-owner", execution_id="child", lease_seconds=120)
        prepared_child = self.kernel._prepare_handler_entry(self.lease)
        self.budget = self.kernel.confirm_handler_entry(self.lease,
            prepared_child.enter_handler(45, origin_id="execution:child"))
        self.kernel.register_supervisor_obligation(self.lease)
        self.result = make_result(self.kernel, self.lease)

    def assert_blocked_without_mutation(self):
        before = self.kernel.get("child").to_dict()
        before_events = self.kernel.events("child")
        before_obligation = self.kernel.inspect_supervisor_obligations("child")["obligations"]
        for settlement in (False, True):
            with self.subTest(settlement=settlement), self.assertRaises(BudgetClockUnknownError):
                self.kernel._complete_sdk_result(self.lease, self.result, budget_envelope=self.budget,
                    supervisor_cleanup_confirmed=True, settlement=settlement)
            self.assertEqual(self.kernel.get("child").to_dict(), before)
            self.assertEqual(self.kernel.events("child"), before_events)
            self.assertEqual(self.kernel.inspect_supervisor_obligations("child")["obligations"], before_obligation)
            self.assertEqual(before_obligation[0]["state"], "unresolved")

    def finish_and_assert_settled(self, token, execution_id, budget):
        captured = budget.recheckpoint(sample=sample_clock())
        self.kernel._finish_budget_sample(token, execution_id, captured, timeout_seconds=1)
        settled = self.kernel._complete_sdk_result(self.lease, self.result, budget_envelope=self.budget,
            supervisor_cleanup_confirmed=True, settlement=True, timeout_seconds=1)
        self.assertEqual(settled.state, "succeeded")
        self.assertEqual(settled.result.to_dict(), self.result.to_dict())
        obligation = self.kernel.inspect_supervisor_obligations("child")["obligations"][0]
        self.assertEqual(obligation["resolution"]["result_id"], self.result.result_id)

    def test_exact_execution_marker_blocks_then_acknowledgement_releases(self):
        token = self.kernel._begin_budget_sample("child", timeout_seconds=1)
        self.assert_blocked_without_mutation()
        with self.assertRaises(CASConflictError):
            self.kernel._finish_budget_sample("different-token", "child", self.budget, timeout_seconds=1)
        self.assert_blocked_without_mutation()
        self.finish_and_assert_settled(token, "child", self.budget)

    def test_ancestor_marker_blocks_then_acknowledgement_releases(self):
        token = self.kernel._begin_budget_sample("parent", timeout_seconds=1)
        self.assert_blocked_without_mutation()
        self.finish_and_assert_settled(token, "parent", self.parent_budget)

    def test_terminal_exact_result_replay_waits_for_new_sample_without_cleanup_proof(self):
        original = self.kernel._complete_sdk_result(self.lease, self.result,
            budget_envelope=self.budget, settlement=True, timeout_seconds=1)
        self.assertEqual(original.result.to_dict(), self.result.to_dict())
        self.assertEqual(self.kernel.inspect_supervisor_obligations("child")["obligations"][0]["state"], "unresolved")
        for execution_id, budget in (("child", self.budget), ("parent", self.parent_budget)):
            with self.subTest(execution_id=execution_id):
                token = self.kernel._begin_budget_sample(execution_id, timeout_seconds=1)
                before = self.kernel.get("child").to_dict()
                floor = self.kernel._connection.execute(
                    "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?", ("child",)).fetchone()[0]
                with self.assertRaises(BudgetClockUnknownError):
                    self.kernel._complete_sdk_result(self.lease, self.result,
                        budget_envelope=self.budget, settlement=True, timeout_seconds=1)
                self.assertEqual(self.kernel.get("child").to_dict(), before)
                self.assertEqual(self.kernel._connection.execute(
                    "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?", ("child",)).fetchone()[0], floor)
                self.assertEqual(self.kernel.inspect_supervisor_obligations("child")["obligations"][0]["state"], "unresolved")
                captured = budget.recheckpoint(sample=sample_clock())
                self.kernel._finish_budget_sample(token, execution_id, captured, timeout_seconds=1)
                replay = self.kernel._complete_sdk_result(self.lease, self.result,
                    budget_envelope=self.budget, settlement=True, timeout_seconds=1)
                self.assertEqual(replay.result.to_dict(), self.result.to_dict())
                self.assertEqual(self.kernel.inspect_supervisor_obligations("child")["obligations"][0]["state"], "unresolved")

    def test_armed_without_sample_cannot_acknowledge_or_settle(self):
        owner = _KernelBudgetCapture(self.kernel, "child")
        token = self.kernel._begin_budget_sample("child", timeout_seconds=1, _owner=owner)
        self.assertEqual(owner._pending, (token, None))
        with self.assertRaises(BudgetClockUnknownError):
            owner.finish_pending(self.budget, timeout_seconds=1)
        self.assert_blocked_without_mutation()
        # The fixture controls the arm and knows no sample occurred. Capture
        # its first sample now so cleanup can release the real owner.
        owner._captured(token, self.budget.recheckpoint(sample=sample_clock()))
        owner.finish_pending(self.budget, timeout_seconds=1)
