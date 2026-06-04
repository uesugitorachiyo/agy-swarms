"""D5.5 Prompt-cache stability and cache-hit reporting tests."""

import pytest

from agy_swarms.eval.cache import (
    CachePrefixSnapshot,
    CacheStabilityIncomplete,
    CacheStabilityStatus,
    build_cache_report,
    hash_prefix,
)

STABLE_HASH = hash_prefix(b"You are a helpful coding assistant. Use the pinned rubric.")
DRIFTED_HASH = hash_prefix(b"You are a helpful coding assistant. Timestamp: 2026-05-31T12:00:00Z")


def _make_stable_snapshots(
    task_ids: tuple[str, ...] = ("task-0", "task-1"),
    reruns: int = 2,
) -> tuple[CachePrefixSnapshot, ...]:
    """Build snapshots with identical prefix hashes across reruns (stable)."""
    result = []
    for tid in task_ids:
        for r in range(reruns):
            result.append(
                CachePrefixSnapshot(
                    task_id=tid,
                    rerun_index=r,
                    prefix_sha256=STABLE_HASH,
                    prefix_length_bytes=58,
                    cache_hit=r > 0,  # first run is a miss, reruns are hits
                )
            )
    return tuple(result)


# --- TDD focus 1: identical static prefix passes ---


def test_identical_static_prefix_passes():
    report = build_cache_report(snapshots=_make_stable_snapshots())
    assert report.status == CacheStabilityStatus.PASSED
    assert report.prefix_stable is True
    assert report.num_tasks == 2
    assert report.num_snapshots == 4


def test_three_reruns_all_stable():
    report = build_cache_report(snapshots=_make_stable_snapshots(reruns=3))
    assert report.status == CacheStabilityStatus.PASSED
    assert report.prefix_stable is True
    assert report.num_snapshots == 6


# --- TDD focus 2: timestamp or dynamic key in cacheable prefix fails ---


def test_timestamp_in_prefix_causes_instability():
    snapshots = (
        CachePrefixSnapshot("task-0", 0, STABLE_HASH, 58, False),
        CachePrefixSnapshot("task-0", 1, DRIFTED_HASH, 72, False),  # different hash!
    )
    report = build_cache_report(snapshots=snapshots)
    assert report.status == CacheStabilityStatus.FAILED
    assert report.prefix_stable is False
    assert "task-0" in report.instability_details
    assert len(report.instability_details["task-0"]) == 2


def test_one_task_unstable_others_stable_still_fails():
    stable = _make_stable_snapshots(task_ids=("task-0",), reruns=2)
    unstable = (
        CachePrefixSnapshot("task-1", 0, STABLE_HASH, 58, False),
        CachePrefixSnapshot("task-1", 1, DRIFTED_HASH, 72, False),
    )
    report = build_cache_report(snapshots=stable + unstable)
    assert report.status == CacheStabilityStatus.FAILED
    assert "task-1" in report.instability_details
    assert "task-0" not in report.instability_details


def test_dynamic_key_with_three_distinct_hashes_fails():
    h1 = hash_prefix(b"prefix-v1")
    h2 = hash_prefix(b"prefix-v2")
    h3 = hash_prefix(b"prefix-v3")
    snapshots = (
        CachePrefixSnapshot("task-0", 0, h1, 10, False),
        CachePrefixSnapshot("task-0", 1, h2, 10, False),
        CachePrefixSnapshot("task-0", 2, h3, 10, False),
    )
    report = build_cache_report(snapshots=snapshots)
    assert report.status == CacheStabilityStatus.FAILED
    assert len(report.instability_details["task-0"]) == 3


# --- TDD focus 3: cache-hit rate is recorded per benchmark run ---


def test_cache_hit_rate_recorded():
    # 2 tasks × 2 reruns: first run miss, rerun hit → 2 hits / 4 total = 0.5
    report = build_cache_report(snapshots=_make_stable_snapshots())
    assert report.cache_hit_rate == 0.5
    assert report.reported_only["total_hits"] == 2
    assert report.reported_only["total_misses"] == 2


def test_all_hits_gives_rate_one():
    snapshots = tuple(CachePrefixSnapshot("task-0", r, STABLE_HASH, 58, True) for r in range(3))
    report = build_cache_report(snapshots=snapshots)
    assert report.cache_hit_rate == 1.0


def test_all_misses_gives_rate_zero():
    snapshots = tuple(CachePrefixSnapshot("task-0", r, STABLE_HASH, 58, False) for r in range(2))
    report = build_cache_report(snapshots=snapshots)
    assert report.cache_hit_rate == 0.0


# --- fail-closed: edge cases ---


def test_no_snapshots_raises():
    with pytest.raises(CacheStabilityIncomplete, match="at least one"):
        build_cache_report(snapshots=())


def test_single_rerun_raises_when_min_is_two():
    snapshots = (CachePrefixSnapshot("task-0", 0, STABLE_HASH, 58, False),)
    with pytest.raises(CacheStabilityIncomplete, match="rerun"):
        build_cache_report(snapshots=snapshots, min_stability_reruns=2)


def test_single_rerun_passes_when_min_is_one():
    snapshots = (CachePrefixSnapshot("task-0", 0, STABLE_HASH, 58, False),)
    report = build_cache_report(snapshots=snapshots, min_stability_reruns=1)
    assert report.status == CacheStabilityStatus.PASSED


# --- hash_prefix utility ---


def test_hash_prefix_is_deterministic():
    data = b"stable content"
    assert hash_prefix(data) == hash_prefix(data)


def test_hash_prefix_differs_for_different_content():
    assert hash_prefix(b"content-a") != hash_prefix(b"content-b")


# --- reported_only ---


def test_reported_only_includes_instability_task_list():
    snapshots = (
        CachePrefixSnapshot("task-0", 0, STABLE_HASH, 58, False),
        CachePrefixSnapshot("task-0", 1, DRIFTED_HASH, 72, False),
    )
    report = build_cache_report(snapshots=snapshots)
    assert report.reported_only["tasks_with_instability"] == ["task-0"]


def test_stable_report_has_empty_instability_list():
    report = build_cache_report(snapshots=_make_stable_snapshots())
    assert report.reported_only["tasks_with_instability"] == []
