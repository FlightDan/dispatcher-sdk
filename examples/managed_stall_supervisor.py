"""Run a reserved process supervisor through the public Dispatcher API."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

from dispatcher_sdk import Dispatcher, ManagedStallOptions, ObservationOptions, StallPolicy


def business(payload, context):
    context.activity.progress("started")
    while not Path(payload["release"]).exists():
        time.sleep(.05)
    return "business completed"


def supervise(notice, context):
    context.activity.progress("notice-inspected")
    return {"notification_id": notice["notification_id"],
            "execution_id": context.command.execution_id,
            "remaining_work_seconds": context.budget.remaining_work_seconds,
            "decision": "continue observing"}


business.__execution_kernel_revision__ = "managed-stall-example-business-v2"
supervise.__execution_kernel_revision__ = "managed-stall-example-supervisor-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    if args.evidence_dir is not None:
        args.evidence_dir.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="sdk-managed-stall-example-", dir=args.evidence_dir))
    release = directory / "release"
    succeeded = False
    try:
        with Dispatcher(directory / "tasks.sqlite3", {"business": business},
                worker_count=1, observation_options=ObservationOptions(flush_interval=.1),
                stall_handler=supervise,
                stall_options=ManagedStallOptions(memory_limit_bytes=512 * 1024 * 1024,
                    capacity=1, timeout_seconds=2, budget_seconds=5)) as app:
            task = app.submit("business", {"release": str(release)},
                request_id="original-work", timeout_seconds=10)
            task.watch_stall(StallPolicy("example-progress", metrics=("progress",),
                sample_interval=.2, consecutive_windows=2, max_deliveries=2))
            deadline = time.monotonic() + 8
            try:
                report = None
                while time.monotonic() < deadline:
                    for notice in app.stall_notifications(state="consumed", limit=4):
                        current = app.stall_supervisor_status(notice["notification_id"])
                        execution = current.get("execution") or {}
                        result = execution.get("result") or {}
                        if result.get("status") == "succeeded":
                            report = current
                            break
                    if report is not None:
                        break
                    time.sleep(.05)
                if report is None:
                    raise RuntimeError("supervisor did not complete within the original wait")
                business_before_release = task.snapshot
                release.touch()
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("original application wait elapsed")
                result = task.wait(timeout=remaining)
                if result["status"] != "succeeded":
                    raise RuntimeError("original business did not succeed: " + repr(result))
                if args.evidence_dir is not None:
                    (directory / "success.json").write_text(json.dumps({
                        "interpreter": sys.executable,
                        "sdk_import": __import__("dispatcher_sdk").__file__,
                        "business_before_release": business_before_release,
                        "business_result": result, "supervisor": report,
                        "bounds": {"supervisor_timeout": 2, "notice_budget": 5,
                                   "business_timeout": 10, "application_wait": 8}}, indent=2), encoding="utf-8")
                print(json.dumps({"business": result["status"],
                    "supervisor": report["execution"]["result"]["value"],
                    "capacity": report["capacity"], "memory_limit_bytes": report["memory_limit_bytes"]}))
            except BaseException as error:
                evidence = {"error_type": type(error).__name__, "error": str(error),
                    "interpreter": sys.executable,
                    "sdk_import": __import__("dispatcher_sdk").__file__,
                    "bounds": {"supervisor_timeout": 2, "notice_budget": 5,
                               "business_timeout": 10, "application_wait": 8}}
                try:
                    evidence.update(business=task.snapshot, supervisor=app.stall_supervisor_status(),
                        notices=[app.stall_supervisor_status(notice["notification_id"])
                                 for notice in app.stall_notifications(limit=4)])
                except Exception as inspection_error:
                    evidence["inspection_error"] = repr(inspection_error)
                (directory / "failure.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print("managed_stall_evidence=" + str(directory), file=sys.stderr, flush=True)
                raise
            finally:
                release.touch()
        succeeded = True
    finally:
        if succeeded and args.evidence_dir is None:
            shutil.rmtree(directory)


if __name__ == "__main__":
    main()
