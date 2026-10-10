# Execution observability acceptance evidence

This index records [T01 to T09 and A01 to A18](EXECUTION_OBSERVABILITY_GOAL.md).
The scope was revised on 2026-10-04 to cover the SDK alone. ModPort adaptation,
provider requests and changes to other projects have separate acceptance requirements.
The historical integration records below remain available; they do not satisfy the
revised SDK-only A16.

## Current 0.7.2 status, 2026-10-11

SDK-only `0.7.2` acceptance: **accepted**. T01–T09,
A01–A18 and G1–G5: **passed within current applicable SDK scope; unchanged-layout older-writer experiment is not newly applicable**. Accepted commit
`524e1ff6e270ea0862fda2459270d4b26311e3ef`; original full matrix
[38093366109](https://github.com/FlightDan/dispatcher-sdk/actions/runs/38093366109), attempt `1`,
started `2026-10-10T22:58:18Z`; its last original job completed
`2026-10-10T23:14:11Z` (actual job timestamps).
Admission/history scanning: `candidate and secrets original jobs success; all prior rejected/cancelled candidates preserved and ineligible`.
All sixteen original environment verdicts: `{"original_matrix_jobs":16,"passed":16,"failed_jobs":[]}`.

The table records actual emitted installed-test counts; no expected count is substituted for original job output.
Each environment's actual installed suite, import and duration is recorded below;
its original 900-second suite allowance was not renewed. Original logs,
metadata, native artifacts and the complete audit are retained at
`/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff` / `/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/acceptance-review.json`.

| Environment | Actual installed methods | Suite seconds | Actual skips | Actual SDK import |
| --- | ---: | ---: | --- | --- |
| Linux x64 / Python 3.10 | 1206 | 313.754 | 18 | `/tmp/tmpoptx7n1e/venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py` |
| Linux x64 / Python 3.11 | 1206 | 299.619 | 18 | `/tmp/tmpp4svxzam/venv/lib/python3.11/site-packages/dispatcher_sdk/__init__.py` |
| Linux x64 / Python 3.12 | 1206 | 309.547 | 18 | `/tmp/tmp5s6yfiem/venv/lib/python3.12/site-packages/dispatcher_sdk/__init__.py` |
| Linux x64 / Python 3.13 | 1206 | 308.328 | 18 | `/tmp/tmpxfrr131k/venv/lib/python3.13/site-packages/dispatcher_sdk/__init__.py` |
| Linux ARM64 / Python 3.10 | 1206 | 312.846 | 18 | `/tmp/tmp8iih78y5/venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py` |
| Linux ARM64 / Python 3.11 | 1206 | 295.548 | 18 | `/tmp/tmp8ynkjg55/venv/lib/python3.11/site-packages/dispatcher_sdk/__init__.py` |
| Linux ARM64 / Python 3.12 | 1206 | 300.007 | 18 | `/tmp/tmpnr1p9vkw/venv/lib/python3.12/site-packages/dispatcher_sdk/__init__.py` |
| Linux ARM64 / Python 3.13 | 1206 | 303.878 | 18 | `/tmp/tmpmvurnbgh/venv/lib/python3.13/site-packages/dispatcher_sdk/__init__.py` |
| Windows x64 / Python 3.10 | 1206 | 503.856 | 58 | `C:\Users\RUNNER~1\AppData\Local\Temp\tmphcg70shi\venv\lib\site-packages\dispatcher_sdk\__init__.py` |
| Windows x64 / Python 3.11 | 1206 | 657.825 | 58 | `C:\Users\RUNNER~1\AppData\Local\Temp\tmpknxdvshs\venv\Lib\site-packages\dispatcher_sdk\__init__.py` |
| Windows x64 / Python 3.12 | 1206 | 581.502 | 58 | `C:\Users\RUNNER~1\AppData\Local\Temp\tmpmik5_gh3\venv\Lib\site-packages\dispatcher_sdk\__init__.py` |
| Windows x64 / Python 3.13 | 1206 | 349.678 | 58 | `C:\Users\RUNNER~1\AppData\Local\Temp\tmp9fxqxgfh\venv\Lib\site-packages\dispatcher_sdk\__init__.py` |
| Windows ARM host / Python 3.10 x64 emulation | 1206 | 650.096 | 58 | `C:\Users\RUNNER~1\AppData\Local\Temp\tmp0umyxca6\venv\lib\site-packages\dispatcher_sdk\__init__.py` |
| Windows ARM64 / Python 3.11 | 1206 | 705.909 | 58 | `C:\Users\RUNNER~1\AppData\Local\Temp\tmp30hfm4gz\venv\Lib\site-packages\dispatcher_sdk\__init__.py` |
| Windows ARM64 / Python 3.12 | 1206 | 562.621 | 58 | `C:\Users\RUNNER~1\AppData\Local\Temp\tmptxamfcg1\venv\Lib\site-packages\dispatcher_sdk\__init__.py` |
| Windows ARM64 / Python 3.13 | 1206 | 526.468 | 58 | `C:\Users\RUNNER~1\AppData\Local\Temp\tmpywymcoye\venv\Lib\site-packages\dispatcher_sdk\__init__.py` |

Actual external `site-packages` imports/version: `{"actual_versions":["0.7.2"],"environment_count":16,"actual_paths":"per-environment table; interpreters in original matrix audit"}`.
Required applicable native-case coverage counts:
`{"linux_environments":8,"windows_environments":8,"original_matrix_jobs":16,"successful_matrix_jobs":16,"installed_suite_cases_per_environment":1206,"installed_skips_linux":18,"installed_skips_windows":58,"public_scenarios_per_environment":5,"restart_commands_per_environment":6,"canonical_writer_delay_witnesses":16,"native_posix_heldresponse_success_rawfailure_witnesses":16,"native_windows_error5_samehandle_witnesses":8,"native_windows_timeout_samehandle_witnesses":8,"native_windows_cancel_close_witnesses":16,"synthetic_observer_close_receipts":112,"physical_collector_close_records":112,"raw_concurrent_journal_publications":16,"raw_native_controller_cleanup_restart_witnesses":16,"reopened_externalclaim_unknown_reports":16,"pending_platforms":[],"native_scenarios":152,"pressure_scenarios":80}`. Independent evidence-review verdicts:
`{"native_contracts":"clean_with_documented_evidence_limits","scenario_scope":"scope_clean"}`. Five public scenarios, five typed consumers,
source/rebuild checks, six restart commands, documentation and examples coverage:
`{"full_installed_suites":16,"public5_passed":16,"actual_import_version_path_records":16,"six_restart_complete":16,"types_passed":16,"types5_passed":16,"type_source_files_reported":80,"type_emission_count":16,"docs_passed":16,"portable_examples_passed":16,"attempt_matrix_jobs":16,"attempt_execution_artifacts":16,"support_job_logs_expected":2}`.
Current actual scenario-to-review mapping:
`{"A01-A03":"current native startup/entry/output/clock cases","A04-A07":"current execution budget/authority/child/capacity cases","A08-A09":"current exact-generation cleanup/restart/observer contracts","A10-A12":"current stall/evaluator/crash/notification cases with ACK boundaries","A13":"16 original pressure runs:10000 summaries/201 bounded pages each","A14":"current explicit upgrade/history/binding/no implicit mutation regression; layout unchanged from0.7.1","A15-A18":"current public5/types5/docs/examples/restart6/full installed suites","T01-T09/G1-G5":"current applicable regression and independent source/raw reviews; limitations below"}`; retained private review JSON paths:
`["/tmp/sdk-0.7.2-local/raw-review-524e1ff-final.json","/tmp/sdk-0.7.2-local/current-scenario-raw-review-524e1ff.json"]`. Original CI and artifact evidence:
[current original CI and artifact evidence](https://github.com/FlightDan/dispatcher-sdk/actions/runs/38093366109).
README output/skip totals and document link counts:
`{"all_environments_local_links":635,"Linux_README":{"passed":4,"skipped":0},"Windows_README":{"passed":2,"skipped":2,"reason":"two POSIX-marked examples"}}`.

| Environment | Public scenarios | Types | Source/rebuild | Restarts | Docs / README | Portable examples |
| --- | --- | --- | --- | --- | --- | --- |
| ubuntu-latest / Python 3.10 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 334.743s | 6/6 returncode=0 | Checked 635 local links; 4 README examples passed, 0 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:04:30.1822990Z Wake conversation-42: succeeded","2026-10-10T23:04:30.1823543Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186250.log"} |
| ubuntu-latest / Python 3.11 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 319.242s | 6/6 returncode=0 | Checked 635 local links; 4 README examples passed, 0 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:04:10.6046402Z Wake conversation-42: succeeded","2026-10-10T23:04:10.6046831Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186244.log"} |
| ubuntu-latest / Python 3.12 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 328.482s | 6/6 returncode=0 | Checked 635 local links; 4 README examples passed, 0 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:04:21.5672207Z Wake conversation-42: succeeded","2026-10-10T23:04:21.5672545Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186261.log"} |
| ubuntu-latest / Python 3.13 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 327.084s | 6/6 returncode=0 | Checked 635 local links; 4 README examples passed, 0 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:04:21.5184900Z Wake conversation-42: succeeded","2026-10-10T23:04:21.5185410Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186297.log"} |
| ubuntu-24.04-arm / Python 3.10 / arm64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 333.376s | 6/6 returncode=0 | Checked 635 local links; 4 README examples passed, 0 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:04:28.2552920Z Wake conversation-42: succeeded","2026-10-10T23:04:28.2553643Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186290.log"} |
| ubuntu-24.04-arm / Python 3.11 / arm64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 313.051s | 6/6 returncode=0 | Checked 635 local links; 4 README examples passed, 0 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:04:06.5158245Z Wake conversation-42: succeeded","2026-10-10T23:04:06.5159062Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186319.log"} |
| ubuntu-24.04-arm / Python 3.12 / arm64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 316.742s | 6/6 returncode=0 | Checked 635 local links; 4 README examples passed, 0 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:04:11.7116894Z Wake conversation-42: succeeded","2026-10-10T23:04:11.7117345Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186426.log"} |
| ubuntu-24.04-arm / Python 3.13 / arm64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 320.774s | 6/6 returncode=0 | Checked 635 local links; 4 README examples passed, 0 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:04:14.2906171Z Wake conversation-42: succeeded","2026-10-10T23:04:14.2906889Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186310.log"} |
| windows-latest / Python 3.10 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 538.074s | 6/6 returncode=0 | Checked 635 local links; 2 README examples passed, 2 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:08:29.2808301Z Wake conversation-42: succeeded","2026-10-10T23:08:29.2808748Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186282.log"} |
| windows-latest / Python 3.11 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 697.296s | 6/6 returncode=0 | Checked 635 local links; 2 README examples passed, 2 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:11:28.5845013Z Wake conversation-42: succeeded","2026-10-10T23:11:28.5845457Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186322.log"} |
| windows-latest / Python 3.12 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 616.999s | 6/6 returncode=0 | Checked 635 local links; 2 README examples passed, 2 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:10:08.2833466Z Wake conversation-42: succeeded","2026-10-10T23:10:08.2833846Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186269.log"} |
| windows-latest / Python 3.13 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 371.595s | 6/6 returncode=0 | Checked 635 local links; 2 README examples passed, 2 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:05:36.8698952Z Wake conversation-42: succeeded","2026-10-10T23:05:36.8699236Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186275.log"} |
| windows-11-arm / Python 3.10 / x64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 705.807s | 6/6 returncode=0 | Checked 635 local links; 2 README examples passed, 2 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:13:10.8163578Z Wake conversation-42: succeeded","2026-10-10T23:13:10.8163878Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186359.log"} |
| windows-11-arm / Python 3.11 / arm64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 757.000s | 6/6 returncode=0 | Checked 635 local links; 2 README examples passed, 2 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:13:56.1426773Z Wake conversation-42: succeeded","2026-10-10T23:13:56.1427190Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186274.log"} |
| windows-11-arm / Python 3.12 / arm64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 607.780s | 6/6 returncode=0 | Checked 635 local links; 2 README examples passed, 2 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:09:47.1279494Z Wake conversation-42: succeeded","2026-10-10T23:09:47.1279865Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186324.log"} |
| windows-11-arm / Python 3.13 / arm64 | 5 / passed=True | Success: no issues found in 5 source files | Ran 5 tests in 566.682s | 6/6 returncode=0 | Checked 635 local links; 2 README examples passed, 2 skipped | {"steps":{"Run portable examples":"success","Run script notification example":"success"},"observability_result":[{"parsed":true,"status":"succeeded","error":null,"child_status":"succeeded","child_byte_count":25}],"script_notification":["2026-10-10T23:08:51.7430744Z Wake conversation-42: succeeded","2026-10-10T23:08:51.7431115Z report ready"],"raw_record":"/root/HDDworkspace/sdk-release-evidence/0.7.2-524e1ff/job-114334186317.log"} |

Reviewed platform/privilege skips: `{"source":"/tmp/sdk-0.7.2-local/current-skips-final-524e1ff.json","named_skip_predicates":"All16 environments matched current method/class predicates; no unmatched reason","families":{"ubuntu":{"per_environment_count":18,"reason_counts":{"'requires real native Windows Job Objects'":16,"'requires real Windows file sharing'":2}},"windows":{"per_environment_count":58,"reason_counts":{"'requires native POSIX process isolation'":1,"'requires Linux subreaper and supervisor processes'":1,"'requires Linux process containment'":2,"'requires native POSIX process containment'":2,"'requires POSIX fork isolation'":14,"'native Windows has process isolation without fork'":1,"'requires Linux subreaper process isolation'":2,"'requires POSIX process containment'":1,"'fork is unavailable'":1,"'process receipt test uses POSIX fork'":1,"'POSIX startup guard'":1,"'requires POSIX native alarm'":1,"'shared cgroup clues are a Linux-specific scenario'":1,"'requires native Linux multiprocessing'":1,"'requires native Linux process identity'":1,"'requires native Linux process identity and pipe select'":1,"'requires native Linux process birth identity'":1,"'requires real POSIX process containment'":6,"'requires Linux subreaper process containment'":6,"'requires Linux clone and subreaper process containment'":2,"'requires actual POSIX process containment'":1,"'requires real POSIX isolation'":2,"'requires Linux suspend-inclusive native clock'":1,"'scripts require POSIX fork process containment'":1,"'requires POSIX fork process supervision'":3,"'symlink creation can require Windows privileges'":1,"'requires native POSIX alarm'":1,"'non-Windows refusal path'":1}}}}`.
Current original-run evidence limits and native witness review: `{"material_gaps":[],"delivery_sample_limits":["Current native file-publication denial fixture uses synthetic file/process controls. Actual share-zero returned.json denial is separately retained supplemental installed x64Python3.11 proof covering transient and persistent cases, not native outcome.json or real definite ACL5.","Native ERROR5 termination evidence proves exited same-HANDLE race only. Generic definite ACL5 and non-signalled wait/error negatives are synthetic classifier controls; no arbitrary ACCESS_DENIED recovery claim.","Cancellation saved cleanup-before-cancel/reopen tests pass individually in all16 original installed logs, but their TemporaryDirectory raw stores are gone. Retained native controller-crash/restart notes independently show old exact identity/source cleanup and successor admission denial. Reader negatives have retained synthetic inputs/rawSQL, not individual serialized reports for each negative.","Observer negative responses are synthetic, coupled to real recorder/journal writes and current source SQL assertions. Main/WAL/SHM files were not queried or modified. Physical observer closure records remain separate; unknown process metadata does not become known just because collection is complete.","Windows native close can return SDK running while native processes/collectors are contained; physical cleanup is not canonical business completion.","Windows ARM64 Python3.11,3.12,3.13 are native machineARM64. Windows ARMhostPython3.10 is machineAMD64 x64 emulation.","POSIX heldresponse native success/rawfailure tests are inapplicable on Windows, whose canonical writer-cutoff fixture runs threads with actual SQLite contention.","Concurrent external publisher uses synchronousOFF to prove committed visibility; SDK remainsFULL. This is not a power-loss durability witness.","Passing original named assertions establish comparisons/no-mutation not separately encoded in every retained raw file. Pressure readonly dump equality is test-asserted; retained pages independently expose exact count/size/cursors/timing.","Actual PIDs/entry markers/resident memory establish native process execution/capacity; no remote sandbox disposal or all namespace security properties claimed. Thread isolation retains documented process-local limitations.","Native cleanup receipts/ready markers do not establish unrecorded actual double-fork/setsid entry or reaping. Complementary reviewer owns exact same-HANDLE proof.","Stall bridged outbox and pressure processing/pending inbox are publication/receipt facts, not ACK. Later ACK/replay assertions require their original named passing methods; business success is separate from sampled-clock ACK and delivery.","Permission error handling does not identify historical physical ACL/sharing causes. SQL trace includes admission; physical lock owner/hold duration remains unknown absent witness.","Historical rejected/cancelled evidence supplies no current pass result. Original package eligibility/publication/readback remain primary-owned.","CPython3.13 emitted ResourceWarning unclosed database text in some original method blocks; every affected block ended ok and original suite passed. This review does not attribute each warning or infer a live resource leak from garbage collection output."]}`.
Test outcomes do not establish actual fork/setsid creation or process reaping without
the corresponding native witness; business success is not delivery ACK proof.
Windows ARM-host Python 3.10 remains x64 emulation, not native ARM64 CPython evidence;
Linux-only examples remain explicitly inapplicable on Windows.

The SDK correction reads exact-generation native cleanup notes from the
Kernel-bound settlement journal, including after restart, with note source/ID
separate from cancellation receipt identity. Missing, malformed or mismatched
proof remains unknown; local process cleanup does not establish sandbox disposal.
Windows termination error 5 establishes an exit race only when the same acquired
process handle is signalled; live/unknown state and other errors remain failures.
Settlement-note encoding now performs linear page work while preserving the
original time/byte caps, cursor and incomplete-evidence rules.

Native Windows result publication preserves the original permission refusal after
containment if the same result remains unreadable. Recognized sharing refusals and
ambiguous `PermissionError` errno 13 without WinError stay within the original
watchdog window, and success requires rereading that same file. Errno 13 alone
establishes neither sharing nor ACL denial; recognized permanent errors remain
immediate.
Admitted child response observation uses a factual parent-authority read without
a Kernel writer, retaining exact lease/ancestor guards and original deadlines.
Never-claimed queued/cancelled children with legal zero attempt/fence identities
preserve the original wait refusal instead of inventing malformed ancestry.
Committed observation-batch replay uses one connection and a sequence proof;
missing proof still requires atomic admission under the same original deadline.
Final process-collector negatives propagate through recorder and native outcome
receipts. Batch persistence/source closure remain separate factual fields, and
neither later ownership drain nor business success upgrades incomplete telemetry.
The exit137 fixture shares its original two-second process-wait allowance with
bounded read-only durable readiness, retains the exact registration identity and
unchanged final status/signal/OOM assertions, and saves final collector/SQL evidence.
Its earlier missing-publication cause remains unknown. The original local installed
suite (1,201 methods/868.028s, one failure/18 skips) remains rejected; directed final
installed integration subsequently passed Linux24/31.866s and native Windows34/22.801s
(one platform skip), with docs635/four README examples. These local checks do not
replace the original sixteen-environment acceptance recorded above.

Authorized fixture/example choices are separate from SDK budgets. The portable
process example uses child/parent/caller margins of 30/60/120 seconds. The path
portability fixture uses one 30-second attempt and at most five seconds to publish
its original retained result, without another dispatch. Other corrections preserve
existing admission/maintenance windows, canonical cancellation-winner assertions,
native readiness/stop bounds and timeout negatives. Synthetic reader inputs are
seeded separately from the unchanged production note writer. The alarm fixture
retains its original 100ms capture and two-second process limit, distinguishing
an arm COMMIT that consumed the original window from a still-live capture.
The slow-arm fixture records requested begin separately from sticky actual original control-manager entry. It retries only a proven refusal before that entry inside its
original ten-second child constraint; any entered, rolled-back, armed or uncertain sample
and every other exception stops unchanged. Its target10ms, refusal20ms and
same-owner100ms acknowledgement remain unchanged. The wait-owner fixture uses
the actual claimed identity; policy activation/replay retain independent coverage.

Failure diagnostics retain original errors, SQLite codes, clocks, supplied
identity/budgets, process/thread stacks and bounded reads before cleanup in the
README checker, public child/progress consumer, thread, binding and pressure
fixtures. README snippets, `Task.wait(10)` and subprocess limit 30 remain unchanged;
the public consumer remains parent20/child8/tool4 (blocked tool1.2)/caller25, and
the pressure race retains its original 3/5/15-second waits and task10 assertions.
The standalone consumer is invoked with `--evidence-dir`; the fixture environment
variable is not its CLI. Reopened cancellation keeps default1s and per-admission100ms, retaining raw stages before cleanup.
The positive receipt fixture retains its original1s bound, the +0.3s stronger-floor
assertion and a 0.25s writer hold. Those limits are distinct from the persistent
receipt fixture's one producer enqueue within its original300ms window and50ms write
cap; it does not retry preparation.
The public join/maintenance fixture retains its original3s window, capped by
parent12s, child5s and proof0.1s. The concurrent external publisher is enabled only
in `SDKFULL`, whose original0.03s wait is unchanged.
Segmented native join and retained-result publication share the original15s finish deadline, with12s task and100ms control calls unchanged.
Expired-lease receipt archiving shares one original500ms maintenance deadline and retains100ms clock proof, timeout/fence assertions and one invocation.
The invalid-details fixture still requires its first valid publication and makes
exactly two `write_batch` calls, each under its original30ms bound, with no retry.
A quiet second refresh may defer only for the exact write-budget exception with
confirmed rollback and preserved durable/local observations; all other failures
remain fatal. No new write window is added.
The double-fork timeout fixture anchors same-result publication and all post-run observation to
its original 250ms window; execution20ms, descendant sleep150ms and handler1s remain unchanged.
Directed local probes verify immutable pending-result publication and callbacks; they do not
establish actual double-fork creation or reaping, which must be assessed from native witnesses.
The segmented producer retains both original progress calls and requires confirmed state before
reading replay fields; an unknown confirmation remains an acceptance failure. Startup-capacity
and post-ACK interruption fixtures retain their original250ms/100ms admission windows,
healthy success, exact interruption, owner and capacity assertions while recording original
stages before cleanup. SQL scheduling and physical lock causes without witnesses remain unknown.
The public silent cancellation consumer now retains bounded control scopes, original SQL
call timings and live driver thread stacks before observation or cleanup. Its task12s,
caller15s, stall200ms/two windows, supervision100ms and cancellation1s are unchanged;
refused supervision still fails without a cancellation call or retry. Primary errors
survive secondary evidence formatting, writing, inspection and close failures.
The child-admission diagnostic snapshots its trace queue before dictionary allocation,
so same-thread connection cleanup cannot mutate an active queue traversal. Its original
10ms trace admission, 100ms readonly cap and all business calls remain unchanged.
Local paired verification exposed real child pre-entry timeout failures; one subsequent
serial source/install comparison passed with unchanged limits. All evidence is retained;
physical scheduling/storage causes are not established.
The native timeout fixture acquires the original live Job-member descendant HANDLE before termination and requires that same HANDLE be signalled immediately at return, with no additional grace. Focused installed Windows3.11.9 positive validation passed; a directed live-descendant negative failed at this exact assertion and its own Job then reached active0. Holding the identity witness can prevent PID reuse; historical PID7400 cause remains unknown.
The atomic race and two child admission fixtures retain original calls, waits and assertions;
diagnostics copy existing envelopes without sampling. The receipt-writer fixture publishes
the same original result within its original 500ms maintenance/100ms archive caps.
No business retry or SDK budget extension was added.

The historical test-only follow-up corrected five Windows-facing fixtures without
changing SDK runtime behavior: it held the real child-result publisher before its
transaction and recovered the same result inside the original parent deadline;
compared child-read refusals with the retained effective deadline and recorded short
control-lock expiry before the outer deadline; bound receipt-read setup to its
original projected/store context without diagnostic budget samples; preserved
replay-read and concurrent publisher-commit phases when reporting failed; and
compared the recorder observer share with its one absolute close deadline. That
close remained bounded by the original0.4s, with one quarter of its remaining time
for the observer and no fresh0.1s allowance. The public join/maintenance fixture
kept its original3s window, capped by parent12s, child5s and proof0.1s. The
concurrent external publisher remained off except in `SDKFULL`, whose original
0.03s wait was unchanged. Focused historical fixture evidence only: Linux 9
cases/10.910s; native Windows Python 3.13 9 cases/9.212s; native Windows Python
3.11 initially 8/9, followed by the corrected public-result and journal-replay
fixtures passing 2/2 in 5.443s. These results do not establish the installed
full-suite or sixteen-environment acceptance.

The current `524e1ff` candidate additionally carries the public marker-reader
correction and a precise inspection-fixture record. The inspection fixtures are
`test_unstarted_cancelled_child_preserves_original_refusal_without_result_read`
and `test_unstarted_queued_child_preserves_original_refusal_without_result_read`.
In the rejected `cc6f20b` run, the cancelled scenario did run: its original
`InspectionBudgetExceeded` escaped the obsolete type assertion at `store.request`,
so later semantic assertions were not reached. The current test assertion preserves
that exact refusal. This record is separate from the historical five-fixture
follow-up and does not establish acceptance for `524e1ff`.

A business result, canonical winner, durable settlement and sampled-clock ACK are
different facts; one cannot establish the others. Historical causes without
original witnesses remain unknown, including prior README waits, pressure
pre-barrier disposition and the raw parent SQLite callsite/lock owner.

### Preserved 0.7.2 rejected and cancelled candidates

| Candidate / original CI | Historical outcome and failure boundary | Retained evidence |
| --- | --- | --- |
| `bc3e6c06c47ce681017f5be002b596e5b0d43f5e` / `38066968577` | Rejected, 15/16; portable example child-wait failure, underlying stage unproved | `/tmp/sdk-0.7.2-ci-review` |
| `7ce574a22b75ad331bf414cebb988fbf88fca252` / `38068198876` | Rejected, 14/16; restore snapshot and child setup assertions | `/tmp/sdk-0.7.2-ci-review-corrected` |
| `980f008db185276ab640301537e77f69198cc813` / `38070879128` | Rejected, 13/16; native error5 and pre-cleanup thread/child-wait failures | `/tmp/sdk-0.7.2-ci-review-final` |
| `9f1a89cd288b6f668e974b53a92b63c1df720186` / `38072471150` | Rejected, 8/16; native readiness failed before TerminateProcess; binding/archive assertions | `/tmp/sdk-0.7.2-ci-review-windows` |
| `bc81948b5902f8c62656ad471a49203755123bec` / `38073452663` | Rejected, 14/16; ACK completion window expired; synthetic reader setup failed | `/tmp/sdk-0.7.2-ci-review-bounded-native` |
| `8565879c43da75caf8fc3894817ff17ce2bbd4aa` / `38074669771` | Rejected, 13/16; positive claim, README10 wait and bounded page inspection failures | `/tmp/sdk-0.7.2-ci-review-reader-inputs` |
| `9c22aa7dd7717d3f9cfa8336f61d636c8d079c2d` / `38075962705` | Rejected, 14/16; pressure pre-barrier/alarm assertions; ARM-host x64 public parent raw SQLITE_BUSY | `/tmp/sdk-0.7.2-ci-review-linear-notes` |
| `0bdfbc533a02a0e47e80e8d2edb72afc3b2c623f` / `38077104301` | Rejected, 14/16; native ARM slow-arm tokenless pre-admission and asynchronous policy-activation assumptions | `/tmp/sdk-0.7.2-ci-review-public-diagnostics` |
| `3890c70acf7f14b30182d1d288bd2140ab80a0fe` / `38078791584` | Rejected, 14/16; cancellation preparation lacks stage witness; receipt preparation consumed .3; native and expired-lease pending snapshots assumed final | `/tmp/sdk-0.7.2-ci-review-bounded-arm-preparation` |
| `4c8cfad75bcf4552c1d4c4196ca5fadad74e2bd5` / `38080304386` | Rejected, 15/16; second quiet telemetry refresh rolled back after .03s; exact error/physical delay unknown | `/tmp/sdk-0.7.2-ci-review-retained-settlement-windows` |
| `d903dd64f019d62f4cf2b0455ed860ccdad20bb5` / `38081411687` | Rejected, 14/16; missing pre-cleanup atomic/admission diagnostics and pending receipt archive | `/tmp/sdk-0.7.2-ci-review-quiet-refresh-windows` |
| `5febea19339b8ee0b299524f937ff11394b0e019` / `38082849962` | Rejected, 13/16; documented unknown replay dereferenced as success; pending double-fork timeout snapshot; healthy .25 startup admission failure; post-ACK interruption fixture .1 capture expired before intended assertion | `/tmp/sdk-0.7.2-ci-review-admission-and-receipt` |
| `91234f3b710910e82f980f9cd00bb0eda0451ce0` / `38084242976` | Rejected, 15/16; silent cancellation refused its original100ms supervision admission before Runtime.cancel; historical control-lock holder unknown. One passing native ARM3.12 child diagnostic omitted its before-cleanup file after reentrant deque mutation | `/tmp/sdk-0.7.2-ci-review-progress-and-owner` |
| `d85a28b84120aebbe25e8318d3b81a39d4bce9a7` / `38085799411` | Rejected, 14/16; x64/Python3.11 used a fresh PID lookup after timeout, with original descendant identity unretained; native ARM/Python3.11 requested begin refused before actual control-body entry and was misclassified as entered. Historical physical causes unknown | `/root/HDDworkspace/sdk-release-evidence/0.7.2-d85a28b` |
| `44eeda928d8c4c969eaf40a05cf3468181f663d6` / `38087301356` | Rejected, 12/16; ARM3.12 public parent result wait consumed its original8s in writing verify, with child publication outside cutoff; x64Py3.10 targeted claim capture expired before cancellation assertion; ARM3.13 returned.json PermissionError13 without WinError; ARM-hostPy3.10x64 old-sequence telemetry replay expired before BEGIN with committed seq2/count3 retained. Physical causes and missing original owners remain unknown | `/root/HDDworkspace/sdk-release-evidence/0.7.2-44eeda9` |
| `5fad028` / `38076988858` | Cancelled after discovering the documentation CLI mismatch; no acceptance or inferred partial passes | `/tmp/sdk-0.7.2-ci-review-original-errors` |
| `b0a62a198ecfaca4cec2c8655ac26b69807dd092` / `38090932207`, attempt 1 | Rejected; completed original matrix: 9/16 environments passed, 7/16 failed. Each reported 1,206 tests; Linux environments reported 18 skips each and Windows environments 58 skips each. Failures: Windows x64/Python 3.11 and 3.12, `test_live_delivery_inherits_original_expired_control_before_response_read`; Windows ARM64/Python 3.12, `test_actual_receipt_contention_retries_inside_same_window_and_enforces_stronger_floor`; Windows ARM-host/Python 3.10 x64 emulation, ERROR `test_advancing_batch_rechecks_a_concurrent_committed_replay` plus four subtest failures in `test_recorder_close_keeps_source_facts_when_process_observer_is_incomplete`; Windows x64/Python 3.10, `test_public_child_result_survives_kernel_writer_held_until_wait_cutoff`; Windows ARM64/Python 3.13, `test_live_delivery_waits_out_foreign_ancestor_guard_without_ack`, `test_unstarted_cancelled_child_preserves_original_refusal_without_result_read`, and `test_unstarted_queued_child_preserves_original_refusal_without_result_read`; Windows ARM64/Python 3.11, six subtest failures in `test_recorder_close_keeps_source_facts_when_process_observer_is_incomplete`. Original run concluded failure; package is ineligible. No physical cause inferred. All 18 logs and 16 native bundles plus package retained. | `/root/HDDworkspace/sdk-release-evidence/0.7.2-b0a62a1` (offline audit: `/tmp/next-candidate-tooling/audit-b0a62a1-final/acceptance-review.json`) |
| `cc6f20bbf88f9103e2d7a55da86fa2fd8b828ea5` / `38092439819`, attempt 1 | Rejected; completed original matrix: 14/16 environments passed, 2/16 failed. The other 14 include native Windows ARM64/Python 3.11 and 3.12 and Windows ARM-host/Python 3.10 x64 emulation. Windows ARM64/Python 3.13: public marker read failed with `PermissionError` errno 13/no WinError; no full installed suite; outer consumer 5 tests/31.400s. Linux x64/Python 3.13: installed suite 1,206 tests/311.530s/18 skips; outer five-case consumer 329.277s. The `test_unstarted_cancelled_child_preserves_original_refusal_without_result_read` scenario did run, but its original `InspectionBudgetExceeded` escaped the obsolete type assertion at `store.request`; later semantic assertions were not reached. Run conclusion failure; no acceptance. Original package cannot be a release input on this rejected run; the earlier offline audit left exact-package eligibility pending. The official `release_candidate.py find --require` exited 1; stderr reports no complete CI acceptance with retained packages for this completed/failure run, so the package is ineligible. No physical cause inferred. All 18 logs, 16 native bundles, and downloaded package artifact `11684358692` retained. | `/root/HDDworkspace/sdk-release-evidence/0.7.2-cc6f20b` (offline audit: `/tmp/sdk-0.7.2-local/audit-cc6f20b-final/acceptance-review.json`, `acceptance_status=rejected`, raw-contract review rejected) |

All original failed/partial logs and artifacts remain preserved and ineligible;
package artifact `11679525510` from run `38075962705` is not a release input.
Cancelled-run metadata: attempt `1`, full head
`5fad0288cd0a044c57e309bb66c1c020d2914171`, started `2026-10-10T18:44:21Z`, last original job completed
`2026-10-10T18:45:55Z`, conclusion `cancelled`.
Partial job/command observations, if retained: `18 original logs and10 partial native artifacts retained; no release package or full-suite acceptance inferred`;
unexecuted checks and incomplete artifacts remain unknown.
The cancelled candidate differs from `0bdfbc5` only in the three corrected
consumer CLI documentation/Wiki lines, not SDK/tests.

### Verified publication

Eligible original tested package: run `38093366109`, attempt
`1`, artifact `{"id":11684882088,"name":"release-packages-38093366109-1","size_in_bytes":1679445}`;
selection record `/tmp/sdk-0.7.2-local/candidate-524e1ff.json`.
Tag `v0.7.2`: `{"target":"524e1ff6e270ea0862fda2459270d4b26311e3ef","accepted_target":true,"kind":"tag","API_readback":"/tmp/sdk-0.7.2-local/publication-readback-second/publication-readback.json"}`.
Publishing workflow [38094704767](https://github.com/FlightDan/dispatcher-sdk/actions/runs/38094704767):
`{"conclusion":"success","selected_artifact":{"artifact_id":11684882088,"artifact_name":"release-packages-38093366109-1","run_attempt":1,"run_id":38093366109}}`.
Original tested wheel/sdist reuse, with no rebuild or additional matrix:
`{"run":{"id":38094704767,"html_url":"https://github.com/FlightDan/dispatcher-sdk/actions/runs/38094704767","conclusion":"success","head_sha":"524e1ff6e270ea0862fda2459270d4b26311e3ef"},"selected_artifact":{"artifact_id":11684882088,"artifact_name":"release-packages-38093366109-1","run_attempt":1,"run_id":38093366109},"source_log":"/tmp/sdk-0.7.2-local/publisher-38094704767.log","raw_selection_line":"release\tDownload the original tested wheel and source distribution\t2026-10-10T23:21:00.4782697Z {'artifact_id': 11684882088, 'artifact_name': 'release-packages-38093366109-1', 'run_attempt': 1, 'run_id': 38093366109}","rebuild":false,"matrix_rerun":false}`.

[Release v0.7.2](https://github.com/FlightDan/dispatcher-sdk/releases/tag/v0.7.2):
ID `409264867`, published `2026-10-10T23:21:02Z`, draft/prerelease/Latest
readback `{"draft":false,"prerelease":false,"release_id":409264867,"latest_id":409264867}`.
[Wheel](https://github.com/FlightDan/dispatcher-sdk/releases/download/v0.7.2/dispatcher_sdk-0.7.2-py3-none-any.whl):
asset `629237785`, `474762` bytes.
[sdist](https://github.com/FlightDan/dispatcher-sdk/releases/download/v0.7.2/dispatcher_sdk-0.7.2.tar.gz):
asset `629237782`, `1213173` bytes.
Actual published-download version/LICENSE/NOTICE readback:
`{"source":"actual published Release downloads, not local dist","packages":[{"name":"dispatcher_sdk-0.7.2-py3-none-any.whl","path":"/tmp/sdk-0.7.2-local/published-downloads-actual/dispatcher_sdk-0.7.2-py3-none-any.whl","bytes":474762,"metadata_version":"0.7.2","runtime_source_version":"0.7.2","LICENSE_NOTICE":"present and nonempty","archive_safety":"passed","check":"existing scripts/release_candidate.py check_wheel/check_sdist"},{"name":"dispatcher_sdk-0.7.2.tar.gz","path":"/tmp/sdk-0.7.2-local/published-downloads-actual/dispatcher_sdk-0.7.2.tar.gz","bytes":1213173,"metadata_version":"0.7.2","runtime_source_version":"0.7.2","LICENSE_NOTICE":"present and nonempty","archive_safety":"passed","check":"existing scripts/release_candidate.py check_wheel/check_sdist"}],"verification":"existing metadata/source-version/LICENSE/NOTICE/archive checks only"}`. PyPI publication: `This task published GitHub Release only; no PyPI upload was performed`.

GitHub default branch readback: `{"default_branch":"main","readback":"/tmp/sdk-0.7.2-local/publication-readback-second/publication-readback.json"}`.
The 21-page English/Chinese Wiki publication commit and direct public page,
source-link and bilingual-navigation reads: `{"commit":"ac261556ade2174fa6f82d144d4d9d9359548332","pages":21,"repository_ref":"524e1ff6e270ea0862fda2459270d4b26311e3ef","page_reads":[{"name":"Home","url":"https://github.com/FlightDan/dispatcher-sdk/wiki","status":200,"final_url":"https://github.com/FlightDan/dispatcher-sdk/wiki","bytes":242754,"published_ref_visible":true,"english_navigation":true,"chinese_navigation":true,"sidebar_visible":true,"api_link_visible":true,"agent_link_visible":true},{"name":"Home-zh-CN","url":"https://github.com/FlightDan/dispatcher-sdk/wiki/Home-zh-CN","status":200,"final_url":"https://github.com/FlightDan/dispatcher-sdk/wiki/Home-zh-CN","bytes":242803,"published_ref_visible":true,"english_navigation":true,"chinese_navigation":true,"sidebar_visible":true,"api_link_visible":true,"agent_link_visible":true},{"name":"Troubleshooting","url":"https://github.com/FlightDan/dispatcher-sdk/wiki/Troubleshooting","status":200,"final_url":"https://github.com/FlightDan/dispatcher-sdk/wiki/Troubleshooting","bytes":244135,"published_ref_visible":true,"english_navigation":true,"chinese_navigation":true,"sidebar_visible":true,"api_link_visible":true,"agent_link_visible":true},{"name":"Troubleshooting-zh-CN","url":"https://github.com/FlightDan/dispatcher-sdk/wiki/Troubleshooting-zh-CN","status":200,"final_url":"https://github.com/FlightDan/dispatcher-sdk/wiki/Troubleshooting-zh-CN","bytes":243923,"published_ref_visible":true,"english_navigation":true,"chinese_navigation":true,"sidebar_visible":true,"api_link_visible":true,"agent_link_visible":true},{"name":"API","url":"https://github.com/FlightDan/dispatcher-sdk/blob/524e1ff6e270ea0862fda2459270d4b26311e3ef/docs/SDK.md","status":503,"error":"HTTP Error 503: Service Unavailable","read_failed":true},{"name":"DocsforAgents","url":"https://github.com/FlightDan/dispatcher-sdk/blob/524e1ff6e270ea0862fda2459270d4b26311e3ef/DocsforAgents/README.md","status":503,"error":"HTTP Error 503: Service Unavailable","read_failed":true}],"earlier_API_HTML_200":"/tmp/sdk-0.7.2-local/publication-readback-first/API.html","DocsforAgents_HTML_status":503,"DocsforAgents_public_content_API":"/tmp/sdk-0.7.2-local/publication-readback-second/DocsforAgents-content-api.json","additional_successful_reads":[{"route":"API","kind":"earlier HTML read","status":200,"url":"https://github.com/FlightDan/dispatcher-sdk/blob/524e1ff6e270ea0862fda2459270d4b26311e3ef/docs/SDK.md","evidence":"/tmp/sdk-0.7.2-local/publication-readback-first/API.html"},{"route":"DocsforAgents","kind":"GitHub Contents API read; separate from HTML503","status":200,"url":"https://api.github.com/repos/FlightDan/dispatcher-sdk/contents/DocsforAgents/README.md?ref=524e1ff6e270ea0862fda2459270d4b26311e3ef","evidence":"/tmp/sdk-0.7.2-local/publication-readback-second/DocsforAgents-content-api.json"}]}`.
Release/default/Wiki metadata and downloaded assets are retained at
`/tmp/sdk-0.7.2-local`.
These two ledgers are committed after publication; tag and packages retain the accepted pre-ledger commit. Its installed documentation command:
`{"command":["/tmp/sdk-0.7.2-local/published-doc-check-venv/bin/python","scripts/check_docs.py"],"environment":{"PYTHONPATH":"","SDK_ACCEPTANCE_EVIDENCE_DIR":"/tmp/sdk-0.7.2-local/postpublication-doc-evidence"},"returncode":0,"result":"Checked 636 local links; 4 README examples passed, 0 skipped","interpreter":"/tmp/sdk-0.7.2-local/published-doc-check-venv/bin/python","sdk_import":"/tmp/sdk-0.7.2-local/published-doc-check-venv/lib/python3.12/site-packages/dispatcher_sdk/__init__.py","installed_version":"0.7.2","wheel_source":"/tmp/sdk-0.7.2-local/published-downloads-actual/dispatcher_sdk-0.7.2-py3-none-any.whl","log":"/tmp/sdk-0.7.2-local/postpublication-doc-check.log","limits":"Final inert validation-fact text is inserted after this run; no executable block or link changes in that insertion."}`.
All 0.7.1 branches, tags, assets and historical evidence remain preserved;
active development/default-branch policy is `main`. ModPort adaptation remains
outside this SDK-only acceptance.


## Historical 0.7.1 status, 2026-10-06

SDK acceptance and formal delivery passed for `0.7.1`. T01–T09, A01–A18 and
G1–G5 are complete within the revised SDK-only scope.
The reviewed correction commit is now
`e2d3cc52e736afaa622619d4c07686c2c13fc1d6`. Its only full matrix
[37401366407](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37401366407)
started on 2026-10-06 at 01:52:37 UTC and completed successfully. All sixteen
matrix jobs and admission/history scanning passed. Each environment ran exactly
one 1,174-method installed suite within its original 900 seconds, one five-check
source/rebuild command, five public scenarios, the original 30-second managed
example and six original restart commands. Actual imports are `0.7.1` from
external temporary venv `site-packages`. Five type consumers, documentation,
portable examples and script notification passed in every environment.

All sixteen original job logs and native artifact ZIPs, admission/history logs,
host run/artifact metadata, timestamped status snapshots and the tested package
ZIP are retained under `/tmp/sdk-ci-e2d3cc5/`. `complete-matrix-audit.json` records
each environment's original commands, counts, import and duration. Independent
Linux and Windows native evidence reviews found no blocker; the primary also
checked actual native close/flush/capacity/storage facts and original result
equality. The committed publishing helper's live `find --require` selected run
`37401366407`, attempt `1`, original package artifact `11385397936`.

Linux suites took 291.958–329.402 seconds and skipped seventeen Windows-specific
methods. Windows suites took 340.587–671.265 seconds and skipped fifty-eight
platform/privilege methods; all fifteen applicable native Job tests, nine native
observability tests and two file-sharing tests passed. Linux README examples were
four passed/zero skipped; Windows ran two portable examples and explicitly skipped
two Linux-only examples. Native Windows ARM64 Python 3.11–3.13 all passed; Python
3.10 on the ARM host is AMD64 emulation, not native ARM64 evidence.

Actual crash/ACK artifacts establish durable floor preservation, empty sampling
guards and recorded final settlement with the original result. Earlier pending
receipts remain historical facts. A pending canonical outbox does not establish
transport ACK. Sandbox cleanup is confirmed for the same sandbox while its task
correctly remains `recovery_required`. Native close evidence retains physically
closed collectors, stopped capacity and actual storage release; unknown driver
observations are not rewritten as exited. Historical causes lacking original
pre-cleanup evidence remain unknown and are not inferred from this successful run.

Formal delivery completed on 2026-10-06. `release/0.7.1` was created from the
previous default `release/0.7.0` at `b85b828487548cbac5f6ce6adfd2d4ab3ed46eae`
and fast-forwarded to the exact accepted commit `e2d3cc52e736afaa622619d4c07686c2c13fc1d6`.
The annotated tag `v0.7.1` resolves to that same commit. The
[publishing workflow](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37403409155)
completed successfully using run `37401366407`, attempt `1`, original artifact
`11385397936`; its log records that selection. It did not rebuild packages or
run another matrix. Direct post-publication API reads found only the original
complete CI and this publishing run for the accepted commit; the new branch
push did not create an additional CI run.

[Release v0.7.1](https://github.com/FlightDan/dispatcher-sdk/releases/tag/v0.7.1)
is published, `draft=false`, `prerelease=false`, and the Latest API returns that
release (ID `404242276`, published at `2026-10-06T02:17:44Z`). Its two assets are
[wheel](https://github.com/FlightDan/dispatcher-sdk/releases/download/v0.7.1/dispatcher_sdk-0.7.1-py3-none-any.whl)
(asset `614202079`, 471,445 bytes) and
[sdist](https://github.com/FlightDan/dispatcher-sdk/releases/download/v0.7.1/dispatcher_sdk-0.7.1.tar.gz)
(asset `614202078`, 1,157,618 bytes). The actual published downloads passed the
committed helper's distribution/runtime version and LICENSE/NOTICE checks;
the sdist retains the public CI recipes and historical JSON documentation files.
No PyPI publication occurred.

The repository default branch was changed to `release/0.7.1` and read back
through GitHub. Existing branches, tags and evidence were preserved. Publication
logs, final Release/default metadata and downloaded assets are under
`/tmp/sdk-ci-e2d3cc5/`. This post-publication ledger update changes only these
two evidence documents. The tag and published packages retain the accepted
`e2d3cc5` commit and its original pre-publication ledger snapshot; the default
branch receives the later documentation commit, with installed documentation
checks and without another full matrix. The final installed Python 3.10
documentation command checked 631 local links and ran four README examples
with zero skips; its original output is `final-ledger-docs.log` in the same
evidence directory.

The following current closure supersedes the older candidate-specific status
tables below, whose original errors, commands and evidence remain preserved.

| Requirement | Status | Current installed/native evidence |
| --- | --- | --- |
| T01–T09 | passed | Reviewed SDK/state/ownership changes, complete installed regression, public APIs/types/examples, native Linux/Windows and this evidence index |
| A01 | passed | Native queue/ready/entry/model-request and real import-failure witnesses |
| A02 | passed | Actual segmented bytes `[65,255,66,67]`, separate output/heartbeat/progress and duplicate-progress refusal |
| A03 | passed | Current/old attempt and inaccessible identity regressions; retained unknown collector observations |
| A04 | passed | Actual inherited parent/child/tool cutoff, original reserves and native stop evidence |
| A05 | passed | Actual ACK-crash marker, durable floor/empty guards, original typed result and bounded restart/short-wait cases |
| A06 | passed | Actual managed children return success and original failure within bounded capacity and observed parent memory |
| A07 | passed | Actual rejection/partial registration/crash recovery preserves original errors and obligations |
| A08 | passed | Native cancellation/tree containment and physically closed flush/collector/storage/capacity receipts |
| A09 | passed | Original body/cleanup errors, same-sandbox cleanup without business replay and honest unknown OOM attribution |
| A10 | passed | Valid-window/stall/unknown/wait exemption/progress-reset regressions |
| A11 | passed | Managed notices and business budgets/capacity remain separate; original 30-second public example |
| A12 | passed | Original-bounded native pressure/deadline/cancel/memory/callback cases with explicit degraded telemetry |
| A13 | passed | Actual writer contention, incomplete reads, dropped events and bounded pages remain visible |
| A14 | passed | Complete explicit copy-upgrade/old-writer/retained-owner/effect/recovery compatibility regressions |
| A15 | passed | Actual rebuilt wheel outside checkout, version/import/public exports and six raw restart receipts per environment |
| A16 | passed | All five SDK public-entry scenarios in all sixteen installed environments; real handlers/processes/local tools/storage |
| A17 | passed | Native Windows x64 and ARM64 3.11–3.13 Job/process/flush/file-sharing witnesses; 3.10 emulation separately labelled |
| A18 | passed | Same actual 0.7.1 commit across all sixteen environments, one full installed suite each plus packaging/types/docs/examples/restarts |
| G1 | passed | T01–T09 and every required applicable A01–A18 witness completed; no current blocker |
| G2 | passed | Installed public interfaces, five typed consumers, docs, executable examples and public end-to-end consumers |
| G3 | passed | All current matrix imports/package provenance point to the actual same 0.7.1 candidate; old dev2 passes are not reused |
| G4 | passed | Original API/state/receipt compatibility and explicit storage upgrades; original facts and unresolved obligations retained |
| G5 | passed | Independent ownership/concurrency/deadline/cleanup/maintainability review, corrected findings and final Linux/Windows evidence review |

Reviewed candidate `e9780505d93a32ec6e6014e124b1e61123d0fa0d` was pushed after
all known source, fixture and example corrections passed independent review and
necessary local installed checks. Its full matrix
[37397706018](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37397706018)
started on 2026-10-06 at 01:09:16 UTC and completed with nine successful and seven
failed matrix environments. All sixteen installed suites ran 1,174 methods
within their original 900-second allowance. The failed jobs contain twelve
inner failures/errors. All original matrix logs, artifact ZIPs, extracted
evidence, admission/history-scan logs and the tested package artifact are
retained under `/tmp/sdk-ci-e978050/`. At that failed run’s completion, no formal Release or default-branch change
had occurred. This failed run does not establish final 0.7.1 acceptance.

The eight Linux environments and native Windows ARM64 Python 3.12 passed.
Independent Linux evidence review confirmed the installed `0.7.1` imports,
native x64/ARM64 mechanisms, seventeen inapplicable Windows skips, five public
scenarios, six raw restart receipts, types, docs and examples. Public silence
snapshots retain the descendant's earlier alive observation; actual native tree
tests independently confirm physical death at cancel return. Cancellation leaves
a matching pending result outbox; it is not transport/ACK completion. Sandbox
cleanup recovery preserves the task's `recovery_required` business state.

| New failure | Original evidence and correction scope |
| --- | --- |
| Archive cap checks, seven occurrences on Windows x64 3.10/3.11, ARM64 3.11 and ARM host x64 3.10 | Clock-anchor subtraction returned `.10000000000002274` for the original `.1` cap. Three real pre-COMMIT tests already retained correct rollback/pending/original rejection and archive errors, then failed their exact cap assertion. Four writer tests failed that assertion before acquiring the writer, so they never injected SQLite contention. Numerical hardening clamps forwarded timeout to `min(.1, remaining)` while preserving the same operation deadline and exact cap assertions. It only removes an ULP-sized overshoot; it is not evidence of lost results or altered business authority. |
| Lifecycle native wait minimum, two occurrences on x64/ARM64 3.13 | Native waits returned false after .097278/.095998 seconds for forwarded .097808/.097085 seconds. [Windows wait accuracy](https://learn.microsoft.com/en-us/windows/win32/sync/wait-functions) depends on system-clock ticks and does not promise this minimum high-resolution duration. The fixture retains original-deadline/remaining-argument, actual refusal, receipt, owner and physical-close assertions plus raw measured elapsed; it no longer invents a native minimum. |
| Guard subtraction, x64 3.11 | `deadline - now` rounded to `7.000000000000057`. Compare absolute native deadlines against `now + 7`, preserving the same seven-second bound without a grace interval. |
| Provider-failure return, x64 3.10 | The exact return was `running`, before provider-result assertions. The old temporary store was deleted, so the precise pending cause is unknown. The fixture must retain its original result/receipt and retry publication only within the original execution deadline and one API maintenance window; raw provider code/message/status and business assertions remain required. |
| Worker-entry result, x64 3.12 | The assertion message dereferenced `.result.error` when result was absent, hiding the primary state. Its temporary store was deleted. Preserve original entry/business/return evidence, avoid the masking dereference, and use the same bounded factual publication rule without another dispatch. |

The numerical, native-wait and pending-publication corrections passed independent
review. Worker/provider fixtures now compare each complete canonical result with
the first actual captured SDK result for its original execution generation; they
preserve raw errors and cleanup failures separately. The initial local source
command ran sixty affected methods in 58.663 seconds: fifty-nine passed and one
cancel-archive fixture failed its strict return-time assertion. Original evidence
is under `/tmp/sdk-071-post-e978-corrections310/`.

That final archive COMMIT wrapper began 8.296 milliseconds before the original
`.5` maintenance cutoff, completed 28.665 milliseconds after it without error,
and was followed by a 47-microsecond close. This locates the late return inside
the COMMIT wrapper; it does not distinguish native SQLite durability work from
instrumentation-lock or scheduler delay. The earlier pending pass contains an
untraced Kernel/lifecycle interval and remains causally unresolved. The existing
SQLite admission contract preserves successful COMMIT receipts after late native
return. The fixture correction enforces the same absolute admission/pre-COMMIT
deadlines and accepts late return only with an actual successful late COMMIT and
superseded report, followed by exact original-result, cancellation-winner and
single-business-call assertions. It adds no grace interval or renewed deadline;
the affected writer test also retains Kernel SQL evidence.

The correction passed independent review. The source settlement follow-up passed
nineteen methods in 20.763 seconds. A fresh `0.7.1` wheel rebuilt from the corrected
sdist passed eighty-eight affected/integration methods in 72.648 seconds outside
the checkout, including all entry/provider/result, cancellation, reader-lifetime,
received-checkpoint, observer, host-startup, restart-publication and release-helper
cases. Public success/failure/budget/silence/cleanup, the managed example and five
installed type consumers passed. Original commands, SDK import and outputs are
under `/tmp/sdk-071-post-e978-reviewed310/`.

Checking copied documentation first exposed the excluded CI workflow; checking
the actual unpacked sdist then exposed four excluded historical JSON measurements.
The manifest and harness now include both public workflow recipes and all four
linked original measurement files, without editing those records. These packaging
changes passed independent review. The final packaging follow-up under
`/tmp/sdk-071-post-e978-packaging-final310/` validates ordinary package metadata,
runtime version, license/notice and all six required archive members. Its unpacked
source archive passed 630 local links and all four README examples, with zero
skips; the new installed environment also passed five type consumers and all six
original restart commands with their raw receipts.

A real archive COMMIT followed by deliberately delayed return passed the corrected
fixture in 1.749 seconds on the installed final packaging follow-up. The actual
transaction was committed before the original `.5` cutoff; only its return was
held beyond that cutoff. The exact cancellation winner, original result and
single business call remained unchanged. This is a receipt-preservation probe,
not attribution of historical native I/O. Its record and raw SQL are identified
by `committed-late-return-reviewed-probe.json`. The initial probe applied its delay
outside the captured callback and to a read COMMIT, so it failed before testing
archive preservation; its separate source and failed record remain preserved.
The earlier documentation failures also remain in their original directories.

All known corrections are now reviewed and locally verified. A replacement full
sixteen-environment matrix is still required for the final committed candidate.
The previous failed candidate and its package artifact remain preserved and
ineligible for release.
The latest completed development run
[37390861215](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37390861215)
tested `33482b2` / `0.7.0.dev2`: twelve matrix jobs passed, four failed,
and history scanning passed. All sixteen original job logs and artifacts are
retained in `/tmp/sdk-ci-33482b2/`. Every installed suite completed its original
900-second allowance; four failing environments contain seven inner failures
or errors. These results do not establish formal 0.7.1 acceptance.

The revised Goal explicitly authorizes the formal GitHub release, integration
into `release/0.7.1` and making that branch the default, after all required
acceptance passes. PyPI publication is excluded. Live discovery found default
branch `release/0.7.0`, no `release/0.7.1`, no `v0.7.1`, and only historical
prereleases `v0.7.0.dev0` and `v0.5.1`. All existing history is preserved.
The formal workflow reuses a fully successful same-commit matrix and its
original tested wheel and sdist. It neither rebuilds packages nor runs another
matrix for the tag. Authored SHA256SUMS generation and upload were removed.

### Completed development run and final-candidate preparation

All sixteen original logs and artifacts for `37390861215` are under
`/tmp/sdk-ci-33482b2/{logs,artifacts}/`; downloads completed before fixes began.
The sixteen jobs consumed 128.733 observed runner wall minutes including setup
and post-processing. This is elapsed runner time, not billed credits.

| Failed environment | Original installed-suite failures/errors | Attribution and correction |
| --- | --- | --- |
| Windows x64 3.10 | PID-only observer cleanup; lifecycle release (`.02`); startup host recovery; restart publication | Discarded close receipts permitted deleting owned SQLite storage; the fixture now drains both physical workers within the original total two seconds. Release timing incorrectly demanded nominal duration after prior work consumed the same deadline; it now verifies each real acquire's remaining argument and native duration. Restart `run_once()` may legitimately return `running` with an original result pending; the fixture retries only publication, within its original execution budget and one API maintenance allowance. Host success wait and stop both missed their original three seconds; exact historical cause is unresolved. Its unsafe deletion and masking of the primary failure are corrected, with own SQL/worker/health/body/stop evidence and unchanged deadlines. |
| Windows ARM64 3.11 | Lifecycle release (`.02`) | Same confirmed fixture contract mismatch; native coarse monotonic endpoints cannot impose a performance-clock minimum of the whole nominal capture bound. |
| Windows ARM64 3.12 | Cancelled result archival | SDK defect: rejection archival renewed a `.1` operation allowance and leaked a transient journal error. Every branch now shares the original record deadline. A failed archive reports pending with both typed rejection and typed archive error; permanent archive errors retain the original rejection as their cause. Original result/budget/cancellation/outbox remain immutable. |
| Windows ARM64 3.13 | Durable receipt absent after cleanup Future completion | `_thread_done` proves physical Future completion, not journal commit. The fixture publishes the same retained outcome within the existing two-second finish deadline, records raw failures and retains its original token/capacity/close assertions. |

The eight Linux jobs, Windows x64 3.11–3.13 and Windows ARM host 3.10 x64
passed their complete installed suites and applicable public/native scenarios.
Linux skips were seventeen inapplicable Windows mechanisms. Windows skips were
fifty-eight reviewed platform/privilege cases, without a required native Windows
acceptance skip. Windows ARM host 3.10 uses AMD64 CPython on an ARM64 runner;
it does not establish native ARM64 CPython support. Individual raw receipts for
the six restart commands were missing from this development artifact; the final
harness retains each command, stdout, stderr and original timeout.

SDK/fixture corrections passed independent review. The first final-candidate
source-focused command passed 54 cases in 36.385 seconds; the older-gh pagination
correction then passed sixteen release helper cases. Original outputs:
`/tmp/sdk-071-source-focused-{stdout,stderr}.log` and
`/tmp/sdk-071-release-helper-followup-{stdout,stderr}.log`.
Five public type consumers passed. Live GitHub lookup correctly returned no
eligible candidate for this failed development run; the original unsupported
`--slurp` error and corrected lookup are retained. Formal 0.7.1 installed and
native acceptance remains pending.

The local Python 3.10 rebuilt-wheel full run did not pass. Its installed suite
timed out at the unchanged 900-second limit, after 1,097 completed passes and
one received-checkpoint failure; the outer five-check command failed after
941.940 seconds. Original command, stdout/stderr and the actual `0.7.1`
`site-packages` import remain under `/tmp/sdk-071-local-final310/`. The public
five-scenario batch and managed example passed before that timeout. No release
package was exported. The suite's last test name does not establish a hang.
Retained SQL showed continuing progress near 880 seconds; wrapped COMMIT
durations were substantially longer than the previous Linux CI. They include
trace bookkeeping, so native I/O and recorder overhead are not separately
attributed. Cleanup snapshots showed no accumulating owned-worker leak.

The failed received-checkpoint store preserved the same canonical successful
result and a pending journal receipt after cleanup. It did not retain the exact
failing assertion. An unchanged installed reproduction passed in .903 seconds;
that does not explain the historical failure. The affected fixture now records
raw errors and SQL before cleanup, and finishes factual publication within one
original `.5` maintenance window, rather than assuming one recovery pass commits
both stores. Its original capture/finish `.1`, producer/join two-second bounds,
ten-second execution constraints and exact result/checkpoint assertions remain.
A real post-UPDATE/pre-COMMIT expiry regression proves rollback leaves the
receipt pending after Kernel success, then archives that same result within the
same maintenance window. Independent review identified and verified fixes for
native coarse-clock expiry and identifying the actual injected recovery pass.

Necessary installed checks against the diagnostic `0.7.1` wheel outside the
checkout passed 66 cases in 45.855 seconds, including all prior failing fixtures,
received-checkpoint cases and sixteen release-helper tests. The reviewed expiry
correction then passed its two affected installed cases in 1.878 seconds. Five
public typing consumers also passed using that environment's installed package.
Commands, original output and raw recovery/SQL evidence are retained under
`/tmp/sdk-071-received-fact-diag310/`; this diagnostic package is not a release
artifact. These focused results do not convert the timed-out complete suite into
a pass. A final committed 0.7.1 candidate still needs the complete sixteen-job
matrix and all required native acceptance.

The same diagnostic environment passed all six independent restart consumers,
five public type consumers, 630 documentation links and four README examples
with zero skips. Each restart command retained its original stdout/stderr,
timeout and installed import in `restart/` beneath that directory.
Eleven unchanged portable examples passed. `effect_recovery.py` initially
failed its final canonical-success assertion; its original temporary store was
deleted, so that exact execution's state remains unknown. An unchanged retained
diagnostic passed, without establishing the historical cause. Source review
confirmed that its worker discarded `run_once()`'s pending return and inferred
publication from exit zero. The corrected example uses bounded public recovery
and observation within one `.5` maintenance window further limited by its
original five-second execution deadline. It keeps both fifteen-second process
joins and the final canonical-success/single-file-write assertions.

Independent review found and verified a correction for background maintenance
winning publication before the foreground caller: durable state is read
independently of that caller's reports. The corrected actual installed example
passed. A real post-result Kernel writer then forced its initial `running`
return; after release, the reviewed example observed canonical success with the
exact original result before its maintenance deadline and wrote the file once.
Original errors, unchanged diagnostics and reviewed proof are retained in
`portable-examples/`, `effect-original-diagnostic/` and
`effect-publication-reviewed-real-writer/` under the same diagnostic directory.
This corrects the example's unsupported assumption; it does not claim a new SDK
defect or turn the earlier failed local commands into passes.

After the known
fixture defects were corrected and reviewed, implementation commit `d5d9741`
was pushed to the previously authorized work branch. CI run
[37378483985](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37378483985)
has finished: all eight Linux environments passed, all eight Windows environments
failed, and history scanning passed. This is a failed acceptance run. Original
Windows logs and retained artifacts established fixture timing defects and SDK
defects in completion-clock recovery, native cutoff classification, callback
diagnostics and queued-policy promotion before confirmed handler entry.
The reviewed corrections were committed as `a6b897c` and pushed to the authorized
work branch. Replacement CI run
[37385281478](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37385281478)
has finished against that commit: all sixteen matrix jobs failed and history
scanning passed. All eight Linux jobs failed: their original logs show
an outdated Inbox readiness assertion waiting for `callback_errors` after SQL
delivery errors were separated into `delivery_errors`. Two Linux environments
also exposed a transient sampling guard in the final child-result authority
check, after the sole child result read. The final check now retries only its
authority transaction within the same proof deadline; the child result is not
read again. The Windows ARM64 Python 3.13 public budget scenario retained a
returned and contained tool timeout but lost its original completion sample
after `OperationalError: interrupted`; its artifact does not retain the exact
SQLite interruption attribution. Completion capture now preserves proof for
positively attributed reader-window exhaustion and bounded transient admission,
after successful physical close. Unrelated interruptions and permanent errors
remain unproved. These source corrections passed independent review and targeted
installed validation; complete installed and native matrix acceptance remain
pending. The corrected Inbox assertion passed
against the retained installed wheel outside the checkout in 1.373 seconds;
the original command and output are in
`/tmp/sdk-windows-corrections310/readiness-consumer/`.
Original logs from all sixteen jobs were retained under
`/tmp/sdk-windows-corrections310/`. Other confirmed Windows fixture defects were
corrected without changing execution deadlines: event ordering uses causal
ordinals, duration measurement uses the performance clock, deadline setup uses
the supported caller clock, and collector cleanup confirms owned workers finish.
Settlement-journal cold schema setup now explicitly allows one second, while its
subsequent operation budgets remain unchanged. Two telemetry fixtures confirm
prerequisite persistence by retrying the same prepared batch within one finite
one-second maintenance window; each write retains its original 0.03-second
allowance and captured clocks. The original runtime-overlap failure lacks raw
ownership evidence; later local success does not establish its historical cause.
This run cannot satisfy full acceptance; its replacement is `37390861215`.

The SDK corrections now committed as `33482b2` were rebuilt from sdist and installed
in a clean Python 3.10 virtualenv at `/tmp/sdk-final-authority-recovery310/`.
Its recorded import is `venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py`.
The first targeted command ran 73 cases in 70.282 seconds: 72 passed and one
settlement expectation failed. The expectation was outdated because the now
retained completion proof permits conservative resolution after lease expiry;
the corrected assertion requires stale-lease rejection, the unchanged original
outcome, and one business invocation. The affected follow-up ran 43 cases in
22.221 seconds with no failures, including that assertion, both proofless legacy
cases, settlement and cancellation regressions, and both telemetry fixtures.
Independent review of these fixture changes found no blockers. The five public
scenarios, managed example within its original 30-second limit, five type
consumers, 627 links and four README examples also passed against this wheel.
Compile and diff checks passed. Commands, stdout/stderr, import provenance and
raw database evidence remain in that directory; these are local targeted checks,
not a complete suite or native Windows acceptance.
The same installed candidate subsequently passed four packaging/import-boundary
checks and the existing Kernel and Orchestrator restart consumer in six separate
processes. Each process recorded its `site-packages` import; Kernel states were
queued/succeeded/succeeded and Orchestrator states were running/running/succeeded.
The exact repository consumer script, six command receipts, stdout/stderr and
summary are retained in `restart-evidence/` below that candidate directory.
The two duplicate telemetry fixture loops were consolidated into
`tests/_storage_evidence.py` without changing their assertions or caller-owned
windows. Independent delta review found no blockers; both affected installed
cases then passed in 0.940 seconds, with `helper-command.json` and raw evidence
retained under the same candidate directory.

The CI cost audit found that the outer discovery already imports the installed
package and repeats nearly the whole suite inside the isolated rebuilt-wheel
consumer. The failed sixteen-job run used 242.15 unweighted runner-minutes;
104.42 minutes of nested installed suites are included in that total, not added
to it. These are observed durations, not billed credits. The proposed correction
keeps all sixteen environments and one complete installed suite in each, with
outer packaging and isolation checks. Public/native scenarios, types, docs,
examples, restart checks and artifacts remain required. No individual test
definition has been removed. At the user's request, deduplication was completed
and checked before the next push. The user then explicitly authorized pushing;
the one-line selection change is included in `33482b2`, and run `37390861215`
uses one complete installed suite per environment, preserving the existing
matrix and all unique tests.
The proposed one-line workflow diff is retained at
`/tmp/sdk-ci-single-full-suite-review/single-full-suite.patch`. Static inventory
counts 1,159 test methods: five outer packaging/isolation checks plus 1,154 in
the complete installed suite. This establishes selection coverage only, not
execution or native acceptance; subtests are not counted as separate methods.
An independent delta review found no omitted acceptance path. Actual unittest
loading outside the checkout against the same clean installed SDK then found
exactly 1,159 methods in both the original discovery and the partitioned
selection: five outer and 1,154 inner, with no missing, extra, duplicate or
failed imports. The loaded selections and result are retained in that review
directory as `loaded-partition.json`, `full-selection.json`,
`outer-selection.json` and `inner-selection.json`; no tests were executed by
this coverage check. The initial loading attempt lacked the benchmark fixture
script copied by the real consumer; that harness error is retained separately
in `initial-load-missing-fixture/`. Loading passed after copying the same script
as the real consumer. If packaging or an earlier public scenario fails, the
installed suite will not be reached and the job remains failed; unexecuted
checks cannot satisfy acceptance.
The preceding run
[37269716472](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37269716472)
remains cancelled at the user's request.

The Windows corrections now have independent source review and installed
verification in `/tmp/sdk-windows-corrections310/`. The candidate was rebuilt
from an sdist and installed into a clean Python 3.10 virtualenv; its actual
import is that virtualenv's `site-packages/dispatcher_sdk/__init__.py`.
The 115-case targeted run completed in 95.781 seconds with 114 passes and one
fixture error: an external FULL-sync ACK returned after its unchanged 0.1-second
proof window. The fixture's in-window visibility publisher now explicitly uses
NORMAL; its consumer and late-ACK case retain FULL. Four affected/integration
cases then passed, and the late-ACK case passed separately in 0.905 seconds.
A mistyped late-ACK selector in that integration command is retained as a
harness error, followed by the correct single-case command; it is not a SDK pass.
No complete local suite was rerun. The five public end-to-end scenarios,
managed supervisor example within 30 seconds, five typing fixtures, 627 links
and four remaining README examples passed against the same installed wheel.
Raw commands, import provenance, stdout/stderr and scenario evidence remain
under that directory. These checks do not replace the required native matrix.

| Check | Current evidence |
| --- | --- |
| Managed supervisor, native budget capture and thread capacity | 31 cases passed in 75.589 seconds, including all 22 A12 cases |
| WAL anchor, stream capture, storage lifetime and capacity | 20 cases passed in 34.167 seconds, including six real SQLite anchor scenarios |
| Native packets, cancellation and clock floors | 18 cases passed in 20.971 seconds; permanent SQL errors remain failures |
| Idle Inbox admission and immediate Run reopen | Ten cases passed in 16.755 seconds, including the original saturated-worker pressure case; `/tmp/sdk-idle-inbox-reopen-focused310.log` |
| Completion-reader lifetime | All seven new real SQLite lifetime cases and the original reentrant thread-timeout case passed in 6.723 seconds; `/tmp/sdk-completion-reader-stable-fixture310.log` |
| Confirmed-clock and guarded Effect crashes | All five recovery cases passed in 9.112 seconds; `/tmp/sdk-effect-confirmed-and-guarded310.log` |
| Cleanup, capacity, notifications, Inbox and Run reopen | All 64 integration cases passed in 66.902 seconds; `/tmp/sdk-lifetime-notification-integration310.log` |
| Types and README examples | The child-completion handoff wheel passed five public type consumers outside the checkout, plus 626 local links and six README examples with no skips; `/tmp/sdk-child-completion-handoff-types310.log` and `/tmp/sdk-child-completion-handoff-docs310.log` |
| Last complete source run, before the latest fixes | 1,092 cases finished in 1,046.777 seconds: two failures, two errors and 17 platform skips; `/tmp/sdk-child-anchor-source-full310.log` |
| Rebuilt public consumer and managed example | A fresh Python 3.10 virtualenv imported the sdist-rebuilt wheel from `site-packages`. All five public scenarios passed, and the managed supervisor example passed within its original 30-second subprocess limit; `/tmp/sdk-collection-current-independent310-evidence/sdk-observability-consumer-4svbk4rp/` |
| Previous installed suite, before the child handoff and alarm receipt corrections | All 1,126 cases finished in 879.142 seconds: one failure, one error and 17 platform skips; `/tmp/sdk-collection-current-independent310.log` |
| Previous complete installed suite | All 1,131 cases finished in 853.439 seconds: three errors and 17 platform skips; `/tmp/sdk-alarm-current-independent310.log` |
| Latest complete installed suite and restart consumer | All 1,133 cases finished in 863.318 seconds within the original 900-second limit, with no failures or errors and 17 real-Windows skips. The wrapper and final restart consumer passed in 905.929 seconds; `/tmp/sdk-refusal-current-independent310.log`. Native matrix validation remains pending |
| Latest retained-wheel types, packaging and docs | Five public type consumers and three packaging boundary checks passed. README checking failed at Chinese example 2: no callback within its existing 15-second wait. `/tmp/sdk-refusal-current-docs310.log`; CI remains paused during diagnosis |
| Received positive sampling facts | The unchanged older wheel reproduced the missing ACK after actual producer capture, SQLite contention, durable receipt and recovery. The correction passed independent review and 48 source integration cases. All 11 corrected regression cases passed against its rebuilt installed wheel in 7.954 seconds; complete matrix acceptance remains pending |
| Latest received-fact installed candidate | Five public scenarios and the managed example passed. The installed suite hit its original 900-second limit after a managed-capacity cleanup error and seven producer-fixture failures; final restart did not run. `/tmp/sdk-received-current-independent310.log` |
| Final installed types, README and restart checks | The same retained wheel passed five public type consumers outside the checkout, 626 documentation links, all four remaining README examples with zero skips, and Kernel/Orchestrator restart consumers in six separate processes; `/tmp/sdk-received-final-types310.log`, `/tmp/sdk-received-final-docs310.log`, `/tmp/sdk-received-final-restart310/` |
| Final requirement coverage review | An independent read-only audit of committed `d5d9741` mapped T01–T09 and A01–A18 to the concrete current tests, public consumers and CI obligations. No additional mandatory coverage blocker or incorrect mandatory-platform skip was found. This establishes coverage wiring only; terminal jobs, native/installed artifacts and per-platform skips still require reconciliation |
| Current registration and cleanup tests | All nine cases passed against the same installed wheel in 26.463 seconds, including actual registration-connection ownership and close before recorder publication; `/tmp/sdk-runtime-registration-current310.log` |
| Child result to parent completion | Exact captured-fact handoff passed independent review and 65 source cases in 56.343 seconds; five cases against its sdist-rebuilt installed wheel passed in 16.057 seconds, including the unchanged native success and raw-failure scenario. Complete installed validation remains pending |
| Interrupted native sampling receipt | A real alarm exposed a stored control-flow exception that suppressed both supervisor terminal sends. The correction passed independent review, the actual supervisor-to-parent path and 45 source integration cases in 22.707 seconds; `/tmp/sdk-uncaptured-alarm-integration310.log`. The latest installed run passed both terminal receipts, then errored in the recovery refusal assertion; see below |

The current successful full-suite candidate was rebuilt from sdist and imported
from `/tmp/tmpr6htfuwz/venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py`.
All five public scenarios, the managed example and final restart consumer passed.
Its complete raw suite and original 900-second command receipt are in
`/tmp/sdk-refusal-current-independent310-evidence/sdk-observability-consumer-dov8wcqm/`.
The exact wheel, sdist, origin record and persistent installed import record are
under `/tmp/sdk-refusal-current-candidate310/`. All 17 skips concern genuine
Windows file sharing or Job Objects; they do not fulfill Windows acceptance.
The subsequent README check passed four examples before the Chinese script
notification example missed its existing callback window. That failure is
unresolved; full-suite success is not a complete documentation or matrix pass.

One unchanged reproduction of the failed example passed, followed by one full
six-example diagnostic run that also passed (626 local links, no skips).
The latter forwards the original checker and preserves its 10/15/30-second
script, callback and subprocess limits. It retains the actual scripts, raw
outputs, SDK import path and pre-close Host health under
`/tmp/sdk-docs-health-probe310/evidence-run1/`. The Chinese callback succeeded
despite one reported `SettlementBusyError: database is locked`; no notification
error was reported. The original failed run deleted its temporary databases,
so these later passes do not establish its cause or a fix. At the user's request,
the script-notification example was subsequently removed from both READMEs.
The current checker passed all four remaining examples against the retained
received-fact wheel. The removed example's historical failure remains evidence;
it is no longer part of the current README check.

Separate source review found that a supervisor's terminal checkpoint can carry
a positive `captured_envelope` after its finish-only ACK fails. Runtime retains
that fact in the settlement receipt but has no consumer for the supervisor's
remaining token. The bounded real-process probe was inconclusive: its genuine
writer acquired the lock after positive capture, but the supervisor was reaped
with exit code -9 before any terminal packet was observed. It did not reach the
handoff/recovery stage being tested. Evidence is under
`/tmp/sdk-supervisor-fact-handoff-probe310/evidence-native/`; the initial sandbox
attempt failed at local socket setup before SDK invocation. No SDK correction
has been made from this probe, and it does not explain the README failure.
CI remains paused.

The focused regression then reached the intended receipt boundary using a
separate real producer process, the existing native finish/pipe functions and
actual SQLite writer contention. The unchanged wheel publishes the retained
floor but leaves the exact marker after recovery:
`/tmp/sdk-received-checkpoint-baseline-clock310.log`. Its earlier fixture attempt
mixed a controlled clock with a default real-wall entry sample and failed
before this assertion; that fixture was corrected to use its prepared clock
checkpoint, without changing the ACK or recovery limits.

Runtime now consumes positive checkpoints from its returned durable receipt
before resolving result or cleanup obligations. Cold replay after ACK requires
the marker to be absent and both committed clock floors to cover the fact;
ordinary live-owner finish semantics are unchanged. Revoked executions retain
a factual-only receipt, while cancellation winners and unknown original
completion times remain unchanged. Independent review found one reused
remaining-duration value; it now derives each operation's allowance from the
same absolute cutoff. Nine focused source cases passed in 11.201 seconds
(`/tmp/sdk-received-checkpoint-source310.log`), including actual process death
after ACK and before journal settlement. These focused tests do not replace
native-supervisor or public consumer acceptance, and do not attribute the
original README timeout. The earlier 1,133-case pass predates this correction.
The two additional cases confirm retention during independent receipt-writer
contention and that factual ACK cannot invent an unknown original completion
time. All 48 cases across seven affected modules passed in 48.649 seconds
(`/tmp/sdk-received-checkpoint-integration310.log`), and independent review
accepted the final implementation and all 11 new cases. The subsequent installed
validation retained the original 900-second suite limit.

That installed run reached the original 900-second watchdog before completing.
Its command receipt and complete captured output are under
`/tmp/sdk-received-current-independent310-evidence/sdk-observability-consumer-ig1wcbua/installed-suite/`;
the exact wheel, sdist and origin record are retained under
`/tmp/sdk-received-current-candidate310/`. Final restart did not run.
Seven new producer fixtures rejected an actual `TimeoutError` after positive
capture and writer acquisition had consumed the initial .1-second window.
The fixture now retains that original error, requires both the positive fact
and held writer, and still requires actual SQLite contention in the separate
existing .1-second native finish operation. No bound was widened. All 11
corrected cases passed against the same installed wheel in 7.954 seconds
(`/tmp/sdk-received-current-fixture310.log`). SDK code was unchanged.

The other error was in cleanup of the reserved-capacity fixture
`sdk-managed-stalls-i3a_q_xf`. Its capacity assertions completed, both business
tasks succeeded, the revoked supervisor retained its factual receipt, and
final sampling guards were empty. File timestamps bound cleanup and the next
test transition to about 1.577 seconds, below the original 10-second close
window. The actual cleanup exception was lost when the suite watchdog prevented
unittest's final traceback report. The unchanged installed case passed in
5.686 seconds (`/tmp/sdk-received-current-capacity-repro310.log`), and the later
managed-module run also passed that case. These passes do not identify the
historical exception. Fixture cleanup now saves every original traceback and
retries only the supported observation-cleanup pending exception or managed
`supervisor_checkpoint_pending` / `supervisor_cleanup_unknown` errors, sharing
one original 10-second deadline across all attempts for each app. Other errors
and exhausted cleanup still fail. Direct first-close contract assertions remain
unchanged. Independent review accepted this fixture contract correction; it is
not a diagnosis of the lost historical exception. No speculative SDK close
change has been made, and no further reproduction or full-suite rerun was
started after the user's convergence instruction. The final installed type,
remaining README and six-process restart checks all passed. SDK source is
unchanged from the retained wheel. The fixture correction passed independent
review, syntax checking and `git diff --check`; it has not been presented as a
new complete-suite pass. The remaining full-suite and native matrix requirements
will be verified by the original CI workflow, retaining its existing bounds.

The preceding candidate was rebuilt from sdist and imported from
`/tmp/tmps827c_rj/venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py`.
Its five public consumer scenarios and managed supervisor example passed.
The exact wheel, sdist and build/import record are retained in
`/tmp/sdk-alarm-current-candidate310/`. Full-suite stdout, stderr and the
900-second command receipt are under
`/tmp/sdk-alarm-current-independent310-evidence/sdk-observability-consumer-2y874e6w/installed-suite/`.
The previous child-publication and remaining-startup-window cases passed.
This run instead recorded three errors: close retained a live budget owner in
the two-parent-guard fixture; native crash recovery returned no result while a
sampling guard remained; and the new alarm receipt case received control
admission `TimeoutError` in its final recovery rejection assertion. The alarm
case had already proved both receipts and preservation of its original fact.
These errors do not establish a complete pass. CI remains paused.

An unchanged three-case installed reproduction finished in 3.412 seconds;
only native crash recovery repeated its error. Log:
`/tmp/sdk-alarm-current-failure-repro310.log`. Both crash artifacts contain an
unresolved sampling guard, unchanged original constraints, one business call
and no result. The old crash gate proved entry, but could interrupt later
sampling; refusing another claim preserves that uncertainty.

The two-owner fixture passed its original refusal assertions. Historical rows
show its first ACK committed and the second guard remained; precise cleanup
timing was not recorded. One unchanged forwarding probe passed with a 31ms
close and no dropped records (`/tmp/sdk-two-guard-cleanup-probe310/evidence/timing.json`).
After all refusal assertions, the revised fixture explicitly publishes each
exact retained fact under its existing individual .1-second ACK bound. The
SDK's final close bound is unchanged. Independent review found no blocker.

Sampling retries had a separate diagnostic hole: an admission timeout could
replace an unresolved-clock error already established by SQL. A deterministic
real-SQLite test fails against the retained wheel at that replacement, while
its initial-admission timeout control passes
(`/tmp/sdk-sampling-refusal-baseline310.log`). The correction retains the same
original refusal and chains the later timeout; initial admission and newly
armed errors remain unchanged. The alarm receipt test now uses public clock
diagnostics and `admission_budget` to prove recovery refusal and unchanged
facts. Independent review accepted both changes. All four focused source
cases passed in 1.879 seconds (`/tmp/sdk-sampling-refusal-focused310.log`).
All 60 budget, owner, child-cleanup, entry and supervision integration cases
then passed in 33.537 seconds (`/tmp/sdk-sampling-refusal-integration310.log`).
The corrected positive crash fixture passed in 3.262 seconds. Its real native
receipt confirms both parent and supervisor checkpoints, no remaining guard,
physical containment and an unpersisted result before exit 73. Restart retains
the original .8-second constraint and reaches an exhausted result with exactly
one business call. Evidence:
`/tmp/sdk-confirmed-native-receipt-crash310-evidence/sdk-observability-native-4bsla_qo/`.
The crash stage is now explicitly after native receipt and before result
persistence; separate armed-crash cases continue to require unknown-clock
refusal. Independent review accepted the new fixture boundary; Windows behavior
has only been reviewed in source. Complete installed validation remains required.

The retained pre-correction wheel also passed all five public type consumers,
626 local links and six README examples with no skips:
`/tmp/sdk-alarm-current-types310.log` and `/tmp/sdk-alarm-current-docs310.log`.

The previous installed suite retained failures in cancellation lock admission, cancellation
diagnostic ordering and child ownership-release readiness, plus an error while
setting up the expired child-receipt read. Its full stdout, stderr and timeout
receipt are under the public-consumer artifact's `installed-suite/` directory.
An unchanged four-case installed reproduction finished in 9.054 seconds: lock
admission and the child-receipt case passed; cancellation observation lacked its
requested phase, and the child again missed its original two-second readiness
window (`/tmp/sdk-current-installed-failure-repro310.log`). These results do not
establish a complete regression pass. Diagnosis is continuing with the original
deadlines and retained storage evidence.

Cancellation diagnosis found that fallback note projection used publication time
instead of a retained `captured_at`. The corrected projection also uses the
captured observation time for process freshness. Optional cancellation writes
now share the remaining original control allowance; failed or skipped facts use
the existing bounded local buffer, without claiming persistence. Explicit
cancellation-journal failures still surface after physical cleanup. Independent
review found no blocker. All 36 focused cancellation, receipt and delayed-note
cases passed in 52.462 seconds (`/tmp/sdk-cancel-diagnostic-bounds310.log`).
This source correction has not yet passed complete installed or native validation.

The unchanged child ownership case passed once under forwarding timing probes
in 5.826 seconds (`/tmp/sdk-child-readiness-timing-current310.log`). Its four
collector registrations consumed 0.192 seconds in total. The retained report
`/tmp/sdk-child-readiness-timing-current310.json` records original 4/3/2-second
parent, child and readiness limits, with no dropped trace events. Nested spans
are inclusive; this passing probe does not attribute the earlier readiness
failures to collector registration alone or establish complete acceptance.

SDK-managed recorders now defer collector registration to their owned flusher.
Runtime creates one recorder per claimed lease and scope; public and manually
constructed recorders retain registration at construction, so late flushes
cannot reverse their replacement order. All 39 focused journal, flusher and
child ownership cases passed in 22.007 seconds
(`/tmp/sdk-managed-collector-registration310.log`). The two new cases check
close before the first flush and reversed public flush order using real SQLite.
Complete installed and native validation of this change remain pending.

Independent review found no blocker in the private registration change. The
following integration run finished 90 cases in 179.841 seconds with one failure
(`/tmp/sdk-managed-collector-integration310.log`). The reserved-capacity case
exhausted its original eight-second wait for two Inbox notices, before reaching
its capacity assertions. Both business handlers entered. Retained cleanup data
includes a `database is locked` error during the reserved execution's guarded
claim; it does not yet explain the missing second notice. The raw records are
under `/tmp/sdk-managed-collector-integration310-evidence/sdk-managed-stalls-ml_z2jev/`.
The other 89 cases passed. This failure remains open; CI stays paused.

Retained rows narrow that failure to late Inbox delivery: both stall episodes
formed by `1791222061.366`, and both bridges completed by `1791222063.140`.
The second Inbox acceptance occurred at `1791222067.046`, after cleanup began
at `1791222066.833`. See `/tmp/sdk-managed-notice-failure-timeline310.json`.
A forwarding run of the unchanged case passed in 7.922 seconds, but recorded
1.130 seconds inside notification ACK's native `BEGIN IMMEDIATE` and 2.831
seconds inside a coordinator BEGIN. Parent trace history was complete; its
separate critical-event ring overwrote 353 entries. Child timings were omitted.

Store, result delivery and Inbox transactions now retry BEGIN within the
connection's original busy timeout, restoring that timeout before the body.
Clock sampling, savepoints, bodies and COMMIT remain unchanged. Independent
review found no blocker. The same probe then passed in 10.614 seconds: ACK fell
from 1.188 to 0.073 seconds, while the complete case took longer because it
also waited for the managed handler. Both-notice readiness was 5.436 seconds
before and 5.332 seconds afterward. This supports the admission change, not an
overall throughput or complete-regression claim. Raw before/after records are
`/tmp/sdk-managed-notice-probe/timings.json` and `after-timings.json`.

After this change, all 78 notification, result, durability, managed-supervisor
and pressure cases passed in 169.088 seconds, including all 22 managed cases
and the original capacity-shortage test. Seven added real writer-admission
tests passed in 6.812 seconds. They cover the configured cutoff, zero-timeout
admission, body execution once, timeout/durability restoration, original SQL
errors, restoration failure cleanup and expiry after wall-clock rollback.
Logs: `/tmp/sdk-notification-admission-integration310.log` and
`/tmp/sdk-notification-writer-admission310.log`. Complete installed and native
validation remain outstanding.

The preceding independent rebuild finished
(`/tmp/sdk-notification-current-independent310.log`). Its fresh Python 3.10
virtualenv imported `/tmp/tmpg_k0xicw/venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py`.
All five public consumer scenarios and the managed supervisor example have
passed; the example retained its original 30-second limit. The installed suite
timed out at 900 seconds after 933 passes and one failure, while starting
`test_blocked_bridge_does_not_block_tick_and_close_reports_pending`. Evidence:
`/tmp/sdk-notification-current-independent310-evidence/sdk-observability-consumer-ikx4xdy0/`.

The sole recorded failure, `test_initializing_context_keeps_actual_connection_storage_pending`,
failed identically in an unchanged installed reproduction in 3.434 seconds
(`/tmp/sdk-notification-current-failure-repro310.log`). Its gate waits for
collector registration on the handler thread. That operation now runs on the
owned flusher; Context attachment itself opens no SQLite connection. The revised
test holds the actual registration connection and verifies storage retention
until physical close. A separate case covers close before recorder publication,
including refusal to start business work afterward. All nine cleanup cases
passed against the same installed wheel in 26.463 seconds
(`/tmp/sdk-runtime-registration-current310.log`). Original timing limits and
historical failure evidence remain unchanged. Suite duration is still unresolved.

The exact rebuilt wheel was retained under `/tmp/sdk-notification-current-wheel310/`
and installed for the current public typing and README checks. Import evidence
is `/tmp/sdk-notification-current-installed-import310.json`.

The suite-duration investigation ruled out repeated native identity reads as a
priority: they accounted for only 64.68 milliseconds of inclusive time in a
6.685-second passing public parent/child scenario
(`/tmp/sdk-observation-identity-timing310.json`). A broader parent-only profile
failed with a retained `OperationalError: database is locked`, took 12.550
seconds and overflowed its event buffer. Its overhead and missing child-side
origin prevent using it as normal-run timing evidence
(`/tmp/sdk-parent-cost-timing310.json`).

A narrower forwarding probe passed in 7.479 seconds. It recorded 22 empty
notification event pages that still entered result-clock write transactions,
occupying the coordinator for 2.080 seconds in total. The Host now uses a
private read-only readiness check before collection. Planned cancellations
remain bound to the watched attempt; unrelated Kernel events still advance
cursors, and pending or delivering notification/result rows retain the shared
clock path. Public collection is unchanged. Independent source review found
no blocker. The same scenario on the changed source passed in 6.014 seconds,
with zero empty-page write transactions. Both narrow probes retained the
original deadlines and all timing records. These are individual runs, not a
complete-suite performance result: `/tmp/sdk-empty-notification-timing310.json`
and `/tmp/sdk-empty-notification-after310.json`. All 78 notification, result,
durability, managed-supervisor and pressure integration cases then passed in
138.588 seconds (`/tmp/sdk-collection-readiness-integration310.log`), including
all 22 managed-supervisor cases. Eight added readiness cases passed in 4.297
seconds (`/tmp/sdk-collection-readiness-edge310.log`): actual writer contention,
public clock observation, planned and historical cancellations, unrelated
events, a racing cancellation through successive Host pumps, and notification
and result lease fencing after wall rollback. The next independent installed
candidate finished within the original limits; its wrapper log is
`/tmp/sdk-collection-current-independent310.log`. Its five public scenarios and
managed-supervisor example passed from
`/tmp/tmptdutsyqt/venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py`.
The exact sdist-rebuilt wheel is retained in `/tmp/sdk-collection-current-wheel310/`,
and public evidence is under
`/tmp/sdk-collection-current-independent310-evidence/sdk-observability-consumer-4svbk4rp/`.
The installed full suite completed 1,126 cases in 879.142 seconds, with one
failure, one error and 17 platform skips. The held-child-publication success
case returned a parent snapshot without a result, and its fixture then raised
`AttributeError` while recording that result. The remaining-startup-window
case expected `handler_process_start_failure` but received `budget_clock_unknown`.
Both retained failures are under diagnosis. The wrapper's final restart
consumer did not run because the installed suite failed. Complete installed
and native acceptance remain pending.

An unchanged two-case reproduction against that retained wheel finished in
13.620 seconds (`/tmp/sdk-collection-current-failure-repro310.log`). Startup
restoration passed; the held-child-publication success case again returned a
parent snapshot without a result, followed by the fixture's `AttributeError`.
Its retained business receipt contains the exact successful child result, but
the parent completion clock remains unknown. The original assertions and
deadlines remain unchanged. The
same installed wheel passed all five public type consumers and 626 local links
plus six README examples. Its import record is
`/tmp/sdk-collection-current-installed-import310.json`.

Two bounded forwarding probes then recorded actual sampler ownership without
adding SQL, wall samples, ACKs or filesystem writes during sampling. The first
passed in 12.316 seconds. The second reproduced the error in the raw-failure
branch in 12.372 seconds. Its trace is
`/tmp/sdk-completion-sampling-probe310/evidence-run2/sampling.json`.
The same worker armed and captured token `d2f54734-6ec5-4686-a302-0d6e6411b6bd`;
child result proof borrowed it, but parent completion recognized only the
Context's separate sampler and refused that token throughout its original
0.1-second window. Cleanup acknowledged the exact captured fact afterward.
No process trace was missing or dropped. This establishes an ownership handoff
defect for that reproduction; the earlier failures lack this token-level trace.

Successful factual child delivery now retains one exact owner/pending tuple for
its bound Context's completion reader. The handoff occurs after physical reader
close and the original final budget check. Exact Context, capability, Kernel,
command and lease bindings plus current registry/tuple identity are required.
Existing foreign/extra/ancestry guard refusals and cleanup ACK ownership remain
unchanged. Both new positive tests failed against the preceding installed wheel
with the same clock error (`/tmp/sdk-child-completion-handoff-baseline310.log`).
All 65 related source cases passed after the correction in 56.343 seconds,
including success, raw child failure, foreign bindings, replaced tuples,
registration changes, reader lifetime and the unchanged native end-to-end case.
Independent review found no blocker. Full installed and native acceptance remain
pending.

The sdist-rebuilt wheel then passed all four new ownership cases and the
unchanged native success/raw-failure case outside the checkout: five cases in
16.057 seconds (`/tmp/sdk-child-completion-handoff-installed310.log`).
`/tmp/sdk-child-completion-handoff-build310/import.json` records the actual
`venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py` import.
That directory retains the sdist, rebuilt source, wheel and virtualenv; the
successful build log is `/tmp/sdk-child-completion-handoff-rebuild310.log`.
An earlier packaging attempt failed on the read-only default pip cache, before
wheel creation; rerunning the same sdist build with pip caching disabled passed.
The installed candidate also passed five public type consumers and 626 local
links plus six README examples. These focused checks do not replace the full
installed suite or native matrix.

Three unchanged startup forwarding probes passed in 1.461, 1.507 and 1.524
seconds; reports are under `/tmp/sdk-startup-forward-probe310/` and its
`-repeat1` and `-repeat2` siblings. One crossed the startup deadline during a
known captured sample and still acknowledged that exact fact before returning
the expected startup failure. None reproduced the original SQLite lock failure.
Killed workers did not publish their in-memory restore trace, so that stage is
explicitly unobserved. The original startup failure remains under diagnosis;
these passing probes do not discharge it.

A separate controlled captured-ACK contention probe passed in 1.406 seconds
against the handoff wheel (`/tmp/sdk-startup-captured-ack-probe310/`). A real
fixture writer blocked the supervisor's already captured token. Both parent
and supervisor recorded SQLite lock failures; the original startup alarm then
interrupted ACK. When parent termination began, the fixture released its writer.
The supervisor acknowledged the original token, sent its timeout receipt and
physically closed its Kernel; the parent recovered that receipt after termination
and returned the expected startup failure. The supervisor's eventual exit code
was `-9`, unlike the historical self-close failure with exit code `1`. This run
does not reproduce that original failure or establish what happened before its
sampling capture. All writer ownership and cleanup stages were observed; the
killed worker's restore buffer remains unavailable.

A second controlled probe reached the missing boundary using the original
native alarm: arm COMMIT completed, then the alarm interrupted before a clock
fact was captured. The owner retained `(token, None)` and the original
`_DeadlineExpired`. `_finish_budget_capture` rethrew that stored control-flow
exception twice, suppressing both terminal sends; supervisor close then refused
the unresolved sample and exited with code `1`. The original startup assertion
still passed in this run because the parent took its ordinary startup-expiry
fallback. The missing receipt is nevertheless directly observed in
`/tmp/sdk-startup-uncaptured-arm-probe310/timing.json`. This establishes the
packet-loss defect; the historical failure did not record that exact internal
state, so its complete timing remains unavailable.

Uncaptured cleanup now returns an unknown checkpoint with the exact token and
original error instead of invoking an impossible ACK and rethrowing the retained
alarm. It preserves the guard, captured-envelope absence and original envelope.
The captured-fact branch still has its original exception boundary and allowance;
fresh operator interrupts are not caught more broadly. Independent review found
no blocker. A new isolated real-alarm/SQLite/pipe regression failed against the
preceding installed wheel (`/tmp/sdk-uncaptured-alarm-baseline310.log`) and passed
after correction. It checks two actual receipts, no additional SQL or wall
sample, unchanged pending ownership, explicit failed close, and recovery refusal.

The full supervisor probe after correction passed in 1.397 seconds with every
controlled stage reached. Its parent received the exact unknown checkpoint and
original alarm error; the unresolved guard and subsequent supervisor close
failure remained visible. Before/after assertions and import paths are retained
in `/tmp/sdk-uncaptured-alarm-before-after310.json`; the fixed source trace is
`/tmp/sdk-startup-uncaptured-arm-fixed-source310/timing.json`. Both runs denied
business invocation and retained their original startup/control deadlines.
All 45 native-budget, owner-registry, handler-entry and supervision integration
cases then passed in 22.707 seconds. Complete installed and native matrix
validation of the combined corrections remains pending.

A read-only audit of CI run `37203657162` reconciled eight leaf failures in five
categories: wait-policy fixture activation, checkpoint-note expiry, Windows
marker sharing, deferred timeout settlement, and missing script byte counts.
Three isolated-consumer failures wrap those same nested failures. Current
fixtures and corrective source paths have local witnesses, but the original
Windows checkpoint expiry and script-loss causes remain unattributed. The old
records establish no additional current source defect; they also do not close
native acceptance. Retained raw failures are in
`/tmp/sdk-ci-audit-failures-37203657162.json`.

The source error is temporary-directory cleanup after bounded thread timeout and
reentrant close. The retained directory has Kernel WAL/SHM files. Source inspection
confirms that a late handler can admit an independent completion reader after
Context close; the exact connection that produced the residue was not recorded.
The exact original residue-producing connection remains unidentified.

The reader now reserves Context ownership before raw wall sampling or SQLite
admission. Context close atomically refuses later reservations. Admitted readers
retain storage and capacity through the entire body and any failed physical
close; Runtime retries only physical close on the exact reader after the body
has left. Capture and cleanup release admission retain their original absolute
deadlines. Independent review found two test proof gaps, now covered by actual
lock timeout arguments and zero-SQL traces during retry. Initial tests exposed
a fixture assignment typo and mutable captured fixture state; both are fixed.
The final eight lifetime cases passed. Existing completion and default connection
affinity cases passed in the preceding 34-case run, whose three errors were
limited to that fixture (`/tmp/sdk-completion-reader-corrected310.log`).

The pressure failure is late stall callback delivery under saturated workers.
The callback did arrive after its original eight-second readiness wait failed.
Its saved notice was observed at `1791215977.4732375`, bridged at
`1791215979.29661`, accepted into the Inbox at `1791215983.8752928`, and invoked at
`1791215984.511407`. These times identify the delayed stages; they do not yet
identify the lock owner or justify extending the wait.

An unchanged instrumented pressure case later passed in 12.550 seconds
(`/tmp/sdk-stall-trace-run310.log`). During its first Inbox writer admission wait
of 1.030 seconds, budget-sampling transactions occupied about 0.695 seconds and
empty Inbox claims about 0.135 seconds. These are competing writer intervals,
not a single long transaction. The first delivery window is recorded; later
parent trace records hit the configured cap, and forked handler traces are absent.
Background Inbox consumers now use a readonly advisory check while idle.
Any pending message for their source or any processing lease retains the
original atomic claim and logical-clock protection. Public claims are unchanged.

Two further recovery checks failed: generation-zero replay was refused with
`process_cleanup_in_flight`, and immediate applied Effect recovery remained
`queued` when the fixture expected `succeeded`. These outcomes need causal
diagnosis; they do not authorize releasing unresolved cleanup ownership or
extending the original recovery budget.

A forwarding reopen probe passed in 1.472 seconds and recorded completed
Future/Context cleanup with stale local thread ownership at `run_once` return
(`/tmp/sdk-recovery-forward-reopen310.log`). Driver retirement now revisits only
that exact completed generation through the existing ownership checks. The
focused regressions cover both immediate reopen and refusal while actual
handler cleanup is still held.

The original Effect probe passed in 1.765 seconds without sampling guards
(`/tmp/sdk-recovery-forward-effect310.log`). A separate deterministic probe
forced actual process death after the durable sampling marker committed and
before its original sample/ACK. The same marker survived resolution and blocked
the replay claim, leaving attempt/fence unchanged and reproducing the original
`queued` assertion in 1.266 seconds (`/tmp/sdk-effect-orphan-forward310.log`).
This demonstrates the protective behavior; it does not identify the unrecorded
guard state in the failed complete run. The positive recovery fixture now holds
the actual Context budget lock across its original crash phase and checks
confirmed entry with no pending token or durable guard before mutation. It adds
no clock sample or ACK. All four original recovery cases and the separate real
orphan refusal case passed in 9.112 seconds. The latter preserves the same
guard, response, original constraints and floor, with no second invocation or result.

The installed suite keeps its 900-second limit. Public consumer and managed
supervisor example limits remain 180 and 30 seconds. The latest source run also
exceeds the installed suite's original limit; its per-case timings are saved at
`/tmp/sdk-child-anchor-source310-timings.json`. The corrective records below retain earlier
candidates, failed attempts and their original evidence.

## Corrective history, 2026-10-05

CI remains paused: run [37269716472](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37269716472)
was cancelled at the user's request. Known defects must be fixed before another CI
run or a push that triggers CI. The working tree below is not a completed candidate.

An earlier complete source diagnostic ran 1,051 cases in 967.504 seconds, with
four failures and 17 platform skips
(`/tmp/sdk-positive-guard-current-source-full310.log`). Per-case timings are in
`/tmp/sdk-positive-guard-current-source310-timings.json`; the original installed
suite cutoff remains 900 seconds. The strict positive and expired foreign-guard
recovery cases passed. Remaining failures were initial completed-result delivery
under a main writer, child readiness before its contention writer, permanently
unknown completion time after successful binding recovery, and a tardy second
managed stall notice before the capacity assertions.

Tokenless write-admission failure now has a readonly fallback: guard absence
and the canonical floor share one SQLite snapshot. An existing transaction is
refused so stale snapshots and uncommitted floors cannot become authority; the
caller transaction remains untouched. Successful proof merges only the original
envelope's checkpoint. Foreign guards remain fenced, and neither raw wall
sampling nor ACK/guard retirement occurs in this fallback. The first 36-case
run passed completed-result delivery and strict guards, but failed a newly
authored comparison using a later rather than identical elapsed sample, and
the original two-second readiness precondition
(`/tmp/sdk-readonly-floor-guard310.log`, 68.526 seconds). The comparison now uses
the same retained checkpoint; no tolerance or original bound was widened.

An actual traced readiness reproduction passed unchanged in 5.661 seconds
(`/tmp/sdk-child-readiness-native-trace310.log`). Its bounded SQL evidence is
`/tmp/sdk-child-readiness-native-trace310-evidence/sdk-child-storage-contention-l65qdl9x/readiness-native-trace.json`.
Independent review approved removal of duplicated live parent verifications
and one redundant fresh sampling before readonly receipt attachment. Targeted
Kernel claim still atomically checks the original parent lease, confirmed entry,
guards and inherited limits. The subsequent 50-case integration passed 49 in
78.186 seconds (`/tmp/sdk-guard-cold-entry-reviewed310.log`); the completed child
was actually delivered through the bounded rescue, but its successful parent
outcome became permanently unknown when completion-time capture waited on the
shared Kernel lock. Independent factual completion-clock capture now samples
the actual return once and reads a bounded committed snapshot, retaining the
same conservative elapsed floor, exact ancestry and original 0.1-second window.
It never arms, acknowledges or clears a budget sample. The first 77-case run
passed delivery and current binding recovery but found two test construction/
raw-error assertions (`/tmp/sdk-factual-completion-integrated310.log`). The
next 38-case run exposed another overly specific wait-error assertion: an exact
sampling-unresolved refusal preceded successful immutable result rescue and
parent settlement. The assertion now admits only that exact sampling refusal;
foreign-guard denial, original cutoffs, exact result identity and one business
invocation remain required. Independent review approved the production path and
the narrow fixture corrections. All 41 completion, settlement, binding,
delivery and strict-guard cases passed in 53.560 seconds
(`/tmp/sdk-completion-rescue-corrected310.log`), and the five public type consumers
passed (`/tmp/sdk-completion-current-public-types.log`).

A12's retained databases show both episodes were formed and bridged before the
failed readiness wait, while the Orchestrator-to-application Inbox handoff was
late. A real, unchanged one-case trace passed in 7.990 seconds
(`/tmp/sdk-a12-notice-latency-before310.log`); bounded timing evidence at
`/tmp/sdk-a12-notice-latency-before310/latency-trace.json` records notification
BEGIN waits of 0.930, 0.831 and 0.630 seconds. Older real SQL evidence also
records eight empty delivery COMMITs consuming 0.254 seconds within a 1.116-second
ring tail. Host polling now reads both notification and result queues in one
readonly statement and skips a write claim only when neither has pending or
leased work. Explicit public delivery/claim semantics remain unchanged; any
candidate retains original atomic clock and lease checks, and read errors stay
errors. Independent review approved the scope. The 44 notification/Host/Inbox
cases passed in 27.275 seconds (`/tmp/sdk-a12-idle-delivery-corrected310.log`);
the strengthened real writer/read-through and shared-result lease rollback
proofs passed in 1.769 seconds (`/tmp/sdk-a12-idle-proof-final310.log`). The
complete managed suite then passed all 22 cases in 81.777 seconds
(`/tmp/sdk-managed-idle-delivery-final310.log`), including the original second
notice/capacity assertion, actual memory denial, source/notice cutoffs and cleanup
ownership. The candidate was rebuilt and installed from
`/tmp/sdk-completion-idle-final-wheel310/dispatcher_sdk-0.7.0.dev2-py3-none-any.whl`;
build and installation completed successfully. The complete current source
run is retained at `/tmp/sdk-completion-idle-final-source-full310.log`, with
fresh per-case timing destination `/tmp/sdk-completion-idle-final-source310-timings.json`.
The complete source run finished 1,070 cases in 974.287 seconds, with one
failure, two errors and 17 platform skips. It did not pass; elapsed time still
exceeds the unchanged 900-second installed-suite cutoff. The failure was the
healthy successor's startup, after the original admission-timeout classification
and capacity release had succeeded. Retained SQL timing identifies a first
synchronous Context binding publication taking 0.0858 seconds, on top of about
0.090 seconds of entry preparation and further collector setup, before the
original 0.250-second startup signal. Current binding now uses the handler
recorder's existing retained asynchronous publication/retry mechanism;
collector registration and first-entry ACK order stay unchanged.

One error identifies a completion-clock integration defect: a Context's own
already captured, pending exact-token fact was treated as an unowned unknown
clock, retaining its original value but making its receipt permanently
unsettleable. Narrow factual-clock proof for that live owner is now implemented;
foreign, additional and uncaptured guards must remain unknown and no guard may
be cleared by completion capture. The other error is the new late-ACK fixture's
sampling refusal; its separate 0.035-second sleep and ACK operation do not prove
ACK completed within the caller's original 0.1-second window. Actual stage
timings and raw errors are being retained before choosing a correction.
Complete corrected source, independent installed and native acceptance remain open.

The corrected owner proof and asynchronous binding integration passed 60 cases
in 63.320 seconds (`/tmp/sdk-owned-clock-async-binding-first310.log`), including
the original pending-token result and healthy successor startup assertions.
Fresh independent review then found that a real SQLite progress interruption
could replace a preceding refusal at deadline exhaustion. The correction requires
this reader's timeout state and an actual SQLite interruption; unrelated SQL
errors remain raw. Independent review approved it, and all 22 completion-clock
cases passed in 7.938 seconds (`/tmp/sdk-completion-interrupt310.log`). New real
SQLite tests preserve the same original guard exception under recursive-query
progress timeout and the same permanent missing-table error after expiration.
These focused passes do not replace the pending complete or installed acceptance.

The ACK fixture now triggers the actual original-token acknowledgement after a
real sampling refusal, removing its artificial pre-ACK sleep while retaining the
original 0.1-second capture window. Independent review approved this ordering;
post-COMMIT diagnostic timestamps do not impose a scheduler-dependent order on
the reader. The 62-case completion/ownership/binding integration passed in
67.933 seconds (`/tmp/sdk-completion-ordered-ack310.log`). Native observation,
script output/recovery, process integration and all managed supervision cases
passed together: 46 cases in 163.855 seconds
(`/tmp/sdk-clock-binding-native-managed310.log`). Types passed all five consumers;
documentation checked 554 links and six README examples with no skips.

The current source wheel was rebuilt and reinstalled successfully from
`/tmp/sdk-owned-completion-current-wheel310/dispatcher_sdk-0.7.0.dev2-py3-none-any.whl`.
The complete corrected source run finished at
`/tmp/sdk-owned-completion-source-full310.log`, with a new per-case timing
destination `/tmp/sdk-owned-completion-source310-timings.json`. There is no current
complete source, isolated rebuilt-wheel or native matrix pass yet.

That run completed 1,077 cases in 980.226 seconds, with two failures, one error
and 17 platform skips. Previous pending-value and healthy-startup defects passed.
Remaining failures are the real writer-cutoff child rescue and active native
cancellation cleanup; the error is a foreign-owner ACK fixture with an independent
pre-ACK sleep. Child rescue cannot acquire the shared Kernel RLock inside its
original proof window even after recorded native writer rollback. The artifact
does not identify the owning thread; the budget monitor and other control writers
remain competing contenders. An independent readonly factual reader is now
integrated, retaining exact positive capture ownership and a fresh final authority
snapshot after the sole result read. The focused 78-case integration finished
with four positive fixtures refusing a wall read in the real entry revocation
check, before the factual proof began. Their no-wall assertion now covers the
actual rescue only; the 13-case clock cleanup suite passed in 10.267 seconds
(`/tmp/sdk-child-factual-scoped-wall310.log`). The public writer-cutoff rescue,
fresh final cancellation, real final progress interrupt and permanent SQL error
passed in the original focused run. Independent final source review approved
the exact ownership, scalar lease checks and preserved timeout/error causes.

Cancellation returned the original cancelled winner but no explicit physical
cleanup callback. The supervisor was killed before producing its containment
packet; EOF classification followed full-window budget retry, and parent capture
could not observe a newly ready packet during that retry. EOF now proceeds to
bounded factual containment first. Ready original packets interrupt only transient
capture retries, and revocation gives packet publication the existing one-second
grace. An independent review found and corrected a permanent-error masking path:
packet recovery now retains permanent control failure while separately retaining
explicit physical cleanup evidence. The 18 native capture/packet/cancellation/
cleanup/parent-floor cases passed in 20.971 seconds
(`/tmp/sdk-packet-error-gating310.log`), including real BUSY and permanent SQL errors
with the original pipe becoming ready during capture. These are focused source
passes. A newer current-source wheel, including these fixes and the readonly
flush anchor, was built and installed successfully from
`/tmp/sdk-child-anchor-current-wheel310/dispatcher_sdk-0.7.0.dev2-py3-none-any.whl`.
Its actual import outside the checkout was confirmed under
`/tmp/sdk-a05-a12-current-installed310/lib/python3.10/site-packages`.

The measured dormant-sampler probe completed ten genuine empty ticks in 0.0399
seconds using 40 readonly journal connections, with unchanged persisted state
and no errors (`/tmp/sdk-dormant-stall-baseline-corrected310/evidence.json`). No
optimization is justified by that small cost. The prior complete run's exact
installed-suite subset projects 1,066 cases and 972.828 seconds; this projection
is not an actual installed-suite result and does not alter the original 900-second
cutoff. Its 10,000-summary case spent 1.297 seconds in readonly pagination, versus
18.284 seconds of actual execution. Budget-capture and flush costs require direct
stage attribution before choosing further changes. A separate native stage
probe passed the unchanged case in 19.969 seconds. Its actual handler recorded
157 captures taking 4.931 seconds and 206 flush attempts taking 11.320 seconds;
these overlapping inclusive durations cannot be added. An external idle
readonly connection held only during the existing flusher's lifetime reduced
the same case to 13.117 seconds, with 174 flush attempts taking 4.420 seconds
(`/tmp/sdk-summary-anchor-budget-stages310.log`). Capture durability and original
limits were unchanged. This measured improvement supports the narrow production
anchor now integrated, without a transaction, retained cursor or new public
close API. Physical close remains owned by the existing live worker; admission
failure releases failed setup before ordinary flushing. Close refusal retains
the original connection and live worker. The production native pressure,
cancellation, stream and existing storage-lifetime suite passed 14 cases in
40.741 seconds (`/tmp/sdk-flush-anchor-native-first310.log`); the pressure artifact
records 12.967 seconds and 201 pages with no failures. Public types passed five
consumers, and the current installed wheel passed six README examples with zero
skips and 554 links. New anchor lifecycle verification and a complete unchanged
900-second installed-suite pass remain required.

The current-source managed supervisor, native budget-capture and thread-capacity
integration passed 31 cases in 75.589 seconds
(`/tmp/sdk-child-anchor-managed-current310.log`). It includes the 22 A12 cases,
actual native memory denial, capacity shortage, original deadline/result replay
and retained physical collector ownership. No original budget was enlarged.

The anchor lifecycle, stream, Runtime storage and thread capacity suite passed
20 cases in 34.167 seconds (`/tmp/sdk-flush-anchor-lifetime-final310.log`). Six
new real SQLite scenarios prove idle WAL checkpoint/fresh visibility and FULL
or NORMAL writer durability, genuine missing-file admission fallback, manual
flushing, same-connection close retry without flush replay, exact handler flusher
storage/capacity retention, and failed setup cursor release before ordinary work.
Direct recorder close now joins its existing worker only within the same caller
deadline's remaining time; a persisted telemetry receipt does not discharge a
blocked physical connection. The revised current-source wheel was rebuilt and
installed at `/tmp/sdk-child-anchor-joined-wheel310/dispatcher_sdk-0.7.0.dev2-py3-none-any.whl`.
The sequential 1,092-case complete source run is active at
`/tmp/sdk-child-anchor-source-full310.log`, retaining fresh per-case timings at
`/tmp/sdk-child-anchor-source310-timings.json`. Source files and tests are frozen
during that run; it excludes only the separately required nested installed
consumer test, as earlier runs did. No current complete pass is claimed yet.

The complete 1,057-case diagnostic finished in 992.597 seconds with six failures,
two errors and 17 skips (`/tmp/sdk-recorder-ownership-final-source-full310.log`).
It did not pass, and its elapsed time exceeds the unchanged 900-second installed
suite limit. Its raw failures identify receipt-fixture admission consumption,
bounded readonly proof refusal, child readiness, Run-expiry classification,
pending thread-entry clock observation and parent revocation precedence. The
entry gate now observes wall advancement through its durable pending-entry
protocol under the same Context budget lock; confirmed entry keeps pure elapsed
projection. Only the producer's exact Run-deadline CAS fact becomes a timeout;
unmarked and malformed CAS failures retain the original generic failure. Child
recovery first performs bounded readonly parent-revocation inspection. None of
these paths replay business or extend the original work window.

The entry/receipt/result-proof corrective integration passed 55 cases in 58.738
seconds (`/tmp/sdk-source-eight-corrections310.log`). A subsequent 44-case run
retained one strict fresh-recovery failure
(`/tmp/sdk-parent-revocation-child-contention310.log`), while the actual native
cross-store crash/revoked-parent path and five original child-contention cases
passed. The failure's real foreign sampling marker remained committed, but
capture admission timed out before checking it and the retry window returned
trusted positive cached time. Recognized non-token capture admission failures
now retry within the same native work cutoff. Expiry performs only bounded
readonly classification; unresolved foreign markers remain unknown, and proven
absence preserves the original transient failure. Successful capture retry uses
the existing canonical-floor import. The first 35-case correction passed in
64.234 seconds (`/tmp/sdk-positive-initial-guard310.log`), including a new real
foreign-marker witness that exhausts capture admission before its guard read.
Independent review then required optional proof handling for custom Kernels and
expiry classification before any zero-timeout capture. Those adjustments and
the current complete source/installed/native candidate remain under validation.

The 1,057-case source run stopped after 84 tests with one error in 115.743
seconds (`/tmp/sdk-expired-guard-final-source-full310.log`). Its delivery-cause
fixture held the real control lock before reconstructing an expired window,
although the case explicitly models a window already reconstructed and attached.
The fixture now constructs that same real window before holding the lock. The
production initial recovery guard remains unchanged, as do the original proof's
0.1-second bound, error identity and cause assertions. Independent review approved
the staging correction. All seven delivery-diagnostic and expired-guard cases
passed in 3.315 seconds (`/tmp/sdk-child-initial-vs-delivery-control310.log`).
This focused result does not establish full candidate acceptance.

The next source run stopped after 260 tests in 255.220 seconds on a stale schema-4
metadata assertion (`/tmp/sdk-initial-vs-delivery-final-source-full310.log`).
Current-store isolation, strict marker types, preflight and activation fixtures
now describe Kernel schema 5; the legacy managed-gate fixture explicitly applies
both 3-to-4 and 4-to-5 upgrades, preserving the intermediate historical assertion.
The invalid-marker case still rejects schema 4, a future integer version, and
noninteger representations of the current version. Current storage documentation
is aligned; Orchestrator schema remains 4. All 45 isolation, managed-gate,
preflight and activation cases passed in 19.115 seconds
(`/tmp/sdk-schema5-current-contract310.log`). Original retained-outcome copy
semantics and a new complete current candidate run remain required.

The retained-outcome suite passed 12 of 13 cases in 19.237 seconds
(`/tmp/sdk-schema5-original-settlement310.log`). The failed lifecycle-contention
case persisted the original result but blocked its public caller. An unchanged
real-lock reproduction failed in 1.894 seconds; its `lifecycle-caller.json`
captures the driver waiting at the unbounded recorder-removal lifecycle lock
(`/tmp/sdk-lifecycle-recorder-baseline310.log` and its evidence directory).
Active and retired recorder ownership now uses the existing independently guarded
lifecycle condition; recorder I/O stays outside that lock. Exact active entries
retain capacity until close and removal, and live retired workers are retained
before removal. Independent review approved the ownership and lock ordering.
All 18 result-retention, collector-capacity and repeated-close cases passed in
26.365 seconds (`/tmp/sdk-lifecycle-recorder-integrated310.log`). Neither business
budgets nor the original caller-return assertion were widened.

A05 now has schema-5 write-ahead sampling guards and exact live-owner retries.
Unacknowledged sampling fences fresh recovery and descendant business admission;
acknowledgement only advances the canonical clock floor, preserving constraints.
A real committed arm could exhaust the original short admission window before
`current_time()` retained its capture. The corrected path reads the committed
watermark under its already-owned lock and retains the captured floor before
checking the acknowledgement deadline. Targeted child claim failures also transfer
the same live sampler into the original child retry window. These changes do not
clear foreign or interrupted-process markers.

Five focused real-storage/native-clock cases passed in
`/tmp/sdk-a05-canonical-monitor-integration310.log`, including independent writer
contention, slow committed arm return, exact-owner transfer, signal-handler I/O
exclusion, and a forward wall jump immediately after consuming a committed
checkpoint once. That integrated run still failed two original child-contention
cases. After correcting live-sampler races, all five original child-contention
cases passed unchanged in 15.362 seconds
(`/tmp/sdk-a05-sampling-owner-race-retry310.log`). The subsequent combined
clock/storage/child-capacity/collector/close suite passed 52 in 51.200 seconds
(`/tmp/sdk-a05-storage-capacity-integrated310.log`). Earlier native parent-only
and supervisor-only forward-floor recovery cases passed locally. A wider 53-case
native/budget run then retained one failure and one error: the public snapshot's
elapsed floor was absent from its original receipt, and supervisor entry performed
a redundant capture before forwarding committed entry. The receipt correction
passed its actual reopen case in 1.205 seconds. Native entry now consumes and
forwards the committed entry packet before another sample; known expiry keeps its
original timeout cause. Twelve focused native/Windows-budget cases passed in
6.006 seconds (`/tmp/sdk-a05-native-terminal-own-cleanup310.log`); actual native
Windows execution remains unverified.

A fresh ownership review found that a short child window and pre-handler
admission could discard an unresolved helper. The live helper now resides in
`execution_kernel/budget_capture.py`, and Kernel retains each pending exact-token
owner independently of the caller's lifetime. Its owner lock protects a distinct
finish-only operation; existing Runtime maintenance and close can publish the
retained fact without another sample. Arm and ACK transactions use only committed
clock authority; the first raw wall observation occurs after the durable guard.
An interrupted uncommitted RELEASE/COMMIT rolls back its writer, while only the
same retained owner may reconcile an ACK that actually committed before
interruption. Fresh Kernels cannot infer or clear that owner's marker.

Four actual SQLite regressions passed in 1.090 seconds
(`/tmp/sdk-a05-budget-owner-registry310.log`): dropped expired caller with exact
owner retention, interrupted committed ACK, zero wall reads before committed
arm, and interrupted RELEASE with independent writer admission afterward. An
initial combined native/owner/collector/queue/child-capacity suite passed 27 in
15.260 seconds (`/tmp/sdk-kernel-owner-first-integrated310.log`). The queue selector
also excludes unresolved guarded roots; independent queued work remains eligible.
ACK now atomically promotes the same protected floor into the Kernel clock
watermark. A separate real managed-Run/lease/effect witness passed in 0.349 seconds
(`/tmp/sdk-a05-budget-owner-watermark-authority310.log`): after raw-wall rollback,
a fresh Kernel rejects expired source authority and cannot claim the queued
sibling. ACK performs zero new raw wall observations and retains every original
cutoff and identity. These focused passes do not establish a complete candidate
regression.

Thread capacity now remains charged until exact-generation handler and driver
collector ownership ends. A held real SQLite flusher verified a successful original
business result, a still-queued successor, usable owner-thread connection, and
successor admission only after release:
`/tmp/sdk-thread-collector-capacity310-v3.log` and
`/tmp/sdk-thread-collector-capacity-phjcr2uh/evidence.json`.
An unresolved captured clock fact also retains its Context and Kernel writer;
cleanup retries acknowledge only that fact under a shared maintenance deadline.
The repeated-close path passed its independent real-writer regression in 2.351
seconds (`/tmp/sdk-budget-capture-close-lifetime310.log`): the first close retained
storage and capacity; the second acknowledged the original token, with no new
sample, deadline increase or business replay. The original result receipt stayed
unchanged. A separate actual idle-coordinator writer probe also passed; empty
polling no longer acquires an observation write transaction. ChildService close
now shares its original caller deadline across coordinator join, lock inspection
and Future wait; pending ownership retains Kernel and journal storage. Two real
SQLite coordinator/worker close regressions passed in 0.774 seconds
(`tests/test_child_service_close_lifetime.py`). A stopped coordinator cannot submit
business after returning from a contended journal transaction.

A12 includes an independent process Runtime, bounded capacity and configured
memory admission, inherited original notice/source cutoffs, explicit resource
shortage, stable receipt identity, and cleanup ownership. An actual isolated Linux
worker rejected a 512 MiB + 1 allocation under a 512 MiB address-space limit and
released its reservation. This establishes native memory enforcement for that
worker, not aggregate Linux RSS or native Windows Job acceptance. The latest
17-case Python 3.10 diagnostic failed five assertions and produced two errors in
128.988 seconds (`/tmp/sdk-managed-supervisor-17-python310-diagnostic.log`):
queued pre-business admission/receipt contention, source-control races, notification
acknowledgement, and Host close failed. Corrective source now retains the original
admission deadline and exact helpers across Futures, retries only known transient
control errors, and always attempts independent Host stop after a managed-close
error. A cleanup-note fixture now holds a real rollback-journal EXCLUSIVE read
block rather than treating a healthy WAL reader as blocked. The first focused
eight-path run then found a consolidation import defect: Context imported a helper
from the wrong private module, causing no actual handler invocation. After fixing
the dynamic import, seven paths passed in 47.014 seconds and corrected independent
Host close passed in 0.377 seconds. The complete current-watermark 19-case run
passed 17 in 98.306 seconds with two fixture errors
(`/tmp/sdk-managed-supervisor-full19-watermark310.log`): a private one-shot fixture
bypassed production's frozen admission retry, and the held-writer fixture rejected
a real post-arm timeout before ACK. Their correction keeps the original .05/.1
publication and original source/notice windows, requires the same exact captured
fact and real subsequent ACK writer failure, and does not change production.
Both fixture corrections passed their focused rerun in 6.466 seconds. A later
stopping-status query found that the independent business Kernel may already be
closed while managed cleanup retains storage. Status now reads the original
control and execution in one bounded read-only snapshot. Three stopping/byte-cap/
lock-admission cases passed in 2.496 seconds
(`/tmp/sdk-managed-supervisor-stopping-status-original-bounds310.log`).

Fresh review also found two ownership gaps. A pre-native admission can retain a
clock fact without creating a Context, so capacity release and status now consult
the exact-execution Kernel owner registry. Unavailable registry inspection stays
unknown and retains the reservation. CPython executor submission can enqueue a
WorkItem before thread creation raises; a per-attempt gate now permits dispatch
only after its Future is registered. Failed submission retires that executor,
preserves the original error and receipt, and prevents further claims while
accepted work finishes. Independent read-only review approved these transitions.
Six focused cases passed in 6.613 seconds
(`/tmp/sdk-managed-supervisor-executor-registry-focused6-310.log`), including an
actual queued WorkItem becoming RUNNING before rejection and a real pre-native
clock owner retained without Context or process. The complete 21-case current
managed suite remains pending.

The complete reviewed 21-case run then passed 19 with two failures in 99.586
seconds (`/tmp/sdk-managed-supervisor-full21-reviewed310.log`). Its actual
timeout result and one handler invocation were retained, but notification retry
did not become dead within the original eight-second wait. The managed Inbox
used a zero busy timeout and a single immediate BEGIN attempt; bounded write-lock
admission is being corrected without changing the original receipt or handler
budgets. A strict common-sample assertion also exposed a one-ULP clock-floor
extension from floating-point reassociation. Checkpoint construction now rounds
the exact elapsed affine floor upward only when the nearest float lies below it;
exact and unchanged anchors stay unchanged. Twenty-five clock/owner/native
cases passed in 2.664 seconds (`/tmp/sdk-clock-floor-fractional-current310.log`),
including persisted fractional anchors and the original no-drift examples.
Independent read-only review approved the numerical and ownership integration;
the separate Inbox correction and current complete rerun remain pending.

A wider current A05/native/collector/close run retained one failure and one error
among 70 cases in 73.132 seconds
(`/tmp/sdk-a05-current-floor-lifetime-integrated310.log`). Internal checkpoint
diagnostics had been merged into an actual provider's original error details;
they now remain separate outcome/settlement evidence, preserving the provider
error exactly on POSIX and Windows. The independent all-writer fixture also
rejected a real exact post-arm admission timeout; it now accepts that specific
cause only with the original token, captured envelope and held transactions.
Seven focused provider/recovery/floor cases then passed in 26.375 seconds
(`/tmp/sdk-a05-provider-raw-clock-current310.log`). Original publication windows,
business constraints and raw failure facts are unchanged; the complete current
candidate remains unverified.

The reviewed current A05 integration subsequently passed all 73 cases in 63.485
seconds (`/tmp/sdk-a05-raw-facts-reviewed-integrated310.log`): original parent/
tool cutoffs, process and thread terminal floors, original provider failures,
guarded recovery, exact owner registry, fractional checkpoint persistence,
child/collector/close ownership and actual entered serialization. Parent and
supervisor capture-error causes remain separate from provider details and are
frozen in settlement evidence. This is current local integration evidence;
installed-candidate and native Windows acceptance remain required.

The managed Inbox now retries only BEGIN admission within its original .1-second
connection/operation cutoff. Its original clock/savepoint protocol and receipt
leases remain intact, and neither the body nor COMMIT is replayed. Independent
source review found no blocker. Two focused cases passed in 11.221 seconds
(`/tmp/sdk-managed-inbox-original-window-focused2-310.log`). Actual held-writer
evidence (`/tmp/sdk-managed-stalls-7ffjcj6b/managed-inbox-original-admission.json`)
records the previous single-attempt BUSY, six BEGIN attempts with a .04-second
writer release and exactly one mutation, and .100428 seconds of admission while
the writer stays held with the exact original receipt unchanged. The original
timeout scenario also encountered real participating main-database contention
and completed notification retry to dead with one native invocation and unchanged
command/Run cutoffs
(`/tmp/sdk-managed-stalls-gji2ovbg/original-timeout-terminal.json`). Its SQL trace
is a bounded ring, and native worker SQL is explicitly unavailable. Complete
current 22-case managed and installed-candidate acceptance remains pending.

The complete frozen current managed suite then passed all 22 cases in 82.470
seconds (`/tmp/sdk-managed-supervisor-full22-inbox-frozen310.log`, compressed
snapshot `/tmp/sdk-managed-supervisor-full22-inbox-frozen310-summary.json`). It
covers the original source/notice bounds, actual native memory denial, separate
capacity, factual collector/clock cleanup, original timeout receipt replay,
result restart without business replay, rejected executor dispatch and bounded
status. The current candidate-wide Python 3.10 source/rebuilt-installed run is
now in progress (`/tmp/sdk-a05-a12-current-candidate-full310.log`, acceptance
directory `/tmp/sdk-a05-a12-current-candidate310-evidence`). Its isolated suite
still uses the original 900-second cutoff. A05/A12 now have current local
integration passes; candidate-wide and native matrix completion remain pending.

That first candidate-wide run was interrupted by the primary with SIGINT
(exit 130) after eight child-fixture errors and one inherited guard assertion
failure. No complete source/installed pass is claimed. Host-namespace inspection
confirmed no remaining processes from that validation. A three-case causal
probe (`/tmp/sdk-current-child-fixture-causal310.log`, 10.996 seconds) retained
the exact errors: a completed child fixture used frozen raw wall time below
its actual logical start, and a preentry fixture supplied literal start 100
instead of the original child's actual claimed start. The fixture corrections
use original SDK timestamps and preserve fixed completion 102, original error,
all cutoffs and entry-state assertions. The inherited guard failure was not
reproduced by that probe or the full 18-case receipt module, which passed in
26.922 seconds (`/tmp/sdk-current-child-receipt-causal310.log`). Its historical
failure remains retained for the next complete candidate run; no widened
timing assertion or additional retry was added.

The timestamp fixture corrections passed eight of nine cases first; the
remaining no-DML assertion included the fixture's own live guarded budget
observation during setup, before the read-only delivery call. Aging now uses the
existing frozen native cutoff, with the real writer still held. The actual
delivery's no-BEGIN/no-DML, unchanged watermark, exact result and shared .1-second
read window assertions stay intact. Both complete fixture modules then passed
all nine in 3.473 seconds
(`/tmp/sdk-child-original-timestamp-readonly-fixtures9-310.log`). No SDK change
was needed for these fixture corrections. Source-wide regression is now run
before the separate rebuilt-wheel consumer, with every source case retained
and immediate failure reporting; both must pass on the same frozen source.

The first sequential source harness stopped after 52 cases on an invalid mixed
import setup (`/tmp/sdk-a05-a12-reviewed-source-full310.log`): the parent imported
new source through a local `sys.path` override, while its restart subprocess
imported an older wheel from the harness interpreter. The old child rejected the
new guard table before reaching its intended crash. This is not SDK acceptance
or an SDK schema regression. The current frozen wheel was built and installed
into `/tmp/sdk-a05-a12-current-installed310`; its actual SDK import is that
environment's `site-packages`. The unchanged real restart case then passed with
that installed candidate in 1.139 seconds
(`/tmp/sdk-current-installed-restart-original-path310.log`). Further source runs
use both the current installation and inherited source import configuration;
the separate rebuilt-installed run still strips source paths.

The public managed supervisor example also completed both actual business and
reserved handler execution
(`/tmp/sdk-managed-supervisor-public-example310.log`). A separate actual process
serialization witness passed in 3.003 seconds
(`/tmp/sdk-result-serialization-entered310.log`): its worker recorded entry into
the slow JSON serializer before the original one-second deadline stopped it,
confirmed cleanup, and prevented its delayed write. This new witness does not
alter or establish serializer entry for the original 20-millisecond fixture.

The current installed public supervisor example now holds the source execution
until the managed handler succeeds and its notice is consumed, then releases the
business task within the original eight-second caller window. Its previous fixed
three-second source lifetime failed with a checkpoint admission timeout; that
historical cause remains retained without claiming a proven lifetime attribution.
The corrected actual installed path passed
(`/tmp/sdk-current-installed-managed-example-release310.log`); its supervisor
reported 1.757 seconds remaining from the original two-second handler budget.
Optional evidence retains the actual SDK import, original cutoffs and source
snapshot before release. The rebuilt-wheel acceptance invokes this public example.

The coherent fail-fast source run stopped after 68 cases in 95.267 seconds
(`/tmp/sdk-a05-a12-coherent-source-full310.log`): one synthetic `_await` row lacked
the parent identity now required for exact budget-owner retention. The fixture
now supplies its actual Context and lease, preserving errors and assertions.
Its subsequent complete module exposed two actual native delayed-delivery
failures (`/tmp/sdk-child-completed-delivery-authority310.log`): the child result
committed before its original five-second cutoff, but the parent returned a
checkpoint admission timeout instead of that result. Original result and request
facts are retained in `/tmp/sdk-child-completed-delivery-evidence-228mlt_2`.
Bounded parent exception diagnostics were added without changing any deadline;
the first diagnostic native case passed in 13.376 seconds, so the precise
historical failing call remains unresolved. CI stays paused during diagnosis.

Independent review identified a concrete expired-delivery gap, reproduced with
actual guarded capture and a held SQLite writer. Error classification could
retry the pending checkpoint and throw before result proof. Classification now
projects only the retained elapsed floor; exact known-owner ACK and the existing
read-only result proof share one original .1-second factual window. No new sample
or business is admitted. Parent and child ancestry guards are checked before and
after the result read; foreign and uncaptured guards remain unresolved.
All four initial regressions failed before correction
(`/tmp/sdk-child-result-clock-proof-baseline2-310.log`), including actual unsafe
delivery past foreign or concurrently committed guards. The corrected integration
passed all 26 in 31.927 seconds
(`/tmp/sdk-child-result-clock-proof-integrated310.log`), retaining the original
no-BEGIN/no-DML delivery tests. A fifth actual uncaptured-owner case passed in
.794 seconds (`/tmp/sdk-child-result-uncaptured-original310.log`); ordinary close
also refuses this unresolved owner. Five public typing consumers passed.

The second coherent source run stopped after 93 cases in 119.459 seconds
(`/tmp/sdk-a05-a12-coherent-source-full310-v2.log`): cancellation committed and
the receipt reader returned revoked, but total elapsed .869090 exceeded the
unchanged .7-second assertion. Existing evidence did not distinguish cancellation
admission, reader return or scheduling. The fixture now records those phases,
raw errors and bounded SQL before assertions. All 18 original receipt cases
passed in the subsequent combined run
(`/tmp/sdk-child-clock-cleanup-receipt-original-bounds310.log`); the cancellation
record retains elapsed .199602 and committed cancellation
(`/tmp/sdk-child-clock-checkpoint-1ss260gj/evidence.json`). That combined run was
not a whole pass because its new uncaptured-owner fixture needed the specific
original Kernel timeout and explicit interrupted-fixture close handling; the
separate corrected fifth case passed as recorded above. Complete frozen source,
rebuilt installed and native matrix acceptance remain required.

The proof handler additionally retains the original exception when a successful
exact ACK consumes the shared factual window before the read can begin. This is
local proof classification, not broader business retry. Independent review found
no further blocker. Six clock-cleanup cases and six existing propagation cases
passed in 6.925 seconds
(`/tmp/sdk-child-result-clock-shared-proof-final310.log`), including actual ACK
followed by the same deadline's expiry, with no child read and the original
result unchanged. The corrected wheel was rebuilt and reinstalled into the same
current Python 3.10 environment before the next frozen source run
(`/tmp/sdk-a05-a12-clock-proof-source-full310.log`, artifacts
`/tmp/sdk-a05-a12-clock-proof-source310-evidence`). No complete pass is yet claimed.

That next complete source run stopped after 73 cases in 110.298 seconds on
the real held-writer child-result path
(`/tmp/sdk-a05-a12-clock-proof-source-full310.log`). The newly guarded reader
refused an unpublished sample, retaining the original BUSY. A controlled
different-live-owner witness then failed on the same structural omission
(`/tmp/sdk-child-result-other-live-owner-baseline310.log`): Context and child
wait helpers are distinct. Factual cleanup now visits only registered parent/
child owners, within the original proof deadline and with nonblocking owner
admission. Unknown or empty registry inspection skips that cleanup; unrelated
executions cannot spend its allowance.

Two intermediate integration failures are preserved in
`/tmp/sdk-child-result-targeted-owner-proof-integrated310.log`; the empty-registry
lock-timeout cause was corrected without broader retry. The later native stack
(`/tmp/sdk-child-completed-delivery-evidence-1nxaab3u/success/parent-exception.json`)
confirmed initial refusal of a sampling guard owned outside the reader's Kernel.
A controlled independent-Kernel live publisher also failed before correction
(`/tmp/sdk-child-result-foreign-live-owner-baseline310.log`). Initial proof
admission now waits only for the original owner's sampling ACK within the same
.1-second window, releasing the reader lock between fresh authority checks.
It never clears a foreign marker or retries the result read; final guards and
permanent/storage failures remain immediate. All nine new clock-cleanup cases
and original readonly/native-delivery/propagation cases passed, 28 in 35.127
seconds (`/tmp/sdk-child-result-live-owner-authority-integrated310.log`), including
the actual foreign owner's .03-second delayed publication. No complete source,
installed or native matrix pass is claimed yet; CI remains paused.

After independent final review and five public typing passes, the frozen
live-owner source was rebuilt and reinstalled before another complete source
run (`/tmp/sdk-a05-a12-live-owner-source-full310.log`, artifacts
`/tmp/sdk-a05-a12-live-owner-source310-evidence`). The actual installed import
is recorded in `/tmp/sdk-live-owner-installed-import310.json`. That source-wide
run stopped after 87 cases in 114.584 seconds: an old protocol-only inspection
fixture omitted the command and lease fields used by exact result admission.
The fixture now supplies its original synthetic identity; its three tests passed
in .436 seconds (`/tmp/sdk-child-inspection-protocol-fields310.log`). The separate
sdist/rebuilt-wheel consumer and full installed suite still retain their original
cutoffs and remain pending until source-wide success.

The earlier Windows 3.12 raw-script failure also exposed a concrete counter-loss
path: a script could save bytes before its worker's activity batch persisted.
A controlled reproduction now holds a real observation-journal writer through
the original two-second native timeout. It retained the exact 20-byte physical
log and `recovery_required` state, then failed with missing `stdout_bytes` while
artifact recovery was disabled (`/tmp/sdk-script-output-loss-held-writer-baseline310.log`,
4.305 seconds). Earlier stdin-based and cross-spawn mock attempts were invalid
test harnesses and do not establish SDK failures. The correction retains a
separate saved-byte fact after native containment, merges it as a maximum floor,
and retries its publication independently of business settlement. Historical
effect association must use immutable preparation events when the same effect
has been re-prepared after explicit not-applied recovery. No emission timestamps
or successful telemetry flush are invented. Final source, installed and native
Windows acceptance of this correction remains pending.

The history correction passed six real SQLite/file cases in 2.376 seconds
(`/tmp/sdk-script-output-recovery-history-focused310.log`), including supported
not-applied recovery and re-preparation of the same stable effect. A fresh
independent review confirmed that the original event association and close
ownership corrections resolve the reported blockers. The wheel was rebuilt and
installed, but the combined script run provides Linux source verification:
16 tests passed in 23.549 seconds (`/tmp/sdk-script-output-native-integrated310.log`).
The raw-timeout witness imported `/root/dispatcher-sdk/src/dispatcher_sdk/__init__.py`;
see `/tmp/sdk-script-raw-timeout-ac6h73a4/evidence.json`. Its held-writer
native witness returned `recovery_required`, preserved the physical 20 bytes,
recovered the count with unknown emission timestamps, and prevented the later
escape file under the unchanged two-second execution cutoff. The unavailable
activity-journal query also read the same persisted saved-byte receipt. A separate
real-storage revocation test passed in .546 seconds
(`/tmp/sdk-script-revocation-factual-settlement310.log`): busy receipt storage
retained the factual cleanup obligation and later publication issued no Kernel
result CAS or business write. A newly rebuilt final wheel then passed all five
public typing consumers, compilation/diff checks and 554 documentation links
plus six README examples using the current installed SDK. Its actual import is
recorded in `/tmp/sdk-script-output-final-installed-import310.json`.

The next complete run discovered one further child-inspection failure after 108
cases in 144.970 seconds (`/tmp/sdk-script-output-final-source-full310.log`,
retained stores `/tmp/sdk-script-output-final-source310-evidence`). Under persistent
receipt contention, terminal exception handling sampled the budget again, and
the fixture's diagnostic `remaining()` call retried that pending sample before
recording the original exception. Diagnostics now project the retained floor.
SDK retries retain the actual receipt BUSY across the original window, including
its original SQLite cause and any later transient control failure. Positive
admission still uses authoritative samples; known revocation and permanent
failures still propagate. The deterministic pre-fix terminal witness failed
(`/tmp/sdk-child-receipt-terminal-original-error-baseline310.log`), then all 31
receipt/inspection/clock-cleanup tests passed in 34.012 seconds
(`/tmp/sdk-child-receipt-terminal-original-error-integrated310-v2.log`). Independent
review found no remaining blocker in that correction.

A separate review confirmed that a valid execution ID over 1024 bytes could make
optional artifact identity construction reject an already-observed native outcome.
The marker now degrades to an explicit unknown observation identity and retains
the real cleanup confirmation. No business identifier limit was introduced.
The newly rebuilt wheel passed the actual native long-ID success case and the
original persistent-contention case together in 1.746 seconds
(`/tmp/sdk-receipt-cause-long-identity-current-native310.log`). The complete source
and separate installed-consumer regressions remain pending.

The following full run stopped at 101 cases in 130.221 seconds
(`/tmp/sdk-receipt-cause-final-source-full310.log`, retained stores
`/tmp/sdk-receipt-cause-final-source310-evidence`). An inherited fresh-recovery
case did not report its unresolved sampling guard. Its single-case diagnostic
rerun passed in 10.334 seconds, so the original artifact alone cannot establish
whether the guard was checked before the stored work window expired. Independent
source review found a deterministic classification hole: initial construction of
an already-expired window returned trusted zero without checking a foreign
durable guard. It admitted no business, but hid unresolved clock authority.

A new actual-storage witness deliberately ages the same original .3-second tool
constraint after a failed sampling ACK. It failed before the correction in .644
seconds (`/tmp/sdk-child-expired-fresh-guard-baseline310.log`). Expired initial
construction now performs one bounded readonly ancestry check; no new wall
sample, ACK, drain, write or budget extension occurs, and later projections
remain free of I/O. All 41 clock/receipt/inspection/cleanup cases passed in 51.741
seconds (`/tmp/sdk-child-expired-fresh-guard-integrated310.log`), with original
guard assertions unchanged. Fresh independent review found no remaining blocker
in this fix. Complete current-source and installed-consumer acceptance is pending.

A05, A12, installed-candidate regression and native Windows matrix acceptance
remain incomplete. Historical successes below do not override these failures.

Earlier candidate `12771d9ea00fcd58f4948d58f12c4aa903be8f12` failed all
16 environments in [run 37200662333](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37200662333);
history scanning passed. Every outer suite ran 975 cases and each installed suite
970, retaining the original 900-second installed-suite deadline. A shared stale
cancellation test expected a persisted failure receipt after raised control errors
had deliberately moved to bounded local diagnostics. Its revised assertion checks
the original CAS error, unchanged authority, durable original request and separate
nonpersistent failure facts. No successful matrix is claimed for this candidate.

Eight Windows environments retained 40 installed public scenarios, 32 actual
post-close SQLite rename-and-restore round trips, 16 actual launcher/worker final-flush and
PID checks, and 16 `pythonw` cases. They do not override other failures. Raw inventory
and retained native data are `/tmp/sdk-ci-audit-summary-37200662333.json` and
`/tmp/sdk-ci-audit-evidence-37200662333`. Typing passed everywhere; docs/examples
were skipped after test failures, so those steps are not fresh CI passes.

Native ARM traces also retained unrelated fixture seeding writes spending .031s
in `PRAGMA synchronous=2`, exhausting the original .03s admission window before
BEGIN. Read-only aggregation fixtures now seed their known rows with test-owned
SQLite, while actual SDK bind/write/contention validation retains its original
budgets. Unattributed Host stop/notification and entry failures now retain their
original checkpoints and cleanup errors. The receipt caller's original .3s window
and .6s elapsed assertion remain; SQL, actual sleep and thread CPU timing were added
to explain the retained native 1.839s return rather than widening its bound.

Current local corrections passed 148 tests in 137.034s
(`/tmp/sdk-goal-scope-corrections-integrated.log`). This covers public typed
`ExecutionActivity`/`ChildCalls`, explicit unavailable-child errors, real missing
module import, and public parent/child success/failure with a retained 16 MiB
buffer, actual RSS readings and capacity two. These new mandatory witnesses still
require the fresh native matrix. Explicit copy upgrade additionally preserved a
real pending original result in its original external journal, then recovered it
without invoking business again; the destination remained inactive and unchanged
(`/tmp/sdk-copy-upgrade-preservation310-final.log`). Migration checks compare
actual schema and rows instead of running the old SHA fixture. Independent
read-only review found no blocker. The corrected wheel passed all five public
scenarios and the original example with Python 3.10 isolated imports outside the
checkout (`/tmp/sdk-scope-final-public310-evidence/summary.json`,
`/tmp/sdk-scope-final-public310.log`, `/tmp/sdk-scope-final-example310.log`). Actual
import is `/tmp/sdk-scope-final-installed310/lib/python3.10/site-packages/dispatcher_sdk/__init__.py`.
Five public typing fixtures, 550 documentation links/six README examples and 26
upgrade/settlement/packaging checks passed (`/tmp/sdk-scope-final-types.log`,
`/tmp/sdk-scope-final-docs.log`, `/tmp/sdk-scope-final-upgrades312.log`).
Corrected implementation candidate `6d3239f8fe63e7cd0bf675deea0cd1820aec6c9b`
was pushed and [run 37203657162](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37203657162)
started and completed all 16 environments: 11 passed and five Windows
environments failed. History scanning passed. All eight Linux environments
completed successfully: each ran 979
tests with exactly 17 Windows-only skips, five typing fixtures, 551 documentation
links/six README examples without skips, and both example steps. Actual installed
Python 3.10 x64/ARM64 suites ran 974 tests under their original 900-second deadline
and passed five public scenarios from site-packages; raw logs and artifacts are
under `/tmp/sdk-ci-audit-evidence-37203657162`. Windows x64 Python 3.10/3.11/3.13
passed; x64 3.12 and all four ARM-host environments failed. Every installed suite
ran 974 tests under its original 900-second deadline; 13 passed, three failed and
none timed out. Typing passed in all 16 environments; docs/examples passed in
11 and were skipped after failures in five. Windows README checks ran four
applicable examples and skipped the two POSIX-only examples. No applicable
mandatory native case was skipped. Final raw inventory is
`/tmp/sdk-ci-audit-summary-37203657162.json`, with complete errors at
`/tmp/sdk-ci-audit-failures-37203657162.json`. No successful matrix, release or
merge is claimed.

The current failures retain distinct facts. Physical script output was exactly
20 bytes before its observation lacked `stdout_bytes`; that older fixture
deleted its store, so the missing metric's cause remains unknown. The fixture
now retains raw output, observation, SQL and separate cleanup errors without
changing its 2-second deadline. Two inherited-deadline witnesses returned
`running` after bounded lifecycle-lock settlement admission; both native
process outcomes were timeout, both containers were empty and the exact
parent timeout result remained durably pending. The fixture is being corrected
to verify that documented deferred settlement within its existing maintenance
window. Two wait-classification fixtures assumed immediate policy activation;
retained ARM3.11 facts show Kernel selection committed but the sidecar transaction
spent .031s in its .03s window and rolled back to `registering_policy`. Those
classification checks now use the actual claimed identity; policy activation
and recovery retain their separate integration coverage. Native pressure marker
reads also raised an access PermissionError; bounded retries retain the unknown
access/sharing facts inside the existing stage deadline. Finally, an independent
child-clock checkpoint note exhausted its original .1s operation budget before
COMMIT. Its precise native SQL-stage cause remains unknown. A separate real
dual-writer probe confirmed a recovery defect: both sidecar checkpoint paths
failed with original `SettlementBusyError`/`SQLITE_BUSY`, leaving the request
budget unchanged and no independent note. After wall-clock rollback, a fresh
ChildService restored 9.786 seconds against the original window's 6.087 seconds;
actual `Runtime.submit_child` admitted the child as queued. The probe stopped
before business and cancelled that admission. Raw evidence and its exact chained
error are `/tmp/sdk-a05-floor-loss-tdrj4k5y/evidence.json`; the script is
`/tmp/sdk_a05_checkpoint_floor_probe.py`. This probe failed during settlement
writer initialization, not the native pre-COMMIT note-expiry stage. It establishes
A05 as incomplete, without attributing that older native failure's precise cause.
The defect is not fixed: an in-memory floor cannot prove recovery after a crash,
and persisting only to Kernel would not cover simultaneous failure of all stores.

A separate, reproduced inheritance defect was found in `_bind_child_limits`:
new submission and queued submission/adoption replay replaced a stronger incoming
checkpoint with the weaker canonical parent/old-child checkpoint. Two real-SQLite
tests failed on all three paths, losing approximately 3.55–3.61 seconds of floor
(`/tmp/sdk-incoming-child-floor-baseline310.log`, with retained databases and
supplied/bound envelopes). The local correction retains the strongest checkpoint
after all inputs are advanced to the same clock sample. Parent constraints and
storage, child/tool constraints, entry metadata and ownership semantics remain
unchanged. Replaying an older envelope cannot weaken the retained floor.
Independent review found no blocker. Six checkpoint tests passed in 7.684 seconds
(`/tmp/sdk-incoming-child-floor-final310.log`); 37 budget, capacity and native
parent-floor integration tests passed in 16.441 seconds
(`/tmp/sdk-incoming-child-floor-integration310.log`). An earlier corrected run's
only failure was one ULP of epoch-float projection rounding; its raw log remains
`/tmp/sdk-incoming-child-floor-corrected310.log`. The comparison now allows four
ULPs of numeric rounding, about .954 microseconds at the captured epoch, without
changing any production cutoff or work window. This fix does not resolve the
separate failed-persistence recovery defect.

The first complete regression process disappeared without an exit receipt or
unittest summary; its log ends during receipt contention. No test discovery or
multiprocessing worker remained in the same host boot/PID namespace. The cause
is unknown and no pass is claimed (`/tmp/sdk-incoming-floor-full310.log`,
`/tmp/sdk-incoming-floor-full310-interrupted.json`). Initial default-sandbox
`/proc` inspection was insufficient to establish host process absence; subsequent
read-only inspection in host PID namespace `pid:[4026531836]` confirmed that only
the new supervised regression remained, with no original discovery process.
A supervised full regression
was then started as `sdk-incoming-floor-regression-20261005.service`, with no
automatic retry, the existing CI 45-minute overall limit and the unchanged
900-second installed-suite limit. After the launch command exited, service
state was `active/running`, supervisor PID 2092693 and test PID 2092694. Its
current execution/exit record is `/tmp/sdk-incoming-floor-supervised310.json`,
log `/tmp/sdk-incoming-floor-supervised310.log` and retained raw evidence
`/tmp/sdk-incoming-floor-supervised310-evidence`. This is started, not verified
complete; final source and fresh installed results still require inspection.
Its fresh wheel passed all five public consumer scenarios, with actual import
`/tmp/tmpcvkcvpt3/venv/lib/python3.10/site-packages/dispatcher_sdk/__init__.py`
(`/tmp/sdk-incoming-floor-supervised310-evidence/sdk-observability-consumer-l7sfp2b5/summary.json`
and `environment.json`). The complete installed suite is still running under
its original 900-second bound. The outer log has already marked
`test_child_wait_preserves_busy_error_without_revoking_parent` as ERROR; final
traceback and causal attribution remain pending. These facts do not establish
a successful complete regression or installed suite.

The diagnostic/classification corrections passed 18 focused source tests in
22.168 seconds (`/tmp/sdk-ci-native-corrections-integrated310.log`), and three
native Linux pressure cases passed in 25.773 seconds
(`/tmp/sdk-ci-native-pressure-corrections310.log`). These runs used `PYTHONPATH=src`
with `/tmp/sdk-scope-final-installed310/bin/python`, so they are source verification,
not fresh installed or Windows acceptance. A causally corrected real-lock probe
returned the actual original `running` snapshot, then recovered the exact parent
and child timeout results in .127 seconds of its single three-second maintenance
window (`/tmp/sdk-inherited-parent-deferred-maintenance-corrected-probe/probe-result.json`).
Automatic SDK maintenance completed before the first explicit observe; this
does not prove that the probe required an explicit `recover_completions` call.
The earlier failed probe remains at
`/tmp/sdk-inherited-parent-deferred-maintenance-probe/probe-result.json`; it held
the lock through a later unconditional cleanup acquisition and incorrectly
required a timeout child winner rather than the original allowed cancellation
winner with an exact superseded timeout receipt. Independent review of the new
fixtures identified cleanup and unbounded-read issues. Those corrections now
passed independent review: all canonical/limits/winner reads share the original
three-second control window, and primary failures survive diagnostic and Runtime
cleanup errors. The corrected inherited-deadline method passed once in 9.488
seconds (`/tmp/sdk-inherited-parent-maintenance-bound310.log`,
`/tmp/sdk-inherited-parent-deadline-v4ldu7a_/evidence.json`); its caller spent
6.233 seconds of the original 12-second bound, exact settlement proof .054
seconds of the original three-second window, and two real containment receipts
confirmed stopped process trees. This ordinary run returned `timed_out` already,
so it does not exercise an explicit recovery iteration. The corrected
checkpoint writer cleanup also passed once in 1.216 seconds
(`/tmp/sdk-child-clock-checkpoint-cleanup310.log`,
`/tmp/sdk-child-clock-checkpoint-yjjy57pg/evidence.json`); independent review found
no remaining cleanup blocker. Documentation checked 551 local links and all six
README examples (`/tmp/sdk-ci-native-corrections-docs.log`). Production SDK source
remains unchanged by these diagnostic and fixture corrections; the confirmed
A05 defect and missing A12 path are not counted as fixed.

Final focused source commands (these do not establish installed/native Windows
acceptance):

```bash
PYTHONPATH=src:. /tmp/sdk-journal-admission-installed310/bin/python -m unittest tests.test_runtime_deadline_envelopes.RuntimeDeadlineEnvelopeTests.test_real_child_stops_at_inherited_parent_deadline -v
PYTHONPATH=src /tmp/sdk-scope-final-installed310/bin/python -m unittest tests.test_child_clock_checkpoint.ChildClockCheckpointTests.test_locked_observation_writer_preserves_floor_in_independent_note_after_reopen -v
/tmp/sdk-scope-final-installed310/bin/python scripts/check_docs.py
```

A fresh requirement-by-requirement audit found a separate A12 implementation
gap: `subscribe_stalls` currently supports a fixed synchronous callback only.
This proves callback isolation, not managed supervisor-agent execution with
independently reserved capacity, memory/budget admission and a visible shortage
outcome. The full Goal retains that requirement. Its public execution contract
is being clarified before implementation; even a green current matrix will not
close T06/T07/T09 or G1/G2/G5 while that path and its real-process witness are
missing.

### Local observation cost measurement

The fixed offline experiment in [benchmark_observability.py](../scripts/benchmark_observability.py)
completed exactly three interleaved fresh-store trials of four tasks per arm,
using process isolation, FULL durability, default observation settings and the
same workload/original 30-second work and wait windows. All 36 tasks and their
callbacks succeeded; no arm was retried. Installed Python 3.10 paths, commands,
execution IDs, original errors and bounded per-process SQL counters are retained
in `/tmp/sdk-observability-overhead-scope-final.json` and its adjacent directory.

| Arm | Tasks/s | Median wait, s | Median handler, s | SQL mutation attempts | COMMIT attempts | Post-close database bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Historical dev0 | 0.915 | 2.754 | 0.105 | 3,890 | 572 | 1,896,448 |
| Current automatic observation | 0.462 | 5.391 | 0.105 | 5,697 | 1,868 | 3,260,416 |
| Current plus public reports | 0.332 | 8.052 | 0.336 | 6,495 | 2,213 | 3,883,008 |

The historical comparison also includes other SDK changes; it does not isolate
automatic observation overhead. Extra public reports reduced current throughput
by about 28% in this small traced workload. SQL counts include attempts, retries
and SQLite trigger callbacks, not successful physical writes or fsyncs; database
bytes are totals across three stores. All actual handler PIDs had retained traces.
Both current arms returned 12 complete observations, 12 persisted final flushes,
zero collection gaps and zero dropped events. Public progress returned 45 confirmed
and three unknown receipts retaining genuine SQLite contention; no report was
resent to turn unknown into success. Nearest-rank p95 is only the maximum of 12
task samples. This is local cost evidence, not native Windows acceptance or a
production capacity prediction. The earlier partial-counter experiment remains
retained at `/tmp/sdk-observability-overhead-12771d9.json`; it is not substituted
for this corrected complete measurement.

An earlier complete local Linux acceptance passed on implementation commit
`969f0da7f2bdbcda9dc4235e0744e0176e0475b2` (Linux x86_64, Python 3.12).
The complete regression ran 952 tests in 1629.062 seconds with zero failures or
errors and 16 platform skips. Its freshly rebuilt and installed SDK also passed
the complete isolated suite and all five public end-to-end scenarios. The original
portable example also passed in a separate fresh installation with isolated
imports outside the checkout. Five public typing fixtures passed. The latest documentation check passed 546 local links
and six README examples with no skips.

The Goal is not complete: native Windows and the existing 16-environment CI
matrix have not passed for the current implementation. The 16 Linux skips do not count as
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

CI then exposed new platform issues. Both Linux Python 3.13 installed suites
captured unrelated descriptor closures through a globally patched `os.close`.
Windows suites exposed unclosed test-owned SQLite connections, POSIX-only mocked
signal attributes, coarse-clock assumptions and atomic snapshot reader sharing.
These fixture corrections preserve their original deadlines and required cases.
Raw task logs are retained as `/tmp/sdk-ci-job-<job-id>.log`; the parsed inventory
is `/tmp/sdk-ci-all-failures.json`, with native artifacts under
`/tmp/sdk-ci-evidence-37189113536`. The old failed runs remain failed.

Three additional SDK corrections are required before final acceptance:

- Native Windows venv launchers can have a different PID from the actual
  interpreter. Descendant cleanup killed that interpreter before its final
  activity flush. Its Job-verified acquired handle is now preserved while live;
  recycled PIDs are not protected. Internal startup-cap expiry is also distinct
  from inherited work expiry, including readiness/cancellation races.
- Elapsed projection now subtracts elapsed samples before adding the wall floor.
  The previous operation order reduced `105` to `104.99999999999994` on unchanged
  samples, weakening an already retained floor. No assertion tolerance was added.
- Read admission leaves SQLite busy waiting disabled and uses the existing
  Python loop within the same original query budget. A genuine locked-database
  VFS slow-sleep probe reproduced about 0.401 seconds for the original 0.08-second
  query; revised admission took about 0.080 seconds and passed the original
  0.2-second gate. Permanent SQL errors still propagate immediately.

Focused checks and independent Windows control review passed locally. Integrated
correction regression passed 266 tests in 219.563 seconds with 17 native Windows
skips; raw log is `/tmp/sdk-ci-corrections-integrated.log`, with retained evidence
at `/tmp/sdk-ci-corrections-integrated-evidence`. Five public typing fixtures and
546 documentation links/six README examples passed (`/tmp/sdk-ci-corrections-types.log`,
`/tmp/sdk-ci-corrections-docs.log`). The fresh complete candidate matrix is still required. The earlier
`969f0da` complete pass does not establish acceptance of these corrections.
The Windows 3.12 stall collection-gap failure remains unattributed because its
temporary store was deleted. This suite now retains its databases, policy/window
rows, source summaries and flush receipts. One unchanged scenario passed locally;
that does not explain the historical failure. Worker expiry fixtures now use a
caller-provided wall sample scoped to the actual handler, retaining real
`context.budget` and original watchdog cutoffs; they no longer rely on deleting
or replacing a shared Windows clock file or writing evidence after hard stop.

Corrected implementation `21218650d0ff8f41cdc9b9f1fd9fc21854c071ff` was pushed and
launched [run 37190938130](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37190938130).
It is not yet matrix acceptance. A fresh Linux wheel built from that commit
passed all five independent public scenarios and the original public example,
outside the checkout with isolated imports. Evidence:
`/tmp/sdk-ci-corrections-public-evidence/summary.json`,
`/tmp/sdk-ci-corrections-public.log`, `/tmp/sdk-ci-corrections-example.log` and
`/tmp/sdk-ci-corrections-import.json`. Import source is
`/tmp/sdk-ci-corrections-installed/lib/python3.12/site-packages/dispatcher_sdk/__init__.py`.
The first local wheel command failed only because pip attempted to write its
cache outside the writable workspace; the no-cache build succeeded. Logs are
`/tmp/sdk-ci-corrections-wheel.log` and `/tmp/sdk-ci-corrections-wheel-no-cache.log`.

That matrix passed six Linux environments (Python 3.11–3.13 on x64 and ARM64),
but failed native Windows and did not establish Python 3.10 acceptance. Four
Python 3.10 jobs in the earlier run exhausted their original 45-minute limit
after reporting hundreds of SQL authorization failures; the complete test
summary followed by a stuck process is not a pass. A real Python 3.10.22
reproduction confirmed `set_authorizer(None)` causes `DatabaseError: not authorized`;
Python only supports disabling that callback with `None` from 3.11 onward.
Control admission now temporarily allows only the internal `busy_timeout` pragma
through a callable, preserving other authority restrictions and lock restoration.

Additional current corrections address native busy-handler elapsed overshoot
and observation-worker storage ownership. A genuine SQLite VFS sleep probe
reproduced a 0.2-second cancellation admission taking 1.047 seconds, exceeding
its original 0.6-second gate. Immediate SQLite admission plus Python retries
stays inside the same original deadline; a delayed successful `BEGIN` is checked
again before any clock or business writes. `/tmp/sdk-kernel-busy-baseline.log`,
`/tmp/sdk-kernel-busy-revised.log` and independent review logs retain raw results.
The Windows snapshot failures were fixture producer `PermissionError`s at
`local.json` replacement, not proof of delayed telemetry. Dynamic fixture
snapshots now publish independent immutable generations; original readiness,
execution and stop bounds remain unchanged. `/tmp/sdk-pressure-producer-errors.json`
retains the failed worker results. Native acceptance of these corrections remains
required; earlier green jobs cannot establish the next candidate's acceptance.

The current storage-lifetime correction retains stopped collectors, initializing
handler observation contexts, the stall sampler and the settlement worker until
they release SDK storage. All share one existing one-second cleanup window.
An unfinished worker preserves temporary storage and reports pending cleanup;
repeated close advances ownership cleanup without replaying business or changing
the original flush receipt. Actual held-connection, startup, late-handler and
concurrent-close probes and 17 independently reviewed focused tests passed.
Evidence: `/tmp/sdk-observation-cleanup-final-review.log`,
`/tmp/sdk-context-startup-fixed-review.log`,
`/tmp/sdk-service-storage-fixed-review.log` and
`/tmp/sdk-observation-concurrent-close-review.log`.

Python 3.10 also lacks SQLite result-code attributes. One dependency-free shared
classifier now recognizes only actual BUSY/LOCKED codes or, when codes are absent,
the exact SQLite lock messages. Retry policies and deadlines remain with each
caller. Real Python 3.10 focused control, persistence and child tests passed
(35 tests), and independent seven-case classification plus isolated wheel imports
passed. A fresh installed Python 3.10 wheel passed all five public scenarios and
the original portable example. These are intermediate checks, not final matrix
acceptance. Logs are `/tmp/sdk-shared-contention-policy-python310.log`,
`/tmp/sdk-contention-classifier-independent310.log`,
`/tmp/sdk-contention-classifier-isolated-wheel310.log` and
`/tmp/sdk-platform-lifetime-public310.log`.

The intermediate installed full regression ran 967 tests in 792.393 seconds
and failed with two failures, one error and 17 native Windows skips. It exposed
an obsolete test observer without stop events, an exact packaging allowlist
missing the shared module, and a diagnostic fixture reading an absent Python
3.10 SQLite code attribute before publishing its contention witness.
All three fixtures were corrected; five focused checks passed with their original
bounds unchanged (`/tmp/sdk-contention-packaging-fixture-python310.log`). The
intermediate full log remains `/tmp/sdk-platform-lifetime-installed310-regression.log`.
A freshly rebuilt candidate must still pass every required matrix environment.

Frozen candidate `5c5746f4f0e17e383788b79a33187c7d2df72087` completed
[run 37194290510](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37194290510)
with all eight Linux jobs passed, native Windows ARM64 3.11/3.12 passed,
and six other Windows jobs failed. History scanning passed. Every Linux outer
suite ran 969 cases with exactly 17 Windows-only skips; both audited Python 3.10
installed suites ran 964 cases with the same 17 skips, return code zero and their
original 900-second limit. Types, documentation and examples passed in all eight
Linux jobs. Native Windows ARM64 3.12 outer/installed suites passed with 55
POSIX/Linux or platform-specific inapplicable skips; all mandatory native Windows
cases actually ran, including `pythonw`. Its five installed public scenarios and
four actual post-close database-release probes passed. These partial passes do
not establish complete matrix acceptance.

The final local installed Python 3.10 regression for that frozen source passed
967 cases in 756.565 seconds with 17 Windows-only skips. The local harness excluded
only two isolated-consumer methods and included all three packaging methods;
CI separately passed the complete source rebuild and isolated installation.
The original local log's prose label incorrectly described five excluded cases.
Actual filtering, the exact preserved harness and the clarification are retained
at `/tmp/sdk-platform-lifetime-final-installed310-harness.py` and
`/tmp/sdk-platform-lifetime-final-installed310-scope.json`; historical logs are
unchanged. Final wheel public scenarios and the original example passed outside
the checkout with isolated imports. Logs and evidence are
`/tmp/sdk-platform-lifetime-final-installed310-regression.log`,
`/tmp/sdk-platform-lifetime-final-public310-evidence/summary.json`,
`/tmp/sdk-platform-lifetime-final-public310.log` and
`/tmp/sdk-platform-lifetime-final-example310.log`.

Failed native logs and artifacts remain under `/tmp/sdk-ci-audit-job-<job-id>.log`
and `/tmp/sdk-ci-audit-evidence-37194290510`. Failure categories include cancellation
fixture clock anchoring, child read-delay and readiness fixtures, handler outcome
admission/settlement waits, observation initialization, and temporary venv image
deletion. The ARM-host Python 3.10 worker-preservation/flush assertions passed
before its test-owned image deletion failed; the file lock's owner is unknown.
The current fixture retains that environment and explicitly observes the host,
launcher and worker after return. It does not claim the image lock was released.
Actual SDK-owned database-release requirements remain independently tested.
A genuine SQLite VFS locked-sidecar reproduction separately confirmed settlement
admission with a 0.1-second budget taking 0.741 seconds in the native busy handler.
That defect is distinct from the still-unattributed uncontended write latency.
New corrections must pass a fresh complete matrix. Old failed jobs remain failed.

The scoped journal correction disables native busy sleeps and retries only
admission/configuration/validation or a genuine busy COMMIT with its original
transaction still open, against the same original deadline. Transaction bodies
are not replayed. Original vs corrected real VFS probes took 0.741/0.100 seconds
for settlement and 0.742/0.100 seconds for observations, keeping each original
0.1-second budget, 0.5-second gate and raw lock error. An actual observation
transaction held 0.06 seconds inside its original 0.03-second window committed
under the old code; the corrected code confirmed rollback and no row. Only that
proved attempt expiry is eligible for bounded final-batch or child-bookkeeping
retry. Native late successful durability commits preserve their receipt, and
unknown commits are never replayed. Evidence:
`/tmp/sdk-settlement-busy-native-baseline.log`,
`/tmp/sdk-settlement-busy-native-revised.log`,
`/tmp/sdk-observation-write-native-baseline.log` and
`/tmp/sdk-observation-write-native-revised.log`.

The related focused storage/persistence suite passed 113 tests in 93.801 seconds
(`/tmp/sdk-final-storage-persistence-focused.log`). The final observation module
passed 30 tests, and five real Python 3.10 rollback/lock regressions passed.
Permanent real-SQL tests protect expired rollback, exact final-batch replay and
one durable child-bookkeeping row within unchanged original constraints.
Actual COMMIT probes retained one body INSERT across two genuine busy COMMIT
attempts; uncertain and permanent failures each made only one COMMIT attempt.
Logs: `/tmp/sdk-final-storage-new-regressions.log`,
`/tmp/sdk-final-storage-python310-regressions.log` and
`/tmp/sdk-final-storage-commit-probe.log`. Four packaging/import checks,
five public typing fixtures and the documentation check (546 links, six README
examples, zero skips) passed. A fresh corrected Python 3.10 installation also
passed all five public scenarios and the original example, outside the checkout
with isolated imports (`/tmp/sdk-journal-admission-public310.log`,
`/tmp/sdk-journal-admission-public310-evidence/summary.json` and
`/tmp/sdk-journal-admission-example310.log`). Independent review found no remaining
scoped blocker; the next complete matrix remains required.

Candidate `c152c07ca366a58d51b0e8adfc129a9cdc5b99ae` completed
[run 37197108556](https://github.com/FlightDan/dispatcher-sdk/actions/runs/37197108556):
all eight Linux environments and native Windows ARM64 Python 3.12 passed;
seven Windows environments failed. History scanning passed separately. Outer
suites ran 972 cases and installed suites 967, with their original 900-second
installed-suite timeout. The Linux suites retained exactly 17 Windows-only skips;
Windows retained 55 inapplicable skips without skipping mandatory native cases.
All eight Windows environments passed five installed public scenarios and four
actual post-close SDK database-release probes. Actual venv launcher/worker and
`pythonw` cases ran on every Windows environment. This is partial evidence,
not acceptance of the full matrix. Raw inventories and evidence are retained at
`/tmp/sdk-ci-audit-summary-37197108556.json`,
`/tmp/sdk-ci-audit-windows-37197108556.json` and
`/tmp/sdk-ci-audit-evidence-37197108556`.

The failures include inherited-parent child readiness/terminal publication,
observation initialization and final source-close timing, a missing active policy
projection, handler completion timing, sandbox deferred completion/readiness,
and cancellation/child receipt elapsed bounds. Historical temporary databases
were deleted in several cases, so those exact native causes remain unknown.
Affected fixtures now retain original SQLite operations, worker stacks, process
entry/cleanup events and settlement facts, including failure paths. Required
deadlines and authority assertions are unchanged. A child-receipt fixture now
checks the actual RetryWindow used by the operation rather than a separately
constructed timer with a different coarse-clock projection.

A real busy-Kernel cancellation probe separately confirmed four synchronous
diagnostic writes after the original 0.2-second control deadline, increasing
caller return to 0.321 seconds. Raised control operations now capture bounded
local facts without fresh diagnostic write windows, preserve the exact original
exception and leave authority unknown even if a commit preceded the exception.
Fifteen real Python 3.10 cancellation tests passed in 9.260 seconds, including
real commit-then-error, no diagnostic SQL, bounded loss, historical filters and
restart-locality. Logs are `/tmp/sdk-cancel-original-deadline-trace.py`,
`/tmp/sdk-cancel-original-deadline-trace-x_942qqt/cancel-return.json` and
`/tmp/sdk-local-cancel-new-contracts310.log`. This does not explain every native
elapsed failure or establish the next candidate's matrix acceptance.

A real final-batch/sidecar-writer probe confirmed that a bounded recorder close
can persist its final batch while source close remains pending. The close fixture
now distinguishes nominal completion from that pending receipt and separately
checks ownership drain after releasing the writer; it never renews the original
close deadline or upgrades a degraded receipt. Evidence is
`/tmp/sdk-recorder-close-lock-window-evidence.json`. A new evidence-only Kernel
connection tracer also exposed a local fixture deadlock: copying events under
its lock triggered a connection destructor which reentered that lock. Its
snapshot now permits reentry and copies outside the lock. The interrupted local
probe remains failed, with its causal stack retained at
`/tmp/sdk-admission-cleanup-stack-probe.log`.

The corrected integrated control/Host, persistence, deadline and sandbox suite
passed 166 tests in 129.039 seconds (`/tmp/sdk-next-corrections-integrated.log`).
Five public typing fixtures and the documentation check passed 550 links and
six README examples without skips (`/tmp/sdk-next-corrections-types.log`,
`/tmp/sdk-next-corrections-docs.log`). Independent review found no remaining
source blocker, including original deadlines, raw-error identity, maintenance
participation and startup dispatch ownership. Native Windows acceptance of this
new candidate remains required.

Both READMEs now explain the existing Apache 2.0 license and link LICENSE and
NOTICE. Packaging retains both files. The dedicated README check passed 550
local links and six examples without skips; `/tmp/sdk-readme-license-docs.log`
records this documentation-only change.

The following task and gate snapshot is historical. The current implementation
and running candidate checks are recorded in **Current status, 2026-10-06** above.
At this earlier point, T01–T07 had implementation and Linux evidence, but
T01/T06/T07 still required the supervisor-agent contract and A12 path. T08 had
local installation and regression evidence but still needed the native matrix.
T09 had independent corrective reviews; its final closure also required the new
A12 path and T08 acceptance.

| Completion condition | Status at that earlier snapshot |
| --- | --- |
| G1 All mandatory scenarios | Incomplete: latest complete source run has one failure and two errors; corrected source, independently rebuilt installed candidate and native Windows/CI pending |
| G2 Installed public API, types, docs and examples | Five current public typing fixtures passed; complete freshly rebuilt installed API/example witness remains pending |
| G3 Same candidate across required platforms | Pending Windows and CI for this implementation |
| G4 Compatibility and explicit storage upgrade | Linux regression passed; native matrix still required |
| G5 Ownership and maintainability review | Managed admission/ownership implemented and independently reviewed; current corrective completion-clock integration/review remains open |

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

## Historical 0.7.1 candidate and reproducible commands

The source version is `0.7.1`. Final evidence must identify the Git commit,
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
are also required. The latter now runs all four remaining README examples on
Linux; the standalone script-notification example remains a separate CI step.

## Scenario mapping and historical baseline

The table retains the `969f0da` baseline and subsequent intermediate findings;
it does not establish acceptance of the current working tree. Raw
host paths identify retained artifacts for this run; they are not portable
links or substitutes for the candidate CI artifacts.
All Linux-applicable witnesses below passed in the complete source and installed
`969f0da` regression. Subsequent platform corrections described above still need
candidate regression and native matrix verification, including cases skipped on
Linux.

Current updates to that baseline:

- A05: five confirmed-clock and guarded-crash recovery cases passed locally.
  Original-budget, rollback and unknown-clock protection still require the
  current complete installed suite and native matrix; the five public scenarios
  alone do not close A05.
- A12: all 22 managed cases passed in the latest 78-case integration run, including
  the original two-notice readiness case after BEGIN-admission correction. The
  current installed managed example passed. Complete installed/native acceptance
  remains pending; earlier readiness failures remain in the evidence above.
- A15/A16: the current `ikx4xdy0` rebuilt installation passed all five public
  scenarios, including raw child/tool failure, conditional cancellation and
  cleanup across controller restart without business replay. Actual imports and
  receipts are linked by the current status section. The same wheel passed all
  five public type consumers and six README examples outside the checkout.
- A18: the latest installed suite timed out at its original 900-second limit
  with one recorded failure. Previous complete passes and the cancelled CI run do not
  establish current matrix acceptance.

Independent reviews have covered guarded budget ownership, completion-reader
lifetime, managed admission and capacity, cancellation evidence, private
collector registration and the shared BEGIN-admission helper. No additional
unreviewed behavior was identified in the latest T09/G5 coverage audit. The
remaining acceptance work is execution evidence and reconciliation of results;
this review record does not replace the required complete or native tests.

| Scenario | Implementation and witness | Historical evidence / remaining requirement at that point |
| --- | --- | --- |
| A01 Startup phases | `test_observability_native_acceptance`: queue, real deserialization and module import, ready, entry, model request, raw bootstrap failure | Linux source and installed candidate passed; genuine missing-module import keeps the original ModuleNotFoundError and reports no false ready/entry/model event. Windows pending. |
| A02 Raw output and progress | Same native suite: segmented bytes, heartbeat, tool response, new/replayed progress; `test_observation_processes` | Linux focused passed; original byte files and separate metric snapshots retained. Candidate matrix pending. |
| A03 Unknown / old attempts | `test_observation_journal`, `test_observation_processes`, `test_stall_supervision` | Source and installed regressions cover inaccessible identity, collector replacement and old reports. No PID-only exit inference. Native matrix pending. |
| A04 Effective deadlines | Native Run/tool cutoff witness; `test_runtime_deadline_envelopes`, `test_execution_budget` | Actual shortest cutoff, stopped process tree, inherited parent window and reserve semantics covered. Reported tool cause keeps its original message. Candidate matrix pending. |
| A05 Restart and short waits | Native controller crash after confirmed entry; native short `Task.wait`; budget/recovery tests; real dual-writer floor-loss probe | Historical restart/short-wait cases passed. The working tree now fences failed sampling before recovery and retains exact pending owners after caller expiry; four real SQLite lifetime/interruption cases passed. Complete current source/installed/native regression remains pending; A05 is incomplete. |
| A06 Parent waits / capacity | `test_managed_children_capacity`, `test_runtime_deadline_envelopes`, public native parent/child witness | Actual children return success and original failure; parent retains a touched 16 MiB buffer and actual memory readings while waiting; peak capacity two and queued successor work passed locally. This is observed process memory, not a new global memory reservation API. Native matrix pending. |
| A07 Rejection / partial registration | Child admission suite and native cross-store controller crash | Actual independent request reservation exists while Kernel child is absent; exit 73 and original-budget recovery close the wait without child business. Earlier stalled runs remain retained. Candidate matrix pending. |
| A08 Cancellation / natural completion | Native pressure, Runtime lifecycle, Windows Job and sandbox tests | Linux descendant markers stop; Kernel winner and cleanup proof remain distinct. Current Windows Jobs pending. |
| A09 Cleanup failure / exit cause | `test_sandbox_runtime` cleanup-failure restart with native worker business-call log; process exit classifiers; shared cgroup clue witness | Restart retries disposal only and keeps collected output; call count does not increase. Exit 137 remains status/unknown OOM even with readable shared cgroup counters. Provider is explicitly a persistent fake; native worker is real. Candidate matrix pending. |
| A10 Stall windows | `test_stall_supervision` | Complete consecutive windows, activity distinctions, exemptions, unknown gaps, replacement and rollback passed. Native matrix pending. |
| A11 Durable notification | Two real evaluator processes; abrupt exit after orchestration enqueue; repeated native crashes through delivery exhaustion and explicit retry | Same notice ID, one application notification, bounded attempts and explicit dead state passed. Native matrix pending. |
| A12 Supervision capacity and conditional disposition | Actual progress commit between public recheck and cancellation transaction; saturated native workers with blocked callback | Managed process capacity, native memory/budget admission, shortages and ownership are implemented. Earlier frozen local22 passed; latest complete source run failed the two-notice readiness precondition before capacity assertions. Current correction, installed witness and native matrix remain required; A12 is incomplete. |
| A13 Pressure / bounded reads | Native pressure suite: 10,000 summaries, overflowing raw output and blocked activity writer; independent settlement notes; oversized receipts / exhausted query budget | Kernel and telemetry pressure do not claim a completed observation. Runtime and standalone reads expose loss, partial receipts, bounds and cursors. Linux regression passed; native matrix pending. |
| A14 Compatibility / upgrade | Explicit copy upgrade and storage regressions; historical `v0.7.0.dev0` writer; real pending outcome and original sidecar owner | Historical installed writer rejects new storage with `StorageIsolationError`; current writer reopens it. Core copy preserves history, remains inactive, and does not migrate external journals. Original owner recovers the exact pending result without business replay. Native matrix pending. |
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
targeted execution capacity and query-size fallback. Further review verified
timer-floor retention across parent, supervisor and Windows paths, signal
interruption, inherited child pre-entry settlement and original startup-failure
classification. That review also verified that SDK-owned read expiry retries
cannot extend the child window or bypass incomplete checkpoint facts.
Historical candidate `969f0da` passed complete Linux source and installed
verification. The current candidate still needs complete installed acceptance
and native Windows/CI validation; see the current-status section above.

The independent journals retain facts; they do not authorize a new execution,
extend an original budget or prove application consumption. Missing storage,
inaccessible processes and unprovable clocks remain unknown. Historical
execution inputs and evidence are preserved. No additional checksum,
fingerprint or candidate/rubric identity gate is introduced.
