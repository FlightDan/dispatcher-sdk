"""Real SQLite evidence for retained exact budget observation ownership."""

from contextlib import contextmanager
import gc
import json
import sqlite3
import time
import unittest
import weakref

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture
from dispatcher_sdk.execution_kernel.children import _RetryWindow
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.errors import CASConflictError, StaleFenceError
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory


class _ReleaseInterruptConnection:
    """Interrupt after a real RELEASE while the outer transaction is active."""

    def __init__(self, connection):
        self.connection = connection
        self.enabled = False
        self.interrupted = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *arguments):
        result = self.connection.execute(statement, *arguments)
        if (self.enabled and not self.interrupted
                and statement == "RELEASE kernel_operation"):
            self.interrupted = True
            raise KeyboardInterrupt("after actual RELEASE before COMMIT")
        return result


class BudgetOwnerRegistryTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-budget-owner-registry-")
        self.evidence = {"test": self.id()}
        self.addCleanup(self.save_evidence)

    def save_evidence(self):
        path = self.root / "evidence.json"
        path.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
        print("budget_owner_registry_evidence=" + str(path), flush=True)

    def parent(self, *, now=None):
        wall = [time.time()]
        kernel = SQLiteKernel(self.root / "kernel.sqlite3", now=now or (lambda: wall[0]),
            default_lease_seconds=90)
        self.addCleanup(kernel.close)
        kernel.submit(ExecutionCommandV2("parent", "parent", "owner-registry", "owner-proof", None,
            "work", 1, RetryPolicy(), 30, {}))
        lease = kernel.claim_and_start("actual-parent-owner")
        prepared = kernel.prepare_execution_budget(lease)
        original = prepared.enter_handler(30, origin_id="execution:parent",
            sample=sample_clock(wall_time=prepared.checkpoint.wall_at))
        original = kernel.confirm_handler_entry(lease, original)
        return kernel, original, wall

    def reader(self, kernel):
        reader = sqlite3.connect(kernel.db_path, timeout=.1)
        self.addCleanup(reader.close)
        return reader

    def test_expired_short_window_owner_survives_dropped_call_and_drains_same_fact(self):
        kernel, parent, wall = self.parent()
        child = parent.derive(source="tool", origin_id="original-short-call", timeout_seconds=.2,
            sample=sample_clock(wall_time=parent.checkpoint.wall_at))
        window = _RetryWindow(child, kernel, execution_id="parent")
        original_deadline = window.deadline
        owner_ref, window_ref = weakref.ref(window._capture), weakref.ref(window)
        begin = kernel._begin_budget_sample
        writer = self.reader(kernel)
        self.addCleanup(writer.rollback)
        tokens = []
        baseline = wall[0]
        before = kernel.get("parent").to_dict()

        def arm_and_lock(execution_id, **options):
            token = begin(execution_id, **options)
            tokens.append(token)
            writer.execute("BEGIN IMMEDIATE")
            wall[0] = baseline + 1
            return token

        kernel._begin_budget_sample = arm_and_lock
        try:
            window.remaining()
            self.fail("real post-arm writer did not prevent ACK")
        except sqlite3.OperationalError as error:
            captured = error.budget_sample_envelope
            token = error.budget_sample_token
            self.assertEqual(token, tokens[0])
            self.assertGreaterEqual(captured.checkpoint.wall_at, baseline + 1)
            self.assertEqual(window._project_elapsed(), 0)
            self.assertLessEqual(window.deadline, original_deadline)
            self.evidence.update(raw_error={"type": type(error).__name__, "message": str(error)},
                original_child=child.to_dict(), captured=captured.to_dict(), token=token,
                original_native_deadline=original_deadline, expired_native_deadline=window.deadline)
            # The helper's raw error otherwise retains the original caller's
            # traceback. Remove that test reference without altering the fact.
            error.__traceback__ = None
            error.__context__ = None
        finally:
            kernel._begin_budget_sample = begin
        def forbid_new_arm(*arguments, **options):
            raise AssertionError("factual registry drain attempted another budget observation")

        kernel._begin_budget_sample = forbid_new_arm
        self.addCleanup(setattr, kernel, "_begin_budget_sample", begin)
        window = None
        gc.collect()
        self.assertIsNone(window_ref(), "expired original call remains externally retained")
        self.assertIsNotNone(owner_ref(), "Kernel did not retain its exact live fact owner")
        self.assertIs(kernel._budget_sample_owners[token], owner_ref())
        writer.rollback()
        wall[0] = baseline

        with SQLiteKernel(kernel.db_path, now=lambda: wall[0]) as fresh:
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved"):
                fresh._sample_budget("parent", parent, timeout_seconds=.02)
            self.assertTrue(kernel._budget_samples_pending())
            self.assertFalse(kernel._drain_budget_samples(time.monotonic() + .1))
            self.assertEqual(kernel._budget_sample_owners, {})
            self.assertEqual(fresh._connection.execute("SELECT token FROM kernel_budget_samples").fetchall(), [])
            canonical = BudgetEnvelope.from_dict(fresh.get_execution_limits("parent")["envelope"])
            self.assertEqual(canonical.constraints, parent.constraints)
            self.assertEqual(canonical.started_at, parent.started_at)
            self.assertGreaterEqual(canonical.checkpoint.wall_at, captured.checkpoint.wall_at)
            self.assertEqual(fresh.get("parent").to_dict(), before)
            self.assertEqual(tokens, [token])
            self.evidence.update(canonical=canonical.to_dict(), fresh_fenced=True,
                owner_retained_after_call_collection=True, same_token_drained=True)

    def test_interruption_after_real_ack_commit_reconciles_only_original_live_owner(self):
        kernel, parent, wall = self.parent()
        capture = _KernelBudgetCapture(kernel, "parent")
        transaction, begin = kernel._transaction, kernel._begin_budget_sample
        tokens, interrupted = [], []
        reader = self.reader(kernel)
        wall[0] += 1

        def count_arm(execution_id, **options):
            token = begin(execution_id, **options)
            tokens.append(token)
            return token

        @contextmanager
        def commit_then_interrupt(**options):
            with transaction(**options) as current:
                yield current
            if capture._ack_token is not None and not interrupted:
                interrupted.append(capture._ack_token)
                self.assertIsNone(reader.execute("SELECT token FROM kernel_budget_samples").fetchone())
                raise KeyboardInterrupt("after real ACK COMMIT before owner retirement")

        kernel._begin_budget_sample = count_arm
        kernel._transaction = commit_then_interrupt
        try:
            with self.assertRaises(KeyboardInterrupt) as caught:
                capture(parent, timeout_seconds=.1)
            token, captured = capture._pending
            self.assertEqual(token, interrupted[0])
            self.assertEqual(caught.exception.budget_sample_token, token)
            self.assertEqual(capture._ack_token, token)
            self.assertIs(kernel._budget_sample_owners[token], capture)
            committed = BudgetEnvelope.from_dict(kernel.get_execution_limits("parent")["envelope"])
            self.assertGreaterEqual(committed.checkpoint.wall_at, captured.checkpoint.wall_at)
            wall[0] -= 1
            with SQLiteKernel(kernel.db_path, now=lambda: wall[0]) as fresh:
                foreign = _KernelBudgetCapture(fresh, "parent")
                with self.assertRaises(CASConflictError):
                    fresh._finish_budget_sample(token, "parent", captured, timeout_seconds=.1, _owner=foreign)
            foreign = _KernelBudgetCapture(kernel, "parent")
            with self.assertRaises(CASConflictError):
                kernel._finish_budget_sample(token, "parent", captured, timeout_seconds=.1, _owner=foreign)
            resumed = capture.finish_pending(parent, timeout_seconds=.1)
            self.assertIsNone(capture._pending)
            self.assertEqual(kernel._budget_sample_owners, {})
            self.assertEqual(tokens, [token])
            self.assertEqual(resumed.constraints, parent.constraints)
            self.assertGreaterEqual(resumed.checkpoint.wall_at, captured.checkpoint.wall_at)
            self.evidence.update(raw_error=str(caught.exception), token=token,
                captured=captured.to_dict(), committed_before_interruption=committed.to_dict(),
                resumed=resumed.to_dict(), absent_token_reconciled_by_exact_owner=True)
        finally:
            kernel._transaction = transaction
            kernel._begin_budget_sample = begin

    def test_guard_arm_makes_no_raw_wall_observation_before_committed_marker(self):
        raw_observations = []
        inspection = [False]
        observer = [None]
        wall = [time.time()]

        def guarded_wall():
            if inspection[0]:
                markers = observer[0].execute("SELECT token FROM kernel_budget_samples").fetchall()
                self.assertEqual(len(markers), 1, "raw capture happened before a durable arm")
                raw_observations.append(markers[0][0])
            return wall[0]

        kernel, parent, _ = self.parent(now=guarded_wall)
        observer[0] = self.reader(kernel)
        capture = _KernelBudgetCapture(kernel, "parent")
        begin = kernel._begin_budget_sample
        tokens = []

        def observe_arm(execution_id, **options):
            self.assertEqual(raw_observations, [])
            self.assertEqual(observer[0].execute("SELECT token FROM kernel_budget_samples").fetchall(), [])
            token = begin(execution_id, **options)
            self.assertEqual(raw_observations, [], "guard-only arm sampled unprotected wall time")
            self.assertEqual(observer[0].execute("SELECT token FROM kernel_budget_samples").fetchone()[0], token)
            tokens.append(token)
            return token

        kernel._begin_budget_sample = observe_arm
        inspection[0] = True
        try:
            published = capture(parent, timeout_seconds=.1)
        finally:
            inspection[0] = False
            kernel._begin_budget_sample = begin
        self.assertEqual(raw_observations, tokens)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(observer[0].execute("SELECT token FROM kernel_budget_samples").fetchall(), [])
        self.assertEqual(published.constraints, parent.constraints)
        self.evidence.update(raw_wall_observed_committed_tokens=raw_observations,
            guard_arms=tokens, published=published.to_dict())

    def test_interrupt_after_real_release_rolls_back_writer_and_exact_owner_retries(self):
        kernel, parent, wall = self.parent()
        capture = _KernelBudgetCapture(kernel, "parent")
        original_connection = kernel._connection
        proxy = _ReleaseInterruptConnection(original_connection)
        kernel._connection = proxy
        finish, begin = kernel._finish_budget_sample, kernel._begin_budget_sample
        tokens = []
        reader = self.reader(kernel)
        before = BudgetEnvelope.from_dict(kernel.get_execution_limits("parent")["envelope"])
        wall[0] += 1

        def count_arm(execution_id, **options):
            token = begin(execution_id, **options)
            tokens.append(token)
            return token

        def interrupt_ack(*arguments, **options):
            proxy.enabled = True
            return finish(*arguments, **options)

        kernel._begin_budget_sample = count_arm
        kernel._finish_budget_sample = interrupt_ack
        try:
            with self.assertRaises(KeyboardInterrupt) as caught:
                capture(parent, timeout_seconds=.1)
            token, captured = capture._pending
            self.assertTrue(proxy.interrupted)
            self.assertFalse(original_connection.in_transaction, "interrupted RELEASE stranded a writer")
            self.assertEqual(reader.execute("SELECT token FROM kernel_budget_samples").fetchone()[0], token)
            reader.execute("BEGIN IMMEDIATE")
            reader.rollback()
            rolled_back = BudgetEnvelope.from_dict(kernel.get_execution_limits("parent")["envelope"])
            self.assertEqual(rolled_back, before)
            wall[0] -= 1
            resumed = capture.finish_pending(parent, timeout_seconds=.1)
            self.assertIsNone(capture._pending)
            self.assertEqual(tokens, [token])
            self.assertEqual(kernel._budget_sample_owners, {})
            self.assertEqual(reader.execute("SELECT token FROM kernel_budget_samples").fetchall(), [])
            self.assertEqual(resumed.constraints, parent.constraints)
            self.assertGreaterEqual(resumed.checkpoint.wall_at, captured.checkpoint.wall_at)
            self.evidence.update(raw_error=str(caught.exception), token=token,
                captured=captured.to_dict(), rolled_back=rolled_back.to_dict(), resumed=resumed.to_dict(),
                independent_writer_acquired_after_interrupt=True, same_token_acknowledged=True)
        finally:
            kernel._connection = original_connection
            kernel._finish_budget_sample = finish
            kernel._begin_budget_sample = begin

    def test_protected_ack_watermark_fences_managed_sibling_and_expired_lease_after_wall_rollback(self):
        wall = [time.time()]
        baseline = wall[0]
        forbid_raw = [False]
        raw_calls = []

        def raw_wall():
            if forbid_raw[0]:
                raise AssertionError("exact factual ACK attempted another raw wall observation")
            raw_calls.append(wall[0])
            return wall[0]

        kernel = SQLiteKernel(self.root / "kernel.sqlite3", now=raw_wall, default_lease_seconds=1)
        self.addCleanup(kernel.close)
        run_id = "original-managed-run"
        source_id, sibling_id = "sdk-managed:original-managed-run:source", "sdk-managed:original-managed-run:sibling"
        run_deadline = baseline + 4
        kernel.register_run_control(run_id, max_claims=3, deadline_at=run_deadline)
        kernel.set_run_control(run_id, expected_epoch=0, state="active", generation=0)

        def command(identity):
            return ExecutionCommandV2(identity, identity, "watermark-registry", run_id, None,
                "work", 1, RetryPolicy(), 2, {})

        kernel.submit_managed(command(source_id), run_id=run_id, generation=0)
        lease = kernel.claim_and_start("original-source-owner", start_safety_seconds=0)
        self.assertEqual(lease.execution_id, source_id)
        self.assertEqual(lease.expires_at, baseline + 2)
        prepared = kernel.prepare_execution_budget(lease)
        original = prepared.enter_handler(2, origin_id="execution:" + source_id,
            sample=sample_clock(wall_time=prepared.checkpoint.wall_at))
        original = kernel.confirm_handler_entry(lease, original)
        effect = kernel.prepare_effect(lease, effect_id="original-prepared-effect",
            name="original-effect", request={"original": 42})
        kernel.submit_managed(command(sibling_id), run_id=run_id, generation=0)
        source_before, sibling_before = kernel.get(source_id).to_dict(), kernel.get(sibling_id).to_dict()
        control_before = kernel.get_run_control(run_id)
        effect_events = kernel.effect_events(effect.effect_id)
        capture = _KernelBudgetCapture(kernel, source_id)
        begin = kernel._begin_budget_sample
        reader = self.reader(kernel)
        writer = self.reader(kernel)
        self.addCleanup(writer.rollback)
        tokens = []

        def arm_and_lock(execution_id, **options):
            token = begin(execution_id, **options)
            tokens.append(token)
            writer.execute("BEGIN IMMEDIATE")
            wall[0] = baseline + 6
            return token

        kernel._begin_budget_sample = arm_and_lock
        try:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                capture(original, timeout_seconds=.05)
            token, retained = capture._pending
            self.assertEqual(token, tokens[0])
            self.assertGreater(retained.checkpoint.wall_at, run_deadline)
            self.assertGreater(retained.checkpoint.wall_at, lease.expires_at)
            watermark_before = reader.execute("SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()[0]
            self.assertLess(watermark_before, retained.checkpoint.wall_at)
            writer.rollback()
            wall[0] = baseline
            raw_before_ack = len(raw_calls)
            forbid_raw[0] = True
            published = capture.finish_pending(original, timeout_seconds=.1)
            self.assertEqual(len(raw_calls), raw_before_ack)
            ack_snapshot = reader.execute(
                "SELECT c.watermark,l.envelope_json,(SELECT COUNT(*) FROM kernel_budget_samples) "
                "FROM kernel_clock c JOIN kernel_execution_limits l ON l.execution_id=? "
                "WHERE c.singleton=1", (source_id,)).fetchone()
            watermark_after = ack_snapshot[0]
            canonical_after = BudgetEnvelope.from_dict(json.loads(ack_snapshot[1]))
            self.assertGreaterEqual(watermark_after, canonical_after.checkpoint.wall_at)
            self.assertGreaterEqual(canonical_after.checkpoint.wall_at, retained.checkpoint.wall_at)
            self.assertEqual(ack_snapshot[2], 0)
            self.assertEqual(canonical_after.constraints, original.constraints)
            self.assertEqual(canonical_after.started_at, original.started_at)
            self.assertEqual(tokens, [token])
            self.evidence.update(raw_ack_failure={"type": type(caught.exception).__name__, "message": str(caught.exception)},
                token=token, original=original.to_dict(), retained=retained.to_dict(), published=published.to_dict(),
                original_lease=lease.to_dict(), original_control=control_before,
                watermark_before_ack=watermark_before, watermark_after_ack=watermark_after,
                canonical_after_ack=canonical_after.to_dict(), no_raw_observation_during_ack=True)
        finally:
            forbid_raw[0] = False
            writer.rollback()
            kernel._begin_budget_sample = begin

        with SQLiteKernel(kernel.db_path, now=lambda: wall[0]) as fresh:
            self.assertGreaterEqual(fresh.current_time(), retained.checkpoint.wall_at)
            with fresh._control_lock(.1):
                with self.assertRaisesRegex(StaleFenceError, "lease has expired") as renewal:
                    fresh.renew(lease)
            with fresh._control_lock(.1):
                with self.assertRaisesRegex(StaleFenceError, "lease has expired") as effect_claim:
                    fresh.claim_effect(lease, effect.effect_id)
            self.assertEqual(fresh.get(source_id).to_dict(), source_before)
            self.assertEqual(fresh.get_effect(effect.effect_id).to_dict(), effect.to_dict())
            self.assertEqual(fresh.effect_events(effect.effect_id), effect_events)
            self.assertIsNone(fresh.claim_and_start("fresh-sibling-owner", timeout_seconds=.1))
            self.assertEqual(fresh.get(sibling_id).to_dict(), sibling_before)
            self.assertEqual(fresh.get_run_control(run_id), control_before)
            source_after = fresh.get(source_id)
            self.assertEqual((source_after.attempt, source_after.fence), (lease.attempt, lease.fence))
            final = BudgetEnvelope.from_dict(fresh.get_execution_limits(source_id)["envelope"])
            self.assertEqual(final.constraints, original.constraints)
            self.assertEqual(final.started_at, original.started_at)
            self.evidence.update(renewal_error={"type": type(renewal.exception).__name__, "message": str(renewal.exception)},
                effect_authority_error={"type": type(effect_claim.exception).__name__, "message": str(effect_claim.exception)},
                fresh_source=source_after.to_dict(), fresh_sibling=fresh.get(sibling_id).to_dict(),
                final_control=fresh.get_run_control(run_id), unchanged_effect_before_reap=effect.to_dict(),
                sibling_not_claimed_after_original_deadline=True)


if __name__ == "__main__":
    unittest.main()
