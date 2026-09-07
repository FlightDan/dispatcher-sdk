# Durable integration engineering principles

This guide turns recurring integration failures into reusable engineering
rules for applications built on a durable SDK. It complements the API and
recovery contracts; it does not move application policy, product acceptance or
domain-specific states into the SDK.

Use these rules when preparing a deployment, investigating a failed Run, or
assembling evidence for a release. Every claim should identify the component
that can actually prove it and the evidence level that was used.

## 1. Record a version as a vector

One version label cannot identify the code that created or can resume durable
work. Record these coordinates independently:

- package release and source or build revision;
- the module origin actually imported by the process;
- execution and orchestration contract versions;
- each persistent storage schema version;
- handler or plugin registry revision;
- deployment artifact digest and configuration or durability profile.

A diagnostic bundle should make the coordinates machine-readable. For example:

```json
{
  "sdk_release": "0.6.0",
  "sdk_module_origin": "/venv/lib/python3.12/site-packages/dispatcher_sdk/__init__.py",
  "execution_contract_version": 2,
  "orchestration_contract_version": 2,
  "storage_schema_versions": {"kernel": 2, "orchestrator": 2},
  "registry_revision": "sha256:...",
  "deployment_revision": "sha256:..."
}
```

An editable checkout on `PYTHONPATH` can silently differ from the declared
dependency. A matching SemVer also does not prove matching handler bindings or
storage compatibility. Inspect those coordinates before opening an existing
store; see [storage and deployment preflight](STORAGE_AND_UPGRADES.md) and the
[public compatibility guide](PUBLIC_API.md).

## 2. Treat process lifetime as supervised service state

Starting a process, seeing a PID, or detaching a shell does not prove that a
platform will preserve the service or that its work is progressing. A host that
owns durable work should expose and persist:

- owner and process or service identity;
- start time and last heartbeat;
- last successful flush, sync or queue pump;
- active work and worker health;
- stop request, stop result and stop reason;
- durable Run state independent of the host process.

Keep these claims separate: the process is alive, the host is making progress,
the task is terminal, and the Run is settled. Use a platform supervisor for a
long-running deployment and keep the original deployment available for
recovery. The SDK host loop and its limitations are described in
[recovery and retry](SDK_RECOVERY.md).

## 3. Separate reuse, review and current validation

Cached material and generated artifacts have several independent properties.
Do not collapse them into one `approved` flag:

| Property | Question it answers |
| --- | --- |
| Structurally reusable | Does the current payload pass the host's structural checks? |
| Independently reviewed | Did a reviewer other than the producer inspect it? |
| Reviewed for this content | Does that review identify the exact payload or immutable revision? |
| Validated in this Run | Did this Run verify the required behavior in its environment? |
| Accepted for publication | Did the product gate approve this artifact for its intended use? |

If a payload can change while its path and metadata stay the same, an old review
is at most a historical workflow hint. Either bind review to an immutable
payload identity or report clearly that current-content approval is absent.
Reuse never replaces current-run validation. See the [output contract guide](SDK_OUTPUT_CONTRACTS.md)
for the same separation in Agent-generated output.

## 4. Separate evidence acquisition from closure

Finding a source, producing a log, or adding a declaration is evidence
acquisition. It does not by itself answer the question or close a blocker.

Before dispatching research or verification, record:

1. the exact question or obligation;
2. the closure criteria and required authority;
3. the affected tasks or gates;
4. what would count as a new relevant fact.

After evidence arrives, run a separate assessment that decides whether the
criteria are met. Preserve the original question and the acquired material
when the answer remains unresolved. Bound repeated work by relevant evidence
progress, not file churn, changed timestamps or a successful Agent message.

## 5. Distinguish knowledge blockers from deferred verification

Not every missing fact has the same routing consequence:

| Kind | Meaning | Correct routing |
| --- | --- | --- |
| Knowledge | Information needed now to choose a safe contract or implementation | Block only affected work until the question is answered or an approved alternative is chosen |
| Verification | Evidence that can only be obtained after implementation, such as a build or runtime test | Record a deferred obligation and carry it to its declared acceptance gate |

Do not require post-implementation evidence before implementation can start.
Do not mark deferred verification as resolved merely because a workaround was
proposed. An alternative path changes the plan; it does not prove behavioral
equivalence. The SDK can carry typed metadata and waits, while the application
defines the domain meaning and acceptance gate.

## 6. Diagnose with causal identity

The same error count, warning or artifact hash can occur in different failures.
Compare observations using the identities and milestones that establish a
causal chain:

1. exact Run, task, attempt, execution and candidate identity;
2. source and deployment revision used by that execution;
3. first fatal condition, rather than the first warning;
4. lifecycle milestone actually reached;
5. authenticated test identifiers and coverage;
6. raw logs and the change in relevant evidence between attempts.

Classify the result as a product, harness, environment, protocol or operator
failure only after those facts line up. A stable contract file does not prove
that the implementation or lifecycle was unchanged. Source churn proves that
work occurred; it does not prove useful progress. See the
[recovery diagnostics](SDK_RECOVERY.md) and [verification guidance](../DocsforAgents/VERIFICATION.md).

## 7. Report an evidence ladder

Evidence levels answer different questions. State the level and every skipped
level in validation reports:

| Level | It can establish | It cannot establish by itself |
| --- | --- | --- |
| Unit or fixture | Local parsing, validation or routing behavior | Real process, service, build or product behavior |
| Real SDK integration | Persistence, leases, delivery and recovery under the tested setup | Model quality, project build or product acceptance |
| Real process and restart | Lifecycle and restart behavior for the deployment | External service or product semantics |
| Real model or external service | Provider launch and response capture | Artifact correctness or business acceptance |
| Real source build | Toolchain and build execution for a fixed source | Runtime behavior or compatibility in another environment |
| Real server or client harness | Declared runtime witnesses | Every manual, visual or behavioral property |
| Independent product acceptance | The frozen candidate met its declared gates | Universal correctness for other candidates or environments |

Test counts and green fixture suites must not be reported as stronger evidence
than the level they exercised. A skipped capability is a coverage gap, not a
passing result. See [verification for agents](../DocsforAgents/VERIFICATION.md).

## 8. Freeze the candidate before final verification

Targeted tests can run during development. Final verification needs a stable
candidate:

- freeze the source, dependency lock, handler registry and configuration;
- record the artifact and deployment identities;
- run independent review against that identity;
- run the complete applicable suite and record skips;
- build and install the distributable in a clean environment;
- bind the report to the exact artifact and environment.

If any code, dependency, generated artifact or acceptance rule changes after
the run starts, treat the result as belonging to the previous candidate and
repeat the affected verification. Keep the first failure and its race window;
do not make a long run appear to validate a moving checkout.

## 9. Discover durable objects before mutating them

“The search did not find it” means only that the object was absent from that
search scope. Before creating, resuming, retrying, cancelling or deleting a
Run, job or deployment:

1. search only caller-configured roots;
2. read candidate identity without opening a writer or repairing the store;
3. compare stable ID, path, parent, request, schema and deployment binding;
4. report duplicates, ambiguity, damaged or incomplete candidates;
5. keep creation or mutation as a separate explicit action.

Never select a candidate merely because it has a familiar directory name, and
never create a replacement after an inconclusive lookup without an explicit
lineage decision. The SDK's read-only storage checks are documented in
[storage and upgrades](STORAGE_AND_UPGRADES.md); application-level discovery
must also include its own Run roots and lineage fields.

## Applying the principles

Use the detailed SDK contracts for the mechanics:

- [SDK operations and delivery](SDK.md) for explicit decisions, replay and
  separation of execution from business routing;
- [recovery and retry](SDK_RECOVERY.md) for leases, effects and cancellation;
- [storage and deployment preflight](STORAGE_AND_UPGRADES.md) for compatibility;
- [output contracts](SDK_OUTPUT_CONTRACTS.md) for structured Agent artifacts;
- [agent verification](../DocsforAgents/VERIFICATION.md) for a release evidence
  package.

The application remains responsible for domain semantics, business budgets,
independent review policy and final product acceptance.
