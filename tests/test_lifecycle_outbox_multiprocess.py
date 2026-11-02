"""Crash-window and concurrent delivery checks for lifecycle diagnostics."""
import multiprocessing
import os
from contextlib import ExitStack, nullcontext
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import Kernel, SQLiteKernel
from dispatcher_sdk.execution_kernel.settlement import SettlementJournal
from dispatcher_sdk.execution_kernel.runtime import InProcessRuntime
from dispatcher_sdk.execution_kernel import runtime as runtime_module
from test_execution_kernel_v2_sqlite import make_command


def _producer_then_die(path, conn):
    kernel = SQLiteKernel(path)
    token = kernel.lifecycle_reserve('job', 0, 0, 'producer', slots=4)
    sequence = kernel.lifecycle_append(token, 'first', 'requested', {'stage': 1})
    conn.send(sequence)
    conn.close()
    os._exit(0)


def _receiver_commit_then_die(path, journal_path, conn):
    kernel = SQLiteKernel(path)
    journal = SettlementJournal.open_existing(journal_path, source_id='test', kernel_path=path,
                                              timeout_seconds=5)
    event = kernel.lifecycle_peek()
    journal.note({k: event[k] for k in ('execution_id', 'attempt', 'fence')},
                 event['phase'], event['payload'], note_id=event['event_id'], timeout_seconds=5)
    conn.send(event['sequence'])
    conn.close()
    os._exit(0)


def _append_later(path, conn):
    kernel = SQLiteKernel(path)
    sequence = kernel.lifecycle_append('producer', 'second', 'second', {})
    conn.send(sequence)
    conn.close()
    kernel.close()


def _blocking_handler(payload, context):
    Path(payload['started']).write_text(str(os.getpid()))
    time.sleep(25)


class LifecycleOutboxMultiprocessTests(unittest.TestCase):
    def _run_crashing_child(self, target, args, label):
        ctx = multiprocessing.get_context('spawn')
        parent, child = ctx.Pipe(False)
        process = ctx.Process(target=target, args=(*args, child))
        try:
            process.start()
            child.close()
            self.assertTrue(parent.poll(15), f'{label} did not send its committed sequence')
            try:
                sequence = parent.recv()
            except EOFError:
                process.join(15)
                self.fail(f'{label} exited before sending its committed sequence (exitcode={process.exitcode})')
            process.join(15)
            self.assertEqual(process.exitcode, 0, f'{label} did not exit after sending')
            return sequence
        finally:
            parent.close()
            child.close()
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                    if process.is_alive():
                        process.kill()
                        process.join(5)
                else:
                    process.join()
                process.close()

    def test_crashed_producer_and_receiver_ack_loss_replay(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            path = str(Path(directory) / 'kernel.sqlite')
            journal_path = str(Path(directory) / 'settlements.sqlite')
            kernel = SQLiteKernel(path)
            cleanup.callback(kernel.close)
            kernel.submit(make_command('job'))
            journal = SettlementJournal(journal_path, source_id='test', kernel_path=path,
                                        timeout_seconds=5)
            sequence = self._run_crashing_child(_producer_then_die, (path,), 'producer')
            self.assertIsNone(kernel.claim_and_start('other', registry_revision='registry-1',
                                                    execution_id='job'))
            self.assertEqual(self._run_crashing_child(_receiver_commit_then_die,
                                                      (path, journal_path), 'receiver'), sequence)
            event = kernel.lifecycle_peek()
            self.assertEqual(event['event_id'], 'first')
            journal.note({k: event[k] for k in ('execution_id', 'attempt', 'fence')},
                         event['phase'], event['payload'], note_id=event['event_id'], timeout_seconds=5)
            self.assertTrue(kernel.lifecycle_ack(event['sequence'], event['event_id']))
            notes = journal.inspect_notes('job', timeout_seconds=5)['notes']
            self.assertEqual([note['note_id'] for note in notes], ['first'])
            # An unclosed crashed producer still fences admission after delivery.
            self.assertIsNone(kernel.claim_and_start('other', registry_revision='registry-1',
                                                    execution_id='job'))

    def test_oldest_event_must_be_acknowledged_first(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'kernel.sqlite')
            kernel = SQLiteKernel(path)
            kernel.submit(make_command('job'))
            token = kernel.lifecycle_reserve('job', 0, 0, 'producer', slots=4)
            first = kernel.lifecycle_append(token, 'first', 'first', {})
            parent, child = multiprocessing.get_context('spawn').Pipe(False)
            producer = multiprocessing.get_context('spawn').Process(target=_append_later, args=(path, child))
            producer.start()
            child.close()
            self.assertTrue(parent.poll(15), 'second producer did not append')
            second = parent.recv()
            producer.join(15)
            self.assertEqual(producer.exitcode, 0)
            self.assertFalse(kernel.lifecycle_ack(second, 'second'))
            self.assertEqual(kernel.lifecycle_peek()['event_id'], 'first')
            self.assertTrue(kernel.lifecycle_ack(first, 'first'))
            self.assertEqual(kernel.lifecycle_peek()['event_id'], 'second')
            self.assertTrue(kernel.lifecycle_ack(second, 'second'))
            kernel.lifecycle_finish(token)
            self.assertIsNotNone(kernel.claim_and_start('other', registry_revision='registry-1',
                                                       execution_id='job'))
            kernel.close()

    def test_blocked_execution_can_be_skipped_without_reordering_it(self):
        with tempfile.TemporaryDirectory() as directory:
            kernel = SQLiteKernel(Path(directory) / 'kernel.sqlite')
            for execution in ('job', 'other'):
                kernel.submit(make_command(execution))
                kernel.lifecycle_reserve(execution, 0, 0, execution, slots=4)
            kernel.lifecycle_append('job', 'job-first', 'first', {})
            kernel.lifecycle_append('job', 'job-second', 'second', {})
            kernel.lifecycle_append('other', 'other-first', 'first', {})
            self.assertEqual(kernel.lifecycle_peek()['event_id'], 'job-first')
            self.assertEqual(kernel.lifecycle_peek(exclude_execution_ids=('job',))['event_id'], 'other-first')
            self.assertEqual(kernel.lifecycle_peek()['event_id'], 'job-first')
            kernel.close()

    def test_runtime_retry_delivers_other_execution_when_one_receiver_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'kernel.sqlite')
            kernel = SQLiteKernel(path)
            journal = SettlementJournal(Path(directory) / 'settlements.sqlite', source_id='test', kernel_path=path)
            for execution in ('job', 'other'):
                kernel.submit(make_command(execution))
                kernel.lifecycle_reserve(execution, 0, 0, execution, slots=4)
                kernel.lifecycle_append(execution, execution + '-event', 'phase', {})

            class OneFailedJournal:
                def lifecycle_note(self, identity, phase, payload, **kwargs):
                    if identity['execution_id'] == 'job':
                        raise RuntimeError('receiver unavailable for job')
                    return journal.lifecycle_note(identity, phase, payload, **kwargs)

            runtime = InProcessRuntime.__new__(InProcessRuntime)
            runtime.kernel = kernel
            runtime._settlement_journal = OneFailedJournal()
            runtime._diagnostic_retry_lock = threading.Lock()
            runtime._diagnostic_pending_lock = threading.Lock()
            runtime._diagnostic_pending = {}
            runtime._diagnostic_received = set()
            runtime._diagnostic_errors = {}
            runtime._lifecycle_note_tokens = {}
            runtime._lifecycle_enqueued = set()
            runtime._lifecycle_scan_cursor = 0
            runtime._lifecycle_producers = {}
            runtime._lifecycle_finished = set()
            runtime._retry_diagnostic_notes(time.monotonic() + 2)
            self.assertEqual(kernel.lifecycle_peek()['event_id'], 'job-event')
            self.assertEqual([note['phase'] for note in journal.inspect_notes('other')['notes']],
                             ['phase'], runtime._diagnostic_errors)
            kernel.close()

    def _check_cancellation_stops_process_when_diagnostics_fail(self, fail_reserve):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, 'registry_revision', return_value='fixture-registry'), \
             patch.object(runtime_module, 'handler_revision', return_value='fixture-handler'):
            runtime = Kernel.open_sqlite(Path(directory) / 'kernel.sqlite', {'work': _blocking_handler},
                                        isolation_mode='process')
            started = Path(directory) / 'started'
            runtime.submit(runtime.command('work', execution_id='job', idempotency_key='job',
                correlation_id='root', timeout_seconds=40, payload={'started': str(started)}))
            failures, results = [], []
            def drive():
                try:
                    results.append(runtime.run_once(execution_id='job'))
                except Exception as exc:
                    failures.append(exc)
            driver = threading.Thread(target=drive)
            driver.start()
            deadline = time.monotonic() + 20
            while not started.exists() and driver.is_alive() and time.monotonic() < deadline:
                time.sleep(.02)
            try:
                self.assertTrue(started.exists(), (failures, results, runtime._diagnostic_errors, runtime.kernel.get('job')))
                worker_pid = int(started.read_text())
                snapshot = runtime.kernel.get('job')
                original_append = runtime.kernel.lifecycle_append
                reserve_failures = []
                append_failures = []
                def reserve(*args, **kwargs):
                    reserve_failures.append(args)
                    raise RuntimeError('injected diagnostic reserve failure')
                def append(token, event_id, phase, payload, **kwargs):
                    if phase.startswith('cancellation_'):
                        append_failures.append(phase)
                        raise RuntimeError('injected diagnostic write failure')
                    return original_append(token, event_id, phase, payload, **kwargs)
                with patch.object(runtime.kernel, 'lifecycle_append', side_effect=append), \
                     (patch.object(runtime.kernel, 'lifecycle_reserve', side_effect=reserve)
                      if fail_reserve else nullcontext()):
                    runtime.cancel('job', expected_revision=snapshot.revision, timeout_seconds=3)
                self.assertTrue(reserve_failures if fail_reserve else append_failures,
                                'injected diagnostic failure was not exercised')
                driver.join(10)
                self.assertFalse(driver.is_alive(), 'worker did not stop')
                self.assertEqual(runtime.kernel.get('job').state, 'cancelled')
                with self.assertRaises(ProcessLookupError):
                    os.kill(worker_pid, 0)
            finally:
                try:
                    runtime.close()
                finally:
                    driver.join(10)

    @unittest.skipUnless(os.name == 'posix', 'requires POSIX process supervisor')
    def test_cancellation_stops_process_when_diagnostic_reserve_fails(self):
        self._check_cancellation_stops_process_when_diagnostics_fail(True)

    @unittest.skipUnless(os.name == 'posix', 'requires POSIX process supervisor')
    def test_cancellation_stops_process_when_diagnostic_append_fails(self):
        self._check_cancellation_stops_process_when_diagnostics_fail(False)


if __name__ == '__main__':
    unittest.main()
