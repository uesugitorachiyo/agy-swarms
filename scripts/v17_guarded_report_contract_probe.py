#!/usr/bin/env python3
"""Validate guarded saved local-runner reports against the full report schema."""

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


def _load_report(path: Path, label: str) -> tuple[dict[str, Any], str | None]:
    if not path.exists():
        return {}, f"{label} report was not written"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"{label} report was not JSON: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{label} report was not an object"
    return payload, None


def _write_guarded_report(workdir: Path) -> tuple[Path, list[str]]:
    errors: list[str] = []
    bundle_path = workdir / "review-bundle.json"
    report_path = workdir / "guarded-report.json"
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
    if proc.returncode != 0:
        errors.append(proc.stderr or proc.stdout or "guarded run failed")
    return report_path, errors


def _write_unguarded_report(workdir: Path) -> tuple[Path, list[str]]:
    report_path = workdir / "unguarded-report.json"
    proc = _run_cli(
        [
            "run",
            "--graph",
            str(GRAPH_PATH),
            "--allow-local-commands",
            "--report",
            str(report_path),
        ]
    )
    errors = [] if proc.returncode == 0 else [proc.stderr or proc.stdout or "run failed"]
    return report_path, errors


def _resume_with_command_guard(
    report_path: Path, workdir: Path
) -> tuple[dict[str, Any], bool, str | None]:
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


def _validate_guard_evidence(report: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    guard = report.get("review_bundle_guard")
    if not isinstance(guard, dict):
        return False, ["missing review_bundle_guard"]

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


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: dict[str, list[str]] = {
        "guarded_report": [],
        "unguarded_report": [],
        "inspect_resume": [],
    }
    with tempfile.TemporaryDirectory(prefix="agy-v17-guarded-report-contract-") as tmp:
        workdir = Path(tmp)
        guarded_report_path, guarded_write_errors = _write_guarded_report(workdir)
        unguarded_report_path, unguarded_write_errors = _write_unguarded_report(workdir)
        errors["guarded_report"].extend(guarded_write_errors)
        errors["unguarded_report"].extend(unguarded_write_errors)

        guarded_report, guarded_load_error = _load_report(guarded_report_path, "guarded")
        unguarded_report, unguarded_load_error = _load_report(unguarded_report_path, "unguarded")
        if guarded_load_error:
            errors["guarded_report"].append(guarded_load_error)
        if unguarded_load_error:
            errors["unguarded_report"].append(unguarded_load_error)

        guarded_report_schema_valid, guarded_schema_errors = _validate_report(
            guarded_report, schema
        )
        unguarded_report_schema_valid, unguarded_schema_errors = _validate_report(
            unguarded_report, schema
        )
        guard_valid, guard_errors = _validate_guard_evidence(guarded_report)
        errors["guarded_report"].extend(guarded_schema_errors)
        errors["guarded_report"].extend(guard_errors)
        errors["unguarded_report"].extend(unguarded_schema_errors)

        inspect_payload, inspect_error = _load_cli_json(
            _run_cli(["inspect", "--checkpoint", str(guarded_report_path)]),
            "inspect",
        )
        resume_payload, resume_did_not_execute, resume_error = _resume_with_command_guard(
            guarded_report_path, workdir
        )
        if inspect_error:
            errors["inspect_resume"].append(inspect_error)
        if resume_error:
            errors["inspect_resume"].append(resume_error)

    guard = guarded_report.get("review_bundle_guard", {})
    inspect_summary = inspect_payload.get("summary", {}).get("guarded_report", {})
    resume_summary = resume_payload.get("summary", {}).get("guarded_report", {})
    inspect_resume_summary_match = bool(inspect_summary) and inspect_summary == resume_summary
    if not inspect_resume_summary_match:
        errors["inspect_resume"].append("inspect/resume guarded summaries differed")
    if not resume_did_not_execute:
        errors["inspect_resume"].append("resume attempted local command execution")

    unguarded_report_omits_guard = "review_bundle_guard" not in unguarded_report
    passed = (
        guarded_report_schema_valid
        and guard_valid
        and unguarded_report_schema_valid
        and unguarded_report_omits_guard
        and inspect_resume_summary_match
        and resume_did_not_execute
    )
    print(
        json.dumps(
            {
                "gate": "V17-AC1/V17-AC2/V17-AC3/V17-AC4",
                "passed": passed,
                "schema": SCHEMA_PATH.as_posix(),
                "guarded_report_schema_valid": guarded_report_schema_valid,
                "guarded_report_has_guard": isinstance(guard, dict) and bool(guard),
                "guarded_run": guard.get("guarded_run"),
                "guard_commands_executed": guard.get("commands_executed"),
                "guard_evidence_valid": guard_valid,
                "unguarded_report_schema_valid": unguarded_report_schema_valid,
                "unguarded_report_omits_guard": unguarded_report_omits_guard,
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
