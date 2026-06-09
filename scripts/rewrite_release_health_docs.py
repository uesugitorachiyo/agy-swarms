#!/usr/bin/env python3
"""Rewrite the release-health probe list in docs/release-verification.md."""

from __future__ import annotations

from pathlib import Path

from scripts.release_health_docs import render_probe_list

START = "<!-- release-health-probes:start -->"
END = "<!-- release-health-probes:end -->"


def rewrite_release_health_probe_list(text: str) -> str:
    """Return docs text with the marked release-health probe list regenerated."""
    start_idx = text.index(START)
    end_idx = text.index(END, start_idx)
    replacement = f"{START}\n{render_probe_list()}\n"
    return text[:start_idx] + replacement + text[end_idx:]


def main() -> int:
    path = Path("docs/release-verification.md")
    path.write_text(
        rewrite_release_health_probe_list(path.read_text(encoding="utf-8")), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
