"""Real observation read attempt expiry shares the original child wait window."""
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests._acceptance_evidence import retained_directory

from dispatcher_sdk._inspection import InspectionBudgetExceeded, ProgressCallbackError
from dispatcher_sdk.execution_kernel.budget import BudgetClockUnknownError, BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.children import HandlerChildren, ChildExecutionError, _RetryWindow, _Store, _retry, _transient_control_error
from dispatcher_sdk.observability import ObservationJournal, ObservationOptions
from dispatcher_sdk.observability.contracts import ObservationError


class ChildInspectionRetryTests(unittest.TestCase):
    def setUp(self):
        self.root = retained_directory('sdk-child-inspection-retry-')
        self.records = []
        self.addCleanup(self.retain_evidence)
        self.journal = ObservationJournal(self.root/'observations.sqlite3',
            kernel_path=self.root/'kernel.sqlite3', source_id='original-host',
            options=ObservationOptions(query_timeout=.02))
        self.store = _Store(self.journal)

    def retain_evidence(self):
        path = self.root/'evidence.json'
        path.write_text(json.dumps({'test': self.id(), 'records': self.records}, indent=2))
        print('child_inspection_retry_evidence=' + str(path), flush=True)

    @staticmethod
    def delay_binding():
        # Windows monotonic samples may have coarse ticks. Require the same
        # declared .03 seconds of measured metadata delay on every attempt.
        deadline = time.monotonic() + .03
        while (remaining := deadline - time.monotonic()) > 0:
            time.sleep(remaining)

    def window(self, seconds):
        envelope = BudgetEnvelope((), sample_clock()).derive(source='tool', origin_id='original-call',
                                                  timeout_seconds=seconds)
        return _RetryWindow(envelope, SimpleNamespace(_wall_time=time.time))

    def test_real_read_budget_expiry_retries_then_reads_inside_same_original_window(self):
        window = self.window(1)
        original_constraints = window.envelope.constraints
        original_deadline = window.deadline
        errors = []
        original_binding = self.journal._validate_binding
        calls = []

        def delayed_first_binding(connection):
            calls.append(time.monotonic())
            if len(calls) == 1:
                # A deterministic metadata-admission delay expires the actual
                # journal InspectionBudget. No exception is fabricated here.
                self.delay_binding()
            return original_binding(connection)

        def read_request():
            try:
                return self.store.request('missing-parent', 'missing-request')
            except InspectionBudgetExceeded as error:
                errors.append(error)
                raise

        record = {'scenario': 'real_journal_read_expiry_then_success',
            'original_deadline': original_deadline,
            'constraints': [item.to_dict() for item in original_constraints]}
        self.records.append(record)
        before = time.monotonic()
        try:
            with patch.object(self.journal, '_validate_binding', delayed_first_binding):
                value = _retry(window, read_request, store=self.store)
        except BaseException as error:
            record['operation_failure'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            elapsed = time.monotonic() - before
            record.update(attempts=len(calls), elapsed=elapsed, retained_deadline=window.deadline,
                errors=[{'type': type(error).__name__, 'message': str(error),
                         'cause_type': type(error.__cause__).__name__,
                         'cause_message': str(error.__cause__)} for error in errors])
        self.assertIsNone(value)
        self.assertGreaterEqual(len(calls), 2)
        self.assertGreaterEqual(len(errors), 1)
        self.assertEqual(str(errors[0]), 'inspection timeout exceeded')
        self.assertEqual(window.envelope.constraints, original_constraints)
        self.assertLessEqual(window.deadline, original_deadline + .001)
        self.assertGreater(window.remaining(), 0)
        self.assertLess(elapsed, 1)

    def test_persistent_real_read_expiry_preserves_last_raw_error_at_original_cutoff(self):
        window = self.window(.12)
        original_constraints = window.envelope.constraints
        original_deadline = window.deadline
        errors = []
        original_binding = self.journal._validate_binding

        def delayed_binding(connection):
            self.delay_binding()
            return original_binding(connection)

        def read_request():
            try:
                return self.store.request('missing-parent', 'missing-request')
            except InspectionBudgetExceeded as error:
                errors.append(error)
                raise

        record = {'scenario': 'persistent_real_journal_read_expiry',
            'original_deadline': original_deadline,
            'constraints': [item.to_dict() for item in original_constraints]}
        self.records.append(record)
        before = time.monotonic()
        try:
            with patch.object(self.journal, '_validate_binding', delayed_binding):
                with self.assertRaises(InspectionBudgetExceeded) as caught:
                    _retry(window, read_request, store=self.store)
        except BaseException as error:
            record['operation_failure'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            elapsed = time.monotonic() - before
            record.update(attempts=len(errors), elapsed=elapsed, retained_deadline=window.deadline,
                errors=[{'type': type(error).__name__, 'message': str(error),
                         'cause_type': type(error.__cause__).__name__,
                         'cause_message': str(error.__cause__)} for error in errors])
        record['same_last_exception'] = bool(errors) and caught.exception is errors[-1]
        self.assertGreaterEqual(len(errors), 1)
        self.assertIs(caught.exception, errors[-1])
        original_error = caught.exception
        original_cause = original_error.__cause__
        self.assertIs(caught.exception.__cause__, original_cause)
        self.assertEqual(str(caught.exception), 'inspection timeout exceeded')
        self.assertEqual(window.envelope.constraints, original_constraints)
        self.assertLessEqual(window.deadline, original_deadline + .001)
        self.assertEqual(window.remaining(), 0)
        self.assertLess(elapsed, .30)
        # Exercise only the delivery proof protocol after attachment. Its
        # wait error is the actual journal error captured above. A distinct
        # proof error tests causal preservation without another business wait.
        capability = object.__new__(HandlerChildren)
        capability.kernel = window.kernel
        capability.store = self.store
        capability.command = SimpleNamespace(execution_id='parent')
        capability.parent_lease = SimpleNamespace(attempt=1, fence=1)
        row = {'budget_json': json.dumps(window.envelope.to_dict()), 'parent_execution_id': 'parent',
               'parent_attempt': 1, 'parent_fence': 1, 'child_execution_id': 'missing-child'}
        proof_error = InspectionBudgetExceeded('bounded completion proof read expired')
        # Keep this protocol check on the exhausted original local window.
        # Reconstructing a different window while injecting its predecessor's
        # error need not prove that the new local timer has expired.
        with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                patch.object(self.store, 'attach'), patch.object(capability, '_await_window',
                side_effect=original_error), patch.object(capability, '_completed_result',
                side_effect=proof_error) as proof:
            with self.assertRaises(InspectionBudgetExceeded) as delivered:
                capability._await(row)
            self.assertIs(delivered.exception, original_error)
            self.assertIs(delivered.exception.__cause__, proof_error)
            proof.assert_called_once()
        for proof_error in (RuntimeError('permanent proof error'),
                ChildExecutionError('parent_authority_revoked', 'actual revoked parent')):
            with patch('dispatcher_sdk.execution_kernel.children._RetryWindow', return_value=window), \
                    patch.object(self.store, 'attach'), patch.object(capability, '_await_window',
                    side_effect=original_error), patch.object(capability, '_completed_result',
                    side_effect=proof_error) as proof:
                with self.assertRaises(type(proof_error)) as delivered:
                    capability._await(row)
                self.assertIs(delivered.exception, proof_error)
                proof.assert_called_once()

    def test_generic_timeout_unknown_clock_and_provenance_errors_remain_immediate(self):
        for error in (TimeoutError('inspection timeout exceeded'),
                RuntimeError('inspection timeout exceeded'),
                ProgressCallbackError('inspection progress callback failed'),
                BudgetClockUnknownError('unknown clock'), ObservationError('source binding changed')):
            with self.subTest(type=type(error).__name__):
                window = self.window(1)
                calls = []
                def operation():
                    calls.append(True)
                    raise error
                record = {'scenario': 'nontransient_control_error',
                    'error_type': type(error).__name__, 'message': str(error)}
                self.records.append(record)
                before = time.monotonic()
                try:
                    with self.assertRaises(type(error)) as caught:
                        _retry(window, operation)
                finally:
                    record.update(attempts=len(calls), elapsed=time.monotonic() - before)
                record['same_exception'] = caught.exception is error
                self.assertIs(caught.exception, error)
                self.assertEqual(len(calls), 1)
                self.assertFalse(_transient_control_error(error))


if __name__ == '__main__':
    unittest.main()
