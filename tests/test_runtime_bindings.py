"""Deployment changes preserve narrow identity without granting cross-handler authority."""

from dataclasses import replace
import json
import sys
import time
import traceback
import unittest

from dispatcher_sdk.execution_kernel import Runtime, RegistryRevisionMismatchError
from tests._acceptance_evidence import retained_directory


def first(payload, context):
    return payload


def second(payload, context):
    return [payload]


class RuntimeBindingsTests(unittest.TestCase):
    def test_unrelated_upgrade_drains_narrow_work_but_preserves_legacy_binding(self):
        root = retained_directory("sdk-runtime-binding-upgrade-")
        path = str(root / "kernel.db")
        evidence = {"test": self.id(), "interpreter": sys.executable,
                    "runtime_import": sys.modules[Runtime.__module__].__file__,
                    "timeout_seconds": 1, "timestamps": {"original_open_began": time.monotonic()}}
        timestamps = evidence["timestamps"]
        with Runtime(path, {"a": first}, isolation_mode="thread") as original:
            command = original.command("a", execution_id="narrow", idempotency_key="narrow",
                correlation_id="run", timeout_seconds=1, payload=42)
            original.submit(command)
            legacy = replace(command, execution_id="legacy", idempotency_key="legacy",
                             registry_revision=original.registry_revision)
            original.submit(legacy)
            evidence.update(command=command.to_dict(), legacy_command=legacy.to_dict(),
                            original_registry_revision=original.registry_revision)
            timestamps["original_submitted"] = time.monotonic()
        timestamps["original_closed"] = time.monotonic()
        timestamps["upgraded_open_began"] = time.monotonic()
        with Runtime(path, {"a": first, "b": second}, isolation_mode="thread") as upgraded:
            timestamps["upgraded_opened"] = time.monotonic()
            evidence["upgraded_registry_revision"] = upgraded.registry_revision
            try:
                timestamps["run_once_began"] = time.monotonic()
                result = upgraded.run_once()
                timestamps["run_once_returned"] = time.monotonic()
                evidence["returned_snapshot"] = None if result is None else result.to_dict()
                self.assertEqual(result.command.execution_id, "narrow")
                self.assertEqual(result.result.value, 42)
                self.assertIsNone(upgraded.run_once())
                self.assertEqual(upgraded.kernel.get("legacy").state, "queued")
                with self.assertRaises(RegistryRevisionMismatchError):
                    upgraded.submit(legacy)
                evidence["passed"] = True
            except BaseException as error:
                evidence["original_error"] = {"type": type(error).__name__, "message": str(error),
                                              "traceback": traceback.format_exc()}
                timestamps["failure_before_close"] = time.monotonic()
                try:
                    with upgraded.kernel._control_lock(.1):
                        evidence["snapshots"] = {execution_id: upgraded.kernel.get(execution_id).to_dict()
                                                 for execution_id in ("narrow", "legacy")}
                        evidence["events"] = [event.to_dict() for event in
                                              upgraded.kernel.events_since(0, limit=50)]
                except Exception as capture_error:
                    evidence["kernel_capture_error"] = {"type": type(capture_error).__name__,
                                                        "message": str(capture_error)}
                try:
                    evidence["observation"] = upgraded.observe("narrow", timeout=.5)
                except Exception as capture_error:
                    evidence["observation_capture_error"] = {"type": type(capture_error).__name__,
                                                             "message": str(capture_error)}
                raise
            finally:
                timestamps["capture_before_close"] = time.monotonic()
                try:
                    (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                except Exception as capture_error:
                    print("runtime_binding_capture_error=" + repr(capture_error), flush=True)
                print("runtime_binding_evidence=" + str(root / "evidence.json"), flush=True)

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
