"""Reserved supervision through actual notice, Kernel and process ownership."""
from __future__ import annotations

import json
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import sys
import time
import threading
import unittest
from unittest.mock import patch

from dispatcher_sdk import DeploymentMismatchError, Dispatcher, ManagedStallOptions
from dispatcher_sdk.execution_kernel import HandlerExecutionError
from dispatcher_sdk.observability import ObservationJournal, ObservationOptions, StallPolicy
from tests._acceptance_evidence import retained_directory


def _business(payload, context):
    Path(payload["entered"]).write_text(str(os.getpid()), encoding="utf-8")
    while not Path(payload["release"]).exists():
        time.sleep(.02)
    return "released"


def _supervise(notice, context):
    root = Path(notice["target"]["agent_root"])
    evidence = {"pid": os.getpid(), "notice_id": notice["notification_id"],
                "execution_id": context.lease.execution_id,
                "budget": context.budget.to_dict()}
    if os.name == "posix":
        import resource
        evidence["address_space_limit"] = list(resource.getrlimit(resource.RLIMIT_AS))
    if notice["target"].get("memory_probe"):
        requested = notice["target"]["memory_probe"]
        evidence["allocation"] = {"requested_bytes": requested, "allocated": False, "error": None}
        try:
            allocation = bytearray(requested)
        except MemoryError as error:
            evidence["allocation"]["error"] = type(error).__name__
        else:
            evidence["allocation"]["allocated"] = True
            del allocation
    try:
        context.children.run("outside", {}, request_id="forbidden-child")
    except Exception as error:
        evidence["child_error"] = {"type": type(error).__name__, "code": getattr(error, "code", None),
                                   "message": str(error)}
    with (root / "invocations.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(evidence) + "\n")
    if notice["target"].get("hold"):
        while not (root / "agent_release").exists():
            time.sleep(.02)
    if notice["target"].get("fail"):
        raise HandlerExecutionError("supervisor_original_failure", "original handler failure")
    return evidence


_business.__execution_kernel_revision__ = "managed-supervisor-business-v1"
_supervise.__execution_kernel_revision__ = "managed-supervisor-agent-v1"


def _changed_supervise(notice, context):
    return "changed"


_changed_supervise.__execution_kernel_revision__ = "managed-supervisor-agent-v2"


class ManagedStallSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-managed-stalls-")
        (self.root / "fixture.json").write_text(json.dumps({
            "test": self.id(), "interpreter": sys.executable, "version": sys.version,
            "import": __import__("dispatcher_sdk").__file__,
            "business_timeout_seconds": 20, "managed_budget_seconds": 10,
            "managed_timeout_seconds": 5, "original_wait_seconds": 8,
        }, indent=2), encoding="utf-8")
        self.apps = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for index, app in enumerate(self.apps):
            if app._state in {"open", "running"}:
                try:
                    records = app.inbox.list_messages(source_id="dispatcher.stalls.v1")
                    reports = [app.stall_supervisor_status(row["notification_id"]) for row in records]
                    (self.root / ("cleanup-before-"+str(index)+".json")).write_text(
                        json.dumps(reports, default=str, indent=2), encoding="utf-8")
                except Exception as error:
                    (self.root / "cleanup-error.txt").write_text(repr(error), encoding="utf-8")
        (self.root / "release").touch()
        from dispatcher_sdk.execution_kernel.runtime import _ObservationCleanupPendingError
        from dispatcher_sdk.observability.managed_supervisor import _AdmissionError
        import traceback
        for index, app in enumerate(reversed(self.apps)):
            deadline = time.monotonic() + 10
            attempt = 0
            last_error = None
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    assert last_error is not None
                    raise last_error
                try:
                    app.close(timeout=remaining)
                    break
                except BaseException as error:
                    # Preserve each original failure immediately, including
                    # a supported pending-cleanup refusal that later resolves.
                    (self.root / f"cleanup-close-error-{index}-{attempt}.txt").write_text(
                        traceback.format_exc(), encoding="utf-8")
                    attempt += 1
                    retryable = isinstance(error, _ObservationCleanupPendingError) or (
                        isinstance(error, _AdmissionError) and error.code in {
                            "supervisor_checkpoint_pending", "supervisor_cleanup_unknown"})
                    if not retryable or time.monotonic() >= deadline:
                        raise
                    # close explicitly supports retrying retained cleanup.
                    # Every attempt consumes this fixture's original window.
                    last_error = error
                    time.sleep(min(.02, max(0., deadline-time.monotonic())))

    def open(self, *, business_workers=1, observation_options=None, **options):
        config = ManagedStallOptions(memory_limit_bytes=512*1024*1024,
            budget_seconds=10, timeout_seconds=5, **options)
        app = Dispatcher(self.root / "application.sqlite3", {"business": _business},
            worker_count=business_workers, observation_options=observation_options or ObservationOptions(flush_interval=.2),
            callback_retry_delay=.05, stall_handler=_supervise, stall_options=config)
        self.apps.append(app)
        return app

    def wait(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(.02)
        self.fail("original wait exhausted; last=" + repr(last))

    def notice(self, app, *, fail=False, hold=False):
        task = app.submit("business", {"entered": str(self.root / "entered"),
            "release": str(self.root / "release")}, request_id="business", timeout_seconds=20)
        # Register the actual queued policy before worker startup/initial
        # recorder writes; the sampler must promote it at confirmed entry.
        app.orchestrator.flush()
        snapshot = task.snapshot
        app.runtime.watch_stall(snapshot["command"]["execution_id"],
            StallPolicy("managed", sample_interval=.1, consecutive_windows=1, max_deliveries=2),
            target={"run_id": snapshot["command"]["correlation_id"], "task_id": "task",
                    "agent_root": str(self.root), "fail": fail, "hold": hold})
        app.start()
        self.wait(lambda: (self.root / "entered").exists())
        notices = self.wait(lambda: app.inbox.list_messages(source_id="dispatcher.stalls.v1"))
        return task, notices[0]["notification_id"]

    def retain(self, app, notice_id):
        report = app.stall_supervisor_status(notice_id)
        report["import"] = __import__("dispatcher_sdk").__file__
        report["invocations"] = self.invocations()
        (self.root / "evidence.json").write_text(json.dumps(report, default=str, indent=2), encoding="utf-8")
        print("managed_stall_evidence=" + str(self.root / "evidence.json"), flush=True)
        return report

    def invocations(self):
        path = self.root / "invocations.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def test_reserved_process_runs_while_business_slot_busy_with_real_memory_limit_and_child_denial(self):
        app = self.open()
        task, notice_id = self.notice(app)
        self.wait(lambda: app.inbox.get("dispatcher.stalls.v1", notice_id)["state"] == "consumed")
        report = self.retain(app, notice_id)
        self.assertEqual(task.state, "running")
        self.assertEqual(len(report["invocations"]), 1)
        actual = report["invocations"][0]
        self.assertNotEqual(actual["pid"], int((self.root / "entered").read_text()))
        self.assertEqual(actual["execution_id"], report["execution_id"])
        self.assertIn("execution:"+task.snapshot["command"]["execution_id"],
                      {item["origin_id"] for item in actual["budget"]["constraints"]})
        self.assertEqual(report["execution"]["result"]["status"], "succeeded")
        self.assertEqual(actual["child_error"]["code"], "child_service_unavailable")
        self.assertEqual(report["peak_active"], 1)
        self.assertTrue(report["resource_capability"]["supported"])
        if os.name == "posix":
            self.assertEqual(actual["address_space_limit"], [512*1024*1024]*2)
        self.assertLessEqual(report["run_control"]["deadline_at"],
                             report["receipt"]["created_at"] + 10)
        (self.root / "release").touch()
        self.assertEqual(task.wait(timeout=8)["value"], "released")

    def test_failed_notice_replay_keeps_original_result_and_one_business_invocation(self):
        app = self.open()
        _, notice_id = self.notice(app, fail=True)
        self.wait(lambda: app.inbox.get("dispatcher.stalls.v1", notice_id)["state"] == "dead")
        report = self.retain(app, notice_id)
        self.assertEqual(report["receipt"]["attempts"], 2)
        self.assertEqual(len(report["invocations"]), 1)
        self.assertEqual(report["execution"]["result"]["error"]["code"], "supervisor_original_failure")
        self.assertEqual(report["execution"]["attempt"], 1)

    def test_successful_result_survives_ack_failure_and_restart_without_business_replay(self):
        app = self.open()
        supervisor = app._managed_stall_supervisor
        # Fault only ACK persistence after the actual process/Kernel result;
        # permanent failure is not retried as transient writer contention.
        with patch.object(supervisor.inbox, "consume", side_effect=sqlite3.OperationalError("disk I/O error")):
            _, notice_id = self.notice(app)
            self.wait(lambda: app.inbox.get("dispatcher.stalls.v1", notice_id)["state"] == "dead")
            before = self.retain(app, notice_id)
            (self.root / "release").touch()
            app.close(timeout=10)
        reopened = self.open()
        receipt = reopened.inbox.get("dispatcher.stalls.v1", notice_id)
        reopened.inbox.retry_dead("dispatcher.stalls.v1", notice_id, expected_revision=receipt["revision"])
        reopened.start()
        self.wait(lambda: reopened.inbox.get("dispatcher.stalls.v1", notice_id)["state"] == "consumed")
        after = self.retain(reopened, notice_id)
        self.assertEqual(after["execution"], before["execution"])
        self.assertEqual(after["run_control"]["deadline_at"], before["run_control"]["deadline_at"])
        self.assertEqual(len(after["invocations"]), 1)

    def test_memory_shortage_is_visible_without_claim_or_budget_reset(self):
        app = self.open(memory_budget_bytes=1)
        _, notice_id = self.notice(app)
        self.wait(lambda: app.stall_supervisor_status()["admission_state"] == "memory_shortage")
        report = self.retain(app, notice_id)
        self.assertEqual(report["receipt"]["state"], "pending")
        self.assertEqual(report["receipt"]["attempts"], 0)
        self.assertIsNone(report["execution"])
        self.assertEqual(report["active"], 0)
        self.assertEqual(report["invocations"], [])

    def test_actual_process_timeout_and_receipt_retry_keep_original_deadline_and_one_invocation(self):
        from tests._storage_evidence import StorageEvidence
        app = self.open()
        storage = StorageEvidence(self.root, self)
        storage.start(include_kernel=True)
        storage.runtimes.extend((app.runtime, app._managed_stall_supervisor.runtime))
        self.addCleanup(storage.stop)
        self.addCleanup(storage.save)
        checkpoint = {"original_wait_seconds": 8, "inbox_operation_seconds": .1,
                      "managed_timeout_seconds": 5, "native_worker_SQL_trace": "unavailable"}
        try:
            _, notice_id = self.notice(app, hold=True)
            checkpoint["notice_id"] = notice_id
            self.wait(lambda: bool(self.invocations()))
            before = app.stall_supervisor_status(notice_id)
            checkpoint["before"] = before
            self.wait(lambda: app.inbox.get("dispatcher.stalls.v1", notice_id)["state"] == "dead")
            after = self.retain(app, notice_id)
            checkpoint["after"] = after
            self.assertEqual(after["execution"]["result"]["status"], "timed_out")
            self.assertEqual(after["run_control"]["deadline_at"], before["run_control"]["deadline_at"])
            self.assertEqual(after["execution"]["command"]["timeout_seconds"], 5)
            self.assertEqual(after["execution"]["attempt"], 1)
            self.assertEqual(len(after["invocations"]), 1)
        finally:
            checkpoint["invocations"] = self.invocations()
            storage.save(phase="original-timeout-terminal", checkpoint=checkpoint)

    def test_managed_inbox_admits_original_writer_window_without_replaying_claim_body(self):
        from dispatcher_sdk.observability.managed_supervisor import _SupervisorInbox
        from dispatcher_sdk.orchestrator.inbox import NotificationInbox
        inbox = _SupervisorInbox(self.root / "inbox.sqlite3", durability="full", timeout=.1)
        source = "dispatcher.stalls.v1"
        inbox.accept(source, {"notification_id": "released-writer"})
        events = deque(maxlen=512)
        evidence = {"operation_seconds": .1, "release_delay_seconds": .04,
                    "body_replay": False, "phases": {}}
        begin_seen = threading.Event()
        phase = "baseline"
        original_connect = inbox._connect

        def connect():
            connection = original_connect()
            def trace(sql):
                events.append({"phase": phase, "sql": sql, "at": time.monotonic()})
                if sql == "BEGIN IMMEDIATE":
                    begin_seen.set()
            connection.set_trace_callback(trace)
            return connection

        writer = sqlite3.connect(inbox.db_path, timeout=.1, isolation_level=None,
                                 check_same_thread=False)
        release_thread = None
        try:
            with patch.object(inbox, "_connect", connect):
                writer.execute("BEGIN IMMEDIATE")
                started = time.monotonic()
                with patch.object(inbox, "_transaction", lambda: NotificationInbox._transaction(inbox)):
                    with self.assertRaises(sqlite3.OperationalError) as baseline:
                        inbox.claim("owner", source_id=source)
                evidence["phases"][phase] = {"elapsed": time.monotonic()-started,
                    "error": repr(baseline.exception), "receipt": inbox.get(source, "released-writer")}
                self.assertEqual(evidence["phases"][phase]["receipt"]["attempts"], 0)
                phase = "released_within_original_window"
                begin_seen.clear()
                def release_writer():
                    if begin_seen.wait(1):
                        time.sleep(.04)
                        writer.rollback()
                release_thread = threading.Thread(target=release_writer)
                release_thread.start()
                started = time.monotonic()
                lease = inbox.claim("owner", source_id=source)
                evidence["phases"][phase] = {"elapsed": time.monotonic()-started,
                    "receipt": inbox.get(source, "released-writer")}
                release_thread.join(1)
                self.assertFalse(release_thread.is_alive())
                self.assertEqual(lease.attempt, 1)
                self.assertEqual(lease.fence, 1)
                self.assertEqual(evidence["phases"][phase]["receipt"]["attempts"], 1)
                body = [event for event in events if event["phase"] == phase and
                        "attempts=attempts+1" in event["sql"]]
                self.assertEqual(len(body), 1)
                self.assertGreater(len([event for event in events if event["phase"] == phase
                    and event["sql"] == "BEGIN IMMEDIATE"]), 1)
                inbox.accept(source, {"notification_id": "held-through-cutoff"})
                before = inbox.get(source, "held-through-cutoff")
                writer.execute("BEGIN IMMEDIATE")
                phase = "held_through_original_window"
                started = time.monotonic()
                with self.assertRaises(sqlite3.OperationalError) as expired:
                    inbox.claim("owner", source_id=source)
                elapsed = time.monotonic()-started
                after = inbox.get(source, "held-through-cutoff")
                evidence["phases"][phase] = {"elapsed": elapsed,
                    "error": repr(expired.exception), "before": before, "after": after}
                self.assertEqual(after, before)
                self.assertGreaterEqual(elapsed, .09)
                self.assertLess(elapsed, .2)
                self.assertFalse(any(event["phase"] == phase and "attempts=attempts+1"
                                     in event["sql"] for event in events))
        finally:
            if release_thread is not None:
                release_thread.join(1)
            writer.rollback()
            writer.close()
            evidence["events"] = list(events)
            (self.root / "managed-inbox-original-admission.json").write_text(
                json.dumps(evidence, indent=2), encoding="utf-8")

    def test_reserved_capacity_shortage_leaves_second_actual_episode_pending(self):
        app = self.open(business_workers=2)
        for name in ("first", "second"):
            task = app.submit("business", {"entered": str(self.root / (name+"-entered")),
                "release": str(self.root / "release")}, request_id=name, timeout_seconds=20)
            app.orchestrator.flush()
            snapshot = task.snapshot
            app.runtime.watch_stall(snapshot["command"]["execution_id"],
                StallPolicy("managed-"+name, sample_interval=.1, consecutive_windows=1),
                target={"run_id": snapshot["command"]["correlation_id"], "task_id": "task",
                        "agent_root": str(self.root), "hold": True})
        app.start()
        records = self.wait(lambda: rows if len(rows := app.inbox.list_messages(
            source_id="dispatcher.stalls.v1")) == 2 else None)
        self.wait(lambda: bool(self.invocations()))
        first = self.invocations()[0]["notice_id"]
        second = next(row for row in records if row["notification_id"] != first)
        report = self.retain(app, second["notification_id"])
        self.assertEqual(report["admission_state"], "capacity_shortage")
        self.assertEqual(report["receipt"]["state"], "pending")
        self.assertEqual(report["receipt"]["attempts"], 0)
        self.assertIsNone(report["execution"])
        self.assertEqual(report["active"], 1)
        self.assertEqual(report["peak_active"], 1)
        self.assertEqual(len(report["invocations"]), 1)
        (self.root / "agent_release").touch()

    def test_unsupported_native_memory_control_does_not_claim_or_invoke(self):
        app = self.open()
        # Capability fault is explicitly a platform-boundary fixture. It is
        # separate from the real-process native enforcement witness above.
        with patch("dispatcher_sdk.execution_kernel.resources.memory_capability",
                   return_value={"supported": False, "memory_basis": None,
                                 "scope": None, "reason": "fixture unsupported platform"}):
            _, notice_id = self.notice(app)
            self.wait(lambda: app.stall_supervisor_status()["admission_state"] == "resource_enforcement_unsupported")
            report = self.retain(app, notice_id)
            self.assertEqual(report["receipt"]["attempts"], 0)
            self.assertEqual(report["invocations"], [])
            self.assertEqual(report["resource_capability"]["reason"], "fixture unsupported platform")

    def test_actual_retired_flusher_keeps_memory_charge_after_business_result_and_ack(self):
        app = self.open()
        managed = app._managed_stall_supervisor
        entered, release, released_connection = (threading.Event() for _ in range(3))
        original = ObservationJournal._transaction
        retained = []

        @contextmanager
        def transaction(journal, **kwargs):
            with original(journal, **kwargs) as current:
                held = (journal is managed.runtime.observation_journal and
                        threading.current_thread().name == "dispatcher-observation-flush" and not retained)
                if held:
                    retained.append(current[0])
                    entered.set()
                    release.wait(10)
                    # A real connection remains usable on its owning thread
                    # until the original actual SQLite transaction finishes.
                    self.assertEqual(current[0].execute("SELECT 1").fetchone()[0], 1)
                    released_connection.set()
                yield current

        with patch.object(ObservationJournal, "_transaction", transaction):
            try:
                _, notice_id = self.notice(app)
                self.assertTrue(entered.wait(8))
                self.wait(lambda: app.inbox.get("dispatcher.stalls.v1", notice_id)["state"] == "consumed")
                self.wait(lambda: app.stall_supervisor_status()["completed"] == 1)
                before = self.retain(app, notice_id)
                (self.root / "held-flusher-before-release.json").write_text(
                    json.dumps(before, default=str, indent=2), encoding="utf-8")
                self.assertEqual(before["execution"]["result"]["status"], "succeeded")
                self.assertEqual(before["active"], 1)
                self.assertEqual(before["reserved_memory_bytes"], 512*1024*1024)
                self.assertTrue(before["cleanup_pending"])
                self.assertEqual(before["cleanup_ownership"][0]["state"], "confirmed")
            finally:
                release.set()
            self.assertTrue(released_connection.wait(3))
            self.wait(lambda: app.stall_supervisor_status()["active"] == 0)
            after = self.retain(app, notice_id)
            self.assertEqual(after["reserved_memory_bytes"], 0)
            self.assertEqual(after["execution"]["result"], before["execution"]["result"])
            self.assertEqual(after["receipt"], before["receipt"])

    def test_pending_reserved_binding_is_checked_before_recovery_opens_storage(self):
        app = self.open(memory_budget_bytes=1)
        _, notice_id = self.notice(app)
        managed = app._managed_stall_supervisor
        # The fixture owns this enrollment through the original application
        # inbox; no reserved coordinator work is admitted during shortage.
        lease = app.inbox.claim("test-enrollment", source_id="dispatcher.stalls.v1", lease_seconds=10)
        admission = managed._admission_context(lease)
        snapshot, control = managed._admit(lambda: managed._enroll(lease, admission=admission), admission)
        self.assertEqual(snapshot.state, "queued")
        (self.root / "release").touch()
        app.close(timeout=10)
        config = managed.options
        with self.assertRaises(DeploymentMismatchError):
            Dispatcher(self.root / "application.sqlite3", {"business": _business},
                       stall_handler=_changed_supervise, stall_options=config)
        reopened = self.open(memory_budget_bytes=1)
        after = self.retain(reopened, notice_id)
        self.assertEqual(reopened.preflight["checks"]["bindings"], "checked")
        self.assertEqual(after["execution"]["state"], "queued")
        self.assertEqual(after["run_control"]["deadline_at"], control["deadline_at"])
        self.assertEqual(after["invocations"], [])

    def cancellation_race(self, *, before_preparation):
        app = self.open()
        managed = app._managed_stall_supervisor
        entered, release = threading.Event(), threading.Event()
        name = "_prepare_handler_admission" if before_preparation else "run_once"
        original = getattr(managed.runtime, name)
        receipts = []
        observe = managed.runtime._process_cleanup_observer

        def barrier(*args, **kwargs):
            entered.set()
            release.wait(8)
            return original(*args, **kwargs)

        def cleanup_receipt(receipt):
            receipts.append(dict(receipt))
            observe(receipt)

        managed.runtime._process_cleanup_observer = cleanup_receipt
        with patch.object(managed.runtime, name, barrier):
            try:
                task, notice_id = self.notice(app)
                self.assertTrue(entered.wait(8))
                cancellation = task.cancel(reason="source revoked at real SDK admission barrier")
            finally:
                release.set()
            self.wait(lambda: app.inbox.get("dispatcher.stalls.v1", notice_id)["state"] == "dead")
            self.wait(lambda: app.stall_supervisor_status()["active"] == 0)
            report = self.retain(app, notice_id)
            report.update(native_admission_barrier=name, cleanup_receipts=receipts,
                          original_cancellation=cancellation.to_dict())
            (self.root / "cancel-before-invocation.json").write_text(
                json.dumps(report, default=str, indent=2), encoding="utf-8")
            self.assertEqual(report["invocations"], [])
            self.assertEqual(report["reserved_memory_bytes"], 0)
            self.assertFalse(report["cleanup_pending"])
            if before_preparation:
                self.assertEqual(report["execution"]["attempt"], 1)
                self.assertTrue(any(row["state"] == "not_invoked" for row in receipts))
            else:
                self.assertEqual(report["execution"]["attempt"], 0)
            app.close(timeout=10)
            self.assertEqual(app.health()["state"], "closed")

    def test_source_cancel_before_claim_keeps_no_false_process_cleanup_obligation(self):
        self.cancellation_race(before_preparation=False)

    def test_source_cancel_before_native_preparation_keeps_no_false_cleanup_obligation(self):
        self.cancellation_race(before_preparation=True)

    def test_status_bounds_real_oversized_command_and_receipt_before_json_decode(self):
        app = self.open(observation_options=ObservationOptions(query_bytes=4096))
        managed = app._managed_stall_supervisor
        notice_id = "oversized-status"
        run_id, execution_id = managed.identities(notice_id)
        # Actual SDK records are retained; the inspection does not invoke work.
        command = managed.runtime.command("__sdk_stall_supervisor__", execution_id=execution_id,
            idempotency_key=execution_id, correlation_id=run_id, timeout_seconds=5,
            payload={"large": "x"*400000})
        managed.runtime.kernel.register_run_control(run_id, max_claims=1,
            deadline_at=managed.runtime.kernel.current_time()+10)
        control = managed.runtime.kernel.set_run_control(run_id, expected_epoch=0, state="active", generation=0)
        managed.runtime.kernel.submit_managed(command, run_id=run_id, generation=control["generation"])
        app.inbox.accept("dispatcher.stalls.v1", {"notification_id": notice_id, "large": "x"*400000})
        with patch.object(app.runtime.kernel, "_snapshot", side_effect=AssertionError("oversized command decoded")), \
                patch.object(managed.inbox, "_record", side_effect=AssertionError("oversized receipt decoded")):
            report = app.stall_supervisor_status(notice_id)
        encoded = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (self.root / "bounded-status.json").write_bytes(encoded)
        self.assertLessEqual(len(encoded), 4096)
        self.assertFalse(report["complete"])
        self.assertTrue(report["execution"]["truncated"])
        self.assertTrue(report["receipt"]["truncated"])
        self.assertEqual(report["execution"]["state"], "queued")
        self.assertEqual(report["receipt"]["state"], "pending")
        self.assertEqual(self.invocations(), [])

    def test_status_lock_admission_uses_original_query_window(self):
        app = self.open(observation_options=ObservationOptions(query_timeout=.03))
        entered, release = threading.Event(), threading.Event()

        def hold():
            with app._lock:
                entered.set()
                release.wait(2)

        owner = threading.Thread(target=hold)
        owner.start()
        try:
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            with self.assertRaisesRegex(TimeoutError, "managed status admission"):
                app.stall_supervisor_status()
            elapsed = time.monotonic()-started
            (self.root / "query-lock.json").write_text(json.dumps({
                "query_timeout": .03, "elapsed": elapsed, "admitted": False}), encoding="utf-8")
            self.assertLess(elapsed, .2)
        finally:
            release.set()
            owner.join(1)
        self.assertFalse(owner.is_alive())

    def test_idle_reserved_scheduler_keeps_durable_inbox_clock_unchanged(self):
        app = self.open()
        managed = app._managed_stall_supervisor

        def clock():
            connection = sqlite3.connect(self.root / "application.sqlite3")
            try:
                return connection.execute("SELECT value FROM notification_inbox_clock WHERE id=1").fetchone()[0]
            finally:
                connection.close()

        before = clock()
        managed.start()
        self.wait(lambda: app.stall_supervisor_status()["empty_polls"] >= 3)
        report = app.stall_supervisor_status()
        after = clock()
        (self.root / "idle-inbox.json").write_text(json.dumps({
            "before": before, "after": after, "report": report}, indent=2), encoding="utf-8")
        self.assertEqual(report["claim_calls"], 0)
        self.assertEqual(after, before)
        self.assertEqual(report["admission_state"], "ready")
        self.assertIsNone(report["last_error"])

    def test_memory_limit_rejects_native_overflow_before_runtime_construction(self):
        with self.assertRaisesRegex(ValueError, "native representable"):
            ManagedStallOptions(memory_limit_bytes=sys.maxsize+1)
        # Aggregate admission accounting is a Python integer, not a native cap.
        options = ManagedStallOptions(memory_limit_bytes=512*1024*1024,
                                      memory_budget_bytes=sys.maxsize+1)
        self.assertEqual(options.memory_budget_bytes, sys.maxsize+1)
        self.assertEqual(self.apps, [])

    def direct_reserved_worker(self, notice_id, *, memory_probe=None):
        app = self.open()
        managed = app._managed_stall_supervisor
        run_id, execution_id = managed.identities(notice_id)
        # Direct original Kernel Run fixture avoids the independently failing
        # source-stall setup. This witnesses real native resource enforcement
        # and slot ownership, not notification enrollment/source inheritance.
        payload = {"notification_id": notice_id, "target": {"agent_root": str(self.root)}}
        if memory_probe is not None:
            payload["target"]["memory_probe"] = memory_probe
        command = managed.runtime.command("__sdk_stall_supervisor__", execution_id=execution_id,
            idempotency_key=execution_id, correlation_id=run_id, timeout_seconds=5, payload=payload)
        managed.runtime.kernel.register_run_control(run_id, max_claims=1,
            deadline_at=managed.runtime.kernel.current_time()+10)
        control = managed.runtime.kernel.set_run_control(run_id, expected_epoch=0, state="active", generation=0)
        managed.runtime.kernel.submit_managed(command, run_id=run_id, generation=control["generation"])
        with managed._lock:
            managed._ownership[notice_id] = {"execution_id": execution_id, "attempt": None,
                "fence": None, "state": "unknown", "source": "direct_native_resource_fixture"}
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(managed.runtime.run_once, execution_id=execution_id)
            with managed._lock:
                managed._active[notice_id] = future
            self.wait(future.done)
            snapshot = future.result()
        return app, managed, snapshot

    def test_actual_reserved_worker_rejects_allocation_above_native_limit_and_releases_ownership(self):
        app, managed, snapshot = self.direct_reserved_worker("native-memory-allocation",
            memory_probe=512*1024*1024+1)
        self.assertEqual(snapshot.state, "succeeded", snapshot.to_dict())
        report = app.stall_supervisor_status()
        evidence = snapshot.result.value
        (self.root / "native-allocation.json").write_text(json.dumps({
            "witness_scope": "direct_reserved_native_worker_and_ownership",
            "result": snapshot.to_dict(), "before_collection": report}, indent=2), encoding="utf-8")
        self.assertNotEqual(evidence["pid"], os.getpid())
        self.assertEqual(evidence["allocation"], {"requested_bytes": 512*1024*1024+1,
            "allocated": False, "error": "MemoryError"})
        self.assertEqual(report["reserved_memory_bytes"], 512*1024*1024)
        self.assertEqual(report["cleanup_ownership"][0]["state"], "confirmed")
        self.wait(lambda: (managed._collect(), app.stall_supervisor_status()["active"] == 0)[1])
        self.assertEqual(app.stall_supervisor_status()["reserved_memory_bytes"], 0)
        self.assertEqual(len(self.invocations()), 1)

    def test_done_unknown_owner_recovers_only_original_cleanup_note_after_real_reader_contention(self):
        notice_id = "original-cleanup-proof"
        app, managed, snapshot = self.direct_reserved_worker(notice_id)
        self.assertEqual(snapshot.state, "succeeded", snapshot.to_dict())
        original_result = snapshot.to_dict()
        journal = managed.runtime._settlement_journal
        proof = journal.inspect_notes(snapshot.execution_id)
        self.assertTrue(any(note["phase"] == "process_cleanup" and
            note["identity"]["attempt"] == snapshot.attempt and note["identity"]["fence"] == snapshot.fence and
            note["evidence"] == {"state": "confirmed", "source": "runtime_supervisor_reaped"}
            for note in proof["notes"]), proof)
        # Lose only local cache, as a recovering delivery does. Physical facts
        # come from the actual completed SDK process and its original note.
        with managed._lock:
            managed._cleanup_proofs.clear()
            managed._ownership[notice_id].update(state="unknown", source="recovery_fixture",
                fence=snapshot.fence+1)
        managed._collect()
        wrong = app.stall_supervisor_status()
        self.assertEqual(wrong["active"], 1)
        self.assertEqual(wrong["cleanup_ownership"][0]["state"], "unknown")
        with managed._lock:
            managed._ownership[notice_id]["fence"] = snapshot.fence
        # WAL permits this reader under an ordinary writer. Stop the fixture's
        # SDK storage services, then use an explicitly retained rollback-mode
        # lock to exercise real unavailable reading of the existing SDK proof.
        managed.runtime.request_stop()
        connection = sqlite3.connect(journal.path, timeout=.1, isolation_level=None)
        observed = []
        inspect_notes = journal.inspect_notes

        def inspect(*args, **kwargs):
            report = inspect_notes(*args, **kwargs)
            observed.append(report)
            return report

        try:
            fixture_mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            self.assertEqual(fixture_mode, "delete")
            connection.execute("BEGIN EXCLUSIVE")
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
            with patch.object(journal, "inspect_notes", inspect):
                managed._collect()
            blocked = app.stall_supervisor_status()
            (self.root / "cleanup-proof-before-release.json").write_text(json.dumps({
                "wrong_fence": wrong, "blocked": blocked, "actual_reader_reports": observed,
                "fixture_journal_mode": fixture_mode, "original_cleanup_note": proof,
                "original_result": original_result}, indent=2), encoding="utf-8")
            self.assertTrue(observed)
            self.assertFalse(observed[0]["complete"])
            self.assertEqual(blocked["active"], 1)
            self.assertEqual(blocked["reserved_memory_bytes"], 512*1024*1024)
            self.assertEqual(blocked["cleanup_ownership"][0]["state"], "unknown")
        finally:
            connection.rollback()
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            connection.close()
        self.wait(lambda: (managed._collect(), app.stall_supervisor_status()["active"] == 0)[1])
        self.assertEqual(managed.runtime.kernel.get(snapshot.execution_id).to_dict(), original_result)
        self.assertEqual(app.stall_supervisor_status()["reserved_memory_bytes"], 0)
        self.assertEqual(len(self.invocations()), 1)

    def test_pending_supervisor_close_stops_independent_host_preserves_error_and_storage(self):
        from dispatcher_sdk.observability.managed_supervisor import _AdmissionError
        notice_id = "stopping-original-native-result"
        app, managed, snapshot = self.direct_reserved_worker(notice_id)
        self.assertEqual(snapshot.state, "succeeded", snapshot.to_dict())
        # Actual durable receipt for the completed reserved command. This is
        # a lifecycle/query fixture, not a new live-source stall enrollment.
        accepted = app.inbox.accept("dispatcher.stalls.v1", snapshot.command.payload, max_attempts=2)
        lease = app.inbox.claim("stopping-status-fixture", source_id="dispatcher.stalls.v1", lease_seconds=10)
        receipt = app.inbox.consume(lease)
        self.assertEqual(receipt["notification_id"], accepted["notification_id"])
        before = app.stall_supervisor_status(notice_id)
        app.start()
        original = _AdmissionError("supervisor_cleanup_unknown", "fixture unresolved physical proof")
        with patch.object(app._managed_stall_supervisor, "close", side_effect=original):
            with self.assertRaises(_AdmissionError) as raised:
                app.close(timeout=5)
        self.assertIs(raised.exception, original)
        self.assertEqual(app.health()["state"], "stopping")
        self.assertFalse(app.host._thread.is_alive())
        self.assertTrue((self.root / "application.sqlite3").exists())
        # Independent Host cleanup owns and closes the business Runtime. The
        # unresolved reserved owner and application receipt stores stay open.
        with self.assertRaises(sqlite3.ProgrammingError):
            app.runtime.kernel.get_run_control("closed-business-kernel-query")
        self.assertIsNone(app._managed_stall_supervisor.runtime.kernel.get_run_control("still-open-storage-query"))
        after = app.stall_supervisor_status(notice_id)
        self.assertEqual(after["execution"], before["execution"])
        self.assertEqual(after["run_control"], before["run_control"])
        self.assertEqual(after["receipt"], before["receipt"])
        self.assertEqual(after["receipt"]["state"], "consumed")
        self.assertEqual(after["execution"]["result"], snapshot.result.to_dict())
        self.assertTrue(after["complete"])
        self.assertEqual(len(self.invocations()), 1)
        (self.root / "stopping-original-notice-query.json").write_text(json.dumps({
            "scope": "actual reserved result and durable receipt with injected close error",
            "before": before, "after_business_kernel_closed": after,
            "original_error": {"type": type(original).__name__, "code": original.code,
                "message": str(original)}}, indent=2), encoding="utf-8")
        app.close(timeout=5)
        self.assertEqual(app.health()["state"], "closed")

    def test_retained_admission_checkpoint_holds_slot_and_kernel_until_same_fact_commits(self):
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
        from dispatcher_sdk.execution_kernel._process_runtime import _KernelBudgetCapture
        from dispatcher_sdk.observability.managed_supervisor import _AdmissionError
        notice_id = "retained-admission-clock-fact"
        app, managed, snapshot = self.direct_reserved_worker(notice_id)
        self.assertEqual(snapshot.state, "succeeded", snapshot.to_dict())
        managed.runtime.request_stop()
        kernel = managed.runtime.kernel
        envelope = BudgetEnvelope.from_dict(kernel.get_execution_limits(snapshot.execution_id)["envelope"])
        original_deadline = envelope.deadline_monotonic(
            sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
        capture = _KernelBudgetCapture(kernel, snapshot.execution_id)
        begin, finish = kernel._begin_budget_sample, kernel._finish_budget_sample
        writers, trace = [], []
        phase = ["capture"]

        def arm_and_hold(execution_id, **kwargs):
            token = begin(execution_id, **kwargs)
            trace.append({"operation": "arm", "phase": phase[0], "token": token})
            writer = sqlite3.connect(kernel.db_path, timeout=.1, isolation_level=None)
            writer.execute("BEGIN IMMEDIATE")
            writers.append(writer)
            return token

        def acknowledge(token, execution_id, retained, **kwargs):
            event = {"operation": "ack", "phase": phase[0], "token": token}
            trace.append(event)
            try:
                result = finish(token, execution_id, retained, **kwargs)
                event["committed"] = True
                return result
            except BaseException as error:
                event.update(committed=False, error_type=type(error).__name__, error=str(error))
                raise

        evidence = {"scope": "real_reserved_process_then_actual_kernel_admission_checkpoint",
                    "original_result": snapshot.to_dict(), "trace": trace,
                    "capture_window": .05, "cleanup_attempt_window": .1}
        try:
            with patch.object(kernel, "_begin_budget_sample", arm_and_hold), patch.object(
                    kernel, "_finish_budget_sample", acknowledge):
                with self.assertRaises((sqlite3.OperationalError, TimeoutError)) as raised:
                    capture(envelope, timeout_seconds=.05)
                if isinstance(raised.exception, TimeoutError):
                    self.assertEqual(str(raised.exception), "Kernel control admission budget elapsed")
                self.assertTrue(writers, "original sample never armed the actual held writer")
                self.assertTrue(writers[0].in_transaction)
                self.assertEqual(writers[0].execute("SELECT 1").fetchone()[0], 1)
                self.assertIsNotNone(capture._pending)
                token, captured = capture._pending
                self.assertEqual(token, raised.exception.budget_sample_token)
                self.assertIsNotNone(captured)
                self.assertEqual(captured.to_dict(), raised.exception.budget_sample_envelope.to_dict())
                self.assertEqual(kernel._connection.execute(
                    "SELECT token FROM kernel_budget_samples WHERE token=?", (token,)).fetchone()[0], token)
                self.assertEqual(captured.constraints, envelope.constraints)
                self.assertEqual(captured.started_at, envelope.started_at)
                evidence["raw_error"] = {"type": type(raised.exception).__name__, "message": str(raised.exception)}
                evidence["captured"] = captured.to_dict()
                with managed._lock:
                    managed._admissions[notice_id] = {"capture": capture, "pending_owner": None,
                        "envelope": envelope.with_clock_floor(captured.checkpoint)}
                phase[0] = "first_close"
                with self.assertRaises(_AdmissionError) as pending:
                    app.close(timeout=2)
                self.assertEqual(pending.exception.code, "supervisor_checkpoint_pending")
                self.assertEqual(kernel._connection.execute("SELECT 1").fetchone()[0], 1)
                report = app.stall_supervisor_status()
                evidence["pending"] = report
                self.assertEqual(report["active"], 1)
                self.assertEqual(report["budget_checkpoint_pending"], 1)
                self.assertEqual(report["reserved_memory_bytes"], 512*1024*1024)
                self.assertTrue(any(event["operation"] == "ack" and event["phase"] == "first_close"
                    and event["token"] == token and event.get("error_type") == "OperationalError"
                    and event.get("error") == "database is locked" for event in trace), trace)
                writers[0].rollback()
                phase[0] = "second_close"
                app.close(timeout=2)
                self.assertIsNone(capture._pending)
                second = [event for event in trace if event["phase"] == "second_close"]
                self.assertEqual([event["token"] for event in second if event.get("committed")], [token])
                self.assertFalse(any(event["operation"] == "arm" for event in second))
                resumed = managed._admissions.get(notice_id)
                # Collection removes completed admission bookkeeping. Inspect
                # the committed original envelope through the actual database.
                connection = sqlite3.connect(kernel.db_path, timeout=.1)
                try:
                    row = connection.execute("SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?",
                        (snapshot.execution_id,)).fetchone()
                    canonical = BudgetEnvelope.from_dict(json.loads(row[0]))
                    original_result = json.loads(connection.execute(
                        "SELECT result_json FROM kernel_executions WHERE execution_id=?",
                        (snapshot.execution_id,)).fetchone()[0])
                finally:
                    connection.close()
                self.assertEqual(canonical.constraints, envelope.constraints)
                self.assertEqual(canonical.started_at, envelope.started_at)
                comparison_sample = sample_clock(wall_time=canonical.checkpoint.wall_at)
                original_view = envelope.view(sample=comparison_sample)
                canonical_view = canonical.view(sample=comparison_sample)
                self.assertEqual(canonical_view.effective_work_deadline_at, original_view.effective_work_deadline_at)
                self.assertEqual(canonical_view.effective_hard_deadline_at, original_view.effective_hard_deadline_at)
                self.assertLessEqual(canonical_view.remaining_work_seconds, original_view.remaining_work_seconds)
                self.assertLessEqual(canonical_view.remaining_hard_seconds, original_view.remaining_hard_seconds)
                evidence["same_sample_views"] = {"sample": comparison_sample.to_dict(),
                    "original": original_view.to_dict(), "canonical": canonical_view.to_dict()}
                evidence["independent_timer_anchor_instrumentation"] = {
                    "original_projection": original_deadline,
                    "canonical_projection": canonical.deadline_monotonic(sample=comparison_sample),
                    "scope": "independent fresh timer anchors; not a retained Runtime driver cutoff"}
                self.assertEqual(original_result, snapshot.result.to_dict())
                self.assertIsNone(resumed)
                evidence["canonical_after_same_token_ack"] = canonical.to_dict()
                self.assertEqual(managed._active, {})
                self.assertEqual(len(self.invocations()), 1)
                self.assertEqual(app.health()["state"], "closed")
        finally:
            for writer in writers:
                writer.rollback()
                writer.close()
            (self.root / "retained-admission-checkpoint.json").write_text(
                json.dumps(evidence, indent=2), encoding="utf-8")

    def test_actual_preentry_registry_fact_retains_capacity_without_context_or_process(self):
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope
        app = self.open()
        managed, notice_id = app._managed_stall_supervisor, "preentry-owned-clock-fact"
        kernel = managed.runtime.kernel
        run_id, execution_id = managed.identities(notice_id)
        wall = [time.time()]
        command = managed.runtime.command("__sdk_stall_supervisor__", execution_id=execution_id,
            idempotency_key=execution_id, correlation_id=run_id, timeout_seconds=5,
            payload={"notification_id": notice_id, "target": {"agent_root": str(self.root)}})
        writers, receipts, trace = [], [], []
        phase = ["actual_runtime_preparation"]
        preparing = threading.local()
        begin, finish = kernel._begin_budget_sample, kernel._finish_budget_sample
        prepare = managed.runtime._prepare_handler_admission
        observe = managed.runtime._process_cleanup_observer
        evidence = {"scope": "actual Runtime pre-native preparation, no manual admission owner",
            "original_run_seconds": 10, "command_timeout_seconds": 5, "trace": trace}

        def prepare_actual(*args, **kwargs):
            preparing.active = True
            try:
                result = prepare(*args, **kwargs)
                evidence["actual_preparation_error"] = result[1]
                return result
            finally:
                preparing.active = False

        def arm_and_hold(execution, **kwargs):
            token = begin(execution, **kwargs)
            trace.append({"operation": "arm", "phase": phase[0], "token": token})
            if getattr(preparing, "active", False) and not writers:
                writer = sqlite3.connect(kernel.db_path, timeout=.1, isolation_level=None,
                                         check_same_thread=False)
                writer.execute("BEGIN IMMEDIATE")
                writers.append(writer)
                wall[0] += 11
                evidence.update(blocked_token=token, forward_wall=wall[0])
            return token

        def acknowledge(token, execution, envelope, **kwargs):
            event = {"operation": "ack", "phase": phase[0], "token": token,
                     "captured_envelope": envelope.to_dict()}
            trace.append(event)
            try:
                result = finish(token, execution, envelope, **kwargs)
                event["committed"] = True
                return result
            except BaseException as error:
                event.update(committed=False, error_type=type(error).__name__, error=str(error))
                raise

        def actual_receipt(receipt):
            receipts.append(dict(receipt))
            observe(receipt)

        try:
            with patch.object(kernel, "_now", lambda: wall[0]), patch.object(
                    kernel, "_begin_budget_sample", arm_and_hold), patch.object(
                    kernel, "_finish_budget_sample", acknowledge), patch.object(
                    managed.runtime, "_prepare_handler_admission", prepare_actual), patch.object(
                    managed.runtime, "_process_cleanup_observer", actual_receipt):
                kernel.register_run_control(run_id, max_claims=1, deadline_at=wall[0]+10)
                control = kernel.set_run_control(run_id, expected_epoch=0, state="active", generation=0)
                kernel.submit_managed(command, run_id=run_id, generation=control["generation"])
                with managed._lock:
                    managed._ownership[notice_id] = {"execution_id": execution_id, "attempt": None,
                        "fence": None, "state": "unknown", "source": "actual_preparation_fixture"}
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(managed.runtime.run_once, execution_id=execution_id)
                    with managed._lock:
                        managed._active[notice_id] = future
                    self.wait(future.done)
                    snapshot = future.result()
                managed.runtime.request_stop()
                self.assertTrue(writers)
                self.assertTrue(writers[0].in_transaction)
                self.assertTrue(any(receipt["state"] == "not_invoked" for receipt in receipts), receipts)
                self.assertEqual(self.invocations(), [])
                self.assertEqual(managed._admissions, {})
                self.assertEqual(managed.runtime._thread_contexts, {})
                self.assertEqual(managed.runtime._process_supervisors, {})
                initial_status = app.stall_supervisor_status()
                evidence["initial_registry_inspection"] = initial_status
                if initial_status["budget_checkpoint_state"] == "unknown":
                    self.assertIsNone(initial_status["budget_checkpoint_pending"])
                    self.assertFalse(initial_status["complete"])
                    self.assertEqual(initial_status["unknown_reason"], "budget_checkpoint_registry_unavailable")
                self.wait(lambda: kernel._budget_sample_status(execution_id) is True)
                with kernel._lock:
                    owner = kernel._budget_sample_owners[evidence["blocked_token"]]
                    retained = owner._pending[1]
                self.assertIsNotNone(retained)
                self.assertGreaterEqual(retained.checkpoint.wall_at, evidence["forward_wall"])
                original_limits = kernel.get_execution_limits(execution_id)
                original = BudgetEnvelope.from_dict(original_limits["envelope"])
                claimed_control = kernel.get_run_control(run_id)
                self.assertEqual(claimed_control["claims_used"], 1)
                self.assertEqual(claimed_control["deadline_at"], control["deadline_at"])
                self.assertEqual(retained.constraints, original.constraints)
                self.assertEqual(evidence["actual_preparation_error"]["kind"], "timeout")
                self.assertEqual(evidence["actual_preparation_error"]["phase"], "entry_authority")
                managed._collect()
                blocked = app.stall_supervisor_status()
                evidence.update(original_control=control, returned_snapshot=snapshot.to_dict(),
                    claimed_control=claimed_control, cleanup_receipts=receipts,
                    blocked=blocked, original_limits=original_limits)
                self.assertEqual(blocked["active"], 1)
                self.assertEqual(blocked["reserved_memory_bytes"], 512*1024*1024)
                self.assertEqual(blocked["cleanup_ownership"][0]["state"], "not_invoked")
                self.assertEqual(blocked["budget_checkpoint_pending"], 1)
                self.assertEqual(blocked["budget_checkpoint_known_pending"], 1)
                self.assertEqual(blocked["budget_checkpoint_state"], "pending")
                phase[0] = "original_fact_cleanup"
                writers[0].rollback()
                wall[0] -= 11
                self.wait(lambda: (kernel._drain_budget_samples(time.monotonic()+.1),
                    managed._collect(), app.stall_supervisor_status()["active"] == 0)[2])
                after = app.stall_supervisor_status()
                evidence["after_same_fact_cleanup"] = after
                self.assertEqual(after["reserved_memory_bytes"], 0)
                self.assertEqual(after["budget_checkpoint_pending"], 0)
                self.assertEqual(self.invocations(), [])
                self.assertIsNone(owner._pending)
                cleanup = [event for event in trace if event["phase"] == "original_fact_cleanup"]
                self.assertFalse(any(event["operation"] == "arm" for event in cleanup))
                self.assertEqual([event["token"] for event in cleanup if event.get("committed")],
                                 [evidence["blocked_token"]])
                canonical = BudgetEnvelope.from_dict(kernel.get_execution_limits(execution_id)["envelope"])
                self.assertEqual(canonical.constraints, original.constraints)
                self.assertEqual(canonical.started_at, original.started_at)
                self.assertGreaterEqual(canonical.checkpoint.wall_at, retained.checkpoint.wall_at)
                self.assertEqual(kernel.get_run_control(run_id), claimed_control)
        finally:
            for writer in writers:
                writer.rollback()
                writer.close()
            (self.root / "actual-preentry-registry-ownership.json").write_text(
                json.dumps(evidence, indent=2), encoding="utf-8")

    def test_actual_executor_partial_submit_cannot_invoke_or_reclaim_after_failure(self):
        import errno
        app = self.open(capacity=2)
        managed = app._managed_stall_supervisor
        first, second, third = "executor-existing-worker", "executor-rejected-item", "executor-after-failure"
        entered, release, failure = threading.Event(), threading.Event(), threading.Event()
        calls, queued = [], []
        original_error = OSError(errno.EAGAIN, "fixture OS resource failure after real WorkItem enqueue")
        evidence = {"scope": "actual ThreadPoolExecutor registration/retirement; no native handler witness",
                    "capacity": 2, "calls": calls, "claim_seconds": 40}

        def hold_accepted(lease):
            calls.append(lease.notification_id)
            if lease.notification_id == first:
                entered.set()
                release.wait(8)

        class QueueEvidence:
            def __init__(self, actual):
                self.actual = actual
            def put(self, item, *args, **kwargs):
                if item is not None:
                    queued.append(item)
                return self.actual.put(item, *args, **kwargs)
            def get(self, *args, **kwargs):
                return self.actual.get(*args, **kwargs)
            def get_nowait(self):
                return self.actual.get_nowait()

        def fail_after_real_enqueue():
            self.assertTrue(queued, "stdlib did not enqueue before adjusting threads")
            item = queued[-1]
            # Let the already existing worker dequeue this real WorkItem and
            # mark its Future running. SDK registration still holds its lock,
            # so the queued wrapper must wait for the failed acceptance gate.
            release.set()
            self.wait(item.future.running)
            failure.set()
            raise original_error

        try:
            with patch.object(managed, "_handle", hold_accepted):
                app.inbox.accept("dispatcher.stalls.v1", {"notification_id": first, "kind": "stalled"})
                managed.start()
                self.assertTrue(entered.wait(8))
                executor = managed._executor
                executor._work_queue = QueueEvidence(executor._work_queue)
                with patch.object(executor, "_adjust_thread_count", fail_after_real_enqueue):
                    accepted = app.inbox.accept("dispatcher.stalls.v1",
                        {"notification_id": second, "kind": "stalled"})
                    self.assertTrue(failure.wait(8))
                    self.wait(lambda: managed._executor_unavailable)
                    self.wait(lambda: queued[0].future.done())
                self.assertEqual(queued[0].future.result(), None)
                self.assertEqual(calls, [first])
                self.wait(lambda: app.stall_supervisor_status()["active"] == 0)
                rejected = app.inbox.get("dispatcher.stalls.v1", second)
                self.assertEqual(rejected["state"], "processing")
                self.assertEqual(rejected["attempts"], 1)
                self.assertEqual(rejected["payload"], accepted["payload"])
                before = app.stall_supervisor_status()
                self.assertEqual(before["admission_state"], "executor_unavailable")
                self.assertEqual(before["claim_calls"], 2)
                self.assertEqual(before["peak_active"], 1)
                self.assertEqual(before["reserved_memory_bytes"], 0)
                self.assertEqual(before["cleanup_ownership"], [])
                self.assertEqual(before["executor_error"]["type"], "BlockingIOError")
                self.assertEqual(before["executor_error"]["message"], str(original_error))
                app.inbox.accept("dispatcher.stalls.v1", {"notification_id": third, "kind": "stalled"})
                # Observe multiple real coordinator ticks without resetting a
                # work budget or creating another executor/processing lease.
                time.sleep(managed.options.poll_interval*3)
                after = app.stall_supervisor_status()
                self.assertEqual(after["claim_calls"], before["claim_calls"])
                self.assertEqual(after["admission_state"], "executor_unavailable")
                self.assertEqual(app.inbox.get("dispatcher.stalls.v1", second), rejected)
                unclaimed = app.inbox.get("dispatcher.stalls.v1", third)
                self.assertEqual(unclaimed["attempts"], 0)
                self.assertEqual(unclaimed["state"], "pending")
                self.assertEqual(len(queued), 1)
                self.assertEqual(calls, [first])
                evidence.update(before=before, after=after, rejected_receipt=rejected,
                    unclaimed_receipt=unclaimed, real_queued_future_state=queued[0].future._state)
        finally:
            release.set()
            (self.root / "actual-executor-partial-submit.json").write_text(
                json.dumps(evidence, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
