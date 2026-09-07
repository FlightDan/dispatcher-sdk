from __future__ import annotations

from contextlib import closing

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from dispatcher_sdk.execution_kernel import (
    CASConflictError,
    EffectConflictError,
    EffectRecoveryRequiredError,
    ExecutionCommandV2,
    ExecutionError,
    ExecutionResultV2,
    IdempotencyConflictError,
    InvalidStateTransitionError,
    ResultConflictError,
    RetryPolicy,
    SQLiteKernel,
    StaleFenceError,
    StorageIsolationError,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value
        self.lock = threading.Lock()

    def __call__(self) -> float:
        with self.lock:
            return self.value

    def advance(self, seconds: float) -> None:
        with self.lock:
            self.value += seconds


def make_command(
    execution_id: str,
    *,
    key: str | None = None,
    registry: str = "registry-1",
    attempts: int = 1,
    retry_timeouts: bool = False,
) -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=key or f"key-{execution_id}",
        registry_revision=registry,
        correlation_id=f"correlation-{execution_id}",
        causation_id=None,
        handler_id="echo",
        handler_contract_version=1,
        retry_policy=RetryPolicy(
            max_attempts=attempts,
            initial_backoff_seconds=0,
            backoff_multiplier=1,
            max_backoff_seconds=0,
            retry_timeouts=retry_timeouts,
        ),
        timeout_seconds=2,
        payload={"execution": execution_id},
    )


def make_result(
    kernel: SQLiteKernel,
    lease,
    *,
    result_id: str | None = None,
    status: str = "succeeded",
    retryable: bool = False,
    attempt: int | None = None,
    fence: int | None = None,
    effect_ids: list[str] | None = None,
) -> ExecutionResultV2:
    snapshot = kernel.get(lease.execution_id)
    error = None
    if status != "succeeded":
        error = ExecutionError(
            code="attempt_error",
            message="attempt failed",
            retryable=retryable,
            details={},
        )
    return ExecutionResultV2(
        result_id=result_id or f"result-{lease.execution_id}-{lease.attempt}",
        execution_id=lease.execution_id,
        status=status,
        attempt=lease.attempt if attempt is None else attempt,
        fence=lease.fence if fence is None else fence,
        effect_ids=[] if effect_ids is None else effect_ids,
        started_at=snapshot.started_at,
        completed_at=max(snapshot.started_at, kernel.current_time()),
        correlation_id=snapshot.command.correlation_id,
        causation_id=snapshot.command.causation_id,
        value={"ok": True} if status == "succeeded" else None,
        error=error,
    )


class SQLiteKernelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "shared.sqlite3"
        self.clock = Clock()
        self.kernel = SQLiteKernel(
            self.path,
            now=self.clock,
            default_lease_seconds=5,
            outbox_max_attempts=2,
        )

    def tearDown(self) -> None:
        self.kernel.close()
        self.temp.cleanup()

    def running(self, execution_id: str, **options):
        self.kernel.submit(make_command(execution_id, **options))
        lease = self.kernel.claim("owner", registry_revision=options.get("registry", "registry-1"))
        self.assertIsNotNone(lease)
        return self.kernel.start(lease)

    def test_concurrent_idempotent_submit_and_conflicts_fail_closed(self) -> None:
        second = SQLiteKernel(self.path, now=self.clock)
        barrier = threading.Barrier(2)
        cmd = make_command("same", key="same-key")

        def submit(kernel):
            barrier.wait()
            return kernel.submit(cmd)

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                snapshots = list(executor.map(submit, (self.kernel, second)))
            self.assertEqual([item.execution_id for item in snapshots], ["same", "same"])
            self.assertEqual(len(self.kernel.events("same")), 1)
            with self.assertRaises(IdempotencyConflictError):
                second.submit(make_command("other", key="same-key"))
            changed = make_command("same", key="same-key").to_dict()
            changed["payload"] = {"different": True}
            with self.assertRaises(IdempotencyConflictError):
                second.submit(ExecutionCommandV2.from_dict(changed))
        finally:
            second.close()

    def test_concurrent_claim_has_one_winner(self) -> None:
        self.kernel.submit(make_command("claim-once"))
        second = SQLiteKernel(self.path, now=self.clock)
        barrier = threading.Barrier(2)

        def claim(kernel, owner):
            barrier.wait()
            return kernel.claim(owner, registry_revision="registry-1")

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(claim, self.kernel, "one"),
                    executor.submit(claim, second, "two"),
                ]
                leases = [future.result() for future in futures]
            self.assertEqual(sum(item is not None for item in leases), 1)
            self.assertEqual(self.kernel.get("claim-once").attempt, 1)
        finally:
            second.close()

    def test_atomic_claim_and_start_preserves_both_revisioned_transitions(self) -> None:
        self.kernel.submit(make_command("atomic-start"))
        lease = self.kernel.claim_and_start(
            "runtime-owner",
            lease_seconds=1,
            start_safety_seconds=7,
            registry_revision="registry-1",
        )
        self.assertIsNotNone(lease)
        assert lease is not None
        snapshot = self.kernel.get("atomic-start")
        self.assertEqual(snapshot.state, "running")
        self.assertEqual(snapshot.revision, 3)
        self.assertEqual(lease.revision, 3)
        self.assertEqual(lease.expires_at, 109.0)
        events = self.kernel.events("atomic-start")
        self.assertEqual(
            [
                (item["revision"], item["from_state"], item["to_state"])
                for item in events
            ],
            [(1, None, "queued"), (2, "queued", "leased"), (3, "leased", "running")],
        )

    def test_stale_attempt_fence_revision_and_expiry_are_rejected(self) -> None:
        lease = self.running("stale", attempts=3)
        with self.assertRaises(StaleFenceError):
            self.kernel.complete(lease, make_result(self.kernel, lease, attempt=2))
        with self.assertRaises(StaleFenceError):
            self.kernel.complete(lease, make_result(self.kernel, lease, fence=2))
        renewed = self.kernel.renew(lease, lease_seconds=2)
        with self.assertRaises(StaleFenceError):
            self.kernel.verify(lease)
        self.clock.advance(3)
        with self.assertRaises(StaleFenceError):
            self.kernel.verify(renewed)
        redelivered = self.kernel.reap()[0]
        self.assertEqual(redelivered.state, "queued")
        fresh = self.kernel.claim("new-owner", registry_revision="registry-1")
        self.assertGreater(fresh.fence, renewed.fence)
        with self.assertRaises(StaleFenceError):
            self.kernel.start(renewed)

    def test_retry_rules_and_exhaustion_use_dead(self) -> None:
        nonretryable = self.running("permanent", attempts=3)
        failed = self.kernel.complete(
            nonretryable,
            make_result(self.kernel, nonretryable, status="failed", retryable=False),
        )
        self.assertEqual(failed.state, "failed")

        retryable = self.running("retry", attempts=2)
        queued = self.kernel.complete(
            retryable,
            make_result(self.kernel, retryable, status="failed", retryable=True),
        )
        self.assertEqual(queued.state, "queued")
        second = self.kernel.start(
            self.kernel.claim("owner", registry_revision="registry-1")
        )
        dead = self.kernel.complete(
            second,
            make_result(self.kernel, second, status="failed", retryable=True),
        )
        self.assertEqual(dead.state, "dead")
        self.assertEqual(dead.result.error.code, "retry_exhausted")

        timeout = self.running("timeout-no-retry", attempts=2, retry_timeouts=False)
        timed_out = self.kernel.complete(
            timeout,
            make_result(self.kernel, timeout, status="timed_out", retryable=True),
        )
        self.assertEqual(timed_out.state, "timed_out")

        retry_timeout = self.running("timeout-retry", attempts=2, retry_timeouts=True)
        queued_timeout = self.kernel.complete(
            retry_timeout,
            make_result(
                self.kernel, retry_timeout, status="timed_out", retryable=True
            ),
        )
        self.assertEqual(queued_timeout.state, "queued")

        expired = self.running("lease-dead", attempts=1)
        self.clock.advance(6)
        dead_expiry = {item.execution_id: item for item in self.kernel.reap()}["lease-dead"]
        self.assertEqual(dead_expiry.state, "dead")
        self.assertEqual(dead_expiry.result.error.code, "lease_retry_exhausted")
        self.assertEqual(expired.attempt, 1)

    def test_result_binding_duplicate_identity_and_atomic_outbox(self) -> None:
        first = self.running("first")
        result_values = make_result(self.kernel, first, result_id="stable-result").to_dict()
        result_values["value"] = {"number": 1}
        result = ExecutionResultV2.from_dict(result_values)
        terminal = self.kernel.complete(first, result)
        self.assertEqual(terminal.state, "succeeded")
        self.assertEqual(self.kernel.complete(first, result).to_dict(), terminal.to_dict())
        for number in (1.0, True):
            changed = result.to_dict()
            changed["value"] = {"number": number}
            with self.subTest(number=repr(number)), self.assertRaises(ResultConflictError):
                self.kernel.complete(first, ExecutionResultV2.from_dict(changed))
        self.assertEqual(self.kernel.result_outbox()[0]["result_id"], "stable-result")

        second = self.running("second")
        with self.assertRaises(ResultConflictError):
            self.kernel.complete(
                second,
                make_result(self.kernel, second, result_id="stable-result"),
            )
        self.assertEqual(self.kernel.get("second").state, "running")
        self.assertEqual(len(self.kernel.result_outbox()), 1)

    def test_effect_idempotency_uses_exact_canonical_wire_identity(self) -> None:
        lease = self.running("effect-wire", attempts=1)
        self.kernel.prepare_effect(
            lease,
            effect_id="effect-wire-request",
            name="publish",
            request={"number": 1},
        )
        for number in (1.0, True):
            with self.subTest(request_number=repr(number)), self.assertRaises(EffectConflictError):
                self.kernel.prepare_effect(
                    lease,
                    effect_id="effect-wire-request",
                    name="publish",
                    request={"number": number},
                )

        self.kernel.prepare_effect(
            lease,
            effect_id="effect-wire-response",
            name="publish",
            request={},
        )
        claim = self.kernel.claim_effect(lease, "effect-wire-response")
        committed = self.kernel.commit_effect(
            "effect-wire-response", {"number": 1}, lease, claim.claim_id
        )
        self.assertEqual(committed.state, "committed")
        for number in (1.0, True):
            with self.subTest(response_number=repr(number)), self.assertRaises(EffectConflictError):
                self.kernel.commit_effect(
                    "effect-wire-response", {"number": number}, lease, claim.claim_id
                )

        self.kernel.prepare_effect(
            lease,
            effect_id="effect-wire-detail",
            name="publish",
            request={},
        )
        detail_claim = self.kernel.claim_effect(lease, "effect-wire-detail")
        uncertain = self.kernel.mark_effect_indeterminate(
            "effect-wire-detail", {"number": 1}, lease, detail_claim.claim_id
        )
        self.assertEqual(uncertain.state, "indeterminate")
        for number in (1.0, True):
            with self.subTest(detail_number=repr(number)), self.assertRaises(EffectConflictError):
                self.kernel.mark_effect_indeterminate(
                    "effect-wire-detail",
                    {"number": number},
                    lease,
                    detail_claim.claim_id,
                )

        resolving = self.running("effect-wire-recovery", attempts=1)
        self.kernel.prepare_effect(
            resolving,
            effect_id="effect-wire-recovery",
            name="publish",
            request={},
        )
        resolving_claim = self.kernel.claim_effect(resolving, "effect-wire-recovery")
        self.kernel.mark_effect_indeterminate(
            "effect-wire-recovery",
            {"uncertain": True},
            resolving,
            resolving_claim.claim_id,
        )
        parked = self.kernel.complete(
            resolving,
            make_result(self.kernel, resolving, status="failed", retryable=False),
        )
        self.assertEqual(parked.state, "recovery_required")
        uncertain = self.kernel.get_effect("effect-wire-recovery")
        self.kernel.resolve_effect(
            "effect-wire-recovery",
            decision="applied",
            response={"number": 1},
            expected_revision=uncertain.revision,
            recovery_id="wire-recovery-1",
        )
        for number in (1.0, True):
            with self.subTest(recovery_number=repr(number)), self.assertRaises(EffectConflictError):
                self.kernel.resolve_effect(
                    "effect-wire-recovery",
                    decision="applied",
                    response={"number": number},
                    expected_revision=uncertain.revision,
                    recovery_id="wire-recovery-1",
                )

    def test_outbox_claim_ack_release_retry_dead_and_expiry(self) -> None:
        lease = self.running("outbox-one")
        self.kernel.complete(lease, make_result(self.kernel, lease))
        pending = self.kernel.result_outbox()[0]
        self.assertEqual(pending["state"], "pending")
        delivery = self.kernel.claim_outbox("bridge", lease_seconds=2)
        self.assertEqual(delivery["state"], "delivering")
        renewed = self.kernel.renew_outbox(delivery, lease_seconds=4)
        self.assertGreater(renewed["expires_at"], delivery["expires_at"])
        delivery = renewed
        delivered = self.kernel.ack_outbox(delivery)
        self.assertEqual(delivered["state"], "delivered")
        self.assertEqual(self.kernel.ack_outbox(delivery)["state"], "delivered")

        lease = self.running("outbox-two")
        self.kernel.complete(lease, make_result(self.kernel, lease))
        first_delivery = self.kernel.claim_outbox("bridge", lease_seconds=2)
        released = self.kernel.release_outbox(
            first_delivery,
            ExecutionError("bridge_error", "retry", True, {}),
        )
        self.assertEqual(released["state"], "pending")
        self.assertEqual(
            self.kernel.release_outbox(
                first_delivery, ExecutionError("bridge_error", "retry", True, {})
            )["state"],
            "pending",
        )
        with self.assertRaises(StaleFenceError):
            self.kernel.release_outbox(
                first_delivery, ExecutionError("different", "conflict", True, {})
            )
        second_delivery = self.kernel.claim_outbox("bridge", lease_seconds=2)
        dead = self.kernel.release_outbox(
            second_delivery,
            ExecutionError("bridge_error", "retry", True, {}),
        )
        self.assertEqual(dead["state"], "dead")
        status = self.kernel.result_outbox_status()
        self.assertEqual(
            (status.pending, status.delivering, status.dead),
            (0, 0, 1),
        )
        with self.assertRaises(StaleFenceError):
            self.kernel.retry_result_outbox(
                dead["result_id"],
                expected_revision=dead["revision"] - 1,
            )
        retried = self.kernel.retry_result_outbox(
            dead["result_id"],
            expected_revision=dead["revision"],
        )
        self.assertEqual(
            (retried["state"], retried["attempts"], retried["revision"]),
            ("pending", 0, dead["revision"] + 1),
        )
        replayed_retry = self.kernel.retry_result_outbox(
            dead["result_id"],
            expected_revision=dead["revision"],
        )
        self.assertEqual(replayed_retry, retried)
        with self.assertRaises(ValueError):
            self.kernel.retry_result_outbox(
                dead["result_id"],
                expected_revision=retried["revision"],
            )

        lease = self.running("outbox-three")
        self.kernel.complete(lease, make_result(self.kernel, lease))
        expiring = self.kernel.claim_outbox("bridge", lease_seconds=1)
        self.clock.advance(2)
        reaped = self.kernel.reap_outbox()[0]
        self.assertEqual(reaped["state"], "pending")
        with self.assertRaises(StaleFenceError):
            self.kernel.ack_outbox(expiring)
        reclaimed = self.kernel.claim_outbox("bridge", lease_seconds=2)
        self.assertGreater(reclaimed["fence"], expiring["fence"])

    def test_effect_fencing_indeterminate_and_explicit_recovery(self) -> None:
        first = self.running("effects", attempts=1)
        prepared = self.kernel.prepare_effect(
            first,
            effect_id="effect-1",
            name="charge",
            request={"amount": 5},
        )
        self.assertEqual(prepared.state, "prepared")
        with self.assertRaises(TypeError):
            self.kernel.commit_effect("effect-1", {"charge": "x"})
        self.clock.advance(6)
        parked = self.kernel.reap()[0]
        self.assertEqual(parked.state, "recovery_required")
        self.assertEqual(parked.attempt, 1)
        uncertain = self.kernel.get_effect("effect-1")
        self.assertEqual(uncertain.state, "indeterminate")
        with self.assertRaises(StaleFenceError):
            self.kernel.commit_effect(
                "effect-1", {"charge": "old"}, first, "stale-claim"
            )
        self.assertEqual(parked.recovery_effect_id, "effect-1")
        self.assertIsNone(parked.result)
        self.assertEqual(self.kernel.result_outbox(), [])
        recovered = self.kernel.resolve_effect(
            "effect-1",
            decision="applied",
            response={"charge": "known"},
            expected_revision=uncertain.revision,
            recovery_id="recovery-1",
        )
        self.assertEqual(recovered.state, "committed")
        self.assertEqual(recovered.response, {"charge": "known"})
        resumed = self.kernel.get("effects")
        self.assertEqual(resumed.state, "queued")
        self.assertEqual(resumed.attempt, 1)
        second = self.kernel.start(
            self.kernel.claim("owner-two", registry_revision="registry-1")
        )
        reused = self.kernel.prepare_effect(
            second,
            effect_id="effect-1",
            name="charge",
            request={"amount": 5},
        )
        self.assertEqual(reused.response, {"charge": "known"})
        terminal = self.kernel.complete(
            second,
            make_result(self.kernel, second, effect_ids=["effect-1"]),
        )
        self.assertEqual(terminal.state, "succeeded")
        self.assertEqual(terminal.attempt, 2)
        self.assertEqual(
            [event["event_type"] for event in self.kernel.effect_events("effect-1")],
            ["prepared", "lease_expired_indeterminate", "recovery_applied"],
        )
        with self.assertRaises(EffectConflictError):
            self.kernel.resolve_effect(
                "effect-1",
                decision="applied",
                response={"charge": "different"},
                expected_revision=uncertain.revision,
                recovery_id="recovery-2",
            )

    def test_not_applied_recovery_reprepares_under_a_new_fence(self) -> None:
        first = self.running("not-applied", attempts=1)
        self.kernel.prepare_effect(
            first,
            effect_id="effect-not-applied",
            name="send",
            request={"item": 1},
        )
        self.clock.advance(6)
        parked = self.kernel.reap()[0]
        self.assertEqual(parked.state, "recovery_required")
        uncertain = self.kernel.get_effect("effect-not-applied")
        resolved = self.kernel.resolve_effect(
            "effect-not-applied",
            decision="not_applied",
            response=None,
            expected_revision=uncertain.revision,
            recovery_id="human-decision-1",
        )
        self.assertEqual(resolved.state, "not_applied")
        second = self.kernel.start(
            self.kernel.claim("owner-two", registry_revision="registry-1")
        )
        reprepared = self.kernel.prepare_effect(
            second,
            effect_id="effect-not-applied",
            name="send",
            request={"item": 1},
        )
        self.assertEqual(reprepared.state, "prepared")
        self.assertEqual(reprepared.attempt, 2)
        self.assertEqual(reprepared.fence, second.fence)
        claimed = self.kernel.claim_effect(second, "effect-not-applied")
        committed = self.kernel.commit_effect(
            "effect-not-applied", {"sent": True}, second, claimed.claim_id
        )
        self.assertEqual(committed.state, "committed")
        self.assertIsNone(committed.recovery_decision)
        self.assertEqual(
            [event["event_type"] for event in self.kernel.effect_events(
                "effect-not-applied"
            )],
            [
                "prepared",
                "lease_expired_indeterminate",
                "recovery_not_applied",
                "reprepared_after_not_applied",
                "perform_claimed",
                "committed",
            ],
        )

    def test_newer_fence_never_reuses_a_prepared_effect(self) -> None:
        first = self.running("newer-fence", attempts=3)
        self.kernel.prepare_effect(
            first,
            effect_id="effect-newer-fence",
            name="send",
            request={"item": 2},
        )
        parked = self.kernel.complete(
            first,
            make_result(self.kernel, first, status="failed", retryable=True),
        )
        self.assertEqual(parked.state, "recovery_required")
        self.assertEqual(
            self.kernel.get_effect("effect-newer-fence").state,
            "indeterminate",
        )
        self.assertEqual(parked.recovery_effect_id, "effect-newer-fence")

    def test_cancel_recovery_target_survives_restart_and_never_requeues(self) -> None:
        lease = self.running("cancel-effect")
        self.kernel.prepare_effect(
            lease,
            effect_id="effect-cancel-effect",
            name="publish",
            request={"item": 3},
        )
        running = self.kernel.get("cancel-effect")
        with self.assertRaises(EffectRecoveryRequiredError):
            self.kernel.cancel(
                "cancel-effect",
                expected_revision=running.revision,
                reason="operator cancelled during publish",
            )
        parked = self.kernel.get("cancel-effect")
        self.assertEqual(parked.state, "recovery_required")
        self.assertEqual(parked.recovery_target_state, "cancelled")
        self.assertEqual(parked.recovery_reason, "operator cancelled during publish")

        self.kernel.close()
        self.kernel = SQLiteKernel(self.path, now=self.clock)
        restarted = self.kernel.get("cancel-effect")
        self.assertEqual(restarted.recovery_target_state, "cancelled")
        effect = self.kernel.get_effect("effect-cancel-effect")
        resolved = self.kernel.resolve_effect(
            effect.effect_id,
            decision="not_applied",
            response=None,
            expected_revision=effect.revision,
            recovery_id="recovery-cancel-effect",
        )
        terminal = self.kernel.get("cancel-effect")
        self.assertEqual(resolved.state, "not_applied")
        self.assertEqual(terminal.state, "cancelled")
        self.assertEqual(
            terminal.result.error.message, "operator cancelled during publish"
        )
        self.assertIsNone(terminal.recovery_target_state)
        self.assertIsNone(
            self.kernel.claim("another-worker", registry_revision="registry-1")
        )
        self.assertEqual(len(self.kernel.result_outbox()), 1)
        replay = self.kernel.resolve_effect(
            effect.effect_id,
            decision="not_applied",
            response=None,
            expected_revision=effect.revision,
            recovery_id="recovery-cancel-effect",
        )
        self.assertEqual(replay, resolved)
        self.assertEqual(len(self.kernel.result_outbox()), 1)

    def test_cancel_upgrades_an_existing_resume_recovery(self) -> None:
        lease = self.running("upgrade-cancel")
        self.kernel.prepare_effect(
            lease,
            effect_id="effect-upgrade-cancel",
            name="publish",
            request={"item": 4},
        )
        parked = self.kernel.complete(lease, make_result(self.kernel, lease))
        self.assertEqual(parked.recovery_target_state, "queued")
        with self.assertRaises(EffectRecoveryRequiredError):
            self.kernel.cancel(
                "upgrade-cancel",
                expected_revision=parked.revision,
                reason="late operator cancellation",
            )
        upgraded = self.kernel.get("upgrade-cancel")
        self.assertEqual(upgraded.recovery_target_state, "cancelled")
        self.assertEqual(upgraded.revision, parked.revision + 1)
        effect = self.kernel.get_effect("effect-upgrade-cancel")
        self.kernel.resolve_effect(
            effect.effect_id,
            decision="applied",
            response={"published": True},
            expected_revision=effect.revision,
            recovery_id="recovery-upgrade-cancel",
        )
        terminal = self.kernel.get("upgrade-cancel")
        self.assertEqual(terminal.state, "cancelled")
        self.assertEqual(terminal.result.effect_ids, ["effect-upgrade-cancel"])
        self.assertIn(
            "effect_recovery_cancellation_requested",
            [event["event_type"] for event in self.kernel.events("upgrade-cancel")],
        )

    def test_lease_lifecycle_cancel_and_restart(self) -> None:
        self.kernel.submit(make_command("cancel"))
        lease = self.kernel.claim("owner", registry_revision="registry-1")
        self.assertEqual(self.kernel.verify(lease).state, "leased")
        renewed = self.kernel.renew(lease, lease_seconds=8)
        cancelled = self.kernel.cancel(renewed)
        self.assertEqual(cancelled.state, "cancelled")
        self.kernel.close()
        reopened = SQLiteKernel(self.path, now=self.clock)
        try:
            self.assertEqual(reopened.get("cancel").state, "cancelled")
            self.assertEqual(reopened.result_outbox()[0]["result"].status, "cancelled")
        finally:
            reopened.close()

    def test_external_cancel_uses_revision_cas_and_revokes_live_fence(self) -> None:
        self.kernel.submit(make_command("external-cancel"))
        lease = self.kernel.start(
            self.kernel.claim("owner", registry_revision="registry-1")
        )
        running = self.kernel.get("external-cancel")

        with self.assertRaises(CASConflictError):
            self.kernel.cancel(
                "external-cancel",
                expected_revision=running.revision - 1,
                reason="operator request",
            )
        cancelled = self.kernel.cancel(
            "external-cancel",
            expected_revision=running.revision,
            reason="operator request",
        )
        self.assertEqual(cancelled.state, "cancelled")
        self.assertEqual(cancelled.result.error.message, "operator request")
        self.assertEqual(
            self.kernel.cancel(
                "external-cancel",
                expected_revision=running.revision,
                reason="operator request",
            ),
            cancelled,
        )
        with self.assertRaises((InvalidStateTransitionError, StaleFenceError)):
            self.kernel.complete(lease, make_result(self.kernel, lease))

    def test_active_external_cancel_requires_revision_or_live_lease(self) -> None:
        self.kernel.submit(make_command("external-authority"))
        self.kernel.start(
            self.kernel.claim("owner", registry_revision="registry-1")
        )
        with self.assertRaisesRegex(StaleFenceError, "expected_revision"):
            self.kernel.cancel("external-authority", reason="operator request")
        for invalid in (True, -1, 1.0):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.kernel.cancel(
                    "external-authority",
                    expected_revision=invalid,
                    reason="operator request",
                )


class SharedSQLiteIsolationTests(unittest.TestCase):
    def test_concurrent_first_open_installs_one_valid_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "first-open.sqlite3"
            barrier = threading.Barrier(2)

            def open_kernel(_):
                barrier.wait()
                kernel = SQLiteKernel(path)
                kernel.close()
                return True

            with ThreadPoolExecutor(max_workers=2) as executor:
                self.assertEqual(list(executor.map(open_kernel, range(2))), [True, True])
            reopened = SQLiteKernel(path)
            reopened.close()

    def test_approved_tables_coexist_but_kernel_connection_cannot_access_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "shared.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE orch_runs (id TEXT)")
            connection.execute("CREATE TABLE cp_settings (id TEXT)")
            connection.commit()
            connection.close()
            kernel = SQLiteKernel(path)
            try:
                kernel.submit(make_command("coexist"))
                with self.assertRaises(sqlite3.DatabaseError):
                    kernel._connection.execute("SELECT * FROM orch_runs").fetchall()
                with self.assertRaises(sqlite3.DatabaseError):
                    kernel._connection.execute("PRAGMA table_info(orch_runs)").fetchall()
                check = sqlite3.connect(path)
                try:
                    names = {
                        row[0]
                        for row in check.execute(
                            "SELECT name FROM sqlite_master WHERE type = 'table'"
                        )
                    }
                finally:
                    check.close()
                self.assertIn("orch_runs", names)
                self.assertIn("cp_settings", names)
                self.assertIn("kernel_executions", names)
                check = sqlite3.connect(path)
                try:
                    meta = check.execute(
                        "SELECT component, schema_version, typeof(schema_version) "
                        "FROM kernel_schema_meta"
                    ).fetchall()
                finally:
                    check.close()
                self.assertEqual(meta, [("execution_kernel", 2, "integer")])
            finally:
                kernel.close()

    def test_cross_layer_trigger_cannot_borrow_kernel_write_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trigger.sqlite3"
            kernel = SQLiteKernel(path)
            kernel.close()
            connection = sqlite3.connect(path)
            connection.execute(
                """CREATE TRIGGER cp_tamper AFTER INSERT ON kernel_executions
                   BEGIN
                       UPDATE kernel_clock
                       SET event_sequence = event_sequence + 10;
                   END"""
            )
            connection.commit()
            connection.close()
            kernel = SQLiteKernel(path)
            try:
                with self.assertRaises(sqlite3.DatabaseError):
                    kernel.submit(make_command("trigger-denied"))
                self.assertEqual(
                    kernel._connection.execute(
                        "SELECT event_sequence FROM kernel_clock"
                    ).fetchone()[0],
                    0,
                )
            finally:
                kernel.close()

    def test_kernel_schema_meta_is_required_and_strictly_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            partial = Path(temp) / "partial.sqlite3"
            connection = sqlite3.connect(partial)
            connection.execute("CREATE TABLE kernel_executions (id TEXT)")
            connection.commit()
            connection.close()
            with self.assertRaises(StorageIsolationError):
                SQLiteKernel(partial)

        for invalid in (3, 2.0, "2"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "wrong-meta.sqlite3"
                kernel = SQLiteKernel(path)
                kernel.close()
                connection = sqlite3.connect(path)
                connection.execute("PRAGMA ignore_check_constraints = ON")
                connection.execute(
                    "UPDATE kernel_schema_meta SET schema_version = ?", (invalid,)
                )
                connection.commit()
                connection.close()
                with self.assertRaises(StorageIsolationError):
                    SQLiteKernel(path)

    def test_application_tables_can_coexist_but_remain_inaccessible_to_kernel(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "application.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE runs (id TEXT)")
            connection.execute("INSERT INTO runs VALUES ('application-owned')")
            connection.commit()
            connection.close()
            with SQLiteKernel(path) as kernel:
                self.assertEqual(kernel.submit(make_command("independent")).state, "queued")
                for sql in ("SELECT * FROM runs", "DELETE FROM runs"):
                    with self.assertRaises(sqlite3.DatabaseError):
                        kernel._connection.execute(sql)
            with closing(sqlite3.connect(path)) as connection, connection:
                self.assertEqual(connection.execute("SELECT * FROM runs").fetchall(),
                                 [("application-owned",)])


if __name__ == "__main__":
    unittest.main()
