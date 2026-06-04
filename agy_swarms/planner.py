"""FR-3.1 / AC-0.5 — planner-node decomposition + byte-identical replay (SPEC:471).

Submitting a raw ``task`` (not a pre-built graph) is decomposed into a ``TaskGraph`` by a
planner-role node — modelled in Phase 1 by a ``planner`` object whose ``.plan(task_spec)``
returns a ``PlanArtifact`` (the subtask worker nodes + dependency edges; the engine itself
authors no subtasks). The produced graph is validated (FR-4) and recorded for replay keyed
by ``(task_sha, context_hash)`` so a re-run reuses the recorded graph byte-identically
rather than re-decomposing (folded into the checkpoint epoch, FR-7/§D.6).

``context_hash`` follows D-1: ``sha256_hex(canonical({epoch_id, context}))``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import canonical, sha256_hex
from .graph_equivalence import GraphSignature, equivalent_graph_shape, graph_signature
from .graph_store import GraphStore
from .types import Epoch, NodeSpec, TaskGraph, TaskSpec
from .validate import ValidationError, validate_or_die

__all__ = [
    "PLANNER_SYSTEM_PROMPT",
    "PlanArtifact",
    "PlannerEquivalenceReport",
    "ReplanExhausted",
    "RuntimeReplanReport",
    "bounded_replan",
    "compute_context_hash",
    "decompose",
    "merge_runtime_subgraph",
    "verify_seeded_planner_hard_gate",
]

PLANNER_SYSTEM_PROMPT = (
    "You are a dynamic workflow planner. Decompose tasks into standard linear chain "
    "sequences of NodeSpecs (worker, reviewer, closer nodes) and dependency edges. "
    "To maximize Jaccard edge-set similarity and graph shape determinism, avoid arbitrary "
    "fan-out configurations and prefer linear dependency structures. Organize your "
    "decomposition consistently: first the planner node, followed by workers in order, "
    "and ending with verification review/closer nodes."
)


@dataclass(frozen=True)
class PlanArtifact:
    """A planner-role node's output (FR-3.1): the decomposed subtask nodes + dependency edges.

    The planner — not the engine — authors these. ``decompose`` projects the artifact onto a
    ``TaskGraph`` and validates it before recording for replay.
    """

    nodes: tuple[NodeSpec, ...]
    edges: tuple[tuple[str, str], ...] = ()
    seed: int = 0


@dataclass(frozen=True)
class PlannerEquivalenceReport:
    """AC-3 scripted/seeded planner hard-gate evidence."""

    equivalent: bool
    replay_byte_identical: bool
    seed: int
    first_signature: GraphSignature
    second_signature: GraphSignature


@dataclass(frozen=True)
class RuntimeReplanReport:
    """D3.5 bounded-replan evidence."""

    graph: TaskGraph
    attempts: int
    validation_errors: tuple[str, ...] = ()


class ReplanExhausted(ValidationError):
    """Raised when every bounded replan attempt produces an invalid subgraph."""

    def __init__(self, attempts: int, validation_errors: tuple[str, ...]) -> None:
        self.attempts = attempts
        self.validation_errors = validation_errors
        last = validation_errors[-1] if validation_errors else "no replan attempted"
        super().__init__(f"bounded replan exhausted after {attempts} attempts; last error: {last}")


def compute_context_hash(epoch_id: str, context: Mapping[str, Any] | None = None) -> str:
    """D-1: ``context_hash = sha256_hex(canonical({epoch_id, context}))``.

    Folds the cache-validity ``epoch_id`` (§D.6) with the decomposition ``context`` so a
    re-run under the same epoch + context replays the recorded graph, while an epoch bump or
    a context change keys a fresh decomposition. ``canonical`` sorts keys, so context
    insertion order does not affect the hash.
    """
    return sha256_hex(canonical({"epoch_id": epoch_id, "context": dict(context or {})}))


def decompose(
    task_spec: TaskSpec,
    planner: Any,
    *,
    graph_store: GraphStore,
    epoch: Epoch,
    context: Mapping[str, Any] | None = None,
) -> TaskGraph:
    """FR-3.1/AC-0.5: decompose a raw task into a validated ``TaskGraph`` via a planner node.

    The ``planner`` (a planner-role node's worker behavior) authors the subtask nodes +
    edges; the engine merely projects them onto a ``TaskGraph`` and validates it (FR-4)
    before recording it. The recording is keyed by ``(task_sha, context_hash)`` so a re-run
    with the same key replays the recorded graph byte-identically (no re-decomposition,
    FR-3.1/§D.6); a changed task or context (or an epoch bump, via ``context_hash``) keys a
    fresh decomposition.
    """
    task_sha = sha256_hex(canonical(task_spec.task))
    context_hash = task_spec.context_hash or compute_context_hash(epoch.epoch_id, context)
    key = (task_sha, context_hash)
    recorded = graph_store.get(key)
    if recorded is not None:
        return recorded  # byte-identical replay — no re-decomposition (FR-3.1)
    artifact = planner.plan(task_spec)
    graph = TaskGraph(nodes=list(artifact.nodes), edges=list(artifact.edges), seed=artifact.seed)
    validate_or_die(graph)
    _check_plan(graph)
    graph_store.put(key, graph)
    return graph


def verify_seeded_planner_hard_gate(
    task_spec: TaskSpec,
    first_planner: Any,
    second_planner: Any,
    *,
    epoch: Epoch,
    context: Mapping[str, Any] | None = None,
) -> PlannerEquivalenceReport:
    """AC-3 hard gate: same task + seed from scripted planners yields equivalent graph.

    The two planners are decomposed through independent stores to force fresh planner
    outputs. The first store is then reused once to assert the FR-3.1 replay path returns
    the recorded graph byte-identically.
    """
    first_store = GraphStore()
    first_graph = decompose(
        task_spec, first_planner, graph_store=first_store, epoch=epoch, context=context
    )
    replayed = decompose(
        task_spec, first_planner, graph_store=first_store, epoch=epoch, context=context
    )

    second_graph = decompose(
        task_spec, second_planner, graph_store=GraphStore(), epoch=epoch, context=context
    )
    if first_graph.seed != second_graph.seed:
        raise ValidationError(
            "AC-3 scripted/seeded planner seed mismatch: "
            f"{first_graph.seed!r} != {second_graph.seed!r}"
        )

    first_signature = graph_signature(first_graph)
    second_signature = graph_signature(second_graph)
    equivalent = equivalent_graph_shape(first_graph, second_graph)
    if not equivalent:
        raise ValidationError("AC-3 scripted/seeded planner produced non-equivalent graph shape")

    return PlannerEquivalenceReport(
        equivalent=True,
        replay_byte_identical=replayed is first_graph,
        seed=first_graph.seed,
        first_signature=first_signature,
        second_signature=second_signature,
    )


def merge_runtime_subgraph(base_graph: TaskGraph, subgraph: TaskGraph) -> TaskGraph:
    """D3.5 validate-then-merge for runtime graph growth.

    The planner may emit a subgraph whose new nodes depend on already-existing base graph
    nodes. Validation therefore runs against the combined candidate graph before anything is
    returned to the scheduler/conductor. ``base_graph`` is not mutated.
    """
    merged = TaskGraph(
        nodes=[*base_graph.nodes, *subgraph.nodes],
        edges=_merge_edges(base_graph, subgraph),
        seed=base_graph.seed,
    )
    validate_or_die(merged)
    _check_edges_resolvable(merged)
    return merged


def bounded_replan(
    task_spec: TaskSpec,
    replanner: Any,
    *,
    base_graph: TaskGraph,
    failed_node_id: str,
    max_replans: int,
) -> RuntimeReplanReport:
    """Attempt runtime subgraph replanning up to ``max_replans`` times.

    Each emitted subgraph is validate-then-merged with ``base_graph``. Invalid candidates
    are rejected before dispatch and collected. Exhaustion raises ``ReplanExhausted`` with
    the final validation error in the exception message.
    """
    errors: list[str] = []
    for attempt in range(1, max_replans + 1):
        candidate = replanner.replan(
            task_spec, base_graph, failed_node_id=failed_node_id, attempt=attempt
        )
        subgraph = _coerce_replan_output(candidate)
        try:
            return RuntimeReplanReport(
                graph=merge_runtime_subgraph(base_graph, subgraph),
                attempts=attempt,
                validation_errors=tuple(errors),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    raise ReplanExhausted(max_replans, tuple(errors))


def _coerce_replan_output(candidate: Any) -> TaskGraph:
    if isinstance(candidate, TaskGraph):
        return candidate
    if isinstance(candidate, PlanArtifact):
        return TaskGraph(
            nodes=list(candidate.nodes), edges=list(candidate.edges), seed=candidate.seed
        )
    raise ValidationError(
        f"replanner returned unsupported subgraph type {type(candidate).__name__}"
    )


def _merge_edges(base_graph: TaskGraph, subgraph: TaskGraph) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    edges: list[tuple[str, str]] = []
    for edge in [*base_graph.edges, *subgraph.edges, *_dependency_edges(subgraph)]:
        if edge in seen:
            continue
        seen.add(edge)
        edges.append(edge)
    return edges


def _dependency_edges(graph: TaskGraph) -> list[tuple[str, str]]:
    return [(dep, node.id) for node in graph.nodes for dep in node.dependencies]


def _check_edges_resolvable(graph: TaskGraph) -> None:
    ids = {node.id for node in graph.nodes}
    for src, dst in graph.edges:
        if src not in ids:
            raise ValidationError(f"edge source {src!r} is not in graph")
        if dst not in ids:
            raise ValidationError(f"edge target {dst!r} is not in graph")


def _check_plan(graph: TaskGraph) -> None:
    """AC-0.5: every produced node carries a valid role; worker nodes carry capabilities.

    Beyond ``validate_or_die``'s structural checks, a planner-authored graph SHALL carry a
    non-empty ``role`` on every node and non-empty ``required_capabilities`` on each
    ``worker`` subtask node (§D.1). A violation aborts before the graph is recorded.
    """
    for node in graph.nodes:
        if not node.role:
            raise ValidationError(
                f"planner produced node {node.id!r} without a role (§D.1, AC-0.5)"
            )
        if node.role == "worker" and not node.required_capabilities:
            raise ValidationError(
                f"planner produced worker node {node.id!r} without "
                "required_capabilities (§D.1, AC-0.5)"
            )
