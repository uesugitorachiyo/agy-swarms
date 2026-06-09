"""JSON graph intake for local runner workflows."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from .types import NodeSpec, TaskGraph
from .validate import ValidationError, validate_or_die


class GraphLoadError(ValueError):
    """Raised when a graph JSON file cannot be parsed into a valid TaskGraph."""


_SENSITIVE_HINT = re.compile(
    r"(api[_-]?key|auth|bearer|credential|oauth|pass(word)?|secret|token)",
    re.IGNORECASE,
)
_OPAQUE_VALUE = re.compile(r"[A-Za-z0-9_./+=:-]{32,}")


def load_graph(path: str | Path) -> TaskGraph:
    """Load and validate a TaskGraph from a JSON file."""
    graph_path = Path(path)
    try:
        raw = json.loads(graph_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GraphLoadError(f"cannot read graph file: {_safe_path_name(graph_path)}") from exc
    except json.JSONDecodeError as exc:
        raise GraphLoadError(f"invalid graph JSON: {exc}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list):
        raise GraphLoadError("graph JSON must contain a nodes list")

    edges = [_edge_from_json(edge) for edge in raw.get("edges", ())]
    nodes = [_node_from_json(index, item) for index, item in enumerate(raw["nodes"])]
    _validate_edge_endpoints(nodes, edges)
    nodes = _materialize_edge_dependencies(nodes, edges)
    graph = TaskGraph(nodes=nodes, edges=edges)
    try:
        validate_or_die(graph)
    except ValidationError as exc:
        raise GraphLoadError(_sanitize_validation_message(str(exc), nodes)) from exc
    return graph


def _node_from_json(index: int, item: Any) -> NodeSpec:
    if not isinstance(item, dict):
        raise GraphLoadError(f"node[{index}] must be an object")
    try:
        node_id = str(item["id"])
        return NodeSpec(
            id=node_id,
            role=str(item.get("role", "worker")),
            objective=str(item.get("objective", "")),
            dependencies=list(item.get("dependencies", [])),
            command=_command_from_json(index, node_id, item["command"])
            if "command" in item
            else None,
        )
    except KeyError as exc:
        raise GraphLoadError(f"node[{index}] missing field: {exc.args[0]}") from exc


def _command_from_json(index: int, node_id: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(part, str) for part in value):
        raise GraphLoadError(
            f"command for {_node_ref(index, node_id)} must be a non-empty array of strings"
        )
    return list(value)


def _edge_from_json(item: Any) -> tuple[str, str]:
    if (
        not isinstance(item, list | tuple)
        or len(item) != 2
        or not all(isinstance(part, str) for part in item)
    ):
        raise GraphLoadError("each edge must be a two-item string array")
    return (item[0], item[1])


def _validate_edge_endpoints(nodes: list[NodeSpec], edges: list[tuple[str, str]]) -> None:
    node_ids = {node.id for node in nodes}
    for index, (left, right) in enumerate(edges):
        if left not in node_ids or right not in node_ids:
            missing = []
            if left not in node_ids:
                missing.append(f"source={_safe_identifier(left)}")
            if right not in node_ids:
                missing.append(f"target={_safe_identifier(right)}")
            raise GraphLoadError(f"unknown edge endpoint at edge[{index}]: {', '.join(missing)}")


def _materialize_edge_dependencies(
    nodes: list[NodeSpec], edges: list[tuple[str, str]]
) -> list[NodeSpec]:
    dependencies_by_target: dict[str, list[str]] = {
        node.id: list(node.dependencies) for node in nodes
    }
    for source, target in edges:
        target_dependencies = dependencies_by_target[target]
        if source not in target_dependencies:
            target_dependencies.append(source)
    return [replace(node, dependencies=dependencies_by_target[node.id]) for node in nodes]


def _node_ref(index: int, node_id: str) -> str:
    label = _safe_identifier(node_id)
    if label == "<redacted>":
        return f"node[{index}] <redacted>"
    return f"node {label}"


def _safe_path_name(path: Path) -> str:
    return _safe_identifier(path.name)


def _safe_identifier(value: str) -> str:
    if _looks_sensitive(value):
        return "<redacted>"
    return repr(value)


def _looks_sensitive(value: str) -> bool:
    return (
        bool(_SENSITIVE_HINT.search(value))
        or "/" in value
        or "\\" in value
        or "$" in value
        or "@" in value
        or bool(_OPAQUE_VALUE.fullmatch(value))
    )


def _sanitize_validation_message(message: str, nodes: list[NodeSpec]) -> str:
    sanitized = message
    for node in nodes:
        if _looks_sensitive(node.id):
            sanitized = sanitized.replace(repr(node.id), "<redacted>")
            sanitized = sanitized.replace(node.id, "<redacted>")
        for dep in node.dependencies:
            dep_str = str(dep)
            if _looks_sensitive(dep_str):
                sanitized = sanitized.replace(repr(dep_str), "<redacted>")
                sanitized = sanitized.replace(dep_str, "<redacted>")
    return sanitized
