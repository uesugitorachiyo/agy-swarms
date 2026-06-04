#!/usr/bin/env python3
"""Validate opt-in command review evidence against the tracked v0.9 contract."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "local-command-review-v1.schema.json"
FIXTURES = [
    ROOT / "tests" / "fixtures" / "local_runner" / "success-graph.json",
    ROOT / "tests" / "fixtures" / "local_runner" / "failure-graph.json",
    ROOT / "tests" / "fixtures" / "local_runner" / "dependency-skip-graph.json",
]
REVIEW_KEYS = {"executable", "argv_count", "redacted_argv", "argv_sha256"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def main() -> int:
    schema_errors = _validate_schema_file()
    cases = [_run_case(path, schema_errors) for path in FIXTURES]
    passed = not schema_errors and all(case["passed"] for case in cases)
    print(
        json.dumps(
            {
                "gate": "V09-AC4",
                "passed": passed,
                "schema": "schemas/local-command-review-v1.schema.json",
                "schema_errors": schema_errors,
                "cases": cases,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


def _validate_schema_file() -> list[str]:
    errors: list[str] = []
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"schema file missing or unreadable: {exc}"]
    except json.JSONDecodeError as exc:
        return [f"schema file is not valid JSON: {exc}"]

    if schema.get("$id") != "https://agy-swarms.local/schemas/local-command-review-v1.schema.json":
        errors.append("schema $id must match local-command-review-v1")
    if schema.get("type") != "object":
        errors.append("schema root type must be object")

    additional = schema.get("additionalProperties")
    if not isinstance(additional, dict):
        return errors + ["schema additionalProperties must define review entries"]

    if set(additional.get("required", [])) != REVIEW_KEYS:
        errors.append("schema required keys must match command review keys")
    if additional.get("additionalProperties") is not False:
        errors.append("schema review entries must reject additional properties")

    properties = additional.get("properties")
    if not isinstance(properties, dict) or set(properties) != REVIEW_KEYS:
        errors.append("schema properties must match command review keys")
    return errors


def _run_case(path: Path, schema_errors: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "preflight",
            "--graph",
            str(path),
            "--command-review",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return _case_error(path, f"preflight output was not JSON: {exc}")

    errors = list(schema_errors)
    errors.extend(_validate_payload(payload))
    if proc.returncode != 0:
        errors.append(f"preflight exited {proc.returncode}")

    command_node_ids = payload.get("command_node_ids", []) if isinstance(payload, dict) else []
    command_review = payload.get("command_review", {}) if isinstance(payload, dict) else {}
    return {
        "fixture": path.name,
        "passed": not errors,
        "schema_valid": not errors,
        "commands_executed": payload.get("commands_executed")
        if isinstance(payload, dict)
        else None,
        "command_node_ids": command_node_ids,
        "review_node_ids": sorted(command_review) if isinstance(command_review, dict) else [],
        "errors": errors,
    }


def _validate_payload(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["preflight payload must be an object"]

    if payload.get("commands_executed") is not False:
        errors.append("commands_executed must be false")

    command_node_ids = payload.get("command_node_ids")
    if not isinstance(command_node_ids, list) or not all(
        isinstance(node_id, str) for node_id in command_node_ids
    ):
        errors.append("command_node_ids must be a list of strings")
        command_node_ids = []

    command_review = payload.get("command_review")
    if not isinstance(command_review, dict):
        errors.append("command_review must be an object")
        command_review = {}

    missing_review = sorted(set(command_node_ids) - set(command_review))
    extra_review = sorted(set(command_review) - set(command_node_ids))
    if missing_review:
        errors.append(f"missing command review entries: {missing_review}")
    if extra_review:
        errors.append(f"unexpected command review entries: {extra_review}")

    for node_id in sorted(set(command_node_ids) & set(command_review)):
        _validate_review_entry(node_id, command_review[node_id], errors)
    return errors


def _validate_review_entry(node_id: str, entry: Any, errors: list[str]) -> None:
    if not isinstance(entry, dict):
        errors.append(f"command_review.{node_id} must be an object")
        return

    missing = sorted(REVIEW_KEYS - set(entry))
    extra = sorted(set(entry) - REVIEW_KEYS)
    if missing:
        errors.append(f"command_review.{node_id} missing keys: {missing}")
    if extra:
        errors.append(f"command_review.{node_id} unexpected keys: {extra}")

    executable = entry.get("executable")
    argv_count = entry.get("argv_count")
    redacted_argv = entry.get("redacted_argv")
    argv_sha256 = entry.get("argv_sha256")

    if not isinstance(executable, str) or not executable:
        errors.append(f"command_review.{node_id}.executable must be a string")
    if type(argv_count) is not int or argv_count < 1:
        errors.append(f"command_review.{node_id}.argv_count must be positive")
    if not isinstance(redacted_argv, list) or not redacted_argv:
        errors.append(f"command_review.{node_id}.redacted_argv must be non-empty")
    elif not all(isinstance(item, str) for item in redacted_argv):
        errors.append(f"command_review.{node_id}.redacted_argv must be strings")
    elif argv_count != len(redacted_argv):
        errors.append(f"command_review.{node_id}.redacted_argv length mismatch")
    if not isinstance(argv_sha256, str) or not SHA256.fullmatch(argv_sha256):
        errors.append(f"command_review.{node_id}.argv_sha256 must be sha256 hex")


def _case_error(path: Path, error: str) -> dict[str, Any]:
    return {
        "fixture": path.name,
        "passed": False,
        "schema_valid": False,
        "commands_executed": None,
        "command_node_ids": [],
        "review_node_ids": [],
        "errors": [error],
    }


if __name__ == "__main__":
    raise SystemExit(main())
