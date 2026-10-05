"""A public process execution contains JSON serialization at its own deadline."""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import dispatcher_sdk
from dispatcher_sdk.execution_kernel import Kernel
from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope
import dispatcher_sdk.execution_kernel.runtime as runtime_module
from tests._acceptance_evidence import retained_directory


class EnteredSlowJsonList(list):
    def __init__(self, directory: str) -> None:
        super().__init__(["encoded"])
        self.directory = directory

    def __iter__(self):
        root = Path(self.directory)
        (root / "serialization-entered.json").write_text(json.dumps({
            "pid": os.getpid(), "monotonic": time.monotonic(), "wall_at": time.time(),
        }), encoding="utf-8")
        time.sleep(2)
        (root / "forbidden-late.txt").write_text("serialization continued after cutoff", encoding="utf-8")
        return super().__iter__()


def entered_slow_json_result(payload, context):
    return {"items": EnteredSlowJsonList(payload["directory"])}


entered_slow_json_result.__execution_kernel_revision__ = "serialization-deadline-entered-v1"


@unittest.skipUnless(os.name == "posix" and "fork" in multiprocessing.get_all_start_methods(),
                     "requires actual POSIX process containment")
class ResultSerializationDeadlineTests(unittest.TestCase):
    def test_public_process_deadline_stops_entered_json_serialization(self):
        root = retained_directory("sdk-result-serialization-deadline-")
        evidence = {"sdk_import": dispatcher_sdk.__file__, "python": sys.executable,
            "parent_pid": os.getpid(), "execution_timeout_seconds": 1,
            "serialization_sleep_seconds": 2, "phases": [], "cleanup_receipts": []}
        original_invoke = runtime_module.invoke_process_handler

        def observe_invocation(**kwargs):
            original_entered = kwargs["on_entered"]
            original_phase = kwargs["on_phase"]
            original_cleanup = kwargs["on_cleanup_confirmed"]

            def entered(packet):
                original_entered(packet)
                evidence["entry"] = packet

            def phase(name, details):
                original_phase(name, details)
                evidence["phases"].append({"phase": name, "details": details})

            def cleanup():
                original_cleanup()
                evidence["cleanup_receipts"].append({"state": "confirmed",
                    "source": "actual_posix_supervisor_callback", "monotonic": time.monotonic()})

            kwargs.update(on_entered=entered, on_phase=phase, on_cleanup_confirmed=cleanup)
            outcome = original_invoke(**kwargs)
            evidence["process_outcome"] = outcome
            return outcome

        runtime = None
        try:
            runtime = Kernel.open_sqlite(root / "kernel.sqlite3",
                {"serialization": entered_slow_json_result}, isolation_mode="process")
            command = runtime.command("serialization", execution_id="serialization",
                idempotency_key="serialization", correlation_id="serialization-deadline",
                timeout_seconds=1, payload={"directory": str(root)})
            evidence["command"] = command.to_dict()
            runtime.submit(command)
            with patch.object(runtime_module, "invoke_process_handler", observe_invocation):
                result = runtime.run_once(execution_id="serialization")
            evidence["result"] = result.to_dict()
            evidence["execution_limits"] = runtime.kernel.get_execution_limits("serialization")
            marker = root / "serialization-entered.json"
            evidence["serialization_entered"] = marker.exists()
            self.assertTrue(marker.exists(), evidence)
            entered = json.loads(marker.read_text(encoding="utf-8"))
            evidence["serialization_marker"] = entered
            # This wait extends observation only. The command keeps its fixed
            # one-second work budget throughout process entry and serialization.
            time.sleep(max(0, entered["monotonic"] + 2.1 - time.monotonic()))
            evidence["observed_after_entry_seconds"] = time.monotonic() - entered["monotonic"]
            evidence["late_marker_exists"] = (root / "forbidden-late.txt").exists()
            self.assertGreater(evidence["observed_after_entry_seconds"], 2, evidence)
            self.assertFalse(evidence["late_marker_exists"], evidence)
            self.assertNotEqual(entered["pid"], evidence["parent_pid"], evidence)
            ready = next(item["details"] for item in evidence["phases"] if item["phase"] == "worker_ready")
            self.assertEqual(entered["pid"], ready["worker_pid"], evidence)
            self.assertEqual(entered["pid"], evidence["entry"]["worker_pid"], evidence)
            self.assertTrue(evidence["entry"]["entry_confirmed"], evidence)
            self.assertEqual(evidence["execution_limits"]["entry_state"], "confirmed", evidence)
            self.assertEqual(result.state, "timed_out", evidence)
            self.assertEqual(result.result.status, "timed_out", evidence)
            self.assertEqual(result.result.error.code, "handler_timeout", evidence)
            self.assertEqual(result.result.error.details["phase"], "execution", evidence)
            original_budget = BudgetEnvelope.from_dict(evidence["entry"]["budget_envelope"])
            final_budget = BudgetEnvelope.from_dict(result.result.error.details["budget_envelope"])
            original_execution = next(item for item in original_budget.constraints if item.source == "execution")
            final_execution = next(item for item in final_budget.constraints if item.source == "execution")
            self.assertAlmostEqual(original_execution.deadline_at - original_budget.started_at, 1, places=6)
            self.assertEqual(final_execution.deadline_at, original_execution.deadline_at, evidence)
            self.assertEqual(final_execution.reserve_seconds, original_execution.reserve_seconds, evidence)
            self.assertEqual(evidence["process_outcome"]["kind"], "timeout", evidence)
            self.assertEqual(len(evidence["cleanup_receipts"]), 1, evidence)
        finally:
            try:
                if runtime is not None:
                    runtime.close()
                    evidence["runtime_close_completed"] = True
            finally:
                path = root / "evidence.json"
                path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                print("result_serialization_deadline_evidence=" + str(path), flush=True)


if __name__ == "__main__":
    unittest.main()
