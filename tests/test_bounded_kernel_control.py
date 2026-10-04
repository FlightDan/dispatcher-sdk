"""Public Kernel control waits stay finite without revoking valid leases."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel, Kernel, ExecutionNotFoundError
from dispatcher_sdk.execution_kernel.children import HandlerChildren, ChildExecutionError


def child_control_handler(payload, context):
    return payload


def command():
    return ExecutionCommandV2(execution_id="bounded", idempotency_key="bounded",
        registry_revision="control-fixture", correlation_id="bounded", causation_id=None,
        handler_id="fixture", handler_contract_version=1, retry_policy=RetryPolicy(),
        timeout_seconds=10, payload={})


class BoundedKernelControlTests(unittest.TestCase):
    def test_slow_real_begin_cannot_admit_mutations_after_original_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteKernel(Path(directory) / "kernel.sqlite3", control_timeout_seconds=.05) as kernel:
                statements = []
                def trace(statement):
                    statements.append(statement)
                    if statement == "BEGIN IMMEDIATE":
                        time.sleep(.08)
                kernel._connection.set_trace_callback(trace)
                try:
                    with self.assertRaises(TimeoutError):
                        kernel.submit(command())
                finally:
                    kernel._connection.set_trace_callback(None)
                self.assertFalse(kernel._connection.in_transaction)
                self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                    for sql in statements), statements)
                with self.assertRaises(ExecutionNotFoundError):
                    kernel.get("bounded")
                self.assertEqual(kernel.submit(command()).state, "queued")

    def test_control_admission_keeps_authority_during_pragma_access_and_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteKernel(Path(directory) / "kernel.sqlite3", control_timeout_seconds=.05) as kernel:
                kernel.submit(command())
                with kernel._busy_timeout_access():
                    original = kernel._connection.execute("PRAGMA busy_timeout").fetchone()[0]
                    for sql in ("PRAGMA writable_schema=ON", "CREATE TABLE foreign_table(value)"):
                        with self.assertRaises(sqlite3.DatabaseError):
                            kernel._connection.execute(sql)
                with self.assertRaisesRegex(RuntimeError, "operation failed"):
                    with kernel._control_lock(.04):
                        with self.assertRaises(sqlite3.DatabaseError):
                            kernel._connection.execute("PRAGMA busy_timeout")
                        raise RuntimeError("operation failed")
                with kernel._busy_timeout_access():
                    self.assertEqual(kernel._connection.execute("PRAGMA busy_timeout").fetchone()[0], original)
                with self.assertRaises(sqlite3.DatabaseError):
                    kernel._connection.execute("PRAGMA writable_schema=ON")
                self.assertEqual(kernel.get("bounded").state, "queued")

    def test_real_writer_bounds_verify_and_submit_without_changing_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.sqlite3"
            with SQLiteKernel(path) as original:
                original.submit(command())
                lease = original.claim_and_start("worker")
                with SQLiteKernel(path, control_timeout_seconds=.05) as bounded:
                    with closing(sqlite3.connect(path)) as writer, writer:
                        writer.execute("BEGIN IMMEDIATE")
                        for operation in (lambda: bounded.verify(lease), lambda: bounded.submit(command())):
                            began = time.monotonic()
                            with self.assertRaises(sqlite3.OperationalError) as caught:
                                operation()
                            self.assertIn("locked", str(caught.exception))
                            self.assertLess(time.monotonic()-began, .25)
                        self.assertEqual(bounded.get("bounded").lease, lease)
                        writer.rollback()
                    self.assertEqual(bounded.verify(lease).lease, lease)
                    self.assertEqual(bounded.submit(command()).execution_id, "bounded")

    def test_configured_get_and_clock_bound_actual_connection_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteKernel(Path(directory) / "kernel.sqlite3", control_timeout_seconds=.05) as kernel:
                kernel.submit(command())
                held, release = threading.Event(), threading.Event()

                def holder():
                    with kernel._lock:
                        held.set()
                        release.wait(2)

                thread = threading.Thread(target=holder)
                thread.start()
                try:
                    self.assertTrue(held.wait(1))
                    for operation in (lambda: kernel.get("bounded"), kernel.current_time):
                        began = time.monotonic()
                        with self.assertRaises(TimeoutError):
                            operation()
                        self.assertLess(time.monotonic()-began, .25)
                finally:
                    release.set()
                    thread.join(2)
                self.assertEqual(kernel.get("bounded").state, "queued")

    def test_child_wait_preserves_busy_error_without_revoking_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel.sqlite3"
            with Kernel.open_sqlite(path, {"fixture": child_control_handler}, isolation_mode="thread") as runtime:
                parent = runtime.command("fixture", execution_id="parent", idempotency_key="parent",
                    correlation_id="parent", timeout_seconds=10, payload={})
                runtime.submit(parent)
                lease = runtime.kernel.claim_and_start("worker")
                envelope = runtime.kernel.prepare_execution_budget(lease).enter_handler(10,
                    origin_id="execution:parent")
                runtime.kernel.confirm_handler_entry(lease, envelope)
                for control_timeout in (None, .05, 2):
                    with SQLiteKernel(path, control_timeout_seconds=control_timeout) as bounded:
                        children = HandlerChildren(bounded, parent, lease, envelope, {"capacity": 1},
                            journal=runtime.observation_journal)
                        with closing(sqlite3.connect(path)) as writer, writer:
                            writer.execute("BEGIN IMMEDIATE")
                            began = time.monotonic()
                            with self.assertRaises(sqlite3.OperationalError) as caught:
                                children.wait_for("missing-child", request_id="wait", timeout_seconds=1)
                            self.assertNotIsInstance(caught.exception, ChildExecutionError)
                            self.assertGreater(time.monotonic()-began, .8)
                            self.assertLess(time.monotonic()-began, 1.25)
                            writer.rollback()
                        self.assertEqual(bounded.verify(lease).lease, lease)

    def test_invalid_control_bound_fails_before_creating_a_store(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent.sqlite3"
            for value in (0, -1, True, float("inf"), "forever"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    SQLiteKernel(path, control_timeout_seconds=value)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
