from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import (
    ExecutionCommandV2, ExecutionNotFoundError, IdempotencyConflictError,
    Kernel, RetryPolicy, SQLiteKernel,
)
from dispatcher_sdk.orchestrator import Orchestrator


def echo(payload, context):
    return payload


class KernelCancelBeforeAcceptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "kernel.db"
        self.runtime = Kernel.open_sqlite(self.path, {"echo": echo}, isolation_mode="thread")
        self.addCleanup(self.runtime.close)
        self.kernel = self.runtime.kernel
        self.command = ExecutionCommandV2(
            execution_id="task", idempotency_key="task-key",
            registry_revision=self.runtime.registry_revision,
            correlation_id="run", causation_id=None, handler_id="echo", handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=5, payload={"value": 1},
        )

    def test_new_command_cancels_with_normal_events_result_and_durable_idempotency(self):
        result = self.kernel.cancel_before_accept(self.command, reason="stop before acceptance")
        self.assertEqual(result.state, "cancelled")
        self.assertEqual((result.attempt, result.fence), (0, 0))
        self.assertEqual(result.result.error.message, "stop before acceptance")
        self.assertEqual([event.event_type for event in self.kernel.events_since(0)],
                         ["submitted", "cancelled"])
        self.assertEqual(len(self.kernel.outbox()), 1)
        self.assertEqual(self.kernel.outbox()[0]["result_id"], result.result.result_id)
        with SQLiteKernel(self.path) as reopened:
            self.assertEqual(reopened.cancel_before_accept(self.command), result)
            self.assertEqual(reopened.submit(self.command), result)
            self.assertEqual(len(reopened.events_since(0)), 2)
            self.assertEqual(len(reopened.outbox()), 1)
        self.assertIsNone(self.runtime.run_once())

    def test_identity_conflicts_never_change_existing_command(self):
        before = self.kernel.submit(self.command)
        conflicts = (
            replace(self.command, payload={"value": True}),
            replace(self.command, execution_id="different"),
            replace(self.command, idempotency_key="different"),
        )
        for command in conflicts:
            with self.subTest(command=command), self.assertRaises(IdempotencyConflictError):
                self.kernel.cancel_before_accept(command)
            self.assertEqual(self.kernel.get("task"), before)
        self.assertEqual(self.kernel.outbox(), [])

    def test_existing_running_command_is_returned_unchanged_for_runtime_cleanup(self):
        self.kernel.submit(self.command)
        self.kernel.claim_and_start("worker", registry_revision=self.runtime.registry_revision)
        before = self.kernel.get("task")
        self.assertEqual(self.kernel.cancel_before_accept(self.command), before)
        self.assertEqual(self.kernel.get("task"), before)
        self.assertEqual(self.runtime.cancel("task", expected_revision=before.revision).state,
                         "cancelled")

    def test_outbox_failure_rolls_back_submission_and_cancellation_together(self):
        with patch.object(self.kernel, "_insert_result_outbox", side_effect=RuntimeError("crash")):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                self.kernel.cancel_before_accept(self.command)
        with self.assertRaises(ExecutionNotFoundError):
            self.kernel.get("task")
        self.assertEqual(self.kernel.events_since(0), [])
        self.assertEqual(self.kernel.outbox(), [])
        self.assertEqual(self.kernel.cancel_before_accept(self.command).state, "cancelled")

    def test_independent_connection_cannot_claim_intermediate_submission(self):
        observer = SQLiteKernel(self.path)
        self.addCleanup(observer.close)
        original = self.kernel._terminal
        attempting = threading.Event()
        claims = []

        def claim():
            attempting.set()
            return observer.claim_and_start("independent-worker",
                                            registry_revision=self.runtime.registry_revision)

        with ThreadPoolExecutor(max_workers=1) as pool:
            def pause_before_terminal(*args, **kwargs):
                claims.append(pool.submit(claim))
                self.assertTrue(attempting.wait(5))
                # This connection has its own Python lock. Only the SQLite
                # transaction prevents it from claiming the intermediate row.
                with self.assertRaises(FutureTimeoutError):
                    claims[0].result(timeout=0.1)
                return original(*args, **kwargs)

            with patch.object(self.kernel, "_terminal", side_effect=pause_before_terminal):
                self.kernel.cancel_before_accept(self.command)
            self.assertIsNone(claims[0].result(timeout=5))
        self.assertEqual(observer.get("task").state, "cancelled")

    def sdk_with_failed_dispatch(self):
        sdk = Orchestrator(self.root / "sdk.db", self.kernel, runtime=self.runtime)
        sdk.create_run("run", command_id="create")
        sdk.apply_operations("run", command_id="dispatch", expected_revision=0, operations=[
            {"kind": "add_task", "task_id": "task", "command": self.command.to_dict()},
            {"kind": "dispatch", "task_id": "task"},
        ])
        with patch.object(self.runtime, "submit", side_effect=RuntimeError("temporarily unavailable")):
            self.assertEqual(sdk.flush(limit=1), 0)
        sdk.apply_operations("run", command_id="cancel", expected_revision=sdk.get_run("run")["revision"],
                             operations=[{"kind": "cancel", "task_id": "task", "reason": "stop"}])
        return sdk

    def test_sdk_cancel_cannot_start_previously_unaccepted_valid_handler(self):
        sdk = self.sdk_with_failed_dispatch()
        original = self.kernel.cancel_before_accept
        worker_results = []

        def attempt_after_accept(*args, **kwargs):
            snapshot = original(*args, **kwargs)
            worker_results.append(self.runtime.run_once())
            return snapshot

        with patch.object(self.kernel, "cancel_before_accept", side_effect=attempt_after_accept):
            self.assertEqual(sdk.flush(limit=1), 1)
        self.assertEqual(worker_results, [None])
        cancelled = self.kernel.get("task")
        self.assertEqual(cancelled.state, "cancelled")
        self.assertEqual(sdk.flush(), 1)  # Late dispatch observes the terminal identity.
        self.assertEqual(self.kernel.get("task"), cancelled)
        self.assertTrue(all(item["state"] == "delivered" for item in sdk.delivery_messages()))

    def test_sdk_racing_existing_execution_still_uses_runtime_cancel(self):
        sdk = self.sdk_with_failed_dispatch()
        original = self.kernel.cancel_before_accept

        def dispatch_wins(*args, **kwargs):
            self.kernel.submit(self.command)
            self.kernel.claim_and_start("worker", registry_revision=self.runtime.registry_revision)
            return original(*args, **kwargs)

        with patch.object(self.kernel, "cancel_before_accept", side_effect=dispatch_wins):
            with patch.object(self.runtime, "cancel", wraps=self.runtime.cancel) as cancel:
                self.assertEqual(sdk.flush(limit=1), 1)
                cancel.assert_called_once()
        self.assertEqual(self.kernel.get("task").state, "cancelled")

    def test_unflushed_cancel_supersedes_dispatch_before_independent_worker_can_claim(self):
        sdk = Orchestrator(self.root / "sdk.db", self.kernel, runtime=self.runtime)
        sdk.create_run("run", command_id="create")
        sdk.apply_operations("run", command_id="dispatch-then-cancel", expected_revision=0,
                             operations=[
                                 {"kind": "add_task", "task_id": "task", "command": self.command.to_dict()},
                                 {"kind": "dispatch", "task_id": "task"},
                                 {"kind": "cancel", "task_id": "task", "reason": "stop before flush"},
                             ])
        observer = SQLiteKernel(self.path)
        self.addCleanup(observer.close)
        claims = []

        def try_claim_after(operation):
            def wrapped(*args, **kwargs):
                snapshot = operation(*args, **kwargs)
                claims.append(observer.claim_and_start(
                    "independent-worker", registry_revision=self.runtime.registry_revision))
                return snapshot
            return wrapped

        with patch.object(self.runtime, "submit", side_effect=try_claim_after(self.runtime.submit)):
            with patch.object(self.kernel, "cancel_before_accept",
                              side_effect=try_claim_after(self.kernel.cancel_before_accept)):
                self.assertEqual(sdk.flush(limit=1), 1)
        self.assertEqual(claims, [None])
        self.assertEqual(self.kernel.get("task").state, "cancelled")
        self.assertEqual(sdk.flush(limit=1), 1)
        self.assertEqual(self.kernel.get("task").attempt, 0)

    def test_failed_cancel_does_not_block_an_unrelated_dispatch(self):
        sdk = self.sdk_with_failed_dispatch()
        other = replace(self.command, execution_id="other", idempotency_key="other-key")
        sdk.apply_operations("run", command_id="other", expected_revision=sdk.get_run("run")["revision"],
                             operations=[
                                 {"kind": "add_task", "task_id": "other", "command": other.to_dict()},
                                 {"kind": "dispatch", "task_id": "other"},
                             ])
        with patch.object(self.kernel, "cancel_before_accept", side_effect=RuntimeError("cancel unavailable")):
            self.assertEqual(sdk.flush(limit=1), 0)
            self.assertEqual(sdk.flush(limit=1), 1)
        self.assertEqual(self.kernel.get("other").state, "queued")
        with self.assertRaises(ExecutionNotFoundError):
            self.kernel.get("task")
        records = sdk.delivery_messages(["task"])
        self.assertEqual([record["state"] for record in records], ["failed", "failed"])


if __name__ == "__main__":
    unittest.main()
