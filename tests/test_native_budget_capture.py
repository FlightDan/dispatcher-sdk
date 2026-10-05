"""Native observers retain real failed SQLite sampling obligations."""

import json
import multiprocessing
import os
import signal
import sqlite3
import time
import unittest

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel._process_runtime import (
    _BudgetTracker, _DeadlineExpired, _DeadlineGuard, _KernelBudgetCapture, _wait_packet,
)
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.execution_kernel.children import _RetryWindow
from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects


class NativeBudgetCaptureTests(unittest.TestCase):
    def _ready_packet_during_storage_refusal(self, *, busy):
        root = retained_directory('sdk-packet-storage-refusal-')
        receiver, sender = multiprocessing.Pipe(duplex=False)
        self.addCleanup(receiver.close)
        self.addCleanup(sender.close)
        packet = {'kind': 'handler_completed', 'cleanup_confirmed': True,
            'outcome_json': '{"kind":"ok","value":{"original":42}}'}
        raw_errors, calls = [], []
        with SQLiteKernel(root / 'kernel.sqlite3') as kernel:
            envelope, _ = self._admitted_child(kernel)
            owner = _KernelBudgetCapture(kernel, 'parent')
            connection = sqlite3.connect(kernel.db_path, timeout=0)
            try:
                if busy:
                    connection.execute('BEGIN IMMEDIATE')

                def capture(projected, *, timeout_seconds):
                    calls.append(time.monotonic())
                    # The original private pipe becomes ready DURING this
                    # actual storage attempt, after _wait_packet's first poll.
                    sender.send_bytes(json.dumps(packet).encode())
                    try:
                        if busy:
                            return owner(projected, timeout_seconds=min(.02, timeout_seconds))
                        connection.execute('SELECT * FROM absent_budget_table').fetchone()
                    except sqlite3.OperationalError as error:
                        raw_errors.append(error)
                        raise

                tracker = _BudgetTracker(envelope, None, capture, guarded=True)
                deadline = time.monotonic() + .5
                began = time.monotonic()
                if busy:
                    received, bound = _wait_packet(receiver, deadline, tracker)
                    self.assertEqual(packet, received)
                    self.assertLessEqual(bound, deadline)
                    self.assertFalse(receiver.poll(0))
                    self.assertEqual('database is locked', str(raw_errors[0]))
                else:
                    with self.assertRaises(BudgetClockUnknownError) as caught:
                        _wait_packet(receiver, deadline, tracker)
                    self.assertIs(caught.exception, tracker.capture_error)
                    self.assertTrue(receiver.poll(0), 'permanent error was replaced by a packet')
                    self.assertEqual('no such table: absent_budget_table', str(raw_errors[0]))
                self.assertEqual(1, len(calls))
                self.assertIs(raw_errors[0], tracker.capture_error.__cause__)
                self.assertEqual(envelope.constraints, tracker.envelope.constraints)
                evidence = {'busy': busy, 'elapsed': time.monotonic()-began,
                    'original_deadline': deadline, 'calls': len(calls),
                    'pipe_still_ready': receiver.poll(0),
                    'raw_error': {'type': type(raw_errors[0]).__name__, 'message': str(raw_errors[0]),
                        'sqlite_errorcode': getattr(raw_errors[0], 'sqlite_errorcode', None)}}
                (root / 'evidence.json').write_text(json.dumps(evidence, indent=2))
                print('packet_storage_refusal_evidence=' + str(root / 'evidence.json'), flush=True)
            finally:
                connection.rollback()
                connection.close()

    def test_ready_original_packet_interrupts_actual_busy_retry_without_new_capture(self):
        self._ready_packet_during_storage_refusal(busy=True)

    def test_ready_original_packet_cannot_hide_actual_permanent_sql_error(self):
        self._ready_packet_during_storage_refusal(busy=False)

    def _admitted_child(self, kernel):
        def command(identity):
            return ExecutionCommandV2(identity, identity, 'guard-registry', 'guard-proof', None,
                'work', 1, RetryPolicy(), 30, {})
        kernel.submit(command('parent'))
        lease = kernel.claim_and_start('parent-owner')
        parent = kernel.prepare_execution_budget(lease).enter_handler(30, origin_id='execution:parent')
        parent = kernel.confirm_handler_entry(lease, parent)
        child = parent.derive(source='tool', origin_id='original-call', timeout_seconds=10,
            sample=sample_clock(wall_time=parent.checkpoint.wall_at))
        kernel.submit_child(command('child'), lease, child)
        return parent, child

    def test_monitor_consumes_committed_capture_once_then_guards_forward_jump(self):
        root = retained_directory('sdk-monitor-canonical-clock-')
        wall = [time.time()]
        with SQLiteKernel(root / 'kernel.sqlite3', now=lambda: wall[0], default_lease_seconds=90) as kernel:
            command = ExecutionCommandV2('original', 'original', 'guard-registry', 'guard-proof', None,
                'work', 1, RetryPolicy(), 30, {})
            kernel.submit(command)
            lease = kernel.claim_and_start('owner')
            envelope = kernel.prepare_execution_budget(lease).enter_handler(30, origin_id='execution:original')
            envelope = kernel.confirm_handler_entry(lease, envelope)
            context = HandlerContext(command, lease, HandlerEffects(kernel, lease, lambda: True),
                budget_envelope=envelope, service_spec={'guard_budget': True, 'entry_protocol': True})
            context._entry_confirmed = True
            baseline = wall[0]
            # One committed floor may be consumed without a duplicate write.
            first = context._monitor_budget()
            self.assertGreater(first.remaining_work_seconds, 0)
            seen = context._monitor_checkpoint
            wall[0] = baseline + 40
            # The same floor must not suppress a second actual capture.
            jumped = context._monitor_budget()
            self.assertEqual(jumped.remaining_work_seconds, 0)
            self.assertNotEqual(seen, context._monitor_checkpoint)
            canonical = BudgetEnvelope.from_dict(kernel.get_execution_limits('original')['envelope'])
            self.assertGreaterEqual(canonical.checkpoint.wall_at, baseline + 40)
            wall[0] = baseline
            recovered = BudgetEnvelope.from_dict(kernel.get_execution_limits('original')['envelope'])
            self.assertEqual(recovered.view(sample=sample_clock(wall_time=baseline)).remaining_work_seconds, 0)
            self.assertEqual(recovered.constraints, envelope.constraints)
            context.close()
            (root / 'evidence.json').write_text(json.dumps({'first': first.to_dict(),
                'forward_jump': jumped.to_dict(), 'canonical': recovered.to_dict(),
                'iterations_after_reuse': 1}, indent=2))
        print('monitor_canonical_clock_evidence=' + str(root / 'evidence.json'), flush=True)

    def test_targeted_claim_transfers_real_failed_ack_to_original_child_retry_window(self):
        root = retained_directory('sdk-targeted-claim-capture-')
        wall = [time.time()]
        evidence = {}
        try:
            with SQLiteKernel(root / 'kernel.sqlite3', now=lambda: wall[0], default_lease_seconds=90) as kernel:
                parent, child = self._admitted_child(kernel)
                window = _RetryWindow(child, kernel, execution_id='parent')
                original_deadline = window.deadline
                baseline = wall[0]
                begin = kernel._begin_budget_sample
                writer = sqlite3.connect(kernel.db_path, timeout=.1)
                tokens = []

                def arm_and_lock(execution_id, **options):
                    token = begin(execution_id, **options)
                    tokens.append(token)
                    writer.execute('BEGIN IMMEDIATE')
                    wall[0] = baseline + 4
                    return token

                kernel._begin_budget_sample = arm_and_lock
                started = time.monotonic()
                try:
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        kernel.claim_and_start('child-owner', execution_id='child', timeout_seconds=.05)
                    error = caught.exception
                    self.assertIs(error.budget_sample_owner.kernel, kernel)
                    self.assertEqual(error.budget_sample_token, tokens[0])
                    self.assertGreaterEqual(error.budget_sample_envelope.checkpoint.wall_at, baseline + 4)
                    window._adopt_sample_owner(error)
                    evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
                    evidence['capture_seconds'] = time.monotonic() - started
                    self.assertLess(evidence['capture_seconds'], .25)
                finally:
                    writer.rollback()
                    writer.close()
                    wall[0] = baseline
                    kernel._begin_budget_sample = begin
                with SQLiteKernel(kernel.db_path, now=lambda: wall[0]) as fresh:
                    with self.assertRaisesRegex(BudgetClockUnknownError, 'budget_clock_sample_unresolved'):
                        fresh.claim_and_start('foreign-owner', execution_id='child', timeout_seconds=.02)
                    self.assertEqual(fresh.get('child').attempt, 0)
                    window._resume_sample()
                    self.assertLessEqual(window.deadline, original_deadline)
                    self.assertEqual(kernel._connection.execute('SELECT token FROM kernel_budget_samples').fetchall(), [])
                    self.assertEqual(len(tokens), 1)
                    canonical = BudgetEnvelope.from_dict(fresh.get_execution_limits('parent')['envelope'])
                    self.assertEqual(canonical.constraints, parent.constraints)
                    self.assertGreaterEqual(canonical.checkpoint.wall_at, baseline + 4)
                    running = kernel.claim_and_start('child-owner', execution_id='child', timeout_seconds=.1)
                    self.assertIsNotNone(running)
                    self.assertEqual(fresh.get('child').attempt, 1)
                    self.assertEqual(window.envelope.constraints, child.constraints)
                    evidence.update(token=tokens[0], original=child.to_dict(), resumed=window.envelope.to_dict(),
                        canonical=canonical.to_dict(), fresh_recovery_fenced=True, child_attempt=1,
                        original_native_deadline=original_deadline, resumed_native_deadline=window.deadline)
        finally:
            path = root / 'evidence.json'
            path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print('targeted_claim_capture_evidence=' + str(path), flush=True)

    def test_slow_real_guard_arm_return_retains_forward_sample_before_timeout(self):
        root = retained_directory('sdk-slow-budget-arm-')
        wall = [time.time()]
        evidence = {}
        try:
            with SQLiteKernel(root / 'kernel.sqlite3', now=lambda: wall[0], default_lease_seconds=90) as kernel:
                parent, child = self._admitted_child(kernel)
                baseline = wall[0]
                begin = kernel._begin_budget_sample
                observer = sqlite3.connect(kernel.db_path, timeout=.1)
                tokens = []

                def slow_committed_arm(execution_id, **options):
                    token = begin(execution_id, **options)
                    tokens.append(token)
                    self.assertEqual(observer.execute('SELECT token FROM kernel_budget_samples').fetchone()[0], token)
                    wall[0] = baseline + 4
                    time.sleep(.025)
                    return token

                kernel._begin_budget_sample = slow_committed_arm
                try:
                    with self.assertRaises(TimeoutError) as caught:
                        kernel.claim_and_start('child-owner', execution_id='child', timeout_seconds=.01)
                    error = caught.exception
                    retained = error.budget_sample_envelope
                    self.assertIsNotNone(retained)
                    self.assertGreaterEqual(retained.checkpoint.wall_at, baseline + 4)
                    self.assertEqual(error.budget_sample_token, tokens[0])
                    evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
                finally:
                    observer.close()
                    wall[0] = baseline
                    kernel._begin_budget_sample = begin
                with SQLiteKernel(kernel.db_path, now=lambda: wall[0]) as fresh:
                    with self.assertRaisesRegex(BudgetClockUnknownError, 'budget_clock_sample_unresolved'):
                        fresh._sample_budget('parent', child, timeout_seconds=.02)
                    resumed = error.budget_sample_owner.finish_pending(child, timeout_seconds=.1)
                    self.assertEqual(resumed.constraints, child.constraints)
                    self.assertGreaterEqual(resumed.checkpoint.wall_at, retained.checkpoint.wall_at)
                    canonical = BudgetEnvelope.from_dict(fresh.get_execution_limits('parent')['envelope'])
                    self.assertEqual(canonical.constraints, parent.constraints)
                    self.assertGreaterEqual(canonical.checkpoint.wall_at, retained.checkpoint.wall_at)
                    self.assertEqual(kernel._connection.execute('SELECT token FROM kernel_budget_samples').fetchall(), [])
                    self.assertEqual(len(tokens), 1)
                    self.assertEqual(fresh.get('child').attempt, 0)
                    evidence.update(token=tokens[0], retained=retained.to_dict(), resumed=resumed.to_dict(),
                        canonical=canonical.to_dict(), fresh_recovery_fenced=True, same_token_acknowledged=True)
        finally:
            path = root / 'evidence.json'
            path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print('slow_budget_arm_evidence=' + str(path), flush=True)

    def test_failed_real_acknowledgement_fences_recovery_but_allows_factual_cancel_and_owner_retry(self):
        root = retained_directory('sdk-native-budget-capture-')
        wall = [time.time()]
        evidence = {}
        try:
            with SQLiteKernel(root / 'kernel.sqlite3', now=lambda: wall[0], default_lease_seconds=90) as kernel:
                command = ExecutionCommandV2('parent', 'parent', 'guard-registry', 'guard-proof', None,
                    'work', 1, RetryPolicy(), 30, {})
                kernel.submit(command)
                lease = kernel.claim_and_start('actual-parent-owner')
                original = kernel.prepare_execution_budget(lease).enter_handler(30, origin_id='execution:parent')
                original = kernel.confirm_handler_entry(lease, original)
                baseline = wall[0]
                capture = _KernelBudgetCapture(kernel, 'parent')
                begin = kernel._begin_budget_sample
                writer = sqlite3.connect(kernel.db_path, timeout=.1)
                tokens = []

                def arm_and_lock(execution_id, **options):
                    token = begin(execution_id, **options)
                    tokens.append(token)
                    writer.execute('BEGIN IMMEDIATE')
                    wall[0] = baseline + 4
                    return token

                kernel._begin_budget_sample = arm_and_lock
                started = time.monotonic()
                try:
                    with self.assertRaises(sqlite3.OperationalError) as caught:
                        capture(original, timeout_seconds=.05)
                    retained = caught.exception.budget_sample_envelope
                    self.assertEqual(caught.exception.budget_sample_token, tokens[0])
                    self.assertGreaterEqual(retained.checkpoint.wall_at, baseline + 4)
                    evidence['original_error'] = {'type': type(caught.exception).__name__,
                        'message': str(caught.exception),
                        'sqlite_errorcode': getattr(caught.exception, 'sqlite_errorcode', None)}
                    evidence['capture_seconds'] = time.monotonic() - started
                finally:
                    writer.rollback()
                    writer.close()
                    wall[0] = baseline
                    kernel._begin_budget_sample = begin
                with SQLiteKernel(kernel.db_path, now=lambda: wall[0]) as fresh:
                    with self.assertRaisesRegex(BudgetClockUnknownError, 'budget_clock_sample_unresolved'):
                        fresh._sample_budget('parent', original)
                    fresh.cancel('parent', expected_revision=lease.revision, reason='factual cancellation')
                    self.assertEqual(fresh.get('parent').state, 'cancelled')
                    published = capture(original, timeout_seconds=.1)
                    self.assertEqual(published.constraints, original.constraints)
                    self.assertEqual(published.started_at, original.started_at)
                    self.assertGreaterEqual(published.checkpoint.wall_at, retained.checkpoint.wall_at)
                    canonical = BudgetEnvelope.from_dict(fresh.get_execution_limits('parent')['envelope'])
                    self.assertEqual(canonical.constraints, original.constraints)
                    self.assertGreaterEqual(canonical.checkpoint.wall_at, retained.checkpoint.wall_at)
                    self.assertEqual(fresh._connection.execute('SELECT token FROM kernel_budget_samples').fetchall(), [])
                    self.assertEqual(len(tokens), 1, 'retry armed another sampling obligation')
                    self.assertEqual(fresh.get('parent').state, 'cancelled')
                    evidence.update(original=original.to_dict(), retained=retained.to_dict(),
                        published=published.to_dict(), canonical=canonical.to_dict(),
                        fresh_recovery_fenced=True, factual_cancel='cancelled', same_token_acknowledged=True)
        finally:
            path = root / 'evidence.json'
            path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print('native_budget_capture_evidence=' + str(path), flush=True)

    @unittest.skipUnless(os.name == 'posix' and hasattr(signal, 'setitimer'), 'requires POSIX native alarm')
    def test_production_alarm_projects_elapsed_without_calling_capture_or_wall_clock(self):
        envelope = BudgetEnvelope((), sample_clock(wall_time=100))

        def forbidden(*args, **kwargs):
            raise AssertionError('independent alarm attempted a wall sample or storage capture')

        guard = _DeadlineGuard(time.monotonic() + .08, envelope, forbidden,
            capture_budget=forbidden, guarded=True)

        def expire(signum, frame):
            remaining = guard.remaining()
            if remaining <= 0:
                raise _DeadlineExpired()
            signal.setitimer(signal.ITIMER_REAL, min(remaining, .01))

        previous = signal.signal(signal.SIGALRM, expire)
        started = time.monotonic()
        try:
            guard.arm()
            with self.assertRaises(_DeadlineExpired):
                time.sleep(.3)
            self.assertLess(time.monotonic() - started, .25)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)


if __name__ == '__main__':
    unittest.main()
