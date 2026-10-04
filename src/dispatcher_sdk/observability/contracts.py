"""Bounded, identity-bound execution observations.

Observation timestamps are wall-clock facts. They are not execution budget
authority; elapsed time inside a recorder uses its own monotonic clock.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, ContextManager, Literal, Mapping, Protocol


def identifier(value: str, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value.encode("utf-8")) > 1024:
        raise ValueError(f"{name} must be a nonempty string of at most 1024 bytes")
    return value


def positive(value: float, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


@dataclass(frozen=True)
class ObservationOptions:
    flush_interval: float = 1.0
    tail_bytes: int = 64 * 1024
    queue_items: int = 256
    queue_bytes: int = 1024 * 1024
    batch_summaries: int = 128
    batch_bytes: int = 256 * 1024
    page_events: int = 50
    query_bytes: int = 256 * 1024
    query_timeout: float = 3.0
    write_timeout: float = 0.1
    process_freshness: float = 3.0

    def __post_init__(self) -> None:
        for name in ("flush_interval", "query_timeout", "write_timeout", "process_freshness"):
            positive(getattr(self, name), name)
        for name in ("tail_bytes", "queue_items", "queue_bytes", "batch_summaries",
                     "batch_bytes", "page_events", "query_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.query_bytes < 4096 or self.batch_bytes < 1024:
            raise ValueError("query_bytes must be at least 4096 and batch_bytes at least 1024")


@dataclass(frozen=True)
class ObservationIdentity:
    execution_id: str
    attempt: int
    fence: int
    run_id: str | None = None
    task_id: str | None = None
    generation: int = 0
    task_attempt: int | None = None

    def __post_init__(self) -> None:
        identifier(self.execution_id, "execution_id")
        for name in ("run_id", "task_id"):
            value = getattr(self, name)
            if value is not None:
                identifier(value, name)
        for name in ("attempt", "fence", "generation", "task_attempt"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StallPolicy:
    policy_id: str
    metrics: tuple[str, ...] = ("progress",)
    sample_interval: float = 600.0
    consecutive_windows: int = 3
    wait_exemptions: tuple[str, ...] = ()
    max_deliveries: int = 5
    version: int = 1

    def __post_init__(self) -> None:
        identifier(self.policy_id, "policy_id")
        positive(self.sample_interval, "sample_interval")
        for name in ("consecutive_windows", "max_deliveries", "version"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not self.metrics or len(self.metrics) > 32 or len(self.wait_exemptions) > 32:
            raise ValueError("policy must have 1 to 32 metrics and at most 32 wait exemptions")
        for value in (*self.metrics, *self.wait_exemptions):
            identifier(value, "policy metric/exemption")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProcessState = Literal["alive", "exited", "unknown"]


class ObservationError(ValueError):
    """Observation storage or binding is incompatible; no business verdict."""


class ProcessObservation(Protocol):
    def snapshot(self) -> dict[str, Any]: ...


class ExecutionActivity(Protocol):
    """The typed capture capability bound to a handler's execution identity."""

    def report_bytes(self, stream: str, chunk: bytes, *, retain_tail: bool = True) -> dict[str, Any]: ...
    def enable_stream(self, stream: str) -> dict[str, Any]: ...
    def report_byte_count(self, stream: str, byte_count: int, *, source: str | None = None) -> dict[str, Any]: ...
    def model(self, kind: str = "event") -> dict[str, Any]: ...
    def report_model(self, kind: str = "event") -> dict[str, Any]: ...
    def tool(self, kind: str = "activity") -> dict[str, Any]: ...
    def report_tool(self, kind: str = "activity") -> dict[str, Any]: ...
    def observe_process(self, process: Any, *, role: str = "agent", process_id: str | None = None) -> ProcessObservation: ...
    def wait(self, reason: str, *, target: Any = None, deadline_at: float | None = None,
             resources: Mapping[str, Any] | None = None) -> ContextManager[dict[str, Any]]: ...
    def heartbeat(self) -> dict[str, Any]: ...
    def phase(self, phase: str, *, details: Mapping[str, Any] | None = None) -> dict[str, Any]: ...
    def progress(self, key: str, *, details: Mapping[str, Any] | None = None,
                 timeout: float | None = None) -> dict[str, Any]: ...
    def flush(self) -> dict[str, Any]: ...
    def snapshot(self, *, persisted_only: bool = False) -> dict[str, Any]: ...
    def start(self) -> ExecutionActivity: ...
    def close(self, *, timeout: float = 1.0) -> dict[str, Any]: ...


__all__ = ["ObservationOptions", "ObservationIdentity", "StallPolicy", "ProcessState", "ObservationError",
           "ExecutionActivity", "ProcessObservation"]
