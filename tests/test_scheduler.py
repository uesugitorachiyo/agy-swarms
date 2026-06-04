"""FR-5 scheduler — ready-set, §D.1 state machine, back-pressure, FR-5.1 skip.

The scheduler is the engine's deterministic in-memory bookkeeping: it answers *which*
nodes are ready (all `dependencies` committed, FR-5), guards the §D.1 status state
machine (only the 9 tabled transitions are legal), bounds in-flight dispatch to the
config-derived concurrency cap (CON-8: `min(provider headroom, cores − 2)`, never
model-chosen), and propagates the FR-5.1 barrier-failure disposition — a terminal
``failed`` node skips its transitive dependents while leaving in-flight siblings to run
(no fail-fast cancellation). It does NO I/O and is fully synchronous; the conductor
composes it with the budget ledger, adapters, and checkpoint journal.
"""

import pytest

from agy_swarms.scheduler import (
    Scheduler,
    SchedulerError,
    assert_transition,
    can_transition,
    concurrency_cap,
)
from agy_swarms.types import NodeSpec, NodeStatus, TaskGraph

S = NodeStatus


def _node(node_id, deps=()):
    return NodeSpec(id=node_id, role="worker", objective="o", dependencies=list(deps))


def _graph(*nodes):
    return TaskGraph(nodes=list(nodes))


# --- CON-8 concurrency cap -------------------------------------------------


def test_concurrency_cap_is_cores_minus_two_when_headroom_is_higher():
    assert concurrency_cap(provider_headroom=100, cpu_cores=10) == 8


def test_concurrency_cap_is_headroom_when_headroom_is_lower():
    assert concurrency_cap(provider_headroom=3, cpu_cores=10) == 3


def test_concurrency_cap_floors_at_one_for_tiny_machines():
    assert concurrency_cap(provider_headroom=100, cpu_cores=1) == 1
    assert concurrency_cap(provider_headroom=100, cpu_cores=2) == 1


def test_concurrency_cap_floors_at_one_for_zero_headroom():
    assert concurrency_cap(provider_headroom=0, cpu_cores=10) == 1


# --- §D.1 state machine ----------------------------------------------------


def test_legal_transitions_match_the_spec_table():
    assert can_transition(S.PENDING, S.READY)
    assert can_transition(S.READY, S.RESERVED)
    assert can_transition(S.READY, S.SKIPPED)
    assert can_transition(S.RESERVED, S.RUNNING)
    assert can_transition(S.RESERVED, S.READY)  # release (FR-6 preemption)
    assert can_transition(S.RESERVED, S.SKIPPED)
    assert can_transition(S.RUNNING, S.SUCCEEDED)
    assert can_transition(S.RUNNING, S.FAILED)
    assert can_transition(S.RUNNING, S.READY)  # retry (Transient)
    assert can_transition(S.RUNNING, S.CANCELLED)


def test_pending_cannot_jump_straight_to_running_or_reserved():
    assert not can_transition(S.PENDING, S.RUNNING)
    assert not can_transition(S.PENDING, S.RESERVED)


def test_ready_cannot_skip_reservation_to_running():
    assert not can_transition(S.READY, S.RUNNING)
    assert not can_transition(S.READY, S.SUCCEEDED)


def test_terminal_states_have_no_outgoing_transitions():
    for terminal in (S.SUCCEEDED, S.FAILED, S.SKIPPED, S.CANCELLED):
        for dst in S:
            assert not can_transition(terminal, dst)


def test_assert_transition_raises_on_illegal_edge():
    with pytest.raises(SchedulerError):
        assert_transition(S.SUCCEEDED, S.RUNNING)


def test_assert_transition_silent_on_legal_edge():
    assert_transition(S.PENDING, S.READY)  # no raise


# --- FR-5 ready-set --------------------------------------------------------


def test_ready_set_includes_a_pending_node_with_no_dependencies():
    sched = Scheduler(_graph(_node("a")))
    assert sched.ready_set() == ["a"]


def test_ready_set_excludes_a_node_whose_dependency_is_not_committed():
    sched = Scheduler(_graph(_node("a"), _node("b", deps=["a"])))
    sched.states["a"].status = S.RUNNING  # not yet succeeded
    assert sched.ready_set() == []  # b blocked; a is no longer pending


def test_ready_set_includes_a_node_once_all_dependencies_succeeded():
    sched = Scheduler(_graph(_node("a"), _node("b", deps=["a"])))
    sched.states["a"].status = S.SUCCEEDED
    assert sched.ready_set() == ["b"]


def test_ready_set_excludes_non_pending_nodes():
    sched = Scheduler(_graph(_node("a")))
    sched.states["a"].status = S.RUNNING
    assert sched.ready_set() == []


def test_ready_set_excludes_a_node_with_a_failed_dependency():
    sched = Scheduler(_graph(_node("a"), _node("b", deps=["a"])))
    sched.states["a"].status = S.FAILED
    assert sched.ready_set() == []  # b is blocked, not ready (it will be skipped)


def test_ready_set_preserves_graph_node_order():
    sched = Scheduler(_graph(_node("c"), _node("a"), _node("b")))
    assert sched.ready_set() == ["c", "a", "b"]


# --- mark() drives state transitions through the validator ------------------


def test_mark_advances_status_through_a_legal_edge():
    sched = Scheduler(_graph(_node("a")))
    sched.mark("a", S.READY)
    assert sched.status("a") == S.READY


def test_mark_rejects_an_illegal_edge():
    sched = Scheduler(_graph(_node("a")))
    sched.states["a"].status = S.SUCCEEDED
    with pytest.raises(SchedulerError):
        sched.mark("a", S.RUNNING)


# --- FR-5.1 barrier-failure skip propagation -------------------------------


def test_propagate_skips_marks_a_direct_dependent():
    sched = Scheduler(_graph(_node("a"), _node("b", deps=["a"])))
    sched.states["a"].status = S.FAILED
    skipped = sched.propagate_skips("a")
    assert sched.status("b") == S.SKIPPED
    assert skipped == ["b"]


def test_propagate_skips_is_transitive():
    sched = Scheduler(_graph(_node("a"), _node("b", deps=["a"]), _node("c", deps=["b"])))
    sched.states["a"].status = S.FAILED
    skipped = sched.propagate_skips("a")
    assert sched.status("b") == S.SKIPPED
    assert sched.status("c") == S.SKIPPED
    assert set(skipped) == {"b", "c"}


def test_propagate_skips_skips_a_pending_dependent_too():
    # FR-5.1 "any node whose dependencies include it" — a still-pending dependent
    # must not be left to stall (AC-37); skip is a graph operation, not a transition.
    sched = Scheduler(_graph(_node("a"), _node("b", deps=["a"])))
    sched.states["a"].status = S.FAILED
    assert sched.states["b"].status == S.PENDING
    sched.propagate_skips("a")
    assert sched.status("b") == S.SKIPPED


def test_propagate_skips_does_not_cancel_an_inflight_sibling():
    # FR-5.1: a failed node SHALL NOT fail-fast-cancel siblings already dispatched.
    sched = Scheduler(_graph(_node("a"), _node("s")))  # s does not depend on a
    sched.states["a"].status = S.FAILED
    sched.states["s"].status = S.RUNNING
    sched.propagate_skips("a")
    assert sched.status("s") == S.RUNNING


def test_propagate_skips_leaves_already_succeeded_dependents_untouched():
    sched = Scheduler(_graph(_node("a"), _node("b", deps=["a"])))
    sched.states["a"].status = S.FAILED
    sched.states["b"].status = S.SUCCEEDED  # terminal — no further transitions
    skipped = sched.propagate_skips("a")
    assert sched.status("b") == S.SUCCEEDED
    assert skipped == []


def test_propagate_skips_skips_a_node_depending_on_both_failed_and_succeeded():
    sched = Scheduler(_graph(_node("a"), _node("ok"), _node("d", deps=["a", "ok"])))
    sched.states["a"].status = S.FAILED
    sched.states["ok"].status = S.SUCCEEDED
    sched.propagate_skips("a")
    assert sched.status("d") == S.SKIPPED


# --- back-pressure / dispatch selection (FR-5/CON-8/AC-37) -----------------


def test_select_dispatch_is_bounded_by_the_cap():
    sched = Scheduler(_graph(*[_node(f"n{i}") for i in range(100)]))
    batch = sched.select_dispatch(cap=8, in_flight=0)
    assert len(batch) == 8


def test_select_dispatch_accounts_for_inflight_slots():
    sched = Scheduler(_graph(*[_node(f"n{i}") for i in range(100)]))
    assert len(sched.select_dispatch(cap=8, in_flight=5)) == 3


def test_select_dispatch_returns_empty_when_already_at_cap():
    sched = Scheduler(_graph(*[_node(f"n{i}") for i in range(100)]))
    assert sched.select_dispatch(cap=8, in_flight=8) == []


def test_select_dispatch_returns_all_ready_when_under_cap():
    sched = Scheduler(_graph(_node("a"), _node("b")))
    assert sched.select_dispatch(cap=8, in_flight=0) == ["a", "b"]


def test_select_dispatch_never_returns_negative_slots():
    sched = Scheduler(_graph(_node("a")))
    assert sched.select_dispatch(cap=8, in_flight=20) == []


# --- done detection --------------------------------------------------------


def test_is_done_true_when_every_node_is_terminal():
    sched = Scheduler(_graph(_node("a"), _node("b")))
    sched.states["a"].status = S.SUCCEEDED
    sched.states["b"].status = S.SKIPPED
    assert sched.is_done()


def test_is_done_false_while_a_node_is_still_pending():
    sched = Scheduler(_graph(_node("a"), _node("b")))
    sched.states["a"].status = S.SUCCEEDED
    assert not sched.is_done()


# --- AC-37 back-pressure / no-stall over 100 nodes -------------------------


def test_100_ready_nodes_drain_without_stalling_under_the_cap():
    cap = concurrency_cap(provider_headroom=100, cpu_cores=10)  # 8
    sched = Scheduler(_graph(*[_node(f"n{i}") for i in range(100)]))
    waves = 0
    max_batch = 0
    dispatched_total = 0
    while not sched.is_done():
        batch = sched.select_dispatch(cap=cap, in_flight=0)
        assert batch, "scheduler stalled with work remaining (AC-37 violation)"
        max_batch = max(max_batch, len(batch))
        dispatched_total += len(batch)
        for node_id in batch:  # drive the full lifecycle for this wave
            sched.mark(node_id, S.READY)
            sched.mark(node_id, S.RESERVED)
            sched.mark(node_id, S.RUNNING)
            sched.mark(node_id, S.SUCCEEDED)
        waves += 1
        assert waves <= 100, "non-termination — scheduler is looping"
    assert dispatched_total == 100  # every node ran exactly once
    assert max_batch <= cap  # in-flight never exceeded the cap (back-pressure)
    assert waves == 13  # ceil(100 / 8) — bounded waves, full drain
