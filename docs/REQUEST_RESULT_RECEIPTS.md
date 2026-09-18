# Request results and caller receipts

`RequestResultInbox` composes the existing `NotificationInbox` without a new
database schema. It is an adapter-facing journal for one immutable result per
`(source_id, caller_id, request_id)`, with independent transport and caller
receipts. Use a dedicated inbox file and do not run a generic `claim`/`consume`
worker over its records. Its inbox messages are facts, not a work queue.

```python
from dispatcher_sdk.orchestrator import NotificationInbox, RequestResultInbox

results = RequestResultInbox(NotificationInbox("request-results.db"))
identity = results.record_result(
    "source-01", "caller-17", "request-4",
    execution_id="execution-42", result_id="result-42",
    result={"status": "succeeded", "output": "build log available"},
)
results.mark_delivered(identity)
late = results.lookup("source-01", "caller-17", "request-4")
assert late is not None
assert late.received_confirmed_at is None

# Execute only after a separate explicit caller acknowledgement, authenticated
# by the adapter and bound to this caller ID and the exact result identity.
results.confirm_received(late.identity)
```

The [runnable example](../examples/request_result_receipts.py) demonstrates
reopening the journal before consuming a late response.

## Facts and ordering

- `record_result` durably records the adapter's supplied terminal result; the SDK
  does not execute the task or independently prove its terminal state here.
  Serialize an `ExecutionResultV2` using `to_dict()` when recording Kernel results.
- `mark_delivered` records the transport's report of delivery. Returning from a
  tool handler or successfully sending bytes does not prove the caller received them.
- `confirm_received` records the caller's explicit acknowledgement of the exact
  source/caller/request/execution/result identity and canonical result digest.
  It is neither model comprehension nor review approval.
- `lookup` performs point reads and never marks delivery or reception. `None`
  means no result exists in this journal for the requested scope; it does not
  imply that no execution exists elsewhere. A missing timestamp means unknown
  delivery or unconfirmed reception, not proof that delivery did not happen.

These are independent facts. A caller ACK can arrive before the adapter stores
its transport receipt. Queries use independent inbox snapshots; they may miss a
concurrently committed receipt. Repeating a query observes later commits.

## Adapter integration and retries

Persist a stable request identity before SDK submission. Keep the mapping from
that identity to Run/task and execution/result identities; `submit_task` request
IDs are scoped to Run/task and do not automatically form a global request registry.
Namespace sources and callers explicitly. For a request that produces multiple
results, assign distinct application subrequest identities.

When receiving an upstream result, record it first, then acknowledge that
upstream delivery using its existing lease/fence. A crash between these steps
causes replay, which returns the same journal identity. Record a transport
receipt after delivery if the transport can report it. Authenticate a later ACK
and its caller namespace before passing the exact identity to `confirm_received`.
If the client protocol cannot emit that ACK, leave reception unconfirmed.

Identical publication and receipt retries preserve original timestamps. Reusing
the same request with a different result, execution or result ID raises
`CommandConflict`. Receipts for missing results raise `KeyError`; mismatched
identities/digests raise `CommandConflict`. No replay replaces the stored result.
Returned result payloads are detached from storage.

Caller/source IDs and SHA-256 digests provide correlation and conflict detection,
not authentication. An adapter must bind an authenticated caller to its namespace;
the SDK cannot infer who sent an ACK. The journal is application-owned, retained
until the application explicitly manages that separate database. No automatic
retention, core Run gating or MCP transport implementation is added.
