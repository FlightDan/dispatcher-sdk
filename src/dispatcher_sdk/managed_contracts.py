"""Immutable declarations for managed multi-task Runs.

These contracts only describe application intent. In particular, ``routing``
and each task's ``acceptance`` value are opaque application declarations; the
SDK does not infer that a successful execution is accepted or choose a route.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, ClassVar, Literal

from .execution_kernel.contracts import RetryPolicy


class ManagedContractError(ValueError):
    """A managed Run declaration violates its public data contract."""


class _FrozenObject(Mapping[str, Any]):
    """Small recursively immutable mapping used for JSON object fields."""

    __slots__ = ("_items", "_lookup")

    def __init__(self, items: tuple[tuple[str, Any], ...]) -> None:
        object.__setattr__(self, "_items", items)
        object.__setattr__(self, "_lookup", MappingProxyType(dict(items)))

    def __getitem__(self, key: str) -> Any:
        return self._lookup[key]

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return NotImplemented
        return dict(self._items) == dict(other.items())

    def __hash__(self) -> int:
        return hash(self._items)

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("managed JSON values are immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("managed JSON values are immutable")


def _identifier(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ManagedContractError(f"{name} must be a non-empty string")
    return value


def _freeze_json(value: Any, path: str, active: set[int] | None = None) -> Any:
    """Validate strict JSON and freeze containers without retaining caller data."""
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ManagedContractError(f"{path} contains a non-finite number")
        return value
    if type(value) in {list, dict}:
        ancestors = set() if active is None else active
        identity = id(value)
        if identity in ancestors:
            raise ManagedContractError(f"{path} contains a cyclic reference")
        ancestors.add(identity)
        try:
            if type(value) is list:
                return tuple(_freeze_json(item, f"{path}[{index}]", ancestors)
                             for index, item in enumerate(value))
            if any(type(key) is not str for key in value):
                raise ManagedContractError(f"{path} has a non-string object key")
            return _FrozenObject(tuple(
                (key, _freeze_json(value[key], f"{path}.{key}", ancestors))
                for key in sorted(value)
            ))
        finally:
            ancestors.remove(identity)
    raise ManagedContractError(
        f"{path} has unsupported type {type(value).__name__}; expected strict JSON"
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, _FrozenObject):
        return {key: _thaw_json(item) for key, item in value._items}
    if type(value) is tuple:
        return [_thaw_json(item) for item in value]
    return value


def _json_object(value: Any, name: str) -> _FrozenObject:
    if type(value) is not dict:
        raise ManagedContractError(f"{name} must be a strict JSON object")
    return _freeze_json(value, name)


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (OverflowError, RecursionError, TypeError, ValueError) as error:
        raise ManagedContractError("managed Run is not strict JSON") from error


@dataclass(frozen=True, slots=True)
class RunBudget:
    """Run-wide SDK execution limit; deadline uses Unix epoch seconds."""

    max_total_claims: int
    deadline_at: float

    def __post_init__(self) -> None:
        if (type(self.max_total_claims) is not int
                or not 0 <= self.max_total_claims <= (1 << 63) - 1):
            raise ManagedContractError("max_total_claims must be a SQLite-sized integer >= 0")
        deadline = self.deadline_at
        if type(deadline) not in {int, float}:
            raise ManagedContractError("deadline_at must be a finite positive Unix timestamp")
        try:
            deadline = float(deadline)
        except (OverflowError, ValueError) as error:
            raise ManagedContractError(
                "deadline_at must be a finite positive Unix timestamp"
            ) from error
        if not math.isfinite(deadline) or deadline <= 0:
            raise ManagedContractError("deadline_at must be a finite positive Unix timestamp")
        object.__setattr__(self, "deadline_at", deadline)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "max_total_claims": self.max_total_claims,
            "deadline_at": self.deadline_at,
        }

    schema_version: ClassVar[int] = 1


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """One task declaration; acceptance remains an application decision."""

    task_id: str
    handler_id: str
    payload: Any
    acceptance: Mapping[str, Any]
    dependencies: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)

    def __post_init__(self) -> None:
        _identifier(self.task_id, "task_id")
        _identifier(self.handler_id, "handler_id")
        object.__setattr__(self, "payload", _freeze_json(self.payload, "payload"))
        object.__setattr__(self, "acceptance", _json_object(self.acceptance, "acceptance"))

        if type(self.dependencies) not in {list, tuple}:
            raise ManagedContractError("dependencies must be a list or tuple of task identifiers")
        dependencies = tuple(_identifier(value, "dependency") for value in self.dependencies)
        if len(dependencies) != len(set(dependencies)):
            raise ManagedContractError("dependencies must not contain duplicates")
        if self.task_id in dependencies:
            raise ManagedContractError("a task cannot depend on itself")
        object.__setattr__(self, "dependencies", tuple(sorted(dependencies)))

        timeout = self.timeout_seconds
        if type(timeout) not in {int, float}:
            raise ManagedContractError("timeout_seconds must be finite and positive")
        try:
            timeout = float(timeout)
        except (OverflowError, ValueError) as error:
            raise ManagedContractError("timeout_seconds must be finite and positive") from error
        if not math.isfinite(timeout) or timeout <= 0:
            raise ManagedContractError("timeout_seconds must be finite and positive")
        object.__setattr__(self, "timeout_seconds", timeout)

        if type(self.retry_policy) is not RetryPolicy:
            raise ManagedContractError("retry_policy must be a RetryPolicy")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "handler_id": self.handler_id,
            "payload": _thaw_json(self.payload),
            "acceptance": _thaw_json(self.acceptance),
            "dependencies": list(self.dependencies),
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy.to_dict(),
        }

    schema_version: ClassVar[int] = 1


@dataclass(frozen=True, slots=True)
class RunSpec:
    """A declarative task graph with stable content for create idempotency.

    Task and dependency order is normalized by identifier because scheduling
    semantics come from the dependency graph. ``routing`` and per-task
    ``acceptance`` are persisted declarations only; applications interpret them.
    """

    tasks: tuple[TaskSpec, ...]
    budget: RunBudget
    routing: Mapping[str, Any]
    input: Any = None

    def __post_init__(self) -> None:
        if type(self.tasks) not in {list, tuple} or not self.tasks:
            raise ManagedContractError("tasks must be a non-empty list or tuple of TaskSpec")
        if any(type(task) is not TaskSpec for task in self.tasks):
            raise ManagedContractError("tasks must contain only TaskSpec records")
        tasks = tuple(sorted(self.tasks, key=lambda task: task.task_id))
        identifiers = [task.task_id for task in tasks]
        if len(identifiers) != len(set(identifiers)):
            raise ManagedContractError("task identifiers must be unique")
        task_ids = set(identifiers)
        for task in tasks:
            unknown = sorted(set(task.dependencies) - task_ids)
            if unknown:
                raise ManagedContractError(
                    f"task {task.task_id!r} has unknown dependencies: {', '.join(unknown)}"
                )
        _validate_acyclic(tasks)
        object.__setattr__(self, "tasks", tasks)
        if type(self.budget) is not RunBudget:
            raise ManagedContractError("budget must be a RunBudget")
        object.__setattr__(self, "routing", _json_object(self.routing, "routing"))
        object.__setattr__(self, "input", _freeze_json(self.input, "input"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tasks": [task.to_dict() for task in self.tasks],
            "budget": self.budget.to_dict(),
            "routing": _thaw_json(self.routing),
            "input": _thaw_json(self.input),
        }

    @property
    def canonical_json(self) -> str:
        """Stable JSON used as the create request's conflict-defining content."""
        return _canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """SHA-256 of :attr:`canonical_json`, suitable for an idempotency receipt."""
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()

    schema_version: ClassVar[int] = 1


def _validate_acyclic(tasks: tuple[TaskSpec, ...]) -> None:
    dependencies = {task.task_id: task.dependencies for task in tasks}
    dependents: dict[str, list[str]] = {task.task_id: [] for task in tasks}
    indegree = {task_id: len(values) for task_id, values in dependencies.items()}
    for task_id, values in dependencies.items():
        for dependency in values:
            dependents[dependency].append(task_id)
    ready = [task.task_id for task in tasks if indegree[task.task_id] == 0]
    visited = 0
    while ready:
        task_id = ready.pop()
        visited += 1
        for child in dependents[task_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if visited != len(tasks):
        raise ManagedContractError("task dependencies must be acyclic")


ControlState = Literal["active", "pausing", "paused"]


@dataclass(frozen=True, slots=True)
class ManagedControlSnapshot:
    """New control-plane state kept separate from legacy ``RunSnapshot``."""

    control_state: ControlState
    control_version: int
    recovery_obligations: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if type(self.control_state) is not str or self.control_state not in {"active", "pausing", "paused"}:
            raise ManagedContractError("control_state must be active, pausing, or paused")
        if type(self.control_version) is not int or self.control_version < 0:
            raise ManagedContractError("control_version must be an integer >= 0")
        if type(self.recovery_obligations) not in {list, tuple}:
            raise ManagedContractError("recovery_obligations must be a list or tuple")
        obligations = tuple(
            _json_object(value, f"recovery_obligations[{index}]")
            for index, value in enumerate(self.recovery_obligations)
        )
        object.__setattr__(self, "recovery_obligations", obligations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_state": self.control_state,
            "control_version": self.control_version,
            "recovery_obligations": [
                _thaw_json(value) for value in self.recovery_obligations
            ],
        }


__all__ = [
    "ControlState",
    "ManagedContractError",
    "ManagedControlSnapshot",
    "RunBudget",
    "RunSpec",
    "TaskSpec",
]
