"""Windows native process containment for trusted handlers.

A fresh interpreter is created suspended, atomically assigned to an unnamed
kill-on-close Job, and resumed only after runtime registration. The caller owns
the only Job handle. A separate host thread enforces startup/business deadlines.
This is process-tree containment, not a sandbox for hostile same-user code.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from typing import Any, Callable, Optional

from ..durability import Durability, validate_durability
from ._process_runtime import invoke_handler, _serialize_handler_outcome
from ._registry import Handler
from .context import HandlerContext, HandlerEffects
from .contracts import ExecutionCommandV2, ExecutionLease
from .sqlite import SQLiteKernel

_CLEANUP_SECONDS = 5.0
_POLL_SECONDS = 0.01
_KILL_ON_JOB_CLOSE = 0x2000
_JOB_LIST_ATTRIBUTE = 0x0002000D
_CREATE_SUSPENDED = 0x00000004
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_NO_WINDOW = 0x08000000
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _IOCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IOCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in (
        "TotalUserTime", "TotalKernelTime", "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")]
    _fields_ += [(name, wintypes.DWORD) for name in (
        "TotalPageFaultCount", "TotalProcesses", "ActiveProcesses", "TotalTerminatedProcesses")]


class _StartupInfo(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR)]
    _fields_ += [(name, wintypes.DWORD) for name in (
        "dwX", "dwY", "dwXSize", "dwYSize", "dwXCountChars", "dwYCountChars", "dwFillAttribute", "dwFlags")]
    _fields_ += [("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
                ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE)]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


class _WinAPI:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows process isolation requires native Windows")
        self.dll = ctypes.WinDLL("kernel32", use_last_error=True)
        H, D, P, B = wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.BOOL
        signatures = {
            "CreateJobObjectW": ([P, wintypes.LPCWSTR], H),
            "SetInformationJobObject": ([H, ctypes.c_int, P, D], B),
            "QueryInformationJobObject": ([H, ctypes.c_int, P, D, P], B),
            "TerminateJobObject": ([H, wintypes.UINT], B),
            "CloseHandle": ([H], B),
            "InitializeProcThreadAttributeList": ([P, D, D, ctypes.POINTER(ctypes.c_size_t)], B),
            "UpdateProcThreadAttribute": ([P, D, ctypes.c_size_t, P, ctypes.c_size_t, P, P], B),
            "DeleteProcThreadAttributeList": ([P], None),
            "CreateProcessW": ([wintypes.LPCWSTR, wintypes.LPWSTR, P, P, B, D, P,
                                 wintypes.LPCWSTR, P, ctypes.POINTER(_ProcessInformation)], B),
            "ResumeThread": ([H], D),
            "TerminateProcess": ([H, wintypes.UINT], B),
            "WaitForSingleObject": ([H, D], D),
            "GetExitCodeProcess": ([H, ctypes.POINTER(D)], B),
            "IsProcessInJob": ([H, H, ctypes.POINTER(B)], B),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes, function.restype = arguments, result

    def check(self, result: Any, operation: str) -> None:
        if not result:
            error = ctypes.get_last_error()
            raise OSError(error, f"{operation}: {ctypes.FormatError(error)}")

    def active(self, job: Any) -> int:
        accounting = _Accounting()
        self.check(self.dll.QueryInformationJobObject(
            job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None), "QueryInformationJobObject")
        return int(accounting.ActiveProcesses)


def _create_suspended(api: _WinAPI, arguments: list[str]) -> tuple[Any, _ProcessInformation]:
    job = api.dll.CreateJobObjectW(None, None)  # Unnamed, non-inheritable.
    api.check(job, "CreateJobObjectW")
    info = _ProcessInformation()
    attributes = None
    initialized = False
    try:
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        api.check(api.dll.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)),
                  "SetInformationJobObject(KILL_ON_JOB_CLOSE)")
        size = ctypes.c_size_t()
        api.dll.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        if not size.value:
            api.check(False, "InitializeProcThreadAttributeList(size)")
        attributes = ctypes.create_string_buffer(size.value)
        api.check(api.dll.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)),
                  "InitializeProcThreadAttributeList")
        initialized = True
        jobs = (wintypes.HANDLE * 1)(job)
        api.check(api.dll.UpdateProcThreadAttribute(attributes, 0, _JOB_LIST_ATTRIBUTE,
                  ctypes.byref(jobs), ctypes.sizeof(jobs), None, None),
                  "UpdateProcThreadAttribute(JOB_LIST); Windows 10+ is required")
        startup = _StartupInfoEx()
        startup.StartupInfo.cb = ctypes.sizeof(startup)
        startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(arguments))
        api.check(api.dll.CreateProcessW(sys.executable, command_line, None, None, False,
                  _CREATE_SUSPENDED | _EXTENDED_STARTUPINFO_PRESENT | _CREATE_NO_WINDOW,
                  None, None, ctypes.byref(startup), ctypes.byref(info)),
                  "CreateProcessW with Job; an incompatible outer Job is not bypassed")
        assigned = wintypes.BOOL()
        api.check(api.dll.IsProcessInJob(info.hProcess, job, ctypes.byref(assigned)), "IsProcessInJob")
        if not assigned.value:
            raise RuntimeError("Windows worker was not assigned to its containment Job")
        return job, info
    except BaseException:
        if info.hProcess:
            api.dll.TerminateProcess(info.hProcess, 70)
            api.dll.WaitForSingleObject(info.hProcess, int(_CLEANUP_SECONDS * 1000))
        for resource in (info.hThread, info.hProcess, job):
            if resource:
                api.dll.CloseHandle(resource)
        raise
    finally:
        if initialized:
            api.dll.DeleteProcThreadAttributeList(attributes)


class WindowsProcessHandle:
    """Serialize revocation, Job termination, waits and handle closure."""
    def __init__(self, api: _WinAPI, job: Any, info: _ProcessInformation) -> None:
        self._api, self._job, self._info = api, job, info
        self._lock = threading.RLock()
        self._revocation_reason: Optional[str] = None
        self._closed = False
        self._contained = False
        self._exitcode: Optional[int] = None

    @property
    def revocation_reason(self) -> Optional[str]:
        with self._lock:
            return self._revocation_reason

    @property
    def pid(self) -> int:
        return int(self._info.dwProcessId)

    @property
    def exitcode(self) -> Optional[int]:
        with self._lock:
            return self._exitcode

    def resume(self) -> None:
        with self._lock:
            if self._closed or self._contained or self._revocation_reason is not None or not self._info.hThread:
                return
            result = self._api.dll.ResumeThread(self._info.hThread)
            if result == 0xFFFFFFFF:
                self._api.check(False, "ResumeThread")
            self._api.dll.CloseHandle(self._info.hThread)
            self._info.hThread = None

    def exited(self) -> bool:
        with self._lock:
            if self._closed:
                return True
            result = self._api.dll.WaitForSingleObject(self._info.hProcess, 0)
            if result not in (_WAIT_OBJECT_0, _WAIT_TIMEOUT):
                self._api.check(False, "WaitForSingleObject")
            return result == _WAIT_OBJECT_0

    def terminate(self) -> bool:
        with self._lock:
            if self._closed or self._contained:
                return self._contained
            self._api.check(self._api.dll.TerminateJobObject(self._job, 70), "TerminateJobObject")
            deadline = time.monotonic() + _CLEANUP_SECONDS
            while self._api.active(self._job):
                if time.monotonic() >= deadline:
                    return False
                time.sleep(_POLL_SECONDS)
            wait = self._api.dll.WaitForSingleObject(self._info.hProcess, int(_CLEANUP_SECONDS * 1000))
            if wait != _WAIT_OBJECT_0:
                return False
            code = wintypes.DWORD()
            self._api.check(self._api.dll.GetExitCodeProcess(self._info.hProcess, ctypes.byref(code)),
                            "GetExitCodeProcess")
            self._exitcode = int(code.value)
            self._contained = True
            return True

    def revoke(self, reason: str) -> bool:
        with self._lock:
            if self._revocation_reason is None:
                self._revocation_reason = reason
            return self.terminate()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                if not self.terminate():
                    raise RuntimeError("Windows Job did not reach zero active processes")
            finally:
                for resource in (self._info.hThread, self._info.hProcess, self._job):
                    if resource:
                        self._api.dll.CloseHandle(resource)
                self._closed = True


class _Watchdog:
    def __init__(self, handle: WindowsProcessHandle, deadline: float) -> None:
        self.handle, self.deadline = handle, deadline
        self.lock = threading.Lock()
        self.changed = threading.Event()
        self.stopped = False
        self.expired = False
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, name="kernel-windows-deadline", daemon=True)
        self.thread.start()

    def business_deadline(self, seconds: float) -> float:
        with self.lock:
            if self.expired or time.monotonic() >= self.deadline:
                self.expired = True
                self.changed.set()
                return self.deadline
            self.deadline = time.monotonic() + seconds
            self.changed.set()
            return self.deadline

    def _run(self) -> None:
        while True:
            with self.lock:
                if self.stopped:
                    return
                remaining = self.deadline - time.monotonic()
                self.changed.clear()
                if remaining <= 0:
                    self.expired = True
            if remaining > 0:
                self.changed.wait(min(remaining, 60.0))
                continue
            try:
                if not self.handle.terminate():
                    raise RuntimeError("Windows deadline could not terminate the Job")
            except BaseException as exc:
                self.error = exc
            return

    def close(self) -> None:
        with self.lock:
            self.stopped = True
            self.changed.set()
        self.thread.join(_CLEANUP_SECONDS * 2 + 1)
        if self.thread.is_alive():
            raise RuntimeError("Windows deadline watcher did not stop")
        if self.error is not None:
            raise RuntimeError("Windows deadline containment failed") from self.error


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _worker_main(directory: str) -> None:
    root = Path(directory)
    kernel = None
    try:
        # Pickles are private, trusted runtime input, never accepted remotely.
        # User imports/unpickling happen only after atomic Job assignment.
        request = pickle.loads((root / "request.pickle").read_bytes())
        sys.path[:] = request["sys_path"]
        if request["main_module"] or request["main_path"]:
            import runpy
            if request["main_module"]:
                main = runpy.run_module(request["main_module"], run_name="__mp_main__", alter_sys=True)
            else:
                main = runpy.run_path(request["main_path"], run_name="__mp_main__")
            import types
            module = types.ModuleType("__mp_main__")
            module.__dict__.update(main)
            sys.modules["__main__"] = sys.modules["__mp_main__"] = module
        handler, command, lease, now = pickle.loads(request["invocation"])
        kernel = SQLiteKernel(request["db_path"], now=now, durability=request["durability"])
        effects = HandlerEffects(kernel, lease, lambda: True)
        context = HandlerContext(command, lease, effects)
        _atomic_write(root / "ready", "ready")
        while not (root / "go").exists():
            time.sleep(_POLL_SECONDS)
        outcome = invoke_handler(handler, command, context)
        encoded = _serialize_handler_outcome(outcome, effects)
        kernel.close()
        kernel = None
        _atomic_write(root / "outcome.json", encoded)
    except BaseException as exc:
        traceback.print_exc()
        _atomic_write(root / "outcome.json", json.dumps({
            "kind": "error", "code": "handler_process_start_failure",
            "message": str(exc), "retryable": False,
            "details": {"exception_type": type(exc).__name__}, "effect_ids": []}, allow_nan=False))
    finally:
        if kernel is not None:
            kernel.close()


# Redirect file descriptors before importing the worker module so bootstrap
# tracebacks and native stdout/stderr share the bounded diagnostic tail.
_BOOTSTRAP = """
import io, os, sys
d = sys.argv[1]
# A GUI host may provide neither OS standard handles nor valid CRT descriptors.
# Reserve 0/1/2 before opening the log files, so dup2 cannot overwrite a source.
for fd in (0, 1, 2):
    try:
        os.fstat(fd)
    except OSError:
        null = os.open(os.devnull, os.O_RDWR)
        if null != fd:
            os.dup2(null, fd)
            os.close(null)
o = os.open(os.path.join(d, 'stdout.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
e = os.open(os.path.join(d, 'stderr.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.dup2(o, 1)
os.dup2(e, 2)
os.close(o)
os.close(e)
import ctypes, msvcrt
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.SetStdHandle.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
k.SetStdHandle(-11, msvcrt.get_osfhandle(1))
k.SetStdHandle(-12, msvcrt.get_osfhandle(2))
# Python initialized these objects before redirection; pythonw can leave them
# as None, and console streams can retain the original console handles.
sys.stdout = sys.__stdout__ = io.TextIOWrapper(
    io.FileIO(1, 'wb', closefd=False), encoding='utf-8', errors='backslashreplace', write_through=True)
sys.stderr = sys.__stderr__ = io.TextIOWrapper(
    io.FileIO(2, 'wb', closefd=False), encoding='utf-8', errors='backslashreplace', write_through=True)
from dispatcher_sdk.execution_kernel._windows_runtime import _worker_main
_worker_main(d)
"""


def invoke_windows_handler(
    *, db_path: str, handler: Handler, command: ExecutionCommandV2,
    lease: ExecutionLease, now: Any, start_timeout: float,
    durability: Durability = "full",
    on_started: Optional[Callable[[WindowsProcessHandle], bool]] = None,
    on_finished: Optional[Callable[[WindowsProcessHandle], None]] = None,
) -> dict[str, Any]:
    """Spawn one native Windows worker and publish only after Job containment."""
    profile = validate_durability(durability)
    if db_path == ":memory:":
        raise ValueError("Windows process isolation requires a file-backed SQLite database")
    if type(start_timeout) not in (int, float) or not math.isfinite(start_timeout) or start_timeout <= 0:
        raise ValueError("start_timeout must be finite and positive")
    api = _WinAPI()
    start_deadline = time.monotonic() + start_timeout
    with tempfile.TemporaryDirectory(prefix="dispatcher-windows-") as directory:
        root = Path(directory)
        main = sys.modules.get("__main__")
        main_path = getattr(main, "__file__", None)
        main_module = getattr(getattr(main, "__spec__", None), "name", None)
        if main_module and (main_module == "__main__" or main_module.endswith(".__main__")):
            main_module = None
        if main_path and (not os.path.isfile(main_path) or main_path.endswith("__main__.py")):
            main_path = None
        request = {"db_path": os.path.abspath(db_path), "durability": profile,
                   "sys_path": list(sys.path), "main_path": main_path, "main_module": main_module,
                   "invocation": pickle.dumps((handler, command, lease, now), protocol=4)}
        (root / "request.pickle").write_bytes(pickle.dumps(request, protocol=4))
        # sys.path may be configured by an embedder/test runner without PYTHONPATH.
        bootstrap = "import sys; sys.path[:]=%r; " % list(sys.path) + _BOOTSTRAP
        job, info = _create_suspended(api, [sys.executable, "-u", "-c", bootstrap, directory])
        handle = WindowsProcessHandle(api, job, info)
        watchdog = None
        registered = False
        deadline = None
        outcome = None
        contained_at = None
        try:
            watchdog = _Watchdog(handle, start_deadline)
            if on_started is not None:
                registered = bool(on_started(handle))
                if not registered:
                    handle.revoke("runtime_closed")
            handle.resume()
            while not watchdog.expired and handle.revocation_reason is None:
                if deadline is None and (root / "ready").exists():
                    deadline = watchdog.business_deadline(command.timeout_seconds)
                    if not watchdog.expired:
                        _atomic_write(root / "go", "invoke")
                if (root / "outcome.json").exists():
                    outcome = json.loads((root / "outcome.json").read_text(encoding="utf-8"))
                    break
                if handle.exited():
                    break
                time.sleep(_POLL_SECONDS)
        finally:
            try:
                if not handle.terminate():
                    raise RuntimeError("Windows Job did not reach zero active processes")
                contained_at = time.monotonic()
            finally:
                try:
                    if watchdog is not None:
                        watchdog.close()
                finally:
                    try:
                        handle.close()
                    finally:
                        if registered and on_finished is not None:
                            on_finished(handle)
        if handle.revocation_reason is not None:
            return {"kind": "authority_revoked", "reason": handle.revocation_reason, "effect_ids": []}
        if deadline is not None and (contained_at is None or contained_at >= deadline):
            return {"kind": "timeout", "effect_ids": []}
        # The worker can atomically publish between the loop's file check and
        # its exit check. After containment no writer remains, so recover that
        # final publication without weakening cancellation or deadline checks.
        if outcome is None and (root / "outcome.json").exists():
            outcome = json.loads((root / "outcome.json").read_text(encoding="utf-8"))
        stderr = root / "stderr.log"
        tail = ""
        if stderr.exists():
            with stderr.open("rb") as stream:
                stream.seek(max(0, stderr.stat().st_size - 8192))
                tail = stream.read(8192).decode("utf-8", errors="replace")
        if type(outcome) is dict:
            if outcome.get("kind") == "error" and tail:
                outcome["details"] = {**(outcome.get("details") or {}), "stderr_tail": tail}
            return outcome
        return {"kind": "error", "code": "handler_process_exit" if deadline else "handler_process_start_failure",
                "message": "Windows worker exited without a completed outcome",
                "retryable": False, "details": {"exitcode": handle.exitcode, "stderr_tail": tail},
                "effect_ids": []}
