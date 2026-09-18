from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from dispatcher_sdk import (Dispatcher, DeploymentMismatchError, RecoveryRequiredError,
                            SubmissionConflictError)


def double(payload, context):
    return payload * 2


def changed(payload, context):
    return payload * 3


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "work.sqlite3"

    def open(self, **kwargs):
        dispatcher = Dispatcher(self.path, {"double": double}, isolation_mode="thread", **kwargs)
        self.addCleanup(dispatcher.close)
        return dispatcher

    def test_submit_replay_conflict_and_restart_without_exposing_run(self):
        app = self.open()
        original = app.submit("double", 21, request_id="input-1")
        replay = app.submit("double", 21, request_id="input-1")
        self.assertEqual(original.snapshot, replay.snapshot)
        with self.assertRaises(SubmissionConflictError):
            app.submit("double", 22, request_id="input-1")
        app.close()
        with self.open() as reopened:
            result = reopened.task("input-1").wait(timeout=5)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["value"], 42)
            self.assertEqual(reopened.submit("double", 21, request_id="input-1").wait()["result_id"],
                             result["result_id"])

    def test_concurrent_same_request_has_one_execution(self):
        first = self.open()
        second = self.open()
        with ThreadPoolExecutor(2) as pool:
            tasks = list(pool.map(lambda app: app.submit("double", 7, request_id="same"),
                                  [first, second]))
        self.assertEqual(tasks[0].snapshot["command"]["execution_id"],
                         tasks[1].snapshot["command"]["execution_id"])
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM sdk_executions").fetchone()[0], 1)

    def test_preflight_refuses_changed_pending_handler_before_start(self):
        app = self.open()
        app.submit("double", 2, request_id="pending")
        app.close()
        with self.assertRaises(DeploymentMismatchError) as caught:
            Dispatcher(self.path, {"double": changed}, isolation_mode="thread")
        self.assertFalse(caught.exception.report["compatible"])
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM kernel_executions").fetchone()[0], 0)

    def test_callback_failure_retries_receipt_without_reexecuting_task(self):
        received = []
        done = threading.Event()

        def callback(notification):
            received.append(notification)
            if len(received) == 1:
                raise ValueError("retry delivery")
            done.set()

        with self.open(on_result=callback, callback_retry_delay=0.01) as app:
            result = app.submit("double", 8, request_id="retry").wait()
            self.assertTrue(done.wait(5))
            self.assertEqual(len(received), 2)
            self.assertEqual(received[0]["notification_id"], received[1]["notification_id"])
            self.assertEqual(result["attempt"], 1)
            self.assertEqual(app.health()["callback_errors"], 1)

    def test_transactional_consumer_rolls_back_business_sql_and_ack(self):
        with self.open(callback_retry_delay=0.01) as app:
            app.submit("double", 3, request_id="sql").wait()
            wait_for(lambda: bool(app.inbox.list_messages(state="pending")))
            with sqlite3.connect(self.path) as connection:
                connection.execute("CREATE TABLE business(value INTEGER)")

            def failing(connection, notification):
                connection.execute("INSERT INTO business VALUES(6)")
                raise ValueError("transaction failed")

            with self.assertRaises(ValueError):
                app.consume_results(failing)
            with sqlite3.connect(self.path) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM business").fetchone()[0], 0)
            time.sleep(0.02)
            count = app.consume_results(lambda c, n: c.execute(
                "INSERT INTO business VALUES(?)", (n["result"]["value"],)))
            self.assertEqual(count, 1)
            self.assertEqual(app.consume_results(lambda c, n: self.fail("already consumed")), 0)
            with sqlite3.connect(self.path) as connection:
                self.assertEqual(connection.execute("SELECT value FROM business").fetchone()[0], 6)

    def test_unconsumed_results_survive_restart(self):
        app = self.open().start()
        app.submit("double", 4, request_id="inbox").wait()
        wait_for(lambda: bool(app.inbox.list_messages(state="pending")))
        app.close()
        done = threading.Event()
        with self.open(on_result=lambda notification: done.set()):
            self.assertTrue(done.wait(5))

    def test_blocked_callback_has_bounded_retryable_shutdown(self):
        entered = threading.Event()
        release = threading.Event()

        def callback(notification):
            entered.set()
            release.wait(10)

        app = self.open(on_result=callback).start()
        try:
            app.submit("double", 1, request_id="blocked")
            self.assertTrue(entered.wait(5))
            with self.assertRaises(TimeoutError):
                app.close(timeout=0.05)
            self.assertEqual(app.health()["state"], "stopping")
            self.assertTrue(app.health()["consumer_alive"])
        finally:
            release.set()
            app.close(timeout=5)
        self.assertEqual(app.health()["state"], "closed")

    def test_process_default_executes_importable_handler(self):
        with Dispatcher(self.path, {"double": double}) as app:
            self.assertEqual(app.runtime.isolation_mode, "process")
            self.assertEqual(app.submit("double", 5, request_id="process").wait()["value"], 10)

    def test_shutdown_waits_for_transactional_consumer(self):
        app = self.open().start()
        app.submit("double", 4, request_id="sql-blocked").wait()
        wait_for(lambda: bool(app.inbox.list_messages(state="pending")))
        entered = threading.Event()
        release = threading.Event()
        errors = []

        def mutation(connection, notification):
            entered.set()
            release.wait(5)

        def consume():
            try:
                app.consume_results(mutation)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=consume)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                app.close(timeout=0.05)
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertEqual(app.health()["active_consumers"], 1)
        finally:
            release.set()
            thread.join(3)
            app.close()
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_terminal_replay_does_not_require_removed_handler(self):
        with self.open() as app:
            original = app.submit("double", 6, request_id="old").wait()
        with Dispatcher(self.path, {}, isolation_mode="thread") as app:
            self.assertEqual(app.submit("double", 6, request_id="old").wait(), original)
            with self.assertRaises(SubmissionConflictError):
                app.submit("double", 9, request_id="old")

    def test_expired_transaction_lease_preserves_original_failure(self):
        with self.open(callback_lease_seconds=0.2) as app:
            app.submit("double", 1, request_id="expired").wait()
            wait_for(lambda: bool(app.inbox.list_messages(state="pending")))
            app.host.stop()

            def mutation(connection, notification):
                time.sleep(0.3)
                raise ValueError("original mutation failure")

            with self.assertRaisesRegex(ValueError, "original mutation failure"):
                app.consume_results(mutation)
            self.assertEqual(app.consume_results(lambda c, n: None), 1)

    def test_wait_reports_recovery_without_ack(self):
        app = self.open()
        task = app.submit("double", 1, request_id="uncertain")
        app.orchestrator.flush()
        kernel = app.runtime.kernel
        lease = kernel.start(kernel.claim(
            "interrupted-worker", registry_revision=task.snapshot["command"]["registry_revision"],
            lease_seconds=0.1))
        kernel.prepare_effect(lease, effect_id="external-write", name="write", request={"key": 1})
        time.sleep(0.12)
        kernel.reap()
        app.orchestrator.sync()
        with self.assertRaises(RecoveryRequiredError) as error:
            task.wait()
        self.assertEqual(error.exception.request_id, "uncertain")
        self.assertEqual(kernel.get_effect("external-write").state, "indeterminate")


if __name__ == "__main__":
    unittest.main()
