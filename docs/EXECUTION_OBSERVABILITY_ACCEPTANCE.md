# Execution observability acceptance evidence

This index tracks [T01–T09 and A01–A18](EXECUTION_OBSERVABILITY_GOAL.md).
The implementation is not yet fully accepted. Source-level focused checks have
passed on Linux x86_64; installed-candidate validation, full regression, the
native Windows matrix and the remaining live ModPort handoff are pending.
No release is authorized by this work.

## Candidate and reproducible commands

The source version is `0.7.0.dev2`. Final evidence must identify the Git commit,
installed distribution and actual import path, without relying on a version
string alone. The CI test jobs install the package, run the existing complete
matrix, and retain native scenario artifacts under
`SDK_ACCEPTANCE_EVIDENCE_DIR`. Tests print each artifact directory and interpreter.

From the SDK checkout, the focused source witnesses are reproducible with:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_observability_native_acceptance
PYTHONPATH=src .venv/bin/python -m unittest tests.test_observability_pressure
PYTHONPATH=src .venv/bin/python -m unittest tests.test_runtime_settlement tests.test_settlement_journal
PYTHONPATH=src .venv/bin/python -m unittest tests.test_stall_supervision tests.test_managed_children_capacity
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The last command includes the isolated rebuilt-wheel consumer suite. A focused
pass does not replace it. Five public typing fixtures and `scripts/check_docs.py`
are also required. The latter runs all six README examples on Linux.

## Scenario mapping

The status below describes current evidence, not final Goal acceptance. Raw
host paths identify retained artifacts for this run; they are not portable
links or substitutes for the candidate CI artifacts.

| Scenario | Implementation and witness | Current evidence / remaining requirement |
| --- | --- | --- |
| A01 Startup phases | `test_observability_native_acceptance`: queue, real deserialization, ready, entry, model request, raw bootstrap failure | Linux focused passed; readiness and entry facts also survive an unavailable activity writer in independent notes. Installed candidate and Windows pending. |
| A02 Raw output and progress | Same native suite: segmented bytes, heartbeat, tool response, new/replayed progress; `test_observation_processes` | Linux focused passed; original byte files and separate metric snapshots retained. Candidate matrix pending. |
| A03 Unknown / old attempts | `test_observation_journal`, `test_observation_processes`, `test_stall_supervision` | Source regressions cover inaccessible identity, collector replacement and old reports. No PID-only exit inference. Full candidate regression pending. |
| A04 Effective deadlines | Native Run/tool cutoff witness; `test_runtime_deadline_envelopes`, `test_execution_budget` | Actual shortest cutoff, stopped process tree, inherited parent window and reserve semantics covered. Reported tool cause keeps its original message. Candidate matrix pending. |
| A05 Restart and short waits | Native controller crash after confirmed entry; native short `Task.wait`; budget/recovery tests | Original cutoff survives rollback/restart; exhausted business is refused; caller wait does not cancel. Candidate matrix pending. |
| A06 Parent waits / capacity | `test_managed_children_capacity`, `test_runtime_deadline_envelopes`, native saturation pressure witness | Actual children return success and original failure; dedicated capacity and successor work covered. Installed ModPort path and matrix pending. |
| A07 Rejection / partial registration | Child admission suite and native cross-store controller crash | Actual independent request reservation exists while Kernel child is absent; exit 73 and original-budget recovery close the wait without child business. Earlier stalled runs remain retained. Candidate matrix pending. |
| A08 Cancellation / natural completion | Native pressure, Runtime lifecycle, Windows Job and sandbox tests | Linux descendant markers stop; Kernel winner and cleanup proof remain distinct. Current Windows Jobs pending. |
| A09 Cleanup failure / exit cause | `test_sandbox_runtime` cleanup-failure restart with native worker business-call log; process exit classifiers; shared cgroup clue witness | Restart retries disposal only and keeps collected output; call count does not increase. Exit 137 remains status/unknown OOM even with readable shared cgroup counters. Provider is explicitly a persistent fake; native worker is real. Candidate matrix pending. |
| A10 Stall windows | `test_stall_supervision` | Complete consecutive windows, activity distinctions, exemptions, unknown gaps, replacement and rollback covered. Candidate regression pending. |
| A11 Durable notification | Two real evaluator processes; abrupt exit after orchestration enqueue; repeated native crashes through delivery exhaustion and explicit retry | Same notice ID, one application notification, bounded attempts and explicit dead state verified. Candidate regression pending. |
| A12 Conditional disposition | Actual progress commit between public recheck and cancellation transaction; saturated native workers with blocked callback | Confirmed progress defeats stale cancellation; separate capacity keeps local deadlines working. Candidate matrix pending. |
| A13 Pressure / bounded reads | Native pressure suite: 10,000 summaries, overflowing raw output and blocked activity writer; independent settlement notes; oversized receipts / exhausted query budget | Kernel and telemetry pressure do not claim a completed observation. Runtime and standalone reads expose loss, partial receipts, bounds and cursors. Latest candidate regression pending. |
| A14 Compatibility / upgrade | Explicit copy upgrade and storage regressions; separately installed historical `v0.7.0.dev0` writer | Actual old installed writer rejects new storage with `StorageIsolationError`; current writer reopens it. Full public API and pending-obligation upgrade regression pending. |
| A15 Installed entry | Isolated wheel consumer suite and portable public example | Fresh final wheel installation/import proof pending. Earlier wheels do not count. |
| A16 Current ModPort | Current SDKHandler/budget/raw stream adapters; staged actual reviewer → stdio MCP → host schedule → SDK child → host response witness | Ten staged source tests passed, including original storage failure and original tool deadline. Remaining live rework files await cross-project approval; installed candidate and real provider/SSE witness pending. No Minecraft Run was launched. |
| A17 Native Windows | `test_windows_runtime`, portable native observability/deadline/pressure suites | Linux mocks are not native acceptance. Windows x64/ARM64 jobs and raw Job evidence pending. Linux-only cgroup cases do not apply to Windows. |
| A18 Complete candidate regression | Existing 16 environment combinations, public types, README and portable examples | Pending. Earlier full failures and an interrupted run are not passes. |

## Current raw host evidence

| Command/result | Retained evidence |
| --- | --- |
| 46 native/inspection/settlement checks passed in 56.209s | `/tmp/sdk-final-native-inspection-regression.log`; native directories printed in that log |
| 35 settlement/readonly/native-pressure checks passed in 65.315s | `/tmp/sdk-final-readonly-settlement-pressure.log`; pressure JSON files printed in that log |
| 29 nested control / durability / child checks passed in 10.940s | `/tmp/sdk-nested-bounded-control-final.log` |
| 31 child contention / clock checkpoint / admission checks passed in 31.542s | `/tmp/sdk-child-contention-final-focused.log`; controlled clock and real SQLite evidence paths printed in the checkpoint log |
| 50 deadline / cancellation / bounded control / durability checks passed in 78.967s | `/tmp/sdk-child-contention-budget-cancel-final2.log` |
| Native registration crash and corrected saturated-worker supervision passed in 20.186s | `/tmp/sdk-current-binding-crash-pressure.log`; `/tmp/sdk-observability-pressure-mcuj611t/evidence.json` |
| Real blocked current binding, background recovery, historical attempt protection and direct child compatibility passed | `/tmp/sdk-current-binding-recovery-focused.log`; raw JSON paths printed in that log |
| Native cleanup failure then restart passed | `/tmp/sdk-native-cleanup-restart.log` |
| Repeated real notification bridge crashes and retry passed | `/tmp/sdk-stall-repeated-native-crash.log` |
| Historical installed writer rejected new layout | `/tmp/sdk-historical-writer-evidence.json`; `/tmp/sdk-historical-current-reopen.log` |
| Native shared-cgroup clue plus actual exit 137 passed | `/tmp/sdk-native-shared-oom-clue.log`; `/tmp/sdk-observability-native-2jg_2v20` |
| Five public typing fixtures passed; six README examples passed | `/tmp/sdk-docs-latest.log`; current typing command output |

These focused results precede the final candidate freeze. Final installed and
CI results will supersede them for acceptance while preserving failure history.

The first frozen source commit, `0a1304f`, was not accepted: its installed
public parent/child example failed with a real SQLite writer conflict.
`/tmp/sdk-observability-installed-example-final3.log` and
`/tmp/sdk-installed-parent-lock-causal/run-02/parent-exception.json` retain the
original error and already successful child result. The full regression was
interrupted after that finding; `/tmp/sdk-observability-full-regression-final3.log`
is not a pass. Later source fixes retry only transient storage admission errors
within the original call window, retain result publication obligations and
preserve stricter clock checkpoints across replay.

The later combined native batch also found a missing current binding under
ordinary concurrent SDK writers, leaving one subscribed worker without stall
windows. `/tmp/sdk-child-contention-native-pressure-settlement.log` and
`/tmp/sdk-observability-pressure-0h6ryy0f/evidence.json` preserve that failure.
The driver now retries the binding through its existing bounded background
flusher; the corrective native run above passed. A new complete frozen
candidate run remains necessary.

## Review and limits

Independent reviews found and verified fixes for entry authority, original
completion timestamps, deferred result settlement, transient SQLite errors
misclassified as revoked authority, lost final-flush evidence, missing native
bootstrap errors, original deadline cause, readonly receipt mutation, nested
control deadlines, child storage replay, conservative clock receipt recovery,
targeted execution capacity and query-size fallback. Current candidate-wide verification
remains required after those fixes.

The independent journals retain facts; they do not authorize a new execution,
extend an original budget or prove application consumption. Missing storage,
inaccessible processes and unprovable clocks remain unknown. Historical
execution inputs and evidence are preserved. No additional checksum,
fingerprint or candidate/rubric identity gate is introduced.
