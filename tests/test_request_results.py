"""Caller receipts remain separate from durable producer and transport results."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from dispatcher_sdk.orchestrator import CommandConflict
from dispatcher_sdk.orchestrator.inbox import NotificationInbox
from dispatcher_sdk.orchestrator.request_results import RequestResultInbox


class RequestResultTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "receipts.db"
        self.journal = RequestResultInbox(NotificationInbox(self.path))

    def record(self, **changes):
        arguments = dict(source_id="source", caller_id="caller", request_id="request",
                         execution_id="execution", result_id="result", result={"value": 1})
        return self.journal.record_result(**{**arguments, **changes})

    def lookup(self):
        return self.journal.lookup("source", "caller", "request")

    def test_record_lookup_and_delivery_never_confirm_caller_receipt(self):
        self.assertIsNone(self.lookup())
        identity = self.record()
        result = self.lookup()
        self.assertEqual(result.identity, identity)
        self.assertEqual(result.result, {"value": 1})
        self.assertIsNone(result.delivery_reported_at)
        self.assertIsNone(result.received_confirmed_at)
        self.journal.mark_delivered(identity)
        self.assertIsNotNone(self.lookup().delivery_reported_at)
        self.assertIsNone(self.lookup().received_confirmed_at)
        self.journal.confirm_received(identity)
        self.assertIsNotNone(self.lookup().received_confirmed_at)
        json.dumps(self.lookup().to_dict(), allow_nan=False)

    def test_explicit_confirmation_can_precede_transport_receipt(self):
        identity = self.record()
        self.journal.confirm_received(identity)
        observation = self.lookup()
        self.assertIsNotNone(observation.received_confirmed_at)
        self.assertIsNone(observation.delivery_reported_at)

    def test_reopen_and_response_loss_replay_preserve_receipts(self):
        identity = self.record()
        self.journal.mark_delivered(identity)
        self.journal.confirm_received(identity)
        original = self.lookup().to_dict()
        self.journal = RequestResultInbox(NotificationInbox(self.path))
        self.assertEqual(self.record(), identity)
        self.journal.confirm_received(identity)
        self.journal.mark_delivered(identity)
        self.assertEqual(self.lookup().to_dict(), original)

    def test_late_result_survives_producer_process_exit(self):
        code = """
import os, sys
from dispatcher_sdk.orchestrator.inbox import NotificationInbox
from dispatcher_sdk.orchestrator.request_results import RequestResultInbox
journal = RequestResultInbox(NotificationInbox(sys.argv[1]))
journal.record_result('source', 'caller', 'request', execution_id='execution',
                      result_id='result', result={'value': 2})
os._exit(0)
"""
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        subprocess.run([sys.executable, "-c", code, str(self.path)],
                       env=environment, check=True, timeout=20)
        result = self.lookup()
        self.assertEqual(result.result, {"value": 2})
        self.assertIsNone(result.received_confirmed_at)

    def test_same_request_conflicting_result_or_execution_is_rejected(self):
        self.record()
        for change in ({"result": {"value": 2}}, {"execution_id": "other"},
                       {"result_id": "other"}):
            with self.subTest(change=change), self.assertRaises(CommandConflict):
                self.record(**change)
        self.assertEqual(self.lookup().result, {"value": 1})

    def test_receipt_validates_exact_published_identity(self):
        identity = self.record()
        for change in ({"result_digest": "0" * 64}, {"execution_id": "other"},
                       {"result_id": "other"}):
            with self.subTest(change=change), self.assertRaises(CommandConflict):
                self.journal.confirm_received(replace(identity, **change))
        with self.assertRaises(KeyError):
            self.journal.confirm_received(replace(identity, caller_id="other"))
        self.assertIsNone(self.lookup().received_confirmed_at)

    def test_source_caller_and_request_are_independent_namespaces(self):
        first = self.record()
        for fields in ({"source_id": "other"}, {"caller_id": "other"},
                       {"request_id": "other"}):
            identity = self.record(**fields, result={"value": 2})
            self.journal.confirm_received(identity)
            observed = self.journal.lookup(identity.source_id, identity.caller_id, identity.request_id)
            self.assertIsNotNone(observed.received_confirmed_at)
        self.assertEqual(self.lookup().identity, first)
        self.assertIsNone(self.lookup().received_confirmed_at)

    def test_concurrent_replay_is_idempotent(self):
        def publish(_):
            identity = self.record()
            self.journal.mark_delivered(identity)
            self.journal.confirm_received(identity)
            return identity

        with ThreadPoolExecutor(max_workers=4) as pool:
            identities = list(pool.map(publish, range(8)))
        self.assertTrue(all(identity == identities[0] for identity in identities))
        self.assertIsNotNone(self.lookup().received_confirmed_at)
        self.assertEqual(len(self.journal.inbox.list_messages(limit=10)), 3)

    def test_mutable_payloads_do_not_change_persisted_result(self):
        value = {"items": [1]}
        self.record(result=value)
        value["items"].append(2)
        observed = self.lookup()
        observed.result["items"].append(3)
        self.assertEqual(self.lookup().result, {"items": [1]})


if __name__ == "__main__":
    unittest.main()
