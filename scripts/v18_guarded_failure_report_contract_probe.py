#!/usr/bin/env python3
"""Validate guarded failed local-runner reports against the full report schema."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agy_swarms.graph_io import load_graph
from agy_swarms.review_bundle import write_review_bundle


ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "tests" / "fixtures" / "local_runner" / "failure-graph.json"
SCHEMA_PATH = ROOT / "schemas" / "local-runner-report-v1.schema.json"


def _run_cli(
    args: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


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


def _load_report(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.exists():
        return {}, "guarded failure report was not written"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"guarded failure report was not JSON: {exc}"
    if not isinstance(payload, dict):
        return {}, "guarded failure report was not an object"
    return payload, None


def _write_guarded_failure_report(workdir: Path) -> tuple[Path, list[str]]:
    errors: list[str] = []
    bundle_path = workdir / "review-bundle.json"
    report_path = workdir / "guarded-failure-report.json"
    write_review_bundle(
        load_graph(str(GRAPH_PATH)),
        graph_path=str(GRAPH_PATH),
        output_path=bundle_path,
    )

    proc = _run_cli(
        [
            "run",
            "--graph",
            str(GRAPH_PATH),
            "--allow-local-commands",
            "--require-review-bundle",
            str(bundle_path),
            "--report",
            str(report_path),
        ]
    )
    if proc.returncode != 0 and not report_path.exists():
        errors.append(proc.stderr or proc.stdout or "guarded failure run failed")
    return report_path, errors


def _resume_with_command_guard(
    report_path: Path, workdir: Path
) -> tuple[dict[str, Any], bool, str | None]:
    guard_dir = workdir / "resume-command-guard"
    guard_dir.mkdir(exist_ok=True)
    sentinel = workdir / "resume-command-executed.txt"

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
    payload, error = _load_cli_json(
        _run_cli(["resume", "--checkpoint", str(report_path)], env=env),
        "resume",
    )
    return payload, not sentinel.exists(), error


def _validate_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _validate_value(value: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, str):
        if not _validate_type(value, expected_type):
            return [f"expected {expected_type}"]
    elif isinstance(expected_type, list):
        if not any(isinstance(item, str) and _validate_type(value, item) for item in expected_type):
            return [f"expected one of {expected_type}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"expected one of {schema['enum']!r}")

    if isinstance(value, dict):
        errors.extend(_validate_object(value, schema))
    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(f"{idx}.{error}" for error in _validate_value(item, item_schema))

    minimum = schema.get("minimum")
    if isinstance(minimum, int | float) and isinstance(value, int | float) and value < minimum:
        errors.append(f"expected minimum {minimum}")
    return errors


def _validate_object(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in schema.get("required", []):
        if key not in payload:
            errors.append(f"missing {key}")

    properties = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)
    for key, value in payload.items():
        spec = properties.get(key)
        if spec is None:
            if additional is False:
                errors.append(f"unexpected {key}")
            elif isinstance(additional, dict):
                errors.extend(f"{key}.{error}" for error in _validate_value(value, additional))
            continue
        errors.extend(f"{key}.{error}" for error in _validate_value(value, spec))
    return errors


def _validate_report(payload: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = _validate_value(payload, schema)
    return not errors, errors


def _validate_guarded_failure_report(report: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if report.get("status") != "failed":
        errors.append(f"report status was {report.get('status')!r}, expected 'failed'")
    if not _failed_nodes(report):
        errors.append("failed guarded report must include failed_nodes")

    guard = report.get("review_bundle_guard")
    if not isinstance(guard, dict):
        return False, [*errors, "missing review_bundle_guard"]

    expected = {
        "kind": "review_bundle_run_guard",
        "graph_sha256_match": True,
        "review_complete": True,
        "commands_executed": False,
        "guarded_run": True,
        "missing_command_reviews": [],
        "mismatched_command_reviews": [],
    }
    for key, value in expected.items():
        if guard.get(key) != value:
            errors.append(f"review_bundle_guard.{key} was {guard.get(key)!r}")
    for key in ("graph_sha256", "bundle_graph_sha256"):
        digest = guard.get(key)
        if not isinstance(digest, str) or len(digest) != 64:
            errors.append(f"review_bundle_guard.{key} was not a sha256 digest")
    return not errors, errors


def _failed_nodes(report: dict[str, Any]) -> list[str]:
    states = report.get("states", {})
    if not isinstance(states, dict):
        return []
    return [str(node_id) for node_id, state in states.items() if state == "failed"]


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: dict[str, list[str]] = {
        "guarded_failure_report": [],
        "inspect_resume": [],
    }
    with tempfile.TemporaryDirectory(prefix="agy-v18-guarded-failure-report-") as tmp:
        workdir = Path(tmp)
        report_path, write_errors = _write_guarded_failure_report(workdir)
        errors["guarded_failure_report"].extend(write_errors)

        report, load_error = _load_report(report_path)
        if load_error:
            errors["guarded_failure_report"].append(load_error)

        schema_valid, schema_errors = _validate_report(report, schema)
        guard_valid, guard_errors = _validate_guarded_failure_report(report)
        errors["guarded_failure_report"].extend(schema_errors)
        errors["guarded_failure_report"].extend(guard_errors)

        inspect_payload, inspect_error = _load_cli_json(
            _run_cli(["inspect", "--checkpoint", str(report_path)]),
            "inspect",
        )
        resume_payload, resume_did_not_execute, resume_error = _resume_with_command_guard(
            report_path, workdir
        )
        if inspect_error:
            errors["inspect_resume"].append(inspect_error)
        if resume_error:
            errors["inspect_resume"].append(resume_error)

    guard = report.get("review_bundle_guard", {})
    failed_nodes = _failed_nodes(report)
    inspect_summary = inspect_payload.get("summary", {}).get("guarded_report", {})
    resume_summary = resume_payload.get("summary", {}).get("guarded_report", {})
    inspect_resume_summary_match = bool(inspect_summary) and inspect_summary == resume_summary
    if not inspect_resume_summary_match:
        errors["inspect_resume"].append("inspect/resume guarded summaries differed")
    if not resume_did_not_execute:
        errors["inspect_resume"].append("resume attempted local command execution")

    passed = (
        schema_valid and guard_valid and inspect_resume_summary_match and resume_did_not_execute
    )
    print(
        json.dumps(
            {
                "gate": "V18-AC1/V18-AC2/V18-AC3/V18-AC4",
                "passed": passed,
                "schema": SCHEMA_PATH.as_posix(),
                "guarded_failure_report_schema_valid": schema_valid,
                "status": report.get("status"),
                "failed_nodes": failed_nodes,
                "guarded_report_has_guard": isinstance(guard, dict) and bool(guard),
                "guarded_run": guard.get("guarded_run") if isinstance(guard, dict) else None,
                "guard_commands_executed": guard.get("commands_executed")
                if isinstance(guard, dict)
                else None,
                "guard_evidence_valid": guard_valid,
                "inspect_resume_summary_match": inspect_resume_summary_match,
                "resume_did_not_execute_commands": resume_did_not_execute,
                "errors": errors,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
