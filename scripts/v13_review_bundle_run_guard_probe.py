#!/usr/bin/env python3
"""Verify saved review-bundle guards before local graph command execution."""

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
    with tempfile.TemporaryDirectory(prefix="agy-swarms-v13-") as tmp:
        tmp_path = Path(tmp)
        matching_case = _run_matching_case(tmp_path)
        mismatch_case = _run_mismatch_case(tmp_path)
        malformed_case = _run_malformed_case(tmp_path)
    passed = matching_case["passed"] and mismatch_case["passed"] and malformed_case["passed"]
    print(
        json.dumps(
            {
                "gate": "V13-AC4",
                "passed": passed,
                "matching_case": matching_case,
                "mismatch_case": mismatch_case,
                "malformed_case": malformed_case,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


def _run_matching_case(tmp_path: Path) -> dict[str, Any]:
    bundle = tmp_path / "bundle.json"
    errors: list[str] = []
    build = _build_bundle(FIXTURE, bundle)
    if build.returncode != 0:
        errors.append(build.stderr or build.stdout or f"bundle build exited {build.returncode}")

    run = _run_guarded_graph(FIXTURE, bundle)
    if run.returncode != 0:
        errors.append(run.stderr or run.stdout or f"guarded run exited {run.returncode}")

    payload: dict[str, Any] = {}
    if run.stdout:
        try:
            payload = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            errors.append(f"guarded run output is not JSON: {exc}")

    return {
        "passed": not errors and payload.get("status") == "succeeded",
        "run_succeeded": payload.get("status") == "succeeded",
        "states": payload.get("states", {}),
        "errors": errors,
    }


def _run_mismatch_case(tmp_path: Path) -> dict[str, Any]:
    bundle = tmp_path / "bundle.json"
    changed_graph = tmp_path / "changed-graph.json"
    marker = tmp_path / "marker.txt"
    errors: list[str] = []
    _write_changed_graph(changed_graph, marker)

    build = _build_bundle(FIXTURE, bundle)
    if build.returncode != 0:
        errors.append(build.stderr or build.stdout or f"bundle build exited {build.returncode}")

    run = _run_guarded_graph(changed_graph, bundle)
    diagnostic = run.stderr or run.stdout
    rejected = run.returncode == 1 and "review bundle does not match graph" in diagnostic
    redacted = "write_text" not in diagnostic and str(marker) not in diagnostic
    commands_executed = marker.exists()
    if not rejected:
        errors.append(diagnostic or f"mismatch run exited {run.returncode}")
    if not redacted:
        errors.append("mismatch diagnostic exposed changed command details")
    if commands_executed:
        errors.append("mismatched graph command executed")

    return {
        "passed": not errors and rejected and not commands_executed,
        "rejected_before_execution": rejected and not commands_executed,
        "commands_executed": commands_executed,
        "diagnostic_redacted": redacted,
        "errors": errors,
    }


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
    result = _run_guarded_graph(FIXTURE, malformed)
    diagnostic = result.stderr or result.stdout
    redacted = "secret-token-value" not in diagnostic and "/tmp/" not in diagnostic
    repairable = "repair:" in diagnostic
    return {
        "passed": result.returncode == 1 and redacted and repairable,
        "exit_code": result.returncode,
        "diagnostic_redacted": redacted,
        "repairable": repairable,
    }


def _build_bundle(graph: Path, bundle: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "preflight",
            "--graph",
            str(graph),
            "--review-bundle",
            "--output",
            str(bundle),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_guarded_graph(graph: Path, bundle: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "agy_swarms.main",
            "run",
            "--graph",
            str(graph),
            "--allow-local-commands",
            "--require-review-bundle",
            str(bundle),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_changed_graph(destination: Path, marker: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for node in payload["nodes"]:
        if node["id"] == "verify":
            node["command"] = [
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            ]
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
