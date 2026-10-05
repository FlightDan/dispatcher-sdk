"""Early cumulative stream capture and truthful forced-exit evidence."""
from contextlib import closing
import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.settlement import merge_diagnostic_notes
from dispatcher_sdk.observability import (
    ActivityRecorder, ObservationIdentity, ObservationJournal, ObservationOptions,
)
from tests._acceptance_evidence import retained_directory


class StreamTelemetryLifetimeTests(unittest.TestCase):
    def test_first_stream_batch_is_early_and_subsequent_chunks_stay_coalesced(self):
        root = retained_directory("sdk-first-stream-flush-")
        options = ObservationOptions(flush_interval=3, write_timeout=.1, query_timeout=.2)
        journal = ObservationJournal(root / "observations.sqlite3",
            kernel_path=root / "kernel.sqlite3", source_id="host", options=options)
        identity = ObservationIdentity("stream", 1, 1)
        journal.bind_current(identity)
        recorder = ActivityRecorder(journal, identity, source_scope="handler")
        self.addCleanup(recorder.close)
        flushed = threading.Event()
        writes = []
        original_flush = recorder.flush

        def flush():
            began = time.monotonic()
            result = original_flush()
            writes.append({"elapsed": time.monotonic()-began, "receipt": result})
            flushed.set()
            return result

        with patch.object(recorder, "flush", flush):
            recorder.start()
            recorder.enable_stream("stdout")
            began = time.monotonic()
            receipt = recorder.report_bytes("stdout", b"raw-without-newline\xff")
            self.assertEqual("captured", receipt["state"])
            self.assertTrue(flushed.wait(.6), "first stream batch waited for the periodic tick")
            elapsed = time.monotonic()-began
            first = journal.inspect("stream")
            self.assertEqual(20, first["metrics"]["stdout_bytes"]["count"])
            self.assertLess(elapsed, .6)
            self.assertEqual(1, len(writes))
            flushed.clear()
            for _ in range(1000):
                self.assertEqual("captured", recorder.report_bytes("stdout", b"x")["state"])
            self.assertFalse(flushed.wait(.1), "later chunks caused per-chunk persistence")
            self.assertEqual(1, len(writes))
            closed = recorder.close(timeout=1)
        final = journal.inspect("stream")
        self.assertTrue(closed["final_flush_persisted"], closed)
        self.assertEqual(1020, final["metrics"]["stdout_bytes"]["count"])
        with closing(sqlite3.connect(journal.path)) as connection:
            sources = connection.execute("SELECT source_id,sequence,metrics_json FROM obs_sources").fetchall()
        self.assertEqual(1, len(sources), "cumulative publication created another counting source")
        (root / "evidence.json").write_text(json.dumps({"bounds": {"periodic_interval": 3,
            "first_batch_wait": .6, "coalescing_observation": .1, "close": 1},
            "first_batch_elapsed": elapsed, "capture_receipt": receipt, "flushes": writes,
            "close_receipt": closed, "first": first, "final": final, "sources": sources}, indent=2))
        print("first_stream_flush_evidence=" + str(root / "evidence.json"), flush=True)

    def test_busy_raw_capture_remains_unknown_and_does_not_fabricate_zero(self):
        root = retained_directory("sdk-stream-capture-busy-")
        journal = ObservationJournal(root / "observations.sqlite3",
            kernel_path=root / "kernel.sqlite3", source_id="host")
        identity = ObservationIdentity("stream", 1, 1)
        journal.bind_current(identity)
        recorder = ActivityRecorder(journal, identity, source_scope="handler")
        self.addCleanup(recorder.close)
        raw = b"raw-without-newline\xff"
        (root / "stdout.log").write_bytes(raw)
        with recorder._lock:
            declaration = recorder.enable_stream("stdout")
            capture = recorder.report_bytes("stdout", raw)
        self.assertEqual("capture_busy", declaration["reason"])
        self.assertEqual("capture_busy", capture["reason"])
        receipt = recorder.flush()
        report = journal.inspect("stream")
        self.assertEqual("persisted", receipt["state"])
        self.assertEqual(raw, (root / "stdout.log").read_bytes())
        self.assertNotIn("stdout_bytes", report["metrics"])
        self.assertFalse(report["output"]["stdout"]["known"])
        self.assertFalse(report["complete"])
        self.assertEqual(2, report["collection_gaps"])
        (root / "evidence.json").write_text(json.dumps({"raw_bytes": len(raw),
            "declaration": declaration, "capture": capture, "flush": receipt, "observation": report}, indent=2))
        print("busy_stream_capture_evidence=" + str(root / "evidence.json"), flush=True)

    def test_first_batch_writer_busy_retains_counts_for_original_source_cleanup(self):
        from tests._storage_evidence import StorageEvidence

        root = retained_directory("sdk-first-stream-writer-busy-")
        storage = StorageEvidence(root, self)
        storage.start()
        self.addCleanup(storage.stop)
        self.addCleanup(storage.save)
        options = ObservationOptions(flush_interval=3, write_timeout=.05, query_timeout=.2)
        journal = ObservationJournal(root / "observations.sqlite3",
            kernel_path=root / "kernel.sqlite3", source_id="host", options=options)
        identity = ObservationIdentity("stream", 1, 1)
        journal.bind_current(identity)
        recorder = ActivityRecorder(journal, identity, source_scope="handler")
        self.addCleanup(recorder.close)
        attempted = threading.Event()
        flushes = []
        original_flush = recorder.flush

        def flush():
            receipt = original_flush()
            flushes.append(receipt)
            attempted.set()
            return receipt

        with closing(sqlite3.connect(journal.path, timeout=0)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            try:
                with patch.object(recorder, "flush", flush):
                    recorder.start()
                    recorder.report_bytes("stdout", b"raw-without-newline\xff")
                    self.assertTrue(attempted.wait(.6), "early writer admission did not return")
                    self.assertEqual("degraded", flushes[0]["state"])
                    self.assertTrue(flushes[0]["retryable"])
                    local = recorder.snapshot()
                    persisted = journal.inspect("stream")
                    self.assertEqual(20, local["metrics"]["stdout_bytes"]["count"])
                    self.assertNotIn("stdout_bytes", persisted["metrics"])
                    self.assertFalse(persisted["output"]["stdout"]["known"])
            finally:
                writer.rollback()
        closed = recorder.close(timeout=1)
        final = journal.inspect("stream")
        self.assertTrue(closed["final_flush_persisted"], closed)
        self.assertEqual(20, final["metrics"]["stdout_bytes"]["count"])
        self.assertEqual([recorder.source_id], [source["source_id"] for source in final["sources"]])
        (root / "evidence.json").write_text(json.dumps({"bounds": {
            "periodic_interval": 3, "write_timeout": .05, "attempt_wait": .6, "close": 1},
            "flushes": flushes, "local": local, "blocked_persisted": persisted,
            "close": closed, "final": final}, indent=2, default=repr))
        print("first_stream_writer_busy_evidence=" + str(root / "evidence.json"), flush=True)

    def test_forced_worker_flush_uncertainty_makes_driver_observation_incomplete(self):
        report = {"identity": {"attempt": 1, "fence": 1}, "complete": True, "metrics": {}}
        evidence = {"kind": "timeout", "telemetry_incomplete": True,
            "telemetry_flush": {"state": "unknown",
                "reason": "worker_terminated_without_final_flush_receipt"}}
        merge_diagnostic_notes(report, {"complete": True, "has_more": False, "notes": [{
            "identity": {"execution_id": "stream", "attempt": 1, "fence": 1},
            "phase": "handler_outcome", "created_at": time.time(), "note_id": "original",
            "evidence": evidence}]}, process_freshness=3)
        self.assertFalse(report["complete"])
        self.assertEqual("telemetry_collection_incomplete", report["unknown_reason"])
        self.assertNotIn("stdout_bytes", report["metrics"])
        self.assertEqual(evidence, report["phases"][0]["details"])
