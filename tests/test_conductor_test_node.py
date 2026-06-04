"""Conductor execution of ``test``/``verify`` nodes (FR-34 / AC-36).

A ``test``/``verify`` node runs its declared command through the injected
``command_runner`` instead of the worker adapter: a **nonzero** exit marks the node
``failed`` (exit code captured in ``artifact``, stdout/stderr in ``stdout_ref``) and its
dependents are ``skipped`` (transitive-block per FR-5.1); a **zero** exit marks it
``succeeded`` and unblocks dependents. A failing test is NOT a model failure, so it never
triggers the FR-35 model-fallback.
"""

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor
from agy_swarms.runners import CommandOutcome
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


def _env(status="succeeded", *, artifact=None):
    return ResultEnvelope(
        node_id="",
        idempotency_key="",
        status=status,
        error_class=ErrorClass.NONE,
        artifact=artifact or {},
        token_usage={"input": 0, "thinking": 0, "output": 0, "cached": 0, "accounting": "exact"},
    )


class FakeAdapter:
    """Worker adapter for the dependent node; a test node wrongly dispatched here would
    pop a missing script entry (KeyError) and surface in ``.calls``."""

    accounting = "exact"

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[str] = []

    def covers(self, required):
        return True

    def run(self, node, *, attempt=0, reservation_id=None):
        self.calls.append(node.id)
        return self.script[node.id].pop(0)


class FakeRunner:
    """Records each command and returns one preset outcome (hermetic — no real subprocess)."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls: list[list[str]] = []

    def __call__(self, command):
        self.calls.append(command)
        return self.outcome


def _t_then_d():
    t = NodeSpec(id="t", role="test", objective="t", command=["pytest"])
    d = NodeSpec(id="d", role="worker", objective="d", dependencies=["t"])
    return t, d


def test_failing_test_node_marks_failed_and_skips_dependents():
    t, d = _t_then_d()
    graph = TaskGraph(nodes=[t, d], edges=[("t", "d")])
    adapter = FakeAdapter({"d": [_env()]})
    runner = FakeRunner(CommandOutcome(exit_code=1, stdout="boom", stderr="trace"))
    cond = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=2, command_runner=runner)
    report = cond.run()
    assert report.states["t"] == NodeStatus.FAILED
    assert report.results["t"].artifact["exit_code"] == 1
    assert "boom" in report.results["t"].stdout_ref  # stdout captured (§D.2)
    assert "trace" in report.results["t"].stdout_ref  # stderr captured (§D.2)
    assert report.states["d"] == NodeStatus.SKIPPED  # transitive-block FR-5.1
    assert "d" not in adapter.calls  # dependent never dispatched
    assert runner.calls == [["pytest"]]  # the declared command ran exactly once


def test_passing_test_node_marks_succeeded_and_unblocks_dependents():
    t, d = _t_then_d()
    graph = TaskGraph(nodes=[t, d], edges=[("t", "d")])
    adapter = FakeAdapter({"d": [_env(artifact={"ran": True})]})
    runner = FakeRunner(CommandOutcome(exit_code=0, stdout="ok", stderr=""))
    cond = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=2, command_runner=runner)
    report = cond.run()
    assert report.status == RunStatus.SUCCEEDED
    assert report.states["t"] == NodeStatus.SUCCEEDED
    assert report.results["t"].artifact["exit_code"] == 0
    assert report.states["d"] == NodeStatus.SUCCEEDED  # dependent unblocked + ran
    assert adapter.calls == ["d"]


def test_test_node_does_not_dispatch_to_worker_adapter():
    t = NodeSpec(id="t", role="test", objective="t", command=["pytest"])
    graph = TaskGraph(nodes=[t], edges=[])
    adapter = FakeAdapter({})  # KeyError if 't' were (wrongly) dispatched here
    runner = FakeRunner(CommandOutcome(exit_code=0))
    cond = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), command_runner=runner)
    report = cond.run()
    assert report.states["t"] == NodeStatus.SUCCEEDED
    assert adapter.calls == []  # a test node is command-side, never an adapter call


def test_failing_test_node_does_not_trigger_model_fallback():
    t = NodeSpec(
        id="t",
        role="test",
        objective="t",
        command=["pytest"],
        required_capabilities=["py"],
    )
    graph = TaskGraph(nodes=[t], edges=[])
    adapter = FakeAdapter({})
    fallback = ScriptedAdapter({"t": CannedResult(artifact={"ok": True})}, capabilities={"py"})
    runner = FakeRunner(CommandOutcome(exit_code=1, stdout="fail", stderr=""))
    cond = Conductor(
        graph,
        adapter,
        limit=_LIMIT,
        epoch=_epoch(),
        command_runner=runner,
        fallback_adapter=fallback,
    )
    report = cond.run()
    assert report.states["t"] == NodeStatus.FAILED
    # a failing test is a verification result, not a model failure → no model_switch
    assert not [e for e in cond.events if e["type"] == "model_switch"]
