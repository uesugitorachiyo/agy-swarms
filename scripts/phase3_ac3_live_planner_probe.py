#!/usr/bin/env python3
"""Run the AC-3 live-planner bounded-invariants soft-metric probe."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agy_swarms.live_planner_metrics import evaluate_live_planner_soft_metrics
from agy_swarms.types import Caps, NodeSpec, TaskGraph


def _node(node_id: str, role: str, *, deps: list[str] | None = None) -> NodeSpec:
    return NodeSpec(
        id=node_id,
        role=role,
        objective=f"{role} {node_id}",
        dependencies=deps or [],
        required_capabilities=["code"] if role == "worker" else [],
        caps=Caps(max_output_tokens=100, max_thinking_tokens=50),
    )


def _sample_live_outputs() -> list[TaskGraph]:
    """Deterministic stand-in for live planner outputs; no model call in unit evidence."""
    return [
        TaskGraph(
            nodes=[
                _node("s1-plan", "planner"),
                _node("s1-a", "worker", deps=["s1-plan"]),
                _node("s1-b", "worker", deps=["s1-a"]),
            ],
            seed=1,
        ),
        TaskGraph(
            nodes=[
                _node("s2-plan", "planner"),
                _node("s2-a", "worker", deps=["s2-plan"]),
                _node("s2-b", "worker", deps=["s2-plan"]),
            ],
            seed=2,
        ),
    ]


def run_probe(
    *,
    router_cases_path: Path = Path("benchmarks/router_cases.json"),
    config_path: Path = Path("config/defaults.toml"),
    output_path: Path = Path(".planning/spikes/ac3-live-planner-soft.json"),
    write_output: bool = True,
) -> dict:
    result = evaluate_live_planner_soft_metrics(
        _sample_live_outputs(),
        router_cases_path=router_cases_path,
        config_path=config_path,
        budget_limit_tokens=1_000,
    )
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--router-cases",
        type=Path,
        default=Path("benchmarks/router_cases.json"),
    )
    parser.add_argument("--config", type=Path, default=Path("config/defaults.toml"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/ac3-live-planner-soft.json"),
    )
    args = parser.parse_args()
    result = run_probe(
        router_cases_path=args.router_cases,
        config_path=args.config,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "hard_gate": result["hard_gate"],
                "edge_set_jaccard": result["edge_set_jaccard"],
                "jaccard_threshold": result["jaccard_threshold"],
                "concerns": result["concerns"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
