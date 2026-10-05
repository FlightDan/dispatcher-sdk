"""Real SQLite witnesses for the Host's advisory notification collection gate."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy, StaleFenceError
from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator.host import OrchestratorHost


def echo(payload, context):
    return payload


echo.__execution_kernel_revision__ = "collection-readiness-test-v1"


class Clock:
    def __init__(self):
        self.value = 100.
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


class NotificationCollectionReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "state.db"
        self.clock = Clock()
        self.runtime = Kernel.open_sqlite(self.path, {"echo": echo}, isolation_mode="thread",
                                         now=lambda: self.clock.value)
        self.addCleanup(self.runtime.close)
        self.sdk = Orchestrator(self.path, self.runtime.kernel, runtime=self.runtime, clock=self.clock)
        self.sdk.create_run("run", command_id="create")
        self.host = OrchestratorHost(self.sdk)

    def apply(self, *operations):
        state = self.sdk.get_run("run")
        return self.sdk.apply_operations("run", command_id=f"op-{state['revision']}",
            expected_revision=state["revision"], operations=list(operations))

    def command(self, execution_id):
        return ExecutionCommandV2(execution_id=execution_id, idempotency_key=execution_id,
            registry_revision=self.runtime.registry_revision, correlation_id="run", causation_id=None,
            handler_id="echo", handler_contract_version=1, retry_policy=RetryPolicy(),
            timeout_seconds=10, payload={}).to_dict()

    def add(self, task_id="task", execution_id="exec", *, watch=True, dispatch=False):
        operations = [dict(kind="add_task", task_id=task_id, command=self.command(execution_id))]
        if watch:
            operations.append(dict(kind="watch_task", task_id=task_id, watch_id=task_id,
                                   target={"conversation_id": "chat"}))
        if dispatch:
            operations.append(dict(kind="dispatch", task_id=task_id))
        self.apply(*operations)
        self.sdk.flush()

    def pump(self):
        return self.host.runtime_host.bridge.pump()

    def snapshot(self):
        with closing(self.sdk._connect(configure=False)) as connection:
            return (connection.execute("SELECT value FROM sdk_result_clock WHERE id=1").fetchone()[0],
                    connection.execute("SELECT mutation FROM sdk_storage_clock WHERE singleton=1").fetchone()[0],
                    tuple(tuple(row) for row in connection.execute(
                        "SELECT watch_id,cursor,completed FROM sdk_watches ORDER BY watch_id")))

    def test_idle_readiness_reads_through_real_writer_without_clock_or_watermark_writes(self):
        self.add()
        self.assertEqual([], self.runtime.kernel.events_since(0, 100))
        before = self.snapshot()
        calls = self.clock.calls
        completed = threading.Event()
        outcomes = []

        def inspect():
            try:
                outcomes.append(self.sdk._notification_collection_ready())
            except BaseException as error:
                outcomes.append(error)
            finally:
                completed.set()

        with closing(sqlite3.connect(self.path, isolation_level=None)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE sdk_result_clock SET value=999 WHERE id=1")
            worker = threading.Thread(target=inspect, daemon=True)
            worker.start()
            try:
                self.assertTrue(completed.wait(.5), "advisory collection read waited for writer admission")
                self.assertEqual([False], outcomes)
                self.assertEqual(calls, self.clock.calls)
                self.assertEqual(before, self.snapshot())
            finally:
                writer.rollback()
                worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(before, self.snapshot())
        self.clock.value = 200
        self.pump()
        self.assertEqual(before[0], self.snapshot()[0])

    def test_public_empty_collection_still_observes_delivery_clock(self):
        self.add()
        self.assertFalse(self.sdk._notification_collection_ready())
        before_calls = self.clock.calls
        self.clock.value = 200
        self.assertEqual(0, self.sdk.collect_notifications())
        self.assertEqual(200, self.snapshot()[0])
        self.assertGreater(self.clock.calls, before_calls)

    def test_planned_cancellation_without_kernel_events_reaches_actual_host_pump(self):
        self.add()
        self.apply(dict(kind="cancel", task_id="task", reason="application cancelled"))
        self.assertEqual([], self.runtime.kernel.events_since(0, 100))
        self.assertTrue(self.sdk._notification_collection_ready())
        self.pump()
        notices = self.sdk.list_notifications()
        self.assertEqual(1, len(notices))
        self.assertEqual("cancelled", notices[0]["payload"]["state"])
        self.assertIsNone(notices[0]["payload"]["event"])
        self.assertTrue(self.host._wake_event.is_set())
        self.assertEqual(1, self.snapshot()[2][0][2])

    def test_planned_cancellation_uses_bound_historical_attempt_instead_of_latest(self):
        self.add()
        self.apply(dict(kind="cancel", task_id="task", reason="original cancelled"))
        self.apply(dict(kind="new_attempt", task_id="task", command=self.command("exec-new")))
        attempts = self.sdk.get_run("run")["tasks"]["task"]["attempts"]
        self.assertEqual("cancelled", attempts[0]["state"])
        self.assertNotEqual("cancelled", attempts[1]["state"])
        self.assertEqual([], self.runtime.kernel.events_since(0, 100))
        self.assertTrue(self.sdk._notification_collection_ready())
        self.pump()
        payload = self.sdk.list_notifications()[0]["payload"]
        self.assertEqual((0, "exec", "original cancelled"),
                         (payload["attempt"], payload["execution_id"], payload["reason"]))
        self.assertEqual(attempts[1], self.sdk.get_run("run")["tasks"]["task"]["attempts"][1])

    def test_unrelated_kernel_events_still_advance_open_watch_cursor(self):
        self.add()
        self.add("other", "exec-other", watch=False, dispatch=True)
        events = self.runtime.kernel.events_since(0, 100)
        self.assertTrue(events)
        self.assertTrue(all(event.execution_id == "exec-other" for event in events))
        self.assertTrue(self.sdk._notification_collection_ready())
        self.pump()
        self.assertEqual(("task", events[-1].sequence, 0), self.snapshot()[2][0])
        self.assertEqual((), self.sdk.list_notifications())
        self.assertFalse(self.sdk._notification_collection_ready())

    def test_cancellation_racing_false_readiness_is_collected_on_next_actual_pump(self):
        self.add()
        original = self.sdk._notification_collection_ready
        observations = []

        def enqueue_after_read():
            ready = original()
            observations.append(ready)
            if len(observations) == 1:
                self.assertFalse(ready)
                self.apply(dict(kind="cancel", task_id="task", reason="racing cancellation"))
            return ready

        self.sdk._notification_collection_ready = enqueue_after_read
        self.pump()
        self.assertEqual((), self.sdk.list_notifications())
        self.assertFalse(self.host._wake_event.is_set())
        self.pump()
        self.assertEqual([False, True], observations)
        self.assertEqual("racing cancellation", self.sdk.list_notifications()[0]["payload"]["reason"])
        self.assertTrue(self.host._wake_event.is_set())

    def test_pending_and_leased_notification_keep_shared_clock_fencing_under_wall_rollback(self):
        self.add()
        self.apply(dict(kind="cancel", task_id="task", reason="cancelled"))
        self.pump()
        self.add("idle", "idle-exec")
        self.assertEqual([], self.runtime.kernel.events_since(0, 100))
        self.assertTrue(self.sdk._notification_collection_ready())
        self.clock.value = 200
        self.pump()
        self.assertEqual(200, self.snapshot()[0])
        notice = self.sdk.claim_notifications(owner="app", lease_seconds=1)[0]
        self.assertEqual("delivering", notice["state"])
        self.assertTrue(self.sdk._notification_collection_ready())
        self.clock.value = 202
        self.pump()
        self.clock.value = 100
        with self.assertRaises(StaleFenceError):
            self.sdk.acknowledge_notification(notice["notification_id"],
                lease_id=notice["lease_id"], fence=notice["fence"])
        self.assertEqual(202, self.snapshot()[0])
        self.assertEqual("delivering", self.sdk.load_notification(notice["notification_id"])["state"])

    def test_pending_and_leased_result_keep_shared_clock_fencing_under_wall_rollback(self):
        self.add()
        self.add("result", "result-exec", watch=False, dispatch=True)
        self.runtime.run_once()
        self.assertEqual(1, self.sdk.pump_results())
        self.pump()  # Consume unrelated Kernel events before testing the result-only eligibility.
        cursor = self.snapshot()[2][0][1]
        self.assertEqual([], self.runtime.kernel.events_since(cursor, 100))
        self.assertEqual((), self.sdk.list_notifications())
        self.assertTrue(self.sdk._notification_collection_ready())
        self.clock.value = 200
        self.pump()
        self.assertEqual(200, self.snapshot()[0])
        result = self.sdk.claim_results(owner="app", lease_seconds=1, limit=1)[0]
        self.assertTrue(self.sdk._notification_collection_ready())
        self.clock.value = 202
        self.pump()
        self.clock.value = 100
        with self.assertRaises(StaleFenceError):
            self.sdk.acknowledge_result(result["result"]["result_id"],
                lease_id=result["lease_id"], fence=result["fence"])
        self.assertEqual(202, self.snapshot()[0])
        with closing(self.sdk._connect(configure=False)) as connection:
            self.assertEqual("delivering", connection.execute(
                "SELECT state FROM sdk_results WHERE result_id=?", (result["result"]["result_id"],)).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
