"""Telemetry-driven recommendations for reviewer/closer backend selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["ReviewBackendRecommendation", "recommend_review_backend"]


@dataclass(frozen=True)
class ReviewBackendRecommendation:
    """A conservative routing recommendation derived from outcome telemetry."""

    backend: str
    reason: str
    sample_count: int


def recommend_review_backend(
    telemetry_summary: dict[str, Any],
    *,
    source: str = "codex",
    default: str = "codex-low",
) -> ReviewBackendRecommendation:
    """Recommend a review backend from aggregate telemetry only."""
    by_source = telemetry_summary.get("by_source", {})
    if not isinstance(by_source, dict):
        return ReviewBackendRecommendation(default, "no_source_summary", 0)
    bucket = by_source.get(source)
    if not isinstance(bucket, dict):
        return ReviewBackendRecommendation(default, "no_source_history", 0)

    sample_count = int(bucket.get("total", 0))
    missed_failures = int(bucket.get("missed_failures", 0))
    false_blocks = int(bucket.get("false_blocks", 0))
    confirmed_blocks = int(bucket.get("confirmed_blocks", 0))
    block_precision = bucket.get("block_precision")

    if missed_failures > 0:
        return ReviewBackendRecommendation("codex-high", "codex_missed_failure", sample_count)
    if false_blocks > confirmed_blocks and false_blocks >= 2:
        return ReviewBackendRecommendation("codex-high", "codex_false_blocks_high", sample_count)
    if sample_count >= 3 and block_precision is not None and float(block_precision) >= 0.8:
        return ReviewBackendRecommendation("codex-low", "codex_precision_good", sample_count)
    return ReviewBackendRecommendation(default, "insufficient_calibration", sample_count)
