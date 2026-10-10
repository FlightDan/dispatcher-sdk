"""Real SQLite clock floors survive child request publication and recovery."""

import json
import math
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace
from tests._acceptance_evidence import retained_directory
from tests._storage_evidence import StorageEvidence
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.children import ChildService, HandlerChildren, _RetryWindow, _retry
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ObservationJournal, ObservationOptions


class ChildClockCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-child-clock-checkpoint-")
        if self._testMethodName == 'test_more_than_one_note_page_cannot_hide_a_stricter_checkpoint':
            self.storage_evidence = StorageEvidence(self.root, self)
            self.storage_evidence.start(include_kernel=True)
            self.addCleanup(self.storage_evidence.stop)
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
        if hasattr(self, 'storage_evidence'):
            try:
                self.storage_evidence.save(phase='before_cleanup', checkpoint=self.evidence)
            except Exception as error:
                self.evidence['diagnostic_error'] = {'type': type(error).__name__, 'message': str(error)}
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

    def forward_checkpoint(self, envelope, seconds):
        baseline = self.wall[0]
        try:
            self.wall[0] = baseline + seconds
            return envelope.recheckpoint(sample=sample_clock(wall_time=self.wall[0]))
        finally:
            self.wall[0] = baseline

    def assert_bound_floor(self, child_id, supplied):
        limits = self.kernel.get_execution_limits(child_id)
        bound = BudgetEnvelope.from_dict(limits["envelope"])
        sample = sample_clock(wall_time=self.wall[0])
        expected = supplied.recheckpoint(sample=sample)
        actual = bound.recheckpoint(sample=sample)
        self.evidence["records"].append({"supplied": supplied.to_dict(), "bound": limits,
            "expected_remaining": expected.view(sample=sample).remaining_work_seconds,
            "actual_remaining": actual.view(sample=sample).remaining_work_seconds})
        self.assertEqual(supplied.constraints, bound.constraints)
        self.assertEqual(supplied.started_at, bound.started_at)
        # Repeated elapsed projection can round epoch-sized floats by one ULP.
        # This is numeric precision, not an extension of any work deadline.
        tolerance = 4 * math.ulp(expected.checkpoint.wall_at)
        self.assertGreaterEqual(actual.checkpoint.wall_at + tolerance, expected.checkpoint.wall_at)
        self.assertEqual(("parent", self.lease.attempt, self.lease.fence),
            (limits["parent_execution_id"], limits["parent_attempt"], limits["parent_fence"]))
        self.assertEqual("queued", self.kernel.get(child_id).state)

    def test_child_submission_retains_incoming_forward_floor_after_rollback(self):
        envelope = self.parent_budget.derive(source="tool", origin_id="submission-floor", timeout_seconds=10)
        supplied = self.forward_checkpoint(envelope, 4)
        parent_before = self.kernel.get_execution_limits("parent")
        self.kernel.submit_child(self.command("incoming-floor"), self.lease, supplied)
        self.assert_bound_floor("incoming-floor", supplied)
        self.assertEqual(parent_before, self.kernel.get_execution_limits("parent"))

    def test_child_submission_and_adoption_replay_keep_new_stronger_floor(self):
        for action in ("submit", "adopt"):
            with self.subTest(action=action):
                child_id = action + "-floor-replay"
                child = self.command(child_id)
                envelope = self.parent_budget.derive(source="tool", origin_id=child_id, timeout_seconds=10)
                if action == "submit":
                    self.kernel.submit_child(child, self.lease, envelope)
                else:
                    self.kernel.submit(child)
                    self.kernel.adopt_child(child_id, self.lease, envelope)
                before = self.kernel.get(child_id).to_dict()
                supplied = self.forward_checkpoint(envelope, 4)
                parent_before = self.kernel.get_execution_limits("parent")
                if action == "submit":
                    self.kernel.submit_child(child, self.lease, supplied)
                else:
                    self.kernel.adopt_child(child_id, self.lease, supplied)
                self.assert_bound_floor(child_id, supplied)
                self.assertEqual(before, self.kernel.get(child_id).to_dict())
                self.assertEqual(parent_before, self.kernel.get_execution_limits("parent"))
                retained = self.kernel.get_execution_limits(child_id)
                if action == "submit":
                    self.kernel.submit_child(child, self.lease, envelope)
                else:
                    self.kernel.adopt_child(child_id, self.lease, envelope)
                self.assert_bound_floor(child_id, supplied)
                after = self.kernel.get_execution_limits(child_id)
                for field in ("entry_state", "entry_attempt", "entry_fence", "depth"):
                    self.assertEqual(retained[field], after[field])
                self.assertEqual(before, self.kernel.get(child_id).to_dict())
                self.assertEqual(parent_before, self.kernel.get_execution_limits("parent"))

    def test_post_commit_forward_then_rollback_retains_durable_canonical_floor(self):
        baseline = self.wall[0]
        row, original_window = self.enqueue("post-commit")
        original_sample = self.kernel._sample_budget

        def sample_then_rollback(*args, **options):
            try:
                self.wall[0] = baseline + 4
                return original_sample(*args, **options)
            finally:
                self.wall[0] = baseline

        self.kernel._sample_budget = sample_then_rollback
        try:
            original_window.remaining()
        finally:
            self.kernel._sample_budget = original_sample
        persisted = self.persisted_row(row)
        restored = _RetryWindow(BudgetEnvelope.from_dict(json.loads(persisted["budget_json"])), self.kernel)
        original_remaining, restored_remaining = original_window.remaining(), restored.remaining()
        self.evidence["records"].append({"original_remaining": original_remaining,
            "restored_remaining": restored_remaining, "persisted": persisted,
            "kernel_watermark_advance": self.kernel.current_time() - baseline})
        canonical = BudgetEnvelope.from_dict(self.kernel.get_execution_limits("parent")["envelope"])
        self.assertGreaterEqual(canonical.checkpoint.wall_at, baseline + 4)
        self.assertEqual(canonical.constraints, self.parent_budget.constraints)
        self.assertLess(original_remaining, 7)
        self.assertLessEqual(restored_remaining, original_remaining + .1)
        self.assertEqual(original_window.envelope.constraints, restored.envelope.constraints)
        self.assertEqual("running", self.kernel.get("parent").state)

    def test_submit_replay_cannot_replace_a_confirmed_child_actual_entry_timestamp(self):
        baseline = self.wall[0]
        child_id = "entered-replay"
        child = self.command(child_id)
        supplied = self.parent_budget.derive(source="tool", origin_id="replay-tool", timeout_seconds=10)
        self.kernel.submit_child(child, self.lease, supplied)
        try:
            self.wall[0] = baseline + 2
            child_lease = self.kernel.claim_and_start("actual-child-owner", execution_id=child_id,
                                                    child_pool=True)
            entered = self.kernel.prepare_execution_budget(child_lease).enter_handler(
                30, origin_id="execution:" + child_id, sample=sample_clock(wall_time=self.wall[0]))
            self.kernel.confirm_handler_entry(child_lease, entered)
            before = self.kernel.get(child_id).to_dict()
            limits_before = self.kernel.get_execution_limits(child_id)
            self.kernel.submit_child(child, self.lease, supplied)
            limits_after = self.kernel.get_execution_limits(child_id)
            after = BudgetEnvelope.from_dict(limits_after["envelope"])
            self.assertEqual(entered.started_at, after.started_at)
            self.assertNotEqual(supplied.started_at, after.started_at)
            self.assertEqual(entered.constraints, after.constraints)
            for field in ("entry_state", "entry_attempt", "entry_fence", "depth",
                          "parent_execution_id", "parent_attempt", "parent_fence"):
                self.assertEqual(limits_before[field], limits_after[field])
            self.assertEqual(before, self.kernel.get(child_id).to_dict())
            self.evidence["records"].append({"scope": "public Kernel entry ACK; no handler invoked",
                "before": limits_before, "after": limits_after, "child_lease": child_lease.to_dict()})
        finally:
            self.wall[0] = baseline

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

    def test_both_sidecar_writers_fail_but_fresh_service_keeps_canonical_floor(self):
        row, window = self.enqueue("both-writers")
        self.children.store.attach(row, window)
        baseline = self.wall[0]
        writers = []
        try:
            for path in (self.journal.path, self.facts.path):
                writer = sqlite3.connect(path, timeout=.1)
                writers.append(writer)
                writer.execute("BEGIN IMMEDIATE")
            self.wall[0] = baseline + 4
            with self.assertRaises(Exception) as caught:
                window.remaining()
            self.evidence["records"].append({"original_error": {
                "type": type(caught.exception).__name__, "message": str(caught.exception),
                "sqlite_errorcode": getattr(caught.exception, "sqlite_errorcode", None)},
                "failed_window": window.envelope.to_dict()})
            self.assertTrue("locked" in str(caught.exception) or "budget" in str(caught.exception))
            narrowed = window.envelope.view(sample=window.envelope.checkpoint).remaining_work_seconds
        finally:
            self.wall[0] = baseline
            for writer in reversed(writers):
                try:
                    writer.rollback()
                finally:
                    writer.close()
        service = ChildService(SimpleNamespace(kernel=self.kernel), self.journal)
        restored_row = service.store.request(row["parent_execution_id"], row["request_id"])
        restored = _RetryWindow(BudgetEnvelope.from_dict(json.loads(restored_row["budget_json"])), self.kernel)
        service.store.attach(restored_row, restored)
        self.assertLessEqual(restored.remaining(), narrowed)
        self.assertEqual(window.envelope.constraints, restored.envelope.constraints)
        canonical = BudgetEnvelope.from_dict(self.kernel.get_execution_limits("parent")["envelope"])
        self.assertEqual(self.parent_budget.constraints, canonical.constraints)
        self.evidence["records"].append({"fresh_remaining": restored.remaining(),
            "failed_remaining": narrowed, "canonical": canonical.to_dict()})

    def test_failed_kernel_acknowledgement_fences_fresh_recovery_and_child_admission(self):
        row, window = self.enqueue("all-writers")
        baseline = self.wall[0]
        begin = self.kernel._begin_budget_sample
        writers = []
        tokens = []

        def arm_and_lock(execution_id, **options):
            token = begin(execution_id, **options)
            tokens.append(token)
            # These are genuine independent write locks, taken after the
            # durable guard commit and before the authoritative clock sample.
            for path in (self.kernel.db_path, self.journal.path, self.facts.path):
                writer = sqlite3.connect(path, timeout=.1)
                writers.append(writer)
                writer.execute("BEGIN IMMEDIATE")
            self.wall[0] = baseline + 4
            return token

        self.kernel._begin_budget_sample = arm_and_lock
        try:
            with self.assertRaises((sqlite3.OperationalError, TimeoutError)) as caught:
                window.remaining()
            if isinstance(caught.exception, TimeoutError):
                self.assertEqual(str(caught.exception), "Kernel control admission budget elapsed")
            self.assertEqual(tokens[0], caught.exception.budget_sample_token)
            self.assertIsNotNone(caught.exception.budget_sample_envelope)
            self.assertTrue(all(writer.in_transaction for writer in writers))
            self.evidence["records"].append({"raw_error": str(caught.exception),
                "sqlite_errorcode": getattr(caught.exception, "sqlite_errorcode", None), "token": tokens[0]})
        finally:
            self.kernel._begin_budget_sample = begin
            self.wall[0] = baseline
            for writer in reversed(writers):
                try:
                    writer.rollback()
                finally:
                    writer.close()
        with SQLiteKernel(self.kernel.db_path, now=lambda: self.wall[0]) as fresh:
            stored = self.persisted_row(row)
            restored = BudgetEnvelope.from_dict(json.loads(stored["budget_json"]))
            sample = sample_clock(wall_time=restored.checkpoint.wall_at)
            self.evidence["records"].append({"scenario": "fresh_guard_admission_before_retry_window",
                "stored_budget": restored.to_dict(), "pure_stored_view": restored.view(sample=sample).to_dict(),
                "original_wait_deadline": window.deadline, "observed_monotonic": time.monotonic(),
                "pending_guard_rows": [dict(value) for value in fresh._connection.execute(
                    "SELECT * FROM kernel_budget_samples WHERE execution_id='parent'")],
                "retained_captured_budget": window.envelope.to_dict(),
                "original_live_owner_pending": self.kernel._budget_sample_status("parent")})
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved"):
                try:
                    recovered = _RetryWindow(restored, fresh)
                except BaseException as error:
                    self.evidence["records"].append({"fresh_window_error": {
                        "type": type(error).__name__, "message": str(error)}})
                    raise
                else:
                    with recovered.project():
                        remaining = recovered.remaining()
                    self.evidence["records"].append({"fresh_window_returned": {
                        "pure_remaining": remaining, "deadline": recovered.deadline,
                        "budget": recovered.envelope.to_dict()}})
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved"):
                fresh.submit_child(self.command(row["child_execution_id"]), self.lease, window.envelope)
            self.assertEqual("running", fresh.get("parent").state)
            self.assertEqual(self.lease.to_dict(), fresh.get("parent").lease.to_dict())
            self.assertEqual([], fresh._connection.execute(
                "SELECT execution_id FROM kernel_executions WHERE execution_id=?", (row["child_execution_id"],)).fetchall())
            self.assertEqual(tokens, [value[0] for value in fresh._connection.execute(
                "SELECT token FROM kernel_budget_samples WHERE execution_id='parent'")])
        self.assertEqual(self.parent_budget.constraints, BudgetEnvelope.from_dict(
            self.kernel.get_execution_limits("parent")["envelope"]).constraints)

    def test_failed_write_admission_reads_committed_floor_without_sampling_or_budget_regain(self):
        original = self.parent_budget.derive(source="tool", origin_id="writer-held-reconstruction", timeout_seconds=10)
        baseline = self.wall[0]
        try:
            self.wall[0] = baseline + 4
            canonical = self.kernel._sample_budget("parent", self.parent_budget)
        finally:
            self.wall[0] = baseline
        with SQLiteKernel(self.kernel.db_path, now=lambda: self.wall[0]) as fresh:
            writer = sqlite3.connect(fresh.db_path, isolation_level=None)
            statements = []
            fresh._connection.set_trace_callback(statements.append)
            try:
                writer.execute("BEGIN IMMEDIATE")
                began = time.monotonic()
                restored = _RetryWindow(original, fresh)
                with restored.project():
                    remaining = restored.remaining()
                expected = original.with_clock_floor(canonical.checkpoint)
                expected = expected.view(sample=restored.envelope.checkpoint)
                self.assertGreater(remaining, 0)
                self.assertLessEqual(remaining, expected.remaining_work_seconds)
                self.assertEqual(original.constraints, restored.envelope.constraints)
                self.assertEqual(original.started_at, restored.envelope.started_at)
                self.assertTrue(writer.in_transaction)
                self.assertFalse(fresh._connection.in_transaction)
                self.assertLess(time.monotonic() - began, .5)
                self.assertEqual([], fresh._connection.execute("SELECT token FROM kernel_budget_samples").fetchall())
                self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                    for sql in statements), statements)
                self.evidence["records"].append({"scenario": "writer_held_readonly_floor_reconstruction",
                    "original_budget": original.to_dict(), "committed_floor": canonical.to_dict(),
                    "restored_budget": restored.envelope.to_dict(), "remaining": remaining,
                    "expected_maximum_remaining": expected.remaining_work_seconds,
                    "readonly_statements": statements})
            finally:
                fresh._connection.set_trace_callback(None)
                writer.rollback()
                writer.close()

    def test_readonly_floor_refuses_an_existing_snapshot_across_foreign_ack(self):
        with SQLiteKernel(self.kernel.db_path, now=lambda: self.wall[0]) as reader:
            reader._connection.execute("BEGIN")
            previous = reader._connection.execute(
                "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id='parent'").fetchone()[0]
            baseline = self.wall[0]
            try:
                self.wall[0] = baseline + 4
                published = self.kernel._sample_budget("parent", self.parent_budget)
            finally:
                self.wall[0] = baseline
            try:
                with self.assertRaisesRegex(StorageIsolationError, "idle connection"):
                    reader._read_budget_floor("parent")
                self.assertTrue(reader._connection.in_transaction)
                self.assertEqual(previous, reader._connection.execute(
                    "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id='parent'").fetchone()[0])
            finally:
                reader._connection.rollback()
            fresh = reader._read_budget_floor("parent")
            self.assertEqual(published.checkpoint, fresh)
            self.assertFalse(reader._connection.in_transaction)
            self.evidence["records"].append({"scenario": "stale_external_snapshot_rejected",
                "old_envelope": json.loads(previous), "published_floor": published.to_dict(),
                "fresh_floor": fresh.to_dict()})

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
        attachment = {"first_page": page, "stricter_next_page_note": last,
            "original_window": window.envelope.to_dict(), "restored_window": restored.envelope.to_dict(),
            "original_native_deadline": window.deadline, "restored_native_deadline": restored.deadline,
            "began": time.monotonic()}
        self.evidence["records"].append(attachment)
        try:
            with self.assertRaises(BudgetClockUnknownError) as caught:
                reopened.store.attach(row, restored)
            attachment['refusal'] = {'type': type(caught.exception).__name__, 'message': str(caught.exception)}
        except Exception as error:
            attachment['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            attachment['returned'] = time.monotonic()
            attachment['final_native_deadline'] = restored.deadline
            attachment['final_window'] = restored.envelope.to_dict()


if __name__ == "__main__":
    unittest.main()
