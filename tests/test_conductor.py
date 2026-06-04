"""Conductor — the deterministic spine: classify, retry, agent atom, barrier run, pipeline.

The conductor composes the already-built primitives (scheduler §D.1, budget §D.4 ledger,
checkpoint FR-7, scripted adapter FR-17) into the run loop. These tests pin the contracts
the AC-1 Phase-1 exit gate depends on:

* **§D.2 classification** — the total ``error_class → FailureClass`` table + the
  ``timed_out``/fail-closed special cases + the normative retry-eligibility predicate.
* **agent() atom** — ready-time ``idempotency_key``; reserve→run→classify→commit→journal;
  schema-retry (Transient) vs terminal (Deterministic/Budget); cumulative budget admission.
* **run() barrier** — FR-5 ready-set dispatch, FR-5.1 dependent-skip on failure (siblings
  still commit), FR-7 checkpoint-after-barrier, FR-6.6 bounded-overrun best-so-far.
* **resume** — FR-7 cache-hit (no re-dispatch), objective-edit cache-bust, epoch-bump
  cold-bust, cross-resume budget + retry-exhaustion monotonicity.
* **pipeline()** — per-item ordering, per-item failure isolation, per-stage crash-resume.
"""

from dataclasses import asdict

import pytest

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.canonical import canonical
from agy_swarms.checkpoint import Checkpoint
from agy_swarms.conductor import (
    Conductor,
    RunReport,
    classify,
    retry_eligible,
)
from agy_swarms.types import (
    Caps,
    Epoch,
    ErrorClass,
    FailureClass,
    NodeSpec,
    NodeStatus,
    ResultEnvelope,
    RetryPolicy,
    RunStatus,
    TaskGraph,
)

# --- helpers ---------------------------------------------------------------


def _epoch(epoch_id="E1", seq=1):
    return Epoch(epoch_seq=seq, epoch_id=epoch_id)


def _env(
    status="succeeded",
    error_class=ErrorClass.NONE,
    *,
    out=0,
    think=0,
    cost=0.0,
    failure_class=None,
    artifact=None,
):
    return ResultEnvelope(
        node_id="",
        idempotency_key="",
        status=status,
        error_class=error_class,
        failure_class=failure_class,
        artifact=artifact or {},
        token_usage={
            "input": 0,
            "thinking": think,
            "output": out,
            "cached": 0,
            "accounting": "exact",
        },
        cost_usd=cost,
    )


def _fanout_graph(objective_a="do a"):
    """1 source ``root`` fanning out to two leaf workers ``a`` and ``b`` (3 nodes)."""
    root = NodeSpec(id="root", role="worker", objective="root", outputs=["data"])
    a = NodeSpec(id="a", role="worker", objective=objective_a, dependencies=["root"])
    b = NodeSpec(id="b", role="worker", objective="do b", dependencies=["root"])
    return TaskGraph(nodes=[root, a, b], edges=[("root", "a"), ("root", "b")])


def _scripted():
    return ScriptedAdapter(
        {
            "root": CannedResult(artifact={"data": 1}),
            "a": CannedResult(artifact={"x": 2}),
            "b": CannedResult(artifact={"y": 3}),
        }
    )


class _Counting:
    """Wraps any adapter and records the node ids dispatched (to assert no re-dispatch)."""

    def __init__(self, inner):
        self.inner = inner
        self.accounting = inner.accounting
        self.calls: list[str] = []

    def covers(self, required):
        return self.inner.covers(required)

    def run(self, node, *, attempt=0, reservation_id=None):
        self.calls.append(node.id)
        return self.inner.run(node, attempt=attempt, reservation_id=reservation_id)


class FakeAdapter:
    """Returns scripted envelopes per node id (one per attempt) — drives failure paths."""

    def __init__(self, script, *, accounting="exact"):
        self.script = {k: list(v) for k, v in script.items()}
        self.accounting = accounting
        self.calls: list[str] = []

    def covers(self, required):
        return True

    def run(self, node, *, attempt=0, reservation_id=None):
        self.calls.append(node.id)
        return self.script[node.id].pop(0)


def _conductor(graph, adapter, *, limit=None, epoch=None, checkpoint=None, cap=4):
    return Conductor(
        graph,
        adapter,
        limit=limit or Dims(tokens=1_000_000, usd=1000.0),
        epoch=epoch or _epoch(),
        checkpoint=checkpoint,
        cap=cap,
    )


# --- §D.2 classify() : the total error_class → FailureClass table -----------


def test_classify_succeeded_is_none():
    assert classify(_env("succeeded", ErrorClass.NONE)) is None


@pytest.mark.parametrize(
    "error_class",
    [ErrorClass.SCHEMA_INVALID, ErrorClass.TRANSPORT, ErrorClass.TIMEOUT, ErrorClass.TOOL],
)
def test_classify_transient_classes(error_class):
    assert classify(_env("failed", error_class)) == FailureClass.TRANSIENT


@pytest.mark.parametrize("error_class", [ErrorClass.AUTH, ErrorClass.UNKNOWN])
def test_classify_deterministic_classes(error_class):
    assert classify(_env("failed", error_class)) == FailureClass.DETERMINISTIC


def test_classify_budget_class():
    assert classify(_env("failed", ErrorClass.BUDGET)) == FailureClass.BUDGET


def test_classify_timed_out_is_transient():
    # orchestrator-set on a kill; the worker returns no class (§D.2)
    assert classify(_env("timed_out", ErrorClass.TIMEOUT)) == FailureClass.TRANSIENT


def test_classify_failed_with_none_is_failclosed_deterministic():
    # fail-closed rule: status==failed + error_class==none ⇒ Deterministic, never retryable
    assert classify(_env("failed", ErrorClass.NONE)) == FailureClass.DETERMINISTIC


def test_classify_honors_a_preset_failure_class():
    # an orchestrator/worker-set class takes precedence over the table (§D.2)
    env = _env("failed", ErrorClass.TRANSPORT, failure_class=FailureClass.DETERMINISTIC)
    assert classify(env) == FailureClass.DETERMINISTIC


# --- §D.2 retry-eligibility predicate --------------------------------------


def test_retry_eligible_transient_with_retries_and_allowed_class():
    assert retry_eligible(FailureClass.TRANSIENT, ErrorClass.TRANSPORT, 1, ("transport", "timeout"))


def test_retry_not_eligible_when_retries_exhausted():
    assert not retry_eligible(
        FailureClass.TRANSIENT, ErrorClass.TRANSPORT, 0, ("transport", "timeout")
    )


def test_retry_not_eligible_for_deterministic():
    assert not retry_eligible(
        FailureClass.DETERMINISTIC, ErrorClass.AUTH, 3, ("transport", "timeout")
    )


def test_retry_not_eligible_for_budget():
    assert not retry_eligible(FailureClass.BUDGET, ErrorClass.BUDGET, 3, ("transport", "timeout"))


def test_retry_policy_narrows_the_transient_set():
    # schema_invalid is Transient, but a policy omitting it can only subtract (§D.2)
    assert not retry_eligible(
        FailureClass.TRANSIENT, ErrorClass.SCHEMA_INVALID, 3, ("transport", "timeout")
    )


def test_retry_eligible_none_failure_class_is_false():
    assert not retry_eligible(None, ErrorClass.NONE, 3, ("transport", "timeout"))


# --- agent() atom : single-node lifecycle ----------------------------------


def test_agent_happy_path_succeeds_and_records_result():
    graph = TaskGraph(nodes=[NodeSpec(id="n", role="worker", objective="o")])
    adapter = ScriptedAdapter({"n": CannedResult(artifact={"ok": True})})
    cond = _conductor(graph, adapter)
    env = cond.agent(graph.nodes[0])
    assert env.status == "succeeded"
    assert env.artifact == {"ok": True}
    assert cond.runtime["n"].status == NodeStatus.SUCCEEDED
    assert cond.results["n"] is env


def test_agent_stamps_ready_time_idempotency_key():
    node = NodeSpec(id="n", role="worker", objective="o")
    cond = _conductor(TaskGraph(nodes=[node]), ScriptedAdapter({"n": CannedResult()}))
    env = cond.agent(node)
    assert node.idempotency_key  # computed at ready-time (§D.1 [H4])
    assert env.idempotency_key == node.idempotency_key


def test_agent_schema_retry_then_succeeds():
    node = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        retry_policy=RetryPolicy(max_schema_retries=2),
    )
    adapter = FakeAdapter({"n": [_env("failed", ErrorClass.TRANSPORT), _env("succeeded")]})
    cond = _conductor(TaskGraph(nodes=[node]), adapter)
    env = cond.agent(node)
    assert env.status == "succeeded"
    assert adapter.calls == ["n", "n"]  # one retry
    assert cond.runtime["n"].remaining_schema_retries == 1  # 2 → 1 after one retry
    assert cond.runtime["n"].attempt == 2


def test_agent_retry_exhaustion_marks_failed():
    node = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        retry_policy=RetryPolicy(max_schema_retries=1),
    )
    adapter = FakeAdapter(
        {"n": [_env("failed", ErrorClass.TRANSPORT), _env("failed", ErrorClass.TRANSPORT)]}
    )
    cond = _conductor(TaskGraph(nodes=[node]), adapter)
    env = cond.agent(node)
    assert env.status == "failed"
    assert cond.runtime["n"].status == NodeStatus.FAILED
    assert cond.runtime["n"].remaining_schema_retries == 0
    assert adapter.calls == ["n", "n"]  # initial + 1 retry, then terminal


def test_agent_deterministic_failure_does_not_retry():
    node = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        retry_policy=RetryPolicy(max_schema_retries=3),
    )
    adapter = FakeAdapter({"n": [_env("failed", ErrorClass.AUTH)]})
    cond = _conductor(TaskGraph(nodes=[node]), adapter)
    env = cond.agent(node)
    assert env.status == "failed"
    assert cond.runtime["n"].status == NodeStatus.FAILED
    assert adapter.calls == ["n"]  # no retry on Deterministic


def test_agent_budget_failure_does_not_retry():
    node = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        retry_policy=RetryPolicy(max_schema_retries=3),
    )
    adapter = FakeAdapter({"n": [_env("failed", ErrorClass.BUDGET)]})
    cond = _conductor(TaskGraph(nodes=[node]), adapter)
    env = cond.agent(node)
    assert env.status == "failed"
    assert classify(env) == FailureClass.BUDGET
    assert adapter.calls == ["n"]  # Budget is terminal


def test_agent_commits_actual_billable_tokens():
    node = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        caps=Caps(max_output_tokens=100, max_thinking_tokens=100),
    )
    adapter = FakeAdapter({"n": [_env("succeeded", out=30, think=20, cost=0.05)]})
    cond = _conductor(TaskGraph(nodes=[node]), adapter)
    cond.agent(node)
    # billable = output + thinking (thinking billed as output, §D.4)
    assert cond.runtime["n"].budget_consumed["tokens"] == 50
    assert cond.ledger.spent.tokens == 50


def test_agent_cumulative_budget_blocks_retry_after_spend():
    # a Transient failure that consumed tokens cannot retry a fresh full ceiling (§D.4 line 359)
    node = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        caps=Caps(max_output_tokens=100, max_thinking_tokens=0),
        retry_policy=RetryPolicy(max_schema_retries=3),
    )
    adapter = FakeAdapter({"n": [_env("failed", ErrorClass.TRANSPORT, out=80)]})
    cond = _conductor(TaskGraph(nodes=[node]), adapter)
    env = cond.agent(node)
    assert env.status == "failed"  # cumulative admission rejects the retry → terminal
    assert adapter.calls == ["n"]  # not re-dispatched


# --- run() : barrier driver over the 3-node fan-out ------------------------


def test_run_fanout_all_succeed():
    graph = _fanout_graph()
    report = _conductor(graph, _scripted()).run()
    assert report.status == RunStatus.SUCCEEDED
    assert set(report.results) == {"root", "a", "b"}
    assert report.states["a"] == NodeStatus.SUCCEEDED
    assert report.results["a"].artifact == {"x": 2}


def test_run_is_byte_identical_across_two_runs():
    # AC-1 determinism: two fresh runs of the scripted fan-out → identical RunReports
    r1 = _conductor(_fanout_graph(), _scripted()).run()
    r2 = _conductor(_fanout_graph(), _scripted()).run()
    assert canonical(asdict(r1)) == canonical(asdict(r2))


def test_run_records_idempotency_keys_stably():
    r1 = _conductor(_fanout_graph(), _scripted()).run()
    r2 = _conductor(_fanout_graph(), _scripted()).run()
    keys1 = {nid: env.idempotency_key for nid, env in r1.results.items()}
    keys2 = {nid: env.idempotency_key for nid, env in r2.results.items()}
    assert keys1 == keys2
    assert all(keys1.values())


# --- FR-5.1 barrier-failure disposition ------------------------------------


def test_run_failed_node_skips_its_dependents():
    # root → a → c ; root → b. Plant a failing 'a'; c (its dependent) is skipped, b commits.
    root = NodeSpec(id="root", role="worker", objective="root")
    a = NodeSpec(id="a", role="worker", objective="a", dependencies=["root"])
    b = NodeSpec(id="b", role="worker", objective="b", dependencies=["root"])
    c = NodeSpec(id="c", role="worker", objective="c", dependencies=["a"])
    graph = TaskGraph(nodes=[root, a, b, c])
    adapter = FakeAdapter(
        {
            "root": [_env("succeeded")],
            "a": [_env("failed", ErrorClass.AUTH)],  # Deterministic → terminal failed
            "b": [_env("succeeded")],
            "c": [_env("succeeded")],
        }
    )
    report = _conductor(graph, adapter).run()
    assert report.states["a"] == NodeStatus.FAILED
    assert report.states["c"] == NodeStatus.SKIPPED  # transitive dependent of failed a
    assert report.states["b"] == NodeStatus.SUCCEEDED  # sibling still commits
    assert "c" not in adapter.calls  # skipped node never dispatched
    assert report.status == RunStatus.FAILED
    assert any(blk.get("id") == "a" for blk in report.blockers)


def test_run_does_not_fail_fast_cancel_in_flight_siblings():
    # a and b are dispatched in the SAME barrier batch; a fails but b still commits (FR-5.1)
    root = NodeSpec(id="root", role="worker", objective="root")
    a = NodeSpec(id="a", role="worker", objective="a", dependencies=["root"])
    b = NodeSpec(id="b", role="worker", objective="b", dependencies=["root"])
    graph = TaskGraph(nodes=[root, a, b])
    adapter = FakeAdapter(
        {
            "root": [_env("succeeded")],
            "a": [_env("failed", ErrorClass.AUTH)],
            "b": [_env("succeeded")],
        }
    )
    report = _conductor(graph, adapter, cap=4).run()
    assert report.states["b"] == NodeStatus.SUCCEEDED
    assert "b" in adapter.calls


# --- FR-7 resume : cache-hit, cache-bust, epoch-bump -----------------------


def test_resume_cache_hit_does_not_redispatch(tmp_path):
    path = tmp_path / "ck.db"
    graph = _fanout_graph()
    with Checkpoint(path, _epoch()) as ck:
        _conductor(graph, _scripted(), checkpoint=ck).run()
    # second run (resume) on the same journal + epoch → every node cache-hits
    counting = _Counting(_scripted())
    with Checkpoint(path, _epoch()) as ck2:
        report = _conductor(_fanout_graph(), counting, checkpoint=ck2).run()
    assert counting.calls == []  # NO re-dispatch
    assert report.status == RunStatus.SUCCEEDED
    assert report.results["a"].artifact == {"x": 2}  # cached artifact returned


def test_resume_objective_edit_busts_only_that_node(tmp_path):
    path = tmp_path / "ck.db"
    with Checkpoint(path, _epoch()) as ck:
        _conductor(_fanout_graph(), _scripted(), checkpoint=ck).run()
    # edit a's objective → a's idempotency_key changes → a re-runs; root/b cache-hit
    counting = _Counting(_scripted())
    with Checkpoint(path, _epoch()) as ck2:
        _conductor(_fanout_graph(objective_a="DIFFERENT"), counting, checkpoint=ck2).run()
    assert counting.calls == ["a"]  # only the edited node re-dispatches


def test_resume_epoch_bump_busts_whole_journal(tmp_path):
    path = tmp_path / "ck.db"
    with Checkpoint(path, _epoch("E1", seq=1)) as ck:
        _conductor(_fanout_graph(), _scripted(), checkpoint=ck, epoch=_epoch("E1", 1)).run()
    counting = _Counting(_scripted())
    with Checkpoint(path, _epoch("E2", seq=2)) as ck2:
        _conductor(_fanout_graph(), counting, checkpoint=ck2, epoch=_epoch("E2", 2)).run()
    assert sorted(counting.calls) == ["a", "b", "root"]  # all cold → all re-dispatch


# --- FR-6.6 bounded-overrun / best-so-far ----------------------------------


def test_run_cap_overrun_stops_scheduling_and_bounds_spend():
    # 'big' overspends its ceiling; the run then stops scheduling 'next' (best-so-far).
    big = NodeSpec(
        id="big",
        role="worker",
        objective="big",
        caps=Caps(max_output_tokens=100, max_thinking_tokens=0),
    )
    nxt = NodeSpec(
        id="next",
        role="worker",
        objective="next",
        dependencies=["big"],
        caps=Caps(max_output_tokens=100, max_thinking_tokens=0),
    )
    graph = TaskGraph(nodes=[big, nxt])
    # actual output 250 >> reserved ceiling 100 (the cap-overrun), exhausting a 200 budget
    adapter = FakeAdapter({"big": [_env("succeeded", out=250)], "next": [_env("succeeded")]})
    report = _conductor(graph, adapter, limit=Dims(tokens=200, usd=100.0)).run()
    assert "next" not in adapter.calls  # scheduling stopped after the overrun
    # bound: total spend ≤ budget + one in-flight batch's summed admitted ceilings (100)
    assert report.spent_tokens <= 200 + 100
    assert report.status != RunStatus.SUCCEEDED
    assert report.blockers  # best-so-far carries a blocker


# --- AC-1 [H2] cross-resume monotonicity -----------------------------------


def test_cross_resume_budget_monotonicity(tmp_path):
    # a node that consumed 0.8 ceiling pre-crash is not admitted to re-spend a fresh ceiling
    path = tmp_path / "ck.db"
    node = NodeSpec(
        id="n",
        role="worker",
        objective="o",
        caps=Caps(max_output_tokens=100, max_thinking_tokens=0),
    )
    # first run: node succeeds consuming 80 of its 100 ceiling, journaled
    with Checkpoint(path, _epoch()) as ck:
        a1 = FakeAdapter({"n": [_env("succeeded", out=80)]})
        _conductor(TaskGraph(nodes=[node]), a1, checkpoint=ck).run()
    # resume: cache-hit means it is NOT re-dispatched and its consumed budget is preserved
    with Checkpoint(path, _epoch()) as ck2:
        a2 = _Counting(FakeAdapter({"n": [_env("succeeded", out=80)]}))
        cond = _conductor(
            TaskGraph(
                nodes=[
                    NodeSpec(id="n", role="worker", objective="o", caps=Caps(max_output_tokens=100))
                ]
            ),
            a2,
            checkpoint=ck2,
        )
        cond.run()
    assert a2.calls == []  # committed node cache-hits; never re-spends
    assert cond.runtime["n"].budget_consumed["tokens"] == 80  # persisted, not reset to 0


def test_cross_resume_retry_exhaustion_stays_failed(tmp_path):
    # a node that exhausted retries stays failed across N≥3 resumes (no fresh retry budget)
    path = tmp_path / "ck.db"
    node = NodeSpec(
        id="n", role="worker", objective="o", retry_policy=RetryPolicy(max_schema_retries=1)
    )
    with Checkpoint(path, _epoch()) as ck:
        a1 = FakeAdapter(
            {"n": [_env("failed", ErrorClass.TRANSPORT), _env("failed", ErrorClass.TRANSPORT)]}
        )
        _conductor(TaskGraph(nodes=[node]), a1, checkpoint=ck).run()
    for _ in range(3):
        with Checkpoint(path, _epoch()) as ckn:
            counting = _Counting(FakeAdapter({"n": [_env("succeeded")]}))
            cond = _conductor(
                TaskGraph(
                    nodes=[
                        NodeSpec(
                            id="n",
                            role="worker",
                            objective="o",
                            retry_policy=RetryPolicy(max_schema_retries=1),
                        )
                    ]
                ),
                counting,
                checkpoint=ckn,
            )
            report = cond.run()
            assert counting.calls == []  # no re-dispatch, no fresh retry
            assert report.states["n"] == NodeStatus.FAILED
            assert cond.runtime["n"].remaining_schema_retries == 0


# --- pipeline() : per-item ordering, isolation, per-stage resume -----------


def _stage(name, *, fail_items=()):
    """A pipeline stage callable: ok unless the item is planted to fail at this stage."""

    def run_stage(item, prev):
        if item in fail_items:
            return _env("failed", ErrorClass.AUTH, artifact={"stage": name, "item": item})
        carried = (prev or {}).get("seen", [])
        return _env("succeeded", artifact={"stage": name, "item": item, "seen": [*carried, name]})

    return run_stage


def test_pipeline_streams_items_through_stages_in_order():
    cond = _conductor(TaskGraph(nodes=[]), _scripted())
    results = cond.pipeline(["i0", "i1", "i2"], [_stage("s1"), _stage("s2")])
    assert [r.item for r in results] == ["i0", "i1", "i2"]  # per-item ordering preserved
    assert all(r.status == "succeeded" for r in results)
    assert results[0].envelope.artifact["seen"] == ["s1", "s2"]  # both stages, in order


def test_pipeline_isolates_one_failing_item():
    cond = _conductor(TaskGraph(nodes=[]), _scripted())
    results = cond.pipeline(["i0", "i1", "i2"], [_stage("s1"), _stage("s2", fail_items={"i1"})])
    by_item = {r.item: r for r in results}
    assert by_item["i1"].status == "failed"
    assert by_item["i1"].blocker is not None  # surfaces a blocker
    assert by_item["i0"].status == "succeeded"  # others unaffected
    assert by_item["i2"].status == "succeeded"


def test_pipeline_crash_resume_skips_committed_items(tmp_path):
    path = tmp_path / "pipe.db"
    with Checkpoint(path, _epoch()) as ck:
        cond = _conductor(TaskGraph(nodes=[]), _scripted(), checkpoint=ck)
        cond.pipeline(["i0", "i1"], [_stage("s1"), _stage("s2")], pipeline_id="P")
    # resume: a counting stage proves committed items are NOT re-executed
    seen_calls: list[str] = []

    def counting_stage(name):
        def run_stage(item, prev):
            seen_calls.append(f"{name}:{item}")
            return _env("succeeded", artifact={"stage": name, "item": item})

        return run_stage

    with Checkpoint(path, _epoch()) as ck2:
        cond2 = _conductor(TaskGraph(nodes=[]), _scripted(), checkpoint=ck2)
        results = cond2.pipeline(
            ["i0", "i1"], [counting_stage("s1"), counting_stage("s2")], pipeline_id="P"
        )
    assert seen_calls == []  # all terminal-stage-committed items cache-hit on resume
    assert all(r.status == "succeeded" for r in results)


def test_run_report_is_a_dataclass_with_run_status():
    report = _conductor(_fanout_graph(), _scripted()).run()
    assert isinstance(report, RunReport)
    assert report.status in {RunStatus.SUCCEEDED, RunStatus.FAILED}
