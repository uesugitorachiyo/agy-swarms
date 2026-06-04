"""Read-only graph preflight summaries for local runner workflows."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .types import TaskGraph

_SENSITIVE_COMMAND_PART = re.compile(
    r"(api[_-]?key|auth|bearer|credential|oauth|pass(word)?|secret|token)"
    r"|[\\/]"
    r"|[$@]"
    r"|[A-Za-z0-9_./+=:-]{32,}",
    re.IGNORECASE,
)


def summarize_graph_preflight(
    graph: TaskGraph, *, include_command_review: bool = False
) -> dict[str, Any]:
    """Return deterministic JSON-safe graph metadata without dispatching nodes."""
    node_ids = sorted(node.id for node in graph.nodes)
    dependencies_by_node: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    dependents_by_node: dict[str, set[str]] = {node_id: set() for node_id in node_ids}

    for node in graph.nodes:
        dependencies_by_node[node.id].update(str(dep) for dep in node.dependencies)
        for dep in node.dependencies:
            dep_id = str(dep)
            if dep_id in dependents_by_node:
                dependents_by_node[dep_id].add(node.id)

    for source, target in graph.edges:
        dependencies_by_node[target].add(source)
        dependents_by_node[source].add(target)

    payload = {
        "status": "valid",
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "role_counts": dict(sorted(Counter(node.role for node in graph.nodes).items())),
        "command_node_ids": sorted(node.id for node in graph.nodes if node.command),
        "root_nodes": [node_id for node_id in node_ids if not dependencies_by_node[node_id]],
        "leaf_nodes": [node_id for node_id in node_ids if not dependents_by_node[node_id]],
        "commands_executed": False,
        "dependency_fan_out": {
            node_id: {
                "dependencies": sorted(dependencies_by_node[node_id]),
                "dependents": sorted(dependents_by_node[node_id]),
                "fan_in": len(dependencies_by_node[node_id]),
                "fan_out": len(dependents_by_node[node_id]),
            }
            for node_id in node_ids
        },
    }
    if include_command_review:
        payload["commands_executed"] = False
        payload["command_review"] = _summarize_command_review(graph)
    return payload


def _summarize_command_review(graph: TaskGraph) -> dict[str, dict[str, Any]]:
    return {
        node.id: {
            "executable": _redact_command_part(node.command[0]),
            "argv_count": len(node.command),
            "redacted_argv": [_redact_command_part(part) for part in node.command],
            "argv_sha256": hashlib.sha256(
                json.dumps(
                    node.command,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest(),
        }
        for node in sorted(graph.nodes, key=lambda item: item.id)
        if node.command
    }


def _redact_command_part(part: str) -> str:
    if _SENSITIVE_COMMAND_PART.search(part):
        return "<redacted>"
    return part


def load_mock_bundle(path: str | Path) -> dict[str, Any]:
    """Load a custom pre-saved execution bundle mapping node IDs to mock outcomes.

    Supports both flat node-to-outcome mapping and full run reports containing
    a 'results' dictionary.
    """
    from .adapters.scripted import CannedResult
    from .types import ErrorClass

    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Failed to load mock bundle JSON: {exc}")

    if not isinstance(data, dict):
        raise ValueError("Mock bundle must be a JSON object")

    results_map = data.get("results") if "results" in data else data
    if not isinstance(results_map, dict):
        raise ValueError("Mock bundle results must be a JSON object mapping node IDs to results")

    transcript = {}
    for node_id, result in results_map.items():
        if not isinstance(result, dict):
            continue

        err_str = result.get("error_class", "NONE")
        try:
            error_class = (
                ErrorClass[err_str] if err_str in ErrorClass.__members__ else ErrorClass(err_str)
            )
        except Exception:
            error_class = ErrorClass.NONE

        transcript[node_id] = CannedResult(
            status=result.get("status", "succeeded"),
            artifact=result.get("artifact", {}),
            error_class=error_class,
            token_usage=result.get("token_usage"),
            cost_usd=float(result.get("cost_usd", 0.0)),
            concerns=list(result.get("concerns", [])),
            blockers=[dict(b) for b in result.get("blockers", []) if isinstance(b, dict)],
            changed_files=list(result.get("changed_files", [])),
            pointers=list(result.get("pointers", [])),
        )
    return transcript
