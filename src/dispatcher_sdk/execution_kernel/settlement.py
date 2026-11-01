"""Durable result obligations, separate from Kernel and telemetry admission.

This journal records facts only. Its states do not authorize execution or claim
that the Kernel accepted a result; callers must establish that through Kernel
CAS before recording settlement evidence.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4

from .._sqlite_admission import retry_sqlite_admission
from .contracts import ExecutionLease, ExecutionResultV2, _json_value


class SettlementConflictError(RuntimeError):
    """A stable obligation or its settlement conflicts with persisted facts."""


class SettlementBindingError(ValueError):
    """The journal belongs to another Kernel store or uses an unknown schema."""


class SettlementBusyError(TimeoutError):
    """The independent journal could not obtain admission within its bound."""


_STATES = {"pending", "recorded", "superseded", "recovery_required", "error"}
_TERMINAL = {"recorded", "superseded"}
_MAX_RECOVERY_RECORD_BYTES = 256 * 1024
_MAX_RECOVERY_ID_BYTES = 4096
_SCHEMA = (
    "CREATE TABLE settlement_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
    "version INTEGER NOT NULL CHECK(version=2), source_id TEXT NOT NULL, kernel_path TEXT NOT NULL)",
    "CREATE TABLE settlement_records(execution_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>0), "
    "fence INTEGER NOT NULL CHECK(fence>0), lease_json TEXT NOT NULL, payload_kind TEXT NOT NULL "
    "CHECK(payload_kind IN ('result','deferred')), payload_json TEXT NOT NULL, state TEXT NOT NULL "
    "CHECK(state IN ('pending','recorded','superseded','recovery_required','error')), "
    "evidence_json TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), created_at REAL NOT NULL, "
    "updated_at REAL NOT NULL, PRIMARY KEY(execution_id,attempt,fence))",
    "CREATE INDEX settlement_pending ON settlement_records(state,created_at,execution_id,attempt,fence)",
    "CREATE TABLE settlement_notes(sequence INTEGER PRIMARY KEY AUTOINCREMENT, note_id TEXT NOT NULL UNIQUE, "
    "execution_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=0), fence INTEGER NOT NULL CHECK(fence>=0), "
    "phase TEXT NOT NULL, evidence_json TEXT NOT NULL, created_at REAL NOT NULL)",
    "CREATE INDEX settlement_notes_execution ON settlement_notes(execution_id,sequence)",
    "CREATE TABLE settlement_recovery_cursor(singleton INTEGER PRIMARY KEY CHECK(singleton=1), last_rowid INTEGER)",
)
_LIFECYCLE_RECEIPTS = (
    "CREATE TABLE settlement_lifecycle_receipts(store_id TEXT NOT NULL, outbox_sequence INTEGER NOT NULL "
    "CHECK(outbox_sequence>0), note_sequence INTEGER NOT NULL UNIQUE, "
    "PRIMARY KEY(store_id,outbox_sequence), FOREIGN KEY(note_sequence) REFERENCES settlement_notes(sequence))"
)
_COLUMNS = {
    "settlement_lifecycle_receipts": [("store_id", "TEXT", 1, 1), ("outbox_sequence", "INTEGER", 1, 2),
        ("note_sequence", "INTEGER", 1, 0)],
    "settlement_meta": [("singleton", "INTEGER", 0, 1), ("version", "INTEGER", 1, 0),
        ("source_id", "TEXT", 1, 0), ("kernel_path", "TEXT", 1, 0)],
    "settlement_records": [("execution_id", "TEXT", 1, 1), ("attempt", "INTEGER", 1, 2),
        ("fence", "INTEGER", 1, 3), ("lease_json", "TEXT", 1, 0), ("payload_kind", "TEXT", 1, 0),
        ("payload_json", "TEXT", 1, 0), ("state", "TEXT", 1, 0), ("evidence_json", "TEXT", 1, 0),
        ("revision", "INTEGER", 1, 0), ("created_at", "REAL", 1, 0), ("updated_at", "REAL", 1, 0)],
    "settlement_notes": [("sequence", "INTEGER", 0, 1), ("note_id", "TEXT", 1, 0),
        ("execution_id", "TEXT", 1, 0), ("attempt", "INTEGER", 1, 0), ("fence", "INTEGER", 1, 0),
        ("phase", "TEXT", 1, 0), ("evidence_json", "TEXT", 1, 0), ("created_at", "REAL", 1, 0)],
    "settlement_recovery_cursor": [("singleton", "INTEGER", 0, 1), ("last_rowid", "INTEGER", 0, 0)],
}


def _identifier(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _positive(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _json(value: Any) -> str:
    _json_value(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _key(identity: ExecutionLease | Mapping[str, Any], *, allow_unclaimed: bool = False) -> tuple[str, int, int]:
    values = identity.to_dict() if isinstance(identity, ExecutionLease) else identity
    if not isinstance(values, Mapping):
        raise TypeError("identity must be an ExecutionLease or identity mapping")
    if "identity" in values:
        values = values["identity"]
    execution_id = _identifier(values["execution_id"], "execution_id")
    attempt, fence = values["attempt"], values["fence"]
    minimum = 0 if allow_unclaimed else 1
    if any(type(value) is not int or value < minimum for value in (attempt, fence)):
        raise ValueError("attempt and fence must be nonnegative integers" if allow_unclaimed
                         else "attempt and fence must be positive integers")
    return execution_id, attempt, fence


def _record(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"])
    return {"identity": {"execution_id": row["execution_id"], "attempt": row["attempt"], "fence": row["fence"]},
        "lease": json.loads(row["lease_json"]), "result": payload if row["payload_kind"] == "result" else None,
        "deferred": payload if row["payload_kind"] == "deferred" else None, "state": row["state"],
        "evidence": json.loads(row["evidence_json"]), "revision": row["revision"],
        "created_at": row["created_at"], "updated_at": row["updated_at"]}


def _note(row: sqlite3.Row) -> dict[str, Any]:
    return {"note_id": row["note_id"], "sequence": row["sequence"],
        "identity": {"execution_id": row["execution_id"], "attempt": row["attempt"], "fence": row["fence"]},
        "phase": row["phase"], "evidence": json.loads(row["evidence_json"]), "created_at": row["created_at"]}


class SettlementJournal:
    """Full-sync SQLite facts bound to ``source_id`` and resolved Kernel path.

    Connections are operation-local; no Kernel, telemetry, or shared Python
    lock is acquired. BUSY/LOCKED and read-budget expiry raise visibly. Transient
    ``:memory:`` Kernels cannot offer this independent durable obligation store.
    """

    def __init__(self, path: str | Path, *, source_id: str, kernel_path: str | Path,
                 timeout_seconds: float = .1) -> None:
        self._bind(path, source_id=source_id, kernel_path=kernel_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection(timeout_seconds, write=True, initialize=True) as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not names:
                for statement in _SCHEMA:
                    connection.execute(statement.replace("CHECK(version=2)", "CHECK(version=4)"))
                connection.execute(_LIFECYCLE_RECEIPTS)
                connection.execute("INSERT INTO settlement_meta VALUES(1,4,?,?)", (self.source_id, self.kernel_path))
                connection.execute("INSERT INTO settlement_recovery_cursor VALUES(1,NULL)")
            version = self._validate(connection)
            if version == 2:
                raise SettlementBindingError("settlement journal v2 requires explicit copy upgrade")

    def _bind(self, path: str | Path, *, source_id: str, kernel_path: str | Path) -> None:
        self._readonly = False
        if str(path) == ":memory:" or str(kernel_path) == ":memory:":
            raise ValueError("settlement journal requires persistent filesystem paths")
        self.path = str(Path(path).expanduser().resolve())
        self.kernel_path = str(Path(kernel_path).expanduser().resolve())
        self.source_id = _identifier(source_id, "source_id")
        if self.path == self.kernel_path:
            raise SettlementBindingError("settlement journal must be separate from the Kernel")

    @classmethod
    def open_readonly(cls, path: str | Path, *, source_id: str, kernel_path: str | Path,
                      timeout_seconds: float = .1) -> SettlementJournal:
        """Validate existing receipts without creating or changing storage."""
        journal = cls.__new__(cls)
        journal._bind(path, source_id=source_id, kernel_path=kernel_path)
        journal._readonly = True
        with journal._connection(timeout_seconds):
            pass
        return journal

    @classmethod
    def open_existing(cls, path: str | Path, *, source_id: str, kernel_path: str | Path,
                      timeout_seconds: float = .1) -> SettlementJournal:
        """Open an existing v3 or v4 journal without upgrading storage."""
        journal = cls.__new__(cls)
        journal._bind(path, source_id=source_id, kernel_path=kernel_path)
        with journal._connection(timeout_seconds, write=True) as connection:
            if journal._validate(connection) not in (3, 4):
                raise SettlementBindingError('settlement journal v2 requires explicit copy upgrade')
        return journal

    @classmethod
    def upgrade_v2_copy(cls, source: str | Path, destination: str | Path, *, source_id: str,
                        kernel_path: str | Path, timeout_seconds: float = 5.0) -> SettlementJournal:
        """Copy an exact v2 journal to a new, validated v3 journal.

        The host must isolate source writers throughout copying and subsequent
        activation, preserve the source, and explicitly switch consumers to the
        destination. The copy does not retire or fence the source. The source's
        original Kernel path and source identity remain binding on the copy.
        Recovery reports oversized obligations as pending diagnostics; it does
        not decode them, infer their outcome, or remove them.
        """
        duration = _positive(timeout_seconds, "timeout_seconds")
        deadline = time.monotonic() + duration
        reader = cls.open_readonly(source, source_id=source_id, kernel_path=kernel_path,
                                   timeout_seconds=duration)
        target = cls.__new__(cls)
        target._bind(destination, source_id=source_id, kernel_path=kernel_path)
        if target.path == reader.path:
            raise SettlementBindingError("settlement upgrade requires a separate destination")
        with reader._connection(max(.001, deadline - time.monotonic())) as connection:
            if reader._validate(connection) != 2:
                raise SettlementBindingError("settlement upgrade requires schema v2")
        # Exclusive creation avoids overwriting an existing destination.
        with open(target.path, 'xb'):
            pass
        try:
            src = sqlite3.connect(Path(reader.path).as_uri() + '?mode=ro', uri=True, timeout=0)
            dst = sqlite3.connect(target.path, timeout=0)
            try:
                def progress(_status, _remaining, _total):
                    if time.monotonic() >= deadline:
                        raise SettlementBusyError('settlement upgrade budget elapsed')
                src.backup(dst, pages=64, progress=progress, sleep=.01)
            finally:
                dst.close()
                src.close()
            with target._connection(max(.001, deadline - time.monotonic()), write=True, initialize=True) as connection:
                if target._validate(connection) != 2:
                    raise SettlementBindingError('settlement copy is not schema v2')
                connection.execute('ALTER TABLE settlement_meta RENAME TO settlement_meta_v2')
                connection.execute(_SCHEMA[0].replace('CHECK(version=2)', 'CHECK(version=3)'))
                connection.execute('INSERT INTO settlement_meta SELECT singleton,3,source_id,kernel_path FROM settlement_meta_v2')
                connection.execute('DROP TABLE settlement_meta_v2')
                connection.execute(_SCHEMA[-1])
                connection.execute('INSERT INTO settlement_recovery_cursor VALUES(1,NULL)')
                target._validate(connection)
                if time.monotonic() >= deadline:
                    raise SettlementBusyError('settlement upgrade budget elapsed')
            return target
        except BaseException:
            Path(target.path).unlink(missing_ok=True)
            raise

    @classmethod
    def upgrade_v3_copy(cls, source: str | Path, destination: str | Path, *, source_id: str,
                        kernel_path: str | Path, timeout_seconds: float = 5.0) -> SettlementJournal:
        """Copy an isolated v3 journal into a new v4 journal; preserve source."""
        duration = _positive(timeout_seconds, "timeout_seconds")
        deadline = time.monotonic() + duration
        reader = cls.open_readonly(source, source_id=source_id, kernel_path=kernel_path, timeout_seconds=duration)
        target = cls.__new__(cls)
        target._bind(destination, source_id=source_id, kernel_path=kernel_path)
        if target.path == reader.path:
            raise SettlementBindingError("settlement upgrade requires a separate destination")
        with reader._connection(max(.001, deadline - time.monotonic())) as connection:
            if reader._validate(connection) != 3:
                raise SettlementBindingError("settlement upgrade requires schema v3")
        with open(target.path, 'xb'):
            pass
        try:
            src = sqlite3.connect(Path(reader.path).as_uri() + '?mode=ro', uri=True, timeout=0)
            dst = sqlite3.connect(target.path, timeout=0)
            try:
                def progress(_status, _remaining, _total):
                    if time.monotonic() >= deadline:
                        raise SettlementBusyError('settlement upgrade budget elapsed')
                src.backup(dst, pages=64, progress=progress, sleep=.01)
            finally:
                dst.close()
                src.close()
            with target._connection(max(.001, deadline - time.monotonic()), write=True, initialize=True) as connection:
                if target._validate(connection) != 3:
                    raise SettlementBindingError('settlement copy is not schema v3')
                connection.execute('ALTER TABLE settlement_meta RENAME TO settlement_meta_v3')
                connection.execute(_SCHEMA[0].replace('CHECK(version=2)', 'CHECK(version=4)'))
                connection.execute('INSERT INTO settlement_meta SELECT singleton,4,source_id,kernel_path FROM settlement_meta_v3')
                connection.execute('DROP TABLE settlement_meta_v3')
                connection.execute(_LIFECYCLE_RECEIPTS)
                target._validate(connection)
                if time.monotonic() >= deadline:
                    raise SettlementBusyError('settlement upgrade budget elapsed')
            return target
        except BaseException:
            Path(target.path).unlink(missing_ok=True)
            raise

    def _validate(self, connection: sqlite3.Connection) -> int:
        objects = connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        expected = {("settlement_meta", "table"), ("settlement_records", "table"), ("settlement_pending", "index"),
            ("settlement_notes", "table"), ("settlement_notes_execution", "index")}
        actual = {(row[0], row[1]) for row in objects}
        v3 = expected | {("settlement_recovery_cursor", "table")}
        v4 = v3 | {("settlement_lifecycle_receipts", "table")}
        if actual not in (expected, v3, v4):
            raise SettlementBindingError("unsupported settlement journal schema")
        for table, expected_columns in _COLUMNS.items():
            if (table, "table") not in actual:
                continue
            columns = [(row[1], row[2], row[3], row[5]) for row in connection.execute(f"PRAGMA table_info({table})")]
            if columns != expected_columns:
                raise SettlementBindingError("unsupported settlement journal columns")
        rows = connection.execute("SELECT singleton,version,source_id,kernel_path FROM settlement_meta").fetchall()
        version = 4 if actual == v4 else 3 if actual == v3 else 2
        if len(rows) != 1 or tuple(rows[0]) != (1, version, self.source_id, self.kernel_path):
            raise SettlementBindingError("settlement journal store/path binding differs")
        if version >= 3:
            rows = connection.execute("SELECT singleton,last_rowid FROM settlement_recovery_cursor").fetchall()
            if len(rows) != 1 or rows[0][0] != 1:
                raise SettlementBindingError("settlement recovery cursor differs")
            if rows[0][1] is not None and type(rows[0][1]) is not int:
                raise SettlementBindingError("settlement recovery cursor is invalid")
        if version == 4:
            definition = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='settlement_lifecycle_receipts'").fetchone()
            if definition is None or definition[0] != _LIFECYCLE_RECEIPTS:
                raise SettlementBindingError("settlement lifecycle receipt schema differs")
        return version

    @contextmanager
    def _connection(self, timeout_seconds: float, *, write: bool = False,
                    initialize: bool = False) -> Iterator[sqlite3.Connection]:
        if self._readonly and (write or initialize):
            raise SettlementBindingError("settlement inspector is read-only")
        deadline = time.monotonic() + _positive(timeout_seconds, "timeout_seconds")
        mode = "rwc" if initialize else "rw" if write else "ro"
        uri = Path(self.path).as_uri() + "?mode=" + mode
        connection = sqlite3.connect(uri, uri=True, timeout=0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        def admit(operation, *, commit=False):
            return retry_sqlite_admission(operation, deadline=deadline,
                expired=SettlementBusyError("settlement journal operation budget elapsed"),
                transaction_retained=(lambda: connection.in_transaction) if commit else None)
        try:
            admit(lambda: connection.execute("PRAGMA trusted_schema=OFF"))
            if write:
                mode = admit(lambda: connection.execute("PRAGMA journal_mode").fetchone()[0])
                if mode not in {"delete", "wal", "truncate", "persist"}:
                    raise SettlementBindingError("settlement journal requires persistent SQLite journaling")
                admit(lambda: connection.execute("PRAGMA synchronous=FULL"))
                if admit(lambda: connection.execute("PRAGMA synchronous").fetchone()[0]) != 2:
                    raise SettlementBindingError("SQLite refused full settlement durability")
            else:
                admit(lambda: connection.execute("PRAGMA query_only=ON"))
            connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
            admit(lambda: connection.execute("BEGIN IMMEDIATE" if write else "BEGIN"))
            if not initialize:
                admit(lambda: self._validate(connection))
            if time.monotonic() >= deadline:
                raise SettlementBusyError("settlement journal operation budget elapsed")
            yield connection
            if time.monotonic() >= deadline:
                raise SettlementBusyError("settlement journal operation budget elapsed")
            admit(connection.commit, commit=True)
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", None)
            busy = (isinstance(code, int) and code & 255 in {5, 6, 9}) or (
                code is None and any(token in str(exc).lower() for token in ("locked", "busy", "interrupted")))
            if busy:
                raise SettlementBusyError(str(exc)) from exc
            raise
        finally:
            # Closing rolls back an uncommitted write even after a failed COMMIT.
            connection.close()

    def record(self, lease: ExecutionLease, result: ExecutionResultV2 | Mapping[str, Any], *,
               evidence: dict[str, Any] | None = None, timeout_seconds: float = .1) -> dict[str, Any]:
        """Commit original facts and initial diagnostics atomically.

        Replay checks the original lease/payload and retains the first receipt,
        including its initial evidence or subsequent settlement evidence.
        """
        if type(lease) is not ExecutionLease:
            raise TypeError("lease must be an ExecutionLease")
        key = _key(lease)
        lease_json = _json(lease.to_dict())
        if type(result) is ExecutionResultV2:
            if (result.execution_id, result.attempt, result.fence) != key:
                raise SettlementConflictError("result identity differs from its lease")
            payload_kind, payload = "result", result.to_dict()
        elif type(result) is dict and set(result) == {"kind", "outcome"}:
            _identifier(result["kind"], "deferred kind")
            payload_kind, payload = "deferred", result
        else:
            raise TypeError("result must be ExecutionResultV2 or exact deferred kind/outcome mapping")
        payload_json = _json(payload)
        if evidence is not None and type(evidence) is not dict:
            raise TypeError("evidence must be a strict JSON object or None")
        evidence_json = _json({} if evidence is None else evidence)
        with self._connection(timeout_seconds, write=True) as connection:
            row = connection.execute("SELECT * FROM settlement_records WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone()
            if row is not None:
                if (row["lease_json"], row["payload_kind"], row["payload_json"]) != (lease_json, payload_kind, payload_json):
                    raise SettlementConflictError("settlement obligation contents differ")
            else:
                now = time.time()
                connection.execute("INSERT INTO settlement_records VALUES(?,?,?,?,?,?,'pending',?,1,?,?)",
                    (*key, lease_json, payload_kind, payload_json, evidence_json, now, now))
                row = connection.execute("SELECT * FROM settlement_records WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone()
            receipt = _record(row)
        return receipt

    def note(self, identity: ExecutionLease | Mapping[str, Any], phase: str, evidence: dict[str, Any], *,
             timeout_seconds: float = .1, note_id: str | None = None) -> dict[str, Any]:
        """Append a diagnostic receipt without changing result or execution authority.

        By default each call creates a distinct note ID. A supplied ID permits
        retry after an uncertain acknowledgement without duplicating a note.
        The returned ID/sequence identify
        that exact durable receipt after restart. Unclaimed identity zero is
        valid for diagnostic notes, while result obligations remain positive.
        """
        key = _key(identity, allow_unclaimed=True)
        _identifier(phase, "phase")
        if len(phase.encode("utf-8")) > 128:
            raise ValueError("phase must be at most 128 bytes")
        if type(evidence) is not dict:
            raise TypeError("evidence must be a strict JSON object")
        encoded = _json(evidence)
        note_id = str(uuid4()) if note_id is None else _identifier(note_id, "note_id")
        now = time.time()
        with self._connection(timeout_seconds, write=True) as connection:
            row = connection.execute("SELECT * FROM settlement_notes WHERE note_id=?", (note_id,)).fetchone()
            if row is None:
                cursor = connection.execute("INSERT INTO settlement_notes(note_id,execution_id,attempt,fence,phase,evidence_json,created_at) "
                    "VALUES(?,?,?,?,?,?,?)", (note_id, *key, phase, encoded, now))
                row = connection.execute("SELECT * FROM settlement_notes WHERE sequence=?", (cursor.lastrowid,)).fetchone()
            elif (row["execution_id"], row["attempt"], row["fence"], row["phase"], row["evidence_json"]) != (*key, phase, encoded):
                raise SettlementConflictError("diagnostic note contents differ")
            receipt = _note(row)
        return receipt

    def lifecycle_note(self, identity: ExecutionLease | Mapping[str, Any], phase: str, evidence: dict[str, Any], *,
                       store_id: str, outbox_sequence: int, legacy_note_id: str | None = None,
                       timeout_seconds: float = .1) -> dict[str, Any]:
        """Record a Kernel outbox receipt in a namespace separate from note IDs."""
        deadline = time.monotonic() + _positive(timeout_seconds, 'timeout_seconds')
        key = _key(identity, allow_unclaimed=True)
        _identifier(store_id, "store_id")
        if legacy_note_id is not None:
            _identifier(legacy_note_id, "legacy_note_id")
        _identifier(phase, "phase")
        if len(phase) > 256:
            raise ValueError("phase must be at most 256 characters")
        if type(outbox_sequence) is not int or outbox_sequence <= 0:
            raise ValueError("outbox_sequence must be a positive integer")
        if type(evidence) is not dict:
            raise TypeError("evidence must be a strict JSON object")
        encoded = _json(evidence)
        with self._kernel_lifecycle_guard(deadline), self._connection(max(.000001, deadline - time.monotonic()), write=True) as connection:
            if self._validate(connection) != 4:
                raise SettlementBindingError("lifecycle receipts require explicit settlement v3 to v4 copy upgrade")
            retired = self._kernel_retired_watermark(store_id, key[0], deadline,
                event=(outbox_sequence, key, phase, encoded, legacy_note_id))
            if retired is not None and key[1:] <= retired:
                raise SettlementConflictError("lifecycle generation has been retired")
            existing = connection.execute("SELECT note_sequence FROM settlement_lifecycle_receipts WHERE store_id=? AND outbox_sequence=?", (store_id, outbox_sequence)).fetchone()
            if existing is None:
                for _ in range(16):
                    note_id = legacy_note_id if legacy_note_id is not None else str(uuid4())
                    cursor = connection.execute("INSERT INTO settlement_notes(note_id,execution_id,attempt,fence,phase,evidence_json,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(note_id) DO NOTHING", (note_id, *key, phase, encoded, time.time()))
                    if cursor.rowcount:
                        note_sequence = cursor.lastrowid
                        break
                    if legacy_note_id is not None:
                        raise SettlementConflictError("legacy lifecycle note ID already exists without a matching lifecycle receipt")
                else:
                    raise SettlementConflictError("could not allocate a unique lifecycle note ID")
                connection.execute("INSERT INTO settlement_lifecycle_receipts VALUES(?,?,?)", (store_id, outbox_sequence, note_sequence))
            else:
                note_sequence = existing['note_sequence']
            row = connection.execute("SELECT * FROM settlement_notes WHERE sequence=?", (note_sequence,)).fetchone()
            if row is None or (row['execution_id'], row['attempt'], row['fence'], row['phase'], row['evidence_json']) != (*key, phase, encoded):
                raise SettlementConflictError("lifecycle receipt contents differ or note is missing")
            return _note(row)

    @contextmanager
    def _kernel_lifecycle_guard(self, deadline: float) -> Iterator[None]:
        """Serialize Kernel retirement and journal receipt writes in one order.

        The connection reserves Kernel's writer slot but never changes Kernel
        data. It stays held through the separate journal commit, so a retire
        cannot pass the proof check before this receipt becomes visible.
        """
        if time.monotonic() >= deadline:
            raise SettlementBusyError('Kernel lifecycle proof budget elapsed')
        try:
            connection = sqlite3.connect(Path(self.kernel_path).as_uri() + '?mode=rw',
                uri=True, timeout=0, isolation_level=None)
        except sqlite3.Error as exc:
            raise SettlementBusyError('Kernel lifecycle proof unavailable') from exc
        try:
            connection.execute('PRAGMA trusted_schema=OFF')
            try:
                retry_sqlite_admission(lambda: connection.execute('BEGIN IMMEDIATE'),
                    deadline=deadline,
                    expired=SettlementBusyError('Kernel lifecycle proof budget elapsed'))
            except sqlite3.OperationalError as exc:
                raise SettlementBusyError('Kernel lifecycle proof unavailable') from exc
            yield
        finally:
            connection.rollback()
            connection.close()

    def _kernel_retired_watermark(self, store_id: str, execution_id: str, deadline: float, *, event=None):
        """Read retirement proof from the bound Kernel while journal writer is held."""
        if time.monotonic() >= deadline:
            raise SettlementBusyError("lifecycle retirement proof budget elapsed")
        try:
            connection = sqlite3.connect(Path(self.kernel_path).as_uri() + '?mode=ro', uri=True, timeout=0)
            try:
                connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
                connection.execute('PRAGMA query_only=ON')
                connection.execute('BEGIN')
                meta = connection.execute("SELECT component,schema_version FROM kernel_schema_meta").fetchall()
                identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchall()
                if meta != [('execution_kernel', 12)] or identity != [(store_id,)]:
                    raise SettlementBindingError("Kernel lifecycle retirement proof has wrong store or schema")
                row = connection.execute("SELECT attempt,fence FROM kernel_lifecycle_retired WHERE execution_id=?", (execution_id,)).fetchone()
                if event is not None:
                    sequence, key, phase, encoded, legacy_note_id = event
                    legacy_max = connection.execute("SELECT legacy_max_sequence FROM kernel_lifecycle_metadata WHERE singleton=1").fetchone()
                    if legacy_max is None or ((sequence <= legacy_max[0]) != (legacy_note_id is not None)):
                        raise SettlementConflictError("lifecycle event requires the correct legacy receipt mode")
                    source = connection.execute("SELECT p.execution_id,p.attempt,p.fence,o.phase,o.payload_json,o.event_id FROM kernel_lifecycle_outbox o JOIN kernel_lifecycle_producers p ON p.token=o.token WHERE o.sequence=?", (sequence,)).fetchone()
                    if (source is None or tuple(source[:4]) != (*key, phase) or source[4] is None or
                            _json(json.loads(source[4])) != encoded or
                            (legacy_note_id is not None and legacy_note_id != source[5])):
                        raise SettlementConflictError("lifecycle event does not match durable Kernel outbox")
                if time.monotonic() >= deadline:
                    raise SettlementBusyError("lifecycle retirement proof budget elapsed")
                return tuple(row) if row is not None else None
            finally:
                connection.close()
        except sqlite3.OperationalError as exc:
            raise SettlementBusyError("Kernel lifecycle retirement proof unavailable") from exc
        except sqlite3.DatabaseError as exc:
            raise SettlementBindingError("Kernel lifecycle retirement proof invalid") from exc

    def prune_lifecycle_notes(self, execution_id: str, attempt: int, fence: int, *, store_id: str,
                              limit: int = 128, timeout_seconds: float = .1) -> dict[str, Any]:
        """Remove only lifecycle receipts through a durably retired generation."""
        deadline = time.monotonic() + _positive(timeout_seconds, 'timeout_seconds')
        _identifier(execution_id, 'execution_id')
        _identifier(store_id, 'store_id')
        if (type(attempt) is not int or attempt < 0 or type(fence) is not int or fence < 0 or
                type(limit) is not int or not 1 <= limit <= 128):
            raise ValueError("invalid lifecycle note pruning bound")
        with self._kernel_lifecycle_guard(deadline), self._connection(max(.000001, deadline - time.monotonic()), write=True) as connection:
            if self._validate(connection) != 4:
                raise SettlementBindingError("lifecycle pruning requires settlement v4")
            retired = self._kernel_retired_watermark(store_id, execution_id, deadline)
            if retired is None or retired < (attempt, fence):
                raise SettlementConflictError("Kernel has not retired the requested generation")
            rows = connection.execute("SELECT r.outbox_sequence,r.note_sequence FROM settlement_lifecycle_receipts r JOIN settlement_notes n ON n.sequence=r.note_sequence WHERE r.store_id=? AND n.execution_id=? AND (n.attempt,n.fence)<= (?,?) ORDER BY r.outbox_sequence LIMIT ?", (store_id, execution_id, attempt, fence, limit)).fetchall()
            for row in rows:
                connection.execute('DELETE FROM settlement_lifecycle_receipts WHERE store_id=? AND outbox_sequence=?', (store_id, row['outbox_sequence']))
                connection.execute('DELETE FROM settlement_notes WHERE sequence=?', (row['note_sequence'],))
            more = connection.execute("SELECT r.outbox_sequence FROM settlement_lifecycle_receipts r JOIN settlement_notes n ON n.sequence=r.note_sequence WHERE r.store_id=? AND n.execution_id=? AND (n.attempt,n.fence)<= (?,?) LIMIT 1", (store_id, execution_id, attempt, fence)).fetchone() is not None
            return {'pruned': len(rows), 'more': more}

    def lifecycle_receipt_committed(self, identity: ExecutionLease | Mapping[str, Any], phase: str,
                                    evidence: dict[str, Any], *, store_id: str,
                                    outbox_sequence: int, timeout_seconds: float = .1) -> bool:
        """Read the exact v4 receiver receipt for a protected Kernel ACK."""
        key = _key(identity, allow_unclaimed=True)
        _identifier(store_id, 'store_id')
        _identifier(phase, 'phase')
        if type(outbox_sequence) is not int or outbox_sequence <= 0:
            raise ValueError('outbox_sequence must be a positive integer')
        if type(evidence) is not dict:
            raise TypeError('evidence must be a strict JSON object')
        encoded = _json(evidence)
        with self._connection(timeout_seconds) as connection:
            if self._validate(connection) != 4:
                raise SettlementBindingError('exact lifecycle receipts require settlement v4')
            row = connection.execute(
                'SELECT n.execution_id,n.attempt,n.fence,n.phase,n.evidence_json '
                'FROM settlement_lifecycle_receipts r JOIN settlement_notes n ON n.sequence=r.note_sequence '
                'WHERE r.store_id=? AND r.outbox_sequence=?',
                (store_id, outbox_sequence),
            ).fetchone()
            return row is not None and tuple(row) == (*key, phase, encoded)

    def reconcile_legacy_lifecycle_receipt(self, identity: ExecutionLease | Mapping[str, Any],
                                           phase: str, evidence: dict[str, Any], *, store_id: str,
                                           outbox_sequence: int, legacy_note_id: str,
                                           note_sequence: int, credential: Any,
                                           verify_host: Callable[[Any, dict[str, Any]], bool],
                                           timeout_seconds: float = .1) -> dict[str, Any]:
        """Bind a pre-v4 committed note only with independent host provenance.

        The host must attest that the exact note was the receiver's durable
        commit for this Kernel event. Equal content alone does not prove that.
        """
        deadline = time.monotonic() + _positive(timeout_seconds, 'timeout_seconds')
        key = _key(identity, allow_unclaimed=True)
        _identifier(store_id, 'store_id')
        _identifier(legacy_note_id, 'legacy_note_id')
        _identifier(phase, 'phase')
        if len(phase) > 256:
            raise ValueError('phase must be at most 256 characters')
        if (type(outbox_sequence) is not int or outbox_sequence <= 0 or
                type(note_sequence) is not int or note_sequence <= 0):
            raise ValueError('receipt sequences must be positive integers')
        if type(evidence) is not dict:
            raise TypeError('evidence must be a strict JSON object')
        if not callable(verify_host):
            raise TypeError('a trusted host verifier is required')
        encoded = _json(evidence)
        claim = {'kernel_path': self.kernel_path, 'settlement_path': self.path,
                 'kernel_store_id': store_id, 'kernel_outbox_sequence': outbox_sequence,
                 'event_id': legacy_note_id, 'execution_id': key[0], 'attempt': key[1],
                 'fence': key[2], 'phase': phase, 'evidence': json.loads(encoded),
                 'settlement_source_id': self.source_id, 'settlement_note_sequence': note_sequence,
                 'settlement_note_id': legacy_note_id}

        def authorize() -> None:
            if time.monotonic() >= deadline:
                raise SettlementBusyError('legacy lifecycle reconciliation budget elapsed')
            try:
                accepted = verify_host(credential, json.loads(_json(claim))) is True
            except Exception as exc:
                raise SettlementBindingError('host legacy receipt attestation unavailable') from exc
            if not accepted:
                raise SettlementBindingError('host legacy receipt attestation denied')
            if time.monotonic() >= deadline:
                raise SettlementBusyError('legacy lifecycle reconciliation budget elapsed')

        authorize()
        with self._kernel_lifecycle_guard(deadline), self._connection(max(.000001, deadline - time.monotonic()), write=True) as connection:
            if self._validate(connection) != 4:
                raise SettlementBindingError('legacy reconciliation requires settlement v4')
            retired = self._kernel_retired_watermark(store_id, key[0], deadline,
                event=(outbox_sequence, key, phase, encoded, legacy_note_id))
            if retired is not None and key[1:] <= retired:
                raise SettlementConflictError('lifecycle generation has been retired')
            note = connection.execute('SELECT * FROM settlement_notes WHERE sequence=?',
                                      (note_sequence,)).fetchone()
            if note is None or (note['note_id'], note['execution_id'], note['attempt'],
                                note['fence'], note['phase'], note['evidence_json']) != (
                                    legacy_note_id, *key, phase, encoded):
                raise SettlementConflictError('legacy lifecycle note does not match claim')
            existing = connection.execute(
                'SELECT note_sequence FROM settlement_lifecycle_receipts WHERE store_id=? AND outbox_sequence=?',
                (store_id, outbox_sequence)).fetchone()
            if existing is not None and existing['note_sequence'] != note_sequence:
                raise SettlementConflictError('lifecycle event already maps to another note')
            bound = connection.execute('SELECT store_id,outbox_sequence FROM settlement_lifecycle_receipts '
                'WHERE note_sequence=?', (note_sequence,)).fetchone()
            if bound is not None and tuple(bound) != (store_id, outbox_sequence):
                raise SettlementConflictError('legacy note already maps to another lifecycle event')
            authorize()
            if existing is None:
                connection.execute('INSERT INTO settlement_lifecycle_receipts VALUES(?,?,?)',
                                   (store_id, outbox_sequence, note_sequence))
            return _note(note)

    def record_supervisor_outcome(self, identity: ExecutionLease | Mapping[str, Any], outcome_json: str, *,
                                  timeout_seconds: float = .1) -> dict[str, Any]:
        """Record an observed POSIX worker packet, not settlement or cleanup.

        An exact pre-spawn intent must already exist. An oversized, invalid or
        unavailable write remains unknown; replay preserves the first packet.
        """
        return self._record_supervisor_facts(identity, outcome_json, None, timeout_seconds=timeout_seconds)

    def _record_supervisor_disposition(self, lease: ExecutionLease, outcome_json: str,
                                       disposition: dict[str, Any], *,
                                       timeout_seconds: float = .1) -> dict[str, Any]:
        """Store supervisor facts with the observation; grants no completion authority."""
        if type(lease) is not ExecutionLease:
            raise TypeError('supervisor disposition requires the original lease')
        if (type(disposition) is not dict or 'lease' in disposition or 'source' in disposition
                or disposition.get('worker_return') not in ('timely', 'indeterminate')):
            raise ValueError('invalid supervisor disposition')
        evidence = {'source': 'posix_supervisor', 'lease': lease.to_dict(), **disposition}
        if len(_json(evidence).encode('utf-8')) > 256 * 1024:
            raise ValueError('supervisor disposition exceeds its bounded limit')
        return self._record_supervisor_facts(lease, outcome_json, evidence, timeout_seconds=timeout_seconds)

    def _record_supervisor_facts(self, identity: ExecutionLease | Mapping[str, Any], outcome_json: str,
                                 disposition: dict[str, Any] | None, *, timeout_seconds: float) -> dict[str, Any]:
        key = _key(identity)
        if len(key[0].encode('utf-8')) > 4096 or type(outcome_json) is not str or len(outcome_json.encode('utf-8')) > 128 * 1024:
            raise ValueError('supervisor outcome exceeds its bounded limit')
        try:
            parsed = json.loads(outcome_json, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if type(parsed) is not dict:
                raise ValueError()
        except (ValueError, RecursionError):
            raise ValueError('supervisor outcome is invalid JSON') from None
        evidence = {'source': 'posix_supervisor_worker_packet', 'outcome_json': outcome_json}
        encoded = _json(evidence)
        if len(encoded.encode('utf-8')) > 256 * 1024:
            raise ValueError('supervisor outcome evidence exceeds its bounded limit')
        note_id = _json(['supervisor_outcome_observed', *key])
        with self._connection(timeout_seconds, write=True) as connection:
            if connection.execute("SELECT 1 FROM settlement_notes WHERE execution_id=? AND attempt=? AND fence=? AND phase='supervisor_spawn_intent' LIMIT 1", key).fetchone() is None:
                raise SettlementBindingError('exact supervisor spawn intent is unavailable')
            row = connection.execute('SELECT * FROM settlement_notes WHERE note_id=?', (note_id,)).fetchone()
            if row is None:
                cursor = connection.execute('INSERT INTO settlement_notes(note_id,execution_id,attempt,fence,phase,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
                    (note_id, *key, 'supervisor_outcome_observed', encoded, time.time()))
                row = connection.execute('SELECT * FROM settlement_notes WHERE sequence=?', (cursor.lastrowid,)).fetchone()
            elif (row['execution_id'], row['attempt'], row['fence'], row['phase'], row['evidence_json']) != (*key, 'supervisor_outcome_observed', encoded):
                raise SettlementConflictError('supervisor outcome differs from its original packet')
            if disposition is not None:
                phase = 'supervisor_disposition_observed'
                disposition_id = _json([phase, *key])
                disposition_json = _json(disposition)
                existing = connection.execute('SELECT * FROM settlement_notes WHERE note_id=?', (disposition_id,)).fetchone()
                if existing is None:
                    connection.execute('INSERT INTO settlement_notes(note_id,execution_id,attempt,fence,phase,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
                        (disposition_id, *key, phase, disposition_json, time.time()))
                elif (existing['execution_id'], existing['attempt'], existing['fence'], existing['phase'], existing['evidence_json']) != (*key, phase, disposition_json):
                    raise SettlementConflictError('supervisor disposition differs from original facts')
            return _note(row)

    def record_worker_tree_cleanup(self, identity: ExecutionLease | Mapping[str, Any], *,
                                   timeout_seconds: float = .1) -> dict[str, Any]:
        """Record the POSIX supervisor's containment observation, not its own reap."""
        key = _key(identity)
        if len(key[0].encode('utf-8')) > 4096:
            raise ValueError('execution identity exceeds its bounded limit')
        phase = 'worker_tree_cleanup_observed'
        encoded = _json({'state': 'confirmed', 'source': 'posix_supervisor_containment'})
        note_id = _json([phase, *key])
        with self._connection(timeout_seconds, write=True) as connection:
            if connection.execute("SELECT 1 FROM settlement_notes WHERE execution_id=? AND attempt=? AND fence=? AND phase='supervisor_spawn_intent' LIMIT 1", key).fetchone() is None:
                raise SettlementBindingError('exact supervisor spawn intent is unavailable')
            row = connection.execute('SELECT * FROM settlement_notes WHERE note_id=?', (note_id,)).fetchone()
            if row is None:
                cursor = connection.execute('INSERT INTO settlement_notes(note_id,execution_id,attempt,fence,phase,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
                    (note_id, *key, phase, encoded, time.time()))
                row = connection.execute('SELECT * FROM settlement_notes WHERE sequence=?', (cursor.lastrowid,)).fetchone()
            elif (row['execution_id'], row['attempt'], row['fence'], row['phase'], row['evidence_json']) != (*key, phase, encoded):
                raise SettlementConflictError('worker tree cleanup receipt conflicts with existing evidence')
            return _note(row)

    def inspect_notes(self, execution_id: str, *, after: int = 0, limit: int = 50,
                      max_bytes: int = 256 * 1024, timeout_seconds: float = .1) -> dict[str, Any]:
        """Read one bounded diagnostic page without loading oversized JSON.

        Oversized notes retain their ID, identity and cursor as explicit unknown
        markers. Notes, including historical attempts, carry no control rights.
        The single timeout covers connection admission, SQL and Python encoding.
        """
        started = time.monotonic()
        deadline = started + _positive(timeout_seconds, "timeout_seconds")
        _identifier(execution_id, "execution_id")
        if type(after) is not int or after < 0:
            raise ValueError("after must be a nonnegative integer")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer between 1 and 50")
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 256 * 1024:
            raise ValueError("max_bytes must be between 1024 and 262144")
        if len(execution_id) > max_bytes or len(json.dumps(execution_id, ensure_ascii=False).encode("utf-8")) + 768 > max_bytes:
            raise ValueError("execution_id exceeds the settlement inspection byte budget")
        report: dict[str, Any] = {"notes": [], "cursor": after, "has_more": False, "complete": True}
        encoded_note_bytes = 0

        def check():
            if time.monotonic() >= deadline:
                raise SettlementBusyError("settlement notes inspection budget elapsed")

        def size(value):
            length = 0
            encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
            for chunk in encoder.iterencode(value):
                check()
                length += len(chunk.encode("utf-8"))
                if length > max_bytes:
                    break
            check()
            return length

        def report_size():
            # Only the small page metadata changes as immutable notes append.
            # Re-encoding every prior note would make a bounded page quadratic.
            metadata = {**report, "notes": []}
            return size(metadata) + encoded_note_bytes + max(0, len(report["notes"]) - 1)

        try:
            check()
            with self._connection(max(.000001, deadline-time.monotonic())) as connection:
                rows = connection.execute("SELECT sequence,note_id,execution_id,attempt,fence,phase,created_at, "
                    "length(CAST(evidence_json AS BLOB)) AS bytes FROM settlement_notes "
                    "WHERE execution_id=? AND sequence>? ORDER BY sequence LIMIT ?", (execution_id, after, limit+1))
                for index, row in enumerate(rows):
                    check()
                    if index >= limit:
                        report["has_more"] = True
                        break
                    marker = {"note_id": row["note_id"], "sequence": row["sequence"],
                        "identity": {"execution_id": execution_id, "attempt": row["attempt"], "fence": row["fence"]},
                        "phase": row["phase"], "created_at": row["created_at"], "evidence": None,
                        "truncated": True, "unknown_reason": "settlement_notes_inspection_byte_limit"}
                    used = report_size() + 256
                    marker_bytes = size(marker)
                    phase_truncated = marker_bytes + used > max_bytes
                    if phase_truncated:
                        marker["phase"] = None
                        marker_bytes = size(marker)
                    if phase_truncated or row["bytes"] + marker_bytes + used > max_bytes:
                        note = marker
                    else:
                        full = connection.execute("SELECT * FROM settlement_notes WHERE sequence=?", (row["sequence"],)).fetchone()
                        note = _note(full)
                        check()
                    report["notes"].append(note)
                    report["cursor"] = row["sequence"]
                    note_bytes = marker_bytes if note is marker else size(note)
                    encoded_note_bytes += note_bytes
                    if report_size() + 256 > max_bytes:
                        encoded_note_bytes -= note_bytes
                        report["notes"].pop()
                        report["cursor"] = report["notes"][-1]["sequence"] if report["notes"] else after
                        report.update(complete=False, truncated=True, has_more=True,
                                      unknown_reason="settlement_notes_inspection_byte_limit")
                        break
                    if note is marker:
                        report.update(complete=False, truncated=True,
                                      unknown_reason="settlement_notes_inspection_byte_limit")
        except SettlementBusyError as error:
            report.update(complete=False, has_more=True, timed_out=True,
                          unknown_reason="settlement_notes_inspection_timeout", error=str(error))
        report["elapsed_seconds"] = time.monotonic() - started
        return report

    def _inspect_process_cleanup(self, identity: Mapping[str, Any], *,
                                 timeout_seconds: float = .1) -> dict[str, Any] | None:
        """Read the latest generation's cleanup note without paging unrelated notes."""
        key = _key(identity, allow_unclaimed=True)
        with self._connection(timeout_seconds) as connection:
            row = connection.execute(
                "SELECT sequence,length(CAST(evidence_json AS BLOB)) AS bytes "
                "FROM settlement_notes WHERE execution_id=? AND attempt=? AND fence=? "
                "AND phase='process_cleanup' ORDER BY sequence DESC LIMIT 1", key).fetchone()
            if row is None:
                return None
            if row["bytes"] > 4096:
                raise ValueError("process cleanup note exceeds inspection byte limit")
            try:
                note = _note(connection.execute(
                    "SELECT * FROM settlement_notes WHERE sequence=?", (row["sequence"],)).fetchone())
            except RecursionError as exc:
                raise ValueError("process cleanup evidence nesting exceeds decoder limit") from exc
            if type(note["evidence"]) is not dict:
                raise ValueError("process cleanup evidence must be an object")
            return note

    def scan_supervisor_cleanup(self, *, after: int = 0, limit: int = 50,
                                timeout_seconds: float = .1) -> dict[str, Any]:
        """Page persisted supervisor intents/registrations and latest cleanup fact.

        The cursor scans note sequence numbers, including unrelated notes. An
        unknown entry requires host investigation; this does not recover a
        process handle or authorize signaling a PID. For each exact generation,
        handler entry is reported only when its diagnostic receipt is durable;
        outcome is durable only when its settlement record is present. Neither
        fact proves cleanup or Kernel result acceptance. Volatile facts lost in
        a crash and registrations that never committed cannot be discovered.
        """
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("invalid cleanup scan cursor or limit")
        with self._connection(timeout_seconds) as connection:
            rows = connection.execute(
                "SELECT sequence,phase,attempt,fence,CASE WHEN length(CAST(execution_id AS BLOB))<=4096 "
                "THEN execution_id END AS execution_id FROM settlement_notes "
                "WHERE sequence>? ORDER BY sequence LIMIT ?", (after, limit + 1)).fetchall()
            page = rows[:limit]
            entries = []
            for row in page:
                if row["phase"] not in ("supervisor_spawn_intent", "supervisor_registered"):
                    continue
                if row["execution_id"] is None:
                    entries.append({"sequence": row["sequence"], "phase": row["phase"], "identity": None,
                                    "cleanup": "unknown", "worker_tree_cleanup": "unknown", "handler_entry": "unknown", "outcome": "unknown"})
                    continue
                identity = {"execution_id": row["execution_id"], "attempt": row["attempt"], "fence": row["fence"]}
                latest = connection.execute(
                    "SELECT CASE WHEN length(CAST(evidence_json AS BLOB))<=4096 THEN evidence_json END "
                    "FROM settlement_notes WHERE execution_id=? AND attempt=? AND fence=? "
                    "AND phase='process_cleanup' ORDER BY sequence DESC LIMIT 1", tuple(identity.values())).fetchone()
                state = "unknown"
                if latest is not None and latest[0] is not None:
                    try:
                        evidence = json.loads(latest[0])
                        if (type(evidence) is dict and evidence.get("state") == "confirmed"
                                and evidence.get("source") == "runtime_supervisor_reaped"):
                            state = "confirmed"
                    except (ValueError, RecursionError):
                        pass
                key = tuple(identity.values())
                tree = connection.execute(
                    "SELECT 1 FROM settlement_notes WHERE execution_id=? AND attempt=? AND fence=? "
                    "AND phase='worker_tree_cleanup_observed' AND evidence_json=? LIMIT 1",
                    (*key, _json({'state': 'confirmed', 'source': 'posix_supervisor_containment'}))).fetchone()
                entry = connection.execute(
                    "SELECT 1 FROM settlement_notes WHERE execution_id=? AND attempt=? AND fence=? "
                    "AND phase='handler_entered' LIMIT 1", key).fetchone()
                outcome = connection.execute(
                    "SELECT 1 FROM settlement_records WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone()
                entries.append({"sequence": row["sequence"], "phase": row["phase"], "identity": identity,
                                "cleanup": state, "worker_tree_cleanup": "confirmed" if tree else "unknown",
                                "handler_entry": "observed" if entry else "unknown",
                                "outcome": "durable" if outcome else "unknown"})
            return {"registrations": entries, "cursor": page[-1]["sequence"] if page else after,
                    "has_more": len(rows) > limit}

    def inspect_supervisor_handoff(self, identity: ExecutionLease | Mapping[str, Any], *,
                                   max_bytes: int = 256 * 1024, timeout_seconds: float = .1) -> dict[str, Any]:
        """Read exact-generation observations within the total UTF-8 JSON byte bound.

        Missing, malformed or oversized observations are unknown, not proof that
        a process, packet, or cleanup did not exist. A raw worker packet and
        supervisor disposition do not prove acceptance, outcome or cleanup.
        The host must independently verify any reconciliation decision.
        """
        key = _key(identity)
        if len(key[0].encode('utf-8')) > 4096:
            raise ValueError('execution identity exceeds its bounded limit')
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 1024 * 1024:
            raise ValueError('max_bytes must be between 1024 and 1048576')
        phases = {
            'spawn_intent': ('supervisor_spawn_intent', False),
            'worker_packet': ('supervisor_outcome_observed', True),
            'supervisor_disposition': ('supervisor_disposition_observed', True),
            'worker_tree_cleanup': ('worker_tree_cleanup_observed', True),
            'supervisor_reap': ('process_cleanup', False),
        }
        result = {'identity': dict(zip(('execution_id', 'attempt', 'fence'), key)),
                  'facts': {label: {'state': 'unknown', 'reason': 'observation_not_available'}
                            for label in phases}, 'authority': 'not_established'}
        def size() -> int:
            return len(_json(result).encode('utf-8'))
        if size() > max_bytes:
            result['identity'] = None
            result['unknown_reason'] = 'identity_exceeds_byte_budget'
            return result

        def valid(label: str, evidence: dict[str, Any]) -> bool:
            if label == 'spawn_intent':
                return evidence.get('source') == 'runtime_pre_spawn' and evidence.get('cleanup') == 'unknown'
            if label == 'worker_packet':
                if evidence.get('source') != 'posix_supervisor_worker_packet' or type(evidence.get('outcome_json')) is not str:
                    return False
                parsed = json.loads(evidence['outcome_json'], parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                return type(parsed) is dict
            if label == 'supervisor_disposition':
                if evidence.get('source') != 'posix_supervisor' or evidence.get('worker_return') not in ('timely', 'indeterminate'):
                    return False
                lease = ExecutionLease.from_dict(evidence.get('lease'))
                return (lease.execution_id, lease.attempt, lease.fence) == key
            if label == 'worker_tree_cleanup':
                return evidence.get('state') == 'confirmed' and evidence.get('source') == 'posix_supervisor_containment'
            return ((evidence.get('state'), evidence.get('source')) in {
                ('confirmed', 'runtime_supervisor_reaped'), ('not_invoked', 'runtime_admission_denied')})
        with self._connection(timeout_seconds) as connection:
            for label, (phase, canonical) in phases.items():
                if canonical:
                    selector = 'note_id=? AND execution_id=? AND attempt=? AND fence=? AND phase=?'
                    parameters = (_json([phase, *key]), *key, phase)
                else:
                    selector = 'execution_id=? AND attempt=? AND fence=? AND phase=?'
                    parameters = (*key, phase)
                row = connection.execute(
                    'SELECT sequence,length(CAST(evidence_json AS BLOB)) AS bytes FROM settlement_notes WHERE '
                    + selector + ' ORDER BY sequence DESC LIMIT 1', parameters).fetchone()
                fact = {'state': 'unknown', 'reason': 'observation_not_available'}
                if row is not None:
                    if row['bytes'] > max_bytes:
                        fact['reason'] = 'byte_budget_exceeded'
                    else:
                        encoded = connection.execute('SELECT evidence_json FROM settlement_notes WHERE sequence=?',
                                                     (row['sequence'],)).fetchone()[0]
                        try:
                            evidence = json.loads(encoded)
                            if type(evidence) is dict and valid(label, evidence):
                                _json(evidence)
                                fact = {'state': 'observed', 'sequence': row['sequence'], 'evidence': evidence}
                            else:
                                fact['reason'] = 'invalid_observation'
                        except (ValueError, TypeError, KeyError, RecursionError):
                            fact['reason'] = 'invalid_observation'
                result['facts'][label] = fact
                if size() > max_bytes:
                    result['facts'][label] = {'state': 'unknown', 'reason': 'byte_budget_exceeded'}
        return result

    def pending(self, limit: int = 50, *, timeout_seconds: float = .1,
                after: tuple[float, str, int, int] | None = None) -> list[dict[str, Any]]:
        """Return at most ``limit`` obligations eligible for maintenance retry."""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer between 1 and 50")
        if after is not None and (type(after) is not tuple or len(after) != 4
                or type(after[0]) not in (float, int) or not math.isfinite(after[0])
                or type(after[1]) is not str or not after[1]
                or any(type(value) is not int or value < 1 for value in after[2:])):
            raise ValueError("after must be a settlement cursor")
        with self._connection(timeout_seconds) as connection:
            where = "" if after is None else "AND (created_at,execution_id,attempt,fence) > (?,?,?,?) "
            rows = connection.execute("SELECT * FROM settlement_records WHERE state IN ('pending','error') "
                + where + "ORDER BY created_at,execution_id,attempt,fence LIMIT ?",
                (() if after is None else after) + (limit,)).fetchall()
            return [_record(row) for row in rows]

    def next_pending_round_robin(self, *, timeout_seconds: float = .1,
                                 max_record_bytes: int = _MAX_RECOVERY_RECORD_BYTES) -> dict[str, Any] | None:
        """Advance a durable scan position, without claiming or settling work.

        Oversized rows return a bounded diagnostic and remain unresolved. JSON
        decoding happens after the cursor transaction and is bounded by the
        caller's explicit size and time budgets. Rowids are scheduling hints;
        after VACUUM renumbers rows, subsequent scans still wrap and revisit
        every remaining row. Cursor movement never settles an obligation.
        """
        deadline = time.monotonic() + _positive(timeout_seconds, "timeout_seconds")
        if type(max_record_bytes) is not int or not 1 <= max_record_bytes < (1 << 63):
            raise ValueError('max_record_bytes must be a positive bounded integer')
        with self._connection(timeout_seconds, write=True) as connection:
            query = ("SELECT rowid, length(CAST(execution_id AS BLOB)) AS id_bytes, "
                     "length(CAST(lease_json AS BLOB))+length(CAST(payload_json AS BLOB))+"
                     "length(CAST(evidence_json AS BLOB))+length(CAST(execution_id AS BLOB)) AS total_bytes "
                     "FROM settlement_records WHERE state IN ('pending','error') ")
            order = "ORDER BY rowid LIMIT 1"
            row = connection.execute(query + "AND rowid > "
                "(SELECT last_rowid FROM settlement_recovery_cursor WHERE singleton=1) " + order).fetchone()
            if row is None:
                row = connection.execute(query + order).fetchone()
            if row is None:
                return None
            rowid = row['rowid']
            connection.execute("UPDATE settlement_recovery_cursor SET last_rowid=? WHERE singleton=1", (rowid,))
            oversized = row['total_bytes'] > max_record_bytes
            if oversized:
                identity = None
                if row['id_bytes'] <= _MAX_RECOVERY_ID_BYTES:
                    item = connection.execute('SELECT execution_id,attempt,fence FROM settlement_records WHERE rowid=?', (rowid,)).fetchone()
                    identity = {'execution_id': item[0], 'attempt': item[1], 'fence': item[2]}
                bounded = {'oversized': True, 'identity': identity, 'required_bytes': row['total_bytes']}
        if oversized:
            return bounded
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SettlementBusyError('settlement recovery read budget elapsed')
        with self._connection(remaining) as connection:
            bounded = connection.execute("SELECT * FROM settlement_records WHERE rowid=? AND state IN ('pending','error') "
                "AND length(CAST(lease_json AS BLOB))+length(CAST(payload_json AS BLOB))+"
                "length(CAST(evidence_json AS BLOB))+length(CAST(execution_id AS BLOB))<=?", (rowid, max_record_bytes)).fetchone()
        if bounded is None:
            return None
        record = _record(bounded)
        if time.monotonic() >= deadline:
            raise SettlementBusyError('settlement recovery decoding budget elapsed')
        return record

    def pending_script_output(self, *, timeout_seconds: float = .1) -> list[dict[str, Any]]:
        """Find one original artifact obligation, including settled executions.

        Cleanup confirmation belongs to the original outcome receipt. A result
        state or the existence of a file cannot substitute for that fact.
        Business payloads are neither loaded nor replayed by this maintenance.
        """
        with self._connection(timeout_seconds) as connection:
            row = connection.execute(
                "SELECT r.execution_id,r.attempt,r.fence, "
                "CASE WHEN length(CAST(json_extract(r.evidence_json,'$.script_output_recovery') AS BLOB))<=16384 "
                "THEN json_extract(r.evidence_json,'$.script_output_recovery') END AS marker "
                "FROM settlement_records r "
                "WHERE json_extract(r.evidence_json,'$.script_output_recovery.cleanup_confirmed')=1 "
                "AND NOT EXISTS (SELECT 1 FROM settlement_notes n WHERE "
                "n.execution_id=r.execution_id AND n.attempt=r.attempt AND n.fence=r.fence "
                "AND n.phase='script_output_saved') "
                "ORDER BY r.created_at,r.execution_id,r.attempt,r.fence LIMIT 1").fetchone()
            if row is None:
                return []
            if row["marker"] is None:
                raise SettlementBindingError("script output identity exceeds its fact bound")
            return [{"identity": {"execution_id": row["execution_id"],
                                  "attempt": row["attempt"], "fence": row["fence"]},
                     "evidence": {"script_output_recovery": json.loads(row["marker"])}}]

    def record_script_output(self, identity: ExecutionLease | Mapping[str, Any],
                             evidence: dict[str, Any], *, timeout_seconds: float = .1) -> dict[str, Any]:
        """Retain the first bounded post-containment artifact fact exactly once."""
        key = _key(identity)
        encoded = _json(evidence)
        if len(encoded.encode("utf-8")) > 4096:
            raise ValueError("script output fact exceeds 4096 bytes")
        with self._connection(timeout_seconds, write=True) as connection:
            previous = connection.execute(
                "SELECT * FROM settlement_notes WHERE execution_id=? AND attempt=? AND fence=? "
                "AND phase='script_output_saved' ORDER BY sequence LIMIT 1", key).fetchone()
            if previous is not None:
                return _note(previous)
            marker = connection.execute(
                "SELECT json_extract(evidence_json,'$.script_output_recovery.cleanup_confirmed') "
                "FROM settlement_records WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone()
            if marker is None or marker[0] != 1:
                raise SettlementConflictError("original script containment confirmation is unavailable")
            cursor = connection.execute(
                "INSERT INTO settlement_notes(note_id,execution_id,attempt,fence,phase,evidence_json,created_at) "
                "VALUES(?,?,?,?,?,?,?)", (str(uuid4()), *key, "script_output_saved", encoded, time.time()))
            return _note(connection.execute("SELECT * FROM settlement_notes WHERE sequence=?",
                                           (cursor.lastrowid,)).fetchone())

    def inspect_script_output(self, identity: Mapping[str, Any], *,
                              timeout_seconds: float = .1) -> dict[str, Any] | None:
        """Read one saved-output fact independently of diagnostic pagination."""
        key = _key(identity)
        with self._connection(timeout_seconds) as connection:
            row = connection.execute(
                "SELECT sequence,note_id,execution_id,attempt,fence,phase,created_at, "
                "CASE WHEN length(CAST(evidence_json AS BLOB))<=4096 THEN evidence_json END AS evidence_json "
                "FROM settlement_notes WHERE execution_id=? AND attempt=? AND fence=? "
                "AND phase='script_output_saved' ORDER BY sequence LIMIT 1", key).fetchone()
            if row is None:
                return None
            if row["evidence_json"] is None:
                raise SettlementBindingError("saved output fact exceeds its inspection bound")
            return _note(row)

    def settle(self, identity: ExecutionLease | Mapping[str, Any], state: str, evidence: Mapping[str, Any], *,
               timeout_seconds: float = .1, expected_revision: int | None = None) -> dict[str, Any]:
        """CAS settlement facts; resolved rows permit only exact replay.

        Passing an entire returned record uses its revision as the expected
        revision. Evidence is strict JSON and retained in full, including raw
        control errors. ``error`` remains eligible for maintenance retry.
        """
        key = _key(identity)
        if state not in _STATES:
            raise ValueError("unsupported settlement state")
        if type(evidence) is not dict:
            raise TypeError("evidence must be a strict JSON object")
        encoded = _json(evidence)
        if expected_revision is None and isinstance(identity, Mapping):
            expected_revision = identity.get("revision")
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision <= 0):
            raise ValueError("expected_revision must be a positive integer")
        with self._connection(timeout_seconds, write=True) as connection:
            row = connection.execute("SELECT * FROM settlement_records WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone()
            if row is None:
                raise SettlementConflictError("settlement obligation does not exist")
            if (row["state"], row["evidence_json"]) == (state, encoded):
                return _record(row)
            if row["state"] in _TERMINAL or (expected_revision is not None and row["revision"] != expected_revision):
                raise SettlementConflictError("settlement state/revision CAS differs")
            cursor = connection.execute("UPDATE settlement_records SET state=?,evidence_json=?,revision=revision+1,updated_at=? "
                "WHERE execution_id=? AND attempt=? AND fence=? AND revision=?",
                (state, encoded, time.time(), *key, row["revision"]))
            if cursor.rowcount != 1:
                raise SettlementConflictError("settlement revision CAS failed")
            return _record(connection.execute("SELECT * FROM settlement_records WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone())

    def inspect(self, execution_id: str, *, timeout_seconds: float = .1,
                limit: int = 50, max_bytes: int = 256 * 1024) -> list[dict[str, Any]]:
        """Bound diagnostic loading without truncating the stored obligation.

        Oversized rows return identity/state and an explicit unknown receipt.
        ``more=True`` on the last receipt signals additional generations.
        Maintenance uses ``pending`` to obtain the exact original facts.
        """
        _identifier(execution_id, "execution_id")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer between 1 and 50")
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 256 * 1024:
            raise ValueError("max_bytes must be between 1024 and 262144")
        identity_bytes = len(execution_id.encode("utf-8")) + 512
        if identity_bytes > max_bytes:
            raise ValueError("execution_id exceeds the settlement inspection byte budget")
        with self._connection(timeout_seconds) as connection:
            rows = connection.execute("SELECT execution_id,attempt,fence,state,revision, "
                "length(CAST(lease_json AS BLOB))+length(CAST(payload_json AS BLOB))+length(CAST(evidence_json AS BLOB)) AS bytes "
                "FROM settlement_records WHERE execution_id=? ORDER BY attempt,fence LIMIT ?", (execution_id, limit + 1)).fetchall()
            report: list[dict[str, Any]] = []
            remaining = max_bytes
            for row in rows[:limit]:
                if identity_bytes > remaining:
                    report[-1].update(more=True, unknown_reason="settlement_inspection_byte_limit")
                    break
                key = (row["execution_id"], row["attempt"], row["fence"])
                # Reserve space for receipt keys/timestamps and UTF-8 identity.
                needed = row["bytes"] + len(execution_id.encode("utf-8")) + 1024
                if needed > remaining:
                    report.append({"identity": dict(zip(("execution_id", "attempt", "fence"), key)),
                        "state": row["state"], "revision": row["revision"], "truncated": True,
                        "unknown_reason": "settlement_inspection_byte_limit"})
                    remaining -= identity_bytes
                else:
                    full = connection.execute("SELECT * FROM settlement_records WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone()
                    report.append(_record(full))
                    remaining -= needed
            if len(rows) > limit:
                report[-1]["more"] = True
            return report


def merge_script_output(report: dict[str, Any], fact: dict[str, Any]) -> None:
    """Merge a persisted saved-byte floor without adding duplicate counters.

    File size proves retained bytes. It does not prove when those bytes were
    emitted, that telemetry flushed, or that any material progress occurred.
    Collector timestamps continue to describe only their captured activity.
    """
    evidence = fact["evidence"]
    for stream in ("stdout", "stderr"):
        saved = evidence.get("streams", {}).get(stream, {})
        output = report.setdefault("output", {}).setdefault(stream, {})
        count = saved.get("saved_bytes")
        if type(count) is not int or count < 0:
            output["saved_output_unknown_reason"] = saved.get("unknown_reason", "artifact_fact_unavailable")
            report["complete"] = False
            continue
        metric = report.setdefault("metrics", {}).setdefault(
            stream + "_bytes", {"count": 0, "first_at": None, "last_at": None})
        collected_count = metric["count"]
        metric["count"] = max(collected_count, count)
        output.update(known=True, first_missing=metric.get("first_at") is None,
                      saved_bytes=count, saved_at=evidence.get("sampled_at"),
                      saved_path=saved.get("path"), count_basis="max_collected_and_saved_bytes")
        if count > collected_count:
            output["emission_timing_complete"] = False
            report["complete"] = False
            report.setdefault("unknown_reason", "script_output_timing_incomplete")
    report["script_output_fact"] = {"note_id": fact["note_id"],
        "identity": fact["identity"], "source": evidence.get("source"),
        "cleanup_confirmed": evidence.get("cleanup_confirmed"),
        "persisted_at": fact["created_at"]}


def merge_diagnostic_notes(report: dict[str, Any], notes: dict[str, Any], *,
                           process_freshness: float) -> None:
    """Merge persisted observation facts without changing Kernel authority."""
    report["diagnostics"] = notes
    if not notes["complete"] or notes["has_more"]:
        report.update(complete=False, unknown_reason="diagnostic_query_incomplete")
    identity = report.get("identity") or report.get("execution") or {}
    for note in notes["notes"]:
        if (note["identity"]["attempt"], note["identity"]["fence"]) != (
                identity.get("attempt"), identity.get("fence")):
            continue
        evidence = note.get("evidence") or {}
        captured_at = evidence.get("captured_at", evidence.get("observed_at", note["created_at"]))
        phases = report.setdefault("phases", [])
        if not any(item.get("phase") == note.get("phase") for item in phases):
            phases.append({**note["identity"], "phase": note["phase"],
                "captured_at": captured_at,
                "persisted_at": note["created_at"], "details": evidence,
                "diagnostic_note_id": note["note_id"]})
        if evidence.get("telemetry_incomplete") is True:
            report.update(complete=False, unknown_reason="telemetry_collection_incomplete")
        if note.get("phase") == "handler_entered" and evidence.get("worker_pid") is not None:
            processes = report.setdefault("processes", [])
            if not any(item.get("process_id") == "worker" for item in processes):
                age = time.time() - captured_at
                fresh = 0 <= age <= process_freshness
                processes.append({**note["identity"], "process_id": "worker", "role": "worker",
                    "state": "alive" if fresh else "unknown", "last_observed_state": "alive",
                    "observed_at": captured_at,
                    "persisted_at": note["created_at"], "registration": {"pid": evidence["worker_pid"],
                    "birth_identity": evidence.get("birth_identity"), "namespace": evidence.get("namespace"),
                    "source": "worker_self_report"}, "evidence": evidence.get("process_evidence", {}),
                    "unknown_reason": None if fresh else "process_observation_stale"})
        if note.get("phase") == "process_cleanup" and evidence.get("state") == "confirmed":
            for process in report.get("processes", []):
                if process.get("process_id") == "worker":
                    process.update(state="exited", last_observed_state="exited", observed_at=captured_at,
                        evidence={"source": "runtime_supervisor_reaped", "cleanup": "confirmed",
                        "diagnostic_note_id": note["note_id"]}, unknown_reason=None)
