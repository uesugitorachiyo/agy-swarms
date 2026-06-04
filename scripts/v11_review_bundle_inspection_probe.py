#!/usr/bin/env python3
"""Inspect deterministic local review bundles for tracked fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = [
    ROOT / "tests" / "fixtures" / "local_runner" / "success-graph.json",
    ROOT / "tests" / "fixtures" / "local_runner" / "failure-graph.json",
    ROOT / "tests" / "fixtures" / "local_runner" / "dependency-skip-graph.json",
]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agy-swarms-v11-") as tmp:
        tmp_path = Path(tmp)
        cases = [_run_case(path, tmp_path) for path in FIXTURES]
        malformed_case = _run_malformed_case(tmp_path)
    passed = all(case["passed"] for case in cases) and malformed_case["passed"]
    print(
        json.dumps(
            {
                "gate": "V11-AC4",
                "passed": passed,
                "cases": cases,
                "malformed_case": malformed_case,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


def _run_case(path: Path, tmp_path: Path) -> dict[str, Any]:
    bundle_path = tmp_path / f"{path.stem}-bundle.json"
    errors: list[str] = []
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "preflight",
            "--graph",
            str(path),
            "--review-bundle",
            "--output",
            str(bundle_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        errors.append(build.stderr or build.stdout or f"bundle build exited {build.returncode}")

    first = _inspect_bundle(bundle_path)
    second = _inspect_bundle(bundle_path)
    if first.returncode != 0:
        errors.append(first.stderr or first.stdout or f"inspect exited {first.returncode}")
    if second.returncode != 0:
        errors.append(second.stderr or second.stdout or f"inspect exited {second.returncode}")

    byte_stable = first.stdout == second.stdout and bool(first.stdout)
    if not byte_stable:
        errors.append("inspection summary output must be byte-stable")

    try:
        payload = json.loads(first.stdout)
    except json.JSONDecodeError as exc:
        return _case_error(path, errors + [f"inspection summary is not JSON: {exc}"])

    if payload.get("commands_executed") is not False:
        errors.append("commands_executed must be false")
    if payload.get("review_complete") is not True:
        errors.append("review_complete must be true")
    return {
        "fixture": path.name,
        "passed": not errors,
        "byte_stable": byte_stable,
        "commands_executed": payload.get("commands_executed"),
        "review_complete": payload.get("review_complete"),
        "errors": errors,
    }


def _inspect_bundle(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "inspect",
            "--review-bundle",
            str(path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_malformed_case(tmp_path: Path) -> dict[str, Any]:
    malformed = tmp_path / "malformed.json"
    malformed.write_text(
        json.dumps(
            {
                "format": "local-review-bundle",
                "schema_version": "v1",
                "graph_path": "/tmp/secret-token-value/graph.json",
                "commands_executed": False,
            }
        ),
        encoding="utf-8",
    )
    result = _inspect_bundle(malformed)
    diagnostic = result.stderr or result.stdout
    redacted = "secret-token-value" not in diagnostic and "/tmp/" not in diagnostic
    repairable = "repair:" in diagnostic
    return {
        "passed": result.returncode == 1 and redacted and repairable,
        "exit_code": result.returncode,
        "diagnostic_redacted": redacted,
        "repairable": repairable,
    }


def _case_error(path: Path, errors: list[str]) -> dict[str, Any]:
    return {
        "fixture": path.name,
        "passed": False,
        "byte_stable": False,
        "commands_executed": None,
        "review_complete": None,
        "errors": errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
