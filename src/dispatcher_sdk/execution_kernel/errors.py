"""Operational errors raised by the execution kernel."""

from __future__ import annotations

from typing import Any, Mapping


class ExecutionKernelError(RuntimeError):
    pass


class ExecutionNotFoundError(ExecutionKernelError, KeyError):
    pass


class IdempotencyConflictError(ExecutionKernelError):
    pass


class ResultConflictError(ExecutionKernelError):
    pass


class CASConflictError(ExecutionKernelError):
    pass


class StorageIsolationError(ExecutionKernelError):
    pass


class StaleFenceError(ExecutionKernelError):
    def __init__(self, message: str, *, context: Mapping[str, Any] | None = None) -> None:
        self.context = dict(context or {})
        super().__init__(message)


class InvalidStateTransitionError(ExecutionKernelError):
    def __init__(
        self,
        execution_id: str,
        current_state: str,
        requested_state: str,
        *,
        revision: int | None = None,
        lease_id: str | None = None,
        fence: int | None = None,
        reason: str | None = None,
    ) -> None:
        self.context = {
            "execution_id": execution_id,
            "current_state": current_state,
            "requested_state": requested_state,
            "revision": revision,
            "lease_id": lease_id,
            "fence": fence,
            "reason": reason,
        }
        detail = f"; {reason}" if reason else ""
        super().__init__(
            f"invalid execution transition {current_state!r} -> {requested_state!r} "
            f"for {execution_id!r} at revision {revision}{detail}"
        )


class HandlerUnavailableError(ExecutionKernelError):
    pass


class HandlerContractMismatchError(ExecutionKernelError):
    pass


class RegistryRevisionMismatchError(ExecutionKernelError):
    pass


class HandlerExecutionError(Exception):
    """A handler's explicit structured failure signal."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.details = dict(details or {})
        super().__init__(message)


class EffectConflictError(ExecutionKernelError):
    pass


class EffectClaimConflictError(EffectConflictError):
    """Another durable claimant owns the effect's perform authority."""

    pass


class EffectIndeterminateError(ExecutionKernelError):
    pass


class EffectRecoveryRequiredError(EffectIndeterminateError):
    def __init__(self, effect_id: str, message: str = "effect requires explicit recovery") -> None:
        self.effect_id = effect_id
        super().__init__(f"{message}: {effect_id}")
