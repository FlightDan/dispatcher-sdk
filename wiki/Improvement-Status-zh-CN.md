# 0.7.3 发布与验收状态

[English](Improvement-Status.md) | [简体中文](Improvement-Status-zh-CN.md) | [首页](Home-zh-CN.md)

更新于 2026-11-02。本页记录 v0.7.3 发布与验证状态，以及仍待完成的下游验收。发布制品和标签见 [GitHub Releases](https://github.com/FlightDan/dispatcher-sdk/releases)。
逐项证据和未完成事项见[实施状态](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SDK_0_7_2_IMPLEMENTATION_STATUS.md)，
目标范围见[改进策略](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SDK_0_7_2_IMPROVEMENT_STRATEGY.md)。

## 版本边界

- v0.7.2 是上一版正式发布基线；其制品和标签仍供固定使用该版本的部署查阅。
- v0.7.3 是当前发布版。本 Wiki 的快速开始和通用用户指南介绍 v0.7.3，明确标记为历史内容的页面除外。
- 源码修改、候选 wheel、正式发布制品、下游安装、真实 Run 接入和产品验收是不同状态。实施记录标明各项测试对应的制品；较早候选包的结果不能验证正式发布包。

## 验收状态

v0.7.3 SDK 已发布受控接口，合成测试覆盖 Kernel 与 Orchestrator 分离存储 Run 的接入、暂停、修订、激活和恢复；跨库取消与恢复的定向竞态测试验证本地取消意图提交后会拒绝重新开放。ModPort 的真实旧 Run 接入、持续的宿主 writer 隔离、完整的应用投影和正常业务更新流程及宿主现场验收仍待完成。

Kernel schema 12 与 Settlement Journal schema 4 增加精确生命周期回执命名空间和显式分批代次退役。宿主必须先证明生产者静默，并保留仍需使用的诊断历史，才能裁剪。首次持久写入前丢失的事实不能还原；升级前回执有歧义时保持待处理，等待可信核对。这不代表 SDK 全部元数据已得到有界清理。

隔离安装的早期预发布 `0.7.3.dev1` 候选包曾复现：旧 Run 接入受管模式后，ModPort 的后续业务提交被拒绝。v0.7.3 发布版包含受控业务提交接口；合成旧库接入、派发和进程结算已有测试覆盖。ModPort 仍需适配调用与新执行身份，现场验收仍待完成。具体约束见[接入说明](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SPLIT_STORE_ADOPTION.md)。

SDK-01 至 SDK-08 其他条目已有定向实现与测试证据，仍有详细状态记录中的缺口。定向测试通过或较早候选 wheel 通过，都不代表完整平台、故障矩阵、真实宿主或下游验收已经完成。

## 宿主责任

- 在复制、协调和切换期间持续排除所有旧 writer 和自动重启者。提供真实且持续持有的协调租约，并核验最终持久化回执；PID 消失或本地标记本身不能证明隔离。
- 从权威来源提供可信授权、存储身份、原执行归属、预算和绝对 deadline。保留原 Run 和执行身份、历史、截止时间及预算；未知事实继续标为未知。
- 执行唯一外部操作、实时期限和权威用量记账。应用预算账本可以记录预留及对账，但不会计量或拦截外部服务调用。
- 使用外部应用存储时，适配器必须提供原子源版本比较、写入 fencing 和持久回执。宿主还须约束能够读取完整 Run 投影的参与方。
- 分别核验 handler 已进入、执行已结算和业务验收通过。SDK 实现完成或激活调用成功，本身不能证明产品接受了恢复后的工作。

使用 v0.7.3 打开或升级数据库前，先阅读[存储与升级](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/STORAGE_AND_UPGRADES.md)。v0.7.3 使用 Kernel schema 12、Orchestrator schema 6 和 Settlement Journal schema 4；显式复制升级不会接入 Run、退役源库或停止已经打开的 writer。
