#!/usr/bin/env python3
"""Measure real multiprocess SQLiteKernel contention and capacity failure.

Run from the checkout, for example::

    PYTHONPATH=src python3 scripts/benchmark_sqlite_contention.py \
        --workers 2 --items-per-worker 5 --capacity-limit-exercise

The latency values are end-to-end SDK operation durations under contention.
They are not direct SQLite lock-wait measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import queue
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from typing import Any, Callable

from dispatcher_sdk.execution_kernel import (
    ExecutionCommandV2,
    ExecutionNotFoundError,
    ExecutionResultV2,
    RetryPolicy,
    SQLiteKernel,
)
from dispatcher_sdk.execution_kernel import _sqlite_execution, _sqlite_schema


REGISTRY_REVISION = "sqlite-contention-benchmark-v1"


def _command(execution_id: str, payload_bytes: int) -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=f"key-{execution_id}",
        registry_revision=REGISTRY_REVISION,
        correlation_id="sqlite-contention-benchmark",
        causation_id=None,
        handler_id="benchmark",
        handler_contract_version=1,
        retry_policy=RetryPolicy(),
        timeout_seconds=60,
        payload={"data": "x" * payload_bytes},
    )


def _is_busy(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message


def _call(
    observations: list[dict[str, Any]],
    name: str,
    function: Callable[[], Any],
    *,
    busy_retries: int = 5,
) -> Any:
    retry = 0
    while True:
        started = time.perf_counter()
        try:
            value = function()
        except sqlite3.OperationalError as error:
            elapsed = (time.perf_counter() - started) * 1000.0
            if not _is_busy(error):
                observations.append(
                    {"operation": name, "duration_ms": elapsed, "outcome": "error"}
                )
                raise
            observations.append(
                {"operation": name, "duration_ms": elapsed, "outcome": "busy"}
            )
            retry += 1
            if retry > busy_retries:
                raise
            time.sleep(min(0.001 * (2**retry), 0.05))
            continue
        observations.append(
            {
                "operation": name,
                "duration_ms": (time.perf_counter() - started) * 1000.0,
                "outcome": "empty" if value is None else "ok",
            }
        )
        return value


def _result(kernel: SQLiteKernel, lease: Any) -> ExecutionResultV2:
    snapshot = kernel.get(lease.execution_id)
    return ExecutionResultV2(
        result_id=f"result-{lease.execution_id}",
        execution_id=lease.execution_id,
        status="succeeded",
        attempt=lease.attempt,
        fence=lease.fence,
        effect_ids=[],
        started_at=snapshot.started_at,
        completed_at=max(snapshot.started_at, kernel.current_time()),
        correlation_id=snapshot.command.correlation_id,
        causation_id=snapshot.command.causation_id,
        value={"worker": lease.owner},
        error=None,
    )


def _worker(
    database: str,
    worker_number: int,
    items: int,
    payload_bytes: int,
    durability: str,
    start_barrier: Any,
    submitted_barrier: Any,
    completed_barrier: Any,
    output: Any,
) -> None:
    observations: list[dict[str, Any]] = []
    counts = {"submitted": 0, "completed": 0, "outbox_acked": 0}
    kernel: SQLiteKernel | None = None
    try:
        kernel = SQLiteKernel(database, durability=durability)
        start_barrier.wait(timeout=120)
        for number in range(items):
            execution_id = f"worker-{worker_number:03d}-item-{number:06d}"
            _call(
                observations,
                "submit",
                lambda identity=execution_id: kernel.submit(
                    _command(identity, payload_bytes)
                ),
            )
            counts["submitted"] += 1
        submitted_barrier.wait(timeout=120)

        while True:
            lease = _call(
                observations,
                "claim",
                lambda: kernel.claim(
                    f"worker-{worker_number}",
                    registry_revision=REGISTRY_REVISION,
                ),
            )
            if lease is None:
                break
            lease = _call(observations, "start", lambda: kernel.start(lease))
            result = _result(kernel, lease)
            _call(
                observations,
                "complete",
                lambda: kernel.complete(lease, result),
            )
            counts["completed"] += 1
        completed_barrier.wait(timeout=120)

        while True:
            delivery = _call(
                observations,
                "outbox_claim",
                lambda: kernel.claim_outbox(f"bridge-{worker_number}"),
            )
            if delivery is None:
                break
            _call(
                observations,
                "outbox_ack",
                lambda: kernel.ack_outbox(delivery),
            )
            counts["outbox_acked"] += 1
        output.put(
            {
                "worker": worker_number,
                "counts": counts,
                "observations": observations,
                "error": None,
            }
        )
    except BaseException as error:
        for barrier in (start_barrier, submitted_barrier, completed_barrier):
            try:
                barrier.abort()
            except BaseException:
                pass
        output.put(
            {
                "worker": worker_number,
                "counts": counts,
                "observations": observations,
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if kernel is not None:
            kernel.close()


def _nearest_rank(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, (percentile * len(ordered) + 99) // 100 - 1)
    return ordered[index]


def _operation_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in sorted({row["operation"] for row in observations}):
        rows = [row for row in observations if row["operation"] == name]
        durations = [float(row["duration_ms"]) for row in rows]
        result[name] = {
            "calls": len(rows),
            "successful_calls": sum(row["outcome"] == "ok" for row in rows),
            "empty_polls": sum(row["outcome"] == "empty" for row in rows),
            "busy_errors": sum(row["outcome"] == "busy" for row in rows),
            "other_errors": sum(row["outcome"] == "error" for row in rows),
            "p50_ms": _nearest_rank(durations, 50),
            "p95_ms": _nearest_rank(durations, 95),
            "p99_ms": _nearest_rank(durations, 99),
            "max_ms": max(durations) if durations else None,
        }
    return result


def _validate_database(
    database: Path, expected_ids: list[str], durability: str
) -> dict[str, Any]:
    expected = len(expected_ids)
    with SQLiteKernel(database, durability=durability) as kernel:
        public_states: dict[str, str] = {}
        missing_ids: list[str] = []
        for identity in expected_ids:
            try:
                public_states[identity] = kernel.get(identity).state
            except ExecutionNotFoundError:
                missing_ids.append(identity)
        delivered = len(
            kernel.result_outbox(states={"delivered"}, limit=max(1, expected + 1))
        )
    uri = f"{database.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        by_state = {
            str(state): int(count)
            for state, count in connection.execute(
                "SELECT state,COUNT(*) FROM kernel_executions GROUP BY state"
            )
        }
        duplicate_execution_ids = int(
            connection.execute(
                "SELECT COUNT(*)-COUNT(DISTINCT execution_id) FROM kernel_executions"
            ).fetchone()[0]
        )
        outbox_by_state = {
            str(state): int(count)
            for state, count in connection.execute(
                "SELECT state,COUNT(*) FROM kernel_result_outbox GROUP BY state"
            )
        }
        succeeded = by_state.get("succeeded", 0)
    finally:
        connection.close()
    checks = {
        "execution_count": sum(by_state.values()),
        "succeeded": succeeded,
        "outbox_delivered": delivered,
        "duplicate_execution_ids": duplicate_execution_ids,
        "missing_execution_ids": missing_ids,
        "public_get_succeeded": sum(
            state == "succeeded" for state in public_states.values()
        ),
        "execution_states": by_state,
        "outbox_states": outbox_by_state,
    }
    checks["ok"] = (
        checks["execution_count"] == expected
        and succeeded == expected
        and delivered == expected
        and duplicate_execution_ids == 0
        and not missing_ids
        and checks["public_get_succeeded"] == expected
    )
    return checks


def run_benchmark(
    database: str | Path,
    *,
    workers: int = 4,
    items_per_worker: int = 25,
    payload_bytes: int = 256,
    durability: str = "full",
    start_method: str = "spawn",
    process_timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """Run a fresh-database contention benchmark and return JSON-ready data."""

    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be an integer >= 1")
    if type(items_per_worker) is not int or items_per_worker < 1:
        raise ValueError("items_per_worker must be a positive integer")
    if type(payload_bytes) is not int or payload_bytes < 0:
        raise ValueError("payload_bytes must be a nonnegative integer")
    if (
        type(process_timeout_seconds) not in (int, float)
        or float(process_timeout_seconds) <= 0
    ):
        raise ValueError("process_timeout_seconds must be a positive number")
    if durability not in ("full", "normal"):
        raise ValueError("durability must be 'full' or 'normal'")
    if start_method not in multiprocessing.get_all_start_methods():
        raise ValueError(f"unsupported multiprocessing start method: {start_method}")
    path = Path(database).resolve()
    if path.exists():
        raise FileExistsError(f"benchmark requires a fresh database path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with SQLiteKernel(path, durability=durability):
        pass

    context = multiprocessing.get_context(start_method)
    start_barrier = context.Barrier(workers + 1)
    submitted_barrier = context.Barrier(workers)
    completed_barrier = context.Barrier(workers)
    output = context.Queue()
    processes = [
        context.Process(
            target=_worker,
            args=(
                str(path),
                worker,
                items_per_worker,
                payload_bytes,
                durability,
                start_barrier,
                submitted_barrier,
                completed_barrier,
                output,
            ),
        )
        for worker in range(workers)
    ]
    for process in processes:
        process.start()
    started = time.perf_counter()
    barrier_error = None
    try:
        start_barrier.wait(timeout=process_timeout_seconds)
    except BaseException as error:
        barrier_error = f"{type(error).__name__}: {error}"
    rows: list[dict[str, Any]] = []
    deadline = time.monotonic() + process_timeout_seconds
    while len(rows) < workers:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            rows.append(output.get(timeout=min(remaining, 1.0)))
        except queue.Empty:
            if all(not process.is_alive() for process in processes):
                break
    for process in processes:
        process.join(timeout=max(0.0, deadline - time.monotonic()))
    elapsed = time.perf_counter() - started
    hung = [process.pid for process in processes if process.is_alive()]
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        process.close()
    output.close()
    output.join_thread()

    errors = [row for row in rows if row.get("error")]
    if barrier_error is not None:
        errors.append({"error": f"start barrier failed: {barrier_error}"})
    if len(rows) != workers:
        errors.append({"error": f"received {len(rows)} of {workers} worker reports"})
    if hung:
        errors.append({"error": f"workers exceeded timeout: {hung}"})
    observations = [
        observation for row in rows for observation in row.get("observations", [])
    ]
    expected = workers * items_per_worker
    expected_ids = [
        f"worker-{worker:03d}-item-{item:06d}"
        for worker in range(workers)
        for item in range(items_per_worker)
    ]
    correctness = _validate_database(path, expected_ids, durability)
    worker_counts = {
        key: sum(int(row.get("counts", {}).get(key, 0)) for row in rows)
        for key in ("submitted", "completed", "outbox_acked")
    }
    correctness["worker_counts"] = worker_counts
    correctness["ok"] = (
        correctness["ok"]
        and not errors
        and worker_counts == {
            "submitted": expected,
            "completed": expected,
            "outbox_acked": expected,
        }
    )
    return {
        "format_version": 1,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "cpu_count": os.cpu_count(),
            "multiprocessing_start_method": start_method,
            "durability": durability,
            "workers": workers,
            "items_per_worker": items_per_worker,
            "payload_bytes": payload_bytes,
            "database": str(path),
            "implementation_sha256": hashlib.sha256(
                Path(_sqlite_execution.__file__).read_bytes()
            ).hexdigest(),
        },
        "elapsed_seconds": elapsed,
        "throughput": {
            "executions_per_second": expected / elapsed,
            "successful_sdk_mutations_per_second": (expected * 6) / elapsed,
        },
        "operation_latency_under_contention": _operation_summary(observations),
        "busy_errors": sum(row["outcome"] == "busy" for row in observations),
        "latency_is_direct_lock_wait": False,
        "correctness": correctness,
        "worker_errors": errors,
    }


def run_capacity_limit_exercise(
    database: str | Path, *, durability: str = "full", payload_bytes: int = 1_000_000
) -> dict[str, Any]:
    """Force SQLITE_FULL with max_page_count, then prove a later commit works.

    This deterministic exercise checks transaction rejection and reopening after
    capacity returns.  It does not simulate a filesystem, device, or power loss.
    """

    if durability not in ("full", "normal"):
        raise ValueError("durability must be 'full' or 'normal'")
    if type(payload_bytes) is not int or payload_bytes < 1:
        raise ValueError("payload_bytes must be a positive integer")
    path = Path(database).resolve()
    if path.exists():
        raise FileExistsError(f"capacity exercise requires a fresh path: {path}")
    with SQLiteKernel(path, durability=durability) as kernel:
        # max_page_count is connection-scoped.  Temporarily remove and restore
        # the Kernel authorizer around this benchmark-only PRAGMA; all workload
        # writes still go through the real public SDK methods.
        kernel._connection.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
        try:
            current_pages = int(
                kernel._connection.execute("PRAGMA page_count").fetchone()[0]
            )
            applied_limit = int(
                kernel._connection.execute(
                    f"PRAGMA max_page_count={current_pages}"
                ).fetchone()[0]
            )
        finally:
            kernel._authorizer = _sqlite_schema.install_authorizer(kernel._connection)
        rejected = False
        error_text = None
        try:
            kernel.submit(_command("capacity-rejected", payload_bytes))
        except sqlite3.OperationalError as error:
            rejected = "full" in str(error).lower()
            error_text = f"{type(error).__name__}: {error}"
        absent_after_rejection = True
        try:
            kernel.get("capacity-rejected")
        except ExecutionNotFoundError:
            pass
        else:
            absent_after_rejection = False
        kernel._connection.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
        try:
            kernel._connection.execute(
                f"PRAGMA max_page_count={max(applied_limit + 4096, 8192)}"
            )
        finally:
            kernel._authorizer = _sqlite_schema.install_authorizer(kernel._connection)
        recovered = kernel.submit(_command("capacity-recovered", 16))
    ok = rejected and absent_after_rejection and recovered.state == "queued"
    return {
        "mechanism": "SQLite max_page_count",
        "simulates_real_disk_full": False,
        "simulates_power_loss": False,
        "initial_page_limit": applied_limit,
        "transaction_rejected": rejected,
        "rejected_error": error_text,
        "rejected_execution_absent": absent_after_rejection,
        "commit_after_capacity_returned": recovered.state == "queued",
        "ok": ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--items-per-worker", type=int, default=25)
    parser.add_argument("--payload-bytes", type=int, default=256)
    parser.add_argument("--durability", choices=("full", "normal"), default="full")
    parser.add_argument(
        "--start-method",
        choices=multiprocessing.get_all_start_methods(),
        default="spawn",
    )
    parser.add_argument("--capacity-limit-exercise", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--keep-database", action="store_true")
    args = parser.parse_args()

    temporary = None
    if args.database is None:
        temporary = Path(tempfile.mkdtemp(prefix="dispatcher-sqlite-contention-"))
        database = temporary / "contention.sqlite3"
    else:
        database = args.database
    try:
        result = run_benchmark(
            database,
            workers=args.workers,
            items_per_worker=args.items_per_worker,
            payload_bytes=args.payload_bytes,
            durability=args.durability,
            start_method=args.start_method,
        )
        if args.capacity_limit_exercise:
            capacity_path = database.with_name(database.stem + "-capacity.sqlite3")
            result["capacity_limit_exercise"] = run_capacity_limit_exercise(
                capacity_path, durability=args.durability
            )
        encoded = json.dumps(result, indent=2, sort_keys=True)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        valid = result["correctness"]["ok"] and result.get("capacity_limit_exercise", {}).get("ok", True)
        return 0 if valid else 1
    finally:
        if temporary is not None and not args.keep_database:
            shutil.rmtree(temporary)


if __name__ == "__main__":
    sys.exit(main())
