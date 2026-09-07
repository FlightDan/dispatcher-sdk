from contextlib import closing
import base64
import csv
import hashlib
from importlib import metadata
import json
from pathlib import Path
import sqlite3
import shutil
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Runtime, SandboxJournal, SandboxSpec
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.orchestrator import Operations, Orchestrator, NotificationInbox
from dispatcher_sdk.identity import runtime_identity


def echo(payload, context):
    return payload


def other(payload, context):
    return {"other": payload}


class RuntimeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "runtime.db"

    def test_missing_is_not_readable_and_not_created(self):
        result = runtime_identity(self.path, handlers={})
        self.assertEqual(result.storages[0].status, "missing")
        self.assertEqual(result.read.status, "unsupported")
        self.assertEqual(result.resume.status, "unsupported")
        self.assertFalse(self.path.exists())
        self.assertEqual(runtime_identity().read.status, "not_checked")
        json.dumps(result.to_dict())

    def test_current_storage_bindings_and_read_only_contents(self):
        with Runtime(self.path, {"echo": echo}, isolation_mode="thread") as runtime:
            sdk = Orchestrator(self.path, runtime.kernel)
            sdk.create_run("run", command_id="create")
            command = runtime.command("echo", execution_id="x", idempotency_key="x",
                correlation_id="r", timeout_seconds=1, payload="hello")
            sdk.apply_operations("run", command_id="add", expected_revision=0,
                operations=[Operations.add_task("task", command)])
            with closing(sqlite3.connect(self.path)) as connection:
                before = list(connection.iterdump())
            unknown = runtime_identity(self.path)
            good = runtime_identity(self.path, handlers={"echo": echo}, durability="full")
            bad = runtime_identity(self.path, handlers={"echo": other})
            with closing(sqlite3.connect(self.path)) as connection:
                self.assertEqual(before, list(connection.iterdump()))
            self.assertEqual(unknown.read.status, "supported")
            self.assertEqual(unknown.resume.status, "unknown")
            self.assertEqual(unknown.storages[0].bindings, "not_checked")
            self.assertEqual(good.resume.status, "supported")
            self.assertEqual(bad.read.status, "supported")
            self.assertEqual(bad.resume.status, "unsupported")
            self.assertNotEqual(good.handler_bindings, bad.handler_bindings)
            self.assertEqual(bad.storages[0].facts["binding_mismatch_count"], 1)
            durability = good.storages[0].durability
            self.assertEqual(durability.configured, "full")
            self.assertEqual(durability.other_connections_synchronous, "unknown")
            self.assertEqual(durability.hardware_guarantee, "not_checked")

    def test_old_terminal_rows_only_receive_catalog_summary(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_runs(run_id TEXT, state TEXT)")
            connection.execute("INSERT INTO sdk_runs VALUES('old', 'succeeded')")
        before = self.path.read_bytes()
        result = runtime_identity(self.path, handlers={})
        storage = result.storages[0]
        self.assertEqual(storage.status, "unsupported")
        self.assertEqual(storage.summary.status, "supported")
        self.assertEqual(storage.summary.reasons, ("sqlite_catalog_only",))
        self.assertIn("sdk_runs", storage.table_names)
        self.assertEqual(result.read.status, "unsupported")
        self.assertEqual(result.execute.status, "unsupported")
        self.assertEqual(result.resume.status, "unsupported")
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaises(ValueError):
            with Runtime(self.path, {}, isolation_mode="thread") as runtime:
                Orchestrator(self.path, runtime.kernel)

    def test_unknown_active_kernel_schema_rejected_without_write(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE kernel_executions(state TEXT)")
            connection.execute("INSERT INTO kernel_executions VALUES('running')")
        before = self.path.read_bytes()
        result = runtime_identity(self.path, handlers={})
        self.assertEqual(result.execute.status, "unsupported")
        with self.assertRaises(StorageIsolationError):
            Runtime(self.path, {}, isolation_mode="thread")
        self.assertEqual(before, self.path.read_bytes())

    def test_corruption_and_unreadable_do_not_escape_or_claim_success(self):
        self.path.write_bytes(b"not a SQLite database")
        before = self.path.read_bytes()
        result = runtime_identity(self.path)
        self.assertEqual(result.storages[0].status, "damaged")
        self.assertEqual(result.read.status, "unsupported")
        self.assertEqual(before, self.path.read_bytes())
        with patch("dispatcher_sdk.identity.inspect_storage", side_effect=PermissionError("denied")):
            result = runtime_identity(self.path)
        self.assertEqual(result.read.status, "unknown")
        self.assertEqual(result.storages[0].integrity, "unknown")

    def test_sqlite_errors_without_result_codes_are_classified_conservatively(self):
        for message, damaged in (
            ("file is not a database", True),
            ("database disk image is malformed", True),
            ("database is locked", False),
            ("unable to open database file", False),
            ("disk I/O error", False),
            ("attempt to write a readonly database", False),
            ("unrecognized database failure", False),
        ):
            with self.subTest(message=message):
                # Manually created exceptions also lack codes on newer Python.
                error = sqlite3.DatabaseError(message)
                self.assertFalse(hasattr(error, "sqlite_errorcode"))
                with patch("dispatcher_sdk.identity.inspect_storage", side_effect=error):
                    storage = runtime_identity(self.path).storages[0]
                self.assertEqual(storage.status, "damaged" if damaged else "unknown")
                self.assertEqual(storage.integrity, "failed" if damaged else "unknown")
                for verdict in (storage.read, storage.execute, storage.resume):
                    self.assertEqual(verdict.status, "unsupported" if damaged else "unknown")

    def test_sqlite_result_codes_take_precedence_over_messages(self):
        for code, message, damaged in (
            (11, "corruption", True),
            (26, "not a database", True),
            (11 | (1 << 8), "extended corruption result", True),
            (5, "file is not a database", False),
            (10, "database disk image is malformed", False),
        ):
            with self.subTest(code=code):
                error = sqlite3.DatabaseError(message)
                error.sqlite_errorcode = code
                with patch("dispatcher_sdk.identity.inspect_storage", side_effect=error):
                    storage = runtime_identity(self.path).storages[0]
                self.assertEqual(storage.status, "damaged" if damaged else "unknown")

    def test_distribution_does_not_identify_imported_source(self):
        class Distribution:
            version = "0.5.1"
            files = None
        with patch("dispatcher_sdk.identity.metadata.distribution", return_value=Distribution()):
            result = runtime_identity()
        self.assertEqual(result.module.distribution_version, "0.5.1")
        self.assertEqual(result.module.source_version, "0.6.0")
        self.assertEqual(result.module.version_agreement, "mismatch")
        self.assertEqual(len(result.module.source_sha256), 64)
        self.assertEqual(result.module.distribution_record, "unknown")
        self.assertEqual(result.resume.status, "unsupported")
        self.assertIn("distribution_source_version_mismatch", result.resume.reasons)
        with patch("dispatcher_sdk.identity._version.SOURCE_VERSION", None):
            self.assertEqual(runtime_identity().module.version_agreement, "unknown")

    def test_wheel_record_evidence_and_source_overlay(self):
        import dispatcher_sdk
        source = Path(dispatcher_sdk.__file__).parent
        dist_info = self.path.parent / "dispatcher_sdk-0.5.1.dist-info"
        dist_info.mkdir()
        shutil.copytree(source, self.path.parent / "dispatcher_sdk")
        (dist_info / "METADATA").write_text("Metadata-Version: 2.1\nName: dispatcher-sdk\nVersion: 0.5.1\n")
        with (dist_info / "RECORD").open("w", newline="") as stream:
            writer = csv.writer(stream)
            for path in source.rglob("*.py"):
                content = path.read_bytes()
                digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
                writer.writerow(["dispatcher_sdk/" + path.relative_to(source).as_posix(), "sha256=" + digest, len(content)])
        distribution = metadata.PathDistribution(dist_info)
        with patch("dispatcher_sdk.identity.metadata.distribution", return_value=distribution):
            result = runtime_identity().module
            self.assertEqual(result.distribution_record, "verified")
            self.assertEqual(result.version_agreement, "mismatch")
            original_read = Path.read_bytes
            def overlay(path):
                content = original_read(path)
                return content + b"\n# overlay\n" if path.name == "identity.py" else content
            with patch.object(Path, "read_bytes", overlay):
                changed = runtime_identity().module
            self.assertEqual(changed.distribution_record, "mismatch")
            self.assertNotEqual(result.source_sha256, changed.source_sha256)

    def test_source_hash_distinguishes_same_version_edits(self):
        original = runtime_identity().module
        original_read = Path.read_bytes
        def changed(path):
            content = original_read(path)
            return content + b"\n# source overlay\n" if path.name == "identity.py" else content
        with patch.object(Path, "read_bytes", changed):
            overlay = runtime_identity().module
        self.assertEqual(original.source_version, overlay.source_version)
        self.assertNotEqual(original.source_sha256, overlay.source_sha256)

    def test_auxiliary_sandbox_with_pending_cleanup_does_not_certify_resume(self):
        journal = SandboxJournal(str(self.path))
        spec = SandboxSpec("fixture-image", "print('hello')", ("/usr/bin/python3",), "/tmp")
        journal._begin("execution", "effect", "unavailable-backend", "old-v1",
            "sdk.sandbox.missing", 1, spec)
        with closing(sqlite3.connect(self.path)) as connection:
            before = list(connection.iterdump())
        report = runtime_identity(self.path, handlers={})
        storage = report.storages[0]
        self.assertEqual(storage.schemas["sandbox"], 1)
        self.assertEqual(storage.read.status, "supported")
        self.assertEqual(storage.execute.status, "not_applicable")
        self.assertEqual(storage.resume.status, "unknown")
        self.assertEqual(storage.bindings, "not_checked")
        self.assertEqual(report.resume.status, "unknown")
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(before, list(connection.iterdump()))
            self.assertEqual(connection.execute("SELECT cleanup_confirmed FROM sandbox_operations").fetchone()[0], 0)

    def test_inbox_schema_does_not_certify_execution_or_recovery(self):
        NotificationInbox(self.path)
        report = runtime_identity(self.path, handlers={})
        self.assertEqual(report.read.status, "supported")
        self.assertEqual(report.execute.status, "not_applicable")
        self.assertEqual(report.resume.status, "unknown")
        self.assertEqual(report.storages[0].bindings, "not_checked")

    def test_independent_missing_component_blocks_aggregate(self):
        with Runtime(self.path, {}, isolation_mode="thread"):
            pass
        missing = self.path.parent / "missing-inbox.db"
        result = runtime_identity(self.path, handlers={}, component_paths={"inbox": missing})
        self.assertEqual(result.storages[0].read.status, "supported")
        self.assertEqual(result.read.status, "unsupported")
        self.assertIn("independent", result.snapshot_scope)
        self.assertFalse(missing.exists())

    def test_unsupported_orchestrator_writer_does_not_change_journal_mode(self):
        with Runtime(self.path.parent / "kernel.db", {}, isolation_mode="thread") as runtime:
            with closing(sqlite3.connect(self.path)) as connection, connection:
                connection.execute("CREATE TABLE sdk_runs(run_id TEXT,state TEXT)")
                connection.execute("INSERT INTO sdk_runs VALUES('old','running')")
            before = self.path.read_bytes()
            with self.assertRaises(ValueError):
                Orchestrator(self.path, runtime.kernel)
            self.assertEqual(before, self.path.read_bytes())

    def test_explicit_cancellation_journal_is_readable_auxiliary_storage(self):
        journal = self.path.parent / "cancel.db"
        with Runtime(self.path, {}, isolation_mode="thread", cancellation_journal_path=str(journal),
                     source_id="tests"):
            report = runtime_identity(journal, handlers={})
        self.assertEqual(report.storages[0].schemas["cancellation"], 1)
        self.assertEqual(report.storages[0].execute.status, "not_applicable")
        self.assertEqual(report.storages[0].resume.status, "unknown")

    def test_same_file_factory_rejects_old_run_before_kernel_initialization(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_runs(run_id TEXT,state TEXT)")
            connection.execute("INSERT INTO sdk_runs VALUES('old','running')")
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            Orchestrator.open_sqlite(self.path, {}, isolation_mode="thread")
        self.assertEqual(before, self.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
