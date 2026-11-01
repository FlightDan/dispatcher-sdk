"""Exercise real POSIX alarms during a supervisor-owned durable clock sample."""
import contextlib
import multiprocessing
import os
import signal
import sqlite3
import time
import unittest

from dispatcher_sdk.execution_kernel import _process_runtime as process
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory


def capture_during_alarm(path, delay, sender, startup=True):
    kernel = SQLiteKernel(path)
    command = ExecutionCommandV2('alarm', 'alarm', 'alarm', 'alarm', None, 'work', 1, RetryPolicy(), 5, {})
    kernel.submit(command)
    lease = kernel.claim_and_start('owner', execution_id='alarm')
    envelope = kernel.prepare_execution_budget(lease).enter_handler(5, origin_id='execution:alarm')
    envelope = kernel.confirm_handler_entry(lease, envelope)
    owner = process._KernelBudgetCapture(kernel, 'alarm')
    guard = process._DeadlineGuard(time.monotonic() + .08, envelope, None, owner)
    guard._startup_capture_deferral = startup
    original = kernel._begin_budget_sample
    captured = owner._captured
    evidence = {'business': False, 'alarm_during_owned_sample': False}
    def record_capture(token, observed):
        evidence['captured_token'] = token
        evidence['captured_envelope'] = observed.to_dict()
        captured(token, observed)
    owner._captured = record_capture
    def delayed(*args, **kwargs):
        token = original(*args, **kwargs)
        time.sleep(delay)
        return token
    kernel._begin_budget_sample = delayed
    started = time.monotonic()
    worker = None
    if not startup:
        worker = os.fork()
        if worker == 0:
            time.sleep(.25)
            with open(path + '.business', 'w') as output:
                output.write('late')
            os._exit(0)
    def alarm(*_):
        if guard.remaining() <= 0 and owner._pending is not None:
            evidence['alarm_during_owned_sample'] = True
        guard.alarm()
    previous = signal.signal(signal.SIGALRM, alarm)
    try:
        guard.arm()
        try:
            if guard.remaining(resample=True) <= 0:
                raise process._DeadlineExpired()
            evidence['business'] = True
        except process._DeadlineExpired:
            evidence['expired'] = True
            evidence['deadline_elapsed'] = time.monotonic() - started
            if worker is not None:
                os.kill(worker, signal.SIGKILL)
                os.waitpid(worker, 0)
                worker = None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        _, receipt = process._finish_budget_capture(owner, guard.snapshot(), timeout_seconds=.1)
        evidence['receipt'] = receipt
        evidence['business'] = evidence['business'] or os.path.exists(path + '.business')
        evidence['committed_envelope'] = kernel.get_execution_limits('alarm')['envelope']
        evidence['elapsed'] = time.monotonic() - started
        try:
            kernel.close()
            evidence['close'] = 'confirmed'
        except BudgetClockUnknownError:
            evidence['close'] = 'unknown'
        with contextlib.closing(sqlite3.connect(path)) as connection, connection:
            evidence['samples'] = connection.execute('SELECT count(*) FROM kernel_budget_samples').fetchone()[0]
        sender.send(evidence)
    finally:
        if worker is not None:
            os.kill(worker, signal.SIGKILL)
            os.waitpid(worker, 0)
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        sender.close()


@unittest.skipUnless(os.name == 'posix' and hasattr(signal, 'setitimer'), 'requires POSIX alarm')
class SupervisorCaptureAlarmTests(unittest.TestCase):
    def run_capture(self, delay, *, startup=True):
        root = retained_directory('sdk-supervisor-capture-alarm-')
        context = multiprocessing.get_context('spawn')
        receiver, sender = context.Pipe(duplex=False)
        child = context.Process(target=capture_during_alarm, args=(str(root / 'kernel.sqlite3'), delay, sender, startup))
        child.start()
        sender.close()
        try:
            self.assertTrue(receiver.poll(3), 'child failed to return evidence')
            evidence = receiver.recv()
            child.join(2)
            self.assertEqual(child.exitcode, 0)
            self.assertTrue(evidence['expired'], evidence)
            self.assertFalse(evidence['business'], evidence)
            self.assertTrue(evidence['alarm_during_owned_sample'], evidence)
            return evidence
        finally:
            if child.is_alive():
                child.kill()
                child.join(2)
            receiver.close()

    def test_observation_finishes_after_alarm_and_acknowledges_exact_fact(self):
        evidence = self.run_capture(.1)
        self.assertEqual(evidence['receipt']['state'], 'confirmed', evidence)
        self.assertEqual(evidence['receipt']['token'], evidence['captured_token'], evidence)
        observed = BudgetEnvelope.from_dict(evidence['captured_envelope']).checkpoint
        committed = BudgetEnvelope.from_dict(evidence['committed_envelope']).checkpoint
        self.assertGreaterEqual(committed.effective_time(observed), observed.effective_time(observed), evidence)
        self.assertEqual(evidence['close'], 'confirmed', evidence)
        self.assertEqual(evidence['samples'], 0, evidence)

    def test_stuck_observation_is_interrupted_and_remains_unknown(self):
        evidence = self.run_capture(.5)
        self.assertEqual(evidence['receipt']['state'], 'unknown', evidence)
        self.assertTrue(evidence['receipt'].get('token'), evidence)
        self.assertIsNone(evidence['receipt']['captured_envelope'], evidence)
        self.assertEqual(evidence['close'], 'unknown', evidence)
        self.assertEqual(evidence['samples'], 1, evidence)
        self.assertLess(evidence['elapsed'], .4, evidence)

    def test_active_worker_is_killed_at_deadline_during_stalled_capture(self):
        evidence = self.run_capture(.5, startup=False)
        self.assertLess(evidence['deadline_elapsed'], .16, evidence)
        self.assertEqual(evidence['receipt']['state'], 'unknown', evidence)
        self.assertIsNone(evidence['receipt']['captured_envelope'], evidence)
        self.assertEqual(evidence['samples'], 1, evidence)
