"""Received sampling facts retain exact ownership through receipt recovery.

These focused Runtime integration cases use a real process producer and SQLite
writer. They do not replace native-supervisor or public-entry acceptance.
"""
from dataclasses import replace
from contextlib import contextmanager
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, _process_runtime as native
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, ClockCheckpoint
from dispatcher_sdk.execution_kernel.budget_capture import _KernelBudgetCapture
from dispatcher_sdk.execution_kernel.contracts import ExecutionLease
from dispatcher_sdk.execution_kernel.errors import CASConflictError
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory
from tests._storage_evidence import StorageEvidence


def _value_handler(payload, context):
    return payload


def _produce_checkpoint(path, envelope_dict, sender, evidence_path, uncaptured=False):
    """Process exit releases the writer; it never acknowledges the pending fact."""
    envelope = BudgetEnvelope.from_dict(envelope_dict)
    wall_calls = []

    def wall():
        wall_calls.append(True)
        return envelope.checkpoint.wall_at + 4

    kernel = SQLiteKernel(path, now=wall)
    owner = _KernelBudgetCapture(kernel, 'work')
    writer = sqlite3.connect(path, isolation_level=None, timeout=0.)
    evidence = {'uncaptured': uncaptured}
    value = _value_handler({'original': [True, 1, 1.0, 'raw']}, None)
    if uncaptured:
        # A real committed arm with no observed clock fact is intentionally
        # unresolved. Native finish must emit its existing unknown checkpoint.
        token = kernel._begin_budget_sample('work', _owner=owner)
        evidence['arm_committed'] = not kernel._connection.in_transaction
    else:
        captured_call = owner._captured

        def capture_then_hold(token, captured):
            captured_call(token, captured)
            evidence['arm_committed'] = not kernel._connection.in_transaction
            writer.execute('BEGIN IMMEDIATE')
            evidence['writer_held_after_positive_capture'] = writer.in_transaction

        owner._captured = capture_then_hold
        try:
            owner(envelope, timeout_seconds=.1)
        except (sqlite3.OperationalError, TimeoutError) as error:
            # Arm/capture and the independent writer rendezvous share the
            # original .1 window. That window can expire after the positive
            # capture but before ACK admission. The existing finish-only
            # operation below must still report actual SQLite contention.
            evidence['original_capture_error'] = {'type': type(error).__name__, 'message': str(error)}
            if owner._pending is None or owner._pending[1] is None or not writer.in_transaction:
                raise
        else:
            raise AssertionError('the real writer did not prevent the original ACK')
        token = owner._pending[0]
    before_finish = len(wall_calls)
    retained, checkpoint = native._finish_budget_capture(owner, envelope, timeout_seconds=.1)
    evidence.update(token=token, checkpoint=checkpoint,
                    wall_calls_before_finish=before_finish, wall_calls_after_finish=len(wall_calls),
                    pending_captured=owner._pending[1] is not None)
    outcome = {'kind': 'ok', 'value': value, 'effect_ids': [],
               'completed_at': envelope.started_at, 'completion_time_known': True,
               'budget_envelope': retained.to_dict(),
               'budget_checkpoint': {'parent': {'state': 'confirmed'}, 'supervisor': checkpoint}}
    native._send_packet(sender, {'kind': 'handler_completed', 'outcome': outcome})
    Path(evidence_path).write_text(json.dumps(evidence, indent=2))
    sender.close()
    # Do not close the Kernel after releasing the writer: close would retry
    # this live owner and hide the received-fact handoff boundary.
    os._exit(0)


def _crash_after_received_ack(path, running_dict, lease_dict, outcome, evidence_path):
    runtime = Kernel.open_sqlite(path, {'handler': _value_handler}, now=lambda: 100., isolation_mode='thread')
    lease = ExecutionLease.from_dict(lease_dict)
    running = runtime.kernel.get('work')
    if running.to_dict() != running_dict:
        raise AssertionError('original execution changed before receipt recovery crash')
    finish = runtime.kernel._finish_received_budget_sample

    def acknowledge_then_exit(*args, **options):
        result = finish(*args, **options)
        guards = [tuple(row) for row in runtime.kernel._connection.execute(
            'SELECT token,execution_id,reason FROM kernel_budget_samples')]
        Path(evidence_path).write_text(json.dumps({'guards_after_ack': guards,
            'receipt': runtime._settlement_journal.inspect('work'),
            'forwarded_options': options}, indent=2))
        os._exit(73)

    runtime.kernel._finish_received_budget_sample = acknowledge_then_exit
    admission = runtime._pending_settlements.acquire()
    runtime._settle_outcome(running, lease, outcome, admission)
    raise AssertionError('actual received ACK was not reached before process exit')


class ReceivedBudgetCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-received-budget-checkpoint-')
        self.storage_evidence = StorageEvidence(self.root, self)
        self.storage_evidence.start(include_kernel=True)
        self.addCleanup(self.storage_evidence.stop)
        self.addCleanup(self.storage_evidence.save)
        self.wall = [100.]
        self.runtime = self.open_runtime()
        command = self.runtime.command('handler', execution_id='work', idempotency_key='work',
            correlation_id='received-fact', timeout_seconds=10, payload={})
        self.runtime.submit(command)
        self.lease = self.runtime.kernel.claim_and_start('owner', execution_id='work', lease_seconds=90)
        prepared = self.runtime.kernel.prepare_execution_budget(self.lease)
        envelope = prepared.enter_handler(10, origin_id='execution:work', sample=prepared.checkpoint)
        self.envelope = self.runtime.kernel.confirm_handler_entry(self.lease, envelope)
        self.running = self.runtime.kernel.get('work')
        self.evidence = {'test': self.id(), 'records': []}

    def open_runtime(self):
        runtime = Kernel.open_sqlite(self.root/'kernel.sqlite3', {'handler': _value_handler},
                                    now=lambda: self.wall[0], isolation_mode='thread')
        self.addCleanup(runtime.close)
        return runtime

    def tearDown(self):
        self.storage_evidence.save(phase='before_cleanup', checkpoint=self.evidence)
        path = self.root/'evidence.json'
        path.write_text(json.dumps(self.evidence, indent=2))
        print('received_budget_checkpoint_evidence=' + str(path), flush=True)

    def produce(self, *, uncaptured=False):
        context = multiprocessing.get_context('spawn')
        receiver, sender = context.Pipe(duplex=False)
        producer_path = self.root/'producer.json'
        worker = context.Process(target=_produce_checkpoint,
            args=(self.runtime.kernel.db_path, self.envelope.to_dict(), sender, str(producer_path), uncaptured))
        worker.start()
        sender.close()
        try:
            self.assertTrue(receiver.poll(2), 'original two-second producer packet bound elapsed')
            packet = native._receive_packet(receiver)
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(worker.exitcode, 0)
            evidence = json.loads(producer_path.read_text())
            self.assertTrue(evidence['arm_committed'])
            self.assertEqual(evidence['wall_calls_before_finish'], evidence['wall_calls_after_finish'])
            checkpoint = packet['outcome']['budget_checkpoint']['supervisor']
            self.assertEqual(checkpoint, evidence['checkpoint'])
            self.assertEqual(checkpoint['state'], 'unknown')
            self.assertEqual(checkpoint['token'], evidence['token'])
            if uncaptured:
                self.assertIsNone(checkpoint['captured_envelope'])
                self.assertFalse(evidence['pending_captured'])
                self.assertEqual(evidence['wall_calls_after_finish'], 0)
            else:
                self.assertTrue(evidence['writer_held_after_positive_capture'])
                self.assertIn(evidence['original_capture_error']['type'], ('OperationalError', 'TimeoutError'))
                self.assertTrue(evidence['pending_captured'])
                self.assertEqual(checkpoint['error']['cause'], 'OperationalError')
                self.assertEqual(checkpoint['error']['error'], 'database is locked')
                self.assertIsInstance(checkpoint['captured_envelope'], dict)
            self.assertEqual(self.guards(), [(checkpoint['token'], 'work', 'sampling')])
            self.assertEqual(self.runtime.kernel._budget_sample_owners, {})
            self.evidence['records'].append({'producer': evidence, 'packet': packet})
            return packet['outcome']
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join(2)
            receiver.close()

    def guards(self):
        return [tuple(row) for row in self.runtime.kernel._connection.execute(
            'SELECT token,execution_id,reason FROM kernel_budget_samples ORDER BY execution_id,token')]

    def settle(self, outcome):
        admission = self.runtime._pending_settlements.acquire()
        self.assertIsNotNone(admission)
        try:
            return self.runtime._settle_outcome(self.running, self.lease, outcome, admission)
        finally:
            self.runtime._pending_settlements.finish(admission)

    def receipt(self):
        records = self.runtime._settlement_journal.inspect('work')
        self.assertEqual(len(records), 1)
        return records[0]

    def assert_published(self, outcome):
        captured = BudgetEnvelope.from_dict(outcome['budget_checkpoint']['supervisor']['captured_envelope'])
        canonical = BudgetEnvelope.from_dict(self.runtime.kernel.get_execution_limits('work')['envelope'])
        common = ClockCheckpoint(0., max(canonical.checkpoint.elapsed_at, captured.checkpoint.elapsed_at),
            canonical.checkpoint.domain_id, canonical.checkpoint.domain_scope, canonical.checkpoint.unknown_reason)
        self.assertGreaterEqual(canonical.checkpoint.effective_time(common), captured.checkpoint.effective_time(common))
        self.assertEqual(canonical.constraints, self.envelope.constraints)
        self.assertEqual(canonical.started_at, self.envelope.started_at)
        self.assertEqual(self.guards(), [])
        self.assertEqual(self.runtime.kernel._budget_sample_owners, {})

    def recover_recorded(self, original):
        """Finish factual publication within the original .5 maintenance window."""
        began = time.monotonic()
        deadline = began + .5
        maintenance = {'began': began, 'deadline': deadline, 'passes': []}
        self.evidence['records'].append({'maintenance': maintenance})
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            attempt = {'began': time.monotonic(), 'timeout_seconds': remaining}
            maintenance['passes'].append(attempt)
            try:
                attempt['reports'] = self.runtime.recover_completions(timeout_seconds=remaining)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                with self.runtime.kernel._control_lock(remaining):
                    current = self.runtime.kernel.get('work')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                records = self.runtime._settlement_journal.inspect('work', timeout_seconds=remaining)
                attempt['execution'] = current.to_dict()
                attempt['receipts'] = records
            except Exception as error:
                attempt['error'] = {'type': type(error).__name__, 'message': str(error)}
                if not (self.runtime._storage_contention(error) or isinstance(error, TimeoutError)):
                    raise
            finally:
                attempt['returned'] = time.monotonic()
            if 'receipts' in attempt and len(records) == 1 and records[0]['state'] == 'recorded':
                self.assertLessEqual(attempt['returned'], deadline, maintenance)
                self.assertEqual(records[0]['result'], original['result'])
                self.assertEqual(current.result.to_dict(), original['result'])
                return current
        self.fail('original .5-second received-fact maintenance window elapsed: ' + repr(maintenance))

    def recover_after_real_writer(self, *, expire_archive=False):
        outcome = self.produce()
        writer = sqlite3.connect(self.runtime.kernel.db_path, isolation_level=None, timeout=0.)
        writer.execute('BEGIN IMMEDIATE')
        try:
            returned = self.settle(outcome)
            self.assertEqual(returned.state, 'running')
            receipt = self.receipt()
            self.assertEqual(receipt['state'], 'pending')
            self.assertEqual(receipt['evidence']['budget_checkpoint'], outcome['budget_checkpoint'])
            self.assertEqual(receipt['result']['value'], outcome['value'])
            self.assertEqual(len(self.guards()), 1)
        finally:
            writer.rollback()
            writer.close()
        journal = self.runtime._settlement_journal
        connection = journal._connection
        expired_bodies = []

        @contextmanager
        def expire_first_write(timeout_seconds, **options):
            with connection(timeout_seconds, **options) as actual:
                # This is later than production's deadline origin, so crossing
                # it proves expiry even with a coarse native monotonic clock.
                expiry = time.monotonic() + timeout_seconds
                yield actual
                if options.get('write') and not expired_bodies:
                    # The real UPDATE has run. Expire its existing pre-COMMIT
                    # window so the production guard must roll it back.
                    expired_bodies.append({'timeout_seconds': timeout_seconds,
                        'pass_index': len(self.evidence['records'][-1]['maintenance']['passes']) - 1,
                        'transaction_open': actual.in_transaction,
                        'body_state': actual.execute('SELECT state FROM settlement_records').fetchone()[0]})
                    while time.monotonic() < expiry:
                        time.sleep(min(.001, max(0, expiry - time.monotonic())))

        if expire_archive:
            self.evidence['records'].append({'expired_archive_bodies': expired_bodies})
            with patch.object(journal, '_connection', side_effect=expire_first_write):
                settled = self.recover_recorded(receipt)
            self.assertEqual(len(expired_bodies), 1)
            self.assertTrue(expired_bodies[0]['transaction_open'])
            self.assertEqual(expired_bodies[0]['body_state'], 'recorded')
            passes = self.evidence['records'][-1]['maintenance']['passes']
            injected = expired_bodies[0]['pass_index']
            self.assertGreater(len(passes), injected + 1)
            self.assertEqual(passes[injected]['execution']['state'], 'succeeded')
            self.assertEqual(passes[injected]['receipts'][0]['state'], 'pending')
            self.assertEqual(passes[injected]['receipts'][0]['result'], receipt['result'])
            self.assertTrue(any(report.get('state') == 'pending'
                and 'SettlementBusyError' in report.get('error', '')
                for report in passes[injected]['reports']), passes)
        else:
            settled = self.recover_recorded(receipt)
        self.assert_published(outcome)
        self.assertEqual(settled.state, 'succeeded')
        self.assertEqual(settled.result.value, outcome['value'])
        self.assertEqual(self.receipt()['state'], 'recorded')

    def test_received_positive_fact_is_retained_then_recovered_after_real_writer(self):
        """Recovery finishes Kernel and receipt within one original .5 window."""
        self.recover_after_real_writer()

    def test_received_positive_fact_archive_expiry_retries_same_result_within_original_window(self):
        self.recover_after_real_writer(expire_archive=True)

    def test_foreground_received_fact_ack_precedes_recorded_result(self):
        outcome = self.produce()
        returned = self.settle(outcome)
        self.assertEqual(returned.state, 'succeeded')
        self.assertEqual(returned.result.value, outcome['value'])
        self.assert_published(outcome)
        receipt = self.receipt()
        self.evidence['records'].append({'foreground': {'execution': returned.to_dict(),
            'receipt': receipt, 'settlement_error': self.runtime._settlement_error,
            'guards_after_ack': self.guards()}})
        # Kernel success and ACK publication precede the bounded archive write.
        # If that write expires, maintenance archives the same result without
        # repeating business work or restoring spent execution authority.
        if receipt['state'] == 'pending':
            self.recover_recorded(receipt)
        self.assertEqual(self.receipt()['state'], 'recorded')

    def test_receipt_writer_contention_keeps_positive_fact_locally_until_durable(self):
        outcome = self.produce()
        writer = sqlite3.connect(self.runtime._settlement_journal.path,
                                 isolation_level=None, timeout=0.)
        writer.execute('BEGIN IMMEDIATE')
        before = self.guards()
        try:
            returned = self.settle(outcome)
            self.assertEqual(returned.state, 'running')
            self.assertEqual(self.guards(), before)
            self.assertEqual(self.runtime._settlement_journal.inspect('work'), [])
            entries = self.runtime._pending_settlements.entries(1)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].evidence['budget_checkpoint'], outcome['budget_checkpoint'])
        finally:
            writer.rollback()
            writer.close()
        self.runtime.recover_completions(timeout_seconds=.5)
        self.assert_published(outcome)
        self.assertEqual(self.runtime.kernel.get('work').result.value, outcome['value'])
        self.assertEqual(self.receipt()['state'], 'recorded')

    def test_positive_fact_ack_does_not_invent_original_completion_time(self):
        outcome = self.produce()
        outcome['completion_time_known'] = False
        outcome['completion_time_error'] = 'original completion time is unknown'
        returned = self.settle(outcome)
        self.runtime.recover_completions(timeout_seconds=.5)
        self.assertEqual(returned.state, 'running')
        self.assertEqual(self.runtime.kernel.get('work').state, 'running')
        self.assertIsNone(self.runtime.kernel.get('work').result)
        self.assert_published(outcome)
        receipt = self.receipt()
        self.assertEqual(receipt['state'], 'error')
        self.assertEqual(receipt['deferred']['kind'], 'completion_time_unknown')
        self.assertEqual(receipt['deferred']['outcome']['completion_time_error'],
                         outcome['completion_time_error'])

    def test_post_ack_pre_journal_process_exit_replays_durable_floor_proof(self):
        outcome = self.produce()
        self.runtime.close()
        context = multiprocessing.get_context('spawn')
        path = self.root/'ack-crash.json'
        worker = context.Process(target=_crash_after_received_ack, args=(str(self.root/'kernel.sqlite3'),
            self.running.to_dict(), self.lease.to_dict(), outcome, str(path)))
        worker.start()
        try:
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(worker.exitcode, 73)
            crash = json.loads(path.read_text())
            self.assertEqual(crash['guards_after_ack'], [])
            self.assertEqual(crash['receipt'][0]['state'], 'pending')
            self.assertEqual(crash['receipt'][0]['evidence']['budget_checkpoint'], outcome['budget_checkpoint'])
            self.evidence['records'].append({'actual_ack_crash': crash})
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join(2)
        self.runtime = self.open_runtime()
        self.assertEqual(self.runtime.kernel.get('work').state, 'running')
        self.runtime.recover_completions(timeout_seconds=.5)
        self.assert_published(outcome)
        self.assertEqual(self.runtime.kernel.get('work').result.value, outcome['value'])
        self.assertEqual(self.receipt()['state'], 'recorded')

    def test_uncaptured_receipt_keeps_marker_and_original_budget_unknown(self):
        outcome = self.produce(uncaptured=True)
        outcome['completion_time_known'] = False
        outcome['completion_time_error'] = 'original sampling fact was never captured'
        before_guards = self.guards()
        before = self.runtime.kernel.get_execution_limits('work')
        self.settle(outcome)
        self.runtime.recover_completions(timeout_seconds=.5)
        self.assertEqual(self.guards(), before_guards)
        self.assertEqual(self.runtime.kernel.get_execution_limits('work'), before)
        self.assertEqual(self.runtime.kernel.get('work').state, 'running')
        self.assertEqual(self.receipt()['evidence']['budget_checkpoint'], outcome['budget_checkpoint'])

    def test_foreign_real_token_is_rejected_without_retiring_either_guard(self):
        outcome = self.produce()
        other = self.runtime.command('handler', execution_id='other', idempotency_key='other',
            correlation_id='foreign-fact', timeout_seconds=10, payload={})
        self.runtime.submit(other)
        lease = self.runtime.kernel.claim_and_start('other-owner', execution_id='other', lease_seconds=90)
        prepared = self.runtime.kernel.prepare_execution_budget(lease)
        envelope = prepared.enter_handler(10, origin_id='execution:other', sample=prepared.checkpoint)
        self.runtime.kernel.confirm_handler_entry(lease, envelope)
        foreign = self.runtime.kernel._begin_budget_sample('other')
        outcome['budget_checkpoint']['supervisor']['token'] = foreign
        before = self.guards()
        limits = self.runtime.kernel.get_execution_limits('work')
        returned = self.settle(outcome)
        self.assertEqual(returned.to_dict(), self.running.to_dict())
        self.assertEqual(self.receipt()['state'], 'pending')
        reports = self.runtime.recover_completions(timeout_seconds=.5)
        self.assertEqual(self.receipt()['state'], 'error')
        self.assertTrue(any(report.get('state') == 'error'
                            and 'CASConflictError' in report.get('error', '')
                            for report in reports), reports)
        self.assertEqual(self.guards(), before)
        self.assertEqual(self.runtime.kernel.get_execution_limits('work'), limits)
        self.assertEqual(self.runtime.kernel.get('work').state, 'running')

    def test_missing_token_replay_refuses_insufficient_floor_and_incompatible_domain(self):
        outcome = self.produce()
        captured = BudgetEnvelope.from_dict(outcome['budget_checkpoint']['supervisor']['captured_envelope'])
        before_guards = self.guards()
        before_limits = self.runtime.kernel.get_execution_limits('work')
        before_clock = tuple(self.runtime.kernel._connection.execute(
            'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone())
        incompatible = replace(captured, checkpoint=replace(captured.checkpoint,
                                                           domain_id='incompatible-received-clock'))
        for label, received in (('insufficient_committed_floor', captured),
                                ('incompatible_clock_domain', incompatible)):
            with self.subTest(label=label):
                with self.assertRaisesRegex(CASConflictError, 'committed clock floors do not acknowledge received fact'):
                    self.runtime.kernel._finish_received_budget_sample(
                        'nonexistent-received-token', 'work', received, timeout_seconds=.1)
                self.assertEqual(self.guards(), before_guards)
                self.assertEqual(self.runtime.kernel.get_execution_limits('work'), before_limits)
                self.assertEqual(tuple(self.runtime.kernel._connection.execute(
                    'SELECT watermark FROM kernel_clock WHERE singleton=1').fetchone()), before_clock)
                self.assertEqual(self.runtime.kernel._budget_sample_owners, {})

    def test_cancel_winner_keeps_immutable_result_while_received_fact_is_acknowledged(self):
        outcome = self.produce()
        winner = self.runtime.kernel.cancel('work', expected_revision=self.running.revision,
                                            reason='actual cancellation winner')
        returned = self.settle(outcome)
        self.assert_foreground_winner_snapshot(returned, winner)
        self.runtime.recover_completions(timeout_seconds=.5)
        self.assertEqual(self.runtime.kernel.get('work').to_dict(), winner.to_dict())
        self.assert_published(outcome)

    def test_reaped_winner_keeps_immutable_state_while_received_fact_is_acknowledged(self):
        outcome = self.produce()
        self.wall[0] = 200.
        self.runtime.kernel.reap()
        winner = self.runtime.kernel.get('work')
        self.assertEqual(winner.state, 'dead')
        self.settle(outcome)
        self.runtime.recover_completions(timeout_seconds=.5)
        self.assertEqual(self.runtime.kernel.get('work').to_dict(), winner.to_dict())
        self.assert_published(outcome)

    def test_revoked_positive_fact_without_script_artifact_owns_factual_receipt(self):
        original = self.produce()
        winner = self.runtime.kernel.cancel('work', expected_revision=self.running.revision,
                                            reason='actual revoked execution')
        outcome = {'kind': 'authority_revoked', 'reason': 'execution_cancelled', 'effect_ids': [],
                   'budget_envelope': original['budget_envelope'],
                   'budget_checkpoint': original['budget_checkpoint']}
        returned = self.settle(outcome)
        self.assert_foreground_winner_snapshot(returned, winner)
        self.runtime.recover_completions(timeout_seconds=.5)
        self.assertEqual(self.runtime.kernel.get('work').to_dict(), winner.to_dict())
        self.assert_published(outcome)
        receipt = self.receipt()
        self.assertEqual(receipt['state'], 'recorded')
        self.assertEqual(receipt['deferred']['kind'], 'budget_checkpoint_recovery')
        self.assertEqual(receipt['evidence']['budget_checkpoint'], outcome['budget_checkpoint'])
        self.assertNotIn('script_output_recovery', receipt['evidence'])

    def assert_foreground_winner_snapshot(self, returned, winner):
        foreground = {'returned': returned.to_dict(), 'winner': winner.to_dict(),
                      'settlement_error': self.runtime._settlement_error}
        self.evidence['records'].append({'foreground_cancel': foreground})
        for name, operation in (('receipts', lambda: self.runtime._settlement_journal.inspect('work')),
                                ('guards', self.guards)):
            try:
                foreground[name] = operation()
            except Exception as error:
                foreground[name + '_error'] = {'type': type(error).__name__, 'message': str(error)}
        # ACK COMMIT can consume the original completion window before its
        # winner read. Maintenance cannot alter that already returned snapshot.
        # Only the exact supplied snapshot or exact winner is a valid return;
        # the authoritative winner and factual receipt are checked after the
        # original single maintenance call, without restoring execution time.
        if returned.to_dict() != winner.to_dict():
            self.assertEqual(returned.to_dict(), self.running.to_dict())


if __name__ == '__main__':
    unittest.main()
