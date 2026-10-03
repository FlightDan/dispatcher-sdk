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
    result = context.children.run("child", payload, request_id="one-child", timeout_seconds=5)
    context.activity.progress("parent-received-child")
    return {"child": result, "budget": context.budget.to_dict()}


for handler in (parent, child):
    handler.__execution_kernel_revision__ = "execution-observability-example-v1"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "tasks.sqlite3"
        with Dispatcher(path, {"parent": parent, "child": child}, child_capacity=1) as app:
            task = app.submit("parent", {"value": 42}, request_id="one-input", timeout_seconds=12)
            result = task.wait(timeout=15)
            observation = task.observe(timeout=3)
            print(json.dumps({"status": result["status"], "value": result["value"], "error": result["error"],
                "execution": observation.get("execution"), "settlement": observation.get("settlement"),
                "complete": observation["complete"]}, ensure_ascii=False))
            if result["status"] != "succeeded":
                raise RuntimeError("parent/child example did not succeed")


if __name__ == "__main__":
    main()
