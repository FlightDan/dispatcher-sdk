# Troubleshooting

[English](Troubleshooting.md) | [简体中文](Troubleshooting-zh-CN.md) | [Home](Home.md)

| Symptom | What to check next |
| --- | --- |
| Submission succeeded but no work runs | Keep a host alive, or explicitly flush, execute and sync. Inspect command delivery errors and handler compatibility. |
| `Dispatcher` rejects startup | Read `DeploymentMismatchError.report`; keep the historical handler deployment available for unfinished work. |
| `task.wait(timeout=...)` times out | The caller's wait ended; inspect `task.observe()` and the execution deadline before deciding whether work should continue. |
| `run_once()` returns no work | Check leases, `next_attempt_at`, eligible work and handler availability. An empty result does not prove a stall. |
| `flush()` returns zero | Inspect pending delivery records and their last errors; zero does not prove an empty queue. |
| Task succeeded but Run is still running | Validate the business result, release applicable waits and explicitly finish. |
| A successor did not start | Check settled dependencies and business approval, then explicitly dispatch. |
| `CommandConflict` | Replay the original request unchanged, including expected revision. Changed content requires a new decision identity. |
| `RevisionConflict` | Read fresh state, recompute the decision and use a new command identity. |
| Repeated notifications | Delivery is at least once. Durably deduplicate stable identities before acknowledging. |
| `recovery_required` | Inspect unresolved effects and reconcile external evidence before resolving. |
| Cancellation report says local cleanup is unknown after restart | Keep the Kernel-bound settlement journal available and check that its `process_cleanup` note matches the execution ID, attempt and fence. Missing or malformed evidence stays unknown. |
| Old database rejected | Follow the upgrade guide; do not edit schema metadata to bypass compatibility checks. |
| Restored snapshot is still read-only | Restore and activation are separate. Use the local activation procedure; never delete the marker manually. |
| Local activation rejects a changed source | The source advanced after the snapshot. Reconcile the newer facts; the SDK will not run the older copy automatically. |
| Sandbox create/start result is unknown | Reconcile the operation key and provider records. Do not blindly create or start again. |
| Sandbox cleanup remains pending | Inspect the journal and provider, then run bounded recovery. Disposal does not settle external business effects. |

See [submission](../docs/TASK_SUBMISSION.md), [recovery](../docs/SDK_RECOVERY.md),
[inbox](../docs/NOTIFICATION_INBOX.md), [storage](../docs/STORAGE_AND_UPGRADES.md),
[local recovery](../docs/LOCAL_RECOVERY.md) and [sandbox runtime](../docs/SANDBOX_RUNTIME.md)
for exact contracts and recovery procedures. For observation gaps or stall notices,
see [execution activity and supervision](../docs/EXECUTION_OBSERVABILITY.md).

When reporting a problem, include the SDK version or commit, Python version,
platform, isolation mode, relevant IDs and states, and a minimal reproduction.
The [public observability consumer](../examples/sdk_observability_acceptance.py)
retains raw child-call and progress-call tracebacks, SQLite error codes and
original budgets. Set `SDK_ACCEPTANCE_EVIDENCE_DIR` to keep its evidence in a
chosen directory; the diagnostic records do not retry the failed call.
Remove credentials and private payloads. Use
[GitHub Issues](https://github.com/FlightDan/dispatcher-sdk/issues) for bugs and
[security reporting](../SECURITY.md) for vulnerabilities.
