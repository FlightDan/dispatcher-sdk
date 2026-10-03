"""Existing sidecar admission cannot remove the handler's child capability."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

import dispatcher_sdk
from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.observability import ObservationJournal, ObservationOptions
from dispatcher_sdk.observability.contracts import ObservationError, ObservationIdentity


class _Witness:
    entered = threading.Event()
    calls = []


def parent(payload, context):
    _Witness.entered.set()
    return context.children.run("child", {}, request_id="during-contention", timeout_seconds=3)


def child(payload, context):
    _Witness.calls.append(context.command.execution_id)
    return {"original": 42}


parent.__execution_kernel_revision__ = "context-attachment-parent-v1"
child.__execution_kernel_revision__ = "context-attachment-child-v1"


class ContextJournalAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sdk-context-attachment-"))
        self.evidence = {"sdk_import": dispatcher_sdk.__file__, "case": self.id()}
        self.addCleanup(lambda: (self.root / "evidence.json").write_text(json.dumps(self.evidence, indent=2)))
        print("context_attachment_evidence=" + str(self.root / "evidence.json"), flush=True)

    def journal(self):
        return ObservationJournal(self.root / "observations.sqlite3",
            kernel_path=self.root / "kernel.sqlite3", source_id="store",
            options=ObservationOptions(write_timeout=.03))

    def attach(self, journal):
        return ObservationJournal._open_existing_writer(journal.path,
            kernel_path=journal.kernel_path, source_id=journal.source_id, options=journal.options)

    def test_existing_writer_attaches_without_admission_and_validates_on_first_operation(self):
        journal = self.journal()
        identity = ObservationIdentity("work", 1, 1)
        with closing(sqlite3.connect(journal.path)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            before = time.monotonic()
            attached = self.attach(journal)
            elapsed = time.monotonic() - before
            self.assertLess(elapsed, .03)
            self.assertTrue(attached._schema_pending)
            with self.assertRaises(sqlite3.OperationalError) as caught:
                attached.phase(identity, "blocked")
            self.assertIn("locked", str(caught.exception))
            self.assertTrue(attached._schema_pending)
            blocker.rollback()
        attached.phase(identity, "after-release")
        self.assertFalse(attached._schema_pending)
        self.assertEqual([row["phase"] for row in attached.inspect("work", attempt=1, fence=1)["phases"]],
                         ["after-release"])
        self.evidence.update(construction_elapsed=elapsed, raw_admission_error=str(caught.exception))

    def test_missing_sidecar_is_not_recreated(self):
        path = self.root / "absent" / "observations.sqlite3"
        attached = ObservationJournal._open_existing_writer(path,
            kernel_path=self.root / "kernel.sqlite3", source_id="store")
        self.assertFalse(path.parent.exists())
        with self.assertRaises(sqlite3.OperationalError):
            attached.phase(ObservationIdentity("work", 1, 1), "cannot-create")
        self.assertFalse(path.parent.exists())

    def test_replaced_schema_and_wrong_binding_fail_before_first_write(self):
        journal = self.journal()
        wrong_binding = ObservationJournal._open_existing_writer(journal.path,
            kernel_path=journal.kernel_path, source_id="different-store")
        with self.assertRaises(ObservationError):
            wrong_binding.phase(ObservationIdentity("work", 1, 1), "wrong-binding")
        attached = self.attach(journal)
        with closing(sqlite3.connect(journal.path)) as replacement:
            replacement.execute("DROP TABLE obs_waits")
            replacement.commit()
        with self.assertRaises(ObservationError):
            attached.phase(ObservationIdentity("work", 1, 1), "wrong-schema")
        with closing(sqlite3.connect(journal.path)) as reader:
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM obs_phases").fetchone()[0], 0)

    def test_public_parent_and_child_complete_after_real_sidecar_writer_contention(self):
        _Witness.entered = threading.Event()
        _Witness.calls = []
        outcomes, errors = [], []
        with Kernel.open_sqlite(self.root / "kernel.sqlite3", {"parent": parent, "child": child},
                               isolation_mode="thread", observation_options=ObservationOptions(write_timeout=.03)) as runtime:
            runtime.submit(runtime.command("parent", execution_id="parent", idempotency_key="parent",
                correlation_id="attachment", timeout_seconds=10, payload={}))
            def drive():
                try:
                    outcomes.append(runtime.run_once(execution_id="parent"))
                except BaseException as error:
                    errors.append(repr(error))
            driver = threading.Thread(target=drive)
            with closing(sqlite3.connect(runtime.observation_storage["path"])) as blocker:
                blocker.execute("BEGIN IMMEDIATE")
                driver.start()
                try:
                    self.assertTrue(_Witness.entered.wait(2))
                    time.sleep(.15)
                    self.assertEqual(blocker.execute("SELECT COUNT(*) FROM sdk_child_requests").fetchone()[0], 0)
                finally:
                    blocker.rollback()
            driver.join(5)
            self.assertFalse(driver.is_alive(), errors)
            self.assertEqual(errors, [])
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(outcomes[0].state, "succeeded", outcomes[0].to_dict())
            self.assertEqual(outcomes[0].result.value["value"], {"original": 42})
            self.assertEqual(_Witness.calls, [outcomes[0].result.value["execution_id"]])
            self.evidence.update(parent=outcomes[0].to_dict(), child_calls=_Witness.calls,
                                 observation_storage=runtime.observation_storage)


if __name__ == "__main__":
    unittest.main()
