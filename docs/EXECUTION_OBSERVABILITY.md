# Execution activity, deadlines and supervision

The `0.7.0.dev2` implementation adds execution observations, inherited deadlines,
bounded child execution and optional durable stall notifications. Current SDK
and platform acceptance is tracked separately in
[the acceptance index](EXECUTION_OBSERVABILITY_ACCEPTANCE.md). The active Goal
covers SDK functionality, robustness and maintainability; application integration
and production-provider validation require their own evidence.

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

After native containment is confirmed, the standard script handler also retains
a bounded fact about its original stdout/stderr log sizes. `output.stdout` and
`output.stderr` expose `saved_bytes`, `saved_at`, `saved_path` and
`count_basis="max_collected_and_saved_bytes"`. Stream counts use the larger of
the collected count and saved-byte floor, so reconciliation never adds a second
copy of the same bytes. `script_output_fact` identifies the persisted receipt.
Missing emission timestamps remain unknown, and this fact does not confirm a
telemetry flush or progress. It is read even if activity initialization failed.

Artifact publication uses one retained worker with bounded caller waits. If a
filesystem call blocks or SQLite publication fails, that worker retains its
original execution identity and captured fact until cleanup completes. Deferred
facts remain discoverable after the business result settles and after restart;
maintenance does not invoke the script or extend its deadline. Later unsampled
durable queue entries can remain after close without a live local storage owner.

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

The existing recorder flusher holds an idle read-only WAL connection for its
own lifetime. It retains no transaction or cursor, and each write still uses
its configured durability and original timeout. Failed setup releases that
connection before ordinary flushing. Failed physical close retains the same
connection and worker until release; a persisted final-flush receipt alone
does not discharge that storage ownership.

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
Later authoritative budget samples also commit a write-ahead guard before reading
wall time. Their exact acknowledgement atomically advances the execution floor
and Kernel clock watermark. A failed publication fences recovered business;
only its retained live owner can finish the original captured fact. Kernel retains
that owner after a short child call or pre-handler admission ends. Maintenance
and repeated close publish facts without sampling again or renewing a deadline.
An interrupted process leaves its guard unknown; a fresh Kernel cannot guess the
lost observation. Factual completion can use the exact live owner’s already
captured token without acknowledging or clearing it. A foreign or uncaptured
guard remains unknown. `Task.observe` remains read-only; `context.budget` establishes
an authoritative budget sample and can encounter this bounded control admission.
Resolving an uncertain Effect does not acknowledge a clock sample or clear its
guard. The original response remains saved, but a recovered execution stays
fenced while its clock fact is unknown, even if its Effect recovery target is queued.
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
`HandlerContext.activity` implements the public `ExecutionActivity` protocol;
`HandlerContext.children` implements `ChildCalls`, exported by
`dispatcher_sdk.execution_kernel`. Both expose checked method signatures.
When the child journal/service is unavailable, child calls raise
`ChildExecutionError(code="child_service_unavailable")` with the known original
storage reason. They do not create a child or disable ordinary handler work.

Configure `child_capacity` and `max_child_depth` on `Dispatcher` or
`Kernel.open_sqlite`. Defaults are one reserved child slot and one level. A
synchronous parent retains its process and memory while the SDK uses the
separate bounded child capacity. Pending parent entry, stale parent authority,
exhausted deadlines, cycles and exhausted capacity do not create an unlimited
worker pool. Durable wait/request records expose incomplete registration and
recovery rather than claiming a cross-database atomic commit.

The SDK retries short SQLite writer conflicts and SDK-owned per-read timeouts
within the captured child-call window, preserving the request, child identity
and deadline. A committed child result survives a failed response write;
recovery reconciles it without invoking the handler again. Stricter observed
clock checkpoints survive rollback through the request or an independent
receipt. Incomplete checkpoint history remains unknown, and a result read cannot
bypass an unread checkpoint fact.

If publication still lags when that window ends, the standard file-backed
`SQLiteKernel` uses an independent read-only connection to prove an already
committed result within the original 0.1-second factual window. It reads the
child result once, then takes a fresh snapshot of the parent lease, ancestry,
child identity and parent/child association. Cancellation or a new unresolved
guard observed at that final check refuses delivery without replaying the read.
Late results and unknown clock continuity do not qualify.

This proof projects retained elapsed time and may use the original caller's
exact local captured token. It does not sample wall time, acknowledge or drain
pending samples, clear guards, advance the durable clock or release pending
publication. Initial checks can wait for a foreign live owner to publish its
own ACK inside the same proof window; the reader cannot publish it. Uncaptured
or unresolved foreign guards remain unknown. Custom and in-memory Kernels retain
their existing fallback; the independent SQLite proof applies only to the
standard file-backed Kernel.

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
If the control operation raises, Runtime re-raises that original exception and
captures bounded local diagnostics without opening another diagnostic SQL write
window. A raised operation can follow a commit; it does not prove that authority
was unchanged. Re-read the canonical execution before deciding what to do next.

## Reserve capacity for a managed supervisor handler

```python
from dispatcher_sdk import Dispatcher, ManagedStallOptions

def supervise(notice, context):
    context.activity.progress("notice-inspected")
    return {"notification_id": notice["notification_id"],
            "decision": "continue observing"}

with Dispatcher("tasks.sqlite3", {"work": work},
        stall_handler=supervise,
        stall_options=ManagedStallOptions(
            memory_limit_bytes=512 * 1024 * 1024, capacity=1,
            memory_budget_bytes=512 * 1024 * 1024,
            timeout_seconds=10, budget_seconds=30)) as dispatcher:
    task = dispatcher.submit("work", {}, request_id="original-work", timeout_seconds=60)
    task.watch_stall(StallPolicy("progress", sample_interval=5, consecutive_windows=2))
    status = dispatcher.stall_supervisor_status()
```

The synchronous handler receives the original durable notice and a normal
`HandlerContext` in a separate process Runtime. Its configured capacity is
independent of business workers. The original notice ID selects one managed Run
and execution with one business claim; replay delivers the original result and
never invokes the handler again. Configure the handler during Dispatcher
construction when reopening outstanding supervisor commands, so recovery can
validate its binding before opening execution storage. A callback and managed
handler are mutually exclusive consumers. `subscribe_stalls(handler=...,
options=...)` is also available while the Dispatcher is open.

`budget_seconds` includes queue residence from the original notice creation.
The handler also inherits its source execution's constraints and uses the earlier
source, notice and handler cutoffs. Transient admission retries consume those
same bounds. Successful handler completion consumes the notice; the application
still decides whether to cancel, continue observing or perform another action.
Its SDK child service is disabled. External effects still need application
idempotency and the normal fenced effects API.

`memory_limit_bytes` limits each Linux worker's address space or the Windows
Job's private commit. `memory_budget_bytes` controls how many configured
reservations may coexist; it defaults to capacity times the per-worker limit.
These values do not measure host free RAM or aggregate Linux RSS. A native limit
that cannot be enforced refuses admission. `stall_supervisor_status` exposes
`capacity_shortage`, `memory_shortage`, `resource_enforcement_unsupported`,
`cleanup_pending` and actual resource capability. Shortage leaves the notice
unclaimed and does not reset its original budget. Capacity and memory remain
charged until original native cleanup, collector ownership and pending clock
publication are confirmed. Close may report pending cleanup while retaining
storage; repeat close after the original owner or storage recovers.

`budget_checkpoint_state` reports `clear`, `pending` or `unknown`, including
facts retained before a handler Context exists. If the registry cannot be
inspected within the query window, `budget_checkpoint_pending` is `None` and
the report is incomplete; `budget_checkpoint_known_pending` preserves the
locally known count. An unavailable inspection cannot release a reservation.

If worker-thread creation fails after executor submission has queued work, the
unaccepted work cannot enter the handler. The supervisor retires that executor,
reports `executor_unavailable` with the original error, and stops claiming new
notices while already accepted workers finish. The original processing receipt
remains unchanged. Recovery requires reopening the Dispatcher with the same
bindings; receipt recovery still uses the original notice and source cutoffs.

See [the runnable managed supervisor example](../examples/managed_stall_supervisor.py).
Linux actual-process checks cover memory denial, capacity shortage, original
notice/source deadlines and retained cleanup ownership. The current complete
source, installed-wheel and native-matrix requirements remain tracked in
[the acceptance index](EXECUTION_OBSERVABILITY_ACCEPTANCE.md).

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
Native parent timers and supervisors retain the exact samples that shortened
their deadlines and merge those floors into the same obligation. Entry packets
and later wall-clock rollback cannot replace a stronger timer observation.
The worker entry packet projects both deadlines from the committed checkpoint
and one native elapsed sample; it does not add an unconfirmed wall-clock read.
Cleanup may consume the reserved interval after timely business return; its
retained floor constrains future admission without changing that return's cause.
Kernel completion commits that checkpoint with the result, before releasing a
retry. A clock rollback cannot restore time already observed as exhausted.
Recovery tightens the existing budget without confirming an interrupted entry.
A captured clock floor lost before its receipt or Kernel acknowledgement cannot
be reconstructed after process death. Its previously committed sampling guard
remains unknown and refuses recovered business.

If both receipt persistence and Kernel completion are unavailable, the reserved
slot keeps the exact original outcome for maintenance. `observe` exposes it as
`local_settlement_obligations` and marks the report incomplete. These local facts
are not durable across host death. `close` attempts a bounded receipt drain and
raises if it cannot persist them. Retrying `close` after storage recovers writes
the original receipts without reopening business; a fresh Runtime restores
them through the existing fenced settlement path.

`observe` also returns bounded `diagnostics` pages from this independent store.
Raised cancellation operations and failed optional phase writes can additionally produce
`local_cancellation_diagnostics`. These notes are separate from persisted phases
and their event cursor. They carry the known Kernel execution/attempt/fence;
workflow metadata remains unknown. Default queries select the current identity
when it is available, while explicit attempt/fence filters select matching
historical notes. Query time and response size retain their original bounds.
Notes are marked `persisted=False` and disappear when Runtime restarts. A known
request receipt remains identified separately. Queue or detail loss is marked
at Runtime scope and does not establish loss for a particular execution.
Runtime storage also remains owned by observation workers which outlive a
recorder's bounded close wait. Runtime `close()` drains those stopped workers;
if they still hold storage, it raises `RuntimeError` and retains pending cleanup.
Calling `close()` again advances that cleanup without restarting business or
changing the original telemetry receipt. Temporary observation storage is removed
only after its owned workers stop, including observation initialization, the stall
sampler and the settlement worker. Their cleanup shares one absolute deadline.
Recorder close joins its original flusher only within the caller deadline’s remaining time; if physical close
is blocked, Runtime retains the worker and storage. A late handler cannot
register a new process collector after its recorder closes.

Available cancellation stages, the actual handler outcome and the driver close
receipt remain separately queryable when the activity writer is locked. Lost details or an
unconfirmed final flush make the observation incomplete even after the execution
becomes terminal. Settlement updates retain the original diagnostic evidence.
Cancellation retains the original requested/revoked timestamps but writes
optional diagnostics after local revocation, so writer pressure cannot delay
process termination. Those optional writes share the remaining cancellation
control allowance; failed or skipped writes retain local, unpersisted facts.
When independent notes supply a phase, capture time remains separate from
publication time. Delayed publication does not make an old process observation fresh.
Read admission uses the caller's remaining query budget;
exhaustion does not become an empty successful notification page.

For adapters with a finite control deadline, open a public
`SQLiteKernel(path, control_timeout_seconds=.1)`. This caps connection setup and
each control-lock/SQLite admission wait without changing lease or execution
deadlines. Preserve the original control deadline across retries; a SQLite busy
error is a storage-admission failure and does not establish revoked authority.
The default control timeout remains unchanged.

Journal admission retries use each operation's original write window. An
expired observation write can retry only after its rollback is confirmed, inside
the caller's existing window; generic errors and uncertain commits do not grant
another attempt. Native filesystem durability I/O cannot be preempted by a Python
wait deadline. A successful late COMMIT retains its actual receipt; it never
justifies replaying business. Storage still owned by a stopped SDK worker remains
pending cleanup as described above.

The current development candidate uses Kernel layout version 5. It adds sampling
guards; copy-upgrading an older open execution with limits records its unprotected
clock as unknown instead of granting a reconstructed budget. Use the explicit copy-upgrade API for older
supported layouts; normal opens do not migrate them. Observation journals are
separate, source-bound files containing windows, waits and notification handoff
obligations. The independent `*.settlements.sqlite3` journal retains result
obligations and is also bound to its original Kernel path and store identity.
Existing one-file snapshot/upgrade operations do not relocate or
rebind them. Preserve the journal alongside its original Kernel binding when
resuming these obligations; absent observations do not establish completion.

See [the portable example](../examples/execution_observability.py) for a real
parent/child execution. The
[implementation goal](EXECUTION_OBSERVABILITY_GOAL.md) defines the SDK scope;
[the acceptance index](EXECUTION_OBSERVABILITY_ACCEPTANCE.md) records current
evidence and outstanding checks.
