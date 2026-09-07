# Public API and compatibility

Import execution and orchestration APIs from `dispatcher_sdk.execution_kernel`
or `dispatcher_sdk.orchestrator`. Storage utilities live in
`dispatcher_sdk.storage`, durability helpers in `dispatcher_sdk.durability`, and
the optional OpenSandbox adapter in `dispatcher_sdk.adapters`. The package root
exports `runtime_identity` and its report types. Each public package defines its exported
names in `__all__`; underscore-prefixed modules are implementation details.

| Entry point | Use |
| --- | --- |
| `Kernel.open_sqlite` | Open SQLite persistence and a handler runtime |
| `Runtime`, `InProcessRuntime`, `SQLiteKernel`, `ExecutionKernel` | Runtime and persistence interfaces for integrations |
| `ExecutionCommandV2`, `ExecutionResultV2`, `ExecutionSnapshot`, `ExecutionLease`, `ExecutionError`, `RetryPolicy`, `EffectRecord`, `Event`, `ResultOutboxStatusV2` | Validated execution, effect, event and delivery records |
| `Handler`, `HandlerContext`, `HandlerEffects`, `registry_revision`, `handler_revision` | Implement and identify handlers and tracked effects |
| `RuntimeHost`, `RuntimeHostHealth`, `RuntimeHostError` | Run workers and transport with a background host and inspect its health |
| `ScriptSpec`, `script_handler`, `script_handlers` | Freeze inline scripts and register the process-only script handler |
| `Orchestrator` | Explicit Run/task operations, atomic `submit_task`, paged reads, historical revisions, linked continuation, receipts and delivery |
| `NotificationInbox`, `InboxLease`, `InboxRecord`, `InboxState` | Durable application acceptance and fenced transactional processing |
| `SandboxSpec`, `SandboxBackend`, `SandboxHandler`, `SandboxJournal`, `sandbox_handlers` | Frozen remote execution inputs, backend contract and persistent lifecycle recovery |
| `inspect_storage`, `backup_database`, `export_database` (storage module) | Read-only deployment preflight, SQLite backup and SQL export |
| `OrchestratorHost`, `OrchestratorHostHealth` | Drive execution, synchronization and notification callbacks in background threads |
| `canonical_json` | Compare strict JSON content without conflating boolean, integer and float values |
| `Operations` | Construct typed, detached operation dictionaries for `apply_operations` |
| `Operation`, the `*Operation` TypedDicts | Annotate explicit operations; plain dictionaries remain supported |
| `RunSnapshot`, `TaskSnapshot`, `AttemptSnapshot`, `WaitSnapshot`, `RunEvent`, `Observation` | Typed views of existing Run/event dictionaries |
| `RunState`, `TerminalRunState`, `AttemptState` | Literal state names for static checking |
| `RecoveryDetails` | Run/task identity plus authoritative execution and current effect from `inspect_recoveries(run_id)` |
| `runtime_identity`, `RuntimeIdentityReport` (package root or identity module) | Read-only package, source, storage and deployment compatibility observations |
| `ProjectionConsumer`, `ProjectionDrainReport`, `ProjectionEventIdentity` | Persist-before-ACK event projection with bounded retries and fixed high-water draining |
| `inspect_work_availability`, `WorkAvailabilityReport` | Read-only Run-scoped scheduling reasons; also available as an Orchestrator method |
| `inspect_cancellation`, `CancellationRecoveryReport`, `ExecutionCancellationReport`, `CancellationFact` | Read-only phase and generation evidence; also available as an Orchestrator method |
| `CancellationJournal`, `inspect_cancellation_journal`, `CancellationReceipt` (execution package) | Explicit, separate durable cancellation evidence component and its read-only reader |

See [diagnostics and projections](SDK_DIAGNOSTICS_AND_PROJECTIONS.md) for complete
signatures, failure semantics, evidence limits and runnable examples.

Kernel exception types, `SCHEMA_VERSION`, `EXECUTION_STATES`, `TERMINAL_STATES`,
`TRANSITION_MATRIX`, `can_transition` and `reduce_state` are also exported.
The Orchestrator exports `OrchestrationError`, `RevisionConflict` and
`CommandConflict`. See the [Kernel contract](../src/dispatcher_sdk/execution_kernel/README.md)
and [SDK guide](SDK.md) for lifecycle, conflict and recovery rules.

The wheel includes `py.typed`. The convenience interfaces work on Python 3.10+
without third-party runtime dependencies. TypedDict annotations do not validate
runtime data. Strict command and transaction checks still apply, and application
payloads and serialized Kernel records retain their existing JSON shape. Use
Kernel `ExecutionCommandV2.from_dict` / `ExecutionSnapshot.from_dict` to obtain
typed Kernel objects.

Strict Kernel records validate the SDK protocol and JSON representation, not an
application's nested payload or result schema. For example, accepting a result
record does not validate `candidates[].status` or the evidence behind a candidate.
Applications must define and version that contract, communicate exact field
constraints to their handlers and validate the received artifacts at runtime.
`TypedDict`, `Literal` annotations and an Agent's self-reported validation do not
enforce those constraints. See [LLM output contracts and bounded rework](SDK_OUTPUT_CONTRACTS.md)
for shared prompt/validator rules and repair guidance; these are application
patterns, not built-in SDK schema generation or automatic repair APIs.

## Version identities

The distribution version, execution schema version and handler contract version
are separate identities:

- Execution command/result contracts use `SCHEMA_VERSION = 2`. Unknown fields,
  invalid JSON values and conflicting identities are rejected.
- Kernel SQLite storage remains schema 2 with its `kernel_schema_meta` marker.
  Version 0.6 changes Orchestrator persistence to schema 2, using `sdk_*` tables.
  Older unversioned Orchestrator databases are incompatible and are not migrated
  automatically. Table layouts are implementation details, not a public SQL API.
- Commands bind `handler_id`, `handler_contract_version` and `registry_revision`.
  `Runtime.command()` freezes the selected handler using a `handler-v1:` revision;
  adding an unrelated handler does not change that binding. Legacy commands
  using the full runtime registry revision remain supported when the full
  deployment matches. Resume queued work with its original binding; never
  substitute a changed implementation under an accepted command identity.
- `ScriptSpec.command()` selects handler `sdk.script`, contract version 1,
  with one execution attempt. Its timeout is required. Register
  `script_handlers()` on the runtime that will execute it.

Changing handler bytecode, referenced globals or callable class data can change
its registry fingerprint. Opaque state requires an explicit, stable, nonempty
`__execution_kernel_revision__` deployment revision. Keep that revision tied to
the deployed implementation. The Kernel contract describes this binding.

The SDK has no general database migration facility. Private modules and table
layouts are not a compatibility contract across releases.
Preserve durable state and the matching deployment when restarting. See
[storage and upgrades](STORAGE_AND_UPGRADES.md) for read-only preflight, backups,
FULL/NORMAL durability profiles and the drain-to-new-store upgrade procedure.

## Platform and lifecycle behavior

Python 3.10+ is required. The core has no third-party runtime dependencies.
The optional `dispatcher-sdk[opensandbox]` extra installs `opensandbox==0.1.16`.
CI is configured for Linux and Windows on Python 3.10 through 3.13; configuration
is not evidence of a passing run on every version. Native validation passed on
Windows 11 x64, build 10.0.26100.9168, with official Python 3.12.10: the full suite
ran 324 tests in 153.814 seconds with 30 platform-specific skips. This includes
source-to-sdist-to-wheel packaging and the offline installed-package suite.
The native runtime module ran 17 tests in 26.529 seconds: 16 passed and only the
non-Windows refusal test skipped. Storage, Run and sandbox checks passed all
33 tests, including 11 sandbox Runtime tests using native process isolation.
Five installed examples passed; documentation link checks passed alongside
both README script examples, with two Linux-only examples skipped. These results
do not verify every supported Windows/Python combination. macOS is not in the CI
matrix. See [Windows runtime](WINDOWS_RUNTIME.md) for scope and reproduction.

`isolation_mode="auto"` selects process isolation on native Windows or when
POSIX fork is available, and thread isolation otherwise. Explicit process mode
fails on other unsupported platforms. Scripts require process isolation and
reject thread fallback.

Process mode needs a file-backed SQLite database, pickleable handlers and clocks,
and an executable entrypoint guarded by `if __name__ == "__main__":`.
On POSIX, the supervisor starts with `spawn` and forks inside its isolated
process. Linux additionally uses child-subreaper cleanup for detached descendants;
other POSIX hosts provide process-group cleanup. Native Windows uses a suspended
interpreter assigned to a Job Object before startup. See [Windows runtime](WINDOWS_RUNTIME.md)
for requirements and native validation, and [Linux cleanup validation](PROCESS_CLEANUP_VALIDATION.md)
for evidence and parent-fallback PID reuse limitations. Local process modes
contain trusted code; they are not OS security sandboxes. See [sandbox runtime](SANDBOX_RUNTIME.md)
and [backend contracts](SANDBOX_ADAPTERS.md) for separately deployed remote isolation.

Thread mode cannot forcibly stop a blocked handler. Timeout and cancellation
revoke its authority to publish results or effects, but cannot undo an external
call already in progress.

Constructing an Orchestrator starts no worker. Applications can drive
`flush`, runtime execution, `reap` and `sync` themselves, or explicitly start an
`OrchestratorHost`. The host does not choose business successors or finish Runs.
It owns runtime shutdown; the Orchestrator remains caller-owned. Notification
callbacks must return promptly after durable acceptance. Stop may raise
`TimeoutError` while an uninterruptible callback remains alive; keep its
dependencies available until shutdown completes.

`OrchestratorHost(sdk)` (or `callback=None`) starts execution and synchronization
without a notification delivery thread. Registered watches are still collected
durably; pending notifications remain unclaimed for a later callback consumer.
A no-op callback accepts deliveries and allows them to be acknowledged.
Lifecycle and runtime ownership are unchanged.

`inspect_recoveries(run_id)` is a read-only aggregation over registered, dispatched
current task attempts. It reads Kernel authority even if the Run has not been
synced, and returns one current recovery effect per execution. `attempt` is the
zero-based application attempt index; `execution.attempt` counts Kernel claims.
The query does not reap leases, sync state, resolve effects, or consume events.
Individual execution/effect pairs are checked with bounded revision re-reads;
continuous changes raise `RevisionConflict`. The collection is not an atomic
cross-store snapshot, and `run_revision` describes the initial Run read only.
After each resolution, query again for the next effect. Continue to pass the
effect revision and a stable recovery ID to `resolve_effect`.

Result and notification delivery are at least once. Deduplicate their immutable
identities durably. One SDK store owns a bound Kernel result queue; independent
SDK stores must not compete for the same queue. Notifications have a separate
outbox and do not acknowledge result messages. [NotificationInbox](NOTIFICATION_INBOX.md)
can commit application SQL with its consumed marker; it does not make external
network or file operations exactly once. See [task submission](TASK_SUBMISSION.md)
for atomic submission replay and [Run storage validation](RUN_STORAGE_VALIDATION.md)
for history growth and full-snapshot costs.
