import json
from pathlib import Path
import tempfile
import time
import unittest

from dispatcher_sdk.orchestrator import Orchestrator, OrchestrationError, CommandConflict


class Kernel:
    def __init__(self):
        self.state, self.epoch, self.generation = "paused", 3, 0
        self.install_count = 0
        self.installed_receipt = None

    def kernel_store_identity(self):
        return "kernel"

    def get_run_control(self, run_id):
        return {"state": self.state, "control_epoch": self.epoch, "generation": self.generation}

    def install_revision_decision(self, credential, *, worker_credential, expected_decision):
        self.state, self.epoch, self.generation = "paused", 4, 1
        return {"kind": "paused_revision_install", "decision": expected_decision, "activation": "closed",
                "target_control_epoch": 4, "claims_used": 0, "max_claims": 1, "deadline_at": 9999999999}

    def install_projection_receipt(self, credential, *, expected_receipt):
        if credential != "kernel-receipt":
            raise OrchestrationError("Kernel receipt authority denied")
        self.install_count += 1
        self.installed_receipt = expected_receipt
        return expected_receipt


class Participant:
    def __init__(self):
        self.receipt = None
        self.calls = 0
        self.source = None
        self.target = None

    def inspect(self, binding):
        return self.receipt

    def apply(self, binding, source, target, context):
        self.calls += 1
        self.source, self.target = source, target
        self.receipt = {**binding, "receipt_id": "receipt-1"}


class ExternalProjectionFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "store.sqlite"
        self.participant = Participant()
        self.lease = {}
        self.kernel = Kernel()
        self.sdk = Orchestrator(self.path, self.kernel,
            control_verifier=lambda _: {"principal": "operator", "permissions": [("run", "commit_revision"), ("run", "install_revision")]},
            control_lease_verifier=lambda _: dict(self.lease),
            projection_verifier=self.verify_projection)
        with self.sdk._transaction() as c:
            identity = c.execute("SELECT store_id,incarnation FROM sdk_storage_identity").fetchone()
            c.execute("INSERT INTO sdk_runs VALUES('run',0,'{}')")
            c.execute("INSERT INTO sdk_run_items VALUES('run','root','application_state',?)", (json.dumps({"old": 1}),))
            c.execute("INSERT INTO sdk_managed_runs VALUES('run','request','unused','paused',3,0,1,9999999999,1,1)")
            c.execute("INSERT INTO sdk_control_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("decision", "run", "pause", 0, 1, 0, 1, 9999999999, identity[0], identity[1], "kernel",
                 "operator", None, "prepared", '{"claims_used":0}', "{}", "{}", "{}", None, 1, 1))
        self.lease.update(operation_id="decision", run_id="run", kernel_store_id="kernel", orchestrator_store_id=identity[0],
                          orchestrator_incarnation=identity[1], lease_id="lease", lease_fence=1,
                          expires_at=time.time() + 300, held=True, scope="resume_cancel_revoke_through_commit")
        self.arguments = dict(request_id="revision", credential="operator", expected_run_revision=0,
            expected_control_epoch=3, expected_generation=0, deployment={}, revision={"new": 2},
            migration_version="m1", application_projection_version="p2", migrate=lambda old, revision: revision,
            participant_requirements=[{"participant_id": "app", "scope_id": "A"}], source_application_projection_version="p1")

    def verify_projection(self, credential, descriptor):
        if credential != "projection":
            return {}
        if descriptor["phase"] == "apply_authorization":
            return {"apply_authorized": True, "atomic_source_version_cas": True, "fencing": True,
                    "apply_context": descriptor["apply_context"], "binding": descriptor["binding"],
                    "source_application_state": descriptor["source_application_state"],
                    "target_application_state": descriptor["target_application_state"], "expires_at": time.time() + 300}
        participant = descriptor["participant"]
        return {"durable": True, "retained": True, "receipt": participant.receipt,
                "source_application_state": participant.source, "target_application_state": participant.target}

    def seed_future_decision(self):
        self.sdk.commit_cross_store_revision("decision", **self.arguments)

    def reconcile(self):
        return self.sdk.reconcile_external_projection("decision", participant_id="app", scope_id="A", participant=self.participant,
            credential="operator", lease_credential="lease", projection_credential="projection")

    def test_receipt_replay_after_application_commit_and_install(self):
        self.seed_future_decision()
        def fail(stage):
            if stage == "after_external_projection_commit":
                raise RuntimeError("lost acknowledgement")
        self.sdk._failpoint = fail
        with self.assertRaisesRegex(RuntimeError, "lost acknowledgement"):
            self.reconcile()
        self.sdk = Orchestrator(self.path, self.kernel,
            control_verifier=lambda _: {"principal": "operator", "permissions": [("run", "commit_revision"), ("run", "install_revision")]},
            control_lease_verifier=lambda _: dict(self.lease),
            projection_verifier=self.verify_projection)
        receipt = self.reconcile()
        self.assertEqual(self.participant.calls, 1)
        self.assertEqual(self.participant.source, {"old": 1})
        self.assertEqual(self.participant.target, {"new": 2})
        self.assertEqual(receipt["target_generation"], 1)
        self.assertEqual(self.reconcile(), receipt)
        installed = self.sdk.install_cross_store_revision("decision", credential="operator", decision_credential="x", worker_credential="x")
        envelope = json.loads(installed["kernel_install_receipt"])["decision"]
        self.assertEqual(envelope["projection_requirements"], self.arguments["participant_requirements"])
        self.assertEqual(envelope["source_application_projection_version"], "p1")

    def test_active_revision_reconciles_and_delivers_after_lost_kernel_ack(self):
        self.seed_future_decision()
        installed = self.sdk.install_cross_store_revision("decision", credential="operator", decision_credential="x", worker_credential="x")
        self.assertIsNotNone(installed["kernel_install_receipt"])
        # Simulate separately verified Orchestrator install and resume receipts;
        # this test exercises receipt reconciliation, not resume itself.
        with self.sdk._transaction() as c:
            c.execute("UPDATE sdk_revision_decisions SET orchestrator_install_receipt='{}' WHERE operation_id='decision'")
            c.execute("UPDATE sdk_managed_runs SET control_state='active',control_epoch=5,generation=1 WHERE run_id='run'")
            local = {"operation_id": "resume", "run_id": "run", "generation": 1, "control_epoch": 5, "state": "active"}
            remote = {"decision": {"operation_id": "resume", "decision_id": "decision", "generation": 1, "target_control_epoch": 5}}
            c.execute("INSERT INTO sdk_revision_resumes VALUES(?,?,?,?,?,?)", ("resume", "decision", "{}", json.dumps(remote), json.dumps(local), 1))
        self.kernel.state, self.kernel.epoch, self.kernel.generation = "active", 5, 1
        receipt = self.reconcile()
        self.assertEqual(receipt["source_application_projection_version"], "p1")
        def deliver():
            return self.sdk.install_external_projection_receipt("decision", participant_id="app", scope_id="A",
                credential="operator", lease_credential="lease", receipt_credential="kernel-receipt")
        def fail(stage):
            if stage == "after_kernel_projection_receipt":
                raise RuntimeError("lost Kernel acknowledgement")
        self.sdk._failpoint = fail
        with self.assertRaisesRegex(RuntimeError, "lost Kernel acknowledgement"):
            deliver()
        self.sdk._failpoint = lambda _: None
        self.assertEqual(deliver(), receipt)
        self.assertEqual(self.kernel.installed_receipt, receipt)
        with self.assertRaisesRegex(OrchestrationError, "authority denied"):
            self.sdk.install_external_projection_receipt("decision", participant_id="app", scope_id="A",
                credential="operator", lease_credential="lease", receipt_credential="invalid")

    def test_source_version_is_required_before_migration(self):
        calls = []
        with self.assertRaises(OrchestrationError):
            self.sdk.commit_cross_store_revision("decision", **dict(self.arguments, source_application_projection_version=None,
                migrate=lambda *args: calls.append(args)))
        self.assertEqual(calls, [])
        with self.assertRaisesRegex(OrchestrationError, "requires participant"):
            self.sdk.commit_cross_store_revision("decision", **dict(self.arguments, external_projection=True,
                participant_requirements=[], source_application_projection_version=None))

    def test_later_control_epoch_fails_closed(self):
        self.seed_future_decision()
        installed = self.sdk.install_cross_store_revision("decision", credential="operator", decision_credential="x", worker_credential="x")
        with self.sdk._transaction() as c:
            c.execute("UPDATE sdk_revision_decisions SET orchestrator_install_receipt='{}' WHERE operation_id='decision'")
            c.execute("UPDATE sdk_managed_runs SET control_state='paused',control_epoch=6,generation=1 WHERE run_id='run'")
        self.kernel.state, self.kernel.epoch, self.kernel.generation = "paused", 6, 1
        with self.assertRaisesRegex(OrchestrationError, "control changed"):
            self.reconcile()
        self.assertEqual(self.participant.calls, 0)

    def test_missing_cas_or_fencing_authority_never_applies(self):
        self.seed_future_decision()
        prior = self.sdk.projection_verifier
        def verifier(credential, descriptor):
            claim = prior(credential, descriptor)
            if descriptor["phase"] == "apply_authorization":
                claim.pop("fencing")
            return claim
        self.sdk.projection_verifier = verifier
        with self.assertRaisesRegex(OrchestrationError, "authorize"):
            self.reconcile()
        self.assertEqual(self.participant.calls, 0)

    def test_unauthorized_projection_never_applies(self):
        self.seed_future_decision()
        self.sdk.projection_verifier = lambda credential, descriptor: {}
        with self.assertRaisesRegex(OrchestrationError, "authorize"):
            self.reconcile()
        self.assertEqual(self.participant.calls, 0)

    def test_expired_lease_during_inspect_never_applies(self):
        self.seed_future_decision()
        def inspect(_binding):
            self.lease["expires_at"] = time.time() - 1
            return None
        self.participant.inspect = inspect
        with self.assertRaisesRegex(OrchestrationError, "lease"):
            self.reconcile()
        self.assertEqual(self.participant.calls, 0)

    def test_duplicates_and_unattested_receipts_fail(self):
        duplicate = dict(self.arguments, participant_requirements=self.arguments["participant_requirements"] * 2)
        with self.assertRaisesRegex(OrchestrationError, "duplicate"):
            self.sdk.commit_cross_store_revision("decision", **duplicate)
        self.seed_future_decision()
        original_verifier = self.sdk.projection_verifier
        self.sdk.projection_verifier = lambda credential, descriptor: (original_verifier(credential, descriptor) if descriptor["phase"] == "apply_authorization" else {"durable": True, "retained": True, "receipt": descriptor["participant"].receipt})
        with self.assertRaisesRegex(OrchestrationError, "attest"):
            self.reconcile()
        with self.sdk._transaction() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM sdk_external_projection_receipts").fetchone()[0], 0)


class ExternalProjectionMigrationTests(unittest.TestCase):
    def test_exact_v5_copy_upgrade_and_source_preserved(self):
        import sqlite3
        from dispatcher_sdk.maintenance import maintenance_lease
        from dispatcher_sdk.orchestrator.store import SCHEMA_V5, execute_schema, initialize_storage_tracking
        from dispatcher_sdk.orchestrator.results import ResultsMixin
        from dispatcher_sdk.orchestrator.notifications import NotificationsMixin
        from dispatcher_sdk.storage_migration import upgrade_storage, _validate_v5, StorageMigrationError
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "v5.sqlite", Path(directory) / "v6.sqlite"
            with sqlite3.connect(source) as c:
                execute_schema(c, SCHEMA_V5)
                result = ResultsMixin()
                result.max_result_deliveries = 5
                result._init_results(c)
                NotificationsMixin._init_notifications(c)
                initialize_storage_tracking(c)
                c.execute("INSERT INTO sdk_storage_clock VALUES(1,0)")
                c.execute("INSERT INTO sdk_storage_identity VALUES(1,'store','incarnation',1)")
                c.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',5)")
                c.execute("INSERT INTO sdk_runs VALUES('historic',4,'{}')")
            with self.assertRaisesRegex(OrchestrationError, "schema version"):
                Orchestrator(source, Kernel())
            with maintenance_lease(source, "test", "upgrade") as lease:
                upgrade_storage(source, target, lease=lease)
            with sqlite3.connect(source) as c:
                self.assertEqual(c.execute("SELECT version FROM sdk_schema_meta").fetchone()[0], 5)
                self.assertEqual(c.execute("SELECT revision FROM sdk_runs WHERE run_id='historic'").fetchone()[0], 4)
            with sqlite3.connect(target) as c:
                self.assertEqual(c.execute("SELECT version FROM sdk_schema_meta").fetchone()[0], 6)
                self.assertEqual(c.execute("SELECT revision FROM sdk_runs WHERE run_id='historic'").fetchone()[0], 4)
                with self.assertRaises(StorageMigrationError):
                    _validate_v5(c)
            Orchestrator(target, Kernel())

    def test_v4_intermediate_upgrade_and_malformed_v5_rejection(self):
        import sqlite3
        from dispatcher_sdk.maintenance import maintenance_lease
        from dispatcher_sdk.orchestrator.store import SCHEMA_V4, SCHEMA_V5, execute_schema, initialize_storage_tracking
        from dispatcher_sdk.orchestrator.results import ResultsMixin
        from dispatcher_sdk.orchestrator.notifications import NotificationsMixin
        from dispatcher_sdk.storage_migration import upgrade_storage, StorageMigrationError
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for version, schema in ((4, SCHEMA_V4), (5, SCHEMA_V5)):
                source, target = root / f"v{version}.sqlite", root / f"v{version}-target.sqlite"
                with sqlite3.connect(source) as c:
                    execute_schema(c, schema)
                    result = ResultsMixin()
                    result.max_result_deliveries = 5
                    result._init_results(c)
                    NotificationsMixin._init_notifications(c)
                    initialize_storage_tracking(c)
                    c.execute("INSERT INTO sdk_storage_clock VALUES(1,0)")
                    c.execute("INSERT INTO sdk_storage_identity VALUES(1,'store','incarnation',1)")
                    c.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',?)", (version,))
                    if version == 5:
                        c.execute("CREATE TABLE sdk_unexpected (value TEXT)")
                with maintenance_lease(source, "test", "upgrade") as lease:
                    if version == 5:
                        with self.assertRaises(StorageMigrationError):
                            upgrade_storage(source, target, lease=lease)
                        self.assertFalse(target.exists())
                    else:
                        upgrade_storage(source, target, lease=lease)
                        with sqlite3.connect(target) as c:
                            self.assertEqual(c.execute("SELECT version FROM sdk_schema_meta").fetchone()[0], 6)

class RealKernelProjectionIntegrationTests(ExternalProjectionFoundationTests):
    def test_split_store_gate_receipt_recovery(self):
        from dispatcher_sdk.execution_kernel import SQLiteKernel, CASConflictError, ExecutionCommandV2, RetryPolicy
        from dispatcher_sdk.execution_kernel._sqlite_base import encode_json
        # A synthetic completed pause is the boundary of this test. Revision
        # commit, Kernel installation, receipt reconciliation and admission use
        # their public APIs against two independent SQLite stores.
        expiry = time.time() + 300
        claims = {}
        def verify(credential):
            base = {"principal": "worker", "expires_at": expiry, "permissions": [
                ("run", "kernel:install_revision"), ("run", "kernel:worker"),
                ("run", "kernel:declare_projection"), ("run", "kernel:install_projection"),
                ("run", "kernel:submit")], **claims}
            if credential == "worker":
                base.update(run_id="run", generation=1, control_epoch=claims.get("worker_epoch", 4))
            elif credential not in ("decision", "host"):
                raise ValueError("invalid host credential")
            return base
        path = Path(self.temp.name) / "kernel.sqlite"
        kernel = SQLiteKernel(path, authority_verifier=verify, worker_credential="worker")
        self.addCleanup(lambda: kernel.close())
        kernel.register_run_control("run", max_claims=1, deadline_at=9999999999)
        kid = kernel.kernel_store_identity()
        barrier = {"kind": "pause_barrier", "store_id": kid, "expected_epoch": 1, "claims_used": 0}
        with kernel._transaction() as (c, _):
            c.execute("UPDATE kernel_run_controls SET control_epoch=3 WHERE run_id='run'")
            c.execute("INSERT INTO kernel_run_authorities VALUES('run',0,1,'worker',?,NULL)", (expiry,))
            c.execute("INSERT INTO kernel_control_pause_receipts VALUES('decision','run',1,0,?)", (encode_json(barrier),))
            c.execute("INSERT INTO kernel_control_pause_pages VALUES('decision',0,0,?)", (encode_json({"capture_complete": True}),))
        self.kernel = kernel
        self.sdk.kernel = kernel
        self.lease["kernel_store_id"] = kid
        with self.sdk._transaction() as c:
            c.execute("UPDATE sdk_control_operations SET kernel_store_id=?,kernel_receipt=? WHERE operation_id='decision'", (kid, encode_json(barrier)))
        self.arguments["participant_requirements"] = [{"participant_id": "app-x", "scope_id": "x"}, {"participant_id": "app-y", "scope_id": "y"}]
        self.arguments["external_projection"] = True
        self.sdk.commit_cross_store_revision("decision", **self.arguments)
        claims["decision"] = {"decision_id": "decision", "operation_id": "decision", "barrier_operation_id": "decision", "run_id": "run",
            "orchestrator_store_id": self.lease["orchestrator_store_id"], "orchestrator_incarnation": self.lease["orchestrator_incarnation"],
            "kernel_store_id": kid, "source_revision": 0, "source_generation": 0, "source_control_epoch": 3, "target_generation": 1,
            "deployment": {}, "revision": {"new": 2}, "source_application_state": {"old": 1}, "target_application_state": {"new": 2},
            "content_pages": {}, "migration_version": "m1", "application_projection_version": "p2",
            "source_application_projection_version": "p1", "projection_requirements": self.arguments["participant_requirements"]}
        self.sdk.install_cross_store_revision("decision", credential="operator", decision_credential="decision", worker_credential="worker")
        # Seed an already completed global installation/resume. The resume
        # protocol itself is tested separately; here we test its receipt gate.
        active = {"operation_id": "resume", "run_id": "run", "generation": 1, "control_epoch": 5, "state": "active", "committed_at": time.time(),
                  "kernel_store_id": kid, "orchestrator_store_id": self.lease["orchestrator_store_id"], "orchestrator_incarnation": self.lease["orchestrator_incarnation"]}
        resume = {"decision": {"run_id": "run", "generation": 1, "target_control_epoch": 5, "lease_id": "lease", "lease_fence": 1,
                  "operation_id": "resume", "orchestrator_store_id": active["orchestrator_store_id"],
                  "orchestrator_incarnation": active["orchestrator_incarnation"], "kernel_store_id": kid}}
        with kernel._transaction() as (c, _):
            c.execute("UPDATE kernel_run_controls SET state='active',control_epoch=5 WHERE run_id='run'")
            c.execute("UPDATE kernel_run_authorities SET control_epoch=5 WHERE run_id='run'")
            c.execute("INSERT INTO kernel_resume_receipts VALUES('resume','run','decision','done',?)", (encode_json(resume),))
            c.execute("INSERT INTO kernel_budget_policies VALUES('run',1,?)", (encode_json({"scopes": [], "kernel_store_id": kid}),))
        with self.sdk._transaction() as c:
            c.execute("UPDATE sdk_revision_decisions SET orchestrator_install_receipt='{}' WHERE operation_id='decision'")
            c.execute("UPDATE sdk_managed_runs SET control_state='active',control_epoch=5,generation=1 WHERE run_id='run'")
            remote_resume = {"decision": {"operation_id": "resume", "decision_id": "decision", "generation": 1, "target_control_epoch": 5}}
            c.execute("INSERT INTO sdk_revision_resumes VALUES(?,?,?,?,?,?)", ("resume", "decision", "{}", json.dumps(remote_resume), json.dumps(active), 1))
        claims.update(worker_epoch=5, control_lease={"held": True, "lease_id": "lease", "lease_fence": 1, "expires_at": expiry},
            global_admission={"open": True, "operation_id": "resume", "orchestrator_store_id": active["orchestrator_store_id"],
                "orchestrator_incarnation": active["orchestrator_incarnation"], "kernel_store_id": kid, "orchestrator_receipt": active})
        def work(scope):
            execution_id = "sdk-managed:" + scope
            return ExecutionCommandV2(execution_id=execution_id, idempotency_key="key:" + execution_id, registry_revision="test",
                correlation_id="run", causation_id=None, handler_id="test", handler_contract_version=1,
                retry_policy=RetryPolicy(), timeout_seconds=10, payload={})
        x, y = work("x"), work("y")
        for item, scope in ((x, "x"), (y, "y")):
            claims["projection_declaration"] = {"decision_id": "decision", "run_id": "run", "generation": 1,
                "execution_id": item.execution_id, "command": item.to_dict(), "scopes": [scope], "kernel_store_id": kid,
                "orchestrator_store_id": active["orchestrator_store_id"], "orchestrator_incarnation": active["orchestrator_incarnation"]}
            kernel.declare_projection_dependencies("host", expected_declaration=claims["projection_declaration"])
        with self.assertRaises(CASConflictError):
            kernel.submit_managed(x, run_id="run", generation=1)
        def reconcile(participant, scope, adapter):
            return self.sdk.reconcile_external_projection("decision", participant_id=participant, scope_id=scope, participant=adapter,
                credential="operator", lease_credential="lease", projection_credential="projection")
        def deliver(participant, scope, receipt):
            claims["projection_receipt"] = receipt
            return self.sdk.install_external_projection_receipt("decision", participant_id=participant, scope_id=scope,
                credential="operator", lease_credential="lease", receipt_credential="host")
        app_y, app_x = Participant(), Participant()
        receipt_y = reconcile("app-y", "y", app_y)
        deliver("app-y", "y", receipt_y)
        kernel.submit_managed(y, run_id="run", generation=1)
        with self.assertRaises(CASConflictError):
            kernel.submit_managed(x, run_id="run", generation=1)
        self.sdk._failpoint = lambda stage: (_ for _ in ()).throw(RuntimeError("lost app ACK")) if stage == "after_external_projection_commit" else None
        with self.assertRaisesRegex(RuntimeError, "lost app ACK"):
            reconcile("app-x", "x", app_x)
        kernel.close()
        kernel = SQLiteKernel(path, authority_verifier=verify, worker_credential="worker")
        self.sdk = Orchestrator(self.path, kernel, control_verifier=lambda _: {"principal": "operator", "permissions": [("run", "install_revision")]},
            control_lease_verifier=lambda _: dict(self.lease), projection_verifier=self.verify_projection)
        receipt_x = reconcile("app-x", "x", app_x)
        self.assertEqual(app_x.calls, 1)
        deliver("app-x", "x", receipt_x)
        kernel.submit_managed(x, run_id="run", generation=1)
        kernel.close()
