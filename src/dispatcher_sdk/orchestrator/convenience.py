"""Atomic task submission with caller-owned replay identity."""

from __future__ import annotations

from typing import Any

from ..execution_kernel import ExecutionCommandV2, RetryPolicy
from .contracts import CommandConflict, OrchestrationError, digest, identifier, integer
from .operations import Operations
from .types import RunSnapshot


_UNSET = object()


def _submission_ids(run_id: str, task_id: str, request_id: str, generation: int = 0) -> dict[str, str]:
    identity = digest(["dispatcher-sdk.submit-task.v1", run_id, task_id, request_id]
                      if generation == 0 else
                      ["dispatcher-sdk.submit-task.v2", run_id, generation, task_id, request_id])
    version = "v1" if generation == 0 else "v2"
    return {kind: f"sdk-submit-{version}:{kind}:{identity}"
            for kind in ("execution", "idempotency", "watch", "command")}


class ConvenienceMixin:
    def submit_task(
        self, run_id: str, task_id: str, *, request_id: str,
        expected_revision: int, handler_id: str, payload: Any,
        timeout_seconds: float, handler_contract_version: int = 1,
        dependencies: list[str] | None = None, watch_target: Any = _UNSET,
        dispatch: bool = True, retry_policy: RetryPolicy | None = None,
        expected_generation: int | None = None,
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
        if expected_generation is not None:
            integer(expected_generation, "expected_generation")
        if type(dispatch) is not bool:
            raise OrchestrationError("dispatch must be a boolean")
        policy = RetryPolicy(max_attempts=1) if retry_policy is None else retry_policy
        # A generation-0 receipt remains replayable after a Run is reopened.
        # Find that legacy identity before enforcing the new-generation CAS;
        # a replay is resolved by apply_operations before it reads current Run
        # state and cannot create another execution.
        identities = _submission_ids(run_id, task_id, request_id, 0)
        # A generation-0 command predates the recovery fence.  Treat an
        # explicit ``expected_generation=0`` as the same legacy identity so a
        # caller can safely add the new argument while replaying an old
        # response after reopen.
        receipt = (self.get_command_receipt(run_id, identities["command"])
                   if expected_generation in (None, 0) else None)
        replay_generation = None if receipt is not None else expected_generation
        if receipt is None:
            current_generation = int(self.get_run(run_id).get("generation", 0))
            if current_generation and expected_generation is None:
                raise OrchestrationError("expected_generation is required after Run recovery")
            if expected_generation is not None and expected_generation != current_generation:
                raise OrchestrationError("run generation changed")
            identities = _submission_ids(run_id, task_id, request_id, current_generation)
            receipt = self.get_command_receipt(run_id, identities["command"])
            # Generation zero remains compatible with the pre-fence request
            # digest, regardless of whether the caller supplied the optional
            # zero explicitly.
            replay_generation = None if current_generation == 0 else expected_generation

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

        try:
            return self.apply_operations(
                run_id, command_id=identities["command"], expected_revision=expected_revision,
                operations=operations(receipt), expected_generation=replay_generation)
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
                operations=operations(committed), expected_generation=replay_generation)
