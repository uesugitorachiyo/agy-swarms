#!/usr/bin/env python3
"""Run D6.1 declarative policy-engine evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from agy_swarms.governance.policy import (
    ActionKind,
    ApprovalToken,
    PolicyAction,
    PolicyConfig,
    PolicyDecision,
    PolicyDecisionStatus,
    PolicyError,
    PolicyMode,
    RiskLevel,
    evaluate_policy,
)


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/d6.1-policy-engine.json"),
    write_output: bool = True,
) -> dict:
    auto_write = evaluate_policy(
        PolicyAction(
            id="auto-write",
            kind=ActionKind.WRITE,
            target="src/app.py",
            declared=True,
            within_sandbox=True,
            risk=RiskLevel.LOW,
        ),
        PolicyConfig(mode=PolicyMode.AUTO),
    )
    batched_patch = evaluate_policy(
        PolicyAction(
            id="patch-promote",
            kind=ActionKind.PATCH_PROMOTION,
            target="sandbox.patch",
            declared=True,
            within_sandbox=True,
            risk=RiskLevel.HIGH,
        ),
        PolicyConfig(mode=PolicyMode.BATCHED_APPROVAL),
    )
    strict_action = PolicyAction(
        id="strict-shell",
        kind=ActionKind.SHELL,
        target="uv run pytest -q",
        declared=True,
        within_sandbox=True,
        risk=RiskLevel.HIGH,
    )
    strict_without_token = evaluate_policy(
        strict_action,
        PolicyConfig(mode=PolicyMode.STRICT_DIGEST),
    )
    strict_with_token = evaluate_policy(
        strict_action,
        PolicyConfig(
            mode=PolicyMode.STRICT_DIGEST,
            approval_token=ApprovalToken(
                id="approval-1",
                approved_action_ids=("strict-shell",),
            ),
        ),
    )
    try:
        PolicyConfig(mode="permissive")
        unknown_mode_fails_closed = False
    except PolicyError:
        unknown_mode_fails_closed = True

    policy = {
        "auto_write": _decision(auto_write),
        "batched_patch": _decision(batched_patch),
        "strict_without_token": _decision(strict_without_token),
        "strict_with_token": _decision(strict_with_token),
        "unknown_mode_fails_closed": unknown_mode_fails_closed,
    }
    passed = (
        auto_write.status == PolicyDecisionStatus.ALLOWED
        and batched_patch.status == PolicyDecisionStatus.QUEUED
        and strict_without_token.status == PolicyDecisionStatus.BLOCKED
        and strict_with_token.status == PolicyDecisionStatus.ALLOWED
        and unknown_mode_fails_closed
    )
    result = {
        "gate": "D6.1/policy-engine",
        "passed": passed,
        "policy": policy,
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _decision(decision: PolicyDecision) -> dict:
    payload = asdict(decision)
    payload["status"] = decision.status.value
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/d6.1-policy-engine.json"),
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "auto_write": result["policy"]["auto_write"]["status"],
                "batched_patch": result["policy"]["batched_patch"]["status"],
                "strict_without_token": result["policy"]["strict_without_token"]["status"],
                "strict_with_token": result["policy"]["strict_with_token"]["status"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
