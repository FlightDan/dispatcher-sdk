"""Optional OpenSandbox 0.1.16 adapter; importing it has no third-party imports.

Every call owns its SDK clients. The dataclass contains only portable
configuration, never a client, transport, credential value, or event loop.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import timedelta
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
import posixpath
import shlex
import time
from types import SimpleNamespace
from typing import Any, ClassVar, Iterator
from urllib.parse import urlsplit

from ..execution_kernel.sandbox_contracts import (
    SandboxBackendError, SandboxObservation, SandboxOutcomeUnknown,
    SandboxPolicyError, SandboxResourceMissing, SandboxSpec,
)

_SUPPORTED_SDK = "0.1.16"
_OPERATION_LABEL = "dispatcher_operation"


def _sdk() -> Any:
    try:
        installed = version("opensandbox")
    except PackageNotFoundError:
        raise SandboxPolicyError("Install dispatcher-sdk[opensandbox] to use this backend",
                                 code="dependency_missing") from None
    if installed != _SUPPORTED_SDK:
        raise SandboxPolicyError("This adapter requires opensandbox==0.1.16",
                                 code="unsupported_sdk_version")
    from opensandbox.config import ConnectionConfigSync
    from opensandbox.models.execd import RunCommandOpts
    from opensandbox.models.sandboxes import NetworkPolicy, SandboxFilter
    from opensandbox.sync.manager import SandboxManagerSync
    from opensandbox.sync.sandbox import SandboxSync
    from opensandbox.transport import RetryPolicy
    return SimpleNamespace(ConnectionConfig=ConnectionConfigSync, Sandbox=SandboxSync,
                           Manager=SandboxManagerSync, RunCommandOpts=RunCommandOpts,
                           NetworkPolicy=NetworkPolicy, SandboxFilter=SandboxFilter,
                           RetryPolicy=RetryPolicy)


class _Budget:
    def __init__(self, seconds: float) -> None:
        try:
            valid = type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 86400
        except OverflowError:
            valid = False
        if not valid:
            raise SandboxPolicyError("timeout must be positive finite seconds", code="invalid_timeout")
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise SandboxOutcomeUnknown("Sandbox operation budget exhausted", code="operation_timeout")
        return remaining


def _identity(value: str) -> str:
    if type(value) is not str or not value.strip() or "\0" in value or len(value) > 4096:
        raise SandboxPolicyError("Invalid sandbox operation identity", code="invalid_identity")
    return value


def _operation_token(operation_key: str) -> str:
    # OpenSandbox validates metadata values as Kubernetes labels (max 63
    # characters). Base32 preserves all 256 digest bits within 52 characters.
    digest = hashlib.sha256(_identity(operation_key).encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").rstrip("=").lower()


def _provider_identity(value: Any) -> str:
    try:
        return _identity(value)
    except SandboxPolicyError:
        raise SandboxOutcomeUnknown("Provider response contained no valid identity",
                                    code="provider_identity_missing") from None


@contextmanager
def _translate(operation: str) -> Iterator[None]:
    try:
        yield
    except SandboxBackendError:
        raise
    except Exception as exc:
        # Provider exception messages/tracebacks may contain headers, command
        # source or credentials. Only fixed local diagnostics cross this boundary.
        if getattr(exc, "status_code", None) == 404 and operation in {"start", "inspect", "collect"}:
            raise SandboxResourceMissing("Sandbox resource is no longer available",
                                         code="resource_missing") from None
        raise SandboxOutcomeUnknown(f"OpenSandbox {operation} outcome could not be established",
                                    code=f"{operation}_unknown") from None


def _close(client: Any) -> None:
    if client is not None:
        try:
            client.close()
        except Exception:
            # Closing local transport cannot undo a confirmed remote response.
            pass


@dataclass(frozen=True, slots=True)
class OpenSandboxBackend:
    """Linux sandbox backend with explicit endpoint and finite collection limits.

    ``sandbox_ttl_seconds`` is independent of individual HTTP call budgets.
    Authentication is read from ``api_key_env`` at call time and is not pickled.
    Only CPU/memory resource limits and domain-based egress policy are supported.
    Strong termination requires an exclusively owned sandbox.
    """

    domain: str
    protocol: str = "http"
    api_key_env: str = "OPEN_SANDBOX_API_KEY"
    use_server_proxy: bool = True
    sandbox_ttl_seconds: float = 3600.0
    max_output_bytes: int = 64 * 1024
    max_artifact_bytes: int = 1024 * 1024
    max_total_artifact_bytes: int = 4 * 1024 * 1024

    name: ClassVar[str] = "opensandbox"

    def __post_init__(self) -> None:
        if type(self.domain) is not str or not self.domain or len(self.domain) > 1024:
            raise SandboxPolicyError("domain must be a host with optional port", code="invalid_config")
        parsed = urlsplit("//" + self.domain)
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment or any(c.isspace() for c in self.domain)):
            raise SandboxPolicyError("domain must not contain credentials or URL paths", code="invalid_config")
        if self.protocol not in ("http", "https") or type(self.use_server_proxy) is not bool:
            raise SandboxPolicyError("Invalid protocol or proxy configuration", code="invalid_config")
        if type(self.api_key_env) is not str or not self.api_key_env.isidentifier():
            raise SandboxPolicyError("api_key_env must name an environment variable", code="invalid_config")
        if (type(self.sandbox_ttl_seconds) not in (int, float)
                or not math.isfinite(self.sandbox_ttl_seconds) or self.sandbox_ttl_seconds <= 0):
            raise SandboxPolicyError("sandbox TTL must be positive finite seconds", code="invalid_config")
        for name, ceiling in (("max_output_bytes", 1024 * 1024),
                              ("max_artifact_bytes", 8 * 1024 * 1024),
                              ("max_total_artifact_bytes", 16 * 1024 * 1024)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise SandboxPolicyError(f"{name} is outside supported bounds", code="invalid_config")

    @property
    def revision(self) -> str:
        digest = hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()
        return f"1-sdk-{_SUPPORTED_SDK}-{digest}"

    def _config(self, sdk: Any, budget: _Budget) -> Any:
        return sdk.ConnectionConfig(domain=self.domain, protocol=self.protocol,
                                    api_key=os.environ.get(self.api_key_env, ""),
                                    use_server_proxy=self.use_server_proxy, disable_metrics=True,
                                    request_timeout=timedelta(seconds=budget.remaining()),
                                    retry_policy=sdk.RetryPolicy.disabled())

    @contextmanager
    def _connected(self, sdk: Any, sandbox_id: str, budget: _Budget) -> Iterator[Any]:
        client = None
        try:
            client = sdk.Sandbox.connect(_identity(sandbox_id),
                                         connection_config=self._config(sdk, budget),
                                         connect_timeout=timedelta(seconds=budget.remaining()),
                                         skip_health_check=True)
            budget.remaining()
            yield client
        finally:
            _close(client)

    @staticmethod
    def _policies(spec: SandboxSpec) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
        payload = spec.to_payload()
        resources = payload["resources"]
        if resources is not None:
            if (set(resources) - {"cpu", "memory"}
                    or any(type(value) is not str or not value.strip() for value in resources.values())):
                raise SandboxPolicyError("Only string CPU and memory resource limits are supported",
                                         code="unsupported_resources")
        policy = payload["network_policy"]
        if policy is not None:
            if (set(policy) - {"default_action", "egress"}
                    or policy.get("default_action") not in ("allow", "deny")):
                raise SandboxPolicyError("Network policy requires default_action and optional egress",
                                         code="unsupported_network_policy")
            rules = policy.get("egress", [])
            if type(rules) is not list or len(rules) > 128:
                raise SandboxPolicyError("Unsupported egress rules", code="unsupported_network_policy")
            for rule in rules:
                if (type(rule) is not dict or set(rule) != {"action", "target"}
                        or rule["action"] not in ("allow", "deny")
                        or type(rule["target"]) is not str or not rule["target"].strip()):
                    raise SandboxPolicyError("Unsupported egress rule fields",
                                             code="unsupported_network_policy")
        return resources, policy

    def validate(self, spec: SandboxSpec) -> None:
        """Check local policy/dependency support without making provider requests."""
        _, policy = self._policies(spec)
        sdk = _sdk()
        if policy is not None:
            try:
                sdk.NetworkPolicy(**policy)
            except Exception:
                raise SandboxPolicyError("Network policy cannot be represented by the supported SDK",
                                         code="unsupported_network_policy") from None

    def create(self, spec: SandboxSpec, *, operation_key: str, timeout: float) -> str:
        budget = _Budget(timeout)
        token = _operation_token(operation_key)
        resources, policy = self._policies(spec)
        sdk = _sdk()
        client = None
        with _translate("create"):
            try:
                client = sdk.Sandbox.create(
                    spec.image, metadata={_OPERATION_LABEL: token}, resource=resources,
                    network_policy=None if policy is None else sdk.NetworkPolicy(**policy),
                    timeout=timedelta(seconds=self.sandbox_ttl_seconds),
                    ready_timeout=timedelta(seconds=budget.remaining()),
                    connection_config=self._config(sdk, budget),
                )
                return _provider_identity(client.id)
            finally:
                _close(client)

    def find(self, operation_key: str, *, timeout: float) -> tuple[str, ...]:
        budget = _Budget(timeout)
        token = _operation_token(operation_key)
        sdk = _sdk()
        manager = None
        with _translate("find"):
            try:
                manager = sdk.Manager.create(connection_config=self._config(sdk, budget))
                result: set[str] = set()
                for page in range(1, 1001):
                    budget.remaining()
                    response = manager.list_sandbox_infos(sdk.SandboxFilter(
                        metadata={_OPERATION_LABEL: token}, page=page, page_size=100))
                    for info in response.sandbox_infos:
                        if not info.metadata or info.metadata.get(_OPERATION_LABEL) != token:
                            raise SandboxOutcomeUnknown("Provider returned mismatched discovery metadata",
                                                        code="discovery_mismatch")
                        result.add(_provider_identity(info.id))
                    if response.pagination.has_next_page is False:
                        return tuple(sorted(result))
                    if response.pagination.has_next_page is not True:
                        raise SandboxOutcomeUnknown("Provider pagination is incomplete", code="discovery_incomplete")
                raise SandboxOutcomeUnknown("Provider discovery exceeded page bound", code="discovery_incomplete")
            finally:
                _close(manager)

    @staticmethod
    def _paths(spec: SandboxSpec) -> tuple[str, str, str]:
        digest = hashlib.sha256(json.dumps(spec.to_payload(), sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
        prefix = "/tmp/.dispatcher-sdk-" + digest
        return prefix + ".source", prefix + ".stdout", prefix + ".stderr"

    def start(self, sandbox_id: str, spec: SandboxSpec, *, timeout: float) -> str:
        budget = _Budget(timeout)
        self._policies(spec)
        sdk = _sdk()
        source, stdout, stderr = self._paths(spec)
        command = ("exec " + shlex.join((*spec.interpreter, source))
                   + " > " + shlex.quote(stdout) + " 2> " + shlex.quote(stderr))
        with _translate("start"), self._connected(sdk, sandbox_id, budget) as client:
            client.files.write_file(source, spec.source, mode=600)
            budget.remaining()
            execution = client.commands.run(command, opts=sdk.RunCommandOpts(
                background=True, working_directory=spec.cwd))
            # Background completion event acknowledges submission, not process exit.
            return _provider_identity(execution.id)

    @staticmethod
    def _observation(status: Any) -> SandboxObservation:
        running, code = status.running, status.exit_code
        if running is True and code is None:
            return SandboxObservation("running")
        if running is False and type(code) is int and not (code == 0 and getattr(status, "error", None)):
            return SandboxObservation("succeeded" if code == 0 else "failed", code)
        return SandboxObservation("unknown", details={"reason": "incomplete_provider_status"})

    @classmethod
    def _status(cls, client: Any, command_id: str) -> SandboxObservation:
        status = client.commands.get_command_status(command_id)
        if getattr(status, "id", command_id) not in (None, command_id):
            raise SandboxOutcomeUnknown("Provider returned a different command identity",
                                        code="command_identity_mismatch")
        return cls._observation(status)

    def inspect(self, sandbox_id: str, command_id: str, *, timeout: float) -> SandboxObservation:
        budget = _Budget(timeout)
        _identity(command_id)
        sdk = _sdk()
        with _translate("inspect"), self._connected(sdk, sandbox_id, budget) as client:
            return self._status(client, command_id)

    @staticmethod
    def _read_bounded(client: Any, sandbox_id: str, path: str, limit: int, budget: _Budget) -> dict[str, Any]:
        budget.remaining()
        stream = client.files.read_bytes_stream(path, chunk_size=min(limit + 1, 8192))
        data = bytearray()
        try:
            for chunk in stream:
                budget.remaining()
                if type(chunk) is not bytes:
                    raise SandboxOutcomeUnknown("Invalid provider file stream", code="invalid_file_stream")
                data.extend(chunk[:max(0, limit + 1 - len(data))])
                if len(data) > limit:
                    break
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
        truncated = len(data) > limit
        body = bytes(data[:limit])
        return {"path": path, "sandbox_id": sandbox_id, "encoding": "base64",
                "data": base64.b64encode(body).decode("ascii"), "bytes_read": len(body),
                "truncated": truncated,
                "sha256": None if truncated else hashlib.sha256(body).hexdigest(),
                "reference_lifetime": "until_sandbox_destroyed_or_expired"}

    def collect(self, sandbox_id: str, command_id: str, spec: SandboxSpec, *, timeout: float) -> dict[str, Any]:
        budget = _Budget(timeout)
        _identity(command_id)
        sdk = _sdk()
        source, stdout, stderr = self._paths(spec)
        with _translate("collect"), self._connected(sdk, sandbox_id, budget) as client:
            observed = self._status(client, command_id)
            if observed.state not in ("succeeded", "failed"):
                raise SandboxOutcomeUnknown("Command has no confirmed terminal outcome", code="command_not_finished")
            result: dict[str, Any] = {"sandbox_id": sandbox_id, "command_id": command_id,
                                     "exit_code": observed.exit_code, "source_path": source,
                                     "stdout": self._read_bounded(client, sandbox_id, stdout,
                                                                  self.max_output_bytes, budget),
                                     "stderr": self._read_bounded(client, sandbox_id, stderr,
                                                                  self.max_output_bytes, budget),
                                     "artifacts": []}
            remaining = self.max_total_artifact_bytes
            for path in spec.artifacts:
                resolved = posixpath.normpath(posixpath.join(spec.cwd, path))
                artifact = self._read_bounded(client, sandbox_id, resolved,
                                              min(remaining, self.max_artifact_bytes), budget)
                remaining -= artifact["bytes_read"]
                result["artifacts"].append(artifact)
            return result

    def terminate(self, sandbox_id: str, *, timeout: float) -> bool:
        budget = _Budget(timeout)
        _identity(sandbox_id)
        sdk = _sdk()
        manager = None
        with _translate("terminate"):
            try:
                manager = sdk.Manager.create(connection_config=self._config(sdk, budget))
                try:
                    manager.kill_sandbox(sandbox_id)
                except Exception:
                    # The destroy response can be lost after it took effect.
                    # Neither success nor a delete-side 404 alone proves absence.
                    pass
                budget.remaining()
                try:
                    manager.get_sandbox_info(sandbox_id)
                except Exception as exc:
                    if getattr(exc, "status_code", None) == 404:
                        return True
                    raise
                return False
            finally:
                _close(manager)
