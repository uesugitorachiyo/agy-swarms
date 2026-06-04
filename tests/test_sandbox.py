from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agy_swarms.governance.sandbox import SandboxViolation, WorktreeSandbox


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "src").mkdir()
    (repo / "src" / "app.txt").write_text("before\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_worktree_sandbox_allows_writes_inside_declared_root(tmp_path: Path):
    repo = _repo(tmp_path)
    sandbox = WorktreeSandbox(repo)

    written = sandbox.write_text("src/app.txt", "after\n")

    assert written == repo / "src" / "app.txt"
    assert (repo / "src" / "app.txt").read_text() == "after\n"


def test_worktree_sandbox_rejects_path_traversal_outside_root(tmp_path: Path):
    repo = _repo(tmp_path)
    sandbox = WorktreeSandbox(repo)

    with pytest.raises(SandboxViolation, match="outside worktree"):
        sandbox.write_text("../escape.txt", "bad\n")

    assert not (tmp_path / "escape.txt").exists()


def test_changed_files_are_computed_from_git_diff_not_model_claims(tmp_path: Path):
    repo = _repo(tmp_path)
    sandbox = WorktreeSandbox(repo)
    sandbox.write_text("src/app.txt", "after\n")

    assert sandbox.changed_files(model_claims=["fake.py", "src/app.txt"]) == ["src/app.txt"]


def test_changed_files_include_untracked_files_from_worktree(tmp_path: Path):
    repo = _repo(tmp_path)
    sandbox = WorktreeSandbox(repo)
    sandbox.write_text("src/new.txt", "new\n")

    assert sandbox.changed_files() == ["src/new.txt"]


def test_worktree_sandbox_rejects_non_git_roots(tmp_path: Path):
    with pytest.raises(SandboxViolation, match="not a git worktree"):
        WorktreeSandbox(tmp_path / "missing")
