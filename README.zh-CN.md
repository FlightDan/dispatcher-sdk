# Dispatcher SDK

[English](README.md) | [简体中文](README.zh-CN.md)

Dispatcher SDK 执行 Python handler，把执行状态保存在 SQLite 中，并通过显式命令管理任务。
关闭进程后，用相同的 handler 重新打开数据库，已入队的任务仍然存在。
执行中断的任务则按租约、重试预算和副作用恢复规则处理。

单个作业可以直接使用 Kernel。需要管理 Run、任务依赖或持久化通知时，再接入
Orchestrator。应用决定下一步执行什么，以及何时结束整个 Run。

当前版本是开发者预览，后续发布可能调整 API 和持久化格式。要求 Python 3.10+，
运行时没有第三方依赖。仓库名是 `dispatcher-sdk`，安装包名为
`dispatcher-sdk`，导入路径为 `dispatcher_sdk`。

## 安装

```sh
git clone https://github.com/FlightDan/dispatcher-sdk.git
cd dispatcher-sdk
python -m venv .venv
```

Linux/macOS 执行 `source .venv/bin/activate`，Windows PowerShell 执行
`.venv\Scripts\Activate.ps1`，然后安装：

```sh
python -m pip install .
```

也可以从 [GitHub Releases](https://github.com/FlightDan/dispatcher-sdk/releases)
下载 wheel，用 `python -m pip install` 安装本地文件。无需等待 PyPI 发布；运行 SDK
不需要 Git、LLM 或模型账号。从源码安装时需要构建工具。

## 执行一个任务

下面是完整示例：计算三笔发票金额，通过执行结果读取总额。
示例使用临时数据库，短时间运行的可信 handler 采用线程隔离。

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy


def total(payload, context):
    return {"total": sum(payload["amounts"])}


with TemporaryDirectory() as directory:
    with Kernel.open_sqlite(Path(directory) / "jobs.sqlite3", {"total": total},
                           isolation_mode="thread") as runtime:
        runtime.submit(ExecutionCommandV2(
            execution_id="invoice-1", idempotency_key="invoice-1",
            registry_revision=runtime.registry_revision,
            correlation_id="invoice-1", causation_id=None,
            handler_id="total", handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=1), timeout_seconds=5,
            payload={"amounts": [12, 18, 30]},
        ))
        snapshot = runtime.run_once()
        assert snapshot.state == "succeeded"
        print(snapshot.result.value)  # {'total': 60}
```

需要跨进程保留任务时，使用固定的数据库路径。
[单任务示例](examples/kernel_task.py)会在提交后关闭 runtime，再重新打开数据库执行任务。

## 可以直接运行的使用示范

安装 SDK 后，在仓库目录运行：

| 命令 | 具体场景 | 预期输出 |
| --- | --- | --- |
| `python examples/kernel_task.py` | 提交任务，关闭 runtime，重新打开数据库执行 | `{'total': 60}` |
| `python examples/dependent_tasks.py` | 先计算发票总额，再把结果传给依赖它的收据任务，最后显式结束 Run | `Invoice total: 60` |
| `python examples/effect_recovery.py` | worker 写入文件后真正退出；检查文件、裁决未决副作用，再恢复执行 | `Recovered: succeeded; receipt was written once` |
| `python examples/sdk_script_wakeup.py` | 执行 Python 脚本，把完成通知写入应用的持久化 inbox；要求 POSIX 进程隔离 | `Wake conversation-42: succeeded`，随后输出 `report ready` |

恢复示例用可控时钟跳过等待租约过期的时间；worker 确实在写入文件、尚未提交回执时退出。
示例只操作临时目录，结束后清理文件。

依赖任务示例先调用 `create_run`，通过 `apply_operations` 添加并派发计算任务。
应用调用 `flush`、`runtime.run_once` 和 `sync`，检查计算结果，再创建
`dependencies=["calculate"]` 的收据任务，并把计算结果作为输入传给它。
收到收据后，应用检查结果并显式 `finish`。一个任务成功不会自动派发后继任务或结束 Run。

如果需要后台执行，可以启动 `OrchestratorHost`，由它调度 worker、同步执行状态和投递通知。
回调应把通知提交到应用的持久化 inbox，然后尽快返回。脚本示例用 SQLite 按
`notification_id` 去重；实际应用可以由 inbox 消费者启动对话或其他作业。
SDK 自身不会启动 Agent 对话。

## 使用时需要理解的约定

- SQLite 保存执行事实、编排命令和投递队列。结果与通知采用至少一次投递，消费者需要按稳定消息身份去重。
- `RetryPolicy.max_attempts` 包含首次领取，默认是 1。普通租约过期重投和可重试的执行失败共享这个预算；重开数据库不会增加次数。
- 外部修改应通过 `context.effects.execute_once` 执行。已提交的响应可以复用；外部动作发生后、回执保存前中断，会进入 `recovery_required`，由应用核对外部事实再显式裁决。SDK 不保证任意文件写入或 API 调用恰好执行一次。
- 空轮询可能是租约仍有效或任务还在退避，不能据此判定 Run 停滞或完成。业务重试、等待和结束由应用显式决定。
- 进程隔离要求 POSIX fork 支持，以及受 `if __name__ == "__main__":` 保护的入口。Linux 还会清理脱离原进程组的后代进程，其他 POSIX 平台提供进程组清理。它用于约束可信 handler 的执行，不是恶意代码沙箱。脚本功能要求进程模式。
- Windows 使用线程隔离。Python 不能强制终止阻塞线程；取消会撤销结果和 Effect 权限，但不能撤销已经发生的外部动作。

## 文档与维护

- [SDK 操作与示例](docs/SDK.md)
- [恢复、重试预算与外部副作用](docs/SDK_RECOVERY.md)
- [脚本执行与应用唤醒回调](docs/SDK_SCRIPT_WAKEUPS.md)
- [公开 API、平台行为与兼容性](docs/PUBLIC_API.md)
- [Kernel 持久化与隔离约定](src/dispatcher_sdk/execution_kernel/README.md)

CI 配置覆盖 Linux、Windows 和 Python 3.10、3.11、3.12、3.13。进程专属测试只在支持的平台运行，
首批 CI 不包含 macOS。使用某个平台和版本组合前，应查看候选发布的 CI 结果。
预览版没有通用数据库迁移工具；恢复任务时保留匹配的 handler 部署，遇到不兼容升级前先完成或归档已有 Run。

开发和测试见 [CONTRIBUTING.md](CONTRIBUTING.md)，漏洞私密报告方式见
[SECURITY.md](SECURITY.md)，源码来源见 [PROVENANCE.md](PROVENANCE.md)。
项目采用 [Apache-2.0](LICENSE) 许可证。
