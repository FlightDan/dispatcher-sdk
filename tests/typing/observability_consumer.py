"""Type-check the public observation, budget and supervision interfaces."""
from pathlib import Path
from typing import Any

from dispatcher_sdk import Dispatcher, ObservationOptions, StallPolicy, Task, BudgetEnvelope, ExecutionBudget
from dispatcher_sdk.execution_kernel import HandlerContext, SQLiteKernel


def work(payload: Any, context: HandlerContext) -> Any:
    budget: ExecutionBudget = context.budget
    tool: BudgetEnvelope = context.derive_budget(source="tool", origin_id="tool:1", timeout_seconds=2)
    context.activity.enable_stream("stdout")
    context.activity.report_bytes("stdout", b"raw", retain_tail=False)
    context.activity.progress("one-step")
    return {"remaining": budget.remaining_work_seconds, "tool": tool.to_dict()}


def consume(path: Path) -> None:
    with SQLiteKernel(path, control_timeout_seconds=.1) as kernel:
        print(kernel.current_time())
    with Dispatcher(path, {"work": work}, observation_options=ObservationOptions(), child_capacity=1) as app:
        task: Task = app.submit("work", {}, request_id="message")
        observation: dict[str, Any] = task.observe(timeout=3)
        task.events(after=0, limit=50)
        task.watch_stall(StallPolicy("progress"))
        task.stall_windows(limit=50)
        app.subscribe_stalls(lambda notification: None)
        app.stall_notifications(limit=50)
        page = app.stall_notification_page(limit=50)
        app.stall_notification_page(after=page["cursor"])
        app.retry_stall_notification("notice", expected_revision=1, phase="observation")
        task.cancel_if_stalled({"kind": "stalled"})
        task.observe(timeout="forever")  # type: ignore[arg-type]
        print(observation, app.runtime.observation_storage)
        reports: tuple[dict[str, Any], ...] = app.runtime.recover_completions(timeout_seconds=.5)
        print(reports)
