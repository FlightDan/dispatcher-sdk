# 常见问题

[English](Troubleshooting.md) | [简体中文](Troubleshooting-zh-CN.md) | [首页](Home-zh-CN.md)

| 现象 | 下一步检查 |
| --- | --- |
| 提交成功但任务不执行 | 保持 Host 运行，或手动依次调用 `flush()`、`runtime.run_once()` 和 `sync()`；检查命令投递错误与处理器兼容性。 |
| `Dispatcher` 拒绝启动 | 查看 `DeploymentMismatchError.report`；未完成任务仍需要原 handler 部署。 |
| `task.wait(timeout=...)` 超时 | 结束的是调用方等待。先用 `task.observe()` 查看执行状态和时限，再决定任务是否应继续。 |
| `run_once()` 没取到任务 | 检查任务租约、`next_attempt_at`、是否有可执行任务，以及处理器是否可用。一次 `run_once()` 没取到任务，不能据此认定系统停滞。 |
| `flush()` 返回零 | 查看待投递记录和最后一条错误；返回零不等于队列为空。 |
| 任务成功但 Run 仍在运行 | 先校验业务结果，释放相应的 `wait` 条件，再显式结束 Run。 |
| 后继任务没启动 | 检查依赖是否已结算、业务验收是否通过，再显式派发。 |
| `CommandConflict` | 原样重放原始请求，包括预期版本；修改内容需要新的决策身份。 |
| `RevisionConflict` | 读取最新状态，重新计算决策，再使用新的命令身份。 |
| 重复通知 | 通知至少投递一次，同一通知可能重复到达；确认前按稳定身份持久化去重。 |
| `recovery_required` | 检查未决 Effect，根据外部证据核对结果后再作决定。 |
| 重启后取消报告仍显示本地清理未知 | 确保 Kernel 绑定的 settlement journal 可读取，并检查 `process_cleanup` note 是否匹配 execution ID、attempt 和 fence。缺失或格式错误的证据仍是未知。 |
| 旧数据库被拒绝 | 按升级指南处理，不要通过修改 schema 元数据绕过兼容性检查。 |
| 恢复后的快照仍是只读 | 文件恢复和执行激活是两步。按本地激活流程操作，不要手工删除只读标记。 |
| 本地激活提示源数据已变化 | 快照创建后原库又有新状态。先核对这些事实；SDK 不会自动运行较旧副本。 |
| 沙箱 create/start 结果不确定 | 按 operation key 和 provider 记录对账，不要直接重建或重发。 |
| Windows 结果文件读取出现 `PermissionError` | 临时共享拒绝只使用原 watchdog 截止时间。明确的访问拒绝立即失败；清理后仍无法读取时，保留原始权限错误。 |
| 已准入的子任务等待遇到 Kernel 写锁 | 检查原截止时间、父租约和时钟 guard。结果观察使用事实读取；待完成的结果发布仍是单独的恢复义务，不能靠重新执行处理器发布结果。 |
| 超时等待看到已取消子任务的 `attempt=0` / `fence=0` | 这是从未领取的合法身份。事实回读拒绝交付并保留原等待错误，不将这个身份误报为祖先数据损坏。 |
| 重放 observation batch | 匹配已提交的相同或更新 sequence 时，无需写锁并返回 `False`。缺少证据仍需在原截止时间内原子准入；永久存储错误仍应报错。 |
| 最后一个活动批次已写入，但进程观测不完整 | 检查关闭回执中的进程采集完成状态、线程状态和采集错误。批次已写入或 source 已关闭不能证明进程采集完整；之后等待线程退出也不能提升原回执的确认状态。 |
| 沙箱一直等待清理 | 查看 journal 和 provider，再执行有界恢复。资源销毁不能替代外部业务副作用裁决。 |

具体规则和恢复流程见[任务提交](../docs/TASK_SUBMISSION.md)、
[恢复](../docs/SDK_RECOVERY.md)、[收件箱](../docs/NOTIFICATION_INBOX.md)、
[存储](../docs/STORAGE_AND_UPGRADES.md)、[本地恢复](../docs/LOCAL_RECOVERY.md)
和[沙箱运行时](../docs/SANDBOX_RUNTIME.md)。观测缺口和停滞通知的说明见
[执行观测与监督](../docs/EXECUTION_OBSERVABILITY.md)。

反馈问题时，请提供 SDK 版本或 commit、Python 版本、平台、隔离模式、相关身份和状态，
以及最小复现（能重现问题的最小示例）。[公共观测消费者](../examples/sdk_observability_acceptance.py)
会保留子调用和进度调用的原始异常堆栈、SQLite 错误码和原有预算。使用
`--evidence-dir <新的空目录>` 指定证据目录；诊断记录不会重试失败调用。
请先移除凭据和私有数据。
一般问题请提交到 [GitHub Issues](https://github.com/FlightDan/dispatcher-sdk/issues)，
漏洞请使用[安全报告渠道](../SECURITY.md)。
