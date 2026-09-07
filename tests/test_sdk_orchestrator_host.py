from collections import deque
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.host import RuntimeHost
from dispatcher_sdk.orchestrator.host import OrchestratorHost


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true")


class Runtime:
    def __init__(self):
        self.kernel = object()
        self.calls = 0
        self.closed = False

    def run_once(self):
        self.calls += 1

    def reap(self):
        return []

    def close(self):
        self.closed = True


class Orchestrator:
    def __init__(self):
        self.runtime = Runtime()
        self.kernel = self.runtime.kernel
        self.calls = []
        self.notifications = deque()
        self.collect_count = 0
        self.delivery_options = []
        self.delivery_error = None

    def flush(self, *, limit):
        self.calls.append(("flush", threading.get_ident(), limit))
        return 1

    def sync(self):
        self.calls.append(("sync", threading.get_ident(), None))

    def collect_notifications(self, *, limit):
        self.calls.append(("collect", threading.get_ident(), limit))
        self.collect_count += 1
        if self.collect_count == 1:
            self.notifications.append({"kind": "terminal", "run_id": "test"})
            return 1
        return 0

    def deliver_notifications(self, callback, **options):
        self.delivery_options.append(options)
        if self.delivery_error is not None:
            error, self.delivery_error = self.delivery_error, None
            raise error
        try:
            notification = self.notifications.popleft()
        except IndexError:
            return 0
        callback(notification)
        return 1


class OrchestratorHostTests(unittest.TestCase):
    def make_host(self, orchestrator, callback, **options):
        return OrchestratorHost(
            orchestrator, callback, worker_count=1, pump_interval=0.01,
            sweep_interval=0.03, notification_interval=0.01, **options)


    def test_context_manager_drives_and_delivers_without_consuming_results(self):
        orchestrator = Orchestrator()
        received = []
        callback_threads = []

        def callback(notification):
            received.append(notification)
            callback_threads.append(threading.get_ident())

        with self.make_host(orchestrator, callback, notification_owner="test-host") as host:
            self.assertIs(host.start(), host)
            self.assertTrue(host.wake("test"))
            wait_until(lambda: host.health().notification_deliveries == 1
                       and orchestrator.runtime.calls > 0)
            self.assertGreater(orchestrator.runtime.calls, 0)
            self.assertEqual(received, [{"kind": "terminal", "run_id": "test"}])
            coordinator_threads = {row[1] for row in orchestrator.calls}
            self.assertEqual(len(coordinator_threads), 1)
            self.assertNotIn(callback_threads[0], coordinator_threads)
            self.assertEqual(orchestrator.delivery_options[0], {
                "owner": "test-host", "lease_seconds": 30.0,
                "retry_delay": 1.0, "limit": 1})
        self.assertTrue(orchestrator.runtime.closed)
        self.assertEqual(host.health().state, "stopped")
        self.assertFalse(host.health().notification_alive)
        self.assertFalse(host.wake())
        self.assertTrue(host.stop(timeout=0.1))
        with self.assertRaises(RuntimeError):
            host.start()

    def test_blocking_callback_does_not_block_workers_or_coordinator(self):
        orchestrator = Orchestrator()
        entered = threading.Event()
        release = threading.Event()

        def callback(notification):
            entered.set()
            release.wait(3.0)

        host = self.make_host(orchestrator, callback)
        host.start()
        try:
            self.assertTrue(entered.wait(1.0))
            calls = orchestrator.runtime.calls
            collected = orchestrator.collect_count
            wait_until(lambda: orchestrator.runtime.calls > calls + 2
                       and orchestrator.collect_count > collected + 2)
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                host.stop(timeout=0.1)
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertTrue(orchestrator.runtime.closed)
            self.assertTrue(host.health().notification_alive)
            self.assertEqual(host.health().state, "stopping")
            self.assertTrue(host._thread.daemon)
        finally:
            release.set()
            self.assertTrue(host.stop(timeout=1.0))

    def test_delivery_store_error_is_visible_and_retried(self):
        orchestrator = Orchestrator()
        orchestrator.delivery_error = OSError("database busy")
        received = []
        with self.make_host(orchestrator, received.append) as host:
            wait_until(lambda: host.health().notification_deliveries == 1)
            # Notification delivery and coordinator startup run independently.
            wait_until(lambda: host.health().state == "running")
            health = host.health()
            self.assertEqual(health.notification_error_count, 1)
            self.assertEqual(health.last_notification_error, "OSError: database busy")
            self.assertEqual(health.state, "running")

    def test_no_callback_collects_notifications_without_claiming_or_acknowledging(self):
        orchestrator = Orchestrator()
        host = self.make_host(orchestrator, None)
        host.start()
        try:
            wait_until(lambda: orchestrator.collect_count > 0
                       and orchestrator.runtime.calls > 0)
            self.assertEqual(host.health().notification_deliveries, 0)
            self.assertFalse(host.health().notification_alive)
            self.assertEqual(orchestrator.delivery_options, [])
            self.assertEqual(tuple(orchestrator.notifications),
                             ({"kind": "terminal", "run_id": "test"},))
            self.assertTrue(any(call[0] == "flush" for call in orchestrator.calls))
            self.assertTrue(any(call[0] == "sync" for call in orchestrator.calls))
        finally:
            self.assertTrue(host.stop(timeout=1.0))

    def test_no_callback_start_is_idempotent_and_stop_is_repeatable(self):
        orchestrator = Orchestrator()
        host = self.make_host(orchestrator, None)
        self.assertIs(host.start(), host)
        self.assertIs(host.start(), host)
        self.assertIsNone(host._thread)
        self.assertFalse(host.health().notification_alive)
        self.assertTrue(host.stop(timeout=1.0))
        self.assertTrue(host.stop(timeout=0.1))
        self.assertEqual(host.health().state, "stopped")

    def test_none_is_the_only_noncallable_callback_allowed(self):
        orchestrator = Orchestrator()
        with self.assertRaisesRegex(TypeError, "callable or None"):
            self.make_host(orchestrator, object())

    def test_missing_or_mismatched_runtime_is_rejected(self):
        orchestrator = Orchestrator()
        orchestrator.runtime = None
        with self.assertRaisesRegex(ValueError, "requires.*runtime"):
            self.make_host(orchestrator, lambda notification: None)
        orchestrator.runtime = Runtime()
        with self.assertRaisesRegex(ValueError, "share the Kernel"):
            self.make_host(orchestrator, lambda notification: None)

    def test_stop_before_start_closes_runtime_and_validates_deadline(self):
        orchestrator = Orchestrator()
        host = self.make_host(orchestrator, lambda notification: None)
        for timeout in (None, -1, float("inf"), float("nan"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                host.stop(timeout=timeout)
        self.assertTrue(host.stop(timeout=0))
        self.assertTrue(orchestrator.runtime.closed)

    def test_notification_thread_start_failure_stops_runtime(self):
        orchestrator = Orchestrator()
        host = self.make_host(orchestrator, lambda notification: None)
        original_start = threading.Thread.start

        def start(thread):
            if thread.name == "orchestrator-host-notifications":
                raise RuntimeError("notification startup failed")
            return original_start(thread)

        with patch.object(threading.Thread, "start", start):
            with self.assertRaisesRegex(RuntimeError, "notification startup failed"):
                host.start()
        self.assertTrue(orchestrator.runtime.closed)
        self.assertTrue(host.stop(timeout=1))


if __name__ == "__main__":
    unittest.main()
