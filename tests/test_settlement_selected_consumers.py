"""Selected settlement consumer paths, with synthetic cleanup evidence."""
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.children import HandlerChildren, _Store
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.observability import ObservationJournal
from dispatcher_sdk.observability.journal import inspect_execution
from dispatcher_sdk.orchestrator import Orchestrator, Operations
from dispatcher_sdk.orchestrator.contracts import OrchestrationError


def echo(payload, context):
    return payload


class SelectedSettlementConsumerTests(unittest.TestCase):
    def test_runtime_selected_binding_reaches_child_service_and_orchestrator(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed-registry'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed-handler'):
            root = Path(root)
            path = root / 'kernel.sqlite'
            first = Kernel.open_sqlite(path, {'echo': echo}, isolation_mode='thread')
            try:
                binding = first.settlement_storage
                selected = SettlementJournal(root / 'selected.sqlite', source_id=binding['source_id'], kernel_path=path)
            finally:
                first.close()
            runtime = Kernel.open_sqlite(path, {'echo': echo}, isolation_mode='thread',
                                         settlement_journal_path=selected.path)
            try:
                self.assertEqual(runtime.settlement_storage['path'], selected.path)
                self.assertEqual(runtime._child_service.store._facts().path, selected.path)
                self.assertEqual(runtime._service_spec(SimpleNamespace(execution_id='absent'))['settlement_binding'],
                                 runtime.settlement_storage)
                spec = runtime._service_spec(SimpleNamespace(execution_id='parent'))
                children = HandlerChildren(runtime.kernel, SimpleNamespace(execution_id='parent'),
                    SimpleNamespace(execution_id='parent'), None, spec, journal=runtime.observation_journal)
                self.assertEqual(children.store._facts().path, selected.path)
                sdk = Orchestrator(root / 'app.sqlite', runtime.kernel, runtime=runtime)
                self.assertEqual(sdk.settlement_journal_path, selected.path)
                with self.assertRaises(ValueError):
                    sdk.inspect_cancellation('run', settlement_journal_path=binding['path'])
                with self.assertRaises(OrchestrationError):
                    Orchestrator(root / 'different.sqlite', runtime.kernel, runtime=runtime,
                                 settlement_journal_path=binding['path'])
            finally:
                runtime.close()

    def test_real_child_checkpoint_and_public_diagnostics_select_destination(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            kernel = root / 'kernel.sqlite'
            kernel.touch()
            source = 'source'
            observations = ObservationJournal(root / 'observation.sqlite', kernel_path=kernel, source_id=source)
            selected = SettlementJournal(root / 'selected.sqlite', kernel_path=kernel, source_id=source)
            legacy = SettlementJournal(str(kernel) + '.settlements.sqlite3', kernel_path=kernel, source_id=source)
            @contextmanager
            def locked(**_kwargs):
                raise sqlite3.OperationalError('database is locked')
                yield
            journal = SimpleNamespace(source_id=source, kernel_path=str(kernel), _transaction=locked)
            binding = {'path': selected.path, 'kernel_path': selected.kernel_path, 'source_id': source, 'available': True}
            store = _Store(journal, binding)
            original = BudgetEnvelope((), sample_clock())
            advanced = original.recheckpoint(sample=sample_clock(wall_time=time.time() + 5))
            row = {'budget_json': json.dumps(original.to_dict()), 'wait_id': 'wait', 'child_execution_id': 'child'}
            store.remember(row, advanced)
            notes = selected.inspect_notes('child')['notes']
            self.assertEqual([note['phase'] for note in notes], ['child_budget_checkpoint'])
            self.assertEqual(legacy.inspect_notes('child')['notes'], [])
            self.assertEqual(notes[0]['evidence']['wait_id'], 'wait')
            report = inspect_execution(observations.path, 'child', kernel_path=kernel, source_id=source,
                                       settlement_journal_path=selected.path, timeout=2)
            self.assertEqual(report['diagnostics']['notes'][0]['note_id'], notes[0]['note_id'])
            missing = root / 'missing.sqlite'
            report = inspect_execution(observations.path, 'child', kernel_path=kernel, source_id=source,
                                       settlement_journal_path=missing, timeout=2)
            self.assertFalse(report['complete'])
            self.assertEqual(report['unknown_reason'], 'diagnostic_observation_unavailable')
            self.assertFalse(missing.exists())
            with self.assertRaises(BudgetClockUnknownError):
                _Store(journal, {**binding, 'path': str(missing)})._facts()
            with self.assertRaises(BudgetClockUnknownError):
                _Store(journal, {**binding, 'available': False})._facts(writer=True)
            self.assertFalse(missing.exists())

    def test_public_cancellation_uses_selected_not_legacy_cleanup(self):
        with tempfile.TemporaryDirectory() as root, \
             patch.object(runtime_module, 'registry_revision', return_value='fixed-registry'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixed-handler'):
            root = Path(root)
            runtime = Kernel.open_sqlite(root / 'kernel.sqlite', {'echo': echo}, isolation_mode='thread')
            try:
                default = runtime._settlement_journal
                selected = SettlementJournal(root / 'selected.sqlite', source_id=default.source_id,
                                             kernel_path=runtime.kernel.db_path)
                # Standalone selection is explicit; input cleanup notes here are synthetic.
                sdk = Orchestrator(root / 'app.sqlite', runtime.kernel, settlement_journal_path=selected.path)
                sdk.create_run('run', command_id='create')
                command = runtime.command('echo', execution_id='x', idempotency_key='x', correlation_id='run',
                                          payload={}, timeout_seconds=40, retry_policy=RetryPolicy())
                sdk.apply_operations('run', command_id='add', expected_revision=0,
                                     operations=[Operations.add_task('task', command), Operations.dispatch('task')])
                sdk.flush()
                lease = runtime.kernel.claim('external-worker')
                runtime.cancel('x', expected_revision=runtime.kernel.get('x').revision)
                identity = {'execution_id': 'x', 'attempt': lease.attempt, 'fence': lease.fence}
                proof = {'state': 'confirmed', 'source': 'runtime_supervisor_reaped'}
                default.note(identity, 'process_cleanup', proof, timeout_seconds=5)
                self.assertNotEqual(sdk.inspect_cancellation('run').executions[0].local_process_tree_reaped.status, 'confirmed')
                selected.note(identity, 'process_cleanup', proof, timeout_seconds=5)
                report = sdk.inspect_cancellation('run').executions[0]
                self.assertEqual(report.local_process_tree_reaped.status, 'confirmed')
                self.assertEqual(report.local_process_tree_reaped.source, 'settlement_journal')
                missing = Orchestrator(root / 'app.sqlite', runtime.kernel, settlement_journal_path=root / 'missing.sqlite')
                report = missing.inspect_cancellation('run').executions[0]
                self.assertNotEqual(report.local_process_tree_reaped.status, 'confirmed')
                self.assertFalse((root / 'missing.sqlite').exists())
            finally:
                runtime.close()


if __name__ == '__main__':
    unittest.main()
