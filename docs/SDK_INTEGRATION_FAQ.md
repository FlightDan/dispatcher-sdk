# SDK 接入常见问题：可靠审计、输出契约与业务放行

SDK 提供一致观察、独立订阅、历史重放和带条件的确认接口。接入可靠审计、
产物校验和业务放行时，应用需要正确提交审计、校验产物，并显式安排返工或后继
任务。下文提供操作步骤和[可运行审计示例](../examples/durable_audit.py)，
LLM 接入另见[输出契约、校验与有预算返工](SDK_OUTPUT_CONTRACTS.md)。

## 审计失败后能否推进游标？

不能。审计应使用独立订阅，例如 `audit`，与业务决策订阅分开，按以下顺序消费：

1. `observe(run_id, subscription="audit", limit=100)` 在同一读快照中返回 Run、
   当前游标、事件批次及 `event_high_watermark`。
2. 在应用自己的持久化审计库中提交整个批次。以稳定的
   `(source_id, run_id, sequence)` 作为唯一身份，`source_id` 唯一标识原 SDK
   数据库的事件流，重启后沿用。序号不必连续，不能将条数当成游标。
3. 只有持久化提交成功后，才调用 `acknowledge_events` 推进到该批最后一个事件。
   写入或提交异常必须中止本批，不能在 `finally` 中确认。

相同身份且内容完全一致的记录是成功去重；相同身份但内容不同是冲突，必须报错
并停止确认。不能用吞掉异常或无条件 `INSERT OR IGNORE` 代替内容校验。

审计库提交与 SDK ACK 属于两个独立事务。提交后、ACK 前崩溃会导致重放，审计库
通过唯一身份和内容校验接收重复记录。示例将完整 ACK 请求与事件一起提交至应用
表 `pending_ack`，重启先重放原请求；无需读取或修改任何 SDK 内部表。

ACK 遵循精确命令重放与 CAS（比较后更新）规则：

- `expected_revision` 必须来自观察到的 Run；`expected_cursor` 必须是该订阅
  观察到的游标；`advance_to` 是已经可靠提交的批次边界。
- `command_id` 绑定全部请求内容，包括 revision 和游标。响应丢失时原样重放
  相同命令，已提交请求返回原回执，不要求旧 revision 仍是当前值。
- `RevisionConflict` 表示该次新请求未提交；重新观察并形成新请求、新命令身份，
  审计重复记录仍按内容校验。不能改参数后复用旧 ID，否则是 `CommandConflict`。
- `get_command_receipt` 可查询历史回执；回执不是当前 Run 快照。
- ACK 不修改 Run revision，也不产生新事件。纯审计确认应使用该方法；空
  `apply_operations` 仍会生成决策事件，不适合用来循环确认审计流。

按此顺序消费，可以在至少一次投递下恢复并通过审计库去重，但不保证任意外部
副作用 exactly-once。若审计接收方是 HTTP 服务，应以接收方的持久化提交和幂等
契约为准；内存入队或请求已经发送不等于可靠落盘。审计接收方失败应由应用消费
实现修复，不能通过提前 ACK 掩盖失败。

## 为什么终态后还要排空？如何处理超过 100 条事件？

Run 的执行/业务终态与审计订阅进度是两个独立事实。终态 Run 仍可读取和确认
事件；不能在看到 `succeeded`、`failed` 或 `cancelled` 时直接退出消费循环。
`observe` 默认最多返回 100 条，批次结束不代表追上历史末尾。

每轮排空开始时固定 `event_high_watermark` 为目标，持续分页、提交、确认，直到
订阅游标达到该目标。当前批次只处理不超过目标的事件；并发新增的更晚事件留到
下一轮。设置每轮页数/冲突重试或时间上限，耗尽后明确返回未完成并保留进度，
不能将有界退出报告为全部完成。在最终退出前，应先确保应用写入及需要同步的
执行事实已经收敛，再取最终目标并排空；之后若还有写入，需重新排空。

示例运行命令：

```sh
PYTHONPATH=src python3 examples/durable_audit.py
```

示例生成并排空终态 Run 的 207 条事件，验证审计事务失败后游标不动，以及审计
提交后进程中断的恢复路径。示例约定每个 source/run/subscription 只有一个消费
进程；多进程消费还需应用侧互斥或租约保护审计库的待确认请求。

`read_events(run_id, after=..., limit=...)` 是按序号读取历史，不依赖也不推进
订阅游标；ACK 后仍可用它重放、重建或核对审计记录。重放同样需要循环分页。
历史读取能力以原持久化数据库仍保有事件为前提，应用自行定义备份和保留策略。

编排层事件记录 Run 创建、应用决策及 SDK 观察到的执行事实。`sync` 读取
Kernel 快照，可能跨过短暂中间状态，因此编排事件不是 Kernel 每次状态迁移的
完整日志。需要完整执行历史时应使用 Kernel 的事件接口；应用自己的阶段解释、
UI 操作或业务遥测应由应用另行持久化，并关联原 Run/task/attempt 身份。

## 依赖结束是否等于业务成功、是否会自动派发？

不会自动派发。添加任务和依赖只定义约束；应用必须显式提交 `dispatch`。
SDK 检查依赖的当前 attempt 是否已结算，允许的状态是 `succeeded`、`failed`、
`timed_out`、`cancelled`、`dead`。因此前序失败或取消后，应用仍可显式派发
补偿、清理或失败报告任务。`recovery_required` 尚未结算，不满足该条件。
这项机械约束不判断业务验收，也不会把失败结果自动视为通过。

需要“前序成功且业务验收通过才交接”的应用应同时检查执行状态与结果内容。
下面假设前序 handler 返回 `{"accepted": true}` 表示业务放行，`publish`
已经添加并依赖 `review`：

```python
snapshot = sdk.get_run(run_id)
review = snapshot["tasks"]["review"]["attempts"][-1]
result = review["result"]
value = result.get("value") if isinstance(result, dict) else None
allowed = (
    review["state"] == "succeeded"
    and isinstance(value, dict)
    and value.get("accepted") is True
)
if allowed:
    sdk.apply_operations(
        run_id,
        command_id="publish-after-review-1",  # 持久化业务命令身份；变更请求须用新 ID
        expected_revision=snapshot["revision"],
        operations=[{"kind": "dispatch", "task_id": "publish"}],
    )
```

结果结构、证据有效性及允许交接的状态由应用契约定义。机械 `succeeded` 只表示
执行成功返回，并不证明业务审核通过。使用观察快照的 revision 提交，若发生
`RevisionConflict`，重新读取当前 attempt 和结果并重新判断，不能仅替换 revision
后发送旧决定。应用还应检查自己的等待、预算和证据规则，必要时明确失败、等待
人工处理或安排业务返工。Run 成功同样需要应用显式 `finish`。

## Agent 自报 “Validated”，为什么宿主仍会拒绝产物？

自报结果不能代替宿主校验。SDK 校验自己的协议和 JSON 数据约束，应用产物的
字段、枚举、证据和放行条件需要应用校验器检查。仅能解析 JSON、符合 `TypedDict`
注解，或者满足 Agent 在产物中自行声明的 `status_definitions`，都不足以放行。

例如，提示词写 “confirmed change”，宿主却只允许 `confirmed`，Agent 可能输出
非法别名 `confirmed_change`。应从同一份版本化契约生成提示词约束与校验规则，
给出完整合法枚举及含义；Agent 可调用同源自检入口，宿主仍须独立验证收到的产物。
错误反馈应包含字段路径、实际值、允许值及产物身份，便于下一次修复。

上下游 Agent 交接的状态必须使用结构化字段中的精确枚举，自然语言段落不能
作为状态值或路由依据。文字只能解释；下游不能把 “confirmed change” 翻译为
`confirmed_change`，也不能从“已完成”等表述推断放行。缺失或非法状态应由宿主
拒绝并反馈，而不是让下游猜测。合法分类仍不代表整个阶段满足业务验收。

## 执行重试设为 3 次，是否会自动修复非法枚举？

不会。`RetryPolicy.max_attempts=3` 是同一命令最多 3 次机械尝试，包含首次领取；
它不会创建带修复反馈的新命令。handler 正常返回业务错误数据也不等于执行失败。
应用需要配置有限的格式修复预算和路由，在当前 attempt 结算且 Run 仍为
`running` 时，显式提交 `new_attempt` 和 `dispatch`，附上契约、原产物和宿主诊断，
并使用新的执行及幂等身份。预算与返工决定应持久化，重放不能重复扣减。

如果应用第一次校验失败就 `finish`，该 Run 已无法追加修复 attempt。
继续工作需要应用另行创建关联的新 Run，不能修改原终态或抹去失败记录。
完整流程见[有预算的格式返工](SDK_OUTPUT_CONTRACTS.md#4-显式安排有预算的格式返工)。

## 修复格式后，是否可以直接进入下一阶段？

仍须重新校验完整产物和业务验收条件。例如，将非法枚举修正后结构校验通过，
但报告仍有 16 项阻断 gap，就必须继续按 gap 处理策略补证据、返工或等待人工处理。
格式修复不能删除阻断项或替代证据核验。`blocked`、`relevant_skill_gap` 等分类
属于应用业务状态，不是 SDK Run 状态，也不会自动触发 SDK 路由。

相关接口见 [SDK API](SDK.md) 和[恢复与副作用边界](SDK_RECOVERY.md)。
