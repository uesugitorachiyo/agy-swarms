#!/usr/bin/env python3
"""Run D6.0 Phase-6 precondition and existing-surface audit evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from agy_swarms.governance.phase6_preconditions import (
    Phase6EntryStatus,
    evaluate_phase6_preconditions,
)


def run_probe(
    *,
    root: Path = Path("."),
    output_path: Path = Path(".planning/spikes/d6.0-phase6-preconditions.json"),
    write_output: bool = True,
) -> dict:
    report = evaluate_phase6_preconditions(root)
    surfaces = {
        key: {
            "id": surface.id,
            "status": surface.status.value,
            "message": surface.message,
            "evidence": list(surface.evidence),
        }
        for key, surface in report.surfaces.items()
    }
    result = {
        "gate": "D6.0/phase6-preconditions",
        "passed": report.status == Phase6EntryStatus.PASSED,
        "phase6_entry_ready": report.status == Phase6EntryStatus.PASSED,
        "preconditions": {
            "status": report.status.value,
            "blocking_issue_ids": list(report.blocking_issue_ids),
            "blockers": [asdict(blocker) for blocker in report.blockers],
        },
        "surfaces": surfaces,
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
        default=Path(".planning/spikes/d6.0-phase6-preconditions.json"),
    )
    parser.add_argument("--write", action="store_true", help="Write output JSON to disk")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write output JSON to disk (deprecated, default)",
    )
    args = parser.parse_args()
    result = run_probe(
        root=args.root, output_path=args.output, write_output=args.write and not args.no_write
    )
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "phase6_entry_ready": result["phase6_entry_ready"],
                "status": result["preconditions"]["status"],
                "blocking_issue_ids": result["preconditions"]["blocking_issue_ids"],
                "surface_statuses": {
                    key: surface["status"] for key, surface in result["surfaces"].items()
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
