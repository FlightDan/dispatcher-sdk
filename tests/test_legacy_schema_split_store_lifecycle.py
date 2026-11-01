"""Synthetic legacy schema copy-upgrade and split-store process lifecycle.

Host authority is simulated; this does not establish actual writer isolation,
Runtime settlement, or acceptance by a real host.
"""
import json
import os
import multiprocessing
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel._sqlite_schema import KERNEL_SCHEMA_V5
from dispatcher_sdk.maintenance import maintenance_lease
from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator.notifications import NotificationsMixin
from dispatcher_sdk.orchestrator.results import ResultsMixin
from dispatcher_sdk.orchestrator.store import SCHEMA_V4, execute_schema, initialize_storage_tracking
from dispatcher_sdk.storage_migration import upgrade_storage
from tests.test_split_store_process_adoption import _adopt_in_process, _revise_in_process, _WorkerVerifier, _handler


def _seed_legacy(kernel_path, orchestrator_path):
    command = ExecutionCommandV2(execution_id="legacy-execution", idempotency_key="legacy-key",
        registry_revision="host-supplied", correlation_id="legacy", causation_id=None,
        handler_id="handler", handler_contract_version=1, retry_policy=RetryPolicy(), timeout_seconds=1, payload={})
    with sqlite3.connect(kernel_path) as db:
        db.executescript(KERNEL_SCHEMA_V5)
        db.execute("INSERT INTO kernel_executions(execution_id,idempotency_key,registry_revision,command_json,"
            "state,attempt,redelivery_count,next_attempt_at,fence,revision,created_at,updated_at) "
            "VALUES(?,?,?,?,'queued',0,0,1,0,1,1,1)",
            (command.execution_id, command.idempotency_key, command.registry_revision, command.to_json()))
        db.execute("INSERT INTO kernel_events VALUES(1,'legacy-event','legacy-execution',1,'submitted',NULL,'queued','{}',1)")
        db.execute("UPDATE kernel_clock SET event_sequence=1,watermark=1")
    with sqlite3.connect(orchestrator_path) as db:
        execute_schema(db, SCHEMA_V4)
        results = ResultsMixin()
        results.max_result_deliveries = 5
        results._init_results(db)
        NotificationsMixin._init_notifications(db)
        db.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',4)")
        db.execute("INSERT INTO sdk_storage_identity VALUES(1,'legacy-store','legacy-incarnation',1)")
        db.execute("INSERT INTO sdk_storage_clock VALUES(1,0)")
        initialize_storage_tracking(db)
        db.execute("INSERT INTO sdk_runs VALUES('legacy',0,'running')")
        db.execute("INSERT INTO sdk_run_revisions VALUES('legacy',0)")
        for key, value in {"state": "running", "generation": 0, "input": None,
                           "definition": {}, "application_state": {"wait": "pending"}}.items():
            encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
            db.execute("INSERT INTO sdk_run_items VALUES('legacy','root',?,?)", (key, encoded))
            db.execute("INSERT INTO sdk_run_history VALUES('legacy','root',?,0,?)", (key, encoded))
        db.execute("INSERT INTO sdk_events(run_id,revision,kind,payload) VALUES('legacy',0,'legacy.waiting','{\"value\":\"retained\"}')")
        db.execute("INSERT INTO sdk_event_watermarks VALUES('legacy',1,0)")


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
        from tests.test_managed_legacy_policy_integration import _LifecycleHost
        lifecycle_host = _LifecycleHost(kernel_path, command.execution_id, expiry)
        runtime = Kernel.open_sqlite(kernel_path, {"handler-v2": _handler}, isolation_mode="process",
            authority_verifier=_WorkerVerifier(expiry, admission), worker_credential="resumed",
            lifecycle_verifier=lifecycle_host)
        lifecycle_host.binding = runtime.settlement_storage
        try:
            runtime.submit_managed(command, run_id="legacy", generation=1)
            completed = runtime.run_once(execution_id=command.execution_id)
            if completed is None or completed.state != "succeeded":
                raise AssertionError("managed Runtime settlement failed: " + repr(completed))
            value = completed.result.value
            if value["execution_id"] != command.execution_id or value["pid"] == os.getpid():
                raise AssertionError("separate handler identity differs: " + repr(value))
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
    control = kernel.get_run_control("legacy")
    results.put((json.loads(activated["kernel_receipt"])["state"], json.loads(resumed["orchestrator_receipt"])["state"],
                 control["claims_used"], control["max_claims"], control["deadline_at"], sdk.get_run("legacy")["application_state"]))
    kernel.close()


class LegacySchemaSplitStoreLifecycleTests(unittest.TestCase):
    def test_v5_v4_copy_upgrade_and_same_run_process_lifecycle(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            old_kernel, old_orchestrator = root / "kernel-v5.sqlite", root / "orchestrator-v4.sqlite"
            kernel_path, orchestrator_path = root / "kernel.sqlite", root / "orchestrator.sqlite"
            _seed_legacy(old_kernel, old_orchestrator)
            for source, target, versions in ((old_kernel, kernel_path, (5, 12)),
                                             (old_orchestrator, orchestrator_path, (4, 6))):
                with maintenance_lease(source, "fixture", "upgrade") as lease:
                    report = upgrade_storage(source, target, lease=lease)
                self.assertEqual((report["source_version"], report["target_version"]), versions)
            with sqlite3.connect(old_kernel) as source, sqlite3.connect(kernel_path) as target:
                self.assertEqual(source.execute("SELECT schema_version FROM kernel_schema_meta").fetchone()[0], 5)
                self.assertEqual(source.execute("SELECT * FROM kernel_executions").fetchall(), target.execute("SELECT * FROM kernel_executions").fetchall())
                self.assertEqual(source.execute("SELECT * FROM kernel_events").fetchall(), target.execute("SELECT * FROM kernel_events").fetchall())
            with sqlite3.connect(old_orchestrator) as source, sqlite3.connect(orchestrator_path) as target:
                self.assertEqual(source.execute("SELECT version FROM sdk_schema_meta").fetchone()[0], 4)
                for table in ("sdk_runs", "sdk_run_items", "sdk_run_history", "sdk_events", "sdk_storage_identity"):
                    self.assertEqual(source.execute(f"SELECT * FROM {table}").fetchall(), target.execute(f"SELECT * FROM {table}").fetchall())
            deadline = time.time() + 300
            with SQLiteKernel(kernel_path) as kernel:
                manifest = {"operation_id": "adopt", "run_id": "legacy", "kernel_store_id": kernel.kernel_store_identity(),
                    "orchestrator_store_id": "legacy-store", "orchestrator_incarnation": "legacy-incarnation",
                    "generation": 0, "membership": [{"execution_id": "legacy-execution", "status": "accepted"}],
                    "membership_source": "fixture", "membership_complete": True, "page_seq": 0,
                    "claims_used": 3, "claims_source": "fixture", "max_claims": 7, "deadline_at": deadline,
                    "isolation_lease_id": "fixture-lease", "isolation_expires_at": deadline, "isolation_held": True}
            context = multiprocessing.get_context("spawn")
            queue = context.Queue()
            def run(target, *args):
                process = context.Process(target=target, args=(*args, queue))
                process.start()
                process.join(40)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                    self.fail("lifecycle process timed out")
                self.assertEqual(process.exitcode, 0)
                return queue.get(timeout=3)
            paths = (str(orchestrator_path), str(kernel_path), manifest)
            self.assertEqual(run(_adopt_in_process, *paths, False), ("paused", "closed"))
            self.assertEqual(run(_revise_in_process, *paths, "commit"), (1, '{"revision":2,"wait":"pending"}'))
            self.assertEqual(run(_activate_with_runtime, *paths),
                ("paused", "active", 4, 7, deadline, {"revision": 2, "wait": "pending"}))
            with SQLiteKernel(kernel_path) as kernel:
                sdk = Orchestrator(orchestrator_path, kernel)
                self.assertEqual(sdk.get_run("legacy")["application_state"], {"revision": 2, "wait": "pending"})
                self.assertEqual(kernel.get("legacy-execution").state, "queued")
                completed = kernel.get("sdk-managed:legacy:new")
                self.assertEqual(completed.state, "succeeded")
                self.assertEqual(completed.result.value["execution_id"], "sdk-managed:legacy:new")
                obligation = kernel.inspect_supervisor_obligations("sdk-managed:legacy:new")["obligations"][0]
                self.assertEqual(obligation["resolution"]["result_id"], completed.result.result_id)
                self.assertEqual((obligation["attempt"], obligation["fence"]),
                                 (completed.result.attempt, completed.result.fence))
                with sdk._transaction() as db:
                    self.assertEqual(db.execute("SELECT kind FROM sdk_events WHERE run_id='legacy' ORDER BY sequence LIMIT 1").fetchone()[0], "legacy.waiting")
            queue.close()
