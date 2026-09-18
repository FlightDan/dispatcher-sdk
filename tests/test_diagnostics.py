from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.diagnostics import (
    collect_sqlite_diagnostics,
    inspect_diagnostics,
)
from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.orchestrator import NotificationInbox, Orchestrator


def command(identity: str) -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id=identity,
        idempotency_key=f"key-{identity}",
        registry_revision="diagnostics-test",
        correlation_id="diagnostics-test",
        causation_id=None,
        handler_id="test",
        handler_contract_version=1,
        retry_policy=RetryPolicy(),
        timeout_seconds=10,
        payload={"identity": identity},
    )


class DiagnosticsTests(unittest.TestCase):
    def test_single_file_report_counts_backlogs_without_mutating_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dispatcher.sqlite3"
            kernel = SQLiteKernel(path)
            try:
                Orchestrator(path, kernel)
                kernel.submit(command("queued"))
                kernel.submit(command("recovery"))
                with NotificationInbox(path) as inbox:
                    inbox.accept(
                        "source",
                        {"notification_id": "inbox-1", "kind": "terminal"},
                    )
            finally:
                kernel.close()

            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "UPDATE kernel_executions SET state='recovery_required',"
                    "recovery_effect_id='effect-1',recovery_target_state='queued',"
                    "started_at=created_at "
                    "WHERE execution_id='recovery'"
                )
                connection.execute(
                    "INSERT INTO sdk_notifications"
                    "(notification_id,payload,max_attempts,next_attempt_at) "
                    "VALUES('notice-1','{}',3,0)"
                )
                connection.commit()
                before = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "kernel_executions",
                        "sdk_notifications",
                        "notification_inbox_messages",
                    )
                }
            finally:
                connection.close()

            report = inspect_diagnostics(path, timeout_seconds=1)
            self.assertEqual(report["queue"]["executions"]["by_state"]["queued"], 1)
            self.assertEqual(report["queue"]["executions"]["recovery_required"], 1)
            self.assertEqual(report["notifications"]["backlog"], 1)
            self.assertEqual(report["notifications"]["wall_clock_ready_pending"], 1)
            self.assertEqual(report["inbox"]["backlog"], 1)
            self.assertEqual(report["inbox"]["ready_pending"], 1)
            self.assertGreater(report["sampling"]["query_count"], 0)
            self.assertFalse(report["sampling"]["sqlite_lock_wait_measured"])
            self.assertIsNone(report["sampling"]["sqlite_lock_wait_ms"])
            self.assertGreaterEqual(report["databases"][0]["database_bytes"], 1)
            json.dumps(report, allow_nan=False)

            connection = sqlite3.connect(path)
            try:
                after = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in before
                }
            finally:
                connection.close()
            self.assertEqual(after, before)

    def test_distinct_component_files_report_non_atomic_sampling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            kernel_path = root / "kernel.sqlite3"
            inbox_path = root / "inbox.sqlite3"
            with SQLiteKernel(kernel_path) as kernel:
                kernel.submit(command("queued"))
            with NotificationInbox(inbox_path) as inbox:
                inbox.accept("source", {"notification_id": "notice"})

            report = collect_sqlite_diagnostics(
                kernel_path,
                orchestrator_path=kernel_path,
                inbox_path=inbox_path,
            )
            self.assertFalse(report["sampling"]["cross_file_atomic"])
            self.assertEqual(len(report["databases"]), 2)
            self.assertFalse(report["orchestrator"]["present"])
            self.assertTrue(report["inbox"]["present"])

    def test_missing_store_is_rejected_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "missing.sqlite3"
            with self.assertRaises(FileNotFoundError):
                inspect_diagnostics(path)
            self.assertFalse(path.exists())

    def test_zero_budget_returns_an_explicit_incomplete_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dispatcher.sqlite3"
            with SQLiteKernel(path):
                pass
            report = inspect_diagnostics(path, timeout_seconds=0)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "timeout")
        self.assertFalse(report["sampling"]["complete"])
        self.assertEqual(report["sampling"]["query_count"], 0)

    def test_progress_handler_interrupts_a_large_count_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dispatcher.sqlite3"
            with SQLiteKernel(path) as kernel:
                kernel.submit(command("seed"))
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """WITH RECURSIVE numbers(n) AS (
                           VALUES(1) UNION ALL SELECT n+1 FROM numbers WHERE n<5000
                       )
                       INSERT INTO kernel_executions
                       SELECT 'bulk-'||n,'bulk-key-'||n,e.registry_revision,
                              e.command_json,e.state,e.attempt,e.redelivery_count,
                              e.next_attempt_at,e.lease_id,e.lease_owner,e.fence,
                              e.lease_expires_at,e.started_at,e.result_json,
                              e.recovery_effect_id,e.recovery_target_state,
                              e.recovery_reason,e.revision,e.created_at+n,e.updated_at+n
                       FROM kernel_executions AS e, numbers
                       WHERE e.execution_id='seed'"""
                )
                connection.commit()
            finally:
                connection.close()

            progress_calls: list[int] = []

            def expire_from_progress(budget, sqlite_connection):
                def stop() -> int:
                    progress_calls.append(1)
                    budget.deadline = time.monotonic() - 1
                    return 1 if budget.expired() else 0

                sqlite_connection.set_progress_handler(stop, 1_000)

            with patch(
                "dispatcher_sdk.diagnostics.InspectionBudget.install",
                new=expire_from_progress,
            ):
                report = inspect_diagnostics(path, timeout_seconds=60)

        self.assertTrue(progress_calls)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "timeout")
        self.assertGreater(report["sampling"]["query_count"], 0)


if __name__ == "__main__":
    unittest.main()
