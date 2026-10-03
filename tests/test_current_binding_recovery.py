"""Current identity publication recovers without delaying real business entry."""
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from dispatcher_sdk.execution_kernel import HandlerExecutionError, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel.children import HandlerChildren, _RetryWindow, _retry
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ActivityRecorder, ObservationJournal, ObservationOptions


class CurrentBindingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sdk-current-binding-recovery-"))
        self.evidence = {"test": self.id(), "records": []}

    def tearDown(self):
        path = self.root / "evidence.json"
        path.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
        print("current_binding_recovery_evidence=" + str(path), flush=True)

    def wait_for(self, operation, *, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = operation()
            if value:
                return value
            time.sleep(.02)
        self.fail("declared recovery observation deadline expired")

    def test_failed_initial_binding_recovers_and_old_driver_cannot_replace_new_attempt(self):
        entered = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        binding_failed = threading.Event()
        outcomes, errors, threads = [], [], []
        older = None
        writer = None

        def handler(payload, context):
            index = context.lease.attempt - 1
            entered[index].set()
            if not release[index].wait(5):
                raise TimeoutError("business barrier was not released")
            if index == 0:
                raise HandlerExecutionError("real_retry", "first real attempt requests retry", retryable=True)
            return {"actual_attempt": context.lease.attempt}

        handler.__execution_kernel_revision__ = "binding-recovery-business-v1"
        runtime = Kernel.open_sqlite(self.root / "kernel.sqlite3", {"work": handler},
            isolation_mode="thread", observation_options=ObservationOptions(write_timeout=.05, flush_interval=.05))
        journal = runtime.observation_journal
        original_bind = journal.bind_current

        def witnessed_bind(identity):
            try:
                return original_bind(identity)
            except sqlite3.OperationalError as error:
                self.evidence["records"].append({"failed_bind_identity": identity.to_dict(),
                    "error": str(error), "sqlite_errorcode": error.sqlite_errorcode, "at": time.time()})
                binding_failed.set()
                raise

        journal.bind_current = witnessed_bind

        def drive():
            try:
                outcomes.append(runtime.run_once(execution_id="binding-proof"))
            except BaseException as error:
                errors.append(repr(error))

        try:
            runtime.submit(runtime.command("work", execution_id="binding-proof", idempotency_key="binding-proof",
                correlation_id="binding-recovery", timeout_seconds=10, payload={},
                retry_policy=RetryPolicy(max_attempts=2)))
            writer = sqlite3.connect(journal.path, timeout=1)
            writer.execute("BEGIN IMMEDIATE")
            first = threading.Thread(target=drive)
            threads.append(first)
            first.start()
            self.assertTrue(binding_failed.wait(5), "actual driver binding did not hit the held writer")
            self.assertTrue(entered[0].wait(5), "telemetry contention prevented business entry")
            self.assertIsNone(journal.inspect("binding-proof")["identity"])
            recorder = runtime._execution_recorders[("binding-proof", 1, 1)]
            old_identity = recorder.identity
            writer.rollback()
            writer.close()
            writer = None

            def recovered():
                report = journal.inspect("binding-proof")
                driver = any(item.get("source_scope") == "driver" for item in report["sources"])
                dispatched = any(item["phase"] == "worker_dispatch" for item in report["phases"])
                return report if report["current"] and driver and dispatched else None

            repaired = self.wait_for(recovered)
            self.assertEqual((1, 1), (repaired["identity"]["attempt"], repaired["identity"]["fence"]))
            self.evidence["records"].append({"repaired_binding": repaired})
            release[0].set()
            first.join(5)
            self.assertFalse(first.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("queued", outcomes[0].state)
            second = threading.Thread(target=drive)
            threads.append(second)
            second.start()
            self.assertTrue(entered[1].wait(5))
            newer = self.wait_for(lambda: (report if (report := journal.inspect("binding-proof"))["identity"]
                and report["identity"]["attempt"] == 2 else None))
            # Restart a collector for the genuine historical first attempt.
            older = ActivityRecorder(journal, old_identity, source_scope="driver",
                metric_coverage=("phase_events", "heartbeat"), start=True, bind_current=True)
            older.phase("late_old_driver")
            older.heartbeat()
            self.wait_for(lambda: older.snapshot()["persisted_at"])
            current = journal.inspect("binding-proof")
            self.assertEqual(newer["identity"], current["identity"])
            historical = journal.inspect("binding-proof", attempt=1, fence=1)
            self.assertFalse(historical["current"])
            self.assertTrue(any(item["phase"] == "late_old_driver" for item in historical["phases"]))
            self.evidence["records"].append({"new_current": current, "late_historical_driver": historical})
            release[1].set()
            second.join(5)
            self.assertFalse(second.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("succeeded", outcomes[1].state)
        finally:
            for event in release:
                event.set()
            if writer is not None:
                writer.rollback()
                writer.close()
            if older is not None:
                older.close()
            for thread in threads:
                thread.join(10)
            runtime.close()

    def test_direct_real_journal_child_capability_does_not_require_diagnostic_ledger(self):
        wall = time.time()
        with SQLiteKernel(self.root / "direct.sqlite3", now=lambda: wall) as kernel:
            journal = ObservationJournal(self.root / "direct-observations.sqlite3",
                kernel_path=kernel.db_path, source_id="direct-host")
            command = ExecutionCommandV2("direct-parent", "direct-parent", "direct-registry", "direct-proof",
                None, "work", 1, RetryPolicy(), 10, {})
            kernel.submit(command)
            lease = kernel.claim_and_start("direct-owner")
            budget = kernel.prepare_execution_budget(lease).enter_handler(10, origin_id="execution:direct-parent")
            kernel.confirm_handler_entry(lease, budget)
            children = HandlerChildren(kernel, command, lease, budget,
                {"capacity": 1, "max_depth": 1, "registry_revision": "direct-registry"}, journal=journal)
            child = ExecutionCommandV2("direct-child", "direct-child", "direct-registry", "direct-proof",
                "direct-parent", "work", 1, RetryPolicy(), 5, {})
            envelope = budget.derive(source="tool", origin_id="direct-call", timeout_seconds=5)
            window = _RetryWindow(envelope, kernel)
            row = _retry(window, lambda: children._enqueue(request_id="direct-call", child_id=child.execution_id,
                action="run", child_command=child, envelope=envelope, window=window), store=children.store)
            self.assertEqual("pending", row["state"])
            self.assertEqual(child.execution_id, row["child_execution_id"])
            self.assertFalse(Path(kernel.db_path + ".settlements.sqlite3").exists())
            self.evidence["records"].append({"direct_request": row, "diagnostic_ledger_created": False})


if __name__ == "__main__":
    unittest.main()
