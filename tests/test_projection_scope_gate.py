"""Real SQLite admission with synthetic host attestations and revision facts."""
import tempfile
import time
import unittest
from pathlib import Path

from dispatcher_sdk.execution_kernel import CASConflictError, SQLiteKernel
from dispatcher_sdk.execution_kernel._sqlite_base import encode_json
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from tests.test_child_budget_declaration import command


class ProjectionScopeGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.claim = {}
        self.expiry = time.time() + 300
        def verifier(credential):
            if credential != "host":
                raise ValueError("unknown credential")
            return {"principal": "host", "expires_at": self.expiry,
                    "permissions": [("run", "kernel:declare_projection"), ("run", "kernel:install_projection")],
                    **self.claim}
        self.kernel = SQLiteKernel(Path(self.tmp.name) / "kernel.sqlite", authority_verifier=verifier)
        self.addCleanup(self.kernel.close)
        self.kernel.register_run_control("run", max_claims=10, deadline_at=self.expiry)
        self.kernel.set_run_control("run", expected_epoch=0, generation=0, state="active")
        self.decision = {"decision_id": "decision", "run_id": "run", "source_revision": 2,
            "source_control_epoch": 4, "source_generation": 0, "target_generation": 0,
            "migration_version": "m1", "application_projection_version": "v1",
            "source_application_projection_version": "v0",
            "kernel_store_id": self.kernel.kernel_store_identity(), "orchestrator_store_id": "orchestrator",
            "orchestrator_incarnation": "incarnation",
            "projection_requirements": [{"participant_id": "a", "scope_id": "x"},
                                        {"participant_id": "b", "scope_id": "x"},
                                        {"participant_id": "c", "scope_id": "y"}]}
        policy = {"scopes": [], "kernel_store_id": self.kernel.kernel_store_identity()}
        with self.kernel._transaction() as (conn, _):
            conn.execute("INSERT INTO kernel_revision_installs VALUES(?,?,?,?)", ("decision", "run", "barrier", encode_json({"decision": self.decision})))
            conn.execute("INSERT INTO kernel_projection_requirements VALUES(?,?,?,?)", ("run", 0, "decision", encode_json(self.decision["projection_requirements"])))
            conn.execute("INSERT INTO kernel_budget_policies VALUES(?,?,?)", ("run", 0, encode_json(policy)))

    def declaration(self, work, scopes):
        d = {"decision_id": "decision", "run_id": "run", "generation": 0,
             "execution_id": work.execution_id, "command": work.to_dict(), "scopes": scopes,
             "kernel_store_id": self.decision["kernel_store_id"],
             "orchestrator_store_id": self.decision["orchestrator_store_id"],
             "orchestrator_incarnation": self.decision["orchestrator_incarnation"]}
        self.claim["projection_declaration"] = d
        return d

    def receipt(self, participant, scope):
        d = self.decision
        receipt = {"decision_id": "decision", "run_id": "run", "source_revision": d["source_revision"],
                   "source_epoch": d["source_control_epoch"], "source_generation": d["source_generation"],
                   "target_generation": d["target_generation"], "migration_version": d["migration_version"],
                   "source_application_projection_version": d["source_application_projection_version"],
                   "application_projection_version": d["application_projection_version"],
                   "kernel_store_id": d["kernel_store_id"], "orchestrator_store_id": d["orchestrator_store_id"],
                   "orchestrator_incarnation": d["orchestrator_incarnation"],
                   "participant_id": participant, "scope_id": scope, "receipt_id": participant + "-receipt"}
        self.claim["projection_receipt"] = receipt
        return receipt

    def test_independent_scopes_and_all_participants(self):
        work_x, work_y, no_scope = (command("sdk-managed:" + value) for value in ("x", "y", "none"))
        with self.assertRaises(CASConflictError):
            self.kernel.submit_managed(work_x, run_id="run", generation=0)
        for work, scopes in ((work_x, ["x"]), (work_y, ["y"]), (no_scope, [])):
            d = self.declaration(work, scopes)
            self.assertEqual(self.kernel.declare_projection_dependencies("host", expected_declaration=d), d)
        self.kernel.submit_managed(no_scope, run_id="run", generation=0)
        receipt = self.receipt("c", "y")
        self.kernel.install_projection_receipt("host", expected_receipt=receipt)
        self.kernel.submit_managed(work_y, run_id="run", generation=0)
        with self.assertRaises(CASConflictError):
            self.kernel.submit_managed(work_x, run_id="run", generation=0)
        for participant in ("a", "b"):
            receipt = self.receipt(participant, "x")
            self.assertEqual(self.kernel.install_projection_receipt("host", expected_receipt=receipt), receipt)
            self.assertEqual(self.kernel.install_projection_receipt("host", expected_receipt=receipt), receipt)
        self.kernel.submit_managed(work_x, run_id="run", generation=0)
        self.assertEqual(self.kernel.claim("worker", execution_id=work_x.execution_id).execution_id, work_x.execution_id)

    def test_unauthenticated_or_wrong_revision_receipt_does_not_open_scope(self):
        work = command("sdk-managed:blocked")
        declaration = self.declaration(work, ["x"])
        with self.assertRaises(StorageIsolationError):
            self.kernel.declare_projection_dependencies("bad", expected_declaration=declaration)
        self.kernel.declare_projection_dependencies("host", expected_declaration=declaration)
        receipt = self.receipt("a", "x")
        with self.assertRaises(StorageIsolationError):
            self.kernel.install_projection_receipt("bad", expected_receipt=receipt)
        receipt["source_revision"] += 1
        with self.assertRaises(CASConflictError):
            self.kernel.install_projection_receipt("host", expected_receipt=receipt)
        with self.assertRaises(CASConflictError):
            self.kernel.submit_managed(work, run_id="run", generation=0)

    def test_declaration_cannot_be_replayed_for_another_store(self):
        work = command("sdk-managed:wrong-store")
        declaration = self.declaration(work, [])
        declaration["orchestrator_store_id"] = "other-store"
        with self.assertRaises(CASConflictError):
            self.kernel.declare_projection_dependencies("host", expected_declaration=declaration)
        with self.assertRaises(CASConflictError):
            self.kernel.submit_managed(work, run_id="run", generation=0)

    def test_scope_lookup_uses_run_generation_index(self):
        with self.kernel._transaction() as (connection, _):
            plan = connection.execute("EXPLAIN QUERY PLAN SELECT decision_id,requirements_json "
                "FROM kernel_projection_requirements WHERE run_id=? AND generation=?", ("run", 0)).fetchall()
        self.assertTrue(any("SEARCH" in row[3] and "INDEX" in row[3] for row in plan), plan)
