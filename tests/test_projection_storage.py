import contextlib
import tempfile
import threading
import unittest
import os
import subprocess
import sys
import sqlite3
from pathlib import Path

from dispatcher_sdk.orchestrator.projection_storage import ProjectionStorage, ProjectionStorageError


class ProjectionStorageTests(unittest.TestCase):
    def test_identity_is_durable_immutable_and_returned_with_pages(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'one.db'
            store = ProjectionStorage(path)
            identity = store.identity()
            self.assertNotEqual(identity['store_id'], identity['incarnation'])
            self.assertNotEqual(identity, ProjectionStorage(Path(root) / 'two.db').identity())
            store.create('s', total_bytes=1, binding={'source': 'host'})
            store.append('s', sequence=0, data=b'x', complete=True)
            reopened = ProjectionStorage(path)
            self.assertEqual(reopened.identity(), identity)
            for read in (reopened.inspect('s'), reopened.read('s')):
                self.assertEqual({key: read[key] for key in identity}, identity)
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("UPDATE projection_meta SET incarnation='different'")
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute('DELETE FROM projection_meta')

    def test_legacy_store_is_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'legacy.db'
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE projection_meta(version INTEGER NOT NULL)')
                db.execute('INSERT INTO projection_meta VALUES(1)')
                db.execute('CREATE TABLE projection_streams(stream_id TEXT)')
                db.execute('CREATE TABLE projection_pages(stream_id TEXT)')
            with self.assertRaisesRegex(ProjectionStorageError, 'legacy identity'):
                ProjectionStorage(path)
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(db.execute('SELECT * FROM projection_meta').fetchall(), [(1,)])

    def test_committed_page_survives_abrupt_writer_exit(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "projection.db"
            script = ("import os,sys; from dispatcher_sdk.orchestrator.projection_storage import ProjectionStorage; "
                      "s=ProjectionStorage(sys.argv[1]); s.create('s',total_bytes=2,binding={'source':'host'}); "
                      "s.append('s',sequence=0,data=b'a',complete=False); os._exit(0)")
            result = subprocess.run([sys.executable, "-c", script, str(path)], env=os.environ.copy(), timeout=10)
            self.assertEqual(result.returncode, 0)
            store = ProjectionStorage(path)
            self.assertEqual(store.read("s")["pages"][0]["data"], b"a")
            self.assertTrue(store.append("s", sequence=1, data=b"b", complete=True)["complete"])

    def test_exact_replay_and_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "projection.db"
            binding = {"operation": "op", "store": "host-store", "source_revision": 2, "lease": "lease"}
            store = ProjectionStorage(path)
            store.create("source", total_bytes=4, binding=binding)
            store.append("source", sequence=0, data=b"ab", complete=False)
            store = ProjectionStorage(path)
            store.create("source", total_bytes=4, binding=dict(binding))
            store.append("source", sequence=0, data=b"ab", complete=False)
            with self.assertRaises(ProjectionStorageError):
                store.append("source", sequence=0, data=b"ax", complete=False)
            with self.assertRaises(ProjectionStorageError):
                store.create("source", total_bytes=4, binding={**binding, "lease": "other"})
            status = store.append("source", sequence=1, data=b"cd", complete=True)
            self.assertTrue(status["complete"])
            first = store.read("source", limit=1)
            second = store.read("source", after=first["cursor"], limit=1)
            self.assertTrue(first["has_more"])
            self.assertEqual(first["pages"][0]["data"] + second["pages"][0]["data"], b"abcd")
            self.assertFalse(second["has_more"])

    def test_bounds_and_independent_streams(self):
        with tempfile.TemporaryDirectory() as root:
            store = ProjectionStorage(Path(root) / "projection.db")
            store.create("source", total_bytes=1, binding={"kind": "source"})
            store.create("target", total_bytes=0, binding={"kind": "target"})
            with self.assertRaises(ProjectionStorageError):
                store.append("source", sequence=1, data=b"x", complete=True)
            with self.assertRaises(ValueError):
                store.append("source", sequence=0, data=b"", complete=False)
            with self.assertRaises(ProjectionStorageError):
                store.append("source", sequence=0, data=b"xx", complete=True)
            self.assertTrue(store.append("target", sequence=0, data=b"", complete=True)["complete"])
            self.assertFalse(store.inspect("source")["complete"])
            with self.assertRaises(ValueError):
                store.read("target", limit=5)

    def test_conflicting_concurrent_page_has_one_winner(self):
        with tempfile.TemporaryDirectory() as root:
            store = ProjectionStorage(Path(root) / "projection.db")
            store.create("s", total_bytes=1, binding={"kind": "source"})
            barrier, outcomes = threading.Barrier(2), []
            def append(data):
                barrier.wait()
                try:
                    store.append("s", sequence=0, data=data, complete=True)
                    outcomes.append("stored")
                except ProjectionStorageError:
                    outcomes.append("conflict")
            threads = [threading.Thread(target=append, args=(data,)) for data in (b"a", b"b")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)
            self.assertCountEqual(outcomes, ["stored", "conflict"])

    def test_missing_page_does_not_appear_as_complete_stream(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "projection.db"
            store = ProjectionStorage(path)
            store.create("s", total_bytes=2, binding={"source": "host"})
            store.append("s", sequence=0, data=b"a", complete=False)
            store.append("s", sequence=1, data=b"b", complete=True)
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute("DELETE FROM projection_pages WHERE stream_id='s' AND sequence=0")
            with self.assertRaisesRegex(ProjectionStorageError, "missing"):
                store.read("s")
