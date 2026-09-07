# 快速开始

[English](Quick-Start.md) | [简体中文](Quick-Start-zh-CN.md) | [首页](Home-zh-CN.md)

使用 Python 3.10+ 和包含 0.6 预览版的代码。在仓库根目录运行：

```sh
python -m venv .venv
```

POSIX 使用 `source .venv/bin/activate` 激活；Windows PowerShell 使用
`.venv\Scripts\Activate.ps1`。随后运行：

```sh
python -m pip install .
python examples/kernel_task.py
```

预期输出：

```text
{'total': 60}
```

[该示例](../examples/kernel_task.py) 提交任务、关闭 Runtime，随后重新打开
同一 SQLite 数据库并执行排队任务。临时存储会在退出时删除；
实际应用需要保留固定路径的数据，才能在重启后恢复。

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

[脚本示例](../examples/sdk_script_wakeup.py) 提交任务并在后台执行，由回调持久化接收通知，
再读取 stdout。示例只打印消息；应用需要将收件箱消费者接到继续 Agent 流程的逻辑。
后台执行期间必须保持宿主运行。原生 Windows 的运行要求和已记录的验证范围
详见[平台状态](../docs/WINDOWS_RUNTIME.md)。

## 接入自己的任务

从完整的[原子提交示例](../docs/TASK_SUBMISSION.md) 开始：创建 Run、
提交可信函数，并演示响应丢失后的原样重放。请从该示例复制代码，
保证参数与当前版本一致。下一步阅读[接入指南](Integration-Guide-zh-CN.md)。
