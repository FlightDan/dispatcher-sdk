from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.orchestrator import Orchestrator


class Clock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


def echo(payload, context):
    return payload


def mutate_file(payload, context):
    def perform():
        with open(payload["marker"], "a", encoding="utf-8") as marker:
            marker.write("mutation\n")
            marker.flush()
            os.fsync(marker.fileno())
        if payload["crash_window"] == "before_commit":
            os._exit(37)
        return {"receipt": payload["operation_id"], "content": "mutation\n"}

    response = context.effects.execute_once(
        payload["effect_id"], "append-file", payload, perform
    )
    if payload["crash_window"] == "after_commit" and context.lease.attempt == 1:
        os._exit(38)
    return response


# The same deployment and handler code is used before and after every restart.
echo.__execution_kernel_revision__ = "sdk-recovery-echo-v1"
mutate_file.__execution_kernel_revision__ = "sdk-recovery-file-v1"
HANDLERS = {"echo": echo, "mutate": mutate_file}


def run_worker(path, now):
    # Both the initial execution and replay run here. An erroneous replay of
    # perform must fail the child exit-code assertion, never exit the test runner.
    runtime = Kernel.open_sqlite(
        path, HANDLERS, now=Clock(now), lease_seconds=2, isolation_mode="thread"
    )
    try:
        runtime.run_once()
    finally:
        runtime.close()


class SDKRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "recovery.sqlite3"
        self.marker = Path(temporary.name) / "mutation.txt"
        self.clock = Clock()
        self.open_stack()

    def open_stack(self):
        self.runtime = Kernel.open_sqlite(
            self.path, HANDLERS, now=self.clock, lease_seconds=2, isolation_mode="thread"
        )
        self.addCleanup(self.runtime.close)
        self.sdk = Orchestrator(
            self.path, self.runtime.kernel, runtime=self.runtime, clock=self.clock
        )

    def restart(self):
        revision = self.runtime.registry_revision
        self.runtime.close()
        self.open_stack()
        self.assertEqual(self.runtime.registry_revision, revision)

    def register(self, *, handler="echo", attempts=2, backoff=7, payload=None):
        self.command = ExecutionCommandV2(
            execution_id="execution", idempotency_key="original-key",
            registry_revision=self.runtime.registry_revision, correlation_id="run",
            causation_id=None, handler_id=handler, handler_contract_version=1,
            retry_policy=RetryPolicy(
                max_attempts=attempts, initial_backoff_seconds=backoff,
                backoff_multiplier=1, max_backoff_seconds=backoff,
            ),
            timeout_seconds=20, payload={"input": "frozen"} if payload is None else payload,
        )
        self.original_command = self.command.to_dict()
        self.sdk.create_run("run", command_id="create")
        self.sdk.apply_operations(
            "run", command_id="dispatch", expected_revision=0,
            application_state={"business_repairs_used": 0},
            operations=[
                {"kind": "add_task", "task_id": "task", "command": self.original_command},
                {"kind": "dispatch", "task_id": "task"},
            ],
        )
        self.assertEqual(self.sdk.flush(), 1)

    def assert_business_unchanged(self):
        state = self.sdk.get_run("run")
        self.assertEqual(state["state"], "running")
        self.assertEqual(state["application_state"], {"business_repairs_used": 0})
        attempts = state["tasks"]["task"]["attempts"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["command"], self.original_command)
        self.assertEqual(self.sdk.inspect_execution("execution").command.to_dict(),
                         self.original_command)

    def child_worker(self, expected_exit):
        process = multiprocessing.get_context("spawn").Process(
            target=run_worker, args=(str(self.path), self.clock.value)
        )
        process.start()
        try:
            process.join(15)
            self.assertFalse(process.is_alive(), "recovery worker exceeded its deadline")
            self.assertEqual(process.exitcode, expected_exit)
        finally:
            if process.is_alive():
                process.kill()
                process.join(5)
            process.close()

    def test_restart_waits_for_persisted_lease_then_backoff_without_business_retry(self):
        self.register()
        lease = self.runtime.kernel.claim_and_start(
            "lost-worker", registry_revision=self.runtime.registry_revision
        )
        self.sdk.sync()
        before = self.sdk.inspect_execution("execution")
        self.assertGreater(lease.expires_at, self.clock.value + self.runtime.lease_seconds)
        self.clock.value = lease.expires_at - 0.25
        self.restart()
        for _ in range(3):
            self.assertEqual(self.runtime.reap(), [])
            self.assertEqual(self.sdk.flush(), 0)
            self.assertIsNone(self.runtime.run_once())
            self.sdk.sync()
            self.assertEqual(self.sdk.inspect_execution("execution"), before)
            self.assert_business_unchanged()

        self.clock.value = lease.expires_at
        self.assertEqual(len(self.runtime.reap()), 1)
        queued = self.sdk.inspect_execution("execution")
        self.assertEqual(queued.state, "queued")
        self.assertEqual(queued.attempt, 1)
        self.assertEqual(queued.redelivery_count, 1)
        self.assertEqual(queued.next_attempt_at, self.clock.value + 7)
        self.clock.value = queued.next_attempt_at - 0.25
        self.restart()
        for _ in range(3):
            self.assertIsNone(self.runtime.run_once())
            self.sdk.sync()
            self.assertEqual(self.sdk.inspect_execution("execution"), queued)
            self.assert_business_unchanged()
        self.clock.value = queued.next_attempt_at
        terminal = self.runtime.run_once()
        self.sdk.sync()
        self.assertEqual(terminal.state, "succeeded")
        self.assertEqual(terminal.attempt, 2)
        self.assertGreater(terminal.fence, lease.fence)
        self.assertEqual(terminal.result.value, self.original_command["payload"])
        self.assertEqual(len(self.runtime.kernel.result_outbox()), 1)
        self.assert_business_unchanged()

    def effect_crash(self, window, attempts):
        self.register(handler="mutate", attempts=attempts, backoff=0, payload={
            "marker": str(self.marker), "effect_id": "file-effect",
            "operation_id": "original-operation", "crash_window": window,
        })
        self.runtime.close()
        self.child_worker(37 if window == "before_commit" else 38)
        self.open_stack()
        running = self.sdk.inspect_execution("execution")
        self.assertEqual(running.state, "running")
        self.assertEqual(running.attempt, 1)
        self.assertIsNone(running.result)
        self.assertEqual(self.marker.read_text(encoding="utf-8"), "mutation\n")
        self.assertEqual(self.runtime.kernel.result_outbox(), [])
        return running

    def assert_effect_replay(self, running):
        self.runtime.close()
        self.child_worker(0)
        self.open_stack()
        self.sdk.sync()
        terminal = self.sdk.inspect_execution("execution")
        self.assertEqual(terminal.state, "succeeded")
        self.assertEqual(terminal.attempt, 2)
        self.assertGreater(terminal.fence, running.fence)
        self.assertEqual(terminal.result.value,
                         {"receipt": "original-operation", "content": "mutation\n"})
        self.assertEqual(terminal.result.effect_ids, ["file-effect"])
        self.assertEqual(self.marker.read_text(encoding="utf-8"), "mutation\n")
        self.assertEqual(len(self.runtime.kernel.result_outbox()), 1)
        self.assert_business_unchanged()

    def test_crash_after_mutation_requires_explicit_applied_resolution_at_one_attempt(self):
        running = self.effect_crash("before_commit", 1)
        self.assertEqual(self.runtime.kernel.get_effect("file-effect").state, "performing")
        self.clock.value = running.lease.expires_at
        self.runtime.reap()
        self.sdk.sync()
        parked = self.sdk.inspect_execution("execution")
        self.assertEqual(parked.state, "recovery_required")
        self.assertEqual(parked.recovery_effect_id, "file-effect")
        self.assertIsNone(parked.result)
        self.assertEqual(self.runtime.kernel.result_outbox(), [])
        self.assert_business_unchanged()
        self.restart()
        effect = self.runtime.kernel.get_effect("file-effect")
        self.assertEqual(effect.state, "indeterminate")
        self.assertEqual(self.runtime.pending_recoveries()[0].execution_id, "execution")
        response = {"receipt": "original-operation", "content": self.marker.read_text()}
        resolved = self.sdk.resolve_effect(
            "file-effect", decision="applied", response=response,
            expected_revision=effect.revision, recovery_id="reconciled-file",
        )
        self.assertEqual(resolved.state, "committed")
        self.assertEqual(self.sdk.inspect_execution("execution").state, "queued")
        self.assert_effect_replay(running)

    def test_committed_effect_survives_crash_before_result_and_reuses_response(self):
        running = self.effect_crash("after_commit", 2)
        self.assertEqual(self.runtime.kernel.get_effect("file-effect").state, "committed")
        self.clock.value = running.lease.expires_at
        self.runtime.reap()
        self.sdk.sync()
        self.assertEqual(self.sdk.inspect_execution("execution").state, "queued")
        self.assertEqual(self.runtime.pending_recoveries(), [])
        self.assert_effect_replay(running)


if __name__ == "__main__":
    unittest.main()
