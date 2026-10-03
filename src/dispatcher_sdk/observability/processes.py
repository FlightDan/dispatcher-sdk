"""Bounded observation of registered process handles, independent of execution.

The collector never reads application streams, waits for process completion,
terminates processes, or infers OOM. It observes only registered handles and
retains exact-handle evidence separately from optional Linux birth metadata.
"""

from __future__ import annotations

from copy import deepcopy
import multiprocessing.process
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Any
import uuid


def _birth(pid: int) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if os.name != "posix":
        return None, None, "birth_identity_unavailable"
    try:
        if not Path("/proc/self/stat").exists():
            return None, None, "birth_identity_unavailable"
        own_namespace = os.readlink("/proc/self/ns/pid")
        namespace = os.readlink(f"/proc/{pid}/ns/pid")
        if namespace != own_namespace:
            return None, namespace, "pid_namespace_differs"
        with open(f"/proc/{pid}/stat", "rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096 or b")" not in raw:
            return None, namespace, "process_stat_unrecognized"
        # comm may contain spaces or parentheses; fields after its final ')'
        # begin at stat field 3. Field 22 is the native process start tick.
        fields = raw.rsplit(b")", 1)[1].split()
        if len(fields) < 20:
            return None, namespace, "process_stat_unrecognized"
        ticks = int(fields[19])
        return {"pid": pid, "start_ticks": ticks, "namespace": namespace}, namespace, None
    except (OSError, ValueError):
        return None, None, "process_identity_inaccessible"


def _handle(process: Any) -> tuple[Any, str]:
    if isinstance(process, subprocess.Popen):
        return process, "popen"
    if isinstance(process, multiprocessing.process.BaseProcess):
        return process, "multiprocessing"
    cls = type(process)
    if cls.__module__ == "dispatcher_sdk.execution_kernel._process_runtime" and cls.__name__ == "ProcessSupervisorHandle":
        child = getattr(process, "_process", None)
        if isinstance(child, multiprocessing.process.BaseProcess):
            return child, "multiprocessing"
    if cls.__module__ == "dispatcher_sdk.execution_kernel._windows_runtime" and cls.__name__ == "WindowsProcessHandle":
        return process, "windows_native"
    return process, "unsupported"


def _exit_evidence(code: int | None, kind: str) -> dict[str, Any]:
    result: dict[str, Any] = {"returncode": code, "exit_kind": "unknown", "signal": None,
                              "oom": "unknown", "cleanup": "unknown"}
    if code is None:
        return result
    if code < 0 and os.name == "posix" and kind != "windows_native":
        result["exit_kind"] = "signal"
        result["signal"] = -code
        try:
            result["signal_name"] = signal.Signals(-code).name
        except ValueError:
            pass
    else:
        result["exit_kind"] = "status"
    # Positive 137 is retained as an exit status, never converted to proof of
    # SIGKILL/OOM. Exact process exit alone proves no descendant cleanup.
    return result


class ObservedProcess:
    """A registered handle's bounded local observations, without control powers."""

    def __init__(self, owner: ProcessObserver, process: Any, role: str, process_id: str) -> None:
        self.owner, self.process_id, self.role = owner, process_id, role
        self.process, self.kind = _handle(process)
        try:
            pid = process if type(process) is int else getattr(self.process, "pid", None)
        except Exception:
            pid = None
        self.pid = pid if type(pid) is int and pid > 0 else None
        if self.kind != "unsupported" and self.pid is not None:
            self.birth_identity, self.namespace, reason = _birth(self.pid)
        else:
            self.birth_identity, self.namespace, reason = None, None, "process_handle_required"
        self._lock = threading.Lock()
        self._report: dict[str, Any] = {"process_id": process_id, "role": role, "pid": self.pid,
            "birth_identity": self.birth_identity, "namespace": self.namespace,
            "handle_kind": self.kind, "state": "unknown", "observed_at": None,
            "collected_at": None, "persisted_at": None, "evidence": {},
            "unknown_reason": reason or "not_observed", "collection_error": None}
        self._registered = False
        self._last_persisted_monotonic = 0.0
        self._last_persisted_state: tuple[Any, ...] | None = None

    def _unavailable(self, reason: str) -> ObservedProcess:
        with self._lock:
            self._report.update(unknown_reason=reason, collection_error=reason)
        return self

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            report = deepcopy(self._report)
        report["last_observed_state"] = report["state"]
        observed = report["observed_at"]
        now = float(self.owner._clock())
        if report["state"] == "alive" and (self.owner._stop.is_set() or observed is None or
                now < observed or now - observed > self.owner.freshness):
            report["state"] = "unknown"
            report["unknown_reason"] = "collector_closed" if self.owner._stop.is_set() else "observation_stale"
        return report

    def _sample(self) -> None:
        with self._lock:
            if self._report["state"] == "exited":
                return
        state, reason, code = "unknown", None, None
        evidence: dict[str, Any] = {}
        try:
            if self.kind == "unsupported":
                reason = "process_handle_required"
            elif self.pid is None:
                reason = "process_not_started"
            elif self.kind == "popen":
                code = self.process.poll()
                if code is not None:
                    state, evidence = "exited", {"source": "popen_wait_status", **_exit_evidence(code, self.kind)}
                else:
                    state, reason, evidence = self._alive_identity()
            elif self.kind == "multiprocessing":
                code = self.process.exitcode
                if code is not None:
                    state, evidence = "exited", {"source": "multiprocessing_wait_status", **_exit_evidence(code, self.kind)}
                elif self.process.is_alive():
                    state, reason, evidence = self._alive_identity()
                else:
                    reason = "process_state_unconfirmed"
            elif self.kind == "windows_native":
                lock = getattr(self.process, "_lock", None)
                if lock is None or not lock.acquire(blocking=False):
                    reason = "native_handle_busy"
                else:
                    try:
                        code = self.process.exitcode
                        if getattr(self.process, "_closed", False) and code is None:
                            reason = "native_handle_closed_without_exit_status"
                        elif self.process.exited():
                            state, evidence = "exited", {"source": "native_process_handle", **_exit_evidence(code, self.kind)}
                        else:
                            state, evidence = "alive", {"source": "native_process_handle"}
                    finally:
                        lock.release()
        except Exception as exc:
            reason = "handle_collection_failed"
            evidence = {"error_type": type(exc).__name__}
        now = float(self.owner._clock())
        with self._lock:
            self._report.update(state=state, observed_at=now, collected_at=now,
                                evidence=evidence, unknown_reason=reason if state == "unknown" else None)

    def _alive_identity(self) -> tuple[str, str | None, dict[str, Any]]:
        if os.name == "nt":
            return "alive", None, {"source": "exact_process_handle"}
        if self.birth_identity is None:
            return "unknown", "process_identity_inaccessible", {"source": "exact_handle_pending_without_birth"}
        birth, namespace, reason = _birth(self.pid)
        if birth is None:
            return "unknown", reason, {"source": "linux_process_identity", "namespace": namespace}
        if birth != self.birth_identity:
            return "unknown", "process_birth_identity_changed", {"source": "linux_process_identity"}
        return "alive", None, {"source": "exact_handle_and_linux_birth", "birth_identity": birth}

    def _persist(self) -> None:
        with self._lock:
            report = deepcopy(self._report)
        key = (report["state"], report["unknown_reason"], report["evidence"].get("returncode"))
        now = self.owner._monotonic()
        if self._registered and key == self._last_persisted_state and report["state"] == "exited":
            return
        if self._registered and key == self._last_persisted_state and now - self._last_persisted_monotonic < self.owner.persist_interval:
            return
        try:
            journal, identity = self.owner.activity.journal, self.owner.activity.identity
            if not self._registered:
                journal.register_process(identity, self.process_id, role=self.role, pid=self.pid,
                    birth_identity=self.birth_identity, namespace=self.namespace,
                    source=self.owner.activity.source_id)
                self._registered = True
            journal.observe_process(identity, self.process_id, report["state"], observed_at=report["observed_at"],
                evidence=report["evidence"], unknown_reason=report["unknown_reason"])
            self._last_persisted_state, self._last_persisted_monotonic = key, now
            with self._lock:
                self._report.update(persisted_at=float(self.owner._clock()), collection_error=None)
        except Exception as exc:
            with self._lock:
                self._report["collection_error"] = f"{type(exc).__name__}: {exc}"[:2048]


class ProcessObserver:
    """One independent collector per execution with a fixed registration bound."""

    def __init__(self, activity: Any, *, poll_interval: float = .2,
                 max_processes: int = 32, start: bool = True, clock=None, monotonic=None) -> None:
        if type(poll_interval) not in (int, float) or not 0 < poll_interval <= 60:
            raise ValueError("poll_interval must be positive and at most 60 seconds")
        if type(max_processes) is not int or not 1 <= max_processes <= 32:
            raise ValueError("max_processes must be between 1 and 32")
        self.activity, self.poll_interval, self.max_processes = activity, float(poll_interval), max_processes
        self._clock, self._monotonic = clock or time.time, monotonic or time.monotonic
        self.freshness = activity.options.process_freshness
        self.persist_interval = max(1.0, activity.options.flush_interval)
        self._lock = threading.Lock()
        self._stop, self._wake = threading.Event(), threading.Event()
        self._processes: dict[str, ObservedProcess] = {}
        self._thread: threading.Thread | None = None
        self._last_error: str | None = None
        if start:
            self.start()

    def start(self) -> ProcessObserver:
        with self._lock:
            if self._stop.is_set():
                raise RuntimeError("process observer is closed")
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="dispatcher-process-observer", daemon=True)
                self._thread.start()
        return self

    def observe_process(self, process: Any, *, role: str = "agent", process_id: str | None = None) -> ObservedProcess:
        """Register without consuming streams or controlling the process.

        Explicitly invalid registration options are configuration errors. Poll
        and persistence failures remain observations and do not escape to the
        business handler. Reusing an ID for another handle is rejected.
        """
        for name, value in (("role", role), ("process_id", process_id)):
            if value is not None and (type(value) is not str or not value.strip() or len(value) > 1024):
                raise ValueError(f"{name} must be a nonempty string of at most 1024 characters")
        process_id = process_id or str(uuid.uuid4())
        with self._lock:
            if self._stop.is_set():
                return ObservedProcess(self, process, role, process_id)._unavailable("collector_closed")
            previous = self._processes.get(process_id)
            if previous is not None:
                if _handle(process)[0] is not previous.process or role != previous.role:
                    return ObservedProcess(self, process, role, process_id)._unavailable("process_registration_conflict")
                return previous
            if len(self._processes) >= self.max_processes:
                self._last_error = "process_observer_capacity_exhausted"
                return ObservedProcess(self, process, role, process_id)._unavailable("process_observer_capacity_exhausted")
            observed = ObservedProcess(self, process, role, process_id)
            self._processes[process_id] = observed
        self._wake.set()
        return observed

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                processes = tuple(self._processes.values())
            for observed in processes:
                if self._stop.is_set():
                    break
                try:
                    observed._sample()
                except Exception as exc:
                    self._last_error = f"{type(exc).__name__}: {exc}"[:2048]
            for observed in processes:
                if self._stop.is_set():
                    break
                observed._persist()
            self._wake.wait(self.poll_interval)
            self._wake.clear()
        # Final collection stays on this independent thread. Caller close is
        # bounded even if a platform handle or journal cannot be collected.
        # A completed exact handle may become exited; still-live observations
        # become unknown because automatic collection is ending.
        with self._lock:
            processes = tuple(self._processes.values())
        for observed in processes:
            try:
                observed._sample()
                with observed._lock:
                    if observed._report["state"] == "alive":
                        observed._report.update(state="unknown", unknown_reason="collector_closed")
                observed._persist()
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"[:2048]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            processes = tuple(self._processes.values())
        reports = [process.snapshot() for process in processes]
        return {"observed_at": float(self._clock()), "state": "closed" if self._stop.is_set() else "active",
            "max_processes": self.max_processes, "registered_processes": len(reports), "processes": reports,
            "collector_alive": self._thread is not None and self._thread.is_alive(),
            "complete": self._last_error is None and all(report["collection_error"] is None for report in reports),
            "error": self._last_error}

    def close(self, *, timeout: float = 1.0) -> dict[str, Any]:
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise ValueError("timeout must be positive and at most 60 seconds")
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(float(timeout))
        report = self.snapshot()
        report["unfinished_collector"] = report["collector_alive"]
        return report

    def __enter__(self) -> ProcessObserver:
        return self.start()

    def __exit__(self, *args: Any) -> None:
        self.close()


__all__ = ["ProcessObserver", "ObservedProcess"]
