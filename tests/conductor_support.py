"""Shared helpers for conductor behavior tests."""

from __future__ import annotations

from typing import Any

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.types import ErrorClass, Epoch, FailureClass, NodeSpec, ResultEnvelope, TaskGraph

LIMIT = Dims(tokens=1_000_000, usd=1000.0)


def epoch(epoch_id: str = "E1", seq: int = 1) -> Epoch:
    return Epoch(epoch_seq=seq, epoch_id=epoch_id)


def envelope(
    status: str = "succeeded",
    error_class: ErrorClass = ErrorClass.NONE,
    *,
    out: int = 0,
    think: int = 0,
    cost: float = 0.0,
    failure_class: FailureClass | None = None,
    artifact: dict[str, Any] | None = None,
) -> ResultEnvelope:
    return ResultEnvelope(
        node_id="",
        idempotency_key="",
        status=status,
        error_class=error_class,
        failure_class=failure_class,
        artifact=artifact or {},
        token_usage={
            "input": 0,
            "thinking": think,
            "output": out,
            "cached": 0,
            "accounting": "exact",
        },
        cost_usd=cost,
    )


def fanout_graph(objective_a: str = "do a") -> TaskGraph:
    """Return the common root → {a, b} graph used by conductor resume tests."""
    root = NodeSpec(id="root", role="worker", objective="root", outputs=["data"])
    a = NodeSpec(id="a", role="worker", objective=objective_a, dependencies=["root"])
    b = NodeSpec(id="b", role="worker", objective="do b", dependencies=["root"])
    return TaskGraph(nodes=[root, a, b], edges=[("root", "a"), ("root", "b")])


def scripted_fanout_adapter() -> ScriptedAdapter:
    return ScriptedAdapter(
        {
            "root": CannedResult(artifact={"data": 1}),
            "a": CannedResult(artifact={"x": 2}),
            "b": CannedResult(artifact={"y": 3}),
        }
    )


def single_graph(node: NodeSpec) -> TaskGraph:
    return TaskGraph(nodes=[node], edges=[])


class CountingAdapter:
    """Wrap an adapter and record dispatched node ids."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.accounting = inner.accounting
        self.calls: list[str] = []

    def covers(self, required: Any) -> bool:
        return self.inner.covers(required)

    def run(self, node: NodeSpec, *, attempt: int = 0, reservation_id: str | None = None):
        self.calls.append(node.id)
        return self.inner.run(node, attempt=attempt, reservation_id=reservation_id)


class FakeAdapter:
    """Return scripted envelopes per node id, one per attempt, while recording calls."""

    accounting = "exact"

    def __init__(self, script: dict[str, list[ResultEnvelope]], *, accounting: str = "exact"):
        self.script = {key: list(value) for key, value in script.items()}
        self.accounting = accounting
        self.calls: list[str] = []

    def covers(self, required: Any) -> bool:
        return True

    def run(self, node: NodeSpec, *, attempt: int = 0, reservation_id: str | None = None):
        self.calls.append(node.id)
        return self.script[node.id].pop(0)
