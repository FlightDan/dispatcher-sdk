# Integration engineering principles

[English](Engineering-Principles.md) | [简体中文](Engineering-Principles-zh-CN.md) | [Home](Home.md)

These principles make durable SDK integrations easier to operate and review.
They describe application discipline; the SDK still owns execution, storage,
leases and delivery, while the application owns business meaning and product
acceptance. The [full guide](../docs/INTEGRATION_PRINCIPLES.md) contains the
definitions and checklists.

| Principle | Practice |
| --- | --- |
| Version vector | Record release, imported module, contract and storage schemas, registry and deployment identity separately. |
| Supervised lifetime | Track owner, heartbeat, queue progress and stop result; a PID is not service health. |
| Review identity | Report structural reuse, independent review, current-Run validation and publication approval separately. |
| Evidence closure | A new source or log is evidence, not an automatically closed question. Define closure criteria and reassess. |
| Knowledge versus verification | Block affected work only for knowledge needed now; carry post-implementation checks to their declared gate. |
| Causal diagnosis | Compare exact execution identity, first fatal condition, lifecycle milestone and authenticated coverage. |
| Evidence ladder | Name whether evidence is fixture, SDK integration, restart, model, build, runtime or product acceptance. |
| Frozen candidate | Freeze code, dependencies, registry and rules before final review and full verification. |
| Safe discovery | Locate and match durable objects before mutation; ambiguity must not create a new lineage. |

## Before starting work

Write down the question, the acceptance criteria, the identity of the candidate
and the evidence level that will answer it. Keep a matching deployment available
for active durable work. Read [storage and upgrades](../docs/STORAGE_AND_UPGRADES.md)
before reusing a database and [recovery](../docs/SDK_RECOVERY.md) before retrying
an interrupted effect.

## Before reporting success

Preserve the first failure and the raw evidence that explains it. State skipped
tests and unverified capabilities. Re-run the final checks if the candidate,
dependency, generated artifact or acceptance rule changed. A green test count,
stable hash or Agent self-report is only as strong as the evidence level and
authority behind it.

For coding-agent workflows, use the [verification checklist](../DocsforAgents/VERIFICATION.md).
