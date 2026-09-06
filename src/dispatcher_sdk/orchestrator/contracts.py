"""Application-neutral contracts for durable orchestration operations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..execution_kernel import ExecutionCommandV2


class OrchestrationError(ValueError):
    """An operation violates a mechanical orchestration invariant."""


class RevisionConflict(OrchestrationError):
    """The application decided from a stale snapshot or subscription cursor."""


class CommandConflict(OrchestrationError):
    """A command identity was reused for different content."""


TERMINAL = frozenset({"succeeded", "failed", "timed_out", "cancelled", "dead"})
RUN_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


def canonical(value: Any) -> str:
    def validate(item):
        if item is None or type(item) in {bool, str, int, float}:
            return
        if type(item) is list:
            for child in item:
                validate(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                validate(child)
            return
        raise OrchestrationError("value must be strict JSON with string object keys")
    try:
        validate(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (RecursionError, ValueError, TypeError) as exc:
        raise OrchestrationError("value must be finite, acyclic strict JSON") from exc


def clone(value: Any) -> Any:
    return json.loads(canonical(value))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise OrchestrationError(f"{label} must be a nonempty string")
    return value


def integer(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise OrchestrationError(f"{label} must be a nonnegative integer")
    return value


def attempt(command: Any) -> dict:
    parsed = ExecutionCommandV2.from_dict(command)
    return {"command": parsed.to_dict(), "state": "planned", "result": None, "dispatched": False,
            "kernel_revision": 0, "kernel_snapshot": None}


def validate_operation(value: Any) -> dict:
    if type(value) is not dict:
        raise OrchestrationError("operation must be an object")
    schemas = {
        "add_task": ({"task_id", "command"}, {"dependencies"}),
        "set_dependencies": ({"task_id", "dependencies"}, set()),
        "dispatch": ({"task_id"}, set()),
        "new_attempt": ({"task_id", "command"}, set()),
        "cancel": ({"task_id", "reason"}, set()),
        "wait": ({"wait_id"}, {"payload"}),
        "signal": ({"signal_id", "payload"}, set()),
        "release_wait": ({"wait_id"}, set()),
        "finish": ({"state"}, set()),
        "watch_task": ({"task_id", "watch_id", "target"}, {"max_deliveries"}),
    }
    kind = value.get("kind")
    if type(kind) is not str or kind not in schemas:
        raise OrchestrationError("unknown operation kind")
    required, optional = schemas[kind]
    if not required <= value.keys() or value.keys() - required - optional - {"kind"}:
        raise OrchestrationError(f"invalid fields for {kind}")
    for field in ("task_id", "wait_id", "signal_id", "reason", "watch_id"):
        if field in value:
            identifier(value[field], field)
    return clone(value)
