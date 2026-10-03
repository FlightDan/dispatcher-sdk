"""POSIX handler isolation supervised outside the handler process.

The supervisor owns the deadline and, on Linux, acts as a child subreaper so
double-forked descendants cannot escape cleanup by changing process groups or
sessions.  A handler never receives the parent result channel and cannot
cancel or replace the supervisor's timer.
"""

from __future__ import annotations

import ctypes
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

from .context import HandlerContext, HandlerEffects
from .budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
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
        envelope = getattr(context, "_budget_envelope", None)
        if isinstance(envelope, BudgetEnvelope):
            outcome.update(budget_envelope=envelope.to_dict(), started_at=envelope.started_at)
        return outcome
    except BaseException as exc:
        from .children import ChildExecutionError
        if isinstance(exc, ChildExecutionError):
            return {"kind": "error", "code": exc.code, "message": str(exc), "retryable": False,
                "details": {"child_execution_id": exc.execution_id, "child_result": exc.result},
                "effect_ids": context.effects.effect_ids}
        return {
            "kind": "error",
            "code": "handler_error",
            "message": str(exc),
            "retryable": False,
            "details": {"exception_type": type(exc).__name__},
            "effect_ids": context.effects.effect_ids,
        }


def _capture_completion_time(outcome: dict[str, Any], context: HandlerContext) -> None:
    """Retain logical completion time without waiting on shared control locks.

    Raw wall time can roll back below a durably observed lease expiry. The
    original result must not use that rollback as proof of timely completion.
    """
    try:
        with context._kernel._control_lock(.1):
            outcome["completed_at"] = context._kernel.current_time()
        outcome["completion_time_known"] = True
    except Exception as exc:
        outcome["completion_time_known"] = False
        outcome["completion_time_error"] = f"{type(exc).__name__}: {exc}"


def _budget_sample(now: Any):
    return sample_clock(wall_time=now() if callable(now) else None)


def _bounded_deadline(deadline: float, envelope: BudgetEnvelope | None, now: Any,
                      *, hard: bool = False) -> float:
    if envelope is None:
        return deadline
    bound = envelope.deadline_monotonic(hard=hard, sample=_budget_sample(now))
    return deadline if bound is None else min(deadline, bound)


def _entry_packet(context: HandlerContext, now: Any) -> dict[str, Any]:
    envelope = context.budget_envelope
    try:
        from ..observability.processes import _birth
        birth, namespace, birth_reason = _birth(os.getpid())
    except Exception:
        birth, namespace, birth_reason = None, None, "birth_identity_unavailable"
    return {"kind": "worker_entered", "budget_envelope": envelope.to_dict(),
            "deadline_monotonic": envelope.deadline_monotonic(sample=_budget_sample(now)),
            "hard_deadline_monotonic": envelope.deadline_monotonic(hard=True, sample=_budget_sample(now)),
            "started_at": envelope.started_at, "worker_pid": os.getpid(),
            "birth_identity": birth, "namespace": namespace, "birth_unknown_reason": birth_reason,
            "process_evidence": {"source": "worker_self_report", "state": "alive", "pid": os.getpid()}}


def _confirmed_entry_packet(context: HandlerContext, now: Any) -> dict[str, Any]:
    # Retry only writer contention, retaining the one actual-entry cutoff.
    # The supervisor independently bounds startup while no entry ACK exists.
    captured = context.budget_envelope
    while True:
        view = context.budget
        if view.clock_status != "trusted":
            raise HandlerExecutionError("budget_clock_unknown", view.unknown_reason, details=view.to_dict())
        if not view.remaining_work_seconds:
            raise HandlerExecutionError("execution_deadline_exhausted",
                "execution work deadline elapsed before durable entry confirmation", details=view.to_dict())
        # Keep every observed forward wall jump when a BUSY retry later sees
        # a rollback. Constraints and the original entry time stay immutable.
        captured = captured.recheckpoint(sample=context.budget_envelope.checkpoint)
        try:
            envelope = context._kernel.confirm_handler_entry(context.lease, captured,
                timeout_seconds=min(.1, view.remaining_work_seconds))
            context.budget
            latest = context.budget_envelope.checkpoint
            confirmed_now = envelope.checkpoint.effective_time(latest)
            if confirmed_now is None:
                raise BudgetClockUnknownError("entry clock continuity cannot be established")
            if latest.wall_at > confirmed_now:
                captured = captured.recheckpoint(sample=latest)
                continue
            break
        except Exception as exc:
            sqlite_code = getattr(exc, "sqlite_errorcode", None)
            busy = isinstance(exc, sqlite3.OperationalError) and (
                (isinstance(sqlite_code, int) and sqlite_code & 0xff in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})
                or (sqlite_code is None and str(exc).lower() in {
                    "database is locked", "database table is locked", "database schema is locked"}))
            if busy:
                # Yield briefly; the next iteration resamples authoritative
                # elapsed/wall time instead of granting a new entry interval.
                time.sleep(min(.01, view.remaining_work_seconds))
                continue
            code = "budget_clock_unknown" if isinstance(exc, BudgetClockUnknownError) else "entry_confirmation_unknown"
            raise HandlerExecutionError(code, str(exc), details={"cause": type(exc).__name__}) from exc
    with context._budget_lock:
        local = context.budget_envelope.checkpoint
        if local.elapsed_at <= envelope.checkpoint.elapsed_at:
            checkpoint = context.budget_envelope.recheckpoint(sample=envelope.checkpoint).checkpoint
            envelope = envelope.recheckpoint(sample=checkpoint)
        context._budget_envelope = envelope
        if context.children is not None:
            context.children.budget_envelope = envelope
    view = context.budget
    if view.clock_status != "trusted":
        raise HandlerExecutionError("budget_clock_unknown", view.unknown_reason, details=view.to_dict())
    if not view.remaining_work_seconds:
        raise HandlerExecutionError("execution_deadline_exhausted",
            "execution work deadline elapsed before durable entry confirmation", details=view.to_dict())
    return {**_entry_packet(context, now), "entry_confirmed": True}


def _budget_outcome(outcome: dict[str, Any], envelope: BudgetEnvelope | None,
                    entry: dict[str, Any] | None = None) -> dict[str, Any]:
    if outcome.get("code") == "execution_deadline_exhausted":
        outcome = {**outcome, "kind": "timeout", "phase": outcome.get("phase", "entry_authority")}
    if outcome.get("code") == "budget_clock_unknown":
        outcome = {**outcome, "control_error": True}
    if entry is None and type(outcome.get("budget_envelope")) is dict:
        envelope = BudgetEnvelope.from_dict(outcome["budget_envelope"])
    if entry is not None:
        envelope = BudgetEnvelope.from_dict(entry["budget_envelope"])
    if envelope is None:
        return outcome
    constraint = None if envelope is None else min(
        envelope.constraints, key=lambda item: item.work_deadline_at, default=None)
    return {**outcome, "started_at": outcome.get("started_at") if entry is None else entry.get("started_at"),
            "budget_envelope": None if envelope is None else envelope.to_dict(),
            "limiting_source": outcome.get("limiting_source") if outcome.get("code") == "execution_deadline_exhausted"
                and type(outcome.get("limiting_source")) is str
                and outcome.get("limiting_source") in {"run", "execution", "parent", "tool"}
                else None if constraint is None else constraint.source}


def _wait_packet(receiver: Any, deadline: float, envelope: BudgetEnvelope | None,
                 now: Any, *, hard: bool = False) -> tuple[dict[str, Any] | None, float]:
    while True:
        deadline = _bounded_deadline(deadline, envelope, now, hard=hard)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, deadline
        if receiver.poll(min(remaining, 0.05)):
            return _receive_packet(receiver), deadline


def _close_context(context: HandlerContext | None) -> dict[str, Any]:
    if context is not None:
        try:
            receipt = context.close()
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

    def __init__(self, deadline: float, envelope: BudgetEnvelope | None, now: Any) -> None:
        self.envelope, self.now = envelope, now
        self.inherited_work_deadline = _bounded_deadline(math.inf, envelope, now)
        self.inherited_hard_deadline = _bounded_deadline(math.inf, envelope, now, hard=True)
        self.deadline = _bounded_deadline(deadline, envelope, now)
        self.hard_deadline = _bounded_deadline(deadline, envelope, now, hard=True)
        self.cleanup = False
        self.elapsed_deadline: float | None = None
        self._refresh_elapsed_limit()

    def _refresh_elapsed_limit(self) -> None:
        if self.envelope is not None and self.envelope.constraints:
            anchor = self.envelope.checkpoint
            if anchor.domain_scope == "boot" and anchor.domain_id is not None and anchor.domain_id.startswith("linux-boot:"):
                self.elapsed_deadline = anchor.elapsed_at + min(
                    item.deadline_at if self.cleanup else item.work_deadline_at
                    for item in self.envelope.constraints) - anchor.wall_at

    def remaining(self, *, resample: bool = False) -> float:
        if resample:
            self.inherited_work_deadline = _bounded_deadline(self.inherited_work_deadline, self.envelope, self.now)
            self.inherited_hard_deadline = _bounded_deadline(self.inherited_hard_deadline, self.envelope, self.now, hard=True)
            self.deadline = _bounded_deadline(self.deadline, self.envelope, self.now, hard=self.cleanup)
        if self.envelope is not None and self.envelope.constraints and self.now is None:
            offset = time.monotonic() - time.time()
            work_bound = min(item.work_deadline_at for item in self.envelope.constraints) + offset
            hard_bound = min(item.deadline_at for item in self.envelope.constraints) + offset
            self.inherited_work_deadline = min(self.inherited_work_deadline, work_bound)
            self.inherited_hard_deadline = min(self.inherited_hard_deadline, hard_bound)
            # Remember forward jumps locally so a later rollback cannot extend.
            self.deadline = min(self.deadline, hard_bound if self.cleanup else work_bound)
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
            self.envelope = entered
        self.deadline = min(self.inherited_work_deadline,
                            _bounded_deadline(float(packet_deadline), self.envelope, self.now))
        hard_deadline = packet.get("hard_deadline_monotonic", packet_deadline)
        if not isinstance(hard_deadline, (int, float)) or isinstance(hard_deadline, bool) or not math.isfinite(hard_deadline):
            raise ValueError("worker entry lacks a finite hard deadline")
        self.hard_deadline = min(self.inherited_hard_deadline,
                                 _bounded_deadline(float(hard_deadline), self.envelope, self.now, hard=True))
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
            ready = _receive_packet(worker_channel)
            if type(ready) is not dict or ready.get("kind") != "worker_ready":
                contained = _contain_tree(
                    os.getpid(), worker_pid, time.monotonic() + _CLEANUP_GRACE_SECONDS,
                    subreaper=subreaper,
                )
                _send_packet(parent_sender, {"kind": "handler_start_failed",
                                            "cleanup_confirmed": contained and subreaper,
                                            "message": ready.get("message", "handler worker did not become ready")
                                                if type(ready) is dict else "handler worker did not become ready",
                                            "details": ready.get("details", {}) if type(ready) is dict else {}})
                return
            _send_packet(parent_sender, ready)
            _send_packet(worker_channel, {"kind": "invoke"})
            packet = _receive_packet(worker_channel)
            if type(packet) is dict and packet.get("kind") == "worker_entered":
                guard.entered(packet)
                _send_packet(parent_sender, {**packet, "kind": "handler_started",
                                            "deadline_monotonic": guard.deadline,
                                            "hard_deadline_monotonic": guard.hard_deadline})
                guard.arm()
                packet = _receive_packet(worker_channel)
            elif type(packet) is dict and packet.get("kind") == "worker_completed":
                # Entry can fail before granting the callable any authority.
                contained = _contain_tree(os.getpid(), worker_pid, guard.deadline, subreaper=subreaper)
                if not contained:
                    raise _DeadlineExpired()
                _send_packet(parent_sender, {"kind": "handler_entry_failed",
                                            "cleanup_confirmed": subreaper,
                                            "outcome_json": packet.get("outcome_json")})
                return
            if guard.remaining(resample=True) <= 0:
                raise _DeadlineExpired()
            if type(packet) is dict and packet.get("kind") == "worker_returned":
                completed = packet.get("completed_monotonic")
                if (type(completed) not in {int, float} or not math.isfinite(completed)
                        or completed >= guard.deadline or type(packet.get("outcome_json")) is not str):
                    raise _DeadlineExpired()
                business_outcome_json = packet["outcome_json"]
            guard.begin_cleanup()
            deadline = guard.deadline
            if type(packet) is dict and packet.get("kind") == "worker_returned":
                _send_packet(parent_sender, {"kind": "handler_returned"})
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
                    if guard.remaining(resample=True) <= 0:
                        raise _DeadlineExpired()
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
                _send_packet(
                    parent_sender,
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
                _send_packet(
                    parent_sender,
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
            _send_packet(
                parent_sender,
                {
                    "kind": "handler_completed",
                    "cleanup_confirmed": subreaper,
                    "contained_monotonic": contained_at,
                    "outcome_json": packet["outcome_json"],
                },
            )
        except _DeadlineExpired:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            contained = _contain_tree(
                os.getpid(), worker_pid, time.monotonic() + _CLEANUP_GRACE_SECONDS,
                subreaper=subreaper,
            )
            _send_packet(parent_sender, {"kind": "handler_timed_out", "cleanup_confirmed": contained and subreaper,
                                       "business_outcome_json": business_outcome_json})
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
            details = _bootstrap_diagnostic(exc, "supervisor_setup")
            _send_packet(
                parent_sender,
                {
                    "kind": "handler_start_failed",
                    "cleanup_confirmed": contained and subreaper,
                    "message": details["message"],
                    "details": details,
                },
            )
        except BaseException:
            pass
    finally:
        if worker_channel is not None:
            worker_channel.close()
        parent_sender.close()


def _kill_supervisor(process: multiprocessing.Process) -> bool:
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
            elif now - quiet_since >= _TREE_QUIET_SECONDS:
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
            return _kill_supervisor(self._process)

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
) -> dict[str, Any]:
    """Run a handler behind an independently timed and reaping supervisor."""

    try:
        startup_deadline = _bounded_deadline(time.monotonic() + start_timeout, budget_envelope, now)
    except BudgetClockUnknownError as exc:
        return _budget_outcome({"kind": "error", "code": "budget_clock_unknown", "message": str(exc),
                                "control_error": True, "retryable": False, "effect_ids": []}, budget_envelope)
    if startup_deadline <= time.monotonic():
        return _budget_outcome({"kind": "timeout", "phase": "admission", "effect_ids": []}, budget_envelope)

    # ``spawn`` avoids forking the potentially multi-threaded caller.  The
    # freshly started, single-threaded supervisor may then safely fork its
    # private handler worker for subreaper containment.
    process_context = multiprocessing.get_context("spawn")
    receiver, sender = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_supervisor_entry,
        args=(db_path, _SerializedHandler(handler), command, lease, now, sender, durability,
              budget_envelope, service_spec, startup_deadline),
        daemon=False,
    )
    handle = ProcessSupervisorHandle(process)
    registered = False
    try:
        process.start()
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
    try:
        first, startup_deadline = _wait_packet(receiver, startup_deadline, budget_envelope, now)
        if type(first) is dict and first.get("kind") == "worker_ready":
            _observe_phase(on_phase, "worker_ready", {key: value for key, value in first.items() if key != "kind"})
            first, startup_deadline = _wait_packet(receiver, startup_deadline, budget_envelope, now)
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
            if budget_envelope is not None:
                budget_envelope = BudgetEnvelope.from_dict(first["budget_envelope"])
            if on_entered is not None:
                try:
                    on_entered(first)
                except BaseException:
                    pass
        if deadline is not None:
            terminal, deadline = _wait_packet(receiver, deadline, budget_envelope, now)
            if type(terminal) is dict and terminal.get("kind") == "handler_returned":
                assert hard_deadline is not None
                terminal, deadline = _wait_packet(receiver, hard_deadline, budget_envelope, now, hard=True)
            if terminal is None and receiver.poll(_CLEANUP_GRACE_SECONDS):
                # The business deadline has elapsed, so a successful outcome
                # can no longer be accepted.  The supervisor still gets a
                # bounded interval to contain and reap detached descendants
                # before the parent tears it down.
                terminal = _receive_packet(receiver)
        elif type(first) is dict and first.get("kind") != "handler_started":
            terminal = first
        observed_at = time.monotonic()
    except BudgetClockUnknownError as exc:
        terminal = {"kind": "handler_failed", "code": "budget_clock_unknown", "message": str(exc)}
        observed_at = time.monotonic()
    finally:
        reaped = handle.terminate()
        receiver.close()
        if registered and on_finished is not None:
            on_finished(handle)
    if not reaped:
        raise RuntimeError("handler supervisor could not be terminated")

    # A dead supervisor alone cannot prove that orphaned descendants are gone.
    # Only its explicit post-containment packet supports a durable tree receipt.
    if (type(terminal) is dict and terminal.get("cleanup_confirmed") is True
            and on_cleanup_confirmed is not None):
        on_cleanup_confirmed()

    revocation_reason = handle.revocation_reason
    if revocation_reason is not None:
        return _budget_outcome({
            "kind": "authority_revoked",
            "reason": revocation_reason,
            "effect_ids": [],
        }, budget_envelope, entry)

    if (
        started
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
            return _budget_outcome(outcome, budget_envelope, entry)
    if (
        (type(terminal) is dict and terminal.get("kind") == "handler_timed_out")
        or (started and deadline is not None and observed_at >= deadline)
    ):
        original = None
        if type(terminal) is dict and type(terminal.get("business_outcome_json")) is str:
            try:
                original = json.loads(terminal["business_outcome_json"])
            except ValueError:
                pass
        outcome = {"kind": "timeout", "effect_ids": [] if type(original) is not dict else original.get("effect_ids", [])}
        if type(original) is dict:
            outcome["details"] = {"business_outcome": original}
        return _budget_outcome(outcome, budget_envelope, entry)
    if type(terminal) is dict and terminal.get("kind") == "handler_entry_failed":
        try:
            outcome = json.loads(terminal["outcome_json"])
        except (KeyError, TypeError, ValueError):
            outcome = None
        if type(outcome) is dict:
            return _budget_outcome(outcome, budget_envelope, entry)
    if type(terminal) is dict and terminal.get("kind") == "handler_failed":
        return _budget_outcome({
            "kind": "error",
            "code": str(terminal.get("code", "handler_process_exit")),
            "message": str(terminal.get("message", "handler process failed")),
            "retryable": False,
            "details": {**(terminal.get("details") or {}), "exitcode": process.exitcode},
            "effect_ids": [],
        }, budget_envelope, entry)
    if started:
        return _budget_outcome({
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
    return _budget_outcome({
        "kind": "error",
        "code": "handler_process_start_failure",
        "message": message,
        "retryable": False,
        "details": {**(terminal.get("details") or {}), "exitcode": process.exitcode}
            if type(terminal) is dict else {"exitcode": process.exitcode},
        "effect_ids": [],
    }, budget_envelope, entry)
