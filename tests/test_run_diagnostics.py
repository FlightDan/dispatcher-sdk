from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator.run_diagnostics import inspect_run_diagnostics


class PassiveKernel:
    """The Run setup APIs need a Kernel handle but do not dispatch it."""

    pass


class RunDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.sdk = Orchestrator(self.path, PassiveKernel())
        self.sdk.create_run("run", command_id="create")

    def command(self, name: str, payload=None) -> dict:
        return ExecutionCommandV2(
            execution_id=name,
            idempotency_key=name,
            registry_revision="diagnostics-test-registry",
            correlation_id="run",
            causation_id=None,
            handler_id="echo",
            handler_contract_version=1,
            retry_policy=RetryPolicy(),
            timeout_seconds=5,
            payload={"value": name} if payload is None else payload,
        ).to_dict()

    def dump(self) -> list[str]:
        with closing(sqlite3.connect(self.path)) as connection:
            return list(connection.iterdump())

    def test_summary_pages_blockers_and_read_only_schema_check(self):
        self.sdk.apply_operations(
            "run",
            command_id="add-task-and-wait",
            expected_revision=0,
            operations=[
                {"kind": "add_task", "task_id": "task-a",
                 "command": self.command("exec-a", {"api_key": "task-private-value"})},
                {"kind": "dispatch", "task_id": "task-a"},
                {"kind": "wait", "wait_id": "approval",
                 "payload": {"token": "wait-private-value"}},
            ],
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO sdk_managed_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("run", "private-request", "private-spec-digest", "active", 2, 0,
                 12, 9999.0, 1.0, 2.0),
            )
            connection.executemany(
                "INSERT INTO sdk_managed_budget_entries VALUES(?,?,?,?,?,?)",
                [
                    ("run", "budget-1", "claims", 2, "private-budget-evidence", 1.0),
                    ("run", "budget-2", "claims", 3, "private-budget-evidence", 2.0),
                    ("run", "budget-3", "tokens", 8, "private-budget-evidence", 3.0),
                ],
            )
        before = self.dump()

        report = inspect_run_diagnostics(self.path, "run", task_limit=2, wait_limit=2)

        self.assertEqual(report.schema_status, "verified")
        self.assertIsInstance(report.schema_version, int)
        self.assertEqual(report.kernel_schema_status, "unknown")
        self.assertEqual(report.deployment_status, "unknown")
        self.assertEqual(report.run_summary["state"], "running")
        self.assertEqual(report.run_summary["generation"], 0)
        self.assertEqual(report.task_count, 1)
        self.assertEqual(report.tasks[0]["task_id"], "task-a")
        self.assertEqual(report.tasks[0]["latest_attempt"]["state"], "pending_dispatch")
        self.assertEqual(report.tasks[0]["latest_attempt"]["execution_id"], "exec-a")
        self.assertEqual(report.tasks[0]["latest_attempt"]["handler_id"], "echo")
        self.assertEqual(
            report.tasks[0]["latest_attempt"]["registry_revision"],
            "diagnostics-test-registry",
        )
        self.assertEqual(report.waits[0]["wait_id"], "approval")
        self.assertEqual(report.waits[0]["state"], "open")
        managed = report.run_summary["managed_control"]
        self.assertEqual(managed["control_state"], "active")
        self.assertEqual(managed["control_epoch"], 2)
        self.assertEqual(managed["max_claims"], 12)
        self.assertEqual(managed["budget_entry_count"], 3)
        self.assertEqual(managed["budget_counts_by_kind"], {"claims": 2, "tokens": 1})
        self.assertEqual(managed["budget_amounts_by_kind"], {"claims": 5, "tokens": 8})
        self.assertEqual(report.blockers["pending_execution_delivery"]["items"][0]["command_id"],
                         "add-task-and-wait")
        self.assertEqual(report.blockers["open_waits"]["wait_ids"], ("approval",))
        self.assertEqual(report.blockers["kernel_execution_recovery"]["status"], "unknown")
        self.assertFalse(report.blockers_complete)
        self.assertFalse(report.complete)
        encoded_report = json.dumps(report.to_dict())
        self.assertNotIn("task-private-value", encoded_report)
        self.assertNotIn("wait-private-value", encoded_report)
        self.assertNotIn("private-budget-evidence", encoded_report)
        self.assertNotIn("private-request", encoded_report)
        self.assertNotIn("private-spec-digest", encoded_report)
        self.assertEqual(before, self.dump())

        limited = inspect_run_diagnostics(
            self.path, "run", blocker_limit=1, task_limit=1, wait_limit=1)
        limited_managed = limited.run_summary["managed_control"]
        self.assertIsNone(limited_managed["budget_entry_count"])
        self.assertEqual(limited_managed["budget_entry_count_lower_bound"], 1)
        self.assertFalse(limited_managed["budget_counts_complete"])

    def test_large_run_history_returns_bounded_pages(self):
        # Populate a large current item history in one public command. The
        # diagnostic still returns only the requested task and wait pages.
        operations = [
            {"kind": "add_task", "task_id": f"task-{index:03d}",
             "command": self.command(f"exec-{index:03d}")}
            for index in range(50)
        ]
        operations.extend(
            {"kind": "wait", "wait_id": f"wait-{index:04d}"}
            for index in range(1_000)
        )
        self.sdk.apply_operations(
            "run", command_id="large-run", expected_revision=0, operations=operations)
        with closing(sqlite3.connect(self.path)) as connection:
            history_rows = connection.execute(
                "SELECT COUNT(*) FROM sdk_run_history WHERE run_id='run'").fetchone()[0]
        self.assertGreater(history_rows, 1000)

        report = inspect_run_diagnostics(
            self.path, "run", task_limit=5, wait_limit=7, blocker_limit=10)

        self.assertEqual(len(report.tasks), 5)
        self.assertTrue(report.tasks_has_more)
        self.assertEqual(len(report.waits), 7)
        self.assertTrue(report.waits_has_more)
        self.assertEqual(report.task_count, 50)
        self.assertEqual(len(report.blockers["open_waits"]["wait_ids"]), 10)
        self.assertTrue(report.blockers["open_waits"]["has_more"])
        self.assertFalse(report.blockers_complete)
        self.assertFalse(report.complete)

        count_limited = inspect_run_diagnostics(
            self.path, "run", task_count_scan_limit=10, task_limit=5,
            wait_limit=7, blocker_limit=10)
        self.assertIsNone(count_limited.task_count)
        self.assertEqual(count_limited.task_count_lower_bound, 10)
        self.assertFalse(count_limited.task_count_complete)

    def test_timeout_and_unsupported_schema_are_incomplete_and_unknown(self):
        timed_out = inspect_run_diagnostics(self.path, "run", timeout_seconds=0)
        self.assertTrue(timed_out.timed_out)
        self.assertFalse(timed_out.complete)
        self.assertEqual(timed_out.schema_status, "unknown")

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute(
                "UPDATE sdk_schema_meta SET version=99 WHERE component='orchestrator'")
        unsupported = inspect_run_diagnostics(self.path, "run")
        self.assertEqual(unsupported.schema_status, "unsupported")
        self.assertIsNone(unsupported.run_summary)
        self.assertFalse(unsupported.complete)


if __name__ == "__main__":
    unittest.main()
