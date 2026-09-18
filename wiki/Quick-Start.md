# Quick start

[English](Quick-Start.md) | [简体中文](Quick-Start-zh-CN.md) | [Home](Home.md)

Use Python 3.10+ and the 0.7 development checkout. From its root:

```sh
python -m venv .venv
```

Activate with `source .venv/bin/activate` on POSIX, or
`.venv\Scripts\Activate.ps1` in Windows PowerShell. Then:

```sh
python -m pip install .
python examples/managed_task.py
```

Expected output:

```text
42
```

The [example](../examples/managed_task.py) uses `Dispatcher` to own the Runtime,
background Host, deployment check and notification inbox. It submits one task
with a stable request ID and waits for the persisted result. The temporary
directory keeps the example self-contained; use a fixed path in an application.

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

Start with [managed tasks](Managed-Tasks.md). Use the lower-level
[atomic submission guide](../docs/TASK_SUBMISSION.md) when you need dependencies,
waits or explicit Run decisions. Then read the [integration guide](Integration-Guide.md).
