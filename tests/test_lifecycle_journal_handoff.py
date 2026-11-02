"""Exercise exact lifecycle notes through real Kernel and journal storage."""
import contextlib
from pathlib import Path
import multiprocessing
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, SQLiteKernel
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.execution_kernel.runtime import _UnpersistedDiagnosticsError, _UnpersistedSettlementsError
from dispatcher_sdk.execution_kernel.host import RuntimeHost


def lifecycle_handler(payload, context):
    return {"value": payload["value"]}


lifecycle_handler.__execution_kernel_revision__ = "lifecycle-journal-test-v1"


def crash_after_claim(path):
    runtime = Kernel.open_sqlite(path, {"work": lifecycle_handler}, isolation_mode="process")
    def crash(*args):
        os._exit(23)
    runtime._invoke_process = crash
    runtime.run_once(execution_id="crashed")
    os._exit(24)


def crash_before_claim_receipt(path):
    runtime = Kernel.open_sqlite(path, {"work": lifecycle_handler}, isolation_mode="process")
    original = runtime._diagnostic_note
    def crash(identity, phase, evidence, **kwargs):
        if phase == "execution_claimed":
            os._exit(25)
        return original(identity, phase, evidence, **kwargs)
    runtime._diagnostic_note = crash
    runtime.run_once(execution_id="crash-before-receipt")
    os._exit(26)


def crash_after_cancel_commit(path):
    runtime = Kernel.open_sqlite(path, {"work": lifecycle_handler}, isolation_mode="process")
    original = runtime.kernel.cancel
    def cancel_and_crash(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(27)
    runtime.kernel.cancel = cancel_and_crash
    runtime.cancel("cancel-crash", expected_revision=runtime.kernel.get("cancel-crash").revision)
    os._exit(28)


class LifecycleJournalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "kernel.sqlite3"
        self.runtime = Kernel.open_sqlite(self.path, {"work": lifecycle_handler}, isolation_mode="process")
        self.addCleanup(self.runtime.close)

    def submit(self, name):
        self.runtime.submit(self.runtime.command("work", execution_id=name, idempotency_key=name,
            correlation_id=name, timeout_seconds=10, payload={"value": 12}))

    def reopen_notes(self, name):
        journal = self.runtime._settlement_journal
        reopened = SettlementJournal(journal.path, source_id=journal.source_id, kernel_path=self.path)
        return reopened.inspect_notes(name, timeout_seconds=1)["notes"]

    def test_host_retries_exact_pending_diagnostic_until_durable(self):
        from types import SimpleNamespace

        self.submit("host-close-retry")
        journal = self.runtime._settlement_journal
        original_note = journal.lifecycle_note
        original_close = self.runtime.close
        unavailable = [True]
        failed_closes = []

        def note(identity, phase, evidence, **kwargs):
            if phase == "worker_invocation_escaped" and unavailable[0]:
                raise OSError("journal unavailable")
            return original_note(identity, phase, evidence, **kwargs)

        def close():
            try:
                return original_close()
            except _UnpersistedDiagnosticsError:
                failed_closes.append(True)
                unavailable[0] = False
                raise

        with patch.object(journal, "lifecycle_note", side_effect=note), \
             patch.object(self.runtime, "_invoke_process", side_effect=RuntimeError("escaped")), \
             patch.object(self.runtime, "close", side_effect=close):
            with self.assertRaisesRegex(RuntimeError, "escaped"):
                self.runtime.run_once(execution_id="host-close-retry")
            event = self.runtime.kernel.lifecycle_peek(execution_id="host-close-retry")
            self.assertEqual(event["phase"], "worker_invocation_escaped")
            store_id = self.runtime.kernel.kernel_store_identity()
            bridge = SimpleNamespace(pump=lambda **_: None, sweep=lambda **_: None)
            host = RuntimeHost(self.runtime, bridge)
            self.assertTrue(host.stop(timeout=5))
        self.assertEqual(len(failed_closes), 1)
        self.assertFalse(self.runtime._diagnostics_block_admission())
        notes = self.reopen_notes("host-close-retry")
        self.assertEqual(len([n for n in notes if n["phase"] == "worker_invocation_escaped"]), 1)
        self.assertTrue(self.runtime._kernel_storage_closed)
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT event_id, delivered FROM kernel_lifecycle_outbox WHERE sequence=?",
                (event["sequence"],)).fetchone()
        self.assertEqual(row, (event["event_id"], 1))
        with contextlib.closing(sqlite3.connect(journal.path)) as connection:
            receipt = connection.execute(
                "SELECT n.execution_id,n.attempt,n.fence,n.phase,n.evidence_json "
                "FROM settlement_lifecycle_receipts r JOIN settlement_notes n ON n.sequence=r.note_sequence "
                "WHERE r.store_id=? AND r.outbox_sequence=?",
                (store_id, event["sequence"])).fetchone()
        import json
        self.assertEqual(receipt[:4], (event["execution_id"], event["attempt"], event["fence"], event["phase"]))
        self.assertEqual(json.loads(receipt[4]), event["payload"])

    def test_real_worker_registration_and_cleanup_receipts_survive_reopen(self):
        self.submit("real-worker")
        result = self.runtime.run_once(execution_id="real-worker")
        self.assertEqual(result.state, "succeeded")
        notes = self.reopen_notes("real-worker")
        phases = [note["phase"] for note in notes]
        for phase in ("supervisor_registered", "worker_ready", "handler_entered", "process_cleanup", "handler_outcome"):
            self.assertIn(phase, phases)
        self.assertLess(phases.index("supervisor_registered"), phases.index("worker_ready"))
        identity = {"execution_id": "real-worker", "attempt": result.attempt, "fence": result.fence}
        self.assertTrue(all(note["identity"] == identity for note in notes))
        registration = next(note for note in notes if note["phase"] == "supervisor_registered")
        self.assertEqual(registration["evidence"]["source"], "runtime_registration")
        cleanup = next(note for note in notes if note["phase"] == "process_cleanup")
        self.assertEqual(cleanup["evidence"], {"state": "confirmed", "source": "runtime_supervisor_reaped"})

    def test_real_worker_does_not_overtake_failed_registration_receipt(self):
        self.submit("ordered-worker")
        journal = self.runtime._settlement_journal
        original_note = journal.lifecycle_note
        def fail_registration(identity, phase, evidence, **kwargs):
            if phase == "supervisor_registered":
                raise OSError("registration journal write unavailable")
            return original_note(identity, phase, evidence, **kwargs)
        with patch.object(journal, "lifecycle_note", side_effect=fail_registration):
            result = self.runtime.run_once(execution_id="ordered-worker")
            self.assertEqual(result.state, "succeeded")
            phases = [note["phase"] for note in self.reopen_notes("ordered-worker")]
            self.assertNotIn("worker_ready", phases)
            self.assertNotIn("process_cleanup", phases)
            self.assertTrue(self.runtime._diagnostics_block_admission())
            # Reproduce a concurrent writer owning the lock at retry time.
            self.assertTrue(self.runtime._diagnostic_retry_lock.acquire(timeout=5))
        try:
            self.runtime._retry_diagnostic_notes(time.monotonic() + 1)
            self.assertNotIn("supervisor_registered",
                             [note["phase"] for note in self.reopen_notes("ordered-worker")])
        finally:
            self.runtime._diagnostic_retry_lock.release()
        # The background settlement thread may already own the writer; wait
        # for that handoff before inspecting the durable receiver journal.
        self.runtime._retry_diagnostic_notes(time.monotonic() + 5, wait_for_writer=True)
        self.assertFalse(self.runtime._diagnostics_block_admission("ordered-worker"))
        notes = self.reopen_notes("ordered-worker")
        phases = [note["phase"] for note in notes]
        for earlier, later in (("supervisor_registered", "worker_ready"),
                               ("worker_ready", "handler_entered"),
                               ("handler_entered", "process_cleanup"),
                               ("process_cleanup", "handler_outcome")):
            self.assertLess(phases.index(earlier), phases.index(later))
        self.assertTrue(all(note["identity"] == {"execution_id": "ordered-worker",
            "attempt": result.attempt, "fence": result.fence} for note in notes))

    def test_crash_after_claim_retains_only_claim_fact(self):
        self.submit("crashed")
        process = multiprocessing.get_context("spawn").Process(target=crash_after_claim, args=(self.path,))
        process.start()
        process.join(15)
        self.assertFalse(process.is_alive())
        self.assertEqual(process.exitcode, 23)
        snapshot = self.runtime.kernel.get("crashed")
        notes = self.reopen_notes("crashed")
        claim = next(note for note in notes if note["phase"] == "execution_claimed")
        self.assertEqual(claim["identity"], {"execution_id": "crashed",
            "attempt": snapshot.attempt, "fence": snapshot.fence})
        self.assertFalse(any(note["phase"] in ("handler_entered", "handler_outcome", "process_cleanup")
                             for note in notes))
        self.assertIsNone(snapshot.result)

    def test_failed_claim_receipt_prevents_handler_invocation_and_can_retry(self):
        self.submit("claim-receipt")
        journal = self.runtime._settlement_journal
        original_note = journal.lifecycle_note
        def unavailable(identity, phase, evidence, **kwargs):
            if phase == "execution_claimed":
                raise OSError("claim receipt unavailable")
            return original_note(identity, phase, evidence, **kwargs)
        with patch.object(journal, "lifecycle_note", side_effect=unavailable), \
             patch.object(self.runtime, "_invoke_process") as invoke:
            with self.assertRaisesRegex(_UnpersistedDiagnosticsError, "not confirmed durable"):
                self.runtime.run_once(execution_id="claim-receipt")
            invoke.assert_not_called()
            self.assertTrue(self.runtime._diagnostics_block_admission())
        self.runtime._retry_diagnostic_notes(time.monotonic() + 2)
        phases = [note["phase"] for note in self.reopen_notes("claim-receipt")]
        self.assertLess(phases.index("execution_claimed"), phases.index("worker_invocation_escaped"))
        self.assertFalse(self.runtime._diagnostics_block_admission())

    def test_unretained_claim_fact_keeps_durable_producer_open(self):
        self.submit('unretained-claim')
        original_note = self.runtime._diagnostic_note
        def exhaust_after_claim(identity, phase, evidence, **kwargs):
            if phase == 'execution_claimed':
                self.runtime._diagnostic_pending_capacity = 0
            return original_note(identity, phase, evidence, **kwargs)
        with patch.object(self.runtime, '_diagnostic_note', side_effect=exhaust_after_claim), \
             patch.object(self.runtime, '_invoke_process') as invoke:
            with self.assertRaisesRegex(_UnpersistedDiagnosticsError, 'not confirmed durable'):
                self.runtime.run_once(execution_id='unretained-claim')
            invoke.assert_not_called()
        producer = self.runtime.kernel.lifecycle_list_open_producers(limit=10)['producers']
        self.assertEqual(len(producer), 1)
        self.assertEqual(producer[0]['execution_id'], 'unretained-claim')
        reopened = SQLiteKernel(self.path)
        try:
            self.assertEqual(reopened.lifecycle_list_open_producers(limit=10)['producers'][0]['token'],
                             producer[0]['token'])
        finally:
            reopened.close()
        # Clear only this live Runtime's volatile test fault so tear-down can
        # close it; the durable producer remains open in the database.
        self.runtime._diagnostic_pending_capacity = 64
        self.runtime._diagnostic_pending_overflow = False
        self.runtime._diagnostic_failed_executions.clear()

    def test_restart_recovers_atomic_claim_without_inventing_outcome_or_cleanup(self):
        self.submit("crash-before-receipt")
        process = multiprocessing.get_context("spawn").Process(target=crash_before_claim_receipt, args=(self.path,))
        process.start()
        process.join(15)
        self.assertFalse(process.is_alive())
        self.assertEqual(process.exitcode, 25)
        snapshot = self.runtime.kernel.get("crash-before-receipt")
        self.assertFalse(self.reopen_notes("crash-before-receipt"))
        self.runtime.close()
        restarted = Kernel.open_sqlite(self.path, {"work": lifecycle_handler}, isolation_mode="process")
        self.addCleanup(restarted.close)
        args = ("crash-before-receipt", snapshot.attempt, snapshot.fence)
        with patch.object(restarted._settlement_journal, "note", side_effect=OSError("journal unavailable")):
            unavailable = restarted.recover_claim_lifecycle(*args)
        self.assertEqual((unavailable["state"], unavailable["reason"]), ("unknown", "recovery_unavailable"))
        self.assertEqual(unavailable["process_cleanup"], "unknown")
        self.assertEqual(restarted._settlement_journal.inspect_notes(args[0], timeout_seconds=1)["notes"], [])
        reports = []
        barrier = threading.Barrier(3)
        def recover():
            barrier.wait()
            reports.append(restarted.recover_claim_lifecycle(*args, timeout_seconds=3))
        threads = [threading.Thread(target=recover) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual([report["state"] for report in reports], ["recorded", "recorded"])
        self.assertTrue(all(report["process_cleanup"] == report["outcome"] == "unknown" for report in reports))
        notes = restarted._settlement_journal.inspect_notes(args[0], timeout_seconds=1)["notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["phase"], "kernel_claim_recovered")
        self.assertEqual(notes[0]["identity"], {"execution_id": args[0], "attempt": args[1], "fence": args[2]})
        self.assertEqual(notes[0]["evidence"]["source"], "kernel_started_event")
        missing = restarted.recover_claim_lifecycle(args[0], args[1], args[2] + 1)
        self.assertEqual((missing["state"], missing["reason"]), ("unknown", "kernel_claim_event_missing"))
        self.assertEqual(len(restarted._settlement_journal.inspect_notes(args[0], timeout_seconds=1)["notes"]), 1)

    def test_escaped_invocation_records_exact_identity_without_inventing_cleanup(self):
        self.submit("escaped")
        with patch.object(self.runtime, "_invoke_process", side_effect=RuntimeError("escaped invocation")):
            with self.assertRaisesRegex(RuntimeError, "escaped invocation") as raised:
                self.runtime.run_once(execution_id="escaped")
        context = raised.exception.execution_context
        # This is a snapshot of a bounded synchronous attempt. On a slow
        # host the receipt can remain queued and be persisted by a retry.
        self.assertIsInstance(context["diagnostic_saved"], bool)
        self.runtime._drain_diagnostic_notes(time.monotonic() + 5)
        self.assertFalse(self.runtime._diagnostics_block_admission("escaped"))
        notes = self.reopen_notes("escaped")
        note = next(note for note in notes if note["phase"] == "worker_invocation_escaped")
        self.assertEqual(note["identity"], {key: context[key] for key in ("execution_id", "attempt", "fence")})
        self.assertEqual(note["evidence"]["process_cleanup"], "unknown")
        self.assertEqual(note["evidence"]["outcome"], "unknown")
        self.assertFalse(any(note["phase"] == "process_cleanup" for note in notes))

    def test_failed_escape_receipt_is_reported_as_unsaved(self):
        self.submit("unavailable")
        journal = self.runtime._settlement_journal
        original_note = journal.lifecycle_note
        def unavailable(identity, phase, evidence, **kwargs):
            if phase == "worker_invocation_escaped":
                raise OSError("journal unavailable")
            return original_note(identity, phase, evidence, **kwargs)
        with patch.object(journal, "lifecycle_note", side_effect=unavailable), \
             patch.object(self.runtime, "_invoke_process", side_effect=RuntimeError("escaped invocation")):
            with self.assertRaisesRegex(RuntimeError, "escaped invocation") as raised:
                self.runtime.run_once(execution_id="unavailable")
            self.assertFalse(raised.exception.execution_context["diagnostic_saved"])
            self.assertEqual(raised.exception.execution_context["process_cleanup"], "unknown")
            self.assertFalse(any(note["phase"] == "worker_invocation_escaped"
                                 for note in self.reopen_notes("unavailable")))

    def test_ambiguous_ack_retries_same_note_and_blocks_same_execution(self):
        self.submit("first")
        self.submit("second")
        journal = self.runtime._settlement_journal
        original_note = journal.lifecycle_note
        def ambiguous(identity, phase, evidence, **kwargs):
            if phase == "worker_invocation_escaped":
                original_note(identity, phase, evidence, **kwargs)
                raise OSError("acknowledgement lost")
            return original_note(identity, phase, evidence, **kwargs)
        with patch.object(journal, "lifecycle_note", side_effect=ambiguous), \
             patch.object(self.runtime, "_invoke_process", side_effect=RuntimeError("escaped")):
            with self.assertRaisesRegex(RuntimeError, "escaped"):
                self.runtime.run_once(execution_id="first")
            self.assertTrue(self.runtime._diagnostics_block_admission())
            self.assertEqual(len([note for note in self.reopen_notes("first")
                                  if note["phase"] == "worker_invocation_escaped"]), 1)
            with patch.object(self.runtime.kernel, "claim_and_start", wraps=self.runtime.kernel.claim_and_start) as claim:
                self.assertIsNone(self.runtime.run_once(execution_id="first"))
                claim.assert_not_called()
        self.runtime._drain_diagnostic_notes(time.monotonic() + 5)
        self.assertFalse(self.runtime._diagnostics_block_admission())
        notes = [note for note in self.reopen_notes("first") if note["phase"] == "worker_invocation_escaped"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(self.runtime.kernel.get("second").state, "queued")

    def test_preclaim_failure_has_unassigned_context(self):
        with patch.object(self.runtime.kernel, "claim_and_start", side_effect=OSError("claim failed")):
            with self.assertRaisesRegex(OSError, "claim failed") as raised:
                self.runtime.run_once()
        context = raised.exception.execution_context
        self.assertEqual(context["execution_assignment"], "execution_unassigned")
        self.assertEqual(context["phase"], "claim")
        self.assertEqual(context["worker_id"], self.runtime.worker_id)
        self.assertNotIn("execution_id", context)

    def test_close_reports_and_retries_unpersisted_note(self):
        self.submit("close-retry")
        journal = self.runtime._settlement_journal
        original_note = journal.lifecycle_note
        def fail_escape(identity, phase, evidence, **kwargs):
            if phase == "worker_invocation_escaped":
                raise OSError("journal unavailable")
            return original_note(identity, phase, evidence, **kwargs)
        with patch.object(journal, "lifecycle_note", side_effect=fail_escape), \
             patch.object(self.runtime, "_invoke_process", side_effect=RuntimeError("escaped")):
            with self.assertRaisesRegex(RuntimeError, "escaped"):
                self.runtime.run_once(execution_id="close-retry")
            with self.assertRaises(_UnpersistedDiagnosticsError):
                self.runtime.close()
        self.runtime.close()
        self.assertFalse(self.runtime._diagnostics_block_admission())
        self.assertEqual(len([note for note in self.reopen_notes("close-retry")
                              if note["phase"] == "worker_invocation_escaped"]), 1)

    def test_repeated_clean_close_does_not_access_closed_kernel(self):
        self.runtime.close()
        with patch.object(self.runtime.kernel, "lifecycle_peek", side_effect=AssertionError("closed Kernel")):
            self.runtime.close()

    def test_close_retains_kernel_for_unpersisted_settlement(self):
        pending = [{"execution_id": "pending", "attempt": 1, "fence": 1}]
        with patch.object(self.runtime._pending_settlements, "identities", return_value=pending), \
             patch.object(self.runtime, "_persist_pending_settlements"):
            with self.assertRaises(_UnpersistedSettlementsError):
                self.runtime.close()
            self.assertFalse(self.runtime._kernel_storage_closed)
        self.runtime.close()
        self.assertTrue(self.runtime._kernel_storage_closed)

    def test_close_preserves_original_failure_when_kernel_close_fails(self):
        with patch.object(self.runtime, "recover_sandboxes", side_effect=ValueError("original failure")), \
             patch.object(self.runtime, "_close_kernel_storage", side_effect=OSError("close failure")):
            with self.assertRaisesRegex(ValueError, "original failure") as caught:
                self.runtime.close()
        if hasattr(caught.exception, "add_note"):
            self.assertTrue(any("close failure" in note for note in caught.exception.__notes__))
        else:
            self.assertIn("close failure", str(caught.exception.kernel_close_error))
        # The retained original error is intentional; release the fixture's
        # storage after the injected failures are removed.
        self.runtime._close_error = None
        self.runtime.close()

    def test_close_waits_for_cancellation_diagnostic_handoff(self):
        self.submit("cancel-close")
        revision = self.runtime.kernel.get("cancel-close").revision
        entered, release = threading.Event(), threading.Event()
        errors = []
        original_note = self.runtime._diagnostic_note
        def blocked_note(identity, phase, evidence, **kwargs):
            if phase == "cancellation_requested":
                entered.set()
                if not release.wait(3):
                    raise AssertionError("test did not release cancellation")
            return original_note(identity, phase, evidence, **kwargs)
        def cancel():
            try:
                self.runtime.cancel("cancel-close", expected_revision=revision, timeout_seconds=3)
            except Exception as exc:
                errors.append(exc)
        def close():
            try:
                self.runtime.close()
            except Exception as exc:
                errors.append(exc)
        with patch.object(self.runtime, "_diagnostic_note", side_effect=blocked_note):
            worker = threading.Thread(target=cancel)
            worker.start()
            self.assertTrue(entered.wait(2))
            closer = threading.Thread(target=close)
            closer.start()
            try:
                closer.join(.1)
                self.assertTrue(closer.is_alive())
            finally:
                release.set()
                worker.join(4)
                closer.join(4)
            self.assertFalse(worker.is_alive())
            self.assertFalse(closer.is_alive())
        self.assertEqual(errors, [])
        self.assertIn("cancellation_requested", [note["phase"] for note in self.reopen_notes("cancel-close")])

    def test_another_runtime_ack_releases_original_local_note(self):
        self.submit("cross-runtime-ack")
        identity = {"execution_id": "cross-runtime-ack", "attempt": 0, "fence": 0}
        with patch.object(self.runtime._settlement_journal, "lifecycle_note", side_effect=OSError("unavailable")):
            self.assertFalse(self.runtime._diagnostic_note(identity, "receipt", {"state": "unknown"}))
        peer = Kernel.open_sqlite(self.path, {"work": lifecycle_handler}, isolation_mode="process")
        try:
            peer._retry_diagnostic_notes(time.monotonic() + 2)
            self.assertEqual([n["phase"] for n in self.reopen_notes("cross-runtime-ack")], ["receipt"])
            self.runtime._retry_diagnostic_notes(time.monotonic() + 2)
            self.assertFalse(self.runtime._diagnostics_block_admission("cross-runtime-ack"))
            self.assertEqual([n["phase"] for n in self.reopen_notes("cross-runtime-ack")], ["receipt"])
        finally:
            peer.close()

    def test_windows_containment_receipt_retries_and_preserves_exact_identity(self):
        self.submit("windows-containment")
        lease = self.runtime.kernel.claim_and_start("worker", execution_id="windows-containment")
        identity = {"execution_id": lease.execution_id, "attempt": lease.attempt, "fence": lease.fence}
        journal = self.runtime._settlement_journal
        self.assertTrue(self.runtime._diagnostic_note(identity, "supervisor_spawn_intent",
            {"source": "runtime_pre_spawn", "cleanup": "unknown"}, timeout_seconds=1))
        evidence = {"state": "confirmed", "source": "windows_job_containment"}
        with patch.object(journal, "lifecycle_note", side_effect=OSError("journal unavailable")):
            self.assertFalse(self.runtime._diagnostic_note(identity, "worker_tree_cleanup_observed", evidence))
            self.assertEqual(journal.inspect_supervisor_handoff(identity, timeout_seconds=1)
                             ["facts"]["worker_tree_cleanup"]["state"], "unknown")
        self.runtime._retry_diagnostic_notes(time.monotonic() + 2)
        fact = journal.inspect_supervisor_handoff(identity, timeout_seconds=1)["facts"]["worker_tree_cleanup"]
        self.assertEqual(fact["evidence"], evidence)
        other = {**identity, "fence": identity["fence"] + 1}
        self.assertEqual(journal.inspect_supervisor_handoff(other, timeout_seconds=1)
                         ["facts"]["worker_tree_cleanup"]["state"], "unknown")
        entry = journal.scan_supervisor_cleanup(timeout_seconds=1)["registrations"][0]
        self.assertEqual(entry["worker_tree_cleanup"], "confirmed")

    def test_posix_parent_containment_outbox_is_visible_to_exact_handoff_inspection(self):
        self.submit("posix-containment")
        lease = self.runtime.kernel.claim_and_start("worker", execution_id="posix-containment")
        identity = {"execution_id": lease.execution_id, "attempt": lease.attempt, "fence": lease.fence}
        evidence = {"state": "confirmed", "source": "posix_supervisor_containment"}
        journal = self.runtime._settlement_journal
        with patch.object(journal, "lifecycle_note", side_effect=OSError("journal unavailable")):
            self.assertFalse(self.runtime._diagnostic_note(identity, "worker_tree_cleanup_observed", evidence))
            self.assertEqual(journal.inspect_supervisor_handoff(identity, timeout_seconds=1)
                             ["facts"]["worker_tree_cleanup"]["state"], "unknown")
        self.runtime._retry_diagnostic_notes(time.monotonic() + 2)
        fact = journal.inspect_supervisor_handoff(identity, timeout_seconds=1)["facts"]["worker_tree_cleanup"]
        self.assertEqual(fact["evidence"], evidence)
        wrong = {**identity, "fence": identity["fence"] + 1}
        self.assertEqual(journal.inspect_supervisor_handoff(wrong, timeout_seconds=1)
                         ["facts"]["worker_tree_cleanup"]["state"], "unknown")

    def test_scoped_diagnostic_retries_transient_write_within_original_window(self):
        self.submit("transient-diagnostic")
        identity = {"execution_id": "transient-diagnostic", "attempt": 0, "fence": 0}
        journal = self.runtime._settlement_journal
        original = journal.lifecycle_note
        attempts = []

        def once_busy(*args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise TimeoutError("transient writer contention")
            return original(*args, **kwargs)

        with patch.object(journal, "lifecycle_note", side_effect=once_busy):
            self.assertTrue(self.runtime._diagnostic_note(identity, "receipt", {"state": "observed"},
                                                          timeout_seconds=1))
        self.assertEqual(len(attempts), 2)
        self.assertEqual([note["phase"] for note in self.reopen_notes("transient-diagnostic")], ["receipt"])

    def test_close_waits_for_diagnostic_writer_and_persists_retained_note(self):
        self.submit("close-writer")
        identity = {"execution_id": "close-writer", "attempt": 0, "fence": 0}
        self.runtime._diagnostic_retry_lock.acquire()
        try:
            self.assertFalse(self.runtime._diagnostic_note(identity, "receipt", {"state": "unknown"},
                                                           timeout_seconds=.01))
        except BaseException:
            self.runtime._diagnostic_retry_lock.release()
            raise
        release = threading.Timer(.3, self.runtime._diagnostic_retry_lock.release)
        release.start()
        try:
            self.runtime.close()
        finally:
            release.join()
        self.assertEqual([n["phase"] for n in self.reopen_notes("close-writer")], ["receipt"])

    def test_close_still_fails_closed_if_diagnostic_writer_remains_busy(self):
        self.submit("close-writer-busy")
        identity = {"execution_id": "close-writer-busy", "attempt": 0, "fence": 0}
        self.assertTrue(self.runtime._diagnostic_retry_lock.acquire())
        try:
            self.assertFalse(self.runtime._diagnostic_note(identity, "receipt", {"state": "unknown"},
                                                           timeout_seconds=.01))
            with self.assertRaises(_UnpersistedDiagnosticsError):
                self.runtime.close()
        finally:
            self.runtime._diagnostic_retry_lock.release()
        self.runtime.close()
        self.assertEqual([n["phase"] for n in self.reopen_notes("close-writer-busy")], ["receipt"])

    def test_receiver_ack_survives_outbox_ack_failure(self):
        self.submit("receiver-ack")
        identity = {"execution_id": "receiver-ack", "attempt": 0, "fence": 0}
        with patch.object(self.runtime.kernel, "lifecycle_ack", side_effect=OSError("ack unavailable")):
            self.assertTrue(self.runtime._diagnostic_note(identity, "receipt", {"state": "unknown"}, timeout_seconds=2))
            self.assertTrue(self.runtime._diagnostics_block_admission("receiver-ack"))
        self.runtime._retry_diagnostic_notes(time.monotonic() + 2)
        self.assertFalse(self.runtime._diagnostics_block_admission("receiver-ack"))
        self.assertEqual([n["phase"] for n in self.reopen_notes("receiver-ack")], ["receipt"])

    @unittest.skipUnless("fork" in multiprocessing.get_all_start_methods(), "requires fork")
    def test_cancel_reserves_before_control_mutation(self):
        self.submit("cancel-crash")
        process = multiprocessing.get_context("fork").Process(target=crash_after_cancel_commit, args=(self.path,))
        process.start()
        process.join(10)
        self.assertEqual(process.exitcode, 27)
        with contextlib.closing(sqlite3.connect(self.path)) as connection, connection:
            rows = connection.execute("SELECT attempt,fence,state FROM kernel_lifecycle_producers WHERE execution_id=?",
                                      ("cancel-crash",)).fetchall()
        self.assertEqual(rows, [(0, 0, "open")])
        self.assertEqual(self.runtime.kernel.get("cancel-crash").state, "cancelled")

    def test_uncertain_cancel_commit_keeps_producer_open(self):
        self.submit("cancel-uncertain")
        original = self.runtime.kernel.cancel
        def commit_then_raise(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("cancel acknowledgement lost")
        with patch.object(self.runtime.kernel, "cancel", side_effect=commit_then_raise):
            with self.assertRaisesRegex(OSError, "acknowledgement lost"):
                self.runtime.cancel("cancel-uncertain", expected_revision=self.runtime.kernel.get("cancel-uncertain").revision)
        with contextlib.closing(sqlite3.connect(self.path)) as connection, connection:
            states = connection.execute("SELECT state FROM kernel_lifecycle_producers WHERE execution_id=?",
                                        ("cancel-uncertain",)).fetchall()
        self.assertEqual(states, [("open",)])
        self.assertEqual(self.runtime.kernel.get("cancel-uncertain").state, "cancelled")

    def test_failed_execution_does_not_block_independent_target(self):
        self.submit("independent")
        self.submit("failed")
        journal = self.runtime._settlement_journal
        original = journal.lifecycle_note
        failed = {"execution_id": "failed", "attempt": 0, "fence": 0}
        def fail_one(identity, phase, evidence, **kwargs):
            if identity["execution_id"] == "failed":
                raise OSError("execution-specific failure")
            return original(identity, phase, evidence, **kwargs)
        with patch.object(journal, "lifecycle_note", side_effect=fail_one):
            self.assertFalse(self.runtime._diagnostic_note(failed, "first", {"state": "unknown"}))
            self.assertFalse(self.runtime._diagnostic_note(failed, "second", {"state": "unknown"}))
            self.assertTrue(self.runtime._diagnostics_block_admission("failed"))
            self.assertFalse(self.runtime._diagnostics_block_admission("independent"))
            self.assertTrue(self.runtime._diagnostics_block_admission())
            result = self.runtime.run_once()
            self.assertEqual(result.state, "succeeded")
            self.assertIn("execution_claimed", [note["phase"] for note in self.reopen_notes("independent")])
        deadline = time.monotonic() + 15
        phases = []
        while time.monotonic() < deadline:
            self.runtime._retry_diagnostic_notes(min(deadline, time.monotonic() + 2), wait_for_writer=True)
            phases = [note["phase"] for note in self.reopen_notes("failed")]
            self.assertIn(phases, ([], ["first"], ["first", "second"]))
            if phases == ["first", "second"] and not self.runtime._diagnostics_block_admission():
                break
        self.assertEqual(phases, ["first", "second"])
        self.assertFalse(self.runtime._diagnostics_block_admission())

    def test_concurrent_independent_note_survives_failed_writer(self):
        self.submit("blocked")
        self.submit("other")
        journal = self.runtime._settlement_journal
        original = journal.lifecycle_note
        entered, release = threading.Event(), threading.Event()
        results = {}
        def fail_one(identity, phase, evidence, **kwargs):
            if identity["execution_id"] == "blocked":
                entered.set()
                release.wait(2)
                raise OSError("specific write failure")
            return original(identity, phase, evidence, **kwargs)
        def publish(name):
            identity = {"execution_id": name, "attempt": 0, "fence": 0}
            results[name] = self.runtime._diagnostic_note(identity, "phase", {}, timeout_seconds=1)
        with patch.object(journal, "lifecycle_note", side_effect=fail_one):
            first = threading.Thread(target=publish, args=("blocked",))
            second = threading.Thread(target=publish, args=("other",))
            first.start()
            self.assertTrue(entered.wait(2))
            second.start()
            release.set()
            first.join(3)
            second.join(3)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(results, {"blocked": False, "other": True})
            self.assertEqual([n["phase"] for n in self.reopen_notes("other")], ["phase"])
        self.runtime._retry_diagnostic_notes(time.monotonic() + 2)
        self.assertFalse(self.runtime._diagnostics_block_admission())

    def test_retention_overflow_keeps_admission_closed_even_after_retry(self):
        self.submit("overflow")
        self.runtime._diagnostic_pending_capacity = 1
        identity = {"execution_id": "overflow", "attempt": 0, "fence": 0}
        with patch.object(self.runtime._settlement_journal, "lifecycle_note", side_effect=OSError("unavailable")):
            self.assertFalse(self.runtime._diagnostic_note(identity, "first", {"state": "unknown"}))
            self.assertFalse(self.runtime._diagnostic_note(identity, "second", {"state": "unknown"}))
        self.runtime._retry_diagnostic_notes(time.monotonic() + 1)
        self.assertTrue(self.runtime._diagnostics_block_admission())
        self.assertTrue(self.runtime._diagnostic_pending_overflow)
        self.assertEqual([note["phase"] for note in self.reopen_notes("overflow")], ["first"])
        # The lost second fact cannot be reconstructed; release the artificial
        # overflow only to permit this isolated test's temporary-store cleanup.
        self.runtime._diagnostic_pending_overflow = False


if __name__ == "__main__":
    unittest.main()
