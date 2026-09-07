"""Discoverable constructors that preserve the JSON command protocol."""

from typing import Any, cast

from ..execution_kernel import ExecutionCommandV2
from .contracts import validate_operation
from .types import (
    AddTaskOperation, CancelOperation, DispatchOperation, FinishOperation,
    NewAttemptOperation, ReleaseWaitOperation, SetDependenciesOperation,
    SignalOperation, TerminalRunState, WaitOperation, WatchTaskOperation,
)


def _command(command: ExecutionCommandV2 | dict[str, Any]) -> dict[str, Any]:
    if isinstance(command, ExecutionCommandV2):
        command = command.to_dict()
    return ExecutionCommandV2.from_dict(command).to_dict()


class Operations:
    """Build detached dictionaries; submit them with ``apply_operations``.

    Identifiers and JSON are checked at construction. Run-dependent invariants
    (such as dependency cycles and allowed transitions) are checked atomically
    on submission, exactly as for hand-written operation dictionaries.
    """

    @staticmethod
    def add_task(task_id: str, command: ExecutionCommandV2 | dict[str, Any], *,
                 dependencies: list[str] | None = None) -> AddTaskOperation:
        value: dict[str, Any] = {"kind": "add_task", "task_id": task_id, "command": _command(command)}
        if dependencies is not None:
            value["dependencies"] = dependencies
        return cast(AddTaskOperation, validate_operation(value))

    @staticmethod
    def set_dependencies(task_id: str, dependencies: list[str]) -> SetDependenciesOperation:
        return cast(SetDependenciesOperation, validate_operation({
            "kind": "set_dependencies", "task_id": task_id, "dependencies": dependencies}))

    @staticmethod
    def dispatch(task_id: str) -> DispatchOperation:
        return cast(DispatchOperation, validate_operation({"kind": "dispatch", "task_id": task_id}))

    @staticmethod
    def new_attempt(task_id: str, command: ExecutionCommandV2 | dict[str, Any]) -> NewAttemptOperation:
        return cast(NewAttemptOperation, validate_operation({
            "kind": "new_attempt", "task_id": task_id, "command": _command(command)}))

    @staticmethod
    def cancel(task_id: str, *, reason: str) -> CancelOperation:
        return cast(CancelOperation, validate_operation({
            "kind": "cancel", "task_id": task_id, "reason": reason}))

    @staticmethod
    def wait(wait_id: str, *, payload: Any = None) -> WaitOperation:
        return cast(WaitOperation, validate_operation({
            "kind": "wait", "wait_id": wait_id, "payload": payload}))

    @staticmethod
    def signal(signal_id: str, payload: Any) -> SignalOperation:
        return cast(SignalOperation, validate_operation({
            "kind": "signal", "signal_id": signal_id, "payload": payload}))

    @staticmethod
    def release_wait(wait_id: str) -> ReleaseWaitOperation:
        return cast(ReleaseWaitOperation, validate_operation({"kind": "release_wait", "wait_id": wait_id}))

    @staticmethod
    def finish(state: TerminalRunState) -> FinishOperation:
        return cast(FinishOperation, validate_operation({"kind": "finish", "state": state}))

    @staticmethod
    def watch_task(task_id: str, *, watch_id: str, target: Any,
                   max_deliveries: int = 5) -> WatchTaskOperation:
        return cast(WatchTaskOperation, validate_operation({
            "kind": "watch_task", "task_id": task_id, "watch_id": watch_id,
            "target": target, "max_deliveries": max_deliveries}))


__all__ = ["Operations"]
