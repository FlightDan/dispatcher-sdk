"""Real writer admission preserves delivery bodies, clocks, and profiles."""
from contextlib import closing, contextmanager
import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.durability import configure_sqlite_connection
from dispatcher_sdk.execution_kernel import ExecutionResultV2, StaleFenceError
from dispatcher_sdk.orchestrator.inbox import NotificationInbox
from dispatcher_sdk.orchestrator.results import ResultsMixin
from dispatcher_sdk.orchestrator.store import StoreMixin
from tests._acceptance_evidence import retained_directory


class _Clock:
    def __init__(self):
        self.value = 100.0
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


class _AdmissionConnections:
    def _connect(self, *args, **kwargs):
        connection = super()._connect(*args, **kwargs)
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")

        def trace(statement):
            if statement == "BEGIN IMMEDIATE":
                self.begins.append(time.monotonic())
                self.begin_seen.set()

        connection.set_trace_callback(trace)
        return connection

    def reset_admission(self):
        self.begins.clear()
        self.begin_seen.clear()
        self.clock.calls = 0


class _Store(_AdmissionConnections, StoreMixin):
    def __init__(self, path, *, durability="full", busy_timeout_ms=100):
        self.db_path = str(path)
        self.durability = durability
        self.busy_timeout_ms = busy_timeout_ms
        self.begins = []
        self.begin_seen = threading.Event()
        self.clock = _Clock()
        self.failpoints = []
        with closing(self._connect()) as connection:
            connection.execute("CREATE TABLE application_values(value INTEGER NOT NULL)")
            connection.commit()

    def _failpoint(self, stage):
        self.failpoints.append(stage)


class _Results(_Store, ResultsMixin):
    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
        with closing(self._connect()) as connection:
            self._init_results(connection)
            connection.commit()

    def seed_result(self):
        result = ExecutionResultV2(result_id="result", execution_id="task", status="succeeded",
            attempt=1, fence=1, effect_ids=[], started_at=100, completed_at=100,
            correlation_id="run", causation_id=None, value={"answer": 42}, error=None)
        with closing(self._connect()) as connection:
            connection.execute("INSERT INTO sdk_results(result_id,execution_id,result_json,"
                "kernel_revision,state,max_attempts,next_attempt_at,created_at,updated_at) "
                "VALUES(?,?,?,1,'pending',5,100,100,100)",
                (result.result_id, result.execution_id, json.dumps(result.to_dict())))
            connection.commit()


class _Inbox(_AdmissionConnections, NotificationInbox):
    def __init__(self, path, *, durability="full", busy_timeout_ms=100):
        self.busy_timeout_ms = busy_timeout_ms
        self.begins = []
        self.begin_seen = threading.Event()
        clock = _Clock()
        super().__init__(path, durability=durability, clock=clock)
        with closing(self._connect()) as connection:
            connection.execute("CREATE TABLE application_values(value INTEGER NOT NULL)")


class NotificationWriterAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-notification-writer-admission-")
        self.records = []

    def tearDown(self):
        path = self.root / "evidence.json"
        path.write_text(json.dumps({"test": self.id(), "records": self.records}, indent=2),
            encoding="utf-8")
        print("notification_writer_admission_evidence=" + str(path), flush=True)

    def client(self, kind, *, profile="full", timeout_ms=100):
        cls = {"store": _Store, "results": _Results, "inbox": _Inbox}[kind]
        client = cls(self.root / f"{kind}-{profile}-{timeout_ms}.sqlite3",
            durability=profile, busy_timeout_ms=timeout_ms)
        client.reset_admission()
        return client

    @staticmethod
    @contextmanager
    def transaction(client, kind):
        if kind == "store":
            with client._transaction() as connection:
                yield connection
        else:
            operation = client._results_transaction if kind == "results" else client._transaction
            with operation() as (connection, _):
                yield connection

    @staticmethod
    def writer(client):
        connection = sqlite3.connect(client.db_path, timeout=0, isolation_level=None,
            check_same_thread=False)
        connection.execute("BEGIN IMMEDIATE")
        return connection

    @staticmethod
    def values(client):
        with closing(sqlite3.connect(client.db_path)) as reader:
            return reader.execute("SELECT value FROM application_values").fetchall()

    @staticmethod
    def clock_value(client, kind):
        table = "sdk_result_clock" if kind == "results" else "notification_inbox_clock"
        with closing(sqlite3.connect(client.db_path)) as reader:
            return reader.execute(f"SELECT value FROM {table} WHERE id=1").fetchone()[0]

    def release_after_begin(self, client, writer, *, before_release=None):
        errors = []
        observations = []

        def release():
            try:
                if not client.begin_seen.wait(1):
                    raise AssertionError("transaction did not attempt BEGIN")
                time.sleep(.02)
                observations.append({"clock_calls_before_release": client.clock.calls,
                    "values_before_release": self.values(client)})
                if before_release is not None:
                    before_release()
            except BaseException as error:
                errors.append(repr(error))
            finally:
                writer.rollback()

        thread = threading.Thread(target=release)
        thread.start()
        return thread, errors, observations

    def assert_busy(self, error):
        self.assertEqual("database is locked", str(error))
        if hasattr(error, "sqlite_errorcode"):
            self.assertEqual(sqlite3.SQLITE_BUSY, error.sqlite_errorcode & 255)

    def faulty_connection(self, client, *, fault):
        facts = {"begin_calls": 0, "rollback_calls": 0, "closed": False}
        restoration_error = sqlite3.OperationalError("injected busy policy restoration failure")

        class Connection(sqlite3.Connection):
            armed = False

            def execute(self, sql, parameters=()):
                if sql == "PRAGMA busy_timeout=0":
                    self.armed = True
                if sql == "BEGIN IMMEDIATE":
                    facts["begin_calls"] += 1
                    if fault == "permanent_begin":
                        try:
                            super().execute("SELECT * FROM missing_notification_admission_table")
                        except sqlite3.OperationalError as error:
                            facts["original_error"] = error
                            raise
                if self.armed and sql == "PRAGMA busy_timeout=100" and fault == "restore":
                    facts["transaction_before_restore_failure"] = self.in_transaction
                    raise restoration_error
                return super().execute(sql, parameters)

            def rollback(self):
                facts["rollback_calls"] += 1
                return super().rollback()

            def close(self):
                if facts["closed"]:
                    return
                facts["transaction_before_close"] = self.in_transaction
                super().close()
                facts["closed"] = True

        connection = sqlite3.connect(client.db_path, timeout=.1, factory=Connection)
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        configure_sqlite_connection(connection, client.db_path, durability=client.durability)
        connection.execute("PRAGMA busy_timeout=100")
        return connection, facts, restoration_error

    def test_writer_release_admits_each_original_transaction_body_once_and_restores_profile(self):
        for kind in ("store", "results", "inbox"):
            for profile, synchronous in (("full", 2), ("normal", 1)):
                with self.subTest(kind=kind, profile=profile):
                    client = self.client(kind, profile=profile)
                    writer = self.writer(client)
                    thread, errors, observations = self.release_after_begin(client, writer)
                    body_calls = []
                    started = time.monotonic()
                    try:
                        with self.transaction(client, kind) as connection:
                            body_calls.append(time.monotonic())
                            self.assertEqual(100, connection.execute("PRAGMA busy_timeout").fetchone()[0])
                            self.assertEqual("wal", connection.execute("PRAGMA journal_mode").fetchone()[0])
                            self.assertEqual(synchronous, connection.execute("PRAGMA synchronous").fetchone()[0])
                            connection.execute("INSERT INTO application_values VALUES(1)")
                    finally:
                        thread.join(1)
                        writer.close()
                    elapsed = time.monotonic() - started
                    self.assertFalse(thread.is_alive())
                    self.assertEqual([], errors)
                    self.assertEqual([{"clock_calls_before_release": 0, "values_before_release": []}], observations)
                    self.assertEqual(1, len(body_calls))
                    self.assertGreater(len(client.begins), 1)
                    self.assertEqual(0 if kind == "store" else 1, client.clock.calls)
                    self.assertEqual([(1,)], self.values(client))
                    if kind == "store":
                        self.assertEqual(["before_commit"], client.failpoints)
                    self.records.append({"scenario": "writer_released", "kind": kind,
                        "profile": profile, "original_timeout_ms": 100, "elapsed": elapsed,
                        "begin_attempts": len(client.begins), "body_calls": len(body_calls),
                        "clock_calls": client.clock.calls, "before_release": observations})

    def test_held_writer_exhausts_configured_allowance_without_body_or_clock_observation(self):
        for kind in ("store", "results", "inbox"):
            with self.subTest(kind=kind):
                client = self.client(kind)
                writer = self.writer(client)
                bodies = []
                started = time.monotonic()
                try:
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        with self.transaction(client, kind) as connection:
                            bodies.append(True)
                            connection.execute("INSERT INTO application_values VALUES(1)")
                    elapsed = time.monotonic() - started
                finally:
                    writer.rollback()
                    writer.close()
                self.assert_busy(caught.exception)
                self.assertGreaterEqual(elapsed, .08)
                self.assertLess(elapsed, .5)
                self.assertGreater(len(client.begins), 1)
                self.assertEqual([], bodies)
                self.assertEqual(0, client.clock.calls)
                self.assertEqual([], self.values(client))
                if kind != "store":
                    self.assertEqual(0, self.clock_value(client, kind))
                self.records.append({"scenario": "writer_held", "kind": kind,
                    "original_timeout_ms": 100, "elapsed": elapsed,
                    "begin_attempts": len(client.begins), "error": str(caught.exception)})

    def test_zero_timeout_keeps_one_immediate_begin_attempt(self):
        for kind in ("store", "results", "inbox"):
            with self.subTest(kind=kind):
                client = self.client(kind, timeout_ms=0)
                writer = self.writer(client)
                started = time.monotonic()
                try:
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        with self.transaction(client, kind):
                            self.fail("zero-timeout writer contention entered the body")
                    elapsed = time.monotonic() - started
                finally:
                    writer.rollback()
                    writer.close()
                self.assert_busy(caught.exception)
                self.assertEqual(1, len(client.begins))
                self.assertEqual(0, client.clock.calls)
                self.assertLess(elapsed, .5)
                with self.transaction(client, kind) as connection:
                    self.assertEqual(0, connection.execute("PRAGMA busy_timeout").fetchone()[0])
                    connection.execute("INSERT INTO application_values VALUES(1)")
                self.assertEqual([(1,)], self.values(client))
                self.records.append({"scenario": "zero_timeout", "kind": kind, "elapsed": elapsed})

    def test_body_failure_is_not_replayed_and_delivery_clock_floor_survives_rollback(self):
        for kind in ("store", "results", "inbox"):
            with self.subTest(kind=kind):
                client = self.client(kind)
                client.clock.value = 200
                original = RuntimeError("original transaction body failure")
                bodies = []
                with self.assertRaises(RuntimeError) as caught:
                    with self.transaction(client, kind) as connection:
                        bodies.append(True)
                        connection.execute("INSERT INTO application_values VALUES(1)")
                        raise original
                self.assertIs(original, caught.exception)
                self.assertEqual([True], bodies)
                self.assertEqual(1, len(client.begins))
                self.assertEqual([], self.values(client))
                if kind != "store":
                    self.assertEqual(1, client.clock.calls)
                    self.assertEqual(200, self.clock_value(client, kind))
                self.records.append({"scenario": "body_rollback", "kind": kind,
                    "clock_calls": client.clock.calls, "original_error_preserved": True})

    def test_restore_failure_after_actual_begin_rolls_back_and_closes_without_entering_body(self):
        for kind in ("store", "results", "inbox"):
            with self.subTest(kind=kind):
                client = self.client(kind)
                connection, facts, original = self.faulty_connection(client, fault="restore")
                with patch.object(client, "_connect", return_value=connection):
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        with self.transaction(client, kind):
                            self.fail("failed timeout restoration entered the body")
                self.assertIs(original, caught.exception)
                self.assertTrue(facts["transaction_before_restore_failure"])
                self.assertEqual(1, facts["begin_calls"])
                self.assertEqual(1, facts["rollback_calls"])
                self.assertTrue(facts["closed"])
                self.assertFalse(facts["transaction_before_close"])
                self.assertEqual(0, client.clock.calls)
                with closing(self.writer(client)) as writer:
                    writer.rollback()
                self.records.append({"scenario": "restore_failure", "kind": kind,
                    "begin_calls": facts["begin_calls"], "closed": facts["closed"],
                    "rolled_back": not facts["transaction_before_close"]})

    def test_permanent_begin_error_is_preserved_without_retry_or_clock_observation(self):
        for kind in ("store", "results", "inbox"):
            with self.subTest(kind=kind):
                client = self.client(kind)
                connection, facts, _ = self.faulty_connection(client, fault="permanent_begin")
                with patch.object(client, "_connect", return_value=connection):
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        with self.transaction(client, kind):
                            self.fail("permanent BEGIN failure entered the body")
                self.assertIs(facts["original_error"], caught.exception)
                self.assertIn("no such table", str(caught.exception))
                self.assertEqual(1, facts["begin_calls"])
                self.assertEqual(0, client.clock.calls)
                self.assertTrue(facts["closed"])
                self.assertFalse(facts["transaction_before_close"])
                self.records.append({"scenario": "permanent_begin_error", "kind": kind,
                    "begin_calls": facts["begin_calls"], "error": str(caught.exception)})

    def test_writer_delayed_result_ack_and_inbox_consume_cannot_revive_expired_lease(self):
        for kind in ("results", "inbox"):
            with self.subTest(kind=kind):
                client = self.client(kind)
                mutations = []
                if kind == "results":
                    client.seed_result()
                    claim = client.claim_results(owner="owner", lease_seconds=1, limit=1)[0]
                    expired = claim["lease_until"]

                    def operation():
                        return client.acknowledge_result(claim["result"]["result_id"],
                            lease_id=claim["lease_id"], fence=claim["fence"])
                else:
                    client.accept("source", {"notification_id": "notice"})
                    lease = client.claim("owner", lease_seconds=1)
                    expired = lease.expires_at

                    def mutation(connection, payload):
                        mutations.append(True)
                        connection.execute("INSERT INTO application_values VALUES(1)")

                    def operation():
                        return client.consume(lease, mutation)

                client.reset_admission()
                writer = self.writer(client)

                def expire():
                    client.clock.value = expired + 1

                thread, errors, observations = self.release_after_begin(client, writer,
                    before_release=expire)
                try:
                    with self.assertRaises(StaleFenceError):
                        operation()
                finally:
                    thread.join(1)
                    writer.close()
                self.assertFalse(thread.is_alive())
                self.assertEqual([], errors)
                self.assertEqual(0, observations[0]["clock_calls_before_release"])
                self.assertGreater(len(client.begins), 1)
                self.assertEqual(expired + 1, self.clock_value(client, kind))
                client.clock.value = 100
                with self.assertRaises(StaleFenceError):
                    operation()
                self.assertEqual(expired + 1, self.clock_value(client, kind))
                self.assertEqual([], mutations)
                self.assertEqual([], self.values(client))
                self.records.append({"scenario": "writer_delayed_expiry", "kind": kind,
                    "lease_expires_at": expired, "durable_clock": self.clock_value(client, kind),
                    "mutation_calls": len(mutations)})


if __name__ == "__main__":
    unittest.main()
