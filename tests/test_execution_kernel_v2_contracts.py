from __future__ import annotations

from dataclasses import fields
import json
import math
import unittest

from dispatcher_sdk.execution_kernel import (
    ContractValidationError,
    EffectRecord,
    Event,
    ExecutionCommandV2,
    ExecutionError,
    ExecutionLease,
    ExecutionResultV2,
    ExecutionSnapshot,
    InvalidStateTransitionError,
    RetryPolicy,
    TRANSITION_MATRIX,
    reduce_state,
)


def policy(**changes):
    values = {
        "max_attempts": 2,
        "initial_backoff_seconds": 0,
        "backoff_multiplier": 1,
        "max_backoff_seconds": 10,
        "retry_timeouts": False,
    }
    values.update(changes)
    return RetryPolicy(**values)


def command() -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id="execution-1",
        idempotency_key="idempotency-1",  # gitleaks:allow synthetic test identity, not a credential
        registry_revision="registry-1",
        correlation_id="correlation-1",
        causation_id=None,
        handler_id="echo",
        handler_contract_version=3,
        retry_policy=policy(),
        timeout_seconds=4,
        payload={"value": [1, True, None]},
    )


def error(*, retryable: bool = False) -> ExecutionError:
    return ExecutionError(
        code="example_error",
        message="example",
        retryable=retryable,
        details={"kind": "test"},
    )


class StrictContractTests(unittest.TestCase):
    def test_all_contracts_round_trip_as_strict_json(self) -> None:
        cmd = command()
        lease = ExecutionLease(
            execution_id=cmd.execution_id,
            lease_id="lease-1",
            owner="owner-1",
            fence=2,
            attempt=1,
            expires_at=20,
            revision=3,
        )
        result = ExecutionResultV2(
            result_id="result-1",
            execution_id=cmd.execution_id,
            status="succeeded",
            attempt=1,
            fence=2,
            effect_ids=["effect-1"],
            started_at=10,
            completed_at=11,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            value={"ok": True},
            error=None,
        )
        snapshot = ExecutionSnapshot(
            execution_id=cmd.execution_id,
            state="succeeded",
            revision=4,
            attempt=1,
            fence=2,
            redelivery_count=0,
            command=cmd,
            lease=None,
            result=result,
            recovery_effect_id=None,
            next_attempt_at=0,
            started_at=10,
            created_at=1,
            updated_at=11,
        )
        effect = EffectRecord(
            effect_id="effect-1",
            execution_id=cmd.execution_id,
            name="notify",
            request={"value": 1},
            state="committed",
            lease_id=lease.lease_id,
            claim_id="claim-1",
            attempt=lease.attempt,
            fence=lease.fence,
            prepared_at=10,
            response={"sent": True},
            committed_at=10.5,
            indeterminate_at=None,
            recovery_id=None,
            recovery_decision=None,
            resolved_at=None,
            revision=2,
        )
        event = Event(
            sequence=1,
            event_id="execution-1:4",
            execution_id=cmd.execution_id,
            revision=4,
            event_type="succeeded",
            from_state="running",
            to_state="succeeded",
            data={"result_id": result.result_id},
            created_at=11,
        )
        for value, contract_type in (
            (policy(), RetryPolicy),
            (cmd, ExecutionCommandV2),
            (error(), ExecutionError),
            (lease, ExecutionLease),
            (result, ExecutionResultV2),
            (snapshot, ExecutionSnapshot),
            (effect, EffectRecord),
            (event, Event),
        ):
            encoded = value.to_json()
            self.assertEqual(json.loads(encoded), value.to_dict())
            self.assertEqual(contract_type.from_json(encoded).to_dict(), value.to_dict())

    def test_command_has_required_first_class_identity_and_no_metadata(self) -> None:
        names = {item.name for item in fields(ExecutionCommandV2)}
        self.assertEqual(
            names,
            {
                "execution_id",
                "idempotency_key",
                "registry_revision",
                "correlation_id",
                "causation_id",
                "handler_id",
                "handler_contract_version",
                "retry_policy",
                "timeout_seconds",
                "payload",
                "schema_version",
            },
        )
        payload = command().to_dict()
        for name in (
            "execution_id",
            "idempotency_key",
            "registry_revision",
            "correlation_id",
            "handler_id",
        ):
            with self.subTest(name=name):
                changed = dict(payload)
                changed[name] = " "
                with self.assertRaises(ContractValidationError):
                    ExecutionCommandV2.from_dict(changed)
        child = dict(payload)
        child["causation_id"] = "cause-1"
        self.assertEqual(ExecutionCommandV2.from_dict(child).causation_id, "cause-1")
        with self.assertRaises(ContractValidationError):
            ExecutionCommandV2.from_dict(payload | {"metadata": {"escape": True}})

    def test_schema_version_requires_exact_integer_two_for_every_contract(self) -> None:
        cmd = command()
        lease = ExecutionLease("execution-1", "lease-1", "owner", 1, 1, 10, 2)
        result = ExecutionResultV2(
            "result-1",
            "execution-1",
            "failed",
            1,
            1,
            [],
            1,
            2,
            "correlation-1",
            None,
            None,
            error(),
        )
        snapshot = ExecutionSnapshot(
            "execution-1",
            "failed",
            3,
            1,
            1,
            0,
            cmd,
            None,
            result,
            None,
            0,
            1,
            0,
            2,
        )
        effect = EffectRecord(
            "effect-1",
            "execution-1",
            "x",
            {},
            "prepared",
            "lease-1",
            None,
            1,
            1,
            1,
            None,
            None,
            None,
            None,
            None,
            None,
            1,
        )
        event = Event(1, "event-1", "execution-1", 1, "submitted", None, "queued", {}, 1)
        values = [policy(), cmd, error(), lease, result, snapshot, effect, event]
        for value in values:
            for invalid in (2.0, True, 3, "2"):
                with self.subTest(contract=type(value).__name__, invalid=invalid):
                    changed = value.to_dict()
                    changed["schema_version"] = invalid
                    with self.assertRaises(ContractValidationError):
                        type(value).from_dict(changed)

    def test_missing_unknown_and_malformed_nested_fields_are_normalized(self) -> None:
        cmd = command()
        lease = ExecutionLease("execution-1", "lease", "owner", 1, 1, 10, 2)
        result = ExecutionResultV2(
            "result",
            "execution-1",
            "failed",
            1,
            1,
            [],
            1,
            2,
            cmd.correlation_id,
            None,
            None,
            error(),
        )
        snapshot = ExecutionSnapshot(
            "execution-1", "failed", 3, 1, 1, 0, cmd, None, result, None, 0, 1, 0, 2
        )
        effect = EffectRecord(
            "effect", "execution-1", "x", {}, "prepared", "lease", None, 1, 1, 1,
            None, None, None, None, None, None, 1,
        )
        event = Event(1, "event", "execution-1", 1, "submitted", None, "queued", {}, 1)
        values = [policy(), cmd, error(), lease, result, snapshot, effect, event]
        for value in values:
            payload = value.to_dict()
            contract_type = type(value)
            missing = dict(payload)
            missing.pop(next(iter(missing)))
            with self.subTest(contract=contract_type.__name__, case="missing"):
                with self.assertRaises(ContractValidationError):
                    contract_type.from_dict(missing)
            with self.subTest(contract=contract_type.__name__, case="unknown"):
                with self.assertRaises(ContractValidationError):
                    contract_type.from_dict(payload | {"unknown": 1})
        malformed = command().to_dict()
        malformed["retry_policy"] = []
        with self.assertRaises(ContractValidationError):
            ExecutionCommandV2.from_dict(malformed)
        malformed_result = {
            "result_id": "r",
            "execution_id": "e",
            "status": "failed",
            "attempt": 1,
            "fence": 1,
            "effect_ids": [],
            "started_at": 1,
            "completed_at": 2,
            "correlation_id": "c",
            "causation_id": None,
            "value": None,
            "error": [],
            "schema_version": 2,
        }
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2.from_dict(malformed_result)
        with self.assertRaises(ContractValidationError):
            ExecutionCommandV2.from_json('{"schema_version": NaN}')
        with self.assertRaises(ContractValidationError):
            RetryPolicy.from_json(
                '{"max_attempts":1,"max_attempts":2,'
                '"initial_backoff_seconds":0,"backoff_multiplier":1,'
                '"max_backoff_seconds":0,"retry_timeouts":false,"schema_version":2}'
            )
        malformed_key = command().to_dict()
        malformed_key[1] = "not-a-field-name"
        with self.assertRaises(ContractValidationError):
            ExecutionCommandV2.from_dict(malformed_key)

    def test_non_json_and_non_finite_values_are_rejected_and_copied(self) -> None:
        with self.assertRaises(ContractValidationError):
            ExecutionCommandV2(
                "e", "i", "r", "c", None, "h", 1, policy(), 1, {"x": math.inf}
            )
        with self.assertRaises(ContractValidationError):
            ExecutionError("code", "bad", False, {"call": lambda: None})
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaises(ContractValidationError):
            ExecutionError("code", "bad", False, {"cycle": cyclic})
        with self.assertRaises(ContractValidationError):
            RetryPolicy(initial_backoff_seconds=10 ** 10000)
        source = {"nested": [1]}
        cmd = ExecutionCommandV2(
            "e", "i", "r", "c", None, "h", 1, policy(), 1, source
        )
        source["nested"].append(2)
        self.assertEqual(cmd.payload, {"nested": [1]})

    def test_invalid_result_semantic_combinations_are_rejected(self) -> None:
        base = {
            "result_id": "result",
            "execution_id": "execution",
            "status": "succeeded",
            "attempt": 1,
            "fence": 1,
            "effect_ids": [],
            "started_at": 1,
            "completed_at": 2,
            "correlation_id": "correlation",
            "causation_id": None,
            "value": None,
            "error": None,
        }
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2(**(base | {"error": error()}))
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2(**(base | {"status": "failed"}))
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2(
                **(base | {"status": "dead", "error": error(retryable=True)})
            )
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2(**(base | {"effect_ids": ["x", "x"]}))
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2(**(base | {"completed_at": 0}))
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2(**(base | {"attempt": 0, "fence": 0}))
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2(
                **(base | {"status": "failed", "error": error(), "value": {"bad": True}})
            )
        with self.assertRaises(ContractValidationError):
            ExecutionResultV2(
                **(base | {"status": "cancelled", "error": error(), "attempt": 0})
            )

    def test_recovery_contract_semantics_are_explicit(self) -> None:
        cmd = command()
        parked = ExecutionSnapshot(
            execution_id=cmd.execution_id,
            state="recovery_required",
            revision=5,
            attempt=2,
            fence=2,
            redelivery_count=1,
            command=cmd,
            lease=None,
            result=None,
            recovery_effect_id="effect-1",
            recovery_target_state="queued",
            next_attempt_at=0,
            started_at=10,
            created_at=1,
            updated_at=11,
        )
        self.assertEqual(
            ExecutionSnapshot.from_json(parked.to_json()).recovery_effect_id,
            "effect-1",
        )
        invalid = parked.to_dict()
        invalid["recovery_effect_id"] = None
        with self.assertRaises(ContractValidationError):
            ExecutionSnapshot.from_dict(invalid)
        with self.assertRaises(ContractValidationError):
            EffectRecord(
                effect_id="effect-1",
                execution_id=cmd.execution_id,
                name="notify",
                request={},
                state="not_applied",
                lease_id="lease-1",
                claim_id=None,
                attempt=1,
                fence=1,
                prepared_at=1,
                response={"ambiguous": True},
                committed_at=None,
                indeterminate_at=2,
                recovery_id="recovery-1",
                recovery_decision="not_applied",
                resolved_at=3,
                revision=3,
            )

    def test_performing_effect_requires_a_claim_and_event_sequence_is_strict(self) -> None:
        base = {
            "effect_id": "effect-claim",
            "execution_id": "execution-1",
            "name": "publish",
            "request": {},
            "state": "performing",
            "lease_id": "lease-1",
            "claim_id": "claim-1",
            "attempt": 1,
            "fence": 1,
            "prepared_at": 1,
            "response": None,
            "committed_at": None,
            "indeterminate_at": None,
            "recovery_id": None,
            "recovery_decision": None,
            "resolved_at": None,
            "revision": 2,
        }
        self.assertEqual(EffectRecord(**base).claim_id, "claim-1")
        with self.assertRaises(ContractValidationError):
            EffectRecord(**(base | {"claim_id": None}))
        with self.assertRaises(ContractValidationError):
            EffectRecord(**(base | {"state": "prepared"}))
        event = Event(1, "event-1", "execution-1", 1, "x", None, "queued", {}, 1)
        for invalid in (0, True, 1.0):
            with self.subTest(invalid=invalid):
                changed = event.to_dict()
                changed["sequence"] = invalid
                with self.assertRaises(ContractValidationError):
                    Event.from_dict(changed)


class TransitionTests(unittest.TestCase):
    def test_dead_is_terminal_and_exhaustion_paths_are_explicit(self) -> None:
        self.assertEqual(reduce_state("queued", "lease"), "leased")
        self.assertEqual(reduce_state("leased", "start"), "running")
        self.assertEqual(reduce_state("running", "retry"), "queued")
        self.assertEqual(
            reduce_state("running", "require_recovery"), "recovery_required"
        )
        self.assertEqual(
            reduce_state("recovery_required", "recovery_resolved"), "queued"
        )
        self.assertEqual(reduce_state("running", "dead_letter"), "dead")
        self.assertEqual(reduce_state("leased", "dead_letter"), "dead")
        self.assertEqual(TRANSITION_MATRIX["dead"], frozenset())
        with self.assertRaises(InvalidStateTransitionError) as caught:
            reduce_state("dead", "retry", execution_id="e", revision=8, fence=3)
        self.assertEqual(caught.exception.context["execution_id"], "e")
        self.assertEqual(caught.exception.context["fence"], 3)


if __name__ == "__main__":
    unittest.main()
