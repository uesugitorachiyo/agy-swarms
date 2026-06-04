"""Read-only diffs for saved local review bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .review_bundle_inspection import load_review_bundle


def summarize_review_bundle_diff(before_path: str | Path, after_path: str | Path) -> dict[str, Any]:
    """Return a stable JSON-safe diff summary without reading graph files."""
    before = load_review_bundle(before_path)
    after = load_review_bundle(after_path)
    before_commands = _command_digests(before)
    after_commands = _command_digests(after)
    before_ids = set(before_commands)
    after_ids = set(after_commands)

    return {
        "kind": "review_bundle_diff",
        "before_path": str(before_path),
        "after_path": str(after_path),
        "before_schema_version": before["schema_version"],
        "after_schema_version": after["schema_version"],
        "before_graph_sha256": before["graph_sha256"],
        "after_graph_sha256": after["graph_sha256"],
        "graph_changed": before["graph_sha256"] != after["graph_sha256"],
        "command_changes": {
            "added": sorted(after_ids - before_ids),
            "removed": sorted(before_ids - after_ids),
            "changed": sorted(
                node_id
                for node_id in before_ids & after_ids
                if before_commands[node_id] != after_commands[node_id]
            ),
            "unchanged": sorted(
                node_id
                for node_id in before_ids & after_ids
                if before_commands[node_id] == after_commands[node_id]
            ),
        },
        "before_review_complete": bool(before["review_bundle"].get("review_complete", False)),
        "after_review_complete": bool(after["review_bundle"].get("review_complete", False)),
        "schemas": dict(sorted(after["schemas"].items())),
        "commands_executed": False,
    }


def _command_digests(bundle: dict[str, Any]) -> dict[str, str]:
    command_review = bundle.get("preflight", {}).get("command_review", {})
    if not isinstance(command_review, dict):
        return {}
    return {
        str(node_id): str(item.get("argv_sha256", ""))
        for node_id, item in command_review.items()
        if isinstance(item, dict)
    }
