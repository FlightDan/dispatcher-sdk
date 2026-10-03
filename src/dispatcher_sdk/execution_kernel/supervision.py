"""Kernel-owned deadline inheritance and confirmed supervision control facts.

High-volume activity belongs in the observation journal. These small records
share the execution transaction so progress can invalidate a stale disposition.
"""

from __future__ import annotations

import json
import math
from typing import Any

from ._sqlite_base import encode_json
from .budget import BudgetClockUnknownError, BudgetEnvelope, DeadlineConstraint, sample_clock
from .contracts import ExecutionCommandV2, ExecutionLease
from .errors import CASConflictError, StaleFenceError


class SupervisionMixin:
    def _supervision_row(self, connection, row):
        current = connection.execute(
            "SELECT * FROM kernel_supervision WHERE execution_id=?", (row["execution_id"],)
        ).fetchone()
        if current is None:
            connection.execute(
                "INSERT INTO kernel_supervision(execution_id,attempt,fence) VALUES(?,?,?)",
                (row["execution_id"], row["attempt"], row["fence"]),
            )
        elif (current["attempt"], current["fence"]) != (row["attempt"], row["fence"]):
            connection.execute(
                "UPDATE kernel_supervision SET attempt=?,fence=?,progress_revision=0,progress_at=NULL,"
                "episode_id=NULL,policy_version=NULL,episode_progress_revision=NULL WHERE execution_id=?",
                (row["attempt"], row["fence"], row["execution_id"]),
            )
        return connection.execute(
            "SELECT * FROM kernel_supervision WHERE execution_id=?", (row["execution_id"],)
        ).fetchone()

    def supervision_status(self, execution_id: str, *, timeout_seconds: float = .1) -> dict[str, Any]:
        """Read current authority and progress without creating a control row."""
        with self._control_lock(timeout_seconds):
            row = self._get_row(self._connection, execution_id)
            current = self._connection.execute(
                "SELECT * FROM kernel_supervision WHERE execution_id=?", (execution_id,)
            ).fetchone()
            value = dict(current) if current is not None else {}
            if (value.get("attempt"), value.get("fence")) != (row["attempt"], row["fence"]):
                value = {"execution_id": execution_id, "attempt": row["attempt"],
                         "fence": row["fence"], "progress_revision": 0, "progress_at": None,
                         "episode_id": None, "policy_version": None,
                         "episode_progress_revision": None}
            return {**value, "execution_state": row["state"], "execution_revision": row["revision"]}

    def confirm_progress(self, lease: ExecutionLease, event_id: str, *, timeout_seconds: float = .1) -> dict[str, Any]:
        """Confirm one application progress key under its live execution fence.

        Application meaning is not validated. Replayed keys do not reset the
        progress clock and do not mutate the execution's public lease revision.
        """
        if type(event_id) is not str or not event_id.strip() or len(event_id) > 1024:
            raise ValueError("progress event_id must be a non-empty string of at most 1024 characters")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = self._assert_lease(connection, lease, timestamp=timestamp, states={"running"})
            self._authorize_managed_operation(
                connection, lease.execution_id, timestamp=timestamp, operation="progress confirmation"
            )
            current = self._supervision_row(connection, row)
            previous = connection.execute(
                "SELECT progress_revision FROM kernel_progress_keys "
                "WHERE execution_id=? AND attempt=? AND event_id=?",
                (lease.execution_id, lease.attempt, event_id),
            ).fetchone()
            if previous is not None:
                return {"state": "confirmed", "new": False,
                        "progress_revision": current["progress_revision"],
                        "event_progress_revision": previous[0], "at": current["progress_at"]}
            revision = current["progress_revision"] + 1
            connection.execute(
                "INSERT INTO kernel_progress_keys(execution_id,attempt,event_id,progress_revision) "
                "VALUES(?,?,?,?)", (lease.execution_id, lease.attempt, event_id, revision),
            )
            connection.execute(
                "UPDATE kernel_supervision SET progress_revision=?,progress_at=?,episode_id=NULL,"
                "episode_progress_revision=NULL WHERE execution_id=?",
                (revision, timestamp, lease.execution_id),
            )
            return {"state": "confirmed", "new": True, "progress_revision": revision,
                    "event_progress_revision": revision, "at": timestamp}

    def register_stall_episode(self, execution_id: str, *, attempt: int, fence: int,
                               progress_revision: int, episode_id: str,
                               policy_version: str, timeout_seconds: float = .1) -> dict[str, Any]:
        for name, value in (("episode_id", episode_id), ("policy_version", policy_version)):
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = self._get_row(connection, execution_id)
            if (row["state"] != "running" or (row["attempt"], row["fence"]) != (attempt, fence)
                    or row["lease_expires_at"] <= timestamp):
                raise StaleFenceError("stall episode no longer belongs to an active execution")
            current = self._supervision_row(connection, row)
            if current["policy_version"] not in {None, policy_version}:
                raise CASConflictError("stall policy was replaced")
            if current["progress_revision"] != progress_revision:
                raise CASConflictError("new progress invalidated the observed stall window")
            if current["episode_id"] is not None and current["episode_id"] != episode_id:
                raise CASConflictError("another stall episode already owns this progress revision")
            connection.execute(
                "UPDATE kernel_supervision SET episode_id=?,policy_version=?,episode_progress_revision=? "
                "WHERE execution_id=?", (episode_id, policy_version, progress_revision, execution_id),
            )
            return {"execution_id": execution_id, "attempt": attempt, "fence": fence,
                    "progress_revision": progress_revision, "episode_id": episode_id,
                    "policy_version": policy_version}

    def set_stall_policy(self, execution_id: str, *, attempt: int, fence: int,
                         policy_version: str, timeout_seconds: float = .1) -> dict[str, Any]:
        """Replace optional disposition authority without altering execution facts."""
        if type(policy_version) is not str or not policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = self._get_row(connection, execution_id)
            if (row["state"] != "running" or (row["attempt"], row["fence"]) != (attempt, fence)
                    or row["lease_expires_at"] <= timestamp):
                raise StaleFenceError("policy belongs to an inactive execution")
            current = self._supervision_row(connection, row)
            if current["policy_version"] != policy_version:
                connection.execute(
                    "UPDATE kernel_supervision SET policy_version=?,episode_id=NULL,episode_progress_revision=NULL "
                    "WHERE execution_id=?", (policy_version, execution_id))
            return {"execution_id": execution_id, "attempt": attempt, "fence": fence,
                    "policy_version": policy_version, "progress_revision": current["progress_revision"]}

    def _assert_stall_disposition(self, connection, row, expected: dict[str, Any]) -> None:
        keys = {"execution_id", "attempt", "fence", "progress_revision", "episode_id", "policy_version"}
        if type(expected) is not dict or set(expected) != keys:
            raise ValueError("invalid stall disposition identity")
        current = connection.execute(
            "SELECT * FROM kernel_supervision WHERE execution_id=?", (row["execution_id"],)
        ).fetchone()
        if (current is None or row["state"] != "running"
                or expected["execution_id"] != row["execution_id"]
                or any(expected[key] != current[key] for key in keys)
                or (row["attempt"], row["fence"]) != (current["attempt"], current["fence"])):
            raise CASConflictError("stall disposition is stale; current progress/episode changed")

    def clear_stall_episode(self, *, expected: dict[str, Any], timeout_seconds: float = .1):
        """End only the sampled episode, without claiming application progress."""
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = self._get_row(connection, expected["execution_id"])
            try:
                self._assert_stall_disposition(connection, row, expected)
            except CASConflictError:
                return {"state": "superseded", "cleared": False}
            connection.execute("UPDATE kernel_supervision SET episode_id=NULL,episode_progress_revision=NULL "
                "WHERE execution_id=?", (row["execution_id"],))
            return {"state": "confirmed", "cleared": True}

    def get_execution_limits(self, execution_id: str, *, timeout_seconds: float = .1) -> dict[str, Any] | None:
        with self._control_lock(timeout_seconds):
            row = self._connection.execute(
                "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (execution_id,)
            ).fetchone()
            if row is None:
                return None
            return {**dict(row), "envelope": json.loads(row["envelope_json"])}

    def admission_budget(self, lease: ExecutionLease, *, timeout_seconds: float = .1) -> BudgetEnvelope:
        """Return existing cutoffs and the managed Run constraint at admission."""
        with self._control_lock(timeout_seconds):
            row = self._get_row(self._connection, lease.execution_id)
            if (row["attempt"], row["fence"]) != (lease.attempt, lease.fence):
                raise StaleFenceError("budget admission belongs to a stale execution")
            stored = self.get_execution_limits(lease.execution_id)
            if (stored is not None and stored["entry_state"] == "pending"
                    and (stored["entry_attempt"], stored["entry_fence"]) != (lease.attempt, lease.fence)):
                raise BudgetClockUnknownError("entry_confirmation_pending: original handler entry is unresolved")
            envelope = (BudgetEnvelope.from_dict(stored["envelope"]) if stored is not None
                        else BudgetEnvelope((), sample_clock(wall_time=self._wall_time())))
            return self._run_budget(self._connection, lease.execution_id, envelope)

    @staticmethod
    def _run_budget(connection, execution_id: str, envelope: BudgetEnvelope) -> BudgetEnvelope:
        control = connection.execute(
            "SELECT c.run_id,c.deadline_at FROM kernel_managed_executions m "
            "JOIN kernel_run_controls c ON c.run_id=m.run_id WHERE m.execution_id=?",
            (execution_id,),
        ).fetchone()
        if control is not None:
            origin = "run:" + control["run_id"]
            prior = next((item for item in envelope.constraints if item.origin_id == origin), None)
            constraint = DeadlineConstraint(origin, "run", control["deadline_at"])
            if prior is not None:
                constraint = DeadlineConstraint(origin, "run", min(prior.deadline_at, constraint.deadline_at),
                                                prior.reserve_seconds)
            envelope = BudgetEnvelope(
                tuple(item for item in envelope.constraints if item.origin_id != origin) + (constraint,),
                envelope.checkpoint, envelope.started_at,
            )
        return envelope

    def prepare_execution_budget(self, lease: ExecutionLease, *,
                                 timeout_seconds: float = .1) -> BudgetEnvelope:
        """Durably admit one entry without starting the execution's clock.

        An interrupted first entry has no provable cutoff. A later attempt must
        keep that uncertainty instead of granting a new duration. Replaying
        preparation under the same live lease is safe before worker dispatch.
        """
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            self._assert_lease(connection, lease, timestamp=timestamp, states={"running"})
            self._authorize_managed_operation(
                connection, lease.execution_id, timestamp=timestamp, operation="handler entry admission"
            )
            existing = connection.execute(
                "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (lease.execution_id,)
            ).fetchone()
            if (existing is not None and existing["entry_state"] == "pending"
                    and (existing["entry_attempt"], existing["entry_fence"]) != (lease.attempt, lease.fence)):
                raise BudgetClockUnknownError("entry_confirmation_pending: original handler entry is unresolved")
            envelope = (BudgetEnvelope.from_dict(json.loads(existing["envelope_json"]))
                        if existing is not None else BudgetEnvelope((), sample_clock(wall_time=self._wall_time())))
            envelope = self._run_budget(connection, lease.execution_id, envelope).recheckpoint(
                sample=sample_clock(wall_time=self._wall_time()))
            origin = "execution:" + lease.execution_id
            cutoff = next((item for item in envelope.constraints if item.origin_id == origin), None)
            if cutoff is not None and cutoff.source != "execution":
                raise ValueError("execution origin conflicts with inherited constraint")
            if existing is not None and existing["entry_state"] == "confirmed" and cutoff is None:
                raise BudgetClockUnknownError("confirmed handler entry has no original execution cutoff")
            state = "confirmed" if cutoff is not None else "pending"
            if existing is None:
                connection.execute(
                    "INSERT INTO kernel_execution_limits(execution_id,envelope_json,entry_state,entry_attempt,entry_fence) "
                    "VALUES(?,?,?,?,?)", (lease.execution_id, encode_json(envelope.to_dict()), state,
                                          lease.attempt, lease.fence),
                )
            else:
                connection.execute(
                    "UPDATE kernel_execution_limits SET envelope_json=?,entry_state=?,entry_attempt=?,entry_fence=? "
                    "WHERE execution_id=?", (encode_json(envelope.to_dict()), state, lease.attempt,
                                              lease.fence, lease.execution_id),
                )
            return envelope

    def confirm_handler_entry(self, lease: ExecutionLease, envelope: BudgetEnvelope, *,
                              timeout_seconds: float = .1) -> BudgetEnvelope:
        """Confirm the worker's captured entry; persistence never resets its cutoff."""
        if type(envelope) is not BudgetEnvelope:
            raise TypeError("budget must be a BudgetEnvelope")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = self._assert_lease(connection, lease, timestamp=timestamp, states={"running"})
            self._authorize_managed_operation(
                connection, lease.execution_id, timestamp=timestamp, operation="handler entry confirmation"
            )
            existing = connection.execute(
                "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (lease.execution_id,)
            ).fetchone()
            if (existing is None or existing["entry_state"] not in {"pending", "confirmed"}
                    or (existing["entry_attempt"], existing["entry_fence"]) != (lease.attempt, lease.fence)):
                raise CASConflictError("handler entry has no matching durable admission")
            old = BudgetEnvelope.from_dict(json.loads(existing["envelope_json"]))
            # A replayed ACK can precede the persisted checkpoint. Preserve
            # both elapsed continuity and the greatest effective wall time.
            if envelope.checkpoint.elapsed_at >= old.checkpoint.elapsed_at:
                checkpoint = old.recheckpoint(sample=envelope.checkpoint).checkpoint
                envelope = envelope.recheckpoint(sample=checkpoint)
            else:
                envelope = envelope.recheckpoint(sample=old.checkpoint)
            values = {item.origin_id: item for item in envelope.constraints}
            for previous in old.constraints:
                current = values.get(previous.origin_id)
                if (current is None or current.source != previous.source
                        or current.deadline_at > previous.deadline_at
                        or current.reserve_seconds < previous.reserve_seconds):
                    raise ValueError("handler entry weakens an admitted budget constraint")
            origin = "execution:" + lease.execution_id
            cutoff = values.get(origin)
            if cutoff is None or cutoff.source != "execution" or envelope.started_at is None:
                raise ValueError("handler entry requires its execution cutoff and actual entry timestamp")
            if existing["entry_state"] == "pending":
                expected = envelope.started_at + self._command(row["command_json"]).timeout_seconds
                if not math.isclose(cutoff.deadline_at, expected, rel_tol=0, abs_tol=1e-6):
                    raise ValueError("first handler cutoff does not match its actual entry timeout")
            envelope = self._run_budget(connection, lease.execution_id, envelope).recheckpoint(
                sample=sample_clock(wall_time=self._wall_time()))
            connection.execute(
                "UPDATE kernel_execution_limits SET envelope_json=?,entry_state='confirmed' WHERE execution_id=?",
                (encode_json(envelope.to_dict()), lease.execution_id),
            )
            return envelope

    def record_execution_budget(self, lease: ExecutionLease, envelope: BudgetEnvelope, *,
                                timeout_seconds: float = .1) -> BudgetEnvelope:
        """Compatibility helper for callers already holding an actual-entry ACK."""
        if type(envelope) is not BudgetEnvelope:
            raise TypeError("budget must be a BudgetEnvelope")
        self.prepare_execution_budget(lease, timeout_seconds=timeout_seconds)
        return self.confirm_handler_entry(lease, envelope, timeout_seconds=timeout_seconds)

    def submit_child(self, command: ExecutionCommandV2, parent_lease: ExecutionLease,
                     budget_envelope: BudgetEnvelope):
        """Atomically bind a queued child to a live parent and inherited limits."""
        with self._transaction() as (connection, timestamp):
            parent = self._assert_lease(connection, parent_lease, timestamp=timestamp, states={"running"})
            self._authorize_managed_operation(
                connection, parent_lease.execution_id, timestamp=timestamp, operation="child submission"
            )
            depth = self._child_depth(connection, parent_lease.execution_id)
            managed = connection.execute(
                "SELECT run_id,generation FROM kernel_managed_executions WHERE execution_id=?",
                (parent_lease.execution_id,),
            ).fetchone()
            if managed is not None:
                if (not command.execution_id.startswith("sdk-managed:")
                        or command.correlation_id != managed["run_id"]):
                    raise ValueError("managed child must retain its Run control association")
                mapping = connection.execute(
                    "SELECT run_id,generation FROM kernel_managed_executions WHERE execution_id=?",
                    (command.execution_id,),
                ).fetchone()
                if mapping is None:
                    connection.execute(
                        "INSERT INTO kernel_managed_executions(execution_id,run_id,generation,drain_allowed) "
                        "VALUES(?,?,?,0)", (command.execution_id, managed["run_id"], managed["generation"]),
                    )
                elif tuple(mapping) != (managed["run_id"], managed["generation"]):
                    raise CASConflictError("child managed Run association changed")
            elif command.execution_id.startswith("sdk-managed:"):
                raise ValueError("ordinary parent cannot create a managed child")
            result, _ = self._submit_in_transaction(
                command, encode_json(command.to_dict()), connection, timestamp
            )
            self._bind_child_limits(connection, command.execution_id, parent, budget_envelope, depth + 1)
            return self._snapshot(result)

    def adopt_child(self, execution_id: str, parent_lease: ExecutionLease,
                    budget_envelope: BudgetEnvelope):
        with self._transaction() as (connection, timestamp):
            parent = self._assert_lease(connection, parent_lease, timestamp=timestamp, states={"running"})
            self._authorize_managed_operation(
                connection, parent_lease.execution_id, timestamp=timestamp, operation="child adoption"
            )
            target = self._get_row(connection, execution_id)
            if target["state"] != "queued":
                raise CASConflictError("only a queued child may acquire inherited limits")
            parent_mapping = connection.execute(
                "SELECT run_id,generation FROM kernel_managed_executions WHERE execution_id=?",
                (parent_lease.execution_id,)).fetchone()
            child_mapping = connection.execute(
                "SELECT run_id,generation FROM kernel_managed_executions WHERE execution_id=?",
                (execution_id,)).fetchone()
            if ((parent_mapping is None) != (child_mapping is None)
                    or (parent_mapping is not None and tuple(parent_mapping) != tuple(child_mapping))):
                raise CASConflictError("adopted child must retain the parent's managed Run and generation")
            depth = self._child_depth(connection, parent_lease.execution_id)
            self._bind_child_limits(connection, execution_id, parent, budget_envelope, depth + 1)
            return self._snapshot(target)

    @staticmethod
    def _child_depth(connection, execution_id: str) -> int:
        row = connection.execute(
            "SELECT depth FROM kernel_execution_limits WHERE execution_id=?", (execution_id,)
        ).fetchone()
        return 0 if row is None else row[0]

    def _bind_child_limits(self, connection, execution_id: str, parent, envelope: BudgetEnvelope, depth: int):
        if execution_id == parent["execution_id"]:
            raise ValueError("execution cannot wait on itself")
        current_sample = sample_clock(wall_time=self._wall_time())
        envelope = envelope.recheckpoint(sample=current_sample)
        parent_limits = connection.execute(
            "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?",
            (parent["execution_id"],)).fetchone()
        if parent_limits is None:
            raise CASConflictError("child submission requires confirmed parent handler entry and limits")
        authority = BudgetEnvelope.from_dict(json.loads(parent_limits[0])).recheckpoint(sample=current_sample)
        if not authority.view(sample=current_sample).remaining_work_seconds:
            raise CASConflictError("parent work deadline has elapsed")
        values = {item.origin_id: item for item in authority.constraints}
        for item in envelope.constraints:
            previous = values.get(item.origin_id)
            if previous is not None and previous.source != item.source:
                raise ValueError("child budget origin changes an authoritative constraint source")
            values[item.origin_id] = item if previous is None else DeadlineConstraint(
                item.origin_id, item.source, min(item.deadline_at, previous.deadline_at),
                max(item.reserve_seconds, previous.reserve_seconds))
        envelope = BudgetEnvelope(tuple(values.values()), authority.checkpoint, envelope.started_at)
        ancestor = parent["execution_id"]
        for _ in range(64):
            if ancestor == execution_id:
                raise ValueError("child relationship forms a cycle")
            previous = connection.execute(
                "SELECT parent_execution_id FROM kernel_execution_limits WHERE execution_id=?", (ancestor,)
            ).fetchone()
            if previous is None or previous[0] is None:
                break
            ancestor = previous[0]
        else:
            raise ValueError("child relationship exceeds bounded depth")
        existing = connection.execute(
            "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (execution_id,)
        ).fetchone()
        if existing is not None and existing["parent_execution_id"] not in {None, parent["execution_id"]}:
            raise CASConflictError("child already belongs to another parent")
        if (existing is not None and existing["parent_execution_id"] is not None
                and (existing["parent_attempt"], existing["parent_fence"]) != (parent["attempt"], parent["fence"])):
            raise CASConflictError("child belongs to a previous parent attempt")
        if existing is not None:
            old = BudgetEnvelope.from_dict(json.loads(existing["envelope_json"]))
            for item in old.constraints:
                previous = values.get(item.origin_id)
                if previous is not None and previous.source != item.source:
                    raise ValueError("existing child constraint source cannot change")
                values[item.origin_id] = item if previous is None else DeadlineConstraint(
                    item.origin_id, item.source, min(item.deadline_at, previous.deadline_at),
                    max(item.reserve_seconds, previous.reserve_seconds))
            child_sample = old.recheckpoint(sample=current_sample).checkpoint
            envelope = BudgetEnvelope(tuple(values.values()),
                child_sample if child_sample.wall_at >= authority.checkpoint.wall_at else authority.checkpoint,
                envelope.started_at)
            connection.execute(
                "UPDATE kernel_execution_limits SET envelope_json=? WHERE execution_id=?",
                (encode_json(envelope.to_dict()), execution_id),
            )
            if existing["parent_execution_id"] is None:
                connection.execute(
                    "UPDATE kernel_execution_limits SET parent_execution_id=?,parent_attempt=?,parent_fence=?,depth=? "
                    "WHERE execution_id=? AND parent_execution_id IS NULL",
                    (parent["execution_id"], parent["attempt"], parent["fence"], depth, execution_id))
        else:
            connection.execute(
                "INSERT INTO kernel_execution_limits(execution_id,envelope_json,parent_execution_id,"
                "parent_attempt,parent_fence,depth) VALUES(?,?,?,?,?,?)",
                (execution_id, encode_json(envelope.to_dict()), parent["execution_id"],
                 parent["attempt"], parent["fence"], depth),
            )
