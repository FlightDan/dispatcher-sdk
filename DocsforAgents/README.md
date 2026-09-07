# Dispatcher SDK: docs for agents

Use this directory when implementing an application with Dispatcher SDK. Start
with the task below, read its linked contract, and adapt the existing example.
Detailed API documentation lives in [docs/](../docs/SDK.md); these pages provide
navigation and integration checks, not a separate API specification.

Dispatcher executes and records work. Your application supplies handlers,
validates business results, chooses subsequent tasks, and continues conversations.
The SDK does not invoke a model or choose business routing.

## Choose a task

| Your task | Read | Runnable reference |
| --- | --- | --- |
| Run a Python function and retain queued work across restart | [Integration](INTEGRATION.md), [public API](../docs/PUBLIC_API.md) | [kernel_task.py](../examples/kernel_task.py) |
| Submit one task with stable replay identity | [Atomic task submission](../docs/TASK_SUBMISSION.md) | Complete example in that guide |
| Execute a script and wake a conversation | [Scripts and notifications](../docs/SDK_SCRIPT_WAKEUPS.md), [notification inbox](../docs/NOTIFICATION_INBOX.md) | [sdk_script_wakeup.py](../examples/sdk_script_wakeup.py) |
| Dispatch dependent tasks or arrange business rework | [SDK operations](../docs/SDK.md), [output contracts](../docs/SDK_OUTPUT_CONTRACTS.md) | [dependent_tasks.py](../examples/dependent_tasks.py) |
| Recover an interrupted external operation | [Recovery and retry](../docs/SDK_RECOVERY.md) | [effect_recovery.py](../examples/effect_recovery.py) |
| Persist an audit consumer without losing events | [Integration FAQ](../docs/SDK_INTEGRATION_FAQ.md) (Chinese) | [durable_audit.py](../examples/durable_audit.py) |
| Bound a trusted task's process lifetime | [Public API and isolation](../docs/PUBLIC_API.md) | [isolation_timeout.py](../examples/isolation_timeout.py) (Linux) |
| Execute through a remote sandbox | [Sandbox runtime](../docs/SANDBOX_RUNTIME.md), [adapters](../docs/SANDBOX_ADAPTERS.md) | Validation commands in those guides |
| Upgrade, back up, or grow a persistent deployment | [Storage and upgrades](../docs/STORAGE_AND_UPGRADES.md) | Preflight and backup examples in that guide |

Before submitting an integration, review [contracts and pitfalls](CONTRACTS.md)
and run the applicable [verification steps](VERIFICATION.md).

## Reading and maintenance rules

- Import from the public `dispatcher_sdk.execution_kernel` and
  `dispatcher_sdk.orchestrator` interfaces documented in
  [PUBLIC_API.md](../docs/PUBLIC_API.md). Do not build an integration on private
  modules or write directly to SDK-owned tables.
- Read the documentation from the same checkout or release as the installed
  SDK. Check [storage compatibility](../docs/STORAGE_AND_UPGRADES.md) before
  opening an existing deployment with a different version.
- Keep API definitions and detailed behavior in `docs/`. When changing a
  contract, update its canonical guide and examples, then adjust these links
  and summaries as needed.
- For changes to the SDK itself, follow [CONTRIBUTING.md](../CONTRIBUTING.md).

