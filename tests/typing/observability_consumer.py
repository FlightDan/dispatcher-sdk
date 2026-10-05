"""Type-check the public observation, budget and supervision interfaces."""
from pathlib import Path
from typing import Any

from dispatcher_sdk import Dispatcher, ExecutionActivity, ObservationOptions, StallPolicy, Task, BudgetEnvelope, ExecutionBudget, ManagedStallOptions
from dispatcher_sdk.execution_kernel import ChildCalls, HandlerContext, SQLiteKernel


def work(payload: Any, context: HandlerContext) -> Any:
    budget: ExecutionBudget = context.budget
    tool: BudgetEnvelope = context.derive_budget(source="tool", origin_id="tool:1", timeout_seconds=2)
    context.activity.enable_stream("stdout")
    context.activity.report_bytes("stdout", b"raw", retain_tail=False)
    context.activity.progress("one-step")
    activity: ExecutionActivity = context.activity
    children: ChildCalls = context.children
    activity.report_bytes("stdout", "not bytes")  # type: ignore[arg-type]
    activity.progress("step", timeout="forever")  # type: ignore[arg-type]
    children.run("child", {}, request_id="bounded", timeout_seconds="forever")  # type: ignore[arg-type]
    children.wait_for("child", request_id=123)  # type: ignore[arg-type]
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


def supervise(notification: dict[str, Any], context: HandlerContext) -> dict[str, Any]:
    context.activity.progress("reviewed-notice")
    budget: ExecutionBudget = context.budget
    return {"notification_id": notification["notification_id"],
            "remaining": budget.remaining_work_seconds}


def consume_managed(path: Path) -> None:
    options = ManagedStallOptions(memory_limit_bytes=512 * 1024 * 1024, capacity=1,
                                  memory_budget_bytes=512 * 1024 * 1024, budget_seconds=10)
    with Dispatcher(path, {"work": work}, stall_handler=supervise, stall_options=options) as app:
        report: dict[str, Any] = app.stall_supervisor_status()
        detail: dict[str, Any] = app.stall_supervisor_status("notice")
        app.subscribe_stalls(handler=supervise, options=options)
        app.stall_supervisor_status(123)  # type: ignore[arg-type]
        app.subscribe_stalls(handler=supervise, options="unbounded")  # type: ignore[arg-type]
        print(report, detail)
