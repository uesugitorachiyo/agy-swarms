#!/usr/bin/env python3
"""Diff deterministic local review bundles without executing commands."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "local_runner" / "success-graph.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agy-swarms-v12-") as tmp:
        tmp_path = Path(tmp)
        diff_case = _run_diff_case(tmp_path)
        malformed_case = _run_malformed_case(tmp_path)
    passed = diff_case["passed"] and malformed_case["passed"]
    print(
        json.dumps(
            {
                "gate": "V12-AC4",
                "passed": passed,
                "diff_case": diff_case,
                "malformed_case": malformed_case,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


def _run_diff_case(tmp_path: Path) -> dict[str, Any]:
    before_bundle = tmp_path / "before-bundle.json"
    after_graph = tmp_path / "after-graph.json"
    after_bundle = tmp_path / "after-bundle.json"
    errors: list[str] = []

    _write_modified_graph(after_graph)
    for graph_path, bundle_path in (
        (FIXTURE, before_bundle),
        (after_graph, after_bundle),
    ):
        build = subprocess.run(
            [
                sys.executable,
                "-m",
                "agy_swarms.main",
                "preflight",
                "--graph",
                str(graph_path),
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

    first = _diff_bundles(before_bundle, after_bundle)
    second = _diff_bundles(before_bundle, after_bundle)
    if first.returncode != 0:
        errors.append(first.stderr or first.stdout or f"diff exited {first.returncode}")
    if second.returncode != 0:
        errors.append(second.stderr or second.stdout or f"diff exited {second.returncode}")

    byte_stable = first.stdout == second.stdout and bool(first.stdout)
    if not byte_stable:
        errors.append("diff summary output must be byte-stable")

    try:
        payload = json.loads(first.stdout)
    except json.JSONDecodeError as exc:
        return _diff_case_error(errors + [f"diff summary is not JSON: {exc}"])

    if payload.get("commands_executed") is not False:
        errors.append("commands_executed must be false")
    if payload.get("graph_changed") is not True:
        errors.append("graph_changed must be true")

    command_changes = payload.get("command_changes", {})
    if command_changes.get("added") != ["audit"]:
        errors.append("expected audit command node to be added")
    if command_changes.get("changed") != ["verify"]:
        errors.append("expected verify command digest to change")
    if command_changes.get("unchanged") != ["prepare"]:
        errors.append("expected prepare command digest to be unchanged")

    return {
        "passed": not errors,
        "byte_stable": byte_stable,
        "commands_executed": payload.get("commands_executed"),
        "graph_changed": payload.get("graph_changed"),
        "command_changes": command_changes,
        "errors": errors,
    }


def _write_modified_graph(destination: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for node in payload["nodes"]:
        if node["id"] == "verify":
            node["command"] = ["python", "-c", "print('fixture-success:changed')"]
    payload["nodes"].append(
        {
            "id": "audit",
            "role": "verify",
            "objective": "emit deterministic fixture audit evidence",
            "dependencies": ["verify"],
            "command": ["python", "-c", "print('fixture-success:audit')"],
        }
    )
    payload["edges"].append(["verify", "audit"])
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _diff_bundles(before: Path, after: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "inspect",
            "--review-bundle-diff",
            str(before),
            str(after),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_malformed_case(tmp_path: Path) -> dict[str, Any]:
    malformed = tmp_path / "malformed.json"
    valid = tmp_path / "valid.json"
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
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "preflight",
            "--graph",
            str(FIXTURE),
            "--review-bundle",
            "--output",
            str(valid),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    result = _diff_bundles(malformed, valid)
    diagnostic = result.stderr or result.stdout
    redacted = "secret-token-value" not in diagnostic and "/tmp/" not in diagnostic
    repairable = "repair:" in diagnostic
    return {
        "passed": build.returncode == 0 and result.returncode == 1 and redacted and repairable,
        "exit_code": result.returncode,
        "diagnostic_redacted": redacted,
        "repairable": repairable,
    }


def _diff_case_error(errors: list[str]) -> dict[str, Any]:
    return {
        "passed": False,
        "byte_stable": False,
        "commands_executed": None,
        "graph_changed": None,
        "command_changes": {},
        "errors": errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
