"""SQLite contention facts, independent of operation retry policy."""
import sqlite3


def is_sqlite_contention(error: Exception) -> bool:
    if not isinstance(error, sqlite3.OperationalError):
        return False
    code = getattr(error, "sqlite_errorcode", None)
    if isinstance(code, int):
        return code & 255 in {5, 6}
    # Python 3.10 does not expose SQLite result codes. Never override a
    # present permanent code, or infer contention from arbitrary error text.
    return code is None and str(error).lower() in {
        "database is locked", "database table is locked"}
