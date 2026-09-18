"""Logical compatibility and physical growth across orchestration write paths."""

from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dispatcher_sdk.execution_kernel import SQLiteKernel
from dispatcher_sdk.orchestrator import Orchestrator, CommandConflict
from dispatcher_sdk.orchestrator.contracts import digest


class StateStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "orchestrator.db"
        self.kernel = SQLiteKernel(Path(self.tmp.name) / "kernel.db")
        self.addCleanup(self.kernel.close)
        self.sdk = Orchestrator(self.path, self.kernel)
        self.sdk.create_run("run", command_id="create")
        # High entropy fixture: a compression-only change cannot meet the budget.
        self.blob = "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(8192))

    def apply(self, i, state):
        return self.sdk.apply_operations("run", command_id=f"step-{i}", expected_revision=i,
                                         operations=[], application_state=state)

    def test_changing_sibling_deduplicates_across_history_and_events(self):
        first = None
        for i in range(80):
            state = {"blob": self.blob, "step": i}
            result = self.apply(i, state)
            first = result if first is None else first
        self.assertEqual(self.sdk.get_run("run")["application_state"], state)
        self.assertEqual(self.sdk.get_run_at("run", 1), first)
        self.assertEqual(self.sdk.get_command_receipt("run", "step-0"), first)
        replay = self.sdk.apply_operations("run", command_id="step-0", expected_revision=0,
            operations=[], application_state={"blob": self.blob, "step": 0})
        self.assertEqual(replay, first)
        events = self.sdk.read_events("run", limit=100)
        self.assertEqual(events[-1]["payload"]["application_state"], state)
        self.assertEqual(self.sdk.observe("run", subscription="reader")["events"], events)
        self.assertLess(self.path.stat().st_size, 4 * 1024 * 1024)
        with closing(sqlite3.connect(self.path)) as connection:
            payload_bytes = connection.execute(
                "SELECT COALESCE(SUM(length(CAST(encoded AS BLOB))),0) FROM sdk_content_objects"
            ).fetchone()[0]
            self.assertLess(payload_bytes, 2 * len(self.blob))
            request = {"kind": "apply_operations", "expected_revision": 0,
                       "operations": [], "subscription": None, "expected_cursor": None,
                       "advance_to": None, "has_application_state": True,
                       "application_state": {"blob": self.blob, "step": 0}}
            stored = connection.execute(
                "SELECT digest FROM sdk_commands WHERE command_id='step-0'").fetchone()[0]
            self.assertEqual(stored, digest(request))
        with self.assertRaises(CommandConflict):
            self.sdk.apply_operations("run", command_id="step-0", expected_revision=0,
                operations=[], application_state={"blob": self.blob, "step": 1})

    def test_failed_commit_does_not_publish_objects_or_history(self):
        with closing(sqlite3.connect(self.path)) as connection:
            before = connection.execute("SELECT COUNT(*) FROM sdk_content_objects").fetchone()[0]
        def fail(name):
            if name == "before_commit":
                raise RuntimeError("injected crash")
        self.sdk._failpoint = fail
        with self.assertRaisesRegex(RuntimeError, "injected crash"):
            self.apply(0, {"blob": self.blob})
        self.assertEqual(self.sdk.get_run("run")["revision"], 0)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sdk_content_objects").fetchone()[0], before)

    def test_corruption_rejects_reads_and_decisions(self):
        self.apply(0, {"blob": self.blob})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM sdk_content_objects")
        from dispatcher_sdk.content import ContentIntegrityError
        for read in (lambda: self.sdk.get_run("run"),
                     lambda: self.sdk.get_command_receipt("run", "step-0"),
                     lambda: self.sdk.read_events("run"),
                     lambda: self.apply(1, {"small": True})):
            with self.assertRaises(ContentIntegrityError):
                read()

    def test_recovery_reuses_content_and_remains_readable(self):
        self.apply(0, {"blob": self.blob, "step": 1})
        self.sdk.apply_operations("run", command_id="finish", expected_revision=1,
            operations=[{"kind": "finish", "state": "failed"}])
        record = self.sdk.reopen_run("run", command_id="reopen", expected_revision=2,
            actor="operator", authorization_source="test", reason="retry",
            target_deployment={"registry_revision": "deployment"},
            decision={"start_stage": "retry", "evidence": self.blob},
            application_state={"blob": self.blob, "step": 2})
        self.assertEqual(record["application_state"], {"blob": self.blob, "step": 2})
        self.assertEqual(self.sdk.get_recovery(record["recovery_id"])["decision"], record["decision"])
        self.assertEqual(self.sdk.get_run("run")["application_state"], record["application_state"])


if __name__ == "__main__":
    unittest.main()
