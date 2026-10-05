"""Kernel-owned deadline inheritance and confirmed supervision control facts.

High-volume activity belongs in the observation journal. These small records
share the execution transaction so progress can invalidate a stale disposition.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from typing import Any

from ._sqlite_base import encode_json
from .budget import BudgetClockUnknownError, BudgetEnvelope, ClockCheckpoint, DeadlineConstraint, sample_clock
from .contracts import ExecutionCommandV2, ExecutionLease
from .errors import CASConflictError, ExecutionNotFoundError, StaleFenceError, StorageIsolationError


class SupervisionMixin:
    def _read_budget_floor(self, execution_id: str, *, timeout_seconds: float = .1) -> ClockCheckpoint:
        """Read guard absence and its canonical floor from one snapshot.

        This imports committed clock facts after failed write admission. It
        observes no new wall time and cannot admit business or retire a sample.
        """
        with self._control_lock(timeout_seconds):
            connection = self._connection
            if connection.in_transaction:
                raise StorageIsolationError("budget floor inspection requires an idle connection")
            failure = None
            try:
                connection.execute("BEGIN")
                self._assert_budget_clock(connection, execution_id)
                row = connection.execute(
                    "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?",
                    (execution_id,)).fetchone()
                if row is None:
                    raise BudgetClockUnknownError("canonical budget floor cannot be established")
                canonical = BudgetEnvelope.from_dict(json.loads(row[0]))
                if time.monotonic() >= self._control_deadline:
                    raise TimeoutError("Kernel control admission budget elapsed")
                return canonical.checkpoint
            except BaseException as error:
                failure = error
                raise
            finally:
                if connection.in_transaction:
                    try:
                        connection.rollback()
                    except BaseException as cleanup_error:
                        if failure is not None:
                            raise failure from cleanup_error
                        raise

    def _assert_budget_clock(self, connection, execution_id: str) -> None:
        """Unacknowledged samples fence entry and descendant admission."""
        seen = set()
        while execution_id is not None:
            if execution_id in seen or len(seen) >= 64:
                raise BudgetClockUnknownError("budget ancestry cannot be established")
            seen.add(execution_id)
            pending = connection.execute(
                "SELECT reason FROM kernel_budget_samples WHERE execution_id=? LIMIT 1",
                (execution_id,)).fetchone()
            if pending is not None:
                raise BudgetClockUnknownError("budget_clock_sample_unresolved:" + pending[0])
            parent = connection.execute(
                "SELECT parent_execution_id FROM kernel_execution_limits WHERE execution_id=?",
                (execution_id,)).fetchone()
            execution_id = None if parent is None else parent[0]

    def _budget_sample_status(self, execution_id: str | None = None) -> bool | None:
        """Inspect owned obligations; unavailable inspection remains unknown."""
        if not self._lock.acquire(blocking=False):
            return None
        try:
            if execution_id is None:
                return bool(self._budget_sample_owners)
            return any(owner.execution_id == execution_id
                       for owner in self._budget_sample_owners.values())
        finally:
            self._lock.release()

    def _budget_samples_pending(self, execution_id: str | None = None) -> bool:
        # Resource release requires positive proof that no exact owner remains.
        return self._budget_sample_status(execution_id) is not False

    def _drain_budget_samples(self, deadline: float, *,
                              execution_ids: tuple[str, ...] | None = None) -> bool:
        """Finish retained facts within one maintenance bound, without sampling."""
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self._lock.acquire(timeout=max(0., remaining)):
            return True
        try:
            # A nonblocking owner admission preserves owner -> Kernel order.
            # No helper whose original caller still holds it is waited on here.
            visited = set()
            while self._budget_sample_owners and time.monotonic() < deadline:
                item = next(((token, owner) for token, owner in self._budget_sample_owners.items()
                             if token not in visited and (execution_ids is None
                                 or owner.execution_id in execution_ids)), None)
                if item is None:
                    break
                token, owner = item
                visited.add(token)
                if not owner._lock.acquire(blocking=False):
                    continue
                try:
                    pending = owner._pending
                    if pending is None and owner._published is not None:
                        if self._budget_sample_owners.get(token) is owner:
                            self._budget_sample_owners.pop(token, None)
                    if pending is not None and pending[0] == token and pending[1] is not None:
                        try:
                            owner.finish_pending(pending[1], timeout_seconds=max(
                                .000001, deadline - time.monotonic()))
                        except Exception:
                            # Original causal failure remains with its owner.
                            pass
                finally:
                    owner._lock.release()
            return any(execution_ids is None or owner.execution_id in execution_ids
                       for owner in self._budget_sample_owners.values())
        finally:
            self._lock.release()

    def _begin_budget_sample(self, execution_id: str, *, timeout_seconds: float = .1,
                             _owner=None) -> str:
        token = str(uuid.uuid4())
        with self._control_lock(timeout_seconds):
            self._assert_budget_clock(self._connection, execution_id)
            try:
                # Arm from committed authority only. A wall sample before this
                # COMMIT would have no durable crash marker protecting it.
                with self._transaction(timeout_seconds=timeout_seconds,
                                       _observe_clock=False) as (connection, _):
                    self._get_row(connection, execution_id)
                    self._assert_budget_clock(connection, execution_id)
                    connection.execute(
                        "INSERT INTO kernel_budget_samples(token,execution_id,reason) VALUES(?,?,'sampling')",
                        (token, execution_id))
                    if _owner is not None:
                        _owner._armed(token)
                        self._budget_sample_owners[token] = _owner
            except BaseException as exc:
                # Publish ownership before COMMIT, retire only after a proven
                # rollback. Interrupted/uncertain COMMIT keeps its live owner.
                try:
                    marker = self._connection.execute(
                        "SELECT token FROM kernel_budget_samples WHERE token=?", (token,)).fetchone()
                except Exception:
                    marker = True
                if marker is None:
                    if self._budget_sample_owners.get(token) is _owner:
                        self._budget_sample_owners.pop(token, None)
                    if _owner is not None and _owner._pending is not None and _owner._pending[0] == token:
                        _owner._pending = None
                else:
                    exc.budget_sample_token = token
                    exc.budget_sample_envelope = None
                    exc.budget_sample_owner = _owner
                raise
        return token

    def _finish_budget_sample(self, token: str, execution_id: str, envelope: BudgetEnvelope,
                              *, timeout_seconds: float = .1, _owner=None) -> BudgetEnvelope:
        with self._control_lock(timeout_seconds):
            with self._transaction(timeout_seconds=timeout_seconds,
                                   _observe_clock=False) as (connection, _):
                marker = connection.execute(
                    "SELECT execution_id,reason FROM kernel_budget_samples WHERE token=?", (token,)).fetchone()
                limits = connection.execute(
                    "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?",
                    (execution_id,)).fetchone()
                if limits is None:
                    raise BudgetClockUnknownError("budget sampling requires admitted execution limits")
                canonical = BudgetEnvelope.from_dict(json.loads(limits[0]))
                if marker is None:
                    # Only a retained live owner that attempted this exact ACK may
                    # reconcile interruption after COMMIT. A new Kernel cannot.
                    if (_owner is None or self._budget_sample_owners.get(token) is not _owner
                            or _owner._ack_token != token):
                        raise CASConflictError("budget sampling token has no matching owner")
                    retained, committed = envelope.checkpoint, canonical.checkpoint
                    common = ClockCheckpoint(0., max(retained.elapsed_at, committed.elapsed_at),
                        committed.domain_id, committed.domain_scope, committed.unknown_reason)
                    committed_floor = committed.effective_time(common)
                    retained_floor = retained.effective_time(common)
                    if (committed_floor is None or retained_floor is None
                            or committed_floor < retained_floor):
                        raise CASConflictError("committed budget floor does not acknowledge captured fact")
                else:
                    if tuple(marker) != (execution_id, "sampling"):
                        raise CASConflictError("budget sampling token has no matching owner")
                    canonical = canonical.with_clock_floor(envelope.checkpoint)
                    connection.execute("UPDATE kernel_execution_limits SET envelope_json=? WHERE execution_id=?",
                                       (encode_json(canonical.to_dict()), execution_id))
                    connection.execute("DELETE FROM kernel_budget_samples WHERE token=? AND execution_id=?",
                                       (token, execution_id))
                    if _owner is not None:
                        _owner._ack_token = token
                # The protected observed floor also governs other executions'
                # Run and lease authority. Publish it with this exact ACK so
                # wall rollback cannot reopen time through a sibling command.
                connection.execute(
                    "UPDATE kernel_clock SET watermark=MAX(watermark,?) WHERE singleton=1",
                    (canonical.checkpoint.wall_at,))
            published = envelope.with_clock_floor(canonical.checkpoint)
            if _owner is not None:
                _owner._acknowledged(token, published)
                if self._budget_sample_owners.get(token) is _owner:
                    self._budget_sample_owners.pop(token, None)
            return published

    def _finish_received_budget_sample(self, token: str, execution_id: str,
                                       envelope: BudgetEnvelope, *,
                                       timeout_seconds: float = .1) -> BudgetEnvelope:
        """Finish a positive fact recovered from the bound settlement journal.

        Runtime must retain the received checkpoint before calling this path.
        A missing marker is replayable only when both committed clock floors
        already acknowledge that fact. This grants no execution authority.
        """
        with self._control_lock(timeout_seconds):
            def remaining():
                duration = self._control_deadline - time.monotonic()
                if duration <= 0:
                    raise TimeoutError("received budget checkpoint admission elapsed")
                return duration

            owner = self._budget_sample_owners.get(token)
            if owner is not None:
                # Preserve owner -> Kernel lock order: never wait on an owner
                # whose caller may already be waiting for this Kernel lock.
                if not owner._lock.acquire(blocking=False):
                    raise TimeoutError("received budget checkpoint owner is busy")
                try:
                    pending = owner._pending
                    if (owner.execution_id != execution_id or pending is None
                            or pending[0] != token or pending[1] is None):
                        raise CASConflictError("received budget checkpoint conflicts with its live owner")
                    return owner.finish_pending(envelope, timeout_seconds=remaining())
                finally:
                    owner._lock.release()
            try:
                return self._finish_budget_sample(token, execution_id, envelope,
                    timeout_seconds=remaining())
            except CASConflictError:
                # The original ACK can commit before the independent receipt
                # state changes. Unlike a live caller, cold recovery has no
                # in-memory _ack_token; the retained receipt owns this replay.
                with self._transaction(timeout_seconds=remaining(),
                                       _observe_clock=False) as (connection, _):
                    marker = connection.execute(
                        "SELECT token FROM kernel_budget_samples WHERE token=?", (token,)).fetchone()
                    if marker is not None:
                        raise
                    limits = connection.execute(
                        "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?",
                        (execution_id,)).fetchone()
                    if limits is None:
                        raise
                    canonical = BudgetEnvelope.from_dict(json.loads(limits[0]))
                    retained, committed = envelope.checkpoint, canonical.checkpoint
                    common = ClockCheckpoint(0., max(retained.elapsed_at, committed.elapsed_at),
                        committed.domain_id, committed.domain_scope, committed.unknown_reason)
                    committed_floor = committed.effective_time(common)
                    retained_floor = retained.effective_time(common)
                    clock = connection.execute(
                        "SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()
                    if (committed_floor is None or retained_floor is None
                            or committed_floor < retained_floor or clock is None
                            or clock[0] < retained.wall_at):
                        raise CASConflictError("committed clock floors do not acknowledge received fact")
                    return envelope.with_clock_floor(committed)

    def _sample_budget(self, execution_id: str, envelope: BudgetEnvelope, *,
                       timeout_seconds: float = .1, _owner=None) -> BudgetEnvelope:
        if _owner is None:
            from .budget_capture import _KernelBudgetCapture
            return _KernelBudgetCapture(self, execution_id)(envelope, timeout_seconds=timeout_seconds)
        deadline = time.monotonic() + timeout_seconds
        unresolved = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if unresolved is not None:
                    raise unresolved
                raise BudgetClockUnknownError("budget_clock_sample_unresolved:sampling")
            token, sampled = None, None
            try:
                with self._control_lock(remaining):
                    # A previous call may have expired while still owning a
                    # captured fact. Drain only those exact retained owners.
                    self._drain_budget_samples(deadline)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Kernel control admission budget elapsed")
                    self._assert_budget_clock(self._connection, execution_id)
                    limits = self._connection.execute(
                        "SELECT envelope_json FROM kernel_execution_limits WHERE execution_id=?",
                        (execution_id,)).fetchone()
                    if limits is not None:
                        canonical = BudgetEnvelope.from_dict(json.loads(limits[0]))
                        envelope = envelope.with_clock_floor(canonical.checkpoint)
                        envelope = envelope.recheckpoint(
                            sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
                        view = envelope.view(sample=envelope.checkpoint)
                        if view.remaining_work_seconds is not None and view.remaining_work_seconds <= 0:
                            return envelope
                    token = self._begin_budget_sample(execution_id, timeout_seconds=remaining, _owner=_owner)
                    clock = self._connection.execute(
                        "SELECT watermark FROM kernel_clock WHERE singleton=1").fetchone()
                    if clock is None:
                        raise RuntimeError("kernel logical clock row is missing")
                    wall = max(self._wall_time(), self._number(clock[0], "clock watermark", minimum=0.0))
                    sampled = envelope.recheckpoint(sample=sample_clock(wall_time=wall))
                    _owner._captured(token, sampled)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Kernel control admission budget elapsed")
                    return self._finish_budget_sample(
                        token, execution_id, sampled, timeout_seconds=remaining, _owner=_owner)
            except BaseException as exc:
                if token is not None:
                    exc.budget_sample_token = token
                    exc.budget_sample_envelope = sampled
                    exc.budget_sample_owner = _owner
                    raise
                if (isinstance(exc, TimeoutError) and unresolved is not None
                        and getattr(exc, "budget_sample_token", None) is None):
                    # Admission expiry cannot replace uncertainty already
                    # established by SQL during this same bounded operation.
                    raise unresolved from exc
                if (not isinstance(exc, BudgetClockUnknownError)
                        or str(exc) != "budget_clock_sample_unresolved:sampling"):
                    raise
                if unresolved is None:
                    unresolved = exc
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise unresolved
                time.sleep(min(.005, remaining))

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
            # One scalar snapshot binds entry confirmation to the actual
            # execution identity, including writes from a native worker.
            row = self._connection.execute(
                "SELECT e.execution_id,e.attempt,e.fence,e.state,e.revision,"
                "l.entry_state,l.entry_attempt,l.entry_fence,"
                "s.attempt AS supervision_attempt,s.fence AS supervision_fence,"
                "s.progress_revision,s.progress_at,s.episode_id,s.policy_version,s.episode_progress_revision "
                "FROM kernel_executions e LEFT JOIN kernel_supervision s ON s.execution_id=e.execution_id "
                "LEFT JOIN kernel_execution_limits l ON l.execution_id=e.execution_id "
                "WHERE e.execution_id=?", (execution_id,)
            ).fetchone()
            if row is None:
                raise ExecutionNotFoundError(execution_id)
            value = {name: row[name] for name in ("progress_revision", "progress_at", "episode_id",
                                                "policy_version", "episode_progress_revision")}
            if (row["supervision_attempt"], row["supervision_fence"]) != (row["attempt"], row["fence"]):
                value = {"progress_revision": 0, "progress_at": None,
                         "episode_id": None, "policy_version": None,
                         "episode_progress_revision": None}
            return {"execution_id": execution_id, "attempt": row["attempt"], "fence": row["fence"],
                    **value, "execution_state": row["state"], "execution_revision": row["revision"],
                    "entry_state": row["entry_state"], "entry_attempt": row["entry_attempt"],
                    "entry_fence": row["entry_fence"]}

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
            try:
                self._assert_budget_clock(self._connection, execution_id)
                clock_status, reason = "trusted", None
            except BudgetClockUnknownError as error:
                clock_status, reason = "unknown", str(error)
            return {**dict(row), "envelope": json.loads(row["envelope_json"]),
                    "clock_status": clock_status, "clock_unknown_reason": reason}

    def admission_budget(self, lease: ExecutionLease, *, timeout_seconds: float = .1) -> BudgetEnvelope:
        """Return existing cutoffs and the managed Run constraint at admission."""
        with self._control_lock(timeout_seconds):
            self._assert_budget_clock(self._connection, lease.execution_id)
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
        return self._prepare_execution_budget(lease, timeout_seconds=timeout_seconds)

    def _prepare_handler_entry(self, lease: ExecutionLease, *,
                               timeout_seconds: float = .1) -> BudgetEnvelope:
        """Fence every SDK entry until its current-attempt clock is confirmed."""
        return self._prepare_execution_budget(lease, timeout_seconds=timeout_seconds, pending=True)

    def _prepare_execution_budget(self, lease: ExecutionLease, *,
                                  timeout_seconds: float, pending: bool = False) -> BudgetEnvelope:
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            self._assert_budget_clock(connection, lease.execution_id)
            self._assert_lease(connection, lease, timestamp=timestamp, states={"running"})
            self._assert_child_claim(connection, lease.execution_id, timestamp)
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
                sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
            origin = "execution:" + lease.execution_id
            cutoff = next((item for item in envelope.constraints if item.origin_id == origin), None)
            if cutoff is not None and cutoff.source != "execution":
                raise ValueError("execution origin conflicts with inherited constraint")
            if existing is not None and existing["entry_state"] == "confirmed" and cutoff is None:
                raise BudgetClockUnknownError("confirmed handler entry has no original execution cutoff")
            state = "confirmed" if cutoff is not None and not pending else "pending"
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
        return self._record_handler_entry(lease, envelope, timeout_seconds=timeout_seconds, pending=False)

    def _checkpoint_handler_entry(self, lease: ExecutionLease, envelope: BudgetEnvelope, *,
                                  timeout_seconds: float = .1) -> BudgetEnvelope:
        """Persist actual entry facts without authorizing business or replay."""
        return self._record_handler_entry(lease, envelope, timeout_seconds=timeout_seconds, pending=True)

    def _record_handler_entry(self, lease: ExecutionLease, envelope: BudgetEnvelope, *,
                              timeout_seconds: float, pending: bool) -> BudgetEnvelope:
        if type(envelope) is not BudgetEnvelope:
            raise TypeError("budget must be a BudgetEnvelope")
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
            row = self._assert_lease(connection, lease, timestamp=timestamp, states={"running"})
            if not pending:
                self._assert_budget_clock(connection, lease.execution_id)
                self._assert_child_claim(connection, lease.execution_id, timestamp)
            self._authorize_managed_operation(
                connection, lease.execution_id, timestamp=timestamp, operation="handler entry confirmation"
            )
            envelope, _ = self._merge_handler_entry_budget(connection, row, lease, envelope)
            connection.execute(
                "UPDATE kernel_execution_limits SET envelope_json=?,entry_state=? WHERE execution_id=?",
                (encode_json(envelope.to_dict()), "pending" if pending else "confirmed", lease.execution_id),
            )
            return envelope

    def _merge_handler_entry_budget(self, connection, row, lease: ExecutionLease,
                                   envelope: BudgetEnvelope, *, completion: bool = False):
        """Validate and merge retained facts; callers own the transaction."""
        if type(envelope) is not BudgetEnvelope:
            raise TypeError("budget must be a BudgetEnvelope")
        existing = connection.execute(
            "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (lease.execution_id,)
        ).fetchone()
        allowed_states = {"pending", "confirmed", "unentered"} if completion else {"pending", "confirmed"}
        if existing is None or existing["entry_state"] not in allowed_states:
            raise CASConflictError("handler entry has no matching durable admission")
        old = BudgetEnvelope.from_dict(json.loads(existing["envelope_json"]))
        origin = "execution:" + lease.execution_id
        old_has_entry = any(item.origin_id == origin for item in old.constraints)
        inherited_start = (completion and not old_has_entry
                           and existing["parent_execution_id"] is not None
                           and envelope.started_at == old.started_at)
        no_entry = (not any(item.origin_id == origin for item in envelope.constraints)
                    and (envelope.started_at is None or inherited_start))
        # A child may be denied by its inherited deadline before SDK entry
        # preparation. Its unentered metadata has no handler-attempt authority.
        unprepared = (completion and no_entry and existing["entry_state"] == "unentered"
                      and (existing["entry_attempt"], existing["entry_fence"]) == (None, None)
                      and (old.started_at is None or inherited_start)
                      and not old_has_entry)
        # A retry denied before its entry preparation still carries the
        # original confirmed budget. Result ownership was checked against the
        # current lease; normal validation below permits only equal or tighter
        # inherited constraints (including a newly tightened managed Run).
        inherited = (completion and existing["entry_state"] == "confirmed"
                     and existing["entry_attempt"] < lease.attempt
                     and existing["entry_fence"] < lease.fence
                     and envelope.started_at == old.started_at)
        if ((existing["entry_attempt"], existing["entry_fence"]) != (lease.attempt, lease.fence)
                and not unprepared and not inherited):
            raise CASConflictError("handler entry has no matching durable admission")
        # Replay cannot erase a later checkpoint or a stronger wall floor.
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
        cutoff = values.get(origin)
        if completion and no_entry and (existing["entry_state"] == "pending" or unprepared):
            pass
        elif cutoff is None or cutoff.source != "execution" or envelope.started_at is None:
            raise ValueError("handler entry requires its execution cutoff and actual entry timestamp")
        if cutoff is not None and existing["entry_state"] == "pending" and not any(
                item.origin_id == origin for item in old.constraints):
            expected = envelope.started_at + self._command(row["command_json"]).timeout_seconds
            if not math.isclose(cutoff.deadline_at, expected, rel_tol=0, abs_tol=1e-6):
                raise ValueError("first handler cutoff does not match its actual entry timeout")
        envelope = self._run_budget(connection, lease.execution_id, envelope).recheckpoint(
            sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
        return envelope, existing["entry_state"]

    def _tighten_completion_budget(self, connection, row, lease: ExecutionLease,
                                   envelope: BudgetEnvelope) -> BudgetEnvelope:
        """Commit an original completion floor without finalizing entry."""
        existing = connection.execute(
            "SELECT * FROM kernel_execution_limits WHERE execution_id=?", (lease.execution_id,)
        ).fetchone()
        origin = "execution:" + lease.execution_id
        if existing is None:
            # Work can be refused by a Run/inherited cutoff before entry
            # preparation. Preserve that refusal without inventing an entry.
            if envelope.started_at is not None or any(item.origin_id == origin for item in envelope.constraints):
                raise CASConflictError("handler entry has no matching durable admission")
            envelope = self._run_budget(connection, lease.execution_id, envelope).recheckpoint(
                sample=sample_clock(wall_time=envelope.checkpoint.wall_at))
            connection.execute(
                "INSERT INTO kernel_execution_limits(execution_id,envelope_json,entry_state,entry_attempt,entry_fence) "
                "VALUES(?,?,'pending',?,?)",
                (lease.execution_id, encode_json(envelope.to_dict()), lease.attempt, lease.fence),
            )
            return envelope
        old = BudgetEnvelope.from_dict(json.loads(existing["envelope_json"]))
        # A contained worker can have committed its entry before its packet
        # reaches the parent. An incomplete parent envelope is not authority
        # to remove those durable cutoffs or their captured entry timestamp.
        values = {item.origin_id: item for item in envelope.constraints}
        for previous in old.constraints:
            values.setdefault(previous.origin_id, previous)
        started_at = (old.started_at if any(item.origin_id == origin for item in old.constraints)
                      else envelope.started_at)
        envelope = BudgetEnvelope(tuple(values.values()), envelope.checkpoint, started_at)
        envelope, _ = self._merge_handler_entry_budget(connection, row, lease, envelope, completion=True)
        connection.execute("UPDATE kernel_execution_limits SET envelope_json=? WHERE execution_id=?",
                           (encode_json(envelope.to_dict()), lease.execution_id))
        return envelope

    def record_execution_budget(self, lease: ExecutionLease, envelope: BudgetEnvelope, *,
                                timeout_seconds: float = .1) -> BudgetEnvelope:
        """Compatibility helper for callers already holding an actual-entry ACK."""
        if type(envelope) is not BudgetEnvelope:
            raise TypeError("budget must be a BudgetEnvelope")
        self.prepare_execution_budget(lease, timeout_seconds=timeout_seconds)
        return self.confirm_handler_entry(lease, envelope, timeout_seconds=timeout_seconds)

    def submit_child(self, command: ExecutionCommandV2, parent_lease: ExecutionLease,
                     budget_envelope: BudgetEnvelope, *, timeout_seconds: float | None = None):
        """Atomically bind a queued child to a live parent and inherited limits."""
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
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
                    budget_envelope: BudgetEnvelope, *, timeout_seconds: float | None = None):
        with self._transaction(timeout_seconds=timeout_seconds) as (connection, timestamp):
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
        self._assert_budget_clock(connection, parent["execution_id"])
        self._assert_budget_clock(connection, execution_id)
        if execution_id == parent["execution_id"]:
            raise ValueError("execution cannot wait on itself")
        # Binding projects the caller's guarded sample. Reading another wall
        # clock inside this transaction would lose a new floor on rollback.
        current_sample = sample_clock(wall_time=envelope.checkpoint.wall_at)
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
        # Both checkpoints were advanced to the same clock sample above.
        # Parent authority cannot erase a stronger floor captured by the caller.
        checkpoint = (envelope.checkpoint if envelope.checkpoint.wall_at >= authority.checkpoint.wall_at
                      else authority.checkpoint)
        envelope = BudgetEnvelope(tuple(values.values()), checkpoint, envelope.started_at)
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
                child_sample if child_sample.wall_at >= envelope.checkpoint.wall_at else envelope.checkpoint,
                old.started_at if any(item.origin_id == "execution:" + execution_id
                                      for item in old.constraints) else envelope.started_at)
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
