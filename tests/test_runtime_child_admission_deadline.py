"""Child deadline checks; registry revisions are fixed for the whole Runtime lifetime."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel import runtime as runtime_module


def handler(payload, context):
    return payload


class ChildAdmissionDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = patch.object(runtime_module, 'registry_revision', return_value='fixed-registry')
        self.handler_revision = patch.object(runtime_module, 'handler_revision', return_value='fixed-handler')
        self.registry_mock = self.registry.start()
        self.handler_revision.start()
        self.runtime = Kernel.open_sqlite(Path(self.temp.name) / 'kernel.sqlite', {'handler': handler}, isolation_mode='thread')
        self.command = self.runtime.command('handler', execution_id='child', idempotency_key='child',
                                            correlation_id='child', timeout_seconds=30, payload={})

    def tearDown(self):
        self.runtime.close()
        self.handler_revision.stop()
        self.registry.stop()
        self.temp.cleanup()

    def test_registry_time_counts_for_submit_and_adopt(self):
        def delayed(_handlers):
            time.sleep(.06)
            return 'fixed-registry'
        self.registry_mock.side_effect = delayed
        with patch.object(self.runtime.kernel, 'submit_child') as submit, \
             patch.object(self.runtime.kernel, 'adopt_child') as adopt:
            with self.assertRaises(TimeoutError):
                self.runtime.submit_child(self.command, parent_lease=None, budget_envelope=None, timeout_seconds=.02)
            with self.assertRaises(TimeoutError):
                self.runtime.adopt_child('child', parent_lease=None, budget_envelope=None, timeout_seconds=.02)
            submit.assert_not_called()
            adopt.assert_not_called()

    def test_adopt_lock_and_get_share_original_deadline(self):
        locked = threading.Event()
        release = threading.Event()
        def holder():
            with self.runtime.kernel._lock:
                locked.set()
                release.wait(1)
        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(locked.wait(1))
        timer = threading.Timer(.06, release.set)
        timer.start()
        def delayed_get(_execution_id):
            time.sleep(.08)
            return SimpleNamespace(command=self.command)
        try:
            with patch.object(self.runtime.kernel, 'get', side_effect=delayed_get), \
                 patch.object(self.runtime.kernel, 'adopt_child') as adopt:
                with self.assertRaises(TimeoutError):
                    self.runtime.adopt_child('child', parent_lease=None, budget_envelope=None, timeout_seconds=.1)
                adopt.assert_not_called()
        finally:
            release.set()
            thread.join(1)
            timer.join(1)

    def test_remaining_time_is_recomputed_after_get(self):
        def delayed_get(_execution_id):
            time.sleep(.06)
            return SimpleNamespace(command=self.command)
        with patch.object(self.runtime.kernel, 'get', side_effect=delayed_get), \
             patch.object(self.runtime.kernel, 'adopt_child', return_value='adopted') as adopt:
            self.assertEqual('adopted', self.runtime.adopt_child('child', parent_lease=None,
                             budget_envelope=None, timeout_seconds=.5))
            self.assertGreater(adopt.call_args.kwargs['timeout_seconds'], 0)
            self.assertLess(adopt.call_args.kwargs['timeout_seconds'], .46)

    def test_unbounded_calls_keep_unbounded_kernel_timeout(self):
        with patch.object(self.runtime.kernel, 'get', return_value=SimpleNamespace(command=self.command)), \
             patch.object(self.runtime.kernel, 'adopt_child', return_value='adopted') as adopt, \
             patch.object(self.runtime.kernel, 'submit_child', return_value='submitted') as submit:
            self.assertEqual('submitted', self.runtime.submit_child(self.command, parent_lease=None, budget_envelope=None))
            self.assertEqual('adopted', self.runtime.adopt_child('child', parent_lease=None, budget_envelope=None))
            self.assertIsNone(submit.call_args.kwargs['timeout_seconds'])
            self.assertIsNone(adopt.call_args.kwargs['timeout_seconds'])


if __name__ == '__main__':
    unittest.main()
