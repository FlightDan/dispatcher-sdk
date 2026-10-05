"""A bounded retry retains uncertainty already established by real SQLite."""
import json
import time
import unittest

from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, RetryPolicy
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory


class SamplingRefusalTests(unittest.TestCase):
    def exercise(self, *, expire_admission):
        root = retained_directory('sdk-sampling-refusal-')
        path = root / 'kernel.sqlite3'
        evidence = {'expire_admission': expire_admission, 'original_bound': .1}
        try:
            with SQLiteKernel(path) as original:
                original.submit(ExecutionCommandV2('work', 'work', 'refusal', 'refusal',
                    None, 'work', 1, RetryPolicy(), 5, {}))
                lease = original.claim_and_start('owner')
                envelope = original.prepare_execution_budget(lease).enter_handler(5, origin_id='execution:work')
                envelope = original.confirm_handler_entry(lease, envelope)
                token = original._begin_budget_sample('work')

            def no_wall():
                raise AssertionError('recovery refusal observed fresh wall time')

            with SQLiteKernel(path, now=no_wall) as recovered:
                before = recovered.get_execution_limits('work')
                guard_check = recovered._assert_budget_clock
                refusals, statements = [], []
                admissions = 0

                def record_refusal(*args, **kwargs):
                    try:
                        return guard_check(*args, **kwargs)
                    except BudgetClockUnknownError as error:
                        refusals.append(error)
                        raise

                def expire_original_window(statement):
                    nonlocal admissions
                    statements.append(statement)
                    if statement == 'PRAGMA busy_timeout=0':
                        admissions += 1
                        if admissions == expire_admission:
                            # Consume this admission's existing deadline. The
                            # SQL guard remains real and no exception is faked.
                            deadline = recovered._control_deadline
                            while True:
                                remaining = deadline - time.monotonic()
                                if remaining <= 0:
                                    break
                                time.sleep(remaining)

                recovered._assert_budget_clock = record_refusal
                recovered._connection.set_trace_callback(expire_original_window)
                try:
                    expected = BudgetClockUnknownError if expire_admission == 2 else TimeoutError
                    with self.assertRaises(expected) as caught:
                        recovered._sample_budget('work', envelope, timeout_seconds=.1)
                finally:
                    recovered._connection.set_trace_callback(None)
                    recovered._assert_budget_clock = guard_check
                error = caught.exception
                evidence.update(admissions=admissions, refusal_count=len(refusals),
                    error_type=type(error).__name__, error_message=str(error),
                    cause_type=type(error.__cause__).__name__ if error.__cause__ else None,
                    statements=statements, token=token)
                self.assertEqual(admissions, expire_admission)
                if expire_admission == 2:
                    self.assertEqual(len(refusals), 1)
                    self.assertIs(error, refusals[0])
                    self.assertEqual(str(error), 'budget_clock_sample_unresolved:sampling')
                    self.assertIsInstance(error.__cause__, TimeoutError)
                else:
                    self.assertEqual(refusals, [])
                    self.assertEqual(str(error), 'Kernel control admission budget elapsed')
                self.assertFalse(any(sql.lstrip().upper().startswith(
                    ('INSERT', 'UPDATE', 'DELETE', 'BEGIN')) for sql in statements), statements)
                self.assertEqual(recovered.get_execution_limits('work'), before)
                self.assertEqual([tuple(row) for row in recovered._connection.execute(
                    'SELECT token,reason FROM kernel_budget_samples')], [(token, 'sampling')])
                self.assertFalse(recovered._budget_samples_pending())
        finally:
            (root / 'evidence.json').write_text(json.dumps(evidence, indent=2))
            print('sampling_refusal_evidence=' + str(root / 'evidence.json'), flush=True)

    def test_retry_admission_expiry_preserves_exact_sql_refusal(self):
        self.exercise(expire_admission=2)

    def test_initial_admission_expiry_remains_original_timeout(self):
        self.exercise(expire_admission=1)


if __name__ == '__main__':
    unittest.main()
