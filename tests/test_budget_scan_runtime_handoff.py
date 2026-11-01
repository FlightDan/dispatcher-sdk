import threading
import unittest
from concurrent.futures import Future
from types import SimpleNamespace

from dispatcher_sdk.execution_kernel.errors import BudgetScanContinuation
from dispatcher_sdk.execution_kernel.host import RuntimeHost
from dispatcher_sdk.execution_kernel.runtime import InProcessRuntime


class BudgetScanRuntimeHandoffTests(unittest.TestCase):
    def test_runtime_carries_cursor_across_exclusions_and_wraps(self):
        runtime = InProcessRuntime.__new__(InProcessRuntime)
        runtime._assert_registry_current = lambda: None
        runtime._recover_script_output = lambda deadline: None
        runtime._lifecycle_lock = threading.RLock()
        runtime._closed = False
        runtime._budget_scan_continuation = None
        runtime.isolation_mode = 'process'
        runtime.worker_id = 'worker'
        runtime.lease_seconds = 10
        runtime.registry_revision = 'revision'
        runtime.handler_revisions = {}
        runtime._handler_start_timeout = lambda: 1
        exclusions = [()]
        runtime._diagnostic_claim_exclusions = lambda execution_id: (False, exclusions[0])
        calls = []
        cursor = {'predicate': {'revisions': ['revision']}, 'after': [1, 'blocked']}
        def claim(*args, **kwargs):
            calls.append(kwargs)
            if len(calls) in (1, 3):
                raise BudgetScanContinuation(cursor)
            return None
        runtime.kernel = SimpleNamespace(claim_and_start=claim)
        with self.assertRaises(BudgetScanContinuation):
            runtime._run_once_active(admission=None)
        self.assertIsNone(runtime._run_once_active(admission=None))
        self.assertEqual(calls[1]['budget_scan_cursor'], cursor)
        with self.assertRaises(BudgetScanContinuation):
            runtime._run_once_active(admission=None)
        exclusions[0] = ('pending',)
        self.assertIsNone(runtime._run_once_active(admission=None))
        self.assertEqual(calls[3]['budget_scan_cursor'], cursor)
        self.assertEqual(calls[3]['exclude_execution_ids'], ('pending',))
        exclusions[0] = ()
        self.assertIsNone(runtime._run_once_active(admission=None))
        self.assertNotIn('budget_scan_cursor', calls[4])

    def test_runtime_drops_cursor_when_revisions_change(self):
        runtime = InProcessRuntime.__new__(InProcessRuntime)
        runtime._assert_registry_current = lambda: None
        runtime._recover_script_output = lambda deadline: None
        runtime._lifecycle_lock = threading.RLock()
        runtime._closed = False
        runtime._budget_scan_continuation = (('old',), {'predicate': {'revisions': ['old']}, 'after': [1, 'blocked']})
        runtime.isolation_mode = 'process'
        runtime.worker_id = 'worker'
        runtime.lease_seconds = 10
        runtime.registry_revision = 'new'
        runtime.handler_revisions = {}
        runtime._handler_start_timeout = lambda: 1
        runtime._diagnostic_claim_exclusions = lambda execution_id: (False, ())
        calls = []
        runtime.kernel = SimpleNamespace(claim_and_start=lambda *args, **kwargs: calls.append(kwargs))
        self.assertIsNone(runtime._run_once_active(admission=None))
        self.assertNotIn('budget_scan_cursor', calls[0])

    def test_host_reschedules_continuation_as_work_not_error(self):
        class FakeRuntime:
            def run_once(self): pass
            def reap(self): pass
            def close(self): pass
        class FakeBridge:
            def pump(self, **kwargs): pass
            def sweep(self, **kwargs): pass
        host = RuntimeHost(FakeRuntime(), FakeBridge())
        future = Future()
        future.set_exception(BudgetScanContinuation({'after': [1, 'blocked']}))
        host._futures.add(future)
        self.assertTrue(host._collect_workers())
        self.assertEqual(host.health().error_count, 0)
