#!/usr/bin/env python3
"""Run D4.1 evaluator-optimizer bounded-loop evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from agy_swarms.quality.verify import (
    Revision,
    VerifyLoopReport,
    VerifyLoopStatus,
    run_evaluator_optimizer_loop,
)


def _report_record(report: VerifyLoopReport) -> dict:
    record = asdict(report)
    record["status"] = report.status.value
    record["unresolved_defect_ids"] = list(report.unresolved_defect_ids)
    record["blockers"] = list(report.blockers)
    record["steps"] = [
        {
            **asdict(step),
            "unresolved_defect_ids": list(step.unresolved_defect_ids),
            "addressed_defect_ids": list(step.addressed_defect_ids),
        }
        for step in report.steps
    ]
    return record


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/d4.1-verify-loop.json"),
    write_output: bool = True,
) -> dict:
    pass_immediate = run_evaluator_optimizer_loop(
        (),
        (),
        max_revisions=2,
        budget_tokens=100,
        generator_node_id="generator-node",
        verifier_node_id="verifier-node",
    )
    max_revisions = run_evaluator_optimizer_loop(
        ("test:one", "lint:two"),
        (Revision(id="rev-1", addressed_defect_ids=("test:one",), cost_tokens=7),),
        max_revisions=1,
        budget_tokens=100,
        generator_node_id="generator-node",
        verifier_node_id="verifier-node",
    )
    budget_exhaustion = run_evaluator_optimizer_loop(
        ("test:one",),
        (Revision(id="rev-expensive", addressed_defect_ids=("test:one",), cost_tokens=50),),
        max_revisions=2,
        budget_tokens=49,
        generator_node_id="generator-node",
        verifier_node_id="verifier-node",
    )
    non_monotonic = run_evaluator_optimizer_loop(
        ("test:one",),
        (Revision(id="rev-stale", addressed_defect_ids=("schema:other",), cost_tokens=1),),
        max_revisions=2,
        budget_tokens=100,
        generator_node_id="generator-node",
        verifier_node_id="verifier-node",
    )

    scenarios = {
        "pass_immediate": _report_record(pass_immediate),
        "max_revisions": _report_record(max_revisions),
        "budget_exhaustion": _report_record(budget_exhaustion),
        "non_monotonic": _report_record(non_monotonic),
    }
    passed = (
        pass_immediate.status == VerifyLoopStatus.PASSED
        and max_revisions.status == VerifyLoopStatus.MAX_REVISIONS
        and budget_exhaustion.status == VerifyLoopStatus.BUDGET_EXHAUSTED
        and budget_exhaustion.revisions == 0
        and non_monotonic.status == VerifyLoopStatus.NON_MONOTONIC
        and non_monotonic.revisions == 0
    )
    result = {
        "gate": "D4.1/evaluator-optimizer-loop",
        "passed": passed,
        "scenarios": scenarios,
        "separate_contexts": {
            "generator_node_id": pass_immediate.generator_node_id,
            "verifier_node_id": pass_immediate.verifier_node_id,
        },
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
        default=Path(".planning/spikes/d4.1-verify-loop.json"),
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "scenarios": {
                    name: scenario["status"] for name, scenario in result["scenarios"].items()
                },
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
