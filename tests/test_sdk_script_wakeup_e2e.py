from pathlib import Path
import os
import multiprocessing
import sys
import tempfile
import threading
import unittest

from dispatcher_sdk.execution_kernel import Kernel, ScriptSpec, script_handlers
from dispatcher_sdk.orchestrator import Orchestrator, OrchestratorHost


@unittest.skipUnless(os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
                     "scripts require POSIX fork process containment")
class ScriptWakeupTests(unittest.TestCase):
    def test_host_runs_scripts_and_wakes_without_application_polling(self):
        scenarios = [
            ("print('ready')", 10, 'succeeded'),
            ("import sys; print('bad', file=sys.stderr); sys.exit(3)", 10, 'failed'),
            ("import time; print('started', flush=True); time.sleep(30)", 1, 'recovery_required'),
        ]
        for source, timeout, expected in scenarios:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime = Kernel.open_sqlite(root / 'kernel.db', script_handlers(), isolation_mode='process')
                orch = Orchestrator(root / 'orchestration.db', runtime.kernel, runtime=runtime)
                orch.create_run('run', command_id='create')
                received = threading.Event()
                notifications = []
                def callback(notification):
                    notifications.append(notification)
                    received.set()
                command = ScriptSpec(source, (sys.executable, '-u'), root, root / 'logs').command(
                    execution_id='script', idempotency_key='script', registry_revision=runtime.registry_revision,
                    correlation_id='run', timeout_seconds=timeout)
                with OrchestratorHost(orch, callback, worker_count=1):
                    orch.apply_operations('run', command_id='submit', expected_revision=0, operations=[
                        {'kind': 'add_task', 'task_id': 'script', 'command': command.to_dict()},
                        {'kind': 'watch_task', 'task_id': 'script', 'watch_id': 'wake',
                         'target': {'conversation_id': 'chat'}},
                        {'kind': 'dispatch', 'task_id': 'script'},
                    ])
                    self.assertTrue(received.wait(10), expected)
                    self.assertEqual(notifications[0]['state'], expected)
                    self.assertEqual(notifications[0]['target'], {'conversation_id': 'chat'})
                    if expected == 'recovery_required':
                        effect_id = notifications[0]['event']['data']['effect_id']
                        self.assertIn('output_root', runtime.kernel.get_effect(effect_id).request)
                    else:
                        self.assertEqual(orch.kernel_result_outbox_status().pending, 1)
                self.assertEqual(len(notifications), 1)


if __name__ == '__main__':
    unittest.main()
