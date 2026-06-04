"""AC-3 graph-equivalence semantics (SPEC:484).

Graph shape equivalence ignores planner-authored ids and objective prose. It is only the
node-role multiset plus dependency-edge set after canonical id-renaming.
"""

from agy_swarms.graph_equivalence import equivalent_graph_shape, graph_signature
from agy_swarms.types import NodeSpec, TaskGraph


def _node(node_id: str, role: str, *, objective: str = "do it", deps: list[str] | None = None):
    return NodeSpec(id=node_id, role=role, objective=objective, dependencies=deps or [])


def test_same_shape_with_different_node_ids_is_equivalent():
    left = TaskGraph(
        nodes=[
            _node("plan", "planner"),
            _node("write", "worker", deps=["plan"]),
            _node("review", "reviewer", deps=["write"]),
        ],
        edges=[("plan", "write"), ("write", "review")],
    )
    right = TaskGraph(
        nodes=[
            _node("p0", "planner"),
            _node("w9", "worker", deps=["p0"]),
            _node("r3", "reviewer", deps=["w9"]),
        ],
        edges=[("p0", "w9"), ("w9", "r3")],
    )

    assert equivalent_graph_shape(left, right)
    assert graph_signature(left) == graph_signature(right)


def test_objective_prose_does_not_affect_equivalence():
    left = TaskGraph(
        nodes=[_node("a", "worker", objective="summarize alpha")],
    )
    right = TaskGraph(
        nodes=[_node("z", "worker", objective="rewrite the entire project")],
    )

    assert equivalent_graph_shape(left, right)


def test_different_role_multiset_is_not_equivalent():
    left = TaskGraph(nodes=[_node("a", "planner"), _node("b", "worker", deps=["a"])])
    right = TaskGraph(nodes=[_node("x", "worker"), _node("y", "worker", deps=["x"])])

    assert not equivalent_graph_shape(left, right)


def test_different_dependency_edge_set_is_not_equivalent():
    chain = TaskGraph(
        nodes=[
            _node("root", "planner"),
            _node("a", "worker", deps=["root"]),
            _node("b", "worker", deps=["a"]),
        ]
    )
    fanout = TaskGraph(
        nodes=[
            _node("p", "planner"),
            _node("x", "worker", deps=["p"]),
            _node("y", "worker", deps=["p"]),
        ]
    )

    assert not equivalent_graph_shape(chain, fanout)


def test_permutation_of_same_role_nodes_can_still_match():
    left = TaskGraph(
        nodes=[
            _node("source", "planner"),
            _node("lint", "worker", deps=["source"]),
            _node("test", "worker", deps=["source"]),
            _node("close", "reviewer", deps=["lint", "test"]),
        ]
    )
    right = TaskGraph(
        nodes=[
            _node("p", "planner"),
            _node("w2", "worker", deps=["p"]),
            _node("w1", "worker", deps=["p"]),
            _node("r", "reviewer", deps=["w1", "w2"]),
        ]
    )

    assert equivalent_graph_shape(left, right)


def test_taskgraph_edges_are_included_in_effective_edge_set():
    left = TaskGraph(
        nodes=[_node("a", "worker"), _node("b", "worker")],
        edges=[("a", "b")],
    )
    right = TaskGraph(nodes=[_node("x", "worker"), _node("y", "worker")])

    assert not equivalent_graph_shape(left, right)
