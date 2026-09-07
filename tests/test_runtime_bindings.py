"""Deployment changes preserve narrow identity without granting cross-handler authority."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from dispatcher_sdk.execution_kernel import Runtime, RegistryRevisionMismatchError


def first(payload, context):
    return payload


def second(payload, context):
    return [payload]


class RuntimeBindingsTests(unittest.TestCase):
    def test_unrelated_upgrade_drains_narrow_work_but_preserves_legacy_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "kernel.db")
            with Runtime(path, {"a": first}, isolation_mode="thread") as original:
                command = original.command("a", execution_id="narrow", idempotency_key="narrow",
                    correlation_id="run", timeout_seconds=1, payload=42)
                original.submit(command)
                legacy = replace(command, execution_id="legacy", idempotency_key="legacy",
                                 registry_revision=original.registry_revision)
                original.submit(legacy)
            with Runtime(path, {"a": first, "b": second}, isolation_mode="thread") as upgraded:
                result = upgraded.run_once()
                self.assertEqual(result.command.execution_id, "narrow")
                self.assertEqual(result.result.value, 42)
                self.assertIsNone(upgraded.run_once())
                self.assertEqual(upgraded.kernel.get("legacy").state, "queued")
                with self.assertRaises(RegistryRevisionMismatchError):
                    upgraded.submit(legacy)

    def test_changed_handler_cannot_accept_old_command(self):
        with Runtime(":memory:", {"a": first}, isolation_mode="thread") as old:
            command = old.command("a", execution_id="x", idempotency_key="x",
                                  correlation_id="r", timeout_seconds=1, payload=None)
        with Runtime(":memory:", {"a": second}, isolation_mode="thread") as new:
            with self.assertRaises(RegistryRevisionMismatchError):
                new.submit(command)
            new.kernel.submit(command)
            self.assertIsNone(new.run_once())

    def test_allowed_revision_for_other_handler_is_not_execution_authority(self):
        with Runtime(":memory:", {"a": first, "b": second}, isolation_mode="thread") as runtime:
            command = runtime.command("a", execution_id="x", idempotency_key="x",
                                      correlation_id="r", timeout_seconds=1, payload=None)
            forged = replace(command, handler_id="b")
            with self.assertRaises(RegistryRevisionMismatchError):
                runtime.submit(forged)
            runtime.kernel.submit(forged)
            snapshot = runtime.run_once()
            self.assertEqual(snapshot.state, "dead")
            self.assertEqual(snapshot.result.error.code, "registry_revision_mismatch")
