# Run storage growth validation

The schema-v2 fixture shows near-linear retained storage as a single Run grows
from 100 to 800 small tasks. Command receipts remain historical Run references;
their payloads are reconstructed from retained item versions when read. The
measurement does not establish constant-time Run operations.

## Reproduce

```sh
PYTHONPATH=src python3 scripts/benchmark_run_storage.py --output /tmp/run-storage.json
```

Defaults are 100/200/400/800 tasks, 128 payload bytes, and `durability="full"`.
The script uses temporary databases and removes them on completion. Add
`--keep-db` to retain them; their directory is recorded in the JSON output.
Use `--sizes`, `--payload-bytes`, and `--durability` to configure the fixture.
`--idle-sync-tasks 0` skips the independent terminal-execution sync fixture.

Every growth step adds one task and cancels it while still planned in a single
`apply_operations` call. Each step therefore adds one command receipt, one task,
and one execution registration. IDs have fixed width, payloads are identical in
size, and the application state does not grow. The kernel is a real SQLite
kernel in the same file, but this fixture does not dispatch or execute handlers.
It contains one Run segment throughout.

At each checkpoint the script verifies the first command through all three
historical paths: `get_command_receipt`, replaying its original request with
`expected_revision=0`, and `get_run_at(..., 1)`. All must return the original
one-task snapshot, and replay must not add another receipt.

The output records Python/SQLite/platform details, durability PRAGMAs, source
SHA-256 hashes, storage metrics, SQL counts, and timings. The script aborts if
the source changes during the run, so one measurement cannot mix implementations.

## Observed storage

Measured on 2026-09-07 with Linux 6.8.0-138 x86-64, glibc 2.39, Python 3.12.3,
SQLite 3.45.1, WAL mode, `synchronous=2` (FULL), and 4096-byte pages. The shared
environment reported 12 logical CPUs.

| Tasks | DB file / allocated page bytes | Pages | Receipt JSON bytes | Receipt rows | Current item rows | History rows | Execution rows |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 258,048 | 63 | 29 | 1 | 4 | 4 | 0 |
| 100 | 630,784 | 154 | 3,021 | 101 | 204 | 204 | 100 |
| 200 | 1,019,904 | 249 | 6,121 | 201 | 404 | 404 | 200 |
| 400 | 1,810,432 | 442 | 12,321 | 401 | 804 | 804 | 400 |
| 800 | 3,317,760 | 810 | 24,721 | 801 | 1,604 | 1,604 | 800 |

The largest individual `sdk_commands.response` was 31 bytes at every nonempty
checkpoint. `sdk_run_revisions` and `sdk_events` each contained `tasks + 1`
rows. The growth fixture had no command outbox entries or kernel executions.
The four initial items are the Run's root values.

The next table sums the actual UTF-8 JSON bytes in `sdk_commands.response`,
`sdk_run_items.value`, `sdk_run_history.value`, `sdk_executions.command`, and
`sdk_events.payload`. It excludes keys, digests, SQLite row/index overhead, and
the other tables; those costs are included in the database file measurement.

| Tasks | Selected JSON bytes | Net JSON bytes per added task | Full returned Run JSON bytes |
|---:|---:|---:|---:|
| 100 | 289,169 | 2,889.82 | 77,067 |
| 200 | 578,369 | 2,890.91 | 153,967 |
| 400 | 1,156,769 | 2,891.46 | 307,767 |
| 800 | 2,313,569 | 2,891.73 | 615,367 |

Net JSON density subtracts the initial 187 JSON bytes. Its maximum/minimum
ratio was 1.000660, about 0.066% variation across the checkpoints. Revision
numbers gaining digits account for small variable-length metadata. The item
and history row counts grow by two rows per added task in this fixture.

Each measured final add operation performed one execution registration lookup,
two current-item upserts, two history inserts, and one receipt insert. It also
performed one full current-Run load query; the number of rows returned by that
query grows with the segment.

## WAL and file measurement boundaries

File/page values above were captured after `wal_checkpoint(TRUNCATE)`, without
`VACUUM`. The checkpoint was unblocked at every point. Page bytes equal
`page_count * page_size`; all observed freelists were empty. The 258,048-byte
initial allocation includes both kernel and orchestration schema/index overhead.

The following table reports WAL allocation separately from the post-checkpoint
file sizes:

| Tasks | DB file bytes before checkpoint | WAL bytes before checkpoint | WAL bytes after checkpoint |
|---:|---:|---:|---:|
| 100 | 462,848 | 4,165,352 | 0 |
| 200 | 1,007,616 | 4,165,352 | 0 |
| 400 | 1,748,992 | 4,202,432 | 0 |
| 800 | 3,166,208 | 4,194,192 | 0 |

The shared-memory file was 32,768 bytes while connections remained open. WAL
can contain repeated versions of pages and retain its allocated size between
checkpoints. These are point-in-time file sizes, not measurements of peak disk
usage, total bytes written, write amplification, or fsync counts. Explicit
checkpoints affect the experiment's maintenance schedule and are outside the
recorded `apply_operations` timings.

## Terminal-only sync

A separate temporary fixture creates 40 real kernel executions already in the
cancelled terminal state, registers and dispatches them through the SDK, and
flushes their command deliveries and projections. It then calls `sync()` five
times. None of these rows are included in the growth tables above.

All five sync calls returned zero. Together they issued five active-execution
queries, zero `Kernel.get` calls, and zero full Run load queries. The measured
median was 1.15 ms, with 4.59 ms p95 across five calls. These counts show
that this polling path excludes settled execution history. They do not
describe overall orchestration polling or guarantee constant-time index work.

## Limits and interpretation

- `apply_operations` still loads and returns a complete current-segment Run.
  `get_run` also materializes its history. The returned JSON grew roughly eight
  times between 100 and 800 tasks. Compact receipts do not make historical
  reconstruction constant time: it can inspect retained item versions.
- The median API timings over the successive 100/100/200/400-call blocks were
  29.87/31.66/33.72/43.42 ms. They include each full returned snapshot, but exclude
  fixture construction, historical verification, and checkpoint measurement.
  Shared-machine scheduling and I/O make these observations unsuitable as
  throughput guarantees or a controlled comparison with another implementation.
- The fixture uses small fixed-size changes. Repeatedly replacing one growing
  JSON item, such as an expanding `application_state` blob, can still accumulate
  much larger version history. Large results and dependency graphs were not
  exercised here.
- Explicit `continue_run` segmentation can bound the active Run's task history
  while retaining old segments and receipts. This benchmark uses one segment
  and does not measure continuation. Summary and paginated APIs reduce returned
  data; callers should not assume that every underlying query is constant time.

The [implementation plan](IMPLEMENTATION_PLAN.md#progress-evidence) records an
earlier approximately 237 MB command-receipt JSON baseline for 800 small tasks.
That investigation used a different fixture, including additional empty
decisions, and a different storage implementation/configuration. It shows
the old full-snapshot duplication, but the differing fixtures prevent a direct
latency or exact storage-ratio comparison with this run. In this run, receipts
totaled 24,721 bytes; the complete retained database occupied 3,317,760 bytes
after checkpoint.
