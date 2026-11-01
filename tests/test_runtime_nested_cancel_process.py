"""Real process A->B->C parent cancellation; registry validation is mocked."""
import json
from contextlib import nullcontext
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dispatcher_sdk.execution_kernel import Kernel, SQLiteKernel
from dispatcher_sdk.execution_kernel import StaleFenceError
from dispatcher_sdk.execution_kernel.contracts import ExecutionLease
from dispatcher_sdk.execution_kernel.children import ChildService, _inspect_parent_revocation
from tests.test_execution_kernel_v2_sqlite import make_command
from dispatcher_sdk.execution_kernel import runtime as runtime_module


def _publish(payload, context, node):
    identity = {"execution_id": context.lease.execution_id, "attempt": context.lease.attempt,
                "fence": context.lease.fence, "pid": os.getpid()}
    Path(payload["directory"], node + ".json").write_text(json.dumps(identity))
    return identity


def _nested_a(payload, context):
    _publish(payload, context, "A")
    return context.children.run("B", payload, request_id="A-B", timeout_seconds=35)


def _nested_b(payload, context):
    _publish(payload, context, "B")
    return context.children.run("C", payload, request_id="B-C", timeout_seconds=30)


def _nested_c(payload, context):
    _publish(payload, context, "C")
    time.sleep(25)
    return {"unexpected": "handler completed without cancellation"}


@unittest.skipUnless(os.name == "posix", "requires POSIX process supervisor")
class RuntimeNestedCancellationTests(unittest.TestCase):
    def test_wall_clock_jump_and_rollback_do_not_prove_parent_revoked(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [100.0]
            with SQLiteKernel(Path(directory) / 'kernel.db', now=lambda: now[0]) as kernel:
                kernel.submit(make_command('parent'))
                lease = kernel.claim_and_start('owner', execution_id='parent', lease_seconds=5)
                now[0] = 110.0
                _inspect_parent_revocation(kernel, lease)
                now[0] = 100.0
                _inspect_parent_revocation(kernel, lease)
                self.assertEqual(kernel.get('parent').state, 'running')

    def test_monitor_requires_known_revocation_and_exact_child_relationship(self):
        lease = ExecutionLease('parent', 'lease', 'owner', 2, 1, 9999999999, 1)
        row = {'parent_lease_json': json.dumps(lease.to_dict()), 'child_execution_id': 'child'}
        kernel = Mock()
        kernel._control_lock.return_value = nullcontext()
        parent = SimpleNamespace(state='running', attempt=1, fence=2)
        child = SimpleNamespace(state='running', revision=12)
        kernel.get.side_effect = lambda execution_id: parent if execution_id == 'parent' else child
        kernel.get_execution_limits.return_value = {'parent_execution_id': 'parent',
            'parent_attempt': 1, 'parent_fence': 2}
        runtime = Mock(kernel=kernel)
        service = object.__new__(ChildService)
        service.runtime = runtime
        service._cancel_if_parent_revoked(row)
        runtime.cancel.assert_not_called()
        kernel._verify_active_lease_readonly.side_effect = TimeoutError('Kernel control lock admission timed out')
        service._cancel_if_parent_revoked(row)
        runtime.cancel.assert_not_called()
        kernel._verify_active_lease_readonly.side_effect = StaleFenceError('parent revoked')
        # A readonly wall-clock expiry with the durable parent still running
        # is not a revocation, even if the wall clock later rolls back.
        service._cancel_if_parent_revoked(row)
        runtime.cancel.assert_not_called()
        parent.state = 'cancelled'
        kernel.get_execution_limits.return_value['parent_fence'] = 3
        service._cancel_if_parent_revoked(row)
        runtime.cancel.assert_not_called()
        kernel.get_execution_limits.return_value['parent_fence'] = 2
        service._cancel_if_parent_revoked(row)
        runtime.cancel.assert_called_once_with('child', expected_revision=12,
            reason='parent authority revoked', timeout_seconds=.5)

    def test_failed_revocation_corroboration_retains_existing_child(self):
        lease = ExecutionLease('parent', 'lease', 'owner', 2, 1, 9999999999, 1)
        row = {'parent_lease_json': json.dumps(lease.to_dict()), 'child_execution_id': 'child',
               'action': 'run'}
        kernel = Mock()
        kernel._control_lock.return_value = nullcontext()
        kernel._verify_active_lease_readonly.side_effect = StaleFenceError('lease expired')
        kernel.get.side_effect = TimeoutError('lookup unavailable')
        service = object.__new__(ChildService)
        service.runtime = Mock(kernel=kernel)
        service._cancel = Mock()
        service._retain_registration = Mock()
        service._execute(row)
        service._cancel.assert_not_called()
        service._retain_registration.assert_called_once()
        self.assertEqual(service._retain_registration.call_args.args[1].code, 'parent_revocation_unknown')

    def test_uncertain_observation_wait_retries_without_publishing_failure(self):
        lease = ExecutionLease('parent', 'lease', 'owner', 2, 1, 9999999999, 1)
        row = {'parent_lease_json': json.dumps(lease.to_dict()), 'child_execution_id': 'child',
               'parent_execution_id': 'parent', 'budget_json': '{}'}
        kernel = Mock()
        kernel._control_lock.return_value = nullcontext()
        kernel._verify_active_lease_readonly.side_effect = StaleFenceError('lease expired')
        kernel.get.side_effect = TimeoutError('lookup unavailable')
        store = Mock(source_id='store')
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = [row]
        store.read.return_value = nullcontext(connection)
        service = object.__new__(ChildService)
        service.runtime = Mock(kernel=kernel)
        service.store = store
        service._stop = threading.Event()
        with patch('dispatcher_sdk.execution_kernel.children._RetryWindow'), \
             patch('dispatcher_sdk.execution_kernel.children.BudgetEnvelope.from_dict'):
            service._observe_waits()
            store.finish.assert_not_called()
            kernel._verify_active_lease_readonly.side_effect = None
            kernel.get.side_effect = None
            kernel.get.return_value = SimpleNamespace(state='succeeded',
                result=SimpleNamespace(to_dict=lambda: {'status': 'succeeded'}))
            service._observe_waits()
        store.finish.assert_called_once_with(row, 'completed', result={'status': 'succeeded'})

    def test_cancel_parent_while_nested_child_running(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runtime_module, "registry_revision", return_value="fixture-registry"), \
             patch.object(runtime_module, "handler_revision", return_value="fixture-handler"):
            runtime = Kernel.open_sqlite(Path(directory) / "kernel.sqlite", {"A": _nested_a, "B": _nested_b, "C": _nested_c},
                isolation_mode="process", child_capacity=2, max_child_depth=2)
            driver_errors, result = [], []
            def drive():
                try:
                    result.append(runtime.run_once(execution_id="parent"))
                except BaseException as error:
                    driver_errors.append(error)
            try:
                runtime.submit(runtime.command("A", execution_id="parent", idempotency_key="parent",
                    correlation_id="root", timeout_seconds=45, payload={"directory": directory}))
                driver = threading.Thread(target=drive)
                driver.start()
                deadline = time.monotonic() + 20
                child_path = Path(directory) / "C.json"
                while not child_path.exists() and driver.is_alive() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(child_path.exists(), (driver_errors, result))
                identities = {node: json.loads((Path(directory) / (node + ".json")).read_text()) for node in ("A", "B", "C")}
                self.assertEqual(len({identity["pid"] for identity in identities.values()}), 3)
                a = runtime.kernel.get("parent")
                self.assertEqual(a.state, "running")
                for node in ("B", "C"):
                    self.assertEqual(runtime.kernel.get(identities[node]["execution_id"]).state, "running")
                cancelled = runtime.cancel("parent", expected_revision=a.revision, timeout_seconds=3)
                self.assertEqual(cancelled.state, "cancelled")
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    states = {node: runtime.kernel.get(identity["execution_id"]).state for node, identity in identities.items()}
                    if all(state == "cancelled" for state in states.values()):
                        break
                    time.sleep(.05)
                registrations = runtime._settlement_journal.scan_supervisor_cleanup(timeout_seconds=1)["registrations"]
                facts = {node: [item for item in registrations if item["identity"] == {
                    "execution_id": identity["execution_id"], "attempt": identity["attempt"],
                    "fence": identity["fence"]}] for node, identity in identities.items()}
                self.assertEqual(states, {"A": "cancelled", "B": "cancelled", "C": "cancelled"},
                                 (identities, facts))
                # The supervisor may terminate before writing its own tree
                # receipt; only the independently observed reap can confirm
                # process cleanup in that case.
                deadline = time.monotonic() + 8
                while True:
                    exact = runtime._settlement_journal.scan_supervisor_cleanup(timeout_seconds=1)["registrations"]
                    cleanup = {node: next(item for item in exact if item["identity"] == {
                        "execution_id": identity["execution_id"], "attempt": identity["attempt"],
                        "fence": identity["fence"]}) for node, identity in identities.items()}
                    if all(item["cleanup"] == "confirmed" for item in cleanup.values()) or time.monotonic() >= deadline:
                        break
                    time.sleep(.05)
                for node, evidence in cleanup.items():
                    self.assertIn(evidence["worker_tree_cleanup"], ("confirmed", "unknown"), node)
                    self.assertEqual(evidence["cleanup"], "confirmed", node)
            finally:
                # Stop any still-running fixture processes even on a failed
                # propagation assertion; do not infer cleanup from cancellation.
                for node in ("C", "B", "A"):
                    path = Path(directory) / (node + ".json")
                    if not path.exists():
                        continue
                    try:
                        identity = json.loads(path.read_text())
                        snapshot = runtime.kernel.get(identity["execution_id"])
                        if snapshot.state == "running":
                            runtime.cancel(identity["execution_id"], expected_revision=snapshot.revision, timeout_seconds=5)
                    except Exception:
                        pass
                if "driver" in locals():
                    driver.join(10)
                runtime.close()
