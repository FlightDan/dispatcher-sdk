"""Real nested process dispatch with registry validation mocked for the test."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel.children import ChildExecutionError


def nested_c(payload, context):
    return {"node": "C", "pid": os.getpid(), "execution_id": context.lease.execution_id,
            "attempt": context.lease.attempt, "fence": context.lease.fence}


def nested_b(payload, context):
    identity = {"node": "B", "pid": os.getpid(), "execution_id": context.lease.execution_id,
                "attempt": context.lease.attempt, "fence": context.lease.fence}
    try:
        identity["child"] = context.children.run("C", {}, request_id="B-to-C", timeout_seconds=20)
    except ChildExecutionError as error:
        identity["child_error"] = error.code
    return identity


def nested_a(payload, context):
    return {"node": "A", "pid": os.getpid(), "execution_id": context.lease.execution_id,
            "attempt": context.lease.attempt, "fence": context.lease.fence,
            "child": context.children.run("B", {}, request_id="A-to-B", timeout_seconds=30)}


@unittest.skipUnless(os.name == "posix", "requires the POSIX supervisor")
class RuntimeNestedCapacityProcessTests(unittest.TestCase):
    def execute(self, capacity):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            runtime = Kernel.open_sqlite(Path(directory) / "kernel.sqlite", {"A": nested_a, "B": nested_b, "C": nested_c},
                isolation_mode="process", max_thread_workers=1, child_capacity=capacity, max_child_depth=2)
            try:
                runtime.submit(runtime.command("A", execution_id="A", idempotency_key="A", correlation_id="root",
                                               timeout_seconds=45, payload={}))
                outcome = runtime.run_once(execution_id="A")
                self.assertIsNotNone(outcome)
                self.assertEqual(outcome.state, "succeeded", outcome.result.to_dict())
                a = outcome.result.value
                b_result = a["child"]
                self.assertEqual(b_result["status"], "succeeded")
                b = b_result["value"]
                nodes = [a, b]
                if capacity == 2:
                    c_result = b["child"]
                    self.assertEqual(c_result["status"], "succeeded")
                    nodes.append(c_result["value"])
                    self.assertEqual(runtime.kernel.get_execution_limits(nodes[2]["execution_id"])["parent_execution_id"], b["execution_id"])
                else:
                    self.assertEqual(b["child_error"], "child_capacity_exhausted")
                self.assertEqual(runtime.kernel.get_execution_limits(b["execution_id"])["parent_execution_id"], "A")
                self.assertEqual(len({node["pid"] for node in nodes}), len(nodes))
                self.assertTrue(all(node["pid"] != os.getpid() for node in nodes))
                for node in nodes:
                    snapshot = runtime.kernel.get(node["execution_id"])
                    self.assertEqual(snapshot.state, "succeeded")
                    self.assertEqual((snapshot.result.attempt, snapshot.result.fence), (node["attempt"], node["fence"]))
                    records = runtime.kernel.inspect_supervisor_obligations(node["execution_id"])["obligations"]
                    self.assertEqual(len(records), 1)
                    if records[0]["state"] == "unresolved":
                        before = runtime._settlement_journal.inspect(node["execution_id"], timeout_seconds=1)
                        recovery = runtime.recover_completions(timeout_seconds=1)
                        after = runtime.kernel.inspect_supervisor_obligations(node["execution_id"])["obligations"]
                        self.assertEqual(after[0]["state"], "resolved", (node, snapshot.to_dict(), before, recovery, after))
                        records = after
                    self.assertEqual(records[0]["state"], "resolved", (node, records,
                        runtime._settlement_journal.inspect(node["execution_id"], timeout_seconds=1),
                        runtime._settlement_journal.scan_supervisor_cleanup(timeout_seconds=1)))
                    self.assertEqual(records[0]["resolution"]["result_id"], snapshot.result.result_id)
                    self.assertEqual(records[0]["resolution"]["source"], "sdk_confirmed_supervisor_cleanup")
                return nodes
            finally:
                runtime.close()

    def test_nested_two_reserved_children_complete_and_settle(self):
        self.assertEqual([node["node"] for node in self.execute(2)], ["A", "B", "C"])

    def test_nested_call_reports_exhausted_reserved_capacity(self):
        self.assertEqual([node["node"] for node in self.execute(1)], ["A", "B"])
