"""Strict version-2 JSON contracts for the execution kernel."""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
import math
from typing import Any, ClassVar, Mapping, Optional, Union


JSONValue = Union[None, bool, int, float, str, list[Any], dict[str, Any]]
SCHEMA_VERSION = 2


class ContractValidationError(ValueError):
    """A value does not satisfy an exact version-2 JSON contract."""


def _schema_version(value: Any, contract: str) -> None:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise ContractValidationError(
            f"{contract}.schema_version must be the integer {SCHEMA_VERSION}"
        )


def _json_value(value: Any, path: str = "value") -> None:
    if value is None or type(value) in {bool, int, str}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ContractValidationError(f"{path} contains a non-finite number")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _json_value(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ContractValidationError(f"{path} has a non-string object key")
            _json_value(item, f"{path}.{key}")
        return
    raise ContractValidationError(
        f"{path} has unsupported type {type(value).__name__}; expected strict JSON"
    )


def _json_copy(value: Any, path: str) -> Any:
    try:
        _json_value(value, path)
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except ContractValidationError:
        raise
    except (OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise ContractValidationError(f"{path} is not strict JSON") from exc


def _identifier(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ContractValidationError(f"{name} must be a non-empty string")
    return value


def _optional_identifier(value: Any, name: str) -> Optional[str]:
    if value is None:
        return None
    return _identifier(value, name)


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ContractValidationError(f"{name} must be an integer >= {minimum}")
    return value


def _finite(value: Any, name: str, *, minimum: float = 0.0) -> float:
    if type(value) not in {int, float}:
        raise ContractValidationError(f"{name} must be a finite number")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ContractValidationError(f"{name} must be a finite number") from exc
    if not math.isfinite(converted) or converted < minimum:
        raise ContractValidationError(f"{name} must be finite and >= {minimum}")
    return converted


def _load_json(text: str, contract: str) -> dict[str, Any]:
    if type(text) is not str:
        raise ContractValidationError(f"{contract}.from_json requires a string")

    def reject_constant(value: str) -> None:
        raise ContractValidationError(f"{contract} contains invalid JSON constant {value}")

    def reject_duplicate_keys(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ContractValidationError(
                    f"{contract} contains duplicate object key {key!r}"
                )
            value[key] = item
        return value

    try:
        value = json.loads(
            text,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except ContractValidationError:
        raise
    except (RecursionError, TypeError, ValueError) as exc:
        raise ContractValidationError(f"invalid JSON for {contract}") from exc
    if type(value) is not dict:
        raise ContractValidationError(f"{contract} requires a JSON object")
    return value


class _StrictContract:
    schema_version: ClassVar[int] = SCHEMA_VERSION

    @classmethod
    def _coerce(cls, values: dict[str, Any]) -> dict[str, Any]:
        return values

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]):
        if type(payload) is not dict:
            raise ContractValidationError(f"{cls.__name__} requires a JSON object")
        if any(type(key) is not str for key in payload):
            raise ContractValidationError(
                f"{cls.__name__} has a non-string top-level field name"
            )
        expected = {item.name for item in fields(cls)}
        actual = set(payload)
        unknown = actual - expected
        missing = expected - actual
        if unknown:
            raise ContractValidationError(
                f"{cls.__name__} has unknown field(s): {', '.join(sorted(unknown))}"
            )
        if missing:
            raise ContractValidationError(
                f"{cls.__name__} is missing field(s): {', '.join(sorted(missing))}"
            )
        _schema_version(payload.get("schema_version"), cls.__name__)
        try:
            values = cls._coerce(dict(payload))
            return cls(**values)
        except ContractValidationError:
            raise
        except (KeyError, OverflowError, RecursionError, TypeError, ValueError) as exc:
            raise ContractValidationError(f"malformed {cls.__name__}: {exc}") from exc

    @classmethod
    def from_json(cls, text: str):
        return cls.from_dict(_load_json(text, cls.__name__))

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


@dataclass(frozen=True, slots=True)
class RetryPolicy(_StrictContract):
    max_attempts: int = 1
    initial_backoff_seconds: float = 0.0
    backoff_multiplier: float = 1.0
    max_backoff_seconds: float = 300.0
    retry_timeouts: bool = False
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _integer(self.max_attempts, "max_attempts", minimum=1)
        initial = _finite(self.initial_backoff_seconds, "initial_backoff_seconds")
        multiplier = _finite(self.backoff_multiplier, "backoff_multiplier", minimum=1.0)
        maximum = _finite(self.max_backoff_seconds, "max_backoff_seconds")
        if maximum < initial:
            raise ContractValidationError(
                "max_backoff_seconds must be >= initial_backoff_seconds"
            )
        if type(self.retry_timeouts) is not bool:
            raise ContractValidationError("retry_timeouts must be boolean")
        _schema_version(self.schema_version, type(self).__name__)
        object.__setattr__(self, "initial_backoff_seconds", initial)
        object.__setattr__(self, "backoff_multiplier", multiplier)
        object.__setattr__(self, "max_backoff_seconds", maximum)

    def delay_for_attempt(self, attempt: int) -> float:
        _integer(attempt, "attempt", minimum=1)
        if self.initial_backoff_seconds == 0 or self.backoff_multiplier == 1:
            return min(self.max_backoff_seconds, self.initial_backoff_seconds)
        try:
            delay = self.initial_backoff_seconds * (
                self.backoff_multiplier ** (attempt - 1)
            )
        except OverflowError:
            return self.max_backoff_seconds
        return min(self.max_backoff_seconds, delay)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "initial_backoff_seconds": self.initial_backoff_seconds,
            "backoff_multiplier": self.backoff_multiplier,
            "max_backoff_seconds": self.max_backoff_seconds,
            "retry_timeouts": self.retry_timeouts,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionCommandV2(_StrictContract):
    execution_id: str
    idempotency_key: str
    registry_revision: str
    correlation_id: str
    causation_id: Optional[str]
    handler_id: str
    handler_contract_version: int
    retry_policy: RetryPolicy
    timeout_seconds: float
    payload: JSONValue
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.execution_id, "execution_id")
        _identifier(self.idempotency_key, "idempotency_key")
        _identifier(self.registry_revision, "registry_revision")
        _identifier(self.correlation_id, "correlation_id")
        _optional_identifier(self.causation_id, "causation_id")
        _identifier(self.handler_id, "handler_id")
        _integer(self.handler_contract_version, "handler_contract_version", minimum=1)
        if type(self.retry_policy) is not RetryPolicy:
            raise ContractValidationError("retry_policy must be RetryPolicy")
        timeout = _finite(self.timeout_seconds, "timeout_seconds", minimum=0.001)
        payload = _json_copy(self.payload, "payload")
        _schema_version(self.schema_version, type(self).__name__)
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "payload", payload)

    @classmethod
    def _coerce(cls, values: dict[str, Any]) -> dict[str, Any]:
        values["retry_policy"] = RetryPolicy.from_dict(values["retry_policy"])
        return values

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "idempotency_key": self.idempotency_key,
            "registry_revision": self.registry_revision,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "handler_id": self.handler_id,
            "handler_contract_version": self.handler_contract_version,
            "retry_policy": self.retry_policy.to_dict(),
            "timeout_seconds": self.timeout_seconds,
            "payload": _json_copy(self.payload, "payload"),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionError(_StrictContract):
    code: str
    message: str
    retryable: bool
    details: dict[str, JSONValue]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.code, "code")
        if type(self.message) is not str:
            raise ContractValidationError("message must be a string")
        if type(self.retryable) is not bool:
            raise ContractValidationError("retryable must be boolean")
        if type(self.details) is not dict:
            raise ContractValidationError("details must be a JSON object")
        details = _json_copy(self.details, "details")
        _schema_version(self.schema_version, type(self).__name__)
        object.__setattr__(self, "details", details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": _json_copy(self.details, "details"),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionLease(_StrictContract):
    execution_id: str
    lease_id: str
    owner: str
    fence: int
    attempt: int
    expires_at: float
    revision: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.execution_id, "execution_id")
        _identifier(self.lease_id, "lease_id")
        _identifier(self.owner, "owner")
        _integer(self.fence, "fence", minimum=1)
        _integer(self.attempt, "attempt", minimum=1)
        expires = _finite(self.expires_at, "expires_at")
        _integer(self.revision, "revision", minimum=1)
        _schema_version(self.schema_version, type(self).__name__)
        object.__setattr__(self, "expires_at", expires)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "lease_id": self.lease_id,
            "owner": self.owner,
            "fence": self.fence,
            "attempt": self.attempt,
            "expires_at": self.expires_at,
            "revision": self.revision,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResultV2(_StrictContract):
    result_id: str
    execution_id: str
    status: str
    attempt: int
    fence: int
    effect_ids: list[str]
    started_at: float
    completed_at: float
    correlation_id: str
    causation_id: Optional[str]
    value: JSONValue
    error: Optional[ExecutionError]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.result_id, "result_id")
        _identifier(self.execution_id, "execution_id")
        if self.status not in {
            "succeeded",
            "failed",
            "timed_out",
            "cancelled",
            "dead",
        }:
            raise ContractValidationError(f"unsupported result status {self.status!r}")
        _integer(self.attempt, "attempt")
        _integer(self.fence, "fence")
        if (self.attempt == 0) != (self.fence == 0):
            raise ContractValidationError("attempt and fence must both be zero or both be positive")
        if self.status != "cancelled" and (self.attempt == 0 or self.fence == 0):
            raise ContractValidationError(
                "non-cancelled results require positive attempt and fence"
            )
        if type(self.effect_ids) is not list:
            raise ContractValidationError("effect_ids must be a JSON array")
        normalized_effects: list[str] = []
        for index, effect_id in enumerate(self.effect_ids):
            normalized_effects.append(_identifier(effect_id, f"effect_ids[{index}]"))
        if len(set(normalized_effects)) != len(normalized_effects):
            raise ContractValidationError("effect_ids must be unique")
        started = _finite(self.started_at, "started_at")
        completed = _finite(self.completed_at, "completed_at")
        if completed < started:
            raise ContractValidationError("completed_at must be >= started_at")
        _identifier(self.correlation_id, "correlation_id")
        _optional_identifier(self.causation_id, "causation_id")
        value = _json_copy(self.value, "value")
        if self.error is not None and type(self.error) is not ExecutionError:
            raise ContractValidationError("error must be ExecutionError or null")
        if self.status == "succeeded" and self.error is not None:
            raise ContractValidationError("succeeded result cannot contain an error")
        if self.status != "succeeded" and self.error is None:
            raise ContractValidationError("non-succeeded result requires an error")
        if self.status != "succeeded" and self.value is not None:
            raise ContractValidationError("non-succeeded result value must be null")
        if self.status == "dead" and self.error is not None and self.error.retryable:
            raise ContractValidationError("dead result error must not be retryable")
        if self.status == "cancelled" and self.error is not None and self.error.retryable:
            raise ContractValidationError("cancelled result error must not be retryable")
        _schema_version(self.schema_version, type(self).__name__)
        object.__setattr__(self, "effect_ids", list(normalized_effects))
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "completed_at", completed)
        object.__setattr__(self, "value", value)

    @classmethod
    def _coerce(cls, values: dict[str, Any]) -> dict[str, Any]:
        if values["error"] is not None:
            values["error"] = ExecutionError.from_dict(values["error"])
        return values

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "execution_id": self.execution_id,
            "status": self.status,
            "attempt": self.attempt,
            "fence": self.fence,
            "effect_ids": list(self.effect_ids),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "value": _json_copy(self.value, "value"),
            "error": None if self.error is None else self.error.to_dict(),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot(_StrictContract):
    execution_id: str
    state: str
    revision: int
    attempt: int
    fence: int
    redelivery_count: int
    command: ExecutionCommandV2
    lease: Optional[ExecutionLease]
    result: Optional[ExecutionResultV2]
    recovery_effect_id: Optional[str]
    next_attempt_at: float
    started_at: Optional[float]
    created_at: float
    updated_at: float
    recovery_target_state: Optional[str] = None
    recovery_reason: Optional[str] = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.execution_id, "execution_id")
        states = {
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
        if self.state not in states:
            raise ContractValidationError(f"unsupported execution state {self.state!r}")
        _integer(self.revision, "revision", minimum=1)
        _integer(self.attempt, "attempt")
        _integer(self.fence, "fence")
        _integer(self.redelivery_count, "redelivery_count")
        if (self.attempt == 0) != (self.fence == 0):
            raise ContractValidationError(
                "snapshot attempt and fence must both be zero or both be positive"
            )
        if type(self.command) is not ExecutionCommandV2:
            raise ContractValidationError("command must be ExecutionCommandV2")
        if self.command.execution_id != self.execution_id:
            raise ContractValidationError("snapshot and command execution_id must match")
        if self.lease is not None and type(self.lease) is not ExecutionLease:
            raise ContractValidationError("lease must be ExecutionLease or null")
        if self.result is not None and type(self.result) is not ExecutionResultV2:
            raise ContractValidationError("result must be ExecutionResultV2 or null")
        terminal = self.state in {"succeeded", "failed", "timed_out", "cancelled", "dead"}
        if self.state in {"leased", "running"} and self.lease is None:
            raise ContractValidationError("leased/running snapshot requires a lease")
        if self.state not in {"leased", "running"} and self.lease is not None:
            raise ContractValidationError("only leased/running snapshot may carry a lease")
        if terminal != (self.result is not None):
            raise ContractValidationError("terminal snapshots require exactly one result")
        recovery_effect_id = _optional_identifier(
            self.recovery_effect_id, "recovery_effect_id"
        )
        if self.state == "recovery_required" and recovery_effect_id is None:
            raise ContractValidationError(
                "recovery_required snapshot requires recovery_effect_id"
            )
        if self.state != "recovery_required" and recovery_effect_id is not None:
            raise ContractValidationError(
                "only recovery_required snapshot may carry recovery_effect_id"
            )
        recovery_target_state = _optional_identifier(
            self.recovery_target_state, "recovery_target_state"
        )
        recovery_reason = _optional_identifier(self.recovery_reason, "recovery_reason")
        if self.state == "recovery_required":
            if recovery_target_state not in {"queued", "cancelled"}:
                raise ContractValidationError(
                    "recovery_required snapshot requires queued or cancelled recovery_target_state"
                )
            if (recovery_target_state == "cancelled") != (recovery_reason is not None):
                raise ContractValidationError(
                    "cancelled recovery target requires exactly one recovery_reason"
                )
        elif recovery_target_state is not None or recovery_reason is not None:
            raise ContractValidationError(
                "only recovery_required snapshot may carry recovery target metadata"
            )
        if self.lease is not None:
            if (
                self.lease.execution_id != self.execution_id
                or self.lease.attempt != self.attempt
                or self.lease.fence != self.fence
                or self.lease.revision != self.revision
            ):
                raise ContractValidationError("snapshot lease identity does not match")
        if self.result is not None and (
            self.result.execution_id != self.execution_id
            or self.result.attempt != self.attempt
            or self.result.fence != self.fence
            or self.result.status != self.state
            or self.result.correlation_id != self.command.correlation_id
            or self.result.causation_id != self.command.causation_id
        ):
            raise ContractValidationError("snapshot result identity does not match")
        next_at = _finite(self.next_attempt_at, "next_attempt_at")
        started = None if self.started_at is None else _finite(self.started_at, "started_at")
        created = _finite(self.created_at, "created_at")
        updated = _finite(self.updated_at, "updated_at")
        if self.state in {"running", "recovery_required"} and started is None:
            raise ContractValidationError(
                "running/recovery_required snapshot requires started_at"
            )
        if self.state in {"queued", "leased"} and started is not None:
            raise ContractValidationError("queued/leased snapshot cannot have started_at")
        if updated < created:
            raise ContractValidationError("updated_at must be >= created_at")
        if terminal and (
            started is None
            or self.result is None
            or self.result.started_at != started
        ):
            raise ContractValidationError(
                "terminal snapshot started_at must match its result"
            )
        _schema_version(self.schema_version, type(self).__name__)
        object.__setattr__(self, "next_attempt_at", next_at)
        object.__setattr__(self, "recovery_effect_id", recovery_effect_id)
        object.__setattr__(self, "recovery_target_state", recovery_target_state)
        object.__setattr__(self, "recovery_reason", recovery_reason)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)

    @classmethod
    def _coerce(cls, values: dict[str, Any]) -> dict[str, Any]:
        values["command"] = ExecutionCommandV2.from_dict(values["command"])
        if values["lease"] is not None:
            values["lease"] = ExecutionLease.from_dict(values["lease"])
        if values["result"] is not None:
            values["result"] = ExecutionResultV2.from_dict(values["result"])
        return values

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "state": self.state,
            "revision": self.revision,
            "attempt": self.attempt,
            "fence": self.fence,
            "redelivery_count": self.redelivery_count,
            "command": self.command.to_dict(),
            "lease": None if self.lease is None else self.lease.to_dict(),
            "result": None if self.result is None else self.result.to_dict(),
            "recovery_effect_id": self.recovery_effect_id,
            "recovery_target_state": self.recovery_target_state,
            "recovery_reason": self.recovery_reason,
            "next_attempt_at": self.next_attempt_at,
            "started_at": self.started_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class EffectRecord(_StrictContract):
    effect_id: str
    execution_id: str
    name: str
    request: JSONValue
    state: str
    lease_id: str
    claim_id: Optional[str]
    attempt: int
    fence: int
    prepared_at: float
    response: JSONValue
    committed_at: Optional[float]
    indeterminate_at: Optional[float]
    recovery_id: Optional[str]
    recovery_decision: Optional[str]
    resolved_at: Optional[float]
    revision: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.effect_id, "effect_id")
        _identifier(self.execution_id, "execution_id")
        _identifier(self.name, "name")
        request = _json_copy(self.request, "request")
        if self.state not in {
            "prepared",
            "performing",
            "committed",
            "indeterminate",
            "not_applied",
        }:
            raise ContractValidationError(f"unsupported effect state {self.state!r}")
        _identifier(self.lease_id, "lease_id")
        claim_id = _optional_identifier(self.claim_id, "claim_id")
        _integer(self.attempt, "attempt", minimum=1)
        _integer(self.fence, "fence", minimum=1)
        prepared = _finite(self.prepared_at, "prepared_at")
        response = _json_copy(self.response, "response")
        committed = (
            None if self.committed_at is None else _finite(self.committed_at, "committed_at")
        )
        indeterminate = (
            None
            if self.indeterminate_at is None
            else _finite(self.indeterminate_at, "indeterminate_at")
        )
        recovery_id = _optional_identifier(self.recovery_id, "recovery_id")
        recovery_decision = self.recovery_decision
        if recovery_decision not in {None, "applied", "not_applied"}:
            raise ContractValidationError(
                "recovery_decision must be applied, not_applied, or null"
            )
        resolved_at = (
            None if self.resolved_at is None else _finite(self.resolved_at, "resolved_at")
        )
        _integer(self.revision, "revision", minimum=1)
        if self.state == "prepared" and (self.response is not None or committed is not None):
            raise ContractValidationError("prepared effect cannot carry an outcome")
        if self.state == "performing" and (
            claim_id is None or self.response is not None or committed is not None
        ):
            raise ContractValidationError(
                "performing effect requires claim_id and cannot carry an outcome"
            )
        if self.state in {"prepared", "not_applied"} and claim_id is not None:
            raise ContractValidationError(
                "prepared/not_applied effect cannot carry claim_id"
            )
        if self.state == "committed" and committed is None:
            raise ContractValidationError("committed effect requires committed_at")
        if self.state == "committed" and indeterminate is not None and recovery_id is None:
            raise ContractValidationError(
                "a recovered committed effect requires recovery_id"
            )
        if self.state == "indeterminate" and (indeterminate is None or committed is not None):
            raise ContractValidationError(
                "indeterminate effect requires indeterminate_at and no committed_at"
            )
        if self.state == "indeterminate" and recovery_id is not None:
            raise ContractValidationError(
                "an indeterminate effect cannot carry a completed recovery decision"
            )
        if self.state == "not_applied" and (
            indeterminate is None
            or committed is not None
            or self.response is not None
            or recovery_decision != "not_applied"
        ):
            raise ContractValidationError("not_applied effect has inconsistent recovery data")
        if (recovery_id is None) != (recovery_decision is None) or (
            recovery_id is None
        ) != (resolved_at is None):
            raise ContractValidationError(
                "recovery_id, recovery_decision, and resolved_at must appear together"
            )
        if recovery_decision == "applied" and self.state != "committed":
            raise ContractValidationError("applied recovery must produce committed state")
        if recovery_id is not None and indeterminate is None:
            raise ContractValidationError(
                "a recovery decision requires the prior indeterminate timestamp"
            )
        if committed is not None and committed < prepared:
            raise ContractValidationError("committed_at must be >= prepared_at")
        if indeterminate is not None and indeterminate < prepared:
            raise ContractValidationError("indeterminate_at must be >= prepared_at")
        if resolved_at is not None and (
            indeterminate is None or resolved_at < indeterminate
        ):
            raise ContractValidationError("resolved_at must be >= indeterminate_at")
        if committed is not None and resolved_at is not None and committed < resolved_at:
            raise ContractValidationError("committed_at must be >= resolved_at")
        _schema_version(self.schema_version, type(self).__name__)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "claim_id", claim_id)
        object.__setattr__(self, "response", response)
        object.__setattr__(self, "prepared_at", prepared)
        object.__setattr__(self, "committed_at", committed)
        object.__setattr__(self, "indeterminate_at", indeterminate)
        object.__setattr__(self, "recovery_id", recovery_id)
        object.__setattr__(self, "recovery_decision", recovery_decision)
        object.__setattr__(self, "resolved_at", resolved_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect_id": self.effect_id,
            "execution_id": self.execution_id,
            "name": self.name,
            "request": _json_copy(self.request, "request"),
            "state": self.state,
            "lease_id": self.lease_id,
            "claim_id": self.claim_id,
            "attempt": self.attempt,
            "fence": self.fence,
            "prepared_at": self.prepared_at,
            "response": _json_copy(self.response, "response"),
            "committed_at": self.committed_at,
            "indeterminate_at": self.indeterminate_at,
            "recovery_id": self.recovery_id,
            "recovery_decision": self.recovery_decision,
            "resolved_at": self.resolved_at,
            "revision": self.revision,
            "schema_version": self.schema_version,
        }
