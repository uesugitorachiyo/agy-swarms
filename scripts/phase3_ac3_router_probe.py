#!/usr/bin/env python3
"""Run the AC-3 router fixture hard-pass probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

from agy_swarms.routing import route_complexity


def _sha256_file(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _locked_router_cases_sha(lockfile_path: Path) -> str:
    data = tomllib.loads(lockfile_path.read_text())
    return str(data.get("benchmarks", {}).get("router_cases_sha", ""))


def run_probe(
    *,
    router_cases_path: Path = Path("benchmarks/router_cases.json"),
    lockfile_path: Path = Path("agy.lock"),
    output_path: Path = Path(".planning/spikes/ac3-router-fixture.json"),
    write_output: bool = True,
) -> dict[str, Any]:
    cases = json.loads(router_cases_path.read_text())
    router_cases_sha = _sha256_file(router_cases_path)
    locked_sha = _locked_router_cases_sha(lockfile_path)
    evaluated: list[dict[str, Any]] = []
    for case in cases:
        decision = route_complexity(case["task"])
        expected = str(case["expected_complexity_route"])
        actual = decision.route.value
        evaluated.append(
            {
                "id": case["id"],
                "expected_complexity_route": expected,
                "actual_complexity_route": actual,
                "matched": actual == expected,
                "fanout": decision.fanout,
                "reason": decision.reason,
                "concerns": list(decision.concerns),
            }
        )

    matched = sum(1 for case in evaluated if case["matched"])
    total = len(evaluated)
    accuracy = matched / total if total else 0.0
    sha_matches_lock = router_cases_sha == locked_sha
    result = {
        "gate": "AC-3/router-fixture",
        "passed": total > 0 and matched == total and sha_matches_lock,
        "accuracy": accuracy,
        "matched": matched,
        "total": total,
        "router_cases_path": str(router_cases_path),
        "router_cases_sha": router_cases_sha,
        "locked_router_cases_sha": locked_sha,
        "router_cases_sha_matches_lock": sha_matches_lock,
        "cases": evaluated,
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
        default=Path(".planning/spikes/ac3-router-fixture.json"),
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
                "accuracy": result["accuracy"],
                "matched": result["matched"],
                "total": result["total"],
                "router_cases_sha": result["router_cases_sha"],
                "router_cases_sha_matches_lock": result["router_cases_sha_matches_lock"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
