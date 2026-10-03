"""Original real handler outcomes survive bounded Kernel write contention."""
from pathlib import Path
from dataclasses import replace
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import HandlerExecutionError, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import runtime as runtime_module


def settlement_success(payload, context):
    with Path(payload["call_log"]).open("a") as stream:
        stream.write(context.command.execution_id + "\n")
    return {"message": "original real success", "payload": payload["value"]}


def settlement_failure(payload, context):
    with Path(payload["call_log"]).open("a") as stream:
        stream.write(context.command.execution_id + "\n")
    raise HandlerExecutionError("original_real_failure", "original handler error",
                                details={"value": payload["value"]})


def settlement_gated_success(payload, context):
    with Path(payload["call_log"]).open("a") as stream:
        stream.write(context.command.execution_id + "\n")
    Path(payload["ready"]).write_text("actual handler entered")
    while not Path(payload["release"]).exists():
        time.sleep(.005)
    return {"message": "actual handler returned while lifecycle was held"}


settlement_success.__execution_kernel_revision__ = "settlement-success-v1"
settlement_failure.__execution_kernel_revision__ = "settlement-failure-v1"
settlement_gated_success.__execution_kernel_revision__ = "settlement-gated-success-v1"


class Clock:
    def __init__(self):
        self.value = time.time()

    def __call__(self):
        return self.value


class RuntimeSettlementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def open(self, name, *, mode="thread", failure=False, clock=None):
        runtime = Kernel.open_sqlite(self.root / (name + ".sqlite3"),
            {"work": settlement_failure if failure else settlement_success},
            isolation_mode=mode, now=clock, max_thread_workers=1)
        self.addCleanup(runtime.close)
        return runtime

    def run_with_result_writer_locked(self, name, *, mode="thread", failure=False, clock=None,
                                      retry_policy=None):
        """Hold the writer after a real outcome, never replace that outcome."""
        runtime = self.open(name, mode=mode, failure=failure, clock=clock)
        call_log = self.root / (name + "-calls.txt")
        command = runtime.command("work", execution_id=name, idempotency_key=name,
            correlation_id=name, timeout_seconds=5,
            payload={"call_log": str(call_log), "value": 17}, retry_policy=retry_policy)
        runtime.submit(command)
        outcome_ready, writer_held = threading.Event(), threading.Event()
        retained = []
        original = runtime._outcome_result

        def outcome(*args):
            result = original(*args)
            retained.append(result.to_dict())
            outcome_ready.set()
            if not writer_held.wait(3):
                raise AssertionError("test writer was not acquired after real outcome")
            return result

        runtime._outcome_result = outcome
        results, errors = [], []

        def drive():
            try:
                results.append(runtime.run_once(execution_id=name))
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=drive)
        driver.start()
        self.addCleanup(lambda: driver.join(3))
        self.addCleanup(writer_held.set)
        self.assertTrue(outcome_ready.wait(3), "real handler did not produce an outcome")
        self.assertEqual(len(call_log.read_text().splitlines()), 1)
        writer = sqlite3.connect(runtime.kernel.db_path, timeout=1)
        self.addCleanup(writer.close)
        writer.execute("BEGIN IMMEDIATE")
        self.addCleanup(writer.rollback)
        writer_held.set()
        driver.join(2)
        self.assertFalse(driver.is_alive(), "result publication waited on the default 30-second writer timeout")
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].state, "running")
        self.assertIsNone(results[0].result)
        obligations = runtime._settlement_journal.inspect(name, timeout_seconds=.5)
        self.assertEqual(len(obligations), 1)
        self.assertEqual(obligations[0]["result"], retained[0])
        self.assertIn(obligations[0]["state"], {"pending", "error"})
        self.assertEqual(obligations[0]["identity"], {
            "execution_id": name, "attempt": results[0].attempt, "fence": results[0].fence})
        observed = runtime.observe(name, timeout=1)
        self.assertIn("settlement_obligations", observed)
        self.assertIn(retained[0]["result_id"], json.dumps(observed["settlement_obligations"]))
        return runtime, writer, call_log, retained[0], obligations[0]

    def recover(self, runtime, name):
        end = time.monotonic() + 3
        reports = []
        while time.monotonic() < end:
            reports.extend(runtime.recover_completions(timeout_seconds=.5))
            current = runtime.kernel.get(name)
            receipt = runtime._settlement_journal.inspect(name, timeout_seconds=.5)
            if current.result is not None and receipt and receipt[0]["state"] == "recorded":
                return current, reports
            time.sleep(.01)
        self.fail((runtime.observe(name), reports))

    def assert_retained(self, runtime, name, original, state):
        records = runtime._settlement_journal.inspect(name, timeout_seconds=.5)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["result"], original)
        self.assertEqual(records[0]["state"], state)

    def stop_maintenance(self, runtime):
        runtime.request_stop()
        if runtime._settlement_thread is not None:
            runtime._settlement_thread.join(1)
            self.assertFalse(runtime._settlement_thread.is_alive())

    def test_real_thread_success_and_error_recover_original_results(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                name = "thread-error" if failure else "thread-success"
                runtime, writer, calls, original, _ = self.run_with_result_writer_locked(
                    name, failure=failure)
                writer.rollback()
                current, _ = self.recover(runtime, name)
                self.assertEqual(current.result.to_dict(), original)
                self.assertEqual(current.state, "failed" if failure else "succeeded")
                if failure:
                    self.assertEqual(current.result.error.code, "original_real_failure")
                self.assertEqual(len(calls.read_text().splitlines()), 1)
                self.assert_retained(runtime, name, original, "recorded")

    def test_oversized_retained_diagnostics_make_public_reads_incomplete(self):
        from dispatcher_sdk.observability import inspect_execution
        runtime, writer, calls, original, obligation = self.run_with_result_writer_locked("oversized-diagnostic")
        self.stop_maintenance(runtime)
        runtime._settlement_journal.settle(obligation, "error", {
            **obligation["evidence"], "raw_control_error": "x" * 300_000}, timeout_seconds=.5)
        before = runtime._settlement_journal.pending(timeout_seconds=.5)[0]
        observed = runtime.observe("oversized-diagnostic", timeout=1)
        storage = runtime.observation_storage
        independent = inspect_execution(storage["path"], "oversized-diagnostic",
            kernel_path=storage["kernel_path"], source_id=storage["source_id"], timeout=1)
        for report in (observed, independent):
            self.assertFalse(report["complete"], report)
            self.assertTrue(report["settlement_obligations"][0]["truncated"])
        self.assertEqual(before, runtime._settlement_journal.pending(timeout_seconds=.5)[0])
        writer.rollback()
        recovered, _ = self.recover(runtime, "oversized-diagnostic")
        self.assertEqual(recovered.result.to_dict(), original)
        self.assertEqual(len(calls.read_text().splitlines()), 1)

    def test_large_query_option_keeps_public_diagnostic_reads_available(self):
        from dispatcher_sdk import ObservationOptions
        from dispatcher_sdk.observability import inspect_execution
        runtime = Kernel.open_sqlite(self.root / "large-query.sqlite3", {"work": settlement_success},
            isolation_mode="thread", observation_options=ObservationOptions(query_bytes=1024 * 1024))
        with runtime:
            command = runtime.command("work", execution_id="large-query", idempotency_key="large-query",
                correlation_id="large-query", timeout_seconds=5,
                payload={"call_log": str(self.root / "large-query-calls"), "value": 17})
            runtime.submit(command)
            self.assertEqual(runtime.run_once().state, "succeeded")
            storage = runtime.observation_storage
            reports = (runtime.observe("large-query"), inspect_execution(storage["path"], "large-query",
                kernel_path=storage["kernel_path"], source_id=storage["source_id"],
                options=runtime.observation_options))
            for report in reports:
                self.assertNotIn("settlement_obligations_error", report)
                self.assertIn("diagnostics", report)
                self.assertIn("settlement_obligations", report)

    @unittest.skipUnless(sys.platform == "linux", "requires real POSIX process containment")
    def test_real_process_success_and_error_recover_original_results(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                name = "process-error" if failure else "process-success"
                runtime, writer, calls, original, _ = self.run_with_result_writer_locked(
                    name, mode="process", failure=failure)
                writer.rollback()
                current, _ = self.recover(runtime, name)
                self.assertEqual(current.result.to_dict(), original)
                self.assertEqual(current.state, "failed" if failure else "succeeded")
                self.assertEqual(len(calls.read_text().splitlines()), 1)
                self.assert_retained(runtime, name, original, "recorded")

    def test_restart_records_original_outcome_without_reinvoking_handler(self):
        runtime, writer, calls, original, _ = self.run_with_result_writer_locked("restart")
        runtime.close()
        writer.rollback()
        reopened = self.open("restart")
        current, _ = self.recover(reopened, "restart")
        self.assertEqual(current.result.to_dict(), original)
        self.assertIsNone(reopened.run_once())
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(reopened, "restart", original, "recorded")

    def test_lifecycle_contention_preserves_actual_return_before_admission(self):
        runtime = Kernel.open_sqlite(self.root / "lifecycle.sqlite3",
            {"work": settlement_gated_success}, isolation_mode="thread")
        self.addCleanup(runtime.close)
        ready, release, calls = (self.root / name for name in ("ready", "release", "calls"))
        command = runtime.command("work", execution_id="lifecycle", idempotency_key="lifecycle",
            correlation_id="lifecycle", timeout_seconds=5,
            payload={"ready": str(ready), "release": str(release), "call_log": str(calls)})
        runtime.submit(command)
        results, errors = [], []

        def drive():
            try:
                results.append(runtime.run_once())
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=drive)
        driver.start()
        self.addCleanup(lambda: driver.join(3))
        self.addCleanup(lambda: release.touch())
        wait_end = time.monotonic() + 3
        while not ready.exists() and not errors and time.monotonic() < wait_end:
            time.sleep(.005)
        self.assertTrue(ready.exists(), errors)
        self.assertTrue(runtime._lifecycle_lock.acquire(timeout=1))
        try:
            release.touch()
            wait_end = time.monotonic() + 2
            receipts = []
            while not receipts and time.monotonic() < wait_end:
                receipts = runtime._settlement_journal.inspect("lifecycle", timeout_seconds=.5)
                if not receipts:
                    time.sleep(.005)
            self.assertEqual(len(receipts), 1, "lifecycle admission lost the original real outcome")
            self.assertEqual(receipts[0]["result"]["value"], {
                "message": "actual handler returned while lifecycle was held"})
            driver.join(1)
            self.assertFalse(driver.is_alive(), "lifecycle contention still blocked the public caller")
            self.assertEqual(errors, [])
            self.assertEqual(results[0].state, "running")
        finally:
            runtime._lifecycle_lock.release()
        current, _ = self.recover(runtime, "lifecycle")
        self.assertEqual(current.result.to_dict(), receipts[0]["result"])
        self.assertEqual(len(calls.read_text().splitlines()), 1)

    def test_expired_exact_lease_restores_completed_before_expiry(self):
        clock = Clock()
        runtime, writer, calls, original, receipt = self.run_with_result_writer_locked(
            "expired-lease", clock=clock)
        self.assertLessEqual(original["completed_at"], receipt["lease"]["expires_at"])
        clock.value = receipt["lease"]["expires_at"] + 1
        writer.rollback()
        current, _ = self.recover(runtime, "expired-lease")
        self.assertEqual(current.result.to_dict(), original)
        self.assertEqual(current.state, "succeeded")
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(runtime, "expired-lease", original, "recorded")

    def start_gated_completion(self, name, clock):
        runtime = Kernel.open_sqlite(self.root / (name + ".sqlite3"),
            {"work": settlement_gated_success}, isolation_mode="thread", now=clock)
        self.addCleanup(runtime.close)
        ready, release, calls = (self.root / (name + suffix) for suffix in ("-ready", "-release", "-calls"))
        command = runtime.command("work", execution_id=name, idempotency_key=name,
            correlation_id=name, timeout_seconds=5,
            payload={"ready": str(ready), "release": str(release), "call_log": str(calls)})
        runtime.submit(command)
        results, errors = [], []

        def drive():
            try:
                results.append(runtime.run_once(execution_id=name))
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=drive)
        self.addCleanup(lambda: driver.join(3))
        self.addCleanup(release.touch)
        driver.start()
        end = time.monotonic() + 3
        while not ready.exists() and not errors and time.monotonic() < end:
            time.sleep(.005)
        self.assertTrue(ready.exists(), errors)
        return runtime, command, release, calls, driver, results, errors

    def test_logical_watermark_rollback_cannot_restore_postexpiry_success(self):
        clock = Clock()
        runtime, command, release, calls, driver, results, errors = self.start_gated_completion("logical-rollback", clock)
        lease = runtime.kernel.get(command.execution_id).lease
        old_wall = clock.value
        context = next(iter(runtime._thread_contexts.values()))
        # Isolate logical-clock continuity from budget polling: neither the
        # handler nor its deadline loop observes this short wall excursion.
        with context._budget_lock:
            clock.value = lease.expires_at + 1
            runtime.kernel.submit(replace(command, execution_id="logical-clock-witness",
                idempotency_key="logical-clock-witness", correlation_id="logical-clock-witness"))
            clock.value = old_wall
        self.assertGreater(runtime.kernel.current_time(), lease.expires_at)
        release.touch()
        driver.join(3)
        self.assertFalse(driver.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(1, len(results))
        runtime.recover_completions(timeout_seconds=.5)
        current = runtime.kernel.get(command.execution_id)
        self.assertNotEqual("succeeded", current.state)
        self.assertIsNone(current.result)
        receipts = runtime._settlement_journal.inspect(command.execution_id, timeout_seconds=.5)
        self.assertEqual(1, len(receipts))
        original = receipts[0]["result"]
        self.assertEqual("succeeded", original["status"])
        self.assertEqual({"message": "actual handler returned while lifecycle was held"}, original["value"])
        self.assertGreater(original["completed_at"], lease.expires_at)
        self.assertEqual("superseded", receipts[0]["state"])
        self.assertEqual(1, len(calls.read_text().splitlines()))

    def test_completion_clock_control_lock_timeout_retains_unknown_original_outcome(self):
        clock = Clock()
        captured, capture_done = [], threading.Event()
        original_capture = runtime_module._capture_completion_time

        def capture(outcome, context):
            began = time.monotonic()
            original_capture(outcome, context)
            captured.append((dict(outcome), time.monotonic() - began))
            capture_done.set()

        with patch.object(runtime_module, "_capture_completion_time", side_effect=capture):
            runtime, command, release, calls, driver, results, errors = self.start_gated_completion("unknown-return-clock", clock)
            lease = runtime.kernel.get(command.execution_id).lease
            context = next(iter(runtime._thread_contexts.values()))
            with runtime.kernel._lock:
                began = time.monotonic()
                release.touch()
                self.assertTrue(capture_done.wait(.25), "return-time capture waited on unbounded Kernel admission")
                self.assertFalse(captured[0][0]["completion_time_known"])
                self.assertLess(captured[0][1], .25)
                # Establish expired logical authority while the worker cannot
                # read this connection, then roll wall time back before retry.
                with context._budget_lock:
                    old_wall = clock.value
                    clock.value = lease.expires_at + 1
                    runtime.kernel.submit(replace(command, execution_id="unknown-clock-witness",
                        idempotency_key="unknown-clock-witness", correlation_id="unknown-clock-witness"))
                    clock.value = old_wall
                time.sleep(max(0, .3 - (time.monotonic() - began)))
            driver.join(3)
        self.assertFalse(driver.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(1, len(results))
        runtime.recover_completions(timeout_seconds=.5)
        current = runtime.kernel.get(command.execution_id)
        self.assertIsNone(current.result)
        self.assertNotEqual("succeeded", current.state)
        receipts = runtime._settlement_journal.inspect(command.execution_id, timeout_seconds=.5)
        self.assertEqual(1, len(receipts))
        self.assertIsNone(receipts[0]["result"])
        self.assertIn(receipts[0]["state"], {"pending", "error"})
        raw = receipts[0]["deferred"]["outcome"]
        self.assertEqual("ok", raw["kind"])
        self.assertFalse(raw["completion_time_known"])
        self.assertNotIn("completed_at", raw)
        self.assertEqual({"message": "actual handler returned while lifecycle was held"}, raw["value"])
        self.assertIn("TimeoutError", raw["completion_time_error"])
        self.assertEqual(1, len(calls.read_text().splitlines()))

    def test_cancel_wins_and_archives_original_outcome(self):
        runtime, writer, calls, original, _ = self.run_with_result_writer_locked("cancel-wins")
        self.stop_maintenance(runtime)
        writer.rollback()
        current = runtime.kernel.get("cancel-wins")
        cancelled = runtime.cancel("cancel-wins", expected_revision=current.revision)
        runtime.recover_completions(timeout_seconds=.5)
        after = runtime.kernel.get("cancel-wins")
        self.assertEqual(after.to_dict(), cancelled.to_dict())
        self.assertEqual(after.state, "cancelled")
        self.assertNotEqual(after.result.result_id, original["result_id"])
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(runtime, "cancel-wins", original, "superseded")

    def test_reap_wins_and_archives_original_outcome(self):
        clock = Clock()
        runtime, writer, calls, original, receipt = self.run_with_result_writer_locked(
            "reap-wins", clock=clock)
        self.stop_maintenance(runtime)
        clock.value = receipt["lease"]["expires_at"] + 1
        writer.rollback()
        # An independent Kernel controller can win before Runtime's recovery.
        # Runtime.reap deliberately tries completion recovery first.
        runtime.kernel.reap()
        reaped = runtime.kernel.get("reap-wins")
        self.assertIn(reaped.state, {"timed_out", "dead", "failed"})
        self.assertIsNotNone(reaped.result)
        runtime.recover_completions(timeout_seconds=.5)
        after = runtime.kernel.get("reap-wins")
        self.assertEqual(after.to_dict(), reaped.to_dict())
        self.assertNotEqual(after.result.result_id, original["result_id"])
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(runtime, "reap-wins", original, "superseded")

    def test_new_attempt_wins_without_accepting_previous_success(self):
        clock = Clock()
        runtime, writer, calls, original, receipt = self.run_with_result_writer_locked(
            "new-attempt", clock=clock,
            retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     max_backoff_seconds=0, retry_timeouts=True))
        self.stop_maintenance(runtime)
        clock.value = receipt["lease"]["expires_at"] + 1
        writer.rollback()
        runtime.kernel.reap()
        lease = runtime.kernel.claim_and_start("independent-worker", execution_id="new-attempt")
        self.assertIsNotNone(lease)
        winner = runtime.kernel.get("new-attempt")
        self.assertEqual(winner.attempt, 2)
        self.assertGreater(winner.fence, receipt["identity"]["fence"])
        runtime.recover_completions(timeout_seconds=.5)
        after = runtime.kernel.get("new-attempt")
        self.assertEqual(after.to_dict(), winner.to_dict())
        self.assertIsNone(after.result)
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(runtime, "new-attempt", original, "superseded")


if __name__ == "__main__":
    unittest.main()
