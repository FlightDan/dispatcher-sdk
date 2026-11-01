"""Bounded durable storage for host-supplied direct projection bytes.

This component does not authenticate sources, isolate writers outside its own
SQLite transactions, interpret bytes, or authorize installation or resume.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4


class ProjectionStorageError(RuntimeError):
    """A stream is unavailable, inconsistent, or conflicts with stored facts."""


MAX_PAGE_BYTES = 256 * 1024
MAX_STREAM_BYTES = 64 * 1024 * 1024
MAX_PAGES = 1024
MAX_READ_PAGES = 4


def _stream_id(value):
    if type(value) is not str or not value.strip() or len(value.encode("utf-8")) > 4096:
        raise ValueError("stream_id must be a bounded nonempty string")
    return value


class ProjectionStorage:
    """SQLite streams with fixed size and exact immutable page replay.

    Each distinct source or target needs its own host-supplied stream ID.
    Only a complete stream is suitable for the host to attest to a consumer.
    This storage is not a participant in a cross-store decision transaction.
    A stream is limited to 64 MiB, with at most 1024 pages of 256 KiB each.
    It cannot authorize or activate application state.
    """

    def __init__(self, path: str | Path):
        if str(path) == ":memory:":
            raise ValueError("projection storage requires a persistent SQLite file")
        self.path = str(path)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                     "AND name IN ('projection_meta','projection_streams','projection_pages')")}
            required = {"projection_meta", "projection_streams", "projection_pages"}
            if names and names != required:
                raise ProjectionStorageError("incomplete projection storage schema")
            if not names:
                db.execute("CREATE TABLE projection_meta(version INTEGER NOT NULL, store_id TEXT NOT NULL, incarnation TEXT NOT NULL)")
                db.execute("INSERT INTO projection_meta VALUES(2,?,?)", (str(uuid4()), str(uuid4())))
                db.execute("CREATE TRIGGER projection_meta_no_update BEFORE UPDATE ON projection_meta BEGIN SELECT RAISE(ABORT,'immutable projection identity'); END")
                db.execute("CREATE TRIGGER projection_meta_no_delete BEFORE DELETE ON projection_meta BEGIN SELECT RAISE(ABORT,'immutable projection identity'); END")
                db.execute("CREATE TRIGGER projection_meta_no_insert BEFORE INSERT ON projection_meta BEGIN SELECT RAISE(ABORT,'immutable projection identity'); END")
                db.execute("CREATE TABLE projection_streams(stream_id TEXT PRIMARY KEY, binding TEXT NOT NULL, total_bytes INTEGER NOT NULL, "
                           "next_sequence INTEGER NOT NULL, stored_bytes INTEGER NOT NULL, complete INTEGER NOT NULL)")
                db.execute("CREATE TABLE projection_pages(stream_id TEXT NOT NULL, sequence INTEGER NOT NULL, "
                           "data BLOB NOT NULL, complete INTEGER NOT NULL, PRIMARY KEY(stream_id,sequence), "
                           "FOREIGN KEY(stream_id) REFERENCES projection_streams(stream_id))")
            else:
                columns = [row[1] for row in db.execute("PRAGMA table_info(projection_meta)")]
                if columns != ['version', 'store_id', 'incarnation']:
                    raise ProjectionStorageError("unsupported projection storage schema; legacy identity is unknown")
                triggers = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='projection_meta'")}
                if triggers != {'projection_meta_no_update', 'projection_meta_no_delete', 'projection_meta_no_insert'}:
                    raise ProjectionStorageError("projection identity protections unavailable")
            self._identity_in(db)
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _identity_in(db):
        rows = db.execute("SELECT version,store_id,incarnation FROM projection_meta LIMIT 2").fetchall()
        if len(rows) != 1 or rows[0][0] != 2:
            raise ProjectionStorageError("projection identity unavailable")
        store_id, incarnation = rows[0][1:]
        try:
            if (type(store_id) is not str or type(incarnation) is not str or
                    str(UUID(store_id)) != store_id or str(UUID(incarnation)) != incarnation or
                    store_id == incarnation):
                raise ValueError()
        except (ValueError, AttributeError):
            raise ProjectionStorageError("projection identity invalid") from None
        return {"store_id": store_id, "incarnation": incarnation}

    def identity(self) -> dict:
        """Read the logical store identity; physical copies need host protection."""
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            return self._identity_in(db)

    def create(self, stream_id: str, *, total_bytes: int, binding: dict) -> dict:
        stream_id = _stream_id(stream_id)
        if type(total_bytes) is not int or not 0 <= total_bytes <= MAX_STREAM_BYTES:
            raise ValueError("stream size exceeds its limit")
        if type(binding) is not dict or not binding:
            raise ValueError("host stream binding must be a nonempty object")
        def validate(value, depth=0):
            if depth > 32:
                raise ValueError("stream binding is too deep")
            if value is None or type(value) in (str, int, float, bool):
                return
            if type(value) is list:
                for item in value:
                    validate(item, depth + 1)
            elif type(value) is dict and all(type(key) is str for key in value):
                for item in value.values():
                    validate(item, depth + 1)
            else:
                raise ValueError("stream binding must be strict JSON")
        validate(binding)
        encoded = json.dumps(binding, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 65536:
            raise ValueError("stream binding exceeds its byte limit")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT total_bytes,binding FROM projection_streams WHERE stream_id=?", (stream_id,)).fetchone()
            if row is None:
                db.execute("INSERT INTO projection_streams VALUES(?,?,?,0,0,0)", (stream_id, encoded, total_bytes))
            elif row != (total_bytes, encoded):
                raise ProjectionStorageError("stream already has different terms")
            db.commit()
        return self.inspect(stream_id)

    def append(self, stream_id: str, *, sequence: int, data: bytes, complete: bool) -> dict:
        stream_id = _stream_id(stream_id)
        if type(sequence) is not int or not 0 <= sequence < MAX_PAGES:
            raise ValueError("invalid page sequence")
        if type(data) is not bytes or len(data) > MAX_PAGE_BYTES or type(complete) is not bool:
            raise ValueError("invalid page bytes or completion flag")
        if not data and not complete:
            raise ValueError("empty nonterminal page")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            stream = db.execute("SELECT total_bytes,next_sequence,stored_bytes,complete FROM projection_streams WHERE stream_id=?", (stream_id,)).fetchone()
            if stream is None:
                raise ProjectionStorageError("stream is unknown")
            old = db.execute("SELECT CASE WHEN typeof(data)='blob' AND length(data)<=? THEN data END,complete FROM projection_pages "
                             "WHERE stream_id=? AND sequence=?", (MAX_PAGE_BYTES, stream_id, sequence)).fetchone()
            if old is not None:
                if old != (data, int(complete)):
                    raise ProjectionStorageError("page already has different content")
            else:
                count = stream[2] + len(data)
                if (stream[3] or sequence != stream[1] or count > stream[0]
                        or complete != (count == stream[0])
                        or (sequence == MAX_PAGES - 1 and not complete)):
                    raise ProjectionStorageError("page does not continue the stream")
                db.execute("INSERT INTO projection_pages VALUES(?,?,?,?)", (stream_id, sequence, data, int(complete)))
                db.execute("UPDATE projection_streams SET next_sequence=?,stored_bytes=?,complete=? WHERE stream_id=?",
                           (sequence + 1, count, int(complete), stream_id))
            db.commit()
        return self.inspect(stream_id)

    def inspect(self, stream_id: str) -> dict:
        stream_id = _stream_id(stream_id)
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            identity = self._identity_in(db)
            row = db.execute("SELECT total_bytes,next_sequence,stored_bytes,complete,binding FROM projection_streams WHERE stream_id=?", (stream_id,)).fetchone()
            if row is None:
                raise ProjectionStorageError("stream is unknown")
            return {**identity, "stream_id": stream_id, "total_bytes": row[0], "next_sequence": row[1],
                    "stored_bytes": row[2], "complete": bool(row[3]), "binding": json.loads(row[4])}

    def read(self, stream_id: str, *, after: int = -1, limit: int = 1) -> dict:
        """Return at most four pages from a single consistent read snapshot."""
        stream_id = _stream_id(stream_id)
        if type(after) is not int or not -1 <= after < MAX_PAGES or type(limit) is not int or not 1 <= limit <= MAX_READ_PAGES:
            raise ValueError("invalid page cursor or limit")
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            identity = self._identity_in(db)
            stream = db.execute("SELECT total_bytes,next_sequence,stored_bytes,complete,binding FROM projection_streams WHERE stream_id=?", (stream_id,)).fetchone()
            if stream is None:
                raise ProjectionStorageError("stream is unknown")
            rows = db.execute("SELECT sequence,CASE WHEN typeof(data)='blob' AND length(data)<=? THEN data END,complete "
                              "FROM projection_pages WHERE stream_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                              (MAX_PAGE_BYTES, stream_id, after, limit)).fetchall()
            if any(row[1] is None or row[0] != after + index + 1 for index, row in enumerate(rows)):
                raise ProjectionStorageError("stored page is invalid or missing")
            if not rows and after + 1 < stream[1]:
                raise ProjectionStorageError("stored page is missing")
            page = rows
            cursor = page[-1][0] if page else after
            return {**identity, "stream_id": stream_id, "binding": json.loads(stream[4]), "total_bytes": stream[0], "stored_bytes": stream[2],
                    "complete": bool(stream[3]), "pages": [{"sequence": r[0], "data": r[1], "complete": bool(r[2])} for r in page],
                    "cursor": cursor, "has_more": cursor + 1 < stream[1]}
