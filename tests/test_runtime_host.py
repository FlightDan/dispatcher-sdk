from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from queue import SimpleQueue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel.host import RuntimeHost


def echo_handler(payload, _context):
    return {"value": payload["value"]}


echo_handler.__execution_kernel_revision__ = "runtime-host-test-v1"


class RecordingBridge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.thread_ids: set[int] = set()
        self.sweep_calls = 0
        self.pump_calls = 0

    def _record(self) -> None:
        with self._lock:
            self.thread_ids.add(threading.get_ident())

    def sweep(self, *, limit: int = 100):
        del limit
        self._record()
        with self._lock:
            self.sweep_calls += 1
        return SimpleNamespace(dispatch_deliveries=0)

    def pump(self, *, limit: int = 100):
        del limit
        self._record()
        with self._lock:
            self.pump_calls += 1
        return SimpleNamespace(dispatch_deliveries=0)


def make_command(execution_id: str, revision: str, *, value: int = 1) -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=f"key-{execution_id}",
        registry_revision=revision,
        correlation_id=f"correlation-{execution_id}",
        causation_id=None,
        handler_id="echo",
        handler_contract_version=1,
        retry_policy=RetryPolicy(),
        timeout_seconds=2.0,
        payload={"value": value},
    )


def wait_until(predicate, timeout: float = 3.0, poll_interval: float = 0.01) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(poll_interval)
    if not predicate():
        raise AssertionError("condition did not become true before timeout")




class RuntimeHostTests(unittest.TestCase):
    def test_worker_submission_respects_and_clears_its_own_backoff(self) -> None:
        from concurrent.futures import Future
        from unittest.mock import Mock

        runtime = SimpleNamespace(reap=lambda: None, run_once=lambda: None,
                                  close=lambda: None)
        host = RuntimeHost(runtime, RecordingBridge(), worker_count=1,
                           pump_interval=0.01, retry_initial=0.2, retry_max=1)
        future = Future()
        host._executor = Mock()
        host._executor.submit.side_effect = [RuntimeError("executor unavailable"), future]
        now = [10.0]
        with patch("dispatcher_sdk.execution_kernel.host.time.monotonic", side_effect=lambda: now[0]):
            host._fill_workers(force=True)
            for now[0] in (10.01, 10.1, 10.19):
                host.wake()
                host._fill_workers(force=True)
            self.assertEqual(host._executor.submit.call_count, 1)
            now[0] = 10.2
            host._fill_workers()
        self.assertEqual(host._executor.submit.call_count, 2)
        self.assertEqual(host.health().active_workers, 1)
        self.assertEqual(host.health().error_count, 1)
        self.assertEqual(host._consecutive_errors["worker_submit"], 0)
        self.assertEqual(host._retry_at["worker_submit"], 0)

    def test_channel_backoff_sleeps_and_keeps_other_channels_running(self) -> None:
        for failing_source in ("pump", "sweep", "progress_hook"):
            with self.subTest(source=failing_source):
                now = [10.0]
                calls = {source: [] for source in ("pump", "sweep", "progress_hook")}

                def operation(source):
                    calls[source].append(now[0])
                    # The first sweep is startup; inject failures only after
                    # startup so this exercises the running recovery loop.
                    startup_sweep = source == "sweep" and len(calls[source]) == 1
                    if source == failing_source and not startup_sweep:
                        raise RuntimeError("temporary channel failure")
                    return False if source == "progress_hook" else SimpleNamespace(dispatch_deliveries=0)

                runtime = SimpleNamespace(reap=lambda: None, run_once=lambda: None,
                                          close=lambda: None)
                bridge = SimpleNamespace(
                    pump=lambda **_: operation("pump"),
                    sweep=lambda **_: operation("sweep"),
                )
                host = RuntimeHost(runtime, bridge, pump_interval=0.01,
                                   sweep_interval=0.02, retry_initial=0.2, retry_max=0.2,
                                   progress_hook=lambda: operation("progress_hook"))
                waits = []

                def advance(deadline=None, **_):
                    self.assertIsNotNone(deadline)
                    self.assertGreater(deadline, now[0], "coordinator must not spin during backoff")
                    waits.append(deadline - now[0])
                    now[0] = min(deadline, now[0] + host.pump_interval)
                    if now[0] >= 10.39:
                        host._stop_event.set()

                with patch("dispatcher_sdk.execution_kernel.host.time.monotonic", side_effect=lambda: now[0]), \
                        patch.object(host, "_wait", side_effect=advance), \
                        patch.object(host, "_fill_workers"), \
                        patch.object(host, "_shutdown_resources"):
                    host._run()

                self.assertNotEqual(host.health().state, "failed", host.health().last_error)
                failed_calls = calls[failing_source][1:] if failing_source == "sweep" else calls[failing_source]
                self.assertEqual(len(failed_calls), 2)
                self.assertGreaterEqual(failed_calls[1], failed_calls[0] + 0.2)
                for source, timestamps in calls.items():
                    if source != failing_source:
                        self.assertGreater(len(timestamps), 10, source)
                self.assertLess(len(waits), 80)





    def test_coordinator_start_failure_closes_owned_runtime(self) -> None:
        class Runtime:
            def __init__(self) -> None:
                self.closed = False

            def reap(self):
                return []

            def run_once(self):
                return None

            def close(self):
                self.closed = True

        runtime = Runtime()
        host = RuntimeHost(runtime, RecordingBridge())
        with patch.object(
            threading.Thread,
            "start",
            side_effect=RuntimeError("injected coordinator start failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "coordinator start failure"):
                host.start()

        self.assertTrue(runtime.closed)
        self.assertEqual(host.health().state, "failed")
        self.assertTrue(host.stop(timeout=0.1))


    def test_start_construction_failures_release_owned_resources(self) -> None:
        for target in ("ThreadPoolExecutor", "threading.Thread"):
            with self.subTest(target=target):
                runtime = SimpleNamespace(
                    reap=lambda: [], run_once=lambda: None,
                    close=unittest.mock.Mock(),
                )
                host = RuntimeHost(runtime, RecordingBridge())
                with patch(
                    f"dispatcher_sdk.execution_kernel.host.{target}",
                    side_effect=RuntimeError("injected construction failure"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "construction failure"):
                        host.start()
                self.assertEqual(host.health().state, "failed")
                runtime.close.assert_called_once_with()
                self.assertTrue(host.stop(timeout=0.1))
                runtime.close.assert_called_once_with()

    def test_close_failure_never_reports_successful_stop(self) -> None:
        for phase in ("new", "start_failure", "running"):
            with self.subTest(phase=phase):
                runtime = SimpleNamespace(
                    reap=lambda: [], run_once=lambda: None,
                    close=unittest.mock.Mock(side_effect=OSError("close incomplete")),
                )
                host = RuntimeHost(runtime, RecordingBridge(), pump_interval=0.01)
                if phase == "start_failure":
                    with patch.object(threading.Thread, "start", side_effect=RuntimeError("start failed")):
                        with self.assertRaisesRegex(RuntimeError, "start failed"):
                            host.start()
                elif phase == "running":
                    host.start()
                    wait_until(lambda: host.health().state == "running")
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                        host.stop(timeout=1.0)
                self.assertEqual(host.health().state, "failed")
                runtime.close.assert_called_once_with()

    def test_kernel_repeated_close_propagates_original_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Kernel.open_sqlite(Path(temp) / "kernel.sqlite3", {})
            real_close = runtime.kernel.close
            try:
                with patch.object(runtime.kernel, "close", side_effect=OSError("kernel close failed")):
                    for _ in range(2):
                        with self.assertRaisesRegex(OSError, "kernel close failed"):
                            runtime.close()
            finally:
                real_close()

    def test_start_failure_still_closes_runtime_if_empty_executor_shutdown_fails(self) -> None:
        runtime = SimpleNamespace(reap=lambda: [], run_once=lambda: None, close=unittest.mock.Mock())
        host = RuntimeHost(runtime, RecordingBridge())
        with patch("dispatcher_sdk.execution_kernel.host.threading.Thread", side_effect=RuntimeError("construction failed")), patch(
            "dispatcher_sdk.execution_kernel.host.ThreadPoolExecutor.shutdown", side_effect=OSError("shutdown failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "construction failed"):
                host.start()
        runtime.close.assert_called_once_with()
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            host.stop()

    def test_final_flush_failure_closes_runtime_and_is_reported(self) -> None:
        runtime = SimpleNamespace(reap=lambda: [], run_once=lambda: None, close=unittest.mock.Mock())
        bridge = RecordingBridge()
        host = RuntimeHost(runtime, bridge, pump_interval=0.01)
        host.start()
        wait_until(lambda: host.health().state == "running")
        with patch.object(bridge, "pump", side_effect=OSError("final pump failed")):
            with self.assertRaisesRegex(RuntimeError, "final Bridge flush failed"):
                host.stop(timeout=1.0)
        runtime.close.assert_called_once_with()
        self.assertEqual(host.health().state, "failed")

    def test_coordinator_failure_waits_for_worker_before_runtime_close(self) -> None:
        class Runtime:
            def __init__(self) -> None:
                self.entered = threading.Event()
                self.finished = threading.Event()
                self.release = threading.Event()
                self.closed_while_active = False
                self.closed = False

            def reap(self):
                return []

            def run_once(self):
                self.entered.set()
                self.release.wait(3.0)
                self.finished.set()
                return None

            def request_stop(self):
                self.release.set()

            def close(self):
                self.closed_while_active = not self.finished.is_set()
                self.closed = True

        class ExplodingReport:
            @property
            def dispatch_deliveries(self):
                raise RuntimeError("coordinator report failure")

        class Bridge(RecordingBridge):
            def pump(self, *, limit: int = 100):
                del limit
                self._record()
                if self.sweep_calls and runtime.entered.is_set():
                    return ExplodingReport()
                return SimpleNamespace(dispatch_deliveries=0)

        runtime = Runtime()
        host = RuntimeHost(
            runtime,
            Bridge(),
            worker_count=1,
            sweep_interval=1.0,
            pump_interval=0.01,
        )
        host.start()
        self.assertTrue(runtime.entered.wait(1.0))
        self.assertTrue(host.join(2.0))
        self.assertEqual(host.health().state, "failed")
        self.assertTrue(runtime.finished.is_set())
        self.assertTrue(runtime.closed)
        self.assertFalse(runtime.closed_while_active)

    def test_stop_timeout_preserves_resources_until_coordinator_quiesces(self) -> None:
        class Runtime:
            def __init__(self) -> None:
                self.closed = False

            def reap(self):
                return []

            def run_once(self):
                return None

            def close(self):
                self.closed = True

        class BlockingBridge(RecordingBridge):
            def __init__(self) -> None:
                super().__init__()
                self.entered = threading.Event()
                self.release = threading.Event()

            def pump(self, *, limit: int = 100):
                self.entered.set()
                if not self.release.is_set():
                    self.release.wait(2.0)
                return super().pump(limit=limit)

        runtime = Runtime()
        bridge = BlockingBridge()
        host = RuntimeHost(
            runtime,
            bridge,
            worker_count=1,
            sweep_interval=1.0,
            pump_interval=0.01,
        )
        host.start()
        self.assertTrue(bridge.entered.wait(1.0))
        self.assertFalse(host.stop(timeout=0.1))
        self.assertFalse(runtime.closed)
        bridge.release.set()
        self.assertTrue(host.join(2.0))
        self.assertTrue(runtime.closed)

    def test_bounded_stop_uses_nonclosing_authority_revocation(self) -> None:
        class Runtime:
            def __init__(self) -> None:
                self.entered = threading.Event()
                self.release = threading.Event()
                self.stop_requests = 0
                self.closed = False

            def reap(self):
                return []

            def run_once(self):
                self.entered.set()
                self.release.wait(2.0)
                return None

            def request_stop(self):
                self.stop_requests += 1
                self.release.set()

            def close(self):
                self.closed = True

        runtime = Runtime()
        host = RuntimeHost(
            runtime,
            RecordingBridge(),
            worker_count=1,
            sweep_interval=1.0,
            pump_interval=0.01,
        )
        host.start()
        self.assertTrue(runtime.entered.wait(1.0))
        self.assertTrue(host.stop(timeout=1.0))
        self.assertEqual(runtime.stop_requests, 1)
        self.assertTrue(runtime.closed)


    def test_startup_recovery_reaps_expired_execution_and_keeps_pumping(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            first = Kernel.open_sqlite(
                path,
                {("echo", 1): echo_handler},
                isolation_mode="thread",
                lease_seconds=0.01,
            )
            command = make_command("host-recovery", first.registry_revision)
            command = replace(
                command,
                retry_policy=RetryPolicy(max_attempts=2),
            )
            try:
                first.submit(command)
                running = first.kernel.claim_and_start(
                    first.worker_id,
                    lease_seconds=0.01,
                    start_safety_seconds=0,
                    registry_revision=first.registry_revision,
                )
                self.assertIsNotNone(running)
            finally:
                first.close()
            time.sleep(0.04)

            runtime = Kernel.open_sqlite(
                path,
                {("echo", 1): echo_handler},
                isolation_mode="thread",
                lease_seconds=1.0,
            )
            bridge = RecordingBridge()
            host = RuntimeHost(
                runtime,
                bridge,
                worker_count=1,
                sweep_interval=0.05,
                pump_interval=0.01,
                retry_initial=0.01,
                retry_max=0.05,
            )
            try:
                host.start()
                wait_until(
                    lambda: runtime.kernel.get(command.execution_id).state
                    == "succeeded"
                )
                self.assertGreaterEqual(bridge.sweep_calls, 1)
                self.assertGreaterEqual(bridge.pump_calls, 1)
                self.assertEqual(len(bridge.thread_ids), 1)
            finally:
                self.assertTrue(host.stop(timeout=3.0))
                self.assertTrue(host.join(0.1))

    def test_worker_exception_is_recorded_and_host_stays_alive(self) -> None:
        class Runtime:
            def __init__(self) -> None:
                self.calls = 0
                self.closed = False

            def reap(self):
                return []

            def run_once(self):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("transient worker failure")
                return None

            def close(self):
                self.closed = True

        runtime = Runtime()
        bridge = RecordingBridge()
        host = RuntimeHost(
            runtime,
            bridge,
            worker_count=2,
            sweep_interval=0.05,
            pump_interval=0.01,
            retry_initial=0.01,
            retry_max=0.05,
        )
        try:
            host.start()
            wait_until(lambda: host.health().error_count >= 1)
            health = host.health()
            self.assertEqual(health.state, "running")
            self.assertTrue(health.coordinator_alive)
            self.assertEqual(health.last_error.source, "worker")
            self.assertGreaterEqual(runtime.calls, 2)
        finally:
            self.assertTrue(host.stop(timeout=2.0))
            self.assertTrue(runtime.closed)

    def test_same_run_tasks_have_overlapping_execution_intervals(self) -> None:
        barrier = threading.Barrier(2)
        # Runtime observations belong in an external sink, not a mutable JSON
        # closure that forms part of the handler's implementation fingerprint.
        observations: SimpleQueue[tuple[str, float, float]] = SimpleQueue()

        def parallel_handler(payload, _context):
            started = time.monotonic()
            # The full 700-test gate can briefly deschedule either executor.
            # Keep the rendezvous bounded without making scheduler latency the
            # property under test; interval overlap remains the hard oracle.
            barrier.wait(5.0)
            time.sleep(0.05)
            finished = time.monotonic()
            observations.put((payload["execution_id"], started, finished))
            return {"run_id": payload["run_id"]}

        parallel_handler.__execution_kernel_revision__ = "runtime-host-parallel-v1"
        with tempfile.TemporaryDirectory() as temp:
            runtime = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("parallel", 1): parallel_handler},
                isolation_mode="thread",
                max_thread_workers=2,
            )
            commands = [
                make_command(
                    f"same-run-{index}",
                    runtime.registry_revision,
                    value=index,
                )
                for index in (1, 2)
            ]
            for command in commands:
                command = replace(
                    command,
                    handler_id="parallel",
                    timeout_seconds=10.0,
                    payload={
                        "execution_id": command.execution_id,
                        "run_id": "run-shared",
                    },
                )
                runtime.submit(command)
            host = RuntimeHost(
                runtime,
                RecordingBridge(),
                worker_count=2,
                sweep_interval=0.05,
                pump_interval=0.01,
            )
            try:
                host.start()
                wait_until(
                    lambda: all(
                        runtime.kernel.get(command.execution_id).state == "succeeded"
                        for command in commands
                    ),
                    timeout=10.0,
                )
                intervals = {}
                for _ in commands:
                    execution_id, started, finished = observations.get_nowait()
                    intervals[execution_id] = (started, finished)
                self.assertEqual(set(intervals), {command.execution_id for command in commands})
                first, second = (intervals[command.execution_id] for command in commands)
                self.assertLess(max(first[0], second[0]), min(first[1], second[1]))
            finally:
                self.assertTrue(host.stop(timeout=2.0))

    def test_stop_drains_workers_and_closes_runtime(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def blocking_handler(_payload, _context):
            entered.set()
            release.wait(2.0)
            return {"done": True}

        blocking_handler.__execution_kernel_revision__ = "runtime-host-stop-v1"
        with tempfile.TemporaryDirectory() as temp:
            runtime = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("blocking", 1): blocking_handler},
                isolation_mode="thread",
                max_thread_workers=1,
            )
            command = make_command("host-stop", runtime.registry_revision)
            command = replace(
                command,
                handler_id="blocking",
                timeout_seconds=5.0,
            )
            runtime.submit(command)
            host = RuntimeHost(
                runtime,
                RecordingBridge(),
                worker_count=1,
                sweep_interval=0.05,
                pump_interval=0.01,
            )
            try:
                host.start()
                self.assertTrue(entered.wait(1.0))
                self.assertTrue(host.stop(timeout=3.0))
                self.assertTrue(host.join(0.1))
                self.assertEqual(host.health().state, "stopped")
                self.assertIsNone(runtime.run_once())
            finally:
                release.set()
                runtime.close()


if __name__ == "__main__":
    unittest.main()
