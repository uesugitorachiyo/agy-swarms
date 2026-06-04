#!/usr/bin/env python3
"""Build and validate deterministic local review bundles for tracked fixtures."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "local-review-bundle-v1.schema.json"
FIXTURES = [
    ROOT / "tests" / "fixtures" / "local_runner" / "success-graph.json",
    ROOT / "tests" / "fixtures" / "local_runner" / "failure-graph.json",
    ROOT / "tests" / "fixtures" / "local_runner" / "dependency-skip-graph.json",
]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def main() -> int:
    schema_errors = _validate_schema_file()
    with tempfile.TemporaryDirectory(prefix="agy-swarms-v10-") as tmp:
        tmp_path = Path(tmp)
        cases = [_run_case(path, tmp_path, schema_errors) for path in FIXTURES]
    passed = not schema_errors and all(case["passed"] for case in cases)
    print(
        json.dumps(
            {
                "gate": "V10-AC4",
                "passed": passed,
                "schema": "schemas/local-review-bundle-v1.schema.json",
                "schema_errors": schema_errors,
                "cases": cases,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


def _validate_schema_file() -> list[str]:
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"schema file missing or unreadable: {exc}"]
    except json.JSONDecodeError as exc:
        return [f"schema file is not valid JSON: {exc}"]

    errors: list[str] = []
    if schema.get("$id") != ("https://agy-swarms.local/schemas/local-review-bundle-v1.schema.json"):
        errors.append("schema $id must match local-review-bundle-v1")
    if schema.get("type") != "object":
        errors.append("schema root type must be object")

    required = set(schema.get("required", []))
    expected = {
        "format",
        "schema_version",
        "graph_path",
        "graph_sha256",
        "schemas",
        "commands_executed",
        "preflight",
        "review_bundle",
    }
    if required != expected:
        errors.append("schema required keys must match review bundle keys")
    return errors


def _run_case(path: Path, tmp_path: Path, schema_errors: list[str]) -> dict[str, Any]:
    first = tmp_path / f"{path.stem}-first.json"
    second = tmp_path / f"{path.stem}-second.json"
    errors = list(schema_errors)
    for output in (first, second):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "agy_swarms.main",
                "preflight",
                "--graph",
                str(path),
                "--review-bundle",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            errors.append(proc.stderr or proc.stdout or f"preflight exited {proc.returncode}")

    byte_stable = (
        first.read_bytes() == second.read_bytes() if first.exists() and second.exists() else False
    )
    if not byte_stable:
        errors.append("review bundle output must be byte-stable")

    try:
        payload = json.loads(first.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _case_error(path, errors + [f"bundle output unreadable: {exc}"])

    errors.extend(_validate_payload(payload))
    return {
        "fixture": path.name,
        "passed": not errors,
        "schema_valid": not errors,
        "commands_executed": payload.get("commands_executed"),
        "byte_stable": byte_stable,
        "errors": errors,
    }


def _validate_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["bundle payload must be an object"]

    errors: list[str] = []
    if payload.get("format") != "local-review-bundle":
        errors.append("format must be local-review-bundle")
    if payload.get("schema_version") != "v1":
        errors.append("schema_version must be v1")

    graph_sha256 = payload.get("graph_sha256")
    if not isinstance(graph_sha256, str) or not SHA256.fullmatch(graph_sha256):
        errors.append("graph_sha256 must be lowercase SHA-256 hex")
    if payload.get("commands_executed") is not False:
        errors.append("commands_executed must be false")

    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        errors.append("preflight must be an object")
        preflight = {}
    if preflight.get("commands_executed") is not False:
        errors.append("preflight.commands_executed must be false")
    if "command_review" not in preflight:
        errors.append("preflight.command_review is required")

    review_bundle = payload.get("review_bundle")
    if not isinstance(review_bundle, dict):
        errors.append("review_bundle must be an object")
        review_bundle = {}
    if review_bundle.get("review_complete") is not True:
        errors.append("review_bundle.review_complete must be true")
    return errors


def _case_error(path: Path, errors: list[str]) -> dict[str, Any]:
    return {
        "fixture": path.name,
        "passed": False,
        "schema_valid": False,
        "commands_executed": None,
        "byte_stable": False,
        "errors": errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
