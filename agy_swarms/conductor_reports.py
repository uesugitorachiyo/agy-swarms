"""Report shapes produced by the conductor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import DriftRecord, NodeStatus, ResultEnvelope, RunStatus


@dataclass
class RunReport:
    """A run's terminal summary (§D.7-adjacent). Byte-stable over the scripted substrate."""

    status: RunStatus
    results: dict[str, ResultEnvelope]
    states: dict[str, NodeStatus]
    blockers: list[dict[str, str]]
    spent_tokens: int
    spent_usd: float
    drift_records: list[DriftRecord] = field(default_factory=list)


@dataclass
class PipelineItemResult:
    """One pipeline item's outcome (FR-7 per-item cadence; FR-5.1-analog isolation)."""

    item: Any
    status: str
    envelope: ResultEnvelope | None
    stages_completed: int
    blocker: dict[str, str] | None = None
