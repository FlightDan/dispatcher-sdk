"""Wall-clock admission for operation-local SQLite transactions."""
from __future__ import annotations

import sqlite3
import time
from typing import Callable, TypeVar

from ._sqlite_errors import is_sqlite_contention


_T = TypeVar("_T")


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
