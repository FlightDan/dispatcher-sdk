from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import os
import multiprocessing
from pathlib import Path
import sys
import tempfile
import time
import unittest

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.scripts import ScriptSpec, script_handlers


class ScriptSpecTests(unittest.TestCase):
    def test_spec_copies_argv_and_command_payload_and_requires_deadline(self):
        argv = [sys.executable, "-u"]
        spec = ScriptSpec("print('original')", argv, ".", "logs")
        argv.append("changed")
        payload = spec.to_payload()
        payload["interpreter"].append("changed")
        self.assertEqual(spec.interpreter, (sys.executable, "-u"))
        self.assertTrue(os.path.isabs(spec.cwd))
        with self.assertRaises(FrozenInstanceError):
            spec.source = "changed"
        kwargs = dict(execution_id="frozen", idempotency_key="frozen", registry_revision="r", correlation_id="run")
        with self.assertRaises(TypeError):
            spec.command(**kwargs)
        command = spec.command(**kwargs, timeout_seconds=2)
        command.payload["source"] = "changed"
        self.assertEqual(spec.to_payload()["source"], "print('original')")
        self.assertEqual(spec.command(**kwargs, timeout_seconds=2).retry_policy.max_attempts, 1)

    def test_invalid_invocations_and_unfrozen_payload_are_rejected(self):
        for values in ({"interpreter": ("python",)}, {"tail_bytes": True}, {"tail_bytes": 65537}, {"source": " "}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ScriptSpec(**(dict(source="pass", interpreter=(sys.executable,), cwd=".", output_dir=".") | values))
        payload = ScriptSpec("pass", (sys.executable,), ".", ".").to_payload()
        payload["cwd"] = "."
        with self.assertRaises(ValueError):
            ScriptSpec.from_payload(payload)

    def test_thread_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError, "process isolation"):
            Kernel.open_sqlite(Path(temp) / "kernel.db", script_handlers(), isolation_mode="thread")


@unittest.skipUnless(os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
                     "requires POSIX fork process supervision")
class ScriptExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = Kernel.open_sqlite(self.root / "kernel.db", script_handlers(), isolation_mode="process")
        self.addCleanup(self.runtime.close)

    def submit(self, source, *, timeout=5, tail=128):
        command = ScriptSpec(source, (sys.executable, "-u"), self.root, self.root / "logs", tail).command(
            execution_id="script-execution", idempotency_key="script-command",
            registry_revision=self.runtime.registry_revision, correlation_id="conversation-run",
            timeout_seconds=timeout,
        )
        self.runtime.submit(command)
        return command

    def test_success_freezes_submitted_source_and_retains_bounded_verified_logs(self):
        command = self.submit("import sys\nprint('x' * 200000)\nprint('error stream', file=sys.stderr)\nopen('effect.txt', 'w').write('done')\n", tail=64)
        command.payload["source"] = "raise RuntimeError('mutated after submit')"
        snapshot = self.runtime.run_once()
        self.assertEqual(snapshot.state, "succeeded")
        value = snapshot.result.value
        self.assertEqual(value["exit_code"], 0)
        self.assertEqual((self.root / "effect.txt").read_text(), "done")
        self.assertEqual(value["stdout"]["bytes"], 200001)
        self.assertEqual(len(value["stdout"]["tail"]), 64)
        for stream in ("stdout", "stderr"):
            actual = Path(value[stream]["path"]).read_bytes()
            self.assertEqual(value[stream]["sha256"], hashlib.sha256(actual).hexdigest())
        self.assertEqual(len(snapshot.result.effect_ids), 1)
        self.assertEqual(self.runtime.kernel.get_effect(snapshot.result.effect_ids[0]).state, "committed")
        self.assertIsNone(self.runtime.run_once())

    def test_nonzero_exit_is_failure_with_committed_outcome_and_stderr(self):
        self.submit("import sys\nprint('broken', file=sys.stderr)\nsys.exit(7)\n")
        snapshot = self.runtime.run_once()
        self.assertEqual(snapshot.state, "failed")
        self.assertEqual(snapshot.result.error.code, "script_exit_nonzero")
        self.assertEqual(snapshot.result.error.details["exit_code"], 7)
        self.assertEqual(snapshot.result.error.details["stderr"]["tail"], "broken\n")
        self.assertEqual(self.runtime.kernel.get_effect(snapshot.result.effect_ids[0]).state, "committed")

    def test_timeout_kills_script_and_parks_ambiguous_effect_without_terminal_result(self):
        self.submit("import time\nprint('started')\ntime.sleep(2)\nopen('escaped.txt', 'w').write('escaped')\n", timeout=0.3)
        snapshot = self.runtime.run_once()
        self.assertEqual(snapshot.state, "recovery_required")
        self.assertIsNone(snapshot.result)
        effect = self.runtime.kernel.get_effect(snapshot.recovery_effect_id)
        self.assertEqual(effect.state, "indeterminate")
        logs = list(Path(effect.request["output_root"]).glob("*/stdout.log"))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].read_text(), "started\n")
        time.sleep(2)
        self.assertFalse((self.root / "escaped.txt").exists())
        self.assertIsNone(self.runtime.run_once())
        self.assertEqual(self.runtime.kernel.result_outbox(), [])
