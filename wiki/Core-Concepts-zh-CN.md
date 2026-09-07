# 核心概念

[English](Core-Concepts.md) | [简体中文](Core-Concepts-zh-CN.md) | [首页](Home-zh-CN.md)

| 概念 | 职责 |
| --- | --- |
| Handler | 应用函数，接收 payload 和执行上下文。 |
| Kernel / Runtime | Kernel 保存执行权威状态；Runtime 执行已注册的处理器。 |
| 执行命令 | 指定执行身份、处理器绑定、输入、超时和重试策略。 |
| Run / task | Run 组织应用工作；任务记录依赖和业务尝试。 |
| Host | 在宿主进程存活期间驱动执行和投递。 |
| Effect | 保存外部操作意图和回执，用于显式恢复。 |
| 通知 / 收件箱 | 向应用投递结果；持久化收件箱负责接收去重。 |

最小流程从创建 Run 开始，随后记录任务与派发意图、投递命令、执行任务并同步结果。
应用校验结果后，显式决定下一步操作或结束 Run。

`submit_task()` 保存意图，不会执行处理器。手动循环使用 `flush()`、
`runtime.run_once()` 和 `sync()`；`OrchestratorHost` 驱动后台循环。
仅创建 Orchestrator 不会启动调度器。

执行成功、输出结构合法、业务验收通过是三个独立判断。
派发前依赖必须已结算，但结果是否可接受仍由应用判断。
成功不会自动派发后继任务或结束 Run。未释放的 wait 会阻止结束 Run，
不会自动阻止任务派发。

请求重放、执行重试、业务返工和通知重投需要分别处理。
重放请求沿用原始身份和内容；新的业务工作需要新的决策和身份。
结果不确定的外部操作需要依据证据核对，不能盲目重试。

详细规则见 [SDK 契约](../docs/SDK.md)、[恢复指南](../docs/SDK_RECOVERY.md)
和[输出校验](../docs/SDK_OUTPUT_CONTRACTS.md)。
