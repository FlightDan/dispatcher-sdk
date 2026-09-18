"""Exercise all four reliability additions against a temporary local store."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from dispatcher_sdk import runtime_identity
from dispatcher_sdk.orchestrator import (
    Orchestrator, OrchestratorHost, NotificationInbox, RequestResultInbox,
    inspect_execution_origin,
)


def echo(payload, context):
    return payload


with TemporaryDirectory() as directory:
    path = Path(directory) / "state.db"
    with Orchestrator.open_sqlite(path, {"echo": echo}, isolation_mode="thread") as sdk:
        sdk.create_run("run", command_id="create")
        receipt = sdk.submit_task("run", "task", request_id="request", expected_revision=0,
                                  handler_id="echo", payload={"value": 1}, timeout_seconds=5)
        execution = receipt["tasks"]["task"]["attempts"][0]["command"]["execution_id"]
        sdk.flush()
        sdk.runtime.run_once()
        sdk.sync()
        identity = runtime_identity(path, check="schema", timeout_seconds=5)
        # A source checkout may not match wheel RECORD; storage facts are still
        # independently readable. Installed-wheel validation checks this field.
        assert identity.storages[0].integrity == "not_checked"
        assert identity.complete
        origin = inspect_execution_origin(path, execution_id=execution)
        assert origin.status == "found", origin
        assert origin.task_id == "task" and origin.application_attempt == 0
        json.dumps(origin.to_dict(), allow_nan=False)
        host = OrchestratorHost(sdk, worker_count=1).start()
        assert host.stop(timeout=5)
        assert host.stop_report.status == "completed", host.stop_report
        json.dumps(host.stop_report.to_dict(), allow_nan=False)
    journal = RequestResultInbox(NotificationInbox(Path(directory) / "receipts.db"))
    result = journal.record_result("source", "caller", "request", execution_id=execution,
                                    result_id="result", result={"value": 1})
    journal.mark_delivered(result)
    assert journal.lookup("source", "caller", "request").received_confirmed_at is None
    journal.confirm_received(result)
    assert journal.lookup("source", "caller", "request").received_confirmed_at is not None
print("identity, execution origin, shutdown report, caller receipt passed")
