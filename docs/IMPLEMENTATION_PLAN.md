# Reliability and sandbox implementation plan

Status: implementation verified on 2026-09-07; version 0.6.0 is prepared for delivery.
Approved implementation scope: 2026-09-07.

## Goal and boundaries

Build a core with no third-party runtime dependencies and keep active
orchestration work bounded. Define storage and deployment compatibility, apply
one durability policy to all writers, contain native Windows scripts, and make
notification intake reliable. Provide a public sandbox interface and an
OpenSandbox adapter. Preserve the existing working-tree changes.

The user approved segmented Run continuation with complete history, a documented
breaking storage/API baseline where necessary, WAL + FULL by default with
explicit NORMAL opt-in, and synchronization of the notified attempt before
publishing its notice.
They explicitly requested real OpenSandbox validation and evidence that cheaper
process cleanup still handles descendants, cancellation, and exit races.

The implementation scope excludes releases, deployment, deletion of old
databases, and general migration from the legacy namespace. It makes no
exactly-once promise for arbitrary external effects or unverified claims about
platform support and security. A local process backend manages trusted code;
the configured sandbox provider supplies its declared security isolation.

## Ordered work and acceptance criteria

### 1. Validate execution boundaries before choosing implementations

- [x] OpenSandbox: pin the evaluated upstream revision/version; run an isolated
  real service if the environment supports it. Verify create, background command,
  stable identity, reconnect, status/log/artifact retrieval, cancellation of
  descendants, and disposal. Record response-loss and retention limitations.
- [x] Process cleanup: compare the existing 50 ms quiet window with a kernel-backed
  completion proof where available. Test fork/double-fork/setsid, continued child
  creation, cancellation/success races, supervisor exit, and unrelated processes.
  Keep the conservative fallback on platforms without the proof.
- [x] Record reproducible before/after measurements with equivalent settings.
  Lower average latency must not come at the cost of weaker cleanup guarantees.

### 2. Unify persistence and compatibility

- [x] Configure and verify WAL and synchronous on every SDK-owned writer, including
  handler subprocess connections. Default `durability='full'`, allow `'normal'`.
- [x] Use explicit orchestration schema/version metadata; reject unsupported old
  layouts without deleting or silently rewriting their contents.
- [x] Provide read-only upgrade/deployment preflight and safe backup/export entry
  points. Preserve strict execution identity, effect/fence and schema validation.
- [x] Add per-handler implementation binding for new commands, so adding an
  unrelated handler does not strand those commands; preserve exact historical
  binding for legacy full-registry commands. Changed implementations must not
  execute previously accepted work under a false identity.

### 3. Bound active Run work while preserving history

- [x] Store task/attempt changes independently. Each command receipt must retain
  an immutable historical state reference without duplicating the complete Run.
- [x] Register only newly created attempts; sync active/unsettled executions and
  avoid repeatedly loading completed historical Runs for each old execution.
- [x] Provide summary/paged history reads and explicit segmented continuation.
  Old segments remain queryable, their identities and event cursors remain valid,
  and unsettled effects/deliveries remain recoverable.
- [x] Demonstrate near-linear retained storage for a fixed-size incremental task
  fixture, stable command replay, and no old-terminal scan on an idle sync cycle.

### 4. Make notifications reliable and convenient to consume

- [x] Synchronize the corresponding attempt before notification publication;
  cover a worker finishing between sync and collection, older attempts, and rapid
  recovery-to-terminal transitions without regressing newer state.
- [x] Supply a persistent inbox with source-scoped deduplication, payload conflict
  detection, leases/fences, acknowledgement and retry. Document the transaction
  boundary and preserve at-least-once processing for arbitrary external effects.
- [x] Extend the existing convenience layer with stable caller request identities,
  runtime ownership and straightforward result/notification access. Keep business
  acceptance and routing explicit.

### 5. Add portable execution and an adapter extension surface

- [x] Implement native Windows script/worker containment with Job Objects, controlled
  launch and confirmed cleanup. Add native CI coverage for descendants, cancellation,
  deadline and host-exit races. A Linux test or mock is not Windows acceptance.
- [x] Define a small public sandbox protocol and serializable identities/statuses;
  preserve uncertain launch/cancellation outcomes across SDK restart.
- [x] Ship the OpenSandbox adapter in the project with lazy optional dependencies.
  Provide adapter registration and reusable conformance tests; community providers
  must not depend on private Kernel internals.
- [x] Collect/persist required results before disposal. Unsupported required
  policies must fail explicitly. Canceling a local request is not remote cleanup.

### 6. Integrate, review, verify and document

- [x] Independently review persistence, recovery, concurrency and public interfaces.
- [x] Fix actionable findings and run appropriate regression, packaging, typing and
  documentation checks. Re-run performance fixtures after relevant changes.
- [x] Update compatibility notes, examples, platform matrix and dependency claims.
- [x] Record real external/native-platform validation separately from simulated
  contract tests. If the environment cannot run a required check, leave that
  acceptance item explicitly open and complete all independent implementation.

## Work ownership

The primary agent owns public contracts, orchestration/storage integration,
versioning, final review and verification. Parallel work covered OpenSandbox
validation, the process cleanup proof and implementation, and shared durability
code. Platform and adapter work received independent review.

## Progress evidence

The pre-change investigation is available in the task's research report and
temporary reproducible probes. The baselines include approximately 237 MB
of command-receipt JSON for the 800-small-task fixture and Linux empty-task median
`run_once` latency of 2.6 ms (thread) / 271 ms (process). Those timing results came
from a shared environment and are not throughput or cross-platform guarantees.

The following records and focused validation documents contain the findings,
commands, results and acceptance limits.

### Evidence recorded on 2026-09-07

- [OpenSandbox validation](OPENSANDBOX_VALIDATION.md): official SDK 0.1.16,
  server 0.2.3 and execd v1.0.22 ran against a disposable isolated Docker daemon.
  Real create/start response loss, reconnection, output collection and disposal
  passed. The additional `scripts/verify_sandbox_runtime.py --live` probe passed
  Runtime success/artifact persistence, timeout, detached descendants,
  cancellation with disposal before return, and close.
- [Process cleanup](PROCESS_CLEANUP_VALIDATION.md): 30-sample cleanup medians
  fell from 52.92/55.77 ms to 3.65/3.39 ms for worker-only/double-fork fixtures.
  The repeated real race fixture covered 160 topology/delay combinations;
  separate non-SIGCHLD clone tests exercised the `__WALL` completion requirement.
  These measurements exclude process startup and database work. The parent
  fallback retains its documented limits.
- [Run storage](RUN_STORAGE_VALIDATION.md): 100/200/400/800 tasks retained
  0.63/1.02/1.81/3.32 MB databases. The 800-task receipt JSON was 24.7 KB;
  per-task retained JSON stayed within approximately 0.07% across those sizes.
  Old receipt replay and historical reconstruction passed; five idle syncs over
  40 completed real executions made no Kernel snapshot or full-Run loads.
- Notification regressions cover completion after an earlier host sync, old
  watches alongside new application attempts, and rapid recovery-to-terminal
  transitions. Inbox tests cover crash/restart, duplicate/conflicting payloads,
  stale fences, SQL transaction rollback and damaged schema rejection.
- Independent reviews covered normalized persistence, inbox fencing/schema,
  Windows launch/handle lifetime, sandbox recovery/configuration/generations,
  and public consumer typing. Actionable findings were fixed before final checks.
- Source/sdist/wheel isolation passed. An offline-installed 0.6.0 wheel passed
  public consumer mypy checks, 4 README examples, all local documentation links,
  and all 5 standalone examples. Final source discovery is recorded below.

### Final acceptance

| Environment/check | Result |
| --- | --- |
| Linux, Python 3.12.3, final complete discovery | 324 tests in 429.890 s; passed, 14 Windows-specific skips |
| Windows 11 x64 build 10.0.26100.9168, Python 3.12.10, complete discovery | 324 tests in 153.814 s; passed, 30 platform-specific skips |
| Native Windows runtime module | 17 tests in 26.529 s; 16 passed, non-Windows refusal test skipped |
| Native Windows storage, Run history and sandbox recovery | 33 passed, including 11 sandbox Runtime process-isolation cases |
| Packaging | Both platforms rebuilt source/sdist/wheel and ran isolated installed-package consumers |
| Public typing | Installed 0.6.0 wheel consumer passed mypy with Python 3.10 compatibility settings |
| Examples | All 5 standalone examples passed on Linux and Windows; README examples passed where applicable |
| Remote sandbox | Real OpenSandbox adapter and Runtime probes passed; dedicated service/daemon/resources cleaned |

Native verification fixed test fixture imports, atomic PID publication and
SQLite connection closure, plus the Windows writable-handle requirement for
backup/export flushing. Direct native cleanup tests assert absence immediately
after return; abrupt host death uses a separate bounded operating-system cleanup
observation. The final Windows audit found no remaining Python processes from
the task's dedicated installation.

The README files, API/platform guides, changelog, focused validation records and
this plan record the verified outcome. The CI matrix includes additional Python
versions; only executed checks are reported as passing.
The documented non-Linux POSIX containment, trusted-handler, external-effect
reconciliation and cross-database snapshot limits remain part of the contract.
The candidate is version 0.6.0, unreleased; no old database was migrated/deleted
and no release was published.

## Requested delivery

After implementation verification, the user requested that the implementation,
bilingual Wiki and other documentation be combined as version 0.6.0 and pushed
and merged into the main branch. The linked Wiki task also supplies the English
`DocsforAgents/` guides and a local Wiki exporter.

All 36 other Markdown documents received a Humanizer review before delivery.
The four `DocsforAgents/` files were excluded and remain byte-identical.
Cross-review found no changes to API contracts, validation results or limitations;
automated checks confirmed that code blocks and link targets were preserved.
