# 常见问题

[English](Troubleshooting.md) | [简体中文](Troubleshooting-zh-CN.md) | [首页](Home-zh-CN.md)

| 现象 | 下一步检查 |
| --- | --- |
| 提交成功但任务不执行 | 保持 Host 运行，或显式 flush、执行和 sync；检查命令投递错误与处理器兼容性。 |
| `run_once()` 没取到任务 | 检查租约、`next_attempt_at`、可执行任务和处理器可用性，不能据此认定停滞。 |
| `flush()` 返回零 | 查看待投递记录及最后错误；返回零不代表队列为空。 |
| 任务成功但 Run 仍在运行 | 校验业务结果，释放相应等待条件，然后显式结束 Run。 |
| 后继任务没启动 | 检查依赖是否结算且业务验收通过，再显式派发。 |
| `CommandConflict` | 原样重放原始请求，包括预期版本；修改内容需要新的决策身份。 |
| `RevisionConflict` | 读取最新状态，重新计算决策并使用新的命令身份。 |
| 重复通知 | 通知至少投递一次；确认前按稳定身份持久化去重。 |
| `recovery_required` | 检查未决 Effect，依据外部证据核对后再裁决。 |
| 旧数据库被拒绝 | 按升级指南处理，不要修改 schema 元数据绕过兼容性检查。 |

精确规则与恢复流程见[任务提交](../docs/TASK_SUBMISSION.md)、
[恢复](../docs/SDK_RECOVERY.md)、[收件箱](../docs/NOTIFICATION_INBOX.md)
和[存储](../docs/STORAGE_AND_UPGRADES.md)。

反馈问题时请提供 SDK 版本或 commit、Python 版本、平台、隔离模式、
相关身份与状态以及最小复现，并移除凭据和私有数据。
普通问题提交到 [GitHub Issues](https://github.com/FlightDan/dispatcher-sdk/issues)，
漏洞请使用[安全报告渠道](../SECURITY.md)。
