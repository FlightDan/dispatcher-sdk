"""Real local worker interruption with a persistent fake remote provider."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import (
    Runtime, SandboxHandler, SandboxObservation, SandboxOutcomeUnknown,
    SandboxSpec, EffectRecoveryRequiredError, RetryPolicy, SandboxJournal,
)


@dataclass(frozen=True)
class FileBackend:
    root: str
    mode: str = "success"
    name: str = "file-test"
    revision: str = "file-test-v1"

    def _write(self, name, value):
        Path(self.root, name).write_text(json.dumps(value))

    def create(self, spec, *, operation_key, timeout):
        self._write("created", operation_key)
        self._write("alive", True)
        if self.mode == "lost_create":
            raise SandboxOutcomeUnknown("create reply lost")
        return "sandbox-1"

    def find(self, operation_key, *, timeout):
        if Path(self.root, "created").exists() and json.loads(Path(self.root, "created").read_text()) == operation_key:
            return ("sandbox-1",) if Path(self.root, "alive").exists() else ()
        return ()

    def start(self, sandbox_id, spec, *, timeout):
        self._write("started", sandbox_id)
        if self.mode == "lost_start" and not Path(self.root, "allow_start").exists():
            raise SandboxOutcomeUnknown("start reply lost")
        return "command-1"

    def inspect(self, sandbox_id, command_id, *, timeout):
        if self.mode == "running":
            time.sleep(0.01)
            return SandboxObservation("running")
        return SandboxObservation("succeeded", exit_code=0)

    def collect(self, sandbox_id, command_id, spec, *, timeout):
        self._write("collected", True)
        return {"stdout": "result", "artifact": "retained"}

    def terminate(self, sandbox_id, *, timeout):
        if Path(self.root, "reject_cleanup").exists():
            return False
        Path(self.root, "alive").unlink(missing_ok=True)
        self._write("terminated", True)
        return True


@unittest.skipUnless(os.name in {"posix", "nt"}, "requires native process isolation")
class SandboxRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.spec = SandboxSpec("fixture-image", "print('hello')", ("/usr/bin/python3",), "/tmp")

    def runtime(self, mode="success", timeout=10):
        handler = SandboxHandler(FileBackend(str(self.root), mode), str(self.root / "sandbox.db"),
                                 poll_interval=0.01, operation_timeout=0.2)
        runtime = Runtime(str(self.root / "kernel.db"), {handler.handler_id: handler})
        command = runtime.command(handler.handler_id, execution_id="x", idempotency_key="x",
                                  correlation_id="run", timeout_seconds=timeout, payload=self.spec.to_payload(),
                                  retry_policy=RetryPolicy(max_attempts=3))
        runtime.submit(command)
        return runtime, handler

    def test_result_is_durable_before_cleanup_and_committed_before_success(self):
        runtime, handler = self.runtime()
        with runtime:
            snapshot = runtime.run_once()
            self.assertEqual(snapshot.state, "succeeded")
            record = handler.journal().get("x")
            self.assertEqual(record["phase"], "collected")
            self.assertTrue(record["cleanup_confirmed"])
            self.assertEqual(record["result"], snapshot.result.value)
            self.assertEqual(runtime.kernel.get_effect(handler.effect_id("x")).state, "committed")
            self.assertFalse((self.root / "alive").exists())

    def test_timeout_kills_local_waiter_and_disposes_identified_remote(self):
        runtime, handler = self.runtime("running", timeout=4)
        with runtime:
            snapshot = runtime.run_once()
            self.assertEqual(snapshot.state, "recovery_required")
            self.assertTrue(handler.journal().get("x")["cleanup_confirmed"])
            self.assertFalse((self.root / "alive").exists())
            self.assertEqual(runtime.kernel.get_effect(handler.effect_id("x")).state, "indeterminate")

    def test_cancel_waits_for_remote_cleanup_even_when_effect_needs_recovery(self):
        runtime, handler = self.runtime("running", timeout=10)
        with runtime, ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(runtime.run_once)
            # Native interpreter startup has its own budget, separate from the
            # cancellation/cleanup boundary asserted after backend readiness.
            deadline = time.monotonic() + runtime._handler_start_timeout() + 5
            while (not (self.root / "started").exists() and not future.done()
                   and time.monotonic() < deadline):
                time.sleep(0.01)
            self.assertTrue((self.root / "started").exists(),
                            future.result() if future.done() else "worker startup did not finish")
            current = runtime.kernel.get("x")
            with self.assertRaises(EffectRecoveryRequiredError):
                runtime.cancel("x", expected_revision=current.revision)
            self.assertFalse((self.root / "alive").exists())
            self.assertTrue(handler.journal().get("x")["cleanup_confirmed"])
            self.assertEqual(future.result(timeout=15).state, "recovery_required")

    def test_lost_start_reply_never_reissues_command_and_cleanup_is_confirmed(self):
        runtime, handler = self.runtime("lost_start")
        with runtime:
            self.assertEqual(runtime.run_once().state, "recovery_required")
            record = handler.journal().get("x")
            self.assertEqual(record["phase"], "starting")
            self.assertIsNone(record["command_id"])
            self.assertTrue(record["cleanup_confirmed"])
            self.assertIsNone(runtime.run_once())

    def test_lost_create_reply_remains_unknown_after_empty_search_and_restart(self):
        runtime, handler = self.runtime("lost_create")
        self.assertEqual(runtime.run_once().state, "recovery_required")
        self.assertFalse((self.root / "alive").exists())
        self.assertFalse(handler.journal().get("x")["cleanup_confirmed"])
        with self.assertRaises(SandboxOutcomeUnknown):
            runtime.close()
        reopened = Runtime(str(self.root / "kernel.db"), {handler.handler_id: handler})
        self.assertEqual(reopened.recover_sandboxes()[0]["cleanup_confirmed"], False)
        self.assertIsNone(reopened.run_once())
        with self.assertRaises(SandboxOutcomeUnknown):
            reopened.close()

    def test_disposal_failure_preserves_result_and_recovery_retries_only_disposal(self):
        (self.root / "reject_cleanup").touch()
        runtime, handler = self.runtime()
        with runtime:
            self.assertEqual(runtime.run_once().state, "recovery_required")
            record = handler.journal().get("x")
            self.assertEqual(record["result"]["output"]["artifact"], "retained")
            self.assertFalse(record["cleanup_confirmed"])
            (self.root / "reject_cleanup").unlink()
            self.assertTrue(runtime.recover_sandboxes()[0]["cleanup_confirmed"])
            self.assertEqual(runtime.kernel.get("x").state, "recovery_required")
            self.assertEqual(handler.journal().get("x")["result"], record["result"])

    def test_explicit_not_applied_creates_new_generation_only_after_old_cleanup(self):
        runtime, handler = self.runtime("lost_start")
        with runtime:
            self.assertEqual(runtime.run_once().state, "recovery_required")
            old = handler.journal().get("x")
            self.assertTrue(old["cleanup_confirmed"])
            effect = runtime.kernel.get_effect(handler.effect_id("x"))
            runtime.kernel.resolve_effect(effect.effect_id, expected_revision=effect.revision,
                decision="not_applied", response=None, recovery_id="retry-confirmed-safe")
            (self.root / "allow_start").touch()
            self.assertEqual(runtime.run_once().state, "succeeded")
            latest = handler.journal().get("x")
            self.assertNotEqual(old["operation_key"], latest["operation_key"])
            archived = handler.journal().history("x")
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0]["record"]["operation_key"], old["operation_key"])
            self.assertEqual(archived[0]["record"]["sandbox_id"], old["sandbox_id"])

    def test_disposal_not_applied_recovery_does_not_reexecute_script(self):
        (self.root / "reject_cleanup").touch()
        runtime, handler = self.runtime()
        with runtime:
            snapshot = runtime.run_once()
            self.assertEqual(snapshot.state, "recovery_required")
            record = handler.journal().get("x")
            self.assertEqual(runtime.kernel.get_effect(handler.effect_id("x")).state, "committed")
            effect_id = handler.effect_id("x") + ":dispose:" + record["operation_key"]
            effect = runtime.kernel.get_effect(effect_id)
            self.assertEqual(effect.state, "indeterminate")
            runtime.kernel.resolve_effect(effect_id, expected_revision=effect.revision,
                decision="not_applied", response=None, recovery_id="retry-disposal")
            (self.root / "reject_cleanup").unlink()
            self.assertEqual(runtime.run_once().state, "succeeded")
            self.assertEqual(handler.journal().get("x")["operation_key"], record["operation_key"])
            self.assertEqual(handler.journal().history("x"), ())

    def test_applied_execution_recovery_collects_no_second_command(self):
        runtime, handler = self.runtime("lost_start")
        with runtime:
            self.assertEqual(runtime.run_once().state, "recovery_required")
            record = handler.journal().get("x")
            effect = runtime.kernel.get_effect(handler.effect_id("x"))
            observed = {"state": "succeeded", "exit_code": 0, "output": {"verified": True},
                        "sandbox_id": "sandbox-1", "command_id": "observed-command"}
            runtime.kernel.resolve_effect(effect.effect_id, expected_revision=effect.revision,
                decision="applied", response=observed, recovery_id="provider-evidence")
            self.assertEqual(runtime.run_once().result.value, observed)
            self.assertEqual(handler.journal().get("x")["operation_key"], record["operation_key"])
            self.assertEqual(handler.journal().history("x"), ())

    def test_applied_unknown_outcome_cannot_be_published_as_success(self):
        runtime, handler = self.runtime("lost_start")
        with runtime:
            self.assertEqual(runtime.run_once().state, "recovery_required")
            effect = runtime.kernel.get_effect(handler.effect_id("x"))
            runtime.kernel.resolve_effect(effect.effect_id, expected_revision=effect.revision,
                decision="applied", recovery_id="invalid-observation", response={
                    "state": "unknown", "exit_code": None, "output": {},
                    "sandbox_id": "sandbox-1", "command_id": None})
            result = runtime.run_once()
            self.assertEqual(result.state, "failed")
            self.assertEqual(result.result.error.code, "invalid_sandbox_recovery")

    def test_unsupported_provider_policy_fails_before_any_effect_or_remote_intent(self):
        from dispatcher_sdk.adapters import OpenSandboxBackend
        backend = OpenSandboxBackend("localhost:1")
        handler = SandboxHandler(backend, str(self.root / "journal.db"))
        spec = SandboxSpec("image", "echo ok", ("/bin/sh",), "/tmp", resources={"unsupported": "1"})
        with Runtime(self.root / "kernel.db", {handler.handler_id: handler}) as runtime:
            runtime.submit(runtime.command(handler.handler_id, execution_id="policy", idempotency_key="policy",
                correlation_id="r", timeout_seconds=10, payload=spec.to_payload()))
            result = runtime.run_once()
            self.assertEqual(result.state, "failed")
            self.assertEqual(result.result.error.code, "unsupported_resources")
            self.assertEqual(result.result.effect_ids, [])
            self.assertIsNone(handler.journal().get("policy"))


class SandboxJournalTests(unittest.TestCase):
    def test_old_generation_cannot_confirm_or_overwrite_new_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = SandboxJournal(str(Path(directory) / "journal.db"))
            spec = SandboxSpec("image", "echo ok", ("/bin/sh",), "/tmp")
            arguments = ("x", "effect", "provider", "v1", "handler", 1, spec)
            old = journal._begin(*arguments)
            journal.confirm_cleanup("x", operation_key=old, evidence={"provider_receipt": "absent"})
            new = journal._begin(*arguments)
            self.assertNotEqual(old, new)
            with self.assertRaises(SandboxOutcomeUnknown):
                journal.confirm_cleanup("x", operation_key=old, evidence="late old proof")
            with self.assertRaises(SandboxOutcomeUnknown):
                journal._update("x", operation_key=old, phase="collected", result={"stale": True})
            self.assertEqual(journal.get("x")["phase"], "creating")
            self.assertFalse(journal.get("x")["cleanup_confirmed"])
            self.assertEqual(len(journal.history("x")), 1)

    def test_same_revision_does_not_route_cleanup_to_a_different_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a", "b"):
                (root / name).mkdir()
                (root / name / "alive").touch()
            handlers = [SandboxHandler(FileBackend(str(root / name), name=name, revision="v1"),
                                       str(root / "journal.db")) for name in ("a", "b")]
            with Runtime(root / "kernel.db", {h.handler_id: h for h in handlers}) as runtime:
                target = handlers[1]
                spec = SandboxSpec("image", "echo ok", ("/bin/sh",), "/tmp")
                command = runtime.command(target.handler_id, execution_id="x", idempotency_key="x",
                                          correlation_id="r", timeout_seconds=1, payload=spec.to_payload())
                runtime.submit(command)
                runtime.kernel.cancel("x", expected_revision=1)
                journal = target.journal()
                operation = journal._begin("x", target.effect_id("x"), "b", "v1", target.handler_id, 1, spec)
                journal._update("x", operation_key=operation, sandbox_id="sandbox-1")
                self.assertTrue(runtime.recover_sandboxes()[0]["cleanup_confirmed"])
                self.assertTrue((root / "a" / "alive").exists())
                self.assertFalse((root / "b" / "alive").exists())

    def test_unavailable_backend_revision_is_reported_and_close_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = SandboxHandler(FileBackend(str(root)), str(root / "journal.db"))
            runtime = Runtime(root / "kernel.db", {target.handler_id: target})
            spec = SandboxSpec("image", "echo ok", ("/bin/sh",), "/tmp")
            command = runtime.command(target.handler_id, execution_id="x", idempotency_key="x",
                                      correlation_id="r", timeout_seconds=1, payload=spec.to_payload())
            runtime.submit(command)
            runtime.kernel.cancel("x", expected_revision=1)
            target.journal()._begin("x", target.effect_id("x"), target.backend.name, "old-revision", target.handler_id, 1, spec)
            self.assertEqual(runtime.recover_sandboxes()[0]["error"], "sandbox_backend_revision_unavailable")
            with self.assertRaises(SandboxOutcomeUnknown):
                runtime.close()

    def test_recovery_snapshot_cannot_delete_a_new_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = SandboxHandler(FileBackend(str(root)), str(root / "journal.db"))
            with Runtime(root / "kernel.db", {target.handler_id: target}) as runtime:
                spec = SandboxSpec("image", "echo ok", ("/bin/sh",), "/tmp")
                command = runtime.command(target.handler_id, execution_id="x", idempotency_key="x",
                    correlation_id="r", timeout_seconds=1, payload=spec.to_payload())
                runtime.submit(command)
                journal = target.journal()
                old = journal._begin("x", target.effect_id("x"), target.backend.name, target.backend.revision,
                                     target.handler_id, 1, spec)
                journal._update("x", operation_key=old, sandbox_id="old-sandbox")
                original_get = runtime.kernel.get

                def advance_generation(identity):
                    captured = original_get(identity)
                    journal.confirm_cleanup("x", operation_key=old, evidence="old resource confirmed absent")
                    lease = runtime.kernel.claim_and_start("new-owner", registry_revision=command.registry_revision)
                    new = journal._begin("x", target.effect_id("x"), target.backend.name, target.backend.revision,
                                         target.handler_id, 1, spec, lease=lease)
                    journal._update("x", operation_key=new, sandbox_id="new-sandbox")
                    (root / "alive").touch()
                    return captured

                with patch.object(runtime.kernel, "get", side_effect=advance_generation):
                    report = runtime.recover_sandboxes()
                self.assertFalse(report[0]["cleanup_confirmed"])
                self.assertTrue((root / "alive").exists())
                self.assertFalse(journal.get("x")["cleanup_confirmed"])
                self.assertEqual(runtime.kernel.get("x").state, "running")
                current = runtime.kernel.get("x")
                runtime.kernel.cancel("x", expected_revision=current.revision)
                target.cleanup("x", operation_key=journal.get("x")["operation_key"])

    def test_removed_handler_does_not_hide_its_registered_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = SandboxHandler(FileBackend(str(root)), str(root / "journal.db"))
            runtime = Runtime(root / "kernel.db", {target.handler_id: target})
            spec = SandboxSpec("image", "echo ok", ("/bin/sh",), "/tmp")
            command = runtime.command(target.handler_id, execution_id="x", idempotency_key="x",
                                      correlation_id="r", timeout_seconds=1, payload=spec.to_payload())
            runtime.submit(command)
            runtime.kernel.cancel("x", expected_revision=1)
            operation = target.journal()._begin("x", target.effect_id("x"), target.backend.name,
                                               target.backend.revision, target.handler_id, 1, spec)
            target.journal()._update("x", operation_key=operation, sandbox_id="sandbox-1")
            (root / "reject_cleanup").touch()
            with self.assertRaises(SandboxOutcomeUnknown):
                runtime.close()
            reopened = Runtime(root / "kernel.db", {}, isolation_mode="thread")
            self.assertEqual(reopened.recover_sandboxes()[0]["error"], "sandbox_handler_unavailable")
            with self.assertRaises(SandboxOutcomeUnknown):
                reopened.close()
            (root / "reject_cleanup").unlink()
            target.cleanup("x", operation_key=operation)

    def test_journal_cannot_be_bound_to_two_independent_kernel_stores(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handler = SandboxHandler(FileBackend(str(root)), str(root / "journal.db"))
            with Runtime(root / "first.db", {handler.handler_id: handler}):
                with self.assertRaisesRegex(ValueError, "another Kernel store"):
                    Runtime(root / "second.db", {handler.handler_id: handler})

    def test_invalid_durability_does_not_register_a_missing_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrong = SandboxHandler(FileBackend(str(root)), str(root / "journal.db"), durability="normal")
            with self.assertRaisesRegex(ValueError, "same durability"):
                Runtime(root / "kernel.db", {wrong.handler_id: wrong})
            correct = SandboxHandler(FileBackend(str(root)), str(root / "journal.db"))
            with Runtime(root / "kernel.db", {correct.handler_id: correct}) as runtime:
                self.assertEqual(runtime.recover_sandboxes(), ())

    def test_recovery_pages_past_unknown_earlier_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handler = SandboxHandler(FileBackend(str(root)), str(root / "journal.db"))
            runtime = Runtime(root / "kernel.db", {handler.handler_id: handler})
            spec = SandboxSpec("image", "echo ok", ("/bin/sh",), "/tmp")
            for identity in ("a", "b", "c"):
                command = runtime.command(handler.handler_id, execution_id=identity, idempotency_key=identity,
                    correlation_id="r", timeout_seconds=1, payload=spec.to_payload())
                runtime.submit(command)
                runtime.kernel.cancel(identity, expected_revision=1)
                operation = handler.journal()._begin(identity, handler.effect_id(identity), handler.backend.name,
                    handler.backend.revision, handler.handler_id, 1, spec)
                if identity != "a":
                    handler.journal()._update(identity, operation_key=operation, sandbox_id=identity)
            reports = runtime.recover_sandboxes(limit=1, all_pages=True)
            self.assertEqual([r["cleanup_confirmed"] for r in reports], [False, True, True])
            with self.assertRaises(SandboxOutcomeUnknown):
                runtime.close()
