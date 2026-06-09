"""Conductor fallback-on-primary-failure (FR-35 / AC-35).

When a node's PRIMARY adapter returns a ``FailureClass::Deterministic`` result (§D.2), the
conductor SHALL retry the node exactly once on the *configured fallback adapter*, record
the model switch in the event log, and gate that retry on budget (FR-6) and capability
cover (FR-13/§D.1). A fallback never consumes a transient schema-retry; a missing fallback
is a silent no-op (the node fails as it would without FR-35, so AC-1 is unperturbed); an
uncovered fallback fires nothing and raises a blocker instead (AC-35 c).
"""

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.conductor import Conductor
from agy_swarms.types import (
    Caps,
    ErrorClass,
    NodeSpec,
    NodeStatus,
    RetryPolicy,
    RunStatus,
)
from tests.conductor_support import LIMIT as _LIMIT
from tests.conductor_support import epoch as _epoch
from tests.conductor_support import single_graph as _single


class CountingScripted(ScriptedAdapter):
    """A real FR-17 scripted adapter that also records each dispatch and carries a distinct
    ``name``, so a test can assert exactly how many times — and to which model — the
    conductor dispatched."""

    def __init__(self, name, transcript, *, capabilities=frozenset()):
        super().__init__(transcript, capabilities=capabilities)
        self.name = name
        self.calls: list[str] = []

    def run(self, node, *, attempt=0, reservation_id=None):
        self.calls.append(node.id)
        return super().run(node, attempt=attempt, reservation_id=reservation_id)


def _deterministic_fail():
    # AUTH → FailureClass.DETERMINISTIC (§D.2 _ERROR_TO_FAILURE), non-retryable.
    return CannedResult(status="failed", error_class=ErrorClass.AUTH)


def test_deterministic_primary_triggers_exactly_one_fallback_dispatch():
    node = NodeSpec(id="n", role="worker", objective="n", required_capabilities=["py"])
    primary = CountingScripted("primary", {"n": _deterministic_fail()})
    fallback = CountingScripted(
        "fallback", {"n": CannedResult(artifact={"ok": True})}, capabilities={"py"}
    )
    cond = Conductor(
        _single(node), primary, limit=_LIMIT, epoch=_epoch(), fallback_adapter=fallback
    )
    report = cond.run()
    assert report.status == RunStatus.SUCCEEDED  # the fallback rescued the node
    assert report.results["n"].artifact == {"ok": True}  # result is the fallback's
    assert primary.calls == ["n"]  # deterministic → primary tried once, no retry
    assert fallback.calls == ["n"]  # (a) EXACTLY ONE fallback dispatch
    switches = [e for e in cond.events if e["type"] == "model_switch"]
    assert len(switches) == 1  # (b) the switch is recorded in the event log
    assert switches[0]["node_id"] == "n"
    assert switches[0]["from"] == "primary"
    assert switches[0]["to"] == "fallback"


def test_uncovered_fallback_does_not_fire_and_raises_blocker():
    node = NodeSpec(id="n", role="worker", objective="n", required_capabilities=["gpu"])
    primary = CountingScripted("primary", {"n": _deterministic_fail()})
    fallback = CountingScripted(  # declares py, NOT the required gpu
        "fallback", {"n": CannedResult(artifact={"ok": True})}, capabilities={"py"}
    )
    cond = Conductor(
        _single(node), primary, limit=_LIMIT, epoch=_epoch(), fallback_adapter=fallback
    )
    report = cond.run()
    assert report.states["n"] == NodeStatus.FAILED
    assert fallback.calls == []  # (c) no fallback fires when it can't cover
    assert any(b["needs"] == "fallback_uncovered" for b in report.blockers)
    assert not [e for e in cond.events if e["type"] == "model_switch"]


def test_fallback_also_failing_leaves_node_failed_after_one_switch():
    node = NodeSpec(id="n", role="worker", objective="n", required_capabilities=["py"])
    primary = CountingScripted("primary", {"n": _deterministic_fail()})
    fallback = CountingScripted(
        "fallback",
        {"n": CannedResult(status="failed", error_class=ErrorClass.UNKNOWN)},
        capabilities={"py"},
    )
    cond = Conductor(
        _single(node), primary, limit=_LIMIT, epoch=_epoch(), fallback_adapter=fallback
    )
    report = cond.run()
    assert report.states["n"] == NodeStatus.FAILED  # both failed → terminal
    assert fallback.calls == ["n"]  # still exactly one fallback dispatch
    assert len([e for e in cond.events if e["type"] == "model_switch"]) == 1


def test_no_fallback_configured_fails_normally_without_switch():
    node = NodeSpec(id="n", role="worker", objective="n")
    primary = CountingScripted("primary", {"n": _deterministic_fail()})
    cond = Conductor(_single(node), primary, limit=_LIMIT, epoch=_epoch())
    report = cond.run()
    assert report.states["n"] == NodeStatus.FAILED
    assert cond.events == []  # nothing to switch to
    assert all(b["needs"] != "fallback_uncovered" for b in report.blockers)
    assert any(b["what"] == "node failed" for b in report.blockers)  # ordinary failure


def test_fallback_does_not_consume_a_transient_retry():
    node = NodeSpec(
        id="n",
        role="worker",
        objective="n",
        required_capabilities=["py"],
        retry_policy=RetryPolicy(max_schema_retries=2),
    )
    primary = CountingScripted("primary", {"n": _deterministic_fail()})
    fallback = CountingScripted(
        "fallback", {"n": CannedResult(artifact={"ok": True})}, capabilities={"py"}
    )
    cond = Conductor(
        _single(node), primary, limit=_LIMIT, epoch=_epoch(), fallback_adapter=fallback
    )
    cond.run()
    # the switch is NOT a transient retry — the schema-retry budget is untouched.
    assert cond.runtime["n"].remaining_schema_retries == 2


def test_fallback_is_budget_gated():
    # est(node)=50 admits the first reserve under a 120-token cap; the primary's planted
    # overrun then exhausts the budget, so the fallback re-reserve is refused (FR-6).
    node = NodeSpec(
        id="n",
        role="worker",
        objective="n",
        required_capabilities=["py"],
        caps=Caps(max_output_tokens=50),
    )
    overrun = {
        "input": 0,
        "thinking": 0,
        "output": 10_000,
        "cached": 0,
        "accounting": "exact",
    }
    primary = CountingScripted(
        "primary",
        {"n": CannedResult(status="failed", error_class=ErrorClass.AUTH, token_usage=overrun)},
    )
    fallback = CountingScripted(
        "fallback", {"n": CannedResult(artifact={"ok": True})}, capabilities={"py"}
    )
    cond = Conductor(
        _single(node),
        primary,
        limit=Dims(tokens=120, usd=1000.0),
        epoch=_epoch(),
        fallback_adapter=fallback,
    )
    report = cond.run()
    assert fallback.calls == []  # budget gate refused the fallback re-reserve
    assert report.states["n"] == NodeStatus.FAILED


def test_dynamic_escalation_upon_repeated_failures():
    # Primary fails with SCHEMA_INVALID (which is classified as Transient retry-eligible).
    node = NodeSpec(
        id="n",
        role="worker",
        objective="n",
        required_capabilities=["py"],
        retry_policy=RetryPolicy(max_schema_retries=2, retryable_error_classes=("schema_invalid",)),
    )
    primary = CountingScripted(
        "primary",
        {"n": CannedResult(status="failed", error_class=ErrorClass.SCHEMA_INVALID)},
    )
    fallback = CountingScripted(
        "fallback",
        {"n": CannedResult(artifact={"escalated": True})},
        capabilities={"py"},
    )
    cond = Conductor(
        _single(node),
        primary,
        limit=_LIMIT,
        epoch=_epoch(),
        fallback_adapter=fallback,
    )
    report = cond.run()
    # At attempt 1: run on primary (failed_attempts=1 -> no escalation). Fails with SCHEMA_INVALID.
    # At attempt 2: run on fallback (failed_attempts=2 -> escalates!). Succeeds!
    assert report.status == RunStatus.SUCCEEDED
    assert report.results["n"].artifact == {"escalated": True}
    assert primary.calls == ["n"]
    assert fallback.calls == ["n"]
    # Verify model_switch event was logged
    switches = [e for e in cond.events if e["type"] == "model_switch"]
    assert len(switches) == 1
    assert switches[0]["node_id"] == "n"
    assert switches[0]["from"] == "primary"
    assert switches[0]["to"] == "fallback"


def test_dynamic_escalation_for_high_value_node():
    node = NodeSpec(
        id="n",
        role="worker",
        objective="n",
        required_capabilities=["py"],
    )
    node.high_value = True
    primary = CountingScripted("primary", {"n": CannedResult(artifact={"primary_ok": True})})
    fallback = CountingScripted(
        "fallback",
        {"n": CannedResult(artifact={"escalated_ok": True})},
        capabilities={"py"},
    )
    cond = Conductor(
        _single(node),
        primary,
        limit=_LIMIT,
        epoch=_epoch(),
        fallback_adapter=fallback,
    )
    report = cond.run()
    # Should escalate immediately on first run because high_value is True.
    assert report.status == RunStatus.SUCCEEDED
    assert report.results["n"].artifact == {"escalated_ok": True}
    assert primary.calls == []
    assert fallback.calls == ["n"]
    # Verify model_switch event was logged
    switches = [e for e in cond.events if e["type"] == "model_switch"]
    assert len(switches) == 1
