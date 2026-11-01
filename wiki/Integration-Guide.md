# Integration guide

[English](Integration-Guide.md) | [简体中文](Integration-Guide-zh-CN.md) | [Home](Home.md)

Choose the shortest integration path that meets your application's needs.

Before connecting real work, review the [integration engineering principles](Engineering-Principles.md).
They cover version identity, supervised lifetime, evidence levels, candidate
freezing and safe discovery without moving business policy into the SDK.

| Goal | Start with | Working example |
| --- | --- | --- |
| Run one managed local task | [Managed application API](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/MANAGED_APPLICATION.md) | [Managed task](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/managed_task.py) |
| Inspect activity and supervise long-running work | [Execution activity and supervision](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/EXECUTION_OBSERVABILITY.md) | [Parent/child example](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/execution_observability.py) |
| Execute a function with persisted state | [SDK](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SDK.md) and [public API](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/PUBLIC_API.md) | [Queued work after reopen](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/kernel_task.py) |
| Submit a task with replayable identity | [Atomic task submission](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/TASK_SUBMISSION.md) | Complete example in that guide |
| Execute a script and notify an Agent | [Scripts and wakeups](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SDK_SCRIPT_WAKEUPS.md), [durable inbox](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/NOTIFICATION_INBOX.md) | [Script callback](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/sdk_script_wakeup.py) |
| Coordinate dependencies | [SDK operations](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SDK.md) | [Dependent tasks](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/dependent_tasks.py) |
| Reconcile an interrupted external operation | [Recovery](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SDK_RECOVERY.md) | [Effect recovery](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/effect_recovery.py) |
| Reopen an eligible failed or cancelled Run under a new generation | [Same-Run recovery](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SDK.md#reopen-a-failed-run-in-place) | Code in the SDK guide |
| Validate LLM output and request repairs | [Output contracts](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SDK_OUTPUT_CONTRACTS.md) | Follow the application validation flow in that guide |
| Consume an audit trail | [Integration FAQ](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SDK_INTEGRATION_FAQ.md) | [Durable audit](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/durable_audit.py) |
| Use remote execution | [Sandbox runtime](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SANDBOX_RUNTIME.md), [adapters](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SANDBOX_ADAPTERS.md) | Follow the service setup in those guides |
| Inspect SQLite backlog and contention | [SQLite operations](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SQLITE_OPERATIONS.md) | Run the contention benchmark on the target host |
| Activate a restored local snapshot | [Local recovery](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/LOCAL_RECOVERY.md) | [Local restore drill](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/local_restore.py) |
| Adopt and revise a legacy Run across separate stores (development only) | [Cross-store adoption](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SPLIT_STORE_ADOPTION.md), [current status](Improvement-Status.md) | Real host isolation and old-Run acceptance remain incomplete |

The existing same-Run recovery entry above covers reopening an eligible failed or
cancelled Run under a new generation. It does not mean the broader legacy
multi-task adoption, revision, activation and resume workflow has passed
acceptance. That workflow is still in the unreleased development candidate.

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
record after a restart. The 0.7.2 release uses Orchestrator schema 4. Older stores
need the preparation and copy-upgrade steps supported by the storage guide;
never open an incompatible store as a current writer.

Check [storage and upgrades](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/STORAGE_AND_UPGRADES.md) before reusing old
stores; 0.7 does not automatically migrate old Orchestrator databases.
Review [Windows status](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/WINDOWS_RUNTIME.md) and
[Linux cleanup evidence](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/PROCESS_CLEANUP_VALIDATION.md) for deployment limits.

For an Agent implementing the integration, use the English
[DocsforAgents entry point](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/DocsforAgents/README.md).
