# Dispatcher SDK 使用指南

[English](Home.md) | [简体中文](Home-zh-CN.md)

本指南介绍如何在 Python 应用中接入持久化任务执行、执行时限和显式恢复，
面向 SDK 使用者，包括 Agent 应用开发者。应用负责业务决策，
Dispatcher 负责执行与投递。

## 从这里开始

1. [快速开始](Quick-Start-zh-CN.md)：安装当前代码并运行完整示例。
2. [核心概念](Core-Concepts-zh-CN.md)：理解 Runtime、Run、任务和宿主的职责。
3. [接入指南](Integration-Guide-zh-CN.md)：选择函数、脚本或工作流接入路径。
4. [常见问题](Troubleshooting-zh-CN.md)：排查待执行任务、重复通知和恢复状态。

编程 Agent 请先阅读英文 [DocsforAgents](../DocsforAgents/README.md)。
详细 API 契约统一维护在 [docs/SDK.md](../docs/SDK.md) 和
[公共 API 文档](../docs/PUBLIC_API.md)。部分详细指南目前为中文；
Wiki 的两种语言版本均链接到同一份权威文档。

## 版本与范围

这些页面对应 0.6 开发者预览代码，要求 Python 3.10+。
请阅读与代码版本对应的文档；旧版本可能没有这里介绍的接口。
打开现有数据库前，先阅读[存储与升级](../docs/STORAGE_AND_UPGRADES.md)。

核心仅依赖 Python 标准库和 SQLite。OpenSandbox 是可选扩展，需要额外依赖和服务。
进程隔离用于控制可信代码的执行，不提供文件系统或网络权限沙箱。
