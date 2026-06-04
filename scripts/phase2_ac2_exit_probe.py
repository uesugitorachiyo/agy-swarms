#!/usr/bin/env python3
"""Run the AC-2 Phase-2 exit evidence probe."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agy_swarms.phase2_exit import run_ac2_exit_probe


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/ac2-phase2-exit.json"),
    write_output: bool = True,
) -> dict[str, Any]:
    result = run_ac2_exit_probe(
        reference_task_path=Path("benchmarks/reference_task.md"),
        baseline_path=Path(".planning/spikes/s1-g0.1-baseline-bootstrap.json"),
        config_path=Path("config/defaults.toml"),
        adr001_path=Path(".planning/spikes/d2.9-adr001-go-kill-profile.json"),
    )
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/ac2-phase2-exit.json"),
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
                "widths": result["widths"],
                "m2_reduction": result["m2"]["candidate_reduction"],
                "x_target": result["m2"]["x_target_reduction"],
                "peak_context_tokens": max(
                    report["peak_conductor_context_tokens"] for report in result["width_reports"]
                ),
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
