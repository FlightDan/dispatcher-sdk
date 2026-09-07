"""Opt-in, independently versioned cancellation evidence; never execution authority."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
import uuid

from ..durability import Durability, configure_sqlite_connection, validate_durability
from .contracts import ExecutionSnapshot, _json_value


CANCELLATION_SCHEMA_VERSION = 1
_META = """CREATE TABLE cancellation_meta (
 version INTEGER NOT NULL CHECK(version=1), source_id TEXT NOT NULL,
 kernel_path TEXT NOT NULL)"""
_REQUESTS = """CREATE TABLE cancellation_requests (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, receipt_id TEXT NOT NULL UNIQUE,
 execution_id TEXT NOT NULL, command_digest TEXT NOT NULL,
 attempt INTEGER NOT NULL, fence INTEGER NOT NULL, expected_revision INTEGER NOT NULL,
 reason TEXT NOT NULL, isolation_mode TEXT NOT NULL, requested_at REAL NOT NULL)"""
_STAGES = """CREATE TABLE cancellation_stages (
 receipt_id TEXT NOT NULL REFERENCES cancellation_requests(receipt_id),
 stage TEXT NOT NULL, evidence TEXT NOT NULL, PRIMARY KEY(receipt_id,stage))"""
_INDEX = """CREATE INDEX cancellation_generation ON cancellation_requests
 (execution_id,command_digest,attempt,fence,sequence)"""
_OBJECTS = {"cancellation_meta": _META, "cancellation_requests": _REQUESTS,
            "cancellation_stages": _STAGES, "cancellation_generation": _INDEX}
_PHASES = {"authority_revoked", "process_cleanup", "remote_cleanup", "failure"}


def _validate_evidence(stage: str, evidence: Any, request=None) -> None:
    """A valid SQLite layout does not imply valid receipt payloads."""
    if type(stage) is not str or stage not in _PHASES or type(evidence) is not dict:
        raise ValueError("invalid cancellation evidence phase")
    _json_value(evidence)
    if stage == "authority_revoked":
        if (set(evidence) != {"state", "execution_revision", "execution_state", "attempt", "fence"}
                or evidence["state"] != "confirmed"
                or type(evidence["execution_state"]) is not str
                or evidence["execution_state"] not in {"cancelled", "recovery_required"}
                or any(type(evidence[key]) is not int or evidence[key] < 0
                       for key in ("execution_revision", "attempt", "fence"))):
            raise ValueError("invalid cancellation authority evidence")
        if request is not None and (evidence["attempt"], evidence["fence"]) != (request["attempt"], request["fence"]):
            raise ValueError("cancellation authority evidence belongs to another generation")
    elif stage == "process_cleanup":
        allowed = {"runtime_supervisor_reaped": "confirmed", "execution_never_claimed": "not_applicable",
                   "thread_authority_is_not_thread_termination": "not_applicable",
                   "no_local_supervisor_evidence": "unknown"}
        if (set(evidence) != {"state", "code"} or type(evidence["code"]) is not str
                or evidence["code"] not in allowed or allowed[evidence["code"]] != evidence["state"]):
            raise ValueError("invalid cancellation process evidence")
        if request is not None:
            if evidence["code"] == "execution_never_claimed" and request["attempt"] != 0:
                raise ValueError("claimed execution cannot have never-claimed evidence")
            if evidence["code"] == "runtime_supervisor_reaped" and request["isolation_mode"] != "process":
                raise ValueError("process evidence from a thread-only runtime")
    elif stage == "remote_cleanup":
        if (set(evidence) != {"state", "code", "reports"}
                or type(evidence["state"]) is not str
                or evidence["state"] not in {"confirmed", "unknown", "pending"}
                or evidence["code"] != "sandbox_cleanup_checked" or type(evidence["reports"]) is not list):
            raise ValueError("invalid cancellation remote evidence")
        for item in evidence["reports"]:
            if (type(item) is not dict or type(item.get("cleanup_confirmed")) is not bool
                    or not isinstance(item.get("execution_id"), (str, type(None)))):
                raise ValueError("invalid cancellation cleanup report")
        if evidence["state"] == "confirmed" and (not evidence["reports"]
                or not all(item["cleanup_confirmed"] for item in evidence["reports"])):
            raise ValueError("missing remote cleanup confirmation")
    elif (set(evidence) != {"phase", "type"}
          or type(evidence["phase"]) is not str
          or evidence["phase"] not in {"kernel_cancel", "process_cleanup", "remote_cleanup", "evidence_write"}
          or type(evidence["type"]) is not str or not evidence["type"]):
        raise ValueError("invalid cancellation failure evidence")


def _identifier(value: str, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def command_digest(snapshot: ExecutionSnapshot) -> str:
    raw = json.dumps(snapshot.command.to_dict(), sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


@contextmanager
def _read_only(path: str | Path):
    connection = sqlite3.connect(Path(path).resolve(strict=True).as_uri() + "?mode=ro",
                                 uri=True, timeout=30)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN")
        yield connection
    finally:
        connection.close()


def validate_cancellation_schema(connection: sqlite3.Connection, *,
                                 source_id: str | None = None,
                                 kernel_path: str | None = None) -> dict[str, Any]:
    """Validate a dedicated journal without modifying it."""
    objects = dict(connection.execute(
        "SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"))
    if objects != _OBJECTS:
        raise ValueError("unsupported or damaged cancellation journal schema")
    rows = connection.execute("SELECT version,source_id,kernel_path FROM cancellation_meta").fetchall()
    if (len(rows) != 1 or type(rows[0][0]) is not int or rows[0][0] != 1
            or type(rows[0][1]) is not str or not rows[0][1].strip()
            or type(rows[0][2]) is not str or not rows[0][2]):
        raise ValueError("unsupported cancellation journal metadata")
    if source_id is not None and rows[0][1] != source_id:
        raise ValueError("cancellation journal source identity differs")
    if kernel_path is not None and rows[0][2] != kernel_path:
        raise ValueError("cancellation journal Kernel path differs")
    return {"version": rows[0][0], "source_id": rows[0][1], "kernel_path": rows[0][2]}


@dataclass(frozen=True)
class CancellationReceipt:
    receipt_id: str
    execution_id: str
    command_digest: str
    attempt: int
    fence: int
    expected_revision: int
    reason: str
    isolation_mode: str
    requested_at: float
    phases: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CancellationJournalPage:
    receipts: tuple[CancellationReceipt, ...]
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {"receipts": [receipt.to_dict() for receipt in self.receipts], "truncated": self.truncated}


def inspect_cancellation_journal(path: str | Path, *, source_id: str,
                                 kernel_path: str | Path, snapshot: ExecutionSnapshot,
                                 limit: int = 100) -> CancellationJournalPage:
    """Read receipts for exactly one command/attempt/fence, including after restart.

    A missing or damaged file raises; this reader never creates or repairs it.
    The caller must not replace these receipts with an execution decision.
    """
    _identifier(source_id, "source_id")
    if type(snapshot) is not ExecutionSnapshot:
        raise TypeError("snapshot must be an ExecutionSnapshot")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    with _read_only(path) as connection:
        validate_cancellation_schema(connection, source_id=source_id,
                                     kernel_path=str(Path(kernel_path).resolve()))
        rows = connection.execute(
            "SELECT * FROM cancellation_requests WHERE execution_id=? AND command_digest=? "
            "AND attempt=? AND fence=? ORDER BY sequence DESC LIMIT ?",
            (snapshot.execution_id, command_digest(snapshot), snapshot.attempt, snapshot.fence, limit + 1),
        ).fetchall()
        receipts = []
        for row in rows[:limit]:
            if (any(type(row[key]) is not int or row[key] < 0 for key in ("attempt", "fence", "expected_revision"))
                    or row["isolation_mode"] not in {"thread", "process"}
                    or type(row["requested_at"]) not in {int, float}
                    or not math.isfinite(row["requested_at"]) or row["requested_at"] < 0):
                raise ValueError("invalid cancellation request metadata")
            _identifier(row["receipt_id"], "receipt_id")
            _identifier(row["reason"], "reason")
            phases = {item[0]: json.loads(item[1]) for item in connection.execute(
                "SELECT stage,evidence FROM cancellation_stages WHERE receipt_id=? ORDER BY stage",
                (row["receipt_id"],))}
            for stage, evidence in phases.items():
                _validate_evidence(stage, evidence, row)
            receipts.append(CancellationReceipt(
                row["receipt_id"], row["execution_id"], row["command_digest"], row["attempt"],
                row["fence"], row["expected_revision"], row["reason"], row["isolation_mode"],
                row["requested_at"], phases))
    return CancellationJournalPage(tuple(receipts), len(rows) > limit)


class CancellationJournal:
    """Explicit creation of a new evidence component, separate from core schemas.

    Runtime owns phase writes. Applications inspect through the read-only
    ``inspect_cancellation_journal`` function, not a writer constructor.
    """

    def __init__(self, path: str | Path, *, source_id: str, kernel_path: str | Path,
                 durability: Durability = "full") -> None:
        self.source_id = _identifier(source_id, "source_id")
        if str(path) == ":memory:" or str(kernel_path) == ":memory:":
            raise ValueError("cancellation evidence requires durable file paths")
        self.path = str(Path(path).resolve())
        self.kernel_path = str(Path(kernel_path).resolve())
        if self.path == self.kernel_path or (
                Path(self.path).exists() and Path(self.kernel_path).exists()
                and os.path.samefile(self.path, self.kernel_path)):
            raise ValueError("cancellation journal must be a separate file from the Kernel")
        self.durability = validate_durability(durability)
        existed = Path(self.path).exists()
        if existed:
            with _read_only(self.path) as check:
                validate_cancellation_schema(check, source_id=self.source_id, kernel_path=self.kernel_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            objects = connection.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if not objects and not existed:
                for statement in (_META, _REQUESTS, _STAGES, _INDEX):
                    connection.execute(statement)
                connection.execute("INSERT INTO cancellation_meta VALUES(1,?,?)",
                                   (self.source_id, self.kernel_path))
            validate_cancellation_schema(connection, source_id=self.source_id, kernel_path=self.kernel_path)
            connection.commit()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            configure_sqlite_connection(connection, self.path, durability=self.durability)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            yield connection
        finally:
            connection.close()

    def _begin(self, snapshot: ExecutionSnapshot, *, expected_revision: int,
               reason: str, isolation_mode: str) -> str:
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected_revision must be an integer >= 0")
        _identifier(reason, "reason")
        receipt_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            validate_cancellation_schema(connection, source_id=self.source_id, kernel_path=self.kernel_path)
            connection.execute(
                "INSERT INTO cancellation_requests(receipt_id,execution_id,command_digest,attempt,fence,"
                "expected_revision,reason,isolation_mode,requested_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (receipt_id, snapshot.execution_id, command_digest(snapshot), snapshot.attempt,
                 snapshot.fence, expected_revision, reason, isolation_mode, time.time()))
            connection.commit()
        return receipt_id

    def _record(self, receipt_id: str, stage: str, evidence: dict[str, Any]) -> None:
        _validate_evidence(stage, evidence)
        encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            validate_cancellation_schema(connection, source_id=self.source_id, kernel_path=self.kernel_path)
            request = connection.execute("SELECT attempt,fence,isolation_mode FROM cancellation_requests WHERE receipt_id=?",
                                         (receipt_id,)).fetchone()
            if request is None:
                raise ValueError("cancellation request is missing")
            _validate_evidence(stage, evidence, dict(zip(("attempt", "fence", "isolation_mode"), request)))
            prior = connection.execute(
                "SELECT evidence FROM cancellation_stages WHERE receipt_id=? AND stage=?",
                (receipt_id, stage)).fetchone()
            if prior is not None and prior[0] != encoded:
                raise ValueError("immutable cancellation receipt phase differs")
            if prior is None:
                connection.execute("INSERT INTO cancellation_stages VALUES(?,?,?)",
                                   (receipt_id, stage, encoded))
            connection.commit()


__all__ = ["CancellationJournal", "CancellationReceipt", "CancellationJournalPage",
           "CANCELLATION_SCHEMA_VERSION", "inspect_cancellation_journal"]
