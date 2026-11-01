# SDK 0.7.2 合成历史库诊断记录

本地 Linux / Python 3.12 探针创建独立临时 Orchestrator schema 5 数据库，包含一个 Run、60,000 个 task 条目和 100,000 条事件，文件大小 10,661,888 字节。数据是合成的，并非现场旧库，不能作为现场布局或生产性能的验收。

可在 Linux 上从仓库根目录使用 `PYTHONPATH=src python3 scripts/benchmark_diagnostic_bounds.py` 重跑。脚本在系统临时目录创建独立数据库，并输出 JSON 测量结果。

| 检查 | 耗时 | 范围及结果 |
| --- | ---: | --- |
| `inspect_storage(check="schema")` | 0.0162 秒 | schema 已检查；完整性、绑定及执行计数未检查；输出 623 字节 |
| `inspect_run_diagnostics(task_limit=10, task_count_scan_limit=100)` | 0.0190 秒 | 返回 10 项和后续游标；计数为未知、下限为 100；`complete=false`；输出 2,672 字节 |
| `inspect_run_diagnostics(timeout_seconds=0)` | 小于 0.0001 秒 | `inspection_timeout`，计数未知，`complete=false`，没有冒充零项 |
| `inspect_storage(check="full")` | 0.0498 秒 | schema 和 SQLite 结构检查通过；未提供 handler，因此绑定未检查；输出 626 字节 |

同一探针进程在四项检查后的峰值驻留内存为 32,428 KiB；这是累计峰值，不是单项增量。上述时间为一次测量，不能作为稳定性能保证。现场两库只读检查仍返回 `unable to open database file`，原因未知；未获取现场数据库的当前快照或修改 Run。

开发候选 schema 6 的同一合成探针也已重跑：数据库 10,690,560 字节；schema 检查 0.0185 秒，有界检查 0.0201 秒，零预算立即返回不完整，full 检查 0.0546 秒，进程累计峰值 32,684 KiB。断言核验了有界结果的未知计数、下限、分页游标及完整性标志。这仍是单机、单次合成测量，不代表现场成本。
