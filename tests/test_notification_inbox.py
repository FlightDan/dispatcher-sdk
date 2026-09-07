"""Persistence, fencing, replay, and local SQL atomicity for the inbox."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy, StaleFenceError
from dispatcher_sdk.orchestrator import CommandConflict, Orchestrator
from dispatcher_sdk.orchestrator.inbox import NotificationInbox, validate_inbox_schema


class _Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


def _crash_during_consume(path, lease):
    inbox = NotificationInbox(path, clock=lambda: 100.0)

    def mutation(connection, payload):
        connection.execute("INSERT INTO application_values VALUES('applied',1)")
        os._exit(23)

    inbox.consume(lease, mutation)


def _echo(payload, context):
    return payload


class NotificationInboxTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "application.sqlite3"
        self.clock = _Clock()
        self.inbox = NotificationInbox(self.path, clock=self.clock)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TABLE application_values (name TEXT PRIMARY KEY, value INTEGER NOT NULL)")

    def receive(self, *, source="source", identity="notice", maximum=5):
        return self.inbox.accept(source, {"notification_id": identity, "value": 1}, max_attempts=maximum)

    def values(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute("SELECT name,value FROM application_values ORDER BY name").fetchall()

    @staticmethod
    def increment(connection, payload):
        connection.execute("INSERT INTO application_values VALUES('applied',1) "
                           "ON CONFLICT(name) DO UPDATE SET value=value+1")

    def test_default_full_and_opt_in_normal_apply_to_operation_connections(self):
        for profile, synchronous in (("full", 2), ("normal", 1)):
            inbox = NotificationInbox(self.path, durability=profile)
            with closing(inbox._connect()) as connection:
                self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], synchronous)
        with self.assertRaises(ValueError):
            NotificationInbox(":memory:")
        invalid_path = self.root / "invalid.sqlite3"
        with self.assertRaises(ValueError):
            NotificationInbox(invalid_path, durability="off")
        self.assertFalse(invalid_path.exists())

    def test_schema_validator_accepts_a_read_only_connection(self):
        self.receive()
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            validate_inbox_schema(connection)
            self.assertEqual(connection.total_changes, 0)
            self.assertEqual(connection.execute(
                "SELECT component,version FROM notification_inbox_meta").fetchall(),
                [("notification_inbox", 1)])
        self.assertEqual(NotificationInbox(self.path, clock=self.clock).get("source", "notice")["state"], "pending")

    def test_existing_incompatible_schema_is_rejected_without_repair(self):
        changes = (
            "DROP TABLE notification_inbox_meta",
            "DROP TABLE notification_inbox_messages",
            "DROP INDEX notification_inbox_pending",
            "ALTER TABLE notification_inbox_messages RENAME COLUMN settlement TO old_settlement",
            "DELETE FROM notification_inbox_meta",
            "UPDATE notification_inbox_meta SET version=2",
            "DELETE FROM notification_inbox_clock",
            "UPDATE notification_inbox_clock SET value=-1",
        )
        for index, change in enumerate(changes):
            with self.subTest(change=change):
                path = self.root / f"incompatible-{index}.sqlite3"
                NotificationInbox(path, clock=self.clock).accept("source", {"notification_id": "notice"})
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute("PRAGMA ignore_check_constraints=ON")
                    connection.execute(change)
                    connection.commit()
                    before = tuple(connection.iterdump())
                with self.assertRaises(ValueError):
                    NotificationInbox(path, clock=self.clock)
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(tuple(connection.iterdump()), before)
                    with self.assertRaises(ValueError):
                        validate_inbox_schema(connection)

    def test_unrelated_application_schema_does_not_prevent_inbox_initialization(self):
        path = self.root / "application-first.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE application_data(value TEXT)")
            connection.execute("INSERT INTO application_data VALUES('preserved')")
            connection.commit()
        inbox = NotificationInbox(path, clock=self.clock)
        inbox.accept("source", {"notification_id": "notice"})
        with closing(sqlite3.connect(path)) as connection:
            validate_inbox_schema(connection)
            self.assertEqual(connection.execute("SELECT value FROM application_data").fetchone(), ("preserved",))

    def test_source_scoped_identity_and_detached_payload(self):
        payload = {"notification_id": "same", "items": [1]}
        accepted = self.inbox.accept("one", payload)
        self.inbox.accept("two", {"notification_id": "same", "items": [2]})
        payload["items"].append(99)
        accepted["payload"]["items"].append(88)
        self.assertEqual(self.inbox.get("one", "same")["payload"]["items"], [1])
        self.assertEqual(len(self.inbox.list_messages()), 2)
        self.assertEqual(self.inbox.claim("worker", source_id="two").payload["items"], [2])

    def test_explicit_identity_accepts_other_json_and_rejects_conflicting_embedded_identity(self):
        self.assertEqual(self.inbox.accept("source", [1, {"x": 2}], notification_id="array")["payload"], [1, {"x": 2}])
        with self.assertRaises(ValueError):
            self.inbox.accept("source", {"notification_id": "one"}, notification_id="two")
        with self.assertRaises(ValueError):
            self.inbox.accept("source", [1])
        with self.assertRaises(ValueError):
            self.inbox.accept("source", {"notification_id": "invalid", "value": float("nan")})

    def test_replay_never_resets_processing_or_consumed_state(self):
        self.receive()
        lease = self.inbox.claim("worker")
        processing = self.inbox.get("source", "notice")
        self.assertEqual(self.inbox.accept("source", {"value": 1, "notification_id": "notice"}, max_attempts=99), processing)
        consumed = self.inbox.consume(lease, self.increment)
        reopened = NotificationInbox(self.path, clock=self.clock)
        self.assertEqual(reopened.accept("source", {"notification_id": "notice", "value": 1}), consumed)
        self.assertEqual(reopened.consume(lease, self.increment), consumed)
        self.assertIsNone(reopened.claim("another"))
        self.assertEqual(self.values(), [("applied", 1)])

    def test_same_identity_different_payload_conflicts_before_and_after_consumption(self):
        self.receive()
        for consumed in (False, True):
            if consumed:
                self.inbox.consume(self.inbox.claim("worker"))
            with self.assertRaises(CommandConflict):
                self.inbox.accept("source", {"notification_id": "notice", "value": 2})
            self.assertEqual(self.inbox.get("source", "notice")["payload"]["value"], 1)

    def test_sql_failure_rolls_back_business_writes_and_consumed_marker(self):
        self.receive()
        lease = self.inbox.claim("worker")

        def fail(connection, payload):
            self.increment(connection, payload)
            raise RuntimeError("application failed")

        with self.assertRaisesRegex(RuntimeError, "application failed"):
            self.inbox.consume(lease, fail)
        self.assertEqual(self.values(), [])
        self.assertEqual(self.inbox.get("source", "notice")["state"], "processing")
        self.inbox.consume(lease, self.increment)
        self.assertEqual(self.values(), [("applied", 1)])

    def test_mutation_reads_durable_payload_not_the_callers_lease_copy(self):
        self.receive()
        lease = self.inbox.claim("worker")
        lease.payload["value"] = 999
        self.inbox.consume(lease, lambda connection, payload: connection.execute(
            "INSERT INTO application_values VALUES('payload',?)", (payload["value"],)))
        self.assertEqual(self.values(), [("payload", 1)])

    def test_expired_worker_cannot_run_mutation_or_fail_a_reclaimed_message(self):
        self.receive()
        old = self.inbox.claim("old", lease_seconds=1)
        self.clock.value = 101
        fresh = self.inbox.claim("new")
        self.assertEqual((fresh.attempt, fresh.fence), (2, old.fence + 1))
        with self.assertRaises(StaleFenceError):
            self.inbox.consume(old, self.increment)
        with self.assertRaises(StaleFenceError):
            self.inbox.fail(old, error={"message": "late"})
        self.assertEqual(self.values(), [])
        self.inbox.consume(fresh, self.increment)
        self.assertEqual(self.values(), [("applied", 1)])

    def test_expiry_during_mutation_rolls_back_and_backwards_clock_cannot_revive_lease(self):
        self.receive()
        lease = self.inbox.claim("worker", lease_seconds=1)

        def too_slow(connection, payload):
            self.increment(connection, payload)
            self.clock.value = lease.expires_at

        with self.assertRaises(StaleFenceError):
            self.inbox.consume(lease, too_slow)
        self.assertEqual(self.values(), [])
        self.clock.value = 1
        with self.assertRaises(StaleFenceError):
            self.inbox.consume(lease, self.increment)
        fresh = self.inbox.claim("fresh", lease_seconds=1)
        self.assertEqual(fresh.expires_at, lease.expires_at + 1)
        self.assertGreater(fresh.fence, lease.fence)

    def test_waiting_for_sqlite_writer_lock_cannot_preserve_an_expired_lease(self):
        self.receive()
        lease = self.inbox.claim("worker", lease_seconds=1)
        entered = threading.Event()

        class TracedInbox(NotificationInbox):
            def _connect(self):
                connection = super()._connect()
                connection.set_trace_callback(lambda statement: entered.set()
                                              if statement == "BEGIN IMMEDIATE" else None)
                return connection

        inbox = TracedInbox(self.path, clock=self.clock)
        entered.clear()
        with closing(sqlite3.connect(self.path, isolation_level=None)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            with ThreadPoolExecutor(max_workers=1) as pool:
                waiting = pool.submit(inbox.consume, lease, self.increment)
                try:
                    self.assertTrue(entered.wait(5))
                    self.clock.value = lease.expires_at
                finally:
                    blocker.commit()
                with self.assertRaises(StaleFenceError):
                    waiting.result(timeout=5)
        self.assertEqual(self.values(), [])

    def test_failure_receipt_delay_dead_letter_and_explicit_retry_keep_fences(self):
        self.receive(maximum=2)
        first = self.inbox.claim("worker")
        failure = self.inbox.fail(first, error={"message": "retry"}, retry_delay=2)
        self.assertEqual(self.inbox.fail(first, error={"message": "retry"}, retry_delay=2), failure)
        with self.assertRaises(CommandConflict):
            self.inbox.fail(first, error={"message": "different"}, retry_delay=2)
        self.clock.value = 101
        self.assertIsNone(self.inbox.claim("worker"))
        self.clock.value = 102
        second = self.inbox.claim("worker")
        dead = self.inbox.fail(second, error={"message": "stop"}, retry_delay=0)
        self.assertEqual(dead["state"], "dead")
        self.assertIsNone(self.inbox.claim("worker"))
        with self.assertRaises(StaleFenceError):
            self.inbox.retry_dead("source", "notice", expected_revision=dead["revision"] - 1)
        self.inbox.retry_dead("source", "notice", expected_revision=dead["revision"])
        third = self.inbox.claim("worker")
        self.assertEqual(third.attempt, 1)
        self.assertGreater(third.fence, second.fence)
        with self.assertRaises(StaleFenceError):
            self.inbox.consume(second)
        self.inbox.consume(third)

    def test_expired_last_attempt_becomes_dead_without_redelivery(self):
        self.receive(maximum=1)
        lease = self.inbox.claim("worker", lease_seconds=1)
        self.clock.value = lease.expires_at
        self.assertIsNone(self.inbox.claim("worker"))
        dead = self.inbox.get("source", "notice")
        self.assertEqual(dead["state"], "dead")
        self.assertEqual(dead["last_error"]["type"], "LeaseExpired")

    def test_transaction_control_and_inbox_mutation_are_rejected_atomically(self):
        self.receive()
        lease = self.inbox.claim("worker")
        forbidden = (
            lambda connection: connection.commit(),
            lambda connection: connection.rollback(),
            lambda connection: connection.executescript("INSERT INTO application_values VALUES('escaped',1);"),
            lambda connection: connection.execute("UPDATE main.notification_inbox_clock SET value=? WHERE id=1", (0,)),
            lambda connection: connection.execute("UPDATE notification_inbox_messages SET state='consumed'"),
            lambda connection: connection.execute("CREATE TEMP TABLE NOTIFICATION_INBOX_MESSAGES (source_id TEXT)"),
            lambda connection: connection.execute("ATTACH DATABASE ':memory:' AS other"),
        )
        for operation in forbidden:
            def mutation(connection, payload):
                self.increment(connection, payload)
                operation(connection)

            with self.subTest(operation=operation), self.assertRaises(sqlite3.DatabaseError):
                self.inbox.consume(lease, mutation)
            self.assertEqual(self.values(), [])
            self.assertEqual(self.inbox.get("source", "notice")["state"], "processing")
        self.inbox.consume(lease, self.increment)

    def test_async_mutation_is_not_marked_consumed(self):
        self.receive()
        lease = self.inbox.claim("worker")

        async def mutation(connection, payload):
            self.increment(connection, payload)

        with self.assertRaisesRegex(TypeError, "synchronous"):
            self.inbox.consume(lease, mutation)
        self.assertEqual(self.values(), [])
        self.assertEqual(self.inbox.get("source", "notice")["state"], "processing")

    def test_concurrent_receivers_retain_one_receipt_and_reject_conflicts(self):
        barrier = threading.Barrier(2)

        def accept(value):
            inbox = NotificationInbox(self.path, clock=self.clock)
            barrier.wait(timeout=5)
            try:
                inbox.accept("source", {"notification_id": "notice", "value": value})
                return True
            except CommandConflict:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(accept, (1, 2))), 1)
        self.assertEqual(len(self.inbox.list_messages()), 1)

    def test_concurrent_claims_and_completed_replays_mutate_business_once(self):
        self.receive()
        barrier = threading.Barrier(2)

        def claim(owner):
            inbox = NotificationInbox(self.path, clock=self.clock)
            barrier.wait(timeout=5)
            return inbox.claim(owner)

        with ThreadPoolExecutor(max_workers=2) as pool:
            leases = [lease for lease in pool.map(claim, ("one", "two")) if lease is not None]
        self.assertEqual(len(leases), 1)
        barrier = threading.Barrier(2)

        def consume(_):
            inbox = NotificationInbox(self.path, clock=self.clock)
            barrier.wait(timeout=5)
            return inbox.consume(leases[0], self.increment)

        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(consume, (1, 2)))
        self.assertEqual(records[0], records[1])
        self.assertEqual(self.values(), [("applied", 1)])

    def test_process_crash_rolls_back_business_sql_and_reclaim_is_safe(self):
        self.receive()
        lease = self.inbox.claim("crashing", lease_seconds=1)
        process = multiprocessing.get_context("spawn").Process(
            target=_crash_during_consume, args=(self.path, lease))
        process.start()
        process.join(10)
        try:
            self.assertEqual(process.exitcode, 23)
        finally:
            if process.is_alive():
                process.kill()
                process.join(3)
            process.close()
        self.assertEqual(self.values(), [])
        self.clock.value = lease.expires_at
        fresh = NotificationInbox(self.path, clock=self.clock).claim("replacement")
        self.inbox.consume(fresh, self.increment)
        self.assertEqual(self.values(), [("applied", 1)])

    def test_upstream_crash_after_acceptance_replays_without_reprocessing(self):
        kernel_path = self.root / "origin.sqlite3"
        with Kernel.open_sqlite(kernel_path, {"echo": _echo}, isolation_mode="thread", now=self.clock) as runtime:
            sdk = Orchestrator(kernel_path, runtime.kernel, runtime=runtime, clock=self.clock)
            sdk.create_run("run", command_id="create")
            command = ExecutionCommandV2(
                execution_id="exec", idempotency_key="exec", registry_revision=runtime.registry_revision,
                correlation_id="run", causation_id=None, handler_id="echo", handler_contract_version=1,
                retry_policy=RetryPolicy(), timeout_seconds=2, payload={"value": 1},
            )
            sdk.apply_operations("run", command_id="schedule", expected_revision=0, operations=[
                {"kind": "add_task", "task_id": "task", "command": command.to_dict()},
                {"kind": "watch_task", "task_id": "task", "watch_id": "watch", "target": "application"},
                {"kind": "dispatch", "task_id": "task"},
            ])
            sdk.flush()
            runtime.run_once()
            sdk.collect_notifications()

            def crash(name):
                if name == "after_notification_callback":
                    raise RuntimeError("origin crashed after receipt")

            callback = lambda payload: self.inbox.accept("origin-instance", payload)
            sdk._failpoint = crash
            with self.assertRaisesRegex(RuntimeError, "origin crashed"):
                sdk.deliver_notifications(callback, owner="delivery", lease_seconds=1)
            lease = self.inbox.claim("application")
            self.inbox.consume(lease, self.increment)
            self.clock.value += 1
            sdk._failpoint = lambda name: None
            self.assertEqual(sdk.deliver_notifications(callback, owner="delivery"), 1)
            self.assertIsNone(self.inbox.claim("application"))
            self.assertEqual(self.values(), [("applied", 1)])


if __name__ == "__main__":
    unittest.main()
