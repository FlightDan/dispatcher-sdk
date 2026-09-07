# Durable sandbox execution

`SandboxHandler` registers a provider as a normal Kernel handler. The core
protocol, lifecycle journal and Runtime use only the standard library and
SQLite. `dispatcher-sdk[opensandbox]` adds the pinned official OpenSandbox SDK;
community providers implement the same public `SandboxBackend` protocol.

## Submit a script

Run this as a guarded Python file against an application-configured OpenSandbox
service. Set `OPEN_SANDBOX_API_KEY` in the host environment. The image,
interpreter and working directory refer to the remote Linux sandbox.

```python
from dispatcher_sdk.adapters import OpenSandboxBackend
from dispatcher_sdk.execution_kernel import Runtime, SandboxHandler, SandboxSpec


def main():
    backend = OpenSandboxBackend(domain="localhost:8080")
    handler = SandboxHandler(backend, "sandbox-journal.db")
    spec = SandboxSpec(
        image="python:3.12.10-slim-bookworm",
        source="print('hello from the sandbox')\n",
        interpreter=("/usr/local/bin/python3",),
        cwd="/tmp",
    )
    with Runtime("kernel.db", {handler.handler_id: handler}) as runtime:
        command = runtime.command(
            handler.handler_id,
            execution_id="script-1", idempotency_key="script-1",
            correlation_id="workflow-1", timeout_seconds=120,
            payload=spec.to_payload(),
        )
        runtime.submit(command)
        snapshot = runtime.run_once()
        print(snapshot.state)


if __name__ == "__main__":
    main()
```

Use a stable application request identity for command replay. `sandbox_handlers`
is a convenience factory returning a mapping from `(handler_id, 1)` to a
`SandboxHandler`. Provider configuration must be pickleable and stable. The
handler and Runtime must select the same durability profile. Sandbox handlers
require process isolation; thread mode is rejected.

## What is persisted and when

The Kernel prepares and claims the effect before calling the provider. The journal
records the execution/effect identity, lease and fence, original provider
revision, frozen specification and a new operation key before `create`. It
records the sandbox ID before `start`, and the command ID before polling.

The handler collects the terminal outcome and requested output into the journal
before committing the execution effect. Disposal uses a separate effect bound
to the generation. A successful result requires confirmed disposal; a nonzero
script exit is an execution failure with the collected result in its error details.

The Kernel and journal use separate SQLite transactions. A crash between their
commits requires explicit recovery. The journal retains collected output even
if the effect commit was interrupted. Back up both stores and preserve the
original provider configuration; see [storage and upgrades](STORAGE_AND_UPGRADES.md).

Output is bounded JSON, including base64 artifact data. It reports truncation
and includes references to the remaining remote data. Disposal invalidates those
references; export any larger required artifact to application storage before
disposal.
Collection does not promise an atomic file snapshot while descendants can still
write. See [adapter limits](SANDBOX_ADAPTERS.md).

## Timeout, cancellation and restart

Runtime first contains the local worker, then uses its durable journal to dispose
of identified remote resources. A cancelled HTTP request does not establish that
the remote script stopped. `cancel()` may raise `EffectRecoveryRequiredError`
after successful remote disposal because the script's business effects remain
uncertain. Unconfirmed remote cleanup is reported as `SandboxOutcomeUnknown`.
`close()` also attempts inactive cleanup and reports unresolved resources.

Registered journal paths are persisted in the Kernel database and bound to its
store identity. Restarting with an empty handler registry or a different journal
path does not hide old obligations. Missing journals, unavailable original
handlers, mismatched revisions and damaged schemas remain visible in recovery
reports and storage preflight. Reopening a registered journal never silently
replaces it with an empty store.

After expired leases have been reaped, call
`runtime.recover_sandboxes(all_pages=True)` to retry disposal of inactive
executions. The default call scans a bounded page per journal; use the cursor or
`all_pages=True` to cover the whole backlog. Live leased/running executions are
skipped. Recovery retries disposal only; it neither replays scripts nor resolves
Kernel effects. `runtime.reap()` also runs a cleanup pass.

## Resolve uncertain operations from evidence

1. Inspect `handler.journal().get(execution_id)`, Kernel effects and provider
   records. Reconcile the script's external business effects independently from
   sandbox resource disposal.
2. Establish cleanup. For a known sandbox ID, provider termination must confirm
   absence. If the create response was lost, metadata search can locate and
   dispose candidates, but even an empty result cannot prove there is no late
   create. Obtain external evidence before recording
   `journal.confirm_cleanup(execution_id, operation_key=..., evidence=...)`.
   This public recovery decision is fenced to that generation and does not
   authorize execution replay.
3. Resolve each indeterminate Kernel effect using its current revision and a
   stable recovery ID. `applied` requires its actual response; an execution
   response must contain terminal `state`, `exit_code`, `output`, `sandbox_id`
   and `command_id`, consistent with already recorded identities/output.
   A disposal response is exactly `{"cleanup_confirmed": True}` and requires
   evidence of absence. `not_applied` requires proof the effect did not happen.
4. Resume the normal Runtime path. A committed execution response is reused;
   disposal recovery does not rerun the script. Explicit `not_applied` for the
   execution effect permits a fresh generation only after the previous one is
   disposed and a newer fence is held. Prior generation records remain in
   `journal.history(execution_id)`. A persisted cancellation target settles
   through Kernel recovery without running another script.

OpenSandbox has no caller-supplied command idempotency key and no authoritative
lookup for a lost command ID. Its metadata filter is not a uniqueness constraint.
Missing logs, expired resources and empty searches are not `not_applied` evidence.
Neither the SDK nor a sandbox can roll back arbitrary external network effects.

## Provider integration and verification

Implement `name`, `revision`, `create`, `find`, `start`, `inspect`, `collect` and
`terminate` from `SandboxBackend`. The revision binds behavior and configuration.
Reject unsupported required policies explicitly. An optional `validate(spec)`
method can reject policies before preparing an effect. Run the public
`dispatcher_sdk.adapters.verify_backend` harness against a disposable real
backend; it creates resources, collects output and verifies cleanup without
hidden retries. It cannot certify hostile-code isolation or production security.

Tests with a persistent fake provider exercise real local process interruption,
lost responses, restart, missing configurations, generation fencing and disposal
recovery on both Linux and native Windows. A separate real-service probe passed
on Linux with official SDK 0.1.16, server
0.2.3 and execd v1.0.22 on an isolated Linux Docker daemon:

```sh
OPEN_SANDBOX_DOMAIN=127.0.0.1:18087 \
  python scripts/verify_sandbox_runtime.py --live
```

The probe passed community conformance, Runtime success with a persisted file
artifact, timeout disposal, cancellation disposal before return, and Runtime
close. The timeout/cancel fixtures spawned detached descendants. The service and
protocol evidence, including actual lost-response probes, is recorded in
[OpenSandbox validation](OPENSANDBOX_VALIDATION.md). This is Linux service
validation; successful native Windows process/recovery validation is recorded in
[Windows runtime](WINDOWS_RUNTIME.md).
