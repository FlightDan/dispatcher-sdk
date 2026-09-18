from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.content import (
    CONTENT_PREFIX,
    CONTENT_SCHEMA,
    ContentIntegrityError,
    MAX_DEPTH,
    _object_digest,
    encode_value,
)
from dispatcher_sdk.maintenance import InvalidLeaseError, maintenance_lease
from dispatcher_sdk.orchestrator import EventCursorExpired, HistoryExpired, Orchestrator
from dispatcher_sdk.orchestrator.contracts import canonical
import dispatcher_sdk.retention as retention_module
from dispatcher_sdk.retention import (
    IncompleteRetentionPlan,
    RetentionError,
    RetentionPolicy,
    StaleRetentionPlan,
    apply_retention,
    plan_retention,
)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "store.sqlite3"

    def tearDown(self):
        self.temporary.cleanup()

    def _build(self, *, states=None, second_run=False):
        states = states or [{"counter": number} for number in range(1, 4)]
        with Orchestrator.open_sqlite(self.path, {}) as orchestrator:
            orchestrator.create_run("run", command_id="create")
            revision = 0
            for number, state in enumerate(states, 1):
                snapshot = orchestrator.apply_operations(
                    "run", command_id=f"commit-{number}", expected_revision=revision,
                    operations=[], application_state=state,
                )
                revision = snapshot["revision"]
            if second_run:
                orchestrator.create_run("other", command_id="other-create")
                orchestrator.apply_operations(
                    "other", command_id="other-commit", expected_revision=0,
                    operations=[], application_state=states[0],
                )

    def _unpin(self, *commands):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executemany(
                "DELETE FROM sdk_commands WHERE run_id='run' AND command_id=?",
                [(command,) for command in commands],
            )

    def _counts(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return {
                "history": connection.execute(
                    "SELECT COUNT(*) FROM sdk_run_history WHERE run_id='run'"
                ).fetchone()[0],
                "revisions": connection.execute(
                    "SELECT COUNT(*) FROM sdk_run_revisions WHERE run_id='run'"
                ).fetchone()[0],
                "events": connection.execute(
                    "SELECT COUNT(*) FROM sdk_events WHERE run_id='run'"
                ).fetchone()[0],
                "objects": connection.execute("SELECT COUNT(*) FROM sdk_content_objects").fetchone()[0],
            }

    def _replace_trigger_with_noop(self, trigger, table, action):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(f'DROP TRIGGER "{trigger}"')
            connection.execute(
                f'CREATE TRIGGER "{trigger}" AFTER {action} ON "{table}" BEGIN SELECT 1; END'
            )

    def test_receipts_preserve_every_referenced_revision_and_baseline(self):
        self._build()
        plan = plan_retention(
            self.path, "run", RetentionPolicy(history_revisions=0), scan_limit=10_000
        )
        self.assertTrue(plan["applicable"])
        self.assertEqual(plan["candidates"]["revisions"], [])
        self.assertEqual(plan["candidates"]["history"], [])
        reasons = {row["revision"]: row["reasons"] for row in plan["protected"]["revisions"]}
        self.assertTrue(any(reason.startswith("command_receipt:") for reason in reasons[1]))
        json.dumps(plan)

    def test_apply_preserves_current_state_and_receipts_and_advances_only_expiry(self):
        states = [
            {"large": "a" * 70_000, "counter": 1},
            {"large": "b" * 70_000, "counter": 2},
            {"large": "c" * 70_000, "counter": 3},
        ]
        self._build(states=states)
        self._unpin("commit-1", "commit-2")
        with Orchestrator.open_sqlite(self.path, {}) as orchestrator:
            before = orchestrator.get_run("run")
            receipt = orchestrator.get_command_receipt("run", "commit-3")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            high_before = connection.execute(
                "SELECT high_water FROM sdk_event_watermarks WHERE run_id='run'"
            ).fetchone()[0]

        plan = plan_retention(
            self.path, "run", RetentionPolicy(history_revisions=1, decision_events=1),
            scan_limit=10_000,
        )
        self.assertEqual([row["revision"] for row in plan["candidates"]["revisions"]], [1, 2])
        self.assertEqual(len(plan["candidates"]["events"]), 2)
        self.assertGreater(len(plan["candidates"]["content_objects"]), 0)
        with maintenance_lease(self.path, "test", "retention") as lease:
            result = apply_retention(self.path, plan, lease=lease)

        with Orchestrator.open_sqlite(self.path, {}) as orchestrator:
            self.assertEqual(orchestrator.get_run("run"), before)
            self.assertEqual(orchestrator.get_command_receipt("run", "commit-3"), receipt)
            with self.assertRaises(HistoryExpired):
                orchestrator.get_run_at("run", 1)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            high_after, expired = connection.execute(
                "SELECT high_water,expired_through FROM sdk_event_watermarks WHERE run_id='run'"
            ).fetchone()
        self.assertEqual(high_after, high_before)
        self.assertEqual(expired, result["event_expired_through"])
        self.assertEqual(result["deleted"]["revisions"], 2)

    def test_expired_event_opt_in_reads_survivors_with_sequence_gaps(self):
        self._build()
        self._unpin("commit-1", "commit-2")
        plan = plan_retention(
            self.path, "run", RetentionPolicy(history_revisions=1, decision_events=1),
            scan_limit=10_000,
        )
        deleted_sequences = [row["sequence"] for row in plan["candidates"]["events"]]
        self.assertEqual(len(deleted_sequences), 2)
        with maintenance_lease(self.path, "test", "retention") as lease:
            apply_retention(self.path, plan, lease=lease)

        with Orchestrator.open_sqlite(self.path, {}) as orchestrator:
            with self.assertRaises(EventCursorExpired):
                orchestrator.read_events("run", after=0)
            with self.assertRaises(EventCursorExpired):
                orchestrator.observe("run", subscription="reader")

            first = orchestrator.read_events(
                "run", after=0, limit=1, allow_expired=True
            )
            second = orchestrator.read_events(
                "run", after=first[-1]["sequence"], limit=1, allow_expired=True
            )
            self.assertEqual([event["kind"] for event in first + second], [
                "run.created", "application.decided",
            ])
            self.assertTrue(all(
                event["sequence"] not in deleted_sequences for event in first + second
            ))
            self.assertEqual(orchestrator.read_events(
                "run", after=second[-1]["sequence"], limit=1, allow_expired=True
            ), [])

    def test_apply_removes_retention_timestamps_for_deleted_records(self):
        self._build()
        self._unpin("commit-1", "commit-2")
        plan = plan_retention(
            self.path, "run", RetentionPolicy(history_revisions=1, decision_events=1),
            scan_limit=10_000,
        )
        deleted_event_keys = {
            str(row["sequence"]) for row in plan["candidates"]["events"]
        }
        deleted_revision_keys = {
            canonical([row["run_id"], row["revision"]])
            for row in plan["candidates"]["revisions"]
        }
        with maintenance_lease(self.path, "test", "retention") as lease:
            apply_retention(self.path, plan, lease=lease)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            remaining_event_keys = {
                row[0] for row in connection.execute(
                    "SELECT record_key FROM sdk_retention_times WHERE category='event'"
                )
            }
            remaining_revision_keys = {
                row[0] for row in connection.execute(
                    "SELECT record_key FROM sdk_retention_times WHERE category='revision'"
                )
            }
        self.assertTrue(deleted_event_keys)
        self.assertTrue(deleted_revision_keys)
        self.assertTrue(deleted_event_keys.isdisjoint(remaining_event_keys))
        self.assertTrue(deleted_revision_keys.isdisjoint(remaining_revision_keys))
        self.assertTrue(remaining_event_keys)
        self.assertTrue(remaining_revision_keys)

    def test_content_shared_with_another_run_is_not_collected(self):
        shared = {"large": "shared" * 12_000}
        self._build(states=[shared, {"large": "new" * 24_000}, {"large": "last" * 24_000}],
                    second_run=True)
        self._unpin("commit-1", "commit-2")
        plan = plan_retention(
            self.path, "run", RetentionPolicy(history_revisions=1, decision_events=1),
            scan_limit=20_000,
        )
        candidate_digests = [row["digest"] for row in plan["candidates"]["content_objects"]]
        self.assertEqual(len(candidate_digests), len(set(candidate_digests)))
        with maintenance_lease(self.path, "test", "retention") as lease:
            apply_retention(self.path, plan, lease=lease)
        with Orchestrator.open_sqlite(self.path, {}) as orchestrator:
            self.assertEqual(orchestrator.get_run("other")["application_state"], shared)

    def test_scan_limit_blocks_application(self):
        self._build()
        plan = plan_retention(
            self.path, "run", RetentionPolicy(history_revisions=0), scan_limit=1
        )
        self.assertFalse(plan["scan"]["complete"])
        self.assertEqual(plan["candidates"]["history"], [])
        with maintenance_lease(self.path, "test", "retention") as lease:
            with self.assertRaises(IncompleteRetentionPlan):
                apply_retention(self.path, plan, lease=lease)

    def test_tampered_and_stale_plans_delete_nothing(self):
        self._build()
        self._unpin("commit-1", "commit-2")
        policy = RetentionPolicy(history_revisions=1, decision_events=1)
        plan = plan_retention(self.path, "run", policy, scan_limit=10_000)
        before = self._counts()
        tampered = copy.deepcopy(plan)
        tampered["candidates"]["history"].clear()
        with maintenance_lease(self.path, "test", "retention") as lease:
            with self.assertRaises(RetentionError):
                apply_retention(self.path, tampered, lease=lease)
        self.assertEqual(self._counts(), before)

        with Orchestrator.open_sqlite(self.path, {}) as orchestrator:
            events = orchestrator.read_events("run", limit=100)
            orchestrator.acknowledge_events(
                "run", command_id="ack", expected_revision=3, subscription="consumer",
                expected_cursor=0, advance_to=events[-1]["sequence"],
            )
        with maintenance_lease(self.path, "test", "retention") as lease:
            with self.assertRaises(StaleRetentionPlan):
                apply_retention(self.path, plan, lease=lease)
        self.assertGreaterEqual(self._counts()["history"], before["history"])

    def test_expired_lease_and_idempotent_repeat(self):
        self._build()
        self._unpin("commit-1", "commit-2")
        plan = plan_retention(
            self.path, "run", RetentionPolicy(history_revisions=1, decision_events=1),
            scan_limit=10_000,
        )
        with maintenance_lease(
            self.path, "test", "retention", lease_seconds=30
        ) as expired:
            with patch("dispatcher_sdk.maintenance.time.time", return_value=expired.expires_at + 1):
                with self.assertRaises(InvalidLeaseError):
                    apply_retention(self.path, plan, lease=expired)

        with maintenance_lease(self.path, "test", "retention") as lease:
            first = apply_retention(self.path, plan, lease=lease)
            second = apply_retention(self.path, plan, lease=lease)
        self.assertEqual(second, first)

    def test_planner_rejects_a_trigger_with_the_right_name_and_wrong_body(self):
        self._build()
        before = self._counts()
        self._replace_trigger_with_noop(
            "sdk_events_track_delete", "sdk_events", "DELETE"
        )

        with self.assertRaisesRegex(RetentionError, "exact supported schema"):
            plan_retention(
                self.path, "run", RetentionPolicy(decision_events=0), scan_limit=10_000
            )
        self.assertEqual(self._counts(), before)

    def test_applier_rejects_changed_trigger_body_before_any_deletion(self):
        self._build()
        self._unpin("commit-1", "commit-2")
        plan = plan_retention(
            self.path, "run", RetentionPolicy(history_revisions=1, decision_events=1),
            scan_limit=10_000,
        )
        before = self._counts()
        self._replace_trigger_with_noop(
            "sdk_run_history_track_delete", "sdk_run_history", "DELETE"
        )

        with maintenance_lease(self.path, "test", "retention") as lease:
            with self.assertRaisesRegex(RetentionError, "exact supported schema"):
                apply_retention(self.path, plan, lease=lease)
        self.assertEqual(self._counts(), before)

    def test_scanner_enforces_aggregate_stored_byte_budget(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("CREATE TABLE payloads(value TEXT NOT NULL)")
            connection.executemany(
                "INSERT INTO payloads VALUES(?)", [("a" * 40,), ("b" * 40,), ("c" * 40,)]
            )
            scanner = retention_module._Scanner(connection, 10)
            scanner.byte_limit = 90

            with self.assertRaises(retention_module._BudgetExceeded):
                scanner.rows("SELECT value FROM payloads", (), "payloads")
            self.assertEqual(scanner.used, 2)
            self.assertEqual(scanner.bytes_used, 80)
        finally:
            connection.close()

    def test_scanner_does_not_transfer_an_individually_oversized_body(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("CREATE TABLE payloads(value TEXT NOT NULL)")
            connection.execute("INSERT INTO payloads VALUES(?)", ("x" * 1_000,))
            scanner = retention_module._Scanner(connection, 10)
            scanner.byte_limit = 64
            connection.text_factory = lambda _value: self.fail("oversized body reached Python")

            with self.assertRaises(retention_module._BudgetExceeded):
                scanner.rows("SELECT value FROM payloads", (), "payloads")
            self.assertEqual(scanner.used, 0)
            self.assertEqual(scanner.bytes_used, 0)
        finally:
            connection.close()

    def test_cached_content_dag_keeps_descendants_reachable(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(CONTENT_SCHEMA)
            shared = "shared-value-" * 6_000
            first_root = encode_value(connection, {"first": shared, "second": shared})
            second_root = encode_value(connection, {"nested": {"value": shared}})
            objects = {
                row["digest"]: (row["encoded"], row["logical_bytes"])
                for row in connection.execute(
                    "SELECT digest,encoded,logical_bytes FROM sdk_content_objects"
                )
            }
            graph = retention_module._ContentGraph(connection, objects)
            # Seed every cache entry as the planner does while validating even
            # currently orphaned objects, then traverse retained roots.
            for identity, (_, logical_bytes) in objects.items():
                graph.walk(["ref", identity, logical_bytes], set())

            first = graph.references(first_root)
            second = graph.references(second_root)
            self.assertGreaterEqual(len(first), 2)
            self.assertGreaterEqual(len(second), 2)
            self.assertTrue(first & second)
            self.assertEqual(graph.references(first_root), first)
        finally:
            connection.close()

    def test_content_graph_rejects_reference_chain_over_decoder_limit(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute(CONTENT_SCHEMA)
            logical_bytes = 4
            encoded = canonical(["null"])
            digest = _object_digest(encoded)
            objects = {digest: (encoded, logical_bytes)}
            for _ in range(MAX_DEPTH):
                encoded = canonical(["ref", digest, logical_bytes])
                digest = _object_digest(encoded)
                objects[digest] = (encoded, logical_bytes)

            graph = retention_module._ContentGraph(connection, objects)
            root = CONTENT_PREFIX + canonical(["ref", digest, logical_bytes])

            with self.assertRaisesRegex(ContentIntegrityError, "reference depth"):
                graph.references(root)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
