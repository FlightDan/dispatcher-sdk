"""Wall-clock admission for operation-local SQLite transactions."""
from __future__ import annotations

import sqlite3
import time
from typing import Callable, TypeVar

from ._sqlite_errors import is_sqlite_contention


_T = TypeVar("_T")


def begin_immediate(connection: sqlite3.Connection) -> None:
    """Acquire a writer without native busy backoff missing short free slots.

    Keep the connection's existing admission allowance. Only BEGIN retries;
    the original busy policy is restored before any transaction body or COMMIT.
    """
    timeout_ms = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    if timeout_ms == 0:
        connection.execute("BEGIN IMMEDIATE")
        return
    deadline = time.monotonic() + timeout_ms / 1000
    connection.execute("PRAGMA busy_timeout=0")
    try:
        retry_sqlite_admission(lambda: connection.execute("BEGIN IMMEDIATE"),
            deadline=deadline, expired=TimeoutError("SQLite writer admission elapsed"))
    except BaseException as error:
        try:
            connection.execute(f"PRAGMA busy_timeout={timeout_ms}")
        except BaseException as restoration_error:
            raise error from restoration_error
        raise
    else:
        connection.execute(f"PRAGMA busy_timeout={timeout_ms}")


def retry_sqlite_admission(operation: Callable[[], _T], *, deadline: float,
                           expired: Exception,
                           transaction_retained: Callable[[], bool] | None = None) -> _T:
    """Retry only an admission operation, never its caller's business body.

    COMMIT callers require a retained transaction after a genuine busy error.
    A successful COMMIT is returned even if native durability I/O took longer:
    elapsed time cannot revoke an established receipt or justify work replay.
    """
    last_busy = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if last_busy is not None:
                raise last_busy
            raise expired
        try:
            return operation()
        except sqlite3.OperationalError as error:
            if (not is_sqlite_contention(error)
                    or (transaction_retained is not None and not transaction_retained())):
                raise
            last_busy = error
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(.01, remaining))
