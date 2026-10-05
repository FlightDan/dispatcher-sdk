"""Real receipt read admission retries keep original authority and clock floors."""
import json
from collections import deque
from contextlib import ExitStack
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope
from dispatcher_sdk.execution_kernel import children as children_module
from dispatcher_sdk.execution_kernel.children import _RetryWindow
from dispatcher_sdk.execution_kernel.settlement import SettlementBusyError
from tests import test_child_clock_checkpoint as checkpoint_fixture
from tests import test_observability_runtime_integration as runtime_fixture
from tests._storage_evidence import StorageEvidence


class ChildReceiptReadTests(unittest.TestCase):
    # Reuse the real stores without rerunning every independent clock case.
    setUp = checkpoint_fixture.ChildClockCheckpointTests.setUp
    tearDown = checkpoint_fixture.ChildClockCheckpointTests.tearDown
    command = staticmethod(checkpoint_fixture.ChildClockCheckpointTests.command)

    def short_row(self, seconds):
        envelope = self.parent_budget.derive(source='tool', origin_id='receipt-read', timeout_seconds=seconds)
        window = _RetryWindow(envelope, self.kernel)
        row = self.children._enqueue(request_id='receipt-read', child_id='receipt-child', action='run',
            child_command=self.command('receipt-child'), envelope=envelope, window=window)
        return row, window

    def exclusive_writer(self):
        connection = sqlite3.connect(self.facts.path, timeout=.1, check_same_thread=False)
        connection.execute('BEGIN EXCLUSIVE')
        return connection

    def test_actual_receipt_contention_retries_inside_same_window_and_enforces_stronger_floor(self):
        from dataclasses import replace
        row, window = self.short_row(1)
        original = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
        narrowed = replace(original, checkpoint=replace(original.checkpoint,
            wall_at=original.checkpoint.wall_at + .3))
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'wait_id': row['wait_id'], 'budget_envelope': narrowed.to_dict()},
            timeout_seconds=window.remaining())
        writer = self.exclusive_writer()
        def unlock():
            time.sleep(.25)
            writer.rollback()
            writer.close()
        release = threading.Thread(target=unlock)
        release.start()
        before = time.monotonic()
        original_facts = self.children.store._facts
        try:
            with patch.object(self.children.store, '_facts', wraps=original_facts) as reads:
                self.children.store.attach(row, window)
                attempts = reads.call_count
        finally:
            release.join(1)
        elapsed = time.monotonic() - before
        remaining = window.remaining()
        original_remaining = original.view(sample=self.kernel_clock()).remaining_work_seconds
        self.assertGreaterEqual(attempts, 2)
        self.assertGreaterEqual(elapsed, .20)
        self.assertLess(elapsed, 1)
        self.assertGreater(remaining, 0)
        self.assertLess(remaining, original_remaining - .25)
        self.assertEqual(window.envelope.constraints, original.constraints)
        self.evidence['records'].append({'scenario': 'receipt_writer_released_before_original_cutoff',
            'read_attempts': attempts, 'elapsed': elapsed, 'original_remaining': original_remaining,
            'enforced_remaining': remaining, 'original_constraints': original.to_dict()['constraints'],
            'retained_floor': window.envelope.to_dict()})

    def kernel_clock(self):
        from dispatcher_sdk.execution_kernel.budget import sample_clock
        return sample_clock(wall_time=self.kernel._wall_time())

    def test_persistent_receipt_contention_expires_without_completed_result_rescue(self):
        import traceback

        row, window = self.short_row(.3)
        original = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
        writer = self.exclusive_writer()
        sql_evidence = StorageEvidence(self.root, self)
        sql_evidence.start(include_kernel=True)
        self.addCleanup(sql_evidence.stop)
        self.addCleanup(sql_evidence.save)
        steps = deque(maxlen=256)

        def traced(stage, operation):
            def invoke(*args, **kwargs):
                entry = {'stage': stage, 'began': time.monotonic(),
                         'thread_cpu_began': time.thread_time()}
                if stage == 'sleep':
                    entry['requested_seconds'] = args[0]
                steps.append(entry)
                try:
                    return operation(*args, **kwargs)
                except BaseException as error:
                    entry['error'] = {'type': type(error).__name__, 'message': str(error)}
                    raise
                finally:
                    entry['elapsed'] = time.monotonic() - entry['began']
                    entry['thread_cpu_seconds'] = time.thread_time() - entry['thread_cpu_began']
            return invoke

        import dispatcher_sdk._sqlite_admission as admission_module
        timing = SimpleNamespace(**{**vars(time), 'sleep': traced('sleep', time.sleep)})
        before = time.monotonic()
        actual_windows = []
        actual_deadlines_at_call = []
        original_window_factory = children_module._RetryWindow

        def observe_window(*args, **kwargs):
            actual = original_window_factory(*args, **kwargs)
            actual_windows.append(actual)
            actual_deadlines_at_call.append(actual.deadline)
            return actual

        try:
            with ExitStack() as diagnostics:
                rescue = diagnostics.enter_context(patch.object(self.children, '_completed_result'))
                diagnostics.enter_context(patch.object(children_module, '_RetryWindow', side_effect=observe_window))
                diagnostics.enter_context(patch.object(self.children.store, '_facts',
                    traced('receipt_open', self.children.store._facts)))
                diagnostics.enter_context(patch.object(self.kernel, '_verify_active_lease_readonly',
                    traced('parent_authority_read', self.kernel._verify_active_lease_readonly)))
                diagnostics.enter_context(patch.object(children_module, 'time', timing))
                diagnostics.enter_context(patch.object(admission_module, 'time', timing))
                with window.project():
                    remaining_at_call = window.remaining()
                window_at_call = window.envelope.to_dict()
                deadline_at_call = window.deadline
                caught, returned, raw_traceback = None, None, None
                try:
                    returned = self.children._await(row)
                except Exception as error:
                    caught, raw_traceback = error, traceback.format_exc()
                elapsed = time.monotonic() - before
                # _await reconstructs the authoritative wait window from the
                # persisted envelope; the helper returned by short_row is a
                # separate local timer and can differ by a coarse host tick.
                actual_window = actual_windows[0] if len(actual_windows) == 1 else None
                remaining_at_end = None
                if actual_window is not None:
                    with actual_window.project():
                        remaining_at_end = actual_window.remaining()
                with window.project():
                    setup_window_remaining_at_end = window.remaining()
                row_budget_at_end = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
                self.evidence['records'].append({'scenario': 'persistent_receipt_contention',
                    'elapsed': elapsed, 'began': before,
                    'remaining_at_call': remaining_at_call, 'remaining_at_end': remaining_at_end,
                    'setup_window_remaining_at_end': setup_window_remaining_at_end,
                    'setup_deadline_at_call': deadline_at_call,
                    'actual_deadlines_at_call': actual_deadlines_at_call,
                    'error_type': None if caught is None else type(caught).__name__,
                    'error': None if caught is None else str(caught), 'traceback': raw_traceback,
                    'control_cause': None if caught is None or caught.__cause__ is None else {
                        'type': type(caught.__cause__).__name__, 'message': str(caught.__cause__)},
                    'original_receipt_cause': None if getattr(caught, 'original_receipt_cause', None) is None else {
                        'type': type(caught.original_receipt_cause).__name__,
                        'message': str(caught.original_receipt_cause),
                        'sqlite_errorcode': getattr(caught.original_receipt_cause, 'sqlite_errorcode', None)},
                    'sqlite_errorcode': getattr(caught, 'sqlite_errorcode', None), 'returned': returned,
                    'completed_result_rescue_calls': rescue.call_count,
                    'writer_in_transaction': writer.in_transaction,
                    'original_budget': original.to_dict(), 'setup_window_at_call': window_at_call,
                    'setup_window_at_end': window.envelope.to_dict(),
                    'actual_window_at_end': None if actual_window is None else actual_window.envelope.to_dict(),
                    'row_budget_at_end': row_budget_at_end.to_dict(), 'actual_steps': list(steps)})
                # Setup already spent part of the original .3-second window.
                # Exhaustion, rather than a new minimum wait, is the contract.
                self.assertIsInstance(caught, SettlementBusyError)
                rescue.assert_not_called()
                self.assertEqual(len(actual_windows), 1, raw_traceback)
                self.assertEqual(remaining_at_end, 0)
                self.assertEqual(actual_window.envelope.constraints, original.constraints)
                self.assertEqual(window.envelope.constraints, original.constraints)
                self.assertEqual(row_budget_at_end.constraints, original.constraints)
                self.assertTrue(writer.in_transaction)
                self.assertLess(elapsed, .6)
        finally:
            writer.rollback()
            writer.close()

    def test_terminal_receipt_busy_keeps_original_error_without_resampling(self):
        row, window = self.short_row(.3)
        writer = self.exclusive_writer()
        original_facts = self.children.store._facts
        original_remaining = window.remaining
        terminal = []
        proof_error = TimeoutError('Kernel control lock admission timed out')

        def exhaust_receipt_read(*args, **kwargs):
            try:
                return original_facts(*args, **kwargs)
            except SettlementBusyError as error:
                deadline = window.deadline
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(remaining)
                with window.project():
                    self.assertEqual(window.remaining(), 0)
                terminal.append(error)
                raise

        def remaining_without_new_terminal_sample():
            if terminal and not window._projecting:
                raise TimeoutError('terminal receipt attempted another authoritative sample')
            return original_remaining()

        try:
            with patch.object(self.children.store, '_facts', side_effect=exhaust_receipt_read), \
                    patch.object(window, 'remaining', side_effect=remaining_without_new_terminal_sample), \
                    patch.object(self.kernel, '_verify_active_lease_readonly', side_effect=proof_error):
                with self.assertRaises(SettlementBusyError) as caught:
                    self.children.store.attach(row, window)
                self.assertTrue(terminal, "original cutoff elapsed before the actual receipt read")
                self.assertIs(caught.exception, terminal[0])
                self.assertIs(caught.exception.__cause__, proof_error)
                self.assertIsInstance(caught.exception.original_receipt_cause, sqlite3.OperationalError)
                with window.project():
                    self.assertEqual(window.remaining(), 0)
                self.assertTrue(writer.in_transaction)
        finally:
            writer.rollback()
            writer.close()

    def test_missing_checkpoint_facts_are_unknown_without_rescue(self):
        row, window = self.short_row(1)
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'budget_envelope': window.envelope.to_dict()})
        with patch.object(self.children, '_completed_result') as rescue:
            with self.assertRaises(BudgetClockUnknownError):
                self.children._await(row)
            rescue.assert_not_called()

    def test_expired_wait_with_actual_reaped_parent_keeps_revocation_without_receipt_read(self):
        from dispatcher_sdk.execution_kernel.children import ChildExecutionError
        row, window = self.short_row(.2)
        original = json.loads(row['budget_json'])
        # Reaping is an actual persisted parent transition after the original
        # window has been spent, as in controller crash recovery.
        self.wall[0] = self.lease.expires_at + 1
        self.kernel.reap()
        watermark = self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0]
        with patch.object(self.children, '_completed_result') as rescue, \
                patch.object(self.children.store, '_facts') as facts:
            before = time.monotonic()
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._await(row)
            elapsed = time.monotonic() - before
            self.assertEqual(caught.exception.code, 'parent_authority_revoked')
            self.assertLess(elapsed, .1)
            rescue.assert_not_called()
            facts.assert_not_called()
        self.assertEqual(self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0], watermark)
        self.assertEqual(json.loads(row['budget_json']), original)
        self.evidence['records'].append({'scenario': 'expired_wait_actual_reaped_parent',
            'elapsed': elapsed, 'error': str(caught.exception), 'code': caught.exception.code,
            'original_budget': original, 'watermark': watermark,
            'receipt_read_calls': facts.call_count, 'completed_result_rescue_calls': rescue.call_count})

    def test_other_wait_checkpoint_does_not_require_the_current_wait_envelope(self):
        row, window = self.short_row(1)
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'wait_id': 'different-historical-wait'})
        self.children.store.attach(row, window)
        self.assertGreater(window.remaining(), .5)
        self.evidence['records'].append({'scenario': 'unrelated_wait_history',
            'remaining': window.remaining(), 'original_wait_id': row['wait_id']})

    def test_current_wait_missing_envelope_facts_remain_unknown(self):
        row, window = self.short_row(1)
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'wait_id': row['wait_id']})
        with patch.object(self.children, '_completed_result') as rescue:
            with self.assertRaises(BudgetClockUnknownError):
                self.children._await(row)
            rescue.assert_not_called()

    def test_current_wait_byte_truncation_remains_unknown(self):
        row, window = self.short_row(1)
        self.facts.note({'execution_id': row['child_execution_id'], 'attempt': 0, 'fence': 0},
            'child_budget_checkpoint', {'wait_id': row['wait_id'],
                'budget_envelope': window.envelope.to_dict(), 'padding': 'x'*300000})
        with patch.object(self.children, '_completed_result') as rescue:
            with self.assertRaises(BudgetClockUnknownError):
                self.children._await(row)
            rescue.assert_not_called()

    def test_actual_parent_cancellation_interrupts_receipt_retry_before_original_cutoff(self):
        import traceback
        from copy import deepcopy
        from dispatcher_sdk.execution_kernel.children import ChildExecutionError
        row, window = self.short_row(1)
        writer = self.exclusive_writer()
        errors = []
        timings, sql = {}, deque(maxlen=256)
        sql_operations = [0]
        evidence_lock = threading.RLock()
        record = {'scenario': 'cancel_during_receipt_exclusive_lock',
            'original_row_seconds': 1, 'original_sleep_seconds': .15,
            'original_join_seconds': .5, 'original_elapsed_assertion_seconds': .7,
            'original_budget': json.loads(row['budget_json']),
            'setup_native_deadline': window.deadline, 'actual_windows': [],
            'thread_timings': timings}
        self.evidence['records'].append(record)
        storage = StorageEvidence(self.root, self)
        storage.start(include_kernel=True)
        self.addCleanup(storage.stop)
        self.addCleanup(storage.save)
        original_window = children_module._RetryWindow

        def observe_window(*args, **kwargs):
            actual = original_window(*args, **kwargs)
            with evidence_lock:
                record['actual_windows'].append({'initial_native_deadline': actual.deadline,
                    'budget': actual.envelope.to_dict(), 'execution_id': actual.execution_id})
            return actual

        def trace(statement):
            with evidence_lock:
                sql_operations[0] += 1
                sql.append({'at': time.monotonic(), 'thread': threading.current_thread().name,
                            'sql': statement[:2048], 'sql_truncated': len(statement) > 2048})

        def error_facts(error):
            envelope = getattr(error, 'budget_sample_envelope', None)
            cause = error.__cause__
            return {'type': type(error).__name__, 'message': str(error),
                'code': getattr(error, 'code', None),
                'cause': None if cause is None else {'type': type(cause).__name__, 'message': str(cause)},
                'pending_token': getattr(error, 'budget_sample_token', None),
                'captured_envelope': None if envelope is None else envelope.to_dict()}

        def await_child():
            with evidence_lock:
                timings['reader_start'] = time.monotonic()
                timings['reader_cpu_start'] = time.thread_time()
            try:
                self.children._await(row)
            except BaseException as error:
                returned_at, returned_cpu = time.monotonic(), time.thread_time()
                errors.append(error)
                with evidence_lock:
                    timings['reader_return'] = returned_at
                    timings['reader_cpu_return'] = returned_cpu
                    record['reader_error'] = {**error_facts(error),
                        'traceback': traceback.format_exc(limit=16)[-16384:]}
            else:
                with evidence_lock:
                    timings['reader_return'] = time.monotonic()
                    timings['reader_cpu_return'] = time.thread_time()
            finally:
                with evidence_lock:
                    timings['reader_thread_done'] = time.monotonic()
        reader = threading.Thread(target=await_child)
        before = time.monotonic()
        record['began'] = before
        self.kernel._connection.set_trace_callback(trace)
        with patch.object(self.children, '_completed_result') as rescue, \
                patch.object(children_module, '_RetryWindow', side_effect=observe_window):
            try:
                reader.start()
                time.sleep(.15)
                timings['cancel_start'] = time.monotonic()
                timings['cancel_cpu_start'] = time.thread_time()
                try:
                    self.kernel.cancel(self.parent.execution_id, lease=self.lease, reason='real parent cancellation')
                    record['cancel_committed'] = True
                except BaseException as error:
                    record['cancel_error'] = {**error_facts(error),
                        'traceback': traceback.format_exc(limit=16)[-16384:]}
                    raise
                finally:
                    timings['cancel_return'] = time.monotonic()
                    timings['cancel_cpu_return'] = time.thread_time()
                reader.join(.5)
                elapsed = time.monotonic() - before
                # Retain real phase facts even when the original timing
                # assertion fails; do not obtain another budget observation.
                with evidence_lock:
                    record.update(elapsed=elapsed, reader_alive_at_join=reader.is_alive(),
                        reader_error_count=len(errors), rescue_calls=rescue.call_count,
                        sql=list(sql), parent_lease=self.lease.to_dict())
                self.assertFalse(reader.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], ChildExecutionError)
                self.assertEqual(errors[0].code, 'parent_authority_revoked')
                self.assertLess(elapsed, .7)
                rescue.assert_not_called()
            finally:
                with evidence_lock:
                    record['before_cleanup_at'] = time.monotonic()
                    record['elapsed_before_cleanup'] = record['before_cleanup_at'] - before
                    timings['writer_release_start'] = time.monotonic()
                writer.rollback()
                writer.close()
                with evidence_lock:
                    timings['writer_release_return'] = time.monotonic()
                reader.join(1)
                self.kernel._connection.set_trace_callback(None)
                with evidence_lock:
                    record.update(terminal_at=time.monotonic(),
                        reader_alive_after_cleanup=reader.is_alive(), sql=list(sql),
                        sql_operations=sql_operations[0],
                        sql_events_dropped=max(0, sql_operations[0]-len(sql)))
                    checkpoint = deepcopy(record)
                storage.save(phase='cancel-receipt-terminal', checkpoint=checkpoint)

    def test_original_public_parent_process_child_fixture(self):
        runtime_fixture.RuntimeObservationIntegrationTests().execute('process')


if __name__ == '__main__':
    unittest.main()
