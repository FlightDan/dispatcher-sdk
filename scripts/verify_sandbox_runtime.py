"""Opt-in Runtime/OpenSandbox integration probe against an isolated real service."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import base64
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="create and destroy real disposable sandboxes")
    parser.add_argument("--image", default="python:3.12.10-slim-bookworm")
    arguments = parser.parse_args()
    if not arguments.live:
        print("Set OPEN_SANDBOX_DOMAIN / OPEN_SANDBOX_API_KEY and pass --live against an isolated test service.")
        return
    from dispatcher_sdk.execution_kernel import (
        Runtime, SandboxHandler, SandboxSpec, EffectRecoveryRequiredError,
    )
    from dispatcher_sdk.adapters import OpenSandboxBackend, verify_backend

    backend = OpenSandboxBackend(os.environ["OPEN_SANDBOX_DOMAIN"], sandbox_ttl_seconds=300)
    root = Path(tempfile.mkdtemp(prefix="dispatcher-runtime-live-"))
    print(json.dumps({"durable_evidence_directory": str(root)}), flush=True)
    handler = SandboxHandler(backend, str(root / "journal.db"), operation_timeout=60)
    fixture = SandboxSpec(arguments.image,
        "from pathlib import Path\nprint('runtime-e2e-success')\nPath('/tmp/result.txt').write_text('retained')\n",
        ("/usr/local/bin/python3",), "/tmp", artifacts=("/tmp/result.txt",))
    descendant = SandboxSpec(arguments.image,
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(240)'],start_new_session=True)\n"
        "Path('/tmp/descendant.pid').write_text(str(child.pid))\ntime.sleep(240)\n",
        ("/usr/local/bin/python3",), "/tmp")
    report = verify_backend(backend, fixture, timeout=120)
    assert report["cleanup_confirmed"]
    print(json.dumps({"community_conformance_harness": "passed"}), flush=True)
    with Runtime(root / "kernel.db", {handler.handler_id: handler}) as runtime:
        def submit(identity, spec, timeout):
            command = runtime.command(handler.handler_id, execution_id=identity, idempotency_key=identity,
                correlation_id="sandbox-runtime-probe", timeout_seconds=timeout, payload=spec.to_payload())
            runtime.submit(command)

        submit("success", fixture, 120)
        result = runtime.run_once()
        assert result.state == "succeeded", result
        assert base64.b64decode(result.result.value["output"]["artifacts"][0]["data"]) == b"retained"
        assert handler.journal().get("success")["result"] == result.result.value
        print(json.dumps({"runtime_success_result_and_artifact": "passed"}), flush=True)

        submit("timeout", descendant, 12)
        result = runtime.run_once()
        record = handler.journal().get("timeout")
        assert result.state == "recovery_required", result
        assert record["command_id"] and record["cleanup_confirmed"], record
        assert backend.find(record["operation_key"], timeout=15) == ()
        print(json.dumps({"runtime_timeout_remote_disposal": "passed"}), flush=True)

        submit("cancel", descendant, 120)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(runtime.run_once)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                record = handler.journal().get("cancel")
                if record is not None and record["command_id"]:
                    break
                time.sleep(0.1)
            assert record is not None and record["command_id"], record
            # The command remains running while the remote child starts.
            time.sleep(0.5)
            current = runtime.kernel.get("cancel")
            try:
                runtime.cancel("cancel", expected_revision=current.revision)
            except EffectRecoveryRequiredError:
                pass
            else:
                raise AssertionError("interrupted external effect must require recovery")
            assert handler.journal().get("cancel")["cleanup_confirmed"]
            assert backend.find(record["operation_key"], timeout=15) == ()
            assert future.result(timeout=30).state == "recovery_required"
        print(json.dumps({"runtime_cancel_confirmed_before_return": "passed"}), flush=True)
    print(json.dumps({"runtime_close": "passed", "all_test_resources_disposed": True}), flush=True)


if __name__ == "__main__":
    main()
