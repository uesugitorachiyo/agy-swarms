#!/usr/bin/env python3
"""Validate tracked local-runner fixtures through the v0.6 preflight contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


FIXTURES = {
    "success": {
        "path": Path("tests/fixtures/local_runner/success-graph.json"),
        "expected": {
            "node_count": 2,
            "edge_count": 1,
            "role_counts": {"test": 1, "verify": 1},
            "command_node_ids": ["prepare", "verify"],
            "root_nodes": ["prepare"],
            "leaf_nodes": ["verify"],
        },
        "command_evidence": [
            "fixture-success:prepare",
            "fixture-success:verify",
        ],
    },
    "failure": {
        "path": Path("tests/fixtures/local_runner/failure-graph.json"),
        "expected": {
            "node_count": 3,
            "edge_count": 2,
            "role_counts": {"test": 2, "verify": 1},
            "command_node_ids": ["integration", "prepare", "unit"],
            "root_nodes": ["prepare"],
            "leaf_nodes": ["integration"],
        },
        "command_evidence": [
            "fixture-failure:prepare",
            "fixture-failure:unit",
            "fixture-failure:should-not-run",
        ],
    },
    "dependency_skip": {
        "path": Path("tests/fixtures/local_runner/dependency-skip-graph.json"),
        "expected": {
            "node_count": 4,
            "edge_count": 3,
            "role_counts": {"test": 1, "verify": 3},
            "command_node_ids": ["docs", "lint", "package", "root"],
            "root_nodes": ["root"],
            "leaf_nodes": ["docs", "package"],
        },
        "command_evidence": [
            "fixture-dependency-skip:root",
            "fixture-dependency-skip:lint",
            "fixture-dependency-skip:docs-should-not-run",
            "fixture-dependency-skip:package-should-not-run",
        ],
    },
}


def main() -> int:
    cases = [_run_case(name, fixture) for name, fixture in FIXTURES.items()]
    passed = all(case["passed"] for case in cases)
    print(
        json.dumps(
            {
                "gate": "V06-AC4",
                "passed": passed,
                "cases": cases,
            },
            indent=2,
        )
    )
    return 0 if passed else 1


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        capture_output=True,
        text=True,
    )


def _run_case(name: str, fixture: dict[str, Any]) -> dict[str, Any]:
    path = fixture["path"]
    proc = _run_cli("preflight", "--graph", str(path))
    commands_executed = any(
        evidence in proc.stdout or evidence in proc.stderr
        for evidence in fixture["command_evidence"]
    )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return _case_error(name, path, f"preflight output was not JSON: {exc}")

    expected = fixture["expected"]
    contract_errors = _contract_errors(payload, expected)
    if proc.returncode != 0:
        contract_errors.append(f"preflight exited {proc.returncode}")
    if commands_executed:
        contract_errors.append("preflight emitted command execution evidence")

    return {
        "fixture": path.name,
        "passed": not contract_errors,
        "status": payload.get("status"),
        "node_count": payload.get("node_count"),
        "edge_count": payload.get("edge_count"),
        "role_counts": payload.get("role_counts"),
        "command_node_ids": payload.get("command_node_ids", []),
        "root_nodes": payload.get("root_nodes", []),
        "leaf_nodes": payload.get("leaf_nodes", []),
        "commands_executed": commands_executed,
        "contract_errors": contract_errors,
    }


def _contract_errors(payload: Any, expected: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return ["preflight output was not an object"]

    errors: list[str] = []
    if payload.get("status") != "valid":
        errors.append(f"status was {payload.get('status')!r}")
    for key, value in expected.items():
        if payload.get(key) != value:
            errors.append(f"{key} was {payload.get(key)!r}")

    fan_out = payload.get("dependency_fan_out")
    if not isinstance(fan_out, dict):
        errors.append("dependency_fan_out was not an object")
    elif sorted(fan_out) != expected["command_node_ids"]:
        errors.append("dependency_fan_out keys did not match command node ids")

    return errors


def _case_error(name: str, path: Path, error: str) -> dict[str, Any]:
    return {
        "fixture": path.name,
        "passed": False,
        "status": "probe_error",
        "node_count": 0,
        "edge_count": 0,
        "role_counts": {},
        "command_node_ids": [],
        "root_nodes": [],
        "leaf_nodes": [],
        "commands_executed": False,
        "contract_errors": [f"{name}: {error}"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
