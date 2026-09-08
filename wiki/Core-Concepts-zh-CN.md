# 核心概念

[English](Core-Concepts.md) | [简体中文](Core-Concepts-zh-CN.md) | [首页](Home-zh-CN.md)

| 概念 | 职责 |
| --- | --- |
| Handler | 应用提供的函数，接收 payload 和执行上下文。 |
| Kernel / Runtime | Kernel 是执行状态的最终记录；Runtime 运行已注册的处理器。 |
| 执行命令 | 描述一次执行，指定执行身份、处理器绑定、输入、超时和重试策略。 |
| Run / task | Run 组织一组应用工作；task 记录依赖关系和业务尝试。 |
| Host | 在宿主进程保持运行时，驱动任务执行和结果投递。 |
| Effect | 保存外部操作的意图和回执，供应用显式恢复。 |
| Recovery / generation | Recovery 重新打开已结束的 Run；generation 用来区分恢复前后的工作。 |
| 通知 / 收件箱 | 通知把结果投递给应用；持久化收件箱负责接收通知并去重。 |

最小流程从创建 Run 开始。应用随后记录任务和派发意图，投递命令，执行任务，再同步
结果。应用校验结果后，显式决定下一步操作，或者结束 Run。

`submit_task()` 只保存任务意图，不会运行处理器。手动循环需要使用 `flush()`、
`runtime.run_once()` 和 `sync()`；`OrchestratorHost` 会驱动后台循环。仅创建
`Orchestrator` 不会启动调度器。

执行成功、输出符合结构要求、业务验收通过，分别是三个独立判断。
任务派发前，依赖必须已经结束（结算），但结果是否可接受仍由应用判断。
成功不会自动派发后继任务或结束 Run。未释放的 wait 会阻止结束 Run，
但不会自动阻止任务派发。

请求重放、执行重试、业务返工和通知重投需要分别处理。
重放请求沿用原始身份和内容；如果要改变请求内容，就需要新的业务决策和身份。
结果不确定的外部操作，应先根据证据核对，再决定是否重试。

Effect 恢复和 Run 恢复处理的问题不同。Effect 恢复用于核定一次结果不确定的外部操作。
Run 恢复保留原有身份和历史，再以新的 generation 重新打开失败或取消的 Run。
事件、尝试、结果和通知都会记录产生它们的 generation，因此迟到的第 0 代数据不会
与恢复后的新工作混在一起。

详细规则见 [SDK 契约](../docs/SDK.md)、[恢复指南](../docs/SDK_RECOVERY.md)
和[输出校验](../docs/SDK_OUTPUT_CONTRACTS.md)。
