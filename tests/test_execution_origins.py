from __future__ import annotations

from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.content import encode_value
from dispatcher_sdk.execution_kernel import RetryPolicy
from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator.origins import inspect_execution_origin


def echo(payload, _context):
    return payload


class ExecutionOriginTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "store.sqlite3"
        self.sdk = Orchestrator.open_sqlite(
            self.path, {"echo": echo}, isolation_mode="thread"
        )
        self.addCleanup(self.sdk.close)

    def command(self, execution_id: str, *, payload=None) -> dict:
        return self.sdk.runtime.command(
            execution_id=execution_id,
            idempotency_key=execution_id,
            correlation_id="run",
            causation_id=None,
            handler_id="echo",
            handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=1),
            timeout_seconds=5,
            payload={"execution": execution_id} if payload is None else payload,
        ).to_dict()

    def test_content_lookup_requires_a_complete_unique_digest_index(self):
        self.add_cancelled_attempts_and_continuation()
        for partial in (False, True):
            with self.subTest(partial=partial):
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute("DROP TABLE sdk_content_objects")
                    connection.execute(
                        "CREATE TABLE sdk_content_objects(digest TEXT,encoded TEXT NOT NULL,logical_bytes INTEGER NOT NULL)")
                    if partial:
                        connection.execute(
                            "CREATE UNIQUE INDEX partial_digest ON sdk_content_objects(digest) WHERE logical_bytes>0")
                report = inspect_execution_origin(self.path, execution_id="old")
                self.assertEqual(report.status, "incomplete")
                self.assertIn("unsupported_or_incomplete_schema", report.reason_codes)

    def test_referenced_encoded_bytes_share_one_payload_budget(self):
        self.add_cancelled_attempts_and_continuation()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute(
                "SELECT value FROM sdk_run_items WHERE run_id='run' AND section='attempt' AND item_key=?",
                ('["task",0]',)).fetchone()
            attempt = json.loads(row[0])
            attempt["extra"] = {f"k{index}": f"unique-value-{index}" for index in range(250)}
            encoded = encode_value(connection, attempt, threshold=1)
            connection.execute(
                "UPDATE sdk_run_items SET value=? WHERE run_id='run' AND section='attempt' AND item_key=?",
                (encoded, '["task",0]'))
            total, largest = connection.execute(
                "SELECT sum(length(CAST(encoded AS BLOB))),max(length(CAST(encoded AS BLOB))) FROM sdk_content_objects"
            ).fetchone()
        limit = largest + 2000  # Each object fits, but their cumulative bytes do not.
        self.assertGreater(total, limit)
        report = inspect_execution_origin(self.path, execution_id="old", max_payload_bytes=limit,
                                          max_query_steps=1_000_000)
        self.assertEqual(report.reason_codes, ("payload_budget_exceeded",))
        complete = inspect_execution_origin(self.path, execution_id="old", max_payload_bytes=total + 10_000,
                                            max_query_steps=1_000_000)
        self.assertEqual(complete.status, "found", complete)

    def test_depth_corruption_is_not_reported_as_a_byte_budget(self):
        self.add_cancelled_attempts_and_continuation()
        nested = []
        for _ in range(105):
            nested = [nested]
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute(
                "SELECT value FROM sdk_run_items WHERE run_id='run' AND section='attempt' AND item_key=?",
                ('["task",0]',)).fetchone()
            attempt = json.loads(row[0])
            attempt["extra"] = nested
            connection.execute(
                "UPDATE sdk_run_items SET value=? WHERE run_id='run' AND section='attempt' AND item_key=?",
                (json.dumps(attempt), '["task",0]'))
        report = inspect_execution_origin(self.path, execution_id="old")
        self.assertEqual(report.reason_codes, ("stored_origin_payload_invalid",))

    def test_missing_task_identity_and_blob_link_do_not_produce_complete_evidence(self):
        self.add_cancelled_attempts_and_continuation()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            original = connection.execute(
                "SELECT value FROM sdk_run_items WHERE run_id='run' AND section='task' AND item_key='task'"
            ).fetchone()[0]
            connection.execute("UPDATE sdk_run_items SET value='{}' WHERE run_id='run' AND section='task'")
        report = inspect_execution_origin(self.path, execution_id="old")
        self.assertEqual(report.status, "incomplete")
        self.assertIn("task_identity_mismatch", report.reason_codes)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE sdk_run_items SET value=? WHERE run_id='run' AND section='task'", (original,))
            connection.execute("UPDATE sdk_run_links SET next_run_id=x'ff' WHERE previous_run_id='run'")
        report = inspect_execution_origin(self.path, execution_id="old")
        self.assertEqual(report.reason_codes, ("stored_origin_payload_invalid",))
        json.dumps(report.to_dict(), allow_nan=False)

    def add_cancelled_attempts_and_continuation(self):
        self.sdk.create_run("run", command_id="create", definition={"kind": "origin"})
        self.sdk.apply_operations(
            "run",
            command_id="old",
            expected_revision=0,
            operations=[
                {"kind": "add_task", "task_id": "task", "command": self.command("old")},
                {"kind": "cancel", "task_id": "task", "reason": "retry"},
            ],
        )
        self.sdk.apply_operations(
            "run",
            command_id="new",
            expected_revision=1,
            operations=[
                {"kind": "new_attempt", "task_id": "task", "command": self.command("new")},
                {"kind": "cancel", "task_id": "task", "reason": "done"},
            ],
        )
        finished = self.sdk.apply_operations(
            "run",
            command_id="finish",
            expected_revision=2,
            operations=[{"kind": "finish", "state": "succeeded"}],
        )
        self.sdk.continue_run(
            "run", "next", command_id="continue", expected_revision=finished["revision"]
        )

    def insert_result(self, result_id: str, execution_id: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO sdk_results("
                "result_id,execution_id,result_json,kernel_revision,state,lease_id,lease_owner,"
                "fence,attempts,max_attempts,lease_expires_at,next_attempt_at,last_error_json,"
                "revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result_id,
                    execution_id,
                    "{}",
                    1,
                    "delivered",
                    None,
                    None,
                    0,
                    0,
                    1,
                    None,
                    0.0,
                    None,
                    1,
                    0.0,
                    0.0,
                ),
            )

    def test_result_lookup_finds_original_segment_and_old_attempt(self):
        self.add_cancelled_attempts_and_continuation()
        self.insert_result("result-old", "old")

        report = inspect_execution_origin(self.path, result_id="result-old")

        self.assertEqual(report.status, "found")
        self.assertTrue(report.complete)
        self.assertEqual(report.reason_codes, ())
        self.assertEqual(report.execution_id, "old")
        self.assertEqual(report.result_id, "result-old")
        self.assertEqual(report.run_id, "run")
        self.assertEqual(report.next_run_id, "next")
        self.assertIsNone(report.previous_run_id)
        self.assertEqual(report.task_id, "task")
        self.assertEqual(report.application_attempt, 0)
        self.assertEqual(report.generation, 0)
        self.assertEqual(report.command["execution_id"], "old")
        self.assertEqual(report.attempt["state"], "cancelled")
        self.assertNotIn("command", report.attempt)
        self.assertEqual(report.handler_binding.handler_id, "echo")
        self.assertEqual(report.handler_binding.handler_contract_version, 1)
        self.assertEqual(
            report.handler_binding.registry_revision, report.command["registry_revision"]
        )
        json.dumps(report.to_dict())

    def test_execution_lookup_uses_exact_attempt_instead_of_latest(self):
        self.add_cancelled_attempts_and_continuation()

        old = inspect_execution_origin(self.path, execution_id="old")
        new = inspect_execution_origin(self.path, execution_id="new")

        self.assertEqual((old.application_attempt, old.command["execution_id"]), (0, "old"))
        self.assertEqual((new.application_attempt, new.command["execution_id"]), (1, "new"))

    def test_missing_identity_is_scoped_to_the_supplied_store(self):
        self.sdk.create_run("run", command_id="create")

        execution = inspect_execution_origin(self.path, execution_id="absent")
        result = inspect_execution_origin(self.path, result_id="absent")

        self.assertEqual(execution.status, "not_found")
        self.assertTrue(execution.complete)
        self.assertEqual(
            execution.reason_codes, ("execution_not_found_in_supplied_store",)
        )
        self.assertEqual(result.status, "not_found")
        self.assertTrue(result.complete)
        self.assertEqual(result.reason_codes, ("result_not_found_in_supplied_store",))
        self.assertEqual(execution.source_scope, "supplied_store")

    def test_payload_and_sql_step_budgets_return_incomplete_reports(self):
        self.sdk.create_run("run", command_id="create")
        self.sdk.apply_operations(
            "run",
            command_id="large",
            expected_revision=0,
            operations=[
                {
                    "kind": "add_task",
                    "task_id": "task",
                    "command": self.command("large", payload={"blob": "x" * 10_000}),
                }
            ],
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute(
                "SELECT value FROM sdk_run_items WHERE run_id='run' AND section='attempt'"
            ).fetchone()
            value = json.loads(row[0])
            encoded = encode_value(connection, value, threshold=1)
            connection.execute(
                "UPDATE sdk_run_items SET value=? "
                "WHERE run_id='run' AND section='attempt'",
                (encoded,),
            )

        payload = inspect_execution_origin(
            self.path, execution_id="large", max_payload_bytes=512
        )
        sql = inspect_execution_origin(
            self.path, execution_id="large", max_query_steps=1
        )
        class Clock:
            calls = 0

            def __call__(self):
                self.calls += 1
                return 0.0 if self.calls == 1 else 1.0

        with patch("dispatcher_sdk.orchestrator.origins.time.monotonic", new=Clock()):
            timed_out = inspect_execution_origin(
                self.path, execution_id="large", timeout=0.5
            )

        self.assertEqual(payload.status, "incomplete")
        self.assertEqual(payload.reason_codes, ("payload_budget_exceeded",))
        self.assertEqual(sql.status, "incomplete")
        self.assertEqual(sql.reason_codes, ("query_step_budget_exceeded",))
        self.assertEqual(timed_out.status, "incomplete")
        self.assertEqual(timed_out.reason_codes, ("inspection_timeout",))

    def test_point_lookup_does_not_load_run_history_or_write(self):
        self.sdk.create_run("run", command_id="create")
        self.sdk.apply_operations(
            "run",
            command_id="target",
            expected_revision=0,
            operations=[
                {"kind": "add_task", "task_id": "task", "command": self.command("target")}
            ],
        )
        statements: list[str] = []

        @contextmanager
        def traced_reader(path, *, timeout=30):
            connection = sqlite3.connect(
                Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.set_trace_callback(statements.append)
            try:
                yield connection
            finally:
                connection.close()

        with patch("dispatcher_sdk.orchestrator.origins._read_only", traced_reader):
            report = inspect_execution_origin(self.path, execution_id="target")

        self.assertEqual(report.status, "found")
        normalized = [statement.strip().upper() for statement in statements]
        self.assertFalse(any(" FROM SDK_RUN_HISTORY " in statement for statement in normalized))
        self.assertFalse(any("SELECT SECTION,ITEM_KEY,VALUE" in statement for statement in normalized))
        self.assertFalse(any(statement.startswith(("INSERT", "UPDATE", "DELETE")) for statement in normalized))

    def test_disposed_pruned_and_unknown_evidence_have_distinct_reasons(self):
        self.sdk.create_run("run", command_id="create")
        self.sdk.apply_operations(
            "run", command_id="add", expected_revision=0,
            operations=[{"kind": "add_task", "task_id": "task", "command": self.command("target")}],
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO sdk_disposed_runs VALUES('run','{}','test-authentication')"
            )
        disposed = inspect_execution_origin(self.path, execution_id="target")
        self.assertEqual(disposed.reason_codes, ("origin_run_disposed",))

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM sdk_disposed_runs WHERE run_id='run'")
            connection.execute(
                "DELETE FROM sdk_run_items WHERE run_id='run' AND section='attempt'"
            )
            connection.execute(
                "DELETE FROM sdk_run_history WHERE run_id='run' AND section='attempt'"
            )
        unknown = inspect_execution_origin(self.path, execution_id="target")
        self.assertEqual(unknown.reason_codes, ("attempt_evidence_unknown",))

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO sdk_expired_revisions VALUES('run',0)")
        pruned = inspect_execution_origin(self.path, execution_id="target")
        self.assertEqual(pruned.reason_codes, ("attempt_evidence_pruned",))

    def test_same_execution_identity_is_resolved_only_within_supplied_store(self):
        self.sdk.create_run("run", command_id="create")
        self.sdk.apply_operations(
            "run", command_id="add", expected_revision=0,
            operations=[{"kind": "add_task", "task_id": "first", "command": self.command("same")}],
        )
        second_path = Path(self.temporary.name) / "second.sqlite3"
        second = Orchestrator.open_sqlite(
            second_path, {"echo": echo}, isolation_mode="thread"
        )
        self.addCleanup(second.close)
        second.create_run("other", command_id="create")
        command = second.runtime.command(
            execution_id="same", idempotency_key="same", correlation_id="other",
            causation_id=None, handler_id="echo", handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=5, payload={},
        ).to_dict()
        second.apply_operations(
            "other", command_id="add", expected_revision=0,
            operations=[{"kind": "add_task", "task_id": "second", "command": command}],
        )

        first_report = inspect_execution_origin(self.path, execution_id="same")
        second_report = inspect_execution_origin(second_path, execution_id="same")

        self.assertEqual((first_report.run_id, first_report.task_id), ("run", "first"))
        self.assertEqual((second_report.run_id, second_report.task_id), ("other", "second"))
        self.assertNotEqual(first_report.store_id, second_report.store_id)


if __name__ == "__main__":
    unittest.main()
