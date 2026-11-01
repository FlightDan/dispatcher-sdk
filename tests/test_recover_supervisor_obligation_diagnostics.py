"""Exact durable Kernel facts only; no Runtime registry initialization."""
from pathlib import Path
import os
import multiprocessing
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import SQLiteKernel
from dispatcher_sdk.execution_kernel.runtime import Runtime
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from tests.test_execution_kernel_v2_sqlite import make_command, make_result


class RecoverSupervisorObligationDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        # This test exercises durable records only; no hash operation is needed.
        hash_guard = patch('hashlib.sha256', side_effect=AssertionError('unexpected hash operation'))
        hash_guard.start()
        self.addCleanup(hash_guard.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.kernel_path = Path(self.temp.name) / 'kernel.db'
        self.journal_path = Path(self.temp.name) / 'settlement.db'
        self.kernel = SQLiteKernel(self.kernel_path, now=lambda: 100.0)
        self.addCleanup(self.kernel.close)
        self.kernel.submit(make_command('exec', attempts=3))
        self.lease = self.kernel.claim_and_start('owner', execution_id='exec')
        self.registration = self.kernel.register_supervisor_obligation(self.lease)

    def runtime(self):
        runtime = object.__new__(Runtime)
        runtime.kernel = self.kernel
        runtime._settlement_journal = SettlementJournal(self.journal_path,
            source_id='test-store', kernel_path=self.kernel_path, timeout_seconds=1)
        return runtime

    def test_restarted_projection_is_exact_idempotent_and_does_not_infer_cleanup(self):
        runtime = self.runtime()
        identity = (self.lease.execution_id, self.lease.attempt, self.lease.fence)
        first = runtime.recover_claim_lifecycle(*identity, timeout_seconds=1)
        reopened = self.runtime()
        second = reopened.recover_claim_lifecycle(*identity, timeout_seconds=1)
        self.assertEqual(first['supervisor_obligation']['state'], 'recorded')
        self.assertEqual(second['supervisor_obligation']['receipt']['note_id'],
                         first['supervisor_obligation']['receipt']['note_id'])
        notes = reopened._settlement_journal.inspect_notes('exec', timeout_seconds=1)['notes']
        facts = [note for note in notes if note['phase'] == 'kernel_supervisor_obligation_recovered']
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['identity'], dict(zip(('execution_id', 'attempt', 'fence'), identity)))
        self.assertEqual(facts[0]['evidence'], {'source': 'kernel_supervisor_obligation',
            'registered_at': self.registration['registered_at']})
        self.assertEqual((second['outcome'], second['process_cleanup']), ('unknown', 'unknown'))
        self.assertFalse(any(note['phase'] in ('supervisor_registered', 'handler_entered',
            'handler_outcome', 'process_cleanup') for note in notes))
        missing = reopened.recover_claim_lifecycle('exec', self.lease.attempt, self.lease.fence + 1,
                                                   timeout_seconds=1)
        self.assertEqual(missing['supervisor_obligation'], {'state': 'unknown', 'reason': 'obligation_missing'})

    def test_lost_ack_replays_same_operation_after_reopen(self):
        runtime = self.runtime()
        journal = runtime._settlement_journal
        note = journal.note
        def lost_ack(identity, phase, evidence, **kwargs):
            receipt = note(identity, phase, evidence, **kwargs)
            if phase == 'kernel_supervisor_obligation_recovered':
                raise OSError('lost acknowledgement')
            return receipt
        args = (self.lease.execution_id, self.lease.attempt, self.lease.fence)
        with patch.object(journal, 'note', side_effect=lost_ack):
            first = runtime.recover_claim_lifecycle(*args, timeout_seconds=1)
        self.assertEqual(first['supervisor_obligation']['state'], 'unknown')
        reopened = self.runtime()
        replay = reopened.recover_claim_lifecycle(*args, timeout_seconds=1)
        self.assertEqual(replay['supervisor_obligation']['state'], 'recorded')
        notes = reopened._settlement_journal.inspect_notes('exec', timeout_seconds=1)['notes']
        self.assertEqual(sum(note['phase'] == 'kernel_supervisor_obligation_recovered' for note in notes), 1)

    def test_committed_cleanup_resolution_survives_restart_and_lost_ack(self):
        result = make_result(self.kernel, self.lease, status='failed', retryable=True)
        self.kernel._complete_sdk_result(self.lease, result, budget_envelope=None,
                                         supervisor_cleanup_confirmed=True)
        self.kernel.close()
        self.kernel = SQLiteKernel(self.kernel_path, now=lambda: 100.0)
        self.addCleanup(self.kernel.close)
        runtime = self.runtime()
        journal = runtime._settlement_journal
        original = journal.note
        def lost_ack(identity, phase, evidence, **kwargs):
            receipt = original(identity, phase, evidence, **kwargs)
            if phase == 'kernel_supervisor_resolution_recovered':
                raise OSError('lost acknowledgement')
            return receipt
        identity = (self.lease.execution_id, self.lease.attempt, self.lease.fence)
        with patch.object(journal, 'note', side_effect=lost_ack):
            first = runtime.recover_claim_lifecycle(*identity, timeout_seconds=1)
        self.assertEqual(first['supervisor_resolution']['state'], 'unknown')
        self.kernel.close()
        self.kernel = SQLiteKernel(self.kernel_path, now=lambda: 100.0)
        self.addCleanup(self.kernel.close)
        reopened = self.runtime()
        replay = reopened.recover_claim_lifecycle(*identity, timeout_seconds=1)
        self.assertEqual(replay['supervisor_resolution']['state'], 'recorded')
        self.assertEqual((replay['outcome'], replay['process_cleanup']), ('unknown', 'unknown'))
        notes = reopened._settlement_journal.inspect_notes('exec', timeout_seconds=1)['notes']
        recovered = [n for n in notes if n['phase'] == 'kernel_supervisor_resolution_recovered']
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]['identity'], dict(zip(('execution_id', 'attempt', 'fence'), identity)))
        self.assertEqual(recovered[0]['evidence'], {'source': 'sdk_confirmed_supervisor_cleanup',
                                                   'result_id': result.result_id, 'status': result.status})
        self.assertFalse(any(n['phase'] == 'process_cleanup' for n in notes))
        missing = reopened.recover_claim_lifecycle(identity[0], identity[1], identity[2] + 1, timeout_seconds=1)
        self.assertEqual(missing['supervisor_resolution']['state'], 'unknown')

    @unittest.skipUnless('fork' in multiprocessing.get_all_start_methods(), 'requires fork')
    def test_projection_survives_process_exit_after_journal_commit(self):
        result = make_result(self.kernel, self.lease, status='failed', retryable=True)
        self.kernel._complete_sdk_result(self.lease, result, budget_envelope=None,
                                         supervisor_cleanup_confirmed=True)
        identity = (self.lease.execution_id, self.lease.attempt, self.lease.fence)
        self.kernel.close()
        kernel_path, journal_path = self.kernel_path, self.journal_path

        def project_then_exit():
            with SQLiteKernel(kernel_path, now=lambda: 100.0) as kernel:
                runtime = object.__new__(Runtime)
                runtime.kernel = kernel
                journal = SettlementJournal(journal_path, source_id='test-store',
                                            kernel_path=kernel_path, timeout_seconds=1)
                runtime._settlement_journal = journal
                original = journal.note
                def exit_after_commit(key, phase, evidence, **kwargs):
                    receipt = original(key, phase, evidence, **kwargs)
                    if phase == 'kernel_supervisor_resolution_recovered':
                        os._exit(73)
                    return receipt
                with patch.object(journal, 'note', side_effect=exit_after_commit):
                    runtime.recover_claim_lifecycle(*identity, timeout_seconds=1)
            os._exit(1)

        process = multiprocessing.get_context('fork').Process(target=project_then_exit)
        process.start()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
            self.fail('projection process did not exit')
        self.assertEqual(process.exitcode, 73)
        self.kernel = SQLiteKernel(kernel_path, now=lambda: 100.0)
        self.addCleanup(self.kernel.close)
        runtime = self.runtime()
        report = runtime.recover_claim_lifecycle(*identity, timeout_seconds=1)
        self.assertEqual(report['supervisor_resolution']['state'], 'recorded')
        notes = runtime._settlement_journal.inspect_notes('exec', timeout_seconds=1)['notes']
        self.assertEqual(sum(note['phase'] == 'kernel_supervisor_resolution_recovered'
                             for note in notes), 1)
        self.assertFalse(any(note['phase'] == 'process_cleanup' for note in notes))

    def test_host_resolution_does_not_become_sdk_cleanup(self):
        with self.kernel._transaction() as (connection, _):
            connection.execute('UPDATE kernel_supervisor_obligations SET resolution_json=? WHERE execution_id=?',
                               ('{"decision":{},"principal":"host"}', 'exec'))
        runtime = self.runtime()
        report = runtime.recover_claim_lifecycle('exec', self.lease.attempt, self.lease.fence, timeout_seconds=1)
        self.assertEqual(report['supervisor_resolution'],
                         {'state': 'unknown', 'reason': 'resolution_not_sdk_cleanup'})
        self.assertFalse(any(n['phase'] == 'kernel_supervisor_resolution_recovered'
                             for n in runtime._settlement_journal.inspect_notes('exec', timeout_seconds=1)['notes']))

    def test_invalid_or_oversized_resolution_remains_unknown(self):
        runtime = self.runtime()
        for value, reason in [('{bad', 'recovery_unavailable'), ('x' * 65537, 'resolution_too_large')]:
            with self.kernel._transaction() as (connection, _):
                connection.execute('UPDATE kernel_supervisor_obligations SET resolution_json=? WHERE execution_id=?',
                                   (value, 'exec'))
            report = runtime.recover_claim_lifecycle('exec', self.lease.attempt, self.lease.fence, timeout_seconds=1)
            self.assertEqual((report['supervisor_resolution']['state'], report['supervisor_resolution']['reason']),
                             ('unknown', reason))
        self.assertFalse(any(n['phase'] == 'kernel_supervisor_resolution_recovered'
                             for n in runtime._settlement_journal.inspect_notes('exec', timeout_seconds=1)['notes']))

    def test_unregistered_exact_generation_stays_unknown(self):
        self.kernel.submit(make_command('unregistered', attempts=3))
        lease = self.kernel.claim_and_start('owner', execution_id='unregistered')
        runtime = self.runtime()
        report = runtime.recover_claim_lifecycle(lease.execution_id, lease.attempt, lease.fence,
                                                  timeout_seconds=1)
        self.assertEqual(report['supervisor_obligation'], {'state': 'unknown', 'reason': 'obligation_missing'})
        notes = runtime._settlement_journal.inspect_notes(lease.execution_id, timeout_seconds=1)['notes']
        self.assertFalse(any(note['phase'] == 'kernel_supervisor_obligation_recovered' for note in notes))
        self.assertEqual((report['outcome'], report['process_cleanup']), ('unknown', 'unknown'))

    def test_replaced_kernel_path_cannot_project_foreign_facts(self):
        runtime = self.runtime()
        replacement_path = Path(self.temp.name) / 'replacement.db'
        with SQLiteKernel(replacement_path, now=lambda: 100.0) as replacement:
            replacement.submit(make_command('exec', attempts=3))
            foreign = replacement.claim_and_start('owner', execution_id='exec')
            replacement.register_supervisor_obligation(foreign)
        with sqlite3.connect(self.kernel_path) as connection:
            connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        os.replace(replacement_path, self.kernel_path)
        report = runtime.recover_claim_lifecycle(self.lease.execution_id, self.lease.attempt,
                                                   self.lease.fence, timeout_seconds=1)
        self.assertEqual((report['state'], report['reason']), ('unknown', 'kernel_store_identity_mismatch'))
        self.assertEqual(report['supervisor_obligation']['state'], 'unknown')
        notes = runtime._settlement_journal.inspect_notes('exec', timeout_seconds=1)['notes']
        self.assertEqual(notes, [])


if __name__ == '__main__':
    unittest.main()
