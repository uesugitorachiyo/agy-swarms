"""Reservation and accounting helpers for conductor node attempts."""

from __future__ import annotations

from typing import Any

from .budget import Dims
from .conductor_budget import actual_from_envelope, commit_actual_usage, dims_from_consumed
from .model_routing import route_model_tier
from .types import Epoch, NodeSpec, ResultEnvelope, TaskGraph


def reserve_node_attempt(
    *,
    ledger: Any,
    epoch: Epoch,
    node: NodeSpec,
    runtime: Any,
    adapter: Any,
    fallback_adapter: Any | None,
    graph: TaskGraph,
) -> Any:
    """Reserve budget for a node attempt using the adapter accounting that may run it."""
    accounting = adapter.accounting
    if fallback_adapter is not None and node.role not in ("reducer", "test", "verify"):
        entry = ledger.entries.get((epoch.epoch_seq, node.id))
        reserved_dims = entry.reserved if entry is not None else Dims()
        remaining_budget = ledger.available + reserved_dims
        high_value = getattr(node, "high_value", False) or getattr(graph, "high_value", False)
        decision = route_model_tier(
            node,
            failed_attempts=runtime.attempt + 1,
            high_value=high_value,
            remaining_budget=remaining_budget,
        )
        if decision.escalated and fallback_adapter.covers(node.required_capabilities):
            accounting = fallback_adapter.accounting

    return ledger.reserve(
        epoch.epoch_seq,
        node.id,
        node,
        epoch_id=epoch.epoch_id,
        budget_consumed=dims_from_consumed(runtime.budget_consumed),
        accounting=accounting,
    )


def commit_envelope_usage(
    *,
    ledger: Any,
    epoch: Epoch,
    node: NodeSpec,
    runtime: Any,
    envelope: ResultEnvelope,
    adapter: Any,
    fallback_adapter: Any | None,
) -> Dims:
    """Commit an attempt envelope and update the runtime's cumulative consumed budget."""
    accounting = adapter.accounting
    fallback_name = getattr(fallback_adapter, "name", None)
    if fallback_adapter is not None and envelope.adapter == fallback_name:
        accounting = fallback_adapter.accounting

    return commit_actual_usage(
        ledger=ledger,
        epoch_seq=epoch.epoch_seq,
        node_id=node.id,
        runtime=runtime,
        actual=actual_from_envelope(envelope),
        accounting=accounting,
    )


__all__ = ["commit_envelope_usage", "reserve_node_attempt"]
