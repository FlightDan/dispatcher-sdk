# Dispatcher SDK 使用指南

[English](Home.md) | [简体中文](Home-zh-CN.md)

本指南面向 SDK 使用者，包括开发 Agent 应用的 Python 开发者。它介绍如何在
Python 应用中运行任务，并使用持久化状态、执行时限和显式恢复。应用负责业务
决策；Dispatcher 负责执行任务并投递结果。

## 从这里开始

1. [快速开始](Quick-Start-zh-CN.md)：安装当前代码并运行完整示例。
2. [核心概念](Core-Concepts-zh-CN.md)：理解 Runtime、Run、任务和宿主各自负责什么。
3. [接入指南](Integration-Guide-zh-CN.md)：选择函数、脚本或工作流接入路径。
4. [常见问题](Troubleshooting-zh-CN.md)：排查待执行任务、重复通知和恢复状态。
5. [接入工程原则](Engineering-Principles-zh-CN.md)：准备可恢复的部署和可审查的证据。
6. [诊断与事件投影](Diagnostics-and-Projections-zh-CN.md)：检查部署身份和持久化事件，排查工作是否可用以及取消状态。

使用编程 Agent 接入 SDK 时，可让它先阅读英文 [DocsforAgents](../DocsforAgents/README.md)。
详细 API 契约统一维护在 [docs/SDK.md](../docs/SDK.md) 和
[公共 API 文档](../docs/PUBLIC_API.md)。部分详细指南目前只有中文；Wiki 的两种
语言版本都链接到同一份权威文档。关于如何核对版本和证据、在最终验证前固定
待发布版本，以及修改持久化对象前确认身份，见[接入工程原则](Engineering-Principles-zh-CN.md)。

## 版本与范围

这些页面对应 0.6 开发者预览代码，运行环境要求 Python 3.10+。
文档要和代码版本匹配；旧版本可能没有这里介绍的接口。
如果要打开现有数据库，请先阅读[存储与升级](../docs/STORAGE_AND_UPGRADES.md)。

核心组件只依赖 Python 标准库和 SQLite。OpenSandbox 是可选扩展，需要额外依赖和服务。
进程隔离只用于控制可信代码的执行，不能当作文件系统或网络权限沙箱。
