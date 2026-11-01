"""Read-only, bounded execution mapping for a legacy split-store Run.

This is an inspection building block, not an eligibility decision or adoption
operation. Each database has its own read transaction and observation time.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import time
from typing import Any

from .._inspection import InspectionBudget
from .contracts import identifier

# Bound each SQLite value/row as well as the number of rows returned.
_MAX_SQLITE_LENGTH = 65536


def inspect_legacy_execution_page(
    orchestrator_path: str | Path, kernel_path: str | Path, run_id: str, *,
    after_task_id: str = "", after_attempt: int = -1, limit: int = 100,
    timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    """Read one page of original execution identities and observed Kernel facts.

    A missing Kernel row is reported as ``not_observed``; it is not proof that
    the command was never delivered. Cursors are valid only as a new observation,
    not a shared snapshot across calls. Matching Kernel facts use execution_id
    only and do not prove association or command delivery. No handlers or
    storage writers are opened; SQLite may manage WAL sidecars for a reader.
    """
    identifier(run_id, "run_id")
    if len(run_id.encode("utf-8")) > _MAX_SQLITE_LENGTH:
        raise ValueError("run_id exceeds inspection length limit")
    if type(after_task_id) is not str or type(after_attempt) is not int or after_attempt < -1:
        raise ValueError("invalid execution cursor")
    if len(after_task_id.encode("utf-8")) > _MAX_SQLITE_LENGTH:
        raise ValueError("cursor exceeds inspection length limit")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    budget = InspectionBudget(timeout_seconds, None)

    def open_reader(path: str | Path) -> sqlite3.Connection:
        budget.check()
        if str(path) == ":memory:":
            raise ValueError("inspection requires an existing SQLite file")
        connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True,
                                     isolation_level=None, timeout=budget.sqlite_timeout_seconds)
        try:
            if not hasattr(connection, "setlimit") or not hasattr(sqlite3, "SQLITE_LIMIT_LENGTH"):
                raise RuntimeError("bounded inspection requires SQLite limit support (Python 3.11+)")
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, _MAX_SQLITE_LENGTH)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("BEGIN")
            budget.install(connection)
            return connection
        except BaseException:
            connection.close()
            raise

    with closing(open_reader(orchestrator_path)) as orch:
        with closing(open_reader(kernel_path)) as kernel:
            budget.check()
            orch_version = orch.execute("SELECT version FROM sdk_schema_meta WHERE component='orchestrator'").fetchone()
            orch_observed_at = time.time()
            kernel_version = kernel.execute("SELECT schema_version FROM kernel_schema_meta WHERE component='execution_kernel'").fetchone()
            kernel_observed_at = time.time()
            if orch_version is None or orch_version[0] not in (4, 5):
                raise ValueError("unsupported Orchestrator schema marker")
            if kernel_version is None or kernel_version[0] not in (5, 6, 7, 8):
                raise ValueError("unsupported Kernel schema marker")
            # Keyset cursors require a unique ordering key. A schema marker
            # alone does not establish that the required index exists.
            cursor_index = False
            for index in orch.execute("PRAGMA index_list(sdk_executions)"):
                budget.check()
                if not index[2] or index[4]:
                    continue
                name = index[1].replace('"', '""')
                columns = orch.execute(f'PRAGMA index_xinfo("{name}")').fetchall()
                keys = [(column[2], column[4]) for column in columns if column[5]]
                if keys == [("run_id", "BINARY"), ("task_id", "BINARY"),
                            ("attempt", "BINARY")]:
                    cursor_index = True
                    break
            if not cursor_index:
                raise ValueError("unsupported execution cursor index")
            run = orch.execute("SELECT run_id,revision,state FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Run not found")
            # Reading the marker and Run above establishes this connection's
            # snapshot; Kernel's snapshot is established by its marker read.
            observed_at = {"orchestrator": orch_observed_at, "kernel": kernel_observed_at}
            rows = orch.execute(
                "SELECT execution_id,task_id,attempt,generation,active FROM sdk_executions "
                "WHERE run_id COLLATE BINARY=? AND (task_id COLLATE BINARY>? OR "
                "(task_id COLLATE BINARY=? AND attempt>?)) "
                "ORDER BY task_id COLLATE BINARY,attempt LIMIT ?",
                (run_id, after_task_id, after_task_id, after_attempt, limit + 1),
            ).fetchall()
            has_more = len(rows) > limit
            result = []
            for row in rows[:limit]:
                budget.check()
                factual = kernel.execute(
                    "SELECT state,attempt,fence FROM kernel_executions WHERE execution_id=?",
                    (row["execution_id"],),
                ).fetchone()
                result.append({**dict(row), "kernel_observation": (
                    {"status": "observed", **dict(factual)} if factual is not None
                    else {"status": "not_observed"})})
            budget.check()
            last = result[-1] if has_more and result else None
            return {
                "run": dict(run), "orchestrator_schema": orch_version[0],
                "kernel_schema": kernel_version[0], "observed_at": observed_at,
                "executions": result, "has_more": has_more,
                "next_cursor": ({"after_task_id": last["task_id"],
                                 "after_attempt": last["attempt"]} if last else None),
                "cross_store_snapshot": False, "schema_validation": "marker_and_cursor_index_only",
                "kernel_association": "execution_id_match_only",
                "writer_isolation": "unknown", "budget": "unknown", "cleanup": "unknown",
                "adoption_eligibility": "unknown", "elapsed_seconds": budget.elapsed_seconds,
            }
