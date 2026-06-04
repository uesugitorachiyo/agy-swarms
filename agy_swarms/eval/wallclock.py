"""D5.4 M3 wall-clock harness and breakdown."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "BreakdownBucket",
    "M3GateStatus",
    "WallClockIncomplete",
    "WallClockReport",
    "WallClockRun",
    "build_wallclock_report",
]

# Breakdown buckets that every timed run must record.
REQUIRED_BREAKDOWN_BUCKETS: tuple[str, ...] = (
    "dispatch_setup",
    "worker_exec",
    "barrier_wait",
    "verify",
    "conflict_resolution",
    "synthesis",
)

# Measurement-environment fields that must be present and non-empty before M3 gates.
REQUIRED_ENVIRONMENT_FIELDS: tuple[str, ...] = (
    "host_class",
    "logical_cores",
    "ram_gb",
    "arch",
    "provider_region",
    "network_profile",
)

# Minimum number of timed repeats before M3 can gate.
MIN_REPEATS: int = 3


class M3GateStatus(StrEnum):
    """M3 wall-clock gate status."""

    PASSED = "passed"
    FAILED = "failed"


class BreakdownBucket(StrEnum):
    """Named breakdown buckets for wall-clock time accounting."""

    DISPATCH_SETUP = "dispatch_setup"
    WORKER_EXEC = "worker_exec"
    BARRIER_WAIT = "barrier_wait"
    VERIFY = "verify"
    CONFLICT_RESOLUTION = "conflict_resolution"
    SYNTHESIS = "synthesis"


class WallClockIncomplete(ValueError):
    """Raised when M3 cannot gate because mandatory evidence is absent."""


@dataclass(frozen=True)
class WallClockRun:
    """One timed run with wall-clock total and per-bucket breakdown."""

    run_id: str
    wall_clock_s: float
    breakdown: dict[str, float] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class WallClockReport:
    """M3 gate report over repeated wall-clock runs."""

    status: M3GateStatus
    candidate_median_s: float
    ao2_baseline_s: float
    ao2_threshold_s: float
    factory_v3_baseline_s: float
    factory_v3_threshold_s: float
    target_ratio: float
    num_repeats: int
    measurement_environment: dict[str, Any]
    runs: tuple[WallClockRun, ...]
    reported_only: dict[str, Any]


def build_wallclock_report(
    *,
    runs: tuple[WallClockRun, ...],
    ao2_baseline_s: float | None,
    factory_v3_baseline_s: float | None,
    target_ratio: float,
    measurement_environment: dict[str, Any] | None = None,
    required_breakdown_buckets: tuple[str, ...] = REQUIRED_BREAKDOWN_BUCKETS,
) -> WallClockReport:
    """Build a fail-closed M3 report for the candidate wall-clock runs.

    Fail-closed on:
    - single timed run (< MIN_REPEATS)
    - missing/invalid measurement environment
    - missing mandatory baseline
    - missing breakdown bucket in any run
    - candidate median above threshold for either baseline
    """
    # --- fail-closed: mandatory baselines ---
    if ao2_baseline_s is None or ao2_baseline_s <= 0:
        raise WallClockIncomplete("ao2 wall-clock baseline is required before M3 can gate")
    if factory_v3_baseline_s is None or factory_v3_baseline_s <= 0:
        raise WallClockIncomplete("factory-v3 wall-clock baseline is required before M3 can gate")

    # --- fail-closed: target ratio ---
    if target_ratio <= 0:
        raise WallClockIncomplete("m3 target_ratio must be positive")

    # --- fail-closed: measurement environment ---
    _validate_measurement_environment(measurement_environment)

    # --- fail-closed: minimum repeats ---
    if len(runs) < MIN_REPEATS:
        raise WallClockIncomplete(f"M3 requires >= {MIN_REPEATS} repeats; got {len(runs)}")

    # --- fail-closed: breakdown buckets ---
    for run in runs:
        _validate_breakdown_buckets(run, required_breakdown_buckets)
        if run.wall_clock_s <= 0:
            raise WallClockIncomplete(f"wall_clock_s must be positive for run {run.run_id!r}")

    # --- compute median and thresholds ---
    candidate_median = statistics.median(r.wall_clock_s for r in runs)
    ao2_threshold = ao2_baseline_s * target_ratio
    factory_v3_threshold = factory_v3_baseline_s * target_ratio

    passed = candidate_median <= ao2_threshold and candidate_median <= factory_v3_threshold

    return WallClockReport(
        status=M3GateStatus.PASSED if passed else M3GateStatus.FAILED,
        candidate_median_s=candidate_median,
        ao2_baseline_s=ao2_baseline_s,
        ao2_threshold_s=ao2_threshold,
        factory_v3_baseline_s=factory_v3_baseline_s,
        factory_v3_threshold_s=factory_v3_threshold,
        target_ratio=target_ratio,
        num_repeats=len(runs),
        measurement_environment=measurement_environment or {},
        runs=runs,
        reported_only={
            "ao2_ratio": round(candidate_median / ao2_baseline_s, 4),
            "factory_v3_ratio": round(candidate_median / factory_v3_baseline_s, 4),
        },
    )


def _validate_measurement_environment(env: dict[str, Any] | None) -> None:
    """Fail closed if any required measurement-environment field is missing or empty."""
    if env is None:
        raise WallClockIncomplete("measurement environment is required before M3 can gate")
    for field_name in REQUIRED_ENVIRONMENT_FIELDS:
        value = env.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise WallClockIncomplete(
                f"measurement environment field {field_name!r} is required before M3 can gate"
            )


def _validate_breakdown_buckets(run: WallClockRun, required: tuple[str, ...]) -> None:
    """Fail closed if any required breakdown bucket is missing from a run."""
    missing = [b for b in required if b not in run.breakdown]
    if missing:
        raise WallClockIncomplete(
            f"run {run.run_id!r} missing breakdown bucket(s): {', '.join(missing)}"
        )
