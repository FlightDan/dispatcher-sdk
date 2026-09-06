"""Show Linux process isolation cleaning up a timed-out handler tree."""

import os
from pathlib import Path
import sys
import tempfile
import time

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy


def sleep_with_child(payload, _context):
    child = os.fork()
    if child == 0:
        time.sleep(30)
        os._exit(0)
    Path(payload["pid_file"]).write_text(f"{os.getpid()} {child}", encoding="ascii")
    time.sleep(30)


sleep_with_child.__execution_kernel_revision__ = "isolation-timeout-v1"


def echo(payload, _context):
    return payload


echo.__execution_kernel_revision__ = "isolation-timeout-v1"


def command(runtime, execution_id, handler_id, payload, timeout_seconds):
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=execution_id,
        registry_revision=runtime.registry_revision,
        correlation_id=execution_id,
        causation_id=None,
        handler_id=handler_id,
        handler_contract_version=1,
        retry_policy=RetryPolicy(max_attempts=1),
        timeout_seconds=timeout_seconds,
        payload=payload,
    )


def assert_gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    raise AssertionError(f"PID {pid} survived timeout cleanup")


def main():
    if os.name != "posix" or not sys.platform.startswith("linux"):
        raise SystemExit("This example requires Linux process isolation.")

    with tempfile.TemporaryDirectory(prefix="dispatcher-isolation-") as directory:
        root = Path(directory)
        pid_file = root / "pids.txt"
        handlers = {"sleep": sleep_with_child, "echo": echo}
        with Kernel.open_sqlite(root / "jobs.sqlite3", handlers, isolation_mode="process") as runtime:
            runtime.submit(command(runtime, "timeout", "sleep", {"pid_file": str(pid_file)}, 2))
            timed_out = runtime.run_once()
            assert timed_out.state == "timed_out", timed_out.state
            assert timed_out.result.error.code == "handler_timeout"
            assert pid_file.exists(), "timed-out handler never reached startup"
            pids = [int(value) for value in pid_file.read_text(encoding="ascii").split()]
            assert len(pids) == 2, pids
            for pid in pids:
                assert_gone(pid)
            print("timeout: timed_out; handler and child are gone")

            runtime.submit(command(runtime, "next", "echo", {"message": "reused"}, 2))
            succeeded = runtime.run_once()
            assert succeeded.state == "succeeded"
            assert succeeded.result.value == {"message": "reused"}
            print("next task: succeeded")


if __name__ == "__main__":
    main()
