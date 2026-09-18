# Managed application API

The primary entry point is `from dispatcher_sdk import Dispatcher`. It composes
the existing Kernel, Orchestrator, Host and notification inbox in one SQLite file.
The package root stays lazy for applications which only use the Kernel.

## Lifecycle and submissions

Create `Dispatcher(path, handlers)` and enter its context, or call `start()` and
later `close()`. Construction alone allows durable enqueueing without starting
workers. Process isolation is the default; `isolation_mode="thread"` explicitly
opts into a mode that cannot kill blocked Python calls. `worker_count` controls
host workers, and `durability` configures every owned writer consistently.

`submit(handler_id, payload, request_id=..., timeout_seconds=30, target=None,
retry_policy=None)` returns `Task`. Reuse the original request ID and content
after response loss; a new ID means new work. Reusing an ID with changed payload,
handler, timeout, retry policy or target raises the root-exported
`SubmissionConflictError`. The default retry budget is one
attempt. The SDK creates an internal single-task Run and durable watch. Its Run
is an execution container; business acceptance and advanced Run finalization
remain explicit application decisions.

After reopening the same database with matching handlers, use `task(request_id)`
to recover a handle. `Task.state` and `Task.snapshot` read the latest persisted
orchestration view. `Task.wait(timeout=30)` returns the Kernel result dictionary
with `status`, `value` and `error`. It does not acknowledge a notification. Wait
timeout does not cancel execution. A `recovery_required` observation raises
`RecoveryRequiredError` with the request ID and snapshot for investigation.

Use `app.runtime` and `app.orchestrator` for cancellation, effect inspection,
evidence-based resolution or advanced dependencies. These are escape hatches;
the managed request identity must not be rewritten. Recovery which reopens a Run
with a new generation requires the explicit advanced API.

## Notification processing

Every managed task is watched. The Host writes each notification to the built-in
`NotificationInbox` before acknowledging upstream transport. With no callback,
notifications remain pending across restarts. The inbox shares the execution
database, so a consistent single-file backup includes receipt state.

`on_result(notification)` runs on a separate daemon consumer thread. A failure
schedules another delivery (default delay one second, inbox maximum five attempts).
Execution is not retried. `notification_id` is stable across delivery retries;
use it as an external idempotency key. A crash after an external call but before
settlement can cause redelivery. A callback exceeding `callback_lease_seconds`
(default 30) can also be redelivered. The callback must be synchronous.

For local SQL, omit `on_result` and call `consume_results(mutation, limit=100)`.
The mutation receives `(sqlite_connection, notification)` and performs business
SQL in the same transaction as the inbox consumed marker. Exceptions roll back
both and propagate. A valid lease schedules retry; an expired lease is reclaimed
by a subsequent claim. A settlement error never replaces the original mutation
error. The mutation must not manage transactions,
modify SDK tables or execute external effects. It should be short enough to
complete within its lease. The two consumption styles cannot be mixed on one
Dispatcher instance.

`app.inbox` exposes dead messages and explicit `retry_dead` for operator repair.
Retries are bounded; the SDK does not silently reset exhausted budgets.

## Preflight, diagnosis and shutdown

Construction checks storage schema and unfinished handler bindings before opening
writers. `DeploymentMismatchError.report` contains structured issues; a timed-out
or incomplete inspection also fails closed. This uses `check="bindings"`, not a
full integrity scan. `preflight_timeout` defaults to 30 seconds. Historical
pending commands need their original deployment or an explicit recovery decision.

`health()` reports host health, callback errors and consumer liveness without a
storage scan. `diagnostics(timeout_seconds=5)` performs bounded read-only storage
observations; see [SQLite operations](SQLITE_OPERATIONS.md) for cost and limits.

`close(timeout=...)` stops accepting new work, drains result consumers, then stops
the Host using the remaining deadline. If a consumer is blocked, it raises
`TimeoutError` and retains a
`stopping` state; the Host may still run while a consumer is draining. Keep
callback dependencies alive and retry close after it returns. Closing from the
result callback itself is rejected. Do not terminate the
application and assume daemon threads have finished external side effects.

For restored storage, use the explicit activation protocol described in the
[0.7 devdoc](DEV_0_7.md). Ordinary construction never removes snapshot markers,
migrates an incompatible store or bypasses retired-source protection.
