"""Frozen inline scripts executed by the Kernel's process-isolated runtime.

Register ``script_handlers()`` when opening a Kernel, then submit
``ScriptSpec(...).command(registry_revision=runtime.registry_revision, ...)``.
The application must provide a deadline. Scripts run with the worker's OS
permissions and environment; this is process containment, not a security sandbox.
Full output is retained on disk; only bounded tails enter the result database.
Applications own log storage quotas and retention. Interpreter binaries, imports,
and files in the working directory are not snapshotted by this helper.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
from typing import Any

from .context import HandlerContext
from .contracts import ExecutionCommandV2, RetryPolicy
from .errors import HandlerExecutionError

SCRIPT_HANDLER_ID = "sdk.script"
SCRIPT_HANDLER_VERSION = 1
_MAX_SOURCE_BYTES = 1024 * 1024
_MAX_TAIL_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class ScriptSpec:
    """Immutable source and invocation inputs, copied into the submitted command.

    ``interpreter`` is an argv prefix with an absolute executable path, e.g.
    ``(sys.executable, '-u')`` or ``('/bin/bash',)``. The source file path is
    appended to it. Relative cwd/output paths are resolved when constructing
    the spec, never when the worker eventually runs it.
    """

    source: str
    interpreter: tuple[str, ...]
    cwd: str
    output_dir: str
    tail_bytes: int = 8192

    def __post_init__(self) -> None:
        if type(self.source) is not str or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        if len(self.source.encode("utf-8")) > _MAX_SOURCE_BYTES:
            raise ValueError("source exceeds 1 MiB")
        if not isinstance(self.interpreter, (tuple, list)) or not self.interpreter:
            raise ValueError("interpreter must be a non-empty argv sequence")
        argv = tuple(self.interpreter)
        if any(type(part) is not str or not part or "\0" in part for part in argv):
            raise ValueError("interpreter arguments must be non-empty strings without NUL")
        if not os.path.isabs(argv[0]):
            raise ValueError("interpreter executable must be an absolute path")
        object.__setattr__(self, "interpreter", argv)
        for name in ("cwd", "output_dir"):
            value = getattr(self, name)
            if not isinstance(value, (str, os.PathLike)) or not str(value) or "\0" in str(value):
                raise ValueError(f"{name} must be a non-empty path without NUL")
            object.__setattr__(self, name, str(Path(value).resolve()))
        if type(self.tail_bytes) is not int or not 0 <= self.tail_bytes <= _MAX_TAIL_BYTES:
            raise ValueError("tail_bytes must be an integer between 0 and 65536")

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "interpreter": list(self.interpreter),
            "cwd": self.cwd,
            "output_dir": self.output_dir,
            "tail_bytes": self.tail_bytes,
        }

    @classmethod
    def from_payload(cls, payload: Any) -> ScriptSpec:
        if type(payload) is not dict or set(payload) != {
            "source", "interpreter", "cwd", "output_dir", "tail_bytes"
        }:
            raise ValueError("invalid script payload fields")
        for name in ("cwd", "output_dir"):
            if type(payload[name]) is not str or not os.path.isabs(payload[name]):
                raise ValueError(f"frozen {name} must be an absolute path")
        return cls(**payload)

    def command(
        self,
        *,
        execution_id: str,
        idempotency_key: str,
        registry_revision: str,
        correlation_id: str,
        timeout_seconds: float,
        causation_id: str | None = None,
    ) -> ExecutionCommandV2:
        """Create a one-attempt command with an explicit application deadline."""
        return ExecutionCommandV2(
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            registry_revision=registry_revision,
            correlation_id=correlation_id,
            causation_id=causation_id,
            handler_id=SCRIPT_HANDLER_ID,
            handler_contract_version=SCRIPT_HANDLER_VERSION,
            retry_policy=RetryPolicy(max_attempts=1),
            timeout_seconds=timeout_seconds,
            payload=self.to_payload(),
        )


def _output_summary(path: Path, tail_bytes: int) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
            size += len(chunk)
        stream.seek(max(0, size - tail_bytes))
        tail = stream.read(tail_bytes).decode("utf-8", errors="replace")
    return {"path": str(path), "sha256": digest.hexdigest(), "bytes": size, "tail": tail}


def script_handler(payload: Any, context: HandlerContext) -> dict[str, Any]:
    """Standard handler; use only with process isolation and trusted scripts.

    Nonzero exits commit the observed process outcome before reporting failure.
    A timeout/crash while the effect is in flight requires explicit recovery;
    retrying an arbitrary script could duplicate external side effects.
    """
    try:
        spec = ScriptSpec.from_payload(payload)
    except (TypeError, ValueError) as exc:
        raise HandlerExecutionError("invalid_script", str(exc)) from exc
    identity = hashlib.sha256(context.command.execution_id.encode("utf-8")).hexdigest()
    directory = Path(spec.output_dir) / identity / f"{context.lease.attempt}-{context.lease.fence}"
    source_path = directory / "script.source"
    stdout_path = directory / "stdout.log"
    stderr_path = directory / "stderr.log"
    source_hash = hashlib.sha256(spec.source.encode("utf-8")).hexdigest()
    request = {
        "script": spec.to_payload(),
        "source_sha256": source_hash,
        # Stable across recovery attempts so a committed effect can replay.
        # Individual attempts retain separate artifacts beneath this root.
        "output_root": str(Path(spec.output_dir) / identity),
    }

    def perform() -> dict[str, Any]:
        directory.mkdir(parents=True, exist_ok=False)
        with source_path.open("xb") as source:
            source.write(spec.source.encode("utf-8"))
            source.flush()
            os.fsync(source.fileno())
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            # No second timer or process supervisor: the Kernel owns both the
            # command deadline and containment of this process's descendants.
            completed = subprocess.run(
                [*spec.interpreter, str(source_path)],
                cwd=spec.cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
            stdout.flush()
            stderr.flush()
            os.fsync(stdout.fileno())
            os.fsync(stderr.fileno())
        return {
            "exit_code": completed.returncode,
            "source_path": str(source_path),
            "source_sha256": source_hash,
            "stdout": _output_summary(stdout_path, spec.tail_bytes),
            "stderr": _output_summary(stderr_path, spec.tail_bytes),
        }

    result = context.effects.execute_once(
        f"script:{identity}", "script.execute", request, perform
    )
    if result["exit_code"] != 0:
        raise HandlerExecutionError(
            "script_exit_nonzero",
            f"script exited with status {result['exit_code']}",
            details=result,
        )
    return result


script_handler.__execution_kernel_revision__ = "sdk-script-v1"
script_handler.requires_process_isolation = True


def script_handlers() -> dict[tuple[str, int], Any]:
    """Return fresh standard bindings to merge into an application's registry."""
    return {(SCRIPT_HANDLER_ID, SCRIPT_HANDLER_VERSION): script_handler}
