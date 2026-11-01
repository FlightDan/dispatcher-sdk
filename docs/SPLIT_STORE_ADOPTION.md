# 分离存储旧 Run 接入：开发接口与恢复顺序

本页记录当前开发版本的接口顺序，供宿主集成和审查；它不证明现场旧 writer 已隔离，也不授权切换现场 Run。接入前，宿主必须停止并持续隔离所有旧 writer 和自动拉起者，维护唯一可执行目标，并为每次推进提供真实、有效的隔离及操作凭据。仅有退休标记或 PID 消失不足以证明隔离。组件复制升级也不会自行完成隔离或接入。

控制器使用宿主验证器创建 `Orchestrator` 和 `SQLiteKernel`。真实宿主应从权威来源提供存储身份、原执行归属、预算和绝对 deadline；未知项保持未知。逐页调用 `adopt_legacy_page`，以同一 operation ID 提交按执行 ID 排序的成员页。最后一页必须标识成员已完整；只有 Kernel 回执和协调器记录均完成后，接入状态才是 `paused`。业务状态、原执行 ID、未消费事件和原始预算不得为接入而重写。

完成接入后，以相同的接入 operation ID 建立暂停事务。以下示例仅展示接口顺序，变量和凭据来自宿主；它不是独立可运行程序：

```python
controller.begin_adopted_cross_store_pause(adoption_id, credential=operator)
controller.advance_cross_store_pause(
    adoption_id, credential=operator, adoption_credential=isolation_proof
)
controller.complete_cross_store_pause_participant(adoption_id, credential=operator)
while not controller.capture_cross_store_pause_page(
    adoption_id, credential=operator
)["capture_complete"]:
    pass
controller.prepare_cross_store_pause(adoption_id, credential=operator)
controller.finalize_cross_store_pause(adoption_id, credential=operator)
```

隔离证明必须覆盖已完成的终页及当前仍持有的隔离租约。控制器可在同一 operation ID 上重放；Kernel 已提交屏障但回执尚未记录时，重新推进应取得同一屏障回执，不得重新创建执行或恢复旧 writer。若凭据过期、隔离撤销、参与方身份或终页发生变化，调用必须失败并保持关闭。操作过程中没有全局原子快照，两个存储的状态和回执应分别检查。

暂停后使用 `commit_cross_store_revision` 提交明确的预期 revision、generation、control epoch、部署声明和应用投影迁移；然后使用 `install_cross_store_revision` 和 `install_cross_store_projection` 安装参与方，并用 `activate_cross_store_revision` 激活。激活后仍应验证两方均处于 paused。按实际应用账本通过 `install_cross_store_budget_policy` 配置预算依赖，并在宿主持续持有协调租约时调用 `resume_cross_store_revision`。安装和恢复均要求各自的宿主凭据与参与方回执；调用成功不代表业务 handler 已进入或结算完成。

## 恢复后的业务决策

开发版本提供 `apply_managed_operations`，用于将一批任务操作、应用状态和可选的事件订阅游标作为同一个协调器事务提交。普通 `apply_operations` 和调用它的 `submit_task` 不接受受管 Run；原有调用方需要显式适配，旧 Run 恢复成功本身不会替换调用接口。

```python
snapshot = controller.apply_managed_operations(
    run_id,
    command_id=decision_id,
    expected_revision=revision,
    expected_generation=generation,
    expected_control_epoch=control_epoch,
    source_resume_operation_id=resume_operation_id,
    credential=operator_credential,
    lease_credential=host_lease_credential,
    operations=operations,
    application_state=application_state,
    subscription=subscription,
    expected_cursor=cursor,
    advance_to=observed_sequence,
)
```

宿主验证器须授予该 Run 的 `apply_operations` 权限，且在事务提交前持续持有对应恢复操作的排他控制租约，串行化取消、撤销、预算及控制变更。协调器和 Kernel 的当前代次、控制 epoch、存储身份与恢复回执均须匹配。无需推进游标时应省略三个订阅参数；不更新业务状态时省略 `application_state`。新任务及新尝试的 `execution_id` 必须以 `sdk-managed:` 开头，`correlation_id` 必须为原 Run ID；历史执行身份保持不变，调用方负责生成新身份并满足 Kernel 的预算声明和执行授权要求。

返回的快照只证明协调器决策已提交，后续仍需递送 outbox、取得 Kernel 准入并检查 handler 和结算事实。同一命令重放也会重新检查当前授权和控制状态；若提交结果不明且租约已经过期或控制状态已经变化，可用 `get_command_receipt(run_id, decision_id)` 查询已持久化的原始快照，再由宿主决定如何处理。任务取消与整 Run 跨库存储取消屏障是不同操作，不应以任务取消代替后者。该接口及上述示例属于开发树，真实 ModPort 适配及旧 Run 现场验收尚未完成。

应用数据位于第三方存储时，提交修订应显式声明外部投影参与方、依赖范围及源投影版本，并通过 `reconcile_external_projection` 协调适配器、`install_external_projection_receipt` 安装经过宿主认证的持久回执。适配器必须提供原子源版本比较、有效租约写入围栏和持久回执；SDK 无法代替应用存储实现这些保证。参与方可读取完整 Run 投影，宿主须信任并约束其数据访问。缺少相关回执时相应执行范围保持关闭，不依赖该参与方的已声明范围可继续。重试先检查已提交回执，不能把超时视为未写入。

开发版本的 Kernel schema 为 11，Orchestrator schema 为 6；旧布局通过显式复制升级，升级不等同于接入完成。控制租约转移需要宿主验证新租约和旧持有者排除，并按原操作及持久回执前向恢复；回执只是历史事实，不代表当前工作已获准。宿主还须核验最终协调器开放回执及当前授权。无法确认远端提交状态时保持 unknown。

中断后读取原 operation、参与方回执和当前控制状态，只重放缺失的步骤；已提交修订只能按原决策前向完成。若宿主不能证明连续隔离、预算或必要的清理事实，保留未完成或 unknown 状态，不通过新 Run、重置计数或延长 deadline 绕过。`tests/test_split_store_process_adoption.py` 是临时数据库和模拟宿主凭据的可执行示例；它不能证明实际宿主隔离，也不能替代真实旧 Run 验收。
