# 托管任务

[English](Managed-Tasks.md) | [简体中文](Managed-Tasks-zh-CN.md) | [首页](Home-zh-CN.md)

0.7 推荐用 `Dispatcher` 运行普通本地任务。它用一个 SQLite 文件管理 Runtime、
Orchestrator、后台 Host 和通知收件箱。需要任务依赖、等待条件或显式 Run 决策时，
仍可使用底层接口。

```python
from dispatcher_sdk import Dispatcher


def double(payload, context):
    return payload * 2


with Dispatcher("tasks.sqlite3", {"double": double}) as app:
    task = app.submit("double", 21, request_id="message-42")
    result = task.wait(timeout=10)
    print(result["value"])
```

`request_id` 应来自应用已有的持久身份。相同 ID 和内容会返回原任务；内容变化时抛出
`SubmissionConflictError`。进程重启后，重新打开同一路径，再调用
`app.task("message-42")` 即可取回任务句柄。

默认使用进程隔离。它能终止受监督的可信代码，但不会限制文件和网络权限。
线程模式需要显式开启，而且无法强制停止阻塞调用。

## 处理结果

需要后台回调时，传入 `on_result=callback`。Dispatcher 会先把通知写入收件箱，
再调用回调。回调失败只会重试通知，不会重跑任务。回调仍可能重复，因此调用外部
API 时必须使用幂等键。

如果只写本地业务表，不要设置 `on_result`，改用
`app.consume_results(mutation)`。mutation 会收到 SQLite 连接和通知；业务 SQL 与
消费标记在同一事务中提交。这个函数应尽快返回，也不应在事务里调用外部服务。

执行成功不等于业务验收。外部 Effect 的结果无法确认时，`Task.wait()` 会抛出
`RecoveryRequiredError`。此时应查看证据，再通过 Runtime 或 Orchestrator 的恢复接口裁决。

Dispatcher 在打开写连接前检查 schema 和未完成任务的 handler 绑定。
如果部署不匹配，`DeploymentMismatchError.report` 会给出原因。`app.health()` 只读取
内存状态；`app.diagnostics()` 会执行有时间上限的 SQLite 只读查询。完整契约见
[统一应用接口](../docs/MANAGED_APPLICATION.md)。

`close(timeout=...)` 会先停止接收新工作，等待结果消费者退出，再停止 Host。
如果回调被卡住，关闭操作会超时。不要提前销毁回调依赖，等回调返回后再次调用 `close()`。
