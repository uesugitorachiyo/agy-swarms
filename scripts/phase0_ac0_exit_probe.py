#!/usr/bin/env python3
"""Aggregate AC-0 exit evidence from the recorded Phase-0 ledger and lockfile."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


REQUIRED_PHASE0_GATES = (
    "s1_g0_1_bootstrap",
    "s1_g0_1_live_repair",
    "s1_g0_1_wall_clock_comparands",
    "s2_g0_2_bootstrap",
    "s2_g0_2_soak",
    "s3_g0_3",
    "s4_g0_4",
    "s5_g0_5",
    "s6_g0_6",
    "g0_8",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_lock(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def run_probe(
    *,
    lock_path: Path | None = None,
    ledger_path: Path | None = None,
    output_path: Path | None = None,
    write_output: bool = True,
) -> dict[str, Any]:
    root = _repo_root()
    lock_path = lock_path or root / "agy.lock"
    ledger_path = ledger_path or root / "phase0-results.md"
    output_path = output_path or root / ".planning/spikes/ac0-exit.json"

    lock = _load_lock(lock_path)
    phase0 = lock.get("phase0", {})
    auth = lock.get("auth", {})
    ledger_text = ledger_path.read_text(encoding="utf-8")

    required_gates = {
        gate: str(phase0.get(gate, "")).startswith("PASSED") for gate in REQUIRED_PHASE0_GATES
    }
    missing_or_unpassed = [gate for gate, passed in required_gates.items() if not passed]
    ac0_lock_go = str(phase0.get("ac0", "")).startswith("GO")
    ac0_ledger_go = (
        "AC-0 aggregate" in ledger_text and "PASSED" in ledger_text and "GO" in ledger_text
    )
    passed = not missing_or_unpassed and ac0_lock_go and ac0_ledger_go
    result = {
        "gate": "AC-0",
        "passed": passed,
        "status": "GO" if passed else "BLOCKED",
        "required_gates": required_gates,
        "missing_or_unpassed": missing_or_unpassed,
        "ac0_lock_go": ac0_lock_go,
        "ac0_ledger_go": ac0_ledger_go,
        "phase2_entry_constraints": {
            "default_worker_transport": auth.get("default"),
            "api_key_default": auth.get("api_key_default"),
            "agy_concurrency_cap": phase0.get("agy_concurrency_cap"),
            "default_fanout_cap": phase0.get("cost_latency_projected_worker_cap"),
            "model_diversity_route": "explicit_gemini_sdk_api_adapter",
        },
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/ac0-exit.json"),
    )
    parser.add_argument("--write", action="store_true", help="Write output JSON to disk")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write output JSON to disk (deprecated, default)",
    )
    args = parser.parse_args()
    result = run_probe(
        lock_path=args.lock,
        ledger_path=args.ledger,
        output_path=args.output,
        write_output=args.write and not args.no_write,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
