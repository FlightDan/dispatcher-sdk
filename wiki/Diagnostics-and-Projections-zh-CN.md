# 诊断与事件投影

[English](Diagnostics-and-Projections.md)

用下面的接口检查当前部署、消费事件，以及排查任务未执行或取消后的状态：

| 能力 | 入口 |
| --- | --- |
| 实际导入的包、源码与存储兼容性 | `dispatcher_sdk.runtime_identity(...)` |
| 先持久化、后 ACK 的事件消费 | `ProjectionConsumer(...).drain(...)` |
| Run 当前无可领取工作的原因 | `sdk.inspect_work_availability(run_id)` |
| 取消阶段、清理状态和恢复身份 | `sdk.inspect_cancellation(run_id)` |

投影回调必须在幂等写入事务提交后返回 `persisted` 或 `already_present`。未完成 ACK 的页会重放，处理失败的事件会阻塞该页。drain 的目标高水位固定，但 Run 持续并发更新仍可能让 ACK 因版本冲突而失败。

诊断查询不会同步或修改 Run。缺少证据的字段保留 unknown；跨库读取也有快照一致性限制。工作诊断有 Effect 扫描上限；超限时计数为未知，不是零。

为 Runtime 显式配置 `cancellation_journal_path` 和 `source_id` 可以持久保存取消证据。回执存放在独立的 schema 1 数据库中，核心存储不会自动迁移。本地进程树清理需要同一执行代际的 Linux subreaper 或 Windows Job 证明。取消 Task 不会自动结束 Run。

完整说明见 [API 指南](../docs/SDK_DIAGNOSTICS_AND_PROJECTIONS.md)、[回执存储设计](../docs/CANCELLATION_EVIDENCE.md)、[投影示例](../examples/projection_consumer.py)和[诊断示例](../examples/capability_diagnostics.py)。
