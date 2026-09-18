# Reliability repair validation

Date: 2026-09-19. Source: current 0.6.0 development tree, including existing
schema 3 storage work. No release, production migration or ModPort database
operation was performed. The [plan](SDK_RELIABILITY_REPAIR_PLAN.md) and
[API guide](SDK_RELIABILITY.md) describe the delivered scope.

## Independent review and fixes

Two independent reviews covered shutdown/receipts and inspections/origins.
Actionable findings were reproduced and fixed:

- Shutdown failure cannot become success merely because resources later close;
  timeout exceptions retain their call status at the completion boundary.
- Nonfinite stop timeouts are rejected before lifecycle changes. Recent runtime
  errors remain in the report, and cleanup failure does not hide a live callback.
- Schema-only storage reads skip handler fingerprints and preserve all bounded
  writer checks for identity/mutation clocks and Kernel watermarks.
- Budgets cover source hashing, registry fingerprints, component scans and Python
  decoding boundaries. An expired last operation cannot yield a complete report.
- Origin lookups require a full unique content digest index; partial indexes are
  rejected. Encoded bytes are charged cumulatively before object body retrieval.
- Missing task identity, invalid link types and excessive content depth return
  incomplete/invalid evidence rather than complete origins or misleading byte limits.

## Executed checks

- Full discovery:
  `PYTHONPATH=src python3 -m unittest discover -s tests -q`
  ran **540 tests in 668.203 seconds**: 523 passed, 16 skipped and one error.
  The error was the nested installed-wheel full suite exceeding its previous
  300-second subprocess limit; it was not an assertion failure. The raw failure
  is retained in `/tmp/dispatcher-reliability-tests.log` for this session.
  The isolated consumer harness now gives only that complete nested suite
  600 seconds and includes captured output tails on timeout. The final tree discovers 542 tests; the
  last two budget-boundary regressions are covered by the focused runs below.
- Isolated packaging/installation rerun:
  `PYTHONPATH=src python3 -m unittest tests.test_execution_kernel_isolated_consumer -v`
  — **2 tests passed in 353.898 seconds**. This rebuilds from the source archive,
  installs the wheel into a fresh virtualenv, runs the final tree's installed
  full sub-suite (537 cases, excluding the 3 source-packaging and 2 isolation
  wrapper cases), and verifies durable Kernel/SDK consumer restart. The raw
  rerun log is `/tmp/dispatcher-reliability-isolated-rerun.log` for this session.
- Final inspection regression:
  `PYTHONPATH=src python3 -m unittest tests.test_storage_preflight tests.test_runtime_identity tests.test_storage_usage -q`
  — **51 tests passed**, including real SQLite interruption of `quick_check` and
  `dbstat`, a 5,000-row no-history-scan trace, and final-row/fingerprint overruns.
- Final identity/codec/origin regression:
  `PYTHONPATH=src python3 -m unittest tests.test_runtime_identity tests.test_content tests.test_execution_origins -q`
  — **49 tests passed**. This includes aggregate referenced-object budgets,
  rejection before object-body fetch, invalid evidence and scoped cross-segment reads.
- Shutdown regressions: **32 tests passed** across report/runtime/orchestrator
  suites; after adding the cleanup-failure/live-callback case, all **9 report
  tests passed**. Existing return and cleanup exception contracts are preserved.
- Inbox/receipt regressions: **30 tests passed**, including producer process exit,
  reopen/replay, conflicting request content, caller namespaces and concurrent ACKs.
- Built and installed the candidate wheel in a separate temporary virtualenv,
  with `--no-cache-dir --no-build-isolation --no-deps`. Installed-source RECORD
  verification and a smoke flow exercising all four APIs passed outside the repo.
- Both new examples passed against the installed candidate:
  [combined diagnostics](../examples/reliability_diagnostics.py) and
  [late-result receipts](../examples/request_result_receipts.py).
- Documentation links and **4 README examples** passed; compilation and
  `git diff --check` passed.
- Installed-candidate public typing passed with mypy 2.3.1, Python 3.10 target,
  `--follow-imports=silent --warn-unused-ignores`: all three fixtures
  (`orchestrator_consumer.py`, `capability_consumer.py`, `reliability_consumer.py`)
  reported no issues. The new fixture and examples are included in CI.

The first local wheel installation hit a read-only pip cache; rerunning with
`--no-cache-dir` succeeded. This was a tooling-path issue, not a package failure.
The default package source could not supply mypy; an explicit official PyPI
installation into a temporary tools directory succeeded, enabling the type check.
Earlier agent full-suite attempts were stopped while review fixes were still changing
the source; those runs are not counted as successful verification.

## Limits

- This run is Linux validation. Native Windows and external sandbox execution
  are not newly certified by these changes.
- Budgets are cooperative. Blocking third-party cleanup, progress callbacks and
  filesystem I/O cannot be forcibly interrupted by Python.
- Shutdown reports do not infer persisted checkpoint contents or pending delivery
  counts. Origin lookup covers one supplied schema 3 store; authenticated cold
  archive resolution and cross-store discovery remain outside this patch.
- Request receipts require the adapter to authenticate the caller and report a
  separate explicit ACK. They do not establish comprehension or business approval.
