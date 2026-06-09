"""Checkpoint/resume helpers for the conductor."""

from __future__ import annotations

from .canonical import canonical, sha256_hex
from .checkpoint import JournalEntry
from .types import Epoch, ErrorClass, NodeRuntimeState, NodeSpec, NodeStatus, ResultEnvelope


def persisted_runtime_matches(
    persisted_idempotency_key: str | None, ready_idempotency_key: str
) -> bool:
    """Return whether persisted runtime belongs to the ready-time node shape."""
    return persisted_idempotency_key == ready_idempotency_key


def cached_terminal_envelope(hit: JournalEntry | None) -> ResultEnvelope | None:
    """Return a node cache envelope when the journal hit is terminal and usable."""
    if hit is None or hit.envelope is None:
        return None
    if hit.status not in (NodeStatus.SUCCEEDED.value, NodeStatus.FAILED.value):
        return None
    return hit.envelope


def cached_success_envelope(hit: JournalEntry | None) -> ResultEnvelope | None:
    """Return a pipeline cache envelope only for committed successful stages."""
    if hit is None or hit.envelope is None or hit.status != NodeStatus.SUCCEEDED.value:
        return None
    return hit.envelope


def adopt_cached_runtime(runtime: NodeRuntimeState, hit: JournalEntry) -> None:
    """Hydrate mutable runtime state from a committed checkpoint hit."""
    runtime.status = NodeStatus(hit.status)
    runtime.attempt = hit.attempt
    runtime.remaining_schema_retries = hit.remaining_schema_retries
    runtime.budget_consumed = dict(hit.budget_consumed)
    runtime.error_class = hit.envelope.error_class if hit.envelope is not None else ErrorClass.NONE


def build_node_journal_entry(
    node_id: str,
    node: NodeSpec,
    runtime: NodeRuntimeState,
    envelope: ResultEnvelope,
    epoch: Epoch,
) -> JournalEntry:
    """Build the checkpoint row for a committed terminal graph node."""
    return JournalEntry(
        node_id=node_id,
        idempotency_key=node.idempotency_key,
        epoch_id=epoch.epoch_id,
        epoch_seq=epoch.epoch_seq,
        status=runtime.status.value,
        attempt=runtime.attempt,
        remaining_schema_retries=runtime.remaining_schema_retries,
        budget_consumed=dict(runtime.budget_consumed),
        envelope=envelope,
    )


def pipeline_stage_key(
    pipeline_id: str, index: int, stage_idx: int, n_stages: int, epoch_id: str
) -> str:
    """Build the deterministic checkpoint key for a pipeline stage."""
    return sha256_hex(canonical([pipeline_id, index, stage_idx, n_stages, epoch_id]))


def build_pipeline_journal_entry(key: str, envelope: ResultEnvelope, epoch: Epoch) -> JournalEntry:
    """Build the checkpoint row for a committed successful pipeline stage."""
    return JournalEntry(
        node_id=envelope.node_id,
        idempotency_key=key,
        epoch_id=epoch.epoch_id,
        epoch_seq=epoch.epoch_seq,
        status=NodeStatus.SUCCEEDED.value,
        attempt=1,
        remaining_schema_retries=0,
        budget_consumed={"tokens": 0, "usd": 0.0},
        envelope=envelope,
    )
