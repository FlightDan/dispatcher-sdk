# 存储与本地恢复

[English](Storage-and-Recovery.md) | [简体中文](Storage-and-Recovery-zh-CN.md) | [首页](Home-zh-CN.md)

0.7 的单文件部署默认使用 SQLite WAL 和 `synchronous=FULL`。Kernel schema 仍为 2，
Orchestrator schema 为 3，通知收件箱使用独立的 schema 1。产品版本与存储 schema
不是同一个概念。

通过 `app.diagnostics()` 或 `dispatcher_sdk.diagnostics.inspect_diagnostics()` 可以查看
执行状态、`recovery_required`、投递与收件箱积压，以及数据库和 WAL 大小。所有组件共用
一个文件时，计数来自同一个 SQLite 只读快照。查询超时会返回明确的不完整报告。
报告不会伪装成 SQLite 锁等待计时。

在目标主机上运行 `scripts/benchmark_sqlite_contention.py`，可以测量多个进程竞争时的
SDK 调用延迟。请保留 JSON 结果，作为部署证据。仓库记录的 FULL 持久化短测在 1、4、8
个 worker 下都正确完成，但 claim 尾延迟随并发上升很明显。这组数字只代表当时的机器和负载。

## 备份、恢复和激活

`snapshot_store_group` 会为调用方声明的完整文件集创建带认证的快照。
`restore_snapshot` 把快照复制到新的只读目录。文件恢复完成后，任务仍不会自动执行。

`activate_restored_snapshot` 用于同一主机上的保守交接。原数据库必须仍可访问、已经停止，
而且从快照创建后没有发生逻辑变化。激活过程会检查 handler 绑定，拒绝无法覆盖的外部资源
和硬链接别名，永久退役旧路径，再把数据复制到新的受保护目录并发布认证回执。

激活中断后，可以用相同 operation ID 重试。目标目录旁保存 reservation 记录，因此 SDK
能区分“创建目录时中断”和“已经运行过但后来丢失的副本”。后一种情况会直接拒绝，
不会从旧快照重建并冒险重复执行任务。

这套协议不提供跨机自动接管。旧主机失联时，SDK 无法证明它已停止，也不知道备份后发生了
哪些操作。旧版 SDK、直接 SQLite 写入和拥有文件系统权限的程序也可能绕过本地标记。
这类恢复需要外部所有权隔离，并按业务证据核对副作用。

激活不会替应用处理未决 Effect。排队任务可以继续；遗留租约按原有过期和 reap 流程处理。
不要手工删除 retirement、reservation、pending 或只读标记。

详细说明见 [SQLite 运维](../docs/SQLITE_OPERATIONS.md)、
[存储升级](../docs/STORAGE_AND_UPGRADES.md)和[本地恢复流程](../docs/LOCAL_RECOVERY.md)。
