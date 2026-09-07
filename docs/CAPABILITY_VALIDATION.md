# A01 至 A04 实现验证记录

日期：2026-09-07。范围：[能力增量策略](SDK_CAPABILITY_INCREMENT_STRATEGY.md)中的 A01 至 A04，包括 A04b 持久化取消回执。实现及本轮 Linux 验证已完成，未发布。

## 候选身份

- Python 3.12.3，Linux 6.8.0-138-generic，x86_64，glibc 2.39。
- 源码版本与独立安装元数据均为 0.6.0。
- SDK 源码 SHA-256：`3d53f35452117993ca0087bfee6d4f34e54b326d0f216dd6df0b020868a09ca7`。
- 独立验证的 wheel：`dispatcher_sdk-0.6.0-py3-none-any.whl`。
- wheel SHA-256：`f8449ad4df54684b62a3ba204862a37b94ca26a3a84f4ecca6ffc5b7084a594a`。
- 独立安装的源码摘要与候选一致，wheel RECORD 校验通过。最终完整回归之后只更新验证文档并重建源码包。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| `PYTHONPATH=src python -m unittest discover -s tests -v` | 383 项，431.416 秒，成功；16 项原生 Windows 测试因平台跳过 |
| 源码公共 API 消费者 mypy | 2 个文件通过 |
| 独立 wheel 安装的公共 API 消费者 mypy | 2 个文件通过 |
| 独立安装的可移植示例 | 8 个通过 |
| 文档检查与 README 示例 | 本地链接通过；4 个 README 示例通过，无跳过 |
| wheel、sdist 构建与隔离消费者 | 通过 |
| `git diff --check` | 通过 |

首次完整回归运行了 381 项测试，隔离消费者检查发现包根目录提前加载子模块。修复为惰性公开导出后，最终完整回归通过。最终测试数增加包含评审补充的取消证据用例。

独立评审覆盖身份判定、只读查询、投影 ACK、取消代际与进程树清理证据。已修复辅助文件导致错误恢复判定、跨 Run 扫描范围、claim 条件比较差异、旧 fence 证据串用、回执失败阻止清理、同文件配置检查过晚，以及 supervisor 退出被误认作进程树清理完成等问题。针对性测试包括真实子进程、崩溃重启和 supervisor 被 SIGKILL 后仍存活的后代；最终完整回归包含这些测试。

## 边界与交付

本轮未执行原生 Windows 环境验证；相关 16 项测试由 Windows CI 覆盖。远程 sandbox 使用确定性 FileBackend 夹具，本轮未新增真实 OpenSandbox 服务验证。其他 POSIX 平台的完整进程树清理缺少证明时保持 unknown。

A04b 使用显式启用、独立 schema 1 的取消回执文件，核心数据库 schema 不变，不自动迁移活动库。A03 的 Effect 扫描有界，超过范围时返回未知，不能把不完整观察解释为零。详细契约见 [API 与限制](SDK_DIAGNOSTICS_AND_PROJECTIONS.md)及[取消回执兼容设计](CANCELLATION_EVIDENCE.md)。本轮未修改 ModPort、迁移历史 Run 或发布 SDK。
