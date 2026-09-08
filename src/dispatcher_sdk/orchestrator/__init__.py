"""Application-neutral durable orchestration. Creating a Run starts no workflow."""

from .contracts import CommandConflict, OrchestrationError, RevisionConflict
from .contracts import canonical as canonical_json
from .engine import Orchestrator
from .host import OrchestratorHost, OrchestratorHostHealth
from .operations import Operations
from .recovery import RecoveryDetails, RecoveryRecord
from .availability import WorkAvailabilityReport, WorkExecutionSummary, inspect_work_availability
from .projection import (
    ProjectionConsumer, ProjectionSource, ProjectionDisposition, ProjectionStatus,
    ProjectionEventIdentity, ProjectionFailure, ProjectionDrainReport,
)
from .cancellation import (
    EvidenceStatus, CancellationFact, ExecutionCancellationReport,
    CancellationRecoveryReport, inspect_cancellation,
)
from .inbox import NotificationInbox, InboxLease, InboxRecord, InboxState
from .types import (
    AddTaskOperation, AttemptSnapshot, AttemptState, CancelOperation,
    DispatchOperation, FinishOperation, NewAttemptOperation, Observation,
    Operation, ReleaseWaitOperation, RunEvent, RunSnapshot, RunState,
    SetDependenciesOperation, SignalOperation, TaskSnapshot, TerminalRunState,
    WaitOperation, WaitSnapshot, WatchTaskOperation,
)

__all__ = [
    "WorkAvailabilityReport", "WorkExecutionSummary", "inspect_work_availability",
    "ProjectionConsumer", "ProjectionSource", "ProjectionDisposition", "ProjectionStatus",
    "ProjectionEventIdentity", "ProjectionFailure", "ProjectionDrainReport",
    "EvidenceStatus", "CancellationFact", "ExecutionCancellationReport",
    "CancellationRecoveryReport", "inspect_cancellation",
    "NotificationInbox", "InboxLease", "InboxRecord", "InboxState",
    "Orchestrator", "OrchestratorHost", "OrchestratorHostHealth", "OrchestrationError",
    "RevisionConflict", "CommandConflict", "canonical_json", "Operations", "RecoveryDetails", "RecoveryRecord",
    "Operation", "AddTaskOperation", "SetDependenciesOperation", "DispatchOperation",
    "NewAttemptOperation", "CancelOperation", "WaitOperation", "SignalOperation",
    "ReleaseWaitOperation", "FinishOperation", "WatchTaskOperation", "AttemptSnapshot",
    "TaskSnapshot", "WaitSnapshot", "RunSnapshot", "RunEvent", "Observation",
    "RunState", "TerminalRunState", "AttemptState",
]
