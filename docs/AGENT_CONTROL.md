# Experimental Agent Control (0.8.0)

> This guide documents the local 0.8.0 development candidate. The implementation is still on the local development branch.

Pending child-result observation starts with a 50 ms sleep and backs off to at most 500 ms while the durable state and diagnostic are unchanged; a change resets the sleep to 50 ms. Each pending observation retains its authority checks and fresh budget sample, and sleep never exceeds the original remaining work window. Result and cancellation observation may therefore take up to 500 ms plus operation and scheduling time; this is not a new execution allowance. Already recorded result delivery retains its existing read-before-sample and factual-delivery rules.


After an invocation's original host deadline, `Invocation.wait()` and `AgentRun.wait()` may raise `AgentExecutionError` with `completion_state="unknown"` when bounded inspection finds a pending late fact for the exact current execution, attempt, fence and lease. The exception snapshot preserves the actual invocation and execution states; it does not label them completed, cancelled or recovery-required. This reports uncertainty at observation time: a valid result can arrive afterward. It grants no retry, cleanup, result-publication or extra budget authority. A confirmed terminal result takes precedence. Missing, stale, oversized, busy or incomplete evidence retains normal waiting and may still end in `TimeoutError`; this is a best-effort observation, not a guarantee that every uncertain execution will be detected. Inspection shares the original caller wait deadline, uses a combined 50 ms probe window and runs at most once per 250 ms; Run probes rotate across eligible invocations.


This describes the experimental 0.8.0 API. The implementation includes task and service invocations, automatic dependencies, dynamic groups, explicit rework, goal validation, session continuation, and persistent recovery interfaces. G17 has legacy API, CLI, supervision and resource admission evidence on the prior installed candidate. G18 remains open for installed-package regression, the platform matrix and final package and document alignment. See the [current acceptance record](SDK_0_8_0_CURRENT_ACCEPTANCE.md) for candidate-specific evidence and limits. Configuration parsing alone does not establish runtime support; unsupported settings are rejected during admission or by the adapter.

## Setup and first invocation

Install the package with its optional YAML dependency (`pip install 'dispatcher-sdk[agents]'`), provide an `opencode` executable on PATH, configure `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in the host environment, and choose an available `anthropic/...` or `openai/...` model. Optional provider endpoint variables are `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL`. The default adapter reads the selected provider's environment; do not place credentials in YAML. Current source implements a Windows host lock and Job Object native guard in addition to the Linux host and subreaper guard. The Windows implementation has not been validated on native Windows; historical native evidence is Linux-only and cross-platform acceptance remains incomplete. A model must be configured before invocation; model availability and credentials are host-specific.

Save a configuration as `agents.yaml`:

```yaml
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
    invocation = app.coder("Explain what this SDK does.")
    print(invocation.request_id)
    print(invocation.wait(timeout=120))
```

The equivalent Python configuration is:

```python
from dispatcher_sdk.agents import AgentSpec, ApplicationSpec

spec = ApplicationSpec(
    {"coder": AgentSpec("coder")},
    defaults={"runtime": {"model": "openai/YOUR_MODEL_ID"}},
)
```

The call can also be written `app.agent("coder")("Explain what this SDK does.")`. Use `app.agent(name)` for names containing hyphens, starting with underscores, or matching existing `AgentApp` attributes such as `start` or `close`. `state_dir` is host-owned and must not be group/world writable. `soul` and `prompt`, if provided, are file paths read relative to `base_dir` (current working directory by default); otherwise the invocation input must contain task instructions. `wait` waits for this invocation and returns its output or raises on failure, cancellation, unknown recovery, or timeout. The wait timeout is not the request budget. A generated `request_id` is exposed on the invocation; an explicit stable ID reuses the same logical invocation only for the same agent and input, and conflicting content raises an error. A successful `AgentApp.close()` stops its local host; it does not leave a durable service running. If cleanup is incomplete, close raises and the application retains ownership so cleanup can be retried.

To configure the runtime explicitly, import the public adapter module and pass the adapter to `AgentApp`. The constructor below retains the default tool grants; add host grants or provider options there when needed.

```python
from dispatcher_sdk.agents.opencode import OpenCodeAdapter

adapter = OpenCodeAdapter(executable="opencode")
with AgentApp(spec, state_dir="./agent-state", adapter=adapter) as app:
    print(app.coder("Explain the task.").wait(timeout=120))
```

## Configuration and defaults

`runtime.reasoning` defaults to null. It selects an exact named variant granted in the host-only provider configuration, for example `models: {"MODEL": {"variants": {"light": {"reasoningEffort": "low"}}}}`. With `runtime.model: provider/MODEL`, `runtime.reasoning: light` selects that variant. The current adapter accepts only OpenAI-compatible providers and the exact option `reasoningEffort: low|medium|high`; unsupported options, unknown variants and Anthropic variants fail before native startup. Provider IDs containing dots are unsupported for this mapping. Supply a nonempty immutable `host_tools_revision` when declaring variants, or `serve --host-tools-revision VERSION` with the private `--provider-config` JSON. The revision covers these model options as well as native grants; change it when the actual options change. The SDK transmits the configured parameter; the provider determines its model behavior. Candidate 19 verified that `reasoningEffort: low` reached the actual OpenCode provider request on Linux x64 / Python 3.12.3 / OpenCode 1.18.32, with ordinary SDK completion and exact authenticated cleanup. Medium/high transmission has not been separately exercised.

Known 0.8.0 worktree issue: a control-channel acquisition failure can currently remain cleanup-unknown and block the retry described below, even for an injected transient error. This is an unresolved release blocker; historical candidate evidence does not establish that the current code retries it.

`recovery.cancel_grace_seconds` defaults to `2` and accepts non-negative integer seconds; `0` requests immediate SDK cancellation. Explicit cancellation lets an exact current local handler settle for at most this interval, bounded by the original request deadline. Tools and new model/native starts remain denied. The interval starts at the first host observation and is not reset by polling; absent or changed ownership, restart, permission revocation, host closing and deadline expiry do not receive this grace. A returned result still projects the Agent as cancelled. Unknown effects or cleanup retain recovery/quarantine; grace alone never proves safe service reuse.

`recovery.technical_retries` defaults to `0` and accepts at most `16` extra attempts across the whole invocation, including all goal steps. OpenCode retries require a durable `not_launched` record for the exact prelaunch attempt. A transient error while creating the private runtime work directory can be retried when that proof is confirmed. **A current regression prevents reliable automatic retry of transient control-channel creation failures:** an interrupted socket acquisition can leave ownership unknown, so the SDK may decline to retry even for an otherwise transient error. The host rechecks the original SDK lease/effect identity, deadline, shared and ancestor model-turn budgets, and proxy/tool/worker quiescence before continuing. Each retry uses a fresh tool authority but the same invocation, SDK effect, session, workspace and frozen budget; no extra Agent call is charged. Successful metadata records `technical_retries`. Exhausted or nontransient proven prelaunch failures settle as failures; missing or stale proof and unknown cleanup remain unknown. HTTP/provider errors, attempted process creation, guard startup, timeout and possibly submitted requests are never retried by this setting. A crash during the runtime effect does not resume the loop blindly. Adapters must declare `technical_retries: verified_native_prelaunch`; declaration alone does not substitute for the ownership proof. `recovery.rework` defaults to null. A configured target is used only by the explicit `agent_rework` route described below; ordinary reviewer rejection never triggers it automatically. Candidate 20 passed an installed real OpenCode 1.18.32 prelaunch-retry case on Linux x64 / Python 3.12.3, before the current regression; its result is historical and does not prove current retry behavior or cross-platform support.

`runtime.fallbacks` defaults to `[]`. In current source it is an ordered list of explicit `provider/model` candidates used only when the trusted host declares an earlier candidate locally unavailable before any proxy or native process starts. Configure `OpenCodeAdapter(..., unavailable_models=["provider/primary"], host_tools_revision="runtime-v1", provider_config=...)`, or repeat `serve --unavailable-model provider/primary`. Every primary/fallback requires an explicit entry in the private host provider model catalog and a nonempty immutable revision. All candidate providers, credentials and requested reasoning variants are validated before selection, including unavailable candidates; missing credentials or invalid options do not mean unavailable. The first locally available model is selected deterministically under the frozen configuration and host revision, and successful metadata records `selected_model`. Change the revision whenever availability changes. The original request keeps its primary/fallback declaration. HTTP failures, timeouts, process failures and unknown submitted results never switch models. This is explicit local selection, with no provider health probing. Candidate 20 passed installed tests and two real OpenCode 1.18.32 calls on Linux x64 / Python 3.12.3 using a host-declared unavailable fixture primary and the real fallback. Host reopen preserved the keyed session and stable replay issued no provider request; both ordinary SDK effects and exact native cleanup were verified. This establishes local selection, not automatic provider outage detection or cross-platform acceptance.

Automatic admission runs only in the foreground host started by `AgentApp.start()`, context entry or a validated host invocation. `trigger.mode: schedule` requires positive integer `trigger.interval_seconds` (default null). Slots use UTC Unix epoch seconds: first activation waits for the next boundary; after downtime or a pause, the latest elapsed slot is coalesced into one occurrence. Earlier missed slots are skipped. A pump accepts at most one occurrence per target. `trigger.mode: state` requires exact `trigger.events` selectors such as `["source.succeeded"]`; supported states are `succeeded`, `failed` and `cancelled` of a finite **root SDK Run** whose entry role is `source`. These are not arbitrary child statuses. The source's original public SDK finish receipt supplies Run ID, root invocation ID, generation, revision and state. Preexisting finishes are excluded when a new trigger epoch is installed; sources already running at activation and finishes observed after a restart remain eligible. Repeated pumps do not emit the same occurrence twice. Self selectors, unknown roles, duplicate selectors and state-trigger cycles are rejected.

Each occurrence atomically records its root intent and stable event binding in Agent-owned storage before SDK submission. It creates an independent finite AgentRun with its own original deadline and budgets, and is recovered using the same IDs. Trigger metadata appears in the root input under `trigger`; it grants no access to source outputs, artifacts or credentials. A changed effective configuration/prompt/host revision creates a new trigger epoch for future occurrences; accepted roots retain their frozen plan. Task targets support per-task/fixed instances and problem/new sessions; keyed task instances/sessions need explicit host input and are rejected for automatic triggers. Continuing service targets require explicit `trigger.session_key` (default null), while `session.mode: new` rejects a key; input-field `session.key` is unsupported for automatic service targets. Existing mailbox, stop and quarantine policies still apply.

`app.triggers_status()` and `AgentClient.triggers_status()` return the paused flag, configured targets and at most the latest 100 occurrence identities. Pass an `invocation_id` to the normal invocation/status APIs to inspect its result. Generated request IDs use the reserved `agent-trigger:` prefix and cannot be submitted as manual host requests. `pause_triggers()` persists an admission pause without cancelling accepted work; `resume_triggers()` explicitly reactivates it after validating current source files. CLI equivalents are `status|stop|resume --state-dir DIR --triggers`, mutually exclusive with `--agent`. Whole-host stop pauses automatic admission before acknowledging, and restart preserves that pause. A paused host can recover existing frozen commands without rereading future trigger prompt files. Candidate 19 passed actual OpenCode state and schedule scenarios (14 and 13 checks), including exact root provenance, independent Run budgets, deduplication, durable schedule pause/reopen and authenticated cleanup. These cases do not replace full G18 regression or platform coverage.

On Windows, current source can construct an absolute private workspace with an empty file policy; SDK file read, list and write remain unimplemented and fail closed, and shared file roots are unsupported. No native Windows validation is claimed. The Windows hello and the operation-ready handshake each have their own maximum five-second window, capped by the original invocation deadline; socket I/O waits use slices of at most 0.1 seconds, with cancellation checked between slices. The read-only startup SQLite busy timeout is 0.05 seconds. These bounds do not limit arbitrary filesystem I/O, custom callbacks, later full SDK authorization, or overall startup or return latency. The guard cleanup wait is five seconds and the host guard wait is eight seconds; neither resolves an unknown business outcome.

Host-granted native tools are implemented in current source; their native evidence is currently limited to Linux. `OpenCodeAdapter(allow_shell=False, mcp_servers=None, host_tools_revision=None)` defaults to no shell and no external MCP servers. An Agent must separately request `tools.shell: true` or list exact server names in `tools.mcp`; the adapter rejects requests outside the host grants before admission. To grant either capability, the host must supply a nonempty `host_tools_revision`. Local MCP entries have `type: local`, a nonempty `command` argument list, and optional `environment` and `timeout` (1–300000 ms); names are at most 64 characters, use lowercase ASCII letters and digits, start with a letter, and cannot be `dispatcher`. Remote MCP is not supported. Grant only trusted commands and environment values; these execute as native host code.

The host must treat `host_tools_revision` as an immutable opaque identifier and change it whenever commands, environment values, grants, model variant options, or local model availability change. The SDK stores that value with frozen configurations and plans, rejects changed revisions when reopening unfinished plans, and rejects live revision drift. The SDK does not verify that the revision identifies the actual grant contents; reusing a revision for different contents defeats this safeguard. Shell and local MCP are not constrained by SDK file-tool path grants and are not a sandbox. Descendant process cleanup requires the corresponding native guard evidence; a cleanup receipt alone does not establish the model result. Candidate 16 passed separate normal-completion and cancellation scenarios with real OpenCode 1.18.32 on Linux x64 / Python 3.12.3: the model executed the authorized shell and local MCP tools, their fixture descendants were observed alive, and exact authenticated guard receipts confirmed cleanup. The normal effect committed and its required output matched. After cancellation the model effect remained indeterminate and the invocation remained recovery_required; cleanup does not resolve that outcome. Other platforms and broader capability fault cases remain unaccepted.

Read-only shared input needs an absolute `files.shared_read` grant and a separate host upper bound, supplied through `AgentApp(..., shared_roots=["/srv/agent-inputs"])` or repeated `dispatcher-agents serve ... --shared-root /srv/agent-inputs` options. Host roots default to empty; Agent configuration cannot enlarge them. Filesystem root, overlap with Agent state, traversal and symbolic-link components are rejected. `file_read`, `file_list` and file artifact publication share the same grants, and shared paths cannot be written. Hosts must keep the roots and ancestors stable and exclude unrelated secrets. This is a file-tool boundary. Writable workspaces use the separate ownership policy below. Candidate 15 passed real OpenCode shared reads, directory listing, denied writes and downstream consumption of the original file snapshot on Linux x86_64; full final-candidate acceptance remains incomplete.

Writable workspaces are supported in current source through explicit host grants: `AgentApp(..., workspace_roots=["/srv/work"], workspace_registry="/srv/agent-workspace-registry")`, or repeated `serve --workspace-root DIR` with `--workspace-registry DIR`. Both arguments default to no grant. The registry must already exist with mode `0700`, outside Agent state and every writable root; every cooperating host sharing those roots must use the same protected, stable registry and unaliased paths. Roots must be existing canonical directories without symlinks, cannot overlap state or registry, and cannot overlap one another. The host must prevent untrusted root/ancestor replacement and registry modification. Advisory ownership does not constrain uncooperative processes or native code.

`workspace.mode: private` remains the default, with `path: null` and `shared: []`. For `persistent`, set an absolute `workspace.path` beneath a host root; relative `files.read/write` grants apply there and contents survive invocations and host reopen. For `shared`, keep `path: null` and list absolute directories in `workspace.shared`; the primary workspace stays private, and each accessible shared file needs a separate **absolute** `files.read` or `files.write` grant. Relative grants apply only to the primary workspace. `files.shared_read` continues to grant reads only. The SDK conservatively serializes the entire containing host root, including sibling subdirectories and read-only invocations that select it. A dynamic child cannot select a root retained by an ancestor; admission reports `agent_workspace_ancestor_conflict` before creating its effect. Sequential downstream roles can use the root after the prior invocation releases ownership.

Ownership is reserved before the runtime effect or adapter starts and remains across goal steps and technical retries under the original deadline. Release requires local helper quiescence and exact original effect/native cleanup proof. Process death or deadline expiry never clears an unknown owner; only the original state host, holding its exclusive host lock, can reconcile exact cleanup evidence. A different state cannot recover that owner. Frozen plans retain exact host roots and registry; reopen with different grants is refused while plans remain unfinished. Nonprivate workspaces currently reject shell and external MCP tools because file-tool grants cannot protect the ownership registry from those tools. Candidate 24 passed seven checks using installed-package OpenCode 1.18.32 on Linux x64 / Python 3.12.3: persistent writes, reopen and stable replay, shared writes, denied outside/state writes, original artifact consumption after a deliberate host file change, original budgets and exact native cleanup. Source SDK integration also passed cancellation/unknown-owner and ancestor-conflict tests. This does not establish native crash recovery, concurrent-host exclusion or other platforms; final-candidate regression remains incomplete.

`ApplicationSpec.from_mapping`, `ApplicationSpec.from_yaml`, and the Python constructors use the same validation and produce the same effective shape via `to_dict()`. Mappings merge recursively, lists replace, omission inherits, and null is accepted only for explicitly nullable fields. Application `defaults` must be a mapping when supplied: omit it or use `{}` to inherit, rather than passing `null` or Python `None`. Unknown fields, duplicate YAML keys, invalid values, unknown role references and static dependency cycles are rejected. YAML uses the optional safe loader. `agent(name).to_dict()` returns the resolved settings without the name. The canonical schema version is `1`. The following is the complete default settings registry for each agent; `ApplicationSpec.to_dict()` contains these effective settings in `defaults` and under each name in `agents`:

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

`concurrency.application` and `resources.memory.capacity_bytes` are application-wide and belong in `defaults`. When memory admission is configured, every agent must declare a positive reservation and it may not exceed capacity. Local budget overrides may only tighten the application budget. The current source enforces these declarations through in-process admission; recovery restrictions are described below.

## Automatic dependency graphs

A host invocation starts one root and freezes the reachable `inputs_ready` graph before admission. A role becomes reachable through explicit dependencies or input references to an already reachable role. Every dependency of every selected role must be within that same graph; mixed-entry graphs that require another independent host root are rejected before admission. The host entry itself must have no Agent dependencies. The current graph has one invocation per role in round 0.

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

The writer must publish its declared `answer` using the SDK `artifact_publish` tool. The consumer starts only after both producers succeed and the requested members exist. Inputs can contain nested lists and mappings; only explicit objects such as `{"ref": "reviewer.output"}` and `{"ref": "writer.artifacts.answer"}` are resolved. Plain strings are data. The resolver also recognizes `status`, `progress` and `tags` members, subject to their availability. It uses the current run, problem and round, records exact producer invocation and member bindings, and rejects ambiguous matches instead of selecting a global latest result. An upstream failure or missing required member fails the affected node.

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

`Invocation.wait()` waits for that invocation only. `AgentRun.wait()` waits for the whole frozen graph, returns the root output on success, and raises on graph failure, cancellation, recovery-required state or timeout. `AgentRun.invocations` exposes the invocation handles and `AgentRun.usage` exposes run-level agent-call and model-turn accounting. A wait timeout does not extend the run budget. YAML is optional; `ApplicationSpec` also accepts Python definitions.

The verifier for isolated-wheel candidate 05 reported G01, G02, G03, G04, G08, G11 and G13 passed on Linux x86_64, Python 3.12.3 and OpenCode 1.18.32. G01 checked configuration; G02, G03, G04, G08 and G11 used real model execution. The historical G03 report did not retain the requested denial paths, and G04 did not demonstrate duplicate dependency-event delivery; neither report alone establishes full current acceptance. G13 covers the capability contract and refusal only: no native strict backend or real isolation has been accepted. The source-level admission primitive and controller landed after this package was built and are not G07 or G17 acceptance evidence. See the [acceptance index](SDK_0_8_0_AGENT_CONTROL_ACCEPTANCE.md) for later evidence and remaining limits.

## Agent calls and request scope in current source

When declared access enables coordination, the current source uses a conditional SDK controller and exposes `agent_call`, `agent_send` and `agent_wait` alongside `agent_context`. `agent_call` and `agent_send` accept exactly `agent`, `input` and a stable `request_id`; the ID is scoped to the calling invocation. Reusing it with the same input returns the same child; changed input is rejected. `agent_call` waits for the result, while `agent_send` leaves it in the original Run and budget. `agent_wait` accepts an invocation ID and only waits for an authorized invocation in the same Run. `agent_context({})` returns the caller's SDK-bound role, invocation, Run, problem, round, depth, tags and status; extra arguments are rejected. Caller identity is supplied by the SDK, not by tool arguments.

Grants are incoming on the **target**: `access.invoke` and `access.send` list caller roles or explicit `*`. A call implicitly permits the caller to read its result; `access.read_artifacts` grants other declared caller roles permission to wait for and read that target's result. These are independent grants. The ordinary, unrecovered SDK admission effect precedes use of the actual controller lease and caller-derived budget. The controller's Kernel parent is distinct from the logical Agent parent. Ancestor call and model-turn quotas and depth limits can only tighten along the chain; child calls do not reset them. Cancellation follows the precise logical subtree, including projection of external SDK revocation.

A waiting call yields its active slot while retaining its session and memory reservation. The active admission limit applies to all model work, including across configuration updates, and defaults to 4. The host has 64 fixed SDK-child waiter slots as a technical limit. A resource wait cycle fails with `agent_capacity_deadlock`; a direct wait cycle fails with `agent_wait_cycle`. The current source applies `concurrency.agent` and declared `resources.memory` capacity and per-agent reservations in an in-process admission pool. Memory admission is disabled by default. A waiting parent retains its reservation; if retained predecessors make a child impossible to admit, the wait returns `agent_memory_deadlock` and the accepted child stays queued until actual parent cleanup. Changing host memory capacity or role limits requires closing and reopening the host. The durable resource ownership ledger restores prior unknown claims, including those from closed plans. Queued work can reopen with matching limits; incompatible original limits are rejected. Capacity is released after exact native cleanup and local tools, proxy, observer and registered workers have quiesced. A late cleanup can release capacity while the business outcome remains unknown. These source-level controls do not establish G14, G16 or G17 acceptance. Dynamic groups, explicit rework, services, CLI operations and supervision remain incomplete and are not fully accepted. Candidate 07 native G07 passed; this evidence does not establish G14, G16 or G17 acceptance.

Candidate 07 passed native G02 and G07 with three model invocations in one SDK Run: call/send/wait and stable replay produced `CALL_NATIVE|SEND_NATIVE`, with the original permission and cycle errors, controller lease and limits, and caller admission effects checked. It includes the resource wiring but predates the experimental source group tools. Candidate 06 G07 failed on an exact artifact mismatch caused by added quotation marks; that result remains failed. See the acceptance index for scope.

Current source exposes experimental `agent_group_open`, `agent_group_send`, `agent_group_close`, `agent_group_wait`, `agent_group_call` and `agent_group_rework`, with SDK receipt checks, ordered exact members and consumer bindings. Explicit rework opens the next group round and freezes prior feedback. The next review uses the same frozen reviewer role and logical reviewer ID, but a new invocation and native session; this does not establish native session continuity. Waiting on an empty group is allowed; an empty consumer or rework is rejected. New late additions and a second successor are rejected before an SDK effect is created. Synthetic-adapter SDK integration, lifetime, authority and rework tests have passed; candidate 08 native G05 and G06 failed at the original 600-second deadline while the second reviewer was running; candidate 09 also failed because coder adapter overlap was not observed, despite successful workflow invocations and correct feedback and bindings; candidate 07 predates the group source. See the acceptance record for the exact outcome and retained evidence.


`agent_rework(group_id, review_invocation_id, member_invocation_id, request_id)` uses the completed reviewer's frozen `recovery.rework` role. The owner must name one exact successful member of its closed source group that has that role; the target must be a callable task and separately authorize the owner through `access.send`. The route returns `{group_id, invocation_id}` for an open successor group containing the selected member. Its original input and exact versioned review feedback are frozen into the new round; the caller closes the group and requests the next review explicitly. Null configuration grants no route. A stable request replays the same group and child, including an interruption between their separate SDK effects; changed member or content conflicts. Unknown commits stay unknown, with no inferred rollback or automatic business retry. Ordinary group APIs keep their request namespace. Current source integration passed with an authenticated loopback runtime; candidate 24 installed SDK route tests passed; native route validation remains pending.

## Experimental task instances and sessions

Task invocations with nondefault `instance`, `session`, or `mailbox` settings use the task instance registry for both host-submitted roots and Agent-created nodes. The default task behavior remains invocation-local. `instance.mode: per_task` creates a fresh instance per invocation; `fixed` uses one instance per role and frozen configuration epoch; `keyed` selects an instance using the exact nonempty top-level input field named by `instance.key`. Each configuration transition gets a new epoch, including A → B → A; accepted calls keep their original binding.

Within an instance, `session.mode: problem` scopes a session to the problem, `new` creates one per invocation, and `keyed` uses the input field named by `session.key` or a host-supplied `session_key`. If both are supplied, they must match. Sessions are scoped to the instance: keyed sessions cannot bridge fresh `per_task` instances, so cross-invocation continuity requires a fixed or keyed instance. Fixed and keyed instances have a private instance workspace shared by their sessions, while native runtime state is separate per session scope. All sessions of one instance serialize to one writer; distinct keyed instances can run in parallel.

Task mailboxes support `queue`, `reject`, `replace_pending`, and `cancel_and_replace`. Root and node bindings are persisted with admission. A child cannot replace pending work or cancel an owner until its original ordinary SDK admission is verified; uncertain admission blocks conservatively. FIFO waiting and expiry use the original Run, deadline and budget, with no implicit extension. A same-instance synchronous recursive wait is rejected; an asynchronous send can queue until the writer has finished and its cleanup is confirmed. An unknown effect keeps the instance quarantined even if native process cleanup is confirmed.

`Invocation.snapshot["instance"]` exposes the task or explicit service binding, otherwise `None`; `agent_context` reports the bound `instance_id` and `session_scope_id`. Writable workspace grants and their limits are described above. Service instance behavior is described below. Candidate 17 passed real OpenCode fixed-instance A/B/A session identity, FIFO, workspace and restart paths, plus independent keyed instances with new native sessions. A fresh challenge supplied only in the first conversation was recalled by the third invocation and again after host reopen; it was absent from observed SDK workspace file calls and declared artifacts. The aggregate installed SDK tests contained one replay error; the focused three-case diagnostic run later passed without a confirmed cause, so complete regression and G18 acceptance remain pending.

## Experimental services

Host-submitted service roots support `session.mode` `problem` (the default), `keyed`, and `new`. Problem and keyed modes require a nonempty `session_key`, supplied with the invocation or taken from the exact top-level input field named by `session.key`; when both are supplied for a new request, their values must match. `new` starts a separate generation and rejects a host-supplied session key. `trigger.mode: message` is accepted for services. Calls to a nested service through Agent tools currently fail with `agent_service_session_required`.

Service storage is Agent-owned schema 4, with one durable service identity per role. Each admitted configuration transition advances the role epoch, including A → B → A. Stable request replay keeps its original config, instance/session binding, deadline and budget; each request has its own finite SDK Run. The default `instance.mode: per_task` retains the existing session-scoped service behavior and directories. Explicit `fixed` uses one writable instance per role/configuration epoch; `keyed` selects an instance from the nonempty top-level input field named by `instance.key`. All sessions of that instance share its private workspace and serialize in instance-wide FIFO order; native conversation IDs and runtime state remain separate per session. Distinct keyed instances can proceed independently. `Invocation.snapshot["instance"]` exposes the explicit service binding, including `instance_owner` and `instance_quarantined`; it remains `None` for default service sessions. `agent_context` reports the bound instance and session IDs.

Mailbox capacity and replacement remain scoped to a session. `cancel_and_replace` cancels only that session's owner and pending work, even when another session owns the shared instance. Stop/resume and their control generation remain role-wide across every instance and epoch. A definite completion releases ownership only after exact SDK execution/effect and local/durable resource cleanup checks; an uncertain business effect quarantines the whole instance across reopen. Automatic schedule/state triggers accept default or fixed service instances; keyed instances need an explicit submission carrying their input key. Source SDK integration covers fixed/keyed instances, retained unknown ownership and live-resource cleanup. Candidate 25 passed five native fixed-instance checks on Linux x64 / Python 3.12.3 / OpenCode 1.18.32: queued work has no execution or charge, the predecessor has exact cleanup and a successful SDK finish before the next entry, sessions share workspace files but retain separate native identities, and close/reopen replay preserves identity and usage without a new entry. Three actual invocations use three finite original Runs; session A resumes after reopen. A separate candidate 25 keyed slice passed six native checks: X sessions serialize over the shared workspace, Y completes independently while X is held at entry, and reopen preserves exact replay and session continuation across four finite Runs. These service scripts did not inspect the SDK envelope absolute cutoff; a separate rework run exposed an approximately 74-microsecond extension that remains under repair. The service results do not establish that budget boundary, dialogue recall, provider concurrency, process crash recovery or full Goal acceptance. Candidate 25 also passed 62 installed SDK integration tests covering service instances, explicit upgrades, goal, task instances and workspaces, without skips; the complete regression and platform matrix remain pending.

Older service schema 2 or 3 is refused before host initialization writes. Stop the host and explicitly call `upgrade_service_store(state_dir, from_version=2)` (or `3`), or run `dispatcher-agents upgrade-service-store --state-dir DIR --from-version 3`. The API takes the same exclusive host lock and upgrades the Agent control sidecar in one transaction. IDs, stopped/control state, old session/native paths, queued bindings, owners and quarantine survive; legacy sessions receive no new instance binding. The upgrade does not modify SDK stores or reset budgets. Unknown/partial schemas fail, and an active host prevents upgrade. This is a structural upgrade, not proof that an unknown execution can resume.

Existing control stores require a separate explicit dependency upgrade: confirm the host has stopped, then run `dispatcher-agents upgrade-dependency-store --state-dir DIR --from-version 1`. Existing plans retain scanning, while newly created plans use event delivery; the upgrade does not modify SDK stores. `dispatcher-agents inspect-dependency-store --state-dir DIR` reports plan-mode counts, unsealed events and unacknowledged receipts and checks selected structural relationships. This read-only snapshot does not prove the host has stopped or that all data is healthy. Both commands require a private host state directory. Actual SDK execution of upgraded plans, complete upgrade compatibility and cross-platform behavior remain unaccepted. Close waits for delivery already in progress; unclaimed receipts remain for recovery on the next start, and acknowledgement is not proof of successful Agent execution.

`app.service_status(name)`, `app.stop_service(name, mode="drain" | "cancel")` and `app.resume_service(name)` manage host service state. Drain stops admission and leaves accepted work to complete; cancel persists cancellation for accepted work and active ownership remains until confirmed cleanup. A stopped service requires explicit resume. Closing an `AgentApp` stops its local host. A foreground CLI service host is available in current source. Candidate 10 passed a real G10 CLI/host scenario covering same-key native session continuity, independent Runs, host restart, recovery of a queued request in the observed crash window, and cross-Run cancellation. Candidate 17 passed all five real G09 mailbox scenarios: FIFO with two concurrent host callers and two queued messages, queue-full, reject, pending replacement, prelaunch cancellation and replacement, and post-send unknown quarantine. Ordinary runtime effects and final SDK receipts were matched to exact invocations, and authenticated native cleanup was verified. Local cleanup preserves unknown business outcomes. Candidate 10 G10 predates later guard, supervision and retained-service-stop fixes; final-candidate G10 and G18 acceptance remain pending.

## Goal completion

Set `completion.mode` to `goal` and `completion.validator` to a name registered by the host. The host supplies trusted callables through `AgentApp(..., validators={"check": check})`, or registers them in a `ValidatorRegistry` and passes the registry. Configuration selects a name; it does not execute an expression. The callable receives a `ValidationContext` with execution identity and copied response and artifact snapshots, and returns `ValidationResult("passed")`, `ValidationResult("continue", feedback)`, or `ValidationResult("blocked", feedback)`; feedback must be JSON.

A `continue` verdict starts another step with validator feedback in the same invocation, session, runtime state, deadline, frozen configuration and root budget. A `passed` verdict succeeds once required outputs exist; if outputs are missing, execution continues. Each step gets a fresh tool endpoint. Goal artifact versions are retained immutably by host step; `invocation.artifact_history(name)` returns committed version, host step and value facts, including versions of an incomplete goal. Downstream artifact bindings record the final successful producer version.

A `blocked` verdict maps to a failed Agent invocation with outcome `blocked` and failure code `goal_blocked`; it does not satisfy downstream dependencies. Validator exceptions and invalid results produce distinct safe failure codes without exposing exception details. A response-mode configuration with a validator is rejected. Goal admission rejects an unregistered validator or an adapter that does not declare same-session resume support before execution. Unknown execution effects are not blindly replayed. Candidate 05 G08 exercised same-session continue → passed with immutable step artifacts; blocked and validator-error cases failed without downstream success.

## Knowledge and configuration versions

`AgentApp` provides a host-owned `knowledge_store` (`KnowledgeStore`) and gives each invocation the `knowledge_read` and `knowledge_write` tools. Configure `knowledge.read` and `knowledge.write` as independent lists of exact namespace names; a write grant does not imply read permission, or vice versa. Names are opaque ASCII identifiers, not paths or wildcard patterns. The scoped tool checks the invocation's frozen grants and active authority. Host calls to `app.knowledge_store` are administrative operations, outside those scoped grants.

Knowledge values are JSON. `read(name)` returns the latest `{name, version, value}`, and `read(name, version)` reads an immutable historical version. `commit(name, value, expected_version)` uses compare-and-swap: use `None` for initial creation and the exact current version for an update. A conflict raises `KnowledgeConflictError` without overwriting history; each successful namespace version starts at 1 and increments. The corresponding tools accept `name`, optional `version` for reads, and `name`, `value`, `expected_version` for writes. Scoped permission and version conflicts are reported as tool errors. `ScopedKnowledge` implements the bound checks; it is available from `dispatcher_sdk.agents.knowledge`.

Host cancellation and close serialize with knowledge admission. A separately initiated Kernel revocation can still race a commit already admitted in the separate knowledge store: cancellation or an unknown response does not prove rollback. Inspect the durable namespace version and value before deciding what to do; do not blindly replay the write.

`app.update_config(new_spec)` activates a frozen configuration version for future requests, leaving existing plans and their prompt contents unchanged. Changing application worker capacity, memory capacity or role limits requires closing and reopening the host, subject to the unfinished-plan restriction above. Activation and each new admission capture **all** declared roles' `soul` and `prompt` source contents, including roles outside the selected graph. If any declared source is missing or unreadable, the new activation or admission fails. Existing frozen request replay and recovery do not depend on those source files remaining available. Relative source paths are resolved against `base_dir`.

## Current execution boundaries

The current slice supports host-submitted response and goal invocations, frozen automatic DAGs, SDK file tools and versioned declared outputs. Configuration for advanced policies is not executable merely because it appears in the registry. Strict file mode is rejected; shared reads require the separate host roots described above. AgentApp rejects non-null token budgets for every adapter; OpenCode also rejects them independently. Model fallback selection requires the trusted host configuration described below. Reasoning variants require explicit trusted host configuration as described below. Each provider inference request attempt is counted as a model turn before connection, including failed or aborted attempts; the default limit is 128 per request chain. Every newly staged Agent or controller SDK command also carries the exact frozen absolute `deadline_at`; coordinated children inherit their own frozen cutoff. Queueing, entry and reopen cannot turn remaining duration into a later SDK deadline. Unfinished work from experimental candidates that staged relative-only commands is refused before dispatch; its commands and receipts are preserved. Closed legacy requests may replay only after the exact public SDK command is confirmed terminal. Ordinary legacy SDK commands outside AgentApp keep their existing relative timeout behavior. The default 3600-second deadline starts with acceptance, and the default agent-call limit is 64; automatic graph invocations count against the run budget. No token ceiling is set by default.

File access rules constrain the SDK file tools; they are not an operating-system sandbox or a process-level isolation guarantee. No native strict isolation backend is provided, and real strict isolation has not been accepted. `strict` requests fail before business execution rather than silently downgrading. Declared output names can be published by the SDK tool; required output names must also be declared.

The target contract and acceptance requirements are recorded in [SDK 0.8.0 Agent Control Goal](SDK_0_8_0_AGENT_CONTROL_GOAL.md). The third isolated-wheel candidate's verifier reported G02–G04 passed on Linux x86_64, Python 3.12 and OpenCode 1.18.32. In a real `seed → fast + slow → consumer` run, a host gate held slow while the consumer remained unstarted; after release, the consumer read the `FAST_NATIVE` file snapshot and `SLOW_NATIVE` artifact and published `FAST_NATIVE|SLOW_NATIVE`. All four invocations shared one SDK Run, with 4 agent calls and 15 inference requests. Replaying the stable ID added no execution, while conflicting content was rejected. File-tool diagnostics recorded failures, but did not retain the attempted paths needed to independently match both requested traversal and symlink denials. In a direct file-tool directory-swap race with 62 substitutions, all 500 operations failed closed, leaving the external file unchanged; allowed file writes were demonstrated in separate model calls. Later candidate-specific passes include G05/G06 and G09; current per-case status and retained failures are listed in the acceptance index. Complete final-candidate regression and platform coverage remain pending. See the [acceptance index](SDK_0_8_0_AGENT_CONTROL_ACCEPTANCE.md) for evidence and scope.

The current Linux native ownership guard uses a subreaper and an `ECHILD` receipt to establish process cleanup. Four process and synthetic protocol tests passed; candidate 11 G02 also passed with real OpenCode and authenticated cleanup readback for the exact SDK generation. Broader guard fault acceptance remains incomplete. This receipt does not establish the model effect outcome or strict isolation. A source supervision ledger and diagnostic admission path passed a real SDK test with a synthetic adapter for the original effect and shared Run budget; native supervision acceptance remains pending.


Candidate 15 passed native G05/G06 with two overlapping coders in each round, explicit rework, the same logical reviewer consuming new results, exact bindings and original budgets. The unclosed-group negative used the actual returned group ID and was rejected. Earlier failed candidates remain recorded in the acceptance index; this evidence does not complete the overall Goal.

## Agent control tools

Incoming `access.cancel` and `access.resume` grants default to empty. `agent_cancel` takes exactly `invocation_id` and `request_id`; it can request cancellation only for an authorized proper descendant in the same Run, root and problem. Self, ancestors, siblings and other Runs are denied. `agent_resume` takes exactly `agent` and `request_id`; it reopens admission globally for an established service role, with permission required in both the caller's frozen plan and the current host configuration. It does not reset cancelled calls or quarantined sessions.

Both operations bind identity and budget from the live SDK caller, use an ordinary `agent.control.admission` effect, and project only its exact original committed receipt. Request IDs share one namespace per caller across these two operations; changed content conflicts. Ordinary policy denial is checked before effect preparation. Applied means that the request was projected, not that process cleanup succeeded. Unknown authority or an uncommitted/ambiguous receipt cannot authorize an action. Replaying an applied resume cannot undo a later host stop; a new explicit request is required. The current service registry is schema 4; explicit stopped-host upgrades from schema 2 or 3 are described above.

Pending accepted intents are reconsidered after host reopen under the original caller deadline, lease/fence and budget. SDK authority and Agent projection use separate stores, so external revocation is not an atomic rollback of an already accepted command. Current-source real SDK/loopback tests passed active descendant cancellation, a live independent root, denial without effects, stable replay, later-stop fencing and retained session quarantine. This is synthetic runtime evidence. Candidate 23 additionally passed a real OpenCode 1.18.32 control slice on Linux x64 / Python 3.12.3: actual self-denial without an effect, three model resume calls including exact replay across an intervening host stop, a new resume request, same-key session continuity, three independent Runs with unchanged original budgets, exact required artifact and authenticated native cleanup. Active descendant cancellation and control crash/reopen still need native acceptance; full G16/G18 remain incomplete.


Host role revocation uses `app.revoke_permissions("worker", request_id="revoke-1", reason="host decision")`, `app.permissions_status("worker")`, and `app.restore_permissions("worker", request_id="restore-1")`; authenticated `AgentClient` provides the same methods. CLI equivalents are `revoke-permissions`, `permissions-status`, and `restore-permissions`, each with `--state-dir DIR --agent worker`; decisions require `--request-id`, and revocation optionally accepts `--reason`. These are host administration operations, not model tools.

The default is allowed with generation `0`, still subject to the configured incoming access grants. Revocation persistently denies new role admissions and cancels unfinished matching invocations and their delegated descendants across open Runs, including live children of completed parents; completed results and unrelated roles are preserved. Invocation status exposes `permission_revocation` with the deciding request ID, role, generation and optional reason. SDK cancellation and native cleanup are separate facts, and an uncertain effect remains uncertain. Restore allows future admissions only; it never resumes cancelled work or clears quarantined ownership, stopped services or paused triggers. Config updates, service resume and host restart do not erase the decision. Exact request replay returns its original receipt without applying an old decision over a newer one; conflicting contents raise an error. Administrative decision IDs are unique across the state directory. Role and decision IDs are nonempty strings of at most 256 characters; an optional reason is a nonempty string of at most 4096 characters; NUL is rejected. Active calls retain their frozen configuration and original budget. These operations revoke the role's invocation authority; they do not selectively edit its frozen file/tool grants.
