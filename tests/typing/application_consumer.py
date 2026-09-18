"""Type-check the primary application entry point."""
from pathlib import Path
from typing import Any

from dispatcher_sdk import Dispatcher, Task, DeploymentMismatchError, RecoveryRequiredError


def consume(path: Path) -> None:
    def double(payload: Any, context: Any) -> Any:
        return payload * 2

    with Dispatcher(path, {"double": double}) as app:
        task: Task = app.submit("double", 21, request_id="message")
        result: dict[str, Any] = task.wait(timeout=5)
        app.task("message")
        app.health()
        app.consume_results(lambda connection, notification: None)
        app.submit("double", 21)  # type: ignore[call-arg]
        task.wait(timeout="forever")  # type: ignore[arg-type]
        try:
            task.wait()
        except RecoveryRequiredError as error:
            print(error.request_id, error.snapshot)
        except DeploymentMismatchError as mismatch:
            print(mismatch.report)
        print(result)
