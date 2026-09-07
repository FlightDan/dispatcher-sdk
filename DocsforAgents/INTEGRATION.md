# Implement an SDK integration

## 1. Select the execution and orchestration boundary

Use the Kernel runtime alone for standalone function execution. Add
`Orchestrator` when you need Runs, dependencies, watches, business attempts, or
application decisions recorded with revisions.

For new single-task integrations, start with the complete
[submit_task example](../docs/TASK_SUBMISSION.md). Use `apply_operations` when a
decision needs several operations or application state and cursor changes in
the same transaction. The [dependency example](../examples/dependent_tasks.py)
shows explicit dispatch, execution, synchronization, and Run completion.

Select isolation deliberately. Process mode controls trusted code's execution
lifetime; thread mode cannot forcibly stop a blocked handler. For code needing
filesystem or network restrictions, evaluate the
[sandbox runtime](../docs/SANDBOX_RUNTIME.md) and its actual provider policy.
Check [platform limits](../docs/PUBLIC_API.md) for the deployment target.

## 2. Prove the smallest execution path

From a checkout in an activated Python 3.10+ virtual environment:

```sh
python -m pip install .
python examples/kernel_task.py
```

This example prints `{'total': 60}` after closing and reopening the same
database. Read the [source](../examples/kernel_task.py), then replace its handler
and payload with application code. Preserve command identity and handler binding
requirements from the [public API guide](../docs/PUBLIC_API.md).

Use persistent application paths in a real deployment. The examples use
temporary directories to remain repeatable; those databases disappear on exit.
Reopening a store requires compatible handlers and does not reset retry budgets.

## 3. Keep execution running

Constructing an Orchestrator does not start a scheduler. Use `RuntimeHost` for
standalone execution or `OrchestratorHost` for orchestration, and keep the host
process alive. If implementing a manual loop, follow
[SDK operations](../docs/SDK.md) and [recovery](../docs/SDK_RECOVERY.md) for command
delivery, execution, lease reaping, synchronization, and delivery inspection.

For script execution, adapt
[sdk_script_wakeup.py](../examples/sdk_script_wakeup.py). Its event wait keeps
the demonstration process alive; your service needs its own lifetime management.
Use `ScriptSpec` to select source, interpreter, working directory, and log paths.
Read [script contracts](../docs/SDK_SCRIPT_WAKEUPS.md) before interpreting logs
or handling an interrupted script.

## 4. Accept notifications durably

Register the application's conversation or task identity as the watch target.
The callback should durably accept the notification and return promptly. A
separate application consumer performs conversation continuation or further work.

The script example uses a small application SQLite inbox. For source-scoped
deduplication, processing leases, and atomic business SQL, follow
[NotificationInbox](../docs/NOTIFICATION_INBOX.md). Keep its source ID stable
across restarts. File writes and network calls are outside its SQL transaction;
use an application outbox or the external service's idempotency protocol.

## 5. Make business decisions explicitly

Read the current attempt and validate the result against your application's
versioned output contract. Execution state `succeeded` is only one condition;
check schema, exact structured status enums, evidence, and business acceptance.

Submit the next dispatch, bounded repair attempt, wait release, or Run finish
explicitly. On a revision conflict, reload state and recompute the decision.
See [output validation and rework](../docs/SDK_OUTPUT_CONTRACTS.md) and
[contracts](CONTRACTS.md) before adding retries or recovery.

