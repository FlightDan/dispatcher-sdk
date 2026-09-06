"""Idempotent Kernel delivery and factual result synchronization."""

from __future__ import annotations

import json

from ..execution_kernel import (CASConflictError, EffectRecoveryRequiredError,
                                ExecutionCommandV2, ExecutionNotFoundError,
                                ExecutionSnapshot, StaleFenceError)
from .contracts import OrchestrationError, TERMINAL, canonical, integer


class TransportMixin:
    def delivery_messages(self, execution_ids=None, *, limit=100, pending_only=False):
        """Inspect command delivery failures without reading private storage."""
        integer(limit, "limit")
        if limit < 1 or type(pending_only) is not bool:
            raise OrchestrationError("invalid delivery query")
        selected = None
        if execution_ids is not None:
            selected = set(execution_ids)
            if any(type(value) is not str or not value.strip() for value in selected):
                raise OrchestrationError("invalid execution identifier")
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM sdk_outbox ORDER BY sequence").fetchall()
        finally:
            connection.close()
        records = []
        for row in rows:
            intent = json.loads(row["payload"])
            if selected is not None and intent["execution_id"] not in selected:
                continue
            if pending_only and row["delivered"]:
                continue
            records.append({"message_id": row["sequence"], "run_id": row["run_id"],
                            "command_id": row["command_id"], "execution_id": intent["execution_id"],
                            "kind": intent["kind"], "intent": intent,
                            "state": "delivered" if row["delivered"] else
                                "failed" if row["last_error"] is not None else "pending",
                            "attempts": row["attempts"], "last_attempt_at": row["last_attempt_at"],
                            "last_error": json.loads(row["last_error"]) if row["last_error"] else None})
            if len(records) >= limit:
                break
        return tuple(records)

    def _delivery_failed(self, row, error):
        detail = {"type": type(error).__name__, "message": str(error)}
        with self._transaction() as connection:
            # A concurrent successful flusher wins over an older failure.
            changed = connection.execute(
                "UPDATE sdk_outbox SET attempts=attempts+1,last_error=?,last_attempt_at=? "
                "WHERE sequence=? AND delivered=0", (canonical(detail), self.clock(), row["sequence"]),
            ).rowcount
            if changed:
                state = self._load(connection, row["run_id"])
                state["revision"] += 1
                self._save(connection, state)
                self._event(connection, state, "delivery.failed", {
                    "message_id": row["sequence"], "intent": json.loads(row["payload"]), "error": detail})

    def _delivery_command(self, intent):
        command = ExecutionCommandV2.from_dict(intent["command"])
        if command.execution_id != intent["execution_id"]:
            raise OrchestrationError("delivery command identity mismatch")
        connection = self._connect()
        try:
            row = connection.execute("SELECT command FROM sdk_executions WHERE execution_id=?",
                                     (command.execution_id,)).fetchone()
        finally:
            connection.close()
        if row is None or row["command"] != canonical(command.to_dict()):
            raise OrchestrationError("delivery differs from accepted command")
        return command

    @staticmethod
    def _check_delivery_snapshot(snapshot, command):
        if (type(snapshot) is not ExecutionSnapshot or snapshot.execution_id != command.execution_id
                or canonical(snapshot.command.to_dict()) != canonical(command.to_dict())):
            raise OrchestrationError("Kernel execution command does not match the accepted command")
        return snapshot

    def flush(self, *, limit=100):
        """Isolate failed messages; replay accepted deliveries without rerunning executions.

        Least-attempted messages go first, so a bounded batch of broken commands
        cannot permanently block later executions or their cancellation intents.
        Selection inspects pending cancellations and defers their matching
        dispatches; limit bounds the number of actual delivery attempts.
        """
        integer(limit, "limit")
        if limit < 1:
            raise OrchestrationError("limit must be positive")
        connection = self._connect()
        try:
            pending = connection.execute(
                "SELECT sequence,run_id,payload FROM sdk_outbox WHERE delivered=0 "
                "ORDER BY attempts,sequence").fetchall()
        finally:
            connection.close()
        messages = [(row, json.loads(row["payload"])) for row in pending]
        cancellations = {intent["execution_id"] for _, intent in messages
                         if intent["kind"] == "cancel"}
        # A durable cancel supersedes an as-yet-undelivered dispatch for the
        # same execution. Preserve fair ordering for every other execution;
        # a broken cancel must not block unrelated dispatches.
        selected = [(row, intent) for row, intent in messages
                    if intent["kind"] != "dispatch"
                    or intent["execution_id"] not in cancellations][:limit]
        count = 0
        for row, intent in selected:
            execution_id = intent["execution_id"]
            try:
                command = self._delivery_command(intent)
                if intent["kind"] == "dispatch":
                    try:
                        snapshot = self.kernel.get(execution_id)
                    except ExecutionNotFoundError:
                        snapshot = (self.runtime or self.kernel).submit(command)
                    # An already accepted command, especially a cancelled one,
                    # must not be submitted through runtime validation again.
                    self._check_delivery_snapshot(snapshot, command)
                elif intent["kind"] == "cancel":
                    self._cancel_execution(execution_id, intent["reason"], command)
                else:
                    raise OrchestrationError("unknown persisted delivery intent")
            except Exception as error:
                self._delivery_failed(row, error)
                continue
            # This is deliberately outside the operational-error handler: a
            # crash after Kernel acceptance must leave the receipt uncommitted.
            self._failpoint("after_kernel_delivery")
            try:
                self.sync_execution(execution_id)
            except Exception as error:
                self._delivery_failed(row, error)
                continue
            with self._transaction() as connection:
                completed = connection.execute(
                    "UPDATE sdk_outbox SET delivered=1,attempts=attempts+1,last_error=NULL,last_attempt_at=? "
                    "WHERE sequence=? AND delivered=0", (self.clock(), row["sequence"])).rowcount
            count += completed
        return count

    def _cancel_execution(self, execution_id, reason, command):
        for _ in range(8):
            try:
                snapshot = self.kernel.get(execution_id)
            except ExecutionNotFoundError:
                # The first visible record must already be cancelled; a
                # submit/cancel pair would let another worker run the command.
                # If a racing dispatch won first, this returns its existing
                # snapshot and the runtime cancellation below handles cleanup.
                snapshot = self.kernel.cancel_before_accept(command, reason=reason)
            self._check_delivery_snapshot(snapshot, command)
            # Re-enter runtime cancellation for cancelled executions to finish process cleanup.
            if snapshot.state in TERMINAL and snapshot.state != "cancelled":
                return snapshot
            try:
                return (self.runtime or self.kernel).cancel(
                    execution_id, expected_revision=snapshot.revision, reason=reason)
            except (CASConflictError, StaleFenceError):
                continue
            except EffectRecoveryRequiredError:
                return self.kernel.get(execution_id)
        raise RevisionError("Kernel cancellation raced repeatedly; retry delivery")

    def sync_execution(self, execution_id):
        """Persist only facts read from the bound Kernel, never caller-supplied results."""
        snapshot = self.kernel.get(execution_id)
        if type(snapshot) is not ExecutionSnapshot or snapshot.execution_id != execution_id:
            raise OrchestrationError("Kernel returned a different execution")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT run_id,task_id,attempt,command FROM sdk_executions WHERE execution_id=?",
                (execution_id,)).fetchone()
            if row is None:
                raise OrchestrationError("execution was not registered through this SDK")
            if canonical(snapshot.command.to_dict()) != row["command"]:
                raise OrchestrationError("Kernel execution command does not match the accepted command")
            state = self._load(connection, row["run_id"])
            current = state["tasks"][row["task_id"]]["attempts"][row["attempt"]]
            if not current["dispatched"]:
                raise OrchestrationError("execution was not explicitly dispatched")
            if snapshot.revision < current["kernel_revision"]:
                # A concurrent synchronizer has already persisted a newer authoritative fact.
                return snapshot
            if snapshot.revision == current["kernel_revision"]:
                if canonical(current["kernel_snapshot"]) != canonical(snapshot.to_dict()):
                    raise OrchestrationError("Kernel changed an immutable execution revision")
                return snapshot
            if current["kernel_revision"] and current["state"] in TERMINAL:
                raise OrchestrationError("terminal execution history cannot be rewritten")
            current.update(state=snapshot.state, kernel_revision=snapshot.revision,
                           result=snapshot.result.to_dict() if snapshot.result else None,
                           kernel_snapshot=snapshot.to_dict())
            state["revision"] += 1
            self._save(connection, state)
            self._event(connection, state, "execution.observed", {
                "task_id": row["task_id"], "attempt": row["attempt"],
                "execution_id": execution_id, "snapshot": snapshot.to_dict()})
        return snapshot

    def get_execution(self, execution_id):
        return self.sync_execution(execution_id)

    def inspect_execution(self, execution_id):
        """Read registered Kernel authority without ingestion or a state write.

        Administrative inspection remains available when result ingestion needs
        repair. It does not bypass the accepted execution command's identity.
        """
        connection = self._connect()
        try:
            row = connection.execute("SELECT command FROM sdk_executions WHERE execution_id=?",
                                     (execution_id,)).fetchone()
        finally:
            connection.close()
        if row is None:
            raise ExecutionNotFoundError("execution was not registered through this SDK")
        snapshot = self.kernel.get(execution_id)
        if (type(snapshot) is not ExecutionSnapshot or snapshot.execution_id != execution_id
                or canonical(snapshot.command.to_dict()) != row["command"]):
            raise OrchestrationError("Kernel execution command does not match the accepted command")
        return snapshot

    def sync(self):
        """Poll known dispatched executions without making any application decision."""
        connection = self._connect()
        try:
            rows = connection.execute("SELECT execution_id FROM sdk_executions").fetchall()
        finally:
            connection.close()
        count = 0
        for row in rows:
            try:
                self.sync_execution(row["execution_id"])
                count += 1
            except ExecutionNotFoundError:
                continue
        return count

    def resolve_effect(self, effect_id, *, decision, response, expected_revision, recovery_id):
        """Forward an explicit uncertainty-resolution decision to the Kernel."""
        before = self.kernel.get_effect(effect_id)
        # Establish SDK ownership and exact command identity before changing an
        # external fact. An error after resolution must not mask an unauthorized write.
        self.sync_execution(before.execution_id)
        result = self.kernel.resolve_effect(
            effect_id, decision=decision, response=response,
            expected_revision=expected_revision, recovery_id=recovery_id)
        self.sync_execution(result.execution_id)
        return result

    def kernel_events(self, after_sequence, *, limit=100):
        return self.kernel.events_since(after_sequence, limit)


class RevisionError(OrchestrationError):
    """A transient Kernel CAS race left a delivery pending."""
