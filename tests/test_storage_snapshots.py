from __future__ import annotations

from collections import namedtuple
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from dispatcher_sdk.maintenance import MaintenanceBusyError, storage_participant
from dispatcher_sdk import storage_snapshots as snapshots
from dispatcher_sdk.storage_snapshots import (
    SnapshotSpaceError,
    SnapshotValidationError,
    StoreGroupDescriptor,
    restore_snapshot,
    snapshot_store_group,
    verify_snapshot,
)


class StorageSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.first = self.root / "orchestrator.db"
        self.second = self.root / "kernel.db"
        self.blob = self.root / "input.bin"
        self.key = b"deployment-managed-test-key-32-bytes-minimum"
        self._database(self.first, "orchestrator", 3)
        self._database(self.second, "kernel", 5)
        self.blob.write_bytes(b"immutable input\x00payload")

    def _database(self, path: Path, identity: str, sequence: int) -> None:
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE component_meta(version INTEGER, store_id TEXT)")
            connection.execute("INSERT INTO component_meta VALUES(?, ?)", (1, identity))
            connection.execute("CREATE TABLE events(sequence INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO events VALUES(?, ?)", (sequence, f"value-{sequence}"))

    def _group(self) -> StoreGroupDescriptor:
        return StoreGroupDescriptor(
            {"orchestrator": self.first, "kernel": self.second},
            {"immutable-input": self.blob},
            group_id="test-group",
        )

    def _snapshot(self, name: str = "snapshot") -> Path:
        return snapshot_store_group(
            self._group(), self.root / name,
            signing_key=self.key, owner_id="test-suite",
        )

    def test_snapshot_backs_up_closed_group_and_authenticates_manifest(self):
        first_before = self.first.read_bytes()
        second_before = self.second.read_bytes()
        blob_before = self.blob.read_bytes()
        manifest_path = self._snapshot()
        self.assertEqual(manifest_path, self.root / "snapshot" / "manifest.json")
        verified = verify_snapshot(manifest_path, self.key)
        self.assertEqual(verified.group_id, "test-group")
        self.assertTrue(verified.requires_explicit_activation)
        self.assertEqual(set(verified.components), {"orchestrator", "kernel"})
        self.assertEqual(set(verified.blobs), {"immutable-input"})
        self.assertEqual(verified.blobs["immutable-input"].read_bytes(), blob_before)
        for name, expected in (("orchestrator", 3), ("kernel", 5)):
            with closing(sqlite3.connect(verified.components[name])) as connection:
                self.assertEqual(connection.execute("SELECT MAX(sequence) FROM events").fetchone()[0], expected)
        self.assertEqual(self.first.read_bytes(), first_before)
        self.assertEqual(self.second.read_bytes(), second_before)
        self.assertEqual(self.blob.read_bytes(), blob_before)
        document = json.loads(manifest_path.read_text())
        self.assertEqual(document["authentication"]["algorithm"], "HMAC-SHA256")
        self.assertFalse(document["activation"]["activation_api_available"])
        self.assertTrue((manifest_path.parent / ".sdk-snapshot-readonly").is_file())

    def test_online_backup_includes_committed_wal_content(self):
        connection = sqlite3.connect(self.first)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute("INSERT INTO events VALUES(10, 'committed in WAL')")
            connection.commit()
            self.assertTrue(Path(str(self.first) + "-wal").exists())
            verified = verify_snapshot(self._snapshot("wal-snapshot"), self.key)
            with closing(sqlite3.connect(verified.components["orchestrator"])) as copy:
                self.assertEqual(copy.execute("SELECT value FROM events WHERE sequence=10").fetchone()[0],
                                 "committed in WAL")
        finally:
            connection.close()

    def test_descriptor_rejects_aliases_traversal_and_symlinks(self):
        alias = self.root / "alias.db"
        os.link(self.first, alias)
        with self.assertRaises(SnapshotValidationError):
            StoreGroupDescriptor({"one": self.first, "two": alias})
        with self.assertRaises(SnapshotValidationError):
            StoreGroupDescriptor({"bad/name": self.first})
        with self.assertRaises(SnapshotValidationError):
            StoreGroupDescriptor({"one": self.root / "folder" / ".." / self.first.name})
        symlink = self.root / "database-link"
        try:
            symlink.symlink_to(self.first)
        except OSError as error:
            self.skipTest(f"cannot create symlink: {error}")
        with self.assertRaises(SnapshotValidationError):
            StoreGroupDescriptor({"one": symlink})

    def test_existing_destination_is_never_overwritten_even_when_empty(self):
        destination = self.root / "existing"
        destination.mkdir()
        with self.assertRaises(FileExistsError):
            snapshot_store_group(
                self._group(), destination, signing_key=self.key, owner_id="test"
            )
        manifest = self._snapshot()
        restored = self.root / "restored-existing"
        restored.mkdir()
        with self.assertRaises(FileExistsError):
            restore_snapshot(manifest, restored, self.key)

    def test_registered_live_participant_blocks_snapshot(self):
        destination = self.root / "blocked"
        with storage_participant(self.first):
            with self.assertRaises(MaintenanceBusyError):
                snapshot_store_group(
                    self._group(), destination,
                    signing_key=self.key, owner_id="test", lease_seconds=10,
                )
        self.assertFalse(destination.exists())

    def test_expired_lease_prevents_manifest_publication(self):
        destination = self.root / "expired"
        original = snapshots._backup_sqlite

        def slow_backup(source: Path, output: Path) -> None:
            original(source, output)
            time.sleep(0.08)

        with mock.patch.object(snapshots, "_backup_sqlite", side_effect=slow_backup):
            with self.assertRaises(Exception) as raised:
                snapshot_store_group(
                    self._group(), destination,
                    signing_key=self.key, owner_id="test", lease_seconds=0.05,
                )
        self.assertIn("expired", str(raised.exception))
        self.assertFalse(destination.exists())

    def test_fault_before_publish_leaves_no_valid_snapshot(self):
        destination = self.root / "failed"

        def fail(name: str) -> None:
            if name == "snapshot.before_manifest_publish":
                raise RuntimeError("injected failure")

        with mock.patch.object(snapshots, "_failpoint", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                snapshot_store_group(
                    self._group(), destination, signing_key=self.key, owner_id="test"
                )
        self.assertFalse(destination.exists())

    def test_verify_rejects_wrong_key_and_tampered_manifest_before_paths(self):
        manifest = self._snapshot()
        with self.assertRaises(SnapshotValidationError):
            verify_snapshot(manifest, b"x" * 32)
        document = json.loads(manifest.read_text())
        document["members"][0]["path"] = "../../outside"
        manifest.write_text(json.dumps(document))
        with self.assertRaisesRegex(SnapshotValidationError, "authentication"):
            verify_snapshot(manifest, self.key)

    def test_verify_rejects_tampered_missing_extra_and_symlink_members(self):
        manifest = self._snapshot("payload-tamper")
        verified = verify_snapshot(manifest, self.key)
        verified.blobs["immutable-input"].write_bytes(b"changed")
        with self.assertRaisesRegex(SnapshotValidationError, "digest mismatch"):
            verify_snapshot(manifest, self.key)

        manifest = self._snapshot("extra")
        (manifest.parent / "unregistered").write_text("extra")
        with self.assertRaisesRegex(SnapshotValidationError, "closed set"):
            verify_snapshot(manifest, self.key)

        manifest = self._snapshot("missing")
        verified = verify_snapshot(manifest, self.key)
        verified.blobs["immutable-input"].unlink()
        with self.assertRaises((FileNotFoundError, SnapshotValidationError)):
            verify_snapshot(manifest, self.key)

        manifest = self._snapshot("symlink")
        verified = verify_snapshot(manifest, self.key)
        blob_path = verified.blobs["immutable-input"]
        blob_path.unlink()
        blob_path.symlink_to(self.blob)
        with self.assertRaises(SnapshotValidationError):
            verify_snapshot(manifest, self.key)

    def test_validly_authenticated_path_traversal_is_still_rejected(self):
        manifest = self._snapshot()
        document = json.loads(manifest.read_text())
        document["members"][0]["path"] = "../escape"
        snapshots._authenticate(document, self.key)
        manifest.write_bytes(snapshots._canonical(document) + b"\n")
        with self.assertRaisesRegex(SnapshotValidationError, "unsafe path"):
            verify_snapshot(manifest, self.key)

    def test_restore_copies_only_verified_set_and_keeps_activation_gate(self):
        manifest = self._snapshot()
        result = restore_snapshot(manifest.parent, self.root / "restored", self.key)
        self.assertTrue(result.requires_explicit_activation)
        self.assertEqual(result.manifest_path, result.path / "manifest.json")
        restored = verify_snapshot(result.path, self.key)
        self.assertTrue((result.path / ".sdk-snapshot-readonly").is_file())
        self.assertEqual(restored.blobs["immutable-input"].read_bytes(), self.blob.read_bytes())
        original_files = {
            path.relative_to(manifest.parent).as_posix()
            for path in manifest.parent.rglob("*") if path.is_file()
        }
        restored_files = {
            path.relative_to(result.path).as_posix()
            for path in result.path.rglob("*") if path.is_file()
        }
        self.assertEqual(restored_files, original_files)

    def test_restore_fault_cleans_only_its_new_directory(self):
        manifest = self._snapshot()
        destination = self.root / "restore-failed"

        def fail(name: str) -> None:
            if name.startswith("restore.after_member"):
                raise RuntimeError("restore failure")

        with mock.patch.object(snapshots, "_failpoint", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "restore failure"):
                restore_snapshot(manifest, destination, self.key)
        self.assertFalse(destination.exists())
        verify_snapshot(manifest, self.key)

    def test_disk_preflight_refuses_before_creating_destination(self):
        usage = namedtuple("usage", "total used free")(100, 99, 1)
        destination = self.root / "no-space"
        with mock.patch.object(snapshots.shutil, "disk_usage", return_value=usage):
            with self.assertRaises(SnapshotSpaceError):
                snapshot_store_group(
                    self._group(), destination, signing_key=self.key, owner_id="test"
                )
        self.assertFalse(destination.exists())

    def test_signing_key_must_be_deployment_supplied_and_strong(self):
        with self.assertRaises(SnapshotValidationError):
            snapshot_store_group(
                self._group(), self.root / "weak", signing_key=b"short", owner_id="test"
            )
        self.assertFalse((self.root / "weak").exists())


if __name__ == "__main__":
    unittest.main()
