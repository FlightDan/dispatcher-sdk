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


@unittest.skipUnless(os.name == "nt" or (os.name == "posix" and "fork" in multiprocessing.get_all_start_methods()),
                     "requires a real supported process backend")
class PortableScriptStreamTests(unittest.TestCase):
    def test_no_newline_raw_stdout_survives_native_process_timeout(self):
        import json
        import sqlite3
        import traceback
        import dispatcher_sdk
        from tests._acceptance_evidence import retained_directory
        from tests._storage_evidence import StorageEvidence

        root = retained_directory("sdk-script-raw-timeout-")
        evidence = {"test": self.id(), "root": str(root), "interpreter": sys.executable,
                    "sdk_import": dispatcher_sdk.__file__, "execution_timeout": 2,
                    "script_sleep": 3, "post_timeout_sleep": 1.2, "capture_errors": [],
                    "snapshot_limits": {"total_seconds": .2, "tables_per_store": 32,
                        "rows_per_table": 32, "cell_bytes": 32768,
                        "oversized_cells": "NULL in snapshot; original retained in database"}}
        storage = StorageEvidence(root, self)
        storage.start(include_kernel=True)
        self.addCleanup(storage.stop)

        def error_facts(error):
            return {"type": type(error).__name__, "message": str(error),
                    "traceback": traceback.format_exc(),
                    "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                    "sqlite_errorname": getattr(error, "sqlite_errorname", None)}

        def save_evidence(phase="cleanup"):
            try:
                storage.save(phase=phase, checkpoint=evidence)
                (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            except BaseException as error:
                evidence["capture_errors"].append({"phase": phase, **error_facts(error)})
                print("script_raw_timeout_capture_error=" + json.dumps(evidence["capture_errors"][-1]), flush=True)
                if "original_error" not in evidence and "cleanup_error" not in evidence:
                    raise
            finally:
                print("script_raw_timeout_evidence=" + str(root / "evidence.json"), flush=True)

        self.addCleanup(save_evidence)
        try:
            runtime = Kernel.open_sqlite(root / "kernel.db", script_handlers(), isolation_mode="process")

            def close_runtime():
                try:
                    runtime.close()
                    evidence["runtime_closed"] = True
                except BaseException as error:
                    evidence["cleanup_error"] = error_facts(error)
                    raise  # unittest records cleanup separately from the original failure.

            self.addCleanup(close_runtime)
            source = "import sys,time\nsys.stdout.buffer.write(b'raw-without-newline\\xff')\nsys.stdout.flush()\ntime.sleep(3)\nopen('escaped', 'w').write('escaped')\n"
            command = ScriptSpec(source, (sys.executable, "-u"), root, root / "logs").command(
                execution_id="raw-timeout", idempotency_key="raw-timeout", registry_revision=runtime.registry_revision,
                correlation_id="raw-timeout", timeout_seconds=2)
            evidence["command"] = command.to_dict()
            runtime.submit(command)
            began = time.monotonic()
            result = runtime.run_once()
            evidence.update(run_once_elapsed=time.monotonic() - began, result=result.to_dict())
            self.assertEqual("recovery_required", result.state)
            effect = runtime.kernel.get_effect(result.recovery_effect_id)
            evidence["effect"] = effect.to_dict()
            logs = list(Path(effect.request["output_root"]).glob("*/stdout.log"))
            evidence["stdout_logs"] = [str(path) for path in logs]
            self.assertEqual(1, len(logs))
            raw = logs[0].read_bytes()
            evidence["stdout"] = {"path": str(logs[0]), "bytes": len(raw),
                                  "raw_hex": raw[:4096].hex(), "truncated": len(raw) > 4096}
            self.assertEqual(b"raw-without-newline\xff", raw)
            observation = runtime.observe("raw-timeout")
            evidence["observation"] = observation
            self.assertEqual(20, observation["metrics"]["stdout_bytes"]["count"])
            time.sleep(1.2)
            evidence["escaped_exists"] = (root / "escaped").exists()
            self.assertFalse((root / "escaped").exists())
        except BaseException as error:
            evidence["original_error"] = error_facts(error)
            raise
        finally:
            # These are read-only diagnostics after the original assertions;
            # retained stores remain available even when collection is partial.
            snapshot = []
            deadline = time.monotonic() + .2
            for database in (root / "kernel.db", root / "kernel.db.observations.sqlite3",
                             root / "kernel.db.settlements.sqlite3"):
                connection = None
                record = {"path": str(database)}
                try:
                    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0)
                    connection.row_factory = sqlite3.Row
                    connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
                    record["tables"] = {}
                    tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 32").fetchall()
                    for table in tables:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("raw storage evidence snapshot budget elapsed")
                        name = table["name"].replace('"', '""')
                        columns = connection.execute(f'PRAGMA table_info("{name}")').fetchall()
                        projection = ",".join('CASE WHEN length(CAST("' + column["name"].replace('"', '""') +
                            '" AS BLOB))<=32768 THEN "' + column["name"].replace('"', '""') + '" END AS "' +
                            column["name"].replace('"', '""') + '"' for column in columns)
                        rows = connection.execute(f'SELECT {projection} FROM "{name}" ORDER BY rowid DESC LIMIT 32').fetchall()
                        record["tables"][table["name"]] = [dict(row) for row in rows]
                except Exception as error:
                    record["error"] = error_facts(error)
                finally:
                    if connection is not None:
                        try:
                            connection.close()
                        except Exception as error:
                            record["close_error"] = error_facts(error)
                snapshot.append(record)
            evidence["raw_storage_snapshot"] = snapshot
            save_evidence(phase="before_cleanup")


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
        # Leave enough time for the isolated process to prepare and persist its
        # effect before the business deadline, without allowing the script to
        # reach the side effect after the supervisor kills it.
        self.submit("import time\nprint('started')\ntime.sleep(3)\nopen('escaped.txt', 'w').write('escaped')\n", timeout=2.0)
        snapshot = self.runtime.run_once()
        self.assertEqual(snapshot.state, "recovery_required")
        self.assertIsNone(snapshot.result)
        effect = self.runtime.kernel.get_effect(snapshot.recovery_effect_id)
        self.assertEqual(effect.state, "indeterminate")
        logs = list(Path(effect.request["output_root"]).glob("*/stdout.log"))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].read_text(), "started\n")
        time.sleep(3)
        self.assertFalse((self.root / "escaped.txt").exists())
        self.assertIsNone(self.runtime.run_once())
        self.assertEqual(self.runtime.kernel.result_outbox(), [])
