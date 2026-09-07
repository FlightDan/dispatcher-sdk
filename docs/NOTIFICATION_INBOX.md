# Durable notification inbox

`NotificationInbox` is a receiver-side store for application notifications.
Receipt and processing are separate: delivery acknowledges upstream after
`accept` commits, while application workers independently claim and consume the
stored notification. The inbox starts no transport integration or background
worker.

```python
from dispatcher_sdk.orchestrator.inbox import NotificationInbox

inbox = NotificationInbox("application.sqlite3")  # WAL + synchronous=FULL

# sdk is the originating Orchestrator. Keep this source ID stable across restarts.
sdk.deliver_notifications(
    lambda payload: inbox.accept("origin-production-01", payload),
    owner="application-delivery",
)
```

The primary key is `(source_id, notification_id)`. Different originating stores
can use the same notification ID independently. `source_id` is a caller-managed
namespace, not proof of authentication; do not derive it from a transient worker
or delivery lease.

Notification dictionaries supply their embedded `notification_id`. A JSON value
without one can instead use an explicit ID:

```python
inbox.accept("external-source", {"delta": 3}, notification_id="event-42")
```

Objects with `to_dict()` are also accepted if the resulting value is strict JSON.
An explicit ID that disagrees with an embedded ID is rejected. Reusing the same
source/ID with different canonical JSON raises `CommandConflict`. Identical
replays return the current inbox record without changing its state, lease,
attempt count, or original processing budget. A replay never requeues an already
consumed message.

## Process local SQLite changes atomically

Application tables can live in the same file. Initialize their schema through
the application's normal database setup, then apply business changes through
`consume`:

```python
# The application's schema includes:
# CREATE TABLE application_totals(name TEXT PRIMARY KEY, total INTEGER NOT NULL)

def apply_sql(connection, payload):
    connection.execute(
        "INSERT INTO application_totals VALUES('handled',1) "
        "ON CONFLICT(name) DO UPDATE SET total=total+1"
    )

lease = inbox.claim("application-worker", lease_seconds=30)
if lease is not None:
    inbox.consume(lease, apply_sql)
```

`consume` validates the lease, runs the synchronous callback, checks the lease
again, and marks the notification consumed in one SQLite write transaction.
It loads the callback's payload from storage, not from the caller's mutable
lease payload copy. A callback error or observed lease expiry rolls back both
the business writes and the consumed marker. A replay of an already committed
consumption with the same lease skips the callback entirely.

Use the supplied connection for those business mutations. Do not commit,
rollback, start savepoints, close the connection, change its authorizer, or keep
it after the callback returns. The helper rejects SQL transaction control,
`executescript`'s implicit pre-commit, attached databases, PRAGMA changes, and
writes to its reserved `notification_inbox_*` objects. The callback is trusted
application Python, not a sandbox; it must not disable these protections.
Async callbacks are rejected rather than acknowledged without awaiting them.

Calling `consume(lease)` without a callback commits only the consumed marker.
Business SQL performed earlier through a separate connection is not part of
that atomic unit.

## Processing leases and retries

```python
lease = inbox.claim("application-worker", source_id="origin-production-01")
if lease is not None:
    try:
        inbox.consume(lease, apply_sql)
    except StaleFenceError:
        pass  # This worker no longer owns processing authority.
    except Exception as error:
        try:
            inbox.fail(
                lease,
                error={"type": type(error).__name__, "message": str(error)},
                retry_delay=2,
            )
        except StaleFenceError:
            pass
```

Import `StaleFenceError` from `dispatcher_sdk.execution_kernel`.

Each claim has a new lease ID and a monotonically increasing fence. Concurrent
claimers cannot own the same active attempt. Expiry and reclaim invalidate the
old worker's consumption and failure commands before any business callback runs.
Lease checks sample time after obtaining SQLite's write lock. A persisted clock
watermark prevents an observed expiry from being undone by a backwards wall
clock, including when the expiry caused a transaction rollback.

The default processing budget is five attempts, set on first acceptance with
`max_attempts`. Explicit failures become pending after `retry_delay`, or dead
when the budget is exhausted. Expired processing leases are reclaimed by the
next `claim` call, with exhausted messages becoming dead. Replaying the same
failure receipt with the same lease/error/delay is harmless; changing that
receipt raises `CommandConflict`.

Inspect and explicitly retry dead messages:

```python
for message in inbox.list_messages(state="dead", limit=100):
    # Retry only after the application has addressed the cause.
    inbox.retry_dead(
        message["source_id"], message["notification_id"],
        expected_revision=message["revision"],
    )
```

`retry_dead` requires the observed revision and resets the attempt counter while
preserving the fence. `get(source_id, notification_id)` returns one detached
record; `list_messages` can filter source and state. These reads do not reap
leases or change records.

## Guarantee and retention boundary

This design prevents repeated committed business SQL for a retained inbox
identity when the mutations use `consume`'s transaction. A crash before commit
rolls back the business changes and marker; a crash after commit leaves the
marker available to suppress processing of an upstream redelivery.

This transaction does not guarantee exactly-once behavior for network calls,
file operations, messages, or other external side effects. An effect performed
in the callback can repeat after a crash or rollback. Write a business outbox
entry in the same transaction and deliver it with a stable idempotency identity,
or use the external system's own deduplication protocol. A callback exception
cannot undo an external effect that already happened.

Consumed identities and their payloads are retained; there is no automatic
pruning. Deleting them removes the protection against later upstream replay.
Keep the source namespace and inbox database together across restarts and
backups.

Pass `durability="normal"` to the constructor to select the same weaker
power-loss durability profile as other SDK stores. Every inbox connection
defaults to `full`. In-memory databases are rejected. Connections are
operation-scoped, and `close()`/the context-manager exit have no persistent
connection to close.

## Validation

```sh
PYTHONPATH=src python3 -m unittest tests.test_notification_inbox -v
```

The tests cover source-scoped conflicts, replay after consumption, concurrent
receivers and claimers, repeated concurrent consumption, SQL rollback, a real
process crash inside the business transaction, stale fences, expiry during
lock waits and callbacks, backwards clocks, dead-letter retries, rejected
transaction control, and upstream delivery crashing after inbox acceptance.
