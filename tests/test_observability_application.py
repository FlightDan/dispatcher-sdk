"""Public facade delivery and bounded cancellation acceptance."""
from pathlib import Path
from contextlib import contextmanager
import json
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dispatcher_sdk import Dispatcher, ObservationOptions, StallPolicy
from dispatcher_sdk.observability import ActivityRecorder, ObservationIdentity
from dispatcher_sdk.execution_kernel import Kernel
from tests._acceptance_evidence import retained_directory


def quiet_handler(payload, context):
    deadline = time.monotonic() + payload['seconds']
    while time.monotonic() < deadline:
        context.activity.heartbeat()
        time.sleep(.01)
    return {'finished': True}


quiet_handler.__execution_kernel_revision__ = 'observability-public-acceptance-v1'


class ObservabilityApplicationTests(unittest.TestCase):
    @contextmanager
    def notification_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            dispatcher = Dispatcher(Path(temporary)/'application.sqlite3', {'quiet': quiet_handler},
                isolation_mode='thread', observation_options=ObservationOptions(page_events=1))
            try:
                task = dispatcher.submit('quiet', {'seconds': 0}, request_id='notification-fixture')
                target = {'run_id': task.snapshot['command']['correlation_id'], 'task_id': 'task'}
                yield dispatcher, target
            finally:
                dispatcher.close()

    def fixture_notice(self, notification_id, target):
        return {'kind': 'stalled', 'notification_id': notification_id, 'target': target,
            'max_deliveries': 2}

    def test_notification_page_continues_past_unrelated_terminal_notification(self):
        with self.notification_fixture() as (dispatcher, target):
            with dispatcher.orchestrator._transaction() as connection:
                connection.execute("INSERT INTO sdk_notifications(notification_id,payload,max_attempts,next_attempt_at) "
                    "VALUES('terminal-first',?,5,0)", (json.dumps({'kind': 'terminal', 'notification_id': 'terminal-first'}),))
            dispatcher.orchestrator.enqueue_stall_notification(self.fixture_notice('stall-second', target))
            first = dispatcher.stall_notification_page(limit=1)
            self.assertEqual(first['notifications'], ())
            self.assertTrue(first['has_more'])
            second = dispatcher.stall_notification_page(after=first['cursor'], limit=1)
            self.assertEqual([row['notification_id'] for row in second['notifications']], ['stall-second'])
            self.assertFalse(second['has_more'])

    def test_notification_state_filter_has_a_continuation_for_empty_pages(self):
        with self.notification_fixture() as (dispatcher, target):
            dispatcher.orchestrator.enqueue_stall_notification(self.fixture_notice('pending-first', target))
            dispatcher.orchestrator.enqueue_stall_notification(self.fixture_notice('dead-second', target))
            with dispatcher.orchestrator._transaction() as connection:
                connection.execute("UPDATE sdk_notifications SET state='dead',revision=9 WHERE notification_id='dead-second'")
            first = dispatcher.stall_notification_page(state='dead', limit=1)
            self.assertEqual(first['notifications'], ())
            self.assertTrue(first['has_more'])
            second = dispatcher.stall_notification_page(state='dead', after=first['cursor'], limit=1)
            self.assertEqual(second['notifications'][0]['notification_id'], 'dead-second')
            self.assertEqual(second['notifications'][0]['revision'], 9)
            retried = dispatcher.retry_stall_notification('dead-second', expected_revision=9)
            self.assertEqual((retried['notification_id'], retried['state'], retried['revision']),
                ('dead-second', 'pending', 10))

    def test_notification_latest_phase_ignores_downstream_page_position(self):
        with self.notification_fixture() as (dispatcher, target):
            first = self.fixture_notice('earlier-inbox', target)
            notice = self.fixture_notice('observation-owned', target)
            journal = dispatcher.runtime.observation_journal
            with journal._transaction() as (connection, now):
                connection.execute("INSERT INTO obs_outbox(notification_id,episode_id,payload,state,created_at,max_attempts,revision) "
                    "VALUES(?,?,?,'dead',?,2,7)", ('observation-owned', 'fixture-episode', json.dumps(notice), now))
            dispatcher.inbox.accept('dispatcher.stalls.v1', first)
            dispatcher.inbox.accept('dispatcher.stalls.v1', notice)
            with dispatcher.inbox._transaction() as (connection, clock):
                connection.execute("UPDATE notification_inbox_messages SET state='consumed',revision=12 "
                    "WHERE notification_id='observation-owned'")
            page = dispatcher.stall_notification_page(limit=1)
            row = page['notifications'][0]
            self.assertEqual(row['notification_id'], 'observation-owned')
            self.assertEqual((row['phase'], row['state'], row['revision']), ('inbox', 'consumed', 12))
            self.assertEqual(row['stages']['observation'], {'state': 'dead', 'revision': 7})
            self.assertTrue(row['consumed'])
            with self.assertRaisesRegex(ValueError, 'advanced'):
                dispatcher.retry_stall_notification(row['notification_id'], expected_revision=7, phase='observation')
            with self.assertRaisesRegex(ValueError, 'only dead'):
                dispatcher.retry_stall_notification(row['notification_id'], expected_revision=12)

    def test_notification_page_byte_and_time_limits_keep_a_usable_cursor(self):
        with self.notification_fixture() as (dispatcher, target):
            notice = self.fixture_notice('large-notice', target)
            notice['details'] = 'large'*4000
            dispatcher.orchestrator.enqueue_stall_notification(notice)
            dispatcher.runtime.observation_options = ObservationOptions(page_events=1, query_bytes=4096)
            page = dispatcher.stall_notification_page(limit=1)
            self.assertLessEqual(len(json.dumps(page, ensure_ascii=False).encode()), 4096)
            self.assertTrue(page['truncated'])
            self.assertEqual(page['notifications'][0]['notification_id'], 'large-notice')
            self.assertFalse(dispatcher.stall_notification_page(after=page['cursor'])['has_more'])
            started = time.monotonic()
            clock = [started]

            def advance_query_clock():
                # Some supported monotonic clocks have ticks longer than this
                # query budget. Observe expiry explicitly within the real API.
                clock[0] += .000002
                return clock[0]

            query_clock = SimpleNamespace(**{**vars(time), 'monotonic': advance_query_clock})
            with patch('dispatcher_sdk._inspection.time', query_clock):
                expired = dispatcher.stall_notification_page(timeout=.000001)
            self.assertTrue(expired['timed_out'])
            self.assertLess(time.monotonic()-started, .1)

    def test_oversized_notification_kind_is_unknown_without_losing_its_identity(self):
        with self.notification_fixture() as (dispatcher, target):
            notice = self.fixture_notice('oversized-stall', target)
            notice['details'] = 'x'*300000
            dispatcher.orchestrator.enqueue_stall_notification(notice)
            page = dispatcher.stall_notification_page(limit=1)
            self.assertFalse(page['complete'])
            self.assertTrue(page['truncated'])
            self.assertEqual(page['unknown_reason'], 'notification_kind_unknown')
            row = page['notifications'][0]
            self.assertEqual(row['notification_id'], 'oversized-stall')
            self.assertFalse(row['kind_known'])
            self.assertEqual(row['payload']['kind'], 'unknown')
            continued = dispatcher.stall_notification_page(after=page['cursor'])
            self.assertEqual(continued['notifications'], ())
            self.assertFalse(continued['has_more'])

    def test_control_snapshot_does_not_mix_execution_and_result_delivery_revisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'kernel.sqlite3'
            with Kernel.open_sqlite(path, {'quiet': quiet_handler}, isolation_mode='thread') as runtime:
                command = runtime.command('quiet', execution_id='snapshot', idempotency_key='snapshot',
                    correlation_id='test', payload={'seconds': .1}, timeout_seconds=30)
                runtime.submit(command)
                lease = runtime.kernel.claim_and_start('fixture-worker', lease_seconds=300,
                    registry_revision=command.registry_revision)
                identity = ObservationIdentity('snapshot', lease.attempt, lease.fence)
                runtime.observation_journal.bind_current(identity)
                recorder = ActivityRecorder(runtime.observation_journal, identity)
                recorder.heartbeat()
                recorder.flush()
                original_connect = sqlite3.connect

                class BarrierCursor:
                    def __init__(self, cursor):
                        self.cursor = cursor

                    def fetchone(self):
                        row = self.cursor.fetchone()
                        runtime.kernel.cancel('snapshot', expected_revision=lease.revision)
                        return row

                class BarrierConnection(sqlite3.Connection):
                    def execute(self, statement, *args):
                        cursor = super().execute(statement, *args)
                        if statement.startswith('SELECT state,attempt,fence,revision,started_at,'):
                            return BarrierCursor(cursor)
                        return cursor

                def connect(database, *args, **kwargs):
                    if str(database) == path.resolve().as_uri()+'?mode=ro':
                        kwargs['factory'] = BarrierConnection
                    return original_connect(database, *args, **kwargs)

                with patch('sqlite3.connect', connect):
                    before = runtime.observe('snapshot')
                self.assertEqual(before['execution']['state'], 'running')
                self.assertFalse(before['settlement']['result_recorded'])
                self.assertIsNone(before['settlement']['kernel_result_delivery'])
                after = runtime.observe('snapshot')
                self.assertEqual(after['execution']['state'], 'cancelled')
                self.assertTrue(after['settlement']['result_recorded'])
                self.assertEqual(after['settlement']['kernel_result_delivery']['state'], 'pending')

    def eventually(self, read, predicate, timeout=6):
        deadline = time.monotonic() + timeout
        while True:
            value = read()
            if predicate(value):
                return value
            if time.monotonic() >= deadline:
                self.fail(f'condition not reached: {value!r}')
            time.sleep(.02)

    def test_dead_bridge_is_visible_and_retried_through_public_dispatcher(self):
        root = retained_directory('sdk-dead-bridge-')
        import dispatcher_sdk
        evidence = {'test': self.id(), 'sdk_import': dispatcher_sdk.__file__, 'interpreter': sys.executable,
            'root': str(root), 'handler_seconds': 3, 'execution_timeout': 5,
            'dead_notification_wait': 6, 'samples': [], 'bridge_attempts': []}
        with Dispatcher(
                root/'application.sqlite3', {'quiet': quiet_handler},
                isolation_mode='thread', observation_options=ObservationOptions(flush_interval=.05, write_timeout=.2)) as dispatcher:
            received = []
            dispatcher.subscribe_stalls(received.append)

            def broken_bridge(payload):
                evidence['bridge_attempts'].append({'at': time.time(), 'payload': payload})
                raise RuntimeError('injected failure before durable inbox receipt')

            def capture(label):
                sample = {'label': label, 'at': time.time(), 'monotonic': time.monotonic()}
                for name, read in (
                        ('task', lambda: task.snapshot),
                        ('observation', lambda: task.observe(timeout=.5)),
                        ('windows', task.stall_windows),
                        ('notifications', lambda: dispatcher.stall_notification_page(timeout=.5)),
                        ('dispatcher_health', dispatcher.health),
                        ('supervisor_health', dispatcher.runtime._stall_supervisor.health)):
                    try:
                        sample[name] = read()
                    except Exception as error:
                        sample[name] = {'error_type': type(error).__name__, 'error': str(error)}
                evidence['samples'].append(sample)

            dispatcher.runtime.set_stall_notification_bridge(broken_bridge)
            task = dispatcher.submit('quiet', {'seconds': 3}, request_id='quiet-once', timeout_seconds=5)
            try:
                with self.assertRaises(TimeoutError):
                    task.wait(timeout=.001)
                evidence['watch_receipt'] = task.watch_stall(StallPolicy('public-progress', sample_interval=.1,
                    consecutive_windows=2, max_deliveries=1))
                dispatcher.start()
                dead = self.eventually(lambda: dispatcher.stall_notifications(state='dead'), bool)[0]
                evidence['dead_notification'] = dead
                capture('dead_before_assertions')
                self.assertEqual(dead['phase'], 'observation')
                self.assertFalse(dead['received'])
                self.assertFalse(dead['consumed'])
                self.assertNotIn('_sdk_subscription_identity', dead['payload']['target'])
                notification_id = dead['notification_id']
                dispatcher.runtime.set_stall_notification_bridge(dispatcher.orchestrator.enqueue_stall_notification)
                retry_deadline = time.monotonic()+2
                while True:
                    try:
                        evidence['retry_receipt'] = dispatcher.retry_stall_notification(
                            notification_id, expected_revision=dead['revision'])
                        break
                    except sqlite3.OperationalError as error:
                        if not any(word in str(error).lower() for word in ('locked', 'busy')):
                            raise
                        if time.monotonic() >= retry_deadline:
                            raise
                        time.sleep(.02)
                consumed = self.eventually(lambda: dispatcher.stall_notifications(),
                    lambda rows: any(row['consumed'] for row in rows))[0]
                evidence['consumed_notification'] = consumed
                capture('consumed_before_assertions')
                self.assertEqual(consumed['notification_id'], notification_id)
                self.assertEqual(consumed['phase'], 'inbox')
                self.assertEqual(set(consumed['stages']), {'observation', 'orchestration', 'inbox'})
                self.assertEqual(len(received), 1)
                self.assertEqual(received[0]['notification_id'], notification_id)
                windows = task.stall_windows()
                self.assertTrue(any(window['state'] == 'stalled' for window in windows['windows']))
                observed = task.observe()
                self.assertEqual(observed['identity']['task_id'], 'task')
                self.assertIn('budget', observed)
                evidence['caller_result'] = task.wait(timeout=5)
                self.assertEqual(evidence['caller_result']['status'], 'succeeded')
            except BaseException as error:
                evidence['error'] = {'type': type(error).__name__, 'message': str(error),
                    'traceback': traceback.format_exc()}
                raise
            finally:
                capture('final_before_close')
                evidence['received'] = received
                path = root/'evidence.json'
                path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
                print('dead_bridge_evidence=' + str(path), flush=True)

    def test_busy_kernel_cancellation_has_a_bounded_uncommitted_error(self):
        from tests._storage_evidence import StorageEvidence

        root = retained_directory('sdk-busy-kernel-cancellation-')
        evidence = StorageEvidence(root, self)
        evidence.start(include_kernel=True)
        self.addCleanup(evidence.stop)
        self.addCleanup(evidence.save)
        runtime = None
        elapsed, raw_error = None, None
        try:
            path = root/'kernel.sqlite3'
            runtime = Kernel.open_sqlite(path, {'quiet': quiet_handler}, isolation_mode='thread')
            command = runtime.command('quiet', execution_id='queued', idempotency_key='queued',
                correlation_id='test', payload={'seconds': .1}, timeout_seconds=1)
            queued = runtime.submit(command)
            blocker = sqlite3.connect(path)
            try:
                blocker.execute('BEGIN IMMEDIATE')
                started = time.monotonic()
                with self.assertRaises(sqlite3.OperationalError):
                    try:
                        runtime.cancel('queued', expected_revision=queued.revision, timeout_seconds=.2)
                    except BaseException as error:
                        elapsed = time.monotonic()-started
                        raw_error = {'type': type(error).__name__, 'message': str(error),
                            'sqlite_errorcode': getattr(error, 'sqlite_errorcode', None),
                            'sqlite_errorname': getattr(error, 'sqlite_errorname', None),
                            'traceback': traceback.format_exc()}
                        raise
                evidence.save(phase='cancel-return', checkpoint={'elapsed': elapsed, 'timeout_seconds': .2,
                    'elapsed_bound': .6, 'raw_error': raw_error, 'queued_revision': queued.revision,
                    'kernel_in_transaction': runtime.kernel._connection.in_transaction})
                self.assertLess(elapsed, .6)
            finally:
                try:
                    blocker.rollback()
                finally:
                    blocker.close()
            unchanged = runtime.kernel.get('queued')
            self.assertEqual((unchanged.state, unchanged.revision), ('queued', queued.revision))
            runtime.cancel('queued', expected_revision=queued.revision)
            cancelled = runtime.kernel.get('queued')
            self.assertEqual(cancelled.state, 'cancelled')
            evidence.save(phase='cancel-confirmed', checkpoint={'uncommitted_state': unchanged.state,
                'uncommitted_revision': unchanged.revision, 'cancelled_state': cancelled.state,
                'cancelled_revision': cancelled.revision})
        except BaseException as error:
            evidence.save(phase='failure', checkpoint={'elapsed': elapsed, 'raw_cancellation_error': raw_error,
                'raw_test_error': {'type': type(error).__name__, 'message': str(error),
                    'traceback': traceback.format_exc()}})
            raise
        finally:
            if runtime is not None:
                runtime.close()

    def test_thread_wall_forward_exhaustion_does_not_commit_success(self):
        class Clock:
            value = time.time()
            def __call__(self):
                return self.value
        clock = Clock()

        def advance_wall(payload, context):
            clock.value += 3
            return {'remaining': context.budget.remaining_work_seconds}

        advance_wall.__execution_kernel_revision__ = 'wall-forward-v1'
        with tempfile.TemporaryDirectory() as temporary:
            with Kernel.open_sqlite(Path(temporary)/'kernel.sqlite3', {'advance': advance_wall},
                        isolation_mode='thread', now=clock) as runtime:
                command = runtime.command('advance', execution_id='advance', idempotency_key='advance',
                    correlation_id='test', payload={}, timeout_seconds=2)
                runtime.submit(command)
                result = runtime.run_once()
                self.assertEqual(result.result.status, 'timed_out')
                self.assertEqual(result.result.error.code, 'handler_timeout')


if __name__ == '__main__':
    unittest.main()
