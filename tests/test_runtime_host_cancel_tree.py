from __future__ import annotations

from dataclasses import replace
import json
import os
import sys
from pathlib import Path
import tempfile
import time
import unittest

from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.host import RuntimeHost
from tests.test_runtime_host import RecordingBridge, make_command, wait_until


def cancellable_process_tree(payload, context):
    root = Path(payload["root"])
    child = os.fork()
    if child == 0:
        grandchild = os.fork()
        if grandchild == 0:
            os.setsid()
            (root / "grandchild.tmp").write_text(str(os.getpid()))
            (root / "grandchild.tmp").replace(root / "grandchild.pid")
            time.sleep(30)
            (root / "late.txt").write_text("unexpected descendant effect")
        else:
            time.sleep(30)
        os._exit(0)
    deadline = time.monotonic() + 5
    while not (root / "grandchild.pid").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("grandchild did not start")
        time.sleep(0.01)
    pids = [os.getpid(), child, int((root / "grandchild.pid").read_text())]
    temporary = root / "tree.tmp"
    temporary.write_text(json.dumps(pids))
    temporary.replace(root / "tree.json")
    time.sleep(30)
    return {"unexpected": True}


cancellable_process_tree.__execution_kernel_revision__ = "host-cancel-tree-v1"


def check_previous_tree_gone(payload, context):
    root = Path(payload["root"])
    survivors = []
    for pid in json.loads((root / "tree.json").read_text()):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        survivors.append(pid)
    (root / "successor.json").write_text(json.dumps(survivors))
    if survivors:
        raise RuntimeError(f"slot reused before process cleanup: {survivors}")
    return {"previous_tree_gone": True}


check_previous_tree_gone.__execution_kernel_revision__ = "host-cancel-successor-v1"


@unittest.skipUnless(os.name == "posix" and sys.platform.startswith("linux"),
                     "requires Linux subreaper process containment")
class RuntimeHostCancelTreeTests(unittest.TestCase):
    def test_cancel_reaps_tree_before_return_and_reuses_only_host_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = Kernel.open_sqlite(
                root / "kernel.sqlite3",
                {("tree", 1): cancellable_process_tree, ("echo", 1): check_previous_tree_gone},
                isolation_mode="process",
            )
            host = RuntimeHost(runtime, RecordingBridge(), worker_count=1, pump_interval=0.01)
            first = replace(
                make_command("cancel-tree", runtime.registry_revision),
                handler_id="tree", payload={"root": str(root)}, timeout_seconds=40,
            )
            second = replace(make_command("after-cancel-tree", runtime.registry_revision),
                             payload={"root": str(root)})
            try:
                runtime.submit(first)
                host.start()
                wait_until(lambda: (root / "tree.json").exists(), timeout=8)
                pids = json.loads((root / "tree.json").read_text())
                self.assertEqual(len(set(pids)), 3)
                for pid in pids:
                    os.kill(pid, 0)
                runtime.submit(second)
                time.sleep(0.05)
                self.assertEqual(runtime.kernel.get(first.execution_id).state, "running")
                self.assertEqual(runtime.kernel.get(second.execution_id).state, "queued")
                running = runtime.kernel.get(first.execution_id)
                cancelled = runtime.cancel(
                    first.execution_id, expected_revision=running.revision,
                    reason="exercise strong cancellation",
                )
                self.assertEqual(cancelled.state, "cancelled")
                # No eventual polling here: returning cancel already promises
                # termination, including the grandchild in a new session.
                for pid in pids:
                    with self.assertRaises(ProcessLookupError, msg=f"PID {pid} survived cancel"):
                        os.kill(pid, 0)
                wait_until(lambda: runtime.kernel.get(second.execution_id).state == "succeeded")
                self.assertEqual(json.loads((root / "successor.json").read_text()), [])
                self.assertFalse((root / "late.txt").exists())
            finally:
                self.assertTrue(host.stop(timeout=5))
                self.assertTrue(host.join(0.1))
