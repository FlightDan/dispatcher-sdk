"""Explicit execution state matrix and pure reducer."""

from __future__ import annotations

from typing import Mapping

from .errors import InvalidStateTransitionError


EXECUTION_STATES = frozenset(
    {
        "queued",
        "leased",
        "running",
        "succeeded",
        "failed",
        "timed_out",
        "cancelled",
        "dead",
        "recovery_required",
    }
)
TERMINAL_STATES = frozenset(
    {"succeeded", "failed", "timed_out", "cancelled", "dead"}
)

TRANSITION_MATRIX: Mapping[str, frozenset[str]] = {
    "queued": frozenset({"leased", "cancelled", "dead", "recovery_required"}),
    "leased": frozenset(
        {"running", "queued", "cancelled", "dead", "recovery_required"}
    ),
    "running": frozenset(
        {
            "queued",
            "succeeded",
            "failed",
            "timed_out",
            "cancelled",
            "dead",
            "recovery_required",
        }
    ),
    "recovery_required": frozenset({"queued", "cancelled"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "timed_out": frozenset(),
    "cancelled": frozenset(),
    "dead": frozenset(),
}

EVENT_TARGETS = {
    "lease": "leased",
    "start": "running",
    "retry": "queued",
    "lease_expired": "queued",
    "succeed": "succeeded",
    "fail": "failed",
    "timeout": "timed_out",
    "cancel": "cancelled",
    "dead_letter": "dead",
    "require_recovery": "recovery_required",
    "recovery_resolved": "queued",
}


def reduce_state(
    current_state: str,
    event: str,
    *,
    execution_id: str = "unknown",
    revision: int | None = None,
    lease_id: str | None = None,
    fence: int | None = None,
) -> str:
    requested = EVENT_TARGETS.get(event, event)
    if current_state not in EXECUTION_STATES or requested not in TRANSITION_MATRIX.get(
        current_state, frozenset()
    ):
        raise InvalidStateTransitionError(
            execution_id,
            current_state,
            requested,
            revision=revision,
            lease_id=lease_id,
            fence=fence,
            reason=f"event={event!r}",
        )
    return requested


def can_transition(current_state: str, requested_state: str) -> bool:
    return requested_state in TRANSITION_MATRIX.get(current_state, frozenset())
