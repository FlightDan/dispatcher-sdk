"""Immutable deadline envelopes and conservative elapsed-clock continuity.

Epoch deadlines are durable. Elapsed samples are reusable only when their
provider proves a common clock domain; a wall-clock watermark is insufficient.
These records intentionally do not change the public V2 execution contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import os
from pathlib import Path
import time
from typing import Any, Mapping
import uuid


class BudgetClockUnknownError(RuntimeError):
    """Business execution cannot establish trustworthy remaining time."""


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be finite and non-negative")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite and non-negative") from exc
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'non-negative'}")
    return result


def _identifier(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _fields(value: Any, keys: set[str]) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys | {"schema_version"}:
        raise ValueError("budget record has missing or unknown fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported budget schema_version")
    return value


@dataclass(frozen=True, slots=True)
class ClockCheckpoint:
    wall_at: float
    elapsed_at: float
    domain_id: str | None
    domain_scope: str = "boot"
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "wall_at", _number(self.wall_at, "wall_at"))
        object.__setattr__(self, "elapsed_at", _number(self.elapsed_at, "elapsed_at"))
        if self.domain_scope not in ("boot", "process", "unknown"):
            raise ValueError("invalid clock domain_scope")
        if self.domain_id is not None:
            _identifier(self.domain_id, "domain_id")
        if (self.domain_scope == "unknown") != (self.domain_id is None):
            raise ValueError("unknown clock domains must have no domain_id")
        if self.unknown_reason is not None:
            _identifier(self.unknown_reason, "unknown_reason")

    def effective_time(self, sample: ClockCheckpoint) -> float | None:
        if (self.domain_id is None or self.domain_id != sample.domain_id
                or self.domain_scope != sample.domain_scope
                or sample.elapsed_at < self.elapsed_at):
            return None
        result = max(sample.wall_at, self.wall_at + sample.elapsed_at - self.elapsed_at)
        return result if math.isfinite(result) else None

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "wall_at": self.wall_at,
                "elapsed_at": self.elapsed_at, "domain_id": self.domain_id,
                "domain_scope": self.domain_scope, "unknown_reason": self.unknown_reason}

    @classmethod
    def from_dict(cls, value: Any) -> ClockCheckpoint:
        fields = _fields(value, {"wall_at", "elapsed_at", "domain_id", "domain_scope", "unknown_reason"})
        return cls(**{key: item for key, item in fields.items() if key != "schema_version"})


_PROCESS_CLOCK_ID = f"process:{os.getpid()}:{uuid.uuid4()}"
_PROCESS_CLOCK_PID = os.getpid()


def _windows_boot_sample() -> tuple[str, float] | None:
    """Use an OS-provided boot GUID and suspend-inclusive tick count.

    Unsupported or unrecognized native responses never establish continuity.
    The boot GUID is copied as clock provenance, not computed from artifacts.
    """
    import ctypes
    from ctypes import wintypes

    class BootEnvironment(ctypes.Structure):
        _fields_ = [("identifier", ctypes.c_ubyte * 16),
                    ("firmware_type", wintypes.DWORD), ("boot_flags", ctypes.c_ulonglong)]

    try:
        win_dll = getattr(ctypes, "WinDLL")
        native = win_dll("ntdll")
        query = native.NtQuerySystemInformation
        query.argtypes = [wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
                          ctypes.POINTER(wintypes.ULONG)]
        query.restype = wintypes.LONG
        environment, returned = BootEnvironment(), wintypes.ULONG()
        status = query(90, ctypes.byref(environment), ctypes.sizeof(environment), ctypes.byref(returned))
        if (status != 0 or returned.value != ctypes.sizeof(environment)
                or environment.firmware_type not in (0, 1, 2)
                or not any(environment.identifier)):
            return None
        ticks = win_dll("kernel32").GetTickCount64
        ticks.argtypes, ticks.restype = [], ctypes.c_ulonglong
        return f"windows-boot:{uuid.UUID(bytes_le=bytes(environment.identifier))}", ticks() / 1000.0
    except (AttributeError, OSError, ValueError):
        return None


def sample_clock(*, wall_time: float | None = None) -> ClockCheckpoint:
    """Capture native boot continuity, or explicitly limited process continuity."""
    global _PROCESS_CLOCK_ID, _PROCESS_CLOCK_PID
    if os.getpid() != _PROCESS_CLOCK_PID:
        _PROCESS_CLOCK_PID = os.getpid()
        _PROCESS_CLOCK_ID = f"process:{os.getpid()}:{uuid.uuid4()}"
    elapsed = time.monotonic()
    domain_id, scope = _PROCESS_CLOCK_ID, "process"
    reason: str | None = "restart_continuity_unavailable"
    try:
        if hasattr(time, "CLOCK_BOOTTIME"):
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
            # Validate the native identifier's representation, without hashing it.
            uuid.UUID(boot_id)
            elapsed = time.clock_gettime(time.CLOCK_BOOTTIME)
            domain_id, scope, reason = f"linux-boot:{boot_id}", "boot", None
        elif os.name == "nt":
            native = _windows_boot_sample()
            if native is not None:
                domain_id, elapsed = native
                scope, reason = "boot", None
    except (OSError, ValueError):
        pass
    wall = time.time() if wall_time is None else wall_time
    return ClockCheckpoint(wall, elapsed, domain_id, scope, reason)


@dataclass(frozen=True, slots=True)
class DeadlineConstraint:
    origin_id: str
    source: str
    deadline_at: float
    reserve_seconds: float = 0.0

    def __post_init__(self) -> None:
        _identifier(self.origin_id, "origin_id")
        if self.source not in ("run", "execution", "parent", "tool"):
            raise ValueError("invalid deadline source")
        object.__setattr__(self, "deadline_at", _number(self.deadline_at, "deadline_at", positive=True))
        object.__setattr__(self, "reserve_seconds", _number(self.reserve_seconds, "reserve_seconds"))
        if self.reserve_seconds > self.deadline_at:
            raise ValueError("reserve_seconds exceeds deadline_at")

    @property
    def work_deadline_at(self) -> float:
        return self.deadline_at - self.reserve_seconds

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "origin_id": self.origin_id, "source": self.source,
                "deadline_at": self.deadline_at, "reserve_seconds": self.reserve_seconds}

    @classmethod
    def from_dict(cls, value: Any) -> DeadlineConstraint:
        fields = _fields(value, {"origin_id", "source", "deadline_at", "reserve_seconds"})
        return cls(**{key: item for key, item in fields.items() if key != "schema_version"})


def _constraints(values: Any) -> tuple[DeadlineConstraint, ...]:
    if type(values) not in (list, tuple):
        raise ValueError("constraints must be a list or tuple")
    result: dict[str, DeadlineConstraint] = {}
    for constraint in values:
        if type(constraint) is not DeadlineConstraint:
            raise ValueError("constraints must contain DeadlineConstraint records")
        previous = result.get(constraint.origin_id)
        if previous is not None and previous != constraint:
            raise ValueError("conflicting deadline constraints for one origin")
        result[constraint.origin_id] = constraint
    return tuple(result.values())


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    started_at: float | None
    constraints: tuple[DeadlineConstraint, ...]
    observed_at: float | None
    effective_work_deadline_at: float | None
    effective_hard_deadline_at: float | None
    limiting_source: str | None
    hard_limiting_source: str | None
    remaining_work_seconds: float | None
    remaining_hard_seconds: float | None
    clock_status: str
    unknown_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", _constraints(self.constraints))
        for name in ("started_at", "observed_at", "effective_work_deadline_at",
                     "effective_hard_deadline_at", "remaining_work_seconds", "remaining_hard_seconds"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _number(value, name))
        for name in ("limiting_source", "hard_limiting_source"):
            if getattr(self, name) not in (None, "run", "execution", "parent", "tool"):
                raise ValueError(f"invalid {name}")
        if self.clock_status not in ("trusted", "unknown"):
            raise ValueError("invalid clock_status")
        if self.unknown_reason is not None:
            _identifier(self.unknown_reason, "unknown_reason")
        if self.clock_status == "unknown" and any(value is not None for value in (
                self.observed_at, self.remaining_work_seconds, self.remaining_hard_seconds)):
            raise ValueError("unknown clock cannot report remaining time")
        if self.clock_status == "trusted" and self.observed_at is None:
            raise ValueError("trusted clock requires observed_at")
        work = min(self.constraints, key=lambda item: item.work_deadline_at, default=None)
        hard = min(self.constraints, key=lambda item: item.deadline_at, default=None)
        expected = (None if work is None else work.work_deadline_at,
                    None if hard is None else hard.deadline_at,
                    None if work is None else work.source, None if hard is None else hard.source)
        if expected != (self.effective_work_deadline_at, self.effective_hard_deadline_at,
                        self.limiting_source, self.hard_limiting_source):
            raise ValueError("effective deadline does not match constraints")
        if self.clock_status == "trusted":
            assert self.observed_at is not None
            for deadline, remaining in ((expected[0], self.remaining_work_seconds),
                                        (expected[1], self.remaining_hard_seconds)):
                value = None if deadline is None else max(0.0, deadline - self.observed_at)
                if value != remaining:
                    raise ValueError("remaining time does not match deadline")

    def to_dict(self) -> dict[str, Any]:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__}
        result["constraints"] = [item.to_dict() for item in self.constraints]
        return {"schema_version": 1, **result}

    @classmethod
    def from_dict(cls, value: Any) -> ExecutionBudget:
        fields = dict(_fields(value, set(cls.__dataclass_fields__)))
        del fields["schema_version"]
        if type(fields["constraints"]) is not list:
            raise ValueError("constraints must be a JSON list")
        fields["constraints"] = tuple(DeadlineConstraint.from_dict(item) for item in fields["constraints"])
        return cls(**fields)


@dataclass(frozen=True, slots=True)
class BudgetEnvelope:
    constraints: tuple[DeadlineConstraint, ...]
    checkpoint: ClockCheckpoint
    started_at: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraints", _constraints(self.constraints))
        if type(self.checkpoint) is not ClockCheckpoint:
            raise ValueError("checkpoint must be a ClockCheckpoint")
        if self.started_at is not None:
            object.__setattr__(self, "started_at", _number(self.started_at, "started_at"))

    def view(self, *, sample: ClockCheckpoint | None = None) -> ExecutionBudget:
        current = sample_clock() if sample is None else sample
        now = self.checkpoint.effective_time(current)
        work = min(self.constraints, key=lambda item: item.work_deadline_at, default=None)
        hard = min(self.constraints, key=lambda item: item.deadline_at, default=None)
        return ExecutionBudget(
            self.started_at, self.constraints, now,
            None if work is None else work.work_deadline_at,
            None if hard is None else hard.deadline_at,
            None if work is None else work.source, None if hard is None else hard.source,
            None if now is None or work is None else max(0.0, work.work_deadline_at - now),
            None if now is None or hard is None else max(0.0, hard.deadline_at - now),
            "unknown" if now is None else "trusted",
            "clock_domain_continuity_unproven" if now is None else None,
        )

    def recheckpoint(self, *, sample: ClockCheckpoint | None = None) -> BudgetEnvelope:
        current = sample_clock() if sample is None else sample
        effective = self.checkpoint.effective_time(current)
        if effective is None:
            raise BudgetClockUnknownError("clock domain continuity cannot be established")
        return replace(self, checkpoint=replace(current, wall_at=effective))

    def enter_handler(self, timeout_seconds: float, *, origin_id: str,
                      reserve_seconds: float = 0.0,
                      sample: ClockCheckpoint | None = None) -> BudgetEnvelope:
        current = sample_clock() if sample is None else sample
        resumed = self.recheckpoint(sample=current)
        timeout = _number(timeout_seconds, "timeout_seconds", positive=True)
        reserve_seconds = _number(reserve_seconds, "reserve_seconds")
        _identifier(origin_id, "origin_id")
        existing = next((item for item in self.constraints if item.origin_id == origin_id), None)
        if existing is not None:
            if existing.source != "execution" or existing.reserve_seconds != reserve_seconds:
                raise ValueError("handler origin conflicts with inherited constraint")
            # A retry enters again, but never receives a new original deadline.
            return replace(resumed, started_at=resumed.checkpoint.wall_at)
        constraint = DeadlineConstraint(origin_id, "execution", resumed.checkpoint.wall_at + timeout,
                                        reserve_seconds)
        return replace(resumed, constraints=(*resumed.constraints, constraint),
                       started_at=resumed.checkpoint.wall_at)

    def with_started_at(self, started_at: float | None) -> BudgetEnvelope:
        """Attach an independently captured handler-entry timestamp."""
        return replace(self, started_at=started_at)

    def derive(self, *, source: str, origin_id: str, timeout_seconds: float | None = None,
               deadline_at: float | None = None, reserve_seconds: float = 0.0,
               sample: ClockCheckpoint | None = None) -> BudgetEnvelope:
        """Add one local constraint while inheriting already-reserved bounds."""
        if (timeout_seconds is None) == (deadline_at is None):
            raise ValueError("provide exactly one of timeout_seconds and deadline_at")
        resumed = self.recheckpoint(sample=sample)
        if timeout_seconds is not None:
            deadline_at = resumed.checkpoint.wall_at + _number(timeout_seconds, "timeout_seconds", positive=True)
        assert deadline_at is not None
        constraint = DeadlineConstraint(origin_id, source, deadline_at, reserve_seconds)
        return replace(resumed, constraints=_constraints((*resumed.constraints, constraint)))

    def deadline_monotonic(self, *, hard: bool = False,
                           sample: ClockCheckpoint | None = None) -> float | None:
        """Map a trusted remaining bound into the caller's local timer domain.

        Suspend-inclusive providers should be resampled on wake; old local
        ``time.monotonic`` values are not persistent clock checkpoints.
        """
        local = time.monotonic()
        view = self.view(sample=sample)
        if view.clock_status == "unknown":
            raise BudgetClockUnknownError(view.unknown_reason)
        remaining = view.remaining_hard_seconds if hard else view.remaining_work_seconds
        return None if remaining is None else local + remaining

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "constraints": [item.to_dict() for item in self.constraints],
                "checkpoint": self.checkpoint.to_dict(), "started_at": self.started_at}

    @classmethod
    def from_dict(cls, value: Any) -> BudgetEnvelope:
        fields = _fields(value, {"constraints", "checkpoint", "started_at"})
        if type(fields["constraints"]) is not list:
            raise ValueError("constraints must be a JSON list")
        return cls(tuple(DeadlineConstraint.from_dict(item) for item in fields["constraints"]),
                   ClockCheckpoint.from_dict(fields["checkpoint"]), fields["started_at"])
