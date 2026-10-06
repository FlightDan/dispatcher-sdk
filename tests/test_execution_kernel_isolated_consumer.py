from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile
import email
import textwrap
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SDK_SOURCE = ROOT / "src" / "dispatcher_sdk"


class IsolatedExecutionKernelConsumerTests(unittest.TestCase):
    """Prove the Kernel can be packaged and consumed without Dispatcher code."""

    def test_kernel_imports_only_standard_library_and_itself(self) -> None:
        for source in (SDK_SOURCE / "execution_kernel").glob("*.py"):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    modules = [node.module or ""]
                else:
                    continue
                for module in modules:
                    self.assertIn(module.split(".")[0], sys.stdlib_module_names,
                                  msg=f"external Kernel import in {source}: {module}")

    def _run(self, command: list[str], *, cwd: Path,
             timeout: float = 300,
             evidence_directory: Path | None = None) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PIP_NO_CACHE_DIR"] = "1"

        def record(stdout, stderr, returncode, *, timed_out=False):
            if evidence_directory is None:
                return
            evidence_directory.mkdir(parents=True, exist_ok=True)
            for name, value in (("stdout.log", stdout), ("stderr.log", stderr)):
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="replace")
                (evidence_directory / name).write_text(value or "", encoding="utf-8")
            (evidence_directory / "command.json").write_text(json.dumps({
                "command": command, "cwd": str(cwd), "timeout_seconds": timeout,
                "returncode": returncode, "timed_out": timed_out,
            }, indent=2), encoding="utf-8")

        try:
            completed = subprocess.run(
                command, cwd=cwd, env=environment, capture_output=True,
                text=True, check=False, timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            record(error.stdout, error.stderr, None, timed_out=True)
            def tail(value):
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="replace")
                return (value or "")[-8000:]

            self.fail(f"command timed out after {timeout}s: {command!r}\n"
                      f"stdout tail:\n{tail(error.stdout)}\nstderr tail:\n{tail(error.stderr)}")
        record(completed.stdout, completed.stderr, completed.returncode)
        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                f"command failed: {command!r}\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            ),
        )
        return completed

    def test_kernel_only_wheel_restarts_with_just_path_and_handler(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            distribution = root / "distribution"
            distribution.mkdir()
            shutil.copytree(ROOT / "src", distribution / "src",
                            ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            for document in ("pyproject.toml", "MANIFEST.in", "README.md", "README.zh-CN.md",
                             "LICENSE", "NOTICE", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md",
                             "PROVENANCE.md", "SOURCE_MANIFEST.json", "RELEASING.md"):
                shutil.copy2(ROOT / document, distribution / document)
            for directory in ("docs", "examples", "tests", "scripts", "wiki", "DocsforAgents"):
                shutil.copytree(ROOT / directory, distribution / directory,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            self._run([sys.executable, "-c",
                       "from setuptools.build_meta import build_sdist; build_sdist('dist')"],
                      cwd=distribution)
            sdists = list((distribution / "dist").glob("*.tar.gz"))
            self.assertEqual(len(sdists), 1)
            rebuilt = root / "rebuilt"
            rebuilt.mkdir()
            with tarfile.open(sdists[0]) as archive:
                source_root = archive.getmembers()[0].name.split("/")[0]
                members = set(archive.getnames())
                for relative in ("MANIFEST.in", "RELEASING.md", "SOURCE_MANIFEST.json", "README.zh-CN.md",
                                 "docs/EXECUTION_OBSERVABILITY.md", "docs/EXECUTION_OBSERVABILITY_ACCEPTANCE.md",
                                 "examples/execution_observability.py", "tests/test_runtime_settlement.py",
                                 "scripts/release_candidate.py", "wiki/Home.md", "DocsforAgents/README.md"):
                    self.assertIn(f"{source_root}/{relative}", members)
                for member in archive.getmembers():
                    self.assertFalse(member.issym() or member.islnk())
                    self.assertTrue((rebuilt / member.name).resolve().is_relative_to(rebuilt.resolve()))
                archive.extractall(rebuilt, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
            distribution = next(rebuilt.iterdir())

            wheelhouse = root / "wheelhouse"
            wheelhouse.mkdir()
            self._run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    ".",
                    "--no-build-isolation",
                    "--no-deps",
                    "--wheel-dir",
                    str(wheelhouse),
                ],
                cwd=distribution,
            )
            wheels = tuple(wheelhouse.glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            self.assertTrue(wheels[0].name.startswith("dispatcher_sdk-0.7.1-"))
            with zipfile.ZipFile(wheels[0]) as archive:
                self.assertIn("dispatcher_sdk/py.typed", archive.namelist())
                packaged_python = {
                    name for name in archive.namelist() if name.endswith(".py")
                }
                metadata_name = next(name for name in archive.namelist()
                                     if name.endswith(".dist-info/METADATA"))
                metadata = email.message_from_bytes(archive.read(metadata_name))
                self.assertEqual(metadata["Name"], "dispatcher-sdk")
                self.assertEqual(metadata["Version"], "0.7.1")
                requirements = metadata.get_all("Requires-Dist", [])
                self.assertEqual(len(requirements), 1)
                self.assertRegex(requirements[0], r'^opensandbox\s*==\s*0\.1\.16\s*;\s*extra == [\"\']opensandbox[\"\']$')
                self.assertEqual(metadata.get_all("Provides-Extra"), ["opensandbox"])
                self.assertFalse(any(name.endswith("entry_points.txt") for name in archive.namelist()))
                for document in ("LICENSE", "NOTICE"):
                    entries = [name for name in archive.namelist()
                               if ".dist-info/" in name and name.endswith("/" + document)]
                    self.assertEqual(len(entries), 1)
                    self.assertEqual(archive.read(entries[0]),
                                     (ROOT / document).read_bytes())
            expected_python = {"dispatcher_sdk/" + str(path.relative_to(SDK_SOURCE)).replace("\\", "/")
                               for path in SDK_SOURCE.rglob("*.py")}
            self.assertEqual(packaged_python, expected_python)
            self.assertTrue(all(name.startswith("dispatcher_sdk/")
                                for name in packaged_python))

            virtualenv = root / "venv"
            self._run([sys.executable, "-m", "venv", str(virtualenv)], cwd=root)
            interpreter = virtualenv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            self._run(
                [
                    str(interpreter),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    str(wheels[0]),
                ],
                cwd=root,
            )

            # A public application consumer runs outside the source tree and
            # reuses this wheel/interpreter. Its evidence survives this test's
            # temporary install, including failures before the full suite.
            evidence_parent = os.environ.get("SDK_ACCEPTANCE_EVIDENCE_DIR")
            if evidence_parent:
                Path(evidence_parent).mkdir(parents=True, exist_ok=True)
            evidence = Path(tempfile.mkdtemp(prefix="sdk-observability-consumer-", dir=evidence_parent))
            public_consumer = root / "public-consumer"
            public_consumer.mkdir()
            script = public_consumer / "sdk_observability_acceptance.py"
            shutil.copy2(ROOT / "examples" / script.name, script)
            print("sdk_observability_consumer_artifact=" + str(evidence), flush=True)
            self._run([str(interpreter), str(script), "--evidence-dir", str(evidence)],
                      cwd=public_consumer, timeout=180)
            summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
            environment_record = json.loads((evidence / "environment.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["passed"])
            self.assertEqual(summary["scenarios"], ["success", "failure", "budget", "silence", "cleanup"])
            self.assertTrue(Path(environment_record["sdk_import"]).is_relative_to(virtualenv))
            if sys.platform == "linux" or os.name == "nt":
                supervisor_example = public_consumer / "managed_stall_supervisor.py"
                shutil.copy2(ROOT / "examples" / supervisor_example.name, supervisor_example)
                self._run([str(interpreter), str(supervisor_example), "--evidence-dir",
                           str(evidence / "managed-stall-example" / "workspace")], cwd=public_consumer,
                          timeout=30, evidence_directory=evidence / "managed-stall-example")

            installed_suite = root / "installed-suite"
            shutil.copytree(ROOT / "tests", installed_suite / "tests",
                            ignore=shutil.ignore_patterns("__pycache__", "test_packaging.py",
                                                          "test_execution_kernel_isolated_consumer.py"))
            # The contention test exercises a checkout CLI against the installed
            # wheel; copy only that fixture, never the SDK source tree.
            (installed_suite / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts" / "benchmark_sqlite_contention.py",
                         installed_suite / "scripts" / "benchmark_sqlite_contention.py")
            shutil.copy2(ROOT / "scripts" / "release_candidate.py",
                         installed_suite / "scripts" / "release_candidate.py")
            self._run([str(interpreter), "-m", "unittest", "discover", "-s", "tests", "-v"],
                      # This runs the complete installed suite, including SQLite
                      # FULL durability fixtures; it needs its own suite budget.
                      cwd=installed_suite, timeout=900,
                      evidence_directory=evidence / "installed-suite")

            consumer = root / "consumer.py"
            consumer.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os
                    import multiprocessing
                    from pathlib import Path
                    import sys
                    import time

                    import importlib.util
                    import dispatcher_sdk
                    from importlib.metadata import version
                    assert version("dispatcher-sdk") == "0.7.1"
                    assert importlib.util.find_spec("agent_dispatcher") is None
                    assert importlib.util.find_spec("agent_dispatcher_sdk") is None
                    assert not any(name.startswith("dispatcher_sdk.")
                                   for name in sys.modules)
                    from dispatcher_sdk.execution_kernel import (
                        ExecutionCommandV2,
                        Kernel,
                        RetryPolicy,
                    )
                    from dispatcher_sdk.adapters import OpenSandboxBackend, verify_backend
                    assert "opensandbox" not in sys.modules


                    def echo(payload, context):
                        return {
                            "echo": payload["value"],
                            "attempt": context.lease.attempt,
                        }


                    def main():
                        database = Path(sys.argv[1])
                        mode = sys.argv[2]
                        with Kernel.open_sqlite(
                            database,
                            {("consumer.echo", 1): echo},
                            isolation_mode=("process" if os.name == "posix" and
                                            "fork" in multiprocessing.get_all_start_methods() else "thread"),
                        ) as runtime:
                            if mode.startswith("sdk-"):
                                from dispatcher_sdk.orchestrator import Orchestrator
                                sdk = Orchestrator(database, runtime.kernel, runtime=runtime)
                                if mode == "sdk-seed":
                                    run = sdk.create_run("application", command_id="create", input={})
                                    assert run["tasks"] == {}
                                    assert runtime.kernel.events_since(0) == []
                                    command = ExecutionCommandV2(
                                        execution_id="sdk-execution", idempotency_key="sdk-command",
                                        registry_revision=runtime.registry_revision,
                                        correlation_id="application", causation_id=None,
                                        handler_id="consumer.echo", handler_contract_version=1,
                                        retry_policy=RetryPolicy(), timeout_seconds=5,
                                        payload={"value": "application-owned"},
                                    )
                                    sdk.apply_operations(
                                        "application", command_id="start", expected_revision=0,
                                        operations=[
                                            {"kind": "add_task", "task_id": "work", "command": command.to_dict()},
                                            {"kind": "dispatch", "task_id": "work"},
                                        ],
                                    )
                                    # Exit with a committed SDK outbox, before Kernel delivery.
                                    assert runtime.kernel.events_since(0) == []
                                elif mode == "sdk-resume":
                                    sdk.flush()
                                    runtime.run_once()
                                    sdk.pump_results()
                                    assert sdk.get_run("application")["state"] == "running"
                                elif mode == "sdk-verify":
                                    claims = sdk.claim_results(owner="application", lease_seconds=30, limit=1)
                                    assert len(claims) == 1
                                    claim = claims[0]
                                    assert claim["result"]["value"]["echo"] == "application-owned"
                                    sdk.acknowledge_result(claim["result"]["result_id"],
                                                           lease_id=claim["lease_id"], fence=claim["fence"])
                                    run = sdk.get_run("application")
                                    sdk.apply_operations(
                                        "application", command_id="finish", expected_revision=run["revision"],
                                        operations=[{"kind": "finish", "state": "succeeded"}],
                                    )
                                else:
                                    raise AssertionError(mode)
                                run = sdk.get_run("application")
                                assert importlib.util.find_spec("agent_dispatcher") is None
                                print(json.dumps({"mode": mode, "state": run["state"],
                                                  "package_file": dispatcher_sdk.__file__}))
                                return
                            if mode == "seed":
                                command = ExecutionCommandV2(
                                    execution_id="isolated-execution",
                                    idempotency_key="isolated-command",
                                    registry_revision=runtime.registry_revision,
                                    correlation_id="isolated-run",
                                    causation_id=None,
                                    handler_id="consumer.echo",
                                    handler_contract_version=1,
                                    retry_policy=RetryPolicy(
                                        max_attempts=1,
                                        initial_backoff_seconds=0,
                                        backoff_multiplier=1,
                                        max_backoff_seconds=0,
                                        retry_timeouts=False,
                                    ),
                                    timeout_seconds=5,
                                    payload={"value": "durable"},
                                )
                                snapshot = runtime.submit(command)
                            elif mode == "resume":
                                snapshot = runtime.run_once()
                                deadline = time.monotonic() + snapshot.command.timeout_seconds
                                while snapshot.state == "running" and time.monotonic() < deadline:
                                    remaining = deadline-time.monotonic()
                                    if remaining <= 0:
                                        break
                                    runtime.recover_completions(timeout_seconds=min(.1, remaining))
                                    remaining = deadline-time.monotonic()
                                    if remaining <= 0:
                                        break
                                    with runtime.kernel._control_lock(remaining):
                                        snapshot = runtime.kernel.get("isolated-execution")
                                    if snapshot.state == "running":
                                        time.sleep(min(.01, max(0., deadline-time.monotonic())))
                            elif mode == "verify":
                                snapshot = runtime.kernel.get("isolated-execution")
                            else:
                                raise AssertionError(mode)

                            print(json.dumps({
                                "mode": mode,
                                "state": snapshot.state,
                                "value": (
                                    None if snapshot.result is None else snapshot.result.value
                                ),
                                "package_file": dispatcher_sdk.__file__,
                                "forbidden_modules": sorted(
                                    name for name in sys.modules
                                    if name.startswith((
                                        "agent_dispatcher.dev_application",
                                        "agent_dispatcher.control_plane",
                                        "agent_dispatcher.workflow_ops",
                                    ))
                                ),
                            }, sort_keys=True))


                    if __name__ == "__main__":
                        main()
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            database = root / "consumer.sqlite3"
            observations = []
            for mode in ("seed", "resume", "verify"):
                completed = self._run(
                    [str(interpreter), str(consumer), str(database), mode],
                    cwd=root,
                    evidence_directory=evidence / "restart" / mode,
                )
                observations.append(json.loads(completed.stdout))

            self.assertEqual([item["state"] for item in observations], [
                "queued",
                "succeeded",
                "succeeded",
            ])
            self.assertEqual(observations[-1]["value"], {
                "attempt": 1,
                "echo": "durable",
            })
            self.assertTrue(
                all(item["forbidden_modules"] == [] for item in observations)
            )
            self.assertTrue(
                all(str(virtualenv) in item["package_file"] for item in observations)
            )
            sdk_observations = []
            for mode in ("sdk-seed", "sdk-resume", "sdk-verify"):
                completed = self._run(
                    [str(interpreter), str(consumer), str(root / "sdk.sqlite3"), mode], cwd=root,
                    evidence_directory=evidence / "restart" / mode)
                sdk_observations.append(json.loads(completed.stdout))
            self.assertEqual([item["state"] for item in sdk_observations],
                             ["running", "running", "succeeded"])
            # Retain the exact sdist and its rebuilt, installed wheel only
            # after all package, public, full-suite and restart assertions pass.
            # Release publishing consumes these files without another build.
            package_export = os.environ.get("SDK_RELEASE_PACKAGE_DIR")
            if package_export:
                destination = Path(package_export)
                destination.mkdir(parents=True, exist_ok=True)
                for package in (sdists[0], wheels[0]):
                    shutil.copy2(package, destination / package.name)


if __name__ == "__main__":
    unittest.main()
