# Storage, upgrades, and deployment preflight

Version 0.6 changes the Orchestrator's persisted layout to schema 2 without
automatically migrating older, unversioned orchestration databases.
Opening an unsupported or damaged orchestration store raises an error instead
of recreating missing tables. The Kernel's protocol and SQLite schema remain
at version 2; the Orchestrator change does not introduce a Kernel schema 3.

The notification inbox has its own schema version 1, recorded in
`notification_inbox_meta`. Existing inbox tables must match that schema,
including the version marker and clock row. Opening a partial, unversioned, or
incompatible inbox fails without filling in missing tables.

## Adding same-Run recovery to a schema 2 store

An Orchestrator database created by an earlier schema 2 build needs an explicit
upgrade before this version can open it:

```python
from dispatcher_sdk.orchestrator import Orchestrator

Orchestrator.upgrade_schema("application.db")
```

The upgrade adds recovery coordination tables and generation columns. Existing
execution and watch registrations are assigned generation 0. SQLite applies the
upgrade in one transaction. Repeating it after a successful run makes no further
changes, and Run history remains unchanged.

`upgrade_schema()` accepts only a durable database with an Orchestrator schema 2
marker. It does not convert an unversioned store, repair damaged tables, or
upgrade the notification inbox. Back up the database and stop its writers before
running a deployment upgrade.

## Moving from an older orchestration store

1. Keep the old database, application deployment, handler implementations, and
   runtime dependencies available. Stop routing new work to that deployment.
2. Use the old deployment to drain pending execution, recovery, result delivery,
   notifications, and application consumption. Resolve work that needs an
   explicit recovery decision before retiring its workers.
3. Take a database backup and, when useful, a SQL export. Preserve the original
   database and deployment for historical inspection or unfinished recovery.
4. Start the 0.6 application with a new database. Transfer only the application
   input or state that the application explicitly chooses to carry forward.

A backup or SQL dump preserves the source layout; restoring it does not convert
an old Orchestrator schema into schema 2. There is no built-in in-place migration
for an unversioned store and no automatic replay into a new one. If Kernel and
Orchestrator tables share one file, an unchanged Kernel schema does not make that
file's old Orchestrator tables compatible with the new Orchestrator.

## Durability is configured on every writer

File-backed SDK writers default to SQLite WAL with `synchronous=FULL` and a
30-second busy timeout. Runtime/Kernel storage, Orchestrator connections,
notification inbox operations, and sandbox journals apply their configured
profile when opening writer connections. `FULL` synchronizes WAL commits;
durability still depends on the filesystem and storage honoring synchronization.

`durability="normal"` explicitly selects `synchronous=NORMAL`. It retains
SQLite's process-crash safety but may lose recent commits after host power loss.
Choose the profile separately for every component that opens connections,
including components sharing a database file. WAL journal mode is persistent;
`synchronous` is connection-local. Configuring one Runtime does not configure
an independently created Orchestrator or application SQLite connection.

For application-owned connections, call
`dispatcher_sdk.durability.configure_sqlite_connection(connection, path,
durability="full")` before starting a transaction. It configures the main
database, not attached databases. In-memory Kernel storage remains nonpersistent.

## Inspect before opening a new deployment

`dispatcher_sdk.storage.inspect_storage(path, handlers=...)` opens a read-only
SQLite connection and takes a consistent read snapshot. It does not initialize
an SDK writer or upgrade the source schema. The report includes:

- `exists`, `compatible`, `journal_mode`, and structured `issues`;
- Kernel, Orchestrator, inbox, and sandbox schema status for components present;
- Kernel execution counts by state;
- unavailable handler binding counts and up to 100 example mismatches.

For registered sandbox journals, preflight also checks original store/path
bindings, missing or damaged journals, and unavailable handlers required for
pending cleanup. These checks use separate read snapshots and do not form an
atomic multi-database inspection.

For a missing path, the function creates no file and reports `exists=False`.
`compatible=True` then means there is no existing incompatible schema, not that
a database was found. Omitting `handlers` skips deployment binding checks.
Deployment tooling must inspect the report and handle exceptions from filesystem
or SQLite access failures.

Binding checks cover unfinished Kernel executions and commands already persisted
by the Orchestrator but not yet present in the local Kernel store, including
planned tasks and work awaiting `flush()`. Terminal orchestration attempts that
never reached the Kernel do not require the old handler. When Kernel and
Orchestrator use separate files, inspect both: one file's report is not a
snapshot of the other file's execution state.

The report observes persisted schema and the database journal mode. It cannot
measure another connection's `synchronous` setting, prove hardware fsync
guarantees, or certify application-level recovery and delivery completion.

## Handler bindings during deployment changes

Create new commands with `Runtime.command(...)` to bind each command to its
handler ID, contract version, implementation, and fingerprinted deployment
state. The resulting `registry_revision` starts with `handler-v1:`. Adding an
unrelated handler does not change that command's binding. Changing the bound
handler can still make the command incompatible.

Commands created with a complete `runtime.registry_revision` retain strict
whole-registry matching. Adding an unrelated handler changes that full registry
fingerprint; existing commands are not silently rewritten into per-handler
bindings. Keep a matching old deployment available to drain or recover those
commands. Do not rewrite persisted revisions to bypass a mismatch.

## Backups and SQL exports

`backup_database(source, destination)` uses SQLite's online backup API, so its
single-database snapshot includes committed WAL data. It checks the backup's
integrity and produces a standalone database file that does not depend on a
WAL sidecar. Copying only a live source database's main file is not equivalent.

`export_database(source, destination)` writes a SQL dump from a consistent read
transaction. Both functions can preserve unsupported legacy SDK schemas without
opening their writers. A dump can be restored with SQLite into a separate empty
database for inspection; it retains the original schema and data.

Both functions refuse existing destinations with `FileExistsError`. They write
a temporary file beside the destination and publish through a hard link that
also refuses a destination created concurrently. The destination filesystem
must support hard links. Each call takes its own snapshot, so an online backup
and a later export may capture different committed states.

The completed artifact is flushed before publication. Directory metadata is
also synchronized on POSIX; Windows has no directory-sync step here, so the
helper does not promise that a newly published name survives sudden power loss.

Each database needs its own backup, including a separate notification inbox or
sandbox journal. Stop all relevant writers while taking the set of backups if
the application requires a coordinated cross-database point. These helpers do
not provide a cross-database atomic transaction or snapshot.

## Runnable example

This example uses only the SDK core and Python's standard library. Save it as a
Python file and run it after installing the SDK. It creates a temporary database
to demonstrate preflight, archival, and continuation; use application-managed
paths when retaining real data. The thread runtime here does not run any handler.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatcher_sdk.execution_kernel import Runtime
from dispatcher_sdk.orchestrator import Operations, Orchestrator
from dispatcher_sdk.storage import backup_database, export_database, inspect_storage


def echo(payload, context):
    return payload


def unrelated(payload, context):
    return {"value": payload}


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "application.db"
        with Runtime(path, {"echo": echo}, isolation_mode="thread") as runtime:
            sdk = Orchestrator(path, runtime.kernel)
            sdk.create_run("segment-1", command_id="create")
            command = runtime.command(
                "echo", execution_id="execution-1", idempotency_key="execution-1",
                correlation_id="segment-1", timeout_seconds=5, payload="hello",
            )
            planned = sdk.apply_operations(
                "segment-1", command_id="plan", expected_revision=0,
                operations=[Operations.add_task("task-1", command)],
            )
            # The command has not been dispatched or flushed to the Kernel.
            report = inspect_storage(path, handlers={"echo": echo, "extra": unrelated})
            assert report["exists"] and report["compatible"], report
            print("Preflight:", report["binding_mismatch_count"], "binding mismatches")
            print("Task page:", sdk.list_tasks("segment-1", limit=10))

            finished = sdk.apply_operations(
                "segment-1", command_id="finish", expected_revision=planned["revision"],
                operations=[Operations.cancel("task-1", reason="demo complete"),
                            {"kind": "finish", "state": "succeeded"}],
            )
            following = sdk.continue_run(
                "segment-1", "segment-2", command_id="continue",
                expected_revision=finished["revision"], input={"chapter": 2},
            )
            assert following["tasks"] == {}
            assert sdk.get_run_at("segment-1", finished["revision"]) == finished
            sdk.close()

        snapshot = backup_database(path, root / "snapshot.db")
        dump = export_database(path, root / "snapshot.sql")
        assert inspect_storage(snapshot)["compatible"]
        print("Backup and export created:", snapshot.name, dump.name)


if __name__ == "__main__":
    main()
```

## Long-running applications and retained history

Use `get_run_summary()` for metadata and task counts, `list_runs()` for Run
pages, `list_tasks()` for task metadata and latest attempts, and
`list_attempts()` for attempt history pages. Cursors are `after_run_id`,
`after_task_id`, and `after_attempt`; page limits are between 1 and 10,000.
These views avoid materializing an entire Run. Counts still require database
work, and payload size affects page cost.

After explicitly finishing a Run, `continue_run()` creates a new linked segment
with the inherited definition and explicitly supplied input. It does not copy
tasks or automatically carry application state into the new segment. Historical
revisions, command receipts, events, and late notifications remain associated
with the original Run and retain their identities. Continue processing old
segments' delivery and event obligations as needed.

Even with incremental storage and pagination, `get_run()`, historical
reconstruction, and operations that load or return a full Run still take work
proportional to the segment's materialized content rather than constant time.
`continue_run()` itself loads its predecessor. Use bounded segments and paged
reads to control that work; continuation retains history and does not reclaim
database space or erase delivery obligations.

## Validation status

The storage and inbox tests cover WAL-backed snapshots, refusal to overwrite,
legacy SQL export, schema rejection, pending-command binding checks, fencing,
and transaction rollback. Real Windows 11 x64/Python 3.12.10 validation passed
the storage and Run history tests, including WAL-inclusive backup, SQL export,
file flushing, non-overwriting publication and schema rejection. The complete
Windows suite passed 324 tests with 30 platform-specific skips.

The repository CI is configured for Linux and Windows with Python 3.10 through
3.13; that configuration does not prove every matrix entry has passed. See
[Windows runtime](WINDOWS_RUNTIME.md) for the recorded platform, commands and
limits.
