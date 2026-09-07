# Dispatcher SDK Wiki

[English](Home.md) | [简体中文](Home-zh-CN.md)

This guide explains how to run tasks in a Python application with durable state,
bounded execution, and explicit recovery. It is for SDK users, including Agent
application developers. Your application makes business decisions; Dispatcher
handles execution and delivery.

## Start here

1. [Quick start](Quick-Start.md): install the checkout and run a complete example.
2. [Core concepts](Core-Concepts.md): understand Runtime, Run, task and host ownership.
3. [Integration guide](Integration-Guide.md): choose a path for functions, scripts or workflows.
4. [Troubleshooting](Troubleshooting.md): diagnose pending work, duplicates and recovery.

Coding agents should start with [DocsforAgents](../DocsforAgents/README.md).
Detailed API contracts are maintained in [docs/SDK.md](../docs/SDK.md) and the
[public API guide](../docs/PUBLIC_API.md). Some detailed guides are currently in
Chinese; both language editions of this Wiki link to the same authoritative files.

## Version and scope

These pages describe the 0.6 developer-preview checkout, which requires Python 3.10+.
Read documentation from the same revision as your code. Older releases may lack
these entry points. Before opening an existing database, read
[storage and upgrades](../docs/STORAGE_AND_UPGRADES.md).

The core uses the Python standard library and SQLite. OpenSandbox is optional and
requires its own dependency and service. Process isolation controls execution of
trusted code; it is not a filesystem or network security sandbox.
