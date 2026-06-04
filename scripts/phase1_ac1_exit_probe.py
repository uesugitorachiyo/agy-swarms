#!/usr/bin/env python3
"""Run the AC-1 Phase-1 exit test cluster as one aggregate probe."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Any


AC1_TEST_FILES = (
    "tests/test_ac1_integration.py",
    "tests/test_conductor.py",
    "tests/test_conductor_resume_ledger.py",
    "tests/test_conductor_backpressure.py",
    "tests/test_crash_containment.py",
    "tests/test_gates.py",
    "tests/test_validate.py",
    "tests/test_conductor_test_node.py",
)

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
PYTEST_DURATION_PATTERN = re.compile(r"\bin \d+(?:\.\d+)?s\b")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _summary(stdout: str, stderr: str) -> str:
    combined = [line.strip() for line in f"{stdout}\n{stderr}".splitlines() if line.strip()]
    return combined[-1] if combined else ""


def _normalize_pytest_timing(text: str) -> str:
    return PYTEST_DURATION_PATTERN.sub("in <duration>", text)


def run_probe(
    *,
    output_path: Path | None = None,
    write_output: bool = True,
    command_runner: CommandRunner = _run_command,
) -> dict[str, Any]:
    output_path = output_path or _repo_root() / ".planning/spikes/ac1-exit.json"
    command = ["uv", "run", "pytest", *AC1_TEST_FILES, "-q"]
    completed = command_runner(command)
    stdout = _normalize_pytest_timing(completed.stdout)
    stderr = _normalize_pytest_timing(completed.stderr)
    passed = completed.returncode == 0
    result = {
        "gate": "AC-1",
        "passed": passed,
        "status": "PHASE-1 EXIT READY" if passed else "BLOCKED",
        "command": command,
        "test_files": list(AC1_TEST_FILES),
        "returncode": completed.returncode,
        "summary": _summary(stdout, stderr),
        "stdout": stdout,
        "stderr": stderr,
    }
    if write_output:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".planning/spikes/ac1-exit.json"),
    )
    parser.add_argument("--write", action="store_true", help="Write output JSON to disk")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write output JSON to disk (deprecated, default)",
    )
    args = parser.parse_args()
    result = run_probe(output_path=args.output, write_output=args.write and not args.no_write)
    print(
        json.dumps(
            {
                "gate": result["gate"],
                "passed": result["passed"],
                "status": result["status"],
                "summary": result["summary"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
