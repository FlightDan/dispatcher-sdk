# Native Windows execution

The native backend runs each Python handler in a fresh Windows interpreter.
`ScriptSpec` uses the same handler context and fenced effect records, so script
stdout/stderr files and committed operation receipts retain the usual recovery
semantics. The child SQLite connection receives the selected `durability`
profile. This backend does not use WSL or a remote Linux service.

The backend requires Windows 10 / Windows Server 2016 or newer, an ordinary
console Python executable, and a file-backed SQLite database. The backend
uses standard-library `ctypes` and Win32 Job Objects; it adds no Python runtime
dependency.

## Containment and startup

`CreateProcessW` receives `CREATE_SUSPENDED` and the extended
`PROC_THREAD_ATTRIBUTE_JOB_LIST` attribute. Windows assigns the Job
as part of process creation, before interpreter startup, user module imports,
or handler unpickling. The runtime registers its cancellation handle
before resuming the primary thread. This avoids the window left by starting a Python
process and assigning its Job afterwards.

The unnamed Job enables `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. The host owns its
only handle; it is not inheritable, and process creation disables handle
inheritance. When the host process terminates, the Job terminates too.
Neither Job breakaway flag is enabled. Ordinary child processes, including new
process groups and nested Jobs, remain subject to the containing Job.

An incompatible outer Job or unsupported creation attribute causes startup to
fail. There is no uncontained execution fallback. These rules follow Microsoft's
[creation attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
and [Job Object semantics](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

## Deadlines, cancellation, and cleanup

A host watchdog thread controls startup and execution deadlines independently
of the handler interpreter. The worker waits for a host invocation gate after
opening SQLite; only then does the business timeout begin. Startup imports and
unpickling remain bounded by the startup timeout.

Revocation, termination, process waits, and handle closure share a lock.
Termination uses `TerminateJobObject`, polls Job accounting until the active
process count reaches zero, and waits for worker process exit. A successful
outcome is accepted only after this containment completes within the execution
deadline. Even successful handlers have leftover child processes terminated.
Cleanup failures raise an error and prevent publication of a successful
execution result.

Termination cannot roll back external mutations. An unfinished effect may need
explicit reconciliation after its lease expires. The timeout watcher runs in a
host thread, not a separate watchdog service. Suspending or stopping the entire host
also suspends its timer; exiting the host closes the Job handle.

## Handler and output constraints

Handlers and custom clocks must be pickleable and importable in a fresh Python
interpreter. Top-level functions/classes in importable modules are supported.
A normal file or module entrypoint is replayed with `__mp_main__` semantics; use
`if __name__ == "__main__":` around application startup. Local functions,
lambdas, interactive/notebook-only `__main__` definitions, frozen executables,
and package `__main__.py`-only definitions are not supported. Prefer an ordinary
importable handler module for these applications. Deserialization failure is a
startup error, never an instruction to run the handler in the host.

Worker stdout/stderr go to temporary diagnostic files. Failure outcomes include
at most 8 KiB of stderr; temporary files are removed after containment. The
diagnostic files do not provide persistent logging. `ScriptSpec` retains its separately configured
artifact files and bounded tails. A host crash may leave temporary diagnostic
files for operating-system cleanup; do not treat them as execution authority.

Job Objects contain cooperative process trees; they are not an authorization or
hostile-code security sandbox. Code runs under the host user's identity and can
access that user's files and network. Windows services, WMI process creation,
or another external broker can create processes outside normal Job inheritance.
Untrusted code needs a separately secured sandbox backend. Same-user attacks
against the host and its Job handles are outside this trusted-handler contract.

## Validation status

`tests/test_windows_runtime.py` contains real Win32 integration tests for Job
assignment before deserialization, durable effects and profile propagation,
script artifacts, timeout, concurrent cancellation, new process-group cleanup,
abrupt worker stderr, abrupt host termination, incompatible outer Jobs, startup
deadlines, and guarded file entrypoints. The tests explicitly skip on
non-Windows systems. A Linux skip is not Windows verification.

Run on a native Windows worker:

```console
python -m unittest discover -s tests -p test_windows_runtime.py -v
```

Native validation passed on 2026-09-07 on Windows 11 x64, build
`10.0.26100.9168`, with the official Python 3.12.10 x64 distribution:

| Check | Actual result |
| --- | --- |
| Native runtime module | 17 tests in 26.529 s; 16 passed, only the non-Windows refusal path skipped |
| Storage, Run history and sandbox recovery | 33 passed, including the 11 process-interruption sandbox Runtime cases |
| Full discovery, including source/sdist/wheel rebuild and isolated installed consumers | 324 tests in 153.814 s; no failures, 30 platform-specific skips |
| Installed examples | All 5 passed, including scripts, effect recovery and durable audit |
| README scripts | Both English and Chinese script examples passed; the 2 Linux-specific process-crash examples skipped |

Direct success, timeout, cancel and close tests assert that descendants are gone
immediately when the invocation returns. The abrupt host-death test separately
allows bounded observation of operating-system Job-handle cleanup. Tests also
cover a host without standard handles, concurrent revocation and startup before
user deserialization. Sandbox recovery tests use a persistent fake provider and
real native local processes; the separate
[OpenSandbox service validation](OPENSANDBOX_VALIDATION.md) ran on Linux.

Native testing exposed and fixed a writable-handle requirement for backup/export
file flushing, explicit SQLite connection closure in fixtures/examples, and
test fixture import/PID-publication errors. The cleanup and recovery
assertions remain intact. The core adds no Windows-specific Python
dependency.

GitHub CI also exposed intermittent sharing violations when deleting private
diagnostic logs after worker containment. Cleanup now retries only Windows
sharing/lock errors for up to five seconds, then reports any remaining failure.
The Job termination checks still run first, and the retry does not extend the
handler's execution deadline. Native regression tests hold a log open from a
separate process and check both release-and-delete and persistent-lock failure.
After this fix, the native runtime, notification inbox and sandbox recovery
modules passed together: 59 tests in 44.992 s, with only the non-Windows refusal
test skipped.

The CI matrix runs Linux and Windows with Python 3.10 through 3.13, including
the script-notification example on both operating systems. The local evidence
above covers Windows 11/Python 3.12.10; it does not claim a completed matrix run
or direct Windows 10/Server testing. macOS/BSD detached-descendant containment
remains outside the native Windows evidence.
