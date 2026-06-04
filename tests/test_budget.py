"""§D.4 budget: ``est()`` (caps-driven estimator) + §D.1.2 deterministic split.

``est(node) = caps.max_output_tokens + caps.max_thinking_tokens`` (billable-equivalent
tokens; line 324). ``split_budget`` is the integer floor+remainder rule (§D.1.2, line 219)
that keeps per-child caps — a hashed field — byte-identical across implementations, so it
takes NO floating-point division and distributes the remainder one unit at a time in
ascending child-index order.
"""

import pytest

from agy_swarms.budget import (
    Admission,
    BudgetError,
    BudgetLedger,
    Dims,
    TokenUsageSummary,
    aggregate_token_usage,
    est,
    split_budget,
)
from agy_swarms.types import Caps, NodeSpec, ResultEnvelope


# --- est() (§D.4) ----------------------------------------------------------


def test_est_is_sum_of_output_and_thinking_caps():
    n = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        caps=Caps(max_output_tokens=100, max_thinking_tokens=50),
    )
    assert est(n) == 150


def test_est_zero_caps_is_zero():
    assert est(NodeSpec(id="n", role="worker", objective="o")) == 0


def test_est_ignores_max_tool_calls():
    n = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        caps=Caps(max_output_tokens=10, max_thinking_tokens=0, max_tool_calls=999),
    )
    assert est(n) == 10


# --- split_budget: equal split (§D.1.2) ------------------------------------


def test_split_equal_exact_division():
    assert split_budget(9, 3) == [3, 3, 3]


def test_split_equal_remainder_goes_to_low_indices():
    assert split_budget(10, 3) == [4, 3, 3]
    assert split_budget(11, 3) == [4, 4, 3]


def test_split_equal_single_child_gets_all():
    assert split_budget(10, 1) == [10]


def test_split_equal_conserves_total_and_is_nonnegative():
    for total in (0, 1, 7, 100, 101):
        for n in (1, 2, 3, 7):
            parts = split_budget(total, n)
            assert sum(parts) == total
            assert len(parts) == n
            assert all(p >= 0 for p in parts)


# --- split_budget: weighted split (§D.1.2) ---------------------------------


def test_split_weighted_even_weights():
    assert split_budget(10, 2, weights=(1, 1)) == [5, 5]


def test_split_weighted_proportional_with_remainder_low_index():
    # wsum=4; floors=[5,2,2] sum 9; remainder 1 → index 0 → [6,2,2]
    assert split_budget(10, 3, weights=(2, 1, 1)) == [6, 2, 2]


def test_split_weighted_conserves_total():
    assert sum(split_budget(100, 3, weights=(5, 3, 2))) == 100


def test_split_weighted_zero_weight_child_floors_to_zero():
    assert split_budget(10, 2, weights=(0, 1)) == [0, 10]


# --- split_budget: errors --------------------------------------------------


def test_split_rejects_nonpositive_n():
    with pytest.raises(ValueError):
        split_budget(10, 0)


def test_split_rejects_weight_length_mismatch():
    with pytest.raises(ValueError):
        split_budget(10, 3, weights=(1, 1))


def test_split_rejects_negative_weight():
    with pytest.raises(ValueError):
        split_budget(10, 2, weights=(-1, 3))


def test_split_rejects_all_zero_weights():
    with pytest.raises(ValueError):
        split_budget(10, 2, weights=(0, 0))


# ===================== Pass B: BudgetLedger (§D.4) =====================


def _node(est_tokens):
    """A node whose ``est()`` is ``est_tokens`` (all in the output cap)."""
    return NodeSpec(
        id="x",
        role="worker",
        objective="o",
        caps=Caps(max_output_tokens=est_tokens, max_thinking_tokens=0),
    )


def test_dims_arithmetic_and_fit():
    a = Dims(tokens=10, usd=1.0)
    b = Dims(tokens=3, usd=0.25)
    assert a + b == Dims(13, 1.25)
    assert a - b == Dims(7, 0.75)
    assert Dims(5, 0.0).fits_within(Dims(5, 0.0))
    assert not Dims(6, 0.0).fits_within(Dims(5, 0.0))
    assert Dims.max(Dims(5, 2.0), Dims(7, 1.0)) == Dims(7, 2.0)


def test_fresh_ledger_available_equals_limit():
    led = BudgetLedger(Dims(tokens=1000))
    assert led.available == Dims(tokens=1000)
    assert led.reserved == Dims()
    assert led.spent == Dims()


def test_reserve_attempt_one_admitted_and_holds_est():
    led = BudgetLedger(Dims(tokens=1000))
    adm = led.reserve(0, "n1", _node(100))
    assert isinstance(adm, Admission)
    assert adm.admitted and adm.reservation_id
    assert led.reserved == Dims(tokens=100)
    assert led.available == Dims(tokens=900)


def test_reserve_is_idempotent_per_node_no_double_count():  # FR-30.1
    led = BudgetLedger(Dims(tokens=1000))
    a1 = led.reserve(0, "n1", _node(100))
    a2 = led.reserve(0, "n1", _node(100))
    assert a2.admitted and a2.reservation_id == a1.reservation_id
    assert led.reserved == Dims(tokens=100)  # not 200


def test_commit_reconciles_releasing_the_delta():
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(0, "n1", _node(100))
    led.commit(0, "n1", Dims(tokens=60))
    assert led.spent == Dims(tokens=60)
    assert led.reserved == Dims()
    assert led.available == Dims(tokens=940)


def test_reserve_commit_cycle_appears_exactly_once():  # AC-S3
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(0, "n1", _node(100))
    led.commit(0, "n1", Dims(tokens=60))
    assert list(led.entries.keys()) == [(0, "n1")]
    e = led.entries[(0, "n1")]
    assert e.status == "committed" and e.committed == Dims(tokens=60)
    assert e.reserved == Dims()


def test_reserve_release_cycle_appears_exactly_once():  # AC-S3
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(0, "n2", _node(100))
    led.release(0, "n2")
    e = led.entries[(0, "n2")]
    assert e.status == "released"
    assert led.reserved == Dims() and led.spent == Dims()
    assert led.available == Dims(tokens=1000)


def test_node_ceiling_admits_attempt_one_at_exact_ceiling():
    led = BudgetLedger(Dims(tokens=10_000))
    adm = led.reserve(0, "n1", _node(100), budget_consumed=Dims())
    assert adm.admitted


def test_node_ceiling_rejects_cumulative_breach_on_retry():  # AC-1 monotonicity (line 476)
    led = BudgetLedger(Dims(tokens=10_000))  # global has ample room
    adm = led.reserve(0, "n1", _node(100), budget_consumed=Dims(tokens=80))
    assert not adm.admitted and adm.reason == "node-ceiling"


def test_global_rejection_when_amount_exceeds_available():
    led = BudgetLedger(Dims(tokens=50))
    adm = led.reserve(0, "n1", _node(100), budget_consumed=Dims())
    assert not adm.admitted and adm.reason == "global"


def test_subtree_limit_gates_independently_of_global():
    led = BudgetLedger(Dims(tokens=10_000))
    led.register_subtree("root", Dims(tokens=30))
    a1 = led.reserve(0, "c1", _node(20), subtree="root")
    a2 = led.reserve(0, "c2", _node(20), subtree="root")
    assert a1.admitted
    assert not a2.admitted and a2.reason == "subtree"


def test_opaque_commit_never_releases_below_reserved_floor():
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(0, "n1", _node(100), accounting="opaque")
    led.commit(0, "n1", Dims(tokens=40), accounting="opaque")
    assert led.spent == Dims(tokens=100)  # floor; never under-billed


def test_opaque_multiplier_scales_reservation():
    led = BudgetLedger(Dims(tokens=1000), opaque_multiplier=3)
    led.reserve(0, "n1", _node(10), accounting="opaque")
    assert led.reserved == Dims(tokens=30)


def test_no_token_count_charges_full_reservation_and_concerns():
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(0, "n1", _node(100))
    led.commit(0, "n1", None)
    assert led.spent == Dims(tokens=100)
    assert led.concerns


def test_overspend_exact_records_actual_and_marks_overspend():
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(0, "n1", _node(100))
    led.commit(0, "n1", Dims(tokens=130))
    e = led.entries[(0, "n1")]
    assert e.status == "overspend"
    assert led.spent == Dims(tokens=130)


def test_orphan_sweep_releases_uncommitted_keeps_committed():  # FR-30
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(0, "done", _node(100))
    led.commit(0, "done", Dims(tokens=50))
    led.reserve(0, "orphan", _node(100))  # reserved, never committed
    released = led.sweep_orphans()
    assert released == ["orphan"]
    assert led.reserved == Dims()  # orphan reservation returned to pool
    assert led.spent == Dims(tokens=50)  # committed untouched


def test_orphan_sweep_scans_all_epoch_seq():  # FR-30 (all prior epochs)
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(1, "a", _node(100))
    led.reserve(2, "b", _node(100))
    released = led.sweep_orphans()
    assert sorted(released) == ["a", "b"]
    assert led.reserved == Dims()


def test_ledger_key_is_epoch_seq_plus_node_id():
    led = BudgetLedger(Dims(tokens=1000))
    led.reserve(1, "n", _node(100))
    led.reserve(2, "n", _node(100))
    assert (1, "n") in led.entries and (2, "n") in led.entries
    assert led.reserved == Dims(tokens=200)


def test_commit_without_reservation_raises():
    led = BudgetLedger(Dims(tokens=1000))
    with pytest.raises(BudgetError):
        led.commit(0, "ghost", Dims(tokens=10))


def test_release_without_open_reservation_is_noop():
    led = BudgetLedger(Dims(tokens=1000))
    led.release(0, "ghost")  # no raise
    led.reserve(0, "n1", _node(100))
    led.commit(0, "n1", Dims(tokens=50))
    led.release(0, "n1")  # already committed → no-op
    assert led.spent == Dims(tokens=50)


def test_aggregate_token_usage_counts_input_output_thinking_cached_and_usd():
    envelopes = [
        ResultEnvelope(
            node_id="a",
            idempotency_key="ka",
            status="succeeded",
            token_usage={
                "input": 10,
                "thinking": 3,
                "output": 7,
                "cached": 5,
                "accounting": "exact",
            },
            cost_usd=0.12,
        ),
        ResultEnvelope(
            node_id="b",
            idempotency_key="kb",
            status="succeeded",
            token_usage={
                "input": 20,
                "thinking": 4,
                "output": 6,
                "cached": 2,
                "accounting": "exact",
            },
            cost_usd=0.30,
        ),
    ]

    assert aggregate_token_usage(envelopes) == TokenUsageSummary(
        input_tokens=30,
        output_tokens=13,
        thinking_tokens=7,
        cached_tokens=7,
        billable_equivalent_tokens=20,
        cost_usd=0.42,
        accounting_modes={"exact": 2},
        concerns=[],
    )


def test_aggregate_token_usage_preserves_opaque_accounting_concern():
    summary = aggregate_token_usage(
        [
            ResultEnvelope(
                node_id="agy-node",
                idempotency_key="k",
                status="succeeded",
                token_usage={"accounting": "opaque"},
            )
        ]
    )

    assert summary.accounting_modes == {"opaque": 1}
    assert summary.concerns == ["agy-node: opaque token accounting"]


def test_check_multiplier_drift_no_drift():
    led = BudgetLedger(Dims(tokens=1000, usd=10.0))
    led.reserve(0, "n1", _node(100))
    led.commit(0, "n1", Dims(tokens=60, usd=2.0))
    assert not led.check_multiplier_drift(1.55, 1.5)
    assert not led.concerns
    assert led.entries[(0, "n1")].committed.usd == 2.0


def test_check_multiplier_drift_with_drift_invalidates_costs():
    led = BudgetLedger(Dims(tokens=1000, usd=10.0))
    led.reserve(0, "n1", _node(100))
    led.commit(0, "n1", Dims(tokens=60, usd=2.0))
    # Drift is (1.7 - 1.5) / 1.5 = 13.3% > 10%
    assert led.check_multiplier_drift(1.7, 1.5)
    assert len(led.concerns) == 1
    assert "Multiplier drift detected" in led.concerns[0]
    assert led.entries[(0, "n1")].committed.usd == 0.0
