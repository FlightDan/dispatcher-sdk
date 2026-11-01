"""Only exact acknowledged transient captures can be retired as uncertainty."""
import unittest
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, SQLiteKernel, runtime as runtime_module
from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture
from tests.test_execution_kernel_v2_sqlite import make_command


def _handler(payload, context):
    return {"execution_id": context.lease.execution_id, "pid": os.getpid()}


class RuntimeCaptureAckRegressionTests(unittest.TestCase):
    def setUp(self):
        self.capture = _KernelBudgetCapture(None, "execution")
        self.envelope = BudgetEnvelope((), sample_clock())

    def timeout(self, token=None, captured=None):
        error = BudgetClockUnknownError("budget_clock_capture_failed")
        error.__cause__ = TimeoutError("capture admission timed out")
        error.budget_sample_token = token
        error.budget_sample_envelope = captured
        return error

    def confirmed(self, error, checkpoint, capture=None):
        return process_runtime._confirmed_transient_capture_error(
            self.capture if capture is None else capture, error, checkpoint)

    def test_exact_ack_retires_transient_sample(self):
        self.assertTrue(self.confirmed(self.timeout("sample-1", self.envelope),
                                       {"state": "confirmed", "token": "sample-1"}))

    def test_proven_unarmed_timeout_retires_without_token(self):
        self.assertTrue(self.confirmed(self.timeout(), {"state": "confirmed"}))

    def test_other_or_missing_ack_never_retires_owned_sample(self):
        error = self.timeout("sample-1", self.envelope)
        for checkpoint in ({"state": "confirmed", "token": "sample-2"},
                           {"state": "confirmed"}, {"state": "unknown", "token": "sample-1"}):
            with self.subTest(checkpoint=checkpoint):
                self.assertFalse(self.confirmed(error, checkpoint))
        self.capture._pending = ("sample-1", self.envelope)
        self.assertFalse(self.confirmed(error, {"state": "confirmed", "token": "sample-1"}))
        self.capture._pending = ("sample-1", None)
        self.assertFalse(self.confirmed(error, {"state": "confirmed", "token": "sample-1"}))

    def test_nontransient_error_or_foreign_capture_never_retires(self):
        error = BudgetClockUnknownError("clock continuity unknown")
        error.budget_sample_token = "sample-1"
        self.assertFalse(self.confirmed(error, {"state": "confirmed", "token": "sample-1"}))
        self.assertFalse(self.confirmed(self.timeout("sample-1", self.envelope),
                                        {"state": "confirmed", "token": "sample-1"}, capture=object()))

    def test_sample_without_token_is_not_proven_unarmed(self):
        self.assertFalse(self.confirmed(self.timeout(None, self.envelope), {"state": "confirmed"}))

    def test_lock_delay_and_finish_share_original_deadline(self):
        clock = [0.0]
        owner = self.capture
        owner._pending = ("sample-1", self.envelope)
        class DelayedLock:
            def acquire(self, *, timeout):
                self.timeout = timeout
                clock[0] += .08
                return True
            def release(self):
                pass
        owner._lock = DelayedLock()
        granted = []
        def blocked_finish(envelope, *, timeout_seconds):
            granted.append(timeout_seconds)
            clock[0] += timeout_seconds
            raise TimeoutError("fixture finish blocked through its budget")
        with patch.object(process_runtime.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(owner, "finish_pending", side_effect=blocked_finish):
            _, checkpoint = process_runtime._finish_budget_capture(owner, self.envelope, timeout_seconds=.1)
        self.assertEqual(checkpoint["state"], "unknown")
        self.assertEqual(checkpoint["token"], "sample-1")
        self.assertAlmostEqual(owner._lock.timeout, .1)
        self.assertAlmostEqual(granted[0], .02)
        self.assertAlmostEqual(clock[0], .1)

    def test_rearm_waits_until_original_publication_releases_owner(self):
        owner = self.capture
        owner._pending = ("sample-1", self.envelope)
        entered, release, rearm_attempted, rearmed = (threading.Event() for _ in range(4))
        result, errors = [], []
        def hold_finish(envelope, *, timeout_seconds):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("fixture did not release publication")
            owner._acknowledged("sample-1", envelope)
            return envelope
        def publish():
            try:
                result.append(process_runtime._finish_budget_capture(owner, self.envelope, timeout_seconds=5))
            except BaseException as error:
                errors.append(error)
        def rearm():
            rearm_attempted.set()
            with owner._lock:
                owner._armed("sample-2")
                rearmed.set()
        with patch.object(owner, "finish_pending", side_effect=hold_finish):
            publishing = threading.Thread(target=publish)
            publishing.start()
            try:
                self.assertTrue(entered.wait(3))
                arming = threading.Thread(target=rearm)
                arming.start()
                self.assertTrue(rearm_attempted.wait(3))
                self.assertFalse(rearmed.wait(.1))
                self.assertEqual(owner._pending[0], "sample-1")
            finally:
                release.set()
                publishing.join(5)
                if "arming" in locals():
                    arming.join(5)
        self.assertFalse(publishing.is_alive())
        self.assertFalse(arming.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result[0][1], {"state": "confirmed", "token": "sample-1"})
        self.assertTrue(rearmed.is_set())
        self.assertEqual(owner._pending, ("sample-2", None))

    def test_maintenance_ack_before_publication_retains_exact_token_and_floor(self):
        with tempfile.TemporaryDirectory() as directory, SQLiteKernel(Path(directory) / "kernel.sqlite") as kernel:
            kernel.submit(make_command("execution"))
            lease = kernel.claim_and_start("worker", execution_id="execution", lease_seconds=120)
            original = kernel._prepare_handler_entry(lease)
            owner = _KernelBudgetCapture(kernel, "execution")
            token = kernel._begin_budget_sample("execution", timeout_seconds=1, _owner=owner)
            captured = original.recheckpoint(sample=sample_clock(wall_time=original.checkpoint.wall_at + 3))
            owner._captured(token, captured)
            error = self.timeout(token, captured)
            errors = []
            def maintenance():
                try:
                    owner.finish_pending(captured, timeout_seconds=1)
                except BaseException as exc:
                    errors.append(exc)
            worker = threading.Thread(target=maintenance)
            worker.start()
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            merged, checkpoint = process_runtime._finish_budget_capture(owner, original, timeout_seconds=1)
            self.assertEqual(checkpoint, {"state": "confirmed", "token": token})
            self.assertGreaterEqual(merged.checkpoint.wall_at, captured.checkpoint.wall_at)
            self.assertTrue(self.confirmed(error, checkpoint, capture=owner))
            self.assertFalse(self.confirmed(self.timeout("different-token", captured), checkpoint, capture=owner))
            # Model a new owner attempt: its unresolved marker must never be
            # confused with the earlier asynchronously acknowledged token.
            owner._armed("new-pending-token")
            _, checkpoint = process_runtime._finish_budget_capture(owner, original, timeout_seconds=1)
            self.assertEqual(checkpoint["state"], "unknown")
            self.assertEqual(checkpoint["token"], "new-pending-token")
            self.assertFalse(self.confirmed(error, checkpoint, capture=owner))

    @unittest.skipUnless(os.name == "posix", "requires the POSIX supervisor")
    def test_runtime_settles_after_injected_unarmed_transient_at_terminal(self):
        original_wait = process_runtime._wait_packet
        injected = []
        def wait_with_unarmed_timeout(receiver, deadline, tracker, *, hard=False):
            packet, remaining = original_wait(receiver, deadline, tracker, hard=hard)
            if not injected and isinstance(packet, dict) and packet.get("kind") in ("handler_contained", "handler_completed"):
                self.assertIsInstance(tracker.capture_budget, _KernelBudgetCapture)
                self.assertIsNone(tracker.capture_budget._pending)
                tracker.capture_error = self.timeout()
                injected.append(True)
            return packet, remaining

        # The timeout is injected at packet handoff; process isolation,
        # original handler execution, cleanup and Kernel settlement are real.
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"), \
             patch.object(process_runtime, "_wait_packet", side_effect=wait_with_unarmed_timeout):
            runtime = Kernel.open_sqlite(Path(directory) / "kernel.sqlite", {"handler": _handler}, isolation_mode="process")
            try:
                command = runtime.command("handler", execution_id="execution", idempotency_key="execution",
                    correlation_id="execution", timeout_seconds=15, payload={})
                runtime.submit(command)
                result = runtime.run_once(execution_id="execution")
                self.assertEqual(injected, [True])
                self.assertEqual(result.state, "succeeded", result.result.to_dict())
                self.assertNotEqual(result.result.value["pid"], os.getpid())
                obligation = runtime.kernel.inspect_supervisor_obligations("execution")["obligations"][0]
                self.assertEqual(obligation["resolution"]["result_id"], result.result.result_id)
                self.assertEqual(obligation["resolution"]["source"], "sdk_confirmed_supervisor_cleanup")
            finally:
                runtime.close()
