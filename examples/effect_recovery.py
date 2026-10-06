"""Recover a real worker crash after a file write but before its receipt commits.

The child is joined before explicit repair, within the original execution budget.
An expired budget would preserve the repaired effect but forbid business replay.
"""
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from dispatcher_sdk.execution_kernel import BudgetEnvelope, ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel.budget import sample_clock


class DemoClock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


def append_receipt(payload, context):
    def perform():
        with open(payload["path"], "a", encoding="utf-8") as output:
            output.write("invoice-1\n")
            output.flush()
            os.fsync(output.fileno())
        os._exit(37)  # The mutation happened; the Effect response never committed.

    return context.effects.execute_once("invoice-write", "append-receipt", payload, perform)


append_receipt.__execution_kernel_revision__ = "example-append-receipt-v1"


def worker(database, clock_value=100.0):
    clock = DemoClock(clock_value)
    with Kernel.open_sqlite(database, {"append": append_receipt}, now=clock,
                           isolation_mode="thread") as runtime:
        returned = runtime.run_once()
        assert returned is not None, 'the original recovery execution was not dispatched'
        # A returned handler result can still need factual publication. Recover
        # that receipt without dispatching the business again or renewing its
        # five-second execution deadline. Share one API maintenance allowance.
        if returned.state == "running":
            limits = runtime.kernel.get_execution_limits("invoice-1")
            envelope = BudgetEnvelope.from_dict(limits["envelope"])
            original_deadline = envelope.deadline_monotonic(sample=sample_clock(wall_time=clock.value))
            assert original_deadline is not None, 'original execution clock is unproved'
            deadline = min(original_deadline, time.monotonic() + .5)
            reports = []
            observations = []
            published = False
            while not published and time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                reports.extend(runtime.recover_completions(timeout_seconds=min(.1, remaining)))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                observed = runtime.observe("invoice-1", timeout=remaining,
                    attempt=returned.attempt, fence=returned.fence)
                observations.append(observed)
                execution = observed.get("execution", {})
                result = observed.get("result", {})
                # Background maintenance can publish before this caller's pass.
                # Read the durable business state independently of its reports.
                published = (execution.get("state") == "succeeded"
                    and (execution.get("attempt"), execution.get("fence")) == (returned.attempt, returned.fence)
                    and result.get("status") == "succeeded")
            assert published and time.monotonic() <= deadline, (returned.to_dict(), reports, observations)
        else:
            assert returned.state == "succeeded", returned.to_dict()


def main():
    with TemporaryDirectory() as directory:
        database = str(Path(directory) / "recovery.sqlite3")
        marker = Path(directory) / "receipts.txt"
        clock = DemoClock()
        with Kernel.open_sqlite(database, {"append": append_receipt}, now=clock,
                               isolation_mode="thread") as runtime:
            runtime.submit(ExecutionCommandV2(
                execution_id="invoice-1", idempotency_key="invoice-1",
                registry_revision=runtime.registry_revision, correlation_id="invoice-1",
                causation_id=None, handler_id="append", handler_contract_version=1,
                retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=5,
                payload={"path": str(marker)},
            ))
        process = multiprocessing.get_context("spawn").Process(target=worker, args=(database,))
        process.start()
        try:
            process.join(15)
            if process.is_alive():
                raise TimeoutError("worker did not exit")
            assert process.exitcode == 37
        finally:
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        with Kernel.open_sqlite(database, {"append": append_receipt}, now=clock,
                               isolation_mode="thread") as runtime:
            crashed = runtime.kernel.get("invoice-1")
            runtime.kernel.require_effect_recovery(crashed.lease, "invoice-write")
            assert runtime.kernel.get("invoice-1").state == "recovery_required"
            print("Worker exited; execution is recovery_required")
            # This demo owns an exclusive temporary directory and the child has exited.
            # In production, establish ownership and inspect actual external state first.
            assert marker.read_text(encoding="utf-8") == "invoice-1\n"
            effect = runtime.kernel.get_effect("invoice-write")
            runtime.kernel.resolve_effect("invoice-write", decision="applied",
                response={"receipt": "invoice-1"}, expected_revision=effect.revision,
                recovery_id="verified-invoice-write")
        # Replay also runs in a child: an accidental repeat of perform would exit 37.
        resumed = multiprocessing.get_context("spawn").Process(target=worker, args=(database, clock.value))
        resumed.start()
        try:
            resumed.join(15)
            if resumed.is_alive():
                raise TimeoutError("resumed worker did not exit")
            assert resumed.exitcode == 0
        finally:
            if resumed.is_alive():
                resumed.kill()
                resumed.join()
            resumed.close()
        with Kernel.open_sqlite(database, {"append": append_receipt}, now=clock,
                               isolation_mode="thread") as runtime:
            assert runtime.kernel.get("invoice-1").state == "succeeded"
            assert marker.read_text(encoding="utf-8") == "invoice-1\n"
            print("Recovered: succeeded; receipt was written once")


if __name__ == "__main__":
    main()
