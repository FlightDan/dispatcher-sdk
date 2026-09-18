"""Public reliability API type coverage for an installed candidate."""

from pathlib import Path

from dispatcher_sdk import RuntimeIdentityReport, runtime_identity
from dispatcher_sdk.execution_kernel import RuntimeHost, StopReport
from dispatcher_sdk.orchestrator import (
    ExecutionOriginReport, NotificationInbox, OrchestratorHost,
    OrchestratorHostTimeoutError, RequestResultIdentity, RequestResultInbox,
    RequestResultObservation, inspect_execution_origin,
)
from dispatcher_sdk.storage import inspect_storage, inspect_storage_usage


def use_reliability(path: Path, host: OrchestratorHost, runtime_host: RuntimeHost) -> None:
    report: StopReport | None = runtime_host.stop_report
    try:
        host.stop(timeout=1)
    except OrchestratorHostTimeoutError as error:
        report = error.report
        report.to_dict()
        report.unfinished_phases
        report.unfinished_phase  # type: ignore[attr-defined]

    identity: RuntimeIdentityReport = runtime_identity(path, check="schema", timeout_seconds=2)
    inspect_storage(path, check="bindings", handlers={}, timeout_seconds=2)
    inspect_storage_usage(path, detail="files", timeout_seconds=2)
    runtime_identity(path, check="unchecked")  # type: ignore[arg-type]
    origin: ExecutionOriginReport = inspect_execution_origin(path, execution_id="execution")
    origin.application_attempt
    origin.application_atempt  # type: ignore[attr-defined]
    journal = RequestResultInbox(NotificationInbox(path))
    result_id: RequestResultIdentity = journal.record_result(
        "source", "caller", "request", execution_id="execution", result_id="result", result={})
    journal.mark_delivered(result_id)
    result: RequestResultObservation | None = journal.lookup("source", "caller", "request")
    if result is not None:
        journal.confirm_received(result.identity)
    journal.confirm_received("result")  # type: ignore[arg-type]
