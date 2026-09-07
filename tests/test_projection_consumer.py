from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator.projection import ProjectionConsumer


class ProjectionConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "source.sqlite"
        self.sdk = Orchestrator.open_sqlite(self.path, {}, isolation_mode="thread")
        self.addCleanup(self.sdk.close)
        self.sdk.create_run("run", command_id="create")
        self.add_event()
        self.add_event()
        self.effects = set()

    def add_event(self):
        revision = self.sdk.get_run("run")["revision"]
        self.sdk.apply_operations("run", command_id=f"event-{revision}", expected_revision=revision, operations=[])

    def consumer(self, **kwargs):
        return ProjectionConsumer(self.sdk, source_id="source", subscription="projection", **kwargs)

    def persist(self, identity, event):
        if identity in self.effects:
            return "already_present"
        self.effects.add(identity)
        return "persisted"

    def test_poison_page_replays_without_skipping(self):
        events = self.sdk.read_events("run")
        def poison(identity, event):
            if identity.sequence == events[1]["sequence"]:
                raise RuntimeError("poison")
            return self.persist(identity, event)
        report = self.consumer().drain("run", poison)
        self.assertEqual(report.status, "blocked")
        self.assertEqual(report.failure.event.sequence, events[1]["sequence"])
        self.assertEqual(self.sdk.get_subscription("run", "projection"), 0)
        report = self.consumer().drain("run", self.persist)
        self.assertEqual((report.status, report.replayed), ("completed", 1))
        self.assertEqual(len(self.effects), 3)

    def test_invalid_and_async_confirmations(self):
        async def async_callback(identity, event):
            return "persisted"
        for callback in (lambda i, e: None, lambda i, e: "success", async_callback):
            with self.subTest(callback=callback):
                result = self.consumer().drain("run", callback)
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.failure.stage, "callback")
                self.assertEqual(self.sdk.get_subscription("run", "projection"), 0)

    def test_ack_response_loss_uses_exact_request(self):
        original = self.sdk.acknowledge_events
        requests = []
        def lost(*args, **kwargs):
            requests.append(kwargs.copy())
            value = original(*args, **kwargs)
            if len(requests) == 1:
                raise OSError("response lost")
            return value
        with patch.object(self.sdk, "acknowledge_events", lost):
            result = self.consumer().drain("run", self.persist)
        self.assertEqual(result.status, "completed")
        self.assertEqual(requests[0], requests[1])

    def test_revision_conflict_bounded_and_replayed(self):
        original = self.sdk.acknowledge_events
        requests = []
        def racing(*args, **kwargs):
            requests.append(kwargs.copy())
            self.add_event()
            return original(*args, **kwargs)
        with patch.object(self.sdk, "acknowledge_events", racing):
            result = self.consumer(max_conflict_retries=2).drain("run", self.persist)
        self.assertEqual((result.status, result.conflicts), ("conflict", 3))
        self.assertEqual(len({r["command_id"] for r in requests}), 3)
        self.assertEqual(self.sdk.get_subscription("run", "projection"), 0)
        self.assertEqual(len(self.effects), 3)  # Frozen watermark despite producers.

    def test_cursor_conflict_reobserves(self):
        original = self.sdk.acknowledge_events
        first = True
        def racing(*args, **kwargs):
            nonlocal first
            if first:
                first = False
                original(*args, **{**kwargs, "command_id": "other-consumer"})
            return original(*args, **kwargs)
        with patch.object(self.sdk, "acknowledge_events", racing):
            result = self.consumer().drain("run", self.persist)
        self.assertEqual((result.status, result.conflicts), ("completed", 1))

    def test_fixed_watermark_with_success_window(self):
        first = True
        def callback(identity, event):
            nonlocal first
            if first:
                first = False
                self.add_event()
            return self.persist(identity, event)
        result = self.consumer(page_size=1).drain("run", callback)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.target, 3)
        self.assertEqual(result.acknowledged_cursor, 3)
        self.assertEqual(len(self.effects), 3)
        self.assertGreater(self.sdk.observe("run", subscription="projection")["event_high_watermark"], result.target)

    def test_stop_and_time_budget_after_callback_leave_page_unacked(self):
        stopped = False
        def callback(identity, event):
            nonlocal stopped
            stopped = True
            return self.persist(identity, event)
        result = self.consumer().drain("run", callback, should_stop=lambda: stopped)
        self.assertEqual(result.status, "interrupted")
        self.assertEqual(self.sdk.get_subscription("run", "projection"), 0)
        with patch("dispatcher_sdk.orchestrator.projection.time.monotonic", side_effect=[0, 0, 0, 2]):
            result = self.consumer().drain("run", self.persist, timeout_seconds=1)
        self.assertEqual(result.status, "interrupted")
        self.assertEqual(self.sdk.get_subscription("run", "projection"), 0)

    def test_prior_pages_survive_failure_and_callback_mutation(self):
        def callback(identity, event):
            if len(self.effects) == 1:
                raise RuntimeError("fail second page")
            event["sequence"] = 999999
            return self.persist(identity, event)
        result = self.consumer(page_size=1).drain("run", callback)
        self.assertEqual(result.acknowledged_cursor, 1)
        self.assertEqual(self.sdk.get_subscription("run", "projection"), 1)

    def test_sequence_holes_and_source_namespaces(self):
        self.sdk.create_run("other", command_id="other-create")
        self.add_event()
        result = self.consumer().drain("run", self.persist, target=4)
        self.assertEqual((result.status, result.acknowledged_cursor), ("completed", 3))
        second = ProjectionConsumer(self.sdk, source_id="independent", subscription="second")
        result = second.drain("run", self.persist)
        self.assertEqual(result.replayed, 0)
        self.assertEqual(result.acknowledged_cursor, 5)
        with self.assertRaises(ValueError):
            self.consumer().drain("run", self.persist, target=100)

    def test_concurrent_revision_from_another_thread(self):
        first = True
        with ThreadPoolExecutor(max_workers=1) as executor:
            def callback(identity, event):
                nonlocal first
                if first:
                    first = False
                    executor.submit(self.add_event).result(timeout=10)
                return self.persist(identity, event)
            result = self.consumer().drain("run", callback)
        self.assertEqual((result.status, result.conflicts, result.replayed), ("completed", 1, 3))

    def test_ack_failure_is_bounded_and_next_drain_replays(self):
        with patch.object(self.sdk, "acknowledge_events", side_effect=OSError("unavailable")) as ack:
            result = self.consumer(max_ack_retries=1).drain("run", self.persist)
        self.assertEqual((result.status, result.failure.reason), ("blocked", "ack_failed"))
        self.assertEqual(ack.call_count, 2)
        self.assertEqual(self.sdk.get_subscription("run", "projection"), 0)
        result = self.consumer().drain("run", self.persist)
        self.assertEqual((result.status, result.replayed), ("completed", 3))

    def test_reentrant_drain_rejected_and_lock_released(self):
        consumer = self.consumer()
        def callback(identity, event):
            consumer.drain("run", self.persist)
            return "persisted"
        result = consumer.drain("run", callback)
        self.assertEqual(result.failure.error_type, "RuntimeError")
        self.assertEqual(consumer.drain("run", self.persist).status, "completed")

    def test_process_crash_transaction_and_ack_windows(self):
        projection = Path(self.tmp.name) / "effects.sqlite"
        with closing(sqlite3.connect(projection)) as db:
            db.executescript("CREATE TABLE receipts(source,run,sequence,PRIMARY KEY(source,run,sequence));"
                             "CREATE TABLE effects(n INTEGER); INSERT INTO effects VALUES(0);")
        script = r'''
import os, sqlite3, sys
from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator.projection import ProjectionConsumer
sdk = Orchestrator.open_sqlite(sys.argv[1], {}, isolation_mode="thread")
mode = sys.argv[3]
def persist(identity, event):
    db = sqlite3.connect(sys.argv[2])
    with db:
        inserted = db.execute("INSERT OR IGNORE INTO receipts VALUES(?,?,?)", (identity.source_id,identity.run_id,identity.sequence)).rowcount
        if inserted:
            db.execute("UPDATE effects SET n=n+1")
        if mode == "before_commit": os._exit(71)
    db.close()
    if mode == "after_commit": os._exit(72)
    return "persisted" if inserted else "already_present"
original = sdk.acknowledge_events
def ack(*args, **kwargs):
    value = original(*args, **kwargs)
    if mode == "after_ack": os._exit(73)
    return value
sdk.acknowledge_events = ack
report = ProjectionConsumer(sdk,source_id="source",subscription="projection").drain("run",persist)
assert report.status == "completed", report
sdk.close()
'''
        for mode, expected_code, expected_effects in (("before_commit", 71, 0), ("after_commit", 72, 1), ("after_ack", 73, 3), ("resume", 0, 3)):
            result = subprocess.run([sys.executable, "-c", script, str(self.path), str(projection), mode],
                                    capture_output=True, text=True, timeout=30, env=os.environ.copy())
            self.assertEqual(result.returncode, expected_code, result.stderr)
            with closing(sqlite3.connect(projection)) as db:
                self.assertEqual(db.execute("SELECT n FROM effects").fetchone()[0], expected_effects)
            self.assertEqual(self.sdk.get_subscription("run", "projection"), 0 if expected_effects < 3 else 3)


if __name__ == "__main__":
    unittest.main()
