"""Recovery fairness with real SQLite records and synthetic retained receipts.

Receipt cleanup evidence is fixture data and is not a host cleanup attestation.
No handler is run by this recovery test; registry revision checks are mocked.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from tests.test_execution_kernel_v2_sqlite import make_result


def _never_invoked(payload, context):
    raise AssertionError("completion recovery must not invoke a handler")


class RecoveryPendingFairPaginationTests(unittest.TestCase):
    def test_clock_unknown_first_page_does_not_starve_later_receipt(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            runtime = Kernel.open_sqlite(Path(directory) / "kernel.sqlite", {"work": _never_invoked}, isolation_mode="thread")
            try:
                journal = runtime._settlement_journal
                confirmed = {"supervisor_completion": {"cleanup": "confirmed",
                    "source": "runtime_supervisor_reaped", "result": "accepted"}}
                blocked = []
                for index in range(52):
                    execution_id = f"blocked-{index:03d}"
                    command = runtime.command("work", execution_id=execution_id, idempotency_key=execution_id,
                        correlation_id=execution_id, timeout_seconds=120, payload={})
                    runtime.submit(command)
                    lease = runtime.kernel.claim_and_start("worker", execution_id=execution_id, lease_seconds=300)
                    runtime.kernel.register_supervisor_obligation(lease)
                    runtime.kernel._begin_budget_sample(execution_id, timeout_seconds=1)
                    result = make_result(runtime.kernel, lease)
                    journal.record(lease, result, evidence=confirmed, timeout_seconds=1)
                    blocked.append((execution_id, result.result_id))
                late = runtime.command("work", execution_id="later", idempotency_key="later",
                    correlation_id="later", timeout_seconds=120, payload={})
                runtime.submit(late)
                lease = runtime.kernel.claim_and_start("worker", execution_id="later", lease_seconds=300)
                runtime.kernel.register_supervisor_obligation(lease)
                result = make_result(runtime.kernel, lease)
                journal.record(lease, result, evidence=confirmed, timeout_seconds=1)
                self.assertEqual(len(journal.pending(limit=50, timeout_seconds=1)), 50)
                # An in-flight receipt must not stall the cursor; it must be
                # revisited after its active owner relinquishes it.
                first_key = ("blocked-000", 1, 1)
                with runtime._settlement_inflight_lock:
                    runtime._settlement_inflight.add(first_key)
                reports = []
                for _ in range(120):
                    batch = runtime.recover_completions(limit=50, timeout_seconds=.5)
                    self.assertLessEqual(len(batch), 50)
                    reports.extend(batch)
                    observed = {item.get("execution_id") for item in reports if item["state"] == "pending"}
                    later_recorded = any(item.get("execution_id") == "later" and item["state"] == "recorded"
                                         for item in reports)
                    # The Kernel result can commit before its journal receipt
                    # transitions to recorded; wait for both durable outcomes.
                    if (runtime.kernel.get("later").state == "succeeded"
                            and later_recorded
                            and {execution_id for execution_id, _ in blocked[1:]} <= observed):
                        break
                self.assertEqual(runtime.kernel.get("later").result.to_dict(), result.to_dict())
                self.assertTrue(any(item.get("execution_id") == "later" and item["state"] == "recorded" for item in reports))
                expected_blocked = {execution_id for execution_id, _ in blocked[1:]}
                # The later receipt may also report pending transiently before it is recorded.
                pending_ids = {item.get("execution_id") for item in reports
                               if item["state"] == "pending" and item.get("execution_id") is not None}
                self.assertLessEqual(pending_ids, expected_blocked | {"later"})
                seen_blocked = pending_ids & expected_blocked
                self.assertEqual(seen_blocked, expected_blocked)
                with runtime._settlement_inflight_lock:
                    runtime._settlement_inflight.remove(first_key)
                # A valid cursor can be just past the formerly in-flight row.
                # Fifty bounded reads cannot traverse all 52 remaining rows
                # in a single call, even without any timeout or contention.
                with journal._connection(1, write=True) as connection:
                    connection.execute('UPDATE settlement_recovery_cursor SET last_rowid='
                                       '(SELECT rowid FROM settlement_records WHERE execution_id=?)',
                                       ('blocked-000',))
                wrap = runtime.recover_completions(limit=50, timeout_seconds=.5)
                self.assertFalse(any(item.get("execution_id") == "blocked-000" for item in wrap))
                for _ in range(120):
                    wrap = runtime.recover_completions(limit=50, timeout_seconds=.5)
                    if any(item.get("execution_id") == "blocked-000" and item["state"] == "pending" for item in wrap):
                        break
                else:
                    self.fail('formerly in-flight receipt was not revisited across bounded scans')
                self.assertEqual(journal.inspect("later", timeout_seconds=1)[0]["state"], "recorded")
                self.assertEqual(runtime.kernel.inspect_supervisor_obligations("later")["obligations"][0]["resolution"]["result_id"], result.result_id)
                for execution_id, result_id in blocked:
                    record = journal.inspect(execution_id, timeout_seconds=1)[0]
                    self.assertIn(record["state"], ("pending", "error"))
                    self.assertEqual(record["result"]["result_id"], result_id)
                    self.assertEqual(runtime.kernel.get(execution_id).state, "running")
                    self.assertEqual(runtime.kernel.inspect_supervisor_obligations(execution_id)["obligations"][0]["state"], "unresolved")
                with journal._connection(1) as connection:
                    prior_cursor = tuple(connection.execute('SELECT last_rowid FROM settlement_recovery_cursor').fetchone())
                self.assertIsNotNone(prior_cursor[0])
                runtime.close()
                reopened = Kernel.open_sqlite(Path(directory) / "kernel.sqlite", {"work": _never_invoked}, isolation_mode="thread")
                try:
                    with reopened._settlement_journal._connection(1) as connection:
                        self.assertEqual(tuple(connection.execute('SELECT last_rowid FROM settlement_recovery_cursor').fetchone()), prior_cursor)
                    after_restart = reopened.recover_completions(limit=50, timeout_seconds=.5)
                    self.assertTrue(any(item.get("execution_id", "").startswith("blocked-") and item["state"] == "pending" for item in after_restart))
                finally:
                    reopened.close()
            finally:
                runtime.close()
