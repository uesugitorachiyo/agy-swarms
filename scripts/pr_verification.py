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
    verification_section = _replace_markdown_sections(existing, "Verification", section)
    if verification_section is not None:
        return verification_section

    test_plan_index = existing.find("\n## Test Plan")
    if test_plan_index == -1 and existing.startswith("## Test Plan"):
        test_plan_index = 0
    if test_plan_index != -1:
        prefix = existing[:test_plan_index].rstrip()
        return f"{prefix}\n\n{section}\n"

    return f"{existing.rstrip()}\n\n{section}\n"


def _markdown_section_bounds(existing: str, heading: str) -> list[tuple[int, int]]:
    marker = f"## {heading}"
    bounds: list[tuple[int, int]] = []
    search_from = 0
    while True:
        if existing.startswith(marker, search_from):
            start = search_from
        else:
            marker_index = existing.find(f"\n{marker}", search_from)
            if marker_index == -1:
                break
            start = marker_index + 1
        next_heading = existing.find("\n## ", start + len(marker))
        end = len(existing) if next_heading == -1 else next_heading + 1
        bounds.append((start, end))
        search_from = end
    return bounds


def _replace_markdown_sections(existing: str, heading: str, replacement: str) -> str | None:
    bounds = _markdown_section_bounds(existing, heading)
    if not bounds:
        return None

    first_start, first_end = bounds[0]
    parts = [existing[:first_start].rstrip(), replacement]
    cursor = first_end
    for start, end in bounds[1:]:
        parts.append(existing[cursor:start].strip())
        cursor = end
    parts.append(existing[cursor:].strip())
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


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
