"""Back-pressure: a wide ready-set drains fully under a small cap (AC-37 / FR-5 / CON-8).

When many nodes are ready at once, ``run()`` must not stall or drop work: it slices each
barrier to ``cap`` (``ready[: self.cap]``) and re-derives the ready-set on the next loop,
so successive barriers exhaust the set. With 100 independent nodes and ``cap=10`` every
node is dispatched exactly once and the run terminates SUCCEEDED. This is a lock-in /
characterization test for the existing cap-bounded driver — not a RED→GREEN cycle.
"""

from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor
from agy_swarms.types import (
    Epoch,
    ErrorClass,
    NodeSpec,
    NodeStatus,
    ResultEnvelope,
    RunStatus,
    TaskGraph,
)

_LIMIT = Dims(tokens=1_000_000, usd=1000.0)


def _epoch():
    return Epoch(epoch_seq=1, epoch_id="E1")


class _OkAdapter:
    """Returns a fresh zero-token succeeded envelope for any node (no per-node script);
    records every dispatch so we can assert each ready node ran exactly once."""

    accounting = "exact"

    def __init__(self):
        self.calls: list[str] = []

    def covers(self, required):
        return True

    def run(self, node, *, attempt=0, reservation_id=None):
        self.calls.append(node.id)
        return ResultEnvelope(
            node_id=node.id,
            idempotency_key="",
            status="succeeded",
            error_class=ErrorClass.NONE,
            artifact={"id": node.id},
            token_usage={
                "input": 0,
                "thinking": 0,
                "output": 0,
                "cached": 0,
                "accounting": "exact",
            },
        )


def test_wide_ready_set_drains_under_small_cap_without_stall():
    n = 100
    nodes = [NodeSpec(id=f"n{i}", role="worker", objective="o") for i in range(n)]
    graph = TaskGraph(nodes=nodes, edges=[])
    adapter = _OkAdapter()
    cond = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=10)
    report = cond.run()
    assert report.status == RunStatus.SUCCEEDED
    assert len(report.results) == n  # nothing dropped
    assert all(s == NodeStatus.SUCCEEDED for s in report.states.values())
    assert len(adapter.calls) == n  # each ready node dispatched exactly once
    assert len(set(adapter.calls)) == n  # ...and none dispatched twice
