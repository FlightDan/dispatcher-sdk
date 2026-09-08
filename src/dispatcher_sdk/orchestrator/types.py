"""Typed views of the existing JSON operation and Run contracts.

These TypedDicts are ordinary dictionaries at runtime. Application payloads
remain application-defined; the command boundary still validates strict JSON.
"""

from typing import Any, Literal, TypedDict, Union


RunState = Literal["running", "succeeded", "failed", "cancelled"]
TerminalRunState = Literal["succeeded", "failed", "cancelled"]
AttemptState = Literal[
    "planned", "pending_dispatch", "queued", "leased", "running",
    "recovery_required", "succeeded", "failed", "timed_out", "cancelled", "dead",
]


class _AddTaskRequired(TypedDict):
    kind: Literal["add_task"]
    task_id: str
    command: dict[str, Any]


class AddTaskOperation(_AddTaskRequired, total=False):
    dependencies: list[str]


class SetDependenciesOperation(TypedDict):
    kind: Literal["set_dependencies"]
    task_id: str
    dependencies: list[str]


class DispatchOperation(TypedDict):
    kind: Literal["dispatch"]
    task_id: str


class NewAttemptOperation(TypedDict):
    kind: Literal["new_attempt"]
    task_id: str
    command: dict[str, Any]


class CancelOperation(TypedDict):
    kind: Literal["cancel"]
    task_id: str
    reason: str


class _WaitRequired(TypedDict):
    kind: Literal["wait"]
    wait_id: str


class WaitOperation(_WaitRequired, total=False):
    payload: Any


class SignalOperation(TypedDict):
    kind: Literal["signal"]
    signal_id: str
    payload: Any


class ReleaseWaitOperation(TypedDict):
    kind: Literal["release_wait"]
    wait_id: str


class FinishOperation(TypedDict):
    kind: Literal["finish"]
    state: TerminalRunState


class _WatchTaskRequired(TypedDict):
    kind: Literal["watch_task"]
    task_id: str
    watch_id: str
    target: Any


class WatchTaskOperation(_WatchTaskRequired, total=False):
    max_deliveries: int


Operation = Union[
    AddTaskOperation, SetDependenciesOperation, DispatchOperation,
    NewAttemptOperation, CancelOperation, WaitOperation, SignalOperation,
    ReleaseWaitOperation, FinishOperation, WatchTaskOperation,
]


class _AttemptRequired(TypedDict):
    command: dict[str, Any]
    state: AttemptState
    result: dict[str, Any] | None
    dispatched: bool
    kernel_revision: int
    kernel_snapshot: dict[str, Any] | None


class AttemptSnapshot(_AttemptRequired, total=False):
    dependency_attempts: dict[str, int]
    cancel_reason: str
    generation: int


class TaskSnapshot(TypedDict):
    task_id: str
    dependencies: list[str]
    attempts: list[AttemptSnapshot]


class WaitSnapshot(TypedDict):
    state: Literal["open", "released"]
    payload: Any


class RunSnapshot(TypedDict):
    run_id: str
    revision: int
    state: RunState
    generation: int
    input: Any
    definition: Any
    application_state: Any
    tasks: dict[str, TaskSnapshot]
    waits: dict[str, WaitSnapshot]
    signals: dict[str, Any]


class RunEvent(TypedDict):
    sequence: int
    run_id: str
    revision: int
    kind: str
    payload: Any


class Observation(TypedDict):
    snapshot: RunSnapshot
    cursor: int
    event_high_watermark: int
    events: list[RunEvent]


__all__ = [
    "RunState", "TerminalRunState", "AttemptState", "Operation",
    "AddTaskOperation", "SetDependenciesOperation", "DispatchOperation",
    "NewAttemptOperation", "CancelOperation", "WaitOperation", "SignalOperation",
    "ReleaseWaitOperation", "FinishOperation", "WatchTaskOperation",
    "AttemptSnapshot", "TaskSnapshot", "WaitSnapshot", "RunSnapshot",
    "RunEvent", "Observation",
]
