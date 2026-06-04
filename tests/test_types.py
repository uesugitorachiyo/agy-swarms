"""§D.1–§D.6 typed shapes + the ``idempotency_key`` derivation.

The behavioral core here is ``compute_idempotency_key`` (§D.1): the content hash that
makes resume correct (FR-7) and the AC-1 cache-bust test machine-checkable. The recipe
is the precise §D.1 enumeration — id/outputs/timeout_s are NOT hashed; inputs and
output_schema and tools are folded in as §D.0 digests.
"""

import pytest

from agy_swarms.canonical import canonical, sha256_hex
from agy_swarms.types import (
    Caps,
    Epoch,
    EpochBump,
    ErrorClass,
    FailureClass,
    MapSpec,
    NodeRuntimeState,
    NodeSpec,
    NodeStatus,
    Reducer,
    ResultEnvelope,
    RetryPolicy,
    RunStatus,
    SectionConflict,
    TaskGraph,
    ToolEntry,
    compute_epoch_id,
    compute_idempotency_key,
)


# --- enums -----------------------------------------------------------------


def test_node_status_has_eight_members():
    assert {s.value for s in NodeStatus} == {
        "pending",
        "ready",
        "reserved",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "cancelled",
    }


def test_failure_class_three_members():
    assert {f.value for f in FailureClass} == {"Transient", "Deterministic", "Budget"}


def test_run_status_four_members():
    assert {r.value for r in RunStatus} == {"running", "succeeded", "failed", "cancelled"}


def test_error_class_eight_members():
    assert {e.value for e in ErrorClass} == {
        "none",
        "schema_invalid",
        "transport",
        "auth",
        "timeout",
        "budget",
        "tool",
        "unknown",
    }


def test_str_enum_canonicalizes_as_its_value():
    assert canonical(NodeStatus.READY) == b'"ready"'


# --- NodeSpec construction + defaults --------------------------------------


def test_minimal_nodespec_defaults():
    n = NodeSpec(id="n1", role="worker", objective="do x")
    assert n.kind == "single"
    assert n.revision == 0
    assert n.inputs == []
    assert n.dependencies == []
    assert n.map is None
    assert n.reducer is None
    assert n.caps == Caps()
    assert n.retry_policy == RetryPolicy()
    assert n.idempotency_key == ""


def test_retry_policy_default_retryable_classes():
    assert RetryPolicy().retryable_error_classes == ("transport", "timeout")


# --- compute_idempotency_key -----------------------------------------------


def _spec(**kw):
    base = {"id": "n", "role": "worker", "objective": "o"}
    base.update(kw)
    return NodeSpec(**base)


def test_idempotency_key_is_deterministic():
    assert compute_idempotency_key(_spec()) == compute_idempotency_key(_spec())


def test_idempotency_key_is_lowercase_64_hex():
    k = compute_idempotency_key(_spec())
    assert len(k) == 64 and k == k.lower()


def test_idempotency_key_excludes_the_key_field_itself():
    a = compute_idempotency_key(_spec(idempotency_key="junk"))
    b = compute_idempotency_key(_spec(idempotency_key="other"))
    assert a == b


def test_idempotency_key_excludes_node_id():
    # §D.1: id is NOT in the hashed enumeration — identical work = identical key.
    assert compute_idempotency_key(_spec(id="a")) == compute_idempotency_key(_spec(id="b"))


def test_idempotency_key_excludes_outputs_and_timeout():
    base = compute_idempotency_key(_spec())
    assert compute_idempotency_key(_spec(outputs=["sec.a"])) == base
    assert compute_idempotency_key(_spec(timeout_s=999)) == base


def test_objective_change_busts_key():
    assert compute_idempotency_key(_spec(objective="x")) != compute_idempotency_key(
        _spec(objective="y")
    )


def test_revision_change_busts_key():
    # AC-12: a needs-revision retry has a distinct key, never shadowed by the cache.
    assert compute_idempotency_key(_spec(revision=0)) != compute_idempotency_key(_spec(revision=1))


def test_caps_change_busts_key():
    assert compute_idempotency_key(
        _spec(caps=Caps(max_output_tokens=10))
    ) != compute_idempotency_key(_spec(caps=Caps(max_output_tokens=20)))


def test_reducer_object_is_hashed_whole():
    a = _spec(role="reducer", reducer=Reducer(kind="custom", custom_id="x"))
    b = _spec(role="reducer", reducer=Reducer(kind="custom", custom_id="y"))
    assert compute_idempotency_key(a) != compute_idempotency_key(b)


def test_resolved_input_value_change_busts_key():
    s = _spec(inputs=["up"])
    k1 = compute_idempotency_key(s, resolved_inputs={"up": {"v": 1}})
    k2 = compute_idempotency_key(s, resolved_inputs={"up": {"v": 2}})
    assert k1 != k2


def test_missing_resolved_input_raises():
    # §D.1 [H4]: the key is only computable once inputs are resolved (ready-time).
    s = _spec(inputs=["up"])
    with pytest.raises(KeyError):
        compute_idempotency_key(s, resolved_inputs={})


def test_tool_impl_sha_change_busts_key():
    s = _spec(tool_allowlist=["read"])
    reg1 = {"read": ToolEntry(schema={"n": "read"}, impl_source_sha256="a" * 64)}
    reg2 = {"read": ToolEntry(schema={"n": "read"}, impl_source_sha256="b" * 64)}
    assert compute_idempotency_key(s, tool_registry=reg1) != compute_idempotency_key(
        s, tool_registry=reg2
    )


def test_field_construction_order_is_irrelevant():
    a = NodeSpec(id="n", role="worker", objective="o", boundaries="b", max_turns=2)
    b = NodeSpec(max_turns=2, boundaries="b", objective="o", role="worker", id="n")
    assert compute_idempotency_key(a) == compute_idempotency_key(b)


# --- Epoch (§D.6) ----------------------------------------------------------


def test_epoch_id_is_content_hash_of_its_three_inputs():
    eid = compute_epoch_id("lock1", "engine1", "pp1")
    assert eid == sha256_hex(canonical(["lock1", "engine1", "pp1"]))


def test_epoch_id_same_inputs_rehit_after_revert():
    # A revert reproducing prior content reproduces the prior epoch_id (cache re-hit).
    assert compute_epoch_id("a", "b", "c") == compute_epoch_id("a", "b", "c")


def test_epoch_id_changes_when_any_input_changes():
    base = compute_epoch_id("a", "b", "c")
    assert compute_epoch_id("a2", "b", "c") != base
    assert compute_epoch_id("a", "b2", "c") != base
    assert compute_epoch_id("a", "b", "c2") != base


def test_epoch_carries_seq_and_id():
    e = Epoch(epoch_seq=3, epoch_id="deadbeef")
    assert e.epoch_seq == 3 and e.epoch_id == "deadbeef"


def test_epoch_bump_carries_new_epoch_and_section_allowlist():
    eb = EpochBump(new_epoch=Epoch(epoch_seq=4, epoch_id="x"), sections=["sec.a"])
    assert eb.new_epoch.epoch_seq == 4
    assert eb.sections == ["sec.a"]


# --- runtime / graph / envelope holders ------------------------------------


def test_node_runtime_state_defaults():
    rt = NodeRuntimeState(node_id="n1")
    assert rt.status == NodeStatus.PENDING
    assert rt.attempt == 0
    assert rt.budget_consumed == {"tokens": 0, "usd": 0.0}
    assert rt.error_class == ErrorClass.NONE
    assert rt.reservation_id is None


def test_taskgraph_holds_nodes_and_edges():
    g = TaskGraph(
        nodes=[NodeSpec(id="a", role="worker", objective="o")],
        edges=[("a", "b")],
        seed=7,
    )
    assert g.nodes[0].id == "a"
    assert g.edges == [("a", "b")]
    assert g.seed == 7


def test_result_envelope_defaults_succeeded_with_exact_accounting():
    env = ResultEnvelope(node_id="n1", idempotency_key="k", status="succeeded")
    assert env.failure_class is None
    assert env.token_usage["accounting"] == "exact"
    assert env.artifact == {}
    assert env.concerns == []


def test_section_conflict_shape():
    sc = SectionConflict(
        section="sec.a",
        epoch="eid",
        existing_writer_node="n1",
        attempted_writer_node="n2",
        reason="different-writer",
    )
    assert sc.reason == "different-writer"


def test_mapspec_fields():
    ms = MapSpec(
        collection_input="src",
        element_artifact="items",
        max_fanout=4,
        child_template="{{input.src.artifact.items}}",
    )
    assert ms.max_fanout == 4
    assert ms.weights is None
