"""Host-enforced exclusive control lease for split-store decisions.

The configured verifier is a host trust boundary. It must serialize every
resume, cancellation, budget-policy and revocation writer for the named Run and both stores,
and retain exclusivity through the calling SQLite transaction's commit. A
timestamp or a caller-supplied lease string alone does not provide that lock.
"""
import math

from .contracts import OrchestrationError


def observe_control_clock(orchestrator):
    """Commit a clock observation before entering a lease-dependent transaction.

    Call even for attempts that later fail; the final transaction rechecks the
    lease and clock while the host maintains exclusivity through commit.
    """
    now = float(orchestrator.clock())
    if not math.isfinite(now):
        raise OrchestrationError("host control clock is invalid")
    with orchestrator._transaction() as connection:
        connection.execute("INSERT INTO sdk_control_authority_clock VALUES(1,?) "
                           "ON CONFLICT(singleton) DO UPDATE SET observed_at=MAX(observed_at,excluded.observed_at)", (now,))


def check_control_lease(orchestrator, connection, credential, expected):
    """Check a host credential in the active transaction and fence stale leases.

    The caller must invoke observe_control_clock before opening this transaction.
    """
    verifier = orchestrator.control_lease_verifier
    if not callable(verifier):
        raise OrchestrationError("host exclusive control lease verifier is required")
    try:
        claim = verifier(credential)
        keys = {"operation_id", "run_id", "kernel_store_id", "orchestrator_store_id",
                "orchestrator_incarnation", "lease_id", "lease_fence", "expires_at",
                "held", "scope"}
        if type(claim) is not dict or set(claim) != keys:
            raise ValueError("invalid lease claim")
        for key in ("operation_id", "run_id", "kernel_store_id", "orchestrator_store_id",
                    "orchestrator_incarnation", "lease_id"):
            if type(claim[key]) is not str or not claim[key].strip() or len(claim[key].encode("utf-8")) > 4096:
                raise ValueError("invalid lease identity")
        if (type(claim["lease_fence"]) is not int or not 0 <= claim["lease_fence"] <= (1 << 63) - 1 or
                type(claim["expires_at"]) not in (int, float) or not math.isfinite(claim["expires_at"]) or
                claim["held"] is not True or claim["scope"] != "resume_cancel_revoke_through_commit" or
                any(claim[key] != value for key, value in expected.items())):
            raise ValueError("lease scope or identity differs")
        now = float(orchestrator.clock())
        if not math.isfinite(now):
            raise ValueError("lease clock is invalid")
        observed = connection.execute("SELECT observed_at FROM sdk_control_authority_clock WHERE singleton=1").fetchone()
        if observed is None:
            raise ValueError("lease clock has not been observed")
        if observed is not None and observed[0] > now:
            now = observed[0]
        connection.execute("INSERT INTO sdk_control_authority_clock VALUES(1,?) "
                           "ON CONFLICT(singleton) DO UPDATE SET observed_at=MAX(observed_at,excluded.observed_at)", (now,))
        if claim["expires_at"] <= now:
            raise ValueError("lease expired")
        prior = connection.execute("SELECT fence,lease_id FROM sdk_control_lease_fences WHERE run_id=?", (claim["run_id"],)).fetchone()
        if prior is not None and (claim["lease_fence"] < prior[0] or
                (claim["lease_fence"] == prior[0] and claim["lease_id"] != prior[1])):
            raise ValueError("lease fence is stale")
        connection.execute("INSERT INTO sdk_control_lease_fences VALUES(?,?,?) ON CONFLICT(run_id) "
                           "DO UPDATE SET fence=excluded.fence,lease_id=excluded.lease_id",
                           (claim["run_id"], claim["lease_fence"], claim["lease_id"]))
        return claim
    except Exception:
        raise OrchestrationError("host exclusive control lease is unavailable, expired or stale") from None
