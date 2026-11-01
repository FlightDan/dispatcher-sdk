# 0.7.3 release and acceptance status

[English](Improvement-Status.md) | [简体中文](Improvement-Status-zh-CN.md) | [Home](Home.md)

Updated 2026-11-02. This page records the v0.7.3 release and validation status, along with downstream acceptance that remains pending. See [GitHub Releases](https://github.com/FlightDan/dispatcher-sdk/releases) for the release artifact and tag. The [implementation status](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SDK_0_7_2_IMPLEMENTATION_STATUS.md)
contains item-by-item evidence and remaining work; the [improvement strategy](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SDK_0_7_2_IMPROVEMENT_STRATEGY.md)
describes the intended scope.

## Version boundary

- v0.7.2 is the previous published baseline; its artifact and tag remain available for deployments pinned to that release.
- v0.7.3 is the current release. This Wiki's quick-start and general user guides describe v0.7.3 unless a page explicitly identifies historical behavior.
- Source changes, candidate wheels, the release artifact, downstream installation, real Run access and product acceptance are separate states. The status record identifies which artifact each test covers; earlier candidates do not verify the released package.

## Acceptance status

The v0.7.3 SDK release includes the controlled interface for adopting, pausing, revising, activating and resuming a Run split across Kernel and Orchestrator stores, with synthetic test coverage. A focused cancellation-versus-resume race fails closed when a local cancellation intent has committed. Real old-Run access, continuous host writer isolation, the complete application projection and business-update sequence, and on-host acceptance remain outstanding for ModPort.

Kernel schema 12 and Settlement Journal schema 4 provide exact lifecycle receipt keys and explicit generation retirement with bounded batches. The host must prove producer quiescence and retain any needed diagnostic history before pruning. Pre-persistence facts cannot be reconstructed; ambiguous pre-upgrade receipts stay pending for trusted reconciliation. This does not make all SDK metadata bounded.

An isolated installation of the earlier pre-release `0.7.3.dev1` candidate reproduced rejected ModPort business updates after legacy Run adoption. The v0.7.3 release contains the controlled decision interface; synthetic legacy-store adoption, dispatch and process settlement are covered. ModPort still needs to adopt the interface and generate compliant identities for new executions, and on-host acceptance remains outstanding. See the [adoption guide](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/SPLIT_STORE_ADOPTION.md) for the interface constraints.

Other SDK-01 through SDK-08 items have targeted implementation and test evidence, with remaining gaps in the detailed status record. Passing a targeted test or an earlier candidate wheel does not establish complete platform, failure-matrix, real-host or downstream acceptance.

## Host responsibilities

- Keep every old writer and automatic restarter excluded throughout copy, coordination and cutover. Provide a real, continuously held coordination lease and verify final durable receipts; a PID disappearing or a local marker alone does not prove isolation.
- Supply trustworthy authorization, storage identity, original execution ownership, budget and absolute deadline from authoritative sources. Preserve the existing Run and execution identities, history, deadline and budget; keep unknown facts unknown.
- Enforce the single external operation, live deadline and authoritative usage accounting. The application budget ledger records reservations and reconciliation but does not meter or intercept an external provider call.
- For external application storage, provide atomic source-version comparison, write fencing and durable receipts. The host must also constrain participants that can read the complete Run projection.
- Verify handler entry, execution settlement and business acceptance separately. SDK implementation or a successful activation call alone does not prove that the product accepted the resumed work.

Before opening or upgrading a database with v0.7.3, read [storage and upgrades](https://github.com/FlightDan/dispatcher-sdk/blob/main/docs/STORAGE_AND_UPGRADES.md). v0.7.3 uses Kernel schema 12, Orchestrator schema 6 and Settlement Journal schema 4; explicit copy upgrade does not adopt a Run, retire the source or stop already-open writers.
