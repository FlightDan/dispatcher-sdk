"""SQLite transaction boundary for application-neutral orchestration state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

from .contracts import CommandConflict, OrchestrationError, canonical


SCHEMA = """
CREATE TABLE IF NOT EXISTS sdk_runs (
 run_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, snapshot TEXT NOT NULL);
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
 UNIQUE(run_id,task_id,attempt));
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


class StoreMixin:
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

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
    def _load(connection, run_id):
        row = connection.execute("SELECT snapshot FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise OrchestrationError("unknown run")
        return json.loads(row["snapshot"])

    @staticmethod
    def _replay(connection, run_id, command_id, fingerprint):
        row = connection.execute(
            "SELECT digest,response FROM sdk_commands WHERE run_id=? AND command_id=?",
            (run_id, command_id)).fetchone()
        if row is None:
            return None
        if row["digest"] != fingerprint:
            raise CommandConflict("command identity already has different content")
        return json.loads(row["response"])

    @staticmethod
    def _event(connection, state, kind, payload):
        connection.execute(
            "INSERT INTO sdk_events(run_id,revision,kind,payload) VALUES(?,?,?,?)",
            (state["run_id"], state["revision"], kind, canonical(payload)))

    @staticmethod
    def _save(connection, state):
        connection.execute("UPDATE sdk_runs SET revision=?,snapshot=? WHERE run_id=?",
                           (state["revision"], canonical(state), state["run_id"]))

    @staticmethod
    def _register_executions(connection, state):
        for task_id, task in state["tasks"].items():
            for index, value in enumerate(task["attempts"]):
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
