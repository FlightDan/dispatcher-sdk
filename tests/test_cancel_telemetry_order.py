from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import threading
import time
from tests._acceptance_evidence import retained_directory
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel
from tests.test_execution_kernel_v2_runtime import make_command, started_then_late_write_with_pid


@unittest.skipUnless(
    os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
    "requires native POSIX process isolation",
)
class CancellationTelemetryOrderTests(unittest.TestCase):
    def test_diagnostic_writer_cannot_delay_process_revocation(self):
        root = retained_directory("sdk-cancel-telemetry-order-")
        trace = []
        evidence = {"artifact": str(root), "command_timeout": 2.0,
                    "business_sleep": .3, "diagnostic_writer_hold": .4}

        def mark(event, **details):
            trace.append({"event": event, "wall": time.time(),
                          "monotonic": time.monotonic(), **details})

        stack = Kernel.open_sqlite(root / "kernel.sqlite3",
            {("lifecycle", 1): started_then_late_write_with_pid}, isolation_mode="process")
        driver = None
        writer_thread = None
        writer_errors = []
        try:
            started, pid_file, late = (root / name for name in
                                      ("started.txt", "handler.pid", "late.txt"))
            command = make_command("cancel-telemetry", stack.registry_revision,
                handler_id="lifecycle", timeout=2.0,
                payload={"started": str(started), "pid": str(pid_file),
                         "late": str(late), "sleep": .3})
            stack.submit(command)
            outcomes, errors = [], []

            def drive():
                try:
                    outcomes.append(stack.run_once())
                except BaseException as error:
                    errors.append({"type": type(error).__name__, "message": str(error)})
                finally:
                    mark("driver_finished")

            driver = threading.Thread(target=drive)
            driver.start()
            entry_deadline = time.monotonic() + command.timeout_seconds
            while not (started.exists() and pid_file.exists()) and time.monotonic() < entry_deadline:
                time.sleep(.005)
            self.assertTrue(started.exists(), str(root))
            self.assertTrue(pid_file.exists(), str(root))
            mark("entry_detected")
            handler_pid = int(pid_file.read_text(encoding="utf-8"))
            running = stack.kernel.get(command.execution_id)
            generation = (running.execution_id, running.attempt, running.fence)
            supervisor = stack._process_supervisors[generation]
            original_revoke = supervisor.revoke
            original_cancel = stack.kernel.cancel
            original_note = stack._diagnostic_note

            def revoke(reason):
                mark("supervisor_revoke_begin")
                try:
                    return original_revoke(reason)
                finally:
                    mark("supervisor_revoke_end")

            def cancel(*args, **kwargs):
                mark("kernel_cancel_begin")
                try:
                    return original_cancel(*args, **kwargs)
                finally:
                    mark("kernel_cancel_end")

            def note(identity, phase, details):
                mark("diagnostic_note_begin", phase=phase)
                try:
                    return original_note(identity, phase, details)
                finally:
                    mark("diagnostic_note_end", phase=phase)

            # Contend only the independent diagnostic store, never Kernel
            # execution authority. Its admission window exceeds the existing
            # handler's late write without changing either business timeout.
            writer = sqlite3.connect(stack._settlement_journal.path,
                                     isolation_level=None, check_same_thread=False)
            writer.execute("BEGIN IMMEDIATE")
            mark("diagnostic_writer_held")

            def release_writer():
                try:
                    time.sleep(.4)
                    writer.rollback()
                except BaseException as error:
                    writer_errors.append(str(error))
                finally:
                    writer.close()
                    mark("diagnostic_writer_released")

            writer_thread = threading.Thread(target=release_writer)
            writer_thread.start()
            with patch.object(supervisor, "revoke", revoke), \
                    patch.object(stack.kernel, "cancel", cancel), \
                    patch.object(stack, "_diagnostic_note", note):
                mark("cancel_called")
                cancelled = stack.cancel(command.execution_id,
                    expected_revision=running.revision, reason="operator cancellation")
                mark("cancel_returned")
                driver.join(1.0)
            writer_thread.join(1.0)
            self.assertFalse(driver.is_alive(), str(root))
            self.assertFalse(writer_thread.is_alive(), str(root))
            self.assertEqual(writer_errors, [])
            self.assertEqual(errors, [])
            self.assertEqual(cancelled.state, "cancelled")
            self.assertEqual(outcomes, [cancelled])
            with self.assertRaises(ProcessLookupError):
                os.kill(handler_pid, 0)
            time.sleep(.35)
            evidence.update(started_mtime=started.stat().st_mtime,
                late_exists=late.exists(), late_mtime=late.stat().st_mtime if late.exists() else None,
                cancelled_state=cancelled.state, outcome_states=[item.state for item in outcomes],
                errors=errors, process_reaped=True)
            self.assertFalse(late.exists(), str(root))

            requested_note = next(item for item in trace if item["event"] == "diagnostic_note_begin"
                                  and item["phase"] == "cancellation_requested")
            revoked = next(item for item in trace if item["event"] == "supervisor_revoke_end")
            self.assertLess(revoked["monotonic"], requested_note["monotonic"])
            report = stack.observe(command.execution_id)
            phases = {item["phase"]: item for item in report["phases"]}
            requested = phases["cancellation_requested"]
            authority = phases["cancellation_authority_revoked"]
            cleanup = phases["process_cleanup"]
            cancellation_cleanup = phases["cancellation_process_cleanup"]
            evidence["cancellation_phases"] = [requested, authority, cleanup, cancellation_cleanup]
            self.assertLess(requested["captured_at"], authority["captured_at"])
            self.assertLess(authority["captured_at"], cleanup["captured_at"])
            self.assertLess(cleanup["captured_at"], requested["persisted_at"])
            self.assertGreaterEqual(requested["persisted_at"], revoked["wall"])
            self.assertGreaterEqual(authority["persisted_at"], revoked["wall"])
        finally:
            try:
                if writer_thread is not None:
                    writer_thread.join(1.0)
                stack.close()
                if driver is not None:
                    driver.join(1.0)
            finally:
                evidence["trace"] = trace
                (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print("cancel_telemetry_order_evidence=" + str(root / "evidence.json"))


if __name__ == "__main__":
    unittest.main()
