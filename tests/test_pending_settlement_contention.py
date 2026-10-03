"""Real results survive simultaneous receipt and control admission pressure."""
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

import dispatcher_sdk
from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.pending_settlements import PendingSettlements
from tests.test_runtime_settlement import settlement_success, settlement_failure


class PendingSettlementContentionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sdk-double-settlement-contention-"))
        self.facts = {"sdk_import": dispatcher_sdk.__file__, "cases": []}
        self.addCleanup(lambda: (self.root / "evidence.json").write_text(json.dumps(self.facts, indent=2)))
        print("pending_settlement_evidence=" + str(self.root / "evidence.json"), flush=True)

    def blocked_result(self, name, *, failure=False):
        runtime = Kernel.open_sqlite(self.root / (name + ".sqlite3"),
            {"work": settlement_failure if failure else settlement_success}, isolation_mode="thread")
        self.addCleanup(runtime.close)
        runtime._pending_settlements = PendingSettlements(capacity=1)
        calls = self.root / (name + "-calls")
        runtime.submit(runtime.command("work", execution_id=name, idempotency_key=name,
            correlation_id=name, timeout_seconds=5, payload={"call_log": str(calls), "value": 17}))
        runtime.submit(runtime.command("work", execution_id=name + "-next", idempotency_key=name + "-next",
            correlation_id=name, timeout_seconds=5, payload={"call_log": str(calls), "value": 18}))
        ready, admitted = threading.Event(), threading.Event()
        original_result, returned, errors = [], [], []
        construct = runtime._outcome_result

        def capture(*args):
            result = construct(*args)
            original_result.append(result.to_dict())
            ready.set()
            if not admitted.wait(3):
                raise AssertionError("test did not acquire its writers")
            return result

        runtime._outcome_result = capture
        # Exclude maintenance while both independently owned writers are held.
        owned = {"maintenance": False, "lifecycle": False}

        def release_control():
            if owned["lifecycle"]:
                runtime._lifecycle_lock.release()
                owned["lifecycle"] = False
            if owned["maintenance"]:
                runtime._settlement_lock.release()
                owned["maintenance"] = False

        self.addCleanup(release_control)
        runtime._settlement_lock.acquire()
        owned["maintenance"] = True

        def drive():
            try:
                returned.append(runtime.run_once(execution_id=name))
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=drive)
        self.addCleanup(lambda: driver.join(2))
        self.addCleanup(admitted.set)
        driver.start()
        self.assertTrue(ready.wait(3))
        writer = sqlite3.connect(runtime._settlement_journal.path)
        self.addCleanup(writer.close)
        writer.execute("BEGIN IMMEDIATE")
        runtime._lifecycle_lock.acquire()
        owned["lifecycle"] = True
        admitted.set()
        driver.join(2)
        self.assertFalse(driver.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(returned[0].state, "running")
        self.assertIsNone(returned[0].result)
        self.assertEqual(runtime._pending_settlements.identities(), ({"execution_id": name,
            "attempt": returned[0].attempt, "fence": returned[0].fence},))
        self.assertEqual(runtime._settlement_journal.inspect(name, timeout_seconds=.2), [])
        observed = runtime.observe(name)
        self.assertFalse(observed["complete"])
        self.assertTrue(observed["local_settlement_obligations"])
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assertIsNone(runtime.run_once(execution_id=name + "-next"))
        self.assertEqual(runtime.kernel.get(name + "-next").state, "queued")
        self.facts["cases"].append({"execution_id": name, "original": original_result[0],
            "local_unpersisted": runtime._pending_settlements.identities(),
            "receipt_error": runtime._settlement_error, "successor_state": "queued"})
        return runtime, writer, calls, original_result[0], release_control

    def test_original_success_and_failure_are_persisted_then_recovered(self):
        for failure in (False, True):
            name = "failure" if failure else "success"
            runtime, writer, calls, original, release_control = self.blocked_result(name, failure=failure)
            try:
                writer.rollback()
                release_control()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    runtime.recover_completions(timeout_seconds=.5)
                    current = runtime.kernel.get(name)
                    if current.result is not None:
                        break
                self.assertEqual(current.result.to_dict(), original)
                self.assertEqual(runtime._pending_settlements.identities(), ())
                self.assertEqual(runtime._settlement_journal.inspect(name)[0]["result"], original)
                self.assertEqual(len(calls.read_text().splitlines()), 1)
                self.assertIsNotNone(runtime.run_once(execution_id=name + "-next"))
                self.assertEqual(len(calls.read_text().splitlines()), 2)
            finally:
                writer.close()
                runtime.close()

    def test_close_reports_unpersisted_facts_and_later_receipt_survives_restart(self):
        runtime, writer, calls, original, release_control = self.blocked_result("close")
        release_control()
        try:
            with self.assertRaisesRegex(RuntimeError, "not yet durably persisted"):
                runtime.close()
            self.assertTrue(runtime._pending_settlements.identities())
        finally:
            writer.rollback()
            writer.close()
        # Retrying close transfers the receipt without reopening business on
        # this Runtime. A fresh Runtime owns normal fenced restoration.
        runtime.close()
        runtime.close()
        self.assertEqual(runtime._pending_settlements.identities(), ())
        with Kernel.open_sqlite(self.root / "close.sqlite3", {"work": settlement_success},
                               isolation_mode="thread") as reopened:
            reopened.recover_completions(timeout_seconds=.5)
            self.assertEqual(reopened.kernel.get("close").result.to_dict(), original)
            self.assertEqual(len(calls.read_text().splitlines()), 1)
