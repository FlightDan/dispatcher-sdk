"""A native caller-only clock observation survives timeout settlement and retry."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel import Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, DeadlineConstraint, sample_clock


class ParentWaitClock:
    """One forward sample only in the parent's real packet-wait timer.

    Entry ACK arms this fixture in the caller after native startup. Frame
    inspection scopes the injected clock to the actual packet-wait timer;
    Kernel, telemetry, supervisor, and worker reads always return wall100.
    """
    def __init__(self, root):
        self.root = str(root)
        self.parent_pid = os.getpid()
        self.parent_thread = threading.get_ident()
        self.entry = None
        self.fired = False

    def __call__(self):
        if (self.entry is None or self.fired or os.getpid() != self.parent_pid
                or threading.get_ident() != self.parent_thread):
            return 100.0
        frame = sys._getframe(1)
        stack = []
        while frame is not None:
            stack.append({'name': frame.f_code.co_name, 'file': frame.f_code.co_filename,
                          'line': frame.f_lineno})
            frame = frame.f_back
        marker = Path(self.root) / 'worker-entry.json'
        if not any(item['name'] == '_wait_packet' for item in stack) or not marker.exists():
            return 100.0
        worker = json.loads(marker.read_text(encoding='utf-8'))
        if worker['attempt'] != 1:
            return 100.0
        self.fired = True
        wall = worker['budget']['effective_work_deadline_at'] + 1
        (Path(self.root) / 'parent-forward.json').write_text(json.dumps({
            'pid': os.getpid(), 'wall_sample': wall, 'monotonic': time.monotonic(),
            'stack': stack, 'worker_entry': worker}), encoding='utf-8')
        return wall


class SupervisorGuardClock(ParentWaitClock):
    """Only the native supervisor's explicit guard resample jumps forward."""
    def __call__(self):
        if self.fired or os.getpid() == self.parent_pid:
            return 100.0
        frame = sys._getframe(1)
        stack, guard_resample = [], False
        while frame is not None:
            owner = frame.f_locals.get('self')
            if (frame.f_code.co_name == 'remaining' and frame.f_locals.get('resample') is True
                    and type(owner).__name__ == '_DeadlineGuard'):
                guard_resample = True
            stack.append({'name': frame.f_code.co_name, 'file': frame.f_code.co_filename,
                          'line': frame.f_lineno})
            frame = frame.f_back
        marker = Path(self.root) / 'worker-entry.json'
        if not guard_resample or not marker.exists():
            return 100.0
        worker = json.loads(marker.read_text(encoding='utf-8'))
        if worker['attempt'] != 1:
            return 100.0
        self.fired = True
        wall = worker['budget']['effective_work_deadline_at'] + 1
        (Path(self.root) / 'supervisor-forward.json').write_text(json.dumps({
            'pid': os.getpid(), 'wall_sample': wall, 'monotonic': time.monotonic(),
            'stack': stack, 'worker_entry': worker}), encoding='utf-8')
        return wall


def native_wait_then_return(payload, context):
    root = Path(payload['root'])
    call = {'attempt': context.lease.attempt, 'pid': os.getpid(),
            'budget': context.budget.to_dict(), 'monotonic': time.monotonic()}
    with (root / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(call) + '\n')
    temporary = root / 'worker-entry.new'
    temporary.write_text(json.dumps(call), encoding='utf-8')
    os.replace(temporary, root / 'worker-entry.json')
    if context.lease.attempt == 1:
        time.sleep(payload['hold_seconds'])
    return {'business_attempt': context.lease.attempt}


native_wait_then_return.__execution_kernel_revision__ = 'native-parent-floor-v1'


@unittest.skipUnless(sys.platform == 'linux', 'requires real POSIX process containment')
class ParentBudgetFloorTests(unittest.TestCase):
    def test_alarm_observation_between_normal_capture_and_assignment_keeps_stronger_floor(self):
        root = retained_directory('sdk-alarm-budget-floor-')
        checkpoint = sample_clock(wall_time=100)
        envelope = BudgetEnvelope((DeadlineConstraint('execution:original', 'execution', 110),),
                                  checkpoint, started_at=100)
        evidence = {'interleaving': 'emulate actual alarm callback after normal checkpoint computes, before normal assignment',
                    'original': envelope.to_dict(), 'callback_count': 0}
        recheckpoint = BudgetEnvelope.recheckpoint
        try:
            with patch.object(process_runtime, '_budget_sample', return_value=checkpoint):
                guard = process_runtime._DeadlineGuard(time.monotonic() + 10, envelope, None)
            def interrupted_capture(current, *, sample=None):
                captured = recheckpoint(current, sample=sample)
                if evidence['callback_count'] == 0:
                    evidence['callback_count'] += 1
                    # The signal path sees the sole forward sample. Normal
                    # execution then resumes with its already computed older
                    # object, exactly the assignment that previously lost it.
                    with patch.object(process_runtime.time, 'time', return_value=111):
                        evidence['alarm_remaining'] = guard.remaining()
                        evidence['alarm_snapshot'] = guard.snapshot().to_dict()
                return captured
            with patch.object(process_runtime, '_budget_sample', return_value=sample_clock(wall_time=100)):
                with patch.object(BudgetEnvelope, 'recheckpoint', new=interrupted_capture):
                    evidence['normal_remaining'] = guard.remaining(resample=True)
            retained = guard.snapshot()
            evidence['normal_envelope'] = guard.envelope.to_dict()
            evidence['retained'] = retained.to_dict()
            self.assertEqual(evidence['callback_count'], 1)
            self.assertLessEqual(evidence['alarm_remaining'], 0)
            self.assertLess(guard.envelope.checkpoint.wall_at, 110, evidence)
            self.assertGreaterEqual(retained.checkpoint.wall_at, 111, evidence)
            self.assertEqual(retained.constraints, envelope.constraints)
            self.assertEqual(retained.view(sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)
            self.assertLessEqual(evidence['normal_remaining'], 0)
        except BaseException as error:
            evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            path = root / 'evidence.json'
            path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print('alarm_budget_floor_evidence=' + str(path), flush=True)

    def test_parent_only_expiry_survives_rollback_and_rejects_actual_native_retry(self):
        self.run_observer_expiry('parent')

    def test_supervisor_only_expiry_survives_terminal_packet_and_rejects_native_retry(self):
        self.run_observer_expiry('supervisor')

    def run_observer_expiry(self, scope):
        root = retained_directory('sdk-' + scope + '-budget-floor-')
        clock = ParentWaitClock(root) if scope == 'parent' else SupervisorGuardClock(root)
        evidence = {'timeout_seconds': 10, 'lease_seconds': 90,
            'timer_scope': scope, 'hold_seconds': 3 if scope == 'parent' else .2,
            'interpreter': sys.executable, 'runtime_import': runtime_module.__file__,
            'backend_import': process_runtime.__file__,
            'clock_injection': 'one selected native timer sample jumps past original cutoff; all other/subsequent wall reads100'}
        invoke = runtime_module.invoke_process_handler

        def with_actual_entry(*args, **kwargs):
            callback = kwargs.get('on_entered')
            def entered(packet):
                if packet.get('started_at') is not None:
                    clock.entry = packet
                if callback is not None:
                    callback(packet)
            kwargs['on_entered'] = entered
            return invoke(*args, **kwargs)

        try:
            with patch.object(runtime_module, 'invoke_process_handler', side_effect=with_actual_entry):
                with Kernel.open_sqlite(root / 'kernel.sqlite3', {'work': native_wait_then_return},
                        isolation_mode='process', now=clock, lease_seconds=90) as runtime:
                    runtime.submit(runtime.command('work', execution_id='original', idempotency_key='original',
                        correlation_id='parent-floor', timeout_seconds=10,
                        retry_policy=RetryPolicy(max_attempts=2, retry_timeouts=True),
                        payload={'root': str(root), 'hold_seconds': evidence['hold_seconds']}))
                    first = runtime.run_once(execution_id='original')
                    evidence['first'] = first.to_dict()
                    evidence['first_limits'] = runtime.kernel.get_execution_limits('original')
                    evidence['first_receipts'] = runtime._settlement_journal.inspect('original', timeout_seconds=.5)
                    envelope = BudgetEnvelope.from_dict(evidence['first_limits']['envelope'])
                    evidence['first_budget_after_rollback'] = envelope.view(sample=sample_clock(wall_time=100)).to_dict()
                    marker = root / (scope + '-forward.json')
                    evidence['timer_forward'] = json.loads(marker.read_text()) if marker.exists() else None
                    evidence['parent_wall_after_first'] = clock()
                    # Drive the original queued retry once, preserving its
                    # policy and cutoff; a spent window must refuse business.
                    second = runtime.run_once(execution_id='original')
                    evidence['second'] = None if second is None else second.to_dict()
                    evidence['second_limits'] = runtime.kernel.get_execution_limits('original')
                    evidence['calls'] = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
                    evidence['final_receipts'] = runtime._settlement_journal.inspect('original', timeout_seconds=.5)
                    evidence['parent_wall_after_retry'] = clock()
                    self.assertIsNotNone(evidence['timer_forward'], evidence)
                    self.assertEqual(evidence['parent_wall_after_first'], 100)
                    self.assertEqual(evidence['parent_wall_after_retry'], 100)
                    if scope == 'parent':
                        self.assertTrue(clock.fired, evidence)
                        self.assertEqual(evidence['timer_forward']['pid'], os.getpid(), evidence)
                    else:
                        self.assertFalse(clock.fired, evidence)
                        self.assertNotEqual(evidence['timer_forward']['pid'], os.getpid(), evidence)
                        self.assertNotEqual(evidence['timer_forward']['pid'], evidence['calls'][0]['pid'], evidence)
                    self.assertEqual(first.state, 'queued', evidence)
                    original = next(item for item in evidence['first_receipts'] if item['identity']['attempt'] == 1)
                    self.assertEqual(original['result']['status'], 'timed_out', evidence)
                    self.assertEqual(original['result']['error']['code'], 'handler_timeout', evidence)
                    retained = BudgetEnvelope.from_dict(original['evidence']['budget_envelope'])
                    self.assertGreaterEqual(retained.checkpoint.wall_at, evidence['timer_forward']['wall_sample'], evidence)
                    self.assertEqual(evidence['first_budget_after_rollback']['remaining_work_seconds'], 0, evidence)
                    self.assertEqual([call['attempt'] for call in evidence['calls']], [1], evidence)
                    self.assertNotEqual(evidence['calls'][0]['pid'], os.getpid(), evidence)
                    self.assertIsNotNone(second, evidence)
                    self.assertEqual(second.state, 'dead', evidence)
                    self.assertEqual(second.result.error.details['last_result']['status'], 'timed_out', evidence)
                    self.assertEqual(evidence['first_limits']['envelope']['constraints'],
                        evidence['second_limits']['envelope']['constraints'], evidence)
                    first_receipt_after = next(item for item in evidence['final_receipts'] if item['identity']['attempt'] == 1)
                    self.assertEqual(first_receipt_after['result'], original['result'], evidence)
        except BaseException as error:
            evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            path = root / 'evidence.json'
            path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print('parent_budget_floor_evidence=' + str(path), flush=True)
