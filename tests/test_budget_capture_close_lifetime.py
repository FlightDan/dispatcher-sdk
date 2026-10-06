"""A stopped live Context retains storage until its exact clock fact commits."""

import json
import sqlite3
import threading
import time
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.runtime import Runtime, _ObservationCleanupPendingError
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ObservationOptions
from tests._acceptance_evidence import retained_directory


class BudgetCaptureCloseLifetimeTests(unittest.TestCase):
    def test_repeated_close_finishes_same_real_context_token_without_replaying_business(self):
        root = retained_directory("sdk-budget-capture-close-lifetime-")
        wall = [time.time()]
        phase = ["business"]
        trace, calls, contexts, capture_errors, writers = [], [], [], [], []
        outcomes, driver_errors = [], []
        capturing = threading.local()
        failed_capture = threading.Event()
        evidence = {"original_windows": {"handler_work": 4, "capture_admission": .05,
            "driver_join": 2, "future_finish": 2}, "trace": trace}

        def handler(payload, context):
            calls.append(context.command.execution_id)
            contexts.append(context)
            evidence["entered"] = context.budget_envelope.to_dict()
            evidence["entered_native_deadline"] = context.budget_envelope.deadline_monotonic(
                sample=sample_clock(wall_time=context.budget_envelope.checkpoint.wall_at))
            capturing.active = True
            try:
                # One bounded normal-code capture on the actual live Context.
                # Its production sampler and SQLite acknowledgement are intact.
                with context._budget_lock:
                    context._capture_budget(timeout_seconds=.05)
            except sqlite3.OperationalError as error:
                capture_errors.append(error)
                evidence["capture_error"] = {"type": type(error).__name__, "message": str(error),
                    "token": getattr(error, "budget_sample_token", None),
                    "captured": error.budget_sample_envelope.to_dict()}
            finally:
                capturing.active = False
                failed_capture.set()
            return {"original_business": 42}

        handler.__execution_kernel_revision__ = "budget-capture-close-lifetime-v1"
        runtime = Runtime(root / "kernel.sqlite3", {"handler": handler}, now=lambda: wall[0],
            isolation_mode="thread", max_thread_workers=1, allow_children=False,
            observation_options=ObservationOptions(write_timeout=.05, flush_interval=.1))
        kernel = runtime.kernel
        begin, sample, finish, close = (kernel._begin_budget_sample, kernel._sample_budget,
            kernel._finish_budget_sample, kernel.close)

        def begin_and_hold(execution_id, **options):
            token = begin(execution_id, **options)
            trace.append({"operation": "armed", "phase": phase[0], "token": token})
            if getattr(capturing, "active", False) and not writers:
                writer = sqlite3.connect(kernel.db_path, timeout=.1, check_same_thread=False)
                writer.execute("BEGIN IMMEDIATE")
                writers.append(writer)
                wall[0] += 1
                evidence["blocked_token"] = token
                evidence["forward_wall"] = wall[0]
            return token

        def observed_sample(execution_id, envelope, **options):
            trace.append({"operation": "sample", "phase": phase[0]})
            return sample(execution_id, envelope, **options)

        def observed_finish(token, execution_id, envelope, **options):
            item = {"operation": "ack", "phase": phase[0], "token": token,
                "captured_wall": envelope.checkpoint.wall_at}
            trace.append(item)
            try:
                result = finish(token, execution_id, envelope, **options)
                item["committed"] = True
                return result
            except BaseException as error:
                item.update(committed=False, error_type=type(error).__name__, error=str(error))
                raise

        def observed_close():
            trace.append({"operation": "kernel_close", "phase": phase[0]})
            return close()

        kernel._begin_budget_sample = begin_and_hold
        kernel._sample_budget = observed_sample
        kernel._finish_budget_sample = observed_finish
        kernel.close = observed_close
        runtime.submit(runtime.command("handler", execution_id="original", idempotency_key="original",
            correlation_id="capture-close", timeout_seconds=4, payload={}))

        def drive():
            try:
                outcomes.append(runtime.run_once(execution_id="original"))
            except BaseException as error:
                driver_errors.append(error)

        driver = threading.Thread(target=drive, name="budget-capture-close-driver")
        driver.start()
        try:
            self.assertTrue(failed_capture.wait(2), "actual handler did not finish its original capture admission")
            driver.join(2)
            self.assertFalse(driver.is_alive(), "original business result did not return within its fixture window")
            self.assertEqual(driver_errors, [])
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(len(capture_errors), 1)
            self.assertEqual(calls, ["original"])
            context = contexts[0]
            error = capture_errors[0]
            token, retained = context._budget_capture._pending
            self.assertEqual(token, evidence["blocked_token"])
            self.assertEqual(token, error.budget_sample_token)
            self.assertGreaterEqual(retained.checkpoint.wall_at, evidence["forward_wall"])
            self.assertEqual(retained.constraints, context.budget_envelope.constraints)

            cutoff = time.monotonic() + 2
            receipts_before = []
            publication = []
            evidence["completion_publication"] = publication
            evidence["future_finish_deadline"] = cutoff
            while time.monotonic() < cutoff:
                remaining = cutoff - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    receipts_before = runtime._settlement_journal.inspect("original",
                        timeout_seconds=min(.1, remaining))
                    if runtime._thread_done and receipts_before:
                        break
                    remaining = cutoff - time.monotonic()
                    if remaining > 0:
                        publication.append({"reports": runtime.recover_completions(
                            timeout_seconds=min(.1, remaining))})
                except (sqlite3.OperationalError, TimeoutError) as error:
                    publication.append({"error_type": type(error).__name__, "error": str(error)})
                time.sleep(min(.01, max(0., cutoff - time.monotonic())))
            evidence["settlement_error_before_close"] = runtime._settlement_error
            evidence["receipts_before_close"] = receipts_before
            self.assertTrue(runtime._thread_done, "actual Context cleanup Future did not finish")
            self.assertTrue(context._observation_closed)
            self.assertTrue(runtime._context_observation_pending(context))
            self.assertFalse(runtime._thread_slots.acquire(blocking=False), "owned clock fact released capacity early")
            self.assertEqual(len(receipts_before), 1)
            self.assertEqual(receipts_before[0]["result"]["value"], {"original_business": 42})
            evidence["original_receipt"] = receipts_before[0]

            phase[0] = "first_close"
            with self.assertRaises(_ObservationCleanupPendingError) as first:
                runtime.close()
            evidence["first_close_error"] = {"type": type(first.exception).__name__, "message": str(first.exception)}
            self.assertEqual(kernel._connection.execute("SELECT 1").fetchone()[0], 1)
            self.assertEqual(context._budget_capture._pending[0], token)
            self.assertIn(context, runtime._retired_observation_contexts)
            self.assertFalse(runtime._thread_slots.acquire(blocking=False))
            self.assertFalse(any(item["operation"] == "kernel_close" for item in trace))
            self.assertEqual(kernel._connection.execute("SELECT token FROM kernel_budget_samples").fetchone()[0], token)
            evidence["first_cleanup_report"] = runtime._observation_cleanup_report

            phase[0] = "second_close"
            writers[0].rollback()
            wall[0] = evidence["entered"]["checkpoint"]["wall_at"]
            resumed_before = context.budget_envelope
            runtime.close()
            self.assertIsNone(context._budget_capture._pending)
            self.assertEqual(context.budget_envelope.constraints, resumed_before.constraints)
            self.assertEqual(context.budget_envelope.started_at, resumed_before.started_at)
            self.assertGreaterEqual(context.budget_envelope.checkpoint.wall_at, retained.checkpoint.wall_at)
            resumed_deadline = context.budget_envelope.deadline_monotonic(
                sample=sample_clock(wall_time=context.budget_envelope.checkpoint.wall_at))
            self.assertLessEqual(resumed_deadline, evidence["entered_native_deadline"])
            second_trace = [item for item in trace if item["phase"] == "second_close"]
            self.assertFalse(any(item["operation"] in ("armed", "sample") for item in second_trace))
            committed = [item for item in second_trace if item["operation"] == "ack" and item["committed"]]
            self.assertEqual([item["token"] for item in committed], [token])
            self.assertEqual([item["phase"] for item in trace if item["operation"] == "kernel_close"], ["second_close"])
            self.assertEqual(runtime._thread_contexts, {})
            self.assertEqual(runtime._thread_done, set())
            self.assertFalse(runtime._thread_authorities)
            self.assertTrue(runtime._thread_slots.acquire(blocking=False))
            runtime._thread_slots.release()
            self.assertFalse(runtime._observation_cleanup_pending)
            self.assertEqual(runtime._retired_observation_contexts, [])
            self.assertIsNone(runtime._close_error)
            self.assertEqual(calls, ["original"])
            receipts_after = runtime._settlement_journal.inspect("original")
            self.assertEqual(receipts_after[0]["result"], receipts_before[0]["result"])
            with self.assertRaises(sqlite3.ProgrammingError):
                kernel._connection.execute("SELECT 1")
            with SQLiteKernel(kernel.db_path, now=lambda: wall[0]) as fresh:
                canonical = BudgetEnvelope.from_dict(fresh.get_execution_limits("original")["envelope"])
                self.assertGreaterEqual(canonical.checkpoint.wall_at, retained.checkpoint.wall_at)
                self.assertEqual(canonical.constraints, retained.constraints)
                self.assertEqual(fresh._connection.execute("SELECT token FROM kernel_budget_samples").fetchall(), [])
                self.assertEqual(fresh.get("original").attempt, 1)
                evidence["canonical_after_retry"] = canonical.to_dict()
            evidence.update(calls=calls, resumed=context.budget_envelope.to_dict(),
                resumed_native_deadline=resumed_deadline, final_cleanup_report=runtime._observation_cleanup_report,
                same_token_acknowledged=True, capacity_released=True)
        finally:
            for writer in writers:
                writer.rollback()
                writer.close()
            driver.join(2)
            try:
                runtime.close()
            except BaseException as error:
                evidence["final_cleanup_error"] = {"type": type(error).__name__, "message": str(error)}
            evidence["driver_errors"] = [{"type": type(error).__name__, "message": str(error)} for error in driver_errors]
            evidence["outcomes"] = [None if item is None else item.to_dict() for item in outcomes]
            path = root / "evidence.json"
            path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print("budget_capture_close_lifetime_evidence=" + str(path), flush=True)


if __name__ == "__main__":
    unittest.main()
