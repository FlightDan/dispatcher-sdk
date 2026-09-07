# Dispatcher SDK：面向 AI Agent 的持久化任务编排

[English](README.md) | [简体中文](README.zh-CN.md) | [Wiki](wiki/Home-zh-CN.md) | [Agent 接入文档](DocsforAgents/README.md) | [API 文档](docs/SDK.md)

Dispatcher 使用 SQLite 保存任务状态、结果和通知。关闭后重开同一个数据库，
已经入队的任务仍然存在。

**核心运行时不依赖第三方包。**

Dispatcher 是一个嵌入 Python 应用的 SDK。它在本地运行应用提交的 Python 函数和脚本，
也可以通过远程沙箱执行脚本。Dispatcher 控制超时与取消，并把任务状态写入 SQLite。
对于沙箱任务，它会按设定的上限收集输出和制品，并保留执行中断后清理资源所需的状态。
应用可以订阅任务，在工作完成或需要恢复时收到通知，再根据结果继续对话、安排后续任务
或处理执行中断。

## 可以做什么

| 能力 | 用在什么地方 |
| --- | --- |
| 执行隔离与控制 | 在进程模式下独立运行任务；超时或取消时终止受监督的进程树，也能处理卡住的工具调用 |
| 沙箱执行 | 通过可插拔的 `SandboxBackend`（沙箱后端接口）运行脚本，按设定的上限收集输出和制品，并保存清理和恢复所需的状态；可选的 OpenSandbox 适配器需要对应 SDK 和独立的沙箱服务 |
| 持久化执行 | 将任务、结果和通知保存到 SQLite；关闭后重开原数据库，已入队的任务仍然存在 |
| 有限重试 | 为允许重试的执行失败设置次数和退避间隔，避免无限重跑 |
| 外部操作恢复 | 通过 Effect（登记外部操作的接口）记录文件写入、API 调用等操作并保存回执；中断后结果不确定时，等待应用核对并裁决 |
| 多步任务编排 | 记录任务依赖、业务尝试和等待条件，由应用决定派发、返工或结束 |
| 结果与通知 | 读取执行结果和脚本日志，把任务状态通知应用，让 Agent 接续流程，不必由 LLM（大语言模型）反复查询进度 |

核心运行时只依赖 Python 标准库和 SQLite；无需另外部署队列服务，也不绑定特定模型或 Agent 框架。

## 适合你的应用吗

如果 Agent 应用需要运行工具或脚本、限制执行时长、保留任务状态，
或把多个任务组织成可恢复的流程，就可以接入 Dispatcher。
即使只运行一个函数任务，也不必先接入通知或多步编排。

应用决定任务内容、业务验收标准和下一步操作。Dispatcher 负责执行控制、状态记录和可靠传输。
后台执行期间，宿主进程必须保持运行。

接入边界：

- 进程模式用于约束可信代码，提供超时、取消和进程清理。它不是不可信代码所需的文件、网络或权限沙箱；Agent 生成的代码仍需经过应用审查，或放进额外沙箱。
- Linux 进程模式通过 subreaper（用于回收子进程的机制）清理脱离原进程组的后代；其他 POSIX（类 Unix 系统标准）平台提供进程组清理。Windows 使用 Job Object（Windows 的进程容器）执行原生进程和脚本，已在 Windows 11 x64（build 10.0.26100.9168）、Python 3.12.10 上通过原生测试。验证范围与结果见 [Windows 运行时](docs/WINDOWS_RUNTIME.md)。线程模式不能强制停止阻塞处理器。
- 恢复时必须使用原数据库和匹配的 handler（任务处理函数）部署。重开数据库不会重置重试次数，也不保证中断的任务一定自动重跑。
- SDK 不能撤销已经发生的写入或 API 调用。结果不确定时必须先核对再恢复；不能保证任意操作只发生一次。
- 结果和通知采用至少一次投递（同一消息可能到达多次）。应用需要按稳定的消息 ID 持久化去重。

0.6 是开发者预览版，要求 Python 3.10+。Orchestrator（负责多步编排的组件）的
持久化布局改为 schema 2（数据库结构版本 2），不会自动迁移旧版编排数据库。
升级前请阅读[存储与升级](docs/STORAGE_AND_UPGRADES.md)和[兼容性说明](docs/PUBLIC_API.md)。
可选的 OpenSandbox 适配器需要额外安装固定版本的 `opensandbox` 依赖，并连接独立的沙箱服务。

## 安装

在 Linux 终端运行以下命令，从源码安装：

```sh
git clone https://github.com/FlightDan/dispatcher-sdk.git
cd dispatcher-sdk
python -m venv .venv
source .venv/bin/activate
python -m pip install .
```

在 Windows PowerShell 中，使用 `.venv\Scripts\Activate.ps1` 激活环境。
也可以从 [GitHub Releases](https://github.com/FlightDan/dispatcher-sdk/releases) 下载 wheel 包，
再用 `python -m pip install <wheel文件路径>` 安装。

## 使用案例

### 1. 后台生成报告，完成后接续对话

这个示例用一个只输出 `report ready` 的脚本，串起后台生成报告的流程。
实际接入时，把它替换成自己的报告逻辑。

1. 应用提交脚本，并登记要接收通知的对话标识。
2. Dispatcher 在后台运行脚本，再把通知交给应用回调（Dispatcher 调用的函数）。
3. 回调把通知写入应用的 SQLite 收件箱（保存待处理通知的表），并按通知 ID 去重。
4. 示例读取收件箱并打印结果。实际应用可以在这里接续对话或处理报告。

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

```python
from contextlib import closing
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
        with closing(sqlite3.connect(inbox)) as connection, connection:
            connection.execute('CREATE TABLE inbox (notification_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        accepted = threading.Event()

        def wake_agent(notification):
            with closing(sqlite3.connect(inbox)) as connection, connection:
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
        with closing(sqlite3.connect(inbox)) as connection, connection:
            notification = json.loads(connection.execute('SELECT payload FROM inbox').fetchone()[0])
        assert notification['state'] == 'succeeded', notification
        assert notification['result']['value']['stdout']['tail'].strip() == 'report ready'
        orch.close()
        print(f"Wake {notification['target']['conversation_id']}: {notification['state']}")
        print(notification['result']['value']['stdout']['tail'].strip())


if __name__ == '__main__':
    main()
```

示例使用临时目录，退出时会清理数据库和日志。实际接入时请使用固定路径，
并保持 `OrchestratorHost` 运行。回调在通知可靠入队后应尽快返回，
再由应用的收件箱消费者接续 Agent 流程。

</details>

### 2. 任务卡住时，超时终止任务和子进程

工具调用有时会阻塞，也可能启动其他子进程。进程模式会在任务超时后清理
受监督的进程树，让应用继续执行其他任务。

这个 Linux 示例运行一个休眠 30 秒的函数；函数还会启动一个同样休眠的子进程。
执行超时设为 2 秒。示例先确认函数进程和子进程都已退出，再用同一个 runtime（运行时实例）
执行正常任务，验证后续任务仍能运行。

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

示例运行的是可信函数。它把进程 ID（PID）写入临时目录，供示例检查进程是否已退出。
这个模式负责控制进程生命周期，但不限制函数访问文件或网络。

</details>

应用也可以调用 `runtime.cancel` 显式取消任务。进程模式会清理受监督的进程树；
线程模式只能撤销提交结果和 Effect 的权限，无法强制停止阻塞线程。
如果中断时有未决外部操作，任务可能进入 `recovery_required`（需要恢复），而不是直接结束。
`ScriptSpec` 执行会登记 Effect，因此脚本中断时尤其需要检查恢复状态。
详见[隔离与生命周期说明](docs/PUBLIC_API.md)。

### 3. 重启后继续处理任务，中断后核对外部操作

任务提交后即使应用退出，重新打开同一个数据库也能领取之前排队的任务。
[持久化示例](examples/kernel_task.py)提交任务后关闭 runtime，再重开数据库执行任务，输出 `{'total': 60}`：

```sh
python examples/kernel_task.py
```

如果任务已经写入文件，却在保存操作回执前崩溃，直接重跑可能再次写入。
[恢复示例](examples/effect_recovery.py)让 worker（负责执行任务的进程）在这个时点退出；应用检查文件，
确认写入已发生后，通过 `resolve_effect` 记录裁决，再恢复执行，验证没有第二次写入：

```sh
python examples/effect_recovery.py
```

外部操作必须通过 `context.effects.execute_once` 登记。已提交的回执可以复用；
未决操作会进入 `recovery_required`，由应用依据外部事实作出裁决。
示例使用可控时钟跳过租约等待，只操作临时文件。

普通执行失败和租约（领取任务后暂时占用它的期限）过期后的重投共用 `RetryPolicy.max_attempts`；
这个数包括第一次领取，默认值是 1。应用应根据任务是否可安全重试，设置有限的次数和退避间隔。
业务返工通过显式的新尝试完成，和执行重试、通知重投分别计数。
详见[恢复与重试指南](docs/SDK_RECOVERY.md)。

### 4. 根据前一步结果，决定下一项任务

Agent 的多步工作通常要先检查结果，再决定继续、返工还是等待。
应用可以在一个 Run（一次应用工作）中组织任务依赖，读到结果后显式提交下一步。

[依赖任务示例](examples/dependent_tasks.py)先计算金额；应用检查结果后，
把总额传给依赖它的收据任务，最后显式结束 Run，输出 `Invoice total: 60`：

```sh
python examples/dependent_tasks.py
```

即使依赖任务成功，也不会自动派发后继任务；单个任务成功也不会自动结束 Run。
应用还可以登记等待条件，在条件满足后解除等待，或提交新的业务尝试。
详见[SDK 操作与编排](docs/SDK.md)。

## 接入自己的 Agent 应用

根据要接入的能力选择入口：

| 你要接入的能力 | 入口与应用责任 |
| --- | --- |
| 函数执行与隔离 | 用 `Kernel.open_sqlite` 注册 handler、选择隔离模式；命令设置超时与 `RetryPolicy`（重试策略） |
| 脚本执行与日志 | 用 `ScriptSpec`（脚本配置）指定脚本、解释器、工作目录和日志目录，再由 `.command()` 设置超时 |
| 持久化与恢复 | 使用固定数据库路径和匹配的 handler 部署；通过 `context.effects.execute_once` 记录外部操作，再按证据调用 `resolve_effect` |
| 依赖、等待与业务返工 | 用 `Orchestrator` 创建 Run，通过 `apply_operations` 显式提交任务、依赖、等待、新尝试和结束操作 |
| 后台运行 | 单独执行可用 `RuntimeHost`；编排场景用 `OrchestratorHost` 驱动执行、同步和通知投递 |
| 应用通知 | 用 `watch_task` 的 `target` 关联对话或业务任务；回调可靠保存并去重通知，再由消费者接续流程 |

## 深入阅读

- [原子提交单个任务](docs/TASK_SUBMISSION.md)：稳定请求 ID 与单处理器绑定。
- [存储与升级](docs/STORAGE_AND_UPGRADES.md)：持久化配置、部署预检、备份、Run 分页与分段延续。
- [Run 存储验证](docs/RUN_STORAGE_VALIDATION.md)：增量历史的实测增长与完整 Run 读取成本。
- [可靠通知收件箱](docs/NOTIFICATION_INBOX.md)：带租约和 fence（防止旧消费者继续写入的标记）的消费及同事务业务 SQL。
- [沙箱运行时](docs/SANDBOX_RUNTIME.md)与 [OpenSandbox 适配器](docs/SANDBOX_ADAPTERS.md)：远程执行、产物与销毁恢复。
- [进程清理验证](docs/PROCESS_CLEANUP_VALIDATION.md)：Linux 清理证据与回退路径的限制。
- [SDK 操作与示例](docs/SDK.md)：任务、依赖、等待与显式编排。
- [Kernel 执行契约](src/dispatcher_sdk/execution_kernel/README.md)：隔离、超时、取消和持久化机制。
- [恢复、重试与外部副作用](docs/SDK_RECOVERY.md)：中断后如何判断、等待和恢复。
- [脚本执行与应用通知](docs/SDK_SCRIPT_WAKEUPS.md)：脚本、日志、回调和通知重试。
- [可靠审计与业务放行](docs/SDK_INTEGRATION_FAQ.md)：独立游标、落盘后确认、终态排空和依赖结果检查。
- [公开 API 与兼容性](docs/PUBLIC_API.md)：接口、平台差异和升级约束。

开发和测试见 [CONTRIBUTING.md](CONTRIBUTING.md)，漏洞报告见
[SECURITY.md](SECURITY.md)，源码来源见 [PROVENANCE.md](PROVENANCE.md)。
项目采用 [Apache-2.0](LICENSE) 许可证。
