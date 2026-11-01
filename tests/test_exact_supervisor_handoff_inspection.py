"""Raw journal observations are never host acceptance or cleanup authority."""
import contextlib
import multiprocessing
import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, runtime as runtime_module
from dispatcher_sdk._inspection import InspectionBudget
from dispatcher_sdk.execution_kernel.contracts import ExecutionLease
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.observability.journal import ObservationJournal, inspect_execution
import test_supervisor_outcome_handoff as fixture
from tests.test_execution_kernel_v2_sqlite import make_result


def _never_invoked(payload, context):
    raise AssertionError('observation must not invoke handlers')


class ExactHandoffInspectionTests(unittest.TestCase):
    def test_standalone_handoff_unknown_when_observation_open_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(ObservationJournal, 'open_readonly', side_effect=TimeoutError('original failure')):
                report = inspect_execution(root / 'missing', 'execution', kernel_path=root / 'kernel',
                    source_id='source', attempt=1, fence=2, timeout=2)
            self.assertFalse(report['complete'])
            self.assertEqual(report['unknown_reason'], 'diagnostic_observation_unavailable')
            self.assertIn('TimeoutError: original failure', report['error'])
            self.assertEqual(report['supervisor_handoff']['identity'],
                {'execution_id': 'execution', 'attempt': 1, 'fence': 2})
            self.assertEqual(report['supervisor_handoff']['unknown_reason'], 'inspection_unavailable')

    def test_standalone_handoff_failure_preserves_generic_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = {'path': str(root / 'settlement'), 'kernel_path': str(root / 'kernel'), 'source_id': 'source'}
            journal = SettlementJournal(**binding)
            identity = {'execution_id': 'execution', 'attempt': 1, 'fence': 1}
            journal.note(identity, 'example_note', {'value': 'retained'})
            observations = ObservationJournal(root / 'observation', kernel_path=binding['kernel_path'], source_id='source')
            with patch.object(SettlementJournal, 'inspect_supervisor_handoff', side_effect=TimeoutError('busy')):
                report = inspect_execution(observations.path, 'execution', kernel_path=binding['kernel_path'],
                    source_id='source', attempt=1, fence=1, settlement_journal_path=binding['path'], timeout=2)
            self.assertFalse(report['complete'])
            self.assertEqual(report['supervisor_handoff']['unknown_reason'], 'inspection_unavailable')
            self.assertIn('TimeoutError', report['supervisor_handoff_error'])
            self.assertEqual(report['diagnostics']['notes'][0]['evidence']['value'], 'retained')
            self.assertIn('settlement_obligations', report)

    def test_runtime_observes_exact_generation_beyond_generic_notes_page(self):
        # Revision functions are stubbed; this test does not validate the registry.
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, 'registry_revision', return_value='fixture-registry'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixture-handler'):
            runtime = Kernel.open_sqlite(Path(directory) / 'kernel', {'work': _never_invoked}, isolation_mode='thread')
            try:
                runtime.submit(runtime.command('work', execution_id='execution', idempotency_key='execution',
                    correlation_id='execution', timeout_seconds=30, payload={}))
                journal = runtime._settlement_journal
                lease = runtime.kernel.claim_and_start('worker', execution_id='execution', lease_seconds=30)
                result = make_result(runtime.kernel, lease)
                journal.record(lease, result, evidence={}, timeout_seconds=1)
                for i in range(60):
                    journal.note({'execution_id': 'execution', 'attempt': 3, 'fence': 4},
                                 'noise', {'index': i, 'padding': 'x' * 200}, timeout_seconds=1)
                identity = {'execution_id': 'execution', 'attempt': 2, 'fence': 3}
                journal.note(identity, 'supervisor_spawn_intent', {'source': 'runtime_pre_spawn', 'cleanup': 'unknown'})
                journal.record_supervisor_outcome(identity, fixture.RAW)
                report = runtime.observe('execution', attempt=2, fence=3, timeout=3)
                handoff = report['supervisor_handoff']
                self.assertEqual(handoff['authority'], 'not_established')
                self.assertEqual(handoff['facts']['spawn_intent']['state'], 'observed')
                self.assertEqual(handoff['facts']['worker_packet']['evidence']['outcome_json'], fixture.RAW)
                wrong = runtime.observe('execution', attempt=2, fence=8, timeout=3)['supervisor_handoff']
                self.assertTrue(all(fact['state'] == 'unknown' for fact in wrong['facts'].values()))
                with patch.object(journal, 'inspect_supervisor_handoff', side_effect=TimeoutError('busy')):
                    unavailable = runtime.observe('execution', attempt=2, fence=3, timeout=3)
                self.assertFalse(unavailable['complete'])
                self.assertEqual(unavailable['supervisor_handoff']['unknown_reason'], 'inspection_unavailable')
                self.assertIn('TimeoutError', unavailable['supervisor_handoff_error'])
                self.assertNotIn('settlement_obligations_error', unavailable)
                self.assertEqual(unavailable['settlement_obligations'][0]['identity'],
                    {'execution_id': 'execution', 'attempt': lease.attempt, 'fence': lease.fence})
                self.assertEqual(unavailable['diagnostics']['notes'][0]['phase'], 'noise')
                runtime.observation_options = replace(runtime.observation_options, query_bytes=4096)
                bounded = runtime.observe('execution', attempt=2, fence=3, timeout=3)
                self.assertEqual(bounded['supervisor_handoff']['facts']['worker_packet']['evidence']['outcome_json'], fixture.RAW)
                self.assertFalse(bounded['complete'])
                self.assertFalse(bounded['diagnostics']['complete'])
                self.assertLessEqual(len(json.dumps(bounded, ensure_ascii=False, separators=(',', ':')).encode()), 4096)
                # A filled generic section must be displaced before the requested handoff.
                constrained = ObservationJournal._bound_without_storage(
                    {'execution_id': 'execution', 'complete': True, 'diagnostics': {'notes': ['x' * 3500]},
                     'supervisor_handoff': handoff}, options=runtime.observation_options,
                    budget=InspectionBudget(3, None))
                self.assertEqual(constrained['supervisor_handoff']['facts']['worker_packet']['evidence']['outcome_json'], fixture.RAW)
                self.assertFalse(constrained['complete'])
                self.assertTrue(constrained['truncated'])
            finally:
                runtime.close()

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_supervisor_crash_raw_packet_survives_and_public_diagnostics_target_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = {'path': str(root / 'settlement'), 'kernel_path': str(root / 'kernel'), 'source_id': 'source'}
            journal = SettlementJournal(**binding, timeout_seconds=1)
            identity = fixture.IDENTITY
            journal.note(identity, 'supervisor_spawn_intent', {'source': 'runtime_pre_spawn', 'cleanup': 'unknown'})
            # Unrelated notes cannot hide the exact generation behind pages.
            for i in range(60):
                journal.note({'execution_id': 'execution', 'attempt': 3, 'fence': 4},
                             'noise', {'index': i})
            lease = ExecutionLease('execution', 'lease', 'owner', 3, 2, 9999999999, 1)
            ctx = multiprocessing.get_context('fork')
            receiver, sender = ctx.Pipe(duplex=False)
            process = ctx.Process(target=fixture.supervisor_crashes_before_delivery,
                                  args=(sender, binding, False, False, lease))
            process.start()
            sender.close()
            process.join(10)
            self.assertEqual(process.exitcode, 61)
            receiver.close()
            reopened = SettlementJournal.open_readonly(**binding, timeout_seconds=1)
            report = reopened.inspect_supervisor_handoff(identity, timeout_seconds=1)
            facts = report['facts']
            self.assertEqual(report['authority'], 'not_established')
            self.assertEqual(facts['worker_packet']['evidence']['outcome_json'], fixture.RAW)
            self.assertEqual(facts['supervisor_disposition']['evidence']['worker_return'], 'indeterminate')
            self.assertEqual(facts['supervisor_reap']['state'], 'unknown')
            wrong = reopened.inspect_supervisor_handoff({**identity, 'fence': 4}, timeout_seconds=1)
            self.assertTrue(all(fact['state'] == 'unknown' for fact in wrong['facts'].values()))
            observations = ObservationJournal(root / 'observation', kernel_path=binding['kernel_path'], source_id='source')
            public = inspect_execution(observations.path, 'execution', kernel_path=binding['kernel_path'],
                source_id='source', attempt=2, fence=3, settlement_journal_path=binding['path'], timeout=2)
            self.assertEqual(public['supervisor_handoff']['facts']['worker_packet']['evidence']['outcome_json'], fixture.RAW)
            self.assertEqual(public['supervisor_handoff']['authority'], 'not_established')

    def test_budget_unknown_and_invalid_data_never_become_observed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = SettlementJournal(root / 'journal', source_id='source', kernel_path=root / 'kernel')
            identity = {'execution_id': 'execution', 'attempt': 1, 'fence': 1}
            journal.note(identity, 'supervisor_spawn_intent', {'source': 'runtime_pre_spawn', 'cleanup': 'unknown', 'value': 'x' * 2000})
            report = journal.inspect_supervisor_handoff(identity, max_bytes=1024)
            self.assertEqual(report['facts']['spawn_intent'], {'state': 'unknown', 'reason': 'byte_budget_exceeded'})
            self.assertEqual(report['facts']['worker_packet']['state'], 'unknown')
            with contextlib.closing(sqlite3.connect(journal.path)) as db, db:
                db.execute("UPDATE settlement_notes SET evidence_json='not-json' WHERE phase='supervisor_spawn_intent'")
            report = journal.inspect_supervisor_handoff(identity, max_bytes=1024)
            self.assertEqual(report['facts']['spawn_intent'], {'state': 'unknown', 'reason': 'invalid_observation'})
            with self.assertRaises(ValueError):
                journal.inspect_supervisor_handoff(identity, max_bytes=1023)

    def test_encoded_size_and_malformed_canonical_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = SettlementJournal(root / 'journal', source_id='source', kernel_path=root / 'kernel')
            long_identity = {'execution_id': '界"\\' * 600, 'attempt': 1, 'fence': 1}
            report = journal.inspect_supervisor_handoff(long_identity, max_bytes=1024)
            self.assertIsNone(report['identity'])
            self.assertEqual(report['unknown_reason'], 'identity_exceeds_byte_budget')
            self.assertLessEqual(len(json.dumps(report, ensure_ascii=False, separators=(',', ':')).encode()), 1024)
            identity = {'execution_id': 'exec', 'attempt': 1, 'fence': 1}
            journal.note(identity, 'supervisor_spawn_intent',
                         {'source': 'runtime_pre_spawn', 'cleanup': 'unknown', 'value': '界"\\' * 200},
                         timeout_seconds=5)
            phase = 'supervisor_outcome_observed'
            note_id = json.dumps([phase, 'exec', 1, 1], separators=(',', ':'))
            journal.note(identity, phase, {'source': 'posix_supervisor_worker_packet', 'outcome_json': '{bad'},
                         note_id=note_id, timeout_seconds=5)
            for limit in (1024, 2048, 4096):
                report = journal.inspect_supervisor_handoff(identity, max_bytes=limit)
                self.assertLessEqual(len(json.dumps(report, ensure_ascii=False, separators=(',', ':')).encode()), limit)
                self.assertEqual(report['facts']['worker_packet']['reason'], 'invalid_observation')
            self.assertEqual(journal.inspect_supervisor_handoff(identity, max_bytes=1024)['facts']['spawn_intent']['reason'], 'byte_budget_exceeded')
            self.assertEqual(journal.inspect_supervisor_handoff(identity, max_bytes=4096)['facts']['spawn_intent']['state'], 'observed')
            with contextlib.closing(sqlite3.connect(journal.path)) as db, db:
                db.execute('UPDATE settlement_notes SET evidence_json=? WHERE note_id=?', ('{}', note_id))
            self.assertEqual(journal.inspect_supervisor_handoff(identity)['facts']['worker_packet']['reason'], 'invalid_observation')
            phase = 'supervisor_disposition_observed'
            disposition_id = json.dumps([phase, 'exec', 1, 1], separators=(',', ':'))
            wrong_lease = ExecutionLease('exec', 'lease', 'worker', 2, 1, 9999999999, 1)
            journal.note(identity, phase, {'source': 'posix_supervisor', 'worker_return': 'timely',
                                           'lease': wrong_lease.to_dict()}, note_id=disposition_id,
                         timeout_seconds=5)
            self.assertEqual(journal.inspect_supervisor_handoff(identity)['facts']['supervisor_disposition']['reason'], 'invalid_observation')
