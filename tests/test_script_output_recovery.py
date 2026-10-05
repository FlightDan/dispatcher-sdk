"""Real saved artifacts survive timeout-sidecar loss without business replay."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.contracts import (
    ExecutionCommandV2, ExecutionError, ExecutionLease, ExecutionResultV2, RetryPolicy,
)
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.execution_kernel.script_output import ScriptOutputRecovery
from tests._acceptance_evidence import retained_directory


class ScriptOutputRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-script-output-recovery-")
        self.kernel_path = self.root / "kernel.db"
        kernel = SQLiteKernel(self.kernel_path)
        kernel.close()
        self.journal = SettlementJournal(self.root / "settlement.db",
            source_id="original-store", kernel_path=self.kernel_path)
        self.key = {"execution_id": "original-script", "attempt": 2, "fence": 3}
        self.identity = {**self.key, "run_id": "original-run", "task_id": "original-task",
                         "generation": 4, "task_attempt": 1}
        self.output = self.root / "original-output"
        self.logs = self.output / "2-3"
        self.logs.mkdir(parents=True)
        (self.logs / "stdout.log").write_bytes(b"abcdefghijklmnopqrst")
        (self.logs / "stderr.log").write_bytes(b"raw stderr")
        self.seed_effect("original-effect", self.output, attempt=2, fence=3)
        lease = ExecutionLease("original-script", "original-lease", "original-owner", 3, 2,
                               9999999999, 100)
        result = ExecutionResultV2("original-result", "original-script", "timed_out", 2, 3,
            ["original-effect"], 100, 102, "original-correlation", None, None,
            ExecutionError("timeout", "original timeout", False, {}))
        self.original_result = result.to_dict()
        self.journal.record(lease, result, evidence={"script_output_recovery": {
            "identity": self.identity, "cleanup_confirmed": True}})
        self.owner = ScriptOutputRecovery(self.kernel_path, self.journal)
        self.addCleanup(lambda: self.owner.drain(time.monotonic() + 1))

    def seed_effect(self, effect_id, output, *, attempt, fence):
        # Actual schema and historical event identity, with no handler invocation
        # or fabricated native-cleanup proof. This is an artifact-owner fixture.
        with closing(sqlite3.connect(self.kernel_path)) as connection, connection:
            connection.execute("INSERT INTO kernel_effects(effect_id,execution_id,name,request_json,"
                "state,lease_id,attempt,fence,prepared_at,revision) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (effect_id, "original-script", "script.execute", json.dumps({"output_root": str(output),
                    "script": {"source": "not read by output recovery"}}), "prepared",
                 "original-lease", attempt, fence, 100, 1))
            connection.execute("INSERT INTO kernel_effect_events(event_id,effect_id,execution_id,revision,"
                "event_type,to_state,data_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (effect_id + "-event", effect_id, "original-script", 1, "prepared", "prepared",
                 json.dumps({"attempt": attempt, "fence": fence}), 100))

    def fact(self):
        note = self.journal.inspect_script_output(self.key)
        return None if note is None else note["evidence"]

    def test_settled_restart_recovers_only_exact_original_attempt(self):
        wrong = self.root / "other-attempt"
        (wrong / "1-1").mkdir(parents=True)
        (wrong / "1-1" / "stdout.log").write_bytes(b"wrong" * 100)
        self.seed_effect("other-effect", wrong, attempt=1, fence=1)
        original = self.journal.inspect("original-script")[0]
        self.journal.settle(original, "recorded", {**original["evidence"],
            "canonical_result": "original-result"})
        reopened = SettlementJournal(self.root / "settlement.db", source_id="original-store",
                                      kernel_path=self.kernel_path)
        owner = ScriptOutputRecovery(self.kernel_path, reopened)
        self.assertFalse(owner.recover(time.monotonic() + 1)["pending"])
        fact = self.fact()
        self.assertEqual(self.identity, fact["identity"])
        self.assertEqual("original-effect", fact["effect_id"])
        self.assertEqual(20, fact["streams"]["stdout"]["saved_bytes"])
        self.assertEqual(str(self.logs / "stdout.log"), fact["streams"]["stdout"]["path"])
        self.assertNotIn("first_at", fact["streams"]["stdout"])
        self.assertNotIn("last_at", fact["streams"]["stdout"])
        self.assertEqual([], reopened.pending_script_output())
        self.assertEqual(self.original_result, reopened.inspect("original-script")[0]["result"])

    def test_held_publication_retains_same_fact_and_worker(self):
        original_stat = Path.stat
        sampled = []

        def counted(path, *args, **kwargs):
            if path.name in {"stdout.log", "stderr.log"}:
                sampled.append(str(path))
            return original_stat(path, *args, **kwargs)

        with closing(sqlite3.connect(self.journal.path)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            with patch.object(Path, "stat", counted):
                report = self.owner.recover(time.monotonic() + .1)
                self.assertTrue(report["pending"])
                self.assertTrue(self.owner.pending(**self.key))
                worker = self.owner._worker
                frozen = json.loads(json.dumps(self.owner._fact))
                (self.logs / "stdout.log").write_bytes(b"changed after sampling")
                writer.rollback()
                self.assertFalse(self.owner.drain(time.monotonic() + 1))
            self.assertEqual(2, len(sampled))
            self.assertFalse(worker.is_alive())
            self.assertEqual(frozen, self.fact())
            self.assertEqual(20, self.fact()["streams"]["stdout"]["saved_bytes"])

    def test_blocked_stat_keeps_one_worker_and_exact_owner_until_release(self):
        entered, release = threading.Event(), threading.Event()
        original_stat = Path.stat
        calls = []

        def held(path, *args, **kwargs):
            if path.name == "stdout.log":
                calls.append(threading.get_ident())
                entered.set()
                release.wait()
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", held):
            try:
                deadline = time.monotonic() + .05
                self.assertTrue(self.owner.recover(deadline)["pending"])
                self.assertTrue(entered.is_set())
                worker = self.owner._worker
                self.assertTrue(self.owner.drain(time.monotonic() + .05))
                self.assertIs(worker, self.owner._worker)
                self.assertTrue(self.owner.pending("original-script", 2, 3))
                self.assertFalse(self.owner.pending("original-script", 1, 1))
                self.assertEqual(1, len(calls))
            finally:
                release.set()
            self.assertFalse(self.owner.drain(time.monotonic() + 1))
        self.assertFalse(self.owner.pending())
        self.assertEqual(20, self.fact()["streams"]["stdout"]["saved_bytes"])

    def test_nonregular_and_missing_files_are_explicit_unknown(self):
        (self.logs / "stdout.log").unlink()
        (self.logs / "stdout.log").mkdir()
        (self.logs / "stderr.log").unlink()
        self.assertFalse(self.owner.recover(time.monotonic() + 1)["pending"])
        for stream in self.fact()["streams"].values():
            self.assertIn("unknown_reason", stream)
            self.assertNotIn("saved_bytes", stream)
        self.assertLessEqual(len(json.dumps(self.fact()).encode()), 4096)

    def test_valid_long_path_publishes_bounded_unknown_instead_of_pending_forever(self):
        output = self.root
        for i in range(6):
            output = output / (str(i) + "x" * 130)
        (output / "2-3").mkdir(parents=True)
        with closing(sqlite3.connect(self.kernel_path)) as connection, connection:
            connection.execute("UPDATE kernel_effects SET request_json=? WHERE effect_id='original-effect'",
                               (json.dumps({"output_root": str(output)}),))
        self.assertFalse(self.owner.recover(time.monotonic() + 1)["pending"])
        fact = self.fact()
        self.assertEqual("original-effect", fact["effect_id"])
        self.assertIn("exceeds", fact["streams"]["stdout"]["error"])
        self.assertLessEqual(len(json.dumps(fact).encode()), 4096)

    def test_supported_not_applied_repreparation_keeps_original_artifact_association(self):
        # Real Kernel lifecycle; no script handler or external effect is invoked.
        # Cleanup marker below is fixture evidence for this fact-owner test, not
        # a native containment witness.
        clock = [100.]
        path = self.root / "reprepared-kernel.db"
        kernel = SQLiteKernel(path, now=lambda: clock[0], default_lease_seconds=5)
        self.addCleanup(kernel.close)
        command = ExecutionCommandV2("reprepared-script", "reprepared-key", "registry",
            "correlation", None, "script-handler", 1, RetryPolicy(max_attempts=1), 2, {})
        kernel.submit(command)
        first = kernel.start(kernel.claim("first-owner", registry_revision="registry"))
        output = self.root / "reprepared-output"
        request = {"output_root": str(output), "script": {"source": "never invoked"}}
        kernel.prepare_effect(first, effect_id="stable-script-effect", name="script.execute", request=request)
        claimed = kernel.claim_effect(first, "stable-script-effect")
        kernel.mark_effect_indeterminate("stable-script-effect", {"fixture": "unknown"}, first, claimed.claim_id)
        clock[0] = 106.
        self.assertEqual("recovery_required", kernel.reap()[0].state)
        uncertain = kernel.get_effect("stable-script-effect")
        kernel.resolve_effect("stable-script-effect", decision="not_applied", response=None,
                              expected_revision=uncertain.revision, recovery_id="explicit-fixture-recovery")
        second = kernel.start(kernel.claim("second-owner", registry_revision="registry"))
        current = kernel.prepare_effect(second, effect_id="stable-script-effect", name="script.execute", request=request)
        self.assertGreater(second.attempt, first.attempt)
        self.assertEqual((second.attempt, second.fence), (current.attempt, current.fence))
        events = kernel.effect_events("stable-script-effect")
        self.assertEqual("reprepared_after_not_applied", events[-1]["event_type"])
        for lease, contents in ((first, b"old original stdout"), (second, b"new attempt stdout is different")):
            directory = output / (str(lease.attempt) + "-" + str(lease.fence))
            directory.mkdir(parents=True)
            (directory / "stdout.log").write_bytes(contents)
            (directory / "stderr.log").write_bytes(b"")
        journal = SettlementJournal(self.root / "reprepared-settlement.db", source_id="reprepared-store", kernel_path=path)
        identity = {"execution_id": first.execution_id, "attempt": first.attempt, "fence": first.fence,
                    "run_id": None, "task_id": None, "generation": 0, "task_attempt": None}
        original_result = ExecutionResultV2("first-original-result", first.execution_id, "timed_out",
            first.attempt, first.fence, ["stable-script-effect"], 100, 102, "correlation", None, None,
            ExecutionError("timeout", "original first attempt", False, {}))
        receipt = journal.record(first, original_result, evidence={"script_output_recovery": {
            "identity": identity, "cleanup_confirmed": True}})
        journal.settle(receipt, "superseded", receipt["evidence"])
        owner = ScriptOutputRecovery(path, journal)
        self.addCleanup(lambda: owner.drain(time.monotonic() + 1))
        self.assertFalse(owner.recover(time.monotonic() + 1)["pending"])
        fact = journal.inspect_script_output(identity)["evidence"]
        self.assertEqual("stable-script-effect", fact["effect_id"])
        self.assertEqual(identity, fact["identity"])
        self.assertEqual(len(b"old original stdout"), fact["streams"]["stdout"]["saved_bytes"])
        self.assertEqual(str(output / (str(first.attempt) + "-" + str(first.fence)) / "stdout.log"),
                         fact["streams"]["stdout"]["path"])
        self.assertEqual(original_result.to_dict(), journal.inspect(first.execution_id)[0]["result"])
        self.assertEqual(current.to_dict(), kernel.get_effect("stable-script-effect").to_dict())


if __name__ == "__main__":
    unittest.main()
