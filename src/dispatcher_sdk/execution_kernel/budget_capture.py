"""Live ownership of guarded budget observations and factual publication."""
from __future__ import annotations

import threading
import time
from typing import Any

from .._sqlite_errors import is_sqlite_contention
from .budget import BudgetClockUnknownError, BudgetEnvelope


class _KernelBudgetCapture:
    """Keep one exact fact alive independently of its original call window."""

    def __init__(self, kernel: Any, execution_id: str) -> None:
        self.kernel, self.execution_id = kernel, execution_id
        self._lock = threading.RLock()
        self._pending: tuple[str, BudgetEnvelope | None] | None = None
        self._error: BaseException | None = None
        self._published: BudgetEnvelope | None = None
        self._ack_token: str | None = None

    def _armed(self, token: str) -> None:
        self._published = None
        self._ack_token = None
        self._pending = (token, None)

    def _captured(self, token: str, envelope: BudgetEnvelope) -> None:
        self._pending = (token, envelope)

    def _acknowledged(self, token: str, envelope: BudgetEnvelope) -> None:
        if self._pending is not None and self._pending[0] == token:
            self._published = envelope
            self._pending = self._error = self._ack_token = None

    def finish_pending(self, envelope: BudgetEnvelope, *, timeout_seconds: float) -> BudgetEnvelope:
        """Only publish the retained fact; never start another observation."""
        return self._run(envelope, timeout_seconds=timeout_seconds, finish_only=True)

    def __call__(self, envelope: BudgetEnvelope, *, timeout_seconds: float) -> BudgetEnvelope:
        return self._run(envelope, timeout_seconds=timeout_seconds, finish_only=False)

    def _run(self, envelope: BudgetEnvelope, *, timeout_seconds: float,
             finish_only: bool) -> BudgetEnvelope:
        deadline = time.monotonic() + timeout_seconds
        if not self._lock.acquire(timeout=max(0., deadline-time.monotonic())):
            raise TimeoutError("budget capture owner admission timed out")
        try:
            while True:
                if finish_only and self._pending is None:
                    return (envelope if self._published is None else
                            envelope.with_clock_floor(self._published.checkpoint))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if self._error is not None:
                        raise self._error
                    raise TimeoutError("budget capture exhausted its original native window")
                try:
                    options = {"timeout_seconds": remaining}
                    if hasattr(self.kernel, "_budget_sample_owners"):
                        options["_owner"] = self
                    if self._pending is None:
                        published = self.kernel._sample_budget(self.execution_id, envelope, **options)
                        self._error = None
                        return published
                    token, captured = self._pending
                    if captured is None:
                        if self._error is not None:
                            raise self._error
                        raise BudgetClockUnknownError("budget_clock_sample_unresolved:sampling")
                    published = self.kernel._finish_budget_sample(
                        token, self.execution_id, captured, **options)
                    self._acknowledged(token, published)
                    return envelope.with_clock_floor(published.checkpoint)
                except BaseException as exc:
                    token = getattr(exc, "budget_sample_token", None)
                    captured = getattr(exc, "budget_sample_envelope", None)
                    # Commit acknowledgement may already have retired the owner.
                    if token is not None and self._published is None:
                        self._pending = (token, captured)
                    if self._pending is not None:
                        exc.budget_sample_token, exc.budget_sample_envelope = self._pending
                        exc.budget_sample_owner = self
                    self._error = exc
                    transient = ((isinstance(exc, Exception) and is_sqlite_contention(exc))
                                 or isinstance(exc, TimeoutError))
                    remaining = deadline - time.monotonic()
                    if (not transient or self._pending is None or self._pending[1] is None
                            or remaining <= 0):
                        raise
                    time.sleep(min(.005, remaining))
        finally:
            self._lock.release()
