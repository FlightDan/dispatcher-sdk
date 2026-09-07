# 接入指南

[English](Integration-Guide.md) | [简体中文](Integration-Guide-zh-CN.md) | [首页](Home-zh-CN.md)

按应用需要，选择最少的一组接入步骤。

开始接入真实工作前，请先阅读[接入工程原则](Engineering-Principles-zh-CN.md)。
其中会说明版本身份（实际运行的版本和部署标识）、受监督生命周期（持续记录运行状态）、
证据等级（结论由哪类验证支持）、候选冻结和安全发现，也不会把业务策略塞进 SDK。

| 目标 | 先读 | 可运行示例 |
| --- | --- | --- |
| 持久化执行函数 | [SDK](../docs/SDK.md) 与[公共 API](../docs/PUBLIC_API.md) | [重开后执行排队任务](../examples/kernel_task.py) |
| 使用可重放身份提交任务 | [原子任务提交](../docs/TASK_SUBMISSION.md) | 该指南中的完整示例 |
| 执行脚本并通知 Agent | [脚本与唤醒](../docs/SDK_SCRIPT_WAKEUPS.md)、[持久化收件箱](../docs/NOTIFICATION_INBOX.md) | [脚本回调](../examples/sdk_script_wakeup.py) |
| 编排任务依赖 | [SDK 操作](../docs/SDK.md) | [依赖任务](../examples/dependent_tasks.py) |
| 核对中断的外部操作 | [恢复](../docs/SDK_RECOVERY.md) | [Effect 恢复](../examples/effect_recovery.py) |
| 校验 LLM 输出并安排修复 | [输出契约](../docs/SDK_OUTPUT_CONTRACTS.md) | 按该指南的应用校验流程接入 |
| 消费审计事件 | [接入 FAQ](../docs/SDK_INTEGRATION_FAQ.md) | [持久化审计](../examples/durable_audit.py) |
| 使用远程执行 | [沙箱运行时](../docs/SANDBOX_RUNTIME.md)、[适配器](../docs/SANDBOX_ADAPTERS.md) | 按指南配置对应服务 |

## 接入实际业务前

使用固定的数据库和日志路径，选择适用的隔离模式，并为排队任务准备匹配的处理器部署。
每次决策都使用稳定身份，保留原始请求，方便重放。

回调完成持久化接收和去重（同一通知重复到达时只处理一次）后应尽快返回，
之后由消费者处理收件箱里的通知。每个外部写入都需要自己的幂等或核对方案。
进程执行本身不会限制文件或网络访问。

复用旧存储前先看[存储与升级](../docs/STORAGE_AND_UPGRADES.md)：
0.6 不会自动迁移旧 Orchestrator 数据库。
部署限制见 [Windows 状态](../docs/WINDOWS_RUNTIME.md)
和 [Linux 清理验证](../docs/PROCESS_CLEANUP_VALIDATION.md)。

由 Agent 实现接入时，请从英文 [DocsforAgents](../DocsforAgents/README.md) 开始。
