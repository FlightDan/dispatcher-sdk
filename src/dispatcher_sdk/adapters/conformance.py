"""Opt-in, real-resource contract check reusable by community adapter authors."""

import math
import time
from uuid import uuid4

from ..execution_kernel.contracts import _json_value
from ..execution_kernel.sandbox_contracts import SandboxBackend, SandboxOutcomeUnknown, SandboxSpec


def verify_backend(backend: SandboxBackend, spec: SandboxSpec, *, timeout: float = 120,
                   expected_exit_code: int = 0) -> dict:
    """Create one disposable sandbox, execute a fixture, collect, and destroy it.

    This function deliberately uses real resources. Use an isolated test account
    and a harmless fixture whose expected exit status is known. It tests contract
    interoperability; security isolation and response-loss scenarios require
    provider-specific tests. It never repeats an uncertain create or start.
    """
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if type(expected_exit_code) is not int:
        raise ValueError("expected_exit_code must be an integer")
    deadline = time.monotonic() + timeout
    operation_key = "conformance-" + uuid4().hex

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("sandbox conformance fixture exceeded its deadline")
        return value

    sandbox_id = None
    try:
        sandbox_id = backend.create(spec, operation_key=operation_key, timeout=remaining())
        if type(sandbox_id) is not str or not sandbox_id.strip():
            raise SandboxOutcomeUnknown("create returned no identity")
        if backend.find(operation_key, timeout=remaining()) != (sandbox_id,):
            raise AssertionError("created sandbox is not uniquely discoverable by its operation key")
        command_id = backend.start(sandbox_id, spec, timeout=remaining())
        if type(command_id) is not str or not command_id.strip():
            raise SandboxOutcomeUnknown("start returned no identity")
        while True:
            observation = backend.inspect(sandbox_id, command_id, timeout=remaining())
            if observation.state == "unknown":
                raise SandboxOutcomeUnknown("fixture outcome could not be established")
            if observation.state != "running":
                break
            time.sleep(min(0.05, remaining()))
        if observation.exit_code != expected_exit_code:
            raise AssertionError(f"expected exit {expected_exit_code}, got {observation.exit_code}")
        result = backend.collect(sandbox_id, command_id, spec, timeout=remaining())
        _json_value(result)
    finally:
        # Cleanup gets its own budget even when the fixture used its whole time.
        if sandbox_id is not None:
            if backend.terminate(sandbox_id, timeout=timeout) is not True:
                raise SandboxOutcomeUnknown(f"test sandbox {sandbox_id} has no confirmed disposal")
        else:
            # Discovery can mitigate a lost response, but never proves no future
            # resource will appear. The original create error remains visible.
            for identity in backend.find(operation_key, timeout=timeout):
                backend.terminate(identity, timeout=timeout)
    if backend.find(operation_key, timeout=timeout):
        raise AssertionError("disposed sandbox remains discoverable")
    return {"backend": backend.name, "revision": backend.revision, "sandbox_id": sandbox_id,
            "command_id": command_id, "exit_code": observation.exit_code,
            "result": result, "cleanup_confirmed": True}


__all__ = ["verify_backend"]
