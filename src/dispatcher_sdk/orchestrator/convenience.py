"""Atomic task submission with caller-owned replay identity."""

from __future__ import annotations

from typing import Any

from ..execution_kernel import ExecutionCommandV2, RetryPolicy
from .contracts import CommandConflict, OrchestrationError, digest, identifier, integer
from .operations import Operations
from .types import RunSnapshot


_UNSET = object()


def _submission_ids(run_id: str, task_id: str, request_id: str) -> dict[str, str]:
    identity = digest(["dispatcher-sdk.submit-task.v1", run_id, task_id, request_id])
    return {kind: f"sdk-submit-v1:{kind}:{identity}"
            for kind in ("execution", "idempotency", "watch", "command")}


class ConvenienceMixin:
    def submit_task(
        self, run_id: str, task_id: str, *, request_id: str,
        expected_revision: int, handler_id: str, payload: Any,
        timeout_seconds: float, handler_contract_version: int = 1,
        dependencies: list[str] | None = None, watch_target: Any = _UNSET,
        dispatch: bool = True, retry_policy: RetryPolicy | None = None,
    ) -> RunSnapshot:
        """Add a task, optionally watch it, and enqueue dispatch atomically.

        Reuse the same request identity and arguments after response loss. The
        original handler binding is retained on replay, while apply_operations
        still checks every operation and the original expected revision.
        This does not flush the outbox, execute handlers, or finish the Run.
        """
        for label, value in (("run_id", run_id), ("task_id", task_id), ("request_id", request_id)):
            identifier(value, label)
        integer(expected_revision, "expected_revision")
        if type(dispatch) is not bool:
            raise OrchestrationError("dispatch must be a boolean")
        policy = RetryPolicy(max_attempts=1) if retry_policy is None else retry_policy
        identities = _submission_ids(run_id, task_id, request_id)

        def operations(receipt):
            fields = dict(
                execution_id=identities["execution"], idempotency_key=identities["idempotency"],
                correlation_id=run_id, causation_id=identities["command"],
                handler_id=handler_id, handler_contract_version=handler_contract_version,
                payload=payload, timeout_seconds=timeout_seconds, retry_policy=policy,
            )
            if receipt is None:
                if self.runtime is None:
                    raise OrchestrationError("submit_task requires a Runtime for a new request")
                command = self.runtime.command(**fields)
            else:
                try:
                    original = receipt["tasks"][task_id]["attempts"][0]["command"]
                    if (receipt["run_id"] != run_id
                            or original["execution_id"] != identities["execution"]
                            or original["idempotency_key"] != identities["idempotency"]
                            or original["causation_id"] != identities["command"]
                            or not original["registry_revision"].startswith("handler-v1:")):
                        raise ValueError("foreign receipt")
                    binding = original["registry_revision"]
                except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
                    raise CommandConflict("request identity is already used by another command") from error
                command = ExecutionCommandV2(registry_revision=binding, **fields)
            values = [Operations.add_task(task_id, command, dependencies=dependencies)]
            if watch_target is not _UNSET:
                values.append(Operations.watch_task(
                    task_id, watch_id=identities["watch"], target=watch_target))
            if dispatch:
                values.append(Operations.dispatch(task_id))
            return values

        receipt = self.get_command_receipt(run_id, identities["command"])
        try:
            return self.apply_operations(
                run_id, command_id=identities["command"], expected_revision=expected_revision,
                operations=operations(receipt))
        except CommandConflict:
            if receipt is not None:
                raise
            # Another submitter may have committed after our first read, using
            # a different deployment binding. Rebuild only that binding; the
            # underlying receipt digest still rejects changed request content.
            committed = self.get_command_receipt(run_id, identities["command"])
            if committed is None:
                raise
            return self.apply_operations(
                run_id, command_id=identities["command"], expected_revision=expected_revision,
                operations=operations(committed))
