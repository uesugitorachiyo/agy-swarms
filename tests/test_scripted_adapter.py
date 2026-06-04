"""FR-17 scripted adapter — zero-token deterministic replay (AC-S1/AC-S2/AC-1).

The ``scripted`` adapter maps a node (by ``id`` or ``idempotency_key``) to a canned
``ResultEnvelope`` — deterministic outputs, planted failures/timeouts/budget-overruns/
malformed artifacts — spending ZERO model tokens and declaring ``accounting=exact``. Two
runs of the same node produce byte-identical envelopes (the backbone of the determinism
gate). Schema validation + failure classification are the conductor's job; the adapter
only replays what is planted.
"""

from dataclasses import asdict

import pytest

from agy_swarms.adapters.scripted import (
    CannedResult,
    ScriptedAdapter,
    ScriptedAdapterError,
)
from agy_swarms.canonical import canonical
from agy_swarms.types import Caps, ErrorClass, NodeSpec


def _node(node_id="n1", **kw):
    base = dict(id=node_id, role="worker", objective="o", idempotency_key=f"key-{node_id}")
    base.update(kw)
    return NodeSpec(**base)


def test_scripted_returns_canned_artifact_zero_tokens():
    adp = ScriptedAdapter({"n1": CannedResult(artifact={"answer": 42})})
    env = adp.run(_node("n1"))
    assert env.status == "succeeded"
    assert env.artifact == {"answer": 42}
    assert env.token_usage == {
        "input": 0,
        "thinking": 0,
        "output": 0,
        "cached": 0,
        "accounting": "exact",
    }
    assert env.adapter == "scripted"
    assert env.cost_usd == 0.0


def test_scripted_declares_exact_accounting():
    assert ScriptedAdapter({}).accounting == "exact"


def test_scripted_stamps_node_identity_and_attempt():
    adp = ScriptedAdapter({"n1": CannedResult(artifact={})})
    env = adp.run(_node("n1"), attempt=2, reservation_id="r9")
    assert env.node_id == "n1"
    assert env.idempotency_key == "key-n1"
    assert env.attempt == 2
    assert env.reservation_id == "r9"


def test_scripted_is_byte_identical_across_runs():  # AC-S1/AC-S2
    adp = ScriptedAdapter({"n1": CannedResult(artifact={"x": 1})}, seed=7)
    e1 = adp.run(_node("n1"))
    e2 = adp.run(_node("n1"))
    assert e1 == e2
    assert canonical(asdict(e1)) == canonical(asdict(e2))


def test_scripted_has_no_wallclock_timestamps():
    env = ScriptedAdapter({"n1": CannedResult(artifact={})}).run(_node("n1"))
    assert env.started_at == "" and env.ended_at == ""


def test_planted_failure_carries_status_and_error_class():
    adp = ScriptedAdapter({"n1": CannedResult(status="failed", error_class=ErrorClass.TRANSPORT)})
    env = adp.run(_node("n1"))
    assert env.status == "failed"
    assert env.error_class == ErrorClass.TRANSPORT


def test_planted_timeout():
    env = ScriptedAdapter({"n1": CannedResult(status="timed_out")}).run(_node("n1"))
    assert env.status == "timed_out"


def test_planted_budget_overrun_usage():
    adp = ScriptedAdapter(
        {
            "n1": CannedResult(
                token_usage={
                    "input": 0,
                    "thinking": 0,
                    "output": 100,
                    "cached": 0,
                    "accounting": "exact",
                },
            )
        }
    )
    env = adp.run(_node("n1", caps=Caps(max_output_tokens=100)))
    assert env.token_usage["output"] == 100


def test_planted_malformed_artifact_returned_as_is():
    adp = ScriptedAdapter({"n1": CannedResult(artifact={"unexpected": True})})
    assert adp.run(_node("n1")).artifact == {"unexpected": True}


def test_lookup_by_idempotency_key():
    adp = ScriptedAdapter({"key-n1": CannedResult(artifact={"via": "key"})})
    assert adp.run(_node("n1")).artifact == {"via": "key"}


def test_missing_canned_result_raises():
    with pytest.raises(ScriptedAdapterError):
        ScriptedAdapter({}).run(_node("ghost"))


def test_capability_cover_check():  # FR-13 (used by AC-35 fallback)
    adp = ScriptedAdapter({}, capabilities=frozenset({"file_write"}))
    assert adp.covers(["file_write"])
    assert not adp.covers(["browser"])


def test_seed_is_carried():
    assert ScriptedAdapter({}, seed=42).seed == 42
