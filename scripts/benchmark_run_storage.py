"""Measure retained Run storage with fixed-size, individually committed tasks.

PYTHONPATH=src python3 scripts/benchmark_run_storage.py --output /tmp/run-storage.json
The default fixture uses 100/200/400/800 tasks and WAL/FULL. Databases are
temporary and removed unless --keep-db is supplied. No handlers are executed.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time

from dispatcher_sdk import durability as durability_module
from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel import _sqlite_base, _sqlite_execution
from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator import engine, runs, store, transport
from dispatcher_sdk.orchestrator.contracts import canonical


class _ObservedKernel(SQLiteKernel):
    get_calls = 0

    def get(self, execution_id):
        self.get_calls += 1
        return super().get(execution_id)


class _ObservedOrchestrator(Orchestrator):
    statements = None

    def _connect(self):
        connection = super()._connect()
        if self.statements is not None:
            connection.set_trace_callback(self.statements.append)
        return connection


def _source_hashes():
    modules = (durability_module, _sqlite_base, _sqlite_execution, engine, runs, store, transport)
    return {module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in modules}


def _command(identity, payload_bytes):
    return ExecutionCommandV2(
        execution_id=identity, idempotency_key=identity, registry_revision="benchmark-registry",
        correlation_id="run", causation_id=None, handler_id="echo", handler_contract_version=1,
        retry_policy=RetryPolicy(), timeout_seconds=5, payload={"data": "x" * payload_bytes},
    )


def _files(path):
    return {name: candidate.stat().st_size if candidate.exists() else 0
            for name, candidate in (("database", path), ("wal", Path(str(path) + "-wal")),
                                    ("shm", Path(str(path) + "-shm")))}


def _storage(sdk):
    path = Path(sdk.db_path)
    files_before = _files(path)
    with closing(sdk._connect()) as connection:
        checkpoint = tuple(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        if checkpoint[0] != 0:
            raise RuntimeError(f"checkpoint was blocked: {checkpoint}")
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
        free_pages = connection.execute("PRAGMA freelist_count").fetchone()[0]
        tables = {}
        for table, column in (("sdk_commands", "response"), ("sdk_run_items", "value"),
                              ("sdk_run_history", "value"), ("sdk_executions", "command"),
                              ("sdk_events", "payload")):
            rows, byte_count, maximum = connection.execute(
                f"SELECT COUNT(*),COALESCE(SUM(length(CAST({column} AS BLOB))),0),"
                f"COALESCE(MAX(length(CAST({column} AS BLOB))),0) FROM {table}"
            ).fetchone()
            tables[table] = {"rows": rows, "json_column": column, "json_bytes": byte_count,
                             "largest_json_bytes": maximum}
        for table in ("sdk_runs", "sdk_run_revisions", "sdk_run_links", "sdk_outbox", "kernel_executions"):
            tables[table] = {"rows": connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]}
        return {
            "sqlite": {
                "files_before_checkpoint": files_before,
                "files_after_checkpoint": _files(path),
                "checkpoint_result": checkpoint,
                "page_size": page_size,
                "page_count": page_count,
                "allocated_page_bytes": page_count * page_size,
                "freelist_pages": free_pages,
                "used_page_bytes": (page_count - free_pages) * page_size,
                "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
                "synchronous": connection.execute("PRAGMA synchronous").fetchone()[0],
            },
            "tables": tables,
            "selected_json_bytes": sum(value.get("json_bytes", 0) for value in tables.values()),
            "active_executions": connection.execute("SELECT COUNT(*) FROM sdk_executions WHERE active=1").fetchone()[0],
        }


def _trace_counts(statements):
    normalized = [" ".join(statement.split()) for statement in statements]
    return {
        "execution_registration_lookups": sum(value.startswith(
            "SELECT run_id,task_id,attempt,command FROM sdk_executions") for value in normalized),
        "current_run_load_queries": sum(value.startswith(
            "SELECT section,item_key,value FROM sdk_run_items WHERE run_id=") for value in normalized),
        "history_inserts": sum(value.startswith("INSERT INTO sdk_run_history ") for value in normalized),
        "current_item_upserts": sum(value.startswith("INSERT INTO sdk_run_items ") for value in normalized),
        "receipt_inserts": sum(value.startswith("INSERT INTO sdk_commands ") for value in normalized),
        "active_execution_queries": sum(value.startswith(
            "SELECT execution_id FROM sdk_executions WHERE active=1") for value in normalized),
    }


def _timing(values):
    return {"samples": len(values), "median_ms": statistics.median(values),
            "p95_ms": sorted(values)[max(0, (95 * len(values) + 99) // 100 - 1)],
            "total_seconds": sum(values) / 1000}


def _growth(path, sizes, payload_bytes, durability):
    with _ObservedKernel(path, durability=durability) as kernel:
        sdk = _ObservedOrchestrator(path, kernel, durability=durability)
        sdk.create_run("run", command_id="create", definition={"fixture": "run-storage-growth"})
        baseline = _storage(sdk)
        points, block_times = [], []
        first_snapshot, first_request = None, None
        revision = 0
        for number in range(1, sizes[-1] + 1):
            identity = f"task-{number:08d}"
            request = {
                "command_id": f"add-{number:08d}", "expected_revision": revision,
                "operations": [
                    {"kind": "add_task", "task_id": identity,
                     "command": _command(identity, payload_bytes).to_dict()},
                    {"kind": "cancel", "task_id": identity, "reason": "fixture completed"},
                ],
            }
            sdk.statements = [] if number in sizes else None
            started = time.perf_counter()
            snapshot = sdk.apply_operations("run", **request)
            block_times.append((time.perf_counter() - started) * 1000)
            revision = snapshot["revision"]
            if number == 1:
                first_snapshot, first_request = snapshot, request
            if number not in sizes:
                continue
            counts = _trace_counts(sdk.statements)
            sdk.statements = None
            # Replaying the old expected_revision must return the old response,
            # not the current Run, and must not insert another command receipt.
            queried = sdk.get_command_receipt("run", first_request["command_id"])
            replayed = sdk.apply_operations("run", **first_request)
            historical = sdk.get_run_at("run", first_snapshot["revision"])
            if queried != first_snapshot or replayed != first_snapshot or historical != first_snapshot:
                raise AssertionError("the original historical command response changed")
            measurement = _storage(sdk)
            if measurement["tables"]["sdk_commands"]["rows"] != number + 1:
                raise AssertionError("command replay changed receipt cardinality")
            if len(snapshot["tasks"]) != number or measurement["tables"]["sdk_executions"]["rows"] != number:
                raise AssertionError("fixture task/execution cardinality differs")
            measurement.update({
                "tasks": number,
                "full_run_json_bytes": len(canonical(snapshot).encode("utf-8")),
                "last_add_sql": counts,
                "apply_operations_in_last_block": _timing(block_times),
                "original_receipt_verified": True,
                "original_receipt_tasks": len(queried["tasks"]),
                "net_json_bytes_per_task": (measurement["selected_json_bytes"] - baseline["selected_json_bytes"]) / number,
            })
            points.append(measurement)
            block_times = []
            print(f"tasks={number} pages={measurement['sqlite']['allocated_page_bytes']} "
                  f"receipt_json={measurement['tables']['sdk_commands']['json_bytes']}", file=sys.stderr, flush=True)
        densities = [point["net_json_bytes_per_task"] for point in points]
        return {"baseline": baseline, "measurements": points,
                "max_to_min_net_json_bytes_per_task": max(densities) / min(densities)}


def _idle_sync(path, count, durability):
    with _ObservedKernel(path, durability=durability) as kernel:
        sdk = _ObservedOrchestrator(path, kernel, durability=durability)
        sdk.create_run("run", command_id="create")
        operations = []
        for number in range(count):
            identity = f"settled-{number:08d}"
            command = _command(identity, 128)
            kernel.cancel_before_accept(command, reason="idle-sync fixture")
            operations.extend([
                {"kind": "add_task", "task_id": identity, "command": command.to_dict()},
                {"kind": "dispatch", "task_id": identity},
            ])
        sdk.apply_operations("run", command_id="register", expected_revision=0, operations=operations)
        if sdk.flush(limit=count) != count:
            raise AssertionError("fixture dispatches were not fully delivered and projected")
        if any(task["attempts"][-1]["state"] != "cancelled" for task in sdk.get_run("run")["tasks"].values()):
            raise AssertionError("idle fixture still contains nonterminal executions")
        before_gets = kernel.get_calls
        sdk.statements = []
        durations = []
        for _ in range(5):
            started = time.perf_counter()
            if sdk.sync() != 0:
                raise AssertionError("idle sync polled terminal execution history")
            durations.append((time.perf_counter() - started) * 1000)
        counts = _trace_counts(sdk.statements)
        sdk.statements = None
        gets = kernel.get_calls - before_gets
        if gets or counts["current_run_load_queries"]:
            raise AssertionError("idle sync read terminal execution snapshots")
        return {"terminal_executions": count, "sync_calls": len(durations), "kernel_get_calls": gets,
                "sql": counts, "sync_timing": _timing(durations)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 200, 400, 800])
    parser.add_argument("--payload-bytes", type=int, default=128)
    parser.add_argument("--durability", choices=("full", "normal"), default="full")
    parser.add_argument("--idle-sync-tasks", type=int, default=40, help="zero skips the independent idle-sync fixture")
    parser.add_argument("--keep-db", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if min(args.sizes) < 1 or args.payload_bytes < 0 or args.idle_sync_tasks < 0:
        parser.error("sizes must be positive; payload bytes and idle-sync tasks must be nonnegative")
    sizes = sorted(set(args.sizes))
    root = Path(tempfile.mkdtemp(prefix="dispatcher-run-storage-"))
    before_hashes = _source_hashes()
    try:
        report = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {"platform": platform.platform(), "python": platform.python_version(),
                            "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count()},
            "configuration": {"sizes": sizes, "payload_bytes": args.payload_bytes,
                              "durability": args.durability, "segment_count": 1,
                              "temporary_directory": str(root), "databases_retained": args.keep_db},
            "source_sha256": before_hashes,
            "growth": _growth(root / "growth.sqlite3", sizes, args.payload_bytes, args.durability),
        }
        if args.idle_sync_tasks:
            report["idle_sync"] = _idle_sync(root / "idle.sqlite3", args.idle_sync_tasks, args.durability)
        report["source_changed_during_run"] = _source_hashes() != before_hashes
        if report["source_changed_during_run"]:
            raise RuntimeError("source files changed during this benchmark; rerun against a stable checkout")
        encoded = json.dumps(report, indent=2) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded)
        print(encoded, end="")
    finally:
        if not args.keep_db:
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
