from pathlib import Path
import json
import os
import sqlite3
import sys
import time
import traceback
import unittest

import dispatcher_sdk
from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.children import ChildExecutionError
from tests._acceptance_evidence import retained_directory


# Nominal integration uses the public example's original windows. Deadline
# boundary behavior has separate contention and timeout witnesses.
PARENT_SECONDS = 12
CHILD_CALL_SECONDS = 5


def child_handler(payload, context):
    context.activity.report_bytes('stdout', b'raw-without-newline\xff')
    context.activity.progress('child-finished')
    return {'value': payload['value'], 'budget': context.budget.to_dict()}


def failing_child(payload, context):
    from dispatcher_sdk.execution_kernel import HandlerExecutionError
    raise HandlerExecutionError('provider_denied', 'original provider failure', details={'provider': 'fixture'})


def _capture_child_call_error(payload, error):
    """Optional fixture diagnostics cannot replace the actual child exception."""
    diagnostic_path = payload.get('_child_diagnostic_path')
    if diagnostic_path is None:
        return
    try:
        chain, seen = [], set()
        current = error
        while current is not None and id(current) not in seen and len(chain) < 8:
            seen.add(id(current))
            chain.append({'type': type(current).__name__, 'message': str(current)[:8192],
                'sqlite_errorcode': getattr(current, 'sqlite_errorcode', None),
                'sqlite_errorname': getattr(current, 'sqlite_errorname', None),
                'code': getattr(current, 'code', None),
                'traceback': ''.join(traceback.format_tb(current.__traceback__, limit=16))[:16384]})
            current = current.__cause__ if current.__cause__ is not None else (
                None if current.__suppress_context__ else current.__context__)
        Path(diagnostic_path).write_text(json.dumps({'phase': 'parent_child_run',
            'captured_at': time.time(), 'worker_pid': os.getpid(), 'exception_chain': chain,
            'chain_truncated': current is not None}, indent=2), encoding='utf-8')
    except Exception:
        # Failure to write optional evidence must preserve the original error.
        pass


def parent_handler(payload, context):
    before = context.budget.to_dict()
    try:
        try:
            child = context.children.run(payload.get('handler', 'child'), {'value': 9},
                request_id='one-child', timeout_seconds=CHILD_CALL_SECONDS)
        except Exception as error:
            _capture_child_call_error(payload, error)
            raise
    except ChildExecutionError as exc:
        cause = exc.__cause__
        return {'child_error': exc.result, 'code': exc.code, 'child_error_message': str(exc),
            'child_execution_id': exc.execution_id,
            'child_error_cause': None if cause is None else {
                'type': type(cause).__name__, 'message': str(cause),
                'sqlite_errorcode': getattr(cause, 'sqlite_errorcode', None)},
            'before': before, 'after': context.budget.to_dict()}
    progress = context.activity.progress('child-returned')
    return {'child': child, 'before': before, 'after': context.budget.to_dict(), 'progress': progress}


for handler in (parent_handler, child_handler, failing_child):
    handler.__execution_kernel_revision__ = 'observability-runtime-integration-v1'


class RuntimeObservationIntegrationTests(unittest.TestCase):
    @staticmethod
    def _database_evidence(root):
        """Read retained facts after native cleanup, outside the business window."""
        databases = {}
        for path in root.glob('*.sqlite3'):
            tables = {}
            try:
                with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.1) as connection:
                    connection.row_factory = sqlite3.Row
                    names = connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'").fetchall()
                    for name in names:
                        quoted = name['name'].replace('"', '""')
                        rows = connection.execute(f'SELECT * FROM "{quoted}" LIMIT 101').fetchall()
                        tables[name['name']] = {'rows': [
                            {key: {'bytes_hex': value.hex()} if isinstance(value, bytes) else value
                             for key, value in dict(row).items()} for row in rows[:100]],
                            'truncated': len(rows) > 100}
                databases[path.name] = tables
            except Exception as error:
                databases[path.name] = {'error_type': type(error).__name__, 'error': str(error)}
        return databases

    def execute(self, mode, *, fail=False):
        root = retained_directory('sdk-runtime-child-publication-')
        path = root / 'kernel.sqlite3'
        evidence_path = root / 'evidence.json'
        evidence = {'mode': mode, 'failed_child': fail, 'interpreter': sys.executable,
            'sdk_module': dispatcher_sdk.__file__, 'kernel_path': str(path),
            'original_parent_seconds': PARENT_SECONDS, 'original_child_call_seconds': CHILD_CALL_SECONDS,
            'raw_child_exception_path': str(root / 'parent-child-error.json')}
        before = None
        try:
            with Kernel.open_sqlite(path, {'parent': parent_handler, 'child': child_handler,
                    'failing': failing_child}, isolation_mode=mode,
                    max_thread_workers=1, child_capacity=1) as runtime:
                runtime.submit(runtime.command('parent', execution_id='parent', idempotency_key='parent',
                    correlation_id='root', timeout_seconds=PARENT_SECONDS,
                    payload={'handler': 'failing' if fail else 'child',
                        '_child_diagnostic_path': str(root / 'parent-child-error.json')}))
                before = time.monotonic()
                result = runtime.run_once()
                evidence['result'] = result.to_dict()
                evidence['returned_after_seconds'] = time.monotonic() - before
                evidence_path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
                self.assertEqual(result.state, 'succeeded', result.result.to_dict())
                self.assertLess(time.monotonic() - before, PARENT_SECONDS)
                # Business result delivery and durable wait publication are
                # separate. Allow SDK maintenance to finish within this same
                # original caller bound; never rerun the handler.
                observation = runtime.observation_journal.inspect('parent', timeout=.1)
                first_observation = observation
                evidence['first_observation'] = first_observation
                end = before + PARENT_SECONDS
                while not observation.get('child_waits') or any(
                        wait['state'] == 'open' for wait in observation['child_waits']):
                    remaining = end - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(.01, remaining))
                    remaining = end - time.monotonic()
                    if remaining <= 0:
                        break
                    observation = runtime.observation_journal.inspect('parent', timeout=min(.1, remaining))
                evidence['final_observation'] = observation
                evidence['caller_elapsed'] = time.monotonic() - before
                evidence_path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
                self.assertEqual(observation['identity']['execution_id'], 'parent')
                self.assertTrue(observation['child_waits'])
                self.assertTrue(all(wait['state'] != 'open' for wait in observation['child_waits']))
                value = result.result.value
                if fail:
                    self.assertEqual(value['code'], 'provider_denied')
                    self.assertEqual(value['child_error']['error']['details']['provider'], 'fixture')
                    self.assertEqual(value['child_error']['causation_id'], 'parent')
                else:
                    self.assertIn('child', value, json.dumps(value, indent=2))
                    self.assertEqual(value['child']['value']['value'], 9)
                    self.assertEqual(value['progress']['state'], 'confirmed')
                    self.assertLessEqual(value['after']['remaining_work_seconds'],
                                         value['before']['remaining_work_seconds'])
                    child_id = value['child']['execution_id']
                    child_obs = runtime.observation_journal.inspect(child_id)
                    evidence['child_observation'] = child_obs
                    self.assertEqual(child_obs['metrics']['stdout_bytes']['count'], 20)
                    self.assertEqual(runtime.kernel.get_execution_limits(child_id)['parent_execution_id'], 'parent')
        except BaseException as error:
            evidence['raised'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            evidence['cleanup_completed_at'] = time.time()
            evidence['databases'] = self._database_evidence(root)
            evidence_path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print('runtime_child_publication_evidence=' + str(evidence_path), flush=True)

    def test_single_parent_thread_slot_has_independent_bounded_child_capacity(self):
        self.execute('thread')

    def test_process_parent_calls_real_process_child_and_observes_raw_bytes(self):
        self.execute('process')

    def test_child_failure_reaches_parent_without_losing_causal_result(self):
        self.execute('thread', fail=True)


if __name__ == '__main__':
    unittest.main()
