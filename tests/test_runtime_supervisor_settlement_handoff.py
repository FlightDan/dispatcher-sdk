"""Isolated settlement ownership checks without registry initialization."""
from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time
import tempfile
import unittest
from unittest.mock import Mock, patch

from dispatcher_sdk.execution_kernel.contracts import ExecutionLease
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel import _windows_runtime
from dispatcher_sdk.execution_kernel.runtime import Runtime
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal


def windows_test_handler(payload, context):
    return payload


class SupervisorSettlementHandoffTests(unittest.TestCase):
    def runtime(self):
        runtime = object.__new__(Runtime)
        runtime.isolation_mode = 'process'
        runtime.kernel = Mock()
        runtime.kernel._control_lock.return_value = nullcontext()
        runtime.kernel.effect_ids_for_attempt.return_value = []
        runtime.kernel._complete_sdk_result.return_value = SimpleNamespace(state='failed', revision=2)
        runtime._settlement_journal = Mock()
        runtime._settlement_journal.record.side_effect = lambda lease, result, evidence, **kwargs: {'evidence': evidence}
        runtime._pending_settlements = Mock()
        runtime._pending_settlements.retain.return_value = ('exec', 1, 2)
        runtime._received_budget_checkpoints = Mock(return_value=[])
        runtime._finish_received_budget_checkpoints = Mock()
        runtime._outcome_result = Mock(return_value=SimpleNamespace(result_id='result', to_dict=lambda: {}))
        runtime._activity_phase = Mock()
        runtime._lifecycle_lock = threading.RLock()
        runtime._diagnostic_pending_lock = threading.Lock()
        runtime._diagnostic_unknown_handoffs = set()
        runtime._diagnostic_handoff_cursor = None
        runtime._closed = False
        return runtime

    def test_foreground_releases_only_accepted_and_reaped_execution(self):
        lease = ExecutionLease('exec', 'lease', 'owner', 2, 1, 9999999999, 1)
        snapshot = SimpleNamespace(command=SimpleNamespace(execution_id='exec'), started_at=1)
        cases = [
            ({'kind': 'error', '_sdk_supervisor_completion_confirmed': True}, True),
            ({'kind': 'error', '_sdk_supervisor_completion_confirmed': False}, False),
            ({'kind': 'error', '_sdk_supervisor_completion_confirmed': True, 'control_error': True}, False),
            ({'kind': 'timeout', '_sdk_supervisor_completion_confirmed': True}, True),
            ({'kind': 'timeout', '_sdk_supervisor_completion_confirmed': False}, False),
        ]
        for outcome, expected in cases:
            with self.subTest(outcome=outcome):
                runtime = self.runtime()
                runtime._settle_outcome_active(snapshot, lease, outcome, object())
                call = runtime.kernel._complete_sdk_result.call_args
                self.assertEqual(call.kwargs['supervisor_cleanup_confirmed'], expected)
                evidence = runtime._settlement_journal.record.call_args.kwargs['evidence']
                self.assertEqual('supervisor_completion' in evidence, expected)

    def test_windows_mocked_job_only_accepts_timed_return_after_close(self):
        for mode in ('timely', 'missing_return', 'close_failure', 'watchdog_timeout',
                     'watchdog_clock_unknown', 'watchdog_startup_expired', 'watchdog_startup_returned',
                     'watchdog_delayed_return', 'watchdog_unreadable', 'timestamp_missing', 'timestamp_invalid', 'timestamp_nan'):
            with self.subTest(mode=mode):
                roots, events, watchdogs = [], [], []
                command = ExecutionCommandV2('exec', 'idempotency', 'revision', 'run', None,
                                             'handler', 1, RetryPolicy(), 10, {})
                lease = ExecutionLease('exec', 'lease', 'owner', 2, 1, 9999999999, 1)
                def create(api, args):
                    roots.append(Path(args[-1]))
                    return None, None
                class Handle:
                    revocation_reason = None
                    exitcode = 0
                    def __init__(self, *args): pass
                    def resume(self):
                        start = time.monotonic()
                        envelope = BudgetEnvelope((), sample_clock(), time.time()).to_dict()
                        (roots[0] / 'ready').write_text(json.dumps({'worker_pid': 7}))
                        (roots[0] / 'entered.json').write_text(json.dumps({'worker_pid': 7,
                            'budget_envelope': envelope, 'deadline_monotonic': start + 5,
                            'hard_deadline_monotonic': start + 10, 'started_at': time.time()}))
                        if mode != 'missing_return' and (not mode.startswith('watchdog_') or
                                                         mode == 'watchdog_startup_returned'):
                            completed = {'outcome_json': '{"kind":"ok"}'}
                            if mode != 'timestamp_missing':
                                completed['completed_monotonic'] = ({'timestamp_invalid': 'invalid',
                                    'timestamp_nan': float('nan')}.get(mode, time.monotonic()))
                            (roots[0] / 'returned.json').write_text(json.dumps(completed))
                        if not mode.startswith('watchdog_') or mode == 'watchdog_startup_returned':
                            (roots[0] / 'outcome.json').write_text('{"kind":"ok"}')
                    def preserve_worker(self, pid): pass
                    def stop_descendants(self, until): return True
                    def exited(self):
                        if mode.startswith('watchdog_'):
                            if mode in ('watchdog_delayed_return', 'watchdog_unreadable'):
                                (roots[0] / 'returned.json').write_text(json.dumps({
                                    'completed_monotonic': time.monotonic(), 'outcome_json': '{"kind":"ok"}'}))
                            watchdogs[0].expired = True
                            watchdogs[0].business_cutoff = not mode.startswith('watchdog_startup_')
                            if mode == 'watchdog_clock_unknown':
                                watchdogs[0].clock_error = BudgetClockUnknownError('clock unknown')
                        return False
                    def terminate(self): events.append('terminate'); return True
                    def close(self):
                        events.append('close')
                        if mode == 'close_failure': raise OSError('close failed')
                class Watchdog:
                    expired = False
                    cleanup = False
                    clock_error = None
                    business_phase = False
                    business_cutoff = False
                    def __init__(self, *args):
                        self.deadline = time.monotonic() + 10
                        watchdogs.append(self)
                    def business_deadline(self, seconds, **kwargs):
                        if mode.startswith('watchdog_startup_'):
                            self.expired = True
                            return time.monotonic() - 1
                        self.business_phase = kwargs.get('entered', False)
                        return kwargs.get('deadline', time.monotonic() + 5)
                    def hard_deadline_bound(self, deadline): return deadline
                    def cleanup_deadline(self, deadline): self.cleanup, self.deadline = True, deadline
                    def snapshot(self): return None
                    def close(self): pass
                read_text = Path.read_text
                def read_publication(path, *args, **kwargs):
                    if mode == 'watchdog_unreadable' and path.name == 'returned.json':
                        raise PermissionError('unreadable')
                    return read_text(path, *args, **kwargs)
                with patch.object(Path, 'read_text', autospec=True, side_effect=read_publication), \
                     patch.object(_windows_runtime, '_WinAPI', return_value=object()), \
                     patch.object(_windows_runtime, '_create_suspended', side_effect=create), \
                     patch.object(_windows_runtime, 'WindowsProcessHandle', Handle), \
                     patch.object(_windows_runtime, '_Watchdog', Watchdog):
                    kwargs = dict(db_path='/unused/db', handler=windows_test_handler, command=command,
                        lease=lease, now=None, start_timeout=5,
                        on_cleanup_confirmed=lambda: events.append('cleanup'),
                        on_phase=lambda phase, details: events.append(phase))
                    if mode == 'close_failure':
                        with self.assertRaisesRegex(OSError, 'close failed'):
                            _windows_runtime.invoke_windows_handler(**kwargs)
                    else:
                        result = _windows_runtime.invoke_windows_handler(**kwargs)
                        self.assertEqual(result['kind'], {'watchdog_timeout': 'timeout',
                            'watchdog_clock_unknown': 'error', 'watchdog_startup_expired': 'timeout',
                            'watchdog_startup_returned': 'error', 'watchdog_delayed_return': 'error', 'watchdog_unreadable': 'error',
                            'timestamp_missing': 'error',
                            'timestamp_invalid': 'error', 'timestamp_nan': 'error'}.get(mode, 'ok'))
                        if mode == 'watchdog_clock_unknown':
                            self.assertEqual(result['code'], 'budget_clock_unknown')
                        if mode.startswith('timestamp_'):
                            self.assertEqual(result['code'], 'handler_completion_time_unknown')
                        if mode in ('watchdog_startup_returned', 'watchdog_delayed_return', 'watchdog_unreadable'):
                            self.assertEqual(result['code'], 'handler_completion_disposition_unknown')
                            self.assertTrue(result['control_error'])
                        if mode in ('watchdog_startup_returned', 'watchdog_delayed_return', 'watchdog_unreadable') or mode.startswith('timestamp_'):
                            runtime = self.runtime()
                            snapshot = SimpleNamespace(command=command, started_at=1)
                            with tempfile.TemporaryDirectory() as tmp:
                                path, kernel = Path(tmp) / 'settlement.db', Path(tmp) / 'kernel.db'
                                runtime._settlement_journal = SettlementJournal(path, source_id='store', kernel_path=kernel, timeout_seconds=1)
                                self.assertIs(runtime._settle_outcome_active(snapshot, lease, result, object()), snapshot)
                                runtime._outcome_result.assert_not_called()
                                runtime.kernel._complete_sdk_result.assert_not_called()
                                reopened = SettlementJournal.open_readonly(path, source_id='store', kernel_path=kernel, timeout_seconds=1)
                                deferred = reopened.pending(timeout_seconds=1)[0]['deferred']
                                self.assertEqual(deferred['kind'], 'completion_time_unknown')
                                self.assertEqual(deferred['outcome']['supervisor_return_observation'],
                                                 result['supervisor_return_observation'])
                                runtime._settlement_journal = SettlementJournal(path, source_id='store', kernel_path=kernel, timeout_seconds=1)
                                runtime._settlement_lock = threading.RLock()
                                runtime._settlement_inflight_lock = threading.Lock()
                                runtime._settlement_inflight = set()
                                runtime._persist_pending_settlements = Mock(return_value=[])
                                runtime._drain_recovery_completion_readers = Mock()
                                runtime._recover_script_output = Mock()
                                runtime._bounded_lifecycle = Mock(return_value=nullcontext())
                                runtime.kernel._positive_duration.return_value = 1
                                runtime.kernel.get.return_value = SimpleNamespace(attempt=lease.attempt,
                                    fence=lease.fence, state='running')
                                reports = runtime.recover_completions(timeout_seconds=1)
                                self.assertEqual(reports[0]['state'], 'unknown')
                                runtime.kernel._complete_sdk_result.assert_not_called()
                if mode in ('timely', 'watchdog_timeout'):
                    self.assertLess(events.index('close'), events.index('supervisor_result_accepted'))
                    self.assertLess(events.index('cleanup'), events.index('supervisor_result_accepted'))
                else:
                    self.assertNotIn('supervisor_result_accepted', events)

    def test_recovery_uses_only_original_durable_exact_proof(self):
        lease = ExecutionLease('exec', 'lease', 'owner', 2, 1, 9999999999, 1)
        proof = {'cleanup': 'confirmed', 'source': 'runtime_supervisor_reaped', 'result': 'accepted'}
        for evidence, expected in (({'supervisor_completion': proof}, True),
                                   ({}, False),
                                   ({'supervisor_completion': {**proof, 'source': 'other'}}, False)):
            with self.subTest(evidence=evidence):
                runtime = self.runtime()
                runtime.kernel._positive_duration.return_value = 1
                runtime._settlement_lock = threading.RLock()
                runtime._settlement_inflight_lock = threading.Lock()
                runtime._settlement_inflight = set()
                runtime._persist_pending_settlements = Mock(return_value=[])
                runtime._drain_recovery_completion_readers = Mock()
                runtime._recover_script_output = Mock()
                runtime._bounded_lifecycle = Mock(return_value=nullcontext())
                runtime._settlement_journal.next_pending_round_robin.side_effect = [{'identity': {
                    'execution_id': 'exec', 'attempt': 1, 'fence': 2}, 'lease': lease.to_dict(),
                    'deferred': None, 'result': {}, 'evidence': evidence, 'created_at': 1.0}, None]
                with patch('dispatcher_sdk.execution_kernel.runtime.ExecutionResultV2.from_dict',
                           return_value=SimpleNamespace(result_id='result')):
                    runtime.recover_completions(timeout_seconds=1)
                call = runtime.kernel._complete_sdk_result.call_args
                self.assertIsNotNone(call)
                self.assertEqual(call.kwargs['supervisor_cleanup_confirmed'], expected)

    def test_windows_expired_startup_bound_never_becomes_business_cutoff(self):
        for established in (False, True):
            with self.subTest(business_phase_established=established):
                watchdog = object.__new__(_windows_runtime._Watchdog)
                watchdog.lock = threading.Lock()
                watchdog.changed = threading.Event()
                watchdog.expired = False
                watchdog.business_phase = established
                watchdog.business_cutoff = False
                watchdog.deadline = time.monotonic() - 1
                watchdog.business_deadline(5, deadline=time.monotonic() + 5)
                self.assertTrue(watchdog.expired)
                self.assertEqual(watchdog.business_cutoff, established)

    def test_windows_provisional_deadline_expiry_is_not_entry_cutoff(self):
        watchdog = object.__new__(_windows_runtime._Watchdog)
        watchdog.lock = threading.Lock()
        watchdog.changed = threading.Event()
        watchdog.expired = False
        watchdog.business_phase = False
        watchdog.business_cutoff = False
        watchdog.envelope = None
        watchdog.deadline = time.monotonic() + 5
        watchdog.inherited_work_deadline = float('inf')
        watchdog._retain_sample_locked = lambda: None
        watchdog.business_deadline(5)
        self.assertFalse(watchdog.business_phase)
        watchdog.deadline = time.monotonic() - 1
        watchdog.business_deadline(5, deadline=time.monotonic() + 5, entered=True)
        self.assertTrue(watchdog.expired)
        self.assertFalse(watchdog.business_phase)
        self.assertFalse(watchdog.business_cutoff)


if __name__ == '__main__':
    unittest.main()
