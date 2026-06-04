#!/usr/bin/env python3
"""Run the AC-28 hermetic gate evidence probe."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any

from agy_swarms.gates import (
    GateError,
    Verdict,
    declared_network_dependencies,
    run_gate,
)


def run_probe(
    *,
    output_path: Path = Path(".planning/spikes/ac28-hermetic-gate.json"),
    write_output: bool = True,
) -> dict[str, Any]:
    undeclared_error = ""

    def _undeclared_network_gate(output, contract):
        socket.create_connection(("undeclared.example", 443), timeout=0.01)
        return Verdict(passed=True)

    try:
        run_gate(_undeclared_network_gate, {}, {}, gate_id="undeclared-network")
        undeclared_blocked = False
    except GateError as exc:
        undeclared_blocked = True
        undeclared_error = str(exc)

    declared_contract = {
        "network_dependencies": [
            {"host": "declared.example", "port": 443, "purpose": "AC-28 probe"}
        ]
    }

    def _declared_network_gate(output, contract):
        sock = socket.create_connection(("declared.example", 443), timeout=0.01)
        sock.close()
        return Verdict(passed=True)

    declared_verdict = run_gate(
        _declared_network_gate, {}, declared_contract, gate_id="declared-network"
    )

    calls = {"n": 0}

    def _impure_gate(output, contract):
        calls["n"] += 1
        return Verdict(passed=(calls["n"] == 1))

    try:
        run_gate(_impure_gate, {}, {}, gate_id="purity-check")
        divergence_caught = False
        divergence_error = ""
    except GateError as exc:
        divergence_caught = True
        divergence_error = str(exc)

    result = {
        "gate": "AC-28/hermetic-gate",
        "passed": undeclared_blocked and declared_verdict.passed and divergence_caught,
        "undeclared_network": {
            "blocked": undeclared_blocked,
            "error": undeclared_error,
        },
        "declared_network": {
            "passed": declared_verdict.passed,
            "dependencies": [
                [host, port] for host, port in declared_network_dependencies(declared_contract)
            ],
        },
        "purity_guard": {
            "divergence_caught": divergence_caught,
            "error": divergence_error,
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
        default=Path(".planning/spikes/ac28-hermetic-gate.json"),
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "undeclared_network_blocked": result["undeclared_network"]["blocked"],
                "declared_network_passed": result["declared_network"]["passed"],
                "purity_divergence_caught": result["purity_guard"]["divergence_caught"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
