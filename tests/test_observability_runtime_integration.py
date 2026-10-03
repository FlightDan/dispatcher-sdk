from pathlib import Path
import os
import tempfile
import time
import unittest

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.children import ChildExecutionError


def child_handler(payload, context):
    context.activity.report_bytes('stdout', b'raw-without-newline\xff')
    context.activity.progress('child-finished')
    return {'value': payload['value'], 'budget': context.budget.to_dict()}


def failing_child(payload, context):
    from dispatcher_sdk.execution_kernel import HandlerExecutionError
    raise HandlerExecutionError('provider_denied', 'original provider failure', details={'provider': 'fixture'})


def parent_handler(payload, context):
    before = context.budget.to_dict()
    try:
        child = context.children.run(payload.get('handler', 'child'), {'value': 9},
            request_id='one-child', timeout_seconds=2)
    except ChildExecutionError as exc:
        return {'child_error': exc.result, 'code': exc.code}
    progress = context.activity.progress('child-returned')
    return {'child': child, 'before': before, 'after': context.budget.to_dict(), 'progress': progress}


for handler in (parent_handler, child_handler, failing_child):
    handler.__execution_kernel_revision__ = 'observability-runtime-integration-v1'


class RuntimeObservationIntegrationTests(unittest.TestCase):
    def execute(self, mode, *, fail=False):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'kernel.sqlite3'
            with Kernel.open_sqlite(path, {'parent': parent_handler, 'child': child_handler,
                    'failing': failing_child}, isolation_mode=mode,
                    max_thread_workers=1, child_capacity=1) as runtime:
                runtime.submit(runtime.command('parent', execution_id='parent', idempotency_key='parent',
                    correlation_id='root', timeout_seconds=5,
                    payload={'handler': 'failing' if fail else 'child'}))
                before = time.monotonic()
                result = runtime.run_once()
                self.assertEqual(result.state, 'succeeded', result.result.to_dict())
                self.assertLess(time.monotonic() - before, 5)
                observation = runtime.observation_journal.inspect('parent')
                self.assertEqual(observation['identity']['execution_id'], 'parent')
                self.assertTrue(observation['child_waits'])
                self.assertTrue(all(wait['state'] != 'open' for wait in observation['child_waits']))
                value = result.result.value
                if fail:
                    self.assertEqual(value['code'], 'provider_denied')
                    self.assertEqual(value['child_error']['error']['details']['provider'], 'fixture')
                    self.assertEqual(value['child_error']['causation_id'], 'parent')
                else:
                    self.assertEqual(value['child']['value']['value'], 9)
                    self.assertEqual(value['progress']['state'], 'confirmed')
                    self.assertLessEqual(value['after']['remaining_work_seconds'],
                                         value['before']['remaining_work_seconds'])
                    child_id = value['child']['execution_id']
                    child_obs = runtime.observation_journal.inspect(child_id)
                    self.assertEqual(child_obs['metrics']['stdout_bytes']['count'], 20)
                    self.assertEqual(runtime.kernel.get_execution_limits(child_id)['parent_execution_id'], 'parent')

    def test_single_parent_thread_slot_has_independent_bounded_child_capacity(self):
        self.execute('thread')

    def test_process_parent_calls_real_process_child_and_observes_raw_bytes(self):
        self.execute('process')

    def test_child_failure_reaches_parent_without_losing_causal_result(self):
        self.execute('thread', fail=True)


if __name__ == '__main__':
    unittest.main()
