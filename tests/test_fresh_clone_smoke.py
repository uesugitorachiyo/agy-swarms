from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.fresh_clone_smoke import SmokeStep, build_smoke_steps, run_smoke


def test_build_smoke_steps_uses_fresh_clone_and_console_entrypoint(tmp_path: Path):
    repo = tmp_path / "repo"
    checkout = tmp_path / "checkout"
    repo.mkdir()

    steps = build_smoke_steps(repo_root=repo, checkout_dir=checkout)

    assert steps[0] == SmokeStep(["git", "clone", "--quiet", str(repo), str(checkout)])
    assert SmokeStep(["uv", "sync", "--extra", "dev"], cwd=checkout) in steps
    assert any(step.command[:2] == ["uv", "run"] and "agy-swarms" in step.command for step in steps)
    assert steps[-1] == SmokeStep(["git", "status", "--short"], cwd=checkout, expect_stdout="")


def test_run_smoke_reports_successful_steps(tmp_path: Path):
    calls: list[SmokeStep] = []

    def runner(step: SmokeStep) -> subprocess.CompletedProcess[str]:
        calls.append(step)
        return subprocess.CompletedProcess(step.command, 0, stdout=step.expect_stdout, stderr="")

    report = run_smoke(repo_root=tmp_path / "repo", base_dir=tmp_path, command_runner=runner)

    assert report["passed"] is True
    assert report["failed_step"] is None
    assert [step["status"] for step in report["steps"]] == ["passed"] * len(calls)
    assert calls[0].command[:2] == ["git", "clone"]


def test_run_smoke_blocks_on_unexpected_dirty_status(tmp_path: Path):
    def runner(step: SmokeStep) -> subprocess.CompletedProcess[str]:
        stdout = " M README.md\n" if step.command == ["git", "status", "--short"] else ""
        return subprocess.CompletedProcess(step.command, 0, stdout=stdout, stderr="")

    report = run_smoke(repo_root=tmp_path / "repo", base_dir=tmp_path, command_runner=runner)

    assert report["passed"] is False
    assert report["failed_step"]["command"] == ["git", "status", "--short"]
    assert report["failed_step"]["stdout"] == " M README.md\n"
