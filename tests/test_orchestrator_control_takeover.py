import json
import time

from test_external_projection_foundation import ExternalProjectionFoundationTests
from dispatcher_sdk.orchestrator import OrchestrationError


class TakeoverTests(ExternalProjectionFoundationTests):
    def prepare_activation(self):
        self.seed_future_decision()
        installed = self.sdk.install_cross_store_revision("decision", credential="operator", decision_credential="x", worker_credential="x")
        kernel_install = json.loads(installed["kernel_install_receipt"])
        local_install = {"run_id": "run", "generation": 1}
        with self.sdk._transaction() as c:
            c.execute("UPDATE sdk_revision_decisions SET orchestrator_install_receipt=? WHERE operation_id='decision'", (json.dumps(local_install),))
            c.execute("UPDATE sdk_managed_runs SET control_epoch=4,generation=1 WHERE run_id='run'")
        self.kernel.state, self.kernel.epoch, self.kernel.generation = "paused", 4, 1
        self.lease.update(operation_id="activation", lease_id="new", lease_fence=2)
        original = {"operation_id": "activation", "run_id": "run", "kernel_store_id": "kernel",
            "orchestrator_store_id": self.lease["orchestrator_store_id"], "orchestrator_incarnation": self.lease["orchestrator_incarnation"],
            "decision_id": "decision", "barrier_operation_id": "decision", "completion_operation_id": "decision:local-paused",
            "generation": 1, "expected_control_epoch": 4, "orchestrator_install_receipt": local_install,
            "kernel_install_receipt": kernel_install, "lease_id": "old", "lease_fence": 1,
            "lease_expires_at": time.time() - 10, "lease_held": True}
        with self.sdk._transaction() as c:
            c.execute("INSERT INTO sdk_revision_activations VALUES(?,?,?,NULL,?)", ("activation", "decision", json.dumps(original), 1))
        self.sdk.control_authorizer.verifier = lambda _: {"principal": "operator", "permissions": [("run", "activate_revision")]}
        self.kernel.get_run_control = lambda _: {"state": "paused", "control_epoch": 4, "generation": 1, "max_claims": 1, "claims_used": 0, "deadline_at": 9999999999}
        self.kernel.inspect_control_participant_receipt = lambda credential, expected_inspection: None
        receipts = {}
        self.kernel.inspect_control_takeover = lambda credential, expected_inspection: receipts.get(expected_inspection["original_takeover"]["takeover_id"])
        def takeover(credential, expected_takeover):
            if credential != "takeover":
                raise OrchestrationError("takeover authority denied")
            claim = expected_takeover
            key = claim["takeover_id"]
            if key not in receipts:
                receipts[key] = {"kind": "control_lease_takeover", "claim": claim, "recorded_at": 1}
            return receipts[key]
        self.kernel.takeover_control_lease = takeover
        self.kernel.activate_revision = lambda credential, expected_decision: {"kind": "revision_activation", "state": "paused", "decision": expected_decision}
        return original

    def takeover(self, token="takeover"):
        return self.sdk.takeover_cross_store_control_lease("activation", phase="activation", takeover_id="handoff",
            credential="operator", lease_credential="lease", inspection_credential="inspect", takeover_credential=token)

    def test_lost_ack_replay_and_new_lease_activation(self):
        original = self.prepare_activation()
        self.sdk._failpoint = lambda stage: (_ for _ in ()).throw(RuntimeError("lost ACK")) if stage == "after_kernel_control_takeover" else None
        with self.assertRaisesRegex(RuntimeError, "lost ACK"):
            self.takeover()
        with self.sdk._transaction() as c:
            row = c.execute("SELECT kernel_receipt FROM sdk_control_lease_takeovers WHERE takeover_id='handoff'").fetchone()
            self.assertIsNone(row[0])
        self.sdk._failpoint = lambda _: None
        receipt = self.takeover()
        self.assertEqual(receipt["claim"]["new_fence"], 2)
        result = self.sdk.activate_cross_store_revision("decision", operation_id="activation", credential="operator",
            lease_credential="lease", activation_credential="activation")
        self.assertEqual(json.loads(result["envelope"]), original)
        self.assertEqual(json.loads(result["kernel_receipt"])["decision"]["lease_id"], "new")

    def test_resume_committed_in_kernel_recovers_under_new_lease(self):
        self.prepare_activation()
        self.takeover()
        activation = self.sdk.activate_cross_store_revision("decision", operation_id="activation", credential="operator",
            lease_credential="lease", activation_credential="activation")
        activation_receipt = json.loads(activation["kernel_receipt"])
        with self.sdk._transaction() as c:
            decision = c.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id='decision'").fetchone()
            policy = '{"policy_id":"budget"}'
            c.execute("INSERT INTO sdk_revision_budget_policies VALUES('decision',?,?)", (policy, policy))
        self.kernel.inspect_budget_policy = lambda run_id, generation: {"policy_id": "budget"}
        original = {"operation_id": "resume", "run_id": "run", "kernel_store_id": "kernel",
            "orchestrator_store_id": self.lease["orchestrator_store_id"], "orchestrator_incarnation": self.lease["orchestrator_incarnation"],
            "decision_id": "decision", "barrier_operation_id": "decision", "completion_operation_id": "decision:local-paused",
            "activation_operation_id": "activation", "activation_receipt": activation_receipt,
            "generation": 1, "expected_control_epoch": 4, "target_control_epoch": 5,
            "orchestrator_install_receipt": json.loads(decision["orchestrator_install_receipt"]),
            "kernel_install_receipt": json.loads(decision["kernel_install_receipt"]), "lease_id": "new", "lease_fence": 2,
            "lease_expires_at": self.lease["expires_at"], "lease_held": True}
        kernel_receipt = {"kind": "revision_resume", "decision": original}
        with self.sdk._transaction() as c:
            c.execute("INSERT INTO sdk_revision_resumes VALUES(?,?,?,NULL,NULL,?)", ("resume", "decision", json.dumps(original), 1))
        self.lease.update(operation_id="resume", lease_id="next", lease_fence=3)
        self.sdk.control_authorizer.verifier = lambda _: {"principal": "operator", "permissions": [("run", "resume")]}
        self.kernel.get_run_control = lambda _: {"state": "active", "control_epoch": 5, "generation": 1,
            "max_claims": 1, "claims_used": 0, "deadline_at": 9999999999}
        self.kernel.inspect_control_participant_receipt = lambda credential, expected_inspection: kernel_receipt
        self.kernel.resume_revision = lambda credential, worker_credential, expected_decision: kernel_receipt
        self.sdk.takeover_cross_store_control_lease("resume", phase="resume", takeover_id="handoff-resume", credential="operator",
            lease_credential="lease", inspection_credential="inspect", takeover_credential="takeover")
        completed = self.sdk.resume_cross_store_revision("activation", operation_id="resume", credential="operator", lease_credential="lease",
            resume_credential="resume", worker_credential="worker")
        self.assertEqual(json.loads(completed["envelope"]), original)
        self.assertEqual(json.loads(completed["kernel_receipt"]), kernel_receipt)
        self.assertEqual(json.loads(completed["orchestrator_receipt"])["state"], "active")

    def test_renewed_lease_recovers_historical_receipt_after_expiry(self):
        self.prepare_activation()
        now = time.time()
        self.sdk.clock = lambda: now
        self.lease["expires_at"] = now + 5
        self.sdk._failpoint = lambda stage: (_ for _ in ()).throw(RuntimeError("lost ACK")) if stage == "after_kernel_control_takeover" else None
        with self.assertRaisesRegex(RuntimeError, "lost ACK"):
            self.takeover()
        self.sdk.clock = lambda: now + 10
        self.lease["expires_at"] = now + 100
        self.sdk._failpoint = lambda _: None
        receipt = self.takeover()
        self.assertLess(receipt["claim"]["lease_expires_at"], now + 10)
        self.assertEqual(receipt["claim"]["new_fence"], 2)

    def test_confirmed_absent_pending_allows_higher_fence(self):
        self.prepare_activation()
        real_takeover = self.kernel.takeover_control_lease
        self.kernel.takeover_control_lease = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("before Kernel commit"))
        with self.assertRaisesRegex(RuntimeError, "before Kernel commit"):
            self.takeover()
        self.kernel.takeover_control_lease = real_takeover
        self.lease.update(lease_id="later", lease_fence=3)
        result = self.takeover()
        self.assertEqual(result["claim"]["previous_fence"], 1)
        self.assertEqual(result["claim"]["new_fence"], 3)
        with self.sdk._transaction() as c:
            old = c.execute("SELECT resolution,kernel_receipt FROM sdk_control_lease_takeovers WHERE takeover_id='handoff'").fetchone()
            self.assertIsNotNone(old[0])
            self.assertIsNone(old[1])

    def test_successor_pending_receipt_survives_newer_takeover(self):
        self.prepare_activation()
        self.takeover()
        self.lease.update(lease_id="second", lease_fence=3)
        self.sdk._failpoint = lambda stage: (_ for _ in ()).throw(RuntimeError("lost second ACK")) if stage == "after_kernel_control_takeover" else None
        with self.assertRaisesRegex(RuntimeError, "lost second ACK"):
            self.sdk.takeover_cross_store_control_lease("activation", phase="activation", takeover_id="second", credential="operator",
                lease_credential="lease", inspection_credential="inspect", takeover_credential="takeover")
        self.sdk._failpoint = lambda _: None
        self.lease.update(lease_id="third", lease_fence=4)
        third = self.sdk.takeover_cross_store_control_lease("activation", phase="activation", takeover_id="third", credential="operator",
            lease_credential="lease", inspection_credential="inspect", takeover_credential="takeover")
        self.assertEqual((third["claim"]["previous_fence"], third["claim"]["new_fence"]), (3, 4))
        with self.sdk._transaction() as c:
            rows = c.execute("SELECT new_fence,kernel_receipt FROM sdk_control_lease_takeovers ORDER BY new_fence").fetchall()
            self.assertEqual([row[0] for row in rows], [2, 3, 4])
            self.assertTrue(all(row[1] is not None for row in rows))

    def test_repeated_confirmed_absence_retains_intents(self):
        self.prepare_activation()
        real_takeover = self.kernel.takeover_control_lease
        self.kernel.takeover_control_lease = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("before Kernel commit"))
        for _ in range(3):
            with self.assertRaisesRegex(RuntimeError, "before Kernel commit"):
                self.takeover()
        self.kernel.takeover_control_lease = real_takeover
        self.assertEqual(self.takeover()["claim"]["new_fence"], 2)
        with self.sdk._transaction() as c:
            rows = c.execute("SELECT resolution,kernel_receipt FROM sdk_control_lease_takeovers ORDER BY rowid").fetchall()
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row[0] is not None and row[1] is None for row in rows[:-1]))
            self.assertIsNotNone(rows[-1][1])

    def test_historical_ack_does_not_authorize_changed_budget(self):
        self.prepare_activation()
        self.sdk._failpoint = lambda stage: (_ for _ in ()).throw(RuntimeError("lost ACK")) if stage == "after_kernel_control_takeover" else None
        with self.assertRaisesRegex(RuntimeError, "lost ACK"):
            self.takeover()
        self.sdk._failpoint = lambda _: None
        self.kernel.get_run_control = lambda _: {"state": "paused", "control_epoch": 4, "generation": 1, "max_claims": 1, "claims_used": 1, "deadline_at": 9999999999}
        self.takeover()
        with self.assertRaisesRegex(OrchestrationError, "budget facts changed"):
            self.sdk.activate_cross_store_revision("decision", operation_id="activation", credential="operator",
                lease_credential="lease", activation_credential="activation")

    def test_cancellation_blocks_takeover_before_kernel_call(self):
        self.prepare_activation()
        called = []
        self.kernel.takeover_control_lease = lambda *args, **kwargs: called.append(True)
        with self.sdk._transaction() as c:
            c.execute("INSERT INTO sdk_cancellation_fences VALUES('cancel','run',1,'kernel',?,?,4,NULL,NULL,1)",
                      (self.lease["orchestrator_store_id"], self.lease["orchestrator_incarnation"]))
        with self.assertRaisesRegex(OrchestrationError, "cancelled"):
            self.takeover()
        self.assertEqual(called, [])

    def test_reject_stale_and_unauthorized_takeover(self):
        self.prepare_activation()
        self.lease["lease_fence"] = 1
        with self.assertRaises(OrchestrationError):
            self.takeover()
        self.lease["lease_fence"] = 2
        with self.assertRaisesRegex(OrchestrationError, "authority denied"):
            self.takeover("bad")
        with self.sdk._transaction() as c:
            row = c.execute("SELECT kernel_receipt FROM sdk_control_lease_takeovers WHERE takeover_id='handoff'").fetchone()
            self.assertIsNone(row[0])
