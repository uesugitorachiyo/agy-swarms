#!/usr/bin/env python3
"""Run the AC-3 / FR-20 model-router fixture and escalation probe."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agy_swarms.budget import Dims
from agy_swarms.model_routing import route_model_tier, run_model_router_fixture
from agy_swarms.types import Caps, NodeSpec


def _decision_record(decision) -> dict[str, Any]:
    record = asdict(decision)
    record["tier"] = decision.tier.value
    record["charge"] = record["escalation_charge"]
    record["concerns"] = list(decision.concerns)
    return record


def run_probe(
    *,
    router_cases_path: Path = Path("benchmarks/router_cases.json"),
    lockfile_path: Path = Path("agy.lock"),
    output_path: Path = Path(".planning/spikes/ac3-model-router.json"),
    write_output: bool = True,
) -> dict[str, Any]:
    fixture = run_model_router_fixture(
        router_cases_path=router_cases_path,
        lockfile_path=lockfile_path,
    )
    escalatable = NodeSpec(
        id="retrying_worker",
        role="worker",
        objective="retry after repeated failure",
        caps=Caps(max_output_tokens=250, max_thinking_tokens=25),
    )
    admitted = route_model_tier(
        escalatable,
        failed_attempts=2,
        remaining_budget=Dims(tokens=1_000, usd=1.0),
    )
    blocked = route_model_tier(
        escalatable,
        failed_attempts=2,
        remaining_budget=Dims(tokens=274, usd=1.0),
    )
    result = {
        "gate": "AC-3/model-router",
        "passed": fixture["passed"] and admitted.escalated and not blocked.budget_admitted,
        "fixture": fixture,
        "escalation": {
            "admitted": _decision_record(admitted),
            "blocked": _decision_record(blocked),
        },
    }
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
    parser.add_argument("--lockfile", type=Path, default=Path("agy.lock"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/ac3-model-router.json"),
    )
    args = parser.parse_args()
    result = run_probe(
        router_cases_path=args.router_cases,
        lockfile_path=args.lockfile,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "fixture_accuracy": result["fixture"]["accuracy"],
                "fixture_matched": result["fixture"]["matched"],
                "fixture_total": result["fixture"]["total"],
                "router_cases_sha_matches_lock": result["fixture"]["router_cases_sha_matches_lock"],
                "admitted_escalation_tokens": result["escalation"]["admitted"]["escalation_charge"][
                    "tokens"
                ],
                "blocked_budget_admitted": result["escalation"]["blocked"]["budget_admitted"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
