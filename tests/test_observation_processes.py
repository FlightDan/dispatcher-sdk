"""Real handles and byte chunks, including silent and unterminated output."""

import multiprocessing
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.observability.activity import ActivityRecorder
from dispatcher_sdk.observability.contracts import ObservationIdentity, ObservationOptions
from dispatcher_sdk.observability.journal import ObservationJournal
from dispatcher_sdk.observability.processes import ProcessObserver
from dispatcher_sdk.observability.streams import decoded_tail, observed_byte_chunks, observe_bytes


def silent_child(gate):
    gate.wait(5)


class ProcessObservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.options = ObservationOptions(flush_interval=.05, process_freshness=.2)
        self.identity = ObservationIdentity("execution", 1, 1)
        self.journal = ObservationJournal(root / "observations.sqlite3", kernel_path=root / "kernel.sqlite3",
            source_id="test-source", options=self.options)
        self.journal.bind_current(self.identity)
        self.activity = ActivityRecorder(self.journal, self.identity, options=self.options)
        self.addCleanup(self.activity.close)
        self.observer = ProcessObserver(self.activity, poll_interval=.02)
        self.addCleanup(self.observer.close)

    def launch(self, source):
        process = subprocess.Popen([sys.executable, "-u", "-c", source], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)

        def cleanup():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            process.stdout.close()
            process.stderr.close()

        self.addCleanup(cleanup)
        return process

    def wait_state(self, observed, state, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            report = observed.snapshot()
            if report["state"] == state:
                return report
            time.sleep(.01)
        self.fail(f"process did not reach {state}: {observed.snapshot()}")

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires native Linux process identity and pipe select")
    def test_real_no_newline_chunk_observed_before_next_output_or_completion(self):
        process = self.launch("import os,time; os.write(1,b'first\\xff'); time.sleep(2); os.write(1,b'\\n')")
        observed = self.observer.observe_process(process, role="agent", process_id="writer")
        ready, _, _ = select.select([process.stdout], [], [], 1)
        self.assertTrue(ready)
        raw = os.read(process.stdout.fileno(), 4096)
        chunk = next(observed_byte_chunks(iter([raw]), self.activity))
        self.assertIs(raw, chunk)
        report = self.activity.snapshot()
        self.assertEqual(6, report["metrics"]["stdout_bytes"]["count"])
        self.assertNotIn(b"\n", chunk)
        self.assertEqual("first\ufffd", decoded_tail(chunk))
        self.assertIsNone(process.poll())
        self.assertEqual("alive", self.wait_state(observed, "alive")["state"])
        self.activity.flush()
        persisted = self.journal.inspect("execution")
        self.assertEqual(6, persisted["metrics"]["stdout_bytes"]["count"])

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires native Linux process birth identity")
    def test_real_silent_process_alive_then_exact_handle_exit(self):
        process = self.launch("import time; time.sleep(5)")
        observed = self.observer.observe_process(process, process_id="silent")
        self.activity.enable_stream("stdout")
        alive = self.wait_state(observed, "alive")
        self.assertIsNotNone(alive["birth_identity"])
        snapshot = self.activity.snapshot()
        self.assertEqual(0, snapshot["metrics"]["stdout_bytes"]["count"])
        self.assertTrue(snapshot["output"]["stdout"]["first_missing"])
        process.terminate()
        process.wait(timeout=2)
        exited = self.wait_state(observed, "exited")
        self.assertEqual(-signal.SIGTERM, exited["evidence"]["returncode"])
        self.assertEqual("signal", exited["evidence"]["exit_kind"])
        self.assertEqual("unknown", exited["evidence"]["cleanup"])

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires native Linux multiprocessing")
    def test_actual_multiprocessing_handle_observes_alive_and_exit(self):
        context = multiprocessing.get_context("spawn")
        gate = context.Event()
        process = context.Process(target=silent_child, args=(gate,))
        process.start()

        def cleanup():
            if process.is_alive():
                process.terminate()
            process.join(timeout=3)

        self.addCleanup(cleanup)
        observed = self.observer.observe_process(process, process_id="multiprocessing")
        self.wait_state(observed, "alive")
        gate.set()
        process.join(timeout=3)
        self.assertEqual(0, self.wait_state(observed, "exited")["evidence"]["returncode"])

    def test_pid_only_registration_remains_unknown_even_for_current_process(self):
        observed = self.observer.observe_process(os.getpid(), process_id="pid-only")
        deadline = time.monotonic() + 1
        while observed.snapshot()["observed_at"] is None and time.monotonic() < deadline:
            time.sleep(.01)
        report = observed.snapshot()
        self.assertEqual(os.getpid(), report["pid"])
        self.assertEqual("unknown", report["state"])
        self.assertEqual("process_handle_required", report["unknown_reason"])

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires native Linux process identity")
    def test_inaccessible_identity_does_not_invent_alive_from_pid(self):
        process = self.launch("import time; time.sleep(5)")
        with patch("dispatcher_sdk.observability.processes._birth", return_value=(None, None, "pid_namespace_differs")):
            observed = self.observer.observe_process(process, process_id="inaccessible")
            time.sleep(.06)
            self.assertEqual("unknown", observed.snapshot()["state"])
        process.kill()
        process.wait(timeout=2)
        # Exact handle completion remains valid when /proc identity is unavailable.
        self.wait_state(observed, "exited")

    def test_exit_137_retains_status_without_oom_or_signal_inference(self):
        process = self.launch("import sys; sys.exit(137)")
        observed = self.observer.observe_process(process, process_id="exit-137")
        process.wait(timeout=2)
        report = self.wait_state(observed, "exited")
        self.assertEqual(137, report["evidence"]["returncode"])
        self.assertEqual("status", report["evidence"]["exit_kind"])
        self.assertIsNone(report["evidence"]["signal"])
        self.assertEqual("unknown", report["evidence"]["oom"])

    def test_process_capacity_is_bounded_and_excess_is_diagnostic(self):
        observer = ProcessObserver(self.activity, start=False)
        self.addCleanup(observer.close)
        for index in range(32):
            observer.observe_process(os.getpid(), process_id=f"process-{index}")
        excess = observer.observe_process(os.getpid(), process_id="excess")
        self.assertEqual(32, observer.snapshot()["registered_processes"])
        self.assertEqual("unknown", excess.snapshot()["state"])
        self.assertEqual("process_observer_capacity_exhausted", excess.snapshot()["unknown_reason"])

    def test_storage_failure_and_bounded_close_do_not_change_live_process(self):
        process = self.launch("import time; time.sleep(5)")
        entered, release = threading.Event(), threading.Event()

        def blocked_registration(*args, **kwargs):
            entered.set()
            release.wait(3)
            raise OSError("journal unavailable")

        with patch.object(self.journal, "register_process", blocked_registration):
            observed = self.observer.observe_process(process, process_id="blocked-storage")
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            report = self.observer.close(timeout=.05)
            self.assertLess(time.monotonic() - started, .3)
            self.assertTrue(report["unfinished_collector"])
            self.assertIsNone(process.poll())
            self.assertEqual("unknown", observed.snapshot()["state"])
            release.set()
        self.observer.close(timeout=1)

    def test_stream_wrapper_does_not_prefetch_and_telemetry_error_does_not_drop_chunk(self):
        read = []

        def source():
            for chunk in (b"one", b"two"):
                read.append(chunk)
                yield chunk

        with patch.object(self.activity, "report_bytes", side_effect=OSError("telemetry unavailable")):
            wrapped = observed_byte_chunks(source(), self.activity)
            self.assertEqual([], read)
            self.assertEqual(b"one", next(wrapped))
            self.assertEqual([b"one"], read)
            self.assertEqual(b"two", next(wrapped))
            self.assertEqual("degraded", observe_bytes(self.activity, "stderr", b"three")["state"])
        self.assertEqual("\ufffd", decoded_tail(b"x\xff", limit_bytes=1))


if __name__ == "__main__":
    unittest.main()
