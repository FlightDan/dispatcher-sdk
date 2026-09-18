from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dispatcher_sdk.content import CONTENT_PREFIX, decode_value
from dispatcher_sdk.maintenance import (
    InvalidLeaseError,
    MaintenanceBusyError,
    maintenance_lease,
    storage_participant,
)
from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.orchestrator.contracts import canonical
from dispatcher_sdk.orchestrator.notifications import NotificationsMixin
from dispatcher_sdk.orchestrator.results import ResultsMixin
from dispatcher_sdk.orchestrator.store import LEGACY_SCHEMA, execute_schema
from dispatcher_sdk.storage_migration import compact_database, upgrade_storage


class StorageMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "legacy.db"
        self.destination = self.root / "upgraded.db"

    @staticmethod
    def _digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _create_legacy(self) -> dict:
        blob = "stable-large-value:" + "x" * (70 * 1024)
        revision_zero = {
            "state": "running",
            "generation": 0,
            "input": {"blob": blob, "request": "initial"},
            "definition": {"kind": "fixture"},
            "application_state": {"blob": blob, "counter": 0},
        }
        current = {**revision_zero, "application_state": {"blob": blob, "counter": 1}}
        with closing(sqlite3.connect(self.source)) as connection:
            execute_schema(connection, LEGACY_SCHEMA)
            results = ResultsMixin()
            results.max_result_deliveries = 5
            results._init_results(connection)
            NotificationsMixin._init_notifications(connection)
            connection.execute("INSERT INTO sdk_schema_meta VALUES('orchestrator',2)")
            connection.execute("INSERT INTO sdk_runs VALUES('run',1,'running')")
            connection.executemany(
                "INSERT INTO sdk_run_revisions VALUES('run',?)", [(0,), (1,)]
            )
            for key, value in current.items():
                connection.execute(
                    "INSERT INTO sdk_run_items VALUES('run','root',?,?)",
                    (key, canonical(value)),
                )
            for key, value in revision_zero.items():
                connection.execute(
                    "INSERT INTO sdk_run_history VALUES('run','root',?,0,?)",
                    (key, canonical(value)),
                )
            connection.execute(
                "INSERT INTO sdk_run_history VALUES('run','root','application_state',1,?)",
                (canonical(current["application_state"]),),
            )
            connection.execute(
                "INSERT INTO sdk_commands VALUES('run','create','request-digest',?)",
                (canonical({"run_id": "run", "revision": 0}),),
            )
            for sequence in range(1, 4):
                connection.execute(
                    "INSERT INTO sdk_events(run_id,revision,kind,payload) VALUES('run',?,?,?)",
                    (min(sequence - 1, 1), "fixture.event", canonical({"sequence": sequence})),
                )
            connection.execute(
                "INSERT INTO sdk_recoveries("
                "recovery_id,run_id,command_id,request_digest,source_generation,target_generation,"
                "status,actor,authorization_source,reason,target_deployment,decision,application_state,"
                "owner_id,owner_fence,lease_until,waiters,manifest,error,created_at,updated_at,"
                "committed_at,activated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "recovery", "run", "recover", "digest", 0, 1, "prepared", "actor",
                    "authority", "test", "deployment", canonical({"approved": True}),
                    canonical({"blob": blob, "counter": 0}), "owner", 1, 1000.0, 0,
                    canonical({"entries": [1, 2]}), None, 1.0, 2.0, None, None,
                ),
            )
            connection.commit()
        return {"revision_zero": revision_zero, "current": current, "blob": blob}

    def test_copy_upgrade_reopens_with_equal_history_events_and_receipt(self):
        expected = self._create_legacy()
        before_hash = self._digest(self.source)
        with maintenance_lease(self.source, "test", "upgrade", lease_seconds=30) as lease:
            report = upgrade_storage(self.source, self.destination, lease=lease)

        self.assertEqual(self._digest(self.source), before_hash)
        self.assertEqual((report["source_version"], report["target_version"]), (2, 3))
        self.assertTrue(report["source_unchanged"])
        self.assertFalse(report["automatic_cutover"])
        self.assertFalse(report["resumable"])
        self.assertIn("134 GB", report["limitation"])
        self.assertGreater(report["converted_values"], 0)

        sdk = Orchestrator(self.destination, object())
        self.assertEqual(sdk.get_run("run")["application_state"], expected["current"]["application_state"])
        self.assertEqual(sdk.get_run_at("run", 0)["input"], expected["revision_zero"]["input"])
        self.assertEqual(
            sdk.get_command_receipt("run", "create")["application_state"],
            expected["revision_zero"]["application_state"],
        )
        self.assertEqual(
            [event["payload"] for event in sdk.read_events("run")],
            [{"generation": 0, "sequence": 1},
             {"generation": 0, "sequence": 2},
             {"generation": 0, "sequence": 3}],
        )

        with closing(sqlite3.connect(self.destination)) as connection:
            encoded = connection.execute(
                "SELECT application_state FROM sdk_recoveries WHERE recovery_id='recovery'"
            ).fetchone()[0]
            self.assertTrue(encoded.startswith(CONTENT_PREFIX))
            self.assertEqual(decode_value(connection, encoded)["blob"], expected["blob"])
            self.assertEqual(
                connection.execute("SELECT count(*) FROM sdk_retention_times").fetchone()[0], 0
            )
            self.assertEqual(
                connection.execute(
                    "SELECT high_water FROM sdk_event_watermarks WHERE run_id='run'"
                ).fetchone()[0],
                3,
            )

    def test_failure_and_destination_collision_never_publish_partial_output(self):
        self._create_legacy()
        failed = self.root / "failed.db"

        def failpoint(stage):
            if stage == "after_backup":
                raise RuntimeError("injected failure")

        with maintenance_lease(self.source, "test", "upgrade", lease_seconds=30) as lease:
            with self.assertRaisesRegex(RuntimeError, "injected"):
                upgrade_storage(self.source, failed, lease=lease, failpoint=failpoint)
            self.assertFalse(failed.exists())

            self.destination.write_text("preserve")
            with self.assertRaises(FileExistsError):
                upgrade_storage(self.source, self.destination, lease=lease)
            self.assertEqual(self.destination.read_text(), "preserve")

    def test_stale_or_wrong_lease_is_rejected_before_destination_creation(self):
        self._create_legacy()
        class ClaimedLease:
            def check(self, path):
                pass
        with self.assertRaises(TypeError):
            upgrade_storage(self.source, self.destination, lease=ClaimedLease())
        self.assertFalse(self.destination.exists())
        with maintenance_lease(self.source, "test", "upgrade") as stale:
            pass
        with self.assertRaises(InvalidLeaseError):
            upgrade_storage(self.source, self.destination, lease=stale)
        self.assertFalse(self.destination.exists())

        other = self.root / "other.db"
        other.write_bytes(b"not used")
        with maintenance_lease(other, "test", "other") as wrong:
            with self.assertRaises(InvalidLeaseError):
                upgrade_storage(self.source, self.destination, lease=wrong)
        self.assertFalse(self.destination.exists())

    def test_live_participant_blocks_the_required_maintenance_lease(self):
        self._create_legacy()
        with storage_participant(self.source):
            with self.assertRaises(MaintenanceBusyError):
                with maintenance_lease(self.source, "test", "upgrade"):
                    pass
        self.assertFalse(self.destination.exists())

    def test_copy_compaction_preserves_deleted_tail_sequence_high_water(self):
        self._create_legacy()
        with maintenance_lease(self.source, "test", "upgrade", lease_seconds=30) as lease:
            upgrade_storage(self.source, self.destination, lease=lease)

        with closing(sqlite3.connect(self.destination)) as connection:
            original_high = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='sdk_events'"
            ).fetchone()[0]
            connection.execute("DELETE FROM sdk_events WHERE sequence=?", (original_high,))
            connection.commit()

        compacted = self.root / "compacted.db"
        before_hash = self._digest(self.destination)
        with maintenance_lease(self.destination, "test", "compact", lease_seconds=30) as lease:
            report = compact_database(self.destination, compacted, lease)
        self.assertEqual(self._digest(self.destination), before_hash)
        self.assertEqual(report["operation"], "compact")
        self.assertFalse(report["automatic_activation"])

        with closing(sqlite3.connect(compacted)) as connection:
            preserved = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='sdk_events'"
            ).fetchone()[0]
            self.assertEqual(preserved, original_high)
            connection.execute(
                "INSERT INTO sdk_events(run_id,revision,kind,payload) VALUES('run',1,'next',?)",
                (canonical({"next": True}),),
            )
            self.assertGreater(connection.execute("SELECT last_insert_rowid()").fetchone()[0], original_high)


if __name__ == "__main__":
    unittest.main()
