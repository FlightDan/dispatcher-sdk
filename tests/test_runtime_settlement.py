"""Original real handler outcomes survive bounded Kernel write contention."""
from pathlib import Path
from contextlib import closing
from dataclasses import replace
import json
import sqlite3
import sys
import threading
import time
import traceback
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import HandlerExecutionError, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel import completion_clock as completion_clock_module
from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects
from tests._acceptance_evidence import retained_directory
from tests._storage_evidence import StorageEvidence


def settlement_success(payload, context):
    with Path(payload["call_log"]).open("a") as stream:
        stream.write(context.command.execution_id + "\n")
    return {"message": "original real success", "payload": payload["value"]}


def settlement_failure(payload, context):
    with Path(payload["call_log"]).open("a") as stream:
        stream.write(context.command.execution_id + "\n")
    raise HandlerExecutionError("original_real_failure", "original handler error",
                                details={"value": payload["value"]})


def settlement_gated_success(payload, context):
    with Path(payload["call_log"]).open("a") as stream:
        stream.write(context.command.execution_id + "\n")
    Path(payload["ready"]).write_text("actual handler entered")
    while not Path(payload["release"]).exists():
        time.sleep(.005)
    return {"message": "actual handler returned while lifecycle was held"}


settlement_success.__execution_kernel_revision__ = "settlement-success-v1"
settlement_failure.__execution_kernel_revision__ = "settlement-failure-v1"
settlement_gated_success.__execution_kernel_revision__ = "settlement-gated-success-v1"


class Clock:
    def __init__(self):
        self.value = time.time()

    def __call__(self):
        return self.value


class RuntimeSettlementTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-runtime-settlement-")
        self.storage_evidence = StorageEvidence(self.root, self)
        self.storage_evidence.start()
        self.addCleanup(self.storage_evidence.stop)
        self.addCleanup(self.storage_evidence.save)

    def tearDown(self):
        self.storage_evidence.save(phase="before_cleanup")

    def open(self, name, *, mode="thread", failure=False, clock=None):
        runtime = Kernel.open_sqlite(self.root / (name + ".sqlite3"),
            {"work": settlement_failure if failure else settlement_success},
            isolation_mode=mode, now=clock, max_thread_workers=1)
        self.addCleanup(runtime.close)
        return runtime

    def run_with_result_writer_locked(self, name, *, mode="thread", failure=False, clock=None,
                                      retry_policy=None):
        """Hold the writer after a real outcome, never replace that outcome."""
        runtime = self.open(name, mode=mode, failure=failure, clock=clock)
        call_log = self.root / (name + "-calls.txt")
        command = runtime.command("work", execution_id=name, idempotency_key=name,
            correlation_id=name, timeout_seconds=5,
            payload={"call_log": str(call_log), "value": 17}, retry_policy=retry_policy)
        runtime.submit(command)
        outcome_ready, writer_held = threading.Event(), threading.Event()
        retained = []
        original = runtime._outcome_result

        def outcome(*args):
            result = original(*args)
            retained.append(result.to_dict())
            outcome_ready.set()
            if not writer_held.wait(3):
                raise AssertionError("test writer was not acquired after real outcome")
            return result

        runtime._outcome_result = outcome
        results, errors = [], []

        def drive():
            try:
                results.append(runtime.run_once(execution_id=name))
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=drive)
        driver.start()
        self.addCleanup(lambda: driver.join(3))
        self.addCleanup(writer_held.set)
        ready = outcome_ready.wait(3)
        if not ready:
            self.storage_evidence.save(phase="outcome_wait_expired",
                checkpoint={"original_wait": 3, "original_outcomes": retained, "driver_errors": [repr(e) for e in errors]})
        self.assertTrue(ready, "real handler did not produce an outcome")
        self.assertEqual(len(call_log.read_text().splitlines()), 1)
        writer = sqlite3.connect(runtime.kernel.db_path, timeout=1)
        self.addCleanup(writer.close)
        writer.execute("BEGIN IMMEDIATE")
        self.addCleanup(writer.rollback)
        writer_held.set()
        driver.join(2)
        self.assertFalse(driver.is_alive(), "result publication waited on the default 30-second writer timeout")
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].state, "running")
        self.assertIsNone(results[0].result)
        obligations = runtime._settlement_journal.inspect(name, timeout_seconds=.5)
        self.assertEqual(len(obligations), 1)
        self.assertEqual(obligations[0]["result"], retained[0])
        self.assertIn(obligations[0]["state"], {"pending", "error"})
        self.assertEqual(obligations[0]["identity"], {
            "execution_id": name, "attempt": results[0].attempt, "fence": results[0].fence})
        observed = runtime.observe(name, timeout=1)
        self.assertIn("settlement_obligations", observed)
        self.assertIn(retained[0]["result_id"], json.dumps(observed["settlement_obligations"]))
        return runtime, writer, call_log, retained[0], obligations[0]

    def recover(self, runtime, name):
        end = time.monotonic() + 3
        reports = []
        while time.monotonic() < end:
            reports.extend(runtime.recover_completions(timeout_seconds=.5))
            current = runtime.kernel.get(name)
            receipt = runtime._settlement_journal.inspect(name, timeout_seconds=.5)
            if current.result is not None and receipt and receipt[0]["state"] == "recorded":
                return current, reports
            time.sleep(.01)
        self.fail((runtime.observe(name), reports))

    def assert_retained(self, runtime, name, original, state):
        records = runtime._settlement_journal.inspect(name, timeout_seconds=.5)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["result"], original)
        self.assertEqual(records[0]["state"], state)

    def stop_maintenance(self, runtime):
        runtime.request_stop()
        if runtime._settlement_thread is not None:
            runtime._settlement_thread.join(1)
            self.assertFalse(runtime._settlement_thread.is_alive())

    def deferred_guarded_handler_outcome(self, name, *, failure=False):
        """Run the actual invocation wrapper, then refuse its original clock read.

        This boundary fixture owns no scheduler thread: only explicit recovery
        can ACK the foreign guard or publish the actual retained handler result.
        """
        clock = Clock()
        runtime = self.open(name, failure=failure, clock=clock)
        calls = self.root / (name + "-calls.txt")
        command = runtime.command("work", execution_id=name, idempotency_key=name,
            correlation_id=name, timeout_seconds=5,
            payload={"call_log": str(calls), "value": 17})
        runtime.submit(command)
        lease = runtime.kernel.claim_and_start("actual-handler-owner", execution_id=name)
        envelope = runtime.kernel.prepare_execution_budget(lease)
        context = HandlerContext(command, lease,
            HandlerEffects(runtime.kernel, lease, lambda: True), budget_envelope=envelope)
        self.addCleanup(context.close)
        outcome = runtime_module.invoke_handler(
            settlement_failure if failure else settlement_success, command, context)
        self.assertEqual("error" if failure else "ok", outcome["kind"])
        self.assertEqual([name], calls.read_text().splitlines())
        token = runtime.kernel._begin_budget_sample(name)
        runtime_module._capture_completion_time(outcome, context)
        self.assertFalse(outcome["completion_time_known"])
        self.assertIn("completion_clock_proof", outcome)
        context._drain_completion_readers(time.monotonic() + 1)
        record = runtime._settlement_journal.record(lease,
            {"kind": "completion_time_unknown", "outcome": outcome},
            evidence={"outcome_kind": outcome["kind"], "budget_envelope": outcome["budget_envelope"]})
        return runtime, clock, command, lease, context.budget_envelope, token, calls, record, context

    def test_later_watermark_resolves_original_sample_as_timeout_with_raw_business_error(self):
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope

        name = "guarded-return-past-work"
        runtime, clock, command, lease, envelope, token, calls, record, _ = self.deferred_guarded_handler_outcome(
            name, failure=True)
        original = record["deferred"]["outcome"]
        proof_before = json.loads(json.dumps(original["completion_clock_proof"]))
        work_deadline = envelope.view(sample=envelope.checkpoint).effective_work_deadline_at
        clock.value = work_deadline + 1
        self.assertLess(clock.value, lease.expires_at)
        runtime.kernel.submit(replace(command, execution_id="later-clock-witness",
            idempotency_key="later-clock-witness"))
        runtime.kernel._finish_budget_sample(token, name, envelope)
        current, reports = self.recover(runtime, name)
        self.assertEqual("timed_out", current.state)
        self.assertGreaterEqual(current.result.completed_at, clock.value)
        raw = current.result.error.details["business_outcome"]
        self.assertEqual("original_real_failure", raw["code"])
        self.assertEqual("original handler error", raw["message"])
        self.assertEqual({"value": 17}, raw["details"])
        self.assertEqual(proof_before, raw["completion_clock_proof"])
        resolved = runtime._settlement_journal.pending(timeout_seconds=.5)
        self.assertFalse(any(row["identity"]["execution_id"] == name for row in resolved))
        self.assertEqual([name], calls.read_text().splitlines())
        retained = runtime._settlement_journal.inspect(name, timeout_seconds=.5)[0]
        self.assertEqual(proof_before, retained["deferred"]["outcome"]["completion_clock_proof"])
        self.assertEqual(envelope.constraints,
            BudgetEnvelope.from_dict(retained["evidence"]["budget_envelope"]).constraints)
        (self.root / "guarded-return-timeout.json").write_text(json.dumps({
            "original_receipt": record, "recovery_reports": reports,
            "resolved_receipt": retained, "kernel_result": current.result.to_dict(),
            "business_invocations": calls.read_text().splitlines()}, indent=2))

    def test_resolved_result_survives_interruption_after_kernel_commit_and_exact_reopen_replay(self):
        name = "guarded-return-commit-crash"
        runtime, _, _, _, envelope, token, calls, original, _ = self.deferred_guarded_handler_outcome(name)
        runtime.kernel._finish_budget_sample(token, name, envelope)
        settle = runtime._settlement_journal.settle
        committed_results = []

        class AfterKernelCommit(BaseException):
            pass

        def interrupted(record, state, evidence, **kwargs):
            if state == "recorded":
                actual = runtime.kernel.get(name).result.to_dict()
                self.assertEqual(record["evidence"]["resolved_result"], actual)
                committed_results.append(actual)
                raise AfterKernelCommit("interrupted before journal recording")
            return settle(record, state, evidence, **kwargs)

        with patch.object(runtime._settlement_journal, "settle", side_effect=interrupted):
            with self.assertRaises(AfterKernelCommit):
                runtime.recover_completions(timeout_seconds=.5)
        self.assertEqual(1, len(committed_results))
        pending = runtime._settlement_journal.pending(timeout_seconds=.5)[0]
        self.assertEqual("pending", pending["state"])
        self.assertEqual(committed_results[0], pending["evidence"]["resolved_result"])
        self.assertEqual(original["deferred"], pending["deferred"])
        runtime.close()
        reopened = self.open(name)
        with patch.object(reopened, "_outcome_result", side_effect=AssertionError("replay generated a new result")), \
                patch.object(runtime_module, "resolve_completion_time",
                             side_effect=AssertionError("replay reread the completion clock")):
            current, reports = self.recover(reopened, name)
        self.assertEqual(committed_results[0], current.result.to_dict())
        self.assertEqual("succeeded", current.state)
        final = reopened._settlement_journal.inspect(name, timeout_seconds=.5)[0]
        self.assertEqual("recorded", final["state"])
        self.assertEqual(pending["evidence"]["resolved_result"], final["evidence"]["resolved_result"])
        self.assertEqual([name], calls.read_text().splitlines())
        (self.root / "guarded-return-replay.json").write_text(json.dumps({
            "before_reopen": pending, "after_reopen": final,
            "recovery_reports": reports, "business_invocations": calls.read_text().splitlines()}, indent=2))

    def test_failed_recovery_reader_close_retains_one_owner_until_runtime_close_retry(self):
        from dispatcher_sdk import storage_connection

        name = "guarded-return-reader-close"
        runtime, _, _, _, envelope, token, calls, _, context = self.deferred_guarded_handler_outcome(name)
        runtime.kernel._finish_budget_sample(token, name, envelope)
        factory = completion_clock_module._connect_readonly
        physical_close = storage_connection._ParticipatingConnection.close
        readers, close_failures = [], []

        def opened(*args, **kwargs):
            reader = factory(*args, **kwargs)
            readers.append(reader)
            return reader

        def failed_close(reader):
            if reader in readers:
                close_failures.append("recovery reader remains physically open")
                raise OSError(close_failures[-1])
            return physical_close(reader)

        try:
            with patch.object(completion_clock_module, "_connect_readonly", side_effect=opened), \
                    patch.object(storage_connection._ParticipatingConnection, "close", failed_close):
                runtime.recover_completions(timeout_seconds=.5)
                self.assertEqual(1, len(readers))
                self.assertEqual(1, len(runtime._recovery_completion_readers))
                self.assertEqual(1, readers[0].execute("SELECT 1").fetchone()[0])
                runtime.recover_completions(timeout_seconds=.5)
                self.assertEqual(1, len(readers), "failed-close recovery opened another reader")
                self.assertIsNone(runtime.kernel.get(name).result)
                # A previously retired real Context may have finished before
                # this close pass. Its successful drain must not erase the
                # independent recovery reader's failed physical release.
                context.close()
                runtime._retired_observation_contexts.append(context)
                with self.assertRaises(runtime_module._ObservationCleanupPendingError):
                    runtime.close()
                self.assertFalse(runtime.kernel._connection_closed)
                self.assertEqual(1, len(runtime._recovery_completion_readers))
            runtime.close()
            self.assertEqual(set(), runtime._recovery_completion_readers)
            self.assertTrue(runtime.kernel._connection_closed)
            with self.assertRaises(sqlite3.ProgrammingError):
                readers[0].execute("SELECT 1")
            reopened = self.open(name)
            current, _ = self.recover(reopened, name)
            self.assertEqual("succeeded", current.state)
            self.assertEqual([name], calls.read_text().splitlines())
            (self.root / "guarded-return-reader-close.json").write_text(json.dumps({
                "reader_connections_before_close": len(readers), "close_errors": close_failures,
                "recovered_result": current.result.to_dict(),
                "business_invocations": calls.read_text().splitlines()}, indent=2))
        finally:
            for reader in readers:
                physical_close(reader)

    def test_real_thread_success_and_error_recover_original_results(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                name = "thread-error" if failure else "thread-success"
                runtime, writer, calls, original, _ = self.run_with_result_writer_locked(
                    name, failure=failure)
                writer.rollback()
                current, _ = self.recover(runtime, name)
                self.assertEqual(current.result.to_dict(), original)
                self.assertEqual(current.state, "failed" if failure else "succeeded")
                if failure:
                    self.assertEqual(current.result.error.code, "original_real_failure")
                self.assertEqual(len(calls.read_text().splitlines()), 1)
                self.assert_retained(runtime, name, original, "recorded")

    def test_oversized_retained_diagnostics_make_public_reads_incomplete(self):
        from dispatcher_sdk.observability import inspect_execution
        runtime, writer, calls, original, obligation = self.run_with_result_writer_locked("oversized-diagnostic")
        self.stop_maintenance(runtime)
        runtime._settlement_journal.settle(obligation, "error", {
            **obligation["evidence"], "raw_control_error": "x" * 300_000}, timeout_seconds=.5)
        before = runtime._settlement_journal.pending(timeout_seconds=.5)[0]
        observed = runtime.observe("oversized-diagnostic", timeout=1)
        storage = runtime.observation_storage
        independent = inspect_execution(storage["path"], "oversized-diagnostic",
            kernel_path=storage["kernel_path"], source_id=storage["source_id"], timeout=1)
        for report in (observed, independent):
            self.assertFalse(report["complete"], report)
            self.assertTrue(report["settlement_obligations"][0]["truncated"])
        self.assertEqual(before, runtime._settlement_journal.pending(timeout_seconds=.5)[0])
        writer.rollback()
        recovered, _ = self.recover(runtime, "oversized-diagnostic")
        self.assertEqual(recovered.result.to_dict(), original)
        self.assertEqual(len(calls.read_text().splitlines()), 1)

    def test_large_query_option_keeps_public_diagnostic_reads_available(self):
        from dispatcher_sdk import ObservationOptions
        from dispatcher_sdk.observability import inspect_execution
        runtime = Kernel.open_sqlite(self.root / "large-query.sqlite3", {"work": settlement_success},
            isolation_mode="thread", observation_options=ObservationOptions(query_bytes=1024 * 1024))
        with runtime:
            command = runtime.command("work", execution_id="large-query", idempotency_key="large-query",
                correlation_id="large-query", timeout_seconds=5,
                payload={"call_log": str(self.root / "large-query-calls"), "value": 17})
            runtime.submit(command)
            self.assertEqual(runtime.run_once().state, "succeeded")
            storage = runtime.observation_storage
            reports = (runtime.observe("large-query"), inspect_execution(storage["path"], "large-query",
                kernel_path=storage["kernel_path"], source_id=storage["source_id"],
                options=runtime.observation_options))
            for report in reports:
                self.assertNotIn("settlement_obligations_error", report)
                self.assertIn("diagnostics", report)
                self.assertIn("settlement_obligations", report)

    @unittest.skipUnless(sys.platform == "linux", "requires real POSIX process containment")
    def test_real_process_success_and_error_recover_original_results(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                name = "process-error" if failure else "process-success"
                runtime, writer, calls, original, _ = self.run_with_result_writer_locked(
                    name, mode="process", failure=failure)
                writer.rollback()
                current, _ = self.recover(runtime, name)
                self.assertEqual(current.result.to_dict(), original)
                self.assertEqual(current.state, "failed" if failure else "succeeded")
                self.assertEqual(len(calls.read_text().splitlines()), 1)
                self.assert_retained(runtime, name, original, "recorded")

    def test_restart_records_original_outcome_without_reinvoking_handler(self):
        runtime, writer, calls, original, _ = self.run_with_result_writer_locked("restart")
        runtime.close()
        writer.rollback()
        reopened = self.open("restart")
        current, _ = self.recover(reopened, "restart")
        self.assertEqual(current.result.to_dict(), original)
        self.assertIsNone(reopened.run_once())
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(reopened, "restart", original, "recorded")

    def test_copy_upgrade_keeps_external_pending_outcome_with_original_owner(self):
        from dispatcher_sdk.maintenance import maintenance_lease
        from dispatcher_sdk.storage_migration import upgrade_storage
        from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
        from tests.test_storage_migration import StorageMigrationTests

        name = "upgrade-original-owner"
        runtime, writer, calls, original, obligation = self.run_with_result_writer_locked(name)
        source = Path(runtime.kernel.db_path)
        observation = dict(runtime.observation_storage)
        journal_path = runtime._settlement_journal.path
        source_id = runtime._settlement_journal.source_id
        runtime.close()
        writer.rollback()
        before = StorageMigrationTests._stored_rows(source)
        destination = self.root / "upgrade-copy.sqlite3"
        with maintenance_lease(source, "tests", "pending-outcome-copy") as lease:
            report = upgrade_storage(source, destination, lease=lease)
        self.assertEqual(StorageMigrationTests._stored_rows(source), before)
        self.assertEqual(StorageMigrationTests._stored_rows(destination), before)
        for field in ("automatic_activation", "automatic_cutover",
                      "external_stores_included", "observation_journal_included"):
            self.assertFalse(report[field])
        self.assertEqual((report["source_version"], report["target_version"]), (5, 5))
        pending = SettlementJournal.open_readonly(journal_path, source_id=source_id,
            kernel_path=source, timeout_seconds=.5).inspect(name, timeout_seconds=.5)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["result"], original)
        self.assertIn(pending[0]["state"], {"pending", "error"})
        with closing(sqlite3.connect(destination.resolve().as_uri() + "?mode=ro", uri=True)) as copied:
            names = {row[0] for row in copied.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse(any(table.startswith("obs_") or table.startswith("settlement_")
                                 for table in names))
        # Only the original deployment owns its unchanged external receipt.
        # Recovery settles the retained result; it does not execute the handler.
        reopened = self.open(name)
        current, recovery = self.recover(reopened, name)
        self.assertEqual(current.result.to_dict(), original)
        self.assertIsNone(reopened.run_once())
        self.assertEqual(calls.read_text().splitlines(), [name])
        self.assert_retained(reopened, name, original, "recorded")
        self.assertEqual(StorageMigrationTests._stored_rows(destination), before)
        (self.root / "copy-upgrade-evidence.json").write_text(json.dumps({
            "source": str(source), "destination": str(destination),
            "observation_storage": observation, "original_obligation": obligation,
            "pending_after_copy": pending,
            "copy_report": report, "recovery_reports": recovery,
            "original_result": original, "recovered_result": current.result.to_dict(),
            "business_invocations": calls.read_text().splitlines(),
            "destination_activated": False,
        }, indent=2, default=str))

    def test_lifecycle_contention_preserves_actual_return_before_admission(self):
        runtime = Kernel.open_sqlite(self.root / "lifecycle.sqlite3",
            {"work": settlement_gated_success}, isolation_mode="thread")
        self.addCleanup(runtime.close)
        ready, release, calls = (self.root / name for name in ("ready", "release", "calls"))
        command = runtime.command("work", execution_id="lifecycle", idempotency_key="lifecycle",
            correlation_id="lifecycle", timeout_seconds=5,
            payload={"ready": str(ready), "release": str(release), "call_log": str(calls)})
        runtime.submit(command)
        results, errors = [], []

        def drive():
            try:
                results.append(runtime.run_once())
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=drive)
        driver.start()
        self.addCleanup(lambda: driver.join(3))
        self.addCleanup(lambda: release.touch())
        wait_end = time.monotonic() + 3
        while not ready.exists() and not errors and time.monotonic() < wait_end:
            time.sleep(.005)
        self.assertTrue(ready.exists(), errors)
        self.assertTrue(runtime._lifecycle_lock.acquire(timeout=1))
        try:
            release.touch()
            wait_end = time.monotonic() + 2
            receipts = []
            while not receipts and time.monotonic() < wait_end:
                receipts = runtime._settlement_journal.inspect("lifecycle", timeout_seconds=.5)
                if not receipts:
                    time.sleep(.005)
            self.assertEqual(len(receipts), 1, "lifecycle admission lost the original real outcome")
            self.assertEqual(receipts[0]["result"]["value"], {
                "message": "actual handler returned while lifecycle was held"})
            driver.join(1)
            frame = sys._current_frames().get(driver.ident)
            (self.root / "lifecycle-caller.json").write_text(json.dumps({
                "original_execution_timeout_seconds": command.timeout_seconds,
                "original_receipt": receipts[0], "driver_alive": driver.is_alive(),
                "driver_stack": [] if frame is None else traceback.format_stack(frame)[-12:],
                "errors": [repr(error) for error in errors],
                "returned_states": [result.state for result in results],
            }, indent=2), encoding="utf-8")
            self.assertFalse(driver.is_alive(), "lifecycle contention still blocked the public caller")
            self.assertEqual(errors, [])
            self.assertEqual(results[0].state, "running")
        finally:
            runtime._lifecycle_lock.release()
        current, _ = self.recover(runtime, "lifecycle")
        self.assertEqual(current.result.to_dict(), receipts[0]["result"])
        self.assertEqual(len(calls.read_text().splitlines()), 1)

    def test_expired_exact_lease_restores_completed_before_expiry(self):
        clock = Clock()
        runtime, writer, calls, original, receipt = self.run_with_result_writer_locked(
            "expired-lease", clock=clock)
        self.assertLessEqual(original["completed_at"], receipt["lease"]["expires_at"])
        clock.value = receipt["lease"]["expires_at"] + 1
        writer.rollback()
        current, _ = self.recover(runtime, "expired-lease")
        self.assertEqual(current.result.to_dict(), original)
        self.assertEqual(current.state, "succeeded")
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(runtime, "expired-lease", original, "recorded")

    def start_gated_completion(self, name, clock):
        runtime = Kernel.open_sqlite(self.root / (name + ".sqlite3"),
            {"work": settlement_gated_success}, isolation_mode="thread", now=clock)
        self.addCleanup(runtime.close)
        ready, release, calls = (self.root / (name + suffix) for suffix in ("-ready", "-release", "-calls"))
        command = runtime.command("work", execution_id=name, idempotency_key=name,
            correlation_id=name, timeout_seconds=5,
            payload={"ready": str(ready), "release": str(release), "call_log": str(calls)})
        runtime.submit(command)
        results, errors = [], []

        def drive():
            try:
                results.append(runtime.run_once(execution_id=name))
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=drive)
        self.addCleanup(lambda: driver.join(3))
        self.addCleanup(release.touch)
        driver.start()
        end = time.monotonic() + 3
        while not ready.exists() and not errors and time.monotonic() < end:
            time.sleep(.005)
        self.assertTrue(ready.exists(), errors)
        return runtime, command, release, calls, driver, results, errors

    def test_logical_watermark_rollback_cannot_restore_postexpiry_success(self):
        clock = Clock()
        runtime, command, release, calls, driver, results, errors = self.start_gated_completion("logical-rollback", clock)
        lease = runtime.kernel.get(command.execution_id).lease
        old_wall = clock.value
        context = next(iter(runtime._thread_contexts.values()))
        # Isolate logical-clock continuity from budget polling: neither the
        # handler nor its deadline loop observes this short wall excursion.
        with context._budget_lock:
            clock.value = lease.expires_at + 1
            runtime.kernel.submit(replace(command, execution_id="logical-clock-witness",
                idempotency_key="logical-clock-witness", correlation_id="logical-clock-witness"))
            clock.value = old_wall
        self.assertGreater(runtime.kernel.current_time(), lease.expires_at)
        release.touch()
        driver.join(3)
        self.assertFalse(driver.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(1, len(results))
        runtime.recover_completions(timeout_seconds=.5)
        current = runtime.kernel.get(command.execution_id)
        self.assertNotEqual("succeeded", current.state)
        self.assertIsNone(current.result)
        receipts = runtime._settlement_journal.inspect(command.execution_id, timeout_seconds=.5)
        self.assertEqual(1, len(receipts))
        original = receipts[0]["result"]
        self.assertEqual("succeeded", original["status"])
        self.assertEqual({"message": "actual handler returned while lifecycle was held"}, original["value"])
        self.assertGreater(original["completed_at"], lease.expires_at)
        self.assertEqual("superseded", receipts[0]["state"])
        self.assertEqual(1, len(calls.read_text().splitlines()))

    def test_completion_clock_storage_timeout_retains_unknown_original_outcome(self):
        clock = Clock()
        captured, capture_done = [], threading.Event()
        original_capture = runtime_module._capture_completion_time

        def capture(outcome, context):
            began = time.monotonic()
            original_capture(outcome, context)
            captured.append((dict(outcome), time.monotonic() - began))
            capture_done.set()

        with patch.object(runtime_module, "_capture_completion_time", side_effect=capture):
            runtime, command, release, calls, driver, results, errors = self.start_gated_completion("unknown-return-clock", clock)
            lease = runtime.kernel.get(command.execution_id).lease
            context = next(iter(runtime._thread_contexts.values()))
            with runtime.kernel._lock:
                # The writer lock alone no longer blocks factual snapshots.
                # Make clock storage genuinely unreadable during the original
                # return capture, using a real rollback-journal writer.
                connection = runtime.kernel._connection
                connection.set_authorizer(lambda *args: sqlite3.SQLITE_OK)
                try:
                    self.assertEqual("delete", connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0])
                finally:
                    connection.set_authorizer(runtime.kernel._authorizer)
                began = time.monotonic()
                with closing(sqlite3.connect(runtime.kernel.db_path, timeout=0)) as writer:
                    writer.execute("BEGIN EXCLUSIVE")
                    try:
                        release.touch()
                        self.assertTrue(capture_done.wait(.25), "return-time capture exceeded its original admission bound")
                    finally:
                        writer.rollback()
                self.assertFalse(captured[0][0]["completion_time_known"])
                self.assertLess(captured[0][1], .25)
                # Establish expiry only after the genuinely unreadable return
                # point; later availability cannot recreate its original time.
                with context._budget_lock:
                    old_wall = clock.value
                    clock.value = lease.expires_at + 1
                    runtime.kernel.submit(replace(command, execution_id="unknown-clock-witness",
                        idempotency_key="unknown-clock-witness", correlation_id="unknown-clock-witness"))
                    clock.value = old_wall
                time.sleep(max(0, .3 - (time.monotonic() - began)))
            driver.join(3)
        self.assertFalse(driver.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(1, len(results))
        runtime.recover_completions(timeout_seconds=.5)
        current = runtime.kernel.get(command.execution_id)
        self.assertIsNone(current.result)
        self.assertNotEqual("succeeded", current.state)
        receipts = runtime._settlement_journal.inspect(command.execution_id, timeout_seconds=.5)
        self.assertEqual(1, len(receipts))
        self.assertIsNone(receipts[0]["result"])
        self.assertIn(receipts[0]["state"], {"pending", "error"})
        raw = receipts[0]["deferred"]["outcome"]
        self.assertEqual("ok", raw["kind"])
        self.assertFalse(raw["completion_time_known"])
        self.assertNotIn("completed_at", raw)
        self.assertEqual({"message": "actual handler returned while lifecycle was held"}, raw["value"])
        self.assertEqual("OperationalError: database is locked", raw["completion_time_error"])
        self.assertEqual(1, len(calls.read_text().splitlines()))

    def test_cancel_wins_and_archives_original_outcome(self):
        runtime, writer, calls, original, _ = self.run_with_result_writer_locked("cancel-wins")
        self.stop_maintenance(runtime)
        writer.rollback()
        current = runtime.kernel.get("cancel-wins")
        cancelled = runtime.cancel("cancel-wins", expected_revision=current.revision)
        runtime.recover_completions(timeout_seconds=.5)
        after = runtime.kernel.get("cancel-wins")
        self.assertEqual(after.to_dict(), cancelled.to_dict())
        self.assertEqual(after.state, "cancelled")
        self.assertNotEqual(after.result.result_id, original["result_id"])
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(runtime, "cancel-wins", original, "superseded")

    def test_reap_wins_and_archives_original_outcome(self):
        clock = Clock()
        runtime, writer, calls, original, receipt = self.run_with_result_writer_locked(
            "reap-wins", clock=clock)
        self.stop_maintenance(runtime)
        clock.value = receipt["lease"]["expires_at"] + 1
        writer.rollback()
        # An independent Kernel controller can win before Runtime's recovery.
        # Runtime.reap deliberately tries completion recovery first.
        runtime.kernel.reap()
        reaped = runtime.kernel.get("reap-wins")
        self.assertIn(reaped.state, {"timed_out", "dead", "failed"})
        self.assertIsNotNone(reaped.result)
        runtime.recover_completions(timeout_seconds=.5)
        after = runtime.kernel.get("reap-wins")
        self.assertEqual(after.to_dict(), reaped.to_dict())
        self.assertNotEqual(after.result.result_id, original["result_id"])
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(runtime, "reap-wins", original, "superseded")

    def test_new_attempt_wins_without_accepting_previous_success(self):
        clock = Clock()
        runtime, writer, calls, original, receipt = self.run_with_result_writer_locked(
            "new-attempt", clock=clock,
            retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                     max_backoff_seconds=0, retry_timeouts=True))
        self.stop_maintenance(runtime)
        clock.value = receipt["lease"]["expires_at"] + 1
        writer.rollback()
        runtime.kernel.reap()
        lease = runtime.kernel.claim_and_start("independent-worker", execution_id="new-attempt")
        self.assertIsNotNone(lease)
        winner = runtime.kernel.get("new-attempt")
        self.assertEqual(winner.attempt, 2)
        self.assertGreater(winner.fence, receipt["identity"]["fence"])
        runtime.recover_completions(timeout_seconds=.5)
        after = runtime.kernel.get("new-attempt")
        self.assertEqual(after.to_dict(), winner.to_dict())
        self.assertIsNone(after.result)
        self.assertEqual(len(calls.read_text().splitlines()), 1)
        self.assert_retained(runtime, "new-attempt", original, "superseded")


if __name__ == "__main__":
    unittest.main()
