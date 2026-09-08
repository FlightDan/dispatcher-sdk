"""Bounded Run views and explicit continuation with retained historical identity."""

from __future__ import annotations

import json

from .contracts import (CommandConflict, OrchestrationError, RevisionConflict,
                        RUN_TERMINAL, canonical, clone, digest, identifier, integer)


def _page(limit):
    integer(limit, "limit")
    if not 1 <= limit <= 10000:
        raise OrchestrationError("limit must be between 1 and 10000")


class RunHistoryMixin:
    def get_task(self, run_id: str, task_id: str) -> dict:
        """Read one task and its latest attempt without loading the whole Run."""
        identifier(run_id, "run_id")
        identifier(task_id, "task_id")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT value FROM sdk_run_items WHERE run_id=? AND section='task' AND item_key=?",
                (run_id, task_id)).fetchone()
            if row is None:
                raise OrchestrationError("unknown task")
            latest = connection.execute(
                "SELECT attempt FROM sdk_executions WHERE run_id=? AND task_id=? ORDER BY attempt DESC LIMIT 1",
                (run_id, task_id)).fetchone()
            if latest is None:
                raise OrchestrationError("stored task has no attempt")
            attempt = connection.execute(
                "SELECT value FROM sdk_run_items WHERE run_id=? AND section='attempt' AND item_key=?",
                (run_id, canonical([task_id, latest[0]]))).fetchone()
            return {**json.loads(row[0]), "attempt_count": latest[0] + 1,
                    "latest_attempt": json.loads(attempt[0])}
        finally:
            connection.rollback()
            connection.close()

    def get_run_at(self, run_id: str, revision: int) -> dict:
        """Reconstruct an immutable historical Run; cost follows returned history."""
        identifier(run_id, "run_id")
        integer(revision, "revision")
        connection = self._connect()
        try:
            return self._load_at(connection, run_id, revision)
        finally:
            connection.close()

    def get_run_summary(self, run_id: str) -> dict:
        """Read metadata/counts without deserializing task history or payloads."""
        identifier(run_id, "run_id")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            row = connection.execute("SELECT run_id,revision,state FROM sdk_runs WHERE run_id=?",
                                     (run_id,)).fetchone()
            if row is None:
                raise OrchestrationError("unknown run")
            previous = connection.execute("SELECT previous_run_id FROM sdk_run_links WHERE next_run_id=?",
                                          (run_id,)).fetchone()
            following = connection.execute("SELECT next_run_id FROM sdk_run_links WHERE previous_run_id=?",
                                           (run_id,)).fetchone()
            generation_row = connection.execute(
                "SELECT value FROM sdk_run_items WHERE run_id=? AND section='root' AND item_key='generation'",
                (run_id,)).fetchone()
            recovery = connection.execute(
                "SELECT recovery_id,status,target_generation FROM sdk_recoveries "
                "WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
                (run_id,)).fetchone()
            count = connection.execute(
                "SELECT COUNT(*) FROM sdk_run_items WHERE run_id=? AND section='task'", (run_id,)).fetchone()[0]
            return {**dict(row), "generation": 0 if generation_row is None else json.loads(generation_row[0]),
                    "recovery_id": recovery[0] if recovery else None,
                    "recovery_status": recovery[1] if recovery else None,
                    "recovery_target_generation": recovery[2] if recovery else None,
                    "task_count": count,
                    "previous_run_id": previous[0] if previous else None,
                    "next_run_id": following[0] if following else None}
        finally:
            connection.rollback()
            connection.close()

    def list_runs(self, *, after_run_id: str = "", limit: int = 100) -> tuple[dict, ...]:
        _page(limit)
        if type(after_run_id) is not str:
            raise OrchestrationError("after_run_id must be a string")
        connection = self._connect()
        try:
            return tuple(dict(row) for row in connection.execute(
                "SELECT run_id,revision,state FROM sdk_runs WHERE run_id>? ORDER BY run_id LIMIT ?",
                (after_run_id, limit)))
        finally:
            connection.close()

    def list_tasks(self, run_id: str, *, after_task_id: str = "", limit: int = 100) -> tuple[dict, ...]:
        """Page task metadata and latest attempt; use list_attempts for full history."""
        identifier(run_id, "run_id")
        _page(limit)
        if type(after_task_id) is not str:
            raise OrchestrationError("after_task_id must be a string")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._require_run(connection, run_id)
            rows = connection.execute(
                "SELECT item_key,value FROM sdk_run_items WHERE run_id=? AND section='task' "
                "AND item_key>? ORDER BY item_key LIMIT ?", (run_id, after_task_id, limit)).fetchall()
            values = []
            for row in rows:
                task = json.loads(row["value"])
                latest = connection.execute(
                    "SELECT attempt FROM sdk_executions WHERE run_id=? AND task_id=? "
                    "ORDER BY attempt DESC LIMIT 1", (run_id, row["item_key"])).fetchone()
                if latest is None:
                    raise OrchestrationError("stored task has no attempt")
                attempt = connection.execute(
                    "SELECT value FROM sdk_run_items WHERE run_id=? AND section='attempt' AND item_key=?",
                    (run_id, canonical([row["item_key"], latest[0]]))).fetchone()
                values.append({**task, "attempt_count": latest[0] + 1,
                               "latest_attempt": json.loads(attempt[0])})
            return tuple(values)
        finally:
            connection.rollback()
            connection.close()

    def list_attempts(self, run_id: str, task_id: str, *, after_attempt: int = -1,
                      limit: int = 100) -> tuple[dict, ...]:
        identifier(run_id, "run_id")
        identifier(task_id, "task_id")
        _page(limit)
        if type(after_attempt) is not int or after_attempt < -1:
            raise OrchestrationError("after_attempt must be an integer >= -1")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._require_run(connection, run_id)
            if not connection.execute(
                "SELECT 1 FROM sdk_run_items WHERE run_id=? AND section='task' AND item_key=?",
                (run_id, task_id)).fetchone():
                raise OrchestrationError("unknown task")
            indices = connection.execute(
                "SELECT attempt FROM sdk_executions WHERE run_id=? AND task_id=? AND attempt>? "
                "ORDER BY attempt LIMIT ?", (run_id, task_id, after_attempt, limit)).fetchall()
            values = []
            for index in indices:
                row = connection.execute(
                    "SELECT value FROM sdk_run_items WHERE run_id=? AND section='attempt' AND item_key=?",
                    (run_id, canonical([task_id, index[0]]))).fetchone()
                values.append({"attempt": index[0], **json.loads(row[0])})
            return tuple(values)
        finally:
            connection.rollback()
            connection.close()

    def continue_run(self, run_id: str, next_run_id: str, *, command_id: str,
                     expected_revision: int, input=None,
                     expected_generation: int | None = None) -> dict:
        """Create the next segment of a finished Run without copying its history.

        The application finishes the predecessor and supplies the next segment's
        input explicitly. Its definition is inherited. Late notifications and
        unacknowledged events of the old segment remain independently consumable.
        """
        identifier(run_id, "run_id")
        identifier(next_run_id, "next_run_id")
        identifier(command_id, "command_id")
        integer(expected_revision, "expected_revision")
        if expected_generation is not None:
            integer(expected_generation, "expected_generation")
        request = {"kind": "continue_run", "next_run_id": next_run_id,
                   "expected_revision": expected_revision, "input": input}
        if expected_generation is not None:
            request["expected_generation"] = expected_generation
        fingerprint = digest(request)
        with self._transaction() as connection:
            replay = self._replay(connection, run_id, command_id, fingerprint)
            if replay is not None:
                return replay
            previous = self._load(connection, run_id)
            active_recovery = self._active_recovery(connection, run_id)
            if active_recovery is not None:
                raise OrchestrationError(
                    f"Run recovery {active_recovery['recovery_id']} is still activating")
            if previous["revision"] != expected_revision:
                raise RevisionConflict("run revision changed")
            previous_generation = int(previous.get("generation", 0))
            if previous_generation and expected_generation is None:
                raise RevisionConflict("expected_generation is required after Run recovery")
            if expected_generation is not None and expected_generation != previous_generation:
                raise RevisionConflict("run generation changed")
            if previous["state"] not in RUN_TERMINAL:
                raise OrchestrationError("finish the current Run before continuing it")
            if connection.execute("SELECT 1 FROM sdk_runs WHERE run_id=?", (next_run_id,)).fetchone():
                raise CommandConflict("next Run identity already exists")
            if connection.execute("SELECT 1 FROM sdk_run_links WHERE previous_run_id=?", (run_id,)).fetchone():
                raise CommandConflict("Run already has a continuation; replay the original command")
            state = {"run_id": next_run_id, "revision": 0, "state": "running", "generation": 0,
                     "input": clone(input),
                     "definition": clone(previous["definition"]), "application_state": None,
                     "tasks": {}, "waits": {}, "signals": {}}
            connection.execute("INSERT INTO sdk_runs VALUES(?,?,?)", (next_run_id, 0, "running"))
            self._save(connection, state)
            connection.execute("INSERT INTO sdk_run_links VALUES(?,?)", (run_id, next_run_id))
            previous["revision"] += 1
            self._save(connection, previous, changes=set())
            self._event(connection, previous, "run.continued", {"next_run_id": next_run_id})
            self._event(connection, state, "run.created", {
                "input": input, "definition": state["definition"], "previous_run_id": run_id})
            self._write_receipt(connection, run_id, command_id, fingerprint, state)
            return state
