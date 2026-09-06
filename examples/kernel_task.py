"""Submit a task, close the runtime, then execute it after reopening SQLite."""
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy


def total(payload, context):
    return {"total": sum(payload["amounts"])}


def main():
    with TemporaryDirectory() as directory:
        database = Path(directory) / "tasks.sqlite3"
        with Kernel.open_sqlite(database, {"total": total}, isolation_mode="thread") as runtime:
            runtime.submit(ExecutionCommandV2(
                execution_id="invoice-1", idempotency_key="invoice-1",
                registry_revision=runtime.registry_revision,
                correlation_id="invoice-1", causation_id=None,
                handler_id="total", handler_contract_version=1,
                retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=5,
                payload={"amounts": [12, 18, 30]},
            ))
        # The command is in SQLite. Closing the runtime did not discard it.
        with Kernel.open_sqlite(database, {"total": total}, isolation_mode="thread") as runtime:
            result = runtime.run_once()
            assert result.state == "succeeded"
            assert result.result.value == {"total": 60}
            print(result.result.value)


if __name__ == "__main__":
    main()
