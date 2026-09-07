from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.orchestrator import (
    Operations, Orchestrator, OrchestratorHost, OrchestrationError, RevisionConflict,
)


def echo(payload, context):
    return payload


class ConvenienceTests(unittest.TestCase):
    def test_open_sqlite_owns_its_runtime_but_injected_runtime_remains_open(self):
        path = self.root / "owned.db"
        with Orchestrator.open_sqlite(path, {"echo": echo}, isolation_mode="thread") as owned:
            owned.create_run("owned", command_id="create")
            owned.submit_task("owned", "task", request_id="caller-request", expected_revision=0,
                              handler_id="echo", payload={"answer": 42}, timeout_seconds=1)
            owned.flush()
            owned.runtime.run_once()
            owned.sync()
            self.assertEqual(owned.get_task("owned", "task")["latest_attempt"]["result"]["value"], {"answer": 42})
            runtime = owned.runtime
        self.assertTrue(runtime._closed)
        with self.sdk:
            self.assertEqual(self.sdk.get_run("run")["state"], "running")
        self.assertFalse(self.runtime._closed)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.now = 100.0
        self.runtime = Kernel.open_sqlite(
            self.root / "kernel.db", {"echo": echo}, isolation_mode="thread", now=lambda: self.now)
        self.addCleanup(self.runtime.close)
        self.sdk = Orchestrator(self.root / "runs.db", self.runtime.kernel, runtime=self.runtime)
        self.sdk.create_run("run", command_id="create")

    def command(self, execution_id):
        return ExecutionCommandV2(
            execution_id=execution_id, idempotency_key=execution_id,
            registry_revision=self.runtime.registry_revision, correlation_id="run",
            causation_id=None, handler_id="echo", handler_contract_version=1,
            retry_policy=RetryPolicy(), timeout_seconds=5, payload={"value": [1]})

    def apply(self, *operations, run_id="run"):
        state = self.sdk.get_run(run_id)
        return self.sdk.apply_operations(
            run_id, command_id=f"op:{state['revision']}", expected_revision=state["revision"],
            operations=list(operations))

    def park(self, execution_id="a", *, effects=("first",), run_id="run"):
        self.apply(Operations.add_task(execution_id, self.command(execution_id)),
                   Operations.dispatch(execution_id), run_id=run_id)
        self.sdk.flush()
        lease = self.runtime.kernel.claim_and_start("worker", registry_revision=self.runtime.registry_revision)
        for effect_id in effects:
            self.runtime.kernel.prepare_effect(lease, effect_id=effect_id, name="send", request={"item": effect_id})
        self.now = lease.expires_at
        self.runtime.reap()

    def test_builders_work_with_legacy_dicts_and_preserve_execution_policy(self):
        state = self.apply(
            Operations.add_task("a", self.command("a")),
            Operations.add_task("b", self.command("b").to_dict()),
            Operations.set_dependencies("b", ["a"]),
            Operations.wait("approval", payload={"owner": "app"}),
            Operations.signal("ready", {"ok": True}),
            Operations.watch_task("a", watch_id="a-watch", target={"chat": "test"}),
            Operations.cancel("a", reason="stop"),
            {"kind": "dispatch", "task_id": "b"},
        )
        # A cancelled dependency is settled; an open wait is application policy.
        self.assertEqual(state["tasks"]["b"]["attempts"][-1]["state"], "pending_dispatch")
        self.sdk.flush()
        self.runtime.run_once()
        self.sdk.sync()
        self.apply(Operations.new_attempt("a", self.command("a2")), Operations.dispatch("a"))
        self.sdk.flush()
        self.runtime.run_once()
        self.sdk.sync()
        state = self.apply(Operations.release_wait("approval"), Operations.finish("succeeded"))
        self.assertEqual(state["state"], "succeeded")
        self.assertEqual(len(state["tasks"]["a"]["attempts"]), 2)

    def test_builders_detach_inputs_and_submission_keeps_atomic_validation(self):
        command = self.command("a").to_dict()
        dependencies = []
        operation = Operations.add_task("a", command, dependencies=dependencies)
        command["payload"]["value"].append(2)
        dependencies.append("missing")
        self.assertEqual(operation["command"]["payload"], {"value": [1]})
        self.assertEqual(operation["dependencies"], [])
        with self.assertRaises(OrchestrationError):
            Operations.dispatch("")
        with self.assertRaises(OrchestrationError):
            Operations.signal("bad", float("nan"))
        before = self.sdk.get_run("run")
        with self.assertRaises(OrchestrationError):
            self.apply(operation, Operations.set_dependencies("a", ["missing"]))
        self.assertEqual(before, self.sdk.get_run("run"))

    def test_host_without_callback_executes_and_preserves_durable_notification(self):
        self.apply(Operations.add_task("a", self.command("a")),
                   Operations.watch_task("a", watch_id="watch", target="application"),
                   Operations.dispatch("a"))
        with OrchestratorHost(self.sdk, worker_count=1, pump_interval=0.01) as host:
            deadline = time.monotonic() + 3
            while not self.sdk.list_notifications() and time.monotonic() < deadline:
                time.sleep(0.01)
            notification, = self.sdk.list_notifications()
            self.assertEqual(notification["state"], "pending")
            self.assertEqual(notification["attempts"], 0)
            self.assertEqual(self.sdk.get_run("run")["tasks"]["a"]["attempts"][-1]["state"], "succeeded")
            self.assertFalse(host.health().notification_alive)
        received = []
        self.assertEqual(self.sdk.deliver_notifications(received.append, owner="consumer",
                         lease_seconds=30, retry_delay=1, limit=1), 1)
        self.assertEqual(received[0]["task_id"], "a")

    def test_inspection_finds_unsynced_recovery_without_changing_run_or_events(self):
        self.park()
        before = self.sdk.get_run("run")
        events = self.sdk.read_events("run")
        self.assertNotEqual(before["tasks"]["a"]["attempts"][-1]["state"], "recovery_required")
        details, = self.sdk.inspect_recoveries("run")
        self.assertEqual((details.run_id, details.task_id, details.attempt), ("run", "a", 0))
        self.assertEqual(details.run_revision, before["revision"])
        self.assertEqual(details.execution.state, "recovery_required")
        self.assertEqual(details.effect.state, "indeterminate")
        self.assertEqual(self.sdk.get_run("run"), before)
        self.assertEqual(self.sdk.read_events("run"), events)
        self.sdk.resolve_effect(details.effect.effect_id, decision="applied", response={"receipt": "ok"},
                                expected_revision=details.effect.revision, recovery_id="decision")
        self.assertEqual(self.sdk.inspect_recoveries("run"), [])

    def test_inspection_is_run_scoped_and_skips_planned_or_undelivered_attempts(self):
        self.sdk.create_run("other", command_id="create")
        self.park("foreign", run_id="other")
        self.apply(Operations.add_task("planned", self.command("planned")),
                   Operations.add_task("pending", self.command("pending")),
                   Operations.dispatch("pending"))
        self.assertEqual(self.sdk.inspect_recoveries("run"), [])
        self.assertEqual(self.sdk.inspect_recoveries("other")[0].task_id, "foreign")
        with self.assertRaises(OrchestrationError):
            self.sdk.inspect_recoveries("missing")

    def test_inspection_follows_next_effect_after_resolution_races_read(self):
        self.park(effects=("first", "second"))
        get_effect = self.runtime.kernel.get_effect
        raced = False

        def resolve_during_read(effect_id):
            nonlocal raced
            effect = get_effect(effect_id)
            if not raced:
                raced = True
                self.runtime.kernel.resolve_effect(effect_id, decision="not_applied", response=None,
                    expected_revision=effect.revision, recovery_id="racer")
            return effect

        with patch.object(self.runtime.kernel, "get_effect", side_effect=resolve_during_read):
            details, = self.sdk.inspect_recoveries("run")
        self.assertEqual(details.effect.effect_id, "second")
        self.assertEqual(details.execution.recovery_effect_id, "second")

    def test_inspection_omits_execution_resolved_during_read(self):
        self.park()
        get_effect = self.runtime.kernel.get_effect

        def resolve_during_read(effect_id):
            effect = get_effect(effect_id)
            self.runtime.kernel.resolve_effect(effect_id, decision="not_applied", response=None,
                expected_revision=effect.revision, recovery_id="racer")
            return effect

        with patch.object(self.runtime.kernel, "get_effect", side_effect=resolve_during_read):
            self.assertEqual(self.sdk.inspect_recoveries("run"), [])

    def test_inspection_preserves_cancel_target_and_application_attempt_index(self):
        self.apply(Operations.add_task("a", self.command("old")), Operations.cancel("a", reason="replace"),
                   Operations.new_attempt("a", self.command("current")), Operations.dispatch("a"))
        self.sdk.flush()
        lease = self.runtime.kernel.claim_and_start("worker", registry_revision=self.runtime.registry_revision)
        self.runtime.kernel.prepare_effect(lease, effect_id="cancel-effect", name="send", request={})
        self.apply(Operations.cancel("a", reason="stop"))
        self.sdk.flush()
        details, = self.sdk.inspect_recoveries("run")
        self.assertEqual(details.attempt, 1)
        self.assertEqual(details.execution.recovery_target_state, "cancelled")
        self.sdk.resolve_effect(details.effect.effect_id, decision="not_applied", response=None,
                                expected_revision=details.effect.revision, recovery_id="cancel-decision")
        self.assertEqual(self.sdk.inspect_recoveries("run"), [])
        self.assertEqual(self.runtime.kernel.get("current").state, "cancelled")

    def test_inspection_rejects_mismatched_kernel_identity(self):
        self.park()
        effect = self.runtime.kernel.get_effect("first")
        with patch.object(self.runtime.kernel, "get_effect", return_value=replace(effect, execution_id="foreign")):
            with self.assertRaises(OrchestrationError):
                self.sdk.inspect_recoveries("run")

    def test_inspection_bounds_continuously_changing_reads(self):
        self.park()
        execution = self.runtime.kernel.get("a")
        with patch.object(self.sdk, "inspect_execution", side_effect=[
                replace(execution, revision=execution.revision + n) for n in range(6)]):
            with self.assertRaises(RevisionConflict):
                self.sdk.inspect_recoveries("run")


if __name__ == "__main__":
    unittest.main()
