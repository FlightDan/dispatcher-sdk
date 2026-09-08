# Core concepts

[English](Core-Concepts.md) | [简体中文](Core-Concepts-zh-CN.md) | [Home](Home.md)

| Concept | Responsibility |
| --- | --- |
| Handler | Application function that receives payload and execution context. |
| Kernel / Runtime | Kernel stores execution authority; Runtime executes registered handlers. |
| Execution command | Identifies one execution, handler binding, payload, timeout and retry policy. |
| Run / task | A Run groups application work. A task records its dependencies and business attempts. |
| Host | Drives execution and delivery while its process remains alive. |
| Effect | Records an external operation's intent and receipt for explicit recovery. |
| Recovery / generation | Recovery resumes a terminal Run; generation separates old work from work created after the reopen. |
| Notification / inbox | Delivers outcomes to the application; a durable inbox deduplicates receipt. |

A minimal workflow creates a Run, records a task and dispatch intent, delivers the
command, executes it, then synchronizes results. The application validates the
result and explicitly chooses the next operation or finishes the Run.

`submit_task()` persists intent; it does not execute the handler. Manual loops use
`flush()`, `runtime.run_once()` and `sync()`. `OrchestratorHost` drives the background
loop. Creating an Orchestrator alone starts no scheduler.

Execution success, valid output structure and business acceptance are separate.
Dependencies must be settled before dispatch, but the application must check
whether their outcomes are acceptable. Success does not automatically dispatch a
successor or finish a Run. An open wait prevents finish; it does not automatically
block task dispatch.

Handle submission replay, execution retries, business rework and notification
redelivery separately. Replay requests with their original identity and content;
use a new decision and identity for new business work. Reconcile uncertain
external effects using evidence before retrying them.

Effect recovery and Run recovery solve different problems. Effect recovery
settles one uncertain external operation. Run recovery retains the Run's
identity and history, then reopens a failed or cancelled Run under its next
generation. Events, attempts, results and notifications carry the generation
that produced them, so late data from generation 0 remains distinguishable from
new work.

See [SDK contracts](../docs/SDK.md), [recovery](../docs/SDK_RECOVERY.md) and
[output validation](../docs/SDK_OUTPUT_CONTRACTS.md) for the detailed rules.
