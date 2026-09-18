# 快速开始

[English](Quick-Start.md) | [简体中文](Quick-Start-zh-CN.md) | [首页](Home-zh-CN.md)

使用 0.7 开发版代码，并确保 Python 版本为 3.10+。
在仓库根目录运行：

```sh
python -m venv .venv
```

在 POSIX 系统上使用 `source .venv/bin/activate` 激活环境；在 Windows PowerShell
中使用 `.venv\Scripts\Activate.ps1`。激活后运行：

```sh
python -m pip install .
python examples/managed_task.py
```

预期输出：

```text
42
```

[该示例](../examples/managed_task.py) 使用 `Dispatcher` 管理 Runtime、后台 Host、
部署检查和通知收件箱。它用稳定的请求 ID 提交一个任务，并等待持久化结果。
示例为了方便运行使用临时目录；实际应用应改用固定路径。

## 执行脚本并接收结果

在 Linux 上运行：

```sh
python examples/sdk_script_wakeup.py
```

预期输出：

```text
Wake conversation-42: succeeded
report ready
```

[脚本示例](../examples/sdk_script_wakeup.py) 会提交任务并在后台执行。回调会持久化
收到的通知，示例随后读取 stdout。示例只打印消息；实际应用需要让收件箱消费者读取
这些通知，并据此继续 Agent 流程。后台执行期间必须保持宿主运行。原生 Windows
的运行要求和已记录的验证范围详见[平台状态](../docs/WINDOWS_RUNTIME.md)。

## 接入自己的任务

先看[托管任务](Managed-Tasks-zh-CN.md)。需要任务依赖、等待条件或显式 Run 决策时，
再使用底层的[原子提交指南](../docs/TASK_SUBMISSION.md)。接着可阅读
[接入指南](Integration-Guide-zh-CN.md)。
