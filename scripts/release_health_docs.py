"""Markdown rendering helpers for release-health documentation."""

from __future__ import annotations

import shlex
import sys
from collections.abc import Sequence

from scripts.release_health_registry import PROBES


def _format_command(command: Sequence[str]) -> str:
    if len(command) == 2 and command[0] == sys.executable and command[1].startswith("scripts/"):
        return command[1]
    return " ".join(shlex.quote(part) for part in command)


def render_probe_list() -> str:
    """Render the release-health probe commands as a markdown bullet list."""
    return "\n".join(f"- `{_format_command(probe['command'])}`" for probe in PROBES)
