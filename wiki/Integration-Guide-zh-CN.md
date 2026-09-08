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
| 原地继续失败或取消的 Run | [同 Run 恢复](../docs/SDK.md#reopen-a-failed-run-in-place) | SDK 指南中的代码 |
| 校验 LLM 输出并安排修复 | [输出契约](../docs/SDK_OUTPUT_CONTRACTS.md) | 按该指南的应用校验流程接入 |
| 消费审计事件 | [接入 FAQ](../docs/SDK_INTEGRATION_FAQ.md) | [持久化审计](../examples/durable_audit.py) |
| 使用远程执行 | [沙箱运行时](../docs/SANDBOX_RUNTIME.md)、[适配器](../docs/SANDBOX_ADAPTERS.md) | 按指南配置对应服务 |

## 接入实际业务前

使用固定的数据库和日志路径，选择适用的隔离模式，并为排队任务准备匹配的处理器部署。
每次决策都使用稳定身份，保留原始请求，方便重放。

回调完成持久化接收和去重（同一通知重复到达时只处理一次）后应尽快返回，
之后由消费者处理收件箱里的通知。每个外部写入都需要自己的幂等或核对方案。
进程执行本身不会限制文件或网络访问。

## 重新打开已结束的 Run

重新打开失败或取消的 Run 前，先调用 `inspect_reopen()`。它会列出尚未结束的尝试、
待投递数据、仍持有租约的通知，以及已经存在的 continuation。`reopen_run()`
会在提交决定前再次检查这些事实，保留原来的 `run_id` 和历史，并递增 Run 的
`generation`。

恢复后，修改 Run 或提交新任务时需要传入 `expected_generation`。新尝试必须使用
新的 execution identity 和 idempotency identity，处理器绑定也必须匹配目标部署。
取消的 Run 还需要单独的授权记录。成功的 Run 或已经有 continuation 的 Run
不能重新打开。

恢复进度会持久化。进程重启后，Host 可以继续处理 prepared 或 committed 记录。
如果 Orchestrator 数据库已经使用 schema 2，请先运行
`Orchestrator.upgrade_schema(path)`，再用当前版本打开。该升级需要显式执行，
可以重复运行，并会保留 Run 历史。

复用旧存储前先看[存储与升级](../docs/STORAGE_AND_UPGRADES.md)：
0.6 不会自动迁移旧 Orchestrator 数据库。
部署限制见 [Windows 状态](../docs/WINDOWS_RUNTIME.md)
和 [Linux 清理验证](../docs/PROCESS_CLEANUP_VALIDATION.md)。

由 Agent 实现接入时，请从英文 [DocsforAgents](../DocsforAgents/README.md) 开始。
