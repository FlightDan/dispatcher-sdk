"""Runtime storage lifetime follows its stopped observation workers."""
from contextlib import contextmanager
from pathlib import Path
import multiprocessing
import tempfile
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, SQLiteKernel
from dispatcher_sdk.execution_kernel.runtime import _ObservationCleanupPendingError, _UnpersistedSettlementsError
from dispatcher_sdk.execution_kernel.sandbox_contracts import SandboxOutcomeUnknown
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.observability import ActivityRecorder, ObservationIdentity, ObservationJournal
from tests._acceptance_evidence import retained_directory
from tests._storage_evidence import StorageEvidence


def completed_handler(payload, context):
    return {"original": "completed"}


class RuntimeObservationCleanupTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-runtime-observation-cleanup-")
        self.storage_evidence = StorageEvidence(self.root, self)
        self.storage_evidence.start()
        self.addCleanup(self.storage_evidence.stop)
        self.addCleanup(self.storage_evidence.save)

    def tearDown(self):
        self.storage_evidence.save(phase="before_cleanup")

    @contextmanager
    def kernel_storage(self):
        path = self.root / ("kernel-" + str(len(list(self.root.iterdir()))))
        path.mkdir()
        yield str(path)

    @contextmanager
    def held_observer(self, runtime, *, expected_close_error=None):
        entered, release, joining, released_connection = (threading.Event() for _ in range(4))
        original_transaction = ObservationJournal._transaction
        original_join = ActivityRecorder._join_owned_workers
        held = []

        @contextmanager
        def transaction(journal, **kwargs):
            owned = None
            try:
                with original_transaction(journal, **kwargs) as current:
                    if threading.current_thread().name == "dispatcher-process-observer" and not held:
                        owned = current[0]
                        held.append(owned)
                        entered.set()
                        if not release.wait(10):
                            raise RuntimeError("fixture did not release its real SQLite connection")
                    yield current
            finally:
                if owned is not None:
                    # SQLite checks thread affinity before checking closed.
                    # Inspect from its actual owning collector thread.
                    try:
                        owned.execute("SELECT 1")
                    except sqlite3.ProgrammingError as error:
                        if "closed database" in str(error):
                            released_connection.set()

        def join(recorder, deadline):
            joining.set()
            return original_join(recorder, deadline)

        try:
            with patch.object(ObservationJournal, "_transaction", transaction), \
                    patch.object(ActivityRecorder, "_join_owned_workers", join):
                runtime.submit(runtime.command("work", execution_id="original", idempotency_key="original",
                    correlation_id="original", timeout_seconds=10, payload={}))
                result = runtime.run_once()
                self.assertTrue(entered.is_set(), "fixture did not hold an actual observer transaction")
                self.assertEqual(result.state, "succeeded")
                self.assertEqual(result.result.value, {"original": "completed"})
                yield result, released_connection, release, joining
        finally:
            release.set()
            try:
                runtime.close()
            except BaseException as error:
                if error is not expected_close_error:
                    raise

    def test_close_waits_for_owned_real_sqlite_connection(self):
        with self.kernel_storage() as temporary:
            path = Path(temporary) / "runtime.sqlite3"
            runtime = Kernel.open_sqlite(path, {"work": completed_handler}, isolation_mode="thread")
            with self.held_observer(runtime) as (result, released_connection, release, joining):
                errors = []
                returned = threading.Event()

                def close():
                    try:
                        runtime.close()
                    except BaseException as error:
                        errors.append(error)
                    finally:
                        returned.set()

                closer = threading.Thread(target=close)
                closer.start()
                try:
                    self.assertTrue(joining.wait(5), "close did not drain its retired observation workers")
                    self.assertFalse(returned.is_set())
                    release.set()
                    closer.join(5)
                    self.assertFalse(closer.is_alive())
                    self.assertEqual(errors, [])
                    self.assertTrue(released_connection.is_set())
                    self.assertEqual(runtime._retired_recorders, [])
                    self.assertTrue(all(report["state"] == "closed" for report in runtime._observation_cleanup_report))
                    with SQLiteKernel(path) as reader:
                        self.assertEqual(reader.get("original").to_dict(), result.to_dict())
                finally:
                    release.set()
                    closer.join(5)

    def test_pending_cleanup_retains_temporary_storage_until_repeated_close(self):
        with self.kernel_storage() as temporary:
            observation = tempfile.TemporaryDirectory(dir=self.root)
            path = Path(observation.name) / "observations.sqlite3"
            runtime = Kernel.open_sqlite(Path(temporary) / "runtime.sqlite3", {"work": completed_handler},
                isolation_mode="thread", observation_path=str(path))
            # Give this real file-backed fixture runtime ownership of its
            # temporary observation directory, as an in-memory runtime does.
            runtime._temporary_observation = observation
            with self.held_observer(runtime) as (result, released_connection, release, joining):
                began = time.monotonic()
                with self.assertRaises(_ObservationCleanupPendingError):
                    runtime.close()
                self.assertLess(time.monotonic() - began, 3)
                self.assertTrue(joining.is_set())
                self.assertTrue(path.exists())
                self.assertTrue(runtime._retired_recorders)
                self.assertTrue(any(report["state"] == "pending" for report in runtime._observation_cleanup_report))
                self.assertEqual(result.result.value, {"original": "completed"})
                retired = runtime._retired_recorders[0]
                original_receipt = retired._close_result
                release.set()
                retired._join_owned_workers(time.monotonic() + 1)
                runtime._retain_observation_workers(retired)
                self.assertEqual(runtime._retired_recorders, [])
                self.assertTrue(runtime._observation_cleanup_pending)
                runtime.close()
                self.assertIs(retired._close_result, original_receipt)
                self.assertTrue(released_connection.is_set())
                self.assertEqual(runtime._retired_recorders, [])
                self.assertIsNone(runtime._close_error)
                self.assertFalse(runtime._observation_cleanup_pending)
                self.assertFalse(path.exists())

    def test_cleanup_retry_does_not_clear_original_sandbox_error(self):
        with self.kernel_storage() as temporary:
            path = Path(temporary) / "runtime.sqlite3"
            runtime = Kernel.open_sqlite(path, {"work": completed_handler}, isolation_mode="thread")
            error = SandboxOutcomeUnknown("original sandbox cleanup is unresolved")
            with self.held_observer(runtime, expected_close_error=error) as (result, released_connection, release, joining):
                with patch.object(runtime, "recover_sandboxes", side_effect=error):
                    with self.assertRaises(SandboxOutcomeUnknown) as first:
                        runtime.close()
                    self.assertIs(first.exception, error)
                self.assertTrue(runtime._retired_recorders)
                release.set()
                with self.assertRaises(SandboxOutcomeUnknown) as repeated:
                    runtime.close()
                self.assertIs(repeated.exception, error)
                self.assertTrue(released_connection.is_set())
                self.assertEqual(runtime._retired_recorders, [])
                with SQLiteKernel(path) as reader:
                    self.assertEqual(reader.get("original").to_dict(), result.to_dict())

    def test_settlement_retry_cannot_clear_pending_real_connection_cleanup(self):
        with self.kernel_storage() as temporary:
            runtime = Kernel.open_sqlite(Path(temporary) / "runtime.sqlite3", {"work": completed_handler},
                isolation_mode="thread")
            with self.held_observer(runtime) as (result, released_connection, release, joining):
                with patch.object(runtime, "_persist_pending_settlements"), \
                        patch.object(runtime._pending_settlements, "identities", return_value=({"execution_id": "original"},)) as identities:
                    with self.assertRaises(_UnpersistedSettlementsError):
                        runtime.close()
                    identities.return_value = ()
                    with self.assertRaises(_ObservationCleanupPendingError):
                        runtime.close()
                self.assertTrue(runtime._retired_recorders)
                self.assertFalse(released_connection.is_set())
                self.assertEqual(result.result.value, {"original": "completed"})
                release.set()
                runtime.close()
                self.assertTrue(released_connection.is_set())
                self.assertEqual(runtime._retired_recorders, [])
                self.assertIsNone(runtime._close_error)

    def test_revoked_handler_cannot_start_observer_after_storage_cleanup(self):
        release, finished = threading.Event(), threading.Event()
        observations = []

        def late_handler(payload, context):
            try:
                release.wait()
                observed = context.activity.observe_process(multiprocessing.current_process(), process_id="late")
                observations.append((context.activity, observed.snapshot()))
                return {"late": True}
            finally:
                finished.set()

        late_handler.__execution_kernel_revision__ = "late-observer-cleanup-fixture-v1"

        with self.kernel_storage() as temporary:
            observation = tempfile.TemporaryDirectory(dir=self.root)
            path = Path(observation.name) / "observations.sqlite3"
            runtime = Kernel.open_sqlite(Path(temporary) / "runtime.sqlite3", {"work": late_handler},
                isolation_mode="thread", observation_path=str(path))
            runtime._temporary_observation = observation
            try:
                runtime.submit(runtime.command("work", execution_id="late", idempotency_key="late",
                    correlation_id="late", timeout_seconds=.2, payload={}))
                original = runtime.run_once()
                self.assertEqual(original.result.status, "timed_out")
                runtime.close()
                self.assertFalse(path.exists())
                release.set()
                self.assertTrue(finished.wait(3))
                self.assertEqual(len(observations), 1)
                recorder, report = observations[0]
                self.assertEqual(report["unknown_reason"], "collector_closed")
                self.assertTrue(recorder._process_observer._stop.is_set())
                self.assertIsNone(recorder._process_observer._thread)
                self.assertFalse(recorder._owned_workers_alive())
                with SQLiteKernel(Path(temporary) / "runtime.sqlite3") as reader:
                    self.assertEqual(reader.get("late").to_dict(), original.to_dict())
            finally:
                release.set()
                finished.wait(3)
                runtime.close()

    def test_expired_flusher_close_still_stops_existing_process_observer(self):
        with self.kernel_storage() as temporary:
            runtime = Kernel.open_sqlite(Path(temporary) / "runtime.sqlite3", {"work": completed_handler},
                isolation_mode="thread")
            runtime.submit(runtime.command("work", execution_id="flush", idempotency_key="flush",
                correlation_id="flush", timeout_seconds=10, payload={}))
            lease = runtime.kernel.claim_and_start("fixture")
            entered, release = threading.Event(), threading.Event()
            original_transaction = ObservationJournal._transaction

            @contextmanager
            def transaction(journal, **kwargs):
                with original_transaction(journal, **kwargs) as current:
                    if threading.current_thread().name == "dispatcher-observation-flush" and not entered.is_set():
                        entered.set()
                        release.wait()
                    yield current

            recorder = ActivityRecorder(runtime.observation_journal,
                ObservationIdentity("flush", lease.attempt, lease.fence), start=True)
            recorder.observe_process(multiprocessing.current_process(), process_id="driver")
            try:
                with patch.object(ObservationJournal, "_transaction", transaction):
                    recorder.report_bytes("stdout", b"original output")
                    recorder._wake.set()
                    self.assertTrue(entered.wait(3))
                    receipt = recorder.close(timeout=.05)
                    original_deadline = recorder._close_deadline
                    self.assertEqual(receipt["state"], "pending")
                    self.assertFalse(receipt["final_flush_persisted"])
                    self.assertTrue(recorder._process_observer._stop.is_set())
                    release.set()
                    report = recorder._join_owned_workers(time.monotonic() + 1)
                    self.assertEqual(report["state"], "closed")
                    self.assertEqual(recorder._close_deadline, original_deadline)
                    self.assertFalse(receipt["final_flush_persisted"])
            finally:
                release.set()
                recorder.close()
                recorder._join_owned_workers(time.monotonic() + 1)
                runtime.close()

    def test_initializing_context_keeps_actual_connection_storage_pending(self):
        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        held, errors, results, calls = [], [], [], []

        def handler(payload, context):
            calls.append("business")
            return {"original": "completed"}

        handler.__execution_kernel_revision__ = "held-observation-start-fixture-v1"
        original_transaction = ObservationJournal._transaction

        @contextmanager
        def transaction(journal, **kwargs):
            with original_transaction(journal, **kwargs) as current:
                if threading.current_thread().name.startswith("execution-kernel_") and not held:
                    held.append(current[0])
                    entered.set()
                    release.wait()
                yield current

        with self.kernel_storage() as temporary:
            observation = tempfile.TemporaryDirectory(dir=self.root)
            path = Path(observation.name) / "observations.sqlite3"
            runtime = Kernel.open_sqlite(Path(temporary) / "runtime.sqlite3", {"work": handler},
                isolation_mode="thread", lease_seconds=5, observation_path=str(path))
            runtime._temporary_observation = observation
            runtime.submit(runtime.command("work", execution_id="startup", idempotency_key="startup",
                correlation_id="startup", timeout_seconds=.2, payload={}))

            def run():
                try:
                    results.append(runtime.run_once())
                except BaseException as error:
                    errors.append(error)
                finally:
                    returned.set()

            with patch.object(ObservationJournal, "_transaction", transaction):
                runner = threading.Thread(target=run)
                runner.start()
                try:
                    entered_on_time = entered.wait(3)
                    if not entered_on_time:
                        self.storage_evidence.save(phase="initialization_entry_wait_expired",
                            checkpoint={"original_wait": 3, "entered": entered_on_time})
                    self.assertTrue(entered_on_time)
                    contexts = tuple(runtime._thread_contexts.values())
                    self.assertEqual(len(contexts), 1)
                    context = contexts[0]
                    self.assertFalse(context._observation_start_done.is_set())
                    with self.assertRaises(_ObservationCleanupPendingError):
                        runtime.close()
                    self.assertTrue(returned.is_set())
                    self.assertEqual(errors, [])
                    self.assertTrue(path.exists())
                    self.assertFalse(context._observation_start_done.is_set())
                    self.assertTrue(runtime._retired_observation_contexts)
                    self.assertEqual(calls, [])
                    release.set()
                    start_done = context._observation_start_done.wait(3)
                    if not start_done:
                        self.storage_evidence.save(phase="initialization_wait_expired",
                            checkpoint={"original_wait": 3, "start_done": start_done})
                    self.assertTrue(start_done)
                    runtime.close()
                    self.assertFalse(path.exists())
                    self.assertEqual(runtime._retired_observation_contexts, [])
                    self.assertEqual(calls, [])
                    if isinstance(context.activity, ActivityRecorder):
                        # A collector constructor may have held the original
                        # SQL operation after the pre-creation close check.
                        # That losing publication is closed before startdone.
                        self.assertTrue(context.activity._closed)
                        self.assertFalse(context.activity._owned_workers_alive())
                finally:
                    release.set()
                    runner.join(3)
                    runtime.close()

    def test_sdk_sampler_and_settlement_connections_keep_storage_pending(self):
        for service in ("sampler", "settlement"):
            with self.subTest(service=service), self.kernel_storage() as temporary:
                observation = tempfile.TemporaryDirectory(dir=self.root)
                path = Path(observation.name) / "observations.sqlite3"
                runtime = Kernel.open_sqlite(Path(temporary) / "runtime.sqlite3", {"work": completed_handler},
                    isolation_mode="thread", observation_path=str(path))
                runtime._temporary_observation = observation
                if service == "settlement":
                    runtime._settlement_journal = SettlementJournal(Path(observation.name) / "settlements.sqlite3",
                        source_id=runtime._sandbox_store_id, kernel_path=runtime.kernel.db_path)
                owner, method = ((ObservationJournal, "_read_connection") if service == "sampler"
                                 else (SettlementJournal, "_connection"))
                target = "dispatcher-stall-sampler" if service == "sampler" else "execution-kernel-settlement"
                entered, release = threading.Event(), threading.Event()
                held = []
                original_connection = getattr(owner, method)

                @contextmanager
                def connection(journal, *args, **kwargs):
                    with original_connection(journal, *args, **kwargs) as current:
                        if threading.current_thread().name == target and not held:
                            held.append(current[0] if service == "sampler" else current)
                            entered.set()
                            release.wait()
                        yield current

                with patch.object(owner, method, connection):
                    try:
                        runtime._start_services()
                        self.assertTrue(entered.wait(3), service)
                        with self.assertRaises(_ObservationCleanupPendingError):
                            runtime.close()
                        self.assertTrue(path.exists())
                        self.assertTrue(any(report["kind"] == "sdk_storage_service" and report["state"] == "pending"
                            for report in runtime._observation_cleanup_report))
                        release.set()
                        runtime.close()
                        self.assertFalse(path.exists())
                        self.assertFalse(runtime._observation_cleanup_pending)
                    finally:
                        release.set()
                        runtime.close()


if __name__ == "__main__":
    unittest.main()
