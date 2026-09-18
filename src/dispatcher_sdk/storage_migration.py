"""Explicit copy upgrades and copy compaction for Orchestrator stores.

These operations never modify or activate the source database.  They require a
live exclusive maintenance lease and publish only a fully validated new file.
The current implementation intentionally has no resumable large-store protocol;
a failed operation discards its private copy and must be restarted.
"""

from __future__ import annotations

from contextlib import closing
import errno
import os
from pathlib import Path
import shutil
import sqlite3
import time
from typing import Any, Callable
import uuid

from .content import decode_value, encode_value
from .maintenance import Lease
from .storage import _new_artifact
from .orchestrator.contracts import canonical
from .orchestrator.engine import Orchestrator
from .orchestrator.notifications import NotificationsMixin
from .orchestrator.results import ResultsMixin
from .orchestrator.store import (
    LEGACY_SCHEMA,
    ORCHESTRATOR_SCHEMA_VERSION,
    SCHEMA,
    StoreMixin,
    execute_schema,
    initialize_storage_tracking,
)


_BATCH_SIZE = 256
_Failpoint = Callable[[str], None]


class StorageMigrationError(ValueError):
    """A store cannot be safely upgraded or compacted as requested."""


def _hit(failpoint: _Failpoint | None, stage: str) -> None:
    if failpoint is not None:
        failpoint(stage)


def _paths(source: str | Path, destination: str | Path) -> tuple[Path, Path]:
    source_path = Path(source).expanduser().resolve(strict=True)
    destination_path = Path(destination).expanduser().absolute()
    if source_path == destination_path.resolve(strict=False):
        raise StorageMigrationError("destination must be a new file, not the source")
    if destination_path.exists():
        raise FileExistsError(destination_path)
    return source_path, destination_path


def _source_footprint(path: Path) -> int:
    total = path.stat().st_size
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(path) + suffix)
        try:
            total += sidecar.stat().st_size
        except FileNotFoundError:
            pass
    return total


def _space_precheck(source: Path, destination: Path) -> int:
    parent = destination.parent
    probe = parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    footprint = _source_footprint(source)
    # The private backup and SQLite's rewrite workspace may coexist.  This is
    # deliberately conservative and is still only a precheck, not a quota.
    required = max(footprint, 4096) * 2
    available = shutil.disk_usage(probe).free
    if available < required:
        raise OSError(
            errno.ENOSPC,
            f"copy operation needs at least {required} free bytes; {available} available",
            str(destination),
        )
    return required


def _open_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def _legacy_schema_objects() -> dict[tuple[str, str], str]:
    with closing(sqlite3.connect(":memory:")) as reference:
        execute_schema(reference, LEGACY_SCHEMA)
        results = ResultsMixin()
        results.max_result_deliveries = 5
        results._init_results(reference)
        NotificationsMixin._init_notifications(reference)
        return StoreMixin._schema_objects(reference)


def _declared_version(connection: sqlite3.Connection) -> int:
    try:
        marker = connection.execute(
            "SELECT component,version FROM sdk_schema_meta"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise StorageMigrationError(
            "database has no declared Orchestrator schema"
        ) from exc
    if len(marker) != 1 or marker[0][0] != "orchestrator" or type(marker[0][1]) is not int:
        raise StorageMigrationError("invalid Orchestrator schema marker")
    return marker[0][1]


def _validate_legacy(connection: sqlite3.Connection) -> None:
    if _declared_version(connection) != 2:
        raise StorageMigrationError("upgrade_storage requires an exact schema v2 source")
    if StoreMixin._schema_objects(connection) != _legacy_schema_objects():
        raise StorageMigrationError(
            "schema v2 source differs from the supported legacy schema"
        )


def _validate_current(connection: sqlite3.Connection) -> None:
    if _declared_version(connection) != ORCHESTRATOR_SCHEMA_VERSION:
        raise StorageMigrationError(
            f"operation requires an exact schema v{ORCHESTRATOR_SCHEMA_VERSION} source"
        )
    try:
        Orchestrator.__new__(Orchestrator)._validate_existing_store(connection)
    except (ValueError, RuntimeError, sqlite3.DatabaseError) as exc:
        raise StorageMigrationError("current Orchestrator schema validation failed") from exc


def _backup(source: Path, target_path: Path) -> None:
    with closing(_open_read_only(source)) as source_connection:
        source_connection.execute("BEGIN")
        with closing(sqlite3.connect(target_path, timeout=30)) as target:
            source_connection.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
            target.commit()


def _install_v3(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("DROP TABLE sdk_schema_meta")
        execute_schema(connection, SCHEMA)
        results = ResultsMixin()
        results.max_result_deliveries = 5
        results._init_results(connection)
        NotificationsMixin._init_notifications(connection)
        # The clock row must exist before tracked writes begin.  Triggers are
        # installed only after every component-owned SDK table is present.
        connection.execute("INSERT INTO sdk_storage_clock VALUES(1,0)")
        initialize_storage_tracking(connection)
        connection.execute(
            "INSERT INTO sdk_schema_meta VALUES('orchestrator',?)",
            (ORCHESTRATOR_SCHEMA_VERSION,),
        )
        connection.execute(
            "INSERT INTO sdk_storage_identity VALUES(1,?,?,?)",
            (uuid.uuid4().hex, uuid.uuid4().hex, time.time()),
        )
        # Legacy rows have no reliable creation time.  Leave retention times
        # unknown instead of fabricating age metadata.
        connection.execute("DELETE FROM sdk_retention_times")
        connection.execute(
            "INSERT INTO sdk_event_watermarks(run_id,high_water,expired_through) "
            "SELECT r.run_id,COALESCE(MAX(e.sequence),0),0 FROM sdk_runs r "
            "LEFT JOIN sdk_events e ON e.run_id=r.run_id GROUP BY r.run_id"
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def _convert_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    where: str,
    parameters: tuple[Any, ...],
    source: Path,
    lease: Lease,
    failpoint: _Failpoint | None,
) -> int:
    converted = 0
    after_rowid = 0
    while True:
        lease.check(source)
        rows = connection.execute(
            f"SELECT rowid,{column} FROM {table} "
            f"WHERE rowid>? AND ({where}) ORDER BY rowid LIMIT ?",
            (after_rowid, *parameters, _BATCH_SIZE),
        ).fetchall()
        if not rows:
            return converted
        connection.execute("BEGIN IMMEDIATE")
        try:
            for rowid, raw in rows:
                after_rowid = rowid
                if raw is None:
                    continue
                logical = decode_value(connection, raw)
                encoded = encode_value(connection, logical)
                if canonical(decode_value(connection, encoded)) != canonical(logical):
                    raise StorageMigrationError(
                        f"logical validation failed for {table}.{column} rowid {rowid}"
                    )
                connection.execute(
                    f"UPDATE {table} SET {column}=? WHERE rowid=?", (encoded, rowid)
                )
                converted += 1
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        lease.check(source)
        _hit(failpoint, f"after_batch:{table}.{column}")


def _convert_legacy_values(
    connection: sqlite3.Connection,
    source: Path,
    lease: Lease,
    failpoint: _Failpoint | None,
) -> int:
    total = 0
    selected_roots = (
        "section='root' AND item_key IN ('application_state','input','definition')"
    )
    total += _convert_column(
        connection, "sdk_run_items", "value", selected_roots, (), source, lease, failpoint
    )
    total += _convert_column(
        connection, "sdk_run_history", "value", selected_roots, (), source, lease, failpoint
    )
    total += _convert_column(
        connection, "sdk_events", "payload", "1", (), source, lease, failpoint
    )
    for column in ("decision", "manifest", "application_state"):
        total += _convert_column(
            connection,
            "sdk_recoveries",
            column,
            f"{column} IS NOT NULL",
            (),
            source,
            lease,
            failpoint,
        )
    return total


def _quick_validate(connection: sqlite3.Connection) -> None:
    rows = connection.execute("PRAGMA quick_check").fetchall()
    if [tuple(row) for row in rows] != [("ok",)]:
        raise StorageMigrationError(
            "target SQLite integrity check failed: " + "; ".join(str(row[0]) for row in rows)
        )
    _validate_current(connection)


def _report(
    operation: str,
    source: Path,
    destination: Path,
    before_bytes: int,
    required_bytes: int,
    source_version: int,
    converted_values: int = 0,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "source": str(source),
        "destination": str(destination),
        "before_bytes": before_bytes,
        "after_bytes": destination.stat().st_size,
        "space_precheck_bytes": required_bytes,
        "source_version": source_version,
        "target_version": ORCHESTRATOR_SCHEMA_VERSION,
        "from_schema": source_version,
        "to_schema": ORCHESTRATOR_SCHEMA_VERSION,
        "converted_values": converted_values,
        "source_unchanged": True,
        "automatic_activation": False,
        "automatic_cutover": False,
        "resumable": False,
        "limitation": (
            "This copy operation is not a resumable 134 GB migration; validate capacity "
            "and rehearse large production stores separately."
        ),
    }


def upgrade_storage(
    source: str | Path,
    destination: str | Path,
    *,
    lease: Lease,
    failpoint: _Failpoint | None = None,
) -> dict[str, Any]:
    """Copy an exact Orchestrator schema-v2 store into a fresh schema-v3 file."""

    if not isinstance(lease, Lease):
        raise TypeError("lease must be a maintenance Lease")
    source_path, destination_path = _paths(source, destination)
    lease.check(source_path)
    before_bytes = source_path.stat().st_size
    required_bytes = _space_precheck(source_path, destination_path)
    with closing(_open_read_only(source_path)) as connection:
        connection.execute("BEGIN")
        _validate_legacy(connection)
    _hit(failpoint, "after_source_validation")
    lease.check(source_path)

    converted = 0
    with _new_artifact(destination_path) as temporary:
        _backup(source_path, temporary)
        _hit(failpoint, "after_backup")
        lease.check(source_path)
        with closing(sqlite3.connect(temporary, timeout=30)) as target:
            target.row_factory = sqlite3.Row
            _install_v3(target)
            _hit(failpoint, "after_schema")
            converted = _convert_legacy_values(
                target, source_path, lease, failpoint
            )
            _hit(failpoint, "before_validation")
            _quick_validate(target)
            target.execute("PRAGMA journal_mode=DELETE")
            target.commit()
        lease.check(source_path)
        _hit(failpoint, "before_publish")
        lease.check(source_path)

    return _report(
        "upgrade",
        source_path,
        destination_path,
        before_bytes,
        required_bytes,
        2,
        converted,
    )


def compact_database(
    source: str | Path, destination: str | Path, lease: Lease
) -> dict[str, Any]:
    """Create a compact private copy of an exact current Orchestrator store."""

    if not isinstance(lease, Lease):
        raise TypeError("lease must be a maintenance Lease")
    source_path, destination_path = _paths(source, destination)
    lease.check(source_path)
    before_bytes = source_path.stat().st_size
    required_bytes = _space_precheck(source_path, destination_path)
    with closing(_open_read_only(source_path)) as connection:
        connection.execute("BEGIN")
        _validate_current(connection)
    lease.check(source_path)

    with _new_artifact(destination_path) as temporary:
        _backup(source_path, temporary)
        lease.check(source_path)
        with closing(sqlite3.connect(temporary, timeout=30)) as target:
            target.row_factory = sqlite3.Row
            sequences = {
                row[0]: row[1]
                for row in target.execute("SELECT name,seq FROM sqlite_sequence")
            }
            target.execute("PRAGMA journal_mode=DELETE")
            target.execute("VACUUM")
            for name, high_water in sequences.items():
                row = target.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name=?", (name,)
                ).fetchone()
                if row is None:
                    target.execute(
                        "INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)",
                        (name, high_water),
                    )
                elif row[0] < high_water:
                    target.execute(
                        "UPDATE sqlite_sequence SET seq=? WHERE name=?",
                        (high_water, name),
                    )
            target.commit()
            _quick_validate(target)
        lease.check(source_path)

    return _report(
        "compact",
        source_path,
        destination_path,
        before_bytes,
        required_bytes,
        ORCHESTRATOR_SCHEMA_VERSION,
    )


__all__ = ["StorageMigrationError", "compact_database", "upgrade_storage"]
