import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel.contracts import ExecutionLease
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal


class SupervisorCleanupScanTests(unittest.TestCase):
    def test_native_admission_timeout_reports_not_invoked_on_both_platforms(self):
        from dispatcher_sdk.execution_kernel import _process_runtime, _windows_runtime
        for invoke in (_process_runtime.invoke_process_handler, _windows_runtime.invoke_windows_handler):
            with self.subTest(invoke=invoke.__name__):
                phases = []
                with patch.object(_process_runtime._BudgetTracker, 'bound', return_value=time.monotonic() - 1):
                    outcome = invoke(db_path='kernel.db', handler=cleanup_handler, command=None,
                                     lease=None, now=time.time, start_timeout=1,
                                     on_phase=lambda phase, details: phases.append((phase, details)))
                self.assertEqual(outcome['kind'], 'timeout')
                self.assertIn(('supervisor_not_invoked', {'source': 'runtime_pre_spawn'}), phases)

    def test_registration_commit_then_raise_resolves_exact_obligation(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.db', {'work': cleanup_handler}, isolation_mode='process')
            try:
                command = runtime.command('work', execution_id='uncertain', idempotency_key='uncertain',
                                          correlation_id='uncertain', timeout_seconds=10, payload={})
                runtime.submit(command)
                register = runtime.kernel.register_supervisor_obligation
                def commit_then_raise(*args, **kwargs):
                    register(*args, **kwargs)
                    raise OSError('lost acknowledgement')
                with patch.object(runtime.kernel, 'register_supervisor_obligation', side_effect=commit_then_raise), \
                     patch.object(runtime_module, 'invoke_process_handler') as invoke:
                    result = runtime.run_once(execution_id='uncertain')
                invoke.assert_not_called()
                obligation = runtime.kernel.inspect_supervisor_obligations('uncertain')['obligations'][0]
                self.assertEqual(obligation['resolution']['source'], 'sdk_supervisor_not_invoked')
                self.assertEqual(obligation['resolution']['result_id'], result.result.result_id)
            finally:
                runtime.close()

    def test_native_early_timeout_replays_after_budget_capture_is_finished(self):
        from dispatcher_sdk.execution_kernel import _process_runtime, _windows_runtime
        with tempfile.TemporaryDirectory() as root:
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.db', {'work': cleanup_handler}, isolation_mode='process')
            try:
                command = runtime.command('work', execution_id='replay', idempotency_key='replay',
                                          correlation_id='replay', timeout_seconds=10, payload={})
                runtime.submit(command)
                invoke = (_windows_runtime.invoke_windows_handler if os.name == 'nt'
                          else runtime_module.invoke_process_handler)
                tokens = []
                def native_with_pending_capture(**kwargs):
                    token = runtime.kernel._begin_budget_sample('replay')
                    tokens.append((token, kwargs['budget_envelope']))
                    def fail_capture(capture, envelope, **options):
                        return envelope, {'state': 'unknown', 'token': token,
                                          'captured_envelope': envelope.to_dict(), 'error': {'cause': 'busy'}}
                    with patch.object(_process_runtime._BudgetTracker, 'bound', return_value=time.monotonic() - 1), \
                         patch.object(_process_runtime, '_finish_budget_capture', side_effect=fail_capture), \
                         patch.object(_windows_runtime, '_finish_budget_capture', side_effect=fail_capture):
                        return invoke(**kwargs)
                with patch.object(runtime_module, 'invoke_process_handler', side_effect=native_with_pending_capture), \
                     patch('dispatcher_sdk.execution_kernel._windows_runtime.invoke_windows_handler', side_effect=native_with_pending_capture), \
                     patch.object(runtime, '_finish_received_budget_checkpoints', side_effect=TimeoutError('busy')) as finish:
                    runtime.run_once(execution_id='replay')
                    record = runtime._settlement_journal.inspect('replay', timeout_seconds=1)[0]
                    self.assertEqual(record['evidence']['supervisor_not_invoked']['process_creation'], 'not_invoked')
                    self.assertTrue(runtime._received_budget_checkpoints(record['evidence']))
                    finish.assert_called()
                    self.assertEqual(runtime.kernel.inspect_supervisor_obligations('replay')['obligations'][0]['state'], 'unresolved')
                runtime.recover_completions(timeout_seconds=1)
                obligation = runtime.kernel.inspect_supervisor_obligations('replay')['obligations'][0]
                self.assertEqual(obligation['resolution']['source'], 'sdk_supervisor_not_invoked')
            finally:
                runtime.close()

    def test_unknown_completion_time_retains_pre_spawn_proof_for_replay(self):
        from dispatcher_sdk.execution_kernel.context import HandlerContext, HandlerEffects
        from dispatcher_sdk.execution_kernel._process_runtime import _capture_completion_time
        with tempfile.TemporaryDirectory() as root:
            runtime = Kernel.open_sqlite(Path(root) / 'kernel.db', {'work': cleanup_handler}, isolation_mode='process')
            try:
                command = runtime.command('work', execution_id='clock', idempotency_key='clock',
                                          correlation_id='clock', timeout_seconds=10, payload={},
                                          retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0,
                                                                   backoff_multiplier=1, max_backoff_seconds=0,
                                                                   retry_timeouts=True))
                runtime.submit(command)
                retained = []
                def unknown_completion(**kwargs):
                    lease, envelope = kwargs['lease'], kwargs['budget_envelope']
                    context = HandlerContext(command, lease, HandlerEffects(runtime.kernel, lease, lambda: True),
                                             budget_envelope=envelope)
                    token = runtime.kernel._begin_budget_sample('clock')
                    outcome = {'kind': 'error', 'code': 'admission', 'message': 'not started',
                               'retryable': True, 'effect_ids': [], 'details': {},
                               'budget_envelope': envelope.to_dict()}
                    _capture_completion_time(outcome, context)
                    context._drain_completion_readers(time.monotonic() + 1)
                    context.close()
                    self.assertFalse(outcome['completion_time_known'])
                    kwargs['on_phase']('supervisor_not_invoked', {'source': 'runtime_pre_spawn'})
                    retained.append((token, envelope))
                    return outcome
                with patch.object(runtime_module, 'invoke_process_handler', side_effect=unknown_completion), \
                     patch('dispatcher_sdk.execution_kernel._windows_runtime.invoke_windows_handler', side_effect=unknown_completion):
                    runtime.run_once(execution_id='clock')
                record = runtime._settlement_journal.inspect('clock', timeout_seconds=1)[0]
                self.assertEqual(record['evidence']['supervisor_not_invoked']['process_creation'], 'not_invoked')
                self.assertEqual(runtime.kernel.inspect_supervisor_obligations('clock')['obligations'][0]['state'], 'unresolved')
                runtime.kernel._finish_budget_sample(retained[0][0], 'clock', retained[0][1])
                settle = runtime._settlement_journal.settle
                def fail_recorded(record, state, evidence, **kwargs):
                    if state == 'recorded':
                        raise TimeoutError('journal acknowledgement lost')
                    return settle(record, state, evidence, **kwargs)
                with patch.object(runtime._settlement_journal, 'settle', side_effect=fail_recorded):
                    runtime.recover_completions(timeout_seconds=1)
                self.assertEqual(runtime.kernel.get('clock').state, 'queued')
                pending = runtime._settlement_journal.inspect('clock', timeout_seconds=1)[0]
                self.assertEqual(pending['state'], 'pending')
                result_id = pending['evidence']['resolved_result']['result_id']
                retry = runtime.kernel.claim_and_start('retry-owner', execution_id='clock')
                self.assertGreater(retry.attempt, pending['identity']['attempt'])
                runtime.recover_completions(timeout_seconds=1)
                obligation = runtime.kernel.inspect_supervisor_obligations('clock')['obligations'][0]
                self.assertEqual(obligation['resolution']['source'], 'sdk_supervisor_not_invoked')
                self.assertEqual(obligation['resolution']['result_id'], result_id)
                replayed = runtime._settlement_journal.inspect('clock', timeout_seconds=1)[0]
                self.assertEqual(replayed['state'], 'recorded')
                self.assertEqual(replayed['evidence']['result_id'], result_id)
            finally:
                runtime.close()

    def test_post_registration_timeout_resolves_exact_obligation_without_spawn(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Kernel.open_sqlite(Path(root) / "kernel.db", {"work": cleanup_handler}, isolation_mode="process")
            try:
                command = runtime.command("work", execution_id="timeout", idempotency_key="timeout",
                                          correlation_id="timeout", timeout_seconds=10, payload={})
                runtime.submit(command)
                prepare = runtime._prepare_handler_admission
                register = runtime.kernel.register_supervisor_obligation
                def short_admission(lease):
                    budget, error, _ = prepare(lease)
                    return budget, error, time.monotonic() + .5
                def slow_registration(*args, **kwargs):
                    result = register(*args, **kwargs)
                    time.sleep(.55)
                    return result
                with patch.object(runtime, "_prepare_handler_admission", side_effect=short_admission), \
                     patch.object(runtime.kernel, "register_supervisor_obligation", side_effect=slow_registration), \
                     patch.object(runtime_module, "invoke_process_handler") as invoke:
                    result = runtime.run_once(execution_id="timeout")
                invoke.assert_not_called()
                obligation = runtime.kernel.inspect_supervisor_obligations("timeout")["obligations"][0]
                self.assertEqual(obligation["state"], "resolved")
                self.assertEqual(obligation["resolution"]["source"], "sdk_supervisor_not_invoked")
                self.assertEqual(obligation["resolution"]["result_id"], result.result.result_id)
                self.assertEqual((obligation["attempt"], obligation["fence"]),
                                 (result.result.attempt, result.result.fence))
            finally:
                runtime.close()

    def test_ambiguous_spawn_failure_keeps_obligation_unresolved(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Kernel.open_sqlite(Path(root) / "kernel.db", {"work": cleanup_handler}, isolation_mode="process")
            try:
                command = runtime.command("work", execution_id="ambiguous", idempotency_key="ambiguous",
                                          correlation_id="ambiguous", timeout_seconds=10, payload={})
                runtime.submit(command)
                with patch.object(runtime_module, "invoke_process_handler", side_effect=OSError("ambiguous")), \
                     patch("dispatcher_sdk.execution_kernel._windows_runtime.invoke_windows_handler", side_effect=OSError("ambiguous")):
                    with self.assertRaises(OSError):
                        runtime.run_once(execution_id="ambiguous")
                obligation = runtime.kernel.inspect_supervisor_obligations("ambiguous")["obligations"][0]
                self.assertEqual(obligation["state"], "unresolved")
            finally:
                runtime.close()

    def test_reopen_pages_exact_attempts_and_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "settlement.db"
            kernel = Path(root) / "kernel.db"
            journal = SettlementJournal(path, source_id="store", kernel_path=kernel, timeout_seconds=1)
            first = {"execution_id": "exec", "attempt": 1, "fence": 2}
            second = {"execution_id": "exec", "attempt": 2, "fence": 3}
            journal.note(first, "supervisor_registered", {}, timeout_seconds=1)
            journal.note(second, "supervisor_spawn_intent", {}, timeout_seconds=1)
            journal.note(first, "process_cleanup", {"state": "confirmed", "source": "runtime_supervisor_reaped"}, timeout_seconds=1)
            journal = SettlementJournal.open_readonly(path, source_id="store", kernel_path=kernel, timeout_seconds=1)
            page = journal.scan_supervisor_cleanup(limit=1, timeout_seconds=1)
            self.assertTrue(page["has_more"])
            self.assertEqual(page["registrations"][0]["cleanup"], "confirmed")
            page = journal.scan_supervisor_cleanup(after=page["cursor"], limit=1, timeout_seconds=1)
            self.assertEqual(page["registrations"][0]["identity"], second)
            self.assertEqual(page["registrations"][0]["phase"], "supervisor_spawn_intent")
            self.assertEqual(page["registrations"][0]["cleanup"], "unknown")
            self.assertEqual(page["registrations"][0]["handler_entry"], "unknown")
            self.assertEqual(page["registrations"][0]["outcome"], "unknown")

    def test_restart_discovery_only_reports_exact_durable_entry_and_outcome(self):
        with tempfile.TemporaryDirectory() as root:
            path, kernel = Path(root) / "settlement.db", Path(root) / "kernel.db"
            journal = SettlementJournal(path, source_id="store", kernel_path=kernel, timeout_seconds=1)
            identity = {"execution_id": "exec", "attempt": 1, "fence": 2}
            other = {"execution_id": "exec", "attempt": 2, "fence": 3}
            journal.note(identity, "supervisor_spawn_intent", {}, timeout_seconds=1)
            journal.note(other, "handler_entered", {}, timeout_seconds=1)
            first = SettlementJournal.open_readonly(path, source_id="store", kernel_path=kernel, timeout_seconds=1)
            entry = first.scan_supervisor_cleanup(timeout_seconds=1)["registrations"][0]
            self.assertEqual((entry["handler_entry"], entry["outcome"]), ("unknown", "unknown"))
            journal.note(identity, "handler_entered", {}, timeout_seconds=1)
            lease = ExecutionLease("exec", "lease", "owner", 2, 1, 9999999999, 1)
            journal.record(lease, {"kind": "deferred", "outcome": {"kind": "error"}}, timeout_seconds=1)
            entry = first.scan_supervisor_cleanup(timeout_seconds=1)["registrations"][0]
            self.assertEqual((entry["handler_entry"], entry["outcome"], entry["cleanup"]),
                             ("observed", "durable", "unknown"))

    def test_real_process_records_intent_before_registration(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Kernel.open_sqlite(Path(root) / "kernel.db", {"work": cleanup_handler}, isolation_mode="process")
            try:
                command = runtime.command("work", execution_id="process", idempotency_key="process",
                                          correlation_id="process", timeout_seconds=10, payload={})
                runtime.submit(command)
                runtime.run_once(execution_id="process")
                journal = runtime._settlement_journal
                notes = journal.inspect_notes("process", timeout_seconds=1)["notes"]
                phases = [note["phase"] for note in notes]
                self.assertLess(phases.index("supervisor_spawn_intent"), phases.index("supervisor_registered"))
                intent = next(note for note in notes if note["phase"] == "supervisor_spawn_intent")
                self.assertGreater(intent["identity"]["attempt"], 0)
                self.assertGreater(intent["identity"]["fence"], 0)
                entry = next(item for item in journal.scan_supervisor_cleanup(timeout_seconds=1)["registrations"]
                             if item["identity"] == intent["identity"])
                self.assertEqual(entry["worker_tree_cleanup"], "confirmed")
            finally:
                runtime.close()

    def test_failed_intent_does_not_spawn(self):
        runtime = object.__new__(runtime_module.Runtime)
        runtime._prepare_handler_admission = lambda lease: (None, None, time.monotonic() + 1)
        runtime._diagnostic_note = lambda *args, **kwargs: False
        runtime._settlement_journal = object()
        runtime.require_durable_cleanup_intent = True
        lease = type("Lease", (), {"execution_id": "exec", "attempt": 1, "fence": 2})()
        with patch.object(runtime_module, "invoke_process_handler") as invoke:
            outcome = runtime._invoke_process(None, None, lease)
        invoke.assert_not_called()
        self.assertEqual(outcome["code"], "cleanup_obligation_unavailable")
        runtime._settlement_journal = None
        with patch.object(runtime_module, "invoke_process_handler") as invoke:
            outcome = runtime._invoke_process(None, None, lease)
        invoke.assert_not_called()
        self.assertEqual(outcome["code"], "cleanup_obligation_unavailable")

    def test_failed_kernel_obligation_never_spawns_in_strict_mode(self):
        runtime = object.__new__(runtime_module.Runtime)
        runtime._prepare_handler_admission = lambda lease: (None, None, time.monotonic() + 1)
        notes = []
        runtime._diagnostic_note = lambda lease, phase, evidence, **kwargs: notes.append((phase, evidence)) or True
        runtime._settlement_journal = object()
        runtime.require_durable_cleanup_intent = True
        runtime.kernel = type('Kernel', (), {'register_supervisor_obligation':
            lambda self, lease, **kwargs: (_ for _ in ()).throw(OSError('uncertain commit'))})()
        lease = ExecutionLease('exec', 'lease', 'owner', 2, 1, 9999999999, 1)
        with patch.object(runtime_module, 'invoke_process_handler') as invoke:
            outcome = runtime._invoke_process(None, None, lease)
        invoke.assert_not_called()
        self.assertEqual(outcome['code'], 'cleanup_obligation_unavailable')
        self.assertEqual([phase for phase, _ in notes],
                         ['supervisor_spawn_intent', 'supervisor_obligation_registration_failed'])
        self.assertEqual(notes[-1][1]['registration'], 'unknown')

    def test_default_strict_failure_cannot_fall_back_to_process_launch(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Kernel.open_sqlite(Path(root) / "kernel.db", {"work": cleanup_handler}, isolation_mode="process")
            try:
                self.assertTrue(runtime.require_durable_cleanup_intent)
                command = runtime.command("work", execution_id="blocked", idempotency_key="blocked",
                                          correlation_id="blocked", timeout_seconds=10, payload={})
                runtime.submit(command)
                original = runtime._diagnostic_note
                def fail_intent(identity, phase, evidence, **kwargs):
                    return False if phase == "supervisor_spawn_intent" else original(identity, phase, evidence, **kwargs)
                with patch.object(runtime, "_diagnostic_note", side_effect=fail_intent), \
                        patch.object(runtime_module, "invoke_process_handler") as invoke:
                    runtime.run_once(execution_id="blocked")
                invoke.assert_not_called()
            finally:
                runtime.close()


def cleanup_handler(payload, context):
    return {"ok": True}
