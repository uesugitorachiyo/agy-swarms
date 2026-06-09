"""Append-only metadata ledger for review outcome calibration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ReviewTelemetryRecord",
    "append_review_telemetry",
    "summarize_review_telemetry",
]


@dataclass(frozen=True)
class ReviewTelemetryRecord:
    """Code-free metadata for later reviewer quality calibration."""

    node_id: str
    role: str
    source: str
    verdict: str
    model: str
    reasoning_effort: str
    concern_count: int = 0
    blocker_count: int = 0
    token_output: int = 0
    wall_ms: int = 0
    later_outcome: str = "unknown"


def append_review_telemetry(path: str | Path, record: ReviewTelemetryRecord) -> None:
    """Append one telemetry record as JSONL without prompt/code/objective contents."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def summarize_review_telemetry(path: str | Path) -> dict[str, Any]:
    """Aggregate review calibration counters from a telemetry JSONL file."""
    target = Path(path)
    records = _read_records(target)
    by_source: dict[str, dict[str, Any]] = {}
    for record in records:
        source = str(record.get("source", "unknown"))
        bucket = by_source.setdefault(
            source,
            {
                "total": 0,
                "confirmed_blocks": 0,
                "false_blocks": 0,
                "missed_failures": 0,
                "verdict_counts": {},
            },
        )
        bucket["total"] += 1
        verdict = str(record.get("verdict", "unknown"))
        outcome = str(record.get("later_outcome", "unknown"))
        bucket["verdict_counts"][verdict] = bucket["verdict_counts"].get(verdict, 0) + 1
        if verdict == "block" and outcome == "failed":
            bucket["confirmed_blocks"] += 1
        if verdict == "block" and outcome == "passed":
            bucket["false_blocks"] += 1
        if verdict == "pass" and outcome == "failed":
            bucket["missed_failures"] += 1

    for bucket in by_source.values():
        denom = bucket["confirmed_blocks"] + bucket["false_blocks"]
        bucket["block_precision"] = bucket["confirmed_blocks"] / denom if denom else None

    return {"total": len(records), "by_source": by_source}


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if isinstance(data, dict):
            records.append(data)
    return records
