from pathlib import Path

from agy_swarms.review_routing_policy import recommend_review_backend
from agy_swarms.review_telemetry import (
    ReviewTelemetryRecord,
    append_review_telemetry,
    summarize_review_telemetry,
)


def test_recommend_review_backend_prefers_codex_low_when_precision_is_good(
    tmp_path: Path,
):
    telemetry = tmp_path / "review.jsonl"
    for node_id, verdict, outcome in (
        ("a", "block", "failed"),
        ("b", "block", "failed"),
        ("c", "pass", "passed"),
    ):
        append_review_telemetry(
            telemetry,
            ReviewTelemetryRecord(
                node_id=node_id,
                role="reviewer",
                source="codex",
                verdict=verdict,
                model="gpt-5.5",
                reasoning_effort="low",
                later_outcome=outcome,
            ),
        )

    recommendation = recommend_review_backend(summarize_review_telemetry(telemetry))

    assert recommendation.backend == "codex-low"
    assert recommendation.reason == "codex_precision_good"


def test_recommend_review_backend_escalates_after_missed_failure(tmp_path: Path):
    telemetry = tmp_path / "review.jsonl"
    append_review_telemetry(
        telemetry,
        ReviewTelemetryRecord(
            node_id="a",
            role="reviewer",
            source="codex",
            verdict="pass",
            model="gpt-5.5",
            reasoning_effort="low",
            later_outcome="failed",
        ),
    )

    recommendation = recommend_review_backend(summarize_review_telemetry(telemetry))

    assert recommendation.backend == "codex-high"
    assert recommendation.reason == "codex_missed_failure"
