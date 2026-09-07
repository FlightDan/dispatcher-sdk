# Dispatcher SDK: Durable Task Orchestration for AI Agents

[English](README.md) | [简体中文](README.zh-CN.md) | [Wiki](wiki/Home.md) | [Docs for coding agents](DocsforAgents/README.md) | [API documentation](docs/SDK.md)

Dispatcher uses SQLite to persist execution state and adds process isolation, retries, recovery, and durable notifications.

**The core has no third-party runtime dependencies.**

Dispatcher runs submitted Python functions and scripts locally, and can run scripts
in remote sandboxes. It controls timeouts and cancellation and saves task state in
SQLite. For sandbox jobs, it collects bounded output and artifacts and keeps the
lifecycle state needed for cleanup after an interruption. Task subscriptions notify
your application when work finishes or needs recovery, so it can continue a
conversation, schedule another task, or handle an interrupted execution.

## What you can do

| Capability | Where it helps |
| --- | --- |
| Execution isolation and control | Run tasks in separate processes. In process mode, timeouts and cancellation terminate the supervised process tree to handle stuck tool calls. |
| Sandbox execution | Run scripts through a pluggable `SandboxBackend`, collect bounded output and artifacts, and persist lifecycle state for cleanup and recovery. The optional OpenSandbox adapter requires its SDK and a separate sandbox service. |
| Durable execution | Save tasks, results, and notifications in SQLite. Queued work remains available when you close and reopen the database. |
| Bounded retries | Configure attempt limits and backoff for retryable failures, avoiding endless reruns. |
| External effect recovery | Save receipts for file writes and API calls registered through the Effect interface. When an interruption leaves the outcome uncertain, wait for the application to verify and resolve it. |
| Multi-step orchestration | Record dependencies, business attempts, and wait conditions. The application decides when to dispatch, rework, or finish. |
| Results and notifications | Read execution results and script logs, and notify the application so its Agent can continue without repeated LLM progress checks. |

Dispatcher is a Python SDK embedded in your application. The core uses only
the standard library and SQLite, needs no separate queue service, and is not tied
to a particular model or Agent framework. The optional OpenSandbox adapter
adds the pinned `opensandbox` dependency and requires a separate sandbox service.

## Is it a fit?

Use Dispatcher when your Agent application needs to run tools or scripts, limit
execution time, retain task state, or organize tasks into a recoverable workflow.
You can also use it for a single function task without adding notifications or
multi-step orchestration.

Your application defines task content and business acceptance criteria, then
decides what happens next. Dispatcher controls execution, records state, and delivers messages
reliably. Keep the host process running while work executes in the background.

Integration boundaries:

- Process mode contains trusted code with timeouts, cancellation, and process cleanup. It does not provide a filesystem, network, or permission sandbox for untrusted code. Agent-generated code still needs application review or an additional sandbox.
- Linux process mode uses subreaper cleanup for detached descendants; other POSIX platforms use process-group cleanup. Native Windows process and script execution uses Job Objects and has passed native tests on Windows 11 x64 (build 10.0.26100.9168) with Python 3.12.10. See [Windows runtime](docs/WINDOWS_RUNTIME.md) for scope and results. Thread mode cannot forcibly stop a blocked handler.
- Resume with the original database and matching handler deployment. Reopening the database does not reset retry budgets or guarantee that interrupted tasks will automatically rerun.
- The SDK cannot undo a write or API call that has already happened. Uncertain outcomes require verification before recovery; arbitrary operations are not guaranteed to happen exactly once.
- Results and notifications are delivered at least once. The application must deduplicate durably using stable message IDs.

Version 0.6 is a developer preview requiring Python 3.10+. It changes the
Orchestrator storage layout to schema 2 and does not automatically migrate older
Orchestrator databases. Read [storage and upgrades](docs/STORAGE_AND_UPGRADES.md)
and the [compatibility guide](docs/PUBLIC_API.md) before upgrading.

## Install

To install from source, run these commands in a Linux terminal:

```sh
git clone https://github.com/FlightDan/dispatcher-sdk.git
cd dispatcher-sdk
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

In Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.
You can also download a wheel from
[GitHub Releases](https://github.com/FlightDan/dispatcher-sdk/releases)
and install it with `python -m pip install <path-to-wheel>`.

## Examples

### 1. Generate a report in the background, then continue a conversation

To verify the complete report-generation flow, this demo uses a script that
only prints `report ready`. Replace it with your own report-generation code when integrating.

1. The application submits a script and registers a conversation identifier for notifications.
2. Dispatcher runs the script in the background and delivers a notification to the application callback.
3. The callback writes the notification to the application's SQLite inbox, deduplicating by notification ID.
4. The example reads the inbox and prints the result. Your application can use this step to continue the conversation or handle the report.

After installing, run from the checkout:

```sh
python examples/sdk_script_wakeup.py
```

Expected output:

```text
Wake conversation-42: succeeded
report ready
```

<details>
<summary>Show the complete Python example: submit a script, receive a notification, read the result</summary>

Save this code as `demo.py` and run `python demo.py` after installing the SDK.

```python
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import threading

from dispatcher_sdk.execution_kernel import Kernel, ScriptSpec, script_handlers
from dispatcher_sdk.orchestrator import Orchestrator, OrchestratorHost


def main():
    with tempfile.TemporaryDirectory(prefix='sdk-wakeup-') as directory:
        root = Path(directory)
        inbox = root / 'application-inbox.sqlite3'
        with closing(sqlite3.connect(inbox)) as connection, connection:
            connection.execute('CREATE TABLE inbox (notification_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        accepted = threading.Event()

        def wake_agent(notification):
            with closing(sqlite3.connect(inbox)) as connection, connection:
                connection.execute('INSERT OR IGNORE INTO inbox VALUES(?,?)',
                                   (notification['notification_id'], json.dumps(notification)))
            accepted.set()

        runtime = Kernel.open_sqlite(root / 'work.sqlite3', script_handlers(), isolation_mode='process')
        orch = Orchestrator(root / 'work.sqlite3', runtime.kernel, runtime=runtime)
        orch.create_run('example', command_id='create')
        command = ScriptSpec("print('report ready')", (sys.executable, '-u'), root, root / 'logs').command(
            execution_id='script-1', idempotency_key='script-1', registry_revision=runtime.registry_revision,
            correlation_id='example', timeout_seconds=10)
        with OrchestratorHost(orch, wake_agent):
            orch.apply_operations('example', command_id='submit', expected_revision=0, operations=[
                {'kind': 'add_task', 'task_id': 'report', 'command': command.to_dict()},
                {'kind': 'watch_task', 'task_id': 'report', 'watch_id': 'report-wake',
                 'target': {'conversation_id': 'conversation-42'}},
                {'kind': 'dispatch', 'task_id': 'report'},
            ])
            # Demo process lifetime: wait on a Python event, with no LLM polling.
            if not accepted.wait(15):
                raise TimeoutError('demo did not receive its callback')
        with closing(sqlite3.connect(inbox)) as connection, connection:
            notification = json.loads(connection.execute('SELECT payload FROM inbox').fetchone()[0])
        assert notification['state'] == 'succeeded', notification
        assert notification['result']['value']['stdout']['tail'].strip() == 'report ready'
        orch.close()
        print(f"Wake {notification['target']['conversation_id']}: {notification['state']}")
        print(notification['result']['value']['stdout']['tail'].strip())


if __name__ == '__main__':
    main()
```

The example uses a temporary directory and removes its databases and logs on exit.
Use persistent paths in your application and keep `OrchestratorHost` running.
Return from the callback promptly after durably accepting the notification;
your application's inbox consumer continues the Agent workflow.

</details>

### 2. Stop a stuck task and its child process on timeout

Tool calls can block or launch additional child processes. Process mode cleans up
the supervised process tree after a timeout so the application can run other tasks.

In this Linux example, a function sleeps for 30 seconds and starts a child that
also sleeps. Its execution timeout is 2 seconds. After checking that the function
process and its child have exited, the example runs a normal task with the same
runtime to verify that it can continue working.

```sh
python examples/isolation_timeout.py
```

Expected output:

```text
timeout: timed_out; handler and child are gone
next task: succeeded
```

<details>
<summary>Show the complete Python example: process isolation, timeout cleanup, and another task</summary>

Save this code as `isolation_demo.py` and run `python isolation_demo.py` on Linux.
You can also read the [example file](examples/isolation_timeout.py).

<!-- example-platform: linux -->

```python
import os
from pathlib import Path
import sys
import tempfile
import time

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy


def sleep_with_child(payload, _context):
    child = os.fork()
    if child == 0:
        time.sleep(30)
        os._exit(0)
    Path(payload["pid_file"]).write_text(f"{os.getpid()} {child}", encoding="ascii")
    time.sleep(30)


sleep_with_child.__execution_kernel_revision__ = "isolation-timeout-v1"


def echo(payload, _context):
    return payload


echo.__execution_kernel_revision__ = "isolation-timeout-v1"


def command(runtime, execution_id, handler_id, payload, timeout_seconds):
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=execution_id,
        registry_revision=runtime.registry_revision,
        correlation_id=execution_id,
        causation_id=None,
        handler_id=handler_id,
        handler_contract_version=1,
        retry_policy=RetryPolicy(max_attempts=1),
        timeout_seconds=timeout_seconds,
        payload=payload,
    )


def assert_gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    raise AssertionError(f"PID {pid} survived timeout cleanup")


def main():
    if os.name != "posix" or not sys.platform.startswith("linux"):
        raise SystemExit("This example requires Linux process isolation.")

    with tempfile.TemporaryDirectory(prefix="dispatcher-isolation-") as directory:
        root = Path(directory)
        pid_file = root / "pids.txt"
        handlers = {"sleep": sleep_with_child, "echo": echo}
        with Kernel.open_sqlite(root / "jobs.sqlite3", handlers, isolation_mode="process") as runtime:
            runtime.submit(command(runtime, "timeout", "sleep", {"pid_file": str(pid_file)}, 2))
            timed_out = runtime.run_once()
            assert timed_out.state == "timed_out", timed_out.state
            assert timed_out.result.error.code == "handler_timeout"
            assert pid_file.exists(), "timed-out handler never reached startup"
            pids = [int(value) for value in pid_file.read_text(encoding="ascii").split()]
            assert len(pids) == 2, pids
            for pid in pids:
                assert_gone(pid)
            print("timeout: timed_out; handler and child are gone")

            runtime.submit(command(runtime, "next", "echo", {"message": "reused"}, 2))
            succeeded = runtime.run_once()
            assert succeeded.state == "succeeded"
            assert succeeded.result.value == {"message": "reused"}
            print("next task: succeeded")


if __name__ == "__main__":
    main()
```

The example runs a trusted function and records its PIDs in a temporary directory
for the cleanup checks. It controls the process lifecycle without restricting
the function's filesystem or network access.

</details>

Applications can also cancel tasks explicitly with `runtime.cancel`. Process mode
cleans up the supervised process tree. Thread mode only revokes authority to
publish results and Effects; it cannot forcibly stop a blocked thread.
If an interruption leaves an unresolved external operation, the task may enter
`recovery_required` instead of ending immediately. `ScriptSpec` executions register
an Effect, so check recovery state when a script is interrupted.
See [isolation and lifecycle behavior](docs/PUBLIC_API.md).

### 3. Resume queued work after restart and reconcile interrupted external operations

If your application exits after submission, reopening the same database lets it
claim work that was already queued. The [persistence example](examples/kernel_task.py)
submits a task, closes the runtime, reopens the database, and executes the task,
printing `{'total': 60}`:

```sh
python examples/kernel_task.py
```

If a task writes a file but crashes before saving its operation receipt, rerunning
it directly could duplicate the write. The [recovery example](examples/effect_recovery.py)
exits its worker at this point. The application inspects the file,
confirms the write happened, records that decision with `resolve_effect`, and
resumes execution while verifying there was no second write:

```sh
python examples/effect_recovery.py
```

Register external operations through `context.effects.execute_once`. Committed
receipts can be reused; unresolved operations enter `recovery_required` for the
application to resolve using external evidence. The example uses a controllable
clock to skip the lease wait and operates only on temporary files.

Ordinary execution failures and lease-expiry redelivery share
`RetryPolicy.max_attempts`, which includes the first claim and defaults to 1.
Set bounded attempts and backoff according to whether the task is safe to retry.
Business rework uses explicit new attempts, counted separately from execution
retries and notification redelivery. See the [recovery and retry guide](docs/SDK_RECOVERY.md).

### 4. Choose the next task based on the previous result

Before continuing, reworking, or waiting in an Agent workflow, your application
may need to inspect the previous result. Organize task dependencies within a Run
and explicitly submit the next step after reading that result.

The [dependency example](examples/dependent_tasks.py) first calculates an invoice
total. The application checks the result, passes it to a dependent receipt task,
and explicitly finishes the Run, printing `Invoice total: 60`:

```sh
python examples/dependent_tasks.py
```

A successful dependency does not automatically dispatch its successor, and a
successful task does not automatically finish the Run. Applications can also
register wait conditions, release them when satisfied, or submit a new business
attempt. See [SDK operations and orchestration](docs/SDK.md).

## Integrate with your Agent application

Choose the entry points you need:

| Capability | Entry points and application responsibilities |
| --- | --- |
| Function execution and isolation | Register handlers and select isolation with `Kernel.open_sqlite`; set the command timeout and `RetryPolicy`. |
| Scripts and logs | Use `ScriptSpec` to specify source, interpreter, working directory, and log directory; set the timeout with `.command()`. |
| Persistence and recovery | Keep a fixed database path and matching handler deployment. Record external operations with `context.effects.execute_once` and use evidence to `resolve_effect`. |
| Dependencies, waits, and business rework | Create a Run with `Orchestrator`; use `apply_operations` to explicitly submit tasks, dependencies, waits, new attempts, and completion. |
| Background execution | Use `RuntimeHost` for standalone execution or `OrchestratorHost` to drive execution, synchronization, and notifications for orchestration. |
| Application notifications | Associate a conversation or business task through `watch_task`'s `target`. Durably accept and deduplicate notifications in the callback; let the inbox consumer continue the workflow. |

## Further reading

- [Atomic task submission](docs/TASK_SUBMISSION.md): stable request IDs and per-handler command bindings.
- [Storage and upgrades](docs/STORAGE_AND_UPGRADES.md): durability profiles, preflight, backups, paged Run reads, and linked Run continuation.
- [Run storage validation](docs/RUN_STORAGE_VALIDATION.md): measured incremental history growth and remaining full-Run costs.
- [Durable notification inbox](docs/NOTIFICATION_INBOX.md): fenced processing and atomic application SQL.
- [Sandbox runtime](docs/SANDBOX_RUNTIME.md) and [OpenSandbox adapter](docs/SANDBOX_ADAPTERS.md): remote execution, artifacts, and disposal recovery.
- [Process cleanup validation](docs/PROCESS_CLEANUP_VALIDATION.md): Linux containment evidence and fallback limitations.
- [SDK operations and examples](docs/SDK.md): tasks, dependencies, waits, and explicit orchestration.
- [Reliable audit and dependency approval](docs/SDK_INTEGRATION_FAQ.md): integration FAQ and a runnable durable consumer example (Chinese).
- [Kernel execution contract](src/dispatcher_sdk/execution_kernel/README.md): isolation, timeouts, cancellation, and persistence.
- [Recovery, retries, and external effects](docs/SDK_RECOVERY.md): inspecting, waiting, and recovering after interruptions.
- [Script execution and application notifications](docs/SDK_SCRIPT_WAKEUPS.md): scripts, logs, callbacks, and notification retries.
- [Public API and compatibility](docs/PUBLIC_API.md): interfaces, platform differences, and upgrade constraints.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and tests,
[SECURITY.md](SECURITY.md) for vulnerability reports, and
[PROVENANCE.md](PROVENANCE.md) for source provenance.
Licensed under [Apache-2.0](LICENSE).
