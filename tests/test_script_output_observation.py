from __future__ import annotations

from copy import deepcopy
import multiprocessing
import os
import json
from pathlib import Path
import sys
import sqlite3
import time
import unittest

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.scripts import ScriptSpec, script_handlers
from dispatcher_sdk.execution_kernel.settlement import merge_script_output


class SavedScriptOutputObservationTests(unittest.TestCase):
    def test_saved_floor_preserves_collector_counts_timestamps_and_other_metrics(self):
        fact = {"note_id": "saved", "identity": {"execution_id": "script", "attempt": 1, "fence": 1},
                "created_at": 50, "evidence": {"cleanup_confirmed": True,
                    "source": "script_artifact_after_native_cleanup", "sampled_at": 40,
                    "streams": {"stdout": {"saved_bytes": 20, "path": "/logs/stdout.log"},
                                "stderr": {"saved_bytes": 0, "path": "/logs/stderr.log"}}}}
        for collected in (0, 7, 20, 25):
            with self.subTest(collected=collected):
                report = {"complete": True, "metrics": {
                    "stdout_bytes": {"count": collected, "first_at": 10, "last_at": 11},
                    "model_requests": {"count": 3, "first_at": 8, "last_at": 9}},
                    "telemetry_flush": {"state": "unknown"}}
                original = deepcopy(report)
                merge_script_output(report, fact)
                merge_script_output(report, fact)
                self.assertEqual(max(collected, 20), report["metrics"]["stdout_bytes"]["count"])
                self.assertEqual(10, report["metrics"]["stdout_bytes"]["first_at"])
                self.assertEqual(11, report["metrics"]["stdout_bytes"]["last_at"])
                self.assertEqual(original["metrics"]["model_requests"], report["metrics"]["model_requests"])
                self.assertEqual(original["telemetry_flush"], report["telemetry_flush"])
                self.assertEqual(40, report["output"]["stdout"]["saved_at"])

    @unittest.skipUnless(os.name == "nt" or (os.name == "posix" and "fork" in multiprocessing.get_all_start_methods()),
                         "requires a real supported process backend")
    def test_real_native_timeout_recovers_saved_bytes_when_telemetry_writer_is_blocked(self):
        from tests._acceptance_evidence import retained_directory
        root = retained_directory("sdk-script-capture-loss-")
        try:
            source = ("import sys,time\n"
                      "sys.stdout.buffer.write(b'raw-without-newline\\xff')\n"
                      "sys.stdout.flush()\ntime.sleep(3)\n"
                      "open('escaped', 'w').write('escaped')\n")
            with Kernel.open_sqlite(root / "kernel.db", script_handlers(), isolation_mode="process") as runtime:
                command = ScriptSpec(source, (sys.executable, "-u"), root, root / "logs").command(
                    execution_id="lost-capture", idempotency_key="lost-capture",
                    registry_revision=runtime.registry_revision, correlation_id="lost-capture",
                    timeout_seconds=2)
                runtime.submit(command)
                writer = sqlite3.connect(runtime.observation_journal.path, isolation_level=None)
                writer.execute("BEGIN IMMEDIATE")
                try:
                    result = runtime.run_once()
                finally:
                    writer.rollback()
                    writer.close()
                (root / "result.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
                self.assertEqual("recovery_required", result.state)
                effect = runtime.kernel.get_effect(result.recovery_effect_id)
                original_state = effect.state
                path = Path(effect.request["output_root"]) / f"{result.attempt}-{result.fence}" / "stdout.log"
                self.assertEqual(b"raw-without-newline\xff", path.read_bytes())
                report = runtime.observe("lost-capture")
                self.assertEqual(20, report["metrics"]["stdout_bytes"]["count"])
                self.assertIsNone(report["metrics"]["stdout_bytes"]["first_at"])
                self.assertIsNone(report["metrics"]["stdout_bytes"]["last_at"])
                self.assertFalse(report["complete"])
                self.assertEqual(20, report["output"]["stdout"]["saved_bytes"])
                self.assertTrue(report["script_output_fact"]["cleanup_confirmed"])
                self.assertEqual(original_state, runtime.kernel.get_effect(result.recovery_effect_id).state)
                journal = runtime.observation_journal
                runtime.observation_journal = None
                try:
                    unavailable = runtime.observe("lost-capture")
                    self.assertEqual(20, unavailable["metrics"]["stdout_bytes"]["count"])
                    self.assertFalse(unavailable["complete"])
                    self.assertEqual(report["script_output_fact"], unavailable["script_output_fact"])
                finally:
                    runtime.observation_journal = journal
                time.sleep(1.2)
                self.assertFalse((root / "escaped").exists())
        finally:
            print("script_capture_loss_evidence=" + str(root), flush=True)

    def test_saved_fact_and_output_paths_obey_the_public_query_byte_limit(self):
        from dispatcher_sdk.observability import ObservationOptions
        from dispatcher_sdk.observability.journal import ObservationJournal
        report = {"execution_id": "script", "view": "persisted", "complete": True,
                  "metrics": {"stdout_bytes": {"count": 20, "first_at": None, "last_at": None}},
                  "output": {"stdout": {"saved_bytes": 20, "saved_path": "x" * 3800},
                             "stderr": {"saved_bytes": 0, "saved_path": "y" * 3800}},
                  "script_output_fact": {"note_id": "n" * 1000, "identity": {"run_id": "r" * 1000}}}
        from dispatcher_sdk._inspection import InspectionBudget
        bounded = ObservationJournal._bound_without_storage(report,
            options=ObservationOptions(query_bytes=4096), budget=InspectionBudget(1, None))
        self.assertLessEqual(len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode()), 4096)
        self.assertFalse(bounded["complete"])
        self.assertTrue(bounded["truncated"])

    def test_revoked_cleanup_receipt_survives_busy_storage_without_result_cas(self):
        """Exercise factual settlement ownership, without invoking a script."""
        from tests._acceptance_evidence import retained_directory
        root = retained_directory("sdk-script-revoked-fact-")
        with Kernel.open_sqlite(root / "kernel.db", script_handlers(), isolation_mode="process") as runtime:
            command = ScriptSpec("pass", (sys.executable,), root, root / "logs").command(
                execution_id="revoked", idempotency_key="revoked",
                registry_revision=runtime.registry_revision, correlation_id="revoked", timeout_seconds=2)
            runtime.submit(command)
            lease = runtime.kernel.claim_and_start("fixture")
            running = runtime.kernel.get("revoked")
            winner = runtime.kernel.cancel("revoked", expected_revision=running.revision)
            marker = {"identity": runtime._observation_identity(lease).to_dict(), "cleanup_confirmed": True}
            admission = runtime._pending_settlements.acquire()
            statements = []
            runtime.kernel._connection.set_trace_callback(statements.append)
            writer = sqlite3.connect(runtime._settlement_journal.path, isolation_level=None)
            writer.execute("BEGIN IMMEDIATE")
            try:
                returned = runtime._settle_outcome(running, lease,
                    {"kind": "authority_revoked", "script_output_recovery": marker}, admission)
                self.assertEqual(winner.to_dict(), returned.to_dict())
                self.assertTrue(runtime._pending_settlements.identities())
                self.assertTrue(runtime._execution_observation_pending("revoked", lease.attempt, lease.fence))
            finally:
                writer.rollback()
                writer.close()
                runtime._pending_settlements.finish(admission)
            try:
                runtime.recover_completions(timeout_seconds=1)
                self.assertEqual(winner.to_dict(), runtime.kernel.get("revoked").to_dict())
                self.assertFalse(runtime._pending_settlements.identities())
                receipt = runtime._settlement_journal.inspect("revoked")[0]
                self.assertEqual("recorded", receipt["state"])
                self.assertEqual("script_output_recovery", receipt["deferred"]["kind"])
                self.assertIsNone(receipt["result"])
                self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "BEGIN IMMEDIATE"))
                                     for sql in statements), statements)
            finally:
                runtime.kernel._connection.set_trace_callback(None)

    @unittest.skipUnless(os.name == "nt" or (os.name == "posix" and "fork" in multiprocessing.get_all_start_methods()),
                         "requires a real supported process backend")
    def test_valid_long_execution_identity_does_not_lose_the_native_business_outcome(self):
        from tests._acceptance_evidence import retained_directory
        root = retained_directory("sdk-script-long-identity-")
        execution_id = "original-" + "x" * 1500
        with Kernel.open_sqlite(root / "kernel.db", script_handlers(), isolation_mode="process") as runtime:
            command = ScriptSpec("print('finished')", (sys.executable, "-u"), root, root / "logs").command(
                execution_id=execution_id, idempotency_key="long-identity",
                registry_revision=runtime.registry_revision, correlation_id="long-identity", timeout_seconds=2)
            runtime.submit(command)
            result = runtime.run_once()
            self.assertEqual("succeeded", result.state)
            self.assertEqual(execution_id, result.execution_id)
            self.assertEqual(9, result.result.value["stdout"]["bytes"])
            receipt = runtime._settlement_journal.inspect(execution_id)[0]
            marker = receipt["evidence"]["script_output_recovery"]
            self.assertIsNone(marker["identity"])
            self.assertTrue(marker["cleanup_confirmed"])
            self.assertIn("ValueError", marker["identity_unknown_reason"])
            fact = runtime._settlement_journal.inspect_script_output({
                "execution_id": execution_id, "attempt": result.attempt, "fence": result.fence})
            self.assertTrue(fact["evidence"]["cleanup_confirmed"])
            self.assertNotIn("saved_bytes", fact["evidence"]["streams"]["stdout"])


if __name__ == "__main__":
    unittest.main()
