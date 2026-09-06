# Changelog

## 0.5.1 (developer preview)

First standalone Dispatcher SDK release, extracted from Agent Dispatcher.
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

Scripts require POSIX process isolation. Windows supports thread-mode handlers;
thread cancellation cannot forcibly stop a blocked external call. See
[public API and compatibility](docs/PUBLIC_API.md) for the supported boundary.
