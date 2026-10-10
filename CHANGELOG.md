# Changelog

## 0.7.2

- Cancellation reports read the Runtime's durable native process cleanup notes
  when cancellation receipts lack cleanup proof. Matching execution ID, attempt,
  fence and Kernel store binding are required, including after restart and without
  an attached Runtime. Evidence sources and note IDs remain visible separately
  from cancellation receipt IDs.
- Cleanup inspection queries the current generation directly, so unrelated
  diagnostic pages cannot hide its confirmation. Missing, mismatched, oversized
  or malformed evidence remains unknown; unresolved sandbox cleanup remains
  pending even when local process cleanup is confirmed.
- Native Windows descendant cleanup treats `ERROR_ACCESS_DENIED` as an exit race
  only when the same acquired process handle is signaled. A live process or any
  other termination error remains a cleanup failure.
- Settlement-note pages avoid repeatedly encoding earlier notes. Inspection
  retains its original time and byte limits, cursors and incomplete evidence rules.
- Active development and GitHub's default branch use `main`. Versions are
  identified by release tags such as `v0.7.2`.
- The portable process observability example uses finite startup and delivery
  margins for native Windows, checks the returned child output, and prints its
  full bounded observation on failure. SDK budget rules remain unchanged.
- The public observability consumer retains raw child, progress and cancellation
  failures, SQLite error codes and supplied budgets without retrying failures.
  Cancellation failures preserve bounded driver stacks and original control-call
  timings before cleanup; diagnostic and close errors do not replace the cause.

## 0.7.1

- Kernel storage uses layout schema 5 and Orchestrator storage uses schema 4.
  Kernel execution records retain their public v2 contract.
- Execution activity records handler entry, output, waits, tool and model use,
  progress, and bounded script-output facts. Read APIs remain separate from
  execution control. Durable sampling guards keep recovery from restoring time
  after an interrupted or unacknowledged clock sample.
- Bounded child-result recovery uses a read-only final check of the parent,
  child and ancestry after its one result read. It can return a result completed
  within the original window without rerunning business work or extending its
  budget; publication acknowledgement remains a separate obligation.
- Optional managed stall supervision reserves independent capacity and enforces
  native memory limits. It preserves the original notice and business budgets
  and reports capacity shortages and pending cleanup. Linux limits worker address
  space; Windows uses Job committed-memory limits. Validation results and
  previous development-version evidence are recorded in the acceptance index.
- Cancelled result recovery archives its original obligation within the same
  bounded operation window. Transient archive failures retain both the business
  rejection and archive error, and permanent storage failures keep their cause.
  Per-record storage timeouts stay at or below the original 0.1-second cap,
  including when floating-point deadline subtraction rounds upward.
- The Effect recovery example checks durable result publication after a worker
  returns a pending outcome, within the original execution deadline and without
  repeating the file mutation.
- Formal GitHub publishing reuses the exact successful candidate's tested wheel
  and source distribution, without repeating the matrix or rebuilding packages.
  Source distributions include the linked public CI recipes and historical
  documentation measurements.
- See [execution activity and supervision](docs/EXECUTION_OBSERVABILITY.md) and
  the [acceptance index](docs/EXECUTION_OBSERVABILITY_ACCEPTANCE.md) for behavior,
  validation evidence and remaining gates.

## 0.7.0.dev0

- `Dispatcher` is the primary managed application entry point: stable request
  submission, startup binding checks, owned Host lifecycle and durable inbox.
- Background result callbacks retry independently of execution; transactional
  local SQL consumption hides notification leases and commits with its ACK.
- Read-only operational diagnostics and reproducible multiprocess SQLite
  contention measurements expose backlog, capacity and verification limits.
- Explicit authenticated local snapshot activation retires participating source
  writers before enabling a single successor. It is not cross-machine failover.
- README quick starts use the managed API and document Orchestrator schema 3.
  See [0.7 design, compatibility and validation](docs/DEV_0_7.md).

## 0.6.0 (developer preview, unreleased)

- Structured shutdown reports preserve stop/error contracts and expose worker,
  final-pump, resource-close and notification phases without post-timeout scans.
- Explicit schema/binding/full inspection levels, cooperative scan budgets and
  progress; file-only capacity reads avoid implicit page attribution.
- Bounded read-only execution/result origin lookup across same-store segments.
- Request/result correlation and independent explicit caller receipts compose
  the existing inbox schema. Delivery does not imply reception or review approval.
  See [reliability APIs](docs/SDK_RELIABILITY.md).

- Orchestrator schema 3 stores large application-state children by content digest,
  sharing history/event payloads without changing logical reads or command digests.
  Existing schema 2 requires explicit copy upgrade; Kernel remains schema 2.
- Bounded read-only storage usage and retention planning; maintenance leases guard
  validated, idempotent history/event pruning and unreachable internal-object GC.
- Non-overwriting copy upgrade/compaction, authenticated component snapshot and
  read-only restore, and conservative registry-backed terminal-Run disposal.
  See [storage maintenance scope and limits](docs/STORAGE_RETENTION.md); full
  quotas, resumable large migrations and restore activation remain unimplemented.

- Runtime identity and independent storage read/execute/resume preflight verdicts;
  unsupported Kernel/Orchestrator schemas are checked before configuring WAL.
- Synchronous `ProjectionConsumer` persists complete pages before ACK, safely
  replays idempotent effects, and drains to a fixed high-water boundary.
- Read-only work-availability and cancellation reports expose scheduling causes,
  pending delivery, execution generations, uncertainty and cleanup evidence.
- Opt-in cancellation journal schema 1 is a separate file; it does not itself change core schemas. Runtime process/thread registrations are fenced by invocation
  generation so older invocations cannot supply newer cleanup evidence.
- Typed operation constructors and Run/event views, with a packaged `py.typed` marker.
- Optional notification callback for `OrchestratorHost`: omitted callbacks leave
  notifications queued while execution and synchronization continue.
- Read-only `inspect_recoveries(run_id)` joins application task identity with
  authoritative execution and current effect records, including their revisions.
- Reliable audit consumption example and integration FAQ covering independent
  cursors, durable acceptance, replay, draining and application-owned dependency approval.
- Per-handler `handler-v1:` bindings through `Runtime.command()` and atomic,
  exactly replayable `Orchestrator.submit_task()` with optional watch/dispatch.
- Orchestrator schema 2 stores incremental Run history and compact receipt
  references; paged reads and explicit linked continuation bound active segments.
  Loading a full Run still takes work proportional to the segment's content.
- SQLite writers default to WAL/FULL, with explicit NORMAL opt-in. Read-only
  storage preflight, non-overwriting backup and SQL export support upgrades.
- Durable notification inbox with source-scoped deduplication, fenced leases,
  processing retries and atomic business SQL plus consumed marker.
- Linux supervisor cleanup uses `waitpid(..., __WALL)` and ECHILD proof instead
  of the quiet interval. Real detached fork/clone and teardown-race tests cover
  success, timeout and cancellation boundaries; parent fallback limitations remain.
- Native Windows process/script execution via Job Objects, verified on Windows
  11 x64 build 10.0.26100.9168 with Python 3.12.10. The full suite passed with
  324 tests and 30 platform-specific skips; the native runtime module passed
  16 cases with only the non-Windows refusal case skipped. Storage, Run and
  sandbox checks, packaging and five installed examples also passed. See the
  [native validation scope](docs/WINDOWS_RUNTIME.md).
- Persistent sandbox lifecycle and recovery, with an optional OpenSandbox
  adapter. The core retains zero runtime dependencies; the `opensandbox` extra
  installs `opensandbox==0.1.16` and needs an external service.

Dictionary operations and explicit dependency routing remain supported.
Orchestrator storage changes to schema 2. Applications must drain older
unversioned databases and start a new store; there is no automatic migration.
Kernel storage and execution contracts remain version 2. See [storage and upgrades](docs/STORAGE_AND_UPGRADES.md),
[task submission](docs/TASK_SUBMISSION.md), [notification inbox](docs/NOTIFICATION_INBOX.md),
[Run storage measurements](docs/RUN_STORAGE_VALIDATION.md), and [sandbox runtime](docs/SANDBOX_RUNTIME.md).

## 0.5.1 (developer preview)

This is the first standalone Dispatcher SDK release, extracted from Agent Dispatcher.
The distribution is `dispatcher-sdk` and the Python namespace is `dispatcher_sdk`.
Existing consumers must update imports and installation dependencies.

- SQLite-backed execution with leases, fences, cancellation, bounded retries,
  durable results and explicit recovery of uncertain external effects.
- Explicit Run/task operations, dependencies, waits, signals, command receipts,
  result delivery and task notifications.
- Runtime and orchestration hosts, plus process-isolated script handlers.
- Independent source and wheel builds, runtime tests, and runnable examples.

Execution contracts remain schema v2. Renaming the Python package can change
handler fingerprints. This release does not migrate live databases or frozen
commands from the original namespace; start with fresh storage and keep the
original deployment available for existing runs.

In 0.5.1, scripts required POSIX process isolation. Windows supported thread-mode handlers;
thread cancellation cannot forcibly stop a blocked external call. See
[public API and compatibility](docs/PUBLIC_API.md) for the supported boundary.
