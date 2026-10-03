"""Readonly notification admission shares the caller's query budget."""
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from dispatcher_sdk import ObservationOptions
from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk._inspection import InspectionBudgetExceeded


def unused_handler(payload, context):
    return payload


class ObservationReadAdmissionTests(unittest.TestCase):
    def test_public_outbox_waits_for_writer_within_its_read_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Kernel.open_sqlite(Path(directory) / "kernel.sqlite3", {"unused": unused_handler},
                observation_options=ObservationOptions(write_timeout=.01, query_timeout=1))
            with runtime:
                journal = runtime.observation_journal
                writer = sqlite3.connect(journal.path, check_same_thread=False)
                self.addCleanup(writer.close)
                writer.execute("PRAGMA journal_mode=DELETE")
                writer.execute("BEGIN EXCLUSIVE")
                release = threading.Timer(.2, writer.rollback)
                release.start()
                try:
                    started = time.monotonic()
                    self.assertEqual(runtime.stall_notifications(), ())
                    elapsed = time.monotonic() - started
                    self.assertGreater(elapsed, .1)
                    self.assertLess(elapsed, 1)
                finally:
                    release.join(1)
                    writer.rollback()

    def test_exhausted_query_does_not_return_an_empty_success(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Kernel.open_sqlite(Path(directory) / "kernel.sqlite3", {"unused": unused_handler},
                observation_options=ObservationOptions(write_timeout=.01, query_timeout=.08))
            with runtime:
                writer = sqlite3.connect(runtime.observation_journal.path)
                self.addCleanup(writer.close)
                writer.execute("PRAGMA journal_mode=DELETE")
                writer.execute("BEGIN EXCLUSIVE")
                try:
                    started = time.monotonic()
                    with self.assertRaises(InspectionBudgetExceeded):
                        runtime.stall_notifications()
                    self.assertLess(time.monotonic() - started, .2)
                finally:
                    writer.rollback()
