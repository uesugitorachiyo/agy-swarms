"""AC-0.5 — in-memory recorded-graph store (D-3; FR-3.1/§D.6).

Keyed by ``(task_sha, context_hash)``. A SQLite-backed fold into the checkpoint epoch is
deferred (D-3); the in-memory map is the Phase-1 recording substrate for replay.
"""

from agy_swarms.graph_store import GraphStore
from agy_swarms.types import NodeSpec, TaskGraph


def _g():
    return TaskGraph(nodes=[NodeSpec(id="a", role="worker", objective="o")], edges=[])


def test_get_returns_none_for_unrecorded_key():
    assert GraphStore().get(("task-sha", "ctx-hash")) is None


def test_put_then_get_returns_the_recorded_graph():
    store = GraphStore()
    graph = _g()
    store.put(("task-sha", "ctx-hash"), graph)
    assert store.get(("task-sha", "ctx-hash")) is graph


def test_distinct_keys_are_isolated():
    store = GraphStore()
    g1, g2 = _g(), _g()
    store.put(("t", "c1"), g1)
    store.put(("t", "c2"), g2)
    assert store.get(("t", "c1")) is g1
    assert store.get(("t", "c2")) is g2
