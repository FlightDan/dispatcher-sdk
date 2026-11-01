"""Durable application projection dependencies for managed execution.

The host authenticates both declarations and receipts.  A receipt is a host
attestation of a durable application-store commit, not an SDK-generated fact.
"""
from __future__ import annotations

import json

from ._sqlite_base import encode_json
from .errors import CASConflictError, StorageIsolationError


class ProjectionGateMixin:
    def _projection_proof(self, credential, claim, expected, action, timestamp):
        try:
            verified = self._authority_verifier(credential)
            principal = verified["principal"]
            expiry = self._number(verified["expires_at"], "authority expiry", minimum=0.0)
            if (type(principal) is not str or not principal.strip() or expiry <= timestamp
                    or encode_json(verified[claim]) != encode_json(expected)
                    or not any(tuple(p) == (expected["run_id"], action) for p in verified["permissions"])):
                raise ValueError("projection authorization differs")
            return principal, expiry
        except Exception:
            raise StorageIsolationError("host did not authorize projection operation") from None

    @staticmethod
    def _projection_decision(connection, decision_id, run_id, generation):
        row = connection.execute("SELECT receipt_json FROM kernel_revision_installs WHERE decision_id=? AND run_id=?",
                                 (decision_id, run_id)).fetchone()
        if row is None:
            raise CASConflictError("projection revision is not installed")
        decision = json.loads(row[0])["decision"]
        identity = connection.execute("SELECT store_id FROM kernel_store_identity WHERE singleton=1").fetchone()
        if (decision["target_generation"] != generation or identity is None
                or decision.get("kernel_store_id") != identity[0]):
            raise CASConflictError("projection revision generation differs")
        return decision

    def declare_projection_dependencies(self, credential, *, expected_declaration):
        """Bind a host-attested exact command to its application scope subset."""
        try:
            d = json.loads(encode_json(expected_declaration))
            if (set(d) != {"decision_id", "run_id", "generation", "execution_id", "command", "scopes", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"}
                    or any(type(d[k]) is not str or not d[k].strip() or len(d[k].encode()) > 1024
                           for k in ("decision_id", "run_id", "execution_id", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"))
                    or type(d["generation"]) is not int or d["generation"] < 0
                    or type(d["command"]) is not dict or d["command"].get("execution_id") != d["execution_id"]
                    or type(d["scopes"]) is not list or len(d["scopes"]) > 32
                    or any(type(s) is not str or not s.strip() or len(s.encode()) > 1024 for s in d["scopes"])
                    or len(set(d["scopes"])) != len(d["scopes"])
                    or len(encode_json(d).encode()) > 65536):
                raise ValueError("invalid declaration")
        except Exception:
            raise ValueError("invalid projection dependency declaration") from None
        with self._transaction() as (connection, timestamp):
            proof = self._projection_proof(credential, "projection_declaration", d, "kernel:declare_projection", timestamp)
            decision = self._projection_decision(connection, d["decision_id"], d["run_id"], d["generation"])
            control = connection.execute("SELECT generation FROM kernel_run_controls WHERE run_id=?", (d["run_id"],)).fetchone()
            scopes = {item["scope_id"] for item in decision.get("projection_requirements", [])}
            if (control is None or control[0] != d["generation"] or any(s not in scopes for s in d["scopes"])
                    or any(d[k] != decision[k] for k in ("kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"))):
                raise CASConflictError("projection declaration scope or generation differs")
            row = connection.execute("SELECT command_json FROM kernel_executions WHERE execution_id=?", (d["execution_id"],)).fetchone()
            if row is not None and row[0] != encode_json(d["command"]):
                raise CASConflictError("projection declaration command differs")
            encoded = encode_json(d)
            prior = connection.execute("SELECT declaration_json FROM kernel_projection_declarations WHERE execution_id=?", (d["execution_id"],)).fetchone()
            if prior is None:
                connection.execute("INSERT INTO kernel_projection_declarations VALUES(?,?,?,?)", (d["execution_id"], d["run_id"], d["generation"], encoded))
            elif prior[0] != encoded:
                raise CASConflictError("projection declaration is immutable")
            now = self._advance_clock(connection)
            if self._projection_proof(credential, "projection_declaration", d, "kernel:declare_projection", now) != proof or proof[1] <= self._advance_clock(connection):
                raise StorageIsolationError("projection declaration authority expired")
            return d

    def install_projection_receipt(self, credential, *, expected_receipt):
        """Install a host-authenticated receipt of an external participant commit."""
        fields = {"decision_id", "run_id", "source_revision", "source_epoch", "source_generation", "target_generation", "migration_version", "source_application_projection_version", "application_projection_version", "participant_id", "scope_id", "receipt_id", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"}
        try:
            receipt = json.loads(encode_json(expected_receipt))
            if (type(receipt) is not dict or set(receipt) != fields or len(encode_json(receipt).encode()) > 65536
                    or any(type(receipt[k]) is not str or not receipt[k].strip() or len(receipt[k].encode()) > 1024
                           for k in ("decision_id", "run_id", "migration_version", "source_application_projection_version", "application_projection_version", "participant_id", "scope_id", "receipt_id", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"))
                    or any(type(receipt[k]) is not int or receipt[k] < 0 for k in ("source_revision", "source_epoch", "source_generation", "target_generation"))):
                raise ValueError("invalid receipt")
        except Exception:
            raise ValueError("invalid projection receipt") from None
        with self._transaction() as (connection, timestamp):
            proof = self._projection_proof(credential, "projection_receipt", receipt, "kernel:install_projection", timestamp)
            decision = self._projection_decision(connection, receipt["decision_id"], receipt["run_id"], receipt["target_generation"])
            control = connection.execute("SELECT generation FROM kernel_run_controls WHERE run_id=?", (receipt["run_id"],)).fetchone()
            if (control is None or control[0] != receipt["target_generation"]
                    or any(receipt[k] != decision[k] for k in ("source_revision", "source_generation", "target_generation", "migration_version", "source_application_projection_version", "application_projection_version", "kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation"))
                    or receipt["source_epoch"] != decision["source_control_epoch"]
                    or {"participant_id": receipt["participant_id"], "scope_id": receipt["scope_id"]} not in decision.get("projection_requirements", [])):
                raise CASConflictError("projection receipt is not bound to the installed revision")
            key = (receipt["decision_id"], receipt["participant_id"], receipt["scope_id"])
            encoded = encode_json(receipt)
            prior = connection.execute("SELECT receipt_json FROM kernel_projection_receipts WHERE decision_id=? AND participant_id=? AND scope_id=?", key).fetchone()
            if prior is None:
                connection.execute("INSERT INTO kernel_projection_receipts VALUES(?,?,?,?)", (*key, encoded))
            elif prior[0] != encoded:
                raise CASConflictError("projection participant receipt is immutable")
            now = self._advance_clock(connection)
            if self._projection_proof(credential, "projection_receipt", receipt, "kernel:install_projection", now) != proof or proof[1] <= self._advance_clock(connection):
                raise StorageIsolationError("projection receipt authority expired")
            return receipt

    def _check_projection_dependencies(self, connection, run_id, generation, execution_id, *, command_json=None):
        row = connection.execute("SELECT decision_id,requirements_json FROM kernel_projection_requirements WHERE run_id=? AND generation=?", (run_id, generation)).fetchone()
        if row is None:
            return
        decision_id, requirements = row[0], json.loads(row[1])
        declared = connection.execute("SELECT declaration_json FROM kernel_projection_declarations WHERE execution_id=? AND run_id=? AND generation=?", (execution_id, run_id, generation)).fetchone()
        if declared is None:
            raise CASConflictError("execution has no projection dependency declaration")
        declaration = json.loads(declared[0])
        if command_json is None:
            actual = connection.execute("SELECT command_json FROM kernel_executions WHERE execution_id=?", (execution_id,)).fetchone()
            command_json = None if actual is None else actual[0]
        if declaration["decision_id"] != decision_id or command_json != encode_json(declaration["command"]):
            raise CASConflictError("projection dependency command or revision differs")
        for item in requirements:
            if item["scope_id"] in declaration["scopes"] and connection.execute(
                    "SELECT 1 FROM kernel_projection_receipts WHERE decision_id=? AND participant_id=? AND scope_id=?",
                    (decision_id, item["participant_id"], item["scope_id"])).fetchone() is None:
                raise CASConflictError("application projection scope is not ready")
