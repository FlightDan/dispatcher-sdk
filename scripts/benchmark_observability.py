"""Fixed, offline installed-SDK observation cost experiment; no acceptance gate.

Run with --historical-python, --current-python and --output. Each arm uses public
Dispatcher with default automatic observations, process isolation and FULL
durability. SQL traces count attempts, not fsyncs or successful physical writes.
"""
from __future__ import annotations

import argparse
import atexit
from collections import Counter
from dataclasses import dataclass
import importlib.metadata
import json
import math
import mmap
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import struct
import subprocess
import sys
import threading
import time
import traceback


ARMS = ("historical_dev0", "current_automatic", "current_reports")
PAYLOAD = {"steps": 4, "sleep_seconds": .025, "iterations": 10000, "value": 7}
TRIALS, TASKS, WORK_TIMEOUT, WAIT_TIMEOUT, ARM_TIMEOUT = 3, 4, 30, 30, 180
ORIGINAL_CONNECT = sqlite3.connect
SQL_TOKENS = ("connections", "SELECT", "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE",
              "ALTER", "DROP", "BEGIN", "COMMIT", "ROLLBACK", "PRAGMA", "OTHER", "EMPTY")
COUNTER_SLOTS, SLOT_BYTES, METADATA_BYTES = 33, 4096, 2048


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing-" + str(os.getpid()))
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def raw_error(error):
    return {"type": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc(),
            "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
            "sqlite_errorname": getattr(error, "sqlite_errorname", None)}


class SQLCounters:
    """Bounded aggregate counters; never retains a connection or raw SQL."""

    def __init__(self, root):
        self.root = Path(root)
        self.pid = os.getpid()
        self.lock = threading.RLock()
        self.databases = {}
        self.factories = Counter()
        self.trace_errors = 0
        self.open_mapping()
        self.register_exit()

    def open_mapping(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (str(self.pid) + ".counters")
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.ftruncate(descriptor, (COUNTER_SLOTS + 1) * SLOT_BYTES)
            self.mapping = mmap.mmap(descriptor, (COUNTER_SLOTS + 1) * SLOT_BYTES)
        finally:
            os.close(descriptor)
        header = json.dumps({"pid": self.pid, "interpreter": sys.executable,
                             "format": "bounded-sql-attempt-counters-v1"}).encode()
        self.mapping[:len(header)] = header
        self.slots = {}
        self.slot_types = {}

    def increment(self, database, token):
        slot = self.slots[database]
        offset = (slot + 1) * SLOT_BYTES + METADATA_BYTES + SQL_TOKENS.index(token) * 8
        value = struct.unpack_from("<Q", self.mapping, offset)[0]
        struct.pack_into("<Q", self.mapping, offset, value + 1)

    def register_exit(self):
        atexit.register(self.save)
        # multiprocessing workers may bypass ordinary atexit with os._exit.
        from multiprocessing.util import Finalize
        self.finalizer = Finalize(None, self.save, exitpriority=-100)

    def ensure_pid(self):
        if self.pid != os.getpid():
            self.mapping.close()
            self.pid = os.getpid()
            self.lock = threading.RLock()
            self.databases = {}
            self.factories = Counter()
            self.trace_errors = 0
            self.open_mapping()
            self.register_exit()

    def connect(self, *args, **kwargs):
        # The caller's arguments, factory, connection and close ownership survive.
        connection = ORIGINAL_CONNECT(*args, **kwargs)
        self.ensure_pid()
        database = str(args[0] if args else kwargs.get("database", "unknown"))
        with self.lock:
            if database not in self.databases and len(self.databases) >= 32:
                database = "other_databases"
            counter = self.databases.setdefault(database, Counter())
            if database not in self.slots:
                self.slots[database] = len(self.slots)
                self.slot_types[database] = set()
            counter["connections"] += 1
            self.increment(database, "connections")
            factory = type(connection).__module__ + "." + type(connection).__name__
            self.factories[factory] += 1
            self.slot_types[database].add(factory)
            metadata = json.dumps({"database": database, "connection_types": sorted(self.slot_types[database])}).encode()
            if len(metadata) >= METADATA_BYTES:
                raise RuntimeError("SQL counter metadata bound exceeded")
            offset = (self.slots[database] + 1) * SLOT_BYTES
            self.mapping[offset:offset + METADATA_BYTES] = metadata.ljust(METADATA_BYTES, b"\0")

        def trace(statement):
            try:
                token = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "EMPTY"
                if token not in {"SELECT", "INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE",
                                 "ALTER", "DROP", "BEGIN", "COMMIT", "ROLLBACK", "PRAGMA"}:
                    token = "OTHER"
                with self.lock:
                    counter[token] += 1
                    self.increment(database, token)
            except Exception:
                with self.lock:
                    self.trace_errors += 1
                    struct.pack_into("<Q", self.mapping, METADATA_BYTES, self.trace_errors)

        connection.set_trace_callback(trace)
        return connection

    def save(self):
        self.ensure_pid()
        with self.lock:
            value = {"pid": self.pid, "interpreter": sys.executable,
                     "databases": {key: dict(value) for key, value in self.databases.items()},
                     "connection_types": dict(self.factories), "trace_errors": self.trace_errors}
        save(self.root / (str(self.pid) + ".json"), value)


def read_sql_counters(root):
    records = []
    try:
        paths = sorted(root.glob("*.counters"))
    except Exception as error:
        return [{"path": str(root), "pid": None, "databases": {}, "trace_errors": 0,
                 "complete": False, "read_error": raw_error(error)}]
    for path in paths:
        record = {"path": str(path), "pid": None, "databases": {}, "trace_errors": 0, "complete": False}
        try:
            data = path.read_bytes()
            header = json.loads(data[:METADATA_BYTES].split(b"\0", 1)[0])
            record["parsed_header"] = header
            if not isinstance(header, dict):
                raise ValueError("SQL counter header must be an object")
            if type(header.get("pid")) is not int or header["pid"] <= 0:
                raise ValueError("SQL counter header PID must be a positive integer")
            if type(header.get("interpreter")) is not str or not header["interpreter"]:
                raise ValueError("SQL counter header interpreter must be a nonempty string")
            if header.get("format") != "bounded-sql-attempt-counters-v1":
                raise ValueError("SQL counter header format is unsupported")
            record["pid"] = header["pid"]
            record["interpreter"] = header["interpreter"]
            record["format"] = header["format"]
            record["trace_errors"] = struct.unpack_from("<Q", data, METADATA_BYTES)[0]
            if len(data) != (COUNTER_SLOTS + 1) * SLOT_BYTES:
                raise ValueError("SQL counter file is incomplete: " + str(len(data)) + " bytes")
            for slot in range(COUNTER_SLOTS):
                offset = (slot + 1) * SLOT_BYTES
                metadata = data[offset:offset + METADATA_BYTES].split(b"\0", 1)[0]
                if not metadata:
                    continue
                entry = json.loads(metadata)
                counts = {token: struct.unpack_from("<Q", data, offset + METADATA_BYTES + index * 8)[0]
                          for index, token in enumerate(SQL_TOKENS)}
                record["databases"][entry["database"]] = counts
                record.setdefault("connection_types", {})[entry["database"]] = entry["connection_types"]
            record["complete"] = True
        except Exception as error:
            record["read_error"] = raw_error(error)
        records.append(record)
    return records


COUNTERS = None
if os.environ.get("SDK_OBSERVABILITY_BENCHMARK_SQL_COUNTER_DIR"):
    COUNTERS = SQLCounters(os.environ["SDK_OBSERVABILITY_BENCHMARK_SQL_COUNTER_DIR"])
    sqlite3.connect = COUNTERS.connect


@dataclass(frozen=True)
class BenchmarkHandler:
    reports: bool
    __execution_kernel_revision__ = "observability-overhead-v1"

    def __call__(self, payload, context):
        started = time.monotonic()
        reports, errors = [], []
        total = 0
        for step in range(payload["steps"]):
            total += sum((value * payload["value"]) % 97 for value in range(payload["iterations"]))
            time.sleep(payload["sleep_seconds"])
            if self.reports:
                # Same business computation; these are extra public reporting calls.
                for name, call in (
                    ("bytes", lambda: context.activity.report_bytes("stdout", b"benchmark activity chunk\n")),
                    ("heartbeat", context.activity.heartbeat),
                    ("tool_request", lambda: context.activity.tool("request")),
                    ("tool_response", lambda: context.activity.tool("response")),
                    ("model_request", lambda: context.activity.model("request")),
                    ("model_text", lambda: context.activity.model("text")),
                    ("progress", lambda: context.activity.progress("benchmark-step-" + str(step))),
                ):
                    try:
                        reports.append({"step": step, "method": name, "receipt": call()})
                    except Exception as error:
                        errors.append({"step": step, "method": name, "error": raw_error(error)})
                        raise
        return {"business_value": total, "handler_seconds": time.monotonic() - started,
                "pid": os.getpid(), "execution_id": context.command.execution_id,
                "interpreter": sys.executable, "sdk_import": __import__("dispatcher_sdk").__file__,
                "reports": reports, "report_errors": errors}


def storage_snapshot(root):
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not (path.name.endswith((".db", ".sqlite3", "-wal", "-shm"))):
            continue
        record = {"path": str(path), "bytes": path.stat().st_size}
        if path.name.endswith((".db", ".sqlite3")):
            connection = None
            try:
                connection = ORIGINAL_CONNECT(path.as_uri() + "?mode=ro", uri=True, timeout=0)
                deadline = time.monotonic() + 1
                connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
                tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
                if len(tables) > 128:
                    raise RuntimeError("diagnostic table bound exceeded")
                record["table_rows"] = {name: connection.execute(
                    'SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                    for (name,) in tables}
            except Exception as error:
                record["error"] = raw_error(error)
            finally:
                if connection is not None:
                    connection.close()
        records.append(record)
    return records


def run_arm(args):
    import dispatcher_sdk
    from dispatcher_sdk import Dispatcher
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    callbacks = []
    condition = threading.Condition()

    def on_result(notification):
        with condition:
            callbacks.append({"monotonic": time.monotonic(), "notification": notification})
            condition.notify_all()

    evidence = {"arm": args.arm, "trial": args.trial, "root": str(root),
                "command": [sys.executable, *sys.argv], "interpreter": sys.executable,
                "python": sys.version, "platform": platform.platform(),
                "sdk_import": dispatcher_sdk.__file__,
                "sdk_version": importlib.metadata.version("dispatcher-sdk"),
                "sqlite_version": sqlite3.sqlite_version, "payload": PAYLOAD,
                "tasks": [], "errors": [], "callbacks": callbacks}
    app = None
    lifecycle_started = time.monotonic()
    try:
        app = Dispatcher(root / "application.sqlite3", {"benchmark": BenchmarkHandler(args.arm == "current_reports")},
                         on_result=on_result, isolation_mode="process", worker_count=1, durability="full")
        evidence["constructor_seconds"] = time.monotonic() - lifecycle_started
        batch_started = time.monotonic()
        app.start()
        handles = []
        for index in range(TASKS):
            request_id = f"benchmark-{args.arm}-{args.trial}-{index}"
            task_record = {"request_id": request_id, "submitted_at_monotonic": time.monotonic()}
            evidence["tasks"].append(task_record)
            task = app.submit("benchmark", dict(PAYLOAD), request_id=request_id, timeout_seconds=WORK_TIMEOUT)
            handles.append((task, task_record))
        for task, record in handles:
            try:
                record["result"] = task.wait(timeout=WAIT_TIMEOUT)
                record["wait_return_at_monotonic"] = time.monotonic()
                record["wait_latency_seconds"] = record["wait_return_at_monotonic"] - record["submitted_at_monotonic"]
            except Exception as error:
                record["error"] = raw_error(error)
        evidence["batch_seconds"] = time.monotonic() - batch_started
        callback_deadline = time.monotonic() + WAIT_TIMEOUT
        with condition:
            while len(callbacks) < TASKS and time.monotonic() < callback_deadline:
                condition.wait(max(0, callback_deadline - time.monotonic()))
        evidence["callback_delivery_complete"] = len(callbacks) == TASKS
        for task, record in handles:
            try:
                record["snapshot"] = task.snapshot
                if args.arm != "historical_dev0":
                    record["observation"] = task.observe()
            except Exception as error:
                record["diagnostic_error"] = raw_error(error)
        for record in evidence["tasks"]:
            delivery = next((item for item in callbacks if item["notification"].get("target", {}).get("request_id")
                             == record["request_id"]), None)
            if delivery is not None:
                record["callback_latency_seconds"] = delivery["monotonic"] - record["submitted_at_monotonic"]
    except Exception as error:
        evidence["errors"].append(raw_error(error))
    finally:
        if app is not None:
            closed_at = time.monotonic()
            try:
                app.close()
                evidence["closed"] = True
            except Exception as error:
                evidence["errors"].append({"phase": "close", **raw_error(error)})
                evidence["closed"] = False
            evidence["close_seconds"] = time.monotonic() - closed_at
        evidence["lifecycle_seconds"] = time.monotonic() - lifecycle_started
        evidence["post_close_storage"] = storage_snapshot(root)
        if COUNTERS is not None:
            COUNTERS.save()
        save(root / "arm.json", evidence)
    print(json.dumps({"arm": args.arm, "trial": args.trial, "batch_seconds": evidence.get("batch_seconds"),
                      "closed": evidence.get("closed"), "errors": evidence["errors"]}), flush=True)


def distribution(values):
    ordered = sorted(values)
    return {"samples": len(ordered), "median": statistics.median(ordered) if ordered else None,
            "p95_nearest_rank": ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None}


def summarize(runs):
    summaries = {}
    for arm in ARMS:
        samples = [run for run in runs if run["arm"] == arm]
        tasks = [task for run in samples for task in run.get("tasks", [])]
        succeeded = [task for task in tasks if task.get("result", {}).get("status") == "succeeded"]
        durations = [run["batch_seconds"] for run in samples if "batch_seconds" in run]
        sql = Counter()
        for run in samples:
            for process in run.get("sql_counters", []):
                for counts in process["databases"].values():
                    sql.update(counts)
        summaries[arm] = {"submitted": len(tasks), "succeeded": len(succeeded),
            "throughput_tasks_per_second": len(succeeded) / sum(durations) if durations else None,
            "batch_seconds": distribution(durations),
            "task_wait_latency_seconds": distribution([task["wait_latency_seconds"] for task in tasks if "wait_latency_seconds" in task]),
            "task_callback_latency_seconds": distribution([task["callback_latency_seconds"] for task in tasks if "callback_latency_seconds" in task]),
            "handler_seconds": distribution([task["result"]["value"]["handler_seconds"] for task in succeeded]),
            "sql_statement_attempts": dict(sql),
            "mutation_statement_attempts": sum(sql[key] for key in ("INSERT", "UPDATE", "DELETE", "REPLACE")),
            "post_close_database_bytes": sum(item["bytes"] for run in samples for item in run.get("post_close_storage", [])
                                             if item["path"].endswith((".db", ".sqlite3"))),
            "raw_errors": [error for run in samples for error in run.get("errors", [])]}
        summaries[arm]["sql_trace_complete"] = len(samples) == TRIALS and all(
            run.get("sql_trace_complete") is True for run in samples)
        summaries[arm]["sql_counter_read_errors"] = [error for run in samples
                                                    for error in run.get("sql_counter_read_errors", [])]
        observations = [task["observation"] for task in tasks if "observation" in task]
        final_receipts = [note["evidence"] for observation in observations
                          for note in observation.get("diagnostics", {}).get("notes", [])
                          if note.get("phase") == "driver_close"]
        summaries[arm]["observation"] = {"responses": len(observations),
            "complete": sum(item.get("complete") is True for item in observations),
            "collection_gaps": sum(item.get("collection_gaps", 0) for item in observations),
            "driver_final_flush_receipts": len(final_receipts),
            "driver_final_flush_persisted": sum(item.get("receipt", {}).get("final_flush_persisted") is True for item in final_receipts),
            "driver_dropped_events": sum(item.get("dropped_events", 0) for item in final_receipts)}
        summaries[arm]["public_report_receipt_counts"] = dict(Counter(
            item["method"] + ":" + item["receipt"].get("state", "missing")
            for task in succeeded for item in task["result"]["value"]["reports"]))
    return summaries


def driver(args):
    output = Path(args.output).resolve()
    root = output.with_suffix("")
    root.mkdir(parents=True, exist_ok=True)
    plan = [(trial, ARMS[(trial + offset) % len(ARMS)]) for trial in range(TRIALS) for offset in range(len(ARMS))]
    evidence = {"plan": plan, "trials": TRIALS, "tasks_per_arm_trial": TASKS, "payload": PAYLOAD,
                "work_timeout_seconds": WORK_TIMEOUT, "wait_timeout_seconds": WAIT_TIMEOUT,
                "arm_process_timeout_seconds": ARM_TIMEOUT, "worker_count": 1, "isolation": "process", "durability": "full",
                "limitations": ["Historical comparison includes other SDK changes; only current reporting increment is isolated.",
                    "SQL traces count attempted statements/COMMIT, not successful fsyncs or physical page writes.",
                    "A traced statement may repeat for SQLite triggers; counts are callback observations, not logical write operations.",
                    "Three fresh-store trials and twelve tasks per arm; p95 nearest rank is the maximum of twelve samples.",
                    "Local Linux Python 3.10 measurement with tracing enabled for every arm; no native Windows acceptance.",
                    "Task.wait latency includes sequential wait observation; raw callback timestamps also retained.",
                    "No observation options are supplied; current automatic observation remains enabled."], "runs": []}
    save(output, evidence)
    for trial, arm in plan:
        trial_root = root / f"trial-{trial}-{arm}"
        trial_root.mkdir()
        python = args.historical_python if arm == "historical_dev0" else args.current_python
        command = [str(Path(python).absolute()), str(Path(__file__).resolve()), "--arm", arm,
                   "--trial", str(trial), "--root", str(trial_root)]
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["SDK_OBSERVABILITY_BENCHMARK_SQL_COUNTER_DIR"] = str(trial_root / "sql-counters")
        print(json.dumps({"starting": arm, "trial": trial, "command": command}), flush=True)
        try:
            completed = subprocess.run(command, cwd=trial_root, env=env, capture_output=True, text=True, timeout=ARM_TIMEOUT)
            (trial_root / "stdout.log").write_text(completed.stdout, encoding="utf-8")
            (trial_root / "stderr.log").write_text(completed.stderr, encoding="utf-8")
            run = json.loads((trial_root / "arm.json").read_text()) if (trial_root / "arm.json").exists() else {
                "arm": arm, "trial": trial, "errors": [{"message": "arm did not produce evidence"}]}
            run.update(command=command, returncode=completed.returncode,
                       stdout=completed.stdout, stderr=completed.stderr)
        except Exception as error:
            run = {"arm": arm, "trial": trial, "command": command, "errors": [raw_error(error)]}
        run["sql_counters"] = read_sql_counters(trial_root / "sql-counters")
        run["sql_counter_read_errors"] = [{"path": record["path"], "error": record["read_error"]}
                                          for record in run["sql_counters"] if "read_error" in record]
        worker_pids = sorted({task["result"]["value"]["pid"] for task in run.get("tasks", [])
                              if task.get("result", {}).get("status") == "succeeded"})
        run["handler_pids_without_sql_trace"] = sorted(set(worker_pids) - {
            record["pid"] for record in run["sql_counters"] if record["complete"]})
        run["sql_trace_complete"] = bool(run["sql_counters"]) and not run["handler_pids_without_sql_trace"] and all(
            record["complete"] and record["trace_errors"] == 0 for record in run["sql_counters"])
        evidence["runs"].append(run)
        save(output, evidence)
        print(json.dumps({"finished": arm, "trial": trial, "batch_seconds": run.get("batch_seconds"),
                          "errors": run.get("errors"), "missing_worker_traces": run["handler_pids_without_sql_trace"]}), flush=True)
    evidence["summary"] = summarize(evidence["runs"])
    save(output, evidence)
    print(json.dumps(evidence["summary"], indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-python")
    parser.add_argument("--current-python")
    parser.add_argument("--output", default="/tmp/sdk-observability-overhead-12771d9.json")
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--trial", type=int)
    parser.add_argument("--root")
    args = parser.parse_args()
    if args.arm:
        run_arm(args)
    elif args.historical_python and args.current_python:
        driver(args)
    else:
        parser.error("driver requires --historical-python and --current-python")
