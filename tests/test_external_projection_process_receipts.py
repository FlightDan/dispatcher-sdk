"""Synthetic SQLite application participant across OS processes.

The existing real-Kernel integration supplies the local control fixture; it
seeds pause/resume state. The host verifier is synthetic, not an isolation proof.
"""
import json
import multiprocessing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_external_projection_foundation as foundation


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _commit_projection(path, binding, source, target, context):
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        version, state, fence, lease = db.execute(
            "SELECT version,state,fence,lease FROM projection").fetchone()
        incoming, lease_id = context["lease_fence"], context["lease_id"]
        if incoming < fence or (incoming == fence and lease_id != lease):
            raise ValueError("stale fence")
        receipt = _encoded({**binding, "receipt_id": "receipt-1"})
        prior = db.execute("SELECT data,source,target FROM receipt").fetchone()
        if prior is not None:
            if prior != (receipt, _encoded(source), _encoded(target)):
                raise ValueError("changed receipt replay")
            db.execute("UPDATE projection SET fence=?,lease=?", (incoming, lease_id))
            return
        if version != binding["source_application_projection_version"] or state != _encoded(source):
            raise ValueError("source projection differs")
        db.execute("UPDATE projection SET version=?,state=?,fence=?,lease=?",
                   (binding["application_projection_version"], _encoded(target), incoming, lease_id))
        if context.get("fail_after_update"):
            raise RuntimeError("injected participant failure")
        db.execute("INSERT INTO receipt VALUES(?,?,?)", (receipt, _encoded(source), _encoded(target)))


class _SQLiteParticipant:
    root = None
    next_id = 0

    def __init__(self):
        self.path = str(Path(self.root) / ("app-%d.sqlite" % self.next_id))
        type(self).next_id += 1
        self.calls = 0
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE projection (version TEXT,state TEXT,fence INTEGER,lease TEXT)")
            db.execute("INSERT INTO projection VALUES(?,?,?,?)", ("p1", _encoded({"old": 1}), -1, ""))
            db.execute("CREATE TABLE receipt (data TEXT,source TEXT,target TEXT)")

    def _read(self):
        if not Path(self.path).exists():
            return (None, None, None)
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT data,source,target FROM receipt").fetchone()
        return tuple(json.loads(value) for value in row) if row else (None, None, None)

    @property
    def receipt(self):
        return self._read()[0]

    @property
    def source(self):
        return self._read()[1]

    @property
    def target(self):
        return self._read()[2]

    def inspect(self, binding):
        receipt = self.receipt
        return receipt if receipt is not None and all(receipt.get(k) == v for k, v in binding.items()) else None

    def apply(self, binding, source, target, context):
        self.calls += 1
        process = multiprocessing.get_context("spawn").Process(
            target=_commit_projection, args=(self.path, binding, source, target, context))
        process.start()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join()
            raise AssertionError("application participant timed out")
        if process.exitcode != 0:
            raise AssertionError("application participant failed")


def _run_fixture(result):
    with tempfile.TemporaryDirectory() as directory:
        _SQLiteParticipant.root = directory
        _SQLiteParticipant.next_id = 0
        case = foundation.RealKernelProjectionIntegrationTests("test_split_store_gate_receipt_recovery")
        case.setUp()
        try:
            with patch.object(foundation, "Participant", _SQLiteParticipant):
                case.test_split_store_gate_receipt_recovery()
            result.put("ok")
        finally:
            case.doCleanups()


class ExternalProjectionProcessReceiptTests(unittest.TestCase):
    def test_atomic_compare_fence_and_immutable_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            _SQLiteParticipant.root = directory
            _SQLiteParticipant.next_id = 0
            participant = _SQLiteParticipant()
            binding = {"source_application_projection_version": "p1", "application_projection_version": "p2",
                       "decision_id": "decision", "scope_id": "x"}
            source, target = {"old": 1}, {"new": 2}
            context = {"lease_fence": 2, "lease_id": "lease-2"}
            with self.assertRaisesRegex(ValueError, "source projection"):
                _commit_projection(participant.path, binding, {"old": 0}, target, context)
            with self.assertRaisesRegex(ValueError, "source projection"):
                _commit_projection(participant.path, {**binding, "source_application_projection_version": "wrong"},
                                   source, target, context)
            with self.assertRaisesRegex(RuntimeError, "injected participant failure"):
                _commit_projection(participant.path, binding, source, target, {**context, "fail_after_update": True})
            with sqlite3.connect(participant.path) as db:
                self.assertEqual(db.execute("SELECT version,state,fence,lease FROM projection").fetchone(),
                                 ("p1", _encoded(source), -1, ""))
                self.assertEqual(db.execute("SELECT count(*) FROM receipt").fetchone()[0], 0)
            self.assertIsNone(participant.inspect(binding))
            participant.apply(binding, source, target, context)
            original = participant.inspect(binding)
            participant.apply(binding, source, target, context)
            self.assertEqual(participant.inspect(binding), original)
            with self.assertRaisesRegex(ValueError, "stale fence"):
                _commit_projection(participant.path, binding, source, target, {"lease_fence": 1, "lease_id": "old"})
            with self.assertRaisesRegex(ValueError, "stale fence"):
                _commit_projection(participant.path, binding, source, target, {"lease_fence": 2, "lease_id": "other"})
            with self.assertRaisesRegex(ValueError, "changed receipt"):
                _commit_projection(participant.path, binding, source, {"new": 3}, context)
            with sqlite3.connect(participant.path) as db:
                self.assertEqual(db.execute("SELECT version,state,fence,lease FROM projection").fetchone(),
                                 ("p2", _encoded(target), 2, "lease-2"))
                self.assertEqual(db.execute("SELECT count(*) FROM receipt").fetchone()[0], 1)
            _commit_projection(participant.path, binding, source, target, {"lease_fence": 3, "lease_id": "lease-3"})
            with self.assertRaisesRegex(ValueError, "stale fence"):
                _commit_projection(participant.path, binding, source, target, context)
            self.assertEqual(participant.inspect(binding), original)

    def test_scoped_partial_admission_and_receipt_recovery(self):
        context = multiprocessing.get_context("spawn")
        result = context.Queue()
        try:
            process = context.Process(target=_run_fixture, args=(result,))
            process.start()
            process.join(30)
            if process.is_alive():
                process.terminate()
                process.join()
                self.fail("projection lifecycle timed out")
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(result.get(timeout=2), "ok")
        finally:
            result.close()
