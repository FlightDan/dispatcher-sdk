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
from typing import Any, Iterator, Mapping
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
)
_COLUMNS = {
    "settlement_meta": [("singleton", "INTEGER", 0, 1), ("version", "INTEGER", 1, 0),
        ("source_id", "TEXT", 1, 0), ("kernel_path", "TEXT", 1, 0)],
    "settlement_records": [("execution_id", "TEXT", 1, 1), ("attempt", "INTEGER", 1, 2),
        ("fence", "INTEGER", 1, 3), ("lease_json", "TEXT", 1, 0), ("payload_kind", "TEXT", 1, 0),
        ("payload_json", "TEXT", 1, 0), ("state", "TEXT", 1, 0), ("evidence_json", "TEXT", 1, 0),
        ("revision", "INTEGER", 1, 0), ("created_at", "REAL", 1, 0), ("updated_at", "REAL", 1, 0)],
    "settlement_notes": [("sequence", "INTEGER", 0, 1), ("note_id", "TEXT", 1, 0),
        ("execution_id", "TEXT", 1, 0), ("attempt", "INTEGER", 1, 0), ("fence", "INTEGER", 1, 0),
        ("phase", "TEXT", 1, 0), ("evidence_json", "TEXT", 1, 0), ("created_at", "REAL", 1, 0)],
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
                    connection.execute(statement)
                connection.execute("INSERT INTO settlement_meta VALUES(1,2,?,?)", (self.source_id, self.kernel_path))
            self._validate(connection)

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

    def _validate(self, connection: sqlite3.Connection) -> None:
        objects = connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        expected = {("settlement_meta", "table"), ("settlement_records", "table"), ("settlement_pending", "index"),
            ("settlement_notes", "table"), ("settlement_notes_execution", "index")}
        if {(row[0], row[1]) for row in objects} != expected:
            raise SettlementBindingError("unsupported settlement journal schema")
        for table, expected_columns in _COLUMNS.items():
            columns = [(row[1], row[2], row[3], row[5]) for row in connection.execute(f"PRAGMA table_info({table})")]
            if columns != expected_columns:
                raise SettlementBindingError("unsupported settlement journal columns")
        rows = connection.execute("SELECT singleton,version,source_id,kernel_path FROM settlement_meta").fetchall()
        if len(rows) != 1 or tuple(rows[0]) != (1, 2, self.source_id, self.kernel_path):
            raise SettlementBindingError("settlement journal store/path binding differs")

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
             timeout_seconds: float = .1) -> dict[str, Any]:
        """Append a diagnostic receipt without changing result or execution authority.

        Each call creates a distinct note ID. The returned ID/sequence identify
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
        note_id, now = str(uuid4()), time.time()
        with self._connection(timeout_seconds, write=True) as connection:
            cursor = connection.execute("INSERT INTO settlement_notes(note_id,execution_id,attempt,fence,phase,evidence_json,created_at) "
                "VALUES(?,?,?,?,?,?,?)", (note_id, *key, phase, encoded, now))
            receipt = _note(connection.execute("SELECT * FROM settlement_notes WHERE sequence=?", (cursor.lastrowid,)).fetchone())
        return receipt

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
                    used = size(report) + 256
                    phase_truncated = size(marker) + used > max_bytes
                    if phase_truncated:
                        marker["phase"] = None
                    if phase_truncated or row["bytes"] + size(marker) + used > max_bytes:
                        note = marker
                    else:
                        full = connection.execute("SELECT * FROM settlement_notes WHERE sequence=?", (row["sequence"],)).fetchone()
                        note = _note(full)
                        check()
                    report["notes"].append(note)
                    report["cursor"] = row["sequence"]
                    if size(report) + 256 > max_bytes:
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

    def pending(self, limit: int = 50, *, timeout_seconds: float = .1) -> list[dict[str, Any]]:
        """Return at most ``limit`` obligations eligible for maintenance retry."""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer between 1 and 50")
        with self._connection(timeout_seconds) as connection:
            rows = connection.execute("SELECT * FROM settlement_records WHERE state IN ('pending','error') "
                "ORDER BY created_at,execution_id,attempt,fence LIMIT ?", (limit,)).fetchall()
            return [_record(row) for row in rows]

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
