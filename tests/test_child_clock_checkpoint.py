"""Real SQLite clock floors survive child request publication and recovery."""

import json
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace
from tests._acceptance_evidence import retained_directory
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.children import ChildService, HandlerChildren, _RetryWindow, _retry
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ObservationJournal, ObservationOptions


class ChildClockCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-child-clock-checkpoint-")
        self.wall = [time.time()]
        self.kernel = SQLiteKernel(self.root / "kernel.sqlite3", now=lambda: self.wall[0],
                                   default_lease_seconds=90)
        self.addCleanup(self.kernel.close)
        self.journal = ObservationJournal(self.root / "observations.sqlite3",
            kernel_path=self.kernel.db_path, source_id="clock-host",
            options=ObservationOptions(write_timeout=.05, query_timeout=.5))
        self.facts = SettlementJournal(self.kernel.db_path + ".settlements.sqlite3",
            kernel_path=self.kernel.db_path, source_id=self.journal.source_id)
        self.parent = self.command("parent")
        self.kernel.submit(self.parent)
        self.lease = self.kernel.claim_and_start("actual-parent-owner")
        self.parent_budget = self.kernel.prepare_execution_budget(self.lease).enter_handler(
            30, origin_id="execution:parent")
        self.kernel.confirm_handler_entry(self.lease, self.parent_budget)
        self.children = HandlerChildren(self.kernel, self.parent, self.lease, self.parent_budget,
            {"capacity": 1, "max_depth": 1, "registry_revision": "clock-registry"}, journal=self.journal)
        self.evidence = {"test": self.id(), "interpreter": sys.executable,
            "kernel_path": self.kernel.db_path, "parent_lease": self.lease.to_dict(), "records": []}

    def tearDown(self):
        path = self.root / "evidence.json"
        path.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
        print("child_clock_checkpoint_evidence=" + str(path), flush=True)

    @staticmethod
    def command(execution_id):
        return ExecutionCommandV2(execution_id, execution_id, "clock-registry", "clock-proof", None,
                                  "work", 1, RetryPolicy(), 30, {})

    def enqueue(self, request_id="original-call", *, window=None):
        envelope = self.parent_budget.derive(source="tool", origin_id=request_id, timeout_seconds=10)
        window = window or _RetryWindow(envelope, self.kernel)
        row = _retry(window, lambda: self.children._enqueue(request_id=request_id,
            child_id="child-" + request_id, action="run", child_command=self.command("child-" + request_id),
            envelope=envelope, window=window), store=self.children.store)
        self.evidence["records"].append({"enqueued": json.loads(json.dumps(row))})
        return row, window

    def persisted_row(self, row):
        return self.children.store.request(row["parent_execution_id"], row["request_id"])

    def test_post_commit_forward_then_rollback_retains_floor_without_kernel_watermark(self):
        baseline = self.wall[0]
        original_request = self.children.store.request
        original_verify = self.kernel.verify

        def post_commit_forward(*args):
            row = original_request(*args)
            self.wall[0] = baseline + 4
            return row

        def verify_after_rollback(lease):
            self.wall[0] = baseline
            return original_verify(lease)

        self.children.store.request = post_commit_forward
        self.kernel.verify = verify_after_rollback
        try:
            row, original_window = self.enqueue("post-commit")
        finally:
            self.children.store.request = original_request
            self.kernel.verify = original_verify
        persisted = self.persisted_row(row)
        restored = _RetryWindow(BudgetEnvelope.from_dict(json.loads(persisted["budget_json"])), self.kernel)
        original_remaining, restored_remaining = original_window.remaining(), restored.remaining()
        self.evidence["records"].append({"original_remaining": original_remaining,
            "restored_remaining": restored_remaining, "persisted": persisted,
            "kernel_watermark_advance": self.kernel.current_time() - baseline})
        self.assertLess(self.kernel.current_time() - baseline, .01)
        self.assertLess(original_remaining, 7)
        self.assertLessEqual(restored_remaining, original_remaining + .1)
        self.assertEqual(original_window.envelope.constraints, restored.envelope.constraints)
        self.assertEqual("running", self.kernel.get("parent").state)

    def test_locked_observation_writer_preserves_floor_in_independent_note_after_reopen(self):
        from contextlib import ExitStack
        from copy import deepcopy
        import traceback
        from unittest.mock import patch
        from tests._storage_evidence import StorageEvidence

        storage = StorageEvidence(self.root, self)
        storage.start(include_kernel=True)
        self.addCleanup(storage.stop)
        self.addCleanup(lambda: storage.save(checkpoint=self.evidence))
        stages = self.evidence["helper_stages"] = []
        self.evidence["stage_limit"] = 128

        def error_facts(error):
            return {"type": type(error).__name__, "message": str(error),
                    "traceback": traceback.format_exc(),
                    "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                    "sqlite_errorname": getattr(error, "sqlite_errorname", None)}

        def stage(name, operation, **inputs):
            record = {"stage": name, "wall": self.wall[0], "inputs": deepcopy(inputs)}
            if len(stages) < 128:
                stages.append(record)
            else:
                self.evidence["stage_overflow"] = True
            record["began"] = time.monotonic()
            try:
                result = operation()
                record["elapsed"] = time.monotonic() - record["began"]
                record["returned"] = True
                if isinstance(result, (dict, float)):
                    record["result"] = deepcopy(result)
                return result
            except BaseException as error:
                record["error"] = error_facts(error)
                raise
            finally:
                record.setdefault("elapsed", time.monotonic() - record["began"])

        with ExitStack() as patches:
            def trace_store(store, label):
                original_facts = store._facts

                def facts(*args, **kwargs):
                    journal = stage(label + "._facts", lambda: original_facts(*args, **kwargs),
                                    arguments=args, options=kwargs)
                    if journal is not None and kwargs.get("writer"):
                        original_note = journal.note

                        def note(*note_args, **note_kwargs):
                            return stage(label + ".facts.note",
                                lambda: original_note(*note_args, **note_kwargs),
                                arguments=note_args, options=note_kwargs)

                        journal.note = note
                    return journal

                patches.enter_context(patch.object(store, "_facts", facts))

            trace_store(self.children.store, "original_store")
            try:
                row, original_window = stage("enqueue", lambda: self.enqueue("writer-held"))
                original = json.loads(row["budget_json"])
                baseline = self.wall[0]
                writer = stage("writer.connect", lambda: sqlite3.connect(self.journal.path, timeout=1))
                writer_owned = [True]

                def cleanup_writer():
                    if not writer_owned[0]:
                        return
                    writer_owned[0] = False
                    primary = sys.exc_info()[1]
                    errors = []
                    try:
                        try:
                            stage("writer.rollback", writer.rollback)
                        except BaseException as error:
                            errors.append(error)
                            self.evidence.setdefault("writer_cleanup_errors", []).append(error_facts(error))
                    finally:
                        try:
                            try:
                                stage("writer.close", writer.close)
                            except BaseException as error:
                                errors.append(error)
                                self.evidence.setdefault("writer_cleanup_errors", []).append(error_facts(error))
                        finally:
                            self.wall[0] = baseline
                    if errors and primary is None:
                        raise errors[0]

                self.addCleanup(cleanup_writer)
                try:
                    stage("writer.begin", lambda: writer.execute("BEGIN IMMEDIATE"))
                    self.wall[0] = baseline + 4
                    started = time.monotonic()
                    narrowed_remaining = stage("original_window.remaining", original_window.remaining,
                                               envelope=original_window.envelope.to_dict())
                    self.assertLess(time.monotonic() - started, 1)
                    self.wall[0] = baseline
                    stored = stage("persisted_row", lambda: self.persisted_row(row))
                    self.assertEqual(original, json.loads(stored["budget_json"]))
                    notes = stage("inspect_notes", lambda: self.facts.inspect_notes(row["child_execution_id"]))
                    matching = [note for note in notes["notes"] if note["phase"] == "child_budget_checkpoint"]
                    self.assertTrue(matching, notes)
                    self.assertTrue(all(note["identity"]["attempt"] == note["identity"]["fence"] == 0
                                        for note in matching))
                    self.assertTrue(all(note["evidence"]["wait_id"] == row["wait_id"] for note in matching))
                    # A new service has no in-memory floor; only the persisted receipt can restore it.
                    reopened_journal = ObservationJournal(self.journal.path, kernel_path=self.kernel.db_path,
                        source_id=self.journal.source_id, options=self.journal.options)
                    service = ChildService(SimpleNamespace(kernel=self.kernel), reopened_journal)
                    trace_store(service.store, "reopened_store")
                    restored = _RetryWindow(BudgetEnvelope.from_dict(json.loads(stored["budget_json"])), self.kernel)
                    stage("reopened_store.attach", lambda: service.store.attach(stored, restored))
                    restored_remaining = stage("restored.remaining", restored.remaining,
                                               envelope=restored.envelope.to_dict())
                    self.assertLessEqual(restored_remaining, narrowed_remaining + .1)
                    self.assertEqual(original_window.envelope.constraints, restored.envelope.constraints)
                    self.evidence["records"].append({"held_writer_row": stored, "notes": notes,
                        "narrowed_remaining": narrowed_remaining, "reopened_remaining": restored_remaining})
                finally:
                    cleanup_writer()
                fresh = service.store.request(row["parent_execution_id"], row["request_id"])
                stage("unlocked_store.attach", lambda: service.store.attach(fresh, restored))
                committed = service.store.request(row["parent_execution_id"], row["request_id"])
                committed_budget = BudgetEnvelope.from_dict(json.loads(committed["budget_json"]))
                self.assertEqual(original_window.envelope.constraints, committed_budget.constraints)
                self.assertLessEqual(_RetryWindow(committed_budget, self.kernel).remaining(), narrowed_remaining + .1)
                self.evidence["records"].append({"unlocked_checkpoint": committed})

            except BaseException as error:
                self.evidence["original_error"] = error_facts(error)
                if "original_window" in locals():
                    self.evidence["failed_window"] = original_window.envelope.to_dict()
                with self.children.store._floor_lock:
                    self.evidence["in_memory_floors"] = {
                        key: value.to_dict() for key, value in self.children.store._floors.items()}
                raise
            finally:
                try:
                    storage.save(phase="before-cleanup", checkpoint=self.evidence)
                except BaseException as error:
                    self.evidence["capture_error"] = error_facts(error)
                    if "original_error" not in self.evidence:
                        raise
                    print("child_clock_checkpoint_capture_error=" + str(error), flush=True)

    def test_late_older_checkpoint_cannot_widen_persisted_floor(self):
        row, window = self.enqueue("out-of-order")
        original = BudgetEnvelope.from_dict(json.loads(row["budget_json"]))
        baseline = self.wall[0]
        self.wall[0] = baseline + 4
        window.remaining()
        self.wall[0] = baseline
        tight_row = self.persisted_row(row)
        tight = BudgetEnvelope.from_dict(json.loads(tight_row["budget_json"]))
        self.children.store.remember(row, original)
        restored_row = self.persisted_row(row)
        restored = BudgetEnvelope.from_dict(json.loads(restored_row["budget_json"]))
        tight_remaining = _RetryWindow(tight, self.kernel).remaining()
        restored_remaining = _RetryWindow(restored, self.kernel).remaining()
        self.assertLessEqual(restored_remaining, tight_remaining + .1)
        self.assertEqual(original.constraints, restored.constraints)
        self.evidence["records"].append({"tight": tight_row, "after_delayed_checkpoint": restored_row,
            "tight_remaining": tight_remaining, "restored_remaining": restored_remaining})

    def test_more_than_one_note_page_cannot_hide_a_stricter_checkpoint(self):
        row, window = self.enqueue("paged-history")
        identity = {"execution_id": row["child_execution_id"], "attempt": 0, "fence": 0}
        for index in range(50):
            self.facts.note(identity, "prior_diagnostic", {"index": index})
        baseline = self.wall[0]
        self.wall[0] = baseline + 4
        checkpoint = window.envelope.recheckpoint(sample=sample_clock(wall_time=self.wall[0]))
        self.wall[0] = baseline
        last = self.facts.note(identity, "child_budget_checkpoint",
            {"wait_id": row["wait_id"], "budget_envelope": checkpoint.to_dict()})
        # This establishes pagination, independently of the attachment's
        # strict per-attempt inspection budget and original work cutoff.
        page = self.facts.inspect_notes(row["child_execution_id"], timeout_seconds=1)
        self.assertTrue(page["complete"])
        self.assertTrue(page["has_more"])
        self.assertNotIn(last["note_id"], [note["note_id"] for note in page["notes"]])
        reopened = ChildService(SimpleNamespace(kernel=self.kernel), self.journal)
        restored = _RetryWindow(BudgetEnvelope.from_dict(json.loads(row["budget_json"])), self.kernel)
        self.evidence["records"].append({"first_page": page, "stricter_next_page_note": last})
        with self.assertRaises(BudgetClockUnknownError):
            reopened.store.attach(row, restored)


if __name__ == "__main__":
    unittest.main()
