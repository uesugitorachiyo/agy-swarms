"""D5.2 M1 quality scoring and confidence gate."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "M1GateStatus",
    "QualityGateIncomplete",
    "QualityJudgeConfig",
    "QualityReport",
    "QualityRunScore",
    "build_quality_report",
]

# Minimum runs required (bare point estimates are rejected).
MIN_RUNS: int = 2

# One-sided 95% t-distribution critical values by degrees of freedom.
# Used for the lower confidence bound: mean - t * (s / sqrt(n)).
_T_CRITICAL_95: dict[int, float] = {
    1: 6.314,
    2: 2.920,
    3: 2.353,
    4: 2.132,
    5: 2.015,
    6: 1.943,
    7: 1.895,
    8: 1.860,
    9: 1.833,
    10: 1.812,
    15: 1.753,
    20: 1.725,
    25: 1.708,
    30: 1.697,
    40: 1.684,
    60: 1.671,
    120: 1.658,
}

# Fallback for large df (z-score at 95%).
_Z_FALLBACK: float = 1.645


class M1GateStatus(StrEnum):
    """M1 quality gate status."""

    PASSED = "passed"
    FAILED = "failed"


class QualityGateIncomplete(ValueError):
    """Raised when M1 cannot gate because mandatory provenance is absent."""


@dataclass(frozen=True)
class QualityRunScore:
    """One judge-scored run with candidate and baseline scores."""

    run_id: str
    candidate_score: float
    baseline_score: float

    @property
    def ratio(self) -> float:
        """Candidate-to-baseline score ratio."""
        if self.baseline_score <= 0:
            raise QualityGateIncomplete(f"baseline_score must be positive for run {self.run_id!r}")
        return self.candidate_score / self.baseline_score


@dataclass(frozen=True)
class QualityJudgeConfig:
    """Judge configuration provenance for M1."""

    judge_model_id: str
    temperature: float
    rubric_hash: str
    blinding_map: dict[str, str]
    panel_composition: tuple[str, ...]
    artifact_pointers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityReport:
    """M1 gate report over K judge-scored runs."""

    status: M1GateStatus
    mean_ratio: float
    ci_lower_bound: float
    ci_upper_bound: float
    threshold: float
    num_runs: int
    judge_config: QualityJudgeConfig
    scores: tuple[QualityRunScore, ...]
    reported_only: dict[str, Any]


def build_quality_report(
    *,
    scores: tuple[QualityRunScore, ...],
    judge_config: QualityJudgeConfig,
    ci_lower_threshold: float,
    min_runs: int = MIN_RUNS,
) -> QualityReport:
    """Build a fail-closed M1 report for the candidate quality scores.

    Fail-closed on:
    - bare point estimate (< min_runs)
    - missing rubric hash
    - non-zero temperature
    - missing blinding map
    - CI lower bound below threshold
    """
    # --- fail-closed: judge provenance ---
    _validate_judge_config(judge_config)

    # --- fail-closed: reject bare point estimates ---
    if len(scores) < min_runs:
        raise QualityGateIncomplete(
            f"M1 requires >= {min_runs} runs; got {len(scores)} (bare point estimates are rejected)"
        )

    if ci_lower_threshold <= 0:
        raise QualityGateIncomplete("ci_lower_threshold must be positive")

    # --- compute ratios ---
    ratios = [s.ratio for s in scores]

    # --- compute CI ---
    mean_ratio = statistics.mean(ratios)
    if len(ratios) == 1:
        # Should not reach here due to min_runs check, but defensive.
        ci_lower = mean_ratio
        ci_upper = mean_ratio
    else:
        stdev = statistics.stdev(ratios)
        se = stdev / math.sqrt(len(ratios))
        t_crit = _t_critical(len(ratios) - 1)
        ci_lower = mean_ratio - t_crit * se
        ci_upper = mean_ratio + t_crit * se

    passed = ci_lower >= ci_lower_threshold

    return QualityReport(
        status=M1GateStatus.PASSED if passed else M1GateStatus.FAILED,
        mean_ratio=round(mean_ratio, 6),
        ci_lower_bound=round(ci_lower, 6),
        ci_upper_bound=round(ci_upper, 6),
        threshold=ci_lower_threshold,
        num_runs=len(scores),
        judge_config=judge_config,
        scores=scores,
        reported_only={
            "stdev": round(stdev, 6) if len(ratios) > 1 else 0.0,
            "margin": round(t_crit * se, 6) if len(ratios) > 1 else 0.0,
        },
    )


def _validate_judge_config(config: QualityJudgeConfig) -> None:
    """Fail closed on missing M1 provenance."""
    if not config.rubric_hash:
        raise QualityGateIncomplete("rubric_hash is required before M1 can gate")
    if config.temperature != 0:
        raise QualityGateIncomplete(
            f"temperature must be 0 for reproducible judging; got {config.temperature}"
        )
    if not config.blinding_map:
        raise QualityGateIncomplete("blinding_map is required before M1 can gate")
    if not config.judge_model_id:
        raise QualityGateIncomplete("judge_model_id is required before M1 can gate")
    if not config.panel_composition:
        raise QualityGateIncomplete("panel_composition is required before M1 can gate")


def _t_critical(df: int) -> float:
    """One-sided 95% t-distribution critical value for the given degrees of freedom."""
    if df in _T_CRITICAL_95:
        return _T_CRITICAL_95[df]
    # Interpolate: find the nearest lower and upper keys.
    keys = sorted(_T_CRITICAL_95.keys())
    if df < keys[0]:
        return _T_CRITICAL_95[keys[0]]
    if df > keys[-1]:
        return _Z_FALLBACK
    # Linear interpolation between bracketing keys.
    for i, k in enumerate(keys):
        if k > df:
            lo, hi = keys[i - 1], k
            frac = (df - lo) / (hi - lo)
            return _T_CRITICAL_95[lo] + frac * (_T_CRITICAL_95[hi] - _T_CRITICAL_95[lo])
    return _Z_FALLBACK
