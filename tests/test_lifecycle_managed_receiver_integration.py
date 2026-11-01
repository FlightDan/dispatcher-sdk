"""Protected Run lifecycle delivery uses exact durable receiver facts."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_child_budget_admissions as fixture_module
from dispatcher_sdk.execution_kernel import Kernel, SQLiteKernel
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel.errors import StorageIsolationError
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal


class ProtectedLifecycleReceiverTests(unittest.TestCase):
    def test_runtime_retry_delivers_exact_v4_receipt(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, 'registry_revision', return_value='host-registry'), \
             patch.object(runtime_module, 'handler_revision', return_value='host-handler'):
            path = Path(directory) / 'kernel.sqlite'
            runtime = Kernel.open_sqlite(path, {'work': lambda payload, context: payload},
                                         isolation_mode='thread')
            try:
                runtime.kernel.submit(fixture_module.command('job'))
                token = runtime.kernel.lifecycle_reserve('job', 0, 0, 'producer', slots=1)
                sequence = runtime.kernel.lifecycle_append(token, 'event', 'phase', {'value': 1})
                runtime._retry_diagnostic_notes(time.monotonic() + 2)
                journal = runtime._settlement_journal
                self.assertTrue(journal.lifecycle_receipt_committed(
                    {'execution_id': 'job', 'attempt': 0, 'fence': 0}, 'phase', {'value': 1},
                    store_id=runtime.kernel.kernel_store_identity(), outbox_sequence=sequence))
                self.assertTrue(runtime.kernel.lifecycle_event_delivered('event'))
            finally:
                runtime.close()

    def test_append_verifier_observes_frozen_payload_at_precommit(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {'fact': {'value': 'original'}}
            observed = []
            def verifier(credential, operation, identity, event):
                if operation == 'append':
                    observed.append(event['payload']['fact']['value'])
                    payload['fact']['value'] = 'changed by caller'
                    event['payload']['fact']['value'] = 'changed by verifier'
                return {'allowed': True, 'expires_at': time.time() + 60}
            kernel = SQLiteKernel(Path(directory) / 'kernel.sqlite', lifecycle_verifier=verifier)
            self.addCleanup(kernel.close)
            kernel.submit(fixture_module.command('job'))
            token = kernel.lifecycle_reserve('job', 0, 0, 'producer', slots=1)
            kernel.lifecycle_append(token, 'event', 'phase', payload)
            self.assertEqual(observed, ['original', 'original'])
            self.assertEqual(kernel.lifecycle_peek()['payload'], {'fact': {'value': 'original'}})

    def test_post_cancel_delivery_requires_exact_committed_receiver_note(self):
        fixture = fixture_module.ChildBudgetAdmissionsTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        kernel, lease = fixture.worker, fixture.lease
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        journal = SettlementJournal(Path(temp.name) / 'settlement.sqlite', source_id='test', kernel_path=kernel.db_path)
        calls = []

        def lifecycle_verifier(credential, operation, identity, event):
            calls.append((credential, operation, dict(identity), event))
            allowed = credential == 'worker' and identity == {
                'run_id': 'run', 'generation': 0, 'execution_id': lease.execution_id,
                'attempt': lease.attempt, 'fence': lease.fence}
            committed = False
            if operation == 'ack' and allowed:
                committed = journal.lifecycle_receipt_committed(
                    {k: identity[k] for k in ('execution_id', 'attempt', 'fence')},
                    event['phase'], event['payload'], store_id=event['store_id'],
                    outbox_sequence=event['sequence'])
            return {'allowed': allowed, 'expires_at': time.time() + 60,
                    'receiver_committed': committed}

        kernel._lifecycle_verifier = lifecycle_verifier
        token = kernel.lifecycle_reserve(lease.execution_id, lease.attempt, lease.fence, 'owner', slots=2)
        sequence = kernel.lifecycle_append(token, 'cancel-event', 'cancellation_process_cleanup', {'state': 'confirmed'})
        # Kernel cancellation revokes the live execution lease. Lifecycle evidence
        # remains recoverable under an independent host-authorized callback.
        # This fixture establishes a protected Run directly; set its control to
        # pausing before exercising the real Kernel cancellation path.
        with fixture.manager._transaction() as (connection, _):
            connection.execute("UPDATE kernel_run_controls SET state='pausing' WHERE run_id='run'")
        kernel.cancel(lease)
        from dispatcher_sdk.execution_kernel import StaleFenceError
        with self.assertRaises(StaleFenceError):
            kernel.verify(lease)
        event = kernel.lifecycle_peek(execution_id=lease.execution_id)
        self.assertEqual(event['event_id'], 'cancel-event')
        with self.assertRaises(StorageIsolationError):
            kernel.lifecycle_ack(sequence, 'cancel-event')
        self.assertFalse(kernel.lifecycle_event_delivered('cancel-event'))
        journal.lifecycle_note({k: event[k] for k in ('execution_id', 'attempt', 'fence')},
                     event['phase'], event['payload'], store_id=event['receiver_store_id'],
                     outbox_sequence=sequence)
        self.assertTrue(kernel.lifecycle_ack(sequence, 'cancel-event'))
        self.assertTrue(kernel.lifecycle_finish(token))
        self.assertTrue(any(call[1] == 'ack' and call[3] == {
            'store_id': event['receiver_store_id'], 'sequence': sequence,
            'event_id': 'cancel-event', 'phase': 'cancellation_process_cleanup',
            'payload': {'state': 'confirmed'}} for call in calls))

        # An SDK connection without host authorization cannot inspect or alter
        # another protected execution's lifecycle facts.
        other = SQLiteKernel(kernel.db_path)
        self.addCleanup(other.close)
        self.assertIsNone(other.lifecycle_peek())
        with self.assertRaises(StorageIsolationError):
            other.lifecycle_finish(token)


if __name__ == '__main__':
    unittest.main()
