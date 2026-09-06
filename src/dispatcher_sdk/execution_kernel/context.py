"""The narrow, lease-fenced API exposed to handlers."""

from __future__ import annotations

from typing import Any, Callable

from .contracts import ExecutionCommandV2, ExecutionLease
from .errors import EffectRecoveryRequiredError, StaleFenceError
from .sqlite import SQLiteKernel


class HandlerEffects:
    def __init__(
        self,
        kernel: SQLiteKernel,
        lease: ExecutionLease,
        is_active: Callable[[], bool],
    ) -> None:
        self._kernel = kernel
        self._lease = lease
        self._is_active = is_active
        self._effect_ids: list[str] = []

    @property
    def effect_ids(self) -> list[str]:
        return list(self._effect_ids)

    def _verify_active(self) -> None:
        if not self._is_active():
            raise StaleFenceError("handler authority has been revoked")
        self._kernel.verify(self._lease)

    def is_active(self) -> bool:
        """Return whether this handler still owns the live execution fence."""
        try:
            self._verify_active()
        except StaleFenceError:
            return False
        return True

    def execute_once(
        self,
        effect_id: str,
        name: str,
        request: Any,
        perform: Callable[[], Any],
    ) -> Any:
        """Execute once, or return a previously committed response.

        A crash after preparation is intentionally not replayed under a newer
        fence.  The storage API marks that record indeterminate and requires an
        explicit recovery decision.
        """

        if not callable(perform):
            raise TypeError("perform must be callable")
        self._verify_active()
        record = self._kernel.prepare_effect(
            self._lease,
            effect_id=effect_id,
            name=name,
            request=request,
        )
        if record.state == "committed":
            if effect_id not in self._effect_ids:
                self._effect_ids.append(effect_id)
            return record.response
        claim = self._kernel.claim_effect(self._lease, effect_id)
        assert claim.claim_id is not None
        self._verify_active()
        try:
            response = perform()
        except BaseException as exc:
            try:
                self._verify_active()
                self._kernel.mark_effect_indeterminate(
                    effect_id,
                    {
                        "code": "effect_call_raised",
                        "message": str(exc),
                        "exception_type": type(exc).__name__,
                    },
                    self._lease,
                    claim.claim_id,
                )
            except StaleFenceError:
                raise
            raise EffectRecoveryRequiredError(
                effect_id, "effect call raised with an uncertain external outcome"
            ) from exc
        self._verify_active()
        try:
            committed = self._kernel.commit_effect(
                effect_id, response, self._lease, claim.claim_id
            )
        except BaseException as exc:
            try:
                self._verify_active()
                self._kernel.mark_effect_indeterminate(
                    effect_id,
                    {
                        "code": "effect_commit_failed",
                        "message": "effect returned but its durable commit failed",
                    },
                    self._lease,
                    claim.claim_id,
                )
            except BaseException:
                raise exc
            raise EffectRecoveryRequiredError(
                effect_id, "effect response could not be durably committed"
            ) from exc
        if effect_id not in self._effect_ids:
            self._effect_ids.append(effect_id)
        return committed.response


class HandlerContext:
    """Execution identity plus the only supported effect capability."""

    def __init__(
        self,
        command: ExecutionCommandV2,
        lease: ExecutionLease,
        effects: HandlerEffects,
    ) -> None:
        self.command = command
        self.lease = lease
        self.effects = effects

    def is_active(self) -> bool:
        """Expose cooperative cancellation without leaking Kernel internals."""
        return self.effects.is_active()
