"""Persist journal discovery independently of the current handler deployment."""

from pathlib import Path
import sqlite3
from uuid import uuid4

from ..durability import configure_sqlite_connection


_META = "CREATE TABLE runtime_sandbox_meta (version INTEGER NOT NULL CHECK(version=1), store_id TEXT NOT NULL)"
_JOURNALS = "CREATE TABLE runtime_sandbox_journals (path TEXT PRIMARY KEY)"


def validate_registry(connection):
    objects = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'runtime_sandbox_*'"))
    if objects != {"runtime_sandbox_meta": _META, "runtime_sandbox_journals": _JOURNALS}:
        raise ValueError("incompatible sandbox journal registry")
    rows = connection.execute("SELECT version,store_id FROM runtime_sandbox_meta").fetchall()
    if len(rows) != 1 or rows[0][0] != 1 or type(rows[0][1]) is not str or not rows[0][1]:
        raise ValueError("incompatible sandbox journal registry metadata")
    return rows[0][1]


def register_journals(db_path, paths, *, durability, initialize_only=False):
    if str(db_path) == ":memory:":
        return None
    connection = sqlite3.connect(db_path, timeout=30)
    try:
        configure_sqlite_connection(connection, db_path, durability=durability)
        connection.execute("BEGIN IMMEDIATE")
        objects = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE name GLOB 'runtime_sandbox_*'"))
        if not objects:
            if not paths and not initialize_only:
                return None
            connection.execute(_META)
            connection.execute(_JOURNALS)
            connection.execute("INSERT INTO runtime_sandbox_meta VALUES(1,?)", (uuid4().hex,))
        store_id = validate_registry(connection)
        if initialize_only:
            connection.commit()
            return store_id
        old_paths = {r[0] for r in connection.execute("SELECT path FROM runtime_sandbox_journals")}
        for path in paths:
            if path in old_paths and not Path(path).is_file():
                raise ValueError("registered sandbox journal is missing; restore it before execution")
            if Path(path).is_file():
                prior = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
                try:
                    bound = prior.execute("SELECT store_id FROM sandbox_meta").fetchone()[0]
                    if bound != store_id:
                        raise ValueError("registered sandbox journal binding is missing or belongs to another store")
                finally:
                    prior.close()
            else:
                raise ValueError("sandbox journal must be bound before registration")
            connection.execute("INSERT OR IGNORE INTO runtime_sandbox_journals VALUES(?)", (path,))
        connection.commit()
        return store_id
    finally:
        connection.close()


def journal_paths(db_path):
    if str(db_path) == ":memory:":
        return ()
    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='runtime_sandbox_journals'").fetchone() is None:
            return ()
        return tuple(r[0] for r in connection.execute("SELECT path FROM runtime_sandbox_journals ORDER BY path"))
    finally:
        connection.close()
