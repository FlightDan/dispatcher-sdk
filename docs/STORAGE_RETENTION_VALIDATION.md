# Storage retention implementation validation

Date: 2026-09-18. Scope: the local development tree, not a released SDK or a
production migration. The [implementation guide](STORAGE_RETENTION.md) separates
available APIs from the [remaining roadmap](STORAGE_RETENTION_IMPROVEMENT_PLAN.md).

## Capacity evidence

The deterministic benchmark used Python 3.12.3, SQLite 3.45.1 and Linux x86_64,
WAL/FULL durability, and a 524,288-byte high-entropy stable child. Every commit
explicitly supplied the state and changed a small sibling. The fixture is
SHAKE-256 bytes encoded as base64; compression cannot explain the measured reuse.
Kernel and Orchestrator shared one database in this benchmark.

| Commits | Allocated SQLite pages (bytes) | Main file (bytes) | WAL (bytes) | Main + WAL + SHM (bytes) |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 1,040,384 | 1,028,096 | 4,165,352 | 5,226,216 |
| 1,000 | 2,383,872 | 2,318,336 | 4,231,272 | 6,582,376 |
| 10,000 | 15,736,832 | 15,708,160 | 4,235,392 | 19,976,320 |

These are observations while the database was open, not post-compaction sizes.
SHM was 32,768 bytes at each observation. Allocated pages include committed pages
in WAL, so they can exceed the then-current main-file size. Revision, receipt and
event metadata still grow with commit count. Timing for the successive 100,
900 and 9,000 commits was about 10.0, 82.5 and 802.5 seconds, respectively.
The development tree received safety fixes during the run; this is a capacity
measurement, not a frozen-release performance certification.

Command:

```sh
PYTHONPATH=src python3 scripts/benchmark_state_storage.py --counts 100 1000 10000 --modes changing-sibling
```

The [machine-readable measurements](validation/storage-state-10000.json) retain
the environment and configuration. Temporary database paths were removed from
the report after the benchmark cleaned them up. Other 10,000-commit workload
variants from the roadmap were not measured in this run.

## Correctness and safety

Regression coverage includes logical Run/history/event/receipt equality and
replay fingerprints; stable-child deduplication; transaction rollback; corrupted,
missing and oversized objects; depth bounds; schema and trigger tampering;
row/byte planning budgets; protected shared objects and historical baselines;
stale/tampered plans; idempotent retries; physical maintenance exclusion; failed
cross-thread connection close; snapshot write protection including dangling
markers; copy publication failure; authenticated snapshot members; disposal
recovery and permanent identity reuse rejection.

Commands and completed results:

- `PYTHONPATH=src python3 -m unittest tests.test_content tests.test_retention tests.test_storage_connection tests.test_provenance tests.test_maintenance tests.test_storage_snapshots tests.test_storage_migration tests.test_storage_usage tests.test_state_storage -q`: 88 tests passed.
- After the final depth-boundary regressions and deterministic lease-expiry test
  adjustment, `PYTHONPATH=src python3 -m unittest tests.test_content tests.test_retention -q`:
  27 tests passed.
- An isolated environment built and installed the wheel with
  `python -m pip install --no-cache-dir --no-deps --no-build-isolation .`.
- Installed-package `python scripts/check_docs.py`: 409 local links checked,
  four README examples passed, none skipped.
- `python3 -m compileall -q src tests` and `git diff --check` passed.

Full regression: `PYTHONPATH=src python3 -m unittest discover -s tests -q`
completed in 416.607 seconds: **483 tests, OK, 16 skipped**. This includes the
isolated built-wheel consumer and its installed-package suite. The final depth
boundary and lease-test adjustments are additionally covered by the 27-test
focused rerun above.

## Limits of this verification

No real ModPort database, archive, or business blob was changed. The historical
134 GB archive was not migrated. Windows locking code requires a real Windows
host run; Linux success is not evidence of Windows behavior. Static type checking
was unavailable: `mypy` was not installed and its installation could not resolve
a package in the restricted environment. Full quotas, cross-store activation,
resumable migrations and general external GC remain implementation work, not
features validated by these tests.
