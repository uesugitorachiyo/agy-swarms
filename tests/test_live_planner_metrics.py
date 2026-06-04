"""D3.4 live-planner bounded-invariants soft metric."""

from pathlib import Path

from agy_swarms.live_planner_metrics import (
    edge_set_jaccard,
    evaluate_live_planner_soft_metrics,
)
from agy_swarms.types import Caps, NodeSpec, TaskGraph


def _node(node_id: str, role: str, *, deps: list[str] | None = None) -> NodeSpec:
    return NodeSpec(
        id=node_id,
        role=role,
        objective=f"{role} {node_id}",
        dependencies=deps or [],
        required_capabilities=["code"] if role == "worker" else [],
        caps=Caps(max_output_tokens=100, max_thinking_tokens=50),
    )


def _chain(prefix: str) -> TaskGraph:
    return TaskGraph(
        nodes=[
            _node(f"{prefix}-plan", "planner"),
            _node(f"{prefix}-a", "worker", deps=[f"{prefix}-plan"]),
            _node(f"{prefix}-b", "worker", deps=[f"{prefix}-a"]),
        ],
        seed=1,
    )


def _fanout(prefix: str) -> TaskGraph:
    return TaskGraph(
        nodes=[
            _node(f"{prefix}-plan", "planner"),
            _node(f"{prefix}-a", "worker", deps=[f"{prefix}-plan"]),
            _node(f"{prefix}-b", "worker", deps=[f"{prefix}-plan"]),
        ],
        seed=2,
    )


def test_live_planner_soft_metric_records_valid_invariants_and_jaccard():
    result = evaluate_live_planner_soft_metrics(
        [_chain("one"), _chain("two")],
        router_cases_path=Path("benchmarks/router_cases.json"),
        config_path=Path("config/defaults.toml"),
        budget_limit_tokens=1_000,
    )

    assert result["gate"] == "AC-3/live-planner-soft"
    assert result["hard_gate"] is False
    assert result["passed"] is True
    assert result["jaccard_threshold"] == 0.70
    assert result["edge_set_jaccard"] == 1.0
    assert result["concerns"] == []
    assert result["invariants"] == {
        "schema_valid": True,
        "acyclic": True,
        "budget_valid": True,
        "dependency_complete": True,
        "router_correct": True,
    }


def test_live_planner_instability_below_j_is_recorded_as_non_gating_concern():
    result = evaluate_live_planner_soft_metrics(
        [_chain("one"), _fanout("two")],
        router_cases_path=Path("benchmarks/router_cases.json"),
        config_path=Path("config/defaults.toml"),
        budget_limit_tokens=1_000,
    )

    assert result["passed"] is True
    assert result["edge_set_jaccard"] == edge_set_jaccard([_chain("one"), _fanout("two")])
    assert result["edge_set_jaccard"] < result["jaccard_threshold"]
    assert "planner-instability" in result["concerns"]


def test_budget_invalidity_is_recorded_without_turning_live_shape_into_hard_gate():
    result = evaluate_live_planner_soft_metrics(
        [_chain("one")],
        router_cases_path=Path("benchmarks/router_cases.json"),
        config_path=Path("config/defaults.toml"),
        budget_limit_tokens=100,
    )

    assert result["hard_gate"] is False
    assert result["passed"] is True
    assert result["invariants"]["budget_valid"] is False
    assert "budget-invalid" in result["concerns"]
