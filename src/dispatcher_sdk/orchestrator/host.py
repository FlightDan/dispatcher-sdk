"""Autonomous Kernel execution and durable application notification delivery."""

from __future__ import annotations

from dataclasses import dataclass, fields
import threading
import time
from typing import Callable
from uuid import uuid4

from ..execution_kernel.host import RuntimeHost, RuntimeHostHealth


@dataclass(frozen=True)
class OrchestratorHostHealth(RuntimeHostHealth):
    notification_alive: bool
    notification_deliveries: int
    notification_error_count: int
    last_notification_error: str | None


@dataclass(frozen=True)
class _Report:
    dispatch_deliveries: int


class _Transport:
    def __init__(self, orchestrator, wake_notifications):
        self.orchestrator = orchestrator
        self.wake_notifications = wake_notifications

    def pump(self, *, limit=100):
        delivered = self.orchestrator.flush(limit=limit)
        self.orchestrator.sync()
        if self.orchestrator.collect_notifications(limit=limit):
            self.wake_notifications.set()
        return _Report(dispatch_deliveries=delivered)

    def sweep(self, *, limit=100):
        return self.pump(limit=limit)


class OrchestratorHost:
    """Own the Orchestrator's runtime and drive it until explicitly stopped.

    The synchronous callback receives durable notification dictionaries on a
    separate daemon thread. It never runs on the coordinator or worker pool.
    Callback failures follow the Orchestrator's durable delivery retry policy;
    they do not make application decisions or retry executions.

    ``stop`` stops new delivery claims and drains the runtime, leaving unclaimed
    notifications durable for a subsequent host. Its default deadline is five
    seconds. Python cannot interrupt an arbitrary callback: a deadline expiry
    raises ``TimeoutError`` and the daemon thread may remain alive until the
    callback returns. Keep callback dependencies available until a later stop
    succeeds. The Orchestrator itself remains caller-owned.
    """

    def __init__(self, orchestrator, callback: Callable[[dict], object], *,
                 notification_interval: float = 0.05,
                 notification_lease_seconds: float = 30.0,
                 notification_retry_delay: float = 1.0,
                 notification_owner: str | None = None,
                 **runtime_options):
        runtime = getattr(orchestrator, "runtime", None)
        if runtime is None:
            raise ValueError("OrchestratorHost requires an Orchestrator runtime")
        if getattr(runtime, "kernel", None) is not getattr(orchestrator, "kernel", None):
            raise ValueError("runtime and orchestrator must share the Kernel")
        if not callable(callback):
            raise TypeError("callback must be callable")
        for name in ("flush", "sync", "collect_notifications", "deliver_notifications"):
            if not callable(getattr(orchestrator, name, None)):
                raise TypeError(f"orchestrator must provide {name}")
        self.notification_interval = RuntimeHost._positive_number(
            notification_interval, "notification_interval")
        self.notification_lease_seconds = RuntimeHost._positive_number(
            notification_lease_seconds, "notification_lease_seconds")
        self.notification_retry_delay = RuntimeHost._positive_number(
            notification_retry_delay, "notification_retry_delay")
        if notification_owner is not None and (
                not isinstance(notification_owner, str) or not notification_owner.strip()):
            raise ValueError("notification_owner must be a nonempty string")
        self.notification_owner = notification_owner or f"orchestrator-host-{uuid4().hex}"
        self.orchestrator = orchestrator
        self.callback = callback
        self.runtime = runtime
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread = None
        self._deliveries = 0
        self._error_count = 0
        self._last_error = None
        self.runtime_host = RuntimeHost(
            runtime, _Transport(orchestrator, self._wake_event), **runtime_options)

    def start(self):
        with self._lock:
            if self._stop_event.is_set():
                raise RuntimeError("cannot restart a stopped OrchestratorHost")
            if self._thread is not None:
                return self
            self.runtime_host.start()
            try:
                thread = threading.Thread(target=self._deliver, daemon=True,
                                          name="orchestrator-host-notifications")
                thread.start()
                self._thread = thread
            except BaseException as error:
                self._stop_event.set()
                try:
                    self.runtime_host.stop(timeout=5.0)
                except BaseException as cleanup_error:
                    if hasattr(error, "add_note"):
                        error.add_note(f"Runtime cleanup failed: {cleanup_error}")
                raise
        return self

    def wake(self, run_id: str | None = None) -> bool:
        self._wake_event.set()
        return self.runtime_host.wake(run_id)

    def _deliver(self):
        while not self._stop_event.is_set():
            try:
                count = self.orchestrator.deliver_notifications(
                    self.callback, owner=self.notification_owner,
                    lease_seconds=self.notification_lease_seconds,
                    retry_delay=self.notification_retry_delay, limit=1)
                with self._lock:
                    self._deliveries += count
            except Exception as error:
                with self._lock:
                    self._error_count += 1
                    self._last_error = f"{type(error).__name__}: {error}"
                count = 0
            if not count:
                self._wake_event.wait(self.notification_interval)
                self._wake_event.clear()

    def health(self) -> OrchestratorHostHealth:
        runtime = self.runtime_host.health()
        values = {field.name: getattr(runtime, field.name) for field in fields(runtime)}
        with self._lock:
            alive = self._thread is not None and self._thread.is_alive()
            if alive and values["state"] == "stopped":
                values["state"] = "stopping"
            return OrchestratorHostHealth(
                **values, notification_alive=alive,
                notification_deliveries=self._deliveries,
                notification_error_count=self._error_count,
                last_notification_error=self._last_error)

    def stop(self, timeout: float = 5.0) -> bool:
        if type(timeout) not in {int, float} or timeout < 0 or not float(timeout) < float("inf"):
            raise ValueError("timeout must be a finite non-negative number")
        with self._lock:
            if self._thread is threading.current_thread():
                raise RuntimeError("notification callback cannot join its own host")
        deadline = time.monotonic() + timeout
        self._stop_event.set()
        self._wake_event.set()
        error = None
        try:
            stopped = self.runtime_host.stop(timeout=max(0.0, deadline - time.monotonic()))
        except BaseException as exc:
            error = exc
            stopped = False
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(max(0.0, deadline - time.monotonic()))
        if error is not None:
            raise error
        if not stopped or (thread is not None and thread.is_alive()):
            raise TimeoutError("OrchestratorHost did not stop before the timeout")
        return True

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, traceback):
        self.stop()


__all__ = ["OrchestratorHost", "OrchestratorHostHealth"]
