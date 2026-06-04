#!/usr/bin/env python3
"""Aggregate Phase-4 AC-4 exit evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.phase4_d4_0_verify_probe import run_probe as run_ground_truth_probe
from scripts.phase4_d4_1_verify_loop_probe import run_probe as run_verify_loop_probe
from scripts.phase4_d4_2_judges_probe import run_probe as run_judge_probe
from scripts.phase4_d4_3_discovery_probe import run_probe as run_discovery_probe
from scripts.phase4_d4_4_obligations_probe import run_probe as run_obligation_probe


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/ac4-phase4-exit.json"),
    write_output: bool = True,
    evidence_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    overrides = evidence_overrides or {}
    evidence = {
        "ground_truth_verify": overrides.get(
            "ground_truth_verify", run_ground_truth_probe(write_output=False)
        ),
        "verify_loop": overrides.get("verify_loop", run_verify_loop_probe(write_output=False)),
        "judge_panel": overrides.get("judge_panel", run_judge_probe(write_output=False)),
        "discovery": overrides.get("discovery", run_discovery_probe(write_output=False)),
        "obligations": overrides.get("obligations", run_obligation_probe(write_output=False)),
    }
    hard_gates = _hard_gate_summary(evidence)
    hard_failures = [name for name, gate in hard_gates.items() if not gate.get("passed", False)]
    soft_concerns = list(
        evidence["judge_panel"].get("soft_evidence", {}).get("judge_only_defects", ())
    )
    passed = not hard_failures
    result = {
        "gate": "AC-4/phase4-exit",
        "passed": passed,
        "status": "PHASE-4 EXIT READY" if passed else "BLOCKED",
        "hard_gates": hard_gates,
        "hard_failures": hard_failures,
        "soft_evidence": {
            "judge_only_defect": evidence["judge_panel"],
        },
        "soft_concerns": soft_concerns,
        "source_evidence": evidence,
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _hard_gate_summary(evidence: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ground_truth = evidence["ground_truth_verify"]
    verify_loop = evidence["verify_loop"]
    judge_panel = evidence["judge_panel"]
    discovery = evidence["discovery"]
    obligations = evidence["obligations"]

    verify_statuses = {
        name: scenario.get("status") for name, scenario in verify_loop.get("scenarios", {}).items()
    }
    obligation_scenarios = obligations.get("scenarios", {})
    judge_soft_evidence = judge_panel.get("soft_evidence", {})
    judge_verdict = judge_panel.get("judge_verdict", {})

    return {
        "verify_loop_terminates": {
            "passed": bool(verify_loop.get("passed"))
            and verify_statuses.get("pass_immediate") == "passed"
            and verify_statuses.get("max_revisions") == "max_revisions"
            and verify_statuses.get("budget_exhaustion") == "budget_exhausted"
            and verify_statuses.get("non_monotonic") == "non_monotonic",
            "evidence": verify_statuses,
        },
        "ground_truth_defect_rejected": {
            "passed": bool(ground_truth.get("passed"))
            and ground_truth.get("planted_defect", {}).get("status") == "failed"
            and not ground_truth.get("fr33_double_execution", {}).get("divergence", True),
            "evidence": {
                "planted_status": ground_truth.get("planted_defect", {}).get("status"),
                "fr33_divergence": ground_truth.get("fr33_double_execution", {}).get("divergence"),
            },
        },
        "discovery_loop_terminates": {
            "passed": bool(discovery.get("passed"))
            and discovery.get("scenarios", {}).get("dry", {}).get("status") == "dry"
            and discovery.get("scenarios", {}).get("max_iterations", {}).get("status")
            == "max_iterations",
            "evidence": {
                "dry_status": discovery.get("scenarios", {}).get("dry", {}).get("status"),
                "max_iterations_status": discovery.get("scenarios", {})
                .get("max_iterations", {})
                .get("status"),
            },
        },
        "unverified_obligation_blocks": {
            "passed": obligation_scenarios.get("handoff", {}).get("closure_status") == "blocked"
            and bool(obligation_scenarios.get("handoff", {}).get("unresolved_concerns")),
            "evidence": obligation_scenarios.get("handoff", {}),
        },
        "omitted_obligation_caught": {
            "passed": obligation_scenarios.get("omitted_obligation", {}).get("closable") is False,
            "evidence": obligation_scenarios.get("omitted_obligation", {}),
        },
        "false_verification_rejected": {
            "passed": obligation_scenarios.get("false_verification", {}).get("closable") is False,
            "evidence": obligation_scenarios.get("false_verification", {}),
        },
        "judge_only_evidence_separated": {
            "passed": bool(judge_panel.get("passed"))
            and judge_verdict.get("temperature") == 0.0
            and judge_soft_evidence.get("deterministic_gate") is False,
            "evidence": {
                "temperature": judge_verdict.get("temperature"),
                "deterministic_gate": judge_soft_evidence.get("deterministic_gate"),
                "judge_only_defects": judge_soft_evidence.get("judge_only_defects", []),
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/ac4-phase4-exit.json"),
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
                "status": result["status"],
                "hard_failures": result["hard_failures"],
                "soft_concerns": result["soft_concerns"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
