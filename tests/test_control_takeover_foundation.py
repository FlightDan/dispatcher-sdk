"""Kernel takeover protocol with a synthetic host verifier, not host isolation."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from dispatcher_sdk.execution_kernel._sqlite_schema import KERNEL_SCHEMA_V9, upgrade_kernel_schema_v9_to_v10, upgrade_kernel_schema_v10_to_v11, upgrade_kernel_schema_v11_to_v12
from dispatcher_sdk.execution_kernel._sqlite_base import encode_json, SQLiteBase
from dispatcher_sdk.execution_kernel.control_takeover import ControlTakeoverMixin
from dispatcher_sdk.execution_kernel.errors import CASConflictError, StorageIsolationError
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel


class Participant(ControlTakeoverMixin):
    _number = staticmethod(SQLiteBase._number)
    def __init__(self, path, claim):
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.claim = claim
        self.calls = 0
        self.fail_second = False
        self.now = 1.0
        self.inspection = None
    def _authority_verifier(self, credential):
        self.calls += 1
        if credential != 'proof' or (self.fail_second and self.calls % 2 == 0):
            raise ValueError('revoked')
        return {'principal': 'host', 'expires_at': 100.0,
                'permissions': [('run', 'kernel:takeover_control'), ('run', 'kernel:inspect_control')],
                'control_takeover': self.claim, 'control_takeover_inspection': self.inspection}
    @contextmanager
    def _transaction(self):
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield self.connection, self.now
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
    def _advance_clock(self, connection):
        return self.now
    def _has_unresolved_control_barrier(self, connection, run_id):
        return False


class TakeoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'kernel.sqlite'
        self.db = sqlite3.connect(self.path)
        self.db.executescript(KERNEL_SCHEMA_V9)
        upgrade_kernel_schema_v9_to_v10(self.db)
        upgrade_kernel_schema_v10_to_v11(self.db)
        upgrade_kernel_schema_v11_to_v12(self.db)
        self.db.execute("UPDATE kernel_store_identity SET store_id='kernel' WHERE singleton=1")
        self.db.execute("INSERT INTO kernel_run_controls VALUES('run',4,2,'paused',10,3,90.0)")
        self.db.execute("INSERT INTO kernel_run_authorities VALUES('run',2,4,'worker',80.0,NULL)")
        installation = {'decision': {'kernel_store_id': 'kernel', 'orchestrator_store_id': 'orch',
                                     'orchestrator_incarnation': 'inc', 'target_generation': 2,
                                     'run_id': 'run', 'barrier_operation_id': 'barrier', 'decision_id': 'revision'},
                        'worker_principal': 'worker', 'worker_expires_at': 80.0}
        self.db.execute('INSERT INTO kernel_revision_installs VALUES(?,?,?,?)',
                        ('revision', 'run', 'barrier', encode_json(installation)))
        pause = {'kind': 'local_paused', 'barrier_operation_id': 'barrier'}
        self.db.execute('INSERT INTO kernel_control_pause_receipts VALUES(?,?,?,?,?)', ('complete', 'run', 4, 2, encode_json(pause)))
        self.db.commit()
        self.decision = {'operation_id': 'activate', 'run_id': 'run', 'kernel_store_id': 'kernel',
                         'orchestrator_store_id': 'orch', 'orchestrator_incarnation': 'inc', 'generation': 2,
                         'expected_control_epoch': 4, 'decision_id': 'revision', 'barrier_operation_id': 'barrier',
                         'completion_operation_id': 'complete', 'kernel_install_receipt': installation,
                         'lease_id': 'old', 'lease_fence': 1, 'lease_expires_at': 10.0}
        self.claim = {'takeover_id': 'take1', 'phase': 'activation', 'operation_id': 'activate', 'run_id': 'run',
                      'kernel_store_id': 'kernel', 'orchestrator_store_id': 'orch', 'orchestrator_incarnation': 'inc',
                      'generation': 2, 'control_epoch': 4, 'original_decision': self.decision, 'original_receipt': None,
                      'previous_lease_id': 'old', 'previous_fence': 1, 'new_lease_id': 'new', 'new_fence': 2,
                      'lease_expires_at': 50.0, 'lease_held': True, 'old_holder_excluded': True,
                      'max_claims': 10, 'claims_used': 3, 'deadline_at': 90.0}
        self.participant = Participant(self.path, self.claim)

    def tearDown(self):
        self.participant.connection.close()
        self.db.close()
        self.temp.cleanup()

    def test_exact_reopen_replay_and_stale_decision(self):
        receipt = self.participant.takeover_control_lease('proof', expected_takeover=self.claim)
        self.participant.connection.close()
        self.participant = Participant(self.path, self.claim)
        self.assertEqual(receipt, self.participant.takeover_control_lease('proof', expected_takeover=self.claim))
        updated = dict(self.decision, lease_id='new', lease_fence=2, lease_expires_at=50.0)
        self.assertTrue(self.participant._verify_effective_control_decision(self.participant.connection, 'activation', updated))
        with self.assertRaises(CASConflictError):
            self.participant._verify_effective_control_decision(self.participant.connection, 'activation', self.decision)
        with self.assertRaises(CASConflictError):
            self.participant._verify_effective_control_decision(self.participant.connection, 'activation', dict(updated, generation=3))

    def test_revoked_host_rolls_back(self):
        self.participant.fail_second = True
        with self.assertRaises(StorageIsolationError):
            self.participant.takeover_control_lease('proof', expected_takeover=self.claim)
        self.assertEqual(0, self.db.execute('SELECT count(*) FROM kernel_control_takeovers').fetchone()[0])

    def test_sequential_takeover_after_previously_absent_receipt_commits(self):
        self.participant.takeover_control_lease('proof', expected_takeover=self.claim)
        updated = dict(self.decision, lease_id='new', lease_fence=2, lease_expires_at=50.0)
        original = {'kind': 'revision_activation', 'decision': updated, 'state': 'paused'}
        self.db.execute('INSERT INTO kernel_activation_receipts VALUES(?,?,?)',
                        ('activate', 'run', encode_json(original)))
        self.db.commit()
        self.assertEqual('take1', self.participant.takeover_control_lease('proof', expected_takeover=self.claim)['claim']['takeover_id'])
        successor = copy.deepcopy(self.claim)
        successor.update(takeover_id='take2', original_receipt=original, previous_lease_id='new', previous_fence=2,
                         new_lease_id='newer', new_fence=3)
        self.participant.claim = successor
        self.participant.takeover_control_lease('proof', expected_takeover=successor)
        self.assertTrue(self.participant._verify_effective_control_decision(
            self.participant.connection, 'activation', dict(updated, lease_id='newer', lease_fence=3)))

    def test_real_kernel_three_handoffs_preserve_issuing_receipt(self):
        # The verifier is synthetic; Kernel storage, transactions, activation,
        # authorizer and the later reopened Kernel are real.
        decision = dict(self.decision, orchestrator_install_receipt={'state': 'paused'}, lease_held=True)
        claim = copy.deepcopy(self.claim)
        claim['original_decision'] = decision
        verified = {'principal': 'host', 'expires_at': 100.0,
                    'permissions': [('run', 'kernel:takeover_control'), ('run', 'kernel:activate_revision')]}
        def verify(_credential):
            return verified
        kernel = SQLiteKernel(self.path, now=lambda: 1.0, authority_verifier=verify)
        try:
            verified['control_takeover'] = claim
            first = kernel.takeover_control_lease('proof', expected_takeover=claim)
            activated = dict(decision, lease_id='new', lease_fence=2, lease_expires_at=50.0)
            verified['activation'] = activated
            receipt = kernel.activate_revision('proof', expected_decision=activated)
            second = copy.deepcopy(claim)
            second.update(takeover_id='take2', original_receipt=receipt, previous_lease_id='new', previous_fence=2,
                          new_lease_id='newer', new_fence=3)
            verified['control_takeover'] = second
            kernel.takeover_control_lease('proof', expected_takeover=second)
            kernel.close()
            kernel = SQLiteKernel(self.path, now=lambda: 1.0, authority_verifier=verify)
            third = copy.deepcopy(second)
            third.update(takeover_id='take3', previous_lease_id='newer', previous_fence=3,
                         new_lease_id='newest', new_fence=4)
            verified['control_takeover'] = third
            kernel.takeover_control_lease('proof', expected_takeover=third)
            current = dict(decision, lease_id='newest', lease_fence=4, lease_expires_at=50.0)
            verified['activation'] = current
            self.assertEqual(receipt, kernel.activate_revision('proof', expected_decision=current))
            self.assertEqual(2, receipt['decision']['lease_fence'])
            self.assertEqual('take1', first['claim']['takeover_id'])
            stale = copy.deepcopy(third)
            stale.update(takeover_id='bad', previous_lease_id='newer', previous_fence=3,
                         new_lease_id='invalid', new_fence=5)
            verified['control_takeover'] = stale
            with self.assertRaises(CASConflictError):
                kernel.takeover_control_lease('proof', expected_takeover=stale)
            self.assertFalse(kernel._verify_historical_control_decision(
                kernel._connection, 'activation', decision, dict(activated, lease_fence=9)))
            self.assertFalse(kernel._verify_historical_control_decision(
                kernel._connection, 'activation', decision, dict(activated, generation=3)))
        finally:
            kernel.close()

    def test_real_kernel_newer_lease_for_another_operation(self):
        # A synthetic host verifier supplies the exclusive lease facts.
        verified = {'principal': 'host', 'expires_at': 100.0,
                    'permissions': [('run', 'kernel:takeover_control')]}
        kernel = SQLiteKernel(self.path, now=lambda: 1.0, authority_verifier=lambda _: verified)
        try:
            verified['control_takeover'] = self.claim
            kernel.takeover_control_lease('proof', expected_takeover=self.claim)
            def other(lease_id, fence, target_fence):
                claim = copy.deepcopy(self.claim)
                claim.update(takeover_id='other', operation_id='activate-other',
                             previous_lease_id=lease_id, previous_fence=fence,
                             new_lease_id='next', new_fence=target_fence)
                claim['original_decision'].update(operation_id='activate-other', lease_id=lease_id, lease_fence=fence)
                return claim
            # The latest durable Run fence is 2. An older predecessor or a
            # different lease claiming the same fence is never accepted.
            for claim in (other('stale', 1, 4), other('impostor', 2, 4)):
                verified['control_takeover'] = claim
                with self.assertRaises(CASConflictError):
                    kernel.takeover_control_lease('proof', expected_takeover=claim)
            claim = other('unrelated-live', 3, 4)
            verified['control_takeover'] = claim
            receipt = kernel.takeover_control_lease('proof', expected_takeover=claim)
            self.assertEqual(('unrelated-live', 3, 4),
                             (receipt['claim']['previous_lease_id'], receipt['claim']['previous_fence'], receipt['claim']['new_fence']))
            # The previous operation cannot advance from its now stale f2.
            old = copy.deepcopy(self.claim)
            old.update(takeover_id='stale-first', previous_lease_id='new', previous_fence=2,
                       new_lease_id='invalid', new_fence=5)
            verified['control_takeover'] = old
            with self.assertRaises(CASConflictError):
                kernel.takeover_control_lease('proof', expected_takeover=old)
        finally:
            kernel.close()

    def test_renewed_lease_retrieves_original_fact_after_business_progress(self):
        receipt = self.participant.takeover_control_lease('proof', expected_takeover=self.claim)
        self.db.execute("UPDATE kernel_run_controls SET claims_used=4, state='active', control_epoch=5 WHERE run_id='run'")
        self.db.execute("UPDATE kernel_run_authorities SET revoked_at=30.0 WHERE run_id='run'")
        self.db.commit()
        renewed = copy.deepcopy(self.claim)
        renewed['lease_expires_at'] = 95.0
        self.participant.claim = renewed
        self.participant.now = 81.0
        self.assertEqual(receipt, self.participant.takeover_control_lease('proof', expected_takeover=renewed))
        altered = copy.deepcopy(renewed)
        altered['claims_used'] = 4
        self.participant.claim = altered
        with self.assertRaises(CASConflictError):
            self.participant.takeover_control_lease('proof', expected_takeover=altered)
        self.participant.claim = self.claim
        with self.assertRaises(StorageIsolationError):
            self.participant.takeover_control_lease('proof', expected_takeover=self.claim)

    def test_inspection_under_successor_is_read_only_and_fails_closed(self):
        inspection = {'original_takeover': copy.deepcopy(self.claim), 'current_lease_id': 'later',
                      'current_lease_fence': 3, 'current_lease_expires_at': 95.0,
                      'lease_held': True, 'old_holder_excluded': True}
        self.participant.inspection = inspection
        self.assertIsNone(self.participant.inspect_control_takeover('proof', expected_inspection=inspection))
        receipt = self.participant.takeover_control_lease('proof', expected_takeover=self.claim)
        self.participant.now = 81.0
        self.assertEqual(receipt, self.participant.inspect_control_takeover('proof', expected_inspection=inspection))
        changed = copy.deepcopy(inspection)
        changed['original_takeover']['deadline_at'] = 91.0
        self.participant.inspection = changed
        with self.assertRaises(CASConflictError):
            self.participant.inspect_control_takeover('proof', expected_inspection=changed)
        self.participant.inspection = inspection
        self.participant.calls = 0
        self.participant.fail_second = True
        with self.assertRaises(StorageIsolationError):
            self.participant.inspect_control_takeover('proof', expected_inspection=inspection)
        self.assertEqual(1, self.db.execute('SELECT count(*) FROM kernel_control_takeovers').fetchone()[0])

    def test_budget_and_identity_fail_closed(self):
        for key, value in [('deadline_at', 91.0), ('claims_used', 4), ('kernel_store_id', 'other')]:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.claim)
                changed[key] = value
                self.participant.claim = changed
                with self.assertRaises((CASConflictError, ValueError)):
                    self.participant.takeover_control_lease('proof', expected_takeover=changed)
        self.assertEqual(0, self.db.execute('SELECT count(*) FROM kernel_control_takeovers').fetchone()[0])


if __name__ == '__main__':
    unittest.main()
