# Troubleshooting

[English](Troubleshooting.md) | [简体中文](Troubleshooting-zh-CN.md) | [Home](Home.md)

| Symptom | What to check next |
| --- | --- |
| Submission succeeded but no work runs | Keep a host alive, or explicitly flush, execute and sync. Inspect command delivery errors and handler compatibility. |
| `run_once()` returns no work | Check leases, `next_attempt_at`, eligible work and handler availability. An empty result does not prove a stall. |
| `flush()` returns zero | Inspect pending delivery records and their last errors; zero does not prove an empty queue. |
| Task succeeded but Run is still running | Validate the business result, release applicable waits and explicitly finish. |
| A successor did not start | Check settled dependencies and business approval, then explicitly dispatch. |
| `CommandConflict` | Replay the original request unchanged, including expected revision. Changed content requires a new decision identity. |
| `RevisionConflict` | Read fresh state, recompute the decision and use a new command identity. |
| Repeated notifications | Delivery is at least once. Durably deduplicate stable identities before acknowledging. |
| `recovery_required` | Inspect unresolved effects and reconcile external evidence before resolving. |
| Old database rejected | Follow the upgrade guide; do not edit schema metadata to bypass compatibility checks. |

See [submission](../docs/TASK_SUBMISSION.md), [recovery](../docs/SDK_RECOVERY.md),
[inbox](../docs/NOTIFICATION_INBOX.md) and [storage](../docs/STORAGE_AND_UPGRADES.md)
for exact contracts and recovery procedures.

When reporting a problem, include the SDK version or commit, Python version,
platform, isolation mode, relevant IDs and states, and a minimal reproduction.
Remove credentials and private payloads. Use
[GitHub Issues](https://github.com/FlightDan/dispatcher-sdk/issues) for bugs and
[security reporting](../SECURITY.md) for vulnerabilities.
