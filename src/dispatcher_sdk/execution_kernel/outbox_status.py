"""Typed operational projection for the terminal-result outbox."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class ResultOutboxStatusV2:
    pending: int
    delivering: int
    dead: int
    oldest_pending_at: float | None

    def __post_init__(self) -> None:
        for name in ("pending", "delivering", "dead"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        value = self.oldest_pending_at
        if value is not None:
            if type(value) not in {int, float} or not math.isfinite(float(value)):
                raise ValueError("oldest_pending_at must be finite or null")
            if float(value) < 0:
                raise ValueError("oldest_pending_at must be non-negative")
            object.__setattr__(self, "oldest_pending_at", float(value))


__all__ = ("ResultOutboxStatusV2",)
