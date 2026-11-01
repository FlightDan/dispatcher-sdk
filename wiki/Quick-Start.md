# Quick start

[English](Quick-Start.md) | [简体中文](Quick-Start-zh-CN.md) | [Home](Home.md)

Use the source revision for the published 0.7.2 release with Python 3.10 or later.
These commands install the checkout you are currently using; the improvement-development
tree is the unreleased 0.7.3.dev1 candidate. See the [status page](Improvement-Status.md)
for its acceptance limits. From the 0.7.2 source root:

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

The [example](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/managed_task.py) uses `Dispatcher` to own the Runtime,
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

The [script example](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/examples/sdk_script_wakeup.py) submits a task and runs it
in the background. Its callback durably accepts the notification, and the
example reads stdout. Connect your application's inbox consumer to the logic
that continues the Agent workflow, and keep the host alive while work is pending.
For native Windows
requirements and recorded validation scope, see
[platform status](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/WINDOWS_RUNTIME.md).

## Add your own task

Start with [managed tasks](Managed-Tasks.md). Use the lower-level
[atomic submission guide](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/TASK_SUBMISSION.md) when you need dependencies,
waits or explicit Run decisions. Then read the [integration guide](Integration-Guide.md).
