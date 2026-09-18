# Storage retention and maintenance APIs

These APIs describe the current development tree, not an already published
release. New Orchestrator stores use schema 3. Kernel remains schema 2.
The [full improvement plan](STORAGE_RETENTION_IMPROVEMENT_PLAN.md) is broader
than the capabilities implemented here.

## Content-addressed state

Application state, input, definition, decision events and recovery decisions use
a typed internal codec. Values of at least 64 KiB are stored by digest in the
same SQLite transaction. Stable large children are reused even when a sibling
changes. Historical revisions and events share these objects. Small references
and revision metadata still grow with the number of commits.

Public Run, history, event and receipt reads return the original logical JSON;
command fingerprints retain their original semantics. Missing objects, modified
digests and invalid structures raise `ContentIntegrityError`. The codec limits
logical values to 128 MiB, encoded values to at most 256 MiB, and
logical/reference depth to 100 by default. Physical size is checked before JSON
parsing or object hydration. A whole
decision event must fit the bound, including its request metadata. There is no
automatic compression, external blob interpretation, or pruning.

Task/attempt payloads and Kernel rows retain their existing JSON representation.
This implementation does not promise deduplication of every SDK payload category.

## Read-only usage

```python
from dispatcher_sdk.storage import inspect_storage_usage

usage = inspect_storage_usage("orchestrator.db", detail="physical")
logical = inspect_storage_usage("orchestrator.db", detail="logical", scan_limit=10000)
```

Missing paths are reported without creation. Inspection does not open a writer,
upgrade schemas, create backups, checkpoint WAL, decode all values or run an
integrity check. Physical reports separate the main file, WAL, SHM and journal,
allocated pages and free pages. Table/index attribution uses `dbstat` when
available and reports when it is unavailable. Logical scans have an explicit row
budget and report incomplete results rather than silently treating them as totals.

Shared content-object bytes are counted once. Physical file observations and
SQLite read snapshots are not one atomic observation, and separate databases
are not a coordinated group snapshot. Page-level reclaim estimates do not
promise an exact compacted file size.

## Maintenance exclusion

```python
from dispatcher_sdk.storage import maintenance_lease, inspect_maintenance

with maintenance_lease("orchestrator.db", "operator", "retention", lease_seconds=120) as lease:
    lease.check("orchestrator.db")
    status = inspect_maintenance("orchestrator.db")
```

SDK writer connections and ordinary Orchestrator readers hold a shared stable
path lock for their full connection lifetime. Maintenance requires the exclusive
lock. Close Runtime/Kernel connections before requesting maintenance; even an
idle open Kernel is a blocker. The maintenance descriptor exposes owner, purpose,
expiry and a monotonic fence. Expiry prevents admission to new destructive
phases or publications; an atomic commit admitted while valid may finish after
its deadline while the exclusive OS lock remains held. Expiry cannot steal that
lock. Leases may be renewed while valid. Stable lock anchors detect replacement
of a coordination file; deleting all coordination files is outside the protocol.

This is separate from recovery and execution leases. It does not discover
undeclared stores or stop non-SDK writers. All cooperating processes must use
this SDK build; older binaries and direct application SQL do not join the gate.
Dedicated read-only diagnostic APIs use SQLite snapshots without creating lock
sidecars; they do not provide a stable-inode maintenance lease.

## Explicit copy upgrade and compaction

```python
from dispatcher_sdk.storage import maintenance_lease
from dispatcher_sdk.storage_migration import upgrade_storage, compact_database

with maintenance_lease("old.db", "operator", "upgrade", lease_seconds=600) as lease:
    result = upgrade_storage("old.db", "upgraded.db", lease=lease)

with maintenance_lease("upgraded.db", "operator", "compact", lease_seconds=600) as lease:
    compacted = compact_database("upgraded.db", "compacted.db", lease)
```

`upgrade_storage` accepts the exact supported legacy schema 2, including its
recovery tables. It copies committed WAL contents, converts values in bounded
row batches, verifies logical equality and the target schema, then flushes and
publishes a new file without overwriting any existing destination. Other
components in that SQLite file are copied unchanged. Unknown legacy retention
timestamps are not invented.

`compact_database` accepts schema 3 and compacts a private copy. Sequence high
watermarks survive deletion of tail rows and compaction. Both functions require
a real, active lease and perform a conservative free-space precheck. They leave
the source in place and do not perform an application deployment cutover.

These copy operations are **not resumable large-store migrations**. A failure
requires restarting the copy; process death may leave a private temporary file.
They are not a verified operating procedure for the ModPort 134 GB archive.
Use adequate scratch storage and a separate rehearsal. Source-side external
writers must be stopped; a SQLite backup alone does not establish that a whole
application is quiescent.

## Conservative single-store retention

```python
from dispatcher_sdk.retention import RetentionPolicy, plan_retention, apply_retention
from dispatcher_sdk.storage import maintenance_lease

plan = plan_retention(
    "orchestrator.db", "run-1",
    RetentionPolicy(history_revisions=100, decision_events=1000),
)
if plan["applicable"]:
    with maintenance_lease("orchestrator.db", "operator", "retention", lease_seconds=120) as lease:
        result = apply_retention("orchestrator.db", plan, lease=lease)
```

`None` retains a category indefinitely; counts are nonnegative. Plans enumerate
candidate history rows, revision identities, decision events and unreferenced
content objects. Current values, all command receipts, historical reconstruction
baselines, other Runs and recovery evidence are protected. All receipts may pin
all historical revisions: a small configured window is not a deletion guarantee.

Subscriptions protect unconsumed decision events. Explicit event expiry raises
`EventCursorExpired` for an older cursor; its `expired_through` attribute gives
the boundary. A pruned historical revision raises `HistoryExpired`, rather than
being confused with an unknown identity. Sequence numbers are never reset.

For explicit inspection of surviving events, use
`orchestrator.read_events(run_id, after=0, allow_expired=True)`. This returns only
retained records, including non-decision events before the expiry boundary;
it does not reconstruct deleted events or promise complete history. Pagination
uses the last returned sequence as `after`. The default `read_events` behavior
and subscription-based `observe` still reject expired cursors.

Pruning events and revisions also removes their associated retention timestamps
in the same transaction. Expired revision identities remain recorded so readers
can distinguish intentional removal from an unknown revision.

Applying a plan recomputes its complete deletion set under an exclusive lease
and SQLite write transaction. Changed tokens, modified plans, incomplete scans
and corrupt reachable content prevent deletion. A durable maintenance receipt
makes repeat application idempotent. Deletion and content GC share a transaction;
physical file shrinkage requires a separate copy compaction.

The current policy does not expire attempts, Effects, outboxes, immutable audit
evidence, cross-store references, or age-based categories. The planner is a
bounded in-memory plan with row and 64 MiB accepted stored-payload budgets, not a
streaming million-record planning service. The row crossing the aggregate byte
budget may be fetched before rejection; individually oversized row bodies are
suppressed in SQLite. Parsed structures and reference sets add memory overhead,
so this budget is not a process RSS limit. It does
not infer ownership of application files from JSON strings.

## Authenticated component snapshots

`dispatcher_sdk.storage_snapshots` exposes `StoreGroupDescriptor`,
`snapshot_store_group`, `verify_snapshot` and `restore_snapshot`. A descriptor
declares the complete component database set and immutable owned blobs. Snapshot
creation locks all declared databases in stable order, includes committed WAL,
verifies component files and publishes the authenticated manifest last.

Authentication is HMAC-SHA256 with an explicit deployment-supplied key of at least
32 bytes; it is not a public-key signature or proof of an independently trusted
origin. Keep the key outside the artifact. Verification rejects altered, missing,
unexpected or symlink members and unsafe paths.

Snapshot and restored component files sit beside `.sdk-snapshot-readonly`.
SDK write connections and maintenance leases reject such artifacts, including
a dangling marker symlink; read-only inspection remains
available. Restore only targets a new directory, never overwrites an existing
store, and does not activate execution. There is no activation API yet. Do not
remove this marker as a substitute for resolving source ownership and recovery
requirements.

The descriptor is a caller-declared closed set, not an automatically discovered
cross-Run provenance graph. Files not registered in it are not covered.

## Provenance and conservative disposal

`dispatcher_sdk.provenance` provides `ProvenanceRegistry`, `plan_disposal` and
`dispose_run`. The deployment supplies the registry authentication key and
explicitly closes the declared reference scope. Incoming references, active
Runs, tasks, links, subscriptions, recovery and uncertain ownership block this
initial disposal implementation. Only eligible task-free terminal Runs can be
removed. It is not a general cascade deletion API.

Disposal authenticates a durable tombstone, preserves event sequence high water,
and resumes an interrupted registry/source transition using the same operation
ID. The source tombstone is committed with deletion. SDK reads and identity reuse
raise `RunDisposed`; shared content objects remain for a later retention GC.
Schema and trigger bodies are validated before destructive SQL, including retries.

Generic archive registration checks a local file digest, keeps the authoritative
hot locator, and labels the cold locator `origin_bound: false`. Explicit
`resolve(origin_digest, prefer_cold=True)` rechecks the artifact's presence and
digest. This does not prove that the artifact contains that Run, authorize hot
store deletion, or activate an archive.

## Remaining implementation work

The full roadmap still requires resumable large-store conversion, authenticated
hot/cold provenance activation, a compact successor with full retained evidence,
general terminal-Run disposal, external-object publication and GC, all retention
categories, and hard group quotas including concurrent reservations and temporary
peak space. The provenance/disposal support above has conservative eligibility rules and
does not imply these broad lifecycle guarantees.

Do not use direct SQL DELETE or VACUUM against live SDK stores to fill these gaps.
Use the implemented planners and copy operations within their declared scope.

## Validation and benchmark

Focused tests cover logical round trips, changing-sibling deduplication, replay,
corruption rejection, transaction rollback, stale plans, protected references,
lease ownership, copy-upgrade publication and snapshot authentication. These tests
do not establish that every roadmap capability exists or that the Windows
locking implementation has been exercised on a real Windows host.

Run the deterministic high-entropy state benchmark with:

```sh
PYTHONPATH=src python3 scripts/benchmark_state_storage.py --counts 100 1000 10000
```

The output records environment, page allocation, sidecar sizes and growth for
unchanged state, changing siblings, and omitted subsequent state submissions.

See the [recorded validation results](STORAGE_RETENTION_VALIDATION.md) for the
measured environment, commands and remaining verification limits.
