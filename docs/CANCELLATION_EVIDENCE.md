# Cancellation evidence and recovery reports

Cancellation is a sequence of facts: an intent can be committed before delivery,
execution authority can be revoked before process cleanup finishes, and an
external effect can remain unknown after a local process exits. The report records these facts separately and identifies the exact execution
generation.

## Storage design

The optional Runtime cancellation journal uses a separate SQLite file that the
caller explicitly configures. Current Kernel storage uses schema 5 and
Orchestrator storage uses schema 4; existing sandbox storage uses schema 1.
Enabling cancellation evidence creates
a separate schema-1 journal without migrating an existing active
database. Existing SDK APIs keep their default behavior.

Journal schema 1 stores immutable cancellation requests and immutable phase
receipts. A journal binds to the caller's stable `source_id` and the resolved
Kernel path. Each request also binds to a canonical command digest, execution
ID, Kernel attempt/fence, expected revision and a unique receipt ID. Repeated
cancellation calls can have separate requests; a receipt never authorizes an
execution or replaces revision/fence checks.

- Creating a journal requires an explicit path distinct from the Kernel file.
  Existing partial, foreign or unsupported journals are rejected without repair.
- Phase receipts are appended only after the corresponding fact is observed.
  Missing receipts remain unknown. Kernel cancellation, process termination,
  provider calls and journal writes cannot be one atomic transaction.
- When the Kernel cancellation operation raises, Runtime preserves that exact
  exception and captures bounded local facts without another synchronous
  diagnostic write. `observe` exposes them as `local_cancellation_diagnostics`,
  separately from durable phase receipts. They have no authority and do not
  survive Runtime restart. A request receipt, if already persisted, remains
  durable; absent failure receipts do not prove that the control operation made
  no commit. The caller must inspect canonical authority before a new action.
- Optional cancellation diagnostics share the remaining control allowance. If
  neither diagnostic store saves a phase, the same bounded local buffer retains
  its original capture time and marks it unpersisted, even when cancellation
  succeeds. This does not replace an explicitly configured cancellation journal.
- Failure to record evidence after cancellation cannot prevent process cleanup.
  The Runtime attempts cleanup and reports the evidence-write failure; callers
  must re-read authority before retrying. Failure to persist the initial request
  stops the journal-enabled operation before Kernel cancellation.
- Receipt identity includes the original fence. Old-generation cleanup evidence
  cannot establish cleanup for a newly claimed execution.
- Cancellation reports can supplement cancellation receipts with a read-only
  `process_cleanup` settlement note from the Kernel-bound Runtime journal. This
  works after Runtime restart and without an attached Runtime. The report accepts
  only a note bound to the same Kernel store and matching execution ID, attempt
  and fence, with state `confirmed` and source `runtime_supervisor_reaped`. It
  exposes the settlement note ID and source separately from cancellation receipt
  IDs. Missing, malformed or foreign notes remain unknown; this evidence does
  not resolve pending sandbox disposal or external effects.
- Journal readers use a read-only connection and do not initialize a file,
  synchronize the Run, reap leases, or contact providers.

The journal has no upgrade or conversion operation. Schema 1 is accepted
as-is or rejected. A future schema requires a separate version and conversion
design. New evidence is available only for calls made with the journal enabled;
existing records are not backfilled. A pre-increment SDK can continue using its
unchanged core databases, but it does not produce or consume cancellation phase
receipts. Do not describe its new cancellations as covered by the journal.

## Backup and restoration

Preserve the journal alongside the Kernel, Orchestrator and registered sandbox
journals. Stop all relevant writers for a coordinated backup set; individual
SQLite backups are not an atomic multi-file snapshot. Restore the original
source identity and Kernel path with that set. A journal/path mismatch is an
error. Restore the matching path rather than rewriting the binding. Independent forks require a
different source namespace and a newly configured journal. No automatic history
merge, rebinding or in-place downgrade is provided.

## Evidence boundaries

An explicit Linux subreaper containment receipt or Windows Job zero-active-process
proof supports local process-tree cleanup for that invocation. A dead supervisor
alone does not prove that orphaned workers are gone. Other POSIX backends retain
their process-group cleanup behavior, but the full-tree fact remains unknown.
An absent PID or a restarted Runtime with no supervisor is not evidence either.
A matching local thread invocation establishes that process-tree cleanup is not
applicable; it does not prove that a blocked Python call has terminated. The
cancelling Runtime's isolation configuration alone does not identify the actual
execution backend.

Sandbox outcome and disposal evidence come from the bound lifecycle journal;
unknown create responses stay unknown until resolved with provider evidence.
Known execution results can coexist with pending or failed disposal. Outcomes
for arbitrary external actions not recorded through Effects are outside the
report's coverage. Cancelling one Task does not cancel its Run or its siblings.

See [API usage](SDK_DIAGNOSTICS_AND_PROJECTIONS.md) and the
[scenario tests](../tests/test_cancellation_report.py). This design does not
authorize publishing a release or migrating existing deployment stores.
