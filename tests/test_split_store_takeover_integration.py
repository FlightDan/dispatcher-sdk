"""Real SQLite split-store takeover with synthetic host claims, no Runtime."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.orchestrator import Orchestrator, OrchestrationError
from tests.test_split_store_process_adoption import _adopt_in_process, _revise_in_process

class Sink:
    def put(self, _value): pass

def exercise_takeover(orchestrator_path, kernel_path, manifest):
    expiry = manifest["isolation_expires_at"]
    envelope, activation, lease, budget, resume, admission, declaration = {}, {}, {}, {}, {}, {}, {}
    host_claims = {}
    def authority(credential):
        permissions = {"decision": ("install_revision", "decision", envelope),
                       "activation": ("activate_revision", "activation", activation),
                       "budget": ("manage_budget", "budget_policy", budget),
                       "declare": ("declare_budget", "budget_declaration", declaration),
                       "resume": ("resume", "resume", resume)}
        if credential in permissions:
            permission, key, value = permissions[credential]
            return {"principal": "manager", "expires_at": expiry, "permissions": [("legacy", "kernel:" + permission)], key: dict(value)}
        if credential in ("inspection", "takeover"):
            permission = "inspect_control" if credential == "inspection" else "takeover_control"
            return {"principal": "host", "expires_at": expiry,
                    "permissions": [("legacy", "kernel:" + permission)], **host_claims}
        if credential == "next":
            return {"principal": "next", "expires_at": expiry, "permissions": [("legacy", "kernel:worker")],
                    "run_id": "legacy", "generation": 1, "control_epoch": 3}
        if credential == "resumed":
            return {"principal": "resumed", "expires_at": expiry,
                    "permissions": [("legacy", "kernel:" + p) for p in ("worker", "claim", "submit", "start", "work")],
                    "run_id": "legacy", "generation": 1, "control_epoch": 4, **admission}
        raise ValueError("unexpected credential")
    kernel = SQLiteKernel(kernel_path, authority_verifier=authority)
    # The synthetic host attests exact coordinator requests; this does not prove
    # real exclusive-writer isolation or independent host enforcement.
    for name, field in (("inspect_control_participant_receipt", "control_receipt_inspection"),
                        ("inspect_control_takeover", "control_takeover_inspection"),
                        ("takeover_control_lease", "control_takeover")):
        original = getattr(kernel, name)
        argument = "expected_takeover" if name == "takeover_control_lease" else "expected_inspection"
        def wrapper(credential, *, _original=original, _argument=argument, _field=field, **kwargs):
            host_claims[_field] = json.loads(json.dumps(kwargs[_argument]))
            return _original(credential, **kwargs)
        setattr(kernel, name, wrapper)
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
    def failpoint(stage):
        if stage == "after_kernel_revision_activation":
            raise RuntimeError("lost activation acknowledgement")
    sdk._failpoint = failpoint
    try:
        sdk.activate_cross_store_revision("adopt", operation_id="activate", credential="operator",
            lease_credential="lease", activation_credential="activation")
    except RuntimeError as error:
        assert str(error) == "lost activation acknowledgement"
    else:
        raise AssertionError("lost ACK not exercised")
    with sdk._transaction() as db:
        assert db.execute("SELECT kernel_receipt FROM sdk_revision_activations WHERE operation_id='activate'").fetchone()[0] is None
    kernel.close()
    # A new Kernel connection models the controller restarting with the same durable stores.
    kernel = SQLiteKernel(kernel_path, authority_verifier=authority)
    for name, field in (("inspect_control_participant_receipt", "control_receipt_inspection"),
                        ("inspect_control_takeover", "control_takeover_inspection"),
                        ("takeover_control_lease", "control_takeover")):
        original = getattr(kernel, name)
        argument = "expected_takeover" if name == "takeover_control_lease" else "expected_inspection"
        def wrapper(credential, *, _original=original, _argument=argument, _field=field, **kwargs):
            host_claims[_field] = json.loads(json.dumps(kwargs[_argument]))
            return _original(credential, **kwargs)
        setattr(kernel, name, wrapper)
    sdk.kernel = kernel
    sdk._failpoint = lambda _: None
    lease.update(lease_id="successor", lease_fence=2)
    takeover = sdk.takeover_cross_store_control_lease("activate", phase="activation", takeover_id="handoff",
        credential="operator", lease_credential="lease", inspection_credential="inspection", takeover_credential="takeover")
    assert takeover["claim"]["new_fence"] == 2
    # Host no longer attests the former lease, and Orchestrator rejects it.
    lease.update(lease_id="host-lease", lease_fence=1)
    try:
        sdk.activate_cross_store_revision("adopt", operation_id="activate", credential="operator",
            lease_credential="lease", activation_credential="activation")
    except OrchestrationError:
        pass
    else:
        raise AssertionError("stale lease was accepted")
    lease.update(lease_id="successor", lease_fence=2)
    activation.update(lease_id="successor", lease_fence=2)
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
        lease_id="successor", lease_fence=2, lease_expires_at=expiry, lease_held=True)
    resumed = sdk.resume_cross_store_revision("activate", operation_id="resume", credential="operator", lease_credential="lease",
        resume_credential="resume", worker_credential="resumed")
    admission.update(control_lease={"held": True, "lease_id": "successor", "lease_fence": 2, "expires_at": expiry},
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
    control = kernel.get_run_control("legacy")
    assert (control["claims_used"], control["max_claims"], control["deadline_at"]) == (4, 7, manifest["deadline_at"])
    assert kernel.get("legacy-execution").execution_id == "legacy-execution"
    assert sdk.get_run("legacy")["application_state"] == {"revision": 2, "wait": "pending"}
    worker.close()
    kernel.close()

class SplitStoreTakeoverIntegrationTests(unittest.TestCase):
    def test_activation_lost_ack_takeover_then_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            opath, kpath = str(Path(directory) / 'orchestrator.sqlite'), str(Path(directory) / 'kernel.sqlite')
            deadline = time.time() + 300
            kernel = SQLiteKernel(kpath)
            sdk = Orchestrator(opath, kernel)
            command = ExecutionCommandV2(execution_id='legacy-execution', idempotency_key='legacy-key',
                registry_revision='host-supplied', correlation_id='legacy', causation_id=None, handler_id='handler',
                handler_contract_version=1, retry_policy=RetryPolicy(), timeout_seconds=1, payload={})
            kernel.submit(command)
            with sdk._transaction() as db:
                db.execute("INSERT INTO sdk_runs VALUES('legacy',0,'running')")
                state = {'run_id': 'legacy', 'revision': 0, 'state': 'running', 'generation': 0,
                         'input': None, 'definition': {}, 'application_state': {'wait': 'pending'},
                         'tasks': {}, 'waits': {}, 'signals': {}}
                sdk._save(db, state)
                identity = db.execute('SELECT store_id,incarnation FROM sdk_storage_identity').fetchone()
            manifest = {'operation_id': 'adopt', 'run_id': 'legacy', 'kernel_store_id': kernel.kernel_store_identity(),
                'orchestrator_store_id': identity[0], 'orchestrator_incarnation': identity[1], 'generation': 0,
                'membership': [{'execution_id': 'legacy-execution', 'status': 'accepted'}],
                'membership_source': 'fixture', 'membership_complete': True, 'page_seq': 0, 'claims_used': 3,
                'claims_source': 'fixture', 'max_claims': 7, 'deadline_at': deadline,
                'isolation_lease_id': 'fixture-lease', 'isolation_expires_at': deadline, 'isolation_held': True}
            kernel.close()
            _adopt_in_process(opath, kpath, manifest, False, Sink())
            _revise_in_process(opath, kpath, manifest, 'commit', Sink())
            exercise_takeover(opath, kpath, manifest)
