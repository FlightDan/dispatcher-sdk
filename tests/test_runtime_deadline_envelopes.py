"""Deadline protocol checks and bounded real POSIX execution witnesses."""
from __future__ import annotations

import os
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import traceback
from contextlib import closing, contextmanager
from collections import deque
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import dispatcher_sdk
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, ClockCheckpoint, DeadlineConstraint, sample_clock
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.execution_kernel.runtime import Runtime
from dispatcher_sdk.execution_kernel.context import HandlerContext
from dispatcher_sdk.execution_kernel.errors import HandlerExecutionError
import dispatcher_sdk.execution_kernel.runtime as runtime_module
from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime
from dispatcher_sdk.execution_kernel import _windows_runtime as windows_runtime
from dispatcher_sdk.observability import ActivityRecorder, ObservationIdentity, ObservationJournal, ObservationOptions
from tests._acceptance_evidence import retained_directory
from tests._storage_evidence import StorageEvidence


def _fixture_error(error):
    return {"type": type(error).__name__, "message": str(error),
        "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
        "traceback": traceback.format_exception(type(error), error, error.__traceback__)}


@contextmanager
def _retained_deadline_runtime(test, root, handlers, mode, evidence):
    """Keep the actual return and storage facts before Runtime cleanup."""
    storage = StorageEvidence(root, test)
    storage.start(include_kernel=True)
    runtime = None
    captures = []
    evidence.update({"root": str(root), "mode": mode, "sdk_import": dispatcher_sdk.__file__,
        "original_outcomes": [], "original_results": []})

    def secondary(stage, error):
        evidence.setdefault("secondary_errors", []).append({"stage": stage, **_fixture_error(error)})
        def report():
            raise error.with_traceback(error.__traceback__)
        test.addCleanup(report)

    def capture(phase):
        facts = {"captured_at": time.monotonic(), "markers": {}, "storage": {}}
        for name in ("confirming", "release", "business", "attempts"):
            marker = root / name
            facts["markers"][name] = {"exists": marker.exists()}
            if marker.exists():
                try:
                    facts["markers"][name]["contents"] = marker.read_text(encoding="utf-8")
                except OSError as error:
                    facts["markers"][name]["error"] = _fixture_error(error)
        stores = {"kernel.db": ("kernel_executions", "kernel_execution_limits", "kernel_events"),
            "kernel.db.settlements.sqlite3": ("settlement_records", "settlement_notes")}
        # Read-only diagnostic snapshots are bounded independently; they never
        # alter an execution, a clock checkpoint, or a retained result.
        deadline = time.monotonic() + .2
        for filename, tables in stores.items():
            database = root / filename
            snapshot = {"exists": database.exists(), "tables": {}}
            facts["storage"][filename] = snapshot
            if not database.exists():
                continue
            try:
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0)) as reader:
                    reader.row_factory = sqlite3.Row
                    reader.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
                    for table in tables:
                        snapshot["tables"][table] = [dict(row) for row in
                            reader.execute(f"SELECT * FROM {table} LIMIT 65")]
            except (sqlite3.Error, OSError) as error:
                snapshot["error"] = _fixture_error(error)
        evidence[phase] = facts
        (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        storage.save(phase=phase, checkpoint=evidence)

    try:
        runtime = Runtime(str(root / "kernel.db"), handlers, isolation_mode=mode)
        original_settle, original_result = runtime._settle_outcome, runtime._outcome_result

        def settle(snapshot, lease, outcome, admission):
            evidence["original_outcomes"].append({"snapshot": snapshot.to_dict(),
                "lease": lease.to_dict(), "outcome": deepcopy(outcome)})
            return original_settle(snapshot, lease, outcome, admission)

        def result(*args, **kwargs):
            actual = original_result(*args, **kwargs)
            evidence["original_results"].append(actual.to_dict())
            return actual

        for name, wrapper in (("_settle_outcome", settle), ("_outcome_result", result)):
            current = patch.object(runtime, name, wrapper)
            current.start()
            captures.append(current)
        yield runtime, capture
    except BaseException as error:
        evidence["raw_error"] = _fixture_error(error)
        raise
    finally:
        try:
            capture("before-cleanup")
        except BaseException as error:
            secondary("before-cleanup evidence", error)
        if runtime is not None:
            try:
                runtime.close()
                evidence["runtime_cleanup"] = {"returned": True}
            except BaseException as error:
                evidence["runtime_cleanup"] = {"error": _fixture_error(error)}
                secondary("Runtime.close", error)
        try:
            (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            storage.save(phase="runtime-cleanup", checkpoint=evidence)
        except BaseException as error:
            secondary("runtime-cleanup evidence", error)
        finally:
            for current in reversed(captures):
                current.stop()
            storage.stop()
        print("deadline_fixture_evidence=" + str(root / "evidence.json"), flush=True)


def _recover_original_publication(runtime, original, evidence):
    """Publish retained facts within one API window and the committed deadline."""
    if original is None or original.state != "running":
        return original
    began = time.monotonic()
    maintenance = {"began": began, "api_timeout_seconds": .5, "deadline": began + .5, "passes": []}
    evidence["publication"] = maintenance
    deadline, current = maintenance["deadline"], original

    def read(operation):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("original publication window elapsed")
        with runtime.kernel._control_lock(min(.1, remaining)):
            value = operation(original.command.execution_id)
        if time.monotonic() > deadline:
            raise TimeoutError("original publication read window elapsed")
        return value

    try:
        limits = read(runtime.kernel.get_execution_limits)
        envelope = BudgetEnvelope.from_dict(limits["envelope"])
        maintenance["original_envelope"] = envelope.to_dict()
        original_deadline = envelope.deadline_monotonic(sample=sample_clock())
        maintenance["original_execution_deadline"] = original_deadline
        # Missing entry confirmation supplies no committed execution deadline.
        # Keep that uncertainty; do not grant it a fresh execution timeout.
        if original_deadline is None:
            maintenance["unavailable"] = "no committed execution deadline"
            return original
        deadline = min(deadline, original_deadline)
        maintenance["deadline"] = deadline
        while current.state == "running" and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            attempt = {"began": time.monotonic(), "timeout_seconds": min(.1, remaining)}
            maintenance["passes"].append(attempt)
            attempt["reports"] = list(runtime.recover_completions(timeout_seconds=attempt["timeout_seconds"]))
            attempt["returned_at"] = time.monotonic()
            if time.monotonic() >= deadline:
                break
            current = read(runtime.kernel.get)
            attempt["snapshot"] = current.to_dict()
            if current.state == "running":
                time.sleep(min(.005, max(0., deadline - time.monotonic())))
        maintenance["canonical_return"] = current.to_dict()
        return current
    except BaseException as error:
        maintenance["raw_error"] = _fixture_error(error)
        raise
    finally:
        maintenance["returned_at"] = time.monotonic()


def _assert_original_result(test, original, canonical, evidence):
    """Compare the full canonical receipt with the first real result generated."""
    test.assertIsNotNone(original)
    test.assertIsNotNone(canonical)
    test.assertEqual((original.execution_id, original.attempt, original.fence),
        (canonical.execution_id, canonical.attempt, canonical.fence))
    captured = next((item for item in evidence["original_results"]
        if (item["execution_id"], item["attempt"], item["fence"]) ==
        (original.execution_id, original.attempt, original.fence)), None)
    # A result may first be generated during deferred publication. Capture it
    # from the real SDK call; never fabricate an expected receipt from the final one.
    evidence["expected_original_result"] = deepcopy(captured)
    test.assertIsNotNone(captured, evidence)
    test.assertIsNotNone(canonical.result, canonical.to_dict())
    test.assertEqual(captured, canonical.result.to_dict())


def command(payload=None, timeout=10):
    return ExecutionCommandV2(execution_id="deadline-test", idempotency_key="deadline-key",
        registry_revision="deadline-test-registry", correlation_id="deadline-correlation",
        causation_id=None, handler_id="deadline-handler", handler_contract_version=1,
        retry_policy=RetryPolicy(), timeout_seconds=timeout, payload={} if payload is None else payload)


def echo(payload, context):
    return {"started_at": context.budget.started_at, "source": context.budget.limiting_source}


def blocked(payload, context):
    Path(payload["pid"]).write_text(str(os.getpid()), encoding="ascii")
    time.sleep(30)
    Path(payload["late"]).write_text("escaped", encoding="ascii")
    return {}


def orphan_with_held_final_flush(payload, context):
    original_close = context.activity.close

    def held_close():
        release = Path(payload["release"])
        while not release.exists():
            time.sleep(.002)
        Path(payload["flush_started"]).write_text(json.dumps({
            "pid": os.getpid(), "started_at": time.monotonic(),
        }), encoding="ascii")
        time.sleep(.4)
        receipt = original_close()
        Path(payload["flush_done"]).write_text(json.dumps({
            "pid": os.getpid(), "finished_at": time.monotonic(),
        }), encoding="ascii")
        return receipt

    context.activity.close = held_close
    context.activity.phase("business_returning")
    containment = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                   else {"start_new_session": True})
    child = (
        "import json,os,pathlib,sys,time; "
        "ready,release,escaped=map(pathlib.Path,sys.argv[1:]); "
        "ready.write_text(json.dumps({'pid':os.getpid(),'ready_at':time.monotonic()}),encoding='ascii'); "
        "exec('while not release.exists():\\n time.sleep(.002)'); "
        "escaped.write_text(json.dumps({'pid':os.getpid(),'escaped_at':time.monotonic()}),encoding='ascii')"
    )
    subprocess.Popen([sys.executable, "-c", child, payload["orphan_ready"], payload["release"],
                      payload["orphan"]], **containment)
    remaining = context.budget.remaining_work_seconds
    ready_deadline = time.monotonic() + (0 if remaining is None else remaining)
    while not Path(payload["orphan_ready"]).exists() and time.monotonic() < ready_deadline:
        time.sleep(.002)
    if not Path(payload["orphan_ready"]).exists():
        raise TimeoutError("orphan did not become ready before business return")
    Path(payload["business_returning"]).write_text(json.dumps({
        "pid": os.getpid(), "returned_at": time.monotonic(),
    }), encoding="ascii")
    return {"completed": True}


orphan_with_held_final_flush.__execution_kernel_revision__ = "held-final-flush-v1"


def inherited_deadline_child(payload, context):
    Path(payload["entered"]).write_text(str(os.getpid()), encoding="ascii")
    time.sleep(6)
    Path(payload["escaped"]).write_text("escaped", encoding="ascii")
    return {}


def inherited_deadline_parent(payload, context):
    return context.children.run("deadline-child", payload, request_id="inherited", timeout_seconds=30)


inherited_deadline_child.__execution_kernel_revision__ = "portable-inherited-child-v1"
inherited_deadline_parent.__execution_kernel_revision__ = "portable-inherited-parent-v1"


def denied_child(payload, context):
    from dispatcher_sdk.execution_kernel import HandlerExecutionError
    raise HandlerExecutionError("provider_denied", "raw provider rejection", details={"status": 401, "provider": "fixture"})


def uncaught_child_parent(payload, context):
    return context.children.run("denied-child", {}, request_id="denied", timeout_seconds=5)


denied_child.__execution_kernel_revision__ = "portable-denied-child-v1"
uncaught_child_parent.__execution_kernel_revision__ = "portable-uncaught-parent-v1"


class WorkerEntryProbe:
    __execution_kernel_revision__ = "portable-worker-entry-probe-v1"

    def __init__(self, directory, mode):
        self.directory, self.mode = directory, mode

    def __setstate__(self, state):
        self.__dict__.update(state)
        original = SQLiteKernel._checkpoint_handler_entry
        root, mode = Path(self.directory), self.mode

        def confirmation(kernel, lease, envelope, **kwargs):
            (root / "confirming").write_text("pending", encoding="ascii")
            if mode == "lock":
                with (root / "attempts").open("a", encoding="utf-8") as attempts:
                    attempts.write(json.dumps({"envelope": envelope.to_dict(),
                        "timeout_seconds": kwargs.get("timeout_seconds")}) + "\n")
            if mode == "fail":
                from dispatcher_sdk.execution_kernel.errors import CASConflictError
                raise CASConflictError("injected worker-side confirmation failure")
            if mode == "crash":
                os._exit(42)
            end = time.monotonic() + 5
            while not (root / "release").exists():
                if time.monotonic() >= end:
                    raise TimeoutError("entry probe was not released")
                time.sleep(.01)
            return original(kernel, lease, envelope, **kwargs)

        SQLiteKernel._checkpoint_handler_entry = confirmation

    def __call__(self, payload, context):
        (Path(self.directory) / "business").write_text("invoked", encoding="ascii")
        return context._kernel.get_execution_limits(context.command.execution_id)["entry_state"]


@unittest.skipUnless(sys.platform.startswith("linux") or os.name == "nt", "requires supported real process containment")
class WorkerEntryConfirmationTests(unittest.TestCase):
    def execute(self, mode):
        root = retained_directory("sdk-worker-entry-" + mode + "-")
        evidence = {"bounds": {"command_timeout": 3, "first_entry_wait": 15,
            "driver_join": 15, "writer_hold": .25}, "variant": mode}
        with _retained_deadline_runtime(self, root,
                {"probe": WorkerEntryProbe(str(root), mode)}, "process", evidence) as (runtime, capture):
            results, failures = [], []
            submitted = runtime.command("probe", execution_id="probe", idempotency_key="probe",
                correlation_id="probe", timeout_seconds=3, payload={})
            evidence["submitted_command"] = submitted.to_dict()
            runtime.submit(submitted)

            def drive():
                try:
                    result = runtime.run_once()
                    results.append(result)
                    evidence["original_return"] = None if result is None else result.to_dict()
                except Exception as exc:
                    failures.append(exc)
                    evidence["driver_error"] = _fixture_error(exc)

            driver = threading.Thread(target=drive)
            driver.start()
            try:
                end = time.monotonic() + 15
                while not (root / "confirming").exists() and driver.is_alive() and time.monotonic() < end:
                    time.sleep(.01)
                self.assertTrue((root / "confirming").exists())
                evidence["business_before_release"] = (root / "business").exists()
                self.assertFalse((root / "business").exists())
                # Observe the durable entry barrier without contending for
                # the parent's native-preparation control lock.
                with closing(sqlite3.connect((root / "kernel.db").as_uri() + "?mode=ro",
                                             uri=True, timeout=.1)) as reader:
                    entry = reader.execute("SELECT entry_state FROM kernel_execution_limits "
                        "WHERE execution_id = ?", ("probe",)).fetchone()
                evidence["original_pending_entry"] = entry
                self.assertEqual(("pending",), entry)
                if mode == "lock":
                    with closing(sqlite3.connect(root / "kernel.db", timeout=.1)) as writer:
                        with writer:
                            writer.execute("BEGIN IMMEDIATE")
                            (root / "release").write_text("released", encoding="ascii")
                            time.sleep(.25)
                            self.assertFalse((root / "business").exists())
            finally:
                (root / "release").write_text("released", encoding="ascii")
                driver.join(15)
                evidence["driver_join"] = {"alive": driver.is_alive(),
                    "errors": [_fixture_error(error) for error in failures]}
            self.assertFalse(driver.is_alive())
            self.assertEqual([], failures)
            capture("original-driver-return")
            result = _recover_original_publication(runtime, results[0], evidence)
            _assert_original_result(self, results[0], result, evidence)
            if mode in {"hold", "lock"}:
                self.assertEqual("succeeded", None if result is None else result.state,
                    None if result is None else result.to_dict())
                self.assertEqual("confirmed", result.result.value)
                self.assertTrue((root / "business").exists())
                if mode == "lock":
                    attempts = [json.loads(line) for line in (root / "attempts").read_text().splitlines()]
                    self.assertGreaterEqual(len(attempts), 2)
                    self.assertTrue(all(item["envelope"]["constraints"] == attempts[0]["envelope"]["constraints"]
                        and item["envelope"]["started_at"] == attempts[0]["envelope"]["started_at"] for item in attempts))
                    self.assertTrue(all(0 < item["timeout_seconds"] <= .1 for item in attempts))
                    persisted = runtime.kernel.get_execution_limits("probe")["envelope"]
                    self.assertEqual(attempts[0]["envelope"]["started_at"], persisted["started_at"])
                    self.assertEqual(attempts[0]["envelope"]["constraints"], persisted["constraints"])
            else:
                self.assertEqual("failed", None if result is None else result.state,
                    None if result is None else result.to_dict())
                if mode == "fail":
                    self.assertEqual("entry_confirmation_unknown", result.result.error.code)
                self.assertFalse((root / "business").exists())
                limits = runtime.kernel.get_execution_limits("probe")
                self.assertEqual("pending", limits["entry_state"])
                self.assertEqual([], limits["envelope"]["constraints"])

    def test_worker_requires_durable_confirmation_before_business(self):
        self.execute("hold")

    def test_worker_confirmation_failure_denies_business(self):
        self.execute("fail")

    def test_worker_retries_real_sqlite_writer_lock_without_new_entry_budget(self):
        self.execute("lock")

    def test_worker_crash_before_confirmation_keeps_first_entry_unresolved(self):
        self.execute("crash")


class RuntimeDeadlineEnvelopeTests(unittest.TestCase):
    def entry_context(self, timeout):
        effects = Mock()
        effects._kernel._wall_time.return_value = sample_clock().wall_at
        envelope = BudgetEnvelope((), sample_clock()).enter_handler(timeout, origin_id="execution:deadline-test")
        effects._kernel.confirm_handler_entry.side_effect = lambda lease, captured, **kwargs: captured
        return HandlerContext(command(timeout=timeout), None, effects, budget_envelope=envelope)

    def test_entry_busy_retries_emit_confirmed_marker_only_after_durable_success(self):
        context = self.entry_context(1)
        captured = context.budget_envelope
        context._kernel._checkpoint_handler_entry.side_effect = [sqlite3.OperationalError("database is locked"), captured]
        with patch.object(process_runtime, "_entry_packet", return_value={"kind": "worker_entered"}):
            packet = process_runtime._confirmed_entry_packet(context, None)
        self.assertIs(packet["entry_confirmed"], True)
        calls = context._kernel._checkpoint_handler_entry.call_args_list
        self.assertEqual(2, len(calls))
        self.assertTrue(all(call.args[1].constraints == captured.constraints
            and call.args[1].started_at == captured.started_at for call in calls))
        self.assertTrue(all(0 < call.kwargs["timeout_seconds"] <= .1 for call in calls))

    def test_permanent_entry_busy_exhausts_original_budget_without_ack(self):
        context = self.entry_context(.08)
        captured = context.budget_envelope
        context._kernel._checkpoint_handler_entry.side_effect = sqlite3.OperationalError("database is locked")
        with patch.object(process_runtime, "_entry_packet") as entry_packet:
            with self.assertRaises(HandlerExecutionError) as caught:
                process_runtime._confirmed_entry_packet(context, None)
        self.assertEqual("execution_deadline_exhausted", caught.exception.code)
        self.assertGreater(context._kernel._checkpoint_handler_entry.call_count, 1)
        self.assertTrue(all(call.args[1].constraints == captured.constraints
            and call.args[1].started_at == captured.started_at
            for call in context._kernel._checkpoint_handler_entry.call_args_list))
        entry_packet.assert_not_called()

    def test_entry_busy_retry_persists_forward_wall_watermark_after_rollback(self):
        context = self.entry_context(10)
        original = context.budget_envelope
        wall = original.checkpoint.wall_at
        seen = []

        def confirm(lease, envelope, **kwargs):
            seen.append(envelope)
            if len(seen) == 1:
                context._kernel._wall_time.return_value = wall + 6
                context.budget
                context._kernel._wall_time.return_value = wall
                raise sqlite3.OperationalError("database is locked")
            return envelope

        context._kernel._checkpoint_handler_entry.side_effect = confirm
        with patch.object(process_runtime, "_entry_packet", return_value={}):
            packet = process_runtime._confirmed_entry_packet(context, None)
        self.assertTrue(packet["entry_confirmed"])
        self.assertGreaterEqual(seen[-1].checkpoint.wall_at, wall + 6)
        self.assertEqual(original.constraints, seen[-1].constraints)
        self.assertEqual(original.started_at, seen[-1].started_at)
        self.assertLessEqual(context.budget.remaining_work_seconds, 4)

    def test_close_degradation_preserves_explicit_final_flush_receipt(self):
        for state in ("unknown", "degraded", "pending"):
            with self.subTest(state=state):
                receipt = {"state": state, "reason": "final write unavailable",
                    "final_flush_persisted": False, "source_closed": False}
                context = Mock()
                context.close.return_value = receipt
                closed = process_runtime._close_context(context)
                self.assertEqual("unknown", closed["state"])
                self.assertEqual(receipt, closed["receipt"])

    def test_recorder_close_keeps_source_facts_when_process_observer_is_incomplete(self):
        root = retained_directory("sdk-observer-close-receipt-")
        identity = ObservationIdentity("observer-close", 1, 1)
        journal = ObservationJournal(root / "observations.sqlite3", kernel_path=root / "kernel.sqlite3",
            source_id="observer-receipt-store", options=ObservationOptions(write_timeout=.1))
        journal.bind_current(identity)
        cases = [
            ({"complete": True, "collector_alive": True}, "pending"),
            ({"unfinished_collector": True}, "pending"),
            ({"complete": False, "collector_alive": False}, "degraded"),
            ({"complete": True, "error": "collector failed"}, "degraded"),
            ({"complete": True, "processes": [{"collection_error": "process write failed"}]}, "degraded"),
            ({"complete": True, "collector_alive": False, "unfinished_collector": False, "error": None,
              "processes": [{"state": "unknown", "unknown_reason": "birth metadata inaccessible", "collection_error": None}]}, "persisted"),
        ]
        receipts = []
        for report, expected in cases:
            with self.subTest(report=report):
                recorder = ActivityRecorder(journal, identity)
                observer = SimpleNamespace(_stop=threading.Event(), _wake=threading.Event(), _thread=None,
                    close=Mock(return_value=report))
                recorder._process_observer = observer
                recorder.report_bytes("stdout", b"final")
                receipt = recorder.close(timeout=.4)
                receipts.append(receipt)
                self.assertEqual(expected, receipt["state"], receipt)
                self.assertTrue(receipt["final_flush_persisted"], receipt)
                self.assertTrue(receipt["source_closed"], receipt)
                self.assertEqual(report, receipt["process_observer"])
                self.assertTrue(observer._stop.is_set())
                observer.close.assert_called_once()
                self.assertLessEqual(observer.close.call_args.kwargs["timeout"], .1)
                with closing(sqlite3.connect(journal.path)) as connection:
                    row = connection.execute("SELECT state,metrics_json FROM obs_sources WHERE source_id=?",
                        (recorder.source_id,)).fetchone()
                self.assertEqual("closed", row[0])
                self.assertEqual(5, json.loads(row[1])["stdout_bytes"]["count"])
                context = Mock()
                context.close.return_value = receipt
                closed = process_runtime._close_context(context)
                self.assertEqual("confirmed" if expected == "persisted" else "unknown", closed["state"])
        recorder = ActivityRecorder(journal, identity)
        recorder._process_observer = SimpleNamespace(_stop=threading.Event(), _wake=threading.Event(), _thread=None,
            close=Mock(return_value={"unfinished_collector": True}))
        with patch.object(journal, "close_source", side_effect=RuntimeError("original source close failure")):
            receipt = recorder.close(timeout=.4)
        receipts.append(receipt)
        self.assertEqual("degraded", receipt["state"], receipt)
        self.assertEqual("source_close_failed", receipt["reason"], receipt)
        self.assertEqual("original source close failure", receipt["error"])
        self.assertTrue(receipt["final_flush_persisted"])
        self.assertFalse(receipt["source_closed"])
        self.assertTrue(receipt["process_observer"]["unfinished_collector"])
        (root / "receipts.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")

    def test_worker_close_refuses_negative_nested_receipts_and_bounds_the_summary(self):
        reports = [
            {"complete": True, "collector_alive": True},
            {"unfinished_collector": True},
            {"complete": False},
            {"complete": True, "error": "x" * 10000},
            {"complete": True, "processes": [{"collection_error": "y" * 10000,
                "arbitrary_snapshot": "z" * 10000} for _ in range(100)]},
        ]
        for report in reports:
            for state in ("persisted", "pending", "degraded"):
                with self.subTest(report=report.keys(), state=state):
                    receipt = {"state": state, "final_flush_persisted": True, "source_closed": True,
                        "process_observer": report}
                    if state != "persisted":
                        receipt["reason"] = "original source failure"
                    context = Mock()
                    context.close.return_value = receipt
                    closed = process_runtime._close_context(context)
                    self.assertEqual("unknown", closed["state"], closed)
                    self.assertEqual("process_observer_incomplete" if state == "persisted" else "original source failure",
                        closed["reason"])
                    summary = closed["receipt"]["process_observer"]
                    self.assertNotIn("processes", summary)
                    self.assertLessEqual(len(summary.get("error", "")), 2048)
                    errors = summary.get("process_collection_errors", [])
                    self.assertLessEqual(len(errors), 32)
                    self.assertLessEqual(sum(map(len, errors)), 2048)
                    self.assertTrue(closed["receipt"]["source_closed"])
                    self.assertTrue(closed["receipt"]["final_flush_persisted"])
                    context.close.assert_called_once_with()
        context.close.return_value = {"state": "persisted", "process_observer": {
            "complete": True, "collector_alive": False, "unfinished_collector": False, "error": None,
            "processes": [{"state": "unknown", "unknown_reason": "inaccessible", "collection_error": None}]}}
        self.assertEqual({"state": "confirmed"}, process_runtime._close_context(context))
        context._budget_capture._pending = None
        context.close.return_value = {"state": "persisted", "budget_checkpoint": {"state": "unknown"},
            "process_observer": {"complete": False}}
        closed = process_runtime._close_context(context)
        self.assertEqual("unknown", closed["state"])
        self.assertEqual("owned budget checkpoint remains pending", closed["reason"])
        self.assertEqual({"complete": False}, closed["receipt"]["process_observer"])

    def test_uncaught_child_failure_preserves_original_provider_result(self):
        modes = ["thread"]
        if sys.platform.startswith("linux") or os.name == "nt":
            modes.append("process")
        for mode in modes:
            root = retained_directory("sdk-provider-child-failure-" + mode + "-")
            evidence = {"bounds": {"parent_timeout": 12, "child_timeout": 5}}
            with self.subTest(mode=mode):
                with _retained_deadline_runtime(self, root, {"parent": uncaught_child_parent,
                        "denied-child": denied_child}, mode, evidence) as (runtime, capture):
                    submitted = runtime.command("parent", execution_id="parent", idempotency_key="parent",
                        correlation_id="provider-failure", timeout_seconds=12, payload={})
                    evidence["submitted_command"] = submitted.to_dict()
                    runtime.submit(submitted)
                    result = runtime.run_once()
                    evidence["original_return"] = None if result is None else result.to_dict()
                    capture("original-run-once-return")
                    original = result
                    result = _recover_original_publication(runtime, original, evidence)
                    _assert_original_result(self, original, result, evidence)
                    self.assertEqual("failed", None if result is None else result.state,
                        None if result is None else result.to_dict())
                    details = result.result.error.details
                    child_result = details.get("child_result") if type(details) is dict else None
                    self.assertEqual("provider_denied", result.result.error.code,
                        f"parent_error={result.result.error.to_dict()!r}; child_result={child_result!r}")
                    child_result = details["child_result"]
                    captured_child = next((item for item in evidence["original_results"]
                        if (item["execution_id"], item["attempt"], item["fence"]) ==
                        (child_result["execution_id"], child_result["attempt"], child_result["fence"])), None)
                    evidence["captured_child_result"] = deepcopy(captured_child)
                    if captured_child is not None:
                        self.assertEqual(captured_child, child_result)
                    self.assertEqual(child_result["execution_id"], details["child_execution_id"])
                    self.assertEqual("parent", child_result["causation_id"])
                    self.assertEqual("provider_denied", child_result["error"]["code"])
                    self.assertEqual("raw provider rejection", child_result["error"]["message"])
                    self.assertEqual({"status": 401, "provider": "fixture"}, child_result["error"]["details"])

    def test_flush_descendant_pid_reuse_outside_lineage_is_not_signalled(self):
        close = Mock()
        signal_process = Mock()
        kill_signal = object()
        process_os = SimpleNamespace(pidfd_open=Mock(return_value=99), close=close)
        process_signal = SimpleNamespace(pidfd_send_signal=signal_process, SIGKILL=kill_signal)
        with patch.object(process_runtime, "os", process_os), patch.object(
                process_runtime, "signal", process_signal), patch.object(
                process_runtime, "_descendant_process_ids", side_effect=[(42, 43), (43,)]):
            self.assertTrue(process_runtime._stop_flush_descendants(1, 43))
        signal_process.assert_not_called()
        close.assert_called_once_with(99)

    def test_flush_descendant_signal_uses_acquired_process_handle(self):
        close = Mock()
        signal_process = Mock()
        kill_signal = object()
        process_os = SimpleNamespace(pidfd_open=Mock(return_value=99), close=close)
        process_signal = SimpleNamespace(pidfd_send_signal=signal_process, SIGKILL=kill_signal)
        with patch.object(process_runtime, "os", process_os), patch.object(
                process_runtime, "signal", process_signal), patch.object(process_runtime, "_descendant_process_ids",
                return_value=(42, 43)):
            self.assertTrue(process_runtime._stop_flush_descendants(1, 43))
        signal_process.assert_called_once_with(99, kill_signal)
        close.assert_called_once_with(99)

    @staticmethod
    def capture_process_cleanup(receipts):
        backend = windows_runtime if os.name == "nt" else runtime_module
        name = "invoke_windows_handler" if os.name == "nt" else "invoke_process_handler"
        original = getattr(backend, name)

        def capture(**kwargs):
            confirmed = kwargs["on_cleanup_confirmed"]

            def receipt():
                receipts.append("job_empty" if os.name == "nt" else "tree_reaped")
                confirmed()

            kwargs["on_cleanup_confirmed"] = receipt
            return original(**kwargs)

        return patch.object(backend, name, capture)

    @staticmethod
    def capture_actual_descendant_stop(paths, root):
        if os.name == "nt":
            original = windows_runtime.WindowsProcessHandle.stop_descendants

            def stop_descendants(handle, until):
                contained = original(handle, until)
                if not Path(paths["stop_result"]).exists():
                    Path(paths["stop_result"]).write_text(json.dumps({
                        "host_pid": os.getpid(), "launcher_pid": handle.pid,
                        "worker_pid": handle._worker_pid, "contained": contained,
                        "returned_at": time.monotonic(),
                    }), encoding="ascii")
                    Path(paths["release"]).write_text("released", encoding="ascii")
                return contained

            return patch.object(windows_runtime.WindowsProcessHandle, "stop_descendants", stop_descendants)

        hook = root / "sitecustomize.py"
        hook.write_text(
            "import json, os\n"
            "from pathlib import Path\n"
            "from dispatcher_sdk.execution_kernel import _process_runtime\n"
            "_original_stop = _process_runtime._stop_flush_descendants\n"
            "def _record_stop(root_pid, worker_pid):\n"
            "    contained = _original_stop(root_pid, worker_pid)\n"
            "    result = Path(os.environ['DISPATCHER_SDK_TEST_STOP_RESULT'])\n"
            "    if not result.exists():\n"
            "        result.write_text(json.dumps({'supervisor_pid': root_pid, 'worker_pid': worker_pid, "
            "'contained': contained, "
            "'returned_at': __import__('time').monotonic()}), encoding='ascii')\n"
            "        Path(os.environ['DISPATCHER_SDK_TEST_STOP_RELEASE']).write_text('released', encoding='ascii')\n"
            "    return contained\n"
            "_process_runtime._stop_flush_descendants = _record_stop\n",
            encoding="utf-8")
        python_path = os.pathsep.join(filter(None, (
            str(root), str(Path(__file__).resolve().parents[1] / "src"), os.environ.get("PYTHONPATH"),
        )))
        return patch.dict(os.environ, {
            "PYTHONPATH": python_path,
            "DISPATCHER_SDK_TEST_STOP_RESULT": paths["stop_result"],
            "DISPATCHER_SDK_TEST_STOP_RELEASE": paths["release"],
        })

    @unittest.skipUnless(sys.platform.startswith("linux") or os.name == "nt", "requires supported real process containment")
    def test_business_return_stops_orphan_before_held_final_journal_flush(self):
        root = retained_directory("sdk-orphan-final-flush-")
        keys = ("orphan", "orphan_ready", "release", "business_returning", "stop_result",
                "flush_started", "flush_done")
        paths = {key: str(root / key) for key in keys}
        receipts = []
        result = None
        evidence = {
            "test": self.id(),
            "interpreter": {"executable": sys.executable, "version": sys.version},
            "sdk_import": {"module": dispatcher_sdk.__file__, "runtime_module": runtime_module.__file__},
            "limits": {"execution_timeout_seconds": 3, "held_final_flush_seconds": .4},
            "result": None,
            "result_error": None,
            "runtime_exception": None,
            "process_cleanup_receipts": receipts,
        }
        try:
            with Runtime(str(root / "kernel.db"), {"held-flush": orphan_with_held_final_flush},
                         isolation_mode="process") as runtime:
                runtime.submit(runtime.command("held-flush", execution_id="held-flush", idempotency_key="held-flush",
                    correlation_id="held-flush", timeout_seconds=3, payload=paths))
                stop_boundary = self.capture_actual_descendant_stop(paths, root)
                with self.capture_process_cleanup(receipts), stop_boundary:
                    result = runtime.run_once()
                evidence["result"] = result.to_dict()
                evidence["result_error"] = (None if result.result is None or result.result.error is None
                    else result.result.error.to_dict())
        except BaseException as exc:
            evidence["runtime_exception"] = {
                "type": type(exc).__name__, "message": str(exc), "repr": repr(exc),
                "traceback": traceback.format_exc(),
            }
            raise
        finally:
            evidence["markers"] = {}
            for key, marker in paths.items():
                try:
                    contents = Path(marker).read_text(encoding="utf-8")
                except Exception as exc:
                    evidence["markers"][key] = {
                        "path": marker,
                        "read_error": {"type": type(exc).__name__, "message": str(exc),
                                       "repr": repr(exc), "errno": getattr(exc, "errno", None)},
                    }
                else:
                    evidence["markers"][key] = {"path": marker, "contents": contents}
            evidence_path = root / "evidence.json"
            evidence_path.write_text(json.dumps(evidence, indent=2, allow_nan=False), encoding="utf-8")
            print("orphan_final_flush_evidence=" + str(evidence_path), flush=True)

        self.assertIsNotNone(result)
        self.assertEqual("succeeded", result.state)
        self.assertEqual({"completed": True}, result.result.value)
        self.assertTrue(Path(paths["orphan_ready"]).exists(), "orphan never reached its release gate")
        self.assertTrue(Path(paths["release"]).exists(), "descendant stop boundary never released the fixture")
        stop_result = json.loads(Path(paths["stop_result"]).read_text(encoding="ascii"))
        self.assertIs(stop_result["contained"], True, f"descendant stop failed: {stop_result!r}")
        self.assertTrue(Path(paths["flush_started"]).exists())
        self.assertTrue(Path(paths["flush_done"]).exists())
        ready = json.loads(Path(paths["orphan_ready"]).read_text(encoding="ascii"))
        business_returning = json.loads(Path(paths["business_returning"]).read_text(encoding="ascii"))
        flush_started = json.loads(Path(paths["flush_started"]).read_text(encoding="ascii"))
        flush_done = json.loads(Path(paths["flush_done"]).read_text(encoding="ascii"))
        self.assertTrue(ready["pid"] > 0)
        # The ready/release files enforce the causal ordering. Windows
        # clocks may give adjacent stages the same monotonic tick.
        self.assertLessEqual(business_returning["returned_at"], stop_result["returned_at"])
        self.assertLessEqual(stop_result["returned_at"], flush_started["started_at"])
        self.assertLess(flush_started["started_at"], flush_done["finished_at"])
        self.assertFalse(Path(paths["orphan"]).exists(), "orphan escaped after stop release")
        self.assertEqual(["job_empty" if os.name == "nt" else "tree_reaped"], receipts)

    @unittest.skipUnless(sys.platform.startswith("linux") or os.name == "nt", "requires supported real process containment")
    def test_real_child_stops_at_inherited_parent_deadline(self):
        from tests._storage_evidence import StorageEvidence

        root = retained_directory("sdk-inherited-parent-deadline-")
        storage_evidence = StorageEvidence(root, self)
        storage_evidence.start(include_kernel=True)
        self.addCleanup(storage_evidence.stop)
        self.addCleanup(storage_evidence.save)
        payload = {key: str(root / key) for key in ("entered", "escaped")}
        receipts, invocations = [], deque(maxlen=16)
        original_results = deque(maxlen=16)
        evidence_lock = threading.Lock()
        evidence = {"test": self.id(), "interpreter": sys.executable,
            "sdk_import": dispatcher_sdk.__file__, "runtime_import": runtime_module.__file__,
            "backend_import": (windows_runtime if os.name == "nt" else process_runtime).__file__,
            "bounds": {"parent_timeout": 5, "child_timeout": 30, "child_sleep": 6,
                "elapsed_limit": 12, "child_settlement_wait": 3, "escape_wait": 1.2},
            "payload": payload}
        backend = windows_runtime if os.name == "nt" else runtime_module
        name = "invoke_windows_handler" if os.name == "nt" else "invoke_process_handler"
        original_invoke = getattr(backend, name)

        def raw_error(error):
            return {"type": type(error).__name__, "message": str(error), "repr": repr(error),
                "errno": getattr(error, "errno", None),
                "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
                "traceback": traceback.format_exc()}

        def capture_callback(callback, label, events):
            def observed(*args, **kwargs):
                facts = [deepcopy(arg) if isinstance(arg, (dict, str, int, float, bool, type(None))) else
                    {"type": type(arg).__name__, "pid": getattr(arg, "pid", None)} for arg in args]
                event = {"callback": label, "began": time.monotonic(), "arguments": facts}
                with evidence_lock:
                    events.append(event)
                try:
                    result = callback(*args, **kwargs)
                except BaseException as error:
                    failure = raw_error(error)
                    with evidence_lock:
                        event["error"] = failure
                    raise
                else:
                    with evidence_lock:
                        event["returned"] = result
                    return result
                finally:
                    with evidence_lock:
                        event["elapsed"] = time.monotonic() - event["began"]
            return observed

        def capture_invocation(**kwargs):
            events = deque(maxlen=128)
            invocation = {"began": time.monotonic(), "thread": threading.current_thread().name,
                "command": kwargs["command"].to_dict(), "lease": kwargs["lease"].to_dict(),
                "start_timeout": kwargs["start_timeout"], "db_path": kwargs["db_path"],
                "durability": kwargs.get("durability"), "callbacks": events,
                "envelope": None if kwargs.get("budget_envelope") is None else kwargs["budget_envelope"].to_dict()}
            with evidence_lock:
                invocations.append(invocation)
            for label in ("on_started", "on_finished", "on_cleanup_confirmed", "on_entered", "on_phase"):
                callback = kwargs.get(label)
                if callback is not None:
                    kwargs[label] = capture_callback(callback, label, events)
            try:
                outcome = original_invoke(**kwargs)
            except BaseException as error:
                failure = raw_error(error)
                with evidence_lock:
                    invocation["error"] = failure
                raise
            else:
                with evidence_lock:
                    invocation["outcome"] = deepcopy(outcome)
                return outcome
            finally:
                with evidence_lock:
                    invocation["elapsed"] = time.monotonic() - invocation["began"]

        def raise_secondary(error, error_traceback):
            raise error.with_traceback(error_traceback)

        def capture_secondary(label, error):
            evidence.setdefault("secondary_errors", []).append({"stage": label, **raw_error(error)})
            # unittest reports cleanup errors separately from the original
            # assertion; diagnostic failure must not replace its traceback.
            self.addCleanup(raise_secondary, error, error.__traceback__)

        runtime = None
        try:
            runtime = Runtime(str(root / "kernel.db"), {"deadline-parent": inherited_deadline_parent,
                "deadline-child": inherited_deadline_child}, isolation_mode="process")
            with patch.object(backend, name, capture_invocation), self.capture_process_cleanup(receipts):
                original_result = runtime._outcome_result

                def capture_result(*args, **kwargs):
                    result = original_result(*args, **kwargs)
                    with evidence_lock:
                        original_results.append({"captured_at": time.monotonic(),
                            "result": result.to_dict()})
                    return result

                result_patch = patch.object(runtime, "_outcome_result", capture_result)
                result_patch.start()
                self.addCleanup(result_patch.stop)
                parent = runtime.command("deadline-parent", execution_id="parent", idempotency_key="parent",
                    correlation_id="inherited", timeout_seconds=5, payload=payload)
                evidence["submitted_parent"] = parent.to_dict()
                runtime.submit(parent)
                began = time.monotonic()
                result = runtime.run_once()
                evidence["parent_elapsed"] = time.monotonic() - began
                evidence["parent_returned"] = result.to_dict()
                evidence["runtime_at_return"] = {"settlement_error": runtime._settlement_error,
                    "observation_error": runtime._observation_error,
                    "diagnostic_errors": dict(runtime._diagnostic_errors),
                    "lifecycle_lock": repr(runtime._lifecycle_lock),
                    "threads": [{"name": thread.name, "ident": thread.ident,
                        "native_id": thread.native_id, "alive": thread.is_alive()}
                        for thread in threading.enumerate()],
                    "original_pending": [{"identity": entry.identity, "payload": entry.payload,
                        "evidence": entry.evidence} for entry in runtime._pending_settlements.entries()]}
                storage_evidence.save(phase="original-run-once-return", checkpoint={
                    "parent_returned": evidence["parent_returned"],
                    "parent_elapsed": evidence["parent_elapsed"],
                    "runtime_at_return": evidence["runtime_at_return"]})
                self.assertLess(evidence["parent_elapsed"], 12)
                self.assertIn(result.state, {"running", "timed_out"})
                self.assertTrue(Path(payload["entered"]).exists(), "child never reached actual handler entry")
                # One existing maintenance window covers both exact outcomes.
                # recover_completions publishes retained facts without another
                # run_once, handler invocation, or execution-budget renewal.
                settlement_began = time.monotonic()
                end = settlement_began + 3
                evidence["settlement_deadline"] = end
                def maintenance_remaining(stage):
                    remaining = end-time.monotonic()
                    evidence["maintenance_stage"] = stage
                    evidence["settlement_elapsed"] = time.monotonic()-settlement_began
                    self.assertGreater(remaining, 0,
                        "original shared settlement window expired at " + stage)
                    return remaining

                def maintenance_read(stage, read, execution_id):
                    with runtime.kernel._control_lock(maintenance_remaining(stage)):
                        value = read(execution_id)
                    maintenance_remaining(stage + " completed")
                    return value

                initial = runtime.observe("parent", timeout=maintenance_remaining("parent observation"))
                maintenance_remaining("parent observation completed")
                evidence["original_settlement_observation"] = initial
                waits = initial["child_waits"]
                self.assertEqual(1, len(waits))
                child_id = waits[0]["target_execution_id"]
                limits = maintenance_read("child limits", runtime.kernel.get_execution_limits, child_id)
                self.assertTrue(any(item["source"] == "parent" for item in limits["envelope"]["constraints"]))
                reports = []
                evidence["settlement_reports"] = reports
                while True:
                    final_parent = maintenance_read("parent winner", runtime.kernel.get, "parent")
                    final_child = maintenance_read("child winner", runtime.kernel.get, child_id)
                    evidence["canonical_parent"] = final_parent.to_dict()
                    evidence["canonical_child"] = final_child.to_dict()
                    if final_parent.state == "timed_out" and final_child.state in {"timed_out", "cancelled", "dead"}:
                        break
                    reports.extend(runtime.recover_completions(
                        timeout_seconds=min(.5, maintenance_remaining("completion recovery"))))
                    remaining = end-time.monotonic()
                    if remaining > 0:
                        time.sleep(min(.02, remaining))
                evidence["settlement_elapsed"] = time.monotonic()-settlement_began
                storage_evidence.save(phase="settlement-boundary", checkpoint={
                    "original_parent": evidence["parent_returned"],
                    "canonical_parent": evidence["canonical_parent"],
                    "canonical_child": evidence["canonical_child"],
                    "elapsed": evidence["settlement_elapsed"], "deadline": end,
                    "reports": reports})
                self.assertEqual("timed_out", final_parent.state)
                self.assertIn(final_child.state, {"timed_out", "cancelled", "dead"})
                with evidence_lock:
                    originals = {item["result"]["execution_id"]: item["result"]
                                 for item in original_results}
                    native = list(invocations)
                self.assertEqual({"parent", child_id}, set(originals))
                self.assertEqual(originals["parent"], final_parent.result.to_dict())
                if final_child.state == "timed_out":
                    self.assertEqual(originals[child_id], final_child.result.to_dict())
                else:
                    # A cancellation/reaper winner is immutable. Maintenance
                    # keeps the native timeout as a superseded obligation;
                    # it must never replace that winner to satisfy this test.
                    reports.extend(runtime.recover_completions(
                        timeout_seconds=min(.5, maintenance_remaining("superseded completion recovery"))))
                    child_observation = runtime.observe(child_id,
                        timeout=maintenance_remaining("superseded child observation"))
                    maintenance_remaining("superseded child observation completed")
                    evidence["child_settlement_observation"] = child_observation
                    superseded = [receipt for receipt in child_observation.get("settlement_obligations", ())
                        if receipt.get("state") == "superseded"
                        and receipt.get("result", {}).get("result_id") == originals[child_id]["result_id"]]
                    self.assertEqual(1, len(superseded), "original native timeout needs a superseded receipt")
                    self.assertEqual(originals[child_id], superseded[0]["result"])
                    self.assertEqual({"execution_id": child_id, "attempt": final_child.attempt,
                        "fence": final_child.fence}, superseded[0]["identity"])
                    evidence["superseded_child_original"] = superseded[0]
                    preserved_winner = maintenance_read(
                        "preserved child winner", runtime.kernel.get, child_id).to_dict()
                    evidence["preserved_child_winner"] = preserved_winner
                    self.assertEqual(evidence["canonical_child"], preserved_winner)
                    self.assertNotEqual(originals[child_id]["result_id"], final_child.result.result_id)
                maintenance_remaining("exact settlement proof completed")
                evidence["settlement_elapsed"] = time.monotonic()-settlement_began
                self.assertLess(evidence["settlement_elapsed"], 3)
                self.assertEqual(2, len(native), "maintenance must not replay either handler")
                self.assertEqual({"parent", child_id}, {item["command"]["execution_id"] for item in native})
                self.assertTrue(all(item["outcome"]["kind"] == "timeout" for item in native))
                entered_pids = {str(event["arguments"][0]["worker_pid"]) for item in native
                    if item["command"]["execution_id"] == child_id for event in item["callbacks"]
                    if event["callback"] == "on_entered"}
                self.assertEqual({Path(payload["entered"]).read_text(encoding="ascii")}, entered_pids)
                self.assertEqual(["job_empty" if os.name == "nt" else "tree_reaped"] * 2, receipts)
                time.sleep(1.2)
                self.assertFalse(Path(payload["escaped"]).exists())
        except BaseException as error:
            evidence["fixture_error"] = raw_error(error)
            try:
                storage_evidence.save(phase="original-failure", checkpoint={
                    "fixture_error": evidence["fixture_error"],
                    "parent_returned": evidence.get("parent_returned"),
                    "canonical_parent": evidence.get("canonical_parent"),
                    "canonical_child": evidence.get("canonical_child"),
                    "maintenance_stage": evidence.get("maintenance_stage"),
                    "settlement_elapsed": evidence.get("settlement_elapsed"),
                    "settlement_deadline": evidence.get("settlement_deadline")})
            except BaseException as capture_error:
                capture_secondary("original-failure storage evidence", capture_error)
            raise
        finally:
            if runtime is not None:
                try:
                    runtime.close()
                    evidence["runtime_cleanup"] = {"returned": True}
                except BaseException as cleanup_error:
                    evidence["runtime_cleanup"] = {"error": raw_error(cleanup_error)}
                    capture_secondary("Runtime.close", cleanup_error)
            try:
                storage_evidence.save(phase="runtime-cleanup", checkpoint={
                    "fixture_error": evidence.get("fixture_error"),
                    "runtime_cleanup": evidence.get("runtime_cleanup"),
                    "secondary_errors": evidence.get("secondary_errors", [])})
            except BaseException as capture_error:
                capture_secondary("runtime-cleanup storage evidence", capture_error)
            try:
                with evidence_lock:
                    evidence["invocations"] = deepcopy(list(invocations))
                    evidence["original_results"] = deepcopy(list(original_results))
                for invocation in evidence["invocations"]:
                    invocation["callbacks"] = list(invocation["callbacks"])
                evidence["cleanup_receipts"] = list(receipts)
                evidence["markers"] = {}
                for key, path in payload.items():
                    try:
                        evidence["markers"][key] = {"path": path, "contents": Path(path).read_text(encoding="ascii")}
                    except OSError as error:
                        evidence["markers"][key] = {"path": path, "read_error": raw_error(error)}
                evidence["storage"] = {}
                stores = {"kernel.db": ("kernel_executions", "kernel_execution_limits", "kernel_events"),
                    "kernel.db.observations.sqlite3": ("sdk_child_requests", "sdk_child_waits", "obs_current", "obs_processes", "obs_events"),
                    "kernel.db.settlements.sqlite3": ("settlement_records", "settlement_notes")}
                for filename, tables in stores.items():
                    snapshot = {"path": str(root / filename), "tables": {}}
                    evidence["storage"][filename] = snapshot
                    deadline = time.monotonic() + .2
                    try:
                        with closing(sqlite3.connect((root / filename).as_uri() + "?mode=ro", uri=True, timeout=0)) as connection:
                            connection.row_factory = sqlite3.Row
                            connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
                            for table in tables:
                                sql = f"SELECT * FROM {table} LIMIT 65"
                                try:
                                    rows = connection.execute(sql).fetchall()
                                    snapshot["tables"][table] = {"sql": sql, "rows": [dict(row) for row in rows[:64]],
                                        "truncated": len(rows) > 64}
                                except sqlite3.Error as error:
                                    snapshot["tables"][table] = {"sql": sql, "read_error": raw_error(error)}
                    except sqlite3.Error as error:
                        snapshot["read_error"] = raw_error(error)
                path = root / "evidence.json"
                path.write_text(json.dumps(evidence, indent=2, default=repr), encoding="utf-8")
                print("inherited_parent_deadline_evidence=" + str(path), flush=True)
            except BaseException as capture_error:
                capture_secondary("final raw evidence", capture_error)
                print("inherited_parent_deadline_evidence_error=" + repr(capture_error), flush=True)

    def test_callable_entry_ack_follows_authority_setup(self):
        events = []
        context = Mock()
        context.effects.effect_ids = []
        context._enter_handler.side_effect = lambda: events.append("authority")
        result = process_runtime.invoke_handler(lambda payload, ctx: events.append("callable"),
            command(), context, on_entered=lambda ctx: events.append("entered_ack"))
        self.assertEqual(events, ["authority", "entered_ack", "callable"])
        self.assertEqual(result["kind"], "ok")

    def test_unknown_clock_and_exhausted_work_do_not_spawn_or_create_job(self):
        native = sample_clock()
        unknown = BudgetEnvelope((DeadlineConstraint("run-a", "run", native.wall_at + 100),),
                                 ClockCheckpoint(native.wall_at, native.elapsed_at, "other-boot"))
        expired = BudgetEnvelope((DeadlineConstraint("run-a", "run", native.wall_at + 10, 20),), native)
        for backend, spawn in ((process_runtime.invoke_process_handler, "multiprocessing.get_context"),
                               (windows_runtime.invoke_windows_handler, "_WinAPI")):
            module = process_runtime if backend is process_runtime.invoke_process_handler else windows_runtime
            for envelope, kind in ((unknown, "error"), (expired, "timeout")):
                with self.subTest(backend=backend.__name__, kind=kind), patch.object(
                        module.multiprocessing if module is process_runtime else module,
                        "get_context" if module is process_runtime else spawn) as launcher:
                    outcome = backend(db_path="unused.db", handler=echo, command=command(), lease=None,
                                      now=None, start_timeout=30, budget_envelope=envelope)
                    self.assertEqual(outcome["kind"], kind)
                    self.assertIsNone(outcome["started_at"])
                    self.assertEqual(outcome["limiting_source"], "run")
                    launcher.assert_not_called()
                    if kind == "error":
                        self.assertEqual(outcome["code"], "budget_clock_unknown")
                        self.assertTrue(outcome["control_error"])

    def test_posix_guard_entry_preserves_run_and_separates_cleanup_reserve(self):
        native = sample_clock()
        inherited = BudgetEnvelope((DeadlineConstraint("run-a", "run", native.wall_at + 10, 3),), native)
        entered = inherited.enter_handler(20, origin_id="execution:a", sample=native)
        packet = {"budget_envelope": entered.to_dict(), "deadline_monotonic": time.monotonic() + 20,
                  "hard_deadline_monotonic": time.monotonic() + 20}
        guard = process_runtime._DeadlineGuard(time.monotonic() + 30, inherited, None)
        guard.entered(packet)
        self.assertLessEqual(guard.deadline, time.monotonic() + 7)
        self.assertGreater(guard.hard_deadline - guard.deadline, 2.9)
        interval_timer = object()
        timer_api = SimpleNamespace(ITIMER_REAL=interval_timer, setitimer=Mock())
        with patch.object(process_runtime, "signal", timer_api):
            guard.begin_cleanup()
        self.assertTrue(guard.cleanup)
        self.assertLessEqual(guard.deadline, guard.hard_deadline)
        timer_api.setitimer.assert_called_once()

    def test_posix_timer_detects_suspend_elapsed_without_a_storage_read(self):
        native = sample_clock()
        if not native.domain_id.startswith("linux-boot:"):
            self.skipTest("requires Linux suspend-inclusive native clock")
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", native.wall_at + 10),), native)
        guard = process_runtime._DeadlineGuard(time.monotonic() + 10, envelope, None)
        with patch.object(process_runtime.time, "clock_gettime", return_value=native.elapsed_at + 11):
            self.assertLessEqual(guard.remaining(), 0)

    def test_ready_to_entry_transition_cannot_undo_observed_forward_wall_jump(self):
        native = sample_clock()
        envelope = BudgetEnvelope((DeadlineConstraint("run-a", "run", native.wall_at + 100, 10),), native)
        wall = [native.wall_at + 80]
        guard = process_runtime._DeadlineGuard(time.monotonic() + 30, envelope, lambda: wall[0])
        original = guard.deadline
        wall[0] = native.wall_at + 5
        entered = envelope.enter_handler(200, origin_id="execution:a", sample=sample_clock(wall_time=wall[0]))
        guard.entered({"budget_envelope": entered.to_dict(), "deadline_monotonic": time.monotonic() + 200,
                       "hard_deadline_monotonic": time.monotonic() + 200})
        self.assertLessEqual(guard.deadline, original)
        handle = Mock()
        wall[0] = native.wall_at + 80
        watchdog = windows_runtime._Watchdog(handle, time.monotonic() + 30, envelope, lambda: wall[0])
        try:
            original = watchdog.inherited_work_deadline
            wall[0] = native.wall_at + 5
            actual = watchdog.business_deadline(200, envelope=entered, deadline=time.monotonic() + 200)
            self.assertLessEqual(actual, original)
        finally:
            watchdog.close()

    def test_windows_watchdog_enforces_work_and_reconstructs_entry_deadline(self):
        native = sample_clock()
        inherited = BudgetEnvelope((DeadlineConstraint("tool-a", "tool", native.wall_at + 1, .8),), native)
        handle = Mock()
        terminated = threading.Event()
        handle.terminate.side_effect = lambda: terminated.set() or True
        watchdog = windows_runtime._Watchdog(handle, time.monotonic() + 10, inherited)
        try:
            actual = inherited.enter_handler(10, origin_id="execution:a")
            deadline = watchdog.business_deadline(100, envelope=actual, deadline=time.monotonic() + 100)
            self.assertEqual(actual.constraints[0], inherited.constraints[0])
            self.assertLessEqual(deadline, watchdog.inherited_work_deadline)
            self.assertTrue(terminated.wait(2))
            self.assertTrue(watchdog.expired)
        finally:
            watchdog.close()

    def test_windows_watchdog_unknown_clock_still_stops_owned_process(self):
        native = sample_clock()
        unknown = BudgetEnvelope((DeadlineConstraint("run-a", "run", native.wall_at + 10),),
                                 ClockCheckpoint(native.wall_at, native.elapsed_at, "other-boot"))
        handle = Mock()
        terminated = threading.Event()
        handle.terminate.side_effect = lambda: terminated.set() or True
        watchdog = windows_runtime._Watchdog(handle, time.monotonic() + 10, unknown)
        try:
            self.assertTrue(terminated.wait(2))
            self.assertIsNotNone(watchdog.clock_error)
        finally:
            watchdog.close()

    @unittest.skipUnless(os.name == "posix", "requires real POSIX isolation")
    def test_actual_worker_entry_and_persisted_budget_survive_protocol(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "kernel.db")
            with SQLiteKernel(path) as kernel:
                cmd = command()
                kernel.submit(cmd)
                lease = kernel.claim_and_start("deadline-test-owner")
                envelope = kernel.admission_budget(lease)
                entries = []

                def observe_entry(packet):
                    entries.append(packet)
                    raise RuntimeError("telemetry collector failed")

                outcome = process_runtime.invoke_process_handler(db_path=path, handler=echo,
                    command=cmd, lease=lease, now=None, start_timeout=10, budget_envelope=envelope,
                    on_entered=observe_entry)
                self.assertEqual(outcome["kind"], "ok", outcome)
                self.assertIsNotNone(outcome["started_at"])
                self.assertEqual(outcome["started_at"], outcome["value"]["started_at"])
                stored = kernel.get_execution_limits(cmd.execution_id)
                self.assertEqual(stored["envelope"]["started_at"], outcome["started_at"])
                self.assertEqual(outcome["limiting_source"], "execution")
                self.assertEqual(len(entries), 1)
                self.assertNotEqual(entries[0]["worker_pid"], os.getpid())
                self.assertEqual(entries[0]["process_evidence"]["source"], "worker_self_report")
                if envelope.checkpoint.domain_id.startswith("linux-boot:"):
                    self.assertIsNotNone(entries[0]["birth_identity"])

    @unittest.skipUnless(os.name == "posix", "requires real POSIX isolation")
    def test_parent_work_deadline_stops_already_running_real_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "kernel.db")
            pidfile, late = Path(temp) / "pid", Path(temp) / "late"
            with SQLiteKernel(path) as kernel:
                cmd = command({"pid": str(pidfile), "late": str(late)})
                kernel.submit(cmd)
                lease = kernel.claim_and_start("deadline-test-owner")
                native = sample_clock()
                envelope = BudgetEnvelope((DeadlineConstraint("parent-a", "parent", native.wall_at + 2, .5),), native)
                begun = time.monotonic()
                outcome = process_runtime.invoke_process_handler(db_path=path, handler=blocked,
                    command=cmd, lease=lease, now=None, start_timeout=10, budget_envelope=envelope)
                self.assertEqual(outcome["kind"], "timeout", outcome)
                self.assertEqual(outcome["limiting_source"], "parent")
                self.assertIsNotNone(outcome["started_at"])
                self.assertLess(time.monotonic() - begun, 3)
                self.assertTrue(pidfile.exists(), outcome)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pidfile.read_text(encoding="ascii")), 0)
                self.assertFalse(late.exists())


if __name__ == "__main__":
    unittest.main()
