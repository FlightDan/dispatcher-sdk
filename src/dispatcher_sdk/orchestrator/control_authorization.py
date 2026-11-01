"""Host-verified control authority and durable local delegations.

This ledger controls Orchestrator operations only. It does not install or
revoke execution authority in the Kernel or in an external service.
"""
from __future__ import annotations

import math
from .contracts import OrchestrationError, CommandConflict, identifier


class ControlAuthorizer:
    """Verify credentials using a host-owned callable on every request.

    The verifier returns a principal and a list of exact (run_id, action)
    permissions. It owns credential authentication, expiry and revocation of
    its direct permissions. No supplied credential is persisted by the SDK.
    """
    def __init__(self, orchestrator, verifier):
        if not callable(verifier):
            raise TypeError("control verifier must be callable")
        self.orchestrator = orchestrator
        self.verifier = verifier

    def verify(self, credential):
        verified = self.verifier(credential)
        if type(verified) is not dict:
            raise OrchestrationError("control verifier did not authenticate a principal")
        principal = verified.get("principal")
        permissions = verified.get("permissions")
        identifier(principal, "principal")
        if type(permissions) is not list or any(
            type(item) not in (tuple, list) or len(item) != 2 or
            any(type(value) is not str or not value.strip() for value in item)
            for item in permissions
        ):
            raise OrchestrationError("control verifier returned invalid permissions")
        now = float(self.orchestrator.clock())
        if not math.isfinite(now):
            raise OrchestrationError("control authority clock is invalid")
        # Commit this observation separately: a denied decision must not roll
        # back the clock and let a later backwards wall-clock jump revive it.
        with self.orchestrator._transaction() as connection:
            connection.execute(
                "INSERT INTO sdk_control_authority_clock VALUES(1,?) "
                "ON CONFLICT(singleton) DO UPDATE SET observed_at=MAX(observed_at,excluded.observed_at)",
                (now,),
            )
        return principal, frozenset(tuple(item) for item in permissions)

    def check_in_transaction(self, connection, verified, run_id, action, delegation_id=None):
        principal, permissions = verified
        if delegation_id is None:
            if (run_id, action) in permissions:
                return principal
            raise OrchestrationError("control authority is not granted")
        identifier(delegation_id, "delegation_id")
        row = connection.execute(
            "SELECT * FROM sdk_control_delegations WHERE delegation_id=?", (delegation_id,)
        ).fetchone()
        if (row is None or row["run_id"] != run_id or row["action"] != action or
                row["principal"] != principal or row["revoked_at"] is not None or
                row["expires_at"] <= self._observed_time(connection)):
            raise OrchestrationError("control delegation is missing, expired, revoked or out of scope")
        return principal

    @staticmethod
    def _observed_time(connection):
        row = connection.execute("SELECT observed_at FROM sdk_control_authority_clock WHERE singleton=1").fetchone()
        if row is None:
            raise OrchestrationError("control authority clock is unknown")
        return row[0]

    def grant(self, credential, *, delegation_id, run_id, action, principal, expires_at):
        for key, value in (("delegation_id", delegation_id), ("run_id", run_id),
                           ("action", action), ("principal", principal)):
            identifier(value, key)
        if type(expires_at) not in (int, float) or not math.isfinite(expires_at):
            raise OrchestrationError("delegation expiry must be finite")
        verified = self.verify(credential)
        grantor, permissions = verified
        if ((run_id, "delegate:" + action) not in permissions or
                (run_id, action) not in permissions):
            raise OrchestrationError("delegation is not authorized")
        with self.orchestrator._transaction() as connection:
            old = connection.execute("SELECT * FROM sdk_control_delegations WHERE delegation_id=?", (delegation_id,)).fetchone()
            if old is not None:
                if (old["run_id"], old["action"], old["principal"], old["granted_by"], old["expires_at"]) != (
                        run_id, action, principal, grantor, float(expires_at)):
                    raise CommandConflict("delegation identity already has different content")
                return dict(old)
            now = self._observed_time(connection)
            if expires_at <= now:
                raise OrchestrationError("delegation is already expired")
            connection.execute("INSERT INTO sdk_control_delegations VALUES(?,?,?,?,?,?,NULL,NULL,?)",
                               (delegation_id, run_id, action, principal, grantor, float(expires_at), now))
            return dict(connection.execute("SELECT * FROM sdk_control_delegations WHERE delegation_id=?", (delegation_id,)).fetchone())

    def revoke(self, credential, *, delegation_id):
        identifier(delegation_id, "delegation_id")
        principal, permissions = self.verify(credential)
        with self.orchestrator._transaction() as connection:
            row = connection.execute("SELECT * FROM sdk_control_delegations WHERE delegation_id=?", (delegation_id,)).fetchone()
            if row is None:
                raise OrchestrationError("unknown control delegation")
            if principal != row["granted_by"] and (row["run_id"], "revoke:" + row["action"]) not in permissions:
                raise OrchestrationError("delegation revocation is not authorized")
            if row["revoked_at"] is None:
                connection.execute("UPDATE sdk_control_delegations SET revoked_at=?,revoked_by=? WHERE delegation_id=?",
                                   (self._observed_time(connection), principal, delegation_id))
            return dict(connection.execute("SELECT * FROM sdk_control_delegations WHERE delegation_id=?", (delegation_id,)).fetchone())
