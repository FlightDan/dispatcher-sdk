"""Static consumer checks; run mypy with --warn-unused-ignores, do not execute."""

from pathlib import Path
import sqlite3
from typing import Any, Mapping

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, ExecutionSnapshot
from dispatcher_sdk.execution_kernel import (
    Handler, RetryPolicy, SandboxBackend, SandboxHandler, SandboxJournal,
    SandboxObservation, SandboxSpec, sandbox_handlers,
)
from dispatcher_sdk.orchestrator import (
    DispatchOperation, Observation, Operation, Operations, Orchestrator,
    OrchestratorHost, RecoveryDetails, RunEvent, RunSnapshot, NotificationInbox,
    InboxLease, InboxRecord, InboxState,
)
from dispatcher_sdk.storage import backup_database, export_database, inspect_storage


def use_sdk(sdk: Orchestrator, command: ExecutionCommandV2) -> None:
    operations: list[Operation] = [Operations.add_task("task", command), Operations.dispatch("task")]
    snapshot: RunSnapshot = sdk.apply_operations(
        "run", command_id="dispatch", expected_revision=0, operations=operations)
    dispatches = [Operations.dispatch("task")]
    sdk.apply_operations("run", command_id="dispatch-only", expected_revision=0, operations=dispatches)
    legacy = [{"kind": "dispatch", "task_id": "task"}]
    sdk.apply_operations("run", command_id="legacy", expected_revision=0, operations=legacy)
    observed: Observation = sdk.observe("run", subscription="app")
    event: RunEvent = observed["events"][0]
    revision: int = snapshot["revision"]
    sdk.acknowledge_events("run", command_id="ack", expected_revision=revision,
                          subscription="app", expected_cursor=observed["cursor"], advance_to=event["sequence"])
    receipt: RunSnapshot | None = sdk.get_command_receipt("run", "ack")
    details: list[RecoveryDetails] = sdk.inspect_recoveries("run")
    execution: ExecutionSnapshot = sdk.inspect_execution(command.execution_id)
    for recovery in details:
        effect_revision: int = recovery.effect.revision
        task_id: str = recovery.task_id
    host = OrchestratorHost(sdk)
    host_with_callback = OrchestratorHost(sdk, lambda notification: None)

    # These ignores must remain necessary: an accidental Any regression makes
    # --warn-unused-ignores fail, proving callers still get useful diagnostics.
    Operations.dispatch(task="typo")  # type: ignore[call-arg]
    Operations.finish("running")  # type: ignore[arg-type]
    typo: DispatchOperation = {"kind": "dispatch", "task_id": "task", "extra": True}  # type: ignore[typeddict-unknown-key]
    snapshot["revison"]  # type: ignore[typeddict-item]
    observed["events"][0]["sequece"]  # type: ignore[typeddict-item]
    details[0].effect.revison  # type: ignore[attr-defined]


def use_task_submission(path: Path, handlers: dict[str, Handler], sdk: Orchestrator) -> None:
    accepted: RunSnapshot = sdk.submit_task(
        "run", "task", request_id="request", expected_revision=0,
        handler_id="echo", payload={"value": 1}, timeout_seconds=5,
        dependencies=[], watch_target={"conversation": "app"},
        dispatch=True, retry_policy=RetryPolicy(max_attempts=1))
    sdk.submit_task("run", "task", request_id="request", expected_revision=0,
                    handler_id="echo", payload=None, timeout_seconds=5)["revison"]  # type: ignore[typeddict-item]
    sdk.submit_task("run", "task", expected_revision=0,
                    handler_id="echo", payload=None, timeout_seconds=5)  # type: ignore[call-arg]
    sdk.submit_task("run", "task", request_id="request", expected_revision=0,
                    handler_id="echo", payload=None, timeout_seconds=5, dispatch="yes")  # type: ignore[arg-type]

    # Inference must survive the factory and context manager, not just explicit
    # variable annotations that could hide an Any return type.
    owned = Orchestrator.open_sqlite(path, handlers, durability="full")
    owned.submt_task()  # type: ignore[attr-defined]
    with Orchestrator.open_sqlite(path, handlers) as opened:
        snapshot: RunSnapshot = opened.create_run("run", command_id="create")
        opened.create_run("run", command_id="create")["revison"]  # type: ignore[typeddict-item]


def use_inbox_and_storage(path: Path, lease: InboxLease, handlers: dict[str, Handler]) -> None:
    def mutate(connection: sqlite3.Connection, payload: Any) -> None:
        connection.execute("INSERT INTO application_values VALUES(?)", (payload["value"],))

    def invalid_mutation() -> None:
        pass

    with NotificationInbox(path, durability="full") as inbox:
        received: InboxRecord = inbox.accept("source", {"notification_id": "notice", "value": 1})
        claimed: InboxLease | None = inbox.claim("consumer", lease_seconds=5)
        if claimed is not None:
            consumed: InboxRecord = inbox.consume(claimed, mutate)
        messages: tuple[InboxRecord, ...] = inbox.list_messages(state="pending")
        state: InboxState = received["state"]
        revision: int = received["revision"]
        inbox.retry_dead("source", "notice", expected_revision=revision)
        inbox.get("source", "notice")["revison"]  # type: ignore[typeddict-item]
        inbox.list_messages(state="delivered")  # type: ignore[arg-type]
        inbox.consume("lease")  # type: ignore[arg-type]
        inbox.consume(lease, invalid_mutation)  # type: ignore[arg-type]
        lease.fance  # type: ignore[attr-defined]

    report: dict[str, Any] = inspect_storage(path, handlers=handlers)
    backup: Path = backup_database(path, path.with_suffix(".backup.db"))
    exported: Path = export_database(path, path.with_suffix(".sql"))
    backup_database(path, path.with_suffix(".backup.db")).read_bites()  # type: ignore[attr-defined]
    export_database(path, path.with_suffix(".sql")).read_tex()  # type: ignore[attr-defined]
    inspect_storage(path, handlers=[])  # type: ignore[arg-type]


class ConsumerSandboxBackend:
    """A structural provider implementation with no optional SDK dependency."""

    name = "consumer"
    revision = "deployment-v1"

    def create(self, spec: SandboxSpec, *, operation_key: str, timeout: float) -> str:
        return "sandbox-id"

    def find(self, operation_key: str, *, timeout: float) -> tuple[str, ...]:
        return ("sandbox-id",)

    def start(self, sandbox_id: str, spec: SandboxSpec, *, timeout: float) -> str:
        return "command-id"

    def inspect(self, sandbox_id: str, command_id: str, *, timeout: float) -> SandboxObservation:
        return SandboxObservation("succeeded", exit_code=0)

    def collect(self, sandbox_id: str, command_id: str, spec: SandboxSpec, *, timeout: float) -> str:
        return "output"

    def terminate(self, sandbox_id: str, *, timeout: float) -> bool:
        return True


def use_sandbox(path: Path) -> None:
    backend: SandboxBackend = ConsumerSandboxBackend()
    spec = SandboxSpec(image="python:3.12", source="print('hello')",
                       interpreter=("/usr/local/bin/python",), cwd="/workspace",
                       artifacts=("result.json",), resources={"cpu": "1"})
    payload: dict[str, Any] = spec.to_payload()
    restored: SandboxSpec = SandboxSpec.from_payload(payload)
    observation: SandboxObservation = backend.inspect("sandbox", "command", timeout=5)
    status: str = observation.state
    handler = SandboxHandler(backend, str(path), durability="full")
    journal: SandboxJournal = handler.journal()
    pending: tuple[dict[str, Any], ...] = journal.pending(limit=10)
    history: dict[str, Any] | None = journal.get("execution")
    confirmed: bool = handler.cleanup("execution", operation_key="operation", max_fence=1)
    registered = sandbox_handlers(backend, str(path))
    runtime_bindings: Mapping[tuple[str, int], Handler] = registered
    registered[("sdk.sandbox.consumer", 1)].jornal()  # type: ignore[attr-defined]
    registered["sdk.sandbox.consumer"]  # type: ignore[index]
    handler.cleanup("execution", max_fence="old")  # type: ignore[arg-type]
    backend.inspect("sandbox", "command")  # type: ignore[call-arg]
    SandboxObservation("complete", exit_code=0)  # type: ignore[arg-type]
    restored.to_paylod()  # type: ignore[attr-defined]
    SandboxHandler(object(), str(path))  # type: ignore[arg-type]
