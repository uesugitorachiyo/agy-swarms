#!/usr/bin/env python3
"""Aggregate Phase-3 exit evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agy_swarms.planner import PlanArtifact, verify_seeded_planner_hard_gate
from agy_swarms.types import Epoch, NodeSpec, TaskSpec
from scripts.phase3_ac28_hermetic_gate_probe import run_probe as run_hermetic_probe
from scripts.phase3_ac3_live_planner_probe import run_probe as run_live_planner_probe
from scripts.phase3_ac3_model_router_probe import run_probe as run_model_router_probe
from scripts.phase3_ac3_router_probe import run_probe as run_router_probe
from scripts.phase3_runtime_subgraph_probe import run_probe as run_runtime_subgraph_probe


class _Planner:
    def __init__(self, artifact: PlanArtifact) -> None:
        self.artifact = artifact

    def plan(self, task_spec):
        return self.artifact


def _worker(node_id: str, *, deps: list[str] | None = None) -> NodeSpec:
    return NodeSpec(
        id=node_id,
        role="worker",
        objective=f"work {node_id}",
        dependencies=deps or [],
        required_capabilities=["code"],
    )


def _scripted_graph_equivalence() -> dict[str, Any]:
    first = _Planner(
        PlanArtifact(
            nodes=(_worker("a"), _worker("b", deps=["a"])),
            edges=(("a", "b"),),
            seed=7,
        )
    )
    second = _Planner(
        PlanArtifact(
            nodes=(_worker("x"), _worker("y", deps=["x"])),
            edges=(("x", "y"),),
            seed=7,
        )
    )
    report = verify_seeded_planner_hard_gate(
        TaskSpec(task="same task", model_pins={"default": "flash"}),
        first,
        second,
        epoch=Epoch(epoch_seq=1, epoch_id="phase3"),
    )
    payload = asdict(report)
    payload["gate"] = "AC-3/scripted-graph-equivalence"
    payload["passed"] = bool(report.equivalent and report.replay_byte_identical)
    return payload


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/ac3-phase3-exit.json"),
    write_output: bool = True,
    evidence_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    overrides = evidence_overrides or {}
    hard_gates = {
        "scripted_graph_equivalence": _scripted_graph_equivalence(),
        "router_fixture": run_router_probe(write_output=False),
        "model_router": run_model_router_probe(write_output=False),
        "hermetic_gate": run_hermetic_probe(write_output=False),
        "runtime_subgraph": run_runtime_subgraph_probe(write_output=False),
    }
    for key, value in overrides.items():
        if key in hard_gates:
            hard_gates[key] = value

    live_planner = overrides.get("live_planner", run_live_planner_probe(write_output=False))
    hard_failures = [
        name for name, evidence in hard_gates.items() if not evidence.get("passed", False)
    ]
    soft_concerns = list(live_planner.get("concerns", ()))
    passed = not hard_failures
    result = {
        "gate": "AC-3/phase3-exit",
        "passed": passed,
        "status": "PHASE-3 EXIT READY" if passed else "BLOCKED",
        "hard_gates": hard_gates,
        "hard_failures": hard_failures,
        "soft_evidence": {
            "live_planner": live_planner,
        },
        "soft_concerns": soft_concerns,
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/ac3-phase3-exit.json"),
    )
    parser.add_argument("--write", action="store_true", help="Write output JSON to disk")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write output JSON to disk (deprecated, default)",
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output, write_output=args.write and not args.no_write)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "status": result["status"],
                "hard_failures": result["hard_failures"],
                "soft_concerns": result["soft_concerns"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
