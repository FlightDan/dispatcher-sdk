"""Controlled application decisions with synthetic host authority and no hashing."""
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.orchestrator import Orchestrator, OrchestrationError, RevisionConflict
from dispatcher_sdk.orchestrator import engine


class _Kernel:
    def __init__(self):
        self.identity = 'kernel-original'
        self.gate = {'state': 'active', 'generation': 1, 'control_epoch': 4}
    def kernel_store_identity(self):
        return self.identity
    def get_run_control(self, run_id):
        return dict(self.gate)


class ControlledApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        patch('hashlib.sha256', side_effect=AssertionError('hash prohibited')).start()
        patch('hashlib.sha1', side_effect=AssertionError('hash prohibited')).start()
        patch.object(engine, 'digest', side_effect=lambda obj: json.dumps(obj, sort_keys=True)).start()
        values = {}
        def object_id(value):
            if value not in values:
                values[value] = format(len(values) + 1, '064x')
            return values[value]
        patch('dispatcher_sdk.content._object_digest', side_effect=object_id).start()
        self.kernel = _Kernel()
        self.permissions = [('run', 'apply_operations')]
        self.lease = {}
        self.sdk = Orchestrator(Path(self.tmp.name) / 'runs.db', self.kernel, clock=lambda: 100.,
            control_verifier=lambda _: {'principal': 'host', 'permissions': list(self.permissions)},
            control_lease_verifier=lambda _: dict(self.lease))
        self.sdk.create_run('run', command_id='create')
        with self.sdk._transaction() as db:
            state = self.sdk._load(db, 'run')
            state['generation'] = 1
            state['revision'] = 1
            self.sdk._save(db, state)
            identity = db.execute('SELECT store_id,incarnation FROM sdk_storage_identity').fetchone()
            orch, incarnation = identity
            expected = {'operation_id': 'resume', 'run_id': 'run', 'kernel_store_id': 'kernel-original',
                        'orchestrator_store_id': orch, 'orchestrator_incarnation': incarnation}
            self.lease = {**expected, 'lease_id': 'lease', 'lease_fence': 1, 'expires_at': 200.,
                          'held': True, 'scope': 'resume_cancel_revoke_through_commit'}
            envelope = {**expected, 'lease_id': 'lease', 'lease_fence': 1}
            remote = {'kind': 'revision_resume', 'decision': {**expected, 'generation': 1, 'target_control_epoch': 4}}
            local = {**expected, 'state': 'active', 'generation': 1, 'control_epoch': 4}
            db.execute('INSERT INTO sdk_managed_runs VALUES(?,?,?,?,?,?,?,?,?,?)',
                       ('run', 'register', 'recorded', 'active', 4, 1, 7, 200., 100., 100.))
            db.execute('INSERT INTO sdk_control_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       ('decision', 'run', 'pause', 0, 2, 0, 7, 200., orch, incarnation,
                        'kernel-original', 'host', None, 'prepared', None, None, None, None, None, 100., 100.))
            db.execute('INSERT INTO sdk_revision_resumes VALUES(?,?,?,?,?,?)',
                       ('resume', 'decision', json.dumps(envelope), json.dumps(remote), json.dumps(local), 100.))

    def apply(self, **changes):
        args = dict(command_id='decision-1', expected_revision=1, expected_generation=1,
                    expected_control_epoch=4, source_resume_operation_id='resume',
                    credential='operator', lease_credential='lease',
                    operations=[{'kind': 'wait', 'wait_id': 'w'}], application_state={'step': 1},
                    subscription='consumer', expected_cursor=0, advance_to=1)
        args.update(changes)
        return self.sdk.apply_managed_operations('run', **args)

    def test_composed_commit_and_idempotent_replay(self):
        first = self.apply()
        self.assertEqual(first['revision'], 2)
        self.assertEqual(first['application_state'], {'step': 1})
        self.assertEqual(first['waits']['w']['state'], 'open')
        self.assertEqual(self.apply(), first)
        with contextlib.closing(self.sdk._connect()) as db, db:
            self.assertEqual(db.execute('SELECT cursor FROM sdk_subscriptions WHERE run_id=? AND name=?', ('run', 'consumer')).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM sdk_commands WHERE run_id=? AND command_id=?', ('run', 'decision-1')).fetchone()[0], 1)

    def test_rejected_authority_and_stale_sources_do_not_commit(self):
        cases = ('authority', 'lease', 'identity', 'epoch', 'generation', 'cursor')
        for case in cases:
            with self.subTest(case=case):
                permissions, lease, identity, gate = list(self.permissions), dict(self.lease), self.kernel.identity, dict(self.kernel.gate)
                try:
                    if case == 'authority': self.permissions.clear()
                    if case == 'lease': self.lease['expires_at'] = 99.
                    if case == 'identity': self.kernel.identity = 'replacement'
                    if case == 'epoch': self.kernel.gate['control_epoch'] = 5
                    if case == 'generation': self.kernel.gate['generation'] = 2
                    changes = {'expected_cursor': 1} if case == 'cursor' else {}
                    with self.assertRaises((OrchestrationError, RevisionConflict)):
                        self.apply(**changes)
                    self.assertEqual(self.sdk.get_run('run')['revision'], 1)
                    with contextlib.closing(self.sdk._connect()) as db, db:
                        self.assertIsNone(db.execute('SELECT 1 FROM sdk_subscriptions WHERE run_id=?', ('run',)).fetchone())
                        self.assertIsNone(db.execute('SELECT 1 FROM sdk_commands WHERE run_id=? AND command_id=?', ('run', 'decision-1')).fetchone())
                finally:
                    self.permissions[:] = permissions
                    self.lease.clear(); self.lease.update(lease)
                    self.kernel.identity = identity
                    self.kernel.gate = gate

    def test_replay_requires_live_authority(self):
        original = self.apply()
        self.lease['held'] = False
        with self.assertRaises(OrchestrationError):
            self.apply()
        self.assertEqual(self.sdk.get_command_receipt('run', 'decision-1'), original)

    def test_lease_revocation_before_commit_rolls_back_decision_and_cursor(self):
        calls = []
        def verifier(_):
            calls.append(None)
            return {**self.lease, 'held': len(calls) == 1}
        self.sdk.control_lease_verifier = verifier
        with self.assertRaises(OrchestrationError):
            self.apply()
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.sdk.get_run('run')['revision'], 1)
        with contextlib.closing(self.sdk._connect()) as db, db:
            self.assertIsNone(db.execute('SELECT 1 FROM sdk_subscriptions WHERE run_id=?', ('run',)).fetchone())
            self.assertIsNone(db.execute('SELECT 1 FROM sdk_commands WHERE run_id=? AND command_id=?', ('run', 'decision-1')).fetchone())


if __name__ == '__main__':
    unittest.main()
