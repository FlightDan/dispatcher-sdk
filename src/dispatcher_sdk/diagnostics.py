"""Low-cost, read-only operational diagnostics for SDK SQLite stores.

The collector opens one read transaction per distinct database.  Counts from a
single file therefore share a SQLite snapshot; counts across different files do
not.  File sizes are filesystem observations and can change independently of a
snapshot.

This module deliberately does not report SQLite lock-wait time.  SQLite's
standard Python API does not expose that measurement.  ``sampling_duration_ms``
is the end-to-end cost of collecting the report, not lock contention.
"""

from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

from ._inspection import InspectionBudget, InspectionBudgetExceeded


DIAGNOSTICS_FORMAT_VERSION = 1

_EXECUTION_STATES = (
    "queued",
    "leased",
    "running",
    "recovery_required",
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
    "dead",
)
_OUTBOX_STATES = ("pending", "delivering", "delivered", "dead")
_NOTIFICATION_STATES = ("pending", "delivering", "delivered", "dead")
_INBOX_STATES = ("pending", "processing", "consumed", "dead")


class _Snapshot:
    def __init__(
        self, connection: sqlite3.Connection, budget: InspectionBudget
    ) -> None:
        self.connection = connection
        self.budget = budget
        self.query_count = 0

    def rows(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        self.budget.check()
        self.query_count += 1
        try:
            rows = self.connection.execute(sql, parameters).fetchall()
        except sqlite3.DatabaseError as error:
            if self.budget.interrupted(error):
                raise InspectionBudgetExceeded(
                    "diagnostics timeout exceeded"
                ) from error
            raise
        # A small query may finish without invoking SQLite's progress handler.
        # Never label a report complete after the shared deadline has passed.
        self.budget.check()
        return rows

    def value(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
        rows = self.rows(sql, parameters)
        return None if not rows else rows[0][0]


def _path(value: str | Path, name: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError(f"{name} must be a non-empty filesystem path")
    path = Path(value).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _readonly(path: Path, timeout_seconds: float) -> sqlite3.Connection:
    # as_uri() quotes URI-significant path characters.  mode=ro prevents an
    # accidental database creation while still reading committed WAL frames.
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro",
        uri=True,
        timeout=timeout_seconds,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
    except BaseException:
        connection.close()
        raise
    return connection


def _state_counts(
    snapshot: _Snapshot, table: str, states: tuple[str, ...]
) -> dict[str, int]:
    # table is selected only from fixed SDK table names in this module.
    rows = snapshot.rows(f"SELECT state,COUNT(*) FROM {table} GROUP BY state")
    observed = {str(row[0]): int(row[1]) for row in rows}
    return {state: observed.get(state, 0) for state in states}


def _file_sizes(path: Path) -> dict[str, int]:
    def size(candidate: Path) -> int:
        try:
            return candidate.stat().st_size
        except FileNotFoundError:
            return 0

    return {
        "database_bytes": size(path),
        "wal_bytes": size(Path(str(path) + "-wal")),
        "shm_bytes": size(Path(str(path) + "-shm")),
    }


def _kernel(snapshot: _Snapshot, tables: set[str], wall_now: float) -> dict[str, Any]:
    if "kernel_executions" not in tables:
        return {"present": False}
    executions = _state_counts(snapshot, "kernel_executions", _EXECUTION_STATES)
    watermark = snapshot.value(
        "SELECT watermark FROM kernel_clock WHERE singleton=1"
    )
    logical_now = max(wall_now, float(watermark))
    ready = int(
        snapshot.value(
            "SELECT COUNT(*) FROM kernel_executions "
            "WHERE state='queued' AND next_attempt_at<=?",
            (logical_now,),
        )
    )
    outbox = (
        _state_counts(snapshot, "kernel_result_outbox", _OUTBOX_STATES)
        if "kernel_result_outbox" in tables
        else {state: 0 for state in _OUTBOX_STATES}
    )
    return {
        "present": True,
        "logical_now": logical_now,
        "executions": {
            "by_state": executions,
            "total": sum(executions.values()),
            "backlog": sum(
                executions[state]
                for state in ("queued", "leased", "running", "recovery_required")
            ),
            "ready_queued": ready,
            "recovery_required": executions["recovery_required"],
        },
        "result_outbox": {
            "by_state": outbox,
            "backlog": outbox["pending"] + outbox["delivering"] + outbox["dead"],
        },
    }


def _orchestrator(snapshot: _Snapshot, tables: set[str]) -> dict[str, Any]:
    if "sdk_schema_meta" not in tables:
        return {"present": False}
    result: dict[str, Any] = {"present": True}
    if "sdk_outbox" in tables:
        pending = int(
            snapshot.value("SELECT COUNT(*) FROM sdk_outbox WHERE delivered=0")
        )
        result["dispatch_outbox"] = {"undelivered": pending}
    if "sdk_watches" in tables:
        result["open_watches"] = int(
            snapshot.value("SELECT COUNT(*) FROM sdk_watches WHERE completed=0")
        )
    return result


def _notifications(
    snapshot: _Snapshot, tables: set[str], wall_now: float
) -> dict[str, Any]:
    if "sdk_notifications" not in tables:
        return {"present": False}
    counts = _state_counts(snapshot, "sdk_notifications", _NOTIFICATION_STATES)
    ready = int(
        snapshot.value(
            "SELECT COUNT(*) FROM sdk_notifications "
            "WHERE state='pending' AND next_attempt_at<=?",
            (wall_now,),
        )
    )
    return {
        "present": True,
        "by_state": counts,
        "backlog": counts["pending"] + counts["delivering"] + counts["dead"],
        "wall_clock_ready_pending": ready,
    }


def _inbox(snapshot: _Snapshot, tables: set[str], wall_now: float) -> dict[str, Any]:
    if "notification_inbox_messages" not in tables:
        return {"present": False}
    counts = _state_counts(snapshot, "notification_inbox_messages", _INBOX_STATES)
    watermark = snapshot.value(
        "SELECT value FROM notification_inbox_clock WHERE id=1"
    )
    logical_now = max(wall_now, float(watermark))
    ready = int(
        snapshot.value(
            "SELECT COUNT(*) FROM notification_inbox_messages "
            "WHERE state='pending' AND next_attempt_at<=?",
            (logical_now,),
        )
    )
    return {
        "present": True,
        "logical_now": logical_now,
        "by_state": counts,
        "backlog": counts["pending"] + counts["processing"] + counts["dead"],
        "ready_pending": ready,
    }


def collect_sqlite_diagnostics(
    kernel_path: str | Path,
    *,
    orchestrator_path: str | Path | None = None,
    inbox_path: str | Path | None = None,
    timeout_seconds: float = 5.0,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Collect queue and storage health without opening an SDK writer.

    ``orchestrator_path`` and ``inbox_path`` default to ``kernel_path`` for the
    common single-file deployment.  Each distinct file is sampled in one
    read-only SQLite transaction.  The returned dictionary is JSON serializable.

    The collector executes aggregate count queries.  Their cost depends on the
    database size and available indexes; ``sampling_duration_ms`` and
    ``query_count`` expose the observation cost.  They do not measure lock wait.
    """

    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(float(timeout_seconds))
        or float(timeout_seconds) < 0
    ):
        raise ValueError("timeout_seconds must be a finite nonnegative number")
    if not callable(clock):
        raise TypeError("clock must be callable")
    started = time.perf_counter()
    budget = InspectionBudget(float(timeout_seconds), None)
    wall_now = float(clock())
    if not math.isfinite(wall_now) or wall_now < 0:
        raise ValueError("clock must return a finite nonnegative timestamp")
    kernel = _path(kernel_path, "kernel_path")
    orchestrator = _path(
        kernel if orchestrator_path is None else orchestrator_path,
        "orchestrator_path",
    )
    inbox = _path(kernel if inbox_path is None else inbox_path, "inbox_path")
    component_paths = {
        "queue": kernel,
        "orchestrator": orchestrator,
        "notifications": orchestrator,
        "inbox": inbox,
    }
    grouped: dict[Path, set[str]] = {}
    for component, path in component_paths.items():
        grouped.setdefault(path, set()).add(component)

    result: dict[str, Any] = {
        "format_version": DIAGNOSTICS_FORMAT_VERSION,
        "collected_at": wall_now,
        "queue": {"present": False},
        "orchestrator": {"present": False},
        "notifications": {"present": False},
        "inbox": {"present": False},
        "databases": [],
        "complete": True,
        "stopped_reason": None,
    }
    total_queries = 0
    for path, components in grouped.items():
        connection: sqlite3.Connection | None = None
        snapshot: _Snapshot | None = None
        try:
            budget.check()
            connection = _readonly(path, budget.sqlite_timeout_seconds)
            budget.install(connection)
            snapshot = _Snapshot(connection, budget)
            tables = {
                str(row[0])
                for row in snapshot.rows(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                )
            }
            page_size = int(snapshot.value("PRAGMA page_size"))
            page_count = int(snapshot.value("PRAGMA page_count"))
            free_pages = int(snapshot.value("PRAGMA freelist_count"))
            database = {
                "path": str(path),
                "components": sorted(components),
                **_file_sizes(path),
                "page_size": page_size,
                "page_count": page_count,
                "freelist_pages": free_pages,
                "allocated_page_bytes": page_size * page_count,
                "used_page_bytes": page_size * (page_count - free_pages),
                "journal_mode": str(snapshot.value("PRAGMA journal_mode")),
            }
            result["databases"].append(database)
            if "queue" in components:
                result["queue"] = _kernel(snapshot, tables, wall_now)
                result["queue"]["path"] = str(path)
            if "orchestrator" in components:
                result["orchestrator"] = _orchestrator(snapshot, tables)
                result["orchestrator"]["path"] = str(path)
            if "notifications" in components:
                result["notifications"] = _notifications(snapshot, tables, wall_now)
                result["notifications"]["path"] = str(path)
            if "inbox" in components:
                result["inbox"] = _inbox(snapshot, tables, wall_now)
                result["inbox"]["path"] = str(path)
            budget.check()
        except InspectionBudgetExceeded:
            result["complete"] = False
            result["stopped_reason"] = budget.stopped_reason or "timeout"
            break
        except sqlite3.DatabaseError as error:
            if not budget.interrupted(error):
                raise
            result["complete"] = False
            result["stopped_reason"] = budget.stopped_reason or "timeout"
            break
        finally:
            if snapshot is not None:
                total_queries += snapshot.query_count
            if connection is not None:
                budget.clear(connection)
                connection.rollback()
                connection.close()

    result["databases"].sort(key=lambda item: item["path"])
    if result["complete"]:
        try:
            budget.check()
        except InspectionBudgetExceeded:
            result["complete"] = False
            result["stopped_reason"] = budget.stopped_reason or "timeout"
    result["sampling"] = {
        "mode": "one read-only transaction per distinct database",
        "cross_file_atomic": len(grouped) == 1,
        "query_count": total_queries,
        "sampling_duration_ms": (time.perf_counter() - started) * 1000.0,
        "sqlite_lock_wait_measured": False,
        "sqlite_lock_wait_ms": None,
        "file_sizes_transactional": False,
        "complete": result["complete"],
        "stopped_reason": result["stopped_reason"],
    }
    return result


def inspect_diagnostics(
    path: str | Path, *, timeout_seconds: float = 5.0
) -> dict[str, Any]:
    """Inspect a standard single-file Dispatcher deployment."""

    return collect_sqlite_diagnostics(path, timeout_seconds=timeout_seconds)


__all__ = [
    "DIAGNOSTICS_FORMAT_VERSION",
    "collect_sqlite_diagnostics",
    "inspect_diagnostics",
]
