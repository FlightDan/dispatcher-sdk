"""Managed registration and control receipts use real SQLite transactions."""

from pathlib import Path
import tempfile
import time
import unittest

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.orchestrator import CommandConflict, OrchestrationError, Orchestrator, RevisionConflict


def command(run_id: str, task_id: str) -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id=f"sdk-managed:{run_id}:{task_id}",
        idempotency_key=f"sdk-managed-key:{run_id}:{task_id}",
        registry_revision="handler-v1:fixture",
        correlation_id=run_id,
        causation_id=None,
        handler_id="fixture",
        handler_contract_version=1,
        retry_policy=RetryPolicy(),
        timeout_seconds=1,
        payload={"task": task_id},
    )


class ManagedOrchestratorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "store.sqlite3"
        self.kernel = SQLiteKernel(self.path)
        self.addCleanup(self.kernel.close)
        self.sdk = Orchestrator(self.path, self.kernel)
        self.deadline = time.time() + 60
        self.arguments = {
            "request_id": "create-request",
            "definition": {"kind": "fixture"},
            "task_commands": [
                ("a", command("run", "a"), []),
                ("b", command("run", "b"), ["a"]),
            ],
            "max_claims": 2,
            "deadline_at": self.deadline,
        }

    def test_atomic_create_replay_and_conflict(self):
        created = self.sdk.register_managed_run("run", **self.arguments)
        self.assertEqual(created["revision"], 0)
        self.assertEqual(created["tasks"]["a"]["attempts"][0]["state"], "pending_dispatch")
        self.assertEqual(created["tasks"]["b"]["attempts"][0]["state"], "planned")
        self.assertEqual(self.sdk.get_managed_control("run")["control_state"], "paused")
        self.assertEqual(created, self.sdk.register_managed_run("run", **self.arguments))
        with self.assertRaises(CommandConflict):
            self.sdk.register_managed_run("run", **{**self.arguments, "max_claims": 3})
        with self.sdk._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sdk_outbox").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sdk_executions").fetchone()[0], 2)

    def test_invalid_graph_rolls_back_all_records(self):
        bad = {**self.arguments, "task_commands": [
            ("b", command("run", "b"), ["a"]),
            ("a", command("run", "a"), ["b"]),
        ]}
        with self.assertRaises(Exception):
            self.sdk.register_managed_run("run", **bad)
        with self.sdk._connect() as connection:
            for table in ("sdk_runs", "sdk_managed_runs", "sdk_executions", "sdk_outbox"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_orphaned_kernel_control_cannot_be_adopted_as_a_new_run(self):
        self.kernel.register_run_control(
            "run", max_claims=2, deadline_at=self.deadline,
        )
        self.kernel.set_run_control(
            "run", expected_epoch=0, state="active", generation=0,
        )
        with self.assertRaisesRegex(CommandConflict, "Kernel control identity"):
            self.sdk.register_managed_run("run", **self.arguments)
        with self.sdk._connect() as connection:
            self.assertIsNone(connection.execute(
                "SELECT 1 FROM sdk_managed_runs WHERE run_id='run'"
            ).fetchone())
        self.assertEqual(self.kernel.get_run_control("run")["state"], "active")

    def test_reverse_input_order_preserves_valid_dependency_graph(self):
        reversed_arguments = {**self.arguments,
                              "task_commands": list(reversed(self.arguments["task_commands"]))}
        created = self.sdk.register_managed_run("run", **reversed_arguments)
        self.assertEqual(created["tasks"]["a"]["attempts"][0]["state"], "pending_dispatch")
        self.assertEqual(created["tasks"]["b"]["attempts"][0]["state"], "planned")
        self.assertEqual(created, self.sdk.register_managed_run("run", **self.arguments))

    def test_missing_kernel_participant_rejects_without_creating_run(self):
        passive = Orchestrator(self.path.parent / "passive.sqlite3", object())
        with self.assertRaises(OrchestrationError):
            passive.register_managed_run("run", **self.arguments)
        with passive._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sdk_runs").fetchone()[0], 0)

    def test_control_request_receipt_is_durable(self):
        self.sdk.register_managed_run("run", **self.arguments)
        resume = self.sdk._request_managed_control(
            "run", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0,
        )
        self.assertEqual(resume["control_state"], "active")
        self.assertEqual(resume, self.sdk._request_managed_control(
            "run", request_id="resume", kind="resume",
            expected_run_revision=999, expected_control_epoch=999,
        ))
        with self.assertRaises(RevisionConflict):
            self.sdk._request_managed_control(
                "run", request_id="stale", kind="pause", mode="drain",
                expected_run_revision=0, expected_control_epoch=0,
            )
        pause = self.sdk._request_managed_control(
            "run", request_id="pause", kind="pause", mode="drain",
            expected_run_revision=0, expected_control_epoch=1,
        )
        self.assertEqual(pause["control_state"], "pausing")
        self.assertEqual(pause["drain_execution_ids"], [])
        self.assertEqual(self.sdk._settle_managed_pause("run", expected_control_epoch=2)["control_state"], "paused")
        self.assertEqual([row["control_epoch"] for row in self.sdk.list_managed_control_transitions("run")], [0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main()
