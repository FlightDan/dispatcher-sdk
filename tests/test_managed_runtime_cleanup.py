"""A real process receipt is needed before a managed interrupt can settle."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import time
import unittest

from dispatcher_sdk.execution_kernel import Runtime
from dispatcher_sdk.orchestrator import Orchestrator


def wait_for_cancellation(payload, context):
    Path(payload["started_path"]).write_text("started")
    time.sleep(20)
    return {"unexpected": True}


wait_for_cancellation.__execution_kernel_revision__ = "managed-runtime-cleanup-test-v1"


@unittest.skipUnless(os.name == "posix", "process receipt test uses POSIX fork")
class ManagedRuntimeCleanupTests(unittest.TestCase):
    def test_interrupt_uses_bound_process_receipt_to_settle_pause(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "store.db"
            started = Path(root) / "started"
            runtime = Runtime(
                str(path), {"wait": wait_for_cancellation},
                isolation_mode="process",
                cancellation_journal_path=str(Path(root) / "cancel.db"),
                source_id="managed-test",
            )
            sdk = Orchestrator(path, runtime.kernel, runtime=runtime)
            try:
                command = runtime.command(
                    "wait", execution_id="sdk-managed:run:a",
                    idempotency_key="sdk-managed:run:a", correlation_id="run",
                    payload={"started_path": str(started)}, timeout_seconds=30,
                )
                sdk.register_managed_run(
                    "run", request_id="create", definition={},
                    task_commands=[("a", command, [])], max_claims=1,
                    deadline_at=time.time() + 60,
                )
                sdk._request_managed_control(
                    "run", request_id="resume", kind="resume",
                    expected_run_revision=0, expected_control_epoch=0,
                )
                self.assertEqual(sdk.flush(), 1)
                with ThreadPoolExecutor(max_workers=1) as workers:
                    future = workers.submit(runtime.run_once)
                    end = time.monotonic() + 10
                    while not started.exists() and time.monotonic() < end:
                        time.sleep(0.02)
                    self.assertTrue(started.exists(), "handler process did not start")
                    pause = sdk._request_managed_control(
                        "run", request_id="interrupt", kind="pause", mode="interrupt",
                        expected_run_revision=sdk.get_run("run")["revision"],
                        expected_control_epoch=1,
                    )
                    self.assertEqual(sdk.flush(), 1)
                    self.assertEqual(future.result(timeout=10).state, "cancelled")
                proof = sdk._confirm_managed_cleanup_from_runtime(
                    "run", command.execution_id, control_epoch=pause["control_epoch"],
                )
                self.assertEqual(proof["source"], "runtime.cancellation_journal")
                self.assertEqual(proof, sdk._confirm_managed_cleanup_from_runtime(
                    "run", command.execution_id, control_epoch=pause["control_epoch"],
                ))
                self.assertEqual(sdk._settle_managed_pause(
                    "run", expected_control_epoch=pause["control_epoch"],
                )["control_state"], "paused")
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
