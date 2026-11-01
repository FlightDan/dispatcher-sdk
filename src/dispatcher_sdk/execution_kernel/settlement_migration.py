"""Explicit host-authorized settlement copy; this does not activate either store."""
from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Any, Callable

from .settlement import SettlementBindingError, SettlementBusyError, SettlementJournal, _SCHEMA, _identifier, _positive


def copy_rebind_settlement(source: str | Path, destination: str | Path, *,
                           source_kernel_path: str | Path, destination_kernel_path: str | Path,
                           source_id: str, operation_id: str, credential: Any,
                           verify_host: Callable[[Any, dict[str, Any]], bool],
                           timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Copy v2/v3/v4 facts, bound to a separately copied Kernel.

    The trusted verifier must independently establish the exact Kernel copy
    relationship and continuous exclusion of all relevant writers, including
    throughout later cutover. This function neither fences writers nor activates
    the destination. An existing destination always fails closed, including
    after a lost acknowledgement; it must be reconciled by the host.
    """
    duration = _positive(timeout_seconds, 'timeout_seconds')
    deadline = time.monotonic() + duration
    source_id = _identifier(source_id, 'source_id')
    operation_id = _identifier(operation_id, 'operation_id')
    if len(operation_id.encode('utf-8')) > 4096 or len(source_id.encode('utf-8')) > 4096:
        raise ValueError('migration identity exceeds bound')
    if not callable(verify_host):
        raise TypeError('a trusted host verifier is required')
    destination_path = Path(destination).expanduser()
    # Resolve the parent only: resolving the leaf follows a dangling symlink
    # and would publish through an already occupied destination name.
    destination_path = destination_path.parent.resolve() / destination_path.name
    paths = [Path(source).expanduser().resolve(), destination_path,
             Path(source_kernel_path).expanduser().resolve(),
             Path(destination_kernel_path).expanduser().resolve()]
    if len(set(paths)) != 4:
        raise SettlementBindingError('migration paths must be distinct')
    src, dst, old_kernel, new_kernel = paths
    if any(str(p) == ':memory:' for p in (source, destination, source_kernel_path, destination_kernel_path)):
        raise ValueError('migration requires persistent paths')
    for path in (src, old_kernel, new_kernel):
        if not path.is_file():
            raise SettlementBindingError('migration source and Kernel files must exist')
    if any(os.path.samefile(a, b) for i, a in enumerate((src, old_kernel, new_kernel))
           for b in (src, old_kernel, new_kernel)[i + 1:]):
        raise SettlementBindingError('migration files must not alias')
    if os.path.lexists(dst):
        raise FileExistsError('settlement destination exists; outcome requires host reconciliation')
    reader = SettlementJournal.open_readonly(src, source_id=source_id, kernel_path=old_kernel,
                                              timeout_seconds=duration)
    with reader._connection(max(.001, deadline - time.monotonic())) as connection:
        version = reader._validate(connection)
    claim = {'operation_id': operation_id, 'source': str(src), 'destination': str(dst),
             'source_kernel_path': str(old_kernel), 'destination_kernel_path': str(new_kernel),
             'source_id': source_id, 'source_version': version, 'target_version': max(3, version)}

    def authorize() -> None:
        if time.monotonic() >= deadline:
            raise SettlementBusyError('settlement migration budget elapsed')
        try:
            accepted = verify_host(credential, dict(claim)) is True
        except Exception as exc:
            raise SettlementBindingError('host authorization unavailable') from exc
        if not accepted:
            raise SettlementBindingError('host authorization denied')
        if time.monotonic() >= deadline:
            raise SettlementBusyError('settlement migration budget elapsed')

    authorize()
    fd, name = tempfile.mkstemp(prefix='.settlement-copy-', dir=dst.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with closing(sqlite3.connect(src.as_uri() + '?mode=ro', uri=True, timeout=0)) as source_db:
            with closing(sqlite3.connect(temporary, timeout=0)) as target_db:
                def progress(_status: int, _remaining: int, _total: int) -> None:
                    if time.monotonic() >= deadline:
                        raise SettlementBusyError('settlement migration budget elapsed')
                source_db.backup(target_db, pages=64, progress=progress, sleep=.01)
        target = SettlementJournal.__new__(SettlementJournal)
        target._bind(temporary, source_id=source_id, kernel_path=old_kernel)
        with target._connection(max(.001, deadline - time.monotonic()), write=True, initialize=True) as db:
            if target._validate(db) != version:
                raise SettlementBindingError('source schema changed during migration')
            if version == 2:
                db.execute('ALTER TABLE settlement_meta RENAME TO settlement_meta_v2')
                db.execute(_SCHEMA[0].replace('CHECK(version=2)', 'CHECK(version=3)'))
                db.execute('INSERT INTO settlement_meta SELECT singleton,3,source_id,kernel_path FROM settlement_meta_v2')
                db.execute('DROP TABLE settlement_meta_v2')
                db.execute(_SCHEMA[-1])
                db.execute('INSERT INTO settlement_recovery_cursor VALUES(1,NULL)')
            db.execute('UPDATE settlement_meta SET kernel_path=? WHERE singleton=1', (str(new_kernel),))
            target.kernel_path = str(new_kernel)
            target._validate(db)
            if time.monotonic() >= deadline:
                raise SettlementBusyError('settlement migration budget elapsed')
        with open(temporary, 'r+b') as artifact:
            os.fsync(artifact.fileno())
        authorize()
        # A hard link publishes a fully formed file without replacing any target.
        os.link(temporary, dst)
        if os.name == 'posix':
            directory = os.open(dst.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return {**claim, 'automatic_activation': False, 'source_preserved': True}
    finally:
        temporary.unlink(missing_ok=True)
