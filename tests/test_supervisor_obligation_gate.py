"""Exact-generation process obligations gate retry across Kernel clients."""
import contextlib
import multiprocessing
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from dispatcher_sdk.execution_kernel import CASConflictError, SQLiteKernel, StaleFenceError, StorageIsolationError
from tests.test_execution_kernel_v2_sqlite import make_command, make_result


def _claim_after_restart(path, queue):
    with SQLiteKernel(path, now=lambda: 108.0) as kernel:
        lease = kernel.claim("restart", execution_id="first")
        queue.put(None if lease is None else (lease.execution_id, lease.attempt, lease.fence))


class SupervisorObligationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "kernel.sqlite")
        self.now = 100.0
        self.decision = {}
        self.held = True
        def verify(credential):
            if credential != "host" or not self.held:
                raise ValueError("host authority revoked")
            return {"principal": "host", "expires_at": 200.0,
                    "permissions": [(self.decision["execution_id"], "kernel:resolve_supervisor")],
                    "supervisor_resolution": dict(self.decision)}
        self.kernel = SQLiteKernel(self.path, now=lambda: self.now, authority_verifier=verify)
        self.addCleanup(self.kernel.close)

    def decision_for(self, lease, *, outcome="unknown"):
        self.decision = {"execution_id": lease.execution_id, "attempt": lease.attempt,
                         "fence": lease.fence, "cleanup": "confirmed", "outcome": outcome,
                         "disposition": "retry_authorized", "evidence": "host-receipt-1"}
        return dict(self.decision)

    def test_expiry_restart_exact_resolution_and_unrelated_progress(self):
        self.kernel.submit(make_command("first", attempts=3))
        self.kernel.submit(make_command("other", attempts=3))
        lease = self.kernel.claim_and_start("first-worker", execution_id="first", lease_seconds=1)
        original = self.kernel.register_supervisor_obligation(lease)
        self.assertEqual(self.kernel.register_supervisor_obligation(lease), original)
        self.now = 108.0
        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        process = ctx.Process(target=_claim_after_restart, args=(self.path, queue))
        process.start()
        process.join(20)
        self.assertFalse(process.is_alive())
        self.assertEqual(process.exitcode, 0)
        self.assertIsNone(queue.get(timeout=2))
        self.assertEqual(self.kernel.get("first").state, "running")
        other = self.kernel.claim("other-worker", execution_id="other")
        self.assertEqual(other.execution_id, "other")
        decision = self.decision_for(lease)
        self.held = False
        with self.assertRaises(StorageIsolationError):
            self.kernel.resolve_supervisor_obligation("host", expected_resolution=decision)
        self.held = True
        changed = dict(decision, fence=decision["fence"] + 1)
        with self.assertRaises(StorageIsolationError):
            self.kernel.resolve_supervisor_obligation("host", expected_resolution=changed)
        self.assertTrue(self.kernel.resolve_supervisor_obligation("host", expected_resolution=decision)["resolved"])
        self.assertTrue(self.kernel.resolve_supervisor_obligation("host", expected_resolution=decision)["resolved"])
        retried = self.kernel.claim("retry", execution_id="first")
        self.assertEqual(retried.execution_id, "first")
        self.assertGreater(retried.fence, lease.fence)
        with self.assertRaises(CASConflictError):
            self.kernel.resolve_supervisor_obligation("host", expected_resolution=decision)
        queue.close()

    def test_retryable_result_is_retained_but_retry_waits_for_cleanup(self):
        self.kernel.submit(make_command("first", attempts=3))
        lease = self.kernel.claim_and_start("worker", execution_id="first")
        self.kernel.register_supervisor_obligation(lease)
        result = make_result(self.kernel, lease, status="failed", retryable=True)
        completed = self.kernel.complete(lease, result)
        self.assertEqual(completed.state, "queued")
        self.assertIsNone(self.kernel.claim("second", execution_id="first"))
        events = self.kernel.events("first")
        self.assertTrue(any(event["event_type"] == "retry_scheduled" and event["data"]["result"]["result_id"] == result.result_id for event in events))
        decision = self.decision_for(lease, outcome="failed")
        self.kernel.resolve_supervisor_obligation("host", expected_resolution=decision)
        self.assertEqual(self.kernel.claim("second", execution_id="first").attempt, lease.attempt + 1)

    def test_competing_registration_and_expiry_are_transactional(self):
        self.kernel.submit(make_command("first", attempts=3))
        lease = self.kernel.claim_and_start("worker", execution_id="first", lease_seconds=1)
        ready = threading.Barrier(2)
        outcomes = {}
        def register():
            with SQLiteKernel(self.path, now=lambda: 100.0) as client:
                ready.wait()
                try:
                    client.register_supervisor_obligation(lease)
                    outcomes["registered"] = True
                except Exception as error:
                    outcomes["error"] = type(error).__name__
        def claim():
            with SQLiteKernel(self.path, now=lambda: 108.0) as client:
                ready.wait()
                outcomes["claim"] = client.claim("new-worker", execution_id="first")
        threads = [threading.Thread(target=register), threading.Thread(target=claim)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        if outcomes.get("registered"):
            self.assertIsNone(outcomes["claim"])
        else:
            self.assertIn(outcomes.get("error"), {"StaleFenceError"})
            self.assertIsNotNone(outcomes["claim"])

    def test_sdk_confirmed_cleanup_and_retry_settle_atomically(self):
        self.kernel.submit(make_command("first", attempts=3))
        lease = self.kernel.claim_and_start("worker", execution_id="first")
        self.kernel.register_supervisor_obligation(lease)
        result = make_result(self.kernel, lease, status="failed", retryable=True)
        state = self.kernel._complete_sdk_result(lease, result, budget_envelope=None,
                                                 supervisor_cleanup_confirmed=True)
        self.assertEqual(state.state, "queued")
        self.assertEqual(self.kernel.claim("retry", execution_id="first").attempt, lease.attempt + 1)

    def test_timeout_cleanup_retry_survives_lost_ack(self):
        self.kernel.submit(make_command("first", attempts=3, retry_timeouts=True))
        lease = self.kernel.claim_and_start("worker", execution_id="first")
        self.kernel.register_supervisor_obligation(lease)
        result = make_result(self.kernel, lease, status="timed_out", retryable=True)
        self.assertEqual(self.kernel._complete_sdk_result(lease, result, budget_envelope=None,
            supervisor_cleanup_confirmed=True).state, "queued")
        # Retrying the old ACK cannot settle it a second time; its durable
        # retry event and resolution remain available after reopening.
        with SQLiteKernel(self.path, now=lambda: self.now) as restarted:
            with self.assertRaises(StaleFenceError):
                restarted._complete_sdk_result(lease, result, budget_envelope=None, supervisor_cleanup_confirmed=True)
            self.assertEqual(restarted.inspect_supervisor_obligations("first")["obligations"][0]["state"], "resolved")
            self.assertTrue(any(event["event_type"] == "retry_scheduled" and event["data"]["result"]["result_id"] == result.result_id
                                for event in restarted.events("first")))
            self.assertEqual(restarted.claim("retry", execution_id="first").attempt, lease.attempt + 1)

    def test_cancelled_execution_cannot_release_using_late_result(self):
        self.kernel.submit(make_command("first", attempts=3))
        lease = self.kernel.claim_and_start("worker", execution_id="first")
        self.kernel.register_supervisor_obligation(lease)
        result = make_result(self.kernel, lease, status="failed", retryable=True)
        self.kernel.cancel("first", expected_revision=self.kernel.get("first").revision)
        with self.assertRaises(Exception):
            self.kernel._complete_sdk_result(lease, result, budget_envelope=None,
                                              supervisor_cleanup_confirmed=True)
        with self.kernel._transaction() as (db, _):
            self.assertIsNone(db.execute("SELECT resolution_json FROM kernel_supervisor_obligations WHERE execution_id=?", ("first",)).fetchone()[0])

    def test_unresolved_effect_does_not_release_supervisor_obligation(self):
        self.kernel.submit(make_command("first", attempts=3))
        lease = self.kernel.claim_and_start("worker", execution_id="first")
        self.kernel.register_supervisor_obligation(lease)
        self.kernel.prepare_effect(lease, effect_id="pending-effect", name="send", request={"item": 1})
        result = make_result(self.kernel, lease, status="failed", retryable=True)
        state = self.kernel._complete_sdk_result(lease, result, budget_envelope=None,
                                                 supervisor_cleanup_confirmed=True)
        self.assertEqual(state.state, "recovery_required")
        with self.kernel._transaction() as (db, _):
            self.assertIsNone(db.execute("SELECT resolution_json FROM kernel_supervisor_obligations WHERE execution_id=?", ("first",)).fetchone()[0])

    def test_retained_result_after_expiry_resolves_only_with_confirmed_cleanup(self):
        self.kernel.submit(make_command("first", attempts=3))
        lease = self.kernel.claim_and_start("worker", execution_id="first", lease_seconds=1)
        self.kernel.register_supervisor_obligation(lease)
        result = make_result(self.kernel, lease)
        self.now = 108.0
        self.assertEqual(self.kernel.reap(), [])
        settled = self.kernel._complete_sdk_result(lease, result, budget_envelope=None, settlement=True,
                                                    supervisor_cleanup_confirmed=True)
        self.assertEqual(settled.state, "succeeded")
        replay = self.kernel._complete_sdk_result(lease, result, budget_envelope=None, settlement=True,
                                                  supervisor_cleanup_confirmed=True)
        self.assertEqual(replay.state, "succeeded")

    def test_inspection_is_paged_and_survives_reopen(self):
        self.kernel.submit(make_command("first", attempts=3))
        first = self.kernel.claim_and_start("worker", execution_id="first")
        self.kernel.register_supervisor_obligation(first)
        result = make_result(self.kernel, first, status="failed", retryable=True)
        self.kernel.complete(first, result)
        decision = self.decision_for(first, outcome="failed")
        self.kernel.resolve_supervisor_obligation("host", expected_resolution=decision)
        second = self.kernel.claim_and_start("worker", execution_id="first")
        self.kernel.register_supervisor_obligation(second)
        with SQLiteKernel(self.path, now=lambda: self.now) as reopened:
            page = reopened.inspect_supervisor_obligations("first", limit=1)
            self.assertEqual(page["obligations"][0]["state"], "resolved")
            tail = reopened.inspect_supervisor_obligations("first", limit=1, after=page["next_after"])
            self.assertEqual(tail["obligations"][0]["state"], "unresolved")
            self.assertIsNone(tail["obligations"][0]["resolution"])
            self.assertIsNone(tail["next_after"])

    def test_reap_completes_all_eligible_batches_and_skips_blocked(self):
        blocked = set()
        for index in range(300):
            execution_id = f"execution-{index:03d}"
            self.kernel.submit(make_command(execution_id, attempts=3))
            lease = self.kernel.claim_and_start("worker", execution_id=execution_id, lease_seconds=1)
            if index % 10 == 0:
                blocked.add(execution_id)
                self.kernel.register_supervisor_obligation(lease)
        self.now = 108.0
        reaped = self.kernel.reap()
        self.assertEqual(len(reaped), 300 - len(blocked))
        self.assertTrue(all(item.state == "queued" for item in reaped))
        self.assertTrue(all(self.kernel.get(item).state == "running" for item in blocked))


class SupervisorSchemaUpgradeTests(unittest.TestCase):
    def test_explicit_copy_upgrade_preserves_v8_rows(self):
        from dispatcher_sdk.execution_kernel._sqlite_schema import KERNEL_SCHEMA_V8
        from dispatcher_sdk.maintenance import maintenance_lease
        from dispatcher_sdk.storage_migration import upgrade_storage
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite"
            target = Path(directory) / "target.sqlite"
            with contextlib.closing(sqlite3.connect(source)) as db, db:
                db.executescript(KERNEL_SCHEMA_V8)
                db.execute("UPDATE kernel_clock SET watermark=17")
                db.execute("INSERT INTO kernel_executions(execution_id,idempotency_key,registry_revision,command_json,state,attempt,redelivery_count,next_attempt_at,fence,revision,created_at,updated_at) VALUES('old','key','rev','{}','queued',0,0,1,0,1,1,1)")
                db.execute("INSERT INTO kernel_events VALUES(1,'old-event','old',1,'submitted',NULL,'queued','{}',1)")
                db.execute("UPDATE kernel_clock SET event_sequence=1")
            with maintenance_lease(source, "test", "upgrade") as lease:
                report = upgrade_storage(source, target, lease=lease)
            self.assertEqual((report["source_version"], report["target_version"]), (8, 12))
            with contextlib.closing(sqlite3.connect(source)) as db, db:
                self.assertEqual(db.execute("SELECT schema_version FROM kernel_schema_meta").fetchone()[0], 8)
                source_execution = db.execute("SELECT * FROM kernel_executions").fetchall()
                source_events = db.execute("SELECT * FROM kernel_events").fetchall()
            with contextlib.closing(sqlite3.connect(target)) as db, db:
                self.assertEqual(db.execute("SELECT * FROM kernel_executions").fetchall(), source_execution)
                self.assertEqual(db.execute("SELECT * FROM kernel_events").fetchall(), source_events)
            with SQLiteKernel(target) as kernel:
                with kernel._transaction() as (db, _):
                    self.assertIsNone(db.execute("SELECT execution_id FROM kernel_supervisor_obligations LIMIT 1").fetchone())
                    self.assertGreaterEqual(db.execute("SELECT watermark FROM kernel_clock").fetchone()[0], 17)


if __name__ == "__main__":
    unittest.main()
