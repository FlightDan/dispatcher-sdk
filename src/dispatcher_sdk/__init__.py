"""Standalone orchestration and execution SDK, independent of the host application."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .identity import (
        CapabilityVerdict, DurabilityObservation, HandlerBindingIdentity, ModuleIdentity,
        RuntimeIdentityReport, StorageIdentity, VerdictStatus, runtime_identity,
    )

__all__ = ["runtime_identity", "RuntimeIdentityReport", "ModuleIdentity", "StorageIdentity",
           "CapabilityVerdict", "HandlerBindingIdentity", "DurabilityObservation", "VerdictStatus"]


def __getattr__(name: str):
    # Keep the package root inert for Kernel-only consumers. Merely importing
    # dispatcher_sdk must not import the runtime, storage or orchestration stack.
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    identity = import_module(".identity", __name__)
    value = getattr(identity, name)
    globals()[name] = value
    return value
