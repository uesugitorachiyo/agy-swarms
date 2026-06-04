"""FR-4 ``validate_or_die`` — the plan-time gate, plus AC-27 pin-required intake.

``validate_or_die`` rejects a malformed graph before any worker dispatches: duplicate
ids, dangling dependencies, dependency cycles, reducer/map field-presence violations
(§D.1), and templating errors (§D.1.1 restricted Mustache-subset — an undeclared-input
reference is a plan-time error, FR-1.2). ``validate_intake`` enforces AC-27: a TaskSpec
that omits model-version pins is rejected with a specific error before dispatch.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from .lockfile import Lockfile
from .types import DriftRecord, NodeSpec, TaskGraph, TaskSpec

__all__ = ["ValidationError", "validate_or_die", "validate_intake", "check_drift"]


class ValidationError(Exception):
    """Raised by the plan-time gate; aborts the run before dispatch (FR-4)."""


# Non-escaped {{ ... }} (a leading backslash escapes the braces, §D.1.1).
_INTERP = re.compile(r"(?<!\\)\{\{(.*?)\}\}", re.DOTALL)
_REDUCER_KINDS = ("concat", "json_merge", "custom")
_NODE_KINDS = ("single", "map")


def validate_intake(task_spec: TaskSpec) -> None:
    """AC-27: reject a TaskSpec that omits required model-version pins."""
    if not task_spec.model_pins:
        raise ValidationError(
            "intake: TaskSpec omits required model-version pins (AC-27/FR-1/NFR-7)"
        )


def check_drift(
    locked: Lockfile, actual: Lockfile, *, allow_drift: bool = False
) -> list[DriftRecord]:
    """Verify the lockfile per-key (§D.5): record drift, abort on control-flow drift.

    WITHOUT ``allow_drift``, mismatches in model_pins, prompt_hashes, skill_hashes,
    and policy_version abort the run.
    For tool_versions: a completely missing tool hash blocks AC-6 and aborts WITHOUT
    ``allow_drift``, whereas a tool version mismatch is warn-only and never aborts.

    ``allow_drift`` downgrades every abort to a recorded ``DriftRecord``.
    """
    records: list[DriftRecord] = []

    # 1. Check maps (model_pins, prompt_hashes, tool_versions, skill_hashes)
    for category, locked_map, actual_map in (
        ("model_pins", locked.model_pins, actual.model_pins),
        ("prompt_hashes", locked.prompt_hashes, actual.prompt_hashes),
        ("tool_versions", locked.tool_versions, actual.tool_versions),
        ("skill_hashes", locked.skill_hashes, actual.skill_hashes),
    ):
        for key in sorted(locked_map):
            expected = locked_map[key]
            got = actual_map.get(key, "")
            if got != expected:
                records.append(
                    DriftRecord(category=category, key=key, expected=expected, actual=got)
                )

    # 2. Check governance policy version
    if locked.policy_version and actual.policy_version != locked.policy_version:
        records.append(
            DriftRecord(
                category="policy_version",
                key="default",
                expected=locked.policy_version,
                actual=actual.policy_version,
            )
        )

    # 3. Abort on non-allow_drift mismatches
    if not allow_drift:
        aborting = []
        for r in records:
            if r.category in ("model_pins", "prompt_hashes", "skill_hashes", "policy_version"):
                aborting.append(r)
            elif r.category == "tool_versions" and r.actual == "":
                # Missing tool hash blocks AC-6 / aborts!
                aborting.append(r)

        if aborting:
            detail = "; ".join(
                f"{r.category}.{r.key}: {r.expected!r}->{r.actual!r}" for r in aborting
            )
            raise ValidationError(
                "drift: control-flow-affecting lockfile drift without --allow-drift "
                f"({detail}) — §D.5/AC-31"
            )
    return records


def validate_or_die(
    graph: TaskGraph,
    reducers: Mapping[str, Callable[..., Any]] | None = None,
) -> None:
    """Validate ``graph`` or raise ``ValidationError`` (FR-4)."""
    nodes = graph.nodes
    ids = [n.id for n in nodes]
    idset = set(ids)
    if len(idset) != len(ids):
        raise ValidationError("graph has duplicate node ids")

    for n in nodes:
        for dep in n.dependencies:
            if dep not in idset:
                raise ValidationError(f"node {n.id!r} depends on unknown node {dep!r}")
        _check_reducer(n, reducers)
        _check_map(n)
        _check_template(n)

    _check_single_writer(nodes)
    _check_acyclic(nodes)


def _check_reducer(n: NodeSpec, reducers: Mapping[str, Any] | None) -> None:
    if n.role == "reducer":
        if n.reducer is None:
            raise ValidationError(f"reducer node {n.id!r} requires a reducer object")
    elif n.reducer is not None:
        raise ValidationError(f"non-reducer node {n.id!r} must not carry a reducer object")
    if n.reducer is None:
        return
    r = n.reducer
    if r.kind not in _REDUCER_KINDS:
        raise ValidationError(f"node {n.id!r} unknown reducer kind {r.kind!r}")
    if r.kind == "custom":
        if not r.custom_id:
            raise ValidationError(f"custom reducer on {n.id!r} requires custom_id")
        if reducers is not None and r.custom_id not in reducers:
            raise ValidationError(f"custom reducer id {r.custom_id!r} not in REDUCERS registry")
    elif r.custom_id is not None:
        raise ValidationError(f"non-custom reducer on {n.id!r} must not set custom_id")


def _check_map(n: NodeSpec) -> None:
    if n.kind not in _NODE_KINDS:
        raise ValidationError(f"node {n.id!r} unknown kind {n.kind!r}")
    if n.kind == "map" and n.map is None:
        raise ValidationError(f"map node {n.id!r} requires a MapSpec")
    if n.kind == "single" and n.map is not None:
        raise ValidationError(f"single node {n.id!r} must not carry a MapSpec")


def _check_template(n: NodeSpec) -> None:
    for match in _INTERP.finditer(n.prompt_template):
        node_id = _parse_interpolation(match.group(1).strip(), n.id)
        if node_id not in n.inputs:
            raise ValidationError(
                f"node {n.id!r} template references undeclared input {node_id!r} "
                "(§D.1.1: every interpolated NodeId must appear in inputs)"
            )


def _parse_interpolation(inner: str, node_id: str) -> str:
    """Validate one ``{{...}}`` body and return the referenced NodeId (§D.1.1)."""
    if not inner.startswith("input."):
        raise ValidationError(f"node {node_id!r} invalid interpolation {inner!r}")
    rest = inner[len("input.") :]
    if rest.endswith(".summary"):
        ref = rest[: -len(".summary")]
    elif ".artifact." in rest:
        ref, _, name = rest.partition(".artifact.")
        if not name:
            raise ValidationError(
                f"node {node_id!r} interpolation missing artifact name: {inner!r}"
            )
    else:
        raise ValidationError(
            f"node {node_id!r} invalid interpolation key {inner!r} "
            "(only .summary or .artifact.<name> are valid)"
        )
    if not ref:
        raise ValidationError(f"node {node_id!r} interpolation missing NodeId: {inner!r}")
    return ref


def _check_single_writer(nodes: list[NodeSpec]) -> None:
    """FR-8.1: each blackboard section has exactly one writer node (AC-S5 part a).

    A node's ``outputs`` are the sections it writes; two nodes sharing an output section
    is a concurrent-write planning error caught here, before any dispatch.
    """
    writers: dict[str, str] = {}
    for n in nodes:
        for section in n.outputs:
            prior = writers.get(section)
            if prior is not None:
                raise ValidationError(
                    f"section {section!r} has multiple writers "
                    f"({prior!r}, {n.id!r}) — FR-8.1 single-writer blackboard"
                )
            writers[section] = n.id


def _check_acyclic(nodes: list[NodeSpec]) -> None:
    """Kahn's algorithm over ``dependencies`` (bounded loop, CON-2)."""
    indeg: dict[str, int] = {n.id: 0 for n in nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in nodes}
    for n in nodes:
        for dep in n.dependencies:
            adj[dep].append(n.id)
            indeg[n.id] += 1
    queue = [nid for nid, d in indeg.items() if d == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if seen != len(nodes):
        raise ValidationError("graph has a dependency cycle")
