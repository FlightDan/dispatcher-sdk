"""Thread entry uses the same durable ACK rules as native workers."""

import json
from pathlib import Path
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel import Kernel


class HandlerEntryContentionTests(unittest.TestCase):
    def run_entry(self, *, exhaust=False, broken=False, control=False):
        root = retained_directory('sdk-entry-contention-')
        reached, release = threading.Event(), threading.Event()
        busy = threading.Event()
        calls, business, results, errors = [], [], [], []
        timeout = .3 if exhaust else 5

        def handler(payload, context):
            business.append(context.budget.to_dict())
            return {'original': 42}

        handler.__execution_kernel_revision__ = 'entry-contention-v1'
        with Kernel.open_sqlite(root/'kernel.sqlite3', {'handler': handler},
                                isolation_mode='thread') as runtime:
            runtime.submit(runtime.command('handler', execution_id='entry', idempotency_key='entry',
                correlation_id='entry', timeout_seconds=timeout, payload={}))
            confirm = runtime.kernel._checkpoint_handler_entry

            def confirmation(lease, envelope, **kwargs):
                reached.set()
                if not release.wait(3):
                    raise RuntimeError('test did not release entry confirmation')
                attempt = {'at': time.time(), 'budget': envelope.to_dict(), **kwargs}
                calls.append(attempt)
                try:
                    if broken:
                        with sqlite3.connect(runtime.kernel.db_path) as connection:
                            connection.execute('SELECT * FROM deliberately_missing_entry_table')
                    result = confirm(lease, envelope, **kwargs)
                    attempt['confirmed'] = result.to_dict()
                    return result
                except Exception as exc:
                    attempt.update(error=str(exc), cause=type(exc).__name__,
                                   sqlite_errorcode=getattr(exc, 'sqlite_errorcode', None))
                    if ((isinstance(exc, sqlite3.OperationalError) and str(exc) == 'database is locked')
                            or isinstance(exc, TimeoutError)):
                        busy.set()
                    raise

            def drive():
                try:
                    results.append(runtime.run_once(execution_id='entry'))
                except BaseException as exc:
                    errors.append({'cause': type(exc).__name__, 'error': str(exc)})

            with patch.object(runtime.kernel, '_checkpoint_handler_entry', side_effect=confirmation):
                driver = threading.Thread(target=drive)
                driver.start()
                writer = None
                control_lock = None
                try:
                    self.assertTrue(reached.wait(3), 'handler did not reach entry gate')
                    if control:
                        control_lock = runtime.kernel._control_lock(None)
                        control_lock.__enter__()
                    elif not broken:
                        writer = sqlite3.connect(runtime.kernel.db_path, timeout=.1)
                        writer.execute('BEGIN IMMEDIATE')
                    release.set()
                    if not broken:
                        self.assertTrue(busy.wait(2), 'test did not create an actual SQLite BUSY')
                        if exhaust:
                            cutoff = min(item['deadline_at'] - item['reserve_seconds']
                                         for item in calls[0]['budget']['constraints'])
                            time.sleep(max(0, cutoff - time.time()) + .03)
                finally:
                    release.set()
                    if control_lock is not None:
                        control_lock.__exit__(None, None, None)
                    if writer is not None:
                        writer.rollback()
                        writer.close()
                    driver.join(5)
                import dispatcher_sdk
                evidence = {'sdk_import': dispatcher_sdk.__file__, 'timeout_seconds': timeout,
                    'exhaust': exhaust, 'broken': broken, 'control_lock': control, 'attempts': calls, 'business_calls': business,
                    'driver_alive': driver.is_alive(), 'driver_errors': errors,
                    'outcomes': [item.to_dict() for item in results],
                    'limits': runtime.kernel.get_execution_limits('entry')}
                path = root/'evidence.json'
                path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
                print('handler_entry_contention_evidence=' + str(path), flush=True)
                self.assertFalse(driver.is_alive(), evidence)
                self.assertEqual(errors, [], evidence)
                self.assertEqual(len(results), 1, evidence)
                self.assertTrue(calls, evidence)
                self.assertTrue(all(call['budget']['constraints'] == calls[0]['budget']['constraints']
                                    for call in calls), evidence)
                self.assertTrue(all(call['budget']['started_at'] == calls[0]['budget']['started_at']
                                    for call in calls), evidence)
                return results[0], evidence

    def test_real_writer_release_retries_original_entry_and_calls_business_once(self):
        result, evidence = self.run_entry()
        self.assertEqual(result.state, 'succeeded', evidence)
        self.assertEqual(result.result.value, {'original': 42})
        self.assertEqual(len(evidence['business_calls']), 1, evidence)
        self.assertGreaterEqual(len(evidence['attempts']), 2, evidence)
        if evidence['attempts'][0]['sqlite_errorcode'] is not None:
            self.assertEqual(evidence['attempts'][0]['sqlite_errorcode'], sqlite3.SQLITE_BUSY)
        self.assertEqual(evidence['limits']['envelope']['constraints'],
                         evidence['attempts'][0]['budget']['constraints'])

    def test_busy_until_original_cutoff_never_invokes_business(self):
        result, evidence = self.run_entry(exhaust=True)
        self.assertEqual(result.state, 'timed_out', evidence)
        self.assertEqual(evidence['business_calls'], [], evidence)
        if 'sqlite_errorcode' in result.result.error.details['storage_error']:
            self.assertEqual(result.result.error.details['storage_error']['sqlite_errorcode'], sqlite3.SQLITE_BUSY)
        self.assertEqual(result.result.error.details['storage_error']['error'], 'database is locked')

    def test_non_contention_sqlite_error_is_preserved_without_retry(self):
        result, evidence = self.run_entry(broken=True)
        self.assertEqual(result.state, 'failed', evidence)
        self.assertEqual(evidence['business_calls'], [], evidence)
        self.assertEqual(len(evidence['attempts']), 1, evidence)
        self.assertEqual(result.result.error.code, 'entry_confirmation_unknown')
        if 'sqlite_errorcode' in result.result.error.details:
            self.assertEqual(result.result.error.details['sqlite_errorcode'], sqlite3.SQLITE_ERROR)
        self.assertIn('deliberately_missing_entry_table', result.result.error.message)
        self.assertEqual(result.result.error.details['error'], result.result.error.message)

    def test_kernel_control_lock_release_retries_same_entry(self):
        result, evidence = self.run_entry(control=True)
        self.assertEqual(result.state, 'succeeded', evidence)
        self.assertEqual(result.result.value, {'original': 42})
        self.assertEqual(len(evidence['business_calls']), 1, evidence)
        self.assertGreaterEqual(len(evidence['attempts']), 2, evidence)
        self.assertEqual(evidence['attempts'][0]['cause'], 'TimeoutError')
        self.assertEqual(evidence['attempts'][0]['error'], 'Kernel control lock admission timed out')
