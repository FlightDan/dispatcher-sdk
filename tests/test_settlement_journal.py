from __future__ import annotations

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import time
import traceback
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.contracts import ExecutionLease, ExecutionResultV2
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.execution_kernel.settlement import (
    SettlementBindingError, SettlementBusyError, SettlementConflictError, SettlementJournal,
)
from tests._acceptance_evidence import retained_directory
from tests._storage_evidence import StorageEvidence


def lease(attempt=1, fence=1):
    return ExecutionLease("execution", "lease", "owner", fence, attempt, 9999999999, 1)


def result(value=None, attempt=1, fence=1):
    return ExecutionResultV2("original-result", "execution", "succeeded", attempt, fence, ["effect-original"],
        100, 101, "correlation", None, {"value": value}, None)


class SettlementJournalTests(unittest.TestCase):
    def setUp(self):
        if self._testMethodName == 'test_committed_original_result_survives_process_exit_and_reopen':
            root = retained_directory('sdk-settlement-process-exit-')
        else:
            root = retained_directory('sdk-settlement-journal-')
        self.root = root
        self.storage_evidence = StorageEvidence(root, self)
        self.storage_evidence.start()
        self.addCleanup(self.storage_evidence.stop)
        self.addCleanup(self.storage_evidence.save)
        self.kernel_path = root / "kernel.db"
        self.path = Path(str(self.kernel_path) + ".settlements.sqlite3")
        self.journal = SettlementJournal(self.path, source_id="store-original", kernel_path=self.kernel_path,
            timeout_seconds=1 if self._testMethodName == 'test_committed_original_result_survives_process_exit_and_reopen' else .1)

    def tearDown(self):
        self.storage_evidence.save(phase="before_cleanup")

    def test_kernel_writer_cannot_block_independent_durable_result(self):
        kernel = SQLiteKernel(self.kernel_path)
        self.addCleanup(kernel.close)
        with closing(sqlite3.connect(self.kernel_path)) as writer, writer:
            writer.execute("BEGIN IMMEDIATE")
            began = time.monotonic()
            receipt = self.journal.record(lease(), result("business-finished"), timeout_seconds=.1)
            self.assertLess(time.monotonic() - began, .5)
            self.assertEqual("pending", receipt["state"])
            self.assertEqual(result("business-finished").to_dict(), self.journal.pending()[0]["result"])
            self.assertEqual([], kernel.events_since(0))

    def test_journal_writer_contention_is_bounded_and_leaves_no_fake_receipt(self):
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute("BEGIN EXCLUSIVE")
            began = time.monotonic()
            with self.assertRaises(SettlementBusyError) as caught:
                self.journal.record(lease(), result(), timeout_seconds=.04)
            self.assertLess(time.monotonic() - began, .5)
            self.assertIsInstance(caught.exception.__cause__, sqlite3.OperationalError)
            with self.assertRaises(SettlementBusyError):
                self.journal.inspect("execution", timeout_seconds=.04)
        self.assertEqual([], self.journal.pending())
        self.assertEqual("pending", self.journal.record(lease(), result())["state"])

    def test_committed_original_result_survives_process_exit_and_reopen(self):
        script = """import json,os,sys,time,traceback
from dispatcher_sdk.execution_kernel.contracts import ExecutionLease,ExecutionResultV2
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
def event(stage, **facts):
    value={'stage':stage,'at':time.time(),'monotonic':time.monotonic(),'pid':os.getpid(),**facts}
    print(json.dumps(value),flush=True)
timeout=float(sys.argv[5])
try:
    event('initialize_started',timeout_seconds=timeout)
    journal=SettlementJournal(sys.argv[1],source_id='store-original',kernel_path=sys.argv[2],timeout_seconds=timeout)
    event('initialize_committed')
    event('record_started',timeout_seconds=timeout)
    receipt=journal.record(ExecutionLease.from_dict(json.loads(sys.argv[3])),ExecutionResultV2.from_dict(json.loads(sys.argv[4])),
        evidence={'telemetry_flush':{'final_flush_persisted':False}},timeout_seconds=timeout)
    event('record_committed',receipt=receipt)
    event('note_started',timeout_seconds=timeout)
    note=journal.note(ExecutionLease.from_dict(json.loads(sys.argv[3])),'collector_flush',{'state':'pending'},timeout_seconds=timeout)
    event('note_committed',note=note)
    os._exit(42)
except BaseException as error:
    event('error',error_type=type(error).__name__,message=str(error),traceback=traceback.format_exc(),
          sqlite_errorcode=getattr(error,'sqlite_errorcode',None))
    raise
"""
        original = result({"raw": "provider-response", "sequence": [1, 2, 3]})
        import dispatcher_sdk
        evidence = {'test': self.id(), 'sdk_import': dispatcher_sdk.__file__, 'interpreter': sys.executable,
            'journal_path': str(self.path), 'kernel_path': str(self.kernel_path), 'operation_timeout': 1,
            'process_timeout': 10, 'original_lease': lease().to_dict(), 'original_result': original.to_dict()}
        try:
            process = subprocess.run([sys.executable, "-c", script, str(self.path), str(self.kernel_path),
                json.dumps(lease().to_dict()), json.dumps(original.to_dict()), str(evidence['operation_timeout'])],
                timeout=evidence['process_timeout'], capture_output=True)
            evidence['child'] = {'returncode': process.returncode, 'stdout': process.stdout.decode(errors='replace'),
                'stderr': process.stderr.decode(errors='replace')}
            events = [json.loads(line) for line in evidence['child']['stdout'].splitlines()]
            evidence['child']['events'] = events
            self.assertEqual(42, process.returncode, evidence['child'])
            reopened = SettlementJournal(self.path, source_id="store-original", kernel_path=self.kernel_path,
                timeout_seconds=evidence['operation_timeout'])
            pending = reopened.pending(timeout_seconds=evidence['operation_timeout'])
            notes = reopened.inspect_notes("execution", timeout_seconds=evidence['operation_timeout'])
            evidence.update(reopened_pending=pending, reopened_notes=notes)
            self.assertEqual(1, len(pending), evidence)
            receipt = pending[0]
            self.assertEqual(original.to_dict(), receipt["result"])
            self.assertEqual(lease().to_dict(), receipt["lease"])
            self.assertEqual("pending", receipt["state"])
            self.assertEqual({"telemetry_flush": {"final_flush_persisted": False}}, receipt["evidence"])
            committed_note = next(event['note'] for event in events if event['stage'] == 'note_committed')
            self.assertEqual(committed_note['note_id'], notes['notes'][0]['note_id'])
        except BaseException as error:
            evidence['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
            if isinstance(error, subprocess.TimeoutExpired):
                evidence['child'] = {'stdout': (error.stdout or b'').decode(errors='replace'),
                    'stderr': (error.stderr or b'').decode(errors='replace'), 'timeout': error.timeout}
            raise
        finally:
            path = self.path.parent/'evidence.json'
            path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print('settlement_process_exit_evidence=' + str(path), flush=True)

    def test_canonical_replay_preserves_record_and_conflicting_facts_fail(self):
        first = self.journal.record(lease(), result({"a": 1, "b": 2}))
        self.assertEqual(first, self.journal.record(lease(), result({"b": 2, "a": 1})))
        with self.assertRaises(SettlementConflictError):
            self.journal.record(lease(), result("changed-original"))
        with self.assertRaises(SettlementConflictError):
            self.journal.record(replace(lease(), expires_at=9999999998), result({"a": 1, "b": 2}))
        self.assertEqual([first], self.journal.pending())

    def test_concurrent_different_original_results_have_one_winner(self):
        def record(value):
            try:
                return self.journal.record(lease(), result(value), timeout_seconds=1)
            except SettlementConflictError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(record, ["first", "second"]))
        self.assertEqual(1, outcomes.count("conflict"))
        self.assertEqual(1, len(self.journal.pending()))

    def test_settlement_cas_idempotency_and_raw_error_recovery(self):
        pending = self.journal.record(lease(), result())
        raw = {"exception_type": "OperationalError", "message": "database is locked",
            "sqlite_errorcode": 5, "raw": {"nested": ["retain", "all"]}}
        errored = self.journal.settle(pending, "error", raw)
        self.assertEqual(raw, self.journal.pending()[0]["evidence"])
        self.assertEqual(2, errored["revision"])
        self.assertEqual(errored, self.journal.settle(pending, "error", raw))
        with self.assertRaises(SettlementConflictError):
            self.journal.settle(pending, "recorded", {"kernel_revision": 4})
        recorded = self.journal.settle(errored, "recorded", {"kernel_revision": 4})
        self.assertEqual([], self.journal.pending())
        self.assertEqual(recorded, self.journal.settle(errored, "recorded", {"kernel_revision": 4}))
        with self.assertRaises(SettlementConflictError):
            self.journal.settle(recorded, "superseded", {"kernel_revision": 5})
        self.assertEqual(result().to_dict(), recorded["result"])
        self.assertEqual(recorded, self.journal.record(lease(), result()))

    def test_deferred_outcome_and_recovery_required_preserve_exact_facts(self):
        deferred = {"kind": "deferred", "outcome": {"kind": "timeout", "effect_ids": ["original-effect"],
            "error": {"message": "original control error"}}}
        pending = self.journal.record(lease(), deferred)
        self.assertIsNone(pending["result"])
        self.assertEqual(deferred, pending["deferred"])
        state = self.journal.settle(pending, "recovery_required", {"effect_id": "original-effect"})
        self.assertEqual([], self.journal.pending())
        self.assertEqual(state, self.journal.inspect("execution")[0])
        with self.assertRaises(ValueError):
            self.journal.record(lease(2, 2), {"kind": "deferred", "outcome": ("not-json",)})

    def test_store_path_and_schema_binding_reject_other_database(self):
        for source_id, kernel_path in (("other-store", self.kernel_path), ("store-original", self.kernel_path.with_name("other.db"))):
            with self.assertRaises(SettlementBindingError):
                SettlementJournal(self.path, source_id=source_id, kernel_path=kernel_path)
        with self.assertRaises(SettlementBindingError):
            SettlementJournal(self.kernel_path, source_id="store-original", kernel_path=self.kernel_path)
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute("CREATE TABLE unrelated(value)")
        with self.assertRaises(SettlementBindingError):
            self.journal.pending()

    def test_inspection_connections_are_read_only_and_cannot_create_missing_store(self):
        self.journal.record(lease(), result())
        reader = SettlementJournal.open_readonly(self.path, source_id=self.journal.source_id,
            kernel_path=self.journal.kernel_path)
        self.assertEqual(reader.inspect("execution"), self.journal.inspect("execution"))
        for operation in (lambda: reader.note(lease(), "unexpected-write", {}),
                          lambda: reader.record(lease(), result()),
                          lambda: reader.settle(lease(), "error", {})):
            with self.assertRaises(SettlementBindingError):
                operation()
        with self.journal._connection(.1) as reader:
            self.assertEqual(1, reader.execute("PRAGMA query_only").fetchone()[0])
            with self.assertRaises(sqlite3.OperationalError):
                reader.execute("DELETE FROM settlement_records")
        self.assertEqual(1, len(self.journal.inspect("execution")))
        os.unlink(self.path)
        with self.assertRaises(sqlite3.OperationalError):
            self.journal.inspect("execution")
        self.assertFalse(self.path.exists())
        with self.assertRaises(sqlite3.OperationalError):
            SettlementJournal.open_readonly(self.path, source_id=self.journal.source_id,
                kernel_path=self.journal.kernel_path)
        self.assertFalse(self.path.exists())

    def test_unsafe_sqlite_journal_mode_cannot_issue_durable_receipt(self):
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute("PRAGMA journal_mode=OFF")
        # OFF is connection-local in SQLite: test a writer which actually
        # reopens with disabled rollback journaling, rather than assuming its
        # persisted setting changes a different connection.
        original = sqlite3.connect

        def unsafe_connection(*args, **kwargs):
            connection = original(*args, **kwargs)
            connection.execute("PRAGMA journal_mode=OFF")
            return connection

        with patch("dispatcher_sdk.execution_kernel.settlement.sqlite3.connect", side_effect=unsafe_connection):
            with self.assertRaises(SettlementBindingError):
                self.journal.record(lease(), result())
        self.assertEqual([], self.journal.pending())

    def test_large_original_is_durable_but_inspection_does_not_load_or_truncate_it(self):
        original = result("原始" * 100000)
        self.journal.record(lease(), original)
        with patch("dispatcher_sdk.execution_kernel.settlement.json.loads", side_effect=AssertionError("diagnostic loaded oversized JSON")):
            report = self.journal.inspect("execution")
        self.assertEqual("pending", report[0]["state"])
        self.assertTrue(report[0]["truncated"])
        self.assertEqual("settlement_inspection_byte_limit", report[0]["unknown_reason"])
        self.assertEqual(original.to_dict(), self.journal.pending()[0]["result"])

    def test_inspection_count_limit_is_explicit_and_pending_is_bounded(self):
        for generation in range(1, 4):
            self.journal.record(lease(generation, generation), result(generation, generation, generation))
        report = self.journal.inspect("execution", limit=2)
        self.assertEqual(2, len(report))
        self.assertTrue(report[-1]["more"])
        self.assertEqual(1, len(self.journal.pending(limit=1)))
        with self.assertRaises(ValueError):
            self.journal.pending(limit=51)

    def test_original_result_and_initial_evidence_commit_atomically_and_replay_preserves_first(self):
        evidence = {"telemetry_flush": {"state": "pending", "final_flush_persisted": False},
            "raw_error": {"message": "original collector failure"}}
        with patch("dispatcher_sdk.execution_kernel.settlement._record", side_effect=RuntimeError("before commit")):
            with self.assertRaisesRegex(RuntimeError, "before commit"):
                self.journal.record(lease(), result("original"), evidence=evidence)
        self.assertEqual(self.journal.pending(), [])
        receipt = self.journal.record(lease(), result("original"), evidence=evidence)
        reopened = SettlementJournal(self.path, source_id="store-original", kernel_path=self.kernel_path)
        self.assertEqual(reopened.pending()[0], receipt)
        self.assertEqual(receipt["evidence"], evidence)
        self.assertEqual(receipt, reopened.record(lease(), result("original"), evidence={"later": "ignored"}))
        self.assertEqual(receipt, reopened.record(lease(), result("original")))
        with self.assertRaises(SettlementConflictError):
            reopened.record(lease(), result("different"), evidence=evidence)

    def test_notes_persist_independently_of_both_kernel_and_observation_writers(self):
        kernel = SQLiteKernel(self.kernel_path)
        self.addCleanup(kernel.close)
        observation_path = self.root / "observations.sqlite3"
        with closing(sqlite3.connect(observation_path)) as initialize, initialize:
            initialize.execute("CREATE TABLE pressure(value)")
        with (
            closing(sqlite3.connect(self.kernel_path)) as kernel_writer,
            kernel_writer,
            closing(sqlite3.connect(observation_path)) as observation_writer,
            observation_writer,
        ):
            kernel_writer.execute("BEGIN IMMEDIATE")
            observation_writer.execute("BEGIN IMMEDIATE")
            began = time.monotonic()
            receipt = self.journal.note(lease(), "collector_flush", {"final_flush_persisted": False})
            self.assertLess(time.monotonic() - began, .5)
            self.assertEqual(self.journal.pending(), [])
            self.assertEqual(self.journal.inspect_notes("execution")["notes"], [receipt])
        reopened = SettlementJournal(self.path, source_id="store-original", kernel_path=self.kernel_path)
        self.assertEqual(reopened.inspect_notes("execution")["notes"], [receipt])

    def test_notes_do_not_create_replace_or_settle_original_results(self):
        unclaimed = {"execution_id": "execution", "attempt": 0, "fence": 0}
        first = self.journal.note(unclaimed, "cancellation_requested", {"stage": "request"})
        self.assertEqual([], self.journal.pending())
        receipt = self.journal.record(lease(), result("original"), evidence={"initial": True})
        stale = self.journal.note(lease(2, 2), "collector_flush", {"state": "pending"})
        current = self.journal.note(lease(), "execution_returned", {"status": "failed"})
        self.assertEqual(self.journal.pending(), [receipt])
        with self.assertRaises(SettlementConflictError):
            self.journal.settle(stale, "recorded", {"claimed_authority": True})
        with self.assertRaises(ValueError):
            self.journal.settle(first, "recorded", {})
        self.assertEqual(self.journal.inspect_notes("execution")["notes"], [first, stale, current])
        self.assertEqual(3, len({note["note_id"] for note in (first, stale, current)}))
        terminal = self.journal.settle(receipt, "recorded", {"kernel_revision": 4})
        self.journal.note(lease(), "late_diagnostic", {"raw": "late fact"})
        self.assertEqual(self.journal.inspect("execution"), [terminal])

    def test_notes_read_only_missing_store_and_unshipped_version_one_are_not_repaired(self):
        self.journal.note(lease(), "phase", {"raw": "fact"})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            before = list(connection.iterdump())
        self.journal.inspect_notes("execution")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(list(connection.iterdump()), before)
        with self.journal._connection(.1) as reader:
            with self.assertRaises(sqlite3.OperationalError):
                reader.execute("DELETE FROM settlement_notes")
        os.unlink(self.path)
        with self.assertRaises(sqlite3.OperationalError):
            self.journal.inspect_notes("execution")
        self.assertFalse(self.path.exists())
        from dispatcher_sdk.execution_kernel import settlement
        with closing(sqlite3.connect(self.path)) as old, old:
            for statement in settlement._SCHEMA[:3]:
                old.execute(statement.replace("version=2", "version=1"))
            old.execute("INSERT INTO settlement_meta VALUES(1,1,?,?)", ("store-original", str(self.kernel_path)))
            before = list(old.iterdump())
        with self.assertRaises(SettlementBindingError):
            SettlementJournal(self.path, source_id="store-original", kernel_path=self.kernel_path)
        with closing(sqlite3.connect(self.path)) as old, old:
            self.assertEqual(list(old.iterdump()), before)

    def test_oversized_notes_are_not_loaded_and_cursor_continues_to_small_note(self):
        big = self.journal.note(lease(), "collector_flush", {"raw": "原始" * 100000})
        small = self.journal.note(lease(), "collector_closed", {"confirmed": True})
        with patch("dispatcher_sdk.execution_kernel.settlement.json.loads", side_effect=AssertionError("oversized diagnostic loaded")):
            page = self.journal.inspect_notes("execution", limit=1, max_bytes=1024)
        self.assertFalse(page["complete"])
        self.assertTrue(page["truncated"])
        self.assertTrue(page["has_more"])
        self.assertEqual(page["cursor"], big["sequence"])
        self.assertEqual(page["notes"][0]["note_id"], big["note_id"])
        self.assertIsNone(page["notes"][0]["evidence"])
        self.assertLessEqual(len(json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode()), 1024)
        second = self.journal.inspect_notes("execution", after=page["cursor"], max_bytes=1024)
        self.assertEqual(second["notes"], [small])
        self.assertTrue(second["complete"])
        self.assertFalse(second["has_more"])

    def test_note_inspection_budget_includes_python_serialization_and_busy_is_unknown(self):
        self.journal.note(lease(), "phase", {"raw": "fact"})
        original = json.JSONEncoder.iterencode

        def slow_encode(encoder, *args, **kwargs):
            time.sleep(.03)
            yield from original(encoder, *args, **kwargs)

        with patch("dispatcher_sdk.execution_kernel.settlement.json.JSONEncoder.iterencode", slow_encode):
            page = self.journal.inspect_notes("execution", timeout_seconds=.01)
        self.assertFalse(page["complete"])
        self.assertTrue(page["timed_out"])
        self.assertEqual(page["cursor"], 0)
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute("BEGIN EXCLUSIVE")
            began = time.monotonic()
            page = self.journal.inspect_notes("execution", timeout_seconds=.04)
            self.assertLess(time.monotonic() - began, .5)
            self.assertTrue(page["timed_out"])
            with self.assertRaises(SettlementBusyError):
                self.journal.note(lease(), "blocked", {})
        self.assertEqual(len(self.journal.inspect_notes("execution")["notes"]), 1)

    def test_note_pagination_and_strict_bounds_preserve_every_receipt(self):
        receipts = [self.journal.note(lease(), "phase", {"number": number}) for number in range(4)]
        first = self.journal.inspect_notes("execution", limit=2)
        second = self.journal.inspect_notes("execution", after=first["cursor"], limit=2)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertEqual(first["notes"] + second["notes"], receipts)
        for kwargs in ({"after": -1}, {"after": True}, {"limit": 51}, {"max_bytes": 262145}):
            with self.assertRaises(ValueError):
                self.journal.inspect_notes("execution", **kwargs)
        with self.assertRaises(ValueError):
            self.journal.note({"execution_id": "execution", "attempt": -1, "fence": 0}, "phase", {})
        with self.assertRaises(ValueError):
            self.journal.note(lease(), "界" * 128, {})
        with self.assertRaises(ValueError):
            self.journal.note(lease(), "phase", {"not_json": (1, 2)})
        with self.assertRaises(ValueError):
            self.journal.inspect_notes("\\" * 200, max_bytes=1024)

    def test_escaped_phase_marker_preserves_identity_and_cursor_with_minimum_byte_budget(self):
        name = "x" * 240
        receipt = self.journal.note({"execution_id": name, "attempt": 0, "fence": 0},
            "x" + "\x00" * 127, {})
        page = self.journal.inspect_notes(name, max_bytes=1024)
        self.assertEqual(page["cursor"], receipt["sequence"])
        self.assertEqual(page["notes"][0]["note_id"], receipt["note_id"])
        self.assertEqual(page["notes"][0]["identity"], receipt["identity"])
        self.assertFalse(page["complete"])
        self.assertTrue(page["truncated"])
        self.assertLessEqual(len(json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode()), 1024)


if __name__ == "__main__":
    unittest.main()
