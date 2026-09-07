"""Dependency-free contracts for restartable, externally identified sandboxes."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import json
import posixpath
from typing import Any, Literal, Protocol, runtime_checkable

from .contracts import JSONValue, ContractValidationError, _json_copy


class SandboxBackendError(RuntimeError):
    """A sanitized adapter error; ``code`` is safe to persist in a journal."""

    def __init__(self, message: str, *, code: str = "sandbox_backend_error") -> None:
        super().__init__(message)
        self.code = code


class SandboxOutcomeUnknown(SandboxBackendError):
    """An external action may have happened, or its outcome cannot be established."""


class SandboxResourceMissing(SandboxBackendError):
    """An identified resource is absent; this does not prove it never existed."""


class SandboxPolicyError(SandboxBackendError):
    """A requested input, limit or policy cannot be represented by the backend."""


@dataclass(frozen=True, slots=True, eq=False)
class _FrozenObject(Mapping[str, Any]):
    """JSON-backed immutable object with fresh values on every read; pickle-safe."""

    text: str

    def __getitem__(self, key: str) -> Any:
        return json.loads(self.text)[key]

    def __iter__(self) -> Iterator[str]:
        return iter(json.loads(self.text))

    def __len__(self) -> int:
        return len(json.loads(self.text))


def _freeze_object(value: Any, name: str) -> _FrozenObject | None:
    if value is None:
        return None
    if isinstance(value, _FrozenObject):
        return value
    if type(value) is not dict:
        raise ContractValidationError(f"{name} must be a JSON object or null")
    value = _json_copy(value, name)
    if len(json.dumps(value).encode("utf-8")) > 64 * 1024:
        raise ContractValidationError(f"{name} exceeds 64 KiB")
    return _FrozenObject(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _object_payload(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return None if value is None else dict(value)


def _text(value: Any, name: str, *, limit: int = 4096) -> str:
    if type(value) is not str or not value or "\0" in value:
        raise ContractValidationError(f"{name} must be a non-empty string without NUL")
    if len(value.encode("utf-8")) > limit:
        raise ContractValidationError(f"{name} exceeds its byte limit")
    return value


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """Frozen Linux sandbox inputs. All paths refer to the sandbox, never the host.

    ``interpreter`` is an argv prefix; the uploaded source path is appended.
    ``artifacts`` are literal paths, absolute or relative to ``cwd`` (no globs).
    Policy objects are strict JSON, deeply copied and exposed immutably.
    """

    image: str
    source: str
    interpreter: tuple[str, ...]
    cwd: str
    artifacts: tuple[str, ...] = ()
    resources: Mapping[str, Any] | None = None
    network_policy: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _text(self.image, "image")
        _text(self.source, "source", limit=1024 * 1024)
        _text(self.cwd, "cwd")
        if not posixpath.isabs(self.cwd):
            raise ContractValidationError("cwd must be an absolute sandbox path")
        if type(self.interpreter) not in (list, tuple) or not 1 <= len(self.interpreter) <= 64:
            raise ContractValidationError("interpreter must contain 1 to 64 argv elements")
        argv = tuple(_text(value, "interpreter argument") for value in self.interpreter)
        if not posixpath.isabs(argv[0]):
            raise ContractValidationError("interpreter executable must be an absolute sandbox path")
        object.__setattr__(self, "interpreter", argv)
        if type(self.artifacts) not in (list, tuple) or len(self.artifacts) > 32:
            raise ContractValidationError("artifacts must contain at most 32 literal paths")
        paths = tuple(_text(path, "artifact") for path in self.artifacts)
        if len(set(paths)) != len(paths):
            raise ContractValidationError("artifacts must not contain duplicate paths")
        object.__setattr__(self, "artifacts", paths)
        for name in ("resources", "network_policy"):
            object.__setattr__(self, name, _freeze_object(getattr(self, name), name))

    def to_payload(self) -> dict[str, Any]:
        return {"image": self.image, "source": self.source,
                "interpreter": list(self.interpreter), "cwd": self.cwd,
                "artifacts": list(self.artifacts), "resources": _object_payload(self.resources),
                "network_policy": _object_payload(self.network_policy)}

    @classmethod
    def from_payload(cls, payload: Any) -> SandboxSpec:
        if type(payload) is not dict or set(payload) != {
            "image", "source", "interpreter", "cwd", "artifacts", "resources", "network_policy"
        }:
            raise ContractValidationError("invalid sandbox payload fields")
        return cls(**_json_copy(payload, "sandbox payload"))


@dataclass(frozen=True, slots=True)
class SandboxObservation:
    """Backend facts; missing status is unknown, never successful completion."""

    state: Literal["running", "succeeded", "failed", "unknown"]
    exit_code: int | None = None
    details: JSONValue = None

    def __post_init__(self) -> None:
        if type(self.state) is not str or self.state not in ("running", "succeeded", "failed", "unknown"):
            raise ContractValidationError("invalid sandbox observation state")
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise ContractValidationError("exit_code must be an integer or null")
        if self.state == "succeeded" and self.exit_code != 0:
            raise ContractValidationError("successful observation requires exit_code 0")
        if self.state == "failed" and (self.exit_code is None or self.exit_code == 0):
            raise ContractValidationError("failed observation requires a nonzero exit code")
        if self.state == "running" and self.exit_code is not None:
            raise ContractValidationError("running observation cannot have an exit code")
        # Observations cross persistence as JSON; detach caller-owned mutable values.
        object.__setattr__(self, "details", _json_copy(self.details, "observation details"))


@runtime_checkable
class SandboxBackend(Protocol):
    """Blocking provider API. ``timeout`` is an operation budget in seconds.

    Implementations must not retain live clients across calls. Empty ``find``
    results are observations only, never permission to replay an uncertain create.
    ``terminate`` returns True only after authoritative absence confirmation.
    """

    @property
    def name(self) -> str: ...

    @property
    def revision(self) -> str: ...

    def create(self, spec: SandboxSpec, *, operation_key: str, timeout: float) -> str: ...
    def find(self, operation_key: str, *, timeout: float) -> tuple[str, ...]: ...
    def start(self, sandbox_id: str, spec: SandboxSpec, *, timeout: float) -> str: ...
    def inspect(self, sandbox_id: str, command_id: str, *, timeout: float) -> SandboxObservation: ...
    def collect(self, sandbox_id: str, command_id: str, spec: SandboxSpec, *, timeout: float) -> JSONValue: ...
    def terminate(self, sandbox_id: str, *, timeout: float) -> bool: ...
