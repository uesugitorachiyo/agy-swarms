"""Single-attempt node dispatch helpers for the conductor."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .budget import Dims
from .conductor_adapters import adapter_crash_envelope
from .conductor_commands import run_command_node
from .conductor_review import run_review_node
from .model_routing import route_model_tier
from .reducers import run_reducer
from .types import ErrorClass, Epoch, NodeSpec, ResultEnvelope, TaskGraph


@dataclass(frozen=True)
class RunNodeAttemptDeps:
    """Conductor-owned dependencies needed to run one node attempt."""

    adapter: Any
    fallback_adapter: Any | None
    graph: TaskGraph
    ledger: Any
    epoch: Epoch
    command_runner: Callable[[list[str]], Any]
    reducer_registry: Mapping[str, Any]
    results: Mapping[str, ResultEnvelope]
    reviewer: str
    closer: str
    review_telemetry_path: str | None
    add_blocker: Callable[[str, str, str], None]
    record_event: Callable[[dict[str, Any]], None]


def run_node_attempt(
    node: NodeSpec,
    runtime: Any,
    *,
    reservation_id: Any,
    deps: RunNodeAttemptDeps,
) -> ResultEnvelope:
    """Run one role-specific node attempt and return its result envelope."""
    if node.role == "reducer" and node.reducer is not None:
        children = [
            {"node_id": dep_id, "artifact": deps.results[dep_id].artifact}
            for dep_id in node.dependencies
            if dep_id in deps.results and deps.results[dep_id].status == "succeeded"
        ]
        merged = run_reducer(node.reducer, children, registry=deps.reducer_registry)
        return ResultEnvelope(
            node_id=node.id,
            idempotency_key=node.idempotency_key,
            status="succeeded",
            error_class=ErrorClass.NONE,
            artifact=merged.artifact,
            concerns=merged.concerns,
            token_usage={
                "input": 0,
                "thinking": 0,
                "output": 0,
                "cached": 0,
                "accounting": "exact",
            },
        )
    if node.role in ("test", "verify"):
        return run_command_node(node, deps.command_runner(node.command or []))

    active_adapter = _active_adapter_for_attempt(node, runtime, deps)

    if node.role in ("reviewer", "closer"):
        return run_review_node(
            node,
            active_adapter=active_adapter,
            attempt=runtime.attempt,
            reservation_id=reservation_id,
            adapter_name=deps.reviewer if node.role == "reviewer" else deps.closer,
            telemetry_path=deps.review_telemetry_path,
        )

    try:
        return active_adapter.run(node, attempt=runtime.attempt, reservation_id=reservation_id)
    except Exception as exc:
        return adapter_crash_envelope(node, exc)


def _active_adapter_for_attempt(node: NodeSpec, runtime: Any, deps: RunNodeAttemptDeps) -> Any:
    active_adapter = deps.adapter
    if node.role in ("reducer", "test", "verify"):
        return active_adapter

    entry = deps.ledger.entries.get((deps.epoch.epoch_seq, node.id))
    reserved_dims = entry.reserved if entry is not None else Dims()
    remaining_budget = deps.ledger.available + reserved_dims
    high_value = getattr(node, "high_value", False) or getattr(deps.graph, "high_value", False)
    decision = route_model_tier(
        node,
        failed_attempts=runtime.attempt,
        high_value=high_value,
        remaining_budget=remaining_budget,
    )
    if decision.escalated and deps.fallback_adapter is not None:
        if deps.fallback_adapter.covers(node.required_capabilities):
            active_adapter = deps.fallback_adapter
            deps.record_event(
                {
                    "type": "model_switch",
                    "node_id": node.id,
                    "from": getattr(deps.adapter, "name", "primary"),
                    "to": getattr(deps.fallback_adapter, "name", "fallback"),
                    "error_class": runtime.error_class.value
                    if hasattr(runtime, "error_class")
                    else "none",
                }
            )
        else:
            deps.add_blocker(node.id, "fallback misses required capabilities", "fallback_uncovered")
    return active_adapter


__all__ = ["RunNodeAttemptDeps", "run_node_attempt"]
