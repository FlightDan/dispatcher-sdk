"""Close retains real child storage owners after its caller's deadline."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.children import ChildService, HandlerChildren, _Store
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, ExecutionLease, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests.test_managed_children_capacity import ParentAuthority, RequestJournal


class ChildServiceCloseLifetimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)
        self.journal = RequestJournal(self.path / "children.sqlite3")
        self.journal.options.write_timeout = 2
        self.journal.clock = time.time
        command = ExecutionCommandV2("parent", "parent", "test-registry", "close-lifetime", None,
            "child", 1, RetryPolicy(), 10, {})
        lease = ExecutionLease("parent", "parent-lease", "worker", 1, 1, time.time() + 60, 1)
        budget = BudgetEnvelope((), sample_clock()).enter_handler(30, origin_id="parent-time", reserve_seconds=2)
        capability = HandlerChildren(ParentAuthority(), command, lease, budget,
            {"capacity": 1, "max_depth": 1, "registry_revision": "test-registry"}, journal=self.journal)
        child = ExecutionCommandV2("child", "child", "test-registry", "close-lifetime", None,
            "child", 1, RetryPolicy(), 10, {})
        self.row = capability._enqueue(request_id="one", child_id="child", action="run",
            child_command=child, envelope=capability._budget("one", 10))

    def test_coordinator_sqlite_wait_does_not_extend_close_deadline(self):
        entered = threading.Event()
        original = self.journal._transaction

        @contextmanager
        def observe_transaction(*, timeout_seconds=None):
            entered.set()
            with original(timeout_seconds=timeout_seconds) as transaction:
                yield transaction

        service = ChildService(SimpleNamespace(kernel=ParentAuthority()), self.journal)
        writer = sqlite3.connect(self.journal.path)
        writer.execute("BEGIN IMMEDIATE")
        try:
            with patch.object(self.journal, "_transaction", observe_transaction):
                service.start()
                self.assertTrue(entered.wait(2))
                started = time.monotonic()
                report = service.close(timeout_seconds=.05)
                self.assertLess(time.monotonic() - started, .3, report)
                self.assertTrue(report["dispatcher_alive"], report)
                self.assertTrue(report["inspection_pending"], report)
                self.assertIsNone(report["unfinished_workers"], report)
                self.assertTrue(service._close_pending())
        finally:
            writer.rollback()
            writer.close()
            report = service.close(timeout_seconds=2)
        self.assertFalse(service._close_pending(), report)
        self.assertEqual(report["unfinished_workers"], 0)
        # The coordinator's already-claimed row must not submit new business
        # when its SQLite operation finally returns after close.
        self.assertEqual(service._futures, {})

    def test_actual_child_cleanup_future_remains_owned_until_sqlite_finishes(self):
        kernel = SQLiteKernel(self.path / "kernel.sqlite3")
        self.addCleanup(kernel.close)
        # The real Kernel has no matching parent. The actual _execute worker
        # must publish that original failure through its normal cleanup path.
        service = ChildService(SimpleNamespace(kernel=kernel), self.journal)
        finish_entered = threading.Event()
        finish_release = threading.Event()
        storage_entered = threading.Event()
        original_finish = _Store.finish
        original_transaction = self.journal._transaction

        def gate_finish(store, *args, **kwargs):
            finish_entered.set()
            if not finish_release.wait(3):
                raise TimeoutError("test did not release child cleanup")
            return original_finish(store, *args, **kwargs)

        @contextmanager
        def observe_transaction(*, timeout_seconds=None):
            if threading.current_thread().name.startswith("sdk-child_"):
                storage_entered.set()
            with original_transaction(timeout_seconds=timeout_seconds) as transaction:
                yield transaction

        writer = None
        try:
            with patch.object(_Store, "finish", gate_finish), patch.object(
                    self.journal, "_transaction", observe_transaction):
                service.start()
                self.assertTrue(finish_entered.wait(2))
                writer = sqlite3.connect(self.journal.path)
                writer.execute("BEGIN IMMEDIATE")
                finish_release.set()
                self.assertTrue(storage_entered.wait(2))
                started = time.monotonic()
                report = service.close(timeout_seconds=.05)
                self.assertLess(time.monotonic() - started, .3, report)
                self.assertFalse(report["dispatcher_alive"], report)
                self.assertEqual(report["unfinished_workers"], 1, report)
                self.assertTrue(service._close_pending())
        finally:
            finish_release.set()
            if writer is not None:
                writer.rollback()
                writer.close()
            report = service.close(timeout_seconds=2)
        self.assertFalse(service._close_pending(), report)
        self.assertEqual(report["unfinished_workers"], 0, report)
        self.assertEqual(service.store.request("parent", "one")["state"], "failed")


if __name__ == "__main__":
    unittest.main()
