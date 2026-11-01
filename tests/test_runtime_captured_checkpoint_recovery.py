"""Recover a contained result only after its exact retained clock fact is acknowledged."""
import os
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionLease, Kernel, runtime as runtime_module
from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture


def _handler(payload, context):
    return {"execution_id": context.lease.execution_id, "pid": os.getpid()}


def _crash_after_receipt(path, connection, captured_sample=True):
    original_finish = process_runtime._finish_budget_capture
    original_capture_until = process_runtime._capture_budget_until
    injected = []

    def isolate_checkpoint_fault(envelope, capture, deadline, **kwargs):
        # Keep the parent's normal bounded capture retries running when the
        # supervisor packet arrives. Otherwise a coincident SQLite writer can
        # independently make the tracker unknown before this fixture injects
        # its retained checkpoint. The original deadline and all nontransient
        # failures remain in force; no captured error is cleared here.
        kwargs["stop_retry"] = None
        return original_capture_until(envelope, capture, deadline, **kwargs)

    def inject(owner, envelope, *, timeout_seconds=.1):
        if not injected:
            token = owner.kernel._begin_budget_sample(owner.execution_id, timeout_seconds=1, _owner=owner)
            captured = envelope.recheckpoint(sample=sample_clock())
            if captured_sample:
                owner._captured(token, captured)
            owner.finish_pending = lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("blocked"))
            injected.append(token)
        return original_finish(owner, envelope, timeout_seconds=timeout_seconds)

    try:
        with patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            runtime = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            command = runtime.command("handler", execution_id="execution", idempotency_key="execution",
                correlation_id="execution", timeout_seconds=15, payload={})
            runtime.submit(command)
            with patch.object(process_runtime, "_capture_budget_until", side_effect=isolate_checkpoint_fault), \
                 patch.object(process_runtime, "_finish_budget_capture", side_effect=inject), \
                 patch.object(runtime, "_finish_received_budget_checkpoints", side_effect=TimeoutError("blocked")):
                runtime.run_once(execution_id="execution")
            record = runtime._settlement_journal.pending(limit=10)[0]
            obligation = runtime.kernel.inspect_supervisor_obligations("execution")["obligations"][0]
            connection.send((injected, record, obligation))
    except BaseException as exc:
        connection.send(("error", repr(exc)))
    finally:
        connection.close()
        os._exit(0)


class CapturedCheckpointRecoveryTests(unittest.TestCase):
    def crash_receipt(self, path, *, captured_sample=True):
        context = multiprocessing.get_context("spawn")
        reader, writer = context.Pipe(duplex=False)
        process = context.Process(target=_crash_after_receipt, args=(path, writer, captured_sample))
        process.start()
        writer.close()
        self.assertTrue(reader.poll(30), "parent fixture did not report")
        data = reader.recv()
        process.join(10)
        self.assertEqual(process.exitcode, 0)
        self.assertNotEqual(data[0], "error", data)
        return data

    def test_only_exact_transient_owned_capture_is_recoverable(self):
        capture = _KernelBudgetCapture(None, "execution")
        envelope = BudgetEnvelope((), sample_clock())
        checkpoint = {"state": "unknown", "token": "sample", "captured_envelope": envelope.to_dict(),
                      "owned_transient": True}
        error = BudgetClockUnknownError("capture failed")
        error.__cause__ = TimeoutError("blocked")
        error.budget_sample_token = "sample"
        error.budget_sample_envelope = envelope
        check = process_runtime._recoverable_captured_checkpoint
        self.assertTrue(check(capture, error, checkpoint))
        self.assertFalse(check(capture, error, {**checkpoint, "token": "other"}))
        self.assertFalse(check(capture, error, {**checkpoint, "captured_envelope": None}))
        self.assertFalse(check(capture, error, {**checkpoint, "owned_transient": False}))
        self.assertFalse(check(object(), error, checkpoint))
        error.__cause__ = ValueError("clock continuity")
        self.assertFalse(check(capture, error, checkpoint))

    @unittest.skipUnless(os.name == "posix", "requires POSIX process containment")
    def test_cancellation_before_recovery_wins_and_retains_receipt(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            path = Path(directory) / "kernel.sqlite"
            tokens, record, _ = self.crash_receipt(path)
            runtime = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            try:
                before = runtime.kernel.get("execution")
                runtime.kernel.cancel("execution", expected_revision=before.revision)
                reports = runtime.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "superseded" for item in reports), reports)
                self.assertEqual(runtime.kernel.get("execution").state, "cancelled")
                self.assertEqual(runtime.kernel.inspect_supervisor_obligations("execution")["obligations"][0]["state"], "unresolved")
                receipt = runtime._settlement_journal.inspect("execution")[0]
                self.assertEqual(receipt["result"], record["result"])
                self.assertEqual(receipt["evidence"]["supervisor_completion_pending_checkpoint"],
                                 record["evidence"]["supervisor_completion_pending_checkpoint"])
            finally:
                runtime.close()

    @unittest.skipUnless(os.name == "posix", "requires POSIX process containment")
    def test_new_unresolved_sample_blocks_original_result_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            path = Path(directory) / "kernel.sqlite"
            tokens, record, _ = self.crash_receipt(path)
            runtime = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            try:
                checkpoint = record["evidence"]["budget_checkpoint"]["parent"]
                captured = BudgetEnvelope.from_dict(checkpoint["captured_envelope"])
                runtime.kernel._finish_received_budget_sample(tokens[0], "execution", captured, timeout_seconds=1)
                other = runtime.kernel._begin_budget_sample("execution", timeout_seconds=1)
                reports = runtime.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "pending" for item in reports), reports)
                self.assertEqual(runtime.kernel.get("execution").state, "running")
                self.assertEqual(runtime.kernel.inspect_supervisor_obligations("execution")["obligations"][0]["state"], "unresolved")
                retained = runtime._settlement_journal.pending(limit=10)[0]
                self.assertEqual(retained["result"], record["result"])
                self.assertEqual(retained["evidence"]["budget_checkpoint"]["parent"], checkpoint)
                runtime.kernel._finish_budget_sample(other, "execution", captured, timeout_seconds=1)
                reports = runtime.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "recorded" for item in reports), reports)
                self.assertEqual(runtime.kernel.get("execution").result.to_dict(), record["result"])
            finally:
                runtime.close()

    @unittest.skipUnless(os.name == "posix", "requires POSIX process containment")
    def test_unresolved_sample_blocks_result_without_cleanup_confirmation(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            path = Path(directory) / "kernel.sqlite"
            tokens, record, _ = self.crash_receipt(path)
            runtime = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            try:
                checkpoint = record["evidence"]["budget_checkpoint"]["parent"]
                captured = BudgetEnvelope.from_dict(checkpoint["captured_envelope"])
                runtime.kernel._finish_received_budget_sample(tokens[0], "execution", captured, timeout_seconds=1)
                other = runtime.kernel._begin_budget_sample("execution", timeout_seconds=1)
                # A separate capture error means this receipt cannot assert
                # the supervisor completion needed to release cleanup.
                evidence = dict(record["evidence"])
                evidence.pop("supervisor_completion_pending_checkpoint", None)
                evidence.pop("supervisor_completion", None)
                evidence["budget_capture_error"] = {"parent": {"state": "unknown"}}
                runtime._settlement_journal.settle(record, "pending", evidence, timeout_seconds=1)
                reports = runtime.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "pending" for item in reports), reports)
                self.assertEqual(runtime.kernel.get("execution").state, "running")
                self.assertEqual(runtime.kernel.inspect_supervisor_obligations("execution")["obligations"][0]["state"], "unresolved")
                retained = runtime._settlement_journal.pending(limit=10)[0]
                self.assertEqual(retained["result"], record["result"])
                self.assertEqual(retained["evidence"]["budget_checkpoint"]["parent"], checkpoint)
                runtime.kernel._finish_budget_sample(other, "execution", captured, timeout_seconds=1)
                reports = runtime.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "recorded" for item in reports), reports)
                self.assertEqual(runtime.kernel.get("execution").result.to_dict(), record["result"])
                self.assertEqual(runtime.kernel.inspect_supervisor_obligations("execution")["obligations"][0]["state"], "unresolved")
            finally:
                runtime.close()

    @unittest.skipUnless(os.name == "posix", "requires POSIX process containment")
    def test_armed_without_sample_never_grants_native_release(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            path = Path(directory) / "kernel.sqlite"
            tokens, record, _ = self.crash_receipt(path, captured_sample=False)
            checkpoint = record["evidence"]["budget_checkpoint"]["parent"]
            self.assertEqual(checkpoint["token"], tokens[0])
            self.assertIsNone(checkpoint["captured_envelope"])
            self.assertNotIn("supervisor_completion_pending_checkpoint", record["evidence"])
            runtime = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            try:
                reports = runtime.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "pending" for item in reports), reports)
                self.assertEqual(runtime.kernel.get("execution").state, "running")
                self.assertEqual(runtime.kernel.inspect_supervisor_obligations("execution")["obligations"][0]["state"], "unresolved")
                self.assertEqual(runtime._settlement_journal.pending(limit=10)[0]["result"], record["result"])
            finally:
                runtime.close()

    @unittest.skipUnless(os.name == "posix", "requires POSIX process containment")
    def test_mixed_receipt_replays_captured_ack_before_missing_sample_blocks(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            path = Path(directory) / "kernel.sqlite"
            tokens, record, _ = self.crash_receipt(path)
            runtime = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            try:
                checkpoint = record["evidence"]["budget_checkpoint"]["parent"]
                captured = BudgetEnvelope.from_dict(checkpoint["captured_envelope"])
                runtime.kernel._finish_received_budget_sample(tokens[0], "execution", captured, timeout_seconds=1)
                missing = runtime.kernel._begin_budget_sample("execution", timeout_seconds=1)
                # Model a receipt containing an ACK-lost captured fact and a
                # subsequently armed but uncaptured independent fact.
                evidence = {**record["evidence"], "budget_checkpoint": {
                    "parent": checkpoint, "supervisor": {"state": "unknown", "token": missing,
                                                           "captured_envelope": None}}}
                runtime._settlement_journal.settle(record, "pending", evidence, timeout_seconds=1)
                with patch.object(runtime.kernel, "_finish_received_budget_sample",
                                  wraps=runtime.kernel._finish_received_budget_sample) as finish:
                    reports = runtime.recover_completions(timeout_seconds=2)
                    repeated = runtime.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "pending" for item in reports), reports)
                self.assertTrue(any(item["state"] == "pending" for item in repeated), repeated)
                self.assertEqual(finish.call_count, 2)
                self.assertTrue(all(call.args[0] == tokens[0] for call in finish.call_args_list))
                self.assertEqual(runtime.kernel.get("execution").state, "running")
                self.assertEqual(runtime.kernel.inspect_supervisor_obligations("execution")["obligations"][0]["state"], "unresolved")
                retained = runtime._settlement_journal.pending(limit=10)[0]
                self.assertEqual(retained["result"], record["result"])
                self.assertEqual(retained["evidence"]["budget_checkpoint"], evidence["budget_checkpoint"])
                row = runtime.kernel._connection.execute(
                    "SELECT token FROM kernel_budget_samples WHERE execution_id=?", ("execution",)).fetchall()
                self.assertEqual([item[0] for item in row], [missing])
            finally:
                runtime.close()

    @unittest.skipUnless(os.name == "posix", "requires POSIX process containment")
    def test_deferred_resolved_result_stays_pending_with_uncaptured_marker_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            path = Path(directory) / "kernel.sqlite"
            _, original, _ = self.crash_receipt(path, captured_sample=False)
            runtime = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            try:
                # Create a synthetic deferred receipt with the same real
                # original result and unresolved marker as the crash fixture.
                journal = runtime._settlement_journal
                with journal._connection(1, write=True) as connection:
                    connection.execute("DELETE FROM settlement_records WHERE execution_id=?", ("execution",))
                evidence = {**original["evidence"], "resolved_result": original["result"]}
                deferred = journal.record(ExecutionLease.from_dict(original["lease"]),
                    {"kind": "completion_time_unknown", "outcome": {}}, evidence=evidence, timeout_seconds=1)
            finally:
                runtime.close()
            reopened = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            try:
                reports = reopened.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "pending" for item in reports), reports)
                snapshot = reopened.kernel.get("execution")
                self.assertEqual(snapshot.state, "running")
                self.assertIsNone(snapshot.result)
                self.assertEqual(reopened.kernel.inspect_supervisor_obligations("execution")["obligations"][0]["state"], "unresolved")
                retained = reopened._settlement_journal.pending(limit=10)[0]
                self.assertEqual(retained["deferred"], deferred["deferred"])
                self.assertEqual(retained["evidence"]["resolved_result"], original["result"])
                self.assertEqual(retained["evidence"]["budget_checkpoint"], original["evidence"]["budget_checkpoint"])
            finally:
                reopened.close()

    @unittest.skipUnless(os.name == "posix", "requires POSIX process containment")
    def test_reopen_acknowledges_original_sample_and_settles_original_result(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            path = Path(directory) / "kernel.sqlite"
            injected, record, obligation = self.crash_receipt(path)
            self.assertEqual(len(injected), 1)
            result = record["result"]
            self.assertIn("supervisor_completion_pending_checkpoint", record["evidence"], record)
            self.assertEqual(record["evidence"]["supervisor_completion_pending_checkpoint"]["result"], "captured")
            self.assertEqual(obligation["state"], "unresolved")
            reopened = Kernel.open_sqlite(path, {"handler": _handler}, isolation_mode="process")
            try:
                original_settle = reopened._settlement_journal.settle
                def lose_ack(record, state, evidence, **kwargs):
                    if state == "recorded":
                        raise TimeoutError("injected lost journal acknowledgement")
                    return original_settle(record, state, evidence, **kwargs)
                with patch.object(reopened._settlement_journal, "settle", side_effect=lose_ack):
                    reports = reopened.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "pending" for item in reports), reports)
                self.assertEqual(reopened.kernel.get("execution").result.to_dict(), result)
                reports = reopened.recover_completions(timeout_seconds=2)
                self.assertTrue(any(item["state"] == "recorded" for item in reports), reports)
                snapshot = reopened.kernel.get("execution")
                self.assertEqual(snapshot.state, "succeeded")
                self.assertEqual(snapshot.result.to_dict(), result)
                obligation = reopened.kernel.inspect_supervisor_obligations("execution")["obligations"][0]
                self.assertEqual(obligation["resolution"]["result_id"], result["result_id"])
                self.assertEqual(reopened.recover_completions(timeout_seconds=2), ())
            finally:
                reopened.close()
