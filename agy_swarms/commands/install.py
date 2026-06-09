"""Install command handlers."""

from __future__ import annotations

import argparse
import subprocess
import sys


def cmd_pre_commit_install(args: argparse.Namespace) -> int:
    """Install pre-commit git hooks in the local workspace."""
    print("Installing pre-commit git hooks...")
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pre_commit", "install"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(res.stdout)
        print("Success: pre-commit hooks installed.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(
            f"Error: Failed to install pre-commit hooks:\n{exc.stderr or exc.stdout}",
            file=sys.stderr,
        )
        return 1


__all__ = ["cmd_pre_commit_install"]
