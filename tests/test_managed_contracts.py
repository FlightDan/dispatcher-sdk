import unittest

from dispatcher_sdk.execution_kernel import RetryPolicy
from dispatcher_sdk.managed_contracts import (
    ManagedContractError,
    ManagedControlSnapshot,
    RunBudget,
    RunSpec,
    TaskSpec,
)


def task(task_id, *, dependencies=(), payload=None, acceptance=None):
    return TaskSpec(
        task_id=task_id,
        handler_id=f"handler-{task_id}",
        payload={} if payload is None else payload,
        acceptance={} if acceptance is None else acceptance,
        dependencies=dependencies,
    )


def run_spec(tasks, *, routing=None, max_total_claims=12, deadline_at=2_000_000_000):
    return RunSpec(
        tasks=tasks,
        budget=RunBudget(max_total_claims=max_total_claims, deadline_at=deadline_at),
        routing={} if routing is None else routing,
        input={"request": "r-1"},
    )


class ManagedContractTests(unittest.TestCase):
    def test_dependency_graph_rejects_duplicates_unknowns_self_edges_and_cycles(self):
        with self.assertRaisesRegex(ManagedContractError, "unique"):
            run_spec([task("a"), task("a")])
        with self.assertRaisesRegex(ManagedContractError, "unknown dependencies"):
            run_spec([task("a", dependencies=["missing"])])
        with self.assertRaisesRegex(ManagedContractError, "itself"):
            task("a", dependencies=["a"])
        with self.assertRaisesRegex(ManagedContractError, "duplicates"):
            task("a", dependencies=["b", "b"])
        with self.assertRaisesRegex(ManagedContractError, "acyclic"):
            run_spec([task("a", dependencies=["b"]), task("b", dependencies=["a"])])

    def test_spec_copies_and_freezes_caller_json(self):
        payload = {"nested": [1, {"ok": True}]}
        acceptance = {"required": ["artifact"]}
        routing = {"failed": {"action": "review"}}
        spec = run_spec(
            [task("a", payload=payload, acceptance=acceptance)], routing=routing
        )

        payload["nested"].append(2)
        acceptance["required"].clear()
        routing["failed"]["action"] = "retry"

        stored = spec.to_dict()
        self.assertEqual(stored["tasks"][0]["payload"], {"nested": [1, {"ok": True}]})
        self.assertEqual(stored["tasks"][0]["acceptance"], {"required": ["artifact"]})
        self.assertEqual(stored["routing"], {"failed": {"action": "review"}})
        with self.assertRaises(TypeError):
            spec.tasks[0].payload["nested"][1]["ok"] = False
        with self.assertRaises(AttributeError):
            spec.tasks[0].payload["nested"].append(3)

    def test_canonical_content_normalizes_graph_order_and_defines_conflicts(self):
        first = run_spec([
            task("b", dependencies=["a"], payload={"n": 2}),
            task("a", acceptance={"mode": "manual"}),
        ])
        reordered = run_spec([
            task("a", acceptance={"mode": "manual"}),
            task("b", dependencies=["a"], payload={"n": 2}),
        ])
        changed_payload = run_spec([
            task("a", acceptance={"mode": "manual"}),
            task("b", dependencies=["a"], payload={"n": 3}),
        ])
        changed_acceptance = run_spec([
            task("a", acceptance={"mode": "automatic"}),
            task("b", dependencies=["a"], payload={"n": 2}),
        ])
        changed_budget = run_spec([
            task("a", acceptance={"mode": "manual"}),
            task("b", dependencies=["a"], payload={"n": 2}),
        ], max_total_claims=13)
        changed_routing = run_spec([
            task("a", acceptance={"mode": "manual"}),
            task("b", dependencies=["a"], payload={"n": 2}),
        ], routing={"failed": "stop"})

        self.assertEqual(first.canonical_json, reordered.canonical_json)
        self.assertEqual(first.fingerprint, reordered.fingerprint)
        self.assertNotEqual(first.fingerprint, changed_payload.fingerprint)
        self.assertNotEqual(first.fingerprint, changed_acceptance.fingerprint)
        self.assertNotEqual(first.fingerprint, changed_budget.fingerprint)
        self.assertNotEqual(first.fingerprint, changed_routing.fingerprint)

    def test_existing_retry_policy_is_kept_as_the_task_contract(self):
        policy = RetryPolicy(max_attempts=3, retry_timeouts=True)
        spec = run_spec([TaskSpec(
            task_id="a", handler_id="handler-a", payload=None, acceptance={},
            retry_policy=policy,
        )])
        self.assertEqual(spec.to_dict()["tasks"][0]["retry_policy"], policy.to_dict())
        with self.assertRaisesRegex(ManagedContractError, "RetryPolicy"):
            TaskSpec(task_id="b", handler_id="handler-b", payload=None,
                     acceptance={}, retry_policy={"max_attempts": 3})

    def test_strict_json_and_run_budget_validation(self):
        with self.assertRaisesRegex(ManagedContractError, "non-finite"):
            task("a", payload={"bad": float("nan")})
        with self.assertRaisesRegex(ManagedContractError, "strict JSON"):
            task("a", payload={"bad": object()})
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(ManagedContractError, "cyclic"):
            task("a", payload=cyclic)
        with self.assertRaisesRegex(ManagedContractError, "max_total_claims"):
            RunBudget(max_total_claims=True, deadline_at=None)
        with self.assertRaisesRegex(ManagedContractError, "max_total_claims"):
            RunBudget(max_total_claims=1 << 63, deadline_at=2_000_000_000)
        with self.assertRaisesRegex(ManagedContractError, "deadline_at"):
            RunBudget(max_total_claims=1, deadline_at=float("inf"))
        with self.assertRaisesRegex(ManagedContractError, "deadline_at"):
            RunBudget(max_total_claims=1, deadline_at=None)

    def test_control_snapshot_is_separate_and_freezes_recovery_obligations(self):
        obligations = [{"code": "cleanup_pending", "execution_id": "e-1"}]
        snapshot = ManagedControlSnapshot(
            control_state="pausing", control_version=4,
            recovery_obligations=obligations,
        )
        obligations[0]["code"] = "cleared"
        self.assertEqual(snapshot.control_state, "pausing")
        self.assertEqual(snapshot.to_dict()["recovery_obligations"], [
            {"code": "cleanup_pending", "execution_id": "e-1"}
        ])
        with self.assertRaises(ManagedContractError):
            ManagedControlSnapshot(control_state="running", control_version=0)


if __name__ == "__main__":
    unittest.main()
