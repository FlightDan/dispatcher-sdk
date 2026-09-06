"""Recover a real worker crash after a file write but before its receipt commits.

A controllable clock advances the expired lease without making the demo sleep.
Use the normal Kernel clock in an application. The child is joined before repair.
"""
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy


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
    with Kernel.open_sqlite(database, {"append": append_receipt}, now=DemoClock(clock_value),
                           isolation_mode="thread") as runtime:
        runtime.run_once()


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
            clock.value = runtime.kernel.get("invoice-1").lease.expires_at
            runtime.reap()
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
