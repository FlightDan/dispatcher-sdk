"""Opt-in checks against a real OpenSandbox server; never substitutes a mock.

Install opensandbox==0.1.16 in a disposable venv. Set OPEN_SANDBOX_DOMAIN and
OPEN_SANDBOX_API_KEY, then pass --live. Only the sandbox created here is destroyed.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import timedelta
import json
import logging
import os
import shlex
import time
import uuid


def verify_adapter(image: str) -> None:
    """Exercise this repository's adapter against real provider APIs."""
    from dispatcher_sdk.adapters import OpenSandboxBackend
    from dispatcher_sdk.execution_kernel.sandbox_contracts import SandboxSpec

    backend = OpenSandboxBackend(os.environ["OPEN_SANDBOX_DOMAIN"], sandbox_ttl_seconds=300,
                                 max_output_bytes=16, max_artifact_bytes=32,
                                 max_total_artifact_bytes=64)
    spec = SandboxSpec(
        image=image,
        source=("import sys\nfrom pathlib import Path\nprint('x'*50)\n"
                "print('err', file=sys.stderr)\n"
                "Path(\"result 'quoted'.bin\").write_bytes(b'payload')\nsys.exit(7)\n"),
        interpreter=("/usr/local/bin/python3", "-u"), cwd="/tmp",
        artifacts=("result 'quoted'.bin",), resources={"cpu": "1", "memory": "256Mi"},
    )
    key = "adapter-live-" + uuid.uuid4().hex
    print(json.dumps({"phase": "adapter", "operation_key": key}), flush=True)
    sandbox_id = backend.create(spec, operation_key=key, timeout=60)
    print(json.dumps({"adapter_created": sandbox_id}), flush=True)
    try:
        assert backend.find(key, timeout=10) == (sandbox_id,)
        command_id = backend.start(sandbox_id, spec, timeout=20)
        for _ in range(100):
            observation = backend.inspect(sandbox_id, command_id, timeout=10)
            if observation.state in ("succeeded", "failed"):
                break
            time.sleep(.1)
        assert observation.state == "failed" and observation.exit_code == 7
        result = backend.collect(sandbox_id, command_id, spec, timeout=20)
        assert result["exit_code"] == 7
        assert base64.b64decode(result["stdout"]["data"]) == b"x" * 16
        assert result["stdout"]["truncated"] and result["stdout"]["sha256"] is None
        assert base64.b64decode(result["stderr"]["data"]) == b"err\n"
        assert base64.b64decode(result["artifacts"][0]["data"]) == b"payload"
        print(json.dumps({"actual_adapter_start_inspect_collect": "passed", "exit_code": 7,
                          "bounded_stdout": 16, "quoted_artifact": "passed"}), flush=True)
    finally:
        assert backend.terminate(sandbox_id, timeout=20)
        assert backend.find(key, timeout=10) == ()
        print(json.dumps({"actual_adapter_terminate_confirmed_absent": True}), flush=True)


async def verify_response_loss(image: str) -> None:
    """Discard successful real HTTP responses, never replace the remote service."""
    import httpx
    from opensandbox import Sandbox
    from opensandbox.config import ConnectionConfig
    from opensandbox.exceptions import SandboxApiException
    from opensandbox.manager import SandboxManager
    from opensandbox.models.execd import RunCommandOpts
    from opensandbox.models.sandboxes import SandboxFilter
    from opensandbox.transport import RetryPolicy

    class DiscardResponse(httpx.AsyncBaseTransport):
        def __init__(self, suffix: str) -> None:
            self.inner = httpx.AsyncHTTPTransport()
            self.suffix = suffix
            self.dropped = False

        async def handle_async_request(self, request):
            response = await self.inner.handle_async_request(request)
            if (not self.dropped and request.method == "POST"
                    and request.url.path.endswith(self.suffix) and 200 <= response.status_code < 300):
                await response.aread()
                await response.aclose()
                self.dropped = True
                raise httpx.ReadError("intentional validation response loss", request=request)
            return response

        async def aclose(self):
            await self.inner.aclose()

    def config(transport=None):
        options = dict(use_server_proxy=True, disable_metrics=True,
                       retry_policy=RetryPolicy.disabled(), request_timeout=timedelta(seconds=120))
        if transport is not None:
            options["transport"] = transport
        return ConnectionConfig(**options)

    token = uuid.uuid4().hex
    print(json.dumps({"phase": "response_loss", "operation_token": token}), flush=True)
    create_transport = DiscardResponse("/v1/sandboxes")
    command_transport = DiscardResponse("/command")
    manager = await SandboxManager.create(connection_config=config())
    sandboxes = []
    ids = []
    try:
        lost = False
        try:
            unexpected = await Sandbox.create(
                image, timeout=timedelta(minutes=5), ready_timeout=timedelta(seconds=120),
                metadata={"dispatcher_validation": token}, connection_config=config(create_transport))
            ids.append(unexpected.id)
            sandboxes.append(unexpected)
        except Exception:
            lost = True
        assert lost and create_transport.dropped, "successful create response was not discarded"
        page = 1
        while True:
            matches = await manager.list_sandbox_infos(SandboxFilter(
                metadata={"dispatcher_validation": token}, page=page, page_size=100))
            for info in matches.sandbox_infos:
                assert info.metadata.get("dispatcher_validation") == token
                ids.append(info.id)
            if not matches.pagination.has_next_page:
                break
            page += 1
            assert page <= 100, "discovery pagination exceeded test bound"
        assert len(ids) == 1, "create recovery was not uniquely discoverable; do not blindly recreate"
        sandbox = await Sandbox.connect(ids[0], connection_config=config())
        faulty = await Sandbox.connect(ids[0], connection_config=config(command_transport))
        sandboxes.extend((sandbox, faulty))
        print(json.dumps({"lost_create_discovered": True, "sandbox_id": ids[0]}), flush=True)
        marker = "/tmp/dispatcher-response-loss-" + token
        command = "printf 'applied\\n' >> " + shlex.quote(marker)
        lost = False
        try:
            await faulty.commands.run(command, opts=RunCommandOpts(background=True))
        except Exception:
            lost = True
        assert lost and command_transport.dropped
        for _ in range(100):
            try:
                content = await sandbox.files.read_file(marker)
                if content == "applied\n":
                    break
            except SandboxApiException as exc:
                if exc.status_code != 404:
                    raise
            await asyncio.sleep(.1)
        else:
            raise AssertionError("lost-response command effect not observed")
        # Deliberately duplicate this harmless task-owned marker write to expose
        # the production danger of treating response loss as not_applied.
        await sandbox.commands.run(command, opts=RunCommandOpts(background=True))
        for _ in range(100):
            if await sandbox.files.read_file(marker) == "applied\napplied\n":
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError("duplicate marker write not observed")
        print(json.dumps({"lost_start_applied": True, "blind_retry_duplicates": True}), flush=True)
    finally:
        cleanup_failed = False
        for sandbox_id in set(ids):
            try:
                await manager.kill_sandbox(sandbox_id)
            except Exception:
                pass
            try:
                await manager.get_sandbox_info(sandbox_id)
            except SandboxApiException as exc:
                cleanup_failed = cleanup_failed or exc.status_code != 404
            except Exception:
                cleanup_failed = True
            else:
                cleanup_failed = True
        for sandbox in sandboxes:
            await sandbox.close()
        await manager.close()
        await create_transport.aclose()
        await command_transport.aclose()
        if cleanup_failed:
            raise AssertionError("test sandbox destruction was not confirmed")


async def verify(image: str) -> None:
    from opensandbox import Sandbox
    from opensandbox.config import ConnectionConfig
    from opensandbox.exceptions import SandboxApiException
    from opensandbox.models.execd import RunCommandOpts
    from opensandbox.manager import SandboxManager
    from opensandbox.transport import RetryPolicy

    def config():
        return ConnectionConfig(
            use_server_proxy=True, disable_metrics=True,
            request_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy.disabled(),
        )

    token = uuid.uuid4().hex
    print(json.dumps({"phase": "creating", "operation_token": token}), flush=True)
    sandbox = await Sandbox.create(
        image, connection_config=config(), timeout=timedelta(minutes=5),
        ready_timeout=timedelta(seconds=120),
        metadata={"dispatcher_validation": token},
    )
    sandbox_id = sandbox.id
    print(json.dumps({"sandbox_id": sandbox_id}), flush=True)
    destroyed = False
    try:
        execution = await sandbox.commands.run(
            "printf 'first\\n'; sleep 2; printf 'last\\n'; exit 7",
            opts=RunCommandOpts(background=True),
        )
        assert execution.id, "background execution did not return an identity"
        command_id = execution.id
        await sandbox.close()
        sandbox = await Sandbox.connect(sandbox_id, connection_config=config())
        deadline = time.monotonic() + 20
        while True:
            status = await sandbox.commands.get_command_status(command_id)
            if status.running is False:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("background command never finished")
            await asyncio.sleep(.2)
        assert status.exit_code == 7, status
        logs = await sandbox.commands.get_background_command_logs(command_id)
        assert "first" in logs.content and "last" in logs.content, logs
        tail = await sandbox.commands.get_background_command_logs(command_id, logs.cursor)
        assert tail.content == "", tail
        print(json.dumps({"reconnect_status_logs": "passed", "command_id": command_id,
                          "cursor": logs.cursor}), flush=True)

        # A direct child stays in the shell's group. An escaped setsid child
        # intentionally demonstrates why interrupt cannot prove strong stop.
        path = "/tmp/dispatcher-validation-" + token
        child = "import time; time.sleep(90)"
        program = (
            "import os,subprocess,time; "
            f"a=subprocess.Popen(['python3','-c',{child!r}]); "
            f"b=subprocess.Popen(['python3','-c',{child!r}],start_new_session=True); "
            f"open({path!r},'w').write(str(a.pid)+' '+str(b.pid)); time.sleep(90)"
        )
        execution = await sandbox.commands.run(
            "python3 -c " + shlex.quote(program), opts=RunCommandOpts(background=True),
        )
        await asyncio.sleep(1)
        await sandbox.commands.interrupt(execution.id)
        check = (
            "import pathlib,json; "
            f"pids=pathlib.Path({path!r}).read_text().split(); "
            "print(json.dumps([pathlib.Path('/proc/'+p+'/stat').read_text().split()[2] "
            "if pathlib.Path('/proc/'+p+'/stat').exists() else 'absent' for p in pids]))"
        )
        result = await sandbox.commands.run("python3 -c " + shlex.quote(check))
        print(json.dumps({"interrupt_descendant_probe": result.model_dump(mode="json")}), flush=True)
        await sandbox.destroy()
        destroyed = True
        probe = await SandboxManager.create(connection_config=config())
        try:
            try:
                await probe.get_sandbox_info(sandbox_id)
            except SandboxApiException as exc:
                assert exc.status_code == 404, "destroy absence requires HTTP 404"
            else:
                raise AssertionError("destroyed sandbox still discoverable")
        finally:
            await probe.close()
        print(json.dumps({"destroy_confirmed_absent": True}), flush=True)
    finally:
        if not destroyed:
            await sandbox.destroy()
        await sandbox.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    live = parser.add_mutually_exclusive_group()
    live.add_argument("--live", action="store_true")
    live.add_argument("--live-loss", action="store_true",
                      help="discard real create/start responses and check recovery boundaries")
    live.add_argument("--live-adapter", action="store_true",
                      help="exercise this repository's optional adapter against real APIs")
    parser.add_argument("--image", default="python:3.12.10-slim-bookworm")
    args = parser.parse_args()
    if not (args.live or args.live_loss or args.live_adapter):
        print(json.dumps({"live": "not requested", "configured_env_names": sorted(
            name for name in os.environ if name.startswith("OPEN_SANDBOX_")
        )}))
        return
    if not os.environ.get("OPEN_SANDBOX_DOMAIN"):
        parser.error("live checks require OPEN_SANDBOX_DOMAIN")
    logging.getLogger("opensandbox").setLevel(logging.CRITICAL)
    if args.live_adapter:
        verify_adapter(args.image)
        return
    asyncio.run(verify_response_loss(args.image) if args.live_loss else verify(args.image))


if __name__ == "__main__":
    main()
