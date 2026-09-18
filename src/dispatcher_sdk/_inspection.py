"""Shared, read-only inspection budgets and progress observations."""

from __future__ import annotations

import math
import sqlite3
import time
from typing import Any, Callable


ProgressCallback = Callable[[dict[str, Any]], None]


class InspectionBudgetExceeded(RuntimeError):
    """Raised internally when an inspection's wall-clock budget is exhausted."""


class ProgressCallbackError(RuntimeError):
    """A caller's progress callback failed."""


class InspectionBudget:
    """One wall-clock budget shared by SQLite and Python inspection work.

    SQLite's progress handler exposes VM instruction intervals, not total work,
    so emitted events deliberately contain phases and elapsed time but no
    fabricated completion percentage.
    """

    def __init__(self, timeout_seconds: float | None, progress: ProgressCallback | None) -> None:
        if timeout_seconds is not None:
            if (type(timeout_seconds) not in (int, float)
                    or not math.isfinite(timeout_seconds) or timeout_seconds < 0):
                raise ValueError("timeout_seconds must be finite and nonnegative")
        if progress is not None and not callable(progress):
            raise TypeError("progress must be callable or None")
        self.timeout_seconds = None if timeout_seconds is None else float(timeout_seconds)
        self.progress = progress
        self.started = time.monotonic()
        self.deadline = None if timeout_seconds is None else self.started + float(timeout_seconds)
        self.stopped_reason: str | None = None

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started)

    @property
    def sqlite_timeout_seconds(self) -> float:
        """Bound SQLite lock waiting by the remaining wall-clock budget."""
        if self.deadline is None:
            return 30.0
        return max(0.001, self.deadline - time.monotonic())

    def expired(self) -> bool:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.stopped_reason = "timeout"
            return True
        return False

    def check(self) -> None:
        if self.expired():
            raise InspectionBudgetExceeded("inspection timeout exceeded")

    def emit(self, phase: str, status: str, **details: Any) -> None:
        if self.progress is not None:
            try:
                self.progress({
                    "phase": phase,
                    "status": status,
                    "elapsed_seconds": self.elapsed_seconds,
                    **details,
                })
            except Exception as error:
                raise ProgressCallbackError("inspection progress callback failed") from error

    def install(self, connection: sqlite3.Connection) -> None:
        if self.deadline is not None:
            connection.set_progress_handler(lambda: 1 if self.expired() else 0, 1_000)

    @staticmethod
    def clear(connection: sqlite3.Connection) -> None:
        connection.set_progress_handler(None, 0)

    def interrupted(self, error: sqlite3.Error) -> bool:
        return self.expired() or (
            self.stopped_reason == "timeout" and "interrupt" in str(error).lower())


__all__ = ["InspectionBudget", "InspectionBudgetExceeded", "ProgressCallback", "ProgressCallbackError"]
