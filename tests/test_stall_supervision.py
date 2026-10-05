"""Durable window and delivery races against real Kernel/sidecar SQLite."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from dispatcher_sdk.execution_kernel import CASConflictError, ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel.budget import ClockCheckpoint, sample_clock
from dispatcher_sdk.observability import ActivityRecorder, ObservationIdentity, ObservationJournal, ObservationOptions, StallPolicy
from dispatcher_sdk.observability.supervision import StallSupervisor
from tests._acceptance_evidence import retained_directory


class _Clock:
    def __init__(self):
        self.wall = 100.0
        self.elapsed = 100.0
        self.domain = "test-boot"

    def __call__(self):
        return self.wall

    def sample(self):
        return ClockCheckpoint(self.wall, self.elapsed, self.domain, "boot" if self.domain else "unknown")

    def advance(self, seconds):
        self.wall += seconds
        self.elapsed += seconds


def _notification_process(root, current, action, start=None):
    """Exercise independent evaluator/bridge transactions and abrupt ACK loss."""
    from dispatcher_sdk.orchestrator import Orchestrator
    clock = _Clock()
    clock.advance(current - 100)
    root = Path(root)
    with SQLiteKernel(root / "kernel.sqlite3", now=clock) as kernel:
        journal = ObservationJournal(root / "observations.sqlite3", kernel_path=kernel.db_path,
                                     source_id="host-store", clock=clock)
        orchestrator = Orchestrator(root / "application.sqlite3", kernel, clock=clock)

        def bridge(payload):
            orchestrator.enqueue_stall_notification(payload)
            if action == "crash_after_enqueue":
                os._exit(73)

        service = StallSupervisor(journal, kernel, bridge, clock=clock,
                                  clock_sample=clock.sample, delivery_lease_seconds=2)
        if start is not None:
            start.wait(10)
        if action == "evaluate":
            service.tick()
        else:
            service.deliver_pending()


class StallSupervisionTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-stall-supervision-')
        self.clock = _Clock()
        self.kernel = SQLiteKernel(self.root / "kernel.sqlite3", now=self.clock)
        self.addCleanup(self.kernel.close)
        command = ExecutionCommandV2(execution_id="execution", idempotency_key="request", registry_revision="test",
                                     correlation_id="correlation", causation_id=None, handler_id="handler", handler_contract_version=1,
                                     retry_policy=RetryPolicy(), timeout_seconds=300, payload={})
        self.kernel.submit(command)
        self.lease = self.kernel.claim_and_start("worker", lease_seconds=1000, registry_revision="test")
        self.identity = ObservationIdentity("execution", self.lease.attempt, self.lease.fence)
        self.journal = ObservationJournal(self.root / "observations.sqlite3", kernel_path=self.kernel.db_path,
                                           source_id="host-store", options=ObservationOptions(write_timeout=.2), clock=self.clock)
        self.journal.bind_current(self.identity)
        self.recorder = ActivityRecorder(self.journal, self.identity, clock=self.clock, monotonic=lambda: self.clock.elapsed)
        self.recorder.enable_stream("stdout")
        self.recorder.phase("handler_entered")
        self.flush_receipts = [self.recorder.flush()]
        self.policy = StallPolicy("policy", sample_interval=2, consecutive_windows=3)
        self.service = self.open_service()
        self.addCleanup(self.retain_diagnostics)

    def retain_diagnostics(self):
        record = {'test': self.id(), 'clock': vars(self.clock), 'flush_receipts': self.flush_receipts,
                  'local_activity': self.recorder.snapshot()}
        try:
            with self.journal._read_connection(1) as (connection, _):
                for table in ('obs_policies', 'obs_windows', 'obs_outbox', 'obs_sources'):
                    record[table] = [dict(row) for row in connection.execute(f'SELECT * FROM {table}')]
        except Exception as error:
            record['diagnostic_error'] = {'type': type(error).__name__, 'message': str(error)}
        path = self.root / 'evidence.json'
        path.write_text(json.dumps(record, default=str, indent=2), encoding='utf-8')
        print('stall_supervision_evidence=' + str(path), flush=True)

    def open_service(self, bridge=None, **kwargs):
        return StallSupervisor(self.journal, self.kernel, bridge, clock=self.clock, clock_sample=self.clock.sample,
                               delivery_lease_seconds=2, **kwargs)

    def watch(self, policy=None):
        return self.service.watch(self.identity, policy or self.policy, target={"run_id": "host-run", "task_id": "task"})

    def advance(self, seconds=2, *, flush=True):
        self.clock.advance(seconds)
        if flush:
            self.flush_receipts.append(self.recorder.flush())
        return self.service.tick()

    def policy_row(self):
        with self.journal._read_connection(3) as (connection, _):
            return dict(connection.execute("SELECT * FROM obs_policies WHERE state='active'").fetchone())

    def make_notice(self):
        self.watch()
        self.service.tick()
        for _ in range(3):
            self.advance()
        return self.service.outbox()[0]

    def test_real_process_evaluators_and_crash_after_enqueue_replay_one_identity(self):
        from dispatcher_sdk.orchestrator import Orchestrator
        orchestrator = Orchestrator(self.root / "application.sqlite3", self.kernel, clock=self.clock)
        orchestrator.create_run("host-run", command_id="create")
        self.watch()
        self.service.tick()
        self.advance()
        self.advance()
        self.clock.advance(2)
        self.recorder.flush()
        spawn = multiprocessing.get_context("spawn")
        start = spawn.Event()
        processes = [spawn.Process(target=_notification_process,
                                  args=(str(self.root), 106, "evaluate", start)) for _ in range(2)]
        for process in processes:
            process.start()
        start.set()
        for process in processes:
            process.join(15)
            try:
                self.assertFalse(process.is_alive())
                self.assertEqual(process.exitcode, 0)
            finally:
                if process.is_alive():
                    process.kill()
                    process.join(5)
                process.close()
        notices = self.service.outbox()
        self.assertEqual(len(notices), 1)
        notification_id = notices[0]["notification_id"]
        self.assertEqual(len(self.service.windows("execution")["windows"]), 3)
        for current, action, expected in ((106, "crash_after_enqueue", 73), (109, "deliver", 0)):
            process = spawn.Process(target=_notification_process, args=(str(self.root), current, action))
            process.start()
            process.join(15)
            try:
                self.assertFalse(process.is_alive())
                self.assertEqual(process.exitcode, expected)
            finally:
                if process.is_alive():
                    process.kill()
                    process.join(5)
                process.close()
        notice = self.service.outbox()[0]
        self.assertEqual(notice["notification_id"], notification_id)
        self.assertEqual(notice["state"], "bridged")
        self.assertEqual(notice["attempts"], 2)
        queued = orchestrator.list_notifications()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["notification_id"], notification_id)

    def test_repeated_real_bridge_crashes_exhaust_and_retry_same_notification(self):
        from dispatcher_sdk.orchestrator import Orchestrator
        orchestrator = Orchestrator(self.root / "application.sqlite3", self.kernel, clock=self.clock)
        orchestrator.create_run("host-run", command_id="create")
        self.policy = StallPolicy("policy", sample_interval=2, consecutive_windows=3, max_deliveries=2)
        notice = self.make_notice()
        notification_id = notice["notification_id"]
        spawn = multiprocessing.get_context("spawn")

        def invoke(current, action, expected):
            process = spawn.Process(target=_notification_process, args=(str(self.root), current, action))
            process.start()
            process.join(15)
            try:
                self.assertFalse(process.is_alive())
                self.assertEqual(process.exitcode, expected)
            finally:
                if process.is_alive():
                    process.kill()
                    process.join(5)
                process.close()

        for current in (106, 109):
            invoke(current, "crash_after_enqueue", 73)
        invoke(112, "deliver", 0)
        dead = self.service.outbox()[0]
        self.assertEqual((dead["state"], dead["attempts"]), ("dead", 2))
        self.assertEqual(dead["notification_id"], notification_id)
        self.clock.advance(6)
        self.service.retry_dead(notification_id, expected_revision=dead["revision"])
        invoke(112, "deliver", 0)
        accepted = self.service.outbox()[0]
        self.assertEqual((accepted["state"], accepted["attempts"]), ("bridged", 1))
        self.assertEqual(accepted["notification_id"], notification_id)
        queued = orchestrator.list_notifications()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["notification_id"], notification_id)

    def test_disabled_until_explicit_watch_and_three_complete_windows(self):
        self.service.tick()
        self.assertEqual(self.service.outbox(), ())
        self.watch()
        self.service.tick()
        for _ in range(2):
            self.recorder.report_bytes("stdout", b"log")
            self.recorder.heartbeat()
            self.advance()
        self.assertEqual(self.service.outbox(), ())
        self.advance()
        outbox = self.service.outbox()
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox[0]["state"], "pending")
        self.assertEqual([window["state"] for window in self.service.windows("execution")["windows"]], ["stalled"] * 3)

    def test_queued_subscription_survives_restart_and_binds_actual_handler_attempt(self):
        command = ExecutionCommandV2(execution_id="queued", idempotency_key="queued-request", registry_revision="test",
                                     correlation_id="correlation", causation_id=None, handler_id="handler", handler_contract_version=1,
                                     retry_policy=RetryPolicy(), timeout_seconds=300, payload={})
        self.kernel.submit(command)
        queued = ObservationIdentity("queued", 0, 0, run_id="run", task_id="task", generation=0)
        target = {"run_id": "run", "task_id": "task", "generation": 0}
        receipt = self.service.watch(queued, self.policy, target=target)
        self.assertEqual(receipt["state"], "pending_execution")
        restarted = self.open_service()
        restarted.tick()
        self.assertEqual(restarted.outbox(), ())
        lease = self.kernel.claim_and_start("queued-worker", lease_seconds=1000, registry_revision="test", execution_id="queued")
        actual = ObservationIdentity("queued", lease.attempt, lease.fence, run_id="run", task_id="task")
        self.journal.bind_current(actual)
        recorder = ActivityRecorder(self.journal, actual, clock=self.clock)
        restarted.tick()
        self.assertEqual(restarted._watch_state("queued"), "pending_execution")
        self.assertEqual(restarted.outbox(), ())
        prepared = self.kernel._prepare_handler_entry(lease)
        restarted.tick()
        self.assertEqual(restarted._watch_state("queued"), "pending_execution")
        self.assertEqual(restarted.outbox(), ())
        entered = prepared.enter_handler(command.timeout_seconds, origin_id="execution:queued",
                                         sample=sample_clock(wall_time=self.clock()))
        self.kernel.confirm_handler_entry(lease, entered)
        recorder.phase("handler_entered")
        recorder.flush()
        restarted.tick()
        with self.journal._read_connection(3) as (connection, _):
            row = connection.execute("SELECT * FROM obs_policies WHERE execution_id='queued'").fetchone()
            self.assertEqual((row["attempt"], row["fence"]), (lease.attempt, lease.fence))
            self.assertEqual(row["state"], "active")
        self.assertTrue(restarted.watch(queued, self.policy, target=target)["replayed"])

    def test_terminal_before_entry_closes_queued_subscription_without_stall(self):
        command = ExecutionCommandV2(execution_id="queued", idempotency_key="queued-request", registry_revision="test",
                                     correlation_id="correlation", causation_id=None, handler_id="handler", handler_contract_version=1,
                                     retry_policy=RetryPolicy(), timeout_seconds=300, payload={})
        self.kernel.submit(command)
        self.service.watch(ObservationIdentity("queued", 0, 0), self.policy, target={"task_id": "task"})
        self.kernel.cancel("queued")
        self.service.tick()
        self.assertEqual(self.service._watch_state("queued"), "closed")
        self.assertEqual(self.service.outbox(), ())

    def test_arbitrary_stale_identity_cannot_register_or_replay_running_policy(self):
        from dispatcher_sdk.observability.contracts import ObservationError
        target = {"run_id": "host-run", "task_id": "task"}
        for identity in (ObservationIdentity("execution", 9, 9), ObservationIdentity("execution", 0, 0)):
            with self.assertRaises(ObservationError):
                self.service.watch(identity, self.policy, target=target)
        self.watch()
        with self.assertRaises(ObservationError):
            self.service.watch(ObservationIdentity("execution", 0, 0), self.policy, target=target)

    def test_unknown_gap_breaks_streak_without_erasing_history(self):
        self.watch()
        self.service.tick()
        self.advance()
        self.assertEqual(self.policy_row()["consecutive"], 1)
        self.advance(10, flush=False)
        self.assertEqual(self.policy_row()["consecutive"], 0)
        self.assertEqual(self.service.outbox(), ())
        self.recorder.flush()
        self.service.tick()
        self.advance()
        self.assertEqual(self.policy_row()["consecutive"], 1)
        states = [window["state"] for window in self.service.windows("execution")["windows"]]
        self.assertEqual(states, ["stalled", "unknown", "stalled"])

    def test_crashed_scope_replacement_recovers_fresh_windows_same_attempt(self):
        self.recorder.close()
        self.recorder = ActivityRecorder(self.journal, self.identity, source_id="before-crash",
                                        source_scope="handler", clock=self.clock,
                                        monotonic=lambda: self.clock.elapsed)
        self.recorder.enable_stream("stdout")
        self.recorder.phase("handler_entered")
        self.recorder.flush()
        self.watch(StallPolicy("policy", sample_interval=2, consecutive_windows=1))
        self.service.tick()
        self.clock.advance(10)
        self.service.tick()
        self.assertEqual(self.service.outbox(), ())
        # The crashed recorder never closes. Explicitly replacing its scope
        # preserves history and starts a fresh collection continuity.
        self.recorder = ActivityRecorder(self.journal, self.identity, source_id="after-crash",
                                        source_scope="handler", clock=self.clock,
                                        monotonic=lambda: self.clock.elapsed)
        self.recorder.enable_stream("stdout")
        self.recorder.flush()
        self.service = self.open_service()
        self.service.tick()
        self.assertEqual(self.service.outbox(), ())
        self.advance()
        self.assertEqual(len(self.service.outbox()), 1)
        report = self.journal.inspect("execution")
        self.assertTrue(report["complete"])
        self.assertTrue(any(row["source_id"] == "before-crash" for row in report["retired_sources"]))
        states = [row["state"] for row in self.service.windows("execution")["windows"]]
        self.assertIn("unknown", states)
        self.assertEqual(states[-1], "stalled")

    def test_old_but_fresh_persisted_endpoint_does_not_complete_later_window(self):
        self.watch(StallPolicy("policy", sample_interval=2, consecutive_windows=1))
        self.service.tick()
        self.clock.advance(2)
        self.service.tick()
        self.assertEqual(self.service.outbox(), ())
        self.assertEqual(self.policy_row()["consecutive"], 0)
        self.recorder.flush()
        self.service.tick()
        self.assertEqual(len(self.service.outbox()), 1)

    def test_collection_gap_breaks_window_but_history_does_not_prevent_recovery(self):
        self.recorder.close()
        self.recorder = ActivityRecorder(self.journal, self.identity, source_id="before-gap",
                                        source_scope="handler", clock=self.clock,
                                        monotonic=lambda: self.clock.elapsed)
        self.recorder.enable_stream("stdout")
        self.flush_receipts.append(self.recorder.flush())
        self.watch(StallPolicy("policy", sample_interval=2, consecutive_windows=1))
        self.service.tick()
        self.recorder.phase("phase", details={"too_large": "x" * 10000})
        self.advance()
        self.assertEqual(self.service.outbox(), ())
        self.assertEqual(self.policy_row()["consecutive"], 0)
        self.service.tick()
        self.advance()
        self.assertEqual(self.service.outbox(), ())
        # A successful flush cannot restore missing wait coverage. A new
        # declared collector starts fresh continuity and preserves the gap
        # as retired history, rather than silently clearing that history.
        self.recorder.close()
        self.recorder = ActivityRecorder(self.journal, self.identity, source_id="after-gap",
                                        source_scope="handler", clock=self.clock,
                                        monotonic=lambda: self.clock.elapsed)
        self.recorder.enable_stream("stdout")
        self.flush_receipts.append(self.recorder.flush())
        self.service.tick()
        self.advance()
        self.assertEqual(len(self.service.outbox()), 1)
        report = self.journal.inspect("execution")
        self.assertTrue(any(source["source_id"] == "before-gap" for source in report["retired_sources"]))

    def test_restart_does_not_retroactively_count_shutdown_windows(self):
        self.watch()
        self.service.tick()
        self.advance()
        self.service = self.open_service()
        self.clock.advance(20)
        self.recorder.flush()
        self.service.tick()
        self.assertEqual(self.policy_row()["consecutive"], 0)
        self.assertEqual(self.service.outbox(), ())
        self.assertIn("unknown", [window["state"] for window in self.service.windows("execution")["windows"]])

    def test_wait_exemption_suspends_and_unknown_metrics_cannot_stall(self):
        policy = StallPolicy("policy", sample_interval=2, consecutive_windows=3, wait_exemptions=("service_response",))
        self.watch(policy)
        self.service.tick()
        self.advance()
        self.journal.record_wait(self.identity, "wait", details={"reason": "service_response"})
        self.advance()
        self.assertEqual(self.policy_row()["consecutive"], 0)
        self.assertEqual(self.service.windows("execution")["windows"][-1]["state"], "exempt")
        self.journal.end_wait(self.identity, "wait")
        self.advance()
        self.watch(StallPolicy("new", metrics=("model_events",), sample_interval=2, consecutive_windows=1))
        self.service.tick()
        self.advance()
        self.assertEqual(self.service.outbox(), ())

    def test_all_configured_metrics_must_be_stagnant(self):
        self.watch(StallPolicy("policy", metrics=("progress", "stdout_bytes"), sample_interval=2, consecutive_windows=1))
        self.service.tick()
        self.recorder.report_bytes("stdout", b"forward")
        self.advance()
        self.assertEqual(self.service.outbox(), ())
        self.advance()
        self.assertEqual(len(self.service.outbox()), 1)

    def test_selected_output_ends_old_episode_and_later_stall_has_new_identity(self):
        self.watch(StallPolicy("policy", metrics=("stdout_bytes",), sample_interval=2, consecutive_windows=1))
        self.service.tick()
        self.advance()
        old = self.service.outbox()[0]
        self.recorder.report_bytes("stdout", b"fresh")
        self.advance()
        with self.assertRaises(CASConflictError):
            self.kernel.cancel("execution", expected_supervision=old["payload"]["disposition"])
        self.advance()
        outbox = self.service.outbox()
        self.assertEqual([notice["state"] for notice in outbox], ["superseded", "pending"])
        self.assertNotEqual(outbox[0]["notification_id"], outbox[1]["notification_id"])

    def test_replayed_progress_does_not_reset_episode_new_progress_invalidates_token(self):
        notice = self.make_notice()
        token = notice["payload"]["disposition"]
        self.kernel.confirm_progress(self.lease, "milestone")
        with self.assertRaises(CASConflictError):
            self.kernel.cancel("execution", expected_supervision=token)
        self.advance()
        self.assertEqual(self.service.outbox()[0]["state"], "superseded")
        self.assertEqual(self.policy_row()["consecutive"], 0)
        self.kernel.confirm_progress(self.lease, "milestone")
        self.advance()
        self.assertEqual(self.policy_row()["consecutive"], 1)

    def test_policy_replacement_invalidates_previously_delivered_disposition(self):
        old = self.make_notice()
        self.watch(StallPolicy("policy", version=2, sample_interval=2, consecutive_windows=1))
        with self.assertRaises(CASConflictError):
            self.kernel.cancel("execution", expected_supervision=old["payload"]["disposition"])
        self.service.tick()
        self.advance()
        self.assertEqual([row["state"] for row in self.service.outbox()], ["superseded", "pending"])

    def test_competing_evaluators_create_one_logical_notice(self):
        self.watch(StallPolicy("policy", sample_interval=2, consecutive_windows=1))
        self.service.tick()
        self.clock.advance(2)
        self.recorder.flush()
        other = self.open_service()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda service: service.tick(), (self.service, other)))
        self.assertEqual(len(self.service.outbox()), 1)
        self.assertEqual(len(self.service.windows("execution")["windows"]), 1)

    def test_concurrent_identical_watch_replays_one_durable_subscription(self):
        barrier = threading.Barrier(2)
        def subscribe(service):
            barrier.wait()
            return service.watch(self.identity, self.policy, target={"task_id": "task"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(subscribe, (self.service, self.open_service())))
        self.assertTrue(any(receipt["replayed"] for receipt in receipts))
        with self.journal._read_connection(3) as (connection, _):
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM obs_policies").fetchone()[0], 1)

    def test_bridge_retry_preserves_identity_and_dead_is_explicit(self):
        identities = []
        def bridge(payload):
            identities.append(payload["notification_id"])
            raise OSError("offline")
        self.service = self.open_service(bridge)
        self.policy = StallPolicy("policy", sample_interval=2, consecutive_windows=1, max_deliveries=2)
        self.make_notice()
        notice = self.service.outbox()[0]
        self.assertEqual(self.service.deliver_pending()["state"], "pending")
        self.clock.advance(2)
        self.assertEqual(self.service.deliver_pending()["state"], "dead")
        dead = self.service.outbox()[0]
        self.assertEqual(identities, [notice["notification_id"]] * 2)
        self.service.retry_dead(dead["notification_id"], expected_revision=dead["revision"])
        self.service.notification_bridge = lambda payload: identities.append(payload["notification_id"])
        self.assertEqual(self.service.deliver_pending()["state"], "bridged")
        self.assertEqual(identities[-1], notice["notification_id"])

    def test_crashed_delivery_lease_replays_same_identity(self):
        notice = self.make_notice()
        with self.journal._transaction() as (connection, now):
            connection.execute("UPDATE obs_outbox SET state='delivering',attempts=1,lease_id='old',owner='crashed',expires_at=?",
                               (now + 1,))
        self.clock.advance(2)
        received = []
        restarted = self.open_service(lambda payload: received.append(payload["notification_id"]))
        self.assertEqual(restarted.deliver_pending()["state"], "bridged")
        self.assertEqual(received, [notice["notification_id"]])

    def test_blocked_bridge_does_not_block_tick_and_close_reports_pending(self):
        entered, release = threading.Event(), threading.Event()
        def bridge(payload):
            entered.set()
            release.wait(3)
        self.service = self.open_service(bridge)
        self.make_notice()
        self.service.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.service.deliver_pending()["reason"], "delivery_capacity_occupied")
            before = self.service.health()["ticks"]
            result = self.service.tick()
            self.assertIn(result["state"], ("evaluated", "pending"))
            deadline = time.monotonic() + 1
            while self.service.health()["ticks"] <= before and time.monotonic() < deadline:
                release.wait(.01)
            self.assertGreater(self.service.health()["ticks"], before)
            self.assertEqual(self.service.close(timeout=.03)["state"], "pending")
        finally:
            release.set()
            self.service.close(timeout=1)

    def test_wall_rollback_and_clock_domain_change_do_not_count_stall(self):
        self.watch()
        self.service.tick()
        self.advance()
        self.clock.wall -= 1
        self.clock.elapsed += 1
        self.recorder.flush()
        self.service.tick()
        self.assertEqual(self.policy_row()["consecutive"], 0)
        self.clock.domain = "new-boot"
        self.advance()
        self.assertEqual(self.policy_row()["consecutive"], 0)


if __name__ == "__main__":
    unittest.main()
