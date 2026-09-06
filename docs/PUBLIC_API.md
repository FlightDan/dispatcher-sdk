# Public API and compatibility

Import from `dispatcher_sdk.execution_kernel` or
`dispatcher_sdk.orchestrator`. The package root has no convenience
re-exports. The two subpackages' `__all__` lists define their exported names;
underscore-prefixed modules are implementation details.

| Entry point | Use |
| --- | --- |
| `Kernel.open_sqlite` | Open SQLite persistence and a handler runtime |
| `Runtime`, `InProcessRuntime`, `SQLiteKernel`, `ExecutionKernel` | Runtime and persistence interfaces for integrations |
| `ExecutionCommandV2`, `ExecutionResultV2`, `ExecutionSnapshot`, `ExecutionLease`, `ExecutionError`, `RetryPolicy`, `EffectRecord`, `Event`, `ResultOutboxStatusV2` | Validated execution, effect, event and delivery records |
| `Handler`, `HandlerContext`, `HandlerEffects`, `registry_revision` | Implement and identify handlers and tracked effects |
| `RuntimeHost`, `RuntimeHostHealth`, `RuntimeHostError` | Run workers and transport with a background host and inspect its health |
| `ScriptSpec`, `script_handler`, `script_handlers` | Freeze inline scripts and register the process-only script handler |
| `Orchestrator` | Explicit Run/task operations, observations, receipts, command/result delivery and notifications |
| `OrchestratorHost`, `OrchestratorHostHealth` | Drive execution, synchronization and notification callbacks in background threads |
| `canonical_json` | Compare strict JSON content without conflating boolean, integer and float values |

Kernel exception types, `SCHEMA_VERSION`, `EXECUTION_STATES`, `TERMINAL_STATES`,
`TRANSITION_MATRIX`, `can_transition` and `reduce_state` are also exported.
The Orchestrator exports `OrchestrationError`, `RevisionConflict` and
`CommandConflict`. See the [Kernel contract](../src/dispatcher_sdk/execution_kernel/README.md)
and [SDK guide](SDK.md) for lifecycle, conflict and recovery rules.

## Version identities

The distribution version, execution schema version and handler contract version
are separate identities:

- Execution command/result contracts use `SCHEMA_VERSION = 2`. Unknown fields,
  invalid JSON values and conflicting identities are rejected.
- Kernel SQLite storage requires the exact v2 schema and
  `kernel_schema_meta` marker. Opening a store does not implicitly migrate an
  incompatible Kernel schema. Orchestrator persistence uses `sdk_*` tables;
  these tables are implementation details, not a public SQL API.
- Commands bind `handler_id`, `handler_contract_version` and
  `registry_revision`. Use the runtime's registry revision when constructing
  commands. Redeploy the matching handler implementation to resume queued work.
  Do not substitute a changed implementation under an accepted command identity.
- `ScriptSpec.command()` selects handler `sdk.script`, contract version 1,
  with one execution attempt. Its timeout is required. Register
  `script_handlers()` on the runtime that will execute it.

Changing handler bytecode, referenced globals or callable class data can change
its registry fingerprint. Opaque state requires an explicit, stable, nonempty
`__execution_kernel_revision__` deployment revision. Keep that revision tied to
the deployed implementation. The Kernel contract describes this binding.

The SDK has no general database migration facility. Private modules and table
layouts are not a compatibility contract across releases.
Preserve durable state and the matching deployment when restarting; review
release changes before upgrading a running installation.

## Platform and lifecycle behavior

Python 3.10+ is required. Runtime code uses only the standard library.
`isolation_mode="auto"` selects process isolation when POSIX fork is available,
and thread isolation otherwise. Explicit process mode fails when fork is
unavailable. Scripts require process isolation and reject thread fallback.

Process mode needs a file-backed SQLite database, pickleable handlers and clocks,
and an executable entrypoint guarded by `if __name__ == "__main__":`.
The supervisor starts with `spawn` and forks only inside its isolated process.
Linux additionally uses child-subreaper cleanup for detached descendants; other
POSIX hosts provide process-group cleanup. These are containment mechanisms for
trusted code, not an OS security sandbox.

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

Result and notification delivery are at least once. Deduplicate their immutable
identities durably. One SDK store owns a bound Kernel result queue; independent
SDK stores must not compete for the same queue. Notifications have a separate
outbox and do not acknowledge result messages.
