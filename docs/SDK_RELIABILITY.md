# Shutdown reports, inspection cost and execution origins

These additive APIs preserve existing writer validation and storage formats.
The [repair plan](SDK_RELIABILITY_REPAIR_PLAN.md) records scope; caller receipts
are described separately in [request result receipts](REQUEST_RESULT_RECEIPTS.md).
The [combined runnable example](../examples/reliability_diagnostics.py) exercises
all four additions using temporary stores.

## Shutdown diagnostics

```python
from dispatcher_sdk.orchestrator import OrchestratorHostTimeoutError

try:
    host.stop(timeout=5)
except OrchestratorHostTimeoutError as error:
    report = error.report.to_dict()  # Snapshot taken when the call timed out.
    print(report["unfinished_phases"])
    print(report["can_continue_waiting"])
```

`OrchestratorHost.stop()` still returns `True` on success and raises a
`TimeoutError` on timeout; `OrchestratorHostTimeoutError` is its subclass.
`RuntimeHost.stop()` still returns `False` on timeout. Cleanup errors retain
their existing exceptions/causes. Both hosts expose `stop_report`, initially
`None`, and a live `StopReport` snapshot during or after shutdown. Read that
property after a cleanup exception or to observe further progress after timeout.

`StopReport` and `StopPhase` expose `to_dict()`. Phases are `worker_drain`,
`executor_shutdown`, `final_pump`, `runtime_close`, and, for the orchestrator,
`notification_join`. Each distinguishes not started, in progress, completed,
skipped or failed, with monotonic timestamps, elapsed time and observed errors.
The report's `errors` retains recent runtime error sources, including a coordinator
failure even when all resources subsequently close. A successful resource stop
does not erase a prior failure. The orchestrator's last timeout status remains
visible until a successful retry; phase/thread observations can still advance.
Monotonic timestamps are local to this process, not portable wall-clock evidence.
Worker counts describe futures still tracked by the host, including completed
calls awaiting collection, not an enumeration of execution IDs.

`can_continue_waiting` means unfinished host threads are still observable; it
does not guarantee that they will finish. Keep runtime/callback dependencies
available and call `stop` again after resolving a blocker. Python cannot forcibly
terminate arbitrary synchronous callbacks or resource methods. Join waits share
one monotonic budget; a blocking third-party call or synchronous close can exceed
it. This API adds diagnosis, not a universal hard cancellation deadline.

`pending_delivery_count` and `pending_delivery_persisted` are currently `None`
because shutdown reporting does not scan or wait for application storage.
They must not be treated as zero or successful persistence. The report concerns
host lifecycle, not checkpoint contents, Run completion or business acceptance.
Read the appropriate public Run/result APIs separately when those facts are needed.

## Explicit inspection cost

```python
from dispatcher_sdk import runtime_identity
from dispatcher_sdk.storage import inspect_storage, inspect_storage_usage

module = runtime_identity()  # Imported source identity, no database supplied.
schema = runtime_identity("state.db", check="schema", timeout_seconds=2)
bindings = inspect_storage("state.db", handlers=handlers, check="bindings",
                           timeout_seconds=5, progress=print)
integrity = inspect_storage("state.db", check="full", timeout_seconds=30)
files = inspect_storage_usage("state.db", detail="files")
```

| Selection | Work and evidence |
| --- | --- |
| `runtime_identity()` without paths | Module/source and optional handler identity; no storage verdict |
| `check="schema"` | Catalog, schema and small metadata validation; no integrity, historical execution counts or command traversal |
| `check="bindings"` | Schema and applicable command/deployment bindings; can scan command records and registered journals |
| `check="full"` (existing default) | Existing integrity (`quick_check`), schema, counts and applicable binding checks |
| Usage `detail="files"` | File/sidecar sizes only; no SQLite page attribution or payload scan |
| Usage `detail="physical"` (existing default) | Page/allocation attribution, including potentially large `dbstat` scans |
| Usage `detail="logical"` | Physical work plus payload-length scans bounded by `scan_limit` |

An omitted integrity check is `not_checked`, never `ok`. Reports identify actual
scope, elapsed time, completeness and a stopping reason. Partial preflight
evidence does not yield an affirmative overall `compatible` value. Capability
verdicts remain scoped to the evidence gathered, not a permission to bypass writer
schema, handler binding, revision or fence checks.

`timeout_seconds` budgets SQLite and cooperative inspection work. Progress reports
describe phase and elapsed time; they do not invent a percentage of an unknown
scan. A budget interruption returns incomplete/unknown evidence rather than
declaring corruption. Progress callbacks must be fast and synchronous; arbitrary
filesystem I/O and callback code do not have a hard interruption guarantee.
Multiple component files are independent snapshots, not an atomic store group.

## Bounded execution origin lookup

```python
from dispatcher_sdk.orchestrator import inspect_execution_origin

origin = inspect_execution_origin(
    "state.db", result_id="result-42",
    max_payload_bytes=1024 * 1024, max_query_steps=100_000, timeout=5,
)
print(origin.to_dict())
```

Supply exactly one of `execution_id` or `result_id`. The standalone function
opens the supplied store read-only, performs indexed lookups and returns an
`ExecutionOriginReport`: source/store identity, Run/task, application attempt and
generation, task/attempt/accepted command evidence, frozen handler binding and
adjacent continuation IDs. It does not construct an Orchestrator writer, load a
whole Run or traverse filesystem catalogs. Same-store continuation keeps execution
identity queryable without copying descriptors into each new segment.

The reader targets the current schema 3 layout. Payload bytes, SQL work and elapsed
time have explicit limits; content-object decoding participates in payload limits.
The encoded-byte allowance is cumulative across roots and referenced objects,
as is the separate logical-payload allowance. The content codec exposes
`ContentReadBudget` for callers composing several `decode_value` operations;
`ContentSizeLimitError` distinguishes byte limits from malformed/deep content
while remaining a subclass of `ContentIntegrityError`. Existing decoding calls
retain their per-value limits unless a shared read budget is supplied.
`found`, `not_found` and `incomplete` are distinct, with reason codes. A missing or
oversized required record is never replaced by the latest attempt. A `not_found`
result applies only to the supplied store; it is not evidence of global absence.

The accepted handler binding is historical evidence, not proof of an available
deployment. Application-only descriptors and rework eligibility are not inferred.
Cross-store search, authenticated cold archive loading and unregistered deployment
metadata remain outside this reader. Registered provenance and lifecycle work are
tracked by the [storage plan](STORAGE_RETENTION_IMPROVEMENT_PLAN.md).
