"""Integrated conductor failure paths across crash containment, fallback, budget, resume."""

from agy_swarms.adapters.scripted import CannedResult, ScriptedAdapter
from agy_swarms.budget import Dims
from agy_swarms.checkpoint import Checkpoint
from agy_swarms.conductor import Conductor
from agy_swarms.types import (
    Caps,
    Epoch,
    ErrorClass,
    NodeSpec,
    NodeStatus,
    ResultEnvelope,
    RunStatus,
    TaskGraph,
)

_LIMIT = Dims(tokens=1_000_000, usd=1000.0)


def _epoch() -> Epoch:
    return Epoch(epoch_seq=1, epoch_id="integration")


def _usage(*, output: int = 0, thinking: int = 0) -> dict[str, object]:
    return {
        "input": 0,
        "thinking": thinking,
        "output": output,
        "cached": 0,
        "accounting": "exact",
    }


class CrashThenScripted:
    """Adapter that raises for planted node ids and returns envelopes for the rest."""

    accounting = "exact"
    name = "primary"

    def __init__(self, *, crash_ids: set[str], transcript: dict[str, CannedResult] | None = None):
        self.crash_ids = set(crash_ids)
        self.transcript = transcript or {}
        self.calls: list[str] = []

    def covers(self, required: object) -> bool:
        return True

    def run(self, node: NodeSpec, *, attempt: int = 0, reservation_id: str | None = None):
        self.calls.append(node.id)
        if node.id in self.crash_ids:
            raise RuntimeError(f"crash:{node.id}")
        canned = self.transcript.get(node.id, CannedResult(artifact={"node": node.id}))
        usage = dict(canned.token_usage or _usage())
        usage.setdefault("accounting", "exact")
        return ResultEnvelope(
            node_id=node.id,
            idempotency_key=node.idempotency_key,
            status=canned.status,
            attempt=attempt,
            adapter=self.name,
            reservation_id=reservation_id,
            error_class=canned.error_class,
            artifact=dict(canned.artifact),
            token_usage=usage,
            cost_usd=canned.cost_usd,
        )


class CountingFallback(ScriptedAdapter):
    """Scripted fallback with a distinct adapter name and dispatch log."""

    def __init__(self, transcript: dict[str, CannedResult]):
        super().__init__(transcript, capabilities={"py"})
        self.name = "fallback"
        self.calls: list[str] = []

    def run(self, node: NodeSpec, *, attempt: int = 0, reservation_id: str | None = None):
        self.calls.append(node.id)
        return super().run(node, attempt=attempt, reservation_id=reservation_id)


def test_adapter_crash_fallback_result_checkpoints_and_resumes_without_redispatch(tmp_path):
    path = tmp_path / "ck.db"
    node = NodeSpec(
        id="n",
        role="worker",
        objective="work",
        required_capabilities=["py"],
        caps=Caps(max_output_tokens=100),
    )
    graph = TaskGraph(nodes=[node])
    primary = CrashThenScripted(crash_ids={"n"})
    fallback = CountingFallback(
        {"n": CannedResult(artifact={"rescued": True}, token_usage=_usage(output=40))}
    )

    with Checkpoint(path, _epoch()) as ck:
        cond = Conductor(
            graph,
            primary,
            limit=_LIMIT,
            epoch=_epoch(),
            checkpoint=ck,
            fallback_adapter=fallback,
        )
        report = cond.run()

    assert report.status == RunStatus.SUCCEEDED
    assert report.results["n"].artifact == {"rescued": True}
    assert report.results["n"].adapter == "fallback"
    assert primary.calls == ["n"]
    assert fallback.calls == ["n"]
    assert cond.runtime["n"].budget_consumed["tokens"] == 40
    assert report.spent_tokens == 40
    assert [
        event
        for event in cond.events
        if event["type"] == "model_switch" and event["node_id"] == "n"
    ]

    resumed_primary = CrashThenScripted(crash_ids={"n"})
    resumed_fallback = CountingFallback(
        {"n": CannedResult(artifact={"should_not_run": True}, token_usage=_usage(output=99))}
    )
    resumed_node = NodeSpec(
        id="n",
        role="worker",
        objective="work",
        required_capabilities=["py"],
        caps=Caps(max_output_tokens=100),
    )
    with Checkpoint(path, _epoch()) as ck2:
        resumed = Conductor(
            TaskGraph(nodes=[resumed_node]),
            resumed_primary,
            limit=_LIMIT,
            epoch=_epoch(),
            checkpoint=ck2,
            fallback_adapter=resumed_fallback,
        )
        resumed_report = resumed.run()

    assert resumed_report.status == RunStatus.SUCCEEDED
    assert resumed_report.results["n"].artifact == {"rescued": True}
    assert resumed_primary.calls == []
    assert resumed_fallback.calls == []
    assert resumed.runtime["n"].budget_consumed["tokens"] == 40
    assert resumed.ledger.spent.tokens == 0


def test_adapter_crash_without_fallback_fails_node_skips_dependent_and_keeps_sibling():
    root = NodeSpec(id="root", role="worker", objective="root")
    crashy = NodeSpec(id="crashy", role="worker", objective="crashy", dependencies=["root"])
    sibling = NodeSpec(id="sibling", role="worker", objective="sibling", dependencies=["root"])
    dependent = NodeSpec(
        id="dependent",
        role="worker",
        objective="dependent",
        dependencies=["crashy"],
    )
    adapter = CrashThenScripted(
        crash_ids={"crashy"},
        transcript={
            "root": CannedResult(artifact={"root": True}),
            "sibling": CannedResult(artifact={"sibling": True}),
            "dependent": CannedResult(artifact={"dependent": True}),
        },
    )
    report = Conductor(
        TaskGraph(nodes=[root, crashy, sibling, dependent]),
        adapter,
        limit=_LIMIT,
        epoch=_epoch(),
        cap=4,
    ).run()

    assert report.status == RunStatus.FAILED
    assert report.states["crashy"] == NodeStatus.FAILED
    assert report.results["crashy"].error_class == ErrorClass.UNKNOWN
    assert report.results["crashy"].artifact == {"crash": "RuntimeError"}
    assert report.states["sibling"] == NodeStatus.SUCCEEDED
    assert report.results["sibling"].artifact == {"sibling": True}
    assert report.states["dependent"] == NodeStatus.SKIPPED
    assert "dependent" not in adapter.calls
    assert any(blocker["id"] == "dependent" for blocker in report.blockers)
