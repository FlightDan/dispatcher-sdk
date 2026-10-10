"""Native alarm receipts survive an interrupted, durably armed clock sample."""
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sqlite3
import time
import unittest

from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, ExecutionLease, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory


def _interrupted_capture(path, sender):
    """Process exit owns physical cleanup; an unknown guard is never cleared."""
    calls = []

    def wall():
        calls.append(time.monotonic())
        return time.time()

    kernel = SQLiteKernel(path, now=wall)
    command = ExecutionCommandV2('original', 'original', 'alarm-proof', 'alarm-proof',
        None, 'work', 1, RetryPolicy(), 5, {})
    kernel.submit(command)
    lease = kernel.claim_and_start('owner', execution_id='original')
    envelope = kernel.prepare_execution_budget(lease).enter_handler(5, origin_id='execution:original')
    envelope = kernel.confirm_handler_entry(lease, envelope)
    owner = process_runtime._KernelBudgetCapture(kernel, 'original')
    begin = kernel._begin_budget_sample
    evidence = {'original_envelope': envelope.to_dict(), 'original_lease': lease.to_dict()}
    guard = None

    def expire(signum, frame):
        evidence['alarm_signals'] = evidence.get('alarm_signals', []) + [signum]
        if guard.remaining() <= 0:
            raise process_runtime._DeadlineExpired()
        guard.arm()

    def arm_then_wait(*args, **kwargs):
        nonlocal guard
        token = begin(*args, **kwargs)
        # Establish a real alarm inside the already existing capture bound,
        # after the actual arm COMMIT. No supplied deadline is extended.
        guard = process_runtime._DeadlineGuard(
            min(kernel._control_deadline, time.monotonic() + .01), envelope, wall, guarded=True)
        evidence.update(token=token, control_deadline=kernel._control_deadline,
            alarm_deadline=guard.deadline, guard_committed=not kernel._connection.in_transaction,
            wall_calls_after_arm=len(calls))
        remaining = guard.remaining()
        evidence['alarm_expired_after_arm'] = remaining <= 0
        evidence['original_expired_after_arm'] = kernel._control_deadline <= time.monotonic()
        # COMMIT may have consumed the original capture bound. Deliver the
        # real native alarm at that expired bound instead of extending it or
        # failing before the intended uncaptured-alarm path is exercised.
        if remaining <= 0:
            os.kill(os.getpid(), signal.SIGALRM)
        else:
            signal.setitimer(signal.ITIMER_REAL, min(remaining, .05))
        while True:
            signal.pause()

    previous = signal.signal(signal.SIGALRM, expire)
    kernel._begin_budget_sample = arm_then_wait
    try:
        try:
            owner(envelope, timeout_seconds=.1)
        except process_runtime._DeadlineExpired as error:
            evidence['original_error'] = type(error).__name__
            evidence['same_stored_error'] = owner._error is error
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
            kernel._begin_budget_sample = begin
        pending = owner._pending
        evidence['uncaptured'] = pending is not None and pending[1] is None
        statements = []
        kernel._connection.set_trace_callback(statements.append)
        try:
            for _ in range(2):
                retained, checkpoint = process_runtime._finish_budget_capture(owner, envelope)
                evidence['same_envelope'] = retained is envelope
                process_runtime._send_packet(sender, {'kind': 'handler_timed_out',
                    'cleanup_confirmed': True, 'budget_checkpoint': checkpoint})
            evidence['same_pending'] = owner._pending is pending
            evidence['finish_sql'] = statements
            evidence['wall_calls_after_receipts'] = len(calls)
        finally:
            kernel._connection.set_trace_callback(None)
    except BaseException as error:
        evidence['receipt_error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        try:
            kernel.close()
        except BudgetClockUnknownError as error:
            evidence['close_error'] = str(error)
        Path(path).with_suffix('.evidence.json').write_text(json.dumps(evidence, indent=2))
        sender.close()


@unittest.skipUnless(os.name == 'posix' and hasattr(signal, 'setitimer'), 'requires native POSIX alarm')
class UncapturedAlarmReceiptTests(unittest.TestCase):
    def test_original_alarm_is_reported_without_rethrowing_or_acknowledging_unknown_sample(self):
        root = retained_directory('sdk-uncaptured-alarm-receipt-')
        path = root/'kernel.sqlite3'
        context = multiprocessing.get_context('spawn')
        receiver, sender = context.Pipe(duplex=False)
        worker = context.Process(target=_interrupted_capture, args=(str(path), sender))
        worker.start()
        sender.close()
        try:
            worker.join(2)
            self.assertFalse(worker.is_alive(), 'original two-second process bound elapsed')
            self.assertEqual(worker.exitcode, 0)
            evidence = json.loads(path.with_suffix('.evidence.json').read_text())
            self.assertNotIn('receipt_error', evidence)
            self.assertTrue(evidence['guard_committed'], evidence)
            self.assertTrue(evidence['same_stored_error'], evidence)
            self.assertTrue(evidence['uncaptured'], evidence)
            self.assertTrue(evidence['same_envelope'], evidence)
            self.assertTrue(evidence['same_pending'], evidence)
            self.assertTrue(evidence['alarm_signals'], evidence)
            self.assertEqual(set(evidence['alarm_signals']), {signal.SIGALRM}, evidence)
            self.assertEqual(evidence['finish_sql'], [], evidence)
            self.assertEqual(evidence['wall_calls_after_arm'], evidence['wall_calls_after_receipts'], evidence)
            self.assertEqual(evidence['close_error'], 'budget_clock_cleanup_pending', evidence)
            self.assertLessEqual(evidence['alarm_deadline'], evidence['control_deadline'], evidence)
            for _ in range(2):
                self.assertTrue(receiver.poll(0), evidence)
                packet = process_runtime._receive_packet(receiver)
                self.assertEqual(packet['kind'], 'handler_timed_out', evidence)
                checkpoint = packet['budget_checkpoint']
                self.assertEqual(checkpoint['state'], 'unknown')
                self.assertEqual(checkpoint['token'], evidence['token'])
                self.assertIsNone(checkpoint['captured_envelope'])
                self.assertEqual(checkpoint['error']['cause'], '_DeadlineExpired')
            with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as connection:
                self.assertEqual(connection.execute(
                    'SELECT token,reason FROM kernel_budget_samples').fetchall(),
                    [(evidence['token'], 'sampling')])
            with SQLiteKernel(path) as recovered:
                limits = recovered.get_execution_limits('original')
                self.assertEqual(limits['clock_status'], 'unknown')
                self.assertEqual(limits['clock_unknown_reason'], 'budget_clock_sample_unresolved:sampling')
                self.assertEqual(limits['envelope'], evidence['original_envelope'])
                with self.assertRaisesRegex(BudgetClockUnknownError, 'sample_unresolved:sampling'):
                    recovered.admission_budget(ExecutionLease.from_dict(evidence['original_lease']))
                self.assertEqual(recovered.get_execution_limits('original'), limits)
                self.assertEqual(recovered._connection.execute(
                    'SELECT token,reason FROM kernel_budget_samples').fetchall()[0]['token'], evidence['token'])
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join(2)
            receiver.close()
            print('uncaptured_alarm_receipt_evidence=' + str(path.with_suffix('.evidence.json')), flush=True)


if __name__ == '__main__':
    unittest.main()
