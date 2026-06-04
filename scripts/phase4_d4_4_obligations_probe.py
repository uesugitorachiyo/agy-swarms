#!/usr/bin/env python3
"""Run D4.4 obligation-ledger closure evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from agy_swarms.quality.obligations import (
    ObligationClosureReport,
    VerificationSignal,
    evaluate_obligation_closure,
)


SPEC_TEXT = """\
- FR-25 The system SHALL keep an obligation ledger.
- AC-4 The closure gate MUST reject omitted obligations.
"""


def _report_record(report: ObligationClosureReport) -> dict:
    return {
        "closable": report.status.closable,
        "blockers": list(report.status.blockers),
        "obligations": [asdict(obligation) for obligation in report.obligations],
        "synthesis_handoff": {
            "closure_status": report.synthesis_handoff.closure_status,
            "obligation_ids": list(report.synthesis_handoff.obligation_ids),
            "unresolved_concerns": list(report.synthesis_handoff.unresolved_concerns),
        },
    }


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/d4.4-obligation-closure.json"),
    write_output: bool = True,
) -> dict:
    omitted_obligation = evaluate_obligation_closure(
        SPEC_TEXT,
        (
            VerificationSignal(
                obligation_id="clause:0001",
                kind="test",
                artifact_pointer="tests/test_obligations_ac4.py::test_ledger",
                producer_node_id="implementer",
                verifier_node_id="reviewer",
                verdict="passed",
            ),
        ),
    )
    false_verification = evaluate_obligation_closure(
        "FR-25 The system SHALL keep an obligation ledger.",
        (
            VerificationSignal(
                obligation_id="clause:0001",
                kind="test",
                artifact_pointer="",
                producer_node_id="implementer",
                verifier_node_id="reviewer",
                verdict="passed",
            ),
            VerificationSignal(
                obligation_id="id:FR-25",
                kind="test",
                artifact_pointer="tests/test_obligations_ac4.py::test_ledger",
                producer_node_id="implementer",
                verifier_node_id="implementer",
                verdict="passed",
            ),
        ),
    )
    valid_closure = evaluate_obligation_closure(
        "FR-25 The system SHALL keep an obligation ledger.",
        (
            VerificationSignal(
                obligation_id="clause:0001",
                kind="test",
                artifact_pointer="tests/test_obligations_ac4.py::test_clause",
                producer_node_id="implementer",
                verifier_node_id="reviewer",
                verdict="passed",
            ),
            VerificationSignal(
                obligation_id="id:FR-25",
                kind="lint",
                artifact_pointer="ruff:agy_swarms/quality/obligations.py",
                producer_node_id="implementer",
                verifier_node_id="reviewer",
                verdict="passed",
            ),
        ),
    )
    handoff = evaluate_obligation_closure(SPEC_TEXT, ())

    scenarios = {
        "omitted_obligation": _report_record(omitted_obligation),
        "false_verification": _report_record(false_verification),
        "valid_closure": _report_record(valid_closure),
        "handoff": {
            "closure_status": handoff.synthesis_handoff.closure_status,
            "unresolved_concerns": list(handoff.synthesis_handoff.unresolved_concerns),
        },
    }
    passed = (
        not omitted_obligation.status.closable
        and "clause:0002: no non-self passing verification with artifact pointer"
        in omitted_obligation.status.blockers
        and not false_verification.status.closable
        and valid_closure.status.closable
        and handoff.synthesis_handoff.unresolved_concerns == handoff.status.blockers
    )
    result = {
        "gate": "D4.4/obligation-closure",
        "passed": passed,
        "scenarios": scenarios,
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
        default=Path(".planning/spikes/d4.4-obligation-closure.json"),
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "omitted_closable": result["scenarios"]["omitted_obligation"]["closable"],
                "false_verification_closable": result["scenarios"]["false_verification"][
                    "closable"
                ],
                "valid_closure_closable": result["scenarios"]["valid_closure"]["closable"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
