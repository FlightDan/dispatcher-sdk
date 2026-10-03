"""An inherited deadline during real deserialization is admission timeout."""
from pathlib import Path
import json
import os
from tests._acceptance_evidence import retained_directory
import time
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, DeadlineConstraint, sample_clock
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from dispatcher_sdk.execution_kernel._process_runtime import invoke_process_handler


class SlowBootstrap:
    __execution_kernel_revision__ = 'slow-bootstrap-admission-v1'

    def __init__(self, directory):
        self.directory = str(directory)

    def __setstate__(self, state):
        self.__dict__.update(state)
        Path(self.directory, 'deserializing').write_text(str(os.getpid()))
        time.sleep(3)

    def __call__(self, payload, context):
        Path(self.directory, 'business').write_text('unexpected')
        return {'unexpected': True}


@unittest.skipUnless(os.name == 'posix', 'POSIX startup guard')
class NativeAdmissionDeadlineTests(unittest.TestCase):
    def test_original_tool_cutoff_before_handler_entry_is_admission_timeout(self):
        root = retained_directory('sdk-native-admission-timeout-')
        evidence = {'tool_timeout': .7, 'startup_safety_timeout': 10, 'execution_timeout': 5}
        try:
            with SQLiteKernel(root / 'kernel.sqlite3') as kernel:
                command = ExecutionCommandV2(execution_id='original', idempotency_key='original',
                    registry_revision='fixture', correlation_id='fixture', causation_id=None,
                    handler_id='slow', handler_contract_version=1, retry_policy=RetryPolicy(),
                    timeout_seconds=5, payload={})
                kernel.submit(command)
                lease = kernel.claim_and_start('fixture', lease_seconds=30)
                sample = sample_clock()
                envelope = BudgetEnvelope((DeadlineConstraint(source='tool', origin_id='original-tool', deadline_at=sample.wall_at + .7),), sample)
                evidence['original_budget'] = envelope.to_dict()
                outcome = invoke_process_handler(db_path=str(kernel.db_path), handler=SlowBootstrap(root),
                    command=command, lease=lease, now=None, start_timeout=10, budget_envelope=envelope)
                evidence.update(outcome=outcome, deserialized=(root/'deserializing').exists(),
                                business_called=(root/'business').exists())
                self.assertFalse(evidence['business_called'], evidence)
                self.assertEqual(outcome['kind'], 'timeout', evidence)
                self.assertEqual(outcome['phase'], 'admission', evidence)
                self.assertEqual(outcome['limiting_source'], 'tool', evidence)
                self.assertEqual(outcome['budget_envelope']['constraints'], envelope.to_dict()['constraints'])
        finally:
            path = root / 'evidence.json'
            path.write_text(json.dumps(evidence, indent=2))
            print('native_admission_timeout_evidence=' + str(path), flush=True)
