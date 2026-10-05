"""The narrow, lease-fenced API exposed to handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Mapping
from contextlib import nullcontext
import threading
import time

from .budget import BudgetClockUnknownError, BudgetEnvelope, ExecutionBudget, sample_clock

from .contracts import ExecutionCommandV2, ExecutionLease
from .errors import EffectRecoveryRequiredError, HandlerExecutionError, StaleFenceError
from .sqlite import SQLiteKernel

if TYPE_CHECKING:
    from ..observability import ExecutionActivity
    from .children import ChildCalls


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

    def start(self) -> _UnavailableActivity:
        return self

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


class _UnavailableChildren:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def run(self, handler_id: str, payload: Any, *, request_id: str,
            timeout_seconds: float = 300.0, handler_contract_version: int = 1) -> dict[str, Any]:
        from .children import ChildExecutionError
        raise ChildExecutionError("child_service_unavailable", self.reason)

    def wait_for(self, execution_id: str, *, request_id: str,
                 timeout_seconds: float | None = None, reason: str = "child_result") -> dict[str, Any]:
        from .children import ChildExecutionError
        raise ChildExecutionError("child_service_unavailable", self.reason, execution_id=execution_id)


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
        self._observation_lifecycle_lock = threading.Lock()
        self._observation_closed = False
        self._observation_start_done = threading.Event()
        self._observation_start_done.set()
        self._completion_readers: set[Any] = set()
        self._completion_readers_done = threading.Event()
        self._completion_readers_done.set()
        self._budget_lock = threading.RLock()
        self._budget_capture = None
        self._monitor_checkpoint = None
        self._entered = False
        self._entry_confirmed = False
        self.activity: ExecutionActivity = _UnavailableActivity("observation_unavailable")
        self.children: ChildCalls = _UnavailableChildren(
            self._service_spec.get("child_service_error", "child service not configured"))
        self._journal: Any = None

    def _sample(self):
        if self._service_spec.get("guard_budget") and self._budget_envelope is not None:
            return sample_clock(wall_time=self._budget_envelope.checkpoint.wall_at)
        return sample_clock(wall_time=self._kernel._wall_time())

    def _capture_budget(self, *, timeout_seconds: float | None = None) -> BudgetEnvelope:
        envelope = self.budget_envelope
        if self._observation_closed:
            return envelope.recheckpoint(sample=self._sample())
        if not self._service_spec.get("guard_budget"):
            return envelope.recheckpoint(sample=self._sample())
        if self._service_spec.get("entry_protocol") and not self._entry_confirmed:
            # The durable pending-entry record already guards this capture.
            # Its final ACK commits the strongest floor before user code runs;
            # another attempt cannot consume an interrupted entry's allowance.
            return envelope.recheckpoint(sample=sample_clock(wall_time=self._kernel._wall_time()))
        view = envelope.view(sample=self._sample())
        remaining = view.remaining_work_seconds
        timeout = .1 if remaining is None else min(.1, max(.001, remaining))
        try:
            from .budget_capture import _KernelBudgetCapture
            from ._process_runtime import _capture_budget_until
            if self._budget_capture is None:
                self._budget_capture = _KernelBudgetCapture(self._kernel, self.command.execution_id)
            if timeout_seconds is not None:
                return self._budget_capture(envelope, timeout_seconds=min(timeout, timeout_seconds))
            # Short control collisions consume the existing work window. A
            # budget read must not turn one transient ACK failure into a
            # business error while its exact live owner can still publish.
            deadline = time.monotonic() + (timeout if remaining is None else max(0., remaining))
            def captured(updated):
                self._budget_envelope = self.budget_envelope.with_clock_floor(updated.checkpoint)
            def capture(current, *, timeout_seconds):
                if not self.effects._is_active():
                    raise HandlerExecutionError("execution_authority_revoked",
                                                "handler authority revoked during budget inspection")
                return self._budget_capture(current, timeout_seconds=timeout_seconds)
            return _capture_budget_until(envelope, capture, deadline, on_capture=captured)
        except BaseException as error:
            captured = getattr(error, "budget_sample_envelope", None)
            if captured is not None:
                self._budget_envelope = envelope.with_clock_floor(captured.checkpoint)
            raise

    @property
    def budget_envelope(self) -> BudgetEnvelope:
        if self._budget_envelope is None:
            self._budget_envelope = self._kernel.admission_budget(self.lease)
        return self._budget_envelope

    @property
    def budget(self) -> ExecutionBudget:
        """Current Run, execution, parent, and local constraints, without lease guesses."""
        with self._budget_lock:
            if not self._service_spec.get("guard_budget"):
                sample = self._sample()
                view = self.budget_envelope.view(sample=sample)
                if view.clock_status == "trusted":
                    self._budget_envelope = self.budget_envelope.recheckpoint(sample=sample)
                return view
            self._budget_envelope = self._capture_budget()
            # Native elapsed projection is also a retained local fact. Keep
            # the exact public snapshot in outcomes rather than a checkpoint
            # from before its acknowledgement completed.
            self._budget_envelope = self._budget_envelope.recheckpoint(sample=self._sample())
            return self._budget_envelope.view(sample=self._budget_envelope.checkpoint)

    def derive_budget(self, *, source: str, origin_id: str,
                      timeout_seconds: float | None = None, deadline_at: float | None = None,
                      reserve_seconds: float = 0.0) -> BudgetEnvelope:
        with self._budget_lock:
            self.budget
            return self.budget_envelope.derive(source=source, origin_id=origin_id,
                timeout_seconds=timeout_seconds, deadline_at=deadline_at,
                reserve_seconds=reserve_seconds, sample=self._sample())

    def _monitor_budget(self, *, timeout_seconds: float = .1) -> ExecutionBudget:
        """One bounded capture so independent timing never waits a work window."""
        deadline = time.monotonic() + timeout_seconds
        if not self._budget_lock.acquire(timeout=timeout_seconds):
            raise TimeoutError("budget monitor lock admission elapsed")
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("budget monitor admission elapsed")
            if self._budget_capture is None or self._budget_capture._pending is None:
                with self._kernel._control_lock(remaining):
                    self._kernel._assert_budget_clock(self._kernel._connection, self.command.execution_id)
                    limits = self._kernel._connection.execute(
                        "SELECT l.envelope_json,e.attempt,e.fence FROM kernel_execution_limits l "
                        "JOIN kernel_executions e ON e.execution_id=l.execution_id WHERE l.execution_id=?",
                        (self.command.execution_id,)).fetchone()
                    if limits is not None and (limits[1], limits[2]) == (self.lease.attempt, self.lease.fence):
                        import json
                        canonical = BudgetEnvelope.from_dict(json.loads(limits[0]))
                        checkpoint = canonical.checkpoint
                        previous = self._monitor_checkpoint
                        if (previous is None or (checkpoint.domain_id == previous.domain_id
                                and checkpoint.elapsed_at > previous.elapsed_at)):
                            # Another observer supplied a committed capture.
                            # Consume it once; an unchanged checkpoint cannot
                            # postpone this monitor's next guarded wall sample.
                            self._budget_envelope = self.budget_envelope.with_clock_floor(checkpoint)
                            self._monitor_checkpoint = checkpoint
                            return self._budget_envelope.view(sample=self._sample())
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("budget monitor admission elapsed")
            self._budget_envelope = self._capture_budget(timeout_seconds=remaining)
            self._monitor_checkpoint = self._budget_envelope.checkpoint
            return self._budget_envelope.view(sample=self._sample())
        finally:
            self._budget_lock.release()

    def _project_budget(self) -> ExecutionBudget:
        """Monitor retained authority without competing with its live writer."""
        envelope = self.budget_envelope
        lock = self._kernel._lock
        if lock.acquire(blocking=False):
            try:
                limits = self._kernel._connection.execute(
                    "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?",
                    (self.command.execution_id,)).fetchone()
                if limits is not None:
                    import json
                    canonical = BudgetEnvelope.from_dict(json.loads(limits[0]))
                    envelope = envelope.with_clock_floor(canonical.checkpoint)
            finally:
                lock.release()
        return envelope.view(sample=sample_clock(wall_time=envelope.checkpoint.wall_at))

    def _enter_handler(self) -> None:
        """Called once by the invocation wrapper immediately before user code."""
        with self._entry_lock:
            if self._entered:
                return
            self._start_observation()
            handler_children = None
            if self._journal is not None and self._service_spec.get("allow_children", True):
                from .children import HandlerChildren
                handler_children = HandlerChildren(self._kernel, self.command, self.lease,
                    self.budget_envelope, self._service_spec, journal=self._journal,
                    _budget_context=self)
                self.children = handler_children
            with self._budget_lock:
                self._budget_envelope = self._capture_budget()
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
            if handler_children is not None:
                handler_children.budget_envelope = envelope
            self.activity.phase("handler_entered")

    def _start_observation(self) -> None:
        with self._observation_lifecycle_lock:
            if self._observation_closed:
                return
            self._observation_start_done.clear()
        try:
            from ..observability import ActivityRecorder, ObservationIdentity, ObservationJournal, ObservationOptions
            spec = self._service_spec
            if not spec.get("journal_path"):
                return
            options = ObservationOptions(**spec.get("options", {}))
            self._journal = ObservationJournal._open_existing_writer(
                spec["journal_path"], kernel_path=self._kernel.db_path,
                source_id=spec["source_id"], options=options, clock=self._kernel._wall_time)
            identity = ObservationIdentity(self.command.execution_id, self.lease.attempt, self.lease.fence,
                run_id=spec.get("run_id"), task_id=spec.get("task_id"), generation=spec.get("generation", 0),
                task_attempt=spec.get("task_attempt"))
            def confirm(key, *, details, timeout):
                receipt = self._kernel.confirm_progress(self.lease, key, timeout_seconds=timeout)
                return {**receipt, "revision": receipt["progress_revision"], "advanced": receipt["new"]}

            with self._observation_lifecycle_lock:
                if self._observation_closed:
                    return
            recorder = ActivityRecorder(self._journal, identity, options=options,
                progress_confirm=confirm, clock=self._kernel._wall_time, start=False,
                source_scope="handler", bind_current=True,
                _defer_collector_registration=spec.get("_defer_collector_registration", False))
            with self._observation_lifecycle_lock:
                self.activity = recorder
                closing = self._observation_closed
                if not closing:
                    recorder.start()
            if closing:
                recorder.close()
        except Exception as exc:
            self.activity = _UnavailableActivity(f"observation_unavailable:{type(exc).__name__}")
            if self._journal is None:
                self.children = _UnavailableChildren(f"{type(exc).__name__}: {exc}")
        finally:
            self._observation_start_done.set()

    def _reserve_completion_reader(self, owner: Any, budget: Any) -> None:
        """Admit one storage lifetime against close under its original bound."""
        budget.check()
        remaining = max(0., budget.deadline - time.monotonic())
        acquired = self._observation_lifecycle_lock.acquire(timeout=remaining)
        if not acquired:
            budget.check()
            raise TimeoutError("completion reader lifecycle admission timed out")
        try:
            budget.check()
            if self._observation_closed:
                raise BudgetClockUnknownError("completion_clock_context_closed")
            self._completion_readers.add(owner)
            self._completion_readers_done.clear()
        finally:
            self._observation_lifecycle_lock.release()

    def _release_completion_reader(self, owner: Any, deadline: float) -> bool:
        # Only after actual physical close, or before any connection opened.
        # This lock never covers SQLite or a user's handler.
        if not self._observation_lifecycle_lock.acquire(timeout=max(0., deadline - time.monotonic())):
            return False
        try:
            self._completion_readers.discard(owner)
            if not self._completion_readers:
                self._completion_readers_done.set()
            return True
        finally:
            self._observation_lifecycle_lock.release()

    def _completion_readers_pending(self) -> bool:
        return not self._completion_readers_done.is_set()

    def _drain_completion_readers(self, deadline: float) -> bool:
        remaining = max(0., deadline - time.monotonic())
        if not self._observation_lifecycle_lock.acquire(timeout=remaining):
            return True
        try:
            owners = tuple(self._completion_readers)
        finally:
            self._observation_lifecycle_lock.release()
        for owner in owners:
            if time.monotonic() >= deadline:
                break
            owner.drain(deadline)
        return self._completion_readers_pending()

    def close(self) -> dict[str, Any]:
        with self._observation_lifecycle_lock:
            self._observation_closed = True
            activity = self.activity
        return {**activity.close(), "budget_checkpoint": self._finish_budget_checkpoint()}

    def _finish_budget_checkpoint(self, timeout: float = .1) -> dict[str, Any]:
        """Retry only an owned captured fact; do not sample or renew business time."""
        checkpoint = {"state": "confirmed"}
        deadline = time.monotonic() + timeout
        if self._budget_capture is not None:
            acquired = self._budget_lock.acquire(timeout=timeout)
            try:
                remaining = deadline - time.monotonic()
                if not acquired or remaining <= 0:
                    checkpoint = {"state": "unknown", "reason": "budget checkpoint cleanup admission elapsed"}
                else:
                    self._budget_envelope = self._budget_capture.finish_pending(
                        self.budget_envelope, timeout_seconds=remaining)
            except Exception as error:
                checkpoint = {"state": "unknown", "reason": f"{type(error).__name__}: {error}"[:4096]}
            finally:
                if acquired:
                    self._budget_lock.release()
        return checkpoint

    def is_active(self) -> bool:
        """Expose cooperative cancellation without leaking Kernel internals."""
        return self.effects.is_active()
