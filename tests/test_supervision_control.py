from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from dispatcher_sdk.execution_kernel import (
    CASConflictError, ExecutionCommandV2, RetryPolicy, SQLiteKernel, StorageIsolationError,
)
from dispatcher_sdk.execution_kernel._sqlite_schema import (
    KERNEL_SCHEMA_V3, upgrade_kernel_schema_v3_to_v4, upgrade_kernel_schema_v4_to_v5,
)
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock


def command(identity, parent=None):
    return ExecutionCommandV2(
        execution_id=identity, idempotency_key=identity, registry_revision="fixture",
        correlation_id="run", causation_id=parent, handler_id="fixture",
        handler_contract_version=1, retry_policy=RetryPolicy(), timeout_seconds=30, payload={},
    )


class SupervisionControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "tasks.sqlite3"
        self.kernel = SQLiteKernel(self.path)
        self.addCleanup(self.kernel.close)
        self.kernel.submit(command("parent"))
        self.lease = self.kernel.claim_and_start("parent-worker")

    def test_replayed_progress_does_not_refresh_or_revoke_handler_lease(self):
        first = self.kernel.confirm_progress(self.lease, "completed-one-unit")
        repeated = self.kernel.confirm_progress(self.lease, "completed-one-unit")
        self.assertTrue(first["new"])
        self.assertFalse(repeated["new"])
        self.assertEqual(first["at"], repeated["at"])
        self.assertEqual(first["progress_revision"], repeated["progress_revision"])
        self.kernel.verify(self.lease)

    def test_progress_between_notice_read_and_cancel_commit_rejects_cancel(self):
        notice = self.kernel.register_stall_episode(
            "parent", attempt=self.lease.attempt, fence=self.lease.fence,
            progress_revision=0, episode_id="episode-one", policy_version="policy-one",
        )
        progressed = threading.Event()
        errors = []

        def producer():
            try:
                with SQLiteKernel(self.path) as other:
                    other.confirm_progress(self.lease, "new-work-after-notice")
            except BaseException as error:
                errors.append(error)
            finally:
                progressed.set()

        thread = threading.Thread(target=producer)
        thread.start()
        self.assertTrue(progressed.wait(5))
        thread.join()
        self.assertEqual(errors, [])
        with self.assertRaises(CASConflictError):
            self.kernel.cancel("parent", expected_revision=self.lease.revision,
                               expected_supervision=notice)
        self.assertEqual(self.kernel.get("parent").state, "running")

    def test_explicit_cancel_keeps_its_original_semantics(self):
        self.kernel.confirm_progress(self.lease, "work")
        result = self.kernel.cancel("parent", expected_revision=self.lease.revision)
        self.assertEqual(result.state, "cancelled")

    def test_child_identity_and_budget_are_persisted_together(self):
        envelope = BudgetEnvelope((), sample_clock()).enter_handler(
            30, origin_id="execution:parent"
        )
        self.kernel.record_execution_budget(self.lease, envelope)
        result = self.kernel.submit_child(command("child", "parent"), self.lease, envelope)
        limits = self.kernel.get_execution_limits("child")
        self.assertEqual(result.state, "queued")
        self.assertEqual(limits["parent_execution_id"], "parent")
        self.assertEqual(limits["parent_fence"], self.lease.fence)
        self.assertEqual(limits["envelope"]["constraints"], envelope.to_dict()["constraints"])

    def test_old_layout_requires_explicit_copy_upgrade(self):
        path = Path(self.temporary.name) / "former.sqlite3"
        connection = sqlite3.connect(path)
        try:
            connection.executescript(KERNEL_SCHEMA_V3)
            connection.execute("UPDATE kernel_clock SET watermark=12 WHERE singleton=1")
            connection.commit()
            with self.assertRaises(StorageIsolationError):
                SQLiteKernel(path)
            upgrade_kernel_schema_v3_to_v4(connection)
            upgrade_kernel_schema_v4_to_v5(connection)
            self.assertEqual(connection.execute(
                "SELECT watermark FROM kernel_clock"
            ).fetchone()[0], 12)
        finally:
            connection.close()
        with SQLiteKernel(path):
            pass


if __name__ == "__main__":
    unittest.main()
