from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy, Runtime
from dispatcher_sdk.orchestrator import Orchestrator, CommandConflict, OrchestrationError


def echo(payload, context):
    return payload


class RunHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.db"
        self.runtime = Kernel.open_sqlite(self.path, {"echo": echo}, isolation_mode="thread")
        self.addCleanup(self.runtime.close)
        self.sdk = Orchestrator(self.path, self.runtime.kernel, runtime=self.runtime)
        self.sdk.create_run("run", command_id="create", definition={"kind": "story"})

    def command(self, name):
        return ExecutionCommandV2(
            execution_id=name, idempotency_key=name, registry_revision=self.runtime.registry_revision,
            correlation_id="run", causation_id=None, handler_id="echo", handler_contract_version=1,
            retry_policy=RetryPolicy(), timeout_seconds=5, payload={"data": "x" * 128})

    def add_cancelled(self, index):
        name = f"task-{index:04d}"
        return self.sdk.apply_operations(
            "run", command_id=name, expected_revision=self.sdk.get_run_summary("run")["revision"],
            operations=[{"kind": "add_task", "task_id": name, "command": self.command(name).to_dict()},
                        {"kind": "cancel", "task_id": name, "reason": "finished"}])

    def stored_bytes(self):
        with closing(sqlite3.connect(self.path)) as c, c:
            return sum(c.execute(f"SELECT COALESCE(SUM(length({column})),0) FROM {table}").fetchone()[0]
                       for table, column in (("sdk_run_items", "value"), ("sdk_run_history", "value"),
                                             ("sdk_commands", "response"), ("sdk_executions", "command"),
                                             ("sdk_events", "payload")))

    def test_incremental_history_and_receipts_grow_linearly_and_replay_original(self):
        original = self.add_cancelled(0)
        for i in range(1, 50):
            self.add_cancelled(i)
        before = self.stored_bytes()
        for i in range(50, 100):
            self.add_cancelled(i)
        self.assertLess(self.stored_bytes(), before * 2.2)
        with closing(sqlite3.connect(self.path)) as c, c:
            self.assertLess(c.execute("SELECT MAX(length(response)) FROM sdk_commands").fetchone()[0], 100)
        self.assertEqual(self.sdk.get_command_receipt("run", "task-0000"), original)
        self.assertEqual(self.sdk.get_run_at("run", 1), original)
        self.assertEqual(len(self.sdk.get_run("run")["tasks"]), 100)

    def test_noop_does_not_query_history_execution_registration(self):
        for i in range(10):
            self.add_cancelled(i)
        statements = []
        connect = self.sdk._connect
        def traced():
            c = connect()
            c.set_trace_callback(statements.append)
            return c
        with patch.object(self.sdk, "_connect", traced):
            self.sdk.apply_operations("run", command_id="noop", expected_revision=10, operations=[])
        self.assertFalse(any("FROM sdk_executions" in statement for statement in statements))

    def test_idle_sync_does_not_read_completed_executions(self):
        command = self.command("done")
        self.runtime.kernel.cancel_before_accept(command, reason="cancelled")
        self.sdk.apply_operations("run", command_id="add", expected_revision=0, operations=[
            {"kind": "add_task", "task_id": "done", "command": command.to_dict()},
            {"kind": "dispatch", "task_id": "done"}])
        self.assertEqual(self.sdk.sync(), 1)
        with patch.object(self.runtime.kernel, "get", side_effect=AssertionError("read terminal history")):
            self.assertEqual(self.sdk.sync(), 0)

    def test_bounded_views_do_not_load_full_run_and_history_is_retained_after_continuation(self):
        for i in range(3):
            self.add_cancelled(i)
        with patch.object(self.sdk, "_load", side_effect=AssertionError("full Run read")):
            self.assertEqual(self.sdk.get_run_summary("run")["task_count"], 3)
            first = self.sdk.list_tasks("run", limit=2)
            self.assertEqual(len(first), 2)
            self.assertEqual(len(self.sdk.list_tasks("run", after_task_id=first[-1]["task_id"])), 1)
            self.assertEqual(len(self.sdk.list_attempts("run", first[0]["task_id"], limit=1)), 1)
            self.assertEqual(len(self.sdk.read_events("run", limit=1)), 1)
        completed = self.sdk.apply_operations("run", command_id="finish", expected_revision=3,
                                              operations=[{"kind": "finish", "state": "succeeded"}])
        args = {"command_id": "next", "expected_revision": completed["revision"], "input": {"chapter": 2}}
        continuation = self.sdk.continue_run("run", "next-run", **args)
        self.assertEqual(continuation["tasks"], {})
        self.assertEqual(continuation["definition"], {"kind": "story"})
        self.assertEqual(self.sdk.get_run_summary("run")["next_run_id"], "next-run")
        self.assertEqual(self.sdk.get_run_summary("next-run")["previous_run_id"], "run")
        self.sdk.apply_operations("next-run", command_id="wait", expected_revision=0,
                                  operations=[{"kind": "wait", "wait_id": "review"}])
        self.assertEqual(self.sdk.continue_run("run", "next-run", **args), continuation)
        self.assertEqual(self.sdk.get_run_at("run", completed["revision"]), completed)
        with self.assertRaises(CommandConflict):
            self.sdk.continue_run("run", "next-run", **{**args, "input": {"chapter": 3}})

    def test_continuation_rejects_active_run_and_rolls_back_failed_commit(self):
        with self.assertRaises(OrchestrationError):
            self.sdk.continue_run("run", "next", command_id="continue", expected_revision=0)
        self.sdk.apply_operations("run", command_id="finish", expected_revision=0,
                                  operations=[{"kind": "finish", "state": "succeeded"}])
        self.sdk._failpoint = lambda name: (_ for _ in ()).throw(RuntimeError("crash"))
        with self.assertRaises(RuntimeError):
            self.sdk.continue_run("run", "next", command_id="continue", expected_revision=1)
        self.assertEqual(len(self.sdk.list_runs()), 1)
        self.assertIsNone(self.sdk.get_run_summary("run")["next_run_id"])

    def test_schema_damage_and_unversioned_store_are_rejected_without_recreation(self):
        old = Path(self.tmp.name) / "old.db"
        with closing(sqlite3.connect(old)) as c, c:
            c.execute("CREATE TABLE sdk_runs(run_id TEXT PRIMARY KEY, revision INTEGER, snapshot TEXT)")
            c.execute("INSERT INTO sdk_runs VALUES('kept',1,'original')")
        with self.assertRaisesRegex(OrchestrationError, "unversioned"):
            Orchestrator(old, self.runtime.kernel)
        with closing(sqlite3.connect(old)) as c, c:
            self.assertEqual(c.execute("SELECT snapshot FROM sdk_runs").fetchone()[0], "original")
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='sdk_schema_meta'").fetchone())
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute("DROP TABLE sdk_run_history")
        with self.assertRaisesRegex(OrchestrationError, "schema differs"):
            Orchestrator(self.path, self.runtime.kernel)
        with closing(sqlite3.connect(self.path)) as c, c:
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='sdk_run_history'").fetchone())


class SchemaLiteralTests(unittest.TestCase):
    def test_literal_case_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.db"
            with Runtime(path, {}, isolation_mode="thread") as runtime:
                Orchestrator(path, runtime.kernel)
                with closing(sqlite3.connect(path)) as connection, connection:
                    sql = connection.execute("SELECT sql FROM sqlite_master WHERE name='sdk_results'").fetchone()[0]
                    self.assertIn("'pending'", sql)
                    connection.execute("DROP TABLE sdk_results")
                    connection.execute(sql.replace("'pending'", "'PENDING'"))
                with self.assertRaisesRegex(OrchestrationError, "schema differs"):
                    Orchestrator(path, runtime.kernel)


if __name__ == "__main__":
    unittest.main()
