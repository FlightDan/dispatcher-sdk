"""A co-located control change and Kernel claim share one SQLite authority."""

from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import (
    CASConflictError, ExecutionCommandV2, ExecutionError, ExecutionNotFoundError, ExecutionResultV2,
    RetryPolicy, SQLiteKernel,
)
from dispatcher_sdk.orchestrator import (
    OrchestrationError, Orchestrator, inspect_run_diagnostics,
)


def command(run_id: str, task_id: str, *, managed: bool = True) -> ExecutionCommandV2:
    identity = f"sdk-managed:{run_id}:{task_id}" if managed else f"plain:{run_id}:{task_id}"
    return ExecutionCommandV2(
        execution_id=identity,
        idempotency_key=identity + ":key",
        registry_revision="handler-v1:fixture",
        correlation_id=run_id,
        causation_id=None,
        handler_id="fixture",
        handler_contract_version=1,
        retry_policy=RetryPolicy(),
        timeout_seconds=1,
        payload={"task": task_id},
    )


class ManagedKernelGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "store.sqlite3"
        self.kernel = SQLiteKernel(self.path)
        self.addCleanup(self.kernel.close)
        self.sdk = Orchestrator(self.path, self.kernel)
        self.deadline = time.time() + 60

    def _register(self, run_id: str, *, claims: int = 1):
        self.sdk.register_managed_run(
            run_id,
            request_id=f"create:{run_id}",
            definition={"kind": "gate-test"},
            task_commands=[("a", command(run_id, "a"), [])],
            max_claims=claims,
            deadline_at=self.deadline,
        )

    def test_create_and_pause_barrier_block_claims_without_stopping_other_run(self):
        self._register("one")
        self.assertEqual(self.kernel.get_run_control("one")["state"], "paused")
        self.assertEqual(self.sdk.flush(), 0)
        with self.assertRaises(ExecutionNotFoundError):
            self.kernel.get("sdk-managed:one:a")
        self.kernel.submit(command("other", "a", managed=False))
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.assertEqual(self.sdk.flush(), 1)
        self.assertEqual(self.kernel.get_run_control("one")["state"], "active")
        self.sdk._request_managed_control(
            "one", request_id="pause", kind="pause", mode="interrupt",
            expected_run_revision=self.sdk.get_run("one")["revision"],
            expected_control_epoch=1,
        )
        self.assertEqual(self.kernel.get_run_control("one")["state"], "pausing")
        lease = self.kernel.claim("worker")
        self.assertIsNotNone(lease)
        self.assertEqual(lease.execution_id, "plain:other:a")
        self.assertIsNone(self.kernel.claim("worker"))
        self.sdk.flush()
        self.assertEqual(
            self.sdk._settle_managed_pause("one", expected_control_epoch=2)["control_state"],
            "paused",
        )

    def test_active_lease_blocks_pause_settlement_until_cancelled(self):
        self._register("one")
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.sdk.flush()
        lease = self.kernel.claim("worker")
        self.assertEqual(lease.execution_id, "sdk-managed:one:a")
        self.sdk._request_managed_control(
            "one", request_id="pause", kind="pause", mode="interrupt",
            expected_run_revision=self.sdk.get_run("one")["revision"],
            expected_control_epoch=1,
        )
        with self.assertRaises(OrchestrationError):
            self.sdk._settle_managed_pause("one", expected_control_epoch=2)
        self.kernel.cancel(lease.execution_id, expected_revision=self.kernel.get(lease.execution_id).revision)
        self.sdk.flush()
        self.assertEqual(
            self.sdk._settle_managed_pause("one", expected_control_epoch=2)["control_state"],
            "paused",
        )

    def test_queued_execution_cannot_be_declared_a_drain_dependency_without_wait_record(self):
        self._register("one")
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.sdk.flush()
        with self.assertRaisesRegex(OrchestrationError, "wait registration is not available"):
            self.sdk._request_managed_control(
                "one", request_id="pause", kind="pause", mode="drain",
                expected_run_revision=self.sdk.get_run("one")["revision"],
                expected_control_epoch=1,
                drain_execution_ids=("sdk-managed:one:a",),
            )
        self.assertEqual(self.kernel.get_run_control("one")["state"], "active")

    def test_direct_kernel_cancel_cannot_bypass_active_run_control(self):
        self._register("one")
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.sdk.flush()
        lease = self.kernel.claim_and_start("worker")
        current = self.kernel.get(lease.execution_id)
        with self.assertRaisesRegex(CASConflictError, "persisted pause barrier"):
            self.kernel.cancel(lease.execution_id, expected_revision=current.revision)
        self.assertEqual(self.kernel.get(lease.execution_id).state, "running")

    def test_default_drain_admits_existing_lease_and_records_late_result(self):
        self._register("one")
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.sdk.flush()
        lease = self.kernel.claim_and_start("worker")
        pause = self.sdk._request_managed_control(
            "one", request_id="pause", kind="pause", mode="drain",
            expected_run_revision=self.sdk.get_run("one")["revision"],
            expected_control_epoch=1,
        )
        self.assertEqual(pause["drain_execution_ids"], [lease.execution_id])
        observed = self.kernel.get(lease.execution_id)
        result = ExecutionResultV2(
            result_id="result:late", execution_id=lease.execution_id,
            status="succeeded", attempt=lease.attempt, fence=lease.fence,
            effect_ids=[], started_at=observed.started_at,
            completed_at=max(observed.started_at, self.kernel.current_time()),
            correlation_id="one", causation_id=None, value={"ok": True}, error=None,
        )
        self.assertEqual(self.kernel.complete(lease, result).state, "succeeded")
        with self.assertRaisesRegex(OrchestrationError, "cleanup evidence"):
            self.sdk._settle_managed_pause("one", expected_control_epoch=2)

    def test_deadline_after_start_allows_result_settlement_without_retry(self):
        self.deadline = time.time() + 0.4
        self._register("one")
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.sdk.flush()
        lease = self.kernel.claim_and_start("worker")
        observed = self.kernel.get(lease.execution_id)
        time.sleep(max(0, self.deadline - time.time()) + 0.03)
        result = ExecutionResultV2(
            result_id="result:deadline", execution_id=lease.execution_id,
            status="failed", attempt=lease.attempt, fence=lease.fence,
            effect_ids=[], started_at=observed.started_at,
            completed_at=max(observed.started_at, self.kernel.current_time()),
            correlation_id="one", causation_id=None, value=None,
            error=ExecutionError("temporary", "retry requested", True, {}),
        )
        self.assertEqual(self.kernel.complete(lease, result).state, "failed")
        self.assertEqual(self.kernel.get_run_control("one")["claims_used"], 1)

    def test_explicit_acceptance_advances_graph_and_preserves_budget(self):
        self.sdk.register_managed_run(
            "one", request_id="create:one", definition={"kind": "graph-test"},
            task_commands=[
                ("b", command("one", "b"), ["a"]),
                ("a", command("one", "a"), []),
            ],
            max_claims=2, deadline_at=self.deadline,
        )
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.assertEqual(self.sdk.flush(), 1)
        lease = self.kernel.claim_and_start("worker")
        self.assertEqual(lease.execution_id, "sdk-managed:one:a")
        observed = self.kernel.get(lease.execution_id)
        result = ExecutionResultV2(
            result_id="result:a", execution_id=lease.execution_id,
            status="succeeded", attempt=lease.attempt, fence=lease.fence,
            effect_ids=[], started_at=observed.started_at,
            completed_at=max(observed.started_at, self.kernel.current_time()),
            correlation_id="one", causation_id=None, value={"ok": True}, error=None,
        )
        self.kernel.complete(lease, result)
        self.sdk.sync_execution(lease.execution_id)
        revision = self.sdk.get_run("one")["revision"]
        self.sdk._request_managed_control(
            "one", request_id="pause", kind="pause", mode="drain",
            expected_run_revision=revision, expected_control_epoch=1,
        )
        self.sdk._settle_managed_pause("one", expected_control_epoch=2)
        accepted = self.sdk.record_managed_acceptance(
            "one", "a", request_id="accept:a", expected_revision=revision,
            accepted=True, evidence={"source": "test", "decision": "approved"},
        )
        self.assertEqual(accepted["tasks"]["b"]["attempts"][0]["state"], "planned")
        self.assertEqual(accepted, self.sdk.record_managed_acceptance(
            "one", "a", request_id="accept:a", expected_revision=accepted["revision"],
            accepted=True, evidence={"source": "test", "decision": "approved"},
        ))
        resumed = self.sdk._request_managed_control(
            "one", request_id="resume:after-acceptance", kind="resume",
            expected_run_revision=accepted["revision"], expected_control_epoch=3,
        )
        self.assertEqual(resumed["control_state"], "active")
        self.assertEqual(self.sdk.get_run("one")["tasks"]["b"]["attempts"][0]["state"],
                         "pending_dispatch")
        self.assertEqual(self.sdk.flush(), 1)
        self.assertEqual(self.kernel.claim("worker").execution_id, "sdk-managed:one:b")
        self.assertEqual(self.kernel.get_run_control("one")["claims_used"], 2)
        self.assertIsNone(self.kernel.claim("worker"))

    def test_zero_claim_budget_and_elapsed_deadline_never_grant_lease(self):
        self._register("zero", claims=0)
        self.sdk._request_managed_control(
            "zero", request_id="resume:zero", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.assertEqual(self.sdk.flush(), 1)
        self.assertIsNone(self.kernel.claim("worker"))
        self.assertEqual(self.kernel.get_run_control("zero")["claims_used"], 0)

        self.sdk.register_managed_run(
            "expired", request_id="create:expired", definition={},
            task_commands=[("a", command("expired", "a"), [])],
            max_claims=1, deadline_at=time.time() - 1,
        )
        self.sdk._request_managed_control(
            "expired", request_id="resume:expired", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.assertEqual(self.sdk.flush(), 1)
        self.assertIsNone(self.kernel.claim("worker"))
        self.assertEqual(self.kernel.get_run_control("expired")["claims_used"], 0)

    def test_stale_new_submission_after_pause_is_rejected_but_replay_is_safe(self):
        self.sdk.register_managed_run(
            "one", request_id="create:one", definition={},
            task_commands=[
                ("a", command("one", "a"), []),
                ("b", command("one", "b"), ["a"]),
            ], max_claims=2, deadline_at=self.deadline,
        )
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.sdk.flush()
        self.sdk._request_managed_control(
            "one", request_id="pause", kind="pause", mode="drain",
            expected_run_revision=self.sdk.get_run("one")["revision"],
            expected_control_epoch=1,
        )
        self.sdk._settle_managed_pause("one", expected_control_epoch=2)
        with self.assertRaises(CASConflictError):
            self.kernel.submit_managed(command("one", "b"), run_id="one", generation=0)
        self.assertEqual(
            self.kernel.submit_managed(command("one", "a"), run_id="one", generation=0).execution_id,
            "sdk-managed:one:a",
        )

    def test_running_interrupt_requires_cleanup_evidence_after_authority_revocation(self):
        self._register("one")
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.sdk.flush()
        lease = self.kernel.claim_and_start("worker")
        self.assertEqual(lease.execution_id, "sdk-managed:one:a")
        pause = self.sdk._request_managed_control(
            "one", request_id="interrupt", kind="pause", mode="interrupt",
            expected_run_revision=self.sdk.get_run("one")["revision"],
            expected_control_epoch=1,
        )
        self.assertEqual(pause["cancel_count"], 1)
        report = inspect_run_diagnostics(self.path, "one")
        self.assertEqual(report.run_summary["managed_control"]["cleanup_pending_execution_ids"],
                         (lease.execution_id,))
        self.sdk.flush()
        self.assertEqual(self.kernel.get(lease.execution_id).state, "cancelled")
        with self.assertRaisesRegex(OrchestrationError, "cleanup evidence"):
            self.sdk._settle_managed_pause("one", expected_control_epoch=2)
        self.assertEqual(self.sdk.get_managed_control("one")["control_state"], "pausing")

    def test_managed_delivery_failure_diagnostics_redact_command_payload(self):
        secret_command = ExecutionCommandV2.from_dict({
            **command("one", "a").to_dict(),
            "payload": {"credential": "secret-payload-sentinel"},
        })
        self.sdk.register_managed_run(
            "one", request_id="create:one", definition={},
            task_commands=[("a", secret_command, [])],
            max_claims=1, deadline_at=self.deadline,
        )
        self.sdk._request_managed_control(
            "one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        with patch.object(self.kernel, "submit_managed",
                          side_effect=RuntimeError("secret-error-sentinel")):
            self.assertEqual(self.sdk.flush(), 0)
        delivery = self.sdk.delivery_messages(limit=1)[0]
        events = self.sdk.read_events("one")
        exposed = str(delivery) + str(events)
        self.assertNotIn("secret-payload-sentinel", exposed)
        self.assertNotIn("secret-error-sentinel", exposed)
        self.assertIsNotNone(delivery["intent"]["command_digest"])


if __name__ == "__main__":
    unittest.main()
