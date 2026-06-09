"""Reviewer/closer dispatch helpers for the conductor."""

from __future__ import annotations

from typing import Any

from .conductor_adapters import adapter_crash_envelope
from .types import ErrorClass, NodeSpec, ResultEnvelope

_ZERO_USAGE = {
    "input": 0,
    "thinking": 0,
    "output": 0,
    "cached": 0,
    "accounting": "exact",
}


def run_review_node(
    node: NodeSpec,
    *,
    active_adapter: Any,
    attempt: int,
    reservation_id: str | None,
    adapter_name: str,
    telemetry_path: str | None,
) -> ResultEnvelope:
    """Dispatch a reviewer/closer node through its resolved review route."""
    from .hybrid_review import route_review_role

    route = route_review_role(node.role, adapter=adapter_name)
    if route.adapter == "agy":
        try:
            return active_adapter.run(node, attempt=attempt, reservation_id=reservation_id)
        except Exception as exc:
            return adapter_crash_envelope(node, exc)
    if route.adapter == "claude":
        from .adapters.claude import ClaudeAdapter

        try:
            return ClaudeAdapter().run(node, attempt=attempt, reservation_id=reservation_id)
        except Exception as exc:
            return adapter_crash_envelope(node, exc)
    if route.adapter == "codex":
        from .adapters.codex import CodexAdapter

        try:
            return CodexAdapter(telemetry_path=telemetry_path).run(
                node, attempt=attempt, reservation_id=reservation_id
            )
        except Exception as exc:
            return adapter_crash_envelope(node, exc)
    return ResultEnvelope(
        node_id=node.id,
        idempotency_key=node.idempotency_key,
        status="succeeded",
        error_class=ErrorClass.NONE,
        artifact={
            "route": route.to_json(),
            "commands_executed": False,
        },
        token_usage=dict(_ZERO_USAGE),
    )


__all__ = ["run_review_node"]
