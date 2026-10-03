# Execution activity, deadlines and supervision

The `0.7.0.dev2` implementation adds execution observations, inherited deadlines,
bounded child execution and optional durable stall notifications. Platform and
application acceptance are tracked separately in
[the implementation goal](EXECUTION_OBSERVABILITY_GOAL.md).

## Read activity through a task

```python
from dispatcher_sdk import Dispatcher, ObservationOptions, StallPolicy

with Dispatcher("tasks.sqlite3", {"work": work},
                observation_options=ObservationOptions()) as dispatcher:
    task = dispatcher.submit("work", {"input": "value"},
                             request_id="durable-input-id", timeout_seconds=30)
    activity = task.observe(timeout=3)
    events = task.events(after=0, limit=50, timeout=3)
    result = task.wait(timeout=30)
```

`observe` reads persisted observations. It does not claim work, renew a lease,
advance a notification, or clean up a process. `complete=False`, `unknown_reason`
and source freshness explain missing or partial evidence. Use the event cursor
returned by `events` to read the next page. A timed out `Task.wait` ends the
caller’s wait without changing execution deadlines or cancelling the task.

The execution state, actual handler entry, process cleanup, recorded result and
result delivery are separate facts. The Kernel’s `running` timestamp records its
state transition; the budget’s `started_at` records actual handler entry. An
entry still awaiting durable confirmation has an unknown budget view. Delivered
Kernel results do not establish that an application consumed a notification.

## Report separate kinds of activity

Handlers receive an automatically bound `HandlerContext`:

```python
def work(payload, context):
    context.activity.enable_stream("stdout")
    context.activity.report_bytes("stdout", b"partial output without a newline")
    context.activity.model("request")
    context.activity.tool("request")
    context.activity.heartbeat()
    receipt = context.activity.progress("accepted-step-id")
    return {"progress_receipt": receipt}
```

Byte reports count raw chunks before decoding or line parsing. `retain_tail=False`
records their lengths without retaining private content. `report_byte_count`
supports an adapter that already counted bytes. Streams and model/tool metrics
that have not been installed or reported are unknown rather than inferred zero.
SDK script handlers install their stdout/stderr observers automatically.

Heartbeat, output, model activity, tool activity and application progress have
separate counters and timestamps. Logs and heartbeats do not reset the progress
clock. `progress` returns `confirmed` only after the Kernel commits its receipt.
Replaying the same key for the same attempt preserves the original progress
revision and time. This confirms the application’s declaration, without deciding
that an artifact or business result is valid.

The SDK buffers observations and flushes finite batches in its own background
workers. Defaults are one second between flushes, 256 queued details, 1 MiB of
queued detail, 128 details and 256 KiB per batch. stdout and stderr tails are
limited to 64 KiB each. Read pages default to 50 records, 256 KiB and three
seconds. Storage pressure and dropped details are visible; telemetry failure
does not replace a handler’s business outcome.

## Use the execution budget

```python
view = context.budget
tool_budget = context.derive_budget(
    source="tool", origin_id="lookup:1", timeout_seconds=5, reserve_seconds=1)
remaining = tool_budget.view().remaining_work_seconds
```

The envelope retains applicable Run, execution, parent and local tool constraints.
Its effective work deadline and hard deadline are each the earliest applicable
bound, with their limiting source. A reserve belongs to its original constraint
and is inherited once. A tool adapter must use the derived envelope at its actual
request and blocking wait; deriving it alone does not supervise an external
provider.

The first actual handler entry establishes the execution cutoff. Retry, restart
and lease renewal preserve it. Native same-boot elapsed time establishes
continuity across processes where supported. An unprovable clock domain or
unconfirmed admission is unknown and cannot grant a fresh business budget.
The SDK records entry as pending before dispatch, then durably confirms the
captured cutoff and observed clock floor before calling business code. Temporary
storage contention may retry that confirmation within the original work window;
it does not restart the timeout. An interrupted confirmation remains pending.
Process hard deadlines operate independently of observation persistence.
Thread mode can revoke authority and prevent result/effect commits, but cannot
force an arbitrary Python thread to stop.

## Wait for a child within bounded capacity

```python
child_result = context.children.run(
    "child", {"input": "value"}, request_id="durable-child-id",
    timeout_seconds=5)
```

`child_result` is the child’s complete V2 result. `ChildExecutionError` retains
the child execution ID, error code and original result. `wait_for` can observe
an existing execution; a queued execution may acquire inherited limits when
ownership permits. It never reparents an already owned execution.

Configure `child_capacity` and `max_child_depth` on `Dispatcher` or
`Kernel.open_sqlite`. Defaults are one reserved child slot and one level. A
synchronous parent retains its process and memory while the SDK uses the
separate bounded child capacity. Pending parent entry, stale parent authority,
exhausted deadlines, cycles and exhausted capacity do not create an unlimited
worker pool. Durable wait/request records expose incomplete registration and
recovery rather than claiming a cross-database atomic commit.

The SDK retries short SQLite writer conflicts within the captured child-call
window. It retains the same request, child identity and deadline; applications
do not need a retry loop. A committed child result survives a failed response
write, and recovery reconciles that result without invoking the handler again.
If publication still lags when the call window ends, one bounded authoritative
read can return a result already completed within that original window. It
checks the parent authority and child binding; late results and unknown clocks
do not qualify. This does not acknowledge or release the pending publication.
Stricter observed clock checkpoints survive rollback through the request or an
independent receipt. Incomplete checkpoint history remains unknown. A transient
receipt-read timeout retries inside the same original call window; unread
checkpoint facts cannot be bypassed by the completed-result read. That proof
uses read-only lease checks and leaves the durable logical clock unchanged.

An adapter can report resource or external-service waits without changing
deadlines:

```python
with context.activity.wait("provider_response", target="provider"):
    response = call_provider()
```

Only report memory and other resource amounts that the adapter actually knows.
Wait entry captures bounded IDs and timestamps without waiting for SQLite. A
returned `captured` receipt has `persisted=False`; the SDK flusher persists and
replays both endpoints. Lost wait facts and persistence errors retain coverage
gaps and bounded raw diagnostics, including after unrelated successful flushes.

## Enable and recover optional stall notifications

```python
dispatcher.subscribe_stalls(handle_stall)
task.watch_stall(StallPolicy(
    "application-progress", metrics=("progress",),
    sample_interval=10, consecutive_windows=3,
    wait_exemptions=("provider_response",), max_deliveries=5))
page = dispatcher.stall_notification_page(limit=50, timeout=3)
windows = task.stall_windows(limit=50)
```

No stall policy or automatic cancellation is enabled by default. The SDK samples
explicit subscriptions independently of business worker capacity. Only complete
fresh windows count. Sampling gaps, collector replacement and unknown metrics
break the consecutive streak and preserve the historical windows. Wait exemptions
pause counting without extending any deadline. Confirmed new progress ends the
current episode; later stagnation creates a new episode.
An active collector with retained coverage gaps remains unknown. A successful
counter flush does not prove that missing wait facts were recovered; a new
declared collector starts fresh continuity while preserving retired history.
An open diagnostic wait can exempt sampling only while its owning collector is
active and observed. Closed or replaced collectors cannot revive old exemptions.

Each episode has a stable notification ID. The observation outbox, orchestration
delivery and application inbox have separately visible phases and revisions.
Persistent receipt and application consumption are different states. Continue
filtered notification pages with their returned cursor, including an empty
partial page. `stall_notifications` is a convenience view; the paged API exposes
the bounds needed for a full inspection.

Retry an exhausted phase with the revision returned by inspection:

```python
dispatcher.retry_stall_notification(
    notice["notification_id"], expected_revision=notice["revision"],
    phase=notice["phase"])
```

Retries preserve the ID and episode. A transient control/storage error is not an
accepted retry; callers can repeat the same conditional operation within their
own bounded control deadline. Callbacks are synchronous and have one separate
worker. A blocked callback does not acquire more threads or block local hard
deadlines. External callback actions still need application idempotency.

If the application authorizes cancellation for a stall, use
`task.cancel_if_stalled(notice)`. The Kernel checks the attempt, fence, episode,
policy and progress revision in the cancellation transaction. A confirmed
progress commit that wins the race rejects the stale disposition. Ordinary
`task.cancel()` retains explicit cancellation semantics.
Cancellation retries temporary control-storage contention only when it can prove
that the attempt made no writes. All such attempts share the original caller
window and the same revision and supervision token. Cleanup and evidence
collection after the cancellation decision retain their separate bounds.

## Independent reads and storage

`runtime.observation_storage` supplies the public sidecar path, Kernel path and
source binding. An inspector can call `dispatcher_sdk.observability.inspect_execution`
with those fields without loading handlers or opening a writer. Missing,
inaccessible or incompatible observation storage is unknown; reads never create
or upgrade it.

Registered processes expose observed `alive`, `exited` or `unknown` facts with
their source and observation time. Old `alive` evidence becomes unknown when
stale. A PID alone, an inaccessible namespace or an unregistered external child
does not prove current liveness or exit. A process exit does not by itself prove
that all descendants were cleaned up. Exit 137 is not sufficient evidence of OOM.

After a real handler returns, the runtime retains its immutable original result
and attempts an independent, full-sync settlement receipt before bounded Kernel
completion. Admission reserves one of 64 local outcome slots before claiming
work; additional executions remain queued while all slots are occupied. If the
Kernel writer is busy, `run_once` may return the existing
`running` snapshot. `observe` then exposes `settlement_obligations`; a pending
receipt proves retention, not terminal acceptance. SDK maintenance retries the
same result during operation and after reopening. `recover_completions` can also
request a bounded maintenance pass. It never invokes the handler. A cancellation,
reaper or newer attempt that already won remains authoritative; the original
receipt is retained as superseded. In-memory storage and unavailable receipt
storage expose unknown retention rather than claiming durability.

The retained obligation also carries the original observed budget checkpoint.
Kernel completion commits that checkpoint with the result, before releasing a
retry. A clock rollback cannot restore time already observed as exhausted.
Recovery tightens the existing budget without confirming an interrupted entry.
A clock observation lost before any receipt or Kernel write is not a durable
fact and cannot be reconstructed after process death.

If both receipt persistence and Kernel completion are unavailable, the reserved
slot keeps the exact original outcome for maintenance. `observe` exposes it as
`local_settlement_obligations` and marks the report incomplete. These local facts
are not durable across host death. `close` attempts a bounded receipt drain and
raises if it cannot persist them. Retrying `close` after storage recovers writes
the original receipts without reopening business; a fresh Runtime restores
them through the existing fenced settlement path.

`observe` also returns bounded `diagnostics` pages from this independent store.
Cancellation stages, the actual handler outcome and the driver close receipt
remain visible when the activity writer is locked. Lost details or an
unconfirmed final flush make the observation incomplete even after the execution
becomes terminal. Settlement updates retain the original diagnostic evidence.
Cancellation retains the original requested/revoked timestamps but writes
optional diagnostics after local revocation, so writer pressure cannot delay
process termination. Read admission uses the caller's remaining query budget;
exhaustion does not become an empty successful notification page.

For adapters with a finite control deadline, open a public
`SQLiteKernel(path, control_timeout_seconds=.1)`. This caps connection setup and
each control-lock/SQLite admission wait without changing lease or execution
deadlines. Preserve the original control deadline across retries; a SQLite busy
error is a storage-admission failure and does not establish revoked authority.
The default control timeout remains unchanged.

The Kernel layout is version 4. Use the explicit copy-upgrade API for older
supported layouts; normal opens do not migrate them. Observation journals are
separate, source-bound files containing windows, waits and notification handoff
obligations. The independent `*.settlements.sqlite3` journal retains result
obligations and is also bound to its original Kernel path and store identity.
Existing one-file snapshot/upgrade operations do not relocate or
rebind them. Preserve the journal alongside its original Kernel binding when
resuming these obligations; absent observations do not establish completion.

See [the portable example](../examples/execution_observability.py) for a real
parent/child execution. Acceptance status and platform evidence remain in the
implementation goal and its acceptance index.
The current evidence and outstanding gates are listed in
[the acceptance index](EXECUTION_OBSERVABILITY_ACCEPTANCE.md).
