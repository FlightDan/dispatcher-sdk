# Diagnostics and projections

[中文](Diagnostics-and-Projections-zh-CN.md)

Use these APIs to inspect the deployment, consume events, and investigate work availability or cancellation:

| Capability | Entry point |
| --- | --- |
| Imported package, source and storage compatibility | `dispatcher_sdk.runtime_identity(...)` |
| Persist-before-ACK event consumption | `ProjectionConsumer(...).drain(...)` |
| Why a Run has no currently claimable work | `sdk.inspect_work_availability(run_id)` |
| Cancellation phases, cleanup and recovery identities | `sdk.inspect_cancellation(run_id)` |

Projection callbacks must commit idempotent destination writes before returning
`persisted` or `already_present`. A failed page replays, poison events are not
skipped, and a fixed high-water target does not guarantee an ACK window during
continuous concurrent updates.

Diagnostic queries do not synchronize or mutate the Run. They distinguish
missing evidence from confirmed facts and report cross-store snapshot limitations.
Work diagnostics bound their Effect scan; an exceeded budget yields an unknown
count, not zero.

Runtime cancellation evidence can be persisted with explicit
`cancellation_journal_path` and `source_id` options. Receipts use a separate SQLite
database with schema version 1. Core stores are not automatically migrated. Local process cleanup requires
the matching execution generation's Linux subreaper or Windows Job proof.
Stopping a Task does not finish its Run.

See the [API guide](../docs/SDK_DIAGNOSTICS_AND_PROJECTIONS.md),
[journal design](../docs/CANCELLATION_EVIDENCE.md),
[projection example](../examples/projection_consumer.py) and
[diagnostic example](../examples/capability_diagnostics.py).
