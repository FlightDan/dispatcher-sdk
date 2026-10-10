"""Observe a real process parent and child through the public SDK facade."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from dispatcher_sdk import Dispatcher


def child(payload, context):
    context.activity.enable_stream("stdout")
    process = subprocess.Popen(
        [sys.executable, "-c", "import os; os.write(1, b'raw bytes without newline')"],
        stdout=subprocess.PIPE)
    observation = context.activity.observe_process(process, role="agent")
    assert process.stdout is not None
    with context.activity.wait("tool_response", target="local-python"):
        chunk = process.stdout.read(4096)
        context.activity.report_bytes("stdout", chunk)
        process.stdout.close()
        process.wait(timeout=2)
    context.activity.tool("response")
    context.activity.progress("child-returned")
    return {"value": payload["value"], "byte_count": len(chunk),
            "process": observation.snapshot()["state"]}


def parent(payload, context):
    # This smoke example includes child process startup and result delivery in
    # its finite call window; native Windows startup can exceed five seconds.
    result = context.children.run("child", payload, request_id="one-child", timeout_seconds=30)
    context.activity.progress("parent-received-child")
    return {"child": result, "budget": context.budget.to_dict()}


for handler in (parent, child):
    handler.__execution_kernel_revision__ = "execution-observability-example-v2"


def observe_for_diagnostics(task):
    try:
        return task.observe(timeout=3)
    except Exception as exc:
        return {"complete": False,
                "observation_error": {"type": type(exc).__name__, "message": str(exc)}}


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "tasks.sqlite3"
        with Dispatcher(path, {"parent": parent, "child": child}, child_capacity=1) as app:
            task = app.submit("parent", {"value": 42}, request_id="one-input", timeout_seconds=60)
            # Caller waiting also includes the parent's process startup.
            try:
                result = task.wait(timeout=120)
            except Exception as exc:
                print(json.dumps({"wait_error": {"type": type(exc).__name__, "message": str(exc)},
                                  "observation": observe_for_diagnostics(task)}, ensure_ascii=False))
                raise
            observation = observe_for_diagnostics(task)
            print(json.dumps({"status": result["status"], "value": result["value"], "error": result["error"],
                "execution": observation.get("execution"), "settlement": observation.get("settlement"),
                "complete": observation["complete"]}, ensure_ascii=False))
            if result["status"] != "succeeded":
                print(json.dumps({"result": result, "observation": observation}, ensure_ascii=False))
                raise RuntimeError("parent/child example did not succeed")
            try:
                child_result = result["value"]["child"]
                if (child_result["status"] != "succeeded" or child_result["value"]["value"] != 42
                        or child_result["value"]["byte_count"] != len(b"raw bytes without newline")):
                    raise RuntimeError("parent/child example returned unexpected output")
                if "observation_error" in observation:
                    raise RuntimeError("parent/child example observation failed")
            except (KeyError, TypeError, RuntimeError):
                print(json.dumps({"result": result, "observation": observation}, ensure_ascii=False))
                raise


if __name__ == "__main__":
    main()
