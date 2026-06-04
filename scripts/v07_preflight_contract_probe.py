#!/usr/bin/env python3
"""Validate local graph preflight output against the v0.7 schema contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_PATH = Path("schemas/local-graph-preflight-v1.schema.json")
FIXTURES = {
    "success": {
        "path": Path("tests/fixtures/local_runner/success-graph.json"),
        "command_evidence": [
            "fixture-success:prepare",
            "fixture-success:verify",
        ],
    },
    "failure": {
        "path": Path("tests/fixtures/local_runner/failure-graph.json"),
        "command_evidence": [
            "fixture-failure:prepare",
            "fixture-failure:unit",
            "fixture-failure:should-not-run",
        ],
    },
    "dependency_skip": {
        "path": Path("tests/fixtures/local_runner/dependency-skip-graph.json"),
        "command_evidence": [
            "fixture-dependency-skip:root",
            "fixture-dependency-skip:lint",
            "fixture-dependency-skip:docs-should-not-run",
            "fixture-dependency-skip:package-should-not-run",
        ],
    },
}
SCHEMA_ID = "https://agy-swarms.local/schemas/local-graph-preflight-v1.schema.json"


def main() -> int:
    schema = _load_schema()
    cases = [_run_case(fixture, schema) for fixture in FIXTURES.values()]
    passed = all(case["passed"] for case in cases)
    print(
        json.dumps(
            {
                "gate": "V07-AC3",
                "passed": passed,
                "schema": SCHEMA_PATH.as_posix(),
                "cases": cases,
            },
            indent=2,
        )
    )
    return 0 if passed else 1


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        capture_output=True,
        text=True,
    )


def _run_case(fixture: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    path = fixture["path"]
    proc = _run_cli("preflight", "--graph", str(path))
    commands_executed = any(
        evidence in proc.stdout or evidence in proc.stderr
        for evidence in fixture["command_evidence"]
    )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return _case_error(path, f"preflight output was not JSON: {exc}")

    validation_errors = _validate_preflight_payload(payload, schema)
    contract_errors: list[str] = []
    if proc.returncode != 0:
        contract_errors.append(f"preflight exited {proc.returncode}")
    if commands_executed:
        contract_errors.append("preflight emitted command execution evidence")

    return {
        "fixture": path.name,
        "passed": not validation_errors and not contract_errors,
        "schema_valid": not validation_errors,
        "status": payload.get("status") if isinstance(payload, dict) else None,
        "node_count": payload.get("node_count") if isinstance(payload, dict) else None,
        "edge_count": payload.get("edge_count") if isinstance(payload, dict) else None,
        "command_node_ids": payload.get("command_node_ids", [])
        if isinstance(payload, dict)
        else [],
        "commands_executed": commands_executed,
        "validation_errors": validation_errors,
        "contract_errors": contract_errors,
    }


def _validate_preflight_payload(payload: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if schema.get("$id") != SCHEMA_ID:
        errors.append("schema id mismatch")
    if schema.get("additionalProperties") is not False:
        errors.append("schema must reject additional top-level properties")
    if not isinstance(payload, dict):
        return [*errors, "preflight payload must be an object"]

    required = set(schema.get("required", []))
    missing = sorted(required - set(payload))
    if missing:
        errors.append(f"missing top-level keys: {missing}")

    extra = sorted(set(payload) - required)
    if extra:
        errors.append(f"unexpected top-level keys: {extra}")

    if payload.get("status") != "valid":
        errors.append("status must be valid")
    _validate_non_negative_int(payload, "node_count", errors)
    _validate_non_negative_int(payload, "edge_count", errors)
    _validate_string_int_map(payload, "role_counts", errors)
    _validate_string_list(payload, "command_node_ids", errors)
    _validate_string_list(payload, "root_nodes", errors)
    _validate_string_list(payload, "leaf_nodes", errors)
    _validate_dependency_fan_out(payload.get("dependency_fan_out"), errors)
    if payload.get("commands_executed") is not False:
        errors.append("commands_executed must be false")

    return errors


def _validate_non_negative_int(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if type(value) is not int or value < 0:
        errors.append(f"{key} must be a non-negative integer")


def _validate_string_int_map(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return
    for item_key, item_value in value.items():
        if not isinstance(item_key, str):
            errors.append(f"{key} contains a non-string key")
        if type(item_value) is not int or item_value < 0:
            errors.append(f"{key}.{item_key} must be a non-negative integer")


def _validate_string_list(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return
    if not all(isinstance(item, str) for item in value):
        errors.append(f"{key} must contain only strings")


def _validate_dependency_fan_out(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("dependency_fan_out must be an object")
        return

    expected_keys = {"dependencies", "dependents", "fan_in", "fan_out"}
    for node_id, fan_out in value.items():
        if not isinstance(node_id, str):
            errors.append("dependency_fan_out contains a non-string key")
            continue
        if not isinstance(fan_out, dict):
            errors.append(f"dependency_fan_out.{node_id} must be an object")
            continue
        missing = sorted(expected_keys - set(fan_out))
        extra = sorted(set(fan_out) - expected_keys)
        if missing:
            errors.append(f"dependency_fan_out.{node_id} missing keys: {missing}")
        if extra:
            errors.append(f"dependency_fan_out.{node_id} unexpected keys: {extra}")
        _validate_string_list(fan_out, "dependencies", errors)
        _validate_string_list(fan_out, "dependents", errors)
        _validate_non_negative_int(fan_out, "fan_in", errors)
        _validate_non_negative_int(fan_out, "fan_out", errors)


def _case_error(path: Path, error: str) -> dict[str, Any]:
    return {
        "fixture": path.name,
        "passed": False,
        "schema_valid": False,
        "status": "probe_error",
        "node_count": None,
        "edge_count": None,
        "command_node_ids": [],
        "commands_executed": False,
        "validation_errors": [error],
        "contract_errors": [],
    }


if __name__ == "__main__":
    raise SystemExit(main())
