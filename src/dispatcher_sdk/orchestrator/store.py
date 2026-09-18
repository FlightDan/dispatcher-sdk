"""SQLite transaction boundary for application-neutral orchestration state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

from ..durability import configure_sqlite_connection
from ..storage_connection import connect as storage_connect
from ..content import CONTENT_SCHEMA, decode_value, encode_value
from .contracts import CommandConflict, OrchestrationError, HistoryExpired, EventCursorExpired, RunDisposed, TERMINAL, canonical


ORCHESTRATOR_SCHEMA_VERSION = 3
def _schema_marker(version: int) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS sdk_schema_meta (
 component TEXT PRIMARY KEY CHECK(component='orchestrator'),
 version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version={version}));
"""


# These table definitions are shared by the supported v2 and v3 layouts.
_COMMON_SCHEMA = """
CREATE TABLE IF NOT EXISTS sdk_runs (
 run_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sdk_run_revisions (
 run_id TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(run_id,revision));
CREATE TABLE IF NOT EXISTS sdk_run_items (
 run_id TEXT NOT NULL, section TEXT NOT NULL, item_key TEXT NOT NULL,
 value TEXT NOT NULL, PRIMARY KEY(run_id,section,item_key));
CREATE TABLE IF NOT EXISTS sdk_run_history (
 run_id TEXT NOT NULL, section TEXT NOT NULL, item_key TEXT NOT NULL,
 revision INTEGER NOT NULL, value TEXT NOT NULL,
 PRIMARY KEY(run_id,section,item_key,revision));
CREATE TABLE IF NOT EXISTS sdk_run_links (
 previous_run_id TEXT PRIMARY KEY, next_run_id TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS sdk_commands (
 run_id TEXT NOT NULL, command_id TEXT NOT NULL, digest TEXT NOT NULL,
 response TEXT NOT NULL, PRIMARY KEY(run_id,command_id));
CREATE TABLE IF NOT EXISTS sdk_events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
 revision INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sdk_events_run ON sdk_events(run_id,sequence);
CREATE TABLE IF NOT EXISTS sdk_executions (
 execution_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, task_id TEXT NOT NULL,
 attempt INTEGER NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
 command TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
 active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0,1)),
 UNIQUE(run_id,task_id,attempt));
CREATE INDEX IF NOT EXISTS sdk_executions_active ON sdk_executions(active,execution_id);
CREATE TABLE IF NOT EXISTS sdk_outbox (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
 command_id TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
 delivered INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT, last_attempt_at REAL, UNIQUE(run_id,command_id,ordinal));
CREATE INDEX IF NOT EXISTS sdk_outbox_delivery ON sdk_outbox(delivered,attempts,sequence);
CREATE TABLE IF NOT EXISTS sdk_subscriptions (
 run_id TEXT NOT NULL, name TEXT NOT NULL, cursor INTEGER NOT NULL,
 PRIMARY KEY(run_id,name));
CREATE TABLE IF NOT EXISTS sdk_recoveries (
 recovery_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, command_id TEXT NOT NULL,
 request_digest TEXT NOT NULL, source_generation INTEGER NOT NULL,
 target_generation INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN (
   'preparing','prepared','committed','activated','aborted','failed')),
 actor TEXT NOT NULL, authorization_source TEXT NOT NULL, reason TEXT NOT NULL,
 target_deployment TEXT NOT NULL, decision TEXT NOT NULL,
 application_state TEXT, owner_id TEXT NOT NULL, owner_fence INTEGER NOT NULL,
 lease_until REAL NOT NULL, waiters INTEGER NOT NULL DEFAULT 0,
 manifest TEXT NOT NULL, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
 committed_at REAL, activated_at REAL,
 UNIQUE(run_id,command_id),
 CHECK(source_generation >= 0 AND target_generation = source_generation + 1),
 CHECK(length(trim(recovery_id)) > 0 AND length(trim(run_id)) > 0),
 CHECK(length(trim(command_id)) > 0 AND length(trim(request_digest)) > 0),
 CHECK(length(trim(actor)) > 0 AND length(trim(authorization_source)) > 0),
 CHECK(length(trim(reason)) > 0 AND length(trim(target_deployment)) > 0),
 CHECK(owner_fence >= 1 AND waiters >= 0));
CREATE INDEX IF NOT EXISTS sdk_recoveries_run_status ON sdk_recoveries(run_id,status);
CREATE TABLE IF NOT EXISTS sdk_recovery_waiters (
 recovery_id TEXT NOT NULL, waiter_id TEXT NOT NULL, lease_until REAL NOT NULL,
 PRIMARY KEY(recovery_id,waiter_id));
CREATE INDEX IF NOT EXISTS sdk_recovery_waiters_expiry ON sdk_recovery_waiters(recovery_id,lease_until);
"""

# Keep the previous exact DDL available to the explicit copy-upgrade tool.
LEGACY_SCHEMA = _schema_marker(2) + _COMMON_SCHEMA
SCHEMA = _schema_marker(ORCHESTRATOR_SCHEMA_VERSION) + _COMMON_SCHEMA + CONTENT_SCHEMA + """
CREATE TABLE IF NOT EXISTS sdk_storage_identity (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), store_id TEXT NOT NULL,
 incarnation TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sdk_retention_times (
 category TEXT NOT NULL, record_key TEXT NOT NULL, created_at REAL NOT NULL,
 PRIMARY KEY(category,record_key));
CREATE TABLE IF NOT EXISTS sdk_storage_clock (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), mutation INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sdk_event_watermarks (
 run_id TEXT PRIMARY KEY, high_water INTEGER NOT NULL CHECK(high_water>=0),
 expired_through INTEGER NOT NULL CHECK(expired_through>=0 AND expired_through<=high_water));
CREATE TABLE IF NOT EXISTS sdk_expired_revisions (
 run_id TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(run_id,revision));
CREATE TABLE IF NOT EXISTS sdk_disposed_runs (
 run_id TEXT PRIMARY KEY, tombstone TEXT NOT NULL, authentication TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sdk_maintenance_receipts (
 operation_id TEXT PRIMARY KEY, plan_digest TEXT NOT NULL, result TEXT NOT NULL);
"""


def execute_schema(connection, script):
    """Execute our fixed DDL without executescript's implicit transaction commit."""
    statement = ""
    for fragment in script.split(";"):
        statement += fragment + ";"
        if sqlite3.complete_statement(statement):
            if statement.strip("; \n\t"):
                connection.execute(statement)
            statement = ""
    if statement.strip("; \n\t"):
        raise ValueError("incomplete SDK schema statement")


def initialize_storage_tracking(connection):
    """Install change tracking after all component-owned sdk tables exist."""
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'sdk_*' "
        "AND name != 'sdk_storage_clock'")]
    for table in tables:
        for action in ("INSERT", "UPDATE", "DELETE"):
            # Table names originate in the fixed SDK DDL, never an application.
            if not table.replace("_", "").isalnum():
                raise OrchestrationError("invalid SDK table name")
            connection.execute(
                f'CREATE TRIGGER IF NOT EXISTS "{table}_track_{action.lower()}" '
                f'AFTER {action} ON "{table}" BEGIN '
                'UPDATE sdk_storage_clock SET mutation=mutation+1 WHERE singleton=1; END')


class StoreMixin:
    def _connect(self, *, configure=True):
        connection = storage_connect(self.db_path, timeout=30)
        try:
            connection.row_factory = sqlite3.Row
            if configure:
                configure_sqlite_connection(connection, self.db_path, durability=self.durability)
        except BaseException:
            connection.close()
            raise
        return connection

    def _initialize_store(self):
        connection = self._connect(configure=False)
        try:
            # Do not change the persistent WAL setting on an unsupported store.
            connection.execute("BEGIN")
            self._validate_existing_store(connection)
            connection.rollback()
            configure_sqlite_connection(connection, self.db_path, durability=self.durability)
            connection.execute("BEGIN IMMEDIATE")
            if not self._validate_existing_store(connection):
                execute_schema(connection, SCHEMA)
                self._init_results(connection)
                self._init_notifications(connection)
                initialize_storage_tracking(connection)
                connection.execute("INSERT INTO sdk_storage_clock VALUES(1,0)")
                connection.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',?)",
                                   (ORCHESTRATOR_SCHEMA_VERSION,))
                import time
                import uuid
                connection.execute("INSERT INTO sdk_storage_identity VALUES(1,?,?,?)",
                                   (uuid.uuid4().hex, uuid.uuid4().hex, time.time()))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _validate_existing_store(self, connection):
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'sdk_*'")}
        if not tables:
            return False
        if "sdk_schema_meta" not in tables:
            raise OrchestrationError(
                "unsupported unversioned orchestration store; preserve the old database "
                "and deployment, or use an explicit copy upgrade")
        marker = connection.execute("SELECT component,version FROM sdk_schema_meta").fetchall()
        if len(marker) != 1 or tuple(marker[0]) != ("orchestrator", ORCHESTRATOR_SCHEMA_VERSION):
            raise OrchestrationError("unsupported orchestration schema version; use an explicit copy upgrade")
        reference = sqlite3.connect(":memory:")
        try:
            execute_schema(reference, SCHEMA)
            self._init_results(reference)
            self._init_notifications(reference)
            initialize_storage_tracking(reference)
            if self._schema_objects(connection) != self._schema_objects(reference):
                raise OrchestrationError("orchestration schema differs from its declared version")
        finally:
            reference.close()
        identity = connection.execute(
            "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
        clock = connection.execute("SELECT mutation FROM sdk_storage_clock WHERE singleton=1").fetchone()
        if (identity is None or any(type(value) is not str or not value for value in identity)
                or clock is None or type(clock[0]) is not int or clock[0] < 0):
            raise OrchestrationError("orchestration storage identity or mutation clock is missing or damaged")
        return True

    @staticmethod
    def _schema_objects(connection):
        # Both sides are SQLite's own stored DDL generated from the same fixed
        # schema. Preserve quoted literals: case/space changes inside a CHECK
        # expression can change which persisted values it accepts.
        return {(row[0], row[1]): row[2]
                for row in connection.execute(
                    "SELECT type,name,sql FROM sqlite_master WHERE (name GLOB 'sdk_*' OR tbl_name GLOB 'sdk_*') AND sql IS NOT NULL")}

    @contextmanager
    def _transaction(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            self._failpoint("before_commit")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _assert_not_disposed(connection, run_id):
        if connection.execute("SELECT 1 FROM sdk_disposed_runs WHERE run_id=?", (run_id,)).fetchone():
            raise RunDisposed(f"Run {run_id} has been permanently disposed")

    @staticmethod
    def _require_run(connection, run_id):
        StoreMixin._assert_not_disposed(connection, run_id)
        row = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise OrchestrationError("unknown run")
        return row[0]

    @staticmethod
    def _inflate(connection, run_id, revision, rows):
        state = {"run_id": run_id, "revision": revision, "generation": 0,
                 "tasks": {}, "waits": {}, "signals": {}}
        attempts = []
        for row in rows:
            section, key, value = row[0], row[1], decode_value(connection, row[2])
            if section == "root":
                state[key] = value
            elif section == "task":
                state["tasks"][key] = {**value, "attempts": []}
            elif section == "attempt":
                task_id, index = json.loads(key)
                attempts.append((task_id, index, value))
            elif section in {"waits", "signals"}:
                state[section][key] = value
            else:
                raise OrchestrationError("unknown stored Run item")
        for task_id, index, value in sorted(attempts, key=lambda item: (item[0], item[1])):
            task = state["tasks"].get(task_id)
            if task is None or index != len(task["attempts"]):
                raise OrchestrationError("stored attempt history is incomplete")
            # Historical attempts belong to the original generation unless
            # they explicitly carry the field.  Never infer a new generation
            # from the current Run view during a reopen.
            value.setdefault("generation", 0)
            task["attempts"].append(value)
        return state

    @classmethod
    def _load(cls, connection, run_id):
        revision = cls._require_run(connection, run_id)
        rows = connection.execute(
            "SELECT section,item_key,value FROM sdk_run_items WHERE run_id=?", (run_id,)).fetchall()
        return cls._inflate(connection, run_id, revision, rows)

    @classmethod
    def _load_at(cls, connection, run_id, revision):
        cls._assert_not_disposed(connection, run_id)
        if connection.execute("SELECT 1 FROM sdk_run_revisions WHERE run_id=? AND revision=?",
                              (run_id, revision)).fetchone() is None:
            if connection.execute("SELECT 1 FROM sdk_expired_revisions WHERE run_id=? AND revision=?",
                                  (run_id, revision)).fetchone():
                raise HistoryExpired(f"Run revision {revision} for {run_id} expired")
            raise OrchestrationError("unknown historical Run revision")
        rows = connection.execute(
            "SELECT h.section,h.item_key,h.value FROM sdk_run_history h JOIN "
            "(SELECT section,item_key,MAX(revision) AS revision FROM sdk_run_history "
            "WHERE run_id=? AND revision<=? GROUP BY section,item_key) last "
            "ON h.section=last.section AND h.item_key=last.item_key AND h.revision=last.revision "
            "WHERE h.run_id=?", (run_id, revision, run_id)).fetchall()
        return cls._inflate(connection, run_id, revision, rows)

    @staticmethod
    def _event_high_water(connection, run_id, cursor=None):
        row = connection.execute(
            "SELECT high_water,expired_through FROM sdk_event_watermarks WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise OrchestrationError("Run event watermark is missing")
        if cursor is not None and cursor < row[1]:
            raise EventCursorExpired(run_id, cursor, row[1])
        return row[0]

    @classmethod
    def _receipt(cls, connection, response):
        ref = json.loads(response)
        return cls._load_at(connection, ref["run_id"], ref["revision"])

    @staticmethod
    def _write_receipt(connection, run_id, command_id, fingerprint, state):
        connection.execute("INSERT INTO sdk_commands VALUES(?,?,?,?)",
                           (run_id, command_id, fingerprint,
                            canonical({"run_id": state["run_id"], "revision": state["revision"]})))

    @classmethod
    def _replay(cls, connection, run_id, command_id, fingerprint):
        cls._assert_not_disposed(connection, run_id)
        row = connection.execute(
            "SELECT digest,response FROM sdk_commands WHERE run_id=? AND command_id=?",
            (run_id, command_id)).fetchone()
        if row is None:
            return None
        if row["digest"] != fingerprint:
            raise CommandConflict("command identity already has different content")
        return cls._receipt(connection, row["response"])

    @staticmethod
    def _event(connection, state, kind, payload):
        if isinstance(payload, dict):
            payload = dict(payload)
            payload.setdefault("generation", int(state.get("generation", 0)))
        cursor = connection.execute(
            "INSERT INTO sdk_events(run_id,revision,kind,payload) VALUES(?,?,?,?)",
            (state["run_id"], state["revision"], kind, encode_value(connection, payload)))
        connection.execute(
            "INSERT INTO sdk_retention_times VALUES('event',?,(julianday('now')-2440587.5)*86400.0)",
            (str(cursor.lastrowid),))
        connection.execute(
            "INSERT INTO sdk_event_watermarks VALUES(?,?,0) ON CONFLICT(run_id) "
            "DO UPDATE SET high_water=excluded.high_water", (state["run_id"], cursor.lastrowid))

    @staticmethod
    def _item_values(state, changes=None):
        for key, value in state.items():
            if key not in {"run_id", "revision", "tasks", "waits", "signals"}:
                yield "root", key, value
        if changes is None:
            changes = {(section, key) for section in ("waits", "signals") for key in state[section]}
            for task_id, task in state["tasks"].items():
                changes.add(("task", task_id))
                changes.update(("attempt", canonical([task_id, index]))
                               for index in range(len(task["attempts"])))
        for section, key in sorted(changes):
            if section == "task":
                yield section, key, {k: v for k, v in state["tasks"][key].items() if k != "attempts"}
            elif section == "attempt":
                task_id, index = json.loads(key)
                yield section, key, state["tasks"][task_id]["attempts"][index]
            else:
                yield section, key, state[section][key]

    @classmethod
    def _save(cls, connection, state, *, changes=None):
        connection.execute("UPDATE sdk_runs SET revision=?,state=? WHERE run_id=?",
                           (state["revision"], state["state"], state["run_id"]))
        connection.execute("INSERT INTO sdk_run_revisions VALUES(?,?)",
                           (state["run_id"], state["revision"]))
        connection.execute(
            "INSERT INTO sdk_retention_times VALUES('revision',?,(julianday('now')-2440587.5)*86400.0)",
            (canonical([state["run_id"], state["revision"]]),))
        for section, key, value in cls._item_values(state, changes):
            encoded = (encode_value(connection, value)
                       if section == "root" and key in {"application_state", "input", "definition"}
                       else canonical(value))
            before = connection.execute(
                "SELECT value FROM sdk_run_items WHERE run_id=? AND section=? AND item_key=?",
                (state["run_id"], section, key)).fetchone()
            if before is not None and before[0] == encoded:
                continue
            connection.execute("INSERT INTO sdk_run_items VALUES(?,?,?,?) ON CONFLICT(run_id,section,item_key) "
                               "DO UPDATE SET value=excluded.value", (state["run_id"], section, key, encoded))
            connection.execute("INSERT INTO sdk_run_history VALUES(?,?,?,?,?)",
                               (state["run_id"], section, key, state["revision"], encoded))
            if section == "attempt":
                connection.execute("UPDATE sdk_executions SET active=? WHERE execution_id=?",
                                   (int(value["dispatched"] and value["state"] not in TERMINAL),
                                    value["command"]["execution_id"]))

    @staticmethod
    def _register_executions(connection, state, registrations):
        for task_id, index, value in registrations:
            command = canonical(value["command"])
            execution_id = value["command"]["execution_id"]
            generation = int(value.get("generation", state.get("generation", 0)))
            expected = (state["run_id"], task_id, index, generation, command)
            existing = connection.execute(
                "SELECT run_id,task_id,attempt,generation,command FROM sdk_executions WHERE execution_id=?",
                (execution_id,)).fetchone()
            if existing is not None:
                if tuple(existing) != expected:
                    raise CommandConflict("execution identity is already bound to another attempt")
                continue
            if connection.execute("SELECT 1 FROM sdk_executions WHERE idempotency_key=?",
                                  (value["command"]["idempotency_key"],)).fetchone():
                raise CommandConflict("Kernel idempotency key is already bound to another execution")
            connection.execute(
                "INSERT INTO sdk_executions(execution_id,run_id,task_id,attempt,generation,command,idempotency_key) "
                "VALUES(?,?,?,?,?,?,?)",
                (execution_id, *expected, value["command"]["idempotency_key"]))
