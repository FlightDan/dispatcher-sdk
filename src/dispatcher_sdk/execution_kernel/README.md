# Execution Kernel v2

Install the `dispatcher-sdk` distribution and import this package as
`dispatcher_sdk.execution_kernel`. The SDK package root is lightweight;
importing the Kernel does not load the Orchestrator or host application.

The package provides a standalone execution boundary using only the standard
library. Its contracts are exact JSON schema version 2 records; callers must treat unknown
fields, non-finite values, stale leases, and result identity conflicts as hard
failures.

## Storage and delivery assumptions

- `Kernel.open_sqlite(path, handlers)` opens the complete local stack. A restart
  with the same handler implementation fingerprint resumes durable queued work.
- Application-owned tables may coexist in the SQLite file. Kernel connections
  are authorizer-limited to `kernel_*` and SQLite internals and cannot read or
  write application tables. Partial or altered Kernel schemas and anything except
  the exact `kernel_schema_meta` v2 marker are rejected; the Kernel performs
  no implicit schema migration.
- File-backed writers default to WAL and `synchronous=FULL`. The explicit
  `durability="normal"` profile selects NORMAL on each writer connection.
- State changes use revision compare-and-swap updates. Terminal execution facts,
  execution/effect events, and result identity are immutable. The separately
  fenced result outbox delivers results at least once.
- Lease timestamps use one comparable, non-decreasing clock domain. A handler
  contract version is bound within a registry revision; changing handler
  bytecode, referenced global state, or callable class data changes the
  derived registry revision. Opaque globals and callable class behavior fail
  closed unless the handler exposes a stable non-empty
  `__execution_kernel_revision__` deployment revision.
- Process isolation requires a file-backed SQLite path; `:memory:` is rejected
  because a child would otherwise open a separate database. On POSIX the
  supervisor is started with Python's safe `spawn` context, so handlers and a
  custom clock must be pickleable and executable entrypoints must use the
  standard `if __name__ == "__main__"` guard. The supervisor then forks only
  after it is isolated and single-threaded. The supervisor uses its own timer and kills the handler process group on timeout,
  cancel, and runtime close. On Linux it is also a child subreaper, so
  new-session and double-fork descendants are adopted, killed, and reaped
  before success is published. Other POSIX hosts guarantee process-group
  cleanup only; callers needing detached-descendant containment must use a
  host sandbox with an equivalent process-tree primitive.
- Native Windows uses `CreateProcessW` with a Job-list attribute and suspended
  startup, placing the interpreter in a kill-on-close Job before importing user
  code. A host watchdog thread enforces deadlines; cleanup confirms zero active
  Job processes before success. Importable, pickleable handlers and guarded
  entrypoints are required. See the source checkout's
  [Windows guide](../../../docs/WINDOWS_RUNTIME.md) for validation status and limits.
- Runtime lifecycle transitions share one finalization lock: active
  `cancel()` and handler completion compete atomically, and only one can succeed.
  A completion cannot validate a running lease, lose a cancellation race, and then attempt
  to overwrite the cancelled terminal state.
- `SQLiteKernel.cancel_before_accept(command, reason=...)` atomically records
  an unseen command as cancelled, with the normal result, events and outbox.
  Workers never observe an intermediate queued execution. An already accepted
  exact command is returned unchanged; its runtime must perform cancellation
  and process cleanup using the returned revision. Conflicting execution or
  idempotency identities are rejected.
- Process isolation is an execution-containment boundary for trusted handler
  implementations, not a hostile-code security sandbox. A same-UID handler can
  inspect file descriptors, signal peer processes, and access host resources.
  Untrusted handlers require a separate OS identity/container plus cgroup or
  equivalent process and resource isolation outside this package.
- Thread isolation uses a bounded long-lived executor. Timeout, cancel, and
  `close()` revoke cooperative result/effect authority and wake the runtime
  caller, but Python cannot kill an uncooperative thread or undo a raw side
  effect already in progress. Use process isolation when hard termination is a
  requirement.

Use `runtime.command(...)` for per-handler implementation binding. Adding an
unrelated handler preserves these commands' bindings; changing their selected
handler does not. Manually using `runtime.registry_revision` retains strict
whole-registry matching for historical commands. Storage/deployment preflight,
backup and export are available from `dispatcher_sdk.storage`.

`SandboxHandler` adapts a public `SandboxBackend` into this same effect and
recovery model. The optional `dispatcher_sdk.adapters.OpenSandboxBackend`
imports its pinned provider SDK lazily; installing the core adds no dependencies.
The [sandbox Runtime guide](../../../docs/SANDBOX_RUNTIME.md) explains durable
identities, output collection, disposal and uncertain-operation recovery.

## Lease expiry and retry budgets

`RetryPolicy.max_attempts` includes the first claim and defaults to 1. Ordinary
lease-expiry redelivery and retryable execution failures share this limit;
`redelivery_count` records scheduled redeliveries after lease expiry or retryable
failure but grants no independent budget.
An ordinary expired first attempt with `max_attempts=1` becomes terminal `dead`
with `lease_retry_exhausted`. Waiting for a live lease or retry backoff consumes
no further attempt. Business rework is a separate application decision.

The runtime's configured lease duration is a floor: `claim_and_start` also
allows for command timeout and startup safety. Read `snapshot.lease.expires_at`
and `snapshot.next_attempt_at` instead of assuming a fixed recovery delay.
`runtime.reap()` explicitly processes expired execution leases; claim paths
also reap. SDK `sync()` only observes facts. An empty `run_once()` return does
not establish that a workflow is stalled or complete.

## Effect recovery

An effect is prepared under a live execution lease and claimed as `performing`
before external work. An unfinished prepared/performing record encountered under
a newer fence becomes `indeterminate`; it is never automatically replayed.
Lease reaping also converts unfinished effects to
indeterminate and parks immediately, even when the mechanical retry budget is
already exhausted. Waiting in recovery consumes no execution attempts; the
host must still observe and expose this persistent state. The
runtime parks the execution in `recovery_required`, without a terminal result
or outbox entry.

An operator resolves that effect with `resolve_effect(..., decision="applied")`
and the known response, or with `decision="not_applied"` and a null response.
With multiple indeterminate effects, each must be resolved. After the last
decision, a normal recovery target returns to `queued` in the same transaction;
a persisted cancellation target instead settles as `cancelled` and never reruns.
`applied` is reused as committed; `not_applied` permits preparation
and execution only under the next lease/fence. That explicit continuation may
claim one attempt beyond the mechanical retry limit; any later retryable failure
or lease expiry exhausts normally. Both execution and effect event streams
retain the decision and recovery identity.

Handlers must wrap the actual external mutation with
`HandlerContext.effects.execute_once` and stable effect identity/request.
Arbitrary filesystem edits or Git commits bypassing this interface are not
automatically tracked, rolled back or made idempotent. A crash after mutation
but before effect commit requires reconciliation; missing output does not prove
the mutation did not occur, and partial effects also require reconciliation.

If the effect response is committed but the execution result is not, an allowed
mechanical retry can reuse that response. Exhausted attempts can still become
`dead`; committed effects alone do not grant another attempt or prove business
success. Once an execution result is durable, replay its result delivery instead
of rerunning the handler. See the [application integration guide](../../../docs/SDK_RECOVERY.md)
in the source checkout for evidence and repository recovery requirements.

POSIX process runtimes use a separate supervisor for timeout and lifecycle
isolation. The explicit thread fallback revokes result/effect publication, but
Python cannot stop an external call that was already executing when timeout or
cancellation occurred. Its durable prepared fact remains visible; retrying
under a newer fence invokes the same indeterminate recovery path.
