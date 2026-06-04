"""AC-11 — resume-cache-hit ledger gate (§D.4 / FR-7 / FR-30.1 / AC-11 @ SPEC:478).

A crash that persists a worker's result but not its commit-fsync must, on resume, serve the
node from the FR-7 cache WITHOUT leaving a phantom budget reservation that permanently
shrinks ``available``. Per AC-11 the resumed ledger SHALL show, for the cache-hit node:
(a) ``committed`` unchanged — no new commit; (b) ``reserved`` net-zero — the open
reservation was released (FR-30.1); (c) no second reserve / no re-dispatch — the worker is
not re-invoked. These lock in behavior already implemented in ``_serve_from_cache`` (which
calls ``ledger.release`` before emitting node-succeeded), so this is characterization, not
a RED→GREEN cycle.

Teeth: the phantom-release test opens a REAL reservation (``reserved.tokens > 0`` asserted
pre-resume) and asserts it is ``0`` post-resume while ``counting.calls == []``. Because a
cache-served node never dispatches, ``_dispatch``'s commit path (the only OTHER code that
zeroes ``reserved``) cannot run — so the >0→0 transition uniquely implicates the
``_serve_from_cache`` release line.
"""

from agy_swarms.budget import Dims
from agy_swarms.checkpoint import Checkpoint
from agy_swarms.conductor import Conductor
from agy_swarms.types import (
    Caps,
    Epoch,
    ErrorClass,
    NodeSpec,
    NodeStatus,
    ResultEnvelope,
    TaskGraph,
)

_LIMIT = Dims(tokens=1_000_000, usd=1000.0)


def _epoch():
    return Epoch(epoch_seq=1, epoch_id="E1")


def _ok_envelope(out):
    return ResultEnvelope(
        node_id="",
        idempotency_key="",
        status="succeeded",
        error_class=ErrorClass.NONE,
        artifact={"x": 1},
        token_usage={"input": 0, "thinking": 0, "output": out, "cached": 0, "accounting": "exact"},
    )


class CountingAdapter:
    """Pops one scripted envelope per call and records every dispatch (proves no re-run)."""

    accounting = "exact"

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[str] = []

    def covers(self, required):
        return True

    def run(self, node, *, attempt=0, reservation_id=None):
        self.calls.append(node.id)
        return self.script[node.id].pop(0)


def _committed_checkpoint(path):
    """Run the node once so its succeeded result is journaled (committed-terminal)."""
    node = NodeSpec(id="n", role="worker", objective="o", caps=Caps(max_output_tokens=100))
    with Checkpoint(path, _epoch()) as ck:
        Conductor(
            TaskGraph(nodes=[node]),
            CountingAdapter({"n": [_ok_envelope(80)]}),
            limit=_LIMIT,
            epoch=_epoch(),
            checkpoint=ck,
        ).run()
    return node


def test_ac11_resume_cache_hit_leaves_ledger_pristine(tmp_path):
    # Natural resume: a committed node cache-hits → the resumed ledger takes NO new commit
    # and NO reservation, so `available` is the full budget (no phantom shrink).
    path = tmp_path / "ck.db"
    node = _committed_checkpoint(path)
    with Checkpoint(path, _epoch()) as ck2:
        counting = CountingAdapter({"n": [_ok_envelope(80)]})
        cond = Conductor(
            TaskGraph(nodes=[node]), counting, limit=_LIMIT, epoch=_epoch(), checkpoint=ck2
        )
        report = cond.run()
    assert counting.calls == []  # (c) no re-dispatch
    assert cond.ledger.spent.tokens == 0  # (a) no new commit on resume
    assert cond.ledger.reserved.tokens == 0  # (b) no open reservation
    assert cond.ledger.available == _LIMIT  # no phantom shrink of available
    assert report.states["n"] == NodeStatus.SUCCEEDED


def test_ac11_resume_cache_hit_releases_phantom_reservation(tmp_path):
    # FR-30.1 teeth: a phantom reservation that survived the crash must be RELEASED by the
    # cache-serve path, not left to permanently shrink `available`.
    path = tmp_path / "ck.db"
    node = _committed_checkpoint(path)
    with Checkpoint(path, _epoch()) as ck2:
        counting = CountingAdapter({"n": [_ok_envelope(80)]})
        cond = Conductor(
            TaskGraph(nodes=[node]), counting, limit=_LIMIT, epoch=_epoch(), checkpoint=ck2
        )
        admission = cond.ledger.reserve(
            cond.epoch.epoch_seq, "n", node, epoch_id=cond.epoch.epoch_id
        )
        assert admission.admitted
        assert cond.ledger.reserved.tokens > 0  # the phantom reservation is really open
        report = cond.run()
    assert counting.calls == []  # (c) still no re-dispatch
    assert cond.ledger.reserved.tokens == 0  # (b) phantom released (FR-30.1)
    assert cond.ledger.spent.tokens == 0  # (a) still no new commit
    assert cond.ledger.available == _LIMIT  # available made whole again
    assert report.states["n"] == NodeStatus.SUCCEEDED
