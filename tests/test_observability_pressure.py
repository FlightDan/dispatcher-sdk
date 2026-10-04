"""Portable native A12/A13 witnesses; preserve raw evidence outside fixtures."""
import json
from itertools import count
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import dispatcher_sdk
from dispatcher_sdk import Dispatcher, ObservationOptions, StallPolicy
from dispatcher_sdk.execution_kernel import CASConflictError, Kernel
from dispatcher_sdk.observability import inspect_execution


_snapshot_sequence = count()


def open_snapshot(path):
    path = Path(path)
    generations = path.with_name(path.name + ".snapshots")
    try:
        latest = max((candidate for candidate in generations.iterdir()
                      if candidate.suffix == ".json"), default=path)
    except FileNotFoundError:
        latest = path
    return latest.open(encoding="utf-8")


def publish_snapshot(path, value):
    # Each path has one producer with its original 8-second execution window
    # and a .01-second child output cadence. Retain their finite generations
    # so readers never race deletion or replace an open Windows destination.
    path = Path(path)
    generations = path.with_name(path.name + ".snapshots")
    generations.mkdir(exist_ok=True)
    destination = generations / f"{next(_snapshot_sequence):020d}.json"
    write_json(destination, value)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, default=str), encoding="utf-8")
    temporary.replace(path)


def quiet_pressure_handler(payload, context):
    root = Path(payload["root"])
    write_json(root / "entered.json", {"pid": os.getpid(), "at": time.time(),
        "execution_id": context.command.execution_id, "budget": context.budget.to_dict()})
    while not (root / "release").exists():
        if (root / "progress").exists() and not (root / "confirmed.json").exists():
            write_json(root / "confirmed.json", context.activity.progress("actual-new-work"))
        context.activity.heartbeat()
        time.sleep(.03)
    return {"actual_pid": os.getpid()}


def history_pressure_handler(payload, context):
    failures = []

    def persist():
        # A bounded telemetry write may decline a batch under host pressure.
        # Keep its raw receipt and drain that finite queue before producing more.
        end = time.monotonic() + min(3, context.budget.remaining_work_seconds)
        while True:
            receipt = context.activity.flush()
            if receipt["state"] == "persisted":
                return receipt
            failures.append(receipt)
            transient = receipt.get("retryable") or "OperationalError: interrupted" in receipt.get("error", "")
            if not transient or time.monotonic() >= end:
                raise RuntimeError("history flush was not persisted: " + repr(receipt))
            time.sleep(.01)

    for number in range(10_000):
        while context.activity.phase("pressure-summary", details={"number": number})["state"] != "captured":
            time.sleep(.001)
        if number % 64 == 63:
            persist()
    receipt = persist()
    return {"events": 10_000, "receipt": receipt, "pid": os.getpid(), "write_degradation": failures}


def streaming_pressure_handler(payload, context):
    root = Path(payload["root"])
    context.activity.enable_stream("stdout")
    write_json(root / "entered.json", {"pid": os.getpid(), "at": time.time(),
        "execution_id": context.command.execution_id, "budget": context.budget.to_dict()})
    while not (root / "start-output").exists():
        time.sleep(.01)
    source = """
import json, os, pathlib, sys, time
sys.path[:] = %r
from %s import publish_snapshot
root = pathlib.Path(sys.argv[1])
count = 0
while True:
    if (root / 'escape-release').exists():
        (root / 'escaped').write_text('descendant survived its owner')
    os.write(1, b'x' * 512)
    count += 512
    publish_snapshot(root / 'child.json', {'pid': os.getpid(), 'bytes': count, 'at': time.time()})
    time.sleep(.01)
""" % (sys.path, __name__)
    child = subprocess.Popen([sys.executable, "-u", "-c", source, str(root)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    context.activity.observe_process(child, role="tool", process_id="native-output")
    with child.stdout:
        while True:
            chunk = child.stdout.read(512)
            if not chunk:
                break
            context.activity.report_bytes("stdout", chunk)
            for number in range(12):
                context.activity.phase("output-summary", details={"number": number})
            snapshot = context.activity.snapshot()
            snapshot.pop("tails", None)
            publish_snapshot(root / "local.json", snapshot)
    return {"unexpected_child_exit": child.wait()}


for handler in (quiet_pressure_handler, history_pressure_handler, streaming_pressure_handler):
    handler.__execution_kernel_revision__ = "portable-observability-pressure-v1"


class ObservabilityPressureTests(unittest.TestCase):
    def setUp(self):
        evidence_directory = os.environ.get("SDK_ACCEPTANCE_EVIDENCE_DIR")
        if evidence_directory:
            Path(evidence_directory).mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="sdk-observability-pressure-", dir=evidence_directory))
        self.evidence = {"platform": sys.platform, "interpreter": sys.executable,
            "sdk_import": dispatcher_sdk.__file__, "started_at": time.time(), "records": []}
        self.addCleanup(self.save_evidence)

    def save_evidence(self):
        result = self._outcome.result
        self.evidence["test"] = self.id()
        self.evidence["test_failures"] = [{"test": case.id(), "raw_failure": failure}
            for case, failure in (*result.errors, *result.failures)
            if case.id().startswith(self.id())]
        self.evidence["finished_at"] = time.time()
        write_json(self.root / "evidence.json", self.evidence)
        print("PRESSURE_EVIDENCE " + json.dumps({"path": str(self.root / "evidence.json"),
            "platform": sys.platform, "interpreter": sys.executable,
            "sdk_import": dispatcher_sdk.__file__}), flush=True)

    def wait_for(self, query, predicate=bool, *, seconds=15):
        deadline = time.monotonic() + seconds
        last = None
        while time.monotonic() < deadline:
            last = query()
            if predicate(last):
                return last
            time.sleep(.02)
        self.fail("stage deadline expired: " + repr(last))

    def read_json(self, path):
        try:
            with open_snapshot(path) as reader:
                return json.load(reader)
        except FileNotFoundError:
            return None
        except PermissionError as error:
            native_code = getattr(error, "winerror", None)
            if os.name != "nt" or not (native_code in (5, 32, 33)
                    or (native_code is None and error.errno == 13)):
                raise
            # The caller's existing stage loop owns all retries and its one
            # original deadline. Access/sharing failures remain unknown facts.
            errors = self.evidence.setdefault("snapshot_read_errors", [])
            if len(errors) < 128:
                errors.append({"path": str(path), "at": time.time(),
                    "type": type(error).__name__, "message": str(error),
                    "errno": error.errno, "winerror": native_code,
                    "reason": "native_access_or_sharing_unknown"})
            else:
                self.evidence["snapshot_read_errors_omitted"] = self.evidence.get(
                    "snapshot_read_errors_omitted", 0) + 1
            return None

    def encoded(self, report):
        return len(json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode())

    def test_atomic_snapshot_publication_preserves_open_reader(self):
        path = self.root / "snapshot.json"
        publish_snapshot(path, {"sequence": 1})
        with open_snapshot(path) as reader:
            # An incomplete generation is never a readiness result.
            pending = path.with_name(path.name + ".snapshots") / "99999999999999999999.json.pending"
            pending.write_text('{"sequence":', encoding="utf-8")
            self.assertEqual(self.read_json(path), {"sequence": 1})
            publish_snapshot(path, {"sequence": 2})
            self.assertEqual(json.load(reader), {"sequence": 1})
            self.assertEqual(self.read_json(path), {"sequence": 2})

    def test_native_saturated_workers_keep_stall_capacity_and_hard_deadlines(self):
        options = ObservationOptions(flush_interval=.1, write_timeout=.1)
        app = Dispatcher(self.root / "application.sqlite3", {"quiet": quiet_pressure_handler},
            isolation_mode="process", worker_count=2, observation_options=options)
        release, entered = threading.Event(), threading.Event()
        counts = {"active": 0, "peak": 0, "calls": 0}
        guard = threading.Lock()

        def blocked_callback(payload):
            with guard:
                counts["active"] += 1
                counts["peak"] = max(counts["peak"], counts["active"])
                counts["calls"] += 1
            self.evidence["records"].append({"callback": payload, "at": time.time()})
            entered.set()
            release.wait(30)
            with guard:
                counts["active"] -= 1

        app.subscribe_stalls(blocked_callback)
        tasks = []
        try:
            for name in ("occupied-a", "occupied-b", "queued-successor"):
                root = self.root / name
                root.mkdir()
                if name == "queued-successor":
                    (root / "release").touch()
                task = app.submit("quiet", {"root": str(root)}, request_id=name, timeout_seconds=8)
                tasks.append(task)
                if name != "queued-successor":
                    task.watch_stall(StallPolicy("pressure", sample_interval=.2, consecutive_windows=3))
            app.start()
            markers = [self.wait_for(lambda name=name: self.read_json(self.root / name / "entered.json"))
                       for name in ("occupied-a", "occupied-b")]
            self.assertEqual(len({item["pid"] for item in markers}), 2)
            self.assertNotIn(os.getpid(), {item["pid"] for item in markers})
            self.assertEqual(tasks[2].snapshot["state"], "queued")
            self.assertFalse((self.root / "queued-successor" / "entered.json").exists())
            self.assertTrue(entered.wait(8), "real stall callback was never delivered")
            first = len(tasks[0].stall_windows(limit=50)["windows"])
            self.wait_for(lambda: len(tasks[0].stall_windows(limit=50)["windows"]),
                          lambda size: size > first, seconds=3)
            for task in tasks[:2]:
                result = task.wait(timeout=15)
                self.assertEqual(result["status"], "timed_out")
                self.evidence["records"].append({"execution_id": task.snapshot["command"]["execution_id"],
                    "result": result, "observation": task.observe(), "stopped_at": time.time()})
            self.assertEqual(tasks[2].wait(timeout=15)["status"], "succeeded")
            self.assertEqual(counts["peak"], 1)
            self.assertEqual(sum(thread.name == "dispatcher-stall-consumer" and thread.is_alive()
                                 for thread in threading.enumerate()), 1)
            self.evidence.update({"configuration": {"workers": 2, "timeout": 8,
                "sample_interval": .2, "windows": 3}, "actual_entry": markers,
                "callback_counts": dict(counts), "health": app.health(),
                "notifications": app.stall_notification_page(limit=50)})
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                app.close(timeout=.3)
            self.assertLess(time.monotonic() - started, .7)
        finally:
            release.set()
            app.close(timeout=15)

    def test_native_progress_between_public_recheck_and_sqlite_cancel_commit(self):
        runtime = Kernel.open_sqlite(self.root / "kernel.sqlite3", {"quiet": quiet_pressure_handler},
            isolation_mode="process", observation_options=ObservationOptions(flush_interval=.1))
        self.addCleanup(runtime.close)
        name = "pressure-cas"
        runtime.submit(runtime.command("quiet", execution_id=name, idempotency_key=name, correlation_id=name,
            payload={"root": str(self.root)}, timeout_seconds=10))
        runtime.watch_stall(name, StallPolicy("commit-race", sample_interval=.2, consecutive_windows=3))
        results, errors = [], []

        def drive():
            try:
                results.append(runtime.run_once())
            except BaseException as error:
                errors.append(repr(error))

        driver = threading.Thread(target=drive)
        driver.start()
        self.addCleanup(lambda: driver.join(15))
        self.addCleanup(lambda: (self.root / "release").touch())
        self.wait_for(lambda: self.read_json(self.root / "entered.json"))
        notice = self.wait_for(lambda: runtime.stall_notifications())[0]["payload"]
        original_cancel = runtime.kernel.cancel
        reached = threading.Event()
        permit = threading.Event()
        cancel_errors = []

        def barrier_cancel(*args, **kwargs):
            reached.set()
            if not permit.wait(5):
                raise RuntimeError("cancel transaction barrier expired")
            return original_cancel(*args, **kwargs)

        runtime.kernel.cancel = barrier_cancel
        self.addCleanup(lambda: setattr(runtime.kernel, "cancel", original_cancel))

        def dispose():
            try:
                runtime.cancel_if_stalled(notice)
            except BaseException as error:
                cancel_errors.append(error)

        disposer = threading.Thread(target=dispose)
        disposer.start()
        try:
            self.assertTrue(reached.wait(3))
            (self.root / "progress").touch()
            confirmation = self.wait_for(lambda: self.read_json(self.root / "confirmed.json"), seconds=3)
            self.assertEqual(confirmation["state"], "confirmed")
            permit.set()
            disposer.join(3)
            self.assertFalse(disposer.is_alive())
            self.assertEqual(len(cancel_errors), 1)
            self.assertIsInstance(cancel_errors[0], CASConflictError)
            self.assertEqual(runtime.kernel.get(name).state, "running")
            self.evidence.update({"execution_id": name, "notification": notice,
                "confirmed_progress": confirmation, "cancel_error": repr(cancel_errors[0]),
                "after_race": runtime.observe(name), "at": time.time()})
        finally:
            permit.set()
            disposer.join(5)
            runtime.kernel.cancel = original_cancel
            (self.root / "release").touch()
            driver.join(15)
        self.assertEqual(errors, [])
        self.assertEqual(runtime.kernel.get(name).state, "succeeded")

    def test_native_ten_thousand_summaries_have_bounded_readonly_pages(self):
        options = ObservationOptions(flush_interval=1, queue_items=256, queue_bytes=262144,
            batch_summaries=128, page_events=50, query_bytes=16384)
        runtime = Kernel.open_sqlite(self.root / "kernel.sqlite3", {"history": history_pressure_handler},
            isolation_mode="process", observation_options=options)
        self.addCleanup(runtime.close)
        name = "pressure-history"
        runtime.submit(runtime.command("history", execution_id=name, idempotency_key=name, correlation_id=name,
            payload={}, timeout_seconds=20))
        result = runtime.run_once()
        self.evidence["actual_result"] = result.result.to_dict() if result.result else result.to_dict()
        self.assertEqual(result.state, "succeeded", result.result)
        self.assertNotEqual(result.result.value["pid"], os.getpid())
        database = runtime.observation_storage["path"]
        with sqlite3.connect(database) as connection:
            before = list(connection.iterdump())
        cursor, total, summaries, pages, maximum = 0, 0, 0, 0, 0
        actual_numbers = set()
        while True:
            started = time.monotonic()
            page = runtime.observation_events(name, after=cursor, limit=1000, timeout=.5)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, .8)
            size = self.encoded(page)
            self.assertLessEqual(size, options.query_bytes)
            self.assertLessEqual(len(page["events"]), options.page_events)
            self.assertFalse(page.get("timed_out", False), page)
            pages += 1
            maximum = max(maximum, size)
            for event in page["events"]:
                total += 1
                if event["kind"] == "phase" and event["payload"].get("phase") == "pressure-summary":
                    summaries += 1
                    actual_numbers.add(event["payload"]["details"]["number"])
            self.evidence["records"].append({"cursor_before": cursor, "cursor": page["cursor"],
                "events": len(page["events"]), "bytes": size, "elapsed": elapsed,
                "has_more": page["has_more"], "complete": page["complete"]})
            if not page["has_more"]:
                break
            self.assertGreater(page["cursor"], cursor)
            cursor = page["cursor"]
            self.assertLess(pages, 1000)
        self.assertEqual(summaries, 10_000)
        self.assertEqual(actual_numbers, set(range(10_000)))
        observed = runtime.observe(name, timeout=.5)
        with sqlite3.connect(database) as connection:
            self.assertEqual(list(connection.iterdump()), before)
        self.evidence.update({"execution_id": name, "actual_result": result.result.to_dict(),
            "configuration": options.__dict__, "persisted_events": total, "summaries": summaries,
            "pages": pages, "maximum_page_bytes": maximum, "observation": observed})

    def test_native_output_queue_overflow_cannot_delay_deadline_or_public_cancel(self):
        for action in ("deadline", "cancel"):
            with self.subTest(action=action):
                root = self.root / action
                root.mkdir()
                options = ObservationOptions(flush_interval=.1, write_timeout=.1, tail_bytes=64,
                    queue_items=16, queue_bytes=4096, batch_summaries=8, query_bytes=16384)
                runtime = Kernel.open_sqlite(root / "kernel.sqlite3", {"stream": streaming_pressure_handler},
                    isolation_mode="process", observation_options=options,
                    cancellation_journal_path=str(root / "cancellation.sqlite3"), source_id="pressure-host")
                name = "pressure-" + action
                runtime.submit(runtime.command("stream", execution_id=name, idempotency_key=name, correlation_id=name,
                    timeout_seconds=8, payload={"root": str(root)}))
                results, errors = [], []

                def drive():
                    try:
                        results.append(runtime.run_once())
                    except BaseException as error:
                        errors.append(repr(error))

                driver = threading.Thread(target=drive)
                driver.start()
                writer = None
                record = {"execution_id": name, "action": action, "configuration": options.__dict__,
                    "work_timeout_seconds": 8, "stop_lateness_limit_seconds": 2,
                    "cancel_elapsed_limit_seconds": 2}
                self.evidence["records"].append(record)
                try:
                    record["actual_entry"] = self.wait_for(lambda: self.read_json(root / "entered.json"))
                    current = runtime.kernel.get(name)
                    recorder = runtime._execution_recorders[(name, current.attempt, current.fence)]
                    original_close = recorder.close
                    record["driver_close_receipts"] = []

                    def capture_close(*args, **kwargs):
                        receipt = original_close(*args, **kwargs)
                        record["driver_close_receipts"].append({"at": time.time(), "receipt": receipt})
                        return receipt

                    recorder.close = capture_close
                    writer = sqlite3.connect(runtime.observation_storage["path"], timeout=1)
                    writer.execute("BEGIN IMMEDIATE")
                    record["writer_locked_at"] = time.time()
                    (root / "start-output").touch()
                    local = self.wait_for(lambda: self.read_json(root / "local.json"),
                        lambda item: item and item["dropped_events"] > 0 and item["error"], seconds=4)
                    self.assertLessEqual(local["queued_items"], options.queue_items)
                    self.assertLessEqual(local["queued_bytes"], options.queue_bytes)
                    self.assertGreater(local["metrics"]["stdout_bytes"]["count"], 0)
                    self.assertFalse(local["complete"])
                    record["local_degradation"] = local
                    record["child_before_stop"] = self.read_json(root / "child.json")
                    if action == "cancel":
                        started = time.monotonic()
                        current = runtime.kernel.get(name)
                        cancelled = runtime.cancel(name, expected_revision=current.revision,
                            timeout_seconds=1, reason="native pressure cancellation")
                        record["cancel_elapsed"] = time.monotonic() - started
                        record["cancel_result"] = cancelled.to_dict()
                        self.assertLess(record["cancel_elapsed"], 2)
                        self.assertEqual(cancelled.state, "cancelled")
                    driver.join(12)
                    self.assertFalse(driver.is_alive(), "observation writer blocked native stopping")
                    self.assertEqual(errors, [])
                    record["run_once_snapshot"] = results[0].to_dict()
                    record["stopped_at"] = time.time()
                    if action == "deadline":
                        cutoff = min(item["deadline_at"] for item in
                            record["actual_entry"]["budget"]["constraints"])
                        record["deadline_stop_lateness"] = record["stopped_at"] - cutoff
                        self.assertLess(record["deadline_stop_lateness"], 2)
                    record["kernel_state"] = runtime.kernel.get(name).state
                    self.assertEqual(record["kernel_state"], "timed_out" if action == "deadline" else "cancelled")
                    record["snapshot_generations"] = {kind: len(tuple(
                        (root / f"{kind}.json.snapshots").glob("*.json"))) for kind in ("local", "child")}
                    record["locked_observation"] = runtime.observe(name, timeout=.5)
                    self.assertTrue(any(not item["receipt"]["final_flush_persisted"]
                        for item in record["driver_close_receipts"]), record["driver_close_receipts"])
                    stopped = self.read_json(root / "child.json")
                    (root / "escape-release").touch()
                    time.sleep(.3)
                    self.assertEqual(self.read_json(root / "child.json"), stopped)
                    self.assertFalse((root / "escaped").exists())
                    record["descendant_stopped"] = stopped
                    writer.rollback()
                    record["writer_unlocked_at"] = time.time()
                    record["recovery"] = runtime.recover_completions(timeout_seconds=.5)
                    record["recovered_observation"] = runtime.observe(name, timeout=.5)
                    storage = runtime.observation_storage
                    record["independent_observation"] = inspect_execution(storage["path"], name,
                        kernel_path=storage["kernel_path"], source_id=storage["source_id"],
                        options=options, timeout=.5)
                    self.assertFalse(record["locked_observation"]["complete"],
                        "lost unpersisted telemetry was reported as a complete observation")
                    self.assertFalse(record["independent_observation"]["complete"])
                    self.assertIn("diagnostics", record["independent_observation"])
                finally:
                    if writer is not None:
                        writer.rollback()
                        writer.close()
                    runtime.close()
                    driver.join(15)


if __name__ == "__main__":
    unittest.main()
