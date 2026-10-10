"""Root-process diagnostics for unchanged generated README examples."""
import atexit
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import traceback


def _error(error):
    try:
        message = str(error)
    except BaseException:
        message = "<error message unavailable>"
    try:
        stack = traceback.format_exception(type(error), error, error.__traceback__)
    except BaseException:
        stack = []
    return {"type": type(error).__name__, "message": message, "traceback": stack}


def install(directory):
    """Observe the parent only; never retry, drive, cancel, or change a budget."""
    root = Path(directory)
    owner_pid = os.getpid()
    from dispatcher_sdk.application import Task
    from dispatcher_sdk._inspection import InspectionBudget
    from tests._storage_evidence import StorageEvidence

    report = {"interpreter": sys.executable, "pid": owner_pid,
              "installed_at": time.monotonic(), "temporary_directories": [],
              "diagnostic_errors": [], "waits": []}
    storage = StorageEvidence(root, None)

    def attempt(name, operation, target):
        began = time.monotonic()
        try:
            target[name] = {"value": operation()}
        except BaseException as error:
            target[name] = {"error": _error(error)}
        target[name].update(began=began, returned=time.monotonic())

    attempt("storage_start", lambda: storage.start(include_kernel=True), report)
    original_directory = tempfile.TemporaryDirectory

    class RetainedDirectory(original_directory):
        def __init__(self, *args, **kwargs):
            if os.getpid() == owner_pid:
                kwargs.setdefault("dir", str(root))
            super().__init__(*args, **kwargs)
            if os.getpid() == owner_pid:
                # Retain even when an exception exits the nested README context.
                self._finalizer.detach()
                report["temporary_directories"].append(self.name)

        def cleanup(self):
            if os.getpid() == owner_pid:
                self._finalizer.detach()
            else:
                super().cleanup()

    tempfile.TemporaryDirectory = RetainedDirectory

    def threads():
        frames = sys._current_frames()
        return [{"name": thread.name, "ident": thread.ident, "alive": thread.is_alive(),
                 "stack": traceback.format_stack(frames[thread.ident])
                 if thread.ident in frames else []} for thread in threading.enumerate()]

    def persisted(task):
        # Task.snapshot uses unbounded control locks. Inspect its original
        # persisted rows instead, within one read-only SQLite budget.
        budget = InspectionBudget(.1, None)
        budget.check()
        connection = sqlite3.connect(task.dispatcher.path.as_uri() + "?mode=ro", uri=True,
                                     timeout=budget.sqlite_timeout_seconds)
        connection.row_factory = sqlite3.Row
        try:
            budget.install(connection)
            result = {}
            for table in ("sdk_runs", "sdk_run_items", "sdk_executions", "kernel_executions"):
                result[table] = [dict(row) for row in connection.execute(f"SELECT * FROM {table} LIMIT 50")]
                budget.check()
            return result
        finally:
            connection.close()

    def health(task):
        app = task.dispatcher
        owners = (app, app.host, app.host.runtime_host)
        deadline = time.monotonic() + .1
        acquired = []
        try:
            for owner in owners:
                if not owner._lock.acquire(timeout=max(0, deadline-time.monotonic())):
                    raise TimeoutError("README diagnostic health lock budget elapsed")
                acquired.append(owner)
            return app.health()
        finally:
            for owner in reversed(acquired):
                owner._lock.release()

    def save(filename):
        report["imports"] = {name: module.__file__ for name, module in tuple(sys.modules.items())
                             if name.startswith("dispatcher_sdk") and getattr(module, "__file__", None)}
        attempt("threads", threads, report)

        def sql_events():
            if not storage._lock.acquire(timeout=.1):
                raise TimeoutError("README diagnostic storage lock budget elapsed")
            try:
                # Copy dictionaries, not live connection/runtime objects.
                return {"operations": storage.operations,
                        "events": [dict(event) for event in storage.events]}
            finally:
                storage._lock.release()

        attempt("storage", sql_events, report)
        (root / filename).write_text(json.dumps(report, indent=2, default=repr), encoding="utf-8")

    original_wait = Task.wait

    def wait(task, *, timeout=30):
        call = {"request_id": task.request_id, "timeout_seconds": timeout,
                "began": time.monotonic(), "path": str(task.dispatcher.path)}
        report["waits"].append(call)
        try:
            value = original_wait(task, timeout=timeout)
            call.update(returned=time.monotonic(), result=value)
            return value
        except BaseException as error:
            try:
                call.update(returned=time.monotonic(), error=_error(error))
                # Capture stacks first, before observation or context teardown.
                attempt("threads_before_cleanup", threads, call)
                attempt("observe", lambda: task.observe(timeout=.5), call)
                attempt("events", lambda: task.events(timeout=.1), call)
                attempt("persisted_snapshot", lambda: persisted(task), call)
                attempt("host_health", lambda: health(task), call)
                save("wait-failure-before-cleanup.json")
                print(f"README wait evidence retained at {root}", file=sys.stderr)
            except BaseException as secondary:
                try:
                    report["diagnostic_errors"].append(_error(secondary))
                except BaseException:
                    pass
            raise

    Task.wait = wait

    def finish():
        if os.getpid() != owner_pid:
            return
        try:
            report["finished_at"] = time.monotonic()
            save("readme-evidence.json")
        except BaseException as error:
            try:
                print(f"README evidence capture failed: {type(error).__name__}: {error}", file=sys.stderr)
            except BaseException:
                pass

    atexit.register(finish)
    attempt("startup_save", lambda: save("readme-startup.json"), report)
