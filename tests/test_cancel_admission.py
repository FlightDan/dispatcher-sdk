"""One cancellation deadline covers only proved uncommitted admission replay."""
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.observability import ObservationOptions
from dispatcher_sdk.execution_kernel.errors import CASConflictError, EffectRecoveryRequiredError
import dispatcher_sdk.execution_kernel.runtime as runtime_module


def unused(payload, context):
    raise AssertionError('cancellation fixture executed business')

unused.__execution_kernel_revision__ = 'cancel-admission-fixture-v1'


class CancelAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-cancel-admission-')
        self.runtime = Kernel.open_sqlite(self.root/'kernel.sqlite3', {'unused': unused}, isolation_mode='thread')
        self.addCleanup(self.runtime.close)
        self.runtime.submit(self.runtime.command('unused', execution_id='parent', idempotency_key='parent',
            correlation_id='cancel-admission', timeout_seconds=5, payload={}))
        self.lease = self.runtime.kernel.claim_and_start('manual-owner', execution_id='parent')
        self.token = self.runtime.kernel.register_stall_episode('parent', attempt=self.lease.attempt,
            fence=self.lease.fence, progress_revision=0, episode_id='original-episode', policy_version='v1')
        self.calls, self.raw_errors = [], []
        self.actual_cancel = self.runtime.kernel.cancel
        self.evidence = {'test': self.id(), 'runtime_import': runtime_module.__file__,
            'interpreter': sys.executable, 'kernel_path': self.runtime.kernel.db_path, 'records': []}

    def tearDown(self):
        self.evidence['cancel_attempts'] = self.calls
        path = self.root/'evidence.json'
        path.write_text(json.dumps(self.evidence, indent=2), encoding='utf-8')
        print('cancel_admission_evidence=' + str(path), flush=True)

    def observed_cancel(self, *args, **kwargs):
        kernel = self.runtime.kernel
        entry = {'at': time.monotonic(), 'timeout_seconds': kwargs['timeout_seconds'],
            'expected_revision': kwargs['expected_revision'],
            'expected_supervision': dict(kwargs['expected_supervision']) if kwargs.get('expected_supervision') else None,
            'changes_before': kernel._connection.total_changes}
        self.calls.append(entry)
        try:
            return self.actual_cancel(*args, **kwargs)
        except Exception as error:
            self.raw_errors.append(error)
            entry.update(error_type=type(error).__name__, error=str(error),
                sqlite_errorcode=getattr(error, 'sqlite_errorcode', None))
            raise
        finally:
            entry.update(changes_after=kernel._connection.total_changes,
                in_transaction_after=kernel._connection.in_transaction)

    def cancel(self, timeout=.5):
        return self.runtime.cancel('parent', expected_revision=self.lease.revision,
            expected_supervision=self.token, timeout_seconds=timeout)

    def writer(self):
        connection = sqlite3.connect(self.runtime.kernel.db_path, timeout=.1, check_same_thread=False)
        connection.execute('BEGIN IMMEDIATE')
        return connection

    def actual_busy(self):
        path = self.root/'busy.sqlite3'
        owner = sqlite3.connect(path)
        owner.execute('CREATE TABLE control(value)')
        owner.commit()
        reader = sqlite3.connect(path, timeout=.001)
        owner.execute('BEGIN EXCLUSIVE')
        try:
            try:
                reader.execute('SELECT * FROM control').fetchall()
            except sqlite3.OperationalError as error:
                self.assertEqual(str(error), 'database is locked')
                if hasattr(error, 'sqlite_errorcode'):
                    self.assertEqual(error.sqlite_errorcode, getattr(sqlite3, 'SQLITE_BUSY', 5))
                return error
            self.fail('exclusive writer did not block reader')
        finally:
            owner.rollback()
            owner.close()
            reader.close()

    def test_real_writer_release_retries_same_authority_within_original_deadline(self):
        writer = self.writer()
        def release():
            time.sleep(.22)
            writer.rollback()
            writer.close()
        releaser = threading.Thread(target=release)
        releaser.start()
        before = time.monotonic()
        try:
            with patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
                result = self.cancel(timeout=1)
        finally:
            releaser.join(1)
        elapsed = time.monotonic()-before
        self.assertEqual(result.state, 'cancelled')
        self.assertGreaterEqual(len(self.calls), 2)
        self.assertLess(elapsed, 1)
        self.assertTrue(all(call['expected_revision'] == self.lease.revision for call in self.calls))
        self.assertTrue(all(call['expected_supervision'] == self.token for call in self.calls))
        self.assertTrue(all(call['at'] < before+1 for call in self.calls))
        self.assertEqual(self.calls[0]['changes_before'], self.calls[0]['changes_after'])
        self.evidence['records'].append({'scenario': 'writer_release', 'original_timeout': 1,
            'elapsed': elapsed, 'result': result.to_dict()})

    def test_persistent_writer_exhausts_original_bound_and_retains_last_busy(self):
        writer = self.writer()
        before = time.monotonic()
        try:
            with patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    self.cancel(timeout=.25)
            self.assertIs(caught.exception, self.raw_errors[-1])
            self.assertEqual(str(caught.exception), 'database is locked')
            if hasattr(caught.exception, 'sqlite_errorcode'):
                self.assertEqual(caught.exception.sqlite_errorcode, getattr(sqlite3, 'SQLITE_BUSY', 5))
            self.assertEqual(self.runtime.kernel.get('parent').state, 'running')
            self.assertTrue(all(call['at'] < before+.25 for call in self.calls))
            self.assertLessEqual(len(self.calls), 3)
            self.evidence['records'].append({'scenario': 'persistent_writer', 'original_timeout': .25,
                'elapsed': time.monotonic()-before, 'error': str(caught.exception)})
        finally:
            writer.rollback()
            writer.close()

    def test_lifecycle_admission_spends_the_same_original_control_window(self):
        writer = self.writer()
        ready, admission_started, release = (threading.Event(), threading.Event(), threading.Event())
        admission_start = []

        def hold_lifecycle():
            with self.runtime._lifecycle_lock:
                ready.set()
                if not admission_started.wait(.5):
                    return
                release_at = admission_start[0] + .18
                while not release.is_set():
                    remaining = release_at - time.monotonic()
                    if remaining <= 0:
                        break
                    release.wait(remaining)

        holder = threading.Thread(target=hold_lifecycle)
        holder.start()
        self.assertTrue(ready.wait(.5))
        before = time.monotonic()
        original_bounded_lifecycle = self.runtime._bounded_lifecycle

        def observe_lifecycle_admission(timeout_seconds, **kwargs):
            admission_start.append(time.monotonic())
            admission_started.set()
            return original_bounded_lifecycle(timeout_seconds, **kwargs)

        try:
            with patch.object(self.runtime, '_bounded_lifecycle', side_effect=observe_lifecycle_admission), \
                    patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
                with self.assertRaises(sqlite3.OperationalError):
                    self.cancel(timeout=.25)
            self.assertTrue(self.calls)
            first_call = self.calls[0]
            elapsed_to_first_call = first_call['at'] - before
            lifecycle_wait = first_call['at'] - admission_start[0]
            remaining_after_minimum_lifecycle_wait = .25 - .18
            self.evidence['records'].append({'scenario': 'lifecycle_consumes_original_window',
                'original_timeout': .25, 'elapsed_to_first_call': elapsed_to_first_call,
                'lifecycle_wait': lifecycle_wait,
                'remaining_after_minimum_lifecycle_wait': remaining_after_minimum_lifecycle_wait,
                'first_kernel_timeout': first_call['timeout_seconds']})
            self.assertGreaterEqual(lifecycle_wait, .18)
            self.assertLess(first_call['timeout_seconds'], .08)
            self.assertLessEqual(first_call['timeout_seconds'], remaining_after_minimum_lifecycle_wait)
            self.assertTrue(all(call['at'] < before+.25 for call in self.calls))
        finally:
            release.set()
            holder.join(1)
            writer.rollback()
            writer.close()

    def test_progress_committed_before_retry_rejects_original_stall_token(self):
        writer = self.writer()
        first_busy = threading.Event()
        def observe(*args, **kwargs):
            try:
                return self.observed_cancel(*args, **kwargs)
            except sqlite3.OperationalError:
                first_busy.set()
                raise
        def progress():
            first_busy.wait(1)
            # This actual authoritative progress update becomes visible
            # atomically when the external writer releases admission.
            writer.execute('UPDATE kernel_supervision SET progress_revision=1,progress_at=?, '
                'episode_id=NULL,episode_progress_revision=NULL WHERE execution_id=?', (time.time(), 'parent'))
            writer.execute('INSERT INTO kernel_progress_keys VALUES(?,?,?,?)',
                ('parent', self.lease.attempt, 'between-attempts', 1))
            writer.commit()
            writer.close()
        updater = threading.Thread(target=progress)
        updater.start()
        began = time.monotonic()
        try:
            with patch.object(self.runtime.kernel, 'cancel', side_effect=observe):
                with self.assertRaises(CASConflictError):
                    self.cancel(timeout=1)
            self.assertEqual(self.runtime.kernel.get('parent').state, 'running')
            self.assertEqual(self.runtime.kernel.supervision_status('parent')['progress_revision'], 1)
            self.evidence['records'].append({'scenario': 'progress_invalidates_original_token',
                'execution_state': 'running', 'original_token': self.token,
                'original_timeout': 1, 'began': began, 'elapsed': time.monotonic()-began})
            # A real commit can span more than one short admission attempt.
            # Every rejected attempt must preserve authority and spend the
            # same caller window; the final stale token must never cancel.
            self.assertGreaterEqual(len(self.calls), 2)
            self.assertTrue(all(call['expected_supervision'] == self.token for call in self.calls))
            self.assertTrue(all(call['at'] < began+1 for call in self.calls))
            for call in self.calls[:-1]:
                self.assertEqual(call['error_type'], 'OperationalError')
                self.assertEqual(call['error'], 'database is locked')
                self.assertEqual(call['changes_before'], call['changes_after'])
                self.assertFalse(call['in_transaction_after'])
            self.assertEqual(self.calls[-1]['error_type'], 'CASConflictError')
        finally:
            updater.join(1)
            if updater.is_alive():
                writer.rollback()
                writer.close()

    def test_exact_legacy_sqlite_messages_retry_but_other_no_code_errors_do_not(self):
        for message in ('database is locked', 'database table is locked', 'database schema is locked'):
            with self.subTest(message=message):
                raw = sqlite3.OperationalError(message)
                self.assertFalse(hasattr(raw, 'sqlite_errorcode'))
                calls = []
                def unavailable_once(*args, **kwargs):
                    calls.append(kwargs)
                    if len(calls) == 1:
                        raise raw
                    return self.runtime.kernel.get('parent')
                with patch.object(self.runtime.kernel, 'cancel', side_effect=unavailable_once):
                    self.assertEqual(self.cancel().state, 'running')
                self.assertEqual(len(calls), 2)
                self.assertTrue(all(call['expected_supervision'] == self.token for call in calls))
        for message, code in (('database is locked: control', None), ('disk I/O error', None),
                              ('database is locked', 10)):
            with self.subTest(message=message, code=code):
                raw = sqlite3.OperationalError(message)
                if code is not None:
                    raw.sqlite_errorcode = code
                with patch.object(self.runtime.kernel, 'cancel', side_effect=raw) as operation:
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        self.cancel()
                self.assertIs(caught.exception, raw)
                self.assertEqual(operation.call_count, 1)
        self.assertEqual(self.runtime.kernel.get('parent').state, 'running')

    def test_transaction_write_followed_by_busy_is_not_retried(self):
        raw = self.actual_busy()
        calls = []
        def wrote_then_failed(*args, **kwargs):
            calls.append(kwargs)
            self.runtime.kernel.verify(self.lease)
            raise raw
        with patch.object(self.runtime.kernel, 'cancel', side_effect=wrote_then_failed):
            with self.assertRaises(sqlite3.OperationalError) as caught:
                self.cancel()
        self.assertIs(caught.exception, raw)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.runtime.kernel.get('parent').state, 'running')

    def test_known_commit_followed_by_busy_is_not_replayed(self):
        raw = self.actual_busy()
        calls = []
        def committed_then_failed(*args, **kwargs):
            calls.append(kwargs)
            self.actual_cancel(*args, **kwargs)
            raise raw
        with patch.object(self.runtime.kernel, 'cancel', side_effect=committed_then_failed):
            with self.assertRaises(sqlite3.OperationalError) as caught:
                self.cancel()
        self.assertIs(caught.exception, raw)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.runtime.kernel.get('parent').state, 'cancelled')
        local = self.runtime.observe('parent')['local_cancellation_diagnostics']
        self.assertFalse(local['persisted'])
        self.assertEqual(local['notes'][-1]['details']['authority'], 'unknown')
        self.assertEqual(local['notes'][-1]['details']['message'], str(raw))

    def test_retained_transaction_after_busy_is_not_retried(self):
        raw = self.actual_busy()
        calls = []
        def retained_transaction(*args, **kwargs):
            calls.append(kwargs)
            self.runtime.kernel._connection.execute('BEGIN IMMEDIATE')
            raise raw
        try:
            with patch.object(self.runtime.kernel, 'cancel', side_effect=retained_transaction):
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    self.cancel()
            self.assertIs(caught.exception, raw)
            self.assertEqual(len(calls), 1)
            self.assertTrue(self.runtime.kernel._connection.in_transaction)
        finally:
            self.runtime.kernel._connection.rollback()

    def test_committed_effect_recovery_is_not_retried_and_preserves_cleanup_path(self):
        self.runtime.kernel.prepare_effect(self.lease, effect_id='unfinished', name='external', request={})
        with patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
            with self.assertRaises(EffectRecoveryRequiredError):
                self.cancel()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.runtime.kernel.get('parent').state, 'recovery_required')

    def test_receipt_setup_cannot_grant_fresh_control_time(self):
        stages = []
        def slow_begin(*args, **kwargs):
            time.sleep(.13)
            return 'receipt'
        self.runtime.cancellation_journal = SimpleNamespace(_begin=slow_begin,
            _record=lambda receipt, stage, evidence, **kw: stages.append(stage))
        with patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
            with self.assertRaises(TimeoutError):
                self.cancel(timeout=.12)
        self.assertEqual(self.calls, [])
        self.assertEqual(stages, [])
        local = self.runtime.observe('parent')['local_cancellation_diagnostics']
        self.assertEqual([note['phase'] for note in local['notes']],
                         ['cancellation_requested', 'cancellation_failure'])
        self.assertTrue(all(not note['persisted'] for note in local['notes']))
        self.assertTrue(all(note['request_receipt_id'] == 'receipt' and note['request_persisted']
                            for note in local['notes']))
        self.assertEqual(self.runtime.kernel.get('parent').state, 'running')

    def test_failed_cancel_local_diagnostics_are_bounded_without_journal_io(self):
        options = ObservationOptions(queue_items=2, queue_bytes=1200, query_bytes=4096)
        with Kernel.open_sqlite(self.root/'bounded.sqlite3', {'unused': unused},
                               isolation_mode='thread', observation_options=options) as runtime:
            queued = runtime.submit(runtime.command('unused', execution_id='bounded',
                idempotency_key='bounded', correlation_id='bounded', timeout_seconds=5, payload={}))
            raw = RuntimeError('original failure ' + 'x' * 16000)
            with patch.object(runtime.kernel, 'cancel', side_effect=raw), \
                    patch.object(runtime, '_diagnostic_note') as notes, \
                    patch.object(runtime_module.ObservationJournal, 'phase') as phases:
                for _ in range(3):
                    with self.assertRaises(RuntimeError) as caught:
                        runtime.cancel('bounded', expected_revision=queued.revision, timeout_seconds=.2)
                    self.assertIs(caught.exception, raw)
                notes.assert_not_called()
                phases.assert_not_called()
            with patch.object(runtime, 'observation_journal', None), \
                    patch.object(runtime_module.sqlite3, 'connect', side_effect=AssertionError('unexpected query SQL')):
                report = runtime.observe('bounded')
            self.assertFalse(report['complete'])
            local = report['local_cancellation_diagnostics']
            self.assertLessEqual(len(local['notes']), 2)
            self.assertTrue(local['loss_observed'])
            self.assertEqual(local['loss_scope'], 'runtime')
            self.assertLessEqual(len(json.dumps(report, ensure_ascii=False).encode('utf-8')), options.query_bytes)
            self.assertEqual(runtime.kernel.get('bounded').revision, queued.revision)
            self.evidence['records'].append({'scenario': 'bounded_local_failure_no_storage', 'report': report})

    def test_successful_cancel_keeps_local_facts_when_optional_writers_exhaust_its_allowance(self):
        writers = []
        try:
            for path in (self.runtime._settlement_journal.path, self.runtime.observation_journal.path):
                writer = sqlite3.connect(path, timeout=.1)
                writers.append(writer)
                writer.execute('BEGIN IMMEDIATE')
            before = time.monotonic()
            with patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
                result = self.cancel(timeout=.3)
            elapsed = time.monotonic() - before
            self.assertEqual('cancelled', result.state)
            self.assertEqual(1, len(self.calls))
            # Two independently held writers must share the original allowance;
            # each cancellation phase cannot start another pair of .1s waits.
            self.assertLess(elapsed, .6)
        finally:
            for writer in writers:
                try:
                    writer.rollback()
                finally:
                    writer.close()
        report = self.runtime.observe('parent')
        local = report['local_cancellation_diagnostics']
        self.assertFalse(report['complete'])
        self.assertFalse(local['persisted'])
        notes = {item['phase']: item for item in local['notes']}
        self.assertEqual({'cancellation_requested', 'cancellation_authority_revoked',
            'cancellation_process_cleanup', 'cancellation_remote_cleanup'}, set(notes))
        for note in notes.values():
            self.assertFalse(note['persisted'])
            self.assertNotIn('persisted_at', note)
            self.assertEqual({'execution_id': 'parent', 'attempt': self.lease.attempt,
                'fence': self.lease.fence}, note['identity'])
        self.assertLessEqual(notes['cancellation_requested']['captured_at'],
                             notes['cancellation_authority_revoked']['captured_at'])
        self.assertEqual([], self.runtime._settlement_journal.inspect_notes('parent')['notes'])
        self.assertEqual('cancelled', self.runtime.kernel.get('parent').state)
        self.evidence['records'].append({'scenario': 'successful_cancel_optional_writers_held',
            'original_timeout': .3, 'elapsed': elapsed, 'report': report})

    def test_failed_cancel_historical_filters_and_restart_do_not_claim_durability(self):
        path = self.root/'historical.sqlite3'
        with Kernel.open_sqlite(path, {'unused': unused}, isolation_mode='thread') as runtime:
            queued = runtime.submit(runtime.command('unused', execution_id='historical',
                idempotency_key='historical', correlation_id='historical', timeout_seconds=5, payload={}))
            raw = RuntimeError('control operation raised before returning')
            with patch.object(runtime.kernel, 'cancel', side_effect=raw):
                with self.assertRaises(RuntimeError) as caught:
                    runtime.cancel('historical', expected_revision=queued.revision)
                self.assertIs(caught.exception, raw)
            lease = runtime.kernel.claim_and_start('manual-owner', execution_id='historical')
            self.assertGreater(lease.attempt, queued.attempt)
            for filters in ({'attempt': queued.attempt}, {'fence': queued.fence},
                            {'attempt': queued.attempt, 'fence': queued.fence}):
                report = runtime.observe('historical', **filters)
                local = report['local_cancellation_diagnostics']
                self.assertEqual(len(local['notes']), 2)
                self.assertTrue(all(note['identity'] == {'execution_id': 'historical',
                    'attempt': queued.attempt, 'fence': queued.fence} for note in local['notes']))
                self.assertTrue(all(note['identity_scope'] == 'kernel_execution' and
                                    note['workflow_metadata'] == 'unknown' for note in local['notes']))
                self.evidence['records'].append({'scenario': 'historical_local_failure',
                    'filters': filters, 'local': local})
            self.assertNotIn('local_cancellation_diagnostics', runtime.observe('historical'))
        with Kernel.open_sqlite(path, {'unused': unused}, isolation_mode='thread') as reopened:
            self.assertNotIn('local_cancellation_diagnostics',
                             reopened.observe('historical', attempt=queued.attempt, fence=queued.fence))
            self.assertEqual(reopened.kernel.get('historical').attempt, lease.attempt)

    def test_secondary_diagnostic_rendering_cannot_replace_original_error(self):
        class Unrenderable(RuntimeError):
            def __str__(self):
                raise ValueError('secondary rendering failure')
        raw = Unrenderable()
        with patch.object(self.runtime.kernel, 'cancel', side_effect=raw):
            with self.assertRaises(Unrenderable) as caught:
                self.cancel()
        self.assertIs(caught.exception, raw)
        local = self.runtime.observe('parent')['local_cancellation_diagnostics']
        self.assertTrue(local['loss_observed'])
        self.assertEqual(local['loss_scope'], 'runtime')

    def test_real_kernel_lock_admission_release_uses_the_original_deadline(self):
        ready = threading.Event()
        def hold():
            with self.runtime.kernel._lock:
                ready.set()
                time.sleep(.22)
        holder = threading.Thread(target=hold)
        holder.start()
        self.assertTrue(ready.wait(.5))
        before = time.monotonic()
        try:
            with patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
                result = self.cancel(timeout=1)
            self.assertEqual(result.state, 'cancelled')
            self.assertEqual(len(self.calls), 1)
            self.assertGreater(self.calls[0]['at']-before, .20)
            self.assertLess(time.monotonic()-before, 1)
            self.evidence['records'].append({'scenario': 'kernel_lock_admission_release',
                'original_timeout': 1, 'elapsed': time.monotonic()-before})
        finally:
            holder.join(1)

    def test_receipt_evidence_failure_is_surfaced_after_revocation_without_business_retry(self):
        raw = self.actual_busy()
        authority = threading.Event()
        authority.set()
        self.runtime._thread_authority_by_execution[('parent', self.lease.attempt, self.lease.fence)] = authority
        def failed_begin(*args, **kwargs):
            raise raw
        self.runtime.cancellation_journal = SimpleNamespace(_begin=failed_begin)
        with patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
            with self.assertRaises(RuntimeError) as caught:
                self.cancel()
        self.assertIs(caught.exception.__cause__, raw)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.runtime.kernel.get('parent').state, 'cancelled')
        self.assertFalse(authority.is_set())


if __name__ == '__main__':
    unittest.main()
