"""AC-3 scripted/seeded planner hard gate."""

import pytest

from agy_swarms.planner import (
    PlanArtifact,
    verify_seeded_planner_hard_gate,
)
from agy_swarms.types import Epoch, NodeSpec, TaskSpec
from agy_swarms.validate import ValidationError


def _epoch():
    return Epoch(epoch_seq=1, epoch_id="E1")


def _worker(node_id: str, *, deps: list[str] | None = None, objective: str = "work"):
    return NodeSpec(
        id=node_id,
        role="worker",
        objective=objective,
        required_capabilities=["code"],
        dependencies=deps or [],
    )


def _artifact(ids: tuple[str, str], *, seed: int = 7) -> PlanArtifact:
    root, child = ids
    return PlanArtifact(
        nodes=(
            _worker(root, objective="first"),
            _worker(child, deps=[root], objective="different prose is ignored"),
        ),
        edges=((root, child),),
        seed=seed,
    )


class _Planner:
    def __init__(self, artifact: PlanArtifact):
        self.artifact = artifact
        self.calls = 0

    def plan(self, task_spec):
        self.calls += 1
        return self.artifact


def test_scripted_seeded_hard_gate_accepts_equivalent_graph_shape_with_different_ids():
    first = _Planner(_artifact(("a", "b")))
    second = _Planner(_artifact(("x", "y")))

    report = verify_seeded_planner_hard_gate(
        TaskSpec(task="same task", model_pins={"default": "flash"}),
        first,
        second,
        epoch=_epoch(),
    )

    assert report.equivalent is True
    assert report.replay_byte_identical is True
    assert first.calls == 1  # second decompose against same store used recorded replay
    assert second.calls == 1


def test_scripted_seeded_hard_gate_rejects_non_equivalent_graph_shape():
    first = _Planner(
        PlanArtifact(
            nodes=(
                _worker("root"),
                _worker("a", deps=["root"]),
                _worker("b", deps=["a"]),
            ),
            seed=7,
        )
    )
    second = _Planner(
        PlanArtifact(
            nodes=(
                _worker("root2"),
                _worker("x", deps=["root2"]),
                _worker("y", deps=["root2"]),
            ),
            seed=7,
        )
    )

    with pytest.raises(ValidationError, match="non-equivalent graph"):
        verify_seeded_planner_hard_gate(
            TaskSpec(task="same task", model_pins={"default": "flash"}),
            first,
            second,
            epoch=_epoch(),
        )


def test_scripted_seeded_hard_gate_rejects_seed_mismatch():
    first = _Planner(_artifact(("a", "b"), seed=7))
    second = _Planner(_artifact(("x", "y"), seed=8))

    with pytest.raises(ValidationError, match="seed mismatch"):
        verify_seeded_planner_hard_gate(
            TaskSpec(task="same task", model_pins={"default": "flash"}),
            first,
            second,
            epoch=_epoch(),
        )
