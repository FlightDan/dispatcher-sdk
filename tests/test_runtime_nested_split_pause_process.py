"""Real nested Runtime against split stores; host authority is simulated.

Registry revision checks are mocked for the test lifetime. The simulated
authority and lease do not establish actual host isolation.
"""
import json
import os
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import CASConflictError, ExecutionCommandV2, Kernel, RetryPolicy, SQLiteKernel, runtime as runtime_module
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.orchestrator import Orchestrator
from tests.test_split_store_process_adoption import _adopt_in_process, _revise_in_process


def _identity(context, directory, name):
    value = {"execution_id": context.lease.execution_id, "attempt": context.lease.attempt,
             "fence": context.lease.fence, "pid": os.getpid()}
    Path(directory, name + ".json").write_text(json.dumps(value))
    return value


def _a(payload, context):
    _identity(context, payload["directory"], "A")
    return context.children.run("B", payload, request_id="A-B", timeout_seconds=35)


def _b(payload, context):
    _identity(context, payload["directory"], "B")
    return context.children.run("C", payload, request_id="B-C", timeout_seconds=30)


def _c(payload, context):
    identity = _identity(context, payload["directory"], "C")
    deadline = time.monotonic() + 20
    while not Path(payload["directory"], "release").exists() and time.monotonic() < deadline:
        time.sleep(.02)
    return identity


def _new(payload, context):
    return _identity(context, payload["directory"], "new")


class _WorkerAuthority:
    def __init__(self, expiry, generation, epoch, admission):
        self.expiry, self.generation, self.epoch, self.admission = expiry, generation, epoch, admission

    def __call__(self, credential):
        if credential != "worker":
            raise ValueError("unknown worker")
        return {"principal": "next", "expires_at": self.expiry,
                "permissions": [("legacy", "kernel:" + name) for name in
                    ("worker", "claim", "submit", "start", "work", "child", "budget")],
                "run_id": "legacy", "generation": self.generation, "control_epoch": self.epoch,
                **self.admission}


class _Controller:
    def __init__(self, orchestrator_path, kernel_path, expiry):
        self.expiry = expiry
        self.proofs, self.lease = {}, {}
        self.kernel = SQLiteKernel(kernel_path, authority_verifier=self.authority, worker_credential="controller")
        self.sdk = Orchestrator(orchestrator_path, self.kernel,
            control_verifier=lambda _: {"principal": "operator", "permissions": [("legacy", p) for p in
                ("pause", "commit_revision", "install_revision", "activate_revision", "resume")]},
            control_lease_verifier=lambda _: dict(self.lease))

    def authority(self, credential):
        if credential == "controller":
            return {"principal": "controller", "expires_at": self.expiry,
                    "permissions": [("legacy", "kernel:pause")]}
        if credential == "next":
            return {"principal": "next", "expires_at": self.expiry,
                    "permissions": [("legacy", "kernel:worker")], "run_id": "legacy",
                    "generation": self.next_generation, "control_epoch": self.next_epoch}
        permission, key, value = self.proofs[credential]
        return {"principal": "manager", "expires_at": self.expiry,
                "permissions": [("legacy", "kernel:" + permission)], key: dict(value)}

    def activate_resume(self, operation_id, activation_id, resume_id):
        sdk = self.sdk
        with sdk._transaction() as db:
            operation = dict(db.execute("SELECT * FROM sdk_control_operations WHERE operation_id=?", (operation_id,)).fetchone())
            decision = dict(db.execute("SELECT * FROM sdk_revision_decisions WHERE operation_id=?", (operation_id,)).fetchone())
        gen, source_epoch = decision["target_generation"], decision["source_epoch"]
        self.next_generation, self.next_epoch = gen, source_epoch + 1
        common = {"run_id": "legacy", "kernel_store_id": operation["kernel_store_id"],
                  "orchestrator_store_id": operation["orchestrator_store_id"],
                  "orchestrator_incarnation": operation["orchestrator_incarnation"]}
        envelope = {**common, "decision_id": operation_id, "operation_id": operation_id,
            "barrier_operation_id": operation_id, "source_revision": decision["source_revision"],
            "source_generation": decision["source_generation"], "source_control_epoch": source_epoch,
            "target_generation": gen, "deployment": json.loads(decision["deployment"]),
            "revision": json.loads(decision["decision"])["revision"],
            "source_application_state": json.loads(decision["source_application_state"]),
            "target_application_state": json.loads(decision["target_application_state"]),
            "content_pages": {}, "migration_version": decision["migration_version"],
            "application_projection_version": decision["application_projection_version"]}
        self.proofs["decision"] = ("install_revision", "decision", envelope)
        installed = sdk.install_cross_store_revision(operation_id, credential="operator", decision_credential="decision", worker_credential="next")
        projection = sdk.install_cross_store_projection(operation_id, credential="operator")
        self.lease = {**common, "operation_id": activation_id, "lease_id": "host-lease", "lease_fence": 1,
            "expires_at": self.expiry, "held": True, "scope": "resume_cancel_revoke_through_commit"}
        receipts = {"orchestrator_install_receipt": json.loads(projection["orchestrator_install_receipt"]),
                    "kernel_install_receipt": json.loads(installed["kernel_install_receipt"])}
        lease_fields = {"lease_id": "host-lease", "lease_fence": 1, "lease_expires_at": self.expiry, "lease_held": True}
        activation = {**common, **receipts, **lease_fields, "operation_id": activation_id, "decision_id": operation_id,
            "barrier_operation_id": operation_id, "completion_operation_id": operation_id + ":local-paused",
            "generation": gen, "expected_control_epoch": source_epoch + 1}
        self.proofs["activation"] = ("activate_revision", "activation", activation)
        activated = sdk.activate_cross_store_revision(operation_id, operation_id=activation_id, credential="operator",
            lease_credential="lease", activation_credential="activation")
        assert self.kernel.get_run_control("legacy")["state"] == "paused"
        self.lease["operation_id"] = operation_id
        policy = {**common, "policy_id": "budget-" + operation_id, "decision_id": operation_id,
                  "generation": gen, "scopes": []}
        self.proofs["budget"] = ("manage_budget", "budget_policy", policy)
        sdk.install_cross_store_budget_policy(operation_id, policy=policy, credential="operator",
            lease_credential="lease", policy_credential="budget")
        self.lease["operation_id"] = resume_id
        resume = {**common, **receipts, **lease_fields, "operation_id": resume_id, "decision_id": operation_id,
            "barrier_operation_id": operation_id, "completion_operation_id": operation_id + ":local-paused",
            "activation_operation_id": activation_id, "activation_receipt": json.loads(activated["kernel_receipt"]),
            "generation": gen, "expected_control_epoch": source_epoch + 1, "target_control_epoch": source_epoch + 2}
        self.proofs["resume"] = ("resume", "resume", resume)
        self.next_epoch = source_epoch + 2
        resumed = sdk.resume_cross_store_revision(activation_id, operation_id=resume_id, credential="operator",
            lease_credential="lease", resume_credential="resume", worker_credential="next")
        admission = {"control_lease": {"held": True, "lease_id": "host-lease", "lease_fence": 1, "expires_at": self.expiry},
            "global_admission": {"open": True, "operation_id": resume_id, **{key: common[key] for key in
                ("kernel_store_id", "orchestrator_store_id", "orchestrator_incarnation")},
                "orchestrator_receipt": json.loads(resumed["orchestrator_receipt"])}}
        return gen, source_epoch + 2, admission


@unittest.skipUnless(os.name == "posix", "requires POSIX process containment")
class NestedSplitPauseTests(unittest.TestCase):
    def test_active_nested_chain_pause_revision_resume(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            kernel_path, orchestrator_path = (str(Path(directory) / name) for name in ("kernel.sqlite", "orchestrator.sqlite"))
            expiry = time.time() + 300
            kernel = SQLiteKernel(kernel_path)
            sdk = Orchestrator(orchestrator_path, kernel)
            legacy = ExecutionCommandV2(execution_id="legacy-execution", idempotency_key="legacy-key",
                registry_revision="fixture-handler", correlation_id="legacy", causation_id=None, handler_id="new",
                handler_contract_version=1, retry_policy=RetryPolicy(), timeout_seconds=5, payload={})
            kernel.submit(legacy)
            with sdk._transaction() as db:
                db.execute("INSERT INTO sdk_runs VALUES('legacy',0,'running')")
                state = {"run_id": "legacy", "revision": 0, "state": "running", "generation": 0,
                         "input": None, "definition": {}, "application_state": {"wait": "pending"},
                         "tasks": {}, "waits": {}, "signals": {}}
                sdk._save(db, state)
                sdk._event(db, state, "legacy.waiting", {"value": "retained"})
                identity = db.execute("SELECT store_id,incarnation FROM sdk_storage_identity").fetchone()
            manifest = {"operation_id": "adopt", "run_id": "legacy", "kernel_store_id": kernel.kernel_store_identity(),
                "orchestrator_store_id": identity[0], "orchestrator_incarnation": identity[1], "generation": 0,
                "membership": [{"execution_id": "legacy-execution", "status": "accepted"}],
                "membership_source": "fixture", "membership_complete": True, "page_seq": 0,
                "claims_used": 0, "claims_source": "fixture", "max_claims": 12, "deadline_at": expiry,
                "isolation_lease_id": "fixture-lease", "isolation_expires_at": expiry, "isolation_held": True}
            kernel.close()
            results = queue.Queue()
            _adopt_in_process(orchestrator_path, kernel_path, manifest, False, results)
            _revise_in_process(orchestrator_path, kernel_path, manifest, "commit", results)
            controller = _Controller(orchestrator_path, kernel_path, expiry)
            runtime = None
            driver = None
            errors, outcomes = [], []
            try:
                generation, epoch, admission = controller.activate_resume("adopt", "initial-activate", "initial-resume")
                self.assertEqual((generation, epoch), (1, 4))
                receiver = {'generation': generation}
                def verify_lifecycle(credential, operation, identity, event):
                    allowed = (credential == 'worker' and identity['run_id'] == 'legacy'
                               and identity['generation'] == receiver['generation'])
                    committed = False
                    if allowed and operation == 'ack' and receiver.get('runtime') is not None:
                        committed = receiver['runtime']._settlement_journal.lifecycle_receipt_committed(
                            {key: identity[key] for key in ('execution_id', 'attempt', 'fence')},
                            event['phase'], event['payload'], store_id=event['store_id'],
                            outbox_sequence=event['sequence'])
                    return {'allowed': allowed, 'expires_at': expiry, 'receiver_committed': committed}
                runtime = Kernel.open_sqlite(kernel_path, {"A": _a, "B": _b, "C": _c, "new": _new},
                    isolation_mode="process", child_capacity=2, max_child_depth=2,
                    authority_verifier=_WorkerAuthority(expiry, generation, epoch, admission), worker_credential="worker",
                    lifecycle_verifier=verify_lifecycle)
                receiver['runtime'] = runtime
                command = runtime.command("A", execution_id="sdk-managed:legacy:A", idempotency_key="nested-A",
                    correlation_id="legacy", timeout_seconds=45, payload={"directory": directory})
                runtime.submit_managed(command, run_id="legacy", generation=generation)
                def run():
                    try:
                        outcomes.append(runtime.run_once(execution_id=command.execution_id))
                    except BaseException as error:
                        errors.append(repr(error))
                driver = threading.Thread(target=run)
                driver.start()
                deadline = time.monotonic() + 20
                while not Path(directory, "C.json").exists() and driver.is_alive() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(Path(directory, "C.json").exists(), (errors, outcomes,
                    runtime._diagnostic_errors, runtime._lifecycle_delivery_error))
                identities = {name: json.loads(Path(directory, name + ".json").read_text()) for name in ("A", "B", "C")}
                self.assertEqual(len({item["pid"] for item in identities.values()}), 3)
                for item in identities.values():
                    self.assertEqual(runtime.kernel.get(item["execution_id"]).state, "running")
                for parent, child in (("A", "B"), ("B", "C")):
                    self.assertEqual(runtime.kernel.get_execution_limits(identities[child]["execution_id"])["parent_execution_id"], identities[parent]["execution_id"])
                before = controller.kernel.get_run_control("legacy")
                self.assertEqual(before["claims_used"], 3)
                sdk = controller.sdk
                current = sdk.get_run("legacy")
                operation = sdk.begin_cross_store_pause("legacy", operation_id="nested-pause", expected_run_revision=current["revision"],
                    expected_control_epoch=epoch, credential="operator")
                sdk.advance_cross_store_pause("nested-pause", credential="operator")
                sdk.complete_cross_store_pause_participant("nested-pause", credential="operator")
                pages = []
                while True:
                    page = sdk.capture_cross_store_pause_page("nested-pause", credential="operator")
                    pages.append(page)
                    if page["capture_complete"]:
                        break
                prepared = sdk.prepare_cross_store_pause("nested-pause", credential="operator")
                sdk.finalize_cross_store_pause("nested-pause", credential="operator")
                self.assertEqual(controller.kernel.get_run_control("legacy")["state"], "paused")
                self.assertEqual(sdk.get_managed_control("legacy")["control_state"], "paused")
                denied = runtime.command("new", execution_id="sdk-managed:legacy:denied", idempotency_key="denied",
                    correlation_id="legacy", timeout_seconds=10, payload={"directory": directory})
                with self.assertRaises((CASConflictError, StorageIsolationError)):
                    runtime.submit_managed(denied, run_id="legacy", generation=generation)
                captured = {item["execution_id"] for page in pages for item in page["items"]}
                self.assertTrue({value["execution_id"] for value in identities.values()} <= captured)
                self.assertIn("unknown", prepared["prepared_evidence"])
                decision = sdk.commit_cross_store_revision("nested-pause", request_id="nested-revision", credential="operator",
                    expected_run_revision=current["revision"], expected_control_epoch=epoch + 2, expected_generation=generation,
                    deployment={"handler": "v3"}, revision={"v": 3}, migration_version="m2",
                    application_projection_version="p2", migrate=lambda state, revision: dict(state, revision=revision["v"]))
                self.assertEqual(decision["target_generation"], 2)
                next_generation, next_epoch, next_admission = controller.activate_resume("nested-pause", "next-activate", "next-resume")
                self.assertEqual(next_generation, 2)
                after = controller.kernel.get_run_control("legacy")
                self.assertEqual((after["deadline_at"], after["max_claims"]), (before["deadline_at"], before["max_claims"]))
                self.assertGreaterEqual(after["claims_used"], before["claims_used"])
                Path(directory, "release").touch()
                driver.join(15)
                self.assertFalse(driver.is_alive(), errors)
                self.assertEqual(errors, [])
                for node, identity in identities.items():
                    snapshot = runtime.kernel.get(identity["execution_id"])
                    self.assertEqual((snapshot.attempt, snapshot.fence), (identity["attempt"], identity["fence"]), node)
                    records = runtime.kernel.inspect_supervisor_obligations(identity["execution_id"])["obligations"]
                    self.assertEqual(len(records), 1, (node, snapshot.to_dict(), records))
                    self.assertEqual((records[0]["attempt"], records[0]["fence"]),
                                     (identity["attempt"], identity["fence"]))
                with self.assertRaises((CASConflictError, StorageIsolationError)):
                    runtime.submit_managed(denied, run_id="legacy", generation=generation)
                fresh = Kernel.open_sqlite(kernel_path, {"new": _new}, isolation_mode="process",
                    authority_verifier=_WorkerAuthority(expiry, next_generation, next_epoch, next_admission), worker_credential="worker",
                    lifecycle_verifier=verify_lifecycle)
                receiver['runtime'] = fresh
                receiver['generation'] = next_generation
                try:
                    cmd = fresh.command("new", execution_id="sdk-managed:legacy:new2", idempotency_key="new2",
                        correlation_id="legacy", timeout_seconds=15, payload={"directory": directory})
                    fresh.submit_managed(cmd, run_id="legacy", generation=next_generation)
                    result = fresh.run_once(execution_id=cmd.execution_id)
                    self.assertEqual(result.state, "succeeded")
                    self.assertNotEqual(result.result.value["pid"], os.getpid())
                    fresh_obligation = fresh.kernel.inspect_supervisor_obligations(cmd.execution_id)["obligations"][0]
                    self.assertEqual(fresh_obligation["resolution"]["result_id"], result.result.result_id)
                    self.assertEqual(fresh.kernel.get_run_control("legacy")["claims_used"], after["claims_used"] + 1)
                    with sdk._transaction() as db:
                        self.assertEqual(db.execute("SELECT kind FROM sdk_events WHERE run_id='legacy' ORDER BY sequence LIMIT 1").fetchone()[0], "legacy.waiting")
                finally:
                    fresh.close()
            finally:
                Path(directory, "release").touch()
                if driver is not None:
                    driver.join(25)
                if runtime is not None:
                    runtime.close()
                controller.kernel.close()
