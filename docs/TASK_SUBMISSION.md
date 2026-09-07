# Submit one task atomically

`Orchestrator.submit_task()` combines `add_task`, an optional `watch_task`, and
an optional `dispatch` in one `apply_operations()` transaction. A successful
response means the task and requested delivery intent are persisted. Call
`flush()` and drive the Runtime separately to deliver and execute the command.

The method requires an existing Run, a caller-chosen `task_id`, a stable
`request_id`, and the Run revision on which the caller made its decision. New
requests require an Orchestrator constructed with `runtime=runtime`; supplying
only a Kernel is insufficient to freeze a new handler binding.

## Stable request identity and replay

Persist the request ID and arguments before submitting if the application must
recover from a lost response. Reuse the same Run ID, task ID, request ID,
`expected_revision`, and request content when retrying. Do not replace the
original expected revision with the Run's newer revision during a retry.

The method deterministically derives execution, idempotency, watch, and command
IDs from a versioned canonical SHA-256 namespace containing Run ID, task ID, and
request ID. Treat the generated IDs as opaque. Each request ID is scoped to its
Run and task; the method does not provide a globally unique application request
registry. Applications sharing one Kernel across multiple Orchestrator stores
must assign globally unique Run IDs across those stores. Independently created stores are not given
an automatic identity namespace. Conflicting persisted command content is
rejected rather than overwritten.

An identical retry returns the original committed Run snapshot, even after the
Run has advanced. It does not add another task, watch, or dispatch intent.
Changed payload, timeout, handler ID/version, revision, dependencies, watch,
dispatch choice, or retry policy is still checked against the original command
digest and rejected with `CommandConflict` when the request differs. Reusing the
generated command identity for an unrelated operation also conflicts.

New commands use `Runtime.command()` and its `handler-v1:` binding. On replay,
`submit_task()` reconstructs the operations using the original receipt's handler
binding while retaining the current call's other request fields for digest
validation. Adding or changing a handler in a new deployment leaves previously
accepted submissions unchanged. A matching replay can also be read without a
Runtime attached to the Orchestrator.

This replay behavior does not make pending work compatible with changed handler
code. An unexecuted old command still requires its original handler binding to
run. Keep the matching deployment available and use
[storage preflight](STORAGE_AND_UPGRADES.md) before retiring it.

## Options and workflow boundaries

- `dispatch=True` is the default. It enqueues dispatch; it does not call the
  Kernel or execute the handler inside the submission transaction.
- `dispatch=False` leaves the task planned for a later explicit dispatch.
- Omit `watch_target` to create no watch. Supply a JSON target to persist a
  completion watch; explicit `None` is rejected by watch validation. A watch
  records a delivery target and does not itself deliver a notification.
- `dependencies` applies the same checks as `Operations.add_task()`. If dispatch
  cannot proceed because dependencies are unfinished, the entire submission,
  including any watch, rolls back. Use `dispatch=False` to plan dependent work.
- The default retry policy is `RetryPolicy(max_attempts=1)`. Pass an explicit
  `RetryPolicy` to request execution retries. Retrying a submission after a lost
  response is independent of execution retry policy.

Finishing a Run, evaluating its results against business requirements, choosing
the next task, and acknowledging downstream consumption remain application
responsibilities. Successful execution leaves the Run running until the
application explicitly finishes it. Use ordinary `apply_operations()` when
submitting a broader atomic business decision or supplying application state and
event cursor updates.

## Runnable example

Save this example as a Python file and run it after installing the SDK. It uses
the core package and standard library. The temporary database makes the example
repeatable; use a retained application path and durable request records in an
application. Thread execution here is for a small trusted handler.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatcher_sdk.execution_kernel import Runtime
from dispatcher_sdk.orchestrator import Orchestrator


def echo(payload, context):
    return {"echo": payload}


def main():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "application.db"
        with Runtime(path, {"echo": echo}, isolation_mode="thread") as runtime:
            sdk = Orchestrator(path, runtime.kernel, runtime=runtime)
            sdk.create_run("run-1", command_id="create-run")
            request = dict(
                request_id="application-request-123", expected_revision=0,
                handler_id="echo", payload={"message": "hello"},
                timeout_seconds=5, watch_target="conversation-42",
            )
            accepted = sdk.submit_task("run-1", "task-1", **request)

            # Retry unchanged after a lost response; no new dispatch is added.
            assert sdk.submit_task("run-1", "task-1", **request) == accepted

            sdk.flush()
            runtime.run_once()
            sdk.sync()
            current = sdk.get_run("run-1")
            assert current["tasks"]["task-1"]["attempts"][0]["state"] == "succeeded"
            assert current["state"] == "running"
            assert sdk.submit_task("run-1", "task-1", **request) == accepted
            print("Execution finished; the application still owns the Run decision.")
            sdk.close()


if __name__ == "__main__":
    main()
```

Use `collect_notifications()` and `deliver_notifications()` when processing the
watch's delivery. Durable application receipt and fenced consumption are
described in [Notification inbox](NOTIFICATION_INBOX.md).

The returned receipt is a full Run snapshot, so submission cost still depends on
the current Run segment's size. Use bounded segments and paged reads for
long-lived applications.
