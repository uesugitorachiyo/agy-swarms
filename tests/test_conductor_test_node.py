"""Conductor execution of ``test``/``verify`` nodes (FR-34 / AC-36).

A ``test``/``verify`` node runs its declared command through the injected
``command_runner`` instead of the worker adapter: a **nonzero** exit marks the node
``failed`` (exit code captured in ``artifact``, stdout/stderr in ``stdout_ref``) and its
dependents are ``skipped`` (transitive-block per FR-5.1); a **zero** exit marks it
``succeeded`` and unblocks dependents. A failing test is NOT a model failure, so it never
triggers the FR-35 model-fallback.
"""

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.conductor import Conductor
from agy_swarms.runners import CommandOutcome
from agy_swarms.types import (
    NodeSpec,
    NodeStatus,
    RunStatus,
    TaskGraph,
)
from tests.conductor_support import LIMIT as _LIMIT
from tests.conductor_support import FakeAdapter
from tests.conductor_support import envelope as _env
from tests.conductor_support import epoch as _epoch


class FakeRunner:
    """Records each command and returns one preset outcome (hermetic — no real subprocess)."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls: list[list[str]] = []

    def __call__(self, command):
        self.calls.append(command)
        return self.outcome


def test_conductor_command_helpers_are_importable():
    from agy_swarms.conductor_commands import run_command_node

    node = NodeSpec(id="t", role="test", objective="t", command=["pytest"])
    envelope = run_command_node(node, CommandOutcome(exit_code=0, stdout="ok", stderr=""))

    assert envelope.status == "succeeded"
    assert envelope.artifact == {"exit_code": 0, "command": ["pytest"]}
    assert envelope.stdout_ref == "ok"


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
