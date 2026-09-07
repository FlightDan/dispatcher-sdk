# 沙箱后端契约与 OpenSandbox 适配器

`SandboxBackend` 协议和冻结的 `SandboxSpec` 不依赖第三方包。OpenSandbox 是可选适配器，
实现位于 `dispatcher_sdk.adapters.opensandbox`，只在调用后端操作时导入官方 SDK。
支持的版本为 `opensandbox==0.1.16`，使用其 `SandboxSync` / `SandboxManagerSync` API；
其他版本会报 `unsupported_sdk_version`，适配器不会假定它们兼容。

## 创建后端与冻结输入

```python
from dispatcher_sdk.adapters import OpenSandboxBackend
from dispatcher_sdk.execution_kernel.sandbox_contracts import SandboxSpec

backend = OpenSandboxBackend(
    domain="localhost:8080",
    protocol="http",
    api_key_env="OPEN_SANDBOX_API_KEY",
    sandbox_ttl_seconds=3600,
)
spec = SandboxSpec(
    image="python:3.12.10-slim-bookworm",
    source="from pathlib import Path\nPath('/tmp/result.txt').write_text('done')\n",
    interpreter=("/usr/local/bin/python3", "-u"),
    cwd="/tmp",
    artifacts=("result.txt",),
    resources={"cpu": "1", "memory": "512Mi"},
    network_policy={"default_action": "deny", "egress": []},
)
payload = spec.to_payload()
assert SandboxSpec.from_payload(payload) == spec
```

安装可选依赖：`pip install 'dispatcher-sdk[opensandbox]'`。读取环境变量中的 API key 时不会
将密钥放入配置、pickle、revision、结果或本适配器生成的异常文本。运行脚本自行打印的
数据属于脚本输出，适配器不提供任意内容的自动脱敏。

`SandboxSpec` 限制 source 为 1 MiB、解释器 argv 为 64 项、artifact 为 32 个字面路径，
resources 和 network_policy 各为最多 64 KiB 的严格 JSON 对象。构造时复制并冻结策略，
`to_payload()` 返回独立的可变 JSON 副本。cwd 和解释器可执行文件必须是 Linux 沙箱中的
绝对路径；artifact 可以相对 cwd。适配器不解析宿主路径，不读取宿主文件，不展开 glob。

资源仅支持字符串形式的 `cpu` 和 `memory`；网络策略仅支持显式 `default_action`
以及包含 `action` / `target` 的 `egress` 列表。未知资源、ingress、端口或其他无法表达的
策略均在创建前抛出 `SandboxPolicyError`，不会静默删除请求字段。域名规则的实际网络隔离
依赖服务端部署与镜像，不由 SDK 本身提供安全隔离。

## 后端操作

| 操作 | 返回与边界 |
| --- | --- |
| `create(spec, operation_key=..., timeout=...)` | 返回 sandbox ID；operation_key 的 SHA-256 用 52 字符小写 Base32 写入 `dispatcher_operation` metadata，满足服务端 63 字符限制 |
| `find(operation_key, timeout=...)` | 读取所有分页并返回全部匹配 ID；多个候选不任选，空结果不证明创建未发生 |
| `start(sandbox_id, spec, timeout=...)` | 上传 source 文件，以安全引用的 argv 后台执行并返回 command ID；返回不表示脚本已完成 |
| `inspect(sandbox_id, command_id, timeout=...)` | `SandboxObservation`，状态为 running / succeeded / failed / unknown；成功必须有明确退出码 0 |
| `collect(sandbox_id, command_id, spec, timeout=...)` | 仅确认终态后收集；返回退出码、stdout、stderr 和文件产物 |
| `terminate(sandbox_id, timeout=...)` | 销毁远程沙箱，再查询确认 HTTP 404 才返回 True；仍存在返回 False，不可确认则抛不确定异常 |

timeout 为当前操作预算（秒）；HTTP 请求使用该预算，并在分页和流读取之间检查剩余时间。
官方客户端内部多请求或阻塞网络读取的硬中断仍由外层监督进程保证。sandbox_ttl_seconds
是独立的沙箱寿命上限，不等同于某个请求超时，也不能代替业务执行 deadline。

每个操作创建和关闭自己的客户端，OpenSandboxBackend 实例只有可 pickle 的基础配置。
revision 包含 SDK 版本和配置摘要，重连不能静默换 endpoint 或收集限额。API key 的值不在
摘要内，允许凭据轮换。所有 provider 自动重试关闭；重试与恢复应由持久化 Runtime 依据事实决定。

## 输出、产物与强停止

脚本输出在沙箱中分别重定向到 stdout/stderr 文件，不使用可能一次读取全部日志的接口。
默认分别最多采集 64 KiB；每项 artifact 最多 1 MiB，artifact 总量最多 4 MiB。
配置的硬上限分别为 1 MiB、8 MiB 和 16 MiB。返回字段包括：

- `data`：base64 编码的已收集前缀，`bytes_read` 为解码后的字节数。
- `truncated`：是否还有未收集字节；截断时 `sha256` 为 null，避免把前缀摘要当作完整产物摘要。
- `path` / `sandbox_id` / `reference_lifetime`：剩余数据只在沙箱存活期间可读取。

远程引用只在沙箱存活期间有效，不提供持久制品存储。销毁或 TTL 到期后引用失效；
需要完整大文件时，应在销毁前导出到应用指定的制品存储。缺失的请求产物会报资源缺失，
不能变成空内容或成功收集。采集时文件还可能被脚本遗留的后代修改；本契约不保证
产物快照或验证业务正确性。

`terminate` 针对独占沙箱，使用管理 API `kill_sandbox` 后查证不存在。setsid 后代可能逃离进程组，
因此不能依赖 command interrupt 杀死进程组来完成强停止。管理查询确认不存在依赖
服务端与容器运行时的正确性；这仍不能回滚脚本已完成的外部网络或文件系统副作用。

## 恢复与异常

`SandboxBackendError(message, code=...)` 的子类为：

- `SandboxOutcomeUnknown`：创建/启动响应丢失、状态不完整、网络失败等。禁止盲目重发副作用。
- `SandboxResourceMissing`：已知沙箱、命令或文件查询返回 404。它不证明资源从未存在或动作从未发生。
- `SandboxPolicyError`：不支持的输入、SDK 版本、配置或预算。

异常文本是固定的本地诊断，原始 provider 异常文本不进入返回值。SDK 本身的日志配置仍由
宿主负责。OpenSandbox 命令没有调用方幂等键，也没有按 operation_key 查命令的 API；metadata
筛选没有唯一约束。因此零条查询、日志缺失、命令 ID 缺失都不是 `not_applied` 的裁决依据。
Runtime 必须在外部调用前保存请求与身份，结合 Effect 恢复保留不确定状态；重启后不能仅因
新进程没有旧客户端就创建新 sandbox 或重发 start。

## 验证范围

[适配器边界测试](../tests/test_opensandbox_adapter.py) 使用 fake 官方客户端验证字段传递、
安全 argv、分页、缺失身份、丢失响应、资源关闭、严格 JSON、字节上限与销毁确认。
这些测试使用测试替身，不覆盖容器端到端行为；官方 SDK 的实际导入与对应类型已在
临时安装的 0.1.16 上检查。

共享 Docker daemon 曾被 execd 镜像层的 containerd snapshot 错误阻塞。改用独立 `/tmp`
daemon 后，官方 SDK 0.1.16 / server 0.2.3 / execd v1.0.22 的真实容器验证通过；
本适配器 create/find/start/inspect/collect/terminate 全流程也通过，包含非零退出码 7、
stdout 截断、完整 stderr、带单引号路径的产物读取与销毁后管理 API 404。
真实创建/启动响应丢失探针同样通过，详情及复现命令见
[OpenSandbox 验证记录](OPENSANDBOX_VALIDATION.md)。这些结果不包含生产隔离或性能认证。

补充验证使用固定官方源码的真实 execd HTTP 路由和运行器，测试 listener 仅绑定
`127.0.0.1:18088`，没有容器隔离：后台进程重连后的退出码 7 与增量日志验证通过；
interrupt 后普通子进程消失，但 setsid 子进程仍存活，测试已主动清理它；实际接收完
start HTTP 响应后丢弃响应，脚本仍写入标记，盲目重发确实重复写入。
该探针的验证范围限于对应命令和传输边界，不覆盖沙箱 create / destroy 或整套 Runtime E2E。
此版本 execd 日志游标实测为字节偏移（`first\nlast\n` 为 11），虽然部分 SDK/API
描述为行游标。调用方应原样保存和回传 opaque cursor；本适配器使用限量文件流读取，
不依赖该游标的单位。
