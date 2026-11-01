"""Durable application-metered reservations, separate from Kernel budgets.

Amounts are non-negative integer minor units chosen by the host. A reservation
must be durable before an external operation starts. Unknown outcomes retain
that reservation and block additional reservations in the same budget scope.
This ledger cannot meter or fence external providers by itself.
"""
from __future__ import annotations

import math
import json
from contextlib import closing
import sqlite3
import time
from pathlib import Path
from typing import Callable

_MAX_RESERVATIONS = 10_000
_MAX_IMPORT_BYTES = 1_048_576


class BudgetError(RuntimeError):
    """A budget operation is invalid or cannot safely proceed."""


def _name(value: str, label: str) -> str:
    if type(value) is not str or not value.strip() or len(value.encode("utf-8")) > 4096:
        raise ValueError(f"{label} must be a bounded nonempty string")
    return value


def _amount(value: int, label: str) -> int:
    if type(value) is not int or not 0 <= value <= (1 << 63) - 1:
        raise ValueError(f"{label} must be a nonnegative SQLite integer")
    return value


class ApplicationBudget:
    """SQLite-backed budget ledger keyed by Run, owner and unit.

    Each public operation is a separate SQLite transaction. Host identity,
    provider idempotency and authentic usage evidence remain host obligations.
    Each scope supports at most 10,000 unarchived reservations; settled
    entries may be archived while preserving exact replay and lifetime usage.
    Deadline enforcement depends on the host clock and provider integration.
    """

    def __init__(self, path: str | Path, *, clock: Callable[[], float] = time.time):
        if str(path) == ":memory:":
            raise ValueError("application budget requires a persistent SQLite file")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.path, self._clock = str(path), clock
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('application_budget_meta','application_budgets','application_reservations','application_budget_imports','application_budget_archive','application_budget_archive_totals')")}
            required = {'application_budget_meta', 'application_budgets', 'application_reservations'}
            if not names:
                db.execute("CREATE TABLE application_budget_meta (version INTEGER NOT NULL)")
                db.execute("INSERT INTO application_budget_meta VALUES(3)")
            else:
                if 'application_budget_meta' not in names:
                    raise BudgetError("incomplete application budget schema")
                version = db.execute("SELECT version FROM application_budget_meta").fetchall()
                expected = required if version == [(1,)] else required | {'application_budget_imports'}
                if version == [(3,)]:
                    expected |= {'application_budget_archive', 'application_budget_archive_totals'}
                if version not in ([(1,)], [(2,)], [(3,)]):
                    raise BudgetError("unsupported application budget schema")
                if names != expected:
                    raise BudgetError("incomplete application budget schema")
                if version in ([(1,)], [(2,)]):
                    db.execute("UPDATE application_budget_meta SET version=3")
            db.execute("""CREATE TABLE IF NOT EXISTS application_budgets (
                run_id TEXT NOT NULL, owner TEXT NOT NULL, unit TEXT NOT NULL,
                allowance INTEGER NOT NULL, deadline REAL NOT NULL, observed_at REAL NOT NULL,
                PRIMARY KEY(run_id,owner,unit))""")
            db.execute("""CREATE TABLE IF NOT EXISTS application_reservations (
                run_id TEXT NOT NULL, owner TEXT NOT NULL, unit TEXT NOT NULL, request_id TEXT NOT NULL,
                amount INTEGER NOT NULL, state TEXT NOT NULL, actual INTEGER,
                PRIMARY KEY(run_id,owner,unit,request_id),
                FOREIGN KEY(run_id,owner,unit) REFERENCES application_budgets(run_id,owner,unit))""")
            db.execute("""CREATE TABLE IF NOT EXISTS application_budget_imports (
                run_id TEXT NOT NULL, owner TEXT NOT NULL, unit TEXT NOT NULL,
                source TEXT NOT NULL, spent INTEGER NOT NULL, manifest TEXT NOT NULL,
                PRIMARY KEY(run_id,owner,unit),
                FOREIGN KEY(run_id,owner,unit) REFERENCES application_budgets(run_id,owner,unit))""")
            db.execute("""CREATE TABLE IF NOT EXISTS application_budget_archive (
                run_id TEXT NOT NULL, owner TEXT NOT NULL, unit TEXT NOT NULL, request_id TEXT NOT NULL,
                amount INTEGER NOT NULL, actual INTEGER NOT NULL,
                PRIMARY KEY(run_id,owner,unit,request_id),
                FOREIGN KEY(run_id,owner,unit) REFERENCES application_budgets(run_id,owner,unit))""")
            db.execute("""CREATE TABLE IF NOT EXISTS application_budget_archive_totals (
                run_id TEXT NOT NULL, owner TEXT NOT NULL, unit TEXT NOT NULL, spent TEXT NOT NULL,
                PRIMARY KEY(run_id,owner,unit),
                FOREIGN KEY(run_id,owner,unit) REFERENCES application_budgets(run_id,owner,unit))""")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def _now(self) -> float:
        value = self._clock()
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise BudgetError("budget clock is unknown")
        return float(value)

    @staticmethod
    def _reservations(db, scope):
        """Read at most the supported history plus one overflow marker."""
        return db.execute("SELECT CASE WHEN typeof(amount)='integer' THEN amount END, "
                          "CASE WHEN typeof(state)='text' AND length(CAST(state AS BLOB))<=16 THEN state END, "
                          "CASE WHEN typeof(actual)='integer' THEN actual END "
                          "FROM application_reservations WHERE run_id=? AND owner=? AND unit=? LIMIT ?",
                          (*scope, _MAX_RESERVATIONS + 1))

    @staticmethod
    def _scope(run_id: str, owner: str, unit: str) -> tuple[str, str, str]:
        return _name(run_id, "run_id"), _name(owner, "owner"), _name(unit, "unit")

    @staticmethod
    def _archived_spent(db, scope):
        row = db.execute("SELECT CASE WHEN typeof(spent)='text' AND length(spent)<=128 THEN spent END FROM application_budget_archive_totals WHERE run_id=? AND owner=? AND unit=?", scope).fetchone()
        if row is None:
            if db.execute("SELECT 1 FROM application_budget_archive WHERE run_id=? AND owner=? AND unit=? LIMIT 1", scope).fetchone():
                raise BudgetError('archived usage is unavailable')
            return 0
        value = row[0]
        if type(value) is not str or not value.isascii() or not value.isdigit() or str(int(value)) != value:
            raise BudgetError('invalid archived usage')
        return int(value)

    def create(self, run_id: str, owner: str, unit: str, *, allowance: int, deadline: float) -> dict:
        scope = self._scope(run_id, owner, unit)
        allowance = _amount(allowance, "allowance")
        if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= 0:
            raise ValueError("deadline must be finite and positive")
        deadline = float(deadline)
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT allowance,deadline FROM application_budgets WHERE run_id=? AND owner=? AND unit=?", scope).fetchone()
            if old is None:
                db.execute("INSERT INTO application_budgets VALUES(?,?,?,?,?,?)", (*scope, allowance, deadline, self._now()))
            elif old != (allowance, deadline):
                raise BudgetError("budget identity already has different terms")
            db.commit()
        return self.inspect(*scope)

    def import_legacy(self, run_id: str, owner: str, unit: str, *, allowance: int,
                      deadline: float, spent: int, source: str, reservations: list[dict]) -> dict:
        """Import host-attested prior consumption and unresolved reservations atomically.

        The host must obtain authoritative settled usage (excluding the listed
        outstanding reservations) and a complete list of those reservations
        under its own writer isolation. ``source`` is
        provenance supplied by the host, not independently verified here. Each
        reservation has request_id, amount, and state (reserved or unknown).
        Repeat exactly the same manifest to recover an interrupted response.
        """
        scope = self._scope(run_id, owner, unit)
        allowance, spent = _amount(allowance, "allowance"), _amount(spent, "spent")
        source = _name(source, "source")
        if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= 0:
            raise ValueError("deadline must be finite and positive")
        if type(reservations) is not list or len(reservations) > _MAX_RESERVATIONS:
            raise ValueError("reservations must be a bounded list")
        items = []
        for item in reservations:
            if type(item) is not dict or set(item) != {"request_id", "amount", "state"}:
                raise ValueError("invalid legacy reservation")
            request = _name(item["request_id"], "request_id")
            amount = _amount(item["amount"], "amount")
            if item["state"] not in ("reserved", "unknown"):
                raise ValueError("invalid legacy reservation state")
            items.append((request, amount, item["state"]))
        items.sort()
        if len({item[0] for item in items}) != len(items):
            raise ValueError("duplicate legacy reservation")
        manifest = json.dumps({"allowance": allowance, "deadline": float(deadline), "spent": spent,
                               "source": source, "reservations": items}, separators=(",", ":"), sort_keys=True)
        if len(manifest.encode("utf-8")) > _MAX_IMPORT_BYTES:
            raise ValueError("legacy budget manifest exceeds the byte limit")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT manifest FROM application_budget_imports WHERE run_id=? AND owner=? AND unit=?", scope).fetchone()
            if old is not None:
                if old[0] != manifest:
                    raise BudgetError("legacy budget import differs")
            else:
                if db.execute("SELECT 1 FROM application_budgets WHERE run_id=? AND owner=? AND unit=?", scope).fetchone():
                    raise BudgetError("budget already exists without this legacy import")
                db.execute("INSERT INTO application_budgets VALUES(?,?,?,?,?,?)", (*scope, allowance, float(deadline), self._now()))
                db.execute("INSERT INTO application_budget_imports VALUES(?,?,?,?,?,?)", (*scope, source, spent, manifest))
                db.executemany("INSERT INTO application_reservations VALUES(?,?,?,?,?,?,NULL)",
                               [(*scope, request, amount, state) for request, amount, state in items])
            db.commit()
        return self.inspect(*scope)

    def reserve(self, run_id: str, owner: str, unit: str, request_id: str, *, amount: int) -> dict:
        scope = self._scope(run_id, owner, unit)
        request_id, amount = _name(request_id, "request_id"), _amount(amount, "amount")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            budget = db.execute("SELECT allowance,deadline,observed_at FROM application_budgets WHERE run_id=? AND owner=? AND unit=?", scope).fetchone()
            if budget is None:
                raise BudgetError("budget is unknown")
            row = db.execute("SELECT amount,state,actual FROM application_reservations WHERE run_id=? AND owner=? AND unit=? AND request_id=?", (*scope, request_id)).fetchone()
            if row is None:
                archived = db.execute("SELECT amount,actual FROM application_budget_archive WHERE run_id=? AND owner=? AND unit=? AND request_id=?", (*scope, request_id)).fetchone()
                if archived is not None:
                    row = (archived[0], 'settled', archived[1])
            if row is not None:
                if row[0] != amount:
                    raise BudgetError("reservation identity already has different amount")
                return self._receipt(scope, request_id, row)
            now = max(self._now(), budget[2])
            db.execute("UPDATE application_budgets SET observed_at=? WHERE run_id=? AND owner=? AND unit=?", (now, *scope))
            # Commit clock advancement even when the deadline has passed, so a
            # backwards clock cannot revive this scope on a later request.
            if now >= budget[1]:
                db.commit()
                raise BudgetError("budget deadline elapsed")
            entries = self._reservations(db, scope)
            imported = db.execute("SELECT spent FROM application_budget_imports WHERE run_id=? AND owner=? AND unit=?", scope).fetchone()
            used = (imported[0] if imported else 0) + self._archived_spent(db, scope)
            count = 0
            for reserved, state, actual in entries:
                count += 1
                if count > _MAX_RESERVATIONS:
                    raise BudgetError("budget reservation history exceeds the limit")
                if type(reserved) is not int or reserved < 0:
                    raise BudgetError("invalid budget reservation amount")
                if state in ("unknown", "reserved"):
                    db.commit()
                    raise BudgetError("budget usage is unknown or reservation pending")
                if state != "settled" or type(actual) is not int or actual < 0:
                    raise BudgetError("invalid budget reservation state")
                used += actual if state == "settled" else reserved
            if count >= _MAX_RESERVATIONS:
                db.commit()
                raise BudgetError("budget reservation history is full")
            if used + amount > budget[0]:
                db.commit()
                raise BudgetError("budget allowance exhausted")
            now = max(self._now(), now)
            db.execute("UPDATE application_budgets SET observed_at=? WHERE run_id=? AND owner=? AND unit=?", (now, *scope))
            if now >= budget[1]:
                db.commit()
                raise BudgetError("budget deadline elapsed")
            db.execute("INSERT INTO application_reservations VALUES(?,?,?,?,?,'reserved',NULL)", (*scope, request_id, amount))
            now = max(self._now(), now)
            db.execute("UPDATE application_budgets SET observed_at=? WHERE run_id=? AND owner=? AND unit=?", (now, *scope))
            if now >= budget[1]:
                db.execute("DELETE FROM application_reservations WHERE run_id=? AND owner=? AND unit=? AND request_id=?", (*scope, request_id))
                db.commit()
                raise BudgetError("budget deadline elapsed")
            db.commit()
            receipt = self._receipt(scope, request_id, (amount, "reserved", None))
            receipt["spend_authorized"] = True
            return receipt

    @staticmethod
    def _receipt(scope, request_id, row):
        return {"run_id": scope[0], "owner": scope[1], "unit": scope[2], "request_id": request_id,
                "reserved": row[0], "state": row[1], "actual": row[2], "spend_authorized": False}

    def settle(self, run_id: str, owner: str, unit: str, request_id: str, *, actual: int | None) -> dict:
        """Record exact usage, or retain an unknown outcome with ``actual=None``."""
        return self._settle(run_id, owner, unit, request_id, actual=actual, reconcile=False)

    def reconcile(self, run_id: str, owner: str, unit: str, request_id: str, *, actual: int) -> dict:
        """Resolve an unknown outcome using host-provided authoritative usage."""
        if actual is None:
            raise ValueError("reconciliation requires an actual amount")
        return self._settle(run_id, owner, unit, request_id, actual=actual, reconcile=True)

    def _settle(self, run_id, owner, unit, request_id, *, actual, reconcile):
        scope, request_id = self._scope(run_id, owner, unit), _name(request_id, "request_id")
        if actual is not None:
            actual = _amount(actual, "actual")
        target = "unknown" if actual is None else "settled"
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT amount,state,actual FROM application_reservations WHERE run_id=? AND owner=? AND unit=? AND request_id=?", (*scope, request_id)).fetchone()
            if row is None:
                archived = db.execute("SELECT amount,actual FROM application_budget_archive WHERE run_id=? AND owner=? AND unit=? AND request_id=?", (*scope, request_id)).fetchone()
                if archived is not None:
                    row = (archived[0], 'settled', archived[1])
            if row is None:
                raise BudgetError("reservation is unknown")
            if row[1] == target and row[2] == actual:
                return self._receipt(scope, request_id, row)
            if row[1] == "settled" or (row[1] == "unknown" and not reconcile) or (reconcile and row[1] != "unknown"):
                raise BudgetError("reservation outcome conflicts with existing state")
            db.execute("UPDATE application_reservations SET state=?,actual=? WHERE run_id=? AND owner=? AND unit=? AND request_id=?", (target, actual, *scope, request_id))
            db.commit()
            return self._receipt(scope, request_id, (row[0], target, actual))

    def inspect(self, run_id: str, owner: str, unit: str) -> dict:
        scope = self._scope(run_id, owner, unit)
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            budget = db.execute("SELECT allowance,deadline FROM application_budgets WHERE run_id=? AND owner=? AND unit=?", scope).fetchone()
            if budget is None:
                raise BudgetError("budget is unknown")
            rows = self._reservations(db, scope)
            imported = db.execute("SELECT spent,source FROM application_budget_imports WHERE run_id=? AND owner=? AND unit=?", scope).fetchone()
            reserved = unknown = pending = 0
            spent = (imported[0] if imported else 0) + self._archived_spent(db, scope)
            for count, (amount, state, actual) in enumerate(rows, 1):
                if count > _MAX_RESERVATIONS:
                    raise BudgetError("budget reservation history exceeds the limit")
                if type(amount) is not int or amount < 0:
                    raise BudgetError("invalid budget reservation amount")
                if state == "settled":
                    if type(actual) is not int or actual < 0:
                        raise BudgetError("invalid budget reservation state")
                    spent += actual
                else:
                    if state not in ("reserved", "unknown") or actual is not None:
                        raise BudgetError("invalid budget reservation state")
                    reserved += amount
                    unknown += state == "unknown"
                    pending += 1
            return {"run_id": scope[0], "owner": scope[1], "unit": scope[2],
                    "allowance": budget[0], "deadline": budget[1], "spent": spent,
                    "reserved": reserved, "unknown_count": unknown, "admission_blocked": bool(pending),
                    "legacy_source": imported[1] if imported else None,
                    "available": None if unknown else max(0, budget[0] - spent - reserved)}

    def archive_settled(self, run_id: str, owner: str, unit: str, *, limit: int = 100) -> int:
        """Atomically move up to 500 settled requests while retaining exact replay.

        Archive records are never deleted and disk use grows with request count.
        Pending/unknown reservations are never moved. Host storage integrity and
        writer isolation are required for the accumulated total to remain valid.
        """
        scope = self._scope(run_id, owner, unit)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError('archive limit must be between 1 and 500')
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM application_budgets WHERE run_id=? AND owner=? AND unit=?', scope).fetchone() is None:
                raise BudgetError('budget is unknown')
            total = self._archived_spent(db, scope)
            rows = db.execute("SELECT CASE WHEN typeof(request_id)='text' AND length(CAST(request_id AS BLOB))<=4096 THEN request_id END,amount,actual FROM application_reservations WHERE run_id=? AND owner=? AND unit=? AND state='settled' ORDER BY request_id LIMIT ?", (*scope, limit)).fetchall()
            for request_id, amount, actual in rows:
                _name(request_id, 'request_id')
                if type(amount) is not int or amount < 0 or type(actual) is not int or actual < 0:
                    raise BudgetError('invalid settled reservation')
                total += actual
            if len(str(total)) > 128:
                raise BudgetError('archived usage exceeds limit')
            for request_id, amount, actual in rows:
                db.execute('INSERT INTO application_budget_archive VALUES(?,?,?,?,?,?)', (*scope, request_id, amount, actual))
                db.execute('DELETE FROM application_reservations WHERE run_id=? AND owner=? AND unit=? AND request_id=? AND state=\'settled\'', (*scope, request_id))
            if rows:
                db.execute('INSERT INTO application_budget_archive_totals VALUES(?,?,?,?) ON CONFLICT(run_id,owner,unit) DO UPDATE SET spent=excluded.spent', (*scope, str(total)))
            db.commit()
            return len(rows)
