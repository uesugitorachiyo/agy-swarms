"""Conductor reducer-node execution (§D.3 / FR-2 [C1]).

The conductor must execute a ``role=="reducer"`` node by merging its committed
dependency artifacts through ``reducers.run_reducer`` (node-id-sorted, double-executed
for purity) instead of dispatching it to the worker adapter — the fan-out→reduce shape
the whole TaskGraph engine exists for. Reducer nodes are code-side and zero-token, yet
still flow through the normal reserve→commit→journal→cache machinery, so a reducer result
is cacheable on resume like any node.
"""

from dataclasses import asdict

from agy_swarms.canonical import canonical
from agy_swarms.checkpoint import Checkpoint
from agy_swarms.conductor import Conductor
from agy_swarms.types import (
    NodeSpec,
    NodeStatus,
    Reducer,
    RunStatus,
    TaskGraph,
)
from tests.conductor_support import LIMIT as _LIMIT
from tests.conductor_support import FakeAdapter
from tests.conductor_support import envelope as _env
from tests.conductor_support import epoch as _epoch


def _fanout_reduce_graph(reducer: Reducer, *, a_art, b_art):
    """root → {a, b} → r(reducer over a, b)."""
    root = NodeSpec(id="root", role="worker", objective="root")
    a = NodeSpec(id="a", role="worker", objective="a", dependencies=["root"])
    b = NodeSpec(id="b", role="worker", objective="b", dependencies=["root"])
    r = NodeSpec(id="r", role="reducer", objective="r", dependencies=["a", "b"], reducer=reducer)
    graph = TaskGraph(
        nodes=[root, a, b, r],
        edges=[("root", "a"), ("root", "b"), ("a", "r"), ("b", "r")],
    )
    adapter = FakeAdapter(
        {
            "root": [_env(artifact={})],
            "a": [_env(artifact=a_art)],
            "b": [_env(artifact=b_art)],
            # canned result the reducer would (wrongly) return if dispatched to the adapter:
            "r": [_env(artifact={"via_adapter": True})],
        }
    )
    return graph, adapter


def test_reducer_node_json_merge_unions_child_artifacts():
    graph, adapter = _fanout_reduce_graph(
        Reducer(kind="json_merge"), a_art={"x": 1}, b_art={"y": 2}
    )
    report = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=4).run()
    assert report.status == RunStatus.SUCCEEDED
    assert report.results["r"].artifact == {"x": 1, "y": 2}  # merged, not the adapter canned


def test_reducer_node_does_not_dispatch_to_the_adapter():
    graph, adapter = _fanout_reduce_graph(
        Reducer(kind="json_merge"), a_art={"x": 1}, b_art={"y": 2}
    )
    Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=4).run()
    assert "r" not in adapter.calls  # reducer is code-side, never an adapter call
    assert sorted(adapter.calls) == ["a", "b", "root"]


def test_reducer_node_concat_orders_children_by_node_id():
    graph, adapter = _fanout_reduce_graph(
        Reducer(kind="concat"), a_art={"v": "a"}, b_art={"v": "b"}
    )
    report = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=4).run()
    # node-id-sorted: a before b, independent of dispatch/completion order (FR-2 [C1])
    assert report.results["r"].artifact == {"items": [{"v": "a"}, {"v": "b"}]}


def test_reducer_json_merge_conflict_keeps_earlier_node_id_and_emits_concern():
    graph, adapter = _fanout_reduce_graph(
        Reducer(kind="json_merge"), a_art={"k": "from_a"}, b_art={"k": "from_b"}
    )
    report = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=4).run()
    assert report.results["r"].artifact == {"k": "from_a"}  # earlier node-id wins
    assert report.results["r"].concerns  # conflict surfaced as a concern, not silent


def test_reducer_node_marks_succeeded_and_spends_zero():
    graph, adapter = _fanout_reduce_graph(
        Reducer(kind="json_merge"), a_art={"x": 1}, b_art={"y": 2}
    )
    cond = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=4)
    report = cond.run()
    assert report.states["r"] == NodeStatus.SUCCEEDED
    assert cond.runtime["r"].budget_consumed["tokens"] == 0  # reducers are zero-token


def test_reducer_run_is_byte_identical_across_two_runs():
    g1, a1 = _fanout_reduce_graph(Reducer(kind="json_merge"), a_art={"x": 1}, b_art={"y": 2})
    g2, a2 = _fanout_reduce_graph(Reducer(kind="json_merge"), a_art={"x": 1}, b_art={"y": 2})
    r1 = Conductor(g1, a1, limit=_LIMIT, epoch=_epoch(), cap=4).run()
    r2 = Conductor(g2, a2, limit=_LIMIT, epoch=_epoch(), cap=4).run()
    assert canonical(asdict(r1)) == canonical(asdict(r2))


def test_custom_reducer_resolved_from_registry():
    calls: list[int] = []

    def pick_max(children):  # pure: deterministic over sorted children
        calls.append(len(children))
        return {"max": max(c["artifact"]["n"] for c in children)}

    graph, adapter = _fanout_reduce_graph(
        Reducer(kind="custom", custom_id="pick_max"), a_art={"n": 3}, b_art={"n": 7}
    )
    report = Conductor(
        graph,
        adapter,
        limit=_LIMIT,
        epoch=_epoch(),
        cap=4,
        reducer_registry={"pick_max": pick_max},
    ).run()
    assert report.results["r"].artifact == {"max": 7}
    assert calls  # the registered custom reducer was invoked


def test_reducer_node_caches_on_resume_without_recompute(tmp_path):
    path = tmp_path / "ck.db"
    calls: list[str] = []

    def recording(children):
        calls.append("ran")
        return {"sum": sum(c["artifact"]["n"] for c in children)}

    g1, a1 = _fanout_reduce_graph(
        Reducer(kind="custom", custom_id="recording"), a_art={"n": 1}, b_art={"n": 2}
    )
    with Checkpoint(path, _epoch()) as ck:
        Conductor(
            g1,
            a1,
            limit=_LIMIT,
            epoch=_epoch(),
            cap=4,
            checkpoint=ck,
            reducer_registry={"recording": recording},
        ).run()
    assert calls  # ran during the first run (double-executed for purity)
    calls.clear()
    g2, a2 = _fanout_reduce_graph(
        Reducer(kind="custom", custom_id="recording"), a_art={"n": 1}, b_art={"n": 2}
    )
    with Checkpoint(path, _epoch()) as ck2:
        report = Conductor(
            g2,
            a2,
            limit=_LIMIT,
            epoch=_epoch(),
            cap=4,
            checkpoint=ck2,
            reducer_registry={"recording": recording},
        ).run()
    assert calls == []  # resume: reducer node cache-hit, not recomputed (FR-7)
    assert report.results["r"].artifact == {"sum": 3}
