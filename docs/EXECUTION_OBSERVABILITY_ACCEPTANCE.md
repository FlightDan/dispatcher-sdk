# Execution observability acceptance evidence

This index tracks [T01–T09 and A01–A18](EXECUTION_OBSERVABILITY_GOAL.md).
Scope revised on 2026-10-04: this Goal covers SDK functionality, robustness and
maintainability only. The user has activated the revised SDK-only Goal. ModPort adaptation, production-provider requests and cross-project
writes are outside the revised completion criteria. Historical integration evidence
is retained below; it does not establish the new SDK-only A16.

Local Linux acceptance passed on implementation commit
`969f0da7f2bdbcda9dc4235e0744e0176e0475b2` (Linux x86_64, Python 3.12).
The complete regression ran 952 tests in 1629.062 seconds with zero failures or
errors and 16 platform skips. Its freshly rebuilt and installed SDK also passed
the complete isolated suite and all five public end-to-end scenarios. The original
portable example also passed in a separate fresh installation with isolated
imports outside the checkout. Five public typing fixtures passed. The latest documentation check passed 546 local links
and six README examples with no skips.

The Goal is not complete: native Windows and the existing 16-environment CI
matrix have not run for this candidate. The 16 Linux skips do not count as
Windows acceptance. The user explicitly authorized the source/history push on
2026-10-04; branch `work/execution-observability-20261003` was pushed successfully.
The first [CI run](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37188996228)
on `889d1d9` failed before creating any jobs. Its workflow referenced `runner.temp`
in job-level `env`, where GitHub does not allow the runner context. Evidence
directory setup now runs as a Python step through `GITHUB_ENV`; artifact upload
uses the same runner temporary directory. SDK code and test budgets are unchanged.
Raw run metadata is retained at `/tmp/sdk-ci-run-37188996228.json`. This failed
run is not matrix acceptance. The corrected workflow launched
[run 37189113536](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37189113536)
on `0fc705d`; all 16 environments started and the history scan passed, while tests
remain in progress. Independent platform-evidence review identified that successful
nested installed-suite output was captured but discarded. The fixture now saves
the exact command, original timeout, return code and complete stdout/stderr under
each public consumer's `installed-suite` directory, including failure and timeout.
Three bounded local success/failure/timeout probes verified retention at
`/tmp/sdk-installed-suite-log-check-0290z0z5`. No release is authorized.

T01–T07 implementation and Linux evidence are present. T08 has local installation
and regression evidence but still needs the native matrix; T09 independent review
and corrections are complete locally, while final acceptance depends on T08.

| Completion condition | Current status |
| --- | --- |
| G1 All mandatory scenarios | Pending native Windows and CI; local applicable scenarios passed |
| G2 Installed public API, types, docs and examples | Passed on Linux; imported package is outside the checkout |
| G3 Same candidate across required platforms | Pending Windows and CI for this implementation |
| G4 Compatibility and explicit storage upgrade | Linux regression passed; native matrix still required |
| G5 Ownership and maintainability review | Reviewed with corrections verified locally; limitations retained below |

## Earlier local failures and corrections

The `a876f9d` source failure exposed an SDK defect: `InspectionBudgetExceeded`
from one bounded observation read escaped child waiting even with about 2.8
seconds left in the original call window. The child had already succeeded and
its response publication was deliberately held. A real journal-read reproduction
failed on the frozen code; the correction classifies only this SDK-owned read
expiry for retry inside the same original window. Persistent expiry retains the
last original error; completion proof remains a single bounded read, and generic
timeouts, permanent errors and revoked parent authority remain immediate.
Independent review found no control/replay blocker. The corrected code passed the
complete Linux regression on `969f0da`.

The earlier `e14faf5` installed failures were a raw parent `OperationalError: database is
locked` around the original two-second child-call cutoff, and a receipt-contention
fixture requiring 0.2 seconds of waiting after setup had already consumed part of
its original 0.3-second window. The latter now checks original-window exhaustion
directly, preserving its budget and upper bound. The child business completed
before cutoff, but its first explicit postcommit observation was later; neither
the exact commit visibility nor the failing SQL operation is established. One
same-budget diagnostic on freshly installed `e14faf5` passed without reproducing
the error. The nominal activity/capacity fixture now declares the public example's
parent-twelve/child-five-second windows before launch and retains raw exception
stacks. This removes an unsupported performance assumption; it does not explain
the original boundary failure. Dedicated cutoff and publication-contention
witnesses retain their original windows.

One failure in both suites came from a fixture requiring exactly two cancellation
attempts. Retained facts show two uncommitted BUSY attempts, followed by correct
rejection of the unchanged stale token inside the original window. The fixture
now checks those invariants rather than a scheduling-dependent count. Two
cancellation fixtures failed before observing their business-entry markers within
an assumed 0.5 seconds; their deleted stores prevent attribution beyond that
precondition. Those fixtures now use an original five-second readiness bound,
retain entry evidence and keep their original two-second execution budgets. The
native cancellation witness also requires cancellation and synchronous cleanup
before the original work cutoff, excluding natural timeout as a false pass.
The nested parent/child fixture returned a value without `child`; its deleted
store leaves the original child error unknown. One exact installed diagnostic
passed with unchanged parent-five/child-two-second budgets. That fixture now
always retains raw results, child errors and databases. These new focused passes
do not turn the failed complete regression into a pass.

The earlier frozen `2ab808e` candidate passed installed success, raw failure,
tool-budget scenarios and the original public example. Its silence scenario failed
before policy registration committed, at the original 0.1-second observation write
window. Registering once before starting the public host removed competing execution
collectors without changing that window; one independent installed run then passed.
No complete `2ab808e` regression was launched. A separate native probe found a
remaining entry-packet wall sample that shortened a deadline without retaining its
floor; the packet now derives both bounds from the committed ACK and native elapsed
time. The correction is included in the passing Linux candidate. The failed native child-delivery
cases did not establish timely child entry within their original two-second
window. They also exposed an SDK defect: inherited parent start time caused
completion to reject a valid pre-entry failure. That correction preserves pending
entry authority and original constraints. A separate native probe confirmed that
parent-only timer observations were lost on clock rollback, allowing a second
business attempt; timer floors now propagate with original result obligations.
These corrections are included in the passing `969f0da` Linux regression.

The nested dead-bridge notification failure remains unattributed: its temporary
store was deleted, and the log only shows that no dead notice arrived during the
original wait. The fixture now retains observations, windows, bridge calls and
health diagnostics; one focused execution passed with unchanged timing. The
crash-journal subprocess exceeded its original default 0.1-second write window
before commit. Its crash-survival fixture now declares one-second operation
windows before launch and retains raw stages; the original failure is preserved.

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
All Linux-applicable witnesses below passed in the complete source and installed
candidate regression. Native Windows and the remaining CI environments are
unverified, including platform-specific cases skipped on Linux.

| Scenario | Implementation and witness | Current evidence / remaining requirement |
| --- | --- | --- |
| A01 Startup phases | `test_observability_native_acceptance`: queue, real deserialization, ready, entry, model request, raw bootstrap failure | Linux source and installed candidate passed; readiness and entry facts survive an unavailable activity writer. Windows pending. |
| A02 Raw output and progress | Same native suite: segmented bytes, heartbeat, tool response, new/replayed progress; `test_observation_processes` | Linux focused passed; original byte files and separate metric snapshots retained. Candidate matrix pending. |
| A03 Unknown / old attempts | `test_observation_journal`, `test_observation_processes`, `test_stall_supervision` | Source and installed regressions cover inaccessible identity, collector replacement and old reports. No PID-only exit inference. Native matrix pending. |
| A04 Effective deadlines | Native Run/tool cutoff witness; `test_runtime_deadline_envelopes`, `test_execution_budget` | Actual shortest cutoff, stopped process tree, inherited parent window and reserve semantics covered. Reported tool cause keeps its original message. Candidate matrix pending. |
| A05 Restart and short waits | Native controller crash after confirmed entry; native short `Task.wait`; budget/recovery tests | Original cutoff survives rollback/restart; exhausted business is refused; caller wait does not cancel. Candidate matrix pending. |
| A06 Parent waits / capacity | `test_managed_children_capacity`, `test_runtime_deadline_envelopes`, native saturation pressure witness | Actual children return success and original failure; dedicated capacity and successor work passed, including installed end-to-end witnesses. Native matrix pending. |
| A07 Rejection / partial registration | Child admission suite and native cross-store controller crash | Actual independent request reservation exists while Kernel child is absent; exit 73 and original-budget recovery close the wait without child business. Earlier stalled runs remain retained. Candidate matrix pending. |
| A08 Cancellation / natural completion | Native pressure, Runtime lifecycle, Windows Job and sandbox tests | Linux descendant markers stop; Kernel winner and cleanup proof remain distinct. Current Windows Jobs pending. |
| A09 Cleanup failure / exit cause | `test_sandbox_runtime` cleanup-failure restart with native worker business-call log; process exit classifiers; shared cgroup clue witness | Restart retries disposal only and keeps collected output; call count does not increase. Exit 137 remains status/unknown OOM even with readable shared cgroup counters. Provider is explicitly a persistent fake; native worker is real. Candidate matrix pending. |
| A10 Stall windows | `test_stall_supervision` | Complete consecutive windows, activity distinctions, exemptions, unknown gaps, replacement and rollback passed. Native matrix pending. |
| A11 Durable notification | Two real evaluator processes; abrupt exit after orchestration enqueue; repeated native crashes through delivery exhaustion and explicit retry | Same notice ID, one application notification, bounded attempts and explicit dead state passed. Native matrix pending. |
| A12 Conditional disposition | Actual progress commit between public recheck and cancellation transaction; saturated native workers with blocked callback | Confirmed progress defeats stale cancellation; separate capacity keeps local deadlines working. Candidate matrix pending. |
| A13 Pressure / bounded reads | Native pressure suite: 10,000 summaries, overflowing raw output and blocked activity writer; independent settlement notes; oversized receipts / exhausted query budget | Kernel and telemetry pressure do not claim a completed observation. Runtime and standalone reads expose loss, partial receipts, bounds and cursors. Linux regression passed; native matrix pending. |
| A14 Compatibility / upgrade | Explicit copy upgrade and storage regressions; separately installed historical `v0.7.0.dev0` writer | Historical installed writer rejects new storage with `StorageIsolationError`; current writer reopens it. Full public API and pending-obligation upgrade regression passed on Linux. Native matrix pending. |
| A15 Installed entry | Isolated wheel consumer suite and portable public example | `969f0da` rebuilt-wheel consumer, complete source/installed suites and separately installed original portable example passed. Native matrix pending. |
| A16 Independent SDK end-to-end | Installed public APIs, real handlers/processes, local byte/tool fixtures and persisted recovery; no ModPort or external model dependency | All five public-entry scenarios passed on the `969f0da` isolated rebuilt consumer: success/raw failure, output/silence, parent-child/tool budgets, cancellation and cleanup recovery without repeated business. Native matrix remains required. Historical ModPort checks are not a substitute. |
| A17 Native Windows | `test_windows_runtime`, portable native observability/deadline/pressure suites | Linux mocks are not native acceptance. Windows x64/ARM64 jobs and raw Job evidence pending. Linux-only cgroup cases do not apply to Windows. |
| A18 Complete candidate regression | Existing 16 environment combinations, public types, README and portable examples | `969f0da` complete regression passed: 952 tests, 16 platform skips; nested complete installed suite passed. Public types passed. Native matrix remains pending; Linux skips do not fulfill required platforms. |

## Retained raw host evidence

| Command/result | Retained evidence |
| --- | --- |
| Final documentation: 546 local links and six README examples passed, zero skipped | `/tmp/sdk-observability-docs-final13.log` |
| Frozen `969f0da` original portable example passed from a fresh wheel installation, isolated imports outside checkout | `/tmp/sdk-observability-installed-import-final13.json`; `/tmp/sdk-observability-installed-example-final13.log`; `/tmp/sdk-observability-wheel-final13.log`; `/tmp/sdk-observability-install-final13.log` |
| Frozen `969f0da`: complete regression passed, 952 tests / 1629.062s / 16 platform skips; rebuilt installed complete suite and five public scenarios passed | `/tmp/sdk-observability-full-regression-final13.log`; `/tmp/sdk-full-final13-evidence`; `/tmp/sdk-full-final13-evidence/sdk-observability-consumer-qyjjnd4h/summary.json`; its `environment.json` records the actual `/tmp/tmpekzukomp/venv/lib/python3.12/site-packages` import |
| Integrated read-expiry, native held-publication, receipt and readonly-delivery checks: 29 passed in 37.976s; final three read-expiry checks and five public typing fixtures passed | `/tmp/sdk-final13-child-inspection.log`; `/tmp/sdk-final13-child-inspection-evidence`; `/tmp/sdk-final13-inspection-final.log`; `/tmp/sdk-final13-inspection-final-evidence`; `/tmp/sdk-observability-types-final13.log` |
| Frozen `a876f9d`: outer 949 / one failure / 16 skips; complete nested installed suite passed, including all five public scenarios | `/tmp/sdk-observability-full-regression-final12.log`; `/tmp/sdk-full-final12-evidence`; `/tmp/sdk-full-final12-evidence/sdk-observability-consumer-_fob56cj/summary.json` |
| Parent aborted on one read expiry despite remaining original budget and authoritative child success | `/tmp/sdk-full-final12-evidence/sdk-child-completed-delivery-evidence-vix3480r/success.json`; same run's installed success/failure witnesses are in `sdk-child-completed-delivery-evidence-zmt_6_5w` |
| Causal journal-read reproduction failed on frozen source, three staged corrective checks passed; original budgets/error identity/proof bound preserved | `/tmp/sdk-final12-child-inspection-stage/evidence.json`; `/tmp/sdk-final12-child-inspection-stage` retains original and corrected command logs |
| Revised receipt exhaustion and nominal parent/child integration: 16 passed in 25.826s; independent review found no blockers | `/tmp/sdk-final12-child-receipt.log`; `/tmp/sdk-final12-child-receipt-evidence` |
| Current documentation: 546 local links and six README examples passed, zero skipped | `/tmp/sdk-observability-docs-final12.log` |
| Frozen `e14faf5` full regression failed: outer 949 / one failure / 16 skips; nested 944 / two failures / 16 skips; rebuilt-wheel five public scenarios passed | `/tmp/sdk-observability-full-regression-final11.log`; `/tmp/sdk-full-final11-evidence`; `/tmp/sdk-full-final11-evidence/sdk-observability-consumer-scerstph/summary.json` |
| Installed parent failed with original raw SQLite BUSY around tool cutoff; child business timely, exact committed visibility and failing SQL unknown | `/tmp/sdk-full-final11-evidence/sdk-runtime-child-publication-8hg3pu8d/evidence.json`; original databases retained alongside it |
| Same original parent-five/child-two-second diagnostic on fresh installed `e14faf5` passed once in 3.787s; no failure reproduction | `/tmp/sdk-final11-child-diagnostic.log`; `/tmp/sdk-final11-child-diagnostic-evidence/sdk-runtime-child-publication-dfwa7sxr/evidence.json`; staged fixture `/tmp/sdk-final11-child-diagnostic-stage` retains the original configuration |
| Corrected cancellation admission assertions: 12 passed in 10.132s; both revised native/thread cancellation witnesses passed, followed by the reviewed native cutoff proof | `/tmp/sdk-final11-cancel-fixture.log`; `/tmp/sdk-final11-cancel-evidence`; `/tmp/sdk-final11-cancel-native.log`; `/tmp/sdk-final11-reviewed-cancel.log`; `/tmp/sdk-final11-reviewed-cancel-evidence` |
| Exact installed child diagnostic passed once in 3.413s with original parent-five/child-two-second windows; prior failure cause remains unknown | `/tmp/sdk-final10-child-diagnostic/summary.json`; `/tmp/sdk-runtime-child-publication-e5om8c1k/evidence.json`; import points to final10 installed site-packages |
| Frozen `c1471ee` full regression failed: outer 949 / three failures / 16 skips; nested 944 / two failures / one error / 16 skips | `/tmp/sdk-observability-full-regression-final10.log`; `/tmp/sdk-full-final10-evidence` |
| Frozen installed `c1471ee`: five public scenarios and original example passed; fresh import is outside the checkout | `/tmp/sdk-a16-installed-final10/summary.json`; `/tmp/sdk-observability-installed-import-final10.json`; `/tmp/sdk-observability-installed-example-final10.log`; nested five scenarios `/tmp/sdk-full-final10-evidence/sdk-observability-consumer-we_e2bxv/summary.json` |
| Original cancellation fixture false count assumption: two BUSY/no-write attempts then unchanged-token CASConflict; execution still running, progress revision one | `/tmp/sdk-full-final10-evidence/sdk-cancel-admission-ds12fnvx/evidence.json`; independent review accepted stronger original-window/authority assertions |
| Final combined entry-packet, parent/supervisor/Windows floor and native deadline checks: 33 passed in 29.144s | `/tmp/sdk-final10-focused.log`; `/tmp/sdk-final10-focused-evidence`; full frozen regression remains required |
| Entry-packet correction: one actual native business attempt, no false timeout/retry; native elapsed/reserve projection passed | `/tmp/sdk-entry-packet-clock-regression.log`; `/tmp/sdk-native-entry-packet-clock-htlryqe_/evidence.json`; `/tmp/sdk-entry-packet-native-elapsed-ggjqappz/evidence.json`; two tests passed in 1.371s |
| Installed `2ab808e`: three scenarios and original example passed; silence failed before watch registration committed | `/tmp/sdk-a16-installed-final9`; `/tmp/sdk-a16-installed-final9.log`; `/tmp/sdk-observability-installed-import-final9.json`; `/tmp/sdk-observability-installed-example-final9.log` |
| Silence public setup-order correction passed once on the same installed SDK with original windows | `/tmp/sdk-silence-setup-installed-97150h_w/evidence/summary.json`; `watch-registration.json` records the original 0.1-second write window and nonreplayed pending policy before public start |
| Native worker entry-packet wall sample lost on frozen `2ab808e`: two actual business invocations after rollback | `/tmp/sdk-worker-entry-floor-cae3vucc/evidence.json`; original 10-second execution and 90-second lease; no retry-window change |
| Revised public contention fixture passed with original writer/caller bounds and actual SQLite BUSY, one business call and one callback | `/tmp/sdk-final9-public-contention-fixture.log`; `/tmp/sdk-final9-fixture-evidence/sdk-public-admission-contention-jut999bg/evidence.json`; independent review included notification-result transaction setup |
| Final native budget/startup/cancellation-tree boundary checks: 34 passed in 43.424s | `/tmp/sdk-final9-boundary.log`; `/tmp/sdk-final9-boundary-evidence`; original startup failure semantics preserved |
| Public typing and documentation after corrective changes passed | `/tmp/sdk-observability-types-final9.log` (five fixtures); `/tmp/sdk-observability-docs-final9.log` (546 links, six README examples, zero skips) |
| Combined corrective focus: 140 tests / one failure / one error / 16 platform skips; not a pass | `/tmp/sdk-final9-focused.log`; startup guard expectation exposed a classification distinction, and a public contention fixture failed before acquiring its writer |
| Native startup cause distinction: inherited tool expiry is timeout; internal startup guard retains original startup failure | `/tmp/sdk-startup-authority-classification.log`; two checks passed in 2.551s; later original-decision capture included in next boundary run |
| Supervisor-only native floor and deterministic signal interleaving checks passed | `/tmp/sdk-supervisor-floor-regression.log`; `/tmp/sdk-alarm-floor-interleaving-regression.log`; independent review verified separate alarm slot and original timeout decision |
| Windows watchdog floor checks: 10 portable checks passed; not native Windows acceptance | `/tmp/sdk-windows-budget-floor-final.log` |
| Frozen `80906d2` full regression failed: outer 934 / four failures / 16 skips; nested 929 / one failure / 16 skips | `/tmp/sdk-observability-full-regression-final8.log`; `/tmp/sdk-full-final8-evidence` |
| Frozen installed public SDK: all five independent scenarios and original example passed | `/tmp/sdk-a16-installed-final8/summary.json`; `/tmp/sdk-observability-installed-import-final8.json`; `/tmp/sdk-observability-installed-example-final8.log` |
| Parent-only native timer floor lost before correction: retry entered a second real worker after rollback | `/tmp/sdk-parent-deadline-floor-kp_0i4c_/evidence.json`; original 10-second budget and 90-second lease |
| Integrated parent floor, child pre-entry and admission corrections: 28 checks passed in 33.838s | `/tmp/sdk-parent-floor-integration.log`; `/tmp/sdk-parent-budget-floor-ifllip6t/evidence.json`; supervisor/Windows follow-up pending |
| Dead-bridge focused diagnostic passed with original timing; previous installed cause unknown | `/tmp/sdk-dead-bridge-88jtno88/evidence.json` |
| Crash-journal subprocess committed, exited 42 and reopened exact original records with authored one-second operation windows | `/tmp/sdk-settlement-process-exit-dk36npow/evidence.json` |
| Corrective integrated regression: 140 tests passed in 162.589s after fixing all preceding entry/completion failures | `/tmp/sdk-corrective-final-focused.log`; fresh wheel, complete suite and CI remain pending |
| Actual Runtime and fresh settlement journal reopen under rollback: original result restored with one business call; 17 targeted checks passed in 5.089s | `/tmp/sdk-completion-reopen-local-proof-final.log`; `/tmp/sdk-runtime-budget-reopen-8elqhajx/evidence.json`; independent review found no remaining blocker |
| Corrective public SDK source consumer: all five scenarios passed; no external provider or application adapter | `/tmp/sdk-a16-integrated-corrections-20261004/summary.json`; `/tmp/sdk-a16-integrated-corrections-20261004.log`; each scenario retains input, process, byte, budget and outcome records |
| Cancellation admission: 12 integrated checks passed in 10.634s; independent review found no blockers | `/tmp/sdk-cancel-admission-integrated.log`; original-window writer/progress/commit evidence paths printed in the log |
| Thread/native completion clock rollback: four actual worker checks passed in 6.494s; actual Runtime reopen subsequently exposed an additional validation-order gap | `/tmp/sdk-terminal-budget-outcomes.log`; `/tmp/sdk-runtime-budget-reopen-regression.log`; `/tmp/sdk-runtime-budget-reopen-r91fn9z3/evidence.json` |
| Diagnostic retention and entry contention: 10 checks passed in 9.390s; five typing fixtures and six README examples passed | `/tmp/sdk-diagnostic-compatibility.log`; `/tmp/sdk-observability-types-corrective.log`; `/tmp/sdk-observability-docs-corrective.log` |
| Wider corrective integration initially failed: 107 tests, two failures and nine errors; failures retained for causal fixes | `/tmp/sdk-budget-entry-integration.log`; complete corrective rerun pending |
| Completion primitive and unentered-admission corrections: 14 checks passed in 4.751s | `/tmp/sdk-completion-unentered-edge.log` |
| First revised source consumer success failed on explicit unknown progress receipt after its original 0.1s operation window; failure/budget/cleanup scenarios passed | `/tmp/sdk-harness-reviewed-ifl6ekyz`; subsequent consumer declares each original progress operation window, bounded by remaining execution time, and performs no retry loop |
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
| Frozen `5d9db60` installed import and unchanged public example passed | `/tmp/sdk-observability-installed-import-final7.json`; `/tmp/sdk-observability-installed-example-final7.log` |
| Frozen `5d9db60` complete regression failed: outer 891 in 1633.001s; nested 886 in 814.110s | `/tmp/sdk-observability-full-regression-final7.log` |
| Installed SDK thread-entry probe retained real SQLite BUSY before business entry | `/tmp/sdk-thread-entry-writer-original-ry7d0y38/evidence.json` |
| Historical staged ModPort handoff passed ten checks with installed `5d9db60`; outside revised A16 | `/tmp/modport-rework-installed-final7.log` |

These records span multiple candidates. The latest Linux complete regression
passed on `969f0da`; earlier failures remain historical failures, including cases
whose exact cause could not be recovered. Future CI results must identify their
candidate while preserving this history.

The `5d9db60` outer errors were an expired lease during a recovery fixture, an
installed-suite failure, and no dead notification within the application fixture's
original bound. The installed failure returned `child_wait_timeout` instead of the
expected successful child delivery. These require separate causal diagnosis;
no ModPort code participates in these SDK regressions. A subsequent standalone
installed SDK probe confirmed that a 0.25-second SQLite writer hold caused a single
entry-confirmation attempt to fail within an original five-second execution window;
business never ran, and the published error retained only the exception class.
That probe demonstrates an SDK robustness/diagnostic issue, but does not by itself
prove the cause of every full-suite failure. Work resumed under the revised SDK-only scope; these findings require corrected
candidate evidence before they can be closed.

## Historical findings and integration evidence

The ModPort/provider requirements mentioned in this historical record belonged to
the former A16. They no longer block the SDK-only Goal and authorize no further
cross-project implementation or provider runs.

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
return of a failed business result and did not establish the former A16 completion.

The later fresh 180-second temporary Run completed both formal supervisor turns
and the native summary under its unchanged original deadline and seven claims.
It used the installed `269f143` SDK and current production handlers. The supervisor
reported two requests, ten model events, two text events and 1,909 stdout bytes;
the summary reported one request, 98 events, 88 text events and 35,434 stdout bytes.
This is genuine normal-provider evidence, but it did not cover all requirements of the former ModPort A16. Those application
integration requirements are outside the revised Goal.

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

T07/T09 must review ownership of budget, cancellation, state transitions and
recovery obligations, and consolidate duplication introduced by this work.
Public types, errors, docs and examples must agree. Avoid application-specific
branches and unrelated repository-wide refactoring. External adapter failures
require a contract check and an SDK-local reproduction before attribution;
verified SDK defects remain in scope.

Independent reviews found and verified fixes for entry authority, original
completion timestamps, deferred result settlement, transient SQLite errors
misclassified as revoked authority, lost final-flush evidence, missing native
bootstrap errors, original deadline cause, readonly receipt mutation, nested
control deadlines, child storage replay, conservative clock receipt recovery,
targeted execution capacity and query-size fallback. Further review verified timer-floor retention across parent/supervisor/Windows paths, signal interruption, inherited child pre-entry settlement and original startup-failure classification. The final review also verified that SDK-owned read expiry retries cannot extend the child window or bypass incomplete checkpoint facts. Complete Linux source and installed verification passed; native Windows and CI remain required.

The independent journals retain facts; they do not authorize a new execution,
extend an original budget or prove application consumption. Missing storage,
inaccessible processes and unprovable clocks remain unknown. Historical
execution inputs and evidence are preserved. No additional checksum,
fingerprint or candidate/rubric identity gate is introduced.
