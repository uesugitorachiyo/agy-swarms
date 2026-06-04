#!/usr/bin/env python3
"""Run D4.3 loop-until-dry discovery evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from agy_swarms.quality.discovery import (
    DiscoveryReport,
    DiscoveryRound,
    DiscoveryStatus,
    loop_until_dry,
)


def _report_record(report: DiscoveryReport) -> dict:
    record = asdict(report)
    record["status"] = report.status.value
    record["discovered_item_ids"] = list(report.discovered_item_ids)
    record["blockers"] = list(report.blockers)
    record["steps"] = [
        {
            **asdict(step),
            "item_ids": list(step.item_ids),
            "new_item_ids": list(step.new_item_ids),
            "discovered_item_ids": list(step.discovered_item_ids),
        }
        for step in report.steps
    ]
    return record


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/d4.3-loop-until-dry.json"),
    write_output: bool = True,
) -> dict:
    dry = loop_until_dry(
        (
            DiscoveryRound(id="round-1", item_ids=("file:a", "file:b")),
            DiscoveryRound(id="round-2", item_ids=("file:b", "file:c")),
            DiscoveryRound(id="round-3", item_ids=("file:a", "file:c")),
        ),
        max_iterations=5,
    )
    max_iterations = loop_until_dry(
        (
            DiscoveryRound(id="round-1", item_ids=("claim:1",)),
            DiscoveryRound(id="round-2", item_ids=("claim:2",)),
            DiscoveryRound(id="round-3", item_ids=("claim:3",)),
        ),
        max_iterations=2,
    )
    result = {
        "gate": "D4.3/loop-until-dry",
        "passed": (
            dry.status == DiscoveryStatus.DRY
            and dry.discovered_item_ids == ("file:a", "file:b", "file:c")
            and max_iterations.status == DiscoveryStatus.MAX_ITERATIONS
            and max_iterations.discovered_item_ids == ("claim:1", "claim:2")
        ),
        "scenarios": {
            "dry": _report_record(dry),
            "max_iterations": _report_record(max_iterations),
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
        default=Path(".planning/spikes/d4.3-loop-until-dry.json"),
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "dry_status": result["scenarios"]["dry"]["status"],
                "max_iterations_status": result["scenarios"]["max_iterations"]["status"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
