"""Observe chunks already received by an application's existing stream reader.

These adapters neither install readers nor consume process pipes. Observation
precedes yielding a raw chunk to decoding, line assembly or protocol parsing.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator


def observe_bytes(activity: Any, stream: str, chunk: bytes) -> dict[str, Any]:
    """Best-effort raw byte report; telemetry never changes the reader's result."""
    try:
        receipt = activity.report_bytes(stream, chunk)
        return receipt if isinstance(receipt, dict) else {"state": "degraded", "reason": "invalid_observation_receipt"}
    except Exception as exc:
        return {"state": "degraded", "reason": "byte_observation_failed", "error_type": type(exc).__name__}


def observed_byte_chunks(chunks: Iterable[bytes], activity: Any, *, stream: str = "stdout") -> Iterator[bytes]:
    """Yield each original chunk immediately after its observation.

    Iterating this wrapper explicitly drives the supplied application iterator.
    It does not prefetch, decode, buffer, retry or suppress source read errors.
    Empty observed streams remain distinguishable from unattached metrics.
    """
    try:
        activity.enable_stream(stream)
    except Exception:
        pass
    for chunk in chunks:
        observe_bytes(activity, stream, chunk)
        yield chunk


def decoded_tail(chunk: bytes, *, limit_bytes: int = 64 * 1024) -> str:
    """Decode a bounded diagnostic tail without assuming complete UTF-8."""
    if type(limit_bytes) is not int or limit_bytes < 1:
        raise ValueError("limit_bytes must be a positive integer")
    return bytes(memoryview(chunk).cast("B")[-limit_bytes:]).decode("utf-8", errors="replace")


__all__ = ["observe_bytes", "observed_byte_chunks", "decoded_tail"]
