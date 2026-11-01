"""Split-store public lifecycle across processes with a synthetic scoped budget host."""
import contextlib
import json
import hashlib
import multiprocessing
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.orchestrator import Orchestrator
from tests.test_split_store_process_adoption import (_adopt_in_process, _revise_in_process, _handler, _WorkerVerifier)
from tests.test_managed_legacy_policy_integration import _LifecycleHost


@contextmanager
def _synthetic_bookkeeping(path):
    """Replace existing SDK digest bookkeeping with shared opaque test tokens."""
    with contextlib.closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS tokens(id INTEGER PRIMARY KEY, value BLOB UNIQUE NOT NULL)')
    class Token:
        def __init__(self, value=b''): self.value = bytes(value)
        def update(self, value): self.value += bytes(value)
        def digest(self):
            with contextlib.closing(sqlite3.connect(path, timeout=5)) as db, db:
                db.execute('INSERT OR IGNORE INTO tokens(value) VALUES(?)', (self.value,))
                value = db.execute('SELECT id FROM tokens WHERE value=?', (self.value,)).fetchone()[0]
            return value.to_bytes(32, 'big')
        def hexdigest(self): return self.digest().hex()
        def copy(self): return Token(self.value)
    from dispatcher_sdk.orchestrator import contracts
    old_digest = contracts.digest
    def fake_digest(value):
        return Token(contracts.canonical(value).encode()).hexdigest()
    with ExitStack() as stack:
        stack.enter_context(patch.object(hashlib, 'sha256', Token))
        for name, module in tuple(sys.modules.items()):
            if name.startswith('dispatcher_sdk.') and getattr(module, 'digest', None) is old_digest:
                stack.enter_context(patch.object(module, 'digest', fake_digest))
        yield


def _run_with_synthetic_bookkeeping(target, args, token_path):
    with _synthetic_bookkeeping(token_path):
        target(*args)

def _activate_scoped_process(orchestrator_path, kernel_path, manifest, results):
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
            return {"principal": "next", "expires_at": expiry,
                    "permissions": [("legacy", "kernel:" + p) for p in ("worker", "claim", "start", "budget")],
                    "run_id": "legacy", "generation": 1, "control_epoch": 3, **admission}
        if credential == "resumed":
            return {"principal": "resumed", "expires_at": expiry,
                    "permissions": [("legacy", "kernel:" + p) for p in ("worker", "claim", "submit", "start", "work", "budget")],
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
        command=command.to_dict(), scopes=list(budget["scopes"]), decision_id="adopt", kernel_store_id=operation["kernel_store_id"],
        orchestrator_store_id=operation["orchestrator_store_id"], orchestrator_incarnation=operation["orchestrator_incarnation"])
    kernel.declare_budget_dependencies("declare", expected_declaration=dict(declaration))
    admission["budget_admission"] = {key: declaration[key] for key in (
        "run_id", "generation", "policy_id", "execution_id", "scopes", "decision_id", "kernel_store_id",
        "orchestrator_store_id", "orchestrator_incarnation")}
    admission["budget_admission"].update(allowed=False, expires_at=expiry)
    worker = SQLiteKernel(kernel_path, authority_verifier=authority, worker_credential="resumed")
    try:
        worker.submit_managed(command, run_id="legacy", generation=1)
    except StorageIsolationError:
        pass
    else:
        raise AssertionError("denied dependent budget admitted work")
    admission["budget_admission"]["allowed"] = True
    worker.submit_managed(command, run_id="legacy", generation=1)
    stale = SQLiteKernel(kernel_path, authority_verifier=authority, worker_credential="next")
    try:
        try:
            stale.claim('old-worker', execution_id=command.execution_id)
        except StorageIsolationError:
            pass
        else:
            raise AssertionError('old paused-epoch authority admitted work after resume')
    finally:
        stale.close()
    with patch.object(runtime_module, "registry_revision", return_value="host-supplied"), \
         patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
        lifecycle_host = _LifecycleHost(kernel_path, command.execution_id, expiry)
        runtime = Kernel.open_sqlite(kernel_path, {"handler-v2": _handler}, isolation_mode="process",
            authority_verifier=_WorkerVerifier(expiry, admission), worker_credential="resumed",
            lifecycle_verifier=lifecycle_host)
        lifecycle_host.binding = runtime.settlement_storage
        try:
            completed = runtime.run_once(execution_id=command.execution_id)
            if completed is None or completed.state != "succeeded":
                raise AssertionError("runtime did not complete resumed execution: " + repr(completed))
            value = completed.result.value
            if value["execution_id"] != command.execution_id or value["pid"] == os.getpid():
                raise AssertionError("handler identity or process was incorrect: " + repr(value))
            with contextlib.closing(sqlite3.connect(lifecycle_host.path)) as db, db:
                if db.execute('SELECT COUNT(*) FROM producers').fetchone()[0] < 1 or lifecycle_host.acks < 1:
                    raise AssertionError('host reservation or receiver verification was not exercised')
            binding = runtime.settlement_storage
            obligations = runtime.kernel.inspect_supervisor_obligations(command.execution_id)["obligations"]
            if len(obligations) != 1 or obligations[0]["state"] != "resolved":
                raise AssertionError("supervisor settlement unresolved: " + repr(obligations))
        finally:
            runtime.close()
    journal = SettlementJournal.open_readonly(binding["path"], source_id=binding["source_id"],
        kernel_path=binding["kernel_path"], timeout_seconds=1)
    receipts = journal.inspect(command.execution_id, timeout_seconds=1)
    if (len(receipts) != 1 or receipts[0]["state"] != "recorded"
            or receipts[0]["result"]["result_id"] != completed.result.result_id
            or receipts[0]["evidence"]["execution_state"] != "succeeded"):
        raise AssertionError("completion settlement not persisted: " + repr(receipts))
    control = kernel.get_run_control("legacy")
    results.put((json.loads(activated["kernel_receipt"])["state"], json.loads(resumed["orchestrator_receipt"])["state"],
                 control["claims_used"], control["max_claims"], control["deadline_at"], sdk.get_run("legacy")["application_state"]))
    worker.close()
    kernel.close()


@unittest.skipUnless(sys.platform.startswith('linux'), 'requires fork inheritance of synthetic bookkeeping')
class SplitStoreScopedProcessLifecycleTests(unittest.TestCase):
    def test_paused_activation_resume_and_host_scoped_budget_across_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            token_path = str(Path(directory) / 'synthetic-tokens.sqlite')
            with _synthetic_bookkeeping(token_path):
                opath, kpath = str(Path(directory) / 'orchestrator.sqlite'), str(Path(directory) / 'kernel.sqlite')
                deadline = time.time() + 300
                kernel = SQLiteKernel(kpath)
                sdk = Orchestrator(opath, kernel)
                kernel.submit(ExecutionCommandV2(execution_id='legacy-execution', idempotency_key='legacy-key',
                    registry_revision='host-supplied', correlation_id='legacy', causation_id=None, handler_id='handler',
                    handler_contract_version=1, retry_policy=RetryPolicy(), timeout_seconds=1, payload={}))
                with sdk._transaction() as db:
                    db.execute("INSERT INTO sdk_runs VALUES('legacy',0,'running')")
                    state = {'run_id': 'legacy', 'revision': 0, 'state': 'running', 'generation': 0,
                             'input': None, 'definition': {}, 'application_state': {'wait': 'pending'},
                             'tasks': {}, 'waits': {}, 'signals': {}}
                    sdk._save(db, state)
                    sdk._event(db, state, 'legacy.waiting', {'value': 'retained'})
                    identity = db.execute('SELECT store_id,incarnation FROM sdk_storage_identity').fetchone()
                manifest = {'operation_id': 'adopt', 'run_id': 'legacy', 'kernel_store_id': kernel.kernel_store_identity(),
                    'orchestrator_store_id': identity[0], 'orchestrator_incarnation': identity[1], 'generation': 0,
                    'membership': [{'execution_id': 'legacy-execution', 'status': 'accepted'}],
                    'membership_source': 'fixture', 'membership_complete': True, 'page_seq': 0,
                    'claims_used': 3, 'claims_source': 'fixture', 'max_claims': 7, 'deadline_at': deadline,
                    'isolation_lease_id': 'fixture-lease', 'isolation_expires_at': deadline, 'isolation_held': True}
                kernel.close()
                context = multiprocessing.get_context('spawn')
                results = context.Queue()
                try:
                    for target, args, expected in (
                        (_adopt_in_process, (opath, kpath, manifest, False, results), ('paused', 'closed')),
                        (_revise_in_process, (opath, kpath, manifest, 'commit', results), (1, '{"revision":2,"wait":"pending"}')),
                        (_activate_scoped_process, (opath, kpath, manifest, results),
                         ('paused', 'active', 4, 7, deadline, {'revision': 2, 'wait': 'pending'})),
                    ):
                        proc = context.Process(target=_run_with_synthetic_bookkeeping, args=(target, args, token_path))
                        proc.start()
                        proc.join(20)
                        if proc.is_alive():
                            proc.terminate()
                            proc.join()
                            self.fail('participant did not finish')
                        self.assertEqual(proc.exitcode, 0)
                        self.assertEqual(results.get(timeout=2), expected)
                    kernel = SQLiteKernel(kpath)
                    try:
                        self.assertEqual(kernel.get('legacy-execution').execution_id, 'legacy-execution')
                        control = kernel.get_run_control('legacy')
                        self.assertEqual((control['claims_used'], control['max_claims'], control['deadline_at']), (4, 7, deadline))
                        sdk = Orchestrator(opath, kernel)
                        with sdk._transaction() as db:
                            self.assertEqual(db.execute("SELECT kind FROM sdk_events WHERE run_id='legacy' ORDER BY rowid LIMIT 1").fetchone()[0], 'legacy.waiting')
                    finally:
                        kernel.close()
                finally:
                    results.close()
