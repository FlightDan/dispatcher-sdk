import threading
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dispatcher_sdk.execution_kernel import _process_runtime, _windows_runtime
from dispatcher_sdk.execution_kernel.runtime import InProcessRuntime, _ProcessCleanupPendingError


class NativeSupervisorRetentionTests(unittest.TestCase):
    def test_posix_failed_termination_keeps_registered_handle(self):
        receiver = Mock()
        receiver.poll.return_value = False
        sender = Mock()
        process = Mock()
        context = Mock()
        context.Pipe.return_value = (receiver, sender)
        context.Process.return_value = process
        handles = []
        finished = Mock()
        with patch.object(_process_runtime.multiprocessing, "get_context", return_value=context), \
             patch.object(_process_runtime, "_wait_packet", return_value=({}, 0)), \
             patch.object(_process_runtime.ProcessSupervisorHandle, "terminate", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "could not be terminated"):
                _process_runtime.invoke_process_handler(
                    db_path="unused", handler=lambda *_: None, command=None, lease=None,
                    now=None, start_timeout=1, on_started=lambda handle: handles.append(handle) or True,
                    on_finished=finished)
        self.assertEqual(len(handles), 1)
        finished.assert_not_called()

    def test_windows_close_keeps_handles_when_termination_fails(self):
        handle = _windows_runtime.WindowsProcessHandle.__new__(_windows_runtime.WindowsProcessHandle)
        handle._lock = threading.RLock()
        handle._closed = False
        handle.terminate = Mock(return_value=False)
        handle._api = Mock()
        with self.assertRaisesRegex(RuntimeError, "zero active processes"):
            handle.close()
        self.assertFalse(handle._closed)
        handle._api.dll.CloseHandle.assert_not_called()

    def test_windows_directory_is_retained_until_handle_cleanup(self):
        retained = [True]
        with _windows_runtime._worker_directory(retained) as directory:
            Path(directory, "worker-data").write_text("data", encoding="utf-8")
        self.assertTrue(Path(directory, "worker-data").exists())
        handle = _windows_runtime.WindowsProcessHandle.__new__(_windows_runtime.WindowsProcessHandle)
        handle._lock = threading.RLock()
        handle._closed = True
        handle._retained_directory = directory
        handle.close()
        self.assertFalse(Path(directory).exists())

    def test_windows_close_failure_retains_handle_and_directory(self):
        retained = [False]
        finished = Mock()
        handle = Mock()
        handle.close.side_effect = OSError("close failed")
        with self.assertRaisesRegex(OSError, "close failed"):
            _windows_runtime._finish_worker_handle(handle, True, retained, "worker-dir", finished)
        self.assertTrue(retained[0])
        self.assertEqual(handle._retained_directory, "worker-dir")
        finished.assert_not_called()

    def test_windows_partial_close_retries_only_unreleased_handles(self):
        handle = _windows_runtime.WindowsProcessHandle.__new__(_windows_runtime.WindowsProcessHandle)
        handle._lock = threading.RLock()
        handle._closed = False
        handle._contained = True
        handle._worker_process = 11
        handle._info = SimpleNamespace(hThread=12, hProcess=13)
        handle._job = 14
        handle._retained_directory = None
        api = handle._api = Mock()
        attempts = []
        def close(value):
            attempts.append(value)
            return not (value == 13 and attempts.count(13) == 1)
        def check(result, operation):
            if not result:
                raise OSError(operation)
        api.dll.CloseHandle.side_effect = close
        api.check.side_effect = check
        with self.assertRaisesRegex(OSError, "hProcess"):
            handle.close()
        self.assertFalse(handle._closed)
        self.assertIsNone(handle._worker_process)
        self.assertIsNone(handle._info.hThread)
        self.assertEqual(handle._info.hProcess, 13)
        self.assertEqual(handle._job, 14)
        handle.close()
        self.assertTrue(handle._closed)
        self.assertEqual(attempts, [11, 12, 13, 13, 14])

    def test_retained_handle_is_retryable_and_exact_generation_is_kept(self):
        runtime = InProcessRuntime.__new__(InProcessRuntime)
        runtime._lifecycle_lock = threading.RLock()
        handle = Mock()
        handle.revoke.side_effect = [False, True]
        key = ("execution", 3, 7)
        runtime._process_supervisors = {key: handle}
        with self.assertRaises(_ProcessCleanupPendingError):
            runtime._retry_process_cleanup()
        self.assertIs(runtime._process_supervisors[key], handle)
        runtime._retry_process_cleanup()
        self.assertEqual(runtime._process_supervisors, {})
        handle.close.assert_called_once()

    def test_close_attempts_other_obligations_before_retained_process_retry(self):
        runtime = InProcessRuntime.__new__(InProcessRuntime)
        runtime._lifecycle_lock = threading.RLock()
        runtime._lifecycle_condition = threading.Condition()
        runtime._close_complete = threading.Event()
        runtime._close_retry_lock = threading.Lock()
        runtime._closed = False
        runtime._stop_event = threading.Event()
        runtime._active_runs = 0
        runtime._close_error = None
        runtime.request_stop = Mock()
        runtime._stall_supervisor = runtime._child_service = runtime._settlement_thread = None
        runtime._persist_pending_settlements = Mock()
        runtime._drain_observation_workers = Mock(return_value=False)
        runtime.recover_sandboxes = Mock(return_value=[])
        runtime._pending_settlements = Mock()
        runtime._pending_settlements.identities.return_value = ()
        runtime._retry_process_cleanup = Mock(side_effect=[_ProcessCleanupPendingError("pending"), None])
        runtime._close_kernel_storage = Mock()
        runtime._temporary_observation = None
        runtime._retired_recorders = []
        runtime._retired_observation_contexts = []
        runtime._recovery_completion_readers = []
        runtime._observation_cleanup_pending = False
        with self.assertRaises(_ProcessCleanupPendingError):
            runtime.close()
        runtime._persist_pending_settlements.assert_called_once()
        runtime.recover_sandboxes.assert_called_once()
        runtime._close_kernel_storage.assert_called_once()
        runtime.close()
        self.assertIsNone(runtime._close_error)
        self.assertEqual(runtime._retry_process_cleanup.call_count, 2)

    def test_raised_revocation_attempts_other_handles_and_repeated_close_retries(self):
        runtime = InProcessRuntime.__new__(InProcessRuntime)
        runtime._lifecycle_lock = threading.RLock()
        runtime._lifecycle_condition = threading.Condition()
        runtime._thread_lock = threading.RLock()
        runtime._close_complete = threading.Event()
        runtime._close_retry_lock = threading.Lock()
        runtime._closed = False
        runtime._stop_event = threading.Event()
        runtime._active_runs = 0
        runtime._close_error = None
        failing, other = Mock(), Mock()
        failing.revoke.side_effect = [OSError("denied"), OSError("denied"), OSError("denied"), True]
        other.revoke.return_value = True
        first_key, second_key = ("first", 1, 4), ("second", 2, 8)
        runtime._process_supervisors = {first_key: failing, second_key: other}
        runtime._process_registration_events = {}
        runtime._revoked_executions = {}
        runtime._thread_authorities = []
        runtime._thread_executor = Mock()
        runtime._child_thread_executor = None
        runtime._thread_contexts = {}
        runtime._stall_supervisor = runtime._child_service = runtime._settlement_thread = None
        runtime._persist_pending_settlements = Mock()
        runtime._drain_observation_workers = Mock(return_value=False)
        runtime.recover_sandboxes = Mock(return_value=[])
        runtime._pending_settlements = Mock()
        runtime._pending_settlements.identities.return_value = ()
        runtime._close_kernel_storage = Mock()
        runtime._temporary_observation = None
        runtime._retired_recorders = []
        runtime._retired_observation_contexts = []
        runtime._recovery_completion_readers = []
        runtime._observation_cleanup_pending = False
        with self.assertRaises(_ProcessCleanupPendingError) as first:
            runtime.close()
        self.assertIn("first", str(first.exception))
        self.assertIsInstance(first.exception.__cause__, OSError)
        self.assertEqual(other.revoke.call_count, 2)
        self.assertEqual(runtime._process_supervisors, {first_key: failing})
        runtime._thread_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        runtime._persist_pending_settlements.assert_called_once()
        runtime.recover_sandboxes.assert_called_once()
        runtime._close_kernel_storage.assert_called_once()
        with self.assertRaises(_ProcessCleanupPendingError):
            runtime.close()
        self.assertIs(runtime._process_supervisors[first_key], failing)
        runtime.close()
        self.assertEqual(runtime._process_supervisors, {})
        self.assertIsNone(runtime._close_error)

    def test_claimed_invocation_failure_carries_identity_and_original_cause(self):
        runtime = InProcessRuntime.__new__(InProcessRuntime)
        runtime._assert_registry_current = Mock()
        runtime.isolation_mode = "process"
        runtime._lifecycle_lock = threading.RLock()
        runtime._lifecycle_condition = threading.Condition()
        runtime._thread_lock = threading.RLock()
        runtime._closed = False
        runtime.worker_id = "worker"
        runtime.lease_seconds = 30
        runtime.registry_revision = "revision"
        runtime.handler_revisions = {}
        runtime._budget_scan_continuation = None
        runtime._handler_start_timeout = Mock(return_value=1)
        lease = SimpleNamespace(execution_id="execution", attempt=3, fence=7)
        runtime.kernel = Mock()
        runtime.kernel.claim_and_start.return_value = lease
        runtime.kernel.get.return_value = SimpleNamespace(command=object(), started_at=1)
        runtime._begin_process_execution = Mock()
        runtime._finish_process_execution = Mock()
        runtime._begin_activity = Mock()
        runtime._handler_or_error = Mock(return_value=(object(), None))
        original = RuntimeError("native failure")
        runtime._invoke_process = Mock(side_effect=original)
        runtime._diagnostic_note = Mock(return_value=True)
        runtime._diagnostic_claim_exclusions = Mock(return_value=(False, ()))
        runtime._diagnostic_pending_lock = threading.Lock()
        runtime._lifecycle_producers = {}
        runtime._lifecycle_active_tokens = set()
        runtime._lifecycle_token_generations = {}
        runtime._diagnostic_pending_overflow = False
        runtime._diagnostic_failed_executions = set()
        runtime._lifecycle_finished = set()
        runtime._retry_diagnostic_notes = Mock()
        runtime._recover_script_output = Mock()
        runtime._process_registration_events = {}
        runtime._execution_recorders = {}
        runtime._thread_authority_by_execution = {}
        runtime._thread_done = set()
        with self.assertRaises(RuntimeError) as raised:
            runtime._run_once_active(execution_id=None, admission=object())
        error = raised.exception
        self.assertIs(error, original)
        self.assertEqual(error.execution_context, {"execution_id": "execution", "attempt": 3,
            "fence": 7, "phase": "invocation", "process_cleanup": "unknown", "diagnostic_saved": True})
        self.assertEqual(runtime._diagnostic_note.call_count, 2)
        self.assertEqual(runtime._diagnostic_note.call_args.args[2]["outcome"], "unknown")


if __name__ == "__main__":
    unittest.main()
