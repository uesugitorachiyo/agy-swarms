#!/usr/bin/env python3
"""Fresh-clone install smoke for v0.1 release engineering."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any


@dataclass(frozen=True)
class SmokeStep:
    command: list[str]
    cwd: Path | None = None
    expect_stdout: str | None = None


CommandRunner = Callable[[SmokeStep], subprocess.CompletedProcess[str]]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_smoke_steps(*, repo_root: Path, checkout_dir: Path) -> list[SmokeStep]:
    task_path = checkout_dir.parent / "fresh-clone-smoke-task.json"
    task_payload = json.dumps(
        {"task": "Fresh clone install smoke", "model_pins": {"default": "flash-smoke"}},
        sort_keys=True,
    )
    return [
        SmokeStep(["git", "clone", "--quiet", str(repo_root), str(checkout_dir)]),
        SmokeStep(["uv", "sync", "--extra", "dev"], cwd=checkout_dir),
        SmokeStep(
            [
                "uv",
                "run",
                "python",
                "-c",
                "import agy_swarms; import agy_swarms.main",
            ],
            cwd=checkout_dir,
        ),
        SmokeStep(
            [
                "uv",
                "run",
                "python",
                "-c",
                (
                    "from pathlib import Path; "
                    f"Path({str(task_path)!r}).write_text({task_payload!r})"
                ),
            ],
            cwd=checkout_dir,
        ),
        SmokeStep(
            ["uv", "run", "agy-swarms", "plan", "--task", str(task_path)],
            cwd=checkout_dir,
        ),
        SmokeStep(["git", "status", "--short"], cwd=checkout_dir, expect_stdout=""),
    ]


def _run_step(step: SmokeStep) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    return subprocess.run(
        step.command,
        cwd=step.cwd,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def run_smoke(
    *,
    repo_root: Path | None = None,
    base_dir: Path | None = None,
    command_runner: CommandRunner = _run_step,
) -> dict[str, Any]:
    repo_root = (repo_root or _repo_root()).resolve()
    if base_dir is None:
        temp_context = tempfile.TemporaryDirectory(prefix="agy-swarms-fresh-clone-")
        base = Path(temp_context.name)
    else:
        temp_context = None
        base = base_dir
        base.mkdir(parents=True, exist_ok=True)

    checkout_dir = base / "checkout"
    if checkout_dir.exists():
        shutil.rmtree(checkout_dir)

    steps = build_smoke_steps(repo_root=repo_root, checkout_dir=checkout_dir)
    step_reports: list[dict[str, Any]] = []
    failed_step: dict[str, Any] | None = None
    try:
        for step in steps:
            completed = command_runner(step)
            stdout_matches = step.expect_stdout is None or completed.stdout == step.expect_stdout
            passed = completed.returncode == 0 and stdout_matches
            step_report = {
                "command": step.command,
                "cwd": str(step.cwd) if step.cwd is not None else None,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "status": "passed" if passed else "failed",
            }
            step_reports.append(step_report)
            if not passed:
                failed_step = step_report
                break
    finally:
        if temp_context is not None:
            temp_context.cleanup()

    return {
        "gate": "fresh-clone-install-smoke",
        "passed": failed_step is None,
        "repo_root": str(repo_root),
        "checkout_dir": str(checkout_dir),
        "steps": step_reports,
        "failed_step": failed_step,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_repo_root())
    parser.add_argument("--base-dir", type=Path, default=None)
    args = parser.parse_args()
    result = run_smoke(repo_root=args.repo_root, base_dir=args.base_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
