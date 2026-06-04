#!/usr/bin/env python3
"""Aggregate Phase-5 AC-5 exit evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def run_probe(
    *,
    root: Path = Path("."),
    output_path: Path = Path(".planning/spikes/ac5-phase5-exit.json"),
    write_output: bool = True,
    evidence_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    overrides = evidence_overrides or {}
    spikes = root / ".planning" / "spikes"

    # --- Load evidence files ---
    evidence = {
        "preconditions": overrides.get("preconditions")
        or _load_json(spikes / "d5.0-phase5-preconditions.json"),
        "benchmark": overrides.get("benchmark")
        or _load_json(spikes / "d5.1-benchmark-manifest.json"),
        "quality": overrides.get("quality") or _load_json(spikes / "d5.2-m1-quality.json"),
        "tokens": overrides.get("tokens") or _load_json(spikes / "d5.3-m2-token-ledger.json"),
        "wallclock": overrides.get("wallclock") or _load_json(spikes / "d5.4-m3-wallclock.json"),
        "cache": overrides.get("cache") or _load_json(spikes / "d5.5-cache-stability.json"),
        "head_to_head": overrides.get("head_to_head")
        or _load_json(spikes / "d5.6-head-to-head.json"),
    }

    # --- Evaluate hard gates ---
    hard_gates = _hard_gate_summary(evidence)
    hard_failures = [name for name, gate in hard_gates.items() if not gate.get("passed", False)]

    passed = not hard_failures
    result = {
        "gate": "AC-5/phase5-exit",
        "passed": passed,
        "status": "PHASE-5 EXIT READY" if passed else "BLOCKED",
        "hard_gates": hard_gates,
        "hard_failures": hard_failures,
        "provenance_check": _check_provenance(evidence),
        "source_evidence": evidence,
    }

    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    return result


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _hard_gate_summary(evidence: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    preconditions = evidence["preconditions"]
    benchmark = evidence["benchmark"]
    quality = evidence["quality"]
    tokens = evidence["tokens"]
    wallclock = evidence["wallclock"]
    cache = evidence["cache"]
    h2h = evidence["head_to_head"]

    # D5.2 Quality (M1): lower bound must be >= 0.95
    m1_passed = (
        bool(quality.get("passed")) and quality.get("m1", {}).get("ci_lower_bound", 0.0) >= 0.95
    )

    # D5.3 Tokens (M2): billable tokens < 60% of opus baseline
    m2_passed = bool(tokens.get("passed")) and tokens.get("m2", {}).get(
        "billable_equivalent_tokens", 999999
    ) < tokens.get("m2", {}).get("threshold_tokens", 0)

    # D5.4 Wallclock (M3): candidate median <= 0.50x baselines
    m3_passed = (
        bool(wallclock.get("passed"))
        and wallclock.get("m3", {}).get("candidate_median_s", 999999.0)
        <= wallclock.get("m3", {}).get("ao2_threshold_s", 0.0)
        and wallclock.get("m3", {}).get("candidate_median_s", 999999.0)
        <= wallclock.get("m3", {}).get("factory_v3_threshold_s", 0.0)
    )

    # Preconditions & benchmark validity
    preconditions_passed = (
        bool(preconditions.get("passed")) and preconditions.get("phase5_gate_ready") is True
    )
    benchmark_passed = (
        bool(benchmark.get("passed")) and benchmark.get("run_record", {}).get("valid") is True
    )

    # Integrated Head-to-Head Candidate status
    h2h_passed = bool(h2h.get("passed")) and h2h.get("status") == "PHASE-5 CANDIDATE"

    return {
        "preconditions_satisfied": {
            "passed": preconditions_passed,
            "evidence": {
                "passed": preconditions.get("passed"),
                "ready": preconditions.get("phase5_gate_ready"),
            },
        },
        "benchmark_provenance_valid": {
            "passed": benchmark_passed,
            "evidence": {
                "passed": benchmark.get("passed"),
                "run_record_valid": benchmark.get("run_record", {}).get("valid"),
            },
        },
        "m1_quality_ci_lower_bound_passed": {
            "passed": m1_passed,
            "evidence": {
                "passed": quality.get("passed"),
                "ci_lower_bound": quality.get("m1", {}).get("ci_lower_bound"),
                "threshold": quality.get("m1", {}).get("threshold"),
            },
        },
        "m2_token_ledger_passed": {
            "passed": m2_passed,
            "evidence": {
                "passed": tokens.get("passed"),
                "billable_equivalent_tokens": tokens.get("m2", {}).get(
                    "billable_equivalent_tokens"
                ),
                "threshold_tokens": tokens.get("m2", {}).get("threshold_tokens"),
            },
        },
        "m3_wallclock_median_passed": {
            "passed": m3_passed,
            "evidence": {
                "passed": wallclock.get("passed"),
                "candidate_median_s": wallclock.get("m3", {}).get("candidate_median_s"),
                "ao2_threshold_s": wallclock.get("m3", {}).get("ao2_threshold_s"),
                "factory_v3_threshold_s": wallclock.get("m3", {}).get("factory_v3_threshold_s"),
            },
        },
        "cache_stability_recorded": {
            "passed": bool(cache.get("passed"))
            and cache.get("cache", {}).get("prefix_stable") is True,
            "evidence": {
                "passed": cache.get("passed"),
                "prefix_stable": cache.get("cache", {}).get("prefix_stable"),
                "cache_hit_rate": cache.get("cache", {}).get("cache_hit_rate"),
            },
        },
        "integrated_h2h_report_candidate": {
            "passed": h2h_passed,
            "evidence": {
                "passed": h2h.get("passed"),
                "status": h2h.get("status"),
            },
        },
    }


def _check_provenance(evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    preconditions = evidence["preconditions"]
    benchmark = evidence["benchmark"]
    wallclock = evidence["wallclock"]

    # Match seed between precondition pin and benchmark run record
    pin_seed = preconditions.get("preconditions", {}).get("pins", {}).get("blinding_seed")
    run_seed = benchmark.get("run_record", {}).get("blinding_seed")
    seed_match = (pin_seed == run_seed) if pin_seed is not None else False

    # Match rubric hash
    pin_rubric = preconditions.get("preconditions", {}).get("pins", {}).get("judge_rubric_sha")
    manifest_rubric = benchmark.get("manifest", {}).get("rubric_sha")
    rubric_match = (pin_rubric == manifest_rubric) if pin_rubric is not None else False

    # Check network profiles and region
    env = wallclock.get("m3", {}).get("measurement_environment", {})
    env_ok = (
        env.get("arch") == "arm64"
        and env.get("network_profile") == "local_uncontrolled"
        and env.get("provider_region") == "UNOBSERVED_AGY_OAUTH"
    )

    return {
        "blinding_seed_consistent": seed_match,
        "judge_rubric_consistent": rubric_match,
        "measurement_environment_verified": env_ok,
        "provenance_details": {
            "pin_seed": pin_seed,
            "run_seed": run_seed,
            "pin_rubric": pin_rubric,
            "manifest_rubric": manifest_rubric,
            "measurement_env": env,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/ac5-phase5-exit.json"),
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
                "status": result["status"],
                "hard_failures": result["hard_failures"],
                "provenance_check": {
                    "blinding_seed_consistent": result["provenance_check"][
                        "blinding_seed_consistent"
                    ],
                    "judge_rubric_consistent": result["provenance_check"][
                        "judge_rubric_consistent"
                    ],
                    "measurement_environment_verified": result["provenance_check"][
                        "measurement_environment_verified"
                    ],
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
