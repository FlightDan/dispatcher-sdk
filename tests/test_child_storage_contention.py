"""SQLite writer contention must not manufacture child business failures."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
import traceback
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel.children import HandlerChildren
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope
from dispatcher_sdk.execution_kernel.runtime import Runtime
from dispatcher_sdk.observability import ObservationOptions


class WitnessList(list):
    """External test recorder; observations do not change handler deployment state."""


class ChildStorageContentionTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory("sdk-child-storage-contention-")
        self.evidence = {"test": self.id(), "records": []}
        self.addCleanup(self.retain_evidence)
        self.options = ObservationOptions(write_timeout=.05, query_timeout=.3, flush_interval=.1)

    def retain_evidence(self):
        path = self.root / "evidence.json"
        path.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
        print("child_storage_contention_evidence=" + str(path), flush=True)

    def runtime(self, parent, child):
        parent.__execution_kernel_revision__ = "storage-contention-parent-v1"
        child.__execution_kernel_revision__ = "storage-contention-child-v1"
        runtime = Runtime(self.root / "kernel.sqlite3", {"parent": parent, "child": child},
            isolation_mode="thread", child_capacity=1, observation_options=self.options)
        self.addCleanup(runtime.close)
        return runtime

    def drive(self, runtime, *, timeout=6):
        runtime.submit(runtime.command("parent", execution_id="parent", idempotency_key="parent",
            correlation_id="storage-contention", timeout_seconds=timeout, payload={}))
        outcomes, errors = [], []
        def run():
            try:
                outcomes.append(runtime.run_once(execution_id="parent"))
            except BaseException as exc:
                errors.append(exc)
        thread = threading.Thread(target=run)
        self.addCleanup(lambda: thread.join(8))
        thread.start()
        return thread, outcomes, errors

    @contextmanager
    def writer(self, path):
        connection = sqlite3.connect(path, timeout=1)
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        finally:
            connection.rollback()
            connection.close()

    def requests(self, runtime):
        with runtime.observation_journal._read_connection(.3) as (connection, _):
            return [dict(row) for row in connection.execute("SELECT * FROM sdk_child_requests")]

    def poll(self, predicate, *, seconds=4):
        cutoff = time.monotonic() + seconds
        while time.monotonic() < cutoff:
            result = predicate()
            if result:
                return result
            time.sleep(.02)
        self.fail("original bounded fixture window expired")

    def witness_readiness(self, event, seconds, runtime, driver, outcomes, errors, **facts):
        wait_started = time.monotonic()
        reached = event.wait(seconds)
        wait_finished = time.monotonic()
        record = {"readiness_reached": reached, "driver_alive": driver.is_alive(),
            "outcomes": [item.to_dict() for item in outcomes],
            "driver_errors": [{"type": type(error).__name__, "message": str(error)} for error in errors],
            "original_readiness_timeout": seconds,
            "wait_started_monotonic": wait_started, "wait_finished_monotonic": wait_finished,
            "original_readiness_deadline": wait_started + seconds,
            **{key: list(value) if isinstance(value, list) else value for key, value in facts.items()}}
        self.evidence["records"].append(record)
        if not reached:
            frames = sys._current_frames()
            record["workers"] = [{"name": thread.name,
                "stack": traceback.format_stack(frames[thread.ident])[-10:]}
                for thread in threading.enumerate() if thread.ident in frames][:24]
            try:
                if not runtime._thread_lock.acquire(timeout=.1):
                    raise TimeoutError("fixture thread evidence admission elapsed")
                try:
                    record["contexts"] = [{"execution_id": generation[0], "attempt": generation[1],
                        "fence": generation[2], "authority_active": context.effects._is_active(),
                        "entered": context._entered, "entry_confirmed": context._entry_confirmed,
                        "budget_envelope": None if context._budget_envelope is None else context._budget_envelope.to_dict()}
                        for generation, context in tuple(runtime._thread_contexts.items())[:16]]
                finally:
                    runtime._thread_lock.release()
            except Exception as error:
                record["context_capture_error"] = {"type": type(error).__name__, "message": str(error)}
            for name, operation in (("parent", lambda: runtime.kernel.get("parent").to_dict()),
                                    ("requests", lambda: self.requests(runtime))):
                try:
                    with runtime.kernel._control_lock(.1):
                        record[name] = operation()
                except Exception as error:
                    record[name + "_error"] = {"type": type(error).__name__, "message": str(error)}
            record["capture_finished_monotonic"] = time.monotonic()
        self.assertTrue(reached, json.dumps(record, indent=2))

    def finish(self, driver, outcomes, errors):
        driver.join(8)
        self.assertFalse(driver.is_alive())
        self.assertEqual([], errors)
        self.assertEqual(1, len(outcomes))
        return outcomes[0]

    def test_observation_enqueue_busy_retries_one_original_child(self):
        entered, release = threading.Event(), threading.Event()
        calls, original = WitnessList(), WitnessList()
        self.addCleanup(release.set)
        def child(payload, context):
            calls.append(context.lease.execution_id)
            return {"raw_child": 42}
        def parent(payload, context):
            original.append(context.budget_envelope.to_dict())
            entered.set()
            if not release.wait(2):
                raise TimeoutError("reservation fixture was not released")
            return context.children.run("child", {}, request_id="one", timeout_seconds=3)
        runtime = self.runtime(parent, child)
        driver, outcomes, errors = self.drive(runtime)
        self.assertTrue(entered.wait(2))
        with self.writer(runtime.observation_journal.path):
            release.set()
            time.sleep(.35)
            self.assertEqual([], calls)
            self.assertEqual([], self.requests(runtime))
        result = self.finish(driver, outcomes, errors)
        self.assertEqual("succeeded", result.state, result.to_dict())
        rows = self.requests(runtime)
        self.assertEqual(1, len(rows))
        self.assertEqual([rows[0]["child_execution_id"]], calls)
        self.assertEqual("completed", rows[0]["state"])
        self.assertEqual(runtime.kernel.get(calls[0]).result.to_dict(), result.result.value)
        limits = runtime.kernel.get_execution_limits("parent")
        self.assertEqual(original[0]["constraints"], limits["envelope"]["constraints"])

    def test_kernel_busy_during_await_preserves_already_successful_child(self):
        waiting, resume, delivered = threading.Event(), threading.Event(), threading.Event()
        calls, row_seen, returned = WitnessList(), WitnessList(), WitnessList()
        self.addCleanup(resume.set)
        original_await = HandlerChildren._await
        def gated_await(capability, row):
            if capability.command.execution_id == "parent":
                row_seen.append(dict(row))
                waiting.set()
                if not resume.wait(3):
                    raise TimeoutError("await fixture was not released")
            return original_await(capability, row)
        def child(payload, context):
            calls.append(context.lease.execution_id)
            return {"original_result": [1, 2, 3]}
        def parent(payload, context):
            value = context.children.run("child", {}, request_id="one", timeout_seconds=3)
            returned.append(value)
            delivered.set()
            return value
        runtime = self.runtime(parent, child)
        with patch.object(HandlerChildren, "_await", gated_await):
            driver, outcomes, errors = self.drive(runtime)
            self.witness_readiness(waiting, 2, runtime, driver, outcomes, errors,
                parent_timeout=6, child_timeout=3, calls=calls, await_rows=row_seen)
            self.poll(lambda: self.requests(runtime)[0]["state"] == "completed", seconds=2)
            raw_result = runtime.kernel.get(row_seen[0]["child_execution_id"]).result.to_dict()
            with self.writer(runtime.kernel.db_path):
                resume.set()
                time.sleep(.35)
                self.evidence["records"].append({"stage": "kernel_writer_held",
                    "child_delivered": delivered.is_set(), "returned": list(returned),
                    "driver_alive": driver.is_alive(), "calls": list(calls)})
                self.assertTrue(delivered.is_set(), "the committed child result must remain readable")
                self.assertEqual([raw_result], returned)
            snapshot = self.finish(driver, outcomes, errors)
            # run_once may return the original running snapshot when the
            # parent's independent publication encounters this same writer.
            # Recover only that original result; never invoke either handler.
            def settled_parent():
                runtime.recover_completions(timeout_seconds=.1)
                current = runtime.kernel.get("parent")
                return current if current.state == "succeeded" else None
            result = self.poll(settled_parent, seconds=2)
            self.evidence["records"].append({"stage": "original_parent_settled",
                "run_once_snapshot": snapshot.to_dict(), "canonical": result.to_dict()})
        self.assertEqual("succeeded", result.state, result.to_dict())
        self.assertEqual(raw_result, result.result.value)
        self.assertEqual([row_seen[0]["child_execution_id"]], calls)
        self.assertEqual(1, len(self.requests(runtime)))

    def test_failed_ownership_release_reclaims_same_result_without_reinvocation(self):
        entered, return_child = threading.Event(), threading.Event()
        calls = WitnessList()
        self.addCleanup(return_child.set)
        def child(payload, context):
            calls.append(context.lease.execution_id)
            self.evidence["records"].append({"stage": "actual_child_entry",
                "monotonic": time.monotonic(), "envelope": context.budget_envelope.to_dict()})
            entered.set()
            if not return_child.wait(2):
                raise TimeoutError("child fixture was not released")
            return {"raw_fact": "original successful child"}
        def parent(payload, context):
            self.evidence["records"].append({"stage": "original_child_call",
                "monotonic": time.monotonic(), "envelope": context.budget_envelope.to_dict()})
            return context.children.run("child", {}, request_id="one", timeout_seconds=3)
        runtime = self.runtime(parent, child)
        driver, outcomes, errors = self.drive(runtime, timeout=4)
        self.witness_readiness(entered, 2, runtime, driver, outcomes, errors,
            parent_timeout=4, child_timeout=3, calls=calls)
        row = self.requests(runtime)[0]
        with self.writer(runtime.observation_journal.path):
            return_child.set()
            self.poll(lambda: runtime.kernel.get(row["child_execution_id"]).state == "succeeded", seconds=2.5)
            # Keep the actual independent writer through the original caller's
            # expiry. A failed finish/owner release cannot erase this row.
            time.sleep(3.3)
            retained = self.requests(runtime)[0]
            self.assertEqual(row["child_execution_id"], retained["child_execution_id"])
            self.assertIn(retained["state"], {"pending", "running"})
        self.finish(driver, outcomes, errors)
        settled = self.poll(lambda: (rows[0] if (rows := self.requests(runtime)) and rows[0]["state"] == "completed" else None))
        raw_result = runtime.kernel.get(row["child_execution_id"]).result.to_dict()
        self.assertEqual(raw_result, json.loads(settled["response_json"]))
        self.assertEqual(row["wait_id"], settled["wait_id"])
        original_budget = BudgetEnvelope.from_dict(json.loads(row["budget_json"]))
        settled_budget = BudgetEnvelope.from_dict(json.loads(settled["budget_json"]))
        # Recovery may retain a stronger wall-clock sample. It must preserve
        # every original deadline and must never restore spent authority.
        self.assertEqual(original_budget.constraints, settled_budget.constraints)
        self.assertLessEqual(settled_budget.view(sample=settled_budget.checkpoint).remaining_work_seconds,
            original_budget.view(sample=settled_budget.checkpoint).remaining_work_seconds)
        self.assertEqual([row["child_execution_id"]], calls)

    def test_reservation_retry_expires_without_late_child_admission(self):
        entered, release = threading.Event(), threading.Event()
        calls = WitnessList()
        self.addCleanup(release.set)
        def child(payload, context):
            calls.append(context.lease.execution_id)
            return {}
        def parent(payload, context):
            entered.set()
            if not release.wait(1):
                raise TimeoutError("expiry fixture was not released")
            return context.children.run("child", {}, request_id="one", timeout_seconds=.25)
        runtime = self.runtime(parent, child)
        driver, outcomes, errors = self.drive(runtime, timeout=.55)
        self.witness_readiness(entered, .4, runtime, driver, outcomes, errors,
            parent_timeout=.55, child_timeout=.25, calls=calls)
        with self.writer(runtime.observation_journal.path):
            release.set()
            time.sleep(.8)
            self.assertEqual([], self.requests(runtime))
        result = self.finish(driver, outcomes, errors)
        self.assertNotEqual("succeeded", result.state)
        time.sleep(.15)
        self.assertEqual([], calls)
        self.assertEqual([], self.requests(runtime))

    def test_parent_cancellation_ends_reservation_retry_without_admission(self):
        entered, release = threading.Event(), threading.Event()
        calls = WitnessList()
        self.addCleanup(release.set)
        def child(payload, context):
            calls.append(context.lease.execution_id)
            return {}
        def parent(payload, context):
            entered.set()
            if not release.wait(2):
                raise TimeoutError("cancellation fixture was not released")
            return context.children.run("child", {}, request_id="one", timeout_seconds=3)
        runtime = self.runtime(parent, child)
        driver, outcomes, errors = self.drive(runtime)
        self.assertTrue(entered.wait(2))
        with self.writer(runtime.observation_journal.path):
            release.set()
            time.sleep(.15)
            snapshot = runtime.kernel.get("parent")
            runtime.kernel.cancel("parent", expected_revision=snapshot.revision, reason="causal test cancellation")
            time.sleep(.2)
            self.assertEqual([], self.requests(runtime))
        result = self.finish(driver, outcomes, errors)
        self.assertEqual("cancelled", result.state)
        time.sleep(.15)
        self.assertEqual([], calls)
        self.assertEqual([], self.requests(runtime))


if __name__ == "__main__":
    unittest.main()
