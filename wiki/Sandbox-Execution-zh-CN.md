# 沙箱执行

[English](Sandbox-Execution.md) | [简体中文](Sandbox-Execution-zh-CN.md) | [首页](Home-zh-CN.md)

核心沙箱协议不依赖第三方包。`SandboxHandler` 把远程生命周期写入单独的 journal，
并把 provider 注册成普通 Kernel handler。OpenSandbox 是可选适配器：

```sh
python -m pip install 'dispatcher-sdk[opensandbox]'
```

0.7 适配器固定使用 `opensandbox==0.1.16`，只在执行后端操作时导入官方 SDK，
还需要单独部署 OpenSandbox 服务。其他 provider 可以实现 `SandboxBackend`。

`SandboxSpec` 会冻结镜像、源码、解释器、工作目录、产物路径、CPU/内存请求和受支持的
出站网络策略。输入和采集结果都有大小限制。产物路径按字面处理；SDK 不读取宿主文件，
也不展开 glob。网络是否真正隔离，取决于 provider、容器运行时和服务端配置。

Runtime 会在 create 前保存 operation key，在 start 前保存 sandbox ID，并在轮询前保存
command ID。输出和销毁状态也会写入 journal。沙箱 handler 只能使用进程隔离；线程模式
会被拒绝。Runtime 与 journal 必须使用相同的持久化配置。

超时或取消时，Runtime 先约束本地 worker，再尝试销毁远程沙箱。取消 HTTP 请求并不能
证明脚本已经停止。create/start 响应丢失、command ID 缺失或清理无法确认时，状态会保留为
`SandboxOutcomeUnknown`，不能直接重发脚本。查不到 metadata 或日志，也不能证明操作从未发生。

重启后，Kernel 仍记得已经登记的 journal 路径。journal 丢失、损坏，或旧 handler 不可用，
都会在预检中显示。`runtime.recover_sandboxes(all_pages=True)` 只重试清理不活跃资源，
不会重跑脚本，也不会替应用裁决外部业务副作用。

OpenSandbox 适配器支持 create/find/start/inspect/collect/terminate，能够限制 stdout、stderr
和产物大小，处理分页对账，并在 destroy 后确认资源不存在。真实容器验证覆盖了完整调用链、
响应丢失、非零退出、输出截断和带引号的产物路径。这些结果说明功能和恢复边界可用，
不等于生产安全认证或性能认证。

部署前请阅读[沙箱运行时契约](../docs/SANDBOX_RUNTIME.md)、
[适配器限制](../docs/SANDBOX_ADAPTERS.md)和
[OpenSandbox 验证记录](../docs/OPENSANDBOX_VALIDATION.md)。
