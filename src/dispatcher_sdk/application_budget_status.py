"""Bounded observations of a durable application budget scope.

An observation is never authority to spend. The host must reserve and enforce
provider-side idempotency and writer isolation separately.
"""
from __future__ import annotations

from contextlib import closing
import math
import sqlite3

from . import application_budget as _budget


def observe_budget(ledger: _budget.ApplicationBudget, run_id: str, owner: str,
                   unit: str, *, amount: int) -> dict:
    """Observe scope admission and advance its durable wall-clock watermark.

    A concurrent reservation can invalidate an available observation immediately;
    only ``reserve`` can grant a new spending receipt. Storage, clock, missing
    scope or malformed ledger facts yield ``unknown`` and never authorize spend.
    """
    if not isinstance(ledger, _budget.ApplicationBudget):
        raise TypeError('ledger must be ApplicationBudget')
    scope = ledger._scope(run_id, owner, unit)
    amount = _budget._amount(amount, 'amount')
    base = {'run_id': scope[0], 'owner': scope[1], 'unit': scope[2],
            'requested': amount, 'spend_authorized': False}
    try:
        with closing(ledger._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT allowance,deadline,observed_at FROM application_budgets '
                             'WHERE run_id=? AND owner=? AND unit=?', scope).fetchone()
            if row is None:
                return {**base, 'status': 'unknown', 'reason': 'scope_unavailable'}
            allowance, deadline, observed = row
            if (type(allowance) is not int or allowance < 0 or
                type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= 0 or
                type(observed) not in (int, float) or not math.isfinite(observed) or observed < 0):
                raise _budget.BudgetError('invalid scope facts')
            try:
                now = max(ledger._now(), observed)
            except Exception:
                raise _budget.BudgetError('budget clock is unknown') from None
            db.execute('UPDATE application_budgets SET observed_at=? WHERE run_id=? AND owner=? AND unit=?',
                       (now, *scope))
            # Keep a denied or malformed observation from rolling back a
            # deadline-crossing clock sample. The decision below takes a new
            # locked snapshot and observes any intervening budget operation.
            db.commit()
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT allowance,deadline,observed_at FROM application_budgets '
                                 'WHERE run_id=? AND owner=? AND unit=?', scope).fetchone()
            if (current is None or current[:2] != (allowance, deadline) or
                    type(current[2]) not in (int, float) or not math.isfinite(current[2]) or current[2] < now):
                raise _budget.BudgetError('scope changed during observation')
            now = current[2]
            imported = db.execute('SELECT spent FROM application_budget_imports WHERE run_id=? AND owner=? AND unit=?', scope).fetchone()
            spent = (imported[0] if imported else 0) + ledger._archived_spent(db, scope)
            if type(spent) is not int or spent < 0:
                raise _budget.BudgetError('invalid imported usage')
            pending = unknown = reserved = count = 0
            for amount_reserved, state, actual in ledger._reservations(db, scope):
                count += 1
                if count > _budget._MAX_RESERVATIONS:
                    raise _budget.BudgetError('reservation history exceeds limit')
                if type(amount_reserved) is not int or amount_reserved < 0:
                    raise _budget.BudgetError('invalid reservation')
                if state == 'settled' and type(actual) is int and actual >= 0:
                    spent += actual
                elif state in ('reserved', 'unknown') and actual is None:
                    reserved += amount_reserved
                    pending += 1
                    unknown += int(state == 'unknown')
                else:
                    raise _budget.BudgetError('invalid reservation state')
            remaining = None if unknown else max(0, allowance - spent - reserved)
            expired = now >= deadline
            capacity_exhausted = count >= _budget._MAX_RESERVATIONS
            if expired:
                status = 'expired'
            elif unknown:
                status = 'unknown'
            elif pending:
                status = 'pending'
            elif capacity_exhausted:
                status = 'capacity_exhausted'
            elif spent + amount > allowance:
                status = 'exhausted'
            else:
                status = 'available'
            db.commit()
            return {**base, 'status': status, 'deadline': deadline, 'observed_at': now,
                    'allowance': allowance, 'spent': spent, 'reserved': reserved,
                    'unknown_count': unknown, 'pending_count': pending,
                    'available': remaining, 'expired': expired,
                    'capacity_exhausted': capacity_exhausted}
    except (_budget.BudgetError, sqlite3.Error, OSError):
        return {**base, 'status': 'unknown', 'reason': 'facts_unavailable'}
