#!/usr/bin/env python3
"""Run the D3.5 runtime-subgraph and bounded-replan probe."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from agy_swarms.planner import ReplanExhausted, bounded_replan, merge_runtime_subgraph
from agy_swarms.types import NodeSpec, TaskGraph, TaskSpec


def _node(node_id: str, *, deps: list[str] | None = None) -> NodeSpec:
    return NodeSpec(
        id=node_id,
        role="worker",
        objective=f"work {node_id}",
        dependencies=deps or [],
        required_capabilities=["code"],
    )


class _Replanner:
    def __init__(self, outputs: list[TaskGraph]) -> None:
        self.outputs = list(outputs)
        self.calls = 0

    def replan(self, task_spec, graph, *, failed_node_id, attempt):
        self.calls += 1
        return self.outputs.pop(0)


def _configured_max_replans(config_path: Path) -> int:
    data = tomllib.loads(config_path.read_text())
    return int(data.get("phase3", {}).get("max_replans", 2))


def run_probe(
    *,
    config_path: Path = Path("config/defaults.toml"),
    output_path: Path = Path(".planning/spikes/d3.5-runtime-subgraph.json"),
    write_output: bool = True,
) -> dict[str, Any]:
    max_replans = _configured_max_replans(config_path)
    base = TaskGraph(nodes=[_node("root")])
    merged = merge_runtime_subgraph(
        base,
        TaskGraph(nodes=[_node("child", deps=["root"])], edges=[("root", "child")]),
    )

    replanner = _Replanner(
        [
            TaskGraph(nodes=[_node("bad", deps=["missing"])]),
            TaskGraph(nodes=[_node("fixed", deps=["root"])]),
        ]
    )
    replan = bounded_replan(
        TaskSpec(task="repair", model_pins={"default": "flash"}),
        replanner,
        base_graph=base,
        failed_node_id="root",
        max_replans=max_replans,
    )

    failing_replanner = _Replanner(
        [
            TaskGraph(nodes=[_node("bad1", deps=["missing1"])]),
            TaskGraph(nodes=[_node("bad2", deps=["missing2"])]),
        ]
    )
    try:
        bounded_replan(
            TaskSpec(task="repair", model_pins={"default": "flash"}),
            failing_replanner,
            base_graph=base,
            failed_node_id="root",
            max_replans=max_replans,
        )
        exhausted = False
        attempts = failing_replanner.calls
        last_error = ""
    except ReplanExhausted as exc:
        exhausted = True
        attempts = exc.attempts
        last_error = exc.validation_errors[-1]

    result = {
        "gate": "D3.5/runtime-subgraph",
        "passed": (
            [node.id for node in merged.nodes] == ["root", "child"]
            and replan.attempts == 2
            and exhausted
            and attempts == max_replans
        ),
        "configured_max_replans": max_replans,
        "validate_then_merge": {
            "merged_node_ids": [node.id for node in merged.nodes],
            "merged_edges": [list(edge) for edge in merged.edges],
        },
        "bounded_replan": {
            "attempts": replan.attempts,
            "validation_errors": list(replan.validation_errors),
            "merged_node_ids": [node.id for node in replan.graph.nodes],
        },
        "exhaustion": {
            "exhausted": exhausted,
            "attempts": attempts,
            "last_error": last_error,
        },
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/defaults.toml"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/d3.5-runtime-subgraph.json"),
    )
    args = parser.parse_args()
    result = run_probe(config_path=args.config, output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "configured_max_replans": result["configured_max_replans"],
                "bounded_replan_attempts": result["bounded_replan"]["attempts"],
                "exhaustion_attempts": result["exhaustion"]["attempts"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
