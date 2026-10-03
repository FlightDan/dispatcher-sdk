"""Actual worker clock observations survive completion and denied retries."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import unittest

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk.execution_kernel import HandlerExecutionError, Kernel
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.contracts import ExecutionResultV2, RetryPolicy


class FileClock:
    def __init__(self, path):
        self.path = str(path)

    def __call__(self):
        value = json.loads(Path(self.path).read_text(encoding='utf-8'))
        return time.time() if value is None else value


def set_clock(root, value):
    temporary = root / 'clock.new'
    temporary.write_text(json.dumps(value), encoding='utf-8')
    os.replace(temporary, root / 'clock.json')


def observe_expired_then_roll_back(payload, context):
    root = Path(payload['root'])
    with (root / 'calls.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'attempt': context.lease.attempt, 'pid': os.getpid()}) + '\n')
    if context.lease.attempt == 1:
        set_clock(root, context.budget.effective_work_deadline_at + 1)
        observed = context.budget.to_dict()
        set_clock(root, None)
        (root / 'observed.json').write_text(json.dumps(observed), encoding='utf-8')
        if payload['failure']:
            raise HandlerExecutionError('original_failure', 'raw original failure', retryable=True)
    return {'original': 42, 'attempt': context.lease.attempt}


observe_expired_then_roll_back.__execution_kernel_revision__ = 'observed-terminal-budget-v1'


class RuntimeBudgetOutcomeTests(unittest.TestCase):
    def run_expired_completion(self, isolation, failure):
        root = retained_directory('sdk-terminal-budget-outcome-')
        set_clock(root, None)
        evidence = {'isolation': isolation, 'failure': failure, 'timeout_seconds': 10, 'lease_seconds': 90}
        try:
            with Kernel.open_sqlite(root / 'kernel.sqlite3', {'work': observe_expired_then_roll_back},
                                   isolation_mode=isolation, now=FileClock(root / 'clock.json'),
                                   lease_seconds=90) as runtime:
                runtime.submit(runtime.command('work', execution_id='original', idempotency_key='original',
                    correlation_id='original', timeout_seconds=10,
                    retry_policy=RetryPolicy(max_attempts=2, retry_timeouts=True),
                    payload={'root': str(root), 'failure': failure}))
                first = runtime.run_once(execution_id='original')
                evidence['first'] = first.to_dict()
                evidence['first_limits'] = runtime.kernel.get_execution_limits('original')
                second = runtime.run_once(execution_id='original')
                evidence['second'] = second.to_dict()
                evidence['second_limits'] = runtime.kernel.get_execution_limits('original')
                evidence['observed'] = json.loads((root / 'observed.json').read_text())
                evidence['calls'] = [json.loads(line) for line in (root / 'calls.jsonl').read_text().splitlines()]
                self.assertEqual([item['attempt'] for item in evidence['calls']], [1], evidence)
                self.assertEqual(first.state, 'queued', evidence)
                self.assertEqual(second.state, 'dead', evidence)
                self.assertEqual(evidence['observed']['remaining_work_seconds'], 0)
                before, after = (evidence[key]['envelope'] for key in ('first_limits', 'second_limits'))
                self.assertEqual(before['constraints'], after['constraints'])
                self.assertEqual(before['started_at'], after['started_at'])
                self.assertGreaterEqual(before['checkpoint']['wall_at'], evidence['observed']['observed_at'])
                self.assertGreaterEqual(after['checkpoint']['wall_at'], before['checkpoint']['wall_at'])
                self.assertEqual(second.result.error.details['last_result']['status'], 'timed_out')
                if isolation == 'process':
                    self.assertNotEqual(evidence['calls'][0]['pid'], os.getpid())
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
        set_clock(root, None)
        evidence = {'timeout_seconds': 10, 'lease_seconds': 90,
            'barrier': 'actual outcome normalization pauses only until external SQLite writer is held'}
        runtime = reopened = writer = driver = None
        outcome_ready, writer_held = threading.Event(), threading.Event()
        originals, results, errors = [], [], []
        try:
            runtime = Kernel.open_sqlite(root / 'kernel.sqlite3', {'work': observe_expired_then_roll_back},
                isolation_mode='thread', now=FileClock(root / 'clock.json'), lease_seconds=90)
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

            driver = threading.Thread(target=drive)
            driver.start()
            self.assertTrue(outcome_ready.wait(3), errors)
            writer = sqlite3.connect(runtime.kernel.db_path, timeout=.1)
            writer.execute('BEGIN IMMEDIATE')
            writer_held.set()
            driver.join(3)
            evidence['driver_errors'] = [{'type': type(error).__name__, 'message': str(error)} for error in errors]
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
            set_clock(root, original.started_at)
            reopened = Kernel.open_sqlite(root / 'kernel.sqlite3', {'work': observe_expired_then_roll_back},
                isolation_mode='thread', now=FileClock(root / 'clock.json'), lease_seconds=90)
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
