import dataclasses
import json
import math
import pickle
import subprocess
import sys
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.budget import (
    BudgetClockUnknownError,
    BudgetEnvelope,
    ClockCheckpoint,
    DeadlineConstraint,
    ExecutionBudget,
    sample_clock,
)


def checkpoint(wall=1000.0, elapsed=100.0, domain="host-boot-a", scope="boot"):
    return ClockCheckpoint(wall, elapsed, domain, scope)


class ExecutionBudgetTests(unittest.TestCase):
    def test_each_layer_limits_work_and_hard_deadlines(self):
        for source in ("run", "execution", "parent", "tool"):
            with self.subTest(source=source):
                bounds = tuple(DeadlineConstraint(layer, layer, 1020 if layer == source else 1100, 3)
                               for layer in ("run", "execution", "parent", "tool"))
                view = BudgetEnvelope(bounds, checkpoint()).view(sample=checkpoint())
                self.assertEqual(view.limiting_source, source)
                self.assertEqual(view.hard_limiting_source, source)
                self.assertEqual(view.remaining_work_seconds, 17)
                self.assertEqual(view.remaining_hard_seconds, 20)

    def test_work_and_hard_can_have_different_limiting_sources(self):
        bounds = (DeadlineConstraint("run-a", "run", 1100, 30),
                  DeadlineConstraint("tool-a", "tool", 1090, 0))
        view = BudgetEnvelope(bounds, checkpoint()).view(sample=checkpoint())
        self.assertEqual(view.limiting_source, "run")
        self.assertEqual(view.hard_limiting_source, "tool")
        self.assertEqual(view.remaining_work_seconds, 70)
        self.assertEqual(view.remaining_hard_seconds, 90)

    def test_reserve_is_inherited_once_and_tool_cannot_extend_parent(self):
        parent = DeadlineConstraint("parent-a", "parent", 1030, 10)
        envelope = BudgetEnvelope((parent, parent), checkpoint())
        self.assertEqual(envelope.constraints, (parent,))
        child = envelope.derive(source="tool", origin_id="tool-a", timeout_seconds=100,
                                reserve_seconds=5, sample=checkpoint(1005, 105))
        view = child.view(sample=checkpoint(1005, 105))
        self.assertEqual(view.effective_work_deadline_at, 1020)
        self.assertEqual(view.remaining_work_seconds, 15)
        self.assertEqual(view.remaining_hard_seconds, 25)
        self.assertEqual(child.constraints[0].reserve_seconds, 10)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            child.derive(source="parent", origin_id="parent-a", deadline_at=1031,
                         reserve_seconds=10, sample=checkpoint(1005, 105))

    def test_actual_entry_and_retry_do_not_regrant_original_timeout(self):
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", 1200),), checkpoint())
        entered = envelope.enter_handler(40, origin_id="execution-a", sample=checkpoint(1005, 105))
        self.assertEqual(entered.started_at, 1005)
        self.assertEqual(entered.constraints[-1].deadline_at, 1045)
        retry = entered.enter_handler(40, origin_id="execution-a", sample=checkpoint(1030, 130))
        self.assertEqual(retry.started_at, 1030)
        self.assertEqual(retry.constraints[-1].deadline_at, 1045)
        self.assertEqual(retry.view(sample=checkpoint(1030, 130)).remaining_work_seconds, 15)

    def test_continuous_rollback_still_spends_elapsed_budget(self):
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", 1030),), checkpoint())
        view = envelope.view(sample=checkpoint(900, 120))
        self.assertEqual(view.clock_status, "trusted")
        self.assertEqual(view.observed_at, 1020)
        self.assertEqual(view.remaining_work_seconds, 10)
        persisted = envelope.recheckpoint(sample=checkpoint(900, 120))
        self.assertEqual(persisted.checkpoint.wall_at, 1020)
        self.assertEqual(persisted.view(sample=checkpoint(901, 125)).remaining_work_seconds, 5)

    def test_elapsed_projection_never_subtracts_an_unchanged_wall_floor(self):
        # Adding the absolute elapsed value before subtracting it loses bits:
        # 105 + 333.2 - 333.2 is below 105 on these exact input floats.
        original = checkpoint(wall=105, elapsed=333.2)
        rollback = checkpoint(wall=100, elapsed=333.2)
        self.assertEqual(original.effective_time(rollback), 105)
        envelope = BudgetEnvelope((DeadlineConstraint('original', 'tool', 105),), original)
        for _ in range(20):
            envelope = envelope.recheckpoint(sample=rollback)
            self.assertEqual(envelope.checkpoint.wall_at, 105)
            self.assertEqual(envelope.view(sample=rollback).remaining_work_seconds, 0)

    def test_same_boot_restart_accounts_for_downtime_plus_rollback(self):
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", 1100),), checkpoint())
        restored = BudgetEnvelope.from_dict(json.loads(json.dumps(envelope.to_dict())))
        # Wall time exceeds the old watermark, but elapsed time exposes rollback.
        view = restored.view(sample=checkpoint(1010, 190))
        self.assertEqual(view.observed_at, 1090)
        self.assertEqual(view.remaining_hard_seconds, 10)

    def test_recovered_fractional_clock_anchor_cannot_regain_one_ulp_of_budget(self):
        original = BudgetEnvelope((DeadlineConstraint("original", "run", 1791192986),),
            checkpoint(wall=1791192976.1234567, elapsed=812174.123456789))
        advanced = original.recheckpoint(sample=checkpoint(wall=0, elapsed=812174.2234567889))
        restored = BudgetEnvelope.from_dict(json.loads(json.dumps(advanced.to_dict())))
        self.assertEqual(restored.constraints, original.constraints)
        for elapsed in (812174.2234567889, 812174.3234567889, 812175.123456789):
            with self.subTest(elapsed=elapsed):
                sample = checkpoint(wall=0, elapsed=elapsed)
                before, after = original.view(sample=sample), restored.view(sample=sample)
                self.assertGreaterEqual(after.observed_at, before.observed_at)
                self.assertLessEqual(after.remaining_work_seconds, before.remaining_work_seconds)
                self.assertLessEqual(after.remaining_hard_seconds, before.remaining_hard_seconds)

    def test_unknown_restart_refuses_business_without_inventing_remaining(self):
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", 1100),), checkpoint())
        samples = (checkpoint(1050, 150, "host-boot-b"),
                   checkpoint(1050, 50),
                   ClockCheckpoint(1050, 150, None, "unknown", "provider_unavailable"),
                   checkpoint(1050, 150, "host-boot-a", "process"))
        for current in samples:
            with self.subTest(current=current):
                view = envelope.view(sample=current)
                self.assertEqual(view.clock_status, "unknown")
                self.assertIsNone(view.remaining_hard_seconds)
                self.assertEqual(view.effective_hard_deadline_at, 1100)
                with self.assertRaises(BudgetClockUnknownError):
                    envelope.enter_handler(10, origin_id="execution-a", sample=current)
                with self.assertRaises(BudgetClockUnknownError):
                    envelope.derive(source="tool", origin_id="tool-a", timeout_seconds=5, sample=current)
                with self.assertRaises(BudgetClockUnknownError):
                    envelope.deadline_monotonic(sample=current)

    def test_wall_forward_jump_shortens_and_later_rollback_cannot_extend(self):
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", 1100),), checkpoint())
        advanced = envelope.recheckpoint(sample=checkpoint(1080, 110))
        self.assertEqual(advanced.view(sample=checkpoint(1030, 120)).remaining_work_seconds, 10)
        expired = advanced.view(sample=checkpoint(1035, 135))
        self.assertEqual(expired.remaining_work_seconds, 0)
        self.assertEqual(expired.remaining_hard_seconds, 0)

    def test_envelope_view_and_checkpoint_are_json_roundtrippable_and_pickleable(self):
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", 1100, 10),), checkpoint(), 1000)
        view = envelope.view(sample=checkpoint(1005, 105))
        for record in (envelope, view, envelope.checkpoint, envelope.constraints[0]):
            with self.subTest(record=type(record).__name__):
                encoded = json.loads(json.dumps(record.to_dict(), allow_nan=False))
                self.assertEqual(type(record).from_dict(encoded), record)
                self.assertEqual(pickle.loads(pickle.dumps(record)), record)
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(record, next(iter(record.__dataclass_fields__)), None)

    def test_json_validation_rejects_bad_types_and_forged_effective_view(self):
        for value in (True, "10", math.nan, math.inf, -1, 10**400):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    DeadlineConstraint("run-a", "run", value)
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", 1100),), checkpoint())
        encoded = envelope.to_dict()
        for field, value in (("schema_version", True), ("constraints", {}), ("started_at", math.nan)):
            malformed = {**encoded, field: value}
            with self.assertRaises(ValueError):
                BudgetEnvelope.from_dict(malformed)
        with self.assertRaises(ValueError):
            BudgetEnvelope.from_dict({**encoded, "extra": 1})
        view = envelope.view(sample=checkpoint()).to_dict()
        with self.assertRaisesRegex(ValueError, "effective deadline"):
            ExecutionBudget.from_dict({**view, "effective_work_deadline_at": 1200})
        with self.assertRaisesRegex(ValueError, "remaining time"):
            ExecutionBudget.from_dict({**view, "remaining_work_seconds": 120})

    def test_local_deadline_mapping_has_no_remaining_regrant(self):
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", 1100, 10),), checkpoint())
        with patch("dispatcher_sdk.execution_kernel.budget.time.monotonic", return_value=500):
            self.assertEqual(envelope.deadline_monotonic(sample=checkpoint(1005, 105)), 585)
            self.assertEqual(envelope.deadline_monotonic(hard=True, sample=checkpoint(1005, 105)), 595)

    def test_provider_reports_native_or_process_continuity_explicitly(self):
        current = sample_clock(wall_time=1000)
        self.assertEqual(current.wall_at, 1000)
        self.assertIn(current.domain_scope, ("boot", "process"))
        if current.domain_scope == "process":
            self.assertEqual(current.unknown_reason, "restart_continuity_unavailable")
        else:
            self.assertIsNone(current.unknown_reason)

    def test_provider_domain_transfer_across_real_fresh_interpreter(self):
        current = sample_clock()
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", current.wall_at + 30),), current)
        source = (
            "import json; from dispatcher_sdk.execution_kernel.budget import sample_clock; "
            "print(json.dumps(sample_clock().to_dict()))"
        )
        completed = subprocess.run([sys.executable, "-c", source], check=True,
                                   capture_output=True, text=True, timeout=10)
        fresh = ClockCheckpoint.from_dict(json.loads(completed.stdout))
        view = envelope.view(sample=fresh)
        if current.domain_scope == "boot" and fresh.domain_scope == "boot":
            self.assertEqual(current.domain_id, fresh.domain_id)
            self.assertEqual(view.clock_status, "trusted")
            self.assertLess(view.remaining_hard_seconds, 30)
            self.assertGreater(view.remaining_hard_seconds, 0)
        else:
            self.assertEqual(view.clock_status, "unknown")


if __name__ == "__main__":
    unittest.main()
