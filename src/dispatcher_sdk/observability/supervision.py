"""Optional durable stall windows and bounded delivery to the existing inbox."""
from __future__ import annotations

import inspect
import json
import threading
import time
from typing import Any, Callable, Mapping
import uuid

from ..execution_kernel.budget import ClockCheckpoint, sample_clock
from .contracts import ObservationError, ObservationIdentity, StallPolicy, positive
from .journal import ObservationJournal, _bounded_json, _json


class StallSupervisor:
    """Evaluate explicit subscriptions independently of business worker capacity.

    The journal transaction advances a window and creates a durable episode and
    outbox together. A recoverable second step registers the episode with the
    Kernel before its outbox becomes deliverable. Delivery runs only on the
    fixed daemon worker; a blocked bridge cannot block window sampling.
    """

    def __init__(self, journal: ObservationJournal, kernel: Any,
                 notification_bridge: Callable[[dict[str, Any]], Any] | None = None, *,
                 sample_interval: float | None = None, clock=None, clock_sample=None,
                 delivery_lease_seconds: float = 30, retry_delay: float = 1,
                 max_policies: int | None = None) -> None:
        self.journal, self.kernel = journal, kernel
        if notification_bridge is not None and not callable(notification_bridge):
            raise TypeError("notification_bridge must be callable or None")
        self.notification_bridge = notification_bridge
        self.sample_interval = positive(journal.options.flush_interval if sample_interval is None else sample_interval, "sample_interval")
        self.delivery_lease_seconds = positive(delivery_lease_seconds, "delivery_lease_seconds")
        self.retry_delay = positive(retry_delay, "retry_delay")
        self.max_policies = journal.options.page_events if max_policies is None else max_policies
        if type(self.max_policies) is not int or self.max_policies < 1:
            raise ValueError("max_policies must be a positive integer")
        self.clock = clock or journal.clock
        self.clock_sample = clock_sample or (lambda: sample_clock(wall_time=float(self.clock())))
        self.owner = "stall-supervisor-" + uuid.uuid4().hex
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._tick_lock = threading.Lock()
        self._delivery_lock = threading.Lock()
        self._sampler: threading.Thread | None = None
        self._delivery: threading.Thread | None = None
        self._last_error: str | None = None
        self._ticks = 0
        self._closed = False
        self._lifecycle_lock = threading.Lock()

    @staticmethod
    def _policy_key(policy: StallPolicy) -> str:
        return f"{policy.policy_id}:{policy.version}"

    def watch(self, identity: ObservationIdentity, policy: StallPolicy, *,
              target: Mapping[str, Any]) -> dict[str, Any]:
        """Register/replay one policy; replacement retains old window history."""
        if self._closed:
            raise RuntimeError("stall supervisor is closed")
        if type(policy) is not StallPolicy:
            raise TypeError("policy must be a StallPolicy")
        policy_json = _json(policy.to_dict())
        provenance = {name: value for name, value in identity.to_dict().items()
                      if name in ("run_id", "task_id", "generation", "task_attempt")}
        if "_sdk_subscription_identity" in target:
            raise ValueError("reserved subscription target field")
        target_json = _bounded_json({**provenance, **dict(target),
            "_sdk_subscription_identity": [identity.attempt, identity.fence]}, 4096)
        identity_key = (identity.execution_id, identity.attempt, identity.fence)
        authority = self.kernel.supervision_status(identity.execution_id)
        initial_state = "pending_execution" if authority["execution_state"] in ("queued", "leased") else "registering_policy"
        with self.journal._read_connection(self.journal.options.query_timeout) as (connection, _):
            previous = connection.execute("SELECT * FROM obs_policies WHERE execution_id=? AND state IN ('active','registering_policy','pending_execution')",
                                          (identity.execution_id,)).fetchone()
        if previous is not None and (previous["policy_id"], previous["version"]) == (policy.policy_id, policy.version) and (
                (previous["attempt"], previous["fence"]) == (identity.attempt, identity.fence)
                or json.loads(previous["target_json"]).get("_sdk_subscription_identity") == [identity.attempt, identity.fence]):
            if previous["policy_json"] != policy_json or previous["target_json"] != target_json:
                raise ObservationError("policy version already has different content or target")
            self._try_select_policies()
            return {"state": self._watch_state(identity.execution_id), "replayed": True,
                    "policy_id": policy.policy_id, "version": policy.version}
        if (identity.attempt, identity.fence) != (authority["attempt"], authority["fence"]):
            raise ObservationError("subscription identity is stale")
        with self.journal._transaction() as (connection, now):
            existing = connection.execute("SELECT * FROM obs_policies WHERE policy_id=? AND version=? AND execution_id=? AND attempt=? AND fence=?",
                                          (policy.policy_id, policy.version, *identity_key)).fetchone()
            if existing is not None:
                if (existing["state"] in ("active", "registering_policy", "pending_execution")
                        and existing["policy_json"] == policy_json and existing["target_json"] == target_json):
                    return {"state": existing["state"], "replayed": True,
                            "policy_id": policy.policy_id, "version": policy.version}
                raise ObservationError("superseded policy version cannot be reactivated; use a new version")
            count = connection.execute("SELECT COUNT(*) FROM obs_policies WHERE state IN ('active','registering_policy','pending_execution')").fetchone()[0]
            replacing = connection.execute("SELECT 1 FROM obs_policies WHERE execution_id=? AND state IN ('active','registering_policy','pending_execution')",
                                           (identity.execution_id,)).fetchone()
            if count >= self.max_policies and replacing is None:
                raise ObservationError("supervision subscription capacity exhausted")
            connection.execute("UPDATE obs_policies SET state='superseded',revision=revision+1 WHERE execution_id=? AND state IN ('active','registering_policy','pending_execution')",
                               (identity.execution_id,))
            connection.execute("UPDATE obs_episodes SET state='superseded',ended_at=? WHERE execution_id=? AND state IN ('registering','active')",
                               (now, identity.execution_id))
            connection.execute("UPDATE obs_outbox SET state='superseded',lease_id=NULL,owner=NULL,expires_at=NULL,revision=revision+1 "
                               "WHERE episode_id IN (SELECT episode_id FROM obs_episodes WHERE execution_id=? AND state='superseded') "
                               "AND state NOT IN ('bridged','dead')", (identity.execution_id,))
            connection.execute("INSERT INTO obs_policies(policy_id,version,execution_id,attempt,fence,policy_json,target_json,next_sample_at,state) "
                               "VALUES(?,?,?,?,?,?,?,?,?)", (policy.policy_id, policy.version, *identity_key, policy_json, target_json, now, initial_state))
        self._try_select_policies()
        self._wake.set()
        return {"state": self._watch_state(identity.execution_id), "replayed": False, "replaced": previous is not None,
                "policy_id": policy.policy_id, "version": policy.version}

    def _try_select_policies(self) -> None:
        try:
            self._select_policies()
        except Exception as error:
            # Registration is already durable. The sampler retries this
            # recoverable Kernel handoff rather than losing its receipt.
            self._last_error = f"{type(error).__name__}: {error}"
            self._wake.set()

    def _watch_state(self, execution_id):
        with self.journal._read_connection(self.journal.options.query_timeout) as (connection, _):
            row = connection.execute("SELECT state FROM obs_policies WHERE execution_id=? AND state IN ('active','registering_policy','pending_execution')",
                                     (execution_id,)).fetchone()
            if row is None:
                row = connection.execute("SELECT state FROM obs_policies WHERE execution_id=? ORDER BY rowid DESC LIMIT 1", (execution_id,)).fetchone()
            return "superseded" if row is None else row[0]

    def _select_policies(self):
        with self.journal._read_connection(self.journal.options.query_timeout) as (connection, _):
            rows = connection.execute("SELECT * FROM obs_policies WHERE state IN ('registering_policy','pending_execution') LIMIT ?", (self.max_policies,)).fetchall()
        for row in rows:
            # A short sidecar control transaction serializes desired policy
            # selection. It is separate from all per-byte capture and can be
            # recovered if Kernel selection committed before this commit.
            with self.journal._transaction() as (connection, _):
                current = connection.execute("SELECT state,revision FROM obs_policies WHERE policy_id=? AND version=? AND execution_id=? AND attempt=? AND fence=?",
                                             (row["policy_id"], row["version"], row["execution_id"], row["attempt"], row["fence"])).fetchone()
                if current["state"] not in ("registering_policy", "pending_execution") or current["revision"] != row["revision"]:
                    continue
                status = self.kernel.supervision_status(row["execution_id"])
                if status["execution_state"] in ("queued", "leased"):
                    continue
                key = (row["policy_id"], row["version"], row["execution_id"], row["attempt"], row["fence"])
                if status["execution_state"] != "running":
                    connection.execute("UPDATE obs_policies SET state='closed',revision=revision+1 WHERE policy_id=? AND version=? AND execution_id=? AND attempt=? AND fence=?", key)
                    continue
                # Migration uses the actual current Kernel identity, not an
                # inferred increment, after a persisted queued subscription.
                attempt, fence = status["attempt"], status["fence"]
                if current["state"] != "pending_execution" and (row["attempt"], row["fence"]) != (attempt, fence):
                    connection.execute("UPDATE obs_policies SET state='superseded',revision=revision+1 "
                        "WHERE policy_id=? AND version=? AND execution_id=? AND attempt=? AND fence=?", key)
                    continue
                self.kernel.set_stall_policy(row["execution_id"], attempt=attempt, fence=fence,
                                             policy_version=f"{row['policy_id']}:{row['version']}")
                connection.execute("UPDATE obs_policies SET state='active',attempt=?,fence=?,revision=revision+1 WHERE policy_id=? AND version=? AND execution_id=? AND attempt=? AND fence=?",
                                   (attempt, fence, *key))

    def _observed(self, row, policy, status, report):
        if status["execution_state"] != "running" or (status["attempt"], status["fence"]) != (row["attempt"], row["fence"]):
            return None, "execution_identity_changed", None
        if not report["current"] or report.get("truncated") or report.get("collection_gaps", 0) > 0 or any(
                source.get("continuity") == "unknown" for source in report["sources"]):
            return None, "collection_unknown", None
        if not report["sources"]:
            return None, "collector_not_observed", None
        sources = {source["source_id"]: source for source in report["sources"]}
        for wait in report.get("waits", ()):
            if wait["state"] != "waiting":
                continue
            details = wait.get("details", {})
            reason = details.get("reason") or details.get("kind")
            if reason is None or reason not in policy.wait_exemptions:
                continue
            owner = details.get("_collector_source_id")
            if "_collector_source_id" in details and type(owner) is not str:
                return None, "collection_unknown", None
            relevant = (sources.get(owner),) if owner is not None else tuple(sources.values())
            if any(source is None or source.get("state") != "active" or
                   source.get("continuity") != "observed" for source in relevant):
                return None, "collection_unknown", None
            return None, "wait_exempt", reason
        for wait in report.get("child_waits", ()):
            if wait["state"] not in ("waiting", "open"):
                continue
            details = wait.get("details", {})
            reason = wait.get("reason") or details.get("reason") or details.get("kind")
            if reason is not None and reason in policy.wait_exemptions:
                return None, "wait_exempt", reason
        metrics = {}
        for name in policy.metrics:
            if name == "progress":
                value = status["progress_revision"]
            elif name in ("output", "model", "tool"):
                prefix = {"output": ("stdout_bytes", "stderr_bytes"), "model": ("model_",), "tool": ("tool_",)}[name]
                selected = [metric["count"] for key, metric in report["metrics"].items()
                            if key in prefix or (name != "output" and key.startswith(prefix))]
                value = sum(selected) if selected else None
            else:
                metric = report["metrics"].get(name)
                value = None if metric is None else metric["count"]
            if value is None:
                return None, "metric_not_installed:" + name, None
            metrics[name] = value
        return metrics, None, None

    def tick(self) -> dict[str, Any]:
        """Advance at most the configured admitted policies and register outbox."""
        if self._closed:
            return {"state": "closed", "evaluated": 0}
        if not self._tick_lock.acquire(blocking=False):
            return {"state": "pending", "reason": "evaluation_busy", "evaluated": 0}
        evaluated = 0
        try:
            self._select_policies()
            with self.journal._read_connection(self.journal.options.query_timeout) as (connection, _):
                rows = connection.execute("SELECT * FROM obs_policies WHERE state='active' ORDER BY rowid LIMIT ?",
                                          (self.max_policies,)).fetchall()
            for row in rows:
                try:
                    self._evaluate(row)
                    evaluated += 1
                except Exception as error:
                    self._last_error = f"{type(error).__name__}: {error}"
            self._clear_pending()
            self._register_pending()
            self._ticks += 1
            self._wake.set()
            return {"state": "evaluated", "evaluated": evaluated, "error": self._last_error}
        except Exception as error:
            self._last_error = f"{type(error).__name__}: {error}"
            return {"state": "degraded", "evaluated": evaluated, "error": self._last_error}
        finally:
            self._tick_lock.release()

    def _evaluate(self, row) -> None:
        data = json.loads(row["policy_json"])
        data["metrics"], data["wait_exemptions"] = tuple(data["metrics"]), tuple(data["wait_exemptions"])
        policy = StallPolicy(**data)
        sample = self.clock_sample()
        status = self.kernel.supervision_status(row["execution_id"])
        report = self.journal.inspect(row["execution_id"])
        metrics, reason, exempt_reason = self._observed(row, policy, status, report)
        checkpoint = None
        previous = json.loads(row["continuity_id"]) if row["continuity_id"] else None
        sources = sorted(source["source_id"] for source in report["sources"])
        if previous:
            checkpoint = ClockCheckpoint.from_dict(previous["clock"])
            elapsed = sample.elapsed_at - checkpoint.elapsed_at
            if checkpoint.effective_time(sample) is None or sample.wall_at < checkpoint.wall_at:
                reason = "clock_continuity_unknown"
            elif elapsed > max(self.sample_interval * 2.5, self.journal.options.process_freshness):
                reason = "sampling_gap"
            elif previous.get("sources") != sources:
                reason = "collector_identity_changed"
            elif previous.get("gap_count", 0) != report["collection_gaps"]:
                reason = "collection_gap"
        elif sample.domain_id is None:
            reason = "clock_continuity_unknown"
        progress_changed = status["progress_revision"] != row["progress_revision"]
        if previous and metrics is not None and any(metrics[name] < previous["metrics"].get(name, metrics[name]) for name in metrics):
            reason = "metric_counter_regressed"
        now = sample.wall_at
        key = (row["policy_id"], row["version"], row["execution_id"], row["attempt"], row["fence"])
        with self.journal._transaction() as (connection, _):
            current = connection.execute("SELECT * FROM obs_policies WHERE policy_id=? AND version=? AND execution_id=? AND attempt=? AND fence=?", key).fetchone()
            if current["revision"] != row["revision"] or current["state"] != "active":
                return
            baseline, consecutive, episode = row["baseline_at"], row["consecutive"], row["episode_id"]
            identity_changed = reason == "execution_identity_changed"
            if reason is not None or progress_changed:
                if baseline is not None:
                    self._window(connection, row, baseline, now, "exempt" if reason == "wait_exempt" else "unknown" if reason else "progress",
                                 {"reason": reason or "confirmed_progress", "wait_reason": exempt_reason,
                                  "progress_revision": status["progress_revision"]})
                baseline, consecutive = None, 0
                if progress_changed or identity_changed:
                    self._end_episode(connection, episode, now, "progress" if progress_changed else "superseded")
            # An unknown sample cannot form the beginning of a complete window.
            if reason is None:
                if baseline is None:
                    baseline = now
                    baseline_metrics = metrics
                else:
                    baseline_metrics = previous["baseline_metrics"]
                    # Freshness tolerance is not permission to extrapolate
                    # an old persisted endpoint into a completed later window.
                    observed_end = min(now, report["captured_at"]) if report["captured_at"] is not None else baseline
                    if observed_end >= row["next_sample_at"]:
                        stagnant = all(metrics[name] == baseline_metrics[name] for name in policy.metrics)
                        self._window(connection, row, baseline, observed_end, "stalled" if stagnant else "activity",
                                     {"baseline_metrics": baseline_metrics, "metrics": metrics,
                                      "progress_revision": status["progress_revision"]})
                        consecutive = consecutive + 1 if stagnant else 0
                        if not stagnant:
                            self._end_episode(connection, episode, now, "activity")
                        if consecutive >= policy.consecutive_windows and episode is None:
                            episode = uuid.uuid4().hex
                            notification_id = uuid.uuid4().hex
                            disposition = {"execution_id": row["execution_id"], "attempt": row["attempt"],
                                           "fence": row["fence"], "progress_revision": status["progress_revision"],
                                           "episode_id": episode, "policy_version": self._policy_key(policy)}
                            target = json.loads(row["target_json"])
                            target.pop("_sdk_subscription_identity", None)
                            payload = {"notification_id": notification_id, "kind": "stalled", "target": target,
                                       "execution_id": row["execution_id"], "attempt": row["attempt"], "fence": row["fence"],
                                       "episode_id": episode, "policy_id": policy.policy_id, "policy_version": policy.version,
                                       "progress_revision": status["progress_revision"], "disposition": disposition,
                                       "max_deliveries": policy.max_deliveries, "consecutive_windows": consecutive,
                                       "observed_at": now}
                            connection.execute("INSERT INTO obs_episodes VALUES(?,?,?,?,?,?,?,'registering',?,NULL,?,?)",
                                               (episode, *key, status["progress_revision"], now, notification_id, _json(disposition)))
                            connection.execute("INSERT INTO obs_outbox(notification_id,episode_id,payload,state,created_at,max_attempts,next_attempt_at) "
                                               "VALUES(?,?,?,'awaiting_authority',?,?,?)", (notification_id, episode, _json(payload), now, policy.max_deliveries, now))
                        baseline, baseline_metrics = observed_end, metrics
                continuity = {"clock": sample.to_dict(), "metrics": metrics, "baseline_metrics": baseline_metrics,
                              "sources": sources, "gap_count": report["collection_gaps"]}
            else:
                continuity = None
            state = "superseded" if identity_changed else "active"
            connection.execute("UPDATE obs_policies SET baseline_at=?,next_sample_at=?,continuity_id=?,progress_revision=?,"
                               "consecutive=?,episode_id=?,state=?,revision=revision+1 WHERE policy_id=? AND version=? AND execution_id=? AND attempt=? AND fence=? AND revision=?",
                               (baseline, now + policy.sample_interval if baseline is None else baseline + policy.sample_interval,
                                None if continuity is None else _json(continuity), status["progress_revision"], consecutive, episode, state,
                                *key, row["revision"]))

    @staticmethod
    def _window(connection, row, started_at, ended_at, state, details):
        # Backward wall time is retained as a diagnostic, never a valid window.
        connection.execute("INSERT OR IGNORE INTO obs_windows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (uuid.uuid4().hex, row["policy_id"], row["version"], row["execution_id"], row["attempt"], row["fence"],
                            started_at, ended_at, state, row["progress_revision"], details.get("progress_revision"), _json(details), row["revision"]))

    @staticmethod
    def _end_episode(connection, episode, now, state):
        if episode is None:
            return
        row = connection.execute("SELECT * FROM obs_episodes WHERE episode_id=?", (episode,)).fetchone()
        if row is None or row["state"] not in ("registering", "active", "ending"):
            return
        prior = json.loads(row["details"])
        token = prior["disposition"] if "disposition" in prior else prior
        connection.execute("UPDATE obs_episodes SET state='ending',ended_at=?,details=? WHERE episode_id=?",
                           (now, _json({"disposition": token, "end_state": state}), episode))
        connection.execute("UPDATE obs_outbox SET state='superseded',lease_id=NULL,owner=NULL,expires_at=NULL,revision=revision+1 "
                           "WHERE episode_id=? AND state NOT IN ('bridged','dead')", (episode,))

    def _clear_pending(self):
        with self.journal._read_connection(self.journal.options.query_timeout) as (connection, _):
            rows = connection.execute("SELECT * FROM obs_episodes WHERE state='ending' LIMIT ?", (self.max_policies,)).fetchall()
        for row in rows:
            details = json.loads(row["details"])
            try:
                receipt = self.kernel.clear_stall_episode(expected=details["disposition"],
                                                          timeout_seconds=self.journal.options.write_timeout)
                if isinstance(receipt, dict) and receipt.get("state") in ("pending", "unknown"):
                    continue
            except Exception as error:
                self._last_error = f"{type(error).__name__}: {error}"
                continue
            with self.journal._transaction() as (connection, _):
                changed = connection.execute("UPDATE obs_episodes SET state=? WHERE episode_id=? AND state='ending'",
                                             (details["end_state"], row["episode_id"])).rowcount
                if changed:
                    connection.execute("UPDATE obs_policies SET episode_id=NULL,revision=revision+1 WHERE episode_id=?",
                                       (row["episode_id"],))

    def _register_pending(self) -> None:
        with self.journal._read_connection(self.journal.options.query_timeout) as (connection, _):
            rows = connection.execute("SELECT * FROM obs_episodes WHERE state='registering' LIMIT ?", (self.max_policies,)).fetchall()
        for row in rows:
            disposition = json.loads(row["details"])
            try:
                self.kernel.register_stall_episode(**disposition)
            except Exception as error:
                current = self.kernel.supervision_status(row["execution_id"])
                stale = ((current["attempt"], current["fence"]) != (row["attempt"], row["fence"])
                         or current["progress_revision"] != row["progress_revision"] or current["execution_state"] != "running")
                with self.journal._transaction() as (connection, now):
                    if stale:
                        self._end_episode(connection, row["episode_id"], now, "superseded")
                    else:
                        connection.execute("UPDATE obs_outbox SET last_error=? WHERE episode_id=?", (_json({"type": type(error).__name__, "message": str(error)}), row["episode_id"]))
                continue
            with self.journal._transaction() as (connection, _):
                changed = connection.execute("UPDATE obs_episodes SET state='active' WHERE episode_id=? AND state='registering'", (row["episode_id"],)).rowcount
                if changed:
                    connection.execute("UPDATE obs_outbox SET state='pending',last_error=NULL,revision=revision+1 WHERE episode_id=? AND state='awaiting_authority'", (row["episode_id"],))

    def deliver_pending(self) -> dict[str, Any]:
        """Try one bridge invocation; normally called only by the fixed worker."""
        if self.notification_bridge is None:
            return {"state": "pending", "reason": "bridge_not_configured"}
        if not self._delivery_lock.acquire(blocking=False):
            return {"state": "pending", "reason": "delivery_capacity_occupied"}
        try:
            with self.journal._transaction() as (connection, now):
                connection.execute("UPDATE obs_outbox SET state=CASE WHEN attempts>=max_attempts THEN 'dead' ELSE 'pending' END,"
                                   "lease_id=NULL,owner=NULL,expires_at=NULL,next_attempt_at=?,revision=revision+1 "
                                   "WHERE state='delivering' AND expires_at<=?", (now, now))
                row = connection.execute("SELECT * FROM obs_outbox WHERE state='pending' AND next_attempt_at<=? ORDER BY created_at LIMIT 1", (now,)).fetchone()
                if row is None:
                    return {"state": "idle"}
                lease_id = uuid.uuid4().hex
                connection.execute("UPDATE obs_outbox SET state='delivering',attempts=attempts+1,lease_id=?,owner=?,expires_at=?,revision=revision+1 "
                                   "WHERE notification_id=?", (lease_id, self.owner, now + self.delivery_lease_seconds, row["notification_id"]))
            error = None
            try:
                returned = self.notification_bridge(json.loads(row["payload"]))
                if inspect.isawaitable(returned):
                    if inspect.iscoroutine(returned):
                        returned.close()
                    raise TypeError("notification bridge must be synchronous")
            except Exception as caught:
                raw_message = str(caught).encode("utf-8")
                error = {"type": type(caught).__name__,
                    "message": raw_message[:1024].decode("utf-8", errors="ignore"),
                    "truncated": len(raw_message) > 1024}
            with self.journal._transaction() as (connection, now):
                current = connection.execute("SELECT * FROM obs_outbox WHERE notification_id=?", (row["notification_id"],)).fetchone()
                if current["state"] != "delivering" or current["lease_id"] != lease_id or current["expires_at"] <= now:
                    return {"state": "stale", "notification_id": row["notification_id"]}
                state = "bridged" if error is None else "dead" if current["attempts"] >= current["max_attempts"] else "pending"
                connection.execute("UPDATE obs_outbox SET state=?,bridged_at=?,last_error=?,lease_id=NULL,owner=NULL,expires_at=NULL,"
                                   "next_attempt_at=?,revision=revision+1 WHERE notification_id=?",
                                   (state, now if error is None else None, None if error is None else _json(error), now + self.retry_delay, row["notification_id"]))
            return {"state": state, "notification_id": row["notification_id"]}
        finally:
            self._delivery_lock.release()

    def retry_dead(self, notification_id: str, *, expected_revision: int) -> dict[str, Any]:
        with self.journal._transaction() as (connection, now):
            row = connection.execute("SELECT * FROM obs_outbox WHERE notification_id=?", (notification_id,)).fetchone()
            if row is None:
                raise KeyError(notification_id)
            if row["revision"] != expected_revision or row["state"] != "dead":
                raise ObservationError("notification retry requires current dead revision")
            connection.execute("UPDATE obs_outbox SET state='pending',attempts=0,next_attempt_at=?,last_error=NULL,revision=revision+1 WHERE notification_id=?", (now, notification_id))
        self._wake.set()
        return {"state": "pending", "notification_id": notification_id}

    def outbox(self, *, limit: int | None = None) -> tuple[dict[str, Any], ...]:
        maximum = self._page_limit(limit)
        with self.journal._read_connection(self.journal.options.query_timeout) as (connection, _):
            rows = connection.execute("SELECT * FROM obs_outbox ORDER BY created_at LIMIT ?", (maximum,)).fetchall()
            result = []
            for row in rows:
                record = {**dict(row), "payload": json.loads(row["payload"])}
                if len(_json([*result, record]).encode("utf-8")) > self.journal.options.query_bytes:
                    if not result:
                        record["payload"] = {"truncated": True}
                        record["last_error"] = (record.get("last_error") or "").encode("utf-8")[:1024].decode("utf-8", errors="ignore")
                        result.append(record)
                    break
                result.append(record)
            return tuple(result)

    def windows(self, execution_id: str, *, after: str | None = None, limit: int | None = None) -> dict[str, Any]:
        maximum = self._page_limit(limit)
        with self.journal._read_connection(self.journal.options.query_timeout) as (connection, _):
            cursor = 0 if after is None else int(after)
            if cursor < 0:
                raise ValueError("window cursor must be nonnegative")
            rows = connection.execute("SELECT rowid,* FROM obs_windows WHERE execution_id=? AND rowid>? ORDER BY rowid LIMIT ?",
                                      (execution_id, cursor, maximum + 1)).fetchall()
            selected = []
            for row in rows[:maximum]:
                record = {**dict(row), "details": json.loads(row["details"])}
                if len(_json([*selected, record]).encode("utf-8")) > self.journal.options.query_bytes:
                    if not selected:
                        record = {name: record[name] for name in ("rowid", "window_id", "state", "started_at", "ended_at")}
                        record["details"] = {"truncated": True}
                        selected.append(record)
                    break
                selected.append(record)
            return {"windows": tuple(selected), "cursor": str(selected[-1]["rowid"]) if selected else after,
                    "has_more": len(rows) > len(selected), "complete": len(selected) == min(len(rows), maximum)
                        and not any(row["details"].get("truncated") for row in selected)}

    def _page_limit(self, limit):
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError("page limit must be a positive integer")
        return self.journal.options.page_events if limit is None else min(limit, self.journal.options.page_events)

    def start(self) -> StallSupervisor:
        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("stall supervisor is closed")
            if self._sampler is None:
                self._sampler = threading.Thread(target=self._sample_loop, name="dispatcher-stall-sampler", daemon=True)
                self._sampler.start()
            if self.notification_bridge is not None and self._delivery is None:
                self._delivery = threading.Thread(target=self._delivery_loop, name="dispatcher-stall-bridge", daemon=True)
                self._delivery.start()
        return self

    def _sample_loop(self):
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.sample_interval)

    def _delivery_loop(self):
        while not self._stop.is_set():
            try:
                result = self.deliver_pending()
                if result["state"] == "bridged":
                    continue
            except Exception as error:
                self._last_error = f"{type(error).__name__}: {error}"
            self._wake.wait(self.sample_interval)
            self._wake.clear()

    def health(self) -> dict[str, Any]:
        return {"ticks": self._ticks, "error": self._last_error, "closed": self._closed,
                "sampler_alive": self._sampler is not None and self._sampler.is_alive(),
                "delivery_alive": self._delivery is not None and self._delivery.is_alive(),
                "delivery_capacity": 1, "delivery_occupied": self._delivery_lock.locked()}

    def close(self, *, timeout: float = 1) -> dict[str, Any]:
        deadline = time.monotonic() + positive(timeout, "timeout")
        self._stop.set()
        self._wake.set()
        self._closed = True
        for thread in (self._sampler, self._delivery):
            if thread is not None:
                thread.join(max(0.0, deadline - time.monotonic()))
        report = self.health()
        report["state"] = "pending" if report["sampler_alive"] or report["delivery_alive"] else "closed"
        return report


__all__ = ["StallSupervisor"]
