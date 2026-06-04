#!/usr/bin/env python3
"""Run D4.0 ground-truth verify-gate evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from agy_swarms.gates import GateError, run_gate
from agy_swarms.quality.verify import ground_truth_verify_gate, verify_output


def _result_record(result) -> dict:
    record = asdict(result)
    record["status"] = result.status.value
    record["defects"] = list(result.defects)
    record["defect_ids"] = list(result.defect_ids)
    return record


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/d4.0-ground-truth-verify.json"),
    write_output: bool = True,
) -> dict:
    passing = verify_output(
        {"artifact": "ok"},
        {
            "signals": [
                {
                    "id": "unit-pass",
                    "kind": "test",
                    "artifact_pointer": "tests/test_example.py::test_pass",
                    "passed": True,
                }
            ]
        },
    )
    planted = verify_output(
        {"artifact": "bad"},
        {
            "signals": [
                {
                    "id": "planted-unit",
                    "kind": "test",
                    "artifact_pointer": "tests/test_example.py::test_planted",
                    "passed": False,
                    "message": "planted defect reproduced",
                }
            ]
        },
    )
    try:
        verdict = run_gate(
            ground_truth_verify_gate,
            {"artifact": "bad"},
            {
                "signals": [
                    {
                        "id": "planted-unit",
                        "kind": "test",
                        "artifact_pointer": "tests/test_example.py::test_planted",
                        "passed": False,
                        "message": "planted defect reproduced",
                    }
                ]
            },
            gate_id="ground-truth-verify",
        )
        divergence = False
        gate_error = ""
    except GateError as exc:
        verdict = None
        divergence = True
        gate_error = str(exc)

    result = {
        "gate": "D4.0/ground-truth-verify",
        "passed": (
            passing.status.value == "passed"
            and planted.status.value == "failed"
            and verdict is not None
            and verdict.passed is False
            and not divergence
        ),
        "passing_signal": _result_record(passing),
        "planted_defect": _result_record(planted),
        "fr33_double_execution": {
            "passed": verdict.passed if verdict is not None else False,
            "defects": list(verdict.defects) if verdict is not None else [],
            "divergence": divergence,
            "error": gate_error,
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
        default=Path(".planning/spikes/d4.0-ground-truth-verify.json"),
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "planted_status": result["planted_defect"]["status"],
                "fr33_divergence": result["fr33_double_execution"]["divergence"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
