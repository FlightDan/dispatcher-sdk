"""The narrow, lease-fenced API exposed to handlers."""

from __future__ import annotations

from typing import Any, Callable, Mapping
from contextlib import nullcontext
import threading

from .budget import BudgetEnvelope, ExecutionBudget, sample_clock

from .contracts import ExecutionCommandV2, ExecutionLease
from .errors import EffectRecoveryRequiredError, HandlerExecutionError, StaleFenceError
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


class _UnavailableActivity:
    """Telemetry failure has no authority over the handler's result."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def observe_process(self, process: Any, **kwargs: Any):
        class UnknownProcess:
            def snapshot(inner_self):
                return {"state": "unknown", "unknown_reason": self.reason}
        return UnknownProcess()

    def __getattr__(self, name: str):
        def unavailable(*args, **kwargs):
            receipt = {"state": "unknown", "reason": self.reason}
            return nullcontext(receipt) if name == "wait" else receipt
        return unavailable


class HandlerContext:
    """Fenced effects, authoritative timing, activity, and bounded children."""

    def __init__(
        self,
        command: ExecutionCommandV2,
        lease: ExecutionLease,
        effects: HandlerEffects,
        *,
        budget_envelope: BudgetEnvelope | None = None,
        service_spec: Mapping[str, Any] | None = None,
    ) -> None:
        self.command = command
        self.lease = lease
        self.effects = effects
        self._kernel = effects._kernel
        self._budget_envelope = budget_envelope
        self._service_spec = dict(service_spec or {})
        self._entry_lock = threading.Lock()
        self._budget_lock = threading.RLock()
        self._entered = False
        self.activity: Any = _UnavailableActivity("observation_unavailable")
        self.children: Any = None
        self._journal: Any = None

    def _sample(self):
        return sample_clock(wall_time=self._kernel._wall_time())

    @property
    def budget_envelope(self) -> BudgetEnvelope:
        if self._budget_envelope is None:
            self._budget_envelope = self._kernel.admission_budget(self.lease)
        return self._budget_envelope

    @property
    def budget(self) -> ExecutionBudget:
        """Current Run, execution, parent, and local constraints, without lease guesses."""
        with self._budget_lock:
            sample = self._sample()
            view = self.budget_envelope.view(sample=sample)
            if view.clock_status == "trusted":
                self._budget_envelope = self.budget_envelope.recheckpoint(sample=sample)
            return view

    def derive_budget(self, *, source: str, origin_id: str,
                      timeout_seconds: float | None = None, deadline_at: float | None = None,
                      reserve_seconds: float = 0.0) -> BudgetEnvelope:
        with self._budget_lock:
            self.budget
            return self.budget_envelope.derive(source=source, origin_id=origin_id,
                timeout_seconds=timeout_seconds, deadline_at=deadline_at,
                reserve_seconds=reserve_seconds, sample=self._sample())

    def _enter_handler(self) -> None:
        """Called once by the invocation wrapper immediately before user code."""
        with self._entry_lock:
            if self._entered:
                return
            self._start_observation()
            if self._journal is not None:
                from .children import HandlerChildren
                self.children = HandlerChildren(self._kernel, self.command, self.lease,
                    self.budget_envelope, self._service_spec, journal=self._journal)
            envelope = self.budget_envelope.enter_handler(self.command.timeout_seconds,
                origin_id="execution:" + self.command.execution_id, sample=self._sample())
            if not self._service_spec.get("entry_protocol"):
                envelope = self._kernel.record_execution_budget(self.lease, envelope)
            self._budget_envelope = envelope
            view = envelope.view(sample=self._sample())
            if view.remaining_work_seconds is None or view.remaining_work_seconds <= 0:
                raise HandlerExecutionError("execution_deadline_exhausted",
                    "execution has no trusted remaining work time", details=view.to_dict())
            self._entered = True
            if self.children is not None:
                self.children.budget_envelope = envelope
            self.activity.phase("handler_entered")

    def _start_observation(self) -> None:
        try:
            from ..observability import ActivityRecorder, ObservationIdentity, ObservationJournal, ObservationOptions
            spec = self._service_spec
            if not spec.get("journal_path"):
                return
            options = ObservationOptions(**spec.get("options", {}))
            self._journal = ObservationJournal(spec["journal_path"], kernel_path=self._kernel.db_path,
                source_id=spec["source_id"], options=options)
            identity = ObservationIdentity(self.command.execution_id, self.lease.attempt, self.lease.fence,
                run_id=spec.get("run_id"), task_id=spec.get("task_id"), generation=spec.get("generation", 0),
                task_attempt=spec.get("task_attempt"))
            try:
                self._journal.bind_current(identity)
            except Exception:
                # The driver normally bound this identity already. A short
                # writer collision must not discard the handler's byte cache.
                pass

            def confirm(key, *, details, timeout):
                receipt = self._kernel.confirm_progress(self.lease, key, timeout_seconds=timeout)
                return {**receipt, "revision": receipt["progress_revision"], "advanced": receipt["new"]}

            self.activity = ActivityRecorder(self._journal, identity, options=options,
                progress_confirm=confirm, clock=self._kernel._wall_time, start=True, source_scope="handler")
        except Exception as exc:
            self.activity = _UnavailableActivity(f"observation_unavailable:{type(exc).__name__}")

    def close(self) -> dict[str, Any]:
        return self.activity.close()

    def is_active(self) -> bool:
        """Expose cooperative cancellation without leaking Kernel internals."""
        return self.effects.is_active()
