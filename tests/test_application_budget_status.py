import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.application_budget import ApplicationBudget, BudgetError
from dispatcher_sdk.application_budget_status import observe_budget


class BudgetObservationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'budget.db'
        self.now = 10
        self.ledger = ApplicationBudget(self.path, clock=lambda: self.now)
        self.ledger.create('run', 'agent', 'tokens', allowance=5, deadline=20)

    def status(self, amount=1):
        return observe_budget(self.ledger, 'run', 'agent', 'tokens', amount=amount)

    def test_observation_never_authorizes_and_cannot_replace_reservation(self):
        available = self.status(5)
        self.assertEqual(available['status'], 'available')
        self.assertFalse(available['spend_authorized'])
        self.ledger.reserve('run', 'agent', 'tokens', 'call', amount=4)
        self.assertEqual(self.status()['status'], 'pending')
        self.ledger.settle('run', 'agent', 'tokens', 'call', actual=None)
        self.assertEqual(self.status()['status'], 'unknown')
        self.assertIsNone(self.status()['available'])
        self.ledger.reconcile('run', 'agent', 'tokens', 'call', actual=4)
        self.assertEqual(self.status(2)['status'], 'exhausted')
        self.assertEqual(self.status(1)['status'], 'available')

    def test_clock_watermark_survives_restart_and_backwards_clock(self):
        self.now = 20
        self.assertEqual(self.status()['status'], 'expired')
        self.now = 11
        self.ledger = ApplicationBudget(self.path, clock=lambda: self.now)
        result = self.status()
        self.assertEqual((result['status'], result['deadline'], result['observed_at']), ('expired', 20, 20))
        with self.assertRaises(BudgetError):
            self.ledger.reserve('run', 'agent', 'tokens', 'new', amount=1)

    def test_unknown_and_capacity_are_scoped(self):
        self.assertEqual(observe_budget(self.ledger, 'missing', 'agent', 'tokens', amount=1)['status'], 'unknown')
        with patch('dispatcher_sdk.application_budget._MAX_RESERVATIONS', 1):
            self.ledger.reserve('run', 'agent', 'tokens', 'call', amount=1)
            self.ledger.settle('run', 'agent', 'tokens', 'call', actual=1)
            self.assertEqual(self.status()['status'], 'capacity_exhausted')
        self.ledger.create('run', 'other', 'tokens', allowance=5, deadline=20)
        self.assertEqual(observe_budget(self.ledger, 'run', 'other', 'tokens', amount=1)['status'], 'available')

    def test_malformed_facts_unknown_preserve_deadline_watermark(self):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO application_reservations VALUES('run','agent','tokens','bad',1,'invalid',NULL)")
        self.now = 21
        self.assertEqual(self.status()['status'], 'unknown')
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM application_reservations WHERE request_id='bad'")
        self.now = 11
        self.assertEqual(self.status()['status'], 'expired')

    def test_archived_usage_remains_visible(self):
        self.ledger.reserve('run', 'agent', 'tokens', 'old', amount=4)
        self.ledger.settle('run', 'agent', 'tokens', 'old', actual=3)
        self.ledger.archive_settled('run', 'agent', 'tokens')
        result = self.status(3)
        self.assertEqual((result['status'], result['spent'], result['available']), ('exhausted', 3, 2))


if __name__ == '__main__':
    unittest.main()
