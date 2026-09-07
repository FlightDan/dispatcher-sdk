"""Application-scoped, read-only views of Kernel effect recovery."""

from dataclasses import dataclass
from typing import Protocol

from ..execution_kernel import EffectRecord, ExecutionKernel, ExecutionNotFoundError, ExecutionSnapshot
from .contracts import OrchestrationError, RevisionConflict
from .types import RunSnapshot


@dataclass(frozen=True)
class RecoveryDetails:
    """One current effect requiring a decision, with its application identity.

    ``attempt`` is the zero-based application attempt index, not the Kernel's
    execution attempt counter. ``run_revision`` identifies the initial Run
    read; it is not an atomic cross-store snapshot revision. Re-query after
    each resolution: an execution can have more than one uncertain effect.
    """

    run_id: str
    run_revision: int
    task_id: str
    attempt: int
    execution: ExecutionSnapshot
    effect: EffectRecord


class _RecoveryReader(Protocol):
    kernel: ExecutionKernel

    def get_run(self, run_id: str) -> RunSnapshot: ...

    def inspect_execution(self, execution_id: str) -> ExecutionSnapshot: ...


class RecoveryMixin:
    def inspect_recoveries(self: _RecoveryReader, run_id: str) -> list[RecoveryDetails]:
        """Read current recovery pointers for this Run without syncing or reaping.

        Kernel authority is inspected even when the persisted Run view is stale.
        Only dispatched current application attempts are considered. Pending
        command deliveries without a Kernel execution are skipped. Each effect
        is paired with an unchanged execution revision using bounded re-reads;
        continuous changes raise ``RevisionConflict`` for the caller to retry.
        Different entries are not one atomic snapshot. Resolution must still
        use the effect's revision and an explicit, stable recovery identity.
        """
        state = self.get_run(run_id)
        result = []
        for task_id, task in state["tasks"].items():
            index = len(task["attempts"]) - 1
            attempt = task["attempts"][index]
            if not attempt["dispatched"]:
                continue
            execution_id = attempt["command"]["execution_id"]
            for _ in range(3):
                try:
                    execution = self.inspect_execution(execution_id)
                except ExecutionNotFoundError:
                    if attempt["kernel_revision"]:
                        raise
                    break
                if execution.state != "recovery_required":
                    break
                if execution.recovery_effect_id is None:
                    raise OrchestrationError("Kernel recovery execution has no effect")
                effect = self.kernel.get_effect(execution.recovery_effect_id)
                after = self.inspect_execution(execution_id)
                if after.revision != execution.revision:
                    continue
                if (type(effect) is not EffectRecord
                        or effect.effect_id != execution.recovery_effect_id
                        or effect.execution_id != execution_id
                        or effect.state != "indeterminate"):
                    raise OrchestrationError("Kernel recovery effect does not match the execution")
                result.append(RecoveryDetails(
                    run_id, state["revision"], task_id, index, execution, effect))
                break
            else:
                raise RevisionConflict("recovery changed during inspection; retry the query")
        return result


__all__ = ["RecoveryDetails"]
