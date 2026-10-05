"""Real SQLite witnesses for advisory background notification admission."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from dispatcher_sdk import Dispatcher
from dispatcher_sdk.execution_kernel import StaleFenceError
from dispatcher_sdk.orchestrator import NotificationInbox


APPLICATION_SOURCE = "dispatcher.application.v1"
STALL_SOURCE = "dispatcher.stalls.v1"


def passthrough(payload, context):
    return payload


class Clock:
    def __init__(self):
        self.value = 100.
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


class InboxBackgroundReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "application.sqlite3"

    def watermark(self):
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
            return connection.execute(
                "SELECT value FROM notification_inbox_clock WHERE id=1").fetchone()[0]

    def wait_for(self, query, *, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if query():
                return
            time.sleep(.01)
        self.fail("condition was not reached within its original stage deadline")

    def open_app(self, result_callback=None, stall_callback=None):
        app = Dispatcher(self.path, {"passthrough": passthrough},
            isolation_mode="thread", on_result=result_callback or (lambda payload: None))
        self.addCleanup(app.close)
        app.subscribe_stalls(stall_callback or (lambda payload: None))
        return app

    def test_idle_readiness_reads_committed_rows_through_a_real_writer_without_sampling_clock(self):
        clock = Clock()
        inbox = NotificationInbox(self.path, clock=clock)
        inbox.accept("another-source", {"notification_id": "unrelated"})
        before = self.watermark()
        observed_calls = clock.calls
        completed = threading.Event()
        outcome = []

        def inspect():
            try:
                outcome.append(inbox._delivery_ready(STALL_SOURCE))
            except BaseException as error:
                outcome.append(error)
            finally:
                completed.set()

        with closing(sqlite3.connect(self.path, isolation_level=None)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE notification_inbox_clock SET value=999 WHERE id=1")
            worker = threading.Thread(target=inspect, daemon=True)
            worker.start()
            try:
                self.assertTrue(completed.wait(.5), "advisory read waited for the SQLite writer")
                self.assertEqual(outcome, [False])
                self.assertEqual(clock.calls, observed_calls)
                self.assertEqual(self.watermark(), before)
            finally:
                writer.rollback()
                worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(self.watermark(), before)

    def test_public_empty_claim_still_observes_the_original_durable_clock(self):
        clock = Clock()
        inbox = NotificationInbox(self.path, clock=clock)
        self.assertFalse(inbox._delivery_ready(STALL_SOURCE))
        self.assertEqual(self.watermark(), 0)
        self.assertEqual(clock.calls, 0)
        self.assertIsNone(inbox.claim("explicit-consumer", source_id=STALL_SOURCE))
        self.assertEqual(self.watermark(), 100)
        self.assertGreater(clock.calls, 0)

    def test_future_retry_remains_ready_and_the_claim_uses_its_durable_floor_after_wall_rollback(self):
        clock = Clock()
        inbox = NotificationInbox(self.path, clock=clock)
        inbox.accept(STALL_SOURCE, {"notification_id": "retry"})
        original = inbox.claim("original", source_id=STALL_SOURCE)
        receipt = inbox.fail(original, error={"type": "ApplicationError"}, retry_delay=50)
        self.assertEqual(receipt["next_attempt_at"], 150)
        self.assertTrue(inbox._delivery_ready(STALL_SOURCE))
        self.assertIsNone(inbox.claim("too-early", source_id=STALL_SOURCE))
        clock.value = 200
        self.assertIsNone(inbox.claim("clock-observer", source_id="another-source"))
        clock.value = 1
        self.assertTrue(inbox._delivery_ready(STALL_SOURCE))
        replay = inbox.claim("replay", source_id=STALL_SOURCE)
        self.assertEqual(replay.notification_id, "retry")
        self.assertEqual(replay.attempt, 2)
        self.assertGreater(replay.fence, original.fence)
        self.assertEqual(replay.expires_at, 230)
        self.assertEqual(self.watermark(), 200)

    def test_other_source_processing_keeps_global_expiry_and_rollback_fencing_active(self):
        clock = Clock()
        inbox = NotificationInbox(self.path, clock=clock)
        inbox.accept("another-source", {"notification_id": "leased"}, max_attempts=1)
        original = inbox.claim("original", source_id="another-source", lease_seconds=1)
        self.assertTrue(inbox._delivery_ready(STALL_SOURCE))
        clock.value = 200
        with self.assertRaises(StaleFenceError):
            inbox.consume(original)
        # Failed consumption retains the observed clock and leaves expiry to
        # the next claim, even when that claim belongs to another source.
        self.assertEqual(inbox.get("another-source", "leased")["state"], "processing")
        clock.value = 1
        self.assertTrue(inbox._delivery_ready(STALL_SOURCE))
        self.assertIsNone(inbox.claim("stall-consumer", source_id=STALL_SOURCE))
        expired = inbox.get("another-source", "leased")
        self.assertEqual(expired["state"], "dead")
        self.assertEqual(expired["attempts"], 1)
        self.assertEqual(expired["last_error"]["type"], "LeaseExpired")
        self.assertEqual(self.watermark(), 200)
        self.assertFalse(inbox._delivery_ready(STALL_SOURCE))

    def test_both_actual_background_consumers_keep_the_idle_inbox_clock_unchanged_under_writer_contention(self):
        app = self.open_app()
        observed = {APPLICATION_SOURCE: 0, STALL_SOURCE: 0}
        ready_events = {source: threading.Event() for source in observed}
        guard = threading.Lock()
        original = app.inbox._delivery_ready

        def observe(source):
            result = original(source)
            with guard:
                observed[source] += 1
                if observed[source] >= 3:
                    ready_events[source].set()
            return result

        app.inbox._delivery_ready = observe
        before = self.watermark()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE notification_inbox_clock SET value=999 WHERE id=1")
            # Run the actual owned background loops while an independent native
            # writer makes any accidental empty claim unable to commit.
            app.start()
            try:
                for source, event in ready_events.items():
                    self.assertTrue(event.wait(1), "idle consumer could not inspect " + source)
                self.assertEqual(self.watermark(), before)
                self.assertTrue(app._consumer.is_alive())
                self.assertTrue(app._stall_consumer.is_alive())
                self.assertEqual(app.health()["callback_errors"], 0)
            finally:
                writer.rollback()
        self.assertEqual(self.watermark(), before)

    def test_accept_racing_a_false_readiness_poll_reaches_both_actual_callbacks_on_the_next_poll(self):
        received = {APPLICATION_SOURCE: [], STALL_SOURCE: []}
        callbacks = {source: threading.Event() for source in received}

        def callback(source):
            def deliver(payload):
                received[source].append(payload["notification_id"])
                callbacks[source].set()
            return deliver

        app = self.open_app(callback(APPLICATION_SOURCE), callback(STALL_SOURCE))
        sampled = {source: threading.Event() for source in received}
        proceed = threading.Event()
        self.addCleanup(proceed.set)
        original = app.inbox._delivery_ready

        def false_poll(source):
            result = original(source)
            if not result and not sampled[source].is_set():
                sampled[source].set()
                proceed.wait(3)
            return result

        app.inbox._delivery_ready = false_poll
        app.start()
        try:
            for event in sampled.values():
                self.assertTrue(event.wait(1), "consumer did not reach its initial empty poll")
            app._accept({"kind": "terminal", "notification_id": "result-race"})
            app._accept({"kind": "stalled", "notification_id": "stall-race"})
            self.assertEqual(received, {APPLICATION_SOURCE: [], STALL_SOURCE: []})
        finally:
            proceed.set()
        for event in callbacks.values():
            self.assertTrue(event.wait(2), "accepted notification was lost after a false advisory read")
        self.wait_for(lambda: all(app.inbox.get(source, identity)["state"] == "consumed"
            for source, identity in ((APPLICATION_SOURCE, "result-race"), (STALL_SOURCE, "stall-race"))))
        self.assertEqual(received, {APPLICATION_SOURCE: ["result-race"], STALL_SOURCE: ["stall-race"]})
        self.assertEqual(app.health()["callback_errors"], 0)

    def test_actual_readiness_sql_errors_remain_visible_and_background_delivery_recovers(self):
        delivered = threading.Event()
        app = self.open_app(stall_callback=lambda payload: delivered.set())
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("ALTER TABLE notification_inbox_messages RENAME TO unavailable_inbox_messages")
            connection.commit()
        app.start()
        try:
            self.wait_for(lambda: app.health()["callback_errors"] > 0)
            error = app.health()["last_callback_error"]
            self.assertIn("OperationalError", error)
            self.assertIn("notification_inbox_messages", error)
        finally:
            with closing(sqlite3.connect(self.path)) as connection:
                connection.execute("ALTER TABLE unavailable_inbox_messages RENAME TO notification_inbox_messages")
                connection.commit()
        app._accept({"kind": "stalled", "notification_id": "recovered"})
        self.assertTrue(delivered.wait(2), "background consumer did not recover after its read error")
        self.wait_for(lambda: app.inbox.get(STALL_SOURCE, "recovered")["state"] == "consumed")
