from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import (
    ExecutionCommandV2, ExecutionResultV2, ResultConflictError,
    RetryPolicy, SQLiteKernel, StaleFenceError,
)
from dispatcher_sdk.orchestrator.results import ResultsMixin


class Clock:
    value = 100.0

    def __call__(self):
        return self.value


class Harness(ResultsMixin):
    def __init__(self, path, kernel, clock, *, max_result_deliveries=2):
        self.path, self.kernel, self.clock = path, kernel, clock
        self.max_result_deliveries = max_result_deliveries
        self.synced = []
        connection = self._connect()
        try:
            self._init_results(connection)
            connection.commit()
        finally:
            connection.close()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def sync_execution(self, execution_id):
        self.synced.append(self.kernel.get(execution_id))


class SDKResultDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.clock = Clock()
        self.kernel = SQLiteKernel(self.path / "kernel.db", now=self.clock)
        self.addCleanup(self.kernel.close)
        self.sdk = Harness(self.path / "sdk.db", self.kernel, self.clock)

    def terminal(self, execution_id="task"):
        command = ExecutionCommandV2(
            execution_id=execution_id, idempotency_key=execution_id, registry_revision="v1",
            correlation_id="run", causation_id="cause", handler_id="echo",
            handler_contract_version=1, retry_policy=RetryPolicy(max_attempts=1),
            timeout_seconds=10, payload={"input": 1},
        )
        self.kernel.submit(command)
        lease = self.kernel.claim_and_start("worker", registry_revision="v1")
        result = ExecutionResultV2(
            result_id="result-" + execution_id, execution_id=execution_id,
            status="succeeded", attempt=lease.attempt, fence=lease.fence, effect_ids=[],
            started_at=self.clock(), completed_at=self.clock(), correlation_id="run",
            causation_id="cause", value={"answer": 42}, error=None,
        )
        self.kernel.complete(lease, result)
        return result

    def claim(self):
        return self.sdk.claim_results(owner="application", lease_seconds=5, limit=10)[0]

    def ack(self, claim):
        return self.sdk.acknowledge_result(claim["result"]["result_id"],
                                           lease_id=claim["lease_id"], fence=claim["fence"])

    def test_kernel_delivery_commits_before_ack_and_application_delivery_is_independent(self):
        result = self.terminal()
        original = self.kernel.ack_outbox

        def check_commit(*args, **kwargs):
            record = self.sdk.load_result_outbox(result.result_id)
            self.assertEqual(record["result"], result)
            self.assertEqual(record["state"], "pending")
            self.assertEqual(len(self.sdk.synced), 1)
            return original(*args, **kwargs)

        with patch.object(self.kernel, "ack_outbox", side_effect=check_commit):
            self.assertEqual(self.sdk.pump_results(), 1)
        self.assertEqual(self.kernel.load_result_outbox(result.result_id)["state"], "delivered")
        claim = self.claim()
        self.assertEqual(claim["result"], result.to_dict())
        self.assertEqual(claim["kernel_revision"], self.kernel.get(result.execution_id).revision)
        self.assertEqual(self.ack(claim)["state"], "delivered")
        self.assertEqual(self.ack(claim)["state"], "delivered")
        self.assertEqual(self.sdk.result_outbox_status().pending, 0)

    def test_crash_after_sdk_commit_replays_without_resetting_application_lease(self):
        result = self.terminal()
        with patch.object(self.kernel, "ack_outbox", side_effect=RuntimeError("crash before ack")):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                self.sdk.pump_results(lease_seconds=1)
        claim = self.claim()
        self.clock.value += 2
        self.sdk = Harness(self.path / "sdk.db", self.kernel, self.clock)
        self.assertEqual(self.sdk.pump_results(), 1)
        record = self.sdk.load_result_outbox(result.result_id)
        self.assertEqual((record["state"], record["lease_id"], record["fence"]),
                         ("delivering", claim["lease_id"], claim["fence"]))
        self.assertEqual(self.ack(claim)["state"], "delivered")

    def test_failed_snapshot_sync_never_acknowledges_or_enqueues(self):
        result = self.terminal()
        with patch.object(self.sdk, "sync_execution", side_effect=RuntimeError("sync failed")):
            with self.assertRaisesRegex(RuntimeError, "sync failed"):
                self.sdk.pump_results(lease_seconds=1)
        with self.assertRaises(KeyError):
            self.sdk.load_result_outbox(result.result_id)
        self.assertEqual(self.kernel.load_result_outbox(result.result_id)["state"], "delivering")
        self.clock.value += 2
        self.assertEqual(self.sdk.pump_results(), 1)

    def test_fabricated_kernel_delivery_is_rejected_against_authoritative_snapshot(self):
        result = self.terminal()
        delivery = self.kernel.claim_outbox("intercept", lease_seconds=5)
        delivery["result"] = replace(result, value={"answer": 42.0})
        with patch.object(self.kernel, "claim_outbox", return_value=delivery):
            with self.assertRaises(ResultConflictError):
                self.sdk.pump_results(limit=1)
        self.assertFalse(self.sdk.synced)
        self.assertEqual(self.sdk.result_outbox_status().pending, 0)

    def test_expiry_fencing_dead_letter_and_revision_checked_retry(self):
        result = self.terminal()
        self.sdk.pump_results()
        first = self.claim()
        self.clock.value += 5
        self.assertEqual(self.sdk.reap_results(), 1)
        second = self.claim()
        self.assertGreater(second["fence"], first["fence"])
        with self.assertRaises(StaleFenceError):
            self.ack(first)
        self.clock.value += 5
        self.assertEqual(self.sdk.reap_results(), 1)
        dead = self.sdk.load_result_outbox(result.result_id)
        self.assertEqual(dead["state"], "dead")
        self.assertEqual(self.sdk.result_outbox_status([result.execution_id]).dead, 1)
        self.assertEqual(self.sdk.claim_results(owner="app", lease_seconds=5, limit=1), ())
        with self.assertRaises(StaleFenceError):
            self.sdk.retry_result_outbox(result.result_id, expected_revision=dead["revision"] - 1)
        reopened = self.sdk.retry_result_outbox(result.result_id, expected_revision=dead["revision"])
        self.assertEqual(reopened["attempts"], 0)
        self.assertEqual(self.sdk.retry_result_outbox(result.result_id, expected_revision=dead["revision"]), reopened)
        third = self.claim()
        self.assertGreater(third["fence"], second["fence"])
        self.assertEqual(self.ack(third)["state"], "delivered")

    def test_clock_rollback_does_not_revive_rejected_expired_lease(self):
        self.terminal()
        self.sdk.pump_results()
        claim = self.claim()
        self.clock.value += 6
        with self.assertRaises(StaleFenceError):
            self.ack(claim)
        self.clock.value -= 100
        self.sdk = Harness(self.path / "sdk.db", self.kernel, self.clock)
        with self.assertRaises(StaleFenceError):
            self.ack(claim)

    def test_concurrent_consumers_receive_disjoint_leases(self):
        for value in range(5):
            self.terminal(str(value))
        self.sdk.pump_results()
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda n: self.sdk.claim_results(owner=str(n), lease_seconds=5, limit=2), range(4)))
        ids = [claim["result"]["result_id"] for group in claims for claim in group]
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)
        self.assertEqual(self.sdk.result_outbox_status().delivering, 5)
        self.assertEqual(self.sdk.result_outbox_status([]).delivering, 0)

    def test_invalid_limits_and_leases_fail_before_consuming(self):
        for limit in (0, True, -1):
            with self.assertRaises(ValueError):
                self.sdk.pump_results(limit=limit)
        for duration in (0, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                self.sdk.claim_results(owner="app", lease_seconds=duration, limit=1)
        with self.assertRaises(ValueError):
            Harness(self.path / "invalid.db", self.kernel, self.clock, max_result_deliveries=True)


class SDKInboundRecoveryIntegrationTests(unittest.TestCase):
    def test_real_orchestrator_recovers_inbound_dead_letter_without_rerunning_execution(self):
        from dispatcher_sdk.orchestrator import Orchestrator

        with tempfile.TemporaryDirectory() as temp:
            clock = Clock()
            kernel = SQLiteKernel(Path(temp) / "kernel.db", now=clock, outbox_max_attempts=1)
            self.addCleanup(kernel.close)
            sdk = Orchestrator(Path(temp) / "sdk.db", kernel, clock=clock)
            command = ExecutionCommandV2(
                execution_id="execution", idempotency_key="command", registry_revision="v1",
                correlation_id="run", causation_id=None, handler_id="echo", handler_contract_version=1,
                retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=10, payload={})
            sdk.create_run("run", command_id="create")
            sdk.apply_operations("run", command_id="schedule", expected_revision=0, operations=[
                {"kind": "add_task", "task_id": "task", "command": command.to_dict()},
                {"kind": "dispatch", "task_id": "task"},
            ])
            sdk.flush()
            lease = kernel.claim_and_start("worker", registry_revision="v1")
            result = ExecutionResultV2(
                result_id="result", execution_id="execution", status="succeeded",
                attempt=lease.attempt, fence=lease.fence, effect_ids=[], started_at=clock(),
                completed_at=clock(), correlation_id="run", causation_id=None, value={"ok": True}, error=None)
            terminal = kernel.complete(lease, result)
            with patch.object(sdk, "sync_execution", side_effect=RuntimeError("temporary synchronization failure")):
                with self.assertRaises(RuntimeError):
                    sdk.pump_results(lease_seconds=1)
            clock.value += 2
            self.assertEqual(sdk.reap_results(), 1)
            self.assertEqual(sdk.kernel_result_outbox_status(["execution"]).dead, 1)
            dead = sdk.load_kernel_result_outbox("result")
            self.assertEqual(dead["state"], "dead")
            with self.assertRaises(StaleFenceError):
                sdk.retry_kernel_result_outbox("result", expected_revision=dead["revision"] - 1)
            sdk.retry_kernel_result_outbox("result", expected_revision=dead["revision"])
            self.assertEqual(sdk.pump_results(), 1)
            self.assertEqual(sdk.load_kernel_result_outbox("result")["state"], "delivered")
            self.assertEqual(sdk.result_outbox_status().pending, 1)
            claim = sdk.claim_results(owner="application", lease_seconds=5, limit=1)[0]
            sdk.acknowledge_result("result", lease_id=claim["lease_id"], fence=claim["fence"])
            self.assertEqual(kernel.get("execution"), terminal)
            self.assertEqual(sdk.get_run("run")["tasks"]["task"]["attempts"][0]["result"], result.to_dict())
