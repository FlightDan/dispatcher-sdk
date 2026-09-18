# Sandbox execution

[English](Sandbox-Execution.md) | [简体中文](Sandbox-Execution-zh-CN.md) | [Home](Home.md)

The core sandbox protocol has no third-party dependency. A `SandboxHandler`
persists remote lifecycle facts in a separate journal and exposes the provider
as a normal Kernel handler. OpenSandbox is optional:

```sh
python -m pip install 'dispatcher-sdk[opensandbox]'
```

The 0.7 adapter is pinned to `opensandbox==0.1.16`. It imports the provider SDK
only when backend operations run and expects a separately deployed OpenSandbox
service. Other providers can implement `SandboxBackend`.

`SandboxSpec` freezes the image, source, interpreter, working directory,
artifacts, CPU/memory request and supported egress policy. Inputs and collected
data have explicit size limits. Artifact paths are literal; the SDK does not
read host files or expand globs. Actual network isolation still depends on the
provider deployment and container runtime.

The Runtime saves an operation key before create, the sandbox ID before start,
and the command ID before polling. It records bounded output and disposal state
in the journal. Sandbox handlers require process isolation; thread mode is
rejected. The Runtime and journal must use the same durability profile.

Timeout or cancellation first contains the local worker, then tries to dispose
the remote sandbox. Cancelling an HTTP request does not prove that the script
stopped. A lost create/start response, missing command ID or unconfirmed cleanup
remains `SandboxOutcomeUnknown`; do not blindly resend the script. Empty metadata
searches and missing logs are not evidence that an operation never happened.

After restart, the Kernel remembers registered journal paths. Missing or damaged
journals and unavailable historical handlers remain visible during preflight.
`runtime.recover_sandboxes(all_pages=True)` retries disposal of inactive
resources. It does not rerun scripts or resolve external business effects.

The OpenSandbox adapter supports create/find/start/inspect/collect/terminate,
bounded stdout/stderr and artifacts, paged reconciliation, and verified destroy.
Real-container validation covered the full adapter flow, response-loss probes,
nonzero exit, truncation and quoted artifact paths. It is functional evidence,
not a production security or performance certification.

Read the [runtime contract](../docs/SANDBOX_RUNTIME.md),
[adapter limits](../docs/SANDBOX_ADAPTERS.md) and
[validation record](../docs/OPENSANDBOX_VALIDATION.md) before deployment.
