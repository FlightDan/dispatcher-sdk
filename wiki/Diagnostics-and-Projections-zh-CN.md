# 诊断与事件投影

[English](Diagnostics-and-Projections.md) | [简体中文](Diagnostics-and-Projections-zh-CN.md) | [首页](Home-zh-CN.md)

用下面的接口检查当前部署、消费事件，也可以排查任务为什么未执行以及取消后的状态：

| 能力 | 入口 |
| --- | --- |
| 实际导入的包、源码与存储兼容性 | `dispatcher_sdk.runtime_identity(...)` |
| 先持久化、后 ACK 的事件消费 | `ProjectionConsumer(...).drain(...)` |
| Run 当前无可领取工作的原因 | `sdk.inspect_work_availability(run_id)` |
| 取消阶段、清理状态和恢复身份 | `sdk.inspect_cancellation(run_id)` |

投影回调必须先提交幂等写入事务，再返回 `persisted` 或 `already_present`。
回调使用由 `source_id`、`run_id` 和 `sequence` 组成的稳定事件身份去重，并在同一事务中
提交去重记录和业务写入。`persisted` 表示本次已经写入；`already_present` 表示这个事件
已在此前的事务中处理并持久化。整页事件都确认后，消费者才会 ACK 这一页。
没有完成 ACK 的页会重放，处理失败的事件会阻塞该页，不能跳过。
`drain` 的目标高水位（本轮要处理到的事件位置）是固定的，但 Run 持续并发更新时，ACK 仍可能因版本冲突而失败。

诊断查询不会同步或修改 Run。字段缺少证据时保留 `unknown`（未知，不代表零或否定）；跨库读取也受快照一致性限制。
工作诊断有 Effect 扫描上限；超过上限时计数为未知，不是零。

为 Runtime 显式配置 `cancellation_journal_path` 和 `source_id`，可以持久保存取消证据（之后用来核对取消结果的记录）。
回执存放在独立的 schema 1（数据结构版本 1）数据库中，核心存储不会自动迁移。
只有同一执行代际（相同的 attempt/fence）留下的 Linux subreaper 或 Windows Job 清理记录，
才能证明本地进程树已经清理。
取消 Task 不会自动结束 Run。

完整说明见 [API 指南](../docs/SDK_DIAGNOSTICS_AND_PROJECTIONS.md)、[回执存储设计](../docs/CANCELLATION_EVIDENCE.md)、[投影示例](../examples/projection_consumer.py)和[诊断示例](../examples/capability_diagnostics.py)。
