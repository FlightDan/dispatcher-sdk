"""Factual completion clocks survive real writer locks without new authority."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, sample_clock
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture
from dispatcher_sdk.execution_kernel import completion_clock as completion_clock_module
from dispatcher_sdk.execution_kernel.completion_clock import capture_completion_time
from dispatcher_sdk.execution_kernel.completion_clock import resolve_completion_time
from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory


class CompletionClockTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-completion-clock-")
        self.wall = [time.time()]
        self.wall_calls = 0

        def now():
            self.wall_calls += 1
            return self.wall[0]

        self.kernel = SQLiteKernel(self.root / "kernel.sqlite3", now=now)
        self.addCleanup(self.kernel.close)
        self.command = ExecutionCommandV2("original", "original", "clock-proof", "clock-proof",
            None, "work", 1, RetryPolicy(), 10, {})
        self.kernel.submit(self.command)
        self.lease = self.kernel.claim_and_start("owner", execution_id="original")
        envelope = self.kernel.prepare_execution_budget(self.lease).enter_handler(
            10, origin_id="execution:original")
        self.envelope = self.kernel.confirm_handler_entry(self.lease, envelope)
        self.context = SimpleNamespace(_kernel=self.kernel, lease=self.lease,
            _budget_envelope=self.envelope)
        self.evidence = {"test": self.id(), "records": []}

    def tearDown(self):
        path = self.root / "evidence.json"
        path.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
        print("completion_clock_evidence=" + str(path), flush=True)

    def floor(self):
        return self.kernel._connection.execute(
            "SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()[0]

    def owned_capture(self, context=None, *, captured=True):
        context = self.context if context is None else context
        owner = _KernelBudgetCapture(self.kernel, context.lease.execution_id)
        token = self.kernel._begin_budget_sample(context.lease.execution_id, _owner=owner)
        # Execute the real SDK protocol's captured callback with an actual
        # native sample; no acknowledgement or business is synthesized.
        original_wall = self.wall[0]
        self.wall[0] += 1
        try:
            envelope = context._budget_envelope.recheckpoint(sample=sample_clock(
                wall_time=self.kernel._wall_time()))
        finally:
            self.wall[0] = original_wall
        if captured:
            owner._captured(token, envelope)
        context._budget_capture = owner
        return owner, token, envelope

    def finish_owned_capture(self, owner, token, envelope):
        if owner._pending is not None and owner._pending[1] is None:
            owner._captured(token, envelope)
        owner.finish_pending(envelope, timeout_seconds=.1)

    def rollback_journal_writer(self):
        # This real storage-topology fixture permits only the mode change;
        # production capture neither changes journal mode nor installs DML.
        connection = self.kernel._connection
        connection.set_authorizer(lambda *args: sqlite3.SQLITE_OK)
        try:
            self.assertEqual("delete", connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0])
        finally:
            connection.set_authorizer(self.kernel._authorizer)
        writer = sqlite3.connect(self.kernel.db_path, timeout=0, check_same_thread=False)
        writer.execute("BEGIN EXCLUSIVE")
        self.addCleanup(writer.close)
        self.addCleanup(writer.rollback)
        return writer

    def test_actual_shared_kernel_lock_does_not_block_original_return_snapshot(self):
        before = self.floor()
        results, errors = [], []
        done = threading.Event()
        calls_before = self.wall_calls

        def capture():
            try:
                results.append(capture_completion_time(self.context))
            except BaseException as error:
                errors.append(repr(error))
            finally:
                done.set()

        with self.kernel._lock:
            worker = threading.Thread(target=capture)
            worker.start()
            self.assertTrue(done.wait(.3), "capture waited on the held Kernel RLock")
        worker.join(1)
        self.assertEqual([], errors)
        self.assertEqual(1, len(results))
        self.assertGreaterEqual(results[0], before)
        self.assertEqual(1, self.wall_calls - calls_before)
        self.assertEqual(before, self.floor())
        self.evidence["records"].append({"held_kernel_lock": True, "completed_at": results[0],
            "watermark_before": before, "watermark_after": self.floor(), "wall_samples": 1})

    def test_actual_committed_expiry_floor_survives_wall_rollback_without_mutation(self):
        original_wall = self.wall[0]
        self.wall[0] = self.lease.expires_at + 1
        self.kernel.submit(replace(self.command, execution_id="clock-witness", idempotency_key="clock-witness"))
        committed = self.floor()
        self.wall[0] = original_wall
        completed_at = capture_completion_time(self.context)
        self.assertGreater(completed_at, self.lease.expires_at)
        self.assertGreaterEqual(completed_at, committed)
        self.assertEqual(committed, self.floor())
        self.evidence["records"].append({"committed_watermark": committed,
            "rolled_back_wall": original_wall, "completed_at": completed_at,
            "original_lease_expiry": self.lease.expires_at})

    def test_actual_pending_original_sample_remains_unknown_and_unchanged(self):
        token = self.kernel._begin_budget_sample("original")
        before = self.floor()
        try:
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved:sampling"):
                capture_completion_time(self.context)
            row = self.kernel._connection.execute(
                "SELECT token,reason FROM kernel_budget_samples WHERE execution_id='original'").fetchone()
            self.assertEqual((token, "sampling"), tuple(row))
            self.assertEqual(before, self.floor())
        finally:
            self.kernel._finish_budget_sample(token, "original", self.envelope)

    def test_guard_refusal_retains_original_proof_only_after_physical_reader_close(self):
        from dispatcher_sdk import storage_connection

        token = self.kernel._begin_budget_sample("original")
        factory = completion_clock_module._connect_readonly
        physical_close = storage_connection._ParticipatingConnection.close
        readers, closed = [], []
        refuse_close = [False]

        def opened(*args, **kwargs):
            reader = factory(*args, **kwargs)
            readers.append(reader)
            return reader

        def close(reader):
            if reader in readers and refuse_close[0]:
                raise OSError("original reader physical close failed")
            physical_close(reader)
            if reader in readers:
                closed.append(reader)

        try:
            with patch.object(completion_clock_module, "_connect_readonly", side_effect=opened), \
                    patch.object(storage_connection._ParticipatingConnection, "close", close):
                before = self.wall_calls
                with self.assertRaises(BudgetClockUnknownError) as successful_close:
                    capture_completion_time(self.context)
                proof = successful_close.exception._completion_clock_proof
                self.assertEqual(self.lease.to_dict(), proof["lease"])
                self.assertEqual(self.envelope.to_dict(), proof["budget_envelope"])
                self.assertEqual(self.wall[0], proof["sample"]["wall_at"])
                self.assertEqual(1, self.wall_calls - before)
                self.assertEqual(readers, closed)
                with self.assertRaises(sqlite3.ProgrammingError):
                    readers[0].execute("SELECT 1")

                refuse_close[0] = True
                with self.assertRaises(BudgetClockUnknownError) as failed_close:
                    capture_completion_time(self.context)
                self.assertIsInstance(failed_close.exception.__cause__, OSError)
                self.assertFalse(hasattr(failed_close.exception, "_completion_clock_proof"))
                self.assertEqual(1, readers[-1].execute("SELECT 1").fetchone()[0])
                self.evidence["records"].append({"retained_proof": proof,
                    "failed_close_error": str(failed_close.exception.__cause__),
                    "failed_close_published_proof": False})
        finally:
            for reader in readers:
                physical_close(reader)
            self.kernel._finish_budget_sample(token, "original", self.envelope)

    def test_retained_proof_waits_for_real_foreign_ack_without_another_wall_sample(self):
        token = self.kernel._begin_budget_sample("original")
        original_token = token
        context = HandlerContext(self.command, self.lease,
            HandlerEffects(self.kernel, self.lease, lambda: True), budget_envelope=self.envelope)
        self.addCleanup(context.close)
        try:
            with self.assertRaises(BudgetClockUnknownError) as original:
                capture_completion_time(context)
            proof = original.exception._completion_clock_proof
            before = json.loads(json.dumps(proof))
            context._drain_completion_readers(time.monotonic() + 1)
            with patch.object(completion_clock_module, "_connect_readonly",
                              side_effect=AssertionError("invalid proof opened storage")):
                with self.assertRaises(StorageIsolationError):
                    resolve_completion_time(self.kernel, replace(self.lease, lease_id="another-lease"),
                        proof, context, deadline=time.monotonic() + .1)
                incompatible = json.loads(json.dumps(proof))
                incompatible["sample"]["domain_id"] = "another-original-domain"
                with self.assertRaises(BudgetClockUnknownError):
                    resolve_completion_time(self.kernel, self.lease, incompatible, context,
                        deadline=time.monotonic() + .1)
            with patch.object(self.kernel, "_wall_time", side_effect=AssertionError("recovery sampled new wall time")):
                with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved:sampling"):
                    resolve_completion_time(self.kernel, self.lease, proof, context,
                        deadline=time.monotonic() + .1)
            self.assertEqual(token, self.kernel._connection.execute(
                "SELECT token FROM kernel_budget_samples").fetchone()[0])
            self.assertEqual(before, proof)
            self.kernel._finish_budget_sample(token, "original", self.envelope)
            token = None
            context._drain_completion_readers(time.monotonic() + 1)
            with patch.object(self.kernel, "_wall_time", side_effect=AssertionError("recovery sampled new wall time")):
                completed_at, captured = resolve_completion_time(self.kernel, self.lease, proof, context,
                    deadline=time.monotonic() + .1)
            self.assertGreaterEqual(completed_at, proof["sample"]["wall_at"])
            self.assertEqual(proof["sample"]["elapsed_at"], captured.checkpoint.elapsed_at)
            self.assertEqual(before, proof)
            self.evidence["records"].append({"original_proof": proof,
                "foreign_token": original_token, "resolved_at": completed_at,
                "recovery_wall_samples": 0})
        finally:
            context._drain_completion_readers(time.monotonic() + 1)
            if token is not None:
                self.kernel._finish_budget_sample(token, "original", self.envelope)

    def test_actual_own_captured_failed_ack_has_factual_time_without_discharging_guard(self):
        owner, token, captured = self.owned_capture()
        writer = sqlite3.connect(self.kernel.db_path, timeout=0)
        writer.execute("BEGIN IMMEDIATE")
        try:
            with self.assertRaises(sqlite3.OperationalError):
                owner.finish_pending(captured, timeout_seconds=.05)
            before = self.floor()
            calls_before = self.wall_calls
            pending = owner._pending
            statements = []
            self.kernel._connection.set_trace_callback(statements.append)
            try:
                completed_at = capture_completion_time(self.context)
            finally:
                self.kernel._connection.set_trace_callback(None)
            self.assertEqual([], statements, "factual completion touched the live Kernel writer")
            self.assertEqual(1, self.wall_calls-calls_before)
            self.assertGreaterEqual(completed_at, captured.checkpoint.wall_at)
            self.assertIs(pending, owner._pending)
            self.assertIs(owner, self.kernel._budget_sample_owners[token])
            self.assertEqual(before, self.floor())
            self.assertEqual(token, self.kernel._connection.execute(
                "SELECT token FROM kernel_budget_samples").fetchone()[0])
            self.evidence["records"].append({"original_owned_token": token,
                "captured": captured.to_dict(), "completed_at": completed_at,
                "guard_still_pending": True, "watermark_unchanged": before})
        finally:
            writer.rollback()
            writer.close()
            self.finish_owned_capture(owner, token, captured)

    def test_actual_own_armed_uncaptured_guard_cannot_supply_return_time(self):
        owner, token, captured = self.owned_capture(captured=False)
        try:
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved:sampling"):
                capture_completion_time(self.context)
            self.assertEqual((token, None), owner._pending)
            self.assertIs(owner, self.kernel._budget_sample_owners[token])
        finally:
            self.finish_owned_capture(owner, token, captured)

    def test_actual_unregistered_captured_owner_does_not_exempt_original_guard(self):
        token = self.kernel._begin_budget_sample("original")
        owner = _KernelBudgetCapture(self.kernel, "original")
        owner._captured(token, self.envelope)
        self.context._budget_capture = owner
        try:
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved:sampling"):
                capture_completion_time(self.context)
            self.assertNotIn(token, self.kernel._budget_sample_owners)
        finally:
            self.kernel._finish_budget_sample(token, "original", self.envelope)

    def test_actual_extra_foreign_guard_prevents_own_captured_exemption(self):
        owner, token, captured = self.owned_capture()
        foreign = "foreign-extra-token"
        with sqlite3.connect(self.kernel.db_path, timeout=0) as writer:
            writer.execute("INSERT INTO kernel_budget_samples(token,execution_id,reason) VALUES(?,?,'sampling')",
                (foreign, "original"))
        try:
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved:sampling"):
                capture_completion_time(self.context)
            self.assertEqual({token, foreign}, {row[0] for row in self.kernel._connection.execute(
                "SELECT token FROM kernel_budget_samples")})
        finally:
            self.kernel._finish_budget_sample(foreign, "original", self.envelope)
            self.finish_owned_capture(owner, token, captured)

    def test_actual_original_parent_sample_fences_only_matching_ancestry(self):
        child = replace(self.command, execution_id="child", idempotency_key="child", causation_id="original")
        self.kernel.submit_child(child, self.lease,
            self.envelope.derive(source="tool", origin_id="child-call", timeout_seconds=5))
        lease = self.kernel.claim_and_start("child-owner", execution_id="child", child_pool=True)
        envelope = self.kernel.prepare_execution_budget(lease).enter_handler(
            child.timeout_seconds, origin_id="execution:child")
        envelope = self.kernel.confirm_handler_entry(lease, envelope)
        context = SimpleNamespace(_kernel=self.kernel, lease=lease, _budget_envelope=envelope)
        token = self.kernel._begin_budget_sample("original")
        try:
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved:sampling"):
                capture_completion_time(context)
        finally:
            self.kernel._finish_budget_sample(token, "original", self.envelope)

    def test_actual_parent_guard_remains_unknown_with_child_own_captured_fact(self):
        child = replace(self.command, execution_id="child", idempotency_key="child", causation_id="original")
        self.kernel.submit_child(child, self.lease,
            self.envelope.derive(source="tool", origin_id="child-call", timeout_seconds=5))
        lease = self.kernel.claim_and_start("child-owner", execution_id="child", child_pool=True)
        envelope = self.kernel.prepare_execution_budget(lease).enter_handler(
            child.timeout_seconds, origin_id="execution:child")
        envelope = self.kernel.confirm_handler_entry(lease, envelope)
        context = SimpleNamespace(_kernel=self.kernel, lease=lease, _budget_envelope=envelope)
        owner, token, captured = self.owned_capture(context)
        parent_token = self.kernel._begin_budget_sample("original")
        try:
            with self.assertRaisesRegex(BudgetClockUnknownError, "budget_clock_sample_unresolved:sampling"):
                capture_completion_time(context)
            self.assertEqual({token, parent_token}, {row[0] for row in self.kernel._connection.execute(
                "SELECT token FROM kernel_budget_samples")})
        finally:
            self.kernel._finish_budget_sample(parent_token, "original", self.envelope)
            self.finish_owned_capture(owner, token, captured)

    def test_actual_existing_guard_ack_within_original_window_reuses_return_sample(self):
        token = self.kernel._begin_budget_sample("original")
        calls_before = self.wall_calls
        errors = []
        refused = threading.Event()
        record = {"existing_guard_ack": token, "original_capture_timeout": .1,
            "ack_trigger": "actual_reader_guard_refusal", "read_refusals": 0}
        self.evidence["records"].append(record)
        read_floor = completion_clock_module._read_floor

        def raw(error):
            return {"type": type(error).__name__, "message": str(error),
                "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                "sqlite_errorname": getattr(error, "sqlite_errorname", None)}

        def inspected(*args, **kwargs):
            try:
                return read_floor(*args, **kwargs)
            except BudgetClockUnknownError as error:
                record["read_refusals"] += 1
                if "first_refusal_at" not in record:
                    record["first_refusal_at"] = time.monotonic()
                    record["first_refusal_error"] = raw(error)
                refused.set()
                raise

        def acknowledge():
            record["owner_started_at"] = time.monotonic()
            if not refused.wait(.1):
                errors.append("original reader never observed the actual guard")
                return
            record["ack_started_at"] = time.monotonic()
            try:
                self.kernel._finish_budget_sample(token, "original", self.envelope)
                record["ack_committed"] = True
            except BaseException as error:
                errors.append(repr(error))
                record["ack_error"] = raw(error)
            finally:
                # Successful return follows the actual original COMMIT.
                record["ack_finished_at"] = time.monotonic()

        owner = threading.Thread(target=acknowledge)
        owner.start()
        try:
            record["capture_started_at"] = time.monotonic()
            with patch.object(completion_clock_module, "_read_floor", side_effect=inspected):
                completed_at = capture_completion_time(self.context)
            record["completed_at"] = completed_at
        except BaseException as error:
            record["capture_error"] = raw(error)
            raise
        finally:
            record["capture_finished_at"] = time.monotonic()
            owner.join(1)
            record["owner_alive_after_original_join"] = owner.is_alive()
            record["wall_samples"] = self.wall_calls - calls_before
            pending = self.kernel._connection.execute(
                "SELECT token FROM kernel_budget_samples WHERE token=?", (token,)).fetchone()
            if pending is not None:
                record["cleanup_ack_started_at"] = time.monotonic()
                try:
                    self.kernel._finish_budget_sample(token, "original", self.envelope)
                except BaseException as error:
                    record["cleanup_ack_error"] = raw(error)
                    raise
                finally:
                    record["cleanup_ack_finished_at"] = time.monotonic()
        self.assertEqual([], errors)
        self.assertGreater(record["read_refusals"], 0)
        self.assertTrue(record["ack_committed"])
        self.assertLessEqual(record["first_refusal_at"], record["ack_started_at"])
        self.assertEqual(1, self.wall_calls - calls_before)
        self.assertGreaterEqual(completed_at, self.envelope.checkpoint.wall_at)

    def test_actual_rollback_denial_preserves_original_guard_error_and_stops_retry(self):
        token = self.kernel._begin_budget_sample("original")
        reader_factory = completion_clock_module._connect_readonly
        read_floor = completion_clock_module._read_floor
        refusals = []

        def reader(*args, **kwargs):
            connection = reader_factory(*args, **kwargs)
            connection.set_authorizer(lambda action, first, second, database, source:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION and first == "ROLLBACK"
                else sqlite3.SQLITE_OK)
            return connection

        def record_refusal(*args, **kwargs):
            try:
                return read_floor(*args, **kwargs)
            except BudgetClockUnknownError as error:
                refusals.append(error)
                raise

        try:
            with patch.object(completion_clock_module, "_connect_readonly", side_effect=reader), \
                    patch.object(completion_clock_module, "_read_floor", side_effect=record_refusal):
                with self.assertRaises(BudgetClockUnknownError) as caught:
                    capture_completion_time(self.context)
            self.assertEqual(1, len(refusals))
            self.assertIs(refusals[0], caught.exception)
            self.assertIsInstance(caught.exception.__cause__, sqlite3.DatabaseError)
            self.assertEqual("not authorized", str(caught.exception.__cause__))
        finally:
            self.kernel._finish_budget_sample(token, "original", self.envelope)

    def test_actual_reader_unavailable_keeps_raw_busy_and_original_point_one_window(self):
        writer = self.rollback_journal_writer()
        calls_before = self.wall_calls
        began = time.monotonic()
        with self.assertRaises(sqlite3.OperationalError) as caught:
            capture_completion_time(self.context)
        elapsed = time.monotonic() - began
        self.assertEqual("database is locked", str(caught.exception))
        self.assertGreaterEqual(elapsed, .08)
        self.assertLess(elapsed, .3)
        self.assertEqual(1, self.wall_calls - calls_before)
        proof = caught.exception._completion_clock_proof
        writer.rollback()
        context = HandlerContext(self.command, self.lease,
            HandlerEffects(self.kernel, self.lease, lambda: True), budget_envelope=self.envelope)
        self.addCleanup(context.close)
        with patch.object(self.kernel, "_wall_time", side_effect=AssertionError("recovery sampled new wall time")):
            completed_at, captured = resolve_completion_time(self.kernel, self.lease,
                proof, context, deadline=time.monotonic() + .1)
        self.assertGreaterEqual(completed_at, proof["sample"]["wall_at"])
        self.assertEqual(proof["sample"]["elapsed_at"], captured.checkpoint.elapsed_at)
        self.evidence["records"].append({"actual_exclusive_writer": True,
            "original_capture_timeout": .1, "elapsed": elapsed,
            "error": type(caught.exception).__name__ + ": " + str(caught.exception),
            "wall_samples": self.wall_calls - calls_before})

    def test_own_sqlite_interrupt_retains_original_sample_only_after_physical_close(self):
        from dispatcher_sdk import storage_connection

        factory = completion_clock_module._connect_readonly
        physical_close = storage_connection._ParticipatingConnection.close
        for fail_close in (False, True):
            with self.subTest(fail_close=fail_close):
                readers, interruptions = [], []

                def opened(*args, **kwargs):
                    reader = factory(*args, **kwargs)
                    readers.append(reader)
                    return reader

                def close(reader):
                    if fail_close and reader in readers:
                        raise OSError("interrupted reader physical close failed")
                    physical_close(reader)

                def inspected(connection, lease, budget, **kwargs):
                    try:
                        connection.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL "
                            "SELECT x+1 FROM n) SELECT sum(x) FROM n").fetchone()
                    except sqlite3.OperationalError as error:
                        interruptions.append((error, budget.stopped_reason))
                        raise

                before = self.wall_calls
                try:
                    with patch.object(completion_clock_module, "_connect_readonly", side_effect=opened), \
                            patch.object(completion_clock_module, "_read_floor", side_effect=inspected), \
                            patch.object(storage_connection._ParticipatingConnection, "close", close):
                        with self.assertRaises(sqlite3.OperationalError) as caught:
                            capture_completion_time(self.context)
                    self.assertEqual(1, len(interruptions))
                    self.assertIs(interruptions[0][0], caught.exception)
                    self.assertEqual("interrupted", str(caught.exception))
                    self.assertEqual("timeout", interruptions[0][1])
                    self.assertEqual(1, self.wall_calls - before)
                    if fail_close:
                        self.assertIsInstance(caught.exception.__cause__, OSError)
                        self.assertFalse(hasattr(caught.exception, "_completion_clock_proof"))
                        self.assertEqual(1, readers[0].execute("SELECT 1").fetchone()[0])
                    else:
                        with self.assertRaises(sqlite3.ProgrammingError):
                            readers[0].execute("SELECT 1")
                        proof = caught.exception._completion_clock_proof
                        context = HandlerContext(self.command, self.lease,
                            HandlerEffects(self.kernel, self.lease, lambda: True),
                            budget_envelope=self.envelope)
                        self.addCleanup(context.close)
                        with patch.object(self.kernel, "_wall_time",
                                side_effect=AssertionError("recovery sampled new wall time")):
                            completed_at, captured = resolve_completion_time(self.kernel, self.lease,
                                proof, context, deadline=time.monotonic() + .1)
                        self.assertGreaterEqual(completed_at, proof["sample"]["wall_at"])
                        self.assertEqual(proof["sample"]["elapsed_at"], captured.checkpoint.elapsed_at)
                    self.evidence["records"].append({"own_progress_interrupt": str(caught.exception),
                        "sqlite_errorcode": getattr(caught.exception, "sqlite_errorcode", None),
                        "progress_stop_reason": interruptions[0][1], "physical_close_failed": fail_close,
                        "proof_retained": hasattr(caught.exception, "_completion_clock_proof")})
                finally:
                    for reader in readers:
                        physical_close(reader)

    def test_unrelated_sqlite_interrupt_does_not_publish_original_sample(self):
        interruptions = []

        def inspected(connection, lease, budget, **kwargs):
            connection.set_progress_handler(lambda: 1, 1)
            try:
                connection.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL "
                    "SELECT x+1 FROM n) SELECT sum(x) FROM n").fetchone()
            except sqlite3.OperationalError as error:
                interruptions.append((error, budget.stopped_reason))
                raise

        with patch.object(completion_clock_module, "_read_floor", side_effect=inspected):
            with self.assertRaises(sqlite3.OperationalError) as caught:
                capture_completion_time(self.context)
        self.assertIs(interruptions[0][0], caught.exception)
        self.assertEqual("interrupted", str(caught.exception))
        self.assertIsNone(interruptions[0][1])
        self.assertFalse(hasattr(caught.exception, "_completion_clock_proof"))
        self.evidence["records"].append({"unrelated_interrupt": str(caught.exception),
            "progress_stop_reason": interruptions[0][1], "proof_retained": False})

    def test_own_expiry_before_open_and_after_close_retains_original_sample(self):
        from dispatcher_sdk._inspection import InspectionBudgetExceeded
        from dispatcher_sdk import storage_connection

        original_read = completion_clock_module._read_completion_time
        physical_close = storage_connection._ParticipatingConnection.close
        for phase in ("before-open", "after-close"):
            with self.subTest(phase=phase):
                budgets, readers = [], []
                factory = completion_clock_module._connect_readonly

                def expire(budget):
                    while not budget.expired():
                        time.sleep(.001)

                def read(kernel, lease, envelope, sample, budget, owner, **kwargs):
                    budgets.append(budget)
                    if phase == "before-open":
                        expire(budget)
                    return original_read(kernel, lease, envelope, sample, budget, owner, **kwargs)

                def opened(*args, **kwargs):
                    reader = factory(*args, **kwargs)
                    readers.append(reader)
                    return reader

                def close(reader):
                    physical_close(reader)
                    if reader in readers and phase == "after-close":
                        expire(budgets[0])

                with patch.object(completion_clock_module, "_read_completion_time", side_effect=read), \
                        patch.object(completion_clock_module, "_connect_readonly", side_effect=opened), \
                        patch.object(storage_connection._ParticipatingConnection, "close", close):
                    with self.assertRaises(InspectionBudgetExceeded) as caught:
                        capture_completion_time(self.context)
                proof = caught.exception._completion_clock_proof
                self.assertEqual("timeout", budgets[0].stopped_reason)
                self.assertEqual(0 if phase == "before-open" else 1, len(readers))
                if readers:
                    with self.assertRaises(sqlite3.ProgrammingError):
                        readers[0].execute("SELECT 1")
                self.assertEqual(self.lease.to_dict(), proof["lease"])
                self.evidence["records"].append({"own_expiry_phase": phase,
                    "original_error": str(caught.exception), "proof_retained": True})

    def test_actual_progress_timeout_preserves_original_guard_refusal(self):
        token = self.kernel._begin_budget_sample("original")
        read_floor = completion_clock_module._read_floor
        refusals, interruptions = [], []

        def inspected(connection, lease, budget, **kwargs):
            if not refusals:
                try:
                    return read_floor(connection, lease, budget, **kwargs)
                except BudgetClockUnknownError as error:
                    refusals.append(error)
                    raise
            try:
                # The installed real SQLite progress handler stops this
                # unbounded read at the same original control deadline.
                connection.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL "
                    "SELECT x+1 FROM n) SELECT sum(x) FROM n").fetchone()
            except sqlite3.OperationalError as error:
                interruptions.append((error, budget.stopped_reason))
                raise

        try:
            with patch.object(completion_clock_module, "_read_floor", side_effect=inspected):
                with self.assertRaises(BudgetClockUnknownError) as caught:
                    capture_completion_time(self.context)
            self.assertIs(refusals[0], caught.exception)
            self.assertEqual(1, len(interruptions))
            self.assertEqual("interrupted", str(interruptions[0][0]))
            self.assertEqual("timeout", interruptions[0][1])
            self.evidence["records"].append({"original_refusal": str(caught.exception),
                "sqlite_interrupt": str(interruptions[0][0]),
                "progress_stop_reason": interruptions[0][1]})
        finally:
            self.kernel._finish_budget_sample(token, "original", self.envelope)

    def test_expired_window_does_not_replace_unrelated_sqlite_error(self):
        token = self.kernel._begin_budget_sample("original")
        read_floor = completion_clock_module._read_floor
        refusals, permanent_errors = [], []

        def inspected(connection, lease, budget, **kwargs):
            if not refusals:
                try:
                    return read_floor(connection, lease, budget, **kwargs)
                except BudgetClockUnknownError as error:
                    refusals.append(error)
                    raise
            # A deadline observed outside the progress callback must not
            # convert an actual permanent SQL error into the earlier guard.
            while not budget.expired():
                time.sleep(.001)
            connection.set_progress_handler(None, 0)
            try:
                connection.execute("SELECT * FROM absent_completion_table")
            except sqlite3.OperationalError as error:
                permanent_errors.append(error)
                raise

        try:
            with patch.object(completion_clock_module, "_read_floor", side_effect=inspected):
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    capture_completion_time(self.context)
            self.assertIs(permanent_errors[0], caught.exception)
            self.assertEqual("no such table: absent_completion_table", str(caught.exception))
            self.assertFalse(hasattr(caught.exception, "_completion_clock_proof"))
        finally:
            self.kernel._finish_budget_sample(token, "original", self.envelope)

    def test_actual_released_reader_contention_reuses_original_return_sample(self):
        writer = self.rollback_journal_writer()
        original_wall = self.wall[0]
        calls_before = self.wall_calls

        def release():
            time.sleep(.035)
            self.wall[0] = original_wall + 1000
            writer.rollback()

        releaser = threading.Thread(target=release)
        releaser.start()
        try:
            completed_at = capture_completion_time(self.context)
        finally:
            releaser.join(1)
        self.assertEqual(1, self.wall_calls - calls_before)
        self.assertLess(completed_at, original_wall + 1)
        self.evidence["records"].append({"original_wall": original_wall,
            "later_wall": self.wall[0], "completed_at": completed_at, "wall_samples": 1})

    def test_revoked_original_lease_still_has_factual_return_time(self):
        self.kernel.cancel("original", lease=self.lease, reason="actual original cancellation")
        before = self.floor()
        completed_at = capture_completion_time(self.context)
        self.assertGreaterEqual(completed_at, before)
        self.assertEqual("cancelled", self.kernel.get("original").state)
        self.assertEqual(before, self.floor())

    def test_missing_storage_and_incompatible_retained_domain_do_not_fabricate_time(self):
        original_path = self.kernel.db_path
        self.kernel.db_path = str(self.root / "missing.sqlite3")
        try:
            with self.assertRaises(sqlite3.OperationalError):
                capture_completion_time(self.context)
            self.assertFalse(Path(self.kernel.db_path).exists())
        finally:
            self.kernel.db_path = original_path
        self.context._budget_envelope = replace(self.envelope,
            checkpoint=replace(self.envelope.checkpoint, domain_id="another-clock-domain"))
        with self.assertRaisesRegex(BudgetClockUnknownError, "continuity"):
            capture_completion_time(self.context)

    def test_oversized_identity_and_missing_current_schema_are_explicit_unknowns(self):
        self.context.lease = replace(self.lease, execution_id="x"*4097)
        with self.assertRaisesRegex(StorageIsolationError, "oversized"):
            capture_completion_time(self.context)
        self.context.lease = self.lease
        bad = self.root / "unsupported.sqlite3"
        with sqlite3.connect(bad) as connection:
            connection.execute("CREATE TABLE kernel_schema_meta(component,schema_version)")
            connection.execute("INSERT INTO kernel_schema_meta VALUES('execution_kernel',4)")
        original_path = self.kernel.db_path
        self.kernel.db_path = str(bad)
        try:
            with self.assertRaisesRegex(StorageIsolationError, "current Kernel schema"):
                capture_completion_time(self.context)
        finally:
            self.kernel.db_path = original_path

    def test_actual_malformed_watermark_and_cyclic_ancestry_remain_unknown(self):
        with sqlite3.connect(self.kernel.db_path, timeout=0) as writer:
            writer.execute("UPDATE kernel_execution_limits SET parent_execution_id=?,"
                "parent_attempt=?,parent_fence=? WHERE execution_id=?",
                (self.lease.execution_id, self.lease.attempt, self.lease.fence, self.lease.execution_id))
        with self.assertRaisesRegex(BudgetClockUnknownError, "ancestry"):
            capture_completion_time(self.context)
        with sqlite3.connect(self.kernel.db_path, timeout=0) as writer:
            writer.execute("UPDATE kernel_execution_limits SET parent_execution_id=NULL,"
                "parent_attempt=NULL,parent_fence=NULL WHERE execution_id=?", (self.lease.execution_id,))
            writer.execute("PRAGMA ignore_check_constraints=ON")
            writer.execute("UPDATE kernel_clock SET watermark='malformed' WHERE singleton=1")
        with self.assertRaisesRegex(StorageIsolationError, "watermark"):
            capture_completion_time(self.context)

    def test_custom_kernel_preserves_bounded_original_clock_method(self):
        deadlines = []

        class CustomKernel(SQLiteKernel):
            def current_time(inner):
                deadlines.append(inner._control_deadline)
                return 123.0

        kernel = CustomKernel(":memory:")
        try:
            context = SimpleNamespace(_kernel=kernel)
            began = time.monotonic()
            self.assertEqual(123.0, capture_completion_time(context))
            self.assertEqual(1, len(deadlines))
            self.assertGreater(deadlines[0], began)
            self.assertLessEqual(deadlines[0], began + .11)
        finally:
            kernel.close()

    def test_same_sample_conservative_fraction_floor_is_not_rounded_down(self):
        checkpoint = replace(self.envelope.checkpoint, wall_at=float(2**53), elapsed_at=1.)
        self.context._budget_envelope = replace(self.envelope, checkpoint=checkpoint)
        sample = replace(checkpoint, wall_at=self.wall[0], elapsed_at=2.)
        with patch.object(completion_clock_module, "sample_clock", return_value=sample):
            completed_at = capture_completion_time(self.context)
        self.assertEqual(float(2**53 + 2), completed_at)
        self.evidence["records"].append({"retained_floor": checkpoint.to_dict(),
            "fixed_sample": sample.to_dict(), "completed_at": completed_at,
            "exact_floor_integer": 2**53 + 1})

    def test_actual_oversized_sql_scalars_are_rejected_before_python_decoding(self):
        reader_factory = completion_clock_module._connect_readonly

        def bounded_reader(*args, **kwargs):
            connection = reader_factory(*args, **kwargs)

            def decode(value):
                if len(value) > 8192:
                    raise AssertionError("oversized SQL scalar reached Python decoding")
                return value.decode("utf-8")

            connection.text_factory = decode
            return connection

        original_path = self.kernel.db_path
        try:
            for index, (table, field) in enumerate((
                    ("kernel_schema_meta", "schema_version"), ("kernel_clock", "watermark"),
                    ("kernel_executions", "attempt"), ("kernel_executions", "fence"),
                    ("kernel_execution_limits", "parent_attempt"),
                    ("kernel_execution_limits", "parent_fence"))):
                for scalar_type, oversized in (("text", "x"*400000), ("blob", b"x"*400000)):
                    with self.subTest(field=field, scalar_type=scalar_type):
                        path = self.root / ("malformed-"+str(index)+"-"+scalar_type+".sqlite3")
                        with sqlite3.connect(path) as writer:
                            writer.execute("CREATE TABLE kernel_schema_meta(component,schema_version)")
                            writer.execute("INSERT INTO kernel_schema_meta VALUES('execution_kernel',5)")
                            writer.execute("CREATE TABLE kernel_clock(singleton,watermark)")
                            writer.execute("INSERT INTO kernel_clock VALUES(1,?)", (self.floor(),))
                            writer.execute("CREATE TABLE kernel_executions(execution_id,attempt,fence)")
                            writer.execute("INSERT INTO kernel_executions VALUES(?,?,?)",
                                (self.lease.execution_id, self.lease.attempt, self.lease.fence))
                            writer.execute("CREATE TABLE kernel_budget_samples(token,execution_id,reason)")
                            writer.execute("CREATE TABLE kernel_execution_limits(execution_id,"
                                "parent_execution_id,parent_attempt,parent_fence)")
                            writer.execute("INSERT INTO kernel_execution_limits VALUES(?,'parent',1,1)",
                                (self.lease.execution_id,))
                            writer.execute("UPDATE "+table+" SET "+field+"=?", (oversized,))
                        self.kernel.db_path = str(path)
                        with patch.object(completion_clock_module, "_connect_readonly", side_effect=bounded_reader):
                            with self.assertRaises(StorageIsolationError):
                                capture_completion_time(self.context)
                        self.kernel.db_path = original_path
        finally:
            self.kernel.db_path = original_path


if __name__ == "__main__":
    unittest.main()
