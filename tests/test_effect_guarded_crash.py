"""A real crash cannot turn an uncaptured clock sample into replay authority."""
from __future__ import annotations

import contextlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import sqlite3
import threading
import time
import traceback
import unittest

import dispatcher_sdk
from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import _sqlite_execution
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.orchestrator import Orchestrator
from tests._acceptance_evidence import retained_directory


class Clock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


def append_then_crash(payload, context):
    with open(payload["invocations"], "a", encoding="utf-8") as invocation:
        invocation.write(str(context.lease.attempt) + "\n")

    def perform():
        with open(payload["marker"], "a", encoding="utf-8") as marker:
            marker.write("mutation\n")
            marker.flush()
            os.fsync(marker.fileno())
        os._exit(37)

    return context.effects.execute_once(payload["effect_id"], "append-file", payload, perform)


append_then_crash.__execution_kernel_revision__ = "guarded-crash-mutation-v1"
HANDLERS = {"mutate": append_then_crash}


def snapshot(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        return {name: [dict(row) for row in connection.execute(query)] for name, query in {
            "executions": "SELECT * FROM kernel_executions",
            "limits": "SELECT * FROM kernel_execution_limits",
            "sampling_guards": "SELECT token,execution_id,reason FROM kernel_budget_samples",
            "effects": "SELECT * FROM kernel_effects",
        }.items()}
    finally:
        connection.rollback()
        connection.close()


def event(root, phase, **facts):
    record = dict(phase=phase, pid=os.getpid(), monotonic=time.monotonic(), **facts)
    with (Path(root) / ("worker-%s.jsonl" % os.getpid())).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def run_worker(path, now, root, crash):
    exit_ready = threading.Event()
    marker_committed = threading.Event()
    hold_original_window = threading.Event()
    original_exit = os._exit
    original_begin = SQLiteKernel._begin_budget_sample
    original_claim = _sqlite_execution._next_claim_row

    def coordinated_exit(code):
        if code == 37:
            before = snapshot(path)
            envelope = BudgetEnvelope.from_dict(json.loads(before["limits"][0]["envelope_json"]))
            deadline = envelope.deadline_monotonic(
                sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
            event(root, "mutation_before_real_exit", original_native_deadline=deadline, facts=before)
            exit_ready.set()
            witnessed = marker_committed.wait(max(0., deadline - time.monotonic()))
            event(root, "real_exit", exit_code=code, marker_witnessed=witnessed, facts=snapshot(path))
        return original_exit(code)

    def committed_before_exit(kernel, execution_id, **options):
        original_timeout = options["timeout_seconds"]
        deadline = time.monotonic() + original_timeout
        token = original_begin(kernel, execution_id, **options)
        if execution_id == "execution" and exit_ready.is_set():
            event(root, "sample_marker_committed", token=token,
                  original_timeout=original_timeout, original_control_deadline=deadline,
                  facts=snapshot(path))
            marker_committed.set()
            # Consume only this real caller's original control window. The
            # actual handler exits before a new sample or ACK can complete.
            hold_original_window.wait(max(0., deadline - time.monotonic()))
        return token

    def observed_claim(connection, timestamp, revisions, execution_id=None):
        selected = original_claim(connection, timestamp, revisions, execution_id)
        # Read the exact original transaction; no new claim or clock sample.
        event(root, "claim", timestamp=timestamp, execution_id=execution_id,
              selected=None if selected is None else dict(selected),
              sampling_guards=[dict(row) for row in connection.execute(
                  "SELECT token,execution_id,reason FROM kernel_budget_samples")])
        return selected

    if crash:
        os._exit = coordinated_exit
        SQLiteKernel._begin_budget_sample = committed_before_exit
    _sqlite_execution._next_claim_row = observed_claim
    with (Path(root) / ("worker-%s.stdout" % os.getpid())).open("w", encoding="utf-8", buffering=1) as output:
        with (Path(root) / ("worker-%s.stderr" % os.getpid())).open("w", encoding="utf-8", buffering=1) as errors:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                runtime = Kernel.open_sqlite(path, HANDLERS, now=Clock(now),
                    lease_seconds=2, isolation_mode="thread")
                try:
                    event(root, "worker_before", crash=crash, facts=snapshot(path))
                    returned = runtime.run_once()
                    event(root, "worker_return", returned=None if returned is None else returned.to_dict(),
                          facts=snapshot(path))
                except BaseException as error:
                    event(root, "worker_error", error_type=type(error).__name__, message=str(error))
                    traceback.print_exc()
                    raise
                finally:
                    runtime.close()
                    os._exit = original_exit
                    SQLiteKernel._begin_budget_sample = original_begin
                    _sqlite_execution._next_claim_row = original_claim


class EffectGuardedCrashTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-effect-guarded-crash-")
        self.path = self.root / "state.sqlite3"
        self.marker = self.root / "mutation.txt"
        self.invocations = self.root / "invocations.txt"
        self.clock = Clock()
        self.evidence = {"sdk_import": dispatcher_sdk.__file__, "workers": []}
        self.addCleanup(lambda: (self.root / "evidence.json").write_text(
            json.dumps(self.evidence, indent=2), encoding="utf-8"))
        print("effect_guarded_crash_evidence=" + str(self.root / "evidence.json"), flush=True)

    def open_stack(self):
        self.runtime = Kernel.open_sqlite(self.path, HANDLERS, now=self.clock,
            lease_seconds=2, isolation_mode="thread")
        self.addCleanup(self.runtime.close)
        self.sdk = Orchestrator(self.path, self.runtime.kernel, runtime=self.runtime, clock=self.clock)

    def child_worker(self, *, crash, expected_exit):
        process = multiprocessing.get_context("spawn").Process(target=run_worker,
            args=(str(self.path), self.clock.value, str(self.root), crash))
        process.start()
        try:
            process.join(15)
            self.evidence["workers"].append(dict(pid=process.pid, crash=crash,
                exit_code=process.exitcode, alive=process.is_alive()))
            self.assertFalse(process.is_alive(), "guarded recovery worker exceeded its deadline")
            self.assertEqual(process.exitcode, expected_exit)
            return process.pid
        finally:
            if process.is_alive():
                process.kill()
                process.join(5)
            process.close()

    def worker_events(self, pid):
        return [json.loads(line) for line in (self.root / ("worker-%s.jsonl" % pid)).read_text(
            encoding="utf-8").splitlines()]

    def test_applied_effect_keeps_uncaptured_crash_sample_fenced(self):
        self.open_stack()
        command = ExecutionCommandV2(execution_id="execution", idempotency_key="original-key",
            registry_revision=self.runtime.registry_revision, correlation_id="run", causation_id=None,
            handler_id="mutate", handler_contract_version=1, timeout_seconds=20,
            retry_policy=RetryPolicy(max_attempts=1, initial_backoff_seconds=0,
                backoff_multiplier=1, max_backoff_seconds=0),
            payload={"marker": str(self.marker), "invocations": str(self.invocations),
                "effect_id": "file-effect", "operation_id": "original-operation"})
        self.sdk.create_run("run", command_id="create")
        self.sdk.apply_operations("run", command_id="dispatch", expected_revision=0,
            application_state={"business_repairs_used": 0}, operations=[
                {"kind": "add_task", "task_id": "task", "command": command.to_dict()},
                {"kind": "dispatch", "task_id": "task"}])
        self.assertEqual(self.sdk.flush(), 1)
        self.runtime.close()

        crash_pid = self.child_worker(crash=True, expected_exit=37)
        crash_events = self.worker_events(crash_pid)
        armed = next(item for item in crash_events if item["phase"] == "sample_marker_committed")
        exited = next(item for item in crash_events if item["phase"] == "real_exit")
        self.assertTrue(exited["marker_witnessed"])
        representation_error = (math.ulp(armed["original_control_deadline"])
                                + math.ulp(armed["monotonic"]))
        self.assertLessEqual(armed["original_timeout"] - .1, representation_error)
        self.assertLess(armed["monotonic"], exited["monotonic"])
        crashed = snapshot(self.path)
        self.evidence.update(crash_events=crash_events, crashed=crashed)
        guard = {"token": armed["token"], "execution_id": "execution", "reason": "sampling"}
        self.assertEqual(armed["facts"]["sampling_guards"], [guard])
        self.assertEqual(exited["facts"]["sampling_guards"], [guard])
        self.assertEqual(crashed["sampling_guards"], [guard])
        original_limits = armed["facts"]["limits"]
        self.assertEqual(crashed["limits"], original_limits)
        envelope = BudgetEnvelope.from_dict(json.loads(original_limits[0]["envelope_json"]))
        self.assertGreater(envelope.view(sample=sample_clock(
            wall_time=envelope.checkpoint.wall_at)).remaining_work_seconds, 0)

        self.open_stack()
        running = self.sdk.inspect_execution("execution")
        self.assertEqual((running.state, running.attempt, running.fence), ("running", 1, 1))
        self.assertEqual(self.runtime.kernel.get_effect("file-effect").state, "performing")
        self.runtime.kernel.require_effect_recovery(running.lease, "file-effect")
        response = {"receipt": "original-operation", "content": self.marker.read_text(encoding="utf-8")}
        effect = self.runtime.kernel.get_effect("file-effect")
        resolved = self.sdk.resolve_effect("file-effect", decision="applied", response=response,
            expected_revision=effect.revision, recovery_id="original-reconciliation")
        self.assertEqual((resolved.state, resolved.response), ("committed", response))
        reconciled = snapshot(self.path)
        self.evidence["reconciled"] = reconciled
        self.assertEqual(reconciled["sampling_guards"], [guard])
        self.assertEqual(reconciled["limits"], original_limits)
        self.runtime.close()

        replay_pid = self.child_worker(crash=False, expected_exit=0)
        replay_events = self.worker_events(replay_pid)
        replay_claim = next(item for item in replay_events if item["phase"] == "claim")
        self.assertIsNone(replay_claim["selected"])
        self.assertEqual(replay_claim["sampling_guards"], [guard])
        self.assertIsNone(next(item for item in replay_events if item["phase"] == "worker_return")["returned"])
        self.open_stack()
        self.sdk.sync()
        queued = self.sdk.inspect_execution("execution")
        after = snapshot(self.path)
        self.evidence.update(replay_events=replay_events, after=after)
        self.assertEqual((queued.state, queued.attempt, queued.fence), ("queued", 1, 1))
        self.assertIsNone(queued.result)
        self.assertEqual(queued.command.to_dict(), command.to_dict())
        self.assertEqual(after["sampling_guards"], [guard])
        self.assertEqual(after["limits"], original_limits)
        self.assertEqual(self.runtime.kernel.get_effect("file-effect"), resolved)
        self.assertEqual(self.invocations.read_text(encoding="utf-8"), "1\n")
        self.assertEqual(self.marker.read_text(encoding="utf-8"), "mutation\n")
        self.assertEqual(self.runtime.kernel.result_outbox(), [])
        run = self.sdk.get_run("run")
        self.assertEqual(run["state"], "running")
        self.assertEqual(run["application_state"], {"business_repairs_used": 0})
        self.assertEqual(len(run["tasks"]["task"]["attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
