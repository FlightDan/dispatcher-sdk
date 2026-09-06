from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.orchestrator import (
    CommandConflict, OrchestrationError, Orchestrator, RevisionConflict,
)


def echo(payload, context):
    return payload


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.runtime = Kernel.open_sqlite(self.path, {"echo": echo}, isolation_mode="thread")
        self.addCleanup(self.runtime.close)
        self.sdk = Orchestrator(self.path, self.runtime.kernel, runtime=self.runtime)
        self.sdk.create_run("run", command_id="create", input={"anything": "application data"})

    def command(self, name):
        return ExecutionCommandV2(
            execution_id=name, idempotency_key=name, registry_revision=self.runtime.registry_revision,
            correlation_id="run", causation_id=None, handler_id="echo", handler_contract_version=1,
            retry_policy=RetryPolicy(), timeout_seconds=5, payload={"value": name}).to_dict()

    def apply(self, *ops, name=None, **kwargs):
        state = self.sdk.get_run("run")
        return self.sdk.apply_operations(
            "run", command_id=name or f"operation-{state['revision']}",
            expected_revision=state["revision"], operations=list(ops), **kwargs)

    def add(self, name, dependencies=None):
        return {"kind": "add_task", "task_id": name, "command": self.command(name),
                "dependencies": dependencies or []}

    def run_task(self, name):
        self.apply(self.add(name), {"kind": "dispatch", "task_id": name})
        self.sdk.flush()
        self.runtime.run_once()
        self.sdk.sync_execution(name)

    def test_empty_run_and_results_never_advance_business(self):
        self.assertEqual(self.runtime.kernel.events_since(0), [])
        self.apply(self.add("a"), self.add("b", ["a"]), {"kind": "dispatch", "task_id": "a"})
        self.sdk.flush()
        self.runtime.run_once()
        self.sdk.sync()
        state = self.sdk.get_run("run")
        self.assertEqual(state["state"], "running")
        self.assertEqual(state["tasks"]["a"]["attempts"][0]["state"], "succeeded")
        self.assertEqual(state["tasks"]["b"]["attempts"][0]["state"], "planned")
        self.assertFalse(self.runtime.run_once())
        self.apply({"kind": "dispatch", "task_id": "b"})
        self.sdk.flush()
        self.runtime.run_once()
        self.sdk.sync()
        self.apply({"kind": "finish", "state": "succeeded"})
        self.assertEqual(self.sdk.get_run("run")["state"], "succeeded")

    def test_atomic_state_cursor_and_operations_rollback(self):
        cursor = self.sdk.read_events("run")[-1]["sequence"]
        before = self.sdk.get_run("run")
        with self.assertRaises(OrchestrationError):
            self.apply(self.add("a"), {"kind": "dispatch", "task_id": "missing"},
                       application_state={"decision": 1}, subscription="app",
                       expected_cursor=0, advance_to=cursor)
        self.assertEqual(before, self.sdk.get_run("run"))
        self.assertEqual(self.sdk.get_subscription("run", "app"), 0)
        self.apply(self.add("a"), application_state={"decision": 1}, subscription="app",
                   expected_cursor=0, advance_to=cursor)
        self.assertEqual(self.sdk.get_subscription("run", "app"), cursor)
        self.assertEqual(self.sdk.get_run("run")["application_state"], {"decision": 1})

    def test_strict_replay_and_cas(self):
        arguments = dict(command_id="once", expected_revision=0, operations=[self.add("a")])
        receipt = self.sdk.apply_operations("run", **arguments)
        self.apply({"kind": "wait", "wait_id": "approval"})
        self.assertEqual(self.sdk.apply_operations("run", **arguments), receipt)
        self.assertEqual(self.sdk.get_command_receipt("run", "once"), receipt)
        with self.assertRaises(CommandConflict):
            self.sdk.apply_operations("run", **{**arguments, "expected_revision": 2})
        with self.assertRaises(RevisionConflict):
            self.sdk.apply_operations("run", command_id="stale", expected_revision=0, operations=[])

    def test_cursor_only_acknowledgement_cas_replay_and_no_event_churn(self):
        arguments = dict(command_id="ack", expected_revision=0, subscription="app",
                         expected_cursor=0, advance_to=1)
        before = self.sdk.read_events("run")
        receipt = self.sdk.acknowledge_events("run", **arguments)
        self.assertEqual(receipt["revision"], 0)
        self.assertEqual(self.sdk.get_subscription("run", "app"), 1)
        self.assertEqual(self.sdk.read_events("run"), before)
        self.apply({"kind": "signal", "signal_id": "wake", "payload": True})
        self.assertEqual(self.sdk.acknowledge_events("run", **arguments), receipt)
        with self.assertRaises(RevisionConflict):
            self.sdk.acknowledge_events("run", **{**arguments, "command_id": "stale"})
        with self.assertRaises(CommandConflict):
            self.sdk.acknowledge_events("run", **{**arguments, "advance_to": 2})

    def test_crash_after_kernel_acceptance_replays_one_execution(self):
        self.apply(self.add("a"), {"kind": "dispatch", "task_id": "a"})
        def crash(name):
            if name == "after_kernel_delivery":
                raise RuntimeError("simulated process exit")
        self.sdk._failpoint = crash
        with self.assertRaises(RuntimeError):
            self.sdk.flush()
        reopened = Orchestrator(self.path, self.runtime.kernel, runtime=self.runtime)
        self.assertEqual(reopened.flush(), 1)
        self.assertEqual(reopened.flush(), 0)
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM kernel_executions").fetchone()[0], 1)
        self.runtime.run_once()
        reopened.sync()
        self.assertEqual(reopened.get_run("run")["tasks"]["a"]["attempts"][0]["state"], "succeeded")

    def test_concurrent_application_decisions_only_one_commits(self):
        def decide(index):
            sdk = Orchestrator(self.path, self.runtime.kernel)
            try:
                sdk.apply_operations("run", command_id=f"racer-{index}", expected_revision=0,
                                     operations=[self.add(f"task-{index}")])
                return True
            except RevisionConflict:
                return False
        with ThreadPoolExecutor(max_workers=2) as workers:
            self.assertEqual(sum(workers.map(decide, range(2))), 1)
        self.assertEqual(len(self.sdk.get_run("run")["tasks"]), 1)

    def test_application_owns_attempt_count_and_history(self):
        self.run_task("a")
        old = copy.deepcopy(self.sdk.get_run("run")["tasks"]["a"]["attempts"][0])
        for i in range(12):
            self.apply({"kind": "new_attempt", "task_id": "a", "command": self.command(f"a-{i}")},
                       {"kind": "dispatch", "task_id": "a"})
            self.sdk.flush()
            self.runtime.run_once()
            self.sdk.sync()
        attempts = self.sdk.get_run("run")["tasks"]["a"]["attempts"]
        self.assertEqual(len(attempts), 13)
        self.assertEqual(attempts[0], old)

    def test_dependency_cycles_and_command_identity_rejected(self):
        self.apply(self.add("a"), self.add("b", ["a"]))
        with self.assertRaises(OrchestrationError):
            self.apply({"kind": "set_dependencies", "task_id": "a", "dependencies": ["b"]})
        with self.assertRaises(OrchestrationError):
            self.apply({"kind": "dispatch", "task_id": "b"})
        with self.assertRaises(CommandConflict):
            self.apply({"kind": "add_task", "task_id": "other", "command": self.command("a")})
        self.apply({"kind": "dispatch", "task_id": "a"})
        with self.assertRaises(OrchestrationError):
            self.apply({"kind": "set_dependencies", "task_id": "a", "dependencies": []})

    def test_signals_wait_for_application_and_terminal_state_is_explicit(self):
        self.apply({"kind": "wait", "wait_id": "external"})
        self.apply({"kind": "signal", "signal_id": "answer", "payload": {"approved": True}})
        self.assertEqual(self.sdk.get_run("run")["waits"]["external"]["state"], "open")
        with self.assertRaises(OrchestrationError):
            self.apply({"kind": "finish", "state": "succeeded"})
        self.apply({"kind": "release_wait", "wait_id": "external"}, {"kind": "finish", "state": "succeeded"})
        with self.assertRaises(OrchestrationError):
            self.apply(self.add("after-terminal"))

    def test_cancel_and_finish_do_not_forge_execution_results(self):
        self.apply(self.add("planned"), {"kind": "cancel", "task_id": "planned", "reason": "app choice"})
        self.apply(self.add("queued"), {"kind": "dispatch", "task_id": "queued"})
        self.sdk.flush()
        self.apply({"kind": "cancel", "task_id": "queued", "reason": "app choice"})
        self.sdk.flush()
        state = self.sdk.get_run("run")
        self.assertIsNone(state["tasks"]["planned"]["attempts"][0]["result"])
        self.assertEqual(state["tasks"]["queued"]["attempts"][0]["result"]["status"], "cancelled")
        self.apply({"kind": "finish", "state": "cancelled"})

    def test_outside_kernel_submission_cannot_start_planned_task(self):
        self.apply(self.add("a"))
        self.runtime.submit(ExecutionCommandV2.from_dict(self.command("a")))
        with self.assertRaises(OrchestrationError):
            self.sdk.sync_execution("a")

    def test_effect_resolution_checks_ownership_before_changing_kernel(self):
        self.runtime.submit(ExecutionCommandV2.from_dict(self.command("foreign")))
        with patch.object(self.runtime.kernel, "get_effect", return_value=SimpleNamespace(
            execution_id="foreign")), patch.object(self.runtime.kernel, "resolve_effect") as resolve:
            with self.assertRaises(OrchestrationError):
                self.sdk.resolve_effect("foreign-effect", decision="applied", response={},
                                        expected_revision=1, recovery_id="recover")
        resolve.assert_not_called()

    def test_kernel_idempotency_key_conflict_rejected_before_dispatch(self):
        self.apply(self.add("a"))
        command = self.command("different")
        command["idempotency_key"] = "a"
        with self.assertRaises(CommandConflict):
            self.apply({"kind": "add_task", "task_id": "different", "command": command})
        self.assertNotIn("different", self.sdk.get_run("run")["tasks"])

    def test_kernel_reopens_shared_database_without_application_namespace_knowledge(self):
        from dispatcher_sdk.execution_kernel import SQLiteKernel, StorageIsolationError
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE customer_owned_state (value TEXT)")
        with SQLiteKernel(self.path) as kernel:
            self.assertIsNotNone(kernel)
            with self.assertRaises(sqlite3.DatabaseError):
                kernel._connection.execute("SELECT * FROM customer_owned_state")

    def test_failpoint_rolls_back_state_events_command_and_outbox(self):
        def crash(name):
            if name == "before_commit":
                raise RuntimeError("rollback")
        self.sdk._failpoint = crash
        with self.assertRaises(RuntimeError):
            self.apply(self.add("a"), {"kind": "dispatch", "task_id": "a"}, name="rollback")
        self.sdk._failpoint = lambda name: None
        self.assertEqual(self.sdk.get_run("run")["revision"], 0)
        self.assertIsNone(self.sdk.get_command_receipt("run", "rollback"))
        self.assertEqual(self.sdk.flush(), 0)
        self.assertEqual(len(self.sdk.read_events("run")), 1)


if __name__ == "__main__":
    unittest.main()
