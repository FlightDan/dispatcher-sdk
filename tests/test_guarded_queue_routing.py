"""An unresolved root clock obligation cannot poison unrelated queue work."""

import json
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, sample_clock
from dispatcher_sdk.execution_kernel.contracts import (
    ExecutionCommandV2, ExecutionError, ExecutionResultV2, RetryPolicy,
)
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory


class GuardedQueueRoutingTests(unittest.TestCase):
    def test_fresh_broad_claim_skips_requeued_guarded_root_without_changing_it(self):
        root = retained_directory("sdk-guarded-queue-routing-")
        path = root / "kernel.sqlite3"
        wall = [1000.]
        evidence = {}

        def command(identity):
            return ExecutionCommandV2(identity, identity, "queue-registry", "queue-proof", None,
                "work", 1, RetryPolicy(max_attempts=2), 10, {})

        try:
            with SQLiteKernel(path, now=lambda: wall[0]) as original:
                original.submit(command("A"))
                lease = original.claim_and_start("original-owner")
                budget = original.prepare_execution_budget(lease).enter_handler(10,
                    origin_id="execution:A", sample=sample_clock(wall_time=wall[0]))
                original.confirm_handler_entry(lease, budget)
                token = original._begin_budget_sample("A", timeout_seconds=.1)
                snapshot = original.get("A")
                factual_failure = ExecutionResultV2("original-failure", "A", "failed",
                    lease.attempt, lease.fence, [], snapshot.started_at, wall[0], "queue-proof", None,
                    None, ExecutionError("original_retryable_failure", "actual original failure", True, {}))
                requeued = original.complete(lease, factual_failure, timeout_seconds=.1)
                self.assertEqual(requeued.state, "queued")
                wall[0] += 1
                original.submit(command("B"))
                wall[0] += 1
                original.submit(command("C"))
                before = original.get("A").to_dict()
                before_limits = original.get_execution_limits("A")
                before_events = original.events("A")
                before_guards = [dict(row) for row in original._connection.execute(
                    "SELECT * FROM kernel_budget_samples WHERE execution_id='A'")]
                self.assertEqual([item["token"] for item in before_guards], [token])
                evidence.update(original=before, original_limits=before_limits,
                    original_events=before_events, original_guards=before_guards)

            # No owner from the first Kernel is carried into this fresh service.
            with SQLiteKernel(path, now=lambda: wall[0]) as fresh:
                with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved") as targeted:
                    fresh.claim_and_start("targeted-owner", execution_id="A", timeout_seconds=.1)
                evidence["targeted_error"] = {"type": type(targeted.exception).__name__,
                    "message": str(targeted.exception)}
                next_work = fresh.next_queued(registry_revision="queue-registry")
                self.assertIsNotNone(next_work)
                evidence["next_queued"] = next_work.to_dict()
                broad = fresh.claim_and_start("broad-owner", registry_revision="queue-registry",
                    timeout_seconds=.1)
                self.assertIsNotNone(broad)
                self.assertEqual(broad.execution_id, "B")
                self.assertEqual(next_work.execution_id, "B")
                self.assertEqual(fresh.get("B").state, "running")
                leased = fresh.claim("lease-owner", registry_revision="queue-registry")
                self.assertIsNotNone(leased)
                self.assertEqual(leased.execution_id, "C")
                self.assertEqual(fresh.get("A").to_dict(), before)
                self.assertEqual(fresh.get_execution_limits("A"), before_limits)
                self.assertEqual(fresh.events("A"), before_events)
                after_guards = [dict(row) for row in fresh._connection.execute(
                    "SELECT * FROM kernel_budget_samples WHERE execution_id='A'")]
                self.assertEqual(after_guards, before_guards)
                self.assertIsNone(fresh.claim_and_start("empty-owner", timeout_seconds=.1))
                evidence.update(next_queued=next_work.to_dict(), broad_running=fresh.get("B").to_dict(),
                    broad_leased=fresh.get("C").to_dict(), unchanged_guarded_root=fresh.get("A").to_dict(),
                    unchanged_guards=after_guards)
        except BaseException as error:
            evidence["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            artifact = root / "evidence.json"
            artifact.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print("guarded_queue_routing_evidence=" + str(artifact), flush=True)


if __name__ == "__main__":
    unittest.main()
