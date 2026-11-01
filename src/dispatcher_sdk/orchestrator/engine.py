"""Reliable operations for application-owned workflows; no implicit workflow."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Sequence, TypeVar, cast

from ..durability import Durability, validate_durability
from ..content import decode_value
from ..storage_connection import connect as storage_connect
from .contracts import (RevisionConflict, OrchestrationError, canonical, clone,
                        digest, identifier, integer, validate_operation)
from .reducer import reduce_operation
from .store import SCHEMA, LEGACY_SCHEMA, StoreMixin, execute_schema
from .transport import TransportMixin
from .results import ResultsMixin
from .notifications import NotificationsMixin
from .recovery import RecoveryMixin
from .runs import RunHistoryMixin
from .convenience import ConvenienceMixin
from .managed import ManagedRunMixin
from .types import Observation, Operation, RunEvent, RunSnapshot
from .availability import WorkAvailabilityReport, inspect_work_availability
from .cancellation import CancellationRecoveryReport, inspect_cancellation


_UNSET = object()
_OperationInput = TypeVar("_OperationInput", bound=Operation | dict[str, Any])


def _event_payload(connection, raw: str):
    payload = decode_value(connection, raw)
    if isinstance(payload, dict):
        payload.setdefault("generation", 0)
    return payload


class Orchestrator(StoreMixin, TransportMixin, ResultsMixin, NotificationsMixin, RecoveryMixin, RunHistoryMixin, ConvenienceMixin, ManagedRunMixin):
    """Use explicit commands to manage tasks backed by a public Kernel instance.

    Each call opens its own SQLite connection. Application callbacks and Kernel
    calls never execute while an orchestration write transaction is held.

    ``projection_verifier``, when configured, is a trusted host callable. For
    streamed reads it receives the credential and actual ProjectionStorage and
    must authenticate the exact pointer, both store identities, Run and revision
    while continuously enforcing immutable retention and preventing replacement.
    A logical store identity does not distinguish physical copies.
    """

    def __init__(self, db_path, kernel, *, runtime=None, clock=time.time,
                 failpoint=None, max_result_deliveries=5, durability: Durability = "full",
                 control_verifier=None, control_lease_verifier=None, projection_verifier=None,
                 settlement_journal_path=None):
        self.durability = validate_durability(durability)
        if str(db_path) == ":memory:":
            raise OrchestrationError("orchestration requires a durable SQLite file")
        self.db_path = str(Path(db_path).resolve())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.kernel = kernel
        self.runtime = runtime
        self._owns_runtime = False
        if runtime is not None and runtime.kernel is not kernel:
            raise OrchestrationError("runtime and orchestrator must share the Kernel")
        runtime_binding = getattr(runtime, 'settlement_storage', None)
        runtime_path = runtime_binding.get('path') if isinstance(runtime_binding, dict) else None
        selected_path = None if settlement_journal_path is None else str(Path(settlement_journal_path).expanduser().resolve())
        if runtime_path is not None:
            runtime_path = str(Path(runtime_path).expanduser().resolve())
            if selected_path is not None and selected_path != runtime_path:
                raise OrchestrationError('runtime and orchestrator settlement journal paths differ')
            selected_path = runtime_path
        self.settlement_journal_path = selected_path
        self.clock = clock
        self.max_result_deliveries = max_result_deliveries
        self._failpoint = failpoint or (lambda name: None)
        from .control_authorization import ControlAuthorizer
        self.control_authorizer = (ControlAuthorizer(self, control_verifier)
                                   if control_verifier is not None else None)
        if control_lease_verifier is not None and not callable(control_lease_verifier):
            raise TypeError("control_lease_verifier must be callable")
        self.control_lease_verifier = control_lease_verifier
        if projection_verifier is not None and not callable(projection_verifier):
            raise TypeError("projection_verifier must be callable")
        self.projection_verifier = projection_verifier
        self._initialize_store()

    def iter_installed_application_projection(self, run_id, *, revision, storage, credential):
        """Stream an installed current or historical projection under host retention proof.

        Exhaust the returned iterator to validate that every page was read.
        Streamed decision installation is not yet supported by this interface.
        """
        from .projection_stream import iter_installed_projection
        return iter_installed_projection(self, run_id, revision=revision, storage=storage, credential=credential)

    def close(self):
        """Close a runtime created by open_sqlite; injected runtimes stay caller-owned."""
        if self._owns_runtime:
            self.runtime.close()

    @classmethod
    def upgrade_schema(cls, path, *, durability: Durability = "full") -> dict:
        """Explicitly add recovery tables to an existing orchestrator v2 store.

        The operation is idempotent and never recreates or rewrites Run history.
        Older binaries continue to reject the upgraded store because the exact
        schema now contains recovery coordination objects.
        """
        if str(path) == ":memory:":
            raise OrchestrationError("schema upgrade requires a durable SQLite file")
        from ..durability import configure_sqlite_connection
        database = str(Path(path).resolve())
        if not Path(database).exists():
            raise OrchestrationError("cannot upgrade a missing orchestration database")
        connection = storage_connect(database, timeout=30)
        try:
            connection.row_factory = sqlite3.Row
            configure_sqlite_connection(connection, database, durability=durability)
            connection.execute("BEGIN IMMEDIATE")
            try:
                marker = connection.execute(
                    "SELECT component,version FROM sdk_schema_meta").fetchall()
            except sqlite3.DatabaseError as error:
                raise OrchestrationError("database has no declared orchestrator schema") from error
            if len(marker) != 1 or tuple(marker[0]) != ("orchestrator", 2):
                raise OrchestrationError("only a declared orchestrator schema v2 can be upgraded")
            execute_schema(connection, LEGACY_SCHEMA)
            cls._init_notifications(connection)
            executions = {row[1] for row in connection.execute("PRAGMA table_info(sdk_executions)")}
            if executions and "generation" not in executions:
                # Preserve every registration while upgrading the exact v2 DDL.
                # The legacy active index follows the renamed table and is
                # recreated after that table is dropped.
                connection.execute("ALTER TABLE sdk_executions RENAME TO sdk_executions_legacy")
                connection.execute(
                    "CREATE TABLE sdk_executions (\n"
                    " execution_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, task_id TEXT NOT NULL,\n"
                    " attempt INTEGER NOT NULL, generation INTEGER NOT NULL DEFAULT 0,\n"
                    " command TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,\n"
                    " active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0,1)),\n"
                    " UNIQUE(run_id,task_id,attempt))")
                connection.execute(
                    "INSERT INTO sdk_executions(execution_id,run_id,task_id,attempt,generation,command,"
                    "idempotency_key,active) SELECT execution_id,run_id,task_id,attempt,0,command,"
                    "idempotency_key,active FROM sdk_executions_legacy")
                connection.execute("DROP TABLE sdk_executions_legacy")
                connection.execute(
                    "CREATE INDEX sdk_executions_active ON sdk_executions(active,execution_id)")
            watches = {row[1] for row in connection.execute("PRAGMA table_info(sdk_watches)")}
            if watches and "generation" not in watches:
                # Rebuild instead of ALTER ADD: schema validation compares the
                # declared DDL, including column order, after an upgrade.
                connection.execute("ALTER TABLE sdk_watches RENAME TO sdk_watches_legacy")
                connection.execute("""CREATE TABLE sdk_watches (
                run_id TEXT NOT NULL, watch_id TEXT NOT NULL, task_id TEXT NOT NULL,
                execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
                target TEXT NOT NULL,
                max_deliveries INTEGER NOT NULL, cursor INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(run_id,watch_id))""")
                connection.execute(
                    "INSERT INTO sdk_watches(run_id,watch_id,task_id,execution_id,attempt,generation,target,"
                    "max_deliveries,cursor,completed) SELECT run_id,watch_id,task_id,execution_id,attempt,0,target,"
                    "max_deliveries,cursor,completed FROM sdk_watches_legacy")
                connection.execute("DROP TABLE sdk_watches_legacy")
            connection.commit()
            return {"path": database, "from_schema": 2, "to_schema": 2,
                    "recovery_tables": True, "run_history_preserved": True}
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @classmethod
    def open_sqlite(cls, path, handlers, *, durability: Durability = "full",
                    clock=time.time, projection_verifier=None, **runtime_options) -> Orchestrator:
        """Open one durable stack; this Orchestrator owns its Runtime lifetime."""
        from ..execution_kernel import Runtime

        # Runtime initializes the Kernel in this same file. Check existing
        # Orchestrator schema before Runtime could switch WAL or add its tables.
        if str(path) != ":memory:" and Path(path).exists():
            from ..storage import _read_only
            with _read_only(path) as connection:
                connection.execute("BEGIN")
                cls.__new__(cls)._validate_existing_store(connection)
        runtime_options.setdefault("now", clock)
        runtime = Runtime(str(path), handlers, durability=durability, **runtime_options)
        try:
            sdk = cls(path, runtime.kernel, runtime=runtime, clock=clock, durability=durability,
                      projection_verifier=projection_verifier)
        except BaseException as error:
            try:
                runtime.close()
            except BaseException as cleanup_error:
                if hasattr(error, "add_note"):
                    error.add_note(f"Runtime cleanup also failed: {cleanup_error}")
            raise
        sdk._owns_runtime = True
        return sdk

    def __enter__(self) -> Orchestrator:
        return self

    def __exit__(self, *_):
        self.close()

    def create_run(self, run_id: str, *, command_id: str, input: Any = None,
                   definition: Any = None) -> RunSnapshot:
        identifier(run_id, "run_id")
        identifier(command_id, "command_id")
        fingerprint = digest({"kind": "create_run", "input": input, "definition": definition})
        with self._transaction() as connection:
            replay = self._replay(connection, run_id, command_id, fingerprint)
            if replay is not None:
                return replay
            if connection.execute("SELECT 1 FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone():
                raise OrchestrationError("run already exists")
            state: RunSnapshot = {"run_id": run_id, "revision": 0, "state": "running",
                     "generation": 0,
                     "input": clone(input), "definition": clone(definition),
                     "application_state": None, "tasks": {}, "waits": {}, "signals": {}}
            connection.execute("INSERT INTO sdk_runs VALUES(?,?,?)", (run_id, 0, "running"))
            self._save(connection, state)
            self._event(connection, state, "run.created", {"input": input, "definition": definition})
            self._write_receipt(connection, run_id, command_id, fingerprint, state)
            return state

    def get_run(self, run_id: str) -> RunSnapshot:
        identifier(run_id, "run_id")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            return self._load(connection, run_id)
        finally:
            connection.rollback()
            connection.close()

    def get_command_receipt(self, run_id: str, command_id: str) -> RunSnapshot | None:
        """Return the original committed response, or None if not yet accepted."""
        identifier(run_id, "run_id")
        identifier(command_id, "command_id")
        connection = self._connect()
        try:
            self._assert_not_disposed(connection, run_id)
            row = connection.execute(
                "SELECT response FROM sdk_commands WHERE run_id=? AND command_id=?",
                (run_id, command_id)).fetchone()
            return self._receipt(connection, row["response"]) if row else None
        finally:
            connection.close()

    def inspect_work_availability(self, run_id: str, *, registry_revision: str | None = None,
                                  registry_revisions: Sequence[str] | None = None,
                                  sample_limit: int = 20, effect_scan_limit: int = 1000) -> WorkAvailabilityReport:
        """Read bounded scheduling facts without syncing, reaping or changing clocks."""
        return inspect_work_availability(self, run_id, registry_revision=registry_revision,
            registry_revisions=registry_revisions, sample_limit=sample_limit, effect_scan_limit=effect_scan_limit)

    def inspect_cancellation(self, run_id: str, *, task_id: str | None = None,
                             execution_id: str | None = None, source_id: str | None = None,
                             cancellation_journal_path: str | Path | None = None,
                             settlement_journal_path: str | Path | None = None,
                             limit: int = 100, after_task_id: str | None = None) -> CancellationRecoveryReport:
        """Read cancellation facts with their execution and recovery generations."""
        return inspect_cancellation(self, run_id, task_id=task_id, execution_id=execution_id,
            source_id=source_id, cancellation_journal_path=cancellation_journal_path,
            settlement_journal_path=settlement_journal_path,
            limit=limit, after_task_id=after_task_id)

    def apply_managed_operations(self, run_id: str, *, command_id: str,
                                 expected_revision: int, expected_generation: int,
                                 expected_control_epoch: int, source_resume_operation_id: str,
                                 credential, lease_credential, operations: list[_OperationInput],
                                 application_state=_UNSET, subscription=None,
                                 expected_cursor=None, advance_to=None,
                                 delegation_id: str | None = None) -> RunSnapshot:
        """Commit one controlled application decision for a resumed split-store Run.

        The host verifier must continuously hold the source resume's exclusive
        lease through commit, including serialization against cancellation,
        revocation and control changes. New commands retain caller identities;
        their execution IDs must use the managed prefix and correlation must be
        the original Run ID. This transaction does not deliver or execute work.
        """
        from ..execution_kernel import ExecutionCommandV2
        from .control_authorization import ControlAuthorizer
        from .control_lease import check_control_lease, observe_control_clock
        from .managed import _effective_orchestrator_control_lease

        identifier(run_id, "run_id")
        identifier(source_resume_operation_id, "source_resume_operation_id")
        integer(expected_generation, "expected_generation")
        integer(expected_control_epoch, "expected_control_epoch")
        if type(operations) is not list:
            raise OrchestrationError("operations must be a list")
        for operation in operations:
            op = validate_operation(operation)
            if op["kind"] in ("add_task", "new_attempt"):
                command = ExecutionCommandV2.from_dict(op["command"])
                if not command.execution_id.startswith("sdk-managed:") or command.correlation_id != run_id:
                    raise OrchestrationError("new managed command identity differs from Run")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        gate_reader = getattr(participant, "get_run_control", None)
        if not callable(identity_reader) or not callable(gate_reader):
            raise OrchestrationError("Kernel control participant is unavailable")
        observe_control_clock(self)
        verified = authorizer.verify(credential)

        def check(connection):
            authorizer.check_in_transaction(connection, verified, run_id, "apply_operations", delegation_id)
            row = connection.execute(
                "SELECT r.envelope,r.kernel_receipt,r.orchestrator_receipt,o.run_id,"
                "o.kernel_store_id,o.orchestrator_store_id,o.orchestrator_incarnation "
                "FROM sdk_revision_resumes r JOIN sdk_control_operations o ON o.operation_id=r.decision_id "
                "WHERE r.operation_id=?", (source_resume_operation_id,)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row["kernel_receipt"] is None or row["orchestrator_receipt"] is None:
                raise OrchestrationError("completed source resume is required")
            local = json.loads(row["orchestrator_receipt"])
            remote = json.loads(row["kernel_receipt"])
            envelope = json.loads(row["envelope"])
            expected = {"operation_id": source_resume_operation_id, "run_id": run_id,
                        "kernel_store_id": row["kernel_store_id"], "orchestrator_store_id": row["orchestrator_store_id"],
                        "orchestrator_incarnation": row["orchestrator_incarnation"]}
            if (type(remote) is not dict or remote.get("kind") != "revision_resume" or
                    type(remote.get("decision")) is not dict or
                    any(remote["decision"].get(key) != value for key, value in expected.items()) or
                    remote["decision"].get("generation") != expected_generation or
                    remote["decision"].get("target_control_epoch") != expected_control_epoch or
                    row["run_id"] != run_id or identity is None or tuple(identity) !=
                    (row["orchestrator_store_id"], row["orchestrator_incarnation"]) or
                    control is None or tuple(control) != ("active", expected_control_epoch, expected_generation) or
                    (local.get("operation_id"), local.get("run_id"), local.get("generation"), local.get("control_epoch"), local.get("state"),
                     local.get("kernel_store_id"), local.get("orchestrator_store_id"), local.get("orchestrator_incarnation")) !=
                    (source_resume_operation_id, run_id, expected_generation, expected_control_epoch, "active",
                     row["kernel_store_id"], row["orchestrator_store_id"], row["orchestrator_incarnation"])):
                raise RevisionConflict("managed resume source or control changed")
            lease_id, lease_fence = _effective_orchestrator_control_lease(connection, source_resume_operation_id, envelope)
            check_control_lease(self, connection, lease_credential,
                                {**expected, "lease_id": lease_id, "lease_fence": lease_fence})
            gate = gate_reader(run_id)
            if (self.kernel is not participant or identity_reader() != row["kernel_store_id"] or
                    type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) !=
                    ("active", expected_control_epoch, expected_generation)):
                raise RevisionConflict("managed Kernel control changed")

        return self._apply_operations(run_id, command_id=command_id, expected_revision=expected_revision,
            expected_generation=expected_generation, operations=operations, application_state=application_state,
            subscription=subscription, expected_cursor=expected_cursor, advance_to=advance_to,
            managed={"check": check, "source_resume_operation_id": source_resume_operation_id,
                     "expected_control_epoch": expected_control_epoch})

    def apply_operations(self, run_id: str, *, command_id: str, expected_revision: int,
                         operations: list[_OperationInput],
                         application_state=_UNSET, subscription=None,
                         expected_cursor=None, advance_to=None,
                         expected_generation: int | None = None) -> RunSnapshot:
        return self._apply_operations(run_id, command_id=command_id,
            expected_revision=expected_revision, operations=operations,
            application_state=application_state, subscription=subscription,
            expected_cursor=expected_cursor, advance_to=advance_to,
            expected_generation=expected_generation)

    def _apply_operations(self, run_id: str, *, command_id: str, expected_revision: int,
                          operations: list[_OperationInput], application_state=_UNSET,
                          subscription=None, expected_cursor=None, advance_to=None,
                          expected_generation: int | None = None, managed=None) -> RunSnapshot:
        identifier(run_id, "run_id")
        identifier(command_id, "command_id")
        integer(expected_revision, "expected_revision")
        if expected_generation is not None:
            integer(expected_generation, "expected_generation")
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
        if expected_generation is not None:
            request["expected_generation"] = expected_generation
        if application_state is not _UNSET:
            request["application_state"] = clone(application_state)
        if managed is not None:
            request.update(kind="apply_managed_operations",
                           source_resume_operation_id=managed["source_resume_operation_id"],
                           expected_control_epoch=managed["expected_control_epoch"])
        fingerprint = digest(request)
        with self._transaction() as connection:
            if managed is not None:
                managed["check"](connection)
            replay = self._replay(connection, run_id, command_id, fingerprint)
            if replay is not None:
                return replay
            state = self._load(connection, run_id)
            if managed is None and connection.execute(
                "SELECT 1 FROM sdk_managed_runs WHERE run_id=?", (run_id,)
            ).fetchone() is not None:
                raise OrchestrationError(
                    "managed Run operations require the controlled managed interface"
                )
            active_recovery = self._active_recovery(connection, run_id)
            if active_recovery is not None:
                raise OrchestrationError(
                    f"Run recovery {active_recovery['recovery_id']} is still activating")
            if state["revision"] != expected_revision:
                raise RevisionConflict("run revision changed")
            generation = int(state.get("generation", 0))
            if generation and expected_generation is None:
                raise RevisionConflict("expected_generation is required after Run recovery")
            if expected_generation is not None and expected_generation != generation:
                raise RevisionConflict("run generation changed")
            if subscription is not None:
                row = connection.execute(
                    "SELECT cursor FROM sdk_subscriptions WHERE run_id=? AND name=?",
                    (run_id, subscription)).fetchone()
                cursor = row["cursor"] if row else 0
                if cursor != expected_cursor:
                    raise RevisionConflict("subscription cursor changed")
                last = self._event_high_water(connection, run_id, cursor)
                if not cursor <= advance_to <= last:
                    raise OrchestrationError("invalid subscription advancement")
                connection.execute(
                    "INSERT INTO sdk_subscriptions VALUES(?,?,?) ON CONFLICT(run_id,name) "
                    "DO UPDATE SET cursor=excluded.cursor", (run_id, subscription, advance_to))
            intents = []
            registrations = []
            changes = set()
            for op in values:
                if op["kind"] == "watch_task":
                    self._register_watch(connection, state, op)
                else:
                    intents.extend(reduce_operation(state, op))
                    if "task_id" in op:
                        task_id = op["task_id"]
                        task = state["tasks"][task_id]
                        index = len(task["attempts"]) - 1
                        changes.add(("attempt", canonical([task_id, index])))
                        if op["kind"] in {"add_task", "set_dependencies"}:
                            changes.add(("task", task_id))
                        if op["kind"] in {"add_task", "new_attempt"}:
                            task["attempts"][index]["generation"] = generation
                            registrations.append((task_id, index, task["attempts"][index]))
                    elif "wait_id" in op:
                        changes.add(("waits", op["wait_id"]))
                    elif "signal_id" in op:
                        changes.add(("signals", op["signal_id"]))
            if application_state is not _UNSET:
                state["application_state"] = clone(application_state)
            self._register_executions(connection, state, registrations)
            for ordinal, intent in enumerate(intents):
                intent["generation"] = generation
                connection.execute(
                    "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) VALUES(?,?,?,?)",
                    (run_id, command_id, ordinal, canonical(intent)))
            state["revision"] += 1
            self._save(connection, state, changes=changes)
            self._event(connection, state, "application.decided", request)
            self._write_receipt(connection, run_id, command_id, fingerprint, state)
            if managed is not None:
                managed["check"](connection)
            return state

    def read_events(self, run_id: str, *, after: int = 0, limit: int = 100,
                    allow_expired: bool = False) -> list[RunEvent]:
        """Read retained events after a sequence cursor.

        By default, a cursor older than the Run's retention watermark raises
        :class:`EventCursorExpired`. Pass ``allow_expired=True`` to read only
        the surviving events after such a cursor; deleted events remain absent
        and sequence gaps are expected.
        """
        integer(after, "after")
        integer(limit, "limit")
        if not 1 <= limit <= 10000:
            raise OrchestrationError("limit must be between 1 and 10000")
        if type(allow_expired) is not bool:
            raise OrchestrationError("allow_expired must be a boolean")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._require_run(connection, run_id)
            self._event_high_water(connection, run_id, None if allow_expired else after)
            rows = connection.execute(
                "SELECT * FROM sdk_events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (run_id, after, limit)).fetchall()
            values = []
            for row in rows:
                values.append(cast(RunEvent, {**dict(row), "payload": _event_payload(connection, row["payload"])}))
            return values
        finally:
            connection.close()

    def acknowledge_events(self, run_id: str, *, command_id: str, expected_revision: int,
                           subscription: str, expected_cursor: int, advance_to: int,
                           expected_generation: int | None = None) -> RunSnapshot:
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
        if expected_generation is not None:
            integer(expected_generation, "expected_generation")
        request = {"kind": "acknowledge_events", "expected_revision": expected_revision,
                   "subscription": subscription, "expected_cursor": expected_cursor,
                   "advance_to": advance_to}
        if expected_generation is not None:
            request["expected_generation"] = expected_generation
        fingerprint = digest(request)
        with self._transaction() as connection:
            replay = self._replay(connection, run_id, command_id, fingerprint)
            if replay is not None:
                return replay
            state = self._load(connection, run_id)
            active_recovery = self._active_recovery(connection, run_id)
            if active_recovery is not None:
                raise OrchestrationError(
                    f"Run recovery {active_recovery['recovery_id']} is still activating")
            if state["revision"] != expected_revision:
                raise RevisionConflict("run revision changed")
            generation = int(state.get("generation", 0))
            if generation and expected_generation is None:
                raise RevisionConflict("expected_generation is required after Run recovery")
            if expected_generation is not None and expected_generation != generation:
                raise RevisionConflict("run generation changed")
            row = connection.execute(
                "SELECT cursor FROM sdk_subscriptions WHERE run_id=? AND name=?",
                (run_id, subscription)).fetchone()
            cursor = row["cursor"] if row else 0
            if cursor != expected_cursor:
                raise RevisionConflict("subscription cursor changed")
            last = self._event_high_water(connection, run_id, cursor)
            if not cursor <= advance_to <= last:
                raise OrchestrationError("invalid subscription advancement")
            connection.execute(
                "INSERT INTO sdk_subscriptions VALUES(?,?,?) ON CONFLICT(run_id,name) "
                "DO UPDATE SET cursor=excluded.cursor", (run_id, subscription, advance_to))
            self._write_receipt(connection, run_id, command_id, fingerprint, state)
            return state

    def get_subscription(self, run_id: str, name: str) -> int:
        identifier(name, "subscription")
        connection = self._connect()
        try:
            self._require_run(connection, run_id)
            row = connection.execute(
                "SELECT cursor FROM sdk_subscriptions WHERE run_id=? AND name=?", (run_id, name)).fetchone()
            return row["cursor"] if row else 0
        finally:
            connection.close()

    def observe(self, run_id: str, *, subscription: str, limit: int = 100) -> Observation:
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
            last = self._event_high_water(connection, run_id, cursor)
            return {"snapshot": state, "cursor": cursor, "event_high_watermark": last,
                    "events": [cast(RunEvent, {**dict(value),
                                                "payload": _event_payload(connection, value["payload"])})
                               for value in rows]}
        finally:
            connection.rollback()
            connection.close()
