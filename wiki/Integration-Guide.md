# Integration guide

[English](Integration-Guide.md) | [简体中文](Integration-Guide-zh-CN.md) | [Home](Home.md)

Choose the fewest integration steps that meet your application's needs.

Before connecting real work, review the [integration engineering principles](Engineering-Principles.md).
They cover version identity, supervised lifetime, evidence levels, candidate
freezing and safe discovery without moving business policy into the SDK.

| Goal | Start with | Working example |
| --- | --- | --- |
| Execute a function with persisted state | [SDK](../docs/SDK.md) and [public API](../docs/PUBLIC_API.md) | [Queued work after reopen](../examples/kernel_task.py) |
| Submit a task with replayable identity | [Atomic task submission](../docs/TASK_SUBMISSION.md) | Complete example in that guide |
| Execute a script and notify an Agent | [Scripts and wakeups](../docs/SDK_SCRIPT_WAKEUPS.md), [durable inbox](../docs/NOTIFICATION_INBOX.md) | [Script callback](../examples/sdk_script_wakeup.py) |
| Coordinate dependencies | [SDK operations](../docs/SDK.md) | [Dependent tasks](../examples/dependent_tasks.py) |
| Reconcile an interrupted external operation | [Recovery](../docs/SDK_RECOVERY.md) | [Effect recovery](../examples/effect_recovery.py) |
| Resume a failed or cancelled Run in place | [Same-Run recovery](../docs/SDK.md#reopen-a-failed-run-in-place) | Code in the SDK guide |
| Validate LLM output and request repairs | [Output contracts](../docs/SDK_OUTPUT_CONTRACTS.md) | Follow the application validation flow in that guide |
| Consume an audit trail | [Integration FAQ](../docs/SDK_INTEGRATION_FAQ.md) | [Durable audit](../examples/durable_audit.py) |
| Use remote execution | [Sandbox runtime](../docs/SANDBOX_RUNTIME.md), [adapters](../docs/SANDBOX_ADAPTERS.md) | Follow the service setup in those guides |

## Before connecting real work

Use persistent database and log paths. Choose a supported isolation mode and keep
matching handler deployments available for queued work. Give each decision a
stable identity and retain its original request for replay.

Callbacks should return promptly after durably accepting and deduplicating a
notification. Process the inbox separately. Each external write needs its own
idempotency or reconciliation scheme. Process execution alone does not restrict
file or network access.

## Reopen a terminal Run

Call `inspect_reopen()` before reopening a failed or cancelled Run. It reports
unfinished attempts, pending deliveries, active notification leases and an
existing continuation. `reopen_run()` checks those facts again before it
commits the decision, keeps the same `run_id` and history, and increments the
Run's `generation`.

After the reopen, pass `expected_generation` when changing the Run or submitting
more work. New attempts need fresh execution and idempotency identities, and
their handler binding must match the target deployment. A cancelled Run also
needs an authorization record. Successful Runs and Runs with a continuation
cannot be reopened.

Recovery progress is durable. The host can finish a prepared or committed
record after a restart. If the Orchestrator database already uses schema 2,
run `Orchestrator.upgrade_schema(path)` before opening it with this version.
You must start the upgrade explicitly. It is safe to repeat and preserves Run
history.

Check [storage and upgrades](../docs/STORAGE_AND_UPGRADES.md) before reusing old
stores; 0.6 does not automatically migrate old Orchestrator databases.
Review [Windows status](../docs/WINDOWS_RUNTIME.md) and
[Linux cleanup evidence](../docs/PROCESS_CLEANUP_VALIDATION.md) for deployment limits.

For an Agent implementing the integration, use the English
[DocsforAgents entry point](../DocsforAgents/README.md).
