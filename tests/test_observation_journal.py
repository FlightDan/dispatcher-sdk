"""Real SQLite pressure and recorder semantics, without business Run execution."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.observability import (
    ActivityRecorder, ObservationError, ObservationIdentity, ObservationJournal,
    ObservationOptions, StallPolicy,
)


class _Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class ObservationJournalTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        self.clock = _Clock()
        self.options = ObservationOptions(tail_bytes=16, write_timeout=.03)
        self.journal = self.open_journal()
        self.identity = ObservationIdentity("execution", 1, 1, run_id="run", task_id="task", task_attempt=0)
        self.journal.bind_current(self.identity)

    def open_journal(self, **kwargs):
        return ObservationJournal(self.root / "observation.sqlite3", kernel_path=self.root / "kernel.sqlite3",
                                  source_id="host-store-id", options=kwargs.pop("options", self.options),
                                  clock=self.clock, **kwargs)

    def recorder(self, **kwargs):
        return ActivityRecorder(self.journal, self.identity, clock=self.clock, monotonic=self.clock, **kwargs)

    def test_raw_bytes_without_newline_have_immediate_and_persisted_views(self):
        recorder = self.recorder()
        recorder.report_bytes("stdout", b"one")
        local = recorder.snapshot()
        self.assertEqual(local["metrics"]["stdout_bytes"]["count"], 3)
        self.assertEqual(local["tails"]["stdout"], b"one")
        self.assertIsNone(local["persisted_at"])
        self.assertEqual(recorder.flush()["state"], "persisted")
        report = self.journal.inspect("execution")
        self.assertEqual(report["metrics"]["stdout_bytes"]["first_at"], 100)
        self.assertEqual(report["tails"]["stdout"], "one")
        self.assertEqual(report["view"], "persisted")
        self.assertNotIn("stderr_bytes", report["metrics"])

    def test_oversized_event_metadata_is_bounded_and_cursor_advances(self):
        self.journal.write_batch(self.identity, source_id="source", sequence=1,
            metrics={}, tails={}, captured_at=100, gaps=0,
            events=({"kind": "x" * 10000, "captured_at": 100, "details": {}},))
        reader = self.open_journal(writer=False, options=ObservationOptions(query_bytes=4096))
        page = reader.events("execution")
        self.assertLessEqual(len(json.dumps(page).encode()), 4096)
        self.assertTrue(page["truncated"])
        self.assertFalse(page["complete"])
        self.assertGreater(page["cursor"], 0)
        self.assertEqual(page["events"][0]["execution_id"], "execution")
        self.assertEqual(reader.events("execution", after=page["cursor"])["events"], [])

    def test_opening_existing_journal_does_not_request_writer_lock(self):
        with closing(sqlite3.connect(self.journal.path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            reopened = self.open_journal()
            self.assertEqual(reopened.path, self.journal.path)
            connection.rollback()

    def test_metrics_have_independent_clocks_and_logs_do_not_confirm_progress(self):
        confirmed = {}
        def authority(key, *, details, timeout):
            advanced = key not in confirmed
            if advanced:
                confirmed[key] = len(confirmed) + 1
            return {"state": "confirmed", "revision": confirmed[key], "advanced": advanced}
        recorder = self.recorder(progress_confirm=authority)
        recorder.report_bytes("stdout", b"log")
        self.clock.now = 102
        recorder.heartbeat()
        recorder.model("request")
        self.clock.now = 104
        recorder.tool("response")
        self.assertEqual(recorder.snapshot()["no_progress_seconds"], 4)
        self.assertEqual(recorder.progress("milestone")["state"], "confirmed")
        self.clock.now = 108
        self.assertFalse(recorder.progress("milestone")["advanced"])
        snapshot = recorder.snapshot()
        self.assertEqual(snapshot["no_progress_seconds"], 4)
        self.assertEqual(snapshot["metrics"]["progress"]["count"], 1)
        self.assertEqual(snapshot["metrics"]["stdout_bytes"]["last_at"], 100)
        self.assertEqual(snapshot["metrics"]["tool_responses"]["last_at"], 104)

    def test_unconfirmed_progress_does_not_reset_timer(self):
        recorder = self.recorder(progress_confirm=lambda *args, **kwargs: {"state": "pending"})
        self.clock.now = 120
        self.assertEqual(recorder.progress("milestone")["state"], "pending")
        self.assertNotIn("progress", recorder.snapshot()["metrics"])
        self.assertEqual(recorder.snapshot()["no_progress_seconds"], 20)

    def test_silent_successful_collection_is_not_mistaken_for_collector_loss(self):
        recorder = self.recorder()
        recorder.enable_stream("stdout")
        recorder.phase("handler_entered")
        recorder.flush()
        self.clock.now = 120
        recorder.flush()
        report = self.journal.inspect("execution")
        self.assertTrue(report["complete"])
        self.assertEqual(report["captured_at"], 120)
        self.assertEqual(report["metrics"]["phase_events"]["last_at"], 100)
        self.assertTrue(report["output"]["stdout"]["first_missing"])
        self.assertEqual(recorder.snapshot()["output"]["stdout"]["wait_seconds"], 20)

    def test_capture_faults_degrade_without_throwing_or_breaking_subsequent_bytes(self):
        recorder = self.recorder()
        self.assertEqual(recorder.phase("phase", details={"oversized": "x" * 1000000})["state"], "degraded")
        self.assertEqual(recorder.report_bytes("stdout", b"after")["state"], "captured")
        self.assertEqual(recorder.snapshot()["metrics"]["stdout_bytes"]["count"], 5)
        self.assertFalse(recorder.snapshot()["complete"])

    def test_cumulative_batch_replay_and_old_sequences_do_not_double_count(self):
        metrics = {"stdout_bytes": {"count": 3, "first_at": 100, "last_at": 100}}
        self.assertTrue(self.journal.write_batch(self.identity, source_id="worker", sequence=2, metrics=metrics, captured_at=100))
        self.assertFalse(self.journal.write_batch(self.identity, source_id="worker", sequence=2, metrics=metrics, captured_at=100))
        self.assertFalse(self.journal.write_batch(self.identity, source_id="worker", sequence=1, metrics=metrics, captured_at=100))
        metrics["stdout_bytes"]["count"] = 7
        self.journal.write_batch(self.identity, source_id="worker", sequence=3, metrics=metrics, captured_at=102)
        self.assertEqual(self.journal.inspect("execution")["metrics"]["stdout_bytes"]["count"], 7)
        metrics["stdout_bytes"]["count"] = 1
        with self.assertRaises(ObservationError):
            self.journal.write_batch(self.identity, source_id="worker", sequence=4, metrics=metrics, captured_at=103)

    def test_late_old_attempt_is_history_without_changing_current(self):
        old = self.recorder(source_id="old")
        old.report_bytes("stdout", b"old")
        old.flush()
        current = ObservationIdentity("execution", 2, 2, run_id="run", task_id="task", task_attempt=0)
        self.journal.bind_current(current)
        fresh = ActivityRecorder(self.journal, current, source_id="fresh", clock=self.clock)
        fresh.report_bytes("stdout", b"new")
        fresh.flush()
        self.clock.now = 150
        old.report_bytes("stdout", b"late")
        old.flush()
        self.assertFalse(self.journal.bind_current(self.identity))
        report = self.journal.inspect("execution")
        self.assertEqual(report["identity"]["attempt"], 2)
        self.assertEqual(report["tails"]["stdout"], "new")
        self.assertEqual(report["captured_at"], 100)
        history = self.journal.inspect("execution", attempt=1, fence=1)
        self.assertFalse(history["current"])
        self.assertEqual(history["metrics"]["stdout_bytes"]["count"], 7)

    def test_readonly_missing_file_never_initializes_and_read_queries_do_not_write(self):
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            ObservationJournal.open_readonly(missing, kernel_path=self.root / "kernel.sqlite3", source_id="host-store-id")
        self.assertFalse(missing.exists())
        recorder = self.recorder()
        recorder.report_bytes("stdout", b"bytes")
        recorder.flush()
        with closing(sqlite3.connect(self.journal.path)) as connection:
            before = tuple(connection.iterdump())
        reader = self.open_journal(writer=False)
        reader.inspect("execution")
        reader.events("execution")
        with self.assertRaises(ObservationError):
            reader.bind_current(self.identity)
        with closing(sqlite3.connect(self.journal.path)) as connection:
            self.assertEqual(tuple(connection.iterdump()), before)

    def test_incompatible_binding_and_schema_are_not_repaired(self):
        with self.assertRaises(ObservationError):
            ObservationJournal(self.journal.path, kernel_path=self.root / "kernel.sqlite3", source_id="different")
        with closing(sqlite3.connect(self.journal.path)) as connection:
            connection.execute("DROP INDEX obs_events_execution")
            connection.commit()
        with self.assertRaises(ObservationError):
            self.open_journal()

    def test_tails_queue_events_and_queries_are_bounded(self):
        options = ObservationOptions(tail_bytes=16, queue_items=3, queue_bytes=1024,
                                     batch_summaries=2, page_events=2, query_bytes=4096)
        recorder = ActivityRecorder(self.journal, self.identity, options=options, clock=self.clock)
        recorder.report_bytes("stdout", b"x" * 10000)
        for number in range(100):
            recorder.phase(f"phase-{number}")
        snapshot = recorder.snapshot()
        self.assertEqual(len(snapshot["tails"]["stdout"]), 16)
        self.assertEqual(snapshot["metrics"]["stdout_bytes"]["count"], 10000)
        self.assertLessEqual(snapshot["queued_items"], 3)
        self.assertLessEqual(snapshot["queued_bytes"], 1024)
        self.assertGreater(snapshot["dropped_events"], 0)
        recorder.flush()
        recorder.flush()
        reader = self.open_journal(writer=False, options=options)
        page = reader.events("execution", limit=999)
        self.assertLessEqual(len(page["events"]), 2)
        self.assertTrue(page["has_more"])
        next_page = reader.events("execution", after=page["cursor"])
        self.assertGreater(next_page["cursor"], page["cursor"])
        self.assertFalse(reader.inspect("execution")["complete"])

    def test_real_storage_lock_does_not_block_capture_and_flush_is_bounded(self):
        recorder = self.recorder()
        with closing(sqlite3.connect(self.journal.path)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            recorder.report_bytes("stdout", b"before")
            result = recorder.flush()
            self.assertEqual(result["state"], "degraded")
            self.assertLess(time.monotonic() - started, .5)
            recorder.report_bytes("stdout", b"during")
            self.assertEqual(recorder.snapshot()["metrics"]["stdout_bytes"]["count"], 12)
            blocker.rollback()
        self.assertEqual(recorder.flush()["state"], "persisted")
        self.assertEqual(self.journal.inspect("execution")["metrics"]["stdout_bytes"]["count"], 12)

    def test_process_freshness_and_invisibility_preserve_historical_observation(self):
        self.journal.register_process(self.identity, "worker", role="handler", pid=123, birth_identity="birth", namespace="launch")
        self.journal.observe_process(self.identity, "worker", "alive", evidence={"method": "handle"})
        self.assertEqual(self.journal.inspect("execution")["processes"][0]["state"], "alive")
        self.clock.now = 110
        process = self.journal.inspect("execution")["processes"][0]
        self.assertEqual(process["state"], "unknown")
        self.assertEqual(process["last_observed_state"], "alive")
        self.journal.observe_process(self.identity, "worker", "unknown", unknown_reason="namespace_invisible")
        process = self.journal.inspect("execution")["processes"][0]
        self.assertEqual(process["unknown_reason"], "namespace_invisible")

    def test_phase_and_wait_observations_do_not_imply_business_control(self):
        self.journal.phase(self.identity, "handler_entered")
        self.journal.record_wait(self.identity, "wait", details={"kind": "external_service", "reason": "response"})
        self.clock.now = 105
        self.journal.end_wait(self.identity, "wait", state="failed")
        report = self.journal.inspect("execution")
        self.assertEqual(report["phases"][0]["phase"], "handler_entered")
        self.assertEqual(report["waits"][0]["state"], "failed")
        self.assertEqual(report["waits"][0]["ended_at"], 105)

    def test_invalid_unbounded_options_and_policies_rejected(self):
        for options in ({"flush_interval": float("inf")}, {"queue_items": 0}, {"write_timeout": -1}):
            with self.assertRaises(ValueError):
                ObservationOptions(**options)
        with self.assertRaises(ValueError):
            StallPolicy("policy", metrics=())

    def test_explicit_collector_scope_replaces_crashed_incarnation_and_preserves_history(self):
        old = self.recorder(source_id="old-handler", source_scope="handler")
        old.enable_stream("stdout")
        old.report_bytes("stdout", b"old")
        old.phase("handler_entered")
        old.flush()
        self.clock.now = 110
        self.assertFalse(self.journal.inspect("execution")["complete"])
        fresh = self.recorder(source_id="new-handler", source_scope="handler")
        fresh.enable_stream("stdout")
        fresh.flush()
        report = self.journal.inspect("execution")
        self.assertTrue(report["complete"])
        self.assertEqual([source["source_id"] for source in report["sources"]], ["new-handler"])
        self.assertEqual(report["retired_sources"][0]["source_id"], "old-handler")
        self.assertEqual(report["metrics"]["stdout_bytes"]["count"], 3)
        self.assertEqual(report["metrics"]["stdout_bytes"]["first_at"], 100)
        self.assertIn("collector_replaced", [event["kind"] for event in self.journal.events("execution")["events"]])
        old.report_bytes("stdout", b"late")
        old.flush()
        report = self.journal.inspect("execution")
        self.assertEqual(report["metrics"]["stdout_bytes"]["count"], 3)
        self.assertEqual(report["sources"][0]["source_id"], "new-handler")

    def test_independent_scopes_and_insufficient_coverage_cannot_retire_unknown_collector(self):
        handler = self.recorder(source_id="old-handler", source_scope="handler")
        handler.enable_stream("stdout")
        handler.flush()
        self.clock.now = 110
        independent = self.recorder(source_id="independent")
        independent.flush()
        driver = self.recorder(source_id="driver", source_scope="driver")
        driver.flush()
        partial = self.recorder(source_id="partial", source_scope="handler", metric_coverage=("heartbeat",))
        partial.heartbeat()
        partial.flush()
        report = self.journal.inspect("execution")
        self.assertIn("old-handler", [source["source_id"] for source in report["sources"]])
        self.assertEqual(next(source for source in report["sources"] if source["source_id"] == "old-handler")["continuity"], "unknown")
        self.assertFalse(report["complete"])
        self.assertEqual(report["retired_sources"], [])

    def test_replacement_does_not_claim_uninstalled_old_metric_is_currently_known(self):
        old = self.recorder(source_id="old-handler", source_scope="handler")
        old.enable_stream("stdout")
        old.flush()
        self.clock.now = 110
        fresh = self.recorder(source_id="new-handler", source_scope="handler")
        fresh.flush()
        report = self.journal.inspect("execution")
        self.assertNotIn("stdout_bytes", report["metrics"])
        self.assertFalse(report["output"]["stdout"]["known"])

    def test_scope_registration_recovers_after_temporary_storage_lock(self):
        old = self.recorder(source_id="old-handler", source_scope="handler")
        old.enable_stream("stdout")
        old.flush()
        with closing(sqlite3.connect(self.journal.path)) as blocked:
            blocked.execute("BEGIN IMMEDIATE")
            fresh = self.recorder(source_id="fresh-handler", source_scope="handler")
            self.assertIsNone(fresh.snapshot()["collector_incarnation"])
            self.assertEqual(fresh.report_bytes("stdout", b"fresh")["state"], "captured")
            blocked.rollback()
        self.assertEqual(fresh.flush()["state"], "persisted")
        report = self.journal.inspect("execution")
        self.assertEqual([row["source_id"] for row in report["sources"]], ["fresh-handler"])
        self.assertEqual(report["metrics"]["stdout_bytes"]["count"], 5)

    def test_replayed_receipt_arriving_before_first_advance_still_updates_progress_clock_once(self):
        acknowledged, release = threading.Event(), threading.Event()
        first = [True]
        def confirm(key, *, details, timeout):
            if first[0]:
                first[0] = False
                acknowledged.set()
                release.wait(1)
                return {"state": "confirmed", "revision": 1, "advanced": True}
            return {"state": "confirmed", "revision": 1, "advanced": False}
        recorder = self.recorder(progress_confirm=confirm)
        thread = threading.Thread(target=lambda: recorder.progress("milestone"))
        thread.start()
        self.assertTrue(acknowledged.wait(1))
        self.assertFalse(recorder.progress("milestone")["advanced"])
        self.clock.now = 120
        release.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(recorder.snapshot()["metrics"]["progress"]["count"], 1)
        self.assertEqual(recorder.snapshot()["no_progress_seconds"], 0)
        self.clock.now = 125
        recorder.progress("milestone")
        self.assertEqual(recorder.snapshot()["metrics"]["progress"]["count"], 1)
        self.assertEqual(recorder.snapshot()["no_progress_seconds"], 5)

    def test_metric_name_limits_and_large_valid_aggregation_respect_read_budget(self):
        with self.assertRaises(ValueError):
            self.journal.write_batch(self.identity, source_id="invalid", sequence=1,
                metrics={"x" * 100000: {"count": 0, "first_at": None, "last_at": None}}, captured_at=100)
        for source in range(64):
            metrics = {f"metric_{source}_{number}_" + "x" * 100: {"count": 0, "first_at": None, "last_at": None}
                       for number in range(32)}
            self.journal.write_batch(self.identity, source_id=f"source-{source:03}", sequence=1,
                                     metrics=metrics, captured_at=100)
        started = time.monotonic()
        report = self.journal.inspect("execution", timeout=.5)
        self.assertLess(time.monotonic() - started, .6)
        self.assertFalse(report["complete"])
        self.assertTrue(report["truncated"])
        import json
        self.assertLessEqual(len(json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode()), self.options.query_bytes)

    def test_expired_query_returns_bounded_partial_and_keeps_event_cursor(self):
        self.journal.phase(self.identity, "handler_entered")
        report = self.journal.inspect("execution", timeout=0)
        self.assertTrue(report["timed_out"])
        self.assertFalse(report["complete"])
        page = self.journal.events("execution", after=0, timeout=0)
        self.assertTrue(page["timed_out"])
        self.assertEqual(page["cursor"], 0)
        self.assertEqual(page["events"], [])

    def test_report_bounding_honors_caller_inspection_budget(self):
        from dispatcher_sdk._inspection import InspectionBudget
        self.journal.phase(self.identity, "handler_entered")
        report = self.journal.inspect("execution")
        report["runtime_metadata"] = {"enabled": True}
        report.update(diagnostics={"evidence": "d" * 1900},
            settlement_obligations=[{"evidence": "s" * 1900}],
            result={"details": "r" * 1900})
        from dataclasses import replace
        self.journal.options = replace(self.options, query_bytes=4096)
        budget = InspectionBudget(0, None)
        started = time.monotonic()
        bounded = self.journal._bound_report(report, budget)
        self.assertLess(time.monotonic() - started, .05)
        self.assertTrue(bounded["timed_out"])
        self.assertEqual(bounded["phases"], [])
        import json
        self.assertLessEqual(len(json.dumps(bounded).encode()), 4096)

    def test_close_retries_exact_final_batch_after_real_lock_release(self):
        recorder = self.recorder()
        recorder.report_bytes("stdout", b"final bytes without newline")
        locked, release, failed = threading.Event(), threading.Event(), threading.Event()
        def hold_write_lock():
            with closing(sqlite3.connect(self.journal.path)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                locked.set()
                release.wait(2)
                connection.rollback()
        locker = threading.Thread(target=hold_write_lock)
        locker.start()
        self.assertTrue(locked.wait(1))
        write_batch = self.journal.write_batch
        attempted_sequences = []
        def tracked_batch(*args, **kwargs):
            attempted_sequences.append(kwargs["sequence"])
            try:
                return write_batch(*args, **kwargs)
            except sqlite3.OperationalError:
                failed.set()
                raise
        results = []
        try:
            with patch.object(self.journal, "write_batch", side_effect=tracked_batch):
                closer = threading.Thread(target=lambda: results.append(recorder.close(timeout=.8)))
                closer.start()
                self.assertTrue(failed.wait(1))
                release.set()
                closer.join(1)
                self.assertFalse(closer.is_alive())
        finally:
            release.set()
            locker.join(1)
        self.assertEqual(results[0]["state"], "persisted")
        self.assertTrue(results[0]["final_flush_persisted"])
        self.assertTrue(results[0]["source_closed"])
        self.assertGreaterEqual(len(attempted_sequences), 2)
        self.assertEqual(len(set(attempted_sequences)), 1)
        self.assertEqual(recorder.close(timeout=.1), results[0])
        report = self.journal.inspect("execution")
        self.assertEqual(report["metrics"]["stdout_bytes"]["count"], 27)
        self.assertFalse(report["output"]["stderr"]["known"])

    def test_close_has_one_total_budget_under_persistent_write_lock(self):
        recorder = self.recorder()
        recorder.report_bytes("stdout", b"retained")
        with closing(sqlite3.connect(self.journal.path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            result = recorder.close(timeout=.05)
            self.assertLess(time.monotonic() - started, .09)
            self.assertFalse(result["final_flush_persisted"])
            self.assertNotEqual(result["state"], "persisted")
            self.assertEqual(recorder.snapshot()["metrics"]["stdout_bytes"]["count"], 8)
            # Let the already in-flight short SQLite operation finish while
            # the lock remains held. The one worker cannot open a new window.
            recorder._close_complete.wait(.2)
            self.assertTrue(recorder._close_complete.is_set())
            connection.rollback()
        self.assertFalse(recorder.close(timeout=.1)["final_flush_persisted"])

    def test_close_reuses_flusher_and_bounds_all_resource_waits(self):
        recorder = self.recorder(start=True)
        flusher = recorder._thread
        class SlowObserver:
            def __init__(self):
                self._stop = threading.Event()
                self._wake = threading.Event()
                self._thread = None

            def close(self, *, timeout):
                time.sleep(timeout)
                return {"unfinished_collector": True}
        recorder._process_observer = SlowObserver()
        recorder.report_bytes("stdout", b"last")
        started = time.monotonic()
        result = recorder.close(timeout=.4)
        self.assertLess(time.monotonic() - started, .44)
        self.assertIs(recorder._thread, flusher)
        self.assertTrue(result["final_flush_persisted"])
        self.assertTrue(result["source_closed"])
        self.assertTrue(result["process_observer"]["unfinished_collector"])


if __name__ == "__main__":
    unittest.main()
