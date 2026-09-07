"""SQLite connection durability profiles shared by SDK persistence.

``full`` synchronizes every WAL commit; ``normal`` permits loss of recent
commits after host power loss while retaining SQLite's process-crash safety.
Both depend on the filesystem and storage honoring SQLite's synchronization.
Settings are connection-local except for WAL journal mode. Call this function
for every writer, before transactions or a restrictive authorizer are installed.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import time
from typing import Literal, cast

Durability = Literal["full", "normal"]
SQLITE_OPEN_TIMEOUT_SECONDS = 30.0

__all__ = ["Durability", "validate_durability", "configure_sqlite_connection"]


def validate_durability(value: object) -> Durability:
    """Validate a profile without silently falling back to weaker durability."""
    if type(value) is not str or value not in ("full", "normal"):
        raise ValueError("durability must be 'full' or 'normal'")
    return cast(Durability, value)


def _enable_wal(connection: sqlite3.Connection, db_path: str) -> None:
    # SQLite's journal-mode negotiation may return SQLITE_BUSY without invoking
    # its busy handler when two processes first open the same database.
    deadline = time.monotonic() + SQLITE_OPEN_TIMEOUT_SECONDS
    while True:
        try:
            row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            mode = "" if row is None else str(row[0]).lower()
            expected = "memory" if db_path == ":memory:" else "wal"
            if mode != expected:
                raise RuntimeError(f"SQLite refused {expected} journal mode: {mode or 'unknown'}")
            return
        except sqlite3.OperationalError as exc:
            if not any(token in str(exc).lower() for token in ("locked", "busy")):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))


def configure_sqlite_connection(
    connection: sqlite3.Connection,
    db_path: str | Path,
    *,
    durability: Durability = "full",
) -> None:
    """Configure and verify a connection, raising if SQLite refuses the profile.

    The caller owns the connection and must close it if configuration fails.
    In-memory databases remain nonpersistent even when ``full`` is selected.
    This configures the main database only; attached databases are not covered.
    """
    profile = validate_durability(durability)
    if connection.in_transaction:
        raise ValueError("SQLite durability must be configured outside a transaction")
    connection.execute("PRAGMA busy_timeout = 30000")
    _enable_wal(connection, str(db_path))
    synchronous = 2 if profile == "full" else 1
    connection.execute(f"PRAGMA synchronous = {synchronous}")
    expected = {
        "busy_timeout": 30000,
        "journal_mode": "memory" if str(db_path) == ":memory:" else "wal",
        "synchronous": synchronous,
    }
    for pragma, value in expected.items():
        row = connection.execute(f"PRAGMA {pragma}").fetchone()
        if row is None or row[0] != value:
            actual = None if row is None else row[0]
            raise RuntimeError(f"SQLite refused {pragma}={value!r}: {actual!r}")
