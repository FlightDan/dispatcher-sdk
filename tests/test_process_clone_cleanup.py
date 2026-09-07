"""Real Linux clone children, including waitpid's non-SIGCHLD exclusion."""

from __future__ import annotations

import ctypes
import multiprocessing
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.execution_kernel import _process_runtime as process_runtime


_CLONE_HELPER = r"""
#define _GNU_SOURCE
#include <errno.h>
#include <sched.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

static int detached_child(void *argument) {
    int *ready = argument;
    close(ready[0]);
    if (setsid() < 0) _exit(71);
    /* A broken regression must not leave an indefinitely running process. */
    signal(SIGALRM, SIG_DFL);
    alarm(15);
    if (write(ready[1], "R", 1) != 1) _exit(72);
    close(ready[1]);
    for (;;) pause();
}

int spawn_clone_child(void) {
    int ready[2];
    if (pipe(ready) < 0) return -1;
    size_t size = 1024 * 1024;
    void *stack = mmap(NULL, size, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (stack == MAP_FAILED) {
        close(ready[0]); close(ready[1]); return -1;
    }
    /* Zero exit signal: waitpid without __WALL excludes this real child. */
    int pid = clone(detached_child, (char *)stack + size, 0, ready);
    int saved_errno = errno;
    munmap(stack, size);
    close(ready[1]);
    if (pid >= 0) {
        char value;
        if (read(ready[0], &value, 1) != 1 || value != 'R') {
            kill(pid, SIGKILL);
            saved_errno = EIO;
            pid = -1;
        }
    }
    close(ready[0]);
    errno = saved_errno;
    return pid;
}
"""


def _identity(pid):
    try:
        # comm can contain spaces and parentheses; starttime is stat field 22.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except FileNotFoundError:
        return None
    return fields[19]


def _spawn_clone(library_path):
    library = ctypes.CDLL(library_path, use_errno=True)
    library.spawn_clone_child.restype = ctypes.c_int
    pid = library.spawn_clone_child()
    if pid < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    # Verify that the helper really produced the wait class under test.
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return pid
    raise AssertionError("ordinary waitpid unexpectedly included clone child")


def _clone_proof(library_path, sender):
    process_runtime._enable_linux_subreaper()
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    pid = _spawn_clone(library_path)
    identity = _identity(pid)
    try:
        ordinary_empty = process_runtime._reap_children()
        all_empty = process_runtime._reap_children(all_children=True)
        contained = process_runtime._contain_tree(
            os.getpid(), pid, time.monotonic() + 2, subreaper=True
        )
        sender.send({"ordinary_empty": ordinary_empty, "all_empty": all_empty,
                     "contained": contained, "still_present": _identity(pid) == identity,
                     "empty_after": process_runtime._reap_children(all_children=True)})
    finally:
        process_runtime._contain_tree(os.getpid(), pid, time.monotonic() + 2, subreaper=True)
        sender.close()


def clone_cleanup_handler(payload, context):
    pid = _spawn_clone(payload["library"])
    Path(payload["root"], "clone").write_text(f"{pid} {_identity(pid)}")
    if payload["outcome"] == "success":
        return {"completed": True}
    time.sleep(10)
    return {"unexpected": True}


clone_cleanup_handler.__execution_kernel_revision__ = "real-clone-cleanup-v1"


@unittest.skipUnless(sys.platform.startswith("linux") and Path("/proc/self/task").is_dir(),
                     "requires Linux clone and subreaper process containment")
class ProcessCloneCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        if compiler is None:
            raise unittest.SkipTest("real clone regression requires a C compiler (cc)")
        cls.build = tempfile.TemporaryDirectory(prefix="dispatcher-clone-")
        cls.addClassCleanup(cls.build.cleanup)
        source = Path(cls.build.name, "clone.c")
        cls.library = str(Path(cls.build.name, "clone.so"))
        source.write_text(_CLONE_HELPER)
        subprocess.run([compiler, "-shared", "-fPIC", "-O2", "-Wall", "-Wextra",
                        str(source), "-o", cls.library], check=True, capture_output=True, timeout=30)

    def test_real_clone_requires_wall_before_echild_can_prove_containment(self):
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_clone_proof, args=(self.library, sender))
        process.start()
        sender.close()
        try:
            self.assertTrue(receiver.poll(10), "clone probe did not complete")
            result = receiver.recv()
            process.join(3)
            self.assertEqual(process.exitcode, 0)
            self.assertTrue(result["ordinary_empty"])
            self.assertFalse(result["all_empty"])
            self.assertTrue(result["contained"])
            self.assertFalse(result["still_present"])
            self.assertTrue(result["empty_after"])
        finally:
            if process.is_alive():
                process_runtime._kill_supervisor(process)
            receiver.close()
            process.close()

    def test_success_and_timeout_reap_detached_clone_without_harming_sibling(self):
        sibling = multiprocessing.get_context("spawn").Process(target=time.sleep, args=(30,))
        sibling.start()
        try:
            for outcome in ("success", "timeout"):
                with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as root:
                    runtime = Kernel.open_sqlite(Path(root, "kernel.sqlite3"),
                                                 {"clone": clone_cleanup_handler},
                                                 isolation_mode="process")
                    try:
                        runtime.submit(ExecutionCommandV2(
                            execution_id="clone", idempotency_key="clone",
                            registry_revision=runtime.registry_revision, correlation_id="clone",
                            causation_id=None, handler_id="clone", handler_contract_version=1,
                            retry_policy=RetryPolicy(), timeout_seconds=0.5 if outcome == "timeout" else 5,
                            payload={"root": root, "library": self.library, "outcome": outcome},
                        ))
                        runtime.run_once()
                        self.assertEqual(runtime.kernel.get("clone").state,
                                         "succeeded" if outcome == "success" else "timed_out")
                        pid, identity = Path(root, "clone").read_text().split()
                        # Check at the returned terminal boundary, with no eventual polling.
                        # Zombies still have stat entries and therefore fail this assertion.
                        self.assertNotEqual(_identity(int(pid)), identity)
                        self.assertTrue(sibling.is_alive())
                    finally:
                        runtime.close()
        finally:
            if sibling.is_alive():
                sibling.terminate()
            sibling.join(3)
            sibling.close()


if __name__ == "__main__":
    unittest.main()
