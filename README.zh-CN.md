# Dispatcher SDK

[English](README.md) | [简体中文](README.zh-CN.md)

**为 Agent 应用执行任务，提供进程隔离、状态持久化、中断恢复和任务编排。**

Dispatcher 运行应用提交的 Python 函数或脚本，控制执行超时和取消，
将任务状态保存在 SQLite 中，并可通过任务订阅在任务结束或需要恢复处理时通知应用。
应用可以根据结果继续对话、安排后续任务，或处理执行中断。

## 可以做什么

| 能力 | 用在什么地方 |
| --- | --- |
| **执行隔离与控制** | 在进程模式下独立运行任务，超时或取消时终止受监督的进程树，处理卡住的工具调用 |
| **持久化执行** | 将任务、结果和通知保存到 SQLite；关闭后重开原数据库，已入队的任务仍然存在 |
| **有限重试** | 为允许重试的执行失败配置次数和退避，避免无限重跑 |
| **外部操作恢复** | 为通过 Effect 接口登记的文件写入、API 调用保存回执；中断后结果不确定时，等待应用核对并裁决 |
| **多步任务编排** | 记录任务依赖、业务尝试和等待条件，由应用决定派发、返工或结束 |
| **结果与通知** | 读取执行结果和脚本日志，将任务状态通知应用，让 Agent 接续流程，无需 LLM 反复查询进度 |

Dispatcher 是嵌入 Python 应用的 SDK，运行时只依赖标准库和 SQLite，
无需额外部署队列服务，也不绑定特定模型或 Agent 框架。

## 适合你的应用吗

如果你的 Agent 应用需要运行工具或脚本、限制执行时长、保留任务状态，
或将多个任务组织成可恢复的流程，可以按需接入 Dispatcher。
只运行一个函数任务时也可以使用，不必先接入通知和多步编排。

应用负责决定任务内容、业务验收和下一步操作；Dispatcher 负责执行控制、
状态记录和可靠传输。后台执行期间，需要保持宿主进程运行。

接入边界：

- **执行隔离**：进程模式用于约束可信代码，提供超时、取消和进程清理；不提供不可信代码所需的文件、网络或权限沙箱。Agent 生成的代码仍需应用审查或额外沙箱。
- **平台差异**：脚本要求 POSIX 进程隔离。Linux 还会清理脱离原进程组的后代进程，其他 POSIX 平台提供进程组清理。Windows 可用线程模式执行 Python 函数，但不能强制停止阻塞线程。
- **重启与重试**：恢复需要原数据库和匹配的 handler 部署。重开数据库不会重置重试次数，也不保证中断的任务一定自动重跑。
- **外部操作**：SDK 不能撤销已经发生的写入或 API 调用；结果不确定时需核对后恢复，不能承诺任意操作只发生一次。
- **结果与通知**：采用至少一次投递，应用需要按稳定消息 ID 持久化去重。

当前为开发者预览，要求 Python 3.10+。API 和持久化格式可能变化，
升级前请阅读[兼容性说明](docs/PUBLIC_API.md)。

## 安装

从源码安装，在 Linux 终端执行：

```sh
git clone https://github.com/FlightDan/dispatcher-sdk.git
cd dispatcher-sdk
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

Windows PowerShell 使用 `.venv\Scripts\Activate.ps1` 激活环境。
也可以从 [GitHub Releases](https://github.com/FlightDan/dispatcher-sdk/releases)
下载 wheel，用 `python -m pip install <wheel文件路径>` 安装。

## 使用案例

### 1. 后台生成报告，完成后接续对话

下面以“后台生成报告”为场景。演示脚本只输出 `report ready`，便于先验证完整链路；
接入时可替换为自己的报告生成逻辑。

1. 应用提交脚本，并登记接收通知的对话标识。
2. Dispatcher 在后台执行脚本，把通知交给应用回调。
3. 回调将通知写入应用的 SQLite 收件箱，按通知 ID 去重。
4. 示例读取收件箱并打印结果。实际应用在这里接入继续对话或处理报告的逻辑。

安装后，在仓库目录运行：

```sh
python examples/sdk_script_wakeup.py
```

预期输出：

```text
Wake conversation-42: succeeded
report ready
```

<details>
<summary>展开完整 Python 示例：提交脚本、接收通知、读取结果</summary>

将代码保存为 `demo.py`，安装 SDK 后运行 `python demo.py`。

<!-- example-platform: posix -->

```python
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import threading

from dispatcher_sdk.execution_kernel import Kernel, ScriptSpec, script_handlers
from dispatcher_sdk.orchestrator import Orchestrator, OrchestratorHost


def main():
    with tempfile.TemporaryDirectory(prefix='sdk-wakeup-') as directory:
        root = Path(directory)
        inbox = root / 'application-inbox.sqlite3'
        with sqlite3.connect(inbox) as connection:
            connection.execute('CREATE TABLE inbox (notification_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        accepted = threading.Event()

        def wake_agent(notification):
            with sqlite3.connect(inbox) as connection:
                connection.execute('INSERT OR IGNORE INTO inbox VALUES(?,?)',
                                   (notification['notification_id'], json.dumps(notification)))
            accepted.set()

        runtime = Kernel.open_sqlite(root / 'work.sqlite3', script_handlers(), isolation_mode='process')
        orch = Orchestrator(root / 'work.sqlite3', runtime.kernel, runtime=runtime)
        orch.create_run('example', command_id='create')
        command = ScriptSpec("print('report ready')", (sys.executable, '-u'), root, root / 'logs').command(
            execution_id='script-1', idempotency_key='script-1', registry_revision=runtime.registry_revision,
            correlation_id='example', timeout_seconds=10)
        with OrchestratorHost(orch, wake_agent):
            orch.apply_operations('example', command_id='submit', expected_revision=0, operations=[
                {'kind': 'add_task', 'task_id': 'report', 'command': command.to_dict()},
                {'kind': 'watch_task', 'task_id': 'report', 'watch_id': 'report-wake',
                 'target': {'conversation_id': 'conversation-42'}},
                {'kind': 'dispatch', 'task_id': 'report'},
            ])
            # Demo process lifetime: wait on a Python event, with no LLM polling.
            if not accepted.wait(15):
                raise TimeoutError('demo did not receive its callback')
        with sqlite3.connect(inbox) as connection:
            notification = json.loads(connection.execute('SELECT payload FROM inbox').fetchone()[0])
        assert notification['state'] == 'succeeded', notification
        assert notification['result']['value']['stdout']['tail'].strip() == 'report ready'
        orch.close()
        print(f"Wake {notification['target']['conversation_id']}: {notification['state']}")
        print(notification['result']['value']['stdout']['tail'].strip())


if __name__ == '__main__':
    main()
```

示例使用临时目录，退出后清理数据库和日志。实际接入时使用固定路径，
并保持 `OrchestratorHost` 运行。回调应在通知可靠入队后尽快返回，
由应用的收件箱消费者接续 Agent 流程。

</details>

### 2. 任务卡住时，超时终止任务和子进程

工具调用可能阻塞，也可能启动额外的子进程。进程模式可以在任务超时后清理
受监督的进程树，让应用继续执行其他任务。

这个 Linux 示例运行一个会休眠 30 秒的函数，并让它启动一个同样休眠的子进程。
执行超时设为 2 秒。示例检查函数进程和子进程都已退出，再用同一个 runtime
执行正常任务，验证仍可继续工作。

```sh
python examples/isolation_timeout.py
```

预期输出：

```text
timeout: timed_out; handler and child are gone
next task: succeeded
```

<details>
<summary>展开完整 Python 示例：进程隔离、超时清理、继续执行</summary>

将代码保存为 `isolation_demo.py`，在 Linux 上运行 `python isolation_demo.py`。
也可直接查看[示例文件](examples/isolation_timeout.py)。

<!-- example-platform: linux -->

```python
import os
from pathlib import Path
import sys
import tempfile
import time

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, Kernel, RetryPolicy


def sleep_with_child(payload, _context):
    child = os.fork()
    if child == 0:
        time.sleep(30)
        os._exit(0)
    Path(payload["pid_file"]).write_text(f"{os.getpid()} {child}", encoding="ascii")
    time.sleep(30)


sleep_with_child.__execution_kernel_revision__ = "isolation-timeout-v1"


def echo(payload, _context):
    return payload


echo.__execution_kernel_revision__ = "isolation-timeout-v1"


def command(runtime, execution_id, handler_id, payload, timeout_seconds):
    return ExecutionCommandV2(
        execution_id=execution_id,
        idempotency_key=execution_id,
        registry_revision=runtime.registry_revision,
        correlation_id=execution_id,
        causation_id=None,
        handler_id=handler_id,
        handler_contract_version=1,
        retry_policy=RetryPolicy(max_attempts=1),
        timeout_seconds=timeout_seconds,
        payload=payload,
    )


def assert_gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    raise AssertionError(f"PID {pid} survived timeout cleanup")


def main():
    if os.name != "posix" or not sys.platform.startswith("linux"):
        raise SystemExit("This example requires Linux process isolation.")

    with tempfile.TemporaryDirectory(prefix="dispatcher-isolation-") as directory:
        root = Path(directory)
        pid_file = root / "pids.txt"
        handlers = {"sleep": sleep_with_child, "echo": echo}
        with Kernel.open_sqlite(root / "jobs.sqlite3", handlers, isolation_mode="process") as runtime:
            runtime.submit(command(runtime, "timeout", "sleep", {"pid_file": str(pid_file)}, 2))
            timed_out = runtime.run_once()
            assert timed_out.state == "timed_out", timed_out.state
            assert timed_out.result.error.code == "handler_timeout"
            assert pid_file.exists(), "timed-out handler never reached startup"
            pids = [int(value) for value in pid_file.read_text(encoding="ascii").split()]
            assert len(pids) == 2, pids
            for pid in pids:
                assert_gone(pid)
            print("timeout: timed_out; handler and child are gone")

            runtime.submit(command(runtime, "next", "echo", {"message": "reused"}, 2))
            succeeded = runtime.run_once()
            assert succeeded.state == "succeeded"
            assert succeeded.result.value == {"message": "reused"}
            print("next task: succeeded")


if __name__ == "__main__":
    main()
```

这里运行可信函数，并在临时目录写入 PID 作为检查依据。示例展示进程生命周期控制，
不限制函数对文件或网络的访问。

</details>

应用也可以通过 `runtime.cancel` 显式取消任务。进程模式会清理受监督的进程树；
线程模式只能撤销提交结果和 Effect 的权限，无法强制停止阻塞线程。
如果中断时存在未决外部操作，任务可能进入 `recovery_required`，而不是直接结束。
`ScriptSpec` 执行会登记 Effect，因此脚本中断时尤其需要检查恢复状态。
详见[隔离与生命周期说明](docs/PUBLIC_API.md)。

### 3. 重启后继续处理任务，中断后核对外部操作

任务提交后应用退出，重新打开同一个数据库，仍可领取之前排队的任务。
[持久化示例](examples/kernel_task.py)演示“提交 → 关闭 → 重开 → 执行”，输出 `{'total': 60}`：

```sh
python examples/kernel_task.py
```

如果任务已经写入文件，但还没保存操作回执就崩溃，直接重跑可能重复写入。
[恢复示例](examples/effect_recovery.py)让 worker 在这个窗口真正退出；应用检查文件，
确认写入已发生，通过 `resolve_effect` 记录裁决，再恢复执行，验证没有第二次写入：

```sh
python examples/effect_recovery.py
```

外部操作需通过 `context.effects.execute_once` 登记。已提交的回执可复用，
未决操作进入 `recovery_required`，由应用依据外部事实裁决。
示例使用可控时钟跳过租约等待，只操作临时文件。

普通执行失败和租约过期重投共享 `RetryPolicy.max_attempts`，其中包含首次领取，
默认是 1。应用应按任务是否可安全重试设置有限次数和退避。
业务返工使用显式的新尝试，与执行重试、通知重投分别计数。
详见[恢复与重试指南](docs/SDK_RECOVERY.md)。

### 4. 根据前一步结果，决定下一项任务

Agent 的多步工作可能需要先检查结果，再决定继续、返工或等待。
应用可以在一个 Run 中组织任务依赖，读取结果后显式提交下一步。

[依赖任务示例](examples/dependent_tasks.py)先计算金额，应用检查结果后，
把总额传给依赖它的收据任务，最后显式结束 Run，输出 `Invoice total: 60`：

```sh
python examples/dependent_tasks.py
```

依赖成功不会自动派发后继任务，单个任务成功也不会自动结束 Run。
应用还可以登记等待条件，在条件满足后解除等待，或提交新的业务尝试。
详见[SDK 操作与编排](docs/SDK.md)。

## 接入自己的 Agent 应用

按需要选择入口：

| 你要接入的能力 | 入口与应用责任 |
| --- | --- |
| 函数执行与隔离 | `Kernel.open_sqlite` 注册 handler、选择隔离模式；命令设置超时与 `RetryPolicy` |
| 脚本执行与日志 | `ScriptSpec` 指定脚本、解释器、工作目录和日志目录，`.command()` 设置超时 |
| 持久化与恢复 | 使用固定数据库路径和匹配的 handler 部署；通过 `context.effects.execute_once` 记录外部操作，按证据 `resolve_effect` |
| 依赖、等待与业务返工 | `Orchestrator` 创建 Run，通过 `apply_operations` 显式提交任务、依赖、等待、新尝试和结束操作 |
| 后台运行 | 单独执行可用 `RuntimeHost`；编排场景用 `OrchestratorHost` 驱动执行、同步和通知投递 |
| 应用通知 | `watch_task` 的 `target` 关联对话或业务任务；回调可靠保存并去重通知，由消费者接续流程 |

## 深入阅读

- [SDK 操作与示例](docs/SDK.md)：任务、依赖、等待与显式编排。
- [Kernel 执行契约](src/dispatcher_sdk/execution_kernel/README.md)：隔离、超时、取消和持久化机制。
- [恢复、重试与外部副作用](docs/SDK_RECOVERY.md)：中断后如何判断、等待和恢复。
- [脚本执行与应用通知](docs/SDK_SCRIPT_WAKEUPS.md)：脚本、日志、回调和通知重试。
- [公开 API 与兼容性](docs/PUBLIC_API.md)：接口、平台差异和升级约束。

开发和测试见 [CONTRIBUTING.md](CONTRIBUTING.md)，漏洞报告见
[SECURITY.md](SECURITY.md)，源码来源见 [PROVENANCE.md](PROVENANCE.md)。
项目采用 [Apache-2.0](LICENSE) 许可证。
