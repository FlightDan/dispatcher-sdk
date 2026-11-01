"""Direct Kernel coverage for host-declared managed child dependencies."""
import json
from contextlib import nullcontext
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import CASConflictError, ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.children import ChildExecutionError, ChildService, HandlerChildren
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.execution_kernel._sqlite_execution import encode_json


def command(execution_id):
    return ExecutionCommandV2(execution_id=execution_id, idempotency_key='key:' + execution_id,
        registry_revision='test', correlation_id='run', causation_id=None, handler_id='test',
        handler_contract_version=1, retry_policy=RetryPolicy(), timeout_seconds=10, payload={'value': 1})


class Window:
    stop = None
    _pending_sample = None
    def timeout(self): return 1.0
    def remaining(self): return 1.0
    def project(self): return nullcontext()
    def _adopt_sample_owner(self, _error): pass


class ChildBudgetDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.claim = {}
        self.expiry = time.time() + 300
        def verifier(credential):
            if credential != 'valid':
                raise ValueError('credential must stay private')
            return {'principal': 'host', 'expires_at': self.expiry,
                    'permissions': [('run', 'kernel:declare_budget')],
                    'budget_declaration': dict(self.claim)}
        self.kernel = SQLiteKernel(Path(self.directory.name) / 'kernel.sqlite3', authority_verifier=verifier)
        self.addCleanup(self.kernel.close)
        self.kernel.register_run_control('run', max_claims=10, deadline_at=self.expiry)
        self.kernel.set_run_control('run', expected_epoch=0, generation=0, state='active')
        parent = command('sdk-managed:parent')
        self.kernel.submit_managed(parent, run_id='run', generation=0)
        self.lease = self.kernel.claim_and_start('worker', execution_id=parent.execution_id)
        self.envelope = self.kernel.prepare_execution_budget(self.lease).enter_handler(10, origin_id='execution:sdk-managed:parent')
        self.kernel.record_execution_budget(self.lease, self.envelope)
        self.policy = {'policy_id': 'policy', 'decision_id': 'decision', 'run_id': 'run', 'generation': 0,
            'kernel_store_id': self.kernel.kernel_store_identity(), 'orchestrator_store_id': 'orchestrator',
            'orchestrator_incarnation': 'incarnation', 'scopes': [{'owner': 'app', 'unit': 'token', 'source_id': 'ledger'}]}
        with self.kernel._transaction() as (connection, _):
            connection.execute('INSERT INTO kernel_budget_policies VALUES(?,?,?)', ('run', 0, encode_json(self.policy)))
        self.service = object.__new__(ChildService)
        self.service.runtime = SimpleNamespace(kernel=self.kernel)
        self.service.budget_declaration_provider = None
        self.child = command('sdk-managed:child')
        self.claim.update(run_id='run', generation=0, policy_id='policy', decision_id='decision',
            kernel_store_id=self.policy['kernel_store_id'], orchestrator_store_id='orchestrator',
            orchestrator_incarnation='incarnation', execution_id=self.child.execution_id,
            command=self.child.to_dict(), scopes=[])

    def test_host_declaration_is_required_exact_authenticated_and_replayable(self):
        window = Window()
        self.service._declare_child_budget(self.child, self.lease, window)
        with self.assertRaises(CASConflictError):
            self.kernel.submit_child(self.child, self.lease, self.envelope)
        altered = dict(self.claim, command=dict(self.claim['command'], payload={'value': 2}))
        self.service.budget_declaration_provider = lambda **_: ('valid', altered)
        with self.assertRaises(ChildExecutionError):
            self.service._declare_child_budget(self.child, self.lease, window)
        self.service.budget_declaration_provider = lambda **_: ('invalid', dict(self.claim))
        with self.assertRaisesRegex(ChildExecutionError, 'authority'):
            self.service._declare_child_budget(self.child, self.lease, window)
        with self.assertRaises(CASConflictError):
            self.kernel.submit_child(self.child, self.lease, self.envelope)
        observed = []
        def provider(**kwargs):
            observed.append(kwargs)
            return 'valid', dict(self.claim)
        self.service.budget_declaration_provider = provider
        self.service._declare_child_budget(self.child, self.lease, window)
        self.service._declare_child_budget(self.child, self.lease, window)
        self.assertEqual(observed[0]['command'], self.child.to_dict())
        self.assertEqual(observed[0]['parent_lease'], self.lease)
        snapshot = self.kernel.submit_child(self.child, self.lease, self.envelope)
        self.assertEqual(snapshot.execution_id, self.child.execution_id)
        with self.kernel._transaction() as (connection, _):
            declaration = json.loads(connection.execute('SELECT declaration_json FROM kernel_budget_dependencies WHERE execution_id=?', (self.child.execution_id,)).fetchone()[0])
        self.assertEqual(declaration, self.claim)

    def test_expired_host_callback_cannot_persist_declaration(self):
        class Expired(Window):
            count = 0
            def timeout(self):
                self.count += 1
                if self.count == 2:
                    raise TimeoutError('original window elapsed')
                return 1.0
        self.service.budget_declaration_provider = lambda **_: ('valid', dict(self.claim))
        with self.assertRaises(TimeoutError):
            self.service._declare_child_budget(self.child, self.lease, Expired())
        with self.assertRaises(CASConflictError):
            self.kernel.submit_child(self.child, self.lease, self.envelope)

    def test_provider_errors_reach_child_caller_without_credential_details(self):
        secret = 'private worker credential'
        cases = [
            (ChildExecutionError('child_budget_exhausted', secret), 'child_budget_exhausted'),
            (StorageIsolationError(secret), 'child_budget_authority_unknown'),
            (CASConflictError(secret), 'child_budget_conflict'),
            (ValueError(secret), 'child_budget_declaration_unavailable'),
        ]
        row = {'action': 'run', 'parent_lease_json': json.dumps(self.lease.to_dict()),
               'budget_json': json.dumps(self.envelope.to_dict()), 'parent_execution_id': self.lease.execution_id,
               'child_execution_id': self.child.execution_id, 'command_json': json.dumps(self.child.to_dict()),
               'depth': 1, 'request_id': 'request', 'wait_id': 'wait'}
        for failure, expected in cases:
            with self.subTest(expected=expected):
                recorded = []
                store = SimpleNamespace(attach=lambda *_: None, finish=lambda _row, state, **kw: recorded.append((state, kw)))
                self.service.store = store
                self.service._stop = threading.Event()
                self.service.max_depth = 1
                def provider(**_):
                    raise failure
                self.service.budget_declaration_provider = provider
                window = Window()
                window.envelope = self.envelope
                with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                     patch('dispatcher_sdk.execution_kernel.children._wait_parent_entry'), \
                     patch('dispatcher_sdk.execution_kernel.children._inspect_parent_revocation'), \
                     patch.object(self.service, '_cancel', return_value=None):
                    self.service._execute(row)
                state, result = recorded[0]
                self.assertEqual(state, 'failed')
                self.assertEqual(result['error']['code'], expected)
                self.assertNotIn(secret, json.dumps(result))
                caller = object.__new__(HandlerChildren)
                caller.command = self.child
                caller.store = SimpleNamespace(bound=lambda _window: nullcontext(), request=lambda *_: {'state': state, 'response_json': None,
                    'error_json': json.dumps(result['error']), 'child_execution_id': self.child.execution_id})
                caller._active = lambda *_args, **_kwargs: None
                caller.kernel = self.kernel
                with self.assertRaises(ChildExecutionError) as raised:
                    caller._await_window(row, window)
                self.assertEqual(raised.exception.code, expected)
                self.assertNotIn(secret, str(raised.exception))

    def test_kernel_declaration_denial_and_conflict_reach_caller(self):
        window = Window()
        window.envelope = self.envelope
        self.service.budget_declaration_provider = lambda **_: ('invalid', dict(self.claim))
        cases = [('child_budget_authority_unknown', self.service.budget_declaration_provider)]
        self.service.budget_declaration_provider = lambda **_: ('valid', dict(self.claim))
        self.service._declare_child_budget(self.child, self.lease, window)
        self.claim['scopes'] = [self.policy['scopes'][0]]
        cases.append(('child_budget_conflict', lambda **_: ('valid', dict(self.claim))))
        row = {'action': 'run', 'parent_lease_json': json.dumps(self.lease.to_dict()),
               'budget_json': json.dumps(self.envelope.to_dict()), 'parent_execution_id': self.lease.execution_id,
               'child_execution_id': self.child.execution_id, 'command_json': json.dumps(self.child.to_dict()),
               'depth': 1, 'request_id': 'request', 'wait_id': 'wait'}
        for expected, provider in cases:
            with self.subTest(expected=expected):
                recorded = []
                self.service.store = SimpleNamespace(attach=lambda *_: None,
                    finish=lambda _row, state, **kw: recorded.append((state, kw)))
                self.service._stop = threading.Event()
                self.service.max_depth = 1
                self.service.budget_declaration_provider = provider
                with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                     patch('dispatcher_sdk.execution_kernel.children._wait_parent_entry'), \
                     patch('dispatcher_sdk.execution_kernel.children._inspect_parent_revocation'), \
                     patch.object(self.service, '_cancel', return_value=None):
                    self.service._execute(row)
                state, result = recorded[0]
                caller = object.__new__(HandlerChildren)
                caller.command, caller.kernel = self.child, self.kernel
                caller._active = lambda *_args, **_kwargs: None
                caller.store = SimpleNamespace(bound=lambda _window: nullcontext(), request=lambda *_: {
                    'state': state, 'response_json': None, 'error_json': json.dumps(result['error']),
                    'child_execution_id': self.child.execution_id})
                with self.assertRaises(ChildExecutionError) as raised:
                    caller._await_window(row, window)
                self.assertEqual(raised.exception.code, expected)

    def test_pending_revocation_unknown_survives_wait_timeout(self):
        class Store:
            source_id = 'source'
            error = None
            def attach(self, *_): pass
            def bound(self, _window): return nullcontext()
            def transaction(self):
                def execute(_sql, params): self.error = params[0]
                return nullcontext((SimpleNamespace(execute=execute), time.time()))
            def request(self, *_):
                return {'state': 'running', 'response_json': None, 'error_json': self.error,
                        'child_execution_id': 'sdk-managed:child'}
        store = Store()
        self.service.store = store
        row = {'source_id': 'source', 'parent_execution_id': self.lease.execution_id,
               'parent_attempt': self.lease.attempt, 'parent_fence': self.lease.fence,
               'request_id': 'request', 'wait_id': 'wait', 'child_execution_id': self.child.execution_id,
               'budget_json': json.dumps(self.envelope.to_dict())}
        failure = ChildExecutionError('parent_revocation_unknown', 'parent revocation state is unknown')
        self.service._retain_registration(row, failure, failure)
        self.assertEqual(json.loads(store.error)['code'], 'registration_or_cleanup_pending')

        class ExpiredWindow(Window):
            _delivery_deadline = None
            def remaining(self): return 0.0
        window = ExpiredWindow()
        caller = object.__new__(HandlerChildren)
        caller.command = SimpleNamespace(execution_id=self.lease.execution_id)
        caller.kernel, caller.store, caller.parent_lease = self.kernel, store, self.lease
        caller._active = lambda *_args, **_kwargs: None
        caller._complete_result_after_publication = lambda *_: None
        with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
             patch('dispatcher_sdk.execution_kernel.children._inspect_parent_revocation'), \
             patch('dispatcher_sdk.execution_kernel.children._retry', side_effect=lambda _w, fn, **_kw: fn()), \
             patch('dispatcher_sdk.execution_kernel.child_factual_read.uses_independent_reader', return_value=False):
            with self.assertRaises(ChildExecutionError) as raised:
                caller._await(row)
        self.assertEqual(raised.exception.code, 'parent_revocation_unknown')
        self.assertEqual(json.loads(store.error)['code'], 'registration_or_cleanup_pending')
        # The factual-delivery allowance also reads the pending cause if the
        # first business-window check has already expired.
        window._child_pending_diagnostic = None
        def expired(*_args, **_kwargs):
            raise ChildExecutionError('child_wait_timeout', 'elapsed')
        caller._active = expired
        with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
             patch('dispatcher_sdk.execution_kernel.children._inspect_parent_revocation'), \
             patch('dispatcher_sdk.execution_kernel.child_factual_read.uses_independent_reader', return_value=False):
            with self.assertRaises(ChildExecutionError) as raised:
                caller._await(row)
        self.assertEqual(raised.exception.code, 'parent_revocation_unknown')
        self.assertEqual(json.loads(store.error)['code'], 'registration_or_cleanup_pending')

    def test_unresolved_parent_sample_keeps_registration_when_revocation_is_not_durable(self):
        from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError
        row = {'action': 'run', 'parent_lease_json': json.dumps(self.lease.to_dict()),
               'budget_json': json.dumps(self.envelope.to_dict()), 'parent_execution_id': self.lease.execution_id,
               'child_execution_id': self.child.execution_id, 'request_id': 'request'}
        self.service._stop = threading.Event()
        with patch('dispatcher_sdk.execution_kernel.children._inspect_parent_revocation'), \
             patch('dispatcher_sdk.execution_kernel.children._RetryWindow',
                   side_effect=BudgetClockUnknownError('budget_clock_sample_unresolved:sampling')), \
             patch('dispatcher_sdk.execution_kernel.children._parent_durably_revoked', return_value=False), \
             patch.object(self.service, '_retain_registration') as retain, \
             patch.object(self.service, '_cancel') as cancel:
            self.service._execute(row)
        retain.assert_called_once()
        self.assertEqual(str(retain.call_args.args[2]), 'parent revocation is not durable')
        cancel.assert_not_called()

    def test_child_service_executes_declaration_before_real_kernel_submission(self):
        outcomes = []
        class Store:
            def attach(self, _row, _window): pass
            def bound(self, _window): return nullcontext()
            def transaction(self):
                connection = SimpleNamespace(execute=lambda *_args: None)
                return nullcontext((connection, time.time()))
            def finish(self, _row, state, **kwargs): outcomes.append((state, kwargs))
        self.service.store = Store()
        self.service._stop = threading.Event()
        self.service.max_depth = 1
        self.service.poll_interval = .01
        self.service.runtime.submit_child = lambda command, **kwargs: self.kernel.submit_child(
            command, kwargs['parent_lease'], kwargs['budget_envelope'])
        self.service.budget_declaration_provider = lambda **_: ('valid', dict(self.claim))
        window = Window()
        window.envelope = self.envelope
        row = {'action': 'run', 'parent_lease_json': json.dumps(self.lease.to_dict()),
               'budget_json': json.dumps(self.envelope.to_dict()), 'parent_execution_id': self.lease.execution_id,
               'child_execution_id': self.child.execution_id, 'command_json': json.dumps(self.child.to_dict()),
               'depth': 1, 'request_id': 'request'}
        result = SimpleNamespace(to_dict=lambda: {'status': 'succeeded', 'value': 'done'})
        with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
             patch('dispatcher_sdk.execution_kernel.children._wait_parent_entry'), \
             patch('dispatcher_sdk.execution_kernel.children._inspect_parent_revocation'), \
             patch.object(self.kernel, 'get', return_value=SimpleNamespace(state='succeeded', result=result)):
            self.service._execute(row)
        self.assertEqual(outcomes[0][0], 'completed')
        self.assertEqual(self.kernel.get_execution_limits(self.child.execution_id)['parent_execution_id'], self.lease.execution_id)
