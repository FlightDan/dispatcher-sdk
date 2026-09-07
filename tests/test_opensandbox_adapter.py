"""Provider boundary tests with fake official clients, not live sandbox tests.

The live Docker validation and its environment blocker are recorded separately.
"""

import base64
from dataclasses import replace
import importlib
import json
import math
import pickle
import shlex
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dispatcher_sdk.adapters import OpenSandboxBackend
from dispatcher_sdk.execution_kernel.sandbox_contracts import (
    SandboxBackend, SandboxObservation, SandboxOutcomeUnknown, SandboxPolicyError,
    SandboxResourceMissing, SandboxSpec,
)

adapter_module = importlib.import_module("dispatcher_sdk.adapters.opensandbox")


class ProviderFailure(Exception):
    def __init__(self, status_code=500):
        super().__init__("provider diagnostic containing TOP_SECRET")
        self.status_code = status_code


class FakeSDK:
    def __init__(self):
        self.calls = []
        self.closed = []
        self.streams_closed = []
        self.data = {}
        self.pages = []
        self.status = SimpleNamespace(running=False, exit_code=0)
        self.command_id = "command-1"
        self.kill_error = None
        self.query_error = ProviderFailure(404)
        self.create_error = None
        self.run_error = None
        self.read_count = 0
        owner = self

        class Files:
            def write_file(self, path, source, **kwargs):
                owner.calls.append(("write", path, source, kwargs))
                owner.data[path] = source.encode()

            def read_bytes_stream(self, path, **kwargs):
                owner.calls.append(("read", path, kwargs))
                if path not in owner.data:
                    raise ProviderFailure(404)
                try:
                    for offset in range(0, len(owner.data[path]), 3):
                        owner.read_count += 1
                        yield owner.data[path][offset:offset + 3]
                finally:
                    owner.streams_closed.append(path)

        class Commands:
            def run(self, command, *, opts):
                owner.calls.append(("run", command, opts))
                if owner.run_error:
                    raise owner.run_error
                return SimpleNamespace(id=owner.command_id)

            def get_command_status(self, command_id):
                owner.calls.append(("status", command_id))
                if isinstance(owner.status, Exception):
                    raise owner.status
                return owner.status

        class Sandbox:
            id = "sandbox-1"
            files = Files()
            commands = Commands()

            @classmethod
            def create(cls, image, **kwargs):
                owner.calls.append(("create", image, kwargs))
                if owner.create_error:
                    raise owner.create_error
                return cls()

            @classmethod
            def connect(cls, sandbox_id, **kwargs):
                owner.calls.append(("connect", sandbox_id, kwargs))
                return cls()

            def close(self):
                owner.closed.append("sandbox")

        class Manager:
            @classmethod
            def create(cls, **kwargs):
                owner.calls.append(("manager", kwargs))
                return cls()

            def list_sandbox_infos(self, filter):
                owner.calls.append(("list", filter))
                return owner.pages[filter.page - 1]

            def kill_sandbox(self, sandbox_id):
                owner.calls.append(("kill", sandbox_id))
                if owner.kill_error:
                    raise owner.kill_error

            def get_sandbox_info(self, sandbox_id):
                owner.calls.append(("query", sandbox_id))
                if owner.query_error:
                    raise owner.query_error
                return SimpleNamespace(id=sandbox_id)

            def close(self):
                owner.closed.append("manager")

        self.Sandbox = Sandbox
        self.Manager = Manager
        self.ConnectionConfig = SimpleNamespace
        self.NetworkPolicy = SimpleNamespace
        self.RunCommandOpts = SimpleNamespace
        self.SandboxFilter = SimpleNamespace
        self.RetryPolicy = SimpleNamespace(disabled=lambda: "retry-disabled")


class SandboxContractTests(unittest.TestCase):
    def spec(self, **kwargs):
        return SandboxSpec("python:3.12", "print(1)", ("/usr/bin/python3",), "/work", **kwargs)

    def test_payload_and_pickle_preserve_frozen_nested_policies(self):
        policy = {"default_action": "deny", "egress": [{"action": "allow", "target": "example.org"}]}
        spec = self.spec(network_policy=policy)
        policy["egress"][0]["target"] = "modified"
        spec.network_policy["egress"][0]["target"] = "also modified"
        payload = spec.to_payload()
        self.assertEqual(payload["network_policy"]["egress"][0]["target"], "example.org")
        payload["network_policy"]["egress"].clear()
        self.assertEqual(len(spec.network_policy["egress"]), 1)
        self.assertEqual(SandboxSpec.from_payload(spec.to_payload()), spec)
        self.assertEqual(pickle.loads(pickle.dumps(spec)), spec)

    def test_strict_json_and_frozen_path_contract(self):
        for change in ({"resources": {"cpu": math.nan}}, {"interpreter": ("python",)},
                       {"cwd": "relative"}, {"artifacts": ("a", "a")},
                       {"resources": {1: "x"}}, {"network_policy": {"rules": (1, 2)}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.spec(), **change)
        payload = self.spec().to_payload()
        payload["unknown"] = 1
        with self.assertRaises(ValueError):
            SandboxSpec.from_payload(payload)
        payload = self.spec().to_payload()
        payload["interpreter"] = tuple(payload["interpreter"])
        with self.assertRaises(ValueError):
            SandboxSpec.from_payload(payload)

    def test_observation_rejects_false_success(self):
        for state, code in (("succeeded", None), ("succeeded", 1), ("failed", 0),
                            ("failed", None), ("running", 0), ("unknown", True)):
            with self.subTest(state=state, code=code), self.assertRaises(ValueError):
                SandboxObservation(state, code)

    def test_backend_pickle_and_import_require_no_optional_sdk(self):
        backend = OpenSandboxBackend("localhost:8080")
        self.assertIsInstance(backend, SandboxBackend)
        self.assertEqual(pickle.loads(pickle.dumps(backend)), backend)
        self.assertNotEqual(backend.revision, replace(backend, domain="other:8080").revision)
        code = (
            "import sys; from dispatcher_sdk.adapters import OpenSandboxBackend; "
            "x=OpenSandboxBackend('localhost:8080'); print(x.name); "
            "assert not any(k == 'opensandbox' or k.startswith('opensandbox.') for k in sys.modules)"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class OpenSandboxAdapterTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSDK()
        self.patcher = patch.object(adapter_module, "_sdk", return_value=self.fake)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.backend = OpenSandboxBackend("localhost:8080", max_output_bytes=4,
                                          max_artifact_bytes=4, max_total_artifact_bytes=5)
        self.spec = SandboxSpec("python:3.12", "print('hello')", ("/usr/bin/python3",), "/work")

    def test_create_forwards_supported_policy_and_closes_client(self):
        spec = replace(self.spec, resources={"cpu": "1", "memory": "512Mi"},
                       network_policy={"default_action": "deny", "egress": []})
        self.assertEqual(self.backend.create(spec, operation_key="run/task", timeout=5), "sandbox-1")
        kwargs = self.fake.calls[0][2]
        self.assertEqual(kwargs["resource"], {"cpu": "1", "memory": "512Mi"})
        token = kwargs["metadata"]["dispatcher_operation"]
        self.assertLessEqual(len(token), 63)
        self.assertRegex(token, r"^[a-z2-7]+$")
        self.assertEqual(kwargs["network_policy"].default_action, "deny")
        self.assertEqual(kwargs["connection_config"].retry_policy, "retry-disabled")
        self.assertEqual(self.fake.closed, ["sandbox"])

    def test_unsupported_policy_fails_before_any_provider_call(self):
        for fields in ({"resources": {"gpu": "1"}},
                       {"network_policy": {"default_action": "deny", "ingress": []}},
                       {"network_policy": {"default_action": "deny", "egress": [
                           {"action": "allow", "target": "example.org", "port": 443}]}}):
            with self.subTest(fields=fields), self.assertRaises(SandboxPolicyError):
                self.backend.create(replace(self.spec, **fields), operation_key="key", timeout=5)
        self.assertEqual(self.fake.calls, [])

    def test_lost_create_response_is_unknown_without_retry_or_error_secret(self):
        self.fake.create_error = ProviderFailure()
        with self.assertRaises(SandboxOutcomeUnknown) as raised:
            self.backend.create(self.spec, operation_key="key", timeout=5)
        self.assertNotIn("TOP_SECRET", str(raised.exception))
        self.assertEqual(len(self.fake.calls), 1)

    def test_create_missing_identity_is_unknown_after_remote_action(self):
        self.fake.Sandbox.id = None
        with self.assertRaises(SandboxOutcomeUnknown):
            self.backend.create(self.spec, operation_key="key", timeout=5)
        self.assertEqual(self.fake.closed, ["sandbox"])

    def test_discovery_consumes_all_pages_without_selecting_one_duplicate(self):
        token = adapter_module._operation_token("key")
        info = lambda id: SimpleNamespace(id=id, metadata={"dispatcher_operation": token})
        self.fake.pages = [
            SimpleNamespace(sandbox_infos=[info("b")], pagination=SimpleNamespace(has_next_page=True)),
            SimpleNamespace(sandbox_infos=[info("a")], pagination=SimpleNamespace(has_next_page=False)),
        ]
        self.assertEqual(self.backend.find("key", timeout=5), ("a", "b"))
        self.assertEqual(self.fake.closed, ["manager"])

    def test_discovery_empty_is_empty_not_a_create(self):
        self.fake.pages = [SimpleNamespace(sandbox_infos=[], pagination=SimpleNamespace(has_next_page=False))]
        self.assertEqual(self.backend.find("key", timeout=5), ())
        self.assertFalse(any(call[0] == "create" for call in self.fake.calls))

    def test_discovery_rejects_mismatched_metadata(self):
        self.fake.pages = [SimpleNamespace(sandbox_infos=[SimpleNamespace(id="a", metadata={})],
                                          pagination=SimpleNamespace(has_next_page=False))]
        with self.assertRaises(SandboxOutcomeUnknown):
            self.backend.find("key", timeout=5)
        self.assertEqual(self.fake.closed, ["manager"])

    def test_source_uploaded_and_argv_quoted_before_background_start(self):
        spec = replace(self.spec, interpreter=("/bin/a program", "$(touch /outside)", "a'b"))
        self.assertEqual(self.backend.start("sandbox-1", spec, timeout=5), "command-1")
        self.assertEqual([c[0] for c in self.fake.calls], ["connect", "write", "run"])
        run = self.fake.calls[-1]
        words = shlex.split(run[1])
        self.assertEqual(words[:4], ["exec", *spec.interpreter])
        self.assertTrue(run[2].background)
        self.assertEqual(run[2].working_directory, spec.cwd)
        self.assertEqual(self.fake.calls[1][2], spec.source)
        self.assertEqual(self.fake.closed, ["sandbox"])

    def test_lost_start_response_is_unknown_without_retry(self):
        self.fake.run_error = ProviderFailure()
        with self.assertRaises(SandboxOutcomeUnknown):
            self.backend.start("sandbox-1", self.spec, timeout=5)
        self.assertEqual(len([c for c in self.fake.calls if c[0] == "run"]), 1)
        self.assertEqual(self.fake.closed, ["sandbox"])

    def test_missing_command_identity_is_unknown(self):
        self.fake.command_id = None
        with self.assertRaises(SandboxOutcomeUnknown):
            self.backend.start("sandbox-1", self.spec, timeout=5)

    def test_incomplete_status_is_not_success_and_nonzero_exit_is_failure(self):
        for running, code, expected in ((False, None, "unknown"), (None, 0, "unknown"),
                                        (True, None, "running"), (False, 0, "succeeded"),
                                        (False, 7, "failed"), (False, False, "unknown")):
            self.fake.status = SimpleNamespace(running=running, exit_code=code)
            self.assertEqual(self.backend.inspect("sandbox-1", "command-1", timeout=5).state, expected)

    def test_status_404_is_missing_not_success_or_not_applied(self):
        self.fake.status = ProviderFailure(404)
        with self.assertRaises(SandboxResourceMissing):
            self.backend.inspect("sandbox-1", "command-1", timeout=5)

    def test_mismatched_command_identity_and_inconsistent_success_are_rejected(self):
        self.fake.status = SimpleNamespace(id="other", running=False, exit_code=0)
        with self.assertRaises(SandboxOutcomeUnknown):
            self.backend.inspect("sandbox-1", "command-1", timeout=5)
        self.fake.status = SimpleNamespace(id="command-1", running=False, exit_code=0, error="TOP_SECRET")
        observed = self.backend.inspect("sandbox-1", "command-1", timeout=5)
        self.assertEqual(observed.state, "unknown")
        self.assertNotIn("TOP_SECRET", repr(observed))

    def test_collection_is_bounded_closes_streams_and_keeps_exit_code(self):
        spec = replace(self.spec, artifacts=("result.bin", "/tmp/other.bin"))
        _, stdout, stderr = self.backend._paths(spec)
        self.fake.data = {stdout: b"123456789" * 1000, stderr: b"", "/work/result.bin": b"abcdef",
                          "/tmp/other.bin": b"uvwxyz"}
        self.fake.status = SimpleNamespace(running=False, exit_code=9)
        result = self.backend.collect("sandbox-1", "command-1", spec, timeout=5)
        self.assertEqual(result["exit_code"], 9)
        self.assertEqual(base64.b64decode(result["stdout"]["data"]), b"1234")
        self.assertTrue(result["stdout"]["truncated"])
        self.assertIsNone(result["stdout"]["sha256"])
        self.assertFalse(result["stderr"]["truncated"])
        self.assertEqual([a["bytes_read"] for a in result["artifacts"]], [4, 1])
        self.assertEqual(set(self.fake.streams_closed), set(self.fake.data))
        self.assertLess(self.fake.read_count, 10)
        json.dumps(result, allow_nan=False)

    def test_collection_rejects_running_and_missing_artifacts(self):
        self.fake.status = SimpleNamespace(running=True, exit_code=None)
        with self.assertRaises(SandboxOutcomeUnknown):
            self.backend.collect("sandbox-1", "command-1", self.spec, timeout=5)
        self.fake.status = SimpleNamespace(running=False, exit_code=0)
        with self.assertRaises(SandboxResourceMissing):
            self.backend.collect("sandbox-1", "command-1", self.spec, timeout=5)

    def test_termination_requires_query_404_even_if_delete_response_lost(self):
        self.fake.kill_error = ProviderFailure()
        self.assertTrue(self.backend.terminate("sandbox-1", timeout=5))
        self.assertEqual([c[0] for c in self.fake.calls], ["manager", "kill", "query"])
        self.assertEqual(self.fake.closed, ["manager"])

    def test_delete_acknowledgment_is_not_absence_confirmation(self):
        self.fake.query_error = None
        self.assertFalse(self.backend.terminate("sandbox-1", timeout=5))
        self.fake.kill_error = ProviderFailure(404)
        self.fake.query_error = ProviderFailure(503)
        with self.assertRaises(SandboxOutcomeUnknown):
            self.backend.terminate("sandbox-1", timeout=5)

    def test_invalid_budget_fails_before_provider_calls(self):
        for timeout in (0, -1, math.nan, math.inf, True, 10**1000):
            with self.subTest(timeout=timeout), self.assertRaises(SandboxPolicyError):
                self.backend.start("sandbox-1", self.spec, timeout=timeout)
        self.assertEqual(self.fake.calls, [])


if __name__ == "__main__":
    unittest.main()
