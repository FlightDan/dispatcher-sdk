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
        ready, release = threading.Event(), threading.Event()
        def hold_lifecycle():
            with self.runtime._lifecycle_lock:
                ready.set()
                release.wait(.18)
        holder = threading.Thread(target=hold_lifecycle)
        holder.start()
        self.assertTrue(ready.wait(.5))
        before = time.monotonic()
        try:
            with patch.object(self.runtime.kernel, 'cancel', side_effect=self.observed_cancel):
                with self.assertRaises(sqlite3.OperationalError):
                    self.cancel(timeout=.25)
            self.assertTrue(self.calls)
            self.assertLess(self.calls[0]['timeout_seconds'], .08)
            self.assertTrue(all(call['at'] < before+.25 for call in self.calls))
            self.evidence['records'].append({'scenario': 'lifecycle_consumes_original_window',
                'original_timeout': .25, 'elapsed': time.monotonic()-before})
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
        try:
            with patch.object(self.runtime.kernel, 'cancel', side_effect=observe):
                with self.assertRaises(CASConflictError):
                    self.cancel(timeout=1)
            self.assertEqual(self.runtime.kernel.get('parent').state, 'running')
            self.assertEqual(self.runtime.kernel.supervision_status('parent')['progress_revision'], 1)
            self.assertEqual(len(self.calls), 2)
            self.assertTrue(all(call['expected_supervision'] == self.token for call in self.calls))
            self.evidence['records'].append({'scenario': 'progress_invalidates_original_token',
                'execution_state': 'running', 'original_token': self.token})
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
        self.assertIn('failure', stages)
        self.assertEqual(self.runtime.kernel.get('parent').state, 'running')

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
