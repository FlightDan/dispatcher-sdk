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

# Bound values returned to Python as well as the number of rows returned.
# On Python 3.10, SQLite can still materialize larger stored values internally.
_MAX_SQLITE_LENGTH = 65536


def _bounded_projection(*columns: str) -> str:
    """Bound data returned to Python even when Connection.setlimit is absent."""
    size = "+".join(f"coalesce(length(CAST({column} AS BLOB)),0)" for column in columns)
    within = f"({size})<={_MAX_SQLITE_LENGTH}"
    return ",".join(f"CASE WHEN {within} THEN {column} END AS {column}" for column in columns) + f", NOT ({within}) AS _oversized"


def _checked(row: sqlite3.Row | None) -> sqlite3.Row | None:
    if row is not None and row["_oversized"]:
        raise sqlite3.DataError("inspection row exceeds length limit")
    return row


def _values(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys() if key != "_oversized"}


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
            if hasattr(connection, "setlimit") and hasattr(sqlite3, "SQLITE_LIMIT_LENGTH"):
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
            orch_version = _checked(orch.execute(f"SELECT {_bounded_projection('version')} FROM sdk_schema_meta WHERE component='orchestrator'").fetchone())
            orch_observed_at = time.time()
            kernel_version = _checked(kernel.execute(f"SELECT {_bounded_projection('schema_version')} FROM kernel_schema_meta WHERE component='execution_kernel'").fetchone())
            kernel_observed_at = time.time()
            if orch_version is None or orch_version[0] not in (4, 5):
                raise ValueError("unsupported Orchestrator schema marker")
            if kernel_version is None or kernel_version[0] not in (5, 6, 7, 8):
                raise ValueError("unsupported Kernel schema marker")
            # Keyset cursors require a unique ordering key. A schema marker
            # alone does not establish that the required index exists.
            cursor_index = False
            for index in orch.execute(f"SELECT {_bounded_projection('name', 'partial')} FROM pragma_index_list('sdk_executions') WHERE \"unique\"=1"):
                budget.check()
                _checked(index)
                if index['partial']:
                    continue
                columns = orch.execute(f'SELECT {_bounded_projection("name", "coll")} FROM pragma_index_xinfo(?) WHERE "key"=1 LIMIT 4', (index['name'],))
                keys = [(_checked(column)['name'], column['coll']) for column in columns]
                if keys == [("run_id", "BINARY"), ("task_id", "BINARY"),
                            ("attempt", "BINARY")]:
                    cursor_index = True
                    break
            if not cursor_index:
                raise ValueError("unsupported execution cursor index")
            run = _checked(orch.execute(f"SELECT {_bounded_projection('run_id', 'revision', 'state')} FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone())
            if run is None:
                raise ValueError("Run not found")
            # Reading the marker and Run above establishes this connection's
            # snapshot; Kernel's snapshot is established by its marker read.
            observed_at = {"orchestrator": orch_observed_at, "kernel": kernel_observed_at}
            rows = orch.execute(
                f"SELECT {_bounded_projection('execution_id', 'task_id', 'attempt', 'generation', 'active')} FROM sdk_executions "
                "WHERE run_id COLLATE BINARY=? AND (task_id COLLATE BINARY>? OR "
                "(task_id COLLATE BINARY=? AND attempt>?)) "
                "ORDER BY task_id COLLATE BINARY,attempt LIMIT ?",
                (run_id, after_task_id, after_task_id, after_attempt, limit + 1),
            ).fetchall()
            for row in rows:
                _checked(row)
            has_more = len(rows) > limit
            result = []
            for row in rows[:limit]:
                budget.check()
                factual = _checked(kernel.execute(
                    f"SELECT {_bounded_projection('state', 'attempt', 'fence')} FROM kernel_executions WHERE execution_id=?",
                    (row["execution_id"],),
                ).fetchone())
                result.append({**_values(row), "kernel_observation": (
                    {"status": "observed", **_values(factual)} if factual is not None
                    else {"status": "not_observed"})})
            budget.check()
            last = result[-1] if has_more and result else None
            return {
                "run": _values(run), "orchestrator_schema": orch_version[0],
                "kernel_schema": kernel_version[0], "observed_at": observed_at,
                "executions": result, "has_more": has_more,
                "next_cursor": ({"after_task_id": last["task_id"],
                                 "after_attempt": last["attempt"]} if last else None),
                "cross_store_snapshot": False, "schema_validation": "marker_and_cursor_index_only",
                "kernel_association": "execution_id_match_only",
                "writer_isolation": "unknown", "budget": "unknown", "cleanup": "unknown",
                "adoption_eligibility": "unknown", "elapsed_seconds": budget.elapsed_seconds,
            }
