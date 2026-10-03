"""Wait projection against real SQLite contention and Kernel authority."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import dispatcher_sdk.observability as observability
from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel
from dispatcher_sdk.execution_kernel.budget import ClockCheckpoint
from dispatcher_sdk.observability.contracts import ObservationIdentity, ObservationOptions, StallPolicy

from dispatcher_sdk.observability.journal import ObservationJournal
from dispatcher_sdk.observability.activity import ActivityRecorder
from dispatcher_sdk.observability.supervision import StallSupervisor


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sample(self):
        return ClockCheckpoint(self.now, self.now, 'wait-test-boot', 'boot')


class WaitObservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.clock = Clock()
        self.kernel = SQLiteKernel(self.root / 'kernel.sqlite3', now=self.clock)
        self.addCleanup(self.kernel.close)
        self.kernel.submit(ExecutionCommandV2(execution_id='work', idempotency_key='work',
            registry_revision='test', correlation_id='work', causation_id=None,
            handler_id='test', handler_contract_version=1, retry_policy=RetryPolicy(),
            timeout_seconds=300, payload={}))
        self.lease = self.kernel.claim_and_start('test', lease_seconds=1000, registry_revision='test')
        self.identity = ObservationIdentity('work', self.lease.attempt, self.lease.fence)
        self.journal = ObservationJournal(self.root / 'observations.sqlite3',
            kernel_path=self.kernel.db_path, source_id='store', clock=self.clock,
            options=ObservationOptions(write_timeout=.03))
        self.journal.bind_current(self.identity)

    def recorder(self, **kwargs):
        return ActivityRecorder(self.journal, self.identity, clock=self.clock,
                                monotonic=self.clock, **kwargs)

    def test_real_writer_contention_keeps_original_begin_end_and_raw_diagnostic(self):
        recorder = self.recorder()
        with closing(sqlite3.connect(self.journal.path)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            started = time.monotonic()
            with recorder.wait('memory', target='stage', resources={'capacity': 1}) as memory:
                self.clock.now = 101
                with recorder.wait('workspace', target='/tmp/workspace') as workspace:
                    self.clock.now = 102
                self.clock.now = 103
            self.assertLess(time.monotonic() - started, .03)
            self.assertEqual(memory['state'], 'captured')
            self.assertFalse(memory['persisted'])
            failed = recorder.flush()
            self.assertEqual(failed['state'], 'degraded')
            self.assertIn('database is locked', failed['error'])
            blocker.rollback()
        self.clock.now = 200
        recorder.heartbeat()
        self.assertEqual(recorder.flush()['state'], 'persisted')
        report = self.journal.inspect('work')
        waits = {row['wait_id']: row for row in report['waits']}
        self.assertEqual((waits[memory['wait_id']]['started_at'], waits[memory['wait_id']]['ended_at']), (100, 103))
        self.assertEqual((waits[workspace['wait_id']]['started_at'], waits[workspace['wait_id']]['ended_at']), (101, 102))
        self.assertTrue(all(row['state'] == 'ended' for row in waits.values()))
        self.assertFalse(report['complete'])
        self.assertGreater(report['collection_gaps'], 0)
        self.assertIn('database is locked', recorder.snapshot()['error'])
        coverage = [row for row in self.journal.events('work')['events'] if row['kind'] == 'wait_coverage']
        self.assertIn('database is locked', coverage[0]['payload']['error'])
        recorder.heartbeat()
        recorder.flush()
        self.assertFalse(self.journal.inspect('work')['complete'])
        self.assertIn('database is locked', recorder.snapshot()['error'])

    def test_final_close_retries_same_wait_ids_then_drains_coverage_diagnostic(self):
        recorder = self.recorder()
        with recorder.wait('memory') as receipt:
            self.clock.now = 105
        locked, release, failed = threading.Event(), threading.Event(), threading.Event()
        def lock_writer():
            with closing(sqlite3.connect(self.journal.path)) as connection:
                connection.execute('BEGIN IMMEDIATE')
                locked.set()
                release.wait(2)
                connection.rollback()
        locker = threading.Thread(target=lock_writer)
        locker.start()
        self.assertTrue(locked.wait(1))
        original = self.journal.write_batch
        batches, result = [], []
        def tracked(*args, **kwargs):
            batches.append((kwargs['sequence'], [(event['kind'], event['captured_at'], event['details'].get('wait_id'))
                                                for event in kwargs['events']]))
            try:
                return original(*args, **kwargs)
            except sqlite3.OperationalError:
                failed.set()
                raise
        try:
            with patch.object(self.journal, 'write_batch', side_effect=tracked):
                closer = threading.Thread(target=lambda: result.append(recorder.close(timeout=1)))
                closer.start()
                self.assertTrue(failed.wait(1))
                release.set()
                closer.join(2)
                self.assertFalse(closer.is_alive())
        finally:
            release.set()
            locker.join(1)
        self.assertTrue(result[0]['final_flush_persisted'])
        self.assertTrue(result[0]['source_closed'])
        self.assertEqual(batches[0], batches[1])
        wait = self.journal.inspect('work')['waits'][0]
        self.assertEqual((wait['wait_id'], wait['started_at'], wait['ended_at']), (receipt['wait_id'], 100, 105))
        self.assertIn('wait_coverage', [row['kind'] for row in self.journal.events('work')['events']])
        self.assertGreater(self.journal.inspect('work')['collection_gaps'], 0)

    def test_actual_lost_end_cannot_grant_stale_wait_exemption(self):
        options = ObservationOptions(queue_items=1, queue_bytes=4096)
        recorder = self.recorder(options=options)
        recorder.phase('handler_entered')
        recorder.flush()
        service = StallSupervisor(self.journal, self.kernel, clock=self.clock,
                                  clock_sample=self.clock.sample)
        policy = StallPolicy('policy', sample_interval=2, consecutive_windows=1,
                             wait_exemptions=('memory',))
        service.watch(self.identity, policy, target={})
        service.tick()
        with recorder.wait('memory'):
            recorder.flush()
            self.clock.now = 101
        # Overflow the captured end after its begin has reached SQLite.
        recorder.phase('unrelated-phase')
        recorder.flush()
        report = self.journal.inspect('work')
        self.assertEqual(report['waits'][0]['state'], 'waiting')
        self.assertGreater(report['collection_gaps'], 0)
        with self.journal._read_connection(3) as (connection, _):
            row = dict(connection.execute("SELECT * FROM obs_policies WHERE state='active'").fetchone())
        observed = service._observed(row, policy, self.kernel.supervision_status('work'), report)
        self.assertEqual(observed, (None, 'collection_unknown', None))
        self.clock.now = 102
        recorder.flush()
        service.tick()
        self.assertEqual(service.outbox(), ())
        self.assertIn('bounded queue', recorder.snapshot()['error'])
        self.assertLessEqual(recorder.snapshot()['queued_items'], 1)
        self.assertLessEqual(recorder.snapshot()['queued_bytes'], 4096)

    def test_invalid_details_are_dropped_without_poisoning_future_batches(self):
        recorder = self.recorder()
        with recorder.wait('memory', resources={'huge': 'x' * 100000}) as receipt:
            pass
        self.assertEqual(receipt['state'], 'unknown')
        recorder.report_bytes('stdout', b'after')
        self.assertEqual(recorder.flush()['state'], 'persisted')
        report = self.journal.inspect('work')
        self.assertEqual(report['waits'], [])
        self.assertEqual(report['metrics']['stdout_bytes']['count'], 5)
        self.assertFalse(report['complete'])
        self.assertLessEqual(len(recorder.snapshot()['error'].encode()), 512)
        self.assertEqual(recorder.flush()['state'], 'persisted')

    def test_locked_capture_returns_promptly_and_keeps_lost_end_unknown(self):
        recorder = self.recorder()
        manager = recorder.wait('memory')
        manager.__enter__()
        recorder.flush()
        held, release = threading.Event(), threading.Event()
        def hold_capture_lock():
            with recorder._lock:
                held.set()
                release.wait(1)
        holder = threading.Thread(target=hold_capture_lock)
        holder.start()
        self.assertTrue(held.wait(1))
        try:
            started = time.monotonic()
            manager.__exit__(None, None, None)
            with recorder.wait('workspace') as receipt:
                pass
            self.assertLess(time.monotonic() - started, .03)
            self.assertEqual(receipt['state'], 'unknown')
        finally:
            release.set()
            holder.join(1)
        self.assertEqual(recorder.flush()['state'], 'persisted')
        report = self.journal.inspect('work')
        self.assertEqual(report['waits'][0]['state'], 'waiting')
        self.assertFalse(report['complete'])
        self.assertGreater(report['collection_gaps'], 0)
        self.assertEqual(recorder.snapshot()['error'], 'wait capture busy')

    def test_end_projection_before_begin_is_idempotent_and_never_reopens_wait(self):
        details = {'wait_id': 'stable-wait', 'started_at': 100,
                   'wait': {'reason': 'memory', 'resources': {}}}
        def write(sequence, kind, captured):
            return self.journal.write_batch(self.identity, source_id='projection', sequence=sequence,
                metrics={}, captured_at=200, events=({'kind': kind, 'captured_at': captured, 'details': details},))
        self.assertTrue(write(1, 'wait_end', 105))
        self.assertFalse(write(1, 'wait_end', 105))
        self.assertTrue(write(2, 'wait_begin', 100))
        self.assertTrue(write(3, 'wait_end', 105))
        waits = self.journal.inspect('work')['waits']
        self.assertEqual(len(waits), 1)
        self.assertEqual((waits[0]['state'], waits[0]['started_at'], waits[0]['ended_at']), ('ended', 100, 105))

    def test_close_inside_wait_and_scope_replacement_never_restore_old_exemption(self):
        recorder = self.recorder(source_id='old', source_scope='handler')
        recorder.phase('handler_entered')
        policy = StallPolicy('owner', sample_interval=2, consecutive_windows=1,
                             wait_exemptions=('memory',))
        service = StallSupervisor(self.journal, self.kernel, clock=self.clock,
                                  clock_sample=self.clock.sample)
        service.watch(self.identity, policy, target={})
        with recorder.wait('memory'):
            recorder.flush()
            result = recorder.close(timeout=1)
            self.assertTrue(result['source_closed'])
        with self.journal._read_connection(3) as (connection, _):
            row = dict(connection.execute("SELECT * FROM obs_policies WHERE state='active'").fetchone())
        status = self.kernel.supervision_status('work')
        report = self.journal.inspect('work')
        self.assertEqual(report['waits'][0]['details']['_collector_source_id'], 'old')
        self.assertEqual(service._observed(row, policy, status, report), (None, 'collection_unknown', None))
        replacement = self.recorder(source_id='new', source_scope='handler')
        replacement.phase('handler_entered')
        replacement.flush()
        report = self.journal.inspect('work')
        self.assertEqual([source['source_id'] for source in report['sources']], ['new'])
        self.assertEqual(service._observed(row, policy, status, report), (None, 'collection_unknown', None))

    def test_close_deadline_after_first_commit_reports_remaining_observations(self):
        recorder = self.recorder(options=ObservationOptions(batch_summaries=1))
        with recorder.wait('memory'):
            pass
        elapsed = [0.0]
        original = self.journal.write_batch
        def write_then_expire(*args, **kwargs):
            receipt = original(*args, **kwargs)
            elapsed[0] = 2.0
            return receipt
        with patch.object(self.journal, 'write_batch', side_effect=write_then_expire), \
             patch.object(observability.activity.time, 'monotonic', side_effect=lambda: elapsed[0]):
            recorder._finish_close(1.0)
        self.assertFalse(recorder._close_result['final_flush_persisted'])
        self.assertFalse(recorder._close_result['source_closed'])
        self.assertEqual(recorder._close_result['reason'], 'remaining_observations')
        self.assertTrue(recorder._close_result['timed_out'])
        self.assertGreater(recorder.snapshot()['queued_items'], 0)
        self.assertEqual(self.journal.inspect('work')['waits'][0]['state'], 'waiting')

    def test_independent_collector_close_and_authoritative_child_wait_remain_separate(self):
        recorder = self.recorder(source_id='owner')
        other = self.recorder(source_id='other')
        recorder.phase('handler_entered')
        other.flush()
        self.assertTrue(other.close(timeout=1)['source_closed'])
        policy = StallPolicy('separate', wait_exemptions=('memory',))
        service = StallSupervisor(self.journal, self.kernel, clock=self.clock,
                                  clock_sample=self.clock.sample)
        service.watch(self.identity, policy, target={})
        with self.journal._read_connection(3) as (connection, _):
            row = dict(connection.execute("SELECT * FROM obs_policies WHERE state='active'").fetchone())
        status = self.kernel.supervision_status('work')
        with recorder.wait('memory'):
            recorder.flush()
            report = self.journal.inspect('work')
            self.assertEqual(service._observed(row, policy, status, report), (None, 'wait_exempt', 'memory'))
        recorder.flush()
        recorder.close(timeout=1)
        report = self.journal.inspect('work')
        report['child_waits'] = [{'state': 'open', 'reason': 'memory'}]
        self.assertEqual(service._observed(row, policy, status, report), (None, 'wait_exempt', 'memory'))

    def test_legacy_wait_cannot_forge_owner_and_malformed_projection_is_unknown(self):
        recorder = self.recorder(source_id='owner')
        recorder.phase('handler_entered')
        recorder.flush()
        policy = StallPolicy('legacy-owner', wait_exemptions=('memory',))
        service = StallSupervisor(self.journal, self.kernel, clock=self.clock,
                                  clock_sample=self.clock.sample)
        service.watch(self.identity, policy, target={})
        with self.journal._read_connection(3) as (connection, _):
            row = dict(connection.execute("SELECT * FROM obs_policies WHERE state='active'").fetchone())
        self.journal.record_wait(self.identity, 'legacy', details={
            'reason': 'memory', '_collector_source_id': []})
        status = self.kernel.supervision_status('work')
        report = self.journal.inspect('work')
        self.assertNotIn('_collector_source_id', report['waits'][0]['details'])
        self.assertEqual(service._observed(row, policy, status, report), (None, 'wait_exempt', 'memory'))
        report['waits'][0]['details']['_collector_source_id'] = []
        self.assertEqual(service._observed(row, policy, status, report), (None, 'collection_unknown', None))

    def test_projected_owner_size_is_validated_before_wait_enqueue(self):
        recorder = self.recorder(source_id='"' * 1000)
        with recorder.wait('memory', target='x' * 2500) as receipt:
            pass
        self.assertEqual(receipt['state'], 'unknown')
        recorder.report_bytes('stdout', b'after')
        self.assertEqual(recorder.flush()['state'], 'persisted')
        self.assertEqual(recorder.flush()['state'], 'persisted')
        report = self.journal.inspect('work')
        self.assertEqual(report['waits'], [])
        self.assertEqual(report['metrics']['stdout_bytes']['count'], 5)
        self.assertFalse(report['complete'])

    def test_caller_mutation_and_legacy_direct_wait_methods_keep_original_facts(self):
        recorder = self.recorder()
        resources = {'nested': {'capacity': 1}}
        with recorder.wait('workspace', resources=resources):
            resources['nested']['capacity'] = 99
            self.clock.now = 102
        recorder.flush()
        waits = self.journal.inspect('work')['waits']
        self.assertEqual(waits[0]['details']['resources']['nested']['capacity'], 1)
        self.journal.record_wait(self.identity, 'legacy', details={'reason': 'memory'}, started_at=110)
        self.journal.end_wait(self.identity, 'legacy', ended_at=111)
        legacy = next(row for row in self.journal.inspect('work')['waits'] if row['wait_id'] == 'legacy')
        self.assertEqual((legacy['state'], legacy['started_at'], legacy['ended_at']), ('ended', 110, 111))


if __name__ == '__main__':
    unittest.main()
