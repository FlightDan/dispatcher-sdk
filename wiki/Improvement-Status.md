# 0.7.2 improvement development status

[English](Improvement-Status.md) | [简体中文](Improvement-Status-zh-CN.md) | [Home](Home.md)

Updated 2026-11-02. This page summarizes the 0.7.3 development and validation record;
check [GitHub Releases](https://github.com/FlightDan/dispatcher-sdk/releases) for publication status. See the [implementation status](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SDK_0_7_2_IMPLEMENTATION_STATUS.md)
for item-by-item evidence and remaining work, and the [improvement strategy](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SDK_0_7_2_IMPROVEMENT_STRATEGY.md)
for the intended scope.

## Version boundary

- 0.7.2 is the published baseline. Its release artifact and tag remain the released version.
- The current source package version is 0.7.3. Its release status is tracked on GitHub Releases.
- This Wiki's quick-start and general user guides describe the published 0.7.2 behavior unless a page explicitly points to development-only material.
- Code changes, a locally installed candidate wheel, downstream installation, real Run access and product acceptance are separate states. The status record identifies which wheel each test covers; results for older candidates do not verify later changes.

## Acceptance status

Implementation is in progress and the planned stage exit conditions are not all met. In particular, the development tree has synthetic tests for adopting, pausing, revising, activating and resuming a Run split across Kernel and Orchestrator stores. A focused cancellation-versus-resume race now fails closed when a local cancellation intent has committed. Real old-Run access, continuous host writer isolation, the complete application projection and business-update sequence, and on-host acceptance remain outstanding.

Kernel schema 12 and Settlement Journal schema 4 provide exact lifecycle receipt keys and explicit generation retirement with bounded batches. The host must prove producer quiescence and retain any needed diagnostic history before pruning. Pre-persistence facts cannot be reconstructed; ambiguous pre-upgrade receipts stay pending for trusted reconciliation. This does not make all SDK metadata bounded.

An isolated installation of an earlier `0.7.3.dev1` candidate reproduced rejected ModPort business updates after legacy Run adoption. The development tree now has a controlled decision interface, with synthetic legacy-store adoption, dispatch and process settlement tested. ModPort still needs to adopt the interface and generate compliant identities for new executions, and on-host acceptance remains outstanding. See the [adoption guide](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SPLIT_STORE_ADOPTION.md) for the interface constraints.

Other SDK-01 through SDK-08 items have targeted implementation and test evidence, with remaining gaps in the detailed status record. Passing a targeted test or an earlier candidate wheel does not establish complete platform, failure-matrix, real-host or downstream acceptance.

## Host responsibilities

- Keep every old writer and automatic restarter excluded throughout copy, coordination and cutover. Provide a real, continuously held coordination lease and verify final durable receipts; a PID disappearing or a local marker alone does not prove isolation.
- Supply trustworthy authorization, storage identity, original execution ownership, budget and absolute deadline from authoritative sources. Preserve the existing Run and execution identities, history, deadline and budget; keep unknown facts unknown.
- Enforce the single external operation, live deadline and authoritative usage accounting. The application budget ledger records reservations and reconciliation but does not meter or intercept an external provider call.
- For external application storage, provide atomic source-version comparison, write fencing and durable receipts. The host must also constrain participants that can read the complete Run projection.
- Verify handler entry, execution settlement and business acceptance separately. SDK implementation or a successful activation call alone does not prove that the product accepted the resumed work.

Before opening or upgrading a development database, read [storage and upgrades](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/STORAGE_AND_UPGRADES.md). The development tree uses Kernel schema 12, Orchestrator schema 6 and Settlement Journal schema 4; explicit copy upgrade does not adopt a Run, retire the source or stop already-open writers.
