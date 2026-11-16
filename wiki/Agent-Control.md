# Experimental Agent Control

> This page documents the local 0.8.0 development candidate. The implementation is still on the local development branch.

Pending child-result observation starts with a 50 ms sleep and backs off to at most 500 ms while the durable state and diagnostic are unchanged; a change resets the sleep to 50 ms. Each pending observation retains its authority checks and fresh budget sample, and sleep never exceeds the original remaining work window. Result and cancellation observation may therefore take up to 500 ms plus operation and scheduling time; this is not a new execution allowance. Already recorded result delivery retains its existing read-before-sample and factual-delivery rules.


After an invocation's original host deadline, `Invocation.wait()` and `AgentRun.wait()` may raise `AgentExecutionError` with `completion_state="unknown"` when bounded inspection finds a pending late fact for the exact current execution, attempt, fence and lease. The exception snapshot preserves the actual invocation and execution states; it does not label them completed, cancelled or recovery-required. This reports uncertainty at observation time: a valid result can arrive afterward. It grants no retry, cleanup, result-publication or extra budget authority. A confirmed terminal result takes precedence. Missing, stale, oversized, busy or incomplete evidence retains normal waiting and may still end in `TimeoutError`; this is a best-effort observation, not a guarantee that every uncertain execution will be detected. Inspection shares the original caller wait deadline, uses a combined 50 ms probe window and runs at most once per 250 ms; Run probes rotate across eligible invocations.


AgentApp requires its completion settlement storage to initialize successfully before accepting requests. If that storage is unavailable, construction fails and attempts initialization cleanup; failed cleanup remains explicit. Repair the storage problem before reopening the same state directory. This check does not guarantee later writes will succeed and does not extend any request budget.

On Linux, the normal-return and eligible generic-exception callbacks sample boot elapsed time before arbitration or storage. Native boot-domain discovery cannot shift this timestamp. If this first SDK observation already exhausts the original budget, a live monitor may attempt a timeout decision even when durable return-time capture fails; every existing clock, generation, stop and effect check still applies. This is an SDK observation time, not proof of the physical function-return instant. An earlier observation followed by delayed publication remains unknown when its durable timestamp cannot be confirmed. Other platforms retain conservative behavior for this fallback.

Persisted runtime observation does not wait for the local pending-settlement registry lock. If that lock is busy, the report is incomplete and local settlement inspection is unknown; it does not assert that no obligations exist. Inspection never grants completion or retry authority.

A live invocation monitor can decide an exhausted timeout under its lifecycle and completion arbitration locks. It carries the original budget and verifies shared clock continuity in the same transaction that excludes effect admission: unfinished effects require recovery; otherwise the decision is terminal. A just-published timeout is consumed only through its exact in-memory publication by that live monitor. Retained late facts do not acquire this authority. Only an already captured local budget fact may be acknowledged; no new sample or foreign-owner acknowledgment is permitted after the work cutoff. Stop, contention, missing facts, and uncertain commits remain conservative; a lost response is checked against the exact committed result.

When an owned completion decision raises without an exact committed receipt, its retained outcome records the failure phase and exception class. Exception text is omitted to avoid retaining provider inputs. This diagnostic grants no retry or completion authority.

A local result candidate is constructed without lifecycle ownership; it grants no delivery authority. Failure to acquire the lifecycle lock before the actual owned decision may retry within the original deadline, retaining the same candidate and captured return. Stop or deadline exhaustion prevents further admission.

Live thread completion retries only a positively identified failed SQLite BEGIN admission or a global-sample refusal before any result write, after transaction cleanup and exact connection checks. Other executions retain ownership of their samples; completion waits without acknowledging or adopting them. An on-time captured return keeps its existing first decision opportunity after delayed effect collection; extra attempts remain bounded by the original work deadline. Each attempt retains the original result identity and captured return, releases lifecycle ownership between attempts, and rechecks stop and the original work deadline. Short lock admission remains capped at 0.1 seconds; an admitted completion transaction still checks its original work cutoff before commit. Ambiguous body, commit or cleanup failures do not qualify for this retry. Monitor sampling shares the return/completion arbitration gate; while completion owns it, monitoring projects retained time instead of arming a new sample. Final installed-package acceptance is pending.

Child waits may retry an expired short receipt-encoding window only within their original work deadline, retaining the exact sample token and captured input fact. A chained cleanup failure, missing captured fact, stop, or exhausted original deadline does not authorize another sample or business retry. Factual result delivery also refuses unresolved global clock samples owned by other callers; it never finishes those owners on their behalf. This source behavior still requires final installed-package acceptance.

The host continues periodic reconciliation while invocations or plans are pending. An unchanged pending inventory does not count as progress or force an extra worker poll; actual submissions still wake the host explicitly, and accepted triggers or acknowledged dependency deliveries report progress.

An empty dependency queue is checked with a read-only snapshot. Epoch, arguments and clock validity are still checked, and the exclusively owned host epoch retains the observation's in-process clock high-water without writing the durable clock. Any unacknowledged receipt takes the existing fresh write-transaction claim path. Empty observations are not cached; later deliveries are discovered on subsequent polls.

Managed thread return and ordinary failure capture now also receive the original entry work cutoff. Each short storage admission rechecks the exact live owner and stop/revocation signals; stop cannot interrupt an already executing admission. Pending or uncertain samples are retained without replacement. This source change is under regression verification and is not final installed-package acceptance.

Invocation state, run-node lists and native-operation lists are observed through consistent read-only snapshots. They can return the last committed state while a writer is in progress; an observation never grants launch or cleanup authority. Those actions retain their separate identity, permission and durable ownership checks.

Native process completion sampling waits only within the original work cutoff retained at confirmed entry. Each storage attempt is capped at 0.1 seconds (or a smaller configured control timeout); retries share the original cutoff and tighten it using elapsed budget time. They retain the same lease, sampling owner and fact. A sampled fact may only be acknowledged, never resampled. Without a confirmed finite work cutoff, capture retains its single bounded control window. Unresolved sampling or storage failure remains unknown; this does not authorize repeating the handler. Factual clock publication does not itself authorize a successful result.

Before handler entry, a sampling refusal may wait only within the original startup/work cutoff when this entry owner has not armed a sample. It rechecks authority and waits for the original sampler to publish; it never clears or adopts its marker. An owned uncaptured sample or ambiguous acknowledgment remains unknown.

A finite `RuntimeHost.stop` may return `False` after runtime cleanup has completed if launcher retirement could not acquire its lock before the same deadline. The stop report retains the confirmed cleanup outcome; a later stop retries retirement without running cleanup again. A launcher admission timeout before queue handoff permits retry of the same bound owner. An ambiguous queue handoff never permits a replacement submission.

Finite RuntimeHost stop calls record a structural error summary without reading custom exception attributes or formatting the exception. This diagnostic step does not replace the original error. Its error type is reported as `BaseException`, and execution context fields are omitted. Background diagnostics retain their existing detailed behavior.

AgentApp automatically enables SDK-owned completion delivery and preserves its
`execution.sqlite3.delivery.sqlite3` companion journal across restarts. Keep
that file with the state directory. Existing execution history with a missing
delivery journal is rejected; this path does not migrate legacy journals.
The lower-level Runtime option `managed_delivery` defaults to `False` and
requires file-backed thread isolation when enabled.

The 0.8.0 agent API is experimental. It implements task and service invocations, dependencies, dynamic groups, explicit rework, goal validation, and persistent sessions. G17 has legacy API, CLI, supervision and resource admission evidence on the prior installed candidate. G18 still requires installed-package regression, platform coverage and final package and document alignment; see the [current acceptance record](../docs/SDK_0_8_0_CURRENT_ACCEPTANCE.md) for exact candidate boundaries. See [the detailed guide and complete canonical default registry](../docs/AGENT_CONTROL.md) and [the goal and acceptance contract](../docs/SDK_0_8_0_AGENT_CONTROL_GOAL.md).

Close uses bounded lifecycle receipt batches by default: up to eight events and 262144 encoded payload bytes; one oversized head may advance up to 1048576 bytes. The receiver accepts at most 64 nested JSON containers and rejects cycles. Unsupported facts remain pending. Every close batch, including one event, shares the original remaining deadline; timeout does not authorize replay or a fresh write window. Required rollback and clock-only cleanup of an already-admitted transaction may finish later. See [receipt and deadline details](../docs/EXECUTION_OBSERVABILITY.md).

## Start a standalone invocation

Install the package with YAML support using `pip install 'dispatcher-sdk[agents]'`. On Linux, install `opencode`, configure the host's `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`, and select an available `openai/...` or `anthropic/...` model. The optional endpoint variables are `OPENAI_BASE_URL` and `ANTHROPIC_BASE_URL`. Keep credentials in the host environment.

```yaml
# agents.yaml
schema_version: 1
defaults:
  runtime:
    model: openai/YOUR_MODEL_ID
agents:
  coder: {}
```

```python
from dispatcher_sdk.agents import AgentApp, ApplicationSpec

spec = ApplicationSpec.from_yaml("agents.yaml")
with AgentApp(spec, state_dir="./agent-state") as app:
    call = app.coder("Explain the task.")
    print(call.request_id)
    print(call.wait(timeout=120))
```

The equivalent Python configuration is `ApplicationSpec({"coder": AgentSpec("coder")}, defaults={"runtime": {"model": "openai/YOUR_MODEL_ID"}})` after importing `AgentSpec`. The same handle is available through `app.agent("coder")`. Use `app.agent(name)` when a name contains a hyphen, begins with an underscore, or matches an existing `AgentApp` attribute such as `start` or `close`; those names cannot reliably use the `app.coder` shorthand. State directories must be host-owned and not group/world writable. `soul` and `prompt` identify files, resolved relative to `base_dir`; otherwise provide task instructions in the call. A successful close stops the local host and does not leave a persistent service. If cleanup is incomplete, close raises and the application retains ownership so cleanup can be retried.

Legacy `Kernel.open_sqlite(..., isolation_mode="thread")` without delivery activation retains its existing close behavior: revoke handler authority and drain observation and budget cleanup without waiting for an arbitrary Python callable to return. Python threads cannot be forcibly stopped. Managed Agent delivery additionally retains its completion capability until the callable finishes; an unresolved owner prevents successful close. Neither mode discards ambiguous slot release, pending settlements or active observation/budget readers.

To configure the runtime explicitly, import the public adapter module and pass the adapter to `AgentApp`. The constructor below retains the default tool grants; add host grants or provider options there when needed.

```python
from dispatcher_sdk.agents.opencode import OpenCodeAdapter

adapter = OpenCodeAdapter(executable="opencode")
with AgentApp(spec, state_dir="./agent-state", adapter=adapter) as app:
    print(app.coder("Explain the task.").wait(timeout=120))
```

## What the configuration means today

The parser checks YAML and Python definitions against the same schema. Mappings merge recursively, lists replace, omission inherits and only specified fields accept null. Application `defaults` must be a mapping when supplied: omit it or use `{}` to inherit, rather than passing `null` or Python `None`. It rejects unknown fields, duplicate YAML keys, unknown role references and static dependency cycles. `spec.to_dict()` exposes resolved defaults and agent settings; `spec.agent("coder").to_dict()` exposes one agent's effective settings. The complete default registry is reproduced below.

OpenAI-compatible streaming token settlement requires a finished single completion choice and final usage bound to the same nonempty response ID. An empty final usage choices array is allowed after completion, including tool-only or empty-text output. Missing or conflicting identity, missing completion, malformed usage or interrupted framing retains the full unknown reservation. This source fix still requires installed-package acceptance.

Parsing a setting does not make it executable. Dynamic groups and host-submitted services remain experimental in current source; supervision is experimental and complete recovery remains incomplete. Non-null token budgets are experimental in current source and limited to the SDK-owned OpenCode proxy with a versioned host model contract (`token_budget.request_limit` for the total billable upper bound and `output_limit` for output). Every fallback needs a contract. Without it execution is rejected. Chat Completions and Anthropic Messages are supported by the source parser; Responses is not. Pending group bounds consume capacity in full; unknown usage blocks further admission. Real OpenCode acceptance of this feature remains incomplete; `budget.tokens` defaults to `null`. Model fallback selection requires the trusted host configuration described below. Reasoning variants require explicit trusted host configuration as described below. `strict` execution requires a native backend that is not provided. Each provider inference request attempt counts against `budget.model_turns` before connection, including failed or aborted attempts; the default is 128. A configured model is required at execution time.

SDK file tools enforce their declared path policies, subject to platform support; this is not OS process isolation. The current file backend requires Linux on x86-64 or ARM64 with `openat2` available. A native strict isolation backend is not provided, and real strict isolation has not been accepted. Current source also implements a Windows host lock and Job Object native guard, but these have not been validated on native Windows; no cross-platform acceptance is claimed here.

On Windows, current source can construct an absolute private workspace with an empty file policy; SDK file read, list and write remain unimplemented and fail closed, and shared file roots are unsupported. No native Windows validation is claimed. The Windows hello and the operation-ready handshake each have their own maximum five-second window, capped by the original invocation deadline; socket I/O waits use slices of at most 0.1 seconds, with cancellation checked between slices. The read-only startup SQLite busy timeout is 0.05 seconds. These bounds do not limit arbitrary filesystem I/O, custom callbacks, later full SDK authorization, or overall startup or return latency. The guard cleanup wait is five seconds and the host guard wait is eight seconds; neither resolves an unknown business outcome.

Host-granted native tools are implemented in current source; their native evidence is currently limited to Linux. `OpenCodeAdapter(allow_shell=False, mcp_servers=None, host_tools_revision=None)` defaults to no shell and no external MCP servers. An Agent must separately request `tools.shell: true` or list exact server names in `tools.mcp`; the adapter rejects requests outside the host grants before admission. To grant either capability, the host must supply a nonempty `host_tools_revision`. Local MCP entries have `type: local`, a nonempty `command` argument list, and optional `environment` and `timeout` (1–300000 ms); names are at most 64 characters, use lowercase ASCII letters and digits, start with a letter, and cannot be `dispatcher`. Remote MCP is not supported. Grant only trusted commands and environment values; these execute as native host code.

`tools.network` defaults to `false`. Setting it to `true` in the trusted Agent configuration allows OpenCode's `webfetch` and `websearch` tools; it does not require the separate shell or MCP grants. This setting controls those tool permissions and does not provide operating-system network isolation.

The host must treat `host_tools_revision` as an immutable opaque identifier and change it whenever commands, environment values, grants, model variant options, or local model availability change. The SDK stores that value with frozen configurations and plans, rejects changed revisions when reopening unfinished plans, and rejects live revision drift. The SDK does not verify that the revision identifies the actual grant contents; reusing a revision for different contents defeats this safeguard. Shell and local MCP are not constrained by SDK file-tool path grants and are not a sandbox. Descendant process cleanup requires the corresponding native guard evidence; a cleanup receipt alone does not establish the model result. Candidate 16 passed separate normal-completion and cancellation scenarios with real OpenCode 1.18.32 on Linux x64 / Python 3.12.3: the model executed the authorized shell and local MCP tools, their fixture descendants were observed alive, and exact authenticated guard receipts confirmed cleanup. The normal effect committed and its required output matched. After cancellation the model effect remained indeterminate and the invocation remained recovery_required; cleanup does not resolve that outcome. Other platforms and broader capability fault cases remain unaccepted.

Read-only shared inputs require both an absolute `files.shared_read` grant and a host upper bound: `AgentApp(..., shared_roots=["/srv/agent-inputs"])`, or repeated `serve --shared-root /srv/agent-inputs` options. The default host list is empty. Shared roots cannot include the filesystem root or overlap Agent state, and symbolic-link components are rejected. `file_read`, `file_list` and file artifact publication use the same grants; `file_write` cannot write shared paths. Hosts must protect roots and their ancestors against replacement and keep unrelated secrets outside them. Writable workspaces use the separate host ownership policy below. Candidate 15 passed real OpenCode reads, directory listing, denied writes and original file-snapshot consumption on Linux x86_64; full final-candidate acceptance is still incomplete.

Writable workspaces are supported in current source through explicit host grants: `AgentApp(..., workspace_roots=["/srv/work"], workspace_registry="/srv/agent-workspace-registry")`, or repeated `serve --workspace-root DIR` with `--workspace-registry DIR`. Both arguments default to no grant. The registry must already exist with mode `0700`, outside Agent state and every writable root; every cooperating host sharing those roots must use the same protected, stable registry and unaliased paths. Roots must be existing canonical directories without symlinks, cannot overlap state or registry, and cannot overlap one another. The host must prevent untrusted root/ancestor replacement and registry modification. Advisory ownership does not constrain uncooperative processes or native code.

`workspace.mode: private` remains the default, with `path: null` and `shared: []`. For `persistent`, set an absolute `workspace.path` beneath a host root; relative `files.read/write` grants apply there and contents survive invocations and host reopen. For `shared`, keep `path: null` and list absolute directories in `workspace.shared`; the primary workspace stays private, and each accessible shared file needs a separate **absolute** `files.read` or `files.write` grant. Relative grants apply only to the primary workspace. `files.shared_read` continues to grant reads only. The SDK conservatively serializes the entire containing host root, including sibling subdirectories and read-only invocations that select it. A dynamic child cannot select a root retained by an ancestor; admission reports `agent_workspace_ancestor_conflict` before creating its effect. Sequential downstream roles can use the root after the prior invocation releases ownership.

Ownership is reserved before the runtime effect or adapter starts and remains across goal steps and technical retries under the original deadline. Release requires local helper quiescence and exact original effect/native cleanup proof. Process death or deadline expiry never clears an unknown owner; only the original state host, holding its exclusive host lock, can reconcile exact cleanup evidence. A different state cannot recover that owner. Frozen plans retain exact host roots and registry; reopen with different grants is refused while plans remain unfinished. Nonprivate workspaces currently reject shell and external MCP tools because file-tool grants cannot protect the ownership registry from those tools. Candidate 24 passed seven checks using installed-package OpenCode 1.18.32 on Linux x64 / Python 3.12.3: persistent writes, reopen and stable replay, shared writes, denied outside/state writes, original artifact consumption after a deliberate host file change, original budgets and exact native cleanup. Source SDK integration also passed cancellation/unknown-owner and ancestor-conflict tests. This does not establish native crash recovery, concurrent-host exclusion or other platforms. Candidate 47 completed the Linux x64 Python 3.12 full installed regression with skips; Windows-specific skips, other platforms and final acceptance remain open.

## Automatic dependency graphs

A host invocation starts a dependency-free root and freezes all reachable `inputs_ready` roles before admission. A role is reachable through dependencies or input references, and all of its dependencies must be in that root graph. Mixed-entry graphs requiring a second independent root are rejected before admission. The current graph runs each role once in round 0.

Save this graph configuration as `graph-agents.yaml`:

```yaml
schema_version: 1
defaults:
  runtime:
    model: openai/YOUR_MODEL_ID
agents:
  seed: {}
  writer:
    inputs:
      task: {ref: seed.output}
      instruction: "Publish your answer as the declared answer artifact."
    output:
      declared:
        answer: {}
      required: [answer]
  reviewer:
    inputs:
      task: {ref: seed.output}
  consumer:
    inputs:
      sources:
        - {ref: writer.artifacts.answer}
        - {ref: reviewer.output}
```

The writer must publish the declared `answer` using the SDK `artifact_publish` tool. The consumer starts when both producers succeed and their requested members exist. Explicit `{ref: ...}` objects may be nested in mappings and lists; plain strings are data. Resolution uses the current run, problem and round and records exact producer invocation and member bindings. Ambiguous matches are rejected rather than choosing a global latest result. An upstream failure or missing member fails the affected node.

```python
from dispatcher_sdk.agents import AgentApp, ApplicationSpec

spec = ApplicationSpec.from_yaml("graph-agents.yaml")
with AgentApp(spec, state_dir="./agent-state") as app:
    root = app.seed("Prepare a response to the task.")
    print(root.wait(timeout=120))       # root output only
    print(root.run.wait(timeout=300))   # waits for the graph; returns root output
    for invocation in root.run.invocations:
        print(invocation.snapshot)     # includes exact producer bindings
    print(root.run.usage)              # agent calls and model turns
```

`Invocation.wait()` waits for that invocation only; `AgentRun.wait()` waits for the graph, returns the root output on success, and raises on graph failure, cancellation, recovery-required state or timeout. `AgentRun.invocations` returns invocation handles and `AgentRun.usage` returns run-level agent-call and model-turn accounting. A wait timeout does not extend the budget. YAML is optional; Python definitions are also supported.

Caller wait admission uses the original absolute `wait(timeout)` deadline for the application lock, Kernel control/read locks and AgentStore writer/commit contention. A confirmed SQLite BUSY commit retries the same transaction, without replaying its body. Expiry rolls back a confirmed uncommitted transaction; uncertain commits retain their recovery fence. These are admission and precommit bounds, not OS syscall preemption or a verified deadline guarantee for every storage and coordination path. Wait timeout does not cancel or resubmit the execution. The original caller cutoff also bounds Orchestrator connection configuration, writer admission and confirmed uncommitted BUSY commit retries, and AgentStore connection-configuration contention. The full wait path remains under verification.

The third isolated-wheel candidate reported G02–G04 passed on Linux x86_64, Python 3.12 and OpenCode 1.18.32. In a real `seed → fast + slow → consumer` run, a host gate held slow while the consumer remained unstarted; after release, the consumer read the `FAST_NATIVE` file snapshot and `SLOW_NATIVE` artifact and published `FAST_NATIVE|SLOW_NATIVE`. All four invocations shared one SDK Run, with 4 agent calls and 15 inference requests. Replaying the stable ID added no execution, while conflicting content was rejected. The file-tool diagnostics recorded failures, but did not retain the attempted paths needed to independently match both requested traversal and symlink denials. In a direct file-tool directory-swap race with 62 substitutions, all 500 operations failed closed, leaving the external file unchanged; allowed file writes were demonstrated in separate model calls. This candidate covers only its recorded scenarios; later evidence and current acceptance limits are in the [acceptance index](../docs/SDK_0_8_0_AGENT_CONTROL_ACCEPTANCE.md).

The verifier for isolated-wheel candidate 05 reported G01, G02, G03, G04, G08, G11 and G13 passed on Linux x86_64, Python 3.12.3 and OpenCode 1.18.32. G01 checked configuration; G02, G03, G04, G08 and G11 used real model execution. The historical G03 report did not retain the requested denial paths, and G04 did not demonstrate duplicate dependency-event delivery; neither report alone establishes full current acceptance. G13 covers the capability contract and refusal only: no native strict backend or real isolation has been accepted. The source-level admission primitive and controller landed after this package was built and are not G07 or G17 acceptance evidence. See the [acceptance index](../docs/SDK_0_8_0_AGENT_CONTROL_ACCEPTANCE.md) for later evidence and remaining limits.

## Agent calls and request scope in current source

When declared access enables coordination, the current source uses a conditional SDK controller and exposes `agent_call`, `agent_send` and `agent_wait` alongside `agent_context`. `agent_call` and `agent_send` accept exactly `agent`, `input` and a stable `request_id`; the ID is scoped to the calling invocation. Reusing it with the same input returns the same child; changed input is rejected. `agent_call` waits for the result, while `agent_send` leaves it in the original Run and budget. `agent_wait` accepts an invocation ID and only waits for an authorized invocation in the same Run. `agent_context({})` returns the caller's SDK-bound role, invocation, Run, problem, round, depth, tags and status; extra arguments are rejected. Caller identity is supplied by the SDK, not by tool arguments.

Grants are incoming on the **target**: `access.invoke` and `access.send` list caller roles or explicit `*`. A call implicitly permits the caller to read its result; `access.read_artifacts` grants other declared caller roles permission to wait for and read that target's result. These are independent grants. The ordinary, unrecovered SDK admission effect precedes use of the actual controller lease and caller-derived budget. The controller's Kernel parent is distinct from the logical Agent parent. Ancestor call and model-turn quotas and depth limits can only tighten along the chain; child calls do not reset them. Cancellation follows the precise logical subtree, including projection of external SDK revocation.

A waiting call yields its active slot while retaining its session and memory reservation. The active admission limit applies to all model work, including across configuration updates, and defaults to 4. The host has 64 fixed SDK-child waiter slots as a technical limit. A resource wait cycle fails with `agent_capacity_deadlock`; a direct wait cycle fails with `agent_wait_cycle`. The current source applies `concurrency.agent` and declared `resources.memory` capacity and per-agent reservations in an in-process admission pool. Memory admission is disabled by default. A waiting parent retains its reservation; if retained predecessors make a child impossible to admit, the wait returns `agent_memory_deadlock` and the accepted child stays queued until actual parent cleanup. Changing host memory capacity or role limits requires closing and reopening the host. The durable resource ownership ledger restores prior unknown claims, including those from closed plans. Queued work can reopen with matching limits; incompatible original limits are rejected. Capacity is released after exact native cleanup and local tools, proxy, observer and registered workers have quiesced. A late cleanup can release capacity while the business outcome remains unknown. These source-level controls do not establish G14, G16 or G17 acceptance. Dynamic groups, explicit rework, services, CLI operations and supervision remain incomplete and are not fully accepted. Candidate 07 native G07 passed; this evidence does not establish G14, G16 or G17 acceptance.

Candidate 07 passed native G02 and G07 with three model invocations in one SDK Run: call/send/wait and stable replay produced `CALL_NATIVE|SEND_NATIVE`, with the original permission and cycle errors, controller lease and limits, and caller admission effects checked. It includes the resource wiring but predates the experimental source group tools. Candidate 06 G07 failed on an exact artifact mismatch caused by added quotation marks; that result remains failed. See the acceptance index for scope.

Current source exposes experimental `agent_group_open`, `agent_group_send`, `agent_group_close`, `agent_group_wait`, `agent_group_call` and `agent_group_rework`, with SDK receipt checks, ordered exact members and consumer bindings. Explicit rework opens the next group round and freezes prior feedback. The next review uses the same frozen reviewer role and logical reviewer ID, but a new invocation and native session; this does not establish native session continuity. Waiting on an empty group is allowed; an empty consumer or rework is rejected. New late additions and a second successor are rejected before an SDK effect is created. Synthetic-adapter SDK integration, lifetime, authority and rework tests have passed; candidate 08 native G05 and G06 failed at the original 600-second deadline while the second reviewer was running. Candidate 09 also failed because coder adapter overlap was not observed, despite successful workflow invocations and correct feedback and bindings. Candidate 07 predates the group source.


`agent_rework(group_id, review_invocation_id, member_invocation_id, request_id)` uses the completed reviewer's frozen `recovery.rework` role. The owner must name one exact successful member of its closed source group that has that role; the target must be a callable task and separately authorize the owner through `access.send`. The route returns `{group_id, invocation_id}` for an open successor group containing the selected member. Its original input and exact versioned review feedback are frozen into the new round; the caller closes the group and requests the next review explicitly. Null configuration grants no route. A stable request replays the same group and child, including an interruption between their separate SDK effects; changed member or content conflicts. Unknown commits stay unknown, with no inferred rollback or automatic business retry. Ordinary group APIs keep their request namespace. Current source integration passed with an authenticated loopback runtime, and candidate 24 installed SDK route tests passed. Candidate 33 passed a real OpenCode route scenario on Linux x64 with exact member feedback and reviewer consumption; current-candidate acceptance remains open.

## Experimental task instances and sessions

Task invocations with nondefault `instance`, `session`, or `mailbox` settings use the task instance registry for both host-submitted roots and Agent-created nodes. The default task behavior remains invocation-local. `instance.mode: per_task` creates a fresh instance per invocation; `fixed` uses one instance per role and frozen configuration epoch; `keyed` selects an instance using the exact nonempty top-level input field named by `instance.key`. Each configuration transition gets a new epoch, including A → B → A; accepted calls keep their original binding.

Within an instance, `session.mode: problem` scopes a session to the problem, `new` creates one per invocation, and `keyed` uses the input field named by `session.key` or a host-supplied `session_key`. If both are supplied, they must match. Sessions are scoped to the instance: keyed sessions cannot bridge fresh `per_task` instances, so cross-invocation continuity requires a fixed or keyed instance. Fixed and keyed instances have a private instance workspace shared by their sessions, while native runtime state is separate per session scope. All sessions of one instance serialize to one writer; distinct keyed instances can run in parallel.

A non-null `instance.key` requires `instance.mode: keyed`. For tasks, a non-null `session.key` requires `session.mode: keyed`; other combinations are rejected at admission.

Task mailboxes support `queue`, `reject`, `replace_pending`, and `cancel_and_replace`. Root and node bindings are persisted with admission. A child cannot replace pending work or cancel an owner until its original ordinary SDK admission is verified; uncertain admission blocks conservatively. FIFO waiting and expiry use the original Run, deadline and budget, with no implicit extension. A same-instance synchronous recursive wait is rejected; an asynchronous send can queue until the writer has finished and its cleanup is confirmed. An unknown effect keeps the instance quarantined even if native process cleanup is confirmed.

`Invocation.snapshot["instance"]` exposes the task or explicit service binding, otherwise `None`; `agent_context` reports the bound `instance_id` and `session_scope_id`. Writable workspace grants and their limits are described above. Service instance behavior is described below. Candidate 17 passed real OpenCode fixed-instance A/B/A session identity, FIFO, workspace and restart paths, plus independent keyed instances with new native sessions. A fresh challenge supplied only in the first conversation was recalled by the third invocation and again after host reopen; it was absent from observed SDK workspace file calls and declared artifacts. The aggregate installed SDK tests contained one replay error; the focused three-case diagnostic run later passed without a confirmed cause, so complete regression and G18 acceptance remain pending.

## Experimental services

Host-submitted service roots support `problem` (default), `keyed`, and `new` sessions. Problem and keyed sessions require a nonempty `session_key`, either supplied to the call or taken from the exact top-level input field named by `session.key`; when both are supplied for a new request, their values must match. New sessions reject a host-supplied key. `trigger.mode: message` is accepted for services. Nested Agent-tool service calls currently return `agent_service_session_required`.

Service storage is Agent-owned schema 4, with one durable service identity per role. Each admitted configuration transition advances the role epoch, including A → B → A. Stable request replay keeps its original config, instance/session binding, deadline and budget; each request has its own finite SDK Run. The default `instance.mode: per_task` retains the existing session-scoped service behavior and directories. Explicit `fixed` uses one writable instance per role/configuration epoch; `keyed` selects an instance from the nonempty top-level input field named by `instance.key`. All sessions of that instance share its private workspace and serialize in instance-wide FIFO order; native conversation IDs and runtime state remain separate per session. Distinct keyed instances can proceed independently. `Invocation.snapshot["instance"]` exposes the explicit service binding, including `instance_owner` and `instance_quarantined`; it remains `None` for default service sessions. `agent_context` reports the bound instance and session IDs.

Mailbox capacity and replacement remain scoped to a session. `cancel_and_replace` cancels only that session's owner and pending work, even when another session owns the shared instance. Stop/resume and their control generation remain role-wide across every instance and epoch. A definite completion releases ownership only after exact SDK execution/effect and local/durable resource cleanup checks; an uncertain business effect quarantines the whole instance across reopen. Automatic schedule/state triggers accept default or fixed service instances; keyed instances need an explicit submission carrying their input key. Source SDK integration covers fixed/keyed instances, retained unknown ownership and live-resource cleanup. Candidate 25 passed five native fixed-instance checks on Linux x64 / Python 3.12.3 / OpenCode 1.18.32: queued work has no execution or charge, the predecessor has exact cleanup and a successful SDK finish before the next entry, sessions share workspace files but retain separate native identities, and close/reopen replay preserves identity and usage without a new entry. Three actual invocations use three finite original Runs; session A resumes after reopen. A separate candidate 25 keyed slice passed six native checks: X sessions serialize over the shared workspace, Y completes independently while X is held at entry, and reopen preserves exact replay and session continuation across four finite Runs. These service scripts did not inspect the SDK envelope absolute cutoff; a separate rework run exposed an approximately 74-microsecond extension that remains under repair. The service results do not establish that budget boundary, dialogue recall, provider concurrency, process crash recovery or full Goal acceptance. Candidate 25 also passed 62 installed SDK integration tests covering service instances, explicit upgrades, goal, task instances and workspaces, without skips; the complete regression and platform matrix remain pending.

Older service schema 2 or 3 is refused before host initialization writes. Stop the host and explicitly call `upgrade_service_store(state_dir, from_version=2)` (or `3`), or run `dispatcher-agents upgrade-service-store --state-dir DIR --from-version 3`. The API takes the same exclusive host lock and upgrades the Agent control sidecar in one transaction. IDs, stopped/control state, old session/native paths, queued bindings, owners and quarantine survive; legacy sessions receive no new instance binding. The upgrade does not modify SDK stores or reset budgets. Unknown/partial schemas fail, and an active host prevents upgrade. This is a structural upgrade, not proof that an unknown execution can resume.

For an older control store, confirm the host has stopped, then run `dispatcher-agents upgrade-dependency-store --state-dir DIR --from-version 1`. Existing plans retain scanning; new plans use event delivery. The upgrade does not modify SDK stores. `dispatcher-agents inspect-dependency-store --state-dir DIR` reports plan-mode counts, unsealed events and unacknowledged receipts and checks selected structural relationships. Its read-only snapshot does not prove that the host is stopped or that all data is healthy. Both commands require a private host state directory. Actual SDK execution of upgraded plans, complete upgrade compatibility and cross-platform behavior remain unaccepted in the current source. Close waits for delivery already in progress; unclaimed receipts remain for recovery at the next start. Acknowledged delivery does not prove the Agent executed successfully.

Use `app.service_status(name)`, `app.stop_service(name, mode="drain" | "cancel")`, and `app.resume_service(name)` for host service state. Drain stops admission while accepted work completes; cancel persists cancellation. The foreground CLI host is available in current source. Candidate 10 passed a real G10 scenario covering CLI/host operation, same-key native session continuity, independent Runs, restart, queued work in the observed crash window, and cross-Run cancellation. Candidate 17 passed all five real G09 mailbox scenarios: FIFO with two concurrent host callers and two queued messages, queue-full, reject, pending replacement, prelaunch cancellation and replacement, and post-send unknown quarantine. Ordinary runtime effects and final SDK receipts were matched to exact invocations, and authenticated native cleanup was verified. Local cleanup preserves unknown business outcomes. Candidate 10 G10 predates later guard, supervision and retained-service-stop fixes; final-candidate G10 and G18 acceptance remain pending.

## Goal completion

Set `completion.mode` to `goal` and `completion.validator` to a name registered by the host. The host supplies trusted callables through `AgentApp(..., validators={"check": check})`, or registers them in a `ValidatorRegistry` and passes the registry. Configuration selects a name; it does not execute an expression. The callable receives a `ValidationContext` with execution identity and copied response and artifact snapshots, and returns `ValidationResult("passed")`, `ValidationResult("continue", feedback)`, or `ValidationResult("blocked", feedback)`; feedback must be JSON.

A `continue` verdict starts another step with validator feedback in the same invocation, session, runtime state, deadline, frozen configuration and root budget. A `passed` verdict succeeds once required outputs exist; if outputs are missing, execution continues. Each step gets a fresh tool endpoint. Goal artifact versions are retained immutably by host step; `invocation.artifact_history(name)` returns committed version, host step and value facts, including versions of an incomplete goal. Downstream artifact bindings record the final successful producer version.

A `blocked` verdict maps to a failed Agent invocation with outcome `blocked` and failure code `goal_blocked`; it does not satisfy downstream dependencies. Validator exceptions and invalid results produce distinct safe failure codes without exposing exception details. A response-mode configuration with a validator is rejected. Goal admission rejects an unregistered validator or an adapter that does not declare same-session resume support before execution. Unknown execution effects are not blindly replayed. Candidate 05 G08 exercised same-session continue → passed with immutable step artifacts; blocked and validator-error cases failed without downstream success.

## Knowledge and configuration versions

`AgentApp` provides a host-owned `knowledge_store` (`KnowledgeStore`) and gives each invocation the `knowledge_read` and `knowledge_write` tools. Configure `knowledge.read` and `knowledge.write` as independent lists of exact namespace names; a write grant does not imply read permission, or vice versa. Names are opaque ASCII identifiers, not paths or wildcard patterns. The scoped tool checks the invocation's frozen grants and active authority. Host calls to `app.knowledge_store` are administrative operations, outside those scoped grants.

Knowledge values are JSON. `read(name)` returns the latest `{name, version, value}`, and `read(name, version)` reads an immutable historical version. `commit(name, value, expected_version)` uses compare-and-swap: use `None` for initial creation and the exact current version for an update. A conflict raises `KnowledgeConflictError` without overwriting history; each successful namespace version starts at 1 and increments. The corresponding tools accept `name`, optional `version` for reads, and `name`, `value`, `expected_version` for writes. Scoped permission and version conflicts are reported as tool errors. `ScopedKnowledge` implements the bound checks; it is available from `dispatcher_sdk.agents.knowledge`.

Host cancellation and close serialize with knowledge admission. A separately initiated Kernel revocation can still race a commit already admitted in the separate knowledge store: cancellation or an unknown response does not prove rollback. Inspect the durable namespace version and value before deciding what to do; do not blindly replay the write.

`app.update_config(new_spec)` activates a frozen configuration version for future requests, leaving existing plans and their prompt contents unchanged. Changing application worker capacity, memory capacity or role limits requires closing and reopening the host, subject to the unfinished-plan restriction above. Activation and each new admission capture **all** declared roles' `soul` and `prompt` source contents, including roles outside the selected graph. If any declared source is missing or unreadable, the new activation or admission fails. Existing frozen request replay and recovery do not depend on those source files remaining available. Relative source paths are resolved against `base_dir`.

Every newly staged Agent or controller SDK command also carries the exact frozen absolute `deadline_at`; coordinated children inherit their own frozen cutoff. Queueing, entry and reopen cannot turn remaining duration into a later SDK deadline. Unfinished work from experimental candidates that staged relative-only commands is refused before dispatch; its commands and receipts are preserved. Closed legacy requests may replay only after the exact public SDK command is confirmed terminal. Ordinary legacy SDK commands outside AgentApp retain their existing relative timeout behavior.

## Complete default registry

Historical observation-reads candidate evidence: the installed-package impact run passed 69 of 74 tests, with three wait errors and two child-test import failures. The import paths were corrected and those two tests passed separately in the same isolated installation; that does not replace the failed combined result. Unexpected waits retain pre-close thread evidence, and their common cause remains unproven. See the [current acceptance record](../docs/SDK_0_8_0_CURRENT_ACCEPTANCE.md) for subsequent fixes, current evidence and package boundaries.

`recovery.cancel_grace_seconds` defaults to `2` and accepts non-negative integer seconds; `0` requests immediate SDK cancellation. Explicit cancellation lets an exact current local handler settle for at most this interval, bounded by the original request deadline. Tools and new model/native starts remain denied. The interval starts at the first host observation and is not reset by polling; absent or changed ownership, restart, permission revocation, host closing and deadline expiry do not receive this grace. A returned result still projects the Agent as cancelled. Unknown effects or cleanup retain recovery/quarantine; grace alone never proves safe service reuse.

`recovery.technical_retries` defaults to `0` and accepts at most `16` extra attempts across the whole invocation, including all goal steps. OpenCode retries require a durable `not_launched` record for the exact prelaunch attempt. A transient error while creating the private runtime work directory can be retried when that proof is confirmed. Control-channel acquisition is retried only when cleanup is proved: a socket factory can acquire a resource and then raise without returning its handle. Such an ambiguous acquisition remains unknown and prevents retry, including for a transient error; the error number alone is insufficient proof. The host rechecks the original SDK lease/effect identity, deadline, shared and ancestor model-turn budgets, and proxy/tool/worker quiescence before continuing. Each retry uses a fresh tool authority but the same invocation, SDK effect, session, workspace and frozen budget; no extra Agent call is charged. Successful metadata records `technical_retries`. Exhausted or nontransient proven prelaunch failures settle as failures; missing or stale proof and unknown cleanup remain unknown. HTTP/provider errors, attempted process creation, guard startup, timeout and possibly submitted requests are never retried by this setting. A crash during the runtime effect does not resume the loop blindly. Adapters must declare `technical_retries: verified_native_prelaunch`; declaration alone does not substitute for the ownership proof. `recovery.rework` defaults to null. A configured target is used only by the explicit `agent_rework` route described below; ordinary reviewer rejection never triggers it automatically. Candidate 20 passed an installed real OpenCode 1.18.32 prelaunch-retry case on Linux x64 / Python 3.12.3, on an earlier candidate; its result is historical and does not prove current retry behavior or cross-platform support.

`runtime.fallbacks` defaults to `[]`. In current source it is an ordered list of explicit `provider/model` candidates used only when the trusted host declares an earlier candidate locally unavailable before any proxy or native process starts. Configure `OpenCodeAdapter(..., unavailable_models=["provider/primary"], host_tools_revision="runtime-v1", provider_config=...)`, or repeat `serve --unavailable-model provider/primary`. Every primary/fallback requires an explicit entry in the private host provider model catalog and a nonempty immutable revision. All candidate providers, credentials and requested reasoning variants are validated before selection, including unavailable candidates; missing credentials or invalid options do not mean unavailable. The first locally available model is selected deterministically under the frozen configuration and host revision, and successful metadata records `selected_model`. Change the revision whenever availability changes. The original request keeps its primary/fallback declaration. HTTP failures, timeouts, process failures and unknown submitted results never switch models. This is explicit local selection, with no provider health probing. Candidate 20 passed installed tests and two real OpenCode 1.18.32 calls on Linux x64 / Python 3.12.3 using a host-declared unavailable fixture primary and the real fallback. Host reopen preserved the keyed session and stable replay issued no provider request; both ordinary SDK effects and exact native cleanup were verified. This establishes local selection, not automatic provider outage detection or cross-platform acceptance.

`runtime.reasoning` selects an exact host-declared model variant; it defaults to null. Current OpenAI-compatible support accepts only `{reasoningEffort: low|medium|high}`. Unknown/unsupported options, Anthropic variants and dot-containing provider IDs fail before startup. Host `provider_config` declares `models.MODEL.variants.NAME`; a nonempty immutable `host_tools_revision` covers those options too. CLI hosts pass `--host-tools-revision VERSION` with their private provider JSON. Candidate 19 verified actual `reasoningEffort: low` transmission and exact SDK completion/cleanup on Linux x64 / Python 3.12.3 / OpenCode 1.18.32. Medium/high have not been separately exercised; transmission does not prove provider reasoning behavior.

Automatic foreground triggers now have explicit `interval_seconds: null` and `session_key: null` defaults. Schedule mode requires a positive interval, waits for the next UTC Unix-epoch boundary on first activation, and coalesces missed slots to the latest elapsed slot. State mode requires exact selectors such as `[source.succeeded]` for terminal finite root SDK Runs, using the original public finish receipt; it excludes prior history at epoch installation and deduplicates restart delivery. Each occurrence gets an independent Run with an atomically persisted root/event binding and frozen original budget. State-trigger cycles and incompatible keyed task targets are rejected. Continuing services require explicit `trigger.session_key`; new sessions reject it.

Use `app.triggers_status()` or the equivalent client API to inspect targets, the durable paused flag and the latest 100 occurrence identities, then normal invocation APIs for each result. `pause_triggers()` and `resume_triggers()` control admission; CLI `status|stop|resume --triggers` is mutually exclusive with `--agent`. Whole-host stop persists the pause, and restart does not resume it. Accepted work retains its original budget, and paused recovery does not require future prompt sources. The [detailed guide](../docs/AGENT_CONTROL.md) defines payloads, epoch changes and limitations. Candidate 19 passed actual OpenCode state and schedule cases (14 and 13 checks), covering exact provenance, original budgets, deduplication, pause/reopen and authenticated cleanup. Full G18 regression and platform coverage remain pending.

These are the complete per-agent schema 1 defaults. Parsing a field does not imply runtime support for all its values.

```json
{
  "tags": [],
  "soul": null,
  "prompt": null,
  "runtime": {
    "name": "opencode",
    "model": null,
    "reasoning": null,
    "fallbacks": []
  },
  "lifetime": "task",
  "instance": {
    "mode": "per_task",
    "key": null
  },
  "trigger": {
    "mode": "inputs_ready",
    "events": [],
    "interval_seconds": null,
    "session_key": null
  },
  "session": {
    "mode": "problem",
    "key": null
  },
  "mailbox": {
    "capacity": 100,
    "policy": "queue"
  },
  "concurrency": {
    "application": 4,
    "agent": null,
    "session": 1
  },
  "resources": {
    "memory": {
      "capacity_bytes": null,
      "reservation_bytes": null
    }
  },
  "access": {
    "invoke": [],
    "send": [],
    "read_artifacts": [],
    "cancel": [],
    "resume": []
  },
  "files": {
    "mode": "tools",
    "read": [],
    "write": [],
    "shared_read": []
  },
  "tools": {
    "shell": false,
    "mcp": [],
    "network": false
  },
  "workspace": {
    "mode": "private",
    "path": null,
    "shared": []
  },
  "completion": {
    "mode": "response",
    "validator": null
  },
  "output": {
    "required": [],
    "declared": {}
  },
  "budget": {
    "seconds": 3600,
    "agent_calls": 64,
    "model_turns": 128,
    "tokens": null,
    "call_depth": 8
  },
  "recovery": {
    "technical_retries": 0,
    "cancel_grace_seconds": 2,
    "rework": null
  },
  "supervision": {
    "enabled": false,
    "interval_seconds": null,
    "metrics": [],
    "diagnostic_agent": null,
    "actions": []
  },
  "knowledge": {
    "read": [],
    "write": []
  },
  "service_stop": {
    "mode": "drain"
  },
  "dependencies": [],
  "inputs": {}
}
```

The Linux subreaper guard has passed process and synthetic protocol tests. Candidate 11 G02 also passed with real OpenCode and authenticated cleanup readback for the exact SDK generation; broader guard fault acceptance remains incomplete. Its `ECHILD` receipt proves process cleanup, not the model effect outcome or strict isolation. The source supervision ledger and diagnostic admission path passed a real SDK test with a synthetic adapter. Candidate 34 passed bounded native supervision trigger, stale, disabled and stop scenarios on Linux x64; complete current-candidate G17 and other-platform acceptance remain open.


Candidate 15 passed native G05/G06 with two overlapping coders in each round, explicit rework, the same logical reviewer consuming new results, exact bindings and original budgets. The unclosed-group negative used the actual returned group ID and was rejected. Earlier failed candidates remain recorded in the acceptance index; this evidence does not complete the overall Goal.

## Agent control permissions

`access.cancel` and `access.resume` are incoming role grants and default to empty. `agent_cancel(invocation_id, request_id)` accepts an authorized proper descendant in the same Run/root/problem; self, ancestors, siblings and other Runs are denied. `agent_resume(agent, request_id)` reopens admission globally for an established service role, requiring both frozen and current host permission. It never clears cancelled calls or quarantined sessions.

Identity and budget come from the actual SDK caller. The exact original committed `agent.control.admission` receipt authorizes projection. Applied confirms the request, not process cleanup. A stable request ID can be replayed; changed operation/target conflicts, and an applied resume cannot undo a later host stop. A new explicit request is required. The current service registry is schema 4; explicit stopped-host upgrades from schema 2 or 3 are described above. Reopen checks the original deadline, lease/fence and budget; external SDK revocation and the Agent-store action are not one atomic transaction. Current-source real SDK/loopback tests passed the bounded control paths. Candidate 23 passed 13 checks with real OpenCode 1.18.32 on Linux x64 / Python 3.12.3: actual self-denial without an effect, service resume and exact replay across a later host stop, a new explicit resume, same-key session continuity, unchanged original budgets across three independent Runs, and authenticated cleanup. This does not establish native descendant cancellation, control crash/reopen or full G16/G18 acceptance.


Host role revocation uses `app.revoke_permissions("worker", request_id="revoke-1", reason="host decision")`, `app.permissions_status("worker")`, and `app.restore_permissions("worker", request_id="restore-1")`; authenticated `AgentClient` provides the same methods. CLI equivalents are `revoke-permissions`, `permissions-status`, and `restore-permissions`, each with `--state-dir DIR --agent worker`; decisions require `--request-id`, and revocation optionally accepts `--reason`. These are host administration operations, not model tools.

The default is allowed with generation `0`, still subject to the configured incoming access grants. Revocation persistently denies new role admissions and cancels unfinished matching invocations and their delegated descendants across open Runs, including live children of completed parents; completed results and unrelated roles are preserved. Invocation status exposes `permission_revocation` with the deciding request ID, role, generation and optional reason. SDK cancellation and native cleanup are separate facts, and an uncertain effect remains uncertain. Restore allows future admissions only; it never resumes cancelled work or clears quarantined ownership, stopped services or paused triggers. Config updates, service resume and host restart do not erase the decision. Exact request replay returns its original receipt without applying an old decision over a newer one; conflicting contents raise an error. Administrative decision IDs are unique across the state directory. Role and decision IDs are nonempty strings of at most 256 characters; an optional reason is a nonempty string of at most 4096 characters; NUL is rejected. Active calls retain their frozen configuration and original budget. These operations revoke the role's invocation authority; they do not selectively edit its frozen file/tool grants.


### Installed CLI lifecycle verification

Run `python -I /absolute/path/scripts/verify_agent_cli_lifecycle.py --output /new/private/evidence-directory` with the installed candidate interpreter and the optional YAML dependency. The verifier starts a real idle `serve` process and checks effective configuration, service and trigger admission controls, status readback, and clean host exit. It does not submit model work or prove cross-Run session continuity. The output directory must not already exist; `report.json` retains command results and any fallback cleanup.
