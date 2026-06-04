#!/usr/bin/env python3
"""Validate pre-execution guard rejection reports against their schema."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agy_swarms.graph_io import load_graph
from agy_swarms.review_bundle import write_review_bundle


ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "tests" / "fixtures" / "local_runner" / "success-graph.json"
SCHEMA_PATH = ROOT / "schemas" / "local-runner-guard-rejection-v1.schema.json"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agy_swarms.main", *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def _write_modified_graph(source: Path, destination: Path, marker: Path) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
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


def _write_incomplete_review_bundle(graph_path: Path, bundle_path: Path) -> None:
    bundle = write_review_bundle(
        load_graph(str(graph_path)),
        graph_path=str(graph_path),
        output_path=bundle_path,
    )
    command_review = bundle["preflight"]["command_review"]
    command_review.pop("verify", None)
    bundle["review_bundle"]["review_node_count"] = len(command_review)
    bundle["review_bundle"]["review_complete"] = False
    bundle_path.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_report(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.exists():
        return {}, "guard rejection report was not written"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"guard rejection report was not JSON: {exc}"
    if not isinstance(payload, dict):
        return {}, "guard rejection report was not an object"
    return payload, None


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


def _validate_guard_rejection(
    report: dict[str, Any],
    *,
    expected_reason_class: str,
    expected_diagnostic: str,
    expected_repair_hint: str,
    expected_guard: dict[str, Any],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    expected = {
        "format": "local-runner-guard-rejection",
        "schema_version": "v1",
        "schema": "schemas/local-runner-guard-rejection-v1.schema.json",
        "status": "rejected",
        "reason_class": expected_reason_class,
        "diagnostic": expected_diagnostic,
        "repair_hint": expected_repair_hint,
        "commands_executed": False,
    }
    for key, value in expected.items():
        if report.get(key) != value:
            errors.append(f"{key} was {report.get(key)!r}")

    guard = report.get("review_bundle_guard")
    if not isinstance(guard, dict):
        return False, [*errors, "missing review_bundle_guard"]
    for key, value in expected_guard.items():
        if guard.get(key) != value:
            errors.append(f"review_bundle_guard.{key} was {guard.get(key)!r}")
    for key in ("graph_sha256",):
        digest = guard.get(key)
        if not isinstance(digest, str) or len(digest) != 64:
            errors.append(f"review_bundle_guard.{key} was not a sha256 digest")
    bundle_digest = guard.get("bundle_graph_sha256")
    if bundle_digest != "" and (not isinstance(bundle_digest, str) or len(bundle_digest) != 64):
        errors.append("review_bundle_guard.bundle_graph_sha256 was not a sha256 digest")
    return not errors, errors


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: dict[str, list[str]] = {
        "graph_digest_mismatch": [],
        "command_review_incomplete": [],
        "malformed_review_bundle": [],
    }
    scenario_results: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="agy-v19-guard-rejection-report-") as tmp:
        workdir = Path(tmp)
        graph_path = workdir / "after-graph.json"
        bundle_path = workdir / "review-bundle.json"
        report_path = workdir / "guard-rejection-report.json"
        marker = workdir / "marker.txt"
        _write_modified_graph(GRAPH_PATH, graph_path, marker)
        write_review_bundle(
            load_graph(str(GRAPH_PATH)),
            graph_path=str(GRAPH_PATH),
            output_path=bundle_path,
        )

        proc = _run_cli(
            [
                "run",
                "--graph",
                str(graph_path),
                "--allow-local-commands",
                "--require-review-bundle",
                str(bundle_path),
                "--report",
                str(report_path),
            ]
        )
        rejected = proc.returncode == 1
        if not rejected:
            errors["graph_digest_mismatch"].append(
                proc.stderr or proc.stdout or "guard rejection run did not fail"
            )
        stderr_redacted = (
            "write_text" not in proc.stderr
            and "GEMINI_API_KEY" not in proc.stderr
            and "secret" not in proc.stderr.lower()
        )
        repair_hint_present = "repair: regenerate the review bundle" in proc.stderr

        report, load_error = _load_report(report_path)
        if load_error:
            errors["graph_digest_mismatch"].append(load_error)
        schema_valid, schema_errors = _validate_report(report, schema)
        guard_valid, guard_errors = _validate_guard_rejection(
            report,
            expected_reason_class="graph_digest_mismatch",
            expected_diagnostic="review bundle does not match graph",
            expected_repair_hint="regenerate the review bundle for this graph",
            expected_guard={
                "kind": "review_bundle_run_guard",
                "graph_sha256_match": False,
                "review_complete": True,
                "missing_command_reviews": [],
                "mismatched_command_reviews": ["verify"],
                "commands_executed": False,
                "guarded_run": False,
            },
        )
        commands_executed = marker.exists()
        if commands_executed:
            errors["graph_digest_mismatch"].append("guard rejection executed local command")
        if not stderr_redacted:
            errors["graph_digest_mismatch"].append("guard rejection stderr exposed unsafe text")
        if not repair_hint_present:
            errors["graph_digest_mismatch"].append("guard rejection stderr missed repair hint")
        errors["graph_digest_mismatch"].extend(schema_errors)
        errors["graph_digest_mismatch"].extend(guard_errors)
        scenario_results["graph_digest_mismatch"] = (
            rejected
            and schema_valid
            and guard_valid
            and not commands_executed
            and stderr_redacted
            and repair_hint_present
        )

        incomplete_bundle_path = workdir / "incomplete-review-bundle.json"
        incomplete_report_path = workdir / "incomplete-guard-rejection-report.json"
        _write_incomplete_review_bundle(graph_path, incomplete_bundle_path)
        marker.unlink(missing_ok=True)
        incomplete_proc = _run_cli(
            [
                "run",
                "--graph",
                str(graph_path),
                "--allow-local-commands",
                "--require-review-bundle",
                str(incomplete_bundle_path),
                "--report",
                str(incomplete_report_path),
            ]
        )
        incomplete_report, incomplete_load_error = _load_report(incomplete_report_path)
        if incomplete_load_error:
            errors["command_review_incomplete"].append(incomplete_load_error)
        incomplete_schema_valid, incomplete_schema_errors = _validate_report(
            incomplete_report, schema
        )
        incomplete_guard_valid, incomplete_guard_errors = _validate_guard_rejection(
            incomplete_report,
            expected_reason_class="command_review_incomplete",
            expected_diagnostic="review bundle command review is incomplete",
            expected_repair_hint="regenerate with preflight --review-bundle",
            expected_guard={
                "kind": "review_bundle_run_guard",
                "graph_sha256_match": True,
                "review_complete": False,
                "missing_command_reviews": ["verify"],
                "mismatched_command_reviews": [],
                "commands_executed": False,
                "guarded_run": False,
            },
        )
        incomplete_commands_executed = marker.exists()
        if incomplete_proc.returncode != 1:
            errors["command_review_incomplete"].append(
                incomplete_proc.stderr
                or incomplete_proc.stdout
                or "incomplete review bundle run did not fail"
            )
        if incomplete_commands_executed:
            errors["command_review_incomplete"].append(
                "incomplete review rejection executed local command"
            )
        errors["command_review_incomplete"].extend(incomplete_schema_errors)
        errors["command_review_incomplete"].extend(incomplete_guard_errors)
        scenario_results["command_review_incomplete"] = (
            incomplete_proc.returncode == 1
            and incomplete_schema_valid
            and incomplete_guard_valid
            and not incomplete_commands_executed
        )

        malformed_bundle_path = workdir / "malformed-review-bundle.json"
        malformed_report_path = workdir / "malformed-guard-rejection-report.json"
        malformed_bundle_path.write_text("{not-json", encoding="utf-8")
        marker.unlink(missing_ok=True)
        malformed_proc = _run_cli(
            [
                "run",
                "--graph",
                str(graph_path),
                "--allow-local-commands",
                "--require-review-bundle",
                str(malformed_bundle_path),
                "--report",
                str(malformed_report_path),
            ]
        )
        malformed_report, malformed_load_error = _load_report(malformed_report_path)
        if malformed_load_error:
            errors["malformed_review_bundle"].append(malformed_load_error)
        malformed_schema_valid, malformed_schema_errors = _validate_report(malformed_report, schema)
        malformed_guard_valid, malformed_guard_errors = _validate_guard_rejection(
            malformed_report,
            expected_reason_class="malformed_review_bundle",
            expected_diagnostic="review bundle is not valid JSON: line 1 column 2",
            expected_repair_hint="regenerate the review bundle",
            expected_guard={
                "kind": "review_bundle_run_guard",
                "bundle_graph_sha256": "",
                "graph_sha256_match": False,
                "review_complete": False,
                "missing_command_reviews": [],
                "mismatched_command_reviews": [],
                "commands_executed": False,
                "guarded_run": False,
            },
        )
        malformed_commands_executed = marker.exists()
        if malformed_proc.returncode != 1:
            errors["malformed_review_bundle"].append(
                malformed_proc.stderr
                or malformed_proc.stdout
                or "malformed review bundle run did not fail"
            )
        if malformed_commands_executed:
            errors["malformed_review_bundle"].append(
                "malformed review rejection executed local command"
            )
        errors["malformed_review_bundle"].extend(malformed_schema_errors)
        errors["malformed_review_bundle"].extend(malformed_guard_errors)
        scenario_results["malformed_review_bundle"] = (
            malformed_proc.returncode == 1
            and malformed_schema_valid
            and malformed_guard_valid
            and not malformed_commands_executed
        )

    guard = report.get("review_bundle_guard", {})
    passed = all(scenario_results.values()) and set(scenario_results) == {
        "graph_digest_mismatch",
        "command_review_incomplete",
        "malformed_review_bundle",
    }
    print(
        json.dumps(
            {
                "gate": "V19-AC1/V19-AC2/V19-AC3",
                "passed": passed,
                "schema": SCHEMA_PATH.as_posix(),
                "guard_rejection_report_schema_valid": schema_valid,
                "status": report.get("status"),
                "reason_class": report.get("reason_class"),
                "graph_sha256_match": guard.get("graph_sha256_match")
                if isinstance(guard, dict)
                else None,
                "commands_executed": commands_executed,
                "marker_command_ran": commands_executed,
                "rejection_scenarios": scenario_results,
                "stderr_redacted": stderr_redacted,
                "repair_hint_present": repair_hint_present,
                "errors": errors,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
