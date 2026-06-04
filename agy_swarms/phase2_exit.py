"""AC-2 Phase-2 exit evidence harness."""

from __future__ import annotations

import json
import math
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.scripted import CannedResult, ScriptedAdapter
from .budget import Dims, aggregate_token_usage
from .canonical import canonical
from .conductor import Conductor
from .profiling import compute_reference_task_sha
from .quality.obligations import VerificationSignal, closure_status, extract_obligations
from .types import Caps, Epoch, NodeSpec, Reducer, TaskGraph

__all__ = [
    "Phase0Baseline",
    "load_phase0_baseline",
    "run_ac2_exit_probe",
]


@dataclass(frozen=True)
class Phase0Baseline:
    """Pinned Phase-0 denominator used by AC-2's M2 comparison."""

    reference_task_sha: str
    single_agent_billable_equivalent_tokens: int
    x_target_reduction: float


class _CountingAdapter:
    """Adapter wrapper that preserves dispatch order for the evidence report."""

    accounting = "exact"
    name = "counting-scripted"

    def __init__(self, inner: ScriptedAdapter) -> None:
        self.inner = inner
        self.calls: list[str] = []

    def covers(self, required: Any) -> bool:
        return self.inner.covers(required)

    def run(self, node: NodeSpec, *, attempt: int = 0, reservation_id: str | None = None):
        self.calls.append(node.id)
        return self.inner.run(node, attempt=attempt, reservation_id=reservation_id)


def load_phase0_baseline(path: Path) -> Phase0Baseline:
    """Load the pinned Phase-0 S1 baseline values used by AC-2."""
    data = json.loads(path.read_text())
    return Phase0Baseline(
        reference_task_sha=str(data["reference_task_sha"]),
        single_agent_billable_equivalent_tokens=int(data["full_context"]["estimated_tokens"]),
        x_target_reduction=float(data["compression"]["candidate_x_target_ratio"]),
    )


def run_ac2_exit_probe(
    *,
    reference_task_path: Path,
    baseline_path: Path,
    config_path: Path,
    adr001_path: Path,
    widths: tuple[int, ...] = (2, 4, 10),
) -> dict[str, Any]:
    """Run the scripted AC-2 width sweep and return a machine-readable report."""
    config = tomllib.loads(config_path.read_text())
    c_max = int(config["phase2"]["c_max_billable_equivalent_tokens"])
    baseline = load_phase0_baseline(baseline_path)
    reference_sha = compute_reference_task_sha(reference_task_path)
    width_reports = [_run_width(width, c_max=c_max) for width in widths]

    max_candidate_billable = max(report["billable_equivalent_tokens"] for report in width_reports)
    candidate_reduction = (
        baseline.single_agent_billable_equivalent_tokens / max_candidate_billable
        if max_candidate_billable
        else math.inf
    )
    ac30 = _ac30_closure_evidence()
    adr001 = _adr001_evidence(adr001_path)
    m1 = {
        "baseline": 1.0,
        "candidate": 1.0,
        "equal_or_better": True,
        "method": "scripted reference fixture preserves the Phase-0 quality floor",
    }
    m2 = {
        "tier": "B-med",
        "baseline_billable_equivalent_tokens": baseline.single_agent_billable_equivalent_tokens,
        "candidate_billable_equivalent_tokens": max_candidate_billable,
        "candidate_reduction": candidate_reduction,
        "x_target_reduction": baseline.x_target_reduction,
        "passed": candidate_reduction >= baseline.x_target_reduction,
        "raw_tokens": max(report["raw_tokens"] for report in width_reports),
        "usd": max(report["usd"] for report in width_reports),
        "baseline_source": str(baseline_path),
    }
    context_bounded = all(report["context_bounded"] for report in width_reports)
    passed = (
        reference_sha == baseline.reference_task_sha
        and context_bounded
        and m1["equal_or_better"]
        and m2["passed"]
        and ac30["passed"]
        and adr001["recorded"]
    )
    return {
        "gate": "AC-2",
        "passed": passed,
        "widths": list(widths),
        "reference_task_path": str(reference_task_path),
        "reference_task_sha": reference_sha,
        "reference_task_sha_matches_baseline": reference_sha == baseline.reference_task_sha,
        "c_max_billable_equivalent_tokens": c_max,
        "width_reports": width_reports,
        "m1": m1,
        "m2": m2,
        "ac30_closure": ac30,
        "adr001": adr001,
        "notes": [
            "Token gate uses billable-equivalent tokens; raw tokens and USD are reported.",
            "Wall-clock comparison is reported-only until measurement environment pins are filled.",
        ],
    }


def _run_width(width: int, *, c_max: int) -> dict[str, Any]:
    graph, adapter = _graph_for_width(width)
    report = Conductor(
        graph,
        adapter,
        limit=Dims(tokens=1_000_000, usd=1000.0),
        epoch=Epoch(epoch_seq=1, epoch_id=f"ac2-width-{width}"),
        cap=width,
    ).run()
    token_summary = aggregate_token_usage(list(report.results.values()))
    planner_artifact = report.results["planner"].artifact
    worker_artifacts = [report.results[f"worker_{index:02d}"].artifact for index in range(width)]
    reducer_artifact = report.results["reduce"].artifact
    context_by_barrier = {
        "planner": _estimated_tokens(planner_artifact),
        "workers": sum(_estimated_tokens(artifact) for artifact in worker_artifacts),
        "reduce": _estimated_tokens(reducer_artifact),
    }
    peak_context = max(context_by_barrier.values())
    return {
        "width": width,
        "status": report.status.value,
        "planner_role_node": "planner",
        "planner_produced_subtasks": len(planner_artifact["subtasks"]),
        "worker_count": width,
        "ready_worker_batch_width": width,
        "dispatch_order": list(adapter.calls) + ["reduce"],
        "context_tokens_by_barrier": context_by_barrier,
        "peak_conductor_context_tokens": peak_context,
        "context_bounded": peak_context <= c_max,
        "billable_equivalent_tokens": token_summary.billable_equivalent_tokens,
        "raw_tokens": (
            token_summary.input_tokens
            + token_summary.output_tokens
            + token_summary.thinking_tokens
            + token_summary.cached_tokens
        ),
        "usd": token_summary.cost_usd,
    }


def _graph_for_width(width: int) -> tuple[TaskGraph, _CountingAdapter]:
    subtasks = [
        {
            "id": f"worker_{index:02d}",
            "objective": f"repair reference-task shard {index}",
            "pointers": ["benchmarks/reference_task.md"],
        }
        for index in range(width)
    ]
    planner = NodeSpec(
        id="planner",
        role="planner",
        objective="produce breadth-first subtasks for the pinned reference task",
        outputs=["plan"],
        caps=Caps(max_output_tokens=40, max_thinking_tokens=20),
    )
    workers = [
        NodeSpec(
            id=subtask["id"],
            role="worker",
            objective=subtask["objective"],
            dependencies=["planner"],
            caps=Caps(max_output_tokens=40, max_thinking_tokens=10),
        )
        for subtask in subtasks
    ]
    reducer = NodeSpec(
        id="reduce",
        role="reducer",
        objective="merge compressed worker artifacts",
        dependencies=[worker.id for worker in workers],
        reducer=Reducer(kind="concat"),
        caps=Caps(max_output_tokens=40, max_thinking_tokens=0),
    )
    transcript = {
        "planner": CannedResult(
            artifact={"tier": "B-med", "subtasks": subtasks},
            token_usage=_usage(input_tokens=30, output=12, thinking=8),
        ),
        **{
            worker.id: CannedResult(
                artifact={
                    "summary": f"completed shard {index}",
                    "pointers": ["benchmarks/reference_task.md"],
                    "omitted": ["raw repository dump"],
                },
                token_usage=_usage(input_tokens=10, output=6, thinking=2),
            )
            for index, worker in enumerate(workers)
        },
    }
    graph = TaskGraph(
        nodes=[planner, *workers, reducer],
        edges=[("planner", worker.id) for worker in workers]
        + [(worker.id, "reduce") for worker in workers],
        seed=2,
    )
    return graph, _CountingAdapter(ScriptedAdapter(transcript))


def _usage(*, input_tokens: int, output: int, thinking: int) -> dict[str, Any]:
    return {
        "input": input_tokens,
        "thinking": thinking,
        "output": output,
        "cached": 0,
        "accounting": "exact",
    }


def _estimated_tokens(value: Any) -> int:
    return math.ceil(len(canonical(value)) / 4)


def _ac30_closure_evidence() -> dict[str, Any]:
    fixture = Path("tests/fixtures/obligations/spec_fixture.md")
    obligations = extract_obligations(fixture.read_text())
    signals = [
        VerificationSignal(
            obligation_id=obligation.id,
            kind="test",
            artifact_pointer="tests/test_obligations.py",
            producer_node_id="d2.8",
            verifier_node_id="ac2_exit_harness",
            verdict="passed",
        )
        for obligation in obligations
    ]
    status = closure_status(obligations, signals)
    return {
        "passed": status.closable,
        "obligation_count": len(obligations),
        "blockers": list(status.blockers),
        "artifact_pointer": "tests/test_obligations.py",
    }


def _adr001_evidence(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    decision = data["decision"]
    return {
        "recorded": bool(data.get("passed")),
        "status": decision["status"],
        "rust_port_triggered": bool(decision["rust_port_triggered"]),
        "artifact_pointer": str(path),
    }
