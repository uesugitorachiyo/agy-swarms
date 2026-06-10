"""Codex batch review dispatch helpers for the conductor."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

from .budget import BudgetLedger, Dims
from .conductor_adapters import adapter_crash_envelope
from .conductor_budget import actual_from_envelope, commit_actual_usage
from .conductor_retry import classify
from .hybrid_review import route_review_role
from .types import Epoch, ErrorClass, NodeSpec, NodeStatus, ResultEnvelope, compute_idempotency_key


@dataclass(frozen=True)
class CodexBatchDispatchResult:
    """Outcome of a Codex review batch dispatch attempt."""

    dispatched: bool
    budget_stopped: bool = False


def can_codex_review_batch(
    *,
    batch: list[str],
    checkpoint: Any | None,
    nodes_by_id: Mapping[str, NodeSpec],
    reviewer: str,
    closer: str,
) -> bool:
    """Return whether a ready batch can use one Codex batch review invocation."""
    if checkpoint is not None or len(batch) < 2:
        return False

    for node_id in batch:
        node = nodes_by_id[node_id]
        if node.role not in ("reviewer", "closer"):
            return False
        adapter_name = reviewer if node.role == "reviewer" else closer
        if route_review_role(node.role, adapter=adapter_name).adapter != "codex":
            return False
    return True


def dispatch_codex_review_batch(
    *,
    batch: list[str],
    checkpoint: Any | None,
    nodes_by_id: Mapping[str, NodeSpec],
    runtime_by_id: MutableMapping[str, Any],
    tool_registry: Mapping[str, Any],
    scheduler: Any,
    ledger: BudgetLedger,
    epoch: Epoch,
    reviewer: str,
    closer: str,
    review_telemetry_path: str | None,
    resolve_inputs: Callable[[NodeSpec], dict[str, Any]],
    restore_runtime: Callable[[NodeSpec, Any], None],
    reserve: Callable[[NodeSpec, Any], Any],
    stamp: Callable[[ResultEnvelope, NodeSpec, Any], None],
    add_blocker: Callable[[str, str, str], None],
    record_review_budget_alert: Callable[[NodeSpec, Dims], None],
    results: MutableMapping[str, ResultEnvelope],
) -> CodexBatchDispatchResult:
    """Dispatch a ready batch of Codex review roles through one CLI invocation."""
    if not can_codex_review_batch(
        batch=batch,
        checkpoint=checkpoint,
        nodes_by_id=nodes_by_id,
        reviewer=reviewer,
        closer=closer,
    ):
        return CodexBatchDispatchResult(dispatched=False)

    from .adapters.codex import CodexAdapter

    prepared: list[tuple[NodeSpec, Any]] = []
    for node_id in batch:
        node = nodes_by_id[node_id]
        runtime = runtime_by_id[node.id]
        node.idempotency_key = compute_idempotency_key(
            node, resolve_inputs(node), dict(tool_registry)
        )
        restore_runtime(node, runtime)
        scheduler.mark(node.id, NodeStatus.READY)
        admission = reserve(node, runtime)
        if not admission.admitted:
            for prepared_node, _ in prepared:
                ledger.release(epoch.epoch_seq, prepared_node.id)
            add_blocker(node.id, "budget exhausted before dispatch", admission.reason or "global")
            return CodexBatchDispatchResult(dispatched=True, budget_stopped=True)
        scheduler.mark(node.id, NodeStatus.RESERVED)
        runtime.reservation_id = admission.reservation_id
        scheduler.mark(node.id, NodeStatus.RUNNING)
        runtime.attempt += 1
        prepared.append((node, runtime))

    nodes = [node for node, _ in prepared]
    try:
        envelopes = CodexAdapter(telemetry_path=review_telemetry_path).run_batch(nodes)
    except Exception as exc:
        envelopes = [adapter_crash_envelope(node, exc) for node in nodes]

    envelope_by_id = {envelope.node_id: envelope for envelope in envelopes}
    for node, runtime in prepared:
        envelope = envelope_by_id.get(node.id)
        if envelope is None:
            envelope = ResultEnvelope(
                node_id=node.id,
                idempotency_key=node.idempotency_key,
                status="failed",
                error_class=ErrorClass.SCHEMA_INVALID,
                artifact={"missing_batch_result": node.id},
            )
        stamp(envelope, node, runtime)
        actual = commit_actual_usage(
            ledger=ledger,
            epoch_seq=epoch.epoch_seq,
            node_id=node.id,
            runtime=runtime,
            actual=actual_from_envelope(envelope),
            accounting="exact",
        )
        runtime.error_class = envelope.error_class
        if classify(envelope) is None:
            scheduler.mark(node.id, NodeStatus.SUCCEEDED)
        else:
            scheduler.mark(node.id, NodeStatus.FAILED)
            add_blocker(node.id, "node failed", envelope.error_class.value)
        results[node.id] = envelope
        record_review_budget_alert(node, actual)
    return CodexBatchDispatchResult(dispatched=True)


__all__ = [
    "CodexBatchDispatchResult",
    "can_codex_review_batch",
    "dispatch_codex_review_batch",
]
