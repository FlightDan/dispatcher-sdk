import tempfile
import threading
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.application_budget import ApplicationBudget, BudgetError


class ApplicationBudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "budget.sqlite"
        self.now = 10.0
        self.ledger = ApplicationBudget(self.path, clock=lambda: self.now)
        self.ledger.create("run", "agent", "tokens", allowance=10, deadline=20)

    def test_restart_unknown_and_reconciliation_preserve_original_budget(self):
        first = self.ledger.reserve("run", "agent", "tokens", "call", amount=6)
        self.assertTrue(first["spend_authorized"])
        restarted = ApplicationBudget(self.path, clock=lambda: self.now)
        self.assertFalse(restarted.reserve("run", "agent", "tokens", "call", amount=6)["spend_authorized"])
        with self.assertRaisesRegex(BudgetError, "pending"):
            restarted.reserve("run", "agent", "tokens", "another", amount=1)
        self.assertTrue(restarted.inspect("run", "agent", "tokens")["admission_blocked"])
        restarted.settle("run", "agent", "tokens", "call", actual=None)
        with self.assertRaisesRegex(BudgetError, "unknown"):
            restarted.reserve("run", "agent", "tokens", "another", amount=1)
        self.assertIsNone(restarted.inspect("run", "agent", "tokens")["available"])
        restarted.reconcile("run", "agent", "tokens", "call", actual=4)
        restarted.reconcile("run", "agent", "tokens", "call", actual=4)
        with self.assertRaises(BudgetError):
            restarted.reconcile("run", "agent", "tokens", "call", actual=5)
        status = restarted.inspect("run", "agent", "tokens")
        self.assertEqual((status["spent"], status["available"], status["deadline"]), (4, 6, 20))
        with self.assertRaises(BudgetError):
            restarted.create("run", "agent", "tokens", allowance=11, deadline=21)

    def test_scope_isolation_deadline_and_overage(self):
        self.ledger.create("run", "api", "cents", allowance=3, deadline=15)
        self.ledger.reserve("run", "agent", "tokens", "a", amount=1)
        self.ledger.settle("run", "agent", "tokens", "a", actual=11)
        with self.assertRaisesRegex(BudgetError, "exhausted"):
            self.ledger.reserve("run", "agent", "tokens", "b", amount=1)
        self.assertTrue(self.ledger.reserve("run", "api", "cents", "a", amount=3)["spend_authorized"])
        self.now = 21
        with self.assertRaisesRegex(BudgetError, "deadline"):
            self.ledger.reserve("run", "agent", "tokens", "c", amount=1)
        self.now = 11
        with self.assertRaisesRegex(BudgetError, "deadline"):
            self.ledger.reserve("run", "agent", "tokens", "c", amount=1)
        self.ledger.settle("run", "api", "cents", "a", actual=2)

    def test_deadline_crossed_during_scan_or_insert_never_authorizes(self):
        original = self.ledger._reservations
        def delayed(db, scope):
            rows = list(original(db, scope))
            self.now = 20
            return iter(rows)
        with patch.object(self.ledger, '_reservations', side_effect=delayed):
            with self.assertRaisesRegex(BudgetError, 'deadline'):
                self.ledger.reserve('run', 'agent', 'tokens', 'scan', amount=1)
        self.now = 11
        with self.assertRaisesRegex(BudgetError, 'deadline'):
            self.ledger.reserve('run', 'agent', 'tokens', 'scan', amount=1)
        self.ledger.create('run', 'second', 'tokens', allowance=5, deadline=30)
        with patch.object(self.ledger, '_now', side_effect=[11, 11, 30]):
            with self.assertRaisesRegex(BudgetError, 'deadline'):
                self.ledger.reserve('run', 'second', 'tokens', 'insert', amount=1)
        with sqlite3.connect(self.path) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM application_reservations WHERE request_id='insert'").fetchone())

    def test_concurrent_reservations_cannot_overallocate(self):
        barrier = threading.Barrier(2)
        outcomes = []
        def reserve(request):
            barrier.wait()
            try:
                outcomes.append(self.ledger.reserve("run", "agent", "tokens", request, amount=6)["state"])
            except BudgetError:
                outcomes.append("rejected")
        threads = [threading.Thread(target=reserve, args=(str(i),)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertCountEqual(outcomes, ["reserved", "rejected"])
        self.assertEqual(self.ledger.inspect("run", "agent", "tokens")["reserved"], 6)

    def test_missing_ledger_table_fails_closed_on_reopen(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE application_reservations")
        with self.assertRaisesRegex(BudgetError, "incomplete"):
            ApplicationBudget(self.path)

    def test_legacy_import_replay_and_restart_preserve_usage(self):
        manifest = dict(allowance=20, deadline=30, spent=7, source="host ledger export",
                        reservations=[{"request_id": "old-call", "amount": 5, "state": "unknown"}])
        status = self.ledger.import_legacy("legacy", "api", "cents", **manifest)
        self.assertEqual((status["spent"], status["reserved"], status["legacy_source"]), (7, 5, "host ledger export"))
        restarted = ApplicationBudget(self.path, clock=lambda: self.now)
        restarted.import_legacy("legacy", "api", "cents", **manifest)
        with self.assertRaisesRegex(BudgetError, "unknown"):
            restarted.reserve("legacy", "api", "cents", "next", amount=1)
        restarted.reconcile("legacy", "api", "cents", "old-call", actual=4)
        self.assertEqual(restarted.inspect("legacy", "api", "cents")["available"], 9)
        restarted.import_legacy("legacy", "api", "cents", **manifest)
        with self.assertRaisesRegex(BudgetError, "differs"):
            restarted.import_legacy("legacy", "api", "cents", **{**manifest, "allowance": 21})
        with self.assertRaisesRegex(BudgetError, "differs"):
            restarted.import_legacy("legacy", "api", "cents", **{**manifest, "source": "other"})
        with self.assertRaisesRegex(BudgetError, "already exists"):
            restarted.import_legacy("run", "agent", "tokens", **manifest)

    def test_missing_import_table_fails_closed_on_reopen(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE application_budget_imports")
        with self.assertRaisesRegex(BudgetError, "incomplete"):
            ApplicationBudget(self.path)

    def test_reservation_history_limit_is_scoped_and_fails_closed(self):
        with patch("dispatcher_sdk.application_budget._MAX_RESERVATIONS", 2):
            for request in ("one", "two"):
                self.ledger.reserve("run", "agent", "tokens", request, amount=1)
                self.ledger.settle("run", "agent", "tokens", request, actual=1)
            self.assertEqual(self.ledger.inspect("run", "agent", "tokens")["spent"], 2)
            with self.assertRaisesRegex(BudgetError, "history is full"):
                self.ledger.reserve("run", "agent", "tokens", "third", amount=1)
            self.ledger.create("run", "other", "tokens", allowance=10, deadline=20)
            self.assertTrue(self.ledger.reserve("run", "other", "tokens", "first", amount=1)["spend_authorized"])
            with sqlite3.connect(self.path) as db:
                db.execute("INSERT INTO application_reservations VALUES(?,?,?,?,?,'settled',?)",
                           ("run", "agent", "tokens", "external", 1, 1))
            with self.assertRaisesRegex(BudgetError, "history exceeds"):
                self.ledger.inspect("run", "agent", "tokens")

    def test_import_manifest_byte_limit(self):
        with patch("dispatcher_sdk.application_budget._MAX_IMPORT_BYTES", 80):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                self.ledger.import_legacy("legacy", "api", "cents", allowance=10, deadline=20,
                                          spent=1, source="authoritative source", reservations=[])

    def test_archive_preserves_usage_and_exact_replay_across_restart(self):
        with patch('dispatcher_sdk.application_budget._MAX_RESERVATIONS', 2):
            for request in ('one', 'two'):
                self.ledger.reserve('run', 'agent', 'tokens', request, amount=2)
                self.ledger.settle('run', 'agent', 'tokens', request, actual=1)
            self.assertEqual(self.ledger.archive_settled('run', 'agent', 'tokens', limit=1), 1)
            restarted = ApplicationBudget(self.path, clock=lambda: self.now)
            self.assertEqual(restarted.inspect('run', 'agent', 'tokens')['spent'], 2)
            self.assertFalse(restarted.reserve('run', 'agent', 'tokens', 'one', amount=2)['spend_authorized'])
            self.assertEqual(restarted.settle('run', 'agent', 'tokens', 'one', actual=1)['state'], 'settled')
            with self.assertRaises(BudgetError):
                restarted.settle('run', 'agent', 'tokens', 'one', actual=2)
            with self.assertRaises(BudgetError):
                restarted.reserve('run', 'agent', 'tokens', 'one', amount=3)
            self.assertTrue(restarted.reserve('run', 'agent', 'tokens', 'three', amount=8)['spend_authorized'])
            self.assertEqual(restarted.archive_settled('run', 'agent', 'tokens'), 1)
            self.assertEqual(restarted.inspect('run', 'agent', 'tokens')['spent'], 2)

    def test_missing_archive_total_fails_closed(self):
        self.ledger.reserve('run', 'agent', 'tokens', 'old', amount=2)
        self.ledger.settle('run', 'agent', 'tokens', 'old', actual=1)
        self.ledger.archive_settled('run', 'agent', 'tokens')
        with sqlite3.connect(self.path) as db:
            db.execute('DELETE FROM application_budget_archive_totals')
        with self.assertRaisesRegex(BudgetError, 'archived usage'):
            self.ledger.reserve('run', 'agent', 'tokens', 'new', amount=1)

    def test_v2_migration_retains_usage(self):
        self.ledger.reserve('run', 'agent', 'tokens', 'old', amount=2)
        self.ledger.settle('run', 'agent', 'tokens', 'old', actual=1)
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TABLE application_budget_archive')
            db.execute('DROP TABLE application_budget_archive_totals')
            db.execute('UPDATE application_budget_meta SET version=2')
        migrated = ApplicationBudget(self.path, clock=lambda: self.now)
        self.assertEqual(migrated.inspect('run', 'agent', 'tokens')['spent'], 1)
        self.assertEqual(migrated.archive_settled('run', 'agent', 'tokens'), 1)


if __name__ == "__main__":
    unittest.main()
