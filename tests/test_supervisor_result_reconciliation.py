"""Host-verifier contract tests; the verifier is simulated, not host isolation proof."""
import contextlib
import multiprocessing
from dataclasses import replace
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from dispatcher_sdk.execution_kernel import (CASConflictError, ExecutionLease, ExecutionResultV2, InvalidStateTransitionError,
    SQLiteKernel, StaleFenceError, StorageIsolationError)
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from tests.test_execution_kernel_v2_sqlite import make_command, make_result


def _crash_after_result(path, pipe):
    kernel = SQLiteKernel(path)
    kernel.submit(make_command("first", attempts=3))
    lease = kernel.claim_and_start("worker", execution_id="first", lease_seconds=0.5)
    kernel.register_supervisor_obligation(lease)
    result = make_result(kernel, lease, status="failed", retryable=True)
    envelope = BudgetEnvelope((), sample_clock())
    pipe.send((lease.to_dict(), result.to_dict(), envelope.to_dict()))
    pipe.close()
    os._exit(0)


class SupervisorResultReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "kernel.sqlite"
        self.proof = None
        self.calls = 0
        self.revoke_on_call = None
        self.change_store_on_call = None
        def verify(credential):
            self.calls += 1
            if credential != "host" or self.calls == self.revoke_on_call or self.proof is None:
                raise ValueError("revoked")
            if self.calls == self.change_store_on_call:
                return dict(self.proof, supervisor_result_reconciliation=dict(
                    self.proof["supervisor_result_reconciliation"], kernel_store_id="other-store"))
            return self.proof
        self.verify = verify
        self.kernel = SQLiteKernel(self.path, authority_verifier=verify)
        self.addCleanup(self.kernel.close)

    def authority(self, lease, result, budget, *, expires=None):
        decision = {"kernel_store_id": self.kernel.kernel_store_identity(), "lease": lease.to_dict(), "result": result.to_dict(),
                    "budget_envelope": budget.to_dict(), "cleanup": "confirmed",
                    "cleanup_evidence": "host-cleanup-receipt"}
        self.proof = {"principal": "host", "expires_at": expires or time.time() + 60,
                      "permissions": [(lease.execution_id, "kernel:reconcile_supervisor_result")],
                      "supervisor_result_reconciliation": decision}

    def reconcile(self, lease, result, budget):
        return self.kernel.reconcile_supervisor_result("host", lease=lease, result=result,
            budget_envelope=budget, kernel_store_id=self.proof["supervisor_result_reconciliation"]["kernel_store_id"],
            cleanup_evidence="host-cleanup-receipt")

    def prepare(self):
        self.kernel.submit(make_command("first", attempts=3))
        lease = self.kernel.claim_and_start("worker", execution_id="first")
        self.kernel.register_supervisor_obligation(lease)
        result = make_result(self.kernel, lease, status="failed", retryable=True)
        budget = BudgetEnvelope((), sample_clock())
        self.authority(lease, result, budget)
        return lease, result, budget

    def test_process_crash_lost_ack_and_exact_retry(self):
        self.kernel.close()
        parent, child = multiprocessing.get_context("spawn").Pipe(duplex=False)
        process = multiprocessing.get_context("spawn").Process(target=_crash_after_result, args=(self.path, child))
        process.start()
        child.close()
        self.assertTrue(parent.poll(10), "child did not return its retained original result")
        lease, result, budget = parent.recv()
        process.join(10)
        self.assertEqual(process.exitcode, 0)
        lease, result, budget = ExecutionLease.from_dict(lease), ExecutionResultV2.from_dict(result), BudgetEnvelope.from_dict(budget)
        self.kernel = SQLiteKernel(self.path, authority_verifier=self.verify)
        self.addCleanup(self.kernel.close)
        time.sleep(max(0, lease.expires_at - time.time()) + .05)
        self.kernel.submit(make_command("other"))
        self.assertEqual(self.kernel.claim("other", execution_id="other").execution_id, "other")
        self.assertIsNone(self.kernel.claim("retry", execution_id="first"))
        self.authority(lease, result, budget)
        self.assertEqual(self.reconcile(lease, result, budget).state, "queued")
        event_count = len(self.kernel.events("first"))
        self.assertEqual(self.reconcile(lease, result, budget).state, "queued")
        self.assertEqual(len(self.kernel.events("first")), event_count)
        self.assertEqual(self.kernel.inspect_supervisor_obligations("first")["obligations"][0]["resolution"]["decision"]["result"], result.to_dict())
        next_lease = self.kernel.claim("retry", execution_id="first")
        self.assertEqual(next_lease.attempt, 2)
        with self.assertRaises(StaleFenceError):
            self.reconcile(lease, result, budget)

    def test_wrong_expired_and_revoked_proof_stays_blocked(self):
        lease, result, budget = self.prepare()
        changed = replace(result, result_id="different-result")
        with self.assertRaises(StorageIsolationError):
            self.reconcile(lease, changed, budget)
        self.proof["supervisor_result_reconciliation"]["cleanup"] = "unknown"
        with self.assertRaises(StorageIsolationError):
            self.reconcile(lease, result, budget)
        self.authority(lease, result, budget, expires=time.time() - 1)
        with self.assertRaises(StorageIsolationError):
            self.reconcile(lease, result, budget)
        self.authority(lease, result, budget)
        self.revoke_on_call = self.calls + 2
        with self.assertRaises(StorageIsolationError):
            self.reconcile(lease, result, budget)
        self.assertEqual(self.kernel.get("first").state, "running")
        self.assertEqual(self.kernel.inspect_supervisor_obligations("first")["obligations"][0]["state"], "unresolved")

    def test_changed_store_authority_at_precommit_rolls_back(self):
        lease, result, budget = self.prepare()
        self.change_store_on_call = self.calls + 2
        with self.assertRaises(StorageIsolationError):
            self.reconcile(lease, result, budget)
        self.assertEqual(self.kernel.get("first").state, "running")
        self.assertEqual(self.kernel.inspect_supervisor_obligations("first")["obligations"][0]["state"], "unresolved")

    def test_unfinished_effect_and_cancellation_do_not_resolve(self):
        lease, result, budget = self.prepare()
        self.kernel.prepare_effect(lease, effect_id="pending", name="send", request={})
        self.assertEqual(self.reconcile(lease, result, budget).state, "recovery_required")
        self.assertEqual(self.kernel.inspect_supervisor_obligations("first")["obligations"][0]["state"], "unresolved")
        with self.assertRaises(StaleFenceError):
            self.reconcile(lease, result, budget)

    def test_cancel_wins(self):
        lease, result, budget = self.prepare()
        self.kernel.cancel("first", expected_revision=self.kernel.get("first").revision)
        with self.assertRaises(InvalidStateTransitionError):
            self.reconcile(lease, result, budget)
        self.assertEqual(self.kernel.inspect_supervisor_obligations("first")["obligations"][0]["state"], "unresolved")

    def test_cancel_after_retry_blocks_old_replay(self):
        lease, result, budget = self.prepare()
        self.assertEqual(self.reconcile(lease, result, budget).state, "queued")
        self.kernel.cancel("first", expected_revision=self.kernel.get("first").revision)
        with self.assertRaises(CASConflictError):
            self.reconcile(lease, result, budget)

    def test_unknown_clock_cannot_settle(self):
        lease, result, budget = self.prepare()
        budget = replace(budget, checkpoint=replace(budget.checkpoint, domain_id="unrelated-clock"))
        self.authority(lease, result, budget)
        with self.assertRaises(StorageIsolationError):
            self.reconcile(lease, result, budget)
        self.assertEqual(self.kernel.inspect_supervisor_obligations("first")["obligations"][0]["state"], "unresolved")

    def test_success_replay_and_changed_decision(self):
        lease, _, budget = self.prepare()
        result = make_result(self.kernel, lease)
        self.authority(lease, result, budget)
        self.assertEqual(self.reconcile(lease, result, budget).state, "succeeded")
        self.assertEqual(self.reconcile(lease, result, budget).result.to_dict(), result.to_dict())
        changed = replace(result, result_id="other-result")
        self.authority(lease, changed, budget)
        with self.assertRaises(CASConflictError):
            self.reconcile(lease, changed, budget)

    def test_other_store_identity_fails_closed(self):
        lease, result, budget = self.prepare()
        other_path = Path(self.temp.name) / "other.sqlite"
        with contextlib.closing(sqlite3.connect(self.path)) as source, source, contextlib.closing(sqlite3.connect(other_path)) as target, target:
            source.backup(target)
            target.execute("UPDATE kernel_store_identity SET store_id=? WHERE singleton=1", ("other-store",))
        with SQLiteKernel(other_path, authority_verifier=self.verify) as other:
            with self.assertRaises(StorageIsolationError):
                other.reconcile_supervisor_result("host", lease=lease, result=result, budget_envelope=budget,
                    kernel_store_id=self.proof["supervisor_result_reconciliation"]["kernel_store_id"],
                    cleanup_evidence="host-cleanup-receipt")
            self.assertEqual(other.inspect_supervisor_obligations("first")["obligations"][0]["state"], "unresolved")
