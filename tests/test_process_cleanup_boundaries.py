"""Real-process boundaries for subreaper cleanup and parent teardown races."""

from __future__ import annotations

import errno
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime


def _record_pid(root):
    descriptor = os.open(str(Path(root) / "pids"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
    finally:
        os.close(descriptor)


def _wait_file(path, timeout=5):
    until = time.monotonic() + timeout
    while not Path(path).exists():
        if time.monotonic() >= until:
            raise RuntimeError(f"process did not publish {path}")
        time.sleep(0.001)


def _sleep_child(root):
    _record_pid(root)
    Path(root, "descendant-ready").touch()
    time.sleep(10)
    os._exit(0)


def _spawn_tree(root, topology):
    def fork_child():
        child = os.fork()
        if child != 0:
            return
        if topology in {"double_fork", "churn"}:
            _record_pid(root)
            if os.fork() != 0:
                os._exit(0)
        if topology != "fork":
            os.setsid()
        if topology == "churn":
            _record_pid(root)
            # Bounded producer, still forking when cleanup starts. Its
            # children also detach, so neither one group nor one scan suffices.
            for index in range(24):
                if os.fork() == 0:
                    os.setsid()
                    _sleep_child(root)
                if index == 0:
                    _wait_file(Path(root, "descendant-ready"))
                time.sleep(0.002)
            time.sleep(10)
            os._exit(0)
        _sleep_child(root)

    if topology == "thread_fork":
        thread = threading.Thread(target=fork_child)
        thread.start()
        thread.join()
    else:
        fork_child()
    _wait_file(Path(root, "descendant-ready"))


def _surviving_pids(root):
    surviving = []
    for pid in {int(value) for value in Path(root, "pids").read_text().split()}:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        surviving.append(pid)
    return surviving


def _proof_probe(root, sender, hide_proc):
    process_runtime._enable_linux_subreaper()
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    worker = os.fork()
    if worker == 0:
        sender.close()
        os.setpgid(0, 0)
        _record_pid(root)
        _spawn_tree(root, "double_fork")
        os._exit(0)
    try:
        # The original worker is gone, but its detached child is now ours.
        os.waitpid(worker, 0)
        empty_with_live_orphan = process_runtime._reap_children(all_children=True)
        hidden_result = None
        if hide_proc:
            with patch.object(process_runtime, "_child_process_ids", return_value=()):
                hidden_result = process_runtime._contain_tree(
                    os.getpid(), worker, time.monotonic() + 0.01, subreaper=True
                )
        contained = process_runtime._contain_tree(
            os.getpid(), worker, time.monotonic() + 2, subreaper=True
        )
        sender.send({
            "empty_with_live_orphan": empty_with_live_orphan,
            "hidden_result": hidden_result,
            "contained": contained,
            "survivors": _surviving_pids(root),
            "empty_after": process_runtime._reap_children(all_children=True),
        })
    finally:
        process_runtime._contain_tree(os.getpid(), worker, time.monotonic() + 2, subreaper=True)
        sender.close()


def _race_supervisor(root, topology, delay, sender):
    os.setsid()
    process_runtime._enable_linux_subreaper()
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    ready_read, ready_write = os.pipe()
    worker = os.fork()
    if worker == 0:
        sender.close()
        os.close(ready_read)
        os.setpgid(0, 0)
        _record_pid(root)
        _spawn_tree(root, topology)
        os.write(ready_write, b"ready")
        os.close(ready_write)
        time.sleep(10)
        os._exit(0)
    os.close(ready_write)
    try:
        if os.read(ready_read, 5) != b"ready":
            raise RuntimeError("worker failed to create its tree")
        sender.send(True)
        time.sleep(delay)
        process_runtime._contain_tree(os.getpid(), worker, time.monotonic() + 2, subreaper=True)
    finally:
        process_runtime._contain_tree(os.getpid(), worker, time.monotonic() + 2, subreaper=True)
        os.close(ready_read)
        sender.close()


def cleanup_boundary_handler(payload, context):
    root = payload["root"]
    _record_pid(root)
    _spawn_tree(root, payload["topology"])
    Path(root, "handler-ready").touch()
    if payload["outcome"] == "success":
        return {"completed": True}
    if payload["outcome"] == "exit":
        os._exit(19)
    time.sleep(10)
    return {"unexpected": True}


cleanup_boundary_handler.__execution_kernel_revision__ = "process-cleanup-boundaries-v1"


@unittest.skipUnless(sys.platform.startswith("linux") and Path("/proc/self/task").is_dir(),
                     "requires Linux subreaper process containment")
class ProcessCleanupBoundaryTests(unittest.TestCase):
    def test_echild_requires_orphans_gone_even_when_proc_looks_empty(self):
        context = multiprocessing.get_context("spawn")
        for hide_proc in (False, True):
            with self.subTest(hide_proc=hide_proc), tempfile.TemporaryDirectory() as root:
                receiver, sender = context.Pipe(duplex=False)
                process = context.Process(target=_proof_probe, args=(root, sender, hide_proc))
                process.start()
                sender.close()
                try:
                    self.assertTrue(receiver.poll(10))
                    result = receiver.recv()
                    process.join(3)
                    self.assertEqual(process.exitcode, 0)
                    self.assertFalse(result["empty_with_live_orphan"])
                    if hide_proc:
                        self.assertFalse(result["hidden_result"])
                    self.assertTrue(result["contained"])
                    self.assertTrue(result["empty_after"])
                    self.assertEqual(result["survivors"], [])
                finally:
                    if process.is_alive():
                        process_runtime._kill_supervisor(process)
                    receiver.close()
                    process.close()

    def test_reap_errors_are_not_empty_tree_proofs(self):
        with patch.object(process_runtime.os, "waitpid", side_effect=OSError(errno.EINVAL, "probe")):
            self.assertFalse(process_runtime._reap_children(all_children=True))
        with self.assertRaisesRegex(ValueError, "own tree"):
            process_runtime._contain_tree(os.getpid() + 1, 1, time.monotonic(), subreaper=True)

    def test_reaped_supervisor_pid_is_never_used_to_signal_a_reused_group(self):
        process = multiprocessing.get_context("spawn").Process(target=time.sleep, args=(0,))
        process.start()
        process.join(5)
        try:
            self.assertEqual(process.exitcode, 0)
            # Simulate its old PID having already become an unrelated group.
            with patch.object(process_runtime.os, "getpgid", return_value=process.pid) as lookup, \
                    patch.object(process_runtime.os, "killpg") as kill:
                self.assertTrue(process_runtime._kill_supervisor(process))
                lookup.assert_not_called()
                kill.assert_not_called()
        finally:
            process.close()

    def test_parent_teardown_races_leave_no_descendants_or_sibling_damage(self):
        context = multiprocessing.get_context("spawn")
        # A separately parented process must never be reaped or signalled by
        # cleanup, including when the supervisor exits during parent teardown.
        sibling = context.Process(target=time.sleep, args=(30,))
        sibling.start()
        try:
            for topology in ("fork", "double_fork", "thread_fork", "churn"):
                for delay in (0, 0.001, 0.005, 0.02):
                    with self.subTest(topology=topology, delay=delay), tempfile.TemporaryDirectory() as root:
                        receiver, sender = context.Pipe(duplex=False)
                        process = context.Process(target=_race_supervisor,
                                                  args=(root, topology, delay, sender))
                        process.start()
                        sender.close()
                        try:
                            self.assertTrue(receiver.poll(10))
                            self.assertTrue(receiver.recv())
                            # Alternate parent-first and supervisor-first races.
                            if delay == 0:
                                time.sleep(0.002)
                            self.assertTrue(process_runtime._kill_supervisor(process))
                            self.assertEqual(_surviving_pids(root), [])
                            self.assertTrue(sibling.is_alive())
                        finally:
                            if process.is_alive():
                                process_runtime._kill_supervisor(process)
                            receiver.close()
                            process.close()
        finally:
            sibling.terminate()
            sibling.join(3)
            sibling.close()

    def test_real_runtime_success_exit_timeout_and_cancel_contain_churning_tree(self):
        for outcome in ("success", "exit", "timeout", "cancel"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as root:
                runtime = Kernel.open_sqlite(Path(root, "kernel.sqlite3"),
                                             {"tree": cleanup_boundary_handler}, isolation_mode="process")
                command = ExecutionCommandV2(
                    execution_id="tree", idempotency_key="tree", registry_revision=runtime.registry_revision,
                    correlation_id="tree", causation_id=None, handler_id="tree", handler_contract_version=1,
                    retry_policy=RetryPolicy(), timeout_seconds=0.3 if outcome in {"exit", "timeout"} else 5,
                    payload={"root": root, "topology": "churn", "outcome": outcome},
                )
                results, errors = [], []

                def drive():
                    try:
                        results.append(runtime.run_once())
                    except BaseException as error:
                        errors.append(error)

                driver = threading.Thread(target=drive)
                try:
                    runtime.submit(command)
                    driver.start()
                    if outcome == "cancel":
                        _wait_file(Path(root, "handler-ready"))
                        running = runtime.kernel.get("tree")
                        cancelled = runtime.cancel("tree", expected_revision=running.revision, reason="probe")
                        self.assertEqual(cancelled.state, "cancelled")
                        # Cancellation's return, not eventual polling, is the boundary.
                        self.assertEqual(_surviving_pids(root), [])
                    driver.join(10)
                    self.assertFalse(driver.is_alive())
                    self.assertEqual(errors, [])
                    self.assertEqual(len(results), 1)
                    # The exited worker's descendants inherit its channel, so
                    # that case reaches the deadline before EOF, as before.
                    expected = {"success": "succeeded", "exit": "timed_out", "timeout": "timed_out", "cancel": "cancelled"}
                    self.assertEqual(runtime.kernel.get("tree").state, expected[outcome])
                    self.assertEqual(_surviving_pids(root), [])
                finally:
                    runtime.close()
                    if driver.is_alive():
                        driver.join(5)


if __name__ == "__main__":
    unittest.main()
