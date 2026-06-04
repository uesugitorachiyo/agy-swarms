#!/usr/bin/env python3
"""Run the D2.9 / ADR-001 Python-vs-Rust go/kill profiling probe."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agy_swarms.profiling import decide_rust_port, profile_conductor


def _locked_reference_sha(lockfile: Path) -> str:
    data = tomllib.loads(lockfile.read_text())
    return str(data.get("benchmarks", {}).get("reference_task_sha", ""))


def run_probe(
    *,
    reference_task_path: Path,
    lockfile_path: Path = Path("agy.lock"),
    worker_count: int = 16,
    model_wait_s: float = 0.005,
) -> dict[str, Any]:
    profile = profile_conductor(
        reference_task_path,
        worker_count=worker_count,
        model_wait_s=model_wait_s,
    )
    decision = decide_rust_port(profile)
    locked_sha = _locked_reference_sha(lockfile_path)
    sha_matches_lock = profile.reference_task_sha == locked_sha
    return {
        "gate": "D2.9/ADR-001",
        "passed": sha_matches_lock
        and decision.status in {"accepted_as_no_port", "trigger_rust_port"},
        "profile": asdict(profile),
        "decision": asdict(decision),
        "thresholds": {
            "conductor_overhead_pct": 20.0,
            "min_gil_bound_fanout": 16,
        },
        "reference_task_path": str(reference_task_path),
        "locked_reference_task_sha": locked_sha,
        "reference_task_sha_matches_lock": sha_matches_lock,
        "measurement_environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "transport": "scripted_profile_fixture",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reference-task",
        type=Path,
        default=Path("benchmarks/reference_task.md"),
    )
    parser.add_argument("--lockfile", type=Path, default=Path("agy.lock"))
    parser.add_argument("--worker-count", type=int, default=16)
    parser.add_argument("--model-wait-s", type=float, default=0.005)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/d2.9-adr001-go-kill-profile.json"),
    )
    args = parser.parse_args()

    result = run_probe(
        reference_task_path=args.reference_task,
        lockfile_path=args.lockfile,
        worker_count=args.worker_count,
        model_wait_s=args.model_wait_s,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "status": result["decision"]["status"],
                "conductor_overhead_pct": result["profile"]["conductor_overhead_pct"],
                "useful_fanout_ceiling": result["profile"]["useful_fanout_ceiling"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
