from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from dispatcher_sdk.storage_usage import inspect_storage_usage


class StorageUsageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_missing_database_is_reported_without_creation(self):
        path = self.root / "missing.sqlite3"
        report = inspect_storage_usage(path, detail="logical")
        self.assertFalse(report["exists"])
        self.assertFalse(path.exists())
        self.assertEqual(report["physical_total_bytes"], 0)
        self.assertTrue(report["logical"]["complete"])

    def test_physical_read_leaves_database_and_directory_unchanged(self):
        path = self.root / "store.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_events(sequence INTEGER PRIMARY KEY, payload TEXT)")
            connection.execute("CREATE INDEX sdk_events_payload ON sdk_events(payload)")
            connection.execute("INSERT INTO sdk_events(payload) VALUES(?)", ('{"value":1}',))
        before_names = sorted(item.name for item in self.root.iterdir())
        before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        before_stat = path.stat()

        report = inspect_storage_usage(path)

        self.assertTrue(report["exists"])
        self.assertEqual(report["sqlite"]["allocated_page_bytes"],
                         report["sqlite"]["page_size_bytes"] * report["sqlite"]["page_count"])
        self.assertIsNone(report["sqlite"]["exact_reclaimable_bytes"])
        self.assertEqual(sorted(item.name for item in self.root.iterdir()), before_names)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before_digest)
        self.assertEqual(path.stat().st_mtime_ns, before_stat.st_mtime_ns)
        if report["owned_objects"]["available"]:
            names = {item["name"] for item in report["owned_objects"]["objects"]}
            self.assertIn("sdk_events", names)
            self.assertIn("sdk_events_payload", names)
        else:
            self.assertIn("unavailable", report["owned_objects"]["reason"])

    def test_inspection_executes_no_write_or_maintenance_statements(self):
        path = self.root / "readonly.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_events(sequence INTEGER PRIMARY KEY, payload TEXT)")
            connection.execute("INSERT INTO sdk_events(payload) VALUES('value')")
        statements = []
        real_connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        with mock.patch("dispatcher_sdk.storage_usage.sqlite3.connect", side_effect=traced_connect):
            inspect_storage_usage(path, detail="logical")

        normalized = [" ".join(statement.upper().split()) for statement in statements]
        forbidden = ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP ", "ALTER ",
                     "VACUUM", "PRAGMA QUICK_CHECK", "PRAGMA WAL_CHECKPOINT", "BEGIN IMMEDIATE")
        self.assertFalse([statement for statement in normalized if statement.startswith(forbidden)])

    def test_logical_scan_reports_payload_categories_without_decoding_json(self):
        path = self.root / "logical.sqlite3"
        current = "not-json-current"
        history = "not-json-history"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE sdk_run_items(run_id TEXT,section TEXT,item_key TEXT,value TEXT)"
            )
            connection.execute(
                "CREATE TABLE sdk_run_history(run_id TEXT,section TEXT,item_key TEXT,revision INTEGER,value TEXT)"
            )
            connection.execute(
                "INSERT INTO sdk_run_items VALUES('r','root','application_state',?)", (current,)
            )
            connection.execute(
                "INSERT INTO sdk_run_history VALUES('r','root','application_state',1,?)", (history,)
            )

        logical = inspect_storage_usage(path, detail="logical")["logical"]
        self.assertTrue(logical["complete"])
        self.assertEqual(logical["categories"]["current_application_state"]["bytes"], len(current))
        self.assertEqual(logical["categories"]["historical_application_state"]["bytes"], len(history))

    def test_logical_scan_stops_at_global_row_budget(self):
        path = self.root / "bounded.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_events(sequence INTEGER PRIMARY KEY, payload TEXT)")
            connection.executemany("INSERT INTO sdk_events(payload) VALUES(?)",
                                   [(f'{{"value":{number}}}',) for number in range(5)])

        logical = inspect_storage_usage(path, detail="logical", scan_limit=2)["logical"]
        self.assertFalse(logical["complete"])
        self.assertEqual(logical["rows_scanned"], 2)
        self.assertEqual(logical["tables"]["sdk_events"]["rows_scanned"], 2)
        self.assertEqual(logical["stopped_at"]["table"], "sdk_events")

    def test_content_object_storage_is_counted_once(self):
        path = self.root / "objects.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE sdk_content_objects(digest TEXT PRIMARY KEY,stored_length INTEGER,content BLOB)"
            )
            connection.execute("INSERT INTO sdk_content_objects VALUES('one',3,?)", (b"abc",))
            connection.execute("INSERT INTO sdk_content_objects VALUES('two',4,?)", (b"defg",))

        logical = inspect_storage_usage(path, detail="logical")["logical"]
        self.assertEqual(logical["content_objects"], {
            "objects_scanned": 2, "stored_bytes": 7, "counted_once": True,
        })
        self.assertEqual(logical["payload_bytes"], 7)

    def test_current_sdk_content_object_schema_reports_encoded_storage(self):
        path = self.root / "encoded-objects.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE sdk_content_objects(digest TEXT PRIMARY KEY,encoded TEXT,logical_bytes INTEGER)"
            )
            connection.execute("INSERT INTO sdk_content_objects VALUES('one','encoded-value',999)")

        logical = inspect_storage_usage(path, detail="logical")["logical"]
        self.assertEqual(logical["content_objects"]["stored_bytes"], len("encoded-value"))
        self.assertEqual(logical["payload_bytes"], len("encoded-value"))

    def test_wal_rows_are_visible_without_checkpointing(self):
        path = self.root / "wal.sqlite3"
        writer = sqlite3.connect(path)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("CREATE TABLE sdk_events(sequence INTEGER PRIMARY KEY, payload TEXT)")
            writer.commit()
            writer.executemany("INSERT INTO sdk_events(payload) VALUES(?)", [("one",), ("two",)])
            writer.commit()
            wal = Path(str(path) + "-wal")
            before = wal.stat().st_size

            report = inspect_storage_usage(path, detail="logical")

            self.assertEqual(report["sqlite"]["journal_mode"], "wal")
            self.assertEqual(report["logical"]["categories"]["event_payloads"]["values"], 2)
            self.assertGreater(report["files"]["wal"]["bytes"], 0)
            self.assertEqual(wal.stat().st_size, before)
        finally:
            writer.close()

    def test_arguments_are_validated_before_opening(self):
        path = self.root / "missing.sqlite3"
        with self.assertRaises(ValueError):
            inspect_storage_usage(path, detail="deep")
        with self.assertRaises(ValueError):
            inspect_storage_usage(path, detail="logical", scan_limit=True)
        self.assertFalse(path.exists())

    def test_files_detail_does_not_open_sqlite(self):
        path = self.root / "files.sqlite3"
        path.write_bytes(b"not necessarily sqlite")
        with mock.patch("dispatcher_sdk.storage_usage.sqlite3.connect") as connect:
            report = inspect_storage_usage(path, detail="files")
        connect.assert_not_called()
        self.assertEqual(report["actual_scope"], ["files"])
        self.assertTrue(report["complete"])
        self.assertEqual(report["physical_total_bytes"], len(b"not necessarily sqlite"))

    def test_timeout_during_physical_inspection_is_incomplete(self):
        path = self.root / "budget.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_events(sequence INTEGER PRIMARY KEY,payload TEXT)")
        events = []
        report = inspect_storage_usage(path, timeout_seconds=0, progress=events.append)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "timeout")
        self.assertEqual(report["actual_scope"], ["files"])
        self.assertTrue(all("percent" not in event for event in events))

    def test_sqlite_progress_handler_interrupts_large_dbstat_scan(self):
        path = self.root / "large-physical.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_large(value BLOB)")
            connection.executemany("INSERT INTO sdk_large VALUES(zeroblob(512))",
                                   [() for _ in range(20_000)])

        class Clock:
            now = 0.0

            def __call__(self):
                return self.now

        clock = Clock()

        def advance(event):
            if event["phase"] == "object_attribution" and event["status"] == "started":
                clock.now = 2.0

        with mock.patch("dispatcher_sdk._inspection.time.monotonic", clock):
            report = inspect_storage_usage(path, timeout_seconds=1, progress=advance)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "timeout")
        self.assertEqual(report["checks"]["sqlite_metadata"], "checked")
        self.assertEqual(report["checks"]["object_attribution"], "unknown")
        self.assertNotIn("object_attribution", report["actual_scope"])

    def test_logical_scan_limit_marks_top_level_incomplete(self):
        path = self.root / "top-level-limit.sqlite3"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE sdk_events(sequence INTEGER PRIMARY KEY,payload TEXT)")
            connection.executemany("INSERT INTO sdk_events(payload) VALUES(?)", [("x",), ("y",)])
        report = inspect_storage_usage(path, detail="logical", scan_limit=1)
        self.assertFalse(report["complete"])
        self.assertEqual(report["stopped_reason"], "scan_limit")
        self.assertIn("logical_payloads", report["actual_scope"])


if __name__ == "__main__":
    unittest.main()
