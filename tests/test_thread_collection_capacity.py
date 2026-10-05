"""Actual recorder ownership retains the original thread capacity reservation."""
from contextlib import contextmanager
import json
import sqlite3
from contextlib import closing
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.runtime import Runtime
from dispatcher_sdk.observability import ObservationJournal, ObservationOptions
from tests._acceptance_evidence import retained_directory


class WitnessList(list):
    """External recorder, outside handler deployment state."""


class ThreadCollectionCapacityTests(unittest.TestCase):
    def test_idle_child_coordinator_reads_without_contending_for_actual_writer(self):
        root = retained_directory("sdk-idle-child-coordinator-")
        def handler(payload, context):
            return payload
        runtime = Runtime(root / "kernel.sqlite3", {"handler": handler}, isolation_mode="thread",
            observation_options=ObservationOptions(write_timeout=.05, query_timeout=.3))
        self.addCleanup(runtime.close)
        service = runtime._child_service
        writes = []
        original = ObservationJournal._transaction
        @contextmanager
        def transaction(journal, **kwargs):
            if journal is runtime.observation_journal:
                writes.append(threading.current_thread().name)
            with original(journal, **kwargs) as current:
                yield current
        with closing(sqlite3.connect(runtime.observation_journal.path, timeout=.1)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            try:
                with patch.object(ObservationJournal, "_transaction", transaction):
                    service.start()
                    began = time.monotonic()
                    for _ in range(3):
                        service.tick()
                    elapsed = time.monotonic() - began
                    self.assertLess(elapsed, .3)
                    self.assertEqual(writes, [])
            finally:
                writer.rollback()
        print("idle_child_coordinator_evidence=" + str(root), flush=True)

    def test_completed_business_retains_slot_until_owning_sqlite_flusher_exits(self):
        root = retained_directory("sdk-thread-collector-capacity-")
        entered, release, connection_released = (threading.Event() for _ in range(3))
        calls = WitnessList()

        def handler(payload, context):
            calls.append(context.command.execution_id)
            context.activity.report_bytes("stdout", b"physical stream")
            if context.command.execution_id == "first":
                if not entered.wait(2):
                    raise TimeoutError("original recorder did not start")
            return {"original": context.command.execution_id}

        handler.__execution_kernel_revision__ = "thread-collector-capacity-v1"
        runtime = Runtime(root / "kernel.sqlite3", {"handler": handler},
            isolation_mode="thread", max_thread_workers=1,
            observation_options=ObservationOptions(write_timeout=.05, flush_interval=.1))
        self.addCleanup(runtime.close)
        self.addCleanup(release.set)
        original = ObservationJournal._transaction
        held = []

        @contextmanager
        def transaction(journal, **kwargs):
            with original(journal, **kwargs) as current:
                if (journal is runtime.observation_journal and not held
                        and threading.current_thread().name == "dispatcher-observation-flush"):
                    held.append(current[0])
                    entered.set()
                    release.wait(8)
                    self.assertEqual(current[0].execute("SELECT 1").fetchone()[0], 1)
                    connection_released.set()
                yield current

        for execution_id in ("first", "second"):
            runtime.submit(runtime.command("handler", execution_id=execution_id,
                idempotency_key=execution_id, correlation_id="collector-capacity",
                timeout_seconds=4, payload={}))
        with patch.object(ObservationJournal, "_transaction", transaction):
            try:
                first = runtime.run_once(execution_id="first")
                self.assertEqual(first.state, "succeeded", first.to_dict())
                cutoff = time.monotonic() + 2
                while not runtime._thread_done and time.monotonic() < cutoff:
                    time.sleep(.01)
                self.assertTrue(runtime._thread_done, "business Future must finish before capacity check")
                self.assertIsNone(runtime.run_once(execution_id="second"))
                blocked = runtime.kernel.get("second").to_dict()
                self.assertEqual(blocked["state"], "queued")
                self.assertEqual(calls, ["first"])
                (root / "evidence.json").write_text(json.dumps({
                    "first": first.to_dict(), "blocked": blocked,
                    "calls_before_release": list(calls), "held_connection": bool(held),
                    "original_bounds": {"business": 4, "future_finish": 2, "hold": 8}}, indent=2))
            finally:
                release.set()
            self.assertTrue(connection_released.wait(2))
            cutoff = time.monotonic() + 2
            second = None
            while second is None and time.monotonic() < cutoff:
                second = runtime.run_once(execution_id="second")
                if second is None:
                    time.sleep(.01)
            self.assertIsNotNone(second)
            self.assertEqual(second.state, "succeeded", second.to_dict())
            self.assertEqual(calls, ["first", "second"])
            self.assertEqual(runtime.kernel.get("first").result, first.result)
        print("thread_collection_capacity_evidence=" + str(root / "evidence.json"), flush=True)
