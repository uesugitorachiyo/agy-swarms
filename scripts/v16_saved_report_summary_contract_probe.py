#!/usr/bin/env python3
"""Validate saved-report inspect/resume summaries against the local schema."""

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
GRAPH_PATH = ROOT / "tests" / "fixtures" / "local_runner" / "success-graph.json"
SCHEMA_PATH = ROOT / "schemas" / "local-runner-summary-v1.schema.json"


def _run_cli(args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def _validate_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _validate_object(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in schema.get("required", []):
        if key not in payload:
            errors.append(f"missing {key}")

    properties = schema.get("properties", {})
    additional = schema.get("additionalProperties")
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


def _validate_value(value: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _validate_type(value, expected_type):
        return [f"expected {expected_type}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"expected const {schema['const']!r}")
    if expected_type == "object" and isinstance(value, dict):
        errors.extend(_validate_object(value, schema))
    if expected_type == "array" and isinstance(value, list):
        item_type = schema.get("items", {}).get("type")
        if isinstance(item_type, str):
            for idx, item in enumerate(value):
                if not _validate_type(item, item_type):
                    errors.append(f"{idx} expected {item_type}")
    minimum = schema.get("minimum")
    if isinstance(minimum, int | float) and isinstance(value, int | float):
        if value < minimum:
            errors.append(f"expected minimum {minimum}")
    return errors


def _validate(payload: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, list[str]]:
    errors = _validate_object(payload, schema)
    return not errors, errors


def _write_guarded_report(workdir: Path) -> Path:
    bundle_path = workdir / "review-bundle.json"
    report_path = workdir / "guarded-report.json"
    write_review_bundle(
        load_graph(str(GRAPH_PATH)),
        graph_path=str(GRAPH_PATH),
        output_path=bundle_path,
    )
    _run_cli(
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
    return report_path


def _write_unguarded_report(workdir: Path) -> Path:
    report_path = workdir / "unguarded-report.json"
    _run_cli(
        [
            "run",
            "--graph",
            str(GRAPH_PATH),
            "--allow-local-commands",
            "--report",
            str(report_path),
        ]
    )
    return report_path


def _resume_with_command_guard(report_path: Path, workdir: Path) -> tuple[dict[str, Any], bool]:
    guard_dir = workdir / "resume-command-guard"
    guard_dir.mkdir(exist_ok=True)
    sentinel = workdir / f"{report_path.stem}-resume-command-executed.txt"

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
    return _run_cli(["resume", "--checkpoint", str(report_path)], env=env), not sentinel.exists()


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="agy-v16-summary-contract-") as tmp:
        workdir = Path(tmp)
        guarded_report = _write_guarded_report(workdir)
        unguarded_report = _write_unguarded_report(workdir)

        guarded_inspect = _run_cli(["inspect", "--checkpoint", str(guarded_report)])
        guarded_resume, guarded_resume_did_not_execute = _resume_with_command_guard(
            guarded_report, workdir
        )
        unguarded_inspect = _run_cli(["inspect", "--checkpoint", str(unguarded_report)])
        unguarded_resume, unguarded_resume_did_not_execute = _resume_with_command_guard(
            unguarded_report, workdir
        )

    guarded_inspect_valid, guarded_inspect_errors = _validate(guarded_inspect, schema)
    guarded_resume_valid, guarded_resume_errors = _validate(guarded_resume, schema)
    unguarded_inspect_valid, unguarded_inspect_errors = _validate(unguarded_inspect, schema)
    unguarded_resume_valid, unguarded_resume_errors = _validate(unguarded_resume, schema)

    inspect_resume_summary_match = (
        guarded_inspect["summary"]["guarded_report"] == guarded_resume["summary"]["guarded_report"]
    )
    commands_executed = guarded_resume["summary"]["guarded_report"]["commands_executed"]
    resume_did_not_execute_commands = (
        guarded_resume_did_not_execute and unguarded_resume_did_not_execute
    )
    all_checks = all(
        [
            guarded_inspect_valid,
            guarded_resume_valid,
            unguarded_inspect_valid,
            unguarded_resume_valid,
            inspect_resume_summary_match,
            commands_executed is False,
            resume_did_not_execute_commands,
            "guarded_report" not in unguarded_inspect["summary"],
            "guarded_report" not in unguarded_resume["summary"],
        ]
    )
    payload = {
        "passed": all_checks,
        "guarded_inspect_schema_valid": guarded_inspect_valid,
        "guarded_resume_schema_valid": guarded_resume_valid,
        "unguarded_inspect_schema_valid": unguarded_inspect_valid,
        "unguarded_resume_schema_valid": unguarded_resume_valid,
        "inspect_resume_summary_match": inspect_resume_summary_match,
        "commands_executed": commands_executed,
        "resume_did_not_execute_commands": resume_did_not_execute_commands,
        "errors": {
            "guarded_inspect": guarded_inspect_errors,
            "guarded_resume": guarded_resume_errors,
            "unguarded_inspect": unguarded_inspect_errors,
            "unguarded_resume": unguarded_resume_errors,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if all_checks else 1


if __name__ == "__main__":
    raise SystemExit(main())
