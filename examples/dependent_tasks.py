"""Calculate an invoice total, then explicitly dispatch a receipt task."""
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.orchestrator import Orchestrator


def calculate(payload, context):
    return {"total": sum(payload["amounts"])}


def receipt(payload, context):
    return {"receipt": f"Invoice total: {payload['total']}"}


def command(runtime, identity, handler, payload):
    return ExecutionCommandV2(
        execution_id=identity, idempotency_key=identity,
        registry_revision=runtime.registry_revision,
        correlation_id="invoice", causation_id=None,
        handler_id=handler, handler_contract_version=1,
        retry_policy=RetryPolicy(), timeout_seconds=5, payload=payload,
    ).to_dict()


def main():
    with TemporaryDirectory() as directory:
        database = Path(directory) / "invoice.sqlite3"
        with Kernel.open_sqlite(database, {"calculate": calculate, "receipt": receipt},
                               isolation_mode="thread") as runtime:
            sdk = Orchestrator(database, runtime.kernel, runtime=runtime)
            sdk.create_run("invoice", command_id="create")
            sdk.apply_operations("invoice", command_id="calculate", expected_revision=0,
                operations=[
                    {"kind": "add_task", "task_id": "calculate",
                     "command": command(runtime, "calculate-1", "calculate", {"amounts": [12, 18, 30]})},
                    {"kind": "dispatch", "task_id": "calculate"},
                ])
            sdk.flush()
            calculation = runtime.run_once()
            sdk.sync()
            assert calculation.state == "succeeded"
            state = sdk.get_run("invoice")
            assert state["state"] == "running"
            # The application checks the result and supplies the next task's input.
            sdk.apply_operations("invoice", command_id="receipt", expected_revision=state["revision"],
                operations=[
                    {"kind": "add_task", "task_id": "receipt", "dependencies": ["calculate"],
                     "command": command(runtime, "receipt-1", "receipt", calculation.result.value)},
                    {"kind": "dispatch", "task_id": "receipt"},
                ])
            sdk.flush()
            result = runtime.run_once()
            sdk.sync()
            assert result.state == "succeeded"
            assert result.result.value == {"receipt": "Invoice total: 60"}
            state = sdk.get_run("invoice")
            sdk.apply_operations("invoice", command_id="finish", expected_revision=state["revision"],
                                 operations=[{"kind": "finish", "state": "succeeded"}])
            assert sdk.get_run("invoice")["state"] == "succeeded"
            print(result.result.value["receipt"])
            sdk.close()


if __name__ == "__main__":
    main()
