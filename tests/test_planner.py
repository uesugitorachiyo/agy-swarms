"""AC-0.5 — planner-node decomposition + byte-identical replay (FR-3.1, SPEC:471).

D-1: ``context_hash = sha256_hex(canonical({epoch_id, context}))``. The replay key is
``(task_sha, context_hash)``; a re-run with the same key reuses the recorded graph
byte-identically rather than re-invoking the planner.
"""

import pytest

from agy_swarms.budget import Dims
from agy_swarms.canonical import canonical, sha256_hex
from agy_swarms.conductor import Conductor
from agy_swarms.graph_store import GraphStore
from agy_swarms.planner import PlanArtifact, compute_context_hash, decompose
from agy_swarms.types import Epoch, NodeSpec, ResultEnvelope, RunStatus, TaskSpec
from agy_swarms.validate import ValidationError


def _epoch():
    return Epoch(epoch_seq=1, epoch_id="E1")


class _ScriptedPlanner:
    """A deterministic seeded planner (FR-2/FR-17): same task ⇒ same PlanArtifact."""

    def __init__(self, artifact):
        self.artifact = artifact
        self.calls = 0

    def plan(self, task_spec):
        self.calls += 1
        return self.artifact


def _two_worker_artifact():
    return PlanArtifact(
        nodes=(
            NodeSpec(id="a", role="worker", objective="step a", required_capabilities=["code"]),
            NodeSpec(
                id="b",
                role="worker",
                objective="step b",
                required_capabilities=["code"],
                dependencies=["a"],
            ),
        ),
        edges=(("a", "b"),),
    )


def test_compute_context_hash_is_canonical_epoch_plus_context_d1():
    # D-1: context_hash = sha256_hex(canonical({epoch_id, context})).
    assert compute_context_hash("E1", {"b": 2, "a": 1}) == sha256_hex(
        canonical({"epoch_id": "E1", "context": {"b": 2, "a": 1}})
    )


def test_compute_context_hash_is_key_order_independent():
    # canonical() sorts keys ⇒ context insertion order can't change the hash.
    assert compute_context_hash("E1", {"a": 1, "b": 2}) == compute_context_hash(
        "E1", {"b": 2, "a": 1}
    )


def test_compute_context_hash_empty_context_defaults_to_empty_map():
    assert compute_context_hash("E1") == sha256_hex(canonical({"epoch_id": "E1", "context": {}}))


def test_compute_context_hash_changes_with_epoch():
    assert compute_context_hash("E1", {"a": 1}) != compute_context_hash("E2", {"a": 1})


# --- decompose: raw task → validated graph via planner node (FR-3.1) --------


def test_decompose_raw_task_produces_valid_graph_via_planner():
    planner = _ScriptedPlanner(_two_worker_artifact())
    spec = TaskSpec(task="build it", model_pins={"default": "flash"})
    graph = decompose(spec, planner, graph_store=GraphStore(), epoch=_epoch())
    assert planner.calls == 1  # the engine authors no subtasks — the planner did
    assert [n.id for n in graph.nodes] == ["a", "b"]
    assert graph.edges == [("a", "b")]
    # every produced node carries a role + required_capabilities (§D.1, AC-0.5).
    assert all(n.role and n.required_capabilities for n in graph.nodes)


# --- replay: same (task, context_hash) reuses the recorded graph (FR-3.1) ---


def test_replay_same_task_and_context_reuses_recorded_graph_byte_identically():
    planner = _ScriptedPlanner(_two_worker_artifact())
    store = GraphStore()
    spec = TaskSpec(task="build it", model_pins={"default": "flash"})
    g1 = decompose(spec, planner, graph_store=store, epoch=_epoch())
    g2 = decompose(spec, planner, graph_store=store, epoch=_epoch())
    assert planner.calls == 1  # replay reused the recorded graph — no re-decomposition
    assert g2 is g1  # the recorded graph is returned byte-identically


def test_different_context_triggers_redecomposition():
    planner = _ScriptedPlanner(_two_worker_artifact())
    store = GraphStore()
    spec = TaskSpec(task="build it", model_pins={"default": "flash"})
    decompose(spec, planner, graph_store=store, epoch=_epoch(), context={"k": 1})
    decompose(spec, planner, graph_store=store, epoch=_epoch(), context={"k": 2})
    assert planner.calls == 2  # distinct context_hash ⇒ distinct key ⇒ re-decompose


# --- invalid planner output is rejected before recording (FR-4/AC-0.5) ------


def test_decompose_rejects_planner_graph_with_dependency_cycle():
    # validate_or_die (FR-4) fires on a structurally invalid produced graph.
    planner = _ScriptedPlanner(
        PlanArtifact(
            nodes=(
                NodeSpec(
                    id="a",
                    role="worker",
                    objective="a",
                    required_capabilities=["c"],
                    dependencies=["b"],
                ),
                NodeSpec(
                    id="b",
                    role="worker",
                    objective="b",
                    required_capabilities=["c"],
                    dependencies=["a"],
                ),
            ),
        )
    )
    spec = TaskSpec(task="t", model_pins={"default": "flash"})
    with pytest.raises(ValidationError):
        decompose(spec, planner, graph_store=GraphStore(), epoch=_epoch())


def test_decompose_rejects_worker_node_without_required_capabilities():
    planner = _ScriptedPlanner(
        PlanArtifact(nodes=(NodeSpec(id="a", role="worker", objective="a"),))
    )
    spec = TaskSpec(task="t", model_pins={"default": "flash"})
    with pytest.raises(ValidationError, match="required_capabilities"):
        decompose(spec, planner, graph_store=GraphStore(), epoch=_epoch())


def test_decompose_rejects_node_without_role():
    planner = _ScriptedPlanner(
        PlanArtifact(nodes=(NodeSpec(id="a", role="", objective="a", required_capabilities=["c"]),))
    )
    spec = TaskSpec(task="t", model_pins={"default": "flash"})
    with pytest.raises(ValidationError, match="role"):
        decompose(spec, planner, graph_store=GraphStore(), epoch=_epoch())


# --- end-to-end: a raw task decomposes then runs to success (FR-3.1/FR-5) ---


class _OkAdapter:
    """A worker adapter that always succeeds — exercises the decompose→run seam."""

    accounting = "exact"

    def covers(self, required):
        return True

    def run(self, node, *, attempt=0, reservation_id=None):
        return ResultEnvelope(node_id=node.id, idempotency_key="", status="succeeded")


def test_decomposed_graph_runs_to_success_via_conductor():
    # Composition check: a raw task → planner-produced graph → Conductor runs it green.
    planner = _ScriptedPlanner(_two_worker_artifact())
    spec = TaskSpec(task="build it", model_pins={"default": "flash"})
    graph = decompose(spec, planner, graph_store=GraphStore(), epoch=_epoch())
    report = Conductor(
        graph, _OkAdapter(), limit=Dims(tokens=1_000_000, usd=1000.0), epoch=_epoch()
    ).run()
    assert report.status == RunStatus.SUCCEEDED
    assert set(report.states) == {"a", "b"}
