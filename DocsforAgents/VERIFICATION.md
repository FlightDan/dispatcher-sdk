# Verify an integration

Run commands from the checkout after installing the SDK in an activated virtual
environment. Select checks for the integration you are implementing.

## General integration discipline

Use the [durable integration engineering principles](../docs/INTEGRATION_PRINCIPLES.md)
when preparing a release or investigating a failed Run. The final report should
show:

- package release, imported module origin, contract and storage schemas, registry
  and deployment identity;
- a supervised host owner, heartbeat and last successful queue pump or sync;
- separate states for structural reuse, independent review, current-Run
  validation and product acceptance;
- the question, closure criteria and affected gate for each evidence item;
- knowledge blockers separated from verification obligations that can only run
  after implementation;
- exact execution and candidate identity, first fatal condition, lifecycle
  milestone and authenticated test coverage;
- the evidence level for every assertion and every skipped capability;
- a frozen candidate and clean installed artifact for final verification;
- a read-only identity match before any durable Run or deployment mutation.

Do not convert a stable hash, green fixture count, Agent self-report or failed
search into a stronger claim than its evidence supports. Keep the first failure
and rerun the final checks when the candidate changes.

## Runnable behavior references

| Command | Evidence to expect |
| --- | --- |
| `python examples/kernel_task.py` | Queued work survives reopening SQLite and returns `{'total': 60}`. |
| `python examples/dependent_tasks.py` | The application explicitly dispatches dependent work and finishes the Run; output is `Invoice total: 60`. |
| `python examples/effect_recovery.py` | A real worker crash leaves an uncertain effect; evidence-based recovery succeeds without writing the receipt again. |
| `python examples/sdk_script_wakeup.py` | A durable callback wakes `conversation-42` with state `succeeded` and script output `report ready`. Follow the script guide's platform requirements. |
| `python examples/durable_audit.py` | Assertions cover durable audit consumption, replay, and application-owned dependency approval. |
| `python examples/isolation_timeout.py` | On Linux, the timed-out handler and child exit, then another task succeeds. |

These examples validate their demonstrated paths using temporary data. They do
not establish that your application's callbacks, external services, recovery
policy, or deployment platform satisfy the same guarantees.

## Check the application's own boundaries

- **Lost submission response:** replay the persisted request unchanged and
  verify that no extra task or dispatch is created.
- **Restart:** reopen persistent paths with matching handlers and verify queued
  work and accepted notifications remain available.
- **Duplicate notification:** deliver the same source/message identity twice
  and verify one committed business update; exercise a crash between acceptance
  and processing as appropriate to your receiver.
- **Business rejection:** return a mechanically successful but invalid or
  unaccepted artifact and verify it cannot dispatch protected successor work.
- **Revision conflict:** make a competing update and verify the application
  recomputes its decision from fresh state.
- **Uncertain external effect:** interrupt a controllable test operation and
  verify recovery uses external evidence rather than blindly repeating it.

Use synthetic inputs and controlled external fixtures. Scope these checks to
features your application actually uses.

For changes to the SDK itself, follow [CONTRIBUTING.md](../CONTRIBUTING.md) for
the test suite, packaging, and documentation checks. Deployment-specific evidence
is documented in [Windows runtime](../docs/WINDOWS_RUNTIME.md),
[process cleanup](../docs/PROCESS_CLEANUP_VALIDATION.md), and
[OpenSandbox validation](../docs/OPENSANDBOX_VALIDATION.md). Use the platform-specific
requirements and recorded validation scope; do not infer Windows coverage from
a passing Linux run.
