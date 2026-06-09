"""Pipeline execution helpers for the conductor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .conductor_reports import PipelineItemResult
from .types import FailureClass, ResultEnvelope

PipelineStage = Callable[[Any, dict[str, Any] | None], ResultEnvelope]
PipelineKey = Callable[[str, int, int, int], str]
PipelineCacheLookup = Callable[[str], ResultEnvelope | None]
PipelineJournal = Callable[[str, ResultEnvelope], None]
EnvelopeClassifier = Callable[[ResultEnvelope], FailureClass | None]


def run_pipeline_item(
    *,
    pipeline_id: str,
    index: int,
    item: Any,
    stages: list[PipelineStage],
    pipeline_key: PipelineKey,
    cache_lookup: PipelineCacheLookup,
    journal: PipelineJournal,
    classify_envelope: EnvelopeClassifier,
) -> PipelineItemResult:
    """Run one item through a staged pipeline with per-stage cache/journal callbacks."""
    prev: dict[str, Any] | None = None
    completed = 0
    final_env: ResultEnvelope | None = None
    for stage_idx, stage in enumerate(stages):
        key = pipeline_key(pipeline_id, index, stage_idx, len(stages))
        cached = cache_lookup(key)
        if cached is not None:
            final_env, prev, completed = cached, cached.artifact, completed + 1
            continue
        envelope = stage(item, prev)
        envelope.node_id = f"{pipeline_id}:{index}:{stage_idx}"
        envelope.idempotency_key = key
        if classify_envelope(envelope) is not None:
            blocker = {
                "id": str(item),
                "what": f"pipeline stage {stage_idx} failed",
                "needs": envelope.error_class.value,
            }
            return PipelineItemResult(
                item=item,
                status="failed",
                envelope=envelope,
                stages_completed=completed,
                blocker=blocker,
            )
        final_env, prev, completed = envelope, envelope.artifact, completed + 1
        journal(key, envelope)
    return PipelineItemResult(
        item=item,
        status="succeeded",
        envelope=final_env,
        stages_completed=completed,
        blocker=None,
    )
