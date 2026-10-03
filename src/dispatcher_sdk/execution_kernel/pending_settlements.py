"""Bounded ownership of original outcomes awaiting a durable receipt.

This cache grants no execution authority. Admission is reserved before the
caller claims work, then transferred to an immutable outcome until the caller
confirms that its independent settlement journal persisted that outcome.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import threading
from typing import Any, cast

from .contracts import ExecutionLease, _json_value


SettlementKey = tuple[str, int, int]


class PendingSettlementConflictError(RuntimeError):
    """A retained obligation was replayed with different facts or ownership."""


def _snapshot(value: dict[str, Any], name: str) -> str:
    if type(value) is not dict:
        raise TypeError(f"{name} must be a strict JSON object")
    copied = deepcopy(value)
    _json_value(copied, name)
    return json.dumps(copied, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, slots=True)
class PendingSettlement:
    """An immutable record whose JSON accessors return independent copies."""

    key: SettlementKey
    lease: ExecutionLease
    _payload_json: str
    _evidence_json: str

    @property
    def payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._payload_json))

    @property
    def evidence(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._evidence_json))

    @property
    def identity(self) -> dict[str, Any]:
        return {"execution_id": self.key[0], "attempt": self.key[1], "fence": self.key[2]}


class SettlementAdmission:
    """Opaque reservation; only its owning PendingSettlements may release it."""

    __slots__ = ("_owner", "_entry", "_released")

    def __init__(self, owner: PendingSettlements) -> None:
        self._owner = owner
        self._entry: PendingSettlement | None = None
        self._released = False


class PendingSettlements:
    """Reserve a fixed number of unresolved obligations without waiting.

    A foreground finish releases unused admission. Once retain transfers that
    admission, only persisted releases it. Either operation may race or replay
    without releasing capacity twice. Released tokens need no retained ledger.
    """

    def __init__(self, capacity: int = 64) -> None:
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self._capacity = capacity
        self._lock = threading.Lock()
        self._in_use = 0
        self._entries: dict[SettlementKey, SettlementAdmission] = {}

    @property
    def capacity(self) -> int:
        return self._capacity

    def acquire(self) -> SettlementAdmission | None:
        with self._lock:
            if self._in_use >= self._capacity:
                return None
            self._in_use += 1
            return SettlementAdmission(self)

    def _owned(self, token: SettlementAdmission) -> None:
        if type(token) is not SettlementAdmission or token._owner is not self:
            raise ValueError("settlement admission belongs to another owner")

    def retain(self, token: SettlementAdmission, lease: ExecutionLease,
               payload: dict[str, Any], evidence: dict[str, Any]) -> SettlementKey:
        self._owned(token)
        if type(lease) is not ExecutionLease:
            raise TypeError("lease must be an ExecutionLease")
        key = (lease.execution_id, lease.attempt, lease.fence)
        # Copy/validate outside the critical section. Stored strings and the
        # frozen lease cannot be changed by the caller or returned readers.
        entry = PendingSettlement(key, lease, _snapshot(payload, "payload"),
                                  _snapshot(evidence, "evidence"))
        with self._lock:
            if token._entry is not None:
                if token._entry != entry:
                    raise PendingSettlementConflictError("retained settlement facts differ")
                # A receipt may already have released the token. Exact replay
                # must not resurrect an obligation or acquire capacity again.
                return key
            if token._released:
                raise ValueError("finished settlement admission cannot retain an outcome")
            if key in self._entries:
                raise PendingSettlementConflictError("settlement identity has another admission owner")
            token._entry = entry
            self._entries[key] = token
            return key

    def entries(self, limit: int = 50) -> tuple[PendingSettlement, ...]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._lock:
            # Dict insertion order preserves admission transfer order. Each
            # record is immutable; JSON accessors copy outside this lock.
            return tuple(token._entry for token in list(self._entries.values())[:limit]
                         if token._entry is not None)

    def persisted(self, key: SettlementKey, *, expected: PendingSettlement | None = None) -> bool:
        with self._lock:
            token = self._entries.get(key)
            if token is None:
                return False
            if expected is not None and token._entry != expected:
                return False
            del self._entries[key]
            token._released = True
            self._in_use -= 1
            return True

    def finish(self, token: SettlementAdmission) -> None:
        self._owned(token)
        with self._lock:
            if token._released or token._entry is not None:
                return
            token._released = True
            self._in_use -= 1

    def identities(self) -> tuple[dict[str, Any], ...]:
        return tuple(entry.identity for entry in self.entries(limit=self._capacity))


__all__ = ["PendingSettlements", "PendingSettlement", "SettlementAdmission",
           "SettlementKey", "PendingSettlementConflictError"]
