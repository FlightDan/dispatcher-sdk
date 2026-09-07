# Quick start

[English](Quick-Start.md) | [简体中文](Quick-Start-zh-CN.md) | [Home](Home.md)

Use Python 3.10+ and a checkout containing the 0.6 preview. From its root:

```sh
python -m venv .venv
```

Activate with `source .venv/bin/activate` on POSIX, or
`.venv\Scripts\Activate.ps1` in Windows PowerShell. Then:

```sh
python -m pip install .
python examples/kernel_task.py
```

Expected output:

```text
{'total': 60}
```

The [example](../examples/kernel_task.py) submits work, closes the Runtime,
reopens the same SQLite database and executes the queued task. Its temporary
storage is deleted on exit. Use persistent paths for real application recovery.

## Run a script and receive its result

On Linux, run:

```sh
python examples/sdk_script_wakeup.py
```

Expected output:

```text
Wake conversation-42: succeeded
report ready
```

The [script example](../examples/sdk_script_wakeup.py) submits a task, runs it in
the background, uses a callback to durably accept the notification, and reads stdout. It prints a
message; connect your application's inbox consumer to the logic that continues
the Agent workflow. Keep the host alive for background work. For native Windows
requirements and recorded validation scope, see
[platform status](../docs/WINDOWS_RUNTIME.md).

## Add your own task

Start with the complete [atomic submission example](../docs/TASK_SUBMISSION.md).
It creates a Run, submits a trusted function and demonstrates exact replay after
a lost response. Copy the code from that example to keep its parameters consistent
with your checkout, then read the [integration guide](Integration-Guide.md).
