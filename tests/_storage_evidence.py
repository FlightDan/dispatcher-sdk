"""Bounded raw SQLite and worker evidence without changing fixture budgets."""
from collections import deque
from copy import deepcopy
from itertools import count
import json
import sqlite3
import sys
import threading
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch


class StorageEvidence:
    def __init__(self, root, test):
        self.root, self.test = root, test
        self.events = deque(maxlen=2048)
        self._lock = threading.Lock()
        self.operations = 0
        self.runtimes = []
        self.patches = []

    def start(self):
        from dispatcher_sdk.execution_kernel import runtime, settlement
        from dispatcher_sdk.observability import journal
        owner, identifiers = self, count(1)

        class Connection(sqlite3.Connection):
            def __init__(self, database, *args, **kwargs):
                with owner._lock:
                    self.evidence_id = next(identifiers)
                self.evidence_path = str(database)
                self._call("connect", lambda: super(Connection, self).__init__(database, *args, **kwargs),
                           timeout=kwargs.get("timeout"))

            def _call(self, operation, call, **facts):
                event = {"connection": self.evidence_id, "path": self.evidence_path,
                         "thread": threading.current_thread().name, "operation": operation,
                         "began": time.monotonic(), **facts}
                with owner._lock:
                    owner.operations += 1
                    owner.events.append(event)
                try:
                    return call()
                except BaseException as error:
                    with owner._lock:
                        event["error"] = {"type": type(error).__name__, "message": str(error),
                            "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                            "sqlite_errorname": getattr(error, "sqlite_errorname", None)}
                    raise
                finally:
                    elapsed = time.monotonic() - event["began"]
                    with owner._lock:
                        event["elapsed"] = elapsed

            def execute(self, sql, *args, **kwargs):
                return self._call("execute", lambda: super(Connection, self).execute(sql, *args, **kwargs), sql=sql)

            def commit(self):
                return self._call("commit", lambda: super(Connection, self).commit())

            def rollback(self):
                return self._call("rollback", lambda: super(Connection, self).rollback())

            def close(self):
                return self._call("close", lambda: super(Connection, self).close())

        def connect(*args, **kwargs):
            kwargs.setdefault("factory", Connection)
            return sqlite3.connect(*args, **kwargs)

        # Only target module references change; the shared sqlite3 module and
        # unrelated/background SDK entrypoints retain their original methods.
        proxy = SimpleNamespace(**{**vars(sqlite3), "connect": connect})
        for module in (journal, settlement):
            current = patch.object(module, "sqlite3", proxy)
            current.start()
            self.patches.append(current)
        original = runtime.InProcessRuntime.__init__

        def initialize(instance, *args, **kwargs):
            original(instance, *args, **kwargs)
            with owner._lock:
                owner.runtimes.append(instance)

        current = patch.object(runtime.InProcessRuntime, "__init__", initialize)
        current.start()
        self.patches.append(current)
        self.imports = {module.__name__: module.__file__ for module in (runtime, journal, settlement)}

    def stop(self):
        for current in reversed(self.patches):
            current.stop()

    def save(self, *, phase="cleanup", checkpoint=None):
        with self._lock:
            operations, events = self.operations, deepcopy(list(self.events))
            runtimes = tuple(self.runtimes)
        frames = sys._current_frames()
        workers = [{"name": thread.name, "alive": thread.is_alive(),
                    "stack": traceback.format_stack(frames[thread.ident]) if thread.ident in frames else []}
                   for thread in threading.enumerate()]
        runtime_facts = []
        for runtime in runtimes:
            entries = runtime._pending_settlements.entries()
            with runtime._thread_lock:
                contexts = tuple(runtime._thread_contexts.values())
            runtime_facts.append({"path": runtime.kernel.db_path, "closed": runtime._closed,
                "active_runs": runtime._active_runs, "settlement_error": runtime._settlement_error,
                "close_error": None if runtime._close_error is None else repr(runtime._close_error),
                "observation_error": runtime._observation_error,
                "cleanup_report": runtime._observation_cleanup_report,
                "contexts": [{"execution_id": context.lease.execution_id,
                    "start_done": context._observation_start_done.is_set(),
                    "closed": context._observation_closed, "activity": type(context.activity).__name__}
                    for context in contexts],
                "original_pending": [{"identity": entry.identity, "payload": entry.payload,
                    "evidence": entry.evidence} for entry in entries]})
        result = getattr(getattr(self.test, "_outcome", None), "result", None)
        errors = [] if result is None else [text for test, text in
            (*getattr(result, "failures", ()), *getattr(result, "errors", ())) if test is self.test]
        report = {"test": self.test.id(), "interpreter": sys.executable, "imports": self.imports,
                  "phase": phase, "checkpoint": checkpoint, "operations": operations,
                  "retained_sql_operations": events, "workers": workers,
                  "runtimes": runtime_facts, "raw_test_errors": errors}
        destination = self.root / ("storage-evidence.json" if phase == "cleanup" else phase + ".json")
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
