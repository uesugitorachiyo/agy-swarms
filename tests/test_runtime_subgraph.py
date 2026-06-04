"""D3.5 runtime subgraph growth and bounded replan."""

import pytest

from agy_swarms.planner import (
    ReplanExhausted,
    bounded_replan,
    merge_runtime_subgraph,
)
from agy_swarms.types import NodeSpec, TaskGraph, TaskSpec
from agy_swarms.validate import ValidationError


def _node(node_id: str, *, deps: list[str] | None = None) -> NodeSpec:
    return NodeSpec(
        id=node_id,
        role="worker",
        objective=f"work {node_id}",
        dependencies=deps or [],
        required_capabilities=["code"],
    )


def test_runtime_subgraph_validate_then_merge_accepts_valid_growth():
    base = TaskGraph(nodes=[_node("root")], edges=[])
    subgraph = TaskGraph(nodes=[_node("child", deps=["root"])], edges=[("root", "child")])

    merged = merge_runtime_subgraph(base, subgraph)

    assert [node.id for node in merged.nodes] == ["root", "child"]
    assert merged.edges == [("root", "child")]
    assert [node.id for node in base.nodes] == ["root"]  # base graph is not mutated


def test_runtime_subgraph_rejects_invalid_growth_before_merge():
    base = TaskGraph(nodes=[_node("root")], edges=[])
    subgraph = TaskGraph(nodes=[_node("child", deps=["missing"])])

    with pytest.raises(ValidationError, match="missing"):
        merge_runtime_subgraph(base, subgraph)

    assert [node.id for node in base.nodes] == ["root"]


def test_runtime_subgraph_rejects_duplicate_node_id_before_merge():
    base = TaskGraph(nodes=[_node("root")], edges=[])
    subgraph = TaskGraph(nodes=[_node("root")])

    with pytest.raises(ValidationError, match="duplicate"):
        merge_runtime_subgraph(base, subgraph)


class _Replanner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def replan(self, task_spec, graph, *, failed_node_id, attempt):
        self.calls += 1
        return self.outputs.pop(0)


def test_bounded_replan_succeeds_after_invalid_attempt():
    base = TaskGraph(nodes=[_node("root")])
    replanner = _Replanner(
        [
            TaskGraph(nodes=[_node("bad", deps=["missing"])]),
            TaskGraph(nodes=[_node("fixed", deps=["root"])]),
        ]
    )

    report = bounded_replan(
        TaskSpec(task="repair", model_pins={"default": "flash"}),
        replanner,
        base_graph=base,
        failed_node_id="root",
        max_replans=2,
    )

    assert report.attempts == 2
    assert report.validation_errors == ("node 'bad' depends on unknown node 'missing'",)
    assert [node.id for node in report.graph.nodes] == ["root", "fixed"]


def test_bounded_replan_hard_fails_with_last_validation_error_when_exhausted():
    base = TaskGraph(nodes=[_node("root")])
    replanner = _Replanner(
        [
            TaskGraph(nodes=[_node("bad1", deps=["missing1"])]),
            TaskGraph(nodes=[_node("bad2", deps=["missing2"])]),
        ]
    )

    with pytest.raises(ReplanExhausted, match="missing2") as excinfo:
        bounded_replan(
            TaskSpec(task="repair", model_pins={"default": "flash"}),
            replanner,
            base_graph=base,
            failed_node_id="root",
            max_replans=2,
        )

    assert excinfo.value.attempts == 2
    assert excinfo.value.validation_errors[-1] == "node 'bad2' depends on unknown node 'missing2'"
