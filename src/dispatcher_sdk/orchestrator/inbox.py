"""Durable, source-scoped receipt and fenced consumption of notifications.

The inbox may share the application's SQLite file. ``consume`` can atomically
commit application SQL and its consumed marker; arbitrary external effects
remain at least once and require their own idempotency or outbox protocol.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import inspect
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Iterator, Literal, TypedDict, cast
import uuid

from ..durability import Durability, configure_sqlite_connection, validate_durability
from ..execution_kernel.errors import StaleFenceError
from .contracts import CommandConflict, canonical


InboxState = Literal["pending", "processing", "consumed", "dead"]


class InboxRecord(TypedDict):
    source_id: str
    notification_id: str
    payload: Any
    state: InboxState
    attempts: int
    max_attempts: int
    fence: int
    revision: int
    lease_id: str | None
    owner: str | None
    expires_at: float | None
    next_attempt_at: float
    last_error: dict[str, Any] | None
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class InboxLease:
    source_id: str
    notification_id: str
    lease_id: str
    owner: str
    fence: int
    expires_at: float
    attempt: int
    payload: Any


INBOX_SCHEMA_VERSION = 1


_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS notification_inbox_meta (
        component TEXT NOT NULL PRIMARY KEY CHECK(component='notification_inbox'),
        version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version=1))""",
    "INSERT INTO main.notification_inbox_meta VALUES('notification_inbox',1)",
    """CREATE TABLE IF NOT EXISTS notification_inbox_messages (
        source_id TEXT NOT NULL, notification_id TEXT NOT NULL, payload TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending','processing','consumed','dead')),
        attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL CHECK(max_attempts>0),
        lease_id TEXT, owner TEXT, fence INTEGER NOT NULL DEFAULT 0,
        expires_at REAL, next_attempt_at REAL NOT NULL, last_error TEXT, settlement TEXT,
        revision INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        PRIMARY KEY(source_id,notification_id))""",
    """CREATE INDEX IF NOT EXISTS notification_inbox_pending
        ON notification_inbox_messages(state,next_attempt_at,created_at,source_id,notification_id)""",
    """CREATE TABLE IF NOT EXISTS notification_inbox_clock (
        id INTEGER PRIMARY KEY CHECK(id=1), value REAL NOT NULL)""",
    "INSERT OR IGNORE INTO main.notification_inbox_clock VALUES(1,0)",
)


def _inbox_schema_objects(connection: sqlite3.Connection) -> dict[tuple[str, str], str]:
    return {(row[0], row[1]): row[2] for row in connection.execute(
        "SELECT type,name,sql FROM main.sqlite_master WHERE sql IS NOT NULL AND "
        "(lower(name) GLOB 'notification_inbox_*' OR lower(tbl_name) GLOB 'notification_inbox_*')")}


def validate_inbox_schema(connection: sqlite3.Connection) -> None:
    """Validate an existing inbox without writing to the supplied connection.

    An absent, partial or unsupported inbox is rejected. Callers that permit a
    database without an inbox must check for its namespace before calling.
    """
    reference = sqlite3.connect(":memory:")
    try:
        for statement in _SCHEMA:
            reference.execute(statement)
        if _inbox_schema_objects(connection) != _inbox_schema_objects(reference):
            raise ValueError("notification inbox schema differs from its declared version")
    finally:
        reference.close()
    marker = connection.execute("SELECT component,version FROM main.notification_inbox_meta").fetchall()
    if len(marker) != 1 or tuple(marker[0]) != ("notification_inbox", INBOX_SCHEMA_VERSION):
        raise ValueError("unsupported notification inbox schema version")
    clock = connection.execute("SELECT id,value FROM main.notification_inbox_clock").fetchall()
    if (len(clock) != 1 or clock[0][0] != 1 or type(clock[0][1]) not in (int, float)
            or not math.isfinite(clock[0][1]) or clock[0][1] < 0):
        raise ValueError("notification inbox clock is missing or invalid")


def _identity(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _integer(value: Any, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return number


def _future(now: float, delay: float) -> float:
    result = now + delay
    if not math.isfinite(result) or (delay > 0 and result <= now):
        raise ValueError("delay cannot produce a finite future timestamp")
    return result


def _check_lease(lease: InboxLease) -> None:
    if type(lease) is not InboxLease:
        raise TypeError("lease must be an InboxLease")
    for name in ("source_id", "notification_id", "lease_id", "owner"):
        _identity(getattr(lease, name), name)
    _integer(lease.fence, "fence")


def _business_authorizer(action, first, second, database, trigger):
    # sqlite3.executescript() implicitly commits an active transaction. Deny
    # transaction control too, rather than silently splitting the atomic unit.
    if action in {sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT,
                  sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}:
        return sqlite3.SQLITE_DENY
    if database not in (None, "main", "temp"):
        return sqlite3.SQLITE_DENY
    writes = {
        sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW, sqlite3.SQLITE_CREATE_TEMP_INDEX, sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER, sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW, sqlite3.SQLITE_DROP_TEMP_INDEX, sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER, sqlite3.SQLITE_DROP_TEMP_VIEW, sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_CREATE_VTABLE, sqlite3.SQLITE_DROP_VTABLE, sqlite3.SQLITE_REINDEX, sqlite3.SQLITE_ANALYZE,
    }
    if action in writes and any(type(value) is str and value.lower().startswith("notification_inbox_")
                                for value in (first, second)):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class NotificationInbox:
    """Accept notifications durably, then process them with independent leases.

    Connections are operation-scoped. The source ID is an application-chosen,
    stable namespace for the originating store, not an authentication boundary.
    """

    def __init__(self, path: str | Path, *, durability: Durability = "full",
                 clock: Callable[[], float] = time.time) -> None:
        self.durability = validate_durability(durability)
        if str(path) == ":memory:":
            raise ValueError("NotificationInbox requires a durable SQLite file")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.db_path = str(Path(path).resolve())
        self.clock = clock
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if _inbox_schema_objects(connection):
                validate_inbox_schema(connection)
            else:
                for statement in _SCHEMA:
                    connection.execute(statement)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            configure_sqlite_connection(connection, self.db_path, durability=self.durability)
            connection.execute("PRAGMA foreign_keys = ON")
        except BaseException:
            connection.close()
            raise
        return connection

    def close(self) -> None:
        """No connections remain open between operations."""

    def __enter__(self) -> NotificationInbox:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterator[tuple[sqlite3.Connection, Callable[[], float]]]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            watermark = float(connection.execute("SELECT value FROM main.notification_inbox_clock WHERE id=1").fetchone()[0])

            def now() -> float:
                nonlocal watermark
                watermark = max(watermark, _number(self.clock(), "clock"))
                connection.execute("UPDATE main.notification_inbox_clock SET value=? WHERE id=1", (watermark,))
                return watermark

            now()
            connection.execute("SAVEPOINT inbox_operation")
            try:
                yield connection, now
            except BaseException:
                connection.execute("ROLLBACK TO inbox_operation")
                connection.execute("RELEASE inbox_operation")
                # Preserve even an expiry observed after a failed business
                # callback, so moving the wall clock back cannot revive it.
                connection.execute("UPDATE main.notification_inbox_clock SET value=? WHERE id=1", (watermark,))
                connection.commit()
                raise
            connection.execute("RELEASE inbox_operation")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _row(connection, source_id, notification_id):
        row = connection.execute(
            "SELECT * FROM main.notification_inbox_messages WHERE source_id=? AND notification_id=?",
            (source_id, notification_id)).fetchone()
        if row is None:
            raise KeyError((source_id, notification_id))
        return row

    @staticmethod
    def _record(row) -> InboxRecord:
        value = dict(row)
        value.pop("settlement")
        value["payload"] = json.loads(value["payload"])
        if isinstance(value["payload"], dict):
            value["payload"].setdefault("generation", 0)
        value["last_error"] = None if value["last_error"] is None else json.loads(value["last_error"])
        return cast(InboxRecord, value)

    @staticmethod
    def _matches(row, lease: InboxLease) -> bool:
        return (row["lease_id"], row["owner"], row["fence"]) == (lease.lease_id, lease.owner, lease.fence)

    def _active(self, connection, lease: InboxLease, now: float):
        row = self._row(connection, lease.source_id, lease.notification_id)
        if not self._matches(row, lease) or row["state"] != "processing" or row["expires_at"] <= now:
            raise StaleFenceError("notification inbox processing lease is stale")
        return row

    def accept(self, source_id: str, payload: Any, *, notification_id: str | None = None,
               max_attempts: int = 5) -> InboxRecord:
        """Commit receipt before the delivery callback acknowledges upstream.

        Notification dictionaries supply their own notification_id. Other JSON
        values require an explicit ID. A replay retains the original retry
        budget and current processing state, including the consumed marker.
        """
        _identity(source_id, "source_id")
        _integer(max_attempts, "max_attempts")
        if callable(getattr(payload, "to_dict", None)):
            payload = payload.to_dict()
        embedded = payload.get("notification_id") if type(payload) is dict else None
        if notification_id is None:
            notification_id = embedded
        elif type(payload) is dict and "notification_id" in payload and embedded != notification_id:
            raise ValueError("notification_id differs from the payload's identity")
        _identity(notification_id, "notification_id")
        encoded = canonical(payload)
        with self._transaction() as (connection, clock):
            now = clock()
            row = connection.execute(
                "SELECT * FROM main.notification_inbox_messages WHERE source_id=? AND notification_id=?",
                (source_id, notification_id)).fetchone()
            if row is not None:
                if row["payload"] != encoded:
                    raise CommandConflict("source/notification identity already has different content")
                return self._record(row)
            connection.execute(
                "INSERT INTO main.notification_inbox_messages(source_id,notification_id,payload,state,max_attempts,"
                "next_attempt_at,created_at,updated_at) VALUES(?,?,?,'pending',?,?,?,?)",
                (source_id, notification_id, encoded, max_attempts, now, now, now))
            return self._record(self._row(connection, source_id, notification_id))

    def get(self, source_id: str, notification_id: str) -> InboxRecord:
        _identity(source_id, "source_id")
        _identity(notification_id, "notification_id")
        connection = self._connect()
        try:
            return self._record(self._row(connection, source_id, notification_id))
        finally:
            connection.close()

    def list_messages(self, *, source_id: str | None = None, state: InboxState | None = None,
                      limit: int = 100) -> tuple[InboxRecord, ...]:
        if source_id is not None:
            _identity(source_id, "source_id")
        if state not in (None, "pending", "processing", "consumed", "dead"):
            raise ValueError("invalid inbox state")
        _integer(limit, "limit")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM main.notification_inbox_messages WHERE (? IS NULL OR source_id=?) "
                "AND (? IS NULL OR state=?) ORDER BY created_at,source_id,notification_id LIMIT ?",
                (source_id, source_id, state, state, limit)).fetchall()
            return tuple(self._record(row) for row in rows)
        finally:
            connection.close()

    def claim(self, owner: str, *, source_id: str | None = None,
              lease_seconds: float = 30) -> InboxLease | None:
        _identity(owner, "owner")
        if source_id is not None:
            _identity(source_id, "source_id")
        duration = _number(lease_seconds, "lease_seconds", positive=True)
        with self._transaction() as (connection, clock):
            now = clock()
            expiry = _future(now, duration)
            connection.execute(
                "UPDATE main.notification_inbox_messages SET state=CASE WHEN attempts>=max_attempts THEN 'dead' ELSE 'pending' END, "
                "expires_at=NULL,next_attempt_at=?,last_error=?,settlement=NULL,revision=revision+1,updated_at=? "
                "WHERE state='processing' AND expires_at<=?",
                (now, canonical({"type": "LeaseExpired", "message": "inbox processing lease expired"}), now, now))
            row = connection.execute(
                "SELECT * FROM main.notification_inbox_messages WHERE state='pending' AND next_attempt_at<=? "
                "AND (? IS NULL OR source_id=?) ORDER BY created_at,source_id,notification_id LIMIT 1",
                (now, source_id, source_id)).fetchone()
            if row is None:
                return None
            lease_id = uuid.uuid4().hex
            connection.execute(
                "UPDATE main.notification_inbox_messages SET state='processing',attempts=attempts+1,fence=fence+1,"
                "lease_id=?,owner=?,expires_at=?,settlement=NULL,revision=revision+1,updated_at=? "
                "WHERE source_id=? AND notification_id=?",
                (lease_id, owner, expiry, now, row["source_id"], row["notification_id"]))
            return InboxLease(row["source_id"], row["notification_id"], lease_id, owner, row["fence"] + 1,
                              expiry, row["attempts"] + 1, json.loads(row["payload"]))

    def consume(self, lease: InboxLease,
                mutation: Callable[[sqlite3.Connection, Any], Any] | None = None) -> InboxRecord:
        """Commit trusted application SQL and mark consumed in one transaction.

        The synchronous mutation receives this inbox's main SQLite connection
        and a fresh payload loaded from storage. It must not manage transactions,
        change the inbox's tables/authorizer, or perform external side effects.
        An already committed replay of this lease skips the mutation entirely.
        """
        _check_lease(lease)
        if mutation is not None and not callable(mutation):
            raise TypeError("mutation must be callable")
        with self._transaction() as (connection, clock):
            now = clock()
            row = self._row(connection, lease.source_id, lease.notification_id)
            if self._matches(row, lease) and row["state"] == "consumed":
                return self._record(row)
            self._active(connection, lease, now)
            if mutation is not None:
                connection.set_authorizer(_business_authorizer)
                try:
                    returned = mutation(connection, json.loads(row["payload"]))
                    if inspect.isawaitable(returned):
                        if inspect.iscoroutine(returned):
                            returned.close()
                        raise TypeError("mutation must be synchronous")
                finally:
                    # Passing None only disables the authorizer on Python 3.11+.
                    # This connection is private to the current operation and
                    # closes after the SDK finishes settlement or rollback.
                    connection.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
            now = clock()
            self._active(connection, lease, now)
            connection.execute(
                "UPDATE main.notification_inbox_messages SET state='consumed',expires_at=NULL,last_error=NULL,"
                "settlement=?,revision=revision+1,updated_at=? WHERE source_id=? AND notification_id=?",
                (canonical({"kind": "consumed"}), now, lease.source_id, lease.notification_id))
            return self._record(self._row(connection, lease.source_id, lease.notification_id))

    def fail(self, lease: InboxLease, *, error: dict[str, Any], retry_delay: float = 1) -> InboxRecord:
        _check_lease(lease)
        if type(error) is not dict:
            raise ValueError("error must be a JSON object")
        delay = _number(retry_delay, "retry_delay")
        encoded_error = canonical(error)
        settlement = canonical({"kind": "failed", "error": error, "retry_delay": delay})
        with self._transaction() as (connection, clock):
            now = clock()
            row = self._row(connection, lease.source_id, lease.notification_id)
            if self._matches(row, lease) and row["state"] in ("pending", "dead") and row["settlement"] is not None:
                if row["settlement"] != settlement:
                    raise CommandConflict("inbox lease already has a different failure receipt")
                return self._record(row)
            self._active(connection, lease, now)
            state = "dead" if row["attempts"] >= row["max_attempts"] else "pending"
            connection.execute(
                "UPDATE main.notification_inbox_messages SET state=?,expires_at=NULL,next_attempt_at=?,last_error=?,"
                "settlement=?,revision=revision+1,updated_at=? WHERE source_id=? AND notification_id=?",
                (state, _future(now, delay), encoded_error, settlement, now, lease.source_id, lease.notification_id))
            return self._record(self._row(connection, lease.source_id, lease.notification_id))

    def retry_dead(self, source_id: str, notification_id: str, *, expected_revision: int) -> InboxRecord:
        _identity(source_id, "source_id")
        _identity(notification_id, "notification_id")
        _integer(expected_revision, "expected_revision")
        with self._transaction() as (connection, clock):
            now = clock()
            row = self._row(connection, source_id, notification_id)
            if row["revision"] != expected_revision:
                raise StaleFenceError("inbox retry revision is stale")
            if row["state"] != "dead":
                raise ValueError("only dead inbox messages can be retried")
            connection.execute(
                "UPDATE main.notification_inbox_messages SET state='pending',attempts=0,lease_id=NULL,owner=NULL,"
                "expires_at=NULL,next_attempt_at=?,settlement=NULL,revision=revision+1,updated_at=? "
                "WHERE source_id=? AND notification_id=?", (now, now, source_id, notification_id))
            return self._record(self._row(connection, source_id, notification_id))


__all__ = ["NotificationInbox", "InboxLease", "InboxRecord", "InboxState"]
