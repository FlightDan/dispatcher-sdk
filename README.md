# Dispatcher SDK

[English](README.md) | [简体中文](README.zh-CN.md)

Dispatcher SDK runs Python handlers, saves execution state in SQLite, and lets
an application manage tasks through explicit commands. Close the process, reopen
the same database with the same handlers, and queued work is still there.
Work interrupted during execution follows the lease, retry and effect-recovery
rules described below.

Use the Kernel for individual jobs. Add the Orchestrator when jobs belong to a
Run, depend on other tasks, or need durable notifications. Your application
chooses what runs next and when the Run is complete.

This is a developer preview. APIs and persistence formats may change between
releases. It requires Python 3.10+ and has no third-party runtime dependencies.
The repository is `dispatcher-sdk`; the distribution is `dispatcher-sdk`
and imports use `dispatcher_sdk`.

## Install

From a checkout:

```sh
git clone https://github.com/FlightDan/dispatcher-sdk.git
cd dispatcher-sdk
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS, or
`.venv\Scripts\Activate.ps1` in Windows PowerShell. Then install:

```sh
python -m pip install .
```

Release packages are on [GitHub Releases](https://github.com/FlightDan/dispatcher-sdk/releases).
Download the wheel and install its local path with `python -m pip install`.
This project does not require a PyPI release, Git at runtime, an LLM, or a model
account. Build dependencies are needed when installing from source.

## Run a job and read its result

This complete example adds three invoice amounts. It uses a temporary database
and thread isolation for a short, trusted handler:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy


def total(payload, context):
    return {"total": sum(payload["amounts"])}


with TemporaryDirectory() as directory:
    with Kernel.open_sqlite(Path(directory) / "jobs.sqlite3", {"total": total},
                           isolation_mode="thread") as runtime:
        runtime.submit(ExecutionCommandV2(
            execution_id="invoice-1", idempotency_key="invoice-1",
            registry_revision=runtime.registry_revision,
            correlation_id="invoice-1", causation_id=None,
            handler_id="total", handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=5,
            payload={"amounts": [12, 18, 30]},
        ))
        snapshot = runtime.run_once()
        assert snapshot.state == "succeeded"
        print(snapshot.result.value)  # {'total': 60}
```

For persistent jobs, supply a database path you keep across restarts.
[`examples/kernel_task.py`](examples/kernel_task.py) closes the runtime after
submission and reopens the database before executing the job.

## Try the examples

After installing the SDK, run these from the checkout:

| Command | What it demonstrates | Expected output |
| --- | --- | --- |
| `python examples/kernel_task.py` | Submit, close, reopen, execute | `{'total': 60}` |
| `python examples/dependent_tasks.py` | Calculate an invoice, pass its result to a dependent receipt task, explicitly finish the Run | `Invoice total: 60` |
| `python examples/effect_recovery.py` | Kill a worker after a real file write, inspect the file, resolve the uncertain Effect, resume without a second write | `Recovered: succeeded; receipt was written once` |
| `python examples/sdk_script_wakeup.py` | Execute a Python script and deliver a callback into a durable application inbox; requires POSIX process isolation | `Wake conversation-42: succeeded`, then `report ready` |

The recovery example uses a controllable clock to advance an expired lease
without sleeping. Its worker really exits before committing the write receipt.
The examples create temporary files and remove them when finished.

In the dependency example, the application calls `create_run`, then
`apply_operations` to add and dispatch the calculation. It calls `flush`,
`runtime.run_once` and `sync`, checks the result, and submits the receipt task
with `dependencies=["calculate"]`. The application passes the result as the new
task's input and explicitly calls `finish` after checking the receipt. A
successful task alone does not advance or finish the Run.

For background execution, `OrchestratorHost` drives workers, synchronization and
task notifications. Its callback should commit to your application's inbox and
return promptly. The script example uses SQLite deduplication on
`notification_id`; a real inbox consumer can launch a conversation or another
application job. The SDK does not launch an Agent conversation itself.

## Execution and recovery rules

- SQLite stores execution facts, orchestration commands and delivery queues.
  Result and notification delivery are at least once. Consumers must deduplicate
  by the stable message identity.
- `RetryPolicy.max_attempts` includes the first claim and defaults to 1.
  Ordinary lease-expiry redelivery and retryable handler failures share that
  budget. Reopening a database does not grant another attempt.
- Wrap external mutations in `context.effects.execute_once`. A committed
  response can be reused. If a worker disappears between the external mutation
  and its receipt, the execution waits in `recovery_required` for an explicit
  decision based on external evidence. Arbitrary file writes and API calls are
  not made exactly once by the SDK.
- An empty worker poll can mean a live lease or retry backoff. It does not prove
  a Run is stuck or finished. Applications decide business retries, waits and
  completion through explicit operations.
- Process isolation needs POSIX fork support and a guarded executable entrypoint.
  Linux includes detached-descendant cleanup; other POSIX hosts provide
  process-group cleanup. This is containment for trusted handlers, not a sandbox
  for hostile code. Scripts require process mode.
- Windows uses thread isolation. Python cannot forcibly stop a blocked thread;
  cancellation revokes result/effect authority but cannot undo an external action
  already in progress.

## Documentation

- [SDK operations and examples](docs/SDK.md)
- [Recovery, retry budgets and external effects](docs/SDK_RECOVERY.md)
- [Scripts and application wakeup callbacks](docs/SDK_SCRIPT_WAKEUPS.md)
- [Public API, platform behavior and compatibility](docs/PUBLIC_API.md)
- [Kernel persistence and isolation contract](src/dispatcher_sdk/execution_kernel/README.md)

CI covers Linux and Windows on Python 3.10, 3.11, 3.12 and 3.13. Process-specific
tests run only where supported; macOS is not in the initial CI matrix. Check the
candidate's CI results before relying on a particular platform/version pair.
The preview has no general database migration facility. Keep the matching
handler deployment when resuming work; finish or archive existing Runs before
an incompatible upgrade.

See [CONTRIBUTING.md](CONTRIBUTING.md) for tests and development,
[SECURITY.md](SECURITY.md) for private vulnerability reports, and
[PROVENANCE.md](PROVENANCE.md) for source provenance. Licensed under
[Apache-2.0](LICENSE).
