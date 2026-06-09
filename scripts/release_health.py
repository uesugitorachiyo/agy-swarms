#!/usr/bin/env python3
"""Unified release health command that aggregates all exit probes dynamically in read-only mode."""

from __future__ import annotations

import json
import subprocess
import sys

from scripts.release_health_registry import PROBES


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
            print(f"  {_color('[OK]', '32')} {name:<35} {_color('[PASSED]', '1;32')}")
            passed_count += 1
        else:
            print(f"  {_color('[FAIL]', '31')} {name:<35} {_color('[FAILED]', '1;31')}")
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
