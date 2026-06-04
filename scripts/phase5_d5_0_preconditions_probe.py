#!/usr/bin/env python3
"""Run D5.0 Phase-5 precondition audit evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from agy_swarms.eval.preconditions import (
    Phase5PreconditionStatus,
    evaluate_phase5_preconditions,
)


def run_probe(
    *,
    root: Path = Path("."),
    output_path: Path = Path(".planning/spikes/d5.0-phase5-preconditions.json"),
    write_output: bool = True,
) -> dict:
    report = evaluate_phase5_preconditions(root)
    preconditions = {
        "status": report.status.value,
        "blocking_issue_ids": list(report.blocking_issue_ids),
        "blockers": [asdict(blocker) for blocker in report.blockers],
        "reported_only": dict(report.reported_only),
        "pins": report.pins,
    }
    result = {
        "gate": "D5.0/phase5-preconditions",
        "passed": True,
        "phase5_gate_ready": report.status == Phase5PreconditionStatus.PASSED,
        "preconditions": preconditions,
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/d5.0-phase5-preconditions.json"),
    )
    args = parser.parse_args()
    result = run_probe(root=args.root, output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "phase5_gate_ready": result["phase5_gate_ready"],
                "status": result["preconditions"]["status"],
                "blocking_issue_ids": result["preconditions"]["blocking_issue_ids"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
