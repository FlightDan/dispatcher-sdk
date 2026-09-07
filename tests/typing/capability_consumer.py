"""Public additive API types; mypy --follow-imports=silent --warn-unused-ignores."""
from pathlib import Path

from dispatcher_sdk import RuntimeIdentityReport, runtime_identity
from dispatcher_sdk.execution_kernel import ExecutionSnapshot, inspect_cancellation_journal
from dispatcher_sdk.orchestrator import (
    CancellationRecoveryReport, Orchestrator, ProjectionConsumer,
    ProjectionDisposition, ProjectionDrainReport, ProjectionEventIdentity,
    RunEvent, WorkAvailabilityReport,
)


def use_capabilities(sdk: Orchestrator, path: Path, snapshot: ExecutionSnapshot) -> None:
    identity: RuntimeIdentityReport = runtime_identity(path, handlers={})
    identity.module.source_sha256
    identity.module.source_hash  # type: ignore[attr-defined]
    runtime_identity(path, durability="unsafe")  # type: ignore[arg-type]

    def persist(event_id: ProjectionEventIdentity, event: RunEvent) -> ProjectionDisposition:
        source: str = event_id.source_id
        sequence: int = event["sequence"]
        return "persisted"

    consumer = ProjectionConsumer(sdk, source_id="stable-source", subscription="projection")
    drained: ProjectionDrainReport = consumer.drain("run", persist, timeout_seconds=5)
    consumer.drain("run", lambda identity, event: None)  # type: ignore[arg-type,return-value]
    drained.acknowleged_cursor  # type: ignore[attr-defined]

    availability: WorkAvailabilityReport = sdk.inspect_work_availability("run", effect_scan_limit=1000)
    available: int | None = availability.claimable_now
    availability.claimable_nwo  # type: ignore[attr-defined]
    sdk.inspect_work_availability("run", effect_scan_limit="all")  # type: ignore[arg-type]

    cancellation: CancellationRecoveryReport = sdk.inspect_cancellation("run", task_id="task")
    cancellation.executions[0].local_process_tree_reaped.status
    cancellation.executions[0].fance  # type: ignore[attr-defined]
    receipts = inspect_cancellation_journal(path, source_id="stable-source", kernel_path=path.parent / "kernel.db",
                                          snapshot=snapshot)
    receipts.receipts[0].expected_revision
    receipts.receipts[0].expected_revison  # type: ignore[attr-defined]
