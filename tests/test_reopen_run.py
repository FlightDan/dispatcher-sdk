from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from dispatcher_sdk.execution_kernel import Kernel, RetryPolicy
from dispatcher_sdk.orchestrator import CommandConflict, OrchestrationError, Orchestrator, RevisionConflict


def echo(payload, context):
    return payload


class ReopenRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.db"
        self.sdk = Orchestrator.open_sqlite(self.path, {"echo": echo}, isolation_mode="thread")
        self.addCleanup(self.sdk.close)
        self.sdk.create_run("run", command_id="create", definition={"workflow": "repair"})

    def command(self, execution_id, idempotency_key=None):
        return self.sdk.runtime.command(
            execution_id=execution_id,
            idempotency_key=idempotency_key or execution_id,
            correlation_id="run", causation_id=None, handler_id="echo",
            handler_contract_version=1, retry_policy=RetryPolicy(),
            timeout_seconds=5, payload={"execution": execution_id},
        ).to_dict()

    def finish_failed(self, *, cancelled=False):
        command = self.command("old")
        operations = [
            {"kind": "add_task", "task_id": "task", "command": command},
            {"kind": "cancel", "task_id": "task", "reason": "test"},
        ]
        if cancelled:
            self.sdk.apply_operations("run", command_id="cancel", expected_revision=0,
                                      operations=operations)
            return self.sdk.apply_operations(
                "run", command_id="stop", expected_revision=1,
                operations=[{"kind": "finish", "state": "cancelled"}],
            )
        operations.append({"kind": "finish", "state": "failed"})
        return self.sdk.apply_operations("run", command_id="fail", expected_revision=0,
                                         operations=operations)

    def reopen_args(self, revision, *, authorization=None):
        return {
            "expected_revision": revision,
            "actor": "operator@example",
            "authorization_source": "incident-123",
            "reason": "repair the failed evidence stage",
            "target_deployment": {"registry_revision": self.sdk.runtime.registry_revision},
            "decision": {
                "start_stage": "contract_repair_plan",
                "reused_artifacts": ["diagnosis"],
                "invalidated_artifacts": ["repair-plan"],
            },
            "cancellation_authorization": authorization,
        }

    def test_reopen_preserves_history_and_requires_new_generation(self):
        failed = self.finish_failed()
        reopened = self.sdk.reopen_run("run", command_id="reopen", **self.reopen_args(failed["revision"]))
        self.assertEqual(reopened["status"], "activated")
        current = self.sdk.get_run("run")
        self.assertEqual((current["state"], current["generation"]), ("running", 1))
        self.assertEqual(self.sdk.get_run_at("run", failed["revision"])["state"], "failed")
        self.assertEqual(self.sdk.get_run_at("run", failed["revision"])["generation"], 0)
        with self.assertRaises(RevisionConflict):
            self.sdk.apply_operations("run", command_id="missing-generation", expected_revision=current["revision"], operations=[])
        updated = self.sdk.apply_operations(
            "run", command_id="with-generation", expected_revision=current["revision"],
            expected_generation=1, application_state={"recovered": True}, operations=[])
        self.assertEqual(updated["application_state"], {"recovered": True})

    def test_reopen_is_idempotent_and_new_command_conflicts(self):
        failed = self.finish_failed()
        args = self.reopen_args(failed["revision"])
        first = self.sdk.reopen_run("run", command_id="reopen", **args)
        second = self.sdk.reopen_run("run", command_id="reopen", **args)
        self.assertEqual(first["recovery_id"], second["recovery_id"])
        changed = dict(args)
        changed["reason"] = "different decision"
        with self.assertRaises(CommandConflict):
            self.sdk.reopen_run("run", command_id="reopen", **changed)

    def test_cancelled_requires_authorization_success_is_rejected_and_continuation_blocks(self):
        cancelled = self.finish_failed(cancelled=True)
        with self.assertRaises(OrchestrationError):
            self.sdk.reopen_run("run", command_id="cancel-reopen", **self.reopen_args(cancelled["revision"]))
        reopened = self.sdk.reopen_run(
            "run", command_id="cancel-reopen", **self.reopen_args(cancelled["revision"], authorization={"grant": "admin"}))
        self.assertEqual(reopened["status"], "activated")

        second = self.sdk.apply_operations(
            "run", command_id="finish-again", expected_revision=self.sdk.get_run("run")["revision"],
            expected_generation=1, operations=[{"kind": "finish", "state": "succeeded"}],
        )
        with self.assertRaises(OrchestrationError):
            self.sdk.reopen_run("run", command_id="success-reopen", **self.reopen_args(second["revision"]))

    def test_prepared_recovery_survives_crash_and_host_can_advance_it(self):
        failed = self.finish_failed()
        self.sdk._failpoint = lambda name: (_ for _ in ()).throw(RuntimeError(name)) \
            if name == "after_recovery_prepare" else None
        with self.assertRaisesRegex(RuntimeError, "after_recovery_prepare"):
            self.sdk.reopen_run("run", command_id="reopen", **self.reopen_args(failed["revision"]))
        with sqlite3.connect(self.path) as connection:
            recovery_id = connection.execute("SELECT recovery_id FROM sdk_recoveries").fetchone()[0]
        self.assertEqual(self.sdk.get_run("run")["state"], "failed")
        self.sdk._failpoint = lambda name: None
        self.assertEqual(self.sdk.advance_recovery(recovery_id, owner_id="reopen-client")["status"], "activated")
        self.assertEqual(self.sdk.get_recovery(recovery_id)["status"], "activated")
        self.assertEqual(self.sdk.get_run("run")["generation"], 1)

    def test_prepared_recovery_can_resume_after_original_owner_lease_expires(self):
        failed = self.finish_failed()
        self.sdk._failpoint = lambda name: (_ for _ in ()).throw(RuntimeError(name)) \
            if name == "after_recovery_prepare" else None
        with self.assertRaisesRegex(RuntimeError, "after_recovery_prepare"):
            self.sdk.reopen_run("run", command_id="reopen", **self.reopen_args(failed["revision"]))
        recovery_id = self.sdk.get_run_summary("run")["recovery_id"]
        lease_until = self.sdk.get_recovery(recovery_id)["lease_until"]
        self.sdk._failpoint = lambda name: None
        self.sdk.clock = lambda: lease_until + 1
        recovered = self.sdk.advance_recovery(recovery_id)
        self.assertEqual(recovered["status"], "activated")
        self.assertEqual(recovered["owner_fence"], 2)

    def test_competing_request_keeps_waiter_registration(self):
        failed = self.finish_failed()
        self.sdk._failpoint = lambda name: (_ for _ in ()).throw(RuntimeError(name)) \
            if name == "after_recovery_prepare" else None
        with self.assertRaisesRegex(RuntimeError, "after_recovery_prepare"):
            self.sdk.reopen_run("run", command_id="reopen", owner_id="owner-1",
                                **self.reopen_args(failed["revision"]))
        self.sdk._failpoint = lambda name: None
        with self.assertRaises(CommandConflict):
            self.sdk.reopen_run("run", command_id="other", owner_id="owner-2",
                                **self.reopen_args(failed["revision"]))
        recovery = self.sdk.get_recovery(
            self.sdk.get_run_summary("run")["recovery_id"])
        self.assertEqual(recovery["waiters"], 1)

    def test_commit_activation_boundary_is_resumable(self):
        failed = self.finish_failed()
        self.sdk._failpoint = lambda name: (_ for _ in ()).throw(RuntimeError(name)) \
            if name == "after_recovery_commit" else None
        with self.assertRaisesRegex(RuntimeError, "after_recovery_commit"):
            self.sdk.reopen_run("run", command_id="reopen", **self.reopen_args(failed["revision"]))
        recovery_id = self.sdk.get_run_summary("run")["recovery_id"]
        self.assertEqual(self.sdk.get_recovery(recovery_id)["status"], "committed")
        self.assertEqual(self.sdk.get_run("run")["generation"], 1)
        self.sdk._failpoint = lambda name: None
        self.assertEqual(self.sdk.advance_recovery(recovery_id)["status"], "activated")

    def test_existing_continuation_is_not_reopened(self):
        failed = self.finish_failed()
        self.sdk.continue_run("run", "next", command_id="continue", expected_revision=failed["revision"])
        with self.assertRaises(CommandConflict):
            self.sdk.reopen_run("run", command_id="reopen", **self.reopen_args(self.sdk.get_run("run")["revision"]))

    def test_generation_zero_submission_replays_after_reopen(self):
        submitted = self.sdk.submit_task(
            "run", "submitted", request_id="request-0", expected_revision=0,
            handler_id="echo", payload={"execution": "submitted"}, timeout_seconds=5,
            dispatch=True)
        self.sdk.flush()
        self.sdk.runtime.run_once()
        self.sdk.sync()
        self.sdk.pump_results()
        claim = self.sdk.claim_results(owner="test", lease_seconds=5, limit=1)[0]
        self.sdk.acknowledge_result(
            claim["result"]["result_id"], lease_id=claim["lease_id"], fence=claim["fence"])
        failed = self.sdk.apply_operations(
            "run", command_id="finish", expected_revision=self.sdk.get_run("run")["revision"],
            operations=[{"kind": "finish", "state": "failed"}])
        self.sdk.reopen_run("run", command_id="reopen", **self.reopen_args(failed["revision"]))
        replay = self.sdk.submit_task(
            "run", "submitted", request_id="request-0", expected_revision=0,
            handler_id="echo", payload={"execution": "submitted"}, timeout_seconds=5,
            dispatch=True)
        self.assertEqual(replay["revision"], submitted["revision"])
        self.assertEqual(replay["generation"], 0)

    def test_reopened_result_delivery_keeps_generation(self):
        failed = self.finish_failed()
        command = self.command("new")
        self.sdk.reopen_run(
            "run", command_id="reopen", **self.reopen_args(failed["revision"]),
            operations=[
                {"kind": "new_attempt", "task_id": "task", "command": command},
                {"kind": "dispatch", "task_id": "task"},
            ],
        )
        self.sdk.flush()
        self.sdk.runtime.run_once()
        self.sdk.sync()
        self.sdk.pump_results()
        claim = self.sdk.claim_results(owner="test", lease_seconds=5, limit=1)[0]
        self.assertEqual(claim["generation"], 1)
        record = self.sdk.load_result_outbox(claim["result"]["result_id"])
        self.assertEqual(record["generation"], 1)


if __name__ == "__main__":
    unittest.main()
