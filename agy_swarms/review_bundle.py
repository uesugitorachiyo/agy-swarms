"""Deterministic saved review bundles for local graph preflight evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .preflight import summarize_graph_preflight
from .types import TaskGraph

SCHEMAS = {
    "preflight": "schemas/local-graph-preflight-v1.schema.json",
    "command_review": "schemas/local-command-review-v1.schema.json",
    "review_bundle": "schemas/local-review-bundle-v1.schema.json",
}


def build_review_bundle(graph: TaskGraph, *, graph_path: str | Path) -> dict[str, Any]:
    """Wrap preflight and command review evidence in a stable saved bundle."""
    path = Path(graph_path)
    preflight = summarize_graph_preflight(graph, include_command_review=True)
    command_node_ids = preflight["command_node_ids"]
    command_review = preflight.get("command_review", {})
    return {
        "format": "local-review-bundle",
        "schema_version": "v1",
        "graph_path": str(graph_path),
        "graph_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schemas": dict(SCHEMAS),
        "commands_executed": False,
        "preflight": preflight,
        "review_bundle": {
            "command_node_count": len(command_node_ids),
            "review_node_count": len(command_review),
            "review_complete": sorted(command_node_ids) == sorted(command_review),
        },
    }


def write_review_bundle(
    graph: TaskGraph, *, graph_path: str | Path, output_path: str | Path
) -> dict[str, Any]:
    """Write a byte-stable review bundle and return the payload."""
    bundle = build_review_bundle(graph, graph_path=graph_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle
