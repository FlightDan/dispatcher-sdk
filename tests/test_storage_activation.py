from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from dispatcher_sdk.execution_kernel import (
    ExecutionCommandV2,
    RetryPolicy,
    Runtime,
    SQLiteKernel,
    registry_revision,
)
from dispatcher_sdk.maintenance import (
    MaintenanceBusyError,
    StorageRetiredError,
    maintenance_lease,
)
from dispatcher_sdk.storage_activation import (
    ActivationConflictError,
    ActivationPreconditionError,
    activate_restored_snapshot,
)
from dispatcher_sdk import storage_activation as activation
from dispatcher_sdk.storage_snapshots import (
    SnapshotValidationError,
    StoreGroupDescriptor,
    restore_snapshot,
    snapshot_store_group,
    verify_snapshot,
)
from dispatcher_sdk import storage_snapshots as snapshots


def echo(payload, context):
    return {"echo": payload["value"]}


def changed_echo(payload, context):
    return {"changed": payload["value"]}


def command(identity: str, *, attempts: int = 3) -> ExecutionCommandV2:
    return ExecutionCommandV2(
        execution_id=identity,
        idempotency_key=f"key-{identity}",
        registry_revision=registry_revision({"echo": echo}),
        correlation_id=identity,
        causation_id=None,
        handler_id="echo",
        handler_contract_version=1,
        retry_policy=RetryPolicy(
            max_attempts=attempts,
            initial_backoff_seconds=0,
            backoff_multiplier=1,
            max_backoff_seconds=0,
        ),
        timeout_seconds=5,
        payload={"value": identity},
    )


class StorageActivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.sqlite3"
        self.snapshot = self.root / "snapshot"
        self.restored = self.root / "restored"
        self.destination = self.root / "active"
        self.key = b"local-activation-test-signing-key-32-bytes"

    def _seed(self, identity: str = "queued") -> None:
        with SQLiteKernel(self.source) as kernel:
            kernel.submit(command(identity))

    def _restore(self) -> None:
        snapshot_store_group(
            StoreGroupDescriptor({"kernel": self.source}, group_id="runtime"),
            self.snapshot,
            signing_key=self.key,
            owner_id="tests",
        )
        restore_snapshot(self.snapshot, self.restored, self.key)

    def _activate(self, *, operation_id: str = "restore-1", handlers=None):
        return activate_restored_snapshot(
            self.restored,
            self.destination,
            signing_key=self.key,
            operation_id=operation_id,
            handlers={"echo": echo} if handlers is None else handlers,
            owner_id="tests",
        )

    def test_active_old_instance_refuses_handoff(self):
        self._seed()
        self._restore()
        old = SQLiteKernel(self.source)
        self.addCleanup(old.close)
        with self.assertRaises(MaintenanceBusyError):
            self._activate()
        self.assertFalse(self.destination.exists())

    def test_activation_retires_source_is_idempotent_and_queued_work_continues(self):
        self._seed()
        self._restore()
        first = self._activate()
        second = self._activate()
        self.assertEqual(first.receipt_path, second.receipt_path)
        with self.assertRaises(StorageRetiredError):
            SQLiteKernel(self.source)
        with self.assertRaises(StorageRetiredError):
            with maintenance_lease(self.source, "tests", "should-not-reopen"):
                pass
        with Runtime(first.components["kernel"], {"echo": echo}, isolation_mode="thread") as runtime:
            result = runtime.run_once()
            self.assertEqual(result.state, "succeeded")
            self.assertEqual(result.result.value, {"echo": "queued"})
        # Idempotency authenticates the handoff identity; the live successor is
        # expected to have changed after normal execution.
        third = self._activate()
        self.assertEqual(third.receipt_path, first.receipt_path)
        with self.assertRaises(StorageRetiredError):
            activate_restored_snapshot(
                self.restored,
                self.root / "other-active",
                signing_key=self.key,
                operation_id="restore-2",
                handlers={"echo": echo},
                owner_id="tests",
            )

    def test_retry_resumes_after_sources_were_retired_but_receipt_was_not_published(self):
        self._seed()
        self._restore()
        with mock.patch.object(activation, "_replace", side_effect=RuntimeError("crash")):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                self._activate()
        self.assertTrue((self.destination / ".sdk-snapshot-readonly").is_file())
        with self.assertRaises(StorageRetiredError):
            SQLiteKernel(self.source)
        result = self._activate()
        self.assertTrue(result.receipt_path.is_file())
        self.assertFalse((self.destination / ".sdk-snapshot-readonly").exists())

    def test_unrelated_destination_is_rejected_before_source_retirement(self):
        self._seed()
        self._restore()
        self.destination.mkdir()
        (self.destination / "user-data").write_text("keep", encoding="utf-8")
        with self.assertRaises(ActivationConflictError):
            self._activate()
        self.assertFalse(Path(str(self.source) + ".sdk-retired.json").exists())
        self.assertEqual((self.destination / "user-data").read_text(encoding="utf-8"), "keep")

    def test_retry_recovers_mkdir_before_pending_publication(self):
        self._seed()
        self._restore()
        with mock.patch.object(activation, "_initialize_directory", side_effect=RuntimeError("crash after mkdir")):
            with self.assertRaisesRegex(RuntimeError, "crash after mkdir"):
                self._activate()
        self.assertEqual(list(self.destination.iterdir()), [])
        result = self._activate()
        with SQLiteKernel(result.components["kernel"]) as kernel:
            self.assertEqual(kernel.get("queued").state, "queued")

    def test_lost_committed_successor_is_never_rebuilt_from_old_snapshot(self):
        self._seed()
        self._restore()
        activated = self._activate()
        with Runtime(activated.components["kernel"], {"echo": echo}, isolation_mode="thread") as runtime:
            runtime.run_once()
        shutil.rmtree(self.destination)
        with self.assertRaises(ActivationConflictError):
            self._activate()
        self.assertFalse(self.destination.exists())

    def test_lost_reservation_after_retirement_fails_closed(self):
        self._seed()
        self._restore()
        self._activate()
        shutil.rmtree(self.destination)
        activation._reservation_path(self.destination).unlink()
        with self.assertRaisesRegex(ActivationConflictError, "lost its activation reservation"):
            self._activate()

    def test_gated_receipt_retry_revalidates_component_bytes(self):
        self._seed()
        self._restore()
        original = activation._replace

        def crash_before_parent_commit(path, payload):
            if path == activation._reservation_path(self.destination):
                raise RuntimeError("crash before commit")
            return original(path, payload)

        with mock.patch.object(activation, "_replace", side_effect=crash_before_parent_commit):
            with self.assertRaisesRegex(RuntimeError, "crash before commit"):
                self._activate()
        document = json.loads((self.destination / ".sdk-activation.json").read_text())
        component = self.destination / document["components"]["kernel"]
        original_bytes = component.read_bytes()
        component.write_bytes(b"damaged")
        with self.assertRaisesRegex(ActivationConflictError, "gated activation component"):
            self._activate()
        self.assertTrue((self.destination / ".sdk-snapshot-readonly").exists())
        component.write_bytes(original_bytes)
        self._activate()
        self.assertFalse((self.destination / ".sdk-snapshot-readonly").exists())

    def test_hard_link_alias_cannot_keep_old_sdk_writer_alive(self):
        self._seed()
        self._restore()
        alias = self.root / "alias.sqlite3"
        os.link(self.source, alias)
        with SQLiteKernel(alias):
            with self.assertRaisesRegex(ActivationPreconditionError, "hard-link"):
                self._activate()
        self.assertFalse(Path(str(self.source) + ".sdk-retired.json").exists())

    @unittest.skipIf(os.name == "nt", "symlink creation can require Windows privileges")
    def test_destination_replaced_by_symlink_after_reservation_is_rejected(self):
        self._seed()
        self._restore()
        redirected = self.root / "redirected"
        redirected.mkdir()
        reserve = activation._reserve_destination

        def replace_destination(destination, pending, key):
            reserve(destination, pending, key)
            destination.symlink_to(redirected, target_is_directory=True)

        with mock.patch.object(activation, "_reserve_destination", side_effect=replace_destination):
            with self.assertRaisesRegex(ActivationConflictError, "became unsafe"):
                self._activate()
        self.assertEqual(list(redirected.iterdir()), [])

    def test_tamper_and_deployment_mismatch_are_rejected_before_retirement(self):
        self._seed()
        self._restore()
        verified = verify_snapshot(self.restored, self.key)
        verified.components["kernel"].write_bytes(b"tampered")
        with self.assertRaises(SnapshotValidationError):
            self._activate()
        self.assertFalse(Path(str(self.source) + ".sdk-retired.json").exists())

        # A fresh authenticated restore reaches deployment preflight.
        self.restored = self.root / "restored-again"
        restore_snapshot(self.snapshot, self.restored, self.key)
        with self.assertRaises(ActivationPreconditionError):
            self._activate(handlers={"echo": changed_echo})
        self.assertFalse(Path(str(self.source) + ".sdk-retired.json").exists())

    def test_source_change_after_snapshot_is_rejected(self):
        self._seed()
        self._restore()
        with SQLiteKernel(self.source) as kernel:
            kernel.submit(command("later"))
        with self.assertRaisesRegex(ActivationPreconditionError, "changed after"):
            self._activate()
        self.assertFalse(self.destination.exists())

    def test_performing_effect_becomes_indeterminate_after_activation_reap(self):
        with SQLiteKernel(self.source, now=lambda: 1.0) as kernel:
            kernel.submit(command("effect"))
            lease = kernel.claim("old", registry_revision=registry_revision({"echo": echo}))
            self.assertIsNotNone(lease)
            running = kernel.start(lease)
            prepared = kernel.prepare_effect(
                running, effect_id="charge", name="charge", request={"amount": 10}
            )
            kernel.claim_effect(running, prepared.effect_id)
        self._restore()
        result = self._activate()
        with SQLiteKernel(result.components["kernel"]) as recovered:
            changed = recovered.reap()
            self.assertEqual(changed[0].state, "recovery_required")
            effect = recovered.get_effect("charge")
            self.assertEqual(effect.state, "indeterminate")
            self.assertIsNone(effect.recovery_decision)

    def test_blob_or_incomplete_component_group_is_not_activated(self):
        self._seed()
        blob = self.root / "external.bin"
        blob.write_bytes(b"external")
        snapshot = self.root / "blob-snapshot"
        restored = self.root / "blob-restored"
        snapshot_store_group(
            StoreGroupDescriptor({"kernel": self.source}, {"external": blob}),
            snapshot,
            signing_key=self.key,
            owner_id="tests",
        )
        restore_snapshot(snapshot, restored, self.key)
        with self.assertRaisesRegex(ActivationPreconditionError, "external resource"):
            activate_restored_snapshot(
                restored,
                self.destination,
                signing_key=self.key,
                operation_id="blob-restore",
                handlers={"echo": echo},
                owner_id="tests",
            )

    def test_authenticated_manifest_source_path_tamper_is_rejected(self):
        self._seed()
        self._restore()
        manifest = self.restored / "manifest.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["activation"]["source_components"]["kernel"] = str(self.root / "other.db")
        manifest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(SnapshotValidationError):
            self._activate()

    def test_pre_activation_v1_snapshot_remains_verifiable_but_not_activatable(self):
        self._seed()
        self._restore()
        manifest = self.restored / "manifest.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["activation"].pop("source_components")
        document["activation"].pop("copy_activation_api_available")
        for member in document["members"]:
            if member["kind"] == "sqlite":
                member["sqlite"].pop("logical_sha256")
        snapshots._authenticate(document, self.key)
        manifest.write_bytes(snapshots._canonical(document) + b"\n")
        verify_snapshot(manifest, self.key)
        with self.assertRaisesRegex(ActivationPreconditionError, "predates"):
            self._activate()


if __name__ == "__main__":
    unittest.main()
