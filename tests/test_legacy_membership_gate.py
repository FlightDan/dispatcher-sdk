"""Kernel authority must follow durable membership, including legacy IDs.

The test inserts a fixture mapping only; it does not exercise or claim an
adoption protocol.  No production API currently installs these mappings.
"""

import contextlib
from pathlib import Path
from dataclasses import replace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import (
    BudgetScanContinuation, CASConflictError, ExecutionCommandV2, RetryPolicy, SQLiteKernel,
)
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock


def command(execution_id):
    return ExecutionCommandV2(
        execution_id=execution_id, idempotency_key="key:" + execution_id,
        registry_revision="test", correlation_id="run", causation_id=None,
        handler_id="test", handler_contract_version=1, retry_policy=RetryPolicy(),
        timeout_seconds=5, payload={},
    )


class LegacyMembershipGateTests(unittest.TestCase):
    def test_failed_claim_rollback_does_not_report_safe_continuation(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temporary:
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3")
            real = kernel._connection
            class FailRollback:
                fail_commit = False
                def __getattr__(self, name):
                    return getattr(real, name)
                def execute(self, sql, *args):
                    if not self.fail_commit and sql == "ROLLBACK TO kernel_operation":
                        raise sqlite3.OperationalError("rollback failed")
                    return real.execute(sql, *args)
                def commit(self):
                    if self.fail_commit:
                        raise sqlite3.OperationalError("watermark commit failed")
                    return real.commit()
            try:
                kernel._connection = FailRollback()
                with self.assertRaisesRegex(sqlite3.OperationalError, "rollback failed"):
                    with kernel._transaction():
                        kernel._claim_continuation = {"predicate": {"revisions": None}, "after": [1, "x"]}
                        error = StorageIsolationError("authority changed")
                        error._claim_authority_failure = True
                        raise error
                self.assertFalse(real.in_transaction)
                kernel._connection.fail_commit = True
                with self.assertRaisesRegex(sqlite3.OperationalError, "watermark commit failed"):
                    with kernel._transaction():
                        kernel._claim_continuation = {"predicate": {"revisions": None}, "after": [1, "x"]}
                        error = StorageIsolationError("authority changed")
                        error._claim_authority_failure = True
                        raise error
                self.assertFalse(real.in_transaction)
            finally:
                kernel._connection = real
                kernel.close()

    def test_budget_candidate_cursor_is_scoped_to_claim_predicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3")
            try:
                kernel.register_run_control("run", max_claims=100, deadline_at=time.time() + 300)
                kernel.set_run_control("run", expected_epoch=0, generation=0, state="active")
                from dispatcher_sdk.execution_kernel._sqlite_execution import encode_json
                with kernel._transaction() as (connection, timestamp):
                    ids = [("sdk-managed:b", "b")]
                    ids += [(f"sdk-managed:blocked-{i:03}", "a") for i in range(65)]
                    ids += [("sdk-managed:eligible", "a")]
                    for execution_id, revision in ids:
                        item = replace(command(execution_id), registry_revision=revision)
                        connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,0)", (execution_id, "run", 0))
                        kernel._submit_in_transaction(item, encode_json(item.to_dict()), connection, timestamp)
                    unblocked = [None]
                    def check(_connection, _run, _generation, execution_id, _timestamp, **_kwargs):
                        if "blocked" in execution_id and execution_id != unblocked[0]:
                            raise CASConflictError("budget unavailable")
                    kernel._check_application_budget = check
                    cursors = []
                    for i in range(129):
                        exclusions = (f"excluded-{i}",)
                        with self.assertRaises(BudgetScanContinuation) as pending:
                            kernel._next_budget_eligible_claim(connection, timestamp, ("a",), exclude_execution_ids=exclusions)
                        cursors.append((exclusions, pending.exception.cursor))
                    self.assertEqual(kernel._next_budget_eligible_claim(connection, timestamp, ("b",))["execution_id"], "sdk-managed:b")
                    for exclusions, cursor in cursors:
                        self.assertEqual(kernel._next_budget_eligible_claim(connection, timestamp, ("a",),
                            exclude_execution_ids=("a-different-exclusion",), budget_scan_cursor=cursor)["execution_id"], "sdk-managed:eligible")
                    self.assertIsNone(kernel._next_budget_eligible_claim(connection, timestamp, ("a",),
                        exclude_execution_ids=("sdk-managed:eligible",), budget_scan_cursor=cursors[0][1]))
                    unblocked[0] = "sdk-managed:blocked-000"
                    self.assertEqual(kernel._next_budget_eligible_claim(connection, timestamp, ("a",))["execution_id"], unblocked[0])
                    unblocked[0] = None
                    with self.assertRaises(ValueError):
                        kernel._next_budget_eligible_claim(connection, timestamp, ("a",), exclude_execution_ids=("x" * 65537,))
                with self.assertRaises(BudgetScanContinuation) as pending:
                    kernel.claim("worker", registry_revision="a")
                original_event = kernel._event
                def fail_event(*_args, **_kwargs):
                    raise StorageIsolationError("unrelated storage failure")
                kernel._event = fail_event
                with self.assertRaisesRegex(StorageIsolationError, "unrelated storage failure"):
                    kernel.claim("worker", registry_revision="a", budget_scan_cursor=pending.exception.cursor)
                kernel._event = original_event
                lease = kernel.claim("worker", registry_revision="a", budget_scan_cursor=pending.exception.cursor)
                self.assertEqual(lease.execution_id, "sdk-managed:eligible")
            finally:
                kernel.close()

    def test_protected_drain_closes_on_pause_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, expiry = Path(temporary) / "kernel.sqlite3", time.time() + 300
            proof, drain = {}, {}
            def verifier(credential):
                if credential == "manager":
                    return {"principal": "manager", "expires_at": expiry, "drain_pause": dict(proof),
                            "permissions": [("run", "kernel:" + p) for p in ("manage_authority", "pause")]}
                return {"principal": "worker", "expires_at": expiry, "run_id": "run", "generation": 0,
                        "control_epoch": 0, "permissions": [("run", "kernel:" + p) for p in ("worker", "claim", "start", "work", "drain")],
                        "drain_admission": dict(drain)}
            kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
            try:
                kernel.register_run_control("run", max_claims=2, deadline_at=expiry)
                kernel.protect_run_authority("run", generation=0, expected_epoch=0, worker_credential="worker")
                work = command("sdk-managed:protected-complete")
                with kernel._transaction() as (connection, timestamp):
                    connection.execute("UPDATE kernel_run_controls SET state='active' WHERE run_id='run'")
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,0)", (work.execution_id, "run", 0))
                    from dispatcher_sdk.execution_kernel._sqlite_execution import encode_json
                    kernel._submit_in_transaction(work, encode_json(work.to_dict()), connection, timestamp)
                proof.update(operation_id="pause", run_id="run", generation=0, control_epoch=1,
                             kernel_store_id=kernel.kernel_store_identity(), orchestrator_store_id="orch",
                             orchestrator_incarnation="inc", drain_execution_ids=[work.execution_id])
                kernel.prepare_control_pause("pause", "run", expected_epoch=0, generation=0, drain_execution_ids=[work.execution_id],
                    drain_orchestrator_store_id="orch", drain_orchestrator_incarnation="inc")
                drain.update({k: v for k, v in proof.items() if k != "drain_execution_ids"}, allowed=True,
                             execution_id=work.execution_id, expires_at=expiry)
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="worker")
                lease = kernel.start(kernel.claim("worker"))
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
                kernel.complete_control_pause("complete", "pause", "run", expected_epoch=1, generation=0)
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="worker")
                with self.assertRaises(CASConflictError):
                    kernel.verify(lease)
            finally:
                kernel.close()

    def test_protected_drain_requires_exact_live_host_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            expiry = time.time() + 300
            drain = {}
            pause_proof = {}
            clock, advance = [time.time()], [False, 0]
            def verifier(credential):
                if credential == "manager":
                    return {"principal": "manager", "expires_at": expiry, "drain_pause": dict(pause_proof),
                            "permissions": [("run", "kernel:" + x) for x in ("manage_authority", "pause", "cancel")]}
                if credential == "worker":
                    if advance[0]:
                        advance[1] += 1
                        if advance[1] == 2:
                            clock[0] = drain["expires_at"] + 1
                    return {"principal": "worker", "expires_at": expiry, "run_id": "run", "generation": 0,
                            "control_epoch": 0, "permissions": [("run", "kernel:" + x) for x in ("worker", "claim", "start", "work", "drain")],
                            "drain_admission": dict(drain)}
                raise ValueError("unknown")
            kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
            try:
                kernel.register_run_control("run", max_claims=4, deadline_at=expiry)
                kernel.protect_run_authority("run", generation=0, expected_epoch=0, worker_credential="worker")
                with kernel._transaction() as (connection, timestamp):
                    connection.execute("UPDATE kernel_run_controls SET state='active' WHERE run_id='run'")
                    work = command("sdk-managed:protected-drain")
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,0)", (work.execution_id, "run", 0))
                    from dispatcher_sdk.execution_kernel._sqlite_execution import encode_json
                    kernel._submit_in_transaction(work, encode_json(work.to_dict()), connection, timestamp)
                pause_proof.update(operation_id="pause", run_id="run", generation=0, control_epoch=1,
                                   kernel_store_id=kernel.kernel_store_identity(), orchestrator_store_id="orch",
                                   orchestrator_incarnation="inc", drain_execution_ids=[work.execution_id])
                kernel.prepare_control_pause("pause", "run", expected_epoch=0, generation=0,
                    drain_execution_ids=[work.execution_id], drain_orchestrator_store_id="orch", drain_orchestrator_incarnation="inc")
                drain.update(allowed=True, operation_id="pause", run_id="run", execution_id=work.execution_id,
                             generation=0, control_epoch=1, kernel_store_id=kernel.kernel_store_identity(),
                             orchestrator_store_id="orch", orchestrator_incarnation="inc", expires_at=expiry)
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="worker")
                kernel._now = lambda: clock[0]
                drain["expires_at"] = clock[0] - 1
                with self.assertRaises(StorageIsolationError):
                    kernel.claim("worker", execution_id=work.execution_id)
                drain["expires_at"] = expiry
                drain["execution_id"] = "different"
                with self.assertRaises(StorageIsolationError):
                    kernel.claim("worker", execution_id=work.execution_id)
                drain["execution_id"] = work.execution_id
                drain["orchestrator_store_id"] = "wrong"
                with self.assertRaises(StorageIsolationError):
                    kernel.claim("worker", execution_id=work.execution_id)
                drain["orchestrator_store_id"] = "orch"
                drain["control_epoch"] = 2
                with self.assertRaises(StorageIsolationError):
                    kernel.claim("worker", execution_id=work.execution_id)
                drain["control_epoch"] = 1
                drain["expires_at"] = clock[0] + 1
                advance[0] = True
                with self.assertRaises(StorageIsolationError):
                    kernel.claim("worker", execution_id=work.execution_id)
                self.assertEqual(kernel.get(work.execution_id).state, "queued")
                advance[0], clock[0] = False, time.time()
                # A wall-clock rollback must not revive the expired proof.
                with self.assertRaises(StorageIsolationError):
                    kernel.claim("worker", execution_id=work.execution_id)
                drain["expires_at"] = expiry
                lease = kernel.claim("worker", execution_id=work.execution_id)
                lease = kernel.start(lease)
                with self.assertRaises(CASConflictError):
                    kernel.prepare_effect(lease, effect_id="new-effect", name="test", request={})
                with self.assertRaises(CASConflictError):
                    kernel.submit_child(command("sdk-managed:child"), lease, None)
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
                kernel.fence_cancelled_run("cancel", "run", expected_epoch=1, generation=0)
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="worker")
                with self.assertRaises(CASConflictError):
                    kernel.verify(lease)
            finally:
                kernel.close()

    def test_split_pause_selective_drain_is_bounded_and_fenced(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            kernel = SQLiteKernel(path)
            try:
                kernel.register_run_control("run", max_claims=4, deadline_at=time.time() + 300)
                kernel.set_run_control("run", expected_epoch=0, generation=0, state="active")
                allowed, blocked = command('sdk-managed:排,"x'), command("sdk-managed:blocked")
                kernel.submit_managed(allowed, run_id="run", generation=0)
                kernel.submit_managed(blocked, run_id="run", generation=0)
                with self.assertRaises(CASConflictError):
                    kernel.prepare_control_pause("pause", "run", expected_epoch=1, generation=0,
                                                 drain_execution_ids=["sdk-managed:missing"])
                receipt = kernel.prepare_control_pause("pause", "run", expected_epoch=1, generation=0,
                                                       drain_execution_ids=[allowed.execution_id])
                self.assertEqual(receipt["drain_execution_ids"], [allowed.execution_id])
                kernel.close()
                kernel = SQLiteKernel(path)
                self.assertEqual(receipt, kernel.prepare_control_pause("pause", "run", expected_epoch=1,
                    generation=0, drain_execution_ids=[allowed.execution_id]))
                with self.assertRaises(CASConflictError):
                    kernel.prepare_control_pause("pause", "run", expected_epoch=1, generation=0,
                                                 drain_execution_ids=[blocked.execution_id])
                lease = kernel.claim("worker")
                self.assertEqual(lease.execution_id, allowed.execution_id)
                self.assertIsNone(kernel.claim("other"))
                lease = kernel.start(lease)
                kernel.complete_control_pause("complete", "pause", "run", expected_epoch=2, generation=0)
                with self.assertRaises(CASConflictError):
                    kernel.verify(lease)
                self.assertIsNone(kernel.claim("other"))
            finally:
                kernel.close()

    def test_fenced_nonacceptance_is_terminal_replayable_and_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            expiry = time.time() + 300
            def verifier(credential):
                return {"principal": "host", "expires_at": expiry,
                        "permissions": [("run", "kernel:cancel")]}
            kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="cancel")
            try:
                kernel.register_run_control("run", max_claims=2, deadline_at=expiry)
                kernel.set_run_control("run", expected_epoch=0, generation=0, state="active")
                accepted = command("sdk-managed:accepted")
                kernel.submit_managed(accepted, run_id="run", generation=0)
                self.assertEqual(kernel.managed_admission_provenance(accepted, run_id="run", generation=0)["provenance"], "accepted")
                lease = kernel.claim("worker")
                kernel.fence_cancelled_run("fence", "run", expected_epoch=1, generation=0)
                kernel.cancel(lease, reason="cancel after acceptance")
                self.assertEqual(kernel.managed_admission_provenance(accepted, run_id="run", generation=0)["provenance"], "accepted")
                args = dict(run_id="run", generation=0, fence_operation_id="fence", receipt_operation_id="receipt")
                with self.assertRaises(StorageIsolationError):
                    kernel.cancel_fenced_before_accept(accepted, **args)
                pending = command("sdk-managed:pending")
                receipt = kernel.cancel_fenced_before_accept(pending, **args)
                self.assertEqual(receipt["kind"], "cancelled_before_accept")
                self.assertEqual(kernel.managed_admission_provenance(pending, run_id="run", generation=0)["provenance"], "unknown")
                proven = kernel.managed_admission_provenance(pending, run_id="run", generation=0, receipt_operation_id="receipt")
                self.assertEqual(proven["provenance"], "cancelled_before_accept")
                self.assertEqual(proven["receipt"], receipt)
                self.assertEqual(kernel.managed_execution_receipt(pending, run_id="run", generation=0).state, "cancelled")
                self.assertEqual(kernel.managed_execution_receipt(pending, run_id="run", generation=0, max_bytes=262144).state, "cancelled")
                with self.assertRaises(StorageIsolationError):
                    kernel.managed_execution_receipt(pending, run_id="run", generation=0, max_bytes=1)
                from dispatcher_sdk.execution_kernel._sqlite_execution import encode_json
                command_size = len(encode_json(pending.to_dict()).encode("utf-8"))
                with self.assertRaises(StorageIsolationError):
                    kernel.managed_execution_receipt(pending, run_id="run", generation=0, max_bytes=command_size + 1)
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="cancel")
                self.assertEqual(receipt, kernel.cancel_fenced_before_accept(pending, **args))
                with self.assertRaises(CASConflictError):
                    kernel.cancel_fenced_before_accept(replace(pending, payload={"changed": True}), **args)
                self.assertEqual(kernel.submit_managed(pending, run_id="run", generation=0).state, "cancelled")
                legacy = command("old-pending")
                with kernel._transaction() as (connection, _):
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,0)", (legacy.execution_id, "run", 0))
                    connection.execute("INSERT INTO kernel_legacy_pending_commands VALUES(?,?)", (legacy.execution_id, encode_json(legacy.to_dict())))
                legacy_args = {**args, "receipt_operation_id": "legacy-receipt"}
                oversized = command("old-oversized")
                with kernel._transaction() as (connection, _):
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,0)", (oversized.execution_id, "run", 0))
                    connection.execute("INSERT INTO kernel_legacy_pending_commands VALUES(?,?)", (oversized.execution_id, 'x' * 65537))
                with self.assertRaises(StorageIsolationError):
                    kernel.cancel_fenced_before_accept(oversized, **legacy_args)
                with self.assertRaises(StorageIsolationError):
                    kernel.cancel_fenced_before_accept(replace(legacy, payload={"changed": True}), **legacy_args)
                self.assertEqual(kernel.cancel_fenced_before_accept(legacy, **legacy_args)["execution_id"], "old-pending")
            finally:
                kernel.close()

    def test_revision_content_pages_are_durable_and_ordered(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            expiry = time.time() + 300
            page = {}
            def verifier(credential):
                return {"principal": "host", "expires_at": expiry,
                        "permissions": [("run", "kernel:stage_revision")], "revision_page": dict(page)}
            kernel = SQLiteKernel(path, authority_verifier=verifier)
            try:
                kernel.register_run_control("run", max_claims=1, deadline_at=expiry)
                kernel.set_run_control("run", expected_epoch=0, generation=0, state="active")
                kernel.prepare_control_pause("barrier", "run", expected_epoch=1, generation=0)
                kernel.complete_control_pause("complete", "barrier", "run", expected_epoch=2, generation=0)
                page.update(operation_id="barrier", barrier_operation_id="barrier", source_generation=0, decision_id="decision", run_id="run",
                    kernel_store_id=kernel.kernel_store_identity(), orchestrator_store_id="orch",
                    orchestrator_incarnation="incarnation", content_kind="revision", page_seq=0,
                    total_bytes=4, chunk="ab", complete=False, lease_id="lease", lease_fence=1,
                    lease_expires_at=expiry, lease_held=True)
                first = kernel.stage_revision_content_page("credential", expected_page=dict(page))
                self.assertFalse(first["capture_complete"])
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier)
                self.assertEqual(first, kernel.stage_revision_content_page("credential", expected_page=dict(page)))
                page.update(page_seq=2, chunk="cd", complete=True)
                with self.assertRaises(CASConflictError):
                    kernel.stage_revision_content_page("credential", expected_page=dict(page))
                page["page_seq"] = 1
                second = kernel.stage_revision_content_page("credential", expected_page=dict(page))
                self.assertEqual(second["cumulative_bytes"], 4)
                self.assertTrue(second["capture_complete"])
            finally:
                kernel.close()

    def test_cancel_fence_is_authorized_durable_and_blocks_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            expiry = time.time() + 300
            revoked_during_call = [False, 0]
            def verifier(credential):
                if credential != "cancel":
                    raise ValueError("invalid")
                if revoked_during_call[0]:
                    revoked_during_call[1] += 1
                    if revoked_during_call[1] == 2:
                        raise ValueError("revoked")
                return {"principal": "host", "expires_at": expiry, "permissions": [("run", "kernel:cancel")]}
            kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="cancel")
            try:
                kernel.register_run_control("run", max_claims=2, deadline_at=expiry)
                kernel.set_run_control("run", expected_epoch=0, generation=0, state="active")
                revoked_during_call[0] = True
                with self.assertRaises(StorageIsolationError):
                    kernel.fence_cancelled_run("cancel-op", "run", expected_epoch=1, generation=0)
                self.assertEqual(kernel.get_run_control("run")["state"], "active")
                revoked_during_call[0] = False
                receipt = kernel.fence_cancelled_run("cancel-op", "run", expected_epoch=1, generation=0)
                self.assertEqual(receipt["control_epoch"], 2)
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="cancel")
                self.assertEqual(receipt, kernel.fence_cancelled_run("cancel-op", "run", expected_epoch=1, generation=0))
                with self.assertRaises(CASConflictError):
                    kernel.set_run_control("run", expected_epoch=2, generation=0, state="active")
            finally:
                kernel.close()

    def test_host_verified_legacy_import_preserves_budget_and_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            expiry = time.time() + 300
            manifest = {}
            initial_receipt = {}
            clock = [time.time()]
            advance_during_check = [False, 0]
            def verifier(credential):
                if credential == "import":
                    if advance_during_check[0]:
                        advance_during_check[1] += 1
                        if advance_during_check[1] == 2:
                            clock[0] = manifest["isolation_expires_at"] + 1
                    return {"principal": "host", "expires_at": expiry,
                            "permissions": [("run", "kernel:import_legacy")], "adoption": dict(manifest)}
                if credential == "bind":
                    return {"principal": "host", "expires_at": expiry,
                            "permissions": [("run", "kernel:bind_initial")], "initial_admission_receipt": dict(initial_receipt)}
                if credential == "worker":
                    return {"principal": "worker", "expires_at": expiry, "run_id": "run",
                            "generation": 0, "control_epoch": 0, "permissions": [("run", "kernel:worker"), ("run", "kernel:submit")],
                            "global_admission": {"open": True, "run_id": "run", "generation": 0, "control_epoch": 0,
                                                 "orchestrator_receipt": dict(initial_receipt)}}
                raise ValueError("unknown")
            kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="worker")
            kernel._now = lambda: clock[0]
            try:
                kernel.submit(command("legacy"))
                manifest.update(operation_id="import-id", run_id="run", kernel_store_id=kernel.kernel_store_identity(),
                    orchestrator_store_id="orch", orchestrator_incarnation="incarnation", generation=0,
                    membership=[{"execution_id": "legacy", "status": "accepted"}],
                    membership_source="host-ledger", membership_complete=False, page_seq=0, claims_used=2,
                    claims_source="host-budget", max_claims=5, deadline_at=expiry,
                    isolation_lease_id="lease", isolation_expires_at=expiry, isolation_held=True)
                manifest["claims_used"] = None
                with self.assertRaises(StorageIsolationError):
                    kernel.import_legacy_run("import", worker_credential="worker", expected_adoption=dict(manifest))
                manifest["claims_used"] = 2
                manifest["isolation_expires_at"] = clock[0] + 1
                advance_during_check[0] = True
                with self.assertRaises(StorageIsolationError):
                    kernel.import_legacy_run("import", worker_credential="worker", expected_adoption=dict(manifest))
                advance_during_check[0] = False
                clock[0] = time.time()
                manifest["isolation_expires_at"] = expiry
                with kernel._transaction() as (connection, _):
                    self.assertIsNone(connection.execute("SELECT 1 FROM kernel_run_controls WHERE run_id='run'").fetchone())
                receipt = kernel.import_legacy_run("import", worker_credential="worker", expected_adoption=dict(manifest))
                self.assertEqual(receipt["activation"], "closed")
                self.assertFalse(receipt["capture_complete"])
                self.assertEqual(receipt, kernel.import_legacy_run("import", worker_credential="worker", expected_adoption=dict(manifest)))
                manifest["isolation_expires_at"] = expiry + 100
                self.assertEqual(receipt, kernel.import_legacy_run("import", worker_credential="worker", expected_adoption=dict(manifest)))
                manifest.update(page_seq=2, membership_complete=True,
                                membership=[{"execution_id": "pending", "status": "pending", "command": command("pending").to_dict()}])
                with self.assertRaises(CASConflictError):
                    kernel.import_legacy_run("import", worker_credential="worker", expected_adoption=dict(manifest))
                manifest.update(page_seq=1, membership_complete=True,
                                membership=[{"execution_id": "pending", "status": "pending", "command": command("pending").to_dict()}])
                receipt = kernel.import_legacy_run("import", worker_credential="worker", expected_adoption=dict(manifest))
                self.assertTrue(receipt["capture_complete"])
                self.assertEqual(receipt, kernel.import_legacy_run("import", worker_credential="worker", expected_adoption=dict(manifest)))
                initial_receipt.update(operation_id="initial", run_id="run", generation=0, control_epoch=0,
                    state="active", committed_at=clock[0], kernel_store_id=kernel.kernel_store_identity(),
                    orchestrator_store_id="orch", orchestrator_incarnation="incarnation")
                kernel.bind_initial_admission("bind", expected_receipt=dict(initial_receipt))
                with kernel._transaction() as (connection, _):
                    self.assertEqual(tuple(connection.execute("SELECT state,claims_used,max_claims FROM kernel_run_controls WHERE run_id='run'").fetchone()), ("paused", 2, 5))
                    self.assertEqual(connection.execute("SELECT count(*) FROM kernel_managed_executions WHERE run_id='run'").fetchone()[0], 2)
                self.assertIsNone(kernel.claim_and_start("worker", execution_id="legacy"))
                with self.assertRaises(CASConflictError):
                    kernel.submit_managed(command("pending"), run_id="run", generation=0)
                # Fixture emulates a future authorized resume; public resume remains closed.
                with kernel._transaction() as (connection, _):
                    connection.execute("UPDATE kernel_run_controls SET state='active' WHERE run_id='run'")
                with self.assertRaises(StorageIsolationError):
                    kernel.submit_managed(replace(command("pending"), payload={"changed": True}), run_id="run", generation=0)
                accepted = kernel.submit_managed(command("pending"), run_id="run", generation=0)
                self.assertEqual(accepted.execution_id, "pending")
                self.assertEqual(accepted, kernel.submit_managed(command("pending"), run_id="run", generation=0))
            finally:
                kernel.close()

    def test_verified_revision_install_remains_paused_and_replays(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            expiry = time.time() + 300
            envelope = {}
            revision_page = {}
            resume = {}
            activation = {}
            policy, declaration, budget_proof = {}, {}, {}
            budget_clock, advance_budget = [time.time()], [False, 0]
            global_open = [False]
            lease_held = [True]
            def verifier(credential):
                if credential == "manager":
                    return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("run", "kernel:" + p) for p in ("manage_authority", "pause", "control", "cancel")]}
                if credential == "decision":
                    return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("run", "kernel:install_revision")], "decision": dict(envelope)}
                if credential == "page":
                    return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("run", "kernel:stage_revision")], "revision_page": dict(revision_page)}
                if credential == "resume":
                    return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("run", "kernel:resume")], "resume": dict(resume)}
                if credential == "activation":
                    return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("run", "kernel:activate_revision")], "activation": dict(activation)}
                if credential == "budget":
                    return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("run", "kernel:manage_budget"), ("run", "kernel:declare_budget")],
                            "budget_policy": dict(policy), "budget_declaration": dict(declaration)}
                if credential == "resumed-worker":
                    if advance_budget[0]:
                        advance_budget[1] += 1
                        if advance_budget[1] == 5:
                            budget_clock[0] = budget_proof["expires_at"] + 1
                    return {"principal": credential, "expires_at": expiry, "run_id": "run", "generation": 1,
                            "control_epoch": 4, "permissions": [("run", "kernel:" + p) for p in ("worker", "submit", "claim", "start", "budget")],
                            "budget_admission": dict(budget_proof),
                            "control_lease": {"held": lease_held[0], "lease_id": "control-lease", "lease_fence": 1, "expires_at": expiry},
                            "global_admission": {"open": global_open[0], "operation_id": "resume-id",
                                "orchestrator_store_id": "orchestrator", "orchestrator_incarnation": "incarnation",
                                "kernel_store_id": envelope["kernel_store_id"], "orchestrator_receipt": {
                                    "operation_id": "resume-id", "run_id": "run", "generation": 1,
                                    "control_epoch": 4, "state": "active", "committed_at": expiry - 1,
                                    "kernel_store_id": envelope["kernel_store_id"], "orchestrator_store_id": "orchestrator",
                                    "orchestrator_incarnation": "incarnation"}}}
                if credential in ("old", "next"):
                    generation, epoch = (0, 0) if credential == "old" else (1, 3)
                    return {"principal": credential, "expires_at": expiry,
                            "permissions": [("run", "kernel:worker")], "run_id": "run",
                            "generation": generation, "control_epoch": epoch}
                raise ValueError("unknown credential")
            kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
            try:
                kernel.register_run_control("run", max_claims=4, deadline_at=time.time() + 200)
                kernel.protect_run_authority("run", generation=0, expected_epoch=0, worker_credential="old")
                with kernel._transaction() as (connection, _):
                    connection.execute("UPDATE kernel_run_controls SET state='active' WHERE run_id='run'")
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)", ("legacy", "run", 0, 0))
                kernel.prepare_control_pause("barrier", "run", expected_epoch=0, generation=0)
                kernel.complete_control_pause("complete", "barrier", "run", expected_epoch=1, generation=0)
                envelope.update(decision_id="decision-id", operation_id="barrier", barrier_operation_id="barrier",
                    run_id="run", orchestrator_store_id="orchestrator", orchestrator_incarnation="incarnation",
                    kernel_store_id=kernel.kernel_store_identity(), source_revision=0, source_generation=0,
                    source_control_epoch=2, target_generation=1, deployment={"name": "target"},
                    migration_version="one", application_projection_version="one", revision=None,
                    source_application_state={"value": 1}, target_application_state={"value": 2},
                    content_pages={"revision": {"operation_id": "barrier", "total_bytes": 4,
                                                "lease_id": "lease", "lease_fence": 1}})
                revision_page.update(operation_id="barrier", barrier_operation_id="barrier", source_generation=0, decision_id="decision-id", run_id="run",
                    kernel_store_id=kernel.kernel_store_identity(), orchestrator_store_id="orchestrator",
                    orchestrator_incarnation="incarnation", content_kind="revision", page_seq=0,
                    total_bytes=4, chunk="da", complete=False, lease_id="lease", lease_fence=1,
                    lease_expires_at=expiry, lease_held=True)
                with self.assertRaisesRegex(CASConflictError, "staged revision"):
                    kernel.install_revision_decision("decision", worker_credential="next", expected_decision=dict(envelope))
                kernel.stage_revision_content_page("page", expected_page=dict(revision_page))
                with self.assertRaisesRegex(CASConflictError, "staged revision"):
                    kernel.install_revision_decision("decision", worker_credential="next", expected_decision=dict(envelope))
                revision_page.update(page_seq=1, chunk="ta", complete=True)
                kernel.stage_revision_content_page("page", expected_page=dict(revision_page))
                with self.assertRaisesRegex(CASConflictError, "capture"):
                    kernel.install_revision_decision("decision", worker_credential="next", expected_decision=dict(envelope))
                page = 0
                while True:
                    result = kernel.capture_control_pause_page("barrier", expected_page=page, max_items=1)
                    if result["capture_complete"]:
                        break
                    page += 1
                with self.assertRaisesRegex(CASConflictError, "expected decision"):
                    kernel.install_revision_decision("decision", worker_credential="next", expected_decision={})
                with self.assertRaises(StorageIsolationError):
                    kernel.install_revision_decision("decision", worker_credential="old", expected_decision=dict(envelope))
                receipt = kernel.install_revision_decision("decision", worker_credential="next", expected_decision=dict(envelope))
                self.assertEqual((receipt["cleanup"], receipt["activation"]), ("unknown", "closed"))
                self.assertEqual((receipt["claims_used"], receipt["max_claims"]), (0, 4))
                self.assertEqual(receipt, kernel.install_revision_decision("decision", worker_credential="next", expected_decision=dict(envelope)))
                self.assertEqual(kernel.observe_revision_authority("decision-id")["state"], "paused")
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
                self.assertEqual(receipt, kernel.install_revision_decision("decision", worker_credential="next", expected_decision=dict(envelope)))
                import sqlite3
                with contextlib.closing(sqlite3.connect(path)) as external, external:
                    external.execute("UPDATE kernel_store_identity SET store_id='different'")
                with self.assertRaises(CASConflictError):
                    kernel.install_revision_decision("decision", worker_credential="next", expected_decision=dict(envelope))
                with self.assertRaises(CASConflictError):
                    kernel.observe_revision_authority("decision-id")
                with contextlib.closing(sqlite3.connect(path)) as external, external:
                    external.execute("UPDATE kernel_store_identity SET store_id=?", (envelope["kernel_store_id"],))
                with kernel._transaction() as (connection, _):
                    self.assertEqual(tuple(connection.execute("SELECT generation,control_epoch,state FROM kernel_run_controls WHERE run_id='run'").fetchone()), (1, 3, "paused"))
                    self.assertEqual(connection.execute("SELECT generation FROM kernel_managed_executions WHERE execution_id='legacy'").fetchone()[0], 0)
                envelope["deployment"] = {"name": "other"}
                with self.assertRaises(CASConflictError):
                    kernel.install_revision_decision("decision", worker_credential="next", expected_decision=dict(envelope))
                envelope["deployment"] = {"name": "target"}
                activation.update(operation_id="activation-id", run_id="run", decision_id="decision-id",
                    barrier_operation_id="barrier", completion_operation_id="complete",
                    kernel_store_id=kernel.kernel_store_identity(), orchestrator_store_id="orchestrator",
                    orchestrator_incarnation="incarnation", generation=1, expected_control_epoch=3,
                    orchestrator_install_receipt={"installed": True}, kernel_install_receipt=receipt,
                    lease_id="control-lease", lease_fence=1, lease_expires_at=expiry, lease_held=True)
                activated = kernel.activate_revision("activation", expected_decision=dict(activation))
                self.assertEqual(activated["state"], "paused")
                resume.update(operation_id="resume-id", run_id="run", decision_id="decision-id",
                    barrier_operation_id="barrier", completion_operation_id="complete",
                    activation_operation_id="activation-id", activation_receipt=activated,
                    kernel_store_id=kernel.kernel_store_identity(), orchestrator_store_id="orchestrator",
                    orchestrator_incarnation="incarnation", generation=1, expected_control_epoch=3,
                    target_control_epoch=4, orchestrator_install_receipt={"installed": True}, kernel_install_receipt=receipt,
                    lease_id="control-lease", lease_fence=1, lease_expires_at=expiry, lease_held=True)
                with self.assertRaisesRegex(CASConflictError, "budget policy"):
                    kernel.resume_revision("resume", worker_credential="resumed-worker", expected_decision=dict(resume))
                policy.update(policy_id="policy", decision_id="decision-id", run_id="run", generation=1,
                    kernel_store_id=kernel.kernel_store_identity(), orchestrator_store_id="orchestrator",
                    orchestrator_incarnation="incarnation", scopes=[{"owner": "app", "unit": "token", "source_id": "ledger"}])
                self.assertEqual(policy, kernel.install_budget_policy("budget", expected_policy=dict(policy)))
                self.assertEqual(policy, kernel.install_budget_policy("budget", expected_policy=dict(policy)))
                self.assertEqual(policy, kernel.inspect_budget_policy("run", 1))
                with self.assertRaises(StorageIsolationError):
                    kernel.install_budget_policy("budget", expected_policy={**policy, "kernel_store_id": "wrong"})
                policy["policy_id"] = "different"
                with self.assertRaises(CASConflictError):
                    kernel.install_budget_policy("budget", expected_policy=dict(policy))
                policy["policy_id"] = "policy"
                resumed = kernel.resume_revision("resume", worker_credential="resumed-worker", expected_decision=dict(resume))
                kernel.close()
                kernel = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
                self.assertEqual(resumed, kernel.resume_revision("resume", worker_credential="resumed-worker", expected_decision=dict(resume)))
                worker = SQLiteKernel(path, authority_verifier=verifier, worker_credential="resumed-worker")
                worker._now = lambda: budget_clock[0]
                try:
                    work = command("sdk-managed:after-resume")
                    declaration.update(run_id="run", generation=1, policy_id="policy", execution_id=work.execution_id,
                                       command=work.to_dict(), scopes=[], decision_id="decision-id",
                                       kernel_store_id=policy["kernel_store_id"], orchestrator_store_id="orchestrator",
                                       orchestrator_incarnation="incarnation")
                    kernel.declare_budget_dependencies("budget", expected_declaration=dict(declaration))
                    declaration["command"] = replace(work, payload={"changed": True}).to_dict()
                    with self.assertRaises(CASConflictError):
                        kernel.declare_budget_dependencies("budget", expected_declaration=dict(declaration))
                    declaration["command"] = work.to_dict()
                    with self.assertRaises(StorageIsolationError):
                        worker.submit_managed(work, run_id="run", generation=1)
                    global_open[0] = True
                    lease_held[0] = False
                    with self.assertRaises(StorageIsolationError):
                        worker.submit_managed(work, run_id="run", generation=1)
                    lease_held[0] = True
                    blocked = command("sdk-managed:budget-blocked")
                    declaration.update(execution_id=blocked.execution_id, command=blocked.to_dict(), scopes=policy["scopes"])
                    kernel.declare_budget_dependencies("budget", expected_declaration=dict(declaration))
                    budget_proof.update(allowed=True, run_id="run", generation=1, execution_id=blocked.execution_id,
                                        policy_id="policy", scopes=policy["scopes"], expires_at=expiry,
                                        decision_id="decision-id", kernel_store_id=policy["kernel_store_id"],
                                        orchestrator_store_id="orchestrator", orchestrator_incarnation="incarnation")
                    budget_proof["kernel_store_id"] = "wrong"
                    with self.assertRaises(StorageIsolationError):
                        worker.submit_managed(blocked, run_id="run", generation=1)
                    budget_proof["kernel_store_id"] = policy["kernel_store_id"]
                    worker.submit_managed(blocked, run_id="run", generation=1)
                    budget_proof["expires_at"] = time.time() + 30
                    advance_budget[0] = True
                    with self.assertRaises(StorageIsolationError):
                        worker.claim("worker", execution_id=blocked.execution_id)
                    self.assertEqual(worker.get(blocked.execution_id).state, "queued")
                    advance_budget[0] = False
                    budget_clock[0] = time.time()
                    budget_proof["expires_at"] = expiry
                    budget_proof["allowed"] = False
                    with self.assertRaises(StorageIsolationError):
                        worker.claim_and_start("worker", execution_id=blocked.execution_id)
                    worker.submit_managed(work, run_id="run", generation=1)
                    global_open[0] = False
                    with self.assertRaises(StorageIsolationError):
                        worker.claim("worker", execution_id=work.execution_id)
                    global_open[0] = True
                    lease_held[0] = False
                    with self.assertRaises(StorageIsolationError):
                        worker.claim("worker", execution_id=work.execution_id)
                    lease_held[0] = True
                    watermark = worker._connection.execute("SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()[0]
                    budget_proof.update(allowed=True, expires_at=watermark + 30)
                    advance_budget[:] = [True, 0]
                    with self.assertRaises(BudgetScanContinuation) as late:
                        worker.claim("worker")
                    self.assertEqual(worker.get(blocked.execution_id).state, "queued")
                    advance_budget[0] = False
                    budget_clock[0] = time.time()
                    budget_proof["allowed"] = False
                    lease = worker.claim("worker", budget_scan_cursor=late.exception.cursor)
                    self.assertEqual(lease.execution_id, work.execution_id)
                    self.assertEqual(worker.get(blocked.execution_id).state, "queued")
                    kernel.fence_cancelled_run("cancel", "run", expected_epoch=4, generation=1)
                    with self.assertRaises(CASConflictError):
                        worker.start(lease)
                    with self.assertRaises(CASConflictError):
                        kernel.resume_revision("resume", worker_credential="resumed-worker", expected_decision=dict(resume))
                finally:
                    worker.close()
            finally:
                kernel.close()

    def test_verifier_errors_do_not_expose_credentials_in_tracebacks(self):
        import traceback
        secret = "secret " + "credential"
        with tempfile.TemporaryDirectory() as temporary:
            def verifier(credential):
                raise ValueError(secret)
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3", authority_verifier=verifier,
                                  worker_credential=secret)
            try:
                kernel.register_run_control("run", max_claims=1, deadline_at=time.time() + 60)
                try:
                    kernel.protect_run_authority("run", generation=0, expected_epoch=0,
                                                 worker_credential=secret)
                except StorageIsolationError as error:
                    self.assertNotIn(secret, "".join(traceback.format_exception(error)))
                else:
                    self.fail("invalid credential was accepted")
            finally:
                kernel.close()

    def test_claim_excludes_unresolved_execution_without_marking_it_settled(self):
        with tempfile.TemporaryDirectory() as temporary:
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3")
            try:
                kernel.submit(command("blocked"))
                kernel.submit(command("eligible"))
                self.assertIsNone(kernel.claim_and_start("worker", execution_id="blocked",
                                                         exclude_execution_ids=("blocked",)))
                lease = kernel.claim_and_start("worker", exclude_execution_ids=("blocked",))
                self.assertEqual(lease.execution_id, "eligible")
                self.assertEqual(kernel.get("blocked").state, "queued")
                with self.assertRaises(ValueError):
                    kernel.claim_and_start("worker", exclude_execution_ids=[str(i) for i in range(513)])
            finally:
                kernel.close()

    def test_protected_run_rejects_missing_and_revoked_worker_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            expiry = time.time() + 300
            global_open = [True]
            initial_receipt = {}
            def verifier(credential):
                if credential == "manager":
                    return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("run", "kernel:manage_authority"), ("run", "kernel:control")]}
                if credential == "bind":
                    return {"principal": "manager", "expires_at": expiry,
                            "permissions": [("run", "kernel:bind_initial")], "initial_admission_receipt": dict(initial_receipt)}
                if credential == "worker":
                    return {"principal": "worker", "expires_at": expiry, "run_id": "run",
                            "generation": 0, "control_epoch": 0,
                            "global_admission": {"open": global_open[0], "run_id": "run", "generation": 0, "control_epoch": 0,
                                                 "orchestrator_receipt": dict(initial_receipt)},
                            "permissions": [("run", "kernel:" + scope) for scope in
                                            ("worker", "submit", "claim", "start", "effect", "child", "work")]}
                raise ValueError("unknown credential")
            manager = SQLiteKernel(path, authority_verifier=verifier, worker_credential="manager")
            worker = SQLiteKernel(path, authority_verifier=verifier, worker_credential="worker")
            missing = SQLiteKernel(path)
            try:
                work = command("legacy-protected")
                manager.submit(work)
                manager.register_run_control("run", max_claims=4, deadline_at=time.time() + 60)
                with manager._transaction() as (connection, _):
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)", (work.execution_id, "run", 0, 0))
                manager.protect_run_authority("run", generation=0, expected_epoch=0, worker_credential="worker")
                initial_receipt.update(operation_id="initial", run_id="run", generation=0, control_epoch=0,
                    state="active", committed_at=time.time(), kernel_store_id="wrong-store",
                    orchestrator_store_id="orch", orchestrator_incarnation="incarnation")
                with self.assertRaises(CASConflictError):
                    manager.bind_initial_admission("bind", expected_receipt=dict(initial_receipt))
                initial_receipt["kernel_store_id"] = manager.kernel_store_identity()
                manager.bind_initial_admission("bind", expected_receipt=dict(initial_receipt))
                with self.assertRaisesRegex(CASConflictError, "activation"):
                    manager.set_run_control("run", expected_epoch=0, state="active", generation=0)
                # Construct a protected active fixture only; public activation is deliberately closed.
                with manager._transaction() as (connection, _):
                    connection.execute("UPDATE kernel_run_controls SET state='active' WHERE run_id='run'")
                independent = replace(command("ordinary-independent"), correlation_id="other")
                manager.submit(independent)
                self.assertEqual(missing.claim("worker").execution_id, independent.execution_id)
                with self.assertRaises(StorageIsolationError):
                    missing.claim("worker", execution_id=work.execution_id)
                initial_receipt["orchestrator_store_id"] = "wrong-orchestrator"
                with self.assertRaises(StorageIsolationError):
                    worker.claim("worker", execution_id=work.execution_id)
                initial_receipt["orchestrator_store_id"] = "orch"
                lease = worker.claim("worker", execution_id=work.execution_id)
                global_open[0] = False
                with self.assertRaises(StorageIsolationError):
                    worker.verify(lease)
                global_open[0] = True
                manager.revoke_run_authority("run", generation=0, expected_epoch=0)
                with self.assertRaises(CASConflictError):
                    worker.start(lease)
                self.assertEqual(worker.get(work.execution_id).state, "leased")
            finally:
                missing.close()
                worker.close()
                manager.close()

    def test_pause_pages_are_bounded_replayable_and_rounds_are_ordered(self):
        with tempfile.TemporaryDirectory() as temporary:
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3")
            try:
                kernel.register_run_control("run", max_claims=4, deadline_at=time.time() + 60)
                with kernel._transaction() as (connection, _):
                    for execution_id in ("one", "two"):
                        connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                                           (execution_id, "run", 0, 0))
                kernel.set_run_control("run", expected_epoch=0, state="active", generation=0)
                receipt = kernel.prepare_control_pause("barrier", "run", expected_epoch=1, generation=0)
                self.assertEqual(receipt["capture_status"], "incomplete")
                first = kernel.capture_control_pause_page("barrier", expected_page=0, max_items=1)
                self.assertEqual(first["items"][0]["execution_id"], "one")
                self.assertEqual(first, kernel.capture_control_pause_page("barrier", expected_page=0, max_items=1))
                with self.assertRaises(CASConflictError):
                    kernel.capture_control_pause_page("barrier", expected_page=0, round_id=1)
                second = kernel.capture_control_pause_page("barrier", expected_page=1, max_items=1)
                self.assertEqual(second["items"][0]["execution_id"], "two")
                kernel.capture_control_pause_page("barrier", expected_page=2, max_items=1)
                final = kernel.capture_control_pause_page("barrier", expected_page=3, max_items=1)
                while not final["capture_complete"]:
                    final = kernel.capture_control_pause_page("barrier", expected_page=final["next_page"], max_items=1)
                self.assertTrue(final["capture_complete"])
                later = kernel.capture_control_pause_page("barrier", expected_page=0, round_id=1)
                self.assertEqual(later["round_id"], 1)
                self.assertEqual(kernel.get_run_control("run")["state"], "pausing")
            finally:
                kernel.close()

    def test_page_failure_and_later_observation_are_not_partial_or_rewritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            kernel = SQLiteKernel(path)
            try:
                work = command("legacy-work")
                kernel.submit(work)
                kernel.register_run_control("run", max_claims=4, deadline_at=time.time() + 60)
                with kernel._transaction() as (connection, _):
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)", (work.execution_id, "run", 0, 0))
                kernel.set_run_control("run", expected_epoch=0, state="active", generation=0)
                kernel.prepare_control_pause("barrier", "run", expected_epoch=1, generation=0)
                with patch.object(kernel, "_encode_pause_receipt", side_effect=RuntimeError("interrupted")):
                    with self.assertRaisesRegex(RuntimeError, "interrupted"):
                        kernel.capture_control_pause_page("barrier", expected_page=0)
                first = kernel.capture_control_pause_page("barrier", expected_page=0)
                self.assertEqual(first["items"][0]["state"], "queued")
                kernel.cancel(work.execution_id, reason="test")
                final = kernel.capture_control_pause_page("barrier", expected_page=1)
                while not final["capture_complete"]:
                    final = kernel.capture_control_pause_page("barrier", expected_page=final["next_page"])
                later = kernel.capture_control_pause_page("barrier", expected_page=0, round_id=1)
                self.assertEqual(later["items"][0]["state"], "cancelled")
                kernel.close()
                kernel = SQLiteKernel(path)
                self.assertEqual(kernel.capture_control_pause_page("barrier", expected_page=0), first)
                self.assertEqual(kernel.capture_control_pause_page("barrier", expected_page=0, round_id=1), later)
            finally:
                kernel.close()

    def test_late_cancellation_cannot_register_after_concurrent_barrier(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            first, second = SQLiteKernel(path), SQLiteKernel(path)
            try:
                first.register_run_control("run", max_claims=4, deadline_at=time.time() + 60)
                first.set_run_control("run", expected_epoch=0, state="active", generation=0)
                locked, release = threading.Event(), threading.Event()
                original = first._encode_pause_receipt
                def hold(*args, **kwargs):
                    result = original(*args, **kwargs)
                    locked.set()
                    if not release.wait(5):
                        raise TimeoutError("test did not release barrier")
                    return result
                first._encode_pause_receipt = hold
                result, errors = [], []
                def prepare():
                    try:
                        result.append(first.prepare_control_pause("barrier", "run", expected_epoch=1, generation=0))
                    except Exception as error:
                        errors.append(error)
                def late_cancel():
                    try:
                        second.cancel_managed_before_accept(command("sdk-managed:late"), run_id="run", generation=0)
                    except Exception as error:
                        errors.append(error)
                t1 = threading.Thread(target=prepare)
                t1.start()
                self.assertTrue(locked.wait(5))
                t2 = threading.Thread(target=late_cancel)
                t2.start()
                release.set()
                t1.join(5)
                t2.join(5)
                self.assertFalse(t1.is_alive() or t2.is_alive())
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["capture_status"], "incomplete")
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], CASConflictError)
                with second._lock:
                    self.assertIsNone(second._connection.execute(
                        "SELECT 1 FROM kernel_managed_executions WHERE execution_id='sdk-managed:late'").fetchone())
            finally:
                release.set()
                first.close()
                second.close()

    def test_barrier_fences_legacy_effect_and_child_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            kernel = SQLiteKernel(path)
            try:
                parent = command("legacy-running")
                kernel.submit(parent)
                kernel.register_run_control("run", max_claims=4, deadline_at=time.time() + 60)
                with kernel._transaction() as (connection, _):
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                                       (parent.execution_id, "run", 0, 0))
                kernel.set_run_control("run", expected_epoch=0, state="active", generation=0)
                lease = kernel.claim_and_start("worker", execution_id=parent.execution_id)
                for effect_id in ("effect-a", "effect-b", "effect-c"):
                    kernel.prepare_effect(lease, effect_id=effect_id, name="send", request={})
                receipt = kernel.prepare_control_pause("barrier", "run", expected_epoch=1, generation=0)
                self.assertEqual(receipt["capture_status"], "incomplete")
                seen = []
                page_number = 0
                while True:
                    page = kernel.capture_control_pause_page("barrier", expected_page=page_number, max_items=1)
                    if page["phase"] == "effects":
                        seen.extend((item["effect_id"], item["execution_generation"]) for item in page["items"])
                    if page["capture_complete"]:
                        break
                    page_number = page["next_page"]
                self.assertEqual(seen, [("effect-a", 0), ("effect-b", 0), ("effect-c", 0)])
                with self.assertRaises(CASConflictError):
                    kernel.prepare_effect(lease, effect_id="new-effect", name="send", request={})
                with self.assertRaises(CASConflictError):
                    kernel.claim_effect(lease, "effect-a")
                with self.assertRaises(CASConflictError):
                    kernel.submit_child(command("sdk-managed:child:new"), lease, BudgetEnvelope((), sample_clock()))
                with self.assertRaises(CASConflictError):
                    kernel.submit_managed(command("sdk-managed:late"), run_id="run", generation=0)
            finally:
                kernel.close()

    def test_pause_receipt_survives_reopen_and_keeps_control_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.sqlite3"
            kernel = SQLiteKernel(path)
            work = command("legacy-work")
            kernel.submit(work)
            kernel.register_run_control("run", max_claims=4, deadline_at=time.time() + 60)
            with kernel._transaction() as (connection, _):
                for execution_id in ("legacy-work", "pending"):
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                                       (execution_id, "run", 0, 0))
            kernel.set_run_control("run", expected_epoch=0, state="active", generation=0)
            lease = kernel.claim("worker")
            receipt = kernel.prepare_control_pause("operation", "run", expected_epoch=1, generation=0)
            self.assertEqual(receipt["claims_used"], 1)
            self.assertEqual(receipt["store_id"], kernel.kernel_store_identity())
            page = kernel.capture_control_pause_page("operation", expected_page=0)
            self.assertEqual([(row["execution_id"], row["state"]) for row in page["items"]],
                             [("legacy-work", "leased"), ("pending", None)])
            self.assertEqual(receipt["cleanup"], "unknown")
            with self.assertRaises(CASConflictError):
                kernel.start(lease)
            with self.assertRaises(CASConflictError):
                kernel.set_run_control("run", expected_epoch=2, state="active", generation=0)
            with self.assertRaises(CASConflictError):
                kernel.complete_control_pause("complete", "operation", "run", expected_epoch=1, generation=0)
            paused = kernel.complete_control_pause("complete", "operation", "run", expected_epoch=2, generation=0)
            self.assertEqual(paused["kind"], "local_paused")
            self.assertEqual(paused["cleanup"], "unknown")
            self.assertEqual(paused["capture_status"], "incomplete")
            with self.assertRaises(CASConflictError):
                kernel.set_run_control("run", expected_epoch=3, state="active", generation=0)
            kernel.close()
            kernel = SQLiteKernel(path)
            try:
                self.assertEqual(kernel.prepare_control_pause("operation", "run", expected_epoch=1, generation=0), receipt)
                self.assertEqual(kernel.complete_control_pause("complete", "operation", "run", expected_epoch=2, generation=0), paused)
                with self.assertRaises(CASConflictError):
                    kernel.complete_control_pause("complete", "different", "run", expected_epoch=2, generation=0)
                with self.assertRaises(CASConflictError):
                    kernel.prepare_control_pause("operation", "run", expected_epoch=2, generation=0)
                with self.assertRaises(CASConflictError):
                    kernel.set_run_control("run", expected_epoch=3, state="active", generation=0)
            finally:
                kernel.close()

    def test_managed_retry_requires_existing_execution_and_matching_membership(self):
        with tempfile.TemporaryDirectory() as temporary:
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3")
            try:
                legacy = replace(command("legacy-existing"), correlation_id="original-correlation")
                pending = command("legacy-pending")
                kernel.submit(legacy)
                kernel.register_run_control("run", max_claims=3, deadline_at=time.time() + 60)
                with kernel._transaction() as (connection, _):
                    for item in (legacy, pending):
                        connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                                           (item.execution_id, "run", 0, 0))
                self.assertEqual(kernel.submit_managed(legacy, run_id="run", generation=0).execution_id,
                                 legacy.execution_id)
                self.assertEqual(kernel.cancel_managed_before_accept(
                    legacy, run_id="run", generation=0).execution_id, legacy.execution_id)
                self.assertEqual(kernel.managed_execution_receipt(
                    legacy, run_id="run", generation=0).execution_id, legacy.execution_id)
                for item, run, generation in ((pending, "run", 0),
                                              (legacy, "other", 0),
                                              (legacy, "run", 1),
                                              (replace(legacy, payload={"changed": True}), "run", 0)):
                    with self.assertRaises(StorageIsolationError):
                        kernel.managed_execution_receipt(item, run_id=run, generation=generation)
                with self.assertRaises(StorageIsolationError):
                    kernel.submit_managed(pending, run_id="run", generation=0)
                with self.assertRaises(StorageIsolationError):
                    kernel.cancel_managed_before_accept(pending, run_id="run", generation=0)
            finally:
                kernel.close()

    def test_managed_parent_cannot_convert_existing_ordinary_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3")
            try:
                parent, existing = command("legacy-parent"), command("ordinary-child")
                kernel.submit(parent)
                kernel.submit(existing)
                kernel.register_run_control("run", max_claims=3, deadline_at=time.time() + 60)
                with kernel._transaction() as (connection, _):
                    connection.execute("INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                                       (parent.execution_id, "run", 0, 0))
                kernel.set_run_control("run", expected_epoch=0, state="active", generation=0)
                lease = kernel.claim_and_start("worker", execution_id=parent.execution_id)
                child = command("sdk-managed:child:new")
                child = replace(child, idempotency_key=existing.idempotency_key)
                with self.assertRaises(CASConflictError):
                    kernel.submit_child(child, lease, BudgetEnvelope((), sample_clock()))
                with kernel._lock:
                    self.assertIsNone(kernel._connection.execute(
                        "SELECT 1 FROM kernel_managed_executions WHERE execution_id=?",
                        (child.execution_id,)).fetchone())
            finally:
                kernel.close()

    def test_ordinary_parent_cannot_bind_a_managed_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3")
            try:
                parent = command("ordinary-parent")
                child = command("legacy-child")
                kernel.submit(parent)
                kernel.submit(child)
                kernel.register_run_control("run", max_claims=2, deadline_at=time.time() + 60)
                with kernel._transaction() as (connection, _):
                    connection.execute(
                        "INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                        (child.execution_id, "run", 0, 0),
                    )
                lease = kernel.claim_and_start("worker", execution_id=parent.execution_id)
                with self.assertRaisesRegex(ValueError, "ordinary parent"):
                    kernel.submit_child(child, lease, BudgetEnvelope((), sample_clock()))
            finally:
                kernel.close()

    def test_existing_id_is_governed_by_run_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            kernel = SQLiteKernel(Path(temporary) / "kernel.sqlite3")
            try:
                legacy = command("legacy-execution")
                ordinary = command("ordinary-execution")
                kernel.submit(legacy)
                kernel.submit(ordinary)
                kernel.register_run_control("run", max_claims=1, deadline_at=time.time() + 60)
                with kernel._transaction() as (connection, _):
                    connection.execute(
                        "INSERT INTO kernel_managed_executions VALUES(?,?,?,?)",
                        (legacy.execution_id, "run", 0, 0),
                    )
                with self.assertRaises(StorageIsolationError):
                    kernel.submit(legacy)
                self.assertEqual(kernel.claim("worker").execution_id, ordinary.execution_id)
                self.assertIsNone(kernel.claim("worker"))
                kernel.set_run_control("run", expected_epoch=0, state="active", generation=0)
                lease = kernel.claim("worker")
                self.assertEqual(lease.execution_id, legacy.execution_id)
                self.assertEqual(kernel.get_run_control("run")["claims_used"], 1)
                with self.assertRaises(CASConflictError):
                    kernel.cancel(legacy.execution_id, reason="test")
                kernel.set_run_control("run", expected_epoch=1, state="pausing", generation=0)
                with self.assertRaises(CASConflictError):
                    kernel.start(lease)
                kernel.set_run_control("run", expected_epoch=2, state="pausing", generation=0,
                                       drain_execution_ids=(legacy.execution_id,))
                self.assertEqual(kernel.start(lease).execution_id, legacy.execution_id)
            finally:
                kernel.close()


if __name__ == "__main__":
    unittest.main()
