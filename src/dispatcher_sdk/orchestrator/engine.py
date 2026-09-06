"""Reliable operations for application-owned workflows; no implicit workflow."""

from __future__ import annotations

import json
from pathlib import Path
import time

from .contracts import (RevisionConflict, OrchestrationError, canonical, clone,
                        digest, identifier, integer, validate_operation)
from .reducer import reduce_operation
from .store import SCHEMA, StoreMixin
from .transport import TransportMixin
from .results import ResultsMixin
from .notifications import NotificationsMixin


_UNSET = object()


class Orchestrator(StoreMixin, TransportMixin, ResultsMixin, NotificationsMixin):
    """Use explicit commands to manage tasks backed by a public Kernel instance.

    Each call opens its own SQLite connection. Application callbacks and Kernel
    calls never execute while an orchestration write transaction is held.
    """

    def __init__(self, db_path, kernel, *, runtime=None, clock=time.time,
                 failpoint=None, max_result_deliveries=5):
        if str(db_path) == ":memory:":
            raise OrchestrationError("orchestration requires a durable SQLite file")
        self.db_path = str(Path(db_path).resolve())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.kernel = kernel
        self.runtime = runtime
        if runtime is not None and runtime.kernel is not kernel:
            raise OrchestrationError("runtime and orchestrator must share the Kernel")
        self.clock = clock
        self.max_result_deliveries = max_result_deliveries
        self._failpoint = failpoint or (lambda name: None)
        connection = self._connect()
        try:
            connection.executescript(SCHEMA)
            self._init_results(connection)
            self._init_notifications(connection)
            connection.commit()
        finally:
            connection.close()

    def close(self):
        """Connections are operation-scoped; the caller owns Kernel/runtime lifetime."""

    def create_run(self, run_id, *, command_id, input=None, definition=None):
        identifier(run_id, "run_id")
        identifier(command_id, "command_id")
        fingerprint = digest({"kind": "create_run", "input": input, "definition": definition})
        with self._transaction() as connection:
            replay = self._replay(connection, run_id, command_id, fingerprint)
            if replay is not None:
                return replay
            if connection.execute("SELECT 1 FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone():
                raise OrchestrationError("run already exists")
            state = {"run_id": run_id, "revision": 0, "state": "running",
                     "input": clone(input), "definition": clone(definition),
                     "application_state": None, "tasks": {}, "waits": {}, "signals": {}}
            connection.execute("INSERT INTO sdk_runs VALUES(?,?,?)", (run_id, 0, canonical(state)))
            self._event(connection, state, "run.created", {"input": input, "definition": definition})
            connection.execute("INSERT INTO sdk_commands VALUES(?,?,?,?)",
                               (run_id, command_id, fingerprint, canonical(state)))
            return state

    def get_run(self, run_id):
        identifier(run_id, "run_id")
        connection = self._connect()
        try:
            return self._load(connection, run_id)
        finally:
            connection.close()

    def get_command_receipt(self, run_id, command_id):
        """Return the original committed response, or None if not yet accepted."""
        identifier(run_id, "run_id")
        identifier(command_id, "command_id")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT response FROM sdk_commands WHERE run_id=? AND command_id=?",
                (run_id, command_id)).fetchone()
            return json.loads(row["response"]) if row else None
        finally:
            connection.close()

    def apply_operations(self, run_id, *, command_id, expected_revision, operations,
                         application_state=_UNSET, subscription=None,
                         expected_cursor=None, advance_to=None):
        identifier(run_id, "run_id")
        identifier(command_id, "command_id")
        integer(expected_revision, "expected_revision")
        if type(operations) is not list:
            raise OrchestrationError("operations must be a list")
        values = [validate_operation(value) for value in operations]
        if subscription is None:
            if expected_cursor is not None or advance_to is not None:
                raise OrchestrationError("cursor fields require subscription")
        else:
            identifier(subscription, "subscription")
            integer(expected_cursor, "expected_cursor")
            integer(advance_to, "advance_to")
        request = {"kind": "apply_operations", "expected_revision": expected_revision,
                   "operations": values, "subscription": subscription,
                   "expected_cursor": expected_cursor, "advance_to": advance_to,
                   "has_application_state": application_state is not _UNSET}
        if application_state is not _UNSET:
            request["application_state"] = clone(application_state)
        fingerprint = digest(request)
        with self._transaction() as connection:
            replay = self._replay(connection, run_id, command_id, fingerprint)
            if replay is not None:
                return replay
            state = self._load(connection, run_id)
            if state["revision"] != expected_revision:
                raise RevisionConflict("run revision changed")
            if subscription is not None:
                row = connection.execute(
                    "SELECT cursor FROM sdk_subscriptions WHERE run_id=? AND name=?",
                    (run_id, subscription)).fetchone()
                cursor = row["cursor"] if row else 0
                if cursor != expected_cursor:
                    raise RevisionConflict("subscription cursor changed")
                last = connection.execute(
                    "SELECT COALESCE(MAX(sequence),0) FROM sdk_events WHERE run_id=?",
                    (run_id,)).fetchone()[0]
                if not cursor <= advance_to <= last:
                    raise OrchestrationError("invalid subscription advancement")
                connection.execute(
                    "INSERT INTO sdk_subscriptions VALUES(?,?,?) ON CONFLICT(run_id,name) "
                    "DO UPDATE SET cursor=excluded.cursor", (run_id, subscription, advance_to))
            intents = []
            for op in values:
                if op["kind"] == "watch_task":
                    self._register_watch(connection, state, op)
                else:
                    intents.extend(reduce_operation(state, op))
            if application_state is not _UNSET:
                state["application_state"] = clone(application_state)
            self._register_executions(connection, state)
            for ordinal, intent in enumerate(intents):
                connection.execute(
                    "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) VALUES(?,?,?,?)",
                    (run_id, command_id, ordinal, canonical(intent)))
            state["revision"] += 1
            self._save(connection, state)
            self._event(connection, state, "application.decided", request)
            connection.execute("INSERT INTO sdk_commands VALUES(?,?,?,?)",
                               (run_id, command_id, fingerprint, canonical(state)))
            return state

    def read_events(self, run_id, *, after=0, limit=100):
        integer(after, "after")
        integer(limit, "limit")
        if not 1 <= limit <= 10000:
            raise OrchestrationError("limit must be between 1 and 10000")
        connection = self._connect()
        try:
            self._load(connection, run_id)
            rows = connection.execute(
                "SELECT * FROM sdk_events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (run_id, after, limit)).fetchall()
            return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
        finally:
            connection.close()

    def acknowledge_events(self, run_id, *, command_id, expected_revision,
                           subscription, expected_cursor, advance_to):
        """Commit cursor-only progress without producing another event to consume.

        A read-only application decision still checks the observed Run revision
        and cursor. Its immutable command receipt is durable, but it does not
        change the Run snapshot or create a self-perpetuating event stream.
        """
        identifier(run_id, "run_id")
        identifier(command_id, "command_id")
        identifier(subscription, "subscription")
        integer(expected_revision, "expected_revision")
        integer(expected_cursor, "expected_cursor")
        integer(advance_to, "advance_to")
        fingerprint = digest({"kind": "acknowledge_events", "expected_revision": expected_revision,
                              "subscription": subscription, "expected_cursor": expected_cursor,
                              "advance_to": advance_to})
        with self._transaction() as connection:
            replay = self._replay(connection, run_id, command_id, fingerprint)
            if replay is not None:
                return replay
            state = self._load(connection, run_id)
            if state["revision"] != expected_revision:
                raise RevisionConflict("run revision changed")
            row = connection.execute(
                "SELECT cursor FROM sdk_subscriptions WHERE run_id=? AND name=?",
                (run_id, subscription)).fetchone()
            cursor = row["cursor"] if row else 0
            if cursor != expected_cursor:
                raise RevisionConflict("subscription cursor changed")
            last = connection.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM sdk_events WHERE run_id=?", (run_id,)).fetchone()[0]
            if not cursor <= advance_to <= last:
                raise OrchestrationError("invalid subscription advancement")
            connection.execute(
                "INSERT INTO sdk_subscriptions VALUES(?,?,?) ON CONFLICT(run_id,name) "
                "DO UPDATE SET cursor=excluded.cursor", (run_id, subscription, advance_to))
            connection.execute("INSERT INTO sdk_commands VALUES(?,?,?,?)",
                               (run_id, command_id, fingerprint, canonical(state)))
            return state

    def get_subscription(self, run_id, name):
        identifier(name, "subscription")
        connection = self._connect()
        try:
            self._load(connection, run_id)
            row = connection.execute(
                "SELECT cursor FROM sdk_subscriptions WHERE run_id=? AND name=?", (run_id, name)).fetchone()
            return row["cursor"] if row else 0
        finally:
            connection.close()

    def observe(self, run_id, *, subscription, limit=100):
        """Read Run state, consumer position and a batch from one SQLite snapshot."""
        identifier(run_id, "run_id")
        identifier(subscription, "subscription")
        integer(limit, "limit")
        if not 1 <= limit <= 10000:
            raise OrchestrationError("limit must be between 1 and 10000")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            state = self._load(connection, run_id)
            row = connection.execute(
                "SELECT cursor FROM sdk_subscriptions WHERE run_id=? AND name=?",
                (run_id, subscription)).fetchone()
            cursor = row["cursor"] if row else 0
            rows = connection.execute(
                "SELECT * FROM sdk_events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (run_id, cursor, limit)).fetchall()
            last = connection.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM sdk_events WHERE run_id=?", (run_id,)).fetchone()[0]
            return {"snapshot": state, "cursor": cursor, "event_high_watermark": last,
                    "events": [{**dict(value), "payload": json.loads(value["payload"])} for value in rows]}
        finally:
            connection.rollback()
            connection.close()
