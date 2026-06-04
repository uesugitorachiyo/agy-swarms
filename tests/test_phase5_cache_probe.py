from __future__ import annotations

from scripts.phase5_d5_5_cache_probe import run_probe


def test_phase5_cache_probe_records_stability_evidence():
    result = run_probe(write_output=False)

    assert result["gate"] == "D5.5/cache-stability"
    assert result["passed"] is True
    assert result["cache"]["status"] == "passed"
    assert result["cache"]["prefix_stable"] is True
    assert result["cache"]["num_tasks"] == 4
    assert result["cache"]["num_snapshots"] == 8
    assert result["cache"]["cache_hit_rate"] == 0.5  # 4 hits / 8 total
    assert result["cache"]["instability_details"] == {}

    # Verify all snapshots have identical prefix hash per task
    by_task: dict[str, set[str]] = {}
    for snap in result["cache"]["snapshots"]:
        by_task.setdefault(snap["task_id"], set()).add(snap["prefix_sha256"])
    for task_id, hashes in by_task.items():
        assert len(hashes) == 1, f"task {task_id} has unstable prefix"

    # Verify provenance
    assert result["provenance"]["cache_mult_pin"]
    assert result["provenance"]["model_snapshot"]
