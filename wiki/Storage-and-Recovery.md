# Storage and local recovery

[English](Storage-and-Recovery.md) | [简体中文](Storage-and-Recovery-zh-CN.md) | [Home](Home.md)

The 0.7 single-file deployment uses SQLite WAL with `synchronous=FULL` by
default. Kernel schema remains 2, Orchestrator schema is 3, and the notification
inbox has its own schema 1. Product version and storage schema are separate.

Use `app.diagnostics()` or `dispatcher_sdk.diagnostics.inspect_diagnostics()`
to inspect execution states, `recovery_required`, delivery and inbox backlog,
and database/WAL sizes. Queries are read-only and share one SQLite snapshot when
all components use one file. A timeout returns an explicitly incomplete report.
The report does not measure SQLite lock-wait time.

Run `scripts/benchmark_sqlite_contention.py` on the target host to measure
end-to-end SDK operation latency under multiple processes. Keep the JSON report
with the deployment evidence. The repository's short FULL-durability runs showed
correct completion at 1, 4 and 8 workers, but claim tail latency rose sharply.
Those figures are observations from one machine, not service-level guarantees.

## Backup, restore and activation

`snapshot_store_group` creates an authenticated snapshot of a declared closed
set. `restore_snapshot` copies it to a new read-only directory. Restoring files
does not authorize execution.

`activate_restored_snapshot` provides a conservative same-host handoff. It
requires the original source paths to remain reachable, stopped and logically
unchanged since the snapshot. It checks handler bindings, rejects unsupported
external resources and hard-link aliases, retires the old source paths, copies
to a new gated directory, and publishes an authenticated successor receipt.

An activation can be retried with the same operation ID. Its reservation record
lives beside the successor so a crash during initial directory creation can be
distinguished from a successor that was already activated and later lost. The
SDK will not rebuild a lost committed successor from an old snapshot.

This is not cross-machine failover. If the old host is gone, the SDK cannot prove
that it stopped or reconcile work performed after the backup. Older SDK writers,
direct SQLite access and a trusted filesystem owner can bypass local markers.
Use external ownership fencing and application-specific reconciliation for that
case.

Existing indeterminate effects remain unresolved after activation. Queued work
can continue, while abandoned leases follow normal expiry and reaping. Never
delete retirement, reservation, pending or read-only markers by hand.

See [SQLite operations](../docs/SQLITE_OPERATIONS.md),
[storage upgrades](../docs/STORAGE_AND_UPGRADES.md), and the
[local recovery procedure](../docs/LOCAL_RECOVERY.md).
