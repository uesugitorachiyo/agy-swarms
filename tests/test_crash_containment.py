"""AC-38 — crash containment for worker dispatch (NFR-8 / FR-12 in-process seam).

A worker adapter that RAISES must not take down the conductor: the exception is contained
into a ``failed`` envelope (opaque ⇒ ``UNKNOWN`` → Deterministic, §D.2 fail-closed), the
node is marked FAILED with a blocker, and the run completes normally. A declared command
killed by a signal (negative exit code) classes as ``TIMEOUT`` → Transient (decision D-5),
distinct from a clean nonzero (``TOOL``) — and either way the command still runs exactly
once (the AC-36 invariant is preserved).

OS-level isolation (FR-12 worktree / NFR-8 hermetic FS) is a Phase-2 concern; this locks
the in-process containment + classification seam only.
"""

import sys

from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor, classify
from agy_swarms.runners import subprocess_runner
from agy_swarms.types import (
    Epoch,
    ErrorClass,
    FailureClass,
    NodeSpec,
    NodeStatus,
    RunStatus,
    TaskGraph,
)

_LIMIT = Dims(tokens=1_000_000, usd=1000.0)

_SIGKILL_SELF = [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]


def _epoch():
    return Epoch(epoch_seq=1, epoch_id="E1")


class _CrashingAdapter:
    """A worker adapter whose every dispatch raises — models a worker that crashes."""

    accounting = "exact"

    def covers(self, required):
        return True

    def run(self, node, *, attempt=0, reservation_id=None):
        raise RuntimeError("worker exploded")


class _CountingRealRunner:
    """Delegates to the real subprocess_runner but records calls (proves exactly-once)."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, command):
        self.calls.append(command)
        return subprocess_runner(command)


def test_raising_worker_adapter_is_contained_not_propagated():
    node = NodeSpec(id="w", role="worker", objective="o")
    graph = TaskGraph(nodes=[node], edges=[])
    cond = Conductor(graph, _CrashingAdapter(), limit=_LIMIT, epoch=_epoch())
    report = cond.run()  # must NOT raise — a crashing worker is contained, not fatal
    assert report.status == RunStatus.FAILED
    assert report.states["w"] == NodeStatus.FAILED
    env = report.results["w"]
    assert env.error_class is ErrorClass.UNKNOWN  # opaque crash ⇒ fail-closed (§D.2)
    assert classify(env) is FailureClass.DETERMINISTIC  # not retryable-by-default
    assert "worker exploded" in (env.stdout_ref or "")  # crash detail surfaced
    assert any(b["id"] == "w" for b in report.blockers)  # blocker raised


def test_signal_killed_command_node_is_timeout_transient_and_runs_once():
    # A test/verify command killed by SIGKILL surfaces a NEGATIVE exit code ⇒ TIMEOUT →
    # Transient (D-5), not TOOL. The signal number rides in the artifact's exit_code, and
    # the declared command still runs exactly once (AC-36 exactly-once preserved).
    if sys.platform == "win32":
        import pytest

        pytest.skip("Windows does not support POSIX signals/SIGKILL return codes")
    runner = _CountingRealRunner()
    node = NodeSpec(id="t", role="test", objective="o", command=_SIGKILL_SELF)
    graph = TaskGraph(nodes=[node], edges=[])
    cond = Conductor(graph, _CrashingAdapter(), limit=_LIMIT, epoch=_epoch(), command_runner=runner)
    report = cond.run()
    assert report.states["t"] == NodeStatus.FAILED
    env = report.results["t"]
    assert env.artifact["exit_code"] < 0  # killed by signal (negative returncode)
    assert env.error_class is ErrorClass.TIMEOUT  # D-5: signal → TIMEOUT, not TOOL
    assert classify(env) is FailureClass.TRANSIENT  # →Transient, never model-fallback'd
    assert len(runner.calls) == 1  # AC-36: the command ran exactly once


def test_missing_exe_command_node_is_tool_distinct_from_signal():
    # Divergence guard: a missing executable (exit 127) is a TOOL error — NOT the TIMEOUT a
    # signal-kill (-9) yields. The two crash kinds must not collapse into one §D.2 class.
    node = NodeSpec(
        id="t", role="test", objective="o", command=["definitely-not-a-real-binary-xyzzy"]
    )
    graph = TaskGraph(nodes=[node], edges=[])
    cond = Conductor(graph, _CrashingAdapter(), limit=_LIMIT, epoch=_epoch())
    report = cond.run()  # default command_runner = the real (now-total) subprocess_runner
    assert report.states["t"] == NodeStatus.FAILED
    assert report.results["t"].artifact["exit_code"] == 127  # contained, not raised
    assert report.results["t"].error_class is ErrorClass.TOOL  # distinct from signal's TIMEOUT
