from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.orchestrator import Orchestrator


def echo(payload, context):
    return payload


class SDKCommandDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)
        self.runtime = Kernel.open_sqlite(path / "kernel.db", {"echo": echo}, isolation_mode="thread")
        self.addCleanup(self.runtime.close)
        self.sdk = Orchestrator(path / "sdk.db", self.runtime.kernel, runtime=self.runtime)
        self.sdk.create_run("run", command_id="create")

    def command(self, name, bad=False):
        return ExecutionCommandV2(
            execution_id=name, idempotency_key=name, registry_revision="wrong" if bad else self.runtime.registry_revision,
            correlation_id="run", causation_id=None, handler_id="echo", handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=5, payload={"value": name})

    def apply(self, *operations):
        revision = self.sdk.get_run("run")["revision"]
        return self.sdk.apply_operations("run", command_id=f"decision-{revision}", expected_revision=revision,
                                         operations=list(operations))

    def schedule(self, name, bad=False):
        self.apply({"kind": "add_task", "task_id": name, "command": self.command(name, bad).to_dict()},
                   {"kind": "dispatch", "task_id": name})

    def cancel(self, name):
        self.apply({"kind": "cancel", "task_id": name, "reason": "operator chose to stop"})

    def test_bad_registry_does_not_block_valid_message_and_failure_is_public_and_durable(self):
        self.schedule("bad", bad=True)
        self.schedule("good")
        self.assertEqual(self.sdk.flush(), 1)
        self.assertEqual(self.runtime.kernel.get("good").state, "queued")
        records = self.sdk.delivery_messages(["bad"])
        self.assertEqual(records[0]["state"], "failed")
        self.assertEqual(records[0]["attempts"], 1)
        self.assertEqual(records[0]["last_error"]["type"], "RegistryRevisionMismatchError")
        failures = [event for event in self.sdk.read_events("run") if event["kind"] == "delivery.failed"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["payload"]["intent"]["execution_id"], "bad")
        reopened = Orchestrator(self.sdk.db_path, self.runtime.kernel, runtime=self.runtime)
        self.assertEqual(reopened.delivery_messages(["bad"]), records)

    def test_bounded_flush_is_fair_past_first_bad_message(self):
        self.schedule("bad", bad=True)
        self.schedule("good")
        self.assertEqual(self.sdk.flush(limit=1), 0)
        self.assertEqual(self.sdk.flush(limit=1), 1)
        self.assertEqual(self.runtime.kernel.get("good").state, "queued")

    def test_cancel_before_kernel_acceptance_retains_command_and_late_delivery_cannot_revive(self):
        self.schedule("bad", bad=True)
        self.assertEqual(self.sdk.flush(), 0)
        self.cancel("bad")
        # The fresh cancel is selected before the older failed dispatch.
        self.assertEqual(self.sdk.flush(limit=1), 1)
        terminal = self.runtime.kernel.get("bad")
        self.assertEqual(terminal.state, "cancelled")
        self.assertEqual(terminal.command, self.command("bad", bad=True))
        self.assertEqual(self.sdk.flush(), 1)
        self.assertEqual(self.runtime.kernel.get("bad"), terminal)
        self.assertFalse(self.runtime.run_once())
        self.assertTrue(all(row["state"] == "delivered" for row in self.sdk.delivery_messages()))

    def test_concurrent_late_dispatch_after_cancel_never_resurrects_execution(self):
        self.schedule("task")
        entered, release = threading.Event(), threading.Event()
        original = self.runtime.submit
        worker_id = []

        def delayed_submit(command):
            if threading.get_ident() == worker_id[0]:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test release timed out")
            return original(command)

        def slow_flush():
            worker_id.append(threading.get_ident())
            return self.sdk.flush(limit=1)

        with patch.object(self.runtime, "submit", side_effect=delayed_submit):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(slow_flush)
                try:
                    self.assertTrue(entered.wait(5))
                    self.cancel("task")
                    # The pending cancel suppresses another dispatch delivery.
                    self.assertEqual(self.sdk.flush(), 1)
                    terminal = self.runtime.kernel.get("task")
                    self.assertEqual(terminal.state, "cancelled")
                finally:
                    release.set()
                future.result(timeout=5)
        self.assertEqual(self.runtime.kernel.get("task"), terminal)
        self.assertFalse(self.runtime.run_once())

    def test_existing_wrong_identity_is_not_cancelled_or_acknowledged(self):
        self.schedule("task")
        original = replace(self.command("task"), payload={"another": "command"})
        before = self.runtime.kernel.submit(original)
        self.cancel("task")
        self.assertEqual(self.sdk.flush(), 0)
        self.assertEqual(self.runtime.kernel.get("task"), before)
        records = self.sdk.delivery_messages()
        self.assertEqual([row["state"] for row in records], ["pending", "failed"])
        self.assertIsNone(records[0]["last_error"])
        self.assertEqual(records[1]["last_error"]["type"], "OrchestrationError")

    def test_after_kernel_acceptance_failpoint_propagates_and_replay_acknowledges(self):
        self.schedule("task")
        def fail(name):
            if name == "after_kernel_delivery":
                raise RuntimeError("crash after acceptance")
        self.sdk._failpoint = fail
        with self.assertRaisesRegex(RuntimeError, "crash after acceptance"):
            self.sdk.flush()
        self.assertEqual(self.sdk.delivery_messages()[0]["state"], "pending")
        self.assertEqual(self.runtime.kernel.get("task").state, "queued")
        self.sdk._failpoint = lambda name: None
        self.assertEqual(self.sdk.flush(), 1)
        self.assertEqual(self.sdk.delivery_messages()[0]["state"], "delivered")
