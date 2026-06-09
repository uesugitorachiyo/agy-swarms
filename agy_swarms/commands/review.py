"""Review and handoff command handlers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agy_swarms.handoff import build_agy_review_prompt
from agy_swarms.hybrid_review import ReviewRole, ReviewRouteError, route_review_role
from agy_swarms.review_benchmark import load_seeded_review_cases, run_review_benchmark
from agy_swarms.review_routing_policy import recommend_review_backend
from agy_swarms.review_telemetry import summarize_review_telemetry


def cmd_handoff(args: argparse.Namespace) -> int:
    """Generate a read-only agy review prompt for a run report."""
    print(build_agy_review_prompt(report_path=args.report))
    return 0


def cmd_review_route(args: argparse.Namespace) -> int:
    """Resolve read-only reviewer/closer routes without provider execution."""
    try:
        reviewer = route_review_role(ReviewRole.REVIEWER, adapter=args.reviewer)
        closer = route_review_role(ReviewRole.CLOSER, adapter=args.closer)
    except ReviewRouteError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    payload: dict[str, Any] = {
        "status": "review_route_resolved",
        "reviewer": reviewer.to_json(),
        "closer": closer.to_json(),
        "commands_executed": False,
    }
    if args.telemetry:
        telemetry_summary = summarize_review_telemetry(args.telemetry)
        recommendation = recommend_review_backend(telemetry_summary)
        payload["telemetry"] = telemetry_summary
        payload["recommendation"] = {
            "backend": recommendation.backend,
            "reason": recommendation.reason,
            "sample_count": recommendation.sample_count,
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_review_benchmark(args: argparse.Namespace) -> int:
    """Run seeded reviewer/closer benchmark cases against selected backends."""
    try:
        cases = load_seeded_review_cases(args.cases)
        report = run_review_benchmark(
            cases,
            backends=args.backends.split(","),
            cwd=Path.cwd(),
        )
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


__all__ = ["cmd_handoff", "cmd_review_benchmark", "cmd_review_route"]
