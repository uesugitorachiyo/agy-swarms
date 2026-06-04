"""§D.3 reducers — pure, total, deterministic merge of node-id-sorted child results.

A reducer reads ONLY its committed children, in canonical node-id-sorted order (FR-2),
and is byte-identical across executions. The runner double-executes and fails the run on
a divergent merge (the purity enforcement, §D.3) — this is what catches an impure
``custom`` reducer. ``json_merge`` key conflicts resolve by node-id order (earlier wins)
and emit a concern; ``concat``/``json_merge`` are total over the empty/single cases.
"""

import pytest

from agy_swarms.reducers import ReduceResult, ReducerError, run_reducer
from agy_swarms.types import Reducer


def _child(node_id, artifact):
    return {"node_id": node_id, "artifact": artifact}


# --- concat ----------------------------------------------------------------


def test_concat_orders_by_node_id_not_input_order():
    children = [_child("b", {"x": 2}), _child("a", {"x": 1})]
    res = run_reducer(Reducer(kind="concat"), children)
    assert res.artifact == {"items": [{"x": 1}, {"x": 2}]}  # 'a' before 'b'


def test_concat_empty_is_total():
    assert run_reducer(Reducer(kind="concat"), []).artifact == {"items": []}


def test_concat_single_is_total():
    res = run_reducer(Reducer(kind="concat"), [_child("a", {"x": 1})])
    assert res.artifact == {"items": [{"x": 1}]}


# --- json_merge ------------------------------------------------------------


def test_json_merge_combines_disjoint_keys():
    children = [_child("a", {"x": 1}), _child("b", {"y": 2})]
    res = run_reducer(Reducer(kind="json_merge"), children)
    assert res.artifact == {"x": 1, "y": 2}
    assert res.concerns == []


def test_json_merge_conflict_earlier_node_id_wins_with_concern():
    children = [_child("b", {"k": "from_b"}), _child("a", {"k": "from_a"})]
    res = run_reducer(Reducer(kind="json_merge"), children)
    assert res.artifact == {"k": "from_a"}  # 'a' sorts first → wins
    assert len(res.concerns) == 1


def test_json_merge_empty_is_total():
    assert run_reducer(Reducer(kind="json_merge"), []).artifact == {}


# --- custom ----------------------------------------------------------------


def test_custom_reducer_resolved_from_registry():
    def my_sum(children):
        return {"total": sum(c["artifact"]["n"] for c in children)}

    children = [_child("a", {"n": 1}), _child("b", {"n": 2})]
    res = run_reducer(
        Reducer(kind="custom", custom_id="my_sum"), children, registry={"my_sum": my_sum}
    )
    assert res.artifact == {"total": 3}


def test_custom_reducer_sees_node_id_sorted_input():
    seen: list[str] = []

    def rec(children):
        seen.extend(c["node_id"] for c in children)
        return {}

    run_reducer(
        Reducer(kind="custom", custom_id="r"),
        [_child("b", {}), _child("a", {})],
        registry={"r": rec},
    )
    assert seen[:2] == ["a", "b"]


def test_impure_custom_reducer_fails_double_execution():
    counter = {"n": 0}

    def impure(children):
        counter["n"] += 1
        return {"call": counter["n"]}

    with pytest.raises(ReducerError):
        run_reducer(
            Reducer(kind="custom", custom_id="imp"),
            [_child("a", {})],
            registry={"imp": impure},
        )


def test_unknown_custom_id_raises_reducer_error():
    with pytest.raises(ReducerError):
        run_reducer(Reducer(kind="custom", custom_id="missing"), [], registry={})


def test_run_reducer_returns_reduce_result():
    assert isinstance(run_reducer(Reducer(kind="concat"), []), ReduceResult)
