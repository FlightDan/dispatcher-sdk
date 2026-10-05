"""Real idle WAL anchors belong to their flusher through physical release."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, SQLiteKernel
from dispatcher_sdk.execution_kernel.runtime import _ObservationCleanupPendingError
from dispatcher_sdk.observability import ActivityRecorder, ObservationIdentity, ObservationJournal, ObservationOptions
from tests._acceptance_evidence import retained_directory


class ObservationFlushAnchorTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-observation-flush-anchor-')
        self.options = ObservationOptions(flush_interval=30, write_timeout=.1, query_timeout=.1)
        self.identity = ObservationIdentity('original', 1, 1)
        self.records = []

    def tearDown(self):
        path = self.root/'evidence.json'
        path.write_text(json.dumps({'test': self.id(), 'write_timeout': .1,
            'event_wait_bound': 3, 'owned_join_bound': .05, 'records': self.records}, indent=2), encoding='utf-8')
        print('observation_flush_anchor_evidence=' + str(path), flush=True)

    def journal(self, name='observations', *, durability='full'):
        return ObservationJournal(self.root/(name+'.sqlite3'), kernel_path=self.root/'kernel.sqlite3',
            source_id='anchor-host', options=self.options, durability=durability)

    def recorder(self, journal):
        return ActivityRecorder(journal, self.identity, source_id='original-source', start=False)

    def stop_recorder(self, recorder):
        recorder.close(timeout=1)
        report = recorder._join_owned_workers(time.monotonic()+1)
        self.assertEqual(report['state'], 'closed')

    def test_managed_deferred_registration_closes_through_the_owned_flusher(self):
        journal = self.journal()
        registered = []
        register = journal.register_collector
        def capture_registration(*args, **kwargs):
            incarnation = register(*args, **kwargs)
            registered.append({'thread': threading.current_thread().name,
                'incarnation': incarnation, 'source_id': args[1]})
            return incarnation
        with patch.object(journal, 'register_collector', side_effect=capture_registration):
            recorder = ActivityRecorder(journal, self.identity, source_id='managed-source',
                source_scope='handler', bind_current=True, start=False,
                _defer_collector_registration=True)
            self.addCleanup(self.stop_recorder, recorder)
            self.assertEqual([], registered)
            recorder.phase('handler_entered')
            recorder.report_bytes('stdout', b'captured before the first flush')
            receipt = recorder.close(timeout=1)
        self.assertTrue(receipt['final_flush_persisted'], receipt)
        self.assertTrue(receipt['source_closed'], receipt)
        self.assertFalse(recorder._owned_workers_alive())
        self.assertEqual(1, len(registered))
        self.assertEqual('dispatcher-observation-flush', registered[0]['thread'])
        with closing(sqlite3.connect(journal.path, timeout=0)) as reader:
            row = reader.execute('SELECT state,incarnation,metrics_json FROM obs_sources WHERE source_id=?',
                ('managed-source',)).fetchone()
        self.assertEqual('closed', row[0])
        self.assertEqual(registered[0]['incarnation'], row[1])
        self.assertEqual(len(b'captured before the first flush'), json.loads(row[2])['stdout_bytes']['count'])
        self.records.append({'scenario': 'managed_close_before_first_flush',
            'registered': registered, 'close': receipt})

    def test_public_bind_current_keeps_construction_order_when_flushes_reverse(self):
        journal = self.journal()
        older = ActivityRecorder(journal, self.identity, source_id='older', source_scope='handler',
            bind_current=True)
        self.addCleanup(self.stop_recorder, older)
        newer = ActivityRecorder(journal, self.identity, source_id='newer', source_scope='handler',
            bind_current=True)
        self.addCleanup(self.stop_recorder, newer)
        self.assertLess(older.snapshot()['collector_incarnation'], newer.snapshot()['collector_incarnation'])
        newer.report_bytes('stdout', b'new')
        self.assertEqual('persisted', newer.flush()['state'])
        older.report_bytes('stdout', b'late old bytes')
        self.assertEqual('persisted', older.flush()['state'])
        report = journal.inspect(self.identity.execution_id)
        self.assertEqual(['newer'], [item['source_id'] for item in report['sources']])
        self.assertEqual(3, report['metrics']['stdout_bytes']['count'])
        self.records.append({'scenario': 'public_registration_order', 'report': report})

    def test_idle_anchor_has_no_snapshot_and_preserves_actual_writer_wal_and_durability(self):
        for durability, synchronous in (('full', 2), ('normal', 1)):
            with self.subTest(durability=durability):
                journal = self.journal(durability, durability=durability)
                recorder = self.recorder(journal)
                anchors, anchor_sql, writer_sql, probes, receipts, errors = [], [], [], [], [], []
                flushed = threading.Event()
                original_connect, original_flush = sqlite3.connect, ActivityRecorder.flush
                def connect(database, *args, **kwargs):
                    connection = original_connect(database, *args, **kwargs)
                    if str(database) == journal.path.as_uri()+'?mode=ro' and threading.current_thread().name == 'dispatcher-observation-flush':
                        anchors.append(connection)
                        connection.set_trace_callback(anchor_sql.append)
                    elif str(database) == journal.path.as_uri()+'?mode=rw':
                        connection.set_trace_callback(writer_sql.append)
                    return connection
                def flush(current):
                    receipt = original_flush(current)
                    if current is recorder:
                        receipts.append(receipt)
                        try:
                            anchor = anchors[0]
                            with closing(anchor.execute('SELECT source_id FROM obs_sources ORDER BY source_id')) as cursor:
                                sources = [row[0] for row in cursor.fetchall()]
                            probes.append({'in_transaction': anchor.in_transaction,
                                'total_changes': anchor.total_changes, 'sources': sources,
                                'owner_thread': threading.current_thread().name})
                        except BaseException as error:
                            errors.append(repr(error))
                        finally:
                            flushed.set()
                    return receipt
                record = {'scenario': 'idle_anchor_checkpoint', 'durability': durability}
                try:
                    with patch('dispatcher_sdk.observability.journal.sqlite3.connect', side_effect=connect), \
                            patch.object(ActivityRecorder, 'flush', flush):
                        recorder.start()
                        recorder.report_bytes('stdout', b'first')
                        recorder._wake.set()
                        self.assertTrue(flushed.wait(3))
                        self.assertEqual(errors, [])
                        self.assertEqual(receipts[-1]['state'], 'persisted')
                        self.assertEqual(len(anchors), 1)
                        self.assertFalse(probes[-1]['in_transaction'])
                        self.assertEqual(probes[-1]['total_changes'], 0)
                        # A real independent writer commits after the anchor's
                        # schema/source read, then a physical WAL truncate must
                        # succeed while that same anchor remains open and idle.
                        journal.write_batch(self.identity, source_id='independent-writer', sequence=1,
                            metrics={'heartbeat': {'count': 1, 'first_at': None, 'last_at': None}},
                            captured_at=time.time())
                        with closing(original_connect(journal.path, timeout=0)) as checkpoint:
                            self.assertEqual(checkpoint.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
                            record['checkpoint'] = checkpoint.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                            self.assertEqual(record['checkpoint'], (0, 0, 0))
                            self.assertEqual(checkpoint.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
                        flushed.clear()
                        recorder.report_bytes('stdout', b'second')
                        recorder._wake.set()
                        self.assertTrue(flushed.wait(3))
                        self.assertEqual(errors, [])
                        self.assertIn('independent-writer', probes[-1]['sources'])
                        self.assertFalse(probes[-1]['in_transaction'])
                        self.assertEqual(probes[-1]['total_changes'], 0)
                        self.assertIn('BEGIN IMMEDIATE', writer_sql)
                        self.assertIn('COMMIT', writer_sql)
                        self.assertIn('PRAGMA synchronous='+str(synchronous), writer_sql)
                        self.assertFalse(any(statement.lstrip().upper().startswith(
                            ('BEGIN', 'INSERT', 'UPDATE', 'DELETE', 'COMMIT')) for statement in anchor_sql), anchor_sql)
                        self.stop_recorder(recorder)
                finally:
                    self.stop_recorder(recorder)
                    record.update(probes=probes, receipts=receipts, errors=errors,
                                  anchor_sql=anchor_sql, writer_sql=writer_sql)
                    self.records.append(record)

    def test_actual_missing_file_anchor_admission_falls_back_after_real_file_restore(self):
        journal = self.journal()
        recorder = self.recorder(journal)
        parked = self.root/'temporarily-unavailable.sqlite3'
        journal.path.rename(parked)
        refused, flushed = threading.Event(), threading.Event()
        failures, receipts = [], []
        original_connect, original_flush = sqlite3.connect, ActivityRecorder.flush
        def connect(database, *args, **kwargs):
            try:
                return original_connect(database, *args, **kwargs)
            except sqlite3.OperationalError as error:
                if str(database) == journal.path.as_uri()+'?mode=ro' and threading.current_thread().name == 'dispatcher-observation-flush':
                    failures.append({'type': type(error).__name__, 'message': str(error),
                        'file_unavailable': not journal.path.exists(), 'refused_at': time.monotonic()})
                    refused.set()
                raise
        def flush(current):
            receipt = original_flush(current)
            if current is recorder:
                receipts.append(receipt)
                flushed.set()
            return receipt
        record = {'scenario': 'actual_unavailable_anchor_fallback'}
        try:
            with patch('dispatcher_sdk.observability.journal.sqlite3.connect', side_effect=connect), \
                    patch.object(ActivityRecorder, 'flush', flush):
                recorder.start()
                self.assertTrue(refused.wait(3), 'actual readonly admission did not fail')
                self.assertFalse(journal.path.exists())
                self.assertEqual(receipts, [])
                parked.rename(journal.path)
                record['restored_at'] = time.monotonic()
                recorder.report_bytes('stdout', b'ordinary-flush')
                recorder._wake.set()
                self.assertTrue(flushed.wait(3))
                self.assertEqual(receipts[-1]['state'], 'persisted')
                with closing(original_connect(journal.path, timeout=0)) as reader:
                    metrics = json.loads(reader.execute('SELECT metrics_json FROM obs_sources WHERE source_id=?',
                        ('original-source',)).fetchone()[0])
                    self.assertEqual(metrics['stdout_bytes']['count'], len(b'ordinary-flush'))
                    self.assertEqual(reader.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
                self.assertEqual(len(failures), 1)
                self.assertTrue(failures[0]['file_unavailable'])
                self.assertLessEqual(failures[0]['refused_at'], record['restored_at'])
                self.stop_recorder(recorder)
        finally:
            if parked.exists():
                parked.rename(journal.path)
            self.stop_recorder(recorder)
            record.update(admission_failures=failures, flush_receipts=receipts)
            self.records.append(record)

    def test_start_false_manual_flush_needs_no_idle_anchor(self):
        journal = self.journal()
        recorder = self.recorder(journal)
        anchors = []
        original_connect = sqlite3.connect
        def connect(database, *args, **kwargs):
            if str(database) == journal.path.as_uri()+'?mode=ro' and threading.current_thread().name == 'dispatcher-observation-flush':
                anchors.append(str(database))
            return original_connect(database, *args, **kwargs)
        try:
            with patch('dispatcher_sdk.observability.journal.sqlite3.connect', side_effect=connect):
                recorder.report_bytes('stdout', b'manual')
                receipt = recorder.flush()
                self.assertEqual(receipt['state'], 'persisted')
                self.assertIsNone(recorder._thread)
                self.assertEqual(anchors, [])
                with closing(original_connect(journal.path, timeout=0)) as reader:
                    metrics = json.loads(reader.execute('SELECT metrics_json FROM obs_sources WHERE source_id=?',
                        ('original-source',)).fetchone()[0])
                    self.assertEqual(metrics['stdout_bytes']['count'], len(b'manual'))
                self.records.append({'scenario': 'manual_start_false', 'receipt': receipt,
                    'anchor_admissions_during_manual_flush': len(anchors), 'persisted_metrics': metrics})
        finally:
            self.stop_recorder(recorder)

    def test_failed_close_retries_same_actual_connection_worker_without_flush_replay(self):
        journal = self.journal()
        recorder = self.recorder(journal)
        failed, retried, release, physically_closed = (threading.Event() for _ in range(4))
        anchors, close_calls, close_probes = [], [], []
        original_connect = sqlite3.connect
        class RetainedConnection(sqlite3.Connection):
            def close(connection):
                close_calls.append(connection)
                with closing(connection.execute('SELECT 1')) as cursor:
                    close_probes.append({'live_scalar': cursor.fetchone()[0],
                        'in_transaction': connection.in_transaction, 'thread': threading.current_thread().name})
                if len(close_calls) == 1:
                    failed.set()
                    raise sqlite3.OperationalError('fixture physical close unavailable')
                retried.set()
                if not release.wait(3):
                    raise RuntimeError('fixture did not release actual anchor close')
                super(RetainedConnection, connection).close()
                try:
                    connection.execute('SELECT 1')
                except sqlite3.ProgrammingError as error:
                    if 'closed database' in str(error):
                        physically_closed.set()
        def connect(database, *args, **kwargs):
            anchor = str(database) == journal.path.as_uri()+'?mode=ro' and threading.current_thread().name == 'dispatcher-observation-flush'
            if anchor:
                kwargs['factory'] = RetainedConnection
            connection = original_connect(database, *args, **kwargs)
            if anchor:
                anchors.append(connection)
            return connection
        record = {'scenario': 'failed_physical_close_same_owner'}
        try:
            with patch('dispatcher_sdk.observability.journal.sqlite3.connect', side_effect=connect), \
                    patch.object(journal, 'write_batch', wraps=journal.write_batch) as batches:
                recorder.start()
                worker = recorder._thread
                receipt = recorder.close(timeout=1)
                self.assertTrue(failed.wait(3))
                self.assertTrue(retried.wait(3))
                self.assertEqual(len(anchors), 1)
                self.assertTrue(all(connection is anchors[0] for connection in close_calls))
                self.assertIs(recorder._thread, worker)
                self.assertTrue(recorder._owned_workers_alive())
                pending = recorder._join_owned_workers(time.monotonic()+.05)
                self.assertEqual(pending['state'], 'pending')
                self.assertTrue(pending['flusher_alive'])
                self.assertFalse(physically_closed.is_set())
                before_batches, before_sequence = batches.call_count, recorder._sequence
                original_deadline = recorder._close_deadline
                self.assertIs(recorder.close(timeout=.05), receipt)
                self.assertEqual(recorder._close_deadline, original_deadline)
                self.assertEqual(batches.call_count, before_batches)
                release.set()
                report = recorder._join_owned_workers(time.monotonic()+1)
                self.assertEqual(report['state'], 'closed')
                self.assertTrue(physically_closed.is_set())
                self.assertFalse(recorder._owned_workers_alive())
                self.assertEqual(recorder._sequence, before_sequence)
                self.assertEqual(batches.call_count, before_batches)
                self.assertEqual(len(close_calls), 2)
                self.assertTrue(all(connection is anchors[0] for connection in close_calls))
                record.update(receipt=receipt, pending=pending, final_report=report,
                    batch_calls=before_batches, final_batch_calls=batches.call_count,
                    close_attempts=len(close_calls), original_close_deadline=original_deadline)
        finally:
            release.set()
            self.stop_recorder(recorder)
            record.update(close_probes=close_probes, physically_closed=physically_closed.is_set())
            self.records.append(record)

    def test_held_physical_anchor_close_retains_runtime_storage_and_capacity(self):
        entered, release, physically_closed = (threading.Event() for _ in range(3))
        recorders, owned_recorders, anchors, close_threads, calls = [], [], [], [], []
        def handler(payload, context):
            calls.append(context.command.execution_id)
            recorders.append(context.activity)
            context.activity.report_bytes('stdout', b'original-output')
            return {'original': 'completed'}
        handler.__execution_kernel_revision__ = 'flush-anchor-owned-runtime-v1'
        observation = tempfile.TemporaryDirectory(dir=self.root)
        path = self.root/'runtime.sqlite3'
        observation_path = journal_path = Path(observation.name)/'observations.sqlite3'
        runtime = Kernel.open_sqlite(path, {'work': handler}, isolation_mode='thread', max_thread_workers=1,
            allow_children=False, observation_path=str(observation_path), observation_options=self.options)
        runtime._temporary_observation = observation
        original_connect = sqlite3.connect
        class HeldConnection(sqlite3.Connection):
            def close(connection):
                close_threads.append(threading.current_thread())
                entered.set()
                if not release.wait(10):
                    raise RuntimeError('fixture did not release owning flusher close')
                super(HeldConnection, connection).close()
                physically_closed.set()
        def connect(database, *args, **kwargs):
            # Context installs its actual recorder before starting its flusher,
            # so this binds even when anchor admission precedes business entry.
            # Driver recorders on the same sidecar retain their ordinary close.
            candidate = (str(database) == journal_path.resolve().as_uri()+'?mode=ro'
                and threading.current_thread().name == 'dispatcher-observation-flush')
            handler_recorder = None
            if candidate:
                with runtime._thread_lock:
                    contexts = tuple(runtime._thread_contexts.values())
                handler_recorder = next((context.activity for context in contexts
                    if context.lease.execution_id == 'original'
                    and isinstance(context.activity, ActivityRecorder)), None)
            anchor = (handler_recorder is not None
                and threading.current_thread() is handler_recorder._thread)
            if anchor:
                kwargs['factory'] = HeldConnection
            connection = original_connect(database, *args, **kwargs)
            if anchor:
                anchors.append(connection)
                owned_recorders.append(handler_recorder)
            return connection
        record = {'scenario': 'runtime_storage_capacity_owned_by_anchor_close'}
        try:
            with patch('dispatcher_sdk.observability.journal.sqlite3.connect', side_effect=connect):
                runtime.submit(runtime.command('work', execution_id='original', idempotency_key='original',
                    correlation_id='original', timeout_seconds=10, payload={}))
                result = runtime.run_once()
                self.assertEqual(result.state, 'succeeded')
                self.assertEqual(result.result.value, {'original': 'completed'})
                self.assertTrue(entered.wait(3))
                self.assertEqual(len(anchors), 1)
                recorder = recorders[0]
                self.assertIs(owned_recorders[0], recorder)
                self.assertIs(close_threads[0], recorder._thread)
                self.assertTrue(recorder._owned_workers_alive())
                self.assertEqual(recorder._join_owned_workers(time.monotonic()+.05)['state'], 'pending')
                available = runtime._thread_slots.acquire(blocking=False)
                if available:
                    runtime._thread_slots.release()
                self.assertFalse(available, 'Runtime returned capacity while its anchor was physically live')
                began = time.monotonic()
                with self.assertRaises(_ObservationCleanupPendingError):
                    runtime.close()
                record['initial_close_elapsed'] = time.monotonic()-began
                self.assertLess(record['initial_close_elapsed'], 3)
                self.assertTrue(observation_path.exists())
                self.assertFalse(runtime.kernel._connection_closed)
                self.assertIn(recorder, runtime._retired_recorders)
                self.assertTrue(runtime._observation_cleanup_pending)
                self.assertEqual(runtime.kernel.get('original').to_dict(), result.to_dict())
                record['pending_cleanup_report'] = runtime._observation_cleanup_report
                release.set()
                self.assertEqual(recorder._join_owned_workers(time.monotonic()+1)['state'], 'closed')
                runtime.close()
                self.assertTrue(physically_closed.is_set())
                self.assertEqual(runtime._retired_recorders, [])
                self.assertFalse(runtime._observation_cleanup_pending)
                self.assertFalse(observation_path.exists())
                available = runtime._thread_slots.acquire(blocking=False)
                if available:
                    runtime._thread_slots.release()
                self.assertTrue(available, 'capacity remained charged after physical close completed')
                self.assertEqual(calls, ['original'])
                with SQLiteKernel(path) as reader:
                    self.assertEqual(reader.get('original').to_dict(), result.to_dict())
                record.update(original_result=result.to_dict(), business_calls=calls,
                    storage_removed_after_release=True, capacity_released=True)
        finally:
            release.set()
            for recorder in recorders:
                recorder._join_owned_workers(time.monotonic()+1)
            runtime.close()
            self.records.append(record)

    def test_setup_cursor_close_failure_retains_connection_before_ordinary_flush(self):
        journal = self.journal()
        recorder = self.recorder(journal)
        close_entered, release, physically_closed, flushed = (threading.Event() for _ in range(4))
        anchors, cursor_failures, receipts = [], [], []
        original_connect, original_flush = sqlite3.connect, ActivityRecorder.flush
        class SetupCursor:
            def __init__(self, cursor):
                self.cursor = cursor
            def __getattr__(self, name):
                return getattr(self.cursor, name)
            def close(self):
                cursor_failures.append('actual setup cursor close unavailable')
                raise sqlite3.OperationalError(cursor_failures[-1])
        class SetupConnection(sqlite3.Connection):
            def execute(connection, statement, *args, **kwargs):
                cursor = super(SetupConnection, connection).execute(statement, *args, **kwargs)
                if statement.startswith('SELECT singleton=1 AND version='):
                    return SetupCursor(cursor)
                return cursor
            def close(connection):
                close_entered.set()
                if not release.wait(3):
                    raise RuntimeError('fixture did not release failed-setup physical connection')
                super(SetupConnection, connection).close()
                physically_closed.set()
        def connect(database, *args, **kwargs):
            anchor = str(database) == journal.path.as_uri()+'?mode=ro' and threading.current_thread().name == 'dispatcher-observation-flush'
            if anchor:
                kwargs['factory'] = SetupConnection
            connection = original_connect(database, *args, **kwargs)
            if anchor:
                anchors.append(connection)
            return connection
        def flush(current):
            receipt = original_flush(current)
            if current is recorder:
                receipts.append(receipt)
                flushed.set()
            return receipt
        record = {'scenario': 'setup_cursor_release_before_fallback'}
        try:
            with patch('dispatcher_sdk.observability.journal.sqlite3.connect', side_effect=connect), \
                    patch.object(ActivityRecorder, 'flush', flush):
                recorder.start()
                recorder.report_bytes('stdout', b'after-release')
                recorder._wake.set()
                self.assertTrue(close_entered.wait(3))
                self.assertEqual(len(anchors), 1)
                self.assertEqual(len(cursor_failures), 1)
                self.assertEqual(receipts, [])
                self.assertFalse(flushed.is_set())
                self.assertTrue(recorder._owned_workers_alive())
                pending = recorder._join_owned_workers(time.monotonic()+.05)
                self.assertEqual(pending['state'], 'pending')
                self.assertFalse(physically_closed.is_set())
                release.set()
                self.assertTrue(flushed.wait(3))
                self.assertTrue(physically_closed.is_set())
                self.assertEqual(receipts[-1]['state'], 'persisted')
                self.assertEqual(len(anchors), 1, 'failed admission must discard its connection without reacquiring')
                with closing(original_connect(journal.path, timeout=0)) as reader:
                    metrics = json.loads(reader.execute('SELECT metrics_json FROM obs_sources WHERE source_id=?',
                        ('original-source',)).fetchone()[0])
                    self.assertEqual(metrics['stdout_bytes']['count'], len(b'after-release'))
                self.stop_recorder(recorder)
                record.update(pending_before_release=pending, receipt=receipts[0], persisted_metrics=metrics)
        finally:
            release.set()
            self.stop_recorder(recorder)
            record.update(cursor_failures=cursor_failures, physically_closed=physically_closed.is_set())
            self.records.append(record)


if __name__ == '__main__':
    unittest.main()
