import contextlib
import multiprocessing
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.settlement import (
    SettlementBindingError, SettlementBusyError, SettlementConflictError, SettlementJournal,
)
from dispatcher_sdk.execution_kernel.contracts import ExecutionLease

IDENTITY = {'execution_id': 'execution', 'attempt': 2, 'fence': 3}
RAW = '{"status":"failure","message":"worker result"}'


def supervisor_crashes_before_delivery(sender, binding, clock_failure=False, cleanup_failure=False, lease=IDENTITY):
    from dispatcher_sdk.execution_kernel import _process_runtime as process
    original_send = process._send_packet

    def fake_worker(db_path, handler, command, lease, now, channel, *args):
        original_send(channel, {'kind': 'worker_ready'})
        process._receive_packet(channel)
        original_send(channel, {'kind': 'worker_returned', 'outcome_json': RAW,
                                'completed_monotonic': time.monotonic()})
        original_send(channel, {'kind': 'worker_completed', 'outcome_json': RAW})
        return 0

    def crash_before_send(channel, packet):
        crash_kinds = ({'handler_failed', 'handler_start_failed'} if clock_failure else
                       {'handler_completed'})
        if packet.get('kind') in crash_kinds:
            os._exit(61)
        original_send(channel, packet)

    if clock_failure:
        original_remaining = process._DeadlineGuard.remaining
        original_receive = process._receive_packet
        observed = [False]
        def observe_return(channel):
            packet = original_receive(channel)
            if type(packet) is dict and packet.get('kind') == 'worker_returned':
                observed[0] = True
            return packet
        def fail_after_observation(guard, *args, **kwargs):
            if observed[0] and kwargs.get('resample'):
                raise process.BudgetClockUnknownError('simulated clock failure')
            return original_remaining(guard, *args, **kwargs)
        process._DeadlineGuard.remaining = fail_after_observation
        process._receive_packet = observe_return
    process._worker_entry = fake_worker
    process._send_packet = crash_before_send
    process._supervisor_entry('unused', None, SimpleNamespace(timeout_seconds=5), lease,
                              None, sender, 'full', startup_deadline=time.monotonic() + 5,
                              settlement_binding=binding)


def supervisor_with_short_work_budget(sender, binding, worker_delay=0):
    from dispatcher_sdk.execution_kernel import _process_runtime as process
    original_guard = process._DeadlineGuard
    original_send = process._send_packet

    class ShortWorkGuard(original_guard):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.deadline = time.monotonic() + .04
            self.hard_deadline = time.monotonic() + 1

    def fake_worker(db_path, handler, command, lease, now, channel, *args):
        original_send(channel, {'kind': 'worker_ready'})
        process._receive_packet(channel)
        time.sleep(worker_delay)
        original_send(channel, {'kind': 'worker_returned', 'outcome_json': RAW,
                                'completed_monotonic': time.monotonic()})
        original_send(channel, {'kind': 'worker_completed', 'outcome_json': RAW})
        return 0

    process._DeadlineGuard = ShortWorkGuard
    process._worker_entry = fake_worker
    process._supervisor_entry('unused', None, SimpleNamespace(timeout_seconds=5), IDENTITY,
                              None, sender, 'full', startup_deadline=time.monotonic() + 5,
                              settlement_binding=binding)


class SupervisorOutcomeHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.binding = {'path': str(root / 'journal.db'), 'kernel_path': str(root / 'kernel.db'), 'source_id': 'source'}
        self.journal = SettlementJournal(**self.binding, timeout_seconds=1)

    def intent(self):
        self.journal.note(IDENTITY, 'supervisor_spawn_intent', {}, timeout_seconds=1)

    def test_exact_intent_restart_replay_and_conflict(self):
        with self.assertRaises(SettlementBindingError):
            self.journal.record_supervisor_outcome(IDENTITY, RAW, timeout_seconds=1)
        self.intent()
        first = self.journal.record_supervisor_outcome(IDENTITY, RAW, timeout_seconds=1)
        reopened = SettlementJournal.open_existing(**self.binding, timeout_seconds=1)
        self.assertEqual(first, reopened.record_supervisor_outcome(IDENTITY, RAW, timeout_seconds=1))
        self.assertEqual(first['evidence']['outcome_json'], RAW)
        with self.assertRaises(SettlementConflictError):
            reopened.record_supervisor_outcome(IDENTITY, '{"different":true}', timeout_seconds=1)
        with self.assertRaises(SettlementBindingError):
            reopened.record_supervisor_outcome({**IDENTITY, 'fence': 4}, RAW, timeout_seconds=1)
        with self.assertRaises(ValueError):
            reopened.record_supervisor_outcome(IDENTITY, '{"x":"' + 'x' * 131072 + '"}', timeout_seconds=1)

    def test_busy_write_is_unknown_and_retry_succeeds(self):
        self.intent()
        with contextlib.closing(sqlite3.connect(self.binding['path'], isolation_level=None)) as lock, lock:
            lock.execute('BEGIN IMMEDIATE')
            with self.assertRaises(SettlementBusyError):
                self.journal.record_supervisor_outcome(IDENTITY, RAW, timeout_seconds=.02)
            lock.rollback()
        self.assertEqual(self.journal.record_supervisor_outcome(IDENTITY, RAW, timeout_seconds=1)['evidence']['outcome_json'], RAW)

    def test_disposition_is_exact_bounded_and_idempotent(self):
        self.intent()
        lease = ExecutionLease('execution', 'lease', 'owner', 3, 2, 9999999999, 1)
        facts = {'worker_return': 'indeterminate', 'parent_decision': 'unknown',
                 'settlement': 'unknown', 'worker_tree_cleanup': 'unknown'}
        self.journal._record_supervisor_disposition(lease, RAW, facts, timeout_seconds=1)
        reopened = SettlementJournal.open_existing(**self.binding, timeout_seconds=1)
        reopened._record_supervisor_disposition(lease, RAW, facts, timeout_seconds=1)
        notes = reopened.inspect_notes('execution', timeout_seconds=1)['notes']
        disposition = [note for note in notes if note['phase'] == 'supervisor_disposition_observed']
        self.assertEqual(len(disposition), 1)
        self.assertEqual(disposition[0]['identity'], IDENTITY)
        self.assertEqual(disposition[0]['evidence']['lease'], lease.to_dict())
        with self.assertRaises(SettlementConflictError):
            reopened._record_supervisor_disposition(lease, RAW, {**facts, 'worker_return': 'timely'}, timeout_seconds=1)
        with self.assertRaises(ValueError):
            reopened._record_supervisor_disposition(lease, RAW, {**facts, 'extra': 'x' * 262144}, timeout_seconds=1)
        self.assertEqual(reopened.pending(timeout_seconds=1), [])

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_indeterminate_disposition_survives_supervisor_crash(self):
        self.intent()
        lease = ExecutionLease('execution', 'lease', 'owner', 3, 2, 9999999999, 1)
        ctx = multiprocessing.get_context('fork')
        receiver, sender = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=supervisor_crashes_before_delivery,
                           args=(sender, self.binding, False, False, lease))
        proc.start()
        sender.close()
        proc.join(10)
        if proc.is_alive():
            proc.terminate()
            proc.join()
            self.fail('supervisor did not exit')
        self.assertEqual(proc.exitcode, 61)
        reopened = SettlementJournal.open_existing(**self.binding, timeout_seconds=1)
        notes = reopened.inspect_notes('execution', timeout_seconds=1)['notes']
        disposition = next(note for note in notes if note['phase'] == 'supervisor_disposition_observed')
        self.assertEqual(disposition['evidence']['worker_return'], 'indeterminate')
        self.assertEqual(disposition['evidence']['parent_decision'], 'unknown')
        self.assertEqual(disposition['evidence']['settlement'], 'unknown')
        self.assertEqual(reopened.pending(timeout_seconds=1), [])
        receiver.close()

    def test_worker_tree_cleanup_receipt_is_exact_and_distinct_from_supervisor_reap(self):
        with self.assertRaises(SettlementBindingError):
            self.journal.record_worker_tree_cleanup(IDENTITY, timeout_seconds=1)
        self.intent()
        first = self.journal.record_worker_tree_cleanup(IDENTITY, timeout_seconds=1)
        reopened = SettlementJournal.open_existing(**self.binding, timeout_seconds=1)
        self.assertEqual(first, reopened.record_worker_tree_cleanup(IDENTITY, timeout_seconds=1))
        with self.assertRaises(SettlementBindingError):
            reopened.record_worker_tree_cleanup({**IDENTITY, 'fence': 4}, timeout_seconds=1)
        row = reopened.scan_supervisor_cleanup(timeout_seconds=1)['registrations'][0]
        self.assertEqual((row['worker_tree_cleanup'], row['cleanup'], row['outcome']),
                         ('confirmed', 'unknown', 'unknown'))

    def test_worker_tree_cleanup_write_failure_remains_unknown_until_retry(self):
        self.intent()
        with contextlib.closing(sqlite3.connect(self.binding['path'], isolation_level=None)) as lock, lock:
            lock.execute('BEGIN IMMEDIATE')
            with self.assertRaises(SettlementBusyError):
                self.journal.record_worker_tree_cleanup(IDENTITY, timeout_seconds=.02)
            lock.rollback()
        row = self.journal.scan_supervisor_cleanup(timeout_seconds=1)['registrations'][0]
        self.assertEqual(row['worker_tree_cleanup'], 'unknown')
        self.journal.record_worker_tree_cleanup(IDENTITY, timeout_seconds=1)
        self.assertEqual(self.journal.scan_supervisor_cleanup(timeout_seconds=1)['registrations'][0]['worker_tree_cleanup'], 'confirmed')

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_blocked_journal_after_on_time_return_does_not_consume_work_budget(self):
        self.intent()
        ctx = multiprocessing.get_context('fork')
        receiver, sender = ctx.Pipe(duplex=False)
        with contextlib.closing(sqlite3.connect(self.binding['path'], isolation_level=None)) as lock, lock:
            lock.execute('BEGIN IMMEDIATE')
            proc = ctx.Process(target=supervisor_with_short_work_budget, args=(sender, self.binding))
            proc.start()
            sender.close()
            packets = []
            while receiver.poll(3):
                try:
                    packets.append(receiver.recv_bytes())
                except EOFError:
                    break
            proc.join(3)
            if proc.is_alive():
                proc.terminate()
                proc.join()
                self.fail('supervisor did not exit')
            lock.rollback()
        decoded = [json.loads(packet) for packet in packets]
        self.assertIn('handler_returned', [packet['kind'] for packet in decoded])
        self.assertIn('handler_completed', [packet['kind'] for packet in decoded])
        completed = next(packet for packet in decoded if packet['kind'] == 'handler_completed')
        self.assertEqual(completed['outcome_handoff']['state'], 'unknown')
        self.assertFalse(any(packet['kind'] == 'handler_timed_out' for packet in decoded))
        self.assertEqual(self.journal.scan_supervisor_cleanup(timeout_seconds=1)['registrations'][0]['worker_tree_cleanup'], 'unknown')
        receiver.close()

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_short_work_budget_still_stops_late_worker(self):
        self.intent()
        ctx = multiprocessing.get_context('fork')
        receiver, sender = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=supervisor_with_short_work_budget, args=(sender, self.binding, .2))
        proc.start()
        sender.close()
        packets = []
        while receiver.poll(3):
            try:
                packets.append(json.loads(receiver.recv_bytes()))
            except EOFError:
                break
        proc.join(3)
        if proc.is_alive():
            proc.terminate()
            proc.join()
            self.fail('supervisor did not exit')
        self.assertIn('handler_timed_out', [packet['kind'] for packet in packets])
        self.assertFalse(any(packet['kind'] == 'handler_completed' for packet in packets))
        self.assertFalse(any(note['phase'] == 'supervisor_outcome_observed'
                             for note in self.journal.inspect_notes('execution', timeout_seconds=1)['notes']))
        receiver.close()

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_parent_accepts_on_time_entry_and_return_with_busy_journal(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
        self.intent()
        ctx = multiprocessing.get_context('fork')
        phases = []

        def worker(db_path, handler, command, lease, now, channel, *args):
            process._send_packet(channel, {'kind': 'worker_ready'})
            process._receive_packet(channel)
            start = time.monotonic()
            envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
            process._send_packet(channel, {'kind': 'worker_entered', 'budget_envelope': envelope,
                'deadline_monotonic': start + .08, 'hard_deadline_monotonic': start + 1,
                'started_at': time.time()})
            process._send_packet(channel, {'kind': 'worker_returned', 'outcome_json': '{"kind":"ok"}',
                                           'completed_monotonic': time.monotonic()})
            process._send_packet(channel, {'kind': 'worker_completed', 'outcome_json': '{"kind":"ok"}'})
            return 0

        with contextlib.closing(sqlite3.connect(self.binding['path'], isolation_level=None)) as lock, lock:
            lock.execute('BEGIN IMMEDIATE')
            with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
                 patch.object(process, '_worker_entry', worker):
                result = process.invoke_process_handler(db_path='unused', handler=None,
                    command=SimpleNamespace(timeout_seconds=5), lease=IDENTITY, now=None,
                    start_timeout=5, settlement_binding=self.binding,
                    on_phase=lambda phase, details: phases.append((phase, details)))
            lock.rollback()
        self.assertEqual(result['kind'], 'ok', result)
        handoff = next(details for phase, details in phases if phase == 'supervisor_outcome_observed')
        self.assertEqual(handoff['state'], 'unknown')

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_parent_accepts_authoritative_timeout_only_after_cleanup(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
        self.intent()
        ctx = multiprocessing.get_context('fork')
        events = []
        lease = ExecutionLease('execution', 'lease', 'owner', 3, 2, 9999999999, 1)

        def worker(db_path, handler, command, lease, now, channel, *args):
            process._send_packet(channel, {'kind': 'worker_ready'})
            process._receive_packet(channel)
            start = time.monotonic()
            envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
            process._send_packet(channel, {'kind': 'worker_entered', 'budget_envelope': envelope,
                'deadline_monotonic': start + .1, 'hard_deadline_monotonic': start + .3,
                'started_at': time.time()})
            time.sleep(2)
            return 0

        with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
             patch.object(process, '_worker_entry', worker):
            result = process.invoke_process_handler(db_path='unused', handler=None,
                command=SimpleNamespace(timeout_seconds=5), lease=lease, now=None,
                start_timeout=5, settlement_binding=self.binding,
                on_phase=lambda phase, details: events.append(phase),
                on_cleanup_confirmed=lambda: events.append('cleanup'))
        self.assertEqual(result['kind'], 'timeout', result)
        self.assertIn('supervisor_result_accepted', events)
        self.assertLess(events.index('cleanup'), events.index('supervisor_result_accepted'))

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_confirmed_pre_invocation_failure_can_release_after_cleanup(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        self.intent()
        ctx = multiprocessing.get_context('fork')
        events = []
        lease = ExecutionLease('execution', 'lease', 'owner', 3, 2, 9999999999, 1)

        def worker(db_path, handler, command, lease, now, channel, *args):
            process._send_packet(channel, {'kind': 'worker_failed', 'message': 'bootstrap failed'})
            return 0

        with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
             patch.object(process, '_worker_entry', worker):
            result = process.invoke_process_handler(db_path='unused', handler=None,
                command=SimpleNamespace(timeout_seconds=5), lease=lease, now=None,
                start_timeout=5, settlement_binding=self.binding,
                on_phase=lambda phase, details: events.append(phase),
                on_cleanup_confirmed=lambda: events.append('cleanup'))
        self.assertEqual((result['kind'], result['code']), ('error', 'handler_process_start_failure'))
        self.assertIn('supervisor_result_accepted', events)
        self.assertLess(events.index('cleanup'), events.index('supervisor_result_accepted'))

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_parent_retains_contained_result_when_journal_crosses_hard_deadline(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
        self.intent()
        ctx = multiprocessing.get_context('fork')
        phases = []
        cleanup = []
        entry_path = Path(self.tmp.name) / 'hard-entry'
        journal_path = Path(self.tmp.name) / 'hard-journal-open'
        original_open = SettlementJournal.open_existing

        def observed_open(*args, **kwargs):
            journal_path.write_text(str(time.monotonic()))
            return original_open(*args, **kwargs)

        def worker(db_path, handler, command, lease, now, channel, *args):
            process._send_packet(channel, {'kind': 'worker_ready'})
            process._receive_packet(channel)
            start = time.monotonic()
            entry_path.write_text(str(start))
            envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
            process._send_packet(channel, {'kind': 'worker_entered', 'budget_envelope': envelope,
                'deadline_monotonic': start + .04, 'hard_deadline_monotonic': start + .09,
                'started_at': time.time()})
            process._send_packet(channel, {'kind': 'worker_returned', 'outcome_json': '{"kind":"ok"}',
                                           'completed_monotonic': time.monotonic()})
            process._send_packet(channel, {'kind': 'worker_completed', 'outcome_json': '{"kind":"ok"}'})
            return 0

        with contextlib.closing(sqlite3.connect(self.binding['path'], isolation_level=None)) as lock, lock:
            lock.execute('BEGIN IMMEDIATE')
            with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
                 patch.object(process, '_worker_entry', worker), \
                 patch.object(SettlementJournal, 'open_existing', side_effect=observed_open):
                result = process.invoke_process_handler(db_path='unused', handler=None,
                    command=SimpleNamespace(timeout_seconds=5), lease=IDENTITY, now=None,
                    start_timeout=5, settlement_binding=self.binding,
                    on_phase=lambda phase, details: phases.append((phase, details)),
                    on_cleanup_confirmed=lambda: cleanup.append(True))
            lock.rollback()
        self.assertEqual(result['kind'], 'ok', result)
        self.assertEqual(cleanup, [True])
        self.assertLess(float(journal_path.read_text()), float(entry_path.read_text()) + .09)
        self.assertGreaterEqual(time.monotonic(), float(entry_path.read_text()) + .09)
        handoff = next(details for phase, details in phases if phase == 'supervisor_outcome_observed')
        self.assertEqual((handoff['state'], handoff['reason']), ('unknown', 'journal_handoff_pending'))

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_parent_preserves_explicit_post_containment_control_failure(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, BudgetClockUnknownError, sample_clock
        self.intent()
        ctx = multiprocessing.get_context('fork')
        original_send = process._send_packet

        def send_with_control_failure(channel, packet):
            if packet.get('kind') == 'handler_completed':
                raise BudgetClockUnknownError('simulated final transport clock failure')
            return original_send(channel, packet)

        def worker(db_path, handler, command, lease, now, channel, *args):
            original_send(channel, {'kind': 'worker_ready'})
            process._receive_packet(channel)
            start = time.monotonic()
            envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
            original_send(channel, {'kind': 'worker_entered', 'budget_envelope': envelope,
                'deadline_monotonic': start + .5, 'hard_deadline_monotonic': start + 2,
                'started_at': time.time()})
            original_send(channel, {'kind': 'worker_returned', 'outcome_json': '{"kind":"ok"}',
                                    'completed_monotonic': time.monotonic()})
            original_send(channel, {'kind': 'worker_completed', 'outcome_json': '{"kind":"ok"}'})
            return 0

        with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
             patch.object(process, '_worker_entry', worker), \
             patch.object(process, '_send_packet', send_with_control_failure):
            result = process.invoke_process_handler(db_path='unused', handler=None,
                command=SimpleNamespace(timeout_seconds=5), lease=IDENTITY, now=None,
                start_timeout=5, settlement_binding=self.binding)
        self.assertEqual(result['kind'], 'error', result)
        self.assertEqual(result['code'], 'budget_clock_unknown')
        self.assertTrue(result['control_error'])
        self.assertIn('simulated final transport clock failure', result['message'])

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_parent_clock_failure_reports_already_received_pending_outcome(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, BudgetClockUnknownError, sample_clock
        self.intent()
        ctx = multiprocessing.get_context('fork')
        phases = []
        cleanup = []
        original_wait = process._wait_packet
        received = [False]

        def wait_with_clock_failure(*args, **kwargs):
            if received[0]:
                raise BudgetClockUnknownError('simulated parent clock failure')
            packet, deadline = original_wait(*args, **kwargs)
            if type(packet) is dict and packet.get('kind') == 'handler_contained':
                received[0] = True
            return packet, deadline

        def worker(db_path, handler, command, lease, now, channel, *args):
            process._send_packet(channel, {'kind': 'worker_ready'})
            process._receive_packet(channel)
            start = time.monotonic()
            envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
            process._send_packet(channel, {'kind': 'worker_entered', 'budget_envelope': envelope,
                'deadline_monotonic': start + .5, 'hard_deadline_monotonic': start + 2,
                'started_at': time.time()})
            process._send_packet(channel, {'kind': 'worker_returned', 'outcome_json': '{"kind":"ok"}',
                                           'completed_monotonic': time.monotonic()})
            process._send_packet(channel, {'kind': 'worker_completed', 'outcome_json': '{"kind":"ok"}'})
            return 0

        with contextlib.closing(sqlite3.connect(self.binding['path'], isolation_level=None)) as lock, lock:
            lock.execute('BEGIN IMMEDIATE')
            with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
                 patch.object(process, '_worker_entry', worker), \
                 patch.object(process, '_wait_packet', wait_with_clock_failure):
                result = process.invoke_process_handler(db_path='unused', handler=None,
                    command=SimpleNamespace(timeout_seconds=5), lease=IDENTITY, now=None,
                    start_timeout=5, settlement_binding=self.binding,
                    on_phase=lambda phase, details: phases.append((phase, details)),
                    on_cleanup_confirmed=lambda: cleanup.append(True))
            lock.rollback()
        self.assertEqual((result['kind'], result['code']), ('error', 'budget_clock_unknown'))
        self.assertIn('simulated parent clock failure', result['message'])
        self.assertEqual(cleanup, [True])
        handoff = next(details for phase, details in phases if phase == 'supervisor_outcome_observed')
        self.assertEqual((handoff['state'], handoff['reason'], handoff['outcome_json']),
                         ('unknown', 'journal_handoff_pending', '{"kind":"ok"}'))

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_successful_final_handoff_does_not_report_stale_unknown(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
        self.intent()
        ctx = multiprocessing.get_context('fork')
        phases = []
        lease = ExecutionLease('execution', 'lease', 'owner', 3, 2, 9999999999, 1)

        def worker(db_path, handler, command, lease, now, channel, *args):
            process._send_packet(channel, {'kind': 'worker_ready'})
            process._receive_packet(channel)
            start = time.monotonic()
            envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
            process._send_packet(channel, {'kind': 'worker_entered', 'budget_envelope': envelope,
                'deadline_monotonic': start + .5, 'hard_deadline_monotonic': start + 2,
                'started_at': time.time()})
            process._send_packet(channel, {'kind': 'worker_returned', 'outcome_json': '{"kind":"ok"}',
                                           'completed_monotonic': time.monotonic()})
            process._send_packet(channel, {'kind': 'worker_completed', 'outcome_json': '{"kind":"ok"}'})
            return 0

        with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
             patch.object(process, '_worker_entry', worker):
            result = process.invoke_process_handler(db_path='unused', handler=None,
                command=SimpleNamespace(timeout_seconds=5), lease=lease, now=None,
                start_timeout=5, settlement_binding=self.binding,
                on_phase=lambda phase, details: phases.append((phase, details)))
        self.assertEqual(result['kind'], 'ok', result)
        self.assertFalse(any(phase == 'supervisor_outcome_observed' for phase, _ in phases))
        observed = [note for note in self.journal.inspect_notes('execution', timeout_seconds=1)['notes']
                    if note['phase'] == 'supervisor_outcome_observed']
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]['evidence']['outcome_json'], '{"kind":"ok"}')
        notes = self.journal.inspect_notes('execution', timeout_seconds=1)['notes']
        disposition = next(note for note in notes if note['phase'] == 'supervisor_disposition_observed')
        self.assertEqual(disposition['identity'], IDENTITY)
        self.assertEqual(disposition['evidence']['lease'], lease.to_dict())
        self.assertEqual(disposition['evidence']['worker_return'], 'timely')
        self.assertEqual(disposition['evidence']['parent_decision'], 'unknown')
        self.assertEqual(disposition['evidence']['settlement'], 'unknown')
        self.assertEqual(disposition['evidence']['supervisor_reap'], 'unknown')
        self.assertEqual(disposition['evidence']['worker_tree_cleanup'], 'confirmed')
        self.assertEqual(self.journal.pending(timeout_seconds=1), [])

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_raw_worker_packet_is_unchanged_when_supervisor_adds_cleanup_diagnostics(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
        self.intent()
        ctx = multiprocessing.get_context('fork')
        lease = ExecutionLease('execution', 'lease', 'owner', 3, 2, 9999999999, 1)
        raw = '{"kind":"ok","value":7}'

        def worker(db_path, handler, command, lease, now, channel, *args):
            process._send_packet(channel, {'kind': 'worker_ready'})
            process._receive_packet(channel)
            start = time.monotonic()
            envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
            process._send_packet(channel, {'kind': 'worker_entered', 'budget_envelope': envelope,
                'deadline_monotonic': start + .5, 'hard_deadline_monotonic': start + 2,
                'started_at': time.time()})
            process._send_packet(channel, {'kind': 'worker_returned', 'outcome_json': raw,
                                           'completed_monotonic': time.monotonic()})
            time.sleep(1)
            return 0

        with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
             patch.object(process, '_worker_entry', worker), \
             patch.object(process, '_stop_flush_descendants', return_value=False):
            result = process.invoke_process_handler(db_path='unused', handler=None,
                command=SimpleNamespace(timeout_seconds=5), lease=lease, now=None,
                start_timeout=5, settlement_binding=self.binding)
        self.assertEqual(result['kind'], 'ok')
        notes = self.journal.inspect_notes('execution', timeout_seconds=1)['notes']
        observed = next(note for note in notes if note['phase'] == 'supervisor_outcome_observed')
        disposition = next(note for note in notes if note['phase'] == 'supervisor_disposition_observed')
        self.assertEqual(observed['evidence']['outcome_json'], raw)
        amended = json.loads(disposition['evidence']['supervisor_final_outcome_json'])
        self.assertEqual(amended['telemetry_flush']['state'], 'unknown')
        self.assertEqual(disposition['evidence']['worker_return'], 'timely')

    @unittest.skipUnless(hasattr(os, 'fork') and os.path.isdir('/proc'), 'requires Linux process containment')
    def test_late_packet_containment_precedes_busy_journal_handoff(self):
        from dispatcher_sdk.execution_kernel import _process_runtime as process
        from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
        self.intent()
        ctx = multiprocessing.get_context('fork')
        child_path = Path(self.tmp.name) / 'child-pid'
        observation_path = Path(self.tmp.name) / 'at-journal-open'
        original_open = SettlementJournal.open_existing

        def observe_open(*args, **kwargs):
            pid = int(child_path.read_text())
            observation_path.write_text('alive' if Path('/proc', str(pid)).exists() else 'reaped')
            return original_open(*args, **kwargs)

        def worker(db_path, handler, command, lease, now, channel, *args):
            process._send_packet(channel, {'kind': 'worker_ready'})
            process._receive_packet(channel)
            start = time.monotonic()
            envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
            process._send_packet(channel, {'kind': 'worker_entered', 'budget_envelope': envelope,
                'deadline_monotonic': start + .3, 'hard_deadline_monotonic': start + 1,
                'started_at': time.time()})
            pid = os.fork()
            if pid == 0:
                time.sleep(10)
                os._exit(0)
            child_path.write_text(str(pid))
            process._send_packet(channel, {'kind': 'worker_returned', 'outcome_json': '{"kind":"ok"}',
                                           'completed_monotonic': start + .5})
            time.sleep(10)
            return 0

        with contextlib.closing(sqlite3.connect(self.binding['path'], isolation_level=None)) as lock, lock:
            lock.execute('BEGIN IMMEDIATE')
            with patch.object(process.multiprocessing, 'get_context', return_value=ctx), \
                 patch.object(process, '_worker_entry', worker), \
                 patch.object(SettlementJournal, 'open_existing', side_effect=observe_open):
                result = process.invoke_process_handler(db_path='unused', handler=None,
                    command=SimpleNamespace(timeout_seconds=5), lease=IDENTITY, now=None,
                    start_timeout=5, settlement_binding=self.binding)
            lock.rollback()
        self.assertEqual(result['kind'], 'timeout', result)
        self.assertEqual(observation_path.read_text(), 'reaped')

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_worker_tree_receipt_survives_supervisor_crash_before_delivery(self):
        self.intent()
        ctx = multiprocessing.get_context('fork')
        receiver, sender = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=supervisor_crashes_before_delivery, args=(sender, self.binding, False, True))
        proc.start()
        sender.close()
        proc.join(10)
        if proc.is_alive():
            proc.terminate()
            proc.join()
            self.fail('supervisor did not exit')
        self.assertEqual(proc.exitcode, 61)
        row = SettlementJournal.open_existing(**self.binding, timeout_seconds=1).scan_supervisor_cleanup(timeout_seconds=1)['registrations'][0]
        self.assertEqual((row['worker_tree_cleanup'], row['cleanup'], row['outcome']),
                         ('confirmed', 'unknown', 'unknown'))
        receiver.close()

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_clock_failure_after_packet_cannot_erase_observation(self):
        self.intent()
        ctx = multiprocessing.get_context('fork')
        receiver, sender = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=supervisor_crashes_before_delivery, args=(sender, self.binding, True))
        proc.start()
        sender.close()
        proc.join(10)
        if proc.is_alive():
            proc.terminate()
            proc.join()
            self.fail('supervisor did not exit')
        self.assertEqual(proc.exitcode, 61)
        notes = self.journal.inspect_notes('execution', timeout_seconds=1)['notes']
        observed = [note for note in notes if note['phase'] == 'supervisor_outcome_observed']
        self.assertEqual(observed[0]['evidence']['outcome_json'], RAW)
        receiver.close()

    @unittest.skipUnless(hasattr(os, 'fork'), 'requires POSIX fork')
    def test_supervisor_packet_survives_crash_before_delivery(self):
        self.intent()
        ctx = multiprocessing.get_context('fork')
        receiver, sender = ctx.Pipe(duplex=False)
        proc = ctx.Process(target=supervisor_crashes_before_delivery, args=(sender, self.binding))
        proc.start()
        sender.close()
        proc.join(10)
        if proc.is_alive():
            proc.terminate()
            proc.join()
            self.fail('supervisor did not exit')
        self.assertEqual(proc.exitcode, 61)
        notes = SettlementJournal.open_existing(**self.binding, timeout_seconds=1).inspect_notes('execution', timeout_seconds=1)['notes']
        observed = [note for note in notes if note['phase'] == 'supervisor_outcome_observed']
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]['identity'], IDENTITY)
        self.assertEqual(observed[0]['evidence']['outcome_json'], RAW)
        receiver.close()
