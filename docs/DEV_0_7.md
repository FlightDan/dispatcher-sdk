# 0.7 development design and migration

Status: implemented and verified on `release/0.7.0` (`0.7.0.dev0`). The user approved
breaking changes and explicit local recovery activation. This document records
the implementation contract, migration impact and validation evidence.

## Goals and scope

The normal embedded application should understand handlers, stable request IDs,
tasks and results. The SDK owns runtime/host construction, durable notification
receipt, delivery retries, deployment preflight and shutdown. Applications still
define business acceptance and supply evidence for uncertain external effects.

SQLite remains the local storage backend. This release adds observable backlog
and storage size, reproducible multiprocess contention measurements, and explicit
activation of a restored local snapshot. Cross-machine automatic failover,
network filesystems and a new database backend are outside this release.

## Implementation sequence

1. Introduce `Dispatcher` as the primary application entry point with stable,
   replay-safe submission, managed execution, a durable inbox and result access.
2. Add read-only operational diagnostics and a multiprocess capacity benchmark.
3. Implement authenticated local restore activation with source exclusion,
   persistent retirement, deployment checks and failure-closed publication.
4. Update English/Chinese quick starts, version metadata, examples and migration
   documentation. Keep advanced execution and orchestration contracts available.
5. Independently review persistence and concurrency changes, fix findings and
   run focused tests, the full suite, typing, documentation and package checks.

## Application API

`Dispatcher(path, handlers, on_result=None, ...)` owns one SQLite file containing
Kernel, Orchestrator and inbox data. Entering its context starts execution;
construction alone permits durable enqueueing without starting workers.
`submit(handler_id, payload, request_id=..., ...)` returns a task handle. The
same ID and content return the original task; different content fails. A task
handle can be recovered using the request ID after restart. Internal Run IDs,
watch IDs and command IDs are deterministic and private to this entry point.

`Task.wait()` returns a terminal result, and raises a recovery-required error
instead of waiting indefinitely when external facts need adjudication. Waiting
does not consume the durable inbox. `on_result` receives notifications after
durable receipt and is retried independently of execution. It is at-least-once:
external calls still need their own idempotency key. `consume_results(mutation)`
offers transactional application SQL plus inbox settlement without exposing
leases; this callback must not perform external effects.

The default isolation is process isolation: unsupported hosts fail clearly.
Thread isolation must be selected explicitly and cannot kill a blocking call.
Shutdown is bounded; a callback that has not returned is reported, and its
dependencies remain owned until a later close succeeds. Deployment binding
checks run before opening writers and do not implicitly upgrade databases.

## Local activation protocol

Restoring files and authorizing execution are separate operations. An immutable
authenticated snapshot remains read-only. Activation validates the complete
declared component set and handler bindings, excludes participating old-source
writers, persistently retires each source, and publishes a single successor.
An interrupted transition must fail closed and support identity-bound retry.
Repeated activation must never authorize a second independent successor.
An authenticated reservation/commit record lives beside the successor directory,
so a lost successor cannot be mistaken for an activation that never completed.
Gated retries verify component bytes before enabling writers. Hard-link source
aliases are rejected because coordination and retirement use stable paths.

Local source ownership must be provable; an inaccessible original host is not
proof of exclusion. Unregistered external resources and unsupported sandbox
bindings must be rejected. Copying an old backup can omit effects that happened
after capture, so activation must either reject source divergence or explicitly
quarantine affected work. It must never infer that an absent receipt means an
external operation did not happen. Existing uncertain effects remain unresolved.

The protocol covers cooperating SDK writers and trusted local filesystem
ownership. It does not fence an external API, a rogue direct-SQL writer or an
older SDK which ignores the retirement protocol. Operators must stop these
before activation. No automatic cross-machine takeover is claimed.

## Compatibility and migration

| 0.6 application pattern | 0.7 primary path |
| --- | --- |
| Construct Kernel, Orchestrator and Host separately | Own a `Dispatcher` context |
| Create a Run and apply add/watch/dispatch operations for one job | `submit(..., request_id=...)` |
| Write custom SQLite notification deduplication | Built-in durable inbox |
| Manage notification leases for local SQL consumption | `consume_results(mutation)` |
| Manually inspect handler compatibility | Mandatory startup preflight with structured errors |
| Restore snapshot only for inspection | Explicit validated local activation |

Existing lower-level imports remain useful for advanced workflows; permission
to break APIs does not justify deleting working protocols. New automatic
preflight and process defaults apply to the new primary entry point. There is
no silent conversion from application-owned inbox schemas or arbitrary old Run
IDs. Existing applications may keep their lower-level integration while moving
new standalone tasks to `Dispatcher`.

Orchestrator storage is schema 3, Kernel schema/protocol 2, inbox schema 1.
Older Orchestrator stores require the existing explicit copy upgrade. Product
version 0.7 does not imply a schema 7. Restore retirement is an intentional
behavioral change: participating writers must refuse a retired source path.

## Acceptance and evidence

- Submit/replay/content conflict, restart and notification retry tests.
- Transactional result consumption rolls back both application SQL and ACK.
- Failed preflight cannot start execution; shutdown timeout remains recoverable.
- Active source, authentication mismatch, deployment mismatch and duplicate
  successor activation are refused; restored queued work can execute.
- Uncertain effects cannot be silently rerun; interruption does not activate
  both source and successor.
- Multiprocess benchmark records environment, operation latency percentiles,
  throughput, busy errors and durable exactly-one-claim correctness checks.
- Report measured results with their environment; no universal concurrency,
  power-loss, recovery-time or hardware durability guarantee is inferred.

Commands, measured results, review findings and remaining limits are recorded
below and in the operational guide.

## Independent review and repairs

Review found and regression tests now cover:

- Closing during a business SQL transaction must drain that consumer before the
  Host's final pump can contend for its write lock; elapsed shutdown is tested.
- Completed request replay retains its historical receipt even when the handler
  has been removed from the new deployment.
- An expired consumption lease must not replace the original mutation exception
  with a secondary settlement error. A later claim reclaims the expired message.
- Submission content conflicts have a root-exported `SubmissionConflictError`.
- Activation interruption after mkdir but before pending publication is resumable
  only with a matching external authenticated reservation.
- Lost committed successors cannot be reconstructed from their old snapshot.
- Committed but gated candidates are revalidated before gate removal.
- An SDK connection through a hard-link alias cannot evade source retirement:
  such source databases are rejected before handoff.
- A destination changed to a symlink after reservation is rejected before files
  are copied. Windows activation copies use writable handles for `fsync`.

## Verification completed

Validation ran on Linux/Python 3.12.3. Commands used the repository-local virtual
environment with an editable candidate installed, so documentation tests could
deliberately remove `PYTHONPATH` and still import the package.

- Full integration regression: `python -m unittest discover -s tests -v`,
  571 tests, 16 platform skips, no failures (475.228 seconds). This includes the
  existing source rebuild and isolated installed-wheel regression harness.
- After the independent-review fixes, rebuilt the final wheel, installed it with
  `--no-index --no-deps` into a clean virtual environment outside the checkout,
  and ran all four new test modules: 35 tests, no failures (28.516 seconds).
  These include 12 managed API tests, 16 activation tests, five diagnostics tests
  and two contention/capacity tests. The isolated fixture copies the benchmark
  script but never copies the SDK source tree.
- Public consumer typing: `python -m mypy --python-version 3.10
  --follow-imports=silent --warn-unused-ignores` over the four files in
  `tests/typing`, no issues.
- `python scripts/check_docs.py`: 446 local links and six executable English/
  Chinese README examples passed; none skipped.
- `python examples/managed_task.py` returned 42. `python examples/local_restore.py`
  returned 42 after activating the successor and confirmed source retirement.
- `git diff --check` passed.

The existing CI matrix also runs the new tests, typing consumer, managed example
and recovery example. This session did not execute that matrix remotely; its
Windows and alternate-Python entries remain CI verification, not measured local
results. `0.7.0.dev0` is a development candidate, not a published release.

## Measured SQLite workload

Linux x86-64, Python 3.12.3, SQLite 3.45.1, WAL/FULL, spawn workers, 256-byte
payloads and 25 submissions per worker. These short runs used the development
container while other verification was running; they are not isolated production
capacity estimates. The benchmark runs submit/execute/delivery phases, and does
not model a continuous mixed application workload or the whole Dispatcher Host.

| Workers | Tasks completed / outbox delivered | Tasks/s | claim p95 ms | claim p99 ms |
| --- | --- | --- | --- | --- |
| 1 | 25 / 25 | 11.87 | 16.02 | 16.60 |
| 4 | 100 / 100 | 20.45 | 16.15 | 1835.78 |
| 8 | 200 / 200 | 22.13 | 13.15 | 3677.87 |

Every run had `correctness.ok=true`, no missing or duplicate execution records,
and zero surfaced busy errors. High claim tail latency still occurred; a zero
busy error count does not mean there was no waiting. The capacity-limit exercise
rejected the entire transaction with `SQLITE_FULL` and committed successfully
after increasing the limit. It does not simulate physical disk exhaustion or
power loss. Raw evidence:
[1 worker](validation/sqlite-contention-1-workers.json),
[4 workers](validation/sqlite-contention-4-workers.json),
[8 workers](validation/sqlite-contention-8-workers.json).

Read [local recovery](LOCAL_RECOVERY.md) for conservative activation limits:
the original source must remain reachable and unchanged, all writers must use
the current coordination protocol, and this release does not activate arbitrary
historical backups after host loss. No real Windows activation or hardware
power-loss exercise was performed in this Linux session.
