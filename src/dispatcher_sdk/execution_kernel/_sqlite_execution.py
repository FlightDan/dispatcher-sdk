"""SQLite execution submission, leasing, and lease-expiry recovery."""

from __future__ import annotations

from collections.abc import Sequence
import json
import math
from typing import Optional
import os
from pathlib import Path
import sqlite3
import time
import uuid

from ._sqlite_base import MAX_SQLITE_INTEGER, SQLiteBase, encode_json
from ._sqlite_completion import ExecutionCompletionMixin
from ._sqlite_effects import EffectStoreMixin
from ._sqlite_outbox import ResultOutboxMixin
from ._sqlite_recovery import EffectRecoveryMixin
from .supervision import SupervisionMixin
from .budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from .contracts import ExecutionCommandV2, ExecutionLease, ExecutionSnapshot
from .claiming import claim_predicate
from .errors import (
    BudgetScanContinuation,
    LifecycleReceiptExpiredError,
    CASConflictError,
    ExecutionNotFoundError,
    IdempotencyConflictError,
    StorageIsolationError,
    StaleFenceError,
)
from .transitions import reduce_state
from .projection_gate import ProjectionGateMixin
from .control_takeover import ControlTakeoverMixin


class _LifecycleDenied(StorageIsolationError):
    """Host explicitly denied visibility or an operation."""


def _claim_revisions(
    registry_revision: Optional[str], registry_revisions: Optional[Sequence[str]]
) -> Optional[tuple[str, ...]]:
    """Validate before entering the transaction, including its logical clock."""

    if registry_revision is not None:
        if registry_revisions is not None:
            raise ValueError("registry_revision and registry_revisions are mutually exclusive")
        if type(registry_revision) is not str or not registry_revision.strip():
            raise ValueError("registry_revision must be a non-empty string")
        return (registry_revision,)
    if registry_revisions is None:
        return None
    if isinstance(registry_revisions, (str, bytes, bytearray)) or not isinstance(registry_revisions, Sequence):
        raise ValueError("registry_revisions must be a non-empty sequence of non-empty strings")
    values = tuple(registry_revisions)
    if not values or any(type(value) is not str or not value.strip() for value in values):
        raise ValueError("registry_revisions must be a non-empty sequence of non-empty strings")
    return tuple(dict.fromkeys(values))


MANAGED_EXECUTION_PREFIX = "sdk-managed:"
_PAUSE_RECEIPT_BYTES = 1024 * 1024
_PAUSE_SQL_TICKS = 500


def _next_claim_row(connection, timestamp: float, revisions: Optional[tuple[str, ...]],
                    execution_id: str | None = None, exclude_execution_ids: tuple[str, ...] = (), after=None):
    predicate, parameters = claim_predicate(timestamp, revisions, alias="k")
    predicate += " AND NOT EXISTS (SELECT 1 FROM kernel_supervisor_obligations so " \
                 "WHERE so.execution_id=k.execution_id AND so.attempt=k.attempt " \
                 "AND so.fence=k.fence AND so.resolution_json IS NULL)"
    predicate += " AND NOT EXISTS (SELECT 1 FROM kernel_lifecycle_producers p WHERE p.execution_id=k.execution_id AND (p.state='open' OR EXISTS (SELECT 1 FROM kernel_lifecycle_outbox o WHERE o.token=p.token AND o.delivered=0)))"
    if exclude_execution_ids:
        predicate += " AND k.execution_id NOT IN (" + ",".join("?" for _ in exclude_execution_ids) + ")"
        parameters = (*parameters, *exclude_execution_ids)
    if execution_id is not None:
        predicate += " AND k.execution_id = ?"
        parameters = (*parameters, execution_id)
    else:
        if after is not None:
            predicate += " AND (k.created_at > ? OR (k.created_at = ? AND k.execution_id > ?))"
            parameters = (*parameters, after[0], after[0], after[1])
        predicate += " AND NOT EXISTS (SELECT 1 FROM kernel_execution_limits l " \
                     "WHERE l.execution_id=k.execution_id AND l.parent_execution_id IS NOT NULL)"
        # An unresolved root keeps its own admission fence, while unrelated
        # eligible work remains claimable. Explicit targets retain the normal
        # authority check and surface their unknown clock instead of skipping.
        predicate += " AND NOT EXISTS (SELECT 1 FROM kernel_budget_samples s " \
                     "WHERE s.execution_id=k.execution_id)"
    return connection.execute(
        """SELECT k.* FROM kernel_executions AS k WHERE """ + predicate + """
           AND (
               (k.execution_id NOT GLOB 'sdk-managed:*' AND NOT EXISTS (
                   SELECT 1 FROM kernel_managed_executions AS membership
                   WHERE membership.execution_id = k.execution_id
               ))
               OR EXISTS (
                   SELECT 1 FROM kernel_managed_executions AS m
                   JOIN kernel_run_controls AS c ON c.run_id = m.run_id
                   WHERE m.execution_id = k.execution_id
                     AND NOT EXISTS (SELECT 1 FROM kernel_control_pause_receipts b WHERE b.run_id=m.run_id
                         AND NOT EXISTS (SELECT 1 FROM kernel_resume_receipts r WHERE r.run_id=b.run_id
                             AND b.operation_id IN (r.barrier_operation_id,r.completion_operation_id))
                         AND COALESCE((c.state='pausing' AND m.drain_allowed=1 AND m.generation=c.generation
                             AND json_extract(b.receipt_json,'$.kind')='pause_barrier'
                             AND json_extract(b.receipt_json,'$.control_epoch')=c.control_epoch
                             AND instr(',' || substr(json_extract(b.receipt_json,'$.drain_execution_ids'),2,
                                 length(json_extract(b.receipt_json,'$.drain_execution_ids'))-2) || ',',
                                 ',' || json_quote(m.execution_id) || ',')>0),0)=0)
                     AND (
                         (
                             c.claims_used < c.max_claims
                             AND c.deadline_at > ?
                             AND (
                                 (c.state = 'active' AND m.generation = c.generation)
                                 OR (c.state = 'pausing' AND m.drain_allowed = 1)
                             )
                         )
                     )
               )
           )
           ORDER BY k.created_at, k.execution_id LIMIT 1""",
        (*parameters, timestamp),
    ).fetchone()


class SQLiteKernel(
    ControlTakeoverMixin,
    ProjectionGateMixin,
    SupervisionMixin,
    ExecutionCompletionMixin,
    EffectRecoveryMixin,
    EffectStoreMixin,
    ResultOutboxMixin,
    SQLiteBase,
):
    """Durable v3 kernel constrained to exact ``kernel_*`` schema objects."""

    def _assert_child_claim(self, connection, execution_id: str, timestamp: float) -> None:
        limits = connection.execute(
            "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (execution_id,)
        ).fetchone()
        if limits is None or limits["parent_execution_id"] is None:
            return
        self._assert_budget_clock(connection, execution_id)
        parent = self._get_row(connection, limits["parent_execution_id"])
        if (parent["state"] != "running"
                or (parent["attempt"], parent["fence"]) != (limits["parent_attempt"], limits["parent_fence"])
                or parent["lease_expires_at"] is None or parent["lease_expires_at"] <= timestamp):
            raise StaleFenceError("child claim belongs to a revoked parent lease")
        self._authorize_managed_operation(
            connection, parent["execution_id"], timestamp=timestamp, operation="child claim"
        )
        parent_limits = connection.execute(
            "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (parent["execution_id"],)
        ).fetchone()
        if (parent_limits is None or parent_limits["entry_state"] != "confirmed"
                or (parent_limits["entry_attempt"], parent_limits["entry_fence"]) != (
                    parent["attempt"], parent["fence"])):
            raise CASConflictError("child claim requires confirmed parent handler entry")
        parent_envelope = BudgetEnvelope.from_dict(json.loads(parent_limits["envelope_json"]))
        # Admission consumes committed clock evidence. The invocation wrapper
        # owns the next guarded wall sample before actual business entry.
        sample = sample_clock(wall_time=parent_envelope.checkpoint.wall_at)
        for stored in (parent_limits, limits):
            envelope = BudgetEnvelope.from_dict(json.loads(stored["envelope_json"]))
            if not any(item.origin_id == "execution:" + parent["execution_id"]
                       and item.source == "execution" for item in envelope.constraints):
                raise CASConflictError("child claim has no confirmed parent execution cutoff")
            view = envelope.view(sample=sample)
            if view.clock_status != "trusted":
                raise BudgetClockUnknownError(view.unknown_reason)
            if not view.remaining_work_seconds:
                raise CASConflictError("child claim inherited work deadline has elapsed")

    @staticmethod
    def _managed_run_id(value: str) -> str:
        if type(value) is not str or not value.strip():
            raise ValueError("run_id must be a non-empty string")
        return value

    @staticmethod
    def _managed_generation(value: int, name: str = "generation") -> int:
        if type(value) is not int or value < 0 or value > MAX_SQLITE_INTEGER:
            raise ValueError(
                f"{name} must be a non-negative SQLite integer"
            )
        return value

    @staticmethod
    def _normalize_drain_ids(values) -> tuple[str, ...]:
        if isinstance(values, (str, bytes, bytearray)) or not isinstance(
            values, (Sequence, set, frozenset)
        ):
            raise ValueError("drain_execution_ids must be a sequence or set of identifiers")
        identifiers = tuple(values)
        if any(type(value) is not str or not value.strip() for value in identifiers):
            raise ValueError("drain_execution_ids must contain non-empty strings")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("drain_execution_ids must not contain duplicates")
        return tuple(sorted(identifiers))

    @staticmethod
    def _run_control_value(row, drain_ids=()) -> dict:
        return {
            "run_id": row[0],
            "control_epoch": row[1],
            "generation": row[2],
            "state": row[3],
            "max_claims": row[4],
            "claims_used": row[5],
            "deadline_at": row[6],
            "drain_execution_ids": tuple(drain_ids),
        }

    def _require_shared_transaction(self, connection) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be a sqlite3.Connection")
        if not connection.in_transaction:
            raise RuntimeError("caller must hold an open SQLite transaction")
        if self.db_path == ":memory:":
            raise ValueError("managed Run controls require a durable Kernel database")
        if connection is self._connection:
            same_store = True
        else:
            main = next(
                (row[2] for row in connection.execute("PRAGMA database_list") if row[1] == "main"),
                None,
            )
            try:
                same_store = main is not None and os.path.samefile(main, self.db_path)
            except OSError:
                same_store = False
        if not same_store:
            raise StorageIsolationError(
                "control transaction must use the Kernel's main SQLite database"
            )
        marker = connection.execute(
            "SELECT component,schema_version FROM kernel_schema_meta"
        ).fetchone()
        from ._sqlite_schema import KERNEL_STORAGE_SCHEMA_VERSION

        if tuple(marker or ()) != ("execution_kernel", KERNEL_STORAGE_SCHEMA_VERSION):
            raise StorageIsolationError("control transaction requires the current Kernel schema")

    def _run_control_snapshot(self, connection, run_id: str):
        row = connection.execute(
            "SELECT run_id,control_epoch,generation,state,max_claims,claims_used,deadline_at "
            "FROM kernel_run_controls WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        drain_ids = tuple(
            row[0]
            for row in connection.execute(
                "SELECT execution_id FROM kernel_managed_executions "
                "WHERE run_id=? AND drain_allowed=1 ORDER BY execution_id",
                (run_id,),
            )
        )
        return self._run_control_value(row, drain_ids)

    def _verified_authority(self, credential, run_id: str, action: str, timestamp: float,
                            *, generation: int | None = None, control_epoch: int | None = None,
                            control_lease: tuple[str, int, str, str, str, str, str, int, int] | None = None,
                            initial_admission: dict | None = None, drain_admission: dict | None = None,
                            clock_check=None):
        if self._authority_verifier is None or credential is None:
            raise StorageIsolationError("protected Run requires a host-verified credential")
        try:
            result = self._authority_verifier(credential)
            principal = result["principal"]
            permissions = result["permissions"]
            expires_at = self._number(result["expires_at"], "authority expiry", minimum=0.0)
            if (type(principal) is not str or not principal.strip() or len(principal.encode("utf-8")) > 4096 or expires_at <= timestamp
                    or not any(tuple(item) == (run_id, action) for item in permissions)):
                raise ValueError("credential scope or expiry is invalid")
            if generation is not None and (result.get("run_id"), result.get("generation"), result.get("control_epoch")) != (
                    run_id, generation, control_epoch):
                raise ValueError("worker credential binding is invalid")
            if drain_admission is not None:
                admission = result["drain_admission"]
                if (type(admission) is not dict or admission.get("allowed") is not True
                        or any(admission.get(k) != v for k, v in drain_admission.items())
                        or not any(tuple(item) == (run_id, "kernel:drain") for item in permissions)
                        or any(type(admission.get(k)) is not str or not admission[k].strip() for k in
                               ("orchestrator_store_id", "orchestrator_incarnation"))
                        or self._number(admission.get("expires_at"), "drain admission expiry", minimum=0.0) <= timestamp):
                    raise ValueError("drain admission is unavailable")
            if control_lease is not None:
                lease = result["control_lease"]
                if (type(lease) is not dict or lease.get("held") is not True
                        or (lease.get("lease_id"), lease.get("lease_fence")) != control_lease[:2]
                        or self._number(lease.get("expires_at"), "control lease expiry", minimum=0.0) <= timestamp):
                    raise ValueError("exclusive control lease is unavailable")
                admission = result["global_admission"]
                if (type(admission) is not dict or admission.get("open") is not True
                        or (admission.get("operation_id"), admission.get("orchestrator_store_id"),
                            admission.get("orchestrator_incarnation"), admission.get("kernel_store_id")) != control_lease[2:6]):
                    raise ValueError("global admission is unavailable")
                receipt = admission["orchestrator_receipt"]
                if (type(receipt) is not dict
                        or set(receipt) != {"operation_id", "run_id", "generation", "control_epoch", "state", "committed_at",
                                            "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"}
                        or (receipt["operation_id"], receipt["run_id"], receipt["generation"],
                            receipt["control_epoch"], receipt["state"]) !=
                           (control_lease[2], control_lease[6], control_lease[7], control_lease[8], "active")
                        or (receipt["kernel_store_id"], receipt["orchestrator_store_id"], receipt["orchestrator_incarnation"]) !=
                           (control_lease[5], control_lease[3], control_lease[4])):
                    raise ValueError("global admission receipt differs")
                self._number(receipt["committed_at"], "admission commit time", minimum=0.0)
            if initial_admission is not None:
                admission = result["global_admission"]
                if (type(admission) is not dict or admission.get("open") is not True
                        or (admission.get("run_id"), admission.get("generation"), admission.get("control_epoch"))
                        != (run_id, generation, control_epoch)
                        or encode_json(admission.get("orchestrator_receipt")) != encode_json(initial_admission)):
                    raise ValueError("initial global admission is unavailable")
            if clock_check is not None:
                fresh = clock_check()
                if expires_at <= fresh or (drain_admission is not None and
                        self._number(result["drain_admission"].get("expires_at"), "drain admission expiry", minimum=0.0) <= fresh):
                    raise ValueError("worker authorization expired during verification")
                if control_lease is not None and self._number(result["control_lease"].get("expires_at"), "control lease expiry", minimum=0.0) <= fresh:
                    raise ValueError("control lease expired during verification")
        except Exception:
            raise StorageIsolationError("host verification did not authorize the protected Run action") from None
        return principal, expires_at

    def protect_run_authority(self, run_id: str, *, generation: int, expected_epoch: int,
                              worker_credential) -> None:
        """Install a host-verified worker binding while a Run is paused.

        This does not activate the Run or establish external writer isolation.
        """
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        if type(expected_epoch) is not int or expected_epoch < 0:
            raise ValueError("expected_epoch must be non-negative")
        with self._transaction() as (connection, timestamp):
            self._verified_authority(self._worker_credential, run_id, "kernel:manage_authority", timestamp)
            principal, expiry = self._verified_authority(worker_credential, run_id, "kernel:worker", timestamp,
                                                         generation=generation, control_epoch=expected_epoch)
            control = connection.execute("SELECT generation,control_epoch,state FROM kernel_run_controls WHERE run_id=?",
                                         (run_id,)).fetchone()
            if control is None or tuple(control) != (generation, expected_epoch, "paused"):
                raise CASConflictError("protected authority requires the expected paused Run")
            old = connection.execute("SELECT generation,control_epoch,principal,expires_at,revoked_at "
                                     "FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone()
            if old is not None:
                if tuple(old) != (generation, expected_epoch, principal, expiry, None):
                    raise CASConflictError("protected Run authority already differs or is revoked")
                return
            connection.execute("INSERT INTO kernel_run_authorities VALUES(?,?,?,?,?,NULL)",
                               (run_id, generation, expected_epoch, principal, expiry))

    def bind_initial_admission(self, credential, *, expected_receipt: dict) -> None:
        """Bind the host-authenticated initial Orchestrator open receipt while paused."""
        with self._transaction() as (connection, timestamp):
            try:
                verified = self._authority_verifier(credential)
                receipt = verified["initial_admission_receipt"]
                fields = {"operation_id", "run_id", "generation", "control_epoch", "state", "committed_at",
                          "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"}
                if type(receipt) is not dict or set(receipt) != fields or encode_json(receipt) != encode_json(expected_receipt):
                    raise ValueError("unexpected initial admission receipt")
                for key in ("operation_id", "run_id", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"):
                    if type(receipt[key]) is not str or not receipt[key].strip():
                        raise ValueError("invalid participant identity")
                for key in ("generation", "control_epoch"):
                    if type(receipt[key]) is not int or not 0 <= receipt[key] <= MAX_SQLITE_INTEGER:
                        raise ValueError("invalid initial version")
                self._number(receipt["committed_at"], "admission commit time", minimum=0.0)
                expiry = self._number(verified["expires_at"], "authority expiry", minimum=0.0)
                principal = verified["principal"]
                if (receipt["state"] != "active" or expiry <= timestamp or type(principal) is not str
                        or not principal.strip() or len(principal.encode("utf-8")) > 4096
                        or not any(tuple(p) == (receipt["run_id"], "kernel:bind_initial") for p in verified["permissions"])):
                    raise ValueError("initial admission not authorized")
            except Exception:
                raise StorageIsolationError("host verification did not authorize initial admission binding") from None
            run_id = receipt["run_id"]
            identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT generation,control_epoch,state FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone()
            authority = connection.execute("SELECT generation,control_epoch,expires_at,revoked_at FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone()
            if (identity is None or identity[0] != receipt["kernel_store_id"] or control is None
                    or tuple(control) != (receipt["generation"], receipt["control_epoch"], "paused")
                    or authority is None or (authority[0], authority[1]) != (receipt["generation"], receipt["control_epoch"])
                    or authority[2] <= timestamp or authority[3] is not None):
                raise CASConflictError("initial admission participant or authority changed")
            old = connection.execute("SELECT binding_json FROM kernel_initial_admission_bindings WHERE run_id=?", (run_id,)).fetchone()
            if old is not None:
                if encode_json(json.loads(old[0])) != encode_json(receipt):
                    raise CASConflictError("initial admission already has a different binding")
            else:
                connection.execute("INSERT INTO kernel_initial_admission_bindings VALUES(?,?)", (run_id, encode_json(receipt)))
            try:
                again = self._authority_verifier(credential)
                if (encode_json(again["initial_admission_receipt"]) != encode_json(receipt) or again["principal"] != principal
                        or self._number(again["expires_at"], "authority expiry", minimum=0.0) != expiry
                        or not any(tuple(p) == (run_id, "kernel:bind_initial") for p in again["permissions"])):
                    raise ValueError("initial admission authority changed")
                if min(expiry, authority[2]) <= self._advance_clock(connection):
                    raise ValueError("initial admission authority expired")
            except Exception:
                raise StorageIsolationError("host no longer authorizes initial admission binding") from None

    def revoke_run_authority(self, run_id: str, *, generation: int, expected_epoch: int) -> None:
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        with self._transaction() as (connection, timestamp):
            self._verified_authority(self._worker_credential, run_id, "kernel:manage_authority", timestamp)
            row = connection.execute("SELECT generation,control_epoch,revoked_at FROM kernel_run_authorities WHERE run_id=?",
                                     (run_id,)).fetchone()
            if row is None or (row[0], row[1]) != (generation, expected_epoch):
                raise CASConflictError("protected Run authority changed")
            if row[2] is None:
                connection.execute("UPDATE kernel_run_authorities SET revoked_at=? WHERE run_id=? AND revoked_at IS NULL",
                                   (timestamp, run_id))

    def import_legacy_run(self, adoption_credential, *, worker_credential, expected_adoption: dict) -> dict:
        """Install one ordered, bounded page of a host-authenticated legacy Run.

        The host verifier must independently verify a currently held writer-isolation
        lease and the provenance of each contiguous membership page and budget.
        A terminal page must attest that the entire membership has been supplied.
        It must be bounded and nonblocking because it executes in the write transaction.
        The host must enforce isolation continuously, including between pages and
        through transaction commit, and reject any revoked lease on revalidation.
        This local import neither renews that lease nor enables execution.
        """
        with self._transaction() as (connection, timestamp):
            if self._authority_verifier is None or adoption_credential is None:
                raise StorageIsolationError("legacy import requires a host verifier")
            try:
                verified = self._authority_verifier(adoption_credential)
                manifest = verified["adoption"]
                fields = {"operation_id", "run_id", "kernel_store_id", "orchestrator_store_id",
                          "orchestrator_incarnation", "generation", "membership", "membership_source",
                          "membership_complete", "page_seq", "claims_used", "claims_source", "max_claims", "deadline_at",
                          "isolation_lease_id", "isolation_expires_at", "isolation_held"}
                if type(manifest) is not dict or set(manifest) != fields or type(expected_adoption) is not dict:
                    raise ValueError("invalid adoption envelope")
                if encode_json(manifest) != encode_json(expected_adoption):
                    raise ValueError("unexpected adoption envelope")
                for key in ("operation_id", "run_id", "kernel_store_id", "orchestrator_store_id",
                            "orchestrator_incarnation", "membership_source", "claims_source", "isolation_lease_id"):
                    if type(manifest[key]) is not str or not manifest[key].strip():
                        raise ValueError("missing evidence identity")
                for key in ("generation", "claims_used", "max_claims", "page_seq"):
                    if type(manifest[key]) is not int or not 0 <= manifest[key] <= MAX_SQLITE_INTEGER:
                        raise ValueError("invalid budget or generation")
                if manifest["claims_used"] > manifest["max_claims"]:
                    raise ValueError("consumed budget exceeds limit")
                deadline = self._number(manifest["deadline_at"], "deadline_at", minimum=0.0)
                lease_expiry = self._number(manifest["isolation_expires_at"], "isolation expiry", minimum=0.0)
                expiry = self._number(verified["expires_at"], "authority expiry", minimum=0.0)
                if (type(manifest["membership_complete"]) is not bool or manifest["isolation_held"] is not True
                        or lease_expiry <= timestamp or expiry <= timestamp
                        or type(verified["principal"]) is not str or not verified["principal"].strip()
                        or len(verified["principal"].encode("utf-8")) > 4096
                        or not any(tuple(p) == (manifest["run_id"], "kernel:import_legacy") for p in verified["permissions"])):
                    raise ValueError("incomplete or expired evidence")
                members = manifest["membership"]
                if type(members) is not list or len(members) > 512:
                    raise ValueError("membership exceeds bounded import")
                ids = set()
                for member in members:
                    if (type(member) is not dict or set(member) not in ({"execution_id", "status"}, {"execution_id", "status", "command"})
                            or type(member["execution_id"]) is not str or not member["execution_id"].strip()
                            or member["status"] not in ("accepted", "pending") or member["execution_id"] in ids):
                        raise ValueError("invalid membership")
                    if member["status"] == "pending":
                        if set(member) != {"execution_id", "status", "command"}:
                            raise ValueError("pending membership requires its original command")
                        command = ExecutionCommandV2.from_dict(member["command"])
                        if command.execution_id != member["execution_id"] or command.correlation_id != manifest["run_id"]:
                            raise ValueError("pending command identity differs")
                    elif "command" in member:
                        raise ValueError("accepted membership has no pending command")
                    ids.add(member["execution_id"])
                if [member["execution_id"] for member in members] != sorted(ids):
                    raise ValueError("membership page is not strictly ordered")
                if not members and not manifest["membership_complete"]:
                    raise ValueError("empty nonterminal membership page")
            except Exception:
                raise StorageIsolationError("host verification did not authorize legacy import") from None
            run_id = manifest["run_id"]
            worker, worker_expiry = self._verified_authority(worker_credential, run_id, "kernel:worker", timestamp,
                generation=manifest["generation"], control_epoch=0)
            store = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if store is None or store[0] != manifest["kernel_store_id"]:
                raise CASConflictError("legacy import participant identity differs")
            prior = connection.execute("SELECT receipt_json FROM kernel_legacy_import_pages WHERE operation_id=? AND page_seq=?",
                                       (manifest["operation_id"], manifest["page_seq"])).fetchone()
            if prior:
                receipt = json.loads(prior[0])
                original_page = dict(receipt["adoption"])
                renewed_page = dict(manifest)
                original_page.pop("isolation_expires_at")
                renewed_page.pop("isolation_expires_at")
                if (encode_json(original_page) != encode_json(renewed_page)
                        or receipt["worker_principal"] != worker or receipt["worker_expires_at"] != worker_expiry):
                    raise CASConflictError("legacy import already has different content")
                return receipt
            initial = connection.execute("SELECT receipt_json FROM kernel_legacy_imports WHERE operation_id=?",
                                         (manifest["operation_id"],)).fetchone()
            last = connection.execute("SELECT page_seq,receipt_json FROM kernel_legacy_import_pages WHERE operation_id=? "
                                      "ORDER BY page_seq DESC LIMIT 1", (manifest["operation_id"],)).fetchone()
            if initial is None:
                if manifest["page_seq"] != 0 or connection.execute("SELECT 1 FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone():
                    raise CASConflictError("legacy import must begin at page zero with a new Run")
            else:
                original = json.loads(initial[0])
                initial_manifest = original["adoption"]
                immutable = fields - {"membership", "membership_complete", "page_seq", "isolation_expires_at"}
                if (any(manifest[key] != initial_manifest[key] for key in immutable)
                        or original["worker_principal"] != worker or original["worker_expires_at"] != worker_expiry
                        or last is None or last[0] + 1 != manifest["page_seq"]):
                    raise CASConflictError("legacy import page does not continue its original operation")
                previous = json.loads(last[1])
                if previous["adoption"]["membership_complete"]:
                    raise CASConflictError("legacy import is already complete")
                if members and previous["cursor"] is not None and members[0]["execution_id"] <= previous["cursor"]:
                    raise CASConflictError("legacy membership cursor did not advance")
                authority = connection.execute("SELECT generation,control_epoch,principal,expires_at,revoked_at "
                                               "FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone()
                control = connection.execute("SELECT generation,control_epoch,state FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone()
                if (authority is None or tuple(authority) != (manifest["generation"], 0, worker, worker_expiry, None)
                        or control is None or tuple(control) != (manifest["generation"], 0, "paused")):
                    raise CASConflictError("legacy import authority or control changed")
            for member in members:
                execution_id = member["execution_id"]
                exists = connection.execute("SELECT 1 FROM kernel_executions WHERE execution_id=?", (execution_id,)).fetchone()
                registered = connection.execute("SELECT 1 FROM kernel_managed_executions WHERE execution_id=?", (execution_id,)).fetchone()
                if registered or bool(exists) != (member["status"] == "accepted"):
                    raise CASConflictError("legacy membership conflicts with local execution state")
            if initial is None:
                connection.execute("INSERT INTO kernel_run_controls VALUES(?,0,?,'paused',?,?,?)",
                                   (run_id, manifest["generation"], manifest["max_claims"], manifest["claims_used"], deadline))
                connection.execute("INSERT INTO kernel_run_authorities VALUES(?,?,0,?,?,NULL)",
                                   (run_id, manifest["generation"], worker, worker_expiry))
            connection.executemany("INSERT INTO kernel_managed_executions VALUES(?,?,?,0)",
                                   [(m["execution_id"], run_id, manifest["generation"]) for m in members])
            connection.executemany("INSERT INTO kernel_legacy_pending_commands VALUES(?,?)",
                                   [(m["execution_id"], encode_json(m["command"])) for m in members if m["status"] == "pending"])
            receipt = {"kind": "paused_legacy_import", "adoption": manifest, "imported_at": timestamp,
                       "authorized_principal": verified["principal"], "worker_principal": worker,
                       "worker_expires_at": worker_expiry, "cleanup": "unknown", "activation": "closed",
                       "cursor": members[-1]["execution_id"] if members else (json.loads(last[1])["cursor"] if last else None),
                       "capture_complete": manifest["membership_complete"]}
            if initial is None:
                connection.execute("INSERT INTO kernel_legacy_imports VALUES(?,?,?)",
                                   (manifest["operation_id"], run_id, self._encode_pause_receipt(receipt)))
            connection.execute("INSERT INTO kernel_legacy_import_pages VALUES(?,?,?)",
                               (manifest["operation_id"], manifest["page_seq"], self._encode_pause_receipt(receipt)))
            try:
                final_verified = self._authority_verifier(adoption_credential)
                if (encode_json(final_verified["adoption"]) != encode_json(manifest)
                        or final_verified["principal"] != verified["principal"]
                        or self._number(final_verified["expires_at"], "authority expiry", minimum=0.0) != expiry
                        or not any(tuple(p) == (run_id, "kernel:import_legacy") for p in final_verified["permissions"])):
                    raise ValueError("host isolation evidence changed")
                final_timestamp = self._advance_clock(connection)
                if min(expiry, lease_expiry, worker_expiry) <= final_timestamp:
                    raise ValueError("host isolation or authority expired")
                final_worker, final_worker_expiry = self._verified_authority(
                    worker_credential, run_id, "kernel:worker", final_timestamp,
                    generation=manifest["generation"], control_epoch=0)
                if (final_worker, final_worker_expiry) != (worker, worker_expiry):
                    raise ValueError("worker authority changed")
                final_timestamp = self._advance_clock(connection)
                if min(expiry, lease_expiry, worker_expiry) <= final_timestamp:
                    raise ValueError("host isolation or authority expired")
            except Exception:
                raise StorageIsolationError("host isolation no longer authorizes legacy import") from None
            return receipt

    def stage_revision_content_page(self, credential, *, expected_page: dict) -> dict:
        """Persist one directly authenticated revision-content page under a host lease."""
        with self._transaction() as (connection, timestamp):
            try:
                if self._authority_verifier is None:
                    raise ValueError("missing host verifier")
                verified = self._authority_verifier(credential)
                page = verified["revision_page"]
                fields = {"operation_id", "barrier_operation_id", "source_generation", "decision_id", "run_id", "kernel_store_id", "orchestrator_store_id",
                          "orchestrator_incarnation", "content_kind", "page_seq", "total_bytes", "chunk", "complete",
                          "lease_id", "lease_fence", "lease_expires_at", "lease_held"}
                if type(page) is not dict or set(page) != fields or encode_json(page) != encode_json(expected_page):
                    raise ValueError("unexpected page")
                for key in ("operation_id", "barrier_operation_id", "decision_id", "run_id", "kernel_store_id", "orchestrator_store_id",
                            "orchestrator_incarnation", "lease_id"):
                    if type(page[key]) is not str or not page[key].strip():
                        raise ValueError("invalid page identity")
                for key in ("page_seq", "total_bytes", "lease_fence", "source_generation"):
                    if type(page[key]) is not int or not 0 <= page[key] <= MAX_SQLITE_INTEGER:
                        raise ValueError("invalid page count")
                if (page["operation_id"] != page["barrier_operation_id"]
                        or page["content_kind"] not in ("revision", "source_application_state", "target_application_state")
                        or type(page["chunk"]) is not str or len(page["chunk"].encode("utf-8")) > 512 * 1024
                        or type(page["complete"]) is not bool or page["lease_held"] is not True):
                    raise ValueError("invalid page content")
                if not page["complete"] and not page["chunk"]:
                    raise ValueError("empty nonterminal page")
                lease_expiry = self._number(page["lease_expires_at"], "lease expiry", minimum=0.0)
                expiry = self._number(verified["expires_at"], "authority expiry", minimum=0.0)
                principal = verified["principal"]
                if (min(lease_expiry, expiry) <= timestamp or type(principal) is not str or not principal.strip()
                        or len(principal.encode("utf-8")) > 4096
                        or not any(tuple(p) == (page["run_id"], "kernel:stage_revision") for p in verified["permissions"])):
                    raise ValueError("page authority unavailable")
            except Exception:
                raise StorageIsolationError("host verification did not authorize revision content") from None
            identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if identity is None or identity[0] != page["kernel_store_id"]:
                raise CASConflictError("revision content participant identity differs")
            paused = connection.execute("SELECT 1 FROM kernel_run_controls c JOIN kernel_control_pause_receipts b "
                "ON b.run_id=c.run_id WHERE c.run_id=? AND c.state='paused' AND c.generation=? "
                "AND b.operation_id=? AND b.generation=? AND json_extract(b.receipt_json,'$.kind')='pause_barrier' LIMIT 1",
                (page["run_id"], page["source_generation"], page["barrier_operation_id"], page["source_generation"])).fetchone()
            if paused is None:
                raise CASConflictError("revision content requires a local paused barrier")
            def revalidate():
                try:
                    final = self._authority_verifier(credential)
                    if (encode_json(final["revision_page"]) != encode_json(page) or final["principal"] != principal
                            or self._number(final["expires_at"], "expiry", minimum=0.0) != expiry
                            or not any(tuple(p) == (page["run_id"], "kernel:stage_revision") for p in final["permissions"])):
                        raise ValueError("page authority changed")
                    if min(lease_expiry, expiry) <= self._advance_clock(connection):
                        raise ValueError("page lease expired")
                except Exception:
                    raise StorageIsolationError("host lease no longer authorizes revision content") from None
            key = (page["operation_id"], page["content_kind"], page["page_seq"])
            old = connection.execute("SELECT receipt_json FROM kernel_revision_content_pages "
                                     "WHERE operation_id=? AND content_kind=? AND page_seq=?", key).fetchone()
            if old:
                receipt = json.loads(old[0])
                old_page, current_page = dict(receipt["page"]), dict(page)
                old_page.pop("lease_expires_at")
                current_page.pop("lease_expires_at")
                if encode_json(old_page) != encode_json(current_page):
                    raise CASConflictError("revision page already has different content")
                revalidate()
                return receipt
            previous = connection.execute("SELECT page_seq,receipt_json FROM kernel_revision_content_pages "
                "WHERE operation_id=? AND content_kind=? ORDER BY page_seq DESC LIMIT 1", key[:2]).fetchone()
            count = 0
            if previous is None:
                if page["page_seq"] != 0:
                    raise CASConflictError("revision content must begin at page zero")
            else:
                prior = json.loads(previous[1])
                immutable = fields - {"page_seq", "chunk", "complete", "lease_expires_at"}
                if (previous[0] + 1 != page["page_seq"] or prior["capture_complete"]
                        or any(page[k] != prior["page"][k] for k in immutable)):
                    raise CASConflictError("revision content page does not continue its source")
                count = prior["cumulative_bytes"]
            count += len(page["chunk"].encode("utf-8"))
            if count > page["total_bytes"] or page["complete"] != (count == page["total_bytes"]):
                raise CASConflictError("revision content total is inconsistent")
            receipt = {"kind": "revision_content_page", "page": page, "cumulative_bytes": count,
                       "capture_complete": page["complete"], "captured_at": timestamp}
            connection.execute("INSERT INTO kernel_revision_content_pages VALUES(?,?,?,?)",
                               (*key, self._encode_pause_receipt(receipt)))
            revalidate()
            return receipt

    def install_revision_decision(self, decision_credential, *, worker_credential, expected_decision: dict) -> dict:
        """Install a host-verified decision and successor worker binding while paused.

        The receipt records a local installation; it does not authorize resume,
        prove external writer isolation, or discharge old execution obligations.
        """
        if self._authority_verifier is None or decision_credential is None:
            raise StorageIsolationError("revision installation requires a host verifier")
        try:
            verified = self._authority_verifier(decision_credential)
            decision = verified["decision"]
            if type(decision) is not dict:
                raise ValueError("decision envelope is missing")
            required = {"decision_id", "operation_id", "barrier_operation_id", "run_id",
                        "orchestrator_store_id", "orchestrator_incarnation", "kernel_store_id",
                        "source_revision", "source_generation", "source_control_epoch", "target_generation",
                        "deployment", "migration_version", "application_projection_version",
                        "revision", "source_application_state", "target_application_state", "content_pages"}
            if set(decision) not in (required, required | {"projection_requirements", "source_application_projection_version"}):
                raise ValueError("decision envelope fields differ from the contract")
            requirements = decision.get("projection_requirements", [])
            if (type(requirements) is not list or len(requirements) > 32
                    or ("projection_requirements" in decision and
                        (not requirements or type(decision["source_application_projection_version"]) is not str
                         or not decision["source_application_projection_version"].strip()
                         or len(decision["source_application_projection_version"].encode("utf-8")) > 1024))
                    or any(type(item) is not dict or set(item) != {"participant_id", "scope_id"}
                           or any(type(value) is not str or not value.strip() or len(value.encode("utf-8")) > 1024
                                  for value in item.values()) for item in requirements)
                    or len({(item["participant_id"], item["scope_id"]) for item in requirements}) != len(requirements)
                    or requirements != sorted(requirements, key=lambda item: (item["participant_id"], item["scope_id"]))):
                raise ValueError("invalid projection requirements")
            for key in ("decision_id", "operation_id", "barrier_operation_id", "run_id",
                        "orchestrator_store_id", "orchestrator_incarnation", "kernel_store_id",
                        "migration_version", "application_projection_version"):
                if type(decision[key]) is not str or not decision[key].strip():
                    raise ValueError("decision identifier is invalid")
            for key in ("source_revision", "source_generation", "source_control_epoch", "target_generation"):
                if type(decision[key]) is not int or not 0 <= decision[key] < MAX_SQLITE_INTEGER:
                    raise ValueError("decision version is invalid")
            if (decision["target_generation"] != decision["source_generation"] + 1
                    or decision["operation_id"] != decision["barrier_operation_id"]
                    or type(decision["deployment"]) is not dict):
                raise ValueError("decision target or barrier is invalid")
            encoded_decision = encode_json(decision)
            pages = decision["content_pages"]
            if type(pages) is not dict or set(pages) - {"revision", "source_application_state", "target_application_state"}:
                raise ValueError("invalid staged content mapping")
            for key in ("revision", "source_application_state", "target_application_state"):
                if key in pages:
                    ref = pages[key]
                    if (decision[key] is not None or type(ref) is not dict
                            or set(ref) != {"operation_id", "total_bytes", "lease_id", "lease_fence"}
                            or type(ref["operation_id"]) is not str or not ref["operation_id"].strip()
                            or type(ref["lease_id"]) is not str or not ref["lease_id"].strip()
                            or type(ref["total_bytes"]) is not int or not 0 <= ref["total_bytes"] <= MAX_SQLITE_INTEGER
                            or type(ref["lease_fence"]) is not int or not 0 <= ref["lease_fence"] <= MAX_SQLITE_INTEGER):
                        raise ValueError("invalid staged content reference")
                elif len(encode_json(decision[key]).encode("utf-8")) > 65536:
                    raise ValueError("revision content exceeds its bound")
            principal = verified["principal"]
            expiry = self._number(verified["expires_at"], "authority expiry", minimum=0.0)
            if (type(principal) is not str or not principal.strip() or len(principal.encode("utf-8")) > 4096
                    or not any(tuple(item) == (decision["run_id"], "kernel:install_revision")
                               for item in verified["permissions"])):
                raise ValueError("decision installation is not authorized")
        except Exception:
            raise StorageIsolationError("host verification did not authorize the revision decision") from None
        run_id = decision["run_id"]
        target_epoch = decision["source_control_epoch"] + 1
        with self._transaction() as (connection, timestamp):
            try:
                current_verified = self._authority_verifier(decision_credential)
                if (encode_json(current_verified["decision"]) != encoded_decision
                        or current_verified["principal"] != principal
                        or self._number(current_verified["expires_at"], "authority expiry", minimum=0.0) != expiry
                        or not any(tuple(item) == (run_id, "kernel:install_revision")
                                   for item in current_verified["permissions"])):
                    raise ValueError("authorization changed")
            except Exception:
                raise StorageIsolationError("host verification did not authorize the revision decision") from None
            if type(expected_decision) is not dict or encode_json(expected_decision) != encoded_decision:
                raise CASConflictError("verified revision decision differs from the expected decision")
            identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if identity is None or identity[0] != decision["kernel_store_id"]:
                raise CASConflictError("revision decision participant identity differs")
            for kind, reference in pages.items():
                last = connection.execute("SELECT receipt_json FROM kernel_revision_content_pages "
                    "WHERE operation_id=? AND content_kind=? ORDER BY page_seq DESC LIMIT 1",
                    (reference["operation_id"], kind)).fetchone()
                if last is None:
                    raise CASConflictError("staged revision content is missing")
                content = json.loads(last[0])
                source = content["page"]
                if (not content["capture_complete"] or content["cumulative_bytes"] != reference["total_bytes"]
                        or source["barrier_operation_id"] != decision["barrier_operation_id"]
                        or source["source_generation"] != decision["source_generation"]
                        or (source["decision_id"], source["run_id"], source["kernel_store_id"],
                            source["orchestrator_store_id"], source["orchestrator_incarnation"],
                            source["lease_id"], source["lease_fence"]) !=
                           (decision["decision_id"], run_id, decision["kernel_store_id"],
                            decision["orchestrator_store_id"], decision["orchestrator_incarnation"],
                            reference["lease_id"], reference["lease_fence"])):
                    raise CASConflictError("staged revision content does not match decision")
            if expiry <= timestamp:
                raise StorageIsolationError("revision decision authorization expired")
            worker, worker_expiry = self._verified_authority(
                worker_credential, run_id, "kernel:worker", timestamp,
                generation=decision["target_generation"], control_epoch=target_epoch)
            prior = connection.execute("SELECT receipt_json FROM kernel_revision_installs WHERE decision_id=?",
                                       (decision["decision_id"],)).fetchone()
            if prior is not None:
                receipt = json.loads(prior[0])
                if (encode_json(receipt["decision"]) != encoded_decision
                        or receipt["worker_principal"] != worker or receipt["worker_expires_at"] != worker_expiry):
                    raise CASConflictError("revision decision already has different content")
                return receipt
            barrier = connection.execute("SELECT run_id,generation,receipt_json FROM kernel_control_pause_receipts "
                                         "WHERE operation_id=?", (decision["barrier_operation_id"],)).fetchone()
            if barrier is None or (barrier[0], barrier[1]) != (run_id, decision["source_generation"]):
                raise CASConflictError("revision decision lacks its matching local barrier")
            barrier_receipt = json.loads(barrier[2])
            if (barrier_receipt.get("kind", "pause_barrier") != "pause_barrier"
                    or barrier_receipt.get("store_id") != decision["kernel_store_id"]):
                raise CASConflictError("revision decision participant identity differs")
            capture = connection.execute(
                "SELECT page_json FROM kernel_control_pause_pages WHERE operation_id=? AND round_id=0 "
                "ORDER BY page_seq DESC LIMIT 1", (decision["barrier_operation_id"],)).fetchone()
            if capture is None or not json.loads(capture[0])["capture_complete"]:
                raise CASConflictError("revision installation requires a complete initial local capture")
            control = connection.execute("SELECT generation,control_epoch,state,claims_used,max_claims,deadline_at "
                                         "FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone()
            if (control is None or (control[0], control[1], control[2]) !=
                    (decision["source_generation"], decision["source_control_epoch"], "paused")):
                raise CASConflictError("revision decision source control changed")
            authority = connection.execute("SELECT generation,control_epoch,principal,expires_at,revoked_at "
                                           "FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone()
            if (authority is None or authority[0] != decision["source_generation"]
                    or authority[1] != barrier_receipt["expected_epoch"] or authority[4] is not None
                    or authority[3] <= timestamp):
                raise CASConflictError("revision source authority is stale, expired or revoked")
            if connection.execute("SELECT 1 FROM kernel_revision_installs WHERE barrier_operation_id=?",
                                  (decision["barrier_operation_id"],)).fetchone():
                raise CASConflictError("pause barrier already has a revision decision")
            cursor = connection.execute("UPDATE kernel_run_controls SET generation=?,control_epoch=? "
                "WHERE run_id=? AND generation=? AND control_epoch=? AND state='paused'",
                (decision["target_generation"], target_epoch, run_id, decision["source_generation"],
                 decision["source_control_epoch"]))
            self._cas(cursor, "paused revision installation")
            cursor = connection.execute("UPDATE kernel_run_authorities SET generation=?,control_epoch=?,principal=?,expires_at=? "
                "WHERE run_id=? AND generation=? AND control_epoch=? AND revoked_at IS NULL",
                (decision["target_generation"], target_epoch, worker, worker_expiry, run_id,
                 authority[0], authority[1]))
            self._cas(cursor, "successor authority installation")
            receipt = {"kind": "paused_revision_install", "decision": decision, "installed_at": timestamp,
                       "authorized_principal": principal, "worker_principal": worker,
                       "worker_expires_at": worker_expiry, "target_control_epoch": target_epoch,
                       "previous_authority": {"generation": authority[0], "control_epoch": authority[1],
                                              "principal": authority[2], "expires_at": authority[3]},
                       "claims_used": control[3], "max_claims": control[4], "deadline_at": control[5],
                       "cleanup": "unknown", "activation": "closed"}
            connection.execute("INSERT INTO kernel_revision_installs VALUES(?,?,?,?)",
                               (decision["decision_id"], run_id, decision["barrier_operation_id"],
                                self._encode_pause_receipt(receipt)))
            if requirements:
                connection.execute("INSERT INTO kernel_projection_requirements VALUES(?,?,?,?)",
                                   (run_id, decision["target_generation"], decision["decision_id"], encode_json(requirements)))
            try:
                final = self._authority_verifier(decision_credential)
                if (encode_json(final["decision"]) != encoded_decision or final["principal"] != principal
                        or self._number(final["expires_at"], "authority expiry", minimum=0.0) != expiry
                        or not any(tuple(item) == (run_id, "kernel:install_revision") for item in final["permissions"])):
                    raise ValueError("revision authorization changed")
                now = self._advance_clock(connection)
                if min(expiry, worker_expiry, authority[3]) <= now:
                    raise ValueError("revision authority expired")
                if self._verified_authority(worker_credential, run_id, "kernel:worker", now,
                    generation=decision["target_generation"], control_epoch=target_epoch) != (worker, worker_expiry):
                    raise ValueError("worker authority changed")
                if min(expiry, worker_expiry, authority[3]) <= self._advance_clock(connection):
                    raise ValueError("revision authority expired")
            except Exception:
                raise StorageIsolationError("host authorization no longer permits revision installation") from None
            return receipt

    def observe_revision_authority(self, decision_id: str) -> dict:
        """Observe the current successor binding; this is not a cross-store lock."""
        with self._transaction() as (connection, timestamp):
            row = connection.execute("SELECT run_id,receipt_json FROM kernel_revision_installs WHERE decision_id=?",
                                     (decision_id,)).fetchone()
            if row is None:
                raise CASConflictError("revision installation is missing")
            receipt = json.loads(row[1])
            decision = receipt["decision"]
            state = connection.execute("SELECT c.generation,c.control_epoch,c.state,a.principal,a.expires_at,a.revoked_at "
                "FROM kernel_run_controls c JOIN kernel_run_authorities a ON a.run_id=c.run_id "
                "WHERE c.run_id=? AND a.generation=c.generation AND a.control_epoch=c.control_epoch", (row[0],)).fetchone()
            identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if (state is None or identity is None or identity[0] != decision["kernel_store_id"]
                    or (state[0], state[1], state[2], state[3], state[4]) !=
                    (decision["target_generation"], receipt["target_control_epoch"], "paused",
                     receipt["worker_principal"], receipt["worker_expires_at"])
                    or state[5] is not None or state[4] <= timestamp):
                raise CASConflictError("revision successor authority is unavailable")
            return {"store_id": identity[0], "run_id": row[0], "decision_id": decision_id,
                    "generation": state[0], "control_epoch": state[1], "state": state[2],
                    "worker_principal": state[3], "worker_expires_at": state[4],
                    "revoked": False, "observed_at": timestamp}

    def activate_revision(self, credential, *, expected_decision: dict) -> dict:
        """Record a verified activation decision while keeping the Run paused."""
        with self._transaction() as (connection, timestamp):
            try:
                verified = self._authority_verifier(credential)
                decision = verified["activation"]
                fields = {"operation_id", "run_id", "decision_id", "barrier_operation_id", "completion_operation_id",
                          "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation", "generation",
                          "expected_control_epoch", "orchestrator_install_receipt", "kernel_install_receipt",
                          "lease_id", "lease_fence", "lease_expires_at", "lease_held"}
                if type(decision) is not dict or set(decision) != fields or encode_json(decision) != encode_json(expected_decision):
                    raise ValueError("unexpected activation decision")
                for key in ("operation_id", "run_id", "decision_id", "barrier_operation_id", "completion_operation_id",
                            "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation", "lease_id"):
                    if type(decision[key]) is not str or not decision[key].strip():
                        raise ValueError("invalid activation identity")
                for key in ("generation", "expected_control_epoch", "lease_fence"):
                    if type(decision[key]) is not int or not 0 <= decision[key] < MAX_SQLITE_INTEGER:
                        raise ValueError("invalid activation version")
                if (decision["lease_held"] is not True or type(decision["orchestrator_install_receipt"]) is not dict
                        or type(decision["kernel_install_receipt"]) is not dict):
                    raise ValueError("invalid activation proof")
                expiry = self._number(verified["expires_at"], "authority expiry", minimum=0.0)
                lease_expiry = self._number(decision["lease_expires_at"], "lease expiry", minimum=0.0)
                principal = verified["principal"]
                if (type(principal) is not str or not principal.strip() or len(principal.encode("utf-8")) > 4096
                        or min(expiry, lease_expiry) <= timestamp
                        or not any(tuple(p) == (decision["run_id"], "kernel:activate_revision") for p in verified["permissions"])):
                    raise ValueError("activation authority unavailable")
            except Exception:
                raise StorageIsolationError("host verification did not authorize revision activation") from None
            run_id = decision["run_id"]
            takeover = self._verify_effective_control_decision(connection, "activation", decision)
            identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            installed = connection.execute("SELECT receipt_json FROM kernel_revision_installs WHERE decision_id=? AND run_id=?",
                                           (decision["decision_id"], run_id)).fetchone()
            control = connection.execute("SELECT generation,control_epoch,state FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone()
            authority = connection.execute("SELECT generation,control_epoch,principal,expires_at,revoked_at FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone()
            completion = connection.execute("SELECT receipt_json FROM kernel_control_pause_receipts WHERE operation_id=? AND run_id=?",
                                            (decision["completion_operation_id"], run_id)).fetchone()
            if (identity is None or identity[0] != decision["kernel_store_id"] or installed is None
                    or encode_json(json.loads(installed[0])) != encode_json(decision["kernel_install_receipt"])
                    or control is None or tuple(control) != (decision["generation"], decision["expected_control_epoch"], "paused")
                    or authority is None or authority[0] != decision["generation"] or authority[1] != decision["expected_control_epoch"]
                    or authority[4] is not None or authority[3] <= timestamp or completion is None):
                raise CASConflictError("paused revision or authority changed before activation")
            installation = json.loads(installed[0])
            source = installation["decision"]
            paused = json.loads(completion[0])
            if ((authority[2], authority[3]) != (installation["worker_principal"], installation["worker_expires_at"])
                    or paused.get("kind") != "local_paused" or paused.get("barrier_operation_id") != decision["barrier_operation_id"]
                    or (source["barrier_operation_id"], source["orchestrator_store_id"], source["orchestrator_incarnation"], source["target_generation"])
                    != (decision["barrier_operation_id"], decision["orchestrator_store_id"], decision["orchestrator_incarnation"], decision["generation"])
                    or connection.execute("SELECT 1 FROM kernel_control_pause_receipts WHERE run_id=? AND json_extract(receipt_json,'$.kind')='cancellation_fence' LIMIT 1", (run_id,)).fetchone()):
                raise CASConflictError("activation installation or cancellation differs")
            previous = connection.execute("SELECT receipt_json FROM kernel_activation_receipts WHERE operation_id=?", (decision["operation_id"],)).fetchone()
            if previous:
                receipt = json.loads(previous[0])
                original, renewed = dict(receipt["decision"]), dict(decision)
                original.pop("lease_expires_at")
                renewed.pop("lease_expires_at")
                if takeover:
                    for key in ("lease_id", "lease_fence"):
                        original.pop(key)
                        renewed.pop(key)
                if encode_json(original) != encode_json(renewed):
                    raise CASConflictError("activation operation already has different content")
            else:
                receipt = {"kind": "revision_activation", "decision": decision, "activated_at": timestamp, "state": "paused"}
                connection.execute("INSERT INTO kernel_activation_receipts VALUES(?,?,?)",
                                   (decision["operation_id"], run_id, self._encode_pause_receipt(receipt)))
            try:
                again = self._authority_verifier(credential)
                if (encode_json(again["activation"]) != encode_json(decision) or again["principal"] != principal
                        or self._number(again["expires_at"], "authority expiry", minimum=0.0) != expiry
                        or not any(tuple(p) == (run_id, "kernel:activate_revision") for p in again["permissions"])):
                    raise ValueError("activation authorization changed")
                if min(expiry, lease_expiry, authority[3]) <= self._advance_clock(connection):
                    raise ValueError("activation authority expired")
            except Exception:
                raise StorageIsolationError("host lease no longer authorizes revision activation") from None
            return receipt

    def _budget_host_proof(self, credential, claim, expected, action, timestamp):
        try:
            result = self._authority_verifier(credential)
            principal = result['principal']
            expiry = self._number(result['expires_at'], 'authority expiry', minimum=0.0)
            if (type(principal) is not str or not principal.strip() or len(principal.encode('utf-8')) > 4096
                    or expiry <= timestamp or encode_json(result[claim]) != encode_json(expected)
                    or not any(tuple(item) == (expected['run_id'], action) for item in result['permissions'])):
                raise ValueError('invalid budget authority')
            return principal, expiry
        except Exception:
            raise StorageIsolationError('host did not authorize budget declaration') from None

    def install_budget_policy(self, credential, *, expected_policy: dict) -> dict:
        """Persist an immutable host-attested dependency policy for a paused revision."""
        try:
            p = expected_policy
            if type(p) is not dict or set(p) != {'policy_id', 'decision_id', 'run_id', 'generation',
                    'kernel_store_id', 'orchestrator_store_id', 'orchestrator_incarnation', 'scopes'}:
                raise ValueError('invalid policy')
            if any(type(p[k]) is not str or not p[k].strip() or len(p[k].encode('utf-8')) > 4096
                   for k in ('policy_id', 'decision_id', 'run_id', 'kernel_store_id', 'orchestrator_store_id', 'orchestrator_incarnation')):
                raise ValueError('invalid identity')
            self._managed_generation(p['generation'])
            if type(p['scopes']) is not list or len(p['scopes']) > 32:
                raise ValueError('invalid scopes')
            for scope in p['scopes']:
                if (type(scope) is not dict or set(scope) != {'owner', 'unit', 'source_id'}
                        or any(type(v) is not str or not v.strip() or len(v.encode('utf-8')) > 4096 for v in scope.values())):
                    raise ValueError('invalid scope')
            if len({encode_json(s) for s in p['scopes']}) != len(p['scopes']):
                raise ValueError('duplicate scopes')
            encoded = encode_json(p)
            if len(encoded.encode('utf-8')) > 65536:
                raise ValueError('policy too large')
            p = json.loads(encoded)
        except Exception:
            raise ValueError('invalid application budget policy') from None
        with self._transaction() as (connection, timestamp):
            principal, expiry = self._budget_host_proof(credential, 'budget_policy', p, 'kernel:manage_budget', timestamp)
            control = connection.execute('SELECT generation,state FROM kernel_run_controls WHERE run_id=?', (p['run_id'],)).fetchone()
            store = connection.execute('SELECT store_id FROM kernel_store_identity WHERE singleton=1').fetchone()
            install = connection.execute('SELECT receipt_json FROM kernel_revision_installs WHERE decision_id=? AND run_id=?',
                                         (p['decision_id'], p['run_id'])).fetchone()
            if control is None or tuple(control) != (p['generation'], 'paused') or store is None or store[0] != p['kernel_store_id'] or install is None:
                raise CASConflictError('budget policy requires its paused installed revision')
            decision = json.loads(install[0])['decision']
            if (decision['target_generation'], decision['kernel_store_id'], decision['orchestrator_store_id'], decision['orchestrator_incarnation']) != (
                    p['generation'], p['kernel_store_id'], p['orchestrator_store_id'], p['orchestrator_incarnation']):
                raise CASConflictError('budget policy participant binding differs')
            old = connection.execute('SELECT policy_json FROM kernel_budget_policies WHERE run_id=? AND generation=?',
                                     (p['run_id'], p['generation'])).fetchone()
            if old is None:
                connection.execute('INSERT INTO kernel_budget_policies VALUES(?,?,?)', (p['run_id'], p['generation'], encoded))
            elif old[0] != encoded:
                raise CASConflictError('budget policy is immutable')
            now = self._advance_clock(connection)
            if self._budget_host_proof(credential, 'budget_policy', p, 'kernel:manage_budget', now) != (principal, expiry) or expiry <= self._advance_clock(connection):
                raise StorageIsolationError('budget policy authority expired')
            return json.loads(encoded)

    def inspect_budget_policy(self, run_id: str, generation: int) -> dict | None:
        with self._lock:
            row = self._connection.execute('SELECT policy_json FROM kernel_budget_policies WHERE run_id=? AND generation=?', (run_id, generation)).fetchone()
            return None if row is None else json.loads(row[0])

    def declare_budget_dependencies(self, credential, *, expected_declaration: dict) -> dict:
        """Persist the host-attested exact command and its dependency subset."""
        d = expected_declaration
        try:
            if type(d) is not dict or set(d) != {'run_id', 'generation', 'policy_id', 'execution_id', 'command', 'scopes',
                    'decision_id', 'kernel_store_id', 'orchestrator_store_id', 'orchestrator_incarnation'}:
                raise ValueError('invalid declaration')
            encoded = encode_json(d)
            if len(encoded.encode('utf-8')) > 65536 or type(d['scopes']) is not list or len(d['scopes']) > 32:
                raise ValueError('declaration too large')
            if type(d['execution_id']) is not str or not d['execution_id'].strip() or type(d['command']) is not dict or d['command'].get('execution_id') != d['execution_id']:
                raise ValueError('invalid command')
            self._managed_generation(d['generation'])
            d = json.loads(encoded)
        except Exception:
            raise ValueError('invalid budget dependency declaration') from None
        with self._transaction() as (connection, timestamp):
            principal, expiry = self._budget_host_proof(credential, 'budget_declaration', d, 'kernel:declare_budget', timestamp)
            policy = connection.execute('SELECT policy_json FROM kernel_budget_policies WHERE run_id=? AND generation=?',
                                        (d['run_id'], d['generation'])).fetchone()
            control = connection.execute('SELECT generation FROM kernel_run_controls WHERE run_id=?', (d['run_id'],)).fetchone()
            if policy is None or control is None or control[0] != d['generation']:
                raise CASConflictError('budget policy or generation unavailable')
            p = json.loads(policy[0])
            identity = connection.execute('SELECT store_id FROM kernel_store_identity WHERE singleton=1').fetchone()
            if (identity is None or identity[0] != p['kernel_store_id']
                    or any(p[key] != d[key] for key in ('policy_id', 'decision_id', 'kernel_store_id', 'orchestrator_store_id', 'orchestrator_incarnation'))
                    or len({encode_json(s) for s in d['scopes']}) != len(d['scopes']) or any(s not in p['scopes'] for s in d['scopes'])):
                raise CASConflictError('budget dependencies do not match the policy')
            existing = connection.execute('SELECT command_json FROM kernel_executions WHERE execution_id=?', (d['execution_id'],)).fetchone()
            if existing is not None and existing[0] != encode_json(d['command']):
                raise CASConflictError('budget declaration command differs')
            prior = connection.execute('SELECT declaration_json FROM kernel_budget_dependencies WHERE execution_id=?', (d['execution_id'],)).fetchone()
            if prior is None:
                connection.execute('INSERT INTO kernel_budget_dependencies VALUES(?,?,?,?)', (d['execution_id'], d['run_id'], d['generation'], encoded))
            elif prior[0] != encoded:
                raise CASConflictError('budget dependency declaration is immutable')
            now = self._advance_clock(connection)
            if self._budget_host_proof(credential, 'budget_declaration', d, 'kernel:declare_budget', now) != (principal, expiry) or expiry <= self._advance_clock(connection):
                raise StorageIsolationError('budget declaration authority expired')
            return json.loads(encoded)

    def resume_revision(self, credential, *, worker_credential, expected_decision: dict) -> dict:
        """Resume a locally installed revision under an exclusive host control lease.

        The host must authenticate both participant installations and hold the
        exclusive control lease until Orchestrator admission has reopened. A
        cancellation must first install a Kernel cancellation fence.
        """
        with self._transaction() as (connection, timestamp):
            try:
                verified = self._authority_verifier(credential)
                decision = verified["resume"]
                fields = {"operation_id", "run_id", "decision_id", "barrier_operation_id", "completion_operation_id",
                          "activation_operation_id", "activation_receipt",
                          "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation", "generation",
                          "expected_control_epoch", "target_control_epoch", "orchestrator_install_receipt",
                          "kernel_install_receipt", "lease_id", "lease_fence", "lease_expires_at", "lease_held"}
                if type(decision) is not dict or set(decision) != fields or encode_json(decision) != encode_json(expected_decision):
                    raise ValueError("unexpected resume decision")
                for key in ("operation_id", "run_id", "decision_id", "barrier_operation_id", "completion_operation_id", "activation_operation_id",
                            "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation", "lease_id"):
                    if type(decision[key]) is not str or not decision[key].strip():
                        raise ValueError("missing resume identity")
                for key in ("generation", "expected_control_epoch", "target_control_epoch", "lease_fence"):
                    if type(decision[key]) is not int or not 0 <= decision[key] <= MAX_SQLITE_INTEGER:
                        raise ValueError("invalid resume version")
                if (decision["target_control_epoch"] != decision["expected_control_epoch"] + 1
                        or decision["lease_held"] is not True
                        or type(decision["orchestrator_install_receipt"]) is not dict
                        or type(decision["kernel_install_receipt"]) is not dict or type(decision["activation_receipt"]) is not dict):
                    raise ValueError("invalid resume target")
                expiry = self._number(verified["expires_at"], "authority expiry", minimum=0.0)
                lease_expiry = self._number(decision["lease_expires_at"], "lease expiry", minimum=0.0)
                principal = verified["principal"]
                if (type(principal) is not str or not principal.strip() or len(principal.encode("utf-8")) > 4096
                        or min(expiry, lease_expiry) <= timestamp
                        or not any(tuple(p) == (decision["run_id"], "kernel:resume") for p in verified["permissions"])):
                    raise ValueError("resume authority unavailable")
            except Exception:
                raise StorageIsolationError("host verification did not authorize revision resume") from None
            run_id = decision["run_id"]
            takeover = self._verify_effective_control_decision(connection, "resume", decision)
            store = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if store is None or store[0] != decision["kernel_store_id"]:
                raise CASConflictError("resume participant identity differs")
            worker, worker_expiry = self._verified_authority(worker_credential, run_id, "kernel:worker", timestamp,
                generation=decision["generation"], control_epoch=decision["target_control_epoch"])
            previous = connection.execute("SELECT receipt_json FROM kernel_resume_receipts WHERE operation_id=?",
                                          (decision["operation_id"],)).fetchone()
            if previous:
                receipt = json.loads(previous[0])
                original_decision, renewed_decision = dict(receipt["decision"]), dict(decision)
                original_decision.pop("lease_expires_at")
                renewed_decision.pop("lease_expires_at")
                if takeover:
                    for key in ("lease_id", "lease_fence"):
                        original_decision.pop(key)
                        renewed_decision.pop(key)
                if (encode_json(original_decision) != encode_json(renewed_decision)
                        or (receipt["worker_principal"], receipt["worker_expires_at"]) != (worker, worker_expiry)):
                    raise CASConflictError("resume operation already has different content")
                current = connection.execute("SELECT c.generation,c.control_epoch,c.state,a.principal,a.expires_at,a.revoked_at "
                    "FROM kernel_run_controls c JOIN kernel_run_authorities a ON a.run_id=c.run_id "
                    "WHERE c.run_id=? AND a.generation=c.generation AND a.control_epoch=c.control_epoch", (run_id,)).fetchone()
                if (current is None or tuple(current) != (decision["generation"], decision["target_control_epoch"],
                        "active", worker, worker_expiry, None)
                        or self._has_unresolved_control_barrier(connection, run_id)):
                    raise CASConflictError("resumed Run has since been fenced")
                try:
                    again = self._authority_verifier(credential)
                    if (encode_json(again["resume"]) != encode_json(decision) or again["principal"] != principal
                            or self._number(again["expires_at"], "authority expiry", minimum=0.0) != expiry
                            or not any(tuple(p) == (run_id, "kernel:resume") for p in again["permissions"])):
                        raise ValueError("resume authorization changed")
                    if min(expiry, lease_expiry, worker_expiry) <= self._advance_clock(connection):
                        raise ValueError("resume authority expired")
                    now = self._advance_clock(connection)
                    if self._verified_authority(worker_credential, run_id, "kernel:worker", now,
                        generation=decision["generation"], control_epoch=decision["target_control_epoch"]) != (worker, worker_expiry):
                        raise ValueError("worker authority changed")
                    if min(expiry, lease_expiry, worker_expiry) <= self._advance_clock(connection):
                        raise ValueError("resume authority expired")
                except Exception:
                    raise StorageIsolationError("host lease no longer authorizes revision resume") from None
                return receipt
            policy = connection.execute("SELECT policy_json FROM kernel_budget_policies WHERE run_id=? AND generation=?", (run_id, decision["generation"])).fetchone()
            if policy is None or json.loads(policy[0])["decision_id"] != decision["decision_id"]:
                raise CASConflictError("revision has no matching application budget policy")
            installed = connection.execute("SELECT receipt_json FROM kernel_revision_installs WHERE decision_id=? AND run_id=?",
                                           (decision["decision_id"], run_id)).fetchone()
            if installed is None or encode_json(json.loads(installed[0])) != encode_json(decision["kernel_install_receipt"]):
                raise CASConflictError("matching Kernel revision installation is missing")
            activation = connection.execute("SELECT receipt_json FROM kernel_activation_receipts WHERE operation_id=? AND run_id=?",
                                            (decision["activation_operation_id"], run_id)).fetchone()
            if activation is None or encode_json(json.loads(activation[0])) != encode_json(decision["activation_receipt"]):
                raise CASConflictError("matching paused activation is missing")
            activated = json.loads(activation[0])["decision"]
            for key in ("run_id", "decision_id", "barrier_operation_id", "completion_operation_id", "kernel_store_id",
                        "orchestrator_store_id", "orchestrator_incarnation", "generation", "expected_control_epoch",
                        "orchestrator_install_receipt", "kernel_install_receipt"):
                if encode_json(activated[key]) != encode_json(decision[key]):
                    raise CASConflictError("resume decision differs from paused activation")
            activation_binding = self._effective_takeover_binding(connection, "activation", decision["activation_operation_id"],
                                                                  activated["lease_id"], activated["lease_fence"])
            if not takeover and activation_binding != (decision["lease_id"], decision["lease_fence"]):
                raise CASConflictError("resume lease differs from paused activation")
            if takeover:
                row = connection.execute("SELECT claim_json FROM kernel_control_takeovers WHERE operation_id=? ORDER BY new_fence DESC LIMIT 1",
                                         (decision["operation_id"],)).fetchone()
                claim = json.loads(row[0])
                original_binding = (claim["original_decision"]["lease_id"], claim["original_decision"]["lease_fence"])
                if activation_binding != original_binding:
                    raise CASConflictError("resume takeover does not bind paused activation lease")
            source = json.loads(installed[0])["decision"]
            if (source["barrier_operation_id"], source["orchestrator_store_id"], source["orchestrator_incarnation"],
                    source["target_generation"]) != (decision["barrier_operation_id"], decision["orchestrator_store_id"],
                    decision["orchestrator_incarnation"], decision["generation"]):
                raise CASConflictError("resume decision differs from installed revision")
            completion = connection.execute("SELECT receipt_json FROM kernel_control_pause_receipts WHERE operation_id=? AND run_id=?",
                                            (decision["completion_operation_id"], run_id)).fetchone()
            if completion is None:
                raise CASConflictError("local pause completion is missing")
            completion = json.loads(completion[0])
            if completion.get("kind") != "local_paused" or completion.get("barrier_operation_id") != decision["barrier_operation_id"]:
                raise CASConflictError("local pause completion differs")
            if connection.execute("SELECT 1 FROM kernel_control_pause_receipts WHERE run_id=? "
                                  "AND json_extract(receipt_json,'$.kind')='cancellation_fence' LIMIT 1", (run_id,)).fetchone():
                raise CASConflictError("Run cancellation has been fenced")
            control = connection.execute("SELECT generation,control_epoch,state FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone()
            authority = connection.execute("SELECT generation,control_epoch,principal,expires_at,revoked_at FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone()
            installation = json.loads(installed[0])
            if (control is None or tuple(control) != (decision["generation"], decision["expected_control_epoch"], "paused")
                    or authority is None or tuple(authority) != (decision["generation"], decision["expected_control_epoch"],
                        installation["worker_principal"], installation["worker_expires_at"], None)
                    or authority[3] <= timestamp):
                raise CASConflictError("resume authority or paused control changed")
            self._cas(connection.execute("UPDATE kernel_run_controls SET state='active',control_epoch=? WHERE run_id=? AND control_epoch=? AND state='paused'",
                (decision["target_control_epoch"], run_id, decision["expected_control_epoch"])), "revision resume control")
            self._cas(connection.execute("UPDATE kernel_run_authorities SET control_epoch=?,principal=?,expires_at=? WHERE run_id=? AND control_epoch=? AND revoked_at IS NULL",
                (decision["target_control_epoch"], worker, worker_expiry, run_id, decision["expected_control_epoch"])), "revision resume authority")
            receipt = {"kind": "revision_resume", "decision": decision, "worker_principal": worker,
                       "worker_expires_at": worker_expiry, "resumed_at": timestamp, "cleanup": "unknown"}
            connection.execute("INSERT INTO kernel_resume_receipts VALUES(?,?,?,?,?)", (decision["operation_id"], run_id,
                decision["barrier_operation_id"], decision["completion_operation_id"], self._encode_pause_receipt(receipt)))
            try:
                again = self._authority_verifier(credential)
                if (encode_json(again["resume"]) != encode_json(decision) or again["principal"] != principal
                        or self._number(again["expires_at"], "authority expiry", minimum=0.0) != expiry
                        or not any(tuple(p) == (run_id, "kernel:resume") for p in again["permissions"])):
                    raise ValueError("resume authorization changed")
                now = self._advance_clock(connection)
                if min(expiry, lease_expiry, worker_expiry) <= now:
                    raise ValueError("resume authority expired")
                if self._verified_authority(worker_credential, run_id, "kernel:worker", now,
                    generation=decision["generation"], control_epoch=decision["target_control_epoch"]) != (worker, worker_expiry):
                    raise ValueError("worker authority changed")
                if min(expiry, lease_expiry, worker_expiry) <= self._advance_clock(connection):
                    raise ValueError("resume authority expired")
            except Exception:
                raise StorageIsolationError("host lease no longer authorizes revision resume") from None
            return receipt

    def _next_budget_eligible_claim(self, connection, timestamp, revisions, execution_id=None,
                                    exclude_execution_ids=(), budget_scan_cursor=None):
        # Callers own the continuation, so bounded scans cannot silently starve
        # under concurrent or alternating claim predicates.
        if (0 if revisions is None else len(revisions)) + len(exclude_execution_ids) > 1024:
            raise ValueError('budget scan predicate exceeds its byte bound')
        values = (*(() if revisions is None else revisions), *exclude_execution_ids)
        if (any(type(value) is not str or len(value) > 4096 for value in values)
                or sum(len(value.encode('utf-8')) for value in values) > 65536):
            raise ValueError('budget scan predicate exceeds its byte bound')
        predicate = {'revisions': None if revisions is None else list(revisions)}
        if len(encode_json(predicate).encode('utf-8')) > 65536:
            raise ValueError('budget scan predicate exceeds its byte bound')
        cursor = None
        if budget_scan_cursor is not None:
            if (execution_id is not None or type(budget_scan_cursor) is not dict
                    or set(budget_scan_cursor) != {'predicate', 'after'}
                    or budget_scan_cursor['predicate'] != predicate):
                raise ValueError('budget scan cursor does not match the claim predicate')
            after = budget_scan_cursor['after']
            if (type(after) is not list or len(after) != 2
                    or type(after[0]) not in (int, float) or not math.isfinite(after[0])
                    or type(after[1]) is not str or not after[1]
                    or len(after[1].encode('utf-8')) > 4096):
                raise ValueError('invalid budget scan cursor')
            cursor = tuple(after)
        for _ in range(64):
            row = _next_claim_row(connection, timestamp, revisions, execution_id, tuple(exclude_execution_ids), cursor)
            if row is None:
                return None
            membership = connection.execute('SELECT run_id,generation FROM kernel_managed_executions WHERE execution_id=?', (row['execution_id'],)).fetchone()
            if membership is None:
                return row
            prior_expiry = self._precommit_budget_expiry
            prior_checks = len(self._precommit_authority_checks)
            try:
                self._check_application_budget(connection, membership[0], membership[1], row['execution_id'], timestamp, command_json=row['command_json'])
                self._check_run_authority(connection, membership[0], 'claim', timestamp, execution_id=row['execution_id'])
                if execution_id is None:
                    if len(row['execution_id'].encode('utf-8')) > 4096:
                        raise ValueError('budget scan execution identity exceeds its byte bound')
                    self._claim_continuation = {'predicate': predicate, 'after': [row['created_at'], row['execution_id']]}
                return row
            except (CASConflictError, StorageIsolationError):
                self._precommit_budget_expiry = prior_expiry
                del self._precommit_authority_checks[prior_checks:]
                if execution_id is not None:
                    raise
                cursor = (row['created_at'], row['execution_id'])
        if len(cursor[1].encode('utf-8')) > 4096:
            raise ValueError('budget scan execution identity exceeds its byte bound')
        raise BudgetScanContinuation({'predicate': predicate, 'after': list(cursor)})

    def _check_application_budget(self, connection, run_id, generation, execution_id, timestamp, *, command_json=None):
        self._check_projection_dependencies(connection, run_id, generation, execution_id, command_json=command_json)
        policy_row = connection.execute('SELECT policy_json FROM kernel_budget_policies WHERE run_id=? AND generation=?', (run_id, generation)).fetchone()
        if policy_row is None:
            revised = connection.execute("SELECT 1 FROM kernel_revision_installs WHERE run_id=? AND json_extract(receipt_json,'$.decision.target_generation')=? LIMIT 1", (run_id, generation)).fetchone()
            if revised is not None:
                raise CASConflictError('revision has no declared application budget policy')
            return
        policy = json.loads(policy_row[0])
        identity = connection.execute('SELECT store_id FROM kernel_store_identity WHERE singleton=1').fetchone()
        if identity is None or identity[0] != policy['kernel_store_id']:
            raise CASConflictError('budget policy participant identity differs')
        if not policy['scopes']:
            return
        declared = connection.execute('SELECT run_id,generation,declaration_json FROM kernel_budget_dependencies WHERE execution_id=?', (execution_id,)).fetchone()
        if declared is None or tuple(declared[:2]) != (run_id, generation):
            raise CASConflictError('execution has no budget dependency declaration')
        declaration = json.loads(declared[2])
        actual = command_json
        if actual is None:
            row = connection.execute('SELECT command_json FROM kernel_executions WHERE execution_id=?', (execution_id,)).fetchone()
            actual = None if row is None else row[0]
        if actual is None or actual != encode_json(declaration['command']):
            raise CASConflictError('budget dependency command differs')
        if declaration['scopes']:
            expected = {'run_id': run_id, 'generation': generation, 'execution_id': execution_id,
                        'policy_id': policy['policy_id'], 'scopes': declaration['scopes'],
                        'decision_id': policy['decision_id'], 'kernel_store_id': policy['kernel_store_id'],
                        'orchestrator_store_id': policy['orchestrator_store_id'],
                        'orchestrator_incarnation': policy['orchestrator_incarnation']}
            try:
                result = self._authority_verifier(self._worker_credential)
                if 'budget_admissions' in result:
                    proofs = result['budget_admissions']
                    if ('budget_admission' in result or type(proofs) is not list or len(proofs) > 16
                            or len(encode_json(proofs).encode('utf-8')) > 65536
                            or any(type(item) is not dict or type(item.get('execution_id')) is not str
                                   or not item['execution_id'].strip() for item in proofs)
                            or len({item['execution_id'] for item in proofs}) != len(proofs)):
                        raise ValueError('invalid budget admissions')
                    selected = [item for item in proofs if item['execution_id'] == execution_id]
                    if len(selected) != 1:
                        raise ValueError('execution budget admission is missing')
                    proof = selected[0]
                else:
                    proof = result['budget_admission']
                authority = connection.execute('SELECT principal FROM kernel_run_authorities WHERE run_id=?', (run_id,)).fetchone()
                fresh = self._advance_clock(connection)
                if (type(proof) is not dict or proof.get('allowed') is not True
                        or any(encode_json(proof.get(k)) != encode_json(v) for k, v in expected.items())
                        or authority is None or result.get('principal') != authority[0]
                        or self._number(result.get('expires_at'), 'authority expiry', minimum=0.0) <= fresh
                        or self._number(proof.get('expires_at'), 'budget expiry', minimum=0.0) <= fresh
                        or not any(tuple(item) == (run_id, 'kernel:budget') for item in result['permissions'])):
                    raise ValueError('budget unavailable')
                expiry = min(self._number(proof['expires_at'], 'budget expiry', minimum=0.0),
                             self._number(result['expires_at'], 'authority expiry', minimum=0.0))
                previous = self._precommit_budget_expiry
                self._precommit_budget_expiry = expiry if previous is None else min(previous, expiry)
            except Exception:
                raise StorageIsolationError('host did not authorize application budget admission') from None

    def _check_run_authority(self, connection, run_id: str, action: str, timestamp: float,
                             *, execution_id: str | None = None, _precommit: bool = False) -> None:
        row = connection.execute(
            "SELECT a.generation,a.control_epoch,a.principal,a.expires_at,a.revoked_at,c.generation,c.control_epoch "
            "FROM kernel_run_authorities a JOIN kernel_run_controls c ON c.run_id=a.run_id WHERE a.run_id=?",
            (run_id,)).fetchone()
        if row is None:
            return
        if (row[4] is not None or row[3] <= timestamp or row[0] != row[5]):
            raise CASConflictError("protected Run authority is revoked, expired or stale")
        if execution_id is not None and (action != "submit" or _precommit):
            self._check_application_budget(connection, run_id, row[0], execution_id, timestamp)
        def check_clock():
            fresh = self._advance_clock(connection)
            if row[3] <= fresh:
                raise CASConflictError("protected Run authority expired")
            return fresh
        if row[1] != row[6]:
            if (execution_id is None or row[6] != row[1] + 1 or
                    not self._drain_barrier_allows(connection, run_id, execution_id)):
                raise CASConflictError("protected Run authority is revoked, expired or stale")
            barrier = connection.execute("SELECT operation_id,receipt_json FROM kernel_control_pause_receipts "
                "WHERE run_id=? AND json_extract(receipt_json,'$.kind')='pause_barrier' "
                "AND json_extract(receipt_json,'$.control_epoch')=? LIMIT 2", (run_id, row[6])).fetchall()
            identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if len(barrier) != 1 or identity is None:
                raise CASConflictError("protected drain barrier is unavailable")
            barrier_receipt = json.loads(barrier[0][1])
            admission = {"operation_id": barrier[0][0], "run_id": run_id, "execution_id": execution_id,
                         "generation": row[0], "control_epoch": row[6], "kernel_store_id": identity[0],
                         "orchestrator_store_id": barrier_receipt.get("drain_orchestrator_store_id"),
                         "orchestrator_incarnation": barrier_receipt.get("drain_orchestrator_incarnation")}
            principal, _ = self._verified_authority(self._worker_credential, run_id, "kernel:" + action, timestamp,
                generation=row[0], control_epoch=row[1], drain_admission=admission,
                clock_check=check_clock if _precommit else None)
            if principal != row[2]:
                raise StorageIsolationError("protected Run worker principal does not match")
            if not _precommit:
                self._precommit_authority_checks.append(lambda: self._claim_checked_authority(
                    connection, run_id, action, self._advance_clock(connection), execution_id=execution_id, _precommit=True))
            return
        resumed = connection.execute("SELECT receipt_json FROM kernel_resume_receipts WHERE run_id=? "
            "AND json_extract(receipt_json,'$.decision.generation')=? "
            "AND json_extract(receipt_json,'$.decision.target_control_epoch')=?", (run_id, row[0], row[1])).fetchone()
        lease = None
        initial = None
        if resumed is not None:
            decision = json.loads(resumed[0])["decision"]
            lease = self._effective_control_lease(connection, decision)
        else:
            binding = connection.execute("SELECT binding_json FROM kernel_initial_admission_bindings WHERE run_id=?",
                                         (run_id,)).fetchone()
            identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if binding is None or identity is None:
                raise StorageIsolationError("initial global admission binding is unavailable")
            initial = json.loads(binding[0])
            if (initial["kernel_store_id"], initial["run_id"], initial["generation"], initial["control_epoch"]) != (
                    identity[0], run_id, row[0], row[1]):
                raise StorageIsolationError("initial global admission binding differs")
        principal, _ = self._verified_authority(self._worker_credential, run_id, "kernel:" + action, timestamp,
                                                generation=row[0], control_epoch=row[1], control_lease=lease,
                                                initial_admission=initial,
                                                clock_check=check_clock if _precommit else None)
        if principal != row[2]:
            raise StorageIsolationError("protected Run worker principal does not match")
        if not _precommit:
            self._precommit_authority_checks.append(lambda: self._claim_checked_authority(
                connection, run_id, action, self._advance_clock(connection), execution_id=execution_id, _precommit=True))

    def _claim_checked_authority(self, connection, run_id, action, timestamp, **kwargs):
        try:
            self._check_run_authority(connection, run_id, action, timestamp, **kwargs)
        except (CASConflictError, StorageIsolationError) as error:
            error._claim_authority_failure = True
            raise

    def _check_control_authority(self, connection, run_id: str, action: str, timestamp: float) -> None:
        if connection.execute("SELECT 1 FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone():
            self._verified_authority(self._worker_credential, run_id, "kernel:" + action, timestamp)

    @staticmethod
    def _has_unresolved_control_barrier(connection, run_id: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM kernel_control_pause_receipts b WHERE b.run_id=? "
            "AND NOT EXISTS (SELECT 1 FROM kernel_resume_receipts r WHERE r.run_id=b.run_id "
            "AND b.operation_id IN (r.barrier_operation_id,r.completion_operation_id)) LIMIT 1",
            (run_id,)).fetchone() is not None

    @staticmethod
    def _drain_barrier_allows(connection, run_id: str, execution_id: str) -> bool:
        """Allow only registered drain work across its one matching pause barrier."""
        return connection.execute(
            "SELECT 1 FROM kernel_managed_executions m JOIN kernel_run_controls c ON c.run_id=m.run_id "
            "WHERE m.run_id=? AND m.execution_id=? AND m.generation=c.generation "
            "AND m.drain_allowed=1 AND c.state='pausing' AND NOT EXISTS ("
            "SELECT 1 FROM kernel_control_pause_receipts b WHERE b.run_id=m.run_id "
            "AND NOT EXISTS (SELECT 1 FROM kernel_resume_receipts r WHERE r.run_id=b.run_id "
            "AND b.operation_id IN (r.barrier_operation_id,r.completion_operation_id)) "
            "AND COALESCE((json_extract(b.receipt_json,'$.kind')='pause_barrier' "
            "AND json_extract(b.receipt_json,'$.control_epoch')=c.control_epoch "
            "AND instr(',' || substr(json_extract(b.receipt_json,'$.drain_execution_ids'),2, "
            "length(json_extract(b.receipt_json,'$.drain_execution_ids'))-2) || ',', "
            "',' || json_quote(m.execution_id) || ',')>0),0)=0)",
            (run_id, execution_id)).fetchone() is not None

    def _authorize_managed_operation(
        self,
        connection,
        execution_id: str,
        *,
        timestamp: float,
        operation: str,
        settlement: bool = False,
    ) -> None:
        """Recheck Run control before managed work or effect settlement."""

        row = connection.execute(
            """SELECT m.generation,m.drain_allowed,c.generation,c.state,c.deadline_at,m.run_id
               FROM kernel_managed_executions AS m
               LEFT JOIN kernel_run_controls AS c ON c.run_id=m.run_id
               WHERE m.execution_id=?""",
            (execution_id,),
        ).fetchone()
        if row is None and not execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            return
        if row is None or row[2] is None:
            raise StorageIsolationError(
                f"managed execution lacks its Run control during {operation}"
            )
        # An external effect may finish after pause/deadline changed. Recording
        # that already-authorized outcome grants no new external authority.
        if settlement:
            return
        action = ("effect" if "effect" in operation else
                  "child" if "child" in operation or "supervisor" in operation else
                  "start" if operation == "start" else "work")
        if row[3] == "pausing" and ("child" in operation or "supervisor" in operation or "effect" in operation):
            raise CASConflictError("drain cannot create child work or external effects")
        self._claim_checked_authority(connection, row[5], action, timestamp, execution_id=execution_id)
        if (self._has_unresolved_control_barrier(connection, row[5])
                and not self._drain_barrier_allows(connection, row[5], execution_id)):
            raise CASConflictError("managed Run has an unresolved local pause barrier")
        if row[4] <= timestamp:
            error = CASConflictError("managed Run deadline has elapsed")
            error._budget_deadline = {
                "source": "run", "deadline_at": row[4], "observed_at": timestamp}
            raise error
        if row[3] == "active" and row[0] == row[2]:
            return
        if (
            row[3] == "pausing"
            and row[1] == 1
            and operation not in {"effect preparation", "external effect claim"}
        ):
            return
        raise CASConflictError(
            f"managed Run control does not allow {operation} for this execution"
        )

    def _charge_managed_claim(self, connection, execution_id: str, *, timestamp: float) -> None:
        authority = connection.execute("SELECT run_id FROM kernel_managed_executions WHERE execution_id=?",
                                       (execution_id,)).fetchone()
        if authority is not None:
            self._claim_checked_authority(connection, authority[0], "claim", timestamp, execution_id=execution_id)
            if (self._has_unresolved_control_barrier(connection, authority[0])
                    and not self._drain_barrier_allows(connection, authority[0], execution_id)):
                raise CASConflictError("managed Run has an unresolved local pause barrier")
        if not execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            mapping = connection.execute(
                "SELECT 1 FROM kernel_managed_executions WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
            if mapping is None:
                return
        cursor = connection.execute(
            """UPDATE kernel_run_controls SET claims_used=claims_used+1
               WHERE run_id=(SELECT run_id FROM kernel_managed_executions
                             WHERE execution_id=?)
                 AND claims_used < max_claims AND deadline_at > ?
                 AND EXISTS (
                     SELECT 1 FROM kernel_managed_executions AS m
                     WHERE m.execution_id=? AND m.run_id=kernel_run_controls.run_id
                       AND (
                           (kernel_run_controls.state='active'
                                AND m.generation=kernel_run_controls.generation)
                           OR (kernel_run_controls.state='pausing' AND m.drain_allowed=1)
                       )
                 )""",
            (execution_id, timestamp, execution_id),
        )
        self._cas(cursor, "managed Run claim budget")

    def get_run_control(self, run_id: str) -> dict | None:
        """Read one durable control snapshot without advancing the Kernel clock."""

        run_id = self._managed_run_id(run_id)
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                return self._run_control_snapshot(self._connection, run_id)
            finally:
                self._connection.rollback()

    def register_run_control(
        self, run_id: str, *, max_claims: int, deadline_at: float
    ) -> dict:
        """Idempotently register a managed Run, initially closed to claims."""

        with self._transaction() as (connection, _timestamp):
            return self.register_run_control_in_transaction(
                connection,
                run_id,
                max_claims=max_claims,
                deadline_at=deadline_at,
            )

    def register_run_control_in_transaction(
        self, connection, run_id: str, *, max_claims: int, deadline_at: float
    ) -> dict:
        """Register in a caller-owned transaction for a shared Orchestrator store."""

        run_id = self._managed_run_id(run_id)
        if type(max_claims) is not int or not 0 <= max_claims <= MAX_SQLITE_INTEGER:
            raise ValueError("max_claims must be a non-negative SQLite integer")
        deadline_at = self._number(deadline_at, "deadline_at", minimum=0.0)
        self._require_shared_transaction(connection)

        current = self._run_control_snapshot(connection, run_id)
        if current is not None:
            if current["max_claims"] != max_claims or current["deadline_at"] != deadline_at:
                raise IdempotencyConflictError(
                    "managed Run was registered with different budget limits"
                )
            return current
        connection.execute(
            "INSERT INTO kernel_run_controls "
            "(run_id,control_epoch,generation,state,max_claims,claims_used,deadline_at) "
            "VALUES(?,0,0,'paused',?,0,?)",
            (run_id, max_claims, deadline_at),
        )
        return self._run_control_snapshot(connection, run_id)

    def kernel_store_identity(self, *, timeout_seconds: float | None = None) -> str:
        """Return the persistent logical identity of this Kernel store."""
        with self._control_lock(timeout_seconds):
            row = self._connection.execute(
                "SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if row is None or type(row[0]) is not str or not row[0].strip():
                raise StorageIsolationError("kernel store identity is missing")
            return row[0]

    def fence_cancelled_run(self, operation_id: str, run_id: str, *, expected_epoch: int,
                            generation: int) -> dict:
        """Durably fence Run admission before reporting a cancellation upstream."""
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        if type(operation_id) is not str or not operation_id.strip():
            raise ValueError("operation_id must be non-empty")
        if type(expected_epoch) is not int or not 0 <= expected_epoch < MAX_SQLITE_INTEGER:
            raise ValueError("invalid control epoch")
        with self._transaction() as (connection, timestamp):
            principal, expiry = self._verified_authority(self._worker_credential, run_id, "kernel:cancel", timestamp)
            def revalidate_cancel():
                now = self._advance_clock(connection)
                if self._verified_authority(self._worker_credential, run_id, "kernel:cancel", now) != (principal, expiry):
                    raise StorageIsolationError("host cancellation authority changed")
                if expiry <= self._advance_clock(connection):
                    raise StorageIsolationError("host cancellation authority expired")
            store = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            if store is None:
                raise StorageIsolationError("Kernel store identity is missing")
            old = connection.execute("SELECT run_id,expected_epoch,generation,receipt_json "
                                     "FROM kernel_control_pause_receipts WHERE operation_id=?", (operation_id,)).fetchone()
            if old:
                receipt = json.loads(old[3])
                if (tuple(old[:3]) != (run_id, expected_epoch, generation)
                        or receipt.get("kind") != "cancellation_fence" or receipt.get("store_id") != store[0]):
                    raise CASConflictError("cancellation operation already has different content")
                revalidate_cancel()
                return receipt
            control = connection.execute("SELECT generation,control_epoch,state FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone()
            if control is None or (control[0], control[1]) != (generation, expected_epoch):
                raise CASConflictError("cancellation source control changed")
            cursor = connection.execute("UPDATE kernel_run_controls SET state='paused',control_epoch=? "
                                        "WHERE run_id=? AND generation=? AND control_epoch=?",
                                        (expected_epoch + 1, run_id, generation, expected_epoch))
            self._cas(cursor, "cancellation control fence")
            connection.execute("UPDATE kernel_run_authorities SET revoked_at=? WHERE run_id=? AND revoked_at IS NULL",
                               (timestamp, run_id))
            receipt = {"kind": "cancellation_fence", "operation_id": operation_id, "run_id": run_id,
                       "generation": generation, "expected_epoch": expected_epoch,
                       "control_epoch": expected_epoch + 1, "store_id": store[0],
                       "fenced_at": timestamp, "cleanup": "unknown"}
            connection.execute("INSERT INTO kernel_control_pause_receipts VALUES(?,?,?,?,?)",
                               (operation_id, run_id, expected_epoch, generation, self._encode_pause_receipt(receipt)))
            revalidate_cancel()
            return receipt

    @staticmethod
    def _encode_pause_receipt(receipt: dict) -> str:
        encoded = encode_json(receipt)
        if len(encoded.encode("utf-8")) > _PAUSE_RECEIPT_BYTES:
            raise StorageIsolationError("local pause facts exceed the receipt size limit")
        return encoded

    def prepare_control_pause(self, operation_id: str, run_id: str, *, expected_epoch: int,
                              generation: int, drain_execution_ids: Sequence[str] = (),
                              drain_orchestrator_store_id: str | None = None,
                              drain_orchestrator_incarnation: str | None = None,
                              adoption_credential=None) -> dict:
        """Close local Run admission and durably capture its barrier facts.

        The receipt is local evidence, not proof of host isolation or cleanup.
        No control is created and no historical claim consumption is inferred.
        """
        if type(operation_id) is not str or not operation_id.strip():
            raise ValueError("operation_id must be a non-empty string")
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        if type(expected_epoch) is not int or not 0 <= expected_epoch < MAX_SQLITE_INTEGER:
            raise ValueError("expected_epoch cannot be advanced")
        if (isinstance(drain_execution_ids, (str, bytes, bytearray)) or
                not isinstance(drain_execution_ids, Sequence) or len(drain_execution_ids) > 128 or
                any(type(item) is not str or not item.strip() or len(item.encode("utf-8")) > 4096
                    for item in drain_execution_ids)):
            raise ValueError("drain set must contain at most 128 bounded execution IDs")
        drain_ids = sorted(set(drain_execution_ids))
        if len(encode_json(drain_ids).encode("utf-8")) > 65536:
            raise ValueError("drain set exceeds its byte limit")
        identity_pair = (drain_orchestrator_store_id, drain_orchestrator_incarnation)
        if identity_pair != (None, None) and any(type(v) is not str or not v.strip() or len(v.encode("utf-8")) > 4096 for v in identity_pair):
            raise ValueError("invalid drain Orchestrator identity")
        with self._transaction() as (connection, timestamp):
            self._check_control_authority(connection, run_id, "pause", timestamp)
            def verify_adoption():
                try:
                    proof = self._authority_verifier(adoption_credential)
                    manifest = proof["adoption"]
                    page = connection.execute(
                        "SELECT receipt_json FROM kernel_legacy_import_pages WHERE operation_id=? "
                        "ORDER BY page_seq DESC LIMIT 1", (operation_id,)).fetchone()
                    if page is None:
                        raise ValueError("missing legacy import")
                    receipt = json.loads(page[0])
                    original, current = dict(receipt["adoption"]), dict(manifest)
                    original.pop("isolation_expires_at")
                    current.pop("isolation_expires_at")
                    now = self._advance_clock(connection)
                    if (encode_json(original) != encode_json(current) or
                            receipt.get("capture_complete") is not True or
                            receipt.get("activation") != "closed" or
                            manifest["operation_id"] != operation_id or manifest["run_id"] != run_id or
                            manifest["generation"] != generation or expected_epoch != 0 or
                            manifest["isolation_held"] is not True or
                            self._number(manifest["isolation_expires_at"], "isolation expiry", minimum=0.0) <= now or
                            self._number(proof["expires_at"], "authority expiry", minimum=0.0) <= now or
                            type(proof["principal"]) is not str or not proof["principal"].strip() or
                            not any(tuple(p) == (run_id, "kernel:import_legacy") for p in proof["permissions"])):
                        raise ValueError("adoption evidence differs or expired")
                except Exception:
                    raise StorageIsolationError("host did not authenticate completed legacy adoption") from None
            if adoption_credential is not None:
                if drain_ids:
                    raise StorageIsolationError("adoption pause cannot authorize a drain")
                verify_adoption()
            existing = connection.execute(
                "SELECT run_id,expected_epoch,generation,receipt_json FROM kernel_control_pause_receipts "
                "WHERE operation_id=?", (operation_id,)).fetchone()
            if existing is not None:
                receipt = json.loads(existing[3])
                if (tuple(existing[:3]) != (run_id, expected_epoch, generation)
                        or receipt.get("kind", "pause_barrier") != "pause_barrier"
                        or receipt.get("drain_execution_ids", []) != drain_ids
                        or (receipt.get("drain_orchestrator_store_id"), receipt.get("drain_orchestrator_incarnation")) != identity_pair):
                    raise CASConflictError("pause operation id already identifies another request")
                if drain_ids and connection.execute("SELECT 1 FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone():
                    try:
                        now = self._advance_clock(connection)
                        principal, expires_at = self._verified_authority(self._worker_credential, run_id, "kernel:pause", now)
                        proof = self._authority_verifier(self._worker_credential)
                        expected = {"operation_id": operation_id, "run_id": run_id, "generation": generation,
                            "control_epoch": expected_epoch + 1, "kernel_store_id": receipt["store_id"],
                            "orchestrator_store_id": identity_pair[0], "orchestrator_incarnation": identity_pair[1],
                            "drain_execution_ids": drain_ids}
                        store = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
                        if (identity_pair == (None, None) or store is None or store[0] != receipt["store_id"] or
                            encode_json(proof["drain_pause"]) != encode_json(expected) or proof["principal"] != principal or
                            proof["expires_at"] != expires_at or not any(tuple(item) == (run_id, "kernel:pause") for item in proof["permissions"]) or
                            expires_at <= self._advance_clock(connection)):
                            raise ValueError("drain pause authority differs")
                    except Exception:
                        raise StorageIsolationError("host did not authenticate the drain pause") from None
                return receipt
            if self._has_unresolved_control_barrier(connection, run_id):
                raise CASConflictError("managed Run already has a local pause barrier")
            row = connection.execute(
                "SELECT run_id,control_epoch,generation,state,max_claims,claims_used,deadline_at "
                "FROM kernel_run_controls WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise ExecutionNotFoundError(f"managed Run control {run_id!r} is not registered")
            control = self._run_control_value(row)
            source_state = "paused" if adoption_credential is not None else "active"
            if (control["control_epoch"] != expected_epoch or control["generation"] != generation
                    or control["state"] != source_state):
                raise CASConflictError("managed Run control changed before local pause")
            protected = connection.execute("SELECT 1 FROM kernel_run_authorities WHERE run_id=?", (run_id,)).fetchone() is not None
            expected_drain = None
            if protected and drain_ids:
                if identity_pair == (None, None):
                    raise StorageIsolationError("protected drain requires the authenticated Orchestrator identity")
                store = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
                if store is None:
                    raise StorageIsolationError("Kernel identity is unavailable")
                expected_drain = {"operation_id": operation_id, "run_id": run_id, "generation": generation,
                                  "control_epoch": expected_epoch + 1, "kernel_store_id": store[0],
                                  "orchestrator_store_id": identity_pair[0], "orchestrator_incarnation": identity_pair[1],
                                  "drain_execution_ids": drain_ids}
                def verify_drain_pause():
                    now = self._advance_clock(connection)
                    principal, expires_at = self._verified_authority(self._worker_credential, run_id, "kernel:pause", now)
                    try:
                        proof = self._authority_verifier(self._worker_credential)
                        if (encode_json(proof["drain_pause"]) != encode_json(expected_drain)
                                or proof["principal"] != principal or proof["expires_at"] != expires_at
                                or not any(tuple(item) == (run_id, "kernel:pause") for item in proof["permissions"])
                                or expires_at <= self._advance_clock(connection)):
                            raise ValueError("drain pause differs")
                    except Exception:
                        raise StorageIsolationError("host did not authenticate the drain pause") from None
                verify_drain_pause()
            if drain_ids:
                rows = connection.execute(
                    "SELECT m.execution_id FROM kernel_managed_executions m JOIN kernel_executions e "
                    "ON e.execution_id=m.execution_id WHERE m.run_id=? AND m.generation=? "
                    "AND e.state IN ('queued','leased','running') AND m.execution_id IN (" +
                    ",".join("?" for _ in drain_ids) + ")", (run_id, generation, *drain_ids)).fetchall()
                if {item[0] for item in rows} != set(drain_ids):
                    raise CASConflictError("drain set contains an unaccepted or ineligible execution")
                for execution_id in drain_ids:
                    self._cas(connection.execute("UPDATE kernel_managed_executions SET drain_allowed=1 "
                        "WHERE run_id=? AND generation=? AND execution_id=?",
                        (run_id, generation, execution_id)), "managed Run drain registration")
            cursor = connection.execute(
                "UPDATE kernel_run_controls SET control_epoch=?,state='pausing' "
                "WHERE run_id=? AND control_epoch=? AND generation=? AND state=?",
                (expected_epoch + 1, run_id, expected_epoch, generation, source_state))
            self._cas(cursor, "managed Run local pause barrier")
            receipt = {"kind": "pause_barrier", "operation_id": operation_id, "run_id": run_id, "generation": generation,
                       "expected_epoch": expected_epoch, "control_epoch": expected_epoch + 1,
                       "store_id": connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()[0],
                       "captured_at": timestamp, "claims_used": control["claims_used"],
                       "max_claims": control["max_claims"], "deadline_at": control["deadline_at"],
                       "capture_status": "incomplete", "cleanup": "unknown",
                       "drain_execution_ids": drain_ids, "drain_orchestrator_store_id": identity_pair[0],
                       "drain_orchestrator_incarnation": identity_pair[1]}
            connection.execute("INSERT INTO kernel_control_pause_receipts VALUES(?,?,?,?,?)",
                               (operation_id, run_id, expected_epoch, generation, self._encode_pause_receipt(receipt)))
            if expected_drain is not None:
                verify_drain_pause()
            if adoption_credential is not None:
                verify_adoption()
            return receipt

    def complete_control_pause(self, operation_id: str, barrier_operation_id: str, run_id: str, *,
                               expected_epoch: int, generation: int) -> dict:
        """Record a local paused control state while retaining its admission fence.

        This records neither global pause nor process cleanup, and cannot reopen
        admission. The barrier remains until a separately supported release.
        """
        for value, name in ((operation_id, "operation_id"), (barrier_operation_id, "barrier_operation_id")):
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        if type(expected_epoch) is not int or not 0 <= expected_epoch < MAX_SQLITE_INTEGER:
            raise ValueError("expected_epoch cannot be advanced")
        with self._transaction() as (connection, timestamp):
            self._check_control_authority(connection, run_id, "pause", timestamp)
            previous = connection.execute(
                "SELECT run_id,expected_epoch,generation,receipt_json FROM kernel_control_pause_receipts "
                "WHERE operation_id=?", (operation_id,)).fetchone()
            if previous is not None:
                receipt = json.loads(previous[3])
                if (tuple(previous[:3]) != (run_id, expected_epoch, generation)
                        or receipt.get("kind") != "local_paused"
                        or receipt.get("barrier_operation_id") != barrier_operation_id):
                    raise CASConflictError("pause operation id already identifies another request")
                return receipt
            barrier = connection.execute(
                "SELECT run_id,generation,receipt_json FROM kernel_control_pause_receipts WHERE operation_id=?",
                (barrier_operation_id,)).fetchone()
            if barrier is None or (barrier[0], barrier[1]) != (run_id, generation):
                raise CASConflictError("matching local pause barrier is missing")
            barrier_receipt = json.loads(barrier[2])
            if (barrier_receipt.get("kind", "pause_barrier") != "pause_barrier"
                    or barrier_receipt.get("control_epoch") != expected_epoch):
                raise CASConflictError("local pause barrier epoch changed")
            control = connection.execute("SELECT control_epoch,generation,state FROM kernel_run_controls WHERE run_id=?",
                                         (run_id,)).fetchone()
            if (control is None or control["control_epoch"] != expected_epoch
                    or control["generation"] != generation or control["state"] != "pausing"):
                raise CASConflictError("managed Run control changed before local pause completion")
            for execution_id in barrier_receipt.get("drain_execution_ids", []):
                connection.execute("UPDATE kernel_managed_executions SET drain_allowed=0 "
                                   "WHERE run_id=? AND generation=? AND execution_id=?",
                                   (run_id, generation, execution_id))
            cursor = connection.execute(
                "UPDATE kernel_run_controls SET state='paused',control_epoch=? "
                "WHERE run_id=? AND state='pausing' AND generation=? AND control_epoch=?",
                (expected_epoch + 1, run_id, generation, expected_epoch))
            self._cas(cursor, "managed Run local pause")
            receipt = {"kind": "local_paused", "operation_id": operation_id,
                       "barrier_operation_id": barrier_operation_id, "run_id": run_id,
                       "generation": generation, "expected_epoch": expected_epoch,
                       "control_epoch": expected_epoch + 1,
                       "store_id": barrier_receipt["store_id"], "captured_at": timestamp,
                       "capture_status": "incomplete", "cleanup": "unknown"}
            connection.execute("INSERT INTO kernel_control_pause_receipts VALUES(?,?,?,?,?)",
                               (operation_id, run_id, expected_epoch, generation, self._encode_pause_receipt(receipt)))
            return receipt

    def capture_control_pause_page(self, operation_id: str, *, expected_page: int,
                                   max_items: int = 128, round_id: int = 0) -> dict:
        """Persist a bounded, replayable observation page for a closed barrier.

        Rows describe their individual page observation, not barrier-time facts.
        Completing a round proves only that its keyspace was traversed.
        """
        if type(operation_id) is not str or not operation_id.strip():
            raise ValueError("operation_id must be a non-empty string")
        if type(expected_page) is not int or not 0 <= expected_page < MAX_SQLITE_INTEGER:
            raise ValueError("expected_page must be a non-negative SQLite integer")
        if type(round_id) is not int or not 0 <= round_id <= MAX_SQLITE_INTEGER:
            raise ValueError("round_id must be a non-negative SQLite integer")
        if type(max_items) is not int or not 1 <= max_items <= 1000:
            raise ValueError("max_items must be between 1 and 1000")
        with self._transaction() as (connection, timestamp):
            barrier = connection.execute(
                "SELECT run_id,generation,receipt_json FROM kernel_control_pause_receipts WHERE operation_id=?",
                (operation_id,)).fetchone()
            if barrier is None:
                raise CASConflictError("local pause barrier is missing")
            source = json.loads(barrier[2])
            if source.get("kind", "pause_barrier") != "pause_barrier":
                raise CASConflictError("operation is not a pause barrier")
            old = connection.execute(
                "SELECT page_json FROM kernel_control_pause_pages WHERE operation_id=? AND round_id=? AND page_seq=?",
                (operation_id, round_id, expected_page)).fetchone()
            if old is not None:
                page = json.loads(old[0])
                if page["max_items"] != max_items:
                    raise CASConflictError("pause page already has a different item limit")
                return page
            if round_id:
                previous_round = connection.execute(
                    "SELECT page_json FROM kernel_control_pause_pages WHERE operation_id=? AND round_id=? "
                    "ORDER BY page_seq DESC LIMIT 1", (operation_id, round_id - 1)).fetchone()
                if previous_round is None or not json.loads(previous_round[0])["capture_complete"]:
                    raise CASConflictError("previous pause capture round is incomplete")
            previous = connection.execute(
                "SELECT page_seq,page_json FROM kernel_control_pause_pages WHERE operation_id=? AND round_id=? "
                "ORDER BY page_seq DESC LIMIT 1", (operation_id, round_id)).fetchone()
            if previous is None:
                if expected_page != 0:
                    raise CASConflictError("pause page sequence changed")
                phase, cursor = "executions", ["", "", ""]
                effect_continue = False
            else:
                prior = json.loads(previous[1])
                if previous[0] + 1 != expected_page or prior["capture_complete"]:
                    raise CASConflictError("pause page sequence changed or capture is complete")
                phase, cursor = prior["next_phase"], prior["cursor"]
                effect_continue = prior.get("effect_continue", False)
            control = connection.execute("SELECT generation,state FROM kernel_run_controls WHERE run_id=?",
                                         (barrier[0],)).fetchone()
            if (control is None or control["generation"] != barrier[1]
                    or control["state"] not in {"pausing", "paused"}):
                raise CASConflictError("local pause barrier is no longer closed")
            ticks, deadline = 0, time.monotonic() + 1.0
            expired = False
            def progress():
                nonlocal ticks, expired
                ticks += 1
                expired = ticks > _PAUSE_SQL_TICKS or time.monotonic() >= deadline
                return int(expired)
            connection.set_progress_handler(progress, 1000)
            try:
                if phase == "executions":
                    rows = connection.execute(
                        "SELECT m.execution_id,m.generation,e.state,e.attempt,e.fence,e.started_at,"
                        "e.lease_id,e.lease_owner,e.lease_expires_at,e.recovery_effect_id "
                        "FROM kernel_managed_executions m LEFT JOIN kernel_executions e "
                        "ON e.execution_id=m.execution_id WHERE m.run_id=? AND m.execution_id>? "
                        "ORDER BY m.execution_id LIMIT ?", (barrier[0], cursor[0], max_items)).fetchall()
                else:
                    current = cursor[0] if effect_continue else None
                    if current is None:
                        member = connection.execute(
                            "SELECT execution_id FROM kernel_managed_executions INDEXED BY kernel_pause_membership_order "
                            "WHERE run_id=? AND execution_id>? ORDER BY execution_id LIMIT 1",
                            (barrier[0], cursor[0])).fetchone()
                        current = None if member is None else member[0]
                    rows = [] if current is None else connection.execute(
                        "SELECT f.effect_id,f.execution_id,f.state,f.attempt,f.fence,m.generation AS execution_generation "
                        "FROM kernel_managed_executions m CROSS JOIN kernel_effects f "
                        "INDEXED BY kernel_effects_execution_state ON f.execution_id=m.execution_id "
                        "WHERE m.execution_id=? AND m.run_id=? "
                        "AND f.state IN ('prepared','performing','indeterminate') "
                        "AND (f.state>? OR (f.state=? AND f.effect_id>?)) ORDER BY f.state,f.effect_id LIMIT ?",
                        (current, barrier[0], cursor[1] if effect_continue else "", cursor[1] if effect_continue else "",
                         cursor[2] if effect_continue else "", max_items)).fetchall()
            except sqlite3.OperationalError as error:
                if expired:
                    raise StorageIsolationError("local pause page exceeds the query budget") from error
                raise
            finally:
                connection.set_progress_handler(None, 0)
            items = [dict(row) for row in rows]
            complete = phase == "effects" and current is None
            next_phase = "effects" if phase == "executions" and len(items) < max_items else phase
            if next_phase != phase:
                next_cursor = ["", "", ""]
                next_continue = False
            elif phase == "effects" and current is not None:
                next_continue = len(items) == max_items
                next_cursor = ([current, items[-1]["state"], items[-1]["effect_id"]] if next_continue
                               else [current, "", ""])
            elif items:
                next_cursor = [items[-1]["execution_id"], items[-1].get("state", "") or "",
                               items[-1].get("effect_id", "")]
                next_continue = False
            else:
                next_cursor = cursor
                next_continue = False
            page = {"operation_id": operation_id, "run_id": barrier[0], "generation": barrier[1],
                    "store_id": source["store_id"], "round_id": round_id, "page": expected_page,
                    "max_items": max_items, "phase": phase, "items": items, "captured_at": timestamp,
                    "next_page": None if complete else expected_page + 1, "next_phase": next_phase,
                    "cursor": next_cursor, "effect_continue": next_continue, "capture_complete": complete}
            connection.execute("INSERT INTO kernel_control_pause_pages VALUES(?,?,?,?)",
                               (operation_id, round_id, expected_page, self._encode_pause_receipt(page)))
            return page

    def set_run_control(
        self,
        run_id: str,
        *,
        expected_epoch: int,
        state: str,
        generation: int,
        drain_execution_ids=(),
    ) -> dict:
        """CAS a durable control epoch and replace its scoped drain set."""

        run_id = self._managed_run_id(run_id)
        with self._transaction() as (connection, _timestamp):
            return self.set_run_control_in_transaction(
                connection,
                run_id,
                expected_epoch=expected_epoch,
                state=state,
                generation=generation,
                drain_execution_ids=drain_execution_ids,
            )

    def set_run_control_in_transaction(
        self,
        connection,
        run_id: str,
        *,
        expected_epoch: int,
        state: str,
        generation: int,
        drain_execution_ids=(),
    ) -> dict:
        """Apply the control CAS inside a caller-owned shared-file transaction.

        The caller must have acquired ``BEGIN IMMEDIATE`` and owns commit or
        rollback. Separate database files cannot share this transaction.
        """

        run_id = self._managed_run_id(run_id)
        if type(expected_epoch) is not int or expected_epoch < 0:
            raise ValueError("expected_epoch must be a non-negative integer")
        if expected_epoch >= MAX_SQLITE_INTEGER:
            raise ValueError("expected_epoch cannot be advanced")
        if type(state) is not str or state not in {"active", "pausing", "paused"}:
            raise ValueError("state must be active, pausing, or paused")
        generation = self._managed_generation(generation)
        drain_ids = self._normalize_drain_ids(drain_execution_ids)
        if state != "pausing" and drain_ids:
            raise ValueError("drain_execution_ids are only valid while pausing")
        self._require_shared_transaction(connection)

        clock = connection.execute("SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()
        self._check_control_authority(connection, run_id, "control", max(self._wall_time(), clock[0]))

        if self._has_unresolved_control_barrier(connection, run_id):
            raise CASConflictError("managed Run has an unresolved local pause barrier")
        if state == "active" and connection.execute(
            "SELECT 1 FROM kernel_run_authorities WHERE run_id=?", (run_id,)
        ).fetchone() is not None:
            raise CASConflictError("protected Run activation is not yet supported")

        current = self._run_control_snapshot(connection, run_id)
        if current is None:
            raise ExecutionNotFoundError(f"managed Run control {run_id!r} is not registered")
        target_epoch = expected_epoch + 1
        if current["control_epoch"] == target_epoch:
            if (
                current["state"] == state
                and current["generation"] == generation
                and current["drain_execution_ids"] == drain_ids
            ):
                return current
            raise CASConflictError("managed Run control epoch already has different content")
        if current["control_epoch"] != expected_epoch:
            raise CASConflictError("managed Run control epoch changed")
        if generation < current["generation"]:
            raise ValueError("managed Run generation cannot move backwards")

        if drain_ids:
            placeholders = ",".join("?" for _ in drain_ids)
            rows = connection.execute(
                "SELECT execution_id FROM kernel_managed_executions "
                f"WHERE run_id=? AND generation=? AND execution_id IN ({placeholders})",
                (run_id, generation, *drain_ids),
            ).fetchall()
            if {row[0] for row in rows} != set(drain_ids):
                raise ValueError(
                    "each drain execution must already be registered to this Run and generation"
                )

        cursor = connection.execute(
            "UPDATE kernel_run_controls SET control_epoch=?,generation=?,state=? "
            "WHERE run_id=? AND control_epoch=?",
            (target_epoch, generation, state, run_id, expected_epoch),
        )
        self._cas(cursor, "managed Run control")
        connection.execute(
            "UPDATE kernel_managed_executions SET drain_allowed=0 WHERE run_id=?",
            (run_id,),
        )
        for execution_id in drain_ids:
            cursor = connection.execute(
                "UPDATE kernel_managed_executions SET drain_allowed=1 "
                "WHERE run_id=? AND generation=? AND execution_id=?",
                (run_id, generation, execution_id),
            )
            self._cas(cursor, "managed Run drain registration")
        return self._run_control_snapshot(connection, run_id)

    def submit(self, command: ExecutionCommandV2) -> ExecutionSnapshot:
        if type(command) is not ExecutionCommandV2:
            raise TypeError("submit requires ExecutionCommandV2")
        if command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            raise StorageIsolationError(
                "reserved managed execution IDs require submit_managed"
            )
        encoded = encode_json(command.to_dict())
        with self._transaction() as (connection, timestamp):
            if connection.execute(
                "SELECT 1 FROM kernel_managed_executions WHERE execution_id=?",
                (command.execution_id,),
            ).fetchone() is not None:
                raise StorageIsolationError("managed execution IDs require managed submission")
            row, _ = self._submit_in_transaction(command, encoded, connection, timestamp)
            return self._snapshot(row)

    def submit_managed(
        self, command: ExecutionCommandV2, *, run_id: str, generation: int
    ) -> ExecutionSnapshot:
        """Atomically register and queue one opted-in managed execution."""
        return self._submit_managed(command, run_id=run_id, generation=generation)

    def managed_execution_receipt(self, command: ExecutionCommandV2, *, run_id: str,
                                  generation: int, timeout_seconds: float | None = None,
                                  max_bytes: int | None = None) -> ExecutionSnapshot:
        """Read an existing managed execution and its exact binding atomically.

        This is a receipt lookup, never an admission or an adoption operation.
        Missing executions and missing or mismatched bindings are unknown here.
        """
        if type(command) is not ExecutionCommandV2:
            raise TypeError("managed_execution_receipt requires ExecutionCommandV2")
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        encoded = encode_json(command.to_dict())
        if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= 1048576):
            raise ValueError("max_bytes must be between 1 and 1048576")
        if max_bytes is not None and len(encoded.encode("utf-8")) > max_bytes:
            raise StorageIsolationError("managed execution receipt exceeds bounded size")
        with self._control_lock(timeout_seconds):
            row = self._connection.execute(
                "SELECT e.* FROM kernel_executions e JOIN kernel_managed_executions m "
                "ON m.execution_id=e.execution_id WHERE e.execution_id=? "
                "AND m.run_id=? AND m.generation=? AND e.command_json=? "
                "AND (? IS NULL OR (length(CAST(e.execution_id AS BLOB)) + "
                "length(CAST(e.idempotency_key AS BLOB)) + length(CAST(e.registry_revision AS BLOB)) + "
                "length(CAST(e.command_json AS BLOB)) + coalesce(length(CAST(e.lease_id AS BLOB)),0) + "
                "coalesce(length(CAST(e.lease_owner AS BLOB)),0) + coalesce(length(CAST(e.result_json AS BLOB)),0) + "
                "coalesce(length(CAST(e.recovery_effect_id AS BLOB)),0) + "
                "coalesce(length(CAST(e.recovery_target_state AS BLOB)),0) + "
                "coalesce(length(CAST(e.recovery_reason AS BLOB)),0)) <= ?)",
                (command.execution_id, run_id, generation, encoded, max_bytes, max_bytes),
            ).fetchone()
            if row is None:
                raise StorageIsolationError("managed execution receipt unavailable or mismatched")
            return self._snapshot(row)

    def _submit_supervisor(self, command: ExecutionCommandV2, *, run_id: str, generation: int,
                           parent_lease: ExecutionLease, budget_envelope: BudgetEnvelope,
                           timeout_seconds: float = .1) -> ExecutionSnapshot:
        """Bind reserved supervision to its original live source in one commit.

        The supervisor has its own claim allowance and reserved process pool;
        parent limits and attempt/fence remain authoritative at claim and entry.
        This private SDK composition does not relax submit_child's Run rules.
        """
        if type(parent_lease) is not ExecutionLease or type(budget_envelope) is not BudgetEnvelope:
            raise TypeError("supervisor admission requires an original parent lease and budget")
        return self._submit_managed(command, run_id=run_id, generation=generation,
            parent_lease=parent_lease, budget_envelope=budget_envelope, timeout_seconds=timeout_seconds)

    def managed_admission_provenance(self, command: ExecutionCommandV2, *, run_id: str,
                                     generation: int, receipt_operation_id: str | None = None,
                                     max_bytes: int = 262144) -> dict:
        """Read bounded, exact local admission facts in a single transaction.

        Historical cancellation at attempt zero has ambiguous provenance unless
        the caller supplies its exact durable fenced-cancellation receipt ID.
        """
        if type(command) is not ExecutionCommandV2:
            raise TypeError("managed_admission_provenance requires ExecutionCommandV2")
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        if type(max_bytes) is not int or not 1 <= max_bytes <= 1048576:
            raise ValueError("max_bytes must be between 1 and 1048576")
        if receipt_operation_id is not None and (type(receipt_operation_id) is not str or not receipt_operation_id.strip()):
            raise ValueError("receipt_operation_id must be non-empty")
        encoded = encode_json(command.to_dict())
        if len(encoded.encode("utf-8")) > max_bytes:
            raise StorageIsolationError("managed execution receipt exceeds bounded size")
        with self._transaction() as (connection, _):
            row = connection.execute(
                "SELECT e.* FROM kernel_executions e JOIN kernel_managed_executions m ON m.execution_id=e.execution_id "
                "WHERE e.execution_id=? AND m.run_id=? AND m.generation=? AND e.command_json=? AND "
                "(length(CAST(e.execution_id AS BLOB))+length(CAST(e.idempotency_key AS BLOB))+"
                "length(CAST(e.registry_revision AS BLOB))+length(CAST(e.command_json AS BLOB))+"
                "coalesce(length(CAST(e.lease_id AS BLOB)),0)+coalesce(length(CAST(e.lease_owner AS BLOB)),0)+"
                "coalesce(length(CAST(e.result_json AS BLOB)),0)+coalesce(length(CAST(e.recovery_effect_id AS BLOB)),0)+"
                "coalesce(length(CAST(e.recovery_target_state AS BLOB)),0)+coalesce(length(CAST(e.recovery_reason AS BLOB)),0))<=?",
                (command.execution_id, run_id, generation, encoded, max_bytes)).fetchone()
            if row is None:
                return {"provenance": "unknown", "snapshot": None, "receipt": None}
            snapshot = self._snapshot(row)
            if receipt_operation_id is not None:
                receipt_row = connection.execute(
                    "SELECT CASE WHEN length(CAST(receipt_json AS BLOB))<=? THEN receipt_json END "
                    "FROM kernel_control_pause_receipts WHERE operation_id=?", (max_bytes, receipt_operation_id)).fetchone()
                if receipt_row is None or receipt_row[0] is None:
                    raise StorageIsolationError("bounded cancellation receipt unavailable")
                receipt = json.loads(receipt_row[0])
                store = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
                if (store is None or snapshot.state != "cancelled" or
                    (receipt.get("kind"), receipt.get("operation_id"), receipt.get("run_id"),
                     receipt.get("generation"), receipt.get("execution_id"), receipt.get("store_id")) !=
                    ("cancelled_before_accept", receipt_operation_id, run_id, generation, command.execution_id, store[0])):
                    raise StorageIsolationError("cancellation provenance differs")
                return {"provenance": "cancelled_before_accept", "snapshot": snapshot, "receipt": receipt}
            provenance = "accepted" if snapshot.state != "cancelled" or snapshot.attempt > 0 else "unknown"
            return {"provenance": provenance, "snapshot": snapshot, "receipt": None}

    def _submit_managed(self, command: ExecutionCommandV2, *, run_id: str, generation: int,
                        parent_lease: ExecutionLease | None = None,
                        budget_envelope: BudgetEnvelope | None = None,
                        timeout_seconds: float | None = None) -> ExecutionSnapshot:

        if type(command) is not ExecutionCommandV2:
            raise TypeError("submit_managed requires ExecutionCommandV2")
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        encoded = encode_json(command.to_dict())
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            control = connection.execute(
                "SELECT generation,state FROM kernel_run_controls WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if control is None:
                raise StorageIsolationError("managed Run control is missing")
            mapping = connection.execute(
                "SELECT run_id,generation FROM kernel_managed_executions "
                "WHERE execution_id=?",
                (command.execution_id,),
            ).fetchone()
            existing = connection.execute(
                "SELECT * FROM kernel_executions WHERE execution_id=? OR idempotency_key=? "
                "ORDER BY CASE WHEN execution_id=? THEN 0 ELSE 1 END LIMIT 1",
                (command.execution_id, command.idempotency_key, command.execution_id),
            ).fetchone()
            if existing is not None:
                if existing["command_json"] != encoded:
                    raise IdempotencyConflictError(
                        "execution_id/idempotency_key already identifies another command"
                    )
                if (
                    mapping is None
                    or mapping["run_id"] != run_id
                    or mapping["generation"] != generation
                ):
                    raise IdempotencyConflictError(
                        "existing execution has no matching managed Run registration"
                    )
                if parent_lease is not None:
                    binding = connection.execute("SELECT parent_execution_id,parent_attempt,parent_fence "
                        "FROM kernel_execution_limits WHERE execution_id=?", (command.execution_id,)).fetchone()
                    if binding is None or tuple(binding) != (
                            parent_lease.execution_id, parent_lease.attempt, parent_lease.fence):
                        raise IdempotencyConflictError("existing supervisor has no matching source binding")
                return self._snapshot(existing)
            if mapping is not None:
                pending = connection.execute("SELECT command_json FROM kernel_legacy_pending_commands WHERE execution_id=?",
                                             (command.execution_id,)).fetchone()
                if (pending is None or pending[0] != encoded or mapping["run_id"] != run_id
                        or mapping["generation"] != generation or parent_lease is not None):
                    raise StorageIsolationError("managed execution registration has no matching pending command")
                if control["generation"] != generation or control["state"] != "active":
                    raise CASConflictError("pending execution requires its active generation")
                if self._has_unresolved_control_barrier(connection, run_id):
                    raise CASConflictError("managed Run has an unresolved local pause barrier")
                page = connection.execute("SELECT p.receipt_json FROM kernel_legacy_imports i "
                    "JOIN kernel_legacy_import_pages p ON p.operation_id=i.operation_id WHERE i.run_id=? "
                    "ORDER BY p.page_seq DESC LIMIT 1", (run_id,)).fetchone()
                if page is None or not json.loads(page[0])["capture_complete"]:
                    raise CASConflictError("legacy membership import is incomplete")
                self._check_application_budget(connection, run_id, generation, command.execution_id, timestamp, command_json=encoded)
                self._check_run_authority(connection, run_id, "submit", timestamp, execution_id=command.execution_id)
                row, created = self._submit_in_transaction(command, encoded, connection, timestamp)
                if not created:
                    raise IdempotencyConflictError("pending execution was already accepted with another identity")
                return self._snapshot(row)
            if not command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
                raise ValueError(f"new managed execution_id must start with {MANAGED_EXECUTION_PREFIX!r}")
            if command.correlation_id != run_id:
                raise ValueError("managed execution correlation_id must match run_id")
            if control["generation"] != generation:
                raise CASConflictError("managed execution generation is stale")
            if control["state"] != "active":
                raise CASConflictError(
                    "new managed executions may only be accepted by an active Run"
                )
            self._check_application_budget(connection, run_id, generation, command.execution_id, timestamp, command_json=encoded)
            self._check_run_authority(connection, run_id, "submit", timestamp, execution_id=command.execution_id)
            connection.execute(
                "INSERT INTO kernel_managed_executions "
                "(execution_id,run_id,generation,drain_allowed) VALUES(?,?,?,0)",
                (command.execution_id, run_id, generation),
            )
            row, created = self._submit_in_transaction(
                command, encoded, connection, timestamp
            )
            if not created:
                raise IdempotencyConflictError(
                    "execution was accepted without its managed registration"
                )
            if parent_lease is not None:
                parent = self._assert_lease(connection, parent_lease, timestamp=timestamp, states={"running"})
                self._authorize_managed_operation(connection, parent_lease.execution_id,
                    timestamp=timestamp, operation="supervisor admission")
                self._bind_child_limits(connection, command.execution_id, parent, budget_envelope,
                                        self._child_depth(connection, parent_lease.execution_id) + 1)
            return self._snapshot(row)

    def cancel_before_accept(
        self, command: ExecutionCommandV2, *, reason: str = "execution cancelled"
    ) -> ExecutionSnapshot:
        """Atomically record a previously unseen command as cancelled.

        The submission and normal terminal result/events/outbox share one
        SQLite transaction, so independent workers can never claim the new
        execution. If an exact command was already accepted, return its current
        snapshot unchanged: callers must still cancel it through its runtime
        to enforce revision authority and process-tree cleanup. Conflicting
        execution or idempotency identities fail without changing either row.
        """
        if type(command) is not ExecutionCommandV2:
            raise TypeError("cancel_before_accept requires ExecutionCommandV2")
        if command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
            raise StorageIsolationError(
                "reserved managed execution IDs require cancel_managed_before_accept"
            )
        if type(reason) is not str or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        encoded = encode_json(command.to_dict())
        with self._transaction() as (connection, timestamp):
            if connection.execute(
                "SELECT 1 FROM kernel_managed_executions WHERE execution_id=?",
                (command.execution_id,),
            ).fetchone() is not None:
                raise StorageIsolationError("managed execution IDs require managed cancellation")
            row, created = self._submit_in_transaction(command, encoded, connection, timestamp)
            if not created:
                return self._snapshot(row)
            result = self._cancelled_result(
                row, command, timestamp=timestamp, reason=reason, effect_ids=[])
            return self._terminal(
                connection, row, result, event_type="cancelled", timestamp=timestamp)

    def cancel_fenced_before_accept(self, command: ExecutionCommandV2, *, run_id: str,
                                    generation: int, fence_operation_id: str,
                                    receipt_operation_id: str,
                                    reason: str = "execution cancelled") -> dict:
        """Record exact local non-acceptance under a durable cancellation fence.

        A terminal execution is inserted atomically, so no claimable work exists.
        This local receipt does not establish external writer isolation or settle
        outstanding dispatch permits; the coordinator must establish both.
        """
        if type(command) is not ExecutionCommandV2:
            raise TypeError("cancel_fenced_before_accept requires ExecutionCommandV2")
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        if any(type(v) is not str or not v.strip() for v in
               (fence_operation_id, receipt_operation_id, reason)):
            raise ValueError("operation IDs and reason must be non-empty strings")
        if fence_operation_id == receipt_operation_id or command.correlation_id != run_id:
            raise ValueError("invalid cancellation receipt binding")
        encoded = encode_json(command.to_dict())
        if len(encoded.encode("utf-8")) > 65536 or len(reason.encode("utf-8")) > 4096:
            raise StorageIsolationError("cancellation command or reason exceeds bounded size")
        with self._transaction() as (connection, timestamp):
            principal, expiry = self._verified_authority(self._worker_credential, run_id, "kernel:cancel", timestamp)
            store = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
            fence = connection.execute("SELECT receipt_json FROM kernel_control_pause_receipts WHERE operation_id=?",
                                       (fence_operation_id,)).fetchone()
            control = connection.execute("SELECT generation,control_epoch,state FROM kernel_run_controls WHERE run_id=?",
                                         (run_id,)).fetchone()
            fence_value = json.loads(fence[0]) if fence else {}
            if (store is None or fence_value.get("kind") != "cancellation_fence" or
                (fence_value.get("run_id"), fence_value.get("generation"), fence_value.get("store_id")) !=
                    (run_id, generation, store[0]) or control is None or
                tuple(control) != (generation, fence_value.get("control_epoch"), "paused")):
                raise CASConflictError("current cancellation fence is required")
            old = connection.execute("SELECT receipt_json FROM kernel_control_pause_receipts WHERE operation_id=?",
                                     (receipt_operation_id,)).fetchone()
            existing = connection.execute("SELECT state,CASE WHEN length(CAST(command_json AS BLOB))<=65536 THEN command_json END AS command_json FROM kernel_executions WHERE execution_id=? OR idempotency_key=? "
                                          "ORDER BY CASE WHEN execution_id=? THEN 0 ELSE 1 END LIMIT 1",
                                          (command.execution_id, command.idempotency_key, command.execution_id)).fetchone()
            if old:
                receipt = json.loads(old[0])
                mapping = connection.execute("SELECT run_id,generation FROM kernel_managed_executions WHERE execution_id=?",
                                             (command.execution_id,)).fetchone()
                if (receipt.get("kind"), receipt.get("fence_operation_id"), receipt.get("run_id"),
                    receipt.get("generation"), receipt.get("execution_id"), receipt.get("reason"), receipt.get("store_id")) != (
                    "cancelled_before_accept", fence_operation_id, run_id, generation, command.execution_id, reason, store[0]) or existing is None or existing["command_json"] != encoded or existing["state"] != "cancelled" or mapping is None or tuple(mapping) != (run_id, generation):
                    raise CASConflictError("cancellation receipt differs")
            else:
                if existing is not None:
                    raise StorageIsolationError("prior execution acceptance is not absence evidence")
                mapping = connection.execute("SELECT run_id,generation FROM kernel_managed_executions WHERE execution_id=?",
                                             (command.execution_id,)).fetchone()
                if mapping is not None:
                    pending = connection.execute("SELECT CASE WHEN length(CAST(command_json AS BLOB))<=65536 THEN command_json END FROM kernel_legacy_pending_commands WHERE execution_id=?",
                                                 (command.execution_id,)).fetchone()
                    if tuple(mapping) != (run_id, generation) or pending is None or pending[0] != encoded:
                        raise StorageIsolationError("pending membership command is unavailable or mismatched")
                else:
                    if not command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
                        raise StorageIsolationError("unregistered legacy execution has no authoritative pending binding")
                    connection.execute("INSERT INTO kernel_managed_executions (execution_id,run_id,generation,drain_allowed) VALUES(?,?,?,0)",
                                       (command.execution_id, run_id, generation))
                row, created = self._submit_in_transaction(command, encoded, connection, timestamp)
                if not created:
                    raise StorageIsolationError("execution acceptance is ambiguous")
                result = self._cancelled_result(row, command, timestamp=timestamp, reason=reason, effect_ids=[])
                self._terminal(connection, row, result, event_type="cancelled", timestamp=timestamp)
                receipt = {"kind": "cancelled_before_accept", "operation_id": receipt_operation_id,
                           "fence_operation_id": fence_operation_id, "run_id": run_id,
                           "generation": generation, "control_epoch": fence_value["control_epoch"],
                           "execution_id": command.execution_id, "reason": reason,
                           "store_id": store[0], "recorded_at": timestamp}
                connection.execute("INSERT INTO kernel_control_pause_receipts VALUES(?,?,?,?,?)",
                                   (receipt_operation_id, run_id, fence_value["expected_epoch"], generation,
                                    self._encode_pause_receipt(receipt)))
            now = self._advance_clock(connection)
            if self._verified_authority(self._worker_credential, run_id, "kernel:cancel", now) != (principal, expiry):
                raise StorageIsolationError("host cancellation authority changed")
            if expiry <= self._advance_clock(connection):
                raise StorageIsolationError("host cancellation authority expired")
            return receipt

    def cancel_managed_before_accept(
        self,
        command: ExecutionCommandV2,
        *,
        run_id: str,
        generation: int,
        reason: str = "execution cancelled",
    ) -> ExecutionSnapshot:
        """Atomically bind then cancel a not-yet-accepted managed execution."""

        if type(command) is not ExecutionCommandV2:
            raise TypeError("cancel_managed_before_accept requires ExecutionCommandV2")
        if type(reason) is not str or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        run_id = self._managed_run_id(run_id)
        generation = self._managed_generation(generation)
        encoded = encode_json(command.to_dict())
        with self._transaction() as (connection, timestamp):
            control = connection.execute(
                "SELECT generation FROM kernel_run_controls WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if control is None:
                raise StorageIsolationError("managed Run control is missing")
            mapping = connection.execute(
                "SELECT run_id,generation FROM kernel_managed_executions "
                "WHERE execution_id=?",
                (command.execution_id,),
            ).fetchone()
            existing = connection.execute(
                "SELECT * FROM kernel_executions WHERE execution_id=? OR idempotency_key=? "
                "ORDER BY CASE WHEN execution_id=? THEN 0 ELSE 1 END LIMIT 1",
                (command.execution_id, command.idempotency_key, command.execution_id),
            ).fetchone()
            if existing is not None:
                if existing["command_json"] != encoded:
                    raise IdempotencyConflictError(
                        "execution_id/idempotency_key already identifies another command"
                    )
                if (
                    mapping is None
                    or mapping["run_id"] != run_id
                    or mapping["generation"] != generation
                ):
                    raise IdempotencyConflictError(
                        "existing execution has no matching managed Run registration"
                    )
                return self._snapshot(existing)
            if mapping is not None:
                raise StorageIsolationError(
                    "managed execution registration exists without its Kernel execution"
                )
            if not command.execution_id.startswith(MANAGED_EXECUTION_PREFIX):
                raise ValueError(f"new managed execution_id must start with {MANAGED_EXECUTION_PREFIX!r}")
            if command.correlation_id != run_id:
                raise ValueError("managed execution correlation_id must match run_id")
            if control["generation"] != generation:
                raise CASConflictError("managed execution generation is stale")
            if self._has_unresolved_control_barrier(connection, run_id):
                raise CASConflictError("managed Run has an unresolved local pause barrier")
            self._check_run_authority(connection, run_id, "submit", timestamp)
            connection.execute(
                "INSERT INTO kernel_managed_executions "
                "(execution_id,run_id,generation,drain_allowed) VALUES(?,?,?,0)",
                (command.execution_id, run_id, generation),
            )
            row, created = self._submit_in_transaction(
                command, encoded, connection, timestamp
            )
            if not created:
                raise IdempotencyConflictError(
                    "execution was accepted without its managed registration"
                )
            result = self._cancelled_result(
                row, command, timestamp=timestamp, reason=reason, effect_ids=[]
            )
            return self._terminal(
                connection, row, result, event_type="cancelled", timestamp=timestamp
            )

    def _submit_in_transaction(self, command, encoded, connection, timestamp):
        existing = connection.execute(
            """SELECT * FROM kernel_executions
               WHERE execution_id = ? OR idempotency_key = ?
               ORDER BY CASE WHEN execution_id = ? THEN 0 ELSE 1 END LIMIT 1""",
            (command.execution_id, command.idempotency_key, command.execution_id),
        ).fetchone()
        if existing is not None:
            if existing["command_json"] != encoded:
                raise IdempotencyConflictError(
                    "execution_id/idempotency_key already identifies another command"
                )
            return existing, False
        cursor = connection.execute(
            """INSERT INTO kernel_executions
               (execution_id, idempotency_key, registry_revision, command_json, state,
                attempt, redelivery_count, next_attempt_at, lease_id, lease_owner,
                fence, lease_expires_at, started_at, result_json,
                recovery_effect_id, revision, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'queued', 0, 0, ?, NULL, NULL, 0, NULL, NULL,
                       NULL, NULL, 1, ?, ?)""",
            (
                command.execution_id,
                command.idempotency_key,
                command.registry_revision,
                encoded,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        self._cas(cursor, "execution submission")
        self._event(
            connection,
            execution_id=command.execution_id,
            revision=1,
            event_type="submitted",
            from_state=None,
            to_state="queued",
            data={"command": command.to_dict()},
            timestamp=timestamp,
        )
        return self._get_row(connection, command.execution_id), True

    def _reap_in_transaction(self, connection, timestamp: float) -> list[str]:
        rows = connection.execute(
            """SELECT e.* FROM kernel_executions e
               WHERE e.state IN ('leased', 'running')
                 AND e.lease_expires_at IS NOT NULL AND e.lease_expires_at <= ?
                 AND NOT EXISTS (SELECT 1 FROM kernel_supervisor_obligations so
                     WHERE so.execution_id=e.execution_id AND so.attempt=e.attempt
                       AND so.fence=e.fence AND so.resolution_json IS NULL)
               ORDER BY e.created_at, e.execution_id LIMIT 256""",
            (timestamp,),
        ).fetchall()
        changed: list[str] = []
        for row in rows:
            command = self._command(row["command_json"])
            parked = self._park_unfinished_effects(
                connection, row, timestamp, trigger="lease_expired"
            )
            if parked is not None:
                changed.append(row["execution_id"])
                continue
            if row["attempt"] >= command.retry_policy.max_attempts:
                result = self._dead_result(
                    row,
                    command,
                    timestamp=timestamp,
                    code="lease_retry_exhausted",
                    message="lease expired after the retry budget was exhausted",
                    details={"max_attempts": command.retry_policy.max_attempts},
                    effect_ids=self._execution_effect_ids(
                        connection, row["execution_id"]
                    ),
                )
                self._terminal(
                    connection,
                    row,
                    result,
                    event_type="lease_expired_dead",
                    timestamp=timestamp,
                )
            else:
                reduce_state(
                    row["state"],
                    "lease_expired",
                    execution_id=row["execution_id"],
                    revision=row["revision"],
                    lease_id=row["lease_id"],
                    fence=row["fence"],
                )
                revision = row["revision"] + 1
                redeliveries = row["redelivery_count"] + 1
                delay = command.retry_policy.delay_for_attempt(row["attempt"])
                next_at = self._checked_add(timestamp, delay, "lease retry delay")
                cursor = connection.execute(
                    """UPDATE kernel_executions
                       SET state = 'queued', redelivery_count = ?, next_attempt_at = ?,
                           lease_id = NULL, lease_owner = NULL, lease_expires_at = NULL,
                           started_at = NULL, recovery_effect_id = NULL,
                           revision = ?, updated_at = ?
                       WHERE execution_id = ? AND state = ? AND revision = ?""",
                    (
                        redeliveries,
                        next_at,
                        revision,
                        timestamp,
                        row["execution_id"],
                        row["state"],
                        row["revision"],
                    ),
                )
                self._cas(cursor, "lease expiry redelivery")
                self._event(
                    connection,
                    execution_id=row["execution_id"],
                    revision=revision,
                    event_type="lease_expired_redelivery",
                    from_state=row["state"],
                    to_state="queued",
                    data={"attempt": row["attempt"], "redelivery_count": redeliveries},
                    timestamp=timestamp,
                )
            changed.append(row["execution_id"])
        return changed

    def reap(self) -> list[ExecutionSnapshot]:
        with self._transaction() as (connection, timestamp):
            ids = []
            while True:
                batch = self._reap_in_transaction(connection, timestamp)
                ids.extend(batch)
                if len(batch) < 256:
                    break
            return [self._snapshot(self._get_row(connection, item)) for item in ids]

    def inspect_supervisor_obligations(self, execution_id: str, *, limit: int = 32,
                                       after: tuple[int, int] | None = None) -> dict:
        """Read a bounded page for one execution without inferring cleanup facts."""
        if type(execution_id) is not str or not execution_id.strip():
            raise ValueError("execution_id must be non-empty")
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError("limit must be between 1 and 64")
        if after is not None and (type(after) is not tuple or len(after) != 2 or
                any(type(value) is not int or value < 0 for value in after)):
            raise ValueError("after must be an attempt and fence pair")
        with self._control_lock(None):
            rows = self._connection.execute(
                "SELECT attempt,fence,registered_at,resolution_json FROM kernel_supervisor_obligations "
                "WHERE execution_id=? AND (attempt>? OR (attempt=? AND fence>?)) "
                "ORDER BY attempt,fence LIMIT ?",
                (execution_id, -1 if after is None else after[0],
                 -1 if after is None else after[0], -1 if after is None else after[1], limit + 1)).fetchall()
        page = rows[:limit]
        return {"execution_id": execution_id, "obligations": [
            {"attempt": row["attempt"], "fence": row["fence"], "registered_at": row["registered_at"],
             "state": "unresolved" if row["resolution_json"] is None else "resolved",
             "resolution": None if row["resolution_json"] is None else json.loads(row["resolution_json"])}
            for row in page],
            "next_after": (page[-1]["attempt"], page[-1]["fence"]) if len(rows) > limit else None}

    def register_supervisor_obligation(self, lease: ExecutionLease, *, timeout_seconds=None) -> dict:
        """Persist an exact-generation cleanup obligation before process spawn."""
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            self._assert_lease(connection, lease, timestamp=timestamp, states={"leased", "running"})
            row = connection.execute("SELECT registered_at,resolution_json FROM kernel_supervisor_obligations "
                                     "WHERE execution_id=? AND attempt=? AND fence=?",
                                     (lease.execution_id, lease.attempt, lease.fence)).fetchone()
            if row is None:
                connection.execute("INSERT INTO kernel_supervisor_obligations VALUES(?,?,?,?,NULL)",
                                   (lease.execution_id, lease.attempt, lease.fence, timestamp))
                return {"execution_id": lease.execution_id, "attempt": lease.attempt, "fence": lease.fence,
                        "registered_at": timestamp, "resolved": False}
            if row["resolution_json"] is not None:
                raise CASConflictError("supervisor obligation is already resolved")
            return {"execution_id": lease.execution_id, "attempt": lease.attempt, "fence": lease.fence,
                    "registered_at": row["registered_at"], "resolved": False}

    def resolve_supervisor_obligation(self, credential, *, expected_resolution: dict) -> dict:
        """Resolve only with fresh host-verified cleanup and retry disposition.

        The verifier must authenticate the exact decision and continuously enforce
        its authority through commit. This method cannot establish process cleanup.
        """
        required = {"execution_id", "attempt", "fence", "cleanup", "outcome", "disposition", "evidence"}
        if (type(expected_resolution) is not dict or set(expected_resolution) != required or
                type(expected_resolution.get("execution_id")) is not str or not expected_resolution["execution_id"].strip() or
                any(type(expected_resolution.get(key)) is not int or expected_resolution[key] < 0 for key in ("attempt", "fence")) or
                expected_resolution.get("cleanup") != "confirmed" or
                expected_resolution.get("outcome") not in ("unknown", "failed", "not_invoked") or
                expected_resolution.get("disposition") != "retry_authorized" or
                type(expected_resolution.get("evidence")) is not str or not expected_resolution["evidence"].strip() or
                len(encode_json(expected_resolution).encode("utf-8")) > 65536):
            raise ValueError("invalid supervisor resolution")
        decision = json.loads(encode_json(expected_resolution))
        def verify(connection):
            try:
                proof = self._authority_verifier(credential)
                now = self._advance_clock(connection)
                principal = proof["principal"]
                if (type(principal) is not str or not principal.strip() or
                        self._number(proof["expires_at"], "authority expiry", minimum=0.0) <= now or
                        encode_json(proof["supervisor_resolution"]) != encode_json(decision) or
                        not any(tuple(p) == (decision["execution_id"], "kernel:resolve_supervisor") for p in proof["permissions"])):
                    raise ValueError("resolution authority differs")
                return principal
            except Exception:
                raise StorageIsolationError("host did not authenticate supervisor resolution") from None
        with self._transaction() as (connection, timestamp):
            principal = verify(connection)
            key = (decision["execution_id"], decision["attempt"], decision["fence"])
            row = connection.execute("SELECT registered_at,resolution_json FROM kernel_supervisor_obligations "
                                     "WHERE execution_id=? AND attempt=? AND fence=?", key).fetchone()
            if row is None:
                raise CASConflictError("exact supervisor obligation is unavailable")
            current = connection.execute("SELECT attempt,fence FROM kernel_executions WHERE execution_id=?", (key[0],)).fetchone()
            if current is None or tuple(current) != key[1:]:
                raise CASConflictError("supervisor execution generation changed")
            record = encode_json({"decision": decision, "principal": principal})
            if row["resolution_json"] is not None and row["resolution_json"] != record:
                raise CASConflictError("supervisor obligation has a different resolution")
            connection.execute("UPDATE kernel_supervisor_obligations SET resolution_json=? "
                               "WHERE execution_id=? AND attempt=? AND fence=? AND resolution_json IS NULL", (record, *key))
            if verify(connection) != principal:
                raise StorageIsolationError("supervisor resolution authority changed")
            return {"execution_id": key[0], "attempt": key[1], "fence": key[2], "resolved": True, "resolution": decision}

    def next_queued(self, *, registry_revision: str) -> Optional[ExecutionSnapshot]:
        if type(registry_revision) is not str or not registry_revision.strip():
            raise ValueError("registry_revision must be a non-empty string")
        with self._transaction() as (connection, timestamp):
            self._reap_in_transaction(connection, timestamp)
            row = _next_claim_row(connection, timestamp, (registry_revision,))
            return None if row is None else self._snapshot(row)

    def claim(
        self,
        owner: str,
        *,
        lease_seconds: Optional[float] = None,
        registry_revision: Optional[str] = None,
        registry_revisions: Optional[Sequence[str]] = None,
        budget_scan_cursor: dict | None = None,
        execution_id: str | None = None,
    ) -> Optional[ExecutionLease]:
        if type(owner) is not str or not owner.strip():
            raise ValueError("owner must be a non-empty string")
        if execution_id is not None and (type(execution_id) is not str or not execution_id.strip()):
            raise ValueError("execution_id must be non-empty")
        revisions = _claim_revisions(registry_revision, registry_revisions)
        duration = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        with self._transaction() as (connection, timestamp):
            self._reap_in_transaction(connection, timestamp)
            row = self._next_budget_eligible_claim(connection, timestamp, revisions, execution_id=execution_id, budget_scan_cursor=budget_scan_cursor)
            if row is None:
                return None
            self._assert_budget_clock(connection, row["execution_id"])
            reduce_state(
                row["state"],
                "lease",
                execution_id=row["execution_id"],
                revision=row["revision"],
            )
            lease_id = uuid.uuid4().hex
            attempt = row["attempt"] + 1
            fence = row["fence"] + 1
            revision = row["revision"] + 1
            expires_at = self._checked_add(timestamp, duration, "lease_seconds")
            self._charge_managed_claim(
                connection, row["execution_id"], timestamp=timestamp
            )
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET state = 'leased', attempt = ?, lease_id = ?, lease_owner = ?,
                       fence = ?, lease_expires_at = ?, revision = ?, updated_at = ?
                   WHERE execution_id = ? AND state = 'queued' AND revision = ?""",
                (
                    attempt,
                    lease_id,
                    owner,
                    fence,
                    expires_at,
                    revision,
                    timestamp,
                    row["execution_id"],
                    row["revision"],
                ),
            )
            self._cas(cursor, "execution claim")
            self._event(
                connection,
                execution_id=row["execution_id"],
                revision=revision,
                event_type="leased",
                from_state="queued",
                to_state="leased",
                data={"owner": owner, "attempt": attempt, "fence": fence},
                timestamp=timestamp,
            )
            return ExecutionLease(
                execution_id=row["execution_id"],
                lease_id=lease_id,
                owner=owner,
                fence=fence,
                attempt=attempt,
                expires_at=expires_at,
                revision=revision,
            )

    def claim_and_start(
        self,
        owner: str,
        *,
        lease_seconds: Optional[float] = None,
        start_safety_seconds: float = 5.0,
        registry_revision: Optional[str] = None,
        registry_revisions: Optional[Sequence[str]] = None,
        execution_id: str | None = None,
        timeout_seconds: float | None = None,
        child_pool: bool | None = None,
        exclude_execution_ids: Sequence[str] = (),
        budget_scan_cursor: dict | None = None,
        lifecycle_producer_id: str | None = None,
        lifecycle_slots: int = 0,
    ) -> Optional[ExecutionLease]:
        """Atomically lease and start one queued execution.

        Both canonical transitions and both revisioned events are retained,
        but a runtime crash cannot land between two local commits.  The final
        running row remains fenced and is recovered by normal lease expiry.
        """

        if type(owner) is not str or not owner.strip():
            raise ValueError("owner must be a non-empty string")
        if execution_id is not None and (type(execution_id) is not str or not execution_id.strip()):
            raise ValueError("execution_id must be non-empty")
        if (isinstance(exclude_execution_ids, (str, bytes, bytearray))
                or not isinstance(exclude_execution_ids, Sequence)
                or len(exclude_execution_ids) > 512
                or any(type(item) is not str or not item.strip() for item in exclude_execution_ids)):
            raise ValueError("exclude_execution_ids must contain at most 512 non-empty strings")
        excluded = tuple(dict.fromkeys(exclude_execution_ids))
        revisions = _claim_revisions(registry_revision, registry_revisions)
        floor = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        safety = self._nonnegative_duration(
            start_safety_seconds, "start_safety_seconds"
        )
        if execution_id is not None:
            with self._control_lock(timeout_seconds):
                deadline = self._control_deadline
                unbounded_sample = deadline is None
                limits = self._connection.execute(
                    "SELECT parent_execution_id,envelope_json FROM kernel_execution_limits WHERE execution_id=?",
                    (execution_id,)).fetchone()
            if limits is not None and limits[0] is not None:
                # Sampling waits must release the wrapper lock so an existing
                # live owner can publish its floor. Admission still rechecks
                # the parent relationship and lease in its own transaction.
                from .budget_capture import _KernelBudgetCapture

                envelope = BudgetEnvelope.from_dict(json.loads(limits[1]))
                projected = envelope.recheckpoint(
                    sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
                work = projected.view(sample=projected.checkpoint).remaining_work_seconds
                if work is None or work > 0:
                    if work is not None:
                        work_deadline = time.monotonic() + work
                        deadline = work_deadline if deadline is None else min(deadline, work_deadline)
                    # A caller/configured control deadline owns the admission
                    # window. Unbounded calls retain the short sampling cap,
                    # even when the child has a long finite work budget.
                    remaining = .1 if deadline is None else deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Kernel control admission budget elapsed")
                    capture = _KernelBudgetCapture(self, limits[0])
                    try:
                        capture(projected, timeout_seconds=min(.1, remaining) if unbounded_sample else remaining)
                    except BaseException as exc:
                        if getattr(exc, "budget_sample_token", None) is not None:
                            # Transfer this exact live obligation to the caller's
                            # original retry window; a new sampler cannot own it.
                            exc.budget_sample_owner = capture
                        raise
            if deadline is not None:
                timeout_seconds = deadline - time.monotonic()
                if timeout_seconds <= 0:
                    raise TimeoutError("Kernel control admission budget elapsed")
        if lifecycle_producer_id is not None:
            self._validate_lifecycle_reservation(lifecycle_producer_id, lifecycle_slots)
        elif lifecycle_slots != 0:
            raise ValueError("lifecycle slots require a producer id")
        return self._claim_and_start(owner, revisions=revisions, floor=floor, safety=safety,
            execution_id=execution_id, timeout_seconds=timeout_seconds, child_pool=child_pool,
            exclude_execution_ids=excluded, budget_scan_cursor=budget_scan_cursor,
            lifecycle_producer_id=lifecycle_producer_id, lifecycle_slots=lifecycle_slots)

    def _claim_and_start(self, owner, *, revisions, floor, safety, execution_id,
                         timeout_seconds, child_pool, exclude_execution_ids, budget_scan_cursor,
                         lifecycle_producer_id=None, lifecycle_slots=0):
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            self._reap_in_transaction(connection, timestamp)
            row = self._next_budget_eligible_claim(connection, timestamp, revisions, execution_id, exclude_execution_ids, budget_scan_cursor)
            if row is None:
                return None
            self._assert_budget_clock(connection, row["execution_id"])
            if child_pool is not None:
                relationship = connection.execute(
                    "SELECT parent_execution_id FROM kernel_execution_limits WHERE execution_id=?",
                    (row["execution_id"],)).fetchone()
                if bool(relationship is not None and relationship[0] is not None) != child_pool:
                    # Adoption may have changed the required pool since the
                    # runtime reserved its slot. Leave the work queued.
                    return None
            if execution_id is not None:
                self._assert_child_claim(connection, row["execution_id"], timestamp)
            command = self._command(row["command_json"])
            duration = max(
                floor,
                self._checked_add(
                    command.timeout_seconds,
                    safety,
                    "handler timeout safety",
                ),
            )
            reduce_state(
                row["state"],
                "lease",
                execution_id=row["execution_id"],
                revision=row["revision"],
            )
            reduce_state(
                "leased",
                "start",
                execution_id=row["execution_id"],
                revision=row["revision"] + 1,
            )
            lease_id = uuid.uuid4().hex
            attempt = row["attempt"] + 1
            fence = row["fence"] + 1
            if lifecycle_producer_id is not None:
                self._authorize_lifecycle(connection, row['execution_id'], attempt, fence, 'reserve', timestamp, {'producer_id': lifecycle_producer_id})
                if not self._lifecycle_reserve_in_transaction(connection, row["execution_id"], attempt, fence,
                                                              lifecycle_producer_id, lifecycle_slots):
                    return None
            leased_revision = row["revision"] + 1
            running_revision = leased_revision + 1
            expires_at = self._checked_add(timestamp, duration, "lease_seconds")
            self._charge_managed_claim(
                connection, row["execution_id"], timestamp=timestamp
            )
            self._authorize_managed_operation(connection, row["execution_id"], timestamp=timestamp, operation="start")
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET state = 'running', attempt = ?, lease_id = ?, lease_owner = ?,
                       fence = ?, lease_expires_at = ?, started_at = ?,
                       revision = ?, updated_at = ?
                   WHERE execution_id = ? AND state = 'queued' AND revision = ?""",
                (
                    attempt,
                    lease_id,
                    owner,
                    fence,
                    expires_at,
                    timestamp,
                    running_revision,
                    timestamp,
                    row["execution_id"],
                    row["revision"],
                ),
            )
            self._cas(cursor, "atomic execution claim/start")
            self._event(
                connection,
                execution_id=row["execution_id"],
                revision=leased_revision,
                event_type="leased",
                from_state="queued",
                to_state="leased",
                data={"owner": owner, "attempt": attempt, "fence": fence},
                timestamp=timestamp,
            )
            self._event(
                connection,
                execution_id=row["execution_id"],
                revision=running_revision,
                event_type="started",
                from_state="leased",
                to_state="running",
                data={"attempt": attempt, "fence": fence},
                timestamp=timestamp,
            )
            return ExecutionLease(
                execution_id=row["execution_id"],
                lease_id=lease_id,
                owner=owner,
                fence=fence,
                attempt=attempt,
                expires_at=expires_at,
                revision=running_revision,
            )

    def _authorize_lifecycle(self, connection, execution_id, attempt, fence, operation, timestamp, event=None, *, precommit=True):
        membership = connection.execute("SELECT m.run_id,m.generation FROM kernel_managed_executions m JOIN kernel_run_authorities a ON a.run_id=m.run_id WHERE m.execution_id=?", (execution_id,)).fetchone()
        verifier = self._lifecycle_verifier
        if membership is None and verifier is None:
            return
        run_id, generation = (None, None) if membership is None else tuple(membership)
        if verifier is None:
            raise StorageIsolationError("protected lifecycle requires host authorization")
        identity = dict(run_id=run_id, generation=generation, execution_id=execution_id, attempt=attempt, fence=fence)
        frozen_event = None if event is None else encode_json(event)
        def verify(now):
            try:
                claim = verifier(self._worker_credential, operation, dict(identity), None if frozen_event is None else json.loads(frozen_event))
            except Exception as exc:
                raise StorageIsolationError("host lifecycle verifier failed") from exc
            if not isinstance(claim, dict) or type(claim.get('allowed')) is not bool:
                raise StorageIsolationError("invalid host lifecycle verification result")
            if claim['allowed'] is False:
                raise _LifecycleDenied("host denied lifecycle operation")
            try:
                expiry = self._number(claim['expires_at'], 'lifecycle authority expiry', minimum=0.0)
            except Exception as exc:
                raise StorageIsolationError("invalid host lifecycle authority expiry") from exc
            if expiry <= now:
                raise StorageIsolationError("host lifecycle authority expired")
            if operation == 'ack' and claim.get('receiver_committed') is not True:
                raise StorageIsolationError("host did not verify the receiver commit")
        verify(timestamp)
        if precommit:
            self._precommit_authority_checks.append(lambda: verify(self._advance_clock(connection)))

    @staticmethod
    def _validate_lifecycle_reservation(token, slots):
        if type(token) is not str or not token.strip() or len(token) > 256:
            raise ValueError("invalid lifecycle producer token")
        if type(slots) is not int or not 1 <= slots <= 1024:
            raise ValueError("invalid lifecycle reservation size")

    @staticmethod
    def _lifecycle_reserve_in_transaction(connection, execution_id, attempt, fence, token, slots):
        retired = connection.execute("SELECT attempt,fence FROM kernel_lifecycle_retired WHERE execution_id=?", (execution_id,)).fetchone()
        if retired is not None and (attempt, fence) <= tuple(retired):
            raise LifecycleReceiptExpiredError("lifecycle generation has been retired")
        existing = connection.execute("SELECT execution_id,attempt,fence,slots,state FROM kernel_lifecycle_producers WHERE token=?", (token,)).fetchone()
        if existing is not None:
            if tuple(existing) != (execution_id, attempt, fence, slots, 'open'):
                raise ValueError("lifecycle producer token already used")
            return True
        usage = connection.execute("SELECT COALESCE(SUM(slots),0) FROM kernel_lifecycle_producers WHERE state='open'").fetchone()[0]
        pending_closed = connection.execute("SELECT COUNT(*) FROM kernel_lifecycle_outbox o JOIN kernel_lifecycle_producers p ON p.token=o.token WHERE p.state='closed' AND o.delivered=0").fetchone()[0]
        if usage + pending_closed + slots > 8192:
            return False
        connection.execute("INSERT INTO kernel_lifecycle_producers VALUES(?,?,?,?,?,'open')", (token, execution_id, attempt, fence, slots))
        return True

    def lifecycle_reserve(self, execution_id, attempt, fence, producer_id, *, slots, timeout_seconds=None):
        self._validate_lifecycle_reservation(producer_id, slots)
        if type(execution_id) is not str or not execution_id.strip() or type(attempt) is not int or type(fence) is not int or attempt < 0 or fence < 0:
            raise ValueError("invalid lifecycle identity")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, _):
            row = connection.execute("SELECT attempt,fence FROM kernel_executions WHERE execution_id=?", (execution_id,)).fetchone()
            if row is None:
                raise ValueError("lifecycle execution does not exist")
            if tuple(row) != (attempt, fence):
                established = connection.execute("SELECT 1 FROM kernel_events WHERE execution_id=? AND event_type='leased' AND json_extract(data_json,'$.attempt')=? AND json_extract(data_json,'$.fence')=? LIMIT 1", (execution_id, attempt, fence)).fetchone()
                if established is None:
                    raise ValueError("lifecycle generation was not established")
            self._authorize_lifecycle(connection, execution_id, attempt, fence, 'reserve', _, {'producer_id': producer_id})
            return producer_id if self._lifecycle_reserve_in_transaction(connection, execution_id, attempt, fence, producer_id, slots) else None

    @staticmethod
    def _lifecycle_qualify_token(connection, identity, expected):
        # Once any retirement has happened, an unqualified token could refer
        # to a different generation after its old producer was collected.
        if expected is None:
            if connection.execute("SELECT execution_id FROM kernel_lifecycle_retired LIMIT 1").fetchone():
                raise ValueError("lifecycle generation is required after retirement")
        elif not isinstance(expected, (tuple, list)) or tuple(expected) != tuple(identity):
            raise ValueError("lifecycle producer generation mismatch")

    def lifecycle_append(self, token, event_id, phase, payload, *, identity=None, timeout_seconds=None, include_status=False):
        if any(type(v) is not str or not v.strip() or len(v) > 256 for v in (token, event_id, phase)) or type(payload) is not dict:
            raise ValueError("invalid lifecycle event")
        if phase == 'producer_recovered_evidence_may_be_missing':
            raise ValueError('producer recovery phase is reserved for the Kernel')
        encoded = encode_json(payload)
        if len(encoded.encode('utf-8')) > 1048576:
            raise ValueError("lifecycle payload exceeds limit")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, _):
            producer_identity = connection.execute("SELECT execution_id,attempt,fence FROM kernel_lifecycle_producers WHERE token=?", (token,)).fetchone()
            if producer_identity is None:
                raise ValueError("lifecycle producer does not exist")
            self._lifecycle_qualify_token(connection, producer_identity, identity)
            self._authorize_lifecycle(connection, *tuple(producer_identity), 'append', _, {'producer_id': token, 'event_id': event_id, 'phase': phase, 'payload': json.loads(encoded)})
            event = connection.execute("SELECT sequence,token,phase,payload_json,delivered FROM kernel_lifecycle_outbox WHERE event_id=?", (event_id,)).fetchone()
            if event is not None:
                if event['payload_json'] is None:
                    raise LifecycleReceiptExpiredError("lifecycle receipt payload expired after delivery")
                if tuple(event)[1:4] != (token, phase, encoded):
                    raise ValueError("lifecycle event id already used")
                return (event[0], bool(event[4])) if include_status else event[0]
            producer = connection.execute("SELECT slots,state FROM kernel_lifecycle_producers WHERE token=?", (token,)).fetchone()
            if producer is None or producer['state'] != 'open':
                raise ValueError("lifecycle producer is not open")
            used = connection.execute("SELECT COUNT(*) FROM kernel_lifecycle_outbox WHERE token=? AND delivered=0", (token,)).fetchone()[0]
            if used >= producer['slots']:
                raise RuntimeError("lifecycle producer reservation exhausted")
            sequence = connection.execute("INSERT INTO kernel_lifecycle_outbox(token,event_id,phase,payload_json,delivered) VALUES(?,?,?,?,0)", (token, event_id, phase, encoded)).lastrowid
            return (sequence, False) if include_status else sequence

    def lifecycle_peek(self, *, execution_id=None, exclude_execution_ids=(), after_sequence=0, timeout_seconds=None):
        if (not isinstance(exclude_execution_ids, (tuple, list)) or len(exclude_execution_ids) > 128
                or any(type(item) is not str or not item or len(item) > 4096 for item in exclude_execution_ids)):
            raise ValueError("invalid lifecycle exclusions")
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("invalid lifecycle continuation")
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        if execution_id is not None and (type(execution_id) is not str or not execution_id or len(execution_id) > 4096):
            raise ValueError("invalid lifecycle execution id")
        exclusion = "" if not exclude_execution_ids else " AND p.execution_id NOT IN (" + ",".join("?" for _ in exclude_execution_ids) + ")"
        parameters = tuple(exclude_execution_ids)
        exclusion += " AND o.sequence>? AND NOT EXISTS (SELECT 1 FROM kernel_lifecycle_outbox older JOIN kernel_lifecycle_producers op ON op.token=older.token WHERE op.execution_id=p.execution_id AND older.delivered=0 AND older.sequence<o.sequence)"
        parameters += (after_sequence,)
        if execution_id is not None:
            exclusion += " AND p.execution_id=?"
            parameters += (execution_id,)
        with self._control_lock(timeout_seconds):
            connection = self._connection
            timestamp = max(self._wall_time(), connection.execute("SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()[0])
            rows = connection.execute("SELECT o.sequence,o.event_id,p.execution_id,p.attempt,p.fence,o.phase,o.payload_json FROM kernel_lifecycle_outbox o JOIN kernel_lifecycle_producers p ON p.token=o.token WHERE o.delivered=0" + exclusion + " ORDER BY o.sequence LIMIT 128", parameters).fetchall()
            for row in rows:
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("lifecycle peek deadline elapsed")
                try:
                    self._authorize_lifecycle(connection, row['execution_id'], row['attempt'], row['fence'], 'peek', timestamp, precommit=False)
                except _LifecycleDenied:
                    continue
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("lifecycle peek deadline elapsed")
                result = dict(row)
                result['payload'] = json.loads(result.pop('payload_json'))
                legacy_max = connection.execute("SELECT legacy_max_sequence FROM kernel_lifecycle_metadata WHERE singleton=1").fetchone()[0]
                if result['sequence'] <= legacy_max:
                    result['receiver_note_id'] = result['event_id']
                    result['receiver_store_id'] = None
                else:
                    store_id = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()[0]
                    result['receiver_note_id'] = None
                    result['receiver_store_id'] = store_id
                return result
            return {'continuation': rows[-1]['sequence']} if len(rows) == 128 else None

    def lifecycle_ack(self, sequence, event_id, *, timeout_seconds=None):
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, _):
            row = connection.execute("SELECT o.delivered,p.execution_id,p.attempt,p.fence,o.phase,o.payload_json FROM kernel_lifecycle_outbox o JOIN kernel_lifecycle_producers p ON p.token=o.token WHERE o.sequence=? AND o.event_id=?", (sequence, event_id)).fetchone()
            if row is None:
                return False
            if row['payload_json'] is None:
                raise LifecycleReceiptExpiredError("lifecycle receipt payload expired after delivery")
            store_id = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()[0]
            self._authorize_lifecycle(connection, row['execution_id'], row['attempt'], row['fence'], 'ack', _,
                                      {'store_id': store_id, 'sequence': sequence, 'event_id': event_id,
                                       'phase': row['phase'], 'payload': json.loads(row['payload_json'])})
            if row['delivered']:
                return True
            older = connection.execute("SELECT 1 FROM kernel_lifecycle_outbox o JOIN kernel_lifecycle_producers p ON p.token=o.token WHERE p.execution_id=? AND o.delivered=0 AND o.sequence<? LIMIT 1", (row['execution_id'], sequence)).fetchone()
            if older is not None:
                return False
            connection.execute("UPDATE kernel_lifecycle_outbox SET delivered=1 WHERE sequence=? AND event_id=?", (sequence,event_id))
            return True

    def lifecycle_event_delivered(self, event_id, *, identity=None, timeout_seconds=None):
        with self._control_lock(timeout_seconds):
            connection = self._connection
            timestamp = max(self._wall_time(), connection.execute("SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()[0])
            row = connection.execute("SELECT o.delivered,p.execution_id,p.attempt,p.fence FROM kernel_lifecycle_outbox o JOIN kernel_lifecycle_producers p ON p.token=o.token WHERE o.event_id=?", (event_id,)).fetchone()
            if row is None:
                return None
            self._lifecycle_qualify_token(connection, (row['execution_id'], row['attempt'], row['fence']), identity)
            self._authorize_lifecycle(connection, row['execution_id'], row['attempt'], row['fence'], 'status', timestamp, precommit=False)
            return bool(row['delivered'])

    def lifecycle_retire_generation(self, execution_id, attempt, fence, *, limit=128, timeout_seconds=None):
        """Retire a quiescent generation prefix, collecting at most limit rows.

        The host must establish that no in-memory or future producers for the
        prefix remain. The durable open/pending check cannot prove that fact.
        Repeating the call continues bounded collection after the cutoff is set.
        """
        if (type(execution_id) is not str or not execution_id.strip() or
                type(attempt) is not int or attempt < 0 or type(fence) is not int or fence < 0 or
                type(limit) is not int or not 1 <= limit <= 128):
            raise ValueError("invalid lifecycle retirement bound")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            current = connection.execute("SELECT attempt,fence FROM kernel_executions WHERE execution_id=?", (execution_id,)).fetchone()
            if current is None or (attempt, fence) > tuple(current):
                raise ValueError("lifecycle retirement generation was not established")
            self._authorize_lifecycle(connection, execution_id, attempt, fence, 'retire', timestamp,
                                      {'through_attempt': attempt, 'through_fence': fence})
            old = connection.execute("SELECT attempt,fence FROM kernel_lifecycle_retired WHERE execution_id=?", (execution_id,)).fetchone()
            if old is not None and (attempt, fence) < tuple(old):
                raise ValueError("lifecycle retirement cannot move backwards")
            blocked = connection.execute("SELECT 1 FROM kernel_lifecycle_producers p WHERE p.execution_id=? AND (p.attempt,p.fence)<= (?,?) AND (p.state='open' OR EXISTS (SELECT 1 FROM kernel_lifecycle_outbox o WHERE o.token=p.token AND o.delivered=0)) LIMIT 1", (execution_id, attempt, fence)).fetchone()
            if blocked is not None:
                raise ValueError("lifecycle retirement has open producers or undelivered events")
            connection.execute("INSERT INTO kernel_lifecycle_retired VALUES(?,?,?) ON CONFLICT(execution_id) DO UPDATE SET attempt=excluded.attempt,fence=excluded.fence", (execution_id, attempt, fence))
            rows = connection.execute("SELECT o.sequence,p.attempt,p.fence FROM kernel_lifecycle_outbox o JOIN kernel_lifecycle_producers p ON p.token=o.token WHERE p.execution_id=? AND (p.attempt,p.fence)<= (?,?) ORDER BY o.sequence LIMIT ?", (execution_id, attempt, fence, limit)).fetchall()
            for row in rows:
                self._authorize_lifecycle(connection, execution_id, row['attempt'], row['fence'], 'retire', timestamp, {'sequence': row['sequence'], 'through_attempt': attempt, 'through_fence': fence})
                connection.execute("DELETE FROM kernel_lifecycle_outbox WHERE sequence=? AND delivered=1", (row['sequence'],))
            remaining = limit - len(rows)
            producers = connection.execute("SELECT p.token,p.attempt,p.fence FROM kernel_lifecycle_producers p WHERE p.execution_id=? AND (p.attempt,p.fence)<= (?,?) AND p.state='closed' AND NOT EXISTS (SELECT 1 FROM kernel_lifecycle_outbox o WHERE o.token=p.token) ORDER BY p.rowid LIMIT ?", (execution_id, attempt, fence, remaining)).fetchall()
            for row in producers:
                self._authorize_lifecycle(connection, execution_id, row['attempt'], row['fence'], 'retire', timestamp, {'producer_id': row['token'], 'through_attempt': attempt, 'through_fence': fence})
                connection.execute("DELETE FROM kernel_lifecycle_producers WHERE token=? AND state='closed'", (row['token'],))
            more = connection.execute("SELECT 1 FROM kernel_lifecycle_producers WHERE execution_id=? AND (attempt,fence)<= (?,?) LIMIT 1", (execution_id, attempt, fence)).fetchone() is not None
            return {'events_deleted': len(rows), 'producers_deleted': len(producers), 'more': more}

    def lifecycle_prune_delivered(self, through_sequence, *, after_sequence=0, limit=128, timeout_seconds=None):
        """Discard delivered payloads through an explicit replay cutoff; retain IDs.

        Duplicate append after pruning returns LifecycleReceiptExpiredError, not
        an assertion that its payload matches the retained receipt.
        """
        if (type(through_sequence) is not int or through_sequence < 0 or type(after_sequence) is not int
                or after_sequence < 0 or type(limit) is not int or not 1 <= limit <= 128):
            raise ValueError("invalid lifecycle pruning bound")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            rows = connection.execute("SELECT o.sequence,o.event_id,o.phase,o.payload_json,p.execution_id,p.attempt,p.fence FROM kernel_lifecycle_outbox o JOIN kernel_lifecycle_producers p ON p.token=o.token WHERE o.delivered=1 AND o.payload_json IS NOT NULL AND o.sequence>? AND o.sequence<=? ORDER BY o.sequence LIMIT ?", (after_sequence, through_sequence, limit)).fetchall()
            removed = 0
            for row in rows:
                try:
                    self._authorize_lifecycle(connection, row['execution_id'], row['attempt'], row['fence'], 'prune', timestamp, {'event_id': row['event_id'], 'phase': row['phase'], 'payload': json.loads(row['payload_json'])})
                except _LifecycleDenied:
                    continue
                connection.execute("UPDATE kernel_lifecycle_outbox SET payload_json=NULL WHERE sequence=? AND delivered=1", (row['sequence'],))
                removed += 1
            return {'pruned': removed, 'through_sequence': through_sequence,
                    'continuation': rows[-1]['sequence'] if len(rows) == limit else None}

    def lifecycle_list_open_producers(self, *, after_rowid=0, limit=128, timeout_seconds=None):
        """Page open producer obligations without treating them as death facts."""
        if type(after_rowid) is not int or after_rowid < 0 or type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("invalid lifecycle producer page")
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        with self._control_lock(timeout_seconds):
            connection = self._connection
            timestamp = max(self._wall_time(), connection.execute("SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()[0])
            rows = connection.execute("SELECT rowid AS page_rowid,token,execution_id,attempt,fence,slots FROM kernel_lifecycle_producers WHERE state='open' AND rowid>? ORDER BY rowid LIMIT ?", (after_rowid, limit)).fetchall()
            items = []
            for row in rows:
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("lifecycle producer inspection deadline elapsed")
                try:
                    self._authorize_lifecycle(connection, row['execution_id'], row['attempt'], row['fence'], 'inspect', timestamp, {'producer_id': row['token']}, precommit=False)
                except _LifecycleDenied:
                    continue
                item = {key: row[key] for key in ('token','execution_id','attempt','fence','slots')}
                item['pending'] = connection.execute("SELECT COUNT(*) FROM kernel_lifecycle_outbox WHERE token=? AND delivered=0", (row['token'],)).fetchone()[0]
                items.append(item)
            return {'producers': items, 'continuation': rows[-1]['page_rowid'] if len(rows) == limit else None}

    def lifecycle_inspect_producer(self, token, *, identity=None, timeout_seconds=None):
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = connection.execute("SELECT execution_id,attempt,fence,slots,state FROM kernel_lifecycle_producers WHERE token=?", (token,)).fetchone()
            if row is None:
                return None
            self._lifecycle_qualify_token(connection, (row['execution_id'], row['attempt'], row['fence']), identity)
            self._authorize_lifecycle(connection, row['execution_id'], row['attempt'], row['fence'], 'inspect', timestamp, {'producer_id': token})
            result = dict(row)
            result['pending'] = connection.execute("SELECT COUNT(*) FROM kernel_lifecycle_outbox WHERE token=? AND delivered=0", (token,)).fetchone()[0]
            return result

    def lifecycle_recover_producer(self, token, proof, *, identity=None, timeout_seconds=None):
        """Close a dead owner and durably report that its evidence may be missing."""
        if type(proof) is not dict:
            raise ValueError("host recovery proof must be a mapping")
        frozen_proof = encode_json(proof)
        if len(frozen_proof.encode('utf-8')) > 65536:
            raise ValueError("host recovery proof exceeds limit")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = connection.execute("SELECT p.execution_id,p.attempt,p.fence,p.state,m.run_id,m.generation FROM kernel_lifecycle_producers p LEFT JOIN kernel_managed_executions m ON m.execution_id=p.execution_id WHERE p.token=?", (token,)).fetchone()
            if row is None:
                return False
            self._lifecycle_qualify_token(connection, (row['execution_id'], row['attempt'], row['fence']), identity)
            verifier = self._lifecycle_verifier
            if verifier is None:
                raise StorageIsolationError("host recovery verifier is required")
            identity = dict(execution_id=row['execution_id'], attempt=row['attempt'], fence=row['fence'], run_id=row['run_id'], generation=row['generation'])
            def verify(now):
                try:
                    result = verifier(self._worker_credential, 'recover', dict(identity), {'producer_id': token, 'proof': json.loads(frozen_proof)})
                    if (not isinstance(result, dict) or result.get('allowed') is not True or result.get('producer_dead') is not True
                            or result.get('evidence_unknown_acknowledged') is not True
                            or self._number(result['expires_at'], 'lifecycle authority expiry', minimum=0.0) <= now):
                        raise ValueError("producer death and unknown evidence disposition are not established")
                except Exception as exc:
                    raise StorageIsolationError("host did not establish producer death and unknown evidence disposition") from exc
            verify(timestamp)
            self._precommit_authority_checks.append(lambda: verify(self._advance_clock(connection)))
            marker = connection.execute("SELECT sequence,payload_json FROM kernel_lifecycle_outbox WHERE token=? AND phase='producer_recovered_evidence_may_be_missing'", (token,)).fetchone()
            marker_payload = encode_json({'state': 'unknown', 'reason': 'producer_interrupted'})
            if marker is not None and marker['payload_json'] != marker_payload:
                raise StorageIsolationError('producer recovery marker contents conflict')
            if row['state'] == 'open' and marker is None:
                # Maintenance recovery must have room even if the original
                # producer consumed every reserved ordinary event slot.
                connection.execute("INSERT INTO kernel_lifecycle_outbox(token,event_id,phase,payload_json,delivered) VALUES(?,?,?,?,0)",
                    (token, str(uuid.uuid4()), 'producer_recovered_evidence_may_be_missing',
                     marker_payload))
            elif row['state'] != 'open' and marker is None:
                raise StorageIsolationError('closed producer has no durable recovery disposition')
            connection.execute("UPDATE kernel_lifecycle_producers SET state='closed',slots=0 WHERE token=?", (token,))
            return True

    def lifecycle_finish(self, token, *, identity=None, timeout_seconds=None):
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, _):
            producer_identity = connection.execute("SELECT execution_id,attempt,fence FROM kernel_lifecycle_producers WHERE token=?", (token,)).fetchone()
            if producer_identity is None:
                return False
            self._lifecycle_qualify_token(connection, producer_identity, identity)
            self._authorize_lifecycle(connection, *tuple(producer_identity), 'finish', _, {'producer_id': token})
            cursor = connection.execute("UPDATE kernel_lifecycle_producers SET state='closed',slots=0 WHERE token=?", (token,))
            return cursor.rowcount == 1

    def _verify_active_lease_readonly(self, lease: ExecutionLease) -> ExecutionSnapshot:
        """Inspect delivery authority without advancing the durable clock.

        Each call reads fresh autocommit state and inherits any enclosing
        control deadline. Business authorization continues to use ``verify``.
        """
        with self._control_lock(None):
            if self._connection.in_transaction:
                raise StorageIsolationError("readonly lease inspection requires autocommit")
            clock = self._connection.execute(
                "SELECT watermark FROM kernel_clock WHERE singleton = 1"
            ).fetchone()
            if clock is None:
                raise RuntimeError("kernel logical clock row is missing")
            timestamp = max(self._wall_time(), self._number(
                clock["watermark"], "clock watermark", minimum=0.0))
            row = self._assert_lease(self._connection, lease, timestamp=timestamp,
                                     states={"leased", "running"})
            return self._snapshot(row)

    def verify(self, lease: ExecutionLease) -> ExecutionSnapshot:
        with self._transaction() as (connection, timestamp):
            row = self._assert_lease(
                connection,
                lease,
                timestamp=timestamp,
                states={"leased", "running"},
            )
            self._authorize_managed_operation(connection, lease.execution_id,
                                              timestamp=timestamp, operation="lease verification")
            return self._snapshot(row)

    def start(self, lease: ExecutionLease) -> ExecutionLease:
        with self._transaction() as (connection, timestamp):
            row = self._assert_lease(
                connection, lease, timestamp=timestamp, states={"leased"}
            )
            self._authorize_managed_operation(
                connection,
                lease.execution_id,
                timestamp=timestamp,
                operation="start",
            )
            self._assert_budget_clock(connection, lease.execution_id)
            reduce_state(
                row["state"],
                "start",
                execution_id=lease.execution_id,
                revision=row["revision"],
                lease_id=lease.lease_id,
                fence=lease.fence,
            )
            revision = row["revision"] + 1
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET state = 'running', started_at = ?, revision = ?, updated_at = ?
                   WHERE execution_id = ? AND state = 'leased' AND revision = ?""",
                (timestamp, revision, timestamp, lease.execution_id, row["revision"]),
            )
            self._cas(cursor, "execution start")
            self._event(
                connection,
                execution_id=lease.execution_id,
                revision=revision,
                event_type="started",
                from_state="leased",
                to_state="running",
                data={"attempt": lease.attempt, "fence": lease.fence},
                timestamp=timestamp,
            )
            return ExecutionLease(
                execution_id=lease.execution_id,
                lease_id=lease.lease_id,
                owner=lease.owner,
                fence=lease.fence,
                attempt=lease.attempt,
                expires_at=lease.expires_at,
                revision=revision,
            )

    def renew(
        self, lease: ExecutionLease, *, lease_seconds: Optional[float] = None
    ) -> ExecutionLease:
        duration = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        with self._transaction() as (connection, timestamp):
            row = self._assert_lease(
                connection,
                lease,
                timestamp=timestamp,
                states={"leased", "running"},
            )
            self._authorize_managed_operation(
                connection,
                lease.execution_id,
                timestamp=timestamp,
                operation="lease renewal",
            )
            expires_at = self._checked_add(timestamp, duration, "lease_seconds")
            revision = row["revision"] + 1
            cursor = connection.execute(
                """UPDATE kernel_executions
                   SET lease_expires_at = ?, revision = ?, updated_at = ?
                   WHERE execution_id = ? AND revision = ?""",
                (expires_at, revision, timestamp, lease.execution_id, row["revision"]),
            )
            self._cas(cursor, "lease renewal")
            self._event(
                connection,
                execution_id=lease.execution_id,
                revision=revision,
                event_type="lease_renewed",
                from_state=row["state"],
                to_state=row["state"],
                data={"fence": lease.fence, "expires_at": expires_at},
                timestamp=timestamp,
            )
            return ExecutionLease(
                execution_id=lease.execution_id,
                lease_id=lease.lease_id,
                owner=lease.owner,
                fence=lease.fence,
                attempt=lease.attempt,
                expires_at=expires_at,
                revision=revision,
            )


ExecutionKernel = SQLiteKernel
