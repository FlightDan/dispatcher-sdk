from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from dispatcher_sdk.execution_kernel import (
    ExecutionCommandV2, Kernel, RetryPolicy, HandlerExecutionError, StaleFenceError)
from dispatcher_sdk.orchestrator import Orchestrator, OrchestrationError


def echo(payload, context):
    if payload.get('retry') and context.lease.attempt == 1:
        raise HandlerExecutionError('temporary', 'retry me', retryable=True)
    return payload


echo.__execution_kernel_revision__ = "notification-test-v1"

class NotificationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.db'
        self.now = 100.
        self.runtime = Kernel.open_sqlite(self.path, {'echo': echo}, isolation_mode='thread',
                                         now=lambda: self.now)
        self.addCleanup(self.runtime.close)
        self.sdk = self.reopen()
        self.sdk.create_run('run', command_id='create')

    def reopen(self):
        return Orchestrator(self.path, self.runtime.kernel, runtime=self.runtime, clock=lambda: self.now)

    def apply(self, *ops):
        state = self.sdk.get_run('run')
        return self.sdk.apply_operations('run', command_id=f"op-{state['revision']}",
                                         expected_revision=state['revision'], operations=list(ops))

    def add(self, *, maximum=5, retry=False, dispatch=True):
        command = ExecutionCommandV2(
            execution_id='exec', idempotency_key='exec', registry_revision=self.runtime.registry_revision,
            correlation_id='run', causation_id=None, handler_id='echo', handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0) if retry else RetryPolicy(),
            timeout_seconds=10, payload={'retry': retry})
        ops = [dict(kind='add_task', task_id='task', command=command.to_dict()),
               dict(kind='watch_task', task_id='task', watch_id='wake', target={'conversation_id': 'chat'},
                    max_deliveries=maximum)]
        if dispatch:
            ops.append(dict(kind='dispatch', task_id='task'))
        self.apply(*ops)
        self.sdk.flush()

    def finish(self, **kwargs):
        self.add(**kwargs)
        self.runtime.run_once()
        self.sdk.collect_notifications()
        return self.sdk.list_notifications()[0]

    def test_atomic_registration_rollback(self):
        self.add(dispatch=False)
        before = self.sdk.get_run('run')
        with self.assertRaises(OrchestrationError):
            self.apply(dict(kind='watch_task', task_id='task', watch_id='rollback', target='chat'),
                       dict(kind='dispatch', task_id='missing'))
        self.assertEqual(before, self.sdk.get_run('run'))
        self.apply(dict(kind='dispatch', task_id='task'))
        self.sdk.flush()
        self.runtime.run_once()
        self.sdk.collect_notifications()
        self.assertEqual(len(self.sdk.list_notifications()), 1)

    def test_terminal_replay_independent_from_result_queue(self):
        record = self.finish()
        self.assertEqual(record['payload']['result']['status'], 'succeeded')
        self.assertEqual(record['payload']['target']['conversation_id'], 'chat')
        self.assertEqual(self.sdk.kernel_result_outbox_status().pending, 1)
        sdk = self.reopen()
        self.assertEqual(sdk.collect_notifications(), 0)
        self.assertEqual(sdk.list_notifications()[0], record)
        # Callback may make an application decision without a held SQLite lock.
        seen = []
        def callback(payload):
            seen.append(payload)
            self.apply(dict(kind='signal', signal_id='woken', payload=payload['notification_id']))
        self.assertEqual(sdk.deliver_notifications(callback, owner='app'), 1)
        self.assertEqual(sdk.deliver_notifications(callback, owner='app'), 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(sdk.kernel_result_outbox_status().pending, 1)

    def test_callback_crash_restart_stable_id_and_stale_ack(self):
        record = self.finish()
        seen = []
        def crash(name):
            if name == 'after_notification_callback':
                raise RuntimeError('process died after app enqueue')
        self.sdk._failpoint = crash
        with self.assertRaises(RuntimeError):
            self.sdk.deliver_notifications(seen.append, owner='one', lease_seconds=1)
        old = self.sdk.load_notification(record['notification_id'])
        self.now += 2
        sdk = self.reopen()
        self.assertEqual(sdk.deliver_notifications(seen.append, owner='two'), 1)
        self.assertEqual(seen[0]['notification_id'], seen[1]['notification_id'])
        with self.assertRaises(StaleFenceError):
            sdk.acknowledge_notification(record['notification_id'], lease_id=old['lease_id'], fence=old['fence'])

    def test_callback_failure_dead_letter_and_explicit_retry(self):
        record = self.finish(maximum=1)
        def fail(payload):
            raise RuntimeError('application offline')
        self.assertEqual(self.sdk.deliver_notifications(fail, owner='app'), 0)
        dead = self.sdk.load_notification(record['notification_id'])
        self.assertEqual(dead['state'], 'dead')
        self.assertEqual(dead['last_error']['message'], 'application offline')
        self.sdk.retry_notification(dead['notification_id'], expected_revision=dead['revision'])
        self.assertEqual(self.sdk.deliver_notifications(lambda payload: None, owner='app'), 1)

    def test_concurrent_consumers_claim_once(self):
        self.finish()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda owner: self.reopen().claim_notifications(owner=owner), ['a', 'b']))
        self.assertEqual(sum(map(len, results)), 1)

    def test_retry_does_not_wake(self):
        self.add(retry=True)
        self.runtime.run_once()
        self.assertEqual(self.runtime.kernel.get('exec').state, 'queued')
        self.assertEqual(self.sdk.collect_notifications(), 0)
        self.runtime.run_once()
        self.assertEqual(self.sdk.collect_notifications(), 1)
        self.assertEqual(self.sdk.list_notifications()[0]['payload']['state'], 'succeeded')

    def test_recovery_transition_not_lost_after_resolution(self):
        self.add()
        kernel = self.runtime.kernel
        lease = kernel.start(kernel.claim('worker', lease_seconds=1,
                                           registry_revision=self.runtime.registry_revision))
        kernel.prepare_effect(lease, effect_id='uncertain', name='write', request={})
        self.now += 2
        kernel.reap()
        self.assertEqual(kernel.get('exec').state, 'recovery_required')
        effect = kernel.get_effect('uncertain')
        kernel.resolve_effect('uncertain', decision='not_applied', response=None,
                              expected_revision=effect.revision, recovery_id='resolved')
        self.runtime.run_once()
        self.assertEqual(kernel.get('exec').state, 'succeeded')
        self.assertEqual(self.sdk.collect_notifications(), 2)
        self.assertEqual([r['payload']['kind'] for r in self.sdk.list_notifications()],
                         ['recovery_required', 'terminal'])

    def test_completion_between_sync_and_collection_is_visible_to_callback(self):
        self.add()
        self.sdk.sync()
        self.assertEqual(self.sdk.get_task('run', 'task')['latest_attempt']['state'], 'queued')
        # The host's previous sync cannot have seen this completion.
        self.runtime.run_once()
        self.assertEqual(self.sdk.collect_notifications(), 1)
        observed = []
        def callback(payload):
            attempt = self.sdk.get_task('run', 'task')['latest_attempt']
            observed.append((payload['state'], attempt['state'], attempt['result']))
        self.assertEqual(self.sdk.deliver_notifications(callback, owner='reader'), 1)
        self.assertEqual(observed[0][0:2], ('succeeded', 'succeeded'))
        self.assertEqual(observed[0][2]['value'], {'retry': False})

    def test_old_watch_does_not_overwrite_newer_application_attempt(self):
        self.add()
        self.runtime.run_once()
        self.sdk.sync()
        command = self.sdk.get_run('run')['tasks']['task']['attempts'][0]['command'].copy()
        command.update(execution_id='exec-new', idempotency_key='exec-new')
        self.apply(dict(kind='new_attempt', task_id='task', command=command),
                   dict(kind='dispatch', task_id='task'))
        self.sdk.flush()
        self.sdk.sync()
        before = self.sdk.get_task('run', 'task')['latest_attempt']
        self.assertEqual(before['state'], 'queued')
        self.assertEqual(self.sdk.collect_notifications(), 1)
        self.assertEqual(self.sdk.list_notifications()[0]['payload']['execution_id'], 'exec')
        self.assertEqual(self.sdk.get_task('run', 'task')['latest_attempt'], before)

    def test_collection_crash_rolls_back_cursor_and_outbox(self):
        self.add()
        self.runtime.run_once()
        def crash(name):
            if name == 'before_notification_commit':
                raise RuntimeError('crash')
        self.sdk._failpoint = crash
        with self.assertRaises(RuntimeError):
            self.sdk.collect_notifications()
        self.assertEqual(self.sdk.list_notifications(), ())
        self.assertEqual(self.reopen().collect_notifications(), 1)

    def test_planned_cancel_and_late_watch(self):
        self.add(dispatch=False)
        self.apply(dict(kind='cancel', task_id='task', reason='app cancelled'))
        self.assertEqual(self.sdk.collect_notifications(), 1)
        payload = self.sdk.list_notifications()[0]['payload']
        self.assertEqual(payload['state'], 'cancelled')
        self.assertIsNone(payload['result'])
        self.apply(dict(kind='watch_task', task_id='task', watch_id='late', target='chat'))
        self.assertEqual(self.sdk.collect_notifications(), 1)

    def test_async_callback_not_silently_acknowledged(self):
        record = self.finish(maximum=1)
        async def async_callback(payload):
            pass
        self.sdk.deliver_notifications(async_callback, owner='app')
        self.assertEqual(self.sdk.load_notification(record['notification_id'])['state'], 'dead')


if __name__ == '__main__':
    unittest.main()
