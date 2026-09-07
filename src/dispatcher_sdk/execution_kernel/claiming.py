"""Pure SQL predicate shared by claiming and read-only diagnostics."""
from __future__ import annotations


def claim_predicate(timestamp: float, revisions: tuple[str, ...] | None,
                    *, alias: str = '') -> tuple[str, tuple]:
    # Aliases are SDK-owned SQL identifiers, never user input.
    if alias not in ('', 'k'):
        raise ValueError('unsupported claim predicate alias')
    prefix = alias + '.' if alias else ''
    sql = f"{prefix}state = 'queued' AND {prefix}next_attempt_at <= ?"
    parameters: tuple = (timestamp,)
    if revisions is not None:
        sql += f" AND {prefix}registry_revision IN (" + ','.join('?' for _ in revisions) + ')'
        parameters += revisions
    return sql, parameters
