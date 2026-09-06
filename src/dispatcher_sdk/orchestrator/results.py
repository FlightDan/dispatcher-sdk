"""Durable, fenced delivery of authoritative Kernel results to applications."""
from __future__ import annotations

from contextlib import contextmanager
import json
import math
import sqlite3
from typing import Sequence
import uuid

from ..execution_kernel import (
    ExecutionError, ExecutionResultV2, ExecutionSnapshot, ResultConflictError,
    ResultOutboxStatusV2, StaleFenceError,
)
from .contracts import canonical


def _positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return float(value)


def _identity(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _integer(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


class ResultsMixin:
    def _init_results(self, connection: sqlite3.Connection) -> None:
        self.max_result_deliveries = _integer(
            getattr(self, "max_result_deliveries", 5), "max_result_deliveries")
        connection.execute("""CREATE TABLE IF NOT EXISTS sdk_results (
            result_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL UNIQUE,
            result_json TEXT NOT NULL, kernel_revision INTEGER NOT NULL CHECK(kernel_revision>0),
            state TEXT NOT NULL CHECK(state IN ('pending','delivering','delivered','dead')),
            lease_id TEXT, lease_owner TEXT, fence INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL CHECK(max_attempts>0),
            lease_expires_at REAL, next_attempt_at REAL NOT NULL, last_error_json TEXT,
            revision INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS sdk_results_delivery ON sdk_results(state,next_attempt_at)")
        connection.execute("CREATE TABLE IF NOT EXISTS sdk_result_clock (id INTEGER PRIMARY KEY CHECK(id=1), value REAL NOT NULL)")
        connection.execute("INSERT OR IGNORE INTO sdk_result_clock VALUES(1,0)")

    def _results_now(self):
        timestamp = self.clock()
        if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("clock must return a finite nonnegative timestamp")
        return float(timestamp)

    @contextmanager
    def _results_transaction(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            observed = self._results_now()
            now = max(observed, connection.execute("SELECT value FROM sdk_result_clock WHERE id=1").fetchone()[0])
            connection.execute("UPDATE sdk_result_clock SET value=? WHERE id=1", (now,))
            connection.execute("SAVEPOINT result_operation")
            try:
                yield connection, now
            except BaseException:
                # Preserve observed time even when a rejected stale operation
                # rolls back, so a backwards wall clock cannot revive a lease.
                connection.execute("ROLLBACK TO result_operation")
                connection.execute("RELEASE result_operation")
                connection.commit()
                raise
            connection.execute("RELEASE result_operation")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _result_record(row):
        return {
            "result_id": row["result_id"], "execution_id": row["execution_id"],
            "result": ExecutionResultV2.from_dict(json.loads(row["result_json"])),
            "kernel_revision": row["kernel_revision"], "state": row["state"],
            "lease_id": row["lease_id"], "owner": row["lease_owner"],
            "fence": row["fence"], "attempts": row["attempts"],
            "max_attempts": row["max_attempts"], "expires_at": row["lease_expires_at"],
            "next_attempt_at": row["next_attempt_at"],
            "last_error": None if row["last_error_json"] is None else
                ExecutionError.from_dict(json.loads(row["last_error_json"])),
            "revision": row["revision"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def pump_results(self, *, limit: int = 100, lease_seconds: float = 30.0) -> int:
        """Commit each result locally before acknowledging its Kernel delivery.

        A crash between these commits replays the identical immutable fact; it
        never resets the application delivery state or consumes its lease.
        """
        _integer(limit, "limit")
        _positive(lease_seconds, "lease_seconds")
        self.kernel.reap_outbox()
        count = 0
        for _ in range(limit):
            delivery = self.kernel.claim_outbox("sdk-result-pump", lease_seconds=lease_seconds)
            if delivery is None:
                break
            result = delivery["result"]
            if type(result) is not ExecutionResultV2:
                raise TypeError("Kernel outbox result must be ExecutionResultV2")
            snapshot = self.kernel.get(result.execution_id)
            if type(snapshot) is not ExecutionSnapshot or (
                snapshot.result is None or canonical(snapshot.result.to_dict()) != canonical(result.to_dict())
                or snapshot.execution_id != delivery["execution_id"]
                or result.result_id != delivery["result_id"]
                or snapshot.command.execution_id != result.execution_id
                or snapshot.command.correlation_id != result.correlation_id
                or snapshot.command.causation_id != result.causation_id
                or snapshot.state != result.status
            ):
                raise ResultConflictError("Kernel delivery differs from authoritative execution")
            self.sync_execution(result.execution_id)
            encoded = canonical(result.to_dict())
            with self._results_transaction() as (connection, now):
                previous = connection.execute(
                    "SELECT * FROM sdk_results WHERE result_id=? OR execution_id=?",
                    (result.result_id, result.execution_id),
                ).fetchone()
                if previous is not None:
                    if (previous["result_id"] != result.result_id
                            or previous["execution_id"] != result.execution_id
                            or previous["result_json"] != encoded
                            or previous["kernel_revision"] != snapshot.revision):
                        raise ResultConflictError("SDK already holds a different immutable result")
                else:
                    connection.execute(
                        "INSERT INTO sdk_results(result_id,execution_id,result_json,kernel_revision,"
                        "state,max_attempts,next_attempt_at,created_at,updated_at) "
                        "VALUES (?,?,?,?,'pending',?,?,?,?)",
                        (result.result_id, result.execution_id, encoded, snapshot.revision,
                         self.max_result_deliveries, now, now, now),
                    )
            self.kernel.ack_outbox(result.result_id, lease_id=delivery["lease_id"], fence=delivery["fence"])
            count += 1
        return count

    @staticmethod
    def _reap_results_tx(connection, now):
        rows = connection.execute(
            "SELECT * FROM sdk_results WHERE state='delivering' AND lease_expires_at<=?", (now,),
        ).fetchall()
        for row in rows:
            state = "dead" if row["attempts"] >= row["max_attempts"] else "pending"
            error = ExecutionError(code="outbox_lease_expired", message="result delivery lease expired",
                                   retryable=state == "pending", details={"attempts": row["attempts"]})
            connection.execute(
                "UPDATE sdk_results SET state=?,lease_expires_at=NULL,next_attempt_at=?,"
                "last_error_json=?,revision=revision+1,updated_at=? WHERE result_id=?",
                (state, now, canonical(error.to_dict()), now, row["result_id"]),
            )
        return len(rows)

    def reap_results(self) -> int:
        inbound = self.kernel.reap_outbox()
        with self._results_transaction() as (connection, now):
            return len(inbound) + self._reap_results_tx(connection, now)

    def kernel_result_outbox_status(self, execution_ids: Sequence[str] | None = None) -> ResultOutboxStatusV2:
        """Inspect Kernel-to-SDK transport, separately from application delivery."""
        return self.kernel.result_outbox_status(execution_ids)

    def load_kernel_result_outbox(self, result_id: str) -> dict:
        """Read an inbound transport receipt through the public Kernel API."""
        return self.kernel.load_result_outbox(result_id)

    def retry_kernel_result_outbox(self, result_id: str, *, expected_revision: int) -> dict:
        """Reopen an inbound dead letter; no execution or application retry occurs."""
        return self.kernel.retry_result_outbox(result_id, expected_revision=expected_revision)

    def claim_results(self, *, owner: str, lease_seconds: float, limit: int) -> tuple[dict, ...]:
        _identity(owner, "owner")
        duration = _positive(lease_seconds, "lease_seconds")
        _integer(limit, "limit")
        with self._results_transaction() as (connection, now):
            expires = now + duration
            if not math.isfinite(expires):
                raise ValueError("lease expiry must be finite")
            self._reap_results_tx(connection, now)
            rows = connection.execute(
                "SELECT * FROM sdk_results WHERE state='pending' AND attempts<max_attempts "
                "AND next_attempt_at<=? ORDER BY created_at,result_id LIMIT ?", (now, limit),
            ).fetchall()
            claims = []
            for row in rows:
                lease_id = uuid.uuid4().hex
                connection.execute(
                    "UPDATE sdk_results SET state='delivering',lease_id=?,lease_owner=?,fence=fence+1,"
                    "attempts=attempts+1,lease_expires_at=?,revision=revision+1,updated_at=? WHERE result_id=?",
                    (lease_id, owner, expires, now, row["result_id"]),
                )
                claims.append({"result": json.loads(row["result_json"]),
                               "kernel_revision": row["kernel_revision"], "lease_id": lease_id,
                               "owner": owner, "fence": row["fence"] + 1, "lease_until": expires,
                               "attempts": row["attempts"] + 1})
            return tuple(claims)

    def acknowledge_result(self, result_id: str, *, lease_id: str, fence: int) -> dict:
        _identity(result_id, "result_id")
        _identity(lease_id, "lease_id")
        _integer(fence, "fence")
        with self._results_transaction() as (connection, now):
            row = connection.execute("SELECT * FROM sdk_results WHERE result_id=?", (result_id,)).fetchone()
            if row is None:
                raise KeyError(result_id)
            same = row["lease_id"] == lease_id and row["fence"] == fence
            if same and row["state"] == "delivered":
                return self._result_record(row)
            if not same or row["state"] != "delivering" or row["lease_expires_at"] <= now:
                raise StaleFenceError("SDK result delivery lease is stale")
            connection.execute(
                "UPDATE sdk_results SET state='delivered',lease_expires_at=NULL,revision=revision+1,"
                "updated_at=? WHERE result_id=?", (now, result_id),
            )
            return self._result_record(connection.execute(
                "SELECT * FROM sdk_results WHERE result_id=?", (result_id,),
            ).fetchone())

    def load_result_outbox(self, result_id: str) -> dict:
        _identity(result_id, "result_id")
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM sdk_results WHERE result_id=?", (result_id,)).fetchone()
            if row is None:
                raise KeyError(result_id)
            return self._result_record(row)
        finally:
            connection.close()

    def result_outbox_status(self, execution_ids: Sequence[str] | None = None) -> ResultOutboxStatusV2:
        selected = None
        if execution_ids is not None:
            values = tuple(execution_ids)
            for value in values:
                _identity(value, "execution_id")
            if len(set(values)) != len(values):
                raise ValueError("execution_ids must be unique")
            selected = frozenset(values)
        connection = self._connect()
        try:
            rows = connection.execute("SELECT execution_id,state,created_at FROM sdk_results WHERE state!='delivered'").fetchall()
        finally:
            connection.close()
        rows = [row for row in rows if selected is None or row["execution_id"] in selected]
        times = [row["created_at"] for row in rows if row["state"] == "pending"]
        return ResultOutboxStatusV2(pending=sum(row["state"] == "pending" for row in rows),
                                   delivering=sum(row["state"] == "delivering" for row in rows),
                                   dead=sum(row["state"] == "dead" for row in rows),
                                   oldest_pending_at=min(times) if times else None)

    def retry_result_outbox(self, result_id: str, *, expected_revision: int) -> dict:
        _identity(result_id, "result_id")
        _integer(expected_revision, "expected_revision")
        with self._results_transaction() as (connection, now):
            row = connection.execute("SELECT * FROM sdk_results WHERE result_id=?", (result_id,)).fetchone()
            if row is None:
                raise KeyError(result_id)
            if (row["state"] == "pending" and row["revision"] == expected_revision + 1
                    and row["attempts"] == 0 and row["last_error_json"] is None):
                return self._result_record(row)
            if row["revision"] != expected_revision:
                raise StaleFenceError("SDK result retry revision is stale")
            if row["state"] != "dead":
                raise ValueError("only a dead SDK result can be retried")
            connection.execute(
                "UPDATE sdk_results SET state='pending',lease_id=NULL,lease_owner=NULL,lease_expires_at=NULL,"
                "attempts=0,next_attempt_at=?,last_error_json=NULL,revision=revision+1,updated_at=? WHERE result_id=?",
                (now, now, result_id),
            )
            return self._result_record(connection.execute(
                "SELECT * FROM sdk_results WHERE result_id=?", (result_id,),
            ).fetchone())
