"""Controlled legacy update integration using isolated stores and simulated authority.

All existing digest paths are stubbed. This proves no host isolation or real Run acceptance.
"""
import hashlib
import json
import multiprocessing
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.maintenance import maintenance_lease
from dispatcher_sdk.orchestrator import Orchestrator, RevisionConflict
from dispatcher_sdk.storage_migration import upgrade_storage
from tests.test_legacy_schema_split_store_lifecycle import _seed_legacy
from tests.test_split_store_process_adoption import _adopt_in_process, _revise_in_process, _WorkerVerifier, _handler

# Fixture tokens stand in for existing SDK bookkeeping; no digest computation occurs.
_tokens = {}
def _fake_sha256(value=b""):
    class Token:
        def __init__(self, raw): self.raw = bytes(raw)
        def update(self, raw): self.raw += bytes(raw)
        def digest(self):
            if self.raw not in _tokens: _tokens[self.raw] = len(_tokens) + 1
            return _tokens[self.raw].to_bytes(32, "big")
        def hexdigest(self): return self.digest().hex()
        def copy(self): return Token(self.raw)
    return Token(value)

class _Results:
    def __init__(self): self.value = None
    def put(self, value): self.value = value


class _LifecycleHost:
    """Synthetic trusted host with an independent durable producer registry."""
    def __init__(self, kernel_path, execution_id, expiry):
        self.kernel_path, self.execution_id, self.expiry = kernel_path, execution_id, expiry
        self.path = str(kernel_path) + '.fixture-host.sqlite'
        self.binding = None
        self.acks = 0
        self.last_error = None
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS producers(token TEXT PRIMARY KEY, identity TEXT NOT NULL)')

    def __call__(self, credential, operation, identity, event):
        allowed = (credential == 'resumed' and identity['run_id'] == 'legacy'
                   and identity['generation'] == 1 and identity['execution_id'] == self.execution_id
                   and identity['attempt'] > 0 and identity['fence'] > 0)
        if operation == 'reserve' and allowed:
            token = event['producer_id']
            encoded = json.dumps(identity, sort_keys=True)
            with sqlite3.connect(self.path, timeout=1) as db:
                db.execute('INSERT OR IGNORE INTO producers VALUES(?,?)', (token, encoded))
                allowed = db.execute('SELECT identity FROM producers WHERE token=?', (token,)).fetchone()[0] == encoded
        result = {'allowed': allowed, 'expires_at': self.expiry}
        if operation == 'ack' and allowed:
            binding = self.binding
            try:
                journal = SettlementJournal.open_readonly(binding['path'], source_id=binding['source_id'],
                    kernel_path=binding['kernel_path'], timeout_seconds=0.1)
                committed = journal.lifecycle_receipt_committed(
                    {key: identity[key] for key in ('execution_id', 'attempt', 'fence')},
                    event['phase'], event['payload'], store_id=event['store_id'],
                    outbox_sequence=event['sequence'])
            except Exception as exc:
                self.last_error = repr(exc)
                raise
            result['receiver_committed'] = committed
            if result['receiver_committed']:
                self.acks += 1
        return result

def _activate_with_runtime(orchestrator_path, kernel_path, manifest, results):
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
        control_verifier=lambda _: {"principal": "operator", "permissions": [("legacy", p) for p in ("install_revision", "activate_revision", "resume", "apply_operations")]},
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
    command = ExecutionCommandV2(execution_id="sdk-managed:legacy:new", idempotency_key="new-key", registry_revision="fixture-handler",
        correlation_id="legacy", causation_id=None, handler_id="handler-v2", handler_contract_version=1,
        retry_policy=RetryPolicy(), timeout_seconds=5, payload={})
    declaration.update(run_id="legacy", generation=1, policy_id="budget", execution_id=command.execution_id,
        command=command.to_dict(), scopes=[], decision_id="adopt", kernel_store_id=operation["kernel_store_id"],
        orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"])
    kernel.declare_budget_dependencies("declare", expected_declaration=dict(declaration))
    from unittest.mock import patch
    from dispatcher_sdk.execution_kernel import Kernel, runtime as runtime_module
    # Keep both registry functions patched for the full Runtime lifetime.
    # Registry validation is mocked; no fingerprint code is executed.
    with patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
         patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
        lifecycle_host = _LifecycleHost(kernel_path, command.execution_id, expiry)
        runtime = Kernel.open_sqlite(kernel_path, {"handler-v2": _handler}, isolation_mode="process",
            authority_verifier=_WorkerVerifier(expiry, admission), worker_credential="resumed",
            lifecycle_verifier=lifecycle_host)
        lifecycle_host.binding = runtime.settlement_storage
        try:
            sdk.kernel = runtime.kernel
            sdk.runtime = runtime
            observed = sdk.observe("legacy", subscription="policy")
            original = observed["snapshot"]
            ops = [{"kind": "add_task", "task_id": "next", "command": command.to_dict(), "dependencies": []},
                   {"kind": "watch_task", "task_id": "next", "watch_id": "watch-next", "target": {"kind": "test"}},
                   {"kind": "dispatch", "task_id": "next"}]
            args = dict(command_id="policy-update", expected_revision=original["revision"],
                expected_generation=1, expected_control_epoch=4, source_resume_operation_id="resume",
                credential="operator", lease_credential="lease", operations=ops,
                application_state={"revision": 2, "wait": "resolved"}, subscription="policy",
                expected_cursor=observed["cursor"], advance_to=observed["events"][-1]["sequence"])
            try:
                sdk.apply_managed_operations("legacy", **{**args, "expected_control_epoch": 3})
            except RevisionConflict:
                pass
            else:
                raise AssertionError("stale control epoch was accepted")
            if sdk.get_subscription("legacy", "policy") != observed["cursor"]:
                raise AssertionError("rejected update advanced the cursor")
            applied = sdk.apply_managed_operations("legacy", **args)
            if applied["application_state"]["wait"] != "resolved" or "next" not in applied["tasks"]:
                raise AssertionError("business update was not persisted")
            if sdk.apply_managed_operations("legacy", **args) != applied:
                raise AssertionError("managed replay differed")
            if sdk.get_subscription("legacy", "policy") != args["advance_to"]:
                raise AssertionError("event cursor did not advance")
            if sdk.flush() != 1:
                raise AssertionError("outbox did not deliver: " + repr(sdk.delivery_messages()))
            completed = runtime.run_once(execution_id=command.execution_id)
            if completed is None or completed.state != "succeeded":
                raise AssertionError("managed Runtime settlement failed: " + repr((completed, runtime._diagnostic_errors, lifecycle_host.last_error)))
            sdk.sync()
            projected = sdk.get_run("legacy")
            if projected["tasks"]["next"]["attempts"][-1]["state"] != "succeeded":
                raise AssertionError("settlement did not reach orchestration")
            if sdk.get_subscription("legacy", "policy") != args["advance_to"]:
                raise AssertionError("sync moved policy cursor")
            value = completed.result.value
            if value["execution_id"] != command.execution_id or value["pid"] == os.getpid():
                raise AssertionError("separate handler identity differs: " + repr(value))
            with sqlite3.connect(lifecycle_host.path) as db:
                if db.execute('SELECT COUNT(*) FROM producers').fetchone()[0] < 1 or lifecycle_host.acks < 1:
                    raise AssertionError('host reservation or receiver verification was not exercised')
            obligations = runtime.kernel.inspect_supervisor_obligations(command.execution_id)["obligations"]
            if len(obligations) != 1 or obligations[0]["state"] != "resolved" or (obligations[0]["attempt"], obligations[0]["fence"]) != (value["attempt"], value["fence"]):
                raise AssertionError("exact Runtime obligation missing: " + repr(obligations))
            if obligations[0]["resolution"] != {"source": "sdk_confirmed_supervisor_cleanup",
                    "result_id": completed.result.result_id, "status": "succeeded"}:
                raise AssertionError("Runtime result and resolution differ: " + repr(obligations))
            records = runtime._settlement_journal.scan_supervisor_cleanup(timeout_seconds=1)["registrations"]
            entry = next(item for item in records if item["identity"] == {"execution_id": command.execution_id,
                "attempt": value["attempt"], "fence": value["fence"]})
            if (entry["worker_tree_cleanup"], entry["cleanup"], entry["outcome"]) != ("confirmed", "confirmed", "durable"):
                raise AssertionError("Runtime cleanup or durable outcome missing: " + repr(entry))
        finally:
            runtime.close()
    sdk.kernel = kernel
    control = kernel.get_run_control("legacy")
    results.put((json.loads(activated["kernel_receipt"])["state"], json.loads(resumed["orchestrator_receipt"])["state"],
                 control["claims_used"], control["max_claims"], control["deadline_at"], sdk.get_run("legacy")["application_state"]))
    kernel.close()


@unittest.skipUnless(sys.platform.startswith("linux"), "fork inheritance is required for fixture stubs")
class ManagedLegacyUpdateTests(unittest.TestCase):
    def test_policy_transaction_delivers_and_settles(self):
        from dispatcher_sdk.orchestrator import contracts
        from dispatcher_sdk.execution_kernel import runtime as runtime_module
        old_digest = contracts.digest
        def fake_digest(value):
            return _fake_sha256(contracts.canonical(value).encode()).hexdigest()
        with ExitStack() as stack:
            stack.enter_context(patch.object(hashlib, "sha256", _fake_sha256))
            # Patch aliases already imported before this test, not only their source.
            for name, module in tuple(sys.modules.items()):
                if name.startswith("dispatcher_sdk.") and getattr(module, "digest", None) is old_digest:
                    stack.enter_context(patch.object(module, "digest", fake_digest))
            stack.enter_context(patch.object(runtime_module, "registry_revision", return_value="fixture-registry"))
            stack.enter_context(patch.object(runtime_module, "handler_revision", return_value="fixture-handler"))
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                old_kernel, old_orch = root / "old-kernel", root / "old-orch"
                kernel_path, orch_path = root / "kernel", root / "orchestrator"
                _seed_legacy(old_kernel, old_orch)
                for source, target in ((old_kernel, kernel_path), (old_orch, orch_path)):
                    with maintenance_lease(source, "fixture", "upgrade") as lease:
                        upgrade_storage(source, target, lease=lease)
                deadline = time.time() + 300
                with SQLiteKernel(kernel_path) as kernel:
                    manifest = {"operation_id": "adopt", "run_id": "legacy", "kernel_store_id": kernel.kernel_store_identity(),
                        "orchestrator_store_id": "legacy-store", "orchestrator_incarnation": "legacy-incarnation",
                        "generation": 0, "membership": [{"execution_id": "legacy-execution", "status": "accepted"}],
                        "membership_source": "fixture", "membership_complete": True, "page_seq": 0,
                        "claims_used": 3, "claims_source": "fixture", "max_claims": 7, "deadline_at": deadline,
                        "isolation_lease_id": "fixture-lease", "isolation_expires_at": deadline, "isolation_held": True}
                result = _Results()
                _adopt_in_process(str(orch_path), str(kernel_path), manifest, False, result)
                self.assertEqual(result.value, ("paused", "closed"))
                _revise_in_process(str(orch_path), str(kernel_path), manifest, "commit", result)
                self.assertEqual(result.value[0], 1)
                _activate_with_runtime(str(orch_path), str(kernel_path), manifest, result)
                self.assertEqual(result.value[:3], ("paused", "active", 4))
                with SQLiteKernel(kernel_path) as kernel:
                    sdk = Orchestrator(orch_path, kernel)
                    self.assertEqual(sdk.get_run("legacy")["application_state"]["wait"], "resolved")
                    self.assertEqual(sdk.get_subscription("legacy", "policy"), 1)
                    self.assertEqual(kernel.get("sdk-managed:legacy:new").state, "succeeded")
