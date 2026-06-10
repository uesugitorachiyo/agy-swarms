"""Contracts for small conductor helper modules."""

from types import SimpleNamespace

from agy_swarms.adapters.scripted import ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.conductor import RunReport, classify, retry_eligible
from agy_swarms.lockfile import Lockfile
from agy_swarms.types import (
    DriftRecord,
    Epoch,
    ErrorClass,
    FailureClass,
    NodeRuntimeState,
    NodeSpec,
    NodeStatus,
    Reducer,
    ResultEnvelope,
    TaskGraph,
)


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


def test_conductor_report_module_exports_report_shapes():
    from agy_swarms.conductor_reports import RunReport as ExtractedRunReport

    assert ExtractedRunReport is RunReport


def test_conductor_retry_module_exports_failure_policy_helpers():
    from agy_swarms.conductor_retry import classify as extracted_classify
    from agy_swarms.conductor_retry import retry_eligible as extracted_retry_eligible

    assert extracted_classify is classify
    assert extracted_retry_eligible is retry_eligible
    assert extracted_classify(_env("failed", ErrorClass.TRANSPORT)) == FailureClass.TRANSIENT
    assert extracted_retry_eligible(
        extracted_classify(_env("failed", ErrorClass.TRANSPORT)),
        ErrorClass.TRANSPORT,
        1,
        ("transport",),
    )


def test_conductor_codex_batch_helper_is_importable():
    from agy_swarms.conductor_codex_batch import can_codex_review_batch
    from agy_swarms.conductor_codex_batch import dispatch_codex_review_batch

    nodes = {
        "rev_a": NodeSpec(id="rev_a", role="reviewer", objective="review A"),
        "rev_b": NodeSpec(id="rev_b", role="reviewer", objective="review B"),
    }

    assert dispatch_codex_review_batch is not None
    assert can_codex_review_batch(
        batch=["rev_a", "rev_b"],
        checkpoint=None,
        nodes_by_id=nodes,
        reviewer="codex",
        closer="codex",
    )
    assert not can_codex_review_batch(
        batch=["rev_a"],
        checkpoint=None,
        nodes_by_id=nodes,
        reviewer="codex",
        closer="codex",
    )


def test_conductor_budget_helpers_are_importable():
    from agy_swarms.conductor_budget import (
        actual_from_envelope,
        add_consumed,
        billable_tokens,
        commit_actual_usage,
        dims_from_consumed,
    )

    assert billable_tokens({"output": 2, "thinking": 3, "input": 99}) == 5
    assert dims_from_consumed({"tokens": "4", "usd": "1.25"}) == Dims(tokens=4, usd=1.25)
    assert add_consumed({"tokens": 1, "usd": 0.5}, Dims(tokens=2, usd=0.25)) == {
        "tokens": 3,
        "usd": 0.75,
    }
    envelope = _env("succeeded", out=7, think=5, cost=0.75)
    actual = actual_from_envelope(envelope)
    assert actual == Dims(tokens=12, usd=0.75)

    class FakeLedger:
        def __init__(self):
            self.commits = []

        def commit(self, epoch_seq, node_id, actual, *, accounting):
            self.commits.append((epoch_seq, node_id, actual, accounting))

    ledger = FakeLedger()
    runtime = SimpleNamespace(budget_consumed={"tokens": 3, "usd": 0.25})

    returned_actual = commit_actual_usage(
        ledger=ledger,
        epoch_seq=9,
        node_id="n",
        runtime=runtime,
        actual=actual,
        accounting="exact",
    )

    assert returned_actual == actual
    assert ledger.commits == [(9, "n", Dims(tokens=12, usd=0.75), "exact")]
    assert runtime.budget_consumed == {"tokens": 15, "usd": 1.0}


def test_drift_helper_is_importable():
    from agy_swarms.conductor_drift import collect_drift_records, report_drift_records

    assert collect_drift_records(None, Lockfile(), allow_drift=True) == []
    assert collect_drift_records(Lockfile(), None, allow_drift=True) == []

    locked = Lockfile(model_pins={"default": "flash-A"})
    actual = Lockfile(model_pins={"default": "flash-B"})
    records = collect_drift_records(locked, actual, allow_drift=True)

    assert records == [
        DriftRecord(category="model_pins", key="default", expected="flash-A", actual="flash-B")
    ]
    copied = report_drift_records(records)
    assert copied == records
    assert copied is not records


def test_adapter_crash_envelope_helper_is_importable():
    from agy_swarms.conductor_adapters import adapter_crash_envelope

    node = NodeSpec(id="n", role="worker", objective="n")
    envelope = adapter_crash_envelope(node, ValueError("boom"))

    assert envelope.status == "failed"
    assert envelope.error_class == ErrorClass.UNKNOWN
    assert envelope.artifact == {"crash": "ValueError"}
    assert "boom" in envelope.stdout_ref


def test_review_dispatch_helper_is_importable():
    from agy_swarms.conductor_review import run_review_node

    node = NodeSpec(id="r", role="reviewer", objective="review")
    envelope = run_review_node(
        node,
        active_adapter=ScriptedAdapter({"r": _env(artifact={"review": True})}),
        attempt=1,
        reservation_id="res-1",
        adapter_name="agy",
        telemetry_path=None,
    )

    assert envelope.status == "succeeded"
    assert envelope.artifact == {"review": True}


def test_conductor_dispatch_helper_is_importable():
    from agy_swarms.conductor_dispatch import RunNodeAttemptDeps, run_node_attempt

    child = _env(artifact={"value": 1})
    node = NodeSpec(
        id="merge",
        role="reducer",
        objective="merge child artifacts",
        dependencies=["child"],
        reducer=Reducer(kind="concat"),
    )
    node.idempotency_key = "key-merge"
    runtime = NodeRuntimeState(node_id="merge", attempt=1)
    blockers: list[tuple[str, str, str]] = []
    events: list[dict[str, object]] = []

    deps = RunNodeAttemptDeps(
        adapter=ScriptedAdapter({}),
        fallback_adapter=None,
        graph=TaskGraph(nodes=[node]),
        ledger=SimpleNamespace(entries={}, available=Dims(tokens=100)),
        epoch=_epoch(),
        command_runner=lambda command: None,
        reducer_registry={},
        results={"child": child},
        reviewer="agy",
        closer="agy",
        review_telemetry_path=None,
        add_blocker=lambda node_id, reason, detail: blockers.append((node_id, reason, detail)),
        record_event=events.append,
    )

    envelope = run_node_attempt(node, runtime, reservation_id="res-merge", deps=deps)

    assert envelope.status == "succeeded"
    assert envelope.error_class == ErrorClass.NONE
    assert envelope.artifact == {"items": [{"value": 1}]}
    assert envelope.token_usage == {
        "input": 0,
        "thinking": 0,
        "output": 0,
        "cached": 0,
        "accounting": "exact",
    }
    assert blockers == []
    assert events == []


def test_fallback_helper_is_importable():
    from agy_swarms.conductor_fallback import execute_fallback_run, next_review_fallback_adapter

    assert next_review_fallback_adapter("agy") == "codex"
    assert next_review_fallback_adapter("codex") == "off"
    assert next_review_fallback_adapter("claude") is None

    node = NodeSpec(id="n", role="worker", objective="n")
    runtime = NodeRuntimeState(node_id="n")
    envelope = _env(
        "failed",
        ErrorClass.AUTH,
        out=11,
        think=7,
        cost=0.5,
        artifact={"fallback": True},
    )

    def run_fallback(node_arg, runtime_arg, reservation_id):
        assert node_arg is node
        assert runtime_arg is runtime
        assert reservation_id == "res-fallback"
        return envelope

    def stamp(envelope_arg, node_arg, runtime_arg):
        envelope_arg.node_id = node_arg.id
        envelope_arg.idempotency_key = "key-n"
        envelope_arg.attempt = runtime_arg.attempt
        envelope_arg.reservation_id = runtime_arg.reservation_id

    result = execute_fallback_run(
        node=node,
        runtime=runtime,
        admission=SimpleNamespace(reservation_id="res-fallback"),
        run=run_fallback,
        stamp=stamp,
    )

    assert result.envelope is envelope
    assert result.actual == Dims(tokens=18, usd=0.5)
    assert runtime.attempt == 1
    assert runtime.reservation_id == "res-fallback"
    assert runtime.error_class == ErrorClass.AUTH
    assert envelope.node_id == "n"
    assert envelope.attempt == 1


def test_review_budget_helper_is_importable():
    from agy_swarms.conductor_review_budget import review_budget_events

    worker_events, worker_closer = review_budget_events(
        node_id="w", role="worker", spent_tokens=5000, closer="agy"
    )
    assert worker_events == []
    assert worker_closer == "agy"

    closer_events, closer_after = review_budget_events(
        node_id="c", role="closer", spent_tokens=1001, closer="agy"
    )
    assert closer_after == "agy"
    assert [event["type"] for event in closer_events] == ["review_budget_alert"]
    assert closer_events[0]["node_id"] == "c"
    assert closer_events[0]["spent_tokens"] == 1001

    reviewer_events, reviewer_closer = review_budget_events(
        node_id="r", role="reviewer", spent_tokens=1500, closer="agy"
    )
    assert reviewer_closer == "codex"
    assert [event["type"] for event in reviewer_events] == [
        "review_budget_alert",
        "review_auto_triage",
    ]
    assert reviewer_events[1]["previous_closer"] == "agy"
    assert reviewer_events[1]["new_closer"] == "codex"


def test_checkpointing_helper_is_importable():
    from agy_swarms.conductor_checkpointing import (
        adopt_cached_runtime,
        build_node_journal_entry,
        build_pipeline_journal_entry,
        cached_success_envelope,
        cached_terminal_envelope,
        persisted_runtime_matches,
        pipeline_stage_key,
    )

    assert persisted_runtime_matches("key-a", "key-a")
    assert not persisted_runtime_matches("key-a", "key-b")
    assert not persisted_runtime_matches(None, "key-a")

    epoch = _epoch("E1", 7)
    node = NodeSpec(id="n", role="worker", objective="n")
    node.idempotency_key = "key-n"
    runtime = NodeRuntimeState(
        node_id="n",
        status=NodeStatus.FAILED,
        attempt=3,
        remaining_schema_retries=0,
        budget_consumed={"tokens": 42, "usd": 0.25},
    )
    envelope = _env("failed", ErrorClass.AUTH, artifact={"why": "auth"})

    entry = build_node_journal_entry("n", node, runtime, envelope, epoch)
    assert entry.node_id == "n"
    assert entry.idempotency_key == "key-n"
    assert entry.epoch_id == "E1"
    assert entry.epoch_seq == 7
    assert entry.status == "failed"
    assert entry.attempt == 3
    assert entry.remaining_schema_retries == 0
    assert entry.budget_consumed == {"tokens": 42, "usd": 0.25}
    assert cached_terminal_envelope(entry) is envelope
    assert cached_success_envelope(entry) is None

    fresh_runtime = NodeRuntimeState(node_id="n")
    adopt_cached_runtime(fresh_runtime, entry)
    assert fresh_runtime.status == NodeStatus.FAILED
    assert fresh_runtime.attempt == 3
    assert fresh_runtime.remaining_schema_retries == 0
    assert fresh_runtime.budget_consumed == {"tokens": 42, "usd": 0.25}
    assert fresh_runtime.error_class == ErrorClass.AUTH

    succeeded = _env("succeeded", artifact={"stage": "done"})
    pipeline_key = pipeline_stage_key("P", 1, 2, 3, "E1")
    assert pipeline_key != pipeline_stage_key("P", 1, 2, 3, "E2")
    pipeline_entry = build_pipeline_journal_entry(pipeline_key, succeeded, epoch)
    assert pipeline_entry.node_id == succeeded.node_id
    assert pipeline_entry.idempotency_key == pipeline_key
    assert pipeline_entry.status == "succeeded"
    assert pipeline_entry.attempt == 1
    assert cached_success_envelope(pipeline_entry) is succeeded


def test_pipeline_helper_is_importable():
    from agy_swarms.conductor_pipeline import run_pipeline_item

    cached_first_stage = _env("succeeded", artifact={"seen": ["cached"], "item": "i0"})
    journaled: list[tuple[str, ResultEnvelope]] = []
    fresh_calls: list[dict[str, object]] = []

    def key_for(pipeline_id, index, stage_idx, n_stages):
        return f"{pipeline_id}:{index}:{stage_idx}:{n_stages}"

    def cache_lookup(key):
        if key == "P:0:0:2":
            return cached_first_stage
        return None

    def first_stage(_item, _prev):
        raise AssertionError("cached stage should not execute")

    def second_stage(item, prev):
        fresh_calls.append({"item": item, "prev": prev})
        return _env("succeeded", artifact={"seen": [*prev["seen"], "fresh"], "item": item})

    result = run_pipeline_item(
        pipeline_id="P",
        index=0,
        item="i0",
        stages=[first_stage, second_stage],
        pipeline_key=key_for,
        cache_lookup=cache_lookup,
        journal=lambda key, envelope: journaled.append((key, envelope)),
        classify_envelope=classify,
    )

    assert result.status == "succeeded"
    assert result.stages_completed == 2
    assert result.envelope.artifact == {"seen": ["cached", "fresh"], "item": "i0"}
    assert fresh_calls == [{"item": "i0", "prev": {"seen": ["cached"], "item": "i0"}}]
    assert journaled == [("P:0:1:2", result.envelope)]
