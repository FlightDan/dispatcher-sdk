# 快速开始

[English](Quick-Start.md) | [简体中文](Quick-Start-zh-CN.md) | [首页](Home-zh-CN.md)

使用包含 0.6 预览版代码的仓库，并确保 Python 版本为 3.10+。
在仓库根目录运行：

```sh
python -m venv .venv
```

在 POSIX 系统上使用 `source .venv/bin/activate` 激活环境；在 Windows PowerShell
中使用 `.venv\Scripts\Activate.ps1`。激活后运行：

```sh
python -m pip install .
python examples/kernel_task.py
```

预期输出：

```text
{'total': 60}
```

[该示例](../examples/kernel_task.py) 会提交任务，关闭 Runtime，再打开同一个
SQLite 数据库并执行队列中的任务。示例使用的临时存储会在退出时删除；实际应用
需要把数据保存在固定路径，才能在重启后恢复。

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

从完整的[原子提交示例](../docs/TASK_SUBMISSION.md)开始。该示例会创建 Run、
提交可信函数，并演示响应丢失后的原样重放。请从该示例复制代码，以保持参数与
当前版本一致。下一步阅读[接入指南](Integration-Guide-zh-CN.md)。
