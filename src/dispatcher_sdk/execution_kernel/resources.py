"""Native memory policy for an SDK-owned process invocation.

Configured reservations are admission accounting, not measured RSS. Linux's
per-process address-space ceiling is intentionally distinct from a Windows
Job's aggregate committed-memory ceiling.
"""

from __future__ import annotations

import os
import sys
from typing import Any


def memory_capability() -> dict[str, Any]:
    if os.name == "nt":
        return {"supported": True, "memory_basis": "job_commit", "reason": None,
                "scope": "process_tree"}
    if sys.platform.startswith("linux"):
        try:
            import resource
            resource.getrlimit(resource.RLIMIT_AS)
        except (ImportError, AttributeError, OSError, ValueError) as exc:
            return {"supported": False, "memory_basis": "address_space",
                    "reason": f"{type(exc).__name__}: {exc}", "scope": "process"}
        return {"supported": True, "memory_basis": "address_space", "reason": None,
                "scope": "process"}
    return {"supported": False, "memory_basis": None,
            "reason": "native memory enforcement is unavailable", "scope": None}


def apply_process_memory_limit(limit: int | None) -> None:
    """Apply before decoding invocation bytes; never alter the host's limits."""
    if limit is None:
        return
    if type(limit) is not int or not 0 < limit <= sys.maxsize:
        raise ValueError("process_memory_limit_bytes must be a positive integer at most sys.maxsize")
    if not sys.platform.startswith("linux"):
        raise RuntimeError("per-process address-space enforcement is unavailable")
    import resource
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    ceiling = limit if hard == resource.RLIM_INFINITY else min(limit, hard)
    resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
