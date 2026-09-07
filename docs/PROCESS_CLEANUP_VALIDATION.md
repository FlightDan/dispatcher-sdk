# Process cleanup validation

Linux supervisor cleanup now finishes when the kernel reports that the
supervisor has no children, instead of waiting for a 50 ms quiet interval.
The parent-side emergency teardown and the non-subreaper fallback retain their
existing conservative observation window. No runtime dependency was added.

## Completion criterion

The private supervisor enables `PR_SET_CHILD_SUBREAPER` before creating its
worker. An orphan is reparented to its nearest living ancestor subreaper,
including a double-forked process that changed sessions. This is the Linux
[subreaper contract](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html).

During cleanup the supervisor creates no further workers, remains single
threaded, and keeps `SIGCHLD` at `SIG_DFL`. Every surviving descendant therefore
still has an ancestor in this tree, or has become the supervisor's direct
child. The supervisor kills its direct children, reaps exited children, and
repeats as further descendants are adopted.

`waitpid(-1, WNOHANG | __WALL)` returning zero means children remain; only
`ECHILD` permits success. `__WALL` also includes clone children that do not
deliver `SIGCHLD`. Other wait errors do not prove containment. These distinctions
come from the Linux [wait contract](https://man7.org/linux/man-pages/man2/waitpid.2.html).

An empty or unreadable `/proc` children listing cannot prove that the tree is empty.
The supervisor uses the listing to locate children to signal and the wait result
to determine completion.
The fast path rejects a root PID other than the calling supervisor's own PID.

The Linux path signals only direct children that this supervisor has not yet
reaped. They cannot have their PIDs reused between enumeration and signalling.
It does not repeatedly signal the original worker's process group after that
worker has been reaped. Parent teardown also returns immediately after observing
that its supervisor has been reaped, without looking up or signalling that
now-reusable PID's process group.

PID reuse races remain possible in the parent fallback.
The parent still scans descendant numeric PIDs and signals them while the live
supervisor can independently reap children. A scanned descendant may exit, be
reaped and have its PID reused before the parent signals it. The fallback has
no pidfd or equivalent stable-identity fence for that interval. The sibling
race tests exercise ordinary contention but do not prove this race impossible;
the direct-child non-reuse argument applies only inside the supervisor fast path.

## Deadlines and containment limits

- Successful handler outcomes still require containment before the monotonic
  business deadline. The fast path does not extend that deadline.
- Timeout cleanup retains the existing bounded grace interval.
- Parent cancellation keeps the supervisor alive while killing its tree and
  retains the conservative fallback. The parent's own wait result
  cannot prove that the supervisor's descendants are gone.
- Other POSIX execution uses the existing group/tree quiet-window path. Native
  Windows has a separate Job Object implementation, verified on Windows 11 x64
  build 10.0.26100.9168 with Python 3.12.10. Its native module passed 16 tests
  with one non-Windows refusal test skipped. These results cover Windows Job
  lifecycle behavior, separately from the Linux subreaper proof described here;
  see [native validation scope](WINDOWS_RUNTIME.md).
- Worker construction still happens through a spawned supervisor. The new
  `durability` argument is forwarded to the worker's SQLite connection, with
  the compatible `"full"` default on each private entry point.

The proof assumes the supervisor remains alive through cleanup. Arbitrary
external destruction of the supervisor remains outside this containment
guarantee. Processes stuck in the kernel still use the existing bounded-cleanup
behavior. A missing `/proc` view cannot cause a false fast-path success while
waitable children remain, but can prevent cleanup from completing.

## Tests

Run the focused and existing runtime checks:

```sh
PYTHONPATH=src python3 -m unittest tests.test_process_cleanup_boundaries tests.test_process_clone_cleanup tests.test_runtime_host_cancel_tree -v
PYTHONPATH=src python3 -m unittest tests.test_execution_kernel_v2_runtime -q
```

The focused tests use real processes and cover:

- A worker that has exited while a detached double-forked descendant remains.
  The supervisor must not report an empty tree, including with an artificially
  empty `/proc` listing.
- Ordinary forks, double forks, forks made by a worker thread, and a bounded
  producer that continues forking detached children during cleanup.
- Parent teardown racing supervisor cleanup and exit at four delay settings,
  with an unrelated sibling process required to remain alive.
- Runtime success, direct worker exit, timeout, and cancellation with a
  continuously spawning tree; cancellation must have no recorded survivors
  when it returns, without eventual polling.
- Real Linux `clone()` children with exit signal zero. A compiled C helper
  creates detached children: ordinary wait reports ECHILD while `__WALL` still
  observes the live child. The isolated supervisor probe then kills and reaps
  it. Runtime success and timeout check disappearance at terminal return,
  including zombies, and require an unrelated sibling to survive. These two
  tests passed; they explicitly skip if a C compiler (`cc`) is unavailable.
  The direct-child probe matters because orphan reparenting can change the exit
  signal, so runtime descendant tests alone do not establish the wait-class distinction.
- Non-`ECHILD` wait errors and simulation of an exited supervisor's numeric PID
  being reused as another process group.

Five focused tests plus the existing host cancellation-tree test passed. The
existing process/thread runtime module passed all 29 tests. The parent teardown
race test was also repeated ten times: 160 topology/delay cases passed
with no recorded surviving descendants or damage to the unrelated sibling.

The direct-exit test preserves an existing behavior: descendants inherit the
worker's channel, so a worker that calls `_exit` while descendants retain that
channel reaches timeout before the supervisor can observe EOF.

## Same-environment benchmark

```sh
PYTHONPATH=src python3 scripts/benchmark_cleanup.py --samples 30 --legacy
PYTHONPATH=src python3 scripts/benchmark_cleanup.py --samples 30
```

Each sample runs in its own Linux subreaper. Measurement begins after the
worker/tree is ready and ends when containment completes. Database work and
supervisor startup are outside the measured interval. `--legacy` exercises the
retained 50 ms path while still using a Linux subreaper for the test tree.

Measured on Linux 6.8.0-138, x86-64, glibc 2.39, Python 3.12.3:

| Tree | Legacy median wall | New median wall | Legacy p95 wall | New p95 wall | Legacy median CPU | New median CPU |
|---|---:|---:|---:|---:|---:|---:|
| Worker only | 52.92 ms | 3.65 ms | 55.66 ms | 6.26 ms | 5.07 ms | 1.60 ms |
| Double fork + new session | 55.77 ms | 3.39 ms | 59.41 ms | 5.12 ms | 5.96 ms | 1.35 ms |

A run before editing the runtime measured 52.96/55.64 ms median wall time for
the same two trees, consistent with the retained-path comparison. Each table
cell summarizes 30 samples; the script emits environment details and the
implementation SHA-256 with its JSON results.

These are cleanup measurements in a shared environment, not end-to-end handler
throughput claims. Database durability, handler work, process startup, and load
still contribute to total latency. The fallback was exercised on Linux;
macOS/BSD were not available for native testing.
