"""AC-3 graph-equivalence primitives.

AC-3 defines graph equivalence as identical node-role multiset plus identical dependency
edge set after canonical id-renaming. Planner prose is intentionally excluded.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from itertools import permutations, product
from typing import TypeAlias

from .types import TaskGraph

__all__ = ["GraphSignature", "equivalent_graph_shape", "graph_signature"]

GraphSignature: TypeAlias = tuple[tuple[str, ...], tuple[tuple[int, int], ...]]


def graph_signature(graph: TaskGraph) -> GraphSignature:
    """Return a canonical shape signature independent of node ids/objectives."""
    roles = tuple(sorted(node.role for node in graph.nodes))
    if not graph.nodes:
        return (roles, ())

    node_index = _node_index(graph)
    edges = _effective_edges(graph, node_index)
    role_groups: dict[str, list[int]] = defaultdict(list)
    for index, node in enumerate(graph.nodes):
        role_groups[node.role].append(index)

    canonical_slots: dict[str, list[int]] = {}
    offset = 0
    for role in sorted(role_groups):
        count = len(role_groups[role])
        canonical_slots[role] = list(range(offset, offset + count))
        offset += count

    best_edges: tuple[tuple[int, int], ...] | None = None
    for choices in product(
        *[permutations(role_groups[role], len(role_groups[role])) for role in sorted(role_groups)]
    ):
        mapping: dict[int, int] = {}
        for role, ordered_originals in zip(sorted(role_groups), choices, strict=True):
            for original, canonical in zip(ordered_originals, canonical_slots[role], strict=True):
                mapping[original] = canonical
        candidate = tuple(sorted((mapping[src], mapping[dst]) for src, dst in edges))
        if best_edges is None or candidate < best_edges:
            best_edges = candidate

    return (roles, best_edges or ())


def equivalent_graph_shape(left: TaskGraph, right: TaskGraph) -> bool:
    """Return whether two graphs are equivalent under AC-3 id-renaming."""
    if len(left.nodes) != len(right.nodes):
        return False
    if _role_counts(left) != _role_counts(right):
        return False

    left_index = _node_index(left)
    right_index = _node_index(right)
    left_edges = _effective_edges(left, left_index)
    right_edges = _effective_edges(right, right_index)
    if len(left_edges) != len(right_edges):
        return False

    left_adj = _adjacency(left_edges)
    right_adj = _adjacency(right_edges)
    candidates: dict[int, list[int]] = {}
    for left_pos, left_node in enumerate(left.nodes):
        candidates[left_pos] = [
            right_pos
            for right_pos, right_node in enumerate(right.nodes)
            if right_node.role == left_node.role
            and _degree_profile(left_pos, left, left_adj)
            == _degree_profile(right_pos, right, right_adj)
        ]
        if not candidates[left_pos]:
            return False

    order = sorted(range(len(left.nodes)), key=lambda pos: (len(candidates[pos]), pos))
    return _has_isomorphism(
        order=order,
        candidates=candidates,
        left_edges=left_edges,
        right_edges=right_edges,
        mapping={},
        used_right=set(),
    )


def _node_index(graph: TaskGraph) -> dict[str, int]:
    return {node.id: index for index, node in enumerate(graph.nodes)}


def _role_counts(graph: TaskGraph) -> Counter[str]:
    return Counter(node.role for node in graph.nodes)


def _effective_edges(graph: TaskGraph, node_index: Mapping[str, int]) -> frozenset[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for node in graph.nodes:
        dst = node_index[node.id]
        for dep in node.dependencies:
            edges.add((node_index[dep], dst))
    for src_id, dst_id in graph.edges:
        edges.add((node_index[src_id], node_index[dst_id]))
    return frozenset(edges)


def _adjacency(
    edges: frozenset[tuple[int, int]],
) -> dict[int, tuple[tuple[int, ...], tuple[int, ...]]]:
    incoming: dict[int, list[int]] = defaultdict(list)
    outgoing: dict[int, list[int]] = defaultdict(list)
    for src, dst in edges:
        outgoing[src].append(dst)
        incoming[dst].append(src)
    return {
        node: (tuple(sorted(incoming[node])), tuple(sorted(outgoing[node])))
        for node in set(incoming) | set(outgoing)
    }


def _degree_profile(
    node_pos: int,
    graph: TaskGraph,
    adjacency: Mapping[int, tuple[tuple[int, ...], tuple[int, ...]]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    incoming, outgoing = adjacency.get(node_pos, ((), ()))
    return (
        tuple(sorted(graph.nodes[src].role for src in incoming)),
        tuple(sorted(graph.nodes[dst].role for dst in outgoing)),
    )


def _has_isomorphism(
    *,
    order: list[int],
    candidates: Mapping[int, list[int]],
    left_edges: frozenset[tuple[int, int]],
    right_edges: frozenset[tuple[int, int]],
    mapping: dict[int, int],
    used_right: set[int],
) -> bool:
    if len(mapping) == len(order):
        mapped_edges = frozenset((mapping[src], mapping[dst]) for src, dst in left_edges)
        return mapped_edges == right_edges

    left_pos = order[len(mapping)]
    for right_pos in candidates[left_pos]:
        if right_pos in used_right:
            continue
        if not _partial_edges_match(left_pos, right_pos, left_edges, right_edges, mapping):
            continue
        mapping[left_pos] = right_pos
        used_right.add(right_pos)
        if _has_isomorphism(
            order=order,
            candidates=candidates,
            left_edges=left_edges,
            right_edges=right_edges,
            mapping=mapping,
            used_right=used_right,
        ):
            return True
        used_right.remove(right_pos)
        del mapping[left_pos]
    return False


def _partial_edges_match(
    left_pos: int,
    right_pos: int,
    left_edges: frozenset[tuple[int, int]],
    right_edges: frozenset[tuple[int, int]],
    mapping: Mapping[int, int],
) -> bool:
    for src, dst in left_edges:
        if src == left_pos and dst in mapping:
            if (right_pos, mapping[dst]) not in right_edges:
                return False
        if dst == left_pos and src in mapping:
            if (mapping[src], right_pos) not in right_edges:
                return False
    return True
