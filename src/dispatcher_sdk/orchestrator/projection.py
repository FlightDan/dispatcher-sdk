"""At-least-once, synchronous event projection over existing subscription CAS.

One subscription belongs to one logical consumer. Application transactions must
commit both deduplication and effects before returning success. No cross-store
atomicity, consumer lease, automatic poison skipping, or callback cancellation
is provided here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import inspect
import math
import threading
import time
from typing import Any, Callable, Literal, Protocol

from .contracts import RevisionConflict, digest, identifier
from .types import Observation, RunEvent, RunSnapshot

ProjectionDisposition = Literal["persisted", "already_present"]
ProjectionStatus = Literal["completed", "blocked", "interrupted", "conflict"]


class ProjectionSource(Protocol):
    def observe(self, run_id: str, *, subscription: str, limit: int = 100) -> Observation: ...

    def acknowledge_events(self, run_id: str, *, command_id: str, expected_revision: int,
                           subscription: str, expected_cursor: int, advance_to: int) -> RunSnapshot: ...


@dataclass(frozen=True)
class ProjectionEventIdentity:
    source_id: str
    run_id: str
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectionFailure:
    stage: Literal["callback", "acknowledge", "observe"]
    reason: str
    event: ProjectionEventIdentity | None = None
    error_type: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ProjectionDrainReport:
    source_id: str
    run_id: str
    subscription: str
    status: ProjectionStatus
    target: int | None
    acknowledged_cursor: int | None
    processed: int
    replayed: int
    acknowledged_pages: int
    conflicts: int
    failure: ProjectionFailure | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectionConsumer:
    """Persist events individually and acknowledge only complete pages.

    ``processed`` counts successful callback invocations, including replays;
    ``replayed`` counts ``already_present`` responses. Counts belong to this
    drain invocation. ``acknowledged_cursor`` is the last confirmed position;
    an ACK transport failure may leave a newer position committed in storage.
    Reinvoke drain to retry a blocked page; no event is automatically skipped.
    """

    def __init__(self, source: ProjectionSource, *, source_id: str, subscription: str,
                 page_size: int = 100, max_conflict_retries: int = 3,
                 max_ack_retries: int = 2) -> None:
        identifier(source_id, "source_id")
        identifier(subscription, "subscription")
        for name, value, minimum in (("page_size", page_size, 1),
                                     ("max_conflict_retries", max_conflict_retries, 0),
                                     ("max_ack_retries", max_ack_retries, 0)):
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if page_size > 10000:
            raise ValueError("page_size must be <= 10000")
        self.source = source
        self.source_id = source_id
        self.subscription = subscription
        self.page_size = page_size
        self.max_conflict_retries = max_conflict_retries
        self.max_ack_retries = max_ack_retries
        self._draining = threading.Lock()

    def drain(self, run_id: str,
              persist: Callable[[ProjectionEventIdentity, RunEvent], ProjectionDisposition], *,
              target: int | None = None, timeout_seconds: float | None = None,
              should_stop: Callable[[], bool] | None = None) -> ProjectionDrainReport:
        """Drain to the initial high watermark (or a specified lower boundary).

        Numeric target boundaries may fall in sequence holes. Stop/time budgets
        are checked at callback boundaries and before ACK attempts. A synchronous
        callback owns its I/O timeout and is never forcibly interrupted. A fresh
        subscription replays historical events without resetting an existing one.
        """
        identifier(run_id, "run_id")
        if not callable(persist):
            raise TypeError("persist must be callable")
        if target is not None and (type(target) is not int or target < 0):
            raise ValueError("target must be a nonnegative integer")
        if timeout_seconds is not None and (type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds) or timeout_seconds < 0):
            raise ValueError("timeout_seconds must be finite and nonnegative")
        if should_stop is not None and not callable(should_stop):
            raise TypeError("should_stop must be callable")
        if not self._draining.acquire(blocking=False):
            raise RuntimeError("ProjectionConsumer already has an active drain")
        try:
            return self._drain(run_id, persist, target, timeout_seconds, should_stop)
        finally:
            self._draining.release()

    def _drain(self, run_id: str,
               persist: Callable[[ProjectionEventIdentity, RunEvent], ProjectionDisposition],
               target: int | None, timeout_seconds: float | None,
               should_stop: Callable[[], bool] | None) -> ProjectionDrainReport:
        started = time.monotonic()
        cursor: int | None = None
        processed = replayed = pages = conflicts = 0

        def interrupted() -> bool:
            return ((should_stop is not None and should_stop()) or
                    (timeout_seconds is not None and time.monotonic() - started >= timeout_seconds))

        def report(status: ProjectionStatus, failure: ProjectionFailure | None = None) -> ProjectionDrainReport:
            return ProjectionDrainReport(self.source_id, run_id, self.subscription, status,
                                         target, cursor, processed, replayed, pages, conflicts, failure)

        while True:
            if interrupted():
                return report("interrupted")
            try:
                observation = self.source.observe(run_id, subscription=self.subscription, limit=self.page_size)
            except Exception as exc:
                return report("blocked", ProjectionFailure("observe", "observe_failed",
                              error_type=type(exc).__name__, message=str(exc)))
            cursor = observation["cursor"]
            if target is None:
                target = observation["event_high_watermark"]
            elif target > observation["event_high_watermark"]:
                raise ValueError("target exceeds observed event high watermark")
            events = [event for event in observation["events"] if event["sequence"] <= target]
            if cursor >= target or not events:
                return report("completed")
            for event in events:
                identity = ProjectionEventIdentity(self.source_id, run_id, event["sequence"])
                if interrupted():
                    return report("interrupted")
                try:
                    disposition = persist(identity, deepcopy(event))
                    if inspect.isawaitable(disposition):
                        if inspect.iscoroutine(disposition):
                            disposition.close()
                        return report("blocked", ProjectionFailure("callback", "async_callback", identity))
                    if type(disposition) is not str or disposition not in ("persisted", "already_present"):
                        return report("blocked", ProjectionFailure("callback", "invalid_confirmation", identity))
                except Exception as exc:
                    return report("blocked", ProjectionFailure("callback", "callback_failed", identity,
                                  type(exc).__name__, str(exc)))
                processed += 1
                replayed += disposition == "already_present"
                if interrupted():
                    return report("interrupted")
            advance_to = events[-1]["sequence"]
            # All request arguments participate in this deterministic identity.
            # Lost responses, including process restarts, never reuse an ID with
            # a different revision/cursor pair.
            request = dict(expected_revision=observation["snapshot"]["revision"],
                           subscription=self.subscription, expected_cursor=cursor, advance_to=advance_to)
            command_id = "projection:" + digest({"source_id": self.source_id, "run_id": run_id, **request})
            for attempt in range(self.max_ack_retries + 1):
                if interrupted():
                    return report("interrupted")
                try:
                    self.source.acknowledge_events(
                        run_id, command_id=command_id,
                        expected_revision=observation["snapshot"]["revision"],
                        subscription=self.subscription, expected_cursor=cursor, advance_to=advance_to)
                except RevisionConflict as exc:
                    conflicts += 1
                    if conflicts > self.max_conflict_retries:
                        return report("conflict", ProjectionFailure("acknowledge", "cas_conflict", identity,
                                      type(exc).__name__, str(exc)))
                    break  # Reobserve and replay; never force a cursor forward.
                except Exception as exc:
                    if attempt == self.max_ack_retries:
                        return report("blocked", ProjectionFailure("acknowledge", "ack_failed", identity,
                                      type(exc).__name__, str(exc)))
                else:
                    cursor = advance_to
                    pages += 1
                    if cursor >= target:
                        return report("completed")
                    break


__all__ = ["ProjectionConsumer", "ProjectionSource", "ProjectionDisposition", "ProjectionStatus",
           "ProjectionEventIdentity", "ProjectionFailure", "ProjectionDrainReport"]
