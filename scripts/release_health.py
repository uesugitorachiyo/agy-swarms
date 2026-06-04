#!/usr/bin/env python3
"""Unified release health command that aggregates all exit probes dynamically in read-only mode."""

from __future__ import annotations

import json
import subprocess
import sys

PROBES = [
    {
        "name": "Ruff Formatting & Lints",
        "command": ["uv", "run", "ruff", "check", "."],
        "desc": "Verifies codebase styling and import standards",
    },
    {
        "name": "Unit Test Suite",
        "command": ["uv", "run", "pytest", "-q"],
        "desc": "Executes 570+ hermetic engine test cases",
    },
    {
        "name": "Fresh Clone Install Smoke",
        "command": [sys.executable, "scripts/fresh_clone_smoke.py"],
        "desc": "Verifies installability and console entrypoint from a fresh clone",
    },
    {
        "name": "AC-7 Local Runner Gate",
        "command": [sys.executable, "scripts/v02_local_runner_probe.py"],
        "desc": "Verifies v0.2 local graph execution, report inspection, and handoff guardrails",
    },
    {
        "name": "V04 Fixture Replay Gate",
        "command": [sys.executable, "scripts/v04_fixture_replay_probe.py"],
        "desc": "Verifies tracked local-runner fixtures, report inspection, and saved-report resume",
    },
    {
        "name": "V05 Report Contract Gate",
        "command": [sys.executable, "scripts/v05_report_contract_probe.py"],
        "desc": "Verifies saved local-runner reports against the stable report contract",
    },
    {
        "name": "V06 Graph Preflight Gate",
        "command": [sys.executable, "scripts/v06_graph_preflight_probe.py"],
        "desc": "Verifies local runner graphs can be preflighted without executing commands",
    },
    {
        "name": "V07 Preflight Contract Gate",
        "command": [sys.executable, "scripts/v07_preflight_contract_probe.py"],
        "desc": "Verifies preflight JSON output against the local schema contract",
    },
    {
        "name": "V08 Command Review Gate",
        "command": [sys.executable, "scripts/v08_command_review_probe.py"],
        "desc": "Verifies opt-in preflight command review evidence without execution",
    },
    {
        "name": "V09 Command Review Contract Gate",
        "command": [sys.executable, "scripts/v09_command_review_contract_probe.py"],
        "desc": "Verifies opt-in command review evidence against the local schema contract",
    },
    {
        "name": "V10 Review Bundle Gate",
        "command": [sys.executable, "scripts/v10_review_bundle_probe.py"],
        "desc": "Verifies deterministic saved review bundles without command execution",
    },
    {
        "name": "V11 Review Bundle Inspection Gate",
        "command": [sys.executable, "scripts/v11_review_bundle_inspection_probe.py"],
        "desc": "Verifies deterministic saved review bundle inspection without command execution",
    },
    {
        "name": "V12 Review Bundle Diff Gate",
        "command": [sys.executable, "scripts/v12_review_bundle_diff_probe.py"],
        "desc": "Verifies deterministic saved review bundle diffs without command execution",
    },
    {
        "name": "V13 Review Bundle Run Guard",
        "command": [sys.executable, "scripts/v13_review_bundle_run_guard_probe.py"],
        "desc": "Verifies saved review bundles can guard local graph execution",
    },
    {
        "name": "V14 Guarded Run Provenance",
        "command": [sys.executable, "scripts/v14_guarded_run_provenance_probe.py"],
        "desc": "Verifies guarded local run reports carry saved review-bundle provenance",
    },
    {
        "name": "V15 Guarded Report Inspection",
        "command": [sys.executable, "scripts/v15_guarded_report_inspection_probe.py"],
        "desc": "Verifies guarded run reports expose read-only inspect/resume guard summaries",
    },
    {
        "name": "V16 Saved Report Summary Contracts",
        "command": [sys.executable, "scripts/v16_saved_report_summary_contract_probe.py"],
        "desc": "Verifies saved-report inspect/resume summaries against the local schema contract",
    },
    {
        "name": "V17 Guarded Report Contract Coverage",
        "command": [sys.executable, "scripts/v17_guarded_report_contract_probe.py"],
        "desc": "Verifies guarded saved local-runner reports against the full report schema contract",
    },
    {
        "name": "V18 Guarded Failure Report Contracts",
        "command": [sys.executable, "scripts/v18_guarded_failure_report_contract_probe.py"],
        "desc": (
            "Verifies guarded failed local-runner reports against the full report schema contract"
        ),
    },
    {
        "name": "V19 Guard Rejection Report Contracts",
        "command": [sys.executable, "scripts/v19_guard_rejection_report_contract_probe.py"],
        "desc": "Verifies pre-execution guard rejection reports against the local schema contract",
    },
    {
        "name": "V20 Guard Rejection Report Inspection",
        "command": [sys.executable, "scripts/v20_guard_rejection_inspection_probe.py"],
        "desc": "Verifies read-only inspect/resume triage for guard rejection reports",
    },
    {
        "name": "V21 Hybrid Review Routing",
        "command": [sys.executable, "scripts/v21_hybrid_review_routing_probe.py"],
        "desc": (
            "Verifies edge-backed graph semantics and Gemini-default optional CLI review routing"
        ),
    },
    {
        "name": "V22 Plugin Installation Smoke",
        "command": [sys.executable, "scripts/plugin_smoke_probe.py"],
        "desc": "Verifies agy plugin validation, installation, listing, and uninstallation",
    },
]


def _color(text: str, color_code: str) -> str:
    # Use standard ANSI escape sequences for premium terminal layout
    if sys.stdout.isatty():
        return f"\033[{color_code}m{text}\033[0m"
    return text


def run_checks() -> int:
    import os
    from pathlib import Path

    if sys.platform == "win32":
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")

    print(_color("─" * 80, "36"))
    print(_color("    AGY-SWARMS RELEASE HEALTH AUDIT DASHBOARD", "1;35"))
    print(_color("─" * 80, "36"))

    passed_count = 0
    failures = []

    # Inject repository root into PYTHONPATH for flawless import resolution
    env = os.environ.copy()
    root = str(Path(__file__).resolve().parents[1])
    path_sep = os.pathsep
    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        env["PYTHONPATH"] = f"{root}{path_sep}{existing_pythonpath}"
    else:
        env["PYTHONPATH"] = root

    for idx, probe in enumerate(PROBES, 1):
        name = probe["name"]
        command = probe["command"]
        print(f"[{idx}/{len(PROBES)}] Running: {name}...", end="", flush=True)

        res = subprocess.run(command, capture_output=True, text=True, env=env)
        passed = res.returncode == 0

        # Erase "Running..." text and render status line
        print("\r", end="")
        if passed:
            print(f"  {_color('✓', '32')} {name:<35} {_color('[PASSED]', '1;32')}")
            passed_count += 1
        else:
            print(f"  {_color('✗', '31')} {name:<35} {_color('[FAILED]', '1;31')}")
            # Try loading JSON output or fallback to stderr/stdout summary
            try:
                data = json.loads(res.stdout)
                summary = data.get("status") or data.get("summary") or "Validation failed"
            except Exception:
                summary = (
                    res.stderr.strip().splitlines()[-1]
                    if res.stderr.strip()
                    else (
                        res.stdout.strip().splitlines()[-1]
                        if res.stdout.strip()
                        else "Unknown error"
                    )
                )
            failures.append((name, summary))

    print(_color("─" * 80, "36"))
    success_rate = (passed_count / len(PROBES)) * 100
    print(f"Audit Summary: {passed_count}/{len(PROBES)} checks passed ({success_rate:.1f}%)")

    if failures:
        print(_color("\nFailure Details:", "1;31"))
        for name, summary in failures:
            print(f"  - {name}: {summary}")
        print(_color("\nRelease Status: BLOCKED", "1;31"))
        return 1

    print(_color("\nRelease Status: READY (local-release-health-certified)", "1;32"))
    return 0


if __name__ == "__main__":
    sys.exit(run_checks())
