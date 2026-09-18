# Managed tasks

[English](Managed-Tasks.md) | [简体中文](Managed-Tasks-zh-CN.md) | [Home](Home.md)

`Dispatcher` is the primary API for a local task in 0.7. It owns the Runtime,
Orchestrator, background Host and durable notification inbox in one SQLite file.
The lower-level APIs remain available for workflows that need dependencies,
waits or explicit Run decisions.

```python
from dispatcher_sdk import Dispatcher


def double(payload, context):
    return payload * 2


with Dispatcher("tasks.sqlite3", {"double": double}) as app:
    task = app.submit("double", 21, request_id="message-42")
    result = task.wait(timeout=10)
    print(result["value"])
```

Use a durable application identity as `request_id`. Repeating the same ID and
content returns the original task; changed content raises
`SubmissionConflictError`. After restart, reopen the same path and call
`app.task("message-42")` to recover the handle.

Process isolation is the default. It can terminate supervised trusted code, but
it does not restrict filesystem or network access. Thread mode must be selected
explicitly and cannot kill a blocked call.

## Results and application work

Pass `on_result=callback` for background delivery. Dispatcher first saves the
notification in its inbox, then invokes the callback. Callback failures retry
delivery without rerunning the task. The callback is still at-least-once, so an
external API call needs its own idempotency key.

For local application SQL, omit `on_result` and use
`app.consume_results(mutation)`. The mutation receives the SQLite connection and
notification; its SQL and the consumed marker commit in one transaction. Keep it
short and do not perform external effects from that transaction.

Execution success is not business acceptance. If an external effect is
uncertain, `Task.wait()` raises `RecoveryRequiredError`; inspect the evidence and
resolve it through the advanced Runtime/Orchestrator APIs.

Construction performs a schema and unfinished-handler binding check before it
opens writers. `DeploymentMismatchError.report` describes a rejected deployment.
`app.health()` is cheap and in-memory; `app.diagnostics()` runs bounded read-only
SQLite queries. See the [full API contract](../docs/MANAGED_APPLICATION.md).

`close(timeout=...)` stops new work, drains result consumers and then stops the
Host. A blocked callback can cause a timeout. Keep its dependencies alive and
retry `close()` after the callback returns.
