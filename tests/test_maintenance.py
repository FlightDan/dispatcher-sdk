from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from dispatcher_sdk.maintenance import (
    InvalidLeaseError,
    MaintenanceBusyError,
    MaintenanceMetadataError,
    SnapshotReadOnlyError,
    inspect_maintenance,
    maintenance_lease,
    storage_participant,
)


def _hold_participant(path: str, ready, release) -> None:
    with storage_participant(path):
        ready.put("held")
        release.get(timeout=10)


def _hold_maintenance(path: str, ready, release) -> None:
    with maintenance_lease(path, "child", "test", lease_seconds=10) as lease:
        ready.put((lease.id, lease.fence))
        release.get(timeout=10)


def _try_maintenance(path: str, delay: float, result) -> None:
    time.sleep(delay)
    try:
        with maintenance_lease(path, "contender", "test", lease_seconds=1):
            result.put("acquired")
    except MaintenanceBusyError:
        result.put("busy")


class MaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "store.db"

    def _create_database(self) -> None:
        self.path.write_bytes(b"database placeholder")

    def test_participant_can_lock_before_database_creation_and_is_reentrant(self):
        self.assertFalse(self.path.exists())
        with storage_participant(self.path):
            with storage_participant(self.path):
                self.path.write_bytes(b"created under shared protocol lock")
        self.assertTrue(self.path.exists())

    def test_maintenance_requires_an_existing_database(self):
        with self.assertRaises(FileNotFoundError):
            with maintenance_lease(self.path, "owner", "upgrade"):
                self.fail("missing database must not be leased")

    def test_existing_participant_blocks_maintenance_in_this_process(self):
        self._create_database()
        with storage_participant(self.path):
            with self.assertRaises(MaintenanceBusyError):
                with maintenance_lease(self.path, "owner", "upgrade"):
                    pass

    def test_participant_in_another_process_blocks_maintenance(self):
        self._create_database()
        context = multiprocessing.get_context("spawn")
        ready = context.Queue()
        release = context.Queue()
        process = context.Process(target=_hold_participant, args=(str(self.path), ready, release))
        process.start()
        self.addCleanup(lambda: process.kill() if process.is_alive() else None)
        self.assertEqual(ready.get(timeout=10), "held")
        with self.assertRaises(MaintenanceBusyError):
            with maintenance_lease(self.path, "parent", "upgrade", timeout=0):
                pass
        release.put("done")
        process.join(10)
        self.assertEqual(process.exitcode, 0)

    def test_maintenance_in_another_process_blocks_new_participant(self):
        self._create_database()
        context = multiprocessing.get_context("spawn")
        ready = context.Queue()
        release = context.Queue()
        process = context.Process(target=_hold_maintenance, args=(str(self.path), ready, release))
        process.start()
        self.addCleanup(lambda: process.kill() if process.is_alive() else None)
        lease_id, fence = ready.get(timeout=10)
        self.assertTrue(lease_id)
        self.assertEqual(fence, 1)
        with self.assertRaises(MaintenanceBusyError):
            with storage_participant(self.path):
                pass
        release.put("done")
        process.join(10)
        self.assertEqual(process.exitcode, 0)

    def test_expiry_does_not_let_a_contender_steal_a_held_os_lock(self):
        self._create_database()
        context = multiprocessing.get_context("spawn")
        result = context.Queue()
        with maintenance_lease(self.path, "owner", "slow operation", lease_seconds=0.1) as lease:
            process = context.Process(
                target=_try_maintenance,
                args=(str(self.path), 0.2, result),
            )
            process.start()
            self.addCleanup(lambda: process.kill() if process.is_alive() else None)
            self.assertEqual(result.get(timeout=10), "busy")
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            with self.assertRaises(InvalidLeaseError):
                lease.check(self.path)
        with maintenance_lease(self.path, "next", "next operation") as next_lease:
            self.assertEqual(next_lease.fence, 2)

    def test_lease_check_rejects_wrong_path_and_use_after_context(self):
        self._create_database()
        with maintenance_lease(self.path, "owner", "upgrade") as lease:
            self.assertIs(lease.check(self.path), lease)
            with self.assertRaises(InvalidLeaseError):
                lease.check(self.root / "other.db")
            with self.assertRaises(AttributeError):
                lease.owner = "other"
        with self.assertRaises(InvalidLeaseError):
            lease.check(self.path)

    def test_forked_process_cannot_use_parent_lease(self):
        if "fork" not in multiprocessing.get_all_start_methods():
            self.skipTest("fork is unavailable")
        self._create_database()
        context = multiprocessing.get_context("fork")
        result = context.Queue()
        with maintenance_lease(self.path, "owner", "upgrade") as lease:
            def check_foreign_process() -> None:
                try:
                    lease.check(self.path)
                except InvalidLeaseError:
                    result.put("foreign")
                else:
                    result.put("accepted")

            process = context.Process(target=check_foreign_process)
            process.start()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(result.get(timeout=2), "foreign")
            lease.check(self.path)

    def test_renew_extends_lifetime_and_publishes_observable_state(self):
        self._create_database()
        with maintenance_lease(self.path, "owner", "upgrade", lease_seconds=0.2) as lease:
            original_expiry = lease.expires_at
            original_id = lease.id
            time.sleep(0.02)
            self.assertIs(lease.renew(2), lease)
            self.assertGreater(lease.expires_at, original_expiry)
            lease.check(self.path)
            inspection = inspect_maintenance(self.path)
            self.assertIsNotNone(inspection)
            assert inspection is not None and inspection.lease is not None
            self.assertEqual(inspection.lease.id, original_id)
            self.assertEqual(inspection.lease.expires_at, lease.expires_at)
        with self.assertRaises(InvalidLeaseError):
            lease.renew(1)

    def test_explicit_lease_is_required_for_participation_under_exclusive_lock(self):
        self._create_database()
        with maintenance_lease(self.path, "owner", "upgrade") as lease:
            with self.assertRaises(MaintenanceBusyError):
                with storage_participant(self.path):
                    pass
            with storage_participant(self.path, lease=lease):
                lease.check(self.path)

    def test_inspection_is_read_only_and_fence_survives_release(self):
        self.assertIsNone(inspect_maintenance(self.path))
        self.assertEqual(list(self.root.iterdir()), [])
        self._create_database()
        with maintenance_lease(self.path, "owner", "upgrade") as lease:
            self.assertEqual(lease.fence, 1)
            active = inspect_maintenance(self.path)
            self.assertIsNotNone(active)
            assert active is not None and active.lease is not None
            self.assertEqual(active.lease.owner, "owner")
            self.assertEqual(active.lease.purpose, "upgrade")
        inactive = inspect_maintenance(self.path)
        self.assertIsNotNone(inactive)
        assert inactive is not None
        self.assertEqual(inactive.fence, 1)
        self.assertIsNone(inactive.lease)
        with maintenance_lease(self.path, "owner", "compact") as second:
            self.assertEqual(second.fence, 2)

    def test_concurrent_threads_hold_independent_shared_handles(self):
        self._create_database()
        entered = threading.Event()
        release = threading.Event()

        def participant() -> None:
            with storage_participant(self.path):
                entered.set()
                release.wait(5)

        thread = threading.Thread(target=participant)
        thread.start()
        self.addCleanup(lambda: release.set())
        self.assertTrue(entered.wait(5))
        with storage_participant(self.path):
            with self.assertRaises(MaintenanceBusyError):
                with maintenance_lease(self.path, "owner", "compact"):
                    pass
        release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())

    def test_missing_primary_lock_name_is_reconstructed_from_permanent_anchor(self):
        self._create_database()
        lock_path = Path(str(self.path.resolve()) + ".sdk-lock")
        anchor_path = Path(str(self.path.resolve()) + ".sdk-lock-anchor")
        with storage_participant(self.path):
            original = anchor_path.stat()
            lock_path.unlink()
            self.assertFalse(lock_path.exists())
            with storage_participant(self.path):
                reconstructed = lock_path.stat()
                self.assertEqual(
                    (reconstructed.st_dev, reconstructed.st_ino),
                    (original.st_dev, original.st_ino),
                )
            with self.assertRaises(MaintenanceBusyError):
                with maintenance_lease(self.path, "owner", "upgrade"):
                    pass
        with maintenance_lease(self.path, "owner", "upgrade") as lease:
            lease.check(self.path)

    def test_recreated_primary_lock_is_rejected_while_same_process_holds_old_inode(self):
        self._create_database()
        lock_path = Path(str(self.path.resolve()) + ".sdk-lock")
        with storage_participant(self.path):
            lock_path.unlink()
            lock_path.write_bytes(b"replacement")
            with self.assertRaises(MaintenanceMetadataError):
                with maintenance_lease(self.path, "owner", "upgrade"):
                    pass

    def test_recreated_primary_lock_is_rejected_across_processes(self):
        self._create_database()
        context = multiprocessing.get_context("spawn")
        ready = context.Queue()
        release = context.Queue()
        process = context.Process(target=_hold_participant, args=(str(self.path), ready, release))
        process.start()
        self.addCleanup(lambda: process.kill() if process.is_alive() else None)
        self.assertEqual(ready.get(timeout=10), "held")
        lock_path = Path(str(self.path.resolve()) + ".sdk-lock")
        lock_path.unlink()
        lock_path.write_bytes(b"replacement")
        with self.assertRaises(MaintenanceMetadataError):
            with maintenance_lease(self.path, "owner", "upgrade"):
                pass
        release.put("done")
        process.join(10)
        self.assertEqual(process.exitcode, 0)

    def test_lease_check_rejects_replaced_lock_name(self):
        self._create_database()
        lock_path = Path(str(self.path.resolve()) + ".sdk-lock")
        with maintenance_lease(self.path, "owner", "upgrade") as lease:
            lock_path.unlink()
            lock_path.write_bytes(b"replacement")
            with self.assertRaises(InvalidLeaseError):
                lease.check(self.path)

    def test_snapshot_marker_denies_maintenance_without_creating_coordination_files(self):
        self._create_database()
        marker = self.root / ".sdk-snapshot-readonly"
        marker.write_text("explicit activation required")
        with self.assertRaises(SnapshotReadOnlyError):
            with maintenance_lease(self.path, "owner", "dispose"):
                pass
        self.assertFalse(Path(str(self.path.resolve()) + ".sdk-lock").exists())
        self.assertFalse(Path(str(self.path.resolve()) + ".sdk-lock-anchor").exists())
        self.assertFalse(Path(str(self.path.resolve()) + ".sdk-maintenance.json").exists())

    def test_dangling_snapshot_marker_symlink_fails_closed(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are unavailable")
        self._create_database()
        marker = self.root / ".sdk-snapshot-readonly"
        try:
            marker.symlink_to(self.root / "missing-marker-target")
        except OSError as error:
            self.skipTest(f"cannot create symlink: {error}")
        self.assertFalse(marker.exists())
        with self.assertRaises(SnapshotReadOnlyError):
            with maintenance_lease(self.path, "owner", "retention"):
                pass

    def test_marker_created_during_lease_invalidates_new_destructive_phases(self):
        self._create_database()
        with maintenance_lease(self.path, "owner", "upgrade") as lease:
            (self.root / ".sdk-snapshot-readonly").write_text("activation required")
            with self.assertRaises(SnapshotReadOnlyError):
                lease.check(self.path)
            with self.assertRaises(MaintenanceBusyError):
                with storage_participant(self.path):
                    pass

    def test_symlink_sidecars_are_rejected_and_not_followed(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are unavailable")
        self._create_database()
        victim = self.root / "victim"
        victim.write_text("preserve")
        lock_path = Path(str(self.path.resolve()) + ".sdk-lock")
        try:
            lock_path.symlink_to(victim)
        except OSError as error:
            self.skipTest(f"cannot create symlink: {error}")
        with self.assertRaises(MaintenanceMetadataError):
            with storage_participant(self.path):
                pass
        self.assertEqual(victim.read_text(), "preserve")
        lock_path.unlink()
        metadata_path = Path(str(self.path.resolve()) + ".sdk-maintenance.json")
        metadata_path.symlink_to(victim)
        with self.assertRaises(MaintenanceMetadataError):
            inspect_maintenance(self.path)
        with self.assertRaises(MaintenanceMetadataError):
            with maintenance_lease(self.path, "owner", "upgrade"):
                pass
        self.assertEqual(victim.read_text(), "preserve")

    def test_corrupt_metadata_fails_closed_without_losing_fence(self):
        self._create_database()
        metadata_path = Path(str(self.path.resolve()) + ".sdk-maintenance.json")
        metadata_path.write_text(json.dumps({
            "version": 1,
            "path": str(self.path.resolve()),
            "fence": "bad",
            "lease": None,
        }))
        before = metadata_path.read_bytes()
        with self.assertRaises(MaintenanceMetadataError):
            inspect_maintenance(self.path)
        with self.assertRaises(MaintenanceMetadataError):
            with maintenance_lease(self.path, "owner", "upgrade"):
                pass
        self.assertEqual(metadata_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
