"""On-time Kernel results survive delayed child response publication."""
from __future__ import annotations

from dataclasses import replace
import json
import math
import os
import sqlite3
import sys
from pathlib import Path
import tempfile
import threading
import time
import traceback
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel import Kernel, HandlerExecutionError
from dispatcher_sdk.execution_kernel import child_factual_read as factual
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, DeadlineConstraint, sample_clock
from dispatcher_sdk.execution_kernel.children import HandlerChildren, ChildExecutionError, _RetryWindow, _Store
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, ExecutionResultV2, RetryPolicy
from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ObservationJournal


def child(payload, context):
    if 'return_after' in payload:
        time.sleep(max(0, payload['return_after'] - time.time()))
    context.activity.report_bytes('stdout', b'real-child-output')
    if payload.get('fail'):
        raise HandlerExecutionError('original_provider_failure', 'raw child failure',
                                    details={'provider': 'local-fixture'})
    return {'value': 9}


def parent(payload, context):
    try:
        value = context.children.run('child', {'fail': payload.get('fail', False)},
                                     request_id='delivery', timeout_seconds=payload.get('child_timeout', 2))
        return {'child': value}
    except ChildExecutionError as error:
        if payload.get('parent_diagnostic_path'):
            Path(payload['parent_diagnostic_path']).write_text(json.dumps({
                'type': type(error).__module__ + '.' + type(error).__qualname__,
                'message': str(error), 'code': error.code,
                'traceback': traceback.format_exc(limit=16)[-16384:],
            }, indent=2), encoding='utf-8')
        return {'code': error.code, 'message': str(error), 'child_error': error.result}
    except Exception as error:
        if payload.get('parent_diagnostic_path'):
            Path(payload['parent_diagnostic_path']).write_text(json.dumps({
                'type': type(error).__module__ + '.' + type(error).__qualname__,
                'message': str(error), 'traceback': traceback.format_exc(),
                'budget_sample_token': getattr(error, 'budget_sample_token', None),
                'budget_sample_envelope': (None if getattr(error, 'budget_sample_envelope', None) is None
                    else error.budget_sample_envelope.to_dict()),
            }, indent=2), encoding='utf-8')
        raise


for handler in (parent, child):
    handler.__execution_kernel_revision__ = 'child-completed-result-delivery-v1'


class ChildCompletedResultDeliveryTests(unittest.TestCase):
    def test_public_child_result_survives_kernel_writer_held_until_wait_cutoff(self):
        from types import SimpleNamespace
        from dispatcher_sdk.execution_kernel.errors import ExecutionNotFoundError
        root = retained_directory('sdk-child-delivery-writer-cutoff-')
        witness = SimpleNamespace(waiting=threading.Event(), resume=threading.Event(), row=None,
                                  calls=[], outcomes=[], errors=[], rescues=[], writer={})

        def retain_observations():
            # Also runs when setup or a timing assertion fails before the
            # normal completed-result report can be assembled.
            path = root / 'observations.json'
            path.write_text(json.dumps({'row': witness.row, 'calls': witness.calls,
                'errors': witness.errors, 'rescues': witness.rescues, 'writer': witness.writer,
                'outcomes': [item.to_dict() for item in witness.outcomes]}, indent=2), encoding='utf-8')
            print('child_writer_cutoff_observations=' + str(path), flush=True)

        self.addCleanup(retain_observations)

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
            owner = window._pending_sample_owner or window._capture
            entry = {'exception_type': type(error).__name__, 'message': str(error),
                'code': getattr(error, 'code', None), 'began': time.monotonic(),
                'proof_deadline': window._delivery_deadline,
                'window_budget': window.envelope.to_dict(),
                'owner_pending': (None if owner is None or owner._pending is None else
                    {'token': owner._pending[0], 'captured': None if owner._pending[1] is None
                        else owner._pending[1].to_dict()})}
            witness.rescues.append(entry)
            try:
                delivered = original_completed(capability, row, window)
                entry['delivered'] = delivered
                return delivered
            except BaseException as proof_error:
                entry['proof_error'] = {'type': type(proof_error).__name__,
                    'message': str(proof_error), 'traceback': traceback.format_exc(limit=16)[-16384:]}
                raise
            finally:
                entry['returned'] = time.monotonic()

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
                    witness.writer['held_at'] = time.monotonic()
                    witness.resume.set()
                    time.sleep(max(0, cutoff - time.time() + .03))
                finally:
                    witness.resume.set()
                    if writer is not None:
                        witness.writer['release_started'] = time.monotonic()
                        writer.rollback()
                        writer.close()
                        witness.writer['release_returned'] = time.monotonic()
                    driver.join(3)
            import dispatcher_sdk
            report = {'sdk_import': dispatcher_sdk.__file__, 'python': sys.executable,
                'command': 'PYTHONPATH=src:tests .venv/bin/python -m unittest '
                           'test_child_completed_result_delivery.ChildCompletedResultDeliveryTests.'
                           'test_public_child_result_survives_kernel_writer_held_until_wait_cutoff -v',
                'parent_timeout_seconds': 12, 'child_timeout_seconds': 5,
                'cutoff': cutoff, 'child_result': child_result, 'calls': witness.calls,
                'errors': witness.errors, 'rescue_original_errors': witness.rescues, 'writer': witness.writer,
                'parent': witness.outcomes[0].to_dict() if witness.outcomes else None}
            evidence = root/'evidence.json'
            evidence.write_text(json.dumps(report, indent=2), encoding='utf-8')
            print('child_writer_cutoff_evidence=' + str(evidence), flush=True)
            self.assertFalse(driver.is_alive(), report)
            self.assertEqual(witness.errors, [], report)
            self.assertEqual(witness.calls, [child_id])
            self.assertEqual(len(witness.rescues), 1, report)
            rescue = witness.rescues[0]
            if rescue['exception_type'] == 'ChildExecutionError':
                self.assertEqual(rescue['code'], 'child_wait_timeout')
            elif rescue['exception_type'] == 'BudgetClockUnknownError':
                self.assertEqual(rescue['message'], 'budget_clock_sample_unresolved:sampling')
            else:
                self.assertIn(rescue['exception_type'], ('OperationalError', 'TimeoutError'))
            self.assertEqual(witness.outcomes[0].state, 'succeeded', report)
            self.assertEqual(witness.outcomes[0].result.value, child_result)
            self.assertLessEqual(child_result['completed_at'], cutoff)

    @unittest.skipUnless(os.name == 'posix', 'requires native POSIX process containment')
    def test_native_success_and_raw_failure_return_while_response_publication_is_held(self):
        evidence_root = retained_directory('sdk-child-completed-delivery-evidence-')
        for fail in (False, True):
            with self.subTest(fail=fail):
                case = 'failure' if fail else 'success'
                root = evidence_root/case
                root.mkdir()
                evidence_path = evidence_root/(case + '.json')
                held = threading.Event()
                release = threading.Event()
                finish_lock = threading.Lock()
                finish_calls = []
                original_finish = _Store.finish

                def delayed_finish(store, row, *args, **kwargs):
                    cutoff = min(item.work_deadline_at for item in
                        BudgetEnvelope.from_dict(json.loads(row['budget_json'])).constraints)
                    published = kwargs.get('result')
                    completed_at = published.get('completed_at') if isinstance(published, dict) else None
                    on_time_result = (isinstance(published, dict)
                        and published.get('status') in ('succeeded', 'failed')
                        and type(completed_at) in (int, float) and math.isfinite(completed_at)
                        and completed_at <= cutoff)
                    call = {'event': 'finish_enter', 'called_at': time.time(), 'monotonic_at': time.monotonic(),
                        'row': dict(row), 'args': args, 'kwargs': kwargs,
                        'work_cutoff': cutoff, 'on_time_result': on_time_result}
                    with finish_lock:
                        finish_calls.append(call)
                        with (root/'finish-calls.jsonl').open('a', encoding='utf-8') as stream:
                            stream.write(json.dumps(call) + '\n')
                    if on_time_result:
                        held.set()
                        # The scenario's original child deadline includes native
                        # startup. Hold only its optional response publication;
                        # the saved cutoff and all business budgets stay fixed.
                        released = release.wait(8)
                    else:
                        released = False
                    with finish_lock:
                        call['released_at'] = time.time()
                        call['release_signalled'] = released
                        with (root/'finish-calls.jsonl').open('a', encoding='utf-8') as stream:
                            stream.write(json.dumps({'event': 'finish_release',
                                'called_at': call['called_at'], 'released_at': call['released_at'],
                                'release_signalled': released}) + '\n')
                    return original_finish(store, row, *args, **kwargs)

                with patch.object(_Store, 'finish', delayed_finish), Kernel.open_sqlite(
                        root/'kernel.sqlite3', {'parent': parent, 'child': child},
                        isolation_mode='process', child_capacity=1) as runtime:
                    runtime.submit(runtime.command('parent', execution_id='parent', idempotency_key='parent',
                        correlation_id='root', timeout_seconds=12, payload={'fail': fail, 'child_timeout': 5,
                            'parent_diagnostic_path': str(root/'parent-exception.json')}))
                    import dispatcher_sdk
                    report = {'sdk_import': dispatcher_sdk.__file__, 'python': sys.executable,
                        'runtime_type': type(runtime).__module__ + '.' + type(runtime).__qualname__,
                        'runtime_directory': str(root), 'kernel_path': str(runtime.kernel.db_path),
                        'observation_path': runtime._observation_path,
                        'isolation_mode': 'process', 'child_capacity': 1, 'fail': fail,
                        'parent_timeout_seconds': 12, 'child_timeout_seconds': 5,
                        'publication_hold_seconds': 8, 'original_return': None,
                        'runtime_error': None, 'diagnostic_errors': {}}

                    def error_facts(error):
                        return {'type': type(error).__module__ + '.' + type(error).__qualname__,
                            'message': str(error), 'repr': repr(error),
                            'code': getattr(error, 'code', None),
                            'traceback': traceback.format_exc()}

                    def write_evidence():
                        with finish_lock:
                            report['finish_calls'] = list(finish_calls)
                            evidence_path.write_text(json.dumps(report, indent=2), encoding='utf-8')

                    try:
                        try:
                            result = runtime.run_once()
                            report['original_return'] = result.to_dict()
                            report['parent_result'] = result.result.to_dict()
                        except BaseException as error:
                            report['runtime_error'] = error_facts(error)
                            raise
                        finally:
                            report['captured_at'] = time.time()
                            report['on_time_publication_held'] = held.is_set()
                            try:
                                observed_row = runtime._child_service.store.request('parent', 'delivery')
                                report['request_while_publication_held'] = observed_row
                                if observed_row is not None:
                                    report['original_wait_work_cutoff'] = min(item.work_deadline_at for item in
                                        BudgetEnvelope.from_dict(json.loads(observed_row['budget_json'])).constraints)
                                    with runtime.kernel._control_lock(.1):
                                        snapshot = runtime.kernel.get(observed_row['child_execution_id'])
                                    report['authoritative_child_state'] = snapshot.state
                                    report['authoritative_child_result'] = (None if snapshot.result is None
                                        else snapshot.result.to_dict())
                            except Exception as error:
                                report['diagnostic_errors']['child_inspection'] = error_facts(error)
                            write_evidence()
                            print('child_completed_delivery_evidence=' + str(evidence_path), flush=True)
                        self.assertTrue(held.is_set(), result.result.to_dict())
                        self.assertEqual(result.state, 'succeeded', result.result.to_dict())
                        value = result.result.value
                        delivered = value['child_error'] if fail else value.get('child')
                        self.assertIsNotNone(delivered, value)
                        child_id = delivered['execution_id']
                        actual = report['authoritative_child_result']
                        self.assertEqual(actual['execution_id'], child_id)
                        self.assertEqual(delivered, actual)
                        if fail:
                            self.assertEqual(value['code'], 'original_provider_failure')
                            self.assertEqual(delivered['error']['details'], {'provider': 'local-fixture'})
                        else:
                            self.assertEqual(delivered['value'], {'value': 9})
                        row = report['request_while_publication_held']
                        self.assertEqual(row['state'], 'running')
                        self.assertIsNone(row['response_json'])
                        deadline = min(item.work_deadline_at for item in
                            BudgetEnvelope.from_dict(json.loads(row['budget_json'])).constraints)
                        self.assertLessEqual(delivered['completed_at'], deadline)
                        self.assertGreaterEqual(time.time(), deadline)
                    except BaseException as error:
                        report['test_error'] = error_facts(error)
                        write_evidence()
                        raise
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
                        timeout_seconds=2, payload={
                            'return_after': envelope.constraints[-1].work_deadline_at + .02}))
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

    def complete_direct_child(self, kernel, context, *, not_before=None):
        command = replace(context.command, execution_id='child', idempotency_key='child',
                          causation_id='parent', timeout_seconds=2)
        budget = context.budget_envelope.derive(source='tool', origin_id='actual-child', timeout_seconds=2)
        kernel.submit_child(command, context.lease, budget)
        lease = kernel.claim_and_start('child-owner', execution_id='child', child_pool=True)
        snapshot = kernel.get('child')
        if not_before is not None:
            time.sleep(max(0., not_before-time.time()))
        result = ExecutionResultV2('actual-child-result', 'child', 'succeeded', lease.attempt,
            lease.fence, [], snapshot.started_at, kernel.current_time(),
            command.correlation_id, command.causation_id, {'original': 42}, None)
        kernel.complete(lease, result)
        return result

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
                with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
                    with self.assertRaises(ChildExecutionError) as caught:
                        capability._completed_result(row, window)
                    self.assertEqual(caught.exception.code, 'parent_authority_revoked')
                    read.assert_not_called()
            finally:
                context.close()
                kernel.close()

    def test_late_child_and_unknown_clock_are_not_delivered(self):
        from dispatcher_sdk.execution_kernel.budget import ClockCheckpoint, BudgetClockUnknownError
        for unknown in (False, True):
            with self.subTest(unknown=unknown), tempfile.TemporaryDirectory() as directory:
                kernel, context, capability = self.direct(Path(directory))
                try:
                    native = sample_clock()
                    envelope = BudgetEnvelope((DeadlineConstraint('tool', 'tool', native.wall_at + .1),), native)
                    result = self.complete_direct_child(kernel, context, not_before=native.wall_at + .2)
                    self.assertGreater(result.completed_at, envelope.constraints[0].work_deadline_at)
                    window = _RetryWindow(envelope, kernel)
                    if unknown:
                        envelope = BudgetEnvelope(envelope.constraints, ClockCheckpoint(
                            native.wall_at, native.elapsed_at, 'different-boot'))
                        window.envelope = envelope
                    row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
                           'parent_attempt': context.lease.attempt, 'parent_fence': context.lease.fence,
                           'child_execution_id': 'child', 'action': 'observe'}
                    with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
                        if unknown:
                            with self.assertRaises(BudgetClockUnknownError):
                                capability._completed_result(row, window)
                            read.assert_not_called()
                        else:
                            self.assertIsNone(capability._completed_result(row, window))
                            read.assert_called_once()
                finally:
                    context.close()
                    kernel.close()

    def test_parent_revoked_during_result_read_wins_within_the_same_control_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel, context, capability = self.direct(Path(directory))
            try:
                envelope = context.budget_envelope.derive(source='tool', origin_id='test-tool', timeout_seconds=1)
                self.complete_direct_child(kernel, context)
                row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': 'parent',
                       'parent_attempt': context.lease.attempt, 'parent_fence': context.lease.fence,
                       'child_execution_id': 'child', 'action': 'observe'}
                window = _RetryWindow(envelope, kernel)
                actual_read = factual._read_child_snapshot
                def concurrent_cancel(*args):
                    result = actual_read(*args)
                    kernel.cancel('parent', lease=context.lease, reason='concurrent cancellation')
                    return result
                with patch.object(factual, '_read_child_snapshot', side_effect=concurrent_cancel) as read:
                    with self.assertRaises(ChildExecutionError) as caught:
                        capability._completed_result(row, window)
                    self.assertEqual(caught.exception.code, 'parent_authority_revoked')
                    read.assert_called_once()
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
                    row = {'budget_json': json.dumps(envelope.to_dict()),
                           'parent_execution_id': context.command.execution_id,
                           'parent_attempt': context.lease.attempt,
                           'parent_fence': context.lease.fence}
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
