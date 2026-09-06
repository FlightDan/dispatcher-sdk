"""Connection, logical-clock, event, and row-codec primitives."""

from __future__ import annotations

from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterator, Optional

from ._sqlite_schema import (
    KERNEL_TABLES,
    existing_table_names,
    initialize_schema,
    install_authorizer,
    validate_schema,
)
from .contracts import (
    ExecutionCommandV2,
    ExecutionLease,
    ExecutionResultV2,
    ExecutionSnapshot,
)
from .errors import CASConflictError, ExecutionNotFoundError, StaleFenceError
from .event import Event
from .transitions import TERMINAL_STATES


MAX_SQLITE_INTEGER = (1 << 63) - 1
SQLITE_OPEN_TIMEOUT_SECONDS = 30.0


def _enable_wal(connection: sqlite3.Connection, db_path: str) -> None:
    """Negotiate WAL despite SQLite's non-busy-handler PRAGMA race.

    SQLite can return ``database is locked`` immediately from
    ``PRAGMA journal_mode=WAL`` when two processes open a new database at the
    same time, even after ``busy_timeout`` has been configured.  Retry only
    that transient lock class, bounded by the same timeout as the connection.
    """

    deadline = time.monotonic() + SQLITE_OPEN_TIMEOUT_SECONDS
    while True:
        try:
            row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            mode = "" if row is None else str(row[0]).lower()
            if db_path != ":memory:" and mode != "wal":
                raise RuntimeError(f"SQLite refused WAL journal mode: {mode or 'unknown'}")
            return
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if not any(token in message for token in ("locked", "busy")):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))


def encode_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class SQLiteBase:
    """Shared SQLite mechanics.

    Mutations use a persisted monotonic watermark sampled only after acquiring
    the database write lock.  A savepoint lets failed operations roll back
    while still committing the observed watermark.
    """

    _SCHEMA_TABLES = KERNEL_TABLES

    def __init__(
        self,
        db_path: str | Path,
        *,
        now: Any = None,
        default_lease_seconds: float = 30.0,
        outbox_max_attempts: int = 8,
    ) -> None:
        self.db_path = str(db_path)
        self._now = now or time.time
        self.default_lease_seconds = self._positive_duration(
            default_lease_seconds, "default_lease_seconds"
        )
        if type(outbox_max_attempts) is not int or outbox_max_attempts < 1:
            raise ValueError("outbox_max_attempts must be a positive integer")
        self.outbox_max_attempts = outbox_max_attempts
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.db_path,
            timeout=SQLITE_OPEN_TIMEOUT_SECONDS,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        try:
            # Configure lock waiting before the journal-mode negotiation; two
            # first-open callers can otherwise fail immediately while one is
            # creating the WAL files.
            self._connection.execute("PRAGMA busy_timeout = 30000")
            # WAL+NORMAL preserves atomicity and consistency across the
            # process-crash model qualified by the Kernel fault matrix while
            # avoiding one fsync per small fenced state transition.  A host
            # power-loss durability guarantee would require a separate FULL
            # durability profile and is not part of this local dispatcher
            # contract.
            _enable_wal(self._connection, self.db_path)
            self._connection.execute("PRAGMA synchronous = NORMAL")
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA writable_schema = OFF")
            self._connection.execute("PRAGMA trusted_schema = OFF")
            names = existing_table_names(self._connection)
            kernel_names = {name for name in names if name.startswith("kernel_")}
            if kernel_names:
                validate_schema(self._connection, kernel_names)
            else:
                initialize_schema(self._connection)
                validate_schema(self._connection, KERNEL_TABLES)
            self._authorizer = install_authorizer(self._connection)
        except BaseException:
            self._connection.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @staticmethod
    def _number(value: Any, name: str, *, minimum: float) -> float:
        if type(value) not in {int, float}:
            raise ValueError(f"{name} must be a finite number")
        try:
            converted = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a finite number") from exc
        if not math.isfinite(converted) or converted < minimum:
            raise ValueError(f"{name} must be finite and >= {minimum}")
        return converted

    @classmethod
    def _positive_duration(cls, value: Any, name: str) -> float:
        converted = cls._number(value, name, minimum=0.0)
        if converted <= 0:
            raise ValueError(f"{name} must be finite and positive")
        return converted

    @classmethod
    def _nonnegative_duration(cls, value: Any, name: str) -> float:
        return cls._number(value, name, minimum=0.0)

    @classmethod
    def _checked_add(cls, base: Any, delta: Any, name: str) -> float:
        left = cls._number(base, "clock value", minimum=0.0)
        right = cls._number(delta, name, minimum=0.0)
        result = left + right
        if not math.isfinite(result):
            raise ValueError(f"{name} addition overflowed the finite clock range")
        if right > 0 and result <= left:
            raise ValueError(f"{name} is too small to advance the logical clock")
        return result

    def _wall_time(self) -> float:
        return self._number(self._now(), "clock", minimum=0.0)

    def current_time(self) -> float:
        """Return logical now without mutating the durable watermark."""

        wall = self._wall_time()
        with self._lock:
            row = self._connection.execute(
                "SELECT watermark FROM kernel_clock WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("kernel logical clock row is missing")
        return max(wall, self._number(row["watermark"], "clock watermark", minimum=0.0))

    def _advance_clock(self, connection: sqlite3.Connection) -> float:
        row = connection.execute(
            "SELECT watermark FROM kernel_clock WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("kernel logical clock row is missing")
        old = self._number(row["watermark"], "clock watermark", minimum=0.0)
        timestamp = max(old, self._wall_time())
        cursor = connection.execute(
            "UPDATE kernel_clock SET watermark = ? WHERE singleton = 1 AND watermark = ?",
            (timestamp, row["watermark"]),
        )
        self._cas(cursor, "logical clock advance")
        return timestamp

    @contextmanager
    def _transaction(self) -> Iterator[tuple[sqlite3.Connection, float]]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                timestamp = self._advance_clock(self._connection)
                self._connection.execute("SAVEPOINT kernel_operation")
            except BaseException:
                self._connection.rollback()
                raise
            try:
                yield self._connection, timestamp
            except BaseException:
                try:
                    self._connection.execute("ROLLBACK TO kernel_operation")
                    self._connection.execute("RELEASE kernel_operation")
                    self._connection.commit()
                except BaseException:
                    self._connection.rollback()
                raise
            else:
                self._connection.execute("RELEASE kernel_operation")
                self._connection.commit()

    @staticmethod
    def _cas(cursor: sqlite3.Cursor, operation: str) -> None:
        if cursor.rowcount != 1:
            raise CASConflictError(f"revision CAS failed during {operation}")

    @staticmethod
    def _command(raw: str) -> ExecutionCommandV2:
        return ExecutionCommandV2.from_dict(json.loads(raw))

    @staticmethod
    def _result(raw: Optional[str]) -> Optional[ExecutionResultV2]:
        return None if raw is None else ExecutionResultV2.from_dict(json.loads(raw))

    @staticmethod
    def _lease(row: sqlite3.Row) -> Optional[ExecutionLease]:
        if row["lease_id"] is None:
            return None
        return ExecutionLease(
            execution_id=row["execution_id"],
            lease_id=row["lease_id"],
            owner=row["lease_owner"],
            fence=row["fence"],
            attempt=row["attempt"],
            expires_at=row["lease_expires_at"],
            revision=row["revision"],
        )

    def _snapshot(self, row: sqlite3.Row) -> ExecutionSnapshot:
        return ExecutionSnapshot(
            execution_id=row["execution_id"],
            state=row["state"],
            revision=row["revision"],
            attempt=row["attempt"],
            fence=row["fence"],
            redelivery_count=row["redelivery_count"],
            command=self._command(row["command_json"]),
            lease=self._lease(row),
            result=self._result(row["result_json"]),
            recovery_effect_id=row["recovery_effect_id"],
            recovery_target_state=row["recovery_target_state"],
            recovery_reason=row["recovery_reason"],
            next_attempt_at=row["next_attempt_at"],
            started_at=row["started_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _get_row(connection: sqlite3.Connection, execution_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM kernel_executions WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        if row is None:
            raise ExecutionNotFoundError(execution_id)
        return row

    def get(self, execution_id: str) -> ExecutionSnapshot:
        with self._lock:
            return self._snapshot(self._get_row(self._connection, execution_id))

    snapshot = get

    def pending_recoveries(self, *, limit: int = 100) -> list[ExecutionSnapshot]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM kernel_executions
                   WHERE state = 'recovery_required'
                   ORDER BY updated_at, execution_id LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._snapshot(row) for row in rows]

    def _assert_lease(
        self,
        connection: sqlite3.Connection,
        lease: ExecutionLease,
        *,
        timestamp: float,
        states: Optional[set[str]] = None,
    ) -> sqlite3.Row:
        if type(lease) is not ExecutionLease:
            raise TypeError("operation requires ExecutionLease")
        row = self._get_row(connection, lease.execution_id)
        context = {
            "execution_id": lease.execution_id,
            "lease_id": lease.lease_id,
            "expected_revision": lease.revision,
            "actual_revision": row["revision"],
            "attempt": lease.attempt,
            "actual_attempt": row["attempt"],
            "fence": lease.fence,
            "actual_fence": row["fence"],
            "state": row["state"],
        }
        if row["state"] in TERMINAL_STATES:
            raise StaleFenceError("terminal execution has no active lease", context=context)
        if states is not None and row["state"] not in states:
            raise StaleFenceError("lease is not valid for the current state", context=context)
        if (
            row["lease_id"] != lease.lease_id
            or row["lease_owner"] != lease.owner
            or row["revision"] != lease.revision
            or row["attempt"] != lease.attempt
            or row["fence"] != lease.fence
            or row["lease_expires_at"] != lease.expires_at
        ):
            raise StaleFenceError("lease attempt, fence, or revision is stale", context=context)
        if row["lease_expires_at"] is None or row["lease_expires_at"] <= timestamp:
            raise StaleFenceError("lease has expired", context=context)
        return row

    def _event(
        self,
        connection: sqlite3.Connection,
        *,
        execution_id: str,
        revision: int,
        event_type: str,
        from_state: Optional[str],
        to_state: str,
        data: Any,
        timestamp: float,
    ) -> Event:
        clock = connection.execute(
            "SELECT event_sequence FROM kernel_clock WHERE singleton = 1"
        ).fetchone()
        if clock is None or type(clock["event_sequence"]) is not int:
            raise RuntimeError("kernel event sequence is invalid")
        if clock["event_sequence"] >= MAX_SQLITE_INTEGER:
            raise OverflowError("kernel event sequence exhausted")
        sequence = clock["event_sequence"] + 1
        cursor = connection.execute(
            """UPDATE kernel_clock SET event_sequence = ?
               WHERE singleton = 1 AND event_sequence = ?""",
            (sequence, clock["event_sequence"]),
        )
        self._cas(cursor, "global event sequence")
        event = Event(
            sequence=sequence,
            event_id=f"{execution_id}:{revision}",
            execution_id=execution_id,
            revision=revision,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            data=data,
            created_at=timestamp,
        )
        cursor = connection.execute(
            """INSERT INTO kernel_events
               (sequence, event_id, execution_id, revision, event_type, from_state,
                to_state, data_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.sequence,
                event.event_id,
                event.execution_id,
                event.revision,
                event.event_type,
                event.from_state,
                event.to_state,
                encode_json(event.data),
                event.created_at,
            ),
        )
        self._cas(cursor, "execution event append")
        return event

    @staticmethod
    def _event_contract(row: sqlite3.Row) -> Event:
        return Event(
            sequence=row["sequence"],
            event_id=row["event_id"],
            execution_id=row["execution_id"],
            revision=row["revision"],
            event_type=row["event_type"],
            from_state=row["from_state"],
            to_state=row["to_state"],
            data=json.loads(row["data_json"]),
            created_at=row["created_at"],
        )

    def events_since(self, after_sequence: int, limit: int = 100) -> list[Event]:
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("after_sequence must be a non-negative integer")
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM kernel_events WHERE sequence > ?
                   ORDER BY sequence LIMIT ?""",
                (after_sequence, limit),
            ).fetchall()
        return [self._event_contract(row) for row in rows]

    def events(self, execution_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM kernel_events WHERE execution_id = ?
                   ORDER BY revision""",
                (execution_id,),
            ).fetchall()
        return [self._event_contract(row).to_dict() for row in rows]
