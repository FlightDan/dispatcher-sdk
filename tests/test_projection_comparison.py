import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dispatcher_sdk.orchestrator import OrchestrationError
from dispatcher_sdk.orchestrator.projection_storage import ProjectionStorage
from dispatcher_sdk.orchestrator.projection_stream import compare_projection_stream, iter_installed_projection, STREAM_POINTER_PREFIX
from dispatcher_sdk.orchestrator.contracts import canonical


class ProjectionComparisonTests(unittest.TestCase):
    def test_installed_history_reader_requires_host_retention(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "run.sqlite"
            store = ProjectionStorage(Path(root) / "bytes.sqlite")
            binding = {"run": "r", "decision": "d"}
            data = b'{"v":1}'
            store.create("s", total_bytes=len(data), binding=binding)
            store.append("s", sequence=0, data=data[:3], complete=False)
            store.append("s", sequence=1, data=data[3:], complete=True)
            pointer = {"stream_id": "s", "binding": binding, "total_bytes": len(data), **store.identity()}
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE sdk_run_revisions(run_id TEXT, revision INTEGER)")
                db.execute("CREATE TABLE sdk_run_history(run_id TEXT, section TEXT, item_key TEXT, revision INTEGER, value TEXT)")
                db.execute("CREATE TABLE sdk_streamed_projection_pointers(run_id TEXT, revision INTEGER, pointer TEXT)")
                db.execute("CREATE TABLE sdk_storage_identity(singleton INTEGER, store_id TEXT, incarnation TEXT)")
                db.execute("INSERT INTO sdk_storage_identity VALUES(1,'orchestrator','incarnation')")
                db.execute("INSERT INTO sdk_run_revisions VALUES('r',1),('r',2)")
                db.execute("INSERT INTO sdk_run_history VALUES('r','root','application_state',1,?)", (data.decode(),))
                db.execute("INSERT INTO sdk_streamed_projection_pointers VALUES('r',1,?)", (STREAM_POINTER_PREFIX + canonical(pointer),))
            class RunStore:
                def _connect(self):
                    return sqlite3.connect(path)
            def verify(_, actual_storage):
                self.assertIs(actual_storage, store)
                return {"run_id": "r", "revision": 2, "pointer": pointer, "retained_immutable": True,
                        "orchestrator_store_id": "orchestrator", "orchestrator_incarnation": "incarnation"}
            run_store = RunStore()
            with self.assertRaises(OrchestrationError):
                b"".join(iter_installed_projection(run_store, "r", revision=2, storage=store, credential="token"))
            run_store.projection_verifier = verify
            self.assertEqual(b"".join(iter_installed_projection(run_store, "r", revision=2, storage=store, credential="token")), data)
            other = ProjectionStorage(Path(root) / "other.sqlite")
            other.create("s", total_bytes=len(data), binding=binding)
            other.append("s", sequence=0, data=b'{"v":2}', complete=True)
            def accept_claim(_, actual_storage):
                return {"run_id": "r", "revision": 2, "pointer": pointer, "retained_immutable": True,
                        "orchestrator_store_id": "orchestrator", "orchestrator_incarnation": "incarnation"}
            run_store.projection_verifier = accept_claim
            with self.assertRaises(OrchestrationError):
                b"".join(iter_installed_projection(run_store, "r", revision=2, storage=other, credential="token"))
            run_store.projection_verifier = verify
            with self.assertRaises(OrchestrationError):
                b"".join(iter_installed_projection(run_store, "r", revision=1, storage=store, credential="token"))

    def test_direct_bytes_complete_and_bound(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "run.sqlite"
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE sdk_runs(run_id TEXT, revision INTEGER)")
                db.execute("CREATE TABLE sdk_run_items(run_id TEXT, section TEXT, item_key TEXT, value TEXT)")
                db.execute("INSERT INTO sdk_runs VALUES('r',2)")
                db.execute("INSERT INTO sdk_run_items VALUES('r','root','application_state',?)", ('{"a":[1,true]}',))
            class RunStore:
                def _connect(self):
                    return sqlite3.connect(path)
            store = ProjectionStorage(Path(root) / "bytes.sqlite")
            binding = {"operation": "op", "revision": 2}
            encoded = b'{"a":[1,true]}'
            store.create("s", total_bytes=len(encoded), binding=binding)
            store.append("s", sequence=0, data=encoded[:5], complete=False)
            with self.assertRaises(OrchestrationError):
                compare_projection_stream(RunStore(), "r", expected_revision=2, storage=store, stream_id="s", expected_binding=binding)
            store.append("s", sequence=1, data=encoded[5:], complete=True)
            self.assertEqual(compare_projection_stream(RunStore(), "r", expected_revision=2, storage=store, stream_id="s", expected_binding=binding)["total_bytes"], len(encoded))
            with contextlib.closing(sqlite3.connect(store.path)) as db, db:
                db.execute("UPDATE projection_pages SET complete=1 WHERE stream_id='s' AND sequence=0")
            with self.assertRaises(OrchestrationError):
                compare_projection_stream(RunStore(), "r", expected_revision=2, storage=store, stream_id="s", expected_binding=binding)
            with contextlib.closing(sqlite3.connect(store.path)) as db, db:
                db.execute("UPDATE projection_pages SET complete=0 WHERE stream_id='s' AND sequence=0")
            with self.assertRaises(OrchestrationError):
                compare_projection_stream(RunStore(), "r", expected_revision=2, storage=store, stream_id="s", expected_binding={"operation": "op", "revision": True})
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute("UPDATE sdk_run_items SET value=?", ('{"a":[2,true]}',))
            with self.assertRaises(OrchestrationError):
                compare_projection_stream(RunStore(), "r", expected_revision=2, storage=store, stream_id="s", expected_binding=binding)
