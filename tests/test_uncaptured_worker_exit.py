"""An interrupted worker sample stays fenced across process exit and reopen."""

import multiprocessing
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel


def _arm_and_wait(path, ready):
    kernel = SQLiteKernel(path)
    owner = _KernelBudgetCapture(kernel, "worker-execution")
    token = kernel._begin_budget_sample("worker-execution", timeout_seconds=2, _owner=owner)
    ready.send(token)
    # The parent terminates this process before it captures or acknowledges a
    # clock sample. Its local owner registry disappears with the process.
    ready.recv()


class UncapturedWorkerExitTests(unittest.TestCase):
    def test_killed_sampler_leaves_guard_unknown_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "kernel.sqlite3")
            with SQLiteKernel(path) as kernel:
                command = ExecutionCommandV2("worker-execution", "worker-execution",
                    "registry", "correlation", None, "handler", 1, RetryPolicy(), 30, {})
                kernel.submit(command)
                lease = kernel.claim_and_start("host", execution_id=command.execution_id)
                kernel.prepare_execution_budget(lease)

            context = multiprocessing.get_context("spawn")
            receiver, sender = context.Pipe()
            worker = context.Process(target=_arm_and_wait, args=(path, sender))
            worker.start()
            sender.close()
            try:
                self.assertTrue(receiver.poll(10), "worker did not commit its guard")
                token = receiver.recv()
                worker.terminate()
                worker.join(10)
                self.assertFalse(worker.is_alive())
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(connection.execute(
                        "SELECT token, execution_id, reason FROM kernel_budget_samples"
                    ).fetchall(), [(token, command.execution_id, "sampling")])
                with SQLiteKernel(path) as reopened:
                    self.assertEqual(reopened.get_execution_limits(command.execution_id)["clock_unknown_reason"],
                                     "budget_clock_sample_unresolved:sampling")
                    with self.assertRaisesRegex(BudgetClockUnknownError, "sample_unresolved:sampling"):
                        reopened.admission_budget(lease)
            finally:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(10)
                receiver.close()


if __name__ == "__main__":
    unittest.main()
