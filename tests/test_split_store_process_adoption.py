"""Cross-process recovery of an interrupted split-store adoption.

The fixture seeds an unmanaged orchestration row and uses a simulated host
attestation. It does not establish real writer isolation or exercise Runtime.
"""
import multiprocessing
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.orchestrator import Orchestrator


class _WorkerVerifier:
    def __init__(self, expiry, admission):
        self.expiry = expiry
        self.admission = admission

    def __call__(self, credential):
        if credential != "resumed":
            raise ValueError("unexpected worker credential")
        return {"principal": "resumed", "expires_at": self.expiry,
                "permissions": [("legacy", "kernel:" + p) for p in
                                ("worker", "claim", "submit", "start", "budget", "work")],
                "run_id": "legacy", "generation": 1, "control_epoch": 4, **self.admission}


def _handler(payload, context):
    return {"execution_id": context.lease.execution_id, "attempt": context.lease.attempt,
            "fence": context.lease.fence, "pid": os.getpid()}


def _adopt_in_process(orchestrator_path, kernel_path, manifest, crash, results):
    expiry = manifest["isolation_expires_at"]

    def kernel_authority(credential):
        if credential == "adoption":
            return {"principal": "host", "expires_at": expiry,
                    "permissions": [("legacy", "kernel:import_legacy")], "adoption": manifest}
        return {"principal": "worker", "expires_at": expiry,
                "permissions": [("legacy", "kernel:worker")], "run_id": "legacy",
                "generation": 0, "control_epoch": 0}

    kernel = SQLiteKernel(kernel_path, authority_verifier=kernel_authority)
    sdk = Orchestrator(orchestrator_path, kernel, control_verifier=lambda _: {
        "principal": "operator", "permissions": [("legacy", "adopt_legacy")]})
    if crash:
        def failpoint(stage):
            if stage == "after_kernel_legacy_import":
                os._exit(73)
        sdk._failpoint = failpoint
    result = sdk.adopt_legacy_page(manifest, expected_run_revision=0, credential="operator",
                                   adoption_credential="adoption", worker_credential="worker")
    results.put((result["phase"], result["receipt"]["activation"]))
    kernel.close()


def _revise_in_process(orchestrator_path, kernel_path, manifest, phase, results):
    expiry = manifest["isolation_expires_at"]
    def authority(credential):
        if credential == "adoption":
            return {"principal": "host", "expires_at": expiry, "permissions": [("legacy", "kernel:import_legacy")], "adoption": manifest}
        if credential == "expired":
            return {"principal": "host", "expires_at": 1, "permissions": [("legacy", "kernel:import_legacy")], "adoption": manifest}
        if credential in ("changed", "revoked", "wrong-store"):
            altered = dict(manifest)
            altered.update({"changed": {"membership_source": "different"}, "revoked": {"isolation_held": False},
                            "wrong-store": {"orchestrator_incarnation": "different"}}[credential])
            return {"principal": "host", "expires_at": expiry, "permissions": [("legacy", "kernel:import_legacy")], "adoption": altered}
        return {"principal": "manager", "expires_at": expiry, "permissions": [("legacy", "kernel:pause")]}
    kernel = SQLiteKernel(kernel_path, authority_verifier=authority, worker_credential="manager")
    sdk = Orchestrator(orchestrator_path, kernel, control_verifier=lambda _: {"principal": "operator", "permissions": [("legacy", "pause"), ("legacy", "commit_revision")]})
    sdk.begin_adopted_cross_store_pause("adopt", credential="operator")
    if phase == "barrier":
        for rejected in ("expired", "changed", "revoked", "wrong-store"):
            try:
                sdk.advance_cross_store_pause("adopt", credential="operator", adoption_credential=rejected)
            except StorageIsolationError:
                pass
            else:
                raise AssertionError("invalid host authority was accepted: " + rejected)
            if kernel.get_run_control("legacy")["state"] != "paused":
                raise AssertionError("rejected host authority changed Kernel admission")
        def crash_after_barrier(stage):
            if stage == "after_kernel_pause_barrier":
                os._exit(74)
        sdk._failpoint = crash_after_barrier
    sdk.advance_cross_store_pause("adopt", credential="operator", adoption_credential="adoption")
    sdk.complete_cross_store_pause_participant("adopt", credential="operator")
    while not sdk.capture_cross_store_pause_page("adopt", credential="operator")["capture_complete"]:
        pass
    sdk.prepare_cross_store_pause("adopt", credential="operator")
    sdk.finalize_cross_store_pause("adopt", credential="operator")
    decision = sdk.commit_cross_store_revision("adopt", request_id="revision", credential="operator",
        expected_run_revision=0, expected_control_epoch=2, expected_generation=0,
        deployment={"handler": "v2"}, revision={"v": 2}, migration_version="m1",
        application_projection_version="p1", migrate=lambda state, revision: dict(state, revision=revision["v"]))
    results.put((decision["target_generation"], decision["target_application_state"]))
    kernel.close()


def _activate_in_process(orchestrator_path, kernel_path, manifest, results):
    expiry = manifest["isolation_expires_at"]
    envelope, activation, lease, budget, resume, admission, declaration = {}, {}, {}, {}, {}, {}, {}
    def authority(credential):
        permissions = {"decision": ("install_revision", "decision", envelope),
                       "activation": ("activate_revision", "activation", activation),
                       "budget": ("manage_budget", "budget_policy", budget),
                       "declare": ("declare_budget", "budget_declaration", declaration),
                       "resume": ("resume", "resume", resume)}
        if credential in permissions:
            permission, key, value = permissions[credential]
            return {"principal": "manager", "expires_at": expiry, "permissions": [("legacy", "kernel:" + permission)], key: dict(value)}
        if credential == "next":
            return {"principal": "next", "expires_at": expiry, "permissions": [("legacy", "kernel:worker")],
                    "run_id": "legacy", "generation": 1, "control_epoch": 3}
        if credential == "resumed":
            return {"principal": "resumed", "expires_at": expiry,
                    "permissions": [("legacy", "kernel:" + p) for p in ("worker", "claim", "submit", "start", "work")],
                    "run_id": "legacy", "generation": 1, "control_epoch": 4, **admission}
        raise ValueError("unexpected credential")
    kernel = SQLiteKernel(kernel_path, authority_verifier=authority)
    sdk = Orchestrator(orchestrator_path, kernel,
        control_verifier=lambda _: {"principal": "operator", "permissions": [("legacy", p) for p in ("install_revision", "activate_revision", "resume")]},
        control_lease_verifier=lambda _: dict(lease))
    with sdk._transaction() as db:
        operation = dict(db.execute("SELECT * FROM sdk_control_operations WHERE operation_id='adopt'").fetchone())
        decision = dict(db.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id='adopt'").fetchone())
    envelope.update(decision_id="adopt", operation_id="adopt", barrier_operation_id="adopt", run_id="legacy",
        orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"],
        kernel_store_id=operation["kernel_store_id"], source_revision=0, source_generation=0, source_control_epoch=2,
        target_generation=1, deployment={"handler": "v2"}, revision={"v": 2},
        source_application_state=json.loads(decision["source_application_state"]),
        target_application_state=json.loads(decision["target_application_state"]), content_pages={},
        migration_version="m1", application_projection_version="p1")
    installed = sdk.install_cross_store_revision("adopt", credential="operator", decision_credential="decision", worker_credential="next")
    projection = sdk.install_cross_store_projection("adopt", credential="operator")
    lease.update(operation_id="activate", run_id="legacy", kernel_store_id=operation["kernel_store_id"],
        orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"],
        lease_id="host-lease", lease_fence=1, expires_at=expiry, held=True, scope="resume_cancel_revoke_through_commit")
    activation.update(operation_id="activate", run_id="legacy", decision_id="adopt", barrier_operation_id="adopt",
        completion_operation_id="adopt:local-paused", kernel_store_id=operation["kernel_store_id"],
        orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"],
        generation=1, expected_control_epoch=3, orchestrator_install_receipt=json.loads(projection["orchestrator_install_receipt"]),
        kernel_install_receipt=json.loads(installed["kernel_install_receipt"]), lease_id="host-lease", lease_fence=1,
        lease_expires_at=expiry, lease_held=True)
    activated = sdk.activate_cross_store_revision("adopt", operation_id="activate", credential="operator",
        lease_credential="lease", activation_credential="activation")
    if kernel.get_run_control("legacy")["state"] != "paused" or sdk.get_managed_control("legacy")["control_state"] != "paused":
        raise AssertionError("activation opened admission")
    lease["operation_id"] = "adopt"
    budget.update(policy_id="budget", decision_id="adopt", run_id="legacy", generation=1,
        kernel_store_id=operation["kernel_store_id"], orchestrator_store_id=operation["orchestrator_store_id"],
        orchestrator_incarnation=operation["orchestrator_incarnation"], scopes=[{"owner": "app", "unit": "token", "source_id": "ledger"}])
    sdk.install_cross_store_budget_policy("adopt", policy=budget, credential="operator", lease_credential="lease", policy_credential="budget")
    lease["operation_id"] = "resume"
    resume.update(operation_id="resume", run_id="legacy", decision_id="adopt", barrier_operation_id="adopt",
        completion_operation_id="adopt:local-paused", activation_operation_id="activate", activation_receipt=json.loads(activated["kernel_receipt"]),
        kernel_store_id=operation["kernel_store_id"], orchestrator_store_id=operation["orchestrator_store_id"],
        orchestrator_incarnation=operation["orchestrator_incarnation"], generation=1, expected_control_epoch=3, target_control_epoch=4,
        orchestrator_install_receipt=json.loads(projection["orchestrator_install_receipt"]), kernel_install_receipt=json.loads(installed["kernel_install_receipt"]),
        lease_id="host-lease", lease_fence=1, lease_expires_at=expiry, lease_held=True)
    resumed = sdk.resume_cross_store_revision("activate", operation_id="resume", credential="operator", lease_credential="lease",
        resume_credential="resume", worker_credential="resumed")
    admission.update(control_lease={"held": True, "lease_id": "host-lease", "lease_fence": 1, "expires_at": expiry},
        global_admission={"open": True, "operation_id": "resume", "kernel_store_id": operation["kernel_store_id"],
            "orchestrator_store_id": operation["orchestrator_store_id"], "orchestrator_incarnation": operation["orchestrator_incarnation"],
            "orchestrator_receipt": json.loads(resumed["orchestrator_receipt"])})
    command = ExecutionCommandV2(execution_id="sdk-managed:legacy:new", idempotency_key="new-key", registry_revision="host-supplied",
        correlation_id="legacy", causation_id=None, handler_id="handler-v2", handler_contract_version=1,
        retry_policy=RetryPolicy(), timeout_seconds=5, payload={})
    declaration.update(run_id="legacy", generation=1, policy_id="budget", execution_id=command.execution_id,
        command=command.to_dict(), scopes=[], decision_id="adopt", kernel_store_id=operation["kernel_store_id"],
        orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"])
    kernel.declare_budget_dependencies("declare", expected_declaration=dict(declaration))
    worker = SQLiteKernel(kernel_path, authority_verifier=authority, worker_credential="resumed")
    worker.submit_managed(command, run_id="legacy", generation=1)
    claimed = worker.claim_and_start("worker", execution_id="sdk-managed:legacy:new")
    if claimed is None or claimed.execution_id != "sdk-managed:legacy:new":
        raise AssertionError("resumed execution was not claimed")
    from dispatcher_sdk.execution_kernel._process_runtime import invoke_process_handler
    outcome = invoke_process_handler(db_path=kernel_path, handler=_handler, command=command, lease=claimed,
        now=None, start_timeout=10, budget_envelope=worker._prepare_handler_entry(claimed),
        authority_verifier=_WorkerVerifier(expiry, admission), worker_credential="resumed")
    if outcome.get("kind") != "ok" or outcome["value"] != {"execution_id": claimed.execution_id,
            "attempt": claimed.attempt, "fence": claimed.fence, "pid": outcome["value"]["pid"]}:
        raise AssertionError("handler execution failed: " + repr(outcome))
    if outcome["value"]["pid"] == os.getpid():
        raise AssertionError("handler did not enter a separate process")
    control = kernel.get_run_control("legacy")
    results.put((json.loads(activated["kernel_receipt"])["state"], json.loads(resumed["orchestrator_receipt"])["state"],
                 control["claims_used"], control["max_claims"], control["deadline_at"], sdk.get_run("legacy")["application_state"]))
    worker.close()
    kernel.close()


class SplitStoreProcessAdoptionTests(unittest.TestCase):
    def test_replay_after_controller_process_exits_between_participant_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            orchestrator_path = str(Path(directory) / "orchestrator.sqlite")
            kernel_path = str(Path(directory) / "kernel.sqlite")
            deadline = time.time() + 300
            kernel = SQLiteKernel(kernel_path)
            sdk = Orchestrator(orchestrator_path, kernel)
            command = ExecutionCommandV2(
                execution_id="legacy-execution", idempotency_key="legacy-key",
                registry_revision="host-supplied", correlation_id="legacy", causation_id=None,
                handler_id="handler", handler_contract_version=1, retry_policy=RetryPolicy(),
                timeout_seconds=1, payload={})
            kernel.submit(command)
            # Build a small pre-existing Run without invoking the old create receipt path.
            with sdk._transaction() as db:
                db.execute("INSERT INTO sdk_runs VALUES('legacy',0,'running')")
                state = {"run_id": "legacy", "revision": 0, "state": "running", "generation": 0,
                         "input": None, "definition": {}, "application_state": {"wait": "pending"},
                         "tasks": {}, "waits": {}, "signals": {}}
                sdk._save(db, state)
                sdk._event(db, state, "legacy.waiting", {"value": "retained"})
                identity = db.execute("SELECT store_id,incarnation FROM sdk_storage_identity").fetchone()
            manifest = {"operation_id": "adopt", "run_id": "legacy",
                        "kernel_store_id": kernel.kernel_store_identity(),
                        "orchestrator_store_id": identity[0], "orchestrator_incarnation": identity[1],
                        "generation": 0, "membership": [{"execution_id": "legacy-execution", "status": "accepted"}],
                        "membership_source": "fixture", "membership_complete": True, "page_seq": 0,
                        "claims_used": 3, "claims_source": "fixture", "max_claims": 7,
                        "deadline_at": deadline, "isolation_lease_id": "fixture-lease",
                        "isolation_expires_at": deadline, "isolation_held": True}
            kernel.close()
            context = multiprocessing.get_context("spawn")
            results = context.Queue()
            crashed = context.Process(target=_adopt_in_process, args=(orchestrator_path, kernel_path, manifest, True, results))
            crashed.start()
            crashed.join(20)
            self.assertFalse(crashed.is_alive())
            self.assertEqual(crashed.exitcode, 73)
            kernel = SQLiteKernel(kernel_path)
            sdk = Orchestrator(orchestrator_path, kernel)
            self.assertEqual(kernel.get_run_control("legacy")["state"], "paused")
            with sdk._transaction() as db:
                self.assertIsNone(db.execute("SELECT kernel_receipt FROM sdk_legacy_adoption_pages").fetchone()[0])
            kernel.close()
            resumed = context.Process(target=_adopt_in_process, args=(orchestrator_path, kernel_path, manifest, False, results))
            resumed.start()
            resumed.join(20)
            self.assertFalse(resumed.is_alive())
            self.assertEqual(resumed.exitcode, 0)
            self.assertEqual(results.get(timeout=2), ("paused", "closed"))
            kernel = SQLiteKernel(kernel_path)
            sdk = Orchestrator(orchestrator_path, kernel)
            control = kernel.get_run_control("legacy")
            self.assertEqual((control["state"], control["claims_used"], control["max_claims"], control["deadline_at"]),
                             ("paused", 3, 7, deadline))
            self.assertEqual(kernel.get("legacy-execution").state, "queued")
            self.assertIsNone(kernel.claim("old-worker"))
            self.assertEqual(sdk.get_run("legacy")["application_state"], {"wait": "pending"})
            with sdk._transaction() as db:
                self.assertEqual(db.execute("SELECT kind FROM sdk_events WHERE run_id='legacy'").fetchone()[0], "legacy.waiting")
            kernel.close()
            process = context.Process(target=_revise_in_process, args=(orchestrator_path, kernel_path, manifest, "barrier", results))
            process.start()
            process.join(20)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 74)
            kernel = SQLiteKernel(kernel_path)
            sdk = Orchestrator(orchestrator_path, kernel)
            self.assertEqual((kernel.get_run_control("legacy")["state"], kernel.get_run_control("legacy")["control_epoch"]), ("pausing", 1))
            with kernel._transaction() as (db, _):
                barrier_receipt = json.loads(db.execute("SELECT receipt_json FROM kernel_control_pause_receipts WHERE operation_id='adopt'").fetchone()[0])
            self.assertEqual((barrier_receipt["claims_used"], barrier_receipt["max_claims"], barrier_receipt["deadline_at"]), (3, 7, deadline))
            with sdk._transaction() as db:
                self.assertIsNone(db.execute("SELECT kernel_receipt FROM sdk_control_operations WHERE operation_id='adopt'").fetchone()[0])
            kernel.close()
            manifest["isolation_expires_at"] += 60
            process = context.Process(target=_revise_in_process, args=(orchestrator_path, kernel_path, manifest, "commit", results))
            process.start()
            process.join(20)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(results.get(timeout=2), (1, '{"revision":2,"wait":"pending"}'))
            kernel = SQLiteKernel(kernel_path)
            sdk = Orchestrator(orchestrator_path, kernel)
            with sdk._transaction() as db:
                self.assertEqual(json.loads(db.execute("SELECT kernel_receipt FROM sdk_control_operations WHERE operation_id='adopt'").fetchone()[0]), barrier_receipt)
            kernel.close()
            process = context.Process(target=_activate_in_process, args=(orchestrator_path, kernel_path, manifest, results))
            process.start()
            process.join(20)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(results.get(timeout=2), ("paused", "active", 4, 7, deadline, {"revision": 2, "wait": "pending"}))
            results.close()


if __name__ == "__main__":
    unittest.main()
