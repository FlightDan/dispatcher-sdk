"""Focused contract tests for the Kernel v3 managed claim gate."""

from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from dispatcher_sdk.execution_kernel import (
    CASConflictError,
    ExecutionCommandV2,
    RetryPolicy,
    SQLiteKernel,
)
from dispatcher_sdk.execution_kernel._sqlite_base import encode_json
from dispatcher_sdk.execution_kernel._sqlite_schema import (
    KERNEL_SCHEMA_V2,
    upgrade_kernel_schema_v2_to_v3,
)


def _command(run_id: str, task_id: str = "a") -> ExecutionCommandV2:
    execution_id = f"sdk-managed:{run_id}:{task_id}"
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=f"key:{run_id}:{task_id}",
        registry_revision="handler-v1:fixture",
        correlation_id=run_id,
        causation_id=None,
        handler_id="fixture",
        handler_contract_version=1,
        retry_policy=RetryPolicy(),
        timeout_seconds=5,
        payload={"task": task_id},
    )


class ManagedGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "kernel.sqlite3"
        self.kernel = SQLiteKernel(self.path)
        self.addCleanup(self.kernel.close)

    def _register_and_activate(self, run_id: str, *, max_claims: int = 3) -> None:
        self.kernel.register_run_control(
            run_id, max_claims=max_claims, deadline_at=time.time() + 60
        )
        self.kernel.set_run_control(
            run_id, expected_epoch=0, state="active", generation=0
        )

    def test_pause_blocks_a_lease_acquired_before_barrier_from_starting(self):
        self._register_and_activate("run")
        command = _command("run")
        self.kernel.submit_managed(command, run_id="run", generation=0)
        lease = self.kernel.claim("worker")
        self.assertIsNotNone(lease)
        self.kernel.set_run_control(
            "run", expected_epoch=1, state="pausing", generation=0
        )
        with self.assertRaises(CASConflictError):
            self.kernel.start(lease)

    def test_pausing_blocks_new_effect_authority_but_allows_existing_effect_settlement(self):
        self._register_and_activate("run")
        command = _command("run")
        self.kernel.submit_managed(command, run_id="run", generation=0)
        lease = self.kernel.claim_and_start("worker")
        self.kernel.prepare_effect(
            lease, effect_id="effect:run:a", name="fixture", request={"write": 1}
        )
        claimed = self.kernel.claim_effect(lease, "effect:run:a")
        self.kernel.prepare_effect(
            lease, effect_id="effect:run:b", name="fixture", request={"write": 2}
        )
        self.kernel.set_run_control(
            "run", expected_epoch=1, state="pausing", generation=0
        )
        with self.assertRaises(CASConflictError):
            self.kernel.prepare_effect(
                lease, effect_id="effect:run:c", name="fixture", request={"write": 3}
            )
        with self.assertRaises(CASConflictError):
            self.kernel.claim_effect(lease, "effect:run:b")
        # An effect claim acquired before the barrier may still persist the
        # outcome of that external call, even after the Run has paused.
        settled = self.kernel.commit_effect(
            "effect:run:a", {"written": True}, lease, claimed.claim_id
        )
        self.assertEqual(settled.state, "committed")

    def test_new_submit_is_active_only_but_exact_replay_is_allowed_while_paused(self):
        self.kernel.register_run_control(
            "run", max_claims=3, deadline_at=time.time() + 60
        )
        command = _command("run")
        with self.assertRaises(CASConflictError):
            self.kernel.submit_managed(command, run_id="run", generation=0)
        self.kernel.set_run_control(
            "run", expected_epoch=0, state="active", generation=0
        )
        accepted = self.kernel.submit_managed(command, run_id="run", generation=0)
        self.kernel.set_run_control(
            "run", expected_epoch=1, state="paused", generation=0
        )
        replay = self.kernel.submit_managed(command, run_id="run", generation=0)
        self.assertEqual(replay, accepted)

    def test_explicit_v2_upgrade_preserves_kernel_rows(self):
        # Build an exact v2 store containing one ordinary queued execution and
        # its event, then verify the copy-upgrade changes only schema objects.
        legacy_path = Path(self.temporary.name) / "legacy-v2.sqlite3"
        with sqlite3.connect(legacy_path) as legacy:
            legacy.executescript(KERNEL_SCHEMA_V2)
            command = ExecutionCommandV2(
                execution_id="legacy:one",
                idempotency_key="legacy-key:one",
                registry_revision="handler-v1:fixture",
                correlation_id="legacy-run",
                causation_id=None,
                handler_id="fixture",
                handler_contract_version=1,
                retry_policy=RetryPolicy(),
                timeout_seconds=5,
                payload={"task": "legacy"},
            )
            legacy.execute(
                """INSERT INTO kernel_executions
                   (execution_id,idempotency_key,registry_revision,command_json,state,
                    attempt,redelivery_count,next_attempt_at,lease_id,lease_owner,fence,
                    lease_expires_at,started_at,result_json,recovery_effect_id,
                    recovery_target_state,recovery_reason,revision,created_at,updated_at)
                   VALUES(?,?,?,?,'queued',0,0,1,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,NULL,1,1,1)""",
                (
                    command.execution_id,
                    command.idempotency_key,
                    command.registry_revision,
                    encode_json(command.to_dict()),
                ),
            )
            legacy.execute(
                """INSERT INTO kernel_events
                   (sequence,event_id,execution_id,revision,event_type,from_state,
                    to_state,data_json,created_at)
                   VALUES(1,'legacy-event:one','legacy:one',1,'submitted',NULL,'queued','{}',1)"""
            )
            legacy.execute(
                "UPDATE kernel_clock SET watermark=1,event_sequence=1 WHERE singleton=1"
            )

        with sqlite3.connect(legacy_path) as upgraded:
            upgrade_kernel_schema_v2_to_v3(upgraded)
            self.assertEqual(
                upgraded.execute(
                    "SELECT count(*) FROM kernel_executions WHERE execution_id='legacy:one'"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                upgraded.execute(
                    "SELECT count(*) FROM kernel_events WHERE event_id='legacy-event:one'"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                upgraded.execute("SELECT schema_version FROM kernel_schema_meta").fetchone()[0],
                3,
            )
        upgraded_kernel = SQLiteKernel(legacy_path)
        self.addCleanup(upgraded_kernel.close)
        snapshot = upgraded_kernel.get("legacy:one")
        self.assertEqual(snapshot.execution_id, "legacy:one")
        self.assertEqual(snapshot.state, "queued")


if __name__ == "__main__":
    unittest.main()
