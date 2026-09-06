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

    def _run(self, command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PIP_NO_CACHE_DIR"] = "1"
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
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
            for document in ("pyproject.toml", "README.md", "LICENSE", "NOTICE"):
                shutil.copy2(ROOT / document, distribution / document)
            self._run([sys.executable, "-c",
                       "from setuptools.build_meta import build_sdist; build_sdist('dist')"],
                      cwd=distribution)
            sdists = list((distribution / "dist").glob("*.tar.gz"))
            self.assertEqual(len(sdists), 1)
            rebuilt = root / "rebuilt"
            rebuilt.mkdir()
            with tarfile.open(sdists[0]) as archive:
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
            self.assertTrue(wheels[0].name.startswith("dispatcher_sdk-0.5.1-"))
            with zipfile.ZipFile(wheels[0]) as archive:
                packaged_python = {
                    name for name in archive.namelist() if name.endswith(".py")
                }
                metadata_name = next(name for name in archive.namelist()
                                     if name.endswith(".dist-info/METADATA"))
                metadata = email.message_from_bytes(archive.read(metadata_name))
                self.assertEqual(metadata["Name"], "dispatcher-sdk")
                self.assertEqual(metadata["Version"], "0.5.1")
                self.assertFalse(metadata.get_all("Requires-Dist", []))
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

            installed_suite = root / "installed-suite"
            shutil.copytree(ROOT / "tests", installed_suite / "tests",
                            ignore=shutil.ignore_patterns("__pycache__", "test_packaging.py",
                                                          "test_execution_kernel_isolated_consumer.py"))
            self._run([str(interpreter), "-m", "unittest", "discover", "-s", "tests", "-v"],
                      cwd=installed_suite)

            consumer = root / "consumer.py"
            consumer.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os
                    import multiprocessing
                    from pathlib import Path
                    import sys

                    import importlib.util
                    import dispatcher_sdk
                    from importlib.metadata import version
                    assert version("dispatcher-sdk") == "0.5.1"
                    assert importlib.util.find_spec("agent_dispatcher") is None
                    assert importlib.util.find_spec("agent_dispatcher_sdk") is None
                    assert not any(name.startswith("dispatcher_sdk.")
                                   for name in sys.modules)
                    from dispatcher_sdk.execution_kernel import (
                        ExecutionCommandV2,
                        Kernel,
                        RetryPolicy,
                    )


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
                    [str(interpreter), str(consumer), str(root / "sdk.sqlite3"), mode], cwd=root)
                sdk_observations.append(json.loads(completed.stdout))
            self.assertEqual([item["state"] for item in sdk_observations],
                             ["running", "running", "succeeded"])


if __name__ == "__main__":
    unittest.main()
