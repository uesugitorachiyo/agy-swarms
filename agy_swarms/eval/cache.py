"""D5.5 Prompt-cache stability and cache-hit reporting."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "CachePrefixSnapshot",
    "CacheStabilityIncomplete",
    "CacheStabilityReport",
    "CacheStabilityStatus",
    "build_cache_report",
    "hash_prefix",
]

# Minimum reruns required to verify prefix stability.
MIN_STABILITY_RERUNS: int = 2


class CacheStabilityStatus(StrEnum):
    """Cache stability gate status."""

    PASSED = "passed"
    FAILED = "failed"


class CacheStabilityIncomplete(ValueError):
    """Raised when cache stability cannot be assessed."""


@dataclass(frozen=True)
class CachePrefixSnapshot:
    """One snapshot of a cacheable prefix for a specific task and rerun."""

    task_id: str
    rerun_index: int
    prefix_sha256: str
    prefix_length_bytes: int
    cache_hit: bool
    note: str = ""


@dataclass(frozen=True)
class CacheStabilityReport:
    """Cache stability and hit-rate report."""

    status: CacheStabilityStatus
    prefix_stable: bool
    cache_hit_rate: float
    num_tasks: int
    num_snapshots: int
    snapshots: tuple[CachePrefixSnapshot, ...]
    instability_details: dict[str, list[str]]
    reported_only: dict[str, Any] = field(default_factory=dict)


def hash_prefix(prefix_bytes: bytes) -> str:
    """SHA-256 hash a cacheable prefix for stability comparison."""
    return hashlib.sha256(prefix_bytes).hexdigest()


def build_cache_report(
    *,
    snapshots: tuple[CachePrefixSnapshot, ...],
    min_stability_reruns: int = MIN_STABILITY_RERUNS,
) -> CacheStabilityReport:
    """Build a cache stability and hit-rate report.

    Fail-closed on:
    - no snapshots
    - fewer than min_stability_reruns for any task
    - unstable prefix (differing hashes across reruns of same task)
    """
    # --- fail-closed: no snapshots ---
    if not snapshots:
        raise CacheStabilityIncomplete("cache stability requires at least one snapshot")

    # --- group by task ---
    by_task: dict[str, list[CachePrefixSnapshot]] = {}
    for snap in snapshots:
        by_task.setdefault(snap.task_id, []).append(snap)

    # --- fail-closed: minimum reruns per task ---
    for task_id, task_snaps in by_task.items():
        if len(task_snaps) < min_stability_reruns:
            raise CacheStabilityIncomplete(
                f"task {task_id!r} has {len(task_snaps)} rerun(s); "
                f"need >= {min_stability_reruns} to verify stability"
            )

    # --- check prefix stability ---
    instability_details: dict[str, list[str]] = {}
    for task_id, task_snaps in by_task.items():
        unique_hashes = sorted({s.prefix_sha256 for s in task_snaps})
        if len(unique_hashes) > 1:
            instability_details[task_id] = unique_hashes

    prefix_stable = len(instability_details) == 0

    # --- compute cache-hit rate ---
    total_hits = sum(1 for s in snapshots if s.cache_hit)
    cache_hit_rate = total_hits / len(snapshots) if snapshots else 0.0

    return CacheStabilityReport(
        status=(CacheStabilityStatus.PASSED if prefix_stable else CacheStabilityStatus.FAILED),
        prefix_stable=prefix_stable,
        cache_hit_rate=round(cache_hit_rate, 4),
        num_tasks=len(by_task),
        num_snapshots=len(snapshots),
        snapshots=snapshots,
        instability_details=instability_details,
        reported_only={
            "total_hits": total_hits,
            "total_misses": len(snapshots) - total_hits,
            "tasks_with_instability": list(instability_details.keys()),
        },
    )
