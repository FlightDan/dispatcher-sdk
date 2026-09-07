"""Native Windows integration tests; skips never count as Win32 verification."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy, SQLiteKernel, ScriptSpec, script_handler
from dispatcher_sdk.execution_kernel import _windows_runtime as windows_runtime
from dispatcher_sdk.execution_kernel._windows_runtime import invoke_windows_handler, _WinAPI, _ExtendedLimits


def _echo(payload, context):
    receipt = context.effects.execute_once("receipt", "test", payload, lambda: {"saved": payload})
    return {"receipt": receipt, "durability": context.effects._kernel.durability}


def _publish_pid(path, pid):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(str(pid), encoding="ascii")
    os.replace(temporary, path)


def _read_pid(path):
    try:
        pid = int(Path(path).read_text(encoding="ascii"))
    except (FileNotFoundError, PermissionError, ValueError):
        # Windows can briefly deny a PID-file open while another process
        # inspects it. The caller's existing deadline still bounds this wait.
        return None
    return pid if pid > 0 else None


def _wait_pid(path, timeout=30):
    deadline = time.monotonic() + timeout
    while True:
        pid = _read_pid(path)
        if pid is not None:
            return pid
        if time.monotonic() >= deadline:
            raise TimeoutError(f"fixture did not publish a valid child PID: {path}")
        time.sleep(.01)


def _test_import_path():
    # Discovery imports this file as test_windows_runtime; package execution
    # uses tests.test_windows_runtime. Support both, and direct file execution.
    return [str(Path(__file__).resolve().parent), *sys.path]


_TEST_MODULE = __name__ if __name__ != "__main__" else "test_windows_runtime"


def _tree(payload, context):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    if payload.get("pidfile"):
        _publish_pid(payload["pidfile"], child.pid)
    if payload.get("block"):
        while True:
            time.sleep(.01)
    return {"child_pid": child.pid}


_tree.__execution_kernel_revision__ = "windows-test-tree-v1"


def _abrupt(payload, context):
    print("windows-worker-diagnostic", file=sys.stderr, flush=True)
    os._exit(23)


def _stream_failure(payload, context):
    sys.stdout.write("pythonw-stdout\n")
    sys.stderr.write("pythonw-stderr\n")
    raise RuntimeError("intentional stream probe")


def _no_console_host(directory):
    # Remove OS standard handles before worker creation, even if the test
    # runner supplied redirected streams to this pythonw host.
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    api.SetStdHandle.restype = wintypes.BOOL
    for identifier in (-10, -11, -12):
        if not api.SetStdHandle(identifier, None):
            raise ctypes.WinError(ctypes.get_last_error())
    path = Path(directory) / "no-console.db"
    with SQLiteKernel(path) as kernel:
        command = _command({})
        kernel.submit(command)
        lease = kernel.claim_and_start("no-console")
        outcome = invoke_windows_handler(db_path=str(path), handler=_stream_failure,
            command=command, lease=lease, now=None, start_timeout=20)
    (Path(directory) / "no-console-outcome.json").write_text(json.dumps(outcome), encoding="utf-8")


def _restore_handler(marker):
    api = _WinAPI()
    assigned = wintypes.BOOL()
    api.check(api.dll.IsProcessInJob(wintypes.HANDLE(-1), None, ctypes.byref(assigned)), "IsProcessInJob")
    Path(marker).write_text(str(bool(assigned.value)), encoding="ascii")
    return _echo


class _RestoredHandler:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        return _restore_handler, (self.marker,)


def _command(payload, timeout=20):
    return ExecutionCommandV2(execution_id="windows-test", idempotency_key="windows-test",
        registry_revision="windows-test", correlation_id="windows-test", causation_id=None,
        handler_id="test", handler_contract_version=1, retry_policy=RetryPolicy(max_attempts=2),
        timeout_seconds=timeout, payload=payload)


def _host_death(directory):
    path = Path(directory) / "host.db"
    with SQLiteKernel(path) as kernel:
        command = _command({"pidfile": str(Path(directory) / "child.pid"), "block": True}, 60)
        kernel.submit(command)
        lease = kernel.claim_and_start("host")
        thread = threading.Thread(target=invoke_windows_handler, kwargs=dict(db_path=str(path),
            handler=_tree, command=command, lease=lease, now=None, start_timeout=30))
        thread.start()
        _wait_pid(Path(directory) / "child.pid")
        os._exit(0)


def _incompatible_outer_job(directory):
    api = _WinAPI()
    job = api.dll.CreateJobObjectW(None, None)
    api.check(job, "CreateJobObjectW(test outer)")
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x8  # ACTIVE_PROCESS limit.
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    api.check(api.dll.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)),
              "SetInformationJobObject(test outer)")
    assign = api.dll.AssignProcessToJobObject
    assign.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    assign.restype = wintypes.BOOL
    api.check(assign(job, wintypes.HANDLE(-1)), "AssignProcessToJobObject(test host)")
    path = Path(directory) / "outer.db"
    marker = Path(directory) / "must-not-unpickle"
    try:
        with SQLiteKernel(path) as kernel:
            command = _command({})
            kernel.submit(command)
            lease = kernel.claim_and_start("outer")
            try:
                invoke_windows_handler(db_path=str(path), handler=_RestoredHandler(str(marker)),
                    command=command, lease=lease, now=None, start_timeout=5)
            except OSError:
                if marker.exists():
                    raise AssertionError("user code executed outside the requested Job")
            else:
                raise AssertionError("outer active-process limit must prevent worker creation")
    finally:
        api.dll.CloseHandle(job)


def _pid_alive(pid):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    process = api.OpenProcess(0x00100000, False, pid)
    if not process:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: no such process.
            return False
        raise ctypes.WinError(error)
    try:
        return api.WaitForSingleObject(process, 0) == 258
    finally:
        api.CloseHandle(process)


class UnsupportedWindowsBackendTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "non-Windows refusal path")
    def test_native_windows_is_required(self):
        with self.assertRaisesRegex(RuntimeError, "native Windows"):
            _WinAPI()


class WindowsPublicationRaceTests(unittest.TestCase):
    def test_bootstrap_restores_missing_python_streams_and_descriptors(self):
        # Exercise descriptor/Python stream setup in a disposable interpreter.
        # Only the two Windows-specific calls and actual worker are substituted;
        # this does not count as native Job or pythonw verification.
        code = """
import ctypes, os, sys, types
ctypes.WinDLL = lambda *args, **kwargs: types.SimpleNamespace(SetStdHandle=lambda *args: 1)
sys.modules['msvcrt'] = types.SimpleNamespace(get_osfhandle=lambda fd: fd)
worker = types.ModuleType('dispatcher_sdk.execution_kernel._windows_runtime')
def report(directory):
    sys.stdout.write('python stdout\\n')
    sys.stderr.write('python stderr\\n')
    os.write(2, b'native descriptor stderr\\n')
worker._worker_main = report
sys.modules[worker.__name__] = worker
sys.stdout = sys.__stdout__ = None
sys.stderr = sys.__stderr__ = None
for fd in (0, 1, 2):
    try:
        os.close(fd)
    except OSError:
        pass
""" + windows_runtime._BOOTSTRAP
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run([sys.executable, "-c", code, directory],
                                       timeout=15, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((Path(directory) / "stdout.log").read_text(encoding="utf-8"),
                             "python stdout\n")
            self.assertEqual((Path(directory) / "stderr.log").read_text(encoding="utf-8"),
                             "python stderr\nnative descriptor stderr\n")

    def test_publication_between_file_check_and_exit_preserves_deadline_and_revocation(self):
        # Control the OS boundary only. The real invocation loop, file protocol
        # and final outcome selection run on every platform.
        for disposition in ("success", "timeout", "cancelled"):
            with self.subTest(disposition=disposition), tempfile.TemporaryDirectory() as directory:
                roots = []
                contained = []
                expected = {"kind": "ok", "value": "published-on-exit", "effect_ids": []}

                def create(api, arguments):
                    roots.append(Path(arguments[-1]))
                    return None, None

                class Handle:
                    revocation_reason = None
                    exitcode = 0

                    def __init__(self, *args):
                        pass

                    def resume(self):
                        (roots[0] / "ready").write_text("ready", encoding="ascii")

                    def exited(self):
                        # The loop has already observed no outcome file.
                        self_test.assertFalse((roots[0] / "outcome.json").exists())
                        windows_runtime._atomic_write(roots[0] / "outcome.json", json.dumps(expected))
                        if disposition == "cancelled":
                            self.revocation_reason = "execution_cancelled"
                        return True

                    def terminate(self):
                        contained.append(True)
                        return True

                    def close(self):
                        pass

                class Watchdog:
                    expired = False

                    def __init__(self, *args):
                        pass

                    def business_deadline(self, seconds):
                        return time.monotonic() + (-1 if disposition == "timeout" else 60)

                    def close(self):
                        pass

                self_test = self
                with patch.object(windows_runtime, "_WinAPI", return_value=object()), \
                        patch.object(windows_runtime, "_create_suspended", side_effect=create), \
                        patch.object(windows_runtime, "WindowsProcessHandle", Handle), \
                        patch.object(windows_runtime, "_Watchdog", Watchdog):
                    outcome = invoke_windows_handler(db_path=str(Path(directory) / "unused.db"),
                        handler=_echo, command=_command({}), lease=None, now=None, start_timeout=5)
                self.assertTrue(contained)
                if disposition == "success":
                    self.assertEqual(outcome, expected)
                elif disposition == "timeout":
                    self.assertEqual(outcome, {"kind": "timeout", "effect_ids": []})
                else:
                    self.assertEqual(outcome, {"kind": "authority_revoked",
                        "reason": "execution_cancelled", "effect_ids": []})


@unittest.skipUnless(os.name == "nt", "requires real Windows file sharing")
class WindowsDirectoryCleanupTests(unittest.TestCase):
    def lock_file(self, path):
        path.write_text("diagnostic", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-u", "-c",
             "import sys\nwith open(sys.argv[1], 'rb') as stream:\n"
             " print('locked', flush=True)\n sys.stdin.readline()\n", str(path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close_locker, process)
        self.assertEqual(process.stdout.readline().strip(), "locked")
        return process

    @staticmethod
    def close_locker(process):
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()

    def test_external_log_lock_is_retried_until_directory_is_removed(self):
        cleanup = shutil.rmtree
        observed = []
        locker = None

        def release_after_sharing_error(directory):
            try:
                cleanup(directory)
            except PermissionError as error:
                if not observed:
                    observed.append(error.winerror)
                    locker.stdin.write("release\n")
                    locker.stdin.flush()
                raise

        with patch.object(shutil, "rmtree", release_after_sharing_error):
            with windows_runtime._worker_directory() as directory:
                root = Path(directory)
                locker = self.lock_file(root / "stderr.log")
        self.assertEqual(observed, [32])
        self.assertFalse(root.exists())
        self.assertEqual(locker.wait(timeout=10), 0)

    def test_persistent_log_lock_propagates_cleanup_failure(self):
        root = None
        locker = None
        try:
            with patch.object(windows_runtime, "_CLEANUP_SECONDS", 0):
                with self.assertRaises(PermissionError) as raised:
                    with windows_runtime._worker_directory() as directory:
                        root = Path(directory)
                        locker = self.lock_file(root / "stderr.log")
            self.assertEqual(raised.exception.winerror, 32)
            self.assertTrue(root.exists())
        finally:
            if locker is not None:
                self.close_locker(locker)
            if root is not None:
                shutil.rmtree(root)


@unittest.skipUnless(os.name == "nt", "requires real native Windows Job Objects")
class WindowsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "kernel.db"
        self.kernel = SQLiteKernel(self.path)
        self.addCleanup(self.kernel.close)

    def invoke(self, handler, payload=None, timeout=20, **options):
        command = _command(payload or {}, timeout)
        self.kernel.submit(command)
        lease = self.kernel.claim_and_start("test-worker", lease_seconds=60)
        start_timeout = options.pop("start_timeout", 30)
        return invoke_windows_handler(db_path=str(self.path), handler=handler, command=command,
                                      lease=lease, now=None, start_timeout=start_timeout, **options)

    def assertProcessGone(self, pid):
        # A returned invocation must already have contained its descendants.
        self.assertFalse(_pid_alive(pid), f"PID {pid} survived the return boundary")

    def test_pickle_handler_executes_effect_and_receives_durability(self):
        outcome = self.invoke(_echo, {"value": "saved"}, durability="normal")
        self.assertEqual(outcome["kind"], "ok", outcome)
        self.assertEqual(outcome["value"]["durability"], "normal")
        self.assertEqual(outcome["effect_ids"], ["receipt"])
        self.assertEqual(self.kernel.get_effect("receipt").state, "committed")

    def test_unpickling_occurs_after_job_assignment(self):
        marker = self.root / "unpickled"
        outcome = self.invoke(_RestoredHandler(str(marker)))
        self.assertEqual(outcome["kind"], "ok", outcome)
        self.assertEqual(marker.read_text(encoding="ascii"), "True")

    def test_success_cleans_new_process_group_child(self):
        outcome = self.invoke(_tree)
        self.assertEqual(outcome["kind"], "ok", outcome)
        self.assertProcessGone(outcome["value"]["child_pid"])

    def test_timeout_cleans_descendant_before_return(self):
        pidfile = self.root / "child.pid"
        outcome = self.invoke(_tree, {"pidfile": str(pidfile), "block": True}, timeout=3)
        self.assertEqual(outcome["kind"], "timeout", outcome)
        self.assertTrue(pidfile.exists(), outcome)
        self.assertProcessGone(_wait_pid(pidfile))

    def test_cancel_before_resume_never_unpickles(self):
        marker = self.root / "must-not-exist"
        handles = []
        def registered(handle):
            handles.append(handle)
            self.assertTrue(handle.revoke("cancelled"))
            return True
        finished = []
        outcome = self.invoke(_RestoredHandler(str(marker)), on_started=registered, on_finished=finished.append)
        self.assertEqual(outcome["kind"], "authority_revoked", outcome)
        self.assertFalse(marker.exists())
        self.assertEqual(finished, handles)
        handles[0].close()  # Idempotent after invocation cleanup.
        self.assertTrue(handles[0].terminate())

    def test_concurrent_revocation_terminates_job_once_without_handle_races(self):
        pidfile = self.root / "child.pid"
        errors, results, threads = [], [], []
        def registered(handle):
            def cancel():
                try:
                    _wait_pid(pidfile, timeout=35)
                    results.append(handle.revoke("cancelled"))
                except BaseException as exc:
                    errors.append(exc)
            for _ in range(3):
                thread = threading.Thread(target=cancel)
                threads.append(thread)
                thread.start()
            return True
        outcome = self.invoke(_tree, {"pidfile": str(pidfile), "block": True}, on_started=registered)
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [True] * 3)
        self.assertEqual(outcome["kind"], "authority_revoked", outcome)
        self.assertProcessGone(_wait_pid(pidfile))

    def test_startup_watchdog_can_terminate_while_registration_is_blocked(self):
        marker = self.root / "must-not-unpickle"
        def registered(handle):
            time.sleep(.5)
            return True
        outcome = self.invoke(_RestoredHandler(str(marker)), on_started=registered, start_timeout=.1)
        self.assertEqual(outcome["code"], "handler_process_start_failure", outcome)
        self.assertFalse(marker.exists())

    def test_incompatible_outer_job_fails_without_unpickling(self):
        code = "import sys; sys.path[:]=%r; from %s import _incompatible_outer_job; _incompatible_outer_job(%r)" % (
            _test_import_path(), _TEST_MODULE, str(self.root))
        completed = subprocess.run([sys.executable, "-c", code], timeout=30, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_guarded_file_main_handler_is_reconstructed(self):
        script = self.root / "entrypoint.py"
        script.write_text(
            "import sys\nsys.path[:]=%r\n" % _test_import_path()
            + ("from %s import _command\n" % _TEST_MODULE)
            +
              "from dispatcher_sdk.execution_kernel import SQLiteKernel\n"
              "from dispatcher_sdk.execution_kernel._windows_runtime import invoke_windows_handler\n"
              "def handler(payload, context): return {'main': 'works'}\n"
              "if __name__ == '__main__':\n"
            + "    with SQLiteKernel(%r) as kernel:\n" % str(self.root / "entry.db")
            + "        command = _command({})\n"
              "        kernel.submit(command)\n"
              "        lease = kernel.claim_and_start('entry')\n"
            + "        outcome = invoke_windows_handler(db_path=%r, handler=handler, command=command, lease=lease, now=None, start_timeout=20)\n" % str(self.root / "entry.db")
            + "        assert outcome.get('value') == {'main': 'works'}, outcome\n",
            encoding="utf-8")
        completed = subprocess.run([sys.executable, str(script)], timeout=60, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_abrupt_worker_exit_preserves_stderr_tail(self):
        outcome = self.invoke(_abrupt)
        self.assertEqual(outcome["code"], "handler_process_exit", outcome)
        self.assertIn("windows-worker-diagnostic", outcome["details"]["stderr_tail"])

    def test_pythonw_host_without_standard_handles_rebuilds_python_streams(self):
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not pythonw.is_file():
            self.skipTest("pythonw.exe is not installed beside this Windows interpreter")
        code = "import sys; sys.path[:]=%r; from %s import _no_console_host; _no_console_host(%r)" % (
            _test_import_path(), _TEST_MODULE, str(self.root))
        completed = subprocess.run([str(pythonw), "-c", code], timeout=60)
        self.assertEqual(completed.returncode, 0)
        result = self.root / "no-console-outcome.json"
        self.assertTrue(result.exists(), "pythonw host did not publish its outcome")
        outcome = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(outcome["code"], "handler_error", outcome)
        self.assertEqual(outcome["message"], "intentional stream probe", outcome)
        self.assertIn("pythonw-stderr", outcome["details"]["stderr_tail"])

    def test_auto_runtime_cancel_and_close_contain_descendants_before_return(self):
        for action in ("cancel", "close"):
            with self.subTest(action=action):
                runtime = Kernel.open_sqlite(self.root / f"runtime-{action}.db", {"test": _tree})
                errors, results = [], []
                driver = None
                try:
                    self.assertEqual(runtime.isolation_mode, "process")
                    pidfile = self.root / f"runtime-{action}.pid"
                    command = ExecutionCommandV2.from_dict({
                        **_command({"pidfile": str(pidfile), "block": True}, 60).to_dict(),
                        "registry_revision": runtime.registry_revision})
                    runtime.submit(command)

                    def drive():
                        try:
                            results.append(runtime.run_once())
                        except BaseException as error:
                            errors.append(error)

                    driver = threading.Thread(target=drive)
                    driver.start()
                    child_pid = _wait_pid(pidfile)
                    if action == "cancel":
                        current = runtime.kernel.get(command.execution_id)
                        cancelled = runtime.cancel(command.execution_id,
                            expected_revision=current.revision, reason="native runtime probe")
                        self.assertEqual(cancelled.state, "cancelled")
                    else:
                        runtime.close()
                    # The public API return is the containment boundary.
                    self.assertFalse(_pid_alive(child_pid))
                    driver.join(10)
                    self.assertFalse(driver.is_alive())
                    self.assertEqual(errors, [])
                    self.assertEqual(len(results), 1)
                finally:
                    runtime.close()
                    if driver is not None:
                        driver.join(10)

    def test_script_artifacts_and_effect_are_committed(self):
        spec = ScriptSpec(source="import sys\nprint('native stdout')\nprint('native stderr', file=sys.stderr)\n",
                          interpreter=(sys.executable,), cwd=str(self.root), output_dir=str(self.root / "output"))
        outcome = self.invoke(script_handler, spec.to_payload())
        self.assertEqual(outcome["kind"], "ok", outcome)
        self.assertIn("native stdout", outcome["value"]["stdout"]["tail"])
        self.assertIn("native stderr", outcome["value"]["stderr"]["tail"])
        self.assertTrue(Path(outcome["value"]["stderr"]["path"]).is_file())

    def test_host_abrupt_exit_closes_only_job_handle_and_kills_descendants(self):
        code = "import sys; sys.path[:]=%r; from %s import _host_death; _host_death(%r)" % (
            _test_import_path(), _TEST_MODULE, str(self.root))
        completed = subprocess.run([sys.executable, "-c", code], timeout=45, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        child_pid = _wait_pid(self.root / "child.pid")
        # Abrupt host death has no Runtime return boundary. Job-close cleanup
        # may complete asynchronously after the host's process handle signals.
        deadline = time.monotonic() + 5
        while _pid_alive(child_pid) and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertProcessGone(child_pid)


if __name__ == "__main__":
    unittest.main()
