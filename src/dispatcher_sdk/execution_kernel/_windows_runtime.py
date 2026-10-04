"""Windows native process containment for trusted handlers.

A fresh interpreter is created suspended, atomically assigned to an unnamed
kill-on-close Job, and resumed only after runtime registration. The caller owns
the only Job handle. A separate host thread enforces startup/business deadlines.
This is process-tree containment, not a sandbox for hostile same-user code.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from typing import Any, Callable, Optional

from ..durability import Durability, validate_durability
from ._process_runtime import (
    invoke_handler, _serialize_handler_outcome,
    _budget_outcome, _confirmed_entry_packet, _close_context, _capture_completion_time,
    _bootstrap_diagnostic, _observe_phase, _budget_sample, _merge_budget_floor,
)
from .budget import BudgetClockUnknownError, BudgetEnvelope
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
_MAX_JOB_PROCESSES = 4096


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
            "OpenProcess": ([D, B, D], H),
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

    def process_ids(self, job: Any) -> tuple[int, ...]:
        capacity = 64
        for _ in range(7):
            class ProcessList(ctypes.Structure):
                _fields_ = [("assigned", wintypes.DWORD), ("count", wintypes.DWORD),
                            ("ids", ctypes.c_size_t * capacity)]

            listing = ProcessList()
            result = self.dll.QueryInformationJobObject(job, 3, ctypes.byref(listing), ctypes.sizeof(listing), None)
            if result and listing.count <= capacity and listing.assigned <= listing.count:
                return tuple(int(listing.ids[index]) for index in range(listing.count))
            if not result and ctypes.get_last_error() != 234:
                self.check(result, "QueryInformationJobObject process list")
            capacity = max(capacity * 2, int(listing.assigned))
            if capacity > _MAX_JOB_PROCESSES:
                break
        raise RuntimeError("Windows Job process list exceeds its bounded enumeration")


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
        self._worker_pid: Optional[int] = None
        self._worker_process: Any = None

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

    def preserve_worker(self, pid: int) -> None:
        """Pin the interpreter identity before permitting its invocation.

        A Windows venv executable can launch the interpreter as another Job
        member. That interpreter owns the final flush, rather than the launcher.
        """
        if type(pid) is not int or pid <= 0:
            raise ValueError("Windows worker readiness lacks a valid process identity")
        with self._lock:
            if self._worker_pid is not None:
                if pid != self._worker_pid:
                    raise RuntimeError("Windows worker entry changed its ready process identity")
                return
            if self._closed or self._contained:
                raise RuntimeError("Windows worker exited before invocation permission")
            process = self._api.dll.OpenProcess(0x00101001, False, pid)
            self._api.check(process, "OpenProcess ready worker")
            try:
                assigned = wintypes.BOOL()
                self._api.check(self._api.dll.IsProcessInJob(process, self._job, ctypes.byref(assigned)),
                                "IsProcessInJob ready worker")
                if not assigned.value:
                    raise RuntimeError("Windows ready worker is outside its containment Job")
                if self._api.dll.WaitForSingleObject(process, 0) != _WAIT_TIMEOUT:
                    raise RuntimeError("Windows worker exited before invocation permission")
            except BaseException:
                self._api.dll.CloseHandle(process)
                raise
            self._worker_pid, self._worker_process = pid, process

    def stop_descendants(self, until: float) -> bool:
        """Stop Job members while preserving the original worker's flush."""
        with self._lock:
            if self._closed or self._contained:
                return self._contained
            quiet_since = None
            while time.monotonic() < until:
                preserved = {self.pid}
                if (self._worker_process is not None
                        and self._api.dll.WaitForSingleObject(self._worker_process, 0) == _WAIT_TIMEOUT):
                    preserved.add(self._worker_pid)
                pids = tuple(pid for pid in self._api.process_ids(self._job) if pid not in preserved)
                if not pids:
                    quiet_since = time.monotonic() if quiet_since is None else quiet_since
                    if time.monotonic() - quiet_since >= _POLL_SECONDS:
                        return True
                else:
                    quiet_since = None
                for pid in pids:
                    if time.monotonic() >= until:
                        return False
                    # PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE.
                    process = self._api.dll.OpenProcess(0x00101001, False, pid)
                    if not process:
                        if ctypes.get_last_error() == 87:
                            continue
                        self._api.check(False, "OpenProcess contained descendant")
                    try:
                        assigned = wintypes.BOOL()
                        self._api.check(self._api.dll.IsProcessInJob(process, self._job, ctypes.byref(assigned)),
                                        "IsProcessInJob descendant")
                        # The acquired handle protects identity across PID reuse.
                        if assigned.value and self._api.dll.WaitForSingleObject(process, 0) == _WAIT_TIMEOUT:
                            self._api.check(self._api.dll.TerminateProcess(process, 70), "TerminateProcess descendant")
                    finally:
                        self._api.dll.CloseHandle(process)
                time.sleep(min(_POLL_SECONDS, max(0, until - time.monotonic())))
            return False

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                if not self.terminate():
                    raise RuntimeError("Windows Job did not reach zero active processes")
            finally:
                for resource in (self._worker_process, self._info.hThread, self._info.hProcess, self._job):
                    if resource:
                        self._api.dll.CloseHandle(resource)
                self._worker_process = None
                self._closed = True


class _Watchdog:
    def __init__(self, handle: WindowsProcessHandle, deadline: float,
                 envelope: BudgetEnvelope | None = None, now: Any = None) -> None:
        self.handle, self.deadline = handle, deadline
        self.envelope, self.now = envelope, now
        self.cleanup = False
        self.clock_error: BudgetClockUnknownError | None = None
        self.lock = threading.Lock()
        try:
            with self.lock:
                self._retain_sample_locked()
                self.inherited_work_deadline = self._bound_locked(math.inf)
                self.inherited_hard_deadline = self._bound_locked(math.inf, hard=True)
        except BudgetClockUnknownError as exc:
            self.clock_error = exc
            self.inherited_work_deadline = self.inherited_hard_deadline = time.monotonic()
        self.changed = threading.Event()
        self.stopped = False
        self.expired = False
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, name="kernel-windows-deadline", daemon=True)
        self.thread.start()

    def _retain_sample_locked(self) -> None:
        if self.envelope is not None:
            self.envelope = self.envelope.recheckpoint(sample=_budget_sample(self.now))

    def _bound_locked(self, deadline: float, *, hard: bool = False) -> float:
        if self.envelope is None:
            return deadline
        bound = self.envelope.deadline_monotonic(hard=hard, sample=self.envelope.checkpoint)
        return deadline if bound is None else min(deadline, bound)

    def snapshot(self) -> BudgetEnvelope | None:
        """Return already observed authority without sampling a fresh wall clock."""
        with self.lock:
            return self.envelope

    def hard_deadline_bound(self, deadline: float) -> float:
        with self.lock:
            return min(self.inherited_hard_deadline, self._bound_locked(deadline, hard=True))

    def business_deadline(self, seconds: float, *, envelope: BudgetEnvelope | None = None,
                          deadline: float | None = None) -> float:
        with self.lock:
            if self.expired or time.monotonic() >= self.deadline:
                self.expired = True
                self.changed.set()
                return self.deadline
            if envelope is not None:
                if self.envelope is not None:
                    envelope = BudgetEnvelope((*self.envelope.constraints, *envelope.constraints),
                                              envelope.checkpoint, envelope.started_at)
                    envelope = _merge_budget_floor(envelope, self.envelope)
                self.envelope = envelope
            self._retain_sample_locked()
            self.deadline = min(self.inherited_work_deadline, self._bound_locked(
                time.monotonic() + seconds if deadline is None else deadline))
            self.changed.set()
            return self.deadline

    def cleanup_deadline(self, deadline: float) -> None:
        with self.lock:
            self.cleanup = True
            self.deadline = min(self.inherited_hard_deadline,
                                self._bound_locked(deadline, hard=True))
            self.changed.set()

    def _run(self) -> None:
        while True:
            with self.lock:
                if self.stopped:
                    return
                try:
                    self._retain_sample_locked()
                    self.inherited_work_deadline = self._bound_locked(self.inherited_work_deadline)
                    self.inherited_hard_deadline = self._bound_locked(self.inherited_hard_deadline, hard=True)
                    self.deadline = self._bound_locked(self.deadline, hard=self.cleanup)
                    remaining = self.deadline - time.monotonic()
                except BudgetClockUnknownError as exc:
                    self.clock_error = exc
                    remaining = 0.0
                self.changed.clear()
                if remaining <= 0:
                    self.expired = True
            if remaining > 0:
                self.changed.wait(min(remaining, 0.05))
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


@contextmanager
def _worker_directory():
    directory = tempfile.mkdtemp(prefix="dispatcher-windows-")
    try:
        yield directory
    finally:
        # Containment is checked before leaving this scope. A separate process
        # (for example a file scanner) can still briefly hold a diagnostic file.
        deadline = time.monotonic() + _CLEANUP_SECONDS
        while True:
            try:
                # Older TemporaryDirectory cleanup can replace a sharing
                # violation with NotADirectoryError while handling the error.
                shutil.rmtree(directory)
                break
            except PermissionError as error:
                if getattr(error, "winerror", None) not in (32, 33) or time.monotonic() >= deadline:
                    raise
                time.sleep(_POLL_SECONDS)


def _worker_main(directory: str) -> None:
    root = Path(directory)
    kernel = None
    context: HandlerContext | None = None
    encoded = None
    entry_announced = False
    stage = "worker_deserialization"
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
        handler, command, lease, now, envelope, service_spec = pickle.loads(request["invocation"])
        stage = "worker_setup"
        kernel = SQLiteKernel(request["db_path"], now=now, durability=request["durability"])
        effects = HandlerEffects(kernel, lease, lambda: True)
        context = HandlerContext(command, lease, effects,
                                 budget_envelope=envelope, service_spec=service_spec)
        _atomic_write(root / "ready", json.dumps({"worker_pid": os.getpid(), "observed_at": time.time()}))
        while not (root / "go").exists():
            time.sleep(_POLL_SECONDS)
        stage = "handler_entry"
        def announce_entry(entered: HandlerContext) -> None:
            nonlocal entry_announced, stage
            _atomic_write(root / "entered.json", json.dumps(_confirmed_entry_packet(entered, now)))
            entry_announced = True
            stage = "handler_execution"

        outcome = invoke_handler(handler, command, context, on_entered=announce_entry)
        _capture_completion_time(outcome, context)
        encoded = _serialize_handler_outcome(outcome, effects)
        stage = "worker_finalization"
        if entry_announced:
            _atomic_write(root / "returned.json", json.dumps({"outcome_json": encoded,
                "completed_monotonic": time.monotonic()}, allow_nan=False))
        receipt = _close_context(context)
        if receipt["state"] != "confirmed":
            final = json.loads(encoded)
            final["telemetry_flush"] = receipt
            encoded = json.dumps(final, allow_nan=False)
        context = None
        kernel.close()
        kernel = None
        _atomic_write(root / "outcome.json", encoded)
    except BaseException as exc:
        traceback.print_exc()
        details = _bootstrap_diagnostic(exc, stage)
        _atomic_write(root / "outcome.json", encoded if encoded is not None else json.dumps({
            "kind": "error", "code": "handler_process_start_failure",
            "message": details["message"], "retryable": False,
            "details": details, "effect_ids": []}, allow_nan=False))
    finally:
        _close_context(context)
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
    on_cleanup_confirmed: Optional[Callable[[], None]] = None,
    budget_envelope: BudgetEnvelope | None = None,
    service_spec: dict | None = None,
    on_entered: Optional[Callable[[dict[str, Any]], None]] = None,
    on_phase: Optional[Callable[[str, dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Spawn one native Windows worker and publish only after Job containment."""
    profile = validate_durability(durability)
    if db_path == ":memory:":
        raise ValueError("Windows process isolation requires a file-backed SQLite database")
    if type(start_timeout) not in (int, float) or not math.isfinite(start_timeout) or start_timeout <= 0:
        raise ValueError("start_timeout must be finite and positive")
    try:
        if budget_envelope is not None:
            budget_envelope = budget_envelope.recheckpoint(sample=_budget_sample(now))
            bound = budget_envelope.deadline_monotonic(sample=budget_envelope.checkpoint)
            start_deadline = min(time.monotonic() + start_timeout,
                                 math.inf if bound is None else bound)
        else:
            start_deadline = time.monotonic() + start_timeout
    except BudgetClockUnknownError as exc:
        return _budget_outcome({"kind": "error", "code": "budget_clock_unknown", "message": str(exc),
                               "control_error": True, "retryable": False, "effect_ids": []}, budget_envelope)
    if start_deadline <= time.monotonic():
        return _budget_outcome({"kind": "timeout", "phase": "admission", "effect_ids": []}, budget_envelope)
    api = _WinAPI()
    with _worker_directory() as directory:
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
                   "invocation": pickle.dumps((handler, command, lease, now, budget_envelope, service_spec), protocol=4)}
        (root / "request.pickle").write_bytes(pickle.dumps(request, protocol=4))
        # sys.path may be configured by an embedder/test runner without PYTHONPATH.
        bootstrap = "import sys; sys.path[:]=%r; " % list(sys.path) + _BOOTSTRAP
        job, info = _create_suspended(api, [sys.executable, "-u", "-c", bootstrap, directory])
        handle = WindowsProcessHandle(api, job, info)
        watchdog = None
        registered = False
        deadline = None
        hard_deadline = None
        entry = None
        invocation_permitted = False
        work_expired = False
        outcome = None
        contained_at = None
        returned = False
        telemetry_unknown = None
        try:
            watchdog = _Watchdog(handle, start_deadline, budget_envelope, now)
            if on_started is not None:
                registered = bool(on_started(handle))
                if not registered:
                    handle.revoke("runtime_closed")
            handle.resume()
            while not watchdog.expired and handle.revocation_reason is None:
                if not invocation_permitted and (root / "ready").exists():
                    try:
                        ready = json.loads((root / "ready").read_text(encoding="utf-8"))
                        handle.preserve_worker(ready["worker_pid"])
                    except Exception as exc:
                        # A cutoff or cancellation can stop the worker while
                        # its ready identity is being acquired. Keep that
                        # authority outcome rather than replacing it with the
                        # resulting OpenProcess/readiness error.
                        if not watchdog.expired and handle.revocation_reason is None:
                            outcome = {"kind": "error", "code": "handler_process_start_failure",
                                "message": str(exc), "retryable": False, "effect_ids": [],
                                "details": _bootstrap_diagnostic(exc, "worker_ready_identity")}
                        break
                    if watchdog.expired or handle.revocation_reason is not None:
                        break
                    if on_phase is not None:
                        _observe_phase(on_phase, "worker_ready", ready)
                    _atomic_write(root / "go", "invoke")
                    invocation_permitted = True
                    if budget_envelope is None:
                        deadline = watchdog.business_deadline(command.timeout_seconds)
                if entry is None and (root / "entered.json").exists():
                    entry = json.loads((root / "entered.json").read_text(encoding="utf-8"))
                    handle.preserve_worker(entry["worker_pid"])
                    actual = BudgetEnvelope.from_dict(entry["budget_envelope"])
                    if budget_envelope is not None:
                        actual = BudgetEnvelope((*budget_envelope.constraints, *actual.constraints),
                                                actual.checkpoint, actual.started_at)
                        budget_envelope = actual
                    deadline = watchdog.business_deadline(command.timeout_seconds, envelope=budget_envelope,
                                                         deadline=entry["deadline_monotonic"])
                    hard_deadline = watchdog.hard_deadline_bound(entry["hard_deadline_monotonic"])
                    if on_entered is not None:
                        try:
                            on_entered(entry)
                        except BaseException:
                            pass
                if not returned and (root / "returned.json").exists():
                    completion = json.loads((root / "returned.json").read_text(encoding="utf-8"))
                    completed = completion.get("completed_monotonic")
                    if (deadline is None or type(completed) not in {int, float} or not math.isfinite(completed)
                            or completed >= deadline):
                        work_expired = True
                        break
                    outcome = json.loads(completion["outcome_json"])
                    returned = True
                    watchdog.cleanup_deadline(hard_deadline if hard_deadline is not None else deadline)
                if returned:
                    try:
                        until = min(hard_deadline if hard_deadline is not None else deadline, time.monotonic() + .25)
                        if not handle.stop_descendants(until):
                            telemetry_unknown = "descendant containment did not become quiet within its bound"
                            break
                    except Exception as exc:
                        telemetry_unknown = f"{type(exc).__name__}: {exc}"
                        break
                if (root / "outcome.json").exists():
                    outcome = json.loads((root / "outcome.json").read_text(encoding="utf-8"))
                    work_expired = not returned and deadline is not None and time.monotonic() >= deadline
                    if deadline is not None and time.monotonic() < deadline and hard_deadline is not None:
                        watchdog.cleanup_deadline(hard_deadline)
                    break
                if handle.exited():
                    break
                time.sleep(_POLL_SECONDS)
        except BudgetClockUnknownError as exc:
            outcome = {"kind": "error", "code": "budget_clock_unknown", "message": str(exc),
                       "control_error": True, "retryable": False, "effect_ids": []}
            if watchdog is not None:
                watchdog.clock_error = exc
        finally:
            try:
                if not handle.terminate():
                    raise RuntimeError("Windows Job did not reach zero active processes")
                contained_at = time.monotonic()
                if on_cleanup_confirmed is not None:
                    on_cleanup_confirmed()
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
        if watchdog is not None:
            snapshot = getattr(watchdog, "snapshot", None)
            observed = snapshot() if callable(snapshot) else None
            if observed is not None and budget_envelope is not None:
                try:
                    budget_envelope = _merge_budget_floor(budget_envelope, observed)
                except BudgetClockUnknownError as exc:
                    watchdog.clock_error = exc
        if handle.revocation_reason is not None:
            return _budget_outcome({"kind": "authority_revoked", "reason": handle.revocation_reason, "effect_ids": []}, budget_envelope, entry)
        if watchdog is not None and getattr(watchdog, "clock_error", None) is not None:
            return _budget_outcome({"kind": "error", "code": "budget_clock_unknown",
                                   "message": str(watchdog.clock_error), "control_error": True,
                                   "retryable": False, "effect_ids": []}, budget_envelope, entry)
        if (work_expired or (entry is None and deadline is not None and time.monotonic() >= deadline)
                or (watchdog is not None and watchdog.expired)
                or (hard_deadline is not None and (contained_at is None or contained_at >= hard_deadline))):
            capture_unknown = None
            if outcome is None and (budget_envelope is not None or entry is not None or (root / "returned.json").exists()):
                for name in ("outcome.json", "returned.json"):
                    path = root / name
                    if not path.exists():
                        continue
                    try:
                        if path.stat().st_size > 256 * 1024:
                            capture_unknown = "completed outcome exceeds bounded timeout diagnostics"
                            continue
                        captured = json.loads(path.read_text(encoding="utf-8"))
                        if name == "returned.json":
                            captured = json.loads(captured["outcome_json"])
                        if type(captured) is dict:
                            outcome = captured
                            break
                    except (ValueError, KeyError, TypeError, OSError) as exc:
                        capture_unknown = f"{type(exc).__name__}: {exc}"[:2048]
            timeout = {"kind": "timeout", "effect_ids": [] if type(outcome) is not dict else outcome.get("effect_ids", [])}
            admission_work_expired = (budget_envelope is not None and
                budget_envelope.view(sample=budget_envelope.checkpoint).remaining_work_seconds == 0)
            if entry is None and deadline is None and not admission_work_expired:
                # An internal startup cap does not establish spent business
                # authority. Inherited Run/tool exhaustion remains a timeout.
                timeout.update(kind="error", code="handler_process_start_failure",
                    message="handler startup window elapsed before confirmed handler entry", retryable=False)
                timeout["details"] = {"phase": "admission", "startup_window_elapsed": True,
                                      "invocation_permitted": invocation_permitted, "exitcode": handle.exitcode}
            if type(outcome) is dict:
                timeout["details"] = {**timeout.get("details", {}), "business_outcome": outcome}
            elif capture_unknown is not None:
                timeout["details"] = {**timeout.get("details", {}),
                    "business_outcome_capture": {"state": "unknown", "reason": capture_unknown}}
            return _budget_outcome(timeout, budget_envelope, entry)
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
            if telemetry_unknown is not None:
                outcome["telemetry_flush"] = {"state": "unknown", "reason": telemetry_unknown}
            if outcome.get("kind") == "error" and tail:
                outcome["details"] = {**(outcome.get("details") or {}), "stderr_tail": tail}
            if (entry is None and outcome.get("code") == "handler_process_start_failure"
                    and type(outcome.get("details")) is dict and outcome["details"].get("exception_type")):
                _observe_phase(on_phase, "worker_bootstrap_failed", outcome["details"])
            return _budget_outcome(outcome, budget_envelope, entry)
        return _budget_outcome({"kind": "error", "code": "handler_process_exit" if deadline else "handler_process_start_failure",
                "message": "Windows worker exited without a completed outcome",
                "retryable": False, "details": {"exitcode": handle.exitcode, "stderr_tail": tail},
                "effect_ids": []}, budget_envelope, entry)
