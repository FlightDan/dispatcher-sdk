# Runtime diagnostics and durable projections

Use these APIs to check deployment identity, persist event projections, inspect
work availability, and read cancellation evidence. Existing execution and
Orchestrator schemas and public operations remain unchanged. Diagnostic reports
do not authorize execution, change application policy, or migrate an old store.

## Deployment identity (A01)

```python
from dispatcher_sdk import runtime_identity

report = runtime_identity("run.sqlite3", handlers=handlers, durability="full")
print(report.module)
print(report.read, report.execute, report.resume)
```

`path` is optional. `component_paths={"inbox": path, "sandbox": path}` adds
independent inspections. The report contains distribution version, actual module
path, package source-version declaration, a framed SHA-256 of Python source
files, wheel RECORD comparison, contract versions and handler fingerprints.
Hashes describe files observed now; they do not authenticate the package or
verify monkeypatched objects, already loaded bytecode, or native dependencies.
Missing build evidence is unknown. A known version/RECORD mismatch blocks the
aggregate execute/resume verdict while retaining the separate storage facts.

Each storage has separate read, execute, resume and catalog-summary verdicts.
Missing storage is not readable. A legacy SQLite catalog summary does not imply
a supported legacy Run reader. Handler checks must be supplied to obtain a
positive resume preflight; pure inbox/sandbox/cancellation journals cannot
establish execution or recovery support by themselves. Reports cover the paths
supplied, not an implicitly discovered complete deployment.

`durability` is the caller's configuration declaration. The journal mode can be
observed, but another connection's `synchronous` setting and hardware fsync
guarantees cannot. See [storage preflight](STORAGE_AND_UPGRADES.md).

## Projection consumer (A02)

```python
from dispatcher_sdk.orchestrator import ProjectionConsumer

consumer = ProjectionConsumer(sdk, source_id="orders-prod", subscription="audit-v1")
result = consumer.drain("run", persist, timeout_seconds=30)
```

`persist(identity, event)` is synchronous and returns exactly `"persisted"` or
`"already_present"` after its transaction commits. The identity has
`source_id`, `run_id` and `sequence`. Commit deduplication and business writes in
the same destination transaction. Keep the source namespace stable across
restart; independent source forks need distinct namespaces. Event sequences can
have gaps and are not local array offsets.

The consumer persists events individually and ACKs a complete page through the
existing subscription/Run revision CAS. A failure leaves that page's cursor
unchanged; earlier pages stay acknowledged. Previously persisted events replay
after a crash and must deduplicate. The source is at least once; exactly-once
projection effects depend on the destination's idempotent transaction. Returning
success before durable commit defeats that guarantee. This helper cannot verify
an arbitrary external callback's durability.

Each subscription has one logical consumer. A poison event blocks its page and
returns its identity and failure; the helper never skips it or advances past it.
There is no automatic dead-letter queue. Async callbacks/awaitables and invalid
return values are rejected as incomplete.

`drain` freezes the initial high watermark, or accepts a caller target no higher
than that observation. It does not chase newly appended events. A successful
ACK window is still necessary: ongoing Run-revision conflicts can exhaust the
bounded conflict budget. Lost ACK responses retry the same request identity and
parameters. The report records completed, blocked, interrupted or conflict,
the last confirmed cursor and callback/replay counts.

Stopping and timeouts are checked between callbacks and before ACK attempts.
Callbacks must bound their own I/O; the SDK does not kill a blocked callback or
interrupt its transaction. A page interrupted before ACK will replay. See the
[SQLite projection example](../examples/projection_consumer.py).

## Work availability (A03)

```python
availability = sdk.inspect_work_availability("run", sample_limit=20, effect_scan_limit=1000)
print(availability.reason_codes, availability.claimable_now)
```

The report counts the target Run's ready queued executions, active/expired
leases, future retry times, pending commands, result synchronization, application
result delivery, waits, recovery and unknown Effects. It uses the attached
Runtime's bindings unless explicit `registry_revision` or `registry_revisions`
are provided. Without either, `claimable_now` is `None` and `queued_ready` is the
unfiltered count.

Claimability describes queued work before reap. A real claim can reap expired
leases first and a later caller can win the lease. `next_change_hint` is an
earliest observed retry/lease time, not a promise of available work. Empty polls
do not establish business stagnation. Reasons may coexist, and terminal Runs can
still have pending delivery or cleanup obligations.

The schema has no per-execution Effect index. To preserve compatibility, this
API reads at most `effect_scan_limit + 1` Effect rows globally (default
1000; 0 disables the check). When that budget is exceeded, `unknown_effects` is
`None`, `complete` is false and the reason explains the limit. A partial count is
never presented as zero. Removing this limit would require a separately versioned index or storage change. Other execution queries use the
existing Run registration index and execution primary key.

Separate databases are not an atomic snapshot. Reports include source paths,
Run revision, Kernel event sequence, logical observation time, and consistency
status. Detected changes make cross-store result sync unknown. The API does not
flush, sync, reap, initialize storage, or update clocks, leases or cursors.

## Cancellation and recovery evidence (A04)

```python
with Orchestrator.open_sqlite(
    "run.sqlite3", handlers,
    cancellation_journal_path="cancel-evidence.sqlite3", source_id="orders-prod",
) as sdk:
    report = sdk.inspect_cancellation("run", task_id="task")
    print(report.to_dict())
```

Creating/opening the stack above is a writer operation. The inspection method
itself is read-only. `Runtime` accepts the same two optional journal arguments.
They are paired: the source identity is required when a journal is configured.
No journal is created by default or by a report query.

The report separates committed request, delivered command, revoked authority,
local process cleanup, tracked external outcomes, cleanup obligations, Task
projection state and Run terminal state. It retains execution revision, Kernel
attempt/fence, application attempt, Effect revision/recovery identity and receipt
IDs. Task projections may lag the authoritative execution; the report exposes
both. `execution_id=` can select a historical attempt. Run-wide queries select
current attempts and support `limit`/exclusive `after_task_id` paging.

A read-only caller without the original Runtime can supply
`cancellation_journal_path=` and `source_id=` to the report. Missing, damaged or
unavailable receipts result in unknown evidence and an issue, never a fabricated
cleanup confirmation. An external result can be known while cleanup is pending;
the report identifies known sandbox results even if Effect recovery is unresolved.

Only a matching execution generation's supervisor can prove local cleanup.
The caller's isolation-mode setting, an absent PID, or successful cancellation
of a different generation cannot. A recorded local thread invocation can establish
that process-tree cleanup is not applicable; it does not prove the thread stopped.
Linux requires an explicit subreaper containment receipt and Windows requires
the Job's active process count to reach zero. Abnormal supervisor death and other
POSIX backends without that full-tree proof leave the fact unknown.

The [cancellation journal design](CANCELLATION_EVIDENCE.md) describes commit gaps,
backup, compatibility and evidence limitations. The
[diagnostic example](../examples/capability_diagnostics.py) demonstrates explicit
cancellation without silently finishing the Run.
