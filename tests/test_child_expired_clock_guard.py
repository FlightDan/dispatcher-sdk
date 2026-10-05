"""Expired reconstruction still reports its original unresolved clock authority."""
import sqlite3
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, sample_clock
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture
from dispatcher_sdk.execution_kernel.children import _RetryWindow
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests import test_child_clock_checkpoint as fixture


class ExpiredChildClockGuardTests(unittest.TestCase):
    setUp = fixture.ChildClockCheckpointTests.setUp
    tearDown = fixture.ChildClockCheckpointTests.tearDown
    command = staticmethod(fixture.ChildClockCheckpointTests.command)

    def test_custom_kernel_admission_expiry_preserves_original_error_without_sqlite_api(self):
        original = self.parent_budget.derive(source="tool", origin_id="custom-kernel-original", timeout_seconds=.03)
        error = TimeoutError("Kernel control lock admission timed out")
        calls = []

        def blocked_sample(execution_id, envelope, *, timeout_seconds):
            calls.append(timeout_seconds)
            time.sleep(timeout_seconds + .002)
            raise error

        with self.assertRaises(TimeoutError) as caught:
            _RetryWindow(original, SimpleNamespace(_sample_budget=blocked_sample))
        self.assertIs(error, caught.exception)
        self.assertEqual(1, len(calls))
        self.assertGreater(calls[0], 0)
        self.assertLessEqual(calls[0], .03)

    def test_positive_reconstruction_cannot_trust_timeout_before_guard_inspection(self):
        original = self.parent_budget.derive(source="tool", origin_id="positive-original", timeout_seconds=1)
        capture = _KernelBudgetCapture(self.kernel, "parent")
        baseline = self.wall[0]
        begin = self.kernel._begin_budget_sample
        writer = sqlite3.connect(self.kernel.db_path, isolation_level=None)
        tokens = []

        def arm_and_hold(execution_id, **options):
            token = begin(execution_id, **options)
            tokens.append(token)
            writer.execute("BEGIN IMMEDIATE")
            self.wall[0] = baseline + 4
            return token

        try:
            with patch.object(self.kernel, "_begin_budget_sample", side_effect=arm_and_hold):
                with self.assertRaises((sqlite3.OperationalError, TimeoutError)):
                    capture(original, timeout_seconds=.1)
            self.assertIsNotNone(capture._pending[1])
        finally:
            self.wall[0] = baseline
            writer.rollback()
            writer.close()
        before = original.view(sample=sample_clock(wall_time=original.checkpoint.wall_at))
        self.assertGreater(before.remaining_work_seconds, 0)
        with SQLiteKernel(self.kernel.db_path, now=lambda: self.wall[0]) as fresh:
            statements, attempts = [], []
            fresh._connection.set_trace_callback(statements.append)

            def exhaust_admission(deadline):
                # Actual admission time expires before the normal guard read.
                # The original protected sample and SQL marker remain real.
                attempts.append(deadline)
                time.sleep(max(0, deadline - time.monotonic()) + .002)
                return False

            try:
                with patch.object(fresh, "_drain_budget_samples", side_effect=exhaust_admission), \
                        patch.object(fresh, "_wall_time", side_effect=AssertionError("unprotected wall read")):
                    with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved"):
                        _RetryWindow(original, fresh)
                self.assertGreaterEqual(len(attempts), 2)
                self.assertEqual(tokens, [row[0] for row in fresh._connection.execute(
                    "SELECT token FROM kernel_budget_samples WHERE execution_id='parent'")])
                self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "BEGIN IMMEDIATE"))
                                     for sql in statements), statements)
                self.assertTrue(self.kernel._budget_sample_status("parent"))
                self.evidence["records"].append({"scenario": "positive_reconstruction_admission_expires_before_guard",
                    "original_budget": original.to_dict(), "positive_initial_view": before.to_dict(),
                    "guard_tokens": tokens, "captured_fact": capture._pending[1].to_dict(),
                    "original_admission_deadlines": attempts, "readonly_statements": statements})
            finally:
                fresh._connection.set_trace_callback(None)

    def test_expired_original_window_keeps_foreign_guard_unknown_without_sampling(self):
        original = self.parent_budget.derive(source="tool", origin_id="expired-original", timeout_seconds=.3)
        capture = _KernelBudgetCapture(self.kernel, "parent")
        baseline = self.wall[0]
        begin = self.kernel._begin_budget_sample
        writer = sqlite3.connect(self.kernel.db_path, isolation_level=None)
        tokens = []

        def arm_and_hold(execution_id, **options):
            token = begin(execution_id, **options)
            tokens.append(token)
            writer.execute("BEGIN IMMEDIATE")
            self.wall[0] = baseline + 4
            return token

        try:
            with patch.object(self.kernel, "_begin_budget_sample", side_effect=arm_and_hold):
                with self.assertRaises((sqlite3.OperationalError, TimeoutError)):
                    capture(original, timeout_seconds=.1)
            self.assertIsNotNone(capture._pending[1])
        finally:
            self.wall[0] = baseline
            writer.rollback()
            writer.close()
        while True:
            expired = original.view(sample=sample_clock(wall_time=original.checkpoint.wall_at))
            if expired.remaining_work_seconds <= 0:
                break
            # Project this same retained floor until its elapsed clock proves
            # expiry; one sleep need not cross a coarse Windows clock tick.
            time.sleep(expired.remaining_work_seconds)
        self.assertEqual(0, expired.remaining_work_seconds)
        with SQLiteKernel(self.kernel.db_path, now=lambda: self.wall[0]) as fresh:
            statements = []
            fresh._connection.set_trace_callback(statements.append)
            try:
                with patch.object(fresh, "_sample_budget", side_effect=AssertionError("new authoritative sample")):
                    with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved"):
                        _RetryWindow(original, fresh)
                self.assertEqual(tokens, [row[0] for row in fresh._connection.execute(
                    "SELECT token FROM kernel_budget_samples WHERE execution_id='parent'")])
                self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "BEGIN IMMEDIATE"))
                                     for sql in statements), statements)
                self.assertTrue(self.kernel._budget_sample_status("parent"))
                self.evidence["records"].append({"scenario": "expired_fresh_original_guard",
                    "original_budget": original.to_dict(), "expired_view": expired.to_dict(),
                    "guard_tokens": tokens, "captured_fact": capture._pending[1].to_dict(),
                    "readonly_statements": statements})
            finally:
                fresh._connection.set_trace_callback(None)


if __name__ == "__main__":
    unittest.main()
