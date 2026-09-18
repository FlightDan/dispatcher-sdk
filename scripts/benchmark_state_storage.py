"""Benchmark repeated 512 KiB application state commits.

PYTHONPATH=src python3 scripts/benchmark_state_storage.py --counts 1 20 80

Each mode uses an independent temporary SQLite store.  The payload is a
deterministic high-entropy ASCII string, so results do not depend on unusually
compressible repeated characters.  Temporary databases are removed by default.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import tempfile
import time

from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.storage_usage import inspect_storage_usage


_MODES = ("unchanged", "changing-sibling", "omitted")


def _payload(size: int) -> str:
    raw = hashlib.shake_256(b"dispatcher-sdk-state-storage-benchmark-v1").digest(
        (size * 3 + 3) // 4
    )
    return base64.b64encode(raw).decode("ascii")[:size]


def _state(mode: str, payload: str, commit: int):
    if mode == "unchanged":
        return {"large_value": payload, "sibling": 0}
    if mode == "changing-sibling":
        return {"large_value": payload, "sibling": commit}
    if mode == "omitted" and commit == 1:
        return {"large_value": payload, "sibling": 0}
    return None


def _run_mode(root: Path, mode: str, counts: list[int], payload: str, durability: str) -> dict:
    path = root / f"{mode}.sqlite3"
    measurements = []
    durations = []
    with Orchestrator.open_sqlite(path, {}, durability=durability) as orchestrator:
        orchestrator.create_run("run", command_id="create")
        revision = 0
        for commit in range(1, counts[-1] + 1):
            started = time.perf_counter()
            state = _state(mode, payload, commit)
            arguments = {
                "command_id": f"commit-{commit:08d}",
                "expected_revision": revision,
                "operations": [],
            }
            if state is not None:
                arguments["application_state"] = state
            snapshot = orchestrator.apply_operations("run", **arguments)
            durations.append(time.perf_counter() - started)
            revision = snapshot["revision"]
            if commit in counts:
                usage = inspect_storage_usage(path, detail="physical")
                measurements.append({
                    "commits": commit,
                    "physical_total_bytes": usage["physical_total_bytes"],
                    "files": {name: value["bytes"] for name, value in usage["files"].items()},
                    "allocated_page_bytes": usage["sqlite"]["allocated_page_bytes"],
                    "free_page_bytes": usage["sqlite"]["free_page_bytes"],
                    "elapsed_seconds": sum(durations),
                })
                durations.clear()
    return {"database": str(path), "measurements": measurements}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--counts", type=int, nargs="+", default=[1, 20, 80])
    parser.add_argument("--payload-bytes", type=int, default=512 * 1024)
    parser.add_argument("--modes", nargs="+", choices=_MODES, default=list(_MODES))
    parser.add_argument("--durability", choices=("full", "normal"), default="full")
    parser.add_argument("--keep-db", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.counts or min(args.counts) < 1:
        parser.error("counts must contain positive integers")
    if args.payload_bytes < 0:
        parser.error("payload bytes must be nonnegative")

    counts = sorted(set(args.counts))
    modes = list(dict.fromkeys(args.modes))
    root = Path(tempfile.mkdtemp(prefix="dispatcher-state-storage-"))
    payload = _payload(args.payload_bytes)
    try:
        report = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "sqlite": sqlite3.sqlite_version,
            },
            "configuration": {
                "counts": counts,
                "payload_bytes": args.payload_bytes,
                "payload_generation": "deterministic SHAKE-256 bytes encoded as base64",
                "modes": modes,
                "durability": args.durability,
                "temporary_directory": str(root),
                "databases_retained": args.keep_db,
            },
            "modes": {
                mode: _run_mode(root, mode, counts, payload, args.durability) for mode in modes
            },
        }
        encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        sys.stdout.write(encoded)
    finally:
        if not args.keep_db:
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
