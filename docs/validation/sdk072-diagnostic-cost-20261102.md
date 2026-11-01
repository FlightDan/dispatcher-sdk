# SDK-07 diagnostic cost probe — 2026-11-02

This is a one-shot Linux / Python 3.12.3 measurement of the existing
`scripts/benchmark_diagnostic_bounds.py` against its generated schema-6 SQLite
fixture. The database held one Run, 60,000 task keys, and 100,000 synthetic
`sdk_events` rows; its file size was 10,690,560 bytes. No product source was
changed. The probe exited 0, including its truncation and integrity assertions.

## Measurements

The original script completed in 5.42 seconds wall time and used 1.20 seconds
user CPU plus 0.14 seconds system CPU. Its maximum resident set was 33,020 KiB.
This total includes Python startup, schema creation, insertion and commit of
160,000 rows, all four inspections, and JSON output. It is not a measurement of
application startup. The script does not separate fixture setup time.

| Inspection | First pass wall time | Second read-only pass wall / CPU | Compact result JSON |
| --- | ---: | ---: | ---: |
| `inspect_storage(check="schema")` | 18.95 ms | 37.58 / 37.58 ms | 588 bytes |
| `inspect_run_diagnostics(task_limit=10, task_count_scan_limit=100)` | 22.16 ms | 29.95 / 29.96 ms | 2,478 bytes |
| `inspect_run_diagnostics(timeout_seconds=0)` | 0.034 ms | 0.081 / 0.081 ms | 636 bytes |
| `inspect_storage(check="full")` | 47.54 ms | 62.03 / 62.04 ms | 589 bytes |

The first pass reported 10,690,560 database bytes. The full check returned
`integrity=ok`. The second pass measured compact UTF-8 JSON for each returned
result object; it excludes the outer benchmark wrapper and transport framing.
The two passes ran while the repository's source suite was also active, so the
variation is a contention-sensitive observation rather than a performance
threshold. The second process peak RSS was 33,088 KiB.

## Bounded behavior and scan scope

The bounded Run report returned 10 tasks, `tasks_has_more=true`, and cursor
`task-0000009`. It reported `task_count=null`, lower bound 100, and
`task_count_complete=false`, while the fixture contained 60,000 task keys. The
report had `complete=false`; Kernel recovery remained explicitly unknown because
the Kernel store was not supplied. A zero-second budget returned
`inspection_timeout`, an incomplete report, and unknown count rather than an
exact zero. The assertions for these conditions passed.

The count query reads at most 101 indexed task keys to determine whether the
100-key scan bound was exceeded; the task page fetches at most 11 keys to return
10. The 100,000 event rows were not read by `inspect_run_diagnostics`; they
contribute to database size and the full SQLite integrity scan, but do not
exercise event-history traversal. The schema phase took about 20.59 ms of the
first bounded inspection's 22.16 ms; the bounded count and page phases each
took under 0.2 ms in that pass.

## Limits

This fixture demonstrates bounded task-key paging on a large synthetic store,
not the actual target Run layout. Task values are minimal, there are no
execution-attempt records or wait history, and the event rows are uniform empty
payloads. The script does not capture output bytes or per-case CPU; the compact
byte and per-case CPU values above came from an additional read-only pass over
the same generated database. No repeated-run distribution, storage-growth
curve, production startup path, or target-handler/deployment acceptance was
measured. No concrete SDK defect was exposed by this probe.
