#!/usr/bin/env python3
"""V04-AC1/V04-AC2 deterministic replay probe for tracked local-runner fixtures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


FIXTURES = {
    "success": {
        "path": Path("tests/fixtures/local_runner/success-graph.json"),
        "report_name": "success-report.json",
        "expected_returncode": 0,
        "expected_status": "succeeded",
        "expected_states": {
            "prepare": "succeeded",
            "verify": "succeeded",
        },
        "expected_stdout": {
            "prepare": "fixture-success:prepare",
            "verify": "fixture-success:verify",
        },
        "expected_summary": {
            "total_nodes": 2,
            "status_counts": {"succeeded": 2},
            "failed_nodes": [],
            "skipped_nodes": [],
            "blocker_count": 0,
            "concern_count": 0,
            "changed_files_count": 0,
        },
    },
    "failure": {
        "path": Path("tests/fixtures/local_runner/failure-graph.json"),
        "report_name": "failure-report.json",
        "expected_returncode": 1,
        "expected_status": "failed",
        "expected_states": {
            "prepare": "succeeded",
            "unit": "failed",
            "integration": "skipped",
        },
        "expected_stdout": {
            "prepare": "fixture-failure:prepare",
            "unit": "fixture-failure:unit",
        },
        "expected_summary": {
            "total_nodes": 3,
            "status_counts": {
                "failed": 1,
                "skipped": 1,
                "succeeded": 1,
            },
            "failed_nodes": ["unit"],
            "skipped_nodes": ["integration"],
            "blocker_count": 2,
            "concern_count": 0,
            "changed_files_count": 0,
        },
    },
    "dependency_skip": {
        "path": Path("tests/fixtures/local_runner/dependency-skip-graph.json"),
        "report_name": "dependency-skip-report.json",
        "expected_returncode": 1,
        "expected_status": "failed",
        "expected_states": {
            "root": "succeeded",
            "lint": "failed",
            "docs": "skipped",
            "package": "skipped",
        },
        "expected_stdout": {
            "root": "fixture-dependency-skip:root",
            "lint": "fixture-dependency-skip:lint",
        },
        "expected_missing_results": ["docs", "package"],
        "expected_summary": {
            "total_nodes": 4,
            "status_counts": {
                "failed": 1,
                "skipped": 2,
                "succeeded": 1,
            },
            "failed_nodes": ["lint"],
            "skipped_nodes": ["docs", "package"],
            "blocker_count": 3,
            "concern_count": 0,
            "changed_files_count": 0,
        },
    },
}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agy-v04-fixture-replay-") as tmp:
        results = {
            name: _run_fixture(name, fixture, Path(tmp)) for name, fixture in FIXTURES.items()
        }
        passed = all(result["passed"] for result in results.values())
        print(
            json.dumps(
                {
                    "gate": "V04-AC1/V04-AC2/V04-AC3",
                    "passed": passed,
                    "fixtures": results,
                },
                indent=2,
            )
        )
        return 0 if passed else 1


def _run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        capture_output=True,
        env=env,
        text=True,
    )


def _run_fixture(name: str, fixture: dict[str, Any], tmp: Path) -> dict[str, Any]:
    path = fixture["path"]
    report = tmp / fixture["report_name"]
    run_proc = _run_cli(
        "run",
        "--graph",
        str(path),
        "--allow-local-commands",
        "--report",
        str(report),
    )

    try:
        run_payload = json.loads(run_proc.stdout)
    except json.JSONDecodeError as exc:
        return _failed_fixture_result(name, path, f"run output was not JSON: {exc}")

    inspect_proc = _run_cli("inspect", "--checkpoint", str(report))
    if inspect_proc.returncode != 0:
        return _failed_fixture_result(name, path, inspect_proc.stderr or inspect_proc.stdout)

    try:
        inspect_payload = json.loads(inspect_proc.stdout)
    except json.JSONDecodeError as exc:
        return _failed_fixture_result(name, path, f"inspect output was not JSON: {exc}")

    resume_proc, resume_did_not_execute_commands = _resume_with_command_guard(report, tmp)
    if resume_proc.returncode != 0:
        return _failed_fixture_result(name, path, resume_proc.stderr or resume_proc.stdout)

    try:
        resume_payload = json.loads(resume_proc.stdout)
    except json.JSONDecodeError as exc:
        return _failed_fixture_result(name, path, f"resume output was not JSON: {exc}")

    passed = (
        report.exists()
        and run_proc.returncode == fixture["expected_returncode"]
        and run_payload.get("status") == fixture["expected_status"]
        and run_payload.get("states") == fixture["expected_states"]
        and _stdout_matches(run_payload, fixture["expected_stdout"])
        and _missing_results_match(run_payload, fixture.get("expected_missing_results", []))
        and inspect_payload.get("kind") == "run_report"
        and inspect_payload.get("summary") == fixture["expected_summary"]
        and resume_payload.get("status") == "resume_loaded"
        and resume_payload.get("source_status") == fixture["expected_status"]
        and resume_payload.get("states") == fixture["expected_states"]
        and resume_payload.get("summary") == inspect_payload.get("summary")
        and resume_did_not_execute_commands
    )
    return {
        "fixture": str(path),
        "passed": passed,
        "resume_status": resume_payload.get("status"),
        "resume_did_not_execute_commands": resume_did_not_execute_commands,
        "status": run_payload.get("status"),
        "states": run_payload.get("states"),
        "summary": inspect_payload.get("summary"),
        "resume_summary": resume_payload.get("summary"),
    }


def _resume_with_command_guard(
    report: Path, tmp: Path
) -> tuple[subprocess.CompletedProcess[str], bool]:
    guard_dir = tmp / "resume-command-guard"
    guard_dir.mkdir(exist_ok=True)
    sentinel = tmp / "resume-command-executed.txt"

    fake_python_unix = (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"Path(r{str(sentinel)!r}).write_text('resume attempted command execution', encoding='utf-8')\n"
        "sys.exit(97)\n"
    )

    fake_python_windows = (
        f'@echo off\necho resume attempted command execution > "{sentinel}"\nexit /b 97\n'
    )

    for name in ("python", "python3"):
        unix_file = guard_dir / name
        unix_file.write_text(fake_python_unix, encoding="utf-8")
        unix_file.chmod(0o755)

        win_file = guard_dir / f"{name}.bat"
        win_file.write_text(fake_python_windows, encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{guard_dir}{os.pathsep}{env.get('PATH', '')}"
    proc = _run_cli("resume", "--checkpoint", str(report), env=env)
    return proc, not sentinel.exists()


def _stdout_matches(run_payload: dict[str, Any], expected_stdout: dict[str, str]) -> bool:
    results = run_payload.get("results", {})
    if not isinstance(results, dict):
        return False
    return all(
        results.get(node_id, {}).get("stdout", "").strip() == expected
        for node_id, expected in expected_stdout.items()
    )


def _missing_results_match(
    run_payload: dict[str, Any], expected_missing_results: list[str]
) -> bool:
    results = run_payload.get("results", {})
    if not isinstance(results, dict):
        return False
    return all(node_id not in results for node_id in expected_missing_results)


def _failed_fixture_result(name: str, path: Path, error: str) -> dict[str, Any]:
    return {
        "fixture": str(path),
        "passed": False,
        "status": "probe_error",
        "states": {},
        "summary": {},
        "error": error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
