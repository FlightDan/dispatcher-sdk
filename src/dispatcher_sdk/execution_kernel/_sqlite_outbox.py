"""Fenced delivery state machine for terminal execution results."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional, Sequence
import uuid

from .contracts import ExecutionError, ExecutionResultV2
from .errors import ResultConflictError, StaleFenceError
from ._sqlite_base import encode_json
from .outbox_status import ResultOutboxStatusV2


OUTBOX_STATES = frozenset({"pending", "delivering", "delivered", "dead"})


class ResultOutboxMixin:
    def _insert_result_outbox(
        self,
        connection: sqlite3.Connection,
        result: ExecutionResultV2,
        timestamp: float,
    ) -> None:
        encoded = encode_json(result.to_dict())
        existing = connection.execute(
            "SELECT * FROM kernel_result_outbox WHERE result_id = ? OR execution_id = ?",
            (result.result_id, result.execution_id),
        ).fetchone()
        if existing is not None:
            if (
                existing["result_id"] == result.result_id
                and existing["execution_id"] == result.execution_id
                and existing["result_json"] == encoded
            ):
                return
            raise ResultConflictError(
                f"result_id/execution_id already has another outbox fact: {result.result_id}"
            )
        cursor = connection.execute(
            """INSERT INTO kernel_result_outbox
               (result_id, execution_id, result_json, state, lease_id, lease_owner,
                fence, attempts, max_attempts, lease_expires_at, next_attempt_at,
                last_error_json, revision, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', NULL, NULL, 0, 0, ?, NULL, ?, NULL, 1, ?, ?)""",
            (
                result.result_id,
                result.execution_id,
                encoded,
                self.outbox_max_attempts,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        self._cas(cursor, "result outbox insertion")

    @staticmethod
    def _outbox_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "result_id": row["result_id"],
            "execution_id": row["execution_id"],
            "result": ExecutionResultV2.from_dict(json.loads(row["result_json"])),
            "state": row["state"],
            "lease_id": row["lease_id"],
            "owner": row["lease_owner"],
            "fence": row["fence"],
            "attempts": row["attempts"],
            "max_attempts": row["max_attempts"],
            "expires_at": row["lease_expires_at"],
            "next_attempt_at": row["next_attempt_at"],
            "last_error": (
                None
                if row["last_error_json"] is None
                else ExecutionError.from_dict(json.loads(row["last_error_json"]))
            ),
            "revision": row["revision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def result_outbox(
        self,
        *,
        states: Optional[set[str]] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        selected = OUTBOX_STATES if states is None else frozenset(states)
        if not selected or not selected.issubset(OUTBOX_STATES):
            raise ValueError("invalid result outbox state filter")
        ordered = tuple(sorted(selected))
        padded = ordered + ("__not_an_outbox_state__",) * (4 - len(ordered))
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM kernel_result_outbox
                   WHERE state IN (?, ?, ?, ?)
                   ORDER BY created_at, result_id LIMIT ?""",
                (*padded, limit),
            ).fetchall()
        return [self._outbox_record(row) for row in rows]

    def outbox(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.result_outbox(states={"pending", "delivering"}, limit=limit)

    def load_result_outbox(self, result_id: str) -> dict[str, Any]:
        if type(result_id) is not str or not result_id.strip():
            raise ValueError("result_id must be a non-empty string")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM kernel_result_outbox WHERE result_id=?",
                (result_id,),
            ).fetchone()
        if row is None:
            raise KeyError(result_id)
        return self._outbox_record(row)

    def result_outbox_status(
        self,
        execution_ids: Sequence[str] | None = None,
    ) -> ResultOutboxStatusV2:
        """Return exact queue counts without exposing a database connection."""

        selected = None
        if execution_ids is not None:
            values = tuple(execution_ids)
            if any(type(item) is not str or not item.strip() for item in values):
                raise ValueError("execution_ids must contain non-empty strings")
            if len(set(values)) != len(values):
                raise ValueError("execution_ids must be unique")
            selected = frozenset(values)
        with self._lock:
            rows = self._connection.execute(
                "SELECT execution_id,state,created_at FROM kernel_result_outbox "
                "WHERE state!='delivered'"
            ).fetchall()
        visible = tuple(
            row
            for row in rows
            if selected is None or row["execution_id"] in selected
        )
        pending_times = tuple(
            float(row["created_at"])
            for row in visible
            if row["state"] == "pending"
        )
        return ResultOutboxStatusV2(
            pending=sum(row["state"] == "pending" for row in visible),
            delivering=sum(row["state"] == "delivering" for row in visible),
            dead=sum(row["state"] == "dead" for row in visible),
            oldest_pending_at=min(pending_times) if pending_times else None,
        )

    def retry_result_outbox(
        self,
        result_id: str,
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        """Explicitly reopen one dead result delivery under revision CAS."""

        if type(result_id) is not str or not result_id.strip():
            raise ValueError("result_id must be a non-empty string")
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        with self._transaction() as (connection, timestamp):
            row = connection.execute(
                "SELECT * FROM kernel_result_outbox WHERE result_id=?",
                (result_id,),
            ).fetchone()
            if row is None:
                raise KeyError(result_id)
            if (
                row["state"] == "pending"
                and row["revision"] == expected_revision + 1
                and row["attempts"] == 0
                and row["last_error_json"] is None
            ):
                return self._outbox_record(row)
            if row["revision"] != expected_revision:
                raise StaleFenceError("result outbox retry revision is stale")
            if row["state"] != "dead":
                raise ValueError("only a dead result outbox record can be retried")
            cursor = connection.execute(
                "UPDATE kernel_result_outbox SET state='pending',lease_id=NULL,"
                "lease_owner=NULL,lease_expires_at=NULL,attempts=0,"
                "next_attempt_at=?,last_error_json=NULL,revision=?,updated_at=? "
                "WHERE result_id=? AND state='dead' AND revision=?",
                (
                    timestamp,
                    expected_revision + 1,
                    timestamp,
                    result_id,
                    expected_revision,
                ),
            )
            self._cas(cursor, "manual result outbox retry")
            return self._outbox_record(
                connection.execute(
                    "SELECT * FROM kernel_result_outbox WHERE result_id=?",
                    (result_id,),
                ).fetchone()
            )

    def _reap_outbox_in_transaction(
        self, connection: sqlite3.Connection, timestamp: float
    ) -> list[str]:
        rows = connection.execute(
            """SELECT * FROM kernel_result_outbox
               WHERE state = 'delivering' AND lease_expires_at <= ?
               ORDER BY created_at, result_id""",
            (timestamp,),
        ).fetchall()
        changed: list[str] = []
        for row in rows:
            state = "dead" if row["attempts"] >= row["max_attempts"] else "pending"
            revision = row["revision"] + 1
            error = ExecutionError(
                code="outbox_lease_expired",
                message="result delivery lease expired",
                retryable=state == "pending",
                details={"attempts": row["attempts"]},
            )
            cursor = connection.execute(
                """UPDATE kernel_result_outbox
                   SET state = ?, lease_expires_at = NULL, next_attempt_at = ?,
                       last_error_json = ?, revision = ?, updated_at = ?
                   WHERE result_id = ? AND state = 'delivering' AND revision = ?""",
                (
                    state,
                    timestamp,
                    encode_json(error.to_dict()),
                    revision,
                    timestamp,
                    row["result_id"],
                    row["revision"],
                ),
            )
            self._cas(cursor, "result outbox expiry")
            changed.append(row["result_id"])
        return changed

    def reap_outbox(self) -> list[dict[str, Any]]:
        with self._transaction() as (connection, timestamp):
            ids = self._reap_outbox_in_transaction(connection, timestamp)
            return [
                self._outbox_record(
                    connection.execute(
                        "SELECT * FROM kernel_result_outbox WHERE result_id = ?", (result_id,)
                    ).fetchone()
                )
                for result_id in ids
            ]

    def claim_outbox(
        self,
        owner: str,
        *,
        lease_seconds: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        if type(owner) is not str or not owner.strip():
            raise ValueError("owner must be a non-empty string")
        duration = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        # An empty poll must stay read-only.  Advancing the durable clock and
        # committing an otherwise empty transaction on every immediate bridge
        # pump creates needless fsync pressure.  A concurrent insert after
        # this observation is safely picked up by the next bounded pump.
        with self._lock:
            active = self._connection.execute(
                """SELECT 1 FROM kernel_result_outbox
                   WHERE state IN ('pending', 'delivering') LIMIT 1"""
            ).fetchone()
        if active is None:
            return None
        with self._transaction() as (connection, timestamp):
            self._reap_outbox_in_transaction(connection, timestamp)
            exhausted = connection.execute(
                """SELECT * FROM kernel_result_outbox
                   WHERE state = 'pending' AND attempts >= max_attempts
                   ORDER BY created_at, result_id"""
            ).fetchall()
            for row in exhausted:
                cursor = connection.execute(
                    """UPDATE kernel_result_outbox SET state = 'dead', revision = ?, updated_at = ?
                       WHERE result_id = ? AND state = 'pending' AND revision = ?""",
                    (row["revision"] + 1, timestamp, row["result_id"], row["revision"]),
                )
                self._cas(cursor, "result outbox exhaustion")
            row = connection.execute(
                """SELECT * FROM kernel_result_outbox
                   WHERE state = 'pending' AND attempts < max_attempts AND next_attempt_at <= ?
                   ORDER BY created_at, result_id LIMIT 1""",
                (timestamp,),
            ).fetchone()
            if row is None:
                return None
            lease_id = uuid.uuid4().hex
            fence = row["fence"] + 1
            attempts = row["attempts"] + 1
            revision = row["revision"] + 1
            expires_at = self._checked_add(timestamp, duration, "lease_seconds")
            cursor = connection.execute(
                """UPDATE kernel_result_outbox
                   SET state = 'delivering', lease_id = ?, lease_owner = ?, fence = ?,
                       attempts = ?, lease_expires_at = ?, revision = ?, updated_at = ?
                   WHERE result_id = ? AND state = 'pending' AND revision = ?""",
                (
                    lease_id,
                    owner,
                    fence,
                    attempts,
                    expires_at,
                    revision,
                    timestamp,
                    row["result_id"],
                    row["revision"],
                ),
            )
            self._cas(cursor, "result outbox claim")
            claimed = connection.execute(
                "SELECT * FROM kernel_result_outbox WHERE result_id = ?", (row["result_id"],)
            ).fetchone()
            return self._outbox_record(claimed)

    @staticmethod
    def _delivery_identity(
        result_or_delivery: str | dict[str, Any],
        lease_id: Optional[str],
        fence: Optional[int],
    ) -> tuple[str, str, int]:
        if type(result_or_delivery) is dict:
            result_id = result_or_delivery.get("result_id")
            lease_id = result_or_delivery.get("lease_id")
            fence = result_or_delivery.get("fence")
        else:
            result_id = result_or_delivery
        if type(result_id) is not str or not result_id:
            raise ValueError("result_id must be a non-empty string")
        if type(lease_id) is not str or not lease_id:
            raise ValueError("lease_id must be a non-empty string")
        if type(fence) is not int or fence < 1:
            raise ValueError("fence must be a positive integer")
        return result_id, lease_id, fence

    def ack_outbox(
        self,
        result_or_delivery: str | dict[str, Any],
        lease_id: Optional[str] = None,
        fence: Optional[int] = None,
    ) -> dict[str, Any]:
        result_id, lease_id, fence = self._delivery_identity(
            result_or_delivery, lease_id, fence
        )
        with self._transaction() as (connection, timestamp):
            row = connection.execute(
                "SELECT * FROM kernel_result_outbox WHERE result_id = ?", (result_id,)
            ).fetchone()
            if row is None:
                raise KeyError(result_id)
            if row["state"] == "delivered" and row["lease_id"] == lease_id and row["fence"] == fence:
                return self._outbox_record(row)
            if (
                row["state"] != "delivering"
                or row["lease_id"] != lease_id
                or row["fence"] != fence
                or row["lease_expires_at"] <= timestamp
            ):
                raise StaleFenceError("result outbox delivery is stale")
            cursor = connection.execute(
                """UPDATE kernel_result_outbox
                   SET state = 'delivered', lease_expires_at = NULL, revision = ?, updated_at = ?
                   WHERE result_id = ? AND state = 'delivering' AND revision = ?""",
                (row["revision"] + 1, timestamp, result_id, row["revision"]),
            )
            self._cas(cursor, "result outbox acknowledgement")
            return self._outbox_record(
                connection.execute(
                    "SELECT * FROM kernel_result_outbox WHERE result_id = ?", (result_id,)
                ).fetchone()
            )

    def renew_outbox(
        self,
        result_or_delivery: str | dict[str, Any],
        lease_id: Optional[str] = None,
        fence: Optional[int] = None,
        *,
        lease_seconds: Optional[float] = None,
    ) -> dict[str, Any]:
        result_id, lease_id, fence = self._delivery_identity(
            result_or_delivery, lease_id, fence
        )
        duration = (
            self.default_lease_seconds
            if lease_seconds is None
            else self._positive_duration(lease_seconds, "lease_seconds")
        )
        with self._transaction() as (connection, timestamp):
            row = connection.execute(
                "SELECT * FROM kernel_result_outbox WHERE result_id = ?", (result_id,)
            ).fetchone()
            if row is None:
                raise KeyError(result_id)
            if (
                row["state"] != "delivering"
                or row["lease_id"] != lease_id
                or row["fence"] != fence
                or row["lease_expires_at"] <= timestamp
            ):
                raise StaleFenceError("result outbox delivery is stale")
            expires_at = self._checked_add(timestamp, duration, "lease_seconds")
            cursor = connection.execute(
                """UPDATE kernel_result_outbox
                   SET lease_expires_at = ?, revision = ?, updated_at = ?
                   WHERE result_id = ? AND state = 'delivering' AND revision = ?""",
                (
                    expires_at,
                    row["revision"] + 1,
                    timestamp,
                    result_id,
                    row["revision"],
                ),
            )
            self._cas(cursor, "result outbox renewal")
            return self._outbox_record(
                connection.execute(
                    "SELECT * FROM kernel_result_outbox WHERE result_id = ?", (result_id,)
                ).fetchone()
            )

    def release_outbox(
        self,
        result_or_delivery: str | dict[str, Any],
        error: ExecutionError,
        lease_id: Optional[str] = None,
        fence: Optional[int] = None,
        *,
        delay_seconds: float = 0.0,
    ) -> dict[str, Any]:
        if type(error) is not ExecutionError:
            raise TypeError("release_outbox requires ExecutionError")
        delay = self._nonnegative_duration(delay_seconds, "delay_seconds")
        result_id, lease_id, fence = self._delivery_identity(
            result_or_delivery, lease_id, fence
        )
        encoded_error = encode_json(error.to_dict())
        with self._transaction() as (connection, timestamp):
            row = connection.execute(
                "SELECT * FROM kernel_result_outbox WHERE result_id = ?", (result_id,)
            ).fetchone()
            if row is None:
                raise KeyError(result_id)
            if (
                row["state"] in {"pending", "dead"}
                and row["lease_id"] == lease_id
                and row["fence"] == fence
            ):
                if row["last_error_json"] == encoded_error:
                    return self._outbox_record(row)
                raise StaleFenceError("result outbox release is stale or conflicts")
            if (
                row["state"] != "delivering"
                or row["lease_id"] != lease_id
                or row["fence"] != fence
                or row["lease_expires_at"] <= timestamp
            ):
                raise StaleFenceError("result outbox delivery is stale")
            state = (
                "pending"
                if error.retryable and row["attempts"] < row["max_attempts"]
                else "dead"
            )
            cursor = connection.execute(
                """UPDATE kernel_result_outbox
                   SET state = ?, lease_expires_at = NULL, next_attempt_at = ?,
                       last_error_json = ?, revision = ?, updated_at = ?
                   WHERE result_id = ? AND state = 'delivering' AND revision = ?""",
                (
                    state,
                    self._checked_add(timestamp, delay, "outbox retry delay"),
                    encoded_error,
                    row["revision"] + 1,
                    timestamp,
                    result_id,
                    row["revision"],
                ),
            )
            self._cas(cursor, "result outbox release")
            return self._outbox_record(
                connection.execute(
                    "SELECT * FROM kernel_result_outbox WHERE result_id = ?", (result_id,)
                ).fetchone()
            )
