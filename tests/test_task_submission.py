"""Task submission identity, durable replay, and operation atomicity."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import RetryPolicy, Runtime
from dispatcher_sdk.orchestrator import CommandConflict, OrchestrationError, Orchestrator
from dispatcher_sdk.orchestrator.convenience import ConvenienceMixin, _submission_ids


def echo(payload, context):
    return payload


def changed(payload, context):
    raise AssertionError("replay must not execute this handler")


class SubmissionOrchestrator(Orchestrator):
    # Keep the isolated mixin tests runnable before the public class is wired.
    submit_task = ConvenienceMixin.submit_task


class TaskSubmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "state.db"
        self.runtime = Runtime(self.path, {"echo": echo}, isolation_mode="thread")
        self.addCleanup(self.runtime.close)
        self.sdk = SubmissionOrchestrator(self.path, self.runtime.kernel, runtime=self.runtime)
        self.sdk.create_run("run", command_id="create")
        self.args = dict(request_id="request", expected_revision=0, handler_id="echo",
                         payload={"value": 1}, timeout_seconds=5)

    def submit(self, **changes):
        return self.sdk.submit_task("run", "task", **{**self.args, **changes})

    def count(self, table):
        connection = sqlite3.connect(self.path)
        try:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            connection.close()

    def test_submission_uses_handler_binding_one_attempt_and_keeps_run_running(self):
        response = self.submit(watch_target="conversation")
        attempt = response["tasks"]["task"]["attempts"][0]
        self.assertEqual(response["revision"], 1)
        self.assertEqual(response["state"], "running")
        self.assertEqual(attempt["state"], "pending_dispatch")
        self.assertTrue(attempt["command"]["registry_revision"].startswith("handler-v1:"))
        self.assertEqual(attempt["command"]["retry_policy"]["max_attempts"], 1)
        self.assertEqual(self.count("sdk_watches"), 1)
        self.assertEqual(self.count("sdk_outbox"), 1)
        self.assertEqual(self.count("kernel_executions"), 0)
        self.sdk.flush()
        self.runtime.run_once()
        self.sdk.sync()
        current = self.sdk.get_run("run")
        self.assertEqual(current["tasks"]["task"]["attempts"][0]["state"], "succeeded")
        self.assertEqual(current["state"], "running")

    def test_same_request_concurrently_commits_one_receipt_and_dispatch(self):
        barrier = threading.Barrier(4)

        def submit(_):
            barrier.wait(timeout=5)
            return self.submit(watch_target={"conversation": "same"})

        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(submit, range(4)))
        self.assertTrue(all(receipt == receipts[0] for receipt in receipts))
        self.assertEqual(self.count("sdk_executions"), 1)
        self.assertEqual(self.count("sdk_outbox"), 1)
        self.assertEqual(self.count("sdk_watches"), 1)
        self.assertEqual(self.count("sdk_commands"), 2)  # create + submission
        self.sdk.flush()
        self.sdk.flush()
        self.assertEqual(self.count("kernel_executions"), 1)

    def test_response_loss_replay_after_restart_returns_original_snapshot(self):
        original = self.submit()
        self.sdk.apply_operations("run", command_id="later", expected_revision=1,
                                  operations=[{"kind": "wait", "wait_id": "review"}])
        self.runtime.close()
        with Runtime(self.path, {"echo": echo}, isolation_mode="thread") as runtime:
            reopened = SubmissionOrchestrator(self.path, runtime.kernel, runtime=runtime)
            replay = reopened.submit_task("run", "task", **self.args)
            self.assertEqual(replay, original)
            self.assertEqual(replay["revision"], 1)
            self.assertEqual(reopened.get_run_summary("run")["revision"], 2)
        self.assertEqual(self.count("sdk_outbox"), 1)

    def test_changed_request_fields_conflict_even_after_commit(self):
        self.submit()
        changes = (
            {"payload": {"value": 2}}, {"timeout_seconds": 6},
            {"handler_id": "different"}, {"handler_contract_version": 2},
            {"expected_revision": 1}, {"dependencies": []},
            {"watch_target": "conversation"}, {"dispatch": False},
            {"retry_policy": RetryPolicy(max_attempts=2)},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(CommandConflict):
                self.submit(**change)
        self.assertEqual(self.count("sdk_outbox"), 1)

    def test_replay_retains_binding_across_unrelated_and_target_handler_upgrades(self):
        original = self.submit()
        self.runtime.close()
        for handlers in ({"echo": echo, "new": changed}, {"echo": changed}, {}):
            with self.subTest(handlers=list(handlers)):
                with Runtime(self.path, handlers, isolation_mode="thread") as runtime:
                    reopened = SubmissionOrchestrator(self.path, runtime.kernel, runtime=runtime)
                    with patch.object(runtime, "command", side_effect=AssertionError("must use receipt binding")):
                        self.assertEqual(reopened.submit_task("run", "task", **self.args), original)
                        with self.assertRaises(CommandConflict):
                            reopened.submit_task("run", "task", **{**self.args, "payload": 2})
        self.assertEqual(self.count("kernel_executions"), 0)

    def test_replay_without_runtime_succeeds_but_new_request_requires_runtime(self):
        original = self.submit()
        without_runtime = SubmissionOrchestrator(self.path, self.runtime.kernel)
        self.assertEqual(without_runtime.submit_task("run", "task", **self.args), original)
        with self.assertRaisesRegex(OrchestrationError, "requires a Runtime"):
            without_runtime.submit_task("run", "another", **{**self.args, "request_id": "new"})

    def test_foreign_receipt_is_an_explicit_command_conflict(self):
        identities = _submission_ids("run", "task", "request")
        self.sdk.apply_operations("run", command_id=identities["command"],
                                  expected_revision=0, operations=[])
        with self.assertRaisesRegex(CommandConflict, "another command"):
            self.submit()

    def test_watch_and_dispatch_are_rolled_back_with_failed_commit(self):
        def fail(name):
            if name == "before_commit":
                raise RuntimeError("injected commit failure")

        self.sdk._failpoint = fail
        with self.assertRaisesRegex(RuntimeError, "injected"):
            self.submit(watch_target="conversation")
        self.sdk._failpoint = lambda name: None
        for table in ("sdk_watches", "sdk_executions", "sdk_outbox"):
            self.assertEqual(self.count(table), 0)
        self.assertEqual(self.sdk.get_run("run")["tasks"], {})
        self.assertEqual(self.count("sdk_commands"), 1)
        self.submit(watch_target="conversation")

    def test_failed_dispatch_rolls_back_its_already_registered_watch(self):
        self.sdk.submit_task("run", "dependency", **{**self.args, "request_id": "dependency", "dispatch": False})
        with self.assertRaisesRegex(OrchestrationError, "dependencies have not settled"):
            self.submit(expected_revision=1, dependencies=["dependency"], watch_target="conversation")
        self.assertEqual(self.count("sdk_watches"), 0)
        self.assertEqual(self.count("sdk_outbox"), 0)
        self.assertEqual(set(self.sdk.get_run("run")["tasks"]), {"dependency"})

    def test_omitted_watch_is_optional_and_explicit_null_is_rejected(self):
        with self.assertRaisesRegex(OrchestrationError, "target"):
            self.submit(watch_target=None)
        self.assertEqual(self.sdk.get_run("run")["tasks"], {})
        result = self.submit(dispatch=False)
        self.assertEqual(result["tasks"]["task"]["attempts"][0]["state"], "planned")
        self.assertEqual(self.count("sdk_watches"), 0)
        self.assertEqual(self.count("sdk_outbox"), 0)

    def test_request_identity_and_dispatch_flag_are_validated(self):
        for change in ({"request_id": ""}, {"request_id": None}, {"dispatch": 1}):
            with self.subTest(change=change), self.assertRaises(OrchestrationError):
                self.submit(**change)

    def test_concurrent_commit_with_an_older_binding_rebuilds_only_binding(self):
        with Runtime(self.path, {"echo": changed}, isolation_mode="thread") as upgraded:
            competing = SubmissionOrchestrator(self.path, upgraded.kernel, runtime=upgraded)
            original_apply = competing.apply_operations
            accepted = []

            def commit_first(*args, **kwargs):
                if not accepted:
                    accepted.append(self.submit())
                return original_apply(*args, **kwargs)

            with patch.object(competing, "apply_operations", side_effect=commit_first):
                replay = competing.submit_task("run", "task", **self.args)
            self.assertEqual(replay, accepted[0])
            self.assertEqual(self.count("sdk_outbox"), 1)


if __name__ == "__main__":
    unittest.main()
