"""D5.6 Integrated head-to-head report."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "HeadToHeadReport",
    "ParetoPoint",
    "Phase5GateResult",
    "Phase5Status",
    "build_head_to_head_report",
]


class Phase5Status(StrEnum):
    """Overall Phase 5 candidate status."""

    CANDIDATE = "PHASE-5 CANDIDATE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Phase5GateResult:
    """One metric gate's pass/fail result."""

    gate_id: str
    status: str  # "passed" or "failed"
    blocking: bool  # True if this gate can block Phase-5
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParetoPoint:
    """Quality-cost Pareto point for one run."""

    run_id: str
    quality_ratio: float
    billable_tokens: int


@dataclass(frozen=True)
class HeadToHeadReport:
    """Integrated Phase-5 head-to-head report."""

    status: Phase5Status
    gates: tuple[Phase5GateResult, ...]
    pareto_points: tuple[ParetoPoint, ...]
    reported_only: dict[str, Any]
    provenance: dict[str, Any]


def build_head_to_head_report(
    *,
    m1_status: str,
    m1_detail: dict[str, Any] | None = None,
    m2_status: str,
    m2_detail: dict[str, Any] | None = None,
    m3_status: str,
    m3_detail: dict[str, Any] | None = None,
    cache_status: str | None = None,
    cache_detail: dict[str, Any] | None = None,
    pareto_points: tuple[ParetoPoint, ...] = (),
    reported_only: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> HeadToHeadReport:
    """Build an integrated head-to-head report from individual gate results.

    Phase-5 CANDIDATE requires all three blocking gates (M1, M2, M3) to pass.
    Cache stability is recorded but non-blocking (soft gate).
    Reported-only comparands cannot flip a failing gate to passing.
    """
    gates = (
        Phase5GateResult(
            gate_id="M1",
            status=m1_status,
            blocking=True,
            detail=m1_detail or {},
        ),
        Phase5GateResult(
            gate_id="M2",
            status=m2_status,
            blocking=True,
            detail=m2_detail or {},
        ),
        Phase5GateResult(
            gate_id="M3",
            status=m3_status,
            blocking=True,
            detail=m3_detail or {},
        ),
    )

    # Cache is a soft (non-blocking) gate.
    if cache_status is not None:
        gates = gates + (
            Phase5GateResult(
                gate_id="cache",
                status=cache_status,
                blocking=False,
                detail=cache_detail or {},
            ),
        )

    # Phase-5 CANDIDATE only if ALL blocking gates pass.
    blocking_failures = [g for g in gates if g.blocking and g.status != "passed"]
    overall = Phase5Status.CANDIDATE if not blocking_failures else Phase5Status.BLOCKED

    return HeadToHeadReport(
        status=overall,
        gates=gates,
        pareto_points=pareto_points,
        reported_only=reported_only or {},
        provenance=provenance or {},
    )
