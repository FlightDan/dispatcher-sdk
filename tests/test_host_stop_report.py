from collections import deque
import json
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.host import RuntimeHost
from dispatcher_sdk.orchestrator.host import (
    OrchestratorHost,
    OrchestratorHostTimeoutError,
)


class Bridge:
    def pump(self, *, limit=100):
        del limit
        return type("Report", (), {"dispatch_deliveries": 0})()

    def sweep(self, *, limit=100):
        return self.pump(limit=limit)


class ClosingRuntime:
    def __init__(self, *, block_close=False, close_error=None):
        self.kernel = object()
        self.close_entered = threading.Event()
        self.close_release = threading.Event()
        self.block_close = block_close
        self.close_error = close_error

    def reap(self):
        return []

    def run_once(self):
        return None

    def close(self):
        self.close_entered.set()
        if self.block_close:
            self.close_release.wait(3.0)
        if self.close_error is not None:
            raise self.close_error


class Orchestrator:
    def __init__(self, runtime):
        self.runtime = runtime
        self.kernel = runtime.kernel
        self.notifications = deque([{"kind": "terminal"}])

    def flush(self, *, limit):
        del limit
        return 0

    def sync(self):
        return None

    def collect_notifications(self, *, limit):
        del limit
        return 0

    def deliver_notifications(self, callback, **options):
        del options
        try:
            item = self.notifications.popleft()
        except IndexError:
            return 0
        callback(item)
        return 1


def phase(report, name):
    return next(item for item in report.phases if item.name == name)


class HostStopReportTests(unittest.TestCase):
    def test_nonfinite_stop_timeouts_are_rejected_before_state_changes(self):
        for started in (False, True):
            host = RuntimeHost(ClosingRuntime(), Bridge(), worker_count=1)
            if started:
                host.start()
            try:
                for timeout in (float("nan"), float("inf"), -float("inf")):
                    with self.subTest(started=started, timeout=timeout):
                        with self.assertRaises(ValueError):
                            host.stop(timeout=timeout)
                        self.assertIsNone(host.stop_report)
            finally:
                host.stop(timeout=1)
            json.dumps(host.stop_report.to_dict(), allow_nan=False)

    def test_coordinator_failure_is_not_erased_by_successful_resource_stop(self):
        class BadReport:
            @property
            def dispatch_deliveries(self):
                raise RuntimeError("invalid bridge report")

        class BadBridge(Bridge):
            def pump(self, *, limit=100):
                return BadReport()

        host = RuntimeHost(ClosingRuntime(), BadBridge(), worker_count=1).start()
        self.assertTrue(host.join(timeout=2))
        self.assertEqual(host.stop_report.status, "failed")
        self.assertTrue(host.stop(timeout=1))  # Preserve the existing stop contract.
        self.assertEqual(host.stop_report.status, "failed")
        self.assertEqual(host.health().state, "failed")
        self.assertIn("coordinator", [error.source for error in host.stop_report.errors])

    def test_timeout_snapshot_preserves_call_status_when_runtime_finishes_at_boundary(self):
        host = OrchestratorHost(Orchestrator(ClosingRuntime()))
        host.runtime_host.stop(timeout=1)
        with patch.object(host.runtime_host, "stop", return_value=False):
            with self.assertRaises(OrchestratorHostTimeoutError) as raised:
                host.stop(timeout=0)
        self.assertEqual(raised.exception.report.status, "timed_out")
        self.assertEqual(host.stop_report.status, "timed_out")
        self.assertTrue(host.stop(timeout=1))
        self.assertEqual(host.stop_report.status, "completed")

    def test_cleanup_failure_does_not_hide_a_still_running_notification_thread(self):
        entered, release = threading.Event(), threading.Event()

        def callback(_):
            entered.set()
            release.wait(3)

        host = OrchestratorHost(
            Orchestrator(ClosingRuntime(close_error=OSError("close incomplete"))), callback,
            worker_count=1, pump_interval=0.01, notification_interval=0.01,
        ).start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                host.stop(timeout=0.05)
            self.assertEqual(host.stop_report.status, "failed")
            self.assertTrue(host.stop_report.can_continue_waiting)
            self.assertTrue(host.stop_report.notification_thread_alive)
        finally:
            release.set()
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                host.stop(timeout=1)
        self.assertFalse(host.stop_report.can_continue_waiting)

    def test_runtime_stop_request_uses_the_original_monotonic_budget(self):
        now = [10.0]

        class Runtime(ClosingRuntime):
            def request_stop(self):
                now[0] += 0.04

        class Coordinator:
            def __init__(self):
                self.joins = []

            def join(self, timeout):
                self.joins.append(timeout)
                if len(self.joins) == 1:
                    now[0] += timeout

            def is_alive(self):
                return True

        runtime = Runtime()
        host = RuntimeHost(runtime, Bridge())
        coordinator = Coordinator()
        host._coordinator = coordinator
        host._state = "running"
        with patch(
            "dispatcher_sdk.execution_kernel.host.time.monotonic",
            side_effect=lambda: now[0],
        ):
            self.assertFalse(host.stop(timeout=0.1))
        self.assertAlmostEqual(coordinator.joins[0], 0.05)
        self.assertAlmostEqual(coordinator.joins[1], 0.01)

    def test_runtime_close_timeout_report_is_live_json_and_retry_completes(self):
        runtime = ClosingRuntime(block_close=True)
        host = RuntimeHost(
            runtime, Bridge(), worker_count=1, pump_interval=0.01,
            sweep_interval=1.0,
        ).start()
        try:
            self.assertFalse(host.stop(timeout=0.05))
            report = host.stop_report
            self.assertIsNotNone(report)
            self.assertEqual(report.scope, "runtime_host")
            self.assertEqual(report.status, "timed_out")
            self.assertEqual(phase(report, "worker_drain").status, "completed")
            self.assertEqual(phase(report, "final_pump").status, "completed")
            self.assertEqual(phase(report, "runtime_close").status, "in_progress")
            self.assertIn("runtime_close", report.unfinished_phases)
            self.assertEqual(report.active_worker_count, 0)
            self.assertTrue(report.can_continue_waiting)
            json.dumps(report.to_dict())

            runtime.close_release.set()
            self.assertTrue(host.stop(timeout=1.0))
            completed = host.stop_report
            self.assertEqual(completed.status, "completed")
            self.assertEqual(completed.unfinished_phases, ())
            self.assertFalse(completed.can_continue_waiting)
        finally:
            runtime.close_release.set()

    def test_notification_only_timeout_attaches_scoped_report(self):
        runtime = ClosingRuntime()
        orchestrator = Orchestrator(runtime)
        entered = threading.Event()
        release = threading.Event()

        def callback(_notification):
            entered.set()
            release.wait(3.0)

        host = OrchestratorHost(
            orchestrator, callback, worker_count=1, pump_interval=0.01,
            sweep_interval=1.0, notification_interval=0.01,
        ).start()
        try:
            self.assertTrue(entered.wait(1.0))
            with self.assertRaises(OrchestratorHostTimeoutError) as raised:
                host.stop(timeout=0.05)
            report = raised.exception.report
            self.assertEqual(host.stop_report.status, "timed_out")
            self.assertEqual(host.stop_report.unfinished_phases, report.unfinished_phases)
            self.assertEqual(report.scope, "orchestrator_host")
            self.assertEqual(report.status, "timed_out")
            self.assertEqual(phase(report, "runtime_close").status, "completed")
            self.assertEqual(phase(report, "notification_join").status, "in_progress")
            self.assertTrue(report.notification_thread_alive)
            self.assertIsNone(report.pending_delivery_count)
            self.assertIsNone(report.pending_delivery_persisted)
            self.assertTrue(report.can_continue_waiting)
            json.dumps(report.to_dict())
        finally:
            release.set()
            self.assertTrue(host.stop(timeout=1.0))
        self.assertEqual(host.stop_report.status, "completed")
        self.assertEqual(phase(host.stop_report, "notification_join").status, "completed")

    def test_runtime_and_notification_timeout_reports_both_unfinished_phases(self):
        runtime = ClosingRuntime(block_close=True)
        orchestrator = Orchestrator(runtime)
        callback_entered = threading.Event()
        callback_release = threading.Event()

        def callback(_notification):
            callback_entered.set()
            callback_release.wait(3.0)

        host = OrchestratorHost(
            orchestrator, callback, worker_count=1, pump_interval=0.01,
            sweep_interval=1.0, notification_interval=0.01,
        ).start()
        try:
            self.assertTrue(callback_entered.wait(1.0))
            with self.assertRaises(OrchestratorHostTimeoutError) as raised:
                host.stop(timeout=0.05)
            report = raised.exception.report
            self.assertEqual(phase(report, "runtime_close").status, "in_progress")
            self.assertEqual(phase(report, "notification_join").status, "in_progress")
            self.assertIn("runtime_close", report.unfinished_phases)
            self.assertIn("notification_join", report.unfinished_phases)
            self.assertTrue(report.can_continue_waiting)
        finally:
            runtime.close_release.set()
            callback_release.set()
            self.assertTrue(host.stop(timeout=1.0))

    def test_cleanup_error_is_preserved_in_report_and_on_repeated_stop(self):
        runtime = ClosingRuntime(close_error=OSError("close incomplete"))
        host = RuntimeHost(runtime, Bridge(), worker_count=1, pump_interval=0.01)
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                host.stop(timeout=0.1)
            report = host.stop_report
            self.assertEqual(report.status, "failed")
            self.assertEqual(phase(report, "runtime_close").status, "failed")
            self.assertEqual(phase(report, "runtime_close").error_type, "OSError")
            self.assertIn("runtime_close", report.unfinished_phases)
            self.assertFalse(report.can_continue_waiting)


if __name__ == "__main__":
    unittest.main()
