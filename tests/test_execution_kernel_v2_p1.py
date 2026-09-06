from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import dispatcher_sdk.execution_kernel._sqlite_base as sqlite_base_module
from dispatcher_sdk.execution_kernel import (
    EffectClaimConflictError,
    EffectRecoveryRequiredError,
    ExecutionCommandV2,
    ExecutionError,
    ExecutionResultV2,
    HandlerEffects,
    Kernel,
    RegistryRevisionMismatchError,
    RetryPolicy,
    SQLiteKernel,
    StaleFenceError,
    StorageIsolationError,
    registry_revision,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value
        self.lock = threading.Lock()

    def __call__(self) -> float:
        with self.lock:
            return self.value

    def set(self, value: float) -> None:
        with self.lock:
            self.value = value


def make_policy(
    *,
    attempts: int = 2,
    backoff: float = 0.0,
    retry_timeouts: bool = True,
) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=attempts,
        initial_backoff_seconds=backoff,
        backoff_multiplier=1,
        max_backoff_seconds=backoff,
        retry_timeouts=retry_timeouts,
    )


def make_command(
    execution_id: str,
    *,
    registry: str = "registry-p1",
    handler_id: str = "handler",
    attempts: int = 2,
    backoff: float = 0.0,
    timeout: float = 1.0,
    payload=None,
) -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=f"key-{execution_id}",
        registry_revision=registry,
        correlation_id=f"correlation-{execution_id}",
        causation_id=None,
        handler_id=handler_id,
        handler_contract_version=1,
        retry_policy=make_policy(attempts=attempts, backoff=backoff),
        timeout_seconds=timeout,
        payload={} if payload is None else payload,
    )


def make_result(
    kernel: SQLiteKernel,
    lease,
    *,
    status: str = "succeeded",
    retryable: bool = False,
    effect_ids=None,
) -> ExecutionResultV2:
    snapshot = kernel.get(lease.execution_id)
    return ExecutionResultV2(
        result_id=f"result-{lease.execution_id}-{lease.attempt}",
        execution_id=lease.execution_id,
        status=status,
        attempt=lease.attempt,
        fence=lease.fence,
        effect_ids=[] if effect_ids is None else effect_ids,
        started_at=snapshot.started_at,
        completed_at=kernel.current_time(),
        correlation_id=snapshot.command.correlation_id,
        causation_id=snapshot.command.causation_id,
        value={"ok": True} if status == "succeeded" else None,
        error=(
            None
            if status == "succeeded"
            else ExecutionError("attempt_failed", "failed", retryable, {})
        ),
    )


def hanging_during_effect(payload, context):
    def perform():
        Path(payload["marker"]).write_text("called", encoding="utf-8")
        time.sleep(payload["sleep"])
        return {"receipt": "too-late"}

    return context.effects.execute_once(
        payload["effect_id"], "publish", {"token": payload["token"]}, perform
    )


def crashing_during_effect(payload, context):
    def perform():
        Path(payload["marker"]).write_text("called", encoding="utf-8")
        os._exit(37)

    return context.effects.execute_once(
        payload["effect_id"], "publish", {"token": payload["token"]}, perform
    )


hanging_during_effect.__execution_kernel_revision__ = "p1-effect-handlers-v2"
crashing_during_effect.__execution_kernel_revision__ = "p1-effect-handlers-v2"


def portable_handler_source(filename: str):
    namespace: dict[str, object] = {}
    source = (
        "def portable(payload, context):\n"
        "    return {'value': payload['value'], 'attempt': context.lease.attempt}\n"
    )
    exec(compile(source, filename, "exec"), namespace)
    return namespace["portable"]


def closure_handler(value):
    def handler(payload, context):
        return {"value": value}

    return handler


def default_handler(value):
    def handler(payload, context, selected=value):
        return {"value": selected}

    return handler


class StatefulHandler:
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self, payload, context):
        return {"value": self.value}


GLOBAL_HANDLER_VALUE = "global-first"


def global_value_handler(_payload, _context):
    return {"value": GLOBAL_HANDLER_VALUE}


class ClassStateHandler:
    mode = "class-first"

    def __call__(self, _payload, _context):
        return {"value": type(self).mode}


class TerminalEffectInvariantTests(unittest.TestCase):
    def _running(self, kernel: SQLiteKernel, execution_id: str):
        kernel.submit(make_command(execution_id))
        lease = kernel.claim("worker", registry_revision="registry-p1")
        self.assertIsNotNone(lease)
        return kernel.start(lease)

    def test_every_exit_path_parks_dangling_effect_without_result_or_outbox(self) -> None:
        for operation in ("success", "retry", "dead_letter", "cancel"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temp:
                kernel = SQLiteKernel(Path(temp) / "kernel.sqlite3", now=Clock())
                try:
                    lease = self._running(kernel, operation)
                    effect_id = f"effect-{operation}"
                    kernel.prepare_effect(
                        lease, effect_id=effect_id, name="publish", request={"v": 1}
                    )
                    if operation == "success":
                        parked = kernel.complete(lease, make_result(kernel, lease))
                    elif operation == "retry":
                        parked = kernel.complete(
                            lease,
                            make_result(
                                kernel, lease, status="failed", retryable=True
                            ),
                        )
                    elif operation == "dead_letter":
                        parked = kernel.dead_letter(
                            lease,
                            ExecutionError("unavailable", "permanent", False, {}),
                        )
                    else:
                        with self.assertRaises(EffectRecoveryRequiredError):
                            kernel.cancel(lease)
                        parked = kernel.get(operation)
                    self.assertEqual(parked.state, "recovery_required")
                    self.assertEqual(parked.recovery_effect_id, effect_id)
                    self.assertIsNone(parked.result)
                    self.assertEqual(kernel.get_effect(effect_id).state, "indeterminate")
                    self.assertEqual(kernel.result_outbox(), [])
                    with self.assertRaises(EffectRecoveryRequiredError):
                        kernel.cancel(operation)
                    self.assertEqual(kernel.get(operation).recovery_effect_id, effect_id)
                finally:
                    kernel.close()

    def test_concurrent_execute_once_has_exactly_one_performer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            kernel = SQLiteKernel(Path(temp) / "kernel.sqlite3", now=Clock())
            try:
                lease = self._running(kernel, "concurrent-effect")
                first_context = HandlerEffects(kernel, lease, lambda: True)
                second_context = HandlerEffects(kernel, lease, lambda: True)
                entered = threading.Event()
                release = threading.Event()
                calls: list[str] = []

                def perform():
                    calls.append("called")
                    entered.set()
                    self.assertTrue(release.wait(2))
                    return {"receipt": "one"}

                with ThreadPoolExecutor(max_workers=2) as executor:
                    winner = executor.submit(
                        first_context.execute_once,
                        "shared-effect",
                        "publish",
                        {"v": 1},
                        perform,
                    )
                    self.assertTrue(entered.wait(2))
                    loser = executor.submit(
                        second_context.execute_once,
                        "shared-effect",
                        "publish",
                        {"v": 1},
                        lambda: calls.append("duplicate"),
                    )
                    with self.assertRaises(EffectClaimConflictError):
                        loser.result(timeout=2)
                    release.set()
                    self.assertEqual(winner.result(timeout=2), {"receipt": "one"})
                self.assertEqual(calls, ["called"])
                committed = kernel.get_effect("shared-effect")
                self.assertEqual(committed.state, "committed")
                self.assertIsNotNone(committed.claim_id)
                replay = second_context.execute_once(
                    "shared-effect",
                    "publish",
                    {"v": 1},
                    lambda: calls.append("replayed"),
                )
                self.assertEqual(replay, {"receipt": "one"})
                self.assertEqual(calls, ["called"])
            finally:
                kernel.close()

    def test_effect_completion_requires_live_lease_and_exact_claim_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock()
            kernel = SQLiteKernel(Path(temp) / "kernel.sqlite3", now=clock)
            try:
                lease = self._running(kernel, "claim-fence")
                kernel.prepare_effect(
                    lease, effect_id="claimed", name="send", request={}
                )
                claimed = kernel.claim_effect(lease, "claimed")
                with self.assertRaises(EffectClaimConflictError):
                    kernel.commit_effect("claimed", {}, lease, "wrong-claim")
                clock.set(200)
                with self.assertRaises(StaleFenceError):
                    kernel.commit_effect("claimed", {}, lease, claimed.claim_id)
                parked = kernel.reap()[0]
                self.assertEqual(parked.state, "recovery_required")
                self.assertEqual(kernel.get_effect("claimed").state, "indeterminate")
            finally:
                kernel.close()

    def test_thread_timeout_parks_inflight_perform_and_blocks_late_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            entered = threading.Event()
            release = threading.Event()
            finished = threading.Event()

            def handler(payload, context):
                def perform():
                    entered.set()
                    release.wait(5)
                    return {"receipt": "late"}

                try:
                    return context.effects.execute_once(
                        "thread-inflight", "publish", {}, perform
                    )
                finally:
                    finished.set()

            handler.__execution_kernel_revision__ = "thread-inflight-v1"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("thread-inflight", 1): handler},
                isolation_mode="thread",
            )
            try:
                stack.submit(
                    make_command(
                        "thread-inflight",
                        registry=stack.registry_revision,
                        handler_id="thread-inflight",
                        timeout=2.0,
                    )
                )
                with ThreadPoolExecutor(max_workers=1) as executor:
                    running = executor.submit(stack.run_once)
                    self.assertTrue(entered.wait(5))
                    parked = running.result(timeout=5)
                self.assertEqual(parked.state, "recovery_required")
                self.assertEqual(
                    stack.kernel.get_effect("thread-inflight").state,
                    "indeterminate",
                )
                release.set()
                self.assertTrue(finished.wait(2))
                self.assertEqual(
                    stack.kernel.get_effect("thread-inflight").state,
                    "indeterminate",
                )
                self.assertEqual(stack.kernel.result_outbox(), [])
            finally:
                release.set()
                stack.close()


@unittest.skipUnless(
    os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
    "requires POSIX fork isolation",
)
class ProcessEffectRecoveryTests(unittest.TestCase):
    def _run_case(self, handler, name: str, timeout: float) -> None:
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "called.txt"
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {(name, 1): handler},
                isolation_mode="process",
                lease_seconds=2,
            )
            try:
                stack.submit(
                    make_command(
                        name,
                        registry=stack.registry_revision,
                        handler_id=name,
                        timeout=timeout,
                        payload={
                            "effect_id": f"effect-{name}",
                            "marker": str(marker),
                            "sleep": 5,
                            "token": name,
                        },
                    )
                )
                parked = stack.run_once()
                self.assertTrue(marker.exists())
                self.assertEqual(parked.state, "recovery_required")
                self.assertEqual(parked.recovery_effect_id, f"effect-{name}")
                self.assertIsNone(parked.result)
                self.assertEqual(stack.pending_recoveries()[0].execution_id, name)
                effect = stack.kernel.get_effect(f"effect-{name}")
                self.assertEqual(effect.state, "indeterminate")
                self.assertIsNotNone(effect.claim_id)
                self.assertEqual(stack.kernel.result_outbox(), [])
            finally:
                stack.close()

    def test_timeout_during_perform_parks_claim_for_recovery(self) -> None:
        self._run_case(hanging_during_effect, "perform-timeout", 2.0)

    def test_subprocess_crash_after_external_call_parks_claim_for_recovery(self) -> None:
        self._run_case(crashing_during_effect, "perform-crash", 5.0)


class RegistryFingerprintTests(unittest.TestCase):
    def test_fingerprint_is_path_portable_and_binds_all_python_state(self) -> None:
        first = portable_handler_source("/deployment/a/handler.py")
        second = portable_handler_source("/another/install/handler.py")
        self.assertEqual(registry_revision({"h": first}), registry_revision({"h": second}))
        self.assertNotEqual(
            registry_revision({"h": closure_handler("a")}),
            registry_revision({"h": closure_handler("b")}),
        )
        self.assertNotEqual(
            registry_revision({"h": default_handler("a")}),
            registry_revision({"h": default_handler("b")}),
        )
        self.assertNotEqual(
            registry_revision({"h": StatefulHandler("a")}),
            registry_revision({"h": StatefulHandler("b")}),
        )

    def test_opaque_state_requires_explicit_deployment_revision(self) -> None:
        lock = threading.Lock()

        def handler(payload, context):
            return {"locked": lock.locked()}

        with self.assertRaises(TypeError):
            registry_revision({"h": handler})
        handler.__execution_kernel_revision__ = "client-library-v1"
        first = registry_revision({"h": handler})
        handler.__execution_kernel_revision__ = "client-library-v2"
        self.assertNotEqual(first, registry_revision({"h": handler}))

    def test_queued_command_restarts_under_same_source_from_another_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            first_handler = portable_handler_source("/first/build/handler.py")
            first = Kernel.open_sqlite(
                path, {("portable", 1): first_handler}, isolation_mode="thread"
            )
            revision = first.registry_revision
            try:
                first.submit(
                    make_command(
                        "portable-restart",
                        registry=revision,
                        handler_id="portable",
                        payload={"value": "durable"},
                    )
                )
            finally:
                first.close()
            second_handler = portable_handler_source("/second/build/handler.py")
            second = Kernel.open_sqlite(
                path, {("portable", 1): second_handler}, isolation_mode="thread"
            )
            try:
                self.assertEqual(second.registry_revision, revision)
                terminal = second.run_once()
                self.assertEqual(terminal.result.value["value"], "durable")
            finally:
                second.close()

    def test_runtime_rejects_mutated_handler_state_before_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            handler = StatefulHandler("first")
            stack = Kernel.open_sqlite(
                Path(temp) / "kernel.sqlite3",
                {("stateful", 1): handler},
                isolation_mode="thread",
            )
            try:
                stack.submit(
                    make_command(
                        "state-change",
                        registry=stack.registry_revision,
                        handler_id="stateful",
                    )
                )
                handler.value = "changed"
                with self.assertRaises(RegistryRevisionMismatchError):
                    stack.run_once()
                self.assertEqual(stack.kernel.get("state-change").state, "queued")
            finally:
                stack.close()

    def test_runtime_rejects_mutated_referenced_global_before_claim(self) -> None:
        global GLOBAL_HANDLER_VALUE
        original = GLOBAL_HANDLER_VALUE
        try:
            with tempfile.TemporaryDirectory() as temp:
                stack = Kernel.open_sqlite(
                    Path(temp) / "kernel.sqlite3",
                    {("global", 1): global_value_handler},
                    isolation_mode="thread",
                )
                try:
                    stack.submit(
                        make_command(
                            "global-change",
                            registry=stack.registry_revision,
                            handler_id="global",
                        )
                    )
                    GLOBAL_HANDLER_VALUE = "global-second"
                    with self.assertRaises(RegistryRevisionMismatchError):
                        stack.run_once()
                    self.assertEqual(stack.kernel.get("global-change").state, "queued")
                finally:
                    stack.close()
        finally:
            GLOBAL_HANDLER_VALUE = original

    def test_runtime_rejects_mutated_referenced_class_state_before_claim(self) -> None:
        original = ClassStateHandler.mode
        try:
            with tempfile.TemporaryDirectory() as temp:
                handler = ClassStateHandler()
                stack = Kernel.open_sqlite(
                    Path(temp) / "kernel.sqlite3",
                    {("class-state", 1): handler},
                    isolation_mode="thread",
                )
                try:
                    stack.submit(
                        make_command(
                            "class-change",
                            registry=stack.registry_revision,
                            handler_id="class-state",
                        )
                    )
                    ClassStateHandler.mode = "class-second"
                    with self.assertRaises(RegistryRevisionMismatchError):
                        stack.run_once()
                    self.assertEqual(stack.kernel.get("class-change").state, "queued")
                finally:
                    stack.close()
        finally:
            ClassStateHandler.mode = original


class EventAndClockTests(unittest.TestCase):
    def test_global_event_pagination_and_pending_recovery_survive_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            clock = Clock()
            kernel = SQLiteKernel(path, now=clock)
            kernel.submit(make_command("plain-a"))
            kernel.submit(make_command("plain-b"))
            kernel.cancel("plain-b")
            kernel.submit(make_command("unknown-recovery"))
            lease = kernel.start(
                kernel.claim("worker", registry_revision="registry-p1")
            )
            self.assertEqual(lease.execution_id, "plain-a")
            kernel.complete(lease, make_result(kernel, lease))
            recovery_lease = kernel.start(
                kernel.claim("worker", registry_revision="registry-p1")
            )
            self.assertEqual(recovery_lease.execution_id, "unknown-recovery")
            kernel.prepare_effect(
                recovery_lease,
                effect_id="unknown-effect",
                name="publish",
                request={},
            )
            parked = kernel.complete(
                recovery_lease, make_result(kernel, recovery_lease)
            )
            self.assertEqual(parked.state, "recovery_required")
            all_events = []
            cursor = 0
            while True:
                page = kernel.events_since(cursor, 2)
                if not page:
                    break
                self.assertEqual(page, kernel.events_since(cursor, 2))
                all_events.extend(page)
                cursor = page[-1].sequence
            self.assertEqual(
                [event.sequence for event in all_events],
                list(range(1, len(all_events) + 1)),
            )
            kernel.close()

            restarted = SQLiteKernel(path, now=clock)
            try:
                self.assertEqual(
                    [item.execution_id for item in restarted.pending_recoveries()],
                    ["unknown-recovery"],
                )
                self.assertEqual(
                    [event.to_dict() for event in restarted.events_since(0, 100)],
                    [event.to_dict() for event in all_events],
                )
                restarted.submit(make_command("after-restart"))
                self.assertEqual(
                    restarted.events_since(cursor, 1)[0].sequence,
                    cursor + 1,
                )
            finally:
                restarted.close()

    def test_persisted_watermark_prevents_wall_clock_rollback_reactivation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clock = Clock(100)
            kernel = SQLiteKernel(
                Path(temp) / "kernel.sqlite3", now=clock, default_lease_seconds=5
            )
            try:
                kernel.submit(make_command("rollback", attempts=2))
                lease = kernel.claim("worker", registry_revision="registry-p1")
                clock.set(110)
                with self.assertRaises(StaleFenceError):
                    kernel.verify(lease)
                clock.set(90)
                kernel.close()
                kernel = SQLiteKernel(
                    Path(temp) / "kernel.sqlite3",
                    now=clock,
                    default_lease_seconds=5,
                )
                self.assertEqual(kernel.current_time(), 110)
                with self.assertRaises(StaleFenceError):
                    kernel.verify(lease)
                self.assertEqual(kernel.reap()[0].state, "queued")
            finally:
                kernel.close()

    def test_lease_clock_is_sampled_after_waiting_for_write_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            kernel = SQLiteKernel(path)
            blocker = sqlite3.connect(path, isolation_level=None)
            try:
                kernel.submit(make_command("lock-wait"))
                blocker.execute("BEGIN IMMEDIATE")
                started = threading.Event()

                def claim():
                    started.set()
                    return kernel.claim(
                        "worker", lease_seconds=0.1, registry_revision="registry-p1"
                    )

                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(claim)
                    self.assertTrue(started.wait(1))
                    time.sleep(0.2)
                    released_at = time.time()
                    blocker.commit()
                    lease = future.result(timeout=2)
                self.assertGreater(lease.expires_at, released_at)
                self.assertEqual(kernel.verify(lease).state, "leased")
            finally:
                try:
                    blocker.rollback()
                except sqlite3.Error:
                    pass
                blocker.close()
                kernel.close()

    def test_finite_addition_overflow_fails_without_partial_transition(self) -> None:
        with self.subTest(path="lease"), tempfile.TemporaryDirectory() as temp:
            kernel = SQLiteKernel(Path(temp) / "lease.sqlite3", now=Clock(1e308))
            try:
                kernel.submit(make_command("lease-overflow"))
                with self.assertRaises(ValueError):
                    kernel.claim(
                        "worker", lease_seconds=1e308, registry_revision="registry-p1"
                    )
                self.assertEqual(kernel.get("lease-overflow").state, "queued")
            finally:
                kernel.close()

        with self.subTest(path="retry"), tempfile.TemporaryDirectory() as temp:
            clock = Clock(1e307)
            kernel = SQLiteKernel(Path(temp) / "retry.sqlite3", now=clock)
            try:
                kernel.submit(
                    make_command("retry-overflow", attempts=2, backoff=1e308)
                )
                lease = kernel.start(
                    kernel.claim(
                        "worker", lease_seconds=1e308, registry_revision="registry-p1"
                    )
                )
                clock.set(1e308)
                with self.assertRaises(ValueError):
                    kernel.complete(
                        lease,
                        make_result(kernel, lease, status="failed", retryable=True),
                    )
                self.assertEqual(kernel.get("retry-overflow").state, "running")
            finally:
                kernel.close()

        with self.subTest(path="outbox"), tempfile.TemporaryDirectory() as temp:
            clock = Clock(1e307)
            kernel = SQLiteKernel(Path(temp) / "outbox.sqlite3", now=clock)
            try:
                kernel.submit(make_command("outbox-overflow"))
                lease = kernel.start(
                    kernel.claim(
                        "worker", lease_seconds=1e308, registry_revision="registry-p1"
                    )
                )
                clock.set(1e308)
                kernel.complete(lease, make_result(kernel, lease))
                with self.assertRaises(ValueError):
                    kernel.claim_outbox("bridge", lease_seconds=1e308)
                self.assertEqual(kernel.result_outbox()[0]["state"], "pending")
                delivery = kernel.claim_outbox("bridge", lease_seconds=1e307)
                with self.assertRaises(ValueError):
                    kernel.release_outbox(
                        delivery,
                        ExecutionError("bridge_retry", "retry", True, {}),
                        delay_seconds=1e308,
                    )
                self.assertEqual(
                    kernel.result_outbox(states={"delivering"})[0]["state"],
                    "delivering",
                )
            finally:
                kernel.close()


class SchemaAndAuthorizerTests(unittest.TestCase):
    def test_authorizer_denies_temp_shadow_ddl_schema_writes_and_pragmas(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            kernel = SQLiteKernel(Path(temp) / "kernel.sqlite3")
            try:
                statements = (
                    "CREATE TEMP TABLE kernel_executions (id INTEGER)",
                    "DROP TABLE kernel_clock",
                    "DROP INDEX kernel_executions_claim",
                    "ALTER TABLE kernel_clock ADD COLUMN weakened INTEGER",
                    "REINDEX kernel_executions_claim",
                    "PRAGMA writable_schema = ON",
                    "ATTACH DATABASE ':memory:' AS extra",
                    "UPDATE sqlite_schema SET sql = NULL WHERE name = 'kernel_clock'",
                    "UPDATE kernel_events SET event_type = 'tampered'",
                    "DELETE FROM kernel_events",
                )
                for statement in statements:
                    with self.subTest(statement=statement):
                        with self.assertRaises(sqlite3.DatabaseError):
                            kernel._connection.execute(statement)
                self.assertEqual(kernel.submit(make_command("still-safe")).state, "queued")
            finally:
                kernel.close()

    def test_constructor_turns_off_a_pre_enabled_writable_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "kernel.sqlite3"
            real_connect = sqlite3.connect
            connection = real_connect(
                path, timeout=30, isolation_level=None, check_same_thread=False
            )
            connection.execute("PRAGMA writable_schema = ON")
            with patch.object(
                sqlite_base_module.sqlite3, "connect", return_value=connection
            ):
                kernel = SQLiteKernel(path)
            try:
                # Python 3.10 cannot disable an authorizer with None.
                # Permit this inspection only; the separate denial test keeps
                # checking the production authorizer's restrictions.
                kernel._connection.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
                self.assertEqual(
                    kernel._connection.execute("PRAGMA writable_schema").fetchone()[0], 0
                )
            finally:
                kernel.close()

    @staticmethod
    def _rewrite_schema(path: Path, table: str, old: str, new: str) -> None:
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA writable_schema = ON")
            original = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()[0]
            changed = original.replace(old, new)
            if changed == original:
                raise AssertionError(f"schema fragment not found: {old!r}")
            connection.execute(
                "UPDATE sqlite_master SET sql = ? WHERE type = 'table' AND name = ?",
                (changed, table),
            )
            connection.execute("PRAGMA schema_version = 99")
            connection.commit()
        finally:
            connection.close()

    def test_same_columns_with_weakened_check_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "weakened.sqlite3"
            kernel = SQLiteKernel(path)
            kernel.close()
            self._rewrite_schema(
                path,
                "kernel_executions",
                "CHECK (length(trim(execution_id)) > 0),",
                "CHECK (1),",
            )
            with self.assertRaises(StorageIsolationError):
                SQLiteKernel(path)

    def test_changed_column_type_and_missing_unique_index_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            typed = Path(temp) / "typed.sqlite3"
            kernel = SQLiteKernel(typed)
            kernel.close()
            self._rewrite_schema(
                typed,
                "kernel_executions",
                "redelivery_count INTEGER NOT NULL",
                "redelivery_count TEXT NOT NULL",
            )
            with self.assertRaises(StorageIsolationError):
                SQLiteKernel(typed)

            indexed = Path(temp) / "indexed.sqlite3"
            kernel = SQLiteKernel(indexed)
            kernel.close()
            connection = sqlite3.connect(indexed)
            connection.execute("DROP INDEX kernel_executions_idempotency")
            connection.commit()
            connection.close()
            with self.assertRaises(StorageIsolationError):
                SQLiteKernel(indexed)

    def test_clock_metadata_row_is_strict(self) -> None:
        for column, value in (
            ("watermark", float("inf")),
            ("event_sequence", -1),
            ("event_sequence", 1),
        ):
            with self.subTest(column=column, value=value), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "clock.sqlite3"
                kernel = SQLiteKernel(path)
                kernel.close()
                connection = sqlite3.connect(path)
                connection.execute("PRAGMA ignore_check_constraints = ON")
                connection.execute(
                    f"UPDATE kernel_clock SET {column} = ? WHERE singleton = 1",
                    (value,),
                )
                connection.commit()
                connection.close()
                with self.assertRaises(StorageIsolationError):
                    SQLiteKernel(path)


if __name__ == "__main__":
    unittest.main()
