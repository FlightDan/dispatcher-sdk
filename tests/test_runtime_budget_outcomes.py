"""Captured terminal budget floors survive completion and denied retries."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager, nullcontext
from pathlib import Path
import sqlite3
import sys
import threading
import time
import traceback
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

import dispatcher_sdk
from dispatcher_sdk.execution_kernel import HandlerExecutionError, Kernel
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.contracts import ExecutionResultV2, RetryPolicy


class HandlerClock:
    """A caller-provided clock with forward samples scoped to its calling thread.

    The instance is pickleable; each process/thread initializes its own local
    sample. Host deadline observers continue sampling the original real clock.
    """
    _sample = threading.local()

    def __init__(self, fixed_wall=None):
        self.fixed_wall = fixed_wall

    def __call__(self):
        value = getattr(self._sample, 'wall', self.fixed_wall)
        return time.time() if value is None else value

    @classmethod
    @contextmanager
    def sample_wall(cls, value):
        previous = getattr(cls._sample, 'wall', None)
        cls._sample.wall = value
        try:
            yield
        finally:
            if previous is None:
                del cls._sample.wall
            else:
                cls._sample.wall = previous


def observe_expired_then_roll_back(payload, context):
    root = Path(payload['root'])
    with (root / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'attempt': context.lease.attempt, 'pid': os.getpid()}) + '\n')
    if context.lease.attempt == 1:
        if not payload.get('expire_at_native_normalization'):
            forward = context.budget.effective_work_deadline_at + 1
            with HandlerClock.sample_wall(forward):
                observed = context.budget.to_dict()
                (root / 'observed.json').write_text(json.dumps(observed), encoding='utf-8')
            # The real context must retain its expired floor after the fixture
            # restores normal sampling; no host-visible file triggers an early kill.
            restored = context.budget.to_dict()
            (root / 'observed-after-rollback.json').write_text(json.dumps(restored), encoding='utf-8')
            (root / 'clock-sampling.json').write_text(json.dumps({'pid': os.getpid(),
                'thread_id': threading.get_ident(), 'forward_wall': forward, 'restored_real_wall': time.time(),
                'interpreter': sys.executable, 'sdk_import': dispatcher_sdk.__file__,
                'source': 'caller-provided HandlerClock',
                'scope': 'handler calling thread; host deadline clock unchanged'}), encoding='utf-8')
        if payload['failure']:
            (root / 'handler-outcome.json').write_text(json.dumps({'kind': 'error',
                'code': 'original_failure', 'message': 'raw original failure', 'retryable': True}), encoding='utf-8')
            raise HandlerExecutionError('original_failure', 'raw original failure', retryable=True)
        (root / 'handler-outcome.json').write_text(json.dumps({'kind': 'ok',
            'value': {'original': 42, 'attempt': context.lease.attempt}}), encoding='utf-8')
    return {'original': 42, 'attempt': context.lease.attempt}


observe_expired_then_roll_back.__execution_kernel_revision__ = 'observed-terminal-budget-v1'


class RuntimeBudgetOutcomeTests(unittest.TestCase):
    @contextmanager
    def native_terminal_expiration(self, runtime, root, evidence):
        if os.name == 'nt':
            from dispatcher_sdk.execution_kernel import _windows_runtime as native_runtime
        else:
            from dispatcher_sdk.execution_kernel import _process_runtime as native_runtime
        normalize = native_runtime._budget_outcome

        def expire_received_outcome(outcome, envelope, entry=None):
            # This host boundary receives the SDK's decoded native packet
            # after containment. A handler file is not a return-packet proof.
            self.assertIsNotNone(entry, outcome)
            self.assertEqual('error' if evidence['failure'] else 'ok', outcome.get('kind'), outcome)
            self.assertFalse(outcome.get('control_error'), outcome)
            self.assertNotIn('received_native_outcome', evidence)
            evidence['received_native_outcome'] = json.loads(json.dumps(outcome))
            raw = json.loads((root / 'handler-outcome.json').read_text())
            for key, value in raw.items():
                self.assertEqual(outcome[key], value, outcome)
            returned = BudgetEnvelope.from_dict(outcome['budget_envelope'])
            forward = returned.view(sample=returned.checkpoint).effective_work_deadline_at + 1
            with HandlerClock.sample_wall(forward):
                captured = runtime.kernel._sample_budget('original', returned, timeout_seconds=.1)
            restored = runtime.kernel._sample_budget('original', captured, timeout_seconds=.1)
            self.assertEqual(returned.constraints, captured.constraints)
            self.assertEqual(returned.started_at, captured.started_at)
            observed = captured.view(sample=captured.checkpoint).to_dict()
            after_rollback = restored.view(sample=restored.checkpoint).to_dict()
            (root / 'observed.json').write_text(json.dumps(observed), encoding='utf-8')
            (root / 'observed-after-rollback.json').write_text(json.dumps(after_rollback), encoding='utf-8')
            (root / 'clock-sampling.json').write_text(json.dumps({'pid': os.getpid(),
                'thread_id': threading.get_ident(), 'forward_wall': forward, 'restored_real_wall': time.time(),
                'interpreter': sys.executable, 'sdk_import': dispatcher_sdk.__file__,
                'source': 'caller-provided HandlerClock through actual Kernel budget capture',
                'scope': 'host terminal normalization after decoded native outcome handoff'}), encoding='utf-8')
            # Inject the captured expiration at terminal normalization, keeping
            # the real entry packet and raw business fields. This does not
            # claim that the worker returned late or that cleanup expiry alone
            # should relabel a timely business return.
            return normalize({**outcome, 'budget_envelope': captured.to_dict()}, restored, entry)

        with patch.object(native_runtime, '_budget_outcome', expire_received_outcome):
            yield

    def run_expired_completion(self, isolation, failure):
        root = retained_directory('sdk-terminal-budget-outcome-')
        evidence = {'isolation': isolation, 'failure': failure, 'timeout_seconds': 10, 'lease_seconds': 90,
            'clock_sampling': 'caller clock forward sample only in actual handler; original host cutoff retained'}
        try:
            with Kernel.open_sqlite(root / 'kernel.sqlite3', {'work': observe_expired_then_roll_back},
                                   isolation_mode=isolation, now=HandlerClock(),
                                   lease_seconds=90) as runtime:
                payload = {'root': str(root), 'failure': failure}
                if isolation == 'process':
                    payload['expire_at_native_normalization'] = True
                    evidence['clock_sampling'] = 'actual host terminal-normalization capture after native handoff'
                runtime.submit(runtime.command('work', execution_id='original', idempotency_key='original',
                    correlation_id='original', timeout_seconds=10,
                    retry_policy=RetryPolicy(max_attempts=2, retry_timeouts=True),
                    payload=payload))
                with (self.native_terminal_expiration(runtime, root, evidence)
                      if isolation == 'process' else nullcontext()):
                    first = runtime.run_once(execution_id='original')
                evidence['first'] = first.to_dict()
                evidence['first_limits'] = runtime.kernel.get_execution_limits('original')
                evidence['first_receipts'] = runtime._settlement_journal.inspect('original', timeout_seconds=.5)
                second = runtime.run_once(execution_id='original')
                evidence['second'] = second.to_dict()
                evidence['second_limits'] = runtime.kernel.get_execution_limits('original')
                evidence['observed'] = json.loads((root / 'observed.json').read_text())
                evidence['after_rollback'] = json.loads((root / 'observed-after-rollback.json').read_text())
                evidence['sampling'] = json.loads((root / 'clock-sampling.json').read_text())
                evidence['handler_outcome'] = json.loads((root / 'handler-outcome.json').read_text())
                evidence['final_receipts'] = runtime._settlement_journal.inspect('original', timeout_seconds=.5)
                evidence['calls'] = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
                self.assertEqual([item['attempt'] for item in evidence['calls']], [1], evidence)
                self.assertEqual(first.state, 'queued', evidence)
                self.assertEqual(second.state, 'dead', evidence)
                self.assertEqual(evidence['observed']['remaining_work_seconds'], 0)
                self.assertEqual(evidence['after_rollback']['remaining_work_seconds'], 0)
                before, after = (evidence[key]['envelope'] for key in ('first_limits', 'second_limits'))
                self.assertEqual(before['constraints'], after['constraints'])
                self.assertEqual(before['started_at'], after['started_at'])
                self.assertGreaterEqual(before['checkpoint']['wall_at'], evidence['observed']['observed_at'])
                self.assertGreaterEqual(after['checkpoint']['wall_at'], before['checkpoint']['wall_at'])
                self.assertEqual(second.result.error.details['last_result']['status'], 'timed_out')
                original = next(receipt for receipt in evidence['first_receipts'] if receipt['identity']['attempt'] == 1)
                after_retry = next(receipt for receipt in evidence['final_receipts'] if receipt['identity']['attempt'] == 1)
                self.assertEqual(after_retry['result'], original['result'])
                if isolation == 'process':
                    self.assertNotEqual(evidence['calls'][0]['pid'], os.getpid())
                    retained_outcome = original['result']['error']['details']['business_outcome']
                    for key, value in evidence['handler_outcome'].items():
                        self.assertEqual(retained_outcome[key], value, evidence)
        except BaseException as error:
            evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            path = root / 'evidence.json'
            path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print('terminal_budget_outcome_evidence=' + str(path), flush=True)

    def test_thread_return_preserves_expired_floor(self):
        self.run_expired_completion('thread', False)

    def test_thread_raw_failure_preserves_expired_floor(self):
        self.run_expired_completion('thread', True)

    def test_native_return_preserves_expired_floor(self):
        self.run_expired_completion('process', False)

    def test_native_raw_failure_preserves_expired_floor(self):
        self.run_expired_completion('process', True)

    def test_runtime_and_journal_reopen_restore_original_expired_floor_under_wall_rollback(self):
        root = retained_directory('sdk-runtime-budget-reopen-')
        evidence = {'timeout_seconds': 10, 'lease_seconds': 90,
            'clock_sampling': 'caller clock forward sample only in actual handler; original host cutoff retained',
            'barrier': 'actual outcome normalization pauses only until external SQLite writer is held'}
        runtime = reopened = writer = driver = None
        outcome_ready, writer_held = threading.Event(), threading.Event()
        originals, results, errors = [], [], []
        driver_tracebacks = []
        try:
            runtime = Kernel.open_sqlite(root / 'kernel.sqlite3', {'work': observe_expired_then_roll_back},
                isolation_mode='thread', now=HandlerClock(), lease_seconds=90)
            runtime.submit(runtime.command('work', execution_id='original', idempotency_key='original',
                correlation_id='original', timeout_seconds=10,
                payload={'root': str(root), 'failure': False}))
            normalize = runtime._outcome_result

            def hold_actual_outcome(*args):
                original = normalize(*args)
                originals.append(original)
                outcome_ready.set()
                if not writer_held.wait(3):
                    raise AssertionError('external writer was not held after actual handler outcome')
                return original

            runtime._outcome_result = hold_actual_outcome

            def drive():
                try:
                    results.append(runtime.run_once(execution_id='original'))
                except BaseException as error:
                    errors.append(error)
                    driver_tracebacks.append(traceback.format_exc())

            driver = threading.Thread(target=drive)
            driver.start()
            self.assertTrue(outcome_ready.wait(3), errors)
            writer = sqlite3.connect(runtime.kernel.db_path, timeout=.1)
            writer.execute('BEGIN IMMEDIATE')
            writer_held.set()
            driver.join(3)
            evidence['driver_errors'] = [{'type': type(error).__name__, 'message': str(error), 'traceback': trace}
                for error, trace in zip(errors, driver_tracebacks)]
            evidence['returned'] = [result.to_dict() for result in results]
            evidence['originals'] = [original.to_dict() for original in originals]
            self.assertFalse(driver.is_alive(), evidence)
            self.assertEqual(errors, [], evidence)
            self.assertEqual(len(results), 1, evidence)
            self.assertEqual(results[0].state, 'running', evidence)
            self.assertIsNone(results[0].result)
            receipt = runtime._settlement_journal.inspect('original', timeout_seconds=.5)[0]
            evidence['pending_receipt'] = receipt
            evidence['before_limits'] = runtime.kernel.get_execution_limits('original')
            evidence['observed'] = json.loads((root / 'observed.json').read_text())
            evidence['after_rollback'] = json.loads((root / 'observed-after-rollback.json').read_text())
            evidence['sampling'] = json.loads((root / 'clock-sampling.json').read_text())
            evidence['handler_outcome'] = json.loads((root / 'handler-outcome.json').read_text())
            self.assertEqual(evidence['after_rollback']['remaining_work_seconds'], 0)
            original = originals[0]
            retained = BudgetEnvelope.from_dict(receipt['evidence']['budget_envelope'])
            self.assertEqual(ExecutionResultV2.from_dict(receipt['result']).to_json(), original.to_json())
            self.assertEqual(original.status, 'timed_out')
            self.assertIn(receipt['state'], {'pending', 'error'})
            self.assertGreaterEqual(retained.checkpoint.wall_at, evidence['observed']['observed_at'])
            self.assertEqual(retained.view(sample=sample_clock(wall_time=original.started_at)).remaining_work_seconds, 0)
            cutoff = next(item for item in retained.constraints if item.origin_id == 'execution:original')
            self.assertEqual(cutoff.deadline_at, retained.started_at + 10)
            self.assertEqual(runtime.lease_seconds, 90)

            # Supported close stops automatic recovery while the real writer
            # still excludes Kernel publication; the durable receipt survives.
            runtime.close()
            writer.rollback()
            writer.close()
            writer = None
            evidence['reopened_wall'] = original.started_at
            reopened = Kernel.open_sqlite(root / 'kernel.sqlite3', {'work': observe_expired_then_roll_back},
                isolation_mode='thread', now=HandlerClock(fixed_wall=original.started_at), lease_seconds=90)
            self.assertIsNot(reopened._settlement_journal, runtime._settlement_journal)
            before_recovery = reopened._settlement_journal.inspect('original', timeout_seconds=.5)[0]
            evidence['reopened_receipt'] = before_recovery
            self.assertEqual(before_recovery['result'], receipt['result'])
            self.assertEqual(before_recovery['evidence']['budget_envelope'], retained.to_dict())
            evidence['recovery_reports'] = reopened.recover_completions(timeout_seconds=.5)
            restored = reopened.kernel.get('original')
            evidence['restored'] = restored.to_dict()
            evidence['after_limits'] = reopened.kernel.get_execution_limits('original')
            after = BudgetEnvelope.from_dict(evidence['after_limits']['envelope'])
            self.assertIsNotNone(restored.result, evidence)
            self.assertEqual(restored.result.to_json(), original.to_json(), evidence)
            self.assertEqual(after.constraints, retained.constraints)
            self.assertEqual(after.started_at, retained.started_at)
            self.assertGreaterEqual(after.checkpoint.wall_at, retained.checkpoint.wall_at)
            self.assertEqual(after.view(sample=sample_clock(wall_time=original.started_at)).remaining_work_seconds, 0)
            settled = reopened._settlement_journal.inspect('original', timeout_seconds=.5)[0]
            evidence['settled_receipt'] = settled
            self.assertEqual(settled['state'], 'recorded', evidence)
            self.assertEqual(settled['result'], receipt['result'])
            self.assertIsNone(reopened.run_once(execution_id='original'))
            evidence['calls'] = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
            self.assertEqual([call['attempt'] for call in evidence['calls']], [1], evidence)
        except BaseException as error:
            evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            try:
                writer_held.set()
                if driver is not None:
                    driver.join(3)
                if writer is not None:
                    writer.rollback()
                    writer.close()
                for instance in (reopened, runtime):
                    if instance is not None:
                        instance.close()
            finally:
                path = root / 'evidence.json'
                path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
                print('runtime_budget_reopen_evidence=' + str(path), flush=True)
