"""Exact multi-execution budget authority for a real protected child submit."""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.execution_kernel._sqlite_execution import encode_json


def command(identifier):
    return ExecutionCommandV2(execution_id=identifier, idempotency_key='key:' + identifier,
        registry_revision='test', correlation_id='run', causation_id=None, handler_id='test',
        handler_contract_version=1, retry_policy=RetryPolicy(), timeout_seconds=10, payload={'value': 1})


class ChildBudgetAdmissionsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.expiry = time.time() + 300
        self.initial = {}
        self.declaration = {}
        self.proofs = []
        self.form = 'list'
        self.scope = {'owner': 'app', 'unit': 'token', 'source_id': 'ledger'}

        def verifier(credential):
            if credential == 'manager':
                return {'principal': 'manager', 'expires_at': self.expiry,
                        'permissions': [('run', 'kernel:manage_authority')]}
            if credential == 'bind':
                return {'principal': 'manager', 'expires_at': self.expiry,
                        'permissions': [('run', 'kernel:bind_initial')],
                        'initial_admission_receipt': dict(self.initial)}
            if credential == 'declaration':
                return {'principal': 'manager', 'expires_at': self.expiry,
                        'permissions': [('run', 'kernel:declare_budget')],
                        'budget_declaration': deepcopy(self.declaration)}
            if credential != 'worker':
                raise ValueError('unknown credential')
            result = {'principal': 'worker', 'expires_at': self.expiry, 'run_id': 'run',
                      'generation': 0, 'control_epoch': 0,
                      'permissions': [('run', 'kernel:' + action) for action in
                                      ('worker', 'submit', 'claim', 'start', 'child', 'work', 'budget')],
                      'global_admission': {'open': True, 'run_id': 'run', 'generation': 0,
                                           'control_epoch': 0, 'orchestrator_receipt': dict(self.initial)}}
            if self.form == 'list':
                result['budget_admissions'] = deepcopy(self.proofs)
            elif self.form == 'single':
                result['budget_admission'] = deepcopy(self.proofs[0])
            elif self.form == 'both':
                result['budget_admission'] = deepcopy(self.proofs[0])
                result['budget_admissions'] = deepcopy(self.proofs)
            return result

        path = Path(directory.name) / 'kernel.sqlite3'
        self.manager = SQLiteKernel(path, authority_verifier=verifier, worker_credential='manager')
        self.worker = SQLiteKernel(path, authority_verifier=verifier, worker_credential='worker')
        self.addCleanup(self.manager.close)
        self.addCleanup(self.worker.close)
        self.manager.register_run_control('run', max_claims=10, deadline_at=self.expiry)
        self.manager.protect_run_authority('run', generation=0, expected_epoch=0, worker_credential='worker')
        self.initial.update(operation_id='initial', run_id='run', generation=0, control_epoch=0,
                            state='active', committed_at=time.time(), kernel_store_id=self.manager.kernel_store_identity(),
                            orchestrator_store_id='orch', orchestrator_incarnation='incarnation')
        self.manager.bind_initial_admission('bind', expected_receipt=dict(self.initial))
        # Public activation is intentionally closed; this models an existing active protected run.
        with self.manager._transaction() as (connection, _):
            connection.execute("UPDATE kernel_run_controls SET state='active' WHERE run_id='run'")
        self.parent, self.child = command('sdk-managed:parent'), command('sdk-managed:child')
        self.worker.submit_managed(self.parent, run_id='run', generation=0)
        self.lease = self.worker.claim_and_start('worker', execution_id=self.parent.execution_id)
        self.envelope = self.worker.prepare_execution_budget(self.lease).enter_handler(10, origin_id='execution:sdk-managed:parent')
        self.worker.record_execution_budget(self.lease, self.envelope)
        self.policy = {'policy_id': 'policy', 'decision_id': 'decision', 'run_id': 'run', 'generation': 0,
                       'kernel_store_id': self.manager.kernel_store_identity(), 'orchestrator_store_id': 'orch',
                       'orchestrator_incarnation': 'incarnation', 'scopes': [self.scope]}
        with self.manager._transaction() as (connection, _):
            connection.execute('INSERT INTO kernel_budget_policies VALUES(?,?,?)', ('run', 0, encode_json(self.policy)))
        for work in (self.parent, self.child):
            self.declaration = {key: value for key, value in self.policy.items() if key != 'scopes'}
            self.declaration.update(execution_id=work.execution_id, command=work.to_dict(), scopes=[self.scope])
            self.manager.declare_budget_dependencies('declaration', expected_declaration=deepcopy(self.declaration))
            proof = {key: value for key, value in self.declaration.items() if key != 'command'}
            proof.update(allowed=True, expires_at=self.expiry)
            self.proofs.append(proof)

    def submit(self):
        return self.worker.submit_child(self.child, self.lease, self.envelope)

    def assert_refused_without_child(self):
        with self.assertRaises(StorageIsolationError):
            self.submit()
        with self.worker._transaction() as (connection, _):
            self.assertIsNone(connection.execute('SELECT 1 FROM kernel_executions WHERE execution_id=?',
                                                (self.child.execution_id,)).fetchone())

    def test_both_dependent_parent_and_child_are_admitted_and_replay(self):
        self.assertEqual(self.submit().execution_id, self.child.execution_id)
        self.assertEqual(self.submit().execution_id, self.child.execution_id)

    def test_missing_duplicate_wrong_and_expired_entries_fail_closed(self):
        original = deepcopy(self.proofs)
        cases = [original[:1], [original[0], original[0], original[1]],
                 [original[0], dict(original[1], policy_id='other')],
                 [original[0], dict(original[1], expires_at=time.time() - 1)],
                 [dict(original[0], allowed=False), original[1]]]
        for proofs in cases:
            with self.subTest(proofs=proofs):
                self.proofs = deepcopy(proofs)
                self.assert_refused_without_child()
        self.proofs = original
        self.form = 'both'
        self.assert_refused_without_child()

    def test_legacy_singleton_authorizes_exactly_one_dependent_execution(self):
        # Parent alone remains dependent; child has an explicit empty dependency list.
        self.child = command('sdk-managed:independent-child')
        self.declaration = dict(self.declaration, execution_id=self.child.execution_id,
                                command=self.child.to_dict(), scopes=[])
        self.manager.declare_budget_dependencies('declaration', expected_declaration=deepcopy(self.declaration))
        self.form = 'single'
        self.assertEqual(self.submit().execution_id, self.child.execution_id)


if __name__ == '__main__':
    unittest.main()
