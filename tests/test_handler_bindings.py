"""Single-handler fingerprints and atomic claiming across revision filters."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel import ExecutionCommandV2, RetryPolicy, SQLiteKernel, StaleFenceError
from dispatcher_sdk.execution_kernel._registry import handler_revision, registry_revision


def original_handler(payload, context):
    return payload + 1


def changed_handler(payload, context):
    return payload + 2


class HandlerRevisionTests(unittest.TestCase):
    def test_singleton_manifest_and_unrelated_bindings(self):
        handlers = {"target": original_handler}
        revision = handler_revision(handlers, "target")
        self.assertEqual(revision, "handler-v1:" + registry_revision(handlers))
        expanded = {"unrelated": changed_handler, **handlers}
        self.assertEqual(handler_revision(expanded, "target"), revision)
        self.assertNotEqual(registry_revision(expanded), registry_revision(handlers))
        # The target can be bound without inspecting an unrelated opaque closure.
        resource = object()
        expanded["opaque"] = lambda payload, context: resource
        self.assertEqual(handler_revision(expanded, "target"), revision)

    def test_implementation_name_and_contract_version_are_bound(self):
        original = handler_revision({"target": original_handler}, "target")
        alternatives = (
            handler_revision({"target": changed_handler}, "target"),
            handler_revision({"renamed": original_handler}, "renamed"),
            handler_revision({("target", 2): original_handler}, "target", 2),
        )
        self.assertEqual(len(set((original, *alternatives))), 4)

    def test_explicit_deployment_dependency_changes_revision(self):
        def handler(payload, context):
            return payload

        handler.__execution_kernel_revision__ = "dependencies-v1"
        before = handler_revision({"target": handler}, "target")
        handler.__execution_kernel_revision__ = "dependencies-v2"
        self.assertNotEqual(handler_revision({"target": handler}, "target"), before)

    def test_defaults_and_closure_state_are_bound(self):
        def closure(value):
            return lambda payload, context: value

        def defaults(value):
            return lambda payload, context, configured=value: configured

        for factory in (closure, defaults):
            with self.subTest(factory=factory.__name__):
                self.assertNotEqual(handler_revision({"target": factory(1)}, "target"),
                                    handler_revision({"target": factory(2)}, "target"))

    def test_opaque_dependency_still_requires_explicit_deployment_binding(self):
        resource = object()

        def handler(payload, context):
            return resource

        with self.assertRaisesRegex(TypeError, "deployment revision"):
            handler_revision({"target": handler}, "target")
        handler.__execution_kernel_revision__ = "opaque-resource-v1"
        self.assertTrue(handler_revision({"target": handler}, "target").startswith("handler-v1:"))

    def test_normalized_keys_match_and_duplicates_remain_invalid(self):
        self.assertEqual(handler_revision({"target": original_handler}, "target"),
                         handler_revision({("target", 1): original_handler}, "target", 1))
        with self.assertRaisesRegex(ValueError, "duplicate handler binding"):
            handler_revision({"target": original_handler, ("target", 1): original_handler}, "target")

    def test_missing_and_invalid_requested_bindings_are_rejected(self):
        handlers = {"target": original_handler}
        for name, version in (("missing", 1), ("target", 2)):
            with self.subTest(name=name, version=version), self.assertRaises(KeyError):
                handler_revision(handlers, name, version)
        for name, version in (("", 1), (" ", 1), (None, 1), ("target", 0), ("target", True), ("target", "1")):
            with self.subTest(name=name, version=version), self.assertRaises(TypeError):
                handler_revision(handlers, name, version)


class _Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class MultiRevisionClaimTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name, "kernel.sqlite3")
        self.clock = _Clock()
        self.kernel = SQLiteKernel(self.path, now=self.clock, default_lease_seconds=5)
        self.addCleanup(self.kernel.close)

    def submit(self, identity, revision, *, attempts=1):
        return self.kernel.submit(ExecutionCommandV2(
            execution_id=identity, idempotency_key=identity, registry_revision=revision,
            correlation_id=identity, causation_id=None, handler_id="target", handler_contract_version=1,
            retry_policy=RetryPolicy(max_attempts=attempts, initial_backoff_seconds=0),
            timeout_seconds=2, payload=None,
        ))

    def _assert_filter_order(self, method_name):
        self.submit("foreign-first", "foreign")
        self.clock.value += 1
        self.submit("z-older", "accepted-a")
        self.clock.value += 1
        self.submit("a-newer", "accepted-b")
        method = getattr(self.kernel, method_name)
        leases = [method("owner", registry_revisions=["accepted-b", "accepted-a"]) for _ in range(2)]
        self.assertEqual([lease.execution_id for lease in leases], ["z-older", "a-newer"])
        self.assertIsNone(method("owner", registry_revisions=["accepted-b", "accepted-a"]))
        self.assertEqual(self.kernel.get("foreign-first").state, "queued")
        expected_state = "running" if method_name == "claim_and_start" else "leased"
        expected_revision = 3 if method_name == "claim_and_start" else 2
        for lease in leases:
            self.assertEqual((lease.attempt, lease.fence, lease.revision), (1, 1, expected_revision))
            self.assertEqual(self.kernel.get(lease.execution_id).state, expected_state)

    def test_claim_filters_all_revisions_in_global_fair_order(self):
        self._assert_filter_order("claim")

    def test_claim_and_start_filters_all_revisions_in_global_fair_order(self):
        self._assert_filter_order("claim_and_start")

    def test_tied_creation_times_use_execution_id_across_revisions(self):
        for identity, revision in (("c", "first"), ("a", "second"), ("b", "first")):
            self.submit(identity, revision)
        selected = [self.kernel.claim("owner", registry_revisions=["first", "second"]).execution_id
                    for _ in range(3)]
        self.assertEqual(selected, ["a", "b", "c"])

    def test_duplicate_revisions_are_normalized_without_duplicate_claims(self):
        self.submit("a", "accepted")
        lease = self.kernel.claim_and_start("owner", registry_revisions=("accepted", "accepted"))
        self.assertEqual(lease.execution_id, "a")
        self.assertIsNone(self.kernel.claim("owner", registry_revisions=["accepted", "accepted"]))
        self.assertEqual(self.kernel.get("a").attempt, 1)

    def _durable_data(self):
        return tuple(tuple(tuple(row) for row in self.kernel._connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
                     for table in ("kernel_clock", "kernel_executions", "kernel_events", "kernel_result_outbox"))

    def test_invalid_filters_do_not_reap_write_events_or_advance_clock(self):
        self.submit("expired", "accepted", attempts=2)
        self.kernel.claim("owner", registry_revision="accepted")
        before = self._durable_data()
        self.clock.value = 1000  # A valid call would reap the expired lease.
        invalid = [[], (), "accepted", b"accepted", {"accepted"}, {"a": "accepted"},
                   iter(["accepted"]), [""], ["  "], ["accepted", None], [True], [1]]
        for method_name in ("claim", "claim_and_start"):
            method = getattr(self.kernel, method_name)
            for value in invalid:
                with self.subTest(method=method_name, revisions=value), self.assertRaises(ValueError):
                    method("owner", registry_revisions=value)
                self.assertEqual(self._durable_data(), before)
            for arguments in (
                {"registry_revision": "accepted", "registry_revisions": ["accepted"]},
                {"registry_revision": ""},
                {"registry_revision": 1},
                {"registry_revisions": ["accepted"], "lease_seconds": 0},
            ):
                with self.subTest(method=method_name, arguments=arguments), self.assertRaises(ValueError):
                    method("owner", **arguments)
                self.assertEqual(self._durable_data(), before)

    def test_revision_values_are_literal_and_selected_with_one_query(self):
        suspicious = "revision') OR 1=1 --"
        self.submit("a-foreign", "foreign")
        self.submit("z-literal", suspicious)
        statements = []
        self.kernel._connection.set_trace_callback(statements.append)
        try:
            lease = self.kernel.claim_and_start("owner", registry_revisions=["absent", suspicious])
        finally:
            self.kernel._connection.set_trace_callback(None)
        self.assertEqual(lease.execution_id, "z-literal")
        self.assertEqual(self.kernel.get("a-foreign").state, "queued")
        selections = [statement for statement in statements
                      if statement.startswith("SELECT * FROM kernel_executions WHERE state = 'queued'")]
        self.assertEqual(len(selections), 1)

    def test_single_revision_and_unfiltered_claims_keep_existing_meanings(self):
        self.submit("a-foreign", "foreign")
        self.submit("b-matching", "accepted")
        self.assertEqual(self.kernel.claim("owner", registry_revision="accepted").execution_id, "b-matching")
        self.assertEqual(self.kernel.claim_and_start("owner").execution_id, "a-foreign")
        self.assertIsNone(self.kernel.claim("owner"))

    def test_expiry_preserves_attempt_fence_and_both_start_events(self):
        self.submit("a", "accepted", attempts=2)
        first = self.kernel.claim_and_start("first", registry_revisions=["accepted", "other"])
        self.clock.value = first.expires_at + 1
        second = self.kernel.claim_and_start("second", registry_revisions=["other", "accepted"])
        self.assertEqual((second.attempt, second.fence, second.revision), (2, 2, 6))
        self.assertEqual(self.kernel.get("a").started_at, self.clock.value)
        self.assertEqual(second.expires_at, self.clock.value + 7)
        with self.assertRaises(StaleFenceError):
            self.kernel.verify(first)
        self.assertEqual([event["event_type"] for event in self.kernel.events("a")],
                         ["submitted", "leased", "started", "lease_expired_redelivery", "leased", "started"])

    def test_concurrent_mixed_claim_methods_never_lease_the_same_execution(self):
        self.submit("a", "accepted-a")
        self.submit("b", "accepted-b")
        other = SQLiteKernel(self.path, now=self.clock)
        self.addCleanup(other.close)
        barrier = threading.Barrier(2)

        def claim(kernel, method_name):
            barrier.wait(timeout=5)
            return getattr(kernel, method_name)(method_name, registry_revisions=["accepted-b", "accepted-a"])

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(claim, self.kernel, "claim")
            second = executor.submit(claim, other, "claim_and_start")
            leases = [first.result(timeout=5), second.result(timeout=5)]
        self.assertEqual({lease.execution_id for lease in leases}, {"a", "b"})
        self.assertTrue(all(lease.attempt == lease.fence == 1 for lease in leases))

    def test_atomic_start_failure_rolls_back_selection_and_both_events(self):
        self.submit("a", "accepted")
        before = self.kernel.get("a")
        event = self.kernel._event

        def fail_after_started(*args, **kwargs):
            event(*args, **kwargs)
            if kwargs["event_type"] == "started":
                raise RuntimeError("injected event failure")

        with patch.object(self.kernel, "_event", side_effect=fail_after_started), \
                self.assertRaisesRegex(RuntimeError, "injected event failure"):
            self.kernel.claim_and_start("owner", registry_revisions=["accepted", "other"])
        self.assertEqual(self.kernel.get("a"), before)
        self.assertEqual([item["event_type"] for item in self.kernel.events("a")], ["submitted"])
        self.assertEqual(self.kernel.claim_and_start("owner", registry_revisions=["accepted"]).attempt, 1)


if __name__ == "__main__":
    unittest.main()
