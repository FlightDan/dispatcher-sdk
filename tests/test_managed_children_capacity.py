"""Bounded admission and durable response semantics before runtime integration."""

from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dispatcher_sdk.execution_kernel.budget import BudgetEnvelope, sample_clock
from dispatcher_sdk.execution_kernel.children import CHILD_SCHEMA, ChildExecutionError, ChildService, HandlerChildren
from dispatcher_sdk.execution_kernel.contracts import ExecutionCommandV2, ExecutionLease, ExecutionResultV2, RetryPolicy
from dispatcher_sdk.execution_kernel.errors import ExecutionNotFoundError
from dispatcher_sdk.execution_kernel.errors import CASConflictError, StaleFenceError
from dispatcher_sdk.execution_kernel.runtime import Runtime
from dispatcher_sdk.execution_kernel.sqlite import SQLiteKernel
from tests._acceptance_evidence import retained_directory
from tests._storage_evidence import StorageEvidence


class RequestJournal:
    """Real SQLite rows with the service's bounded independent connections."""

    def __init__(self, path):
        self.path, self.source_id = Path(path), "test-store"
        self.clock = time.time
        self.options = SimpleNamespace(query_timeout=.5, write_timeout=.2)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(CHILD_SCHEMA)

    @contextmanager
    def _transaction(self, *, timeout_seconds=None):
        connection = sqlite3.connect(self.path, timeout=self.options.write_timeout if timeout_seconds is None else min(self.options.write_timeout, timeout_seconds))
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection, time.time()
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _read_connection(self, timeout):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=timeout)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            yield connection, None
        finally:
            connection.close()


class ParentAuthority:
    def __init__(self):
        self.live = True
        self.depth = 0
        self.targets = {}
        self.limits = {}

    def verify(self, lease):
        if not self.live:
            from dispatcher_sdk.execution_kernel.errors import StaleFenceError
            raise StaleFenceError("original parent fence was revoked")

    def get_execution_limits(self, execution_id):
        return self.limits.get(execution_id, {"depth": self.depth, "entry_state": "confirmed",
            "entry_attempt": 1, "entry_fence": 1})

    def get(self, execution_id):
        if execution_id not in self.targets:
            raise ExecutionNotFoundError(execution_id)
        return self.targets[execution_id]


class ManagedChildAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.admission_evidence = None
        if self._testMethodName in (
                'test_first_child_waits_for_actual_parent_entry_confirmation',
                'test_targeted_child_claim_rejects_expired_inherited_work_window'):
            root = retained_directory('sdk-managed-child-admission-')
            self.admission_evidence = {'test': self.id(), 'interpreter': sys.executable,
                                       'stages': [], 'stage_count': 0, 'diagnostic_errors': []}
            self.admission_storage = StorageEvidence(root, self)
            self.admission_storage.start(include_kernel=True)
            self.addCleanup(self.admission_storage.stop)
            self.addCleanup(self.capture_admission, 'after_cleanup', None)
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        self.journal = RequestJournal(root / "children.sqlite3")
        self.kernel = ParentAuthority()
        self.command = self.make_command("parent")
        self.lease = ExecutionLease("parent", "parent-lease", "worker", 1, 1, time.time() + 60, 1)
        self.budget = BudgetEnvelope((), sample_clock()).enter_handler(30, origin_id="parent-time", reserve_seconds=2)
        self.spec = {"capacity": 1, "max_depth": 1, "registry_revision": "test-registry"}
        self.children = self.capability()

    def admission_diagnostic(self, operation):
        try:
            return operation()
        except BaseException as error:
            try:
                self.admission_evidence['diagnostic_errors'].append(
                    {'type': type(error).__name__, 'message': str(error)})
            except BaseException:
                pass

    def admission_stage(self, name, operation, **facts):
        stage = {'name': name, 'began': time.monotonic(),
                 'thread': threading.current_thread().name}

        def entered():
            stage.update({key: value.to_dict() if hasattr(value, 'to_dict') else value
                          for key, value in facts.items()})
            self.admission_evidence['stages'].append(stage)
            self.admission_evidence['stage_count'] += 1
            if len(self.admission_evidence['stages']) > 128:
                del self.admission_evidence['stages'][32]

        self.admission_diagnostic(entered)
        try:
            result = operation()
            self.admission_diagnostic(lambda: stage.update(
                result=result.to_dict() if hasattr(result, 'to_dict') else result))
            return result
        except BaseException as error:
            def record_error():
                stage['error'] = {'type': type(error).__name__, 'message': str(error),
                    'traceback': traceback.format_exc(),
                    'sqlite_errorcode': getattr(error, 'sqlite_errorcode', None)}
                for field in ('budget_sample_token', 'budget_sample_envelope'):
                    value = getattr(error, field, None)
                    stage['error'][field] = (value.to_dict() if hasattr(value, 'to_dict') else repr(value))
            self.admission_diagnostic(record_error)
            raise
        finally:
            self.admission_diagnostic(lambda: stage.update(ended=time.monotonic()))

    def record_admission_entry(self, name, context):
        # Copy the envelope supplied by Runtime; public context.budget performs
        # guarded sampling and must not be invoked by diagnostic recording.
        envelope = context._budget_envelope
        self.admission_diagnostic(lambda: self.admission_evidence.update({name: {
            'at': time.monotonic(), 'budget': None if envelope is None else envelope.to_dict()}}))

    def capture_admission(self, phase, kernel):
        evidence = self.admission_evidence
        try:
            frames = sys._current_frames()
            evidence['threads'] = [{
                'name': thread.name, 'alive': thread.is_alive(),
                'stack': traceback.format_stack(frames[thread.ident], limit=64) if thread.ident in frames else []
            } for thread in threading.enumerate()]
            if kernel is not None:
                evidence['kernel_path'] = kernel.db_path
                evidence['tables'] = {}
                deadline = time.monotonic() + .1
                paths = [(kernel.db_path, ('kernel_executions', 'kernel_execution_limits',
                                          'kernel_budget_samples', 'kernel_clock'))]
                if evidence.get('observation_path'):
                    paths.append((evidence['observation_path'], ('sdk_child_requests', 'sdk_child_waits')))
                for path, tables in paths:
                    with closing(sqlite3.connect(Path(path).as_uri() + '?mode=ro',
                                                uri=True, timeout=0)) as connection:
                        connection.row_factory = sqlite3.Row
                        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
                        for table in tables:
                            if time.monotonic() >= deadline:
                                raise TimeoutError('admission diagnostic read budget elapsed')
                            evidence['tables'][table] = [dict(row) for row in
                                connection.execute('SELECT * FROM ' + table + ' LIMIT 16')]
        except Exception as error:
            evidence['diagnostic_errors'].append({'phase': phase, 'type': type(error).__name__,
                                                  'message': str(error)})
        try:
            storage = self.admission_storage
            if not storage._lock.acquire(timeout=.01):
                raise TimeoutError('admission diagnostic trace lock elapsed')
            try:
                # Copy the queue before allocating event dictionaries: a
                # same-thread connection destructor can append under the RLock.
                snapshots = tuple(storage.events)
                evidence['storage'] = {'imports': storage.imports, 'operations': storage.operations,
                    'retained_sql_operations': [dict(event) for event in snapshots]}
            finally:
                storage._lock.release()
            (storage.root / (phase + '.json')).write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        except Exception as error:
            evidence['diagnostic_errors'].append({'phase': phase, 'type': type(error).__name__,
                                                  'message': str(error)})

    @staticmethod
    def make_command(execution_id, payload=None):
        return ExecutionCommandV2(execution_id, execution_id, "test-registry", "test-run", None,
            "child", 1, RetryPolicy(), 10, {} if payload is None else payload)

    def capability(self, command=None, lease=None, budget=None):
        return HandlerChildren(self.kernel, command or self.command, lease or self.lease,
                               budget or self.budget, self.spec, journal=self.journal)

    def enqueue(self, *, target="child-1", request="request-1", action="run", capability=None):
        capability = capability or self.children
        return capability._enqueue(request_id=request, child_id=target, action=action,
            child_command=self.make_command(target) if action == "run" else None,
            envelope=capability._budget(request, 10))

    def count(self, table):
        with self.journal._read_connection(.5) as (connection, _):
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def assert_empty(self):
        self.assertEqual(0, self.count("sdk_child_requests"))
        self.assertEqual(0, self.count("sdk_child_waits"))

    def test_capacity_rejects_second_child_without_leaking_request_or_wait(self):
        first = self.enqueue()
        with self.assertRaises(ChildExecutionError) as caught:
            self.enqueue(target="child-2", request="request-2")
        self.assertEqual("child_capacity_exhausted", caught.exception.code)
        self.assertEqual(1, self.count("sdk_child_requests"))
        self.assertEqual(1, self.count("sdk_child_waits"))
        self.children.store.finish(first, "failed", error={"code": "done", "message": "done"})
        second = self.enqueue(target="child-2", request="request-2")
        self.assertEqual("pending", second["state"])

    def test_concurrent_parents_share_one_durable_capacity_reservation(self):
        other_command = self.make_command("other-parent")
        other_lease = ExecutionLease("other-parent", "other-lease", "worker", 1, 1, time.time() + 60, 1)
        other = self.capability(command=other_command, lease=other_lease)
        barrier = threading.Barrier(2)
        outcomes = []

        def admit(capability, target):
            barrier.wait(timeout=2)
            try:
                outcomes.append(self.enqueue(capability=capability, target=target))
            except ChildExecutionError as exc:
                outcomes.append(exc)

        threads = [threading.Thread(target=admit, args=(capability, target))
                   for capability, target in ((self.children, "child-one"), (other, "child-two"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(1, sum(isinstance(item, dict) for item in outcomes))
        self.assertEqual(["child_capacity_exhausted"], [item.code for item in outcomes if isinstance(item, ChildExecutionError)])
        self.assertEqual(1, self.count("sdk_child_requests"))
        self.assertEqual(1, self.count("sdk_child_waits"))

    def test_depth_and_revoked_parent_reject_before_registration(self):
        self.kernel.depth = 1
        with self.assertRaises(ChildExecutionError) as caught:
            self.enqueue()
        self.assertEqual("child_depth_exceeded", caught.exception.code)
        self.assert_empty()
        self.kernel.depth, self.kernel.live = 0, False
        with self.assertRaises(ChildExecutionError) as caught:
            self.enqueue()
        self.assertEqual("parent_authority_revoked", caught.exception.code)
        self.assert_empty()

    def test_cycle_rejected_before_registration_and_existing_wait_preserved(self):
        with self.journal._transaction() as (connection, now):
            connection.execute("INSERT INTO sdk_child_waits VALUES(?,?,?,?,?,?,?,?,?,'open',?,NULL)",
                ("test-store", "existing-wait", "child-1", 1, 1, "parent", "child_result", now, now + 30, now))
        with self.assertRaises(ChildExecutionError) as caught:
            self.enqueue()
        self.assertEqual("child_wait_cycle", caught.exception.code)
        self.assertEqual(0, self.count("sdk_child_requests"))
        self.assertEqual(1, self.count("sdk_child_waits"))

    def test_retry_request_keeps_original_child_and_deadline(self):
        first = self.enqueue()
        replay = self.enqueue(target="new-unused-id")
        self.assertEqual(first["child_execution_id"], replay["child_execution_id"])
        self.assertEqual(first["budget_json"], replay["budget_json"])
        self.assertEqual(1, self.count("sdk_child_requests"))
        self.assertEqual(1, self.count("sdk_child_waits"))
        self.assertLessEqual(json.loads(first["budget_json"])["constraints"][-1]["deadline_at"], time.time() + 10)

    def test_request_id_cannot_identify_different_payload(self):
        self.enqueue()
        with self.assertRaises(ChildExecutionError) as caught:
            self.children._enqueue(request_id="request-1", child_id="new-id", action="run",
                child_command=self.make_command("new-id", {"different": True}),
                envelope=self.children._budget("request-1", 10))
        self.assertEqual("child_request_conflict", caught.exception.code)
        self.assertEqual(1, self.count("sdk_child_requests"))

    def test_child_failure_returns_original_result_and_replays_without_dispatch(self):
        row = self.enqueue()
        result = {"execution_id": "child-1", "status": "failed", "value": None,
                  "error": {"code": "actual_provider_failure", "message": "raw provider error", "details": {"status": 401}}}
        self.children.store.finish(row, "failed", result=result)
        for _ in range(2):
            with self.assertRaises(ChildExecutionError) as caught:
                self.children._await(row)
            self.assertEqual(result, caught.exception.result)
            self.assertEqual("actual_provider_failure", caught.exception.code)
        self.assertEqual(1, self.count("sdk_child_requests"))

    def test_missing_target_and_expired_budget_leave_no_reservation(self):
        with self.assertRaises(ChildExecutionError) as caught:
            self.children.wait_for("missing", request_id="missing")
        self.assertEqual("child_missing", caught.exception.code)
        self.assert_empty()
        checkpoint = sample_clock()
        past = BudgetEnvelope((), checkpoint).derive(source="run", origin_id="expired", deadline_at=checkpoint.wall_at - 1)
        with self.assertRaises(ChildExecutionError) as caught:
            self.capability(budget=past)._budget("late", 10)
        self.assertEqual("parent_budget_exhausted", caught.exception.code)
        self.assert_empty()

    def test_observe_waits_do_not_occupy_child_execution_capacity(self):
        observed = self.enqueue(target="running-target", request="observe", action="observe")
        child = self.enqueue()
        self.assertEqual("observe", observed["action"])
        self.assertEqual("run", child["action"])
        self.assertEqual(2, self.count("sdk_child_waits"))
        self.kernel.targets["running-target"] = SimpleNamespace(state="running")
        service = ChildService(SimpleNamespace(kernel=self.kernel), self.journal)
        service._observe_waits()
        self.assertEqual(0, service.health()["active_workers"])

    def test_service_validates_parent_before_submission_after_durable_admission(self):
        row = self.enqueue()
        self.kernel.live = False
        calls = []
        runtime = SimpleNamespace(kernel=self.kernel, submit_child=lambda *args, **kwargs: calls.append(args))
        ChildService(runtime, self.journal)._execute(row)
        self.assertEqual([], calls)
        response = self.children.store.request("parent", "request-1")
        self.assertEqual("failed", response["state"])
        self.assertIn("original parent fence", response["error_json"])

    def test_unconfirmed_parent_wait_exhausts_actual_budget_without_reserving_capacity(self):
        self.kernel.limits["parent"] = {"depth": 0, "entry_state": "pending", "entry_attempt": 1, "entry_fence": 1}
        budget = self.budget.derive(source="tool", origin_id="entry-wait-bound", timeout_seconds=.03)
        with self.assertRaises(ChildExecutionError) as caught:
            self.children._enqueue(request_id="unconfirmed", child_id="child", action="run",
                child_command=self.make_command("child"), envelope=budget)
        self.assertEqual("parent_entry_confirmation_timeout", caught.exception.code)
        self.assert_empty()

    def test_parent_revocation_during_entry_wait_has_causal_error_and_no_reservation(self):
        def revoke(execution_id):
            self.kernel.live = False
            return {"depth": 0, "entry_state": "pending", "entry_attempt": 1, "entry_fence": 1}

        with patch.object(self.kernel, "get_execution_limits", revoke):
            with self.assertRaises(ChildExecutionError) as caught:
                self.enqueue()
        self.assertEqual("parent_authority_revoked", caught.exception.code)
        self.assertIn("original parent fence", str(caught.exception))
        self.assert_empty()

    def test_partial_registration_replays_same_child_submission_after_reopen(self):
        row = self.enqueue()
        calls = []
        result = {"execution_id": row["child_execution_id"], "status": "succeeded", "value": {"answer": 42}, "error": None}

        def submit_child(command, **kwargs):
            calls.append(command.execution_id)
            # Submission survived, but the service crashed before marking its
            # journal request running. Reopening uses the same execution ID.
            self.kernel.targets[command.execution_id] = SimpleNamespace(state="succeeded",
                result=SimpleNamespace(to_dict=lambda: result))

        runtime = SimpleNamespace(kernel=self.kernel, submit_child=submit_child)
        submit_child(self.make_command(row["child_execution_id"]))
        service = ChildService(runtime, self.journal)
        service._execute(row)
        self.assertEqual([row["child_execution_id"]] * 2, calls)
        self.assertEqual(result, self.children._await(row))

    def test_first_child_waits_for_actual_parent_entry_confirmation(self):
        entered, waiting, release = threading.Event(), threading.Event(), threading.Event()
        results, errors = [], []
        self.admission_evidence['budgets'] = {'parent': 3, 'child': 2,
            'waiting': 2, 'confirmation_release': 3, 'driver_join': 5}

        def leaf(payload, context):
            self.record_admission_entry('child_entry', context)
            return {"child": "executed"}

        def parent(payload, context):
            entered.set()
            self.record_admission_entry('parent_entry', context)
            return self.admission_stage('child_run', lambda: context.children.run(
                "leaf", {}, request_id="first", timeout_seconds=2), timeout_seconds=2)

        leaf.__execution_kernel_revision__ = "entry-wait-leaf"
        parent.__execution_kernel_revision__ = "entry-wait-parent"
        with Runtime(str(self.journal.path.parent / "runtime.sqlite3"), {"parent": parent, "leaf": leaf},
                     isolation_mode="thread") as runtime:
            self.admission_evidence['observation_path'] = str(runtime.observation_journal.path)
            confirm = runtime.kernel.confirm_handler_entry
            limits = runtime.kernel.get_execution_limits

            def delayed_confirm(lease, envelope, **kwargs):
                if lease.execution_id == "parent":
                    waiting.set()
                    if not release.wait(3):
                        raise TimeoutError("test did not release parent confirmation")
                return self.admission_stage('confirm_handler_entry',
                    lambda: confirm(lease, envelope, **kwargs),
                    envelope=envelope, arguments={key: kwargs[key] for key in ('timeout_seconds',)
                                                  if key in kwargs})

            def observed_limits(execution_id):
                value = self.admission_stage('get_execution_limits',
                    lambda: limits(execution_id), execution_id=execution_id)
                if execution_id == "parent" and value is not None and value["entry_state"] == "pending":
                    waiting.set()
                return value

            def run():
                try:
                    results.append(self.admission_stage('run_once', runtime.run_once))
                except Exception as exc:
                    errors.append(exc)

            runtime.submit(runtime.command("parent", execution_id="parent", idempotency_key="parent",
                correlation_id="entry-wait", timeout_seconds=3, payload={}))
            with patch.object(runtime.kernel, "confirm_handler_entry", delayed_confirm), patch.object(
                    runtime.kernel, "get_execution_limits", observed_limits):
                thread = threading.Thread(target=run)
                thread.start()
                try:
                    self.assertTrue(waiting.wait(2))
                    self.assertFalse(entered.is_set())
                    self.assertEqual(limits("parent")["entry_state"], "pending")
                    with runtime.observation_journal._read_connection(.5) as (connection, _):
                        self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM sdk_child_requests").fetchone()[0])
                finally:
                    release.set()
                    thread.join(5)
                    self.admission_evidence['driver_alive'] = thread.is_alive()
                    self.capture_admission('before_cleanup', runtime.kernel)
                self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual("succeeded", results[0].state, results[0].to_dict())
            self.assertEqual({"child": "executed"}, results[0].result.value["value"])

    def test_targeted_child_claim_fences_parent_cancel_between_verify_and_claim(self):
        with SQLiteKernel(self.journal.path.parent / "kernel.sqlite3") as kernel:
            parent = self.make_command("parent")
            kernel.submit(parent)
            lease = kernel.claim_and_start("parent-owner")
            budget = kernel.prepare_execution_budget(lease).enter_handler(10, origin_id="execution:parent")
            kernel.confirm_handler_entry(lease, budget)
            kernel.submit_child(self.make_command("child"), lease, budget)
            kernel.verify(lease)
            # A concurrent cancellation lands after the coordinator's verify
            # but before the targeted claim's transaction.
            with SQLiteKernel(kernel.db_path) as other:
                other.cancel("parent", expected_revision=lease.revision)
            with self.assertRaises(StaleFenceError):
                kernel.claim_and_start("child-owner", execution_id="child")
            self.assertEqual("queued", kernel.get("child").state)
            self.assertEqual(0, kernel.get("child").attempt)

    def test_targeted_child_claim_rejects_expired_inherited_work_window(self):
        offset = [0]
        self.admission_evidence['budgets'] = {'parent': 10, 'child_call': .5,
                                             'sample_attempt': .1, 'wall_offset': 1}
        with SQLiteKernel(self.journal.path.parent / "deadline.sqlite3", now=lambda: time.time() + offset[0]) as kernel:
            try:
                self.admission_stage('submit_parent', lambda: kernel.submit(self.make_command("parent")))
                lease = self.admission_stage('claim_parent', lambda: kernel.claim_and_start("parent-owner"))
                budget = kernel.prepare_execution_budget(lease).enter_handler(10, origin_id="execution:parent")
                self.admission_stage('confirm_parent', lambda: kernel.confirm_handler_entry(lease, budget))
                child_budget = budget.derive(source="tool", origin_id="short-child-call", timeout_seconds=.5)
                self.admission_evidence['child_budget'] = child_budget.to_dict()
                self.admission_stage('submit_child', lambda: kernel.submit_child(
                    self.make_command("child"), lease, child_budget))
                offset[0] = 1
                with self.assertRaises(CASConflictError):
                    self.admission_stage('claim_child', lambda: kernel.claim_and_start(
                        "child-owner", execution_id="child"))
                self.assertEqual(0, kernel.get("child").attempt)
            finally:
                self.capture_admission('before_cleanup', kernel)

    def test_recovered_adoption_keeps_capacity_until_running_child_settles(self):
        with SQLiteKernel(self.journal.path.parent / "adoption.sqlite3") as kernel:
            kernel.submit(self.make_command("parent"))
            lease = kernel.claim_and_start("parent-owner")
            budget = kernel.prepare_execution_budget(lease).enter_handler(10, origin_id="execution:parent")
            kernel.confirm_handler_entry(lease, budget)
            kernel.submit(self.make_command("adopted"))
            children = HandlerChildren(kernel, self.make_command("parent"), lease, budget, self.spec, journal=self.journal)
            row = children._enqueue(request_id="adopt", child_id="adopted", action="adopt",
                child_command=None, envelope=children._budget("adopt", 5))
            kernel.adopt_child("adopted", lease, budget)
            child_lease = kernel.claim_and_start("child-owner", execution_id="adopted")
            running = threading.Event()
            errors = []

            def forbidden_adopt(*args, **kwargs):
                raise AssertionError("recovery must not re-adopt an already running target")

            service = ChildService(SimpleNamespace(kernel=kernel, adopt_child=forbidden_adopt), self.journal)
            finish = service.store.finish

            def unexpected_finish(*args, **kwargs):
                if kernel.get("adopted").state == "running":
                    errors.append("request settled before the owned child")
                return finish(*args, **kwargs)

            original_get = kernel.get

            def observed_get(identity):
                snapshot = original_get(identity)
                if identity == "adopted" and snapshot.state == "running":
                    running.set()
                return snapshot

            service.store.finish = unexpected_finish
            with patch.object(kernel, "get", observed_get):
                thread = threading.Thread(target=service._execute, args=(row,))
                thread.start()
                try:
                    self.assertTrue(running.wait(2))
                    self.assertIn(children.store.request("parent", "adopt")["state"], ("pending", "running"))
                    with self.assertRaises(ChildExecutionError) as caught:
                        children._enqueue(request_id="second", child_id="second", action="run",
                            child_command=self.make_command("second"), envelope=children._budget("second", 5))
                    self.assertEqual("child_capacity_exhausted", caught.exception.code)
                    snapshot = original_get("adopted")
                    result = ExecutionResultV2(result_id="adopted-result", execution_id="adopted", status="succeeded",
                        attempt=child_lease.attempt, fence=child_lease.fence, effect_ids=[],
                        started_at=snapshot.started_at, completed_at=kernel.current_time(),
                        correlation_id="test-run", causation_id=None, value={"recovered": True}, error=None)
                    kernel.complete(child_lease, result)
                finally:
                    thread.join(3)
                    if thread.is_alive():
                        service._stop.set()
                        thread.join(2)
                self.assertFalse(thread.is_alive())
            self.assertEqual([], errors)
            self.assertEqual({"recovered": True}, children._await(row)["value"])

    def test_adoption_commit_followed_by_transport_error_cleans_up_owned_child(self):
        with SQLiteKernel(self.journal.path.parent / "adoption-error.sqlite3") as kernel:
            kernel.submit(self.make_command("parent"))
            lease = kernel.claim_and_start("parent-owner")
            budget = kernel.prepare_execution_budget(lease).enter_handler(10, origin_id="execution:parent")
            kernel.confirm_handler_entry(lease, budget)
            kernel.submit(self.make_command("adopted"))
            children = HandlerChildren(kernel, self.make_command("parent"), lease, budget, self.spec, journal=self.journal)
            row = children._enqueue(request_id="adopt", child_id="adopted", action="adopt",
                child_command=None, envelope=children._budget("adopt", 5))

            def uncertain_adopt(execution_id, *, parent_lease, budget_envelope, timeout_seconds=None):
                kernel.adopt_child(execution_id, parent_lease, budget_envelope)
                raise ConnectionError("response lost after committed adoption")

            runtime = SimpleNamespace(kernel=kernel, adopt_child=uncertain_adopt, cancel=kernel.cancel)
            ChildService(runtime, self.journal)._execute(row)
            self.assertEqual("cancelled", kernel.get("adopted").state)
            response = children.store.request("parent", "adopt")
            self.assertEqual("failed", response["state"])
            self.assertEqual("cancelled", json.loads(response["response_json"])["status"])


if __name__ == "__main__":
    unittest.main()
