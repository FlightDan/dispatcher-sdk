"""Transactional registration for opted-in managed Runs.

This module does not grant execution authority. Kernel registration and the
control barrier must succeed before the managed facade can resume a Run.
"""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from ..execution_kernel import ExecutionCommandV2
from ..execution_kernel.cancellation import CancellationJournal, inspect_cancellation_journal
from .cancellation import _sandbox_facts
from .contracts import (CommandConflict, OrchestrationError, RevisionConflict, TERMINAL,
                        canonical, clone, digest, identifier, integer, validate_operation)
from .reducer import reduce_operation
from .types import RunSnapshot


def _revision_projection(connection, run_id):
    """Read only a bounded inline projection; referenced or large content is unknown."""
    from ..content import CONTENT_PREFIX, decode_value
    limit = 65536
    revision = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
    row = connection.execute("SELECT value FROM sdk_run_items WHERE run_id=? AND section='root' "
                             "AND item_key='application_state' AND length(CAST(value AS BLOB))<=?",
                             (run_id, limit)).fetchone()
    if revision is None or row is None:
        raise OrchestrationError("revision projection is missing or exceeds the bounded read limit")
    encoded = row[0]
    if encoded.startswith(CONTENT_PREFIX):
        try:
            root = json.loads(encoded[len(CONTENT_PREFIX):])
            def has_reference(node):
                if not isinstance(node, list):
                    return False
                return bool(node and node[0] == "ref") or any(has_reference(child) for child in node)
            if has_reference(root):
                raise OrchestrationError("revision projection references external content")
        except (ValueError, RecursionError) as exc:
            raise OrchestrationError("revision projection is invalid") from exc
    value = decode_value(connection, encoded, max_logical_bytes=limit, max_encoded_bytes=limit)
    return {"revision": revision[0], "application_state": value}


def _projection_target_control(connection, operation_id, decision, control):
    """Accept only this revision's installed pause or its committed first resume."""
    if control is None or decision["kernel_install_receipt"] is None or decision["orchestrator_install_receipt"] is None:
        return False
    if tuple(control) == ("paused", decision["source_epoch"] + 1, decision["target_generation"]):
        return True
    if tuple(control) != ("active", decision["source_epoch"] + 2, decision["target_generation"]):
        return False
    rows = connection.execute("SELECT operation_id,kernel_receipt,orchestrator_receipt FROM sdk_revision_resumes WHERE decision_id=?", (operation_id,)).fetchall()
    if len(rows) != 1 or rows[0][1] is None or rows[0][2] is None:
        return False
    local = json.loads(rows[0][2])
    remote = json.loads(rows[0][1])
    envelope = remote.get("decision", {})
    return (local.get("operation_id"), local.get("run_id"), local.get("generation"), local.get("control_epoch"), local.get("state"),
            envelope.get("operation_id"), envelope.get("decision_id"), envelope.get("generation"), envelope.get("target_control_epoch")) == (
            rows[0][0], decision["run_id"], decision["target_generation"], decision["source_epoch"] + 2, "active",
            rows[0][0], operation_id, decision["target_generation"], decision["source_epoch"] + 2)


def _effective_orchestrator_control_lease(connection, operation_id, original):
    row = connection.execute("SELECT claim,kernel_receipt FROM sdk_control_lease_takeovers WHERE operation_id=? AND resolution IS NULL ORDER BY new_fence DESC LIMIT 1", (operation_id,)).fetchone()
    if row is None:
        return original["lease_id"], original["lease_fence"]
    if row[1] is None:
        raise OrchestrationError("control lease takeover has not been acknowledged")
    claim = json.loads(row[0])
    return claim["new_lease_id"], claim["new_fence"]


def _known_orchestrator_control_lease(connection, operation_id, original, binding):
    if binding == (original["lease_id"], original["lease_fence"]):
        return True
    return connection.execute("SELECT 1 FROM sdk_control_lease_takeovers WHERE operation_id=? AND new_fence=? "
                              "AND kernel_receipt IS NOT NULL AND json_extract(claim,'$.new_lease_id')=? LIMIT 1",
                              (operation_id, binding[1], binding[0])).fetchone() is not None


def _check_takeover_budget(connection, operation_id, gate):
    row = connection.execute("SELECT claim FROM sdk_control_lease_takeovers WHERE operation_id=? AND resolution IS NULL "
                             "AND kernel_receipt IS NOT NULL ORDER BY new_fence DESC LIMIT 1", (operation_id,)).fetchone()
    if row is None:
        return
    claim = json.loads(row[0])
    if type(gate) is not dict or any(gate.get(key) != claim[key] for key in ("max_claims", "claims_used", "deadline_at")):
        raise RevisionConflict("control takeover budget facts changed")


def _control_decision_without_lease(envelope):
    return canonical({k: v for k, v in envelope.items() if k not in ("lease_id", "lease_fence", "lease_expires_at")})


def _topological_commands(commands: list[list[Any]]) -> list[list[Any]]:
    """Normalize a task graph while requiring predecessors before reduction."""
    by_id = {item[0]: item for item in commands}
    if len(by_id) != len(commands):
        raise OrchestrationError("managed task identifiers must be unique")
    dependents: dict[str, list[str]] = {task_id: [] for task_id in by_id}
    indegree: dict[str, int] = {}
    for task_id, _, dependencies in commands:
        if any(type(value) is not str or not value.strip() for value in dependencies):
            raise OrchestrationError("dependencies must be task identifiers")
        if len(set(dependencies)) != len(dependencies) or task_id in dependencies:
            raise OrchestrationError("duplicate or self dependency")
        if any(value not in by_id for value in dependencies):
            raise OrchestrationError("managed dependency is not a task in this Run")
        dependencies.sort()
        indegree[task_id] = len(dependencies)
        for dependency in dependencies:
            dependents[dependency].append(task_id)
    ready = [task_id for task_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        task_id = heapq.heappop(ready)
        ordered.append(by_id[task_id])
        for dependent in dependents[task_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(ordered) != len(commands):
        raise OrchestrationError("managed task graph contains a cycle")
    return ordered


class ManagedRunMixin:
    def begin_adopted_cross_store_pause(self, adoption_id: str, *, credential,
                                        delegation_id: str | None = None) -> dict[str, Any]:
        """Create a closed pause operation for a completed legacy adoption.

        The operation retains the adoption ID. Kernel closure still requires a
        fresh host isolation credential in ``advance_cross_store_pause``.
        """
        from .control_authorization import ControlAuthorizer
        identifier(adoption_id, "adoption_id")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        verified = authorizer.verify(credential)
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        if not callable(identity_reader):
            raise OrchestrationError("Kernel participant identity is unknown")
        kernel_id = identity_reader()
        with self._transaction() as connection:
            adoption = connection.execute("SELECT * FROM sdk_legacy_adoptions WHERE operation_id=?", (adoption_id,)).fetchone()
            if adoption is None or adoption["phase"] != "paused":
                raise OrchestrationError("completed legacy adoption is required")
            principal = authorizer.check_in_transaction(connection, verified, adoption["run_id"], "pause", delegation_id)
            page = connection.execute("SELECT manifest,kernel_receipt FROM sdk_legacy_adoption_pages "
                                      "WHERE operation_id=? ORDER BY page_seq DESC LIMIT 1", (adoption_id,)).fetchone()
            if page is None or page["kernel_receipt"] is None:
                raise OrchestrationError("completed legacy adoption receipt is missing")
            manifest, receipt = json.loads(page["manifest"]), json.loads(page["kernel_receipt"])
            receipt_manifest = receipt.get("adoption")
            if type(receipt_manifest) is not dict:
                raise OrchestrationError("legacy adoption receipt is invalid")
            def stable_adoption(value):
                return canonical({key: item for key, item in value.items() if key != "isolation_expires_at"})
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            if (manifest.get("membership_complete") is not True or receipt.get("capture_complete") is not True or
                    receipt.get("activation") != "closed" or manifest.get("kernel_store_id") != kernel_id or
                    stable_adoption(manifest) != stable_adoption(receipt_manifest) or
                    identity is None or tuple(identity) != (manifest.get("orchestrator_store_id"), manifest.get("orchestrator_incarnation")) or
                    self.kernel is not participant):
                raise OrchestrationError("legacy adoption participant evidence changed")
            old = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (adoption_id,)).fetchone()
            if old is not None:
                if (old["run_id"], old["kind"], old["authorized_principal"], old["delegation_id"], old["kernel_store_id"]) != (
                        adoption["run_id"], "pause", principal, delegation_id, kernel_id):
                    raise CommandConflict("adoption pause operation differs")
                return dict(old)
            run = connection.execute("SELECT revision,state FROM sdk_runs WHERE run_id=?", (adoption["run_id"],)).fetchone()
            control = connection.execute("SELECT * FROM sdk_managed_runs WHERE run_id=?", (adoption["run_id"],)).fetchone()
            if (run is None or tuple(run) != (adoption["source_revision"], "running") or control is None or
                    (control["control_state"], control["control_epoch"], control["generation"]) != ("paused", 0, manifest["generation"])):
                raise RevisionConflict("adopted Run control changed")
            now = float(self.clock())
            connection.execute("UPDATE sdk_managed_runs SET control_state='pausing',control_epoch=1,updated_at=? WHERE run_id=?", (now, adoption["run_id"]))
            connection.execute("INSERT INTO sdk_managed_control_transitions VALUES(?,1,'pausing',?,'[]','interrupt',?)", (adoption["run_id"], control["generation"], now))
            connection.execute("INSERT INTO sdk_control_operations VALUES(?,?,'pause',?,?,?,?,?,?,?,?,?,?,'preparing',NULL,NULL,NULL,NULL,NULL,?,?)",
                (adoption_id, adoption["run_id"], run["revision"], 0, control["generation"], control["max_claims"], control["deadline_at"],
                 identity[0], identity[1], kernel_id, principal, delegation_id, now, now))
            return dict(connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (adoption_id,)).fetchone())

    def _authorize_control_continuation(self, operation_id, credential, delegation_id):
        from .control_authorization import ControlAuthorizer
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            operation = connection.execute(
                "SELECT run_id FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if operation is None:
                raise OrchestrationError("unknown cross-store control operation")
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "pause", delegation_id)
        return authorizer, verified

    def begin_cross_store_pause(self, run_id: str, *, operation_id: str,
                                expected_run_revision: int,
                                expected_control_epoch: int, credential,
                                drain_execution_ids: Sequence[str] = (),
                                delegation_id: str | None = None) -> dict[str, Any]:
        """Close the local dispatch gate and persist a split-store pause intent.

        The Kernel participant is advanced separately; this return value never
        certifies that the other store is closed or that a pause is complete.
        """
        identifier(run_id, "run_id")
        identifier(operation_id, "operation_id")
        integer(expected_run_revision, "expected_run_revision")
        integer(expected_control_epoch, "expected_control_epoch")
        if (isinstance(drain_execution_ids, (str, bytes, bytearray))
                or not isinstance(drain_execution_ids, Sequence)
                or any(type(value) is not str or not value.strip()
                       or len(value.encode("utf-8")) > 4096 for value in drain_execution_ids)):
            raise OrchestrationError("invalid drain execution IDs")
        drain_ids = sorted(set(drain_execution_ids))
        encoded_drain = canonical(drain_ids)
        if len(drain_ids) > 128 or len(encoded_drain.encode("utf-8")) > 65536:
            raise OrchestrationError("drain execution IDs exceed the limit")
        from .control_authorization import ControlAuthorizer
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        verified = authorizer.verify(credential)
        kernel_path = getattr(self.kernel, "db_path", None)
        if kernel_path is None or str(Path(kernel_path).resolve()) == self.db_path:
            raise OrchestrationError("cross-store pause requires a separate durable Kernel")
        identity_reader = getattr(self.kernel, "kernel_store_identity", None)
        if not callable(identity_reader) or not callable(getattr(self.kernel, "prepare_control_pause", None)):
            raise OrchestrationError("Kernel lacks an identified durable pause participant")
        kernel_store_id = identity_reader()
        if type(kernel_store_id) is not str or not kernel_store_id:
            raise OrchestrationError("Kernel store identity is unknown")
        now = float(self.clock())
        with self._transaction() as connection:
            principal = authorizer.check_in_transaction(
                connection, verified, run_id, "pause", delegation_id)
            identity = connection.execute(
                "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
            ).fetchone()
            old = connection.execute(
                "SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if old is not None:
                if (old["run_id"], old["kind"], old["source_revision"], old["source_epoch"]) != (
                        run_id, "pause", expected_run_revision, expected_control_epoch):
                    raise CommandConflict("control operation identity already has different content")
                if (old["orchestrator_store_id"], old["orchestrator_incarnation"], old["kernel_store_id"]) != (
                        identity[0], identity[1], kernel_store_id):
                    raise OrchestrationError("control operation participant identity changed")
                if (old["authorized_principal"], old["delegation_id"]) != (principal, delegation_id):
                    raise CommandConflict("control operation authority changed")
                transition = connection.execute(
                    "SELECT drain_execution_ids,pause_mode FROM sdk_managed_control_transitions "
                    "WHERE run_id=? AND control_epoch=?", (run_id, expected_control_epoch + 1)
                ).fetchone()
                if transition is None or tuple(transition) != (encoded_drain, "drain" if drain_ids else "interrupt"):
                    raise CommandConflict("control operation drain selection changed")
                return dict(old)
            run = connection.execute("SELECT revision,state FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
            control = connection.execute("SELECT * FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None or control is None or run["state"] != "running":
                raise OrchestrationError("unknown or terminal managed Run")
            if run["revision"] != expected_run_revision or control["control_epoch"] != expected_control_epoch:
                raise RevisionConflict("managed Run observation changed")
            if control["control_state"] != "active":
                raise OrchestrationError("only an active Run may request pause")
            connection.execute(
                "UPDATE sdk_managed_runs SET control_state='pausing',control_epoch=?,updated_at=? WHERE run_id=?",
                (expected_control_epoch + 1, now, run_id),
            )
            connection.execute(
                "INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                (run_id, expected_control_epoch + 1, "pausing", control["generation"], encoded_drain,
                 "drain" if drain_ids else "interrupt", now),
            )
            connection.execute(
                "INSERT INTO sdk_control_operations VALUES(?,?,'pause',?,?,?,?,?,?,?,?,?,?,'preparing',NULL,NULL,NULL,NULL,NULL,?,?)",
                (operation_id, run_id, expected_run_revision, expected_control_epoch,
                 control["generation"], control["max_claims"], control["deadline_at"],
                 identity[0], identity[1], kernel_store_id,
                 principal, delegation_id, now, now),
            )
            return dict(connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone())

    def complete_cross_store_pause_participant(self, operation_id: str, *, credential,
                                                delegation_id: str | None = None) -> dict[str, Any]:
        """Record the Kernel's local paused receipt, without asserting global pause."""
        identifier(operation_id, "operation_id")
        authorizer, verified = self._authorize_control_continuation(operation_id, credential, delegation_id)
        connection = self._connect()
        try:
            operation = connection.execute(
                "SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            identity = connection.execute(
                "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
            ).fetchone()
        finally:
            connection.close()
        if operation is None or operation["kind"] != "pause" or operation["kernel_receipt"] is None:
            raise OrchestrationError("Kernel pause barrier receipt is required")
        if identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]):
            raise OrchestrationError("control operation Orchestrator identity changed or is unknown")
        identity_reader = getattr(self.kernel, "kernel_store_identity", None)
        participant = getattr(self.kernel, "complete_control_pause", None)
        if not callable(identity_reader) or identity_reader() != operation["kernel_store_id"] or not callable(participant):
            raise OrchestrationError("Kernel pause participant identity is unknown or changed")
        participant_id = operation_id + ":local-paused"
        receipt = participant(participant_id, operation_id, operation["run_id"],
                              expected_epoch=operation["source_epoch"] + 1,
                              generation=operation["generation"])
        if type(receipt) is not dict or (
                receipt.get("kind"), receipt.get("operation_id"), receipt.get("barrier_operation_id"),
                receipt.get("run_id"), receipt.get("generation"), receipt.get("expected_epoch"),
                receipt.get("control_epoch"), receipt.get("store_id")) != (
                "local_paused", participant_id, operation_id, operation["run_id"],
                operation["generation"], operation["source_epoch"] + 1,
                operation["source_epoch"] + 2, operation["kernel_store_id"]):
            raise OrchestrationError("Kernel local pause receipt does not match the operation")
        if len(canonical(receipt).encode("utf-8")) > 1024 * 1024:
            raise OrchestrationError("Kernel local pause receipt exceeds the size limit")
        self._failpoint("after_kernel_pause_completion")
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "pause", delegation_id)
            existing = connection.execute(
                "SELECT kernel_pause_receipt FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if existing is None or (existing[0] is not None and existing[0] != canonical(receipt)):
                raise OrchestrationError("Kernel local pause receipt changed or operation disappeared")
            connection.execute(
                "UPDATE sdk_control_operations SET kernel_pause_receipt=?,updated_at=? WHERE operation_id=?",
                (canonical(receipt), float(self.clock()), operation_id),
            )
            return dict(connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone())

    def prepare_cross_store_pause(self, operation_id: str, *, credential,
                                   delegation_id: str | None = None) -> dict[str, Any]:
        """Record both closed barriers after every tracked handoff is classified.

        Prepared records historical local receipts and dispatch classification.
        Cleanup and host-writer isolation remain explicit dependencies; this
        phase provides no revision, activation or execution permission.
        """
        identifier(operation_id, "operation_id")
        authorizer, verified = self._authorize_control_continuation(operation_id, credential, delegation_id)
        participant_identity = getattr(self.kernel, "kernel_store_identity", None)
        if not callable(participant_identity):
            raise OrchestrationError("Kernel participant identity is unknown")
        kernel_store_id = participant_identity()
        connection = self._connect()
        try:
            observed = connection.execute(
                "SELECT run_id,source_epoch,generation,kernel_store_id FROM sdk_control_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        finally:
            connection.close()
        if observed is None or observed["kernel_store_id"] != kernel_store_id:
            raise OrchestrationError("control operation Kernel identity changed or is unknown")
        gate_reader = getattr(self.kernel, "get_run_control", None)
        gate = gate_reader(observed["run_id"]) if callable(gate_reader) else None
        if (type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) !=
                ("paused", observed["source_epoch"] + 2, observed["generation"])):
            raise OrchestrationError("Kernel local pause barrier is unknown or changed")
        with self._transaction() as connection:
            operation = connection.execute(
                "SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if operation is None or operation["kind"] != "pause":
                raise OrchestrationError("unknown cross-store pause operation")
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "pause", delegation_id)
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            if (identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"])
                    or kernel_store_id != operation["kernel_store_id"]):
                raise OrchestrationError("control operation participant identity changed or is unknown")
            if operation["kernel_receipt"] is None or operation["kernel_pause_receipt"] is None:
                raise OrchestrationError("both Kernel pause receipts are required")
            control = connection.execute(
                "SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?",
                (operation["run_id"],),
            ).fetchone()
            valid_local = (("pausing", operation["source_epoch"] + 1, operation["generation"]),)
            if operation["orchestrator_pause_receipt"] is not None:
                valid_local += (("paused", operation["source_epoch"] + 2, operation["generation"]),)
            if control is None or tuple(control) not in valid_local:
                raise RevisionConflict("Orchestrator pause barrier changed")
            if operation["phase"] == "prepared":
                return dict(operation)
            pending = connection.execute(
                "SELECT o.sequence,json_extract(o.payload,'$.execution_id') AS execution_id,p.state,p.kernel_store_id "
                "FROM sdk_outbox o LEFT JOIN sdk_dispatch_permits p ON p.sequence=o.sequence "
                "WHERE o.run_id=? AND o.delivered=0 AND json_extract(o.payload,'$.kind')='dispatch' "
                "ORDER BY o.sequence LIMIT 1001", (operation["run_id"],),
            ).fetchall()
            uncertain = connection.execute(
                "SELECT sequence,execution_id,state FROM sdk_dispatch_permits "
                "WHERE run_id=? AND (state!='accepted' OR kernel_store_id!=?) ORDER BY sequence LIMIT 1",
                (operation["run_id"], operation["kernel_store_id"]),
            ).fetchall()
            if len(pending) > 1000:
                raise OrchestrationError("cross-store dispatch classification exceeds the bounded preparation limit")
            if uncertain or any(row["state"] != "accepted" for row in pending):
                raise OrchestrationError("cross-store pause has unknown in-flight dispatches")
            pages = connection.execute(
                "SELECT page,receipt FROM sdk_control_capture_pages WHERE operation_id=? AND round_id=0 "
                "ORDER BY page LIMIT 65", (operation_id,),
            ).fetchall()
            if len(pages) > 64:
                raise OrchestrationError("Kernel capture exceeds the bounded preparation limit")
            if not pages or json.loads(pages[-1]["receipt"]).get("capture_complete") is not True:
                raise OrchestrationError("Kernel pause capture is incomplete")
            observations = [json.loads(row["receipt"]) for row in pages]
            if [row["page"] for row in pages] != list(range(len(pages))):
                raise OrchestrationError("Kernel capture pages are incomplete")
            dependencies = []
            for page in observations:
                for item in page["items"]:
                    if type(item) is not dict or type(item.get("execution_id")) is not str:
                        raise OrchestrationError("Kernel capture has invalid dependency facts")
                    generation = item.get("generation" if page["phase"] == "executions" else "execution_generation")
                    if type(generation) is not int or generation < 0:
                        raise OrchestrationError("Kernel capture dependency generation is unknown")
                    dependencies.append({"kind": "execution" if page["phase"] == "executions" else "effect",
                                         "execution_id": item["execution_id"],
                                         "generation": generation,
                                         "state": "unknown", "observed_at": page["captured_at"],
                                         "observed": item})
                    if page["phase"] == "executions":
                        dependencies.append({"kind": "cleanup", "execution_id": item["execution_id"],
                                             "generation": generation,
                                             "state": "unknown"})
            evidence = {"pending_dispatches": [dict(row) for row in pending],
                        "dependencies": dependencies,
                        "capture_pages": len(pages), "capture_consistency": "non_atomic",
                        "fixed_point": "unknown", "writer_isolation": "unknown",
                        "current_gate_state": "unknown",
                        "kernel_gate_observed_at": float(self.clock())}
            connection.execute(
                "UPDATE sdk_control_operations SET phase='prepared',prepared_evidence=?,updated_at=? WHERE operation_id=?",
                (canonical(evidence), float(self.clock()), operation_id),
            )
            return dict(connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone())

    def finalize_cross_store_pause(self, operation_id: str, *, credential,
                                   delegation_id: str | None = None) -> dict[str, Any]:
        """Record the local paused control; cleanup and isolation remain separate facts."""
        identifier(operation_id, "operation_id")
        authorizer, verified = self._authorize_control_continuation(operation_id, credential, delegation_id)
        connection = self._connect()
        try:
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
        finally:
            connection.close()
        if operation is None or operation["phase"] != "prepared":
            raise OrchestrationError("prepared pause decision is required")
        if operation["orchestrator_pause_receipt"] is not None:
            return dict(operation)
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        gate_reader = getattr(participant, "get_run_control", None)
        if not callable(identity_reader) or identity_reader() != operation["kernel_store_id"] or not callable(gate_reader):
            raise OrchestrationError("Kernel participant identity is unknown or changed")
        gate = gate_reader(operation["run_id"])
        epoch = operation["source_epoch"] + 2
        if (type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) !=
                ("paused", epoch, operation["generation"])):
            raise OrchestrationError("Kernel local pause barrier is unknown or changed")
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "pause", delegation_id)
            current = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if current is None or current["phase"] != "prepared" or self.kernel is not participant:
                raise RevisionConflict("pause operation or Kernel participant changed")
            if current["orchestrator_pause_receipt"] is not None:
                return dict(current)
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            if identity is None or tuple(identity) != (current["orchestrator_store_id"], current["orchestrator_incarnation"]):
                raise OrchestrationError("Orchestrator participant identity changed")
            now = float(self.clock())
            changed = connection.execute(
                "UPDATE sdk_managed_runs SET control_state='paused',control_epoch=?,updated_at=? "
                "WHERE run_id=? AND control_state='pausing' AND control_epoch=? AND generation=?",
                (epoch, now, current["run_id"], epoch - 1, current["generation"]),
            ).rowcount
            if changed != 1:
                raise RevisionConflict("Orchestrator pause barrier changed")
            connection.execute("INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                               (current["run_id"], epoch, "paused", current["generation"], "[]", None, now))
            receipt = {"run_id": current["run_id"], "control_epoch": epoch,
                       "generation": current["generation"], "state": "paused", "observed_at": now,
                       "kernel_observation": "non_atomic", "cleanup": "unknown"}
            connection.execute("UPDATE sdk_control_operations SET orchestrator_pause_receipt=?,updated_at=? WHERE operation_id=?",
                               (canonical(receipt), now, operation_id))
            return dict(connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone())

    def capture_cross_store_pause_page(self, operation_id: str, *, credential,
                                       delegation_id: str | None = None, round_id: int = 0,
                                       max_items: int | None = None) -> dict[str, Any]:
        """Persist one replayable bounded Kernel observation page."""
        identifier(operation_id, "operation_id")
        authorizer, verified = self._authorize_control_continuation(operation_id, credential, delegation_id)
        integer(round_id, "round_id")
        if max_items is not None:
            integer(max_items, "max_items")
        if max_items is not None and not 1 <= max_items <= 1000:
            raise OrchestrationError("capture page size must be between 1 and 1000")
        connection = self._connect()
        try:
            operation = connection.execute(
                "SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            identity = connection.execute(
                "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
            ).fetchone()
            last = connection.execute(
                "SELECT page,receipt FROM sdk_control_capture_pages WHERE operation_id=? AND round_id=? "
                "ORDER BY page DESC LIMIT 1", (operation_id, round_id),
            ).fetchone()
            previous = None if round_id == 0 else connection.execute(
                "SELECT receipt FROM sdk_control_capture_pages WHERE operation_id=? AND round_id=? "
                "ORDER BY page DESC LIMIT 1", (operation_id, round_id - 1),
            ).fetchone()
        finally:
            connection.close()
        if operation is None or operation["kernel_pause_receipt"] is None:
            raise OrchestrationError("local Kernel pause receipt is required")
        if identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]):
            raise OrchestrationError("control operation Orchestrator identity changed or is unknown")
        if round_id and (previous is None or json.loads(previous[0]).get("capture_complete") is not True):
            raise OrchestrationError("previous capture round is incomplete")
        if last is not None and json.loads(last["receipt"]).get("capture_complete") is True:
            return json.loads(last["receipt"])
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "pause", delegation_id)
            bound = connection.execute(
                "SELECT max_items FROM sdk_control_capture_rounds WHERE operation_id=? AND round_id=?",
                (operation_id, round_id),
            ).fetchone()
            if bound is None:
                if max_items is None:
                    max_items = 128
                connection.execute("INSERT INTO sdk_control_capture_rounds VALUES(?,?,?)",
                                   (operation_id, round_id, max_items))
            elif max_items is None:
                max_items = bound[0]
            elif bound[0] != max_items:
                raise OrchestrationError("capture round page size differs from its durable request")
        page = 0 if last is None else last["page"] + 1
        identity_reader = getattr(self.kernel, "kernel_store_identity", None)
        participant = getattr(self.kernel, "capture_control_pause_page", None)
        if not callable(identity_reader) or identity_reader() != operation["kernel_store_id"] or not callable(participant):
            raise OrchestrationError("Kernel capture participant identity is unknown or changed")
        receipt = participant(operation_id, round_id=round_id, expected_page=page, max_items=max_items)
        if (type(receipt) is not dict or receipt.get("phase") not in ("executions", "effects") or
                type(receipt.get("items")) is not list or len(receipt["items"]) > max_items or
                type(receipt.get("capture_complete")) is not bool):
            raise OrchestrationError("Kernel capture page is incomplete or malformed")
        if len(canonical(receipt).encode("utf-8")) > 1024 * 1024:
            raise OrchestrationError("Kernel capture page exceeds the receipt size limit")
        if (receipt.get("operation_id"), receipt.get("store_id"), receipt.get("run_id"),
                receipt.get("generation"), receipt.get("round_id"), receipt.get("page")) != (
                operation_id, operation["kernel_store_id"], operation["run_id"],
                operation["generation"], round_id, page):
            raise OrchestrationError("Kernel capture page identity does not match the operation")
        if not receipt["capture_complete"] and receipt.get("next_page") != page + 1:
            raise OrchestrationError("Kernel capture cursor did not advance")
        self._failpoint("after_kernel_capture_page")
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "pause", delegation_id)
            prior = connection.execute(
                "SELECT receipt FROM sdk_control_capture_pages WHERE operation_id=? AND round_id=? AND page=?",
                (operation_id, round_id, page)
            ).fetchone()
            if prior is not None and prior[0] != canonical(receipt):
                raise OrchestrationError("Kernel capture page changed on replay")
            if prior is None:
                connection.execute("INSERT INTO sdk_control_capture_pages VALUES(?,?,?,?)",
                                   (operation_id, round_id, page, canonical(receipt)))
            return receipt

    def commit_cross_store_revision(self, operation_id: str, *, request_id: str, credential,
                                    expected_run_revision: int, expected_control_epoch: int,
                                    expected_generation: int, deployment: Any,
                                    revision: Any, migration_version: str,
                                    application_projection_version: str, migrate,
                                    delegation_id: str | None = None,
                                    external_projection: bool = False,
                                    participant_requirements: list[dict] | None = None,
                                    source_application_projection_version: str | None = None) -> dict[str, Any]:
        """Persist an immutable revision decision while both gates remain closed.

        The application callback must be deterministic and free of external
        business side effects. It runs outside the transaction; its committed
        result is replayed without invoking it again. External projection may
        be requested by the flag or by providing nonempty participant requirements;
        both require an explicit source projection version. This does not install
        or activate the revision, open either gate, or authorize execution.
        """
        from .control_authorization import ControlAuthorizer
        for label, value in (("operation_id", operation_id), ("request_id", request_id),
                             ("migration_version", migration_version),
                             ("application_projection_version", application_projection_version)):
            identifier(value, label)
            if len(value.encode("utf-8")) > 1024:
                raise OrchestrationError(f"{label} exceeds the bounded limit")
        for label, value in (("expected_run_revision", expected_run_revision),
                             ("expected_control_epoch", expected_control_epoch),
                             ("expected_generation", expected_generation)):
            integer(value, label)
        if expected_generation >= (1 << 63) - 1:
            raise OrchestrationError("generation cannot be advanced")
        if type(external_projection) is not bool:
            raise OrchestrationError("invalid external projection flag")
        requirements = [] if participant_requirements is None else clone(participant_requirements)
        if type(requirements) is not list or len(requirements) > 32:
            raise OrchestrationError("invalid projection participant requirements")
        for item in requirements:
            if type(item) is not dict or set(item) != {"participant_id", "scope_id"}:
                raise OrchestrationError("invalid projection participant requirement")
            for key in ("participant_id", "scope_id"):
                identifier(item[key], key)
                if len(item[key].encode("utf-8")) > 1024:
                    raise OrchestrationError("projection participant identity exceeds limit")
        pairs = [(item["participant_id"], item["scope_id"]) for item in requirements]
        if len(set(pairs)) != len(pairs):
            raise OrchestrationError("duplicate projection participant requirement")
        requirements.sort(key=lambda item: (item["participant_id"], item["scope_id"]))
        if len(canonical(requirements).encode("utf-8")) > 65536:
            raise OrchestrationError("projection participant requirements exceed limit")
        if external_projection and not requirements:
            raise OrchestrationError("external projection requires participant requirements")
        if requirements:
            identifier(source_application_projection_version, "source_application_projection_version")
            if len(source_application_projection_version.encode("utf-8")) > 1024:
                raise OrchestrationError("source projection version exceeds limit")
        elif source_application_projection_version is not None:
            raise OrchestrationError("source projection version requires participant requirements")
        if not callable(migrate):
            raise OrchestrationError("application projection migration callback is required")
        frozen_deployment, frozen_revision = clone(deployment), clone(revision)
        if type(frozen_deployment) is not dict:
            raise OrchestrationError("target deployment declaration must be an object")
        if len(canonical(frozen_deployment).encode("utf-8")) > 65536:
            raise OrchestrationError("deployment declaration exceeds the bounded limit")
        if len(canonical(frozen_revision).encode("utf-8")) > 65536:
            raise OrchestrationError("revision declaration exceeds the bounded limit")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        verified = authorizer.verify(credential)
        declaration = canonical({"deployment": frozen_deployment, "revision": frozen_revision,
                                 "migration_version": migration_version,
                                 "application_projection_version": application_projection_version})

        if requirements:
            declaration = canonical({**json.loads(declaration), "participant_requirements": requirements,
                                     "source_application_projection_version": source_application_projection_version})

        def read_source(connection, verified_authority):
            operation = connection.execute(
                "SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if operation is None:
                raise OrchestrationError("unknown pause decision")
            if any(len(operation[key].encode("utf-8")) > 1024 for key in
                   ("run_id", "orchestrator_store_id", "orchestrator_incarnation", "kernel_store_id")):
                raise OrchestrationError("participant identity exceeds the bounded limit")
            principal = authorizer.check_in_transaction(
                connection, verified_authority, operation["run_id"], "commit_revision", delegation_id)
            existing = connection.execute(
                "SELECT * FROM sdk_revision_decisions WHERE run_id=? AND request_id=?",
                (operation["run_id"], request_id),
            ).fetchone()
            if existing is not None:
                if (existing["operation_id"], existing["source_revision"], existing["source_epoch"],
                    existing["source_generation"], existing["decision"], existing["authorized_principal"],
                    existing["delegation_id"]) != (
                    operation_id, expected_run_revision, expected_control_epoch, expected_generation,
                    declaration, principal, delegation_id):
                    raise CommandConflict("revision request identity already has different content")
                stored_requirements = connection.execute("SELECT manifest FROM sdk_external_projection_requirements WHERE operation_id=?", (operation_id,)).fetchone()
                if requirements and (stored_requirements is None or stored_requirements[0] != canonical(requirements)):
                    raise RevisionConflict("projection participant requirements are missing or changed")
                if not requirements and stored_requirements is not None:
                    raise RevisionConflict("unexpected projection participant requirements")
                return operation, None, principal, dict(existing)
            if operation["phase"] != "prepared":
                raise OrchestrationError("prepared pause decision is required")
            control = connection.execute(
                "SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?",
                (operation["run_id"],),
            ).fetchone()
            state = _revision_projection(connection, operation["run_id"])
            if (state["revision"] != expected_run_revision or control is None or tuple(control) !=
                    ("paused", expected_control_epoch, expected_generation) or
                    operation["generation"] != expected_generation or
                    operation["source_epoch"] + 2 != expected_control_epoch or
                    operation["orchestrator_pause_receipt"] is None):
                raise RevisionConflict("revision source observation changed")
            identity = connection.execute(
                "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
            ).fetchone()
            if identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]):
                raise OrchestrationError("revision Orchestrator identity changed")
            if existing is None and connection.execute(
                    "SELECT 1 FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)
            ).fetchone() is not None:
                raise CommandConflict("pause operation already has a revision decision")
            return operation, state, principal, None

        with self._transaction() as connection:
            operation, state, principal, existing = read_source(connection, verified)
            if existing is not None:
                return existing
        source_projection = clone(state["application_state"])
        target_projection = clone(migrate(clone(source_projection), clone(frozen_revision)))
        if len(canonical(target_projection).encode("utf-8")) > 65536:
            raise OrchestrationError("target revision projection exceeds the bounded limit")
        if len(canonical({"declaration": json.loads(declaration), "source": source_projection,
                          "target": target_projection}).encode("utf-8")) > 384 * 1024:
            raise OrchestrationError("revision decision exceeds the bounded limit")
        verified = authorizer.verify(credential)
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        gate_reader = getattr(participant, "get_run_control", None)
        if not callable(identity_reader) or identity_reader() != operation["kernel_store_id"] or not callable(gate_reader):
            raise OrchestrationError("revision Kernel identity is unknown or changed")
        gate = gate_reader(operation["run_id"])
        if (type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) !=
                ("paused", operation["source_epoch"] + 2, expected_generation)):
            raise OrchestrationError("revision Kernel pause barrier is unknown or changed")
        if self.kernel is not participant:
            raise OrchestrationError("revision Kernel participant changed")
        with self._transaction() as connection:
            current, state, current_principal, existing = read_source(connection, verified)
            if existing is not None:
                return existing
            if (current_principal != principal or canonical(state["application_state"]) != canonical(source_projection) or
                    current["kernel_receipt"] != operation["kernel_receipt"] or
                    current["kernel_pause_receipt"] != operation["kernel_pause_receipt"] or
                    current["prepared_evidence"] != operation["prepared_evidence"] or self.kernel is not participant):
                raise RevisionConflict("revision source or participant observation changed")
            now = float(self.clock())
            connection.execute(
                "INSERT INTO sdk_revision_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?)",
                (operation_id, operation["run_id"], request_id, expected_run_revision,
                 expected_control_epoch, expected_generation, expected_generation + 1,
                 canonical(frozen_deployment), migration_version, application_projection_version, canonical(source_projection),
                 canonical(target_projection), declaration, principal, delegation_id, now),
            )
            if requirements:
                connection.execute("INSERT INTO sdk_external_projection_requirements VALUES(?,?)", (operation_id, canonical(requirements)))
            result = dict(connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone())
        self._failpoint("after_revision_decision_commit")
        return result

    def commit_streamed_revision(self, operation_id: str, *, request_id: str, expected_revision: int,
                                 expected_epoch: int, expected_generation: int, deployment: dict,
                                 revision: Any, migration_version: str, projection_version: str,
                                 source_pointer: dict, target_pointer: dict, storage, credential,
                                 lease_credential, projection_credential, source_read_credential=None,
                                 delegation_id: str | None = None) -> dict:
        """Commit host-attested complete direct streams under the exclusive control lease."""
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        from .projection_stream import compare_projection_stream
        from .projection_storage import ProjectionStorage
        for name, value in (("operation_id", operation_id), ("request_id", request_id),
                            ("migration_version", migration_version), ("projection_version", projection_version)):
            identifier(value, name)
            if len(value.encode()) > 1024:
                raise OrchestrationError("revision identity exceeds bounded limit")
        for name, value in (("expected_revision", expected_revision), ("expected_epoch", expected_epoch), ("expected_generation", expected_generation)):
            integer(value, name)
        if expected_generation >= (1 << 63) - 1:
            raise OrchestrationError("generation cannot be advanced")
        if type(storage) is not ProjectionStorage or not callable(self.projection_verifier):
            raise OrchestrationError("configured projection authority and storage are required")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        declaration = {"stream_version": 1, "deployment": clone(deployment), "revision": clone(revision),
                       "migration_version": migration_version, "application_projection_version": projection_version,
                       "source_pointer": clone(source_pointer), "target_pointer": clone(target_pointer)}
        if type(deployment) is not dict or len(canonical(declaration).encode()) > 262144:
            raise OrchestrationError("streamed declaration exceeds bounded limit")
        for pointer in (source_pointer, target_pointer):
            if (type(pointer) is not dict or set(pointer) != {"stream_id", "binding", "total_bytes", "store_id", "incarnation"} or
                    canonical({"store_id": pointer["store_id"], "incarnation": pointer["incarnation"]}) != canonical(storage.identity())):
                raise OrchestrationError("stream pointer or storage identity differs")
            info = storage.inspect(pointer["stream_id"])
            if (not info["complete"] or info["stored_bytes"] != pointer["total_bytes"] or info["total_bytes"] != pointer["total_bytes"] or
                    canonical(info["binding"]) != canonical(pointer["binding"])):
                raise OrchestrationError("complete bound projection stream is required")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None or operation["phase"] != "prepared" or operation["orchestrator_pause_receipt"] is None:
                raise OrchestrationError("prepared participant receipts are required")
            run_id = operation["run_id"]
            principal = authorizer.check_in_transaction(connection, verified, run_id, "commit_revision", delegation_id)
            expected = {"operation_id": operation_id, "run_id": run_id, "kernel_store_id": operation["kernel_store_id"],
                        "orchestrator_store_id": operation["orchestrator_store_id"], "orchestrator_incarnation": operation["orchestrator_incarnation"]}
            lease = check_control_lease(self, connection, lease_credential, expected)
            mappings = {}
            for kind, pointer in (("source_application_state", source_pointer), ("target_application_state", target_pointer)):
                page = connection.execute("SELECT page,kernel_receipt FROM sdk_revision_content_pages WHERE operation_id=? AND content_kind=? ORDER BY page_seq DESC LIMIT 1", (operation_id, kind)).fetchone()
                if page is None or page["kernel_receipt"] is None:
                    raise OrchestrationError("complete Kernel content receipt is required")
                terms, receipt = json.loads(page["page"]), json.loads(page["kernel_receipt"])
                if (not terms["complete"] or not receipt.get("capture_complete") or receipt.get("cumulative_bytes") != pointer["total_bytes"] or
                        terms["lease_id"] != lease["lease_id"] or terms["lease_fence"] != lease["lease_fence"]):
                    raise OrchestrationError("Kernel content stream is incomplete or lease differs")
                mappings[kind] = {"operation_id": operation_id, "total_bytes": pointer["total_bytes"],
                                  "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]}
            declaration["content_pages"] = mappings
            expected_claim = {**expected, "source_revision": expected_revision, "source_epoch": expected_epoch,
                              "source_generation": expected_generation, "declaration": declaration,
                              "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]}
            def attest():
                claim = self.projection_verifier(projection_credential, storage)
                if type(claim) is not dict or claim.get("retained_immutable") is not True or claim.get("valid_json") is not True or canonical(claim.get("decision")) != canonical(expected_claim):
                    raise OrchestrationError("host projection decision authority is unknown")
            attest()
            prior = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            if prior is not None:
                if (prior["request_id"], prior["source_revision"], prior["source_epoch"], prior["source_generation"],
                        prior["authorized_principal"], prior["delegation_id"], prior["decision"]) != (
                        request_id, expected_revision, expected_epoch, expected_generation, principal, delegation_id, canonical(declaration)):
                    raise CommandConflict("streamed decision differs")
                return dict(prior)
        compare_projection_stream(self, run_id, expected_revision=expected_revision, storage=storage,
                                  stream_id=source_pointer["stream_id"], expected_binding=source_pointer["binding"],
                                  source_read_credential=source_read_credential)
        participant = self.kernel
        gate_reader = getattr(participant, "get_run_control", None)
        if not callable(gate_reader):
            raise OrchestrationError("Kernel pause observation is unavailable")
        gate = gate_reader(run_id)
        if type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) != ("paused", expected_epoch, expected_generation):
            raise RevisionConflict("Kernel pause observation changed")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            if authorizer.check_in_transaction(connection, verified, run_id, "commit_revision", delegation_id) != principal:
                raise RevisionConflict("streamed decision authority changed")
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            attest()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            current = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            current_operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            prior = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            if prior is not None:
                if prior["request_id"] != request_id or prior["decision"] != canonical(declaration):
                    raise CommandConflict("streamed decision differs")
                return dict(prior)
            if (control is None or tuple(control) != ("paused", expected_epoch, expected_generation) or current is None or current[0] != expected_revision or
                    identity is None or tuple(identity) != (expected["orchestrator_store_id"], expected["orchestrator_incarnation"]) or
                    self.kernel is not participant or self.kernel.kernel_store_identity() != expected["kernel_store_id"] or
                    current_operation is None or any(current_operation[key] != operation[key] for key in
                        ("phase", "generation", "source_epoch", "kernel_receipt", "kernel_pause_receipt", "orchestrator_pause_receipt", "prepared_evidence"))):
                raise RevisionConflict("streamed revision source changed")
            for kind, mapping in mappings.items():
                last = connection.execute("SELECT page,kernel_receipt FROM sdk_revision_content_pages WHERE operation_id=? AND content_kind=? ORDER BY page_seq DESC LIMIT 1", (operation_id, kind)).fetchone()
                if last is None or last["kernel_receipt"] is None or not json.loads(last["kernel_receipt"]).get("capture_complete") or json.loads(last["kernel_receipt"]).get("cumulative_bytes") != mapping["total_bytes"]:
                    raise RevisionConflict("Kernel content receipt changed")
            connection.execute("INSERT INTO sdk_revision_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?)",
                (operation_id, run_id, request_id, expected_revision, expected_epoch, expected_generation, expected_generation + 1,
                 canonical(deployment), migration_version, projection_version, canonical(source_pointer), canonical(target_pointer),
                 canonical(declaration), principal, delegation_id, float(self.clock())))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            return dict(connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone())

    def reconcile_external_projection(self, operation_id: str, *, participant_id: str,
                                      scope_id: str, participant, credential,
                                      lease_credential, projection_credential,
                                      delegation_id: str | None = None) -> dict:
        """Record a host-attested application receipt for a committed revision.

        The participant must atomically persist its application projection and its
        participant-issued receipt, expose inspect(binding) and idempotent
        apply(binding, source, target, context), and atomically compare the
        expected source version and fence stale concurrent writers. The
        configured projection verifier receives a phase descriptor containing the
        exact binding and stored source and target. For apply_authorization it
        must grant that scope with an expiry; for receipt it must attest the exact
        durable commit and continued retention. The host must serialize authority
        revocation and external writes through the lease and each external write.
        Participants are trusted with the entire Run projection; scope-specific
        data custody is not provided. This foundation does not authorize scope
        admission until the receipt is installed in the Kernel.
        """
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        for name, value in (("operation_id", operation_id), ("participant_id", participant_id), ("scope_id", scope_id)):
            identifier(value, name)
            if len(value.encode("utf-8")) > 1024:
                raise OrchestrationError("projection participant identity exceeds limit")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self or not callable(self.projection_verifier):
            raise OrchestrationError("trusted projection and control authorities are required")
        inspect, apply = getattr(participant, "inspect", None), getattr(participant, "apply", None)
        if not callable(inspect) or not callable(apply):
            raise OrchestrationError("projection participant is unavailable")
        observe_control_clock(self)
        verified = authorizer.verify(credential)

        def read(connection, verified_authority):
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            manifest = connection.execute("SELECT manifest FROM sdk_external_projection_requirements WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None or decision is None or manifest is None:
                raise OrchestrationError("committed external projection decision is required")
            authorizer.check_in_transaction(connection, verified_authority, operation["run_id"], "install_revision", delegation_id)
            declaration = json.loads(decision["decision"])
            if canonical(declaration.get("participant_requirements")) != manifest[0]:
                raise RevisionConflict("projection participant requirements changed")
            if {"participant_id": participant_id, "scope_id": scope_id} not in json.loads(manifest[0]):
                raise OrchestrationError("projection participant scope is not required")
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (operation["run_id"],)).fetchone()
            source_control = ("paused", decision["source_epoch"], decision["source_generation"])
            target_control = _projection_target_control(connection, operation_id, decision, control)
            if (identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]) or
                    control is None or (tuple(control) != source_control and not target_control)):
                raise RevisionConflict("external projection decision or control changed")
            if target_control:
                installed_decision = json.loads(decision["kernel_install_receipt"]).get("decision", {})
                if (installed_decision.get("decision_id") != operation_id or
                        canonical(installed_decision.get("projection_requirements")) != manifest[0] or
                        installed_decision.get("source_application_projection_version") != declaration.get("source_application_projection_version")):
                    raise RevisionConflict("installed Kernel projection decision changed")
            expected = {"operation_id": operation_id, "run_id": operation["run_id"], "kernel_store_id": operation["kernel_store_id"],
                        "orchestrator_store_id": operation["orchestrator_store_id"], "orchestrator_incarnation": operation["orchestrator_incarnation"]}
            lease = check_control_lease(self, connection, lease_credential, expected)
            binding = {"decision_id": operation_id, "run_id": decision["run_id"],
                       "kernel_store_id": operation["kernel_store_id"], "orchestrator_store_id": operation["orchestrator_store_id"],
                       "orchestrator_incarnation": operation["orchestrator_incarnation"],
                       "source_revision": decision["source_revision"], "source_epoch": decision["source_epoch"],
                       "source_generation": decision["source_generation"], "target_generation": decision["target_generation"],
                       "migration_version": decision["migration_version"], "application_projection_version": decision["application_projection_version"],
                       "source_application_projection_version": declaration["source_application_projection_version"],
                       "participant_id": participant_id, "scope_id": scope_id}
            return dict(decision), manifest[0], expected, lease, binding, tuple(control)

        with self._transaction() as connection:
            decision, manifest, expected, lease, binding, control = read(connection, verified)
        kernel = self.kernel
        def check_kernel():
            identity_reader = getattr(kernel, "kernel_store_identity", None)
            gate_reader = getattr(kernel, "get_run_control", None)
            if (self.kernel is not kernel or not callable(identity_reader) or not callable(gate_reader) or
                    identity_reader() != expected["kernel_store_id"]):
                raise RevisionConflict("external projection Kernel identity changed")
            gate = gate_reader(expected["run_id"])
            if (type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) !=
                    control):
                raise RevisionConflict("external projection Kernel control changed")
        check_kernel()
        source = json.loads(decision["source_application_state"])
        target = json.loads(decision["target_application_state"])
        apply_context = {"control_state": control[0], "control_epoch": control[1], "generation": control[2],
                         "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"], "lease_expires_at": lease["expires_at"]}
        descriptor = {"participant": participant, "binding": clone(binding), "apply_context": clone(apply_context),
                      "source_application_state": clone(source), "target_application_state": clone(target)}
        def authorize_apply():
            claim = self.projection_verifier(projection_credential, {**descriptor, "phase": "apply_authorization"})
            now = float(self.clock())
            if (type(claim) is not dict or claim.get("apply_authorized") is not True or
                    claim.get("atomic_source_version_cas") is not True or claim.get("fencing") is not True or
                    canonical(claim.get("apply_context")) != canonical(apply_context) or
                    canonical(claim.get("binding")) != canonical(binding) or
                    "source_application_state" not in claim or "target_application_state" not in claim or
                    canonical(claim["source_application_state"]) != canonical(source) or
                    canonical(claim["target_application_state"]) != canonical(target) or
                    type(claim.get("expires_at")) not in (int, float) or
                    not math.isfinite(claim["expires_at"]) or not math.isfinite(now) or claim["expires_at"] <= now):
                raise OrchestrationError("host did not authorize the external projection write")
        authorize_apply()
        receipt = inspect(clone(binding))
        if receipt is None:
            observe_control_clock(self)
            verified_before_apply = authorizer.verify(credential)
            check_kernel()
            with self._transaction() as connection:
                fresh, fresh_manifest, _, fresh_lease, fresh_binding, fresh_control = read(connection, verified_before_apply)
                if (fresh != decision or fresh_manifest != manifest or fresh_binding != binding or fresh_control != control or
                        fresh_lease["lease_id"] != lease["lease_id"] or fresh_lease["lease_fence"] != lease["lease_fence"]):
                    raise RevisionConflict("external projection decision or lease changed")
                authorize_apply()
            apply(clone(binding), clone(source), clone(target), clone(apply_context))
            receipt = inspect(clone(binding))
        if type(receipt) is not dict or set(receipt) != set(binding) | {"receipt_id"}:
            raise OrchestrationError("durable participant receipt is unknown")
        identifier(receipt["receipt_id"], "receipt_id")
        if len(canonical(receipt).encode("utf-8")) > 65536 or any(canonical(receipt.get(key)) != canonical(value) for key, value in binding.items()):
            raise OrchestrationError("participant receipt binding differs")
        self._failpoint("after_external_projection_commit")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        check_kernel()
        with self._transaction() as connection:
            current, current_manifest, _, current_lease, current_binding, current_control = read(connection, verified)
            if (current != decision or current_manifest != manifest or current_binding != binding or current_control != control or
                    current_lease["lease_id"] != lease["lease_id"] or current_lease["lease_fence"] != lease["lease_fence"]):
                raise RevisionConflict("external projection decision or lease changed")
            authorize_apply()
            claim = self.projection_verifier(projection_credential, {**descriptor, "phase": "receipt"})
            if (type(claim) is not dict or not {"receipt", "source_application_state", "target_application_state"}.issubset(claim) or
                    claim.get("durable") is not True or claim.get("retained") is not True or
                    canonical(claim.get("receipt")) != canonical(receipt) or
                    canonical(claim.get("source_application_state")) != canonical(source) or
                    canonical(claim.get("target_application_state")) != canonical(target)):
                raise OrchestrationError("host did not attest the durable projection commit")
            old = connection.execute("SELECT receipt FROM sdk_external_projection_receipts WHERE operation_id=? AND participant_id=? AND scope_id=?",
                                     (operation_id, participant_id, scope_id)).fetchone()
            if old is not None and old[0] != canonical(receipt):
                raise CommandConflict("projection participant receipt changed")
            if old is None:
                connection.execute("INSERT INTO sdk_external_projection_receipts VALUES(?,?,?,?)", (operation_id, participant_id, scope_id, canonical(receipt)))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            authorizer.check_in_transaction(connection, verified, expected["run_id"], "install_revision", delegation_id)
            return clone(receipt)

    def install_external_projection_receipt(self, operation_id: str, *, participant_id: str,
                                            scope_id: str, credential, lease_credential,
                                            receipt_credential, delegation_id: str | None = None) -> dict:
        """Deliver a stored participant receipt to the Kernel idempotently.

        The host authenticates the durable receipt to the Kernel and serializes
        revocation, external writes and control changes through the lease.
        """
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        for name, value in (("operation_id", operation_id), ("participant_id", participant_id), ("scope_id", scope_id)):
            identifier(value, name)
            if len(value.encode("utf-8")) > 1024:
                raise OrchestrationError("projection participant identity exceeds limit")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authority is required")
        kernel = self.kernel
        identity_reader = getattr(kernel, "kernel_store_identity", None)
        gate_reader = getattr(kernel, "get_run_control", None)
        install = getattr(kernel, "install_projection_receipt", None)
        if not all(callable(item) for item in (identity_reader, gate_reader, install)):
            raise OrchestrationError("Kernel projection participant is unavailable")
        observe_control_clock(self)
        verified = authorizer.verify(credential)

        def read(connection, authority):
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            manifest = connection.execute("SELECT manifest FROM sdk_external_projection_requirements WHERE operation_id=?", (operation_id,)).fetchone()
            stored = connection.execute("SELECT receipt FROM sdk_external_projection_receipts WHERE operation_id=? AND participant_id=? AND scope_id=?", (operation_id, participant_id, scope_id)).fetchone()
            if (operation is None or decision is None or manifest is None or stored is None or
                    decision["kernel_install_receipt"] is None or decision["orchestrator_install_receipt"] is None):
                raise OrchestrationError("installed revision and stored application receipt are required")
            authorizer.check_in_transaction(connection, authority, operation["run_id"], "install_revision", delegation_id)
            declaration = json.loads(decision["decision"])
            kernel_decision = json.loads(decision["kernel_install_receipt"]).get("decision", {})
            if (canonical(declaration.get("participant_requirements")) != manifest[0] or
                    canonical(kernel_decision.get("projection_requirements")) != manifest[0] or
                    kernel_decision.get("decision_id") != operation_id or
                    kernel_decision.get("source_application_projection_version") != declaration.get("source_application_projection_version") or
                    {"participant_id": participant_id, "scope_id": scope_id} not in json.loads(manifest[0])):
                raise RevisionConflict("installed projection requirements changed")
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (operation["run_id"],)).fetchone()
            if (identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]) or
                    not _projection_target_control(connection, operation_id, decision, control)):
                raise RevisionConflict("installed revision control changed")
            expected = {"operation_id": operation_id, "run_id": operation["run_id"], "kernel_store_id": operation["kernel_store_id"],
                        "orchestrator_store_id": operation["orchestrator_store_id"], "orchestrator_incarnation": operation["orchestrator_incarnation"]}
            lease = check_control_lease(self, connection, lease_credential, expected)
            return dict(decision), stored[0], expected, tuple(control), lease

        def check_gate(expected, control):
            if self.kernel is not kernel or identity_reader() != expected["kernel_store_id"]:
                raise RevisionConflict("Kernel projection participant changed")
            gate = gate_reader(expected["run_id"])
            if type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) != control:
                raise RevisionConflict("Kernel projection control changed")

        with self._transaction() as connection:
            decision, stored, expected, control, lease = read(connection, verified)
        check_gate(expected, control)
        receipt = json.loads(stored)
        installed = install(receipt_credential, expected_receipt=receipt)
        if canonical(installed) != stored:
            raise OrchestrationError("Kernel projection receipt differs")
        self._failpoint("after_kernel_projection_receipt")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        check_gate(expected, control)
        with self._transaction() as connection:
            current, current_stored, _, current_control, current_lease = read(connection, verified)
            if (current != decision or current_stored != stored or current_control != control or
                    current_lease["lease_id"] != lease["lease_id"] or current_lease["lease_fence"] != lease["lease_fence"]):
                raise RevisionConflict("projection receipt or control changed")
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            authorizer.check_in_transaction(connection, verified, expected["run_id"], "install_revision", delegation_id)
        return clone(installed)

    def install_cross_store_revision(self, operation_id: str, *, credential,
                                     decision_credential, worker_credential,
                                     delegation_id: str | None = None) -> dict[str, Any]:
        """Install a verified committed decision at the paused Kernel participant.

        This records a participant receipt only. It neither installs the
        Orchestrator projection nor activates or resumes business execution.
        A committed decision without a Kernel receipt is a recoverable partial
        operation: Kernel may already have installed it. A retry requires fresh
        authorization and reconciles the exact immutable participant receipt.
        """
        from .control_authorization import ControlAuthorizer
        identifier(operation_id, "operation_id")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None or decision is None:
                raise OrchestrationError("committed revision decision is required")
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "install_revision", delegation_id)
            requirements_row = connection.execute("SELECT manifest FROM sdk_external_projection_requirements WHERE operation_id=?", (operation_id,)).fetchone()
            declaration = json.loads(decision["decision"])
            requirements = declaration.get("participant_requirements")
            if ((requirements_row is None) != (requirements is None) or
                    (requirements_row is not None and requirements_row[0] != canonical(requirements))):
                raise RevisionConflict("projection participant requirements are missing or changed")
            if decision["kernel_install_receipt"] is not None:
                return dict(decision)
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?",
                                         (operation["run_id"],)).fetchone()
            if (control is None or tuple(control) != ("paused", decision["source_epoch"], decision["source_generation"])
                    or operation["orchestrator_pause_receipt"] is None):
                raise RevisionConflict("revision source control changed")
        declaration = json.loads(decision["decision"])
        streamed = declaration.get("stream_version") == 1
        envelope = {"decision_id": operation_id, "operation_id": operation_id,
                    "barrier_operation_id": operation_id, "run_id": operation["run_id"],
                    "orchestrator_store_id": operation["orchestrator_store_id"],
                    "orchestrator_incarnation": operation["orchestrator_incarnation"],
                    "kernel_store_id": operation["kernel_store_id"],
                    "source_revision": decision["source_revision"],
                    "source_generation": decision["source_generation"],
                    "source_control_epoch": decision["source_epoch"],
                    "target_generation": decision["target_generation"],
                    "deployment": json.loads(decision["deployment"]),
                    "revision": declaration["revision"],
                    "source_application_state": None if streamed else json.loads(decision["source_application_state"]),
                    "target_application_state": None if streamed else json.loads(decision["target_application_state"]),
                    "content_pages": declaration["content_pages"] if streamed else {},
                    "migration_version": decision["migration_version"],
                    "application_projection_version": decision["application_projection_version"]}
        if requirements is not None:
            envelope["projection_requirements"] = requirements
            envelope["source_application_projection_version"] = declaration["source_application_projection_version"]
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        installer = getattr(participant, "install_revision_decision", None)
        if not callable(identity_reader) or identity_reader() != operation["kernel_store_id"] or not callable(installer):
            raise OrchestrationError("identified Kernel revision participant is required")
        receipt = installer(decision_credential, worker_credential=worker_credential,
                            expected_decision=envelope)
        barrier = json.loads(operation["kernel_receipt"])
        if (type(receipt) is not dict or receipt.get("kind") != "paused_revision_install" or
                type(receipt.get("decision")) is not dict or canonical(receipt["decision"]) != canonical(envelope) or receipt.get("activation") != "closed" or
                receipt.get("target_control_epoch") != decision["source_epoch"] + 1 or
                (receipt.get("claims_used"), receipt.get("max_claims"), receipt.get("deadline_at")) !=
                (barrier.get("claims_used"), operation["max_claims"], operation["deadline_at"])):
            raise OrchestrationError("Kernel revision receipt differs from the committed decision or budget")
        if len(canonical(receipt).encode("utf-8")) > 1024 * 1024:
            raise OrchestrationError("Kernel revision receipt exceeds the size limit")
        self._failpoint("after_kernel_revision_install")
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "install_revision", delegation_id)
            current = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?",
                                         (operation["run_id"],)).fetchone()
            if current is None or self.kernel is not participant or current["decision"] != decision["decision"]:
                raise RevisionConflict("revision decision or Kernel participant changed")
            if control is None or tuple(control) != ("paused", decision["source_epoch"], decision["source_generation"]):
                raise RevisionConflict("revision source control changed after Kernel installation")
            if current["kernel_install_receipt"] is not None and current["kernel_install_receipt"] != canonical(receipt):
                raise OrchestrationError("Kernel revision receipt changed on replay")
            connection.execute("UPDATE sdk_revision_decisions SET kernel_install_receipt=? WHERE operation_id=?",
                               (canonical(receipt), operation_id))
            return dict(connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone())

    def fence_cross_store_cancellation(self, run_id: str, *, operation_id: str,
                                       credential, lease_credential,
                                       delegation_id: str | None = None) -> dict[str, Any]:
        """Fence new admission in both stores; business cancellation is separate."""
        from ..execution_kernel import CASConflictError
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        identifier(run_id, "run_id")
        identifier(operation_id, "operation_id")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        participant = self.kernel
        identity_reader, reader, fence = (getattr(participant, "kernel_store_identity", None),
                                          getattr(participant, "get_run_control", None),
                                          getattr(participant, "fence_cancelled_run", None))
        if not all(callable(method) for method in (identity_reader, reader, fence)):
            raise OrchestrationError("Kernel cancellation participant is required")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        gate = reader(run_id)
        kernel_id = identity_reader()
        if type(gate) is not dict or type(gate.get("control_epoch")) is not int or type(gate.get("generation")) is not int:
            raise OrchestrationError("Kernel cancellation source is unknown")
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, run_id, "cancel", delegation_id)
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            if identity is None or control is None or control["generation"] != gate["generation"]:
                raise RevisionConflict("cancellation source is unknown or changed")
            expected = {"operation_id": operation_id, "run_id": run_id, "kernel_store_id": kernel_id,
                        "orchestrator_store_id": identity[0], "orchestrator_incarnation": identity[1]}
            lease = check_control_lease(self, connection, lease_credential, expected)
            record = connection.execute("SELECT * FROM sdk_cancellation_fences WHERE operation_id=?", (operation_id,)).fetchone()
            if record is None:
                now = float(self.clock())
                connection.execute("INSERT INTO sdk_cancellation_fences VALUES(?,?,?,?,?,?,?,NULL,NULL,?)",
                    (operation_id, run_id, control["generation"], kernel_id, identity[0], identity[1], gate["control_epoch"], now))
                kernel_epoch = gate["control_epoch"]
            else:
                if (record["run_id"], record["generation"], record["kernel_store_id"], record["orchestrator_store_id"], record["orchestrator_incarnation"]) != (run_id, control["generation"], kernel_id, identity[0], identity[1]):
                    raise CommandConflict("cancellation operation differs")
                kernel_epoch = record["kernel_epoch"]
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
        for attempt in range(3):
            try:
                receipt = fence(operation_id, run_id, expected_epoch=kernel_epoch, generation=gate["generation"])
                break
            except CASConflictError:
                if attempt == 2:
                    raise
                latest = reader(run_id)
                if type(latest) is not dict or latest.get("generation") != gate["generation"] or type(latest.get("control_epoch")) is not int:
                    raise OrchestrationError("Kernel cancellation epoch is unknown")
                observe_control_clock(self)
                verified = authorizer.verify(credential)
                with self._transaction() as connection:
                    authorizer.check_in_transaction(connection, verified, run_id, "cancel", delegation_id)
                    check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
                    connection.execute("UPDATE sdk_cancellation_fences SET kernel_epoch=? WHERE operation_id=? AND kernel_receipt IS NULL", (latest["control_epoch"], operation_id))
                    kernel_epoch = latest["control_epoch"]
        if (type(receipt) is not dict or (receipt.get("kind"), receipt.get("operation_id"), receipt.get("run_id"),
                receipt.get("generation"), receipt.get("expected_epoch"), receipt.get("control_epoch"), receipt.get("store_id")) !=
                ("cancellation_fence", operation_id, run_id, gate["generation"], kernel_epoch, kernel_epoch + 1, kernel_id)):
            raise OrchestrationError("Kernel cancellation receipt differs")
        self._failpoint("after_kernel_cancellation_fence")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, run_id, "cancel", delegation_id)
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            record = connection.execute("SELECT * FROM sdk_cancellation_fences WHERE operation_id=?", (operation_id,)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            if (record is None or record["kernel_epoch"] != kernel_epoch or self.kernel is not participant or identity_reader() != kernel_id or
                    identity is None or tuple(identity) != (expected["orchestrator_store_id"], expected["orchestrator_incarnation"]) or
                    control is None or control["control_state"] not in ("paused", "active", "pausing") or control["generation"] != gate["generation"] or
                    control["control_epoch"] > receipt["control_epoch"]):
                raise RevisionConflict("cancellation participant or gate changed")
            if record["orchestrator_receipt"] is not None:
                try:
                    local = json.loads(record["orchestrator_receipt"])
                    expected_local = {"operation_id": operation_id, "run_id": run_id, "state": "admission_fenced",
                                      "generation": gate["generation"], "control_epoch": receipt["control_epoch"],
                                      "committed_at": local["committed_at"]}
                except (TypeError, ValueError, KeyError):
                    raise CommandConflict("cancellation receipt differs") from None
                if (record["kernel_receipt"] != canonical(receipt) or
                        type(local) is not dict or canonical(local) != canonical(expected_local) or
                        type(local["committed_at"]) not in (float, int) or
                        not math.isfinite(local["committed_at"]) or
                        tuple(control) != ("paused", receipt["control_epoch"], gate["generation"])):
                    raise CommandConflict("cancellation receipt differs")
                return dict(record)
            now = float(self.clock())
            if control["control_epoch"] < receipt["control_epoch"]:
                connection.execute("UPDATE sdk_managed_runs SET control_state='paused',control_epoch=?,updated_at=? WHERE run_id=?", (receipt["control_epoch"], now, run_id))
                connection.execute("INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)", (run_id, receipt["control_epoch"], "paused", gate["generation"], "[]", None, now))
            elif control["control_state"] != "paused":
                raise RevisionConflict("cancellation epoch does not advance local control")
            local = {"operation_id": operation_id, "run_id": run_id, "state": "admission_fenced",
                     "generation": gate["generation"], "control_epoch": receipt["control_epoch"], "committed_at": now}
            connection.execute("UPDATE sdk_cancellation_fences SET kernel_receipt=?,orchestrator_receipt=? WHERE operation_id=?", (canonical(receipt), canonical(local), operation_id))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            return dict(connection.execute("SELECT * FROM sdk_cancellation_fences WHERE operation_id=?", (operation_id,)).fetchone())

    def apply_fenced_cancellation(self, fence_operation_id: str, *, operation_id: str,
                                  expected_revision: int, operations: list,
                                  credential, lease_credential, delegation_id: str | None = None) -> dict:
        """Persist host-selected cancellation steps after both admission fences.

        Cancellation intents are delivered separately; a finish step succeeds only
        after the existing reducer sees settled tasks and released waits.
        """
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        identifier(fence_operation_id, "fence_operation_id")
        identifier(operation_id, "operation_id")
        integer(expected_revision, "expected_revision")
        if type(operations) is not list or not 1 <= len(operations) <= 128:
            raise OrchestrationError("cancellation requires 1 to 128 explicit operations")
        values = [validate_operation(op) for op in operations]
        if any(op["kind"] not in ("cancel", "release_wait", "finish") or
               (op["kind"] == "finish" and op["state"] != "cancelled") for op in values):
            raise OrchestrationError("operation is not a cancellation step")
        request = canonical({"expected_revision": expected_revision, "operations": values})
        if len(request.encode("utf-8")) > 65536:
            raise OrchestrationError("cancellation action exceeds bounded limit")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        participant = self.kernel
        identity_reader, reader = getattr(participant, "kernel_store_identity", None), getattr(participant, "get_run_control", None)
        if not callable(identity_reader) or not callable(reader):
            raise OrchestrationError("Kernel cancellation participant is required")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            fence = connection.execute("SELECT * FROM sdk_cancellation_fences WHERE operation_id=?", (fence_operation_id,)).fetchone()
            if fence is None or fence["kernel_receipt"] is None or fence["orchestrator_receipt"] is None:
                raise OrchestrationError("completed cancellation admission fence is required")
            run_id = fence["run_id"]
            authorizer.check_in_transaction(connection, verified, run_id, "cancel", delegation_id)
            expected = {"operation_id": fence_operation_id, "run_id": run_id, "kernel_store_id": fence["kernel_store_id"],
                        "orchestrator_store_id": fence["orchestrator_store_id"], "orchestrator_incarnation": fence["orchestrator_incarnation"]}
            lease = check_control_lease(self, connection, lease_credential, expected)
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            kernel_receipt = json.loads(fence["kernel_receipt"])
            local_receipt = json.loads(fence["orchestrator_receipt"])
            gate = reader(run_id)
            if (identity is None or tuple(identity) != (fence["orchestrator_store_id"], fence["orchestrator_incarnation"]) or
                    self.kernel is not participant or identity_reader() != fence["kernel_store_id"] or
                    (kernel_receipt.get("kind"), kernel_receipt.get("operation_id"), kernel_receipt.get("run_id"), kernel_receipt.get("store_id"), kernel_receipt.get("generation")) !=
                    ("cancellation_fence", fence_operation_id, run_id, fence["kernel_store_id"], fence["generation"]) or
                    (local_receipt.get("operation_id"), local_receipt.get("run_id"), local_receipt.get("state"), local_receipt.get("generation"), local_receipt.get("control_epoch")) !=
                    (fence_operation_id, run_id, "admission_fenced", fence["generation"], kernel_receipt["control_epoch"]) or
                    control is None or tuple(control) != ("paused", kernel_receipt["control_epoch"], fence["generation"]) or
                    type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) != tuple(control)):
                raise RevisionConflict("cancellation fence is no longer current")
            old = connection.execute("SELECT * FROM sdk_cancellation_actions WHERE operation_id=?", (operation_id,)).fetchone()
            if old is not None:
                if old["fence_operation_id"] != fence_operation_id or old["request"] != request:
                    raise CommandConflict("cancellation action differs")
                check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
                return json.loads(old["receipt"])
            if connection.execute("SELECT 1 FROM sdk_outbox WHERE run_id=? AND command_id=? LIMIT 1", (run_id, operation_id)).fetchone():
                raise CommandConflict("cancellation action identity is already in use")
            run = connection.execute("SELECT revision,state FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise OrchestrationError("unknown run")
            # Do not materialize application state, signals, or unlimited history
            # for a cancellation decision. Oversized task graphs remain pending.
            sizes = connection.execute("SELECT length(CAST(value AS BLOB)) FROM sdk_run_items "
                "WHERE run_id=? AND section IN ('task','attempt','waits') LIMIT 4097", (run_id,)).fetchall()
            if len(sizes) > 4096 or any(size[0] > 262144 for size in sizes) or sum(size[0] for size in sizes) > 8388608:
                raise OrchestrationError("cancellation graph exceeds bounded read limit")
            rows = connection.execute("SELECT section,item_key,value FROM sdk_run_items "
                "WHERE run_id=? AND section IN ('task','attempt','waits')", (run_id,)).fetchall()
            state = self._inflate(connection, run_id, run["revision"], rows)
            state["state"] = run["state"]
            state["generation"] = fence["generation"]
            if state["revision"] != expected_revision:
                raise RevisionConflict("run revision changed")
            intents, changes = [], set()
            for op in values:
                intents.extend(reduce_operation(state, op))
                if "task_id" in op:
                    task = state["tasks"][op["task_id"]]
                    changes.add(("attempt", canonical([op["task_id"], len(task["attempts"])-1])))
                elif "wait_id" in op:
                    changes.add(("waits", op["wait_id"]))
            for ordinal, intent in enumerate(intents):
                intent["generation"] = fence["generation"]
                connection.execute("INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) VALUES(?,?,?,?)",
                                   (run_id, operation_id, ordinal, canonical(intent)))
            state["revision"] += 1
            self._save(connection, state, changes=changes)
            receipt = {"operation_id": operation_id, "fence_operation_id": fence_operation_id,
                       "run_id": run_id, "revision": state["revision"], "state": state["state"],
                       "pending_intents": len(intents)}
            connection.execute("INSERT INTO sdk_cancellation_actions VALUES(?,?,?,?,?)",
                               (operation_id, fence_operation_id, request, canonical(receipt), float(self.clock())))
            self._event(connection, state, "managed.cancellation", {"operation_id": operation_id, "operations": values})
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
        self._failpoint("after_fenced_cancellation_action")
        return receipt

    def reconcile_fenced_cancellation(self, fence_operation_id: str, *, action_operation_id: str,
                                      ordinal: int, receipt_operation_id: str, credential,
                                      lease_credential, delegation_id: str | None = None) -> dict:
        """Record a locally absent execution as cancelled under a Kernel fence.

        This establishes only participant-local absence. The host must retain
        writer isolation and reconcile any other participant or legacy sender.
        """
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        for label, value in (("fence_operation_id", fence_operation_id), ("action_operation_id", action_operation_id),
                             ("receipt_operation_id", receipt_operation_id)):
            identifier(value, label)
        integer(ordinal, "ordinal")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        cancel = getattr(participant, "cancel_fenced_before_accept", None)
        if not callable(identity_reader) or not callable(cancel):
            raise OrchestrationError("fenced cancellation participant is required")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            fence = connection.execute("SELECT * FROM sdk_cancellation_fences WHERE operation_id=? AND length(CAST(kernel_receipt AS BLOB))<=1048576 AND length(CAST(orchestrator_receipt AS BLOB))<=65536", (fence_operation_id,)).fetchone()
            action = connection.execute("SELECT * FROM sdk_cancellation_actions WHERE operation_id=? AND length(CAST(request AS BLOB))<=65536 AND length(CAST(receipt AS BLOB))<=65536", (action_operation_id,)).fetchone()
            if fence is None or action is None or action["fence_operation_id"] != fence_operation_id or fence["kernel_receipt"] is None or fence["orchestrator_receipt"] is None:
                raise OrchestrationError("completed cancellation action and fence are required")
            run_id = fence["run_id"]
            authorizer.check_in_transaction(connection, verified, run_id, "cancel", delegation_id)
            expected = {"operation_id": fence_operation_id, "run_id": run_id, "kernel_store_id": fence["kernel_store_id"],
                        "orchestrator_store_id": fence["orchestrator_store_id"], "orchestrator_incarnation": fence["orchestrator_incarnation"]}
            lease = check_control_lease(self, connection, lease_credential, expected)
            row = connection.execute("SELECT sequence,CASE WHEN length(CAST(payload AS BLOB))<=65536 THEN payload END AS payload FROM sdk_outbox WHERE run_id=? AND command_id=? AND ordinal=?", (run_id, action_operation_id, ordinal)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            kr = json.loads(fence["kernel_receipt"])
            if (row is None or row["payload"] is None or identity is None or tuple(identity) != (fence["orchestrator_store_id"], fence["orchestrator_incarnation"]) or
                    self.kernel is not participant or identity_reader() != fence["kernel_store_id"] or control is None or
                    tuple(control) != ("paused", kr["control_epoch"], fence["generation"])):
                raise RevisionConflict("cancellation fence or outbox changed")
            intent = json.loads(row["payload"])
            if intent.get("kind") != "cancel" or intent.get("generation") != fence["generation"]:
                raise OrchestrationError("outbox item is not the fenced cancellation")
            conflict = connection.execute("SELECT 1 FROM sdk_dispatch_permits WHERE run_id=? AND execution_id=? AND (kernel_store_id!=? OR generation!=?) LIMIT 1",
                (run_id, intent["execution_id"], fence["kernel_store_id"], fence["generation"])).fetchone()
            if conflict:
                raise OrchestrationError("dispatch participant or generation is unknown")
            command = self._delivery_command(intent, max_bytes=65536)
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
        receipt = cancel(command, run_id=run_id, generation=fence["generation"], fence_operation_id=fence_operation_id,
                         receipt_operation_id=receipt_operation_id, reason=intent["reason"])
        if (type(receipt) is not dict or (receipt.get("kind"), receipt.get("operation_id"), receipt.get("fence_operation_id"), receipt.get("run_id"), receipt.get("generation"), receipt.get("execution_id"), receipt.get("store_id"), receipt.get("control_epoch"), receipt.get("reason")) !=
                ("cancelled_before_accept", receipt_operation_id, fence_operation_id, run_id, fence["generation"], intent["execution_id"], fence["kernel_store_id"], kr["control_epoch"], intent["reason"])):
            raise OrchestrationError("Kernel cancellation receipt differs")
        self._failpoint("after_kernel_fenced_cancellation")
        receipt_reader = getattr(participant, "managed_execution_receipt", None)
        if not callable(receipt_reader):
            raise OrchestrationError("exact Kernel execution receipt is required")
        snapshot = receipt_reader(command, run_id=run_id, generation=fence["generation"], max_bytes=262144)
        self._check_delivery_snapshot(snapshot, command)
        if snapshot.state != "cancelled":
            raise OrchestrationError("Kernel cancelled execution is unknown")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, run_id, "cancel", delegation_id)
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            current = connection.execute("SELECT CASE WHEN length(CAST(payload AS BLOB))<=65536 THEN payload END FROM sdk_outbox WHERE sequence=?", (row["sequence"],)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            current_fence = connection.execute("SELECT kernel_receipt,orchestrator_receipt FROM sdk_cancellation_fences WHERE operation_id=? AND length(CAST(kernel_receipt AS BLOB))<=1048576 AND length(CAST(orchestrator_receipt AS BLOB))<=65536", (fence_operation_id,)).fetchone()
            current_action = connection.execute("SELECT fence_operation_id,request,receipt FROM sdk_cancellation_actions WHERE operation_id=? AND length(CAST(request AS BLOB))<=65536 AND length(CAST(receipt AS BLOB))<=65536", (action_operation_id,)).fetchone()
            conflict = connection.execute("SELECT 1 FROM sdk_dispatch_permits WHERE run_id=? AND execution_id=? AND (kernel_store_id!=? OR generation!=?) LIMIT 1", (run_id, intent["execution_id"], fence["kernel_store_id"], fence["generation"])).fetchone()
            if (current is None or current[0] != row["payload"] or identity is None or tuple(identity) != (fence["orchestrator_store_id"], fence["orchestrator_incarnation"]) or self.kernel is not participant or identity_reader() != fence["kernel_store_id"] or
                    current_fence is None or tuple(current_fence) != (fence["kernel_receipt"], fence["orchestrator_receipt"]) or
                    current_action is None or tuple(current_action) != (fence_operation_id, action["request"], action["receipt"]) or
                    conflict is not None or
                    control is None or tuple(control) != ("paused", kr["control_epoch"], fence["generation"])):
                raise RevisionConflict("cancellation reconciliation changed")
            execution = connection.execute("SELECT task_id,attempt,CASE WHEN length(CAST(command AS BLOB))<=65536 THEN command END AS command FROM sdk_executions WHERE run_id=? AND execution_id=?", (run_id, intent["execution_id"])).fetchone()
            if execution is None or execution["command"] != canonical(command.to_dict()):
                raise RevisionConflict("registered execution differs")
            item_key = canonical([execution["task_id"], execution["attempt"]])
            stored = connection.execute("SELECT CASE WHEN length(CAST(value AS BLOB))<=262144 THEN value END FROM sdk_run_items WHERE run_id=? AND section='attempt' AND item_key=?", (run_id, item_key)).fetchone()
            run = connection.execute("SELECT revision,state FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
            if stored is None or stored[0] is None or run is None:
                raise OrchestrationError("bounded cancellation attempt is unavailable")
            attempt = json.loads(stored[0])
            snap = snapshot.to_dict()
            if not attempt["dispatched"] or attempt["kernel_revision"] > snapshot.revision:
                raise RevisionConflict("cancellation attempt changed")
            if attempt["kernel_revision"] == snapshot.revision:
                if canonical(attempt["kernel_snapshot"]) != canonical(snap):
                    raise RevisionConflict("cancellation snapshot differs")
            else:
                if attempt["kernel_revision"] and attempt["state"] in TERMINAL:
                    raise RevisionConflict("terminal attempt cannot be rewritten")
                attempt.update(state=snapshot.state, kernel_revision=snapshot.revision,
                               result=snapshot.result.to_dict() if snapshot.result else None, kernel_snapshot=snap)
                revision = run["revision"] + 1
                encoded = canonical(attempt)
                if len(encoded.encode("utf-8")) > 262144:
                    raise OrchestrationError("cancellation attempt exceeds bounded limit")
                connection.execute("UPDATE sdk_runs SET revision=? WHERE run_id=?", (revision, run_id))
                connection.execute("INSERT INTO sdk_run_revisions VALUES(?,?)", (run_id, revision))
                connection.execute("INSERT INTO sdk_retention_times VALUES('revision',?,(julianday('now')-2440587.5)*86400.0)", (canonical([run_id, revision]),))
                connection.execute("UPDATE sdk_run_items SET value=? WHERE run_id=? AND section='attempt' AND item_key=?", (encoded, run_id, item_key))
                connection.execute("INSERT INTO sdk_run_history VALUES(?,'attempt',?,?,?)", (run_id, item_key, revision, encoded))
                connection.execute("UPDATE sdk_executions SET active=0 WHERE execution_id=?", (intent["execution_id"],))
                self._event(connection, {"run_id": run_id, "revision": revision, "generation": fence["generation"]}, "execution.observed", {"task_id": execution["task_id"], "attempt": execution["attempt"], "execution_id": intent["execution_id"], "snapshot": snap})
            connection.execute("UPDATE sdk_outbox SET delivered=1,attempts=attempts+1,last_error=NULL,last_attempt_at=? WHERE sequence=? AND delivered=0", (float(self.clock()), row["sequence"]))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
        return {"kernel_receipt": receipt, "run_projection": "cancelled"}

    def install_cross_store_budget_policy(self, operation_id: str, *, policy: dict, credential,
                                          lease_credential, policy_credential,
                                          delegation_id: str | None = None) -> dict:
        """Bind the host-attested budget policy to an installed paused revision.

        The host serializes policy changes and admission against this lease.
        A lost Kernel acknowledgement leaves a recoverable paused partial install.
        """
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        identifier(operation_id, "operation_id")
        if type(policy) is not dict or set(policy) != {"policy_id", "decision_id", "run_id", "generation", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation", "scopes"}:
            raise OrchestrationError("invalid application budget policy")
        policy = clone(policy)
        if len(canonical(policy).encode("utf-8")) > 65536:
            raise OrchestrationError("application budget policy exceeds limit")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        participant = self.kernel
        install, inspect = getattr(participant, "install_budget_policy", None), getattr(participant, "inspect_budget_policy", None)
        identity_reader = getattr(participant, "kernel_store_identity", None)
        if not callable(install) or not callable(inspect) or not callable(identity_reader):
            raise OrchestrationError("Kernel budget participant is unavailable")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            if operation is None or decision is None or decision["kernel_install_receipt"] is None or decision["orchestrator_install_receipt"] is None:
                raise OrchestrationError("both installed revision receipts are required")
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "install_revision", delegation_id)
            expected = {"operation_id": operation_id, "run_id": operation["run_id"], "kernel_store_id": operation["kernel_store_id"],
                        "orchestrator_store_id": operation["orchestrator_store_id"], "orchestrator_incarnation": operation["orchestrator_incarnation"]}
            if (policy["decision_id"], policy["run_id"], policy["generation"], policy["kernel_store_id"], policy["orchestrator_store_id"], policy["orchestrator_incarnation"]) != (
                    operation_id, operation["run_id"], decision["target_generation"], operation["kernel_store_id"], operation["orchestrator_store_id"], operation["orchestrator_incarnation"]):
                raise OrchestrationError("budget policy revision binding differs")
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (operation["run_id"],)).fetchone()
            if (identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]) or
                    identity_reader() != operation["kernel_store_id"] or control is None or
                    tuple(control) != ("paused", decision["source_epoch"] + 1, decision["target_generation"])):
                raise RevisionConflict("budget policy participant or control changed")
            lease = check_control_lease(self, connection, lease_credential, expected)
            existing = connection.execute("SELECT policy FROM sdk_revision_budget_policies WHERE operation_id=?", (operation_id,)).fetchone()
            if existing is not None and existing[0] != canonical(policy):
                raise CommandConflict("budget policy differs")
        receipt = install(policy_credential, expected_policy=policy)
        if canonical(receipt) != canonical(policy):
            raise OrchestrationError("Kernel budget policy receipt differs")
        self._failpoint("after_kernel_budget_policy")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "install_revision", delegation_id)
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            current = connection.execute("SELECT kernel_install_receipt,orchestrator_install_receipt FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            current_operation = connection.execute("SELECT run_id,kernel_store_id,orchestrator_store_id,orchestrator_incarnation FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (operation["run_id"],)).fetchone()
            if (self.kernel is not participant or identity_reader() != operation["kernel_store_id"] or identity is None or
                    tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]) or
                    current_operation is None or tuple(current_operation) != (operation["run_id"], operation["kernel_store_id"], operation["orchestrator_store_id"], operation["orchestrator_incarnation"]) or
                    current is None or tuple(current) != (decision["kernel_install_receipt"], decision["orchestrator_install_receipt"]) or
                    control is None or tuple(control) != ("paused", decision["source_epoch"] + 1, decision["target_generation"]) or
                    canonical(inspect(operation["run_id"], decision["target_generation"])) != canonical(policy)):
                raise RevisionConflict("budget policy participant or revision changed")
            old = connection.execute("SELECT policy,kernel_receipt FROM sdk_revision_budget_policies WHERE operation_id=?", (operation_id,)).fetchone()
            if old is not None and tuple(old) != (canonical(policy), canonical(receipt)):
                raise CommandConflict("budget policy receipt differs")
            final_lease = check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "install_revision", delegation_id)
            if old is None:
                connection.execute("INSERT INTO sdk_revision_budget_policies VALUES(?,?,?)", (operation_id, canonical(policy), canonical(receipt)))
            now = float(self.clock())
            if not math.isfinite(now) or final_lease["expires_at"] <= now:
                raise OrchestrationError("host exclusive control lease expired before commit")
            connection.execute("UPDATE sdk_control_authority_clock SET observed_at=MAX(observed_at,?) WHERE singleton=1", (now,))
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "install_revision", delegation_id)
            return {"operation_id": operation_id, "policy": policy, "kernel_receipt": receipt}

    def takeover_cross_store_control_lease(self, operation_id: str, *, phase: str, takeover_id: str,
                                           credential, lease_credential, inspection_credential,
                                           takeover_credential, delegation_id: str | None = None) -> dict:
        """Transfer a partial activation or resume to a host-excluded new lease.

        The host must exclude the old holder and close business admission until
        the takeover and the final Orchestrator resume receipt both commit.
        A lost Kernel acknowledgement is replayed from the durable intent.
        """
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        for name, value in (("operation_id", operation_id), ("takeover_id", takeover_id)):
            identifier(value, name)
            if len(value.encode("utf-8")) > 1024:
                raise OrchestrationError("control takeover identity exceeds limit")
        if phase not in ("activation", "resume"):
            raise OrchestrationError("invalid control takeover phase")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authority is required")
        kernel = self.kernel
        identity_reader, gate_reader = getattr(kernel, "kernel_store_identity", None), getattr(kernel, "get_run_control", None)
        inspect = getattr(kernel, "inspect_control_participant_receipt", None)
        inspect_takeover = getattr(kernel, "inspect_control_takeover", None)
        take = getattr(kernel, "takeover_control_lease", None)
        if not all(callable(value) for value in (identity_reader, gate_reader, inspect, inspect_takeover, take)):
            raise OrchestrationError("Kernel control takeover participant is unavailable")
        observe_control_clock(self)
        verified = authorizer.verify(credential)

        def read(connection, authority):
            table = "sdk_revision_activations" if phase == "activation" else "sdk_revision_resumes"
            entry = connection.execute(f"SELECT * FROM {table} WHERE operation_id=?", (operation_id,)).fetchone()
            if entry is None:
                raise OrchestrationError("durable original control intent is required")
            decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (entry["decision_id"],)).fetchone()
            source = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (entry["decision_id"],)).fetchone()
            if decision is None or source is None or decision["kernel_install_receipt"] is None or decision["orchestrator_install_receipt"] is None:
                raise OrchestrationError("installed revision decision is required")
            action = "activate_revision" if phase == "activation" else "resume"
            budget = connection.execute("SELECT policy,kernel_receipt FROM sdk_revision_budget_policies WHERE operation_id=?", (entry["decision_id"],)).fetchone()
            if phase == "resume" or budget is not None:
                budget_reader = getattr(kernel, "inspect_budget_policy", None)
                if (budget is None or budget[0] != budget[1] or not callable(budget_reader) or
                        canonical(budget_reader(source["run_id"], decision["target_generation"])) != budget[0]):
                    raise RevisionConflict("control takeover budget policy changed")
            authorizer.check_in_transaction(connection, authority, source["run_id"], action, delegation_id)
            if phase == "resume" and entry["orchestrator_receipt"] is not None:
                raise OrchestrationError("completed resume does not require takeover")
            if connection.execute("SELECT 1 FROM sdk_cancellation_fences WHERE run_id=? LIMIT 1", (source["run_id"],)).fetchone():
                raise RevisionConflict("cancelled Run cannot transfer control")
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (source["run_id"],)).fetchone()
            original = json.loads(entry["envelope"])
            if (identity is None or tuple(identity) != (source["orchestrator_store_id"], source["orchestrator_incarnation"]) or
                    control is None or tuple(control) != ("paused", decision["source_epoch"] + 1, decision["target_generation"]) or
                    original.get("decision_id") != entry["decision_id"] or original.get("operation_id") != operation_id or
                    original.get("kernel_install_receipt") != json.loads(decision["kernel_install_receipt"]) or
                    original.get("orchestrator_install_receipt") != json.loads(decision["orchestrator_install_receipt"])):
                raise RevisionConflict("control takeover revision or local gate changed")
            expected = {"operation_id": operation_id, "run_id": source["run_id"], "kernel_store_id": source["kernel_store_id"],
                        "orchestrator_store_id": source["orchestrator_store_id"], "orchestrator_incarnation": source["orchestrator_incarnation"]}
            lease = check_control_lease(self, connection, lease_credential, expected)
            latest = connection.execute("SELECT * FROM sdk_control_lease_takeovers WHERE operation_id=? AND resolution IS NULL ORDER BY new_fence DESC LIMIT 1", (operation_id,)).fetchone()
            previous = (original["lease_id"], original["lease_fence"])
            pending = None
            if latest is not None:
                item = json.loads(latest["claim"])
                if item["phase"] != phase:
                    raise CommandConflict("takeover phase differs")
                if latest["kernel_receipt"] is None:
                    pending = item
                    previous = (item["previous_lease_id"], item["previous_fence"])
                else:
                    previous = (item["new_lease_id"], item["new_fence"])
                    if latest["takeover_id"] == takeover_id:
                        pending = item
                        previous = (item["previous_lease_id"], item["previous_fence"])
            other = connection.execute("SELECT operation_id FROM sdk_control_lease_takeovers WHERE takeover_id=?", (takeover_id,)).fetchone()
            if other is not None and other[0] != operation_id:
                raise CommandConflict("takeover identity belongs to another operation")
            if lease["lease_fence"] <= previous[1] or (pending is not None and
                    (lease["lease_fence"] < pending["new_fence"] or
                     (lease["lease_fence"] == pending["new_fence"] and lease["lease_id"] != pending["new_lease_id"]))):
                raise RevisionConflict("new takeover lease differs or is not newer")
            return dict(entry), dict(decision), dict(source), expected, lease, original, previous, pending

        with self._transaction() as connection:
            entry, decision, source, expected, lease, original, previous, pending = read(connection, verified)
        if self.kernel is not kernel or identity_reader() != expected["kernel_store_id"]:
            raise RevisionConflict("Kernel control participant changed")
        if pending is not None:
            takeover_inspection = {"original_takeover": pending, "current_lease_id": lease["lease_id"],
                                   "current_lease_fence": lease["lease_fence"], "current_lease_expires_at": lease["expires_at"],
                                   "lease_held": True, "old_holder_excluded": True}
            observed_takeover = inspect_takeover(inspection_credential, expected_inspection=takeover_inspection)
            if (observed_takeover is not None and (type(observed_takeover) is not dict or
                    observed_takeover.get("kind") != "control_lease_takeover" or
                    canonical(observed_takeover.get("claim")) != canonical(pending))):
                raise RevisionConflict("inspected control takeover differs")
            observe_control_clock(self)
            verified = authorizer.verify(credential)
            with self._transaction() as connection:
                fresh = read(connection, verified)
                if fresh[7] != pending:
                    raise RevisionConflict("pending takeover changed during inspection")
                prior_row = connection.execute("SELECT kernel_receipt,resolution FROM sdk_control_lease_takeovers WHERE takeover_id=?", (pending["takeover_id"],)).fetchone()
                if prior_row is None or prior_row[1] is not None or (prior_row[0] is not None and
                        (observed_takeover is None or prior_row[0] != canonical(observed_takeover))):
                    raise RevisionConflict("recorded takeover evidence changed")
                if observed_takeover is None:
                    resolution = canonical({"kind": "confirmed_absent", "inspection": takeover_inspection, "observed_at": float(self.clock())})
                    connection.execute("UPDATE sdk_control_lease_takeovers SET resolution=? WHERE takeover_id=? AND kernel_receipt IS NULL AND resolution IS NULL", (resolution, pending["takeover_id"]))
                else:
                    connection.execute("UPDATE sdk_control_lease_takeovers SET kernel_receipt=? WHERE takeover_id=? AND kernel_receipt IS NULL AND resolution IS NULL", (canonical(observed_takeover), pending["takeover_id"]))
                check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
                authorizer.check_in_transaction(connection, verified, source["run_id"], "activate_revision" if phase == "activation" else "resume", delegation_id)
            if observed_takeover is not None and (lease["lease_id"], lease["lease_fence"]) == (pending["new_lease_id"], pending["new_fence"]):
                return observed_takeover
            retry_id = takeover_id
            with self._transaction() as connection:
                if connection.execute("SELECT 1 FROM sdk_control_lease_takeovers WHERE takeover_id=?", (retry_id,)).fetchone():
                    ordinal = connection.execute("SELECT COUNT(*) FROM sdk_control_lease_takeovers WHERE operation_id=?", (operation_id,)).fetchone()[0]
                    retry_id = takeover_id + ":retry:" + str(lease["lease_fence"]) + ":" + str(ordinal)
                    while connection.execute("SELECT 1 FROM sdk_control_lease_takeovers WHERE takeover_id=?", (retry_id,)).fetchone():
                        ordinal += 1
                        retry_id = takeover_id + ":retry:" + str(lease["lease_fence"]) + ":" + str(ordinal)
            return self.takeover_cross_store_control_lease(operation_id, phase=phase, takeover_id=retry_id, credential=credential,
                lease_credential=lease_credential, inspection_credential=inspection_credential,
                takeover_credential=takeover_credential, delegation_id=delegation_id)
        if pending is None:
            inspection = {**expected, "phase": phase, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"],
                          "lease_expires_at": lease["expires_at"], "lease_held": True}
            observed = inspect(inspection_credential, expected_inspection=inspection)
            if observed is not None:
                observed_decision = observed.get("decision") if type(observed) is dict else None
                if (type(observed_decision) is not dict or
                        _control_decision_without_lease(observed_decision) != _control_decision_without_lease(original)):
                    raise RevisionConflict("Kernel control receipt differs from original intent")
                with self._transaction() as connection:
                    if not _known_orchestrator_control_lease(connection, operation_id, original,
                            (observed_decision.get("lease_id"), observed_decision.get("lease_fence"))):
                        raise RevisionConflict("Kernel control receipt lease is unknown")
            if entry["kernel_receipt"] is not None and canonical(observed) != entry["kernel_receipt"]:
                raise RevisionConflict("stored Kernel control receipt differs")
            gate = gate_reader(source["run_id"])
            if type(gate) is not dict:
                raise RevisionConflict("Kernel control budget is unknown")
            with self._transaction() as connection:
                _check_takeover_budget(connection, operation_id, gate)
            claim = {"takeover_id": takeover_id, "phase": phase, **expected, "generation": original["generation"],
                     "control_epoch": original["expected_control_epoch"], "original_decision": original, "original_receipt": observed,
                     "previous_lease_id": previous[0], "previous_fence": previous[1], "new_lease_id": lease["lease_id"],
                     "new_fence": lease["lease_fence"], "lease_expires_at": lease["expires_at"], "lease_held": True,
                     "old_holder_excluded": True, "max_claims": gate.get("max_claims"), "claims_used": gate.get("claims_used"),
                     "deadline_at": gate.get("deadline_at")}
            if len(canonical(claim).encode("utf-8")) > 1048576:
                raise OrchestrationError("control takeover exceeds limit")
            observe_control_clock(self)
            verified = authorizer.verify(credential)
            with self._transaction() as connection:
                fresh = read(connection, verified)
                if (fresh[0] != entry or fresh[1] != decision or fresh[2] != source or fresh[5] != original or
                        fresh[6] != previous or fresh[7] is not None or
                        (fresh[4]["lease_id"], fresh[4]["lease_fence"], fresh[4]["expires_at"]) !=
                        (lease["lease_id"], lease["lease_fence"], lease["expires_at"])):
                    raise RevisionConflict("control takeover source changed")
                connection.execute("INSERT INTO sdk_control_lease_takeovers VALUES(?,?,?,?,NULL,NULL,?)",
                                   (takeover_id, operation_id, lease["lease_fence"], canonical(claim), float(self.clock())))
                check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
        receipt = take(takeover_credential, expected_takeover=claim)
        if type(receipt) is not dict or receipt.get("kind") != "control_lease_takeover" or canonical(receipt.get("claim")) != canonical(claim):
            raise OrchestrationError("Kernel takeover receipt differs")
        self._failpoint("after_kernel_control_takeover")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            fresh = read(connection, verified)
            if (fresh[0] != entry or fresh[1] != decision or fresh[2] != source or fresh[7] != claim or
                    self.kernel is not kernel or identity_reader() != expected["kernel_store_id"]):
                raise RevisionConflict("control takeover participant or decision changed")
            old = connection.execute("SELECT kernel_receipt FROM sdk_control_lease_takeovers WHERE takeover_id=?", (takeover_id,)).fetchone()
            if old[0] is not None and old[0] != canonical(receipt):
                raise CommandConflict("Kernel takeover receipt changed")
            connection.execute("UPDATE sdk_control_lease_takeovers SET kernel_receipt=? WHERE takeover_id=?", (canonical(receipt), takeover_id))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            authorizer.check_in_transaction(connection, verified, source["run_id"], "activate_revision" if phase == "activation" else "resume", delegation_id)
        return receipt

    def resume_cross_store_revision(self, activation_id: str, *, operation_id: str,
                                    credential, lease_credential, resume_credential, worker_credential,
                                    delegation_id: str | None = None) -> dict[str, Any]:
        """Resume Kernel first, then open Orchestrator under the same host lease.

        The host must keep all resumed Kernel business admissions closed until
        the final local receipt is committed, and must continuously serialize
        cancellation and revocation against this operation through that commit.
        """
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        identifier(activation_id, "activation_id")
        identifier(operation_id, "operation_id")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        participant = self.kernel
        identity_reader, resume = getattr(participant, "kernel_store_identity", None), getattr(participant, "resume_revision", None)
        budget_reader = getattr(participant, "inspect_budget_policy", None)
        if not callable(identity_reader) or not callable(resume) or not callable(budget_reader):
            raise OrchestrationError("Kernel resume participant is required")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            activation = connection.execute("SELECT * FROM sdk_revision_activations WHERE operation_id=?", (activation_id,)).fetchone()
            if activation is None or activation["kernel_receipt"] is None:
                raise OrchestrationError("paused activation receipt is required")
            decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (activation["decision_id"],)).fetchone()
            source = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (activation["decision_id"],)).fetchone()
            if decision is None or source is None or decision["kernel_install_receipt"] is None or decision["orchestrator_install_receipt"] is None:
                raise OrchestrationError("both revision installation receipts are required")
            budget = connection.execute("SELECT policy,kernel_receipt FROM sdk_revision_budget_policies WHERE operation_id=?", (activation["decision_id"],)).fetchone()
            if (budget is None or budget[0] != budget[1] or
                    canonical(budget_reader(source["run_id"], decision["target_generation"])) != budget[0]):
                raise OrchestrationError("current bound application budget policy is required")
            authorizer.check_in_transaction(connection, verified, source["run_id"], "resume", delegation_id)
            expected = {"operation_id": operation_id, "run_id": source["run_id"], "kernel_store_id": source["kernel_store_id"],
                        "orchestrator_store_id": source["orchestrator_store_id"], "orchestrator_incarnation": source["orchestrator_incarnation"]}
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (source["run_id"],)).fetchone()
            epoch, generation = decision["source_epoch"] + 1, decision["target_generation"]
            old = connection.execute("SELECT * FROM sdk_revision_resumes WHERE operation_id=?", (operation_id,)).fetchone()
            valid = (("paused", epoch, generation),)
            if old is not None and old["orchestrator_receipt"] is not None:
                valid += (("active", epoch + 1, generation),)
            if (identity is None or tuple(identity) != (source["orchestrator_store_id"], source["orchestrator_incarnation"]) or
                    identity_reader() != source["kernel_store_id"] or control is None or tuple(control) not in valid):
                raise RevisionConflict("resume participant or local control changed")
            lease = check_control_lease(self, connection, lease_credential, expected)
            active = json.loads(activation["kernel_receipt"])
            envelope = {**expected, "decision_id": activation["decision_id"], "barrier_operation_id": activation["decision_id"],
                "completion_operation_id": activation["decision_id"] + ":local-paused", "activation_operation_id": activation_id,
                "activation_receipt": active, "generation": generation, "expected_control_epoch": epoch, "target_control_epoch": epoch + 1,
                "orchestrator_install_receipt": json.loads(decision["orchestrator_install_receipt"]),
                "kernel_install_receipt": json.loads(decision["kernel_install_receipt"]), "lease_id": lease["lease_id"],
                "lease_fence": lease["lease_fence"], "lease_expires_at": lease["expires_at"], "lease_held": True}
            def stable(value):
                return canonical({k: v for k, v in value.items() if k != "lease_expires_at"})
            if old is not None:
                original = json.loads(old["envelope"])
                if (old["decision_id"] != activation["decision_id"] or
                        _control_decision_without_lease(original) != _control_decision_without_lease(envelope) or
                        _effective_orchestrator_control_lease(connection, operation_id, original) != (lease["lease_id"], lease["lease_fence"])):
                    raise CommandConflict("resume operation differs")
            else:
                connection.execute("INSERT INTO sdk_revision_resumes VALUES(?,?,?,NULL,NULL,?)",
                                   (operation_id, activation["decision_id"], canonical(envelope), float(self.clock())))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
        gate_reader = getattr(participant, "get_run_control", None)
        if not callable(gate_reader):
            raise OrchestrationError("Kernel resume control is unavailable")
        with self._transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM sdk_cancellation_fences WHERE run_id=? AND generation=? LIMIT 1",
                (source["run_id"], generation),
            ).fetchone():
                raise RevisionConflict("cancellation intent prevents resume")
            _check_takeover_budget(connection, operation_id, gate_reader(source["run_id"]))
        receipt = resume(resume_credential, worker_credential=worker_credential, expected_decision=envelope)
        if (type(receipt) is not dict or receipt.get("kind") != "revision_resume" or type(receipt.get("decision")) is not dict or
                _control_decision_without_lease(receipt["decision"]) != _control_decision_without_lease(envelope)):
            raise OrchestrationError("Kernel resume receipt differs")
        self._failpoint("after_kernel_revision_resume")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, source["run_id"], "resume", delegation_id)
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            # A cancellation records its intent in this same store before it
            # touches the Kernel. Serialize this check with the local commit so
            # a concurrent Kernel fence cannot be followed by a stale reopen.
            if connection.execute(
                "SELECT 1 FROM sdk_cancellation_fences WHERE run_id=? AND generation=? LIMIT 1",
                (source["run_id"], generation),
            ).fetchone():
                raise RevisionConflict("cancellation intent prevents resume")
            current = connection.execute("SELECT * FROM sdk_revision_resumes WHERE operation_id=?", (operation_id,)).fetchone()
            current_activation = connection.execute("SELECT kernel_receipt FROM sdk_revision_activations WHERE operation_id=?", (activation_id,)).fetchone()
            current_decision = connection.execute("SELECT kernel_install_receipt,orchestrator_install_receipt FROM sdk_revision_decisions WHERE operation_id=?", (activation["decision_id"],)).fetchone()
            current_budget = connection.execute("SELECT policy,kernel_receipt FROM sdk_revision_budget_policies WHERE operation_id=?", (activation["decision_id"],)).fetchone()
            current_source = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (activation["decision_id"],)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (source["run_id"],)).fetchone()
            gate_reader = getattr(participant, "get_run_control", None)
            gate = gate_reader(source["run_id"]) if callable(gate_reader) else None
            _check_takeover_budget(connection, operation_id, gate)
            if (current is None or _control_decision_without_lease(json.loads(current["envelope"])) != _control_decision_without_lease(envelope) or
                    not _known_orchestrator_control_lease(connection, operation_id, json.loads(current["envelope"]), (receipt["decision"].get("lease_id"), receipt["decision"].get("lease_fence"))) or
                    _effective_orchestrator_control_lease(connection, operation_id, json.loads(current["envelope"])) != (lease["lease_id"], lease["lease_fence"]) or self.kernel is not participant or
                    identity_reader() != source["kernel_store_id"] or identity is None or tuple(identity) != (source["orchestrator_store_id"], source["orchestrator_incarnation"]) or
                    type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) != ("active", epoch + 1, generation) or
                    current_activation is None or current_activation[0] != activation["kernel_receipt"] or current_decision is None or
                    current_budget is None or tuple(current_budget) != tuple(budget) or
                    canonical(budget_reader(source["run_id"], generation)) != budget[0] or
                    current_source is None or any(current_source[key] != source[key] for key in
                        ("run_id", "phase", "generation", "source_epoch", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation", "kernel_pause_receipt", "orchestrator_pause_receipt")) or
                    tuple(current_decision) != (decision["kernel_install_receipt"], decision["orchestrator_install_receipt"])):
                raise RevisionConflict("resume source or participant changed")
            if current["kernel_receipt"] is not None and current["kernel_receipt"] != canonical(receipt):
                raise CommandConflict("Kernel resume receipt differs")
            if current["orchestrator_receipt"] is not None:
                if control is None or tuple(control) != ("active", epoch + 1, generation):
                    raise RevisionConflict("resumed Orchestrator control changed")
                check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
                authorizer.check_in_transaction(connection, verified, source["run_id"], "resume", delegation_id)
                return dict(current)
            if control is None or tuple(control) != ("paused", epoch, generation):
                raise RevisionConflict("resume Orchestrator gate changed")
            now = float(self.clock())
            connection.execute("UPDATE sdk_managed_runs SET control_state='active',control_epoch=?,updated_at=? WHERE run_id=?", (epoch + 1, now, source["run_id"]))
            connection.execute("INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)", (source["run_id"], epoch + 1, "active", generation, "[]", None, now))
            local_receipt = {"operation_id": operation_id, "run_id": source["run_id"], "generation": generation,
                             "control_epoch": epoch + 1, "state": "active", "committed_at": now,
                             "kernel_store_id": source["kernel_store_id"], "orchestrator_store_id": source["orchestrator_store_id"],
                             "orchestrator_incarnation": source["orchestrator_incarnation"]}
            connection.execute("UPDATE sdk_revision_resumes SET kernel_receipt=?,orchestrator_receipt=? WHERE operation_id=?", (canonical(receipt), canonical(local_receipt), operation_id))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            authorizer.check_in_transaction(connection, verified, source["run_id"], "resume", delegation_id)
            return dict(connection.execute("SELECT * FROM sdk_revision_resumes WHERE operation_id=?", (operation_id,)).fetchone())

    def activate_cross_store_revision(self, decision_id: str, *, operation_id: str,
                                      credential, lease_credential, activation_credential,
                                      delegation_id: str | None = None) -> dict[str, Any]:
        """Record an authenticated deployment activation while keeping admission paused."""
        from .control_authorization import ControlAuthorizer
        from .control_lease import observe_control_clock, check_control_lease
        identifier(decision_id, "decision_id")
        identifier(operation_id, "operation_id")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        activate = getattr(participant, "activate_revision", None)
        if not callable(identity_reader) or not callable(activate):
            raise OrchestrationError("Kernel activation participant is required")
        with self._transaction() as connection:
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (decision_id,)).fetchone()
            decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (decision_id,)).fetchone()
            if operation is None or decision is None or decision["kernel_install_receipt"] is None or decision["orchestrator_install_receipt"] is None:
                raise OrchestrationError("both revision installation receipts are required")
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "activate_revision", delegation_id)
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (operation["run_id"],)).fetchone()
            if (identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]) or
                    identity_reader() != operation["kernel_store_id"] or control is None or tuple(control) !=
                    ("paused", decision["source_epoch"] + 1, decision["target_generation"])):
                raise RevisionConflict("activation participant or paused control changed")
            expected = {"operation_id": operation_id, "run_id": operation["run_id"],
                        "kernel_store_id": operation["kernel_store_id"], "orchestrator_store_id": operation["orchestrator_store_id"],
                        "orchestrator_incarnation": operation["orchestrator_incarnation"]}
            lease = check_control_lease(self, connection, lease_credential, expected)
            envelope = {**expected, "decision_id": decision_id, "barrier_operation_id": decision_id,
                        "completion_operation_id": decision_id + ":local-paused", "generation": decision["target_generation"],
                        "expected_control_epoch": decision["source_epoch"] + 1,
                        "orchestrator_install_receipt": json.loads(decision["orchestrator_install_receipt"]),
                        "kernel_install_receipt": json.loads(decision["kernel_install_receipt"]),
                        "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"],
                        "lease_expires_at": lease["expires_at"], "lease_held": True}
            old = connection.execute("SELECT * FROM sdk_revision_activations WHERE operation_id=?", (operation_id,)).fetchone()
            def stable(value):
                return canonical({k: v for k, v in value.items() if k != "lease_expires_at"})
            if old is not None:
                original = json.loads(old["envelope"])
                if (old["decision_id"] != decision_id or
                        _control_decision_without_lease(original) != _control_decision_without_lease(envelope) or
                        _effective_orchestrator_control_lease(connection, operation_id, original) != (lease["lease_id"], lease["lease_fence"])):
                    raise CommandConflict("activation operation differs")
            else:
                connection.execute("INSERT INTO sdk_revision_activations VALUES(?,?,?,NULL,?)",
                                   (operation_id, decision_id, canonical(envelope), float(self.clock())))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
        gate_reader = getattr(participant, "get_run_control", None)
        if not callable(gate_reader):
            raise OrchestrationError("Kernel activation control is unavailable")
        with self._transaction() as connection:
            _check_takeover_budget(connection, operation_id, gate_reader(operation["run_id"]))
        receipt = activate(activation_credential, expected_decision=envelope)
        if (type(receipt) is not dict or receipt.get("kind") != "revision_activation" or receipt.get("state") != "paused" or
                type(receipt.get("decision")) is not dict or _control_decision_without_lease(receipt["decision"]) != _control_decision_without_lease(envelope)):
            raise OrchestrationError("Kernel activation receipt differs")
        self._failpoint("after_kernel_revision_activation")
        observe_control_clock(self)
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "activate_revision", delegation_id)
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            old = connection.execute("SELECT * FROM sdk_revision_activations WHERE operation_id=?", (operation_id,)).fetchone()
            _check_takeover_budget(connection, operation_id, gate_reader(operation["run_id"]))
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (operation["run_id"],)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            current_op = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (decision_id,)).fetchone()
            current_decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (decision_id,)).fetchone()
            if (old is None or _control_decision_without_lease(json.loads(old["envelope"])) != _control_decision_without_lease(envelope) or
                    not _known_orchestrator_control_lease(connection, operation_id, json.loads(old["envelope"]), (receipt["decision"].get("lease_id"), receipt["decision"].get("lease_fence"))) or
                    _effective_orchestrator_control_lease(connection, operation_id, json.loads(old["envelope"])) != (lease["lease_id"], lease["lease_fence"]) or self.kernel is not participant or
                    identity_reader() != operation["kernel_store_id"] or identity is None or
                    tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"]) or
                    current_op is None or current_op["kernel_pause_receipt"] != operation["kernel_pause_receipt"] or
                    current_decision is None or current_decision["kernel_install_receipt"] != decision["kernel_install_receipt"] or
                    current_decision["orchestrator_install_receipt"] != decision["orchestrator_install_receipt"] or
                    control is None or tuple(control) != ("paused", decision["source_epoch"] + 1, decision["target_generation"])):
                raise RevisionConflict("activation source or participant changed")
            if old["kernel_receipt"] is not None and old["kernel_receipt"] != canonical(receipt):
                raise CommandConflict("activation receipt differs")
            connection.execute("UPDATE sdk_revision_activations SET kernel_receipt=? WHERE operation_id=?", (canonical(receipt), operation_id))
            check_control_lease(self, connection, lease_credential, {**expected, "lease_id": lease["lease_id"], "lease_fence": lease["lease_fence"]})
            return dict(connection.execute("SELECT * FROM sdk_revision_activations WHERE operation_id=?", (operation_id,)).fetchone())

    def stage_revision_content_page(self, page: dict, *, credential, page_credential,
                                    delegation_id: str | None = None) -> dict[str, Any]:
        """Record one host-attested direct-content page; this never activates a revision."""
        from .control_authorization import ControlAuthorizer
        fields = {"operation_id", "decision_id", "barrier_operation_id", "run_id", "kernel_store_id", "orchestrator_store_id",
                  "orchestrator_incarnation", "source_generation", "content_kind", "page_seq", "total_bytes", "chunk", "complete",
                  "lease_id", "lease_fence", "lease_expires_at", "lease_held"}
        page = clone(page)
        if type(page) is not dict or set(page) != fields:
            raise OrchestrationError("invalid revision content page")
        for key in ("operation_id", "decision_id", "barrier_operation_id", "run_id", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation", "lease_id"):
            identifier(page[key], key)
            if len(page[key].encode("utf-8")) > 4096:
                raise OrchestrationError("revision content identity exceeds its limit")
        for key in ("source_generation", "page_seq", "total_bytes", "lease_fence"):
            integer(page[key], key)
            if page[key] > (1 << 63) - 1:
                raise OrchestrationError("revision content count exceeds its limit")
        if (page["content_kind"] not in ("revision", "source_application_state", "target_application_state") or
                type(page["chunk"]) is not str or len(page["chunk"].encode("utf-8")) > 256 * 1024 or
                (not page["chunk"] and not page["complete"]) or
                type(page["complete"]) is not bool or page["lease_held"] is not True or
                type(page["lease_expires_at"]) not in (int, float) or not math.isfinite(page["lease_expires_at"]) or
                page["lease_expires_at"] <= float(self.clock()) or page["decision_id"] != page["operation_id"] or
                page["barrier_operation_id"] != page["operation_id"]):
            raise OrchestrationError("invalid bounded revision content or lease")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        verified = authorizer.verify(credential)
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        stage = getattr(participant, "stage_revision_content_page", None)
        if not callable(identity_reader) or identity_reader() != page["kernel_store_id"] or not callable(stage):
            raise OrchestrationError("identified Kernel content participant is required")
        op, kind, seq = page["operation_id"], page["content_kind"], page["page_seq"]
        def same_page(left, right):
            return canonical({k: v for k, v in left.items() if k != "lease_expires_at"}) == canonical({k: v for k, v in right.items() if k != "lease_expires_at"})
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, page["run_id"], "stage_revision_content", delegation_id)
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (op,)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (page["run_id"],)).fetchone()
            if (operation is None or operation["phase"] != "prepared" or operation["orchestrator_pause_receipt"] is None or
                    (operation["run_id"], operation["kernel_store_id"], operation["orchestrator_store_id"], operation["orchestrator_incarnation"]) !=
                    (page["run_id"], page["kernel_store_id"], page["orchestrator_store_id"], page["orchestrator_incarnation"]) or
                    identity is None or tuple(identity) != (page["orchestrator_store_id"], page["orchestrator_incarnation"]) or
                    control is None or page["source_generation"] != operation["generation"] or
                    tuple(control) != ("paused", operation["source_epoch"] + 2, operation["generation"])):
                raise OrchestrationError("revision content source or participant is unknown")
            old = connection.execute("SELECT page,kernel_receipt FROM sdk_revision_content_pages WHERE operation_id=? AND content_kind=? AND page_seq=?", (op, kind, seq)).fetchone()
            if old is not None:
                if not same_page(json.loads(old["page"]), page):
                    raise CommandConflict("revision content page differs")
                if seq:
                    predecessor = connection.execute("SELECT kernel_receipt FROM sdk_revision_content_pages WHERE operation_id=? AND content_kind=? AND page_seq=?", (op, kind, seq - 1)).fetchone()
                    if predecessor is None or predecessor[0] is None:
                        raise OrchestrationError("previous revision content page is not acknowledged")
                    prior_bytes = json.loads(predecessor[0])["cumulative_bytes"]
                else:
                    prior_bytes = 0
            else:
                previous = connection.execute("SELECT page_seq,kernel_receipt FROM sdk_revision_content_pages WHERE operation_id=? AND content_kind=? ORDER BY page_seq DESC LIMIT 1", (op, kind)).fetchone()
                if previous is None:
                    prior_bytes = 0
                    if seq != 0:
                        raise OrchestrationError("revision content starts at page zero")
                else:
                    if previous["page_seq"] + 1 != seq or previous["kernel_receipt"] is None:
                        raise OrchestrationError("previous revision content page is not acknowledged")
                    prior = json.loads(previous["kernel_receipt"])
                    if prior["capture_complete"]:
                        raise OrchestrationError("revision content is already complete")
                    fixed = set(fields) - {"page_seq", "chunk", "complete", "lease_expires_at"}
                    if canonical({k: prior["page"][k] for k in fixed}) != canonical({k: page[k] for k in fixed}):
                        raise CommandConflict("revision content stream identity differs")
                    prior_bytes = prior["cumulative_bytes"]
                count = prior_bytes + len(page["chunk"].encode("utf-8"))
                if count > page["total_bytes"] or page["complete"] != (count == page["total_bytes"]):
                    raise OrchestrationError("revision content total is inconsistent")
                connection.execute("INSERT INTO sdk_revision_content_pages VALUES(?,?,?,?,NULL)", (op, kind, seq, canonical(page)))
            expected_bytes = prior_bytes + len(page["chunk"].encode("utf-8"))
        receipt = stage(page_credential, expected_page=page)
        if (type(receipt) is not dict or receipt.get("kind") != "revision_content_page" or
                type(receipt.get("page")) is not dict or not same_page(receipt["page"], page) or
                receipt.get("capture_complete") is not page["complete"] or
                type(receipt.get("cumulative_bytes")) is not int or receipt["cumulative_bytes"] != expected_bytes or
                len(canonical(receipt).encode("utf-8")) > 1024 * 1024):
            raise OrchestrationError("Kernel content receipt differs")
        self._failpoint("after_kernel_revision_content_page")
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, page["run_id"], "stage_revision_content", delegation_id)
            old = connection.execute("SELECT page,kernel_receipt FROM sdk_revision_content_pages WHERE operation_id=? AND content_kind=? AND page_seq=?", (op, kind, seq)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (op,)).fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (page["run_id"],)).fetchone()
            if (old is None or not same_page(json.loads(old["page"]), page) or self.kernel is not participant or
                    identity is None or tuple(identity) != (page["orchestrator_store_id"], page["orchestrator_incarnation"]) or
                    operation is None or operation["phase"] != "prepared" or operation["orchestrator_pause_receipt"] is None or
                    control is None or tuple(control) != ("paused", operation["source_epoch"] + 2, operation["generation"])):
                raise RevisionConflict("revision content source or participant changed")
            if old["kernel_receipt"] is not None and old["kernel_receipt"] != canonical(receipt):
                raise CommandConflict("revision content receipt differs")
            connection.execute("UPDATE sdk_revision_content_pages SET kernel_receipt=? WHERE operation_id=? AND content_kind=? AND page_seq=?", (canonical(receipt), op, kind, seq))
        return receipt

    def adopt_legacy_page(self, manifest: dict, *, expected_run_revision: int, credential,
                          adoption_credential, worker_credential,
                          delegation_id: str | None = None) -> dict[str, Any]:
        """Stage one host-attested membership page while keeping both gates closed.

        The host verifier must establish continuous exclusive writer isolation,
        membership completeness and the authoritative consumed budget. A staged
        page with no Kernel receipt is recoverable and may already be installed.
        """
        from .control_authorization import ControlAuthorizer
        required = {"operation_id", "run_id", "kernel_store_id", "orchestrator_store_id",
                    "orchestrator_incarnation", "generation", "membership", "membership_source",
                    "membership_complete", "page_seq", "claims_used", "claims_source", "max_claims",
                    "deadline_at", "isolation_lease_id", "isolation_expires_at", "isolation_held"}
        manifest = clone(manifest)
        if type(manifest) is not dict or set(manifest) != required or len(canonical(manifest).encode("utf-8")) > 512 * 1024:
            raise OrchestrationError("invalid bounded adoption page")
        op, run_id, page = manifest["operation_id"], manifest["run_id"], manifest["page_seq"]
        identifier(op, "operation_id")
        identifier(run_id, "run_id")
        integer(page, "page_seq")
        integer(expected_run_revision, "expected_run_revision")
        for key in ("generation", "claims_used", "max_claims"):
            integer(manifest[key], key)
        if (manifest["claims_used"] > manifest["max_claims"] or type(manifest["membership"]) is not list
                or len(manifest["membership"]) > 512 or type(manifest["membership_complete"]) is not bool
                or manifest["isolation_held"] is not True or type(manifest["deadline_at"]) not in (float, int)
                or not math.isfinite(manifest["deadline_at"]) or manifest["deadline_at"] <= 0):
            raise OrchestrationError("invalid adoption evidence")
        if any(type(member) is not dict or type(member.get("execution_id")) is not str or
               len(member["execution_id"].encode("utf-8")) > 4096 for member in manifest["membership"]):
            raise OrchestrationError("adoption execution identity exceeds its bounded limit")
        for key in ("kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation",
                    "membership_source", "claims_source", "isolation_lease_id"):
            if type(manifest[key]) is not str or not manifest[key].strip() or len(manifest[key].encode("utf-8")) > 4096:
                raise OrchestrationError("invalid adoption evidence identity")
        if (type(manifest["isolation_expires_at"]) not in (int, float) or
                not math.isfinite(manifest["isolation_expires_at"]) or manifest["isolation_expires_at"] <= float(self.clock()) or
                any(manifest[key] > (1 << 63) - 1 for key in ("generation", "claims_used", "max_claims", "page_seq"))):
            raise OrchestrationError("adoption evidence is expired or out of range")
        members = manifest["membership"]
        ids = []
        for member in members:
            execution_id = member["execution_id"]
            status = member.get("status")
            if not execution_id.strip() or status not in ("accepted", "pending"):
                raise OrchestrationError("invalid adoption membership")
            if status == "pending":
                if set(member) != {"execution_id", "status", "command"}:
                    raise OrchestrationError("pending adoption membership requires its command")
                try:
                    command = ExecutionCommandV2.from_dict(member["command"])
                except Exception as exc:
                    raise OrchestrationError("invalid pending adoption command") from exc
                if command.execution_id != execution_id or command.correlation_id != run_id:
                    raise OrchestrationError("pending adoption command identity differs")
            elif set(member) != {"execution_id", "status"}:
                raise OrchestrationError("invalid accepted adoption membership")
            ids.append(execution_id)
        if ids != sorted(set(ids)) or (not ids and not manifest["membership_complete"]):
            raise OrchestrationError("adoption membership page must be ordered and nonempty unless terminal")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        verified = authorizer.verify(credential)
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        importer = getattr(participant, "import_legacy_run", None)
        if not callable(identity_reader) or identity_reader() != manifest["kernel_store_id"] or not callable(importer):
            raise OrchestrationError("identified Kernel legacy participant is required")
        immutable = canonical({key: value for key, value in manifest.items() if key not in
                               {"membership", "membership_complete", "page_seq", "isolation_expires_at"}})
        def same_page(left, right):
            return (canonical({key: value for key, value in left.items() if key != "isolation_expires_at"}) ==
                    canonical({key: value for key, value in right.items() if key != "isolation_expires_at"}))
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, run_id, "adopt_legacy", delegation_id)
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            run = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
            stored_generation = connection.execute("SELECT value FROM sdk_run_items WHERE run_id=? AND section='root' AND item_key='generation'", (run_id,)).fetchone()
            if identity is None or tuple(identity) != (manifest["orchestrator_store_id"], manifest["orchestrator_incarnation"]):
                raise OrchestrationError("adoption Orchestrator identity differs")
            if run is None or run[0] != expected_run_revision:
                raise RevisionConflict("legacy Run revision changed")
            if stored_generation is not None and canonical(json.loads(stored_generation[0])) != canonical(manifest["generation"]):
                raise RevisionConflict("legacy Run generation differs from adoption evidence")
            if stored_generation is None and manifest["generation"] != 0:
                raise RevisionConflict("legacy Run generation is unknown")
            existing = connection.execute("SELECT * FROM sdk_legacy_adoptions WHERE operation_id=?", (op,)).fetchone()
            now = float(self.clock())
            if existing is None:
                if page != 0 or connection.execute("SELECT 1 FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone():
                    raise OrchestrationError("legacy adoption must start with an unmanaged Run and page zero")
                connection.execute("INSERT INTO sdk_managed_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (run_id, "legacy-adoption:" + op, "legacy-adoption:" + op, "paused", 0,
                     manifest["generation"], manifest["max_claims"], manifest["deadline_at"], now, now))
                connection.execute("INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                    (run_id, 0, "paused", manifest["generation"], "[]", None, now))
                connection.execute("INSERT INTO sdk_legacy_adoptions VALUES(?,?,?,?,'staging',?,?)",
                                   (op, run_id, expected_run_revision, immutable, now, now))
            elif (existing["run_id"], existing["source_revision"], existing["immutable_evidence"]) != (run_id, expected_run_revision, immutable):
                raise CommandConflict("legacy adoption operation differs")
            previous = connection.execute("SELECT manifest,kernel_receipt FROM sdk_legacy_adoption_pages WHERE operation_id=? AND page_seq=?", (op, page)).fetchone()
            if previous is not None:
                if not same_page(json.loads(previous["manifest"]), manifest):
                    raise CommandConflict("legacy adoption page differs")
            else:
                if page:
                    prior = connection.execute("SELECT kernel_receipt FROM sdk_legacy_adoption_pages WHERE operation_id=? AND page_seq=?", (op, page - 1)).fetchone()
                    if prior is None or prior[0] is None or json.loads(prior[0])["capture_complete"]:
                        raise OrchestrationError("previous adoption page is not acknowledged")
                connection.execute("INSERT INTO sdk_legacy_adoption_pages VALUES(?,?,?,NULL)", (op, page, canonical(manifest)))
        receipt = importer(adoption_credential, worker_credential=worker_credential, expected_adoption=manifest)
        if (type(receipt) is not dict or receipt.get("kind") != "paused_legacy_import" or
                type(receipt.get("adoption")) is not dict or not same_page(receipt["adoption"], manifest) or receipt.get("activation") != "closed" or
                receipt.get("capture_complete") != manifest["membership_complete"] or
                len(canonical(receipt).encode("utf-8")) > 1024 * 1024):
            raise OrchestrationError("Kernel legacy receipt differs or exceeds its limit")
        self._failpoint("after_kernel_legacy_import")
        verified = authorizer.verify(credential)
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, run_id, "adopt_legacy", delegation_id)
            record = connection.execute("SELECT manifest,kernel_receipt FROM sdk_legacy_adoption_pages WHERE operation_id=? AND page_seq=?", (op, page)).fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (run_id,)).fetchone()
            run = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            if (record is None or not same_page(json.loads(record["manifest"]), manifest) or self.kernel is not participant or
                    run is None or run[0] != expected_run_revision or control is None or
                    tuple(control) != ("paused", 0, manifest["generation"]) or identity is None or
                    tuple(identity) != (manifest["orchestrator_store_id"], manifest["orchestrator_incarnation"])):
                raise RevisionConflict("legacy adoption participant or gate changed")
            if record["kernel_receipt"] is not None and record["kernel_receipt"] != canonical(receipt):
                raise CommandConflict("legacy adoption receipt differs")
            connection.execute("UPDATE sdk_legacy_adoption_pages SET kernel_receipt=? WHERE operation_id=? AND page_seq=?", (canonical(receipt), op, page))
            phase = "paused" if manifest["membership_complete"] else "staging"
            connection.execute("UPDATE sdk_legacy_adoptions SET phase=CASE WHEN phase='paused' THEN 'paused' ELSE ? END,updated_at=? WHERE operation_id=?", (phase, float(self.clock()), op))
            phase = connection.execute("SELECT phase FROM sdk_legacy_adoptions WHERE operation_id=?", (op,)).fetchone()[0]
            return {"phase": phase, "receipt": receipt}

    def install_streamed_projection(self, operation_id: str, *, storage, credential,
                                    projection_credential, lease_credential, source_read_credential=None,
                                    delegation_id: str | None = None):
        """Install a complete host-attested stream while both participants remain paused."""
        from .streamed_install import install_streamed_projection
        return install_streamed_projection(self, operation_id, storage=storage, credential=credential,
            projection_credential=projection_credential, lease_credential=lease_credential,
            source_read_credential=source_read_credential, delegation_id=delegation_id)

    def install_cross_store_projection(self, operation_id: str, *, credential,
                                       delegation_id: str | None = None) -> dict[str, Any]:
        """Install the committed local projection while retaining both closed gates."""
        from .control_authorization import ControlAuthorizer
        identifier(operation_id, "operation_id")
        authorizer = self.control_authorizer
        if type(authorizer) is not ControlAuthorizer or authorizer.orchestrator is not self:
            raise OrchestrationError("trusted control authorizer is required")
        verified = authorizer.verify(credential)
        connection = self._connect()
        try:
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone()
            decision = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
        finally:
            connection.close()
        if operation is None or decision is None or decision["kernel_install_receipt"] is None:
            raise OrchestrationError("Kernel revision installation receipt is required")
        participant = self.kernel
        identity_reader = getattr(participant, "kernel_store_identity", None)
        gate_reader = getattr(participant, "get_run_control", None)
        authority_reader = getattr(participant, "observe_revision_authority", None)
        if not callable(authority_reader):
            raise OrchestrationError("current Kernel revision authority observation is required")
        authority = authority_reader(operation_id)
        receipt = json.loads(decision["kernel_install_receipt"])
        if (type(authority) is not dict or
                (authority.get("store_id"), authority.get("run_id"), authority.get("decision_id"),
                 authority.get("generation"), authority.get("control_epoch"), authority.get("state"),
                 authority.get("worker_principal"), authority.get("worker_expires_at"), authority.get("revoked")) !=
                (operation["kernel_store_id"], operation["run_id"], operation_id,
                 decision["target_generation"], decision["source_epoch"] + 1, "paused",
                 receipt.get("worker_principal"), receipt.get("worker_expires_at"), False)):
            raise OrchestrationError("current Kernel revision authority is unknown or changed")
        if not callable(identity_reader) or identity_reader() != operation["kernel_store_id"] or not callable(gate_reader):
            raise OrchestrationError("Kernel participant identity is unknown or changed")
        gate = gate_reader(operation["run_id"])
        if (type(gate) is not dict or (gate.get("state"), gate.get("control_epoch"), gate.get("generation")) !=
                ("paused", decision["source_epoch"] + 1, decision["target_generation"])):
            raise OrchestrationError("installed Kernel gate is unknown or changed")
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "install_revision", delegation_id)
            current = connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone()
            if current is None or current["decision"] != decision["decision"] or self.kernel is not participant:
                raise RevisionConflict("revision decision or Kernel participant changed")
            if current["orchestrator_install_receipt"] is not None:
                return dict(current)
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
            control = connection.execute("SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?", (operation["run_id"],)).fetchone()
            state = _revision_projection(connection, operation["run_id"])
            if (identity is None or tuple(identity) != (operation["orchestrator_store_id"], operation["orchestrator_incarnation"])
                    or control is None or tuple(control) != ("paused", decision["source_epoch"], decision["source_generation"])
                    or state["revision"] != decision["source_revision"]
                    or canonical(state["application_state"]) != decision["source_application_state"]
                    or current["kernel_install_receipt"] != decision["kernel_install_receipt"]):
                raise RevisionConflict("local revision installation source changed")
            revision = state["revision"] + 1
            connection.execute("UPDATE sdk_runs SET revision=? WHERE run_id=?", (revision, operation["run_id"]))
            connection.execute("INSERT INTO sdk_run_revisions VALUES(?,?)", (operation["run_id"], revision))
            connection.execute("INSERT INTO sdk_retention_times VALUES('revision',?,(julianday('now')-2440587.5)*86400.0)",
                               (canonical([operation["run_id"], revision]),))
            for key, value in (("application_state", decision["target_application_state"]),
                               ("generation", canonical(decision["target_generation"]))):
                connection.execute("INSERT INTO sdk_run_items VALUES(?,'root',?,?) ON CONFLICT(run_id,section,item_key) DO UPDATE SET value=excluded.value",
                                   (operation["run_id"], key, value))
                connection.execute("INSERT INTO sdk_run_history VALUES(?,'root',?,?,?)",
                                   (operation["run_id"], key, revision, value))
            epoch = decision["source_epoch"] + 1
            now = float(self.clock())
            connection.execute("UPDATE sdk_managed_runs SET generation=?,control_epoch=?,updated_at=? WHERE run_id=?",
                               (decision["target_generation"], epoch, now, operation["run_id"]))
            connection.execute("INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                               (operation["run_id"], epoch, "paused", decision["target_generation"], "[]", None, now))
            receipt = {"operation_id": operation_id, "run_id": operation["run_id"],
                       "revision": revision, "generation": decision["target_generation"],
                       "control_epoch": epoch, "state": "paused", "installed_at": now,
                       "kernel_observation": "non_atomic", "kernel_authority_observed_at": authority.get("observed_at"),
                       "cleanup": "unknown"}
            connection.execute("UPDATE sdk_revision_decisions SET orchestrator_install_receipt=? WHERE operation_id=?",
                               (canonical(receipt), operation_id))
            result = dict(connection.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone())
        self._failpoint("after_orchestrator_revision_install")
        return result

    def advance_cross_store_pause(self, operation_id: str, *, credential,
                                  delegation_id: str | None = None, adoption_credential=None) -> dict[str, Any]:
        """Replay the Kernel close; a missing or failed receipt remains preparing."""
        identifier(operation_id, "operation_id")
        authorizer, verified = self._authorize_control_continuation(operation_id, credential, delegation_id)
        connection = self._connect()
        try:
            operation = connection.execute(
                "SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            identity = connection.execute(
                "SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1"
            ).fetchone()
            transition = None if operation is None else connection.execute(
                "SELECT drain_execution_ids,pause_mode,generation FROM sdk_managed_control_transitions "
                "WHERE run_id=? AND control_epoch=?",
                (operation["run_id"], operation["source_epoch"] + 1),
            ).fetchone()
            adoption = connection.execute("SELECT phase FROM sdk_legacy_adoptions WHERE operation_id=?", (operation_id,)).fetchone()
        finally:
            connection.close()
        if operation is None or operation["kind"] != "pause":
            raise OrchestrationError("unknown cross-store pause operation")
        if transition is None or transition["generation"] != operation["generation"]:
            raise OrchestrationError("pause drain selection is unknown")
        drain_ids = json.loads(transition["drain_execution_ids"])
        if (type(drain_ids) is not list or len(drain_ids) > 128
                or any(type(value) is not str or not value.strip() or len(value.encode("utf-8")) > 4096 for value in drain_ids)
                or drain_ids != sorted(set(drain_ids)) or len(canonical(drain_ids).encode("utf-8")) > 65536
                or transition["pause_mode"] != ("drain" if drain_ids else "interrupt")):
            raise OrchestrationError("pause drain selection is invalid")
        if identity is None or tuple(identity) != (operation["orchestrator_store_id"],
                                                    operation["orchestrator_incarnation"]):
            raise OrchestrationError("control operation Orchestrator identity changed or is unknown")
        identity_reader = getattr(self.kernel, "kernel_store_identity", None)
        if not callable(identity_reader) or identity_reader() != operation["kernel_store_id"]:
            raise OrchestrationError("control operation Kernel identity changed or is unknown")
        participant = getattr(self.kernel, "prepare_control_pause", None)
        if not callable(participant):
            raise OrchestrationError("Kernel lacks durable pause participant")
        try:
            kwargs = {"expected_epoch": operation["source_epoch"], "generation": operation["generation"]}
            if adoption is not None:
                if adoption["phase"] != "paused" or adoption_credential is None:
                    raise OrchestrationError("completed adoption and host isolation credential are required")
                kwargs["adoption_credential"] = adoption_credential
            if drain_ids:
                kwargs.update(drain_execution_ids=drain_ids,
                              drain_orchestrator_store_id=operation["orchestrator_store_id"],
                              drain_orchestrator_incarnation=operation["orchestrator_incarnation"])
            receipt = participant(operation_id, operation["run_id"], **kwargs)
            if type(receipt) is not dict or receipt.get("store_id") != operation["kernel_store_id"]:
                raise OrchestrationError("Kernel pause receipt identity is missing or changed")
            if len(canonical(receipt).encode("utf-8")) > 1024 * 1024:
                raise OrchestrationError("Kernel pause receipt exceeds the size limit")
            if (receipt.get("operation_id"), receipt.get("run_id"), receipt.get("generation"),
                    receipt.get("expected_epoch"), receipt.get("control_epoch")) != (
                    operation_id, operation["run_id"], operation["generation"],
                    operation["source_epoch"], operation["source_epoch"] + 1):
                raise OrchestrationError("Kernel pause receipt does not match the control operation")
            if (receipt.get("max_claims"), receipt.get("deadline_at")) != (
                    operation["max_claims"], operation["deadline_at"]):
                raise OrchestrationError("Kernel pause receipt budget does not match the Run")
            if receipt.get("drain_execution_ids", []) != drain_ids:
                raise OrchestrationError("Kernel pause receipt drain selection changed")
        except Exception as error:
            with self._transaction() as connection:
                connection.execute("UPDATE sdk_control_operations SET error=?,updated_at=? WHERE operation_id=?",
                                   (canonical({"type": type(error).__name__, "message": str(error)}),
                                    float(self.clock()), operation_id))
            raise
        self._failpoint("after_kernel_pause_barrier")
        with self._transaction() as connection:
            authorizer.check_in_transaction(connection, verified, operation["run_id"], "pause", delegation_id)
            current_transition = connection.execute(
                "SELECT drain_execution_ids,pause_mode,generation FROM sdk_managed_control_transitions "
                "WHERE run_id=? AND control_epoch=?", (operation["run_id"], operation["source_epoch"] + 1)
            ).fetchone()
            if current_transition is None or tuple(current_transition) != tuple(transition):
                raise OrchestrationError("pause drain selection changed")
            existing = connection.execute(
                "SELECT kernel_receipt FROM sdk_control_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if existing is None:
                raise OrchestrationError("control operation disappeared")
            if existing[0] is not None and existing[0] != canonical(receipt):
                raise OrchestrationError("Kernel returned a different pause receipt")
            connection.execute(
                "UPDATE sdk_control_operations SET kernel_receipt=?,error=NULL,updated_at=? WHERE operation_id=?",
                (canonical(receipt), float(self.clock()), operation_id),
            )
            return dict(connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone())

    def _managed_kernel_in_transaction(self, name: str):
        """Return the Kernel's participant writer for a co-located store.

        A managed control transition must share the same SQLite commit as the
        Orchestrator intent. Separate database files need a durable multi-store
        coordinator and are deliberately ineligible for these operations.
        """
        path = getattr(self.kernel, "db_path", None)
        if path is None:
            raise OrchestrationError("managed control requires a durable Kernel participant")
        if str(Path(path).resolve()) != self.db_path:
            raise OrchestrationError("managed control requires a co-located Kernel store")
        method = getattr(self.kernel, name, None)
        if not callable(method):
            raise OrchestrationError("Kernel lacks the managed control participant")
        return method

    def register_managed_run(
        self, run_id: str, *, request_id: str,
        definition: Any, task_commands: Sequence[tuple[str, ExecutionCommandV2, list[str]]],
        max_claims: int, deadline_at: float, input: Any = None,
    ) -> RunSnapshot:
        """Atomically create a paused Run, its task graph and dispatch intents.

        The matching paused Kernel gate is installed in the same SQLite
        transaction. Failure rolls back the Run and its dispatch intents.
        """
        for label, value in (("run_id", run_id), ("request_id", request_id)):
            identifier(value, label)
        integer(max_claims, "max_claims")
        if max_claims > (1 << 63) - 1:
            raise OrchestrationError("max_claims exceeds SQLite integer range")
        if (type(deadline_at) not in (int, float)
                or not math.isfinite(deadline_at) or deadline_at <= 0):
            raise OrchestrationError("deadline_at must be finite and positive")
        frozen_definition = clone(definition)
        frozen_input = clone(input)
        frozen_commands = []
        for task_id, command, dependencies in task_commands:
            identifier(task_id, "task_id")
            if type(command) is not ExecutionCommandV2:
                raise OrchestrationError("managed task command must be ExecutionCommandV2")
            if not command.execution_id.startswith("sdk-managed:") or command.correlation_id != run_id:
                raise OrchestrationError("managed command identity differs from Run")
            if type(dependencies) is not list:
                raise OrchestrationError("dependencies must be a list")
            frozen_commands.append([task_id, command.to_dict(), list(dependencies)])
        frozen_commands = _topological_commands(frozen_commands)
        spec_digest = digest({
            "input": frozen_input, "definition": frozen_definition,
            "commands": frozen_commands,
            "max_claims": max_claims,
            "deadline_at": float(deadline_at),
        })
        now = float(self.clock())
        participant = self._managed_kernel_in_transaction("register_run_control_in_transaction")
        with self._transaction() as connection:
            old = connection.execute(
                "SELECT run_id,spec_digest FROM sdk_managed_runs WHERE request_id=?", (request_id,)
            ).fetchone()
            if old is not None:
                if old["run_id"] != run_id or old["spec_digest"] != spec_digest:
                    raise CommandConflict("managed request identity already has different content")
                return self._load(connection, run_id)
            if connection.execute("SELECT 1 FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone():
                raise CommandConflict("Run identity is already in use")
            if connection.execute(
                "SELECT 1 FROM kernel_run_controls WHERE run_id=?", (run_id,)
            ).fetchone():
                raise CommandConflict("Kernel control identity is already in use")
            state: RunSnapshot = {
                "run_id": run_id, "revision": 0, "state": "running", "generation": 0,
                "input": frozen_input, "definition": frozen_definition,
                "application_state": None, "tasks": {}, "waits": {}, "signals": {},
            }
            connection.execute("INSERT INTO sdk_runs VALUES(?,?,?)", (run_id, 0, "running"))
            connection.execute(
                "INSERT INTO sdk_managed_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (run_id, request_id, spec_digest, "paused", 0, 0, max_claims,
                 float(deadline_at), now, now),
            )
            connection.execute(
                "INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                (run_id, 0, "paused", 0, "[]", None, now),
            )
            participant(
                connection, run_id, max_claims=max_claims,
                deadline_at=float(deadline_at),
            )
            registrations = []
            for task_id, command, dependencies in frozen_commands:
                reduce_operation(state, {"kind": "add_task", "task_id": task_id,
                                         "command": command, "dependencies": dependencies})
                registrations.append((task_id, 0, state["tasks"][task_id]["attempts"][0]))
            self._register_executions(connection, state, registrations)
            intents = []
            for task_id, _, dependencies in frozen_commands:
                if not dependencies:
                    intents.extend(reduce_operation(state, {"kind": "dispatch", "task_id": task_id}))
            for ordinal, intent in enumerate(intents):
                intent["generation"] = 0
                connection.execute(
                    "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) VALUES(?,?,?,?)",
                    (run_id, "managed-create", ordinal, canonical(intent)),
                )
            self._save(connection, state)
            self._event(connection, state, "managed.created", {
                "request_id": request_id, "spec_digest": spec_digest,
                "task_count": len(frozen_commands), "control_state": "paused",
            })
            self._write_receipt(connection, run_id, "managed-create", spec_digest, state)
            return self._load(connection, run_id)

    def get_managed_control(self, run_id: str) -> dict[str, Any]:
        """Read the durable control row without loading task history."""
        identifier(run_id, "run_id")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT run_id,request_id,spec_digest,control_state,control_epoch,generation,"
                "max_claims,deadline_at,created_at,updated_at FROM sdk_managed_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise OrchestrationError("Run is not registered for managed control")
            return dict(row)
        finally:
            connection.close()

    @staticmethod
    def _dispatch_accepted_tasks(state: RunSnapshot) -> tuple[list[dict], set[tuple[str, str]]]:
        """Queue tasks whose current predecessor attempts were explicitly accepted."""
        intents: list[dict] = []
        changes: set[tuple[str, str]] = set()
        for task_id, task in state["tasks"].items():
            current = task["attempts"][-1]
            if current["state"] != "planned":
                continue
            if not task["dependencies"]:
                # Roots are queued at creation and never redispatched here.
                continue
            if any(not state["tasks"][dependency].get("managed_acceptance", {}).get("accepted")
                   or state["tasks"][dependency]["managed_acceptance"].get("attempt")
                   != len(state["tasks"][dependency]["attempts"]) - 1
                   for dependency in task["dependencies"]):
                continue
            intents.extend(reduce_operation(state, {"kind": "dispatch", "task_id": task_id}))
            changes.add(("attempt", canonical([task_id, len(task["attempts"]) - 1])))
        return intents, changes

    def record_managed_acceptance(
        self, run_id: str, task_id: str, *, request_id: str,
        expected_revision: int, accepted: bool, evidence: dict[str, Any],
    ) -> RunSnapshot:
        """Record an application decision and dispatch newly eligible successors.

        SDK terminal status never implies business acceptance. The application
        supplies durable evidence, while this transaction owns the graph
        advancement and its outbox. A paused Run records the decision but does
        not queue new work until a later active advancement.
        """
        for label, value in (("run_id", run_id), ("task_id", task_id),
                             ("request_id", request_id)):
            identifier(value, label)
        integer(expected_revision, "expected_revision")
        if type(accepted) is not bool:
            raise OrchestrationError("accepted must be a boolean")
        if type(evidence) is not dict or not evidence:
            raise OrchestrationError("acceptance requires nonempty application evidence")
        frozen_evidence = clone(evidence)
        fingerprint = digest({
            "kind": "acceptance", "run_id": run_id, "task_id": task_id,
            "accepted": accepted,
            "evidence": frozen_evidence,
        })
        with self._transaction() as connection:
            receipt = connection.execute(
                "SELECT digest,response FROM sdk_managed_commands WHERE run_id=? AND request_id=?",
                (run_id, request_id),
            ).fetchone()
            if receipt is not None:
                if receipt["digest"] != fingerprint:
                    raise CommandConflict("managed request identity already has different content")
                return self._load_at(connection, run_id, json.loads(receipt["response"])["revision"])
            control = connection.execute(
                "SELECT control_state,generation FROM sdk_managed_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if control is None:
                raise OrchestrationError("unknown managed Run")
            state = self._load(connection, run_id)
            if state["revision"] != expected_revision:
                raise RevisionConflict("managed Run revision changed")
            task = state["tasks"].get(task_id)
            if task is None:
                raise OrchestrationError("unknown managed task")
            attempt_index = len(task["attempts"]) - 1
            current = task["attempts"][attempt_index]
            if current["state"] not in TERMINAL:
                raise OrchestrationError("managed task must settle before acceptance")
            if task.get("managed_acceptance") is not None:
                raise CommandConflict("current managed task attempt already has an acceptance decision")
            task["managed_acceptance"] = {
                "attempt": attempt_index, "generation": current.get("generation", 0),
                "accepted": accepted, "evidence": frozen_evidence,
            }
            changes: set[tuple[str, str]] = {("task", task_id)}
            intents: list[dict] = []
            if accepted and control["control_state"] == "active":
                intents, dispatch_changes = self._dispatch_accepted_tasks(state)
                changes.update(dispatch_changes)
            command_id = "managed-accept:" + request_id
            for ordinal, intent in enumerate(intents):
                intent["generation"] = control["generation"]
                connection.execute(
                    "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) VALUES(?,?,?,?)",
                    (run_id, command_id, ordinal, canonical(intent)),
                )
            state["revision"] += 1
            self._save(connection, state, changes=changes)
            self._event(connection, state, "managed.acceptance", {
                "task_id": task_id, "attempt": attempt_index,
                "accepted": accepted, "dispatch_count": len(intents),
            })
            connection.execute(
                "INSERT INTO sdk_managed_commands(run_id,request_id,digest,response) VALUES(?,?,?,?)",
                (run_id, request_id, fingerprint,
                 canonical({"run_id": run_id, "revision": state["revision"]})),
            )
            return state

    def _request_managed_control(
        self, run_id: str, *, request_id: str, kind: str,
        expected_run_revision: int, expected_control_epoch: int,
        mode: str | None = None,
        drain_execution_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Record a control intent before touching a separate Kernel store."""
        identifier(run_id, "run_id")
        identifier(request_id, "request_id")
        integer(expected_run_revision, "expected_run_revision")
        integer(expected_control_epoch, "expected_control_epoch")
        if kind not in {"pause", "resume"}:
            raise OrchestrationError("unsupported managed control request")
        if kind == "pause" and mode not in {"drain", "interrupt"}:
            raise OrchestrationError("pause mode must be drain or interrupt")
        if kind == "resume" and mode is not None:
            raise OrchestrationError("resume has no pause mode")
        if kind == "resume" and drain_execution_ids:
            raise OrchestrationError("resume cannot preserve drain permissions")
        if (isinstance(drain_execution_ids, (str, bytes, bytearray))
                or not isinstance(drain_execution_ids, Sequence)):
            raise OrchestrationError("drain execution identifiers must be a sequence")
        if any(type(value) is not str or not value.strip() for value in drain_execution_ids):
            raise OrchestrationError("drain execution identifiers must be nonempty strings")
        requested_drain_ids = tuple(sorted(set(drain_execution_ids)))
        if len(requested_drain_ids) > 1000:
            raise OrchestrationError("drain set exceeds the 1000-execution control limit")
        if mode == "interrupt" and requested_drain_ids:
            raise OrchestrationError("interrupt pause cannot grant drain executions")
        fingerprint = digest({
            "kind": kind, "run_id": run_id, "mode": mode,
            "drain_execution_ids": list(requested_drain_ids),
        })
        with self._transaction() as connection:
            receipt = connection.execute(
                "SELECT digest,response FROM sdk_managed_commands WHERE run_id=? AND request_id=?",
                (run_id, request_id),
            ).fetchone()
            if receipt is not None:
                if receipt["digest"] != fingerprint:
                    raise CommandConflict("managed request identity already has different content")
                return json.loads(receipt["response"])
            run = connection.execute(
                "SELECT revision,state FROM sdk_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            control = connection.execute(
                "SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if run is None or control is None:
                raise OrchestrationError("unknown managed Run")
            if run["state"] != "running":
                raise OrchestrationError("terminal Run cannot change managed control state")
            if run["revision"] != expected_run_revision or control["control_epoch"] != expected_control_epoch:
                raise RevisionConflict("managed Run observation changed")
            source_state = control["control_state"]
            if kind == "pause" and source_state != "active":
                raise OrchestrationError("only active Run may request pause")
            if kind == "resume" and source_state != "paused":
                raise OrchestrationError("only paused Run may request resume")
            if requested_drain_ids:
                placeholders = ",".join("?" for _ in requested_drain_ids)
                count = connection.execute(
                    "SELECT COUNT(*) FROM sdk_executions s "
                    "JOIN kernel_executions k ON k.execution_id=s.execution_id "
                    "WHERE s.run_id=? AND s.generation=? "
                    "AND k.state IN ('leased','running') "
                    f"AND s.execution_id IN ({placeholders})",
                    (run_id, control["generation"], *requested_drain_ids),
                ).fetchone()[0]
                if count != len(requested_drain_ids):
                    raise OrchestrationError(
                        "drain set requires a previously leased execution; "
                        "queued child wait registration is not available"
                    )
            drain_ids = requested_drain_ids
            if kind == "pause" and mode == "drain":
                admitted = connection.execute(
                    "SELECT m.execution_id FROM kernel_managed_executions m "
                    "JOIN kernel_executions k ON k.execution_id=m.execution_id "
                    "WHERE m.run_id=? AND m.generation=? "
                    "AND k.state IN ('leased','running') LIMIT 1001",
                    (run_id, control["generation"]),
                ).fetchall()
                if len(admitted) > 1000:
                    raise OrchestrationError("drain pause exceeds the 1000-execution control limit")
                drain_ids = tuple(sorted(set(requested_drain_ids) | {row[0] for row in admitted}))
            target_state = "pausing" if kind == "pause" else "active"
            target_epoch = expected_control_epoch + 1
            participant = self._managed_kernel_in_transaction("set_run_control_in_transaction")
            if participant is not None:
                participant(
                    connection, run_id, expected_epoch=expected_control_epoch,
                    state=target_state, generation=control["generation"],
                    drain_execution_ids=drain_ids,
                )
            now = float(self.clock())
            changed = connection.execute(
                "UPDATE sdk_managed_runs SET control_state=?,control_epoch=?,updated_at=? "
                "WHERE run_id=? AND control_state=? AND control_epoch=?",
                (target_state, target_epoch, now, run_id, source_state, expected_control_epoch),
            ).rowcount
            if changed != 1:
                raise RevisionConflict("managed control state changed")
            if kind == "pause":
                cleanup_rows = connection.execute(
                    "SELECT m.execution_id,m.generation FROM kernel_managed_executions m "
                    "JOIN kernel_executions e ON e.execution_id=m.execution_id "
                    "WHERE m.run_id=? AND m.generation=? "
                    "AND e.state IN ('running','recovery_required') "
                    "AND e.started_at IS NOT NULL LIMIT 1001",
                    (run_id, control["generation"]),
                ).fetchall()
                if len(cleanup_rows) > 1000:
                    raise OrchestrationError(
                        "pause exceeds the 1000-execution cleanup transaction limit"
                    )
                for execution in cleanup_rows:
                    connection.execute(
                        "INSERT INTO sdk_managed_cleanup_obligations "
                        "(run_id,control_epoch,execution_id,generation,state,evidence,created_at,updated_at) "
                        "VALUES(?,?,?,?, 'pending',NULL,?,?)",
                        (run_id, target_epoch, execution["execution_id"],
                         execution["generation"], now, now),
                    )
            cancel_count = 0
            if kind == "pause" and mode == "interrupt":
                pending_cancels = connection.execute(
                    "SELECT execution_id,command,generation FROM sdk_executions "
                    "WHERE run_id=? AND active=1 ORDER BY execution_id LIMIT 1001",
                    (run_id,),
                ).fetchall()
                if len(pending_cancels) > 1000:
                    raise OrchestrationError(
                        "interrupt pause exceeds the 1000-execution transaction limit"
                    )
                for ordinal, execution in enumerate(pending_cancels):
                    intent = {
                        "kind": "cancel", "execution_id": execution["execution_id"],
                        "reason": "managed interrupt pause", "command": json.loads(execution["command"]),
                        "generation": execution["generation"],
                    }
                    connection.execute(
                        "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) "
                        "VALUES(?,?,?,?)",
                        (run_id, "managed-interrupt:" + request_id, ordinal, canonical(intent)),
                    )
                cancel_count = len(pending_cancels)
            resulting_revision = run["revision"]
            if kind == "resume":
                state = self._load(connection, run_id)
                intents, changes = self._dispatch_accepted_tasks(state)
                if intents:
                    for ordinal, intent in enumerate(intents):
                        intent["generation"] = control["generation"]
                        connection.execute(
                            "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) "
                            "VALUES(?,?,?,?)",
                            (run_id, "managed-resume:" + request_id, ordinal, canonical(intent)),
                        )
                    state["revision"] += 1
                    self._save(connection, state, changes=changes)
                    resulting_revision = state["revision"]
            response = {"run_id": run_id, "control_state": target_state,
                        "control_epoch": target_epoch, "generation": control["generation"],
                        "run_revision": resulting_revision, "mode": mode,
                        "drain_execution_ids": list(drain_ids),
                        "cancel_count": cancel_count}
            connection.execute(
                "INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                (run_id, target_epoch, target_state, control["generation"],
                 canonical(list(drain_ids)), mode, now),
            )
            connection.execute(
                "INSERT INTO sdk_managed_commands(run_id,request_id,digest,response) VALUES(?,?,?,?)",
                (run_id, request_id, fingerprint, canonical(response)),
            )
            self._event(connection, {
                "run_id": run_id, "revision": resulting_revision,
                "generation": control["generation"],
            }, "managed." + kind + ".requested", response)
            return response

    def _settle_managed_pause(self, run_id: str, *, expected_control_epoch: int) -> dict[str, Any]:
        """Mark pause complete after the caller verifies every execution gate."""
        identifier(run_id, "run_id")
        integer(expected_control_epoch, "expected_control_epoch")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise OrchestrationError("unknown managed Run")
            if row["control_state"] == "paused" and row["control_epoch"] == expected_control_epoch + 1:
                return {"run_id": run_id, "control_state": "paused",
                        "control_epoch": expected_control_epoch + 1,
                        "generation": row["generation"]}
            if row["control_epoch"] != expected_control_epoch:
                raise RevisionConflict("managed control epoch changed")
            if row["control_state"] != "pausing":
                raise OrchestrationError("managed Run is not pausing")
            transition = connection.execute(
                "SELECT pause_mode FROM sdk_managed_control_transitions "
                "WHERE run_id=? AND control_epoch=?",
                (run_id, expected_control_epoch),
            ).fetchone()
            if transition is None:
                raise OrchestrationError("managed pause transition is missing")
            permit = connection.execute(
                "SELECT execution_id,state FROM sdk_dispatch_permits "
                "WHERE run_id=? AND state!='accepted' ORDER BY sequence LIMIT 1",
                (run_id,),
            ).fetchone()
            if permit is not None:
                raise OrchestrationError(
                    f"managed pause has unresolved dispatch {permit['execution_id']} "
                    f"({permit['state']})"
                )
            if transition["pause_mode"] == "interrupt" and connection.execute(
                "SELECT 1 FROM sdk_outbox WHERE run_id=? AND delivered=0 "
                "AND command_id LIKE 'managed-interrupt:%' LIMIT 1",
                (run_id,),
            ).fetchone():
                raise OrchestrationError("managed interrupt cancellations are still pending")
            cleanup = connection.execute(
                "SELECT execution_id FROM sdk_managed_cleanup_obligations "
                "WHERE run_id=? AND control_epoch=? AND state='pending' LIMIT 1",
                (run_id, expected_control_epoch),
            ).fetchone()
            if cleanup is not None:
                raise OrchestrationError(
                    f"managed pause lacks cleanup evidence for {cleanup['execution_id']}"
                )
            participant = self._managed_kernel_in_transaction("set_run_control_in_transaction")
            if participant is not None:
                blocked = connection.execute(
                    "SELECT m.execution_id,COALESCE(e.state,'missing') AS state "
                    "FROM kernel_managed_executions m LEFT JOIN kernel_executions e "
                    "ON e.execution_id=m.execution_id WHERE m.run_id=? AND "
                    "((m.drain_allowed=1 AND (e.execution_id IS NULL OR e.state NOT IN "
                    "('succeeded','failed','timed_out','cancelled','dead'))) "
                    "OR e.state IN ('leased','running','recovery_required')) LIMIT 1",
                    (run_id,),
                ).fetchone()
                if blocked is not None:
                    raise OrchestrationError(
                        f"managed pause is blocked by {blocked['execution_id']} "
                        f"({blocked['state']})"
                    )
                effect = connection.execute(
                    "SELECT e.effect_id FROM kernel_effects e JOIN kernel_managed_executions m "
                    "ON m.execution_id=e.execution_id WHERE m.run_id=? "
                    "AND e.state IN ('performing','indeterminate') LIMIT 1",
                    (run_id,),
                ).fetchone()
                if effect is not None:
                    raise OrchestrationError(
                        f"managed pause is blocked by unresolved effect {effect['effect_id']}"
                    )
                participant(
                    connection, run_id, expected_epoch=expected_control_epoch,
                    state="paused", generation=row["generation"],
                )
            changed = connection.execute(
                "UPDATE sdk_managed_runs SET control_state='paused',control_epoch=?,updated_at=? "
                "WHERE run_id=? AND control_state='pausing' AND control_epoch=?",
                (expected_control_epoch + 1, float(self.clock()), run_id, expected_control_epoch),
            ).rowcount
            if changed != 1:
                raise RevisionConflict("managed control state changed")
            revision = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()[0]
            response = {"run_id": run_id, "control_state": "paused",
                        "control_epoch": expected_control_epoch + 1,
                        "generation": row["generation"]}
            connection.execute(
                "INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                (run_id, expected_control_epoch + 1, "paused", row["generation"],
                 "[]", None, float(self.clock())),
            )
            self._event(connection, {"run_id": run_id, "revision": revision,
                                     "generation": row["generation"]}, "managed.paused", response)
            return response

    def _confirm_managed_cleanup_from_runtime(
        self, run_id: str, execution_id: str, *, control_epoch: int,
    ) -> dict[str, Any]:
        """Seal a cleanup obligation only from a bound Runtime cancellation receipt.

        The cancellation journal is a separate immutable evidence store. A
        missing receipt, thread-only revocation, unresolved sandbox operation,
        or unknown Effect leaves the obligation pending.
        """
        identifier(run_id, "run_id")
        identifier(execution_id, "execution_id")
        integer(control_epoch, "control_epoch")
        journal = getattr(self.runtime, "cancellation_journal", None)
        with self._transaction() as connection:
            obligation = connection.execute(
                "SELECT state,evidence FROM sdk_managed_cleanup_obligations "
                "WHERE run_id=? AND control_epoch=? AND execution_id=?",
                (run_id, control_epoch, execution_id),
            ).fetchone()
            if obligation is None:
                raise OrchestrationError("unknown managed cleanup obligation")
            if obligation["state"] == "confirmed":
                return json.loads(obligation["evidence"])
            if not isinstance(journal, CancellationJournal):
                raise OrchestrationError("trusted Runtime cancellation journal is unavailable")
            row = connection.execute(
                "SELECT k.* FROM kernel_executions k JOIN kernel_managed_executions m "
                "ON m.execution_id=k.execution_id WHERE k.execution_id=? AND m.run_id=?",
                (execution_id, run_id),
            ).fetchone()
            if row is None or row["state"] not in TERMINAL:
                raise OrchestrationError("execution authority has not settled")
            if connection.execute(
                "SELECT 1 FROM kernel_effects WHERE execution_id=? "
                "AND state IN ('performing','indeterminate') LIMIT 1",
                (execution_id,),
            ).fetchone():
                raise OrchestrationError("unresolved effect blocks cleanup confirmation")
            snapshot = self.kernel._snapshot(row)
            try:
                page = inspect_cancellation_journal(
                    journal.path, source_id=journal.source_id,
                    kernel_path=self.kernel.db_path, snapshot=snapshot, limit=1000,
                )
                sandbox_records, sandbox_issues = _sandbox_facts(connection, snapshot)
            except (OSError, ValueError, sqlite3.Error) as error:
                raise OrchestrationError("runtime cleanup evidence is unavailable") from error
            if page.truncated or sandbox_issues or any(
                not record["cleanup_confirmed"] for record in sandbox_records
            ):
                raise OrchestrationError("runtime cleanup evidence is incomplete")
            receipt = next((item for item in page.receipts
                            if "failure" not in item.phases
                            and item.phases.get("authority_revoked", {}).get("state") == "confirmed"
                            and item.phases.get("process_cleanup", {}).get("state") == "confirmed"
                            and (not sandbox_records or item.phases.get("remote_cleanup", {}).get("state")
                                 == "confirmed")), None)
            if receipt is None:
                raise OrchestrationError("no process-stop receipt confirms managed cleanup")
            proof = {
                "source": "runtime.cancellation_journal",
                "source_id": journal.source_id,
                "receipt_id": receipt.receipt_id,
                "command_digest": receipt.command_digest,
                "attempt": receipt.attempt,
                "fence": receipt.fence,
                "sandbox_operations": len(sandbox_records),
            }
            encoded = canonical(proof)
            connection.execute(
                "UPDATE sdk_managed_cleanup_obligations SET state='confirmed',evidence=?,updated_at=? "
                "WHERE run_id=? AND control_epoch=? AND execution_id=? AND state='pending'",
                (encoded, float(self.clock()), run_id, control_epoch, execution_id),
            )
            return proof

    def list_managed_control_transitions(
        self, run_id: str, *, after_epoch: int = -1, limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        """Page immutable transitions for Kernel barrier reconciliation."""
        identifier(run_id, "run_id")
        if type(after_epoch) is not int or after_epoch < -1:
            raise OrchestrationError("after_epoch must be an integer >= -1")
        integer(limit, "limit")
        if not 1 <= limit <= 100:
            raise OrchestrationError("limit must be between 1 and 100")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT control_epoch,control_state,generation,drain_execution_ids,pause_mode "
                "FROM sdk_managed_control_transitions WHERE run_id=? AND control_epoch>? "
                "ORDER BY control_epoch LIMIT ?",
                (run_id, after_epoch, limit),
            ).fetchall()
            return tuple({"control_epoch": row["control_epoch"],
                          "control_state": row["control_state"],
                          "generation": row["generation"],
                          "pause_mode": row["pause_mode"],
                          "drain_execution_ids": json.loads(row["drain_execution_ids"])}
                         for row in rows)
        finally:
            connection.close()
