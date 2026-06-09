"""Budget helper functions used by the conductor."""

from __future__ import annotations

from typing import Any

from .budget import Dims
from .types import ResultEnvelope


def dims_from_consumed(consumed: dict[str, Any]) -> Dims:
    """Convert a consumed budget mapping into typed dimensions."""
    return Dims(tokens=int(consumed.get("tokens", 0)), usd=float(consumed.get("usd", 0.0)))


def billable_tokens(token_usage: dict[str, Any]) -> int:
    """Return billable output tokens, counting thinking as output."""
    return int(token_usage.get("output", 0)) + int(token_usage.get("thinking", 0))


def add_consumed(consumed: dict[str, Any], actual: Dims) -> dict[str, Any]:
    """Add actual dimensions onto a consumed budget mapping."""
    return {
        "tokens": int(consumed.get("tokens", 0)) + actual.tokens,
        "usd": float(consumed.get("usd", 0.0)) + actual.usd,
    }


def actual_from_envelope(envelope: ResultEnvelope) -> Dims:
    """Convert a result envelope's usage fields into actual billable dimensions."""
    return Dims(tokens=billable_tokens(envelope.token_usage), usd=float(envelope.cost_usd))


def commit_actual_usage(
    *,
    ledger: Any,
    epoch_seq: int,
    node_id: str,
    runtime: Any,
    actual: Dims,
    accounting: str,
) -> Dims:
    """Commit actual usage to the ledger and accumulate it on runtime state."""
    ledger.commit(epoch_seq, node_id, actual, accounting=accounting)
    runtime.budget_consumed = add_consumed(runtime.budget_consumed, actual)
    return actual
