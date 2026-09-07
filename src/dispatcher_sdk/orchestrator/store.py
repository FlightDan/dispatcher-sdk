"""SQLite transaction boundary for application-neutral orchestration state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

from ..durability import configure_sqlite_connection
from .contracts import CommandConflict, OrchestrationError, TERMINAL, canonical


ORCHESTRATOR_SCHEMA_VERSION = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS sdk_schema_meta (
 component TEXT PRIMARY KEY CHECK(component='orchestrator'),
 version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version=2));
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
 attempt INTEGER NOT NULL, command TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
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
"""


def execute_schema(connection, script):
    """Execute our fixed DDL without executescript's implicit transaction commit."""
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


class StoreMixin:
    def _connect(self, *, configure=True):
        connection = sqlite3.connect(self.db_path, timeout=30)
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
                connection.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',?)",
                                   (ORCHESTRATOR_SCHEMA_VERSION,))
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
                "and deployment, or use a new database for schema v2")
        marker = connection.execute("SELECT component,version FROM sdk_schema_meta").fetchall()
        if len(marker) != 1 or tuple(marker[0]) != ("orchestrator", ORCHESTRATOR_SCHEMA_VERSION):
            raise OrchestrationError("unsupported orchestration schema version")
        reference = sqlite3.connect(":memory:")
        try:
            execute_schema(reference, SCHEMA)
            self._init_results(reference)
            self._init_notifications(reference)
            if self._schema_objects(connection) != self._schema_objects(reference):
                raise OrchestrationError("orchestration schema differs from its declared version")
        finally:
            reference.close()
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
    def _require_run(connection, run_id):
        row = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise OrchestrationError("unknown run")
        return row[0]

    @staticmethod
    def _inflate(run_id, revision, rows):
        state = {"run_id": run_id, "revision": revision, "tasks": {}, "waits": {}, "signals": {}}
        attempts = []
        for row in rows:
            section, key, value = row[0], row[1], json.loads(row[2])
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
            task["attempts"].append(value)
        return state

    @classmethod
    def _load(cls, connection, run_id):
        revision = cls._require_run(connection, run_id)
        rows = connection.execute(
            "SELECT section,item_key,value FROM sdk_run_items WHERE run_id=?", (run_id,)).fetchall()
        return cls._inflate(run_id, revision, rows)

    @classmethod
    def _load_at(cls, connection, run_id, revision):
        if connection.execute("SELECT 1 FROM sdk_run_revisions WHERE run_id=? AND revision=?",
                              (run_id, revision)).fetchone() is None:
            raise OrchestrationError("unknown historical Run revision")
        rows = connection.execute(
            "SELECT h.section,h.item_key,h.value FROM sdk_run_history h JOIN "
            "(SELECT section,item_key,MAX(revision) AS revision FROM sdk_run_history "
            "WHERE run_id=? AND revision<=? GROUP BY section,item_key) last "
            "ON h.section=last.section AND h.item_key=last.item_key AND h.revision=last.revision "
            "WHERE h.run_id=?", (run_id, revision, run_id)).fetchall()
        return cls._inflate(run_id, revision, rows)

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
        connection.execute(
            "INSERT INTO sdk_events(run_id,revision,kind,payload) VALUES(?,?,?,?)",
            (state["run_id"], state["revision"], kind, canonical(payload)))

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
        for section, key, value in cls._item_values(state, changes):
            encoded = canonical(value)
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
            expected = (state["run_id"], task_id, index, command)
            existing = connection.execute(
                "SELECT run_id,task_id,attempt,command FROM sdk_executions WHERE execution_id=?",
                (execution_id,)).fetchone()
            if existing is not None:
                if tuple(existing) != expected:
                    raise CommandConflict("execution identity is already bound to another attempt")
                continue
            if connection.execute("SELECT 1 FROM sdk_executions WHERE idempotency_key=?",
                                  (value["command"]["idempotency_key"],)).fetchone():
                raise CommandConflict("Kernel idempotency key is already bound to another execution")
            connection.execute(
                "INSERT INTO sdk_executions(execution_id,run_id,task_id,attempt,command,idempotency_key) VALUES(?,?,?,?,?,?)",
                (execution_id, *expected, value["command"]["idempotency_key"]))
