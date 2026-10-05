"""POSIX handler isolation supervised outside the handler process.

The supervisor owns the deadline and, on Linux, acts as a child subreaper so
double-forked descendants cannot escape cleanup by changing process groups or
sessions.  A handler never receives the parent result channel and cannot
cancel or replace the supervisor's timer.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, replace
import json
import math
import multiprocessing
import os
import pickle
import signal
import sqlite3
import sys
import threading
import time
import traceback
from typing import Any, Callable, Mapping, Optional

from .._sqlite_errors import is_sqlite_contention
from .context import HandlerContext, HandlerEffects
from .budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from .budget_capture import _KernelBudgetCapture
from .completion_clock import capture_completion_time
from .contracts import ExecutionCommandV2, ExecutionLease
from .errors import EffectRecoveryRequiredError, HandlerExecutionError
from ._registry import Handler
from .sqlite import SQLiteKernel


_PR_SET_CHILD_SUBREAPER = 36
# Linux wait.h: include clone children whose exit signal is not SIGCHLD.
_WAIT_ALL = 0x40000000
_CLEANUP_GRACE_SECONDS = 1.0
_TREE_QUIET_SECONDS = 0.05


class _DeadlineExpired(BaseException):
    """Private control-flow exception raised only in the supervisor."""


class _SerializedHandler:
    """Defer user deserialization while retaining multiprocessing reducers.

    Reduction runs inside Process.start's spawning context, so supported
    multiprocessing handles keep their existing transfer semantics. The
    supervisor receives only bytes; the contained worker decodes them.
    """
    def __init__(self, handler: Handler) -> None:
        self.handler = handler

    def __reduce__(self):
        return bytes, (bytes(multiprocessing.reduction.ForkingPickler.dumps(self.handler, 4)),)


def _send_packet(sender: Any, packet: Mapping[str, Any]) -> None:
    sender.send_bytes(
        json.dumps(
            packet,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _receive_packet(receiver: Any) -> Optional[dict[str, Any]]:
    try:
        value = json.loads(receiver.recv_bytes().decode("utf-8"))
    except (EOFError, OSError, UnicodeError, ValueError):
        return None
    return value if type(value) is dict else None


def _bootstrap_diagnostic(error: BaseException, stage: str) -> dict[str, Any]:
    """Bound raw worker failure diagnostics without granting entry authority."""
    try:
        raw_message = str(error).encode("utf-8", errors="replace")
    except BaseException as formatting_error:
        raw_message = f"{type(error).__name__} (message unavailable: {type(formatting_error).__name__})".encode()
    limit = 16 * 1024
    parts = []
    used = 0
    truncated = False
    formatted = traceback.TracebackException.from_exception(error, limit=20, capture_locals=False)
    for part in formatted.format():
        raw = part.encode("utf-8", errors="replace")
        remaining = limit - used
        parts.append(raw[:remaining])
        used += min(len(raw), remaining)
        if len(raw) > remaining:
            truncated = True
            break
    return {"exception_type": type(error).__name__,
        "message": raw_message[:4096].decode("utf-8", errors="ignore"),
        "message_truncated": len(raw_message) > 4096,
        "traceback": b"".join(parts).decode("utf-8", errors="ignore"),
        "traceback_truncated": truncated, "stage": stage,
        "worker_pid": os.getpid(), "observed_at": time.time()}


def _observe_phase(callback: Callable[[str, dict[str, Any]], None] | None,
                   phase: str, details: dict[str, Any]) -> None:
    if callback is not None:
        try:
            callback(phase, details)
        except BaseException:
            pass


def _serialize_handler_outcome(
    outcome: dict[str, Any], effects: HandlerEffects
) -> str:
    try:
        return json.dumps(
            outcome,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except BaseException as exc:
        return json.dumps(
            {
                "kind": "error",
                "code": "invalid_handler_result",
                "message": f"handler result is not strict JSON: {exc}",
                "retryable": False,
                "details": {"exception_type": type(exc).__name__},
                "effect_ids": effects.effect_ids,
                "budget_envelope": outcome.get("budget_envelope"),
                "started_at": outcome.get("started_at"),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def invoke_handler(
    handler: Handler,
    command: ExecutionCommandV2,
    context: HandlerContext,
    *,
    on_entered: Optional[Callable[[HandlerContext], None]] = None,
) -> dict[str, Any]:
    """Normalize one handler call for both process and thread runtimes."""
    outcome = _invoke_handler(handler, command, context, on_entered=on_entered)
    envelope = getattr(context, "_budget_envelope", None)
    if isinstance(envelope, BudgetEnvelope):
        outcome.update(budget_envelope=envelope.to_dict(), started_at=envelope.started_at)
    return outcome


def _invoke_handler(
    handler: Handler,
    command: ExecutionCommandV2,
    context: HandlerContext,
    *,
    on_entered: Optional[Callable[[HandlerContext], None]] = None,
) -> dict[str, Any]:

    entered = False
    try:
        context._enter_handler()
        entered = True
        if on_entered is not None:
            on_entered(context)
        value = handler(command.payload, context)
        return {
            "kind": "ok",
            "value": value,
            "effect_ids": context.effects.effect_ids,
        }
    except EffectRecoveryRequiredError as exc:
        return {
            "kind": "recovery_required",
            "effect_id": exc.effect_id,
            "effect_ids": context.effects.effect_ids,
        }
    except HandlerExecutionError as exc:
        outcome: dict[str, Any] = {
            "kind": "timeout" if exc.code == "execution_deadline_exhausted" else "error",
            "code": exc.code,
            "message": str(exc),
            "retryable": exc.retryable,
            "details": exc.details,
            "effect_ids": context.effects.effect_ids,
        }
        if exc.code == "execution_deadline_exhausted":
            outcome["phase"] = "execution" if entered else "entry_authority"
            if type(exc.details) is dict:
                source = exc.details.get("limiting_source")
                if type(source) is str and source in {"run", "execution", "parent", "tool"}:
                    outcome["limiting_source"] = source
                phase = exc.details.get("phase")
                if type(phase) is str and phase.strip() and len(phase) <= 128:
                    outcome["phase"] = phase
        return outcome
    except BaseException as exc:
        from .children import ChildExecutionError
        if isinstance(exc, ChildExecutionError):
            details = {"child_execution_id": exc.execution_id, "child_result": exc.result}
            if isinstance(exc.__cause__, Exception):
                details["cause"] = _control_error_details(exc.__cause__)
            return {"kind": "error", "code": exc.code, "message": str(exc), "retryable": False,
                "details": details, "effect_ids": context.effects.effect_ids}
        return {
            "kind": "error",
            "code": "handler_error",
            "message": str(exc),
            "retryable": False,
            "details": {"exception_type": type(exc).__name__},
            "effect_ids": context.effects.effect_ids,
        }


def _capture_completion_time(outcome: dict[str, Any], context: HandlerContext) -> None:
    """Retain the original logical completion fact under one control bound.

    Raw wall time can roll back below a durably observed lease expiry. The
    original result must not use that rollback as proof of timely completion.
    """
    try:
        outcome["completed_at"] = capture_completion_time(context)
        outcome["completion_time_known"] = True
    except Exception as exc:
        outcome["completion_time_known"] = False
        outcome["completion_time_error"] = f"{type(exc).__name__}: {exc}"
        proof = getattr(exc, "_completion_clock_proof", None)
        if type(proof) is dict:
            outcome["completion_clock_proof"] = proof


def _budget_sample(now: Any):
    return sample_clock(wall_time=now() if callable(now) else None)


def _elapsed_budget_sample(envelope: BudgetEnvelope):
    return sample_clock(wall_time=envelope.checkpoint.wall_at)



def _capture_budget_floor(envelope: BudgetEnvelope, capture: Any,
                          timeout_seconds: float) -> BudgetEnvelope:
    """Preserve captured authority and the causal error when publication fails."""
    try:
        return capture(envelope, timeout_seconds=timeout_seconds)
    except Exception as exc:
        if isinstance(exc, (BudgetClockUnknownError, HandlerExecutionError)):
            raise
        error = BudgetClockUnknownError(f"budget_clock_capture_failed:{type(exc).__name__}: {str(exc)[:4096]}")
        error.budget_sample_token = getattr(exc, "budget_sample_token", None)
        error.budget_sample_envelope = getattr(exc, "budget_sample_envelope", None)
        raise error from exc


def _finish_budget_capture(capture: Any, envelope: BudgetEnvelope | None,
                           *, timeout_seconds: float = .1):
    """Publish one owned fact after containment, without observing wall time."""
    pending = getattr(capture, "_pending", None)
    if pending is None:
        return envelope, {"state": "confirmed"}
    token, captured = pending
    if captured is None:
        # An interrupted arm has no fact to acknowledge. Re-entering its
        # capture would rethrow a retained native alarm and prevent the
        # supervisor from publishing even its containment/timeout receipt.
        # Keep the guard and original error; this is no new observation.
        error = getattr(capture, "_error", None)
        if error is None:
            error = BudgetClockUnknownError("budget_clock_sample_unresolved:sampling")
        return envelope, {"state": "unknown", "token": token,
            "captured_envelope": None, "error": _control_error_details(error.__cause__ or error)}
    envelope = captured if envelope is None else envelope.with_clock_floor(captured.checkpoint)
    try:
        published = capture.finish_pending(envelope, timeout_seconds=timeout_seconds)
        return published, {"state": "confirmed", "token": token}
    except Exception as error:
        return envelope, {"state": "unknown", "token": token,
            "captured_envelope": None if captured is None else captured.to_dict(),
            "error": _control_error_details(error.__cause__ or error)}


def _transient_capture_error(error: BaseException) -> bool:
    cause = error.__cause__ or error
    return (is_sqlite_contention(cause) or isinstance(cause, TimeoutError)
        or str(error) == "budget_clock_sample_unresolved:sampling")


@dataclass(frozen=True)
class _NativeBudgetCutoff:
    """An observed local cutoff, separate from an unpublished clock sample."""

    deadline_monotonic: float
    observed_monotonic: float
    hard: bool
    envelope: BudgetEnvelope

    def to_dict(self) -> dict[str, Any]:
        return {"deadline_monotonic": self.deadline_monotonic,
                "observed_monotonic": self.observed_monotonic, "hard": self.hard,
                "budget_envelope": self.envelope.to_dict()}


def _capture_budget_until(envelope: BudgetEnvelope, capture: Any, deadline: float,
                          *, hard: bool = False, on_capture: Any = None,
                          stop_retry: Any = None) -> BudgetEnvelope:
    """Retry guarded capture inside an already established native cutoff."""
    last_error = None
    while True:
        projected = envelope.recheckpoint(sample=_elapsed_budget_sample(envelope))
        bound = projected.deadline_monotonic(hard=hard, sample=projected.checkpoint)
        deadline = min(deadline, math.inf if bound is None else bound)
        observed = time.monotonic()
        remaining = deadline - observed
        if remaining <= 0:
            if last_error is not None:
                # Preserve the original token/envelope and ACK uncertainty.
                # The trusted projection and this local comparison establish
                # expiry independently of the capture error's classification.
                last_error.budget_native_cutoff = _NativeBudgetCutoff(deadline, observed, hard, projected)
                raise last_error
            return projected
        try:
            published = _capture_budget_floor(projected, capture, min(.1, remaining))
            if on_capture is not None:
                on_capture(published)
            return published
        except BudgetClockUnknownError as exc:
            captured = getattr(exc, "budget_sample_envelope", None)
            if captured is not None:
                envelope = envelope.with_clock_floor(captured.checkpoint)
                if on_capture is not None:
                    on_capture(envelope)
            if not _transient_capture_error(exc):
                raise
            # A ready original packet is a fact, not new execution authority.
            # Let its caller read it while retaining this exact refusal and
            # pending capture, instead of retrying until the business cutoff.
            if stop_retry is not None and stop_retry():
                raise
            last_error = exc
            projected = envelope.recheckpoint(sample=_elapsed_budget_sample(envelope))
            bound = projected.deadline_monotonic(hard=hard, sample=projected.checkpoint)
            deadline = min(deadline, math.inf if bound is None else bound)
            observed = time.monotonic()
            remaining = deadline - observed
            if remaining <= 0:
                exc.budget_native_cutoff = _NativeBudgetCutoff(deadline, observed, hard, projected)
                raise
            time.sleep(min(.005, remaining))


def _merge_budget_floor(base: BudgetEnvelope, observed: BudgetEnvelope) -> BudgetEnvelope:
    """Keep base authority and the strongest floor at the later elapsed sample."""
    earlier, later = sorted((base, observed), key=lambda item: item.checkpoint.elapsed_at)
    checkpoint = earlier.recheckpoint(sample=later.checkpoint).checkpoint
    return BudgetEnvelope(base.constraints, checkpoint, base.started_at)


class _BudgetTracker:
    """Retain the exact samples used by one local deadline observer."""

    def __init__(self, envelope: BudgetEnvelope | None, now: Any,
                 capture_budget: Any = None, *, guarded: bool = False) -> None:
        self.envelope, self.now = envelope, now
        self.capture_budget, self.guarded = capture_budget, guarded or capture_budget is not None
        self.capture_error: Exception | None = None
        self.on_capture: Any = None

    def _retain_capture(self, envelope: BudgetEnvelope) -> None:
        self.envelope = envelope if self.envelope is None else _merge_budget_floor(self.envelope, envelope)
        if self.on_capture is not None:
            self.on_capture(self.envelope)

    def bound(self, deadline: float, *, hard: bool = False,
              stop_retry: Any = None) -> float:
        if self.envelope is None:
            return deadline
        if self.guarded:
            self.envelope = self.envelope.recheckpoint(sample=_elapsed_budget_sample(self.envelope))
            original = self.envelope.deadline_monotonic(hard=hard, sample=self.envelope.checkpoint)
            deadline = min(deadline, math.inf if original is None else original)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return deadline
            if self.capture_budget is None:
                raise BudgetClockUnknownError("budget_clock_capture_unavailable")
            try:
                self.envelope = _capture_budget_until(
                    self.envelope, self.capture_budget, deadline, hard=hard,
                    on_capture=self._retain_capture, stop_retry=stop_retry)
                self.capture_error = None
            except Exception as exc:
                captured = getattr(exc, "budget_sample_envelope", None)
                if captured is not None:
                    self.envelope = self.envelope.with_clock_floor(captured.checkpoint)
                self.capture_error = exc
                raise
        else:
            self.envelope = self.envelope.recheckpoint(sample=_budget_sample(self.now))
        bound = self.envelope.deadline_monotonic(hard=hard, sample=self.envelope.checkpoint)
        return deadline if bound is None else min(deadline, bound)

    def entered(self, envelope: BudgetEnvelope) -> None:
        self.envelope = envelope if self.envelope is None else _merge_budget_floor(envelope, self.envelope)


def _entry_packet(context: HandlerContext, now: Any) -> dict[str, Any]:
    envelope = context.budget_envelope
    try:
        from ..observability.processes import _birth
        birth, namespace, birth_reason = _birth(os.getpid())
    except Exception:
        birth, namespace, birth_reason = None, None, "birth_identity_unavailable"
    # This packet announces the committed ACK, not another wall-clock authority
    # observation. Project native elapsed time from that same durable floor for
    # both bounds; parent/supervisor timers retain their own later observations.
    sample = sample_clock(wall_time=envelope.checkpoint.wall_at)
    return {"kind": "worker_entered", "budget_envelope": envelope.to_dict(),
            "deadline_monotonic": envelope.deadline_monotonic(sample=sample),
            "hard_deadline_monotonic": envelope.deadline_monotonic(hard=True, sample=sample),
            "started_at": envelope.started_at, "worker_pid": os.getpid(),
            "birth_identity": birth, "namespace": namespace, "birth_unknown_reason": birth_reason,
            "process_evidence": {"source": "worker_self_report", "state": "alive", "pid": os.getpid()}}


def _control_error_details(error: Exception) -> dict[str, Any]:
    """Retain the actual control error without unbounded result payloads."""
    raw = str(error).encode("utf-8", errors="replace")
    details: dict[str, Any] = {"cause": type(error).__name__,
        "error": raw[:4096].decode("utf-8", errors="ignore"),
        "error_truncated": len(raw) > 4096}
    code = getattr(error, "sqlite_errorcode", None)
    if isinstance(code, int):
        details["sqlite_errorcode"] = code
    return details


def _confirm_handler_entry(context: HandlerContext) -> None:
    """Complete the SDK's durable pending-to-confirmed entry handshake."""
    captured = context.budget_envelope
    last_error = None
    native_deadline = captured.deadline_monotonic(sample=context._sample())

    def check_budget():
        view = context.budget
        if view.clock_status != "trusted":
            raise HandlerExecutionError("budget_clock_unknown", view.unknown_reason, details=view.to_dict())
        if not view.remaining_work_seconds:
            details = view.to_dict()
            if last_error is not None:
                details["storage_error"] = _control_error_details(last_error)
            raise HandlerExecutionError("execution_deadline_exhausted",
                "execution work deadline elapsed before durable entry confirmation", details=details)
        if not context.effects._is_active():
            raise HandlerExecutionError("entry_confirmation_unknown",
                "handler entry authority was revoked before confirmation")
        return view

    while True:
        try:
            view = check_budget()
            captured = captured.recheckpoint(sample=context.budget_envelope.checkpoint)
            # Admission was already marked pending before dispatch, including
            # retry attempts. A crash at this intermediate ACK cannot authorize
            # another attempt using an unconfirmed, weaker clock floor.
            recorded = context._kernel._checkpoint_handler_entry(context.lease, captured,
                timeout_seconds=min(.1, view.remaining_work_seconds))
            with context._budget_lock:
                view = check_budget()
                latest = context.budget_envelope.checkpoint
                captured = recorded.recheckpoint(sample=latest)
                # Only this bounded storage operation holds the local budget
                # lock. A concurrent waiter cannot add a stronger observed floor
                # between capture and the final durable confirmation.
                confirmed = context._kernel.confirm_handler_entry(context.lease, captured,
                    timeout_seconds=min(.1, view.remaining_work_seconds))
                context._budget_envelope = confirmed
                context._entry_confirmed = True
                if context.children is not None:
                    context.children.budget_envelope = confirmed
            # The committed checkpoint defines the ACK boundary. Sampling wall
            # time again here would create an unconfirmed floor after final ACK.
            accepted = confirmed.view(sample=confirmed.checkpoint)
            if not accepted.remaining_work_seconds:
                raise HandlerExecutionError("execution_deadline_exhausted",
                    "execution work deadline elapsed before durable entry confirmation",
                    details=accepted.to_dict())
            return
        except HandlerExecutionError:
            raise
        except Exception as exc:
            busy = is_sqlite_contention(exc)
            control_busy = isinstance(exc, TimeoutError) and str(exc) in {
                "Kernel control lock admission timed out", "Kernel control admission budget elapsed"}
            competing_sample = (isinstance(exc, BudgetClockUnknownError)
                and str(exc) == "budget_clock_sample_unresolved:sampling")
            if busy or control_busy or competing_sample:
                last_error = exc
                retained = getattr(exc, "budget_sample_envelope", None)
                if retained is not None:
                    with context._budget_lock:
                        context._budget_envelope = context.budget_envelope.with_clock_floor(retained.checkpoint)
                # A publication retry projects the same retained floor; it
                # cannot arm a second wall observation or renew entry's timer.
                envelope = context.budget_envelope
                projected = envelope.view(sample=_elapsed_budget_sample(envelope))
                remaining = projected.remaining_work_seconds
                if native_deadline is not None:
                    remaining = min(remaining or 0, native_deadline - time.monotonic())
                if projected.clock_status != "trusted" or remaining is None or remaining <= 0:
                    details = projected.to_dict()
                    details["storage_error"] = _control_error_details(exc)
                    raise HandlerExecutionError("execution_deadline_exhausted",
                        "execution work deadline elapsed before durable entry confirmation",
                        details=details) from exc
                time.sleep(min(.01, remaining))
                continue
            code = "budget_clock_unknown" if isinstance(exc, BudgetClockUnknownError) else "entry_confirmation_unknown"
            details = _control_error_details(exc)
            raise HandlerExecutionError(code, details["error"], details=details) from exc


def _confirmed_entry_packet(context: HandlerContext, now: Any) -> dict[str, Any]:
    _confirm_handler_entry(context)
    return {**_entry_packet(context, now), "entry_confirmed": True}


def _budget_outcome(outcome: dict[str, Any], envelope: BudgetEnvelope | None,
                    entry: dict[str, Any] | None = None) -> dict[str, Any]:
    if outcome.get("code") == "execution_deadline_exhausted":
        outcome = {**outcome, "kind": "timeout", "phase": outcome.get("phase", "entry_authority")}
    if outcome.get("code") == "budget_clock_unknown":
        outcome = {**outcome, "control_error": True}
    observer = envelope
    if entry is not None:
        envelope = BudgetEnvelope.from_dict(entry["budget_envelope"])
    retained = outcome.get("budget_envelope")
    if retained is None and type(outcome.get("details")) is dict:
        original = outcome["details"].get("business_outcome")
        if type(original) is dict:
            retained = original.get("budget_envelope")
    if type(retained) is dict:
        completed = BudgetEnvelope.from_dict(retained)
        envelope = completed if envelope is None else _merge_budget_floor(envelope, completed)
    if envelope is None:
        return outcome
    if (entry is not None and type(retained) is dict
            and outcome.get("kind") in {"ok", "error"} and not outcome.get("control_error")):
        view = envelope.view(sample=envelope.checkpoint)
        if view.clock_status != "trusted":
            outcome = {**outcome, "kind": "error", "code": "budget_clock_unknown",
                "message": "execution clock continuity cannot be established", "control_error": True,
                "retryable": False, "details": {"business_outcome": outcome}}
        elif not view.remaining_work_seconds:
            outcome = {**outcome, "kind": "timeout", "code": None, "message": None,
                "limiting_source": view.limiting_source, "details": {"business_outcome": outcome}}
    # Cleanup may legitimately consume the reserve after timely business return.
    # Retain its floor for future admission without relabelling that return.
    if observer is not None:
        envelope = _merge_budget_floor(envelope, observer)
    constraint = None if envelope is None else min(
        envelope.constraints, key=lambda item: item.work_deadline_at, default=None)
    return {**outcome, "started_at": outcome.get("started_at") if entry is None else entry.get("started_at"),
            "budget_envelope": None if envelope is None else envelope.to_dict(),
            "limiting_source": outcome.get("limiting_source") if outcome.get("code") == "execution_deadline_exhausted"
                and type(outcome.get("limiting_source")) is str
                and outcome.get("limiting_source") in {"run", "execution", "parent", "tool"}
                else None if constraint is None else constraint.source}


def _wait_packet(receiver: Any, deadline: float, tracker: _BudgetTracker,
                 *, hard: bool = False) -> tuple[dict[str, Any] | None, float]:
    while True:
        # Already available factual packets do not require another clock write.
        if tracker.guarded and receiver.poll(0):
            return _receive_packet(receiver), deadline
        try:
            deadline = tracker.bound(deadline, hard=hard, stop_retry=lambda: receiver.poll(0))
        except BudgetClockUnknownError as error:
            if not _transient_capture_error(error):
                raise
            if receiver.poll(0):
                return _receive_packet(receiver), deadline
            raise
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, deadline
        if receiver.poll(min(remaining, 0.05)):
            return _receive_packet(receiver), deadline


def _close_context(context: HandlerContext | None) -> dict[str, Any]:
    if context is not None:
        try:
            receipt = context.close()
            checkpoint = receipt.get("budget_checkpoint") if type(receipt) is dict else None
            if type(checkpoint) is dict and checkpoint.get("state") != "confirmed":
                pending = getattr(context._budget_capture, "_pending", None)
                return {"state": "unknown", "reason": "owned budget checkpoint remains pending",
                    "budget_checkpoint": {**checkpoint,
                        "token": None if pending is None else pending[0],
                        "captured_envelope": None if pending is None or pending[1] is None else pending[1].to_dict()}}
            if type(receipt) is dict and (receipt.get("state") in {"unknown", "degraded", "pending"}
                    or receipt.get("pending_events", 0) or receipt.get("pending_bytes", 0)):
                return {"state": "unknown", "reason": str(receipt.get("reason") or receipt.get("unknown_reason")
                    or receipt.get("state") or "final telemetry remains pending")[:2048],
                    "receipt": {key: receipt[key] for key in ("state", "reason", "timed_out", "final_flush_persisted", "source_closed")
                                if key in receipt}}
        except BaseException as exc:
            # Collection/flush failure cannot overwrite the original outcome.
            return {"state": "unknown", "reason": f"{type(exc).__name__}: {exc}"[:2048]}
    return {"state": "confirmed"}


class _DeadlineGuard:
    """Local hard timer; neither SQLite nor telemetry is read by the alarm."""

    def __init__(self, deadline: float, envelope: BudgetEnvelope | None, now: Any,
                 capture_budget: Any = None, *, guarded: bool = False) -> None:
        self.envelope, self.now = envelope, now
        self.capture_budget, self.guarded = capture_budget, guarded or capture_budget is not None
        self.capture_error: BaseException | None = None
        # The alarm is the sole writer of this slot. Interrupted normal code
        # must never overwrite the only observation of a forward clock jump.
        self._alarm_envelope: BudgetEnvelope | None = None
        if envelope is not None:
            self.envelope = envelope.recheckpoint(sample=(
                _elapsed_budget_sample(envelope) if self.guarded else _budget_sample(now)))
        self.inherited_work_deadline = self._bound(math.inf)
        self.inherited_hard_deadline = self._bound(math.inf, hard=True)
        self.deadline = self._bound(deadline)
        self.hard_deadline = self._bound(deadline, hard=True)
        self.cleanup = False
        self.elapsed_deadline: float | None = None
        self._refresh_elapsed_limit()

    def snapshot(self) -> BudgetEnvelope | None:
        if self.envelope is None or self._alarm_envelope is None:
            return self.envelope
        return _merge_budget_floor(self.envelope, self._alarm_envelope)

    def _bound(self, deadline: float, *, hard: bool = False) -> float:
        envelope = self.snapshot()
        if envelope is None:
            return deadline
        bound = envelope.deadline_monotonic(hard=hard, sample=envelope.checkpoint)
        return deadline if bound is None else min(deadline, bound)

    def _retain_capture(self, envelope: BudgetEnvelope) -> None:
        previous = self.snapshot()
        self.envelope = envelope if previous is None else _merge_budget_floor(previous, envelope)
        self.inherited_work_deadline = self._bound(self.inherited_work_deadline)
        self.inherited_hard_deadline = self._bound(self.inherited_hard_deadline, hard=True)
        self.hard_deadline = self._bound(self.hard_deadline, hard=True)
        self.deadline = self._bound(self.deadline, hard=self.cleanup)
        self._refresh_elapsed_limit()

    def _refresh_elapsed_limit(self) -> None:
        if self.envelope is not None and self.envelope.constraints:
            anchor = self.envelope.checkpoint
            if anchor.domain_scope == "boot" and anchor.domain_id is not None and anchor.domain_id.startswith("linux-boot:"):
                self.elapsed_deadline = anchor.elapsed_at + min(
                    item.deadline_at if self.cleanup else item.work_deadline_at
                    for item in self.envelope.constraints) - anchor.wall_at

    def remaining(self, *, resample: bool = False, stop_retry: Any = None) -> float:
        if self.envelope is not None:
            envelope = self.snapshot()
            assert envelope is not None
            if resample:
                if self.guarded:
                    remaining = self.deadline - time.monotonic()
                    if remaining > 0:
                        if self.capture_budget is None:
                            raise BudgetClockUnknownError("budget_clock_capture_unavailable")
                        try:
                            envelope = _capture_budget_until(
                                envelope, self.capture_budget, self.deadline, hard=self.cleanup,
                                on_capture=self._retain_capture, stop_retry=stop_retry)
                        except BaseException as exc:
                            self.capture_error = exc
                            captured = getattr(exc, "budget_sample_envelope", None)
                            if captured is not None:
                                self._retain_capture(envelope.with_clock_floor(captured.checkpoint))
                            retained = self.snapshot()
                            if retained is not None:
                                view = retained.view(sample=retained.checkpoint)
                                exhausted = view.remaining_hard_seconds if self.cleanup else view.remaining_work_seconds
                                if exhausted == 0:
                                    raise _DeadlineExpired() from exc
                            raise
                    sample = _elapsed_budget_sample(envelope)
                else:
                    sample = _budget_sample(self.now)
            else:
                # The alarm must not reenter filesystem/codec code. Its known
                # local domain already identifies the native elapsed clock.
                anchor = envelope.checkpoint
                elapsed = (time.clock_gettime(time.CLOCK_BOOTTIME)
                    if anchor.domain_scope == "boot" and anchor.domain_id is not None
                    and anchor.domain_id.startswith("linux-boot:") else time.monotonic())
                sample = replace(anchor, wall_at=(time.time() if self.now is None and not self.guarded
                                                  else anchor.wall_at),
                                 elapsed_at=elapsed)
            observed = envelope.recheckpoint(sample=sample)
            if not resample:
                self._alarm_envelope = observed
                bound = observed.deadline_monotonic(hard=self.cleanup, sample=observed.checkpoint)
                return min(self.deadline, math.inf if bound is None else bound) - time.monotonic()
            self.envelope = observed
            self.inherited_work_deadline = self._bound(self.inherited_work_deadline)
            self.inherited_hard_deadline = self._bound(self.inherited_hard_deadline, hard=True)
            self.deadline = self._bound(self.deadline, hard=self.cleanup)
            self._refresh_elapsed_limit()
        remaining = self.deadline - time.monotonic()
        if self.elapsed_deadline is not None:
            remaining = min(remaining, self.elapsed_deadline - time.clock_gettime(time.CLOCK_BOOTTIME))
        return remaining

    def entered(self, packet: dict[str, Any]) -> None:
        entered = BudgetEnvelope.from_dict(packet["budget_envelope"])
        packet_deadline = packet.get("deadline_monotonic")
        if not isinstance(packet_deadline, (int, float)) or isinstance(packet_deadline, bool) or not math.isfinite(packet_deadline):
            raise ValueError("worker entry lacks a finite execution deadline")
        if self.envelope is not None:
            entered = BudgetEnvelope((*self.envelope.constraints, *entered.constraints),
                                     entered.checkpoint, entered.started_at)
            observed = self.snapshot()
            assert observed is not None
            entered = _merge_budget_floor(entered, observed)
        self.envelope = entered.recheckpoint(sample=(
            _elapsed_budget_sample(entered) if self.guarded else _budget_sample(self.now)))
        self.deadline = min(self.inherited_work_deadline,
                            self._bound(float(packet_deadline)))
        hard_deadline = packet.get("hard_deadline_monotonic", packet_deadline)
        if not isinstance(hard_deadline, (int, float)) or isinstance(hard_deadline, bool) or not math.isfinite(hard_deadline):
            raise ValueError("worker entry lacks a finite hard deadline")
        self.hard_deadline = min(self.inherited_hard_deadline,
                                 self._bound(float(hard_deadline), hard=True))
        self._refresh_elapsed_limit()

    def begin_cleanup(self) -> None:
        self.cleanup = True
        self.deadline = self.hard_deadline
        self._refresh_elapsed_limit()
        self.arm()

    def arm(self) -> None:
        remaining = self.remaining()
        if remaining <= 0:
            raise _DeadlineExpired()
        # A periodic wake also checks suspend-inclusive elapsed bounds.
        signal.setitimer(signal.ITIMER_REAL, min(remaining, 0.05))


def _child_process_ids(parent_pid: int) -> tuple[int, ...]:
    try:
        with open(
            f"/proc/{parent_pid}/task/{parent_pid}/children",
            "r",
            encoding="ascii",
        ) as stream:
            return tuple(int(value) for value in stream.read().split())
    except (OSError, ValueError):
        return ()


def _descendant_process_ids(root_pid: int) -> tuple[int, ...]:
    if not os.path.isdir("/proc"):
        return ()
    pending = [root_pid]
    seen = {root_pid}
    discovered: list[int] = []
    while pending:
        parent = pending.pop()
        for child in _child_process_ids(parent):
            if child in seen:
                continue
            seen.add(child)
            discovered.append(child)
            pending.append(child)
    return tuple(reversed(discovered))


def _kill_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _kill_group(process_group: int) -> None:
    try:
        os.killpg(process_group, signal.SIGKILL)
    except OSError:
        pass


def _kill_descendants(root_pid: int) -> None:
    for descendant in _descendant_process_ids(root_pid):
        _kill_pid(descendant)


def _stop_flush_descendants(root_pid: int, worker_pid: int) -> bool:
    if not (hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal")):
        return False
    for descendant in _descendant_process_ids(root_pid):
        if descendant == worker_pid:
            continue
        try:
            descriptor = os.pidfd_open(descendant)
        except ProcessLookupError:
            continue
        except OSError:
            return False
        try:
            # Re-read lineage after acquiring a lifetime-stable process
            # handle. A reused PID outside this tree must never be signalled.
            if descendant in _descendant_process_ids(root_pid):
                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            return False
        finally:
            os.close(descriptor)
    return True


def _reap_children(*, all_children: bool = False) -> bool:
    """Reap exited children; true means ECHILD, not merely none ready to reap."""

    options = os.WNOHANG | (_WAIT_ALL if all_children else 0)
    while True:
        try:
            waited, _status = os.waitpid(-1, options)
        except ChildProcessError:
            return True
        except OSError:
            return False
        if waited == 0:
            return False


def _reap_pid(pid: int) -> bool:
    """Return true once one direct child is known to have been reaped."""

    try:
        waited, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return True
    except OSError:
        return False
    return waited == pid


def _group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _contain_tree(
    root_pid: int, worker_pid: int, until: float, *, subreaper: bool = False
) -> bool:
    """Kill and reap a worker tree, including subreaper-adopted orphans."""

    if subreaper and sys.platform.startswith("linux"):
        if root_pid != os.getpid():
            raise ValueError("only the subreaper can prove its own tree is empty")
        # This single-threaded supervisor creates no more workers and keeps
        # SIGCHLD at SIG_DFL. Every surviving descendant therefore has a live
        # ancestor here, or is adopted here when that ancestor exits. ECHILD
        # proves the entire tree has gone; an empty /proc read does not.
        # Kill only our unreaped direct children: their PIDs cannot be reused
        # between this read and kill. Detached descendants become direct
        # children on subsequent passes, without using a stale process group.
        while True:
            if _reap_children(all_children=True):
                return True
            for child in _child_process_ids(root_pid):
                _kill_pid(child)
            if _reap_children(all_children=True):
                return True
            if time.monotonic() >= until:
                return False
            time.sleep(0.002)

    # Platforms without subreaper adoption retain the conservative group and
    # tree observation window; ECHILD there says nothing about escaped orphans.
    worker_reaped = False
    quiet_since: Optional[float] = None
    while True:
        _kill_group(worker_pid)
        _kill_descendants(root_pid)
        if not worker_reaped:
            worker_reaped = _reap_pid(worker_pid)
        _reap_children()
        descendants = _descendant_process_ids(root_pid)
        now = time.monotonic()
        if worker_reaped and not descendants and not _group_exists(worker_pid):
            if quiet_since is None:
                quiet_since = now
            elif now - quiet_since >= _TREE_QUIET_SECONDS:
                return True
        else:
            quiet_since = None
        if now >= until:
            return False
        time.sleep(0.002)


def _enable_linux_subreaper() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return True


def _worker_entry(
    db_path: str,
    handler: Handler | bytes,
    command: ExecutionCommandV2,
    lease: ExecutionLease,
    now: Any,
    channel: Any,
    durability: str = "full",
    budget_envelope: BudgetEnvelope | None = None,
    service_spec: dict | None = None,
) -> int:
    kernel: Optional[SQLiteKernel] = None
    effects: Optional[HandlerEffects] = None
    context: HandlerContext | None = None
    entry_announced = False
    stage = "worker_deserialization"
    try:
        os.setpgid(0, 0)
        from .resources import apply_process_memory_limit
        stage = "worker_resource_admission"
        apply_process_memory_limit((service_spec or {}).get("process_memory_limit_bytes"))
        stage = "worker_deserialization"
        if isinstance(handler, bytes):
            # Trusted invocation bytes are decoded only inside the already
            # timed/contained worker, so imports and __setstate__ can report
            # their original bootstrap failure through its private channel.
            handler = pickle.loads(handler)
        stage = "worker_setup"
        kernel = SQLiteKernel(db_path, now=now, durability=durability)
        effects = HandlerEffects(kernel, lease, lambda: True)
        context = HandlerContext(command, lease, effects,
                                 budget_envelope=budget_envelope, service_spec=service_spec)
        _send_packet(channel, {"kind": "worker_ready", "worker_pid": os.getpid(), "observed_at": time.time()})
        go = _receive_packet(channel)
        if go != {"kind": "invoke"}:
            return 70
        stage = "handler_entry"
        def announce_entry(entered: HandlerContext) -> None:
            nonlocal entry_announced, stage
            _send_packet(channel, _confirmed_entry_packet(entered, now))
            entry_announced = True
            stage = "handler_execution"

        outcome = invoke_handler(handler, command, context, on_entered=announce_entry)
        _capture_completion_time(outcome, context)
        outcome_json = _serialize_handler_outcome(outcome, effects)
        stage = "worker_finalization"
        if entry_announced:
            _send_packet(channel, {"kind": "worker_returned", "outcome_json": outcome_json,
                                   "completed_monotonic": time.monotonic()})
        receipt = _close_context(context)
        if receipt["state"] != "confirmed":
            final = json.loads(outcome_json)
            final["telemetry_flush"] = receipt
            outcome_json = json.dumps(final, allow_nan=False)
        context = None
        kernel.close()
        kernel = None
        _send_packet(
            channel,
            {"kind": "worker_completed", "outcome_json": outcome_json},
        )
        return 0
    except BaseException as exc:
        try:
            details = _bootstrap_diagnostic(exc, stage)
            _send_packet(
                channel,
                {
                    "kind": "worker_failed",
                    "exception_type": details["exception_type"],
                    "message": details["message"],
                    "details": details,
                    "effect_ids": [] if effects is None else effects.effect_ids,
                },
            )
        except BaseException:
            pass
        return 70
    finally:
        _close_context(context)
        if kernel is not None:
            try:
                kernel.close()
            except BaseException:
                pass
        channel.close()


def _supervisor_entry(
    db_path: str,
    handler: Handler | bytes,
    command: ExecutionCommandV2,
    lease: ExecutionLease,
    now: Any,
    parent_sender: Any,
    durability: str = "full",
    budget_envelope: BudgetEnvelope | None = None,
    service_spec: dict | None = None,
    startup_deadline: float | None = None,
) -> None:
    worker_pid: Optional[int] = None
    worker_channel: Any = None
    previous_alarm: Any = None
    subreaper = False
    business_outcome_json: str | None = None
    guard: _DeadlineGuard | None = None
    supervisor_kernel: SQLiteKernel | None = None
    handler_entered = False
    stage = "supervisor_setup"

    def send_parent(packet: dict[str, Any]) -> None:
        if guard is not None and packet.get("cleanup_confirmed") is True:
            # The tree is already contained. This bounded exact-token ACK
            # owns factual cleanup time, never another business allowance.
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            published, checkpoint = _finish_budget_capture(guard.capture_budget, guard.snapshot())
            if published is not None:
                guard._retain_capture(published)
            packet = {**packet, "budget_checkpoint": checkpoint}
        observed = None if guard is None else guard.snapshot()
        if observed is not None:
            packet = {**packet, "observed_budget_envelope": observed.to_dict()}
        _send_packet(parent_sender, packet)

    try:
        os.setsid()
        subreaper = _enable_linux_subreaper()
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        supervisor_channel, child_channel = multiprocessing.Pipe(duplex=True)
        worker_pid = os.fork()
        if worker_pid == 0:
            supervisor_channel.close()
            parent_sender.close()
            status = _worker_entry(
                db_path, handler, command, lease, now, child_channel, durability,
                budget_envelope, service_spec,
            )
            os._exit(status)
        child_channel.close()
        worker_channel = supervisor_channel
        guard = _DeadlineGuard(
            time.monotonic() + command.timeout_seconds if startup_deadline is None else startup_deadline,
            budget_envelope, now,
            guarded=bool((service_spec or {}).get("guard_budget")),
        )

        def expire(_signum: int, _frame: Any) -> None:
            remaining = guard.remaining()
            if remaining > 0:
                # A same-UID handler can signal its parent.  Treat SIGALRM as
                # a wake-up only; the supervisor's own monotonic deadline is
                # the authority for termination.
                signal.setitimer(signal.ITIMER_REAL, min(remaining, 0.05))
                return
            # Do not traverse /proc or kill the tree from a Python signal
            # handler.  The alarm can interrupt an in-progress containment
            # scan; re-entering codecs/filesystem code there is unsafe.  The
            # exception unwinds to the bounded cleanup block below.
            raise _DeadlineExpired()

        previous_alarm = signal.signal(signal.SIGALRM, expire)
        try:
            guard.arm()
            if guard.guarded:
                remaining = guard.remaining()
                if remaining <= 0:
                    raise _DeadlineExpired()
                # Install the independent alarm before opening SQLite. Neither
                # connection admission nor a busy sampling writer owns its timer.
                supervisor_kernel = SQLiteKernel(db_path, now=now, durability=durability,
                    control_timeout_seconds=min(.1, remaining))
                guard.capture_budget = _KernelBudgetCapture(supervisor_kernel, lease.execution_id)
                if guard.remaining(resample=True) <= 0:
                    raise _DeadlineExpired()
                guard.arm()
            ready = _receive_packet(worker_channel)
            if type(ready) is not dict or ready.get("kind") != "worker_ready":
                contained = _contain_tree(
                    os.getpid(), worker_pid, time.monotonic() + _CLEANUP_GRACE_SECONDS,
                    subreaper=subreaper,
                )
                send_parent({"kind": "handler_start_failed",
                                            "cleanup_confirmed": contained and subreaper,
                                            "message": ready.get("message", "handler worker did not become ready")
                                                if type(ready) is dict else "handler worker did not become ready",
                                            "details": ready.get("details", {}) if type(ready) is dict else {}})
                return
            send_parent(ready)
            _send_packet(worker_channel, {"kind": "invoke"})
            stage = "handler_entry"
            packet = _receive_packet(worker_channel)
            if type(packet) is dict and packet.get("kind") == "worker_entered":
                guard.entered(packet)
                handler_entered = True
                send_parent({**packet, "kind": "handler_started",
                                            "deadline_monotonic": guard.deadline,
                                            "hard_deadline_monotonic": guard.hard_deadline})
                stage = "handler_execution"
                guard.arm()
                packet = _receive_packet(worker_channel)
            elif type(packet) is dict and packet.get("kind") == "worker_completed":
                # Entry can fail before granting the callable any authority.
                contained = _contain_tree(os.getpid(), worker_pid, guard.deadline, subreaper=subreaper)
                if not contained:
                    raise _DeadlineExpired()
                send_parent({"kind": "handler_entry_failed",
                                            "cleanup_confirmed": subreaper,
                                            "outcome_json": packet.get("outcome_json")})
                return
            if (packet is None or type(packet) is not dict or
                    packet.get("kind") not in {"worker_returned", "worker_completed"} or
                    type(packet.get("outcome_json")) is not str):
                # No remaining callable can earn a successful result. Prove
                # physical containment before trying any clock publication;
                # a killed worker may leave an unresolved sampling marker.
                signal.setitimer(signal.ITIMER_REAL, 0.0)
                contained = _contain_tree(os.getpid(), worker_pid,
                    time.monotonic() + _CLEANUP_GRACE_SECONDS, subreaper=subreaper)
                send_parent({"kind": "handler_failed", "cleanup_confirmed": contained and subreaper,
                    "code": "handler_process_exit",
                    "message": ("handler process exited before reporting an outcome" if packet is None
                        else str(packet.get("message", "handler worker failed internally"))
                        if type(packet) is dict else "handler worker failed internally"),
                    "details": packet.get("details", {}) if type(packet) is dict else {}})
                return
            if (type(packet) is dict and packet.get("kind") == "worker_returned"
                    and type(packet.get("outcome_json")) is str):
                # Retain factual return before a separate clock publication
                # can fail. Deadline validation below still owns acceptance.
                business_outcome_json = packet["outcome_json"]
            if guard.remaining(resample=True) <= 0:
                raise _DeadlineExpired()
            if type(packet) is dict and packet.get("kind") == "worker_returned":
                completed = packet.get("completed_monotonic")
                if (type(completed) not in {int, float} or not math.isfinite(completed)
                        or completed >= guard.deadline or type(packet.get("outcome_json")) is not str):
                    raise _DeadlineExpired()
                business_outcome_json = packet["outcome_json"]
            guard.begin_cleanup()
            stage = "worker_finalization"
            deadline = guard.deadline
            if type(packet) is dict and packet.get("kind") == "worker_returned":
                send_parent({"kind": "handler_returned"})
                # The worker's bounded final telemetry flush can continue,
                # while its detached descendants lose execution authority as
                # soon as the callable has returned. The final containment
                # below still proves the complete tree has been reaped.
                while True:
                    if not _stop_flush_descendants(os.getpid(), worker_pid):
                        original = json.loads(business_outcome_json)
                        original["telemetry_flush"] = {"state": "unknown",
                            "reason": "lifetime-safe descendant containment is unavailable"}
                        business_outcome_json = json.dumps(original, allow_nan=False)
                        packet = None
                        break
                    if worker_channel.poll(0):
                        packet = _receive_packet(worker_channel)
                        break
                    try:
                        if guard.remaining(resample=True,
                                stop_retry=lambda: worker_channel.poll(0)) <= 0:
                            raise _DeadlineExpired()
                    except BudgetClockUnknownError as error:
                        if not _transient_capture_error(error):
                            raise
                        if not worker_channel.poll(0):
                            raise
                        packet = _receive_packet(worker_channel)
                        break
                    if worker_channel.poll(.01):
                        packet = _receive_packet(worker_channel)
                        break
                # Flush/storage-close failures cannot replace a serialized
                # outcome already observed within the work deadline.
                original = json.loads(business_outcome_json)
                if type(packet) is dict and packet.get("kind") == "worker_completed":
                    try:
                        final = json.loads(packet["outcome_json"])
                        if type(final.get("telemetry_flush")) is dict:
                            original["telemetry_flush"] = final["telemetry_flush"]
                    except (KeyError, ValueError, AttributeError):
                        original["telemetry_flush"] = {"state": "unknown", "reason": "worker final flush receipt is invalid"}
                elif "telemetry_flush" not in original:
                    original["telemetry_flush"] = {"state": "unknown", "reason": "worker final flush receipt is unavailable"}
                packet = {"kind": "worker_completed", "outcome_json": json.dumps(original, allow_nan=False)}
            if packet is None:
                contained = _contain_tree(os.getpid(), worker_pid, deadline, subreaper=subreaper)
                if not contained:
                    raise _DeadlineExpired()
                send_parent(
                    {
                        "kind": "handler_failed",
                        "cleanup_confirmed": subreaper,
                        "code": "handler_process_exit",
                        "message": "handler process exited before reporting an outcome",
                    },
                )
                return
            if (
                packet.get("kind") != "worker_completed"
                or type(packet.get("outcome_json")) is not str
            ):
                contained = _contain_tree(os.getpid(), worker_pid, deadline, subreaper=subreaper)
                if not contained:
                    raise _DeadlineExpired()
                send_parent(
                    {
                        "kind": "handler_failed",
                        "cleanup_confirmed": subreaper,
                        "code": "handler_process_exit",
                        "message": str(
                            packet.get("message", "handler worker failed internally")
                        ),
                        "details": packet.get("details", {}),
                    },
                )
                return
            if not _contain_tree(os.getpid(), worker_pid, deadline, subreaper=subreaper):
                raise _DeadlineExpired()
            contained_at = time.monotonic()
            if contained_at >= deadline:
                raise _DeadlineExpired()
            send_parent(
                {
                    "kind": "handler_completed",
                    "cleanup_confirmed": subreaper,
                    "contained_monotonic": contained_at,
                    "outcome_json": packet["outcome_json"],
                },
            )
        except _DeadlineExpired:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            # Collect only packets already written by the original worker.
            # Expiry grants no wait or additional invocation time.
            for _ in range(4):
                if not worker_channel.poll(0):
                    break
                available = _receive_packet(worker_channel)
                if (type(available) is dict and available.get("kind") in
                        {"worker_returned", "worker_completed"}
                        and type(available.get("outcome_json")) is str):
                    business_outcome_json = available["outcome_json"]
            expired_budget = guard.snapshot()
            work_budget_expired = (expired_budget is not None and
                expired_budget.view(sample=expired_budget.checkpoint).remaining_work_seconds == 0)
            contained = _contain_tree(
                os.getpid(), worker_pid, time.monotonic() + _CLEANUP_GRACE_SECONDS,
                subreaper=subreaper,
            )
            send_parent({"kind": "handler_timed_out", "cleanup_confirmed": contained and subreaper,
                                       "work_budget_expired": work_budget_expired,
                                       "business_outcome_json": business_outcome_json,
                                       "budget_capture_error": None if guard.capture_error is None else
                                           _control_error_details(guard.capture_error.__cause__ or guard.capture_error)})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            if previous_alarm is not None:
                signal.signal(signal.SIGALRM, previous_alarm)
    except BaseException as exc:
        contained = worker_pid is None
        if worker_pid is not None:
            contained = _contain_tree(
                os.getpid(), worker_pid, time.monotonic() + _CLEANUP_GRACE_SECONDS,
                subreaper=subreaper,
            )
        try:
            details = _bootstrap_diagnostic(exc, stage)
            send_parent(
                {
                    "kind": "handler_failed" if handler_entered else "handler_start_failed",
                    "cleanup_confirmed": contained and subreaper,
                    "message": details["message"],
                    "details": details,
                    "code": "budget_clock_unknown" if isinstance(exc, BudgetClockUnknownError)
                        else "handler_process_start_failure",
                    "control_error": isinstance(exc, BudgetClockUnknownError),
                    "business_outcome_json": business_outcome_json,
                },
            )
        except BaseException:
            pass
    finally:
        if supervisor_kernel is not None:
            supervisor_kernel.close()
        if worker_channel is not None:
            worker_channel.close()
        parent_sender.close()


def _kill_supervisor(process: multiprocessing.Process, *, wait_for_receipt: bool = False) -> bool:
    # Keep the Linux subreaper alive while its worker is being killed.  A
    # worker can be inside clone/exec when cancellation arrives; killing the
    # supervisor immediately would let a just-created, detached descendant be
    # reparented outside the containment tree.
    until = time.monotonic() + _CLEANUP_GRACE_SECONDS
    quiet_since: Optional[float] = None
    while process.is_alive() and time.monotonic() < until:
        _kill_descendants(process.pid)
        descendants = _descendant_process_ids(process.pid)
        now = time.monotonic()
        if not descendants:
            if quiet_since is None:
                quiet_since = now
            elif not wait_for_receipt and now - quiet_since >= _TREE_QUIET_SECONDS:
                break
        else:
            quiet_since = None
        time.sleep(0.002)
    # is_alive() can reap the supervisor. Its numeric PID is no longer an
    # identity after that point and must not be used to look up or kill a group.
    if not process.is_alive():
        process.join()
        return True
    try:
        process_group = os.getpgid(process.pid)
    except (OSError, TypeError):
        process_group = None
    try:
        if process_group == process.pid:
            _kill_group(process_group)
        elif process.is_alive():
            process.kill()
    except (OSError, AttributeError):
        pass
    process.join(_CLEANUP_GRACE_SECONDS)
    return not process.is_alive()


class ProcessSupervisorHandle:
    """Thread-safe revocation handle owned by one runtime invocation."""

    def __init__(self, process: multiprocessing.Process) -> None:
        self._process = process
        self._lock = threading.RLock()
        self._revocation_reason: Optional[str] = None

    @property
    def revocation_reason(self) -> Optional[str]:
        with self._lock:
            return self._revocation_reason

    def revoke(self, reason: str) -> bool:
        with self._lock:
            if self._revocation_reason is None:
                self._revocation_reason = reason
            # The same one-second grace also belongs to the supervisor's
            # explicit containment packet and bounded finish-only ACK.
            return _kill_supervisor(self._process, wait_for_receipt=True)

    def terminate(self) -> bool:
        with self._lock:
            return _kill_supervisor(self._process)


def invoke_process_handler(
    *,
    db_path: str,
    handler: Handler,
    command: ExecutionCommandV2,
    lease: ExecutionLease,
    now: Any,
    start_timeout: float,
    on_started: Optional[Callable[[ProcessSupervisorHandle], bool]] = None,
    on_finished: Optional[Callable[[ProcessSupervisorHandle], None]] = None,
    on_cleanup_confirmed: Optional[Callable[[], None]] = None,
    durability: str = "full",
    budget_envelope: BudgetEnvelope | None = None,
    service_spec: dict | None = None,
    on_entered: Optional[Callable[[dict[str, Any]], None]] = None,
    on_phase: Optional[Callable[[str, dict[str, Any]], None]] = None,
    capture_budget: Any = None,
) -> dict[str, Any]:
    """Run a handler behind an independently timed and reaping supervisor."""

    tracker = _BudgetTracker(budget_envelope, now, capture_budget,
        guarded=bool((service_spec or {}).get("guard_budget")))
    cleanup_allowed = True
    terminal = None

    def publish(outcome, envelope, entry=None):
        published, checkpoint = _finish_budget_capture(
            capture_budget, envelope, timeout_seconds=.1 if cleanup_allowed else 0.)
        supervisor_checkpoint = terminal.get("budget_checkpoint") if type(terminal) is dict else None
        capture_error = terminal.get("budget_capture_error") if type(terminal) is dict else None
        capture_errors = {}
        if outcome.get("budget_capture_error") is not None:
            capture_errors["parent"] = outcome["budget_capture_error"]
        if capture_error is not None:
            capture_errors["supervisor"] = capture_error
        if checkpoint.get("token") is not None or supervisor_checkpoint is not None or capture_error is not None:
            outcome = {**outcome,
                "budget_checkpoint": {"parent": checkpoint, "supervisor": supervisor_checkpoint},
                **({"budget_capture_error": capture_errors} if capture_errors else {})}
        return _budget_outcome(outcome, published, entry)
    try:
        startup_deadline = tracker.bound(time.monotonic() + start_timeout)
    except BudgetClockUnknownError as exc:
        return publish({"kind": "error", "code": "budget_clock_unknown", "message": str(exc),
                                "control_error": True, "retryable": False, "effect_ids": [],
                                "details": _control_error_details(exc.__cause__ or exc)}, tracker.envelope)
    if startup_deadline <= time.monotonic():
        return publish({"kind": "timeout", "phase": "admission", "effect_ids": []}, tracker.envelope)

    # ``spawn`` avoids forking the potentially multi-threaded caller.  The
    # freshly started, single-threaded supervisor may then safely fork its
    # private handler worker for subreaper containment.
    process_context = multiprocessing.get_context("spawn")
    receiver, sender = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_supervisor_entry,
        args=(db_path, _SerializedHandler(handler), command, lease, now, sender, durability,
              tracker.envelope, service_spec, startup_deadline),
        daemon=False,
    )
    handle = ProcessSupervisorHandle(process)
    registered = False
    try:
        process.start()
        cleanup_allowed = False
    except BaseException:
        receiver.close()
        sender.close()
        raise
    sender.close()
    if on_started is not None:
        try:
            registered = bool(on_started(handle))
        except BaseException:
            handle.terminate()
            receiver.close()
            raise
        if not registered:
            handle.revoke("runtime_closed")
    started = False
    entry: dict[str, Any] | None = None
    deadline: float | None = None
    hard_deadline: float | None = None
    terminal: Optional[dict[str, Any]] = None
    cleanup_fact: Optional[dict[str, Any]] = None
    startup_wait_expired = False
    admission_work_expired = False
    work_wait_expired = False
    try:
        first, startup_deadline = _wait_packet(receiver, startup_deadline, tracker)
        if type(first) is dict and first.get("kind") == "worker_ready":
            _observe_phase(on_phase, "worker_ready", {key: value for key, value in first.items() if key != "kind"})
            first, startup_deadline = _wait_packet(receiver, startup_deadline, tracker)
        if (type(first) is dict and first.get("kind") == "handler_start_failed"
                and type(first.get("details")) is dict and first["details"].get("exception_type")):
            _observe_phase(on_phase, "worker_bootstrap_failed", first["details"])
        started = (
            type(first) is dict
            and first.get("kind") == "handler_started"
            and type(first.get("deadline_monotonic")) in {int, float}
            and math.isfinite(float(first["deadline_monotonic"]))
        )
        if started:
            assert first is not None
            deadline = float(first["deadline_monotonic"])
            entry = first
            hard_deadline = float(first.get("hard_deadline_monotonic", deadline))
            tracker.entered(BudgetEnvelope.from_dict(first["budget_envelope"]))
            if on_entered is not None:
                try:
                    on_entered(first)
                except BaseException:
                    pass
        if deadline is not None:
            terminal, deadline = _wait_packet(receiver, deadline, tracker)
            work_wait_expired = terminal is None and time.monotonic() >= deadline
            if type(terminal) is dict and terminal.get("kind") == "handler_returned":
                assert hard_deadline is not None
                terminal, deadline = _wait_packet(receiver, hard_deadline, tracker, hard=True)
            if terminal is None and receiver.poll(_CLEANUP_GRACE_SECONDS):
                # The business deadline has elapsed, so a successful outcome
                # can no longer be accepted.  The supervisor still gets a
                # bounded interval to contain and reap detached descendants
                # before the parent tears it down.
                terminal = _receive_packet(receiver)
        elif type(first) is dict and first.get("kind") != "handler_started":
            terminal = first
        elif first is None and time.monotonic() >= startup_deadline:
            startup_wait_expired = True
            observed = tracker.envelope
            admission_work_expired = (observed is not None and
                observed.view(sample=observed.checkpoint).remaining_work_seconds == 0)
            # The original admission bound also owns deserialization and the
            # entry handshake. Give its supervisor only bounded containment
            # time, as for expiry after entry; never grant business time.
            if receiver.poll(_CLEANUP_GRACE_SECONDS):
                terminal = _receive_packet(receiver)
        observed_at = time.monotonic()
    except BudgetClockUnknownError as exc:
        terminal = {"kind": "handler_failed", "code": "budget_clock_unknown", "message": str(exc),
                    "control_error": True, "details": _control_error_details(exc.__cause__ or exc)}
        observed_at = time.monotonic()
    finally:
        reaped = handle.terminate()
        if tracker.capture_error is not None:
            # Containment may have produced the original packet while the
            # guarded clock write failed. Preserve ready terminal facts once.
            recover_acceptance = _transient_capture_error(tracker.capture_error)
            for _ in range(4):
                if not receiver.poll(0):
                    break
                available = _receive_packet(receiver)
                if (recover_acceptance and type(available) is dict
                        and available.get("kind") == "handler_started"
                        and type(available.get("deadline_monotonic")) in {int, float}
                        and math.isfinite(available["deadline_monotonic"])):
                    started, entry = True, available
                    deadline = float(available["deadline_monotonic"])
                    hard_deadline = float(available.get("hard_deadline_monotonic", deadline))
                    tracker.entered(BudgetEnvelope.from_dict(available["budget_envelope"]))
                if (type(available) is dict and available.get("cleanup_confirmed") is True
                        and available.get("kind") in ("handler_completed", "handler_entry_failed",
                            "handler_timed_out", "handler_failed", "handler_start_failed")):
                    cleanup_fact = available
                if (recover_acceptance and type(available) is dict
                        and available.get("kind") in (
                        "handler_completed", "handler_entry_failed", "handler_timed_out",
                        "handler_failed", "handler_start_failed")):
                    terminal = available
        receiver.close()
        if registered and on_finished is not None:
            on_finished(handle)
    if not reaped:
        raise RuntimeError("handler supervisor could not be terminated")
    cleanup_allowed = (type(terminal) is dict and terminal.get("cleanup_confirmed") is True
        or cleanup_fact is not None and cleanup_fact.get("cleanup_confirmed") is True)

    budget_envelope = tracker.envelope
    observed_budget = terminal.get("observed_budget_envelope") if type(terminal) is dict else None
    if type(observed_budget) is dict:
        observed = BudgetEnvelope.from_dict(observed_budget)
        budget_envelope = observed if budget_envelope is None else _merge_budget_floor(budget_envelope, observed)

    # A dead supervisor alone cannot prove that orphaned descendants are gone.
    # Only its explicit post-containment packet supports a durable tree receipt.
    if cleanup_allowed and on_cleanup_confirmed is not None:
        on_cleanup_confirmed()

    revocation_reason = handle.revocation_reason
    if revocation_reason is not None:
        return publish({
            "kind": "authority_revoked",
            "reason": revocation_reason,
            "effect_ids": [],
        }, budget_envelope, entry)

    if (
        started and not work_wait_expired
        and type(terminal) is dict
        and terminal.get("kind") == "handler_completed"
        and type(terminal.get("contained_monotonic")) in {int, float}
        and type(terminal.get("outcome_json")) is str
        and math.isfinite(float(terminal["contained_monotonic"]))
        and hard_deadline is not None
        and float(terminal["contained_monotonic"]) < hard_deadline
    ):
        try:
            outcome = json.loads(terminal["outcome_json"])
        except (TypeError, ValueError):
            outcome = None
        if type(outcome) is dict:
            if tracker.capture_error is not None:
                outcome["budget_capture_error"] = {"state": "unknown", "error":
                    _control_error_details(tracker.capture_error.__cause__ or tracker.capture_error)}
            return publish(outcome, budget_envelope, entry)
    if (
        (type(terminal) is dict and terminal.get("kind") == "handler_timed_out")
        or (started and deadline is not None and observed_at >= deadline)
        or startup_wait_expired
    ):
        original = None
        serialized = None if type(terminal) is not dict else terminal.get("business_outcome_json")
        if serialized is None and (startup_wait_expired or work_wait_expired) and type(terminal) is dict:
            serialized = terminal.get("outcome_json")
        if type(serialized) is str:
            try:
                original = json.loads(serialized)
            except ValueError:
                pass
        outcome = {"kind": "timeout", "phase": "execution" if started else "admission",
            "effect_ids": [] if type(original) is not dict else original.get("effect_ids", [])}
        work_budget_expired = (admission_work_expired if startup_wait_expired else
            type(terminal) is dict and terminal.get("work_budget_expired") is True)
        if not started and not work_budget_expired:
            # The internal startup guard does not establish a spent business
            # cutoff. Preserve its existing failure class; inherited work
            # expiry is the distinct authoritative timeout case.
            outcome.update(kind="error", code="handler_process_start_failure",
                message="handler startup window elapsed before invocation", retryable=False)
            outcome["details"] = {"phase": "admission", "startup_window_elapsed": True}
        if startup_wait_expired:
            outcome["details"] = {**outcome.get("details", {}), "supervisor_exitcode": process.exitcode}
            if type(terminal) is dict and terminal.get("kind") in {"handler_failed", "handler_start_failed"}:
                outcome["details"]["startup_failure"] = {key: terminal[key] for key in
                    ("kind", "code", "message", "details") if key in terminal}
        if type(original) is dict:
            outcome["details"] = {**outcome.get("details", {}), "business_outcome": original}
        return publish(outcome, budget_envelope, entry)
    if type(terminal) is dict and terminal.get("kind") == "handler_entry_failed":
        try:
            outcome = json.loads(terminal["outcome_json"])
        except (KeyError, TypeError, ValueError):
            outcome = None
        if type(outcome) is dict:
            return publish(outcome, budget_envelope, entry)
    if (type(terminal) is dict and (terminal.get("kind") == "handler_failed"
            or (terminal.get("kind") == "handler_start_failed" and terminal.get("control_error")))):
        details = {**(terminal.get("details") or {}), "exitcode": process.exitcode}
        original = terminal.get("business_outcome_json")
        if type(original) is str:
            try:
                details["business_outcome"] = json.loads(original)
            except ValueError:
                pass
        return publish({
            "kind": "error",
            "code": str(terminal.get("code", "handler_process_exit")),
            "message": str(terminal.get("message", "handler process failed")),
            "retryable": False,
            "control_error": terminal.get("control_error", False),
            "details": details,
            "effect_ids": [],
        }, budget_envelope, entry)
    if started:
        return publish({
            "kind": "error",
            "code": "handler_process_exit",
            "message": f"handler supervisor exited with code {process.exitcode}",
            "retryable": False,
            "details": {"exitcode": process.exitcode},
            "effect_ids": [],
        }, budget_envelope, entry)
    message = (
        str(terminal.get("message"))
        if type(terminal) is dict and terminal.get("message")
        else "handler supervisor did not reach invocation"
    )
    return publish({
        "kind": "error",
        "code": "handler_process_start_failure",
        "message": message,
        "retryable": False,
        "details": {**(terminal.get("details") or {}), "exitcode": process.exitcode}
            if type(terminal) is dict else {"exitcode": process.exitcode},
        "effect_ids": [],
    }, budget_envelope, entry)
