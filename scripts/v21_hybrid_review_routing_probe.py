#!/usr/bin/env python3
"""Verify v0.21 graph semantics and optional CLI reviewer/closer routing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agy_swarms.graph_io import load_graph
from agy_swarms.hybrid_review import ReviewRole, route_review_role


def main() -> int:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agy-v21-hybrid-review-routing-") as tmp:
        graph_path = Path(tmp) / "edge-only-graph.json"
        graph_path.write_text(
            json.dumps(
                {
                    "nodes": [
                        {"id": "implement", "role": "worker", "objective": "do work"},
                        {"id": "review", "role": "reviewer", "objective": "review work"},
                    ],
                    "edges": [["implement", "review"]],
                }
            ),
            encoding="utf-8",
        )
        graph = load_graph(graph_path)
    if graph.nodes[1].dependencies != ["implement"]:
        errors.append(f"edge dependencies were {graph.nodes[1].dependencies!r}")

    default_reviewer = route_review_role(ReviewRole.REVIEWER)
    default_closer = route_review_role(ReviewRole.CLOSER)
    codex_reviewer = route_review_role(ReviewRole.REVIEWER, adapter="codex")
    codex_closer = route_review_role(ReviewRole.CLOSER, adapter="codex")
    claude_closer = route_review_role(ReviewRole.CLOSER, adapter="claude")

    if default_reviewer.transport != "agy" or default_reviewer.auth != "oauth":
        errors.append("default reviewer did not stay on agy oauth")
    if default_closer.model != "gemini-3.5-flash":
        errors.append("default closer did not stay on Gemini Flash")
    if codex_reviewer.transport != "codex-cli" or codex_reviewer.auth != "cli-session":
        errors.append("codex reviewer did not use local CLI session")
    if codex_closer.transport != "codex-cli" or codex_closer.auth != "cli-session":
        errors.append("codex closer did not use local CLI session")
    if claude_closer.transport != "claude-code-cli" or claude_closer.auth != "cli-session":
        errors.append("claude closer did not use local CLI session")

    routes = [
        default_reviewer.to_json(),
        default_closer.to_json(),
        codex_reviewer.to_json(),
        codex_closer.to_json(),
        claude_closer.to_json(),
    ]
    if any(route.get("read_only") is not True for route in routes):
        errors.append("all review routes must be read-only")
    if any(route.get("auth") == "api_key" for route in routes):
        errors.append("review routing must not default to API-key auth")

    payload = {
        "passed": not errors,
        "errors": errors,
        "edge_dependencies": graph.nodes[1].dependencies,
        "routes": routes,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
