"""ADR-001 Phase-2 profiling helpers for the Python-vs-Rust go/kill decision."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .adapters.scripted import CannedResult, ScriptedAdapter
from .budget import Dims
from .conductor import Conductor
from .types import Caps, Epoch, NodeSpec, Reducer, ResultEnvelope, TaskGraph

__all__ = [
    "ConductorProfile",
    "PortDecision",
    "compute_reference_task_sha",
    "decide_rust_port",
    "profile_conductor",
]


@dataclass(frozen=True)
class ConductorProfile:
    """Measured inputs for ADR-001's Phase-2 port trigger."""

    reference_task_sha: str
    worker_count: int
    wall_clock_s: float
    model_wait_s: float
    conductor_overhead_s: float
    conductor_overhead_pct: float
    useful_fanout_ceiling: int
    fanout_binding: str


@dataclass(frozen=True)
class PortDecision:
    """Go/kill verdict for the optional Rust port."""

    rust_port_triggered: bool
    status: str
    reasons: tuple[str, ...]


class _MeasuredAdapter:
    """Scripted adapter wrapper that measures adapter/model wait separately."""

    accounting = "exact"
    name = "measured-scripted"

    def __init__(self, inner: ScriptedAdapter, *, wait_s: float) -> None:
        self.inner = inner
        self.wait_s = wait_s
        self.model_wait_s = 0.0

    def covers(self, required: Iterable[str]) -> bool:
        return self.inner.covers(required)

    def run(
        self, node: NodeSpec, *, attempt: int = 0, reservation_id: str | None = None
    ) -> ResultEnvelope:
        started = time.perf_counter()
        if self.wait_s > 0:
            time.sleep(self.wait_s)
        self.model_wait_s += time.perf_counter() - started
        return self.inner.run(node, attempt=attempt, reservation_id=reservation_id)


def compute_reference_task_sha(path: Path) -> str:
    """Return the pinned SHA-256 over the reference task's raw bytes."""
    content = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def decide_rust_port(
    profile: ConductorProfile,
    *,
    overhead_threshold_pct: float = 20.0,
    min_gil_fanout: int = 16,
) -> PortDecision:
    """Apply ADR-001's exact trigger rule to a measured profile."""
    reasons: list[str] = []
    triggered = False
    if profile.conductor_overhead_pct > overhead_threshold_pct:
        triggered = True
        reasons.append(
            "conductor_overhead_pct "
            f"{profile.conductor_overhead_pct:.2f} > {overhead_threshold_pct:.2f}"
        )

    if profile.fanout_binding == "gil":
        if profile.useful_fanout_ceiling < min_gil_fanout:
            triggered = True
            reasons.append(
                f"gil_bound_fanout_ceiling {profile.useful_fanout_ceiling} < {min_gil_fanout}"
            )
        else:
            reasons.append(
                f"gil_bound_fanout_ceiling {profile.useful_fanout_ceiling} >= {min_gil_fanout}"
            )

    if not triggered:
        reasons.append(
            "conductor_overhead_pct "
            f"{profile.conductor_overhead_pct:.2f} <= {overhead_threshold_pct:.2f}"
        )
        if profile.fanout_binding == "gil":
            reasons.append(
                f"gil_bound_fanout_ceiling {profile.useful_fanout_ceiling} >= {min_gil_fanout}"
            )
        elif profile.useful_fanout_ceiling < min_gil_fanout:
            reasons.append(f"fanout ceiling is {profile.fanout_binding}-bound, not GIL-bound")
        else:
            reasons.append(
                f"useful_fanout_ceiling {profile.useful_fanout_ceiling} >= {min_gil_fanout}"
            )

    return PortDecision(
        rust_port_triggered=triggered,
        status="trigger_rust_port" if triggered else "accepted_as_no_port",
        reasons=tuple(reasons),
    )


def profile_conductor(
    reference_task_path: Path,
    *,
    worker_count: int = 16,
    model_wait_s: float = 0.005,
    fanout_probe_delay_s: float = 0.002,
) -> ConductorProfile:
    """Measure conductor bookkeeping overhead on a reference fan-out fixture."""
    graph, adapter = _profile_fixture(worker_count, model_wait_s=model_wait_s)
    started = time.perf_counter()
    report = Conductor(
        graph,
        adapter,
        limit=Dims(tokens=1_000_000, usd=1000.0),
        epoch=Epoch(epoch_seq=1, epoch_id="adr001-profile"),
        cap=worker_count,
    ).run()
    wall_clock_s = time.perf_counter() - started
    if str(report.status) != "succeeded":
        raise RuntimeError(f"profile fixture failed: {report.status}")

    overhead_s = max(0.0, wall_clock_s - adapter.model_wait_s)
    ceiling = _measure_useful_fanout_ceiling(delay_s=fanout_probe_delay_s)
    return ConductorProfile(
        reference_task_sha=compute_reference_task_sha(reference_task_path),
        worker_count=worker_count,
        wall_clock_s=wall_clock_s,
        model_wait_s=adapter.model_wait_s,
        conductor_overhead_s=overhead_s,
        conductor_overhead_pct=(overhead_s / wall_clock_s * 100.0) if wall_clock_s > 0 else 0.0,
        useful_fanout_ceiling=ceiling,
        fanout_binding="not_gil_bound" if ceiling >= 16 else "gil",
    )


def _profile_fixture(
    worker_count: int, *, model_wait_s: float
) -> tuple[TaskGraph, _MeasuredAdapter]:
    root = NodeSpec(
        id="root",
        role="worker",
        objective="read pinned reference task",
        outputs=["source"],
        caps=Caps(max_output_tokens=100, max_thinking_tokens=10),
    )
    workers = [
        NodeSpec(
            id=f"w{i:02d}",
            role="worker",
            objective=f"analyze reference shard {i}",
            dependencies=["root"],
            caps=Caps(max_output_tokens=100, max_thinking_tokens=10),
        )
        for i in range(worker_count)
    ]
    reducer = NodeSpec(
        id="reduce",
        role="reducer",
        objective="merge shard reports",
        dependencies=[worker.id for worker in workers],
        reducer=Reducer(kind="concat"),
        caps=Caps(max_output_tokens=100, max_thinking_tokens=0),
    )
    transcript = {
        "root": CannedResult(artifact={"source": "benchmarks/reference_task.md"}),
        **{
            worker.id: CannedResult(artifact={"worker": worker.id, "ok": True})
            for worker in workers
        },
    }
    graph = TaskGraph(
        nodes=[root, *workers, reducer],
        edges=[("root", worker.id) for worker in workers]
        + [(worker.id, "reduce") for worker in workers],
        seed=1,
    )
    return graph, _MeasuredAdapter(ScriptedAdapter(transcript), wait_s=model_wait_s)


def _measure_useful_fanout_ceiling(
    *, delay_s: float, max_fanout: int = 32, tolerance: float = 2.5
) -> int:
    async def _once(count: int) -> float:
        started = time.perf_counter()
        await asyncio.gather(*(asyncio.sleep(delay_s) for _ in range(count)))
        return time.perf_counter() - started

    baseline = asyncio.run(_once(1))
    ceiling = 1
    for fanout in (2, 4, 8, 16, 32):
        if fanout > max_fanout:
            break
        elapsed = asyncio.run(_once(fanout))
        if elapsed <= max(baseline * tolerance, delay_s + 0.02):
            ceiling = fanout
    return ceiling
