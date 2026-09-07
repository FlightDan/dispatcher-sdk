# SDK 接入：恢复、预算与副作用边界

配套文档：[SDK API](SDK.md)、[脚本执行与对话唤醒](SDK_SCRIPT_WAKEUPS.md)、
[公开 API 与兼容性](PUBLIC_API.md)、[可靠审计与业务放行 FAQ](SDK_INTEGRATION_FAQ.md)。

## 1. 谁负责什么

| 责任 | Owner | 当前能力与应用责任 |
| --- | --- | --- |
| 执行、租约、fence、技术重试、Effect | Kernel | 持久化执行事实，拒绝旧 fence；不知道业务阶段和验收含义 |
| Run/task/attempt、依赖、等待、回执、可靠传输 | SDK Orchestrator | 应用显式操作，事务保存状态与事件；不会自行选下一阶段或宣布成功 |
| 阶段路由、预算、审查、验收、业务停滞 | 应用编排策略 | 应用定义阶段数、路由及成功条件 |
| 证据选择、契约冻结、失败知识继承 | 应用策略与执行适配器 | 验证内容及来源，绑定当前输入、版本、attempt 和验收对象 |
| 文件修改、Git、外部系统对账 | 执行适配器 | 接入 Effect，提供可验证的外部事实及操作身份 |
| 工作循环、worker、定时唤醒 | 宿主 | 调度 flush、执行、sync 和应用决策，不在空轮询时猜测业务终态 |

应用可通过 `observe` 读取一致的状态和事件，在事务外计算决策，再通过
`apply_operations` 原子提交操作、应用状态和订阅游标。可重放的决策代码不能
直接修改文件或调用有副作用的服务；独立应用数据库需要自己的 outbox/inbox
与幂等 SDK 命令。

## 2. 四种等待或预算不能混用

| 类别 | 计数/状态 | 处理规则 |
| --- | --- | --- |
| 等待有效租约、重试退避、人工裁决 | 租约到期时间、next_attempt_at、持久化 wait | 轮询和等待本身不消耗执行或业务修复次数 |
| 机械执行重试 | Kernel attempt、RetryPolicy | 同一个 execution_id/idempotency_key；新的领取产生新 attempt/fence |
| 业务修复或返工 | 应用预算、显式 new_attempt | 旧 attempt 先结算，新执行身份；保留旧证据和失败因果 |
| 命令/结果传输重试 | 各投递通道的计数、回执和错误 | 不代表重新执行 handler，不得扣业务返工次数 |

`RetryPolicy.max_attempts` **包含首次领取**，默认是 1。它同时限制普通租约过期
重投和允许的执行失败重试；`redelivery_count` 是观测计数，不是独立重投额度。
普通执行第一次领取后崩溃，若没有未决 Effect 且 `max_attempts=1`，租约到期回收会
产生 `dead / lease_retry_exhausted`，不会自动再领一次。

需要机械恢复时，应用应先满足副作用安全要求，再在命令首次冻结、注册前配置
有限的技术重试额度和退避。增加次数不能修复副作用安全问题；已接受的命令不能
修改，也不能靠不断创建 `new_attempt` 绕开技术重试上限。预算耗尽后，应说明原因
并进入应用定义的失败或人工处理路径；具体执行终态不可复活。

当前 API 没有独立的“崩溃重投预算”字段。若产品要求它与执行失败重试分别计费，
需要单独设计 Kernel 契约、计数和兼容策略；这不是已实现能力，也不是恢复循环
正确区分等待与业务修复的前提。

## 3. 恢复循环与无进展判定

`flush()` 的返回值是本次新送达消息数；0 不证明队列空。
`runtime.run_once()` 返回 `None` 不证明 Run 停滞，例如有效租约、退避、无匹配
registry 的任务或线程槽满都可能暂时没有可执行工作。
`sync()` 返回被查询到的执行数量，不是状态变化数量；它不会回收租约、推进业务
路由或把整个 Run 自动转为 waiting/succeeded。

宿主应使用可重入循环。SDK 的 `OrchestratorHost` 可自动调度 reap、flush、
worker 执行、sync 和通知投递；应用仍须接入自己的业务决策驱动。下列步骤列出
完整接入职责，业务阶段始终由应用选择：

1. 重开原持久化存储，核对 workflow/handler 版本及冻结输入，恢复原身份和游标。
2. 调用 `runtime.reap()` 回收真正过期的租约，然后 `sdk.sync()` 同步执行事实。
3. 应用驱动根据新快照/事件决定派发、等待、业务修复或终止；原子保存决策和预算。
4. 调用 `sdk.flush()`；宿主 worker 执行已接受命令，再 `sdk.sync()`。
   使用独立应用结果消费链时还要泵送结果、提交应用 inbox/决策、最后 ack。
5. 查询持久化状态，安排下一次有界、可取消的唤醒；重新同步后再决策。

宿主可并行运行独立 worker，但不能依赖一个长时间阻塞的 handler 返回来驱动
所有其他任务的同步和恢复。领取路径也会回收过期租约；显式 reap 可使无 worker
执行时的恢复检查继续工作。查询和同步本身不替代 reap。

runtime 的 lease_seconds 是下限，实际租约还会覆盖命令 timeout 与启动安全余量。
因此即使配置为 120 秒，也必须以持久化 lease.expires_at 为准。

| 观察到的事实 | 应用/宿主动作 |
| --- | --- |
| leased/running 且租约有效 | 等待或观察，不能抢占同一执行；旧 worker 的心跳可能延长租约 |
| queued 且 next_attempt_at 未到 | 按可比较的 Kernel 时钟安排退避后检查 |
| queued 且已到期，但无匹配 registry 或 worker 容量 | 呈现执行环境阻塞；不能当业务停滞或换用最新版 handler |
| 租约已过期 | reap 后重新读取，分辨 queued、dead、recovery_required |
| recovery_required | 应用显式建立持久化恢复等待，展示 effect_id/revision；不得 finish 或盲目 new_attempt |
| 命令未送达或结果未消费 | 检查该方向的传输错误及恢复 API，不能伪造任务结果 |
| 所有执行已结算 | 依据冻结验收、审查、依赖和等待状态决定下一阶段或显式 finish |

通过 `sdk.inspect_execution(execution_id)` 可读取已注册执行的权威快照而不写入
SDK；快照含 `lease.expires_at`、`next_attempt_at`、`attempt`、`redelivery_count`、
`kernel revision` 对应的 `revision` 和恢复信息。命令尚未送达时查询可能找不到
执行，应同时检查 `delivery_messages(...)`。分页/limit 不得让部分观察冒充全量。

只有在排除合法等待、退避、传输故障和执行环境阻塞后，应用才能按已定义的业务
规则判定停滞。两秒没有命令不是充分证据。若设总运行时限，应单独呈现时限到达，
安全结算或取消活动任务；不能将进程停止等同于迁移失败或成功。

时限触发策略需要宿主显式提交 signal 等事件。SDK `wait` 只增加 open 等待记录，不把 Run
从 running 改为 waiting，也不自动阻止 dispatch；应用策略必须检查等待条件并在
满足后显式 `release_wait`。open wait 会阻止 finish。业务界面的 waiting 是应用
含义，不能与 SDK Run 状态混用。重复决策或唤醒不能重复扣预算。时间比较使用
Kernel 的同一可比较时钟域。

## 4. 崩溃窗口与 Effect 的实际保证

`HandlerContext.effects.execute_once(effect_id, name, request, perform)` 在调用
`perform` 前持久化 prepared，并在外部动作返回后提交响应。稳定的 effect_id 和
严格匹配的 request 使已提交响应能被同一执行复用。SDK 命令幂等、结果幂等与外部
动作幂等是不同保证；Git/文件系统不与 SQLite 共享原子事务。

| 崩溃窗口 | 恢复规则 |
| --- | --- |
| Kernel 已接受命令，SDK 尚未确认送达 | 重放原命令，只接受相同身份和内容，不创建第二个执行 |
| Effect prepared，外部动作尚未开始或只做了一部分 | 新 fence 下视为不确定，不能仅凭结果缺失判定 not_applied |
| 文件已修改/Git 已提交，Effect 响应未落库 | 进入 recovery_required，由适配器对账后显式裁决；不能自动再改或再提交 |
| Effect committed，执行结果未落库 | 若机械重试仍允许，重跑 handler 时复用原 Effect 响应；预算耗尽仍可 dead，不能承诺自动补结果 |
| 执行结果已落库，SDK/应用尚未消费或 ack | 通过持久化结果队列及原身份重放，应用 inbox 去重，不能重新执行副作用 |

租约回收会先处理未决 Effect，再检查机械预算。因此即使 `max_attempts=1`，
未决 Effect 也会进入非终态 `recovery_required`，没有伪造终态结果或结果 outbox。
宿主必须主动同步这一持久化事实，应用再创建等待；只订阅终态结果会漏掉它。
`watch_task` 通知会同时捕获进入 recovery_required 的事件，可由
`OrchestratorHost` 回调唤醒应用处理；登记通知本身不创建业务 wait，也不裁决 Effect。

只读聚合查询可以按 Run 展示待裁决项，应用无需逐层查找 task、execution、effect：

```python
for recovery in sdk.inspect_recoveries(run_id):
    print(recovery.task_id, recovery.attempt, recovery.execution.recovery_target_state,
          recovery.effect.effect_id, recovery.effect.revision, recovery.effect.request)
```

`attempt` 是从 0 开始的应用尝试索引；`execution.attempt` 是 Kernel 领取次数。
该接口读取 Kernel 权威状态，不依赖已同步的 Run 状态，但不会主动 reap、sync 或裁决。
每项含一个当前待裁决 Effect；裁决后重新查询，才能获取同一执行的下一项。
`run_revision` 是初始 Run 读取的版本，不是跨库原子快照；读取期间持续变化会抛出
`RevisionConflict`，调用方可稍后重查。实际裁决仍必须使用 `effect.revision`
作为 `expected_revision`，并提供稳定 `recovery_id` 和外部事实支持的决定。

未决状态包括动作尚未领取的 prepared 与已领取执行的 performing；在外部写入
完成但提交响应前崩溃，持久记录仍可能是 performing，不能据此断定动作未完成。

显式 `resolve_effect` 绑定 `expected_revision` 和稳定 `recovery_id`：

- `applied`：有证据证明动作已发生，保存已知响应供后续复用。
- `not_applied`：有证据证明动作未发生，响应为 null，允许后续新 fence 重做。
- 无法确定或只完成部分动作：保留等待，不能猜测任一裁决。

多项未决 Effect 必须逐一处理。全部裁决后，普通恢复目标回到 queued，可获一次
超出机械上限的显式恢复领取；后续失败/过期正常耗尽。若持久化恢复目标是 cancelled，
全部裁决后进入 cancelled，不会重新执行。重复同一裁决不会额外释放执行次数。

适配器应在动作前保存操作身份及前置状态，并将成功后的可核对事实作为响应：
例如仓库/worktree 身份、基线提交、冻结输入摘要、目标范围、patch/产物 SHA-256、
生成的提交 ID。对账必须检查操作归属、实际内容和部分完成情况，而不只看 HEAD。
具体字段和对账规则由适配器定义。

Effect 记录不阻止绕过接口的 shell、文件或 Git 操作，也不能回滚它们；fence 只
撤销 Kernel 接受结果/Effect 的权限，不能拦住一个仍存活进程的任意磁盘写入。
恢复前必须确认旧执行已隔离或停止，对共享仓库提供写入排他约束。Git 提交只是
副作用证据，不是验收成功。当前接口不保证任意外部动作 exactly-once。

## 5. 证据链不能由通用 SDK 代办

应用必须按自己的业务契约验证以下约束，任一约束不满足时都应阻止交接：

- 只选择当前合法依赖/祖先的授权结果；拒绝兄弟分支、旧 attempt 或错误工作区的
结果，除非业务规则显式允许并记录继承来源。
- 读取实际产物重新计算 SHA-256，检查来源和冻结身份；摘要匹配只证明字节一致，
  不能证明结果正确或来源被授权。不能用文件名、mtime 或日志文字替代证据。
- 冻结 workflow/assignment、输入、验收规则及执行版本；恢复时拒绝静默换约。
- 业务返工继承被审查 patch、失败原因、验证命令及证据引用；保留全部旧历史。
- 独立审查绑定当前候选产物，最终验收绑定同一候选；修改后旧审查结论不自动生效。

Kernel 的命令/结果身份校验与 registry 绑定不替代业务校验。应用只有在自己的
阶段和验收条件满足后，才能显式声明 Run 成功。

## 6. 脚本通知与恢复

同一 `apply_operations` 可提交 `add_task`、`watch_task` 和 `dispatch`。
`OrchestratorHost` 在后台执行并同步事实，终态或进入 `recovery_required` 时投递
通知。内部技术重试不唤醒应用；通知会保留短暂的恢复状态，处理前应查询当前权威状态。

通知重试属于传输预算，不扣执行次数或业务返工次数。`watch_task` 绑定登记时的
应用 attempt；业务 `new_attempt` 需要新的 `watch_id`。通知与原结果消费队列独立，
不会自动确认原结果。应用 inbox 应原子去重并入队，避免重投创建重复对话任务。

回调异常会重试，耗尽投递预算后进入通知 dead letter，需要显式重投。阻塞回调
不阻塞执行 worker，但会延迟其他通知，关闭宿主时也可能触发 `TimeoutError`。
宿主必须保持运行，应用必须提供可靠、及时返回的对话入队回调。具体接口见
[脚本执行与对话唤醒](SDK_SCRIPT_WAKEUPS.md)。
