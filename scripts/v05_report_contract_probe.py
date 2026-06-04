#!/usr/bin/env python3
"""Validate tracked local-runner fixture reports against the v0.5 report contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_PATH = Path("schemas/local-runner-report-v1.schema.json")
FIXTURES = [
    Path("tests/fixtures/local_runner/success-graph.json"),
    Path("tests/fixtures/local_runner/failure-graph.json"),
    Path("tests/fixtures/local_runner/dependency-skip-graph.json"),
]
STATE_VALUES = {
    "pending",
    "ready",
    "reserved",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "cancelled",
}
RESULT_STATUS_VALUES = {"succeeded", "failed", "cancelled", "timed_out"}
TOP_LEVEL_KEYS = {
    "status",
    "states",
    "blockers",
    "spent_tokens",
    "spent_usd",
    "concerns",
    "changed_files",
    "results",
}
RESULT_KEYS = {"status", "error_class", "artifact", "stdout", "stderr", "exit_code"}


def main() -> int:
    schema = _load_schema()
    with tempfile.TemporaryDirectory(prefix="agy-v05-report-contract-") as tmp:
        cases = [_run_case(fixture, Path(tmp), schema) for fixture in FIXTURES]

    passed = all(case["passed"] for case in cases)
    print(
        json.dumps(
            {
                "gate": "V05-AC1/V05-AC2/V05-AC3",
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


def _run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        capture_output=True,
        env=env,
        text=True,
    )


def _run_case(fixture: Path, tmp: Path, schema: dict[str, Any]) -> dict[str, Any]:
    report_path = tmp / f"{fixture.stem}-report.json"
    proc = _run_cli(
        "run",
        "--graph",
        str(fixture),
        "--allow-local-commands",
        "--report",
        str(report_path),
    )

    if not report_path.exists():
        return _case_error(fixture, "report was not written", proc)

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _case_error(fixture, f"report was not JSON: {exc}", proc)

    validation_errors = _validate_report(report, schema)
    expected_returncode = 0 if report.get("status") == "succeeded" else 1
    inspect_payload, inspect_error = _load_cli_json(
        _run_cli("inspect", "--checkpoint", str(report_path)), "inspect"
    )
    resume_proc, resume_did_not_execute_commands = _resume_with_command_guard(report_path, tmp)
    resume_payload, resume_error = _load_cli_json(resume_proc, "resume")

    inspect_summary_keys = _summary_keys(inspect_payload)
    resume_summary_keys = _summary_keys(resume_payload)
    resume_status = resume_payload.get("status") if isinstance(resume_payload, dict) else None
    contract_errors = [error for error in (inspect_error, resume_error) if error is not None]
    if resume_status != "resume_loaded":
        contract_errors.append(f"resume status was {resume_status!r}")
    if inspect_summary_keys != resume_summary_keys:
        contract_errors.append("inspect/resume summary keys differed")
    if not resume_did_not_execute_commands:
        contract_errors.append("resume attempted local command execution")

    passed = (
        not validation_errors and not contract_errors and proc.returncode == expected_returncode
    )

    return {
        "fixture": fixture.name,
        "passed": passed,
        "schema_valid": not validation_errors,
        "status": report.get("status"),
        "states": report.get("states", {}),
        "result_nodes": sorted(report.get("results", {}).keys())
        if isinstance(report.get("results"), dict)
        else [],
        "validation_errors": validation_errors,
        "contract_errors": contract_errors,
        "inspect_summary_keys": inspect_summary_keys,
        "resume_status": resume_status,
        "resume_summary_keys": resume_summary_keys,
        "resume_did_not_execute_commands": resume_did_not_execute_commands,
        "returncode": proc.returncode,
    }


def _load_cli_json(
    proc: subprocess.CompletedProcess[str], label: str
) -> tuple[dict[str, Any], str | None]:
    if proc.returncode != 0:
        return {}, f"{label} failed: {proc.stderr or proc.stdout}"
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {}, f"{label} output was not JSON: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{label} output was not an object"
    return payload, None


def _summary_keys(payload: dict[str, Any]) -> list[str]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return []
    return sorted(summary)


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


def _validate_report(report: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report must be an object"]

    if schema.get("$id") != ("https://agy-swarms.local/schemas/local-runner-report-v1.schema.json"):
        errors.append("schema id mismatch")

    missing = sorted(TOP_LEVEL_KEYS - set(report))
    if missing:
        errors.append(f"missing top-level keys: {missing}")

    extra = sorted(set(report) - TOP_LEVEL_KEYS)
    if extra:
        errors.append(f"unexpected top-level keys: {extra}")

    if report.get("status") not in {"succeeded", "failed"}:
        errors.append("status must be succeeded or failed")

    states = report.get("states")
    if not isinstance(states, dict):
        errors.append("states must be an object")
    else:
        for node_id, state in states.items():
            if not isinstance(node_id, str) or state not in STATE_VALUES:
                errors.append(f"invalid state for node {node_id!r}: {state!r}")

    _validate_list(report, "blockers", dict, errors)
    _validate_list(report, "concerns", str, errors)
    _validate_list(report, "changed_files", str, errors)

    if not isinstance(report.get("spent_tokens"), int) or report["spent_tokens"] < 0:
        errors.append("spent_tokens must be a non-negative integer")

    spent_usd = report.get("spent_usd")
    if not isinstance(spent_usd, int | float) or spent_usd < 0:
        errors.append("spent_usd must be a non-negative number")

    results = report.get("results")
    if not isinstance(results, dict):
        errors.append("results must be an object")
    else:
        for node_id, result in results.items():
            errors.extend(_validate_result(str(node_id), result))

    return errors


def _validate_list(report: dict[str, Any], key: str, item_type: type, errors: list[str]) -> None:
    value = report.get(key)
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return
    if not all(isinstance(item, item_type) for item in value):
        errors.append(f"{key} contains non-{item_type.__name__} entries")


def _validate_result(node_id: str, result: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return [f"result {node_id} must be an object"]

    missing = sorted(RESULT_KEYS - set(result))
    if missing:
        errors.append(f"result {node_id} missing keys: {missing}")

    extra = sorted(set(result) - RESULT_KEYS)
    if extra:
        errors.append(f"result {node_id} unexpected keys: {extra}")

    if result.get("status") not in RESULT_STATUS_VALUES:
        errors.append(f"result {node_id} has invalid status")
    if not isinstance(result.get("error_class"), str):
        errors.append(f"result {node_id} error_class must be a string")
    if not isinstance(result.get("artifact"), dict):
        errors.append(f"result {node_id} artifact must be an object")
    if not isinstance(result.get("stdout"), str):
        errors.append(f"result {node_id} stdout must be a string")
    if not isinstance(result.get("stderr"), str):
        errors.append(f"result {node_id} stderr must be a string")
    if not (isinstance(result.get("exit_code"), int) or result.get("exit_code") is None):
        errors.append(f"result {node_id} exit_code must be an integer or null")
    return errors


def _case_error(
    fixture: Path, error: str, proc: subprocess.CompletedProcess[str]
) -> dict[str, Any]:
    return {
        "fixture": fixture.name,
        "passed": False,
        "schema_valid": False,
        "status": "probe_error",
        "states": {},
        "result_nodes": [],
        "validation_errors": [error],
        "contract_errors": [],
        "inspect_summary_keys": [],
        "resume_status": None,
        "resume_summary_keys": [],
        "resume_did_not_execute_commands": False,
        "returncode": proc.returncode,
    }


if __name__ == "__main__":
    raise SystemExit(main())
