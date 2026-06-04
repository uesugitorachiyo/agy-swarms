from __future__ import annotations

import subprocess
from pathlib import Path
import pytest

from agy_swarms.governance.footprint import FootprintGate, FootprintViolation


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")

    # Write a simple clean python file
    (repo / "app.py").write_text("print('hello')\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_current_repo_footprint_passes():
    # Enforce current repository root passes footprint check
    repo_root = Path(__file__).resolve().parents[1]
    gate = FootprintGate(repo_root)
    result = gate.run_check()
    assert result["passed"] is True
    assert result["total_loc"] > 0
    assert result["source_files_count"] > 0


def test_footprint_rejects_single_large_file(tmp_path: Path):
    repo = _init_repo(tmp_path, "large_file_repo")
    gate = FootprintGate(repo)

    # Write a 1,501-line python file
    content = "\n".join(f"print({i})" for i in range(1501)) + "\n"
    (repo / "large.py").write_text(content)
    _git(repo, "add", "large.py")
    _git(repo, "commit", "-m", "add large file")

    tracked = gate._git("ls-files").splitlines()
    print(f"DEBUG TRACKED FILES: {tracked}")
    for f in tracked:
        p = repo / f
        if p.exists():
            print(f"DEBUG FILE {f} LOC: {len(p.read_text().splitlines())}")

    with pytest.raises(FootprintViolation, match="exceeds 1,500 lines"):
        gate.run_check()


def test_footprint_rejects_large_source_tree(tmp_path: Path):
    repo = _init_repo(tmp_path, "large_tree_repo")
    gate = FootprintGate(repo)

    # Write 51 python files, each with 1,000 lines (total 51,000 LOC)
    content = "\n".join(f"print({i})" for i in range(1000)) + "\n"
    for idx in range(51):
        file_path = repo / f"file_{idx}.py"
        file_path.write_text(content)
        _git(repo, "add", str(file_path))

    _git(repo, "commit", "-m", "add many files")

    with pytest.raises(FootprintViolation, match="exceeds 50,000 lines"):
        gate.run_check()


def test_footprint_rejects_tracked_run_artifact_hygiene(tmp_path: Path):
    repo = _init_repo(tmp_path, "hygiene_repo")
    gate = FootprintGate(repo)

    # 1. Tracked .log extension
    (repo / "run.log").write_text("raw transcript log")
    _git(repo, "add", "run.log")
    _git(repo, "commit", "-m", "accidentally commit log")

    with pytest.raises(FootprintViolation, match="Hygiene violation"):
        gate.run_check()


def test_footprint_rejects_tracked_run_artifact_directory(tmp_path: Path):
    repo = _init_repo(tmp_path, "hygiene_dir_repo")
    gate = FootprintGate(repo)

    # 2. Tracked inside checkpoints/ directory
    checkpoints_dir = repo / "checkpoints"
    checkpoints_dir.mkdir()
    (checkpoints_dir / "journal.db").write_text("some db content")
    _git(repo, "add", "checkpoints/journal.db")
    _git(repo, "commit", "-m", "accidentally commit checkpoints")

    with pytest.raises(FootprintViolation, match="Hygiene violation"):
        gate.run_check()


def test_footprint_allows_planning_spikes(tmp_path: Path):
    repo = _init_repo(tmp_path, "spikes_repo")
    gate = FootprintGate(repo)

    # Tracked inside .planning/spikes/ (allowed exception)
    spikes_dir = repo / ".planning" / "spikes"
    spikes_dir.mkdir(parents=True)
    (spikes_dir / "probe.json").write_text("{}")
    _git(repo, "add", ".planning/spikes/probe.json")
    _git(repo, "commit", "-m", "commit planning spike")

    # Should pass because planning evidence is explicitly exempted
    result = gate.run_check()
    assert result["passed"] is True
