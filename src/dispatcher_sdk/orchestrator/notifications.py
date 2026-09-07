"""Durable application wakeups, independent of the Kernel result outbox.

Watches bind to one application attempt. Kernel events retain short-lived
recovery transitions even if recovery finishes before this consumer runs.
Delivery is at least once: applications deduplicate by notification_id.
"""
from __future__ import annotations

import json
import math
import uuid

from ..execution_kernel import StaleFenceError
from .contracts import CommandConflict, OrchestrationError, TERMINAL, canonical, digest
from .results import _identity, _integer, _positive
from .store import execute_schema


class NotificationsMixin:
    @staticmethod
    def _init_notifications(connection):
        execute_schema(connection, """
            CREATE TABLE IF NOT EXISTS sdk_watches (
                run_id TEXT NOT NULL, watch_id TEXT NOT NULL, task_id TEXT NOT NULL,
                execution_id TEXT NOT NULL, attempt INTEGER NOT NULL, target TEXT NOT NULL,
                max_deliveries INTEGER NOT NULL, cursor INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(run_id,watch_id));
            CREATE TABLE IF NOT EXISTS sdk_notifications (
                notification_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL, lease_id TEXT, fence INTEGER NOT NULL DEFAULT 0,
                owner TEXT, expires_at REAL, next_attempt_at REAL NOT NULL,
                last_error TEXT, revision INTEGER NOT NULL DEFAULT 1);
            CREATE INDEX IF NOT EXISTS sdk_notifications_pending
                ON sdk_notifications(state,next_attempt_at);
        """)

    @staticmethod
    def _register_watch(connection, state, op):
        if state['state'] != 'running':
            raise OrchestrationError('run is terminal')
        task = state['tasks'].get(op['task_id'])
        if task is None:
            raise OrchestrationError('unknown task')
        maximum = _integer(op.get('max_deliveries', 5), 'max_deliveries')
        target = canonical(op['target'])
        if op['target'] is None:
            raise OrchestrationError('target must identify an application conversation')
        if connection.execute('SELECT 1 FROM sdk_watches WHERE run_id=? AND watch_id=?',
                              (state['run_id'], op['watch_id'])).fetchone():
            raise CommandConflict('watch already exists; replay the original command')
        connection.execute(
            'INSERT INTO sdk_watches(run_id,watch_id,task_id,execution_id,attempt,target,max_deliveries) '
            'VALUES(?,?,?,?,?,?,?)',
            (state['run_id'], op['watch_id'], op['task_id'],
             task['attempts'][-1]['command']['execution_id'], len(task['attempts']) - 1,
             target, maximum))

    def collect_notifications(self, *, limit=100):
        """Read at most limit Kernel events per open watch; atomically queue/cursor.

        Registration replays the bound execution's history, including an already
        settled execution. A new application attempt needs a new watch_id.
        Kernel result deliveries are neither claimed nor acknowledged here.
        """
        _integer(limit, 'limit')
        connection = self._connect()
        try:
            watches = connection.execute('SELECT * FROM sdk_watches WHERE completed=0').fetchall()
        finally:
            connection.close()
        count = 0
        for watch in watches:
            events = self.kernel.events_since(watch['cursor'], limit)
            if any(event.execution_id == watch['execution_id'] for event in events):
                # The notice must not outrun its attempt's durable projection.
                # Read/sync after the event page so the projected snapshot is
                # at least as recent as the facts we are about to publish.
                self.sync_execution(watch['execution_id'])
            with self._results_transaction() as (connection, now):
                current = connection.execute(
                    'SELECT * FROM sdk_watches WHERE run_id=? AND watch_id=?',
                    (watch['run_id'], watch['watch_id'])).fetchone()
                if current['completed'] or current['cursor'] != watch['cursor']:
                    continue
                state = self._load(connection, watch['run_id'])
                attempt = state['tasks'][watch['task_id']]['attempts'][watch['attempt']]
                completed = False
                for event in events:
                    if event.execution_id != watch['execution_id'] or not attempt['dispatched']:
                        continue
                    terminal = event.to_state in TERMINAL
                    recovery = (event.to_state == 'recovery_required'
                                and event.from_state != 'recovery_required')
                    if not terminal and not recovery:
                        continue
                    payload = {
                        'notification_id': digest([watch['run_id'], watch['watch_id'], event.event_id]),
                        'run_id': watch['run_id'], 'task_id': watch['task_id'],
                        'attempt': watch['attempt'], 'execution_id': event.execution_id,
                        'watch_id': watch['watch_id'], 'target': json.loads(watch['target']),
                        'kind': 'terminal' if terminal else 'recovery_required',
                        'state': event.to_state, 'event': event.to_dict(),
                        'result': event.data.get('result') if terminal else None,
                    }
                    count += self._queue_notification(connection, watch, payload, now)
                    if terminal:
                        completed = True
                        break
                # A planned cancellation has no Kernel execution/result to forge.
                if not attempt['dispatched'] and attempt['state'] == 'cancelled':
                    payload = {
                        'notification_id': digest([watch['run_id'], watch['watch_id'], 'planned_cancel']),
                        'run_id': watch['run_id'], 'task_id': watch['task_id'],
                        'attempt': watch['attempt'], 'execution_id': watch['execution_id'],
                        'watch_id': watch['watch_id'], 'target': json.loads(watch['target']),
                        'kind': 'terminal', 'state': 'cancelled', 'event': None, 'result': None,
                        'reason': attempt['cancel_reason'],
                    }
                    count += self._queue_notification(connection, watch, payload, now)
                    completed = True
                connection.execute(
                    'UPDATE sdk_watches SET cursor=?,completed=? WHERE run_id=? AND watch_id=?',
                    (events[-1].sequence if events else watch['cursor'], int(completed),
                     watch['run_id'], watch['watch_id']))
                self._failpoint('before_notification_commit')
        return count

    @staticmethod
    def _queue_notification(connection, watch, payload, now):
        return connection.execute(
            'INSERT OR IGNORE INTO sdk_notifications(notification_id,payload,max_attempts,next_attempt_at) '
            'VALUES(?,?,?,?)', (payload['notification_id'], canonical(payload), watch['max_deliveries'], now)
        ).rowcount

    @staticmethod
    def _notification_record(row):
        value = dict(row)
        value['payload'] = json.loads(value['payload'])
        value['last_error'] = json.loads(value['last_error']) if value['last_error'] else None
        return value

    def load_notification(self, notification_id):
        _identity(notification_id, 'notification_id')
        connection = self._connect()
        try:
            row = connection.execute('SELECT * FROM sdk_notifications WHERE notification_id=?',
                                     (notification_id,)).fetchone()
            if row is None:
                raise KeyError(notification_id)
            return self._notification_record(row)
        finally:
            connection.close()

    def list_notifications(self, *, state=None, limit=100):
        _integer(limit, 'limit')
        if state not in (None, 'pending', 'delivering', 'delivered', 'dead'):
            raise ValueError('invalid notification state')
        connection = self._connect()
        try:
            rows = connection.execute(
                'SELECT * FROM sdk_notifications WHERE (? IS NULL OR state=?) ORDER BY rowid LIMIT ?',
                (state, state, limit)).fetchall()
            return tuple(self._notification_record(row) for row in rows)
        finally:
            connection.close()

    def claim_notifications(self, *, owner, lease_seconds=30, limit=1):
        _identity(owner, 'owner')
        duration = _positive(lease_seconds, 'lease_seconds')
        _integer(limit, 'limit')
        with self._results_transaction() as (connection, now):
            if not math.isfinite(now + duration):
                raise ValueError('lease expiry must be finite')
            connection.execute(
                "UPDATE sdk_notifications SET state=CASE WHEN attempts>=max_attempts THEN 'dead' ELSE 'pending' END, "
                'expires_at=NULL,next_attempt_at=?,last_error=?,revision=revision+1 '
                "WHERE state='delivering' AND expires_at<=?",
                (now, canonical({'type': 'LeaseExpired', 'message': 'notification delivery lease expired'}), now))
            rows = connection.execute(
                "SELECT * FROM sdk_notifications WHERE state='pending' AND next_attempt_at<=? "
                'ORDER BY rowid LIMIT ?', (now, limit)).fetchall()
            claims = []
            for row in rows:
                connection.execute(
                    "UPDATE sdk_notifications SET state='delivering',attempts=attempts+1,lease_id=?,"
                    'fence=fence+1,owner=?,expires_at=?,revision=revision+1 WHERE notification_id=?',
                    (uuid.uuid4().hex, owner, now + duration, row['notification_id']))
                claims.append(self._notification_record(connection.execute(
                    'SELECT * FROM sdk_notifications WHERE notification_id=?',
                    (row['notification_id'],)).fetchone()))
            return tuple(claims)

    def _settle_notification(self, notification_id, lease_id, fence, *, error=None, retry_delay=1):
        _identity(notification_id, 'notification_id')
        _identity(lease_id, 'lease_id')
        _integer(fence, 'fence')
        delay = _positive(retry_delay, 'retry_delay')
        with self._results_transaction() as (connection, now):
            row = connection.execute('SELECT * FROM sdk_notifications WHERE notification_id=?',
                                     (notification_id,)).fetchone()
            if row is None:
                raise KeyError(notification_id)
            same = row['lease_id'] == lease_id and row['fence'] == fence
            if same and row['state'] == 'delivered' and error is None:
                return self._notification_record(row)
            if not same or row['state'] != 'delivering' or row['expires_at'] <= now:
                raise StaleFenceError('notification lease is stale')
            if not math.isfinite(now + delay):
                raise ValueError('retry time must be finite')
            state = ('delivered' if error is None else
                     'dead' if row['attempts'] >= row['max_attempts'] else 'pending')
            connection.execute(
                'UPDATE sdk_notifications SET state=?,expires_at=NULL,next_attempt_at=?,last_error=?, '
                'revision=revision+1 WHERE notification_id=?',
                (state, now + delay, canonical(error) if error is not None else None, notification_id))
            return self._notification_record(connection.execute(
                'SELECT * FROM sdk_notifications WHERE notification_id=?', (notification_id,)).fetchone())

    def acknowledge_notification(self, notification_id, *, lease_id, fence):
        return self._settle_notification(notification_id, lease_id, fence)

    def fail_notification(self, notification_id, *, lease_id, fence, error, retry_delay=1):
        if type(error) is not dict:
            raise ValueError('error must be a JSON object')
        return self._settle_notification(notification_id, lease_id, fence,
                                         error=error, retry_delay=retry_delay)

    def retry_notification(self, notification_id, *, expected_revision):
        _identity(notification_id, 'notification_id')
        _integer(expected_revision, 'expected_revision')
        with self._results_transaction() as (connection, now):
            row = connection.execute('SELECT * FROM sdk_notifications WHERE notification_id=?',
                                     (notification_id,)).fetchone()
            if row is None:
                raise KeyError(notification_id)
            if row['revision'] != expected_revision:
                raise StaleFenceError('notification retry revision is stale')
            if row['state'] != 'dead':
                raise ValueError('only dead notifications can be retried')
            connection.execute(
                "UPDATE sdk_notifications SET state='pending',attempts=0,lease_id=NULL,owner=NULL,"
                'expires_at=NULL,next_attempt_at=?,last_error=NULL,revision=revision+1 WHERE notification_id=?',
                (now, notification_id))
            return self._notification_record(connection.execute(
                'SELECT * FROM sdk_notifications WHERE notification_id=?', (notification_id,)).fetchone())

    def deliver_notifications(self, callback, *, owner, lease_seconds=30, retry_delay=1, limit=1):
        """Invoke a synchronous application enqueue callback outside transactions.

        Return normally only after the application durably accepts the wakeup.
        Keep callbacks short; lease expiry/crashes can redeliver the same ID.
        """
        if not callable(callback):
            raise TypeError('callback must be callable')
        _integer(limit, 'limit')
        _positive(retry_delay, 'retry_delay')
        delivered = 0
        for _ in range(limit):
            claims = self.claim_notifications(owner=owner, lease_seconds=lease_seconds, limit=1)
            if not claims:
                break
            claim = claims[0]
            try:
                returned = callback(claim['payload'])
                # Avoid acknowledging an unawaited async function as success.
                import inspect
                if inspect.isawaitable(returned):
                    if inspect.iscoroutine(returned):
                        returned.close()
                    raise TypeError('notification callback must be synchronous')
            except Exception as exc:
                try:
                    self.fail_notification(claim['notification_id'], lease_id=claim['lease_id'],
                                           fence=claim['fence'], retry_delay=retry_delay,
                                           error={'type': type(exc).__name__, 'message': str(exc)})
                except StaleFenceError:
                    pass
            else:
                self._failpoint('after_notification_callback')
                try:
                    self.acknowledge_notification(claim['notification_id'],
                                                 lease_id=claim['lease_id'], fence=claim['fence'])
                    delivered += 1
                except StaleFenceError:
                    pass
        return delivered
