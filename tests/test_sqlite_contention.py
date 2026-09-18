from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from scripts.benchmark_sqlite_contention import (
    run_benchmark,
    run_capacity_limit_exercise,
)


class SQLiteContentionBenchmarkTests(unittest.TestCase):
    def test_small_multiprocess_run_reports_latency_and_correctness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            start_method = (
                "fork"
                if "fork" in multiprocessing.get_all_start_methods()
                else "spawn"
            )
            result = run_benchmark(
                Path(temporary) / "contention.sqlite3",
                workers=2,
                items_per_worker=1,
                payload_bytes=16,
                durability="normal",
                start_method=start_method,
                process_timeout_seconds=30,
            )
        self.assertTrue(result["correctness"]["ok"], result["worker_errors"])
        self.assertEqual(result["correctness"]["execution_count"], 2)
        self.assertEqual(result["correctness"]["outbox_delivered"], 2)
        self.assertFalse(result["latency_is_direct_lock_wait"])
        for operation in (
            "submit",
            "claim",
            "start",
            "complete",
            "outbox_claim",
            "outbox_ack",
        ):
            measurement = result["operation_latency_under_contention"][operation]
            self.assertIn("p50_ms", measurement)
            self.assertIn("p95_ms", measurement)
            self.assertIn("p99_ms", measurement)
            self.assertIn("busy_errors", measurement)
        json.dumps(result, allow_nan=False)

    def test_page_limit_rejects_whole_transaction_then_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_capacity_limit_exercise(
                Path(temporary) / "capacity.sqlite3",
                durability="normal",
                payload_bytes=1_000_000,
            )
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["transaction_rejected"])
        self.assertTrue(result["rejected_execution_absent"])
        self.assertTrue(result["commit_after_capacity_returned"])
        self.assertFalse(result["simulates_real_disk_full"])
        self.assertFalse(result["simulates_power_loss"])


if __name__ == "__main__":
    unittest.main()
