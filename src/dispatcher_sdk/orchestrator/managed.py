"""Transactional registration for opted-in managed Runs.

This module does not grant execution authority. Kernel registration and the
control barrier must succeed before the managed facade can resume a Run.
"""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from ..execution_kernel import ExecutionCommandV2
from ..execution_kernel.cancellation import CancellationJournal, inspect_cancellation_journal
from .cancellation import _sandbox_facts
from .contracts import (CommandConflict, OrchestrationError, RevisionConflict, TERMINAL,
                        canonical, clone, digest, identifier, integer)
from .reducer import reduce_operation
from .types import RunSnapshot


def _topological_commands(commands: list[list[Any]]) -> list[list[Any]]:
    """Normalize a task graph while requiring predecessors before reduction."""
    by_id = {item[0]: item for item in commands}
    if len(by_id) != len(commands):
        raise OrchestrationError("managed task identifiers must be unique")
    dependents: dict[str, list[str]] = {task_id: [] for task_id in by_id}
    indegree: dict[str, int] = {}
    for task_id, _, dependencies in commands:
        if any(type(value) is not str or not value.strip() for value in dependencies):
            raise OrchestrationError("dependencies must be task identifiers")
        if len(set(dependencies)) != len(dependencies) or task_id in dependencies:
            raise OrchestrationError("duplicate or self dependency")
        if any(value not in by_id for value in dependencies):
            raise OrchestrationError("managed dependency is not a task in this Run")
        dependencies.sort()
        indegree[task_id] = len(dependencies)
        for dependency in dependencies:
            dependents[dependency].append(task_id)
    ready = [task_id for task_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        task_id = heapq.heappop(ready)
        ordered.append(by_id[task_id])
        for dependent in dependents[task_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(ordered) != len(commands):
        raise OrchestrationError("managed task graph contains a cycle")
    return ordered


class ManagedRunMixin:
    def _managed_kernel_in_transaction(self, name: str):
        """Return the Kernel's participant writer for a co-located store.

        A managed control transition must share the same SQLite commit as the
        Orchestrator intent. Separate database files need a durable multi-store
        coordinator and are deliberately ineligible for these operations.
        """
        path = getattr(self.kernel, "db_path", None)
        if path is None:
            raise OrchestrationError("managed control requires a durable Kernel participant")
        if str(Path(path).resolve()) != self.db_path:
            raise OrchestrationError("managed control requires a co-located Kernel store")
        method = getattr(self.kernel, name, None)
        if not callable(method):
            raise OrchestrationError("Kernel lacks the managed control participant")
        return method

    def register_managed_run(
        self, run_id: str, *, request_id: str,
        definition: Any, task_commands: Sequence[tuple[str, ExecutionCommandV2, list[str]]],
        max_claims: int, deadline_at: float, input: Any = None,
    ) -> RunSnapshot:
        """Atomically create a paused Run, its task graph and dispatch intents.

        The matching paused Kernel gate is installed in the same SQLite
        transaction. Failure rolls back the Run and its dispatch intents.
        """
        for label, value in (("run_id", run_id), ("request_id", request_id)):
            identifier(value, label)
        integer(max_claims, "max_claims")
        if max_claims > (1 << 63) - 1:
            raise OrchestrationError("max_claims exceeds SQLite integer range")
        if (type(deadline_at) not in (int, float)
                or not math.isfinite(deadline_at) or deadline_at <= 0):
            raise OrchestrationError("deadline_at must be finite and positive")
        frozen_definition = clone(definition)
        frozen_input = clone(input)
        frozen_commands = []
        for task_id, command, dependencies in task_commands:
            identifier(task_id, "task_id")
            if type(command) is not ExecutionCommandV2:
                raise OrchestrationError("managed task command must be ExecutionCommandV2")
            if not command.execution_id.startswith("sdk-managed:") or command.correlation_id != run_id:
                raise OrchestrationError("managed command identity differs from Run")
            if type(dependencies) is not list:
                raise OrchestrationError("dependencies must be a list")
            frozen_commands.append([task_id, command.to_dict(), list(dependencies)])
        frozen_commands = _topological_commands(frozen_commands)
        spec_digest = digest({
            "input": frozen_input, "definition": frozen_definition,
            "commands": frozen_commands,
            "max_claims": max_claims,
            "deadline_at": float(deadline_at),
        })
        now = float(self.clock())
        participant = self._managed_kernel_in_transaction("register_run_control_in_transaction")
        with self._transaction() as connection:
            old = connection.execute(
                "SELECT run_id,spec_digest FROM sdk_managed_runs WHERE request_id=?", (request_id,)
            ).fetchone()
            if old is not None:
                if old["run_id"] != run_id or old["spec_digest"] != spec_digest:
                    raise CommandConflict("managed request identity already has different content")
                return self._load(connection, run_id)
            if connection.execute("SELECT 1 FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone():
                raise CommandConflict("Run identity is already in use")
            if connection.execute(
                "SELECT 1 FROM kernel_run_controls WHERE run_id=?", (run_id,)
            ).fetchone():
                raise CommandConflict("Kernel control identity is already in use")
            state: RunSnapshot = {
                "run_id": run_id, "revision": 0, "state": "running", "generation": 0,
                "input": frozen_input, "definition": frozen_definition,
                "application_state": None, "tasks": {}, "waits": {}, "signals": {},
            }
            connection.execute("INSERT INTO sdk_runs VALUES(?,?,?)", (run_id, 0, "running"))
            connection.execute(
                "INSERT INTO sdk_managed_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (run_id, request_id, spec_digest, "paused", 0, 0, max_claims,
                 float(deadline_at), now, now),
            )
            connection.execute(
                "INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                (run_id, 0, "paused", 0, "[]", None, now),
            )
            participant(
                connection, run_id, max_claims=max_claims,
                deadline_at=float(deadline_at),
            )
            registrations = []
            for task_id, command, dependencies in frozen_commands:
                reduce_operation(state, {"kind": "add_task", "task_id": task_id,
                                         "command": command, "dependencies": dependencies})
                registrations.append((task_id, 0, state["tasks"][task_id]["attempts"][0]))
            self._register_executions(connection, state, registrations)
            intents = []
            for task_id, _, dependencies in frozen_commands:
                if not dependencies:
                    intents.extend(reduce_operation(state, {"kind": "dispatch", "task_id": task_id}))
            for ordinal, intent in enumerate(intents):
                intent["generation"] = 0
                connection.execute(
                    "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) VALUES(?,?,?,?)",
                    (run_id, "managed-create", ordinal, canonical(intent)),
                )
            self._save(connection, state)
            self._event(connection, state, "managed.created", {
                "request_id": request_id, "spec_digest": spec_digest,
                "task_count": len(frozen_commands), "control_state": "paused",
            })
            self._write_receipt(connection, run_id, "managed-create", spec_digest, state)
            return self._load(connection, run_id)

    def get_managed_control(self, run_id: str) -> dict[str, Any]:
        """Read the durable control row without loading task history."""
        identifier(run_id, "run_id")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT run_id,request_id,spec_digest,control_state,control_epoch,generation,"
                "max_claims,deadline_at,created_at,updated_at FROM sdk_managed_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise OrchestrationError("Run is not registered for managed control")
            return dict(row)
        finally:
            connection.close()

    @staticmethod
    def _dispatch_accepted_tasks(state: RunSnapshot) -> tuple[list[dict], set[tuple[str, str]]]:
        """Queue tasks whose current predecessor attempts were explicitly accepted."""
        intents: list[dict] = []
        changes: set[tuple[str, str]] = set()
        for task_id, task in state["tasks"].items():
            current = task["attempts"][-1]
            if current["state"] != "planned":
                continue
            if not task["dependencies"]:
                # Roots are queued at creation and never redispatched here.
                continue
            if any(not state["tasks"][dependency].get("managed_acceptance", {}).get("accepted")
                   or state["tasks"][dependency]["managed_acceptance"].get("attempt")
                   != len(state["tasks"][dependency]["attempts"]) - 1
                   for dependency in task["dependencies"]):
                continue
            intents.extend(reduce_operation(state, {"kind": "dispatch", "task_id": task_id}))
            changes.add(("attempt", canonical([task_id, len(task["attempts"]) - 1])))
        return intents, changes

    def record_managed_acceptance(
        self, run_id: str, task_id: str, *, request_id: str,
        expected_revision: int, accepted: bool, evidence: dict[str, Any],
    ) -> RunSnapshot:
        """Record an application decision and dispatch newly eligible successors.

        SDK terminal status never implies business acceptance. The application
        supplies durable evidence, while this transaction owns the graph
        advancement and its outbox. A paused Run records the decision but does
        not queue new work until a later active advancement.
        """
        for label, value in (("run_id", run_id), ("task_id", task_id),
                             ("request_id", request_id)):
            identifier(value, label)
        integer(expected_revision, "expected_revision")
        if type(accepted) is not bool:
            raise OrchestrationError("accepted must be a boolean")
        if type(evidence) is not dict or not evidence:
            raise OrchestrationError("acceptance requires nonempty application evidence")
        frozen_evidence = clone(evidence)
        fingerprint = digest({
            "kind": "acceptance", "run_id": run_id, "task_id": task_id,
            "accepted": accepted,
            "evidence": frozen_evidence,
        })
        with self._transaction() as connection:
            receipt = connection.execute(
                "SELECT digest,response FROM sdk_managed_commands WHERE run_id=? AND request_id=?",
                (run_id, request_id),
            ).fetchone()
            if receipt is not None:
                if receipt["digest"] != fingerprint:
                    raise CommandConflict("managed request identity already has different content")
                return self._load_at(connection, run_id, json.loads(receipt["response"])["revision"])
            control = connection.execute(
                "SELECT control_state,generation FROM sdk_managed_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if control is None:
                raise OrchestrationError("unknown managed Run")
            state = self._load(connection, run_id)
            if state["revision"] != expected_revision:
                raise RevisionConflict("managed Run revision changed")
            task = state["tasks"].get(task_id)
            if task is None:
                raise OrchestrationError("unknown managed task")
            attempt_index = len(task["attempts"]) - 1
            current = task["attempts"][attempt_index]
            if current["state"] not in TERMINAL:
                raise OrchestrationError("managed task must settle before acceptance")
            if task.get("managed_acceptance") is not None:
                raise CommandConflict("current managed task attempt already has an acceptance decision")
            task["managed_acceptance"] = {
                "attempt": attempt_index, "generation": current.get("generation", 0),
                "accepted": accepted, "evidence": frozen_evidence,
            }
            changes: set[tuple[str, str]] = {("task", task_id)}
            intents: list[dict] = []
            if accepted and control["control_state"] == "active":
                intents, dispatch_changes = self._dispatch_accepted_tasks(state)
                changes.update(dispatch_changes)
            command_id = "managed-accept:" + request_id
            for ordinal, intent in enumerate(intents):
                intent["generation"] = control["generation"]
                connection.execute(
                    "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) VALUES(?,?,?,?)",
                    (run_id, command_id, ordinal, canonical(intent)),
                )
            state["revision"] += 1
            self._save(connection, state, changes=changes)
            self._event(connection, state, "managed.acceptance", {
                "task_id": task_id, "attempt": attempt_index,
                "accepted": accepted, "dispatch_count": len(intents),
            })
            connection.execute(
                "INSERT INTO sdk_managed_commands(run_id,request_id,digest,response) VALUES(?,?,?,?)",
                (run_id, request_id, fingerprint,
                 canonical({"run_id": run_id, "revision": state["revision"]})),
            )
            return state

    def _request_managed_control(
        self, run_id: str, *, request_id: str, kind: str,
        expected_run_revision: int, expected_control_epoch: int,
        mode: str | None = None,
        drain_execution_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Record a control intent before touching a separate Kernel store."""
        identifier(run_id, "run_id")
        identifier(request_id, "request_id")
        integer(expected_run_revision, "expected_run_revision")
        integer(expected_control_epoch, "expected_control_epoch")
        if kind not in {"pause", "resume"}:
            raise OrchestrationError("unsupported managed control request")
        if kind == "pause" and mode not in {"drain", "interrupt"}:
            raise OrchestrationError("pause mode must be drain or interrupt")
        if kind == "resume" and mode is not None:
            raise OrchestrationError("resume has no pause mode")
        if kind == "resume" and drain_execution_ids:
            raise OrchestrationError("resume cannot preserve drain permissions")
        if (isinstance(drain_execution_ids, (str, bytes, bytearray))
                or not isinstance(drain_execution_ids, Sequence)):
            raise OrchestrationError("drain execution identifiers must be a sequence")
        if any(type(value) is not str or not value.strip() for value in drain_execution_ids):
            raise OrchestrationError("drain execution identifiers must be nonempty strings")
        requested_drain_ids = tuple(sorted(set(drain_execution_ids)))
        if len(requested_drain_ids) > 1000:
            raise OrchestrationError("drain set exceeds the 1000-execution control limit")
        if mode == "interrupt" and requested_drain_ids:
            raise OrchestrationError("interrupt pause cannot grant drain executions")
        fingerprint = digest({
            "kind": kind, "run_id": run_id, "mode": mode,
            "drain_execution_ids": list(requested_drain_ids),
        })
        with self._transaction() as connection:
            receipt = connection.execute(
                "SELECT digest,response FROM sdk_managed_commands WHERE run_id=? AND request_id=?",
                (run_id, request_id),
            ).fetchone()
            if receipt is not None:
                if receipt["digest"] != fingerprint:
                    raise CommandConflict("managed request identity already has different content")
                return json.loads(receipt["response"])
            run = connection.execute(
                "SELECT revision,state FROM sdk_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            control = connection.execute(
                "SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if run is None or control is None:
                raise OrchestrationError("unknown managed Run")
            if run["state"] != "running":
                raise OrchestrationError("terminal Run cannot change managed control state")
            if run["revision"] != expected_run_revision or control["control_epoch"] != expected_control_epoch:
                raise RevisionConflict("managed Run observation changed")
            source_state = control["control_state"]
            if kind == "pause" and source_state != "active":
                raise OrchestrationError("only active Run may request pause")
            if kind == "resume" and source_state != "paused":
                raise OrchestrationError("only paused Run may request resume")
            if requested_drain_ids:
                placeholders = ",".join("?" for _ in requested_drain_ids)
                count = connection.execute(
                    "SELECT COUNT(*) FROM sdk_executions s "
                    "JOIN kernel_executions k ON k.execution_id=s.execution_id "
                    "WHERE s.run_id=? AND s.generation=? "
                    "AND k.state IN ('leased','running') "
                    f"AND s.execution_id IN ({placeholders})",
                    (run_id, control["generation"], *requested_drain_ids),
                ).fetchone()[0]
                if count != len(requested_drain_ids):
                    raise OrchestrationError(
                        "drain set requires a previously leased execution; "
                        "queued child wait registration is not available"
                    )
            drain_ids = requested_drain_ids
            if kind == "pause" and mode == "drain":
                admitted = connection.execute(
                    "SELECT m.execution_id FROM kernel_managed_executions m "
                    "JOIN kernel_executions k ON k.execution_id=m.execution_id "
                    "WHERE m.run_id=? AND m.generation=? "
                    "AND k.state IN ('leased','running') LIMIT 1001",
                    (run_id, control["generation"]),
                ).fetchall()
                if len(admitted) > 1000:
                    raise OrchestrationError("drain pause exceeds the 1000-execution control limit")
                drain_ids = tuple(sorted(set(requested_drain_ids) | {row[0] for row in admitted}))
            target_state = "pausing" if kind == "pause" else "active"
            target_epoch = expected_control_epoch + 1
            participant = self._managed_kernel_in_transaction("set_run_control_in_transaction")
            if participant is not None:
                participant(
                    connection, run_id, expected_epoch=expected_control_epoch,
                    state=target_state, generation=control["generation"],
                    drain_execution_ids=drain_ids,
                )
            now = float(self.clock())
            changed = connection.execute(
                "UPDATE sdk_managed_runs SET control_state=?,control_epoch=?,updated_at=? "
                "WHERE run_id=? AND control_state=? AND control_epoch=?",
                (target_state, target_epoch, now, run_id, source_state, expected_control_epoch),
            ).rowcount
            if changed != 1:
                raise RevisionConflict("managed control state changed")
            if kind == "pause":
                cleanup_rows = connection.execute(
                    "SELECT m.execution_id,m.generation FROM kernel_managed_executions m "
                    "JOIN kernel_executions e ON e.execution_id=m.execution_id "
                    "WHERE m.run_id=? AND m.generation=? "
                    "AND e.state IN ('running','recovery_required') "
                    "AND e.started_at IS NOT NULL LIMIT 1001",
                    (run_id, control["generation"]),
                ).fetchall()
                if len(cleanup_rows) > 1000:
                    raise OrchestrationError(
                        "pause exceeds the 1000-execution cleanup transaction limit"
                    )
                for execution in cleanup_rows:
                    connection.execute(
                        "INSERT INTO sdk_managed_cleanup_obligations "
                        "(run_id,control_epoch,execution_id,generation,state,evidence,created_at,updated_at) "
                        "VALUES(?,?,?,?, 'pending',NULL,?,?)",
                        (run_id, target_epoch, execution["execution_id"],
                         execution["generation"], now, now),
                    )
            cancel_count = 0
            if kind == "pause" and mode == "interrupt":
                pending_cancels = connection.execute(
                    "SELECT execution_id,command,generation FROM sdk_executions "
                    "WHERE run_id=? AND active=1 ORDER BY execution_id LIMIT 1001",
                    (run_id,),
                ).fetchall()
                if len(pending_cancels) > 1000:
                    raise OrchestrationError(
                        "interrupt pause exceeds the 1000-execution transaction limit"
                    )
                for ordinal, execution in enumerate(pending_cancels):
                    intent = {
                        "kind": "cancel", "execution_id": execution["execution_id"],
                        "reason": "managed interrupt pause", "command": json.loads(execution["command"]),
                        "generation": execution["generation"],
                    }
                    connection.execute(
                        "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) "
                        "VALUES(?,?,?,?)",
                        (run_id, "managed-interrupt:" + request_id, ordinal, canonical(intent)),
                    )
                cancel_count = len(pending_cancels)
            resulting_revision = run["revision"]
            if kind == "resume":
                state = self._load(connection, run_id)
                intents, changes = self._dispatch_accepted_tasks(state)
                if intents:
                    for ordinal, intent in enumerate(intents):
                        intent["generation"] = control["generation"]
                        connection.execute(
                            "INSERT INTO sdk_outbox(run_id,command_id,ordinal,payload) "
                            "VALUES(?,?,?,?)",
                            (run_id, "managed-resume:" + request_id, ordinal, canonical(intent)),
                        )
                    state["revision"] += 1
                    self._save(connection, state, changes=changes)
                    resulting_revision = state["revision"]
            response = {"run_id": run_id, "control_state": target_state,
                        "control_epoch": target_epoch, "generation": control["generation"],
                        "run_revision": resulting_revision, "mode": mode,
                        "drain_execution_ids": list(drain_ids),
                        "cancel_count": cancel_count}
            connection.execute(
                "INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                (run_id, target_epoch, target_state, control["generation"],
                 canonical(list(drain_ids)), mode, now),
            )
            connection.execute(
                "INSERT INTO sdk_managed_commands(run_id,request_id,digest,response) VALUES(?,?,?,?)",
                (run_id, request_id, fingerprint, canonical(response)),
            )
            self._event(connection, {
                "run_id": run_id, "revision": resulting_revision,
                "generation": control["generation"],
            }, "managed." + kind + ".requested", response)
            return response

    def _settle_managed_pause(self, run_id: str, *, expected_control_epoch: int) -> dict[str, Any]:
        """Mark pause complete after the caller verifies every execution gate."""
        identifier(run_id, "run_id")
        integer(expected_control_epoch, "expected_control_epoch")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT control_state,control_epoch,generation FROM sdk_managed_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise OrchestrationError("unknown managed Run")
            if row["control_state"] == "paused" and row["control_epoch"] == expected_control_epoch + 1:
                return {"run_id": run_id, "control_state": "paused",
                        "control_epoch": expected_control_epoch + 1,
                        "generation": row["generation"]}
            if row["control_epoch"] != expected_control_epoch:
                raise RevisionConflict("managed control epoch changed")
            if row["control_state"] != "pausing":
                raise OrchestrationError("managed Run is not pausing")
            transition = connection.execute(
                "SELECT pause_mode FROM sdk_managed_control_transitions "
                "WHERE run_id=? AND control_epoch=?",
                (run_id, expected_control_epoch),
            ).fetchone()
            if transition is None:
                raise OrchestrationError("managed pause transition is missing")
            if transition["pause_mode"] == "interrupt" and connection.execute(
                "SELECT 1 FROM sdk_outbox WHERE run_id=? AND delivered=0 "
                "AND command_id LIKE 'managed-interrupt:%' LIMIT 1",
                (run_id,),
            ).fetchone():
                raise OrchestrationError("managed interrupt cancellations are still pending")
            cleanup = connection.execute(
                "SELECT execution_id FROM sdk_managed_cleanup_obligations "
                "WHERE run_id=? AND control_epoch=? AND state='pending' LIMIT 1",
                (run_id, expected_control_epoch),
            ).fetchone()
            if cleanup is not None:
                raise OrchestrationError(
                    f"managed pause lacks cleanup evidence for {cleanup['execution_id']}"
                )
            participant = self._managed_kernel_in_transaction("set_run_control_in_transaction")
            if participant is not None:
                blocked = connection.execute(
                    "SELECT m.execution_id,COALESCE(e.state,'missing') AS state "
                    "FROM kernel_managed_executions m LEFT JOIN kernel_executions e "
                    "ON e.execution_id=m.execution_id WHERE m.run_id=? AND "
                    "((m.drain_allowed=1 AND (e.execution_id IS NULL OR e.state NOT IN "
                    "('succeeded','failed','timed_out','cancelled','dead'))) "
                    "OR e.state IN ('leased','running','recovery_required')) LIMIT 1",
                    (run_id,),
                ).fetchone()
                if blocked is not None:
                    raise OrchestrationError(
                        f"managed pause is blocked by {blocked['execution_id']} "
                        f"({blocked['state']})"
                    )
                effect = connection.execute(
                    "SELECT e.effect_id FROM kernel_effects e JOIN kernel_managed_executions m "
                    "ON m.execution_id=e.execution_id WHERE m.run_id=? "
                    "AND e.state IN ('performing','indeterminate') LIMIT 1",
                    (run_id,),
                ).fetchone()
                if effect is not None:
                    raise OrchestrationError(
                        f"managed pause is blocked by unresolved effect {effect['effect_id']}"
                    )
                participant(
                    connection, run_id, expected_epoch=expected_control_epoch,
                    state="paused", generation=row["generation"],
                )
            changed = connection.execute(
                "UPDATE sdk_managed_runs SET control_state='paused',control_epoch=?,updated_at=? "
                "WHERE run_id=? AND control_state='pausing' AND control_epoch=?",
                (expected_control_epoch + 1, float(self.clock()), run_id, expected_control_epoch),
            ).rowcount
            if changed != 1:
                raise RevisionConflict("managed control state changed")
            revision = connection.execute("SELECT revision FROM sdk_runs WHERE run_id=?", (run_id,)).fetchone()[0]
            response = {"run_id": run_id, "control_state": "paused",
                        "control_epoch": expected_control_epoch + 1,
                        "generation": row["generation"]}
            connection.execute(
                "INSERT INTO sdk_managed_control_transitions VALUES(?,?,?,?,?,?,?)",
                (run_id, expected_control_epoch + 1, "paused", row["generation"],
                 "[]", None, float(self.clock())),
            )
            self._event(connection, {"run_id": run_id, "revision": revision,
                                     "generation": row["generation"]}, "managed.paused", response)
            return response

    def _confirm_managed_cleanup_from_runtime(
        self, run_id: str, execution_id: str, *, control_epoch: int,
    ) -> dict[str, Any]:
        """Seal a cleanup obligation only from a bound Runtime cancellation receipt.

        The cancellation journal is a separate immutable evidence store. A
        missing receipt, thread-only revocation, unresolved sandbox operation,
        or unknown Effect leaves the obligation pending.
        """
        identifier(run_id, "run_id")
        identifier(execution_id, "execution_id")
        integer(control_epoch, "control_epoch")
        journal = getattr(self.runtime, "cancellation_journal", None)
        with self._transaction() as connection:
            obligation = connection.execute(
                "SELECT state,evidence FROM sdk_managed_cleanup_obligations "
                "WHERE run_id=? AND control_epoch=? AND execution_id=?",
                (run_id, control_epoch, execution_id),
            ).fetchone()
            if obligation is None:
                raise OrchestrationError("unknown managed cleanup obligation")
            if obligation["state"] == "confirmed":
                return json.loads(obligation["evidence"])
            if not isinstance(journal, CancellationJournal):
                raise OrchestrationError("trusted Runtime cancellation journal is unavailable")
            row = connection.execute(
                "SELECT k.* FROM kernel_executions k JOIN kernel_managed_executions m "
                "ON m.execution_id=k.execution_id WHERE k.execution_id=? AND m.run_id=?",
                (execution_id, run_id),
            ).fetchone()
            if row is None or row["state"] not in TERMINAL:
                raise OrchestrationError("execution authority has not settled")
            if connection.execute(
                "SELECT 1 FROM kernel_effects WHERE execution_id=? "
                "AND state IN ('performing','indeterminate') LIMIT 1",
                (execution_id,),
            ).fetchone():
                raise OrchestrationError("unresolved effect blocks cleanup confirmation")
            snapshot = self.kernel._snapshot(row)
            try:
                page = inspect_cancellation_journal(
                    journal.path, source_id=journal.source_id,
                    kernel_path=self.kernel.db_path, snapshot=snapshot, limit=1000,
                )
                sandbox_records, sandbox_issues = _sandbox_facts(connection, snapshot)
            except (OSError, ValueError, sqlite3.Error) as error:
                raise OrchestrationError("runtime cleanup evidence is unavailable") from error
            if page.truncated or sandbox_issues or any(
                not record["cleanup_confirmed"] for record in sandbox_records
            ):
                raise OrchestrationError("runtime cleanup evidence is incomplete")
            receipt = next((item for item in page.receipts
                            if "failure" not in item.phases
                            and item.phases.get("authority_revoked", {}).get("state") == "confirmed"
                            and item.phases.get("process_cleanup", {}).get("state") == "confirmed"
                            and (not sandbox_records or item.phases.get("remote_cleanup", {}).get("state")
                                 == "confirmed")), None)
            if receipt is None:
                raise OrchestrationError("no process-stop receipt confirms managed cleanup")
            proof = {
                "source": "runtime.cancellation_journal",
                "source_id": journal.source_id,
                "receipt_id": receipt.receipt_id,
                "command_digest": receipt.command_digest,
                "attempt": receipt.attempt,
                "fence": receipt.fence,
                "sandbox_operations": len(sandbox_records),
            }
            encoded = canonical(proof)
            connection.execute(
                "UPDATE sdk_managed_cleanup_obligations SET state='confirmed',evidence=?,updated_at=? "
                "WHERE run_id=? AND control_epoch=? AND execution_id=? AND state='pending'",
                (encoded, float(self.clock()), run_id, control_epoch, execution_id),
            )
            return proof

    def list_managed_control_transitions(
        self, run_id: str, *, after_epoch: int = -1, limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        """Page immutable transitions for Kernel barrier reconciliation."""
        identifier(run_id, "run_id")
        if type(after_epoch) is not int or after_epoch < -1:
            raise OrchestrationError("after_epoch must be an integer >= -1")
        integer(limit, "limit")
        if not 1 <= limit <= 100:
            raise OrchestrationError("limit must be between 1 and 100")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT control_epoch,control_state,generation,drain_execution_ids,pause_mode "
                "FROM sdk_managed_control_transitions WHERE run_id=? AND control_epoch>? "
                "ORDER BY control_epoch LIMIT ?",
                (run_id, after_epoch, limit),
            ).fetchall()
            return tuple({"control_epoch": row["control_epoch"],
                          "control_state": row["control_state"],
                          "generation": row["generation"],
                          "pause_mode": row["pause_mode"],
                          "drain_execution_ids": json.loads(row["drain_execution_ids"])}
                         for row in rows)
        finally:
            connection.close()
