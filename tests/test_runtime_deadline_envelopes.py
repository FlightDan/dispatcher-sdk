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
from contextlib import closing
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
from tests._acceptance_evidence import retained_directory


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
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, failures = [], []
            with Runtime(str(root / "kernel.db"), {"probe": WorkerEntryProbe(temporary, mode)},
                         isolation_mode="process") as runtime:
                runtime.submit(runtime.command("probe", execution_id="probe", idempotency_key="probe",
                    correlation_id="probe", timeout_seconds=3, payload={}))

                def drive():
                    try:
                        results.append(runtime.run_once())
                    except Exception as exc:
                        failures.append(exc)

                driver = threading.Thread(target=drive)
                driver.start()
                try:
                    end = time.monotonic() + 15
                    while not (root / "confirming").exists() and driver.is_alive() and time.monotonic() < end:
                        time.sleep(.01)
                    self.assertTrue((root / "confirming").exists())
                    self.assertFalse((root / "business").exists())
                    self.assertEqual("pending", runtime.kernel.get_execution_limits("probe")["entry_state"])
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
                self.assertFalse(driver.is_alive())
                self.assertEqual([], failures)
                if mode in {"hold", "lock"}:
                    self.assertEqual("succeeded", results[0].state, results[0].result.error)
                    self.assertEqual("confirmed", results[0].result.value)
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
                    self.assertEqual("failed", results[0].state)
                    if mode == "fail":
                        self.assertEqual("entry_confirmation_unknown", results[0].result.error.code)
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

    def test_uncaught_child_failure_preserves_original_provider_result(self):
        modes = ["thread"]
        if sys.platform.startswith("linux") or os.name == "nt":
            modes.append("process")
        for mode in modes:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                with Runtime(str(Path(temporary) / "kernel.db"), {"parent": uncaught_child_parent,
                        "denied-child": denied_child}, isolation_mode=mode) as runtime:
                    runtime.submit(runtime.command("parent", execution_id="parent", idempotency_key="parent",
                        correlation_id="provider-failure", timeout_seconds=12, payload={}))
                    result = runtime.run_once()
                    self.assertEqual("failed", result.state)
                    details = result.result.error.details
                    child_result = details.get("child_result") if type(details) is dict else None
                    self.assertEqual("provider_denied", result.result.error.code,
                        f"parent_error={result.result.error.to_dict()!r}; child_result={child_result!r}")
                    child_result = details["child_result"]
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
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {key: str(root / key) for key in ("entered", "escaped")}
            receipts = []
            with Runtime(str(root / "kernel.db"), {"deadline-parent": inherited_deadline_parent,
                    "deadline-child": inherited_deadline_child}, isolation_mode="process") as runtime, self.capture_process_cleanup(receipts):
                runtime.submit(runtime.command("deadline-parent", execution_id="parent", idempotency_key="parent",
                    correlation_id="inherited", timeout_seconds=5, payload=payload))
                began = time.monotonic()
                result = runtime.run_once()
                self.assertEqual("timed_out", result.state)
                self.assertLess(time.monotonic() - began, 12)
                self.assertTrue(Path(payload["entered"]).exists(), "child never reached actual handler entry")
                waits = runtime.observe("parent")["child_waits"]
                self.assertEqual(1, len(waits))
                child_id = waits[0]["target_execution_id"]
                limits = runtime.kernel.get_execution_limits(child_id)
                self.assertTrue(any(item["source"] == "parent" for item in limits["envelope"]["constraints"]))
                end = time.monotonic() + 3
                while runtime.kernel.get(child_id).state in {"queued", "leased", "running"} and time.monotonic() < end:
                    time.sleep(.02)
                self.assertIn(runtime.kernel.get(child_id).state, {"timed_out", "cancelled", "dead"})
                self.assertEqual(["job_empty" if os.name == "nt" else "tree_reaped"] * 2, receipts)
                time.sleep(1.2)
                self.assertFalse(Path(payload["escaped"]).exists())

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
        self.assertLessEqual(guard.deadline - time.monotonic(), 7)
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
