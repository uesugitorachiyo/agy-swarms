"""Fallback selection helpers for the conductor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .budget import Dims
from .conductor_budget import billable_tokens
from .types import ErrorClass, NodeSpec, ResultEnvelope


@dataclass(frozen=True)
class FallbackRunResult:
    """Result of one fallback dispatch attempt."""

    envelope: ResultEnvelope
    actual: Dims


def next_review_fallback_adapter(current_adapter: str) -> str | None:
    """Return the next reviewer/closer fallback adapter, if one is available."""
    if current_adapter == "agy":
        return "codex"
    if current_adapter == "codex":
        return "off"
    return None


def model_switch_event(
    *,
    node_id: str,
    from_adapter: str,
    to_adapter: str,
    error_class: ErrorClass,
) -> dict[str, str]:
    """Build a model-switch event payload."""
    return {
        "type": "model_switch",
        "node_id": node_id,
        "from": from_adapter,
        "to": to_adapter,
        "error_class": error_class.value,
    }


def execute_fallback_run(
    *,
    node: NodeSpec,
    runtime: Any,
    admission: Any,
    run: Callable[[NodeSpec, Any, str | None], ResultEnvelope],
    stamp: Callable[[ResultEnvelope, NodeSpec, Any], None],
) -> FallbackRunResult:
    """Run and stamp one fallback attempt, returning its actual budget dimensions."""
    runtime.attempt += 1
    runtime.reservation_id = admission.reservation_id
    envelope = run(node, runtime, admission.reservation_id)
    stamp(envelope, node, runtime)
    actual = Dims(tokens=billable_tokens(envelope.token_usage), usd=float(envelope.cost_usd))
    runtime.error_class = envelope.error_class
    return FallbackRunResult(envelope=envelope, actual=actual)


__all__ = [
    "FallbackRunResult",
    "execute_fallback_run",
    "model_switch_event",
    "next_review_fallback_adapter",
]
