from __future__ import annotations

from contextlib import contextmanager
import json
import multiprocessing
from multiprocessing.connection import Connection
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel import (
    ExecutionCommandV2,
    ExecutionError,
    ExecutionResultV2,
    HandlerExecutionError,
    Kernel,
    RegistryRevisionMismatchError,
    RetryPolicy,
)


def echo_handler(payload, context):
    return {"echo": payload["value"], "version": context.command.handler_contract_version}


def version_one(payload, context):
    return {"version": 1}


def version_two(payload, context):
    return {"version": 2}


def retry_by_attempt(payload, context):
    if context.lease.attempt == 1:
        raise HandlerExecutionError(
            "temporary",
            "retry this attempt",
            retryable=True,
            details={"attempt": context.lease.attempt},
        )
    return {"attempt": context.lease.attempt}


retry_by_attempt.__execution_kernel_revision__ = "runtime-test-handlers-v2"


def generic_failure(payload, context):
    raise RuntimeError("not explicitly retryable")


def effect_handler(payload, context):
    response = context.effects.execute_once(
        "effect-runtime",
        "notify",
        {"value": payload["value"]},
        lambda: {"receipt": "sent"},
    )
    return {"effect": response}


def late_file_write(payload, context):
    time.sleep(payload["sleep"])
    Path(payload["path"]).write_text("late", encoding="utf-8")
    return {"late": True}


late_file_write.__execution_kernel_revision__ = "runtime-test-handlers-v2"


_SPAWNED_TEST_CHILDREN = []


def catch_base_exception_then_write(payload, context):
    try:
        time.sleep(payload["sleep"])
    except BaseException:
        pass
    Path(payload["path"]).write_text("late", encoding="utf-8")
    return {"late": True}


catch_base_exception_then_write.__execution_kernel_revision__ = (
    "runtime-timeout-catch-test-v1"
)


def spawn_late_child(payload, context):
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,sys,time; time.sleep(float(sys.argv[2])); "
                "pathlib.Path(sys.argv[1]).write_text('late', encoding='utf-8')"
            ),
            payload["path"],
            str(payload["child_sleep"]),
        ],
        start_new_session=payload["new_session"],
    )
    _SPAWNED_TEST_CHILDREN.append(child)
    time.sleep(payload["handler_sleep"])
    return {"unexpected": True, "child_pid": child.pid}


spawn_late_child.__execution_kernel_revision__ = "runtime-timeout-child-test-v1"


def double_fork_late_write(payload, context):
    first = os.fork()
    if first == 0:
        second = os.fork()
        if second != 0:
            os._exit(0)
        os.setsid()
        time.sleep(payload["child_sleep"])
        Path(payload["path"]).write_text("late", encoding="utf-8")
        os._exit(0)
    time.sleep(payload["handler_sleep"])
    return {"unexpected": True}


double_fork_late_write.__execution_kernel_revision__ = (
    "runtime-timeout-double-fork-test-v1"
)


def disable_local_deadline_then_write(payload, context):
    import dispatcher_sdk.execution_kernel._process_runtime as process_runtime

    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    signal.setitimer(signal.ITIMER_REAL, 0.0)
    process_runtime.time.monotonic = lambda: 0.0
    time.sleep(payload["sleep"])
    Path(payload["path"]).write_text("late", encoding="utf-8")
    return {"unexpected": True}


disable_local_deadline_then_write.__execution_kernel_revision__ = (
    "runtime-timeout-tamper-test-v1"
)


def inject_early_supervisor_alarm(payload, context):
    os.kill(os.getppid(), signal.SIGALRM)
    time.sleep(0.05)
    return {"completed": True}


inject_early_supervisor_alarm.__execution_kernel_revision__ = (
    "runtime-timeout-early-alarm-test-v1"
)


def started_then_late_write(payload, context):
    Path(payload["started"]).write_text("started", encoding="utf-8")
    time.sleep(payload["sleep"])
    Path(payload["late"]).write_text("late", encoding="utf-8")
    return {"unexpected": True}


started_then_late_write.__execution_kernel_revision__ = (
    "runtime-lifecycle-cancel-test-v1"
)


def started_then_late_write_with_pid(payload, context):
    Path(payload["started"]).write_text("started", encoding="utf-8")
    Path(payload["pid"]).write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(payload["sleep"])
    Path(payload["late"]).write_text("late", encoding="utf-8")
    return {"unexpected": True}


started_then_late_write_with_pid.__execution_kernel_revision__ = (
    "runtime-lifecycle-cancel-pid-test-v1"
)


def cooperative_until_cancelled(payload, context):
    Path(payload["started"]).write_text("started", encoding="utf-8")
    deadline = time.monotonic() + 1.0
    while context.is_active() and time.monotonic() < deadline:
        time.sleep(0.005)
    if context.is_active():
        Path(payload["late"]).write_text("late", encoding="utf-8")
    return {"active": context.is_active()}


cooperative_until_cancelled.__execution_kernel_revision__ = (
    "runtime-thread-cooperative-cancel-test-v1"
)


def gated_active_cancel_handler(payload, context):
    """Hold actual business entry until cancellation within its original cutoff."""
    import json

    Path(payload["pid"]).write_text(str(os.getpid()), encoding="utf-8")
    marker = Path(payload["started"])
    temporary = marker.with_suffix(".writing")
    temporary.write_text(json.dumps({"entered_at": time.time(),
        "budget": context.budget.to_dict()}), encoding="utf-8")
    os.replace(temporary, marker)
    while not Path(payload["release"]).exists():
        remaining = context.budget.remaining_work_seconds
        if remaining <= 0:
            raise TimeoutError("original handler work cutoff elapsed")
        time.sleep(min(.005, remaining))
    # A handler surviving cancellation can still perform the forbidden write.
    Path(payload["late"]).write_text("late", encoding="utf-8")
    return {"unexpected": True}


gated_active_cancel_handler.__execution_kernel_revision__ = "runtime-active-cancel-gate-v1"


class SlowJsonList(list):
    def __init__(self, path: str, delay: float) -> None:
        super().__init__(["encoded"])
        self.path = path
        self.delay = delay

    def __iter__(self):
        time.sleep(self.delay)
        Path(self.path).write_text("late", encoding="utf-8")
        return super().__iter__()


def slow_json_result(payload, context):
    return {"items": SlowJsonList(payload["path"], payload["sleep"])}


slow_json_result.__execution_kernel_revision__ = "runtime-timeout-json-test-v1"


def abrupt_process_exit(payload, context):
    os._exit(17)


abrupt_process_exit.__execution_kernel_revision__ = "runtime-process-exit-test-v1"


def recoverable_effect_handler(payload, context):
    def perform():
        Path(payload["marker"]).write_text("performed", encoding="utf-8")
        return {"receipt": "performed"}

    response = context.effects.execute_once(
        payload["effect_id"],
        "deliver",
        {"token": payload["token"]},
        perform,
    )
    return {"receipt": response}


recoverable_effect_handler.__execution_kernel_revision__ = "runtime-test-handlers-v2"


def effect_then_hang(payload, context):
    if payload["effect_state"] == "committed":
        context.effects.execute_once(
            payload["effect_id"],
            "publish",
            {"token": payload["token"]},
            lambda: {"receipt": "committed-before-timeout"},
        )
    else:
        def uncertain_call():
            raise RuntimeError("external outcome unknown")

        try:
            context.effects.execute_once(
                payload["effect_id"],
                "publish",
                {"token": payload["token"]},
                uncertain_call,
            )
        except RuntimeError:
            pass
    time.sleep(payload["sleep"])
    return {"unexpected": True}


effect_then_hang.__execution_kernel_revision__ = "runtime-test-handlers-v2"


class Clock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def make_command(
    execution_id: str,
    revision: str,
    *,
    handler_id: str = "echo",
    version: int = 1,
    attempts: int = 1,
    retry_timeouts: bool = False,
    timeout: float = 1,
    payload=None,
) -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=f"key-{execution_id}",
        registry_revision=revision,
        correlation_id=f"correlation-{execution_id}",
        causation_id=None,
        handler_id=handler_id,
        handler_contract_version=version,
        retry_policy=RetryPolicy(
            max_attempts=attempts,
            initial_backoff_seconds=0,
            backoff_multiplier=1,
            max_backoff_seconds=0,
            retry_timeouts=retry_timeouts,
        ),
        timeout_seconds=timeout,
        payload={"value": 7} if payload is None else payload,
    )


class RuntimeTests(unittest.TestCase):
    @contextmanager
    def runtime_case_evidence(self, prefix):
        from collections import deque
        from copy import deepcopy
        import traceback
        from dispatcher_sdk.execution_kernel import runtime as runtime_module
        from tests._storage_evidence import StorageEvidence

        root = retained_directory(prefix)
        evidence = {"test": self.id(), "interpreter": sys.executable,
                    "runtime_import": runtime_module.__file__, "root": str(root)}
        storage = StorageEvidence(root, self)
        storage.start(include_kernel=True)
        self.addCleanup(storage.stop)
        self.addCleanup(lambda: storage.save(checkpoint=evidence))
        native = deque(maxlen=16)
        lock = threading.Lock()
        original = runtime_module.invoke_process_handler

        def invoke(**kwargs):
            callbacks = deque(maxlen=128)
            item = {"command": kwargs["command"].to_dict(), "lease": kwargs["lease"].to_dict(),
                    "began": time.monotonic(), "callbacks": callbacks}
            with lock:
                native.append(item)
            for name in ("on_entered", "on_phase", "on_cleanup_confirmed"):
                callback = kwargs.get(name)
                if callback is not None:
                    def forward(*args, _callback=callback, _name=name, **options):
                        with lock:
                            callbacks.append({"callback": _name, "at": time.monotonic(),
                                              "arguments": deepcopy(args)})
                        return _callback(*args, **options)
                    kwargs[name] = forward
            try:
                result = original(**kwargs)
                with lock:
                    item["outcome"] = deepcopy(result)
                return result
            except BaseException as error:
                with lock:
                    item["error"] = {"type": type(error).__name__, "message": str(error),
                                     "traceback": traceback.format_exc()}
                raise
            finally:
                with lock:
                    item["elapsed"] = time.monotonic() - item["began"]

        with patch.object(runtime_module, "invoke_process_handler", invoke):
            try:
                yield root, evidence
            except BaseException as error:
                evidence["original_error"] = {"type": type(error).__name__, "message": str(error),
                                              "traceback": traceback.format_exc()}
                raise
            finally:
                with lock:
                    evidence["native_invocations"] = deepcopy(list(native))
                for invocation in evidence["native_invocations"]:
                    invocation["callbacks"] = list(invocation["callbacks"])
                try:
                    storage.save(phase="before-cleanup", checkpoint=evidence)
                    (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                except BaseException as error:
                    evidence["capture_error"] = {"type": type(error).__name__, "message": str(error),
                                                 "traceback": traceback.format_exc()}
                    if "original_error" not in evidence:
                        raise
                    print("runtime_case_capture_error=" + repr(error), flush=True)
                print("runtime_case_evidence=" + str(root / "evidence.json"), flush=True)

    def test_runtime_exposes_revision_cas_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("echo", 1): echo_handler},
                isolation_mode="thread",
            )
            try:
                command = make_command("runtime-cancel", stack.registry_revision)
                queued = stack.submit(command)
                cancelled = stack.cancel(
                    command.execution_id,
                    expected_revision=queued.revision,
                    reason="control-plane request",
                )
                self.assertEqual(cancelled.state, "cancelled")
                self.assertEqual(
                    cancelled.result.error.message, "control-plane request"
                )
            finally:
                stack.close()

    @unittest.skipIf(os.name == "nt", "native Windows has process isolation without fork")
    def test_auto_isolation_falls_back_to_thread_without_fork(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp, patch(
            "dispatcher_sdk.execution_kernel.runtime.multiprocessing.get_all_start_methods",
            return_value=["spawn"],
        ):
            path = Path(temp) / "portable.sqlite3"
            with Kernel.open_sqlite(path, {("echo", 1): echo_handler}) as runtime:
                self.assertEqual(runtime.isolation_mode, "thread")
                runtime.submit(make_command("portable", runtime.registry_revision))
                self.assertEqual(runtime.run_once().state, "succeeded")
            with self.assertRaisesRegex(ValueError, "requires POSIX fork or native Windows support"):
                Kernel.open_sqlite(path, {("echo", 1): echo_handler}, isolation_mode="process")

    def test_process_isolation_rejects_in_memory_database(self) -> None:
        if not (os.name == "posix" and "fork" in multiprocessing.get_all_start_methods()):
            self.skipTest("requires POSIX fork isolation")
        with self.assertRaisesRegex(ValueError, "file-backed.*memory"):
            Kernel.open_sqlite(
                ":memory:",
                {("echo", 1): echo_handler},
                isolation_mode="process",
            )

    def test_kernel_open_sqlite_needs_only_path_and_handlers_and_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            handlers = {("echo", 1): echo_handler}
            stack = Kernel.open_sqlite(path, handlers)
            try:
                cmd = make_command("open", stack.registry_revision)
                stack.submit(cmd)
                result = stack.run_once()
                self.assertEqual(result.state, "succeeded")
                self.assertEqual(result.result.value, {"echo": 7, "version": 1})
            finally:
                stack.close()
            restarted = Kernel.open_sqlite(path, handlers)
            try:
                self.assertEqual(restarted.kernel.get("open").state, "succeeded")
            finally:
                restarted.close()

    def test_submit_rejects_wrong_registry_without_persisting(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stack = Kernel.open_sqlite(Path(temp) / "kernel.sqlite3", {"echo": echo_handler})
            try:
                with self.assertRaises(RegistryRevisionMismatchError):
                    stack.submit(make_command("wrong", "another-revision"))
                with self.assertRaises(KeyError):
                    stack.kernel.get("wrong")
            finally:
                stack.close()

    def test_exact_registry_selection_and_bad_binding_do_not_block_later_item(self) -> None:
        with self.runtime_case_evidence("sdk-exact-registry-selection-") as (temp, evidence):
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("echo", 1): version_one, ("echo", 2): version_two},
                isolation_mode="thread",
            )
            self.addCleanup(stack.close)
            stack.kernel.submit(make_command("00-wrong-registry", "other"))
            stack.kernel.submit(
                make_command(
                    "01-bad-version",
                    stack.registry_revision,
                    handler_id="echo",
                    version=3,
                )
            )
            stack.submit(
                make_command(
                    "02-valid",
                    stack.registry_revision,
                    handler_id="echo",
                    version=2,
                )
            )
            result = stack.run_once()
            evidence["result"] = result.to_dict()
            evidence["observation"] = stack.observe(result.execution_id)
            self.assertEqual(result.execution_id, "02-valid")
            self.assertEqual(result.result.value, {"version": 2})
            rejected = stack.kernel.get("01-bad-version")
            self.assertEqual(rejected.state, "dead")
            self.assertEqual(rejected.result.error.code, "handler_contract_mismatch")
            self.assertEqual(stack.kernel.get("00-wrong-registry").state, "queued")

    def test_registry_revision_binds_handler_implementation_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            historical = Kernel.open_sqlite(
                path,
                {("echo", 1): version_one},
                isolation_mode="thread",
            )
            old_revision = historical.registry_revision
            try:
                historical.submit(make_command("historical", old_revision))
            finally:
                historical.close()

            current = Kernel.open_sqlite(
                path,
                {("echo", 1): version_two},
                isolation_mode="thread",
            )
            try:
                self.assertNotEqual(current.registry_revision, old_revision)
                current.submit(make_command("current", current.registry_revision))
                result = current.run_once()
                self.assertEqual(result.execution_id, "current")
                self.assertEqual(result.result.value, {"version": 2})
                self.assertEqual(current.kernel.get("historical").state, "queued")
            finally:
                current.close()

    def test_only_explicit_retryable_error_retries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            stack = Kernel.open_sqlite(
                path,
                {("generic", 1): generic_failure, ("retry", 1): retry_by_attempt},
                isolation_mode="thread",
            )
            try:
                stack.submit(
                    make_command(
                        "generic",
                        stack.registry_revision,
                        handler_id="generic",
                        attempts=3,
                    )
                )
                self.assertEqual(stack.run_once().state, "failed")
                stack.submit(
                    make_command(
                        "retry",
                        stack.registry_revision,
                        handler_id="retry",
                        attempts=2,
                        # This tests retry classification. Both attempts share
                        # the original work cutoff, including control and
                        # receipt work between them; deadline exhaustion has
                        # dedicated budget tests.
                        timeout=5,
                    )
                )
                self.assertEqual(stack.run_once().state, "queued")
                succeeded = stack.run_once()
                self.assertEqual(succeeded.state, "succeeded")
                self.assertEqual(succeeded.result.value, {"attempt": 2})
            finally:
                stack.close()

    def test_handler_context_executes_and_records_effect_once(self) -> None:
        root = retained_directory("sdk-effect-handler-outcome-")
        stack = Kernel.open_sqlite(
            root / "kernel.sqlite3",
            {("effect", 1): effect_handler},
        )
        try:
            stack.submit(
                make_command(
                    "effects",
                    stack.registry_revision,
                    handler_id="effect",
                )
            )
            result = stack.run_once()
            record = {"test": self.id(), "interpreter": sys.executable,
                "result": result.to_dict(), "original_timeout": 1}
            (root / "evidence.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            print("effect_handler_evidence=" + str(root / "evidence.json"), flush=True)
            self.assertEqual(result.state, "succeeded", result.to_dict())
            self.assertEqual(result.result.effect_ids, ["effect-runtime"])
            self.assertEqual(stack.kernel.get_effect("effect-runtime").state, "committed")
        finally:
            stack.close()

    def test_runtime_parks_and_human_recovery_safely_continues(self) -> None:
        for decision in ("applied", "not_applied"):
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as temp:
                clock = Clock()
                marker = Path(temp) / "performed.txt"
                path = Path(temp) / "kernel.sqlite3"
                stack = Kernel.open_sqlite(
                    path,
                    {("recover", 1): recoverable_effect_handler},
                    isolation_mode="thread",
                    lease_seconds=5,
                    now=clock,
                )
                effect_id = f"effect-{decision}"
                try:
                    stack.submit(
                        make_command(
                            f"recover-{decision}",
                            stack.registry_revision,
                            handler_id="recover",
                            attempts=2,
                            payload={
                                "effect_id": effect_id,
                                "marker": str(marker),
                                "token": decision,
                            },
                        )
                    )
                    first = stack.kernel.start(
                        stack.kernel.claim(
                            "crashing-worker",
                            registry_revision=stack.registry_revision,
                        )
                    )
                    stack.kernel.prepare_effect(
                        first,
                        effect_id=effect_id,
                        name="deliver",
                        request={"token": decision},
                    )
                    clock.advance(6)
                    parked = stack.kernel.reap()[0]
                    self.assertEqual(parked.state, "recovery_required")
                    self.assertEqual(parked.recovery_effect_id, effect_id)
                    self.assertEqual(parked.attempt, 1)
                    self.assertIsNone(parked.result)
                    self.assertEqual(stack.kernel.result_outbox(), [])
                    uncertain = stack.kernel.get_effect(effect_id)
                    self.assertEqual(uncertain.state, "indeterminate")

                    revision = stack.registry_revision
                    stack.close()
                    stack = Kernel.open_sqlite(
                        path,
                        {("recover", 1): recoverable_effect_handler},
                        isolation_mode="thread",
                        lease_seconds=5,
                        now=clock,
                    )
                    self.assertEqual(stack.registry_revision, revision)
                    self.assertEqual(
                        stack.kernel.get(parked.execution_id).state,
                        "recovery_required",
                    )

                    response = {"receipt": "human-confirmed"} if decision == "applied" else None
                    stack.kernel.resolve_effect(
                        effect_id,
                        decision=decision,
                        response=response,
                        expected_revision=uncertain.revision,
                        recovery_id=f"human-{decision}",
                    )
                    self.assertEqual(stack.kernel.get(parked.execution_id).state, "queued")
                    terminal = stack.run_once()
                    self.assertEqual(terminal.state, "succeeded")
                    self.assertEqual(terminal.attempt, 2)
                    self.assertEqual(terminal.result.effect_ids, [effect_id])
                    if decision == "applied":
                        self.assertFalse(marker.exists())
                        self.assertEqual(
                            terminal.result.value,
                            {"receipt": {"receipt": "human-confirmed"}},
                        )
                    else:
                        self.assertEqual(marker.read_text(encoding="utf-8"), "performed")
                        self.assertEqual(
                            stack.kernel.get_effect(effect_id).recovery_decision,
                            None,
                        )
                    execution_events = [
                        event["event_type"]
                        for event in stack.kernel.events(parked.execution_id)
                    ]
                    self.assertIn(
                        "lease_expired_effect_recovery_required", execution_events
                    )
                    self.assertIn("effect_recovery_resolved", execution_events)
                finally:
                    stack.close()

    def test_runtime_treats_recovery_signal_as_nonterminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock()
            marker = Path(temp) / "must-not-run.txt"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("recover", 1): recoverable_effect_handler},
                isolation_mode="thread",
                lease_seconds=5,
                now=clock,
            )
            try:
                command = make_command(
                    "runtime-recovery-signal",
                    stack.registry_revision,
                    handler_id="recover",
                    attempts=2,
                    payload={
                        "effect_id": "runtime-uncertain",
                        "marker": str(marker),
                        "token": "signal",
                    },
                )
                stack.submit(command)
                first = stack.kernel.start(
                    stack.kernel.claim(
                        "first-worker", registry_revision=stack.registry_revision
                    )
                )
                stack.kernel.prepare_effect(
                    first,
                    effect_id="runtime-uncertain",
                    name="deliver",
                    request={"token": "signal"},
                )
                effect_claim = stack.kernel.claim_effect(first, "runtime-uncertain")
                stack.kernel.mark_effect_indeterminate(
                    "runtime-uncertain",
                    {"reason": "simulated crash"},
                    first,
                    effect_claim.claim_id,
                )
                started_at = stack.kernel.get(command.execution_id).started_at
                parked = stack.kernel.complete(
                    first,
                    ExecutionResultV2(
                        result_id="runtime-recovery-retry",
                        execution_id=command.execution_id,
                        status="failed",
                        attempt=first.attempt,
                        fence=first.fence,
                        effect_ids=["runtime-uncertain"],
                        started_at=started_at,
                        completed_at=clock(),
                        correlation_id=command.correlation_id,
                        causation_id=command.causation_id,
                        value=None,
                        error=ExecutionError(
                            code="worker_crash",
                            message="retry to encounter durable uncertainty",
                            retryable=True,
                            details={},
                        ),
                    ),
                )
                self.assertEqual(parked.state, "recovery_required")
                self.assertEqual(parked.recovery_effect_id, "runtime-uncertain")
                self.assertIsNone(parked.result)
                self.assertEqual(stack.kernel.result_outbox(), [])
                self.assertFalse(marker.exists())
                self.assertEqual(
                    stack.kernel.events(command.execution_id)[-1]["event_type"],
                    "effect_recovery_required",
                )
                recovery_event = stack.kernel.events_since(0)[-1]
                self.assertEqual(
                    recovery_event.data["effect_revision"],
                    stack.kernel.get_effect("runtime-uncertain").revision,
                )
            finally:
                stack.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_timeout_result_recovers_persisted_effect_identities(self) -> None:
        for effect_state in ("committed", "indeterminate"):
            with self.subTest(effect_state=effect_state), tempfile.TemporaryDirectory() as temp:
                effect_id = f"timeout-{effect_state}"
                stack = Kernel.open_sqlite(
                    Path(temp) / "kernel.sqlite3",
                    {("effect-hang", 1): effect_then_hang},
                    isolation_mode="process",
                )
                try:
                    stack.submit(
                        make_command(
                            f"execution-{effect_state}",
                            stack.registry_revision,
                            handler_id="effect-hang",
                            timeout=2.0,
                            payload={
                                "effect_id": effect_id,
                                "effect_state": effect_state,
                                "token": effect_state,
                                "sleep": 5,
                            },
                        )
                    )
                    terminal = stack.run_once()
                    expected_state = (
                        "timed_out" if effect_state == "committed"
                        else "recovery_required"
                    )
                    self.assertEqual(terminal.state, expected_state)
                    self.assertEqual(
                        stack.kernel.get_effect(effect_id).state,
                        effect_state,
                    )
                    if effect_state == "committed":
                        self.assertEqual(terminal.result.effect_ids, [effect_id])
                        self.assertEqual(
                            stack.kernel.result_outbox()[0]["result"].effect_ids,
                            [effect_id],
                        )
                    else:
                        self.assertIsNone(terminal.result)
                        self.assertEqual(terminal.recovery_effect_id, effect_id)
                        self.assertEqual(stack.kernel.result_outbox(), [])
                finally:
                    stack.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_posix_timeout_kills_late_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "late.txt"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("late", 1): late_file_write},
                isolation_mode="process",
            )
            try:
                stack.submit(
                    make_command(
                        "late",
                        stack.registry_revision,
                        handler_id="late",
                        timeout=0.02,
                        payload={"path": str(marker), "sleep": 0.2},
                    )
                )
                result = stack.run_once()
                self.assertEqual(result.state, "timed_out")
                time.sleep(0.25)
                self.assertFalse(marker.exists())
            finally:
                stack.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_posix_deadline_survives_parent_scheduler_stall(self) -> None:
        real_poll = Connection.poll
        parent_poll_calls = 0

        def delayed_second_poll(connection, timeout=0.0):
            nonlocal parent_poll_calls
            parent_poll_calls += 1
            if parent_poll_calls == 2:
                time.sleep(0.15)
            return real_poll(connection, timeout)

        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "late-after-parent-stall.txt"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("late", 1): late_file_write},
                isolation_mode="process",
            )
            try:
                stack.submit(
                    make_command(
                        "parent-stall",
                        stack.registry_revision,
                        handler_id="late",
                        timeout=0.02,
                        payload={"path": str(marker), "sleep": 0.1},
                    )
                )
                with patch.object(
                    Connection,
                    "poll",
                    new=delayed_second_poll,
                ):
                    result = stack.run_once()
                self.assertEqual(result.state, "timed_out")
                self.assertFalse(marker.exists())
            finally:
                stack.close()

    @unittest.skipUnless(
        sys.platform.startswith("linux")
        and Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children").is_file(),
        "requires Linux subreaper process isolation",
    )
    def test_parent_deadline_poll_miss_preserves_detached_child_cleanup(self) -> None:
        real_poll = Connection.poll
        parent_poll_calls = 0

        def miss_deadline_poll(connection, timeout=0.0):
            nonlocal parent_poll_calls
            parent_poll_calls += 1
            if parent_poll_calls == 2:
                time.sleep(max(0.0, timeout))
                return False
            return real_poll(connection, timeout)

        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "late-after-parent-poll-miss.txt"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("detached", 1): spawn_late_child},
                isolation_mode="process",
            )
            try:
                stack.submit(
                    make_command(
                        "parent-poll-miss",
                        stack.registry_revision,
                        handler_id="detached",
                        timeout=0.02,
                        payload={
                            "path": str(marker),
                            "child_sleep": 0.15,
                            "handler_sleep": 1.0,
                            "new_session": True,
                        },
                    )
                )
                with patch.object(Connection, "poll", new=miss_deadline_poll):
                    result = stack.run_once()
                self.assertEqual(result.state, "timed_out")
                time.sleep(0.25)
                self.assertFalse(marker.exists())
            finally:
                stack.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_posix_deadline_cannot_be_caught_and_kills_child_process_group(self) -> None:
        handlers = [
            (
                "catch-timeout",
                catch_base_exception_then_write,
                {"sleep": 0.2},
            ),
            (
                "child-timeout-same-group",
                spawn_late_child,
                {
                    "child_sleep": 0.15,
                    "handler_sleep": 1.0,
                    "new_session": False,
                },
            ),
        ]
        linux_children = Path(
            f"/proc/{os.getpid()}/task/{os.getpid()}/children"
        )
        if linux_children.is_file():
            handlers.append((
                "child-timeout-new-session",
                spawn_late_child,
                {
                    "child_sleep": 0.15,
                    "handler_sleep": 1.0,
                    "new_session": True,
                },
            ))
        for handler_id, handler, timing in handlers:
            with self.subTest(handler_id=handler_id), tempfile.TemporaryDirectory() as temp:
                marker = Path(temp) / f"{handler_id}.txt"
                stack = Kernel.open_sqlite(
                    Path(temp) / "kernel.sqlite3",
                    {(handler_id, 1): handler},
                    isolation_mode="process",
                )
                try:
                    stack.submit(
                        make_command(
                            handler_id,
                            stack.registry_revision,
                            handler_id=handler_id,
                            timeout=0.02,
                            payload={"path": str(marker), **timing},
                        )
                    )
                    result = stack.run_once()
                    self.assertEqual(result.state, "timed_out")
                    time.sleep(0.25)
                    self.assertFalse(marker.exists())
                finally:
                    stack.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_posix_deadline_includes_strict_json_result_serialization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "late-serialization.txt"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("slow-json", 1): slow_json_result},
                isolation_mode="process",
            )
            try:
                stack.submit(
                    make_command(
                        "slow-json",
                        stack.registry_revision,
                        handler_id="slow-json",
                        timeout=0.02,
                        payload={"path": str(marker), "sleep": 0.2},
                    )
                )
                result = stack.run_once()
                self.assertEqual(result.state, "timed_out")
                time.sleep(0.25)
                self.assertFalse(marker.exists())
            finally:
                stack.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_success_path_reaps_same_group_and_new_session_children(self) -> None:
        modes = [False]
        if Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children").is_file():
            modes.append(True)
        for new_session in modes:
            with self.subTest(new_session=new_session), tempfile.TemporaryDirectory() as temp:
                marker = Path(temp) / f"success-child-{new_session}.txt"
                stack = Kernel.open_sqlite(
                    Path(temp) / "kernel.sqlite3",
                    {("spawn", 1): spawn_late_child},
                    isolation_mode="process",
                )
                try:
                    stack.submit(
                        make_command(
                            f"success-child-{new_session}",
                            stack.registry_revision,
                            handler_id="spawn",
                            timeout=1.0,
                            payload={
                                "path": str(marker),
                                "child_sleep": 0.15,
                                "handler_sleep": 0.0,
                                "new_session": new_session,
                            },
                        )
                    )
                    result = stack.run_once()
                    self.assertEqual(result.state, "succeeded")
                    time.sleep(0.25)
                    self.assertFalse(marker.exists())
                finally:
                    stack.close()

    @unittest.skipUnless(
        sys.platform.startswith("linux")
        and Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children").is_file(),
        "requires Linux subreaper process isolation",
    )
    def test_timeout_reaps_double_forked_new_session_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "double-fork.txt"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("double-fork", 1): double_fork_late_write},
                isolation_mode="process",
            )
            try:
                stack.submit(
                    make_command(
                        "double-fork",
                        stack.registry_revision,
                        handler_id="double-fork",
                        timeout=0.02,
                        payload={
                            "path": str(marker),
                            "child_sleep": 0.15,
                            "handler_sleep": 1.0,
                        },
                    )
                )
                result = stack.run_once()
                self.assertEqual(result.state, "timed_out")
                time.sleep(0.25)
                self.assertFalse(marker.exists())
            finally:
                stack.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_handler_cannot_cancel_or_forge_supervisor_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "tampered-deadline.txt"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("tamper", 1): disable_local_deadline_then_write},
                isolation_mode="process",
            )
            try:
                stack.submit(
                    make_command(
                        "tamper",
                        stack.registry_revision,
                        handler_id="tamper",
                        timeout=0.02,
                        payload={"path": str(marker), "sleep": 0.15},
                    )
                )
                result = stack.run_once()
                self.assertEqual(result.state, "timed_out")
                time.sleep(0.25)
                self.assertFalse(marker.exists())
            finally:
                stack.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_early_supervisor_alarm_does_not_shorten_monotonic_deadline(self) -> None:
        with self.runtime_case_evidence("sdk-early-supervisor-alarm-") as (temp, evidence):
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("early-alarm", 1): inject_early_supervisor_alarm},
                isolation_mode="process",
            )
            self.addCleanup(stack.close)
            stack.submit(
                make_command(
                    "early-alarm",
                    stack.registry_revision,
                    handler_id="early-alarm",
                    timeout=1.0,
                )
            )
            result = stack.run_once()
            evidence["result"] = result.to_dict()
            evidence["observation"] = stack.observe(result.execution_id)
            self.assertEqual(result.state, "succeeded")
            self.assertEqual(result.result.value, {"completed": True})

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_close_revokes_and_reaps_active_process_handler(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            started = Path(temp) / "started.txt"
            late = Path(temp) / "late.txt"
            handlers = {("lifecycle", 1): started_then_late_write}
            stack = Kernel.open_sqlite(path, handlers, isolation_mode="process")
            command = make_command(
                "close-active",
                stack.registry_revision,
                handler_id="lifecycle",
                timeout=2.0,
                payload={
                    "started": str(started),
                    "late": str(late),
                    "sleep": 0.3,
                },
            )
            stack.submit(command)
            outcomes = []
            errors = []

            def drive():
                try:
                    outcomes.append(stack.run_once())
                except BaseException as exc:
                    errors.append(exc)

            driver = threading.Thread(target=drive)
            driver.start()
            entry_deadline = time.monotonic() + command.timeout_seconds
            while not started.exists() and not outcomes and not errors and time.monotonic() < entry_deadline:
                time.sleep(0.005)
            self.assertTrue(started.exists())
            stack.close()
            driver.join(1.0)
            self.assertFalse(driver.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(outcomes[0].state, "running")
            time.sleep(0.35)
            self.assertFalse(late.exists())
            reopened = Kernel.open_sqlite(path, handlers, isolation_mode="process")
            try:
                self.assertEqual(reopened.kernel.get(command.execution_id).state, "running")
            finally:
                reopened.close()

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_cancel_revokes_active_handler_without_run_once_exception(self) -> None:
        import json
        import traceback
        from tests._acceptance_evidence import retained_directory
        from dispatcher_sdk.execution_kernel import runtime as runtime_module

        root = retained_directory("sdk-native-active-cancel-")
        started, pid_file, late, release = (root / name for name in
            ("started.json", "handler.pid", "late.txt", "release"))
        evidence = {"test": self.id(), "interpreter": sys.executable,
            "execution_timeout": 2.0, "readiness_timeout": 5.0, "phases": []}
        outcomes, errors = [], []
        driver = None

        stack = Kernel.open_sqlite(root / "kernel.sqlite3", {("lifecycle", 1): gated_active_cancel_handler},
                                  isolation_mode="process")
        command = make_command("cancel-active", stack.registry_revision, handler_id="lifecycle",
            timeout=2.0, payload={"started": str(started), "pid": str(pid_file),
                "late": str(late), "release": str(release)})
        evidence["command"] = command.to_dict()
        cleanup = evidence["actual_cleanup_callbacks"] = []
        original_invoke = runtime_module.invoke_process_handler

        def invoke(**kwargs):
            original_cleanup = kwargs["on_cleanup_confirmed"]

            def confirmed():
                item = {"confirmed_at": time.time(), "monotonic": time.monotonic()}
                cleanup.append(item)
                try:
                    result = original_cleanup()
                    item["returned"] = True
                    return result
                except BaseException as error:
                    item["error"] = {"type": type(error).__name__, "message": str(error),
                                     "traceback": traceback.format_exc()}
                    raise
                finally:
                    item["elapsed"] = time.monotonic() - item["monotonic"]

            kwargs["on_cleanup_confirmed"] = confirmed
            return original_invoke(**kwargs)

        invocation_patch = patch.object(runtime_module, "invoke_process_handler", invoke)
        invocation_patch.start()
        self.addCleanup(invocation_patch.stop)

        def capture(phase):
            item = {"phase": phase, "at": time.time(), "monotonic": time.monotonic(),
                "started": started.exists(), "late": late.exists(), "gate_open": release.exists(),
                "driver_alive": driver is not None and driver.is_alive(),
                "outcomes": [value.to_dict() for value in outcomes], "driver_errors": list(errors)}
            try:
                item["kernel"] = stack.kernel.get(command.execution_id).to_dict()
                item["entry"] = json.loads(started.read_text()) if started.exists() else None
            except Exception as error:
                item["inspection_error"] = {"type": type(error).__name__, "message": str(error)}
            evidence["phases"].append(item)
            (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

        try:
            stack.submit(command)

            def drive():
                try:
                    outcomes.append(stack.run_once())
                except BaseException as error:
                    errors.append({"type": type(error).__name__, "message": str(error),
                        "traceback": traceback.format_exc()})

            driver = threading.Thread(target=drive)
            readiness_deadline = time.monotonic() + evidence["readiness_timeout"]
            driver.start()
            while not started.exists() and not outcomes and not errors and time.monotonic() < readiness_deadline:
                time.sleep(.005)
            capture("entry_wait_finished")
            self.assertTrue(started.exists(), "actual handler entry was not observed; retained evidence: " + str(root))
            handler_pid = int(pid_file.read_text(encoding="utf-8"))
            running = stack.kernel.get(command.execution_id)
            evidence["before_cancel"] = running.to_dict()
            capture("before_cancel")
            self.assertEqual(running.state, "running")
            entry_budget = json.loads(started.read_text(encoding="utf-8"))["budget"]
            work_cutoff = entry_budget["effective_work_deadline_at"]
            self.assertEqual(entry_budget["clock_status"], "trusted")
            self.assertLess(time.time(), work_cutoff)
            cancelled = stack.cancel(command.execution_id, expected_revision=running.revision,
                                     reason="operator cancellation")
            evidence["cancelled"] = cancelled.to_dict()
            evidence["cancel_returned_at"] = time.time()
            release.touch()
            driver.join(1.0)
            capture("after_cancel")
            # Actual cancellation and containment precede the work cutoff.
            # Trailing diagnostic persistence may delay cancel's return.
            self.assertLess(cancelled.result.completed_at, work_cutoff)
            self.assertEqual(1, len(cleanup))
            self.assertTrue(cleanup[0].get("returned"), cleanup)
            self.assertLess(cleanup[0]["confirmed_at"], work_cutoff)
            self.assertFalse(driver.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(cancelled.state, "cancelled")
            self.assertEqual(outcomes, [cancelled])
            for _ in range(100):
                try:
                    os.kill(handler_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(.005)
            time.sleep(.35)
            capture("containment_checked")
            with self.assertRaises(ProcessLookupError):
                os.kill(handler_pid, 0)
            self.assertFalse(late.exists())
        except BaseException as error:
            evidence["error"] = {"type": type(error).__name__, "message": str(error),
                "traceback": traceback.format_exc()}
            raise
        finally:
            capture("before_close")
            try:
                stack.close()
            finally:
                if driver is not None:
                    driver.join(1.0)
                capture("after_close")
                print("native_active_cancel_evidence=" + str(root / "evidence.json"), flush=True)

    def test_cancel_racing_terminal_commit_has_one_atomic_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("echo", 1): echo_handler},
                isolation_mode="thread",
            )
            try:
                command = make_command(
                    "cancel-finalize-race",
                    stack.registry_revision,
                    payload={"value": "done"},
                )
                stack.submit(command)
                finalizing = threading.Event()
                release = threading.Event()
                real_complete = stack.kernel._complete_sdk_result

                def pause_finalization(*args, **kwargs):
                    finalizing.set()
                    self.assertTrue(release.wait(1.0))
                    return real_complete(*args, **kwargs)

                run_outcomes = []
                run_errors = []
                cancel_outcomes = []
                cancel_errors = []

                def drive():
                    try:
                        run_outcomes.append(stack.run_once())
                    except BaseException as exc:
                        run_errors.append(exc)

                def cancel():
                    try:
                        snapshot = stack.kernel.get(command.execution_id)
                        cancel_outcomes.append(
                            stack.cancel(
                                command.execution_id,
                                expected_revision=snapshot.revision,
                            )
                        )
                    except BaseException as exc:
                        cancel_errors.append(exc)

                with patch.object(stack.kernel, "_complete_sdk_result", new=pause_finalization):
                    driver = threading.Thread(target=drive)
                    driver.start()
                    self.assertTrue(finalizing.wait(1.0))
                    canceller = threading.Thread(target=cancel)
                    canceller.start()
                    time.sleep(0.02)
                    self.assertTrue(canceller.is_alive())
                    release.set()
                    driver.join(1.0)
                    canceller.join(1.0)

                self.assertFalse(driver.is_alive())
                self.assertFalse(canceller.is_alive())
                self.assertEqual(run_errors, [])
                self.assertEqual(len(run_outcomes), 1)
                self.assertEqual(run_outcomes[0].state, "succeeded")
                self.assertEqual(cancel_outcomes, [])
                self.assertEqual(len(cancel_errors), 1)
                self.assertEqual(
                    stack.kernel.get(command.execution_id).state, "succeeded"
                )
            finally:
                stack.close()

    def test_thread_cancel_revokes_cooperative_handler_authority(self) -> None:
        import json
        import traceback
        from tests._acceptance_evidence import retained_directory

        root = retained_directory("sdk-thread-active-cancel-")
        started, late, entry = (root / name for name in ("started.txt", "late.txt", "entry.json"))
        evidence = {"test": self.id(), "interpreter": sys.executable,
            "execution_timeout": 2.0, "readiness_timeout": 5.0, "handler_loop_timeout": 1.0, "phases": []}
        outcomes, errors = [], []
        driver = None

        def recorded_handler(payload, context):
            Path(payload["entry"]).write_text(json.dumps({"entered_at": time.time(),
                "budget": context.budget.to_dict()}), encoding="utf-8")
            return cooperative_until_cancelled(payload, context)

        recorded_handler.__execution_kernel_revision__ = "runtime-cooperative-cancel-evidence-v1"
        stack = Kernel.open_sqlite(root / "kernel.sqlite3", {("cooperative", 1): recorded_handler},
                                  isolation_mode="thread")
        command = make_command("thread-cancel-active", stack.registry_revision, handler_id="cooperative",
            timeout=2.0, payload={"started": str(started), "late": str(late), "entry": str(entry)})
        evidence["command"] = command.to_dict()

        def capture(phase):
            item = {"phase": phase, "at": time.time(), "monotonic": time.monotonic(),
                "started": started.exists(), "late": late.exists(),
                "driver_alive": driver is not None and driver.is_alive(),
                "outcomes": [value.to_dict() for value in outcomes], "driver_errors": list(errors)}
            try:
                item["kernel"] = stack.kernel.get(command.execution_id).to_dict()
                item["entry"] = json.loads(entry.read_text()) if entry.exists() else None
            except Exception as error:
                item["inspection_error"] = {"type": type(error).__name__, "message": str(error)}
            evidence["phases"].append(item)
            (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

        try:
            stack.submit(command)

            def drive():
                try:
                    outcomes.append(stack.run_once())
                except BaseException as error:
                    errors.append({"type": type(error).__name__, "message": str(error),
                        "traceback": traceback.format_exc()})

            driver = threading.Thread(target=drive)
            readiness_deadline = time.monotonic() + evidence["readiness_timeout"]
            driver.start()
            while not started.exists() and not outcomes and not errors and time.monotonic() < readiness_deadline:
                time.sleep(.005)
            capture("entry_wait_finished")
            self.assertTrue(started.exists(), "actual handler entry was not observed; retained evidence: " + str(root))
            running = stack.kernel.get(command.execution_id)
            evidence["before_cancel"] = running.to_dict()
            capture("before_cancel")
            self.assertEqual(running.state, "running")
            cancelled = stack.cancel(command.execution_id, expected_revision=running.revision,
                                     reason="cooperative cancellation")
            evidence["cancelled"] = cancelled.to_dict()
            driver.join(1.0)
            capture("after_cancel")
            self.assertFalse(driver.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(outcomes, [cancelled])
            self.assertEqual(cancelled.state, "cancelled")
            self.assertFalse(late.exists())
        except BaseException as error:
            evidence["error"] = {"type": type(error).__name__, "message": str(error),
                "traceback": traceback.format_exc()}
            raise
        finally:
            capture("before_close")
            try:
                stack.close()
            finally:
                if driver is not None:
                    driver.join(1.0)
                capture("after_close")
                print("thread_active_cancel_evidence=" + str(root / "evidence.json"), flush=True)

    @unittest.skipUnless(
        os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
        "requires POSIX fork isolation",
    )
    def test_early_process_exit_is_failure_not_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("abrupt", 1): abrupt_process_exit},
                isolation_mode="process",
            )
            try:
                stack.submit(
                    make_command(
                        "abrupt",
                        stack.registry_revision,
                        handler_id="abrupt",
                        timeout=5.0,
                    )
                )
                result = stack.run_once()
                self.assertEqual(result.state, "failed")
                self.assertEqual(result.result.error.code, "handler_process_exit")
            finally:
                stack.close()

    def test_thread_fallback_revokes_late_effect_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock(time.time())
            entered = threading.Event()
            release = threading.Event()
            attempted = threading.Event()
            performed = threading.Event()
            denied = []

            def late_effect(payload, context):
                entered.set()
                release.wait(5)
                try:
                    context.effects.execute_once(
                        "late-effect",
                        "notify",
                        {},
                        lambda: performed.set(),
                    )
                except BaseException as exc:
                    denied.append(exc)
                    raise
                finally:
                    attempted.set()
                return None

            late_effect.__execution_kernel_revision__ = "thread-timeout-test-v1"

            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("late-effect", 1): late_effect},
                isolation_mode="thread",
                now=clock,
            )
            outcomes = []
            errors = []

            def drive():
                try:
                    outcomes.append(stack.run_once())
                except BaseException as exc:
                    errors.append(exc)

            driver = threading.Thread(target=drive)
            try:
                stack.submit(
                    make_command(
                        "thread-timeout",
                        stack.registry_revision,
                        handler_id="late-effect",
                        timeout=5,
                    )
                )
                driver.start()
                self.assertTrue(entered.wait(2))
                # Entry is downstream of the durable ACK. Expire that already
                # running execution while its actual Python call remains blocked.
                clock.advance(6)
                driver.join(2)
                self.assertFalse(driver.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(outcomes), 1)
                self.assertEqual(outcomes[0].state, "timed_out")
                release.set()
                self.assertTrue(attempted.wait(1))
                self.assertFalse(performed.is_set())
                self.assertEqual(len(denied), 1)
                self.assertEqual(type(denied[0]).__name__, "StaleFenceError")
                with self.assertRaises(KeyError):
                    stack.kernel.get_effect("late-effect")
            finally:
                release.set()
                if driver.ident is not None:
                    driver.join(2)
                stack.close()

    def test_thread_business_result_survives_real_observation_writer_during_final_close(self) -> None:
        from contextlib import closing
        import sqlite3
        import traceback
        from dispatcher_sdk.execution_kernel.context import HandlerContext

        with self.runtime_case_evidence("sdk-thread-business-final-close-") as (root, evidence):
            entered, release = threading.Event(), threading.Event()
            calls, outcomes, errors, close_events = [], [], [], []

            def business(_payload, context):
                entered.set()
                if not release.wait(.5):
                    raise RuntimeError("fixture writer did not enter within the original work window")
                calls.append(context.budget.to_dict())
                return {"business_count": len(calls)}

            business.__execution_kernel_revision__ = "real-thread-final-close-v1"
            runtime = Kernel.open_sqlite(root / "kernel.sqlite3", {"business": business},
                                        isolation_mode="thread", max_thread_workers=1)
            self.addCleanup(runtime.close)
            runtime.submit(make_command("final-close", runtime.registry_revision,
                                        handler_id="business", timeout=1))
            original_close = HandlerContext.close

            def close(context, *args, **kwargs):
                close_events.append({"phase": "started", "at": time.monotonic()})
                try:
                    return original_close(context, *args, **kwargs)
                finally:
                    close_events.append({"phase": "finished", "at": time.monotonic()})

            def drive():
                try:
                    outcomes.append(runtime.run_once())
                except BaseException as error:
                    errors.append({"type": type(error).__name__, "message": str(error),
                                   "traceback": traceback.format_exc()})

            driver = threading.Thread(target=drive)
            try:
                with patch.object(HandlerContext, "close", close):
                    driver.start()
                    self.assertTrue(entered.wait(3))
                    with closing(sqlite3.connect(runtime.observation_journal.path, timeout=1)) as writer:
                        writer.execute("BEGIN IMMEDIATE")
                        release.set()
                        driver.join(3)
                        evidence.update(calls=calls, outcomes=[result.to_dict() for result in outcomes],
                                        errors=errors, close_events=close_events,
                                        driver_alive=driver.is_alive())
                        self.assertFalse(driver.is_alive())
                        self.assertEqual([], errors)
                        self.assertEqual(1, len(calls))
                        self.assertEqual(1, len(outcomes))
                        self.assertEqual("succeeded", outcomes[0].state)
                        self.assertEqual({"business_count": 1}, outcomes[0].result.value)
                        self.assertGreater(calls[0]["remaining_work_seconds"], 0)
                        self.assertLess(outcomes[0].result.completed_at,
                                        calls[0]["effective_work_deadline_at"])
                        self.assertTrue(any(item["phase"] == "started" for item in close_events))
                        writer.rollback()
            finally:
                release.set()
                if driver.ident is not None:
                    driver.join(3)

    def test_thread_timeout_slots_are_bounded_and_close_is_reentrant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock(time.time())
            entered = threading.Event()
            release = threading.Event()
            finished = threading.Event()
            wrapper_finished = threading.Event()

            def blocked(_payload, _context):
                entered.set()
                release.wait(5)
                finished.set()
                return {"done": True}

            blocked.__execution_kernel_revision__ = "bounded-thread-test-v1"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("blocked", 1): blocked},
                isolation_mode="thread",
                max_thread_workers=1,
                now=clock,
            )
            outcomes = []
            errors = []
            thread_finished = stack._thread_finished

            def observed_thread_finished(authority, generation, **options):
                try:
                    return thread_finished(authority, generation, **options)
                finally:
                    if generation[0] == "blocked-1":
                        wrapper_finished.set()

            stack._thread_finished = observed_thread_finished

            def drive():
                try:
                    outcomes.append(stack.run_once())
                except BaseException as exc:
                    errors.append(exc)

            driver = threading.Thread(target=drive)
            try:
                stack.submit(
                    make_command(
                        "blocked-1",
                        stack.registry_revision,
                        handler_id="blocked",
                        timeout=5,
                    )
                )
                stack.submit(
                    make_command(
                        "blocked-2",
                        stack.registry_revision,
                        handler_id="blocked",
                        timeout=5,
                    )
                )
                driver.start()
                self.assertTrue(entered.wait(2))
                clock.advance(6)
                driver.join(2)
                self.assertFalse(driver.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(outcomes), 1)
                self.assertEqual(outcomes[0].state, "timed_out")
                self.assertFalse(finished.is_set())

                # The timed-out Python call still owns the only slot.  The
                # second item must remain queued and its handler must not run.
                self.assertIsNone(stack.run_once())
                self.assertEqual(stack.kernel.get("blocked-2").state, "queued")

                stack.close()
                stack.close()
                self.assertIsNone(stack.run_once())
            finally:
                release.set()
                if driver.ident is not None:
                    driver.join(2)
                self.assertTrue(wrapper_finished.wait(1))
                self.assertTrue(finished.is_set())
                stack.close()

    def test_thread_timeout_releases_slot_after_underlying_call_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock(time.time())
            entered = threading.Event()
            release = threading.Event()
            finished = threading.Event()

            def blocked(_payload, _context):
                entered.set()
                release.wait(5)
                finished.set()
                return {"done": True}

            blocked.__execution_kernel_revision__ = "bounded-thread-release-test-v1"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("blocked", 1): blocked},
                isolation_mode="thread",
                max_thread_workers=1,
                now=clock,
            )
            outcomes = []
            errors = []

            def drive():
                try:
                    outcomes.append(stack.run_once())
                except BaseException as exc:
                    errors.append(exc)

            driver = threading.Thread(target=drive)
            try:
                first = make_command(
                    "release-1",
                    stack.registry_revision,
                    handler_id="blocked",
                    timeout=5,
                )
                second = make_command(
                    "release-2",
                    stack.registry_revision,
                    handler_id="blocked",
                    timeout=5,
                )
                stack.submit(first)
                stack.submit(second)
                driver.start()
                self.assertTrue(entered.wait(2))
                clock.advance(6)
                driver.join(2)
                self.assertFalse(driver.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(outcomes), 1)
                self.assertEqual(outcomes[0].state, "timed_out")
                self.assertFalse(finished.is_set())
                self.assertIsNone(stack.run_once())
                self.assertEqual(stack.kernel.get(second.execution_id).state, "queued")

                release.set()
                self.assertTrue(finished.wait(1))
                # The handler's final statement precedes context cleanup and
                # the executor completion callback. Drive the queued work until
                # that callback releases capacity, within a bounded real wait.
                wait_deadline = time.monotonic() + 2
                recovered = None
                while recovered is None and time.monotonic() < wait_deadline:
                    recovered = stack.run_once()
                    if recovered is None:
                        time.sleep(.01)
                self.assertIsNotNone(recovered)
                self.assertEqual(recovered.state, "succeeded")
            finally:
                release.set()
                if driver.ident is not None:
                    driver.join(2)
                stack.close()


if __name__ == "__main__":
    unittest.main()
