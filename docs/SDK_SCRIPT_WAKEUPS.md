# Script execution and application conversation wakeups

The SDK can run an application script and deliver a Python callback when that
execution becomes terminal or enters `recovery_required`. The application owns
the conversation identifier and the operation that starts/resumes its Agent.
`OrchestratorHost` drives execution and notification delivery in background
threads; the LLM does not need to poll, wait in a conversation, or spend tokens
checking progress. This uses the existing Kernel process supervisor and SQLite
outbox pattern, with no additional service dependency.

For lease recovery, application waits, effects and notification handling,
see the [recovery guide](SDK_RECOVERY.md).

## Integration

```python
import sys
from dispatcher_sdk.execution_kernel import Kernel, ScriptSpec, script_handlers
from dispatcher_sdk.orchestrator import Orchestrator, OrchestratorHost

# Implement this using your application's durable Agent inbox/job queue.
# Enqueue transactionally with a UNIQUE notification_id, then return promptly.
# Its consumer starts/resumes notification["target"]["conversation_id"].
def wake_agent(notification):
    application_agent_inbox.enqueue_once(
        notification_id=notification["notification_id"],
        conversation_id=notification["target"]["conversation_id"],
        message=notification,
    )

def main():
    runtime = Kernel.open_sqlite("work.sqlite3", script_handlers(), isolation_mode="process")
    orch = Orchestrator("work.sqlite3", runtime.kernel, runtime=runtime)

    host = OrchestratorHost(orch, wake_agent).start()
    orch.create_run("report-run", command_id="create-report")
    command = ScriptSpec(
        source="print('report ready')",
        interpreter=(sys.executable, "-u"),
        cwd=".",
        output_dir="./script-logs",
    ).command(
        execution_id="report-exec-1", idempotency_key="report-exec-1",
        registry_revision=runtime.registry_revision, correlation_id="report-run",
        timeout_seconds=300,  # Application policy, explicitly required.
    )
    orch.apply_operations(
        "report-run", command_id="submit-report", expected_revision=0,
        operations=[
            {"kind": "add_task", "task_id": "report", "command": command.to_dict()},
            {"kind": "watch_task", "task_id": "report", "watch_id": "report-wake-1",
             "target": {"conversation_id": "conversation-42"}, "max_deliveries": 5},
            {"kind": "dispatch", "task_id": "report"},
        ],
    )
    host.wake()  # Optional latency hint; durable submission survives a missed wake.
    # Keep host alive for the application's lifetime; no LLM polling loop.
    # At application shutdown:
    # host.stop(timeout=10)

if __name__ == "__main__":
    main()
```

`application_agent_inbox` above is an application integration placeholder.
The sketch starts a host; the application must keep its process alive and call
`host.stop()` during shutdown. Process entrypoints need the main guard shown above. A runnable local example with a durable inbox is available at
[`examples/sdk_script_wakeup.py`](../examples/sdk_script_wakeup.py).

## Delivery and recovery contracts

- Task creation, watch registration, and dispatch intent commit atomically.
  A watch binds to the current application attempt's execution ID. Register a
  new `watch_id` for each `new_attempt`. Multiple conversations can watch the
  same execution. Late registration replays that execution's event history.
- Notifications contain `notification_id`, `target`, `run_id`, `task_id`,
  `attempt` (zero-based application attempt), `execution_id`, `kind`, `state`,
  the original Kernel `event`, and a terminal `result` when one exists.
  A planned cancellation has no Kernel event or result; its `reason` is included.
- Only terminal states (`succeeded`, `failed`, `timed_out`, `cancelled`, `dead`)
  and entry into `recovery_required` wake the application. Internal retry events
  do not. A recovery notification remains a historical fact if recovery has
  already finished; inspect current execution authority before deciding.
- Notifications use their own durable outbox and Kernel event cursors. They do
  not consume the result queue or advance business workflows automatically.
  Each collection reads at most `limit` Kernel events per open watch; startup
  catch-up time grows with event history and watch count.
- Delivery is **at least once**, with a stable notification ID. A crash after
  application acceptance and before acknowledgement may deliver again. The
  application must deduplicate durably, ideally in the same transaction that
  enqueues its conversation job. The SDK cannot make a remote conversation
  service exactly once.
- Callbacks must be synchronous and return only after durable acceptance.
  Exceptions retry after the configured delay; exhausting `max_deliveries`
  creates a dead letter. Inspect `list_notifications(state="dead")` and
  `load_notification(id)`; reopen with
  `retry_notification(id, expected_revision=record["revision"])`.
  Low-level claim/ack/fail methods support an application-owned delivery worker.
- Callbacks run on a separate thread. Slow callbacks do not block scripts, but
  can delay other notifications. Keep enqueue calls shorter than
  `notification_lease_seconds`; lease expiry can cause concurrent redelivery.
  `stop(timeout=...)` raises `TimeoutError` if it cannot drain. Python cannot
  forcibly interrupt a callback; keep its dependencies available until it
  returns. Unclaimed notifications remain durable for the next host.

## Script execution contract

`ScriptSpec` freezes inline source (up to 1 MiB), interpreter argv, absolute
working/output paths and output-tail size. Interpreter binaries, environment,
dependencies and working-directory contents remain application deployment
inputs. Use trusted scripts: process containment is not an OS security sandbox.
The helper requires POSIX process isolation and rejects the thread fallback.

The application supplies the command timeout. Scripts use one execution attempt
by default. Kernel timeout/cancellation terminates the supervised process tree.
Because arbitrary scripts can have external side effects, execution runs inside
an Effect: interruption before the outcome is committed parks the execution in
`recovery_required`, which triggers a wakeup. The application investigates and
uses `resolve_effect` to record the outcome before any retry. A timeout with an
uncertain effect therefore produces a recovery wakeup rather than pretending a
safe terminal result exists.

Normal nonzero exits produce `failed` with `error.code="script_exit_nonzero"`.
Success results and nonzero error details include `exit_code`, source path/hash,
and stdout/stderr path, byte count, SHA-256 and bounded tail (8 KiB by default,
at most 64 KiB each). Full logs stay on disk; the application owns retention,
disk quotas and access controls. For interrupted scripts, use the Effect's
`request.output_root` to locate partial logs, which may not have final hashes.

## Monitoring callback failures

`host.health().notification_error_count` counts exceptions that escape the delivery
loop. A callback failure is handled by the notification queue and may not increment
that counter. Inspect notification records and `list_notifications(state="dead")`
to detect failed or exhausted callback deliveries. A healthy worker thread alone
does not prove that the application accepted every notification.
