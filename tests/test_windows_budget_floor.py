"""Portable clock-floor checks; these do not establish native Windows acceptance."""
from dataclasses import replace
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import _windows_runtime as windows_runtime
from dispatcher_sdk.execution_kernel._process_runtime import _budget_outcome
from dispatcher_sdk.execution_kernel._windows_runtime import _Watchdog
from dispatcher_sdk.execution_kernel.budget import (
    BudgetEnvelope, DeadlineConstraint, sample_clock,
)
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy


def _must_not_invoke(payload, context):
    raise AssertionError('expired startup must not invoke business')


class _StartupClock:
    def __init__(self):
        self.wall = 100.0
        self.samples = []

    def __call__(self):
        self.samples.append(self.wall)
        return 102.0 if len(self.samples) >= 3 else self.wall


class WindowsBudgetFloorTests(unittest.TestCase):
    def test_production_invocation_retains_joined_watchdog_floor_before_entry(self):
        clock = _StartupClock()

        class Handle:
            revocation_reason = None
            exitcode = 0
            def __init__(self, *args):
                pass
            def resume(self):
                pass
            def terminate(self):
                clock.wall = 100.0
                return True
            def close(self):
                pass
            def exited(self):
                return False

        original = BudgetEnvelope((DeadlineConstraint('parent:original', 'parent', 101),),
                                  sample_clock(wall_time=100))
        command = ExecutionCommandV2('work', 'work', 'original-binding', 'root', None,
            'handler', 1, RetryPolicy(), 10, {})
        # Only OS creation/handle boundaries are substituted. Production timer,
        # invocation loop, containment order and final outcome merge all run.
        with patch.object(windows_runtime, '_WinAPI', return_value=object()), \
             patch.object(windows_runtime, '_create_suspended', return_value=(None, None)), \
             patch.object(windows_runtime, 'WindowsProcessHandle', Handle):
            outcome = windows_runtime.invoke_windows_handler(db_path='/unused/kernel.sqlite3',
                handler=_must_not_invoke, command=command, lease=None, now=clock,
                start_timeout=5, budget_envelope=original)
        self.assertEqual(outcome['kind'], 'timeout')
        retained = BudgetEnvelope.from_dict(outcome['budget_envelope'])
        self.assertEqual(retained.constraints, original.constraints)
        self.assertGreaterEqual(retained.checkpoint.wall_at, 102)
        self.assertEqual(retained.view(sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)

    def test_actual_watchdog_retains_expiry_sample_after_wall_rollback(self):
        wall = [100.0]
        calls = []
        terminated = threading.Event()

        def now():
            calls.append(wall[0])
            # The startup sample is timely; the first timer sample expires.
            if len(calls) == 1:
                wall[0] = 102.0
                return 100.0
            return wall[0]

        class Handle:
            def terminate(self):
                wall[0] = 100.0
                terminated.set()
                return True

        original = BudgetEnvelope((DeadlineConstraint('parent:original', 'parent', 101),),
                                  sample_clock(wall_time=100))
        watcher = _Watchdog(Handle(), time.monotonic() + 5, original, now)
        self.addCleanup(watcher.close)
        self.assertTrue(terminated.wait(1), 'independent watchdog did not expire')
        watcher.close()
        retained = watcher.snapshot()
        self.assertEqual(calls, [100.0, 102.0], 'timer sampled wall repeatedly for one decision')
        self.assertTrue(watcher.expired)
        self.assertEqual(retained.constraints, original.constraints)
        self.assertGreaterEqual(retained.checkpoint.wall_at, 102)
        self.assertEqual(retained.view(sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)
        outcome = _budget_outcome({'kind': 'timeout', 'effect_ids': []}, retained)
        self.assertEqual(BudgetEnvelope.from_dict(outcome['budget_envelope']).view(
            sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)

    def test_entry_checkpoint_cannot_erase_earlier_watchdog_forward_floor(self):
        sample = sample_clock(wall_time=100)
        inherited = BudgetEnvelope((DeadlineConstraint('parent:original', 'parent', 110),), sample,
                                   started_at=99)
        entered = inherited.enter_handler(10, origin_id='execution:child', sample=sample)
        wall = [105.0]
        class Handle:
            def terminate(self):
                return True
        watcher = _Watchdog(Handle(), time.monotonic() + 5, inherited, lambda: wall[0])
        self.addCleanup(watcher.close)
        wall[0] = 100
        deadline = watcher.business_deadline(10, envelope=entered, deadline=time.monotonic() + 10)
        watcher.close()
        retained = watcher.snapshot()
        self.assertEqual(retained.constraints, entered.constraints)
        self.assertEqual(retained.started_at, entered.started_at)
        self.assertGreaterEqual(retained.checkpoint.wall_at, 105)
        self.assertLess(deadline - time.monotonic(), 5.1)

    def test_cleanup_floor_is_retained_without_relabelling_timely_business_success(self):
        sample = sample_clock(wall_time=100)
        original = BudgetEnvelope((DeadlineConstraint('execution:worker', 'execution', 120, 10),),
                                  sample, started_at=100)
        terminated = threading.Event()
        class Handle:
            def terminate(self):
                terminated.set()
                return True
        wall = [100.0]
        watcher = _Watchdog(Handle(), time.monotonic() + 5, original, lambda: wall[0])
        self.addCleanup(watcher.close)
        watcher.cleanup_deadline(time.monotonic() + 5)
        wall[0] = 112
        watcher.changed.set()
        until = time.monotonic() + 1
        while watcher.snapshot().checkpoint.wall_at < 112 and time.monotonic() < until:
            time.sleep(.005)
        watcher.close()
        retained = watcher.snapshot()
        self.assertFalse(terminated.is_set(), 'cleanup consumed work reserve as its hard cutoff')
        self.assertGreaterEqual(retained.checkpoint.wall_at, 112)
        entry = {'budget_envelope': original.to_dict(), 'started_at': original.started_at}
        outcome = _budget_outcome({'kind': 'ok', 'value': {'original': True},
                                  'budget_envelope': original.to_dict(), 'effect_ids': []}, retained, entry)
        self.assertEqual(outcome['kind'], 'ok')
        self.assertEqual(outcome['value'], {'original': True})
        self.assertEqual(BudgetEnvelope.from_dict(outcome['budget_envelope']).view(
            sample=sample_clock(wall_time=100)).remaining_work_seconds, 0)

    def test_unknown_timer_domain_remains_explicit_and_contains_worker(self):
        terminated = threading.Event()
        class Handle:
            def terminate(self):
                terminated.set()
                return True
        original = BudgetEnvelope((DeadlineConstraint('parent:original', 'parent', 110),),
                                  replace(sample_clock(wall_time=100), domain_id='unrelated-domain'))
        watcher = _Watchdog(Handle(), time.monotonic() + 5, original, lambda: 100)
        self.addCleanup(watcher.close)
        self.assertTrue(terminated.wait(1))
        watcher.close()
        self.assertIsNotNone(watcher.clock_error)
        self.assertTrue(watcher.expired)


if __name__ == '__main__':
    unittest.main()
