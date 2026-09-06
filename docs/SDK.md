# Dispatcher SDK

`dispatcher-sdk` is an independently installable, standard-library-only
Python distribution. Its namespace is `dispatcher_sdk`; it does not
import `agent_dispatcher`, run Git, or invoke a model.
Applications supply handlers and routing policy.

| Package | Responsibility |
| --- | --- |
| `dispatcher_sdk.execution_kernel` | Durable execution, leases, fences, timeout, cancellation, retry, effects and result delivery |
| `dispatcher_sdk.orchestrator` | Explicit Run/task operations, dependencies, attempts, waits, events, command receipts and transactional delivery |

The SDK Orchestrator owns `sdk_*` tables; Kernel owns `kernel_*`.
Use public APIs across these boundaries. SDK methods never choose a next
business step. Creating a Run starts no task. Observing a successful result
does not dispatch a successor or finish a Run.

For lease-aware host loops, retry budgets, repository effects, and evidence
ownership, see [recovery and integration requirements](SDK_RECOVERY.md). See [public API and compatibility](PUBLIC_API.md) for import paths, versions,
and platform constraints.

## Install

From this repository checkout:

```sh
python3 -m pip install .
```

Build a wheel with `python3 -m pip wheel . --no-deps --wheel-dir dist`.
Python 3.10+ is required. Runtime code uses the Python standard library.

## Command-driven example

This complete example runs a local Python handler. Separate database files make
the persistence authorities visible. Thread isolation is sufficient for this
trusted, short handler; it cannot forcibly stop a blocked external call.

```python
from tempfile import TemporaryDirectory
from pathlib import Path
from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy
from dispatcher_sdk.orchestrator import Orchestrator

def echo(payload, context):
    return {"message": payload["message"]}

def command(runtime, execution_id):
    return ExecutionCommandV2(
        execution_id=execution_id, idempotency_key=execution_id,
        registry_revision=runtime.registry_revision, correlation_id="example",
        causation_id=None, handler_id="echo", handler_contract_version=1,
        retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=5,
        payload={"message": "hello"},
    )

with TemporaryDirectory() as directory:
    root = Path(directory)
    with Kernel.open_sqlite(root / "kernel.db", {"echo": echo},
                            isolation_mode="thread") as runtime:
        sdk = Orchestrator(root / "runs.db", runtime.kernel, runtime=runtime)
        sdk.create_run("example", command_id="create")
        sdk.apply_operations(
            "example", command_id="add-and-dispatch", expected_revision=0,
            operations=[
                {"kind": "add_task", "task_id": "hello",
                 "command": command(runtime, "hello-1").to_dict()},
                {"kind": "dispatch", "task_id": "hello"},
            ],
        )
        sdk.flush()          # Deliver accepted commands to Kernel.
        runtime.run_once()   # Host explicitly executes queued work.
        sdk.sync()           # Observe Kernel facts; make no routing decision.
        state = sdk.get_run("example")
        assert state["state"] == "running"
        assert state["tasks"]["hello"]["attempts"][-1]["state"] == "succeeded"
        sdk.apply_operations(
            "example", command_id="finish", expected_revision=state["revision"],
            operations=[{"kind": "finish", "state": "succeeded"}],
        )
```

Other explicit operations include `new_attempt`, `set_dependencies`, `cancel`,
`wait`, `release_wait`, and `signal`. Dispatch requires settled predecessors;
the application decides whether their outcomes permit progress. A new attempt
requires a settled previous attempt and a new execution/idempotency identity.
Finishing requires settled tasks and released waits. A host schedules `flush`,
execution workers and `sync`; constructing an Orchestrator does not start a background scheduler.
Use `OrchestratorHost` for an SDK-managed background execution loop.

## Decisions, receipts and recovery

Use `observe(run_id, subscription=...)` to read a snapshot, subscription cursor
and event batch from a consistent SQLite read. Compute application decisions
outside the transaction, then submit operations, application state and cursor
through `apply_operations`. Keep replayable decision code free of external
side effects; execute those through handlers. Separate application databases
need their own durable inbox/outbox protocol.

`acknowledge_events` advances a subscription with revision and cursor checks,
without emitting an event or changing the Run revision. It follows the same
command identity and exact-replay rules as other SDK commands.

An SDK `wait` records an open wait while the Run remains `running`. It does not
automatically block dispatch. Applications enforce their own wait scope and
explicitly `release_wait` when the condition is met. Open waits prevent finish.
Hosts can submit `signal` operations to trigger time-based application policy.

Commands use exact identity and content matching, including `expected_revision`
and cursor arguments. Replay the original command unchanged to recover its
original committed response. Reusing its ID with changed content raises
`CommandConflict`. `get_command_receipt` retrieves that historical response;
use `get_run` for current state. On `RevisionConflict`, obtain fresh state and
events, recompute the decision and use a new command identity. Revision checks prevent stale callbacks from advancing
their cursor or partially applying operations.

Execution retry and application retry are different. A Kernel `RetryPolicy`
governs execution attempts for a command. Application rework or an additional
business attempt requires an explicit `new_attempt` operation. An uncertain
external effect must follow the Kernel's fenced effect-recovery protocol;
`resolve_effect` forwards an explicit decision with an expected revision and
recovery identity. Retrying a task cannot prove whether an external effect
already happened. Use durable idempotency keys supported by the external system
and reconcile uncertain effects. There is no exactly-once guarantee for
arbitrary external side effects.

`max_attempts` includes the first claim. Ordinary lease expiry and retryable
execution failures share this mechanical limit; `redelivery_count` is not a
separate budget. With `max_attempts=1`, an ordinary first lease expiry becomes
`dead` with `lease_retry_exhausted`. Unfinished recorded effects instead park in
`recovery_required` before exhaustion is checked. Configure finite retries on
the original command only after making its effects safe to recover; do not
rewrite accepted commands or manufacture business attempts to bypass the limit.

An empty `run_once()` result is not a workflow-stall signal. Inspect the actual
lease expiration, `next_attempt_at`, registry/worker availability and delivery
health. `sync()` observes facts but does not reap execution leases, decide a
Run-level wait, or finish a Run; its return count is not a count of changes.
The host can call `runtime.reap()` before synchronizing and deciding. In the
runtime, configured lease duration is a floor: command timeout and startup
safety may extend it. Use the persisted snapshot's expiration for recovery.

Command delivery is also durable. `flush(limit=100)` returns the number of
messages newly delivered; it records individual delivery errors and continues
with other messages. A zero return does not prove the queue is empty. Inspect
`delivery_messages(execution_ids=None, pending_only=True, limit=100)` for the
command identity, attempts and last error. Failed messages remain eligible for
later flushes, with least-attempted messages selected first. A host chooses
when to retry; delivery failures emit `delivery.failed` events without choosing
an application retry or terminating a Run.

An explicit cancellation can settle an accepted dispatch that has not reached
Kernel yet. It uses the original execution command to establish its identity
and then requests cancellation. A late delivery observes the same settled
execution and cannot restart it. Cancellation of active external work still
follows the Kernel's process-cleanup and effect-recovery rules. Applications
must verify their particular command's delivery status before acknowledging
an upstream delivery.

Result delivery is at least once and independent of business routing. The host
can call `pump_results`, claim SDK result records under leases/fences, and
acknowledge them. Inspect delivery status and explicitly repair dead letters;
consumers must deduplicate immutable result identities. One SDK state store
owns the bound Kernel's result queue; concurrent consumers share that store.
Do not connect independent SDK stores to the same Kernel result queue.

Two separate delivery hops are observable and repairable:

| Hop | Inspect | Retry |
| --- | --- | --- |
| Kernel to SDK | `kernel_result_outbox_status`, `load_kernel_result_outbox` | `retry_kernel_result_outbox` |
| SDK to application | `result_outbox_status`, `load_result_outbox` | `retry_result_outbox` |

Both retries require the message's expected revision. `inspect_execution`
reads registered Kernel authority without ingesting results, so administration
remains possible when ingestion needs repair. Execution results retain their original identities.

`canonical_json` serializes strict JSON for content comparison without treating
booleans, integers and floats as interchangeable application values. See the
[Kernel contract](../src/dispatcher_sdk/execution_kernel/README.md) for process
isolation, timeout, effect uncertainty and recovery details.

## Script conversation wakeups

Applications can submit scripts and use `OrchestratorHost` to receive durable
Python callbacks on terminal outcomes or `recovery_required`, without LLM
polling. See [the integration example and delivery contracts](SDK_SCRIPT_WAKEUPS.md).
