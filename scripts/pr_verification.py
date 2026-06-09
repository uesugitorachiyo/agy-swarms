"""Refresh a pull request body with current local verification evidence."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

START_MARKER = "<!-- agy-verification:start -->"
END_MARKER = "<!-- agy-verification:end -->"


def render_verification_block(
    *,
    commit: str,
    command: str,
    pytest_count: int,
    mypy_files: int,
    release_health_passed: int,
    release_health_total: int,
) -> str:
    """Return the marked verification section body."""
    return "\n".join(
        [
            START_MARKER,
            f"- Commit: `{commit}`",
            f"- Command: `{command}`",
            "- Result:",
            "  - Ruff check passed",
            "  - Ruff format check passed",
            f"  - mypy: `{mypy_files} source files`",
            f"  - pytest: `{pytest_count} passed`",
            "  - package build passed",
            (f"  - release health: `{release_health_passed}/{release_health_total} checks passed`"),
            END_MARKER,
        ]
    )


def update_body(existing: str, verification_block: str) -> str:
    """Replace or append the PR verification section."""
    section = f"## Verification\n{verification_block}"
    if START_MARKER in existing and END_MARKER in existing:
        before, marked_and_after = existing.split(START_MARKER, maxsplit=1)
        _, after = marked_and_after.split(END_MARKER, maxsplit=1)
        if before.rstrip().endswith("## Verification"):
            return f"{before.rstrip()}\n{verification_block}{after}"
        return f"{before.rstrip()}\n\n{section}{after}"

    test_plan_index = existing.find("\n## Test Plan")
    if test_plan_index == -1 and existing.startswith("## Test Plan"):
        test_plan_index = 0
    if test_plan_index != -1:
        prefix = existing[:test_plan_index].rstrip()
        return f"{prefix}\n\n{section}\n"

    return f"{existing.rstrip()}\n\n{section}\n"


def _run_text(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.rstrip()


def current_commit() -> str:
    """Return the current short git commit SHA."""
    return _run_text(["git", "rev-parse", "--short", "HEAD"])


def read_pr_body(pr_number: str, repo: str | None) -> str:
    """Read a PR body through the GitHub CLI."""
    command = ["gh", "pr", "view", pr_number, "--json", "body", "-q", ".body"]
    if repo is not None:
        command.extend(["--repo", repo])
    return _run_text(command)


def write_pr_body(pr_number: str, body: str, repo: str | None) -> None:
    """Write a PR body through the GitHub CLI."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        command = ["gh", "pr", "edit", pr_number, "--body-file", str(body_path)]
        if repo is not None:
            command.extend(["--repo", repo])
        subprocess.run(command, check=True)
    finally:
        body_path.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", required=True, help="Pull request number to update")
    parser.add_argument("--repo", help="GitHub repository in owner/name form")
    parser.add_argument("--commit", help="Commit SHA to record; defaults to current HEAD")
    parser.add_argument("--command", default="make verify", help="Verification command")
    parser.add_argument("--pytest-count", type=int, required=True)
    parser.add_argument("--mypy-files", type=int, required=True)
    parser.add_argument("--release-health-passed", type=int, required=True)
    parser.add_argument("--release-health-total", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Print the updated body")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    block = render_verification_block(
        commit=args.commit or current_commit(),
        command=args.command,
        pytest_count=args.pytest_count,
        mypy_files=args.mypy_files,
        release_health_passed=args.release_health_passed,
        release_health_total=args.release_health_total,
    )
    body = update_body(read_pr_body(args.pr, args.repo), block)
    if args.dry_run:
        print(body)
        return 0
    write_pr_body(args.pr, body, args.repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
