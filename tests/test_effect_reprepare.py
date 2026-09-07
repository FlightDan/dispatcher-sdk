"""A recovered effect's next perform cycle must not inherit stale timestamps."""

from pathlib import Path
import tempfile
import unittest

from dispatcher_sdk.execution_kernel import (
    ExecutionCommandV2, RetryPolicy, SQLiteKernel, StaleFenceError,
)


class EffectReprepareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "kernel.db"
        self.timestamp = 100.0
        self.kernel = SQLiteKernel(self.path, now=lambda: self.timestamp)
        self.addCleanup(lambda: self.kernel.close())
        self.kernel.submit(ExecutionCommandV2(
            execution_id="retry-effect", idempotency_key="retry-effect", registry_revision="fixture",
            correlation_id="fixture", causation_id=None, handler_id="fixture", handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=5), timeout_seconds=60, payload=None))

    def prepare(self):
        lease = self.kernel.claim_and_start("worker", lease_seconds=120)
        self.assertIsNotNone(lease)
        record = self.kernel.prepare_effect(lease, effect_id="effect", name="publish", request={"item": 1})
        return lease, record

    def make_uncertain(self, lease):
        claimed = self.kernel.claim_effect(lease, "effect")
        self.timestamp += 1
        uncertain = self.kernel.mark_effect_indeterminate(
            "effect", {"reason": "response lost"}, lease, claimed.claim_id)
        self.kernel.require_effect_recovery(lease, "effect")
        return claimed, uncertain

    def resolve(self, uncertain, recovery_id, *, decision="not_applied", response=None):
        self.timestamp += 1
        return self.kernel.resolve_effect("effect", decision=decision, response=response,
            expected_revision=uncertain.revision, recovery_id=recovery_id)

    def test_later_reprepare_after_restart_resets_attempt_fields_and_preserves_audit(self):
        first, _ = self.prepare()
        first_claim, uncertain = self.make_uncertain(first)
        resolved = self.resolve(uncertain, "decision-one")
        previous_events = self.kernel.effect_events("effect")
        self.kernel.close()
        self.kernel = SQLiteKernel(self.path, now=lambda: self.timestamp)
        # The old tests kept a frozen clock across resolution and reprepare,
        # hiding the invalid old indeterminate_at < new prepared_at ordering.
        self.timestamp += 10
        second, reprepared = self.prepare()
        self.assertEqual(reprepared.prepared_at, self.timestamp)
        self.assertEqual(reprepared.state, "prepared")
        self.assertEqual(reprepared.attempt, first.attempt + 1)
        self.assertEqual(reprepared.lease_id, second.lease_id)
        self.assertEqual(reprepared.fence, second.fence)
        for field in ("claim_id", "response", "committed_at", "indeterminate_at",
                      "recovery_id", "recovery_decision", "resolved_at"):
            self.assertIsNone(getattr(reprepared, field), field)
        self.assertEqual(self.kernel.effect_events("effect")[:-1], previous_events)
        reprepare_event = self.kernel.effect_events("effect")[-1]
        self.assertEqual(reprepare_event["data"]["prior_recovery_id"], "decision-one")
        self.assertEqual(reprepare_event["data"]["prior_recovery_revision"], resolved.revision)
        claimed = self.kernel.claim_effect(second, "effect")
        self.assertNotEqual(claimed.claim_id, first_claim.claim_id)
        with self.assertRaises(StaleFenceError):
            self.kernel.commit_effect("effect", {"stale": True}, first, first_claim.claim_id)
        self.timestamp += 1
        committed = self.kernel.commit_effect("effect", {"sent": True}, second, claimed.claim_id)
        self.assertEqual(committed.state, "committed")
        self.assertEqual(committed.response, {"sent": True})
        self.assertIsNone(committed.recovery_decision)
        self.assertEqual(self.kernel.effect_events("effect")[:len(previous_events)], previous_events)

    def test_second_uncertain_cycle_accepts_new_recovery_and_keeps_both_decisions(self):
        first, _ = self.prepare()
        _, uncertain = self.make_uncertain(first)
        self.resolve(uncertain, "decision-one")
        self.timestamp += 10
        second, _ = self.prepare()
        _, uncertain_again = self.make_uncertain(second)
        self.assertIsNone(uncertain_again.recovery_id)
        resolved = self.resolve(uncertain_again, "decision-two",
                                decision="applied", response={"sent": True})
        self.assertEqual(resolved.state, "committed")
        self.assertEqual(resolved.recovery_id, "decision-two")
        decisions = [event for event in self.kernel.effect_events("effect")
                     if event["event_type"] in {"recovery_not_applied", "recovery_applied"}]
        self.assertEqual([event["data"]["recovery_id"] for event in decisions],
                         ["decision-one", "decision-two"])
        self.assertLess(decisions[0]["created_at"], decisions[1]["created_at"])


if __name__ == "__main__":
    unittest.main()
