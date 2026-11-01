"""Host-scoped lifecycle retention does not require live Run admission."""
import unittest
from unittest.mock import Mock

from dispatcher_sdk.execution_kernel._sqlite_execution import SQLiteKernel, _LifecycleDenied
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError


class LifecycleAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.kernel = SQLiteKernel.__new__(SQLiteKernel)
        self.kernel._worker_credential = object()
        self.kernel._precommit_authority_checks = []
        self.kernel._advance_clock = Mock(return_value=11)
        self.connection = Mock()
        self.connection.execute.return_value.fetchone.return_value = ('run', 3)
        self.claim = dict(permissions=[('run', 'kernel:retain_lifecycle')], run_id='run', generation=3,
                          execution_id='execution', attempt=2, fence=4,
                          lifecycle_operations=['ack'], expires_at=20)
        self.kernel._lifecycle_verifier = self.verifier

    def verifier(self, credential, operation, identity, event):
        allowed = ((identity['run_id'], 'kernel:retain_lifecycle') in self.claim['permissions']
                   and all(self.claim[k] == identity[k] for k in identity)
                   and operation in self.claim['lifecycle_operations'])
        return {'allowed': allowed, 'expires_at': self.claim['expires_at'], 'receiver_committed': True}

    def check(self):
        self.kernel._authorize_lifecycle(self.connection, 'execution', 2, 4, 'ack', 10)

    def test_exact_scoped_host_authority_and_precommit_recheck(self):
        self.check()
        self.kernel._precommit_authority_checks[-1]()
        self.claim['expires_at'] = 11
        with self.assertRaises(StorageIsolationError):
            self.kernel._precommit_authority_checks[-1]()

    def test_denies_stale_identity_and_missing_permission_or_operation(self):
        for field, value in [('fence', 5), ('generation', 4), ('permissions', []),
                             ('lifecycle_operations', ['finish']), ('expires_at', 10)]:
            with self.subTest(field=field):
                original = self.claim[field]
                self.claim[field] = value
                with self.assertRaises(StorageIsolationError):
                    self.check()
                self.claim[field] = original

    def test_unprotected_local_call_uses_existing_trust_boundary(self):
        self.connection.execute.return_value.fetchone.return_value = None
        self.kernel._lifecycle_verifier = None
        self.check()


if __name__ == '__main__':
    unittest.main()

class LifecyclePeekContinuationTests(unittest.TestCase):
    def test_denied_page_does_not_hide_later_authorized_event(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from tests.test_execution_kernel_v2_p1 import make_command
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        with tempfile.TemporaryDirectory() as directory:
            kernel = SQLiteKernel(Path(directory) / 'kernel.db')
            self.addCleanup(kernel.close)
            for i in range(129):
                name = f'e{i:03}'
                kernel.submit(make_command(name))
                self.assertEqual(kernel.lifecycle_reserve(name, 0, 0, name, slots=1), name)
                kernel.lifecycle_append(name, name, 'phase', {'value': i})
            def authorize(connection, execution_id, attempt, fence, operation, timestamp, event=None, **kwargs):
                if execution_id != 'e128':
                    raise _LifecycleDenied('denied')
            with patch.object(kernel, '_authorize_lifecycle', side_effect=authorize):
                page = kernel.lifecycle_peek()
                self.assertEqual(page, {'continuation': 128})
                event = kernel.lifecycle_peek(after_sequence=page['continuation'])
                self.assertEqual(event['execution_id'], 'e128')
                self.assertEqual(event['payload'], {'value': 128})
            with patch.object(kernel, '_authorize_lifecycle', side_effect=StorageIsolationError('verifier unavailable')):
                with self.assertRaisesRegex(StorageIsolationError, 'unavailable'):
                    kernel.lifecycle_peek()
                with self.assertRaisesRegex(StorageIsolationError, 'unavailable'):
                    kernel.lifecycle_list_open_producers()

class LifecycleRetentionTests(unittest.TestCase):
    def test_explicit_cutoff_prunes_only_delivered_payload_and_reports_expiry(self):
        import tempfile
        from pathlib import Path
        from tests.test_execution_kernel_v2_p1 import make_command
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        from dispatcher_sdk.execution_kernel.errors import LifecycleReceiptExpiredError
        with tempfile.TemporaryDirectory() as directory:
            kernel = SQLiteKernel(Path(directory) / 'kernel.db')
            self.addCleanup(kernel.close)
            kernel.submit(make_command('x'))
            kernel.lifecycle_reserve('x', 0, 0, 'producer', slots=2)
            first = kernel.lifecycle_append('producer', 'first', 'phase', {'fact': 1})
            second = kernel.lifecycle_append('producer', 'second', 'phase', {'fact': 2})
            self.assertTrue(kernel.lifecycle_ack(first, 'first'))
            self.assertEqual(kernel.lifecycle_prune_delivered(second)['pruned'], 1)
            self.assertTrue(kernel.lifecycle_event_delivered('first'))
            self.assertFalse(kernel.lifecycle_event_delivered('second'))
            with self.assertRaises(LifecycleReceiptExpiredError):
                kernel.lifecycle_append('producer', 'first', 'phase', {'fact': 1})
            self.assertEqual(kernel.lifecycle_peek()['event_id'], 'second')

    def test_recovery_requires_host_proof_and_preserves_pending_event(self):
        import tempfile
        from pathlib import Path
        from tests.test_execution_kernel_v2_p1 import make_command
        from dispatcher_sdk.execution_kernel import SQLiteKernel
        from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
        with tempfile.TemporaryDirectory() as directory:
            kernel = SQLiteKernel(Path(directory) / 'kernel.db')
            self.addCleanup(kernel.close)
            journal = SettlementJournal(Path(directory) / 'settlement.db', source_id='test', kernel_path=kernel.db_path)
            kernel.submit(make_command('x'))
            kernel.lifecycle_reserve('x', 0, 0, 'producer', slots=1)
            with self.assertRaises(ValueError):
                kernel.lifecycle_append('producer', 'forged', 'producer_recovered_evidence_may_be_missing',
                                        {'state': 'confirmed'})
            kernel.lifecycle_append('producer', 'event', 'phase', {'actual': True})
            page = kernel.lifecycle_list_open_producers(limit=1)
            self.assertEqual(page['producers'][0]['token'], 'producer')
            self.assertEqual(page['producers'][0]['pending'], 1)
            self.assertEqual(kernel.lifecycle_list_open_producers(after_rowid=page['continuation'])['producers'], [])
            with self.assertRaises(StorageIsolationError):
                kernel.lifecycle_recover_producer('producer', {'claim': 'dead'})
            def verify(credential, operation, identity, event):
                proof = (event or {}).get('proof', {})
                committed = operation == 'ack' and journal.lifecycle_receipt_committed(
                    {key: identity[key] for key in ('execution_id', 'attempt', 'fence')},
                    event['phase'], event['payload'], store_id=event['store_id'],
                    outbox_sequence=event['sequence'])
                return {'allowed': True, 'expires_at': kernel._wall_time() + 100,
                    'producer_dead': operation == 'recover' and proof.get('host_confirmed') is True,
                    'evidence_unknown_acknowledged': proof.get('unknown_acknowledged') is True,
                    'receiver_committed': committed}
            kernel._lifecycle_verifier = verify
            with self.assertRaises(StorageIsolationError):
                kernel.lifecycle_recover_producer('producer', {'host_confirmed': False})
            with self.assertRaises(StorageIsolationError):
                kernel.lifecycle_recover_producer('producer', {'host_confirmed': True})
            self.assertEqual(kernel.lifecycle_inspect_producer('producer')['state'], 'open')
            self.assertTrue(kernel.lifecycle_recover_producer('producer', {'host_confirmed': True, 'unknown_acknowledged': True}))
            self.assertEqual(kernel.lifecycle_inspect_producer('producer')['state'], 'closed')
            self.assertEqual(kernel.lifecycle_list_open_producers()['producers'], [])
            first = kernel.lifecycle_peek()
            self.assertEqual(first['event_id'], 'event')
            journal.lifecycle_note({'execution_id': 'x', 'attempt': 0, 'fence': 0},
                first['phase'], first['payload'], store_id=first['receiver_store_id'],
                outbox_sequence=first['sequence'])
            self.assertTrue(kernel.lifecycle_ack(1, 'event'))
            marker = kernel.lifecycle_peek()
            self.assertEqual(marker['phase'], 'producer_recovered_evidence_may_be_missing')
            self.assertEqual(marker['payload'], {'state': 'unknown', 'reason': 'producer_interrupted'})
            self.assertTrue(kernel.lifecycle_recover_producer('producer', {'host_confirmed': True, 'unknown_acknowledged': True}))
            self.assertEqual(kernel.lifecycle_peek()['sequence'], marker['sequence'])
