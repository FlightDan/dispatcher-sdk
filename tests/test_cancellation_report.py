"""Cancellation evidence must survive restart without inventing cleanup proof."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import ctypes
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from dispatcher_sdk.execution_kernel import CASConflictError, RetryPolicy, Runtime, SandboxHandler, SandboxSpec, SandboxOutcomeUnknown
from dispatcher_sdk.execution_kernel.cancellation import CancellationJournal, inspect_cancellation_journal
from dispatcher_sdk.orchestrator import Orchestrator, Operations, inspect_cancellation
from tests.test_runtime_host import wait_until
from tests.test_runtime_host_cancel_tree import cancellable_process_tree
from tests.test_sandbox_runtime import FileBackend


def echo(payload, context):
    return payload


def kill_supervisor_and_keep_running(payload, context):
    supervisor = os.getppid()
    if supervisor == payload["test_pid"]:
        raise RuntimeError("test handler must run below its own supervisor")
    Path(payload["pid_path"]).write_text(str(os.getpid()))
    os.kill(supervisor, signal.SIGKILL)
    time.sleep(20)
    return {"unexpected": True}


kill_supervisor_and_keep_running.__execution_kernel_revision__ = "cancellation-supervisor-death-v1"


def _crash_after_commit(root):
    runtime = Runtime(str(Path(root) / "kernel.db"), {"echo": echo}, isolation_mode="thread",
                      cancellation_journal_path=str(Path(root) / "cancel.db"), source_id="test-source")
    original = runtime.kernel.cancel
    def commit_and_exit(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(73)
    runtime.kernel.cancel = commit_and_exit
    runtime.cancel("x", expected_revision=runtime.kernel.get("x").revision)


class CancellationReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def stack(self, handlers=None, isolation="thread"):
        runtime = Runtime(str(self.root / "kernel.db"), handlers or {"echo": echo},
                          isolation_mode=isolation, cancellation_journal_path=str(self.root / "cancel.db"),
                          source_id="test-source")
        sdk = Orchestrator(self.root / "app.db", runtime.kernel, runtime=runtime)
        return runtime, sdk

    def setup_task(self, runtime, sdk, handler="echo", payload=None, dispatch=True, retry_policy=None):
        sdk.create_run("run", command_id="create")
        command = runtime.command(handler, execution_id="x", idempotency_key="x",
                                  correlation_id="run", payload=payload or {}, timeout_seconds=40,
                                  retry_policy=retry_policy or RetryPolicy())
        operations = [Operations.add_task("task", command)]
        if dispatch:
            operations.append(Operations.dispatch("task"))
        sdk.apply_operations("run", command_id="add", expected_revision=0, operations=operations)
        if dispatch:
            sdk.flush()
        return command

    def cancel_task(self, sdk):
        sdk.apply_operations("run", command_id="cancel", expected_revision=sdk.get_run("run")["revision"],
                             operations=[Operations.cancel("task", reason="requested")])

    def report(self, sdk, **kwargs):
        return inspect_cancellation(sdk, "run", **kwargs).executions[0]

    def test_before_dispatch_has_no_execution_or_cleanup_claim(self):
        runtime, sdk = self.stack()
        with runtime:
            self.setup_task(runtime, sdk, dispatch=False)
            self.cancel_task(sdk)
            report = self.report(sdk)
            self.assertEqual(report.request_committed.status, "confirmed")
            self.assertEqual(report.command_delivered.status, "not_applicable")
            self.assertIsNone(report.execution_state)
            self.assertEqual(report.local_process_tree_reaped.status, "not_applicable")
            self.assertEqual(report.external_outcome.status, "unknown")

    def test_cancelled_task_does_not_cancel_run_with_running_sibling(self):
        runtime, sdk = self.stack()
        with runtime:
            self.setup_task(runtime, sdk)
            self.cancel_task(sdk)
            sdk.flush()
            sibling = runtime.command("echo", execution_id="sibling", idempotency_key="sibling",
                                      correlation_id="run", payload={}, timeout_seconds=40)
            sdk.apply_operations("run", command_id="sibling", expected_revision=sdk.get_run("run")["revision"],
                                 operations=[Operations.add_task("sibling", sibling), Operations.dispatch("sibling")])
            sdk.flush()
            lease = runtime.kernel.claim("external-sibling")
            runtime.kernel.start(lease)
            sdk.sync_execution("sibling")
            report = inspect_cancellation(sdk, "run")
            self.assertEqual(report.run_state, "running")
            self.assertIsNone(report.run_terminal_state)
            by_task = {item.task_id: item for item in report.executions}
            self.assertEqual(by_task["task"].task_terminal_state, "cancelled")
            self.assertEqual(by_task["sibling"].execution_state, "running")
            self.assertIsNone(by_task["sibling"].task_terminal_state)
            runtime.cancel("sibling", expected_revision=runtime.kernel.get("sibling").revision)

    def test_paging_and_explicit_historical_execution_keep_attempt_identity(self):
        runtime, sdk = self.stack()
        with runtime:
            old_command = self.setup_task(runtime, sdk)
            self.cancel_task(sdk)
            sdk.flush()
            successor = replace(old_command, execution_id="x2", idempotency_key="x2")
            other = replace(old_command, execution_id="z", idempotency_key="z")
            sdk.apply_operations("run", command_id="next", expected_revision=sdk.get_run("run")["revision"],
                                 operations=[Operations.new_attempt("task", successor), Operations.add_task("z", other)])
            first = inspect_cancellation(sdk, "run", limit=1)
            self.assertTrue(first.truncated)
            self.assertEqual(first.executions[0].execution_id, "x2")
            self.assertEqual(first.executions[0].application_attempt, 1)
            self.assertEqual(first.executions[0].receipt_ids, ())
            second = inspect_cancellation(sdk, "run", limit=1, after_task_id=first.next_task_id)
            self.assertFalse(second.truncated)
            self.assertEqual([item.execution_id for item in second.executions], ["z"])
            historical = self.report(sdk, execution_id="x")
            self.assertEqual(historical.execution_id, "x")
            self.assertEqual(historical.application_attempt, 0)
            self.assertEqual(historical.task_terminal_state, "cancelled")
            self.assertTrue(historical.receipt_ids)

    def test_pending_delivery_does_not_revoke_authority_or_mutate_sqlite(self):
        runtime, sdk = self.stack()
        with runtime:
            self.setup_task(runtime, sdk)
            self.cancel_task(sdk)
            paths = [self.root / name for name in ("kernel.db", "app.db", "cancel.db")]
            def dump():
                result = []
                for path in paths:
                    with sqlite3.connect(path) as connection:
                        result.append(tuple(connection.iterdump()))
                return result
            before = dump()
            with patch.object(runtime, "cancel", side_effect=AssertionError("read must not cancel")), \
                 patch.object(runtime, "recover_sandboxes", side_effect=AssertionError("read must not recover")):
                report = self.report(sdk)
            self.assertEqual(report.request_committed.status, "confirmed")
            self.assertEqual(report.command_delivered.status, "pending")
            self.assertEqual(report.execution_authority_revoked.status, "pending")
            self.assertEqual(report.local_process_tree_reaped.status, "unknown")
            self.assertEqual(before, dump())

    def test_running_thread_cancel_never_claims_thread_termination(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        def blocked(payload, context):
            started.set()
            try:
                release.wait(10)
                return "late"
            finally:
                finished.set()
        blocked.__execution_kernel_revision__ = "cancellation-report-thread-v1"
        runtime, sdk = self.stack({"blocked": blocked})
        try:
            self.setup_task(runtime, sdk, handler="blocked")
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(runtime.run_once)
                try:
                    self.assertTrue(started.wait(5))
                    self.cancel_task(sdk)
                    sdk.flush()
                    report = self.report(sdk)
                    self.assertEqual(report.execution_authority_revoked.status, "confirmed")
                    self.assertEqual(report.local_process_tree_reaped.status, "not_applicable")
                    self.assertFalse(finished.is_set())
                finally:
                    release.set()
                future.result(timeout=10)
            self.assertEqual(runtime.kernel.get("x").state, "cancelled")
        finally:
            release.set()
            runtime.close()

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux process containment")
    def test_real_process_tree_receipt_survives_reopen(self):
        runtime, sdk = self.stack({"tree": cancellable_process_tree}, "process")
        try:
            self.setup_task(runtime, sdk, "tree", {"root": str(self.root)})
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(runtime.run_once)
                try:
                    wait_until(lambda: (self.root / "tree.json").exists(), timeout=10)
                    pids = json.loads((self.root / "tree.json").read_text())
                    current = runtime.kernel.get("x")
                    runtime.cancel("x", expected_revision=current.revision)
                    for pid in pids:
                        with self.assertRaises(ProcessLookupError):
                            os.kill(pid, 0)
                    self.assertEqual(self.report(sdk).local_process_tree_reaped.status, "confirmed")
                finally:
                    runtime.close()
                future.result(timeout=10)
        finally:
            runtime.close()
        reopened, sdk = self.stack({"tree": cancellable_process_tree}, "process")
        with reopened:
            report = self.report(sdk)
            self.assertEqual(report.execution_state, "cancelled")
            self.assertEqual(report.local_process_tree_reaped.status, "confirmed")
            self.assertEqual(len(report.receipt_ids), 1)

    def test_stale_revision_records_failure_without_cleanup_proof(self):
        runtime, sdk = self.stack()
        with runtime:
            self.setup_task(runtime, sdk)
            snapshot = runtime.kernel.get("x")
            with self.assertRaises(CASConflictError):
                runtime.cancel("x", expected_revision=snapshot.revision + 1)
            self.assertEqual(runtime.kernel.get("x"), snapshot)
            page = inspect_cancellation_journal(self.root / "cancel.db", source_id="test-source",
                                                kernel_path=self.root / "kernel.db", snapshot=snapshot)
            self.assertEqual(page.receipts[0].phases["failure"]["phase"], "kernel_cancel")
            self.assertNotIn("process_cleanup", page.receipts[0].phases)
            self.assertEqual(self.report(sdk).execution_authority_revoked.status, "pending")

    def test_receipts_cannot_cross_command_attempt_fence_or_source(self):
        runtime, sdk = self.stack()
        with runtime:
            self.setup_task(runtime, sdk)
            runtime.kernel.claim("test-owner")
            snapshot = runtime.kernel.get("x")
            runtime.cancel("x", expected_revision=snapshot.revision)
            snapshot = runtime.kernel.get("x")
            def read(value, source="test-source"):
                return inspect_cancellation_journal(self.root / "cancel.db", source_id=source,
                                                    kernel_path=self.root / "kernel.db", snapshot=value)
            self.assertEqual(len(read(snapshot).receipts), 1)
            # Reader identity filters are independent of execution state; use
            # nonterminal contracts so terminal result identity stays valid.
            query = replace(snapshot, state="queued", result=None, started_at=None)
            for changed in (replace(query, attempt=query.attempt + 1),
                            replace(query, fence=query.fence + 1),
                            replace(query, command=replace(query.command, payload={"changed": True}))):
                self.assertEqual(read(changed).receipts, ())
            with self.assertRaises(ValueError):
                read(snapshot, "other-source")

    def test_missing_and_damaged_journal_readers_do_not_create_or_repair(self):
        runtime, sdk = self.stack()
        with runtime:
            self.setup_task(runtime, sdk)
            missing = self.root / "missing" / "cancel.db"
            report = self.report(sdk, source_id="test-source", cancellation_journal_path=missing)
            self.assertEqual(report.local_process_tree_reaped.status, "unknown")
            self.assertTrue(report.issues)
            self.assertFalse(missing.parent.exists())
            with sqlite3.connect(self.root / "cancel.db") as connection:
                connection.execute("CREATE TABLE unexpected(value)")
            before = (self.root / "cancel.db").read_bytes()
            self.assertTrue(self.report(sdk).issues)
            with self.assertRaises(ValueError):
                CancellationJournal(self.root / "cancel.db", source_id="test-source", kernel_path=self.root / "kernel.db")
            self.assertEqual(before, (self.root / "cancel.db").read_bytes())

    def test_old_supervisor_and_receipt_do_not_prove_new_generation_cleanup(self):
        runtime, sdk = self.stack()
        old_key = None
        try:
            self.setup_task(runtime, sdk, retry_policy=RetryPolicy(max_attempts=3))
            first = runtime.kernel.claim("first-owner", lease_seconds=1)
            snapshot = runtime.kernel.get("x")
            receipt = runtime.cancellation_journal._begin(snapshot, expected_revision=snapshot.revision,
                                                          reason="old request", isolation_mode="process")
            runtime.cancellation_journal._record(receipt, "process_cleanup",
                {"state": "confirmed", "code": "runtime_supervisor_reaped"})
            old_key = ("x", first.attempt, first.fence)
            old_supervisor = Mock()
            runtime._process_supervisors[old_key] = old_supervisor
            with patch.object(runtime.kernel, "_now", return_value=first.expires_at + 1):
                runtime.kernel.reap()
                second = runtime.kernel.claim("second-owner")
                self.assertGreater(second.fence, first.fence)
                self.assertEqual(self.report(sdk).receipt_ids, ())
                runtime.cancel("x", expected_revision=runtime.kernel.get("x").revision)
                old_supervisor.revoke.assert_not_called()
                report = self.report(sdk)
                self.assertEqual(report.local_process_tree_reaped.status, "unknown")
                self.assertNotIn(receipt, report.receipt_ids)
        finally:
            if old_key is not None:
                runtime._process_supervisors.pop(old_key, None)
            runtime.close()

    def test_reopened_thread_runtime_cannot_prove_externally_claimed_cleanup(self):
        runtime, sdk = self.stack()
        self.setup_task(runtime, sdk)
        runtime.kernel.claim("external-worker")
        runtime.close()
        reopened, sdk = self.stack()
        with reopened:
            reopened.cancel("x", expected_revision=reopened.kernel.get("x").revision)
            report = self.report(sdk)
            self.assertEqual(report.execution_authority_revoked.status, "confirmed")
            self.assertEqual(report.local_process_tree_reaped.status, "unknown")

    def test_malformed_phase_evidence_is_unknown_and_not_repaired(self):
        runtime, sdk = self.stack()
        with runtime:
            self.setup_task(runtime, sdk)
            runtime.cancel("x", expected_revision=runtime.kernel.get("x").revision)
            for invalid in ("{", "[]", '{"state":"invented","code":"bad"}',
                            '{"state":[],"code":"bad"}', '{"state":{},"code":"bad"}',
                            '{"state":"confirmed","code":[]}', '{"state":"confirmed","code":{}}'):
                with self.subTest(invalid=invalid):
                    with sqlite3.connect(self.root / "cancel.db") as connection:
                        connection.execute("UPDATE cancellation_stages SET evidence=? WHERE stage='process_cleanup'", (invalid,))
                    with self.assertRaises(ValueError):
                        inspect_cancellation_journal(self.root / "cancel.db", source_id="test-source",
                            kernel_path=self.root / "kernel.db", snapshot=runtime.kernel.get("x"))
                    report = self.report(sdk)
                    self.assertEqual(report.local_process_tree_reaped.status, "unknown")
                    self.assertTrue(report.issues)
                    with sqlite3.connect(self.root / "cancel.db") as connection:
                        self.assertEqual(connection.execute("SELECT evidence FROM cancellation_stages WHERE stage='process_cleanup'").fetchone()[0], invalid)

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux subreaper and supervisor processes")
    def test_dead_supervisor_with_live_worker_never_proves_tree_cleanup(self):
        # Adopt the deliberately orphaned worker so this test can kill AND
        # reap it itself, independently of the container's PID 1 behavior.
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        runtime = None
        reached, release = threading.Event(), threading.Event()
        pid_path = self.root / "orphan.pid"
        try:
            runtime, sdk = self.stack({"orphan": kill_supervisor_and_keep_running}, "process")
            self.setup_task(runtime, sdk, "orphan", {"pid_path": str(pid_path), "test_pid": os.getpid()})
            invoke = runtime._invoke_process
            def pause_after_backend(*args, **kwargs):
                outcome = invoke(*args, **kwargs)
                reached.set()
                if not release.wait(10):
                    raise RuntimeError("test did not release process finalization")
                return outcome
            with patch.object(runtime, "_invoke_process", side_effect=pause_after_backend), \
                 ThreadPoolExecutor(max_workers=2) as executor:
                worker = executor.submit(runtime.run_once)
                try:
                    self.assertTrue(reached.wait(10), "backend did not observe supervisor death")
                    pid = int(pid_path.read_text())
                    os.kill(pid, 0)
                    self.assertNotEqual(Path(f"/proc/{pid}/stat").read_text().split()[2], "Z")
                    current = runtime.kernel.get("x")
                    cancellation = executor.submit(runtime.cancel, "x", expected_revision=current.revision)
                    wait_until(lambda: runtime.kernel.get("x").state == "cancelled", timeout=5)
                    release.set()
                    self.assertEqual(cancellation.result(timeout=10).state, "cancelled")
                    worker.result(timeout=10)
                    # The supervisor has died but the actual handler still
                    # runs. Cancellation must retain this uncertainty.
                    os.kill(pid, 0)
                    self.assertNotEqual(Path(f"/proc/{pid}/stat").read_text().split()[2], "Z")
                    report = self.report(sdk)
                    self.assertEqual(report.execution_authority_revoked.status, "confirmed")
                    self.assertEqual(report.local_process_tree_reaped.status, "unknown")
                    self.assertEqual(report.cleanup.status, "unknown")
                finally:
                    release.set()
        finally:
            release.set()
            try:
                if pid_path.exists():
                    pid = int(pid_path.read_text())
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    wait_until(lambda: os.waitpid(pid, os.WNOHANG)[0] == pid, timeout=5)
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)
            finally:
                try:
                    if runtime is not None:
                        runtime.close()
                finally:
                    self.assertEqual(libc.prctl(36, previous.value, 0, 0, 0), 0)

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux process containment")
    def test_post_commit_journal_failure_still_reaps_real_process_tree(self):
        runtime, sdk = self.stack({"tree": cancellable_process_tree}, "process")
        try:
            self.setup_task(runtime, sdk, "tree", {"root": str(self.root)})
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(runtime.run_once)
                try:
                    wait_until(lambda: (self.root / "tree.json").exists(), timeout=10)
                    pids = json.loads((self.root / "tree.json").read_text())
                    current = runtime.kernel.get("x")
                    with patch.object(runtime.cancellation_journal, "_record", side_effect=OSError("disk failure")):
                        with self.assertRaisesRegex(RuntimeError, "evidence"):
                            runtime.cancel("x", expected_revision=current.revision)
                    self.assertEqual(runtime.kernel.get("x").state, "cancelled")
                    for pid in pids:
                        with self.assertRaises(ProcessLookupError):
                            os.kill(pid, 0)
                    self.assertEqual(self.report(sdk).local_process_tree_reaped.status, "unknown")
                finally:
                    runtime.close()
                future.result(timeout=10)
        finally:
            runtime.close()

    def test_process_exit_after_kernel_commit_does_not_fabricate_restart_receipt(self):
        runtime, sdk = self.stack()
        self.setup_task(runtime, sdk)
        runtime.close()
        child = subprocess.run([sys.executable, "-c",
                                "from tests.test_cancellation_report import _crash_after_commit; "
                                "import sys; _crash_after_commit(sys.argv[1])", str(self.root)],
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 73, child.stderr)
        reopened, sdk = self.stack()
        with reopened:
            report = self.report(sdk)
            self.assertEqual(report.execution_state, "cancelled")
            self.assertEqual(report.execution_authority_revoked.status, "confirmed")
            self.assertEqual(report.local_process_tree_reaped.status, "unknown")
            page = inspect_cancellation_journal(self.root / "cancel.db", source_id="test-source",
                                                kernel_path=self.root / "kernel.db", snapshot=reopened.kernel.get("x"))
            self.assertEqual(len(page.receipts), 1)
            self.assertEqual(page.receipts[0].phases, {})

    def test_lost_create_remains_unknown_after_restart_and_empty_remote_search(self):
        handler = SandboxHandler(FileBackend(str(self.root), "lost_create"), str(self.root / "sandbox.db"),
                                 poll_interval=0.01, operation_timeout=0.2)
        runtime, sdk = self.stack({handler.handler_id: handler}, "process")
        self.setup_task(runtime, sdk, handler.handler_id,
                        SandboxSpec("fixture-image", "print('hello')", ("/usr/bin/python3",), "/tmp").to_payload())
        self.assertEqual(runtime.run_once().state, "recovery_required")
        try:
            report = self.report(sdk)
            self.assertEqual(report.external_outcome.status, "unknown")
            self.assertNotEqual(report.cleanup.status, "confirmed")
            self.assertFalse((self.root / "alive").exists())
        finally:
            with self.assertRaises(SandboxOutcomeUnknown):
                runtime.close()
        reopened, sdk = self.stack({handler.handler_id: handler}, "process")
        try:
            with patch.object(FileBackend, "find", side_effect=AssertionError("inspection contacted provider")):
                report = self.report(sdk)
            self.assertEqual(report.external_outcome.status, "unknown")
            self.assertNotEqual(report.cleanup.status, "confirmed")
        finally:
            with self.assertRaises(SandboxOutcomeUnknown):
                reopened.close()

    def test_collected_remote_result_does_not_imply_cleanup_succeeded(self):
        (self.root / "reject_cleanup").touch()
        handler = SandboxHandler(FileBackend(str(self.root)), str(self.root / "sandbox.db"),
                                 poll_interval=0.01, operation_timeout=0.2)
        runtime, sdk = self.stack({handler.handler_id: handler}, "process")
        try:
            self.setup_task(runtime, sdk, handler.handler_id,
                            SandboxSpec("fixture-image", "print('hello')", ("/usr/bin/python3",), "/tmp").to_payload())
            self.assertEqual(runtime.run_once().state, "recovery_required")
            report = self.report(sdk)
            records = report.external_outcome.details["sandbox_records"]
            self.assertTrue(records[0]["result_known"])
            self.assertFalse(records[0]["cleanup_confirmed"])
            self.assertNotEqual(report.cleanup.status, "confirmed")
        finally:
            (self.root / "reject_cleanup").unlink(missing_ok=True)
            runtime.close()
