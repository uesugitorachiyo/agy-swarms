"""Worktree isolation helpers for file-mutating workers (FR-12/FR-15)."""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = ["SandboxViolation", "WorktreeSandbox"]


class SandboxViolation(Exception):
    """Raised when a worker attempts to escape its declared worktree."""


class WorktreeSandbox:
    """A declared git worktree boundary for file-mutating workers."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise SandboxViolation(f"not a git worktree: {self.root}")
        self._git("rev-parse", "--is-inside-work-tree")

    def resolve_path(self, relative_path: str | Path) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            raise SandboxViolation(f"path is outside worktree: {relative_path}")
        resolved = (self.root / path).resolve()
        if not _is_relative_to(resolved, self.root):
            raise SandboxViolation(f"path is outside worktree: {relative_path}")
        return resolved

    def write_text(self, relative_path: str | Path, content: str) -> Path:
        target = self.resolve_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def changed_files(
        self, *, model_claims: list[str] | tuple[str, ...] | None = None
    ) -> list[str]:
        """Return changed files from git state, ignoring model-supplied claims."""
        del model_claims
        tracked = self._git("diff", "--name-only", "--relative", "--").stdout.splitlines()
        untracked = self._git("ls-files", "--others", "--exclude-standard").stdout.splitlines()
        return sorted({path for path in [*tracked, *untracked] if path})

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise SandboxViolation(detail or f"git {' '.join(args)} failed")
        return completed


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
