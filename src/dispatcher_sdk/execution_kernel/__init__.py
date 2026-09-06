"""Strict execution-kernel v2 public API.

Handlers are bound by portable registry fingerprints, effects require durable
perform claims and explicit uncertainty resolution, and :class:`Event` exposes
the restart-safe global execution-event sequence.
"""

from .context import HandlerContext, HandlerEffects
from .contracts import (
    ContractValidationError,
    EffectRecord,
    ExecutionCommandV2,
    ExecutionError,
    ExecutionLease,
    ExecutionResultV2,
    ExecutionSnapshot,
    RetryPolicy,
    SCHEMA_VERSION,
)
from .errors import (
    CASConflictError,
    EffectConflictError,
    EffectClaimConflictError,
    EffectIndeterminateError,
    EffectRecoveryRequiredError,
    ExecutionKernelError,
    ExecutionNotFoundError,
    HandlerContractMismatchError,
    HandlerExecutionError,
    HandlerUnavailableError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
    RegistryRevisionMismatchError,
    ResultConflictError,
    StaleFenceError,
    StorageIsolationError,
)
from .event import Event
from .kernel import Kernel
from .outbox_status import ResultOutboxStatusV2
from .runtime import Handler, InProcessRuntime, Runtime, registry_revision
from .sqlite import ExecutionKernel, SQLiteKernel
from .host import RuntimeHost, RuntimeHostError, RuntimeHostHealth
from .scripts import ScriptSpec, script_handler, script_handlers
from .transitions import (
    EXECUTION_STATES,
    TERMINAL_STATES,
    TRANSITION_MATRIX,
    can_transition,
    reduce_state,
)

__all__ = [
    "RuntimeHost",
    "RuntimeHostError",
    "RuntimeHostHealth",
    "ScriptSpec",
    "script_handler",
    "script_handlers",
    "CASConflictError",
    "ContractValidationError",
    "EffectConflictError",
    "EffectClaimConflictError",
    "EffectIndeterminateError",
    "EffectRecord",
    "EffectRecoveryRequiredError",
    "Event",
    "EXECUTION_STATES",
    "ExecutionCommandV2",
    "ExecutionError",
    "ExecutionKernel",
    "ExecutionKernelError",
    "ExecutionLease",
    "ExecutionNotFoundError",
    "ExecutionResultV2",
    "ExecutionSnapshot",
    "Handler",
    "HandlerContext",
    "HandlerContractMismatchError",
    "HandlerEffects",
    "HandlerExecutionError",
    "HandlerUnavailableError",
    "IdempotencyConflictError",
    "InProcessRuntime",
    "InvalidStateTransitionError",
    "Kernel",
    "RegistryRevisionMismatchError",
    "ResultConflictError",
    "ResultOutboxStatusV2",
    "RetryPolicy",
    "Runtime",
    "SCHEMA_VERSION",
    "SQLiteKernel",
    "StaleFenceError",
    "StorageIsolationError",
    "TERMINAL_STATES",
    "TRANSITION_MATRIX",
    "can_transition",
    "reduce_state",
    "registry_revision",
]
