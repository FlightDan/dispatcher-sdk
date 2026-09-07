# Changelog

## 0.6.0 (developer preview, unreleased)

- Runtime identity and independent storage read/execute/resume preflight verdicts;
  unsupported Kernel/Orchestrator schemas are checked before configuring WAL.
- Synchronous `ProjectionConsumer` persists complete pages before ACK, safely
  replays idempotent effects, and drains to a fixed high-water boundary.
- Read-only work-availability and cancellation reports expose scheduling causes,
  pending delivery, execution generations, uncertainty and cleanup evidence.
- Opt-in cancellation journal schema 1 is a separate file; core schemas remain
  unchanged. Runtime process/thread registrations are fenced by invocation
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
