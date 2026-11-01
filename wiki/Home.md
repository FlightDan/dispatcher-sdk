# Dispatcher SDK Wiki

[English](Home.md) | [简体中文](Home-zh-CN.md)

This guide explains how to run tasks in a Python application with durable state,
bounded execution, and explicit recovery. It is for SDK users, including Agent
application developers. Your application makes business decisions; Dispatcher
handles execution and delivery.

## Start here

1. [Quick start](Quick-Start.md): install the checkout and run a complete example.
2. [Managed tasks](Managed-Tasks.md): use the 0.7 `Dispatcher` API without assembling the Runtime, Orchestrator and Host yourself.
3. [Core concepts](Core-Concepts.md): understand Runtime, Run, task and host ownership.
4. [Integration guide](Integration-Guide.md): choose a path for functions, scripts or workflows.
5. [Sandbox execution](Sandbox-Execution.md): run remote Linux scripts and understand cleanup and recovery limits.
6. [Storage and local recovery](Storage-and-Recovery.md): inspect SQLite, measure contention and activate a local restored copy.
7. [Troubleshooting](Troubleshooting.md): diagnose pending work, duplicates and recovery.
8. [Integration engineering principles](Engineering-Principles.md): prepare durable deployments and evidence that can be reviewed.
9. [Diagnostics and projections](Diagnostics-and-Projections.md): inspect deployment identity, persist events, and check work availability or cancellation.
10. [Execution activity and supervision](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/EXECUTION_OBSERVABILITY.md): read persisted activity, deadlines, child work and optional stall notifications.
11. [0.7.2 improvement status](Improvement-Status.md): distinguish the published release from current development and see the remaining acceptance work.

Coding agents should start with [DocsforAgents](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/DocsforAgents/README.md).
Detailed 0.7.2 API contracts are in [docs/SDK.md](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/SDK.md) and the
[public API guide](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/PUBLIC_API.md). Some detailed guides are currently in
Chinese; both language editions of this Wiki link to the same authoritative files.
For reusable rules about versions, evidence, candidate freezing and safe object
discovery, see the [integration engineering principles](Engineering-Principles.md).

## Version and scope

These pages describe the published 0.7.2 release, which requires Python 3.10 or
later. The current improvement-development tree is 0.7.3.dev1 and is unreleased;
its implementation and remaining acceptance work are tracked in the
[development status](Improvement-Status.md). Read documentation from the same
revision as your code. Older releases may lack these entry points. Before opening an existing database, read
[storage and upgrades](https://github.com/FlightDan/dispatcher-sdk/blob/v0.7.2/docs/STORAGE_AND_UPGRADES.md).

The core uses the Python standard library and SQLite. OpenSandbox is optional and
requires its own dependency and service. Process isolation controls execution of
trusted code; it is not a filesystem or network security sandbox.
