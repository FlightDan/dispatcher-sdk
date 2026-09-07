"""Measure real Linux process-tree cleanup without database or spawn overhead.

Run from the checkout: PYTHONPATH=src python3 scripts/benchmark_cleanup.py
Each sample has its own subreaper, worker, and optional detached grandchild.
The measured interval starts after the tree is ready and ends at containment.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import multiprocessing
import os
from pathlib import Path
import platform
import signal
import statistics
import time

from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime


def _sample(topology, sender, legacy):
    subreaper = process_runtime._enable_linux_subreaper()
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    ready_read, ready_write = os.pipe()
    worker = os.fork()
    if worker == 0:
        os.close(ready_read)
        sender.close()
        os.setpgid(0, 0)
        if topology == "double_fork_setsid":
            child = os.fork()
            if child == 0:
                if os.fork() != 0:
                    os._exit(0)
                os.setsid()
                os.write(ready_write, b"ready")
            else:
                os.close(ready_write)
        else:
            os.write(ready_write, b"ready")
        while True:
            signal.pause()
    os.close(ready_write)
    try:
        if os.read(ready_read, 5) != b"ready":
            raise RuntimeError("worker did not become ready")
        kwargs = {}
        if "subreaper" in inspect.signature(process_runtime._contain_tree).parameters:
            kwargs["subreaper"] = subreaper and not legacy
        before_cpu = time.process_time()
        before = time.perf_counter()
        contained = process_runtime._contain_tree(
            os.getpid(), worker, time.monotonic() + 2.0, **kwargs
        )
        elapsed = time.perf_counter() - before
        cpu = time.process_time() - before_cpu
        sender.send({"contained": contained, "wall_ms": elapsed * 1000, "cpu_ms": cpu * 1000})
    finally:
        cleanup_kwargs = {}
        if "subreaper" in inspect.signature(process_runtime._contain_tree).parameters:
            cleanup_kwargs["subreaper"] = subreaper
        process_runtime._contain_tree(os.getpid(), worker, time.monotonic() + 2, **cleanup_kwargs)
        os.close(ready_read)
        sender.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--legacy", action="store_true", help="use the retained 50 ms quiet-window path")
    args = parser.parse_args()
    if platform.system() != "Linux" or args.samples < 1:
        parser.error("requires Linux and a positive sample count")
    context = multiprocessing.get_context("fork")
    results = {}
    for topology in ("worker_only", "double_fork_setsid"):
        rows = []
        for _ in range(args.samples):
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=_sample, args=(topology, sender, args.legacy))
            process.start()
            sender.close()
            try:
                if not receiver.poll(5):
                    raise RuntimeError("cleanup sample did not finish")
                row = receiver.recv()
                process.join(3)
                if process.exitcode != 0 or not row["contained"]:
                    raise RuntimeError(f"cleanup failed: {row}; exit={process.exitcode}")
                rows.append(row)
            finally:
                if process.is_alive():
                    process_runtime._kill_supervisor(process)
                receiver.close()
                process.close()
        results[topology] = {
            "samples": len(rows),
            "median_wall_ms": statistics.median(row["wall_ms"] for row in rows),
            "p95_wall_ms": sorted(row["wall_ms"] for row in rows)[max(0, (95 * len(rows) + 99) // 100 - 1)],
            "median_cpu_ms": statistics.median(row["cpu_ms"] for row in rows),
        }
    print(json.dumps({
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cleanup_mode": "legacy_quiet_window" if args.legacy else "subreaper_echild",
        "implementation_sha256": hashlib.sha256(Path(process_runtime.__file__).read_bytes()).hexdigest(),
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
