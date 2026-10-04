"""Separate bounded telemetry storage; execution control remains Kernel-owned."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterator, Mapping

from .._inspection import InspectionBudget, InspectionBudgetExceeded
from .._sqlite_admission import retry_sqlite_admission
from ..durability import Durability, validate_durability
from .contracts import ObservationError, ObservationIdentity, ObservationOptions, identifier, positive


SCHEMA_VERSION = 1


class _ObservationWriteBudgetExceeded(TimeoutError):
    """One write attempt expired; retry requires a confirmed rollback."""
    rollback_confirmed = False


SCHEMA = """
CREATE TABLE obs_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 version INTEGER NOT NULL CHECK(version=1), kernel_path TEXT NOT NULL, source_id TEXT NOT NULL);
CREATE TABLE obs_current(execution_id TEXT PRIMARY KEY, attempt INTEGER NOT NULL,
 fence INTEGER NOT NULL, identity_json TEXT NOT NULL, bound_at REAL NOT NULL);
CREATE TABLE obs_sources(execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 source_id TEXT NOT NULL, sequence INTEGER NOT NULL, identity_json TEXT NOT NULL,
 metrics_json TEXT NOT NULL, tails_json TEXT NOT NULL, captured_at REAL NOT NULL,
 persisted_at REAL NOT NULL, gaps INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'active',
 source_scope TEXT, incarnation INTEGER, coverage_json TEXT NOT NULL DEFAULT '[]',
 PRIMARY KEY(execution_id,attempt,fence,source_id));
CREATE INDEX obs_sources_active ON obs_sources(execution_id,attempt,fence,state);
CREATE TABLE obs_collector_scopes(execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 source_scope TEXT NOT NULL, generation INTEGER NOT NULL, current_source_id TEXT,
 history_metrics_json TEXT NOT NULL DEFAULT '{}',
 PRIMARY KEY(execution_id,attempt,fence,source_scope));
CREATE TABLE obs_collectors(execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 source_id TEXT NOT NULL, source_scope TEXT NOT NULL, incarnation INTEGER NOT NULL,
 coverage_json TEXT NOT NULL, state TEXT NOT NULL, registered_at REAL NOT NULL,
 PRIMARY KEY(execution_id,attempt,fence,source_id));
CREATE TABLE obs_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 source_id TEXT NOT NULL, kind TEXT NOT NULL, captured_at REAL NOT NULL,
 persisted_at REAL NOT NULL, payload TEXT NOT NULL);
CREATE INDEX obs_events_execution ON obs_events(execution_id,attempt,fence,sequence);
CREATE TABLE obs_phases(execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 phase TEXT NOT NULL, captured_at REAL NOT NULL, persisted_at REAL NOT NULL, details TEXT NOT NULL,
 PRIMARY KEY(execution_id,attempt,fence,phase));
CREATE TABLE obs_processes(execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 process_id TEXT NOT NULL, registration TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'unknown',
 observed_at REAL, persisted_at REAL NOT NULL, evidence TEXT NOT NULL, unknown_reason TEXT,
 PRIMARY KEY(execution_id,attempt,fence,process_id));
CREATE TABLE obs_waits(execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 wait_id TEXT NOT NULL, state TEXT NOT NULL, started_at REAL NOT NULL, ended_at REAL,
 details TEXT NOT NULL, persisted_at REAL NOT NULL,
 PRIMARY KEY(execution_id,attempt,fence,wait_id));
CREATE TABLE obs_policies(policy_id TEXT NOT NULL, version INTEGER NOT NULL,
 execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 policy_json TEXT NOT NULL, target_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active',
 revision INTEGER NOT NULL DEFAULT 1, baseline_at REAL, next_sample_at REAL,
 continuity_id TEXT, progress_revision INTEGER NOT NULL DEFAULT 0,
 consecutive INTEGER NOT NULL DEFAULT 0, episode_id TEXT,
 PRIMARY KEY(policy_id,version,execution_id,attempt,fence));
CREATE TABLE obs_windows(window_id TEXT PRIMARY KEY, policy_id TEXT NOT NULL, version INTEGER NOT NULL,
 execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 started_at REAL NOT NULL, ended_at REAL NOT NULL, state TEXT NOT NULL,
 baseline_revision INTEGER, end_revision INTEGER, details TEXT NOT NULL,
 window_revision INTEGER NOT NULL,
 UNIQUE(policy_id,version,execution_id,attempt,fence,window_revision));
CREATE TABLE obs_episodes(episode_id TEXT PRIMARY KEY, policy_id TEXT NOT NULL, version INTEGER NOT NULL,
 execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 progress_revision INTEGER NOT NULL, state TEXT NOT NULL, started_at REAL NOT NULL, ended_at REAL,
 notification_id TEXT NOT NULL UNIQUE, details TEXT NOT NULL);
CREATE TABLE obs_outbox(notification_id TEXT PRIMARY KEY, episode_id TEXT NOT NULL UNIQUE,
 payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL,
 bridged_at REAL, last_error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL DEFAULT 5, lease_id TEXT, owner TEXT, expires_at REAL,
 next_attempt_at REAL NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1);
CREATE INDEX obs_outbox_pending ON obs_outbox(state,next_attempt_at);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _bounded_json(value: Any, maximum: int) -> str:
    """Reject large input containers before allocating their serialized form."""
    remaining = maximum
    nodes = 0
    def visit(item: Any, depth: int) -> None:
        nonlocal remaining, nodes
        nodes += 1
        if depth > 8 or nodes > 256:
            raise ValueError("observation payload is too complex")
        if isinstance(item, str):
            if len(item) > remaining:
                raise ValueError("observation payload exceeds its byte limit")
            remaining -= len(item.encode("utf-8"))
        elif isinstance(item, dict):
            if len(item) > 64:
                raise ValueError("observation payload has too many fields")
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("observation field names must be strings")
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(item, (tuple, list)):
            if len(item) > 128:
                raise ValueError("observation payload has too many items")
            for child in item:
                visit(child, depth + 1)
        elif item is not None and type(item) not in (int, float, bool):
            raise ValueError("observation payload must contain JSON values")
        if remaining < 0:
            raise ValueError("observation payload exceeds its byte limit")
    visit(value, 0)
    encoded = _json(value)
    if len(encoded.encode("utf-8")) > maximum:
        raise ValueError("observation payload exceeds its byte limit")
    return encoded


def _execute_schema(connection: sqlite3.Connection) -> None:
    for statement in SCHEMA.split(";"):
        if statement.strip():
            connection.execute(statement)


def _install_child_schema(connection: sqlite3.Connection) -> None:
    # The scheduling component owns these tables. They are installed only
    # with a new journal, never implicitly by a diagnostic read/open.
    from ..execution_kernel.children import CHILD_SCHEMA
    for statement in CHILD_SCHEMA.split(";"):
        if statement.strip():
            connection.execute(statement)


def _key(identity: ObservationIdentity) -> tuple[str, int, int]:
    return identity.execution_id, identity.attempt, identity.fence


def _json_size(value: Any, budget: InspectionBudget, maximum: int) -> int:
    """One streaming pass, checking Python serialization against its deadline."""
    size = 0
    for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(value):
        budget.check()
        size += len(chunk.encode("utf-8"))
        if size > maximum:
            return maximum + 1
    budget.check()
    return size


class _ReadLimitExceeded(RuntimeError):
    pass


class ObservationJournal:
    """An opt-in sidecar bound to a host-supplied storage identity.

    Only writer construction initializes a new file. Reader construction opens
    mode=ro and neither creates files nor runs persistent PRAGMAs or DDL.
    Every operation has its own connection so telemetry cannot hold a shared
    Kernel connection or Python execution-control lock.
    """

    def __init__(self, path: str | Path, *, kernel_path: str | Path, source_id: str,
                 options: ObservationOptions | None = None, writer: bool = True,
                 clock=None, durability: Durability = "full", _existing_only: bool = False) -> None:
        if type(_existing_only) is not bool or (_existing_only and not writer):
            raise ValueError("existing writer attachment requires a writable journal")
        if str(path) == ":memory:" or str(kernel_path) == ":memory:":
            raise ValueError("observation storage requires durable file paths")
        self.path = Path(path).resolve()
        self.kernel_path = str(Path(kernel_path).resolve())
        if str(self.path) == self.kernel_path:
            raise ValueError("observation journal must be separate from Kernel storage")
        self.source_id = identifier(source_id, "source_id")
        self.options = options or ObservationOptions()
        self.writer = writer
        self.clock = clock or time.time
        self.durability = validate_durability(durability)
        self._schema_pending = _existing_only
        if _existing_only:
            # Runtime supplied an already initialized sidecar. Each first
            # operation validates it inside that operation's original bound.
            # Constructing a child capability must not need SQLite admission.
            return
        if writer:
            self.initialize()
        else:
            with self._read_connection(self.options.query_timeout) as (connection, _):
                self._validate(connection)

    @classmethod
    def open_readonly(cls, path: str | Path, *, kernel_path: str | Path,
                      source_id: str, options: ObservationOptions | None = None,
                      clock=None) -> ObservationJournal:
        return cls(path, kernel_path=kernel_path, source_id=source_id,
                   options=options, writer=False, clock=clock)

    @classmethod
    def _open_existing_writer(cls, path: str | Path, *, kernel_path: str | Path,
                              source_id: str, options: ObservationOptions | None = None,
                              clock=None, durability: Durability = "full") -> ObservationJournal:
        """Attach Runtime's initialized sidecar without recreating or opening it."""
        return cls(path, kernel_path=kernel_path, source_id=source_id, options=options,
                   clock=clock, durability=durability, _existing_only=True)

    def _validate_existing_writer(self, connection: sqlite3.Connection, *, deadline: float) -> None:
        if not self._schema_pending:
            return
        self._validate(connection)
        if connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise ObservationError("existing observation journal requires WAL mode")
        if time.monotonic() >= deadline:
            raise _ObservationWriteBudgetExceeded("observation schema admission budget elapsed")
        self._schema_pending = False

    def _validate(self, connection: sqlite3.Connection) -> None:
        self._validate_binding(connection)
        reference = sqlite3.connect(":memory:")
        try:
            _execute_schema(reference)
            query = "SELECT type,name,sql FROM sqlite_master WHERE name GLOB 'obs_*' ORDER BY type,name"
            if [tuple(row) for row in connection.execute(query)] != list(reference.execute(query)):
                raise ObservationError("observation schema differs from its declared version")
        finally:
            reference.close()

    def _validate_binding(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("SELECT * FROM obs_meta").fetchall()
        if len(row) != 1 or tuple(row[0]) != (1, SCHEMA_VERSION, self.kernel_path, self.source_id):
            raise ObservationError("observation schema or source binding differs")

    def initialize(self) -> None:
        if not self.writer:
            raise ObservationError("read-only observation journal cannot initialize")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=self.options.write_timeout)
        try:
            tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if tables:
                self._validate(connection)
            # Unlike the shared durability helper, negotiation never retries
            # for 30 seconds: telemetry uses its configured short busy bound.
            if connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                raise ObservationError("observation journal requires WAL mode")
            connection.execute(f"PRAGMA synchronous={2 if self.durability == 'full' else 1}")
            if tables:
                # A validated existing journal needs no write transaction.
                # Workers opening it must not contend with activity flushes.
                return
            connection.execute("BEGIN IMMEDIATE")
            if not tables:
                # Recheck after obtaining the write lock for concurrent opens.
                if connection.execute("SELECT 1 FROM sqlite_master WHERE name='obs_meta'").fetchone():
                    self._validate(connection)
                else:
                    _execute_schema(connection)
                    _install_child_schema(connection)
                    connection.execute("INSERT INTO obs_meta VALUES(1,?,?,?)",
                                       (SCHEMA_VERSION, self.kernel_path, self.source_id))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _transaction(self, *, timeout_seconds: float | None = None) -> Iterator[tuple[sqlite3.Connection, float]]:
        if not self.writer:
            raise ObservationError("read-only observation journal cannot write")
        duration = self.options.write_timeout if timeout_seconds is None else min(
            self.options.write_timeout, positive(timeout_seconds, "timeout_seconds"))
        deadline = time.monotonic() + duration
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                                     timeout=0)
        connection.row_factory = sqlite3.Row
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        def admit(operation, *, commit=False):
            return retry_sqlite_admission(operation, deadline=deadline,
                expired=_ObservationWriteBudgetExceeded("observation write admission budget elapsed"),
                transaction_retained=(lambda: connection.in_transaction) if commit else None)
        try:
            admit(lambda: connection.execute("PRAGMA trusted_schema=OFF"))
            admit(lambda: connection.execute(f"PRAGMA synchronous={2 if self.durability == 'full' else 1}"))
            admit(lambda: connection.execute("BEGIN IMMEDIATE"))
            admit(lambda: self._validate_binding(connection))
            admit(lambda: self._validate_existing_writer(connection, deadline=deadline))
            if time.monotonic() >= deadline:
                raise _ObservationWriteBudgetExceeded("observation write admission budget elapsed")
            now = float(self.clock())
            if not math.isfinite(now):
                raise ObservationError("observation wall clock is not finite")
            yield connection, now
            if time.monotonic() >= deadline:
                raise _ObservationWriteBudgetExceeded("observation write operation budget elapsed")
            admit(connection.commit, commit=True)
        except BaseException as error:
            transaction_was_open = connection.in_transaction
            connection.rollback()
            if isinstance(error, _ObservationWriteBudgetExceeded):
                error.rollback_confirmed = (not connection.in_transaction
                    and (transaction_was_open or connection.total_changes == 0))
            raise
        finally:
            connection.close()

    @contextmanager
    def _read_connection(self, timeout: float, budget: InspectionBudget | None = None):
        budget = budget or InspectionBudget(positive(timeout, "timeout"), None)
        budget.check()
        # SQLite's busy handler counts requested sleep durations, which can
        # overrun a wall-clock budget on a coarse or delayed host scheduler.
        # Let the Python admission loop observe the original deadline between
        # immediate reads instead of spending it inside native busy sleeps.
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True,
                                     timeout=0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            budget.install(connection)
            connection.execute("BEGIN")
            while True:
                budget.check()
                try:
                    self._validate_binding(connection)
                    break
                except sqlite3.OperationalError as error:
                    code = getattr(error, "sqlite_errorcode", None)
                    contention = (code & 255 in (5, 6) if type(code) is int else str(error).lower() in {
                        "database is locked", "database table is locked", "database schema is locked"})
                    if not contention:
                        raise
                    budget.check()
                    time.sleep(min(.01, budget.sqlite_timeout_seconds))
            budget.check()
            self._validate_existing_writer(connection, deadline=time.monotonic() + budget.sqlite_timeout_seconds)
            budget.check()
            yield connection, budget
        finally:
            connection.close()

    def bind_current(self, identity: ObservationIdentity) -> bool:
        """Bind an authoritative current identity; old bindings cannot regress it."""
        with self._transaction() as (connection, now):
            row = connection.execute("SELECT * FROM obs_current WHERE execution_id=?",
                                     (identity.execution_id,)).fetchone()
            encoded = _json(identity.to_dict())
            if row is not None:
                old = json.loads(row["identity_json"])
                old_order = (old["generation"], row["attempt"], row["fence"])
                order = (identity.generation, identity.attempt, identity.fence)
                if order < old_order:
                    return False
                if order == old_order:
                    if row["identity_json"] != encoded:
                        raise ObservationError("current identity was rebound with different provenance")
                    return True
            connection.execute(
                "INSERT INTO obs_current VALUES(?,?,?,?,?) ON CONFLICT(execution_id) DO UPDATE SET "
                "attempt=excluded.attempt,fence=excluded.fence,identity_json=excluded.identity_json,bound_at=excluded.bound_at",
                (*_key(identity), encoded, now))
            return True

    def _event(self, connection, identity, source_id, kind, captured_at, details, now):
        encoded = _bounded_json(details, min(4096, self.options.batch_bytes))
        connection.execute("INSERT INTO obs_events(execution_id,attempt,fence,source_id,kind,"
                           "captured_at,persisted_at,payload) VALUES(?,?,?,?,?,?,?,?)",
                           (*_key(identity), source_id, kind, captured_at, now, encoded))
        if kind == "phase":
            phase = identifier(details["phase"], "phase")
            connection.execute("INSERT INTO obs_phases VALUES(?,?,?,?,?,?,?) "
                               "ON CONFLICT(execution_id,attempt,fence,phase) DO UPDATE SET "
                               "captured_at=MAX(captured_at,excluded.captured_at),persisted_at=excluded.persisted_at,details=excluded.details",
                               (*_key(identity), phase, captured_at, now, encoded))
        elif kind in ("wait_begin", "wait_end"):
            wait_id = identifier(details["wait_id"], "wait_id")
            started = details["started_at"]
            if type(started) not in (int, float) or not math.isfinite(started):
                raise ValueError("wait capture time must be finite")
            wait_details = _bounded_json({**details["wait"], "_collector_source_id": source_id}, 4096)
            old = connection.execute("SELECT started_at,details FROM obs_waits WHERE execution_id=? AND attempt=? AND fence=? AND wait_id=?",
                                     (*_key(identity), wait_id)).fetchone()
            if old is not None and (old["started_at"] != started or old["details"] != wait_details):
                raise ObservationError("wait identity was replayed with different original facts")
            ended = captured_at if kind == "wait_end" else None
            connection.execute("INSERT INTO obs_waits VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(execution_id,attempt,fence,wait_id) DO NOTHING",
                               (*_key(identity), wait_id, "ended" if ended is not None else "waiting",
                                started, ended, wait_details, now))
            if ended is not None:
                connection.execute("UPDATE obs_waits SET state='ended',ended_at=CASE WHEN ended_at IS NULL THEN ? ELSE MAX(ended_at,?) END,persisted_at=? "
                                   "WHERE execution_id=? AND attempt=? AND fence=? AND wait_id=?",
                                   (ended, ended, now, *_key(identity), wait_id))

    def phase(self, identity: ObservationIdentity, phase: str, *, captured_at: float | None = None,
              details: Mapping[str, Any] | None = None, source_id: str = "runtime") -> None:
        identifier(phase, "phase")
        with self._transaction() as (connection, now):
            self._event(connection, identity, source_id, "phase", now if captured_at is None else captured_at,
                        {"phase": phase, "details": dict(details or {})}, now)

    def write_batch(self, identity: ObservationIdentity, *, source_id: str, sequence: int,
                    metrics: Mapping[str, Any], captured_at: float,
                    tails: Mapping[str, bytes] | None = None, gaps: int = 0,
                    events: tuple[dict[str, Any], ...] = (), source_scope: str | None = None,
                    collector_incarnation: int | None = None) -> bool:
        """Replace one source's cumulative summary once per increasing sequence.

        Late attempts are stored under their own key. They never change the
        separate current binding. Sequence replay cannot double-count deltas.
        """
        identifier(source_id, "source_id")
        if type(captured_at) not in (int, float) or not math.isfinite(captured_at):
            raise ValueError("capture time must be finite")
        if type(sequence) is not int or sequence < 1 or type(gaps) is not int or gaps < 0:
            raise ValueError("sequence must be positive and gaps nonnegative")
        if len(metrics) > 32 or len(events) > self.options.batch_summaries:
            raise ValueError("too many metrics or events in one observation batch")
        for name, metric in metrics.items():
            self._metric_name(name)
            if type(metric.get("count")) is not int or metric["count"] < 0:
                raise ValueError("metric counts must be nonnegative integers")
            if set(metric) - {"count", "first_at", "last_at"}:
                raise ValueError("metric summary contains unsupported fields")
            for name in ("first_at", "last_at"):
                value = metric.get(name)
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                    raise ValueError("metric timestamps must be finite")
        encoded_metrics = _json(dict(metrics))
        encoded_tails = _json({name: base64.b64encode(value[-self.options.tail_bytes:]).decode("ascii")
                               for name, value in (tails or {}).items() if name in ("stdout", "stderr")})
        if len(encoded_metrics.encode("utf-8")) + len(encoded_tails) + len(_json(events).encode("utf-8")) > self.options.batch_bytes:
            raise ValueError("observation batch exceeds its byte limit")
        with self._transaction() as (connection, now):
            coverage_json, state = '[]', 'active'
            previous = connection.execute("SELECT * FROM obs_sources WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?",
                                          (*_key(identity), source_id)).fetchone()
            if previous is not None:
                if previous["sequence"] >= sequence:
                    return False
                if previous["identity_json"] != _json(identity.to_dict()):
                    raise ObservationError("source identity was rebound with different provenance")
                if previous["source_scope"] != source_scope:
                    raise ObservationError("source collector scope differs")
                old = json.loads(previous["metrics_json"])
                if any(name not in metrics or metrics[name]["count"] < metric["count"] for name, metric in old.items()):
                    raise ObservationError("cumulative metric counters regressed")
            if source_scope is not None:
                collector = connection.execute("SELECT * FROM obs_collectors WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?",
                                               (*_key(identity), source_id)).fetchone()
                if collector is None or (collector["source_scope"], collector["incarnation"]) != (source_scope, collector_incarnation):
                    raise ObservationError("collector scope registration is unavailable or differs")
                coverage_json = collector["coverage_json"]
                if not set(metrics).issubset(json.loads(coverage_json)):
                    raise ObservationError("metric is outside declared collector coverage")
                state = self._activate_collector(connection, identity, collector, now)
            connection.execute("INSERT INTO obs_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                               "ON CONFLICT(execution_id,attempt,fence,source_id) DO UPDATE SET "
                               "sequence=excluded.sequence,metrics_json=excluded.metrics_json,tails_json=excluded.tails_json,"
                               "captured_at=excluded.captured_at,persisted_at=excluded.persisted_at,gaps=excluded.gaps,state=excluded.state",
                               (*_key(identity), source_id, sequence, _json(identity.to_dict()), encoded_metrics,
                                encoded_tails, captured_at, now, gaps, state, source_scope, collector_incarnation, coverage_json))
            for event in events:
                self._event(connection, identity, source_id, event["kind"], event["captured_at"], event["details"], now)
            return True

    @staticmethod
    def _metric_name(name: str) -> None:
        if type(name) is not str or not name.strip() or len(name) > 128 or len(name.encode("utf-8")) > 128:
            raise ValueError("metric names must be nonempty strings of at most 128 bytes")

    def register_collector(self, identity: ObservationIdentity, source_id: str, *,
                           source_scope: str, metric_coverage: tuple[str, ...]) -> int:
        """Allocate a durable scope incarnation; only explicit scopes replace."""
        identifier(source_id, "source_id")
        identifier(source_scope, "source_scope")
        if not metric_coverage or len(metric_coverage) > 32:
            raise ValueError("collector coverage must contain 1 to 32 metric names")
        for name in metric_coverage:
            self._metric_name(name)
        coverage = _json(sorted(set(metric_coverage)))
        with self._transaction() as (connection, now):
            source = connection.execute("SELECT source_scope FROM obs_sources WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?",
                                        (*_key(identity), source_id)).fetchone()
            if source is not None and source[0] != source_scope:
                raise ObservationError("existing source has a different collector scope")
            old = connection.execute("SELECT * FROM obs_collectors WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?",
                                     (*_key(identity), source_id)).fetchone()
            if old is not None:
                if old["source_scope"] != source_scope or old["coverage_json"] != coverage:
                    raise ObservationError("collector incarnation was registered with different coverage")
                return old["incarnation"]
            row = connection.execute("SELECT generation FROM obs_collector_scopes WHERE execution_id=? AND attempt=? AND fence=? AND source_scope=?",
                                     (*_key(identity), source_scope)).fetchone()
            generation = 1 if row is None else row[0] + 1
            connection.execute("INSERT INTO obs_collector_scopes(execution_id,attempt,fence,source_scope,generation,current_source_id) VALUES(?,?,?,?,?,NULL) "
                               "ON CONFLICT(execution_id,attempt,fence,source_scope) DO UPDATE SET generation=excluded.generation",
                               (*_key(identity), source_scope, generation))
            connection.execute("INSERT INTO obs_collectors VALUES(?,?,?,?,?,?,?,'pending',?)",
                               (*_key(identity), source_id, source_scope, generation, coverage, now))
            return generation

    def _activate_collector(self, connection, identity, collector, now):
        if collector["state"] == "retired":
            return "retired"
        scope_key = (*_key(identity), collector["source_scope"])
        scope = connection.execute("SELECT current_source_id,history_metrics_json FROM obs_collector_scopes WHERE execution_id=? AND attempt=? AND fence=? AND source_scope=?", scope_key).fetchone()
        current = None if scope[0] is None else connection.execute("SELECT incarnation FROM obs_collectors WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?", (*_key(identity), scope[0])).fetchone()
        if current is not None and current[0] > collector["incarnation"]:
            connection.execute("UPDATE obs_collectors SET state='retired' WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?",
                               (*_key(identity), collector["source_id"]))
            return "retired"
        old = connection.execute("SELECT source_id,metrics_json,incarnation FROM obs_sources WHERE execution_id=? AND attempt=? AND fence=? AND source_scope=? AND state!='retired' AND source_id!=?",
                                 (*scope_key, collector["source_id"])).fetchall()
        coverage = set(json.loads(collector["coverage_json"]))
        if any(row["incarnation"] > collector["incarnation"] for row in old):
            return "active"  # An older incarnation cannot retire a newer collector.
        if any(not set(json.loads(row["metrics_json"])).issubset(coverage) for row in old):
            return "active"  # Older unknown collector remains visible.
        history = {name: value for name, value in json.loads(scope["history_metrics_json"]).items() if name in coverage}
        for row in old:
            for name, metric in json.loads(row["metrics_json"]).items():
                self._merge_metric(history, name, metric)
            connection.execute("UPDATE obs_sources SET state='retired' WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?", (*_key(identity), row["source_id"]))
            connection.execute("UPDATE obs_collectors SET state='retired' WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?", (*_key(identity), row["source_id"]))
            self._event(connection, identity, collector["source_id"], "collector_replaced", now,
                        {"source_scope": collector["source_scope"], "retired_source_id": row["source_id"],
                         "source_id": collector["source_id"], "incarnation": collector["incarnation"],
                         "reason": "collection_continuity_gap"}, now)
        connection.execute("UPDATE obs_collector_scopes SET current_source_id=?,history_metrics_json=? WHERE execution_id=? AND attempt=? AND fence=? AND source_scope=?",
                           (collector["source_id"], _json(history), *scope_key))
        connection.execute("UPDATE obs_collectors SET state='active' WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?",
                           (*_key(identity), collector["source_id"]))
        return "active"

    @staticmethod
    def _merge_metric(metrics, name, metric):
        total = metrics.setdefault(name, {"count": 0, "first_at": None, "last_at": None})
        total["count"] += metric["count"]
        for field, operation in (("first_at", min), ("last_at", max)):
            value = metric.get(field)
            if value is not None:
                total[field] = value if total[field] is None else operation(total[field], value)

    def close_source(self, identity: ObservationIdentity, source_id: str) -> None:
        with self._transaction() as (connection, now):
            connection.execute("UPDATE obs_sources SET state='closed',persisted_at=? WHERE execution_id=? AND attempt=? AND fence=? AND source_id=? AND state!='retired'",
                               (now, *_key(identity), source_id))

    def register_process(self, identity: ObservationIdentity, process_id: str, *, role: str,
                         pid: int | None = None, birth_identity: Any = None,
                         namespace: str | None = None, source: str = "runtime") -> None:
        identifier(process_id, "process_id")
        identifier(role, "role")
        details = {"role": role, "pid": pid, "birth_identity": birth_identity,
                   "namespace": namespace, "source": source}
        encoded = _bounded_json(details, 4096)
        with self._transaction() as (connection, now):
            old = connection.execute("SELECT registration FROM obs_processes WHERE execution_id=? AND attempt=? AND fence=? AND process_id=?",
                                     (*_key(identity), process_id)).fetchone()
            if old is not None and old[0] != encoded:
                raise ObservationError("process registration identity differs")
            if old is None and connection.execute("SELECT COUNT(*) FROM obs_processes WHERE execution_id=? AND attempt=? AND fence=?",
                                                  _key(identity)).fetchone()[0] >= 32:
                raise ObservationError("execution process observation capacity exhausted")
            connection.execute("INSERT OR IGNORE INTO obs_processes VALUES(?,?,?,?,?,'unknown',NULL,?,'{}','not_observed')",
                               (*_key(identity), process_id, encoded, now))

    def observe_process(self, identity: ObservationIdentity, process_id: str, state: str, *,
                        observed_at: float | None = None, evidence: Mapping[str, Any] | None = None,
                        unknown_reason: str | None = None) -> None:
        if state not in ("alive", "exited", "unknown"):
            raise ValueError("invalid process observation state")
        encoded = _bounded_json(dict(evidence or {}), 4096)
        with self._transaction() as (connection, now):
            observed = now if observed_at is None else observed_at
            changed = connection.execute("UPDATE obs_processes SET state=?,observed_at=?,persisted_at=?,evidence=?,unknown_reason=? "
                                         "WHERE execution_id=? AND attempt=? AND fence=? AND process_id=? "
                                         "AND (observed_at IS NULL OR observed_at<=?)",
                                         (state, observed, now, encoded,
                                          (unknown_reason or "observer_did_not_establish_state") if state == "unknown" else None,
                                          *_key(identity), process_id, observed))
            if changed.rowcount:
                self._event(connection, identity, "process:" + process_id, "process", observed,
                            {"process_id": process_id, "state": state, "evidence": dict(evidence or {}),
                             "unknown_reason": unknown_reason if state == "unknown" else None}, now)
            if not changed.rowcount and not connection.execute("SELECT 1 FROM obs_processes WHERE execution_id=? AND attempt=? AND fence=? AND process_id=?",
                                                              (*_key(identity), process_id)).fetchone():
                raise ObservationError("process must be registered before observing")

    def record_wait(self, identity: ObservationIdentity, wait_id: str, *, details: Mapping[str, Any],
                    started_at: float | None = None) -> None:
        identifier(wait_id, "wait_id")
        legacy_details = dict(details)
        legacy_details.pop("_collector_source_id", None)
        encoded = _bounded_json(legacy_details, 4096)
        with self._transaction() as (connection, now):
            connection.execute("INSERT OR IGNORE INTO obs_waits VALUES(?,?,?,?,'waiting',?,NULL,?,?)",
                               (*_key(identity), wait_id, now if started_at is None else started_at, encoded, now))

    def end_wait(self, identity: ObservationIdentity, wait_id: str, *, state: str = "ended",
                 ended_at: float | None = None) -> None:
        with self._transaction() as (connection, now):
            connection.execute("UPDATE obs_waits SET state=?,ended_at=?,persisted_at=? WHERE execution_id=? AND attempt=? AND fence=? AND wait_id=?",
                               (state, now if ended_at is None else ended_at, now, *_key(identity), wait_id))

    def inspect(self, execution_id: str, *, attempt: int | None = None, fence: int | None = None,
                timeout: float | None = None) -> dict[str, Any]:
        identifier(execution_id, "execution_id")
        duration = self.options.query_timeout if timeout is None else timeout
        budget = InspectionBudget(duration, None)
        report: dict[str, Any] = {"execution_id": execution_id, "observed_at": float(self.clock()),
                                 "view": "persisted", "current": False, "identity": None,
                                 "captured_at": None, "persisted_at": None, "metrics": {}, "tails": {},
                                 "phases": [], "processes": [], "waits": [], "sources": [],
                                 "complete": True, "truncated": False, "collection_gaps": 0, "unknown_reason": None}
        try:
            with self._read_connection(duration, budget) as (connection, _):
                self._inspect(connection, report, execution_id, attempt, fence, budget)
        except _ReadLimitExceeded:
            report.update(complete=False, truncated=True, unknown_reason="query_read_byte_limit")
        except InspectionBudgetExceeded:
            report.update(complete=False, truncated=True, timed_out=True, unknown_reason="query_timeout")
        except sqlite3.Error as error:
            if not budget.interrupted(error):
                raise
            report.update(complete=False, truncated=True, timed_out=True, unknown_reason="query_timeout")
        except (ValueError, TypeError):
            report.update(complete=False, truncated=True, unknown_reason="observation_data_invalid")
        return self._bound_report(report, budget)

    def _inspect(self, connection, report, execution_id, attempt, fence, budget):
        read_remaining = self.options.query_bytes
        def consume(row):
            nonlocal read_remaining
            budget.check()
            for value in row:
                if isinstance(value, str):
                    read_remaining -= len(value.encode("utf-8"))
            if read_remaining < 0:
                raise _ReadLimitExceeded()
            budget.check()
        current = connection.execute("SELECT * FROM obs_current WHERE execution_id=?", (execution_id,)).fetchone()
        if current is not None:
            consume(current)
        if attempt is None:
            if current is None:
                report.update(complete=False, unknown_reason="execution_not_observed")
                return
            attempt, fence = current["attempt"], current["fence"]
        elif fence is None:
            row = connection.execute("SELECT fence FROM obs_sources WHERE execution_id=? AND attempt=? ORDER BY fence DESC LIMIT 1",
                                     (execution_id, attempt)).fetchone()
            if row is None:
                report.update(complete=False, unknown_reason="attempt_not_observed")
                return
            fence = row[0]
        key = (execution_id, attempt, fence)
        report["current"] = current is not None and key == (execution_id, current["attempt"], current["fence"])
        if report["current"]:
            report["identity"] = json.loads(current["identity_json"])
        sources = connection.execute("SELECT source_id,sequence,identity_json,metrics_json,captured_at,persisted_at,gaps,state,"
                                     "source_scope,incarnation,coverage_json FROM obs_sources "
                                     "WHERE execution_id=? AND attempt=? AND fence=? AND state!='retired' ORDER BY source_id LIMIT ?",
                                     (*key, self.options.batch_summaries + 1))
        newest = None
        merged_scopes = set()
        for index, row in enumerate(sources):
            if index >= self.options.batch_summaries:
                report.update(complete=False, truncated=True)
                break
            consume(row)
            report["identity"] = report["identity"] or json.loads(row["identity_json"])
            report["captured_at"] = max(report["captured_at"] or row["captured_at"], row["captured_at"])
            report["persisted_at"] = max(report["persisted_at"] or row["persisted_at"], row["persisted_at"])
            report["collection_gaps"] += row["gaps"]
            report["sources"].append({"source_id": row["source_id"], "sequence": row["sequence"],
                                      "state": row["state"], "captured_at": row["captured_at"],
                                      "persisted_at": row["persisted_at"], "gaps": row["gaps"],
                                      "source_scope": row["source_scope"], "incarnation": row["incarnation"],
                                      "metric_coverage": json.loads(row["coverage_json"])})
            source_age = report["observed_at"] - row["captured_at"]
            if row["state"] == "active" and (source_age < 0 or source_age > self.options.process_freshness):
                report["sources"][-1]["continuity"] = "unknown"
                report["complete"] = False
                report["unknown_reason"] = "collector_not_recently_observed"
            else:
                report["sources"][-1]["continuity"] = "observed"
            if row["gaps"]:
                report["complete"] = False
            for name, metric in json.loads(row["metrics_json"]).items():
                budget.check()
                self._metric_name(name)
                self._merge_metric(report["metrics"], name, metric)
            if row["source_scope"] is not None and row["source_scope"] not in merged_scopes:
                history_row = connection.execute("SELECT current_source_id,history_metrics_json FROM obs_collector_scopes "
                    "WHERE execution_id=? AND attempt=? AND fence=? AND source_scope=?", (*key, row["source_scope"])).fetchone()
                if history_row["current_source_id"] == row["source_id"]:
                    consume(history_row)
                    # Historical offsets preserve first/last facts and
                    # cumulative totals only for currently installed metrics.
                    known = json.loads(row["metrics_json"])
                    for name, metric in json.loads(history_row["history_metrics_json"]).items():
                        budget.check()
                        if name in known:
                            self._merge_metric(report["metrics"], name, metric)
                    merged_scopes.add(row["source_scope"])
            if newest is None or row["captured_at"] > newest["captured_at"]:
                newest = row
        if newest is not None:
            tail = connection.execute("SELECT CASE WHEN length(tails_json)<=? THEN tails_json ELSE NULL END "
                                      "FROM obs_sources WHERE execution_id=? AND attempt=? AND fence=? AND source_id=?",
                                      (read_remaining, *key, newest["source_id"])).fetchone()
            if tail[0] is None:
                report.update(complete=False, truncated=True)
            else:
                consume(tail)
                report["tails"] = {name: base64.b64decode(value).decode("utf-8", errors="replace")
                                   for name, value in json.loads(tail[0]).items()}
        for table, destination in (("obs_phases", "phases"), ("obs_processes", "processes"), ("obs_waits", "waits")):
            budget.check()
            rows = connection.execute(f"SELECT * FROM {table} WHERE execution_id=? AND attempt=? AND fence=? LIMIT ?",
                                      (*key, self.options.page_events + 1))
            for index, row in enumerate(rows):
                if index >= self.options.page_events:
                    report.update(complete=False, truncated=True)
                    break
                consume(row)
                value = dict(row)
                for name in ("details", "registration", "evidence"):
                    if name in value:
                        value[name] = json.loads(value[name])
                if table == "obs_processes":
                    value["last_observed_state"] = value["state"]
                    if value["state"] == "alive" and (value["observed_at"] is None or
                            report["observed_at"] < value["observed_at"] or
                            report["observed_at"] - value["observed_at"] > self.options.process_freshness):
                        value["state"], value["unknown_reason"] = "unknown", "observation_stale"
                report[destination].append(value)
        # Authoritative scheduling waits are readable even if their
        # optional diagnostic mirror has not reached obs_waits yet.
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='sdk_child_waits'").fetchone():
            rows = connection.execute("SELECT wait_id,target_execution_id,reason,started_at,deadline_at,state,updated_at,error_json "
                                      "FROM sdk_child_waits WHERE source_id=? AND parent_execution_id=? AND parent_attempt=? AND parent_fence=? LIMIT ?",
                                      (self.source_id, *key, self.options.page_events + 1)).fetchall()
            report["child_waits"] = []
            for row in rows[:self.options.page_events]:
                consume(row)
                report["child_waits"].append(dict(row))
            if len(rows) > self.options.page_events:
                report["complete"] = False
                report["truncated"] = True
            rows = connection.execute("SELECT request_id,child_execution_id,depth,action,state,wait_id,created_at,updated_at,error_json "
                                      "FROM sdk_child_requests WHERE source_id=? AND parent_execution_id=? AND parent_attempt=? AND parent_fence=? LIMIT ?",
                                      (self.source_id, *key, self.options.page_events + 1)).fetchall()
            report["child_requests"] = []
            for row in rows[:self.options.page_events]:
                consume(row)
                report["child_requests"].append(dict(row))
            if len(rows) > self.options.page_events:
                report["complete"] = False
                report["truncated"] = True
        report["retired_sources"] = []
        for row in connection.execute("SELECT source_id,source_scope,incarnation,captured_at,persisted_at,state "
                                      "FROM obs_sources WHERE execution_id=? AND attempt=? AND fence=? AND state='retired' LIMIT ?",
                                      (*key, self.options.page_events)):
            consume(row)
            report["retired_sources"].append(dict(row))
        if not report["sources"]:
            report.update(complete=False, unknown_reason="activity_not_collected")
        report["output"] = {}
        for stream in ("stdout", "stderr"):
            metric = report["metrics"].get(stream + "_bytes")
            report["output"][stream] = {"known": metric is not None,
                                         "first_missing": None if metric is None else metric["first_at"] is None}

    @classmethod
    def _bound_without_storage(cls, report, *, options, budget):
        """Use the same pure report bounds even when journal opening failed."""
        bounder = cls.__new__(cls)
        bounder.options = options
        return bounder._bound_report(report, budget=budget)

    def _bound_report(self, report: dict[str, Any], budget: InspectionBudget | None = None) -> dict[str, Any]:
        budget = budget or InspectionBudget(self.options.query_timeout, None)
        sections = ("metrics", "sources", "waits", "child_waits", "child_requests", "processes", "phases", "retired_sources", "tails",
                    "diagnostics", "local_cancellation_diagnostics", "settlement_obligations", "result", "budget", "settlement", "supervision")
        original = {name: report[name] for name in sections if isinstance(report.get(name), (dict, list))}
        for name in original:
            report[name] = {} if isinstance(original[name], dict) else []
        try:
            # Reserve space for the explicit truncation explanation so a cut
            # never needs a second quadratic pass over already retained data.
            used = _json_size(report, budget, self.options.query_bytes) + 128
            if used > self.options.query_bytes:
                report["identity"] = None
                for name in tuple(report):
                    if name not in {"execution_id", "view", "observed_at", "current", "identity", "captured_at",
                                    "persisted_at", "complete", "truncated", "collection_gaps", "unknown_reason",
                                    "output", "timed_out", "elapsed_seconds", *sections}:
                        del report[name]
                report.update(complete=False, truncated=True, unknown_reason="query_byte_limit")
                used = _json_size(report, budget, self.options.query_bytes) + 128
                if used > self.options.query_bytes:
                    return self._partial_report(report, original, "query_byte_limit", budget)
            for name, values in original.items():
                if isinstance(values, dict):
                    for key, value in values.items():
                        size = _json_size(key, budget, self.options.query_bytes) + 1 + _json_size(value, budget, self.options.query_bytes) + 1
                        if used + size > self.options.query_bytes:
                            report.update(complete=False, truncated=True, unknown_reason="query_byte_limit")
                            break
                        report[name][key] = value
                        used += size
                else:
                    for value in values:
                        size = _json_size(value, budget, self.options.query_bytes) + 1
                        if used + size > self.options.query_bytes:
                            report.update(complete=False, truncated=True, unknown_reason="query_byte_limit")
                            break
                        report[name].append(value)
                        used += size
            if _json_size(report, budget, self.options.query_bytes) > self.options.query_bytes:
                return self._partial_report(report, original, "query_byte_limit", budget)
        except InspectionBudgetExceeded:
            return self._partial_report(report, original, "query_timeout", budget)
        report["elapsed_seconds"] = budget.elapsed_seconds
        return report

    def _partial_report(self, report, sections, reason, budget):
        # An expired query budget cannot authorize another walk over large
        # results or diagnostic evidence. Return a constant-size envelope.
        execution_id = report.get("execution_id", "")
        execution_id = execution_id[:self.options.query_bytes // 16] if isinstance(execution_id, str) else None
        partial = {"execution_id": execution_id, "view": "persisted", "current": False,
            "identity": None, "complete": False, "truncated": True, "unknown_reason": reason,
            "timed_out": reason == "query_timeout", "elapsed_seconds": budget.elapsed_seconds}
        for name, value in sections.items():
            partial[name] = {} if isinstance(value, dict) else []
        return partial

    def events(self, execution_id: str, *, after: int = 0, limit: int | None = None,
               attempt: int | None = None, fence: int | None = None,
               timeout: float | None = None) -> dict[str, Any]:
        identifier(execution_id, "execution_id")
        if type(after) is not int or after < 0:
            raise ValueError("event cursor must be a nonnegative integer")
        requested = self.options.page_events if limit is None else limit
        if type(requested) is not int or requested < 1:
            raise ValueError("event limit must be positive")
        maximum = min(requested, self.options.page_events)
        report: dict[str, Any] = {"events": [], "cursor": after, "has_more": False, "complete": True}
        duration = self.options.query_timeout if timeout is None else timeout
        budget = InspectionBudget(duration, None)
        try:
            with self._read_connection(duration, budget) as (connection, _):
                rows = connection.execute("SELECT * FROM obs_events WHERE execution_id=? AND sequence>? "
                                          "AND (? IS NULL OR attempt=?) AND (? IS NULL OR fence=?) ORDER BY sequence LIMIT ?",
                                          (execution_id, after, attempt, attempt, fence, fence, maximum + 1))
                used = _json_size(report, budget, self.options.query_bytes) + 128
                for index, row in enumerate(rows):
                    budget.check()
                    if index >= maximum:
                        report["has_more"] = True
                        break
                    event = dict(row)
                    event["payload"] = json.loads(event["payload"])
                    size = _json_size(event, budget, self.options.query_bytes) + 1
                    if used + size > self.options.query_bytes:
                        report.update(has_more=True, complete=False, truncated=True)
                        if not report["events"]:
                            event = {"sequence": row["sequence"], "execution_id": execution_id,
                                     "attempt": row["attempt"], "fence": row["fence"],
                                     "payload": {"truncated": True, "reason": "query_byte_limit"}}
                            report["events"].append(event)
                            report["cursor"] = row["sequence"]
                        break
                    report["events"].append(event)
                    report["cursor"] = row["sequence"]
                    used += size
        except InspectionBudgetExceeded:
            report.update(has_more=True, complete=False, timed_out=True, unknown_reason="query_timeout")
        except sqlite3.Error as error:
            if not budget.interrupted(error):
                raise
            report.update(has_more=True, complete=False, timed_out=True, unknown_reason="query_timeout")
        report["elapsed_seconds"] = budget.elapsed_seconds
        return report


def inspect_execution(path: str | Path, execution_id: str, *, kernel_path: str | Path,
                      source_id: str, attempt: int | None = None, fence: int | None = None,
                      options: ObservationOptions | None = None, timeout: float | None = None) -> dict[str, Any]:
    from dataclasses import replace
    from ..execution_kernel.settlement import SettlementJournal, merge_diagnostic_notes
    settings = options or ObservationOptions()
    duration = settings.query_timeout if timeout is None else timeout
    budget = InspectionBudget(duration, None)
    report: dict[str, Any] = {"execution_id": execution_id, "view": "persisted", "complete": False}
    reader = None
    try:
        reader = ObservationJournal.open_readonly(path, kernel_path=kernel_path, source_id=source_id,
            options=replace(settings, query_timeout=max(.001, duration-budget.elapsed_seconds)))
        budget.check()
        report = reader.inspect(execution_id, attempt=attempt, fence=fence,
            timeout=max(.001, duration-budget.elapsed_seconds))
        budget.check()
        settlement = SettlementJournal.open_readonly(str(Path(kernel_path).resolve()) + ".settlements.sqlite3",
            source_id=source_id, kernel_path=kernel_path,
            timeout_seconds=min(.1, max(.001, duration-budget.elapsed_seconds)))
        budget.check()
        obligations = settlement.inspect(execution_id,
            timeout_seconds=min(.1, max(.001, duration-budget.elapsed_seconds)),
            max_bytes=min(256 * 1024, max(1024, settings.query_bytes // 2)))
        report["settlement_obligations"] = obligations
        if any(item.get("truncated") or item.get("more") or item.get("unknown_reason") for item in obligations):
            report.update(complete=False, unknown_reason="settlement_query_incomplete")
        budget.check()
        notes = settlement.inspect_notes(execution_id,
            timeout_seconds=min(.1, max(.001, duration-budget.elapsed_seconds)),
            max_bytes=min(256 * 1024, max(1024, settings.query_bytes // 2)))
        merge_diagnostic_notes(report, notes, process_freshness=settings.process_freshness)
        if report.get("collection_gaps", 0) > 0:
            report.update(complete=False, unknown_reason="telemetry_collection_incomplete")
        budget.check()
    except Exception as error:
        report.update(complete=False, unknown_reason="diagnostic_observation_unavailable",
            error=f"{type(error).__name__}: {error}")
    return report if reader is None else reader._bound_report(report, budget=budget)


__all__ = ["ObservationJournal", "inspect_execution"]
