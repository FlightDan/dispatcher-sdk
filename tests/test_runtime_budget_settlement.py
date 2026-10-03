"""Original SDK completion budgets settle atomically with exact result facts."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import time
import unittest

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel.budget import (
    BudgetClockUnknownError, BudgetEnvelope, DeadlineConstraint, sample_clock,
)
from dispatcher_sdk.execution_kernel.contracts import (
    ExecutionCommandV2, ExecutionError, ExecutionResultV2, RetryPolicy,
)
from dispatcher_sdk.execution_kernel.errors import (
    InvalidStateTransitionError, StaleFenceError,
)
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel


class RuntimeBudgetSettlementTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-budget-settlement-")
        self.wall = [100.0]
        self.kernel = SQLiteKernel(self.root / "kernel.sqlite3", now=lambda: self.wall[0])
        self.addCleanup(lambda: self.kernel.close())
        self.command = ExecutionCommandV2("work", "work", "budget-settlement-v1", "root", None,
            "handler", 1, RetryPolicy(max_attempts=3, retry_timeouts=True), 10, {})
        self.kernel.submit(self.command)
        self.lease = self.kernel.claim_and_start("worker", execution_id="work", lease_seconds=90)
        self.prepared = self.kernel._prepare_handler_entry(self.lease)
        self.envelope = self.prepared.enter_handler(10, origin_id="execution:work",
            sample=sample_clock(wall_time=self.wall[0]))
        self.evidence = {"test": self.id(), "kernel_path": self.kernel.db_path, "records": []}

    def tearDown(self):
        path = self.root / "evidence.json"
        path.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
        print("budget_settlement_evidence=" + str(path), flush=True)

    def confirm(self):
        self.envelope = self.kernel.confirm_handler_entry(self.lease, self.envelope)

    def floor(self, wall=112.0):
        return self.envelope.recheckpoint(sample=sample_clock(wall_time=wall))

    def result(self, *, timeout=False, retryable=False):
        snapshot = self.kernel.get("work")
        return ExecutionResultV2("original-result", "work", "timed_out" if timeout else "failed",
            self.lease.attempt, self.lease.fence, [], snapshot.started_at, 100.0,
            "root", None, None, ExecutionError("original_timeout" if timeout else "original_provider_error",
                "raw original failure", retryable=retryable,
                details={"original": [True, 1, 1.0, "raw"]}))

    def limits(self):
        return self.kernel.get_execution_limits("work")

    def test_completed_timeout_persists_forward_floor_before_retry_after_wall_rollback(self):
        self.confirm()
        result = self.result(timeout=True, retryable=True)
        observed = self.floor()
        original = result.to_json()
        settled = self.kernel._complete_sdk_result(self.lease, result, budget_envelope=observed)
        self.assertEqual(settled.state, "queued")
        persisted = BudgetEnvelope.from_dict(self.limits()["envelope"])
        self.assertEqual(persisted.constraints, observed.constraints)
        self.assertEqual(persisted.view(sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)
        event = next(event for event in self.kernel.events("work") if event["event_type"] == "retry_scheduled")
        self.assertEqual(ExecutionResultV2.from_dict(event["data"]["result"]).to_json(), original)
        retry = self.kernel.claim_and_start("retry", execution_id="work", lease_seconds=90)
        inherited = self.kernel.admission_budget(retry)
        self.assertEqual(inherited.view(sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)
        self.evidence["records"].append({"original": result.to_dict(), "observed": observed.to_dict(),
            "persisted": persisted.to_dict(), "retry_budget": inherited.to_dict()})

    def test_denied_retry_can_settle_original_confirmed_inherited_floor_without_new_entry(self):
        self.confirm()
        self.kernel._complete_sdk_result(self.lease, self.result(timeout=True, retryable=True),
            budget_envelope=self.floor())
        inherited_limits = self.limits()
        retry = self.kernel.claim_and_start("retry", execution_id="work", lease_seconds=90)
        snapshot = self.kernel.get("work")
        denied = ExecutionResultV2("denied-result", "work", "timed_out", retry.attempt, retry.fence,
            [], snapshot.started_at, 100, "root", None, None,
            ExecutionError("original_timeout", "original window spent", retryable=False, details={}))
        inherited = self.kernel.admission_budget(retry)
        settled = self.kernel._complete_sdk_result(retry, denied, budget_envelope=inherited)
        self.assertEqual(settled.result.to_json(), denied.to_json())
        self.assertEqual((self.limits()["entry_attempt"], self.limits()["entry_fence"]),
                         (inherited_limits["entry_attempt"], inherited_limits["entry_fence"]))
        self.assertEqual(self.limits()["entry_state"], "confirmed")

    def test_exact_terminal_duplicate_discharge_tightens_floor_without_changing_result(self):
        self.confirm()
        result = self.result()
        first = self.kernel.complete(self.lease, result)
        observed = self.floor()
        second = self.kernel._complete_sdk_result(self.lease, result,
            budget_envelope=observed, settlement=True)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(second.result.to_json(), result.to_json())
        self.assertEqual(self.limits()["entry_state"], "confirmed")
        self.assertGreaterEqual(self.limits()["envelope"]["checkpoint"]["wall_at"], 112)
        # Replaying an older original checkpoint cannot undo the stronger floor.
        self.kernel._complete_sdk_result(self.lease, result, budget_envelope=self.envelope, settlement=True)
        self.assertGreaterEqual(self.limits()["envelope"]["checkpoint"]["wall_at"], 112)

    def test_real_writer_contention_retains_exact_receipt_and_reopen_restores_same_budget(self):
        self.confirm()
        result, observed = self.result(), self.floor()
        before = self.limits()
        journal = SettlementJournal(self.root / "settlements.sqlite3", source_id="host",
            kernel_path=self.kernel.db_path)
        writer = sqlite3.connect(self.kernel.db_path, timeout=.03)
        writer.execute("BEGIN IMMEDIATE")
        try:
            receipt = journal.record(self.lease, result,
                evidence={"budget_envelope": observed.to_dict()}, timeout_seconds=.1)
            started = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError) as caught:
                self.kernel._complete_sdk_result(self.lease, result,
                    budget_envelope=observed, timeout_seconds=.03)
            self.assertIn("database is locked", str(caught.exception))
            if getattr(caught.exception, "sqlite_errorcode", None) is not None:
                self.assertEqual(caught.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
            self.assertLess(time.monotonic() - started, .15)
            self.assertEqual(self.kernel.get("work").state, "running")
            self.assertEqual(self.limits(), before)
        finally:
            writer.rollback()
            writer.close()
        self.kernel.close()
        self.wall[0] = self.lease.expires_at + 1
        self.kernel = SQLiteKernel(self.root / "kernel.sqlite3", now=lambda: self.wall[0])
        retained = journal.pending()[0]
        restored = self.kernel._complete_sdk_result(self.lease,
            ExecutionResultV2.from_dict(retained["result"]),
            budget_envelope=BudgetEnvelope.from_dict(retained["evidence"]["budget_envelope"]),
            settlement=True)
        self.assertEqual(restored.result.to_json(), result.to_json())
        self.assertEqual(self.limits()["envelope"]["constraints"], observed.to_dict()["constraints"])
        self.assertEqual(BudgetEnvelope.from_dict(self.limits()["envelope"]).view(
            sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)
        self.evidence["records"].append({"receipt": receipt, "restored": restored.to_dict(),
                                         "limits": self.limits()})

    def test_cancelled_parent_result_wins_without_any_completion_floor_write(self):
        self.confirm()
        result, observed, before = self.result(), self.floor(), self.limits()
        cancelled = self.kernel.cancel("work", lease=self.lease, reason="original cancellation")
        with self.assertRaises(InvalidStateTransitionError):
            self.kernel._complete_sdk_result(self.lease, result, budget_envelope=observed, settlement=True)
        self.assertEqual(self.kernel.get("work").to_dict(), cancelled.to_dict())
        self.assertEqual(self.limits(), before)

    def test_old_attempt_cannot_tighten_new_attempt_or_replace_its_result(self):
        self.confirm()
        result, observed = self.result(timeout=True, retryable=True), self.floor()
        self.kernel.complete(self.lease, result)
        current = self.kernel.claim_and_start("new-worker", execution_id="work", lease_seconds=90)
        self.kernel._prepare_handler_entry(current)
        before = self.limits()
        with self.assertRaises(StaleFenceError):
            self.kernel._complete_sdk_result(self.lease, result, budget_envelope=observed, settlement=True)
        self.assertEqual(self.limits(), before)
        self.assertEqual(self.kernel.get("work").lease, current)

    def test_weakened_constraints_roll_back_budget_and_terminal_result_together(self):
        self.confirm()
        before = self.limits()
        weaker = replace(self.floor(), constraints=tuple(
            replace(constraint, deadline_at=constraint.deadline_at + 1) for constraint in self.envelope.constraints))
        with self.assertRaises(ValueError):
            self.kernel._complete_sdk_result(self.lease, self.result(), budget_envelope=weaker)
        self.assertEqual(self.kernel.get("work").state, "running")
        self.assertEqual(self.limits(), before)

    def test_first_pending_entry_completion_records_facts_without_confirming_entry(self):
        observed = self.floor()
        result = self.result(timeout=True)
        settled = self.kernel._complete_sdk_result(self.lease, result, budget_envelope=observed)
        self.assertEqual(settled.result.to_json(), result.to_json())
        self.assertEqual(self.limits()["entry_state"], "pending")
        self.assertEqual(self.limits()["envelope"]["constraints"], observed.to_dict()["constraints"])

    def test_completion_without_actual_entry_preserves_pending_without_fabricated_cutoff(self):
        result = self.result()
        settled = self.kernel._complete_sdk_result(self.lease, result, budget_envelope=self.prepared)
        self.assertEqual(settled.result.to_json(), result.to_json())
        self.assertEqual(self.limits()["entry_state"], "pending")
        self.assertEqual(self.limits()["envelope"]["constraints"], [])
        self.assertIsNone(self.limits()["envelope"]["started_at"])

    def test_no_observed_envelope_retains_public_completion_behavior(self):
        before = self.limits()
        result = self.result()
        settled = self.kernel._complete_sdk_result(self.lease, result, budget_envelope=None)
        self.assertEqual(settled.result.to_json(), result.to_json())
        self.assertEqual(self.limits(), before)

    def test_contained_worker_parent_envelope_cannot_remove_durable_entry_cutoff(self):
        self.confirm()
        original = self.limits()
        parent_view = self.prepared.recheckpoint(sample=sample_clock(wall_time=112))
        settled = self.kernel._complete_sdk_result(self.lease, self.result(timeout=True),
            budget_envelope=parent_view)
        self.assertEqual(settled.state, "timed_out")
        self.assertEqual(self.limits()["envelope"]["constraints"], original["envelope"]["constraints"])
        self.assertEqual(self.limits()["envelope"]["started_at"], original["envelope"]["started_at"])
        self.assertEqual(self.limits()["entry_state"], "confirmed")
        self.assertGreaterEqual(self.limits()["envelope"]["checkpoint"]["wall_at"], 112)

    def test_preentry_refusal_without_limits_retains_only_pending_inherited_floor(self):
        self.kernel.submit(replace(self.command, execution_id="unprepared", idempotency_key="unprepared"))
        lease = self.kernel.claim_and_start("worker", execution_id="unprepared", lease_seconds=90)
        snapshot = self.kernel.get("unprepared")
        result = ExecutionResultV2("unprepared-result", "unprepared", "timed_out", lease.attempt,
            lease.fence, [], snapshot.started_at, 100, "root", None, None,
            ExecutionError("original_timeout", "inherited window spent", retryable=False, details={}))
        inherited = BudgetEnvelope((DeadlineConstraint("parent:original", "parent", 99),),
                                   sample_clock(wall_time=100))
        settled = self.kernel._complete_sdk_result(lease, result,
            budget_envelope=inherited)
        self.assertEqual(settled.state, "timed_out")
        limits = self.kernel.get_execution_limits("unprepared")
        self.assertEqual(limits["entry_state"], "pending")
        self.assertEqual(limits["envelope"]["constraints"], inherited.to_dict()["constraints"])
        self.assertIsNone(limits["envelope"]["started_at"])

    def test_unentered_inherited_metadata_can_settle_without_handler_confirmation(self):
        self.kernel.submit(replace(self.command, execution_id="unentered", idempotency_key="unentered"))
        inherited = BudgetEnvelope((DeadlineConstraint("parent:original", "parent", 99),),
                                   sample_clock(wall_time=100))
        with self.kernel._transaction() as (connection, _):
            connection.execute("INSERT INTO kernel_execution_limits(execution_id,envelope_json) VALUES(?,?)",
                               ("unentered", json.dumps(inherited.to_dict())))
        lease = self.kernel.claim_and_start("worker", execution_id="unentered", lease_seconds=90)
        snapshot = self.kernel.get("unentered")
        result = ExecutionResultV2("unentered-result", "unentered", "timed_out", lease.attempt,
            lease.fence, [], snapshot.started_at, 100, "root", None, None,
            ExecutionError("original_timeout", "inherited window spent", retryable=False, details={}))
        settled = self.kernel._complete_sdk_result(lease, result,
            budget_envelope=inherited.recheckpoint(sample=sample_clock(wall_time=112)))
        self.assertEqual(settled.result.to_json(), result.to_json())
        limits = self.kernel.get_execution_limits("unentered")
        self.assertEqual(limits["entry_state"], "unentered")
        self.assertIsNone(limits["entry_attempt"])
        self.assertIsNone(limits["entry_fence"])
        self.assertIsNone(limits["envelope"]["started_at"])
        self.assertGreaterEqual(limits["envelope"]["checkpoint"]["wall_at"], 112)

    def test_verified_receipt_floor_proves_original_completion_after_wall_rollback(self):
        self.confirm()
        original = replace(self.result(), completed_at=105)
        retained = self.floor()
        before = self.limits()
        # Public completion has no retained same-domain time evidence.
        with self.assertRaises(StaleFenceError):
            self.kernel.complete(self.lease, original)
        self.assertEqual(self.limits(), before)
        settled = self.kernel._complete_sdk_result(self.lease, original,
            budget_envelope=retained, settlement=True)
        self.assertEqual(settled.result.to_json(), original.to_json())
        self.assertGreaterEqual(self.limits()["envelope"]["checkpoint"]["wall_at"], 112)
        self.evidence["records"].append({"original": original.to_dict(), "retained": retained.to_dict(),
                                         "settled": settled.to_dict()})

    def test_receipt_floor_cannot_prove_completion_after_original_lease_expiry(self):
        self.confirm()
        original = replace(self.result(), completed_at=self.lease.expires_at + 1)
        before = self.limits()
        with self.assertRaises(StaleFenceError):
            self.kernel._complete_sdk_result(self.lease, original,
                budget_envelope=self.floor(self.lease.expires_at + 2), settlement=True)
        self.assertEqual(self.limits(), before)
        self.assertEqual(self.kernel.get("work").state, "running")

    def test_unverified_clock_domain_cannot_prove_original_completion(self):
        self.confirm()
        before = self.limits()
        retained = self.floor()
        unrelated = replace(retained, checkpoint=replace(retained.checkpoint, domain_id="other-domain"))
        with self.assertRaises(BudgetClockUnknownError):
            self.kernel._complete_sdk_result(self.lease, replace(self.result(), completed_at=105),
                budget_envelope=unrelated, settlement=True)
        self.assertEqual(self.limits(), before)
        self.assertEqual(self.kernel.get("work").state, "running")


if __name__ == "__main__":
    unittest.main()
