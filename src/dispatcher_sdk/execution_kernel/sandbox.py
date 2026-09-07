"""Durable sandbox effects and cleanup after the local worker has stopped."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any
from uuid import uuid4

from ..durability import Durability, configure_sqlite_connection, validate_durability
from .contracts import _json_value
from .errors import HandlerExecutionError
from .sandbox_contracts import SandboxBackend, SandboxObservation, SandboxOutcomeUnknown, SandboxPolicyError, SandboxSpec


_DDL = """CREATE TABLE sandbox_operations (
 execution_id TEXT PRIMARY KEY, effect_id TEXT NOT NULL UNIQUE,
 operation_key TEXT NOT NULL UNIQUE, backend_name TEXT NOT NULL, backend_revision TEXT NOT NULL,
 handler_id TEXT NOT NULL, handler_contract_version INTEGER NOT NULL,
 lease_id TEXT NOT NULL, attempt INTEGER NOT NULL, fence INTEGER NOT NULL,
 spec TEXT NOT NULL, phase TEXT NOT NULL, sandbox_id TEXT, command_id TEXT,
 result TEXT, cleanup_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(cleanup_confirmed IN (0,1)),
 cleanup_evidence TEXT)"""
_HISTORY_DDL = """CREATE TABLE sandbox_history (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, execution_id TEXT NOT NULL,
 operation_key TEXT NOT NULL UNIQUE, record TEXT NOT NULL)"""
_META_DDL = "CREATE TABLE sandbox_meta (version INTEGER NOT NULL CHECK(version=1), store_id TEXT)"


def validate_sandbox_schema(connection) -> None:
    objects = dict(connection.execute(
        "SELECT name,sql FROM sqlite_master WHERE name GLOB 'sandbox_*' AND sql IS NOT NULL"))
    if objects != {"sandbox_meta": _META_DDL, "sandbox_operations": _DDL, "sandbox_history": _HISTORY_DDL}:
        raise ValueError("sandbox journal schema differs from declared version")
    rows = connection.execute("SELECT version,store_id FROM sandbox_meta").fetchall()
    if len(rows) != 1 or rows[0][0] != 1 or (rows[0][1] is not None and (type(rows[0][1]) is not str or not rows[0][1])):
        raise ValueError("unsupported sandbox journal version or store binding")


def _json(value: Any) -> str:
    _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class SandboxJournal:
    """Versioned, inspectable lifecycle journal; no provider calls inside a transaction."""

    def __init__(self, path: str, *, durability: Durability = "full") -> None:
        if str(path) == ":memory:":
            raise ValueError("sandbox journal requires a durable file path")
        self.path = str(Path(path).resolve())
        self.durability = validate_durability(durability)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            tables = {r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'sandbox_*'")}
            if tables:
                validate_sandbox_schema(connection)
            else:
                connection.execute(_META_DDL)
                connection.execute("INSERT INTO sandbox_meta VALUES(1,NULL)")
                connection.execute(_DDL)
                connection.execute(_HISTORY_DDL)
            connection.commit()

    def _bind_store(self, store_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT store_id FROM sandbox_meta").fetchone()[0]
            if current is not None and current != store_id:
                raise ValueError("sandbox journal belongs to another Kernel store")
            connection.execute("UPDATE sandbox_meta SET store_id=?", (store_id,))
            connection.commit()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            configure_sqlite_connection(connection, self.path, durability=self.durability)
            yield connection
        finally:
            connection.close()

    def get(self, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM sandbox_operations WHERE execution_id=?",
                                     (execution_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["spec"] = json.loads(result["spec"])
        result["result"] = None if result["result"] is None else json.loads(result["result"])
        result["cleanup_confirmed"] = bool(result["cleanup_confirmed"])
        result["cleanup_evidence"] = None if result["cleanup_evidence"] is None else json.loads(result["cleanup_evidence"])
        return result

    def history(self, execution_id: str, *, after_sequence: int = 0, limit: int = 100):
        if type(limit) is not int or not 1 <= limit <= 1000 or type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("invalid history page")
        with self._connect() as connection:
            return tuple({"sequence": row[0], "record": json.loads(row[1])} for row in connection.execute(
                "SELECT sequence,record FROM sandbox_history WHERE execution_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (execution_id, after_sequence, limit)))

    def confirm_cleanup(self, execution_id: str, *, operation_key: str, evidence: Any) -> None:
        """Record an explicit external proof of disposal, fenced to one generation.

        The caller owns this recovery decision. An empty metadata search is not
        proof. This neither resolves Kernel effects nor authorizes script replay.
        """
        if evidence is None or evidence == {} or evidence == "":
            raise ValueError("external cleanup evidence is required")
        self._update(execution_id, operation_key=operation_key, cleanup_confirmed=1,
                     cleanup_evidence={"source": "external_recovery", "evidence": evidence})

    def pending(self, *, after_execution_id: str = "", limit: int = 100) -> tuple[dict[str, Any], ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connect() as connection:
            ids = [r[0] for r in connection.execute(
                "SELECT execution_id FROM sandbox_operations WHERE cleanup_confirmed=0 AND execution_id>? "
                "ORDER BY execution_id LIMIT ?", (after_execution_id, limit))]
        return tuple(self.get(identity) for identity in ids)

    def _begin(self, execution_id: str, effect_id: str, backend_name: str, revision: str,
               handler_id: str, handler_contract_version: int, spec: SandboxSpec, *, lease=None) -> str:
        operation_key = uuid4().hex
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT * FROM sandbox_operations WHERE execution_id=?", (execution_id,)).fetchone()
            if previous is not None:
                if lease is not None and lease.fence <= previous["fence"]:
                    raise SandboxOutcomeUnknown("sandbox generation requires a newer execution fence")
                if not previous["cleanup_confirmed"]:
                    raise SandboxOutcomeUnknown("previous sandbox generation has no confirmed disposal")
                if (previous["effect_id"], previous["backend_name"], previous["backend_revision"],
                    previous["handler_id"], previous["handler_contract_version"], previous["spec"]) != (
                    effect_id, backend_name, revision, handler_id, handler_contract_version, _json(spec.to_payload())):
                    raise SandboxOutcomeUnknown("sandbox generation identity differs from original intent")
                # This is reachable only inside a newly authorized Kernel perform
                # claim after explicit not_applied recovery; never from a poll.
                connection.execute("INSERT INTO sandbox_history(execution_id,operation_key,record) VALUES(?,?,?)",
                    (execution_id, previous["operation_key"], _json(dict(previous))))
                connection.execute("DELETE FROM sandbox_operations WHERE execution_id=?", (execution_id,))
            try:
                connection.execute(
                    "INSERT INTO sandbox_operations(execution_id,effect_id,operation_key,backend_name,backend_revision,"
                    "handler_id,handler_contract_version,spec,lease_id,attempt,fence,phase) VALUES(?,?,?,?,?,?,?,?,?,?,?,'creating')",
                    (execution_id, effect_id, operation_key, backend_name, revision,
                     handler_id, handler_contract_version, _json(spec.to_payload()),
                     lease.lease_id if lease else "", lease.attempt if lease else 0, lease.fence if lease else 0))
                connection.commit()
            except sqlite3.IntegrityError as error:
                raise SandboxOutcomeUnknown("sandbox intent already exists; explicit effect recovery is required") from error
        return operation_key

    def _update(self, execution_id: str, *, operation_key: str, **values: Any) -> None:
        if not values or not set(values) <= {"phase", "sandbox_id", "command_id", "result", "cleanup_confirmed", "cleanup_evidence"}:
            raise ValueError("invalid sandbox journal update")
        if "result" in values:
            values["result"] = _json(values["result"])
        if "cleanup_evidence" in values:
            values["cleanup_evidence"] = _json(values["cleanup_evidence"])
        with self._connect() as connection:
            cursor = connection.execute("UPDATE sandbox_operations SET " +
                ",".join(key + "=?" for key in values) + " WHERE execution_id=? AND operation_key=?",
                (*values.values(), execution_id, operation_key))
            if cursor.rowcount != 1:
                raise SandboxOutcomeUnknown("sandbox intent is missing")
            connection.commit()


@dataclass(frozen=True)
class SandboxHandler:
    """Register one provider as a normal fenced, process-contained Kernel handler.

    The provider configuration must be immutable and pickleable. Runtime cleanup
    uses this same configuration after the child is gone. A lost create/start
    response never authorizes an automatic repeat of that operation.
    """

    backend: SandboxBackend
    journal_path: str
    operation_timeout: float = 10.0
    poll_interval: float = 0.1
    durability: Durability = "full"
    requires_process_isolation = True

    def __post_init__(self):
        validate_durability(self.durability)
        for name in ("name", "revision"):
            value = getattr(self.backend, name, None)
            if type(value) is not str or not value.strip():
                raise ValueError(f"backend {name} must be nonempty")
        if not isinstance(self.backend, SandboxBackend):
            raise TypeError("backend does not implement SandboxBackend")
        if str(self.journal_path) == ":memory:":
            raise ValueError("sandbox journal must be file-backed")
        object.__setattr__(self, "journal_path", str(Path(self.journal_path).resolve()))
        for name in ("operation_timeout", "poll_interval"):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")

    @property
    def __execution_kernel_revision__(self):
        return "sdk-sandbox-v1:" + self.backend.name + ":" + self.backend.revision

    @property
    def handler_id(self) -> str:
        return "sdk.sandbox." + self.backend.name

    def journal(self) -> SandboxJournal:
        return SandboxJournal(self.journal_path, durability=self.durability)

    @staticmethod
    def effect_id(execution_id: str) -> str:
        return "sandbox:" + hashlib.sha256(execution_id.encode()).hexdigest()

    def cleanup(self, execution_id: str, *, operation_key: str | None = None,
                max_fence: int | None = None) -> bool:
        """Only call after the execution's local process is confirmed stopped.

        Missing create identity remains unknown even if a metadata search is
        empty. Found resources are disposed, but creation uncertainty is retained.
        This method does not resolve the Kernel effect or infer script outcomes.
        """
        journal = self.journal()
        record = journal.get(execution_id)
        if record is None:
            return True
        if operation_key is not None and record["operation_key"] != operation_key:
            raise SandboxOutcomeUnknown("sandbox generation changed before cleanup")
        if max_fence is not None and record["fence"] > max_fence:
            # A new generation can only replace an already disposed predecessor.
            # An old invocation has no authority over that new generation.
            return True
        if (record["backend_name"], record["backend_revision"]) != (self.backend.name, self.backend.revision):
            raise SandboxOutcomeUnknown("cleanup requires the original backend configuration")
        if record["cleanup_confirmed"]:
            return True
        sandbox_id = record["sandbox_id"]
        if sandbox_id is None:
            identities = self.backend.find(record["operation_key"], timeout=self.operation_timeout)
            for identity in identities:
                self.backend.terminate(identity, timeout=self.operation_timeout)
            return False
        confirmed = self.backend.terminate(sandbox_id, timeout=self.operation_timeout)
        if confirmed is not True:
            return False
        journal._update(execution_id, operation_key=record["operation_key"], cleanup_confirmed=1,
            cleanup_evidence={"source": "backend.terminate", "sandbox_id": sandbox_id})
        return True

    def __call__(self, payload: Any, context) -> Any:
        try:
            spec = SandboxSpec.from_payload(payload)
        except (TypeError, ValueError) as error:
            raise HandlerExecutionError("invalid_sandbox_spec", str(error)) from error
        validator = getattr(self.backend, "validate", None)
        if validator is not None:
            try:
                validator(spec)
            except SandboxPolicyError as error:
                raise HandlerExecutionError(error.code, str(error)) from error
        execution_id = context.command.execution_id
        effect_id = self.effect_id(execution_id)
        journal = self.journal()

        def active():
            if not context.is_active():
                raise SandboxOutcomeUnknown("sandbox execution authority was revoked")

        def perform():
            active()
            operation_key = journal._begin(execution_id, effect_id, self.backend.name, self.backend.revision,
                context.command.handler_id, context.command.handler_contract_version, spec, lease=context.lease)
            active()
            sandbox_id = self.backend.create(spec, operation_key=operation_key, timeout=self.operation_timeout)
            if type(sandbox_id) is not str or not sandbox_id.strip():
                raise SandboxOutcomeUnknown("backend did not return a sandbox identity")
            journal._update(execution_id, operation_key=operation_key, phase="created", sandbox_id=sandbox_id)
            active()
            journal._update(execution_id, operation_key=operation_key, phase="starting")
            command_id = self.backend.start(sandbox_id, spec, timeout=self.operation_timeout)
            if type(command_id) is not str or not command_id.strip():
                raise SandboxOutcomeUnknown("backend did not return a command identity")
            journal._update(execution_id, operation_key=operation_key, phase="running", command_id=command_id)
            while True:
                active()
                observation = self.backend.inspect(sandbox_id, command_id, timeout=self.operation_timeout)
                if observation.state == "unknown":
                    raise SandboxOutcomeUnknown("backend cannot establish command outcome")
                if observation.state != "running":
                    break
                time.sleep(self.poll_interval)
            active()
            output = self.backend.collect(sandbox_id, command_id, spec, timeout=self.operation_timeout)
            result = {"state": observation.state, "exit_code": observation.exit_code,
                      "output": output, "sandbox_id": sandbox_id, "command_id": command_id}
            journal._update(execution_id, operation_key=operation_key, phase="collected", result=result)
            return result

        result = context.effects.execute_once(effect_id, "sandbox.execute",
            {"spec": spec.to_payload(), "backend_revision": self.backend.revision,
             "journal_path": self.journal_path}, perform)
        record = journal.get(execution_id)
        if record is None:
            raise SandboxOutcomeUnknown("committed sandbox result has no lifecycle journal")
        try:
            if type(result) is not dict or set(result) != {"state", "exit_code", "output", "sandbox_id", "command_id"}:
                raise ValueError("sandbox result fields are invalid")
            if result["state"] not in {"succeeded", "failed"}:
                raise ValueError("sandbox recovery requires a terminal observation")
            SandboxObservation(result["state"], exit_code=result["exit_code"])
            for name in ("sandbox_id", "command_id"):
                if (type(result[name]) is not str or not result[name].strip()
                        or "\0" in result[name] or len(result[name]) > 4096):
                    raise ValueError("sandbox recovery requires stable resource identities")
                if record[name] is not None and record[name] != result[name]:
                    raise ValueError("sandbox recovery result contradicts the recorded resource identity")
            if record["result"] is not None and _json(record["result"]) != _json(result):
                raise ValueError("sandbox recovery result contradicts the durably collected result")
        except (TypeError, ValueError) as error:
            raise HandlerExecutionError("invalid_sandbox_recovery", str(error)) from error
        if record["result"] is None:
            journal._update(execution_id, operation_key=record["operation_key"],
                phase="collected", result=result, sandbox_id=result["sandbox_id"], command_id=result["command_id"])

        def dispose():
            if not self.cleanup(execution_id, operation_key=record["operation_key"]):
                raise SandboxOutcomeUnknown("sandbox disposal has not been confirmed")
            return {"cleanup_confirmed": True}

        disposal = context.effects.execute_once(effect_id + ":dispose:" + record["operation_key"],
            "sandbox.dispose", {"operation_key": record["operation_key"],
                                "backend_name": self.backend.name, "backend_revision": self.backend.revision}, dispose)
        if type(disposal) is not dict or set(disposal) != {"cleanup_confirmed"} or disposal["cleanup_confirmed"] is not True:
            raise HandlerExecutionError("invalid_disposal_recovery", "disposal recovery must confirm resource absence")
        if not journal.get(execution_id)["cleanup_confirmed"]:
            journal._update(execution_id, operation_key=record["operation_key"], cleanup_confirmed=1,
                cleanup_evidence={"source": "committed_disposal_effect"})
        if result["state"] == "failed":
            raise HandlerExecutionError("sandbox_exit_nonzero",
                f"sandbox exited with status {result['exit_code']}", details=result)
        return result


def sandbox_handlers(backend: SandboxBackend, journal_path: str, **options) -> dict[tuple[str, int], SandboxHandler]:
    """Return bindings for a built-in or community provider; no private API needed."""
    handler = SandboxHandler(backend, journal_path, **options)
    return {(handler.handler_id, 1): handler}
