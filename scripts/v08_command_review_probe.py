#!/usr/bin/env python3
"""Validate opt-in local command review preflight evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


FIXTURES = [
    Path("tests/fixtures/local_runner/success-graph.json"),
    Path("tests/fixtures/local_runner/failure-graph.json"),
    Path("tests/fixtures/local_runner/dependency-skip-graph.json"),
]
REVIEW_KEYS = {"executable", "argv_count", "redacted_argv", "argv_sha256"}


def main() -> int:
    cases = [_run_case(path) for path in FIXTURES]
    passed = all(case["passed"] for case in cases)
    print(
        json.dumps(
            {
                "gate": "V08-AC4",
                "passed": passed,
                "cases": cases,
            },
            indent=2,
        )
    )
    return 0 if passed else 1


def _run_case(path: Path) -> dict[str, Any]:
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
        capture_output=True,
        text=True,
    )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return _case_error(path, f"preflight output was not JSON: {exc}")

    errors = _validate_payload(payload)
    if proc.returncode != 0:
        errors.append(f"preflight exited {proc.returncode}")

    command_node_ids = payload.get("command_node_ids", []) if isinstance(payload, dict) else []
    return {
        "fixture": path.name,
        "passed": not errors,
        "command_node_ids": command_node_ids,
        "commands_executed": payload.get("commands_executed")
        if isinstance(payload, dict)
        else None,
        "command_review_valid": not errors,
        "validation_errors": errors,
    }


def _validate_payload(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["preflight payload must be an object"]
    if payload.get("commands_executed") is not False:
        errors.append("commands_executed must be false")

    command_node_ids = payload.get("command_node_ids")
    command_review = payload.get("command_review")
    if not isinstance(command_node_ids, list) or not all(
        isinstance(item, str) for item in command_node_ids
    ):
        errors.append("command_node_ids must be a list of strings")
        command_node_ids = []
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
    if type(argv_count) is not int or argv_count <= 0:
        errors.append(f"command_review.{node_id}.argv_count must be positive")
    if not isinstance(redacted_argv, list) or not all(
        isinstance(item, str) for item in redacted_argv
    ):
        errors.append(f"command_review.{node_id}.redacted_argv must be strings")
    elif argv_count != len(redacted_argv):
        errors.append(f"command_review.{node_id}.redacted_argv length mismatch")
    if (
        not isinstance(argv_sha256, str)
        or len(argv_sha256) != 64
        or any(char not in "0123456789abcdef" for char in argv_sha256)
    ):
        errors.append(f"command_review.{node_id}.argv_sha256 must be sha256 hex")


def _case_error(path: Path, error: str) -> dict[str, Any]:
    return {
        "fixture": path.name,
        "passed": False,
        "command_node_ids": [],
        "commands_executed": None,
        "command_review_valid": False,
        "validation_errors": [error],
    }


if __name__ == "__main__":
    raise SystemExit(main())
