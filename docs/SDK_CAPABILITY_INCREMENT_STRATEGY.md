# A01 至 A04 SDK 能力增量改进策略

日期：2026-09-07。状态：A01 至 A04 已实现，最终集成验证通过，尚未发布。参见[验证记录](CAPABILITY_VALIDATION.md)。

策略制定后，用户明确要求“执行”。实现保留现有公共 API，优先新增能力，不自动迁移既有存储；必要的 schema 变更必须另行设计兼容路径。此次授权不包含发布或迁移现有部署。

## 1. 目标与依据

将 ModPort 的 A01 至 A04 上游需求转为可独立验收的 SDK 增量：运行身份与兼容性预检、可靠事件投影消费、无可领取工作的诊断、取消与恢复报告。

需求来源：ModPort `sdkguide/08-upstream-improvement-backlog.md` 的 A01 至 A04；关联任务 ID 为 `01a07c4e-e9a7-7f50-a451-4f0f013f85d9`。本文件保留独立可用的需求和验收定义，不要求发布后的 SDK 用户拥有 ModPort 仓库。

当前源码声明版本为 0.6.0；这不证明环境安装版本或已发布版本。实现依据是以下源码与现有契约：

| 能力 | 现有基础 | 实际增量 |
| --- | --- | --- |
| A01 | [inspect_storage](../src/dispatcher_sdk/storage.py)、Runtime registry/handler revision、[存储预检契约](STORAGE_AND_UPGRADES.md) | 统一运行身份，拆分存储状况与读取/执行/恢复判定 |
| A02 | [observe/read_events/acknowledge_events](../src/dispatcher_sdk/orchestrator/engine.py)、[NotificationInbox](../src/dispatcher_sdk/orchestrator/inbox.py) | 通用投影消费循环、显式持久化确认、重放与固定高水位 drain |
| A03 | [Kernel 调度实现](../src/dispatcher_sdk/execution_kernel/_sqlite_execution.py)、Run tasks/waits、delivery/result outbox | 只读聚合原因，暴露调度所需事实及观察边界 |
| A04 | [Runtime.cancel](../src/dispatcher_sdk/execution_kernel/runtime.py)、[inspect_recoveries](../src/dispatcher_sdk/orchestrator/recovery.py)、取消 outbox 与 sandbox journal | 按执行代际关联取消阶段和证据；补齐重启后可读的清理回执 |

## 2. 统一设计约束

- SDK 提供事实、身份、投递与并发控制原语；ModPort 定义停滞、业务成功、Minecraft 验收和 Agent 策略。
- 公共报告采用类型化结构、稳定 reason code 和可序列化表示；本文接口名称均为候选，最终签名在契约评审时冻结。
- 报告记录来源、观察时间及适用 revision/fence。独立数据库的快照不能包装成一个原子快照；有界重读失败时显式报告冲突或不完整。
- `unknown`、`not_checked`、`not_applicable` 与确认成功/失败分开表示。缺失数据不得解释为成功、零计数或外部动作未发生。
- 只读诊断不构造会初始化存储的 writer，不调用 flush、sync、reap、恢复或清理操作，也不更新持久化时钟、租约及游标。
- 预检仅解释观察时的兼容条件，真正执行仍须经过现有 schema、绑定、revision 和 fence 校验，避免检查后状态变化绕过保护。
- 新文档独立落盘，保留工作区既有未提交改动；原有实施计划不重写成此次计划。

## 3. A01：运行身份与兼容性预检（P0）

### 契约与实现策略

在 `inspect_storage` 上新增身份聚合入口，例如 `runtime_identity(...)`，保留原函数及其现有返回语义。

报告分为三个部分，避免用一个 `compatible` 布尔值承担所有判断：

1. 运行身份：distribution 元数据版本、实际模块来源、源码/构建身份及其证据来源、公共 contract 版本、registry 和 per-handler binding。
2. 存储事实：各组件路径、存在性、schema、完整性、活动工作及绑定检查情况；明确 missing、legacy/unsupported、damaged、recognized 等状态。
3. 能力判定：分别给出可读取、可执行、可恢复的 supported/unsupported/unknown 结论与原因。绑定未检查时不能确认可恢复；缺失路径不能判为已有 Run 可读取。

复用现有 schema/binding 检查。wheel 与源码 checkout 都须可报告身份；源码身份优先来自可验证的构建信息。若缺少证据则返回 unknown，不能仅凭目录名猜版本，也不能把安装元数据直接当作被导入源码版本。构建身份可随包提供，不要求写入业务数据库。

durability 分开报告调用方配置、可观察的 journal mode、无法观察的其他连接 synchronous；不认证硬件持久化保证。

旧存储只支持明确列出的只读格式识别/摘要能力；无 reader 的格式报告 unsupported。保留旧部署读取历史数据的路径，不将“Run 已终态”作为新 SDK 支持任意旧格式的依据。

### 验收与完成条件

- 安装 0.5.1 元数据而导入可识别的 0.6.0 源码时明确报告不一致；源码身份不可识别时明确报告无法验证。
- 同 SemVer、不同源码/handler binding 能被区分；未提供 registry 的检查不输出肯定的恢复结论。
- missing、损坏、已支持的旧摘要读取、未知旧 schema、活动不兼容存储分别有测试。
- 旧终态 Run 的只读检查不授予恢复权限；不支持的活动 schema 在任何 SDK 写入前被拒绝。
- schema 首版目标不变；验收覆盖只读连接及存储内容未被修改。

## 4. A02：可靠事件投影消费器（P0）

### 契约与实现策略

新增独立的 `ProjectionConsumer` 类或等价函数，复用已有 subscription 和 ACK；不改变底层 ACK 的现有公共契约，不把业务决策操作并入投影消费。

首版选择同步、逐事件持久化确认，按页提交 ACK。回调必须返回明确的 `persisted` 或 `already_present`；`None`、未知返回值、异常、awaitable 都视为未完成。回调只可在其持久化事务提交后返回成功，SDK 无法验证任意外部系统是否真的完成持久化。

事件身份使用调用方稳定配置的 source namespace 加 `(run_id, sequence)`，避免不同存储复用 Run ID 时在同一投影端误去重。重启/同一逻辑源的恢复保留 namespace；独立分叉的投影源须区分身份。Run 的 event sequence 不保证连续，不能按数字加一推算缺失事件。

消费顺序：

1. 观察 cursor、Run revision、有限事件页及高水位；drain 开始时冻结目标高水位，或验证调用方指定的目标。
2. 按源顺序持久化不超过目标的事件，以稳定身份实现应用事务内去重与效果提交。
3. 整页成功后 ACK 到实际处理的最后事件，带 expected revision/cursor 和稳定 ACK 请求身份。
4. 页内任何失败都不推进该页游标；先前已 ACK 页不回退。重启时重放未 ACK 页，已提交效果由应用幂等去重。
5. ACK 回应丢失先用同一请求身份重试；确认冲突后重新观察，不复用同一 command ID 携带不同参数，不强制覆盖游标。

首版同一 subscription 约定单一逻辑消费者；CAS 冲突仍需安全处理，不宣称新增分布式 consumer lease。多消费者、不同版本的 projection 不应无约束共享 subscription。

毒事件默认阻塞当前页，返回事件身份、失败阶段与原因，允许显式、有界重试。后续事件继续保留，不自动跳过。首版不提供 SDK 持久化 dead-letter 队列；未来增加跳过策略必须先定义持久化隔离回执和游标推进契约。

drain 返回目标、已确认游标、处理/重放数量及 completed/blocked/interrupted/conflict 等结果。停止和超时在回调边界检查；回调负责自身 I/O 超时，SDK 不强制中断正在进行的事务，也不承诺永久阻塞的同步回调可被限时终止。回调返回后若预算耗尽或已请求停止，则保留未完成页游标并退出。

固定高水位避免追逐新增事件，但现有 ACK 仍校验 Run revision；只有存在成功 ACK 的窗口才能完成。持续 revision/cursor 冲突在重试预算耗尽后返回 conflict，不承诺持续写入下必然完成。

### 验收与完成条件

- 注入持久化前、提交后 ACK 前、ACK 提交后响应丢失、页内第 N 个事件、关闭时的失败。
- 重启后源事件至少一次；投影端通过去重记录与业务写入同事务获得恰好一次效果。跨库无原子提交承诺。
- 验证无效/异步回调、poison event、Run revision 变化、cursor 冲突、sequence 空洞、不同 source 同 Run ID。
- 持续生产且存在成功 ACK 窗口时完成固定高水位 drain；强制持续冲突时按预算返回 conflict；失败页未确认事件不被跳过。
- 停止发生于回调内时，待回调返回后退出且未完成页不 ACK；回调永久阻塞不属于 SDK 的有界退出保证。
- 优先不改 schema；批量回调、SDK 自持久化失败计数/dead-letter 属于后续独立扩展。

## 5. A03：无可领取工作的诊断（P1）

### 契约与实现策略

新增 `WorkAvailabilityReport` 及只读查询入口，按指定 Run、执行器绑定和观察时间计算。复用或抽取调度判定中的纯逻辑，避免诊断条件与真实 claim 条件分别演化。

至少包含：Run state、claimable_now、活动租约、过期但待 reap 租约、未来重试时间、待投递命令、待同步结果、应用等待、recovery_required、未知 Effect、原因列表和 next_change_hint。

- `claimable_now` 仅计入该执行器具备绑定资格且满足调度条件的执行；执行器信息缺失时报告未检查或明确更宽的计数范围。
- 租约过期尚未 reap 与当前可领取分开；未来 retry/lease 时间仅是变化提示。
- 时钟从观察上下文读取，复用调度的时间语义；不得通过调用更新逻辑时钟的接口完成查询。
- 结果待同步和命令待投递定义去重身份、方向和计数范围；跨库观察不一致不能伪造精确的零。
- 原因可以并存，不把各计数简单相加成互斥总量。terminal Run 与仍待清理/同步的工作可同时出现。
- 常规查询围绕目标 Run 和相关活动执行，示例明细有上限并标明截断；不默认扫描所有终态历史。

### 验收与完成条件

覆盖活动租约、过期租约、重试退避、未同步结果、open wait、unknown Effect、零任务、终态、handler 不匹配、读取期间并发变化。稳定夹具下诊断计数与实际调度资格一致；查询前后持久化时钟、租约、游标和业务表内容不变。

首版目标不变更 schema；若性能必须新增索引，先检查严格 schema 校验和旧 reader/writer 的兼容行为，再决定版本方案。

## 6. A04：取消与恢复报告（P1）

### 阶段 A04a：只读证据聚合

新增 `CancellationRecoveryReport`，复用取消 intent/outbox、Kernel execution/effect、Run attempt 与 sandbox journal。查询不能调用 `Runtime.cancel` 或 `recover_sandboxes`，后两者具有副作用。

报告独立呈现：请求已提交、命令已送达、执行权限已撤销、本地进程树已回收、外部结果、清理状态、Task 终态和 Run 终态。每项附 evidence source 与 known/unknown/not_applicable 等状态。

身份至少关联 source、Run/revision、task、application attempt、execution/revision、fence、effect/revision 和适用的 recovery ID。区分 application attempt 与 Kernel attempt；重试后的新执行不能继承旧代际的取消或清理证据。报告作用域须明确到 Run、Task 或 execution。

- 进程消失、PID 未找到或方法曾返回不构成持久化清理证明。
- 线程权限撤销不等于线程已经终止；线程场景的进程树回收应标为不适用。
- 缺失外部回执保持 unknown；已知执行结果与清理失败可并存。
- 单任务取消不推出 Run 取消，运行中的兄弟任务须保留原状态。
- 旧记录缺少阶段证据时显示 unknown，不能补造历史确认。恢复决策仍使用现有 revision/fence 保护。

### 阶段 A04b：重启后可读的阶段回执

首先检查现有事件/journal 是否能在正确的提交点保存完整证据，并确认旧 reader 能处理新增记录。不能仅以“新增表/字段”为由声称兼容。

若现有机制不足，单独提交 schema 设计，规定回执身份、幂等键、写入者、阶段转换、证据提交时机、保留策略、旧记录 unknown 语义和崩溃恢复方式。涉及外部进程/服务的动作与本地回执不能同事务；动作完成但回执未提交的窗口必须保留 unknown 或通过有身份约束的重新核验恢复证据。

任何 schema 变化均需迁移提案：支持的源/目标版本、读写兼容矩阵、停写和备份条件、转换/验证步骤、失败恢复及回退部署路径。不得自动升级现有活动库，也不得改写绑定绕过恢复限制。

A04a 可单独交付为“现有证据报告”，但不能据此宣称 A04 的持久化取消诊断已全部完成；A04b 是完整关闭条件。

### 验收与完成条件

矩阵覆盖：dispatch 前取消、本地执行中取消、外部 create intent 后取消、create 响应丢失、结果已取得但清理失败、恢复中取消、兄弟任务仍运行、旧代际回执到达、进程重启后重读。

验证 stale revision/fence 被拒绝；未知外部效果不变成 not_applied；重启后阶段结论有持久证据支持；本地、线程和远程后端分别标明证据边界。A04b 的 schema/兼容方案未通过评审时，该阶段保持未完成。

## 7. 实施顺序与评审门槛

不承诺未经验证的工期，以可验收的小变更划分工作：

| 阶段 | 交付 | 进入下一阶段的条件 |
| --- | --- | --- |
| S0 契约冻结 | 四项候选 API、报告枚举、状态矩阵、source/代际身份及测试清单 | 策略确认；明确公开/内部边界与兼容要求 |
| S1 A01 | 身份聚合、能力判定、wheel/source 夹具 | 身份误配与只读负例通过，旧 API 行为保持 |
| S2 A02 | 安全 consumer、SQLite 幂等投影示例、故障注入 | 重放、ACK/CAS、poison 和高水位验收通过 |
| S3 A03 | 只读诊断及原因说明 | 调度资格一致、无写入与查询范围检查通过 |
| S4 A04a | 现有证据聚合报告、取消场景矩阵 | 不确定性/代际关联正确，不制造清理确认 |
| S5 A04b | 持久化回执；必要时独立迁移设计 | schema 方案评审及崩溃/重启验证通过 |
| S6 集成交付 | 四项联用示例、兼容说明、验证记录 | 冻结候选后的独立评审、修复与相关完整检查通过 |

A02/A03 不依赖 A01 的新 API 才能工作，按上述顺序推进是为了优先处理身份误判和审计丢失风险。主代理负责公共契约、集成和最终验证；有清晰边界后可委派独立测试夹具或源码调查，持久化、并发和公开 API 变更采用“实现 → 独立评审 → 修复 → 验证”。

## 8. 验证与发布策略

- 每项实现配套公开类型、用法、失败语义、边界说明与针对性测试；策略文档本轮仅验证链接和需求覆盖，不运行代码测试来暗示实现完成。
- 存储/消费/取消验收使用真实 SQLite 和进程崩溃重启，单元模拟不代替持久化证据。
- 只读测试检查数据、schema、逻辑时钟、租约和 cursor，并检查缺失路径未创建库；不以活跃 WAL 文件的字节变化单独判断业务写入。
- A01 验证独立 wheel 安装及源码覆盖场景；最终运行既有相关回归、公共类型检查、打包和文档检查，保留原始失败与修复后的结果。
- 涉及 Windows 或外部 sandbox 的结论分别提供原生/真实服务证据；缺失环境时明确留下对应验收缺口。
- 四项可按完成阶段独立交付，发布说明区分 A04a 与 A04b。发布版本按最终 API/schema 差异确定，不预先将“策略完成”标记为已发布功能。
- 新功能发布前记录源码/包身份、支持的 schema 和绑定条件。回退仅在旧版本可读写目标存储时成立；需要新 schema 的功能不得承诺原地回退。
- ModPort 后续集成使用精确构建产物验证身份、投影与报告；本轮不修改 ModPort，也不迁移其历史 Run。

## 9. 本轮完成与后续状态

- [x] 核对 A01 至 A04 现有源码基础，记录最小增量与证据限制。
- [x] 明确兼容优先、无自动迁移、只制定策略的范围。
- [x] 制定分阶段交付、故障矩阵、schema 门槛及发布条件。
- [x] 用户确认策略并授权执行，冻结接口与测试契约。
- [x] 实现 A01 至 A04，完成独立评审与针对性回归。
- [x] 完成最终完整回归、独立安装、类型及文档验证。
- 迁移和发布未执行。

实现采用的细化决策：A03 复用现有索引并限制 Effect 扫描，超限返回未知；A04b 使用显式启用的独立 schema 1 回执文件，核心 schema 不变。参见 [API 与限制](SDK_DIAGNOSTICS_AND_PROJECTIONS.md)及[回执兼容设计](CANCELLATION_EVIDENCE.md)。
