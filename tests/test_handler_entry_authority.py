"""Durable first-entry authority, independent of handler or telemetry setup."""

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import (
    CASConflictError, ExecutionCommandV2, ExecutionError, ExecutionResultV2,
    RetryPolicy, SQLiteKernel, StaleFenceError,
)
from dispatcher_sdk.execution_kernel.budget import (
    BudgetClockUnknownError, BudgetEnvelope, ClockCheckpoint, DeadlineConstraint,
    sample_clock,
)
from dispatcher_sdk.execution_kernel.runtime import Runtime


class HandlerEntryAuthorityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "entry.sqlite3"
        self.wall, self.elapsed = 1000.0, 100.0
        self.addCleanup(patch.stopall)
        patch("dispatcher_sdk.execution_kernel.supervision.sample_clock",
              side_effect=lambda **kwargs: self.sample()).start()
        self.kernel = SQLiteKernel(self.path, now=lambda: self.wall)
        self.addCleanup(self.kernel.close)
        self.command = ExecutionCommandV2("entry", "entry", "fixture", "run", None,
            "fixture", 1, RetryPolicy(max_attempts=3, initial_backoff_seconds=0,
                max_backoff_seconds=0, retry_timeouts=True), 30, {})
        self.kernel.submit(self.command)
        self.lease = self.kernel.claim_and_start("worker")

    def sample(self):
        return ClockCheckpoint(self.wall, self.elapsed, "fixture-boot")

    def advance(self, seconds):
        self.wall += seconds
        self.elapsed += seconds

    def enter(self, envelope):
        return envelope.enter_handler(30, origin_id="execution:entry", sample=self.sample())

    def retry(self):
        snapshot = self.kernel.get("entry")
        result = ExecutionResultV2("failure-" + str(self.lease.attempt), "entry", "failed",
            self.lease.attempt, self.lease.fence, [], snapshot.started_at, self.wall,
            "run", None, None, ExecutionError("test_failure", "retry", True, {}))
        self.kernel.complete(self.lease, result)
        self.lease = self.kernel.claim_and_start("retry-worker")

    def inherit(self):
        envelope = BudgetEnvelope((DeadlineConstraint("parent", "parent", 1100, 10),), self.sample())
        with self.kernel._transaction() as (connection, _):
            connection.execute("INSERT INTO kernel_execution_limits(execution_id,envelope_json) VALUES(?,?)",
                               ("entry", json.dumps(envelope.to_dict())))
        return envelope

    def test_preparation_is_durable_and_does_not_spend_execution_timeout(self):
        prepared = self.kernel.prepare_execution_budget(self.lease)
        self.assertEqual(prepared.constraints, ())
        self.assertIsNone(prepared.started_at)
        limits = self.kernel.get_execution_limits("entry")
        self.assertEqual(limits["entry_state"], "pending")
        self.assertEqual((limits["entry_attempt"], limits["entry_fence"]),
                         (self.lease.attempt, self.lease.fence))
        self.advance(12)
        entered = self.enter(prepared)
        self.advance(8)  # ACK storage latency is charged, never renewed.
        confirmed = self.kernel.confirm_handler_entry(self.lease, entered)
        self.assertEqual(confirmed.started_at, 1012)
        self.assertEqual(confirmed.constraints[0].deadline_at, 1042)
        self.assertEqual(confirmed.view(sample=self.sample()).remaining_work_seconds, 22)
        self.assertEqual(self.kernel.get("entry").started_at, 1000)  # Public V2 meaning unchanged.

    def test_same_admission_and_duplicate_ack_are_idempotent(self):
        first = self.kernel.prepare_execution_budget(self.lease)
        self.advance(1)
        prepared = self.kernel.prepare_execution_budget(self.lease)
        self.assertEqual(first.constraints, prepared.constraints)
        entered = self.enter(prepared)
        confirmed = self.kernel.confirm_handler_entry(self.lease, entered)
        self.advance(4)
        replay = self.kernel.confirm_handler_entry(self.lease, entered)
        self.assertEqual(replay.constraints, confirmed.constraints)
        self.assertEqual(replay.started_at, confirmed.started_at)
        self.assertEqual(replay.view(sample=self.sample()).remaining_work_seconds, 26)

    def test_confirmed_retry_updates_actual_entry_but_keeps_original_cutoff(self):
        entered = self.enter(self.kernel.prepare_execution_budget(self.lease))
        self.kernel.confirm_handler_entry(self.lease, entered)
        self.advance(5)
        self.retry()
        prepared = self.kernel.prepare_execution_budget(self.lease)
        self.assertEqual(self.kernel.get_execution_limits("entry")["entry_state"], "confirmed")
        self.advance(2)
        retry = self.kernel.confirm_handler_entry(self.lease, self.enter(prepared))
        self.assertEqual(retry.started_at, 1007)
        self.assertEqual(retry.constraints[0].deadline_at, 1030)

    def test_confirmed_restart_spends_elapsed_time_despite_wall_rollback(self):
        entered = self.enter(self.kernel.prepare_execution_budget(self.lease))
        self.kernel.confirm_handler_entry(self.lease, entered)
        self.kernel.close()
        self.wall = 900
        self.elapsed += 20
        self.kernel = SQLiteKernel(self.path, now=lambda: self.wall)
        self.addCleanup(self.kernel.close)
        resumed = self.kernel.prepare_execution_budget(self.lease)
        self.assertEqual(resumed.constraints[0].deadline_at, 1030)
        self.assertEqual(resumed.view(sample=self.sample()).remaining_work_seconds, 10)

    def test_interrupted_first_admission_cannot_grant_a_retry_new_cutoff(self):
        self.kernel.prepare_execution_budget(self.lease)
        self.retry()
        for method in (self.kernel.prepare_execution_budget, self.kernel.admission_budget):
            with self.assertRaisesRegex(BudgetClockUnknownError, "entry_confirmation_pending"):
                method(self.lease)
        self.assertEqual(self.kernel.get_execution_limits("entry")["entry_attempt"], 1)

    def test_ack_without_admission_and_stale_fence_are_rejected(self):
        entered = self.enter(BudgetEnvelope((), self.sample()))
        with self.assertRaises(CASConflictError):
            self.kernel.confirm_handler_entry(self.lease, entered)
        self.kernel.prepare_execution_budget(self.lease)
        stale = replace(self.lease, fence=self.lease.fence + 1)
        with self.assertRaises(StaleFenceError):
            self.kernel.confirm_handler_entry(stale, entered)
        self.assertEqual(self.kernel.get_execution_limits("entry")["entry_state"], "pending")

    def test_first_ack_cannot_invent_a_later_cutoff(self):
        entered = self.enter(self.kernel.prepare_execution_budget(self.lease))
        forged = replace(entered, constraints=(replace(entered.constraints[0], deadline_at=1031),))
        with self.assertRaisesRegex(ValueError, "actual entry timeout"):
            self.kernel.confirm_handler_entry(self.lease, forged)
        self.assertEqual(self.kernel.get_execution_limits("entry")["entry_state"], "pending")

    def test_inherited_deadline_source_and_reserve_cannot_weaken(self):
        self.inherit()
        entered = self.enter(self.kernel.prepare_execution_budget(self.lease))
        parent, execution = entered.constraints
        variants = (
            (execution,), (replace(parent, deadline_at=1101), execution),
            (replace(parent, reserve_seconds=9), execution),
            (replace(parent, source="tool"), execution),
        )
        for constraints in variants:
            with self.subTest(constraints=constraints), self.assertRaisesRegex(ValueError, "weakens"):
                self.kernel.confirm_handler_entry(self.lease, replace(entered, constraints=constraints))
        self.kernel.confirm_handler_entry(self.lease, entered)

    def test_unknown_clock_ack_preserves_pending_original_constraints(self):
        self.inherit()
        prepared = self.kernel.prepare_execution_budget(self.lease)
        entered = self.enter(prepared)
        forged = replace(entered, checkpoint=replace(entered.checkpoint, domain_id="different-boot"))
        with self.assertRaises(BudgetClockUnknownError):
            self.kernel.confirm_handler_entry(self.lease, forged)
        limits = self.kernel.get_execution_limits("entry")
        self.assertEqual(limits["entry_state"], "pending")
        self.assertEqual(limits["envelope"]["constraints"], prepared.to_dict()["constraints"])

    def test_sqlite_contention_is_bounded_and_does_not_confirm_entry(self):
        entered = self.enter(self.kernel.prepare_execution_budget(self.lease))
        with sqlite3.connect(self.path) as other:
            other.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                self.kernel.confirm_handler_entry(self.lease, entered, timeout_seconds=.02)
            self.assertLess(time.monotonic() - started, .5)
        self.assertEqual(self.kernel.get_execution_limits("entry")["entry_state"], "pending")

    def test_compatibility_helper_keeps_captured_cutoff(self):
        entered = self.enter(BudgetEnvelope((), self.sample()))
        self.advance(5)
        recorded = self.kernel.record_execution_budget(self.lease, entered)
        self.assertEqual(recorded.started_at, 1000)
        self.assertEqual(recorded.constraints[0].deadline_at, 1030)
        self.assertEqual(self.kernel.get_execution_limits("entry")["entry_state"], "confirmed")

    def test_actual_host_exit_after_prepare_does_not_renew_on_reclaim(self):
        path = self.path.with_name("crashed-host.sqlite3")
        script = """
import os, sys
from dispatcher_sdk.execution_kernel import SQLiteKernel, ExecutionCommandV2, RetryPolicy
k = SQLiteKernel(sys.argv[1], now=lambda: 1000)
c = ExecutionCommandV2('crashed', 'crashed', 'fixture', 'run', None, 'fixture', 1,
    RetryPolicy(max_attempts=2, initial_backoff_seconds=0, max_backoff_seconds=0, retry_timeouts=True), 1, {})
k.submit(c)
lease = k.claim_and_start('host', lease_seconds=1, start_safety_seconds=0)
k.prepare_execution_budget(lease)
os._exit(0)
"""
        completed = subprocess.run([sys.executable, "-B", "-c", script, str(path)],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        # New host has no volatile ACK, even though SQLite committed admission.
        with SQLiteKernel(path, now=lambda: 1002) as reopened:
            pending = reopened.get_execution_limits("crashed")
            self.assertEqual(pending["entry_state"], "pending")
            self.assertEqual(pending["envelope"]["constraints"], [])
            reopened.reap()
            lease = reopened.claim_and_start("new-host", lease_seconds=1, start_safety_seconds=0)
            self.assertIsNotNone(lease)
            with self.assertRaisesRegex(BudgetClockUnknownError, "entry_confirmation_pending"):
                reopened.prepare_execution_budget(lease)


class ThreadHandlerEntryGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.called = threading.Event()
        self.confirming = threading.Event()
        self.release = threading.Event()
        self.worker_finished = threading.Event()
        self.results = []
        self.wall = None

        def handler(payload, context):
            self.called.set()
            self.remaining_at_invocation = context.budget.remaining_work_seconds
            return context._kernel.get_execution_limits(context.command.execution_id)["entry_state"]

        handler.__execution_kernel_revision__ = "thread-entry-gate-v1"
        self.runtime = Runtime(str(Path(temporary.name) / "thread-entry.sqlite3"),
                               {"handler": handler}, isolation_mode="thread", max_thread_workers=1,
                               now=lambda: time.time() if self.wall is None else self.wall)
        self.addCleanup(self.runtime.close)
        self.addCleanup(self.release.set)
        self.confirm = self.runtime.kernel._checkpoint_handler_entry
        finished = self.runtime._thread_finished

        def record_finished(*args):
            finished(*args)
            self.worker_finished.set()

        self.finish_patch = patch.object(self.runtime, "_thread_finished", side_effect=record_finished)
        self.finish_patch.start()
        self.addCleanup(self.finish_patch.stop)

    def start(self, *, timeout=2, fail=False):
        def held_confirmation(*args, **kwargs):
            self.confirming.set()
            if not self.release.wait(3):
                raise RuntimeError("test did not release confirmation")
            if fail:
                raise CASConflictError("injected entry acknowledgement failure")
            return self.confirm(*args, **kwargs)

        self.confirm_patch = patch.object(self.runtime.kernel, "_checkpoint_handler_entry",
                                           side_effect=held_confirmation)
        self.confirm_patch.start()
        self.addCleanup(self.confirm_patch.stop)
        self.runtime.submit(self.runtime.command("handler", execution_id="thread-entry",
            idempotency_key="thread-entry", correlation_id="thread-entry",
            timeout_seconds=timeout, payload={}))
        self.driver = threading.Thread(target=lambda: self.results.append(self.runtime.run_once()))
        self.driver.start()
        self.assertTrue(self.confirming.wait(2), "coordinator never received actual entry")

    def finish(self):
        self.release.set()
        self.driver.join(2)
        self.assertFalse(self.driver.is_alive(), "thread entry driver did not settle")
        return self.results[0]

    def test_user_code_waits_until_first_entry_ack_is_durable(self):
        self.start()
        self.assertEqual(self.runtime.kernel.get_execution_limits("thread-entry")["entry_state"], "pending")
        self.assertFalse(self.called.wait(.05))
        terminal = self.finish()
        self.assertEqual(terminal.state, "succeeded", terminal.result.error)
        self.assertEqual(terminal.result.value, "confirmed")

    def test_expired_admission_releases_slot_for_other_execution(self):
        for execution_id in ("expired", "healthy"):
            self.runtime.submit(self.runtime.command("handler", execution_id=execution_id,
                idempotency_key=execution_id, correlation_id=execution_id,
                timeout_seconds=2, payload={}))
        sample = sample_clock()
        envelope = BudgetEnvelope((DeadlineConstraint("parent", "parent", sample.wall_at - 1),), sample)
        with self.runtime.kernel._transaction() as (connection, _):
            connection.execute("INSERT INTO kernel_execution_limits(execution_id,envelope_json) VALUES(?,?)",
                               ("expired", json.dumps(envelope.to_dict())))
        expired = self.runtime.run_once()
        self.assertEqual(expired.state, "timed_out")
        self.assertFalse(self.called.is_set())
        healthy = self.runtime.run_once()
        self.assertIsNotNone(healthy, "expired admission leaked the only thread slot")
        self.assertEqual(healthy.state, "succeeded", healthy.result.error)

    def test_failed_entry_ack_never_invokes_user_code(self):
        self.start(fail=True)
        terminal = self.finish()
        self.assertEqual(terminal.state, "failed")
        self.assertEqual(terminal.result.error.code, "entry_confirmation_unknown")
        self.assertTrue(self.worker_finished.wait(.5))
        self.assertFalse(self.called.is_set())
        self.assertEqual(self.runtime.kernel.get_execution_limits("thread-entry")["entry_state"], "pending")

    def test_expiry_releases_worker_waiting_for_entry_ack(self):
        self.start(timeout=.15)
        cutoff = self.runtime._thread_contexts[("thread-entry", 1, 1)].budget_envelope.constraints
        self.assertTrue(self.worker_finished.wait(1), "entry wait ignored execution cutoff")
        self.assertFalse(self.called.is_set())
        terminal = self.finish()
        self.assertEqual(terminal.state, "timed_out", terminal.result.error)
        self.assertEqual(terminal.result.error.code, "handler_timeout")
        persisted = self.runtime.kernel.get_execution_limits("thread-entry")["envelope"]["constraints"]
        self.assertEqual(persisted, [item.to_dict() for item in cutoff])

    def test_forward_wall_jump_releases_entry_wait_without_waiting_old_timer(self):
        self.start()
        cutoff = self.runtime._thread_contexts[("thread-entry", 1, 1)].budget_envelope.constraints
        self.wall = cutoff[0].deadline_at + 1
        self.assertTrue(self.worker_finished.wait(.5), "entry wait ignored authoritative wall-clock cutoff")
        self.assertFalse(self.called.is_set())
        terminal = self.finish()
        self.assertEqual(terminal.state, "timed_out", terminal.result.error)
        self.assertEqual(terminal.result.error.code, "handler_timeout")
        persisted = self.runtime.kernel.get_execution_limits("thread-entry")["envelope"]["constraints"]
        self.assertEqual(persisted, [item.to_dict() for item in cutoff])

    def test_forward_jump_then_rollback_before_ack_keeps_observed_remaining_time(self):
        self.start(timeout=10)
        context = self.runtime._thread_contexts[("thread-entry", 1, 1)]
        self.wall = context.budget_envelope.started_at + 6
        remaining = context.budget.remaining_work_seconds
        self.assertLessEqual(remaining, 4)
        self.wall = None
        terminal = self.finish()
        self.assertEqual(terminal.state, "succeeded", terminal.result.error)
        self.assertLessEqual(self.remaining_at_invocation, remaining)
        persisted = BudgetEnvelope.from_dict(self.runtime.kernel.get_execution_limits("thread-entry")["envelope"])
        self.assertLessEqual(persisted.view().remaining_work_seconds, remaining)

    def test_cancellation_releases_worker_waiting_for_entry_ack(self):
        self.start()
        running = self.runtime.kernel.get("thread-entry")
        self.runtime.cancel("thread-entry", expected_revision=running.revision, reason="test cancellation")
        self.assertTrue(self.worker_finished.wait(.5), "revoked worker remained in entry wait")
        self.assertFalse(self.called.is_set())
        terminal = self.finish()
        self.assertEqual(terminal.state, "cancelled")


class AdmissionContentionTests(unittest.TestCase):
    """Real storage collisions must not strand a claimed public execution."""

    class SlowRestoreHandler:
        __execution_kernel_revision__ = "slow-entry-restore-v1"

        def __getstate__(self):
            return {}

        def __setstate__(self, state):
            time.sleep(.45)

        def __call__(self, payload, context):
            Path(payload["marker"]).write_text("entered")
            return {"entered": True}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def runtime(self, *, mode="thread", now=None, startup=.5, handler=None):
        marker = self.root / (mode + "-business")

        def echo(payload, context):
            marker.write_text("entered")
            return context.budget.to_dict()

        echo.__execution_kernel_revision__ = "admission-contention-echo-v1"
        runtime = Runtime(self.root / (mode + ".sqlite3"), {"handler": handler or echo},
                          isolation_mode=mode, max_thread_workers=1, now=now)
        self.addCleanup(runtime.close)
        runtime._handler_start_timeout = lambda: startup
        return runtime, marker

    def submit(self, runtime, identifier, *, managed=False):
        execution_id = ("sdk-managed:" if managed else "") + identifier
        command = runtime.command("handler", execution_id=execution_id,
            idempotency_key=execution_id, correlation_id=identifier, timeout_seconds=5,
            payload={"marker": str(self.root / "process-business")})
        if managed:
            runtime.submit_managed(command, run_id=identifier, generation=1)
        else:
            runtime.submit(command)
        return execution_id

    def drive(self, runtime, execution_id):
        results, errors = [], []

        def run():
            try:
                results.append(runtime.run_once(execution_id=execution_id))
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=run)
        driver.start()
        self.addCleanup(lambda: driver.join(2))
        return driver, results, errors

    def contend(self, runtime):
        ready, held, busy = threading.Event(), threading.Event(), threading.Event()
        original = runtime.kernel._prepare_handler_entry
        failures = []

        def prepare(lease, **kwargs):
            ready.set()
            if not held.wait(2):
                raise AssertionError("test writer was not acquired")
            try:
                return original(lease, **kwargs)
            except sqlite3.OperationalError as error:
                failures.append(error)
                busy.set()
                raise

        runtime.kernel._prepare_handler_entry = prepare
        self.addCleanup(held.set)
        return ready, held, busy, failures

    def writer(self, path):
        connection = sqlite3.connect(path, timeout=1)
        self.addCleanup(connection.close)
        connection.execute("BEGIN IMMEDIATE")
        self.addCleanup(connection.rollback)
        return connection

    def test_public_dispatcher_retries_real_writer_and_delivers_once(self):
        from dispatcher_sdk import Dispatcher
        received = []
        call_log = self.root / "business-calls.txt"
        delivered = threading.Event()

        def echo(payload, context):
            with Path(payload["call_log"]).open("a") as stream:
                stream.write(context.command.execution_id + "\n")
            return payload["value"] * 2

        echo.__execution_kernel_revision__ = "public-admission-contention-v1"

        def callback(notification):
            received.append(notification)
            delivered.set()

        app = Dispatcher(self.root / "app.sqlite3", {"echo": echo}, isolation_mode="thread",
                         on_result=callback, callback_retry_delay=.01)
        self.addCleanup(app.close)
        ready, held, busy, failures = self.contend(app.runtime)
        task = app.submit("echo", {"value": 8, "call_log": str(call_log)}, request_id="retry-admission")
        app.start()
        self.assertTrue(ready.wait(2), (app.health(), task.snapshot))
        writer = self.writer(app.path)
        held.set()
        self.assertTrue(busy.wait(1), "a real SQLite BUSY collision is required")
        writer.rollback()
        result = task.wait(timeout=3)
        self.assertEqual((result["status"], result["value"], result["attempt"]),
                         ("succeeded", 16, 1))
        self.assertTrue(delivered.wait(2))
        self.assertEqual(len(call_log.read_text().splitlines()), 1)
        self.assertEqual(len(received), 1)
        self.assertGreaterEqual(len(failures), 1)
        worker_errors = [item for item in app.health()["host"]["recent_errors"]
                         if item["source"] == "worker"]
        self.assertEqual(worker_errors, [])

    def test_startup_expiry_classifies_without_business_and_releases_capacity(self):
        runtime, marker = self.runtime(startup=.25)
        ready, held, busy, failures = self.contend(runtime)
        classified = threading.Event()
        original = runtime._outcome_result

        def outcome(*args):
            value = original(*args)
            classified.set()
            return value

        runtime._outcome_result = outcome
        identifier = self.submit(runtime, "expired-admission")
        driver, results, errors = self.drive(runtime, identifier)
        self.assertTrue(ready.wait(2))
        writer = self.writer(runtime.kernel.db_path)
        held.set()
        self.assertTrue(busy.wait(1))
        self.assertTrue(classified.wait(1), "admission retried beyond its original startup window")
        self.assertFalse(marker.exists())
        # Durable terminal publication needs the writer; releasing it must
        # publish the already classified failure, without another admission.
        writer.rollback()
        driver.join(2)
        self.assertFalse(driver.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0].state, "failed")
        self.assertEqual(results[0].result.error.code, "entry_admission_timeout")
        healthy = self.submit(runtime, "healthy")
        self.assertEqual(runtime.run_once(execution_id=healthy).state, "succeeded")
        self.assertGreaterEqual(len(failures), 1)

    def test_forward_jump_then_rollback_preserves_inherited_run_time(self):
        base = time.time()
        wall = [base]
        runtime, _ = self.runtime(now=lambda: wall[0], startup=2)
        control = runtime.kernel.register_run_control("clock", max_claims=1, deadline_at=base + 10)
        runtime.kernel.set_run_control("clock", expected_epoch=control["control_epoch"],
                                       state="active", generation=1)
        identifier = self.submit(runtime, "clock", managed=True)
        ready, held, busy, _ = self.contend(runtime)
        jumped = threading.Event()
        original_prepare = runtime.kernel._prepare_handler_entry

        def after_helper_checkpoint(lease, **kwargs):
            # This call follows the helper's resample/recheckpoint, so the
            # barrier proves the forward jump was incorporated before rollback.
            if wall[0] == base + 6:
                jumped.set()
            return original_prepare(lease, **kwargs)

        runtime.kernel._prepare_handler_entry = after_helper_checkpoint
        driver, results, errors = self.drive(runtime, identifier)
        self.assertTrue(ready.wait(2))
        writer = self.writer(runtime.kernel.db_path)
        held.set()
        self.assertTrue(busy.wait(1))
        wall[0] = base + 6
        self.assertTrue(jumped.wait(1))
        wall[0] = base
        writer.rollback()
        driver.join(2)
        self.assertFalse(driver.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0].state, "succeeded")
        view = results[0].result.value
        self.assertLessEqual(view["remaining_work_seconds"], 4)
        self.assertEqual(view["limiting_source"], "run")

    def test_expired_run_during_writer_contention_never_invokes_business(self):
        base = time.time()
        wall = [base]
        runtime, marker = self.runtime(now=lambda: wall[0], startup=2)
        control = runtime.kernel.register_run_control("deadline", max_claims=1, deadline_at=base + 10)
        runtime.kernel.set_run_control("deadline", expected_epoch=control["control_epoch"],
                                       state="active", generation=1)
        identifier = self.submit(runtime, "deadline", managed=True)
        ready, held, busy, _ = self.contend(runtime)
        driver, results, errors = self.drive(runtime, identifier)
        self.assertTrue(ready.wait(2))
        writer = self.writer(runtime.kernel.db_path)
        held.set()
        self.assertTrue(busy.wait(1))
        wall[0] = base + 11
        writer.rollback()
        driver.join(2)
        self.assertFalse(driver.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0].state, "timed_out")
        self.assertFalse(marker.exists())

    @unittest.skipUnless(sys.platform == "linux", "requires POSIX process containment")
    def test_process_restore_uses_remaining_original_startup_window(self):
        runtime, marker = self.runtime(mode="process", startup=.7,
                                       handler=self.SlowRestoreHandler())
        ready, held, busy, failures = self.contend(runtime)
        identifier = self.submit(runtime, "slow-restore")
        driver, results, errors = self.drive(runtime, identifier)
        self.assertTrue(ready.wait(2))
        writer = self.writer(runtime.kernel.db_path)
        held.set()
        self.assertTrue(busy.wait(1))
        wait_end = time.monotonic() + 1
        while len(failures) < 3 and time.monotonic() < wait_end:
            time.sleep(.01)
        self.assertGreaterEqual(len(failures), 3)
        writer.rollback()
        driver.join(2)
        self.assertFalse(driver.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0].state, "failed")
        self.assertEqual(results[0].result.error.code, "handler_process_start_failure")
        self.assertFalse(marker.exists())

    def test_stop_interrupts_pending_admission_without_business(self):
        runtime, marker = self.runtime(startup=2)
        ready, held, busy, _ = self.contend(runtime)
        identifier = self.submit(runtime, "stopped")
        driver, results, errors = self.drive(runtime, identifier)
        self.assertTrue(ready.wait(2))
        writer = self.writer(runtime.kernel.db_path)
        held.set()
        self.assertTrue(busy.wait(1))
        runtime.request_stop()
        writer.rollback()
        driver.join(2)
        self.assertFalse(driver.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0].state, "running")
        self.assertFalse(marker.exists())
        self.assertTrue(runtime._thread_slots.acquire(blocking=False))
        runtime._thread_slots.release()

    def test_cancellation_before_admission_ack_never_invokes_business(self):
        runtime, marker = self.runtime(startup=2)
        ready, held, _, _ = self.contend(runtime)
        identifier = self.submit(runtime, "cancelled-admission")
        driver, results, errors = self.drive(runtime, identifier)
        self.assertTrue(ready.wait(2))
        running = runtime.kernel.get(identifier)
        runtime.cancel(identifier, expected_revision=running.revision)
        held.set()
        driver.join(2)
        self.assertFalse(driver.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results[0].state, "cancelled")
        self.assertFalse(marker.exists())
        healthy = self.submit(runtime, "after-cancel")
        self.assertEqual(runtime.run_once(execution_id=healthy).state, "succeeded")


if __name__ == "__main__":
    unittest.main()
