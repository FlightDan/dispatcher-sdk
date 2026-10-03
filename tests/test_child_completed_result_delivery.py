"""On-time Kernel results survive delayed child response publication."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, HandlerExecutionError
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, DeadlineConstraint, sample_clock
from dispatcher_sdk.execution_kernel.children import HandlerChildren, ChildExecutionError, _RetryWindow, _Store
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ObservationJournal


def child(payload, context):
    context.activity.report_bytes('stdout', b'real-child-output')
    if payload.get('fail'):
        raise HandlerExecutionError('original_provider_failure', 'raw child failure',
                                    details={'provider': 'local-fixture'})
    return {'value': 9}


def parent(payload, context):
    try:
        value = context.children.run('child', {'fail': payload.get('fail', False)},
                                     request_id='delivery', timeout_seconds=2)
        return {'child': value}
    except ChildExecutionError as error:
        return {'code': error.code, 'message': str(error), 'child_error': error.result}


for handler in (parent, child):
    handler.__execution_kernel_revision__ = 'child-completed-result-delivery-v1'


class ChildCompletedResultDeliveryTests(unittest.TestCase):
    def test_public_child_result_survives_kernel_writer_held_until_wait_cutoff(self):
        from types import SimpleNamespace
        from dispatcher_sdk.execution_kernel.errors import ExecutionNotFoundError
        root = Path(tempfile.mkdtemp(prefix='sdk-child-delivery-writer-cutoff-'))
        witness = SimpleNamespace(waiting=threading.Event(), resume=threading.Event(), row=None,
                                  calls=[], outcomes=[], errors=[], rescues=[])

        def actual_child(payload, context):
            witness.calls.append(context.command.execution_id)
            return {'original': 42}

        def actual_parent(payload, context):
            return context.children.run('child', {}, request_id='one', timeout_seconds=5)

        for handler in (actual_parent, actual_child):
            handler.__execution_kernel_revision__ = 'child-writer-cutoff-delivery-v1'
        original = HandlerChildren._await
        original_completed = HandlerChildren._completed_result

        def gate(capability, row):
            witness.row = dict(row)
            witness.waiting.set()
            witness.resume.wait(3)
            return original(capability, row)

        def observe_rescue(capability, row, window):
            error = sys.exc_info()[1]
            witness.rescues.append({'exception_type': type(error).__name__, 'message': str(error)})
            return original_completed(capability, row, window)

        with Kernel.open_sqlite(root/'kernel.sqlite3', {'parent': actual_parent, 'child': actual_child},
                               isolation_mode='thread') as runtime:
            runtime.submit(runtime.command('parent', execution_id='parent', idempotency_key='parent',
                correlation_id='writer-cutoff', timeout_seconds=12, payload={}))
            def drive():
                try:
                    witness.outcomes.append(runtime.run_once(execution_id='parent'))
                except BaseException as error:
                    witness.errors.append(repr(error))
            with patch.object(HandlerChildren, '_await', gate), patch.object(
                    HandlerChildren, '_completed_result', observe_rescue):
                driver = threading.Thread(target=drive)
                driver.start()
                writer = None
                try:
                    self.assertTrue(witness.waiting.wait(2))
                    child_id = witness.row['child_execution_id']
                    end = time.monotonic() + 2
                    snapshot = None
                    while time.monotonic() < end:
                        try:
                            snapshot = runtime.kernel.get(child_id)
                            if snapshot.state == 'succeeded':
                                break
                        except ExecutionNotFoundError:
                            pass
                        time.sleep(.01)
                    self.assertIsNotNone(snapshot)
                    self.assertEqual(snapshot.state, 'succeeded')
                    child_result = snapshot.result.to_dict()
                    cutoff = min(item.work_deadline_at for item in
                        BudgetEnvelope.from_dict(json.loads(witness.row['budget_json'])).constraints)
                    writer = sqlite3.connect(runtime.kernel.db_path, timeout=.1)
                    writer.execute('BEGIN IMMEDIATE')
                    witness.resume.set()
                    time.sleep(max(0, cutoff - time.time() + .03))
                finally:
                    witness.resume.set()
                    if writer is not None:
                        writer.rollback()
                        writer.close()
                    driver.join(3)
            import dispatcher_sdk
            report = {'sdk_import': dispatcher_sdk.__file__, 'python': sys.executable,
                'command': 'PYTHONPATH=src:tests .venv/bin/python -m unittest '
                           'test_child_completed_result_delivery.ChildCompletedResultDeliveryTests.'
                           'test_public_child_result_survives_kernel_writer_held_until_wait_cutoff -v',
                'parent_timeout_seconds': 12, 'child_timeout_seconds': 5,
                'cutoff': cutoff, 'child_result': child_result, 'calls': witness.calls,
                'errors': witness.errors, 'rescue_original_errors': witness.rescues,
                'parent': witness.outcomes[0].to_dict() if witness.outcomes else None}
            evidence = root/'evidence.json'
            evidence.write_text(json.dumps(report, indent=2), encoding='utf-8')
            print('child_writer_cutoff_evidence=' + str(evidence), flush=True)
            self.assertFalse(driver.is_alive(), report)
            self.assertEqual(witness.errors, [], report)
            self.assertEqual(witness.calls, [child_id])
            self.assertEqual(len(witness.rescues), 1, report)
            self.assertIn(witness.rescues[0]['exception_type'], ('OperationalError', 'TimeoutError'))
            self.assertEqual(witness.outcomes[0].state, 'succeeded', report)
            self.assertEqual(witness.outcomes[0].result.value, child_result)
            self.assertLessEqual(child_result['completed_at'], cutoff)

    @unittest.skipUnless(os.name == 'posix', 'requires native POSIX process containment')
    def test_native_success_and_raw_failure_return_while_response_publication_is_held(self):
        evidence_root = Path(tempfile.mkdtemp(prefix='sdk-child-completed-delivery-evidence-'))
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                held = threading.Event()
                release = threading.Event()
                original_finish = _Store.finish

                def delayed_finish(store, row, *args, **kwargs):
                    held.set()
                    # Only optional cross-store publication is held. Original
                    # parent five-second and child two-second limits remain.
                    release.wait(4)
                    return original_finish(store, row, *args, **kwargs)

                with patch.object(_Store, 'finish', delayed_finish), Kernel.open_sqlite(
                        root/'kernel.sqlite3', {'parent': parent, 'child': child},
                        isolation_mode='process', child_capacity=1) as runtime:
                    runtime.submit(runtime.command('parent', execution_id='parent', idempotency_key='parent',
                        correlation_id='root', timeout_seconds=5, payload={'fail': fail}))
                    try:
                        result = runtime.run_once()
                        self.assertTrue(held.is_set(), result.result.to_dict())
                        self.assertEqual(result.state, 'succeeded', result.result.to_dict())
                        value = result.result.value
                        delivered = value['child_error'] if fail else value.get('child')
                        self.assertIsNotNone(delivered, value)
                        child_id = delivered['execution_id']
                        actual = runtime.kernel.get(child_id).result.to_dict()
                        self.assertEqual(delivered, actual)
                        if fail:
                            self.assertEqual(value['code'], 'original_provider_failure')
                            self.assertEqual(delivered['error']['details'], {'provider': 'local-fixture'})
                        else:
                            self.assertEqual(delivered['value'], {'value': 9})
                        row = runtime._child_service.store.request('parent', 'delivery')
                        self.assertEqual(row['state'], 'running')
                        self.assertIsNone(row['response_json'])
                        deadline = min(item.work_deadline_at for item in
                            BudgetEnvelope.from_dict(json.loads(row['budget_json'])).constraints)
                        self.assertLessEqual(delivered['completed_at'], deadline)
                        self.assertGreaterEqual(time.time(), deadline)
                        import dispatcher_sdk
                        evidence_path = evidence_root/('failure.json' if fail else 'success.json')
                        evidence_path.write_text(json.dumps({'sdk_import': dispatcher_sdk.__file__,
                            'parent_timeout_seconds': 5, 'child_timeout_seconds': 2,
                            'parent_result': result.result.to_dict(), 'authoritative_child_result': actual,
                            'request_while_publication_held': row, 'original_wait_work_cutoff': deadline},
                            indent=2), encoding='utf-8')
                        print('child_completed_delivery_evidence=' + str(evidence_path), flush=True)
                    finally:
                        release.set()

    @unittest.skipUnless(os.name == 'posix', 'requires native POSIX process containment')
    def test_native_child_completed_after_observers_original_cutoff_is_not_delivered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel, context, capability = self.direct(root)
            try:
                envelope = context.budget_envelope.derive(source='tool', origin_id='observe-late',
                                                          timeout_seconds=.1)
                window = _RetryWindow(envelope, kernel)
                row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
                       'parent_attempt': context.lease.attempt, 'parent_fence': context.lease.fence,
                       'child_execution_id': 'observed-child', 'action': 'observe'}
                # An observer cannot adopt the deadline of a separately owned
                # child. This real worker finishes after the short observer
                # cutoff while remaining within its own two-second budget.
                with Kernel.open_sqlite(kernel.db_path, {'child': child}, isolation_mode='process') as runtime:
                    runtime.submit(runtime.command('child', execution_id='observed-child',
                        idempotency_key='observed-child', correlation_id='root',
                        timeout_seconds=2, payload={}))
                    result = runtime.run_once(execution_id='observed-child')
                    self.assertEqual(result.state, 'succeeded', str(result))
                    self.assertGreater(result.result.completed_at,
                                       envelope.constraints[-1].work_deadline_at)
                    self.assertIsNone(capability._completed_result(row, window))
            finally:
                context.close()
                kernel.close()

    def direct(self, root):
        kernel = SQLiteKernel(str(root/'kernel.sqlite3'))
        command = ExecutionCommandV2(execution_id='parent', idempotency_key='parent',
            registry_revision='test', correlation_id='root', causation_id=None,
            handler_id='parent', handler_contract_version=1, retry_policy=RetryPolicy(),
            timeout_seconds=5, payload={})
        kernel.submit(command)
        lease = kernel.claim_and_start('owner')
        context = HandlerContext(command, lease, HandlerEffects(kernel, lease, lambda: True))
        context._enter_handler()
        journal = ObservationJournal(root/'observations.sqlite3', kernel_path=kernel.db_path,
                                     source_id='delivery-test')
        capability = HandlerChildren(kernel, command, lease, context.budget_envelope,
            {'capacity': 1, 'max_depth': 1, 'registry_revision': 'test', 'bindings': {'child': 'test'}},
            journal=journal)
        return kernel, context, capability

    def test_parent_revocation_wins_without_reading_child(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel, context, capability = self.direct(Path(directory))
            try:
                envelope = context.budget_envelope.derive(source='tool', origin_id='test-tool', timeout_seconds=.1)
                row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
                       'parent_attempt': context.lease.attempt, 'parent_fence': context.lease.fence,
                       'child_execution_id': 'unread-child', 'action': 'run'}
                window = _RetryWindow(envelope, kernel)
                kernel.cancel('parent', lease=context.lease, reason='test cancellation')
                with patch.object(kernel, 'get', wraps=kernel.get) as read:
                    with self.assertRaises(ChildExecutionError) as caught:
                        capability._completed_result(row, window)
                    self.assertEqual(caught.exception.code, 'parent_authority_revoked')
                    read.assert_not_called()
            finally:
                context.close()
                kernel.close()

    def test_late_child_and_unknown_clock_are_not_delivered(self):
        from dispatcher_sdk.execution_kernel.budget import ClockCheckpoint, BudgetClockUnknownError
        from types import SimpleNamespace
        for unknown in (False, True):
            with self.subTest(unknown=unknown), tempfile.TemporaryDirectory() as directory:
                kernel, context, capability = self.direct(Path(directory))
                try:
                    native = sample_clock()
                    envelope = BudgetEnvelope((DeadlineConstraint('tool', 'tool', native.wall_at + .1),), native)
                    window = _RetryWindow(envelope, kernel)
                    if unknown:
                        envelope = BudgetEnvelope(envelope.constraints, ClockCheckpoint(
                            native.wall_at, native.elapsed_at, 'different-boot'))
                        window.envelope = envelope
                    row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
                           'parent_attempt': context.lease.attempt, 'parent_fence': context.lease.fence,
                           'child_execution_id': 'child', 'action': 'observe'}
                    result = SimpleNamespace(execution_id='child', attempt=1, fence=1,
                        completed_at=native.wall_at + .2, to_dict=lambda: {})
                    snapshot = SimpleNamespace(state='succeeded', result=result, attempt=1, fence=1)
                    with patch.object(kernel, 'get', return_value=snapshot) as read:
                        if unknown:
                            with self.assertRaises(BudgetClockUnknownError):
                                capability._completed_result(row, window)
                            read.assert_not_called()
                        else:
                            self.assertIsNone(capability._completed_result(row, window))
                            read.assert_called_once_with('child')
                finally:
                    context.close()
                    kernel.close()

    def test_parent_revoked_during_result_read_wins_within_the_same_control_budget(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            kernel, context, capability = self.direct(Path(directory))
            try:
                envelope = context.budget_envelope.derive(source='tool', origin_id='test-tool', timeout_seconds=1)
                row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
                       'parent_attempt': context.lease.attempt, 'parent_fence': context.lease.fence,
                       'child_execution_id': 'child', 'action': 'observe'}
                window = _RetryWindow(envelope, kernel)
                result = SimpleNamespace(execution_id='child', attempt=1, fence=1,
                    completed_at=time.time(), to_dict=lambda: {'should_not_be_delivered': True})
                def concurrent_cancel(execution_id):
                    kernel.cancel('parent', lease=context.lease, reason='concurrent cancellation')
                    return SimpleNamespace(state='succeeded', result=result, attempt=1, fence=1)
                with patch.object(kernel, 'get', side_effect=concurrent_cancel):
                    with self.assertRaises(ChildExecutionError) as caught:
                        capability._completed_result(row, window)
                    self.assertEqual(caught.exception.code, 'parent_authority_revoked')
            finally:
                context.close()
                kernel.close()

    def test_transient_error_is_preserved_when_expired_window_has_no_proved_result(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel, context, capability = self.direct(Path(directory))
            try:
                native = sample_clock()
                envelope = BudgetEnvelope((DeadlineConstraint('tool', 'tool', native.wall_at - .01),), native)
                row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
                       'parent_attempt': context.lease.attempt, 'parent_fence': context.lease.fence,
                       'child_execution_id': 'missing-child', 'action': 'observe'}
                original = sqlite3.OperationalError('database is locked')
                with patch.object(capability.store, 'attach'), patch.object(capability, '_await_window',
                        side_effect=original):
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        capability._await(row)
                    self.assertIs(caught.exception, original)
            finally:
                context.close()
                kernel.close()

    def test_live_window_and_permanent_errors_do_not_enter_completed_result_rescue(self):
        for error in (sqlite3.OperationalError('database is locked'),
                      sqlite3.OperationalError('no such table: broken'),
                      ChildExecutionError('parent_authority_revoked', 'revoked')):
            with self.subTest(error=str(error)), tempfile.TemporaryDirectory() as directory:
                kernel, context, capability = self.direct(Path(directory))
                try:
                    envelope = context.budget_envelope.derive(source='tool', origin_id='live', timeout_seconds=1)
                    row = {'budget_json': json.dumps(envelope.to_dict())}
                    with patch.object(capability.store, 'attach'), patch.object(capability, '_await_window',
                            side_effect=error), patch.object(capability, '_completed_result') as rescue:
                        with self.assertRaises(type(error)) as caught:
                            capability._await(row)
                        self.assertIs(caught.exception, error)
                        rescue.assert_not_called()
                finally:
                    context.close()
                    kernel.close()


if __name__ == '__main__':
    unittest.main()
