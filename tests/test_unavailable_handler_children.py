"""Public child calls retain actual journal failure without replaying business."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import unittest

import dispatcher_sdk
from dispatcher_sdk import Dispatcher
from dispatcher_sdk.execution_kernel import ChildExecutionError
from tests._acceptance_evidence import retained_directory


def unavailable_parent(payload, context):
    errors = []
    for call in (
        lambda: context.children.run("child", payload, request_id="new-child", timeout_seconds=2),
        lambda: context.children.wait_for("absent-child", request_id="existing-child", timeout_seconds=2),
    ):
        try:
            call()
        except ChildExecutionError as error:
            errors.append({"type": type(error).__name__, "code": error.code,
                           "message": str(error), "execution_id": error.execution_id})
    return {"errors": errors, "activity": context.activity.report_bytes("stdout", b"still business"),
            "started_activity": context.activity.start().heartbeat()}


def unexpected_child(payload, context):
    Path(payload["child_marker"]).write_text("unexpected child business", encoding="utf-8")
    return "unexpected"


unavailable_parent.__execution_kernel_revision__ = "unavailable-parent-v1"
unexpected_child.__execution_kernel_revision__ = "unavailable-child-v1"


class UnavailableHandlerChildrenTests(unittest.TestCase):
    def test_corrupt_observation_storage_retains_structured_child_failure(self):
        for isolation in ("thread", "process"):
            with self.subTest(isolation=isolation):
                root = retained_directory("sdk-unavailable-child-service-")
                store = root / "application.sqlite3"
                journal = Path(str(store) + ".observations.sqlite3")
                journal.write_bytes(b"actual unsupported SQLite file")
                payload = {"child_marker": str(root / "child-business")}
                evidence = {"interpreter": sys.executable, "sdk_import": dispatcher_sdk.__file__,
                            "isolation": isolation, "execution_timeout": 10, "caller_timeout": 12}
                try:
                    with Dispatcher(store, {"parent": unavailable_parent, "child": unexpected_child},
                                    isolation_mode=isolation) as app:
                        task = app.submit("parent", payload, request_id="parent", timeout_seconds=10)
                        result = task.wait(timeout=12)
                        observation = task.observe()
                        evidence.update(result=result, observation=observation)
                        self.assertEqual(result["status"], "succeeded", result)
                        errors = result["value"]["errors"]
                        self.assertEqual(len(errors), 2)
                        self.assertTrue(all(error["code"] == "child_service_unavailable" for error in errors))
                        self.assertTrue(all(error["message"] == observation["error"] for error in errors))
                        self.assertIn("DatabaseError", observation["error"])
                        self.assertIn("file is not a database", observation["error"])
                        self.assertEqual(errors[1]["execution_id"], "absent-child")
                        self.assertEqual(result["value"]["activity"]["state"], "unknown")
                        self.assertEqual(result["value"]["started_activity"]["state"], "unknown")
                        self.assertFalse(Path(payload["child_marker"]).exists())
                    with closing(sqlite3.connect(store.as_uri() + "?mode=ro", uri=True)) as connection:
                        self.assertEqual(connection.execute("SELECT COUNT(*) FROM kernel_executions").fetchone()[0], 1)
                except BaseException as error:
                    evidence["error"] = {"type": type(error).__name__, "message": str(error)}
                    raise
                finally:
                    (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                    print("unavailable_child_service_evidence=" + str(root / "evidence.json"), flush=True)
