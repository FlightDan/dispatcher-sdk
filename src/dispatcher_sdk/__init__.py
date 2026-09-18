"""Standalone orchestration and execution SDK, independent of the host application."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .application import (Dispatcher, Task, DeploymentMismatchError, RecoveryRequiredError,
                              SubmissionConflictError)
    from .identity import (
        CapabilityVerdict, DurabilityObservation, HandlerBindingIdentity, ModuleIdentity,
        RuntimeIdentityReport, StorageIdentity, VerdictStatus, runtime_identity,
    )

__all__ = ["Dispatcher", "Task", "DeploymentMismatchError", "RecoveryRequiredError", "SubmissionConflictError",
           "runtime_identity", "RuntimeIdentityReport", "ModuleIdentity", "StorageIdentity",
           "CapabilityVerdict", "HandlerBindingIdentity", "DurabilityObservation", "VerdictStatus"]


def __getattr__(name: str):
    # Keep the package root inert for Kernel-only consumers. Merely importing
    # dispatcher_sdk must not import the runtime, storage or orchestration stack.
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module = ".application" if name in {
        "Dispatcher", "Task", "DeploymentMismatchError", "RecoveryRequiredError", "SubmissionConflictError"
    } else ".identity"
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value
