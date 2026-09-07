from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dispatcher_sdk.orchestrator import Orchestrator
from dispatcher_sdk.execution_kernel import Kernel, ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.orchestrator.availability import inspect_work_availability


def echo(payload, context):
    return payload


class WorkAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.db'
        self.time = 100.0
        self.runtime = Kernel.open_sqlite(self.path, {'echo': echo}, isolation_mode='thread', now=lambda: self.time)
        self.addCleanup(self.runtime.close)
        self.sdk = Orchestrator(self.path, self.runtime.kernel, runtime=self.runtime)
        self.sdk.create_run('run', command_id='create')

    def apply(self, operations):
        revision = self.sdk.get_run('run')['revision']
        self.sdk.apply_operations('run', command_id=f'op-{revision}', expected_revision=revision, operations=operations)

    def add(self, name='one', dispatch=True):
        command = ExecutionCommandV2(execution_id=name, idempotency_key=name,
            registry_revision=self.runtime.registry_revision, correlation_id='run', causation_id=None,
            handler_id='echo', handler_contract_version=1, retry_policy=RetryPolicy(),
            timeout_seconds=5, payload={}).to_dict()
        self.apply([{'kind': 'add_task', 'task_id': name, 'command': command}]
                   + ([{'kind': 'dispatch', 'task_id': name}] if dispatch else []))

    def report(self, **kwargs):
        return inspect_work_availability(self.sdk, 'run', **kwargs)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as c:
            return list(c.iterdump())

    def test_no_tasks_wait_terminal_and_json(self):
        report = self.report()
        self.assertIn('no_tasks', report.reason_codes)
        json.dumps(report.to_dict())
        self.apply([{'kind': 'wait', 'wait_id': 'w'}])
        self.assertEqual(self.report().open_waits, 1)

    def test_binding_claim_and_no_mutations(self):
        self.add()
        self.assertEqual(self.report().pending_commands, 1)
        self.sdk.flush()
        before = self.dump()
        self.time = 200.0
        report = self.report()
        self.assertEqual(report.claimable_now, 1)
        self.assertEqual(report.observed_at, 200.0)
        self.assertEqual(before, self.dump())
        self.assertEqual(self.report(registry_revision='other').claimable_now, 0)
        self.sdk.runtime = None
        self.assertIsNone(self.report().claimable_now)
        self.assertEqual(self.report().queued_ready, 1)
        lease = self.runtime.kernel.claim('worker', registry_revision=self.runtime.registry_revision)
        self.assertIsNotNone(lease)
        self.assertEqual(self.report().active_leases, 1)
        self.time += 100
        before = self.dump()
        report = self.report()
        self.assertEqual(report.expired_leases, 1)
        self.assertEqual(report.queued_ready, 0)
        self.assertEqual(before, self.dump())

    def test_terminal_pending_sync_and_delivery(self):
        self.add()
        self.sdk.flush()
        self.runtime.run_once()
        self.assertEqual(self.report().pending_result_sync, 1)
        self.sdk.pump_results()
        report = self.report()
        self.assertEqual(report.pending_result_sync, 0)
        self.assertEqual(report.pending_result_delivery, 1)
        self.apply([{'kind': 'finish', 'state': 'succeeded'}])
        report = self.report()
        self.assertIn('terminal_run', report.reason_codes)
        self.assertEqual(report.pending_result_delivery, 1)

    def test_truncation_and_run_scope(self):
        self.add('one')
        self.add('two')
        self.sdk.flush()
        report = self.report(sample_limit=1)
        self.assertTrue(report.summaries_truncated)
        self.assertEqual(len(report.summaries), 1)
        self.assertEqual(report.claimable_now, 2)
        self.sdk.create_run('empty', command_id='create-empty')
        self.assertEqual(inspect_work_availability(self.sdk, 'empty').claimable_now, 0)

    def test_future_retry_and_logical_watermark(self):
        self.add()
        self.sdk.flush()
        # Persist a scheduler fixture without changing strict schema.
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('UPDATE kernel_executions SET next_attempt_at=150')
        report = self.report()
        self.assertEqual(report.future_retries, 1)
        self.assertEqual(report.next_change_hint, 150)
        self.time = 1
        self.assertEqual(self.report().observed_at, 100)

    def test_concurrent_write_reported_unknown(self):
        self.add()
        self.sdk.flush()
        original = self.runtime.kernel.current_time
        def concurrent():
            # Both databases are already pinned at this point; WAL permits write.
            with closing(sqlite3.connect(self.path)) as c, c:
                c.execute("UPDATE sdk_runs SET revision=revision+1 WHERE run_id='run'")
            return original()
        with patch.object(self.runtime.kernel, 'current_time', side_effect=concurrent):
            report = self.report()
        self.assertFalse(report.complete)
        self.assertIsNone(report.pending_result_sync)
        self.assertIn('concurrent_change', report.reason_codes)

    def test_missing_path_is_not_created(self):
        self.sdk.db_path = str(Path(self.tmp.name) / 'missing.db')
        with self.assertRaises(sqlite3.OperationalError):
            self.report()
        self.assertFalse(Path(self.sdk.db_path).exists())

    def test_recovery_and_unknown_effect_are_read_only(self):
        self.add()
        self.sdk.flush()
        kernel = self.runtime.kernel
        lease = kernel.claim_and_start('worker', registry_revision=self.runtime.registry_revision)
        kernel.prepare_effect(lease, effect_id='effect', name='external', request={})
        kernel.claim_effect(lease, 'effect')
        self.assertEqual(self.report().unknown_effects, 1)
        self.time = lease.expires_at + 1
        kernel.reap()
        before = self.dump()
        report = self.report()
        self.assertEqual(report.recovery_required, 1)
        self.assertEqual(report.unknown_effects, 1)
        self.assertEqual(before, self.dump())

    def test_independent_databases(self):
        self.sdk = Orchestrator(Path(self.tmp.name) / 'application.db', self.runtime.kernel, runtime=self.runtime)
        self.sdk.create_run('run', command_id='create')
        self.add()
        self.sdk.flush()
        report = self.report()
        self.assertEqual(report.claimable_now, 1)
        self.assertNotEqual(report.orchestrator_source, report.kernel_source)
        self.assertEqual(report.snapshot_consistency, 'non_atomic')

    def test_handler_scoped_binding_matches_actual_claim(self):
        command = self.runtime.command('echo', execution_id='scoped', idempotency_key='scoped',
            correlation_id='run', timeout_seconds=5, payload={})
        self.apply([{'kind': 'add_task', 'task_id': 'scoped', 'command': command.to_dict()},
                    {'kind': 'dispatch', 'task_id': 'scoped'}])
        self.sdk.flush()
        self.assertNotEqual(command.registry_revision, self.runtime.registry_revision)
        self.assertEqual(self.report().claimable_now, 1)
        self.assertEqual(self.report(registry_revision=self.runtime.registry_revision).claimable_now, 0)
        lease = self.runtime.kernel.claim('worker', registry_revisions=self.report().registry_revisions)
        self.assertEqual(lease.execution_id, 'scoped')

    def test_effect_scan_is_bounded_and_optional(self):
        self.add()
        self.sdk.flush()
        kernel = self.runtime.kernel
        lease = kernel.claim_and_start('worker', registry_revision=self.runtime.registry_revision)
        for index in range(12):
            kernel.prepare_effect(lease, effect_id=f'effect-{index}', name=f'external-{index}', request={})
        report = self.report(effect_scan_limit=3)
        self.assertIsNone(report.unknown_effects)
        self.assertFalse(report.complete)
        self.assertIn('effect_scan_limit_exceeded', report.reason_codes)
        self.assertEqual(self.report(effect_scan_limit=12).unknown_effects, 0)
        self.assertIn('effects_not_checked', self.report(effect_scan_limit=0).reason_codes)

    def test_run_first_query_plan_ignores_other_run_scale(self):
        from dispatcher_sdk.orchestrator.availability import _open_reader, _run_registration_source
        self.add()
        self.sdk.flush()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            # These registrations are outside the requested Run. They need no
            # matching authority for the index access regression fixture.
            connection.executemany('INSERT INTO sdk_executions VALUES(?,?,?,?,?,?,?)',
                [(f'other-{i}', 'other', f'task-{i}', 0, '{}', f'key-{i}', 1) for i in range(5000)])
        connection = _open_reader(str(self.path))
        try:
            connection.execute('ATTACH DATABASE ? AS authority', (self.path.as_uri() + '?mode=ro',))
            source = _run_registration_source(connection)
            plan = [row[3] for row in connection.execute('EXPLAIN QUERY PLAN SELECT COUNT(*)' + source +
                ' CROSS JOIN authority.kernel_executions k ON k.execution_id=s.execution_id'
                ' WHERE s.run_id=? AND s.active=1', ('run',))]
            self.assertIn('run_id=?', plan[0])
            self.assertIn('execution_id=?', plan[1])
            self.assertTrue(all('SEARCH' in step for step in plan), plan)
        finally:
            connection.close()
        self.assertEqual(self.report().claimable_now, 1)

    def test_command_identity_preserves_json_types(self):
        self.add()
        self.sdk.flush()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            command = json.loads(connection.execute('SELECT command_json FROM kernel_executions').fetchone()[0])
            command['payload'] = {'value': True}
            connection.execute('UPDATE kernel_executions SET command_json=?', (json.dumps(command),))
            command['payload'] = {'value': 1}
            connection.execute('UPDATE sdk_executions SET command=?', (json.dumps(command),))
        from dispatcher_sdk.orchestrator import OrchestrationError
        with self.assertRaisesRegex(OrchestrationError, 'command does not match'):
            self.report()
