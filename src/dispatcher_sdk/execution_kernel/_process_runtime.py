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
import signal
import sys
import threading
import time
from typing import Any, Callable, Mapping, Optional

from .context import HandlerContext, HandlerEffects
from .contracts import ExecutionCommandV2, ExecutionLease
from .errors import EffectRecoveryRequiredError, HandlerExecutionError
from ._registry import Handler
from .sqlite import SQLiteKernel


_PR_SET_CHILD_SUBREAPER = 36
_CLEANUP_GRACE_SECONDS = 1.0
_TREE_QUIET_SECONDS = 0.05


class _DeadlineExpired(BaseException):
    """Private control-flow exception raised only in the supervisor."""


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
) -> dict[str, Any]:
    """Normalize one handler call for both process and thread runtimes."""

    try:
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
        return {
            "kind": "error",
            "code": exc.code,
            "message": str(exc),
            "retryable": exc.retryable,
            "details": exc.details,
            "effect_ids": context.effects.effect_ids,
        }
    except BaseException as exc:
        return {
            "kind": "error",
            "code": "handler_error",
            "message": str(exc),
            "retryable": False,
            "details": {"exception_type": type(exc).__name__},
            "effect_ids": context.effects.effect_ids,
        }


def _descendant_process_ids(root_pid: int) -> tuple[int, ...]:
    if not os.path.isdir("/proc"):
        return ()
    pending = [root_pid]
    seen = {root_pid}
    discovered: list[int] = []
    while pending:
        parent = pending.pop()
        try:
            with open(
                f"/proc/{parent}/task/{parent}/children",
                "r",
                encoding="ascii",
            ) as stream:
                children = tuple(int(value) for value in stream.read().split())
        except (OSError, ValueError):
            continue
        for child in children:
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


def _reap_children() -> None:
    while True:
        try:
            waited, _status = os.waitpid(-1, os.WNOHANG)
        except (ChildProcessError, OSError):
            return
        if waited == 0:
            return


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


def _contain_tree(root_pid: int, worker_pid: int, until: float) -> bool:
    """Kill and reap a worker tree, including subreaper-adopted orphans."""

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
    handler: Handler,
    command: ExecutionCommandV2,
    lease: ExecutionLease,
    now: Any,
    channel: Any,
) -> int:
    kernel: Optional[SQLiteKernel] = None
    effects: Optional[HandlerEffects] = None
    try:
        os.setpgid(0, 0)
        kernel = SQLiteKernel(db_path, now=now)
        effects = HandlerEffects(kernel, lease, lambda: True)
        context = HandlerContext(command, lease, effects)
        _send_packet(channel, {"kind": "worker_ready"})
        go = _receive_packet(channel)
        if go != {"kind": "invoke"}:
            return 70
        outcome = invoke_handler(handler, command, context)
        outcome_json = _serialize_handler_outcome(outcome, effects)
        kernel.close()
        kernel = None
        _send_packet(
            channel,
            {"kind": "worker_completed", "outcome_json": outcome_json},
        )
        return 0
    except BaseException as exc:
        try:
            _send_packet(
                channel,
                {
                    "kind": "worker_failed",
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "effect_ids": [] if effects is None else effects.effect_ids,
                },
            )
        except BaseException:
            pass
        return 70
    finally:
        if kernel is not None:
            try:
                kernel.close()
            except BaseException:
                pass
        channel.close()


def _supervisor_entry(
    db_path: str,
    handler: Handler,
    command: ExecutionCommandV2,
    lease: ExecutionLease,
    now: Any,
    parent_sender: Any,
) -> None:
    worker_pid: Optional[int] = None
    worker_channel: Any = None
    previous_alarm: Any = None
    try:
        os.setsid()
        _enable_linux_subreaper()
        supervisor_channel, child_channel = multiprocessing.Pipe(duplex=True)
        worker_pid = os.fork()
        if worker_pid == 0:
            supervisor_channel.close()
            parent_sender.close()
            status = _worker_entry(
                db_path, handler, command, lease, now, child_channel
            )
            os._exit(status)
        child_channel.close()
        worker_channel = supervisor_channel
        ready = _receive_packet(worker_channel)
        if ready != {"kind": "worker_ready"}:
            _contain_tree(
                os.getpid(), worker_pid, time.monotonic() + _CLEANUP_GRACE_SECONDS
            )
            _send_packet(
                parent_sender,
                {
                    "kind": "handler_start_failed",
                    "message": "handler worker did not become ready",
                },
            )
            return

        deadline = time.monotonic() + command.timeout_seconds

        def expire(_signum: int, _frame: Any) -> None:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                # A same-UID handler can signal its parent.  Treat SIGALRM as
                # a wake-up only; the supervisor's own monotonic deadline is
                # the authority for termination.
                signal.setitimer(signal.ITIMER_REAL, remaining)
                return
            # Do not traverse /proc or kill the tree from a Python signal
            # handler.  The alarm can interrupt an in-progress containment
            # scan; re-entering codecs/filesystem code there is unsafe.  The
            # exception unwinds to the bounded cleanup block below.
            raise _DeadlineExpired()

        previous_alarm = signal.signal(signal.SIGALRM, expire)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _DeadlineExpired()
            signal.setitimer(signal.ITIMER_REAL, remaining)
            _send_packet(worker_channel, {"kind": "invoke"})
            _send_packet(
                parent_sender,
                {"kind": "handler_started", "deadline_monotonic": deadline},
            )
            packet = _receive_packet(worker_channel)
            if packet is None:
                contained = _contain_tree(os.getpid(), worker_pid, deadline)
                if not contained:
                    raise _DeadlineExpired()
                _send_packet(
                    parent_sender,
                    {
                        "kind": "handler_failed",
                        "code": "handler_process_exit",
                        "message": "handler process exited before reporting an outcome",
                    },
                )
                return
            if (
                packet.get("kind") != "worker_completed"
                or type(packet.get("outcome_json")) is not str
            ):
                contained = _contain_tree(os.getpid(), worker_pid, deadline)
                if not contained:
                    raise _DeadlineExpired()
                _send_packet(
                    parent_sender,
                    {
                        "kind": "handler_failed",
                        "code": "handler_process_exit",
                        "message": str(
                            packet.get("message", "handler worker failed internally")
                        ),
                    },
                )
                return
            if not _contain_tree(os.getpid(), worker_pid, deadline):
                raise _DeadlineExpired()
            contained_at = time.monotonic()
            if contained_at >= deadline:
                raise _DeadlineExpired()
            _send_packet(
                parent_sender,
                {
                    "kind": "handler_completed",
                    "contained_monotonic": contained_at,
                    "outcome_json": packet["outcome_json"],
                },
            )
        except _DeadlineExpired:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            _contain_tree(
                os.getpid(), worker_pid, time.monotonic() + _CLEANUP_GRACE_SECONDS
            )
            _send_packet(parent_sender, {"kind": "handler_timed_out"})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            if previous_alarm is not None:
                signal.signal(signal.SIGALRM, previous_alarm)
    except BaseException as exc:
        if worker_pid is not None:
            _contain_tree(
                os.getpid(), worker_pid, time.monotonic() + _CLEANUP_GRACE_SECONDS
            )
        try:
            _send_packet(
                parent_sender,
                {
                    "kind": "handler_start_failed",
                    "message": f"supervisor {type(exc).__name__}: {exc}",
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
) -> dict[str, Any]:
    """Run a handler behind an independently timed and reaping supervisor."""

    # ``spawn`` avoids forking the potentially multi-threaded caller.  The
    # freshly started, single-threaded supervisor may then safely fork its
    # private handler worker for subreaper containment.
    process_context = multiprocessing.get_context("spawn")
    receiver, sender = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_supervisor_entry,
        args=(db_path, handler, command, lease, now, sender),
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
    try:
        first = _receive_packet(receiver) if receiver.poll(start_timeout) else None
        started = (
            type(first) is dict
            and first.get("kind") == "handler_started"
            and type(first.get("deadline_monotonic")) in {int, float}
            and math.isfinite(float(first["deadline_monotonic"]))
        )
        deadline = float(first["deadline_monotonic"]) if started else None
        terminal: Optional[dict[str, Any]] = None
        if deadline is not None:
            if receiver.poll(max(0.0, deadline - time.monotonic())):
                terminal = _receive_packet(receiver)
            elif receiver.poll(_CLEANUP_GRACE_SECONDS):
                # The business deadline has elapsed, so a successful outcome
                # can no longer be accepted.  The supervisor still gets a
                # bounded interval to contain and reap detached descendants
                # before the parent tears it down.
                terminal = _receive_packet(receiver)
        elif type(first) is dict and first.get("kind") != "handler_started":
            terminal = first
        observed_at = time.monotonic()
    finally:
        reaped = handle.terminate()
        receiver.close()
        if registered and on_finished is not None:
            on_finished(handle)
    if not reaped:
        raise RuntimeError("handler supervisor could not be terminated")

    revocation_reason = handle.revocation_reason
    if revocation_reason is not None:
        return {
            "kind": "authority_revoked",
            "reason": revocation_reason,
            "effect_ids": [],
        }

    if (
        started
        and type(terminal) is dict
        and terminal.get("kind") == "handler_completed"
        and type(terminal.get("contained_monotonic")) in {int, float}
        and type(terminal.get("outcome_json")) is str
        and math.isfinite(float(terminal["contained_monotonic"]))
        and float(terminal["contained_monotonic"]) < deadline
    ):
        try:
            outcome = json.loads(terminal["outcome_json"])
        except (TypeError, ValueError):
            outcome = None
        if type(outcome) is dict:
            return outcome
    if started and (
        terminal == {"kind": "handler_timed_out"}
        or (deadline is not None and observed_at >= deadline)
    ):
        return {"kind": "timeout", "effect_ids": []}
    if type(terminal) is dict and terminal.get("kind") == "handler_failed":
        return {
            "kind": "error",
            "code": str(terminal.get("code", "handler_process_exit")),
            "message": str(terminal.get("message", "handler process failed")),
            "retryable": False,
            "details": {"exitcode": process.exitcode},
            "effect_ids": [],
        }
    if started:
        return {
            "kind": "error",
            "code": "handler_process_exit",
            "message": f"handler supervisor exited with code {process.exitcode}",
            "retryable": False,
            "details": {"exitcode": process.exitcode},
            "effect_ids": [],
        }
    message = (
        str(terminal.get("message"))
        if type(terminal) is dict and terminal.get("message")
        else "handler supervisor did not reach invocation"
    )
    return {
        "kind": "error",
        "code": "handler_process_start_failure",
        "message": message,
        "retryable": False,
        "details": {"exitcode": process.exitcode},
        "effect_ids": [],
    }
