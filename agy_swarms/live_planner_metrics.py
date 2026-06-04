"""D3.4 live-planner bounded-invariants soft metrics."""

from __future__ import annotations

import json
import tomllib
from itertools import combinations
from pathlib import Path
from typing import Any

from .budget import est
from .graph_equivalence import graph_signature
from .routing import route_complexity
from .types import TaskGraph
from .validate import ValidationError, validate_or_die

__all__ = ["edge_set_jaccard", "evaluate_live_planner_soft_metrics"]


def edge_set_jaccard(graphs: list[TaskGraph]) -> float:
    """Return the minimum pairwise dependency-edge-set Jaccard across planner outputs."""
    if len(graphs) < 2:
        return 1.0
    scores = [_edge_jaccard(left, right) for left, right in combinations(graphs, 2)]
    return min(scores)


def evaluate_live_planner_soft_metrics(
    graphs: list[TaskGraph],
    *,
    router_cases_path: Path,
    config_path: Path,
    budget_limit_tokens: int,
) -> dict[str, Any]:
    """Evaluate AC-3 live-planner evidence without making graph shape a hard gate.

    Live LLM graph shape is report-only per AC-3. Bounded invariants and Jaccard are made
    observable; instability below the pinned threshold is emitted as a concern.
    """
    config = tomllib.loads(config_path.read_text())
    threshold = float(config.get("phase3", {}).get("planner_edge_jaccard_j", 0.70))
    seed_count = int(config.get("phase3", {}).get("planner_seed_count", len(graphs)))

    validation = [_validate_graph(graph) for graph in graphs]
    router_correct = _router_fixture_correct(router_cases_path)
    invariants = {
        "schema_valid": all(item["schema_valid"] for item in validation),
        "acyclic": all(item["acyclic"] for item in validation),
        "budget_valid": all(_graph_budget_tokens(graph) <= budget_limit_tokens for graph in graphs),
        "dependency_complete": all(item["dependency_complete"] for item in validation),
        "router_correct": router_correct,
    }
    jaccard = edge_set_jaccard(graphs)
    concerns: list[str] = []
    if jaccard < threshold:
        concerns.append("planner-instability")
    if not invariants["budget_valid"]:
        concerns.append("budget-invalid")
    if not invariants["schema_valid"]:
        concerns.append("schema-invalid")
    if not invariants["acyclic"]:
        concerns.append("cycle-detected")
    if not invariants["dependency_complete"]:
        concerns.append("dependency-incomplete")
    if not invariants["router_correct"]:
        concerns.append("router-mismatch")

    return {
        "gate": "AC-3/live-planner-soft",
        "hard_gate": False,
        "passed": True,
        "graph_count": len(graphs),
        "configured_seed_count": seed_count,
        "jaccard_threshold": threshold,
        "edge_set_jaccard": jaccard,
        "invariants": invariants,
        "validation": validation,
        "concerns": concerns,
    }


def _edge_jaccard(left: TaskGraph, right: TaskGraph) -> float:
    left_edges = set(graph_signature(left)[1])
    right_edges = set(graph_signature(right)[1])
    union = left_edges | right_edges
    if not union:
        return 1.0
    return len(left_edges & right_edges) / len(union)


def _validate_graph(graph: TaskGraph) -> dict[str, Any]:
    try:
        validate_or_die(graph)
    except ValidationError as exc:
        message = str(exc)
        return {
            "valid": False,
            "schema_valid": False,
            "acyclic": "cycle" not in message,
            "dependency_complete": "depends on unknown" not in message,
            "error": message,
        }
    return {
        "valid": True,
        "schema_valid": True,
        "acyclic": True,
        "dependency_complete": True,
        "error": "",
    }


def _graph_budget_tokens(graph: TaskGraph) -> int:
    return sum(est(node) for node in graph.nodes)


def _router_fixture_correct(router_cases_path: Path) -> bool:
    cases = json.loads(router_cases_path.read_text())
    return all(
        route_complexity(case["task"]).route.value == case["expected_complexity_route"]
        for case in cases
    )
