# 以 0.7.2 为基线的 SDK 改进策略

日期：2026-10-31。状态：目标与策略已确认，实施进行中；实际进度和限制见[实施记录](SDK_0_7_2_IMPLEMENTATION_STATUS.md)。

## 1. 目标、范围与交付边界

本轮覆盖 SDK-01 至 SDK-08。最终交付是应用可以正式调用的多任务 Run 生命周期：在原 Run ID 下暂停、修订输入或处理器、激活新部署、恢复执行；保留历史证据、未消费事件、原绝对截止时间和累计预算。

**现有非 managed、Kernel 与 Orchestrator 分离存储的 Run 必须能够实际接入。** 仅新增同库 managed Run 示例、返回不可接入原因、给出迁移方案，均不能算完成此目标。接入前确实不满足条件时应准确拒绝；拒绝路径通过测试，只证明拒绝行为正确。

最初的授权仅覆盖制定策略；用户随后授权执行实施。SDK 开发与现场操作分别执行；策略 S5 的下游切换和真实旧 Run 恢复仍需另行授权。SDK 验收不替代 ModPort 接入和目标产品行为验收；没有据此推送或发布版本。

0.7.2 是问题基线。保留已发布版本及其制品、标签和历史证据；新实现使用后续候选版本，不覆盖原 0.7.2。具体版本号在实现范围和兼容性确定后填写，本策略不修改版本。

## 2. 已核对的现状与问题归属

需求来源是本机保留的 `/root/modport/devdoc/SDK_UPDATE_HANDOFF_20261031.md` 和 `/root/modport/devdoc/SDK_DEFECTS.md`。它们是现场索引，转交其他主机时需选择性提供脱敏证据，不附凭据或无差别整库副本。

| 项目 | 已确认的实现或现场边界 | 本轮处理方式 |
| --- | --- | --- |
| SDK-01 | `reopen_run` 只处理终态恢复；`continue_run` 创建新 Run；managed 注册只接受新建同库 Run，完整修订接口未完成 | 补齐公开控制、旧 Run 接入、跨库协调与部署激活 |
| SDK-02 | supervisor 终止失败时，已注册且存在回调的路径会先调用 `on_finished`，再抛出通用异常，可能失去可清理 handle 并绕过 outcome 返回 | 保留精确执行责任和清理义务；修复异常与结算交接 |
| SDK-03 | worker future 异常只有无执行身份的滚动内存记录；缺失 outcome 不能由 `recover_completions` 重造 | 绑定领取上下文，持久记录失败阶段，提供精确恢复 |
| SDK-04 | 历史现场缺少 worker 注册或精确 `process_cleanup` 回执；内部原因未闭合 | 覆盖注册、自然结束、异常和重启的持久回执交接，不伪造历史事实 |
| SDK-05 | 观测事务异常时尝试 rollback；只有指定预算异常附加 `rollback_confirmed`，原始 SQLite interrupt 没有统一结果字段 | 明确事务结果和重放契约；回滚失败保留原异常链与未知状态 |
| SDK-06 | 已有 `stop_report`、阶段、worker 数及线程状态；历史 stop 超时的具体内部原因仍未知 | 扩充责任执行、未完成义务与跨重启处理，复用已有报告 |
| SDK-07 | 已有分级存储检查、检查预算和单 Run 有界诊断；一次全量诊断耗时不能证明性能根因 | 审计真实启动调用链，补足范围、阶段、游标与成本证据 |
| SDK-08 | 已有部分子执行、预算和保留容量机制；本项是新增生命周期的全路径验收要求 | 补齐可信授权、嵌套等待、预算适配器及撤销/恢复验收 |

SDK-02/03 的结构性缺口有源码依据，但不能据此断言已找到所有历史现场的原始原因。SDK-04/06 保持“现象已观测、根因未知”，后续单次绿色运行不能把它们改成“已修复”。

ModPort 的候选与 suite 混用、scope 路由、冻结请求兼容、可变源码部署、incident 操作关系迁移、世界工单归属与清理仍归应用负责。SDK 承载版本、事件和执行事实，不解释这些业务含义。

## 3. 必须保持的约束

1. 同一逻辑 Run 且保持原 Run ID；原 command、execution、attempt、fence、Effect、结果和回执不改名、不覆盖。新增执行使用新授权和新的合法执行身份。
2. 业务 Run 状态、控制状态、修订事务、执行结算、结果投递、消费者确认、进程及 sandbox 清理分别表达；`succeeded`、Host 已停止或 PID 不可见不替代清理证据。
3. 预览是诊断。提交时重新检查权威 revision、generation、control epoch、权限、预算、部署和受影响义务。未知观测不能变成成功或零消耗。
4. 暂停、修订、换宿主、换部署及重放不刷新绝对 deadline，不清零预算，不自动追加额度。预算变更属于另外的显式授权操作。
5. 清理未知和未解决事件保留其实际依赖范围。计划内的显式整 Run 暂停与故障影响范围分开；不能因一个局部未知自动制造全局业务停机条件。
6. 不新增或执行 SHA-1、SHA-256、checksum、fingerprint 检查，也不新增候选/产物身份比较门禁。已有宿主来源字段沿用原值，缺失保持未知；不为补回执重复已通过业务。
7. 身份、认证、预算与总 deadline 错误返回正确消费者，保留原始原因；不能统一转写成“缺少 agent context”或可选观测超时。
8. 通过 SDK 支持的升级和生命周期接口进行未来状态变更；不手工改 SDK 数据库，不把业务状态强制置为终态来使用旧恢复接口。

## 4. 技术主线：控制与业务执行分开，持久决策驱动参与方

### 4.1 复用已有能力，补齐控制路径

保留 `reopen_run` 的终态语义、`continue_run` 的新段语义，以及现有结果投递和确认契约。复用 managed 控制的 epoch、drain 集合、领取时预算计量、清理义务和现有恢复事务的幂等结构；不得直接放宽终态检查充当运行中修订。

当前 managed 执行表限制 `sdk-managed:` 前缀，Kernel 领取查询也按该前缀分流。旧执行接入必须改为由**持久登记的 Run/执行归属和控制版本**约束，覆盖已接收、排队及随后派发的执行。只给新任务加前缀、只在 Orchestrator 包装层暂停或重命名旧 ID 都不成立。

控制状态维持 `active → pausing → paused`。修订事务独立记录 `preparing → prepared → committed → activating → activated`；`activated` 后仍为 paused，只有显式 resume 才开放新业务执行。业务 Run 可以继续保留 running 和未解决的业务等待，无需伪造失败或清空等待。

### 4.2 跨库协调的决策归属

以 Orchestrator 存储中的持久控制操作记录作为协调器的权威决策；Kernel 保存本地参与记录、执行登记和领取屏障。同库路径可使用一个 SQLite 事务，分离路径使用同一语义的持久协调协议，不声称两个文件原子提交。

每个操作至少保存：稳定请求 ID、Run ID、预期 revision/generation/control epoch、操作类型、源/目标部署声明、参与存储的既有身份、参与方阶段与回执、协调者接管信息、原错误、应用迁移版本以及预算截面。协调者 lease 只决定谁能推进操作，不赋予业务执行权限。

| 阶段 | 持久动作与执行边界 | 崩溃后的行为 |
| --- | --- | --- |
| prepare | 记录意图，关闭新派发和新领取；登记跨越屏障的已授权执行、在途派发及清理义务 | 接管者读取原操作逐项推进；部分成功不报告已暂停 |
| prepared | 两个参与方已确认对应屏障和版本；记录可提交的输入、任务图、部署及应用投影 | 提交前重新校验；过期预览不能继续使用 |
| commit | 协调器持久选择新修订、应用投影版本及有效执行集合，保留原输入和旧修订 | 决策已提交后只前向恢复，不混合回旧版本 |
| activate | Kernel 和 Orchestrator 分别安装同一修订的有效映射、部署及受限权限；两方回执齐全 | 保持 paused；新宿主能继续补齐参与方，不启动旧部署 |
| resume | 持久授权开放当前修订，参与方只接受匹配版本的派发/领取 | 单方回执丢失可幂等重放；旧 epoch、旧 worker 和迟到命令不能获得新权限 |

关闭屏障时必须处理派发已经读出但尚未送达 Kernel 的竞态。恢复开放时，任何允许新执行的本地记录都必须有已提交决策和匹配参与版本作为依据；“请求已发送”不是另一方已生效的证明。提交后失联保持可解释的未完成状态，不自动回滚、不因交接重放创建额外执行。

派发以既有 outbox 消息键和原 execution ID 关联，外层记录本次控制版本，不改写旧 command。派发许可与 Orchestrator 屏障在同一本地事务中串行化；Kernel 在接受/登记及领取事务中重复检查 Run 归属与控制版本，不能让未带新前缀的执行绕过屏障。各参与方关闭屏障的本地提交是其生效点；协调器只有取得两方关闭回执并核对在途执行集合后，才能记录全局 prepared。屏障之前已接受或领取的执行进入明确的 drain/interrupt 集合，屏障之后到达的旧派发不能启动新业务。

发送成功但 ACK 丢失时，发送方按原消息/执行身份查询接收事实并幂等重放交接，不创建新 execution 或 attempt。进入 prepared 前必须能将每条在途派发归为已接收、仍被屏障阻止或明确未知；未知依赖不得擅自进入激活。

| 中断位置 | 重启时的权威事实与允许动作 |
| --- | --- |
| 仅 Orchestrator 派发屏障已关闭 | 继续关闭 Kernel 屏障并核对在途执行，不报告全局暂停 |
| 两方关闭回执齐全、协调器尚未 commit | 保持暂停，重新校验后提交或按协议撤销准备，不开放新业务 |
| 协调器已 commit、仅一方应用新修订 | 依原决策补齐另一方，不能恢复旧修订执行资格 |
| 双方已安装新修订、尚未显式 resume | 仍 paused，观察和受限收尾可用 |
| resume 决策已持久化、开放回执不齐 | 先确认双方均安装目标修订且 ready，再向 Kernel 发布本地开放许可，最后开放 Orchestrator 派发；所有步骤绑定同一决策/epoch，重放不重新授权旧消息 |

### 4.3 建议公开的操作面

下列名称仅表达职责，均为待实现能力，不是现有 API 承诺。由独立 controller 提供，观察、暂停和恢复控制不依赖成功导入业务 handler。

| 操作 | 必须具备的语义 |
| --- | --- |
| `inspect_control` / `inspect_execution_lifecycle` | 有界只读查询、精确范围、各参与方观察时间及完整性，不创建或升级数据库 |
| `preview_adoption` / `adopt_existing_run` | 检查并接入既有 Run，显式升级存储和执行登记，重复请求不重复接入 |
| `request_pause` | 明确 drain/interrupt，记录获准 drain 的执行集合和剩余义务 |
| `preview_revision` | 使用权威版本生成影响报告，列出复用、失效、未知和应用迁移要求；没有提交副作用 |
| `commit_revision` / `activate_deployment` | 完成持久协调；历史不变，目标部署和修订对应，激活不自动执行 |
| `resume` | 检查当前授权、预算和实际依赖；拒绝过期调用者及已提交取消 |
| `advance_control` | 重启后推进同一持久操作，只重试未完成步骤，允许单独处理结算或清理 |

控制请求须使用受信授权来源。重复请求的业务幂等检查使用既有持久请求语义，不另外添加文件摘要或候选验证流程。接口须提供类型、错误契约、正常示例和重启示例。

## 5. 旧分离存储 Run 的实际接入

这是 SDK-01 的关键路径，不后置为“后续应用自行处理”。接入后的两个数据库可以继续分离，无需应用自行拼接 lease、generation 和部署切换事务。

1. **只读预览。** 对既有 Kernel schema 5 / Orchestrator schema 4 明确识别 Run、任务/执行映射、未投递 outbox、未消费结果/通知、应用状态、原 deadline、各账本、部署和清理未知。分页读取，跨库报告不冒充单一原子快照。
2. **隔离旧 writer。** 通过受支持的维护入口与宿主控制停止旧 driver、watchdog、dispatcher、worker 和其他相关 writer，保留准确的宿主身份及停止/清理事实。旧 0.7.2 进程不会自动服从新控制表；升级时新增的版本检查也不能撤销已经打开的旧连接。维护清单须覆盖 writer 进程、服务及自动拉起者，并由宿主对实际启动身份/进程树给出退出或隔离证据；未知项不能冒充没有 writer。停用自动拉起后，对受支持 writer 的运行身份实施持久的源存储拒写/只读访问隔离，并保留退休与唯一可执行目标记录，验证旧二进制重启也无法写源库。仅写退休标记、改文件权限或没有观察到 PID，均不足以撤销既有打开连接；须先完成这些持有者的实际停止/隔离。无法确认时停在可恢复的未完成接入，不允许新旧 writer 并行。
3. **显式存储升级。** 在写入已隔离的截面上使用 SDK 升级工具创建升级目标，保留旧存储及其历史只读。组件清单除 Kernel/Orchestrator 外，还须包含实际登记的 settlement、取消、观测、child、sandbox 记录及其内容存储，区分不存在与未知。目标路径变化通过受支持的绑定迁移及持久回执表达，不改历史来源身份、不遗漏仍待处理的 journal。持久记录各参与方的复制/升级/切换进度、源存储退休和唯一目标激活；半切换时两边均不得取得未被决策授权的执行资格。普通构造器不隐式迁移，旧版本重新打开新 schema 须拒绝；原存储不能因保留备份而继续可执行。
4. **保留原执行身份。** 导入实际归属映射，覆盖 Kernel 已接收、Orchestrator 待派发、父子调用及迟到结果所引用的旧执行。升级前后的 Run ID、旧 command 和 attempt/fence 不变。新修订的新执行独立产生；不能把旧 execution ID 改名当新授权。
5. **导入预算。** SDK claim 消耗来自权威执行/计量记录；应用 assignment/token/费用来自相应账本。不能用业务分配次数冒充 claim 次数。每项记录所有者、单位、上限、已用、预留、未知、观察版本和来源引用；不把缺失值填零或推算成额外额度。
6. **迁移应用投影。** 保留原 `application_state`、事件、结果、等待和交接引用。应用提供版本化、确定性且可幂等重放的迁移回调；SDK 在协调操作中保存源状态版本、回调版本、目标投影及其目标修订绑定。回调中断可重算未提交输出；已提交输出按原决策重放，不能重新调用后选择不同业务结果。同库投影与对应激活标记本地原子提交；外部应用存储必须提供持久参与回执，否则相关范围保持未激活，不扩散为无关范围故障。回调不能在数据库事务里偷偷发起外部业务操作。scope/custody 的解释与业务有效性由应用适配器给出。
7. **暂停接入后再修订。** 完成跨库登记和屏障后停在 paused，旧结果继续归属原执行。未知清理义务按实际关联资源/依赖记录；新部署的局部执行资格不能由“整个 Host 已停”推导。
8. **激活与显式恢复。** 在控制协议中选择目标 handler/deployment；新命令绑定目标版本，历史命令继续引用原部署。验证目标绑定及参与方回执，再由明确的 resume 操作启动匹配的新执行。

升级失败时先恢复同一升级/接入操作。只有尚未发生目标写入且 SDK 明确支持退回时，才允许恢复原存储的执行资格；不能同时启用源库和目标库。commit 后通过新修订修复或受支持的前向恢复处理，不做数据库文件替换式“回滚”。

通用验收使用合成的当前支持布局；ModPort 只使用当前明确保留的那一个 Run 做接入验收，不为所有历史 Run 增加兼容分支或回归夹具。当前选定现场为 `hyperbox-workflow130-check-20261030T211609Z`；1274/2240 次业务分配、deadline `1793715688.545443`、清理 unknown 和排队复评均为已有记录，不是本策略重新观测的当前值。实施前重新读取权威状态，不自动扩展 deadline。

## 6. 可靠性与恢复：先补足生命周期所依赖的事实交接

### 6.1 supervisor、worker 和结算（SDK-02/03）

将“从活跃集合移除”与“已确认回收”分开。终止失败后保留可处置 handle，或先转交给持久、精确绑定的清理义务；不能丢掉两者后只抛通用 RuntimeError。异常携带 Run/execution/attempt/fence、phase、原异常链和实际 cleanup 状态。

future 从领取前到执行结束持续关联操作上下文。未领取时明确 `execution_unassigned` 并记录宿主/操作信息；领取后使用真实执行身份，不猜 ID。worker 异常仍允许其他独立执行推进，但不能只写最近 32 条内存错误。

持久状态至少分开：outcome 是否产生、settlement 是否持久化、结果是否投递、消费是否确认、进程及 sandbox 是否清理。已有 `PendingSettlements` 可保留活进程内的原始 outcome，但不是跨进程持久恢复证明；已有 `recover_completions` 也不能重造从未保存的 outcome。

明确 outcome/清理证据从生产者到持久接收方的确认点：只有接收方确认保存，生产者才释放最后一份责任。持久写入暂时失败时保留有界待处理义务并背压；持续失败时显式停止接纳相关新工作。若所有持久存储均不可写，不承诺无损持久化，必须返回可见故障并保持未结算，重启后将无法恢复的 outcome 标为未知，不能从业务 Effect 补造 SDK 成功。

不重复执行的承诺限定于 SDK 已持久提交且具有幂等/可核查契约的 Effect。外部系统已发生操作但响应丢失、无法查询或不提供幂等键时，保留 performing/indeterminate 等真实未知状态，禁止盲目重放；通过适配器核查或显式业务恢复决定解除其实际依赖，不声称 SDK 能保证任意外部副作用恰好执行一次。

### 6.2 注册与清理回执（SDK-04）

对 worker 创建、注册、ready、进入 handler、outcome、driver close 和 cleanup 维护可查询的交接顺序。SDK 所有的正常及故障路径都要保存精确责任；进程树回收、Windows Job Object、sandbox disposal 分别记录来源和状态。

自然结束、异常、取消、宿主重启、回执写入失败/响应丢失使用同一幂等收尾义务。精确 execution/attempt/fence 以及已有宿主启动身份、PID namespace 和进程出生信息用于限定证据；旧现场缺失字段保持未知。重启不得向重用 PID 的新进程发送旧清理指令。

Host completed、active workers 为零、另一执行的回执都不能补出缺失的 `process_cleanup`。原始历史证据不修改；只在后来有对应真实清理事实时附加补偿回执。

### 6.3 观测事务错误（SDK-05）

统一错误结果至少包含 operation、phase、SQLite 原始 code/name、预算来源、事务是否进入、rollback 是否确认、`outcome=not_applied/applied/unknown`、同请求是否可重放，以及异常链。rollback 本身失败时同时保留原 SQL 异常和回滚异常，不能声称已回滚。

只对有幂等契约的精确操作重放。可选观测降级、冷却、重试保留原执行身份，不改变业务状态。认证、绑定、预算和总 deadline 错误不进入这条降级分支。事务结果未知不能统一转换成“未应用”。

### 6.4 Host stop 与诊断成本（SDK-06/07）

扩充既有 `StopReport`，不另起平行报告：在原预算内记录阶段、责任执行、最后进展、未完成结算/投递/Effect/清理，以及已知/未知范围。保留原 stop/timeout 契约，补充同进程继续停止和跨重启处理义务的区别。报告生成不得在超时后展开全库；不通过延长 timeout 掩盖卡点。

复用 `inspect_storage(check='schema'|'bindings'|'full')`、`InspectionBudget`、单 Run 诊断和 settlement 分页。分开启动必需的精确兼容性检查、面向用户的 bounded summary 和显式 full audit；更改默认检查路径前完成旧行为兼容分析。全量检查仍可显式执行，快速路径不冒充完整部署/完整性验证。

对一次真实大历史布局记录各阶段时间、扫描数量、返回字节、查询范围和中断位置；有索引点查不代表 Python 解码、绑定验证或启动导入都便宜。预算耗尽返回 partial/unknown 和可继续位置；`SettlementBusyError` 附当前阶段、已知执行和预算来源。Host 诊断重试与业务重试分别计数，不直接增大共享 journal 预算或调并发作为修复结论。

## 7. 授权、预算与父子等待（SDK-08）

| 责任 | SDK | 应用或适配器 |
| --- | --- | --- |
| 授权 | 将受信授权绑定到 Run/执行/修订，检查操作、收窄委托、撤销及旧调用者失权 | 认证主体、租户、业务许可策略及版本 |
| 预算 | SDK claim、预留/结算、机械重试、原绝对 deadline、幂等重放计量 | assignment、token、费用及外部调用的真实计量/限制 |
| 结果与复用 | 不可变结果、持久交接、迟到结果隔离、版本化复用记录 | 业务兼容、结果是否可接受和业务事件迁移 |
| 父子等待 | 持久等待关系、深度/容量/资源约束、取消/撤销传播 | 任务依赖与合法业务操作范围 |

授权检查覆盖公开 controller，也覆盖 Runtime、Orchestrator、直接 Kernel 调用、child、Effect、结果及恢复入口。只在包装层做检查不算完成。调用者自报 actor、team 或 execution ID 不授予权限；直接任意 SQL、恶意同进程代码及非 SDK 托管的外部进程不在 SDK 自身可隔离的信任边界内。

撤销后禁止新业务操作，但保留此前合法操作的受限结果持久化、确认、取消与清理能力，避免把失权变成无法收尾。取消已提交时，迟到 resume 不得重新开放。

预算适配器明确 reserve/settle/reconcile 的幂等请求和未知结果语义；响应丢失保留预留，不能按零结算。未接入计量的外部调用不能宣称受硬 token/费用预算保证。预算不足或用量未知时限制依赖该额度的新业务，保留有界维护；维护额度不得用于绕开业务限制。

验证 A 等待 B、B 再等待 C，在普通 worker 已满时仍能按声明的 child 深度与保留容量正确推进，或返回准确容量不足。已有 `child_capacity`/`max_child_depth` 为基础，不能创建无限 worker。父进程逻辑让出 slot 后仍存活的进程、内存及外部资源继续计入资源约束。暂停应明确哪些现有 child 可 drain、哪些请求应等待或拒绝；重启后等待关系与预算预留不消失。

## 8. 实施顺序、依赖与阶段退出条件

生命周期是本轮主交付；可靠性补齐是安全接入与恢复的前提。阶段可以产生可审查增量，只有完成最后的实际接入才满足本轮目标。

| 阶段 | 工作与对应事项 | 依赖 | 退出条件 |
| --- | --- | --- | --- |
| S0 契约与源码基线 | 固定控制状态、身份映射、错误/结果契约、授权和预算所有者；明确旧 Run 完成判据、回滚不确定性及既有诊断复用 | 无 | 旧 API 行为对照、存储升级/拒绝条件、8 项状态清单和验收表可独立审查 |
| S1 执行责任闭环 | 修复 supervisor/future 逃逸与身份缺失；可靠交接 outcome/cleanup；补足 SQLite 错误和 stop 责任报告（02–06） | S0 | 定向故障注入后原执行可定位、可收尾或明确未知，独立执行不被误停；未制造成功结算 |
| S2 分离存储与接入屏障 | 实现协调器、显式 schema 升级、旧 writer 隔离、非前缀执行登记、在途派发处理、应用/预算截面导入（01/08） | S0；收尾依赖 S1 | 合成的旧非 managed Run 在原 ID 下接入并 paused；两库任一点中断可由同一操作恢复 |
| S3 完整公开生命周期 | 独立 controller、可信授权、影响预览、修订提交、部署激活、resume、父子等待和预算适配器（01/08） | S1、S2 | 分离存储真实多进程闭环；激活仍暂停；旧权限拒绝、原事件保留、预算连续 |
| S4 诊断与交付验收 | 完成有界诊断/大库验证、installed wheel、公开类型、文档、平台与适配器验证（01–08） | S1–S3 | 验收矩阵有原始证据及限制；已知实现缺陷修复后才运行/触发 CI |
| S5 下游实际接入 | SDK 候选安装后，由 ModPort 通过公开接口接入唯一选定旧 Run，迁移应用投影，逐项验证 pause → revision → deployment activation → explicit resume | S4；现场操作另行授权 | 同一旧 Run 的暂停回执、修订提交、激活仍暂停、显式恢复和实际新 handler 进入均有证据；原 ID、事件/处置关系、deadline 和累计账本保留，旧权限未误放行 |

S0 后，观测错误/stop 报告与 supervisor/settlement 修复可按不重叠模块并行；S2 的存储协议、S3 的授权接口和公共类型由主实现者统一集成。诊断只读框架可提前开展，但不能提前宣布全生命周期可用。

持久化、授权和跨库协议变更采用“实现 → 新上下文独立审查 → 修复 → 实际路径验证”。不以纯 mock、私有 helper 通过或更多绿色测试数量代替公开路径验收。

## 9. 必须执行的验收矩阵

以下是未来实施的验收要求，本次没有运行。每项报告须有版本、实际导入位置、平台、用例、原始失败/结果、精确执行身份及保留限制。

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A01 | 同库和分离存储的多任务 Run；无活跃任务但有业务等待 | 原 ID 下 pause/revise/activate/resume；等待和未消费事件仍在，不要求业务失败 |
| A02 | Kernel5/Orchestrator4 的非 managed、非 `sdk-managed:` 执行接入 | 原 command、execution、attempt/fence 保留；排队和直连 Kernel 路径同受新控制 |
| A03 | 旧 writer 已打开连接、旧二进制重启、在途 dispatch/ACK 丢失、组件升级中断 | 源库持久拒写、只有决策授权的目标可执行；按原消息核对接收事实；旧派发不越过屏障，同一操作可接管推进 |
| A04 | prepare/commit/activate/resume 各写入及回执边界崩溃 | 重放不重复分配或重放已提交的幂等 Effect；外部未知副作用不盲目重跑；不丢已持久事件，commit 后不混合旧修订 |
| A05 | 两个 controller、并发修订、取消与 resume 竞争 | 稳定请求幂等；过期 revision/epoch 拒绝；取消提交后不再开放 |
| A06 | 旧 worker/lease/调用者、迟到结果、部署不匹配 | 旧结果只进原执行；原部署可诊断，新部署获得独立权限；激活不自动执行 |
| A07 | supervisor 无法终止、future 在领取前/后抛错 | 未分配与精确执行正确区分；责任未丢，原异常返回，清理未知不冒充 confirmed |
| A08 | outcome/cleanup 写入失败、接收方已写但确认丢失、宿主崩溃 | 保留待处理义务或明确不可恢复边界；没有业务回执造成功、没有重复业务补回执 |
| A09 | 自然结束、取消、异常、重启、PID 重用、sandbox disposal 失败 | Linux、Windows、远程清理分别给出精确证据或 unknown；旧 PID 不被误杀 |
| A10 | SQLite interrupt、BUSY/LOCKED、预算耗尽、rollback 再失败 | phase、原 SQLite 信息、事务结果与重放许可准确；永久错误不被吞掉 |
| A11 | worker/通知/coordinator 阻塞和 stop 超时 | 原预算内返回既有报告及责任细节；后续只推进未完成义务，不假报 stopped |
| A12 | 原 worker 满、A 等 B 等 C、父仍占内存、暂停/取消/恢复 | 有界容量、等待和撤销传播正确，资源未漏计，无无限扩 worker 或等待死锁 |
| A13 | 预算已耗尽、未决预留、未知 token/assignment、重放与重启 | 预算所有者分开、原 deadline 不变；不清零、不重复扣费、不自动追加 |
| A14 | 多个未解决应用事件、局部 cleanup unknown、回调中断/重放、外部应用投影提交后崩溃 | 投影与目标修订绑定且前向恢复，缺少持久回执的范围不开放；事件/结果/处置引用保留，独立范围按依赖继续，业务有效性由应用验证 |
| A15 | 大历史库：启动精确检查、bounded summary、显式 full audit | 范围/成本/完整性可见；快速查询不整库展开，partial 不变成成功或零问题 |
| A16 | 隔离安装 wheel 和实际服务导入 | 公开 API/类型/示例及真实子进程均使用候选安装包，不误从源码目录导入 |
| A17 | 唯一选定 ModPort 旧 Run 的真实接入及完整生命周期 | 原 ID 下接入、暂停、修订提交、部署激活仍暂停、显式恢复、目标 handler 进入逐项有证据；复评排队和实际消费分开验证，世界清理及产品行为不顺带宣称通过 |

平台要求覆盖 Linux/Windows 的 x86-64 与 ARM64，以及声明支持的 Python 版本。原生 ARM64、x64 模拟运行、未运行分别标记；本机 Linux 结果不能替代其他平台。远程 sandbox 使用代表性受支持适配器单独验证；线程模式只承诺协作式停止，不宣称强制终止。

修复后先完成受影响实际路径的定向验证和独立审查；存储/协议/生命周期变更再执行相应完整回归和平台检查。所有已知实现缺陷修复后才运行或触发 CI；未定位的历史原因单列，不能偷偷改成“已修复”。

## 10. 完成判据与交付清单

每个 SDK-01～08 条目维护“已确认事实／假设、实现状态、验证证据、未解决事项、下游边界”。代码完成、installed wheel 验收、下游依赖安装、真实接入和业务接受分别登记。保留原失败矩阵，不拿隔离复现成功覆盖历史失败。

交付内容包括公开接口/类型与示例、显式升级和接入工具、跨库恢复协议、授权与预算适配器契约、故障矩阵证据、有界诊断和 stop 报告说明、兼容性与平台限制，以及下游接入步骤和原存储退休/回退边界。

S1 的可靠性增量可以单独形成候选，但必须标明 SDK-01 尚未完成。S4 完成只能声明 SDK 通用候选通过；S5 的真实旧 Run 接入完成后，才可声明本轮完整目标达成。HyperBox 迁移、世界清理与目标行为仍需各自验收。

若实施时选定 Run 已耗尽原预算或超过原 deadline，不得擅自延长或伪造“恢复执行通过”。可如实报告接入/控制/拒绝路径结果，完整恢复目标仍未达成；需要改变原约束时另行取得用户明确决定。策略不以等待、换 Run 或重设计数绕开这一点。

## 11. 实现与证据入口

本节链接指向现有代码/文档，用来定位复用点和缺口；它们不代表本策略已实施。

| 主题 | 入口 |
| --- | --- |
| managed 注册、同库限制及暂停义务 | [managed.py](../src/dispatcher_sdk/orchestrator/managed.py) |
| 原终态恢复及持久恢复事务 | [recovery.py](../src/dispatcher_sdk/orchestrator/recovery.py) |
| 前缀约束、控制表与领取屏障 | [_sqlite_schema.py](../src/dispatcher_sdk/execution_kernel/_sqlite_schema.py)、[_sqlite_execution.py](../src/dispatcher_sdk/execution_kernel/_sqlite_execution.py) |
| 派发、结果持久化及确认 | [transport.py](../src/dispatcher_sdk/orchestrator/transport.py)、[results.py](../src/dispatcher_sdk/orchestrator/results.py) |
| supervisor 与 outcome/cleanup 生产者 | [_process_runtime.py](../src/dispatcher_sdk/execution_kernel/_process_runtime.py)、[runtime.py](../src/dispatcher_sdk/execution_kernel/runtime.py) |
| worker 异常、内存待结算与 journal | [host.py](../src/dispatcher_sdk/execution_kernel/host.py)、[pending_settlements.py](../src/dispatcher_sdk/execution_kernel/pending_settlements.py)、[settlement.py](../src/dispatcher_sdk/execution_kernel/settlement.py) |
| 已有 Host stop 报告 | [orchestrator/host.py](../src/dispatcher_sdk/orchestrator/host.py)、[SDK_RELIABILITY.md](SDK_RELIABILITY.md) |
| 观测事务及有界诊断 | [journal.py](../src/dispatcher_sdk/observability/journal.py)、[storage.py](../src/dispatcher_sdk/storage.py)、[run_diagnostics.py](../src/dispatcher_sdk/orchestrator/run_diagnostics.py) |
| 预算、子执行与旧设计边界 | [managed_contracts.py](../src/dispatcher_sdk/managed_contracts.py)、[EXECUTION_OBSERVABILITY.md](EXECUTION_OBSERVABILITY.md)、[DEV_0_7_0_DEV1_IMPROVEMENT_PLAN.md](DEV_0_7_0_DEV1_IMPROVEMENT_PLAN.md) |

旧设计文档是历史背景，不直接沿用其完成状态或验证方式。本次没有调用带摘要计算的预览/身份 helper，没有新增或运行额外哈希验证；实现时也须从作者源头移除任何不被授权的新验证门禁，同时保留既有历史证据。
