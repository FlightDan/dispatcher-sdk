# Exact completion delivery after a late commit

Status: **implementation in progress; not an acceptance result**. A controlled
real SQLite COMMIT interleaving demonstrated that an authorized result can be
durable while its settlement receipt is absent; see the acceptance record and
`tests/test_completion_late_commit_receipt.py`. The worker's result, a receipt,
and cleanup confirmation are separate facts.

## Binding and ordering

### Ordinary Runtime integration prerequisite (2026-11-05)

The owned-return API is not a repair for `floor_above_ack` by itself.
`_capture_owned_return` invokes the same completion observation before creating
its capability. The real SQLite regression
the historical `test_owned_return_does_not_authorize_post_sample_watermark`
commits a later watermark between the original sample and reader creation;
the owned path rejects it, creates no capability and leaves the execution
running. The focused test passed; its output is retained at
`/tmp/sdk-owned-return-floor-boundary-20261105.log`. This confirms a safety
boundary, not successful result delivery.

Changing the ordinary return callback to use that API would therefore retain
the observed integration failure. Removing the floor check would also accept
unproven ordering, including earlier high samples followed by wall rollback.
Holding the main Kernel lock across snapshot acquisition was separately
rejected because outstanding sampling owners need that lock to acknowledge
their original observations.

A repair must first distinguish observations ordered before the original
return from writers ordered after it at the shared storage serialization
boundary, including other Kernel connections. A later snapshot or a local
thread capability alone cannot supply that historical evidence. The original
sample and deadline must survive effect collection and recovery unchanged.
Only after proving that boundary can ordinary Runtime reuse owned delivery:
it needs a real journal activation and reconciler, versioned claim admission,
confirmed pre-entry intent and Kernel registration, and the existing owned
decision, late handoff and recovery lifecycle. Synthetic journal identities or
falling back to unmarked completion after failed admission are not valid.
These remain implementation prerequisites; G14 and G15 are not complete.

The first storage primitive for this prerequisite now exists as the private
`_finish_budget_sample(..., _capture_lease=lease)` mode. It requires a locked,
exact live sample owner and a previously committed marker. Inside its write
transaction it validates the existing floor and guards before sampling, then
atomically publishes the exact receipt and conservative floor. A successful
budget ACK is still not a return witness or a result authorization. A newly
observed expiry is published as a fact without renewing work or lease time.
If interrupted after owner retention, normal ACK recovery uses that exact
fact; if a process dies before fact handoff, its durable marker remains
unknown. The admitted `_capture_owned_return` path now uses a Context-owned
serialized observation, retains the original raw sample and input separately
from later ACK output, and closes or positively retires only unsampled owners.
It binds each owned boundary exclusively and allows only one outcome-capture
attempt; a failed serialization cannot recycle the old observation for a new
outcome. The current regression
`test_owned_return_samples_after_intervening_committed_floor` supersedes the
historical owned-path refusal test above; the ordinary scalar refusal tests
remain unchanged. A real activated thread Runtime result and delivery receipt
passed, but the final related suite retains an unresolved entry-error failure.
Ordinary Runtime without activation does not yet use this primitive. Its integration
must retain the actual outcome and immutable observation, safely handle
pre-sample failures and other live sampling owners, and establish the existing
admission, delivery and cleanup lifecycle before claiming end-to-end repair.

For a newly admitted execution, durable recovery needs an exact binding between
the full execution lease, the Kernel store, the runtime source, the journal
incarnation and canonical location, and a unique intent. An execution ID,
attempt and fence alone do not identify all of those facts.

The proposed admission protocol is:

1. Write an immutable journal intent containing the full binding and confirm
   its commit. A missing or uncertain journal confirmation does not authorize
   handler entry.
2. Register the same intent and journal binding in the Kernel under the exact
   current lease and fence; reconcile an ambiguous commit by reading the exact
   registration. Only after both records are confirmed may the handler enter.
3. An authorized Kernel completion atomically preserves its lease, decision,
   result and applicable budget. It does not imply that the journal has
   received the result or that runtime resources have been cleaned up.
4. Recovery discovers Kernel registrations first, opens the bound journal as an
   existing store, verifies the intent and exact Kernel authority, writes or
   exactly matches the corresponding immutable result receipt, and confirms
   its committed readback before recording delivery acknowledgement. Recovery
   never runs the handler again merely because a receipt is missing.

The receipt proof must preserve the original return-time budget separately
from the Kernel admission or decision budget. The existing ordinary journal
`record` and `settle` APIs can retain or change evidence independently of the
result, so their presence alone is not proof that those immutable fields match.
The new protocol needs exact bounded comparison and an immutable proof written
atomically with the compatible receipt; conflicting evidence is not overwritten.

The ordinary pending-record API must not be used for a pre-commit candidate.
Its existing recovery path can itself complete a running execution. A controlled
two-runtime probe wrote a candidate with that API and held the owner before its
completion call; the second runtime completed the execution and marked the
record delivered first. See `/tmp/sdk-journal-first-probe-9yryr0g5/probe.json`.
Any pre-commit candidate in this protocol must therefore be a distinct,
non-authorizing obligation: recovery can reconcile it against exact committed
Kernel authority, but cannot use it to transition a running execution. The
already-committed comparison in `/tmp/sdk-journal-first-probe-hhgf6mlw/probe.json`
is evidence for that single interleaving, not for crash recovery.

The current owned-thread path computes a return-time view but discards it before
the Kernel writes its later decision budget and clock. Existing authority rows
therefore cannot reconstruct the original view. A new versioned authority fact
must retain an SDK-captured immutable return observation, its original outcome,
the exact intent and lease, and the final decision together with the terminal
transition. The owning thread and its revocation checks must authenticate that
observation; a caller-supplied timestamp or budget is not sufficient. The later
decision clock stays separate. Unknown observations and legacy rows without
this evidence do not become successful through a later read.

The existing registration API alone also does not prove historical pre-entry
ordering: older v14 registrations lack an enforcement marker, and an upgraded
execution without entry metadata may predate that metadata. A future protocol
must establish registration ordering from durable provenance for each new claim,
not infer it from a missing row. Thread ownership cannot simply be transferred
to process mode: that mode needs a separately verified supervisor/worker
identity and handoff protocol before its return facts can authorize delivery.
An opt-in v15 claim now records a versioned admission marker and startup event
in the same Kernel transaction. Its entry gates require an exact committed
Kernel registration before handler entry, and each retry has its own marker.
Existing claims and v14 intents remain unbound. This foundation has focused
tests and an independent review, but the runtime does not yet opt in or verify
the journal half of the binding; it is not an end-to-end admission protocol.
The later v17 storage foundation can retain a return witness with a decision.
A subsequent private v2 capture samples before effect collection and JSON
serialization, but is not connected to Runtime. Its sample follows a
nonblocking reader reservation and is therefore the first observed boundary,
not proof of the physical return instant. For a v2 fact, the Kernel decision
and readback now check the original sample against every subsequently retained
constraint, even when bookkeeping crosses the work deadline. The original lease
must remain valid at the final in-transaction authorization check. This does
not guarantee that SQLite's physical COMMIT finishes before lease expiry.
Neither this foundation nor its tests establish runtime delivery.

A journal intent without a Kernel registration may be an interrupted
admission; it is not evidence of execution. A registered intent without an
authorized result remains pending or unknown. Cancellation and newer attempts
retain their actual Kernel winner; a stale intent cannot authorize completion.
Journal unavailability, a conflicting receipt, an ambiguous commit and
unconfirmed cleanup stay visible rather than being reported as success.

## Handler return boundary

The current thread wrapper samples completion before collecting effect IDs,
but does not publish the observation to its monitor before collection. A real
thread-mode regression gates that collection after the handler returned before
its deadline; the runtime ultimately records a timeout. See
`tests/test_runtime_handler_return_before_effect_collection.py`. A successful
repair must retain the actual outcome and use a trustworthy return observation
without charging subsequent SDK result collection to the handler. The test's
thread-mode result does not prove process or Windows behavior.

The private v2 capture uses a nonblocking reader reservation and samples before
serialization. Contention returns an unknown fact rather than taking a later
sample. Runtime integration still needs an exact worker-owned reservation and
publication protocol whose lifetime includes monitor handoff and worker exit.
Subsequent validation and retries must reuse the original observation. A capture failure
is an SDK completion-unknown fact and must not turn the handler's outcome into
an invented handler exception. Entry failure, exception, stop, cancellation,
close and a handler that never returns all need explicit ownership transitions.

File-backed capture now takes a bounded, participating SQLite writer reservation
after its original sample and makes its subsequent inspection query-only. This
orders it after any already active Kernel writer without changing stored data.
Writer contention or unavailable write access leaves the original time unknown;
recovery retains the same sample and deadline. The reservation does not prove
ordering for an unguarded external envelope or a pending entry sampled outside
the transaction.

The sample alone cannot order concurrent local budget changes or another
process's committed clock watermark. The final protocol must identify each
relevant writer and provide an audited ordering proof for the specific
observation. Evidence concurrent with sampling, a foreign or unresolved guard,
an incomparable clock domain, an uncertain commit or an unproven pre-return
watermark remains unknown. Later reads or acknowledgements cannot retroactively
establish when the handler returned. Stop and cancellation still compete under
the actual authority and lease rules; a factual return never overrides them.
The sample is the first SDK-observed boundary, not proof of a physical return
time before the worker was scheduled. Boundary ambiguity across a work deadline
must not be converted into success.

Holding a reader reservation while the handler is live changes cleanup
ownership. Stop or close cannot free it while an eventual capture can still
open or use storage; a bounded revocation/handoff must be proven first. Process
and Windows modes additionally require an authenticated worker-to-supervisor
handoff and deadline arbitration: a thread-owned capability cannot stand in for
process cleanup, an IPC acknowledgement or a confirmed child exit.

In the reproduced POSIX serialization case, the worker returned with about
1.37 seconds of trusted work budget remaining, but serializing its value was
deliberately held for three seconds. The inherited work and hard deadlines
were identical. The supervisor currently receives `worker_returned` only
after effect collection and serialization, then requires physical containment
before the hard deadline. Continuing the worker until the delayed value is
serialized would extend that original hard bound; a return marker alone cannot
recover the value after the worker is killed or establish its bytes. A process
repair therefore needs an authenticated, lease-bound return witness sampled
before collection and encoding, separate bounded transfer of the matching
result, and confirmed containment. If those are established in time, later
receipt bookkeeping must still use the original lease and verified witness.
If the value is not transferred before hard termination, the protocol must
preserve the actual uncertainty or timeout under the applicable contract; it
cannot manufacture the value. A thread-owned capability or a later timestamp is
not a process witness. The concrete observation is recorded in
`/tmp/sdk-real-process-return-6qpwma39/evidence.json`; no process fix follows
from this analysis alone.

## Lifetime and upgrades

Kernel and journal schemas require explicit, validated copy upgrades; old
records stay unbound and cannot acquire a delivery identity by guessing from a
new runtime configuration. Existing v4 journal and v5 split-receipt modes must
continue to operate. The new journal mode must also support the ordinary
record, settlement and lifecycle operations needed by the eventual runtime.

The current v7 copy does not establish which ordinary settlement rows came
from the original v4 journal. A controlled SQLite probe created an identical
lease/result row in v4 before copying and, separately, through the delivery
journal's internal legacy record method after copying an empty v4 journal;
the resulting rows were byte-identical and neither had an intent or proof
(`/tmp/sdk-v7-legacy-provenance-probe.log`). This demonstrates a schema
limitation, not a public activation API. Absence of a marker is not proof of
legacy provenance. A recovery feed that allows old completion behavior needs
positive, immutable copied-row provenance established under the original copy
exclusion and verified against the exact row and Kernel generation. Existing
v7 data without independently authenticated provenance must remain unknown;
it cannot be backfilled merely by classifying unlinked rows as old.

An explicit v4-to-v8 copy now records the copied ordinary rows in an immutable
manifest while the same host-verified exclusion covers the source and
destination. The v8 activation can inspect that original evidence alongside
the current matching lease and payload. Rows added after the copy and existing
v7 journals do not acquire this provenance. The reconciler requires an explicit
v7 or v8 selection and treats a version mismatch as unknown. This is only a
storage and reconciliation foundation: it is not authority to complete a
legacy obligation, does not provide legacy pending enumeration or ordinary
Runtime journal operations, and is not connected to Runtime.

An incarnation identifier alone does not detect restoration of an older copy
with the same identifier. Recovery must verify every retained Kernel
registration against the bound journal, including registrations previously
acknowledged as delivered: a restored journal may contain an intent while
missing its later receipt. A missing intent or conflicting evidence remains
unknown; a valid intent with an absent receipt may be reconciled only from the
exact retained Kernel authority. Registrations and decision evidence must not
be discarded while that recovery promise applies.

Journal replacement, relocation and restoration require the SDK's cooperating
storage maintenance and activation protocol. A missing bound journal must not
be recreated as if it were the original. Independently restoring both Kernel
and journal to a matching earlier state cannot be detected from those two
stores alone; a stronger external witness would be needed. In-memory and
non-full-durability stores cannot inherit a stronger power-loss guarantee than
their configured storage mode.

Recovery must use bounded reads, fair iteration and the original operation
deadline, preserve the original budget and authoritative decision, and retain
the owners of unconfirmed operations. A receipt or delivery acknowledgement is
not proof that a thread, process or external effect has been cleaned up.

## Outstanding verification

The storage foundations do not by themselves close the defect. Runtime entry,
recovery, migration and startup must be integrated and independently reviewed.
Verify real crashes around each cross-store boundary, lost acknowledgements,
changed journal configuration, restored copies, exact duplicate and conflicting
receipts, cancellation and stale fences, bounded/oversized records, and cleanup
remaining unknown after delivery. Finally rerun the late-COMMIT regression and
the applicable current-package acceptance cases; do not promote a synthetic
or earlier-candidate result to final acceptance.
