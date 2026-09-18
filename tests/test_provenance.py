from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.maintenance import MaintenanceBusyError, maintenance_lease
from dispatcher_sdk.orchestrator import Operations, Orchestrator
from dispatcher_sdk.orchestrator.contracts import RunDisposed
from dispatcher_sdk.provenance import (
    ProvenanceError,
    ProvenanceRegistry,
    RegistryIntegrityError,
    StaleDisposalPlan,
    dispose_run,
    plan_disposal,
)


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = self.root / "store.db"
        self.registry_path = self.root / "registry.db"
        self.key = b"registry-test-key-material-32bytes!"

    def _registry(self):
        return ProvenanceRegistry(self.registry_path, self.key)

    def _create_run(self, run_id: str, *, terminal: bool = True) -> Orchestrator:
        sdk = Orchestrator(self.store, object())
        sdk.create_run(run_id, command_id=f"create-{run_id}")
        if terminal:
            sdk.apply_operations(
                run_id,
                command_id=f"finish-{run_id}",
                expected_revision=0,
                operations=[Operations.finish("succeeded")],
            )
        return sdk

    def test_registry_reopens_and_rejects_constraint_tampering(self):
        self._create_run("persisted")
        registry = self._registry()
        self.assertEqual(registry.revision, 0)
        origin = registry.register_run(self.store, "persisted")
        expected_revision = registry.close_scope()
        reopened = self._registry()
        self.assertEqual(reopened.revision, expected_revision)
        self.assertEqual(reopened.resolve(origin)["path"], str(self.store.resolve()))

        tampered_path = self.root / "tampered-registry.db"
        with closing(sqlite3.connect(tampered_path)) as connection:
            connection.execute(
                "CREATE TABLE provenance_registry ("
                " singleton INTEGER PRIMARY KEY CHECK(singleton IN (1,2)),"
                " document TEXT NOT NULL,"
                " authentication TEXT NOT NULL"
                ")"
            )
            connection.commit()
        with self.assertRaisesRegex(RegistryIntegrityError, "schema"):
            ProvenanceRegistry(tampered_path, self.key)
        with maintenance_lease(
            tampered_path, "test", "rejected-registry-cleanup", lease_seconds=30
        ) as lease:
            lease.check(tampered_path)

    def test_registry_connections_obey_maintenance_and_snapshot_gates(self):
        registry = self._registry()
        with maintenance_lease(
            self.registry_path, "test", "registry-maintenance", lease_seconds=30
        ):
            with self.assertRaises(MaintenanceBusyError):
                _ = registry.revision
            with self.assertRaises(MaintenanceBusyError):
                registry.close_scope()
            with self.assertRaises(MaintenanceBusyError):
                self._registry()

        snapshot_root = self.root / "snapshot"
        snapshot_root.mkdir()
        snapshot_registry = snapshot_root / "registry.db"
        existing = ProvenanceRegistry(snapshot_registry, self.key)
        (snapshot_root / ".sdk-snapshot-readonly").touch()
        with self.assertRaisesRegex(PermissionError, "snapshot"):
            existing.close_scope()
        with self.assertRaisesRegex(PermissionError, "snapshot"):
            ProvenanceRegistry(snapshot_root / "new-registry.db", self.key)
        self.assertFalse((snapshot_root / "new-registry.db").exists())

    def test_registry_authenticates_references_and_archive_locators(self):
        self._create_run("source")
        self._create_run("target")
        registry = self._registry()
        source = registry.register_run(self.store, "source", header={"kind": "continuation"})
        target = registry.register_run(self.store, "target", header={"kind": "origin"})

        with self.assertRaisesRegex(ProvenanceError, "does not match"):
            registry.add_reference(source, target, "0" * 64)
        revision = registry.add_reference(source, target, target)
        self.assertGreater(revision, 0)
        hot = registry.resolve(target)
        self.assertEqual((hot["kind"], hot["path"]), ("hot", str(self.store.resolve())))
        self.assertTrue(registry.verify_locator(hot))
        tampered = {**hot, "path": str(self.root / "foreign.db")}
        with self.assertRaises(RegistryIntegrityError):
            registry.verify_locator(tampered)

        artifact = self.root / "archive.bin"
        artifact.write_bytes(b"authenticated cold archive")
        artifact_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        registry.register_archive(target, artifact, artifact_digest=artifact_digest)
        retained_hot = registry.resolve(target)
        self.assertEqual(retained_hot["kind"], "hot")
        cold = registry.resolve(target, prefer_cold=True)
        self.assertEqual(cold["kind"], "cold")
        self.assertEqual(cold["artifact_digest"], artifact_digest)
        self.assertFalse(cold["origin_bound"])
        self.assertTrue(registry.verify_locator(cold))
        artifact.write_bytes(b"changed after registration")
        with self.assertRaisesRegex(RegistryIntegrityError, "digest verification"):
            registry.resolve(target, prefer_cold=True)
        self.assertEqual(registry.resolve(target)["kind"], "hot")

    def test_corrupt_registry_and_unknown_scope_fail_closed(self):
        self._create_run("run")
        registry = self._registry()
        registry.register_run(self.store, "run")
        plan = plan_disposal(self.store, "run", registry)
        self.assertFalse(plan["applicable"])
        self.assertIn("registry_scope_not_closed", {item["code"] for item in plan["blockers"]})

        with closing(sqlite3.connect(self.registry_path)) as connection:
            document = connection.execute(
                "SELECT document FROM provenance_registry"
            ).fetchone()[0]
            parsed = json.loads(document)
            parsed["revision"] += 1
            connection.execute(
                "UPDATE provenance_registry SET document=?",
                (json.dumps(parsed, sort_keys=True, separators=(",", ":")),),
            )
            connection.commit()
        with self.assertRaises(RegistryIntegrityError):
            registry.resolve(plan["origin_digest"])

    def test_incoming_reference_and_active_run_are_explicit_blockers(self):
        self._create_run("target")
        self._create_run("source", terminal=False)
        registry = self._registry()
        target = registry.register_run(self.store, "target")
        source = registry.register_run(self.store, "source")
        registry.close_scope()
        registry.add_reference(source, target, target)

        target_plan = plan_disposal(self.store, "target", registry)
        self.assertFalse(target_plan["applicable"])
        self.assertIn(
            "incoming_provenance_references",
            {item["code"] for item in target_plan["blockers"]},
        )
        source_plan = plan_disposal(self.store, "source", registry)
        self.assertFalse(source_plan["applicable"])
        self.assertIn("run_not_terminal", {item["code"] for item in source_plan["blockers"]})

    def test_disposal_leaves_signed_tombstone_and_shared_run_untouched(self):
        sdk = self._create_run("dispose")
        self._create_run("survivor")
        survivor_before = sdk.get_run("survivor")
        registry = self._registry()
        origin = registry.register_run(self.store, "dispose", header={"source": "test"})
        registry.register_run(self.store, "survivor")
        registry.close_scope()
        plan = plan_disposal(self.store, "dispose", registry)
        self.assertTrue(plan["applicable"], plan["blockers"])

        with maintenance_lease(self.store, "test", "dispose", lease_seconds=30) as lease:
            result = dispose_run(
                plan, registry, lease=lease, operation_id="dispose-operation"
            )
        self.assertFalse(result["idempotent_replay"])
        self.assertTrue(result["content_objects_preserved"])
        self.assertEqual(sdk.get_run("survivor"), survivor_before)
        with self.assertRaises(RunDisposed):
            sdk.get_run("dispose")
        with self.assertRaises(RunDisposed):
            sdk.get_command_receipt("dispose", "create-dispose")

        with closing(sqlite3.connect(self.store)) as connection:
            row = connection.execute(
                "SELECT tombstone,authentication FROM sdk_disposed_runs WHERE run_id='dispose'"
            ).fetchone()
            tombstone = json.loads(row[0])
            self.assertTrue(registry.verify_tombstone(tombstone, row[1]))
            self.assertEqual(tombstone["origin_digest"], origin)
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM sdk_runs WHERE run_id='survivor'"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT seq FROM sqlite_sequence WHERE name='sdk_events'").fetchone()[0],
                4,
            )
        locator = registry.resolve(origin)
        self.assertEqual(locator["kind"], "disposed")
        self.assertTrue(registry.verify_locator(locator))
        with maintenance_lease(self.store, "test", "dispose-replay", lease_seconds=30) as lease:
            replay = dispose_run(
                plan, registry, lease=lease, operation_id="dispose-operation"
            )
            self.assertTrue(replay["idempotent_replay"])
            with self.assertRaises(StaleDisposalPlan):
                dispose_run(
                    plan, registry, lease=lease, operation_id="different-operation"
                )

    def test_disposal_closes_source_if_registry_connection_is_blocked(self):
        self._create_run("run")
        registry = self._registry()
        registry.register_run(self.store, "run")
        registry.close_scope()
        plan = plan_disposal(self.store, "run", registry)
        opened = []
        sqlite_connect = sqlite3.connect

        def track_source_connection(*args, **kwargs):
            connection = sqlite_connect(*args, **kwargs)
            opened.append(connection)
            return connection

        with maintenance_lease(
            self.store, "test", "dispose", lease_seconds=30
        ) as source_lease, maintenance_lease(
            self.registry_path, "test", "registry-maintenance", lease_seconds=30
        ):
            with patch(
                "dispatcher_sdk.provenance.sqlite3.connect",
                side_effect=track_source_connection,
            ):
                with self.assertRaises(MaintenanceBusyError):
                    dispose_run(
                        plan,
                        registry,
                        lease=source_lease,
                        operation_id="blocked-registry",
                    )

        original_registry_path = registry.path
        with maintenance_lease(
            self.store, "test", "dispose-same-path", lease_seconds=30
        ) as source_lease:
            registry.path = self.store
            try:
                with patch(
                    "dispatcher_sdk.provenance.sqlite3.connect",
                    side_effect=track_source_connection,
                ):
                    with self.assertRaises(MaintenanceBusyError):
                        dispose_run(
                            plan,
                            registry,
                            lease=source_lease,
                            operation_id="same-path-registry",
                        )
            finally:
                registry.path = original_registry_path

        self.assertEqual(len(opened), 2)
        for connection in opened:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_stale_and_tampered_plans_are_rejected_before_deletion(self):
        sdk = self._create_run("run")
        registry = self._registry()
        registry.register_run(self.store, "run")
        registry.close_scope()
        plan = plan_disposal(self.store, "run", registry)

        tampered = dict(plan)
        tampered["run_state"] = "failed"
        with maintenance_lease(self.store, "test", "dispose", lease_seconds=30) as lease:
            with self.assertRaisesRegex(ProvenanceError, "modified"):
                dispose_run(tampered, registry, lease=lease, operation_id="tampered")

        sdk.create_run("later", command_id="create-later")
        with maintenance_lease(self.store, "test", "dispose", lease_seconds=30) as lease:
            with self.assertRaises(StaleDisposalPlan):
                dispose_run(plan, registry, lease=lease, operation_id="stale")
        self.assertEqual(sdk.get_run("run")["state"], "succeeded")

    def test_failpoints_leave_a_recoverable_deleting_state(self):
        for stage in ("before_source_commit", "after_source_commit"):
            with self.subTest(stage=stage):
                store = self.root / f"{stage}.db"
                registry_path = self.root / f"{stage}-registry.db"
                sdk = Orchestrator(store, object())
                sdk.create_run("run", command_id="create")
                sdk.apply_operations(
                    "run", command_id="finish", expected_revision=0,
                    operations=[Operations.finish("succeeded")],
                )
                registry = ProvenanceRegistry(registry_path, self.key)
                origin = registry.register_run(store, "run")
                registry.close_scope()
                plan = plan_disposal(store, "run", registry)

                def failpoint(name):
                    if name == stage:
                        raise RuntimeError(f"failure at {stage}")

                with maintenance_lease(store, "test", "dispose", lease_seconds=30) as lease:
                    with self.assertRaisesRegex(RuntimeError, stage):
                        dispose_run(
                            plan, registry, lease=lease,
                            operation_id=f"operation-{stage}", failpoint=failpoint,
                        )
                    with self.assertRaisesRegex(ProvenanceError, "being permanently disposed"):
                        registry.resolve(origin)
                    recovered = dispose_run(
                        plan, registry, lease=lease, operation_id=f"operation-{stage}"
                    )
                self.assertEqual(recovered["tombstone"]["kind"], "disposed")
                with self.assertRaises(RunDisposed):
                    sdk.get_run("run")

    def test_plan_and_retry_require_exact_schema_and_tracking_triggers(self):
        sdk = self._create_run("run")
        registry = self._registry()
        registry.register_run(self.store, "run")
        registry.close_scope()
        plan = plan_disposal(self.store, "run", registry)

        def fail_before_commit(name):
            if name == "before_source_commit":
                raise RuntimeError("pause disposal")

        with maintenance_lease(self.store, "test", "dispose", lease_seconds=30) as lease:
            with self.assertRaisesRegex(RuntimeError, "pause"):
                dispose_run(
                    plan, registry, lease=lease, operation_id="operation",
                    failpoint=fail_before_commit,
                )
        self.assertEqual(sdk.get_run("run")["state"], "succeeded")

        with closing(sqlite3.connect(self.store)) as connection:
            connection.execute("DROP TRIGGER sdk_runs_track_delete")
            connection.commit()
        with self.assertRaisesRegex(ProvenanceError, "schema and triggers"):
            plan_disposal(self.store, "run", registry)
        with maintenance_lease(self.store, "test", "retry", lease_seconds=30) as lease:
            with self.assertRaisesRegex(ProvenanceError, "schema and triggers"):
                dispose_run(plan, registry, lease=lease, operation_id="operation")
        self.assertEqual(sdk.get_run("run")["state"], "succeeded")


if __name__ == "__main__":
    unittest.main()
