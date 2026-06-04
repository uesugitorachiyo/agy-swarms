"""D5.0 Phase-5 precondition and baseline manifest audit."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

__all__ = [
    "Phase5PreconditionIssue",
    "Phase5PreconditionReport",
    "Phase5PreconditionStatus",
    "evaluate_phase5_preconditions",
]


class Phase5PreconditionStatus(StrEnum):
    """Whether AC-5 gates are allowed to run."""

    PASSED = "passed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Phase5PreconditionIssue:
    """One blocking precondition failure."""

    id: str
    metric: str
    message: str
    evidence: str = ""


@dataclass(frozen=True)
class Phase5PreconditionReport:
    """Fail-closed report for Phase-5 M1/M2/M3 gate prerequisites."""

    status: Phase5PreconditionStatus
    blockers: tuple[Phase5PreconditionIssue, ...]
    reported_only: dict[str, str]
    pins: dict[str, Any]

    @property
    def blocking_issue_ids(self) -> tuple[str, ...]:
        return tuple(issue.id for issue in self.blockers)


def evaluate_phase5_preconditions(root: Path | str = Path(".")) -> Phase5PreconditionReport:
    """Read local pins and baselines, returning blockers for missing AC-5 prerequisites."""
    root_path = Path(root)
    blockers: list[Phase5PreconditionIssue] = []
    reported_only: dict[str, str] = {}

    lock = _read_toml(root_path / "agy.lock", blockers, issue_id="phase5.agy_lock")
    config = _read_toml(
        root_path / "config" / "defaults.toml",
        blockers,
        issue_id="phase5.defaults",
    )
    phase0_results = root_path / "phase0-results.md"
    if not phase0_results.exists():
        blockers.append(
            Phase5PreconditionIssue(
                id="phase5.phase0_results",
                metric="M1/M2/M3",
                message="phase0-results.md is required for baseline provenance",
            )
        )

    benchmarks = lock.get("benchmarks", {})
    phase0 = lock.get("phase0", {})
    phase5 = config.get("phase5", {})
    measurement_environment = config.get("measurement_environment", {})
    baseline_paths = lock.get("phase5_baselines", {})

    _require_hashed_file(
        root_path,
        path=Path("benchmarks/reference_task.md"),
        expected_hash=benchmarks.get("reference_task_sha"),
        issue_id="m3.reference_task_sha",
        metric="M3",
        blockers=blockers,
    )
    _require_hashed_file(
        root_path,
        path=Path("benchmarks/judge_rubric.md"),
        expected_hash=benchmarks.get("judge_rubric_sha"),
        issue_id="m1.rubric_sha",
        metric="M1",
        blockers=blockers,
    )
    _require_recorded_string(
        phase0.get("blinding_seed"),
        issue_id="m1.blinding_seed",
        metric="M1",
        message="blinding_seed must be recorded before M1 can gate",
        blockers=blockers,
    )
    _require_positive_int(
        phase5.get("m1_runs_k"),
        issue_id="m1.runs_k",
        metric="M1",
        message="m1_runs_k must be a positive integer",
        blockers=blockers,
    )
    _require_minimum_float(
        phase5.get("m1_ci_lower_bound"),
        minimum=0.95,
        issue_id="m1.ci_lower_bound",
        metric="M1",
        message="m1_ci_lower_bound must be recorded and at least 0.95",
        blockers=blockers,
    )

    _require_recorded_string(
        phase0.get("cache_mult"),
        issue_id="m2.cache_mult",
        metric="M2",
        message="cache_mult must be recorded before M2 can gate",
        blockers=blockers,
    )
    _require_minimum_float(
        phase5.get("m2_billable_token_ratio"),
        minimum=0.0,
        issue_id="m2.billable_token_ratio",
        metric="M2",
        message="m2_billable_token_ratio must be recorded",
        blockers=blockers,
    )
    _require_json_baseline(
        root_path,
        Path(baseline_paths.get("opus_baseline_path", "benchmarks/opus-baseline.json")),
        issue_id="m2.opus_baseline",
        metric="M2",
        blockers=blockers,
    )

    _require_minimum_float(
        phase5.get("m3_wallclock_ratio"),
        minimum=0.0,
        issue_id="m3.wallclock_ratio",
        metric="M3",
        message="m3_wallclock_ratio must be recorded",
        blockers=blockers,
    )
    _require_existing_file(
        root_path,
        Path(baseline_paths.get("ao2_wallclock_path", "benchmarks/ao2-baseline.md")),
        issue_id="m3.ao2_wallclock_baseline",
        metric="M3",
        message="ao2 wall-clock baseline manifest is required",
        blockers=blockers,
    )
    _require_existing_file(
        root_path,
        Path(
            baseline_paths.get(
                "factory_v3_wallclock_path",
                "benchmarks/factory-v3-baseline.md",
            )
        ),
        issue_id="m3.factory_v3_wallclock_baseline",
        metric="M3",
        message="factory-v3 wall-clock baseline manifest is required",
        blockers=blockers,
    )
    for field in ("host_class", "arch", "provider_region", "network_profile"):
        _require_recorded_string(
            measurement_environment.get(field),
            issue_id=f"m3.measurement_environment.{field}",
            metric="M3",
            message=f"measurement_environment.{field} must be recorded",
            blockers=blockers,
        )
    _require_positive_int(
        measurement_environment.get("logical_cores"),
        issue_id="m3.measurement_environment.logical_cores",
        metric="M3",
        message="measurement_environment.logical_cores must be positive",
        blockers=blockers,
    )
    _require_positive_int(
        measurement_environment.get("ram_gb"),
        issue_id="m3.measurement_environment.ram_gb",
        metric="M3",
        message="measurement_environment.ram_gb must be positive",
        blockers=blockers,
    )

    factory_token_path = root_path / "benchmarks" / "factory-v3-token-baseline.json"
    reported_only["factory_v3_token_baseline"] = (
        "present_reported_only" if factory_token_path.exists() else "missing_reported_only"
    )

    pins = {
        "reference_task_sha": benchmarks.get("reference_task_sha", ""),
        "judge_rubric_sha": benchmarks.get("judge_rubric_sha", ""),
        "blinding_seed": phase0.get("blinding_seed", ""),
        "cache_mult": phase0.get("cache_mult", ""),
        "m1_runs_k": phase5.get("m1_runs_k"),
        "m1_ci_lower_bound": phase5.get("m1_ci_lower_bound"),
        "m2_billable_token_ratio": phase5.get("m2_billable_token_ratio"),
        "m3_wallclock_ratio": phase5.get("m3_wallclock_ratio"),
        "measurement_environment": dict(measurement_environment),
    }
    return Phase5PreconditionReport(
        status=Phase5PreconditionStatus.BLOCKED if blockers else Phase5PreconditionStatus.PASSED,
        blockers=tuple(blockers),
        reported_only=reported_only,
        pins=pins,
    )


def _read_toml(
    path: Path,
    blockers: list[Phase5PreconditionIssue],
    *,
    issue_id: str,
) -> dict[str, Any]:
    if not path.exists():
        blockers.append(
            Phase5PreconditionIssue(
                id=issue_id,
                metric="M1/M2/M3",
                message=f"{path} is required",
            )
        )
        return {}
    return tomllib.loads(path.read_text())


def _require_hashed_file(
    root: Path,
    *,
    path: Path,
    expected_hash: Any,
    issue_id: str,
    metric: str,
    blockers: list[Phase5PreconditionIssue],
) -> None:
    _require_recorded_string(
        expected_hash,
        issue_id=issue_id,
        metric=metric,
        message=f"{path} hash must be recorded",
        blockers=blockers,
    )
    full_path = root / path
    if not full_path.exists():
        blockers.append(
            Phase5PreconditionIssue(
                id=f"{issue_id}.file",
                metric=metric,
                message=f"{path} is required",
            )
        )
        return
    if _is_recorded_string(expected_hash):
        content = full_path.read_bytes().replace(b"\r\n", b"\n")
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            blockers.append(
                Phase5PreconditionIssue(
                    id=f"{issue_id}.mismatch",
                    metric=metric,
                    message=f"{path} hash does not match lockfile",
                    evidence=f"expected={expected_hash} actual={actual_hash}",
                )
            )


def _require_json_baseline(
    root: Path,
    path: Path,
    *,
    issue_id: str,
    metric: str,
    blockers: list[Phase5PreconditionIssue],
) -> None:
    full_path = root / path
    if not full_path.exists():
        blockers.append(
            Phase5PreconditionIssue(
                id=issue_id,
                metric=metric,
                message=f"{path} is required",
            )
        )
        return
    payload = json.loads(full_path.read_text())
    if int(payload.get("billable_equivalent_tokens", 0)) <= 0:
        blockers.append(
            Phase5PreconditionIssue(
                id=f"{issue_id}.billable_tokens",
                metric=metric,
                message=f"{path} must record positive billable_equivalent_tokens",
            )
        )


def _require_existing_file(
    root: Path,
    path: Path,
    *,
    issue_id: str,
    metric: str,
    message: str,
    blockers: list[Phase5PreconditionIssue],
) -> None:
    if not (root / path).exists():
        blockers.append(
            Phase5PreconditionIssue(
                id=issue_id,
                metric=metric,
                message=message,
            )
        )


def _require_recorded_string(
    value: Any,
    *,
    issue_id: str,
    metric: str,
    message: str,
    blockers: list[Phase5PreconditionIssue],
) -> None:
    if not _is_recorded_string(value):
        blockers.append(Phase5PreconditionIssue(id=issue_id, metric=metric, message=message))


def _require_positive_int(
    value: Any,
    *,
    issue_id: str,
    metric: str,
    message: str,
    blockers: list[Phase5PreconditionIssue],
) -> None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    if parsed <= 0:
        blockers.append(Phase5PreconditionIssue(id=issue_id, metric=metric, message=message))


def _require_minimum_float(
    value: Any,
    *,
    minimum: float,
    issue_id: str,
    metric: str,
    message: str,
    blockers: list[Phase5PreconditionIssue],
) -> None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = -1.0
    if parsed < minimum:
        blockers.append(Phase5PreconditionIssue(id=issue_id, metric=metric, message=message))


def _is_recorded_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip() != "UNRECORDED"
