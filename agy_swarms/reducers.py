"""§D.3 reducers — pure, total, deterministic merge of node-id-sorted child results.

A reducer is a pure, total, deterministic function of its **sorted** inputs
(``reduce(inputs_sorted_by_node_id) -> merged``, FR-2 [C1]): it reads only the committed
child artifacts, never wall-clock / RNG / completion-order / ambient I/O. ``run_reducer``
**double-executes** each reduction over the identical sorted input and **fails the run on
a divergent merge** (§D.3) — the enforcement that catches an impure ``custom`` reducer
before its result poisons the FR-7 resume cache.

``concat`` collects child artifacts into an ordered ``items`` list (Phase-1 shape; what is
normative is the node-id-sorted order + determinism). ``json_merge`` unions child dicts;
a key conflict resolves to the **earlier node-id** (deterministic, never last-writer-wins)
and emits a ``concern``. Both are total over the empty and single-input cases.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .canonical import canonical
from .types import Reducer

__all__ = ["run_reducer", "ReduceResult", "ReducerError"]

Child = Mapping[str, Any]
CustomReducer = Callable[[Sequence[Child]], dict[str, Any]]


class ReducerError(Exception):
    """Raised on an unknown/unregistered reducer or a non-deterministic merge (§D.3)."""


@dataclass
class ReduceResult:
    """The merged artifact plus any ``concern`` strings raised during merge."""

    artifact: dict[str, Any]
    concerns: list[str] = field(default_factory=list)


def run_reducer(
    reducer: Reducer,
    children: Sequence[Child],
    *,
    registry: Mapping[str, CustomReducer] | None = None,
) -> ReduceResult:
    """Merge ``children`` per ``reducer`` over node-id-sorted input (FR-2/§D.3).

    Double-executes and raises ``ReducerError`` if the two merges are not byte-identical
    under §D.0 canonicalization (the purity guard).
    """
    registry = registry or {}
    ordered = sorted(children, key=lambda c: c["node_id"])
    first = _apply(reducer, ordered, registry)
    second = _apply(reducer, ordered, registry)
    if canonical(first.artifact) != canonical(second.artifact):
        raise ReducerError(
            f"reducer {reducer.kind!r}/{reducer.custom_id!r} is non-deterministic "
            "(divergent merge under double-execution, §D.3)"
        )
    return first


def _apply(
    reducer: Reducer, ordered: list[Child], registry: Mapping[str, CustomReducer]
) -> ReduceResult:
    if reducer.kind == "concat":
        return ReduceResult(artifact={"items": [c["artifact"] for c in ordered]})
    if reducer.kind == "json_merge":
        merged: dict[str, Any] = {}
        concerns: list[str] = []
        for child in ordered:
            for key, value in child["artifact"].items():
                if key in merged:
                    concerns.append(
                        f"json_merge conflict on key {key!r}: kept the earlier "
                        "node-id's value (§D.3)"
                    )
                else:
                    merged[key] = value
        return ReduceResult(artifact=merged, concerns=concerns)
    if reducer.kind == "custom":
        if reducer.custom_id is None:
            raise ReducerError("custom reducer requires custom_id")
        try:
            fn = registry[reducer.custom_id]  # validated at validate_or_die (§D.1)
        except KeyError:
            raise ReducerError(
                f"custom reducer {reducer.custom_id!r} not in REDUCERS registry"
            ) from None
        return ReduceResult(artifact=fn(ordered))
    raise ReducerError(f"unknown reducer kind {reducer.kind!r}")
