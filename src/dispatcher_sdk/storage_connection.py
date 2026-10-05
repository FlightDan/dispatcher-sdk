"""SQLite connections that participate in stable-path maintenance exclusion."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .maintenance import _assert_not_retired, storage_participant


class _ParticipatingConnection(sqlite3.Connection):
    _participation = None

    def close(self):
        # A failed close (for example from another thread) leaves SQLite live.
        # Keep its participation lock until SQLite has actually closed.
        super().close()
        participation, self._participation = self._participation, None
        if participation is not None:
            participation.__exit__(None, None, None)

    def __del__(self):
        try:
            self.close()
        except BaseException:
            # Finalizers must not mask an exception or interpreter shutdown.
            pass


def connect(
    database: str | os.PathLike[str],
    *,
    timeout: float = 5.0,
    detect_types: int = 0,
    isolation_level: str | None = "",
    check_same_thread: bool = True,
    cached_statements: int = 128,
) -> sqlite3.Connection:
    """Hold a shared maintenance lock for the whole connection lifetime.

    Maintenance code uses explicit SQLite connections while holding its exclusive
    lease. In-memory connections have no filesystem maintenance identity.
    This internal helper accepts filesystem paths or ':memory:', not SQLite
    URIs or custom factories; its connection factory owns the participation lock.
    """
    options = dict(timeout=timeout, detect_types=detect_types,
                   isolation_level=isolation_level, check_same_thread=check_same_thread,
                   cached_statements=cached_statements)
    if str(database) == ":memory:":
        return sqlite3.connect(database, **options)
    if os.path.lexists(Path(database).resolve().parent / ".sdk-snapshot-readonly"):
        raise PermissionError("authenticated snapshot requires explicit activation; SDK writers are disabled")
    _assert_not_retired(Path(database).expanduser().resolve(strict=False))
    participation = storage_participant(database)
    participation.__enter__()
    try:
        _assert_not_retired(Path(database).expanduser().resolve(strict=False))
        connection = sqlite3.connect(database, factory=_ParticipatingConnection, **options)
        connection._participation = participation
        return connection
    except BaseException:
        participation.__exit__(None, None, None)
        raise


def _connect_readonly(database: str | os.PathLike[str], *, timeout: float = 0,
                      check_same_thread: bool = True) -> sqlite3.Connection:
    """Own a file reader's maintenance receipt until SQLite actually closes.

    Readonly URI admission cannot create a missing store. Failed close retains
    the same connection-owned receipt, as it does for SDK writer connections.
    Opting out of thread affinity requires serialized use and positive proof
    that the reader body has left before another thread retries close.
    """
    path = Path(database).expanduser().resolve(strict=False)
    _assert_not_retired(path)
    participation = storage_participant(path, timeout=0)
    participation.__enter__()
    try:
        _assert_not_retired(path)
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
            factory=_ParticipatingConnection, timeout=timeout, isolation_level=None,
            check_same_thread=check_same_thread)
        connection._participation = participation
        return connection
    except BaseException:
        participation.__exit__(None, None, None)
        raise
