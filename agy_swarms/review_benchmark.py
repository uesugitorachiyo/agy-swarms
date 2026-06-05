"""Seeded benchmark harness for reviewer/closer backend calibration."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapters.codex import CodexAdapter, Runner
from .types import NodeSpec, ResultEnvelope

DEFAULT_REVIEW_BENCHMARK_CASES = (
    Path(__file__).resolve().parent / "fixtures" / "review_seeded_cases.json"
)

__all__ = [
    "DEFAULT_REVIEW_BENCHMARK_CASES",
    "ReviewBenchmarkCase",
    "load_seeded_review_cases",
    "run_review_benchmark",
]


@dataclass(frozen=True)
class ReviewBenchmarkCase:
    """One synthetic review/close case with an expected verdict."""

    id: str
    role: str
    objective: str
    expected_verdict: str
    boundaries: str = ""
    expected_labels: list[str] = field(default_factory=list)

    def to_node(self) -> NodeSpec:
        return NodeSpec(
            id=self.id,
            role=self.role,
            objective=self.objective,
            boundaries=self.boundaries,
            required_capabilities=["review"],
        )


def load_seeded_review_cases(
    path: str | Path = DEFAULT_REVIEW_BENCHMARK_CASES,
) -> list[ReviewBenchmarkCase]:
    """Load seeded benchmark cases from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("review benchmark cases must be a JSON array")
    cases: list[ReviewBenchmarkCase] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("review benchmark case entries must be JSON objects")
        cases.append(
            ReviewBenchmarkCase(
                id=str(item["id"]),
                role=str(item["role"]),
                objective=str(item["objective"]),
                boundaries=str(item.get("boundaries", "")),
                expected_verdict=str(item["expected_verdict"]),
                expected_labels=[str(label) for label in item.get("expected_labels", [])],
            )
        )
    return cases


def run_review_benchmark(
    cases: Iterable[ReviewBenchmarkCase],
    *,
    backends: Iterable[str] = ("codex-low", "codex-high"),
    runner: Runner | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Run review cases through each backend and return JSON-safe metrics."""
    case_list = list(cases)
    backend_list = [backend.strip() for backend in backends if backend.strip()]
    if not backend_list:
        raise ValueError("at least one review benchmark backend is required")

    results: list[dict[str, Any]] = []
    aggregate: dict[str, dict[str, Any]] = {}
    for backend in backend_list:
        matched = 0
        for case in case_list:
            result = _run_case(case, backend=backend, runner=runner, cwd=cwd)
            if result["matched"]:
                matched += 1
            results.append(result)
        aggregate[backend] = {
            "total": len(case_list),
            "matched": matched,
            "accuracy": matched / len(case_list) if case_list else None,
        }

    return {
        "status": "completed",
        "case_count": len(case_list),
        "backends": backend_list,
        "aggregate": aggregate,
        "results": results,
    }


def _run_case(
    case: ReviewBenchmarkCase,
    *,
    backend: str,
    runner: Runner | None,
    cwd: str | Path | None,
) -> dict[str, Any]:
    started = time.monotonic()
    envelope = _run_backend(case.to_node(), backend=backend, runner=runner, cwd=cwd)
    latency_ms = int((time.monotonic() - started) * 1000)
    review = envelope.artifact.get("review", {})
    actual_verdict = str(review.get("verdict", envelope.status))
    return {
        "backend": backend,
        "case_id": case.id,
        "role": case.role,
        "expected_verdict": case.expected_verdict,
        "actual_verdict": actual_verdict,
        "matched": actual_verdict == case.expected_verdict,
        "status": envelope.status,
        "concern_count": len(envelope.concerns),
        "blocker_count": len(envelope.blockers),
        "token_output": int(envelope.token_usage.get("output", 0)),
        "latency_ms": latency_ms,
        "expected_labels": list(case.expected_labels),
    }


def _run_backend(
    node: NodeSpec,
    *,
    backend: str,
    runner: Runner | None,
    cwd: str | Path | None,
) -> ResultEnvelope:
    if backend == "codex-low":
        return CodexAdapter(runner=runner, cwd=cwd, reasoning_effort="low").run(node)
    if backend == "codex-high":
        return CodexAdapter(runner=runner, cwd=cwd, reasoning_effort="high").run(node)
    raise ValueError(f"unsupported review benchmark backend: {backend}")
