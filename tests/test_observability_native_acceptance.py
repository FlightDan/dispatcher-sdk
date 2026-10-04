"""Portable real-backend witnesses; evidence directories intentionally survive.

These tests run Linux process containment or native Windows Jobs through the
same public Runtime API. A Linux pass does not constitute Windows acceptance.
"""
from __future__ import annotations

import json
import importlib
import multiprocessing
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import dispatcher_sdk
from dispatcher_sdk import Dispatcher
from dispatcher_sdk.execution_kernel import ChildExecutionError, ExecutionNotFoundError, HandlerExecutionError, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.observability import ObservationOptions


def write_json(path, value):
    destination = Path(path)
    temporary = destination.with_name(destination.name + ".writing-" + str(os.getpid()))
    temporary.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, destination)


def mark(root, name, **details):
    write_json(Path(root) / (name + ".json"), {"wall": time.time(), "monotonic": time.monotonic(),
        "pid": os.getpid(), "interpreter": sys.executable, "sdk_import": dispatcher_sdk.__file__, **details})


def wait_file(path, *, activity=None, seconds=12):
    end = time.monotonic() + seconds
    while not Path(path).exists():
        if time.monotonic() >= end:
            raise TimeoutError("native fixture barrier elapsed: " + str(path))
        if activity is not None:
            activity.heartbeat()
        time.sleep(.02)


class NativePhaseHandler:
    __execution_kernel_revision__ = "native-phase-acceptance-v1"

    def __init__(self, root, fail=False):
        self.root, self.fail = str(root), fail

    def __setstate__(self, state):
        self.__dict__.update(state)
        mark(self.root, "deserializing", mode="failure" if self.fail else "delayed")
        if self.fail:
            raise RuntimeError("native deserialization exploded before handler entry")
        wait_file(Path(self.root) / "release-deserialization")
        mark(self.root, "deserialized")

    def __call__(self, payload, context):
        mark(self.root, "entered", identity=context.lease.to_dict(), budget=context.budget.to_dict())
        context.activity.flush()
        wait_file(Path(self.root) / "release-model", activity=context.activity)
        context.activity.model("request")
        context.activity.flush()
        mark(self.root, "model-request")
        wait_file(Path(self.root) / "release-return", activity=context.activity)
        return {"model_request": True}


class NativeImportHandler:
    __execution_kernel_revision__ = "native-import-failure-acceptance-v1"

    def __init__(self, root):
        self.root = str(root)

    def __setstate__(self, state):
        self.__dict__.update(state)
        module = "sdk_acceptance_intentionally_absent_handler_module"
        mark(self.root, "handler-import-started", module=module)
        try:
            importlib.import_module(module)
        except ModuleNotFoundError as error:
            mark(self.root, "handler-import-failed", module=module,
                error_type=type(error).__name__, message=str(error), missing_name=error.name)
            raise

    def __call__(self, payload, context):
        mark(self.root, "unexpected-import-handler-entry")
        context.activity.model("request")
        return {"unexpected": "handler import succeeded"}


def resident_memory(pid):
    """Measure native resident memory; inaccessible data remains unknown."""
    facts = {"pid": pid, "wall": time.time(), "monotonic": time.monotonic(), "known": False}
    try:
        if sys.platform.startswith("linux"):
            root = Path("/proc") / str(pid)
            before = (root / "stat").read_text(encoding="ascii")
            status = (root / "status").read_text(encoding="ascii")
            after = (root / "stat").read_text(encoding="ascii")
            first, last = before.rsplit(")", 1)[1].split(), after.rsplit(")", 1)[1].split()
            if first[19] != last[19] or last[0] == "Z":
                raise RuntimeError("process changed or became a zombie during resident measurement")
            rss = next(line.split()[1] for line in status.splitlines() if line.startswith("VmRSS:"))
            facts.update(known=True, source="linux_proc_status", resident_bytes=int(rss) * 1024,
                birth_ticks=last[19], process_state=last[0], raw_status=status, raw_stat=after)
        elif os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    *[(name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                        "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle.restype = wintypes.BOOL
            kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
            kernel.GetProcessTimes.restype = wintypes.BOOL
            psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x100410, False, pid)  # synchronize, query, VM read
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if kernel.WaitForSingleObject(handle, 0) != 258:
                    raise RuntimeError("native process handle is not currently active")
                created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
                if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                        ctypes.byref(kernel_time), ctypes.byref(user_time)):
                    raise ctypes.WinError(ctypes.get_last_error())
                counters = Counters()
                counters.cb = ctypes.sizeof(counters)
                if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    raise ctypes.WinError(ctypes.get_last_error())
                facts.update(known=True, source="windows_native_process_handle",
                    resident_bytes=counters.WorkingSetSize, peak_resident_bytes=counters.PeakWorkingSetSize,
                    private_commit_bytes=counters.PrivateUsage,
                    birth_ticks=(created.dwHighDateTime << 32) | created.dwLowDateTime,
                    native_wait_result=258)
            finally:
                if not kernel.CloseHandle(handle):
                    raise ctypes.WinError(ctypes.get_last_error())
        else:
            facts["unknown_reason"] = "resident_measurement_platform_unsupported"
    except Exception as error:
        facts.update(known=False, unknown_reason="resident_measurement_unavailable",
            error_type=type(error).__name__, message=str(error))
    return facts


def capacity_event(root, role, phase):
    event = {"role": role, "phase": phase, "pid": os.getpid(), "wall": time.time(),
        "monotonic": time.monotonic(), "interpreter": sys.executable, "sdk_import": dispatcher_sdk.__file__}
    descriptor = os.open(Path(root) / "handler-events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, (json.dumps(event) + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)


def native_capacity_parent(payload, context):
    root = Path(payload["root"])
    capacity_event(root, "parent", "entered")
    before = resident_memory(os.getpid())
    resident = bytearray(payload["buffer_bytes"])
    for offset in range(0, len(resident), 4096):
        resident[offset] = 91
    resident[-1] = 91
    allocated = resident_memory(os.getpid())
    mark(root, "capacity-parent-entered", identity=context.lease.to_dict(), before=before,
        allocated=allocated, buffer_bytes=len(resident), touched_pages=(len(resident) + 4095) // 4096,
        budget=context.budget.to_dict())
    try:
        try:
            result = context.children.run("child", payload, request_id="one-capacity-child", timeout_seconds=12)
            returned = {"child": result}
        except ChildExecutionError as error:
            returned = {"child_error": error.result, "code": error.code, "message": str(error)}
        mark(root, "capacity-parent-returned", retained_buffer_bytes=len(resident),
            retained_first_byte=resident[0], retained_last_byte=resident[-1], memory=resident_memory(os.getpid()))
        return returned
    finally:
        capacity_event(root, "parent", "returned")


def native_capacity_child(payload, context):
    root = Path(payload["root"])
    capacity_event(root, "child", "entered")
    mark(root, "capacity-child-entered", identity=context.lease.to_dict(), memory=resident_memory(os.getpid()))
    try:
        wait_file(root / "release-capacity-child", activity=context.activity, seconds=10)
        if payload["fail"]:
            mark(root, "capacity-child-error", error_type="HandlerExecutionError", code="native_child_denied",
                message="original native child refusal", input=payload["input"])
            raise HandlerExecutionError("native_child_denied", "original native child refusal",
                details={"input": payload["input"]})
        return {"input": payload["input"]}
    finally:
        capacity_event(root, "child", "returned")


def native_capacity_successor(payload, context):
    capacity_event(payload["root"], "successor", "entered")
    try:
        mark(payload["root"], "capacity-successor-entered", identity=context.lease.to_dict())
        return {"continued": True}
    finally:
        capacity_event(payload["root"], "successor", "returned")


def segmented_output(payload, context):
    root = Path(payload["root"])
    context.activity.enable_stream("stdout")
    script = """import os,pathlib,sys,time
root=pathlib.Path(sys.argv[1]);os.write(1,b'A')
while not (root/'release-chunk').exists(): time.sleep(.02)
os.write(1,b'BC')
while not (root/'release-finish').exists(): time.sleep(.02)
os.write(1,b'DEF')
"""
    process = subprocess.Popen([sys.executable, "-c", script, str(root)], stdout=subprocess.PIPE)
    context.activity.observe_process(process, role="native-stream-tool")
    assert process.stdout is not None
    with (root / "raw.stdout").open("xb", buffering=0) as raw:
        chunk = process.stdout.read(1)
        raw.write(chunk)
        context.activity.report_bytes("stdout", chunk)
        context.activity.flush()
        mark(root, "first-segment", child_pid=process.pid)
        wait_file(root / "release-activity", activity=context.activity)
        context.activity.tool("response")
        new = context.activity.progress("one-real-milestone", details={"step": 1})
        context.activity.flush()
        mark(root, "independent-activity", progress=new)
        wait_file(root / "release-replay", activity=context.activity)
        replay = context.activity.progress("one-real-milestone", details={"step": 1})
        context.activity.flush()
        mark(root, "replayed-progress", progress=replay)
        chunk = process.stdout.read(2)
        raw.write(chunk)
        context.activity.report_bytes("stdout", chunk)
        context.activity.flush()
        mark(root, "second-segment")
        chunk = process.stdout.read(3)
        raw.write(chunk)
        context.activity.report_bytes("stdout", chunk)
    process.stdout.close()
    process.wait(timeout=3)
    return {"bytes": 6, "new": new, "replay": replay}


def blocked_native_tool(payload, context):
    root = Path(payload["root"])
    mark(root, "entered", identity=context.lease.to_dict(), budget=context.budget.to_dict())
    tool = context.derive_budget(source="tool", origin_id="native-tool", timeout_seconds=2,
        reserve_seconds=.3) if payload["derive"] else context.budget_envelope
    view = tool.view()
    mark(root, "tool-budget", envelope=tool.to_dict(), budget=view.to_dict())
    script = """import json,pathlib,sys,time,os
root=pathlib.Path(sys.argv[1]);envelope=json.loads(sys.argv[2])
(root/'tool-received.json').write_text(json.dumps({'envelope':envelope,'wall':time.time(),'monotonic':time.monotonic(),'pid':os.getpid()}))
time.sleep(10);(root/'escaped').write_text('deadline escaped')
"""
    process = subprocess.Popen([sys.executable, "-c", script, str(root), json.dumps(tool.to_dict())])
    context.activity.observe_process(process, role="blocked-native-tool")
    context.activity.tool("request")
    if not payload["derive"]:
        process.wait()
        return {"unexpected": "blocked tool returned"}
    with context.activity.wait("tool_response", target="native-tool", deadline_at=view.effective_work_deadline_at):
        try:
            process.wait(timeout=tool.view().remaining_work_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
            mark(root, "tool-stopped", budget=tool.view().to_dict())
            raise HandlerExecutionError("execution_deadline_exhausted", "native tool reached shortest work cutoff",
                details=view.to_dict())
    return {"unexpected": "tool cutoff did not apply"}


def native_crash_gate(payload, context):
    root = Path(payload["root"])
    with (root / "business-calls").open("a", encoding="ascii") as calls:
        calls.write(str(context.lease.attempt) + "\n")
    mark(root, "entered", identity=context.lease.to_dict(), envelope=context.budget_envelope.to_dict())
    time.sleep(10)
    (root / "escaped").write_text("unexpected retry business")
    return {}


def native_wait_gate(payload, context):
    root = Path(payload["root"])
    mark(root, "entered", identity=context.lease.to_dict())
    wait_file(root / "release-return", activity=context.activity)
    return {"completed": True}


def native_registration_parent(payload, context):
    root = Path(payload["root"])
    mark(root, "registration-entered", identity=context.lease.to_dict(), envelope=context.budget_envelope.to_dict())
    wait_file(root / "release-child", activity=context.activity)
    mark(root, "registration-child-call")
    try:
        return context.children.run("child", {"root": str(root)}, request_id="cross-store", timeout_seconds=20)
    except BaseException as exc:
        mark(root, "registration-child-error", error_type=type(exc).__name__, error=str(exc),
            code=getattr(exc, "code", None))
        raise


def native_registration_child(payload, context):
    mark(payload["root"], "child-business", identity=context.lease.to_dict())
    return {"unexpected": "interrupted registration executed child business"}


def native_shared_oom_clue(payload, context):
    root = Path(payload["root"])
    code = """import pathlib,sys,time
root=pathlib.Path(sys.argv[1]);(root/'exit137-ready').touch()
while not (root/'release-exit137').exists(): time.sleep(.005)
sys.exit(137)
"""
    process = subprocess.Popen([sys.executable, "-c", code, str(root)])
    context.activity.observe_process(process, process_id="exit137", role="tool")
    wait_file(root / "exit137-ready")
    clue = {"scope": "shared_cgroup", "known": False, "observed_at": time.time()}
    try:
        membership = Path(f"/proc/{process.pid}/cgroup").read_text(encoding="utf-8")
        group = next(line.split(":", 2)[2] for line in membership.splitlines() if line.startswith("0::"))
        events_path = Path("/sys/fs/cgroup") / group.lstrip("/") / "memory.events"
        clue.update(membership=membership, path=str(events_path), raw_events=events_path.read_text(encoding="utf-8"), known=True)
    except (OSError, StopIteration) as error:
        clue.update(unknown_reason="cgroup_visibility_unknown", error_type=type(error).__name__, message=str(error))
    context.activity.phase("shared_cgroup_oom_clue", details=clue)
    mark(root, "oom-clue", **clue)
    (root / "release-exit137").touch()
    returncode = process.wait(timeout=2)
    context.activity.observe_process(process, process_id="exit137", role="tool")
    return {"returncode": returncode, "clue": clue}


for handler in (segmented_output, blocked_native_tool, native_crash_gate, native_wait_gate,
                native_registration_parent, native_registration_child, native_shared_oom_clue,
                native_capacity_parent, native_capacity_child, native_capacity_successor):
    handler.__execution_kernel_revision__ = "native-observability-acceptance-v1"


class NativeWallClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def crash_controller(database, root):
    runtime = Kernel.open_sqlite(database, {"work": native_crash_gate}, isolation_mode="process")
    driver = threading.Thread(target=runtime.run_once)
    driver.start()
    wait_file(Path(root) / "entered.json")
    mark(root, "controller-crashing")
    os._exit(73)


def registration_crash_controller(database, root):
    runtime = Kernel.open_sqlite(database, {"work": native_registration_parent, "child": native_registration_child},
        isolation_mode="process", child_capacity=1, observation_options=ObservationOptions(flush_interval=.1))
    driver = threading.Thread(target=runtime.run_once)
    driver.start()
    wait_file(Path(root) / "registration-entered.json")
    # Suspend admission at the actual Runtime lock. The process worker can
    # reserve the independent journal, but ChildService cannot submit to the
    # Kernel until admission resumes. Neither authority nor budgets change.
    with runtime._lifecycle_lock:
        mark(root, "registration-admission-suspended")
        end = time.monotonic() + 8
        while time.monotonic() < end:
            report = runtime.observe("native-registration", timeout=1)
            pending = [row for row in report.get("child_requests", []) if row["state"] == "pending"]
            if pending:
                write_json(Path(root) / "partial-registration.json", report)
                mark(root, "registration-crashing", request=pending[0])
                os._exit(73)
            time.sleep(.02)
    os._exit(74)


@unittest.skipUnless(sys.platform.startswith("linux") or os.name == "nt", "requires Linux containment or native Windows Jobs")
class NativeObservabilityAcceptanceTests(unittest.TestCase):
    def setUp(self):
        evidence_directory = os.environ.get("SDK_ACCEPTANCE_EVIDENCE_DIR")
        if evidence_directory:
            Path(evidence_directory).mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="sdk-observability-native-", dir=evidence_directory))
        self.options = ObservationOptions(flush_interval=.1)
        mark(self.root, "configuration", test=self.id(), platform=platform.platform(), machine=platform.machine(),
            isolation="process", original_observation_options={"flush_interval": .1})
        print(json.dumps({"native_artifact": str(self.root), "test": self.id(), "platform": sys.platform,
            "machine": platform.machine(), "interpreter": sys.executable, "sdk_import": dispatcher_sdk.__file__}), flush=True)

    def open(self, handler, *, clock=None):
        runtime = Kernel.open_sqlite(self.root / "kernel.sqlite3", {"work": handler},
            isolation_mode="process", now=clock, observation_options=self.options)
        self.addCleanup(runtime.close)
        return runtime

    @unittest.skipUnless(sys.platform.startswith("linux"), "shared cgroup clues are a Linux-specific scenario")
    def test_native_exit137_and_shared_oom_clue_do_not_invent_causal_oom(self):
        runtime = self.open(native_shared_oom_clue)
        self.submit(runtime, timeout=8)
        result = runtime.run_once()
        write_json(self.root / "result.json", result.to_dict())
        self.assertEqual(result.state, "succeeded", result.to_dict())
        self.assertEqual(result.result.value["returncode"], 137)
        clue = result.result.value["clue"]
        if clue["known"]:
            self.assertIn("oom_kill", clue["raw_events"])
        else:
            self.assertEqual(clue["unknown_reason"], "cgroup_visibility_unknown")
        observed = runtime.observe("native-execution")
        write_json(self.root / "raw-observation.json", observed)
        process = next(item for item in observed["processes"] if item["process_id"] == "exit137")
        self.assertEqual(process["state"], "exited")
        self.assertEqual(process["evidence"]["returncode"], 137)
        self.assertEqual(process["evidence"]["exit_kind"], "status")
        self.assertIsNone(process["evidence"]["signal"])
        self.assertEqual(process["evidence"]["oom"], "unknown")

    def submit(self, runtime, *, timeout=8, payload=None, managed=False, retry=None):
        execution_id = "sdk-managed:native:work" if managed else "native-execution"
        command = runtime.command("work", execution_id=execution_id, idempotency_key=execution_id,
            correlation_id="native", timeout_seconds=timeout, payload={"root": str(self.root)} if payload is None else payload,
            retry_policy=retry)
        if managed:
            runtime.submit_managed(command, run_id="native", generation=0)
        else:
            runtime.submit(command)
        write_json(self.root / "command.json", command.to_dict())
        return command

    def drive(self, runtime):
        results, errors = [], []
        def run():
            try:
                results.append(runtime.run_once())
            except BaseException as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        driver = threading.Thread(target=run)
        self.addCleanup(lambda: driver.join(15))
        for name in ("release-deserialization", "release-model", "release-return", "release-activity", "release-replay", "release-chunk", "release-finish"):
            self.addCleanup((self.root / name).touch)
        driver.start()
        return driver, results, errors

    def await_marker(self, name, seconds=10):
        wait_file(self.root / (name + ".json"), seconds=seconds)
        return json.loads((self.root / (name + ".json")).read_text())

    def snapshot(self, runtime, command, name, predicate=lambda report: True):
        end = time.monotonic() + 3
        while True:
            report = runtime.observe(command.execution_id, timeout=1)
            if predicate(report) or time.monotonic() >= end:
                write_json(self.root / (name + ".json"), report)
                self.assertTrue(predicate(report), report)
                return report
            time.sleep(.02)

    @staticmethod
    def count(report, metric):
        return report.get("metrics", {}).get(metric, {}).get("count", 0)

    @staticmethod
    def phases(report):
        return {item["phase"] for item in report.get("phases", [])}

    def finish(self, driver, results, errors, seconds=15):
        driver.join(seconds)
        self.assertFalse(driver.is_alive(), "native execution exceeded its fixed acceptance window")
        self.assertEqual([], errors)
        self.assertEqual(1, len(results))
        write_json(self.root / "result.json", results[0].to_dict())
        return results[0]

    def test_native_queued_deserialization_entry_and_model_request_are_distinct(self):
        runtime = self.open(NativePhaseHandler(self.root))
        command = self.submit(runtime)
        queued = self.snapshot(runtime, command, "queued")
        self.assertEqual("queued", queued["execution"]["state"])
        driver, results, errors = self.drive(runtime)
        self.await_marker("deserializing")
        boot = self.snapshot(runtime, command, "during-deserialization")
        self.assertNotIn("handler_entered", self.phases(boot))
        self.assertEqual(0, self.count(boot, "model_requests"))
        self.assertFalse((self.root / "entered.json").exists())
        (self.root / "release-deserialization").touch()
        self.await_marker("entered")
        entered = self.snapshot(runtime, command, "before-model", lambda report: "handler_entered" in self.phases(report))
        self.assertIn("worker_ready", self.phases(entered))
        self.assertEqual(0, self.count(entered, "model_requests"))
        self.assertEqual("confirmed", entered["budget"]["entry_state"])
        (self.root / "release-model").touch()
        self.await_marker("model-request")
        requested = self.snapshot(runtime, command, "after-model", lambda report: self.count(report, "model_requests") == 1)
        self.assertEqual(entered["identity"], requested["identity"])
        (self.root / "release-return").touch()
        self.assertEqual("succeeded", self.finish(driver, results, errors).state)

    def test_native_deserialization_failure_retains_raw_error_without_false_entry(self):
        runtime = self.open(NativePhaseHandler(self.root, fail=True))
        command = self.submit(runtime)
        driver, results, errors = self.drive(runtime)
        self.await_marker("deserializing")
        result = self.finish(driver, results, errors)
        self.assertEqual("failed", result.state)
        self.assertIn("native deserialization exploded before handler entry", json.dumps(result.to_dict()))
        observed = self.snapshot(runtime, command, "failed-bootstrap")
        self.assertNotIn("handler_entered", self.phases(observed))
        self.assertEqual(0, self.count(observed, "model_requests"))
        self.assertFalse((self.root / "entered.json").exists())

    def test_native_handler_import_failure_retains_raw_error_without_false_ready_or_entry(self):
        from tests._storage_evidence import StorageEvidence
        evidence = StorageEvidence(self.root, self)
        evidence.start(include_kernel=True)
        self.addCleanup(evidence.stop)
        self.addCleanup(evidence.save)
        runtime = self.open(NativeImportHandler(self.root))
        command = self.submit(runtime)
        driver, results, errors = self.drive(runtime)
        failure = self.await_marker("handler-import-failed")
        result = self.finish(driver, results, errors)
        observed = self.snapshot(runtime, command, "failed-handler-import")
        evidence.save(phase="handler-import", checkpoint={"failure": failure,
            "result": result.to_dict(), "observation": observed, "original_execution_timeout": 8})
        self.assertEqual("ModuleNotFoundError", failure["error_type"])
        self.assertEqual("sdk_acceptance_intentionally_absent_handler_module", failure["missing_name"])
        self.assertEqual("failed", result.state)
        self.assertIn(failure["message"], json.dumps(result.to_dict()))
        self.assertEqual("ModuleNotFoundError", result.result.error.details["exception_type"])
        self.assertEqual("worker_deserialization", result.result.error.details["stage"])
        self.assertNotIn("worker_ready", self.phases(observed))
        self.assertNotIn("handler_entered", self.phases(observed))
        self.assertEqual(0, self.count(observed, "model_requests"))
        self.assertFalse((self.root / "unexpected-import-handler-entry.json").exists())

    def test_native_parent_resident_memory_and_child_results_keep_configured_capacity(self):
        from tests._storage_evidence import StorageEvidence
        evidence = StorageEvidence(self.root, self)
        evidence.start(include_kernel=True)
        self.addCleanup(evidence.stop)
        self.addCleanup(evidence.save)
        for fail in (False, True):
            with self.subTest(child_failure=fail):
                root = self.root / ("failure" if fail else "success")
                root.mkdir()
                payload = {"root": str(root), "fail": fail, "buffer_bytes": 16 * 1024 * 1024,
                    "input": "original-native-capacity-input"}
                mark(root, "configuration", business_workers=1, child_capacity=1, total_handler_capacity=2,
                    parent_timeout=20, child_timeout=12, caller_timeout=25, child_barrier_timeout=10,
                    entry_barrier_timeout=12, payload=payload)
                app = Dispatcher(root / "application.sqlite3", {"parent": native_capacity_parent,
                    "child": native_capacity_child, "successor": native_capacity_successor},
                    isolation_mode="process", worker_count=1, child_capacity=1, max_child_depth=1,
                    observation_options=self.options)
                parent = app.submit("parent", payload, request_id="capacity-parent", timeout_seconds=20)
                successor = app.submit("successor", {"root": str(root)}, request_id="capacity-successor",
                    timeout_seconds=20)
                try:
                    app.start()
                    wait_file(root / "capacity-parent-entered.json", seconds=12)
                    wait_file(root / "capacity-child-entered.json", seconds=12)
                    entered = json.loads((root / "capacity-parent-entered.json").read_text())
                    child_entered = json.loads((root / "capacity-child-entered.json").read_text())
                    deadline = time.monotonic() + 3
                    while True:
                        waiting = parent.observe(timeout=.5)
                        if any(wait["state"] == "open" for wait in waiting.get("child_waits", [])):
                            break
                        if time.monotonic() >= deadline:
                            self.fail(waiting)
                        time.sleep(.02)
                    memory = {"parent": resident_memory(entered["pid"]),
                        "child": resident_memory(child_entered["pid"])}
                    write_json(root / "during-child-wait.json", {"memory": memory, "observation": waiting,
                        "successor_state": successor.snapshot["state"], "observed_handler_processes": 2})
                    self.assertNotEqual(entered["pid"], child_entered["pid"])
                    self.assertNotIn(os.getpid(), {entered["pid"], child_entered["pid"]})
                    for measured in (entered["before"], entered["allocated"], *memory.values()):
                        self.assertTrue(measured["known"], measured)
                        self.assertGreaterEqual(measured["resident_bytes"], 0)
                    self.assertEqual("queued", successor.snapshot["state"])
                    self.assertFalse((root / "capacity-successor-entered.json").exists())
                    requests = waiting["child_requests"]
                    self.assertEqual(1, len(requests))
                    self.assertEqual(child_entered["identity"]["execution_id"], requests[0]["child_execution_id"])
                    (root / "release-capacity-child").touch()
                    result = parent.wait(timeout=25)
                    continued = successor.wait(timeout=25)
                    returned = json.loads((root / "capacity-parent-returned.json").read_text())
                    raw_events = (root / "handler-events.jsonl").read_text().splitlines()
                    events = sorted((json.loads(line) for line in raw_events), key=lambda event: event["monotonic"])
                    active, peak = set(), 0
                    for event in events:
                        if event["phase"] == "entered":
                            self.assertNotIn(event["pid"], active, events)
                            active.add(event["pid"])
                            peak = max(peak, len(active))
                        else:
                            self.assertIn(event["pid"], active, events)
                            active.remove(event["pid"])
                    write_json(root / "capacity-result.json", {"result": result, "successor": continued,
                        "parent_returned": returned, "raw_events": raw_events, "events": events,
                        "actual_handler_peak": peak, "configured_handler_limit": 2})
                    self.assertEqual("succeeded", result["status"])
                    self.assertEqual("succeeded", continued["status"])
                    self.assertTrue(continued["value"]["continued"])
                    self.assertEqual(2, peak)
                    self.assertEqual(set(), active)
                    self.assertEqual(payload["buffer_bytes"], returned["retained_buffer_bytes"])
                    self.assertEqual(91, returned["retained_first_byte"])
                    self.assertEqual(91, returned["retained_last_byte"])
                    self.assertTrue(returned["memory"]["known"], returned["memory"])
                    if fail:
                        raw_error = json.loads((root / "capacity-child-error.json").read_text())
                        child_error = result["value"]["child_error"]["error"]
                        self.assertEqual(raw_error["code"], child_error["code"])
                        self.assertEqual(raw_error["message"], child_error["message"])
                        self.assertEqual(payload["input"], child_error["details"]["input"])
                    else:
                        self.assertEqual(payload["input"], result["value"]["child"]["value"]["input"])
                    evidence.save(phase="capacity-failure" if fail else "capacity-success",
                        checkpoint={"waiting": waiting, "native_memory": memory, "events": events,
                            "actual_handler_peak": peak, "result": result, "successor": continued})
                finally:
                    (root / "release-capacity-child").touch()
                    app.close()

    def test_native_segmented_bytes_heartbeat_tool_response_and_progress_replay(self):
        runtime = self.open(segmented_output)
        command = self.submit(runtime, timeout=12)
        driver, results, errors = self.drive(runtime)
        self.await_marker("first-segment")
        first = self.snapshot(runtime, command, "first-raw-snapshot", lambda report: self.count(report, "stdout_bytes") == 1)
        self.assertEqual(0, self.count(first, "tool_responses"))
        self.assertEqual(0, self.count(first, "progress"))
        time.sleep(.15)
        (self.root / "release-activity").touch()
        new = self.await_marker("independent-activity")["progress"]
        activity = self.snapshot(runtime, command, "activity-raw-snapshot", lambda report: self.count(report, "tool_responses") == 1 and self.count(report, "progress") == 1)
        self.assertEqual(1, self.count(activity, "stdout_bytes"))
        self.assertGreater(self.count(activity, "heartbeat"), self.count(first, "heartbeat"))
        self.assertTrue(new["advanced"])
        (self.root / "release-replay").touch()
        replay = self.await_marker("replayed-progress")["progress"]
        repeated = self.snapshot(runtime, command, "replay-raw-snapshot")
        self.assertFalse(replay["advanced"])
        self.assertEqual(new["revision"], replay["revision"])
        self.assertEqual(1, self.count(repeated, "progress"))
        (self.root / "release-chunk").touch()
        self.await_marker("second-segment")
        second = self.snapshot(runtime, command, "second-raw-snapshot", lambda report: self.count(report, "stdout_bytes") == 3)
        self.assertEqual(1, self.count(second, "progress"))
        (self.root / "release-finish").touch()
        result = self.finish(driver, results, errors)
        self.assertEqual("succeeded", result.state)
        self.assertEqual(b"ABCDEF", (self.root / "raw.stdout").read_bytes())
        final = self.snapshot(runtime, command, "final-raw-snapshot", lambda report: self.count(report, "stdout_bytes") == 6)
        self.assertEqual(1, self.count(final, "tool_responses"))

    def test_native_run_cutoff_and_derived_blocked_tool_use_shortest_budget(self):
        for derive in (False, True):
            with self.subTest(derived_tool=derive):
                root = self.root / ("tool" if derive else "run")
                root.mkdir()
                with Kernel.open_sqlite(root / "kernel.sqlite3", {"work": blocked_native_tool},
                        isolation_mode="process", observation_options=self.options) as runtime:
                    cutoff = time.time() + (12 if derive else 6)
                    runtime.kernel.register_run_control("native", max_claims=1, deadline_at=cutoff)
                    runtime.kernel.set_run_control("native", expected_epoch=0, state="active", generation=0)
                    command = runtime.command("work", execution_id="sdk-managed:native:work", idempotency_key="native",
                        correlation_id="native", timeout_seconds=30, payload={"root": str(root), "derive": derive})
                    runtime.submit_managed(command, run_id="native", generation=0)
                    began = time.monotonic()
                    result = runtime.run_once()
                    mark(root, "host-result", state=result.state)
                    write_json(root / "result.json", result.to_dict())
                    observed = runtime.observe(command.execution_id)
                    write_json(root / "raw-observation.json", observed)
                    self.assertEqual("timed_out", result.state, result.to_dict())
                    self.assertLess(time.monotonic() - began, 9)
                    self.assertTrue((root / "entered.json").exists(), "native worker never entered before its fixed Run cutoff")
                    received = json.loads((root / "tool-received.json").read_text())
                    sent = json.loads((root / "tool-budget.json").read_text())
                    self.assertEqual(sent["envelope"], received["envelope"])
                    self.assertFalse((root / "escaped").exists())
                    worker = next(item for item in observed["processes"] if item["process_id"] == "worker")
                    self.assertEqual("exited", worker["state"])
                    self.assertEqual("confirmed", worker["evidence"]["cleanup"])
                    cleanup = next(item for item in observed["phases"] if item["phase"] == "process_cleanup")
                    self.assertEqual("confirmed", cleanup["details"]["details"]["state"])
                    host = json.loads((root / "host-result.json").read_text())
                    self.assertGreater(host["monotonic"], received["monotonic"])
                    self.assertLess(host["monotonic"] - received["monotonic"], 7)
                    budget = sent["budget"]
                    self.assertEqual("tool" if derive else "run", budget["limiting_source"])
                    if derive:
                        self.assertEqual("tool", result.result.error.details["limiting_source"])
                        self.assertEqual("native tool reached shortest work cutoff", result.result.error.message)
                        constraint = next(item for item in sent["envelope"]["constraints"] if item["source"] == "tool")
                        self.assertEqual(.3, constraint["reserve_seconds"])
                        self.assertAlmostEqual(constraint["deadline_at"] - .3, budget["effective_work_deadline_at"])
                        stopped = json.loads((root / "tool-stopped.json").read_text())
                        self.assertGreater(stopped["monotonic"], received["monotonic"])
                        self.assertLess(stopped["monotonic"] - received["monotonic"], 3)
                    else:
                        self.assertAlmostEqual(cutoff, budget["effective_work_deadline_at"])

    def test_native_confirmed_entry_controller_crash_restart_spends_original_budget(self):
        runtime = self.open(native_crash_gate)
        command = self.submit(runtime, timeout=.8, retry=RetryPolicy(max_attempts=2,
            initial_backoff_seconds=0, max_backoff_seconds=0, retry_timeouts=True))
        runtime.close()
        controller = multiprocessing.get_context("spawn").Process(target=crash_controller,
            args=(str(self.root / "kernel.sqlite3"), str(self.root)))
        controller.start()
        try:
            controller.join(15)
            self.assertFalse(controller.is_alive())
            self.assertEqual(73, controller.exitcode)
        finally:
            if controller.is_alive():
                controller.kill()
                controller.join(3)
            controller.close()
        entered = self.await_marker("entered")
        original = BudgetEnvelope.from_dict(entered["envelope"])
        time.sleep(1.1)
        clock = NativeWallClock(entered["identity"]["expires_at"] + 1)
        with Kernel.open_sqlite(self.root / "kernel.sqlite3", {"work": native_crash_gate},
                isolation_mode="process", now=clock, observation_options=self.options) as restarted:
            limits = restarted.kernel.get_execution_limits(command.execution_id)
            self.assertEqual("confirmed", limits["entry_state"])
            self.assertEqual(original.to_dict()["constraints"], limits["envelope"]["constraints"])
            restarted.kernel.reap()
            clock.value = entered["wall"] - 10
            now = sample_clock(wall_time=clock.value)
            self.assertEqual(original.checkpoint.domain_id, now.domain_id)
            spent = original.view(sample=now)
            self.assertEqual("trusted", spent.clock_status)
            self.assertEqual(0, spent.remaining_work_seconds)
            result = restarted.run_once()
            write_json(self.root / "restarted-result.json", result.to_dict())
            write_json(self.root / "restarted-observation.json", restarted.observe(command.execution_id))
            self.assertIn(result.state, {"timed_out", "dead"})
            self.assertEqual(["1"], (self.root / "business-calls").read_text().splitlines())
            self.assertFalse((self.root / "escaped").exists())
            after = restarted.kernel.get_execution_limits(command.execution_id)
            self.assertEqual(original.to_dict()["constraints"], after["envelope"]["constraints"])

    def test_native_short_task_wait_does_not_cancel_active_handler(self):
        with Dispatcher(self.root / "dispatcher.sqlite3", {"work": native_wait_gate},
                isolation_mode="process", observation_options=self.options) as app:
            task = app.submit("work", {"root": str(self.root)}, request_id="native-short-wait", timeout_seconds=8)
            self.addCleanup((self.root / "release-return").touch)
            self.await_marker("entered")
            before = task.observe()
            write_json(self.root / "before-short-wait.json", before)
            with self.assertRaises(TimeoutError):
                task.wait(timeout=.05)
            during = task.observe()
            write_json(self.root / "after-short-wait.json", during)
            self.assertEqual("running", during["execution"]["state"])
            self.assertEqual(before["identity"], during["identity"])
            (self.root / "release-return").touch()
            result = task.wait(timeout=10)
            write_json(self.root / "task-result.json", result)
            self.assertEqual("succeeded", result["status"])
            self.assertEqual({"completed": True}, result["value"])

    def test_native_cross_store_registration_crash_recovers_unused_capacity(self):
        handlers = {"work": native_registration_parent, "child": native_registration_child}
        runtime = Kernel.open_sqlite(self.root / "kernel.sqlite3", handlers,
            isolation_mode="process", child_capacity=1, observation_options=self.options)
        self.addCleanup(runtime.close)
        command = runtime.command("work", execution_id="native-registration", idempotency_key="native-registration",
            correlation_id="native-registration", timeout_seconds=5, payload={"root": str(self.root)})
        runtime.submit(command)
        write_json(self.root / "command.json", command.to_dict())
        controller = multiprocessing.get_context("spawn").Process(target=registration_crash_controller,
            args=(runtime.kernel.db_path, str(self.root)))
        controller.start()
        self.addCleanup((self.root / "release-child").touch)
        try:
            entered = self.await_marker("registration-entered")
            self.await_marker("registration-admission-suspended")
            (self.root / "release-child").touch()
            pending = self.await_marker("registration-crashing")["request"]
            self.assertEqual("pending", pending["state"])
            partial = json.loads((self.root / "partial-registration.json").read_text())
            self.assertEqual("open", partial["child_waits"][0]["state"])
            original = BudgetEnvelope.from_dict(entered["envelope"])
            self.assertAlmostEqual(original.view().effective_work_deadline_at,
                partial["child_waits"][0]["deadline_at"])
            # Observation reservation is not Kernel execution authority.
            with self.assertRaises(ExecutionNotFoundError):
                runtime.kernel.get(pending["child_execution_id"])
            controller.join(5)
            self.assertFalse(controller.is_alive())
            self.assertEqual(73, controller.exitcode)
            end = entered["monotonic"] + command.timeout_seconds + .4
            time.sleep(max(0, end - time.monotonic()))
        finally:
            if controller.is_alive():
                controller.kill()
                controller.join(3)
            controller.close()
        self.assertFalse((self.root / "child-business.json").exists())
        runtime.close()
        clock = NativeWallClock(entered["identity"]["expires_at"] + 1)
        with Kernel.open_sqlite(self.root / "kernel.sqlite3", handlers,
                isolation_mode="process", child_capacity=1, now=clock, observation_options=self.options) as recovered:
            recovered.kernel.reap()
            self.assertIsNone(recovered.run_once(), "recovery unexpectedly admitted business")
            end = time.monotonic() + 3
            while True:
                report = recovered.observe(command.execution_id, timeout=1)
                requests = report.get("child_requests", [])
                waits = report.get("child_waits", [])
                if requests and all(row["state"] not in {"pending", "running"} for row in requests) and all(row["state"] != "open" for row in waits):
                    break
                if time.monotonic() >= end:
                    self.fail(report)
                time.sleep(.02)
            write_json(self.root / "recovered-registration.json", report)
            self.assertEqual(1, len(requests))
            self.assertEqual(pending["child_execution_id"], requests[0]["child_execution_id"])
            self.assertEqual("failed", requests[0]["state"])
            self.assertEqual("parent_authority_revoked", json.loads(requests[0]["error_json"])["code"])
            self.assertEqual(1, len(waits))
            self.assertEqual("failed", waits[0]["state"])
            self.assertEqual(partial["child_waits"][0]["deadline_at"], waits[0]["deadline_at"])
            limits = recovered.kernel.get_execution_limits(command.execution_id)
            self.assertEqual(original.to_dict()["constraints"], limits["envelope"]["constraints"])
            self.assertFalse((self.root / "child-business.json").exists())
            with self.assertRaises(ExecutionNotFoundError):
                recovered.kernel.get(pending["child_execution_id"])


if __name__ == "__main__":
    unittest.main()
