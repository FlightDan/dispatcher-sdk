"""Worker transport keeps host authority out of persisted handoff files."""
from pathlib import Path
import os
import ctypes
import threading
import pickle
import sys
import types
from unittest.mock import patch
import tempfile
import unittest
from ctypes import wintypes

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel._windows_runtime import _authority_pipe, _duplicate_worker_authority


def verify_worker(credential):
    return {"principal": credential, "permissions": [], "expires_at": 9999999999}


def inspect_worker_authority(payload, context):
    return {"received": (context._kernel._worker_credential == "worker-token"
                         and context._kernel._authority_verifier is verify_worker)}


inspect_worker_authority.__execution_kernel_revision__ = "worker-authority-transport-v1"


class UnserializableCredential:
    def __reduce__(self):
        raise RuntimeError("sensitive-test-value")


class WorkerAuthorityTransportTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "requires POSIX process worker")
    def test_spawned_worker_receives_host_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Kernel.open_sqlite(Path(directory) / "kernel.db", {"work": inspect_worker_authority},
                isolation_mode="process", authority_verifier=verify_worker, worker_credential="worker-token")
            try:
                runtime.submit(runtime.command("work", execution_id="worker", idempotency_key="worker",
                    correlation_id="worker", timeout_seconds=10, payload={}))
                result = runtime.run_once(execution_id="worker")
                self.assertEqual(result.state, "succeeded")
                self.assertTrue(result.result.value["received"])
            finally:
                runtime.close()

    @unittest.skipUnless(os.name == "posix", "requires POSIX process worker")
    def test_spawn_serialization_error_does_not_expose_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Kernel.open_sqlite(Path(directory) / "kernel.db", {"work": inspect_worker_authority},
                isolation_mode="process", authority_verifier=verify_worker,
                worker_credential=UnserializableCredential())
            try:
                runtime.submit(runtime.command("work", execution_id="failed", idempotency_key="failed",
                    correlation_id="failed", timeout_seconds=10, payload={}))
                with self.assertRaisesRegex(RuntimeError, "protected worker spawn failed") as raised:
                    runtime.run_once(execution_id="failed")
                self.assertNotIn("sensitive-test-value", str(raised.exception))
                notes = runtime._settlement_journal.inspect_notes("failed")["notes"]
                self.assertNotIn("sensitive-test-value", repr(notes))
            finally:
                runtime.close()

    def test_simulated_windows_pipe_transfers_and_closes_both_ends(self):
        fake = types.SimpleNamespace(get_osfhandle=lambda fd: fd)
        with patch.dict(sys.modules, {"msvcrt": fake}), \
             patch.object(os, "set_handle_inheritable", create=True) as inheritable:
            with _authority_pipe(verify_worker, "worker-token") as read_handle:
                self.assertEqual(pickle.loads(os.read(read_handle, 1025)), (verify_worker, "worker-token"))
                self.assertEqual(os.read(read_handle, 1), b"")
                inheritable.assert_not_called()
            with self.assertRaises(OSError):
                os.fstat(read_handle)

    def test_simulated_windows_pipe_closes_on_partial_write(self):
        fake = types.SimpleNamespace(get_osfhandle=lambda fd: fd)
        created = []
        pipe = os.pipe
        def record_pipe():
            result = pipe()
            created.extend(result)
            return result
        with patch.dict(sys.modules, {"msvcrt": fake}), \
             patch.object(os, "set_handle_inheritable", create=True), \
             patch.object(os, "pipe", side_effect=record_pipe), \
             patch.object(os, "write", return_value=1):
            with self.assertRaisesRegex(RuntimeError, "write incomplete"):
                with _authority_pipe(verify_worker, "worker-token"):
                    pass
        for fd in created:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_simulated_windows_duplicates_only_into_target_and_refuses_revocation(self):
        calls = []
        def duplicate(source, reader, target, output, access, inherit, flags):
            calls.append((source, reader, target, access, inherit, flags))
            ctypes.cast(output, ctypes.POINTER(wintypes.HANDLE))[0] = wintypes.HANDLE(42)
            return True
        api = types.SimpleNamespace(dll=types.SimpleNamespace(GetCurrentProcess=lambda: 9,
            DuplicateHandle=duplicate), check=lambda result, operation: self.assertTrue(result))
        handle = types.SimpleNamespace(_lock=threading.RLock(), _closed=False, _contained=False,
            _revocation_reason=None, _info=types.SimpleNamespace(hProcess=11))
        self.assertEqual(_duplicate_worker_authority(api, handle, 7), 42)
        self.assertEqual(calls, [(9, 7, 11, 0, True, 2)])
        handle._revocation_reason = "cancelled"
        with self.assertRaisesRegex(RuntimeError, "stopped before authority handoff"):
            _duplicate_worker_authority(api, handle, 7)
        self.assertEqual(len(calls), 1)

    def test_simulated_windows_pipe_rejects_oversize_before_open(self):
        with patch.object(os, "pipe") as pipe:
            with self.assertRaisesRegex(ValueError, "transport limit"):
                with _authority_pipe(verify_worker, "x" * 2048):
                    pass
            pipe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
