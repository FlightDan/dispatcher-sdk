# OpenSandbox 验证记录

验证日期：2026-09-07。记录包括真实容器验证、实际 execd HTTP 探针和源码契约测试，
各项结果分别注明验证范围。

## 结论

OpenSandbox 提供远程后台执行适配器所需的基础 API，但不保证命令启动 exactly-once。
创建响应丢失和命令启动响应丢失必须保留不确定状态；命令 interrupt
不能作为任意后代进程已停止的证明。独占沙箱销毁并确认不存在，才可作为强停止依据。

官方发布版的真实容器与适配器端到端验证已通过。测试使用独立 `/tmp` Docker daemon，
避开共享 daemon 的存储问题；使用的是发布镜像，没有用 mock 服务或源码替代。

| 真实验证 | 结果 |
| --- | --- |
| 官方 SDK 创建沙箱、后台运行、关闭客户端后重连 | 通过；退出码 7 被正确保留，日志增量查询正确 |
| command interrupt 与后代 | 普通子进程消失；setsid 子进程仍为 S，证实它能逃离进程组取消 |
| 整沙箱 destroy | 通过；已启动且含逃逸后代的沙箱销毁后，管理 API 查询返回 404 |
| 创建成功响应被丢弃 | 通过；客户端报错，按提前保存的 metadata token 找回唯一沙箱 |
| 启动成功响应被丢弃 | 通过；命令仍写入标记，盲目重发实际产生第二次写入 |
| 本仓库 OpenSandboxBackend | create/find/start/inspect/collect/terminate 全流程通过；输出上限与带引号产物路径正确 |

真实环境：Docker 29.1.3 / vfs，官方 SDK 0.1.16，server 0.2.3，
`opensandbox/execd:v1.0.22`（镜像摘要
`sha256:0d8f44cf4194732719aa79999d4b120c98bdab02bc61e9ad13f75f83af4c2684`），
基础镜像 `python:3.12.10-slim-bookworm`。这是功能与恢复边界验证，不是生产安全隔离、
网络策略或性能认证。随后 `scripts/verify_sandbox_runtime.py --live` 也通过真实
Runtime/OpenSandbox 验证，覆盖产物、超时与清理后恢复、取消与清理、Runtime 关闭。

### 验证资源清理

全部真实测试完成后，已在 2026-09-07 定向清理本任务资源：

- 独立 socket `/tmp/dispatcher-docker.sock` 在控制面停止前后均查到零容器。
- 核对完整进程参数后，停止任务 OpenSandbox server（PID 684018）和独立
  Docker daemon（PID 682530）；删除经 ID 核对且无容器端点的任务网络
  `dispatcher-validation-net`。daemon 退出后，其 socket 与 pidfile 均不存在。
- 最终进程检查未发现任务服务或 execd 遗留进程；`127.0.0.1:18087` 与
  `127.0.0.1:18088` 均拒绝连接。共享 Docker daemon（PID 1275）仍运行，未清理共享资源。
- 保留验证日志、探针证据、源码及独立 daemon 数据目录；清理检查记录保存于
  `/tmp/dispatcher-opensandbox-cleanup.log`。未执行全局 prune。

## 共享 daemon 排查与源码证据

- Docker 服务版本 29.1.3；初始 localhost:8080、44772 没有服务；未发现配置
  OpenSandbox 的环境变量，仅检查名称，未输出凭据。
- 在 `/tmp/dispatcher-opensandbox-venv` 安装官方 `opensandbox==0.1.16`、
  `opensandbox-server==0.2.3`；临时服务只绑定 `127.0.0.1:18087`，使用任务配置和 SQLite 路径。
- 第一次真实 `Sandbox.create(image="python:3.12-slim")` 返回
  `DOCKER::SANDBOX_START_FAILED`：containerd `failed to create snapshot: missing parent`
  `moby/2/sha256:f2ec4de84f559f5c7be4233b589cdbdbb5507807e05621b77320edd55a1f2a0f`。
- 单独拉取 `python:3.12.10-slim-bookworm` 成功，镜像摘要
  `sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db`。
  第二次真实创建已生成容器，随后因缺少 execd 镜像而失败；官方服务已清理该任务容器。
- 显式拉取 `opensandbox/execd:v1.0.22` 和独立版本 `v1.1.0` 均失败：
  `unable to prepare extraction snapshot: AlreadyExists: target snapshot`
  `sha256:34884abbe92863fce933ed7c39c0e045631af0ed86d5cc0dfbdf9fdca426ce3c already exists`。
  未进行全局 prune、删除共享镜像或修复共享 Docker 存储。
- 随后基于固定官方源码构建本任务 execd 镜像成功，但共享 daemon 的第三次
  `containers.create` 在 180 秒读取超时，SDK 客户端先在 120 秒超时。按精确容器名查询
  返回 `No such container`；超时本身不构成“创建未发生”的证明。连接共享 daemon 的临时控制面已停止。
- 最终使用独立 `/tmp` data-root、exec-root、socket 与 vfs 存储驱动启动 Docker daemon；
  关闭 daemon 的 iptables、IP forwarding、masquerade 与默认 bridge 操作，创建本任务内部网络。
  两个官方发布镜像在新 daemon 中成功拉取，随后真实验证通过。
- 官方源码固定在 commit `82143b6c2d65698718d63e53cbf5aec3d40c4208`。
  对该源码运行 SDK destroy、close/connect、command streaming、retry decision 测试：61 项通过。
  这些测试使用测试替身，属于 SDK 契约测试。
- 同一源码的 execd Go `TestGetCommandStatus*`、`TestSeekBackgroundCommandOutput*`
  测试通过（包含直接运行后台 shell 的测试）；这不是容器沙箱端到端测试。

安装的发布版和 main 源码版本不同，上述源码结论不自动证明已发布 execd 镜像有完全相同实现。

还运行了固定 main 源码的实际 execd HTTP 路由：仅将 listener 绑定到
`127.0.0.1:18088`，不使用容器。该探针再次验证重连、退出码、日志、setsid 逃逸和真实
启动响应丢失导致重复副作用；重启 execd 后，原命令 ID 查询实测返回 HTTP 404。
这个补充探针不验证容器 create/destroy。

## 能力与恢复边界

| 能力 | 官方 API / 源码事实 | 适配器约束 |
| --- | --- | --- |
| 后台启动 | `commands.run(..., opts=RunCommandOpts(background=True))` 返回 `Execution.id`；后台 complete 事件表示启动请求完成 | 不能将 run 返回当命令成功；继续查询状态 |
| 重连 | `Sandbox.connect(sandbox_id)`；`close()` 只关本地 transport | 持久化 sandbox_id 和 command_id；SDK 对象不能作为恢复身份 |
| 状态 | `get_command_status(id)` 有 running、exit_code、error、时间戳 | 字段可空；查不到不能解释为未执行或成功 |
| 日志 | `get_background_command_logs(id,cursor)` 返回合并输出与 opaque cursor；源码和发布版实测是字节偏移，`first\nlast\n` 返回 11 | 原样保存和回传游标，不按文档中的“行”自行计算；日志不是成功证据，也不保证 stdout/stderr 分离 |
| 保留期 | main 的 command 状态在内存 map；完成命令与日志 24 小时后可清理 | execd 重启、沙箱销毁或保留期后不能承诺恢复历史状态 |
| interrupt | Linux 对进程组 SIGTERM，必要时 SIGKILL；响应允许异步清理 | setsid 后代可逃离该组；不能将 interrupt 返回当强停止 |
| destroy | `destroy()` 调用 kill 并 finally close；kill 失败继续抛出 | 独占 sandbox 才可用于取消；随后确认权威查询 404，失败则保持取消待确认 |
| create 响应丢失 | sandbox ID 服务生成；metadata 可过滤分页查询，没有 metadata 唯一约束 | 稳定 operation token 必须先持久化；0 条不是未创建证明，多条不可任选；禁止盲目重建 |
| command 响应丢失 | ID 由 execd 生成，通过 init 事件返回；请求无 caller command ID / 幂等键，未见按操作 token 查命令接口 | 丢失 ID 时记 UNKNOWN/recovery_required；有 ID 也只证明初始化，须查状态；销毁并确认旧独占 sandbox 后才可按上层副作用策略决定重发 |

取消旧计算不能回滚它已完成的网络、仓库或外部数据库副作用。销毁确认也不是外部副作用
“未发生”的裁决依据。不要用新的 command ID、sandbox ID 或 task attempt 隐式绕过未决 Effect。

adapter 实现 create/find/start/inspect/collect/terminate，见
[沙箱后端契约](SANDBOX_ADAPTERS.md)。客户端在各次操作中重连和关闭；官方 SDK 延迟导入，
不增加核心第三方运行时依赖。实测还发现服务端 metadata 值最多 63 字符，适配器已将
operation_key 的 SHA-256 改为不丢位数的 52 字符小写 Base32，避免 64 字符 hex 被拒绝。

## 可复现检查

[验证脚本](../scripts/verify_opensandbox.py) 默认只检查配置变量名，无第三方导入。
`--live` 创建一个五分钟 TTL 的新沙箱，检查后台非零退出、close 后重连、状态、增量日志、
普通后代与 setsid 后代取消观测，最后销毁并查询不存在。`--live-loss` 在真实成功的
HTTP 响应被完整接收后故意丢弃它，验证创建对账与启动不确定性；没有替换服务端返回数据。
`--live-adapter` 验证本仓库适配器的真实调用、stdout/stderr/产物限量收集和销毁确认。
三个模式均已在独立 daemon 上通过。

```sh
python3 -m venv /tmp/opensandbox-verify
/tmp/opensandbox-verify/bin/pip install opensandbox==0.1.16
python3 scripts/verify_opensandbox.py
# 使用已配置好的隔离测试服务，设置 OPEN_SANDBOX_DOMAIN、OPEN_SANDBOX_API_KEY。
/tmp/opensandbox-verify/bin/python scripts/verify_opensandbox.py --live
/tmp/opensandbox-verify/bin/python scripts/verify_opensandbox.py --live-loss
# 已安装本仓库或设置 PYTHONPATH=src 后：
PYTHONPATH=src /tmp/opensandbox-verify/bin/python scripts/verify_opensandbox.py --live-adapter
```

创建响应丢失时，脚本也可能没有 sandbox_id；它会提前打印唯一 metadata operation token。
此时必须按 token 在服务中对账，不应直接重跑；TTL 限制资源的最长存活时间，不能证明执行结果。
不要在有无关 OpenSandbox 容器的共享 daemon 上随意启动另一控制面：官方服务启动会扫描
既有容器并恢复过期定时器，应使用独立测试 Docker daemon 或既有测试服务。

### 独立 daemon 的复现配置

以下为本次使用的任务专属 daemon 配置，需具备启动 daemon 的系统权限。在独立终端运行，
不更改 `/etc/docker/daemon.json` 或共享 Docker 数据。完成验证后只关闭这个 daemon，
并在关闭前用同一 socket 删除本任务的网络与容器。

```sh
mkdir -p /tmp/dispatcher-docker-data /tmp/dispatcher-docker-run
printf '{}\n' > /tmp/dispatcher-docker-daemon.json
dockerd --config-file /tmp/dispatcher-docker-daemon.json \
  --data-root /tmp/dispatcher-docker-data --exec-root /tmp/dispatcher-docker-run \
  --pidfile /tmp/dispatcher-docker.pid --host unix:///tmp/dispatcher-docker.sock \
  --iptables=false --ip6tables=false --ip-forward=false --ip-masq=false \
  --bridge=none --userland-proxy=false --storage-driver=vfs
```

另一个终端中：

```sh
docker --host unix:///tmp/dispatcher-docker.sock network create --internal dispatcher-validation-net
docker --host unix:///tmp/dispatcher-docker.sock pull python:3.12.10-slim-bookworm
docker --host unix:///tmp/dispatcher-docker.sock pull opensandbox/execd:v1.0.22
```

官方 server 的任务 TOML 配置使用 `[server] host="127.0.0.1"`、`port=18087`、独立测试 key；
`[runtime] type="docker"`、`execd_image="opensandbox/execd:v1.0.22"`；
`[docker] network_mode="dispatcher-validation-net"`；`[store]` 指向独立 `/tmp` 数据库。
启动 server 时设置 `DOCKER_HOST=unix:///tmp/dispatcher-docker.sock`，客户端设置对应的
`OPEN_SANDBOX_DOMAIN` 与 `OPEN_SANDBOX_API_KEY`。不要把这组测试凭据用于公开监听的服务。

官方源码测试命令（先 clone 并 checkout 上述 commit）：

```sh
PYTHONPATH=/tmp/dispatcher-opensandbox-source/sdks/sandbox/python/src \
 /tmp/dispatcher-opensandbox-venv/bin/python -m pytest -q \
 /tmp/dispatcher-opensandbox-source/sdks/sandbox/python/tests/test_sandbox_destroy.py \
 /tmp/dispatcher-opensandbox-source/sdks/sandbox/python/tests/test_sandbox_close_and_connect_validation.py \
 /tmp/dispatcher-opensandbox-source/sdks/sandbox/python/tests/test_command_service_adapter_streaming.py \
 /tmp/dispatcher-opensandbox-source/sdks/sandbox/python/tests/test_retry_decision.py
# 在官方源码 components/execd 目录运行：
go test ./pkg/runtime -run 'Test(GetCommandStatus|SeekBackgroundCommandOutput)' -count=1
```

## 官方依据

- [execd API](https://github.com/opensandbox-group/OpenSandbox/blob/82143b6c2d65698718d63e53cbf5aec3d40c4208/specs/execd-api.yaml)
- [后台进程启动](https://github.com/opensandbox-group/OpenSandbox/blob/82143b6c2d65698718d63e53cbf5aec3d40c4208/components/execd/pkg/runtime/command.go)
- [状态与日志保留](https://github.com/opensandbox-group/OpenSandbox/blob/82143b6c2d65698718d63e53cbf5aec3d40c4208/components/execd/pkg/runtime/command_common.go)
- [Linux interrupt](https://github.com/opensandbox-group/OpenSandbox/blob/82143b6c2d65698718d63e53cbf5aec3d40c4208/components/execd/pkg/runtime/interrupt.go)
- [Python Sandbox 生命周期](https://github.com/opensandbox-group/OpenSandbox/blob/82143b6c2d65698718d63e53cbf5aec3d40c4208/sdks/sandbox/python/src/opensandbox/sandbox.py)
- [SDK retry decision](https://github.com/opensandbox-group/OpenSandbox/blob/82143b6c2d65698718d63e53cbf5aec3d40c4208/sdks/sandbox/python/src/opensandbox/transport/_decision.py)
