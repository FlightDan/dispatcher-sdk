# SQLite operations and capacity evidence

Dispatcher's SQLite profile is intended for a local runtime.  Production
acceptance must use measurements from the target filesystem, Python/SQLite
build, durability profile, process count, payload distribution, and backup
procedure.  Results from a developer laptop are not a cross-machine HA or
disaster-recovery guarantee.

## Read-only diagnostics

The standard single-file deployment has one entry point:

```python
from dispatcher_sdk.diagnostics import inspect_diagnostics

report = inspect_diagnostics("dispatcher.sqlite3", timeout_seconds=5)
```

The 0.7 `Dispatcher.diagnostics()` facade returns this report.  Deployments
that keep the Kernel, Orchestrator, or application inbox in different files can
call `collect_sqlite_diagnostics(kernel_path, orchestrator_path=...,
inbox_path=...)` directly.

The report includes:

- execution counts by state, runnable queued work, active work, and
  `recovery_required` count;
- Kernel result-outbox backlog and Orchestrator dispatch-outbox backlog;
- notification pending, delivering, delivered, dead, and ready counts;
- application notification-inbox pending, processing, consumed, dead, and
  ready counts;
- database, WAL, and shared-memory file sizes, plus allocated and free pages;
- sampling duration, query count, and whether all components shared one SQLite
  snapshot.

`backlog` includes dead records because they still require an operator decision
or an explicit retention action.  Delivered/consumed history is excluded.
`wall_clock_ready_pending` for Orchestrator notifications is evaluated against
the collector wall clock.  An application using a custom Orchestrator clock
must interpret that field against its own clock policy.

The collector opens each distinct file with SQLite `mode=ro`, enables
`query_only`, starts a read transaction, and runs aggregate queries.  It never
checkpoints, reaps a lease, retries a record, or advances an SDK logical clock.
Counts within one file share a snapshot.  Separate files cannot be sampled
atomically.  Filesystem sizes are observations outside SQLite's transaction and
may change while the report is assembled.

`timeout_seconds` is one wall-clock budget for the whole report, including all
component files and Python-side assembly.  The remaining budget bounds SQLite's
busy timeout, and a SQLite progress handler interrupts a count scan after the
deadline.  The busy timeout alone is not the report bound.  Because filesystem
calls and Python code cannot be asynchronously preempted, the collector checks
the budget before and after those phases and never returns `complete: true` once
the deadline has passed.  A timeout returns the observations collected so far
with `complete: false` and `stopped_reason: "timeout"`; consumers must not treat
missing sections in that report as zero backlog.

Sampling is not free.  State counts use the component indexes where available;
some totals, including open-watch counts, can scan table or index entries.  A
read transaction normally coexists with WAL writers, but a long-lived reader
can delay WAL frame reuse.  Keep collection bounded, monitor
`sampling_duration_ms`, and avoid high-frequency polling on a large store.

The report intentionally returns:

```json
{
  "sqlite_lock_wait_measured": false,
  "sqlite_lock_wait_ms": null
}
```

Python's standard SQLite interface does not expose time spent waiting for the
SQLite write lock.  Sampling duration and benchmark operation latency include
all call overhead and must not be renamed or interpreted as lock-wait time.

## Multiprocess contention benchmark

The benchmark uses separate OS processes and the public `SQLiteKernel` path for
every `submit`, `claim`, `start`, `complete`, result-outbox claim, and result-
outbox acknowledgement.  It validates that all submitted execution identities
finish exactly once in the terminal store and that every result outbox record
is delivered.

Run the small CI profile from the checkout:

```bash
PYTHONPATH=src python3 scripts/benchmark_sqlite_contention.py \
  --workers 2 \
  --items-per-worker 2 \
  --payload-bytes 32 \
  --durability full \
  --output /tmp/dispatcher-sqlite-contention.json
```

For a capacity decision, repeat with production-like process counts, payloads,
database location, mount options, encryption layer, and durability profile.
Keep the raw JSON with the release evidence.  It records platform, Python and
SQLite versions, implementation hash, configuration, elapsed throughput,
correctness counts, worker failures, and per-operation p50/p95/p99/max latency.

`operation_latency_under_contention` is end-to-end elapsed time around an SDK
call.  It includes transaction work, synchronization, filesystem work, process
scheduling, and any waiting hidden inside SQLite.  `busy_errors` counts only
`OperationalError` messages reported by SQLite as busy or locked.  A zero count
means no busy error escaped in that run; it does not prove that calls never
waited and does not establish capacity beyond the tested workload.

Treat a run as valid only when:

- `correctness.ok` is true;
- `worker_errors` is empty;
- execution and delivered-outbox counts equal `workers * items_per_worker`;
- the retained environment and parameters match the deployment under review.

CI runs a two-process smoke workload in `tests/test_sqlite_contention.py`.  It
asserts every SDK phase is observed, all execution and outbox counts match, the
report is strict JSON, and the capacity-limit transaction rolls back before a
later commit succeeds.  This smoke test detects protocol regressions; its tiny
sample is not a performance baseline.

Throughput from the default or CI profile is a smoke result, not a supported
service-level objective.  Establish an application-specific envelope by
increasing workers and items until p95/p99 latency or throughput crosses the
application limit, then operate below that measured boundary with headroom.

## Capacity-exhaustion exercise

Add `--capacity-limit-exercise` to the benchmark command.  The exercise sets
SQLite `max_page_count` on the benchmark Kernel connection, submits a payload
that cannot fit, verifies that the entire SDK transaction is absent, raises the
limit, and verifies that a later transaction commits:

```bash
PYTHONPATH=src python3 scripts/benchmark_sqlite_contention.py \
  --workers 2 --items-per-worker 1 --capacity-limit-exercise
```

This is a deterministic `SQLITE_FULL` transaction test.  It proves rollback
and reuse of the connection after that injected condition.  It does not model
a real full filesystem, quota implementation, I/O error, device loss, abrupt
power failure, torn write, or backup restore.  Those cases still require
environment-specific fault injection and restore drills.  In particular, do
not present this exercise as evidence of power-loss durability.

## Operational response

When backlog grows, first identify the layer:

- queued executions with no claims point to missing workers, a handler
  revision mismatch, or insufficient claim capacity;
- leased/running growth points to slow handlers, expired hosts, or capacity
  below arrival rate;
- `recovery_required` means an external effect needs evidence and an explicit
  resolution; adding workers does not settle it;
- result-outbox or dispatch-outbox growth points to a stalled bridge;
- notification growth points to delivery callbacks, while inbox growth points
  to the application consumer.

Record diagnostics before intervention, preserve the database and WAL together,
and use the component's fenced retry or recovery API.  Directly editing queue
rows destroys the evidence needed to distinguish retryable work from uncertain
external effects.
