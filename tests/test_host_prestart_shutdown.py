import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.host import RuntimeHost


class BlockingRuntime:
    def __init__(self, error=None):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.error = error
        self.close_calls = 0

    def run_once(self):
        return None

    def reap(self):
        return []

    def close(self):
        self.close_calls += 1
        self.entered.set()
        self.release.wait()
        if self.error is not None:
            raise self.error


class Bridge:
    def pump(self, **kwargs):
        return None

    def sweep(self, **kwargs):
        return None


class HostPrestartShutdownTests(unittest.TestCase):
    def test_simultaneous_prestart_stop_callers_share_owner(self):
        runtime = BlockingRuntime()
        host = RuntimeHost(runtime, Bridge())
        barrier = threading.Barrier(3)
        results = []
        def stop():
            barrier.wait()
            results.append(host.stop(timeout=.05))
        callers = [threading.Thread(target=stop) for _ in range(2)]
        for caller in callers:
            caller.start()
        try:
            barrier.wait()
            for caller in callers:
                caller.join(1)
                self.assertFalse(caller.is_alive())
            self.assertEqual(results, [False, False])
            self.assertEqual(runtime.close_calls, 1)
            runtime.release.set()
            self.assertTrue(host.stop(timeout=1))
            self.assertEqual(runtime.close_calls, 1)
        finally:
            runtime.release.set()
            for caller in callers:
                caller.join(1)
            host.join(1)

    def test_shutdown_owner_start_failure_is_retryable(self):
        runtime = BlockingRuntime()
        host = RuntimeHost(runtime, Bridge())
        try:
            with patch.object(threading.Thread, 'start', side_effect=RuntimeError('cannot start owner')):
                with self.assertRaisesRegex(RuntimeError, 'cannot start owner'):
                    host.stop(timeout=.1)
            self.assertEqual(runtime.close_calls, 0)
            self.assertEqual(host.stop_report.status, 'failed')
            self.assertFalse(host.stop_report.can_continue_waiting)
            self.assertEqual(host.stop_report.errors[-1].source, 'shutdown_owner_start')
            self.assertFalse(host.stop(timeout=0))
            self.assertTrue(runtime.entered.wait(1))
            runtime.release.set()
            self.assertTrue(host.stop(timeout=1))
            self.assertEqual(host.stop_report.status, 'completed')
            self.assertEqual(runtime.close_calls, 1)
        finally:
            runtime.release.set()
            host.join(1)

    def test_concurrent_waiter_can_retry_owner_start_failure(self):
        runtime = BlockingRuntime()
        runtime.release.set()
        host = RuntimeHost(runtime, Bridge())
        begun = threading.Barrier(2)
        original_begin = host._begin_stop
        original_start = threading.Thread.start
        attempts, results = [], []
        def begin(timeout):
            original_begin(timeout)
            begun.wait()
        def start(thread):
            if thread.name == 'runtime-host-shutdown':
                attempts.append(1)
                if len(attempts) == 1:
                    raise RuntimeError('first owner failed')
            return original_start(thread)
        def stop():
            try:
                results.append(host.stop(timeout=1))
            except RuntimeError as exc:
                results.append(str(exc))
        callers = [threading.Thread(target=stop) for _ in range(2)]
        with patch.object(host, '_begin_stop', side_effect=begin), \
             patch.object(threading.Thread, 'start', autospec=True, side_effect=start):
            for caller in callers:
                caller.start()
            for caller in callers:
                caller.join(2)
                self.assertFalse(caller.is_alive())
        self.assertCountEqual(results, [True, 'first owner failed'])
        self.assertEqual(runtime.close_calls, 1)
        self.assertEqual(host.stop_report.status, 'completed')

    def test_revocation_owner_start_failure_does_not_close_runtime(self):
        runtime = BlockingRuntime()
        runtime.release.set()
        host = RuntimeHost(runtime, Bridge(), worker_count=1, pump_interval=.01).start()
        real_start = threading.Thread.start
        def start(thread):
            if thread.name == 'runtime-host-stop-request':
                raise RuntimeError('cannot start revocation owner')
            return real_start(thread)
        try:
            with patch.object(threading.Thread, 'start', autospec=True, side_effect=start):
                try:
                    host.stop(timeout=.2)
                except RuntimeError:
                    pass
                self.assertTrue(host.join(1))
            with self.assertRaisesRegex(RuntimeError, 'cannot start revocation owner'):
                host.stop(timeout=1)
            self.assertEqual(runtime.close_calls, 0)
        finally:
            # This test runtime has no active work; release its executor.
            host._shutdown_resources()

    def test_running_stop_bounds_blocked_revocation_and_waits_before_close(self):
        class Runtime:
            def __init__(self):
                self.started = threading.Event()
                self.request_entered = threading.Event()
                self.release = threading.Event()
                self.requests = 0
                self.closes = 0

            def run_once(self): return None
            def reap(self): self.started.set(); return []
            def request_stop(self):
                self.requests += 1
                self.request_entered.set()
                self.release.wait()
            def close(self): self.closes += 1

        runtime = Runtime()
        host = RuntimeHost(runtime, Bridge(), worker_count=1, pump_interval=.01).start()
        try:
            self.assertTrue(runtime.started.wait(1))
            barrier = threading.Barrier(3)
            results = []
            def stop():
                barrier.wait()
                results.append(host.stop(timeout=.05))
            callers = [threading.Thread(target=stop) for _ in range(2)]
            for caller in callers:
                caller.start()
            started = time.monotonic()
            barrier.wait()
            for caller in callers:
                caller.join(1)
                self.assertFalse(caller.is_alive())
            self.assertLess(time.monotonic() - started, .5)
            self.assertEqual(results, [False, False])
            self.assertTrue(runtime.request_entered.wait(1))
            self.assertEqual(runtime.closes, 0)
            self.assertFalse(host.stop(timeout=0))
            self.assertEqual(runtime.requests, 1)
            runtime.release.set()
            self.assertTrue(host.stop(timeout=1))
            self.assertEqual((runtime.requests, runtime.closes), (1, 1))
        finally:
            runtime.release.set()
            host.join(1)

    def test_deadline_retains_single_owner_and_later_stop_completes(self):
        runtime = BlockingRuntime()
        host = RuntimeHost(runtime, Bridge())
        try:
            started = time.monotonic()
            self.assertFalse(host.stop(timeout=.05))
            self.assertLess(time.monotonic() - started, .5)
            self.assertTrue(runtime.entered.wait(1))
            self.assertEqual(host.stop_report.status, 'timed_out')
            self.assertTrue(host.stop_report.can_continue_waiting)
            self.assertFalse(host.stop(timeout=0))
            self.assertEqual(runtime.close_calls, 1)
            runtime.release.set()
            self.assertTrue(host.stop(timeout=1))
            self.assertEqual(host.stop_report.status, 'completed')
            self.assertEqual(runtime.close_calls, 1)
        finally:
            runtime.release.set()
            host.join(1)

    def test_delayed_close_failure_is_preserved_for_later_callers(self):
        runtime = BlockingRuntime(OSError('close failed'))
        host = RuntimeHost(runtime, Bridge())
        try:
            self.assertFalse(host.stop(timeout=0))
            self.assertTrue(runtime.entered.wait(1))
            runtime.release.set()
            with self.assertRaisesRegex(RuntimeError, 'close failed'):
                host.stop(timeout=1)
            with self.assertRaisesRegex(RuntimeError, 'close failed'):
                host.stop(timeout=1)
            self.assertEqual(host.stop_report.status, 'failed')
            self.assertEqual(runtime.close_calls, 1)
        finally:
            runtime.release.set()
            host.join(1)


if __name__ == '__main__':
    unittest.main()
