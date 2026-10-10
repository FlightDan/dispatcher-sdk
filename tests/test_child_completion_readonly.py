"""Completed child delivery observes parent authority without a writer grant."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace
from tests._acceptance_evidence import retained_directory
import unittest
from unittest.mock import patch

from dispatcher_sdk._inspection import InspectionBudgetExceeded
from dispatcher_sdk._sqlite_errors import is_sqlite_contention
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope
from dispatcher_sdk.execution_kernel import child_factual_read as factual
from dispatcher_sdk.execution_kernel.children import ChildExecutionError, HandlerChildren, _RetryWindow, _retry
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, ExecutionResultV2, RetryPolicy
from dispatcher_sdk.execution_kernel.errors import StaleFenceError, StorageIsolationError
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.observability import ObservationJournal


class ChildCompletionReadonlyTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-child-completion-readonly-')
        self.wall = [time.time()]
        self.kernel = SQLiteKernel(self.root/'kernel.sqlite3', now=lambda: self.wall[0])
        self.addCleanup(self.kernel.close)
        self.command = ExecutionCommandV2('parent', 'parent', 'readonly-proof', 'root', None,
            'parent', 1, RetryPolicy(), 5, {})
        self.kernel.submit(self.command)
        self.lease = self.kernel.claim_and_start('owner', execution_id='parent')
        budget = self.kernel.prepare_execution_budget(self.lease).enter_handler(
            5, origin_id='execution:parent')
        self.budget = self.kernel.confirm_handler_entry(self.lease, budget)
        journal = ObservationJournal(self.root/'observations.sqlite3',
            kernel_path=self.kernel.db_path, source_id='readonly-host')
        self.children = HandlerChildren(self.kernel, self.command, self.lease, self.budget,
            {'capacity': 1, 'max_depth': 1}, journal=journal)
        self.evidence = {'test': self.id(), 'python': sys.executable,
            'kernel_path': self.kernel.db_path, 'records': []}

    def tearDown(self):
        path = self.root/'evidence.json'
        path.write_text(json.dumps(self.evidence, indent=2), encoding='utf-8')
        print('child_completion_readonly_evidence=' + str(path), flush=True)

    def completed_child(self, *, failure=None):
        envelope = self.budget.derive(source='tool', origin_id='original-child-call', timeout_seconds=.5)
        command = replace(self.command, execution_id='child', idempotency_key='child',
            causation_id=self.command.execution_id)
        self.kernel.submit_child(command, self.lease, envelope)
        # Retry only transient admission within this original child-call window,
        # preserving ownership of a captured clock fact until its ACK commits.
        window = _RetryWindow(envelope, self.kernel)
        original_deadline = window.deadline
        lease = _retry(window, lambda: self.kernel.claim_and_start(
            'child-owner', execution_id='child', child_pool=True,
            timeout_seconds=window.timeout()), kernel=None)
        self.assertIsNotNone(lease)
        self.assertEqual(lease.attempt, 1)
        self.assertLessEqual(window.deadline, original_deadline)
        snapshot = self.kernel.get('child')
        # Guard ACKs promote elapsed floors into the durable logical clock;
        # a frozen raw wall sample can precede this actual claimed snapshot.
        completed_at = self.kernel.current_time()
        record = {'scenario': 'original_child_setup', 'frozen_wall': self.wall[0],
            'claimed_snapshot': snapshot.to_dict(), 'logical_completed_at': completed_at,
            'completion_clock_source': 'SQLiteKernel.current_time',
            'original_budget': envelope.to_dict(),
            'original_native_deadline': original_deadline,
            'retained_native_deadline': window.deadline}
        self.evidence['records'].append(record)
        result = ExecutionResultV2('original-child-result', 'child', 'succeeded' if failure is None else 'failed',
            lease.attempt, lease.fence, [], snapshot.started_at, completed_at,
            'root', self.command.execution_id, {'original': 42} if failure is None else None, failure)
        record['original_result'] = result.to_dict()
        self.kernel.complete(lease, result)
        row = {'budget_json': json.dumps(envelope.to_dict()), 'parent_execution_id': self.command.execution_id,
            'parent_attempt': self.lease.attempt, 'parent_fence': self.lease.fence,
            'child_execution_id': 'child', 'action': 'run'}
        return row, window, result

    def watermark(self):
        return self.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()[0]

    def unstarted_child(self):
        envelope = self.budget.derive(source='tool', origin_id='original-unstarted-child', timeout_seconds=.5)
        command = replace(self.command, execution_id='unstarted-child', idempotency_key='unstarted-child',
            causation_id=self.command.execution_id)
        snapshot = self.kernel.submit_child(command, self.lease, envelope)
        window = _RetryWindow(envelope, self.kernel, execution_id=self.command.execution_id)
        row = self.children._enqueue(request_id='unstarted-response', child_id=command.execution_id,
            action='run', child_command=command, envelope=window.envelope, window=window)
        self.assertEqual((snapshot.state, snapshot.attempt, snapshot.fence), ('queued', 0, 0))
        self.assertIsNone(snapshot.lease)
        self.assertIsNone(snapshot.result)
        return row, window, snapshot

    def unstarted_child_preserves_original_refusal(self, *, cancelled):
        row, window, snapshot = self.unstarted_child()
        if cancelled:
            snapshot = self.kernel.cancel(snapshot.execution_id, expected_revision=snapshot.revision,
                reason='cancel before first claim', timeout_seconds=.1)
        original_deadline = window.deadline
        original_constraints = window.envelope.constraints
        canonical_before = self.kernel.get_execution_limits(snapshot.execution_id)['envelope']
        watermark_before = self.watermark()
        writer = sqlite3.connect(self.kernel.db_path, timeout=.1)
        errors, reader_statements, proof_deadlines = [], [], []
        attach, await_window = self.children.store.attach, self.children._await_window
        connect, completed = factual._connect_readonly, factual.read_completed_result
        record = {'scenario': 'unstarted_cancelled' if cancelled else 'unstarted_queued',
            'original_work_seconds': .5, 'original_proof_seconds': .1,
            'original_native_deadline': original_deadline, 'child': snapshot.to_dict(),
            'original_budget': window.envelope.to_dict(), 'factual_module': factual.__file__}
        self.evidence['records'].append(record)

        def attach_and_hold(*args):
            attach(*args)
            writer.execute('BEGIN IMMEDIATE')
            record['writer_acquired'] = time.monotonic()

        def retain_original_refusal(*args):
            try:
                return await_window(*args)
            except Exception as error:
                errors.append(error)
                record['original_refusal'] = {'type': type(error).__name__, 'message': str(error),
                    'code': getattr(error, 'code', None), 'sqlite_errorcode': getattr(error, 'sqlite_errorcode', None)}
                record['original_refusal_at'] = time.monotonic()
                raise

        def observe_connection(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connection.set_trace_callback(reader_statements.append)
            return connection

        def observe_proof(*args):
            proof_deadlines.append(window._delivery_deadline)
            record['proof_started'] = time.monotonic()
            return completed(*args)

        try:
            with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                    patch.object(self.children.store, 'attach', side_effect=attach_and_hold), \
                    patch.object(self.children, '_await_window', side_effect=retain_original_refusal), \
                    patch.object(factual, '_connect_readonly', side_effect=observe_connection), \
                    patch.object(factual, 'read_completed_result', side_effect=observe_proof), \
                    patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read, \
                    patch.object(self.kernel, 'claim_and_start', wraps=self.kernel.claim_and_start) as claim:
                with self.assertRaises((sqlite3.OperationalError, ChildExecutionError)) as caught:
                    self.children._await(row)
                read.assert_not_called()
                claim.assert_not_called()
            returned = time.monotonic()
            record.update(returned_refusal_at=returned,
                retained_native_deadline=window.deadline,
                retained_budget=window.envelope.to_dict(),
                retained_view=window.envelope.view(sample=window.envelope.checkpoint).to_dict(),
                readonly_statements=reader_statements,
                result_reads=read.call_count, child_claims=claim.call_count)
            self.assertEqual(len(errors), 1)
            self.assertIs(caught.exception, errors[0])
            if isinstance(caught.exception, sqlite3.OperationalError):
                self.assertTrue(is_sqlite_contention(caught.exception), str(caught.exception))
            else:
                # Preparation can consume the same original half-second
                # before a capture attempts SQL; preserve that exact expiry.
                self.assertEqual(caught.exception.code, 'child_wait_timeout')
            self.assertIsNone(caught.exception.__cause__)
            # A stronger captured floor can shorten the original allowance.
            self.assertGreaterEqual(returned, window.deadline)
            self.assertLessEqual(window.deadline, original_deadline)
            self.assertEqual(window.envelope.constraints, original_constraints)
            self.assertIsNone(window._delivery_deadline)
            self.assertEqual(len(proof_deadlines), 1)
            self.assertLessEqual(proof_deadlines[0], record['proof_started'] + .1)
            self.assertEqual(self.watermark(), watermark_before)
            self.assertEqual(self.kernel.get_execution_limits(snapshot.execution_id)['envelope'], canonical_before)
            self.assertEqual(self.kernel._connection.execute('SELECT token FROM kernel_budget_samples').fetchall(), [])
            current = self.kernel.get(snapshot.execution_id)
            self.assertEqual((current.state, current.attempt, current.fence),
                ('cancelled' if cancelled else 'queued', 0, 0))
            self.assertIsNone(current.lease)
            self.assertEqual(current.to_dict(), snapshot.to_dict())
            self.assertFalse(any(sql.lstrip().upper().startswith(('BEGIN', 'UPDATE', 'INSERT', 'DELETE'))
                for sql in reader_statements), reader_statements)
            record.update(assertions_completed_at=time.monotonic(),
                retained_native_deadline=window.deadline, proof_deadline=proof_deadlines[0],
                readonly_statements=reader_statements, child_after=current.to_dict(),
                result_reads=read.call_count, child_claims=claim.call_count,
                watermark_before=watermark_before, watermark_after=self.watermark())
        finally:
            writer.rollback()
            writer.close()

    def test_unstarted_queued_child_preserves_original_refusal_without_result_read(self):
        self.unstarted_child_preserves_original_refusal(cancelled=False)

    def test_unstarted_cancelled_child_preserves_original_refusal_without_result_read(self):
        self.unstarted_child_preserves_original_refusal(cancelled=True)

    def test_unstarted_boundary_keeps_malformed_child_identity_raw(self):
        row, window, _ = self.unstarted_child()
        with sqlite3.connect(self.kernel.db_path, timeout=.1) as corrupt:
            # Only this corruption fixture bypasses schema CHECKs; production
            # readers must still reject these malformed persisted identities.
            corrupt.execute('PRAGMA ignore_check_constraints=ON')
            for state, attempt, fence in (('queued', 0, 1), ('cancelled', 1, 0),
                    ('succeeded', 0, 0), ('failed', 1.5, 1), ('cancelled', b'0', 0)):
                with self.subTest(state=state, attempt=attempt, fence=fence):
                    corrupt.execute('UPDATE kernel_executions SET state=?,attempt=?,fence=? WHERE execution_id=?',
                        (state, attempt, fence, row['child_execution_id']))
                    corrupt.commit()
                    window._delivery_deadline = time.monotonic() + .1
                    try:
                        with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
                            with self.assertRaises(StorageIsolationError) as caught:
                                self.children._completed_result(row, window)
                            read.assert_not_called()
                        self.assertEqual(str(caught.exception), 'child result ancestry identity is malformed')
                        self.assertIsNone(caught.exception.__cause__)
                        self.evidence['records'].append({'scenario': 'malformed_unstarted_identity',
                            'state': state, 'attempt': repr(attempt), 'fence': fence,
                            'refusal': str(caught.exception), 'proof_deadline': window._delivery_deadline,
                            'result_reads': read.call_count})
                    finally:
                        window._delivery_deadline = None

    def test_live_completed_response_does_not_require_kernel_writer(self):
        record = {'scenario': 'live_completed_response', 'stage': 'prepare_original_child'}
        self.evidence['records'].append(record)
        row, window, result = self.completed_child()
        row = self.children._enqueue(request_id='one-completed-response', child_id='child',
            action='observe', child_command=None, envelope=window.envelope, window=window)
        self.children.store.finish(row, 'completed', result=result.to_dict())
        self.children.store.attach(row, window)
        record.update(stage='response_committed', original_native_deadline=window.deadline,
            original_result=result.to_dict(), budget=window.envelope.to_dict())
        writer = sqlite3.connect(self.kernel.db_path, timeout=.1)
        statements = []
        try:
            writer.execute('BEGIN IMMEDIATE')
            before = self.watermark()
            self.kernel._connection.set_trace_callback(statements.append)
            started = time.monotonic()
            record.update(stage='original_writer_held', began=started)
            delivered = self.children._await_window(row, window)
            returned = time.monotonic()
            after = self.watermark()
            record.update(stage='delivered_while_writer_held', returned=returned,
                watermark_before=before, watermark_after=after, statements=statements,
                retained_native_deadline=window.deadline, delivered=delivered)
            self.assertEqual(delivered, result.to_dict())
            self.assertLess(returned, window.deadline)
            self.assertLessEqual(window.deadline, record['original_native_deadline'])
            self.assertEqual(before, after)
            self.assertFalse(any(sql.lstrip().upper().startswith(
                ('BEGIN', 'UPDATE', 'INSERT', 'DELETE')) for sql in statements), statements)
        finally:
            self.kernel._connection.set_trace_callback(None)
            writer.rollback()
            writer.close()

    def test_live_delivery_refuses_stale_parent_before_response_read(self):
        row, window, _ = self.completed_child()
        for field, value in (('lease_id', 'other-lease'), ('owner', 'other-owner'),
                ('revision', self.lease.revision + 1), ('attempt', self.lease.attempt + 1),
                ('fence', self.lease.fence + 1), ('expires_at', self.lease.expires_at + 1)):
            with self.subTest(field=field):
                self.children.parent_lease = replace(self.lease, **{field: value})
                with patch.object(self.children.store, 'request', wraps=self.children.store.request) as read:
                    with self.assertRaises(ChildExecutionError) as caught:
                        self.children._await_window(row, window)
                    self.assertEqual(caught.exception.code, 'parent_authority_revoked')
                    read.assert_not_called()
                self.evidence['records'].append({'scenario': 'stale_parent_before_response',
                    'field': field, 'code': caught.exception.code})

    def live_completed_response(self):
        _, window, result = self.completed_child()
        row = self.children._enqueue(request_id='live-negative-response', child_id='child',
            action='observe', child_command=None, envelope=window.envelope, window=window)
        self.children.store.finish(row, 'completed', result=result.to_dict())
        self.children.store.attach(row, window)
        self.evidence['records'].append({'scenario': 'committed_live_response',
            'result': result.to_dict(), 'original_native_deadline': window.deadline,
            'budget': window.envelope.to_dict()})
        return row, window, result

    def test_live_delivery_rejects_actual_parent_cancellation_before_response_read(self):
        row, window, _ = self.live_completed_response()
        winner = self.kernel.cancel('parent', lease=self.lease, timeout_seconds=.1)
        with patch.object(self.children.store, 'request', wraps=self.children.store.request) as read:
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._await_window(row, window)
            self.assertEqual(caught.exception.code, 'parent_authority_revoked')
            read.assert_not_called()
        self.evidence['records'].append({'scenario': 'live_actual_cancellation',
            'winner': winner.to_dict(), 'refusal': caught.exception.code})

    def test_live_delivery_expiry_uses_committed_watermark_after_wall_rollback(self):
        row, window, _ = self.live_completed_response()
        original_deadline = window.deadline
        baseline = self.wall[0]
        self.wall[0] = self.lease.expires_at + 1
        with self.kernel._control_lock(.1):
            with self.assertRaises(StaleFenceError):
                self.kernel.verify(self.lease)
        advanced = self.watermark()
        self.wall[0] = baseline
        with patch.object(self.children.store, 'request', wraps=self.children.store.request) as read:
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._await_window(row, window)
            self.assertEqual(caught.exception.code, 'parent_authority_revoked')
            read.assert_not_called()
        self.assertGreaterEqual(advanced, self.lease.expires_at + 1)
        self.assertEqual(self.watermark(), advanced)
        self.assertLessEqual(window.deadline, original_deadline)
        self.evidence['records'].append({'scenario': 'live_expiry_after_wall_rollback',
            'watermark': advanced, 'wall': self.wall[0], 'refusal': caught.exception.code})

    def foreign_guard_blocks_live_response(self, *, ancestor):
        guarded_id = 'parent'
        if ancestor:
            # Admit a real second-generation parent rather than inventing an
            # ancestry row; the original parent now owns the foreign guard.
            command = replace(self.command, execution_id='nested-parent',
                idempotency_key='nested-parent', causation_id='parent')
            self.kernel.submit_child(command, self.lease, self.budget, timeout_seconds=.1)
            lease = self.kernel.claim_and_start('nested-owner', execution_id='nested-parent',
                child_pool=True, timeout_seconds=.1)
            budget = self.kernel.prepare_execution_budget(lease).enter_handler(
                5, origin_id='execution:nested-parent')
            budget = self.kernel.confirm_handler_entry(lease, budget)
            self.command, self.lease, self.budget = command, lease, budget
            self.children = HandlerChildren(self.kernel, command, lease, budget,
                {'capacity': 1, 'max_depth': 2}, journal=self.children.store.journal)
        row, window, _ = self.live_completed_response()
        original_deadline = window.deadline
        token = self.kernel._begin_budget_sample(guarded_id, timeout_seconds=.1)
        before = self.watermark()
        canonical = self.kernel._connection.execute(
            'SELECT execution_id,envelope_json FROM kernel_execution_limits ORDER BY execution_id').fetchall()
        record = {'scenario': 'live_foreign_ancestor' if ancestor else 'live_foreign_parent',
            'token': token, 'original_native_deadline': original_deadline,
            'original_budget': window.envelope.to_dict()}
        self.evidence['records'].append(record)
        with patch.object(self.children.store, 'request', wraps=self.children.store.request) as read, \
                patch.object(self.kernel, '_finish_budget_sample', wraps=self.kernel._finish_budget_sample) as ack, \
                patch.object(self.kernel, '_begin_budget_sample', wraps=self.kernel._begin_budget_sample) as arm:
            with self.assertRaises(BudgetClockUnknownError) as caught:
                self.children._await_window(row, window)
            self.assertIn('budget_clock_sample_unresolved', str(caught.exception))
            read.assert_not_called()
            ack.assert_not_called()
            arm.assert_not_called()
        returned = time.monotonic()
        record.update(returned_refusal_at=returned, retained_native_deadline=window.deadline,
            retained_budget=window.envelope.to_dict(),
            retained_view=window.envelope.view(sample=window.envelope.checkpoint).to_dict(),
            refusal=str(caught.exception), response_reads=read.call_count,
            sample_acknowledgements=ack.call_count, sample_arms=arm.call_count)
        self.assertLessEqual(window.deadline, original_deadline)
        self.assertGreaterEqual(returned, window.deadline)
        self.assertEqual(self.watermark(), before)
        self.assertEqual(self.kernel._connection.execute(
            'SELECT execution_id,envelope_json FROM kernel_execution_limits ORDER BY execution_id').fetchall(), canonical)
        markers = self.kernel._connection.execute(
            'SELECT token,execution_id,reason FROM kernel_budget_samples').fetchall()
        self.assertEqual([tuple(marker) for marker in markers], [(token, guarded_id, 'sampling')])
        record.update({'scenario': 'live_foreign_ancestor' if ancestor else 'live_foreign_parent',
            'token': token, 'markers': [tuple(marker) for marker in markers],
            'original_native_deadline': original_deadline, 'retained_native_deadline': window.deadline,
            'refusal': str(caught.exception), 'watermark': before})

    def test_live_delivery_waits_out_foreign_parent_guard_without_ack(self):
        self.foreign_guard_blocks_live_response(ancestor=False)

    def test_live_delivery_waits_out_foreign_ancestor_guard_without_ack(self):
        self.foreign_guard_blocks_live_response(ancestor=True)

    def test_live_delivery_resumes_exact_pending_owner_within_original_window(self):
        row, window, result = self.live_completed_response()
        original_deadline = window.deadline
        writer = sqlite3.connect(self.kernel.db_path, timeout=.1)
        original_begin = self.kernel._begin_budget_sample
        def retain_writer_after_arm(*args, **kwargs):
            token = original_begin(*args, **kwargs)
            writer.execute('BEGIN IMMEDIATE')
            return token
        try:
            with patch.object(self.kernel, '_begin_budget_sample', side_effect=retain_writer_after_arm):
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    window._capture(window.envelope, timeout_seconds=.1)
            error = caught.exception
            self.assertTrue(is_sqlite_contention(error), str(error))
            owner = error.budget_sample_owner
            token = error.budget_sample_token
            self.assertIs(owner, window._capture)
            self.assertIs(self.kernel._budget_sample_owners[token], owner)
            self.assertIsNotNone(owner._pending[1])
            window._adopt_sample_owner(error)
            writer.rollback()
            with patch.object(self.kernel, '_finish_budget_sample', wraps=self.kernel._finish_budget_sample) as ack, \
                    patch.object(self.kernel, '_begin_budget_sample', wraps=self.kernel._begin_budget_sample) as arm:
                delivered = self.children._await_window(row, window)
                self.assertEqual(delivered, result.to_dict())
                self.assertTrue(ack.called)
                self.assertTrue(all(call.args[0] == token for call in ack.call_args_list))
                arm.assert_not_called()
            self.assertLess(time.monotonic(), original_deadline)
            self.assertLessEqual(window.deadline, original_deadline)
            self.assertIsNone(owner._pending)
            self.assertNotIn(token, self.kernel._budget_sample_owners)
            self.assertEqual(self.kernel._connection.execute('SELECT token FROM kernel_budget_samples').fetchall(), [])
            self.evidence['records'].append({'scenario': 'live_exact_owner_ack',
                'token': token, 'original_native_deadline': original_deadline,
                'retained_native_deadline': window.deadline, 'delivered': delivered})
        finally:
            writer.rollback()
            writer.close()

    def test_live_delivery_custom_and_memory_kernels_keep_writing_verify(self):
        class CustomSQLiteKernel(SQLiteKernel):
            pass
        _, window, _ = self.completed_child()
        original_deadline = window.deadline
        for kind in ('custom', 'memory'):
            with self.subTest(kind=kind):
                kernel = (CustomSQLiteKernel(self.kernel.db_path, now=lambda: self.wall[0])
                    if kind == 'custom' else SQLiteKernel(':memory:', now=lambda: self.wall[0]))
                try:
                    lease = self.lease
                    if kind == 'memory':
                        kernel.submit(self.command)
                        lease = kernel.claim_and_start('memory-owner', execution_id='parent', timeout_seconds=.1)
                    capability = HandlerChildren(kernel, self.command, lease, self.budget,
                        {'capacity': 1, 'max_depth': 1}, journal=self.children.store.journal)
                    statements = []
                    kernel._connection.set_trace_callback(statements.append)
                    with patch.object(kernel, 'verify', wraps=kernel.verify) as verify, \
                            patch.object(kernel, '_verify_active_lease_readonly', wraps=kernel._verify_active_lease_readonly) as inspect:
                        capability._active(window, delivery=True)
                        verify.assert_called_once_with(lease)
                        inspect.assert_not_called()
                    self.assertTrue(any(sql.startswith('BEGIN IMMEDIATE') for sql in statements), statements)
                    self.assertTrue(any(sql.startswith('UPDATE kernel_clock') for sql in statements), statements)
                    self.assertLess(time.monotonic(), original_deadline)
                    self.assertLessEqual(window.deadline, original_deadline)
                    self.evidence['records'].append({'scenario': 'live_verify_fallback',
                        'kind': kind, 'statements': statements})
                finally:
                    kernel.close()

    def test_live_delivery_preserves_actual_permanent_sql_error_before_response_read(self):
        row, window, _ = self.live_completed_response()
        errors = []
        def missing_authority_table(lease):
            try:
                self.kernel._connection.execute('SELECT state FROM absent_live_parent_authority')
            except sqlite3.OperationalError as error:
                errors.append(error)
                raise
        with patch.object(self.kernel, '_verify_active_lease_readonly', side_effect=missing_authority_table) as verify, \
                patch.object(self.children.store, 'request', wraps=self.children.store.request) as read:
            with self.assertRaises(sqlite3.OperationalError) as caught:
                self.children._await_window(row, window)
            self.assertIs(caught.exception, errors[0])
            verify.assert_called_once_with(self.lease)
            read.assert_not_called()
        self.evidence['records'].append({'scenario': 'live_permanent_sql',
            'type': type(caught.exception).__name__, 'message': str(caught.exception)})

    def test_live_delivery_inherits_original_expired_control_before_response_read(self):
        row, window, _ = self.live_completed_response()
        original_deadline = window.deadline
        before = self.watermark()
        with patch.object(self.children.store, 'request', wraps=self.children.store.request) as read:
            with self.kernel._control_lock(.005):
                control_deadline = self.kernel._control_deadline
                self.assertIsNotNone(control_deadline)
                time.sleep(.01)
                # Windows' monotonic clock can remain on the same coarse tick
                # after this sleep. Observe expiry of the original 5ms bound.
                while time.monotonic() < control_deadline:
                    self.assertLess(time.monotonic(), original_deadline)
                    time.sleep(.001)
                expired_at = time.monotonic()
                self.evidence['records'].append({
                    'scenario': 'live_inherited_control_expiry_precondition',
                    'original_control_deadline': control_deadline,
                    'observed_expired_at': expired_at,
                    'original_native_deadline': original_deadline})
                self.assertGreaterEqual(expired_at, control_deadline)
                self.assertLess(expired_at, original_deadline)
                with self.assertRaises(TimeoutError) as caught:
                    self.children._await_window(row, window)
            self.assertEqual(str(caught.exception), 'Kernel control admission budget elapsed')
            read.assert_not_called()
        self.assertLessEqual(window.deadline, original_deadline)
        self.assertEqual(self.watermark(), before)
        self.assertEqual(self.kernel._connection.execute('SELECT token FROM kernel_budget_samples').fetchall(), [])
        self.evidence['records'].append({'scenario': 'live_inherited_control_expiry',
            'original_native_deadline': original_deadline, 'retained_native_deadline': window.deadline,
            'refusal': str(caught.exception)})

    def test_live_response_read_cancellation_keeps_existing_boundary_behavior(self):
        row, window, result = self.live_completed_response()
        original_read = self.children.store.request
        def cancel_after_response_read(*args):
            response = original_read(*args)
            self.kernel.cancel('parent', lease=self.lease, reason='during response read', timeout_seconds=.1)
            return response
        with patch.object(self.children.store, 'request', side_effect=cancel_after_response_read) as read:
            self.assertEqual(self.children._await_window(row, window), result.to_dict())
            read.assert_called_once()
        self.assertEqual(self.kernel.get('parent').state, 'cancelled')
        with patch.object(self.children.store, 'request', wraps=self.children.store.request) as read:
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._await_window(row, window)
            self.assertEqual(caught.exception.code, 'parent_authority_revoked')
            read.assert_not_called()
        self.evidence['records'].append({'scenario': 'live_response_cancel_race',
            'delivered': result.to_dict(), 'next_read_refusal': caught.exception.code})

    def test_real_writer_held_beyond_original_cutoff_allows_readonly_delivery_without_clock_write(self):
        row, window, result = self.completed_child()
        original = BudgetEnvelope.from_dict(json.loads(row['budget_json']))
        before = self.watermark()
        writer = sqlite3.connect(self.kernel.db_path, timeout=.1)
        writer.execute('BEGIN IMMEDIATE')
        statements, reader_statements, calls = [], [], []
        self.kernel._connection.set_trace_callback(statements.append)
        connect, read_floor = factual._connect_readonly, factual._read_floor
        def observe_connection(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connection.set_trace_callback(reader_statements.append)
            return connection
        def observe_floor(connection, lease, budget, **kwargs):
            calls.append(budget.deadline)
            return read_floor(connection, lease, budget, **kwargs)
        try:
            # Actual contention remains held throughout the expired original
            # child-call window and both fresh parent observations.
            original_deadline = window.deadline
            time.sleep(max(0., original_deadline - time.monotonic()) + .01)
            before_delivery = time.monotonic()
            self.evidence['records'].append({'scenario': 'held_writer_original_cutoff_aging',
                'original_native_deadline': original_deadline,
                'before_completed_result': before_delivery,
                'cutoff_has_passed': before_delivery >= original_deadline})
            with patch.object(factual, '_connect_readonly', side_effect=observe_connection), \
                    patch.object(factual, '_read_floor', side_effect=observe_floor), \
                    patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as child_read, \
                    patch.object(self.kernel, 'verify', side_effect=AssertionError('business verify invoked')):
                started = time.monotonic()
                delivered = self.children._completed_result(row, window)
                elapsed = time.monotonic() - started
            after = self.watermark()
            self.assertEqual(delivered, result.to_dict())
            self.assertEqual(before, after)
            child_read.assert_called_once()
            self.assertGreaterEqual(len(calls), 4)
            self.assertEqual(len(set(calls)), 1)
            self.assertLess(elapsed, .1)
            self.assertFalse(self.kernel._connection.in_transaction)
            self.assertFalse(any(sql.lstrip().upper().startswith(('BEGIN', 'UPDATE', 'INSERT', 'DELETE'))
                                 for sql in statements), statements)
            self.assertFalse(any(sql.lstrip().upper().startswith(('UPDATE', 'INSERT', 'DELETE'))
                                 for sql in reader_statements), reader_statements)
            self.evidence['records'].append({'scenario': 'writer_held_after_original_cutoff',
                'elapsed': elapsed, 'watermark_before': before, 'watermark_after': after,
                'parent_read_deadlines': calls, 'statements': statements,
                'readonly_statements': reader_statements,
                'original_budget': original.to_dict(), 'delivered': delivered})
        finally:
            self.kernel._connection.set_trace_callback(None)
            writer.rollback()
            writer.close()

    def test_fresh_final_parent_read_observes_actual_cancel_committed_during_child_read(self):
        row, window, _ = self.completed_child()
        original_read = factual._read_child_snapshot
        def cancel_between_reads(*args):
            result = original_read(*args)
            with SQLiteKernel(self.kernel.db_path) as other:
                other.cancel('parent', lease=self.lease, reason='concurrent parent cancellation')
            return result
        with patch.object(factual, '_read_child_snapshot', side_effect=cancel_between_reads) as child_read:
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._completed_result(row, window)
            child_read.assert_called_once()
        self.assertEqual(caught.exception.code, 'parent_authority_revoked')

    def test_shared_kernel_lock_cannot_block_independent_factual_result(self):
        row, window, result = self.completed_child()
        acquired, release = threading.Event(), threading.Event()
        def hold_control():
            with self.kernel._lock:
                acquired.set()
                release.wait(1)
        holder = threading.Thread(target=hold_control)
        holder.start()
        try:
            self.assertTrue(acquired.wait(.5))
            window._delivery_deadline = time.monotonic() + .1
            with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as read:
                delivered = self.children._completed_result(row, window)
                read.assert_called_once()
            self.assertEqual(delivered, result.to_dict())
            self.assertLess(time.monotonic(), window._delivery_deadline)
        finally:
            release.set()
            holder.join(1)
            self.assertFalse(holder.is_alive())

    def final_sql_failure(self, *, exhaust_progress):
        row, window, _ = self.completed_child()
        time.sleep(max(0., window.deadline-time.monotonic())+.01)
        original = ChildExecutionError('child_wait_timeout',
            'child wait exhausted its inherited work window', execution_id='child')
        actual_read, actual_floor = factual._read_child_snapshot, factual._read_floor
        returned = False
        raw_errors = []
        record = {'scenario': 'actual_final_progress_timeout' if exhaust_progress else 'actual_final_permanent_sql',
            'original_proof_seconds': .1, 'original_budget': json.loads(row['budget_json'])}
        def read_once(*args):
            nonlocal returned
            snapshot = actual_read(*args)
            returned = True
            return snapshot
        def final_sql(connection, lease, budget, **kwargs):
            if not returned:
                return actual_floor(connection, lease, budget, **kwargs)
            # The actual reader's final BEGIN starts only after its sole child
            # result read. Its installed progress handler owns this deadline.
            self.assertTrue(connection.in_transaction)
            record['proof_deadline'] = budget.deadline
            try:
                if exhaust_progress:
                    connection.execute('WITH RECURSIVE work(value) AS '
                        '(VALUES(0) UNION ALL SELECT value+1 FROM work) '
                        'SELECT sum(value) FROM work').fetchone()
                else:
                    connection.execute('SELECT value FROM missing_required_authority').fetchone()
            except sqlite3.OperationalError as error:
                raw_errors.append(error)
                record['raw_type'] = type(error).__name__
                record['raw_message'] = str(error)
                record['sqlite_errorcode'] = getattr(error, 'sqlite_errorcode', None)
                record['stopped_reason'] = budget.stopped_reason
                raise
            self.fail('actual proof SQL unexpectedly completed')
        try:
            with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                    patch.object(self.children.store, 'attach'), \
                    patch.object(self.children, '_await_window', side_effect=original), \
                    patch.object(factual, '_read_child_snapshot', side_effect=read_once) as read, \
                    patch.object(factual, '_read_floor', side_effect=final_sql):
                started = time.monotonic()
                expected = ChildExecutionError if exhaust_progress else sqlite3.OperationalError
                with self.assertRaises(expected) as caught:
                    self.children._await(row)
                record['elapsed'] = time.monotonic()-started
                record['read_calls'] = read.call_count
                read.assert_called_once()
            self.assertEqual(len(raw_errors), 1)
            if exhaust_progress:
                self.assertIs(caught.exception, original)
                self.assertIsInstance(caught.exception.__cause__, InspectionBudgetExceeded)
                self.assertIs(caught.exception.__cause__.__cause__, raw_errors[0])
                self.assertEqual(record['stopped_reason'], 'timeout')
                self.assertGreaterEqual(time.monotonic(), record['proof_deadline'])
                code = getattr(raw_errors[0], 'sqlite_errorcode', None)
                if code is not None:
                    self.assertEqual(code & 255, sqlite3.SQLITE_INTERRUPT)
                else:
                    self.assertEqual(str(raw_errors[0]), 'interrupted')
            else:
                self.assertIs(caught.exception, raw_errors[0])
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(record['stopped_reason'])
                self.assertIn('no such table', str(caught.exception))
            self.assertLess(record['elapsed'], .2)
            self.assertIsNone(window._delivery_deadline)
        finally:
            self.evidence['records'].append(record)

    def test_real_final_progress_timeout_keeps_original_wait_and_interrupt_after_one_child_read(self):
        self.final_sql_failure(exhaust_progress=True)

    def test_real_final_permanent_sql_error_remains_raw_after_one_child_read(self):
        self.final_sql_failure(exhaust_progress=False)

    def test_cancelled_and_revoked_parent_are_excluded_before_child_read(self):
        row, window, _ = self.completed_child()
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                self.children.parent_lease = (self.lease if cancelled else
                    replace(self.lease, lease_id='revoked-lease'))
                if cancelled:
                    self.kernel.cancel('parent', lease=self.lease, reason='parent cancelled')
                with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as child_read:
                    with self.assertRaises(ChildExecutionError) as caught:
                        self.children._completed_result(row, window)
                    self.assertEqual(caught.exception.code, 'parent_authority_revoked')
                    child_read.assert_not_called()

    def test_expired_parent_uses_durable_watermark_even_after_wall_rollback(self):
        row, window, _ = self.completed_child()
        self.wall[0] = self.lease.expires_at + 1
        with self.assertRaises(StaleFenceError):
            self.kernel.verify(self.lease)
        advanced = self.watermark()
        self.wall[0] = self.budget.checkpoint.wall_at
        with patch.object(factual, '_read_child_snapshot', wraps=factual._read_child_snapshot) as child_read:
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._completed_result(row, window)
            self.assertEqual(caught.exception.code, 'parent_authority_revoked')
            child_read.assert_not_called()
        self.assertEqual(self.watermark(), advanced)

    def test_readonly_helper_rejects_retained_transaction_and_inherits_control_expiry(self):
        self.kernel._connection.execute('BEGIN')
        try:
            with self.assertRaises(StorageIsolationError):
                self.kernel._verify_active_lease_readonly(self.lease)
        finally:
            self.kernel._connection.rollback()
        before = self.watermark()
        clock = [time.monotonic()]
        control_clock = SimpleNamespace(**{**vars(time), 'monotonic': lambda: clock[0]})
        with patch('dispatcher_sdk.execution_kernel._sqlite_base.time', control_clock):
            with self.kernel._control_lock(.005):
                # A short real sleep need not cross a coarse monotonic tick.
                # Advance the original caller's clock beyond its same cutoff.
                clock[0] += .01
                with self.assertRaises(TimeoutError):
                    self.kernel._verify_active_lease_readonly(self.lease)
        self.assertEqual(self.watermark(), before)


if __name__ == '__main__':
    unittest.main()
