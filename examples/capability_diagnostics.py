"""A deployment preflight and read-only reports over an explicitly cancelled task."""
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatcher_sdk import runtime_identity
from dispatcher_sdk.orchestrator import Operations, Orchestrator


def echo(payload, context):
    return payload


echo.__execution_kernel_revision__ = "diagnostic-example-v1"


def main():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        with Orchestrator.open_sqlite(root / "run.db", {"echo": echo}, isolation_mode="thread",
                cancellation_journal_path=str(root / "cancel.db"), source_id="diagnostic-example") as sdk:
            sdk.create_run("run", command_id="create")
            sdk.submit_task("run", "task", request_id="submit", expected_revision=0,
                handler_id="echo", payload={"value": 1}, timeout_seconds=5)
            sdk.flush()
            identity = runtime_identity(root / "run.db", handlers={"echo": echo})
            assert identity.storages[0].resume.status == "supported"
            assert sdk.inspect_work_availability("run").claimable_now == 1
            sdk.apply_operations("run", command_id="cancel", expected_revision=sdk.get_run("run")["revision"],
                                 operations=[Operations.cancel("task", reason="example complete")])
            sdk.flush()
            cancelled = sdk.inspect_cancellation("run")
            entry = cancelled.executions[0]
            assert entry.command_delivered.status == "confirmed"
            assert entry.execution_state == "cancelled"
            assert entry.local_process_tree_reaped.status == "not_applicable"
            assert cancelled.run_state == "running"
            print("Task cancelled; Run remains running until an explicit application decision.")


if __name__ == "__main__":
    main()
