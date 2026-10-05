"""Completion readers follow real Context close and physical SQLite release."""
from contextlib import contextmanager
import json
import math
import sqlite3
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dispatcher_sdk import storage_connection
from dispatcher_sdk._inspection import InspectionBudgetExceeded
from dispatcher_sdk.execution_kernel import completion_clock as clock_module
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError
from dispatcher_sdk.execution_kernel.completion_clock import capture_completion_time
from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.runtime import Runtime, _ObservationCleanupPendingError
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory
from tests._storage_evidence import StorageEvidence


class CompletionReaderLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-completion-reader-lifetime-")
        self.evidence = {"test": self.id(), "records": []}
        self.storage = StorageEvidence(self.root, self)
        self.storage.start(include_kernel=True)
        self.addCleanup(self.storage.stop)
        self.addCleanup(self.storage.save)
        self._contexts = 0

    def tearDown(self):
        path = self.root / "evidence.json"
        path.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
        print("completion_reader_lifetime_evidence=" + str(path), flush=True)

    @staticmethod
    def raw(error):
        return {"type": type(error).__name__, "message": str(error),
                "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                "cause": None if error.__cause__ is None else {
                    "type": type(error.__cause__).__name__, "message": str(error.__cause__)}}

    @contextmanager
    def actual_context(self, *, control_timeout=None):
        self._contexts += 1
        wall_calls = []
        phase = ["setup"]

        def now():
            if phase[0] == "capture":
                wall_calls.append({"thread": threading.current_thread().name, "at": time.monotonic()})
            return time.time()

        kernel = SQLiteKernel(self.root / ("context-" + str(self._contexts) + ".sqlite3"),
                              now=now, control_timeout_seconds=control_timeout)
        command = ExecutionCommandV2("original", "original", "reader-proof", "reader-proof",
                                     None, "work", 1, RetryPolicy(), 10, {})
        kernel.submit(command)
        lease = kernel.claim_and_start("owner", execution_id="original")
        envelope = kernel.prepare_execution_budget(lease).enter_handler(10, origin_id="execution:original")
        envelope = kernel.confirm_handler_entry(lease, envelope)
        context = HandlerContext(command, lease, HandlerEffects(kernel, lease, lambda: True),
                                 budget_envelope=envelope, service_spec={"guard_budget": True})
        state = SimpleNamespace(kernel=kernel, context=context, phase=phase, wall_calls=wall_calls)
        try:
            yield state
        finally:
            context.close()
            self.assertFalse(context._drain_completion_readers(time.monotonic() + 1),
                             "fixture left a completion reader reservation")
            kernel.close()

    @contextmanager
    def timed_out_runtime(self):
        entered, release, finished, wrapper_finished = (threading.Event() for _ in range(4))
        contexts, outcomes, errors, wall_calls, captures = [], [], [], [], []
        wall = [time.time()]
        capturing = threading.local()
        handler_state = SimpleNamespace(contexts=contexts)

        def now():
            if getattr(capturing, "active", False):
                wall_calls.append({"thread": threading.current_thread().name, "at": time.monotonic()})
            return wall[0]

        def blocked(payload, context):
            handler_state.contexts.append(context)
            entered.set()
            release.wait()
            finished.set()
            return {"late_business": True}

        blocked.__execution_kernel_revision__ = "completion-reader-lifetime-v1"
        runtime = Runtime(str(self.root / "runtime.sqlite3"), {"work": blocked},
                          isolation_mode="thread", max_thread_workers=1, now=now)
        thread_finished = runtime._thread_finished
        capture = runtime_module._capture_completion_time

        def observed_finished(authority, generation, **options):
            try:
                return thread_finished(authority, generation, **options)
            finally:
                if generation[0] == "original":
                    wrapper_finished.set()

        def observed_capture(outcome, context):
            capturing.active = True
            try:
                return capture(outcome, context)
            finally:
                captures.append({key: outcome[key] for key in
                                 ("completed_at", "completion_time_known", "completion_time_error") if key in outcome})
                capturing.active = False

        runtime._thread_finished = observed_finished
        for execution_id in ("original", "queued"):
            runtime.submit(runtime.command("work", execution_id=execution_id,
                idempotency_key=execution_id, correlation_id="reader-lifetime", timeout_seconds=5, payload={}))

        def drive():
            try:
                outcomes.append(runtime.run_once(execution_id="original"))
            except BaseException as error:
                errors.append(error)

        driver = threading.Thread(target=drive, name="completion-reader-driver")
        with patch.object(runtime_module, "_capture_completion_time", side_effect=observed_capture):
            try:
                driver.start()
                self.assertTrue(entered.wait(2))
                wall[0] += 6
                driver.join(2)
                self.assertFalse(driver.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(outcomes), 1)
                self.assertEqual(outcomes[0].state, "timed_out")
                self.assertIsNone(runtime.run_once())
                self.assertEqual(runtime.kernel.get("queued").state, "queued")
                self.assertFalse(runtime._thread_slots.acquire(blocking=False))
                state = SimpleNamespace(runtime=runtime, context=contexts[0], release=release,
                    finished=finished, wrapper_finished=wrapper_finished, original=outcomes[0],
                    wall_calls=wall_calls, captures=captures)
                yield state
            finally:
                release.set()
                driver.join(2)
                if contexts:
                    self.assertTrue(wrapper_finished.wait(1), "actual invocation wrapper did not finish")
                runtime.close()
                self.evidence["records"].append({"runtime_wall_samples": wall_calls,
                    "completion_receipts": captures, "outcomes": [item.to_dict() for item in outcomes],
                    "driver_errors": [self.raw(error) for error in errors],
                    "cleanup_report": runtime._observation_cleanup_report})

    def assert_original_persisted(self, state):
        with SQLiteKernel(state.runtime.kernel.db_path) as reader:
            self.assertEqual(reader.get("original").to_dict(), state.original.to_dict())
            self.assertEqual(reader.get("queued").state, "queued")

    def reader_retry_boundary(self):
        with self.storage._lock:
            return self.storage.operations

    def assert_reader_retry_has_no_sql(self, connection, boundary, sample_calls, samples_before):
        with self.storage._lock:
            operations = self.storage.operations
            retained = tuple(self.storage.events)
        appended = operations - boundary
        self.assertLessEqual(appended, len(retained), "retry operation evidence was truncated")
        # Adjacent stages may share a Windows clock tick. Append order proves
        # which operations belong to this retry without including its body.
        events = [dict(event) for event in (retained[-appended:] if appended else ())
                  if event["connection"] == connection.evidence_id]
        self.assertEqual([event for event in events if event["operation"] != "close"], [],
                         "physical-release retry executed work on the retained reader")
        self.assertEqual(len(sample_calls), samples_before, "physical-release retry took another completion sample")
        self.evidence["records"].append({"phase": "reader_physical_release_retry",
            "exact_reader_connection": connection.evidence_id, "operations": events,
            "operation_boundary": boundary, "operations_after_retry": operations,
            "completion_samples_before": samples_before, "completion_samples_after": len(sample_calls)})
        return events

    def test_successful_close_refuses_late_reader_without_wall_sample_or_wal_recreation(self):
        factory = clock_module._connect_readonly
        opens = []

        def opened(*args, **options):
            connection = factory(*args, **options)
            opens.append(connection)
            return connection

        with self.timed_out_runtime() as state, patch.object(clock_module, "_connect_readonly", side_effect=opened):
            state.runtime.close()
            state.runtime.close()
            self.assertTrue(state.runtime.kernel._connection_closed)
            self.assertTrue(state.context._observation_closed)
            before = sorted(path.name for path in self.root.iterdir())
            state.release.set()
            self.assertTrue(state.wrapper_finished.wait(1))
            self.assertTrue(state.finished.is_set())
            state.runtime.close()
            self.assertEqual(opens, [])
            self.assertEqual(state.wall_calls, [])
            self.assertFalse(state.context._completion_readers_pending())
            self.assertEqual(before, sorted(path.name for path in self.root.iterdir()))
            self.assertFalse(state.captures[0]["completion_time_known"])
            self.assertIn("completion_clock_context_closed", state.captures[0]["completion_time_error"])
            self.evidence["records"].append({"files_before": before,
                "files_after": sorted(path.name for path in self.root.iterdir()), "late_storage_opens": 0})
            self.assert_original_persisted(state)

    def test_admitted_actual_snapshot_retains_storage_until_body_and_physical_close_finish(self):
        held, release_read, draining = (threading.Event() for _ in range(3))
        connections, close_calls, close_errors = [], [], []
        factory, read_floor = clock_module._connect_readonly, clock_module._read_floor
        close = storage_connection._ParticipatingConnection.close

        def opened(*args, **options):
            connection = factory(*args, **options)
            connections.append(connection)
            return connection

        def held_floor(connection, *args, **options):
            result = read_floor(connection, *args, **options)
            self.evidence["records"].append({"snapshot_transaction_open": connection.in_transaction})
            held.set()
            release_read.wait()
            return result

        def observed_close(connection):
            if connections and connection is connections[0]:
                close_calls.append(threading.current_thread().name)
            return close(connection)

        with self.timed_out_runtime() as state:
            drain = state.context._drain_completion_readers

            def observed_drain(deadline):
                draining.set()
                return drain(deadline)

            def close_runtime():
                try:
                    state.runtime.close()
                except BaseException as error:
                    close_errors.append(error)

            closer = threading.Thread(target=close_runtime, name="completion-reader-closer")
            with patch.object(clock_module, "_connect_readonly", side_effect=opened), \
                    patch.object(clock_module, "_read_floor", side_effect=held_floor), \
                    patch.object(storage_connection._ParticipatingConnection, "close", observed_close), \
                    patch.object(state.context, "_drain_completion_readers", side_effect=observed_drain):
                try:
                    state.release.set()
                    self.assertTrue(held.wait(1))
                    self.assertEqual(len(connections), 1)
                    owner = next(iter(state.context._completion_readers))
                    self.assertIs(owner._connection, connections[0])
                    self.assertFalse(owner._body_done.is_set())
                    closer.start()
                    self.assertTrue(draining.wait(2))
                    self.assertTrue(state.context._observation_closed)
                    self.assertFalse(state.runtime.kernel._connection_closed)
                    self.assertEqual(close_calls, [])
                    closer.join(2)
                    self.assertFalse(closer.is_alive())
                    self.assertEqual(len(close_errors), 1)
                    self.assertIsInstance(close_errors[0], _ObservationCleanupPendingError)
                    self.assertTrue(state.context._completion_readers_pending())
                    self.assertIn(state.context, state.runtime._retired_observation_contexts)
                    self.assertIsNotNone(connections[0]._participation)
                    self.assertFalse(state.runtime._thread_slots.acquire(blocking=False))
                    self.assertEqual(close_calls, [], "cleanup closed a reader whose body was still active")
                    self.evidence["records"].append({"pending_close": self.raw(close_errors[0]),
                        "retained_actual_reader": True, "close_calls_during_body": list(close_calls)})
                    release_read.set()
                    self.assertTrue(state.wrapper_finished.wait(1))
                    state.runtime.close()
                    self.assertFalse(state.context._completion_readers_pending())
                    self.assertEqual(state.runtime._retired_observation_contexts, [])
                    self.assertIsNone(connections[0]._participation)
                    with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed database"):
                        connections[0].execute("SELECT 1")
                    self.assertEqual(len(connections), 1)
                    self.assertEqual(len(state.wall_calls), 1)
                    self.assertTrue(state.runtime._thread_slots.acquire(blocking=False))
                    state.runtime._thread_slots.release()
                    self.assert_original_persisted(state)
                finally:
                    release_read.set()
                    if closer.ident is not None:
                        closer.join(2)

    def test_failed_close_retains_same_participating_connection_and_capacity_until_retry(self):
        allow_close = threading.Event()
        connections, close_calls, sample_calls = [], [], []
        sentinel = OSError("real completion reader fixture refused physical close")
        factory = clock_module._connect_readonly
        close = storage_connection._ParticipatingConnection.close
        sample = clock_module.sample_clock

        def observed_sample(*args, **options):
            sample_calls.append({"thread": threading.current_thread().name, "at": time.monotonic()})
            return sample(*args, **options)

        def opened(*args, **options):
            connection = factory(*args, **options)
            connections.append(connection)
            return connection

        with self.timed_out_runtime() as state:
            def failing_close(connection):
                if connections and connection is connections[0]:
                    owner = next(iter(state.context._completion_readers))
                    close_calls.append({"thread": threading.current_thread().name,
                                        "body_done": owner._body_done.is_set(), "allowed": allow_close.is_set()})
                    if not allow_close.is_set():
                        raise sentinel
                return close(connection)

            with patch.object(clock_module, "_connect_readonly", side_effect=opened), \
                    patch.object(storage_connection._ParticipatingConnection, "close", failing_close), \
                    patch.object(clock_module, "sample_clock", side_effect=observed_sample):
                try:
                    state.release.set()
                    self.assertTrue(state.wrapper_finished.wait(1))
                    self.assertEqual(len(connections), 1)
                    owner = next(iter(state.context._completion_readers))
                    self.assertTrue(owner._body_done.is_set())
                    self.assertIs(owner._connection, connections[0])
                    self.assertIs(owner._close_error, sentinel)
                    self.assertEqual(connections[0].execute("SELECT 1").fetchone()[0], 1)
                    self.assertIsNotNone(connections[0]._participation)
                    self.assertFalse(state.runtime._thread_slots.acquire(blocking=False))
                    samples_before = len(sample_calls)
                    retry_boundary = self.reader_retry_boundary()
                    with self.assertRaises(_ObservationCleanupPendingError):
                        state.runtime.close()
                    self.assert_reader_retry_has_no_sql(connections[0], retry_boundary, sample_calls, samples_before)
                    self.assertFalse(state.runtime.kernel._connection_closed)
                    self.assertIn(state.context, state.runtime._retired_observation_contexts)
                    self.assertIs(owner._connection, connections[0])
                    receipt = dict(state.captures[0])
                    self.assertFalse(receipt["completion_time_known"])
                    self.assertIn(str(sentinel), receipt["completion_time_error"])
                    self.assertFalse(close_calls[0]["body_done"])
                    self.assertTrue(all(item["body_done"] for item in close_calls[1:]))
                    allow_close.set()
                    samples_before = len(sample_calls)
                    retry_boundary = self.reader_retry_boundary()
                    state.runtime.close()
                    retry_events = self.assert_reader_retry_has_no_sql(
                        connections[0], retry_boundary, sample_calls, samples_before)
                    self.assertTrue(any(event["operation"] == "close" for event in retry_events),
                                    "successful retry lacked physical close evidence for the exact reader")
                    self.assertIsNone(owner._connection)
                    self.assertIs(owner._close_error, sentinel)
                    self.assertIsNone(connections[0]._participation)
                    with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed database"):
                        connections[0].execute("SELECT 1")
                    self.assertEqual(state.captures[0], receipt)
                    self.assertEqual(len(connections), 1)
                    self.assertEqual(len(state.wall_calls), 1)
                    self.assertEqual(len(sample_calls), 1)
                    self.assertFalse(state.context._completion_readers_pending())
                    self.assertTrue(state.runtime._thread_slots.acquire(blocking=False))
                    state.runtime._thread_slots.release()
                    self.evidence["records"].append({"first_close_error": self.raw(sentinel),
                        "exact_connection_retried": True, "close_calls": close_calls, "original_receipt": receipt})
                    self.assert_original_persisted(state)
                finally:
                    allow_close.set()

    def test_actual_sql_failure_keeps_original_error_and_failed_close_cause(self):
        allow_close = threading.Event()
        connections, refusals = [], []
        sentinel = OSError("actual reader close refused")
        factory, read_floor = clock_module._connect_readonly, clock_module._read_floor
        close = storage_connection._ParticipatingConnection.close

        def opened(*args, **options):
            connection = factory(*args, **options)
            connection.set_authorizer(lambda action, first, second, database, source:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and first == "kernel_clock"
                else sqlite3.SQLITE_OK)
            connections.append(connection)
            return connection

        def record_refusal(*args, **options):
            try:
                return read_floor(*args, **options)
            except BaseException as error:
                refusals.append(error)
                raise

        def failing_close(connection):
            if connections and connection is connections[0] and not allow_close.is_set():
                raise sentinel
            return close(connection)

        with self.actual_context() as state, patch.object(clock_module, "_connect_readonly", side_effect=opened), \
                patch.object(clock_module, "_read_floor", side_effect=record_refusal), \
                patch.object(storage_connection._ParticipatingConnection, "close", failing_close):
            try:
                state.phase[0] = "capture"
                with self.assertRaises(sqlite3.DatabaseError) as caught:
                    capture_completion_time(state.context)
                state.phase[0] = "cleanup"
                self.assertEqual(len(refusals), 1)
                self.assertIs(caught.exception, refusals[0])
                self.assertIs(caught.exception.__cause__, sentinel)
                owner = next(iter(state.context._completion_readers))
                self.assertTrue(owner._body_done.is_set())
                self.assertIs(owner._connection, connections[0])
                self.assertIsNotNone(connections[0]._participation)
                self.assertTrue(state.context._drain_completion_readers(time.monotonic() + 1))
                allow_close.set()
                self.assertFalse(state.context._drain_completion_readers(time.monotonic() + 1))
                self.assertIsNone(connections[0]._participation)
                self.assertEqual(len(connections), 1)
                self.assertEqual(len(state.wall_calls), 1)
                self.evidence["records"].append({"raw_read_failure": self.raw(caught.exception),
                    "retained_close_failure": self.raw(owner._close_error), "exact_connection_retried": True})
            finally:
                allow_close.set()

    @contextmanager
    def record_lifecycle_acquires(self, context):
        actual_lock = context._observation_lifecycle_lock
        records = []

        class ForwardingLock:
            def acquire(self, *args, **options):
                timeout = options.get("timeout", args[1] if len(args) > 1 else None)
                event = {"thread": threading.current_thread().name, "called_at": time.monotonic(),
                         "timeout": timeout}
                records.append(event)
                acquired = actual_lock.acquire(*args, **options)
                event.update(acquired=acquired, returned_at=time.monotonic())
                return acquired

            def release(self):
                return actual_lock.release()

            def __enter__(self):
                self.acquire()
                return self

            def __exit__(self, *args):
                self.release()

        with patch.object(context, "_observation_lifecycle_lock", ForwardingLock()):
            yield records

    def assert_lifecycle_acquires_use_deadline(self, records, budget, bound, *, count):
        calls = [event for event in records if event["thread"] == threading.current_thread().name
                 and event["timeout"] is not None]
        self.assertEqual(len(calls), count)
        self.assertEqual(budget["deadline"], budget["started"] + bound)
        # Subtracting large clock anchors can round just above the nominal
        # duration. This is assertion precision, not extra capture authority.
        representation_error = math.ulp(budget["started"]) + math.ulp(budget["deadline"])
        for event in calls:
            self.assertGreaterEqual(event["timeout"], 0)
            self.assertLessEqual(event["timeout"] - bound, representation_error,
                                 "real lock acquire ignored the tighter configured capture bound")
            remaining = max(0., budget["deadline"] - event["called_at"])
            # Allow interception/scheduler delay between calculating remaining
            # and forwarding to the native lock, without permitting .1 for .02.
            self.assertAlmostEqual(event["timeout"], remaining, delta=bound / 10)
        self.evidence["records"].append({"phase": "actual_lifecycle_lock_arguments",
            "original_budget": budget, "original_bound": bound, "acquires": calls})

    @contextmanager
    def held_lifecycle(self, context, request):
        held, release = threading.Event(), threading.Event()

        def hold():
            request.wait()
            with context._observation_lifecycle_lock:
                held.set()
                release.wait()

        holder = threading.Thread(target=hold, name="completion-lifecycle-holder")
        holder.start()
        try:
            yield held
        finally:
            request.set()
            release.set()
            holder.join(1)
            self.assertFalse(holder.is_alive())

    def test_lifecycle_admission_uses_original_capture_and_tighter_configured_deadline(self):
        for configured in (None, .02):
            with self.subTest(configured=configured), self.actual_context(control_timeout=configured) as state:
                request = threading.Event()
                budgets = []
                reserve = state.context._reserve_completion_reader

                def observed_reserve(owner, budget):
                    budgets.append({"started": budget.started, "deadline": budget.deadline})
                    return reserve(owner, budget)

                with self.record_lifecycle_acquires(state.context) as acquires, \
                        self.held_lifecycle(state.context, request) as held, \
                        patch.object(state.context, "_reserve_completion_reader", side_effect=observed_reserve), \
                        patch.object(clock_module, "_connect_readonly", wraps=clock_module._connect_readonly) as opened:
                    request.set()
                    self.assertTrue(held.wait(1))
                    state.phase[0] = "capture"
                    # Measure the native wait with the duration clock; the
                    # original capture deadline still uses monotonic time.
                    began = time.perf_counter()
                    with self.assertRaises((InspectionBudgetExceeded, TimeoutError)) as caught:
                        capture_completion_time(state.context)
                    finished = time.perf_counter()
                    elapsed = finished - began
                    state.phase[0] = "cleanup"
                    bound = .1 if configured is None else configured
                    representation_error = math.ulp(began) + math.ulp(finished)
                    self.assertGreaterEqual(elapsed - bound * .8, -representation_error)
                    self.assertLess(elapsed, .3)
                    self.assertEqual(len(budgets), 1)
                    self.assert_lifecycle_acquires_use_deadline(acquires, budgets[0], bound, count=1)
                    self.assertEqual(state.wall_calls, [])
                    opened.assert_not_called()
                    self.assertEqual(state.context._completion_readers, set())
                    self.assertFalse(state.context._completion_readers_pending())
                    self.evidence["records"].append({"phase": "admission_contention", "original_bound": bound,
                        "elapsed": elapsed, "elapsed_clock": "perf_counter",
                        "raw_error": self.raw(caught.exception), "wall_samples": 0, "opens": 0})
                state.context.close()
                with patch.object(clock_module, "_connect_readonly", wraps=clock_module._connect_readonly) as opened:
                    state.phase[0] = "capture"
                    with self.assertRaisesRegex(BudgetClockUnknownError, "completion_clock_context_closed"):
                        capture_completion_time(state.context)
                    state.phase[0] = "cleanup"
                    opened.assert_not_called()
                    self.assertEqual(state.wall_calls, [])

    def test_lifecycle_release_contention_keeps_receipt_and_owner_within_same_capture_deadline(self):
        for configured in (None, .02):
            with self.subTest(configured=configured), self.actual_context(control_timeout=configured) as state:
                request = threading.Event()
                owners, deadlines, opens = [], [], []
                reserve = state.context._reserve_completion_reader
                release = state.context._release_completion_reader
                factory = clock_module._connect_readonly

                def observed_reserve(owner, budget):
                    deadlines.append({"started": budget.started, "deadline": budget.deadline})
                    return reserve(owner, budget)

                def opened(*args, **options):
                    connection = factory(*args, **options)
                    opens.append(connection)
                    return connection

                with self.record_lifecycle_acquires(state.context) as acquires, \
                        self.held_lifecycle(state.context, request) as held:
                    def contended_release(owner, deadline):
                        owners.append(owner)
                        request.set()
                        self.assertTrue(held.wait(1))
                        self.assertEqual(deadline, deadlines[0]["deadline"])
                        return release(owner, deadline)

                    with patch.object(state.context, "_reserve_completion_reader", side_effect=observed_reserve), \
                            patch.object(state.context, "_release_completion_reader", side_effect=contended_release), \
                            patch.object(clock_module, "_connect_readonly", side_effect=opened):
                        state.phase[0] = "capture"
                        # Keep the budget's monotonic anchors intact while
                        # measuring this native wait with the duration clock.
                        began = time.perf_counter()
                        completed_at = capture_completion_time(state.context)
                        finished = time.perf_counter()
                        elapsed = finished - began
                        state.phase[0] = "cleanup"
                        bound = .1 if configured is None else configured
                        representation_error = math.ulp(began) + math.ulp(finished)
                        self.assertGreaterEqual(elapsed - bound * .8, -representation_error)
                        self.assertLess(elapsed, .3)
                        self.assertEqual(deadlines[0]["deadline"], deadlines[0]["started"] + bound)
                        self.assert_lifecycle_acquires_use_deadline(acquires, deadlines[0], bound, count=2)
                        self.assertGreaterEqual(completed_at, state.context.budget_envelope.checkpoint.wall_at)
                        self.assertEqual(len(owners), 1)
                        self.assertTrue(owners[0]._body_done.is_set())
                        self.assertIsNone(owners[0]._connection)
                        self.assertIsNone(opens[0]._participation)
                        self.assertTrue(state.context._completion_readers_pending())
                        self.assertIn(owners[0], state.context._completion_readers)
                        self.evidence["records"].append({"phase": "release_contention", "original_bound": bound,
                            "elapsed": elapsed, "elapsed_clock": "perf_counter",
                            "completed_at": completed_at, "capture_deadline": deadlines[0],
                            "physical_reader_closed": True, "owner_retained": True})
                with patch.object(clock_module, "_connect_readonly", side_effect=opened):
                    self.assertFalse(state.context._drain_completion_readers(time.monotonic() + 1))
                self.assertEqual(len(opens), 1)
                self.assertEqual(len(state.wall_calls), 1)
                self.assertFalse(state.context._completion_readers_pending())

    def test_cleanup_release_contention_consumes_existing_drain_deadline_and_retains_owner(self):
        with self.actual_context() as state:
            owner_type = clock_module._CompletionReaderLifetime
            release = state.context._release_completion_reader
            owners = []

            capture_request = threading.Event()
            with self.held_lifecycle(state.context, capture_request) as capture_held:
                def retain(owner, deadline):
                    owners.append(owner)
                    capture_request.set()
                    self.assertTrue(capture_held.wait(1))
                    return release(owner, deadline)

                state.phase[0] = "capture"
                with patch.object(state.context, "_release_completion_reader", side_effect=retain):
                    completed_at = capture_completion_time(state.context)
            state.phase[0] = "cleanup"
            self.assertEqual(len(owners), 1)
            self.assertIsInstance(owners[0], owner_type)
            self.assertTrue(owners[0]._body_done.is_set())
            self.assertIsNone(owners[0]._connection)
            results, errors, deadlines = [], [], []
            request = threading.Event()

            with self.held_lifecycle(state.context, request) as held:
                def contended_release(owner, deadline):
                    deadlines.append(deadline)
                    request.set()
                    self.assertTrue(held.wait(1))
                    return release(owner, deadline)

                def drain():
                    began = time.monotonic()
                    deadline = began + 1.0
                    try:
                        results.append({"pending": state.context._drain_completion_readers(deadline),
                                        "elapsed": time.monotonic() - began, "deadline": deadline})
                    except BaseException as error:
                        errors.append(error)

                drainer = threading.Thread(target=drain, name="completion-cleanup-drain")
                with patch.object(state.context, "_release_completion_reader", side_effect=contended_release), \
                        patch.object(clock_module, "_connect_readonly", wraps=clock_module._connect_readonly) as opened:
                    try:
                        drainer.start()
                        self.assertTrue(held.wait(1))
                        drainer.join(2)
                        self.assertFalse(drainer.is_alive())
                        self.assertEqual(errors, [])
                        self.assertEqual(len(results), 1)
                        self.assertTrue(results[0]["pending"])
                        self.assertGreaterEqual(results[0]["elapsed"], .8)
                        self.assertLess(results[0]["elapsed"], 1.3)
                        self.assertEqual(deadlines, [results[0]["deadline"]])
                        self.assertIn(owners[0], state.context._completion_readers)
                        self.assertTrue(state.context._completion_readers_pending())
                        opened.assert_not_called()
                        self.evidence["records"].append({"phase": "cleanup_release_contention",
                            "original_drain_bound": 1.0, "result": results[0], "completed_at": completed_at})
                    finally:
                        # held_lifecycle releases its lock on exit. The drainer
                        # must have returned from its original bound first.
                        if drainer.ident is not None and not drainer.is_alive():
                            drainer.join(0)
            self.assertFalse(state.context._drain_completion_readers(time.monotonic() + 1))
            self.assertEqual(len(state.wall_calls), 1)
            self.assertFalse(state.context._completion_readers_pending())


if __name__ == "__main__":
    unittest.main()
