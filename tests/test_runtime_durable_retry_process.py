"""Real POSIX supervisor retry; registry revision validation is mocked.

The two revision functions are replaced throughout Runtime's lifetime, so this
exercise deliberately does not execute registry fingerprinting or validate it.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import HandlerExecutionError, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal


def retry_process_handler(payload, context):
    identity = {"execution_id": context.lease.execution_id,
                "attempt": context.lease.attempt, "fence": context.lease.fence,
                "pid": os.getpid()}
    if context.lease.attempt == 1:
        raise HandlerExecutionError("temporary", "retry", retryable=True, details=identity)
    return identity


@unittest.skipUnless(os.name == "posix", "requires the POSIX process supervisor")
class RuntimeDurableRetryProcessTests(unittest.TestCase):
    def test_retry_records_exact_cleanup_and_resolves_both_generations(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            path = Path(root) / "kernel.sqlite3"
            runtime = Kernel.open_sqlite(path, {"retry": retry_process_handler}, isolation_mode="process")
            try:
                policy = RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     backoff_multiplier=1, max_backoff_seconds=0)
                runtime.submit(runtime.command("retry", execution_id="retry-process",
                    idempotency_key="retry-process", correlation_id="retry-process",
                    timeout_seconds=30, payload={}, retry_policy=policy))
                first = runtime.run_once(execution_id="retry-process")
                self.assertEqual(first.state, "queued")
                second = runtime.run_once(execution_id="retry-process")
                self.assertEqual(second.state, "succeeded")
                actual = second.result.value
                self.assertEqual(actual["execution_id"], "retry-process")
                self.assertEqual(actual["attempt"], 2)
                self.assertNotEqual(actual["pid"], os.getpid())
                obligations = runtime.kernel.inspect_supervisor_obligations("retry-process")["obligations"]
                self.assertEqual([item["attempt"] for item in obligations], [1, 2])
                self.assertTrue(all(item["state"] == "resolved" for item in obligations))
                self.assertEqual(obligations[1]["fence"], actual["fence"])
                self.assertNotEqual(obligations[0]["fence"], obligations[1]["fence"])
                for item, status in zip(obligations, ("failed", "succeeded")):
                    self.assertEqual(item["resolution"]["source"], "sdk_confirmed_supervisor_cleanup")
                    self.assertEqual(item["resolution"]["status"], status)
                notes = runtime._settlement_journal.scan_supervisor_cleanup(timeout_seconds=1)["registrations"]
                for obligation in obligations:
                    entry = next(item for item in notes if item["identity"] == {
                        "execution_id": "retry-process", "attempt": obligation["attempt"],
                        "fence": obligation["fence"]})
                    self.assertEqual(entry["cleanup"], "confirmed")
                    self.assertEqual(entry["worker_tree_cleanup"], "confirmed")
                    self.assertEqual(entry["handler_entry"], "observed")
                    self.assertEqual(entry["outcome"], "durable")
                events = runtime.kernel.events("retry-process")
                retry = next(event for event in events if event["event_type"] == "retry_scheduled")
                self.assertEqual(retry["data"]["result"]["result_id"], obligations[0]["resolution"]["result_id"])
                first_identity = retry["data"]["result"]["error"]["details"]
                self.assertEqual(first_identity["execution_id"], "retry-process")
                self.assertEqual(first_identity["attempt"], 1)
                self.assertEqual(first_identity["fence"], obligations[0]["fence"])
                self.assertNotEqual(first_identity["pid"], os.getpid())
                self.assertNotEqual(first_identity["pid"], actual["pid"])
                journal_path = runtime._settlement_journal.path
                source_id = runtime._settlement_journal.source_id
            finally:
                runtime.close()
            with SQLiteKernel(path) as reopened:
                self.assertEqual(reopened.get("retry-process").state, "succeeded")
                self.assertEqual(reopened.inspect_supervisor_obligations("retry-process")["obligations"], obligations)
            journal = SettlementJournal.open_readonly(journal_path, source_id=source_id, kernel_path=path,
                                                      timeout_seconds=1)
            persisted = journal.scan_supervisor_cleanup(timeout_seconds=1)["registrations"]
            self.assertEqual(persisted, notes)
