from __future__ import annotations

import subprocess
from pathlib import Path
import pytest

from agy_swarms.governance.sandbox import SandboxViolation, WorktreeSandbox
from agy_swarms.governance.patch import promote_patch


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hello')\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_promote_patch_applies_valid_changes(tmp_path: Path):
    target = _init_repo(tmp_path, "target")
    # Clone target to sandbox to simulate a git worktree sandbox
    sandbox_dir = tmp_path / "sandbox"
    _git(tmp_path, "clone", str(target), str(sandbox_dir))
    _git(sandbox_dir, "config", "user.email", "test@example.invalid")
    _git(sandbox_dir, "config", "user.name", "Test User")

    sandbox = WorktreeSandbox(sandbox_dir)

    # 1. Modify an existing file
    sandbox.write_text("src/app.py", "print('hello world')\n")
    # 2. Add a new file
    sandbox.write_text("src/new.py", "x = 42\n")

    # Promote patch
    promoted = promote_patch(sandbox, target)

    assert set(promoted) == {"src/app.py", "src/new.py"}
    assert (target / "src" / "app.py").read_text() == "print('hello world')\n"
    assert (target / "src" / "new.py").read_text() == "x = 42\n"


def test_promote_patch_rejects_unmatching_model_claims(tmp_path: Path):
    target = _init_repo(tmp_path, "target")
    sandbox_dir = tmp_path / "sandbox"
    _git(tmp_path, "clone", str(target), str(sandbox_dir))
    sandbox = WorktreeSandbox(sandbox_dir)

    sandbox.write_text("src/app.py", "print('hello world')\n")

    with pytest.raises(SandboxViolation, match="Model claims do not match git state"):
        promote_patch(sandbox, target, model_claims=["src/app.py", "other.py"])


def test_promote_patch_allows_matching_model_claims(tmp_path: Path):
    target = _init_repo(tmp_path, "target")
    sandbox_dir = tmp_path / "sandbox"
    _git(tmp_path, "clone", str(target), str(sandbox_dir))
    sandbox = WorktreeSandbox(sandbox_dir)

    sandbox.write_text("src/app.py", "print('hello world')\n")

    promoted = promote_patch(sandbox, target, model_claims=["src/app.py"])
    assert promoted == ["src/app.py"]
    assert (target / "src" / "app.py").read_text() == "print('hello world')\n"


def test_promote_patch_rejects_disallowed_paths(tmp_path: Path):
    target = _init_repo(tmp_path, "target")
    sandbox_dir = tmp_path / "sandbox"
    _git(tmp_path, "clone", str(target), str(sandbox_dir))
    sandbox = WorktreeSandbox(sandbox_dir)

    sandbox.write_text("src/app.py", "print('hello world')\n")
    sandbox.write_text("src/other.py", "y = 10\n")

    # Limit allowed paths to src/app.py
    with pytest.raises(SandboxViolation, match="Path not explicitly allowed"):
        promote_patch(sandbox, target, allowed_paths=["src/app.py"])


def test_failed_promotion_leaves_target_completely_unchanged(tmp_path: Path):
    target = _init_repo(tmp_path, "target")
    sandbox_dir = tmp_path / "sandbox"
    _git(tmp_path, "clone", str(target), str(sandbox_dir))
    sandbox = WorktreeSandbox(sandbox_dir)

    # Make one valid change and one invalid change (outside allowed_paths)
    sandbox.write_text("src/app.py", "print('hello world')\n")
    sandbox.write_text("src/other.py", "y = 10\n")

    # Limit allowed paths to src/app.py
    with pytest.raises(SandboxViolation, match="Path not explicitly allowed"):
        promote_patch(sandbox, target, allowed_paths=["src/app.py"])

    # Verify target is unchanged
    assert (target / "src" / "app.py").read_text() == "print('hello')\n"
    assert not (target / "src" / "other.py").exists()


def test_promote_patch_rejects_untracked_artifact_directories(tmp_path: Path):
    target = _init_repo(tmp_path, "target")
    sandbox_dir = tmp_path / "sandbox"
    _git(tmp_path, "clone", str(target), str(sandbox_dir))
    sandbox = WorktreeSandbox(sandbox_dir)

    # Create a new untracked directory
    sandbox.write_text("artifacts/run.json", "{}")

    # Fails because 'artifacts' is an untracked directory and not allowed
    with pytest.raises(
        SandboxViolation, match="Untracked artifact directory not explicitly allowed"
    ):
        promote_patch(sandbox, target)

    # Succeeds if explicitly allowed
    promoted = promote_patch(sandbox, target, allowed_paths=["src/", "artifacts/"])
    assert "artifacts/run.json" in promoted
    assert (target / "artifacts" / "run.json").exists()


def test_promote_patch_rejects_path_traversal_and_absolute_paths(tmp_path: Path):
    target = _init_repo(tmp_path, "target")
    sandbox_dir = tmp_path / "sandbox"
    _git(tmp_path, "clone", str(target), str(sandbox_dir))
    sandbox = WorktreeSandbox(sandbox_dir)

    # Absolute path or traversal check is done over the changed list
    # We can mock sandbox.changed_files to return unsafe paths
    sandbox.changed_files = lambda: ["/absolute/path.py"]
    with pytest.raises(SandboxViolation, match="Path is absolute"):
        promote_patch(sandbox, target)

    sandbox.changed_files = lambda: ["src/../../escape.py"]
    with pytest.raises(SandboxViolation, match="Path traversal detected"):
        promote_patch(sandbox, target)
