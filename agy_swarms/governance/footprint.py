"""Footprint and artifact hygiene gate (M4/D6.6)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class FootprintViolation(Exception):
    """Raised when repository footprint or hygiene constraints are violated."""


class FootprintGate:
    """Enforces source code footprint (LOC limits) and Git artifact hygiene."""

    def __init__(self, repo_root: Path | str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def _git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return ""
        return completed.stdout

    def run_check(self) -> dict[str, Any]:
        """Runs the footprint and hygiene scans.

        Raises:
            FootprintViolation if any constraint fails.
        """
        # 1. Get tracked files via git ls-files
        tracked_files = self._git("ls-files").splitlines()

        source_files: list[tuple[str, int]] = []
        total_loc = 0

        # Ignored extensions and directories for run artifacts / raw logs
        artifact_extensions = (".log", ".jsonl", ".ndjson", ".sqlite", ".db")
        artifact_directories = ("runs/", "artifacts/", "checkpoints/", ".agy/")

        for file_str in tracked_files:
            file_str = file_str.strip()
            if not file_str:
                continue

            file_path = Path(file_str)

            # Check if inside forbidden artifact directories
            is_artifact_dir = False
            for ad in artifact_directories:
                if file_str.startswith(ad):
                    is_artifact_dir = True
                    break

            # Check if carrying forbidden extensions
            is_artifact_ext = file_path.suffix in artifact_extensions

            # Enforce hygiene: raw log / artifact must never be tracked in Git
            # Exception: planning spikes under .planning/spikes/ are allowed
            if (is_artifact_dir or is_artifact_ext) and not file_str.startswith(
                ".planning/spikes/"
            ):
                raise FootprintViolation(
                    f"Hygiene violation: run artifact or log tracked in Git: {file_str}"
                )

            # Enforce LOC on source files (.py)
            if file_path.suffix == ".py":
                abs_path = self.repo_root / file_path
                if abs_path.exists():
                    loc = 0
                    has_loc = False
                    try:
                        loc = len(abs_path.read_text(encoding="utf-8").splitlines())
                        has_loc = True
                    except (UnicodeDecodeError, OSError):
                        pass

                    if has_loc:
                        if loc > 1500:
                            raise FootprintViolation(
                                f"LOC violation: file '{file_str}' exceeds 1,500 lines ({loc} LOC)"
                            )
                        source_files.append((file_str, loc))
                        total_loc += loc

        # Enforce global LOC limit
        if total_loc > 50000:
            raise FootprintViolation(
                f"LOC violation: total committed source exceeds 50,000 lines ({total_loc} LOC)"
            )

        return {
            "passed": True,
            "total_loc": total_loc,
            "source_files_count": len(source_files),
        }
