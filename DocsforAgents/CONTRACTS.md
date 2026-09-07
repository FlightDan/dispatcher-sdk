# Contracts and pitfalls

These are integration checkpoints. Follow each linked guide for full semantics
and parameter definitions.

| Boundary | Required application behavior | Canonical guide |
| --- | --- | --- |
| Submission replay | Persist the request and replay it unchanged, including the original expected revision. A replay returns the historical receipt; read current state separately. | [Task submission](../docs/TASK_SUBMISSION.md) |
| Conflicting decisions | On `RevisionConflict`, read fresh state and recompute before submitting a new command identity. Do not replace the revision on an old decision. | [SDK operations](../docs/SDK.md) |
| Dispatch and completion | Explicitly dispatch successors and finish Runs. Settled dependencies can include failures; the application must check business acceptance. Open waits prevent finish but do not automatically prevent dispatch. | [SDK operations](../docs/SDK.md) |
| LLM output | Validate exact enums in structured fields and the full application contract. Natural-language success claims and type annotations do not establish business acceptance. | [Output contracts](../docs/SDK_OUTPUT_CONTRACTS.md) |
| Execution retry | `max_attempts` includes the first claim. Lease-expiry redelivery and ordinary retryable failures share this budget. Reopening the database does not replenish it. | [Recovery](../docs/SDK_RECOVERY.md) |
| Business repair | Persist a separate repair budget. Use explicit `new_attempt` and `dispatch` with new execution/idempotency identities, after the previous attempt settles and while the Run is running. Revalidate repaired output. | [Output contracts](../docs/SDK_OUTPUT_CONTRACTS.md) |
| External effects | Record recoverable operations through the Effect interface. Investigate uncertain outcomes with external evidence before resolving them. Arbitrary file writes and API calls are not guaranteed exactly once. | [Recovery](../docs/SDK_RECOVERY.md) |
| Notifications | Durably deduplicate by stable source and notification identity before acknowledging delivery. Keep callback acceptance separate from processing. | [Notification inbox](../docs/NOTIFICATION_INBOX.md) |
| Result consumers | Delivery is at least once. Deduplicate immutable result identities. One SDK state store owns the bound Kernel result queue; independent stores must not compete for it. | [SDK operations](../docs/SDK.md) |
| Event consumers | Commit the destination before acknowledging the observed batch. Use a dedicated subscription, stable source identity, and event sequence; drain pages even after Run completion. | [Integration FAQ](../docs/SDK_INTEGRATION_FAQ.md) |
| Isolation | Process mode is execution control, not a filesystem/network permission sandbox. Thread cancellation cannot stop a blocked thread. | [Public API](../docs/PUBLIC_API.md) |
| Restart and upgrade | Retain the database and matching handler deployment. Run compatibility/preflight checks before replacing it; do not assume automatic migration of old Orchestrator stores. | [Storage and upgrades](../docs/STORAGE_AND_UPGRADES.md) |

## Diagnose before retrying

An empty `run_once()` return does not prove the workflow is stuck. Inspect the
persisted lease, scheduled retry time, matching handler availability, and command
delivery errors. A zero `flush()` count does not prove there are no pending
messages. `sync()` observes execution facts; it does not reap leases or make
business decisions. Use the inspection and recovery interfaces described in
[SDK operations](../docs/SDK.md) and [recovery](../docs/SDK_RECOVERY.md).

Interrupted scripts can enter `recovery_required` because script execution
records an Effect. Verify external state before assuming a timeout or cancellation
made the script safe to repeat. See [script wakeups](../docs/SDK_SCRIPT_WAKEUPS.md).

