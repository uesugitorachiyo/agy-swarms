"""Read-only review handoff prompts for external agy review."""

from __future__ import annotations


def build_agy_review_prompt(*, report_path: str) -> str:
    """Build a copy/paste prompt that keeps agy in read-only review mode."""
    return f"""TASK: Read-only review of agy-swarms local runner evidence.

Working dir: <path-to-your-agy-swarms-checkout>
Report path: {report_path}

You are reviewing, not implementing.
Do not implement changes.
do not commit.
do not push.
Report findings first, ordered by severity, with file/line references.

Start by running:

```bash
git status --short
uv run python scripts/release_health.py
```

Review whether the report proves the local runner acceptance criteria and list
residual risks only if there are no blockers.
"""
