"""Adapter dispatch helpers for the conductor."""

from __future__ import annotations

from .types import ErrorClass, NodeSpec, ResultEnvelope

_ZERO_USAGE = {
    "input": 0,
    "thinking": 0,
    "output": 0,
    "cached": 0,
    "accounting": "exact",
}


def adapter_crash_envelope(node: NodeSpec, exc: Exception) -> ResultEnvelope:
    """Convert an adapter exception into a contained failed result envelope."""
    return ResultEnvelope(
        node_id=node.id,
        idempotency_key=node.idempotency_key,
        status="failed",
        error_class=ErrorClass.UNKNOWN,
        artifact={"crash": type(exc).__name__},
        stdout_ref=f"{type(exc).__name__}: {exc}",
        token_usage=dict(_ZERO_USAGE),
    )
