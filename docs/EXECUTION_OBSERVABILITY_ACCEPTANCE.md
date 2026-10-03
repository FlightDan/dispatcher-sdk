# Execution observability acceptance evidence

This index tracks [T01–T09 and A01–A18](EXECUTION_OBSERVABILITY_GOAL.md).
The implementation is not yet fully accepted. Focused checks have passed on
Linux x86_64. Installed candidate `269f143` completed a real two-turn production
supervisor and native SSE summary, but failed the complete regression.
The corrective source changes still need a fresh frozen installed candidate,
complete regression, native Windows matrix and remaining live ModPort handoff.
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
| A15 Installed entry | Isolated wheel consumer suite and portable public example | `269f143` clean-wheel import and original parent12/child5/wait15 example passed. Its complete installed consumer suite failed; corrective candidate validation remains required. |
| A16 Current ModPort | Current SDKHandler/budget/raw stream adapters; staged actual reviewer → stdio MCP → host schedule → SDK child → host response witness | Installed `269f143` completed the production supervisor's two real model requests with a validated successful business decision and a genuine native SSE summary. The staged handoff then exposed lost resource waits; the SDK correction is independently reviewed but needs installed replay. Remaining live rework files await cross-project approval. No Minecraft Run was launched. |
| A17 Native Windows | `test_windows_runtime`, portable native observability/deadline/pressure suites | Linux mocks are not native acceptance. Windows x64/ARM64 jobs and raw Job evidence pending. Linux-only cgroup cases do not apply to Windows. |
| A18 Complete candidate regression | Existing 16 environment combinations, public types, README and portable examples | `269f143` outer run of 857 tests had 2 failures and 16 skips; nested installed run of 852 tests had 1 failure and 16 skips. Corrective full candidate and native matrix remain pending. Skips and partial passes do not fulfill required platforms. |

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
| Installed `a8403c3` original public example passed three times | `/tmp/sdk-observability-installed-import-final5.json`; `/tmp/sdk-observability-installed-example-final5-run*.log` |
| Installed ModPort stdio MCP / child raw-error handoff passed ten checks | `/tmp/modport-rework-installed-final5.log` |
| Actual native summary SSE completed; supervisor business timed out | `/tmp/modport-a16-3e4mk7z4/completion.json`; `summary-evidence.json`, `native-summary.txt`, `supervisor-evidence.json`; `/tmp/modport-a16-launch-VLnk45-completion.json` |
| Corrective receipt / child / clock checks passed 63 in 58.878s | `/tmp/sdk-receipt-delivery-corrections-focused.log` |
| Corrective native / pressure / child / entry checks passed 42 in 114.595s | `/tmp/sdk-native-corrections-final.log` |
| Real dual-store contention, receipt-only retry close, and readonly admission passed 4 in 10.073s | `/tmp/sdk-double-settlement-read-final.log`; original outcome artifacts printed in that log |
| Cancellation under a locked diagnostic writer plus existing receipts passed 19 in 34.967s | `/tmp/sdk-cancel-order-public-regression.log`; `/tmp/sdk-cancel-telemetry-order-jizf77lp/evidence.json` |
| Child result delivery under Kernel contention passed eight checks and one final native witness | `/tmp/sdk-child-completed-delivery-writer-final.log`; `/tmp/sdk-child-completed-delivery-writer-proof.log`; `/tmp/sdk-child-delivery-writer-cutoff-eq4mgwoe/evidence.json` |
| Frozen `269f143` complete source and installed regressions failed | `/tmp/sdk-observability-full-regression-final6.log`; `/tmp/sdk-child-delivery-writer-cutoff-h4hyjjxv/evidence.json` |
| Installed `269f143` completed production supervisor and native SSE summary | `/tmp/modport-a16-4rqy492p/completion.json`; `/tmp/modport-a16-provider-partial-final6.json`; `/tmp/modport-a16-installed-import-preflight-final6.json` |
| Original one-second retry-classification fixture genuinely exhausted its original window | `/tmp/sdk-final6-retry-classification-evidence.json`; `/tmp/sdk-final6-retry-classification-probe.log` |
| Corrective wait, attachment, journal and supervision checks passed 65 in 47.338s | `/tmp/sdk-wait-attachment-integrated.log`; context attachment JSON paths printed in the log |
| Corrective readonly proof and native child delivery checks passed 13 in 20.340s | `/tmp/sdk-child-completion-readonly-delivery.log`; `/tmp/sdk-child-delivery-writer-cutoff-ilgtye5o/evidence.json` |
| Final child receipt, clock, readonly delivery and runtime checks passed 33 in 42.237s | `/tmp/sdk-child-corrections-final7.log`; `/tmp/sdk-child-delivery-writer-cutoff-kvfvpywd/evidence.json` |
| Expired receipt inspection and native revoked-parent recovery passed 14 in 18.210s | `/tmp/sdk-child-receipt-revoked-native.log`; `/tmp/sdk-observability-native-u5uuwwwd/recovered-registration.json` |
| Final native startup, restart, deadlines, cancellation, bounded pressure and runtime checks passed 15 in 78.598s | `/tmp/sdk-corrections-native-final7.log`; native artifact paths printed in the log |
| Final five public typing fixtures passed | `/tmp/sdk-observability-types-final7-frozen.log` |

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

The later frozen `a8403c3` complete run finished, rather than being interrupted:
`/tmp/sdk-observability-full-regression-final5.log` retains all three outer
failures and three nested installed-suite errors. Actual cancellation committed
before a late file write, but optional diagnostic writes delayed local revocation.
An installed pressure worker was reaped at its deadline while simultaneous
receipt and lifecycle admission failures dropped its only original timeout
result; `/tmp/sdk-observability-pressure-fx63k80k/evidence.json` and its sidecars
retain that causal evidence. The installed child failure also exposed a result
committed before its cutoff but delivered through the request journal afterward.
The corrective witnesses above preserve the same business deadlines and original
results. A source-focused pass does not supersede the failed frozen candidate.

Both provider witnesses used fresh temporary Run identities, unchanged original
110-second total deadlines, seven claims and no automatic retries. The first
harness allocated an incorrect 80-second supervisor stage and failed before
summary registry entry; `/tmp/modport-a16-o2mkelk8/completion.json` retains it.
After correcting the harness, native SSE reported one model request, 106 events,
96 text chunks and 38,278 stdout bytes. The production supervisor's planning
completed in 43.040s; execution exhausted its remaining 34.711s while retaining
the production settlement reserve. Its SDK `succeeded` state records successful
return of a failed business result and does not establish A16 completion.

The later fresh 180-second temporary Run completed both formal supervisor turns
and the native summary under its unchanged original deadline and seven claims.
It used the installed `269f143` SDK and current production handlers. The supervisor
reported two requests, ten model events, two text events and 1,909 stdout bytes;
the summary reported one request, 98 events, 88 text events and 35,434 stdout bytes.
This is genuine normal-provider evidence, but it does not cover the remaining
live rework, cancellation or recovery requirements.

The `269f143` full regression retained two failures: one source child result
delivery proof and one nested installed retry-classification check. Receipt
inspection had classified a bounded SQLite read timeout as unknown clock
continuity. The correction retries only typed transient inspection failure inside
the unchanged call window and forbids delivery if stronger clock facts remain
unread. Independent traces also showed a write-based parent verification spending
0.111s of a 0.1s proof allowance; the final proof checks are read-only and retain
the same allowance, cancellation recheck and logical clock floor. The classification
fixture now specifies five seconds for both attempts after the raw installed trace
proved its original one-second cutoff had expired; the SDK never resets that cutoff.

The staged ModPort test exposed missing memory/workspace waits with a misleading
complete report. Wait endpoints now use bounded replay with their original
timestamps. Retained loss makes supervision unknown; closed collector waits cannot
exempt it. An independent real contention probe also exposed missing child
capability after optional recorder admission failed. Workers now attach the host's
existing sidecar without constructor I/O and validate it before the first bounded
operation, retaining child availability without recreating missing storage.

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
