# Development-tree integration and diagnosis

This guide describes the current working tree, declared as `0.7.3`, and
its ongoing improvements following 0.7.2. The released 0.7.2 artifact and this
development tree are different deliverables: do not assume an interface or
schema described here exists in an installed 0.7.2 package. The
[implementation record](SDK_0_7_2_IMPLEMENTATION_STATUS.md) describes local
progress and outstanding validation; it is not a release or deployment record.

## Start with bounded inspection

For an existing Orchestrator database, the development-tree API below reads one
Run without constructing a Runtime or importing business handlers:

```python
from dispatcher_sdk.orchestrator import inspect_run_diagnostics
from dispatcher_sdk.storage import inspect_storage

storage = inspect_storage("runs.sqlite3", check="schema", timeout_seconds=3)
report = inspect_run_diagnostics(
    "runs.sqlite3", "run-id", task_limit=20, wait_limit=20,
    task_count_scan_limit=1000, timeout_seconds=3,
)
print(storage)
print(report.to_dict())
```

`check="schema"` checks structure; `bindings` adds unfinished-command binding
scans and `full` also performs integrity and count checks. The default is
`full`, which can cost more. Supplying a time budget limits cooperative work;
it is not a hard guarantee that every underlying operation returns by that time.
These calls do not upgrade the database. A schema check is not a handler
compatibility check or proof of a usable deployment.

The Run report has `complete`, `timed_out`, `error_code`, per-phase timings,
and separate task, wait and blocker completeness flags. If `task_count` is
`None`, use `task_count_lower_bound` as a lower bound, not an exact count.
When `next_task_id` or `next_wait_id` is present, pass it as `after_task_id` or
`after_wait_id` to request the next page. Each call observes a new snapshot;
pages collected while writers are active are not a single frozen view. The
report omits payloads and results and reports Kernel schema and active deployment
as unknown. Missing, timed-out or incomplete observations do not prove absence.

For a legacy two-file Run, `inspect_legacy_execution_page` from
`dispatcher_sdk.orchestrator` takes `(orchestrator_path, kernel_path, run_id)`
and optional `limit`, `after_task_id`, `after_attempt` and `timeout_seconds`.
Its `next_cursor` supplies the next pair. It requires Python 3.11+ and validates
schema markers and the cursor index only. Matching execution IDs are observations,
not proof of membership or command delivery; `not_observed` is not proof of
non-delivery. Calls and stores do not share an atomic snapshot. Read-only SQLite
connections may still cause SQLite to manage WAL sidecars.

## Select the recovery path

Use the existing `Orchestrator.reopen_run` workflow only for an eligible settled
failed or cancelled Run, with the original Run identity and an explicit recovery
decision. Its `command_id` is the idempotency key; revision and generation fence
stale decisions. Preparation, commit and activation are durable stages; after an
interruption inspect the existing recovery and use `advance_recovery` rather
than inventing a new decision. Unresolved effects and cleanup require their own
evidence and resolution. See [recovery](SDK_RECOVERY.md) and
[public API](PUBLIC_API.md).

For a managed split-store legacy Run, copying storage is only preparation. The
[split-store guide](SPLIT_STORE_ADOPTION.md) describes paged adoption, pause,
revision, participant installation, activation and resume. The host must
continuously exclude old writers and prove authority and budget continuity;
the SDK cannot infer those facts from a retired marker, absent PID or copy
receipt. Reconcile each store and original operation after an interruption.
Unknown committed outcomes remain unknown until supported by evidence.

Current development storage targets Kernel schema 12, Orchestrator schema 6,
and Settlement Journal schema 4.
Ordinary opening does not upgrade an older store. Explicit copy upgrade does not
activate a Run, fence the source, or move independent journals. A schema 2
settlement journal requires its own explicit copy; a changed Kernel path requires
the separately authorized rebind procedure. Preserve originals and coordinate
all consumers as described in [storage and upgrades](STORAGE_AND_UPGRADES.md).
Kernel v11 and Settlement Journal v3 each require an explicit copy upgrade.
An upgraded store cannot reconstruct pre-upgrade supervisor obligations.
For new process invocations, a committed exact-generation supervisor obligation
precedes process creation. If the SDK can prove creation was never attempted,
it settles the original result with `sdk_supervisor_not_invoked` in the same
Kernel transaction that resolves any registered obligation. This proof survives
budget or completion-clock deferral and an uncertain registration ACK. A
creation attempt with an ambiguous outcome stays unresolved for host review;
the absence of an `on_started` callback alone is not cleanup proof.

## Development lifecycle delivery

Kernel schema 12 stores lifecycle producer reservations and pending events. A
claim and its worker reservation commit together; cancellation attempts a
bounded reservation before revoking authority, but cancellation and cleanup
continue even if the reservation fails. Only events actually committed to the
Kernel can be replayed. Runtime delivery records a schema-4 receipt keyed by
Kernel store ID and outbox sequence. The receiver checks the actual Kernel
outbox identity, phase and payload before committing that receipt; only then
may the Kernel acknowledge it. For protected Runs,
the host verifier independently checks the committed receipt. A missing event or a
crash before persistence remains unknown.

A managed Runtime requires `lifecycle_verifier(credential, operation, identity,
event)`. The callback returns a mapping with boolean `allowed` and numeric
`expires_at`; successful `ack` also requires `receiver_committed=True`, and
producer recovery requires both `producer_dead=True` and
`evidence_unknown_acknowledged=True`. An explicit denial is distinct
from a verifier exception or expired authority, which are reported as failures.

A host that configures `lifecycle_verifier` must authorize the exact operation,
Run generation, execution, attempt and fence. Before authorizing `reserve`, it
must durably and idempotently associate the producer token with its independently
trusted owner, including for callbacks repeated before transaction commit. For
`ack`, it must verify the exact event against the actual committed receiver. For
schema-4 journals, `SettlementJournal.lifecycle_receipt_committed` checks the
Kernel store ID, outbox sequence, execution identity, phase and payload without
consulting an arbitrary note ID. The Kernel supplies store ID and sequence in
the `ack` verifier event; a missing or mismatched receipt must deny the ACK. For
`recover`, it must independently establish the producer is dead; a timeout or
missing process observation is not such proof. The callback is a host trust
boundary, not protection against a party controlling the SQLite file or Kernel
constructor. The synchronous callback receives no per-call deadline and cannot
be interrupted by the SDK; the host must enforce its own strict time bound. A
slow callback may exceed the requested operation timeout and hold the Kernel
lock or transaction.

`lifecycle_list_open_producers` provides bounded pages of authorized open
reservations; `lifecycle_inspect_producer` and `lifecycle_recover_producer`
support explicit host-directed recovery. Recovery requires both verified
producer death and explicit `evidence_unknown_acknowledged=True` from the host
callback. It atomically closes the producer and writes a Kernel-owned
`producer_recovered_evidence_may_be_missing` event even if all ordinary slots
were used. This reports uncertainty, not handler entry, settlement or cleanup.
Pending events survive recovery and the normal receiver must durably ACK the
marker before another claim can pass the outbox fence.
`lifecycle_prune_delivered` explicitly discards delivered payloads up to a
selected sequence; a later replay reports expiry rather than claiming a payload
match. For a quiescent generation with no open producer and no undelivered
event, `lifecycle_retire_generation` records a monotonic cutoff and removes
delivered outbox rows and closed producers in bounded batches. The host must
first prove that no in-memory or future producer can write the retired
generation. `SettlementJournal.prune_lifecycle_notes` then removes only its
schema-4 receipts and associated notes after independently checking the Kernel
cutoff. A late receiver is rejected. These explicit operations require the host
to preserve any diagnostic evidence still needed by consumers or audit policy.
Generic notes and unrelated ledgers are not covered.

Receipt creation, legacy reconciliation and receipt pruning acquire the Kernel
writer reservation before the Settlement writer. They only read Kernel facts
while holding that reservation through the Settlement commit; this prevents
retirement overtaking a receipt and avoids a lock cycle with protected ACK.

Pending v11 events retain their old event IDs. A pre-upgrade ordinary note with
the same ID cannot, by itself, prove whether the receiver committed this event
before losing the ACK. Delivery fails closed in that ambiguous case until the
host supplies independent reconciliation. Facts never committed before producer
failure remain unknown.

For that exact lost-ACK case, `SettlementJournal.reconcile_legacy_lifecycle_receipt`
requires the existing note sequence and ID, Kernel store ID and outbox sequence,
execution generation, phase and evidence, plus a trusted `verify_host` callback.
The callback must independently attest that the selected old note was the
receiver's committed write for that event; content equality is insufficient.
The claim includes both resolved store paths; the host must bind its attestation
to the active copy/incarnation and continuously exclude retired writers.
The SDK rechecks both stored rows and host attestation under the journal writer
before binding the v4 receipt. An unavailable or negative attestation leaves
the event pending for manual host recovery. The method does not ACK the Kernel
event; delivery must retry the original event and ACK through its normal gate.

For cancellation or interrupted process execution, inspect the exact execution
ID, attempt and fence. Cancellation state, a raw supervisor packet, process
cleanup and durable settlement are distinct facts. Missing or oversized evidence
stays unknown; a raw packet does not authorize settlement or prove cleanup.
See [cancellation evidence](CANCELLATION_EVIDENCE.md) and
[diagnostics and projections](SDK_DIAGNOSTICS_AND_PROJECTIONS.md).

The development paths and synthetic tests are not proof of a real host's writer
isolation, a production Run cutover, or acceptance on every platform. Consult
the implementation record for the current validation limits before adoption.
