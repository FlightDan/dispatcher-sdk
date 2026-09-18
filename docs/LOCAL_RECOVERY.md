# Explicit local restore and activation

Run `python examples/local_restore.py` for a complete same-host recovery drill:
enqueue, close owners, authenticate a snapshot, restore it, retire the source,
activate one successor and finish the queued task.

## Supported handoff

`restore_snapshot` continues to produce a read-only artifact. The separate
`dispatcher_sdk.storage_activation.activate_restored_snapshot` API authorizes a
new writable successor:

```python
from dispatcher_sdk.storage_activation import activate_restored_snapshot

result = activate_restored_snapshot(
    restored_directory,
    new_successor_directory,
    signing_key=deployment_key,
    operation_id="recovery-2026-09-19-1",
    handlers=handlers,
    owner_id="operator",
)
application_path = result.components["application"]
```

The component name comes from the original `StoreGroupDescriptor`. Preserve the
same operation ID, destination, snapshot and key when retrying an interrupted
activation. Retrying a committed activation returns its successor; it does not
rewind a successor that has already begun processing.

Activation verifies authentication, component integrity and handler bindings,
then exclusively locks the signed original source paths. All participating SDK
connections must be closed. The original source must still be locally available
and logically equal to the captured snapshot: activation rejects changes after
capture, including newly completed executions, effects or inbox consumption.

While holding the locks, activation reserves the successor name in an authenticated
file beside its destination directory, then publishes permanent source-retirement
markers binding one manifest and successor. It copies into a new gated directory
and persists the authenticated activation receipt both inside and beside that
directory before allowing writers. The
original backup and restored artifact remain immutable. SDK writer connections
and ordinary maintenance refuse retired source paths. A different operation or
successor for those paths is rejected.

## Interruption and external effects

Source retirement precedes successor write access. A partial failure may leave
sources retired and a successor still blocked; retry the same activation identity
to finish. If initialization was interrupted between directory creation and its
pending record, the external reservation proves ownership and permits retry.
Before opening a committed but still gated successor, retry rechecks its bytes
against the snapshot. Once activated, losing the successor or its receipt causes
retry to fail; the SDK never reconstructs old work that may have already run.
Do not remove retirement, reservation, pending or read-only markers manually.
Retirement is a handoff, not a rollback mechanism.

Activation preserves existing execution leases and retry budgets. Abandoned
leases follow the normal expiry/reaping protocol. Existing uncertain effects
still require evidence and `resolve_effect`; activation does not invent receipts
or authorize reissuing an uncertain external call. A queued task can execute after
the successor starts. The SDK does not infer business acceptance from completion.

## Explicit limits

- This release supports a conservative local component set with one Kernel.
  Unsupported sandbox journals, owned blob resources and layouts whose ownership
  cannot be proved are rejected.
- Older snapshots without authenticated source-path and logical-state bindings
  remain inspectable/restorable, but cannot be activated by this API.
  New manifests advertise `copy_activation_api_available`; the legacy
  `activation_api_available: false` still prohibits unlocking the immutable
  snapshot directory in place.
- An inaccessible original machine or a source changed since backup cannot be
  automatically fenced by this local protocol. Such disaster-recovery cases need
  external ownership fencing and reconciliation; this API fails closed.
- Every writer must participate in the 0.7 retirement protocol. Stop older SDK
  deployments, direct SQLite writers and external processes before activation.
  Trusted filesystem owners can bypass local markers; this is not remote fencing.
- Source databases with hard-link aliases are rejected. Keep source paths and
  filesystem ownership stable during the handoff; creating aliases or copying
  database files around the SDK protocol bypasses local ownership coordination.
- Filesystem synchronization depends on the platform. The tests do not prove
  hardware power-loss behavior or certify Windows activation on a real host.

The current release supplies a verifiable stopped-source handoff, not unrestricted
activation of an arbitrary historical backup. See the [0.7 devdoc](DEV_0_7.md)
for the architectural tradeoffs and recorded verification.
