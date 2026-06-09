"""AC-1 — the Phase-1 exit gate (§E AC-1, lines 472-477).

This is the integration gate the whole Phase-1 stack converges on. It drives the real
``Conductor`` over the real ``Scheduler`` / ``BudgetLedger`` / SQLite-WAL ``Checkpoint`` /
``ScriptedAdapter`` and asserts the AC-1 contract end-to-end:

* a fixed **3-node fan-out** runs, checkpoints after each barrier, and **resumes from a
  simulated crash returning cached results** for completed nodes (FR-7);
* a node whose **objective is edited busts the cache** and re-runs — and a **descendant
  whose resolved input therefore changes re-runs too** (idempotency_key folds input
  digests, §D.1 [H4]); an unaffected sibling stays cached;
* a **checkpoint-epoch bump busts the whole journal** (FR-7 cache validity folds epoch_id);
* **FR-5.1 barrier-failure:** a node that fails after ``max_schema_retries`` leaves its
  siblings committed and its dependents ``skipped`` (no fail-fast cancellation);
* **FR-6.6 cap-overrun:** a node whose actual output overshoots its caps demonstrates total
  spend ≤ ``budget + one in-flight batch's summed admitted ceilings`` — the run stops
  scheduling, checkpoints, and returns best-so-far;
* **NFR-4/FR-8.4 all-or-none:** a crash injected mid barrier-commit leaves the whole
  barrier unapplied while prior barriers stay durable (SQLite-WAL, CON-12);
* **cross-resume monotonicity:** a committed node's ``budget_consumed`` survives resume
  (never reset to zero) and the ledger refuses a fresh full re-spend; a retry-exhausted
  node stays ``failed`` with ``remaining_schema_retries==0`` across N≥3 resumes;
* **pipeline():** N items keep input order through ≥2 stages, a resumed run re-runs only an
  item's first uncommitted stage (committed items return cached), and one failing item is
  isolated with a blocker while the others complete.
"""

from dataclasses import asdict

import pytest

from agy_swarms.budget import BudgetLedger, Dims
from agy_swarms.canonical import canonical
from agy_swarms.checkpoint import Checkpoint, CheckpointError, JournalEntry
from agy_swarms.conductor import Conductor, RunReport
from agy_swarms.types import (
    Caps,
    ErrorClass,
    NodeSpec,
    NodeStatus,
    RetryPolicy,
    RunStatus,
    TaskGraph,
)
from tests.conductor_support import LIMIT as _LIMIT
from tests.conductor_support import CountingAdapter as _Counting
from tests.conductor_support import FakeAdapter
from tests.conductor_support import envelope as _env
from tests.conductor_support import epoch as _epoch
from tests.conductor_support import fanout_graph as _fanout_graph
from tests.conductor_support import scripted_fanout_adapter as _scripted


class EchoAdapter:
    """Echoes a node's objective into its declared outputs — so an objective edit changes
    the artifact, which flows into a dependent's resolved input (descendant cache-bust)."""

    accounting = "exact"

    def __init__(self):
        self.calls: list[str] = []

    def covers(self, required):
        return True

    def run(self, node, *, attempt=0, reservation_id=None):
        self.calls.append(node.id)
        outs = node.outputs or ["out"]
        return _env("succeeded", artifact={name: node.objective for name in outs})


class CrashAtBarrier:
    """Wraps a Checkpoint and aborts the ``crash_on``-th barrier commit by appending a
    malformed entry — exercising the real SQLite all-or-none rollback (NFR-4/FR-8.4)."""

    def __init__(self, inner, *, crash_on):
        self.inner = inner
        self.crash_on = crash_on
        self.n = 0

    def lookup(self, key):
        return self.inner.lookup(key)

    def get_runtime(self, node_id):
        return self.inner.get_runtime(node_id)

    def commit_barrier(self, entries):
        self.n += 1
        if self.n == self.crash_on:
            bad = JournalEntry(
                node_id="",  # invalid → inner raises and rolls back the WHOLE barrier
                idempotency_key="bad",
                epoch_id=self.inner.epoch.epoch_id,
                epoch_seq=self.inner.epoch.epoch_seq,
                status="failed",
                attempt=0,
                remaining_schema_retries=0,
            )
            self.inner.commit_barrier([*entries, bad])
        else:
            self.inner.commit_barrier(entries)

    def close(self):
        self.inner.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.inner.close()


# --- AC-1 : determinism (M5 / FR-2) ----------------------------------------


def test_ac1_fanout_runs_byte_identically_twice():
    c1 = Conductor(_fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch())
    c2 = Conductor(_fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch())
    r1, r2 = c1.run(), c2.run()
    assert r1.status == RunStatus.SUCCEEDED
    # byte-identical RunReport
    assert canonical(asdict(r1)) == canonical(asdict(r2))
    # ... and explicitly: same idempotency_keys, artifacts, budget_consumed
    assert {k: v.idempotency_key for k, v in r1.results.items()} == {
        k: v.idempotency_key for k, v in r2.results.items()
    }
    assert {k: v.artifact for k, v in r1.results.items()} == {
        k: v.artifact for k, v in r2.results.items()
    }
    assert {nid: c1.runtime[nid].budget_consumed for nid in c1.runtime} == {
        nid: c2.runtime[nid].budget_consumed for nid in c2.runtime
    }


# --- AC-1 : checkpoint-after-barrier + resume cache-hit (FR-7) --------------


def test_ac1_checkpoints_every_node_after_each_barrier(tmp_path):
    path = tmp_path / "ck.db"
    with Checkpoint(path, _epoch()) as ck:
        Conductor(_fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck).run()
    with Checkpoint(path, _epoch()) as verify:
        assert verify.get_runtime("root") is not None
        assert verify.get_runtime("a") is not None
        assert verify.get_runtime("b") is not None


def test_ac1_resume_returns_cached_results_without_redispatch(tmp_path):
    path = tmp_path / "ck.db"
    with Checkpoint(path, _epoch()) as ck:
        Conductor(_fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck).run()
    counting = _Counting(_scripted())
    with Checkpoint(path, _epoch()) as ck2:
        report = Conductor(
            _fanout_graph(), counting, limit=_LIMIT, epoch=_epoch(), checkpoint=ck2
        ).run()
    assert counting.calls == []  # every completed node cache-hits
    assert report.status == RunStatus.SUCCEEDED
    assert report.results["a"].artifact == {"x": 2}  # cached artifact returned verbatim


def test_ac1_partial_crash_resumes_only_uncommitted_nodes(tmp_path):
    # crash after barrier 1 (root committed) → resume re-runs only a, b
    path = tmp_path / "ck.db"
    with CrashAtBarrier(Checkpoint(path, _epoch()), crash_on=2) as ck:
        with pytest.raises(CheckpointError):
            Conductor(
                _fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck
            ).run()
    counting = _Counting(_scripted())
    with Checkpoint(path, _epoch()) as ck2:
        report = Conductor(
            _fanout_graph(), counting, limit=_LIMIT, epoch=_epoch(), checkpoint=ck2
        ).run()
    assert sorted(counting.calls) == ["a", "b"]  # root cached; only its dependents re-run
    assert report.status == RunStatus.SUCCEEDED


# --- AC-1 : objective edit busts the cache (FR-7 / M5) ----------------------


def test_ac1_objective_edit_reruns_only_that_node(tmp_path):
    path = tmp_path / "ck.db"
    with Checkpoint(path, _epoch()) as ck:
        Conductor(_fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck).run()
    counting = _Counting(_scripted())
    with Checkpoint(path, _epoch()) as ck2:
        Conductor(
            _fanout_graph(objective_a="EDITED"),
            counting,
            limit=_LIMIT,
            epoch=_epoch(),
            checkpoint=ck2,
        ).run()
    assert counting.calls == ["a"]  # only the edited node's key changed


def test_ac1_source_edit_reruns_node_and_its_descendant(tmp_path):
    # src → mid (consumes src's "data"); side is independent. Editing src changes src's
    # artifact → mid's resolved input digest changes → mid's key changes → mid re-runs too.
    path = tmp_path / "ck.db"
    src = NodeSpec(id="src", role="worker", objective="X", outputs=["data"])
    mid = NodeSpec(id="mid", role="worker", objective="mid", inputs=["data"], dependencies=["src"])
    side = NodeSpec(id="side", role="worker", objective="side")
    graph = TaskGraph(nodes=[src, mid, side])
    with Checkpoint(path, _epoch()) as ck:
        Conductor(graph, EchoAdapter(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck).run()
    src2 = NodeSpec(id="src", role="worker", objective="Y", outputs=["data"])
    mid2 = NodeSpec(id="mid", role="worker", objective="mid", inputs=["data"], dependencies=["src"])
    side2 = NodeSpec(id="side", role="worker", objective="side")
    echo = EchoAdapter()
    with Checkpoint(path, _epoch()) as ck2:
        Conductor(
            TaskGraph(nodes=[src2, mid2, side2]),
            echo,
            limit=_LIMIT,
            epoch=_epoch(),
            checkpoint=ck2,
        ).run()
    assert sorted(echo.calls) == ["mid", "src"]  # src + its descendant re-run; side cached


# --- AC-1 [F3] : epoch bump busts the whole journal -------------------------


def test_ac1_epoch_bump_busts_whole_journal(tmp_path):
    path = tmp_path / "ck.db"
    with Checkpoint(path, _epoch("E1", 1)) as ck:
        Conductor(
            _fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch("E1", 1), checkpoint=ck
        ).run()
    counting = _Counting(_scripted())
    with Checkpoint(path, _epoch("E2", 2)) as ck2:
        Conductor(
            _fanout_graph(), counting, limit=_LIMIT, epoch=_epoch("E2", 2), checkpoint=ck2
        ).run()
    assert sorted(counting.calls) == ["a", "b", "root"]  # all cold → all re-dispatch


# --- AC-1 [H1] : FR-5.1 barrier-failure disposition ------------------------


def test_ac1_barrier_failure_skips_dependents_and_keeps_siblings():
    # root → {a, b}; a → c. a fails AFTER exhausting max_schema_retries (2 transient tries).
    root = NodeSpec(id="root", role="worker", objective="root")
    a = NodeSpec(
        id="a",
        role="worker",
        objective="a",
        dependencies=["root"],
        retry_policy=RetryPolicy(max_schema_retries=1),
    )
    b = NodeSpec(id="b", role="worker", objective="b", dependencies=["root"])
    c = NodeSpec(id="c", role="worker", objective="c", dependencies=["a"])
    graph = TaskGraph(nodes=[root, a, b, c])
    adapter = FakeAdapter(
        {
            "root": [_env("succeeded")],
            "a": [_env("failed", ErrorClass.TRANSPORT), _env("failed", ErrorClass.TRANSPORT)],
            "b": [_env("succeeded")],
            "c": [_env("succeeded")],
        }
    )
    report = Conductor(graph, adapter, limit=_LIMIT, epoch=_epoch(), cap=4).run()
    assert report.states["a"] == NodeStatus.FAILED  # exhausted retries → terminal
    assert report.states["b"] == NodeStatus.SUCCEEDED  # in-flight sibling still commits
    assert report.states["c"] == NodeStatus.SKIPPED  # dependent of the failed node
    assert adapter.calls.count("a") == 2  # initial + 1 retry, then terminal
    assert "c" not in adapter.calls  # skipped, never dispatched
    assert report.status == RunStatus.FAILED
    assert any(blk["id"] == "a" for blk in report.blockers)
    assert any(blk["id"] == "c" for blk in report.blockers)


# --- AC-1 [H1] : FR-6.6 cap-overrun bound + best-so-far ---------------------


def test_ac1_cap_overrun_bounds_spend_and_returns_best_so_far(tmp_path):
    # a (ceiling 100) overshoots to 250; a 200-token budget then can't admit b or c.
    path = tmp_path / "ck.db"
    a = NodeSpec(id="a", role="worker", objective="a", caps=Caps(max_output_tokens=100))
    b = NodeSpec(
        id="b", role="worker", objective="b", dependencies=["a"], caps=Caps(max_output_tokens=100)
    )
    c = NodeSpec(
        id="c", role="worker", objective="c", dependencies=["b"], caps=Caps(max_output_tokens=100)
    )
    graph = TaskGraph(nodes=[a, b, c])
    adapter = FakeAdapter(
        {"a": [_env("succeeded", out=250)], "b": [_env("succeeded")], "c": [_env("succeeded")]}
    )
    with Checkpoint(path, _epoch()) as ck:
        cond = Conductor(
            graph, adapter, limit=Dims(tokens=200, usd=100.0), epoch=_epoch(), checkpoint=ck
        )
        report = cond.run()
    assert adapter.calls == ["a"]  # scheduling stopped after the overrun batch
    # bound: total spend ≤ budget (200) + one in-flight batch's admitted ceiling (a: 100)
    assert report.spent_tokens <= 200 + 100
    assert report.spent_tokens == 250  # the overrun itself is the only spend
    assert report.status != RunStatus.SUCCEEDED  # best-so-far, not complete
    assert report.blockers
    with Checkpoint(path, _epoch()) as verify:
        assert verify.get_runtime("a") is not None  # checkpointed before stopping


# --- AC-1 [H2] : NFR-4 / FR-8.4 multi-artifact barrier all-or-none ----------


def test_ac1_barrier_commit_is_all_or_none_on_crash(tmp_path):
    path = tmp_path / "ck.db"
    # crash mid barrier-2 (a, b): the whole barrier rolls back; barrier-1 (root) stays.
    with CrashAtBarrier(Checkpoint(path, _epoch()), crash_on=2) as ck:
        with pytest.raises(CheckpointError):
            Conductor(
                _fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck
            ).run()
    with Checkpoint(path, _epoch()) as verify:
        assert verify.get_runtime("root") is not None  # prior barrier durable
        assert verify.get_runtime("a") is None  # neither a ...
        assert verify.get_runtime("b") is None  # ... nor b landed (all-or-none)


# --- AC-1 [H2] : cross-resume budget monotonicity --------------------------


def test_ac1_ledger_refuses_full_respend_after_partial_consumption():
    # the direct §D.4 guarantee: a node at 0.8 ceiling cannot reserve a fresh full ceiling
    node = NodeSpec(id="n", role="worker", objective="o", caps=Caps(max_output_tokens=100))
    ledger = BudgetLedger(_LIMIT)
    admission = ledger.reserve(1, "n", node, epoch_id="E1", budget_consumed=Dims(tokens=80))
    assert not admission.admitted
    assert admission.reason == "node-ceiling"


def test_ac1_cross_resume_preserves_budget_consumed(tmp_path):
    path = tmp_path / "ck.db"
    n1 = NodeSpec(id="n", role="worker", objective="o", caps=Caps(max_output_tokens=100))
    with Checkpoint(path, _epoch()) as ck:
        a1 = FakeAdapter({"n": [_env("succeeded", out=80)]})
        Conductor(TaskGraph(nodes=[n1]), a1, limit=_LIMIT, epoch=_epoch(), checkpoint=ck).run()
    n2 = NodeSpec(id="n", role="worker", objective="o", caps=Caps(max_output_tokens=100))
    with Checkpoint(path, _epoch()) as ck2:
        a2 = _Counting(FakeAdapter({"n": [_env("succeeded", out=80)]}))
        cond = Conductor(TaskGraph(nodes=[n2]), a2, limit=_LIMIT, epoch=_epoch(), checkpoint=ck2)
        cond.run()
    assert a2.calls == []  # committed node cache-hits → never re-spends
    assert cond.runtime["n"].budget_consumed["tokens"] == 80  # persisted, not reset to 0


# --- AC-1 [H2] : retry-exhaustion monotonicity across N≥3 resumes -----------


def test_ac1_retry_exhausted_node_stays_failed_across_resumes(tmp_path):
    path = tmp_path / "ck.db"
    node = NodeSpec(
        id="n", role="worker", objective="o", retry_policy=RetryPolicy(max_schema_retries=1)
    )
    with Checkpoint(path, _epoch()) as ck:
        a1 = FakeAdapter(
            {"n": [_env("failed", ErrorClass.TRANSPORT), _env("failed", ErrorClass.TRANSPORT)]}
        )
        Conductor(TaskGraph(nodes=[node]), a1, limit=_LIMIT, epoch=_epoch(), checkpoint=ck).run()
    for _ in range(3):  # N ≥ 3 resumes
        fresh = NodeSpec(
            id="n", role="worker", objective="o", retry_policy=RetryPolicy(max_schema_retries=1)
        )
        with Checkpoint(path, _epoch()) as ckn:
            counting = _Counting(FakeAdapter({"n": [_env("succeeded")]}))
            cond = Conductor(
                TaskGraph(nodes=[fresh]), counting, limit=_LIMIT, epoch=_epoch(), checkpoint=ckn
            )
            report = cond.run()
            assert counting.calls == []  # no re-dispatch, no fresh retry budget
            assert report.states["n"] == NodeStatus.FAILED
            assert cond.runtime["n"].remaining_schema_retries == 0


# --- AC-1 [F11] : pipeline() end-to-end ------------------------------------


def _stage(name, *, fail_items=()):
    def run_stage(item, prev):
        if item in fail_items:
            return _env("failed", ErrorClass.AUTH, artifact={"stage": name, "item": item})
        carried = (prev or {}).get("seen", [])
        return _env("succeeded", artifact={"item": item, "seen": [*carried, name]})

    return run_stage


def test_ac1_pipeline_preserves_per_item_ordering():
    cond = Conductor(TaskGraph(nodes=[]), _scripted(), limit=_LIMIT, epoch=_epoch())
    results = cond.pipeline(["i0", "i1", "i2"], [_stage("s1"), _stage("s2")])
    assert [r.item for r in results] == ["i0", "i1", "i2"]  # input order preserved
    assert all(r.status == "succeeded" for r in results)
    assert results[1].envelope.artifact["seen"] == ["s1", "s2"]  # both stages, in order


def test_ac1_pipeline_isolates_a_failing_item():
    cond = Conductor(TaskGraph(nodes=[]), _scripted(), limit=_LIMIT, epoch=_epoch())
    results = cond.pipeline(["i0", "i1", "i2"], [_stage("s1"), _stage("s2", fail_items={"i1"})])
    by_item = {r.item: r for r in results}
    assert by_item["i1"].status == "failed"
    assert by_item["i1"].blocker is not None  # surfaces a blocker
    assert by_item["i0"].status == "succeeded"  # the others are unaffected
    assert by_item["i2"].status == "succeeded"


def test_ac1_pipeline_full_resume_returns_cached_items(tmp_path):
    path = tmp_path / "pipe.db"
    with Checkpoint(path, _epoch()) as ck:
        Conductor(
            TaskGraph(nodes=[]), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck
        ).pipeline(["i0", "i1"], [_stage("s1"), _stage("s2")], pipeline_id="P")
    seen: list[str] = []

    def counting_stage(name):
        def run_stage(item, prev):
            seen.append(f"{name}:{item}")
            return _env("succeeded", artifact={"item": item})

        return run_stage

    with Checkpoint(path, _epoch()) as ck2:
        results = Conductor(
            TaskGraph(nodes=[]), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck2
        ).pipeline(["i0", "i1"], [counting_stage("s1"), counting_stage("s2")], pipeline_id="P")
    assert seen == []  # all terminal-stage-committed items cache-hit
    assert all(r.status == "succeeded" for r in results)


def test_ac1_pipeline_partial_item_resumes_from_first_uncommitted_stage(tmp_path):
    # i1's stage-2 "crashes" on the first run (stage-1 committed); resume re-runs only s2:i1.
    path = tmp_path / "pipe.db"

    def crashing_s2(item, prev):
        if item == "i1":
            raise RuntimeError("simulated crash mid-item")
        return _env("succeeded", artifact={"item": item})

    with Checkpoint(path, _epoch()) as ck:
        with pytest.raises(RuntimeError):
            Conductor(
                TaskGraph(nodes=[]), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck
            ).pipeline(["i0", "i1"], [_stage("s1"), crashing_s2], pipeline_id="P")
    seen: list[str] = []

    def counting_stage(name):
        def run_stage(item, prev):
            seen.append(f"{name}:{item}")
            return _env("succeeded", artifact={"item": item})

        return run_stage

    with Checkpoint(path, _epoch()) as ck2:
        Conductor(
            TaskGraph(nodes=[]), _scripted(), limit=_LIMIT, epoch=_epoch(), checkpoint=ck2
        ).pipeline(["i0", "i1"], [counting_stage("s1"), counting_stage("s2")], pipeline_id="P")
    # i0 fully cached; i1's committed stage-1 cached → only its uncommitted stage-2 re-runs
    assert seen == ["s2:i1"]


def test_ac1_run_report_type():
    report = Conductor(_fanout_graph(), _scripted(), limit=_LIMIT, epoch=_epoch()).run()
    assert isinstance(report, RunReport)
