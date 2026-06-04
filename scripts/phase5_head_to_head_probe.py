#!/usr/bin/env python3
"""Run D5.6 integrated head-to-head report evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agy_swarms.eval.report import (
    ParetoPoint,
    Phase5Status,
    build_head_to_head_report,
)


def run_probe(
    *,
    root: Path = Path("."),
    output_path: Path = Path(".planning/spikes/d5.6-head-to-head.json"),
    write_output: bool = True,
) -> dict:
    # --- load sub-gate evidence ---
    spikes = root / ".planning" / "spikes"

    m1_evidence = _load_json(spikes / "d5.2-m1-quality.json")
    m2_evidence = _load_json(spikes / "d5.3-m2-token-ledger.json")
    m3_evidence = _load_json(spikes / "d5.4-m3-wallclock.json")
    cache_evidence = _load_json(spikes / "d5.5-cache-stability.json")

    # --- extract gate statuses ---
    m1_status = m1_evidence["m1"]["status"]
    m2_status = m2_evidence["m2"]["status"]
    m3_status = m3_evidence["m3"]["status"]
    cache_status = cache_evidence["cache"]["status"]

    # --- build Pareto points from M1 scores × M2 tokens ---
    pareto_points = _build_pareto_points(m1_evidence, m2_evidence)

    # --- reported-only comparands ---
    reported_only = {
        "m2_factory_v3_token_baseline": m2_evidence["m2"]["reported_only"].get(
            "factory_v3_token_baseline", "absent"
        ),
        "m3_ao2_ratio": m3_evidence["m3"]["reported_only"].get("ao2_ratio"),
        "m3_factory_v3_ratio": m3_evidence["m3"]["reported_only"].get("factory_v3_ratio"),
        "cache_hit_rate": cache_evidence["cache"]["cache_hit_rate"],
    }

    report = build_head_to_head_report(
        m1_status=m1_status,
        m1_detail={
            "mean_ratio": m1_evidence["m1"]["mean_ratio"],
            "ci_lower_bound": m1_evidence["m1"]["ci_lower_bound"],
            "threshold": m1_evidence["m1"]["threshold"],
            "num_runs": m1_evidence["m1"]["num_runs"],
        },
        m2_status=m2_status,
        m2_detail={
            "billable_equivalent_tokens": m2_evidence["m2"]["billable_equivalent_tokens"],
            "threshold_tokens": m2_evidence["m2"]["threshold_tokens"],
        },
        m3_status=m3_status,
        m3_detail={
            "candidate_median_s": m3_evidence["m3"]["candidate_median_s"],
            "ao2_threshold_s": m3_evidence["m3"]["ao2_threshold_s"],
            "factory_v3_threshold_s": m3_evidence["m3"]["factory_v3_threshold_s"],
        },
        cache_status=cache_status,
        cache_detail={
            "prefix_stable": cache_evidence["cache"]["prefix_stable"],
            "cache_hit_rate": cache_evidence["cache"]["cache_hit_rate"],
        },
        pareto_points=pareto_points,
        reported_only=reported_only,
        provenance={
            "m1_evidence": str(spikes / "d5.2-m1-quality.json"),
            "m2_evidence": str(spikes / "d5.3-m2-token-ledger.json"),
            "m3_evidence": str(spikes / "d5.4-m3-wallclock.json"),
            "cache_evidence": str(spikes / "d5.5-cache-stability.json"),
        },
    )

    result = {
        "gate": "D5.6/head-to-head",
        "passed": report.status == Phase5Status.CANDIDATE,
        "status": report.status.value,
        "gates": [
            {
                "gate_id": g.gate_id,
                "status": g.status,
                "blocking": g.blocking,
                "detail": g.detail,
            }
            for g in report.gates
        ],
        "pareto_points": [
            {
                "run_id": p.run_id,
                "quality_ratio": p.quality_ratio,
                "billable_tokens": p.billable_tokens,
            }
            for p in report.pareto_points
        ],
        "reported_only": report.reported_only,
        "provenance": report.provenance,
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _build_pareto_points(m1_evidence: dict, m2_evidence: dict) -> tuple[ParetoPoint, ...]:
    """Build Pareto points pairing each M1 score with the overall M2 billable tokens."""
    billable = m2_evidence["m2"]["billable_equivalent_tokens"]
    points = []
    for score in m1_evidence["m1"]["scores"]:
        points.append(
            ParetoPoint(
                run_id=score["run_id"],
                quality_ratio=score["ratio"],
                billable_tokens=billable,
            )
        )
    return tuple(points)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/d5.6-head-to-head.json"),
    )
    args = parser.parse_args()
    result = run_probe(root=args.root, output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "status": result["status"],
                "blocking_gates_passed": sum(
                    1 for g in result["gates"] if g["blocking"] and g["status"] == "passed"
                ),
                "blocking_gates_total": sum(1 for g in result["gates"] if g["blocking"]),
                "pareto_points": len(result["pareto_points"]),
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
