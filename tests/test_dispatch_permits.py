"""Durable handoff facts for managed dispatches across interrupted sends."""
import json
import unittest

from test_managed_kernel_gate import ManagedKernelGateTests, command
from dispatcher_sdk.execution_kernel import ExecutionCommandV2
from dispatcher_sdk.orchestrator import CommandConflict, OrchestrationError, RevisionConflict


class DispatchPermitTests(ManagedKernelGateTests):
    def test_permit_reconciles_accepted_then_cancelled_after_claim(self):
        import time
        self._register("one")
        with self.sdk._transaction() as connection:
            connection.execute("UPDATE sdk_managed_runs SET control_state='active',control_epoch=1 WHERE run_id='one'")
            connection.execute("UPDATE kernel_run_controls SET state='active',control_epoch=1 WHERE run_id='one'")
            connection.execute("INSERT INTO sdk_managed_control_transitions VALUES('one',1,'active',0,'[]',NULL,?)", (time.time(),))
        row, intent = self._pending()
        self.assertEqual(self.sdk._acquire_dispatch_permit(row, intent), "new")
        self.kernel.submit_managed(command("one", "a"), run_id="one", generation=0)
        self.assertIsNotNone(self.kernel.claim("worker"))
        with self.sdk._transaction() as connection:
            connection.execute("UPDATE kernel_run_controls SET state='pausing' WHERE run_id='one'")
        current = self.kernel.get("sdk-managed:one:a")
        self.kernel.cancel(current.execution_id, expected_revision=current.revision, reason="stop")
        self.assertEqual(self.sdk.reconcile_dispatch_permits("one"), 1)
        with self.sdk._transaction() as connection:
            self.assertEqual(connection.execute("SELECT state FROM sdk_dispatch_permits WHERE sequence=?", (row["sequence"],)).fetchone()[0], "accepted")

    def test_fenced_pending_cancellation_lost_ack_and_restart(self):
        import time
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        from dispatcher_sdk.orchestrator import Orchestrator
        expiry = time.time() + 300
        self._register("one")
        with self.sdk._transaction() as connection:
            connection.execute("UPDATE sdk_managed_runs SET control_state='active',control_epoch=1 WHERE run_id='one'")
            connection.execute("INSERT INTO sdk_managed_control_transitions VALUES('one',1,'active',0,'[]',NULL,?)", (time.time(),))
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity").fetchone()
        path = self.path.parent / "cancel-participant.sqlite"
        def kernel_verify(credential):
            return {"principal": "manager", "expires_at": expiry, "permissions": [("one", "kernel:cancel")]}
        participant = SQLiteKernel(path, authority_verifier=kernel_verify, worker_credential="manager")
        self.addCleanup(participant.close)
        participant.register_run_control("one", max_claims=1, deadline_at=self.deadline)
        with participant._transaction() as (connection, _):
            connection.execute("UPDATE kernel_run_controls SET state='active',control_epoch=1 WHERE run_id='one'")
        kid = participant.kernel_store_identity()
        lease = {"operation_id": "cancel-test", "run_id": "one", "kernel_store_id": kid,
                 "orchestrator_store_id": identity[0], "orchestrator_incarnation": identity[1],
                 "lease_id": "lease", "lease_fence": 1, "expires_at": expiry, "held": True,
                 "scope": "resume_cancel_revoke_through_commit"}
        def verify(credential):
            return {"principal": "operator", "permissions": [("one", "cancel")]}
        def open_sdk():
            return Orchestrator(self.path, participant, control_verifier=verify, control_lease_verifier=lambda _: dict(lease))
        sdk = open_sdk()
        sdk.fence_cross_store_cancellation("one", operation_id="cancel-test", credential="token", lease_credential="lease")
        sdk.apply_fenced_cancellation("cancel-test", operation_id="cancel-action", expected_revision=0,
            operations=[{"kind": "cancel", "task_id": "a", "reason": "stop"}], credential="token", lease_credential="lease")
        def fail(stage):
            if stage == "after_kernel_fenced_cancellation":
                raise RuntimeError("lost receipt")
        sdk._failpoint = fail
        with self.assertRaisesRegex(RuntimeError, "lost receipt"):
            sdk.reconcile_fenced_cancellation("cancel-test", action_operation_id="cancel-action", ordinal=0,
                receipt_operation_id="cancel-receipt", credential="token", lease_credential="lease")
        with sdk._transaction() as connection:
            dispatch = connection.execute("SELECT sequence,payload FROM sdk_outbox WHERE run_id='one' AND command_id='managed-create'").fetchone()
            connection.execute("INSERT INTO sdk_dispatch_permits VALUES(?,?,?,?,?,?,'unknown',?,?)",
                (dispatch[0], "one", json.loads(dispatch[1])["execution_id"], 0, 1, kid, time.time(), time.time()))
        self.assertEqual(sdk.reconcile_dispatch_permits("one"), 0)
        with sdk._transaction() as connection:
            self.assertEqual(connection.execute("SELECT state FROM sdk_dispatch_permits WHERE sequence=?", (dispatch[0],)).fetchone()[0], "unknown")
            connection.execute("UPDATE sdk_dispatch_permits SET generation=1 WHERE sequence=?", (dispatch[0],))
        with self.assertRaises(OrchestrationError):
            sdk.reconcile_fenced_cancellation("cancel-test", action_operation_id="cancel-action", ordinal=0,
                receipt_operation_id="cancel-receipt", credential="token", lease_credential="lease")
        with sdk._transaction() as connection:
            connection.execute("UPDATE sdk_dispatch_permits SET generation=0,state='accepted' WHERE sequence=?", (dispatch[0],))
        participant.close()
        participant = SQLiteKernel(path, authority_verifier=kernel_verify, worker_credential="manager")
        self.addCleanup(participant.close)
        sdk = open_sdk()
        result = sdk.reconcile_fenced_cancellation("cancel-test", action_operation_id="cancel-action", ordinal=0,
            receipt_operation_id="cancel-receipt", credential="token", lease_credential="lease")
        self.assertEqual(result["run_projection"], "cancelled")
        with sdk._transaction() as connection:
            revision = connection.execute("SELECT revision FROM sdk_runs WHERE run_id='one'").fetchone()[0]
        finished = sdk.apply_fenced_cancellation("cancel-test", operation_id="cancel-finish", expected_revision=revision,
            operations=[{"kind": "finish", "state": "cancelled"}], credential="token", lease_credential="lease")
        self.assertEqual(finished["state"], "cancelled")

    def _pending(self):
        connection = self.sdk._connect()
        try:
            row = connection.execute("SELECT sequence,run_id,payload FROM sdk_outbox WHERE delivered=0").fetchone()
            return dict(row), json.loads(row["payload"])
        finally:
            connection.close()

    def test_unknown_dispatch_blocks_pause_after_restart(self):
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        row, intent = self._pending()
        self.assertTrue(self.sdk._acquire_dispatch_permit(row, intent))
        self.sdk._request_managed_control("one", request_id="pause", kind="pause", mode="interrupt",
            expected_run_revision=0, expected_control_epoch=1)
        self.assertEqual(self.sdk.reconcile_dispatch_permits("one"), 0)
        with self.assertRaisesRegex(OrchestrationError, "unresolved dispatch"):
            self.sdk._settle_managed_pause("one", expected_control_epoch=2)
        self.assertFalse(self.sdk._acquire_dispatch_permit(row, intent))

    def test_receipt_after_lost_ack_is_reconciled_without_new_execution(self):
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        row, intent = self._pending()
        self.assertTrue(self.sdk._acquire_dispatch_permit(row, intent))
        self.kernel.submit_managed(ExecutionCommandV2.from_dict(intent["command"]),
                                   run_id="one", generation=0)
        self.assertEqual(self.sdk.reconcile_dispatch_permits("one"), 1)
        self.assertEqual(self.sdk.flush(), 1)

class CrossStorePauseTests(ManagedKernelGateTests):
    def setUp(self):
        super().setUp()
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
        self.sdk.control_authorizer = ControlAuthorizer(self.sdk, lambda credential: {
            "principal": "operator", "permissions": [("one", "pause")]})

    def test_cross_store_selective_drain_persists_and_replays(self):
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume-drain", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        deadline = self.deadline
        class Participant:
            db_path = "/tmp/independent-drain-store"
            def kernel_store_identity(self):
                return "drain-kernel"
            def prepare_control_pause(self, operation_id, run_id, **kwargs):
                self.received = kwargs
                return {"store_id": "drain-kernel", "operation_id": operation_id,
                    "run_id": run_id, "expected_epoch": kwargs["expected_epoch"],
                    "control_epoch": kwargs["expected_epoch"] + 1,
                    "generation": kwargs["generation"], "max_claims": 1,
                    "deadline_at": deadline, "drain_execution_ids": kwargs["drain_execution_ids"]}
        participant = Participant()
        self.sdk.kernel = participant
        args = dict(operation_id="drain-op", expected_run_revision=0,
                    expected_control_epoch=1, credential="token")
        self.sdk.begin_cross_store_pause("one", drain_execution_ids=["b", "a"], **args)
        self.sdk.begin_cross_store_pause("one", drain_execution_ids=["a", "b"], **args)
        with self.assertRaises(CommandConflict):
            self.sdk.begin_cross_store_pause("one", drain_execution_ids=["a"], **args)
        self.sdk.advance_cross_store_pause("drain-op", credential="token")
        self.assertEqual(participant.received["drain_execution_ids"], ["a", "b"])
        self.assertTrue(participant.received["drain_orchestrator_store_id"])
        self.assertTrue(participant.received["drain_orchestrator_incarnation"])

    def test_selective_drain_real_split_restart(self):
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        from dispatcher_sdk.orchestrator import Orchestrator
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume-drain-real", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        path = self.path.parent / "drain-kernel.sqlite"
        participant = SQLiteKernel(path)
        participant.register_run_control("one", max_claims=1, deadline_at=self.deadline)
        participant.set_run_control("one", expected_epoch=0, state="active", generation=0)
        work = command("one", "a")
        participant.submit_managed(work, run_id="one", generation=0)
        self.sdk.kernel = participant
        args = dict(operation_id="drain-real", expected_run_revision=0,
                    expected_control_epoch=1, credential="token", drain_execution_ids=[work.execution_id])
        self.sdk.begin_cross_store_pause("one", **args)
        receipt = self.sdk.advance_cross_store_pause("drain-real", credential="token")
        self.assertEqual(json.loads(receipt["kernel_receipt"])["drain_execution_ids"], [work.execution_id])
        participant.close()
        participant = SQLiteKernel(path)
        self.addCleanup(participant.close)
        restarted = Orchestrator(self.path, participant, control_verifier=lambda credential: {
            "principal": "operator", "permissions": [("one", "pause")]})
        self.assertEqual(restarted.begin_cross_store_pause("one", **args)["operation_id"], "drain-real")
        self.assertEqual(restarted.advance_cross_store_pause("drain-real", credential="token")["kernel_receipt"], receipt["kernel_receipt"])
        completed = restarted.complete_cross_store_pause_participant("drain-real", credential="token")
        self.assertEqual(json.loads(completed["kernel_pause_receipt"])["kind"], "local_paused")

    def test_protected_selective_drain_and_cancel_fence(self):
        import time
        from dispatcher_sdk.execution_kernel import SQLiteKernel, CASConflictError
        from dispatcher_sdk.execution_kernel._sqlite_execution import encode_json
        self._register("one")
        self.sdk._request_managed_control("one", request_id="protected-resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        expiry = time.time() + 300
        proof, drain = {}, {}
        def verifier(credential):
            if credential == "manager":
                return {"principal": "manager", "expires_at": expiry, "drain_pause": dict(proof),
                    "permissions": [("one", "kernel:" + x) for x in ("manage_authority", "pause", "cancel")]}
            return {"principal": "worker", "expires_at": expiry, "run_id": "one", "generation": 0,
                "control_epoch": 1, "permissions": [("one", "kernel:" + x) for x in ("worker", "claim", "start", "work", "drain")],
                "drain_admission": dict(drain)}
        path = self.path.parent / "protected-drain.sqlite"
        participant = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
        participant.register_run_control("one", max_claims=1, deadline_at=self.deadline)
        with participant._transaction() as (db, timestamp):
            db.execute("UPDATE kernel_run_controls SET control_epoch=1 WHERE run_id='one'")
        participant.protect_run_authority("one", generation=0, expected_epoch=1, worker_credential="worker")
        selected, other = command("one", "a"), command("one", "b")
        with participant._transaction() as (db, timestamp):
            db.execute("UPDATE kernel_run_controls SET state='active',control_epoch=1 WHERE run_id='one'")
            for work in (selected, other):
                db.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,0)", (work.execution_id, "one", 0))
                participant._submit_in_transaction(work, encode_json(work.to_dict()), db, timestamp)
        self.sdk.kernel = participant
        operation = self.sdk.begin_cross_store_pause("one", operation_id="protected-pause",
            expected_run_revision=0, expected_control_epoch=1, credential="token", drain_execution_ids=[selected.execution_id])
        proof.update(operation_id="protected-pause", run_id="one", generation=0, control_epoch=2,
            kernel_store_id=operation["kernel_store_id"], orchestrator_store_id=operation["orchestrator_store_id"],
            orchestrator_incarnation=operation["orchestrator_incarnation"], drain_execution_ids=[selected.execution_id])
        result = self.sdk.advance_cross_store_pause("protected-pause", credential="token")
        self.assertEqual(self.sdk.advance_cross_store_pause("protected-pause", credential="token")["kernel_receipt"], result["kernel_receipt"])
        drain.update({key: value for key, value in proof.items() if key != "drain_execution_ids"},
                     allowed=True, execution_id=selected.execution_id, expires_at=expiry)
        participant.close()
        worker = SQLiteKernel(path, authority_verifier=verifier, worker_credential="worker")
        lease = worker.start(worker.claim("worker"))
        self.assertEqual(lease.execution_id, selected.execution_id)
        self.assertEqual(worker.get(other.execution_id).state, "queued")
        self.assertIsNone(worker.claim("worker"))
        worker.close()
        manager = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
        manager.fence_cancelled_run("cancel-drain", "one", expected_epoch=2, generation=0)
        manager.close()
        worker = SQLiteKernel(path, authority_verifier=verifier, worker_credential="worker")
        self.addCleanup(worker.close)
        with self.assertRaises(CASConflictError):
            worker.verify(lease)
        self.assertEqual(worker.get(other.execution_id).state, "queued")

    def test_streamed_revision_real_coordinator_and_kernel(self):
        import time
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        from dispatcher_sdk.orchestrator import Orchestrator
        from dispatcher_sdk.orchestrator.projection_storage import ProjectionStorage
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
        expiry = time.time() + 300
        page, envelope, claim, budget_policy = {}, {}, {}, {}
        def kernel_verify(credential):
            if credential == "manager":
                return {"principal": "manager", "expires_at": expiry,
                    "permissions": [("one", "kernel:" + p) for p in ("manage_authority", "pause", "control")]}
            if credential == "page":
                return {"principal": "manager", "expires_at": expiry, "permissions": [("one", "kernel:stage_revision")], "revision_page": dict(page)}
            if credential == "decision":
                return {"principal": "manager", "expires_at": expiry, "permissions": [("one", "kernel:install_revision")], "decision": dict(envelope)}
            if credential == "budget":
                return {"principal": "manager", "expires_at": expiry, "permissions": [("one", "kernel:manage_budget")], "budget_policy": dict(budget_policy)}
            generation, epoch = (0, 0) if credential == "old" else (1, 4)
            return {"principal": credential, "expires_at": expiry, "permissions": [("one", "kernel:worker")],
                    "run_id": "one", "generation": generation, "control_epoch": epoch}
        def control_verify(credential):
            return {"principal": "operator", "permissions": [("one", p) for p in
                ("pause", "commit_revision", "install_revision", "stage_revision_content")]}
        self.sdk.control_authorizer = ControlAuthorizer(self.sdk, control_verify)
        self.sdk.register_managed_run("one", request_id="create", definition={}, task_commands=[], max_claims=1, deadline_at=self.deadline)
        self.sdk._request_managed_control("one", request_id="resume", kind="resume", expected_run_revision=0, expected_control_epoch=0)
        path = self.path.parent / "stream-kernel.sqlite"
        participant = SQLiteKernel(path, authority_verifier=kernel_verify, worker_credential="manager")
        participant.register_run_control("one", max_claims=1, deadline_at=self.deadline)
        participant.protect_run_authority("one", generation=0, expected_epoch=0, worker_credential="old")
        with participant._transaction() as (db, timestamp):
            db.execute("UPDATE kernel_run_controls SET state='active',control_epoch=1 WHERE run_id='one'")
            db.execute("UPDATE kernel_run_authorities SET control_epoch=1 WHERE run_id='one'")
        self.sdk.kernel = participant
        op = "stream-pause"
        operation = self.sdk.begin_cross_store_pause("one", operation_id=op, expected_run_revision=0, expected_control_epoch=1, credential="c")
        self.sdk.advance_cross_store_pause(op, credential="c")
        self.sdk.complete_cross_store_pause_participant(op, credential="c")
        while not self.sdk.capture_cross_store_pause_page(op, credential="c")["capture_complete"]:
            pass
        self.sdk.prepare_cross_store_pause(op, credential="c")
        self.sdk.finalize_cross_store_pause(op, credential="c")
        expected = {"operation_id": op, "run_id": "one", "kernel_store_id": operation["kernel_store_id"],
                    "orchestrator_store_id": operation["orchestrator_store_id"], "orchestrator_incarnation": operation["orchestrator_incarnation"]}
        lease = {**expected, "lease_id": "lease", "lease_fence": 1, "expires_at": expiry, "held": True,
                 "scope": "resume_cancel_revoke_through_commit"}
        self.sdk.control_lease_verifier = lambda credential: dict(lease)
        self.sdk.projection_verifier = lambda credential, storage: {"retained_immutable": True, "valid_json": True, "decision": dict(claim)}
        storage = ProjectionStorage(self.path.parent / "projections.sqlite")
        pointers = []
        for kind, text in (("source_application_state", "null"), ("target_application_state", '{"x":1}')):
            binding = {"kind": kind}
            storage.create(kind, total_bytes=len(text.encode()), binding=binding)
            storage.append(kind, sequence=0, data=text.encode(), complete=True)
            pointers.append({"stream_id": kind, "binding": binding, "total_bytes": len(text.encode()), **storage.identity()})
            page.clear()
            page.update(**expected, decision_id=op, barrier_operation_id=op, source_generation=0, content_kind=kind,
                page_seq=0, total_bytes=len(text.encode()), chunk=text, complete=True, lease_id="lease", lease_fence=1,
                lease_expires_at=expiry, lease_held=True)
            self.sdk.stage_revision_content_page(page, credential="c", page_credential="page")
        source, target = pointers
        mappings = {kind: {"operation_id": op, "total_bytes": pointer["total_bytes"], "lease_id": "lease", "lease_fence": 1}
                    for kind, pointer in (("source_application_state", source), ("target_application_state", target))}
        declaration = {"stream_version": 1, "deployment": {}, "revision": {}, "migration_version": "m",
            "application_projection_version": "p", "source_pointer": source, "target_pointer": target, "content_pages": mappings}
        claim.update(**expected, source_revision=0, source_epoch=3, source_generation=0, declaration=declaration, lease_id="lease", lease_fence=1)
        self.sdk.commit_streamed_revision(op, request_id="stream", expected_revision=0, expected_epoch=3, expected_generation=0,
            deployment={}, revision={}, migration_version="m", projection_version="p", source_pointer=source, target_pointer=target,
            storage=storage, credential="c", lease_credential="l", projection_credential="p")
        envelope.update(decision_id=op, operation_id=op, barrier_operation_id=op, run_id="one", kernel_store_id=expected["kernel_store_id"],
            orchestrator_store_id=expected["orchestrator_store_id"], orchestrator_incarnation=expected["orchestrator_incarnation"],
            source_revision=0, source_generation=0, source_control_epoch=3, target_generation=1, deployment={}, revision={},
            source_application_state=None, target_application_state=None, content_pages=mappings, migration_version="m", application_projection_version="p")
        self.sdk.install_cross_store_revision(op, credential="c", decision_credential="decision", worker_credential="next")
        participant.close()
        participant = SQLiteKernel(path, authority_verifier=kernel_verify, worker_credential="manager")
        self.addCleanup(participant.close)
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify,
            control_lease_verifier=lambda credential: dict(lease), projection_verifier=self.sdk.projection_verifier)
        installed = restarted.install_streamed_projection(op, storage=storage, credential="c", projection_credential="p", lease_credential="l")
        self.assertEqual(restarted.get_run("one")["application_state"], {"x": 1})
        self.assertEqual(restarted.install_streamed_projection(op, storage=storage, credential="c", projection_credential="p", lease_credential="l")["orchestrator_install_receipt"], installed["orchestrator_install_receipt"])
        budget_policy.update(policy_id="policy", decision_id=op, run_id="one", generation=1,
            kernel_store_id=expected["kernel_store_id"], orchestrator_store_id=expected["orchestrator_store_id"],
            orchestrator_incarnation=expected["orchestrator_incarnation"], scopes=[])
        def lose_budget_ack(stage):
            if stage == "after_kernel_budget_policy":
                raise RuntimeError("lost budget acknowledgement")
        restarted._failpoint = lose_budget_ack
        with self.assertRaisesRegex(RuntimeError, "lost budget"):
            restarted.install_cross_store_budget_policy(op, policy=budget_policy, credential="c", lease_credential="l", policy_credential="budget")
        restarted._failpoint = lambda stage: None
        policy_result = restarted.install_cross_store_budget_policy(op, policy=budget_policy, credential="c", lease_credential="l", policy_credential="budget")
        self.assertEqual(policy_result["kernel_receipt"], budget_policy)

    def test_bounded_projection_stream_reads_reference_nodes(self):
        from dispatcher_sdk.orchestrator.projection_stream import iter_application_projection
        self.sdk.create_run("one", command_id="create")
        value = "a" * 40000
        with self.sdk._transaction() as connection:
            for key in ("first", "second"):
                connection.execute("INSERT INTO sdk_content_objects VALUES(?,?,?)",
                                   (key, json.dumps(["string", value]), len(value) + 2))
            root = ["list", [["ref", "first", len(value) + 2], ["ref", "second", len(value) + 2]]]
            connection.execute("UPDATE sdk_run_items SET value=? WHERE run_id='one' AND section='root' AND item_key='application_state'",
                               ("sdk-content-v1:" + json.dumps(root),))
        fragments = list(iter_application_projection(self.sdk, "one", expected_revision=0, max_node_bytes=65536))
        self.assertEqual(json.loads("".join(fragments)), [value, value])
        with self.assertRaisesRegex(OrchestrationError, "node budget"):
            list(iter_application_projection(self.sdk, "one", expected_revision=0, max_node_bytes=1024))

    def test_control_lease_requires_exact_scope_and_monotonic_fence(self):
        from dispatcher_sdk.orchestrator.control_lease import check_control_lease, observe_control_clock
        claim = {"operation_id": "resume", "run_id": "one", "kernel_store_id": "kernel",
                 "orchestrator_store_id": "store", "orchestrator_incarnation": "incarnation",
                 "lease_id": "lease", "lease_fence": 3, "expires_at": self.deadline,
                 "held": True, "scope": "resume_cancel_revoke_through_commit"}
        expected = {key: claim[key] for key in ("operation_id", "run_id", "kernel_store_id",
                    "orchestrator_store_id", "orchestrator_incarnation")}
        self.sdk.control_lease_verifier = lambda credential: dict(claim)
        observe_control_clock(self.sdk)
        with self.sdk._transaction() as connection:
            self.assertEqual(check_control_lease(self.sdk, connection, "credential", expected)["lease_fence"], 3)
        claim["lease_fence"] = 2
        with self.sdk._transaction() as connection:
            with self.assertRaises(OrchestrationError):
                check_control_lease(self.sdk, connection, "credential", expected)
        claim["scope"] = "resume_cancel_revoke_through_commit"
        claim["lease_fence"] = 4
        claim["expires_at"] = self.deadline + 50
        self.sdk.clock = lambda: self.deadline + 100
        observe_control_clock(self.sdk)
        with self.sdk._transaction() as connection:
            with self.assertRaises(OrchestrationError):
                check_control_lease(self.sdk, connection, "credential", expected)
        self.sdk.clock = lambda: self.deadline + 20
        with self.sdk._transaction() as connection:
            with self.assertRaises(OrchestrationError):
                check_control_lease(self.sdk, connection, "credential", expected)
        # Observe a valid later instant, then roll the clock back.
        self.sdk.clock = lambda: self.deadline + 100
        claim["expires_at"] = self.deadline + 200
        with self.sdk._transaction() as connection:
            check_control_lease(self.sdk, connection, "credential", expected)
        claim["expires_at"] = self.deadline + 50
        self.sdk.clock = lambda: self.deadline + 20
        with self.sdk._transaction() as connection:
            with self.assertRaises(OrchestrationError):
                check_control_lease(self.sdk, connection, "credential", expected)
        self.sdk.clock = lambda: float("nan")
        with self.sdk._transaction() as connection:
            with self.assertRaises(OrchestrationError):
                check_control_lease(self.sdk, connection, "credential", expected)
        claim["lease_fence"] = 4
        claim["scope"] = "resume_only"
        with self.sdk._transaction() as connection:
            with self.assertRaises(OrchestrationError):
                check_control_lease(self.sdk, connection, "credential", expected)

    def test_legacy_adoption_pages_survive_lost_ack_and_require_live_lease(self):
        import time
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
        from dispatcher_sdk.orchestrator import Orchestrator
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
        expiry = time.time() + 300
        manifest = {}
        held = [True]
        def kernel_verify(credential):
            if credential == "adoption" and held[0]:
                return {"principal": "host", "expires_at": expiry,
                        "permissions": [("one", "kernel:import_legacy")], "adoption": dict(manifest)}
            if credential == "worker":
                return {"principal": "worker", "expires_at": expiry, "permissions": [("one", "kernel:worker")],
                        "run_id": "one", "generation": 0, "control_epoch": 0}
            raise ValueError("host isolation unavailable")
        def control_verify(credential):
            return {"principal": "operator", "permissions": [("one", "adopt_legacy")]}
        self.sdk.create_run("one", command_id="create")
        self.sdk.control_authorizer = ControlAuthorizer(self.sdk, control_verify)
        participant = SQLiteKernel(self.path.parent / "legacy-kernel.sqlite", authority_verifier=kernel_verify)
        self.addCleanup(participant.close)
        self.sdk.kernel = participant
        with self.sdk._transaction() as connection:
            identity = connection.execute("SELECT store_id,incarnation FROM sdk_storage_identity WHERE singleton=1").fetchone()
        manifest.update(operation_id="adopt-one", run_id="one", kernel_store_id=participant.kernel_store_identity(),
            orchestrator_store_id=identity[0], orchestrator_incarnation=identity[1], generation=0,
            membership=[{"execution_id": "plain:one:a", "status": "pending", "command": command("one", "a", managed=False).to_dict()}], membership_source="host-source",
            membership_complete=False, page_seq=0, claims_used=3, claims_source="host-budget", max_claims=7,
            deadline_at=self.deadline, isolation_lease_id="lease", isolation_expires_at=expiry, isolation_held=True)
        manifest["membership"][0]["command"]["payload"]["test"] = 1
        arguments = dict(expected_run_revision=0, credential="token", adoption_credential="adoption", worker_credential="worker")
        with self.assertRaisesRegex(OrchestrationError, "bounded adoption page"):
            self.sdk.adopt_legacy_page(dict(manifest, membership_source="x" * (512 * 1024)), **arguments)
        with self.assertRaisesRegex(OrchestrationError, "ordered and nonempty"):
            self.sdk.adopt_legacy_page(dict(manifest, membership=[]), **arguments)
        with self.assertRaisesRegex(OrchestrationError, "requires its command"):
            self.sdk.adopt_legacy_page(dict(manifest, membership=[{"execution_id": "a", "status": "pending"}]), **arguments)
        with self.assertRaisesRegex(OrchestrationError, "identity exceeds"):
            self.sdk.adopt_legacy_page(dict(manifest, membership=[{"execution_id": "x" * 4097, "status": "accepted"}]), **arguments)
        with self.sdk._transaction() as connection:
            self.assertIsNone(connection.execute("SELECT run_id FROM sdk_managed_runs WHERE run_id='one'").fetchone())
        def lost_ack(stage):
            if stage == "after_kernel_legacy_import":
                raise RuntimeError("lost adoption acknowledgement")
        self.sdk._failpoint = lost_ack
        with self.assertRaisesRegex(RuntimeError, "lost adoption"):
            self.sdk.adopt_legacy_page(manifest, **arguments)
        self.assertEqual(self.sdk.get_managed_control("one")["control_state"], "paused")
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify)
        held[0] = False
        with self.assertRaises(StorageIsolationError):
            restarted.adopt_legacy_page(manifest, **arguments)
        held[0] = True
        manifest["isolation_expires_at"] = expiry + 60
        self.assertEqual(restarted.adopt_legacy_page(manifest, **arguments)["phase"], "staging")
        import copy
        import threading
        page_zero = copy.deepcopy(manifest)
        changed = copy.deepcopy(manifest)
        changed["membership"][0]["command"]["payload"]["test"] = True
        with self.assertRaises(OrchestrationError):
            restarted.adopt_legacy_page(changed, **arguments)
        entered, release = threading.Event(), threading.Event()
        late = Orchestrator(self.path, participant, control_verifier=control_verify)
        def delay(stage):
            if stage == "after_kernel_legacy_import":
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("late page timed out")
        late._failpoint = delay
        outcomes = []
        def replay_earlier():
            try:
                outcomes.append(late.adopt_legacy_page(page_zero, **arguments))
            except Exception as exc:
                outcomes.append(exc)
        thread = threading.Thread(target=replay_earlier)
        thread.start()
        self.assertTrue(entered.wait(5))
        manifest.update(page_seq=1, membership=[{"execution_id": "plain:one:b", "status": "pending", "command": command("one", "b", managed=False).to_dict()}], membership_complete=True)
        final = restarted.adopt_legacy_page(manifest, **arguments)
        self.assertEqual((final["phase"], final["receipt"]["activation"]), ("paused", "closed"))
        release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcomes[0]["phase"], "paused")
        manifest.clear()
        manifest.update(page_zero)
        again = Orchestrator(self.path, participant, control_verifier=control_verify)
        self.assertEqual(again.adopt_legacy_page(page_zero, **arguments)["phase"], "paused")
        control = participant.get_run_control("one")
        self.assertEqual((control["state"], control["claims_used"], control["max_claims"], control["deadline_at"]),
                         ("paused", 3, 7, self.deadline))

    def test_revision_install_split_store_lost_ack_and_mismatch(self):
        import time
        from dispatcher_sdk.execution_kernel import SQLiteKernel, CASConflictError
        from dispatcher_sdk.orchestrator import Orchestrator
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer

        expiry = time.time() + 300
        envelope = {}
        content_page = {}
        activation = {}
        resume_decision = {}
        budget_policy = {}
        budget_declaration, budget_proof = {}, {}
        global_open = [False]
        final_receipt = {}
        def kernel_verify(credential):
            if credential == "manager":
                return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("one", "kernel:" + p) for p in ("manage_authority", "pause", "control", "cancel")]}
            if credential == "decision":
                return {"principal": "manager", "expires_at": expiry,
                        "permissions": [("one", "kernel:install_revision")], "decision": dict(envelope)}
            if credential == "page":
                return {"principal": "manager", "expires_at": expiry,
                        "permissions": [("one", "kernel:stage_revision")], "revision_page": dict(content_page)}
            if credential == "activation":
                return {"principal": "manager", "expires_at": expiry,
                        "permissions": [("one", "kernel:activate_revision")], "activation": dict(activation)}
            if credential == "resume":
                return {"principal": "manager", "expires_at": expiry,
                        "permissions": [("one", "kernel:resume")], "resume": dict(resume_decision)}
            if credential == "budget":
                return {"principal": "manager", "expires_at": expiry,
                        "permissions": [("one", "kernel:manage_budget"), ("one", "kernel:declare_budget")],
                        "budget_policy": dict(budget_policy), "budget_declaration": dict(budget_declaration)}
            if credential in ("old", "next", "resumed"):
                generation, epoch = (0, 0) if credential == "old" else ((1, 4) if credential == "next" else (1, 5))
                result = {"principal": credential, "expires_at": expiry, "permissions": [("one", "kernel:worker"), ("one", "kernel:claim"), ("one", "kernel:submit"), ("one", "kernel:budget")],
                          "run_id": "one", "generation": generation, "control_epoch": epoch}
                if credential == "resumed":
                    result["budget_admission"] = dict(budget_proof)
                if credential == "resumed" and global_open[0]:
                    result["control_lease"] = {"held": True, "lease_id": "host-lease", "lease_fence": 9, "expires_at": expiry}
                    result["global_admission"] = {"open": True, "operation_id": "resume-one",
                        "kernel_store_id": operation["kernel_store_id"],
                        "orchestrator_store_id": operation["orchestrator_store_id"], "orchestrator_incarnation": operation["orchestrator_incarnation"],
                        "orchestrator_receipt": dict(final_receipt)}
                return result
            raise ValueError("invalid credential")
        def control_verify(credential):
            return {"principal": "operator", "permissions": [("one", p) for p in
                    ("pause", "commit_revision", "install_revision", "stage_revision_content", "activate_revision", "resume", "cancel")]}
        self.sdk.control_authorizer = ControlAuthorizer(self.sdk, control_verify)
        self.sdk.register_managed_run("one", request_id="create", definition={}, task_commands=[],
                                      max_claims=1, deadline_at=self.deadline)
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
                                         expected_run_revision=0, expected_control_epoch=0)
        path = self.path.parent / "revision-kernel.sqlite"
        participant = SQLiteKernel(path, authority_verifier=kernel_verify, worker_credential="manager")
        self.addCleanup(participant.close)
        participant.register_run_control("one", max_claims=1, deadline_at=self.deadline)
        participant.protect_run_authority("one", generation=0, expected_epoch=0, worker_credential="old")
        # Model an already active protected Run; public activation remains closed.
        with participant._transaction() as (connection, _):
            connection.execute("UPDATE kernel_run_controls SET state='active',control_epoch=1 WHERE run_id='one'")
            connection.execute("UPDATE kernel_run_authorities SET control_epoch=1 WHERE run_id='one'")
        self.sdk.kernel = participant
        op = "install-pause"
        self.sdk.begin_cross_store_pause("one", operation_id=op, expected_run_revision=0,
                                         expected_control_epoch=1, credential="token")
        self.sdk.advance_cross_store_pause(op, credential="token")
        self.sdk.complete_cross_store_pause_participant(op, credential="token")
        while not self.sdk.capture_cross_store_pause_page(op, credential="token")["capture_complete"]:
            pass
        self.sdk.prepare_cross_store_pause(op, credential="token")
        self.sdk.finalize_cross_store_pause(op, credential="token")
        with self.sdk._transaction() as connection:
            source = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (op,)).fetchone()
        content_page.update(operation_id=op, decision_id=op, barrier_operation_id=op, run_id="one", kernel_store_id=source["kernel_store_id"],
            orchestrator_store_id=source["orchestrator_store_id"], orchestrator_incarnation=source["orchestrator_incarnation"],
            source_generation=0, content_kind="revision", page_seq=0, total_bytes=2, chunk="{", complete=False,
            lease_id="control-lease", lease_fence=1, lease_expires_at=expiry, lease_held=True)
        with self.assertRaises(OrchestrationError):
            self.sdk.stage_revision_content_page(dict(content_page, chunk=""), credential="token", page_credential="page")
        def lose_page(stage):
            if stage == "after_kernel_revision_content_page":
                raise RuntimeError("lost content page acknowledgement")
        self.sdk._failpoint = lose_page
        with self.assertRaisesRegex(RuntimeError, "lost content page"):
            self.sdk.stage_revision_content_page(content_page, credential="token", page_credential="page")
        self.sdk._failpoint = lambda stage: None
        self.assertEqual(self.sdk.stage_revision_content_page(content_page, credential="token", page_credential="page")["cumulative_bytes"], 1)
        content_page.update(page_seq=1, chunk="}", complete=True)
        self.assertTrue(self.sdk.stage_revision_content_page(content_page, credential="token", page_credential="page")["capture_complete"])
        decision = self.sdk.commit_cross_store_revision(op, request_id="revision", credential="token",
            expected_run_revision=0, expected_control_epoch=3, expected_generation=0,
            deployment={"handler": "v2"}, revision={}, migration_version="m1",
            application_projection_version="p1", migrate=lambda state, revision: state)
        with self.sdk._transaction() as connection:
            operation = connection.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (op,)).fetchone()
        envelope.update(decision_id=op, operation_id=op, barrier_operation_id=op, run_id="one",
            orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"],
            kernel_store_id=operation["kernel_store_id"], source_revision=0, source_generation=0,
            source_control_epoch=3, target_generation=1, deployment={"handler": "other"},
            revision={}, source_application_state=json.loads(decision["source_application_state"]),
            target_application_state=json.loads(decision["target_application_state"]),
            content_pages={},
            migration_version="m1", application_projection_version="p1")
        with self.assertRaises(CASConflictError):
            self.sdk.install_cross_store_revision(op, credential="token", decision_credential="decision", worker_credential="next")
        self.assertEqual(participant.get_run_control("one")["generation"], 0)
        envelope["deployment"] = {"handler": "v2"}
        self.sdk.control_authorizer.verifier = lambda credential: {"principal": "operator", "permissions": []}
        with self.assertRaises(OrchestrationError):
            self.sdk.install_cross_store_revision(op, credential="token", decision_credential="decision", worker_credential="next")
        self.assertEqual(participant.get_run_control("one")["generation"], 0)
        self.sdk.control_authorizer.verifier = control_verify
        def lose_ack(stage):
            if stage == "after_kernel_revision_install":
                raise RuntimeError("lost install acknowledgement")
        self.sdk._failpoint = lose_ack
        with self.assertRaisesRegex(RuntimeError, "lost install"):
            self.sdk.install_cross_store_revision(op, credential="token", decision_credential="decision", worker_credential="next")
        participant.close()
        participant = SQLiteKernel(path, authority_verifier=kernel_verify, worker_credential="manager")
        self.addCleanup(participant.close)
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify)
        def revoke_inflight(stage):
            if stage == "after_kernel_revision_install":
                restarted.control_authorizer.verifier = lambda credential: {"principal": "operator", "permissions": []}
        restarted._failpoint = revoke_inflight
        with self.assertRaises(OrchestrationError):
            restarted.install_cross_store_revision(op, credential="token", decision_credential="decision", worker_credential="next")
        self.assertEqual(participant.get_run_control("one")["state"], "paused")
        self.assertEqual(participant.get_run_control("one")["generation"], 1)
        with restarted._transaction() as connection:
            self.assertIsNone(connection.execute("SELECT kernel_install_receipt FROM sdk_revision_decisions WHERE operation_id=?", (op,)).fetchone()[0])
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify)
        installed = restarted.install_cross_store_revision(op, credential="token", decision_credential="decision", worker_credential="next")
        receipt = json.loads(installed["kernel_install_receipt"])
        self.assertEqual((receipt["activation"], receipt["cleanup"]), ("closed", "unknown"))
        self.assertEqual((receipt["claims_used"], receipt["max_claims"], receipt["deadline_at"]), (0, 1, self.deadline))
        self.assertEqual((participant.get_run_control("one")["state"], participant.get_run_control("one")["generation"]), ("paused", 1))
        self.assertEqual(restarted.get_managed_control("one")["control_state"], "paused")
        self.assertEqual(restarted.install_cross_store_revision(op, credential="token", decision_credential="decision", worker_credential="next")["kernel_install_receipt"], installed["kernel_install_receipt"])
        def lose_local_ack(stage):
            if stage == "after_orchestrator_revision_install":
                raise RuntimeError("lost projection acknowledgement")
        restarted._failpoint = lose_local_ack
        with self.assertRaisesRegex(RuntimeError, "lost projection"):
            restarted.install_cross_store_projection(op, credential="token")
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify)
        projection = restarted.install_cross_store_projection(op, credential="token")
        self.assertEqual(json.loads(projection["orchestrator_install_receipt"])["generation"], 1)
        self.assertEqual(restarted.get_managed_control("one")["control_state"], "paused")
        lease = {"operation_id": "activate-one", "run_id": "one", "kernel_store_id": operation["kernel_store_id"],
                 "orchestrator_store_id": operation["orchestrator_store_id"], "orchestrator_incarnation": operation["orchestrator_incarnation"],
                 "lease_id": "host-lease", "lease_fence": 9, "expires_at": expiry, "held": True,
                 "scope": "resume_cancel_revoke_through_commit"}
        restarted.control_lease_verifier = lambda credential: dict(lease)
        budget_policy.update(policy_id="budget-one", decision_id=op, run_id="one", generation=1,
            kernel_store_id=operation["kernel_store_id"], orchestrator_store_id=operation["orchestrator_store_id"],
            orchestrator_incarnation=operation["orchestrator_incarnation"],
            scopes=[{"owner": "app", "unit": "token", "source_id": "ledger"}])
        lease["operation_id"] = op
        restarted.install_cross_store_budget_policy(op, policy=budget_policy, credential="token",
            lease_credential="lease", policy_credential="budget")
        lease["operation_id"] = "activate-one"
        activation.update(operation_id="activate-one", run_id="one", decision_id=op, barrier_operation_id=op,
                          completion_operation_id=op + ":local-paused", kernel_store_id=operation["kernel_store_id"],
                          orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"],
                          generation=1, expected_control_epoch=4, orchestrator_install_receipt=json.loads(projection["orchestrator_install_receipt"]),
                          kernel_install_receipt=json.loads(projection["kernel_install_receipt"]), lease_id="host-lease",
                          lease_fence=9, lease_expires_at=expiry, lease_held=True)
        def lose_activation(stage):
            if stage == "after_kernel_revision_activation":
                raise RuntimeError("lost activation acknowledgement")
        restarted._failpoint = lose_activation
        with self.assertRaisesRegex(RuntimeError, "lost activation"):
            restarted.activate_cross_store_revision(op, operation_id="activate-one", credential="token",
                lease_credential="lease", activation_credential="activation")
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify,
                                 control_lease_verifier=lambda credential: dict(lease))
        activated = restarted.activate_cross_store_revision(op, operation_id="activate-one", credential="token",
            lease_credential="lease", activation_credential="activation")
        self.assertEqual(json.loads(activated["kernel_receipt"])["state"], "paused")
        self.assertEqual(participant.get_run_control("one")["state"], "paused")
        lease["operation_id"] = "resume-one"
        resume_decision.update(operation_id="resume-one", run_id="one", decision_id=op, barrier_operation_id=op,
            completion_operation_id=op + ":local-paused", activation_operation_id="activate-one",
            activation_receipt=json.loads(activated["kernel_receipt"]), kernel_store_id=operation["kernel_store_id"],
            orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"],
            generation=1, expected_control_epoch=4, target_control_epoch=5,
            orchestrator_install_receipt=json.loads(projection["orchestrator_install_receipt"]),
            kernel_install_receipt=json.loads(projection["kernel_install_receipt"]), lease_id="host-lease",
            lease_fence=9, lease_expires_at=expiry, lease_held=True)
        def lose_lease(stage):
            if stage == "after_kernel_revision_resume":
                lease["held"] = False
        restarted._failpoint = lose_lease
        with self.assertRaises(OrchestrationError):
            restarted.resume_cross_store_revision("activate-one", operation_id="resume-one", credential="token",
                lease_credential="lease", resume_credential="resume", worker_credential="resumed")
        self.assertEqual(participant.get_run_control("one")["state"], "active")
        self.assertEqual(restarted.get_managed_control("one")["control_state"], "paused")
        from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
        worker = SQLiteKernel(path, authority_verifier=kernel_verify, worker_credential="resumed")
        self.addCleanup(worker.close)
        with worker._transaction() as (connection, timestamp):
            with self.assertRaises(StorageIsolationError):
                worker._check_run_authority(connection, "one", "claim", timestamp)
        lease["held"] = True
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify,
                                 control_lease_verifier=lambda credential: dict(lease))
        resumed = restarted.resume_cross_store_revision("activate-one", operation_id="resume-one", credential="token",
            lease_credential="lease", resume_credential="resume", worker_credential="resumed")
        self.assertEqual(json.loads(resumed["orchestrator_receipt"])["state"], "active")
        self.assertEqual(restarted.get_managed_control("one")["control_state"], "active")
        final_receipt.update(json.loads(resumed["orchestrator_receipt"]))
        global_open[0] = True
        with worker._transaction() as (connection, timestamp):
            worker._check_run_authority(connection, "one", "claim", timestamp)
        blocked, independent = command("one", "blocked"), command("one", "independent")
        budget_declaration.update(run_id="one", generation=1, policy_id="budget-one", execution_id=blocked.execution_id,
                                  command=blocked.to_dict(), scopes=budget_policy["scopes"], decision_id=op,
                                  kernel_store_id=operation["kernel_store_id"], orchestrator_store_id=operation["orchestrator_store_id"],
                                  orchestrator_incarnation=operation["orchestrator_incarnation"])
        participant.declare_budget_dependencies("budget", expected_declaration=dict(budget_declaration))
        budget_proof.update(allowed=True, run_id="one", generation=1, execution_id=blocked.execution_id,
                            policy_id="budget-one", scopes=budget_policy["scopes"], expires_at=expiry,
                            decision_id=op, kernel_store_id=operation["kernel_store_id"],
                            orchestrator_store_id=operation["orchestrator_store_id"],
                            orchestrator_incarnation=operation["orchestrator_incarnation"])
        worker.submit_managed(blocked, run_id="one", generation=1)
        budget_declaration.update(execution_id=independent.execution_id, command=independent.to_dict(), scopes=[])
        participant.declare_budget_dependencies("budget", expected_declaration=dict(budget_declaration))
        worker.submit_managed(independent, run_id="one", generation=1)
        saved_budget = dict(budget_proof)
        budget_proof.clear()
        with self.assertRaises(StorageIsolationError):
            worker.claim_and_start("worker", execution_id=blocked.execution_id)
        budget_proof.update(saved_budget)
        budget_proof["allowed"] = False
        with self.assertRaises(StorageIsolationError):
            worker.claim_and_start("worker", execution_id=blocked.execution_id)
        admitted = worker.claim("worker")
        self.assertEqual(admitted.execution_id, independent.execution_id)
        self.assertEqual(worker.get(blocked.execution_id).state, "queued")
        lease["operation_id"] = "cancel-one"
        original_fence = participant.fence_cancelled_run
        raced = [False]
        def race_epoch(*args, **kwargs):
            if not raced[0]:
                raced[0] = True
                with participant._transaction() as (connection, _):
                    connection.execute("UPDATE kernel_run_controls SET control_epoch=6 WHERE run_id='one'")
                    connection.execute("UPDATE kernel_run_authorities SET control_epoch=6 WHERE run_id='one'")
                raise CASConflictError("racing control change")
            return original_fence(*args, **kwargs)
        participant.fence_cancelled_run = race_epoch
        def lose_cancel(stage):
            if stage == "after_kernel_cancellation_fence":
                raise RuntimeError("lost cancellation acknowledgement")
        restarted._failpoint = lose_cancel
        with self.assertRaisesRegex(RuntimeError, "lost cancellation"):
            restarted.fence_cross_store_cancellation("one", operation_id="cancel-one", credential="token", lease_credential="lease")
        self.assertEqual(restarted.get_managed_control("one")["control_state"], "active")
        self.assertEqual(participant.get_run_control("one")["state"], "paused")
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify,
                                 control_lease_verifier=lambda credential: dict(lease))
        cancelled = restarted.fence_cross_store_cancellation("one", operation_id="cancel-one", credential="token", lease_credential="lease")
        self.assertEqual(json.loads(cancelled["orchestrator_receipt"])["state"], "admission_fenced")
        self.assertEqual(restarted.get_managed_control("one")["control_state"], "paused")
        self.assertEqual(restarted.fence_cross_store_cancellation("one", operation_id="cancel-one", credential="token", lease_credential="lease")["orchestrator_receipt"], cancelled["orchestrator_receipt"])
        with restarted._transaction() as connection:
            connection.execute("UPDATE sdk_managed_runs SET control_epoch=control_epoch-1 WHERE run_id='one'")
        with self.assertRaises((CommandConflict, RevisionConflict)):
            restarted.fence_cross_store_cancellation("one", operation_id="cancel-one", credential="token", lease_credential="lease")
        with restarted._transaction() as connection:
            connection.execute("UPDATE sdk_managed_runs SET control_epoch=control_epoch+1 WHERE run_id='one'")
            local = json.loads(cancelled["orchestrator_receipt"])
            local["run_id"] = "other"
            connection.execute("UPDATE sdk_cancellation_fences SET orchestrator_receipt=? WHERE operation_id='cancel-one'", (json.dumps(local),))
        with self.assertRaises(CommandConflict):
            restarted.fence_cross_store_cancellation("one", operation_id="cancel-one", credential="token", lease_credential="lease")
        with restarted._transaction() as connection:
            connection.execute("UPDATE sdk_cancellation_fences SET orchestrator_receipt=? WHERE operation_id='cancel-one'", (cancelled["orchestrator_receipt"],))
        with restarted._transaction() as connection:
            revision = connection.execute("SELECT revision FROM sdk_runs WHERE run_id='one'").fetchone()[0]
        def lose_action(stage):
            if stage == "after_fenced_cancellation_action":
                raise RuntimeError("lost action acknowledgement")
        restarted._failpoint = lose_action
        with self.assertRaisesRegex(RuntimeError, "lost action"):
            restarted.apply_fenced_cancellation("cancel-one", operation_id="finish-cancel", expected_revision=revision,
                operations=[{"kind": "finish", "state": "cancelled"}], credential="token", lease_credential="lease")
        restarted = Orchestrator(self.path, participant, control_verifier=control_verify,
                                 control_lease_verifier=lambda credential: dict(lease))
        action = restarted.apply_fenced_cancellation("cancel-one", operation_id="finish-cancel", expected_revision=revision,
            operations=[{"kind": "finish", "state": "cancelled"}], credential="token", lease_credential="lease")
        self.assertEqual(action["state"], "cancelled")
        self.assertEqual(restarted.apply_fenced_cancellation("cancel-one", operation_id="finish-cancel", expected_revision=revision,
            operations=[{"kind": "finish", "state": "cancelled"}], credential="token", lease_credential="lease"), action)
        with self.assertRaises(CommandConflict):
            restarted.apply_fenced_cancellation("cancel-one", operation_id="finish-cancel", expected_revision=revision + 1,
                operations=[{"kind": "finish", "state": "cancelled"}], credential="token", lease_credential="lease")
        lease["operation_id"] = "resume-one"
        with self.assertRaises((CASConflictError, OrchestrationError)):
            restarted.resume_cross_store_revision("activate-one", operation_id="resume-one", credential="token",
                lease_credential="lease", resume_credential="resume", worker_credential="resumed")

    def test_persistent_intent_closes_local_gate_and_replays_receipt(self):
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)

        deadline = self.deadline
        class Participant:
            db_path = "/tmp/independent-kernel-store"
            def kernel_store_identity(self):
                return "kernel-store"
            def prepare_control_pause(self, operation_id, run_id, *, expected_epoch, generation):
                return {"store_id": "kernel-store", "operation_id": operation_id,
                        "run_id": run_id, "expected_epoch": expected_epoch,
                        "control_epoch": expected_epoch + 1, "generation": generation,
                        "max_claims": 1, "deadline_at": deadline}

        self.sdk.kernel = Participant()
        op = self.sdk.begin_cross_store_pause("one", operation_id="pause-1",
            expected_run_revision=0, expected_control_epoch=1, credential="token")
        self.assertEqual(op["phase"], "preparing")
        self.assertEqual(self.sdk.get_managed_control("one")["control_state"], "pausing")
        replay = self.sdk.begin_cross_store_pause("one", operation_id="pause-1",
            expected_run_revision=0, expected_control_epoch=1, credential="token")
        self.assertEqual(replay["operation_id"], op["operation_id"])
        advanced = self.sdk.advance_cross_store_pause("pause-1", credential="token")
        self.assertEqual(advanced["phase"], "preparing")
        self.assertEqual(json.loads(advanced["kernel_receipt"])["control_epoch"], 2)
        self.assertEqual(self.sdk.advance_cross_store_pause("pause-1", credential="token")["phase"], "preparing")

    def test_real_split_kernel_pause_receipt_stays_preparing(self):
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        participant = SQLiteKernel(self.path.parent / "separate.sqlite")
        self.addCleanup(participant.close)
        participant.register_run_control("one", max_claims=1, deadline_at=self.deadline)
        participant.set_run_control("one", expected_epoch=0, state="active", generation=0)
        self.sdk.kernel = participant
        self.sdk.begin_cross_store_pause("one", operation_id="real-pause",
            expected_run_revision=0, expected_control_epoch=1, credential="token")
        operation = self.sdk.advance_cross_store_pause("real-pause", credential="token")
        receipt = json.loads(operation["kernel_receipt"])
        self.assertEqual(receipt["control_epoch"], 2)
        self.assertEqual(receipt["cleanup"], "unknown")
        self.assertEqual(operation["phase"], "preparing")
        self.assertEqual(participant.get_run_control("one")["state"], "pausing")
        self.assertEqual(self.sdk.advance_cross_store_pause("real-pause", credential="token")["kernel_receipt"],
                         operation["kernel_receipt"])
        def fail(stage):
            if stage == "after_kernel_pause_completion":
                raise RuntimeError("lost local receipt")
        self.sdk._failpoint = fail
        with self.assertRaisesRegex(RuntimeError, "lost local receipt"):
            self.sdk.complete_cross_store_pause_participant("real-pause", credential="token")
        self.assertEqual(participant.get_run_control("one")["state"], "paused")
        from dispatcher_sdk.orchestrator import Orchestrator
        restarted = Orchestrator(self.path, participant, control_verifier=lambda credential: {"principal": "operator", "permissions": [("one", "pause")]})
        completed = restarted.complete_cross_store_pause_participant("real-pause", credential="token")
        self.assertEqual(json.loads(completed["kernel_pause_receipt"])["cleanup"], "unknown")
        self.assertEqual(completed["phase"], "preparing")
        self.assertEqual(restarted.get_managed_control("one")["control_state"], "pausing")
        with self.assertRaisesRegex(OrchestrationError, "unknown in-flight"):
            restarted.prepare_cross_store_pause("real-pause", credential="token")

    def test_empty_synthetic_run_records_prepared_but_preserves_unknowns(self):
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        from dispatcher_sdk.orchestrator import Orchestrator
        self.sdk.register_managed_run("one", request_id="create", definition={},
            task_commands=[], max_claims=1, deadline_at=self.deadline)
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        participant = SQLiteKernel(self.path.parent / "independent.sqlite")
        self.addCleanup(participant.close)
        participant.register_run_control("one", max_claims=1, deadline_at=self.deadline)
        participant.set_run_control("one", expected_epoch=0, state="active", generation=0)
        self.sdk.kernel = participant
        self.sdk.begin_cross_store_pause("one", operation_id="empty-pause",
            expected_run_revision=0, expected_control_epoch=1, credential="token")
        self.sdk.advance_cross_store_pause("empty-pause", credential="token")
        self.sdk.complete_cross_store_pause_participant("empty-pause", credential="token")
        restarted = Orchestrator(self.path, participant, control_verifier=lambda credential: {"principal": "operator", "permissions": [("one", "pause")]})
        with self.assertRaisesRegex(OrchestrationError, "capture is incomplete"):
            restarted.prepare_cross_store_pause("empty-pause", credential="token")
        def lose_page(stage):
            if stage == "after_kernel_capture_page":
                raise RuntimeError("lost page receipt")
        restarted._failpoint = lose_page
        with self.assertRaisesRegex(RuntimeError, "lost page receipt"):
            restarted.capture_cross_store_pause_page("empty-pause", credential="token", max_items=2)
        restarted = Orchestrator(self.path, participant, control_verifier=lambda credential: {"principal": "operator", "permissions": [("one", "pause")]})
        first = restarted.capture_cross_store_pause_page("empty-pause", credential="token")
        self.assertEqual(first["page"], 0)
        final = restarted.capture_cross_store_pause_page("empty-pause", credential="token")
        self.assertTrue(final["capture_complete"])
        prepared = restarted.prepare_cross_store_pause("empty-pause", credential="token")
        self.assertEqual(prepared["phase"], "prepared")
        evidence = json.loads(prepared["prepared_evidence"])
        self.assertEqual(evidence["fixed_point"], "unknown")
        self.assertEqual(evidence["writer_isolation"], "unknown")
        self.assertEqual(restarted.prepare_cross_store_pause("empty-pause", credential="token")["prepared_evidence"],
                         prepared["prepared_evidence"])
        local_pause = restarted.finalize_cross_store_pause("empty-pause", credential="token")
        self.assertEqual(json.loads(local_pause["orchestrator_pause_receipt"])["state"], "paused")
        self.assertEqual(restarted.prepare_cross_store_pause("empty-pause", credential="token")["phase"], "prepared")
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
        restarted.control_authorizer = ControlAuthorizer(restarted, lambda credential: {
            "principal": "operator", "permissions": [("one", "commit_revision")]})
        calls = []
        def migrate(state, revision):
            calls.append((state, revision))
            return {"migrated": revision["value"]}
        def lose_decision(stage):
            if stage == "after_revision_decision_commit":
                raise RuntimeError("lost decision acknowledgement")
        restarted._failpoint = lose_decision
        arguments = dict(request_id="rev-1", credential="token", expected_run_revision=0,
                         expected_control_epoch=3, expected_generation=0,
                         deployment={"handler": "v2"}, revision={"value": 2},
                         migration_version="migration-v1", application_projection_version="projection-v2", migrate=migrate)
        with self.assertRaisesRegex(OrchestrationError, "deployment declaration exceeds"):
            restarted.commit_cross_store_revision("empty-pause", **dict(arguments, deployment={"value": "x" * 65536}))
        with self.assertRaisesRegex(OrchestrationError, "migration_version exceeds"):
            restarted.commit_cross_store_revision("empty-pause", **dict(arguments, migration_version="x" * 1025))
        self.assertEqual(calls, [])
        def revoke_during_migration(state, revision):
            restarted.control_authorizer.verifier = lambda credential: {
                "principal": "operator", "permissions": []}
            return {"migrated": revision["value"]}
        revoked_arguments = dict(arguments, migrate=revoke_during_migration)
        with self.assertRaisesRegex(OrchestrationError, "not granted"):
            restarted.commit_cross_store_revision("empty-pause", **revoked_arguments)
        restarted.control_authorizer.verifier = lambda credential: {
            "principal": "operator", "permissions": [("one", "commit_revision")]}
        with self.assertRaisesRegex(RuntimeError, "lost decision acknowledgement"):
            restarted.commit_cross_store_revision("empty-pause", **arguments)
        restarted._failpoint = lambda stage: None
        decision = restarted.commit_cross_store_revision("empty-pause", **arguments)
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(decision["target_application_state"]), {"migrated": 2})
        self.assertEqual(participant.get_run_control("one")["state"], "paused")
        # A later state advance must not make an already committed request
        # invoke the migration callback again or lose its original result.
        with restarted._transaction() as connection:
            connection.execute("UPDATE sdk_runs SET revision=revision+1 WHERE run_id='one'")
        replay = restarted.commit_cross_store_revision("empty-pause", **arguments)
        self.assertEqual(replay["target_application_state"], decision["target_application_state"])
        self.assertEqual(len(calls), 1)

    def test_revoked_delegation_blocks_new_pause_before_gate_closes(self):
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        def verifier(credential):
            if credential == "owner":
                return {"principal": "owner", "permissions": [("one", "delegate:pause"), ("one", "pause")]}
            if credential == "operator":
                return {"principal": "operator", "permissions": []}
            raise OrchestrationError("authentication failed")
        self.sdk.control_authorizer = ControlAuthorizer(self.sdk, verifier)
        authority = self.sdk.control_authorizer
        authority.grant("owner", delegation_id="delegation", run_id="one", action="pause",
                        principal="operator", expires_at=self.deadline)
        authority.revoke("owner", delegation_id="delegation")
        class Participant:
            db_path = "/tmp/independent-kernel-store"
            def kernel_store_identity(self):
                return "kernel-store"
            def prepare_control_pause(self, *args, **kwargs):
                raise AssertionError("revoked authority reached Kernel")
        self.sdk.kernel = Participant()
        with self.assertRaisesRegex(OrchestrationError, "revoked"):
            self.sdk.begin_cross_store_pause("one", operation_id="denied",
                expected_run_revision=0, expected_control_epoch=1,
                credential="operator", delegation_id="delegation")
        self.assertEqual(self.sdk.get_managed_control("one")["control_state"], "active")

    def test_host_verified_delegation_is_scoped_and_expires(self):
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
        def verifier(credential):
            if credential == "owner":
                return {"principal": "owner", "permissions": [("one", "delegate:pause"), ("one", "pause")]}
            if credential == "operator":
                return {"principal": "operator", "permissions": []}
            raise OrchestrationError("authentication failed")
        authority = ControlAuthorizer(self.sdk, verifier)
        authority.grant("owner", delegation_id="scope", run_id="one", action="pause",
                        principal="operator", expires_at=self.deadline)
        verified = authority.verify("operator")
        with self.sdk._transaction() as connection:
            self.assertEqual(authority.check_in_transaction(connection, verified, "one", "pause", "scope"), "operator")
            with self.assertRaises(OrchestrationError):
                authority.check_in_transaction(connection, verified, "other", "pause", "scope")
            with self.assertRaises(OrchestrationError):
                authority.check_in_transaction(connection, verified, "one", "resume", "scope")
        with self.assertRaises(OrchestrationError):
            authority.verify("forged")
        self.sdk.clock = lambda: self.deadline + 1
        authority.verify("operator")
        self.sdk.clock = lambda: self.deadline - 10
        with self.sdk._transaction() as connection:
            with self.assertRaisesRegex(OrchestrationError, "expired"):
                authority.check_in_transaction(connection, verified, "one", "pause", "scope")

    def test_delegator_requires_the_action_as_well_as_delegate_permission(self):
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
        authority = ControlAuthorizer(self.sdk, lambda credential: {
            "principal": "owner", "permissions": [("one", "delegate:pause")]})
        with self.assertRaisesRegex(OrchestrationError, "not authorized"):
            authority.grant("owner", delegation_id="excess", run_id="one", action="pause",
                            principal="operator", expires_at=self.deadline)

    def test_split_store_lost_delivery_ack_replays_without_new_execution(self):
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        from dispatcher_sdk.orchestrator import Orchestrator
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        participant = SQLiteKernel(self.path.parent / "independent-ack.sqlite")
        self.addCleanup(participant.close)
        participant.register_run_control("one", max_claims=1, deadline_at=self.deadline)
        participant.set_run_control("one", expected_epoch=0, state="active", generation=0)
        self.sdk.kernel = participant
        def lose_ack(stage):
            if stage == "after_kernel_delivery":
                raise RuntimeError("lost dispatch ack")
        self.sdk._failpoint = lose_ack
        with self.assertRaisesRegex(RuntimeError, "lost dispatch ack"):
            self.sdk.flush()
        self.sdk._failpoint = lambda stage: None
        self.sdk.begin_cross_store_pause("one", operation_id="ack-pause",
            expected_run_revision=0, expected_control_epoch=1, credential="token")
        self.sdk.advance_cross_store_pause("ack-pause", credential="token")
        self.sdk.complete_cross_store_pause_participant("ack-pause", credential="token")
        restarted = Orchestrator(self.path, participant, control_verifier=lambda credential: {"principal": "operator", "permissions": [("one", "pause")]})
        while not restarted.capture_cross_store_pause_page("ack-pause", credential="token")["capture_complete"]:
            pass
        result = restarted.prepare_cross_store_pause("ack-pause", credential="token")
        self.assertEqual(result["phase"], "prepared")
        evidence = json.loads(result["prepared_evidence"])
        self.assertEqual(evidence["pending_dispatches"][0]["state"], "accepted")
        self.assertTrue(any(item["kind"] == "cleanup" and item["execution_id"] == "sdk-managed:one:a"
                            for item in evidence["dependencies"]))
        self.assertEqual(participant.get("sdk-managed:one:a").attempt, 0)

    def test_revoked_authority_cannot_advance_preexisting_operation(self):
        from dispatcher_sdk.orchestrator.control_authorization import ControlAuthorizer
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        def verifier(credential):
            return {"principal": credential, "permissions": (
                [("one", "pause"), ("one", "delegate:pause")] if credential == "owner" else [])}
        self.sdk.control_authorizer = ControlAuthorizer(self.sdk, verifier)
        authority = self.sdk.control_authorizer
        authority.grant("owner", delegation_id="delegation", run_id="one", action="pause",
                        principal="operator", expires_at=self.deadline)
        class Participant:
            db_path = "/tmp/independent-kernel-store"
            def kernel_store_identity(self):
                return "kernel-store"
            def prepare_control_pause(self, *args, **kwargs):
                raise AssertionError("revoked caller reached Kernel")
        self.sdk.kernel = Participant()
        self.sdk.begin_cross_store_pause("one", operation_id="revoked-op",
            expected_run_revision=0, expected_control_epoch=1,
            credential="operator", delegation_id="delegation")
        authority.revoke("owner", delegation_id="delegation")
        with self.assertRaisesRegex(OrchestrationError, "revoked"):
            self.sdk.advance_cross_store_pause("revoked-op", credential="operator", delegation_id="delegation")

    def test_accepted_permit_cannot_be_reused_after_kernel_rebinding(self):
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        self._register("one")
        self.sdk._request_managed_control("one", request_id="resume", kind="resume",
            expected_run_revision=0, expected_control_epoch=0)
        participant_a = SQLiteKernel(self.path.parent / "kernel-a.sqlite")
        participant_b = SQLiteKernel(self.path.parent / "kernel-b.sqlite")
        self.addCleanup(participant_a.close)
        self.addCleanup(participant_b.close)
        for kernel in (participant_a, participant_b):
            kernel.register_run_control("one", max_claims=1, deadline_at=self.deadline)
            kernel.set_run_control("one", expected_epoch=0, state="active", generation=0)
        self.sdk.kernel = participant_a
        self.assertEqual(self.sdk.flush(), 1)
        self.sdk.kernel = participant_b
        self.sdk.begin_cross_store_pause("one", operation_id="rebound",
            expected_run_revision=self.sdk.get_run("one")["revision"], expected_control_epoch=1, credential="token")
        self.sdk.advance_cross_store_pause("rebound", credential="token")
        self.sdk.complete_cross_store_pause_participant("rebound", credential="token")
        with self.assertRaisesRegex(OrchestrationError, "unknown in-flight"):
            self.sdk.prepare_cross_store_pause("rebound", credential="token")
