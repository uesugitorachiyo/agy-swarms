import json
from pathlib import Path

from agy_swarms.review_telemetry import (
    ReviewTelemetryRecord,
    append_review_telemetry,
    summarize_review_telemetry,
)


def test_append_review_telemetry_writes_metadata_without_code_contents(tmp_path: Path):
    ledger = tmp_path / "review-telemetry.jsonl"

    append_review_telemetry(
        ledger,
        ReviewTelemetryRecord(
            node_id="rev",
            role="reviewer",
            source="codex",
            verdict="block",
            model="gpt-5.5",
            reasoning_effort="high",
            concern_count=1,
            blocker_count=1,
            token_output=1200,
            wall_ms=9000,
            later_outcome="failed",
        ),
    )

    payload = json.loads(ledger.read_text(encoding="utf-8"))
    assert payload["node_id"] == "rev"
    assert payload["source"] == "codex"
    assert payload["verdict"] == "block"
    assert "objective" not in payload
    assert "prompt" not in payload
    assert "code" not in payload


def test_summarize_review_telemetry_counts_precision_style_outcomes(tmp_path: Path):
    ledger = tmp_path / "review-telemetry.jsonl"
    records = [
        ReviewTelemetryRecord(
            node_id="a",
            role="reviewer",
            source="codex",
            verdict="block",
            model="gpt-5.5",
            reasoning_effort="high",
            later_outcome="failed",
        ),
        ReviewTelemetryRecord(
            node_id="b",
            role="reviewer",
            source="codex",
            verdict="block",
            model="gpt-5.5",
            reasoning_effort="high",
            later_outcome="passed",
        ),
        ReviewTelemetryRecord(
            node_id="c",
            role="reviewer",
            source="agy",
            verdict="pass",
            model="gemini-3.5-flash",
            reasoning_effort="high",
            later_outcome="failed",
        ),
    ]
    for record in records:
        append_review_telemetry(ledger, record)

    summary = summarize_review_telemetry(ledger)

    assert summary["total"] == 3
    assert summary["by_source"]["codex"]["confirmed_blocks"] == 1
    assert summary["by_source"]["codex"]["false_blocks"] == 1
    assert summary["by_source"]["codex"]["block_precision"] == 0.5
    assert summary["by_source"]["agy"]["missed_failures"] == 1
